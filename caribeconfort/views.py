import base64
import csv
import hashlib
from html import escape as escape_html
from io import BytesIO
import logging
import math
import random
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps
from pathlib import Path
from smtplib import SMTPAuthenticationError, SMTPException
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ValidationError
from django.contrib import messages
from django.contrib.auth.hashers import check_password, make_password
from django.core.files.storage import FileSystemStorage
from django.core.validators import validate_email
from django.core.mail import EmailMessage, get_connection, send_mail
from django.core.paginator import Paginator
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.db.models import Avg, Count, Exists, OuterRef, Q, Sum
from django.forms import ImageField
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.crypto import get_random_string
from caribeconfort.formato import formato_numero_colombiano
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from caribeconfort.models import (Habitaciones, Servicios,TipoHabitacion, Usuarios, CategoriaGaleria, ImagenGaleria,
Planes, CaracteristicaPlan, Huespedes, Roles, Pagos, Reservas, Hoteles, ServicioReserva, Acompanante,
CodigosConvenio, TipoConvenio, ReglaDescuento)
from caribeconfort.models import Resena

logger = logging.getLogger(__name__)

MOTIVOS_RECHAZO_SERVICIO = {
    'sin_disponibilidad': 'Sin disponibilidad en el horario solicitado',
    'mantenimiento': 'Servicio en mantenimiento',
    'datos_incompletos': 'Datos incompletos del huésped',
    'fuera_horario': 'Fuera de horario de atención',
}


def _fernet_credenciales_correo():
    clave = (getattr(settings, 'EMAIL_CREDENTIAL_ENCRYPTION_KEY', '') or '').strip()
    if not clave:
        secreto = getattr(settings, 'SECRET_KEY', '')
        if not secreto:
            raise ValueError('Define SECRET_KEY para cifrar las credenciales SMTP.')
        material = hashlib.sha256(
            ('caribeconfort.smtp.credentials:' + secreto).encode('utf-8')
        ).digest()
        clave = base64.urlsafe_b64encode(material).decode('ascii')
    try:
        return Fernet(clave.encode('ascii'))
    except (ValueError, UnicodeError) as error:
        raise ValueError(
            'EMAIL_CREDENTIAL_ENCRYPTION_KEY debe ser una clave Fernet válida.'
        ) from error


def _cifrar_contrasena_smtp(contrasena):
    return _fernet_credenciales_correo().encrypt(
        contrasena.encode('utf-8')
    ).decode('ascii')


def _descifrar_contrasena_smtp(contrasena_cifrada):
    try:
        return _fernet_credenciales_correo().decrypt(
            contrasena_cifrada.encode('ascii')
        ).decode('utf-8')
    except (InvalidToken, UnicodeError) as error:
        raise RuntimeError(
            'No se pudo descifrar la contraseña SMTP; verifica EMAIL_CREDENTIAL_ENCRYPTION_KEY.'
        ) from error


def _correo_huesped(huesped):
    """Obtiene el correo de contacto del huésped o de su cuenta asociada."""
    correos = [huesped.correo or '']
    if huesped.usuarios_id:
        correos.append(huesped.usuarios.correo or '')
    for correo in correos:
        correo = correo.strip()
        if not correo:
            continue
        try:
            validate_email(correo)
        except ValidationError:
            logger.warning('El huésped %s tiene un correo inválido registrado.', huesped.pk)
            continue
        return correo
    return ''


def _conexion_correo_hotel():
    hotel = Hoteles.objects.filter(smtp_host__gt='').order_by('id').first()
    hotel_smtp_completo = hotel and all((
        hotel.smtp_host,
        hotel.smtp_port,
        hotel.smtp_username,
        hotel.smtp_from_email,
        hotel.smtp_password_encrypted,
    ))
    opciones = getattr(settings, 'MAILERS', {}).get('default', {}).get('OPTIONS', {})
    if hotel_smtp_completo:
        host = hotel.smtp_host
        port = hotel.smtp_port
        username = hotel.smtp_username
        password = _descifrar_contrasena_smtp(hotel.smtp_password_encrypted)
        remitente = hotel.smtp_from_email
        use_ssl = port == 465
        use_tls = hotel.smtp_use_tls and not use_ssl
    else:
        if not opciones.get('host'):
            if hotel:
                raise RuntimeError(
                    'La configuración SMTP del hotel está incompleta y no hay EMAIL_HOST alternativo.'
                )
            raise RuntimeError(
                'Configura el SMTP del hotel o define EMAIL_HOST para enviar correos.'
            )
        host = opciones['host']
        port = opciones['port']
        username = opciones['username']
        password = opciones['password']
        remitente = settings.DEFAULT_FROM_EMAIL
        use_ssl = opciones.get('use_ssl', False)
        use_tls = opciones.get('use_tls', False)

    if use_ssl and use_tls:
        raise RuntimeError('El SMTP no puede usar SSL y STARTTLS simultáneamente.')

    conexion = get_connection(
        host=host,
        port=port,
        username=username,
        password=password,
        use_tls=use_tls,
        use_ssl=use_ssl,
        timeout=10,
        fail_silently=False,
    )
    return conexion, remitente


def _normalizar_contrasena_smtp(host, contrasena):
    """Google muestra las contraseñas de aplicación agrupadas con espacios."""
    if (host or '').strip().lower() in {'smtp.gmail.com', 'smtp.googlemail.com'}:
        return ''.join((contrasena or '').split())
    return contrasena or ''


def _enviar_correo_hotel(asunto, titulo, mensaje, destinatario):
    destinatario = (destinatario or '').strip()
    if not destinatario:
        raise RuntimeError('El destinatario no tiene un correo válido registrado.')
    try:
        validate_email(destinatario)
    except ValidationError as error:
        raise RuntimeError('El destinatario no tiene un correo válido registrado.') from error
    hotel = Hoteles.objects.order_by('id').first()
    nombre_hotel = hotel.nombre if hotel else 'Caribe Confort'
    mensaje_html = escape_html(mensaje).replace('\n', '<br>')
    html_message = f'''<!doctype html>
<html lang="es"><head><meta charset="utf-8"></head>
<body style="margin:0;padding:32px 12px;background:#f1f5f3;font-family:Arial,sans-serif;color:#24464a">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:620px;margin:0 auto;background:#fff;border:1px solid #dfe8e4;border-radius:16px;overflow:hidden">
    <tr><td style="padding:24px 30px;background:#16484b;color:#fff">
      <div style="font-family:Georgia,serif;font-size:27px;font-weight:bold;letter-spacing:.3px">{escape_html(nombre_hotel)}</div>
      <div style="margin-top:5px;color:#dce9e5;font-size:12px;letter-spacing:1.6px;text-transform:uppercase">Hotel · Riohacha, La Guajira</div>
    </td></tr>
    <tr><td style="height:4px;background:#c6a15b;font-size:0">&nbsp;</td></tr>
    <tr><td style="padding:32px 30px">
      <h1 style="margin:0 0 18px;color:#16484b;font-size:23px;line-height:1.3">{escape_html(titulo)}</h1>
      <div style="color:#42595a;font-size:15px;line-height:1.8">{mensaje_html}</div>
    </td></tr>
    <tr><td style="padding:18px 30px;background:#f7f9f8;border-top:1px solid #e6ece9;color:#718184;font-size:12px;line-height:1.6">
      Este mensaje fue enviado automáticamente por {escape_html(nombre_hotel)}. Si necesitas ayuda, comunícate con recepción.
    </td></tr>
  </table>
</body></html>'''
    conexion, remitente = _conexion_correo_hotel()
    enviados = send_mail(
        asunto,
        mensaje,
        remitente,
        [destinatario],
        fail_silently=False,
        connection=conexion,
        html_message=html_message,
    )
    if enviados != 1:
        raise RuntimeError(f'El correo "{asunto}" no fue aceptado por el backend.')
    return enviados


def _enviar_factura_reserva(reserva):
    correo_destino = _correo_huesped(reserva.huespedes)
    if not correo_destino:
        raise RuntimeError('El huésped no tiene un correo válido registrado.')

    hotel = Hoteles.objects.order_by('id').first()
    if reserva.habitaciones_id:
        tipo_habitacion = reserva.habitaciones.tipohabitacion
        alojamiento = f'Habitación {reserva.habitaciones.numero}'
        if tipo_habitacion:
            alojamiento += f' · {tipo_habitacion.nombre}'
    else:
        alojamiento = reserva.planes.nombre if reserva.planes_id else 'Estancia'
    pagos = list(Pagos.objects.filter(reservas=reserva).exclude(
        metodopago='Pendiente',
    ).order_by('fecha', 'id'))
    servicios = list(ServicioReserva.objects.filter(
        reservas=reserva,
        estado='Aprobado',
    ).select_related('servicios').order_by('fecha', 'id'))
    huesped = f'{reserva.huespedes.nombres} {reserva.huespedes.apellidos}'
    contenido = _crear_pdf_factura_reserva(
        reserva,
        hotel,
        huesped,
        alojamiento,
        pagos,
        servicios,
    )
    conexion, remitente = _conexion_correo_hotel()
    correo = EmailMessage(
        f'Factura de tu estancia · Reserva CC-{reserva.id:04d}',
        (
            f'Hola {reserva.huespedes.nombres},\n\n'
            f'Gracias por hospedarte en {hotel.nombre if hotel else "Caribe Confort"}. '
            f'Adjuntamos la factura detallada de tu estancia (reserva CC-{reserva.id:04d}).\n\n'
            'Esperamos recibirte nuevamente.\n'
        ),
        remitente,
        [correo_destino],
        connection=conexion,
    )
    correo.attach(
        f'factura_reserva_CC-{reserva.id:04d}.pdf',
        contenido,
        'application/pdf',
    )
    if correo.send(fail_silently=False) != 1:
        raise RuntimeError('El servidor SMTP no aceptó el correo con la factura.')


def servir_logo_hotel(request, nombre_archivo):
    logo = Hoteles.objects.filter(
        logo=f'hoteles/logos/{nombre_archivo}',
    ).first()
    if not logo or not logo.logo:
        raise Http404
    try:
        archivo = logo.logo.open('rb')
    except FileNotFoundError as error:
        raise Http404 from error
    extension = Path(nombre_archivo).suffix.lower()
    tipos_contenido = {
        '.gif': 'image/gif',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.webp': 'image/webp',
    }
    return FileResponse(
        archivo,
        content_type=tipos_contenido.get(extension, 'application/octet-stream'),
    )


def _enviar_invitacion_resena(reserva, request):
    resena = Resena.objects.get_or_create(reserva=reserva)[0]
    if resena.correo_enviado:
        return True

    destinatario = _correo_huesped(reserva.huespedes)
    if not destinatario:
        logger.warning(
            'No se pudo enviar la invitación de reseña para la reserva %s: el huésped no tiene correo.',
            reserva.pk,
        )
        return False

    enlace = request.build_absolute_uri(
        reverse('dejar_resena', kwargs={'token': resena.token})
    )
    mensaje = (
        f"Hola {reserva.huespedes.nombres},\n\n"
        f"Gracias por hospedarte en Caribe Confort. Cuéntanos cómo fue tu estancia "
        f"en la reserva CC-{reserva.pk:04d}:\n\n{enlace}\n\n"
        "El enlace es personal y solo permite enviar una reseña."
    )

    try:
        enviados = _enviar_correo_hotel(
            _('¿Cómo estuvo tu estancia en Caribe Confort?'),
            'Cuéntanos cómo estuvo tu estancia',
            mensaje,
            destinatario,
        )
    except RuntimeError as error:
        logger.warning(
            'No se pudo enviar la invitación de reseña para la reserva %s: %s',
            reserva.pk,
            error,
        )
        return False
    except (SMTPException, OSError):
        logger.exception(
            'No se pudo enviar la invitación de reseña para la reserva %s.',
            reserva.pk,
        )
        return False

    if enviados != 1:
        logger.error(
            'El backend no aceptó la invitación de reseña para la reserva %s.',
            reserva.pk,
        )
        return False

    resena.correo_enviado = True
    resena.save(update_fields=['correo_enviado'])
    return True


def _regla_descuento_estancia(noches):
    return ReglaDescuento.objects.filter(
        estado=True,
        dias_minimos__lte=noches,
        porcentaje__gt=0,
        porcentaje__lte=100,
    ).order_by('-dias_minimos', '-porcentaje').first()



NACIONALIDADES = {
    'Colombiana':          'Colombia',
    'Venezolana':          'Venezuela',
    'Ecuatoriana':         'Ecuador',
    'Peruana':             'Perú',
    'Brasileña':           'Brasil',
    'Argentina':           'Argentina',
    'Chilena':             'Chile',
    'Boliviana':           'Bolivia',
    'Uruguaya':            'Uruguay',
    'Paraguaya':           'Paraguay',
    'Mexicana':            'México',
    'Panameña':            'Panamá',
    'Costarricense':       'Costa Rica',
    'Cubana':              'Cuba',
    'Dominicana':          'República Dominicana',
    'Puertorriqueña':      'Puerto Rico',
    'Estadounidense':      'Estados Unidos',
    'Canadiense':          'Canadá',
    'Española':            'España',
    'Francesa':            'Francia',
    'Italiana':            'Italia',
    'Alemana':             'Alemania',
    'Británica':           'Reino Unido',
    'Portuguesa':          'Portugal',
    'Otra':                'Otra',
}

def home(request):
    hotel = Hoteles.objects.order_by('id').first()
    direccion_mapa = (hotel.direccion or '').strip() if hotel else ''
    tipos = TipoHabitacion.objects.all().order_by('nombre')
    resenas_publicas = Resena.objects.filter(
        calificacion__isnull=False,
    ).exclude(comentario='')
    resumen_resenas = resenas_publicas.aggregate(
        promedio=Avg('calificacion'),
        total=Count('pk'),
    )
    resenas = resenas_publicas.select_related(
        'reserva__huespedes',
        'reserva__habitaciones__tipohabitacion',
        'reserva__planes',
    ).order_by('-fecha')[:3]
    imagenes_carrusel = list(
        ImagenGaleria.objects.filter(seccion='carrusel', estado=True, categoria__estado=True)
        .select_related('categoria').order_by('id')
    )
    imagenes_galeria_home = list(
        ImagenGaleria.objects.filter(seccion='galeria', estado=True, categoria__estado=True)
        .select_related('categoria').order_by('id')
    )
    for imagen in (*imagenes_carrusel, *imagenes_galeria_home):
        imagen.url_imagen = _url_imagen_local(imagen.imagen)
    imagenes_carrusel = [imagen for imagen in imagenes_carrusel if imagen.url_imagen]
    imagenes_galeria_home = [imagen for imagen in imagenes_galeria_home if imagen.url_imagen]
    return render(request, 'home.html', {
        'tipos': tipos,
        'resenas': resenas,
        'imagenes_carrusel': imagenes_carrusel,
        'imagenes_galeria_home': imagenes_galeria_home,
        'promedio_resenas': resumen_resenas['promedio'],
        'total_resenas': resumen_resenas['total'],
        'direccion_mapa': direccion_mapa or 'Riohacha, La Guajira, Colombia',
    })

def galeria(request):
    categoria_id = request.GET.get('categoria')
    busqueda = request.GET.get('q', '').strip()[:100]

    def imagenes_sin_repetir(queryset):
        unicas = []
        rutas_vistas = set()
        for imagen in queryset.order_by('id'):
            clave = (imagen.imagen or '').strip().replace('\\', '/').casefold()
            # Una ruta vacía no debe ocultar otros registros incompletos.
            clave = clave or f'registro:{imagen.pk}'
            if clave in rutas_vistas:
                continue
            rutas_vistas.add(clave)
            unicas.append(imagen)
        return unicas

    categorias_bd = CategoriaGaleria.objects.filter(
        estado=True,
        imagengaleria__estado=True,
        imagengaleria__seccion__in=SECCIONES_GALERIA_PUBLICA,
    ).distinct().order_by('orden')
    grupos_categorias = {}
    for categoria in categorias_bd:
        clave = categoria.nombre.strip().casefold()
        grupo = grupos_categorias.setdefault(clave, {
            'categoria': categoria,
            'ids': [],
        })
        grupo['ids'].append(categoria.id)

    categorias = []
    for grupo in grupos_categorias.values():
        categoria = grupo['categoria']
        registros_categoria = ImagenGaleria.objects.filter(
            categoria_id__in=grupo['ids'],
            estado=True,
            seccion__in=SECCIONES_GALERIA_PUBLICA,
        ).only('id', 'imagen')
        categoria.total = len(imagenes_sin_repetir(registros_categoria))
        categorias.append(categoria)

    registros_publicos = ImagenGaleria.objects.filter(
        estado=True,
        seccion__in=SECCIONES_GALERIA_PUBLICA,
        categoria__estado=True,
    )
    categoria_activa = None

    if categoria_id:
        categoria_seleccionada = CategoriaGaleria.objects.filter(
            id=categoria_id,
            estado=True,
        ).first()
        if categoria_seleccionada:
            grupo = grupos_categorias.get(categoria_seleccionada.nombre.strip().casefold())
            categoria_activa = grupo['categoria'] if grupo else categoria_seleccionada
            registros_publicos = registros_publicos.filter(
                categoria_id__in=grupo['ids'] if grupo else [categoria_seleccionada.id]
            )

    if busqueda:
        registros_publicos = registros_publicos.filter(
            Q(titulo__icontains=busqueda) | Q(categoria__nombre__icontains=busqueda)
        )

    imagenes = imagenes_sin_repetir(
        registros_publicos.select_related('categoria')
    )
    for imagen in imagenes:
        imagen.url_imagen = _url_imagen_local(imagen.imagen)

    total_general = len(imagenes_sin_repetir(ImagenGaleria.objects.filter(
        estado=True,
        seccion__in=SECCIONES_GALERIA_PUBLICA,
        categoria__estado=True,
    ).only('id', 'imagen')))

    context = {
        'categorias': categorias,
        'imagenes': imagenes,
        'categoria_activa': categoria_activa,
        'total_general': total_general,
        'busqueda': busqueda,
    }
    return render(request, 'clientes/galeria.html', context)

def planes(request):
    planes_qs = list(
        Planes.objects
        .filter(estado=True)
        .prefetch_related('caracteristicas')
        .order_by('orden', 'id')
    )
    planesnombre = Planes.objects.all

    todoplanes = Planes.objects.all



    for p in planes_qs:
        p.precio_fmt = f"{int(p.precio):,}".replace(",", ".")
        p.url_imagen = _url_imagen_local(p.imagen)

    context = {
        'planes': planes_qs,
        'todoplanes': todoplanes
    }
    return render(request, 'clientes/planes.html', context)

def servicios(request):
    categoria_activa = (request.GET.get('categoria') or '').strip()

    categorias_base = [
        {'nombre': 'Habitación',   'icono': 'cama'},
        {'nombre': 'Alimentación', 'icono': 'restaurante'},
        {'nombre': 'Minibar',      'icono': 'copa'},
        {'nombre': 'Recreación',   'icono': 'piscina'},
        {'nombre': 'Eventos',      'icono': 'evento'},
        {'nombre': 'Lavandería',   'icono': 'lavanderia'},
        {'nombre': 'Transporte',   'icono': 'transporte'},
        {'nombre': 'Otros',        'icono': 'estrella'},
    ]

    for c in categorias_base:
        c['total'] = Servicios.objects.filter(estado=True, categoria=c['nombre']).count()
    categorias = [categoria for categoria in categorias_base if categoria['total']]

    servicios_qs = Servicios.objects.filter(estado=True).order_by('nombre')
    if categoria_activa:
        servicios_qs = servicios_qs.filter(categoria=categoria_activa)

    servicios_disponibles = list(servicios_qs)
    for servicio in servicios_disponibles:
        servicio.url_imagen = _url_imagen_local(servicio.imagen)
    servicio_destacado = servicios_disponibles[0] if servicios_disponibles else None
    servicios_catalogo = servicios_disponibles[1:] if servicio_destacado else []

    total_general = Servicios.objects.filter(estado=True).count()

    reservas_activas = []

    huesped = None 
    
    if request.session.get('usuario_id'):
        try:
            huesped = Huespedes.objects.get(usuarios_id=request.session.get('usuario_id'))
            
            hoy = timezone.localdate()
            reservas_activas = Reservas.objects.filter(
                huespedes=huesped,
                fechasalida__gte=hoy,
                estado__in=['Pendiente', 'Confirmada', 'En curso']
            ).select_related('habitaciones', 'planes')
            
        except Huespedes.DoesNotExist:
            pass

    context = {
        'categorias': categorias,
        'servicio_destacado': servicio_destacado,
        'servicios': servicios_catalogo,
        'total_filtrados': len(servicios_disponibles),
        'categoria_activa': categoria_activa,
        'total_general': total_general,
        'reservas_activas': reservas_activas,
        'reserva_preseleccionada': request.GET.get('reserva_id', ''),
        'huesped': huesped,
    }
    return render(request, 'clientes/servicios.html', context)

def cancelar_reserva(request, reserva_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Método no permitido'}, status=405)
    usuario_id = request.session.get('usuario_id')
    rol = request.session.get('rol')
    es_personal = rol in {'Administrador', 'Recepcionista'}
    if not usuario_id and not es_personal:
        return JsonResponse({'success': False, 'message': 'Debes iniciar sesión para cancelar una reserva.'}, status=401)

    try:
        with transaction.atomic():
            reservas_bloqueadas = Reservas.objects.select_for_update()
            if es_personal:
                reserva = get_object_or_404(reservas_bloqueadas, id=reserva_id)
            else:
                reserva = get_object_or_404(
                    reservas_bloqueadas,
                    id=reserva_id,
                    huespedes__usuarios_id=usuario_id,
                )
            if reserva.estado == 'Cancelada':
                return JsonResponse({'success': False, 'message': 'La reserva ya estaba cancelada.'}, status=409)
            if reserva.estado == 'Finalizada':
                return JsonResponse({'success': False, 'message': 'No se puede cancelar una reserva finalizada.'}, status=409)

            reserva.estado = 'Cancelada'
            reserva.save(update_fields=['estado'])
            if reserva.habitaciones_id and not Reservas.objects.filter(
                habitaciones_id=reserva.habitaciones_id,
                estado__in=['Pendiente', 'Pagada - Por validar', 'Confirmada', 'En curso'],
                fechaentrada__lt=reserva.fechasalida,
                fechasalida__gt=reserva.fechaentrada,
            ).exclude(id=reserva.id).exists():
                reserva.habitaciones.estado = 'Disponible'
                reserva.habitaciones.save(update_fields=['estado'])
    except Http404:
        return JsonResponse({'success': False, 'message': 'Reserva no encontrada o no te pertenece.'}, status=404)
    except DatabaseError:
        logger.exception('Error de base de datos al cancelar la reserva CC-%s.', reserva_id)
        return JsonResponse({
            'success': False,
            'message': 'No se pudo cancelar la reserva por un error de base de datos. El estado no se confirmó; actualiza la página antes de reintentar.',
        }, status=500)
    except Exception:
        logger.exception('Error inesperado al cancelar la reserva CC-%s.', reserva_id)
        return JsonResponse({
            'success': False,
            'message': 'Ocurrió un error al cancelar la reserva. Actualiza la página y verifica su estado antes de reintentar.',
        }, status=500)

    correo_enviado = False
    correo_destino = _correo_huesped(reserva.huespedes)
    if correo_destino:
        try:
            correo_enviado = bool(_enviar_correo_hotel(
                f'Cancelación de Reserva CC-{reserva.id:04d}',
                'Tu reserva fue cancelada',
                f"Hola {reserva.huespedes.nombres},\n\nTe confirmamos que tu reserva CC-{reserva.id:04d} en Caribe Confort ha sido cancelada exitosamente.\n\nEsperamos verte en otra ocasión.",
                correo_destino,
            ))
        except Exception:
            logger.exception('La reserva CC-%s se canceló, pero no se pudo enviar el correo.', reserva.id)

    return JsonResponse({
        'success': True,
        'correo_enviado': correo_enviado,
        'message': (
            'Reserva cancelada y correo de confirmación enviado.' if correo_enviado
            else 'Reserva cancelada. No se pudo enviar el correo de confirmación; verifica la configuración SMTP y el correo del huésped.'
        ),
    })

def solicitar_servicio(request):
    if not request.session.get('usuario_id'):
        return JsonResponse({'ok': False, 'error': 'Debes iniciar sesión para solicitar un servicio.'}, status=401)

    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Método no permitido'}, status=405)

    servicio_id = request.POST.get('servicio_id')
    reserva_id = request.POST.get('reserva_id')
    cantidad_str = request.POST.get('cantidad', '1')
    solicitado_por = request.POST.get('solicitado_por', '').strip()
    beneficiario = request.POST.get('beneficiario', '').strip() or solicitado_por
    beneficiario_segundo = request.POST.get('beneficiario_segundo', '').strip()
    metodo_pago_preferido = request.POST.get('metodo_pago_preferido', '').strip()
    tarjeta_titular = request.POST.get('tarjeta_titular', '').strip()
    tarjeta_ultimos4 = request.POST.get('tarjeta_ultimos4', '').strip()
    nequi_titular = request.POST.get('nequi_titular', '').strip()
    nequi_celular = request.POST.get('nequi_celular', '').strip()

    if not servicio_id or not reserva_id:
        return JsonResponse({'ok': False, 'error': 'Faltan datos obligatorios.'}, status=400)

    if not solicitado_por or len(solicitado_por) > 100:
        return JsonResponse({
            'ok': False,
            'error': 'Indica el nombre de quien solicita el servicio (máximo 100 caracteres).',
        }, status=400)
    if not beneficiario or len(beneficiario) > 100 or len(beneficiario_segundo) > 100:
        return JsonResponse({
            'ok': False,
            'error': 'Indica el nombre de la persona beneficiaria (máximo 100 caracteres).',
        }, status=400)
    if metodo_pago_preferido not in {'Tarjeta', 'Nequi'}:
        return JsonResponse({
            'ok': False,
            'error': 'Selecciona Tarjeta o Nequi como método de pago preferido.',
        }, status=400)
    if metodo_pago_preferido == 'Tarjeta':
        if not tarjeta_titular or len(tarjeta_titular) > 100 or not re.fullmatch(r'\d{4}', tarjeta_ultimos4):
            return JsonResponse({
                'ok': False,
                'error': 'Indica el titular y los últimos cuatro dígitos de la tarjeta.',
            }, status=400)
        nequi_titular = ''
        nequi_celular = ''
    else:
        nequi_digitos = re.sub(r'\D', '', nequi_celular)
        if not nequi_titular or len(nequi_titular) > 100 or not 10 <= len(nequi_digitos) <= 15:
            return JsonResponse({
                'ok': False,
                'error': 'Indica el titular y un celular válido asociado a Nequi.',
            }, status=400)
        nequi_celular = ('+' if nequi_celular.strip().startswith('+') else '') + nequi_digitos
        tarjeta_titular = ''
        tarjeta_ultimos4 = ''

    try:
        cantidad = int(cantidad_str)
    except ValueError:
        return JsonResponse({'ok': False, 'error': 'La cantidad debe ser un número entero.'}, status=400)

    if cantidad < 1 or cantidad > 50:
        return JsonResponse({'ok': False, 'error': 'La cantidad debe estar entre 1 y 50.'}, status=400)

    try:
        huesped = Huespedes.objects.get(usuarios_id=request.session.get('usuario_id'))
        servicio = Servicios.objects.get(id=servicio_id, estado=True)
    except Servicios.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'El servicio no existe.'}, status=404)
    except Huespedes.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'No encontramos tu registro de huésped.'}, status=403)

    valor_total = servicio.precio * cantidad
    try:
        with transaction.atomic():
            reserva = Reservas.objects.select_for_update().get(
                id=reserva_id,
                huespedes=huesped,
                estado__in=['Pendiente', 'Pagada - Por validar', 'Confirmada', 'En curso'],
            )
            servicio_reserva = ServicioReserva.objects.create(
                reservas=reserva,
                servicios=servicio,
                cantidad=cantidad,
                valor=valor_total,
                solicitado_por=solicitado_por,
                beneficiario=beneficiario,
                beneficiario_segundo=beneficiario_segundo,
                metodo_pago_preferido=metodo_pago_preferido,
                tarjeta_titular=tarjeta_titular,
                tarjeta_ultimos4=tarjeta_ultimos4,
                nequi_titular=nequi_titular,
                nequi_celular=nequi_celular,
            )
            pago = Pagos.objects.create(
                reservas=reserva,
                valor=valor_total,
                metodopago='Pendiente',
                concepto='Servicio',
            )
            servicio_reserva.pago = pago
            servicio_reserva.save(update_fields=['pago'])
    except Reservas.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Reserva no válida o no te pertenece.'}, status=403)

    correo_destino = huesped.correo or (
        huesped.usuarios.correo if huesped.usuarios_id else ''
    )
    correo_enviado = False
    if correo_destino:
        try:
            correo_enviado = bool(_enviar_correo_hotel(
                'Solicitud de servicio recibida',
                'Recibimos tu solicitud',
                (
                    f'Hola {huesped.nombres},\n\n'
                    f'Recibimos tu solicitud de {servicio.nombre} para la reserva '
                    f'CC-{reserva.id:04d}.\n'
                    f'Cantidad: {cantidad}\n'
                    f'Solicitado por: {solicitado_por}\n'
                    f'Beneficiario(s): {beneficiario}'
                    + (f' y {beneficiario_segundo}' if beneficiario_segundo else '')
                    + '\n'
                    f'Método de pago preferido: {metodo_pago_preferido}\n'
                    f'Valor: ${formato_numero_colombiano(valor_total, 2)} COP\n\n'
                    'Recepción revisará la solicitud y te notificará cuando sea aprobada '
                    'y registrada en tu cuenta.'
                ),
                correo_destino,
            ))
        except Exception:
            logger.exception('No se pudo enviar la confirmación de servicio para la reserva CC-%s.', reserva.id)
    else:
        logger.warning('No se envió confirmación de servicio: el huésped de la reserva CC-%s no tiene correo.', reserva.id)

    return JsonResponse({
        'ok': True,
        'message': (
            'Servicio agregado a la reserva; el saldo queda pendiente de pago.'
            if correo_enviado else
            'Servicio agregado, pero no se pudo enviar el correo de confirmación.'
        ),
        'correo_enviado': correo_enviado,
        'cantidad': cantidad,
        'total': str(valor_total),
    })

def habitaciones(request):
    return render(request, 'clientes/habitaciones.html')

def imagenes(request):
    return render(request, 'admini/imagenes.html')


TAMANO_MAXIMO_IMAGEN = 10 * 1024 * 1024


def _guardar_imagen_catalogo(archivo, carpeta):
    extension = Path(archivo.name).suffix.lower()
    firmas = {
        '.jpg': lambda header: header.startswith(b'\xff\xd8\xff'),
        '.jpeg': lambda header: header.startswith(b'\xff\xd8\xff'),
        '.png': lambda header: header.startswith(b'\x89PNG\r\n\x1a\n'),
        '.gif': lambda header: header.startswith((b'GIF87a', b'GIF89a')),
        '.webp': lambda header: header.startswith(b'RIFF') and header[8:12] == b'WEBP',
    }
    if extension not in firmas:
        raise ValueError('La imagen debe ser JPG, PNG, WEBP o GIF.')
    if archivo.size > TAMANO_MAXIMO_IMAGEN:
        raise ValueError('La imagen no puede superar los 10 MB.')
    encabezado = archivo.read(12)
    archivo.seek(0)
    if not firmas[extension](encabezado):
        raise ValueError('El contenido del archivo no coincide con un formato de imagen permitido.')
    almacenamiento = FileSystemStorage(location=settings.MEDIA_ROOT)
    return almacenamiento.save(f'uploads/{carpeta}/{uuid4().hex}{extension}', archivo)


def _guardar_imagen_habitacion(archivo):
    return _guardar_imagen_catalogo(archivo, 'habitaciones')


def _eliminar_imagen_habitacion(ruta):
    if ruta.startswith('uploads/habitaciones/') and '..' not in Path(ruta).parts:
        FileSystemStorage(location=settings.MEDIA_ROOT).delete(ruta)


def _guardar_imagen_servicio(archivo):
    return _guardar_imagen_catalogo(archivo, 'servicios')


def _guardar_imagen_tipo_habitacion(archivo):
    return _guardar_imagen_catalogo(archivo, 'tipos-habitacion')


def _guardar_imagen_plan(archivo):
    return _guardar_imagen_catalogo(archivo, 'planes')


def _eliminar_imagen_servicio(ruta):
    if not ruta.startswith('uploads/servicios/') or '..' in Path(ruta).parts:
        return
    try:
        if Servicios.objects.filter(imagen=ruta).exists():
            return
    except DatabaseError:
        logger.exception('No se pudo comprobar si la imagen del servicio sigue en uso: %s', ruta)
        return
    FileSystemStorage(location=settings.MEDIA_ROOT).delete(ruta)


def _url_imagen_habitacion(ruta):
    if not ruta:
        return ''
    if ruta.startswith('img/imagenes/'):
        return f'/{settings.STATIC_URL.lstrip("/")}{ruta}'
    if ruta.startswith(('http://', 'https://', '/')):
        return ruta
    return f'/{settings.MEDIA_URL.strip("/")}/{ruta}'


def _url_imagen_local(ruta):
    if not ruta:
        return ''

    ruta = ruta.strip().replace('\\', '/')
    if ruta.startswith(('http://', 'https://', '//', '/')) or '..' in ruta.split('/'):
        return ''

    prefijo_static = settings.STATIC_URL.lstrip('/')
    if ruta.startswith(prefijo_static):
        return f'/{ruta}'
    if ruta.startswith('img/imagenes/'):
        return f'/{prefijo_static}{ruta}'
    if ruta.startswith('uploads/'):
        return f'/{settings.MEDIA_URL.strip("/")}/{ruta}'
    if '/' not in ruta:
        return f'/{prefijo_static}img/imagenes/{ruta}'
    return ''


def registrarhabitacion(request):
    if request.session.get('rol') != 'Administrador':
        return redirect('/login')

    if request.method == 'POST':
        numero = request.POST.get('numero', '').strip()
        tipo_id = request.POST.get('tipohabitacion', '').strip()
        estado = request.POST.get('estado', 'Disponible').strip()
        try:
            capacidad = int(request.POST.get('capacidad', ''))
            precio = Decimal(request.POST.get('precio', '').strip())
        except (ValueError, InvalidOperation, AttributeError):
            messages.error(request, 'La capacidad o la tarifa no son válidas.')
            return redirect('/rhabitaciones')

        tipo = TipoHabitacion.objects.filter(id=tipo_id).first() if tipo_id.isdigit() else None
        if not numero or len(numero) > 20 or Habitaciones.objects.filter(numero=numero).exists():
            messages.error(request, 'Ingresa un número de habitación válido que no esté registrado.')
        elif not tipo:
            messages.error(request, 'Selecciona un tipo de habitación válido.')
        elif estado not in {'Disponible', 'Bloqueada', 'Fuera-de-servicio'}:
            messages.error(request, 'Selecciona un estado inicial válido.')
        elif (
            capacidad < 1 or capacidad > 100 or not precio.is_finite()
            or precio <= 0 or precio > Decimal('99999999.99')
        ):
            messages.error(request, 'La capacidad debe estar entre 1 y 100 y la tarifa debe ser mayor que cero.')
        else:
            ruta_imagen = ''
            try:
                archivo = request.FILES.get('imagen')
                if archivo:
                    ruta_imagen = _guardar_imagen_habitacion(archivo)
                with transaction.atomic():
                    Habitaciones.objects.create(
                        numero=numero,
                        tipohabitacion=tipo,
                        capacidad=capacidad,
                        precio=precio.quantize(Decimal('0.01')),
                        estado=estado,
                        imagen=ruta_imagen or None,
                    )
            except ValueError as error:
                messages.error(request, str(error))
                return redirect('/rhabitaciones')
            except IntegrityError:
                if ruta_imagen:
                    _eliminar_imagen_habitacion(ruta_imagen)
                messages.error(request, 'Ese número de habitación ya fue registrado.')
            else:
                messages.success(request, f'Habitación {numero} registrada correctamente.')
                return redirect('/adminhabitaciones')

    return render(request, 'admini/registrarhabitacion.html', {
        'tipos_habitacion': TipoHabitacion.objects.order_by('nombre'),
        'estados_iniciales': [
            (valor, etiqueta) for valor, etiqueta in Habitaciones.estados
            if valor != 'Ocupada'
        ],
        'nombre': request.session.get('usuario_nom', 'Administrador'),
        'rol': request.session.get('rol', 'Administrador'),
    })

def requiere_login_cliente(funcion_original):
    @wraps(funcion_original)
    def wrapper(request, *args, **kwargs):
        if not request.session.get('usuario_id'):
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'ok': False, 
                    'error': 'Debes iniciar sesión para realizar una reserva.',
                    'redirect': '/login'
                }, status=401)
            return redirect('/login')
        return funcion_original(request, *args, **kwargs)
    return wrapper


def _buscar_convenio_valido(codigo, bloquear=False):
    queryset = CodigosConvenio.objects.select_related('tipoConvenio')
    if bloquear:
        queryset = queryset.select_for_update()
    return queryset.filter(
        Codigo__iexact=codigo.strip(),
        estado='Activo',
        FechaExpiracion__gte=timezone.localdate(),
        tipoConvenio__estado=True,
        tipoConvenio__PorcentajeDescuento__gt=0,
        tipoConvenio__PorcentajeDescuento__lte=100,
    ).first()


def pagar_reserva(request, reserva_id):
    reserva = get_object_or_404(
        Reservas,
        id=reserva_id,
        huespedes__usuarios_id=request.session.get('usuario_id'),
    )
    if reserva.estado in ['Cancelada', 'Finalizada']:
        messages.error(request, 'Esta reserva ya no admite pagos.')
        return redirect('/mis-reservas')

    pagos_realizados = Pagos.objects.filter(reservas=reserva).exclude(metodopago='Pendiente').aggregate(total=Sum('valor'))['total'] or Decimal('0.00')
    saldo_pendiente = max(Decimal('0.00'), reserva.valortotal - pagos_realizados)

    return render(request, 'clientes/pagar.html', {
        'reserva': reserva,
        'pagos_realizados': pagos_realizados,
        'saldo_pendiente': saldo_pendiente
    })

@requiere_login_cliente
def procesar_pago(request, reserva_id):
    if request.method != 'POST':
        return redirect(f'/pagar-reserva/{reserva_id}')

    tipo_pago = request.POST.get('tipo_pago', '100')
    metodo_seleccionado = request.POST.get('metodo_pago', '')
    metodos_pago = {
        'tarjeta_nueva': 'Tarjeta',
        'Tarjeta': 'Tarjeta',
        'Nequi': 'Transferencia',
        'Bancolombia': 'Transferencia',
        'PSE': 'Transferencia',
        'nequi': 'Transferencia',
        'Efectivo': 'Efectivo',
        'Transferencia': 'Transferencia',
    }
    if tipo_pago not in {'50', '100'} or metodo_seleccionado not in metodos_pago:
        messages.error(request, 'Selecciona un monto y un método de pago válidos.')
        return redirect(f'/pagar-reserva/{reserva_id}')

    with transaction.atomic():
        reserva = get_object_or_404(
            Reservas.objects.select_for_update(),
            id=reserva_id,
            huespedes__usuarios_id=request.session.get('usuario_id'),
        )
        if reserva.estado in ['Cancelada', 'Finalizada']:
            messages.error(request, 'Esta reserva ya no admite pagos.')
            return redirect('/mis-reservas')

        pagos_realizados = Pagos.objects.filter(
            reservas=reserva,
        ).exclude(metodopago='Pendiente').aggregate(total=Sum('valor'))['total'] or Decimal('0.00')
        saldo_pendiente = max(Decimal('0.00'), reserva.valortotal - pagos_realizados)
        if saldo_pendiente <= 0:
            messages.info(request, 'La reserva ya está pagada.')
            return redirect('/mis-reservas')

        if tipo_pago == '50' and pagos_realizados == 0:
            monto_a_pagar = (reserva.valortotal * Decimal('0.50')).quantize(Decimal('0.01'))
        else:
            monto_a_pagar = saldo_pendiente

        Pagos.objects.create(
            reservas=reserva,
            valor=monto_a_pagar,
            metodopago=metodos_pago[metodo_seleccionado],
            concepto='Reserva',
        )
        if reserva.estado == 'Pendiente':
            reserva.estado = 'Pagada - Por validar'
            reserva.save(update_fields=['estado'])

    correo_destino = _correo_huesped(reserva.huespedes)
    if correo_destino:
        try:
            _enviar_correo_hotel(
                f'Pago registrado - Reserva CC-{reserva.id:04d}',
                'Recibimos tu pago',
                (
                    f'Hola {reserva.huespedes.nombres},\n\n'
                    f'Registramos un pago de ${formato_numero_colombiano(monto_a_pagar, 2)} COP para tu reserva '
                    f'CC-{reserva.id:04d}. El saldo pendiente es '
                    f'${formato_numero_colombiano(max(Decimal("0.00"), saldo_pendiente - monto_a_pagar), 2)} COP.\n\n'
                    'El hotel verificará el pago antes de confirmarlo.'
                ),
                correo_destino,
            )
        except Exception:
            messages.warning(request, 'El pago se registró, pero no se pudo enviar el correo de confirmación.')

    messages.success(request, 'Pago registrado para verificación.')
    return redirect('/mis-reservas')

@requiere_login_cliente
def crear_reserva(request):
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Metodo no permitido'}, status=405)

    habitacion_ids_str = request.POST.get('habitacion_ids', '').strip()
    entrada = request.POST.get('entrada')
    salida = request.POST.get('salida')
    adultos_str = request.POST.get('adultos', '1')
    ninos_str = request.POST.get('ninos', '0') 

    if not habitacion_ids_str or not entrada or not salida:
        return JsonResponse({'ok': False, 'error': 'Faltan datos en el formulario.'}, status=400)

    lista_ids = [item.strip() for item in habitacion_ids_str.split(',')]
    if not lista_ids or any(not item.isdigit() for item in lista_ids):
        return JsonResponse({'ok': False, 'error': 'La selección de habitaciones no es válida.'}, status=400)
    if len(set(lista_ids)) != len(lista_ids):
        return JsonResponse({'ok': False, 'error': 'No puedes seleccionar la misma habitación más de una vez.'}, status=400)

    try:
        entrada_fecha = datetime.strptime(entrada, "%Y-%m-%d").date()
        salida_fecha = datetime.strptime(salida, "%Y-%m-%d").date()
    except ValueError:
        return JsonResponse({'ok': False, 'error': 'Formato de fecha inválido.'}, status=400)

    if salida_fecha <= entrada_fecha:
        return JsonResponse({'ok': False, 'error': 'La fecha de salida debe ser posterior a la de entrada.'}, status=400)
    if entrada_fecha < timezone.localdate():
        return JsonResponse({'ok': False, 'error': 'La fecha de entrada no puede estar en el pasado.'}, status=400)

    try: 
        adultos = int(adultos_str)
        ninos = int(ninos_str)
    except ValueError:
        return JsonResponse({'ok': False, 'error': 'La cantidad de huéspedes no es válida.'}, status=400)
    if adultos < 1 or ninos < 0:
        return JsonResponse({'ok': False, 'error': 'Indica al menos un adulto y una cantidad válida de niños.'}, status=400)

    total_personas = adultos + ninos

    usuario_id = request.session.get('usuario_id')
    try:
        huesped = Huespedes.objects.get(usuarios_id=usuario_id)
    except Huespedes.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'No encontramos su registro de huésped.'}, status=400)

    codigo_ingresado = request.POST.get('codigo_convenio', '').strip()
    desayunos_ids = request.POST.getlist('desayuno_ids')
    if any(not item.isdigit() or item not in lista_ids for item in desayunos_ids):
        return JsonResponse({'ok': False, 'error': 'La selección de desayunos no es válida.'}, status=400)
    noches = (salida_fecha - entrada_fecha).days
    try:
        with transaction.atomic():
            habitaciones = list(
                Habitaciones.objects.select_for_update(of=('self',))
                .select_related('tipohabitacion')
                .filter(id__in=[int(item) for item in lista_ids])
                .order_by('id')
            )
            if len(habitaciones) != len(lista_ids):
                return JsonResponse({'ok': False, 'error': 'Una o más habitaciones ya no están disponibles.'}, status=409)
            if any(habitacion.estado != 'Disponible' for habitacion in habitaciones):
                return JsonResponse({'ok': False, 'error': 'Una o más habitaciones ya no están disponibles.'}, status=409)
            if Reservas.objects.filter(
                habitaciones_id__in=[habitacion.id for habitacion in habitaciones],
                estado__in=['Pendiente', 'Pagada - Por validar', 'Confirmada', 'En curso'],
                fechaentrada__lt=salida_fecha,
                fechasalida__gt=entrada_fecha,
            ).exists():
                return JsonResponse({'ok': False, 'error': 'Una habitación seleccionada ya tiene una reserva en esas fechas.'}, status=409)
            for habitacion in habitaciones:
                if total_personas > habitacion.capacidad:
                    return JsonResponse({
                        'ok': False,
                        'error': f'La habitación {habitacion.numero} excede su capacidad máxima de {habitacion.capacidad} personas.',
                    }, status=400)

            convenio = _buscar_convenio_valido(codigo_ingresado, bloquear=True) if codigo_ingresado else None
            if codigo_ingresado and not convenio:
                return JsonResponse({'ok': False, 'error': 'El código de convenio no existe, venció o ya fue utilizado.'}, status=400)
            if convenio and Reservas.objects.filter(codigosConvenio=convenio).exists():
                return JsonResponse({'ok': False, 'error': 'El código de convenio ya fue aplicado.'}, status=409)

            regla_estancia = _regla_descuento_estancia(noches)
            porcentaje_estancia = regla_estancia.porcentaje if regla_estancia else Decimal('0')
            porcentaje_convenio = convenio.tipoConvenio.PorcentajeDescuento if convenio else Decimal('0')
            reservas_creadas = []
            total_general = Decimal('0.00')
            for indice, habitacion in enumerate(habitaciones):
                subtotal = (Decimal(noches) * habitacion.precio).quantize(Decimal('0.01'))
                if str(habitacion.id) in desayunos_ids and habitacion.tipohabitacion:
                    subtotal += (Decimal(noches) * habitacion.tipohabitacion.precio_desayuno).quantize(Decimal('0.01'))
                valor_total = (
                    subtotal
                    * (Decimal('100') - porcentaje_estancia) / Decimal('100')
                    * (Decimal('100') - porcentaje_convenio) / Decimal('100')
                ).quantize(Decimal('0.01'))
                reserva = Reservas.objects.create(
                    huespedes=huesped,
                    habitaciones=habitacion,
                    codigosConvenio=convenio if indice == 0 else None,
                    fechaentrada=entrada_fecha,
                    fechasalida=salida_fecha,
                    cantidadacompañantes=total_personas,
                    estado='Pendiente',
                    valortotal=valor_total,
                )
                reservas_creadas.append(reserva)
                total_general += valor_total

            valor_abono = (total_general * Decimal('0.50')).quantize(Decimal('0.01'))
            Pagos.objects.create(
                reservas=reservas_creadas[0],
                valor=valor_abono,
                metodopago='Pendiente',
                concepto='Reserva',
            )
            if convenio:
                convenio.estado = 'Usado'
                convenio.save(update_fields=['estado'])
    except IntegrityError:
        return JsonResponse({'ok': False, 'error': 'La reserva o el código cambió mientras se procesaba. Inténtalo nuevamente.'}, status=409)

    request.session['reservas_pendientes'] = [r.id for r in reservas_creadas]
    return JsonResponse({
        'ok': True,
        'reserva_id': reservas_creadas[0].id,
        'total': str(total_general),
        'abono': str(valor_abono),
        'descuento': str(porcentaje_estancia),
        'descuento_convenio': str(porcentaje_convenio),
    })

@requiere_login_cliente
def perfil_cliente(request):
    try:
        usuario = Usuarios.objects.get(id=request.session.get('usuario_id'))
        huesped = Huespedes.objects.get(usuarios=usuario)
    except (Usuarios.DoesNotExist, Huespedes.DoesNotExist):
        return redirect('/logout')

    reservas = Reservas.objects.filter(huespedes=huesped).order_by('-fechasolicitud')
    total_reservas = reservas.count()
    ultima_reserva = reservas.first()
    fecha_ultima = ultima_reserva.fechasolicitud.strftime('%d/%m/%Y') if ultima_reserva else "Ninguna"

    if request.method == 'POST':
        accion = request.POST.get('accion')

        if accion == 'datos':
            usuario.nombre = request.POST.get('nombres', usuario.nombre).strip()
            usuario.apellido = request.POST.get('apellidos', usuario.apellido).strip()
            usuario.correo = request.POST.get('correo', usuario.correo).strip()
            huesped.telefono = request.POST.get('telefono', huesped.telefono).strip()
            huesped.direccion = request.POST.get('direccion', huesped.direccion).strip()
            
            usuario.save()
            huesped.save()
            
            messages.success(request, 'Tus datos han sido actualizados correctamente.')
            return redirect('/perfil')
            
        elif accion == 'password':
            actual = request.POST.get('password_actual')
            nueva = request.POST.get('password_nueva')
            confirmar = request.POST.get('password_confirmar')

            if not check_password(actual, usuario.contrasena):
                messages.error(request, 'La contraseña actual es incorrecta.')
            elif len(nueva) < 6:
                messages.error(request, 'La nueva contraseña debe tener al menos 6 caracteres.')
            elif nueva != confirmar:
                messages.error(request, 'Las contraseñas nuevas no coinciden.')
            else:
                usuario.contrasena = make_password(nueva)
                usuario.save()
                
                try:
                    asunto = "Seguridad: Tu contraseña ha sido cambiada - Caribe Confort"
                    mensaje = f"¡Hola {usuario.nombre}!\n\nTe informamos que la contraseña de tu cuenta en Caribe Confort ha sido cambiada exitosamente.\n\nSi realizaste este cambio, puedes ignorar este mensaje.\n\nSi NO reconoces esta actividad, por favor contacta inmediatamente a nuestro equipo de soporte.\n\n¡Gracias por elegirnos!\n— El equipo de Caribe Confort"
                    _enviar_correo_hotel(
                        asunto,
                        'Tu contraseña fue actualizada',
                        mensaje,
                        usuario.correo,
                    )
                except Exception as e:
                    print(f"Error al enviar correo de cambio de contraseña: {e}")

                messages.success(request, 'Tu contraseña ha sido cambiada exitosamente. Te hemos enviado un correo de confirmación.')
                return redirect('/perfil')

    return render(request, 'clientes/perfil.html', {
        'usuario': usuario,
        'huesped': huesped,
        'reservas': reservas,
        'total_reservas': total_reservas,
        'fecha_ultima': fecha_ultima,
    })


def recuperar_password(request):
    if request.session.get('usuario_id'):
        return redirect('/home')

    if request.method == 'POST':
        correo = request.POST.get('correo', '').strip().lower()
        usuario = Usuarios.objects.filter(correo=correo, estado=True).first()

        if usuario:
            codigo = str(random.randint(100000, 999999))
            request.session['reset_usuario_id'] = usuario.id
            request.session['reset_codigo'] = codigo
            request.session['reset_verificado'] = False

            try:
                _enviar_correo_hotel(
                    'Recuperación de contraseña — Caribe Confort',
                    'Recupera el acceso a tu cuenta',
                    (
                        f'¡Hola {usuario.nombre}!\n\n'
                        f'Recibimos una solicitud para restablecer tu contraseña.\n\n'
                        f'Tu código de verificación es: {codigo}\n\n'
                        f'Si no solicitaste este cambio, ignora este mensaje.\n\n'
                        f'— Caribe Confort Hotel'
                    ),
                    correo,
                )
                messages.success(request, 'Te hemos enviado un código a tu correo electrónico.')
                return redirect('/cambiar-password')
            except Exception as e:
                return render(request, 'clientes/recuperar.html', {'error': f'No se pudo enviar el correo: {e}', 'correo': correo})
        
        return render(request, 'clientes/recuperar.html', {'error': 'No existe una cuenta con este correo.', 'correo': correo})

    return render(request, 'clientes/recuperar.html')


def cambiar_password_reset(request):
    usuario_id = request.session.get('reset_usuario_id')
    codigo_sesion = request.session.get('reset_codigo')
    verificado = request.session.get('reset_verificado', False)

    if not usuario_id or not codigo_sesion:
        return redirect('/recuperar-password')

    if request.method == 'POST':
        accion = request.POST.get('accion')

        if accion == 'verificar':
            codigo_ingresado = request.POST.get('codigo', '').strip()
            if codigo_ingresado != codigo_sesion:
                return render(request, 'clientes/cambiar_contraseña.html', {'error': 'El código ingresado es incorrecto.', 'mostrar_passwords': False})
            
            request.session['reset_verificado'] = True
            return render(request, 'clientes/cambiar_contraseña.html', {'mostrar_passwords': True})

        elif accion == 'actualizar':
            if not verificado:
                return redirect('/cambiar-password')

            nueva = request.POST.get('password_nueva', '')
            confirmar = request.POST.get('password_confirmar', '')

            if len(nueva) < 6:
                return render(request, 'clientes/cambiar_contraseña.html', {'error': 'La nueva contraseña debe tener al menos 6 caracteres.', 'mostrar_passwords': True})
                
            if nueva != confirmar:
                return render(request, 'clientes/cambiar_contraseña.html', {'error': 'Las contraseñas no coinciden.', 'mostrar_passwords': True})

            try:
                usuario = Usuarios.objects.get(id=usuario_id)
                usuario.contrasena = make_password(nueva)
                usuario.save()

                del request.session['reset_usuario_id']
                del request.session['reset_codigo']
                del request.session['reset_verificado']

                messages.success(request, 'Tu contraseña ha sido restablecida con éxito. Ya puedes iniciar sesión.')
                return redirect('/login')
            except Usuarios.DoesNotExist:
                return redirect('/login')

    return render(request, 'clientes/cambiar_contraseña.html', {'mostrar_passwords': verificado})


def finalizar_reservas_vencidas(request, enviar_invitaciones=True):
    """Una reserva confirmada cuya fecha de salida ya pasó queda como Finalizada."""
    hoy = timezone.localdate()
    Reservas.objects.filter(estado='Confirmada', fechasalida__lt=hoy).update(estado='Finalizada')
    if not enviar_invitaciones:
        return

    reservas_pendientes = Reservas.objects.filter(
        estado='Finalizada',
        fechasalida__lt=hoy,
    ).filter(
        Q(resena__isnull=True) | Q(resena__correo_enviado=False)
    ).select_related('huespedes')

    for reserva in reservas_pendientes:
        _enviar_invitacion_resena(reserva, request)


def dejar_resena(request, token):
    resena = get_object_or_404(
        Resena.objects.select_related('reserva__huespedes', 'reserva__habitaciones'),
        token=token,
    )
    error = None

    if request.method == 'POST' and resena.calificacion is None:
        calificacion = request.POST.get('calificacion', '').strip()
        calificacion_habitacion = request.POST.get(
            'calificacion_habitacion',
            '',
        ).strip()
        comentario = request.POST.get('comentario', '').strip()
        try:
            calificacion = int(calificacion)
        except ValueError:
            calificacion = 0

        if (
            calificacion_habitacion
            and resena.reserva.habitaciones_id
        ):
            try:
                calificacion_habitacion = int(calificacion_habitacion)
            except ValueError:
                calificacion_habitacion = 0
        else:
            calificacion_habitacion = None

        if not 1 <= calificacion <= 5:
            error = _('Selecciona una calificación de 1 a 5 estrellas.')
        elif (
            calificacion_habitacion is not None
            and not 1 <= calificacion_habitacion <= 5
        ):
            error = _('La calificación de la habitación debe estar entre 1 y 5 estrellas.')
        elif not comentario:
            error = _('Escribe un comentario sobre tu estancia.')
        elif len(comentario) > 2000:
            error = _('El comentario no puede superar los 2000 caracteres.')
        else:
            resena.calificacion = calificacion
            resena.calificacion_habitacion = calificacion_habitacion
            resena.comentario = comentario
            resena.fecha = timezone.now()
            resena.save(update_fields=[
                'calificacion',
                'calificacion_habitacion',
                'comentario',
                'fecha',
            ])

    return render(
        request,
        'clientes/dejar_resena.html',
        {
            'resena': resena,
            'error': error,
            'enviada': resena.calificacion is not None,
        },
    )


@requiere_login_cliente
def mis_reservas(request):
    finalizar_reservas_vencidas(request)
    try:
        huesped = Huespedes.objects.get(usuarios_id=request.session.get('usuario_id'))
    except Huespedes.DoesNotExist:
        return redirect('/home')

    reservas = Reservas.objects.filter(huespedes=huesped).select_related(
        'habitaciones__tipohabitacion', 'planes', 'huespedes'
    ).prefetch_related(
        'servicioreserva_set__servicios',
        'planes__Servicios_tipos'
    ).order_by('-fechasolicitud')
    pagos_por_reserva = {
        pago['reservas_id']: pago['total'] or Decimal('0.00')
        for pago in Pagos.objects.filter(
            reservas__huespedes=huesped,
        ).exclude(
            metodopago='Pendiente',
        ).values('reservas_id').annotate(total=Sum('valor'))
    }

    hoy = timezone.localdate()
    activas = []
    historial = []

    for r in reservas:
        r.abono_pagado = pagos_por_reserva.get(r.id, Decimal('0.00'))
        r.saldo_pendiente = max(Decimal('0.00'), r.valortotal - r.abono_pagado)
        r.esta_pagada = r.saldo_pendiente == Decimal('0.00')
        
        r.noches = (r.fechasalida - r.fechaentrada).days
        
        if r.valortotal > 0:
            r.porcentaje_pagado = int((r.abono_pagado / r.valortotal) * 100)
        else:
            r.porcentaje_pagado = 0
        r.formatted_id = f"CC-{r.id:04d}"

        if r.estado in ['Pendiente', 'Pagada - Por validar', 'Confirmada', 'En curso'] and r.fechasalida >= hoy:
            activas.append(r)
        else:
            historial.append(r)

    historial_servicios = ServicioReserva.objects.filter(
        reservas__huespedes=huesped
    ).select_related('servicios', 'reservas').order_by('-id')
    for servicio_reserva in historial_servicios:
        servicio_reserva.servicios.url_imagen = _url_imagen_local(
            servicio_reserva.servicios.imagen
        )

    return render(request, 'clientes/mis_reservas.html', {
        'activas': activas,
        'historial': historial,
        'historial_servicios': historial_servicios
    })

def validar_reserva(request, reserva_id):
    if request.method == 'POST':
        if request.session.get('rol') not in ['Administrador', 'Recepcionista']:
            return JsonResponse({'success': False, 'message': 'No autorizado'}, status=403)
            
        try:
            reserva = Reservas.objects.get(id=reserva_id)
            
            if reserva.estado != 'Pagada - Por validar':
                return JsonResponse({'success': False, 'message': 'Esta reserva no está pendiente de validación.'})

            reserva.estado = 'Confirmada'
            reserva.save()

            asunto = "¡Tu reserva ha sido confirmada! - Caribe Confort"
            mensaje = f"Hola {reserva.huespedes.nombres}, tu pago ha sido validado y tu reserva #{reserva.id} está confirmada."
            correo_destino = _correo_huesped(reserva.huespedes)
            if not correo_destino:
                return JsonResponse({'success': True, 'correo_enviado': False, 'message': 'Reserva confirmada, pero el huésped no tiene un correo válido registrado.'})
            try:
                _enviar_correo_hotel(
                    asunto,
                    'Tu reserva está confirmada',
                    mensaje,
                    correo_destino,
                )
            except Exception:
                logger.exception('La reserva CC-%s se confirmó, pero falló el correo.', reserva.id)
                return JsonResponse({'success': True, 'correo_enviado': False, 'message': 'Reserva confirmada, pero no se pudo enviar el correo. Verifica la configuración SMTP.'})

            return JsonResponse({'success': True, 'correo_enviado': True, 'message': 'Reserva validada y confirmada; correo enviado correctamente.'})
            
        except Reservas.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Reserva no encontrada'}, status=404)
        except Exception:
            logger.exception('No se pudo validar la reserva CC-%s.', reserva_id)
            return JsonResponse({'success': False, 'message': 'No se pudo validar la reserva.'}, status=500)
            
    return JsonResponse({'success': False, 'message': 'Método no permitido'}, status=405)

@requiere_login_cliente
def crear_reserva_plan(request):
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Método no permitido'}, status=405)

    plan_id = request.POST.get('plan_id')
    entrada_str = request.POST.get('entrada')
    salida_str = request.POST.get('salida')
    adultos_str = request.POST.get('adultos', '1')
    ninos_str = request.POST.get('ninos', '0')
    codigo_ingresado = request.POST.get('codigo_convenio', '').strip()

    if not plan_id or not entrada_str or not salida_str:
        return JsonResponse({'ok': False, 'error': 'Faltan datos obligatorios.'}, status=400)

    try:
        entrada_fecha = datetime.strptime(entrada_str, "%Y-%m-%d").date()
        salida_fecha = datetime.strptime(salida_str, "%Y-%m-%d").date()
    except ValueError:
        return JsonResponse({'ok': False, 'error': 'Formato de fecha inválido.'}, status=400)

    if salida_fecha <= entrada_fecha:
        return JsonResponse({'ok': False, 'error': 'La fecha de salida debe ser posterior a la de entrada.'}, status=400)
    if entrada_fecha < timezone.localdate():
        return JsonResponse({'ok': False, 'error': 'La fecha de entrada no puede estar en el pasado.'}, status=400)

    try:
        plan = Planes.objects.get(id=plan_id, estado=True)
    except Planes.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'El plan no existe o no está disponible.'}, status=404)

    try: 
        adultos = int(adultos_str)
        ninos = int(ninos_str)
    except ValueError:
        return JsonResponse({'ok': False, 'error': 'La cantidad de huéspedes no es válida.'}, status=400)

    if adultos < 1 or ninos < 0:
        return JsonResponse({'ok': False, 'error': 'Indica al menos un adulto y una cantidad válida de niños.'}, status=400)
    if adultos > plan.max_adultos:
        return JsonResponse({'ok': False, 'error': f'Este plan permite máximo {plan.max_adultos} adultos.'}, status=400)
    
    if ninos > plan.max_ninos:
         return JsonResponse({'ok': False, 'error': f'Este plan permite máximo {plan.max_ninos} niños.'}, status=400)

    usuario_id = request.session.get('usuario_id')
    try:
        huesped = Huespedes.objects.get(usuarios_id=usuario_id)
    except Huespedes.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'No encontramos tu registro de huésped.'}, status=400)
    
    try:
        with transaction.atomic():
            plan = Planes.objects.select_for_update().get(id=plan.id, estado=True)
            if plan.disponibles <= 0:
                return JsonResponse({'ok': False, 'error': 'Este plan ya no tiene disponibilidad.'}, status=409)
            convenio = _buscar_convenio_valido(codigo_ingresado, bloquear=True) if codigo_ingresado else None
            if codigo_ingresado and not convenio:
                return JsonResponse({'ok': False, 'error': 'El código de convenio no existe, venció o ya fue utilizado.'}, status=400)
            if convenio and Reservas.objects.filter(codigosConvenio=convenio).exists():
                return JsonResponse({'ok': False, 'error': 'El código de convenio ya fue aplicado.'}, status=409)

            porcentaje = convenio.tipoConvenio.PorcentajeDescuento if convenio else Decimal('0')
            valor_total = (plan.precio * (Decimal('100') - porcentaje) / Decimal('100')).quantize(Decimal('0.01'))
            reserva = Reservas.objects.create(
                huespedes=huesped,
                planes=plan,
                codigosConvenio=convenio,
                habitaciones=None,
                fechaentrada=entrada_fecha,
                fechasalida=salida_fecha,
                cantidadacompañantes=adultos + ninos,
                estado='Pendiente',
                valortotal=valor_total,
            )
            valor_abono = (valor_total * Decimal('0.50')).quantize(Decimal('0.01'))
            Pagos.objects.create(
                reservas=reserva,
                valor=valor_abono,
                metodopago='Pendiente',
                concepto='Reserva',
            )
            plan.disponibles -= 1
            plan.save(update_fields=['disponibles'])
            if convenio:
                convenio.estado = 'Usado'
                convenio.save(update_fields=['estado'])
    except IntegrityError:
        return JsonResponse({'ok': False, 'error': 'El plan o el código cambió mientras se procesaba. Inténtalo nuevamente.'}, status=409)

    return JsonResponse({
        'ok': True,
        'reserva_id': reserva.id,
        'total': str(valor_total),
        'descuento': str(porcentaje),
    })


def reservasadmin(request):
    if request.session.get('rol') not in {'Administrador', 'Recepcionista'}:
        return redirect('/login')

    finalizar_reservas_vencidas(request)
    hoy = timezone.localdate()

    huespedes = Huespedes.objects.all()
    habitaciones = Habitaciones.objects.all()

    reserva = Reservas.objects.select_related(
        'huespedes', 'habitaciones', 'planes'
    ).order_by('-fechasolicitud')

    q = request.GET.get('q', '').strip()
    estado_filtro = request.GET.get('estado', '').strip()
    habitacion_filtro = request.GET.get('habitacion', '').strip()
    entrada_desde = request.GET.get('desde', '').strip()
    entrada_hasta = request.GET.get('hasta', '').strip()
    estados_validos = {valor for valor, _ in Reservas.estados}

    if q:
        filtros_busqueda = (
            Q(huespedes__nombres__icontains=q)
            | Q(huespedes__apellidos__icontains=q)
            | Q(huespedes__identificacion__icontains=q)
        )
        numero_reserva = (
            q[3:] if q.upper().startswith('CC-') else q
        )
        if numero_reserva.isdigit():
            filtros_busqueda |= Q(id=int(numero_reserva))
        reserva = reserva.filter(filtros_busqueda)
    if estado_filtro in estados_validos:
        reserva = reserva.filter(estado=estado_filtro)
    elif estado_filtro:
        messages.error(request, 'El estado de reserva seleccionado no es válido.')
        estado_filtro = ''
    if habitacion_filtro:
        if habitacion_filtro.isdigit() and Habitaciones.objects.filter(id=int(habitacion_filtro)).exists():
            reserva = reserva.filter(habitaciones_id=int(habitacion_filtro))
        else:
            messages.error(request, 'La habitación seleccionada no es válida.')
            habitacion_filtro = ''
    try:
        fecha_desde = date.fromisoformat(entrada_desde) if entrada_desde else None
        fecha_hasta = date.fromisoformat(entrada_hasta) if entrada_hasta else None
    except ValueError:
        messages.error(request, 'El rango de fechas del filtro no es válido.')
        entrada_desde = entrada_hasta = ''
        fecha_desde = fecha_hasta = None
    if fecha_desde and fecha_hasta and fecha_hasta < fecha_desde:
        messages.error(request, 'La fecha final del filtro debe ser posterior o igual a la inicial.')
        entrada_desde = entrada_hasta = ''
        fecha_desde = fecha_hasta = None
    if fecha_desde:
        reserva = reserva.filter(fechaentrada__gte=fecha_desde)
    if fecha_hasta:
        reserva = reserva.filter(fechaentrada__lte=fecha_hasta)

    # Los indicadores describen el inventario completo; los filtros afectan solo al listado.
    total_reservas = Reservas.objects.count()
    reservas_contadas = reserva.count()
    reservas_totales = Reservas.objects.all()
    total_confirmadas = reservas_totales.filter(estado='Confirmada').count()
    total_proceso = reservas_totales.filter(
        estado__in=['Pendiente', 'Pagada - Por validar']
    ).count()
    total_canceladas = reservas_totales.filter(estado='Cancelada').count()
    total_finalizadas = reservas_totales.filter(estado='Finalizada').count()
    total_en_curso = reservas_totales.filter(estado='En curso').count()
    porcentaje_confirmadas = round(total_confirmadas * 100 / total_reservas) if total_reservas else 0
    porcentaje_proceso = round(total_proceso * 100 / total_reservas) if total_reservas else 0
    porcentaje_canceladas = round(total_canceladas * 100 / total_reservas) if total_reservas else 0
    porcentaje_en_curso = round(total_en_curso * 100 / total_reservas) if total_reservas else 0

    reservas_por_validar = Reservas.objects.filter(
        estado='Pagada - Por validar'
    ).select_related('huespedes', 'habitaciones', 'planes').order_by('-fechasolicitud')

    notificaciones_pendientes = reservas_por_validar.count()
    notificaciones_servicios = ServicioReserva.objects.filter(
        estado='Pendiente',
        pago__metodopago='Pendiente',
    ).count()

    proximas_reservas = Reservas.objects.filter(
        fechaentrada__gte=hoy,
        estado__in=['Pendiente', 'Pagada - Por validar', 'Confirmada']
    ).select_related('huespedes', 'habitaciones', 'planes').order_by('fechaentrada')

    paginator = Paginator(reserva, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    parametros_paginacion = request.GET.copy()
    parametros_paginacion.pop('page', None)

    for r in page_obj:
        r.formatted_id = f'CC-{r.id:04d}'
        pagado = Pagos.objects.filter(reservas=r).exclude(
            metodopago='Pendiente'
        ).aggregate(total=Sum('valor'))['total'] or Decimal('0.00')
        r.saldo_pendiente = max(Decimal('0.00'), r.valortotal - pagado)
        r.saldo_favor = max(Decimal('0.00'), pagado - r.valortotal)

    return render(request, 'admini/reservas.html', {
        'nombre': request.session.get('usuario_nom', 'Administrador'),
        'rol': request.session.get('rol', 'Administrador'),
        'huespedes': huespedes,
        'habitaciones': habitaciones,
        'reserva': reserva,
        'reservas_contadas': reservas_contadas,
        'page_obj': page_obj,
        'proximas_reservas': proximas_reservas,
        'proximas_reservas_preview': proximas_reservas[:5],
        'total_reservas': total_reservas,
        'total_confirmadas': total_confirmadas,
        'total_proceso': total_proceso,
        'total_canceladas': total_canceladas,
        'total_finalizadas': total_finalizadas,
        'total_en_curso': total_en_curso,
        'porcentaje_confirmadas': porcentaje_confirmadas,
        'porcentaje_proceso': porcentaje_proceso,
        'porcentaje_canceladas': porcentaje_canceladas,
        'porcentaje_en_curso': porcentaje_en_curso,
        'reservas_por_validar': reservas_por_validar,
        'notificaciones_pendientes': notificaciones_pendientes,
        'notificaciones_servicios': notificaciones_servicios,
        'nacionalidades': NACIONALIDADES,
        'habitaciones_disponibles': Habitaciones.objects.filter(
            estado='Disponible'
        ).order_by('numero'),
        'hoy': hoy,
        'manana': hoy + timedelta(days=1),
        'habitaciones': Habitaciones.objects.order_by('numero'),
        'tipos_habitacion': TipoHabitacion.objects.order_by('nombre'),
        'estados_reserva': Reservas.estados,
        'parametros_paginacion': parametros_paginacion.urlencode(),
        'filtros': {
            'q': q,
            'estado': estado_filtro,
            'habitacion': habitacion_filtro,
            'desde': entrada_desde,
            'hasta': entrada_hasta,
        },
    })


def _enviar_confirmacion_reserva(reserva):
    huesped = reserva.huespedes
    correo_destino = _correo_huesped(huesped)
    if not correo_destino:
        return ' El huésped no tiene correo registrado; no se envió confirmación por correo.'

    alojamiento = (
        f'Habitación: {reserva.habitaciones.numero}'
        if reserva.habitaciones_id
        else f'Plan: {reserva.planes.nombre}'
    )
    try:
        enviados = _enviar_correo_hotel(
            f'Confirmación de reserva CC-{reserva.id:04d}',
            'Tu reserva fue registrada',
            (
                f'Hola {huesped.nombres} {huesped.apellidos},\n\n'
                f'Tu reserva en Caribe Confort quedó registrada en recepción.\n'
                f'{alojamiento}\n'
                f'Check-in: {reserva.fechaentrada:%d/%m/%Y}\n'
                f'Check-out: {reserva.fechasalida:%d/%m/%Y}\n'
                f'Total de la estadía: ${formato_numero_colombiano(reserva.valortotal, 2)}\n'
            ),
            correo_destino,
        )
    except (OSError, SMTPException, RuntimeError):
        logger.exception('No se pudo enviar la confirmación de reserva CC-%s.', reserva.id)
        return ' La reserva quedó registrada, pero el correo de confirmación no se pudo enviar.'

    if enviados:
        return ' Se envió el correo de confirmación al huésped.'
    return ' La reserva quedó registrada, pero el correo no pudo ser aceptado por el servidor.'


def crear_reserva_admin(request):
    if request.session.get('rol') not in {'Administrador', 'Recepcionista'}:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'error': 'No tienes permiso para registrar reservas.'}, status=403)
        return redirect('/login')
    destino = '/recepcion' if request.session.get('rol') == 'Recepcionista' else '/adminreserva'
    if request.method != 'POST':
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'error': 'Método no permitido.'}, status=405)
        return redirect(destino)

    es_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    def responder(mensaje, exito=False, status=400, reserva=None):
        if es_ajax:
            data = {'ok': exito, 'message': mensaje}
            if not exito:
                data['error'] = mensaje
            if reserva:
                data['reserva_id'] = reserva.id
                data['habitacion'] = reserva.habitaciones.numero
            return JsonResponse(data, status=status)
        (messages.success if exito else messages.error)(request, mensaje)
        return redirect(destino)

    hoy = timezone.localdate()
    try:
        fecha_entrada = date.fromisoformat(request.POST.get('fechaentrada', ''))
        fecha_salida = date.fromisoformat(request.POST.get('fechasalida', ''))
        tipo_habitacion_id = int(request.POST.get('tipo_habitacion', ''))
        habitacion_id = int(request.POST.get('habitacion', ''))
        cantidad_huespedes = int(request.POST.get('cantidadacompanantes', ''))
        monto_pagado = Decimal(request.POST.get('monto_pagado', '0').strip() or '0')
    except (TypeError, ValueError):
        return responder('Completa fechas, tipo y habitación, cantidad de huéspedes y pago con valores válidos.')
    except (InvalidOperation, AttributeError):
        return responder('Ingresa un monto pagado válido.')

    if fecha_entrada != hoy or fecha_salida <= fecha_entrada:
        return responder('El check-in presencial debe ser hoy y la salida debe ser posterior.')
    if cantidad_huespedes < 1:
        return responder('La reserva debe incluir al menos un huésped.')
    if not monto_pagado.is_finite():
        return responder('Ingresa un monto pagado válido.')
    try:
        monto_pagado = monto_pagado.quantize(Decimal('0.01'))
    except InvalidOperation:
        return responder('Ingresa un monto pagado válido.')
    if monto_pagado < 0:
        return responder('El monto pagado no puede ser negativo.')
    metodo_pago = request.POST.get('metodopago', '').strip()
    if monto_pagado > 0 and metodo_pago not in {'Efectivo', 'Tarjeta', 'Transferencia'}:
        return responder('Selecciona un método de pago válido para el monto recibido.')

    nacionalidad_enviada = request.POST.get('nacionalidad', '').strip()
    nacionalidad = next(
        (
            gentilicio
            for gentilicio, pais in NACIONALIDADES.items()
            if nacionalidad_enviada.casefold() in {gentilicio.casefold(), pais.casefold()}
        ),
        '',
    )
    if not nacionalidad:
        return responder('Selecciona una nacionalidad de las opciones disponibles.')

    datos_huesped = {
        'tipodocumento': request.POST.get('tipodocumento', '').strip(),
        'identificacion': request.POST.get('identificacion', '').strip(),
        'nombres': request.POST.get('nombres', '').strip(),
        'apellidos': request.POST.get('apellidos', '').strip(),
        'telefono': request.POST.get('telefono', '').strip(),
        'direccion': request.POST.get('direccion', '').strip(),
        'correo': request.POST.get('correo', '').strip() or None,
        'nacionalidad': nacionalidad,
    }
    if not all(datos_huesped[key] for key in (
        'tipodocumento', 'identificacion', 'nombres', 'apellidos',
        'telefono', 'direccion', 'nacionalidad',
    )):
        return responder('Completa todos los datos obligatorios del huésped.')
    limites_huesped = {
        'identificacion': 50,
        'nombres': 100,
        'apellidos': 100,
        'telefono': 100,
        'direccion': 100,
        'correo': 100,
        'nacionalidad': 100,
    }
    if datos_huesped['tipodocumento'] not in {'CC', 'CE', 'Pasaporte', 'TI'} or any(
        len(datos_huesped[campo]) > limite
        for campo, limite in limites_huesped.items()
        if datos_huesped[campo] is not None
    ):
        return responder('Revisa el tipo y la longitud de los datos del huésped.')
    if datos_huesped['correo']:
        try:
            validate_email(datos_huesped['correo'])
        except ValidationError:
            return responder('Ingresa un correo electrónico válido.')

    nombres_acompanantes = [nombre.strip() for nombre in request.POST.getlist('acompanante_nombre[]')]
    documentos_acompanantes = [documento.strip() for documento in request.POST.getlist('acompanante_documento[]')]
    parentescos_acompanantes = [parentesco.strip() for parentesco in request.POST.getlist('acompanante_parentesco[]')]
    acompanantes_esperados = cantidad_huespedes - 1
    if len(nombres_acompanantes) != acompanantes_esperados or len(documentos_acompanantes) != acompanantes_esperados:
        return responder('Registra el nombre y documento de cada acompañante.')
    if parentescos_acompanantes and len(parentescos_acompanantes) != acompanantes_esperados:
        return responder('Revisa el parentesco de cada acompañante.')
    if any(
        not nombre or len(nombre) > 200 or not documento or len(documento) > 50
        for nombre, documento in zip(nombres_acompanantes, documentos_acompanantes)
    ):
        return responder('Revisa los nombres y documentos de los acompañantes.')
    if any(len(parentesco) > 50 for parentesco in parentescos_acompanantes):
        return responder('El parentesco de cada acompañante no puede superar 50 caracteres.')

    try:
        with transaction.atomic():
            habitacion = Habitaciones.objects.select_for_update().filter(
                id=habitacion_id,
                tipohabitacion_id=tipo_habitacion_id,
            ).first()
            if not habitacion:
                return responder('La habitación seleccionada no existe.')
            if habitacion.estado != 'Disponible':
                return responder('La habitación seleccionada ya no está disponible.')
            if cantidad_huespedes > habitacion.capacidad:
                return responder(
                    f'La habitación {habitacion.numero} tiene capacidad máxima para {habitacion.capacidad} huéspedes.',
                )
            if Reservas.objects.filter(
                habitaciones=habitacion,
                estado__in=['Pendiente', 'Pagada - Por validar', 'Confirmada', 'En curso'],
                fechaentrada__lt=fecha_salida,
                fechasalida__gt=fecha_entrada,
            ).exists():
                return responder('La habitación ya tiene una reserva para esas fechas.')

            noches = (fecha_salida - fecha_entrada).days
            valor_total = (habitacion.precio * noches).quantize(Decimal('0.01'))
            regla_estancia = _regla_descuento_estancia(noches)
            if regla_estancia:
                valor_total = (
                    valor_total * (Decimal('100') - regla_estancia.porcentaje) / Decimal('100')
                ).quantize(Decimal('0.01'))
            if monto_pagado > valor_total:
                return responder('El monto pagado no puede superar el valor total de la estadía.')

            huesped, creado = Huespedes.objects.get_or_create(
                identificacion=datos_huesped['identificacion'],
                defaults=datos_huesped,
            )
            if not creado and (
                huesped.tipodocumento != datos_huesped['tipodocumento']
                or huesped.nombres.casefold() != datos_huesped['nombres'].casefold()
                or huesped.apellidos.casefold() != datos_huesped['apellidos'].casefold()
            ):
                return responder(
                    'El documento ya está asociado a otro huésped. Verifica los datos antes de crear la reserva.',
                    status=409,
                )
            reserva = Reservas.objects.create(
                huespedes=huesped,
                habitaciones=habitacion,
                fechaentrada=fecha_entrada,
                fechasalida=fecha_salida,
                cantidadacompañantes=cantidad_huespedes,
                estado='En curso',
                valortotal=valor_total,
            )
            Acompanante.objects.bulk_create([
                Acompanante(
                    reserva=reserva,
                    nombre_completo=nombre,
                    documento=documento,
                    parentesco=parentescos_acompanantes[indice] if indice < len(parentescos_acompanantes) else '',
                )
                for indice, (nombre, documento) in enumerate(zip(nombres_acompanantes, documentos_acompanantes))
            ])
            if monto_pagado > 0:
                Pagos.objects.create(
                    reservas=reserva,
                    valor=monto_pagado,
                    metodopago=metodo_pago,
                    concepto='Reserva',
                )
            habitacion.estado = 'Ocupada'
            habitacion.save(update_fields=['estado'])
    except IntegrityError:
        return responder('No se pudo registrar la reserva porque los datos cambiaron. Verifica e inténtalo nuevamente.', status=409)

    mensaje = (
        f'¡Reserva y Check-in exitosos! Reserva CC-{reserva.id:04d} registrada para '
        f'{huesped.nombres} {huesped.apellidos}.'
        + _enviar_confirmacion_reserva(reserva)
    )
    return responder(
        mensaje,
        exito=True,
        status=201,
        reserva=reserva,
    )


def checkin_reserva(request, reserva_id):
    if request.session.get('rol') not in ['Administrador', 'Recepcionista']:
        return redirect('/login')

    destino = '/recepcion' if request.session.get('rol') == 'Recepcionista' else '/adminreserva'
    if request.method not in ['GET', 'POST']:
        return redirect(destino)

    if request.method == 'POST' and request.POST.get('documentacion_verificada') != 'on':
        messages.error(request, 'Confirma que verificaste la identidad y los documentos antes del check-in.')
        return redirect(f'/adminreserva/checkin/{reserva_id}')

    try:
        with transaction.atomic():
            reserva = get_object_or_404(
                Reservas.objects.select_for_update(),
                id=reserva_id,
            )
            if reserva.estado != 'Confirmada':
                messages.error(request, 'Solo se puede hacer check-in de una reserva confirmada.')
                return redirect(destino)

            if request.method == 'POST':
                huesped = reserva.huespedes
                huesped.nombres = request.POST.get('nombres', huesped.nombres).strip()
                huesped.apellidos = request.POST.get('apellidos', huesped.apellidos).strip()
                huesped.telefono = request.POST.get('telefono', huesped.telefono).strip()
                huesped.tipodocumento = request.POST.get('tipodocumento', huesped.tipodocumento)
                huesped.identificacion = request.POST.get('identificacion', huesped.identificacion).strip()
                huesped.direccion = request.POST.get('direccion', huesped.direccion or '').strip()
                if not all([huesped.nombres, huesped.apellidos, huesped.telefono, huesped.identificacion]):
                    messages.error(request, 'Completa los datos obligatorios del titular.')
                    return render(request, 'admini/checkin.html', {'reserva': reserva})
                huesped.save()

                nombres_acompanantes = request.POST.getlist('acompanante_nombre[]')
                documentos_acompanantes = request.POST.getlist('acompanante_documento[]')
                parentescos_acompanantes = request.POST.getlist('acompanante_parentesco[]')
                Acompanante.objects.filter(reserva=reserva).delete()
                for indice, nombre in enumerate(nombres_acompanantes):
                    nombre = nombre.strip()
                    if nombre:
                        Acompanante.objects.create(
                            reserva=reserva,
                            nombre_completo=nombre,
                            documento=documentos_acompanantes[indice].strip() if indice < len(documentos_acompanantes) else '',
                            parentesco=parentescos_acompanantes[indice].strip() if indice < len(parentescos_acompanantes) else '',
                        )

                reserva.estado = 'En curso'
                reserva.save(update_fields=['estado'])
                if reserva.habitaciones:
                    reserva.habitaciones.estado = 'Ocupada'
                    reserva.habitaciones.save(update_fields=['estado'])

        if request.method == 'POST':
            correo_destino = _correo_huesped(reserva.huespedes)
            correo_enviado = False
            if correo_destino:
                try:
                    correo_enviado = bool(_enviar_correo_hotel(
                        f'Check-in confirmado - Reserva CC-{reserva.id:04d}',
                        'Tu check-in quedó confirmado',
                        (
                            f'Hola {reserva.huespedes.nombres} {reserva.huespedes.apellidos},\n\n'
                            f'Confirmamos tu ingreso al hotel para la reserva CC-{reserva.id:04d}. '
                            f'Tu estadía finaliza el {reserva.fechasalida:%d/%m/%Y}. '
                            'Si necesitas ayuda durante tu estadía, comunícate con recepción.'
                        ),
                        correo_destino,
                    ))
                except Exception:
                    logger.exception('El check-in de la reserva CC-%s se registró, pero falló el correo.', reserva.id)
            messages.success(request, f'Check-in confirmado para {reserva.huespedes.nombres} {reserva.huespedes.apellidos}.')
            if not correo_enviado:
                messages.warning(request, 'El check-in se registró, pero no se pudo enviar el correo. Verifica el email del huésped y la configuración SMTP.')
            return redirect(destino)
    except Reservas.DoesNotExist:
        messages.error(request, 'Reserva no encontrada.')
        return redirect(destino)

    return render(request, 'admini/checkin.html', {'reserva': reserva})


def registrar_pago_reserva(request, reserva_id):
    if request.session.get('rol') not in ['Administrador', 'Recepcionista']:
        return redirect('/login')
    destino = '/recepcion' if request.session.get('rol') == 'Recepcionista' else '/adminreserva'
    if request.method != 'POST':
        return redirect(destino)

    metodos = {'Efectivo', 'Tarjeta', 'Transferencia'}
    try:
        monto = Decimal(request.POST.get('valor', '').strip())
    except (InvalidOperation, AttributeError):
        messages.error(request, 'Ingresa un monto válido.')
        return redirect(destino)
    metodo = request.POST.get('metodopago', '')
    if not monto.is_finite() or monto <= 0 or metodo not in metodos:
        messages.error(request, 'El monto y el método de pago deben ser válidos.')
        return redirect(destino)

    with transaction.atomic():
        reserva = get_object_or_404(Reservas.objects.select_for_update(), id=reserva_id)
        if reserva.estado in ['Cancelada', 'Finalizada']:
            messages.error(request, 'No se pueden registrar pagos para una reserva cancelada o finalizada.')
            return redirect(destino)
        pagado = Pagos.objects.filter(reservas=reserva).exclude(
            metodopago='Pendiente'
        ).aggregate(total=Sum('valor'))['total'] or Decimal('0.00')
        saldo = max(Decimal('0.00'), reserva.valortotal - pagado)
        if monto > saldo:
            messages.error(request, 'El monto no puede superar el saldo pendiente.')
            return redirect(destino)

        Pagos.objects.create(reservas=reserva, valor=monto, metodopago=metodo, concepto='Reserva')
        if reserva.estado == 'Pendiente':
            reserva.estado = 'Pagada - Por validar'
            reserva.save(update_fields=['estado'])

    correo_enviado = False
    correo_destino = _correo_huesped(reserva.huespedes)
    if correo_destino:
        try:
            correo_enviado = bool(_enviar_correo_hotel(
                f'Pago registrado - Reserva CC-{reserva.id:04d}',
                'Recibimos tu pago',
                (
                    f'Hola {reserva.huespedes.nombres} {reserva.huespedes.apellidos},\n\n'
                    f'Registramos un pago de ${formato_numero_colombiano(monto, 2)} COP para tu reserva CC-{reserva.id:04d}. '
                    'El hotel verificará el pago antes de confirmarlo.'
                ),
                correo_destino,
            ))
        except Exception:
            logger.exception('El pago de la reserva CC-%s se registró, pero falló el correo.', reserva.id)
    messages.success(request, f'Pago de ${formato_numero_colombiano(monto, 2)} registrado para la reserva CC-{reserva.id:04d}.')
    if not correo_enviado:
        messages.warning(request, 'El pago se registró, pero no se pudo enviar el correo. Verifica el email del huésped y la configuración SMTP.')
    return redirect(destino)


def checkout_reserva(request, reserva_id):
    if request.session.get('rol') not in ['Administrador', 'Recepcionista']:
        return redirect('/login')
    destino = '/recepcion' if request.session.get('rol') == 'Recepcionista' else '/adminreserva'
    if request.method != 'POST':
        return redirect(destino)

    metodo = request.POST.get('metodopago', '')
    with transaction.atomic():
        reserva = get_object_or_404(
            Reservas.objects.select_for_update(),
            id=reserva_id,
        )
        if reserva.estado != 'En curso':
            messages.error(request, 'Solo se puede hacer check-out de una reserva en curso.')
            return redirect(destino)

        pagado = Pagos.objects.filter(reservas=reserva).exclude(
            metodopago='Pendiente'
        ).aggregate(total=Sum('valor'))['total'] or Decimal('0.00')
        saldo = max(Decimal('0.00'), reserva.valortotal - pagado)
        if saldo > 0:
            if metodo not in {'Efectivo', 'Tarjeta', 'Transferencia'}:
                messages.error(request, 'Selecciona un método de pago para saldar la cuenta.')
                return redirect(destino)
            try:
                monto = Decimal(request.POST.get('valor', '').strip())
            except (InvalidOperation, AttributeError):
                messages.error(request, 'Ingresa un monto válido para completar el check-out.')
                return redirect(destino)
            if not monto.is_finite() or monto != saldo:
                messages.error(request, 'Para completar el check-out, registra exactamente el saldo pendiente.')
                return redirect(destino)
            Pagos.objects.create(reservas=reserva, valor=monto, metodopago=metodo, concepto='Reserva')

        if reserva.habitaciones_id and not Reservas.objects.filter(
            habitaciones_id=reserva.habitaciones_id,
            estado='En curso',
            fechaentrada__lt=reserva.fechasalida,
            fechasalida__gt=reserva.fechaentrada,
        ).exclude(id=reserva.id).exists():
            reserva.habitaciones.estado = 'Disponible'
            reserva.habitaciones.save(update_fields=['estado'])
        reserva.estado = 'Finalizada'
        reserva.save(update_fields=['estado'])

    factura_enviada = False
    try:
        _enviar_factura_reserva(reserva)
        factura_enviada = True
    except Exception:
        logger.exception(
            'El check-out de la reserva CC-%s se completó, pero no se pudo enviar la factura.',
            reserva.id,
        )

    resena_enviada = _enviar_invitacion_resena(reserva, request)
    if factura_enviada and resena_enviada:
        messages.success(
            request,
            f'Check-out registrado para la reserva CC-{reserva.id:04d}. Se enviaron la factura y la invitación para dejar una reseña.',
        )
    else:
        detalles = []
        if not factura_enviada:
            detalles.append('no se pudo enviar la factura')
        if not resena_enviada:
            detalles.append('no se pudo enviar la invitación para dejar una reseña')
        messages.warning(
            request,
            f'Check-out registrado para la reserva CC-{reserva.id:04d}, pero {" y ".join(detalles)}.',
        )
    return redirect(destino)


def conveniosadmin(request):
    if request.session.get('rol') != 'Administrador':
        return redirect('/login')

    hoy = timezone.localdate()
    CodigosConvenio.objects.filter(
        estado='Activo',
        FechaExpiracion__lt=hoy,
    ).update(estado='Vencido')

    if request.method == 'POST':
        accion = request.POST.get('accion')
        if accion == 'tipo':
            nombre = request.POST.get('nombre', '').strip()
            descripcion = request.POST.get('descripcion', '').strip()
            tipo_id = request.POST.get('tipo_id', '').strip()
            try:
                descuento = Decimal(request.POST.get('descuento', '').strip())
            except (InvalidOperation, AttributeError):
                descuento = None

            if not nombre or descuento is None or not descuento.is_finite() or descuento <= 0 or descuento > 100:
                messages.error(request, 'Ingresa un nombre y un descuento entre 0 y 100%.')
                return redirect('/adminconvenios')

            if tipo_id:
                if not tipo_id.isdigit():
                    messages.error(request, 'El tipo de convenio seleccionado no es válido.')
                    return redirect('/adminconvenios')
                tipo = get_object_or_404(TipoConvenio, id=tipo_id)
                tipo.nombre = nombre
                tipo.descripcion = descripcion
                tipo.PorcentajeDescuento = descuento
                tipo.estado = request.POST.get('estado') == 'on'
                tipo.save()
                messages.success(request, 'Tipo de convenio actualizado.')
            else:
                TipoConvenio.objects.create(
                    nombre=nombre,
                    descripcion=descripcion,
                    PorcentajeDescuento=descuento,
                    estado=True,
                )
                messages.success(request, 'Tipo de convenio creado.')
            return redirect('/adminconvenios')

        if accion == 'codigo':
            tipo_id = request.POST.get('tipo_convenio', '')
            if not tipo_id.isdigit():
                messages.error(request, 'Selecciona un tipo de convenio válido.')
                return redirect('/adminconvenios')
            tipo = get_object_or_404(TipoConvenio, id=tipo_id)
            sujeto = request.POST.get('tiposujeto', '')
            nombre_sujeto = request.POST.get('nombresujeto', '').strip()
            try:
                fecha_expiracion = date.fromisoformat(request.POST.get('fecha_expiracion', ''))
            except (TypeError, ValueError):
                messages.error(request, 'Selecciona una fecha de expiración válida.')
                return redirect('/adminconvenios')

            if not tipo.estado or fecha_expiracion < hoy or not nombre_sujeto or sujeto not in {'Empresa', 'Persona Natural'}:
                messages.error(request, 'Completa los datos y elige un tipo activo y una fecha de expiración vigente.')
                return redirect('/adminconvenios')

            for intento in range(5):
                codigo = f'CC-{get_random_string(8).upper()}'
                try:
                    with transaction.atomic():
                        CodigosConvenio.objects.create(
                            tipoConvenio=tipo,
                            Codigo=codigo,
                            tiposujeto=sujeto,
                            nombresujeto=nombre_sujeto,
                            FechaExpiracion=fecha_expiracion,
                        )
                    messages.success(request, f'Código de convenio generado: {codigo}')
                    break
                except IntegrityError:
                    if intento == 4:
                        messages.error(request, 'No se pudo generar un código único. Inténtalo nuevamente.')
            return redirect('/adminconvenios')

        if accion == 'estado':
            codigo_id = request.POST.get('codigo_id', '')
            if not codigo_id.isdigit():
                messages.error(request, 'El código seleccionado no es válido.')
                return redirect('/adminconvenios')
            codigo = get_object_or_404(CodigosConvenio, id=codigo_id)
            if codigo.estado == 'Usado':
                messages.error(request, 'Un código usado no se puede reactivar.')
            elif codigo.FechaExpiracion < hoy:
                codigo.estado = 'Vencido'
                codigo.save(update_fields=['estado'])
                messages.error(request, 'Un código vencido no se puede reactivar.')
            else:
                codigo.estado = 'Vencido' if codigo.estado == 'Activo' else 'Activo'
                codigo.save(update_fields=['estado'])
                messages.success(request, 'Estado del código actualizado.')
            return redirect('/adminconvenios')

        messages.error(request, 'La acción solicitada no es válida.')
        return redirect('/adminconvenios')

    return render(request, 'admini/convenios.html', {
        'tipos': TipoConvenio.objects.order_by('nombre'),
        'codigos': CodigosConvenio.objects.select_related('tipoConvenio').order_by('-FechaGeneracion'),
    })


def reportesadmin(request):
    if request.session.get('rol') != 'Administrador':
        return redirect('/login')
    return render(request, 'admini/reportes.html', {
        'hoy': timezone.localdate(),
        'habitaciones': Habitaciones.objects.order_by('numero'),
        'estados': Reservas.estados,
    })


def exportar_reporte(request):
    if request.session.get('rol') != 'Administrador':
        return redirect('/login')

    tipos_validos = {'reservas', 'ocupacion', 'ingresos', 'huespedes'}
    tipo = request.GET.get('tipo', 'reservas')
    if tipo not in tipos_validos:
        messages.error(request, 'Selecciona un tipo de reporte válido.')
        return redirect('/adminreportes')

    desde_str = request.GET.get('desde', '')
    hasta_str = request.GET.get('hasta', '')
    reporte_completo_reservas = (
        tipo == 'reservas' and not desde_str and not hasta_str
    )
    if reporte_completo_reservas:
        desde = hasta = None
    else:
        try:
            desde = date.fromisoformat(desde_str)
            hasta = date.fromisoformat(hasta_str)
        except (TypeError, ValueError):
            messages.error(request, 'Selecciona un rango de fechas válido.')
            return redirect('/adminreportes')
    if not reporte_completo_reservas and hasta < desde:
        messages.error(request, 'La fecha final debe ser igual o posterior a la inicial.')
        return redirect('/adminreportes')

    respuesta = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    nombre_archivo = (
        'reporte_reservas_completo.csv' if reporte_completo_reservas
        else f'reporte_{tipo}_{desde}_{hasta}.csv'
    )
    respuesta['Content-Disposition'] = f'attachment; filename="{nombre_archivo}"'
    escritor = csv.writer(respuesta, delimiter=';')

    def escribir_fila(*valores):
        seguros = [
            f"'{valor}" if isinstance(valor, str) and valor.startswith(('=', '+', '-', '@', '\t', '\r')) else valor
            for valor in valores
        ]
        escritor.writerow(seguros)

    if tipo == 'reservas':
        reservas = Reservas.objects.select_related(
            'huespedes', 'habitaciones', 'planes', 'codigosConvenio'
        )
        if not reporte_completo_reservas:
            reservas = reservas.filter(fechaentrada__gte=desde, fechaentrada__lte=hasta)
        estado = request.GET.get('estado', '')
        habitacion_id = request.GET.get('habitacion', '')
        huesped = request.GET.get('huesped', '').strip()
        if estado:
            reservas = reservas.filter(estado=estado)
        if habitacion_id.isdigit():
            reservas = reservas.filter(habitaciones_id=int(habitacion_id))
        if huesped:
            reservas = reservas.filter(
                Q(huespedes__nombres__icontains=huesped)
                | Q(huespedes__apellidos__icontains=huesped)
            )
        escribir_fila('Reserva', 'Huésped', 'Alojamiento', 'Entrada', 'Salida', 'Estado', 'Total', 'Pagado', 'Saldo', 'Convenio')
        for reserva in reservas.order_by('fechaentrada', 'id').iterator():
            pagado = Pagos.objects.filter(reservas=reserva).exclude(
                metodopago='Pendiente'
            ).aggregate(total=Sum('valor'))['total'] or Decimal('0.00')
            alojamiento = (
                f'Habitación {reserva.habitaciones.numero}' if reserva.habitaciones
                else reserva.planes.nombre if reserva.planes
                else 'Sin asignar'
            )
            escribir_fila(
                f'CC-{reserva.id:04d}',
                f'{reserva.huespedes.nombres} {reserva.huespedes.apellidos}',
                alojamiento,
                reserva.fechaentrada,
                reserva.fechasalida,
                reserva.estado,
                reserva.valortotal,
                pagado,
                max(Decimal('0.00'), reserva.valortotal - pagado),
                reserva.codigosConvenio.Codigo if reserva.codigosConvenio else '',
            )

    elif tipo == 'ocupacion':
        habitaciones = Habitaciones.objects.order_by('numero')
        escribir_fila('Habitación', 'Estado actual', 'Reserva en el periodo', 'Huésped', 'Entrada', 'Salida')
        ocupadas_periodo = 0
        habitaciones_total = habitaciones.count()
        for habitacion in habitaciones.iterator():
            reserva = Reservas.objects.filter(
                habitaciones=habitacion,
                estado__in=['Pendiente', 'Pagada - Por validar', 'Confirmada', 'En curso'],
                fechaentrada__lte=hasta,
                fechasalida__gt=desde,
            ).select_related('huespedes').order_by('fechaentrada').first()
            if reserva:
                ocupadas_periodo += 1
            escribir_fila(
                habitacion.numero,
                habitacion.estado,
                f'CC-{reserva.id:04d}' if reserva else '',
                f'{reserva.huespedes.nombres} {reserva.huespedes.apellidos}' if reserva else '',
                reserva.fechaentrada if reserva else '',
                reserva.fechasalida if reserva else '',
            )
        escribir_fila()
        escribir_fila('Habitaciones con reserva en el periodo', ocupadas_periodo)
        escribir_fila('Habitaciones totales', habitaciones_total)
        escribir_fila('Ocupación proyectada (%)', round(ocupadas_periodo * 100 / habitaciones_total, 2) if habitaciones_total else 0)

    elif tipo == 'ingresos':
        pagos = Pagos.objects.select_related(
            'reservas__huespedes', 'reservas__habitaciones', 'reservas__planes'
        ).filter(
            fecha__date__gte=desde,
            fecha__date__lte=hasta,
        ).exclude(metodopago='Pendiente').order_by('fecha', 'id')
        escribir_fila('Fecha', 'Reserva', 'Huésped', 'Método', 'Pago recibido', 'Total reserva', 'Saldo')
        total_recaudado = Decimal('0.00')
        for pago in pagos.iterator():
            pagado_reserva = Pagos.objects.filter(
                reservas=pago.reservas,
                fecha__date__lte=hasta,
            ).exclude(metodopago='Pendiente').aggregate(total=Sum('valor'))['total'] or Decimal('0.00')
            total_recaudado += pago.valor
            escribir_fila(
                pago.fecha,
                f'CC-{pago.reservas_id:04d}',
                f'{pago.reservas.huespedes.nombres} {pago.reservas.huespedes.apellidos}',
                pago.metodopago,
                pago.valor,
                pago.reservas.valortotal,
                max(Decimal('0.00'), pago.reservas.valortotal - pagado_reserva),
            )
        escribir_fila()
        escribir_fila('Total recaudado en el periodo', total_recaudado)

    else:
        reservas_periodo = Reservas.objects.filter(
            fechaentrada__gte=desde,
            fechaentrada__lte=hasta,
        )
        huespedes = Huespedes.objects.annotate(
            reservas_periodo=Count(
                'reservas',
                filter=Q(reservas__in=reservas_periodo),
                distinct=True,
            )
        ).order_by('apellidos', 'nombres')
        escribir_fila('Documento', 'Huésped', 'Correo', 'Teléfono', 'Nacionalidad', 'Reservas en el periodo')
        for huesped in huespedes.iterator():
            escribir_fila(
                huesped.identificacion,
                f'{huesped.nombres} {huesped.apellidos}',
                huesped.correo or '',
                huesped.telefono,
                huesped.nacionalidad,
                huesped.reservas_periodo,
            )

    return respuesta


def habitacionesadmin(request):
    if request.session.get('rol') != 'Administrador':
        return redirect('/login')

    if request.method == 'POST':
        habitacion_id = request.POST.get('habitacion_id', '')
        estados_permitidos = {valor for valor, _ in Habitaciones.estados}
        if not habitacion_id.isdigit():
            messages.error(request, 'Selecciona una habitación válida.')
            return redirect('/adminhabitaciones')

        ruta_nueva = ''
        try:
            with transaction.atomic():
                habitacion = get_object_or_404(
                    Habitaciones.objects.select_for_update(),
                    id=int(habitacion_id),
                )
                accion = request.POST.get('accion', 'estado')
                estado = request.POST.get('estado', '')
                reserva_en_curso = Reservas.objects.filter(
                    habitaciones=habitacion,
                    estado='En curso',
                    fechaentrada__lte=timezone.localdate(),
                    fechasalida__gt=timezone.localdate(),
                ).first()

                if accion == 'editar':
                    numero = request.POST.get('numero', '').strip()
                    tipo_id = request.POST.get('tipohabitacion', '').strip()
                    tipo = TipoHabitacion.objects.filter(id=tipo_id).first() if tipo_id.isdigit() else None
                    try:
                        capacidad = int(request.POST.get('capacidad', ''))
                        precio = Decimal(request.POST.get('precio', '').strip())
                    except (ValueError, InvalidOperation, AttributeError):
                        raise ValueError('La capacidad o la tarifa no son válidas.')

                    if not numero or len(numero) > 20:
                        raise ValueError('Ingresa un número de habitación válido.')
                    if Habitaciones.objects.exclude(id=habitacion.id).filter(numero=numero).exists():
                        raise ValueError('Ese número de habitación ya está registrado.')
                    if not tipo:
                        raise ValueError('Selecciona un tipo de habitación válido.')
                    if capacidad < 1 or capacidad > 100 or not precio.is_finite() or precio <= 0 or precio > Decimal('99999999.99'):
                        raise ValueError('La capacidad debe estar entre 1 y 100 y la tarifa debe ser mayor que cero.')
                    if estado not in estados_permitidos:
                        raise ValueError('Selecciona un estado válido.')
                    if estado == 'Ocupada' and habitacion.estado != 'Ocupada':
                        raise ValueError('Una habitación solo queda ocupada al registrar el check-in de una reserva.')
                    if reserva_en_curso and estado != 'Ocupada':
                        raise ValueError('No se puede cambiar el estado de una habitación con una estadía en curso.')
                    if reserva_en_curso and capacidad < reserva_en_curso.cantidadacompañantes:
                        raise ValueError('La capacidad no puede ser menor que la cantidad de huéspedes de la estadía actual.')

                    archivo = request.FILES.get('imagen')
                    if archivo:
                        ruta_nueva = _guardar_imagen_habitacion(archivo)
                    ruta_anterior = habitacion.imagen
                    habitacion.numero = numero
                    habitacion.tipohabitacion = tipo
                    habitacion.capacidad = capacidad
                    habitacion.precio = precio.quantize(Decimal('0.01'))
                    habitacion.estado = estado
                    if ruta_nueva:
                        habitacion.imagen = ruta_nueva
                    habitacion.save()
                    if ruta_nueva:
                        _eliminar_imagen_habitacion(ruta_anterior or '')
                    messages.success(request, f'Habitación {habitacion.numero} actualizada correctamente.')
                else:
                    if estado not in estados_permitidos:
                        raise ValueError('Selecciona un estado válido.')
                    if reserva_en_curso:
                        raise ValueError('No se puede cambiar el estado de una habitación con una estadía en curso.')
                    if estado == 'Ocupada':
                        raise ValueError('Una habitación solo queda ocupada al registrar el check-in de una reserva.')
                    habitacion.estado = estado
                    habitacion.save(update_fields=['estado'])
                    messages.success(request, f'Estado de la habitación {habitacion.numero} actualizado.')
        except ValueError as error:
            if ruta_nueva:
                _eliminar_imagen_habitacion(ruta_nueva)
            messages.error(request, str(error))
        except IntegrityError:
            if ruta_nueva:
                _eliminar_imagen_habitacion(ruta_nueva)
            messages.error(request, 'No se pudo guardar la habitación. Verifica los datos e inténtalo nuevamente.')
        return redirect('/adminhabitaciones')

    busqueda = request.GET.get('q', '').strip()
    reservas_actuales = Reservas.objects.filter(
        habitaciones_id=OuterRef('pk'),
        estado='En curso',
        fechaentrada__lte=timezone.localdate(),
        fechasalida__gt=timezone.localdate(),
    )
    habitaciones = Habitaciones.objects.select_related('tipohabitacion').annotate(
        tiene_estadia_actual=Exists(reservas_actuales),
    ).order_by('numero')
    if busqueda:
        habitaciones = habitaciones.filter(
            Q(numero__icontains=busqueda)
            | Q(tipohabitacion__nombre__icontains=busqueda)
            | Q(estado__icontains=busqueda)
        )
    habitaciones = list(habitaciones)
    for habitacion in habitaciones:
        habitacion.imagen_admin_url = _url_imagen_habitacion(habitacion.imagen)
    return render(request, 'admini/habitaciones.html', {
        'habitaciones': habitaciones,
        'busqueda': busqueda,
        'estados_habitacion': Habitaciones.estados,
        'tipos_habitacion': TipoHabitacion.objects.order_by('nombre'),
        'conteo_habitaciones': {
            'total': Habitaciones.objects.count(),
            'disponibles': Habitaciones.objects.filter(estado='Disponible').count(),
            'ocupadas': Habitaciones.objects.filter(estado='Ocupada').count(),
            'bloqueadas': Habitaciones.objects.filter(
                estado__in=['Bloqueada', 'Fuera-de-servicio']
            ).count(),
        },
        'nombre': request.session.get('usuario_nom', 'Administrador'),
        'rol': request.session.get('rol', 'Administrador'),
    })


def huespedesadmin(request):
    if request.session.get('rol') != 'Administrador':
        return redirect('/login')

    busqueda = request.GET.get('q', '').strip()
    huespedes = Huespedes.objects.select_related('usuarios').annotate(
        total_reservas=Count('reservas', distinct=True),
    ).order_by('apellidos', 'nombres')
    if busqueda:
        huespedes = huespedes.filter(
            Q(nombres__icontains=busqueda)
            | Q(apellidos__icontains=busqueda)
            | Q(identificacion__icontains=busqueda)
            | Q(correo__icontains=busqueda)
        )
    huespedes = Paginator(huespedes, 25).get_page(request.GET.get('page'))
    return render(request, 'admini/huespedes.html', {
        'page_obj': huespedes,
        'busqueda': busqueda,
        'total_huespedes': Huespedes.objects.count(),
        'nombre': request.session.get('usuario_nom', 'Administrador'),
        'rol': request.session.get('rol', 'Administrador'),
    })


def usuariosadmin(request):
    if request.session.get('rol') != 'Administrador':
        return redirect('/login')

    if request.method == 'POST':
        if request.POST.get('accion') == 'eliminar':
            usuario_id = request.POST.get('usuario_id', '')
            if not usuario_id.isdigit():
                messages.error(request, 'Selecciona un usuario válido para eliminar.')
                return redirect('/adminusuarios')

            with transaction.atomic():
                usuario = get_object_or_404(
                    Usuarios.objects.select_for_update().select_related('roles'),
                    id=int(usuario_id),
                )
                if str(usuario.id) == str(request.session.get('usuario_id')):
                    messages.error(request, 'No puedes eliminar tu propia cuenta.')
                elif usuario.roles.nombre == 'Administrador' and usuario.estado and Usuarios.objects.filter(
                    roles__nombre='Administrador',
                    estado=True,
                ).count() <= 1:
                    messages.error(request, 'Debe permanecer al menos un administrador activo.')
                else:
                    nombre_usuario = f'{usuario.nombre} {usuario.apellido}'
                    usuario.delete()
                    messages.success(request, f'Usuario {nombre_usuario} eliminado correctamente.')
            return redirect('/adminusuarios')

        if request.POST.get('accion') == 'completar_perfil_huesped':
            usuario_id = request.POST.get('usuario_id', '').strip()
            usuario = Usuarios.objects.filter(
                id=usuario_id,
                roles__nombre='Cliente',
            ).first() if usuario_id.isdigit() else None
            if not usuario:
                return JsonResponse({'ok': False, 'errors': {'usuario': 'Selecciona una cuenta de cliente válida.'}}, status=400)
            if Huespedes.objects.filter(usuarios=usuario).exists():
                return JsonResponse({'ok': False, 'errors': {'perfil': 'Esta cuenta ya tiene un perfil de huésped.'}}, status=409)

            nacionalidad_enviada = request.POST.get('nacionalidad', '').strip()
            nacionalidad = next(
                (
                    gentilicio
                    for gentilicio, pais in NACIONALIDADES.items()
                    if nacionalidad_enviada.casefold() in {
                        gentilicio.casefold(), pais.casefold(),
                    }
                ),
                '',
            )
            datos_huesped = {
                'tipodocumento': request.POST.get('tipodocumento', '').strip(),
                'identificacion': request.POST.get('identificacion', '').strip(),
                'nombres': usuario.nombre,
                'apellidos': usuario.apellido,
                'telefono': request.POST.get('telefono', '').strip(),
                'direccion': request.POST.get('direccion', '').strip(),
                'correo': usuario.correo,
                'nacionalidad': nacionalidad,
            }
            errores = {}
            if datos_huesped['tipodocumento'] not in {'CC', 'CE', 'Pasaporte', 'TI'}:
                errores['tipodocumento'] = 'Selecciona un tipo de documento válido.'
            if not all(datos_huesped[campo] for campo in (
                'identificacion', 'telefono', 'direccion', 'nacionalidad',
            )):
                errores['perfil'] = 'Completa documento, teléfono, dirección y nacionalidad.'
            if len(datos_huesped['identificacion']) > 50 or len(datos_huesped['telefono']) > 100 or len(datos_huesped['direccion']) > 100:
                errores['perfil'] = 'Revisa la longitud de los datos del huésped.'
            if datos_huesped['identificacion'] and Huespedes.objects.filter(
                identificacion=datos_huesped['identificacion'],
            ).exists():
                errores['identificacion'] = 'Ese documento ya está asociado a otro huésped.'
            if errores:
                return JsonResponse({'ok': False, 'errors': errores}, status=400)
            try:
                Huespedes.objects.create(usuarios=usuario, **datos_huesped)
            except IntegrityError:
                return JsonResponse({'ok': False, 'errors': {'perfil': 'No se pudo vincular el perfil. Verifica el documento.'}}, status=409)
            return JsonResponse({'ok': True}, status=201)

        if request.POST.get('accion') == 'crear':
            nombre = request.POST.get('nombre', '').strip()
            apellido = request.POST.get('apellido', '').strip()
            correo = request.POST.get('correo', '').strip().lower()
            contrasena = request.POST.get('contrasena', '')
            rol_id = request.POST.get('rol_id', '').strip()

            errores = {}
            if not nombre or len(nombre) > 100:
                errores['nombre'] = 'Ingresa un nombre de hasta 100 caracteres.'
            if not apellido or len(apellido) > 100:
                errores['apellido'] = 'Ingresa un apellido de hasta 100 caracteres.'
            try:
                validate_email(correo)
            except ValidationError:
                errores['correo'] = 'Ingresa un correo electrónico válido.'
            if len(correo) > 100:
                errores['correo'] = 'El correo no puede superar los 100 caracteres.'
            if correo and Usuarios.objects.filter(correo__iexact=correo).exists():
                errores['correo'] = 'Ya existe una cuenta con ese correo.'
            if len(contrasena) < 8:
                errores['contrasena'] = 'La contraseña debe tener al menos 8 caracteres.'
            rol = Roles.objects.filter(id=rol_id).first() if rol_id.isdigit() else None
            if not rol:
                errores['rol_id'] = 'Selecciona un rol válido.'

            datos_huesped = None
            if rol and rol.nombre == 'Cliente':
                nacionalidad_enviada = request.POST.get('nacionalidad', '').strip()
                nacionalidad = next(
                    (
                        gentilicio
                        for gentilicio, pais in NACIONALIDADES.items()
                        if nacionalidad_enviada.casefold() in {
                            gentilicio.casefold(), pais.casefold(),
                        }
                    ),
                    '',
                )
                datos_huesped = {
                    'tipodocumento': request.POST.get('tipodocumento', '').strip(),
                    'identificacion': request.POST.get('identificacion', '').strip(),
                    'nombres': nombre,
                    'apellidos': apellido,
                    'telefono': request.POST.get('telefono', '').strip(),
                    'direccion': request.POST.get('direccion', '').strip(),
                    'correo': correo,
                    'nacionalidad': nacionalidad,
                }
                if datos_huesped['tipodocumento'] not in {'CC', 'CE', 'Pasaporte', 'TI'}:
                    errores['tipodocumento'] = 'Selecciona un tipo de documento válido.'
                if not all(datos_huesped[campo] for campo in (
                    'identificacion', 'telefono', 'direccion', 'nacionalidad',
                )):
                    errores['perfil_huesped'] = 'Completa documento, teléfono, dirección y nacionalidad del cliente.'
                limites_huesped = {
                    'identificacion': 50,
                    'telefono': 100,
                    'direccion': 100,
                    'correo': 100,
                }
                if any(
                    len(datos_huesped[campo]) > limite
                    for campo, limite in limites_huesped.items()
                ):
                    errores['perfil_huesped'] = 'Revisa la longitud de los datos del huésped.'
                if datos_huesped['identificacion'] and Huespedes.objects.filter(
                    identificacion=datos_huesped['identificacion'],
                ).exists():
                    errores['identificacion'] = 'Ya existe un huésped con ese documento.'
            if errores:
                return JsonResponse({'ok': False, 'errors': errores}, status=400)

            try:
                with transaction.atomic():
                    usuario = Usuarios.objects.create(
                        nombre=nombre,
                        apellido=apellido,
                        correo=correo,
                        contrasena=make_password(contrasena),
                        roles=rol,
                        estado=True,
                    )
                    if datos_huesped:
                        Huespedes.objects.create(usuarios=usuario, **datos_huesped)
            except IntegrityError:
                return JsonResponse({
                    'ok': False,
                    'errors': {'cuenta': 'No se pudo crear la cuenta y el perfil. Verifica el correo y el documento.'},
                }, status=409)

            return JsonResponse({
                'ok': True,
                'message': (
                    f'Cliente {usuario.nombre} {usuario.apellido} y su perfil de huésped creados correctamente.'
                    if datos_huesped
                    else f'Usuario {usuario.nombre} {usuario.apellido} creado correctamente.'
                ),
            }, status=201)

        usuario_id = request.POST.get('usuario_id', '')
        rol_id = request.POST.get('rol_id', '')
        if not usuario_id.isdigit() or not rol_id.isdigit():
            messages.error(request, 'Selecciona un usuario y un rol válidos.')
            return redirect('/adminusuarios')

        with transaction.atomic():
            usuario = get_object_or_404(Usuarios.objects.select_for_update(), id=int(usuario_id))
            rol = get_object_or_404(Roles, id=int(rol_id))
            nuevo_estado = request.POST.get('estado') == 'on'
            cambia_admin = usuario.roles.nombre == 'Administrador' and (
                rol.nombre != 'Administrador' or not nuevo_estado
            )
            if rol.nombre == 'Cliente' and not Huespedes.objects.filter(usuarios=usuario).exists():
                messages.error(
                    request,
                    'No se puede asignar el rol Cliente sin un perfil de huésped. Completa el perfil antes de cambiar el rol.',
                )
            elif str(usuario.id) == str(request.session.get('usuario_id')) and (
                rol.nombre != 'Administrador' or not nuevo_estado
            ):
                messages.error(request, 'No puedes cambiar tu propio rol ni desactivar tu cuenta.')
            elif cambia_admin and Usuarios.objects.filter(
                roles__nombre='Administrador',
                estado=True,
            ).count() <= 1:
                messages.error(request, 'Debe permanecer al menos un administrador activo.')
            else:
                usuario.roles = rol
                usuario.estado = nuevo_estado
                usuario.save(update_fields=['roles', 'estado'])
                messages.success(request, f'Acceso actualizado para {usuario.nombre} {usuario.apellido}.')
        return redirect('/adminusuarios')

    busqueda = request.GET.get('q', '').strip()
    usuarios = Usuarios.objects.select_related('roles')
    if busqueda:
        usuarios = usuarios.filter(
            Q(nombre__icontains=busqueda)
            | Q(apellido__icontains=busqueda)
            | Q(correo__icontains=busqueda)
            | Q(roles__nombre__icontains=busqueda)
        )
    clientes = usuarios.filter(roles__nombre='Cliente').annotate(
        tiene_perfil_huesped=Exists(Huespedes.objects.filter(usuarios_id=OuterRef('pk'))),
    ).order_by('apellido', 'nombre')
    personal = usuarios.filter(
        roles__nombre__in=['Administrador', 'Recepcionista'],
    ).order_by('apellido', 'nombre')
    return render(request, 'admini/usuarios.html', {
        'clientes': Paginator(clientes, 25).get_page(request.GET.get('clientes_page')),
        'personal': Paginator(personal, 25).get_page(request.GET.get('personal_page')),
        'roles': Roles.objects.order_by('nombre'),
        'nacionalidades': NACIONALIDADES,
        'busqueda': busqueda,
        'tab': request.GET.get('tab', 'clientes'),
        'nombre': request.session.get('usuario_nom', 'Administrador'),
        'rol': request.session.get('rol', 'Administrador'),
    })


def serviciosadmin(request):
    if request.session.get('rol') != 'Administrador':
        return redirect('/login')

    if request.method == 'POST':
        accion = request.POST.get('accion', 'crear')
        if accion not in {'crear', 'editar'}:
            messages.error(request, 'La acción solicitada no es válida.')
            return redirect('/adminservicios')
        nombre = request.POST.get('nombre', '').strip()
        descripcion = request.POST.get('descripcion', '').strip()
        estado = request.POST.get('estado') == 'on'
        try:
            precio = Decimal(request.POST.get('precio', '').strip())
            if not precio.is_finite():
                raise InvalidOperation
            precio = precio.quantize(Decimal('0.01'))
        except (InvalidOperation, AttributeError):
            messages.error(request, 'Ingresa un precio válido.')
            return redirect('/adminservicios')
        if precio < 0 or precio > Decimal('99999999.99'):
            messages.error(request, 'Ingresa un precio válido.')
            return redirect('/adminservicios')

        if not nombre or len(nombre) > 100 or len(descripcion) > 255:
            messages.error(request, 'Verifica el nombre y la descripción del servicio.')
            return redirect('/adminservicios')

        if accion == 'editar':
            servicio_id = request.POST.get('servicio_id', '')
            servicio = get_object_or_404(Servicios, id=servicio_id) if servicio_id.isdigit() else None
            if not servicio:
                messages.error(request, 'Selecciona un servicio válido.')
                return redirect('/adminservicios')
        else:
            servicio = Servicios()

        archivo = request.FILES.get('imagen') or request.FILES.get('txtImg')
        ruta_anterior = servicio.imagen or ''
        ruta_nueva = ''
        if archivo:
            try:
                ruta_nueva = _guardar_imagen_servicio(archivo)
            except ValueError as error:
                messages.error(request, str(error))
                return redirect('/adminservicios')

        servicio.nombre = nombre
        servicio.descripcion = descripcion
        servicio.precio = precio
        servicio.estado = estado
        if ruta_nueva:
            servicio.imagen = ruta_nueva
        try:
            servicio.save()
        except Exception:
            if ruta_nueva:
                _eliminar_imagen_servicio(ruta_nueva)
            logger.exception('No se pudo guardar el servicio %s.', nombre)
            messages.error(request, 'No se pudo guardar el servicio. Vuelve a intentarlo.')
            return redirect('/adminservicios')
        if ruta_nueva and ruta_anterior:
            _eliminar_imagen_servicio(ruta_anterior)
        messages.success(request, 'Servicio guardado correctamente.')
        return redirect('/adminservicios')

    servicios = list(Servicios.objects.order_by('nombre'))
    for servicio in servicios:
        servicio.url_imagen = _url_imagen_local(servicio.imagen)
    servicios_pendientes = ServicioReserva.objects.filter(
        estado='Pendiente',
        pago__metodopago='Pendiente',
    ).select_related(
        'reservas__huespedes__usuarios',
        'reservas__habitaciones',
        'servicios',
        'pago',
    ).order_by('fecha')
    fecha_limite_servicios = timezone.now() - timedelta(days=3)
    servicios_recientes = list(ServicioReserva.objects.filter(
        fecha__gte=fecha_limite_servicios,
    ).select_related(
        'reservas__huespedes__usuarios',
        'reservas__habitaciones',
        'servicios',
        'pago',
    ).order_by('-fecha'))
    ids_pagos_servicio = [item.pago_id for item in servicios_recientes if item.pago_id]
    reembolsos_servicio = {
        fila['pago_origen_id']: fila['total'] or Decimal('0.00')
        for fila in Pagos.objects.filter(
            concepto='Reembolso',
            pago_origen_id__in=ids_pagos_servicio,
        ).values('pago_origen_id').annotate(total=Sum('valor'))
    }
    ids_reservas_servicio = {item.reservas_id for item in servicios_recientes}
    pagos_netos_reserva = {
        fila['reservas_id']: fila['total'] or Decimal('0.00')
        for fila in Pagos.objects.filter(
            reservas_id__in=ids_reservas_servicio,
        ).exclude(metodopago='Pendiente').values('reservas_id').annotate(total=Sum('valor'))
    }
    for item in servicios_recientes:
        item.correo_huesped = _correo_huesped(item.reservas.huespedes)
        item.metodo_pago_registrado = item.pago.metodopago if item.pago_id else ''
        item.reembolso_disponible = Decimal('0.00')
        item.reembolso_realizado = Decimal('0.00')
        if item.estado == 'Aprobado' and item.pago_id and item.pago.valor > 0:
            reembolsado = reembolsos_servicio.get(item.pago_id, Decimal('0.00'))
            item.reembolso_realizado = abs(reembolsado)
            disponible_pago = max(Decimal('0.00'), item.pago.valor + reembolsado)
            disponible_reserva = max(
                Decimal('0.00'),
                pagos_netos_reserva.get(item.reservas_id, Decimal('0.00')),
            )
            item.reembolso_disponible = min(disponible_pago, disponible_reserva)
    return render(request, 'admini/servicios.html', {
        'servicios': servicios,
        'servicios_pendientes': servicios_pendientes,
        'servicios_recientes': servicios_recientes,
        'fecha_limite_servicios': fecha_limite_servicios,
        'notificaciones_servicios': servicios_pendientes.count(),
        'nombre': request.session.get('usuario_nom', 'Administrador'),
        'rol': request.session.get('rol', 'Administrador'),
    })


def tiposhabitacionadmin(request):
    if request.session.get('rol') != 'Administrador':
        return redirect('/login')

    if request.method == 'POST':
        accion = request.POST.get('accion', 'crear')
        tab = 'planes' if request.POST.get('tab') == 'planes' else 'habitaciones'
        destino = f'/admintiposhabitacion?tab={tab}'

        if accion in {'crear', 'editar'}:
            nombre = request.POST.get('nombre', '').strip()
            try:
                capacidad = int(request.POST.get('capacidad', ''))
                tarifa = Decimal(request.POST.get('tarifa', '').strip())
                if not tarifa.is_finite():
                    raise InvalidOperation
                tarifa = tarifa.quantize(Decimal('0.01'))
            except (ValueError, InvalidOperation, AttributeError):
                messages.error(request, 'Ingresa una capacidad y tarifa válidas.')
                return redirect('/admintiposhabitacion')

            if not nombre or len(nombre) > 100 or capacidad < 1 or capacidad > 100:
                messages.error(request, 'Ingresa un nombre y una capacidad entre 1 y 100.')
            elif tarifa <= 0 or tarifa > Decimal('99999999.99'):
                messages.error(request, 'La tarifa debe ser mayor que cero y tener un valor válido.')
            else:
                if accion == 'editar':
                    tipo_id = request.POST.get('tipo_id', '')
                    tipo = TipoHabitacion.objects.filter(id=tipo_id).first() if tipo_id.isdigit() else None
                    if not tipo:
                        messages.error(request, 'Selecciona un tipo de habitación válido.')
                        return redirect('/admintiposhabitacion')
                else:
                    tipo = TipoHabitacion()
                archivo_imagen = request.FILES.get('imagen')
                ruta_nueva = ''
                if archivo_imagen:
                    try:
                        ruta_nueva = _guardar_imagen_tipo_habitacion(archivo_imagen)
                    except ValueError as error:
                        messages.error(request, str(error))
                        return redirect(destino)
                tipo.nombre = nombre
                tipo.capacidad = capacidad
                tipo.tarifa = tarifa
                if ruta_nueva:
                    tipo.imagen = ruta_nueva
                tipo.save()
                # Se conserva la imagen anterior para no romper referencias históricas.
                mensaje = 'Tipo de habitación actualizado correctamente.' if accion == 'editar' else 'Tipo de habitación creado correctamente.'
                messages.success(request, mensaje)
            return redirect('/admintiposhabitacion')

        if accion == 'eliminar_plan':
            plan_id = request.POST.get('plan_id', '')
            plan = Planes.objects.filter(id=plan_id).first() if plan_id.isdigit() else None
            if not plan:
                messages.error(request, 'Selecciona un tipo de plan válido.')
            else:
                try:
                    plan.delete()
                    messages.success(request, 'Tipo de plan eliminado correctamente.')
                except ProtectedError:
                    messages.error(
                        request,
                        'No se puede eliminar un plan que ya tiene reservas; puedes desactivarlo en su lugar.',
                    )
            return redirect(destino)

        if accion not in {'crear_plan', 'editar_plan'}:
            messages.error(request, 'La acción solicitada no es válida.')
            return redirect(destino)

        plan_id = request.POST.get('plan_id', '')
        if accion == 'editar_plan':
            plan = Planes.objects.filter(id=plan_id).first() if plan_id.isdigit() else None
            if not plan:
                messages.error(request, 'Selecciona un tipo de plan válido.')
                return redirect(destino)
        else:
            plan = Planes()

        nombre = request.POST.get('nombre', '').strip()
        descripcion = request.POST.get('descripcion', '').strip()
        imagen = plan.imagen or ''
        try:
            precio = Decimal(request.POST.get('precio', '').strip())
            disponibles = int(request.POST.get('disponibles', ''))
            duracion_dias = int(request.POST.get('duracion_dias', ''))
            max_adultos = int(request.POST.get('max_adultos', ''))
            max_ninos = int(request.POST.get('max_ninos', ''))
            orden = int(request.POST.get('orden', ''))
            if not precio.is_finite():
                raise InvalidOperation
            precio = precio.quantize(Decimal('0.01'))
        except (ValueError, InvalidOperation, AttributeError):
            messages.error(request, 'Ingresa valores numéricos válidos para el tipo de plan.')
            return redirect(destino)

        servicio_ids = request.POST.getlist('servicios')
        if any(not servicio_id.isdigit() for servicio_id in servicio_ids):
            messages.error(request, 'Selecciona servicios válidos para el tipo de plan.')
            return redirect(destino)
        servicios = list(Servicios.objects.filter(id__in=servicio_ids))
        if len(servicios) != len(set(servicio_ids)):
            messages.error(request, 'Uno o más servicios seleccionados ya no existen.')
            return redirect(destino)
        caracteristicas = [
            linea.strip()
            for linea in request.POST.get('caracteristicas', '').splitlines()
            if linea.strip()
        ]

        tipo_habitacion_id = request.POST.get('tipo_habitacion', '').strip()
        tipo_habitacion = None
        if tipo_habitacion_id:
            tipo_habitacion = (
                TipoHabitacion.objects.filter(id=tipo_habitacion_id).first()
                if tipo_habitacion_id.isdigit()
                else None
            )
            if not tipo_habitacion:
                messages.error(request, 'Selecciona un tipo de habitación válido.')
                return redirect(destino)

        if (
            not nombre or len(nombre) > 100
            or len(descripcion) > 255
            or len(imagen) > 255
            or any(len(caracteristica) > 100 for caracteristica in caracteristicas)
            or precio <= 0 or precio > Decimal('9999999999.99')
            or disponibles < 0 or disponibles > 2147483647
            or duracion_dias < 1 or duracion_dias > 365
            or max_adultos < 1 or max_adultos > 100
            or max_ninos < 0 or max_ninos > 100
            or orden < 0 or orden > 2147483647
        ):
            messages.error(request, 'Revisa los datos y límites del tipo de plan.')
            return redirect(destino)

        archivo_imagen = request.FILES.get('imagen')
        ruta_nueva = ''
        if archivo_imagen:
            try:
                ruta_nueva = _guardar_imagen_plan(archivo_imagen)
            except ValueError as error:
                messages.error(request, str(error))
                return redirect(destino)

        plan.nombre = nombre
        plan.descripcion = descripcion
        plan.precio = precio
        if ruta_nueva:
            plan.imagen = ruta_nueva
        elif not plan.imagen:
            plan.imagen = None
        plan.estado = request.POST.get('estado') == 'on'
        plan.disponibles = disponibles
        plan.tipo_habitacion = tipo_habitacion
        plan.duracion_dias = duracion_dias
        plan.max_adultos = max_adultos
        plan.max_ninos = max_ninos
        plan.orden = orden
        plan.save()
        plan.Servicios_tipos.set(servicios)
        if accion == 'editar_plan':
            plan.caracteristicas.all().delete()
        CaracteristicaPlan.objects.bulk_create([
            CaracteristicaPlan(
                plan=plan,
                texto=caracteristica,
                orden=orden_caracteristica,
            )
            for orden_caracteristica, caracteristica in enumerate(caracteristicas)
        ])
        mensaje = (
            'Tipo de plan actualizado correctamente.'
            if accion == 'editar_plan'
            else 'Tipo de plan creado correctamente.'
        )
        messages.success(request, mensaje)
        return redirect(destino)

    tipos_habitacion = list(TipoHabitacion.objects.order_by('nombre'))
    for tipo in tipos_habitacion:
        tipo.url_imagen = _url_imagen_local(tipo.imagen)
    planes_admin = list(Planes.objects.select_related(
            'tipo_habitacion',
        ).prefetch_related(
            'Servicios_tipos',
            'caracteristicas',
        ).order_by('orden', 'id'))
    for plan in planes_admin:
        plan.url_imagen = _url_imagen_local(plan.imagen)

    return render(request, 'admini/tipos_habitacion.html', {
        'tipos_habitacion': tipos_habitacion,
        'planes_admin': planes_admin,
        'servicios_admin': Servicios.objects.order_by('nombre'),
        'tab_tipos': 'planes' if request.GET.get('tab') == 'planes' else 'habitaciones',
        'nombre': request.session.get('usuario_nom', 'Administrador'),
        'rol': request.session.get('rol', 'Administrador'),
    })


def pagosadmin(request):
    if request.session.get('rol') != 'Administrador':
        return redirect('/login')

    pagos = Pagos.objects.select_related(
        'reservas__huespedes',
    ).order_by('-fecha')
    pagos_reservas = pagos.filter(concepto='Reserva')
    pagos_servicios = pagos.filter(concepto='Servicio')
    reembolsos = pagos.filter(Q(concepto='Reembolso') | Q(valor__lt=0)).distinct()
    pagos_reembolsables = pagos.filter(
        valor__gt=0,
        concepto__in=['Reserva', 'Servicio'],
    ).exclude(metodopago='Pendiente')
    pagos_reembolsables = list(pagos_reembolsables)
    reembolsos_por_pago = {
        fila['pago_origen_id']: fila['total'] or Decimal('0.00')
        for fila in Pagos.objects.filter(
            pago_origen__in=pagos_reembolsables,
            concepto='Reembolso',
        ).values('pago_origen_id').annotate(total=Sum('valor'))
    }
    for pago in pagos_reembolsables:
        pago.monto_reembolsable = max(
            Decimal('0.00'),
            pago.valor + reembolsos_por_pago.get(pago.id, Decimal('0.00')),
        )
    montos_disponibles = {
        pago.id: pago.monto_reembolsable for pago in pagos_reembolsables
    }
    for pago in [*pagos_reservas, *pagos_servicios]:
        pago.monto_reembolsable = montos_disponibles.get(
            pago.id,
            Decimal('0.00'),
        )
    pestaña = request.GET.get('tab', 'reservas')
    listas = {
        'reservas': pagos_reservas,
        'servicios': pagos_servicios,
        'reembolsos': reembolsos,
    }
    if pestaña not in listas:
        pestaña = 'reservas'
    return render(request, 'admini/pagos.html', {
        'pagos_reservas': pagos_reservas,
        'pagos_servicios': pagos_servicios,
        'reembolsos': reembolsos,
        'pagos_reembolsables': pagos_reembolsables,
        'page_obj': Paginator(listas[pestaña], 25).get_page(request.GET.get('page')),
        'tab_activa': pestaña,
        'nombre': request.session.get('usuario_nom', 'Administrador'),
        'rol': request.session.get('rol', 'Administrador'),
    })


def _crear_pdf_movimientos(titulo, subtitulo, datos, encabezados, anchos, resumen=None):
    salida = BytesIO()
    documento = SimpleDocTemplate(
        salida,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=titulo,
    )
    estilos = getSampleStyleSheet()
    teal = colors.HexColor('#183D3D')
    teal_claro = colors.HexColor('#EAF1EF')
    dorado = colors.HexColor('#C6A15B')
    borde = colors.HexColor('#DCE4E1')
    estilo_titulo = ParagraphStyle(
        'HotelTitle', parent=estilos['Title'], textColor=teal,
        fontName='Helvetica-Bold', fontSize=21, leading=25,
        alignment=0, spaceAfter=4,
    )
    estilo_seccion = ParagraphStyle(
        'HotelSection', parent=estilos['Heading2'], textColor=teal,
        fontName='Helvetica-Bold', fontSize=12, leading=16,
        spaceBefore=0, spaceAfter=8,
    )
    estilo_detalle = ParagraphStyle(
        'HotelDetail',
        parent=estilos['BodyText'],
        textColor=colors.HexColor('#64747A'), fontSize=9, leading=13,
    )
    estilo_celda = ParagraphStyle(
        'HotelCell', parent=estilo_detalle, fontSize=8.5, leading=11,
    )
    estilo_encabezado = ParagraphStyle(
        'HotelTableHeader', parent=estilo_celda,
        textColor=colors.white, fontName='Helvetica-Bold', fontSize=8,
        leading=10,
    )
    tabla_datos = [[Paragraph(escape_html(str(valor)), estilo_encabezado) for valor in encabezados]]
    tabla_datos.extend([
        [Paragraph(escape_html(str(valor)), estilo_celda) for valor in fila]
        for fila in datos
    ])
    tabla = Table(tabla_datos, colWidths=anchos, repeatRows=1, hAlign='LEFT')
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), teal),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [
            colors.white,
            colors.HexColor('#F7F9F8'),
        ]),
        ('LINEBELOW', (0, 0), (-1, 0), 1, dorado),
        ('LINEBELOW', (0, 1), (-1, -1), .45, borde),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (-1, 1), (-1, -1), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 9),
    ]))
    hotel = Hoteles.objects.order_by('id').first()
    nombre_hotel = hotel.nombre if hotel else 'Caribe Confort'
    ubicacion = ', '.join(
        valor for valor in (
            hotel.direccion if hotel else '',
            hotel.municipio if hotel else '',
        ) if valor
    )
    def dibujar_pie(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(borde)
        canvas.setLineWidth(.5)
        canvas.line(18 * mm, 13 * mm, A4[0] - 18 * mm, 13 * mm)
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#748184'))
        canvas.drawString(18 * mm, 8 * mm, escape_html(nombre_hotel))
        canvas.drawRightString(A4[0] - 18 * mm, 8 * mm, f'Página {doc.page}')
        canvas.restoreState()

    contenido = [
        Table([[Paragraph(escape_html(nombre_hotel), ParagraphStyle(
            'HotelBrand', parent=estilo_titulo, fontSize=10, leading=12,
            textColor=colors.white,
        )), Paragraph(escape_html(ubicacion or 'Riohacha, La Guajira'), ParagraphStyle(
            'HotelLocation', parent=estilo_detalle, fontSize=8,
            textColor=colors.HexColor('#D6E2DF'), alignment=2,
        ))]], colWidths=[documento.width * .56, documento.width * .44],
            style=TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), teal),
                ('LINEBEFORE', (0, 0), (0, 0), 3, dorado),
                ('LEFTPADDING', (0, 0), (-1, -1), 12),
                ('RIGHTPADDING', (0, 0), (-1, -1), 12),
                ('TOPPADDING', (0, 0), (-1, -1), 12),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ])),
        Spacer(1, 9 * mm),
        Paragraph(escape_html(titulo), estilo_titulo),
        Paragraph('CERTIFICADO OFICIAL DE MOVIMIENTOS', estilo_seccion),
        Paragraph(escape_html(subtitulo), estilo_detalle),
    ]
    if ubicacion:
        contenido.extend([Paragraph(escape_html(ubicacion), estilo_detalle)])
    contenido.append(Spacer(1, 8 * mm))
    if resumen:
        estilo_resumen_label = ParagraphStyle(
            'HotelSummaryLabel', parent=estilo_detalle,
            fontName='Helvetica-Bold', fontSize=8,
            textColor=colors.HexColor('#64747A'),
        )
        estilo_resumen_valor = ParagraphStyle(
            'HotelSummaryValue', parent=estilo_titulo,
            fontSize=14, leading=17,
        )
        contenido.append(Table(
            [[
                Paragraph('TOTAL PAGADO REGISTRADO', estilo_resumen_label),
                Paragraph(escape_html(resumen['total']), estilo_resumen_valor),
                Paragraph(
                    f"{int(resumen['movimientos'])} movimiento(s)",
                    ParagraphStyle(
                        'HotelSummaryCount', parent=estilo_detalle,
                        alignment=2, fontName='Helvetica-Bold',
                        textColor=teal,
                    ),
                ),
            ]],
            colWidths=[documento.width * .43, documento.width * .34, documento.width * .23],
            style=TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), teal_claro),
                ('LINEBEFORE', (0, 0), (0, 0), 3, dorado),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 10),
                ('RIGHTPADDING', (0, 0), (-1, -1), 10),
                ('TOPPADDING', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ]),
        ))
        contenido.append(Spacer(1, 7 * mm))
    contenido.append(tabla)
    documento.build(contenido, onFirstPage=dibujar_pie, onLaterPages=dibujar_pie)
    return salida.getvalue()


def _respuesta_pdf(contenido, nombre_archivo):
    respuesta = HttpResponse(contenido, content_type='application/pdf')
    respuesta['Content-Disposition'] = f'attachment; filename="{nombre_archivo}"'
    return respuesta


def _crear_pdf_factura_reserva(reserva, hotel, huesped, alojamiento, pagos, servicios=None):
    """Construye una factura de una página con jerarquía visual y resumen de saldo."""
    salida = BytesIO()
    margen = 18 * mm
    ancho_pagina = A4[0] - (2 * margen)
    documento = SimpleDocTemplate(
        salida,
        pagesize=A4,
        rightMargin=margen,
        leftMargin=margen,
        topMargin=15 * mm,
        bottomMargin=16 * mm,
        title=f'Factura reserva CC-{reserva.id:04d}',
        author=hotel.nombre if hotel else 'Caribe Confort',
    )
    teal = colors.HexColor('#183D3D')
    teal_claro = colors.HexColor('#EAF1EF')
    dorado = colors.HexColor('#C6A15B')
    texto = colors.HexColor('#26363A')
    suave = colors.HexColor('#64747A')
    borde = colors.HexColor('#DCE4E1')
    estilos = getSampleStyleSheet()
    marca = ParagraphStyle(
        'FacturaMarca', parent=estilos['Normal'], fontName='Helvetica-Bold',
        fontSize=17, leading=20, textColor=colors.white,
    )
    marca_detalle = ParagraphStyle(
        'FacturaMarcaDetalle', parent=estilos['Normal'], fontSize=8,
        leading=11, textColor=colors.HexColor('#D6E2DF'),
    )
    titulo = ParagraphStyle(
        'FacturaTitulo', parent=estilos['Normal'], fontName='Helvetica-Bold',
        fontSize=10, leading=13, alignment=2, textColor=colors.white,
    )
    seccion = ParagraphStyle(
        'FacturaSeccion', parent=estilos['Normal'], fontName='Helvetica-Bold',
        fontSize=9, leading=12, textColor=teal, spaceAfter=7,
    )
    detalle = ParagraphStyle(
        'FacturaDetalle', parent=estilos['Normal'], fontSize=8.5,
        leading=12, textColor=texto,
    )
    detalle_suave = ParagraphStyle(
        'FacturaDetalleSuave', parent=detalle, fontSize=7.5,
        leading=10, textColor=suave,
    )
    celda = ParagraphStyle(
        'FacturaCelda', parent=detalle, fontSize=7.5, leading=10,
    )
    celda_header = ParagraphStyle(
        'FacturaCeldaHeader', parent=celda, fontName='Helvetica-Bold',
        textColor=teal,
    )
    total_estilo = ParagraphStyle(
        'FacturaTotal', parent=detalle, fontName='Helvetica-Bold',
        fontSize=11, leading=14, textColor=colors.white,
    )
    monto_grande = ParagraphStyle(
        'FacturaMontoGrande', parent=total_estilo, fontSize=15,
        leading=18, alignment=2, textColor=colors.white,
    )

    def moneda(valor):
        return '$' + formato_numero_colombiano(valor, 0) + ' COP'

    telefono = getattr(hotel, 'telefono', '') if hotel else ''
    correo = getattr(hotel, 'correo', '') if hotel else ''
    contacto = ' | '.join(valor for valor in (telefono, correo) if valor)
    encabezado = Table(
        [[
            [Paragraph(escape_html(hotel.nombre if hotel else 'Caribe Confort'), marca),
             Paragraph(escape_html(contacto or 'Riohacha, La Guajira'), marca_detalle)],
            Paragraph('FACTURA DE RESERVA<br/><font size="9">CC-' + f'{reserva.id:04d}' + '</font>', titulo),
        ]],
        colWidths=[ancho_pagina * .68, ancho_pagina * .32],
    )
    encabezado.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), teal),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
    ]))

    direccion = ', '.join(valor for valor in (
        hotel.direccion if hotel else '',
        hotel.municipio if hotel else '',
    ) if valor)
    resumen = Table(
        [[
            Paragraph('<b>HUÉSPED</b><br/>' + escape_html(huesped) + '<br/>' +
                      escape_html(reserva.huespedes.identificacion or 'Documento no registrado'), detalle),
            Paragraph('<b>ESTANCIA</b><br/>' + escape_html(alojamiento) + '<br/>' +
                      f'Entrada: {reserva.fechaentrada:%d/%m/%Y}<br/>' +
                      f'Salida: {reserva.fechasalida:%d/%m/%Y}', detalle),
        ], [
            Paragraph('<b>EMITIDA - ESTADO</b><br/>' + timezone.localdate().strftime('%d/%m/%Y') +
                      ' - ' + escape_html(reserva.estado), detalle_suave),
            Paragraph('<b>HOTEL</b><br/>' + escape_html(direccion or 'Riohacha, La Guajira'), detalle_suave),
        ]],
        colWidths=[ancho_pagina / 2, ancho_pagina / 2],
    )
    resumen.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F6F8F7')),
        ('BOX', (0, 0), (-1, -1), .6, borde),
        ('INNERGRID', (0, 0), (-1, -1), .35, borde),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 11),
        ('RIGHTPADDING', (0, 0), (-1, -1), 11),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))

    servicios = servicios or []
    noches = max(1, (reserva.fechasalida - reserva.fechaentrada).days)
    total_servicios = sum((servicio.valor for servicio in servicios), Decimal('0.00'))
    filas_detalle = [[
        Paragraph('CONCEPTO', celda_header),
        Paragraph('DETALLE', celda_header),
        Paragraph('VALOR', celda_header),
    ]]
    if reserva.habitaciones_id:
        tarifa = reserva.habitaciones.precio
        total_alojamiento = tarifa * noches
        filas_detalle.append([
            Paragraph('Alojamiento', celda),
            Paragraph(f'{noches} noches × {moneda(tarifa)} · {escape_html(alojamiento)}', celda),
            Paragraph(moneda(total_alojamiento), celda),
        ])
    elif reserva.planes_id:
        total_alojamiento = reserva.planes.precio
        filas_detalle.append([
            Paragraph('Plan de estancia', celda),
            Paragraph(escape_html(alojamiento), celda),
            Paragraph(moneda(total_alojamiento), celda),
        ])
    else:
        total_alojamiento = reserva.valortotal - total_servicios
        filas_detalle.append([
            Paragraph('Alojamiento', celda),
            Paragraph(f'{noches} noches · {escape_html(alojamiento)}', celda),
            Paragraph(moneda(total_alojamiento), celda),
        ])
    for servicio in servicios:
        tarifa_servicio = servicio.valor / max(servicio.cantidad, 1)
        filas_detalle.append([
            Paragraph(escape_html(servicio.servicios.nombre), celda),
            Paragraph(f'{servicio.cantidad} × {moneda(tarifa_servicio)}', celda),
            Paragraph(moneda(servicio.valor), celda),
        ])
    ajustes = reserva.valortotal - total_alojamiento - total_servicios
    if ajustes:
        filas_detalle.append([
            Paragraph('Otros conceptos y ajustes', celda),
            Paragraph('Ajuste registrado en la reserva', celda),
            Paragraph(moneda(ajustes), celda),
        ])
    tabla_detalle = Table(
        filas_detalle,
        colWidths=[43 * mm, ancho_pagina - 95 * mm, 52 * mm],
        repeatRows=1,
    )
    tabla_detalle.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), teal_claro),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAF9')]),
        ('LINEBELOW', (0, 0), (-1, -1), .35, borde),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (-1, 0), (-1, -1), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
    ]))

    filas_pagos = [[
        Paragraph('FECHA', celda_header),
        Paragraph('CONCEPTO', celda_header),
        Paragraph('MÉTODO', celda_header),
        Paragraph('VALOR', celda_header),
    ]]
    if pagos:
        for pago in pagos:
            filas_pagos.append([
                Paragraph(pago.fecha.strftime('%d/%m/%Y %H:%M'), celda),
                Paragraph(escape_html(pago.get_concepto_display()), celda),
                Paragraph(escape_html(pago.metodopago or '—'), celda),
                Paragraph(escape_html(moneda(pago.valor)), celda),
            ])
    else:
        filas_pagos.append([
            Paragraph('Sin pagos registrados', celda), '', '', '',
        ])
    tabla_pagos = Table(
        filas_pagos,
        colWidths=[35 * mm, 47 * mm, 43 * mm, ancho_pagina - 125 * mm],
        repeatRows=1,
    )
    tabla_pagos.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), teal_claro),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAF9')]),
        ('LINEBELOW', (0, 0), (-1, 0), .7, borde),
        ('LINEBELOW', (0, 1), (-1, -1), .35, borde),
        ('SPAN', (0, 1), (-1, 1)) if not pagos else ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (-1, 0), (-1, -1), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))

    total_abonado = sum((pago.valor for pago in pagos), Decimal('0.00'))
    saldo = max(Decimal('0.00'), reserva.valortotal - total_abonado)
    resumen_totales = Table([
        [Paragraph('Total de la estancia', detalle), Paragraph(moneda(reserva.valortotal), detalle)],
        [Paragraph('Total abonado', detalle), Paragraph(moneda(total_abonado), detalle)],
        [Paragraph('Saldo pendiente', detalle), Paragraph(moneda(saldo), detalle)],
        [Paragraph('TOTAL FACTURA', total_estilo), Paragraph(moneda(reserva.valortotal), monto_grande)],
    ], colWidths=[ancho_pagina * .62, ancho_pagina * .38])
    resumen_totales.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('LINEABOVE', (0, 0), (-1, 0), .8, borde),
        ('BACKGROUND', (0, 3), (-1, 3), teal),
        ('LINEBEFORE', (0, 3), (0, 3), 3, dorado),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
    ]))

    elementos = [
        encabezado,
        Spacer(1, 8 * mm),
        Paragraph('DETALLE DE LA RESERVA', seccion),
        resumen,
        Spacer(1, 8 * mm),
        Paragraph('DESGLOSE DE LA ESTANCIA', seccion),
        tabla_detalle,
        Paragraph(
            'Impuestos: no se desglosan por separado; se utilizan los importes totales registrados.',
            detalle_suave,
        ),
        Spacer(1, 6 * mm),
        Paragraph('PAGOS REGISTRADOS', seccion),
        tabla_pagos,
        Spacer(1, 5 * mm),
        resumen_totales,
        Spacer(1, 10 * mm),
        Paragraph('Gracias por elegir ' + escape_html(hotel.nombre if hotel else 'Caribe Confort') + '.', detalle_suave),
    ]
    documento.build(elementos)
    return salida.getvalue()


def descargar_factura_reserva(request, reserva_id):
    rol = request.session.get('rol')
    usuario_id = request.session.get('usuario_id')
    if rol not in {'Administrador', 'Recepcionista'} and not usuario_id:
        return redirect('/login')

    reserva = get_object_or_404(
        Reservas.objects.select_related(
            'huespedes',
            'habitaciones__tipohabitacion',
            'planes',
        ),
        id=reserva_id,
    )
    if (
        rol not in {'Administrador', 'Recepcionista'}
        and reserva.huespedes.usuarios_id != usuario_id
    ):
        return HttpResponseForbidden('No tienes permiso para descargar esta factura.')

    pagos = Pagos.objects.filter(reservas=reserva).exclude(
        metodopago='Pendiente',
    ).order_by('fecha', 'id')
    alojamiento = (
        f'Habitación {reserva.habitaciones.numero} · '
        f'{reserva.habitaciones.tipohabitacion.nombre}'
        if reserva.habitaciones
        else (reserva.planes.nombre if reserva.planes else 'Estancia')
    )
    huesped = f'{reserva.huespedes.nombres} {reserva.huespedes.apellidos}'
    hotel = Hoteles.objects.order_by('id').first()
    servicios = ServicioReserva.objects.filter(
        reservas=reserva,
        estado='Aprobado',
    ).select_related('servicios').order_by('fecha', 'id')
    contenido = _crear_pdf_factura_reserva(
        reserva,
        hotel,
        huesped,
        alojamiento,
        list(pagos),
        list(servicios),
    )
    return _respuesta_pdf(contenido, f'factura_reserva_CC-{reserva.id:04d}.pdf')


def descargar_certificado_pagos(request):
    usuario_id = request.session.get('usuario_id')
    if not usuario_id:
        return redirect('/login')
    try:
        huesped = Huespedes.objects.get(usuarios_id=usuario_id)
    except Huespedes.DoesNotExist:
        return HttpResponseForbidden('No hay un huésped asociado a esta cuenta.')

    pagos = Pagos.objects.filter(
        reservas__huespedes=huesped,
    ).exclude(
        metodopago='Pendiente',
    ).select_related('reservas').order_by('fecha', 'id')
    filas = [
        (
            pago.fecha.strftime('%d/%m/%Y %H:%M'),
            f'CC-{pago.reservas_id:04d}',
            pago.get_concepto_display(),
            pago.metodopago,
            f'${formato_numero_colombiano(pago.valor, 2)} COP',
        )
        for pago in pagos
    ]
    total_neto = sum((pago.valor for pago in pagos), Decimal('0.00'))
    subtitulo = (
        f'Certificado de movimientos de {huesped.nombres} {huesped.apellidos}. '
        f'Total neto registrado: ${formato_numero_colombiano(total_neto, 2)} COP.'
    )
    contenido = _crear_pdf_movimientos(
        'Certificado de pagos',
        subtitulo,
        filas,
        ('Fecha', 'Reserva', 'Concepto', 'Método', 'Valor'),
        (30 * mm, 25 * mm, 38 * mm, 35 * mm, 38 * mm),
        resumen={
            'total': f"${formato_numero_colombiano(total_neto, 2)} COP",
            'movimientos': len(filas),
        },
    )
    return _respuesta_pdf(
        contenido,
        f'certificado_pagos_huesped_{huesped.id}.pdf',
    )


def reglas_descuento_admin(request):
    if request.session.get('rol') != 'Administrador':
        return redirect('/login')

    if request.method == 'POST':
        accion = request.POST.get('accion', 'crear')
        try:
            dias_minimos = int(request.POST.get('dias_minimos', '').strip())
            porcentaje = Decimal(request.POST.get('porcentaje', '').strip())
        except (TypeError, ValueError, InvalidOperation, AttributeError):
            messages.error(request, 'Ingresa una cantidad de días y un porcentaje válidos.')
            return redirect('/adminreglas-descuento')

        if dias_minimos < 1 or not porcentaje.is_finite() or porcentaje <= 0 or porcentaje > 100:
            messages.error(request, 'Los días deben ser mayores a cero y el descuento debe estar entre 0 y 100%.')
            return redirect('/adminreglas-descuento')

        activa = request.POST.get('estado') == 'on'
        if accion == 'editar':
            regla_id = request.POST.get('regla_id', '')
            if not regla_id.isdigit():
                messages.error(request, 'Selecciona una regla de descuento válida.')
                return redirect('/adminreglas-descuento')
            regla = get_object_or_404(ReglaDescuento, id=regla_id)
            regla.dias_minimos = dias_minimos
            regla.porcentaje = porcentaje.quantize(Decimal('0.01'))
            regla.estado = activa
            regla.save(update_fields=['dias_minimos', 'porcentaje', 'estado'])
            messages.success(request, 'La regla de descuento se actualizó correctamente.')
        else:
            ReglaDescuento.objects.create(
                dias_minimos=dias_minimos,
                porcentaje=porcentaje.quantize(Decimal('0.01')),
                estado=activa,
            )
            messages.success(request, 'La regla de descuento se creó correctamente.')
        return redirect('/adminreglas-descuento')

    return render(request, 'admini/reglas_descuento.html', {
        'reglas': ReglaDescuento.objects.order_by('dias_minimos'),
        'nombre': request.session.get('usuario_nom', 'Administrador'),
        'rol': request.session.get('rol', 'Administrador'),
    })


def modificar_reserva(request, reserva_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Método no permitido.'}, status=405)
    if request.session.get('rol') not in {'Administrador', 'Recepcionista'}:
        return JsonResponse({'success': False, 'message': 'No autorizado.'}, status=403)

    try:
        nueva_entrada = date.fromisoformat(request.POST.get('nueva_fecha_entrada', ''))
        nueva_salida = date.fromisoformat(request.POST.get('nueva_fecha_salida', ''))
    except (TypeError, ValueError):
        return JsonResponse({'success': False, 'message': 'Ingresa fechas válidas.'}, status=400)
    if nueva_salida <= nueva_entrada:
        return JsonResponse({'success': False, 'message': 'La salida debe ser posterior a la entrada.'}, status=400)

    with transaction.atomic():
        reserva = get_object_or_404(
            Reservas.objects.select_for_update(),
            id=reserva_id,
        )
        if reserva.estado in {'Cancelada', 'Finalizada'}:
            return JsonResponse({'success': False, 'message': 'No se pueden modificar reservas canceladas o finalizadas.'}, status=400)
        if reserva.habitaciones_id:
            conflicto = Reservas.objects.filter(
                habitaciones_id=reserva.habitaciones_id,
                estado__in=['Pendiente', 'Pagada - Por validar', 'Confirmada', 'En curso'],
                fechaentrada__lt=nueva_salida,
                fechasalida__gt=nueva_entrada,
            ).exclude(id=reserva.id).exists()
            if conflicto:
                return JsonResponse({'success': False, 'message': 'La habitación ya está reservada en esas fechas.'}, status=409)
            precio_noche = reserva.habitaciones.precio
        elif reserva.planes_id and reserva.planes.duracion_dias:
            precio_noche = reserva.planes.precio / Decimal(reserva.planes.duracion_dias)
        else:
            return JsonResponse({'success': False, 'message': 'La reserva no tiene una tarifa disponible para recalcular.'}, status=400)

        correo_destino = _correo_huesped(reserva.huespedes)

        entrada_anterior = reserva.fechaentrada
        salida_anterior = reserva.fechasalida
        nuevo_total = (precio_noche * (nueva_salida - nueva_entrada).days).quantize(Decimal('0.01'))
        pagado = Pagos.objects.filter(reservas=reserva).exclude(
            metodopago='Pendiente',
        ).aggregate(total=Sum('valor'))['total'] or Decimal('0.00')
        reembolso = max(Decimal('0.00'), pagado - nuevo_total)
        reserva.fechaentrada = nueva_entrada
        reserva.fechasalida = nueva_salida
        reserva.valortotal = nuevo_total
        reserva.save(update_fields=['fechaentrada', 'fechasalida', 'valortotal'])

    try:
        if not correo_destino:
            raise RuntimeError('El huésped no tiene un correo válido registrado.')
        _enviar_correo_hotel(
            'Modificación de Reserva',
            'Actualización de tu reserva',
            (
                f'Hola {reserva.huespedes.nombres} {reserva.huespedes.apellidos},\n\n'
                f'Tu reserva CC-{reserva.id:04d} fue modificada.\n'
                f'Fechas anteriores: {entrada_anterior:%d/%m/%Y} al {salida_anterior:%d/%m/%Y}\n'
                f'Fechas nuevas: {nueva_entrada:%d/%m/%Y} al {nueva_salida:%d/%m/%Y}\n'
                f'Nuevo total: ${formato_numero_colombiano(nuevo_total, 2)} COP\n'
                f'Monto a reembolsar (si aplica): ${formato_numero_colombiano(reembolso, 2)} COP\n'
            ),
            correo_destino,
        )
    except Exception:
        logger.exception('No se pudo enviar el aviso de modificación de la reserva CC-%s.', reserva.id)
        return JsonResponse({
            'success': True,
            'correo_enviado': False,
            'message': 'La reserva se modificó, pero no se pudo enviar el correo.',
            'reembolso_pendiente': reembolso > 0,
            'reembolso': str(reembolso),
            'nuevo_total': str(nuevo_total),
        })

    return JsonResponse({
        'success': True,
        'correo_enviado': True,
        'message': 'Reserva modificada y correo enviado.',
        'reembolso_pendiente': reembolso > 0,
        'reembolso': str(reembolso),
        'nuevo_total': str(nuevo_total),
    })


def procesar_reembolso(request, reserva_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Método no permitido.'}, status=405)
    if request.session.get('rol') not in {'Administrador', 'Recepcionista'}:
        return JsonResponse({'success': False, 'message': 'No autorizado.'}, status=403)

    try:
        monto = Decimal(request.POST.get('monto', '').strip())
        monto_centavos = monto.quantize(Decimal('0.01'))
    except (InvalidOperation, AttributeError):
        return JsonResponse({'success': False, 'message': 'Ingresa un monto válido.'}, status=400)
    metodo = request.POST.get('metodo', '').strip()
    if (
        not monto.is_finite()
        or monto != monto_centavos
        or monto <= 0
        or metodo not in {'Efectivo', 'Transferencia'}
    ):
        return JsonResponse({'success': False, 'message': 'El monto o el método de reembolso no son válidos.'}, status=400)
    monto = monto_centavos
    pago_origen_id = request.POST.get('pago_id', '').strip()

    with transaction.atomic():
        reserva = get_object_or_404(
            Reservas.objects.select_for_update().select_related('huespedes'),
            id=reserva_id,
        )
        pagado = Pagos.objects.filter(reservas=reserva).exclude(
            metodopago='Pendiente',
        ).aggregate(total=Sum('valor'))['total'] or Decimal('0.00')
        pago_origen = None
        if pago_origen_id:
            pago_origen = Pagos.objects.select_for_update().filter(
                id=pago_origen_id,
                reservas=reserva,
                concepto__in=['Reserva', 'Servicio'],
                valor__gt=0,
            ).exclude(metodopago='Pendiente').first()
            if pago_origen is None:
                return JsonResponse({'success': False, 'message': 'El pago seleccionado no existe o no admite reembolso.'}, status=400)
            reembolsado = Pagos.objects.filter(
                pago_origen=pago_origen,
                concepto='Reembolso',
            ).aggregate(total=Sum('valor'))['total'] or Decimal('0.00')
            excedente = min(
                max(Decimal('0.00'), pago_origen.valor + reembolsado),
                max(Decimal('0.00'), pagado),
            )
        else:
            excedente = max(Decimal('0.00'), pagado - reserva.valortotal)
        if monto > excedente:
            return JsonResponse({'success': False, 'message': 'El monto supera el saldo disponible del pago para reembolso.'}, status=400)
        correo_destino = _correo_huesped(reserva.huespedes)
        Pagos.objects.create(
            reservas=reserva,
            valor=-monto,
            metodopago=metodo,
            concepto='Reembolso',
            pago_origen=pago_origen,
        )

    try:
        if not correo_destino:
            raise RuntimeError('El huésped no tiene un correo válido registrado.')
        _enviar_correo_hotel(
            'Reembolso Procesado',
            'Tu reembolso fue procesado',
            (
                f'Hola {reserva.huespedes.nombres} {reserva.huespedes.apellidos},\n\n'
                f'Te confirmamos la devolución de ${formato_numero_colombiano(monto, 2)} COP por el método {metodo} '
                f'para la reserva CC-{reserva.id:04d}.\n'
            ),
            correo_destino,
        )
    except Exception:
        logger.exception('El reembolso de la reserva CC-%s se registró, pero no se pudo enviar el correo.', reserva.id)
        return JsonResponse({
            'success': True,
            'correo_enviado': False,
            'message': 'El reembolso se registró, pero no se pudo enviar el correo.',
        })
    return JsonResponse({'success': True, 'correo_enviado': True, 'message': 'Reembolso procesado y correo enviado.'})


SECCION_CATEGORIA_GALERIA = {
    'carrusel': ('Carrusel', 'imagen'),
    'portada': ('Portadas', 'imagen'),
    'servicio': ('Servicios', 'estrella'),
    'galeria': ('Galería', 'imagen'),
}
ICONOS_CATEGORIA_GALERIA = {
    'imagen',
    'estrella',
    'cama',
    'personas',
    'restaurante',
    'piscina',
    'exterior',
    'edificio',
    'sol',
}
SECCIONES_GALERIA_PUBLICA = ('carrusel', 'galeria')
EXTENSIONES_IMAGEN_PERMITIDAS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}


def _guardar_imagen_galeria(archivo):
    extension = Path(archivo.name).suffix.lower()
    if extension not in EXTENSIONES_IMAGEN_PERMITIDAS:
        raise ValueError('El archivo debe ser JPG, PNG, WEBP o GIF.')
    if archivo.size > TAMANO_MAXIMO_IMAGEN:
        raise ValueError('La imagen no puede superar los 10 MB.')
    encabezado = archivo.read(12)
    archivo.seek(0)
    firmas = {
        '.jpg': encabezado.startswith(b'\xff\xd8\xff'),
        '.jpeg': encabezado.startswith(b'\xff\xd8\xff'),
        '.png': encabezado.startswith(b'\x89PNG\r\n\x1a\n'),
        '.gif': encabezado.startswith((b'GIF87a', b'GIF89a')),
        '.webp': encabezado.startswith(b'RIFF') and encabezado[8:12] == b'WEBP',
    }
    if not firmas[extension]:
        raise ValueError('El contenido del archivo no coincide con un formato de imagen permitido.')
    almacenamiento = FileSystemStorage(location=settings.MEDIA_ROOT)
    ruta = f'uploads/galeria/{uuid4().hex}{extension}'
    return almacenamiento.save(ruta, archivo)


def _eliminar_archivo_galeria(ruta):
    if not ruta.startswith('uploads/galeria/') or '..' in Path(ruta).parts:
        return
    try:
        if ImagenGaleria.objects.filter(imagen=ruta).exists():
            return
    except DatabaseError:
        logger.exception('No se pudo verificar si el archivo de galería sigue en uso: %s', ruta)
        return
    FileSystemStorage(location=settings.MEDIA_ROOT).delete(ruta)


def galeriaadmin(request):
    if request.session.get('rol') != 'Administrador':
        return redirect('/login')

    if request.method == 'POST':
        accion = request.POST.get('accion') or request.POST.get('_accion', '')
        if accion == 'crear_categoria':
            nombre = request.POST.get('nombre', '').strip()
            icono = request.POST.get('icono', 'imagen').strip()
            if (
                not nombre
                or len(nombre) > 100
                or icono not in ICONOS_CATEGORIA_GALERIA
            ):
                messages.error(request, 'Ingresa un nombre e icono válidos para la categoría.')
                return redirect('/admingaleria')
            nombres_existentes = CategoriaGaleria.objects.values_list(
                'nombre',
                flat=True,
            )
            if any(
                existente.strip().casefold() == nombre.casefold()
                for existente in nombres_existentes
            ):
                messages.error(request, 'Ya existe una categoría con ese nombre.')
                return redirect('/admingaleria')
            ultimo_orden = CategoriaGaleria.objects.order_by(
                '-orden',
            ).values_list('orden', flat=True).first()
            CategoriaGaleria.objects.create(
                nombre=nombre,
                icono=icono,
                orden=ultimo_orden + 1 if ultimo_orden is not None else 0,
                estado=True,
            )
            messages.success(request, f'Categoría "{nombre}" creada correctamente.')
            return redirect('/admingaleria')

        if accion == 'editar_categoria':
            categoria_id = request.POST.get('categoria_id', '').strip()
            nombre = request.POST.get('nombre', '').strip()
            icono = request.POST.get('icono', '').strip()
            if not categoria_id.isdigit():
                messages.error(request, 'La categoría seleccionada no es válida.')
                return redirect('/admingaleria')
            categoria = get_object_or_404(CategoriaGaleria, id=int(categoria_id))
            if (
                not nombre
                or len(nombre) > 100
                or icono not in ICONOS_CATEGORIA_GALERIA
            ):
                messages.error(request, 'Ingresa un nombre e icono válidos para la categoría.')
                return redirect('/admingaleria')
            nombres_existentes = CategoriaGaleria.objects.exclude(
                id=categoria.id,
            ).values_list('nombre', flat=True)
            if any(
                existente.strip().casefold() == nombre.casefold()
                for existente in nombres_existentes
            ):
                messages.error(request, 'Ya existe otra categoría con ese nombre.')
                return redirect('/admingaleria')
            categoria.nombre = nombre
            categoria.icono = icono
            categoria.estado = request.POST.get('estado') == 'on'
            categoria.save(update_fields=['nombre', 'icono', 'estado'])
            messages.success(request, f'Categoría "{nombre}" actualizada correctamente.')
            return redirect('/admingaleria')

        if accion == 'eliminar_categoria':
            categoria_id = request.POST.get('categoria_id', '').strip()
            destino_id = request.POST.get('destino_categoria_id', '').strip()
            if not categoria_id.isdigit():
                messages.error(request, 'La categoría seleccionada no es válida.')
                return redirect('/admingaleria')
            try:
                with transaction.atomic():
                    categoria = get_object_or_404(
                        CategoriaGaleria.objects.select_for_update(),
                        id=int(categoria_id),
                    )
                    imagenes_categoria = ImagenGaleria.objects.filter(categoria=categoria)
                    cantidad_imagenes = imagenes_categoria.count()
                    if cantidad_imagenes:
                        if not destino_id.isdigit():
                            messages.error(
                                request,
                                f'La categoría tiene {cantidad_imagenes} imágenes. Elige otra categoría para conservarlas antes de eliminarla.',
                            )
                            return redirect('/admingaleria')
                        destino = CategoriaGaleria.objects.filter(
                            id=int(destino_id),
                            estado=True,
                        ).exclude(id=categoria.id).first()
                        if destino is None:
                            messages.error(request, 'El destino para las imágenes no es válido.')
                            return redirect('/admingaleria')
                        imagenes_categoria.update(categoria=destino)
                    nombre_eliminado = categoria.nombre
                    categoria.delete()
            except ProtectedError:
                messages.error(
                    request,
                    'No se pudo eliminar la categoría porque todavía tiene imágenes asociadas. Reasígnalas a otra categoría e inténtalo de nuevo.',
                )
                return redirect('/admingaleria')
            messages.success(
                request,
                f'Categoría "{nombre_eliminado}" eliminada. Las imágenes asociadas se conservaron en la categoría de destino.'
                if cantidad_imagenes else f'Categoría "{nombre_eliminado}" eliminada correctamente.',
            )
            return redirect('/admingaleria')

        if accion == 'eliminar':
            imagen_id = request.POST.get('imagen_id', '')
            if not imagen_id.isdigit():
                messages.error(request, 'La imagen seleccionada no es válida.')
                return redirect('/admingaleria')
            imagen = get_object_or_404(ImagenGaleria, id=int(imagen_id))
            ruta_anterior = imagen.imagen
            imagen.delete()
            _eliminar_archivo_galeria(ruta_anterior)
            messages.success(request, 'Imagen eliminada del gestor.')
            return redirect('/admingaleria')

        imagen_id = request.POST.get('imagen_id', '')
        imagen = None
        if accion == 'editar':
            if not imagen_id.isdigit():
                messages.error(request, 'La imagen seleccionada no es válida.')
                return redirect('/admingaleria')
            imagen = get_object_or_404(ImagenGaleria, id=int(imagen_id))
        elif accion != 'crear':
            messages.error(request, 'La acción solicitada no es válida.')
            return redirect('/admingaleria')

        titulo = request.POST.get('titulo', '').strip()
        seccion = request.POST.get('seccion', '')
        if len(titulo) > 100 or seccion not in SECCION_CATEGORIA_GALERIA:
            messages.error(request, 'Revisa el título y la sección seleccionada.')
            return redirect('/admingaleria')

        categoria_id = request.POST.get('categoria_id', '').strip()
        categoria_seleccionada = None
        if categoria_id:
            if not categoria_id.isdigit():
                messages.error(request, 'La categoría seleccionada no es válida.')
                return redirect('/admingaleria')
            categoria_seleccionada = CategoriaGaleria.objects.filter(
                id=int(categoria_id),
            ).first()
            if categoria_seleccionada is None:
                messages.error(request, 'La categoría seleccionada ya no existe.')
                return redirect('/admingaleria')

        archivo = request.FILES.get('archivo')
        if accion == 'crear' and not archivo:
            messages.error(request, 'Selecciona una imagen para subir.')
            return redirect('/admingaleria')

        ruta_nueva = None
        try:
            if archivo:
                ruta_nueva = _guardar_imagen_galeria(archivo)
        except ValueError as error:
            messages.error(request, str(error))
            return redirect('/admingaleria')

        ruta_anterior = imagen.imagen if imagen else ''
        nombre_categoria, icono_categoria = SECCION_CATEGORIA_GALERIA[seccion]
        try:
            with transaction.atomic():
                if categoria_seleccionada:
                    categoria = categoria_seleccionada
                    if not categoria.estado:
                        categoria.estado = True
                        categoria.save(update_fields=['estado'])
                else:
                    categoria = CategoriaGaleria.objects.filter(
                        nombre__iexact=nombre_categoria,
                    ).order_by('id').first()
                    if categoria is None:
                        categoria = CategoriaGaleria.objects.create(
                            nombre=nombre_categoria,
                            icono=icono_categoria,
                            orden=len(SECCION_CATEGORIA_GALERIA),
                            estado=True,
                        )
                    elif (
                        categoria.icono != icono_categoria
                        or not categoria.estado
                    ):
                        categoria.icono = icono_categoria
                        categoria.estado = True
                        categoria.save(update_fields=['icono', 'estado'])

                if imagen:
                    imagen.titulo = titulo
                    imagen.seccion = seccion
                    imagen.categoria = categoria
                    imagen.estado = request.POST.get('estado') == 'on'
                    if ruta_nueva:
                        imagen.imagen = ruta_nueva
                    imagen.save(update_fields=['titulo', 'seccion', 'categoria', 'estado', 'imagen'])
                else:
                    ImagenGaleria.objects.create(
                        categoria=categoria,
                        titulo=titulo,
                        imagen=ruta_nueva,
                        seccion=seccion,
                        estado=True,
                    )
        except Exception:
            if ruta_nueva:
                _eliminar_archivo_galeria(ruta_nueva)
            logger.exception('No se pudo guardar la imagen de galería.')
            messages.error(request, 'No se pudo guardar la imagen. Verifica el archivo y vuelve a intentarlo.')
            return redirect('/admingaleria')

        if ruta_nueva and ruta_anterior:
            _eliminar_archivo_galeria(ruta_anterior)
        messages.success(request, 'Imagen guardada correctamente.')
        return redirect('/admingaleria')

    imagenes = list(ImagenGaleria.objects.select_related('categoria').order_by('seccion', 'id'))
    prefijo_static = f'/{settings.STATIC_URL.lstrip("/")}'
    prefijo_media = f'/{settings.MEDIA_URL.strip("/")}/'
    for imagen in imagenes:
        if imagen.imagen.startswith('img/imagenes/'):
            imagen.url_gestor = f'{prefijo_static}{imagen.imagen}'
        elif imagen.imagen.startswith(('http://', 'https://', '/')):
            imagen.url_gestor = imagen.imagen
        else:
            imagen.url_gestor = f'{prefijo_media}{imagen.imagen}'

    categorias_galeria = list(CategoriaGaleria.objects.annotate(
        total_imagenes=Count('imagengaleria'),
    ).order_by('orden', 'nombre'))
    categorias_activas = [categoria for categoria in categorias_galeria if categoria.estado]
    for categoria in categorias_galeria:
        categoria.tiene_destino_activo = any(
            destino.id != categoria.id for destino in categorias_activas
        )

    return render(request, 'admini/galeria.html', {
        'imagenes': imagenes,
        'secciones_galeria': ImagenGaleria.SECCIONES,
        'categorias_galeria': categorias_galeria,
        'iconos_categoria_galeria': sorted(ICONOS_CATEGORIA_GALERIA),
        'nombre': request.session.get('usuario_nom', 'Administrador'),
        'rol': request.session.get('rol', 'Administrador'),
    })


def configuracionadmin(request):
    if request.session.get('rol') != 'Administrador':
        return redirect('/login')

    hotel = Hoteles.objects.order_by('id').first()
    opciones_smtp = getattr(settings, 'MAILERS', {}).get('default', {}).get('OPTIONS', {})
    smtp_form = {
        'host': hotel.smtp_host if hotel and hotel.smtp_host else opciones_smtp.get('host', ''),
        'port': hotel.smtp_port if hotel and hotel.smtp_host else opciones_smtp.get('port', 587),
        'username': hotel.smtp_username if hotel and hotel.smtp_host else opciones_smtp.get('username', ''),
        'from_email': hotel.smtp_from_email if hotel and hotel.smtp_host else settings.DEFAULT_FROM_EMAIL,
        'use_tls': hotel.smtp_use_tls if hotel and hotel.smtp_host else opciones_smtp.get('use_tls', True),
    }

    if request.method == 'POST':
        if request.POST.get('seccion') == 'correo':
            smtp_form = {
                'host': request.POST.get('smtp_host', '').strip(),
                'port': request.POST.get('smtp_port', '').strip(),
                'username': request.POST.get('smtp_username', '').strip(),
                'from_email': request.POST.get('smtp_from_email', '').strip(),
                'use_tls': request.POST.get('smtp_use_tls') == 'on',
            }
            smtp_password = request.POST.get('smtp_password', '')
            puerto = None
            try:
                puerto = int(smtp_form['port'])
            except (TypeError, ValueError):
                messages.error(request, 'El puerto SMTP debe ser un número entre 1 y 65535.')

            if puerto is None:
                pass
            elif not all((
                smtp_form['host'],
                smtp_form['username'],
                smtp_form['from_email'],
            )):
                messages.error(request, 'Completa el host, usuario SMTP y correo de envío.')
            elif any((
                len(smtp_form['host']) > 255,
                len(smtp_form['username']) > 255,
                len(smtp_form['from_email']) > 254,
            )):
                messages.error(request, 'Uno o más datos SMTP superan la longitud permitida.')
            elif not 1 <= puerto <= 65535:
                messages.error(request, 'El puerto SMTP debe estar entre 1 y 65535.')
            else:
                try:
                    validate_email(smtp_form['from_email'])
                except ValidationError:
                    messages.error(request, 'Ingresa un correo de envío válido.')
                else:
                    if hotel is None:
                        messages.error(request, 'Guarda primero la información del hotel.')
                    else:
                        try:
                            if smtp_password:
                                smtp_password = _normalizar_contrasena_smtp(
                                    smtp_form['host'], smtp_password
                                )
                                contrasena_cifrada = _cifrar_contrasena_smtp(smtp_password)
                            elif hotel.smtp_password_encrypted:
                                _descifrar_contrasena_smtp(hotel.smtp_password_encrypted)
                                contrasena_cifrada = hotel.smtp_password_encrypted
                            else:
                                raise ValueError('Ingresa la contraseña SMTP para completar la configuración.')
                        except ValueError as error:
                            messages.error(request, str(error))
                        except RuntimeError as error:
                            messages.error(request, str(error))
                        else:
                            hotel.smtp_host = smtp_form['host']
                            hotel.smtp_port = puerto
                            hotel.smtp_username = smtp_form['username']
                            hotel.smtp_from_email = smtp_form['from_email']
                            hotel.smtp_password_encrypted = contrasena_cifrada
                            hotel.smtp_use_tls = smtp_form['use_tls']
                            hotel.save(update_fields=[
                                'smtp_host',
                                'smtp_port',
                                'smtp_username',
                                'smtp_from_email',
                                'smtp_password_encrypted',
                                'smtp_use_tls',
                            ])
                            conexion = None
                            try:
                                conexion, _ = _conexion_correo_hotel()
                                conexion.open()
                            except SMTPAuthenticationError:
                                logger.exception('Gmail rechazó las credenciales SMTP guardadas para el hotel.')
                                messages.error(
                                    request,
                                    'La configuración se guardó, pero Gmail rechazó la autenticación (535). Verifica que el usuario sea la misma cuenta que creó la contraseña de aplicación y vuelve a guardarla. El puerto 587 con STARTTLS respondió correctamente.',
                                )
                            except (OSError, SMTPException, RuntimeError, ValueError):
                                logger.exception('No se pudo verificar la conexión SMTP guardada para el hotel.')
                                messages.error(
                                    request,
                                    'La configuración se guardó, pero no se pudo verificar la conexión SMTP. Revisa host, puerto, seguridad y credenciales.',
                                )
                            else:
                                messages.success(
                                    request,
                                    'Configuración SMTP guardada y conexión con el servidor verificada. No se envió ningún correo.',
                                )
                            finally:
                                if conexion:
                                    conexion.close()
                            return redirect('/adminconfiguracion')
        else:
            try:
                archivo_logo = request.FILES.get('logo')
                if archivo_logo and archivo_logo.size > TAMANO_MAXIMO_IMAGEN:
                    raise ValidationError('El logo no puede superar los 10 MB.')
                logo_subido = ImageField(required=False).clean(
                    archivo_logo
                )
            except ValidationError as error:
                logo_subido = None
                messages.error(request, str(error.messages[0]))
            else:
                quitar_logo = request.POST.get('quitar_logo') == 'on'
                if logo_subido and quitar_logo:
                    messages.error(request, 'Sube un logo nuevo o marca la opción para quitarlo, no ambas.')
                else:
                    campos = {
                        'nombre': request.POST.get('nombre', '').strip(),
                        'descripcion': request.POST.get('descripcion', '').strip(),
                        'direccion': request.POST.get('direccion', '').strip(),
                        'municipio': request.POST.get('municipio', '').strip(),
                        'telefono': request.POST.get('telefono', '').strip(),
                        'correo': request.POST.get('correo', '').strip(),
                        'whatsapp': request.POST.get('whatsapp', '').strip(),
                        'checkin': request.POST.get('checkin', '').strip(),
                        'checkout': request.POST.get('checkout', '').strip(),
                        'recepcion': request.POST.get('recepcion', '').strip(),
                        'desayuno': request.POST.get('desayuno', '').strip(),
                        'fotografias': request.POST.get('fotografias', '').strip(),
                    }
                    limites = {
                        'nombre': 100, 'direccion': 100, 'municipio': 100,
                        'telefono': 20, 'correo': 100, 'fotografias': 255,
                        'whatsapp': 30, 'checkin': 30, 'checkout': 30,
                        'recepcion': 100, 'desayuno': 100,
                    }
                    if not all(campos[key] for key in ('nombre', 'direccion', 'municipio', 'telefono', 'correo')):
                        messages.error(request, 'Completa los campos obligatorios del hotel.')
                    elif any(len(campos[key]) > limite for key, limite in limites.items()):
                        messages.error(request, 'Uno o más campos superan la longitud permitida.')
                    else:
                        try:
                            validate_email(campos['correo'])
                        except ValidationError:
                            messages.error(request, 'Ingresa un correo de contacto válido.')
                        else:
                            logo_anterior = hotel.logo.name if hotel and hotel.logo else ''
                            if hotel is None:
                                hotel = Hoteles.objects.create(**campos, logo=logo_subido)
                            else:
                                for campo, valor in campos.items():
                                    setattr(hotel, campo, valor)
                                if logo_subido:
                                    hotel.logo = logo_subido
                                elif quitar_logo:
                                    hotel.logo = None
                                hotel.save(update_fields=[*campos, 'logo'])
                            if logo_anterior and hotel.logo.name != logo_anterior:
                                hotel.logo.storage.delete(logo_anterior)
                            messages.success(request, 'Los datos del hotel se guardaron correctamente.')
                            return redirect('/adminconfiguracion')

    return render(request, 'admini/configuracion.html', {
        'hotel': hotel,
        'smtp_form': smtp_form,
        'smtp_password_configurada': bool(
            hotel.smtp_password_encrypted if hotel and hotel.smtp_host
            else opciones_smtp.get('password')
        ),
        'smtp_encryption_key_configured': bool(
            (getattr(settings, 'EMAIL_CREDENTIAL_ENCRYPTION_KEY', '') or '').strip()
        ),
        'nombre': request.session.get('usuario_nom', 'Administrador'),
        'rol': request.session.get('rol', 'Administrador'),
    })

def registrarservicio(request):
    if request.session.get('rol') != 'Administrador':
        return redirect('/login')
    if request.method == 'POST':
        servicio = Servicios()
        servicio.nombre = (request.POST.get('txtNombre') or '').strip()
        servicio.descripcion = (request.POST.get('txtDescripcion') or '').strip()
        try:
            servicio.precio = Decimal(request.POST.get('txtPrecio', '').strip()).quantize(Decimal('0.01'))
        except (InvalidOperation, AttributeError):
            messages.error(request, 'Ingresa un precio válido para el servicio.')
            return redirect('/adminservicios')
        if not servicio.nombre or len(servicio.nombre) > 100 or len(servicio.descripcion) > 255:
            messages.error(request, 'Verifica el nombre y la descripción del servicio.')
            return redirect('/adminservicios')
        if servicio.precio < 0 or servicio.precio > Decimal('99999999.99'):
            messages.error(request, 'Ingresa un precio válido para el servicio.')
            return redirect('/adminservicios')
        servicio.estado = True
        archivo = request.FILES.get('txtImg') or request.FILES.get('imagen')
        ruta_nueva = ''
        try:
            if archivo:
                ruta_nueva = _guardar_imagen_servicio(archivo)
                servicio.imagen = ruta_nueva
            servicio.save()
        except ValueError as error:
            messages.error(request, str(error))
            return redirect('/adminservicios')
        except Exception:
            if ruta_nueva:
                _eliminar_imagen_servicio(ruta_nueva)
            logger.exception('No se pudo registrar el servicio %s.', servicio.nombre)
            messages.error(request, 'Verifica los datos y el formato de imagen del servicio.')
            return redirect('/adminservicios')
        return redirect('/adminservicios')

    return render(request, 'admini/registrarservicio.html')

def buscar_disponibilidad(request):
    hoy = timezone.localdate()
    fecha_entrada = request.GET.get('entrada') or hoy.isoformat()
    fecha_salida  = request.GET.get('salida') or (hoy + timedelta(days=1)).isoformat()
    adultos       = int(request.GET.get('adultos') or 2)
    ninos         = int(request.GET.get('ninos') or 0)
    habitaciones_n = request.GET.get('habitaciones') or '1'
    tipo          = request.GET.get('tipo', '')
    codigo        = request.GET.get('codigo', '').strip()
    codigo_error = ''
    descuento_convenio = Decimal('0')

    if codigo:
        convenio = _buscar_convenio_valido(codigo)
        if convenio:
            codigo = convenio.Codigo
            descuento_convenio = convenio.tipoConvenio.PorcentajeDescuento
        else:
            codigo_error = 'El código no existe, venció o ya fue utilizado.'

    habitaciones_qs = Habitaciones.objects.filter(
        estado='Disponible',
        capacidad__gte=adultos + ninos,
    )
    try:
        entrada_filtro = date.fromisoformat(fecha_entrada)
        salida_filtro = date.fromisoformat(fecha_salida)
    except (TypeError, ValueError):
        entrada_filtro = salida_filtro = None
    if entrada_filtro and salida_filtro and salida_filtro > entrada_filtro:
        reservas_solapadas = Reservas.objects.filter(
            habitaciones_id=OuterRef('pk'),
            estado__in=['Pendiente', 'Pagada - Por validar', 'Confirmada', 'En curso'],
            fechaentrada__lt=salida_filtro,
            fechasalida__gt=entrada_filtro,
        )
        habitaciones_qs = habitaciones_qs.annotate(
            tiene_reserva_solapada=Exists(reservas_solapadas)
        ).filter(tiene_reserva_solapada=False)
    if tipo:
        habitaciones_qs = habitaciones_qs.filter(tipohabitacion__nombre=tipo)

    tipos_qs = TipoHabitacion.objects.filter(
        habitaciones__isnull=False,
    ).distinct()
    if tipo:
        tipos_qs = tipos_qs.filter(nombre=tipo)
    tipos_qs = list(tipos_qs)
    for t in tipos_qs:
        habs_disponibles = habitaciones_qs.filter(tipohabitacion=t)
        t.cant_disponibles = habs_disponibles.count()
        t.ids_disponibles = list(habs_disponibles.values_list('id', flat=True))
        t.url_imagen = _url_imagen_local(t.imagen)

    resenas_por_tipo = {}
    if tipos_qs:
        resenas = Resena.objects.filter(
            reserva__habitaciones__tipohabitacion_id__in=[t.pk for t in tipos_qs],
            calificacion_habitacion__isnull=False,
        ).exclude(
            comentario='',
        ).select_related(
            'reserva__huespedes',
            'reserva__habitaciones',
        ).order_by('-fecha')

        for resena in resenas:
            habitacion = resena.reserva.habitaciones
            if habitacion and habitacion.tipohabitacion_id:
                resenas_por_tipo.setdefault(habitacion.tipohabitacion_id, []).append(resena)

    for t in tipos_qs:
        resenas_tipo = resenas_por_tipo.get(t.pk, [])
        t.resenas = resenas_tipo
        t.total_resenas = len(resenas_tipo)
        t.promedio_resenas = (
            sum(
                resena.calificacion_habitacion
                for resena in resenas_tipo
            ) / len(resenas_tipo)
            if resenas_tipo else None
        )

    context = {
        'tipos': tipos_qs,
        'fecha_entrada':  fecha_entrada,
        'fecha_salida':   fecha_salida,
        'adultos':        str(adultos),
        'ninos':          str(ninos),
        'habitaciones_n': habitaciones_n,
        'tipo':           tipo,
        'codigo':         codigo,
        'codigo_error':   codigo_error,
        'descuento_convenio': descuento_convenio,
        'noches':         1,
    }

    return render(request, 'clientes/reservar.html', context)

def iniciosesion(request):
    if request.method == "POST":
        correo = request.POST.get('correo')
        clave  = request.POST.get('clave')

        usuario = Usuarios.objects.filter(correo=correo, estado=True).first()

        if usuario and check_password(clave, usuario.contrasena):
            request.session['usuario_id']  = usuario.id
            request.session['usuario_nom'] = usuario.nombre
            request.session['rol']         = usuario.roles.nombre

            destinos = {
                'Administrador': '/administrador',
                'Recepcionista': '/recepcion',
                'Cliente':       '/home',
            }
            return redirect(destinos.get(usuario.roles.nombre, '/home'))

        return render(request, 'clientes/login.html', {'error': 'Credenciales incorrectas'})

    return render(request, 'clientes/login.html')


def registrarcliente(request):
    if request.session.get('usuario_id'):
        return redirect('/home')

    contexto = {
        'nacionalidades': NACIONALIDADES,
        'datos':          {},
        'errores':        [],
        'mostrar_modal':  False,
    }

    if request.method == 'POST':
        nombre       = request.POST.get('nombre', '').strip()
        apellido     = request.POST.get('apellido', '').strip()
        correo       = request.POST.get('correo', '').strip().lower()
        telefono     = request.POST.get('telefono', '').strip()
        tipo_doc     = request.POST.get('tipo_documento', '').strip()
        num_doc      = request.POST.get('numero_documento', '').strip()
        nacionalidad = request.POST.get('nacionalidad', '').strip()
        password     = request.POST.get('password', '')
        password2    = request.POST.get('password2', '')

        errores = []
        if not nombre:       errores.append('El nombre es obligatorio.')
        if not apellido:     errores.append('El apellido es obligatorio.')
        if not correo:       errores.append('El correo es obligatorio.')
        if not telefono:     errores.append('El teléfono es obligatorio.')
        if not tipo_doc:     errores.append('Selecciona el tipo de documento.')
        if not num_doc:      errores.append('El número de documento es obligatorio.')
        if nacionalidad not in NACIONALIDADES:
            errores.append('Selecciona una nacionalidad válida.')
        if len(password) < 6:
            errores.append('La contraseña debe tener al menos 6 caracteres.')
        if password != password2:
            errores.append('Las contraseñas no coinciden.')
        if correo and Usuarios.objects.filter(correo=correo).exists():
            errores.append('Ese correo ya está registrado.')
        if num_doc and Huespedes.objects.filter(identificacion=num_doc).exists():
            errores.append('Ese número de documento ya está registrado.')

        if errores:
            contexto['errores'] = errores
            contexto['datos']   = request.POST
            return render(request, 'clientes/registrarcliente.html', contexto)

        codigo = f"{random.randint(100000, 999999)}"
        request.session['registro_pendiente'] = {
            'nombre':       nombre,
            'apellido':     apellido,
            'correo':       correo,
            'telefono':     telefono,
            'tipo_doc':     tipo_doc,
            'num_doc':      num_doc,
            'nacionalidad': nacionalidad,
            'password':     password, 
            'codigo':       codigo,
        }

        try:
            _enviar_correo_hotel(
                'Tu código de verificación — Caribe Confort',
                'Confirma tu correo electrónico',
                (
                    f'¡Hola {nombre}!\n\n'
                    f'Tu código de verificación es: {codigo}\n\n'
                    f'Ingrésalo en la página para completar tu registro.\n\n'
                    f'Si no solicitaste esta cuenta, ignora este mensaje.\n\n'
                    f'— Caribe Confort Hotel'
                ),
                correo,
            )
        except Exception as e:
            contexto['errores'] = [f'No se pudo enviar el correo: {e}']
            contexto['datos']   = request.POST
            return render(request, 'clientes/registrarcliente.html', contexto)

        contexto['mostrar_modal']  = True
        contexto['correo_destino'] = correo
        return render(request, 'clientes/registrarcliente.html', contexto)

    return render(request, 'clientes/registrarcliente.html', contexto)

def confirmar_codigo(request):

    if request.method != 'POST':
        return redirect('/registrarcliente')

    pendiente = request.session.get('registro_pendiente')
    if not pendiente:
        return redirect('/registrarcliente')

    codigo_ingresado = request.POST.get('codigo', '').strip()

    if codigo_ingresado != pendiente['codigo']:
        contexto = {
            'nacionalidades': NACIONALIDADES,
            'datos':          {},
            'errores':        [],
            'mostrar_modal':  True,
            'error_codigo':   'El código ingresado no es correcto. Inténtalo de nuevo.',
            'correo_destino': pendiente['correo'],
        }
        return render(request, 'clientes/registrarcliente.html', contexto)

    try:
        rol_cliente = Roles.objects.get(nombre='Cliente')
    except Roles.DoesNotExist:
        contexto = {
            'nacionalidades': NACIONALIDADES,
            'datos':          {},
            'errores':        ['El rol "Cliente" no existe. Contacta al administrador.'],
            'mostrar_modal':  False,
        }
        return render(request, 'clientes/registrarcliente.html', contexto)

    with transaction.atomic():
        usuario = Usuarios.objects.create(
            roles      = rol_cliente,
            nombre     = pendiente['nombre'],
            apellido   = pendiente['apellido'],
            correo     = pendiente['correo'],
            contrasena = make_password(pendiente['password']),
            estado     = True,
        )

        Huespedes.objects.create(
            usuarios             = usuario,
            tipodocumento        = pendiente['tipo_doc'],
            identificacion       = pendiente['num_doc'],
            nombres              = pendiente['nombre'],
            apellidos            = pendiente['apellido'],
            telefono             = pendiente['telefono'],
            direccion            = '',
            correo               = pendiente['correo'],
            nacionalidad         = pendiente['nacionalidad'],
            informacionadicional = '',
        )

    del request.session['registro_pendiente']

    messages.success(request, '¡Cuenta creada con éxito! Ya puedes iniciar sesión.')
    return redirect('/login')

def logout_view(request):
    request.session.flush() 
    return redirect('/home')

def hace(fecha):
    """Texto corto en español: hace 12 min / hace 3 h / hace 2 días."""
    seg = int((timezone.now() - fecha).total_seconds())
    if seg < 3600:
        return f'hace {max(seg // 60, 1)} min'
    if seg < 86400:
        return f'hace {seg // 3600} h'
    return f'hace {seg // 86400} d'

def administrador(request):
    if request.session.get('rol') != 'Administrador':
        return redirect('/login')

    finalizar_reservas_vencidas(request, enviar_invitaciones=False)

    hoy = timezone.localdate()
    inicio_mes = hoy.replace(day=1)
    fin_mes_ant = inicio_mes - timedelta(days=1)

    total_habitaciones = Habitaciones.objects.count()
    ocupadas = Habitaciones.objects.filter(estado='Ocupada').count()
    disponibles = Habitaciones.objects.filter(estado='Disponible').count()
    bloqueadas = Habitaciones.objects.filter(estado='Bloqueada').count()

    sin_servicio = Habitaciones.objects.filter(estado='Fuera-de-servicio').count()
    fuera_servicio = sin_servicio


    activas = Reservas.objects.filter(
        estado__in=['Pendiente', 'Pagada - Por validar', 'Confirmada', 'En curso']
    ).count()

    huespedesnumero = Huespedes.objects.count()

    notificaciones_pendientes = Reservas.objects.filter(
        estado='Pagada - Por validar'
    ).count()
    servicios_pendientes_admin = ServicioReserva.objects.filter(
        estado='Pendiente',
        pago__metodopago='Pendiente',
    ).select_related(
        'reservas__huespedes',
        'reservas__habitaciones',
        'servicios',
    ).order_by('fecha')
    notificaciones_servicios = servicios_pendientes_admin.count()

    solicitadas = notificaciones_pendientes

    inicio_dia = timezone.make_aware(
        datetime.combine(hoy, datetime.min.time())
    )
    fin_dia = inicio_dia + timedelta(days=1)
    ayer = inicio_dia - timedelta(days=1)
    ayer_fin = inicio_dia

    del_dia = Reservas.objects.filter(
        fechasolicitud__gte=inicio_dia,
        fechasolicitud__lt=fin_dia
    ).count()

    reservas_hoy = del_dia
    pagosdiarios = Pagos.objects.filter(
        fecha__gte=inicio_dia,
        fecha__lt=fin_dia
    ).exclude(metodopago='Pendiente').aggregate(total=Sum('valor'))['total'] or 0

    pagosdiaanterior = Pagos.objects.filter(
        fecha__gte=ayer,
        fecha__lt=ayer_fin
    ).exclude(metodopago='Pendiente').aggregate(total=Sum('valor'))['total'] or 0

    if pagosdiaanterior == 0:
        hoy_vs_ayer3 = 100 if pagosdiarios > 0 else 0
    else:
        hoy_vs_ayer3 = round(
            ((pagosdiarios - pagosdiaanterior) / pagosdiaanterior) * 100
        )

    ingresos = Pagos.objects.filter(
        fecha__date__gte=inicio_mes,
        fecha__date__lte=hoy
    ).exclude(metodopago='Pendiente').aggregate(total=Sum('valor'))['total'] or 0

    ingresos_ant = Pagos.objects.filter(
        fecha__date__gte=fin_mes_ant.replace(day=1),
        fecha__date__lte=fin_mes_ant
    ).exclude(metodopago='Pendiente').aggregate(total=Sum('valor'))['total'] or 0

    delta = round(
        (ingresos - ingresos_ant) * 100 / ingresos_ant
    ) if ingresos_ant else None

    ocupacion = round(
        ocupadas * 100 / total_habitaciones
    ) if total_habitaciones else 0

    calculo_dona = ocupacion / 100 * 251.2

    inicio_semana = hoy - timedelta(days=hoy.weekday())
    inicio_semana_dt = timezone.make_aware(datetime.combine(inicio_semana, datetime.min.time()))
    fin_semana_dt = inicio_semana_dt + timedelta(days=7)
    ingresos_semanales = Pagos.objects.filter(
        fecha__gte=inicio_semana_dt,
        fecha__lt=fin_semana_dt,
    ).exclude(metodopago='Pendiente').aggregate(total=Sum('valor'))['total'] or 0

    dias_semana = ['L', 'M', 'X', 'J', 'V', 'S', 'D']

    datos_ocupacion_semanal = []

    estados_proyectados = [
        'Confirmada',
        'Pagada - Por validar'
    ]

    for i in range(7):
        dia_actual = inicio_semana + timedelta(days=i)

        reservas_en_curso = Reservas.objects.filter(
            fechaentrada__lte=dia_actual,
            fechasalida__gt=dia_actual,
            estado='En curso',
            habitaciones__isnull=False
        ).aggregate(
            total=Count('habitaciones_id', distinct=True)
        )['total'] or 0

        reservas_proyectadas = Reservas.objects.filter(
            fechaentrada__lte=dia_actual,
            fechasalida__gt=dia_actual,
            estado__in=estados_proyectados,
            habitaciones__isnull=False
        ).aggregate(
            total=Count('habitaciones_id', distinct=True)
        )['total'] or 0

        porcentaje_real = round(
            reservas_en_curso * 100 / total_habitaciones
        ) if total_habitaciones else 0

        porcentaje_proyectado = round(
            reservas_proyectadas * 100 / total_habitaciones
        ) if total_habitaciones else 0

        datos_ocupacion_semanal.append({
            'dia': dias_semana[i],
            'real': min(porcentaje_real, 100),
            'proyectada': min(porcentaje_proyectado, 100)
        })

    recientes = Reservas.objects.select_related(
        'huespedes',
        'habitaciones',
        'planes'
    ).order_by('-fechasolicitud')

    paginator = Paginator(recientes, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    for r in page_obj:
        r.formatted_id = f'CC-{r.id:04d}'

    proximas_reservas = Reservas.objects.filter(
        fechaentrada__gte=hoy,
        estado__in=['Pendiente', 'Pagada - Por validar', 'Confirmada']
    ).select_related(
        'huespedes',
        'habitaciones',
        'planes',
    ).order_by('fechaentrada')

    movs = []

    for r in Reservas.objects.select_related(
        'habitaciones',
        'planes'
    ).order_by('-fechasolicitud')[:3]:

        if r.habitaciones:
            texto = f'Nueva reserva · Hab. {r.habitaciones.numero}'
        elif r.planes:
            texto = f'Nueva reserva · Plan: {r.planes.nombre}'
        else:
            texto = f'Nueva reserva #{r.id}'

        movs.append({
            'texto': texto,
            'fecha': r.fechasolicitud,
            'hace': hace(r.fechasolicitud)
        })

    for p in Pagos.objects.order_by('-fecha')[:3]:

        movs.append({
            'texto': f'Cobro generado · ${formato_numero_colombiano(p.valor, 0)}',
            'fecha': p.fecha,
            'hace': hace(p.fecha)
        })

    movs = sorted(
        movs,
        key=lambda m: m['fecha'],
        reverse=True
    )[:4]

    tipos = TipoHabitacion.objects.annotate(
        n=Count('habitaciones')
    ).order_by('-n')

    servicios_top = [
        {
            'nombre': s['servicios__nombre'],
            'total': s['total']
        }
        for s in ServicioReserva.objects.values(
            'servicios__nombre'
        ).annotate(
            total=Sum('cantidad')
        ).order_by('-total')[:5]
    ]

    banderas = {
        'Colombiana': '🇨🇴',
        'Venezolana': '🇻🇪',
        'Ecuatoriana': '🇪🇨',
        'Peruana': '🇵🇪',
        'Estadounidense': '🇺🇸',
        'Española': '🇪🇸'
    }

    nacionalidades_raw = Huespedes.objects.filter(
        reservas__estado__in=['Confirmada', 'En curso'],
    ).values(
        'nacionalidad'
    ).annotate(
        total=Count('id', distinct=True)
    ).order_by('-total')[:4]

    nacionalidades = []

    for n in nacionalidades_raw:
        nacionalidades.append({
            'nacionalidad': n['nacionalidad'],
            'total': n['total'],
            'bandera': banderas.get(n['nacionalidad'], '🌎')
        })

    meses_es = [
        'Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
        'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'
    ]

    ingresos_meses = []

    for i in range(3, -1, -1):
        mes = hoy.month - i
        anio = hoy.year

        while mes <= 0:
            mes += 12
            anio -= 1

        primer_dia = date(anio, mes, 1)

        if mes == 12:
            ultimo_dia = date(anio, 12, 31)
        else:
            ultimo_dia = date(anio, mes + 1, 1) - timedelta(days=1)

        fecha_final = min(ultimo_dia, hoy) if (
            anio == hoy.year and mes == hoy.month
        ) else ultimo_dia

        inicio_mes_dt = timezone.make_aware(datetime.combine(primer_dia, datetime.min.time()))
        fin_mes_dt = timezone.make_aware(datetime.combine(fecha_final, datetime.max.time()))

        total_mes = Pagos.objects.filter(
            fecha__gte=inicio_mes_dt,
            fecha__lte=fin_mes_dt
        ).exclude(metodopago='Pendiente').aggregate(
            total=Sum('valor')
        )['total'] or 0

        ingresos_meses.append({
            'mes': meses_es[mes - 1],
            'total': total_mes
        })

    max_total = max(
        [m['total'] for m in ingresos_meses]
    ) if any(m['total'] for m in ingresos_meses) else 0

    max_y = math.ceil(max_total / 5000000) * 5000000 if max_total > 0 else 5000000

    def format_monto(val):
        return f"${formato_numero_colombiano(val, 0)}"

    ticks_y = [
        format_monto(max_y),
        format_monto(max_y * 0.75),
        format_monto(max_y * 0.5),
        format_monto(max_y * 0.25),
        '$0'
    ]

    x_points = [70, 356.6, 643.3, 930]
    y_top = 35
    y_bottom = 375
    rango_y = y_bottom - y_top

    puntos = []

    for i, m in enumerate(ingresos_meses):
        total = m['total']

        y = y_bottom - (
            total / max_y * rango_y
        ) if max_y > 0 else y_bottom

        puntos.append({
            'x': x_points[i],
            'y': round(y, 2),
            'x_pct': round(x_points[i] / 1000 * 100, 2),
            'y_pct': round((y / 420) * 100, 2),
            'valor': total,
            'mes': m['mes'],
            'badge': format_monto(total)
        })

    path_linea = f"M {puntos[0]['x']} {puntos[0]['y']}"

    for i in range(1, len(puntos)):
        x0, y0 = puntos[i - 1]['x'], puntos[i - 1]['y']
        x1, y1 = puntos[i]['x'], puntos[i]['y']

        c1_x = x0 + (x1 - x0) / 3
        c2_x = x0 + 2 * (x1 - x0) / 3

        path_linea += (
            f" C {round(c1_x, 2)} {y0}, "
            f"{round(c2_x, 2)} {y1}, {x1} {y1}"
        )

    path_area = (
        path_linea
        + f" L {puntos[-1]['x']} {y_bottom}"
        + f" L {puntos[0]['x']} {y_bottom} Z"
    )

    ingresos_chart = {
        'puntos': puntos,
        'ticks_y': ticks_y,
        'path_linea': path_linea,
        'path_area': path_area
    }

    pagos_hoy = Pagos.objects.filter(
        fecha__gte=inicio_dia, 
        fecha__lt=fin_dia
    ).exclude(metodopago='Pendiente')

    total_pagos_hoy = pagos_hoy.aggregate(t=Sum('valor'))['t'] or 0

    caja_servicios = Pagos.objects.filter(
        concepto='Servicio',
        metodopago__in=['Efectivo', 'Tarjeta', 'Transferencia'],
        fecha__gte=inicio_dia,
        fecha__lt=fin_dia
    ).aggregate(t=Sum('valor'))['t'] or 0

    caja_reservas = total_pagos_hoy - caja_servicios
    caja_total = caja_reservas + caja_servicios

    return render(request, 'admini/dashboard.html', {
        'nombre': request.session.get('usuario_nom', 'Administrador'),
        'rol': request.session.get('rol', 'Administrador'),
        'recientes': recientes,
        'hotel': Hoteles.objects.first(),
        'servicios_top': servicios_top,
        'tipos': tipos,
        'nacionalidades': nacionalidades,
        'ocupadas': ocupadas,
        'disponibles': disponibles,
        'bloqueadas': bloqueadas,
        'total_habitaciones': total_habitaciones,
        'pagosdiarios': pagosdiarios,
        'ingresos_semanales': ingresos_semanales,
        'ocupacion': ocupacion,
        'calculo_dona': calculo_dona,
        'hoy_vs_ayer3': hoy_vs_ayer3,
        'movs': movs,
        'huespedesnumero': huespedesnumero,
        'activas': activas,
        'del_dia': del_dia,
        'notificaciones_pendientes': notificaciones_pendientes,
        'servicios_pendientes': servicios_pendientes_admin[:10],
        'notificaciones_servicios': notificaciones_servicios,
        'reservas_activas': Reservas.objects.filter(
            estado='En curso',
        ).select_related('huespedes', 'habitaciones').order_by('fechaentrada'),
        'servicios_disponibles': Servicios.objects.filter(
            estado=True,
        ).order_by('nombre'),
        'page_obj': page_obj,
        'proximas_reservas': proximas_reservas,
        'proximas_reservas_preview': proximas_reservas[:5],
        'ingresos_chart': ingresos_chart,
        'datos_ocupacion_semanal': datos_ocupacion_semanal,
        'reservas_hoy': reservas_hoy,
        'caja_reservas': caja_reservas,
        'caja_servicios': caja_servicios,
        'caja_total': caja_total,
        'fuera_servicio': fuera_servicio,
        'hoy': hoy,
    })

def reenviar_confirmacion_reserva(request, reserva_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Método no permitido.'}, status=405)
    if request.session.get('rol') not in {'Administrador', 'Recepcionista'}:
        return JsonResponse({'success': False, 'message': 'No autorizado.'}, status=403)

    reserva = Reservas.objects.select_related(
        'huespedes', 'habitaciones', 'planes'
    ).filter(
        id=reserva_id,
        estado='Confirmada',
    ).first()
    if reserva is None:
        return JsonResponse({
            'success': False,
            'message': 'Solo se puede reenviar la confirmación de una reserva aprobada.',
        }, status=404)
    correo_destino = _correo_huesped(reserva.huespedes)
    if not correo_destino:
        return JsonResponse({
            'success': False,
            'message': 'El huésped no tiene un correo válido registrado.',
        }, status=400)

    alojamiento = (
        f'Habitación {reserva.habitaciones.numero}' if reserva.habitaciones_id
        else f'Plan: {reserva.planes.nombre}' if reserva.planes_id
        else 'Reserva general'
    )
    try:
        _enviar_correo_hotel(
            f'Confirmación de reserva CC-{reserva.id:04d}',
            'Tu reserva está confirmada',
            (
                f'Hola {reserva.huespedes.nombres} {reserva.huespedes.apellidos},\n\n'
                f'Tu reserva CC-{reserva.id:04d} está confirmada.\n'
                f'{alojamiento}\n'
                f'Entrada: {reserva.fechaentrada:%d/%m/%Y}\n'
                f'Salida: {reserva.fechasalida:%d/%m/%Y}\n'
                f'Total: ${formato_numero_colombiano(reserva.valortotal, 2)} COP.'
            ),
            correo_destino,
        )
    except Exception:
        logger.exception('No se pudo reenviar la confirmación de la reserva CC-%s.', reserva.id)
        return JsonResponse({
            'success': False,
            'message': 'No se pudo enviar el correo. Revisa la configuración SMTP del hotel.',
        }, status=502)

    return JsonResponse({'success': True, 'message': f'Confirmación enviada a {correo_destino}.'})


def gestionar_reserva(request, reserva_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Método no permitido'}, status=405)

    if request.session.get('rol') not in {'Administrador', 'Recepcionista'}:
        return JsonResponse({'success': False, 'message': 'No autorizado'}, status=403)

    accion = (request.POST.get('accion') or '').strip()
    if accion not in {'aprobar', 'rechazar'}:
        return JsonResponse({'success': False, 'message': 'Acción no válida.'}, status=400)

    try:
        with transaction.atomic():
            reserva = Reservas.objects.select_for_update().filter(id=reserva_id).first()
            if reserva is None:
                return JsonResponse({'success': False, 'message': 'Reserva no encontrada'}, status=404)
            if reserva.estado != 'Pagada - Por validar':
                return JsonResponse({
                    'success': False,
                    'message': 'Esta reserva no está pendiente de validación.',
                }, status=409)

            huesped = reserva.huespedes
            habitacion = reserva.habitaciones if reserva.habitaciones_id else None
            plan = reserva.planes if reserva.planes_id else None
            if accion == 'aprobar':
                reserva.estado = 'Confirmada'
                reserva.save(update_fields=['estado'])
            else:
                reserva.estado = 'Cancelada'
                reserva.save(update_fields=['estado'])
                if habitacion and not Reservas.objects.filter(
                    habitaciones_id=habitacion.id,
                    estado__in=['Pendiente', 'Pagada - Por validar', 'Confirmada', 'En curso'],
                    fechaentrada__lt=reserva.fechasalida,
                    fechasalida__gt=reserva.fechaentrada,
                ).exclude(id=reserva.id).exists():
                    habitacion.estado = 'Disponible'
                    habitacion.save(update_fields=['estado'])
    except Exception:
        logger.exception('No se pudo %s la reserva CC-%s.', accion, reserva_id)
        return JsonResponse({
            'success': False,
            'message': 'No se pudo actualizar la reserva. Revisa el estado actual antes de volver a intentarlo.',
        }, status=500)

    correo_destino = _correo_huesped(huesped)
    detalle = (
        f'Habitación {habitacion.numero}' if habitacion
        else f'Plan: {plan.nombre}' if plan
        else 'Reserva general'
    )
    if habitacion and habitacion.tipohabitacion:
        detalle += f' - {habitacion.tipohabitacion.nombre}'

    if accion == 'aprobar':
        asunto = f'Reserva Confirmada #CC-{reserva.id:04d} - Caribe Confort'
        titulo = 'Tu reserva fue confirmada'
        mensaje = (
            f'Hola {huesped.nombres} {huesped.apellidos},\n\n'
            f'Tu reserva CC-{reserva.id:04d} ha sido confirmada.\n'
            f'{detalle}\n'
            f'Entrada: {reserva.fechaentrada:%d/%m/%Y}\n'
            f'Salida: {reserva.fechasalida:%d/%m/%Y}\n'
            f'Huéspedes: {reserva.cantidadacompañantes}\n'
            f'Total: ${formato_numero_colombiano(reserva.valortotal, 0)} COP.\n\n'
            'Te esperamos en Caribe Confort, Riohacha.'
        )
        accion_texto = 'aprobada'
    else:
        asunto = f'Reserva No Confirmada #CC-{reserva.id:04d} - Caribe Confort'
        titulo = 'No fue posible confirmar tu reserva'
        mensaje = (
            f'Hola {huesped.nombres} {huesped.apellidos},\n\n'
            f'Tu reserva CC-{reserva.id:04d} no pudo ser confirmada y fue cancelada.\n'
            f'{detalle}\n'
            f'Entrada: {reserva.fechaentrada:%d/%m/%Y}\n'
            f'Salida: {reserva.fechasalida:%d/%m/%Y}\n\n'
            'Comunícate con recepción si necesitas ayuda.'
        )
        accion_texto = 'rechazada'

    correo_enviado = False
    if correo_destino:
        try:
            _enviar_correo_hotel(asunto, titulo, mensaje, correo_destino)
            correo_enviado = True
        except Exception:
            logger.exception(
                'La reserva CC-%s fue %s, pero no se pudo enviar el correo.',
                reserva.id,
                accion_texto,
            )
    else:
        logger.warning('No se pudo notificar la reserva CC-%s: huésped sin correo.', reserva.id)

    mensaje_respuesta = f'Reserva {accion_texto}.'
    if correo_enviado:
        mensaje_respuesta += f' Correo enviado a {correo_destino}.'
    else:
        mensaje_respuesta += ' El cambio quedó guardado, pero el correo no se pudo enviar.'
    return JsonResponse({
        'success': True,
        'correo_enviado': correo_enviado,
        'message': mensaje_respuesta,
    })

def recepcionista(request):
    if request.session.get('rol') not in {'Recepcionista', 'Administrador'}:
        return redirect('/login')

    hoy = timezone.localdate()
    llegadas_hoy = list(Reservas.objects.filter(
        fechaentrada=hoy,
        estado='Confirmada',
    ).select_related('huespedes', 'habitaciones', 'planes').order_by('fechaentrada', 'id'))
    salidas_hoy = list(Reservas.objects.filter(
        fechasalida=hoy,
        estado='En curso',
    ).select_related('huespedes', 'habitaciones', 'planes').order_by('fechasalida', 'id'))
    reservas_activas = list(Reservas.objects.filter(
        estado='En curso',
    ).select_related('huespedes', 'habitaciones').order_by('fechaentrada'))

    todas_reservas = llegadas_hoy + salidas_hoy + reservas_activas
    servicios_pendientes = ServicioReserva.objects.filter(
        estado='Pendiente',
        pago__metodopago='Pendiente',
    ).select_related(
        'reservas__huespedes',
        'reservas__habitaciones',
        'servicios',
        'pago',
    ).order_by('fecha')
    ids_reservas = {reserva.id for reserva in todas_reservas}
    pagos_por_reserva = {}
    if ids_reservas:
        pagos_por_reserva = {
            pago['reservas_id']: pago['total']
            for pago in Pagos.objects.filter(
                reservas_id__in=ids_reservas,
            ).exclude(
                metodopago='Pendiente',
            ).values('reservas_id').annotate(total=Sum('valor'))
        }
    for reserva in todas_reservas:
        total_pagado = pagos_por_reserva.get(reserva.id, Decimal('0.00'))
        reserva.saldo_pendiente = max(Decimal('0.00'), reserva.valortotal - total_pagado)

    reservas_hotel = list(Reservas.objects.select_related(
        'huespedes', 'habitaciones', 'planes',
    ).order_by('-fechasolicitud'))
    pagos_reservas = {
        pago['reservas_id']: pago['total'] or Decimal('0.00')
        for pago in Pagos.objects.filter(
            reservas_id__in=[reserva.id for reserva in reservas_hotel],
        ).exclude(
            metodopago='Pendiente',
        ).values('reservas_id').annotate(total=Sum('valor'))
    }
    for reserva in reservas_hotel:
        pagado = pagos_reservas.get(reserva.id, Decimal('0.00'))
        reserva.saldo_favor = max(Decimal('0.00'), pagado - reserva.valortotal)
        reserva.saldo_pendiente = max(Decimal('0.00'), reserva.valortotal - pagado)
    reservas_pendientes_validacion = Reservas.objects.filter(
        estado='Pagada - Por validar',
    ).count()
    return render(request, 'recepcion/dashboard.html', {
        'llegadas_hoy': llegadas_hoy,
        'salidas_hoy': salidas_hoy,
        'reservas_activas': reservas_activas,
        'reservas_hotel': reservas_hotel,
        'total_reservas': len(reservas_hotel),
        'servicios_pendientes': servicios_pendientes,
        'notificaciones_pendientes': reservas_pendientes_validacion,
        'notificaciones_servicios': servicios_pendientes.count(),
        'huespedes': Huespedes.objects.order_by('apellidos', 'nombres'),
        'habitaciones_disponibles': Habitaciones.objects.filter(
            estado='Disponible',
        ).select_related('tipohabitacion').order_by('numero'),
        'servicios_disponibles': Servicios.objects.filter(estado=True).order_by('nombre'),
        'hoy': hoy,
        'manana': hoy + timedelta(days=1),
        'nombre': request.session.get('usuario_nom', 'Recepcionista'),
        'rol': request.session.get('rol'),
    })


def servicios_pendientes_recepcion(request):
    if request.session.get('rol') not in {'Recepcionista', 'Administrador'}:
        return redirect('/login')
    servicios_pendientes = ServicioReserva.objects.filter(
        estado='Pendiente',
        pago__metodopago='Pendiente',
    ).select_related(
        'reservas__huespedes',
        'reservas__habitaciones',
        'servicios',
        'pago',
    ).order_by('fecha')
    fecha_limite_servicios = timezone.now() - timedelta(days=3)
    servicios_recientes = list(ServicioReserva.objects.filter(
        fecha__gte=fecha_limite_servicios,
    ).select_related(
        'reservas__huespedes__usuarios',
        'reservas__habitaciones',
        'servicios',
        'pago',
    ).order_by('-fecha'))
    ids_pagos_servicio = [item.pago_id for item in servicios_recientes if item.pago_id]
    reembolsos_servicio = {
        fila['pago_origen_id']: fila['total'] or Decimal('0.00')
        for fila in Pagos.objects.filter(
            concepto='Reembolso', pago_origen_id__in=ids_pagos_servicio,
        ).values('pago_origen_id').annotate(total=Sum('valor'))
    }
    ids_reservas_servicio = {item.reservas_id for item in servicios_recientes}
    pagos_netos_reserva = {
        fila['reservas_id']: fila['total'] or Decimal('0.00')
        for fila in Pagos.objects.filter(reservas_id__in=ids_reservas_servicio)
        .exclude(metodopago='Pendiente')
        .values('reservas_id').annotate(total=Sum('valor'))
    }
    for item in servicios_recientes:
        item.correo_huesped = _correo_huesped(item.reservas.huespedes)
        item.metodo_pago_registrado = item.pago.metodopago if item.pago_id else ''
        item.reembolso_disponible = Decimal('0.00')
        item.reembolso_realizado = Decimal('0.00')
        if item.estado == 'Aprobado' and item.pago_id and item.pago.valor > 0:
            reembolsado = reembolsos_servicio.get(item.pago_id, Decimal('0.00'))
            item.reembolso_realizado = abs(reembolsado)
            item.reembolso_disponible = min(
                max(Decimal('0.00'), item.pago.valor + reembolsado),
                max(Decimal('0.00'), pagos_netos_reserva.get(item.reservas_id, Decimal('0.00'))),
            )
    return render(request, 'recepcion/servicios_pendientes.html', {
        'servicios_pendientes': servicios_pendientes,
        'servicios_recientes': servicios_recientes,
        'servicios_disponibles': Servicios.objects.filter(estado=True).order_by('nombre'),
        'reservas_para_servicio': Reservas.objects.filter(
            estado__in=['Pendiente', 'Pagada - Por validar', 'Confirmada', 'En curso'],
        ).select_related('huespedes', 'habitaciones').order_by('-fechaentrada'),
        'notificaciones_pendientes': Reservas.objects.filter(estado='Pagada - Por validar').count(),
        'notificaciones_servicios': servicios_pendientes.count(),
        'nombre': request.session.get('usuario_nom', 'Recepcionista'),
        'rol': request.session.get('rol'),
    })


def aprobar_servicio_recepcion(request, servicio_reserva_id):
    if request.session.get('rol') not in {'Recepcionista', 'Administrador'}:
        return redirect('/login')
    destino = request.POST.get('next', '/recepcion/servicios-pendientes')
    destinos_permitidos = {'/administrador', '/recepcion', '/recepcion/servicios-pendientes'}
    if request.session.get('rol') == 'Administrador':
        destinos_permitidos.add('/adminservicios')
    if destino not in destinos_permitidos:
        destino = '/recepcion/servicios-pendientes'
    if request.method != 'POST':
        return redirect(destino)

    accion = request.POST.get('accion', 'aprobar').strip()
    if accion not in {'aprobar', 'rechazar'}:
        messages.error(request, 'La acción seleccionada no es válida.')
        return redirect(destino)
    metodo = request.POST.get('metodopago', '').strip()
    codigo_motivo = request.POST.get('motivo_rechazo', '').strip()
    detalle_motivo = request.POST.get('motivo_detalle', '').strip()
    motivo = ''
    if accion == 'aprobar' and metodo not in {'Efectivo', 'Tarjeta', 'Transferencia', 'Nequi'}:
        messages.error(request, 'Selecciona un método de pago válido.')
        return redirect(destino)
    if accion == 'rechazar':
        if codigo_motivo == 'otro':
            if not detalle_motivo or len(detalle_motivo) > 500:
                messages.error(request, 'Escribe el motivo específico del rechazo (máximo 500 caracteres).')
                return redirect(destino)
            motivo = detalle_motivo
        elif codigo_motivo in MOTIVOS_RECHAZO_SERVICIO:
            motivo = MOTIVOS_RECHAZO_SERVICIO[codigo_motivo]
        else:
            messages.error(request, 'Selecciona un motivo válido para rechazar la solicitud.')
            return redirect(destino)

    with transaction.atomic():
        servicio_reserva = get_object_or_404(
            ServicioReserva.objects.select_for_update().select_related(
                'reservas__huespedes',
                'servicios',
            ),
            id=servicio_reserva_id,
        )
        if servicio_reserva.estado != 'Pendiente':
            messages.error(request, 'Esta solicitud de servicio ya fue procesada.')
            return redirect(destino)
        if not servicio_reserva.pago_id:
            messages.error(request, 'Este servicio no tiene un pago asociado para validar.')
            return redirect(destino)
        pago = Pagos.objects.select_for_update().filter(
            id=servicio_reserva.pago_id,
            reservas=servicio_reserva.reservas,
            metodopago='Pendiente',
        ).first()
        if not pago:
            messages.error(request, 'El pago del servicio ya fue procesado o no existe.')
            return redirect(destino)

        reserva = Reservas.objects.select_for_update().get(id=servicio_reserva.reservas_id)
        if accion == 'aprobar':
            reserva.valortotal += servicio_reserva.valor
            reserva.save(update_fields=['valortotal'])
            pago.metodopago = metodo
            pago.concepto = 'Servicio'
            pago.fecha = timezone.now()
            pago.save(update_fields=['metodopago', 'concepto', 'fecha'])
            servicio_reserva.estado = 'Aprobado'
            servicio_reserva.save(update_fields=['estado'])
        else:
            pago.delete()
            servicio_reserva.pago = None
            servicio_reserva.estado = 'Rechazado'
            servicio_reserva.motivo_rechazo = motivo
            servicio_reserva.save(update_fields=['pago', 'estado', 'motivo_rechazo'])

    huesped = servicio_reserva.reservas.huespedes
    correo_destino = huesped.correo or (
        huesped.usuarios.correo if huesped.usuarios_id else ''
    )
    if correo_destino:
        try:
            if accion == 'aprobar':
                _enviar_correo_hotel(
                    'Servicio aprobado y cobrado',
                    'Tu servicio fue aprobado',
                    (
                        f'Hola {huesped.nombres},\n\n'
                        f'Usted solicitó {servicio_reserva.servicios.nombre}, por un valor de '
                        f'${formato_numero_colombiano(servicio_reserva.valor, 2)} COP. Ha sido aprobado y cargado a su cuenta.\n'
                        f'Reserva: CC-{servicio_reserva.reservas_id:04d}.\n'
                        f'Método de pago registrado: {metodo}.'
                    ),
                    correo_destino,
                )
            else:
                _enviar_correo_hotel(
                    'Actualización de tu solicitud de servicio',
                    'Tu solicitud no pudo ser aprobada',
                    (
                        f'Hola {huesped.nombres},\n\n'
                        f'La solicitud de {servicio_reserva.servicios.nombre} para la reserva '
                        f'CC-{servicio_reserva.reservas_id:04d} fue rechazada.\n'
                        f'Motivo: {motivo}\n\n'
                        'El importe no fue cobrado; por tanto, no hay una devolución bancaria pendiente.'
                    ),
                    correo_destino,
                )
        except Exception:
            logger.exception(
                'No se pudo enviar el correo de %s del servicio reservado %s.',
                accion,
                servicio_reserva.id,
            )
            messages.warning(request, 'La solicitud se procesó, pero no se pudo enviar el correo al huésped.')
        else:
            messages.success(
                request,
                f'Servicio {servicio_reserva.servicios.nombre} '
                f'{"aprobado y cobrado" if accion == "aprobar" else "rechazado sin cargo"}; correo enviado.',
            )
    else:
        logger.warning(
            'No se envió el correo de %s del servicio reservado %s: huésped sin correo.',
            accion,
            servicio_reserva.id,
        )
        messages.warning(request, 'La solicitud se procesó, pero el huésped no tiene correo registrado.')
    return redirect(destino)


def registrar_solicitud_servicio_recepcion(request):
    if request.session.get('rol') not in {'Recepcionista', 'Administrador'}:
        return redirect('/login')
    if request.method != 'POST':
        return redirect('/recepcion/servicios-pendientes')

    try:
        reserva_id = int(request.POST.get('reserva_id', ''))
        servicio_id = int(request.POST.get('servicio_id', ''))
        cantidad = int(request.POST.get('cantidad', '1'))
    except (TypeError, ValueError):
        messages.error(request, 'Selecciona una reserva, un servicio y una cantidad válidos.')
        return redirect('/recepcion/servicios-pendientes')
    beneficiario = request.POST.get('beneficiario', '').strip()
    beneficiario_segundo = request.POST.get('beneficiario_segundo', '').strip()
    metodo_pago_preferido = request.POST.get('metodo_pago_preferido', '').strip()
    if metodo_pago_preferido not in {'Efectivo', 'Tarjeta', 'Transferencia', 'Nequi'}:
        messages.error(request, 'Selecciona un tipo de pago válido.')
        return redirect('/recepcion/servicios-pendientes')
    if not beneficiario or len(beneficiario) > 100 or len(beneficiario_segundo) > 100:
        messages.error(request, 'Indica un beneficiario válido (máximo 100 caracteres).')
        return redirect('/recepcion/servicios-pendientes')
    if cantidad < 1 or cantidad > 50:
        messages.error(request, 'La cantidad debe estar entre 1 y 50.')
        return redirect('/recepcion/servicios-pendientes')

    servicio = Servicios.objects.filter(id=servicio_id, estado=True).first()
    if not servicio:
        messages.error(request, 'El servicio seleccionado no está disponible.')
        return redirect('/recepcion/servicios-pendientes')
    valor_total = (servicio.precio * cantidad).quantize(Decimal('0.01'))
    if valor_total <= 0 or valor_total > Decimal('99999999.99'):
        messages.error(request, 'El valor total del servicio excede el límite permitido.')
        return redirect('/recepcion/servicios-pendientes')
    try:
        with transaction.atomic():
            reserva = Reservas.objects.select_for_update().select_related('huespedes').get(
                id=reserva_id,
                estado__in=['Pendiente', 'Pagada - Por validar', 'Confirmada', 'En curso'],
            )
            solicitud = ServicioReserva.objects.create(
                reservas=reserva,
                servicios=servicio,
                cantidad=cantidad,
                valor=valor_total,
                solicitado_por=(request.session.get('usuario_nom') or 'Recepción')[:100],
                beneficiario=beneficiario,
                beneficiario_segundo=beneficiario_segundo,
                metodo_pago_preferido=metodo_pago_preferido,
                estado='Pendiente',
            )
            pago = Pagos.objects.create(
                reservas=reserva,
                valor=valor_total,
                metodopago='Pendiente',
                concepto='Servicio',
            )
            solicitud.pago = pago
            solicitud.save(update_fields=['pago'])
    except Reservas.DoesNotExist:
        messages.error(request, 'La reserva seleccionada no existe o ya no admite servicios.')
        return redirect('/recepcion/servicios-pendientes')

    correo_destino = _correo_huesped(reserva.huespedes)
    if correo_destino:
        try:
            _enviar_correo_hotel(
                'Solicitud de servicio recibida',
                'Recibimos tu solicitud',
                (
                    f'Hola {reserva.huespedes.nombres},\n\n'
                    f'Recepción registró una solicitud de {servicio.nombre} para la reserva '
                    f'CC-{reserva.id:04d}.\nCantidad: {cantidad}\n'
                    f'Beneficiario(s): {beneficiario}'
                    + (f' y {beneficiario_segundo}' if beneficiario_segundo else '')
                    + f'\nMétodo de pago preferido: {metodo_pago_preferido}'
                    + f'\nValor: ${formato_numero_colombiano(valor_total, 2)} COP.\n\n'
                    'La solicitud está pendiente de aprobación y registro del pago.'
                ),
                correo_destino,
            )
        except Exception:
            logger.exception('No se pudo enviar el aviso de la solicitud manual %s.', solicitud.id)
            messages.warning(request, f'Solicitud de {servicio.nombre} registrada y pendiente, pero no se pudo enviar el correo al huésped.')
        else:
            messages.success(request, f'Solicitud de {servicio.nombre} registrada para la reserva CC-{reserva.id:04d}; quedó pendiente y se notificó al huésped.')
    else:
        messages.warning(request, f'Solicitud registrada para la reserva CC-{reserva.id:04d}, pero el huésped no tiene correo registrado.')
    return redirect('/recepcion/servicios-pendientes')


def registrar_huesped_recepcion(request):
    if request.session.get('rol') not in {'Recepcionista', 'Administrador'}:
        return redirect('/login')
    if request.method != 'POST':
        return redirect('/recepcion')

    datos = {
        'tipodocumento': request.POST.get('tipodocumento', '').strip(),
        'identificacion': request.POST.get('identificacion', '').strip(),
        'nombres': request.POST.get('nombres', '').strip(),
        'apellidos': request.POST.get('apellidos', '').strip(),
        'telefono': request.POST.get('telefono', '').strip(),
        'direccion': request.POST.get('direccion', '').strip(),
        'correo': request.POST.get('correo', '').strip() or None,
        'nacionalidad': request.POST.get('nacionalidad', '').strip(),
    }
    if datos['tipodocumento'] not in {'CC', 'CE', 'Pasaporte', 'TI'}:
        messages.error(request, 'Selecciona un tipo de documento válido.')
        return redirect('/recepcion')
    if not all(datos[campo] for campo in (
        'identificacion', 'nombres', 'apellidos', 'telefono', 'direccion', 'nacionalidad',
    )):
        messages.error(request, 'Completa todos los datos obligatorios del huésped.')
        return redirect('/recepcion')
    limites = {
        'identificacion': 50, 'nombres': 100, 'apellidos': 100,
        'telefono': 100, 'direccion': 100, 'correo': 100, 'nacionalidad': 100,
    }
    if any(len(valor) > limites[campo] for campo, valor in datos.items() if valor is not None):
        messages.error(request, 'Revisa la longitud de los datos ingresados.')
        return redirect('/recepcion')
    if datos['correo']:
        try:
            validate_email(datos['correo'])
        except ValidationError:
            messages.error(request, 'Ingresa un correo electrónico válido.')
            return redirect('/recepcion')
    if Huespedes.objects.filter(identificacion=datos['identificacion']).exists():
        messages.error(request, 'Ya existe un huésped con ese documento; sus datos no se modificaron.')
        return redirect('/recepcion')

    try:
        Huespedes.objects.create(**datos)
    except IntegrityError:
        messages.error(request, 'No se pudo registrar el huésped. Verifica si el documento ya está registrado.')
        return redirect('/recepcion')
    messages.success(request, 'Huésped registrado correctamente.')
    return redirect('/recepcion')


def crear_reserva_recepcion(request):
    if request.session.get('rol') not in {'Recepcionista', 'Administrador'}:
        return redirect('/login')
    if request.method != 'POST':
        return redirect('/recepcion')

    try:
        huesped_id = int(request.POST.get('huesped_id', ''))
        habitacion_id = int(request.POST.get('habitacion_id', ''))
        cantidad_huespedes = int(request.POST.get('cantidad_huespedes', ''))
        fecha_entrada = date.fromisoformat(request.POST.get('fechaentrada', ''))
        fecha_salida = date.fromisoformat(request.POST.get('fechasalida', ''))
    except (TypeError, ValueError):
        messages.error(request, 'Completa huésped, habitación, cantidad y fechas válidas.')
        return redirect('/recepcion')
    try:
        monto_pagado = Decimal(request.POST.get('monto_pagado', '0').strip() or '0').quantize(Decimal('0.01'))
    except (InvalidOperation, AttributeError):
        messages.error(request, 'Ingresa un monto inicial válido.')
        return redirect('/recepcion')
    metodo_pago = request.POST.get('metodopago', '').strip()
    nombres_acompanantes = [valor.strip() for valor in request.POST.getlist('acompanante_nombre[]')]
    documentos_acompanantes = [valor.strip() for valor in request.POST.getlist('acompanante_documento[]')]
    parentescos_acompanantes = [valor.strip() for valor in request.POST.getlist('acompanante_parentesco[]')]

    hoy = timezone.localdate()
    if fecha_entrada < hoy or fecha_salida <= fecha_entrada:
        messages.error(request, 'La entrada no puede ser anterior a hoy y la salida debe ser posterior.')
        return redirect('/recepcion')
    if cantidad_huespedes < 1:
        messages.error(request, 'La reserva debe incluir al menos un huésped.')
        return redirect('/recepcion')
    acompanantes_esperados = cantidad_huespedes - 1
    if len(nombres_acompanantes) != acompanantes_esperados or len(documentos_acompanantes) != acompanantes_esperados:
        messages.error(request, 'Registra el nombre y documento de cada acompañante.')
        return redirect('/recepcion')
    if parentescos_acompanantes and len(parentescos_acompanantes) != acompanantes_esperados:
        messages.error(request, 'Revisa el parentesco de cada acompañante.')
        return redirect('/recepcion')
    if any(not nombre or len(nombre) > 200 for nombre in nombres_acompanantes):
        messages.error(request, 'Los nombres de acompañantes son obligatorios y no pueden superar 200 caracteres.')
        return redirect('/recepcion')
    if any(not documento or len(documento) > 50 for documento in documentos_acompanantes):
        messages.error(request, 'Los documentos de acompañantes son obligatorios y no pueden superar 50 caracteres.')
        return redirect('/recepcion')
    if any(len(parentesco) > 50 for parentesco in parentescos_acompanantes):
        messages.error(request, 'El parentesco no puede superar 50 caracteres.')
        return redirect('/recepcion')
    if not monto_pagado.is_finite() or monto_pagado < 0:
        messages.error(request, 'El monto inicial no puede ser negativo.')
        return redirect('/recepcion')
    if monto_pagado > 0 and metodo_pago not in {'Efectivo', 'Tarjeta', 'Transferencia'}:
        messages.error(request, 'Selecciona un método de pago válido para el monto inicial.')
        return redirect('/recepcion')

    with transaction.atomic():
        huesped = Huespedes.objects.filter(id=huesped_id).first()
        habitacion = Habitaciones.objects.select_for_update().filter(
            id=habitacion_id,
            estado='Disponible',
        ).first()
        if not huesped or not habitacion:
            messages.error(request, 'El huésped o la habitación seleccionados ya no están disponibles.')
            return redirect('/recepcion')
        if cantidad_huespedes > habitacion.capacidad:
            messages.error(request, f'La habitación {habitacion.numero} tiene capacidad máxima para {habitacion.capacidad} huéspedes.')
            return redirect('/recepcion')
        if Reservas.objects.filter(
            habitaciones=habitacion,
            estado__in=['Pendiente', 'Pagada - Por validar', 'Confirmada', 'En curso'],
            fechaentrada__lt=fecha_salida,
            fechasalida__gt=fecha_entrada,
        ).exists():
            messages.error(request, 'La habitación ya tiene una reserva para esas fechas.')
            return redirect('/recepcion')

        noches = (fecha_salida - fecha_entrada).days
        valor_total = (habitacion.precio * noches).quantize(Decimal('0.01'))
        regla_estancia = _regla_descuento_estancia(noches)
        if regla_estancia:
            valor_total = (
                valor_total * (Decimal('100') - regla_estancia.porcentaje) / Decimal('100')
            ).quantize(Decimal('0.01'))
        if monto_pagado > valor_total:
            messages.error(request, 'El pago inicial no puede superar el total de la reserva.')
            return redirect('/recepcion')
        reserva = Reservas.objects.create(
            huespedes=huesped,
            habitaciones=habitacion,
            fechaentrada=fecha_entrada,
            fechasalida=fecha_salida,
            cantidadacompañantes=cantidad_huespedes,
            estado='Confirmada',
            valortotal=valor_total,
        )
        Acompanante.objects.bulk_create([
            Acompanante(
                reserva=reserva,
                nombre_completo=nombre,
                documento=documento,
                parentesco=parentescos_acompanantes[indice] if indice < len(parentescos_acompanantes) else '',
            )
            for indice, (nombre, documento) in enumerate(zip(nombres_acompanantes, documentos_acompanantes))
        ])
        if monto_pagado > 0:
            Pagos.objects.create(
                reservas=reserva,
                valor=monto_pagado,
                metodopago=metodo_pago,
                concepto='Reserva',
            )
    mensaje = (
        f'Reserva CC-{reserva.id:04d} creada para {huesped.nombres} {huesped.apellidos}.'
        + _enviar_confirmacion_reserva(reserva)
    )
    messages.success(request, mensaje)
    return redirect('/recepcion')


def registrar_pago_servicio_recepcion(request):
    if request.session.get('rol') not in {'Recepcionista', 'Administrador'}:
        return redirect('/login')
    destino = '/administrador' if request.session.get('rol') == 'Administrador' else '/recepcion'
    if request.method != 'POST':
        return redirect(destino)

    accion = request.POST.get('accion', '')
    try:
        reserva_id = int(request.POST.get('reserva_id', ''))
    except (TypeError, ValueError):
        messages.error(request, 'Selecciona una reserva válida.')
        return redirect(destino)

    metodos = {'Efectivo', 'Tarjeta', 'Transferencia', 'Nequi'}
    with transaction.atomic():
        reserva = Reservas.objects.select_for_update().filter(id=reserva_id).first()
        if not reserva or reserva.estado not in {'Pendiente', 'Pagada - Por validar', 'Confirmada', 'En curso'}:
            messages.error(request, 'La reserva no existe o no acepta pagos ni servicios.')
            return redirect(destino)

        if accion == 'pago':
            try:
                monto = Decimal(request.POST.get('valor', '').strip())
                if not monto.is_finite():
                    raise InvalidOperation
                monto = monto.quantize(Decimal('0.01'))
            except (InvalidOperation, AttributeError):
                messages.error(request, 'Ingresa un monto válido.')
                return redirect(destino)
            metodo = request.POST.get('metodopago', '')
            pagado = Pagos.objects.filter(reservas=reserva).exclude(
                metodopago='Pendiente',
            ).aggregate(total=Sum('valor'))['total'] or Decimal('0.00')
            saldo = max(Decimal('0.00'), reserva.valortotal - pagado)
            if monto <= 0 or monto > saldo or metodo not in metodos:
                messages.error(request, 'Verifica el monto pendiente y el método de pago.')
                return redirect(destino)
            Pagos.objects.create(reservas=reserva, valor=monto, metodopago=metodo, concepto='Reserva')
            if reserva.estado == 'Pendiente':
                reserva.estado = 'Pagada - Por validar'
                reserva.save(update_fields=['estado'])
            messages.success(request, f'Pago de ${formato_numero_colombiano(monto, 2)} registrado para la reserva CC-{reserva.id:04d}.')
        elif accion == 'servicio':
            if reserva.estado != 'En curso':
                messages.error(request, 'Solo se pueden agregar servicios a una estadía en curso.')
                return redirect(destino)
            try:
                cantidad = int(request.POST.get('cantidad', ''))
                servicio_id = int(request.POST.get('servicio_id', ''))
            except (TypeError, ValueError):
                messages.error(request, 'Selecciona un servicio y una cantidad válida.')
                return redirect(destino)
            servicio = Servicios.objects.filter(id=servicio_id, estado=True).first()
            if not servicio or cantidad < 1 or cantidad > 50:
                messages.error(request, 'El servicio o la cantidad seleccionados no son válidos.')
                return redirect(destino)
            estado = request.POST.get('estado', 'Pendiente').strip()
            if estado not in {'Pendiente', 'Aprobado', 'Rechazado'}:
                messages.error(request, 'Selecciona un estado válido para el servicio.')
                return redirect(destino)
            metodo_servicio = request.POST.get('metodo_pago_servicio', '').strip()
            if metodo_servicio and metodo_servicio not in metodos:
                messages.error(request, 'Selecciona un método de pago válido para el servicio.')
                return redirect(destino)
            try:
                valor_ingresado = request.POST.get('valor', '').strip()
                valor_total = (
                    Decimal(valor_ingresado).quantize(Decimal('0.01'))
                    if valor_ingresado else
                    (servicio.precio * cantidad).quantize(Decimal('0.01'))
                )
                if not valor_total.is_finite():
                    raise InvalidOperation
            except (InvalidOperation, AttributeError):
                messages.error(request, 'Ingresa un valor válido para el servicio.')
                return redirect(destino)
            beneficiario = request.POST.get('beneficiario', '').strip()
            beneficiario_segundo = request.POST.get('beneficiario_segundo', '').strip()
            motivo_rechazo = request.POST.get('motivo_rechazo', '').strip()
            if (
                not beneficiario
                or len(beneficiario) > 100
                or len(beneficiario_segundo) > 100
                or valor_total <= 0
                or valor_total > Decimal('99999999.99')
            ):
                messages.error(request, 'Verifica beneficiarios y valor del servicio.')
                return redirect(destino)
            if estado == 'Aprobado' and metodo_servicio not in metodos:
                messages.error(request, 'Selecciona el método recibido para aprobar el servicio.')
                return redirect(destino)
            if estado == 'Rechazado' and (not motivo_rechazo or len(motivo_rechazo) > 500):
                messages.error(request, 'Indica el motivo del rechazo (máximo 500 caracteres).')
                return redirect(destino)
            servicio_reserva = ServicioReserva.objects.create(
                reservas=reserva,
                servicios=servicio,
                cantidad=cantidad,
                valor=valor_total,
                solicitado_por=(request.session.get('usuario_nom') or 'Registro manual')[:100],
                beneficiario=beneficiario,
                beneficiario_segundo=beneficiario_segundo,
                motivo_rechazo=motivo_rechazo if estado == 'Rechazado' else '',
                metodo_pago_preferido=metodo_servicio,
                estado=estado,
            )
            if estado != 'Rechazado':
                if estado == 'Aprobado':
                    reserva.valortotal += valor_total
                    reserva.save(update_fields=['valortotal'])
                pago = Pagos.objects.create(
                    reservas=reserva,
                    valor=valor_total,
                    metodopago=metodo_servicio if estado == 'Aprobado' else 'Pendiente',
                    concepto='Servicio',
                )
                servicio_reserva.pago = pago
                servicio_reserva.save(update_fields=['pago'])
            messages.success(request, f'{servicio.nombre} registrado para la reserva CC-{reserva.id:04d}.')
        else:
            messages.error(request, 'Selecciona si deseas registrar un pago o un servicio.')
            return redirect(destino)
    return redirect(destino)
