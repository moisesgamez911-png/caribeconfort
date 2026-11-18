import json
from contextlib import nullcontext
from datetime import timedelta
from decimal import Decimal
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from cryptography.fernet import Fernet
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from caribeconfort.context_processors import identidad_hotel
from caribeconfort.models import (
    CategoriaGaleria,
    Huespedes,
    Hoteles,
    ImagenGaleria,
    Pagos,
    Reservas,
    Resena,
    Roles,
    Usuarios,
)
from caribeconfort.views import (
    _cifrar_contrasena_smtp,
    _descifrar_contrasena_smtp,
    _enviar_invitacion_resena,
    _enviar_correo_hotel,
    configuracionadmin,
    descargar_certificado_pagos,
    descargar_factura_reserva,
    dejar_resena,
    galeria,
    home,
    procesar_reembolso,
    servir_logo_hotel,
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
        self.assertEqual(len(context['categorias']), 1)
        self.assertEqual(context['categorias'][0].total, 2)
        self.assertEqual(context['categoria_activa'].pk, categoria_uno.pk)
        self.assertEqual(len(context['imagenes']), 2)


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
