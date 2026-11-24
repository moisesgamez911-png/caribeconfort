import json
from contextlib import nullcontext
from datetime import timedelta
from decimal import Decimal
from io import BytesIO, StringIO
from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from cryptography.fernet import Fernet
from PIL import Image
from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import OperationalError
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from openpyxl import load_workbook

from caribeconfort.context_processors import identidad_hotel, notificaciones_administracion
from caribeconfort.models import (
    CategoriaGaleria,
    CaracteristicaPlan,
    Habitaciones,
    Huespedes,
    Hoteles,
    ImagenGaleria,
    Pagos,
    Planes,
    Reservas,
    Resena,
    Roles,
    ServicioReserva,
    Servicios,
    TipoHabitacion,
    Usuarios,
)
from caribeconfort.views import (
    _cifrar_contrasena_smtp,
    _descifrar_contrasena_smtp,
    _conexion_correo_hotel,
    _enviar_invitacion_resena,
    _enviar_correo_hotel,
    buscar_disponibilidad,
    administrador,
    cancelar_reserva,
    checkout_reserva,
    configuracionadmin,
    descargar_certificado_pagos,
    descargar_factura_reserva,
    dejar_resena,
    finalizar_reservas_vencidas,
    galeria,
    galeriaadmin,
    home,
    mis_reservas,
    procesar_reembolso,
    modificar_reserva,
    recepcionista,
    reservasadmin,
    servir_logo_hotel,
    _url_imagen_local,
    solicitar_servicio,
)


def crear_huesped_prueba(cuenta=True):
    usuario = None
    correo = f'guest-{uuid4().hex}@example.com'
    if cuenta:
        rol = Roles.objects.create(nombre='Cliente')
        usuario = Usuarios.objects.create(
            roles=rol,
            nombre='Ana',
            apellido='Huésped',
            correo=correo,
            contrasena='password-de-prueba',
        )
    return Huespedes.objects.create(
        usuarios=usuario,
        tipodocumento='CC',
        identificacion=uuid4().hex[:20],
        nombres='Ana',
        apellidos='Huésped',
        telefono='3000000000',
        direccion='Calle 1',
        correo=correo,
        nacionalidad='Colombiana',
    )


def crear_reserva_prueba(huesped, fechaentrada=None):
    entrada = fechaentrada or timezone.localdate() + timedelta(days=10)
    return Reservas.objects.create(
        huespedes=huesped,
        fechaentrada=entrada,
        fechasalida=entrada + timedelta(days=2),
        cantidadacompañantes=1,
        estado='Confirmada',
        valortotal=Decimal('100.00'),
    )


class LocalImageURLTests(SimpleTestCase):
    def test_missing_uploaded_image_uses_existing_legacy_static_file(self):
        with TemporaryDirectory() as media_root, TemporaryDirectory() as static_root:
            ruta = 'uploads/servicios/imagen.jpg'
            archivo_legado = Path(static_root) / 'img' / 'imagenes' / ruta
            archivo_legado.parent.mkdir(parents=True)
            archivo_legado.touch()

            with override_settings(
                MEDIA_ROOT=media_root,
                STATICFILES_DIRS=[static_root],
                STATIC_URL='/static/',
                MEDIA_URL='/media/',
            ):
                self.assertEqual(
                    _url_imagen_local(ruta),
                    '/static/img/imagenes/uploads/servicios/imagen.jpg',
                )

    def test_missing_uploaded_image_returns_no_url(self):
        with TemporaryDirectory() as media_root, TemporaryDirectory() as static_root:
            with override_settings(
                MEDIA_ROOT=media_root,
                STATICFILES_DIRS=[static_root],
                STATIC_URL='/static/',
                MEDIA_URL='/media/',
            ):
                self.assertEqual(
                    _url_imagen_local('uploads/servicios/eliminada.jpg'),
                    '',
                )


class ReservationCancellationTests(TestCase):
                def test_customer_cancellation_uses_csrf_cookie_from_reservations_page(self):
                    huesped = crear_huesped_prueba()
                    reserva = crear_reserva_prueba(huesped)
                    client = Client(enforce_csrf_checks=True)
                    session = client.session
                    session['usuario_id'] = huesped.usuarios_id
                    session['rol'] = 'Cliente'
                    session.save()

                    page = client.get('/mis-reservas')

                    self.assertEqual(page.status_code, 200)
                    self.assertIn('csrftoken', page.cookies)
                    token = page.cookies['csrftoken'].value
                    with patch('caribeconfort.views._enviar_correo_hotel', return_value=True):
                        response = client.post(
                            f'/api/cancelar-reserva/{reserva.id}/',
                            data='{}',
                            content_type='application/json',
                            HTTP_X_CSRFTOKEN=token,
                            HTTP_X_SESSION_SCOPE='cliente',
                        )

                    self.assertEqual(response.status_code, 200)
                    self.assertTrue(response.json()['success'])
                    reserva.refresh_from_db()
                    self.assertEqual(reserva.estado, 'Cancelada')


class ReservationRejectionTests(TestCase):
    def test_rejection_voids_unconfirmed_payment_without_refund_and_emails_guest(self):
        huesped = crear_huesped_prueba()
        reserva = crear_reserva_prueba(huesped)
        reserva.estado = 'Pagada - Por validar'
        reserva.save(update_fields=['estado'])
        pago = Pagos.objects.create(
            reservas=reserva,
            valor=Decimal('100.00'),
            metodopago='Transferencia',
            concepto='Reserva',
            estado_pago='Pendiente',
        )
        session = self.client.session
        session['rol'] = 'Administrador'
        session['usuario_nom'] = 'Admin de prueba'
        session.save()

        with patch('caribeconfort.views._enviar_correo_hotel', return_value=1) as enviar_correo:
            response = self.client.post(
                f'/gestionar-reserva/{reserva.id}/',
                {'accion': 'rechazar'},
                HTTP_X_SESSION_SCOPE='admin',
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['correo_enviado'])
        reserva.refresh_from_db()
        pago.refresh_from_db()
        self.assertEqual(reserva.estado, 'Cancelada')
        self.assertEqual(pago.estado_pago, 'Anulado')
        self.assertFalse(Pagos.objects.filter(
            reservas=reserva,
            concepto='Reembolso',
        ).exists())
        self.assertIn('no se realizó ningún cobro', enviar_correo.call_args.args[2].lower())
        self.assertContains(self.client.get('/adminpagos?tab=reservas'), 'Anulado')


class GalleryAdminPageTests(TestCase):
    def test_existing_gallery_list_is_separated_and_collapsed_by_default(self):
                    client = Client()
                    session = client.session
                    session['rol'] = 'Administrador'
                    session['usuario_nom'] = 'Admin'
                    session.save()

                    response = client.get('/admingaleria')

                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, 'Ver galerías existentes')
                    self.assertContains(response, 'class="adm-gallery-details"')
                    self.assertNotContains(response, 'class="adm-gallery-details" open')


class StaffAccountEditTests(TestCase):
    def setUp(self):
        self.admin_role = Roles.objects.create(nombre='Administrador')
        self.reception_role = Roles.objects.create(nombre='Recepcionista')
        self.client_role = Roles.objects.create(nombre='Cliente')
        self.admin = Usuarios.objects.create(
            roles=self.admin_role,
            nombre='Admin',
            apellido='Hotel',
            correo='admin@example.com',
            contrasena='admin-password',
        )
        self.staff = Usuarios.objects.create(
            roles=self.reception_role,
            nombre='Rosa',
            apellido='Recepción',
            correo='rosa@example.com',
            contrasena='password-anterior',
        )
        session = self.client.session
        session['rol'] = 'Administrador'
        session['usuario_id'] = self.admin.id
        session['usuario_nom'] = self.admin.nombre
        session.save()

    def post_edit(self, usuario_id, **datos):
        return self.client.post('/adminusuarios', {
            'accion': 'editar_personal',
            'usuario_id': usuario_id,
            'nombre': 'Rosa',
            'apellido': 'Recepción',
            'correo': 'rosa@example.com',
            **datos,
        })

    def test_admin_can_update_staff_details_and_password(self):
        response = self.post_edit(
            self.staff.id,
            nombre='María',
            apellido='López',
            correo='maria@example.com',
            nueva_contrasena='nueva-clave-segura',
            confirmar_contrasena='nueva-clave-segura',
        )

        self.assertEqual(response.status_code, 302)
        self.staff.refresh_from_db()
        self.assertEqual(self.staff.nombre, 'María')
        self.assertEqual(self.staff.apellido, 'López')
        self.assertEqual(self.staff.correo, 'maria@example.com')
        self.assertNotEqual(self.staff.contrasena, 'nueva-clave-segura')
        self.assertTrue(check_password('nueva-clave-segura', self.staff.contrasena))

    def test_blank_password_keeps_existing_password(self):
        response = self.post_edit(self.staff.id)

        self.assertEqual(response.status_code, 302)
        self.staff.refresh_from_db()
        self.assertEqual(self.staff.contrasena, 'password-anterior')

    def test_password_change_requires_matching_confirmation(self):
        response = self.post_edit(
            self.staff.id,
            nueva_contrasena='nueva-clave-segura',
            confirmar_contrasena='otra-clave-segura',
        )

        self.assertEqual(response.status_code, 302)
        self.staff.refresh_from_db()
        self.assertEqual(self.staff.contrasena, 'password-anterior')

    def test_personnel_edit_rejects_duplicate_email(self):
        otro = Usuarios.objects.create(
            roles=self.reception_role,
            nombre='Otro',
            apellido='Empleado',
            correo='otro@example.com',
            contrasena='password-anterior',
        )

        response = self.post_edit(self.staff.id, correo=otro.correo)

        self.assertEqual(response.status_code, 302)
        self.staff.refresh_from_db()
        self.assertEqual(self.staff.correo, 'rosa@example.com')

    def test_personnel_edit_rejects_customer_accounts(self):
        cliente = Usuarios.objects.create(
            roles=self.client_role,
            nombre='Cliente',
            apellido='Hotel',
            correo='cliente@example.com',
            contrasena='password-anterior',
        )

        response = self.post_edit(cliente.id, nombre='No autorizado')

        self.assertEqual(response.status_code, 302)
        cliente.refresh_from_db()
        self.assertEqual(cliente.nombre, 'Cliente')

    def test_personnel_tab_renders_edit_action(self):
        response = self.client.get('/adminusuarios?tab=personal')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'data-edit-personal="{self.staff.id}"')
        self.assertContains(response, 'Editar personal')


class ReservationImageTests(TestCase):
    def test_active_reservation_uses_fallback_when_room_upload_is_missing(self):
        huesped = crear_huesped_prueba()
        tipo = TipoHabitacion.objects.create(
            nombre='Estándar',
            capacidad=2,
            tarifa=Decimal('50000.00'),
            imagen='uploads/habitaciones/tipo-existente.jpg',
        )
        habitacion = Habitaciones.objects.create(
            tipohabitacion=tipo,
            numero='A01',
            capacidad=2,
            precio=Decimal('50000.00'),
            imagen='uploads/habitaciones/cuarto-inexistente.jpg',
        )
        reserva = crear_reserva_prueba(huesped)
        reserva.habitaciones = habitacion
        reserva.save(update_fields=['habitaciones'])
        client = Client()
        session = client.session
        session['usuario_id'] = huesped.usuarios_id
        session['rol'] = 'Cliente'
        session.save()

        with TemporaryDirectory() as media_root, TemporaryDirectory() as static_root:
            imagen_tipo = Path(static_root) / 'img' / 'imagenes' / 'uploads' / 'habitaciones' / 'tipo-existente.jpg'
            imagen_tipo.parent.mkdir(parents=True)
            imagen_tipo.touch()
            with override_settings(
                MEDIA_ROOT=media_root,
                STATICFILES_DIRS=[static_root],
                STATIC_URL='/static/',
                MEDIA_URL='/media/',
            ):
                response = client.get('/mis-reservas')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'src="/static/img/imagenes/uploads/habitaciones/tipo-existente.jpg"')
        self.assertNotContains(response, '/media/uploads/habitaciones/cuarto-inexistente.jpg')


class AdminNotificationContextTests(TestCase):
    def test_admin_gets_pending_reservation_and_service_notifications(self):
        huesped = crear_huesped_prueba()
        reserva = crear_reserva_prueba(huesped)
        reserva.estado = 'Pagada - Por validar'
        reserva.save(update_fields=['estado'])
        pago = Pagos.objects.create(
            reservas=reserva,
            valor=Decimal('25.00'),
            metodopago='Pendiente',
            concepto='Servicio',
        )
        servicio = Servicios.objects.create(
            nombre='Desayuno',
            precio=Decimal('25.00'),
        )
        solicitud = ServicioReserva.objects.create(
            reservas=reserva,
            servicios=servicio,
            pago=pago,
            cantidad=1,
            valor=Decimal('25.00'),
        )
        request = RequestFactory().get('/administrador')
        request.session = {'rol': 'Administrador', 'usuario_nom': 'Admin'}

        contexto = notificaciones_administracion(request)

        self.assertEqual(contexto['notificaciones_pendientes'], 1)
        self.assertEqual(contexto['notificaciones_servicios'], 1)
        self.assertEqual(contexto['total_notificaciones'], 2)
        self.assertEqual(contexto['reservas_notificaciones'][0], reserva)
        self.assertEqual(contexto['servicios_notificaciones'][0], solicitud)
        html = render_to_string(
            'inc/admin_header.html',
            {'rol': 'Administrador'},
            request=request,
        )
        self.assertIn('adNotificationToggle', html)
        self.assertIn('Reserva por validar', html)
        self.assertIn('Servicio pendiente', html)
        self.assertIn('>2</span>', html)

    def test_guest_does_not_receive_administrator_notification_data(self):
        request = RequestFactory().get('/')
        request.session = {'rol': 'Cliente'}

        self.assertEqual(notificaciones_administracion(request), {})


class AdminPlanTypeManagementTests(TestCase):
    def setUp(self):
        self.client = Client()
        session = self.client.session
        session['rol'] = 'Administrador'
        session['usuario_nom'] = 'Admin'
        session.save()

    def test_types_page_renders_both_catalog_tabs(self):
        plan = Planes.objects.create(
            nombre='Plan visible',
            precio=Decimal('50000.00'),
        )
        servicio = Servicios.objects.create(
            nombre='Desayuno incluido',
            precio=Decimal('10.00'),
        )
        plan.Servicios_tipos.add(servicio)
        CaracteristicaPlan.objects.create(plan=plan, texto='Desayuno')

        response = self.client.get('/admintiposhabitacion?tab=planes')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Tipos de habitación')
        self.assertContains(response, 'Tipos de planes')
        self.assertContains(response, 'Plan visible')
        self.assertContains(response, 'Desayuno incluido')
        self.assertContains(
            response,
            f'<option value="{servicio.id}" selected>Desayuno incluido</option>',
        )
        self.assertContains(response, 'adNotificationToggle')

    def test_create_edit_and_delete_unreferenced_plan_type(self):
        datos = {
            'accion': 'crear_plan',
            'tab': 'planes',
            'nombre': 'Plan Caribe',
            'descripcion': 'Estadía con desayuno',
            'precio': '250000',
            'imagen': 'planes/caribe.jpg',
            'disponibles': '8',
            'duracion_dias': '3',
            'max_adultos': '2',
            'max_ninos': '1',
            'orden': '2',
            'caracteristicas': 'Desayuno incluido\nTraslado al aeropuerto',
            'estado': 'on',
        }
        respuesta = self.client.post('/admintiposhabitacion', datos)

        self.assertRedirects(
            respuesta,
            '/admintiposhabitacion?tab=planes',
            fetch_redirect_response=False,
        )
        plan = Planes.objects.get(nombre='Plan Caribe')
        self.assertEqual(plan.precio, Decimal('250000.00'))
        self.assertEqual(plan.disponibles, 8)
        self.assertEqual(plan.caracteristicas.count(), 2)

        datos.update({
            'accion': 'editar_plan',
            'plan_id': str(plan.id),
            'nombre': 'Plan Caribe Premium',
            'caracteristicas': 'Desayuno de cortesía',
            'estado': '',
        })
        respuesta = self.client.post('/admintiposhabitacion', datos)
        self.assertRedirects(
            respuesta,
            '/admintiposhabitacion?tab=planes',
            fetch_redirect_response=False,
        )
        plan.refresh_from_db()
        self.assertEqual(plan.nombre, 'Plan Caribe Premium')
        self.assertFalse(plan.estado)
        self.assertEqual(
            list(plan.caracteristicas.values_list('texto', flat=True)),
            ['Desayuno de cortesía'],
        )

        respuesta = self.client.post('/admintiposhabitacion', {
            'accion': 'eliminar_plan',
            'tab': 'planes',
            'plan_id': str(plan.id),
        })
        self.assertRedirects(
            respuesta,
            '/admintiposhabitacion?tab=planes',
            fetch_redirect_response=False,
        )
        self.assertFalse(Planes.objects.filter(id=plan.id).exists())

    def test_editing_plan_saves_new_image_and_renders_its_media_url(self):
        plan = Planes.objects.create(
            nombre='Plan Caribe',
            precio=Decimal('250000.00'),
            imagen='uploads/planes/imagen-anterior.png',
        )
        contenido = BytesIO()
        Image.new('RGB', (1, 1), color=(20, 40, 60)).save(contenido, format='PNG')
        imagen_nueva = SimpleUploadedFile(
            'plan-nuevo.png',
            contenido.getvalue(),
            content_type='image/png',
        )

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=Path(media_root)):
            respuesta = self.client.post('/admintiposhabitacion', {
                'accion': 'editar_plan',
                'tab': 'planes',
                'plan_id': str(plan.id),
                'nombre': 'Plan Caribe',
                'descripcion': 'Estadía con desayuno',
                'precio': '250000',
                'imagen': imagen_nueva,
                'disponibles': '8',
                'duracion_dias': '3',
                'max_adultos': '2',
                'max_ninos': '1',
                'orden': '2',
                'caracteristicas': 'Desayuno incluido',
                'estado': 'on',
            })

            self.assertRedirects(
                respuesta,
                '/admintiposhabitacion?tab=planes',
                fetch_redirect_response=False,
            )
            plan.refresh_from_db()
            self.assertTrue(plan.imagen.startswith('uploads/planes/'))
            self.assertTrue(Path(media_root, plan.imagen).is_file())
            self.assertContains(
                self.client.get('/admintiposhabitacion?tab=planes'),
                f'src="/media/{plan.imagen}"',
            )

    def test_plan_referenced_by_reservation_cannot_be_deleted(self):
        huesped = crear_huesped_prueba()
        plan = Planes.objects.create(
            nombre='Plan reservado',
            precio=Decimal('100.00'),
        )
        reserva = crear_reserva_prueba(huesped)
        reserva.planes = plan
        reserva.save(update_fields=['planes'])

        respuesta = self.client.post('/admintiposhabitacion', {
            'accion': 'eliminar_plan',
            'tab': 'planes',
            'plan_id': str(plan.id),
        }, follow=True)

        self.assertTrue(Planes.objects.filter(id=plan.id).exists())
        self.assertContains(respuesta, 'No se puede eliminar un plan que ya tiene reservas')


class PlanReservationCreationTests(TestCase):
    def setUp(self):
        self.huesped = crear_huesped_prueba()
        self.plan = Planes.objects.create(
            nombre='Plan de prueba',
            precio=Decimal('250000.00'),
            duracion_dias=3,
            max_adultos=2,
            max_ninos=1,
            disponibles=4,
        )
        session = self.client.session
        session['usuario_id'] = self.huesped.usuarios_id
        session.save()

    def test_plan_arrival_date_cannot_be_selected_before_today(self):
        response = self.client.get('/planes')

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'id="planEntrada" class="form-control-modalentrada" min="{timezone.localdate():%Y-%m-%d}"',
        )

    def test_guest_can_create_future_plan_reservation(self):
        entrada = timezone.localdate() + timedelta(days=5)

        response = self.client.post('/reservar-plan/crear/', {
            'plan_id': str(self.plan.id),
            'entrada': entrada.isoformat(),
            'salida': (entrada + timedelta(days=self.plan.duracion_dias)).isoformat(),
            'adultos': '2',
            'ninos': '1',
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        reserva = Reservas.objects.get(id=response.json()['reserva_id'])
        self.assertEqual(reserva.planes, self.plan)
        self.assertEqual(reserva.fechaentrada, entrada)
        self.assertEqual(reserva.estado, 'Pendiente')
        self.assertEqual(
            Pagos.objects.get(reservas=reserva).estado_pago,
            'Pendiente',
        )

    def test_database_error_returns_json_and_rolls_back_plan_reservation(self):
        entrada = timezone.localdate() + timedelta(days=5)

        with patch(
            'caribeconfort.views.Pagos.objects.create',
            side_effect=OperationalError('column estado_pago does not exist'),
        ):
            response = self.client.post('/reservar-plan/crear/', {
                'plan_id': str(self.plan.id),
                'entrada': entrada.isoformat(),
                'salida': (entrada + timedelta(days=self.plan.duracion_dias)).isoformat(),
                'adultos': '1',
                'ninos': '0',
            })

        self.assertEqual(response.status_code, 500)
        self.assertJSONEqual(response.content, {
            'ok': False,
            'error': 'No se pudo guardar la reserva. Verifica que las migraciones de la base de datos estén aplicadas.',
        })
        self.assertFalse(Reservas.objects.filter(planes=self.plan).exists())
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.disponibles, 4)

    def test_guest_cannot_create_plan_reservation_in_the_past(self):
        entrada = timezone.localdate() - timedelta(days=1)

        response = self.client.post('/reservar-plan/crear/', {
            'plan_id': str(self.plan.id),
            'entrada': entrada.isoformat(),
            'salida': (entrada + timedelta(days=self.plan.duracion_dias)).isoformat(),
            'adultos': '1',
            'ninos': '0',
        })

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['ok'])
        self.assertFalse(Reservas.objects.filter(planes=self.plan).exists())


class ReservationDashboardCountTests(TestCase):
    def setUp(self):
        huesped = crear_huesped_prueba()
        crear_reserva_prueba(huesped)
        reserva_cancelada = crear_reserva_prueba(huesped)
        reserva_cancelada.estado = 'Cancelada'
        reserva_cancelada.save(update_fields=['estado'])

    def test_admin_count_matches_filtered_reservation_table(self):
        request = RequestFactory().get('/adminreserva', {'estado': 'Cancelada'})
        request.session = {'rol': 'Administrador'}

        with patch(
            'caribeconfort.views.finalizar_reservas_vencidas',
        ), patch(
            'caribeconfort.views.render',
            return_value=HttpResponse(),
        ) as render_view:
            response = reservasadmin(request)

        context = render_view.call_args.args[2]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(context['total_reservas'], 1)
        self.assertEqual(context['page_obj'].paginator.count, 1)

    def test_reception_count_matches_reservation_table(self):
        request = RequestFactory().get('/recepcionista')
        request.session = {'rol': 'Recepcionista'}

        with patch(
            'caribeconfort.views.render',
            return_value=HttpResponse(),
        ) as render_view:
            response = recepcionista(request)

        context = render_view.call_args.args[2]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(context['total_reservas'], len(context['reservas_hotel']))
        self.assertEqual(context['total_reservas'], 2)


class ReservationRoomLifecycleTests(TestCase):
    def test_dashboard_can_finalize_expired_reservations_without_sending_email(self):
        huesped = crear_huesped_prueba()
        habitacion = Habitaciones.objects.create(
            numero='F01',
            capacidad=2,
            precio=Decimal('50000.00'),
            estado='Ocupada',
        )
        reserva = crear_reserva_prueba(
            huesped,
            fechaentrada=timezone.localdate() - timedelta(days=10),
        )
        reserva.habitaciones = habitacion
        reserva.estado = 'En curso'
        reserva.save(update_fields=['habitaciones', 'estado'])
        request = RequestFactory().get('/administrador')

        with patch(
            'caribeconfort.views._enviar_invitacion_resena',
        ) as send_review_invitation:
            finalizar_reservas_vencidas(
                request,
                enviar_invitaciones=False,
            )

        reserva.refresh_from_db()
        habitacion.refresh_from_db()
        self.assertEqual(reserva.estado, 'Finalizada')
        self.assertEqual(habitacion.estado, 'Disponible')
        send_review_invitation.assert_not_called()

    def test_cancellation_releases_room_after_active_stay_is_cancelled(self):
        huesped = crear_huesped_prueba()
        habitacion = Habitaciones.objects.create(
            numero='C01',
            capacidad=2,
            precio=Decimal('50000.00'),
            estado='Ocupada',
        )
        reserva = crear_reserva_prueba(huesped)
        reserva.habitaciones = habitacion
        reserva.estado = 'En curso'
        reserva.save(update_fields=['habitaciones', 'estado'])
        request = RequestFactory().post(
            f'/api/cancelar-reserva/{reserva.id}/',
            data='{}',
            content_type='application/json',
        )
        request.session = {'rol': 'Administrador'}

        with patch('caribeconfort.views._enviar_correo_hotel', return_value=True):
            response = cancelar_reserva(request, reserva.id)

        habitacion.refresh_from_db()
        reserva.refresh_from_db()
        self.assertTrue(json.loads(response.content)['success'])
        self.assertEqual(reserva.estado, 'Cancelada')
        self.assertEqual(habitacion.estado, 'Disponible')

    def test_checkout_releases_room_when_stay_is_finalized(self):
        huesped = crear_huesped_prueba()
        habitacion = Habitaciones.objects.create(
            numero='CO01',
            capacidad=2,
            precio=Decimal('50000.00'),
            estado='Ocupada',
        )
        reserva = crear_reserva_prueba(huesped)
        reserva.habitaciones = habitacion
        reserva.estado = 'En curso'
        reserva.valortotal = Decimal('0.00')
        reserva.save(update_fields=['habitaciones', 'estado', 'valortotal'])
        request = RequestFactory().post(f'/adminreserva/checkout/{reserva.id}/')
        request.session = {'rol': 'Administrador'}
        request._messages = Mock()

        with patch('caribeconfort.views._enviar_factura_reserva'), patch(
            'caribeconfort.views._enviar_invitacion_resena',
            return_value=True,
        ):
            response = checkout_reserva(request, reserva.id)

        habitacion.refresh_from_db()
        reserva.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(reserva.estado, 'Finalizada')
        self.assertEqual(habitacion.estado, 'Disponible')


class ResenaInvitationTests(SimpleTestCase):
    def test_sends_review_invitation_without_shadowing_translation(self):
        resena = SimpleNamespace(
            correo_enviado=False,
            token=uuid4(),
            save=Mock(),
        )
        reserva = SimpleNamespace(
            huespedes=SimpleNamespace(
                correo='cliente@example.com',
                nombres='Cliente',
            ),
            pk=42,
        )

        with patch.object(
            Resena.objects,
            'get_or_create',
            return_value=(resena, True),
        ), patch(
            'caribeconfort.views._enviar_correo_hotel',
            return_value=1,
        ) as send_hotel_email:
            resultado = _enviar_invitacion_resena(
                reserva,
                RequestFactory().get('/'),
            )

        self.assertTrue(resultado)
        self.assertTrue(resena.correo_enviado)
        resena.save.assert_called_once_with(update_fields=['correo_enviado'])
        self.assertEqual(send_hotel_email.call_args.args[3], 'cliente@example.com')

    def test_missing_smtp_configuration_is_logged_without_traceback(self):
        resena = SimpleNamespace(
            correo_enviado=False,
            token=uuid4(),
            save=Mock(),
        )
        reserva = SimpleNamespace(
            huespedes=SimpleNamespace(
                correo='cliente@example.com',
                nombres='Cliente',
            ),
            pk=42,
        )

        with patch.object(
            Resena.objects,
            'get_or_create',
            return_value=(resena, True),
        ), patch(
            'caribeconfort.views._enviar_correo_hotel',
            side_effect=RuntimeError('SMTP no configurado'),
        ), self.assertLogs('caribeconfort.views', level='WARNING') as logs:
            resultado = _enviar_invitacion_resena(
                reserva,
                RequestFactory().get('/'),
            )

        self.assertFalse(resultado)
        self.assertIn('SMTP no configurado', logs.output[0])
        self.assertNotIn('Traceback', '\n'.join(logs.output))


class ServicioRequestValidationTests(SimpleTestCase):
    def test_requires_requester_name_and_preferred_payment_method(self):
        request = RequestFactory().post(
            '/servicios/solicitar',
            {
                'servicio_id': '3',
                'reserva_id': '12',
                'cantidad': '1',
            },
        )
        request.session = {'usuario_id': 5}

        response = solicitar_servicio(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn('nombre', json.loads(response.content)['error'])

    def test_records_payment_preference_without_marking_service_as_paid(self):
        huesped = SimpleNamespace(
            correo='',
            nombres='Cliente',
            usuarios_id=None,
        )
        servicio = SimpleNamespace(
            id=3,
            nombre='Spa',
            precio=Decimal('12.50'),
        )
        reserva = SimpleNamespace(
            id=12,
            valortotal=Decimal('100.00'),
            save=Mock(),
        )
        servicio_reserva = SimpleNamespace(pago=None, save=Mock())
        pago = SimpleNamespace(metodopago='Pendiente')
        request = RequestFactory().post(
            '/servicios/solicitar',
            {
                'servicio_id': '3',
                'reserva_id': '12',
                'cantidad': '2',
                'solicitado_por': 'Ana Pérez',
                'metodo_pago_preferido': 'Nequi',
            },
        )
        request.session = {'usuario_id': 5}
        reserva_query = Mock()
        reserva_query.get.return_value = reserva

        with patch(
            'caribeconfort.views.Huespedes.objects.get',
            return_value=huesped,
        ), patch(
            'caribeconfort.views.Servicios.objects.get',
            return_value=servicio,
        ), patch(
            'caribeconfort.views.ServicioReserva.objects.create',
            return_value=servicio_reserva,
        ) as create_service_request, patch(
            'caribeconfort.views.Reservas.objects.select_for_update',
            return_value=reserva_query,
        ), patch(
            'caribeconfort.views.Pagos.objects.create',
            return_value=pago,
        ) as create_payment, patch(
            'caribeconfort.views.transaction.atomic',
            return_value=nullcontext(),
        ):
            response = solicitar_servicio(request)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(json.loads(response.content)['ok'])
        self.assertEqual(
            create_service_request.call_args.kwargs['solicitado_por'],
            'Ana Pérez',
        )
        self.assertEqual(
            create_service_request.call_args.kwargs['metodo_pago_preferido'],
            'Nequi',
        )
        self.assertEqual(create_payment.call_args.kwargs['metodopago'], 'Pendiente')
        self.assertEqual(reserva.valortotal, Decimal('125.00'))


class PublicGalleryCategoryTests(TestCase):
    def test_duplicate_category_names_are_grouped_without_losing_images(self):
        categoria_uno = CategoriaGaleria.objects.create(nombre='Exteriores')
        categoria_dos = CategoriaGaleria.objects.create(nombre=' exteriores ')
        ImagenGaleria.objects.create(
            categoria=categoria_uno,
            imagen='uploads/galeria/exterior-uno.jpg',
            seccion='galeria',
        )
        ImagenGaleria.objects.create(
            categoria=categoria_dos,
            imagen='uploads/galeria/exterior-dos.jpg',
            seccion='galeria',
        )

        with patch(
            'caribeconfort.views._url_imagen_local',
            side_effect=lambda imagen: imagen,
        ), patch(
            'caribeconfort.views.render',
            return_value=HttpResponse(),
        ) as render_view:
            response = galeria(RequestFactory().get(
                '/galeria',
                {'categoria': categoria_dos.pk},
            ))

        self.assertEqual(response.status_code, 200)
        context = render_view.call_args.args[2]
        categorias_exteriores = [
            categoria for categoria in context['categorias']
            if categoria.nombre.strip().casefold() == 'exteriores'
        ]
        self.assertEqual(len(categorias_exteriores), 1)
        self.assertEqual(categorias_exteriores[0].total, 2)
        self.assertEqual(context['categoria_activa'].pk, categoria_uno.pk)
        self.assertEqual(len(context['imagenes']), 2)


class AdminGalleryCategoryTests(TestCase):
    def test_admin_can_create_and_assign_a_custom_category(self):
        create_category = RequestFactory().post('/admingaleria', {
            'accion': 'crear_categoria',
            'nombre': 'Exteriores',
            'icono': 'exterior',
        })
        create_category.session = {'rol': 'Administrador'}
        create_category._messages = Mock()

        response = galeriaadmin(create_category)

        self.assertEqual(response.status_code, 302)
        categoria = CategoriaGaleria.objects.get(nombre='Exteriores')

        upload = RequestFactory().post(
            '/admingaleria',
            {
                'accion': 'crear',
                'titulo': 'Terraza',
                'seccion': 'galeria',
                'categoria_id': str(categoria.pk),
                'archivo': SimpleUploadedFile(
                    'terraza.jpg',
                    b'imagen-de-prueba',
                    content_type='image/jpeg',
                ),
            },
        )
        upload.session = {'rol': 'Administrador'}
        upload._messages = Mock()

        with patch(
            'caribeconfort.views._guardar_imagen_galeria',
            return_value='uploads/galeria/terraza.jpg',
        ):
            response = galeriaadmin(upload)

        self.assertEqual(response.status_code, 302)
        imagen = ImagenGaleria.objects.get(titulo='Terraza')
        self.assertEqual(imagen.categoria_id, categoria.pk)
        self.assertEqual(imagen.seccion, 'galeria')

        client = Client()
        session = client.session
        session['rol'] = 'Administrador'
        session['usuario_nom'] = 'Admin de prueba'
        session.save()
        response = client.get('/admingaleria')

        self.assertContains(response, 'Crear categoría')
        self.assertContains(response, 'Exteriores')


class AdminGalleryImageUpdateTests(TestCase):
    def test_replacing_an_image_updates_the_public_gallery_url(self):
        categoria, _ = CategoriaGaleria.objects.get_or_create(
            nombre='Carrusel',
            defaults={'estado': False},
        )
        categoria.estado = False
        categoria.save(update_fields=['estado'])
        imagen = ImagenGaleria.objects.create(
            categoria=categoria,
            titulo='Imagen anterior',
            imagen='uploads/galeria/anterior.png',
            seccion='carrusel',
        )
        archivo_imagen = BytesIO()
        Image.new('RGB', (12, 12), color='#c6a15b').save(archivo_imagen, format='PNG')
        archivo = SimpleUploadedFile(
            'reemplazo.png',
            archivo_imagen.getvalue(),
            content_type='image/png',
        )
        request = RequestFactory().post('/admingaleria', {
            'accion': 'editar',
            'imagen_id': str(imagen.pk),
            'titulo': 'Imagen actualizada',
            'seccion': 'carrusel',
            'estado': 'on',
            'archivo': archivo,
        })
        request.session = {'rol': 'Administrador'}
        request._messages = Mock()

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            response = galeriaadmin(request)
            self.assertEqual(response.status_code, 302)
            imagen.refresh_from_db()
            self.assertNotEqual(imagen.imagen, 'uploads/galeria/anterior.png')
            self.assertTrue(Path(media_root, imagen.imagen).is_file())
            imagen.categoria.refresh_from_db()
            self.assertTrue(imagen.categoria.estado)

            with patch(
                'caribeconfort.views.render',
                return_value=HttpResponse(),
            ) as render_view:
                galeria(RequestFactory().get('/galeria'))

            imagenes_publicas = render_view.call_args.args[2]['imagenes']
            imagen_publica_actualizada = next(
                imagen_publica for imagen_publica in imagenes_publicas
                if imagen_publica.pk == imagen.pk
            )
            self.assertEqual(
                imagen_publica_actualizada.url_imagen,
                f'/media/{imagen.imagen}',
            )

            with patch(
                'caribeconfort.views.render',
                return_value=HttpResponse(),
            ) as home_render:
                home(RequestFactory().get('/'))

            imagenes_carrusel = home_render.call_args.args[2]['imagenes_carrusel']
            imagen_portada_actualizada = next(
                imagen_publica for imagen_publica in imagenes_carrusel
                if imagen_publica.pk == imagen.pk
            )
            self.assertEqual(
                imagen_portada_actualizada.url_imagen,
                f'/media/{imagen.imagen}',
            )


class BookingDateDefaultsTests(TestCase):
    @patch('caribeconfort.views.render', return_value=HttpResponse())
    def test_search_defaults_to_today_and_the_following_day(self, render_view):
        response = buscar_disponibilidad(RequestFactory().get('/reservas'))

        self.assertEqual(response.status_code, 200)
        context = render_view.call_args.args[2]
        today = timezone.localdate()
        self.assertEqual(context['fecha_entrada'], today.isoformat())
        self.assertEqual(context['fecha_salida'], (today + timedelta(days=1)).isoformat())
        self.assertEqual(context['fecha_salida_min'], (today + timedelta(days=1)).isoformat())

    def test_search_moves_checkout_after_arrival_when_requested_range_is_invalid(self):
        entrada = timezone.localdate() + timedelta(days=5)
        response = self.client.get('/reservas', {
            'entrada': entrada.isoformat(),
            'salida': (entrada - timedelta(days=1)).isoformat(),
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context['fecha_salida'],
            (entrada + timedelta(days=1)).isoformat(),
        )
        self.assertEqual(
            response.context['fecha_salida_min'],
            (entrada + timedelta(days=1)).isoformat(),
        )
        self.assertContains(response, 'La fecha de salida debe ser posterior')
        self.assertContains(
            response,
            f'min="{(entrada + timedelta(days=1)).isoformat()}"',
        )

    def test_search_includes_occupied_room_when_requested_dates_do_not_overlap(self):
        tipo = TipoHabitacion.objects.create(
            nombre='Estándar',
            capacidad=2,
            tarifa=Decimal('50000.00'),
        )
        ocupada = Habitaciones.objects.create(
            tipohabitacion=tipo,
            numero='E01',
            capacidad=2,
            precio=Decimal('50000.00'),
            estado='Ocupada',
        )
        Habitaciones.objects.create(
            tipohabitacion=tipo,
            numero='E02',
            capacidad=2,
            precio=Decimal('50000.00'),
            estado='Bloqueada',
        )
        huesped = crear_huesped_prueba()
        reserva_en_curso = crear_reserva_prueba(
            huesped,
            fechaentrada=timezone.localdate(),
        )
        reserva_en_curso.habitaciones = ocupada
        reserva_en_curso.estado = 'En curso'
        reserva_en_curso.save(update_fields=['habitaciones', 'estado'])

        entrada = timezone.localdate() + timedelta(days=3)
        response = self.client.get('/reservas', {
            'entrada': entrada.isoformat(),
            'salida': (entrada + timedelta(days=1)).isoformat(),
        })

        tipo_renderizado = response.context['tipos'][0]
        self.assertEqual(tipo_renderizado.cant_disponibles, 1)
        self.assertEqual(tipo_renderizado.ids_disponibles, [ocupada.id])

    def test_booking_accepts_occupied_room_for_dates_after_current_stay(self):
        tipo = TipoHabitacion.objects.create(
            nombre='Estándar',
            capacidad=2,
            tarifa=Decimal('50000.00'),
        )
        ocupada = Habitaciones.objects.create(
            tipohabitacion=tipo,
            numero='E03',
            capacidad=2,
            precio=Decimal('50000.00'),
            estado='Ocupada',
        )
        huesped_actual = crear_huesped_prueba()
        reserva_actual = crear_reserva_prueba(
            huesped_actual,
            fechaentrada=timezone.localdate(),
        )
        reserva_actual.habitaciones = ocupada
        reserva_actual.estado = 'En curso'
        reserva_actual.save(update_fields=['habitaciones', 'estado'])
        huesped_nuevo = crear_huesped_prueba()
        session = self.client.session
        session['usuario_id'] = huesped_nuevo.usuarios_id
        session.save()
        entrada = timezone.localdate() + timedelta(days=3)

        response = self.client.post('/reservas/crear', {
            'habitacion_ids': str(ocupada.id),
            'entrada': entrada.isoformat(),
            'salida': (entrada + timedelta(days=1)).isoformat(),
            'adultos': '1',
            'ninos': '0',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])

    def test_search_renders_fifteen_available_rooms_as_available(self):
        tipo = TipoHabitacion.objects.create(
            nombre='Estándar',
            capacidad=2,
            tarifa=Decimal('50000.00'),
        )
        TipoHabitacion.objects.create(
            nombre='Tipo sin inventario',
            capacidad=2,
            tarifa=Decimal('50000.00'),
        )
        for numero in range(1, 16):
            Habitaciones.objects.create(
                tipohabitacion=tipo,
                numero=f'T{numero:02d}',
                capacidad=2,
                precio=Decimal('50000.00'),
                estado='Disponible',
            )

        response = self.client.get('/reservas')

        self.assertContains(response, '15 disponibles')
        self.assertContains(response, 'tag-disponible')
        self.assertNotContains(response, 'tag-agotado')
        self.assertContains(response, 'src="/static/img/imagenes/BASO.jpg"')
        tipos_renderizados = response.context['tipos']
        self.assertEqual(len(tipos_renderizados), 1)
        tipo_renderizado = tipos_renderizados[0]
        self.assertEqual(tipo_renderizado.cant_disponibles, 15)
        self.assertEqual(len(tipo_renderizado.ids_disponibles), 15)

    @patch('caribeconfort.views.render', return_value=HttpResponse())
    def test_search_capacity_includes_children(self, render_view):
        tipo = TipoHabitacion.objects.create(
            nombre='Individual',
            capacidad=2,
            tarifa=Decimal('50000.00'),
        )
        Habitaciones.objects.create(
            tipohabitacion=tipo,
            numero='I01',
            capacidad=1,
            precio=Decimal('50000.00'),
            estado='Disponible',
        )

        response = buscar_disponibilidad(RequestFactory().get(
            '/reservas',
            {'adultos': '1', 'ninos': '1'},
        ))

        self.assertEqual(response.status_code, 200)
        tipo_renderizado = render_view.call_args.args[2]['tipos'][0]
        self.assertEqual(tipo_renderizado.cant_disponibles, 0)
        self.assertEqual(tipo_renderizado.ids_disponibles, [])


class HomeHotelMapTests(TestCase):
    def test_map_address_uses_hotel_address_or_riohacha_fallback(self):
        hotel = Hoteles.objects.create(
            nombre='Caribe Confort',
            direccion='',
            municipio='Riohacha',
            telefono='3000000000',
            correo='hotel@example.com',
        )

        with patch(
            'caribeconfort.views.render',
            side_effect=[HttpResponse(), HttpResponse()],
        ) as render_view:
            home(RequestFactory().get('/'))
            hotel.direccion = 'Calle 1 # 2-3, Riohacha'
            hotel.save(update_fields=['direccion'])
            home(RequestFactory().get('/'))

        contextos = [llamada.args[2] for llamada in render_view.call_args_list]
        self.assertEqual(
            contextos[0]['direccion_mapa'],
            'Riohacha, La Guajira, Colombia',
        )
        self.assertEqual(
            contextos[1]['direccion_mapa'],
            'Calle 1 # 2-3, Riohacha',
        )


class SMTPMailConfigurationTests(TestCase):
    def test_missing_smtp_host_is_reported_instead_of_using_localhost(self):
        with override_settings(MAILERS={'default': {'OPTIONS': {'host': ''}}}):
            with self.assertRaisesRegex(RuntimeError, 'EMAIL_HOST'):
                _conexion_correo_hotel()

    def test_environment_smtp_settings_are_used_without_hotel_configuration(self):
        opciones = {
            'host': 'smtp.example.com',
            'port': 587,
            'username': 'hotel@example.com',
            'password': 'smtp-secret-for-test',
            'use_tls': True,
            'use_ssl': False,
        }
        with override_settings(
            MAILERS={'default': {'OPTIONS': opciones}},
            DEFAULT_FROM_EMAIL='notificaciones@example.com',
        ), patch(
            'caribeconfort.views.get_connection',
            return_value=object(),
        ) as get_connection:
            conexion, remitente = _conexion_correo_hotel()

        self.assertIsNotNone(conexion)
        self.assertEqual(remitente, 'notificaciones@example.com')
        get_connection.assert_called_once_with(
            host='smtp.example.com',
            port=587,
            username='hotel@example.com',
            password='smtp-secret-for-test',
            use_tls=True,
            use_ssl=False,
            fail_silently=False,
        )

    def test_port_465_uses_implicit_ssl_instead_of_starttls(self):
        clave = Fernet.generate_key().decode('ascii')
        with override_settings(EMAIL_CREDENTIAL_ENCRYPTION_KEY=clave):
            Hoteles.objects.create(
                nombre='Caribe Confort',
                direccion='Calle 1',
                municipio='Riohacha',
                telefono='3000000000',
                correo='hotel@example.com',
                smtp_host='smtp.example.com',
                smtp_port=465,
                smtp_username='hotel@example.com',
                smtp_from_email='notificaciones@example.com',
                smtp_password_encrypted=_cifrar_contrasena_smtp('smtp-secret-for-test'),
                smtp_use_tls=True,
            )
            with patch(
                'caribeconfort.views.get_connection',
                return_value=object(),
            ) as get_connection:
                _conexion_correo_hotel()

        get_connection.assert_called_once_with(
            host='smtp.example.com',
            port=465,
            username='hotel@example.com',
            password='smtp-secret-for-test',
            use_tls=False,
            use_ssl=True,
            fail_silently=False,
        )

    def test_password_is_encrypted_and_branded_html_uses_hotel_smtp_settings(self):
        clave = Fernet.generate_key().decode('ascii')
        contrasena = 'smtp-secret-for-test'

        with override_settings(EMAIL_CREDENTIAL_ENCRYPTION_KEY=clave):
            contrasena_cifrada = _cifrar_contrasena_smtp(contrasena)
            self.assertNotIn(contrasena, contrasena_cifrada)
            self.assertEqual(_descifrar_contrasena_smtp(contrasena_cifrada), contrasena)

            Hoteles.objects.create(
                nombre='Caribe Confort',
                direccion='Calle 1',
                municipio='Riohacha',
                telefono='3000000000',
                correo='hotel@example.com',
                smtp_host='smtp.example.com',
                smtp_port=587,
                smtp_username='hotel@example.com',
                smtp_from_email='notificaciones@example.com',
                smtp_password_encrypted=contrasena_cifrada,
                smtp_use_tls=True,
            )
            with patch(
                'caribeconfort.views.get_connection',
                return_value=object(),
            ) as get_connection, patch(
                'caribeconfort.views.send_mail',
                return_value=1,
            ) as send_mail:
                _enviar_correo_hotel(
                    'Servicio aprobado',
                    'Tu servicio fue aprobado',
                    'Solicitaste desayuno por $20.000 COP.',
                    'cliente@example.com',
                )

        get_connection.assert_called_once_with(
            host='smtp.example.com',
            port=587,
            username='hotel@example.com',
            password=contrasena,
            use_tls=True,
            use_ssl=False,
            fail_silently=False,
        )
        self.assertIn('#16484b', send_mail.call_args.kwargs['html_message'])
        self.assertIn('Tu servicio fue aprobado', send_mail.call_args.kwargs['html_message'])


class SMTPAdminConfigurationTests(TestCase):
    def setUp(self):
        self.hotel = Hoteles.objects.create(
            nombre='Caribe Confort',
            direccion='Calle 1',
            municipio='Riohacha',
            telefono='3000000000',
            correo='hotel@example.com',
        )

    def _post_smtp_config(self, puerto, contrasena):
        request = RequestFactory().post('/adminconfiguracion', {
            'seccion': 'correo',
            'smtp_host': 'smtp.example.com',
            'smtp_port': puerto,
            'smtp_username': 'hotel@example.com',
            'smtp_from_email': 'notificaciones@example.com',
            'smtp_password': contrasena,
            'smtp_use_tls': 'on',
        })
        request.session = {
            'rol': 'Administrador',
            'usuario_nom': 'Administradora',
        }
        request._messages = Mock()
        return configuracionadmin(request)

    def test_saves_smtp_password_encrypted_and_rejects_invalid_port(self):
        clave = Fernet.generate_key().decode('ascii')
        contrasena = 'admin-smtp-secret'

        with override_settings(EMAIL_CREDENTIAL_ENCRYPTION_KEY=clave):
            respuesta = self._post_smtp_config('587', contrasena)
            self.assertEqual(respuesta.status_code, 302)
            self.hotel.refresh_from_db()
            self.assertNotEqual(self.hotel.smtp_password_encrypted, contrasena)
            self.assertEqual(
                _descifrar_contrasena_smtp(self.hotel.smtp_password_encrypted),
                contrasena,
            )

            with patch(
                'caribeconfort.views.render',
                return_value=HttpResponse(),
            ):
                respuesta = self._post_smtp_config('70000', 'replacement-secret')
            self.assertEqual(respuesta.status_code, 200)
            self.hotel.refresh_from_db()
            self.assertEqual(self.hotel.smtp_port, 587)
            self.assertEqual(
                _descifrar_contrasena_smtp(self.hotel.smtp_password_encrypted),
                contrasena,
            )


class HotelBrandingAdminTests(TestCase):
    def setUp(self):
        self.hotel = Hoteles.objects.create(
            nombre='Caribe Confort',
            direccion='Calle 1',
            municipio='Riohacha',
            telefono='3000000000',
            correo='hotel@example.com',
        )

    def test_admin_can_update_name_and_upload_a_valid_logo(self):
        imagen = BytesIO()
        Image.new('RGB', (16, 16), color='#c6a15b').save(imagen, format='PNG')
        imagen.seek(0)
        archivo = SimpleUploadedFile(
            'simbolo.png',
            imagen.read(),
            content_type='image/png',
        )
        datos = {
            'nombre': 'Hotel Caribe Confort',
            'descripcion': '',
            'direccion': 'Calle 2',
            'municipio': 'Riohacha',
            'telefono': '3000000000',
            'correo': 'hotel@example.com',
            'fotografias': '',
            'logo': archivo,
        }
        request = RequestFactory().post('/adminconfiguracion', datos)
        request.session = {'rol': 'Administrador', 'usuario_nom': 'Admin'}
        request._messages = Mock()

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            respuesta = configuracionadmin(request)
            self.assertEqual(respuesta.status_code, 302)
            self.hotel.refresh_from_db()
            self.assertEqual(self.hotel.nombre, 'Hotel Caribe Confort')
            self.assertTrue(self.hotel.logo.name.startswith('hoteles/logos/'))
            self.assertTrue(Path(media_root, self.hotel.logo.name).is_file())
            identidad = identidad_hotel(request)
            self.assertEqual(identidad['nombre_hotel'], 'Hotel Caribe Confort')
            self.assertEqual(
                identidad['logo_hotel_url'],
                f'/media/{self.hotel.logo.name}',
            )
            respuesta_logo = servir_logo_hotel(
                request,
                Path(self.hotel.logo.name).name,
            )
            self.assertEqual(respuesta_logo['Content-Type'], 'image/png')
            respuesta_logo.file_to_stream.close()

    def test_invalid_logo_does_not_change_hotel_brand(self):
        archivo = SimpleUploadedFile(
            'logo.png',
            b'not an image',
            content_type='image/png',
        )
        request = RequestFactory().post('/adminconfiguracion', {
            'nombre': 'Otro nombre',
            'direccion': 'Calle 2',
            'municipio': 'Riohacha',
            'telefono': '3000000000',
            'correo': 'hotel@example.com',
            'logo': archivo,
        })
        request.session = {'rol': 'Administrador', 'usuario_nom': 'Admin'}
        request._messages = Mock()
        with patch(
            'caribeconfort.views.render',
            return_value=HttpResponse(),
        ):
            respuesta = configuracionadmin(request)

        self.assertEqual(respuesta.status_code, 200)
        self.hotel.refresh_from_db()
        self.assertEqual(self.hotel.nombre, 'Caribe Confort')


class ReservationDocumentsTests(TestCase):
    def setUp(self):
        self.huesped = crear_huesped_prueba()
        self.reserva = crear_reserva_prueba(self.huesped)
        self.pago = Pagos.objects.create(
            reservas=self.reserva,
            valor=Decimal('50.00'),
            metodopago='Transferencia',
            concepto='Reserva',
        )

    def test_invoice_is_pdf_and_only_available_to_owner_or_staff(self):
        request = RequestFactory().get(
            f'/reservas/{self.reserva.id}/factura/'
        )
        request.session = {'usuario_id': self.huesped.usuarios_id, 'rol': 'Cliente'}
        respuesta = descargar_factura_reserva(request, self.reserva.id)
        self.assertEqual(respuesta['Content-Type'], 'application/pdf')
        self.assertTrue(respuesta.content.startswith(b'%PDF-'))

        otro_huesped = crear_huesped_prueba()
        request.session = {
            'usuario_id': otro_huesped.usuarios_id,
            'rol': 'Cliente',
        }
        respuesta = descargar_factura_reserva(request, self.reserva.id)
        self.assertEqual(respuesta.status_code, 403)

    def test_admin_can_download_invoice_using_admin_session(self):
        admin_session = import_module(settings.SESSION_ENGINE).SessionStore()
        admin_session['rol'] = 'Administrador'
        admin_session.save()
        admin_cookie_name = f'{settings.SESSION_COOKIE_NAME}_admin'
        self.client.cookies[admin_cookie_name] = admin_session.session_key

        respuesta = self.client.get(
            f'/reservas/{self.reserva.id}/factura/?scope=admin'
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta['Content-Type'], 'application/pdf')
        self.assertTrue(respuesta.content.startswith(b'%PDF-'))

    def test_guest_can_download_payment_certificate(self):
        request = RequestFactory().get('/mis-reservas/certificado-pagos/')
        request.session = {'usuario_id': self.huesped.usuarios_id, 'rol': 'Cliente'}

        respuesta = descargar_certificado_pagos(request)

        self.assertEqual(respuesta['Content-Type'], 'application/pdf')
        self.assertTrue(respuesta.content.startswith(b'%PDF-'))


class RefundPaymentSelectionTests(TestCase):
    def setUp(self):
        huesped = crear_huesped_prueba()
        self.reserva = crear_reserva_prueba(huesped)
        self.pago = Pagos.objects.create(
            reservas=self.reserva,
            valor=Decimal('100.00'),
            metodopago='Tarjeta',
            concepto='Reserva',
        )

    def _post_refund(self, amount):
        request = RequestFactory().post(
            f'/adminreserva/{self.reserva.id}/reembolso',
            {
                'pago_id': self.pago.id,
                'monto': amount,
                'metodo': 'Transferencia',
            },
        )
        request.session = {'rol': 'Administrador'}
        return procesar_reembolso(request, self.reserva.id)

    def test_refund_is_linked_to_payment_and_cannot_exceed_its_remaining_amount(self):
        with patch('caribeconfort.views._enviar_correo_hotel', return_value=1):
            respuesta = self._post_refund('40.00')
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(json.loads(respuesta.content)['correo_enviado'])
        reembolso = Pagos.objects.get(concepto='Reembolso')
        self.assertEqual(reembolso.valor, Decimal('-40.00'))
        self.assertEqual(reembolso.pago_origen_id, self.pago.id)

        respuesta = self._post_refund('60.01')
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(Pagos.objects.filter(concepto='Reembolso').count(), 1)

    def test_invalid_payment_id_returns_validation_error(self):
        request = RequestFactory().post(
            f'/adminreserva/{self.reserva.id}/reembolso',
            {
                'pago_id': 'no-es-un-id',
                'monto': '10.00',
                'metodo': 'Transferencia',
            },
        )
        request.session = {'rol': 'Administrador'}

        respuesta = procesar_reembolso(request, self.reserva.id)

        self.assertEqual(respuesta.status_code, 400)
        self.assertFalse(json.loads(respuesta.content)['success'])

    def test_refund_endpoint_succeeds_through_django_client(self):
        session = self.client.session
        session['rol'] = 'Administrador'
        session.save()

        with patch('caribeconfort.views._enviar_correo_hotel', return_value=1):
            respuesta = self.client.post(
                f'/adminreserva/{self.reserva.id}/reembolso',
                {
                    'pago_id': self.pago.id,
                    'monto': '40.00',
                    'metodo': 'Transferencia',
                },
            )

        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.json()['success'])

    def test_reservation_overpayment_refund_without_source_payment_is_recorded(self):
        self.reserva.valortotal = Decimal('60.00')
        self.reserva.save(update_fields=['valortotal'])
        request = RequestFactory().post(
            f'/adminreserva/{self.reserva.id}/reembolso',
            {
                'monto': '40.00',
                'metodo': 'Transferencia',
            },
        )
        request.session = {'rol': 'Administrador'}

        with patch('caribeconfort.views._enviar_correo_hotel', return_value=1):
            respuesta = procesar_reembolso(request, self.reserva.id)

        self.assertEqual(respuesta.status_code, 200)
        reembolso = Pagos.objects.get(concepto='Reembolso')
        self.assertEqual(reembolso.valor, Decimal('-40.00'))
        self.assertIsNone(reembolso.pago_origen_id)


class RefundAccountingTests(TestCase):
    def setUp(self):
        self.huesped = crear_huesped_prueba()
        self.reserva = crear_reserva_prueba(self.huesped)
        session = self.client.session
        session['rol'] = 'Administrador'
        session['usuario_nom'] = 'Admin de prueba'
        session.save()

    def _dashboard_context(self):
        request = RequestFactory().get('/administrador')
        request.session = {'rol': 'Administrador'}
        with patch('caribeconfort.views.finalizar_reservas_vencidas'), patch(
            'caribeconfort.views.render',
            return_value=HttpResponse(),
        ) as render_view:
            response = administrador(request)
        self.assertEqual(response.status_code, 200)
        return render_view.call_args.args[2]

    def test_unconfirmed_payment_is_not_counted_as_collected_cash(self):
        Pagos.objects.create(
            reservas=self.reserva,
            valor=Decimal('100.00'),
            metodopago='Transferencia',
            concepto='Reserva',
            estado_pago='Pendiente',
        )

        context = self._dashboard_context()

        self.assertEqual(context['caja_reservas'], 0)
        self.assertEqual(context['caja_total'], 0)

    def test_refund_history_renders_refund_amount_without_server_error(self):
        pago = Pagos.objects.create(
            reservas=self.reserva,
            valor=Decimal('100.00'),
            metodopago='Tarjeta',
            concepto='Reserva',
        )
        Pagos.objects.create(
            reservas=self.reserva,
            valor=Decimal('-40.00'),
            metodopago='Transferencia',
            concepto='Reembolso',
            pago_origen=pago,
        )

        response = self.client.get('/adminpagos?tab=reembolsos')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '-$ 40,00')

    def test_dashboard_cash_and_income_graph_include_refund_losses(self):
        pago_reserva = Pagos.objects.create(
            reservas=self.reserva,
            valor=Decimal('300.00'),
            metodopago='Tarjeta',
            concepto='Reserva',
        )
        pago_servicio = Pagos.objects.create(
            reservas=self.reserva,
            valor=Decimal('50.00'),
            metodopago='Nequi',
            concepto='Servicio',
        )
        Pagos.objects.create(
            reservas=self.reserva,
            valor=Decimal('-20.00'),
            metodopago='Transferencia',
            concepto='Reembolso',
            pago_origen=pago_servicio,
        )
        Pagos.objects.create(
            reservas=self.reserva,
            valor=Decimal('-40.00'),
            metodopago='Efectivo',
            concepto='Reembolso',
            pago_origen=pago_reserva,
        )

        context = self._dashboard_context()

        self.assertEqual(context['caja_reservas'], Decimal('300.00'))
        self.assertEqual(context['caja_servicios'], Decimal('50.00'))
        self.assertEqual(context['caja_reembolsos'], Decimal('-60.00'))
        self.assertEqual(context['caja_total'], Decimal('290.00'))
        self.assertEqual(context['pagosdiarios'], Decimal('290.00'))
        self.assertEqual(context['ingresos_semanales'], Decimal('290.00'))
        self.assertEqual(context['ingresos_chart']['puntos'][-1]['valor'], Decimal('290.00'))

    def test_monthly_chart_keeps_negative_net_values_in_view(self):
        Pagos.objects.create(
            reservas=self.reserva,
            valor=Decimal('-10000000.00'),
            metodopago='Transferencia',
            concepto='Reembolso',
        )

        context = self._dashboard_context()
        punto_neto_negativo = context['ingresos_chart']['puntos'][-1]

        self.assertEqual(punto_neto_negativo['valor'], Decimal('-10000000.00'))
        self.assertGreaterEqual(punto_neto_negativo['y'], 35)
        self.assertLessEqual(punto_neto_negativo['y'], 375)


class MisReservasPaymentSummaryTests(TestCase):
    def setUp(self):
        huesped = crear_huesped_prueba()
        self.reserva = crear_reserva_prueba(huesped)
        Pagos.objects.create(
            reservas=self.reserva,
            valor=Decimal('60.00'),
            metodopago='Transferencia',
            concepto='Reserva',
        )
        Pagos.objects.create(
            reservas=self.reserva,
            valor=Decimal('-20.00'),
            metodopago='Transferencia',
            concepto='Reembolso',
        )
        Pagos.objects.create(
            reservas=self.reserva,
            valor=Decimal('50.00'),
            metodopago='Pendiente',
            concepto='Reserva',
        )
        session = self.client.session
        session['usuario_id'] = huesped.usuarios_id
        session['rol'] = 'Cliente'
        session.save()

    def test_reservation_card_separates_paid_amount_from_refunds(self):
        response = self.client.get('/mis-reservas')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '$ 60 <small>COP</small>')
        self.assertContains(response, 'Reembolsado: $ 20 COP')
        self.assertContains(response, 'Saldo pendiente: $ 60 COP')
        reserva = response.context['activas'][0]
        self.assertEqual(reserva.total_pagado, Decimal('60.00'))
        self.assertEqual(reserva.total_reembolsado, Decimal('20.00'))
        self.assertEqual(reserva.abono_pagado, Decimal('40.00'))


class ReservationReminderCommandTests(TestCase):
    def test_sends_two_and_one_day_reminders_only_once(self):
        hoy = timezone.localdate()
        reserva_dos_dias = crear_reserva_prueba(
            crear_huesped_prueba(cuenta=False),
            hoy + timedelta(days=2),
        )
        reserva_un_dia = crear_reserva_prueba(
            crear_huesped_prueba(cuenta=False),
            hoy + timedelta(days=1),
        )
        salida = StringIO()

        with patch(
            'django.utils.timezone.localdate',
            return_value=hoy,
        ), patch(
            'caribeconfort.management.commands.enviar_recordatorios_reservas._enviar_correo_hotel',
            return_value=1,
        ) as enviar:
            call_command('enviar_recordatorios_reservas', stdout=salida)
            call_command('enviar_recordatorios_reservas', stdout=StringIO())

        self.assertEqual(enviar.call_count, 2)
        self.assertTrue(any(
            'el abono del 50% no será reembolsable' in llamada.args[2]
            for llamada in enviar.call_args_list
        ))
        reserva_dos_dias.refresh_from_db()
        reserva_un_dia.refresh_from_db()
        self.assertTrue(reserva_dos_dias.recordatorio_dos_dias_enviado)
        self.assertTrue(reserva_un_dia.recordatorio_un_dia_enviado)

    def test_failed_email_does_not_mark_reminder_as_sent(self):
        hoy = timezone.localdate()
        reserva = crear_reserva_prueba(
            crear_huesped_prueba(cuenta=False),
            hoy + timedelta(days=2),
        )
        with patch(
            'django.utils.timezone.localdate',
            return_value=hoy,
        ), patch(
            'caribeconfort.management.commands.enviar_recordatorios_reservas._enviar_correo_hotel',
            side_effect=RuntimeError('SMTP no disponible'),
        ), self.assertRaises(CommandError):
            call_command('enviar_recordatorios_reservas', stdout=StringIO(), stderr=StringIO())

        reserva.refresh_from_db()
        self.assertFalse(reserva.recordatorio_dos_dias_enviado)


class ReservationReminderRescheduleTests(TestCase):
    def test_changing_checkin_date_resets_sent_reminder_flags(self):
        huesped = crear_huesped_prueba(cuenta=False)
        fecha_original = timezone.localdate() + timedelta(days=4)
        reserva = crear_reserva_prueba(huesped, fecha_original)
        habitacion = Habitaciones.objects.create(
            numero=uuid4().hex[:10],
            capacidad=2,
            precio=Decimal('100.00'),
            estado='Disponible',
        )
        reserva.habitaciones = habitacion
        reserva.recordatorio_dos_dias_enviado = True
        reserva.recordatorio_un_dia_enviado = True
        reserva.save(update_fields=[
            'habitaciones',
            'recordatorio_dos_dias_enviado',
            'recordatorio_un_dia_enviado',
        ])

        nueva_entrada = timezone.localdate() + timedelta(days=8)
        request = RequestFactory().post('/adminreserva/1/modificar', {
            'nueva_fecha_entrada': nueva_entrada.isoformat(),
            'nueva_fecha_salida': (nueva_entrada + timedelta(days=2)).isoformat(),
        })
        request.session = {'rol': 'Administrador'}
        with patch('caribeconfort.views._enviar_correo_hotel', return_value=1):
            respuesta = modificar_reserva(request, reserva.id)

        self.assertEqual(respuesta.status_code, 200)
        reserva.refresh_from_db()
        self.assertFalse(reserva.recordatorio_dos_dias_enviado)
        self.assertFalse(reserva.recordatorio_un_dia_enviado)


class ResenaSubmissionTests(SimpleTestCase):
    def test_saves_room_rating_separately_from_stay_rating(self):
        resena = SimpleNamespace(
            calificacion=None,
            calificacion_habitacion=None,
            comentario='',
            reserva_id=42,
            reserva=SimpleNamespace(habitaciones_id=7),
            save=Mock(),
        )
        request = RequestFactory().post(
            '/resenas/token',
            {
                'calificacion': '5',
                'calificacion_habitacion': '3',
                'comentario': 'La habitación estaba muy cómoda.',
            },
        )
        queryset = Mock()
        queryset.select_related.return_value = queryset

        with patch(
            'caribeconfort.views.Resena.objects',
            Mock(select_related=Mock(return_value=queryset)),
        ), patch(
            'caribeconfort.views.get_object_or_404',
            return_value=resena,
        ), patch(
            'caribeconfort.views.render',
            return_value=HttpResponse(),
        ):
            dejar_resena(request, uuid4())

        self.assertEqual(resena.calificacion, 5)
        self.assertEqual(resena.calificacion_habitacion, 3)
        resena.save.assert_called_once_with(update_fields=[
            'calificacion',
            'calificacion_habitacion',
            'comentario',
            'fecha',
        ])


class AssignLocalImagesCommandTests(TestCase):
    def test_assigns_static_service_images_and_creates_gallery_rows_idempotently(self):
        servicio = Servicios.objects.create(
            nombre='Desayuno',
            precio=Decimal('25000.00'),
        )

        with TemporaryDirectory() as static_root:
            directorio_imagenes = Path(static_root) / 'img' / 'imagenes'
            directorio_imagenes.mkdir(parents=True)
            for nombre in ('foto1.png', 'foto2.png', 'foto3.png', 'foto4.png'):
                (directorio_imagenes / nombre).write_bytes(b'image')

            with override_settings(STATICFILES_DIRS=[Path(static_root)]):
                call_command('asignar_imagenes_locales', stdout=StringIO())
                call_command('asignar_imagenes_locales', stdout=StringIO())

        servicio.refresh_from_db()
        self.assertEqual(servicio.imagen, 'img/imagenes/foto1.png')
        categoria = CategoriaGaleria.objects.get(nombre='Galería')
        self.assertEqual(
            ImagenGaleria.objects.filter(
                categoria=categoria,
                seccion='galeria',
            ).count(),
            4,
        )


class ExcelReportExportTests(TestCase):
    def test_every_report_type_returns_a_valid_xlsx_workbook(self):
        cliente = Client()
        session = cliente.session
        session['rol'] = 'Administrador'
        session.save()
        hoy = timezone.localdate().isoformat()

        for tipo in ('reservas', 'ocupacion', 'ingresos', 'huespedes'):
            with self.subTest(tipo=tipo):
                response = cliente.get(
                    '/adminreportes/exportar',
                    {'tipo': tipo, 'desde': hoy, 'hasta': hoy},
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response['Content-Type'],
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                )
                libro = load_workbook(BytesIO(response.content), read_only=True)
                self.assertGreaterEqual(libro.active.max_column, 1)

    def test_guest_report_is_an_xlsx_with_column_widths_based_on_content(self):
        huesped = crear_huesped_prueba(cuenta=False)
        cliente = Client()
        session = cliente.session
        session['rol'] = 'Administrador'
        session.save()
        hoy = timezone.localdate().isoformat()

        response = cliente.get(
            '/adminreportes/exportar',
            {'tipo': 'huespedes', 'desde': hoy, 'hasta': hoy},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        self.assertIn('.xlsx', response['Content-Disposition'])
        libro = load_workbook(BytesIO(response.content))
        hoja = libro.active
        self.assertEqual(hoja['C2'].value, huesped.correo)
        self.assertEqual(hoja.column_dimensions['C'].width, 42)
        self.assertEqual(hoja.freeze_panes, 'A2')
