import json
from contextlib import nullcontext
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

from caribeconfort.models import Resena
from caribeconfort.views import (
    _enviar_invitacion_resena,
    dejar_resena,
    solicitar_servicio,
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
            'caribeconfort.views.send_mail',
            return_value=1,
        ) as send_mail:
            resultado = _enviar_invitacion_resena(
                reserva,
                RequestFactory().get('/'),
            )

        self.assertTrue(resultado)
        self.assertTrue(resena.correo_enviado)
        resena.save.assert_called_once_with(update_fields=['correo_enviado'])
        self.assertEqual(
            send_mail.call_args.kwargs['recipient_list'],
            ['cliente@example.com'],
        )


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
