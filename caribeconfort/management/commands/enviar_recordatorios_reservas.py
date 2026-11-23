import logging
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from caribeconfort.models import Reservas
from caribeconfort.views import _enviar_correo_hotel, finalizar_reservas_vencidas


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Envía recordatorios para reservas confirmadas que comienzan en uno o dos días.'

    def handle(self, *args, **options):
        hoy = timezone.localdate()
        enviados = 0
        errores = 0
        finalizadas = finalizar_reservas_vencidas(enviar_invitaciones=True)
        recordatorios = (
            (2, 'recordatorio_dos_dias_enviado'),
            (1, 'recordatorio_un_dia_enviado'),
        )

        for dias, campo_enviado in recordatorios:
            fecha_entrada = hoy + timedelta(days=dias)
            ids_reservas = Reservas.objects.filter(
                fechaentrada=fecha_entrada,
                estado='Confirmada',
                **{campo_enviado: False},
            ).values_list('id', flat=True)

            for reserva_id in ids_reservas:
                try:
                    with transaction.atomic():
                        reserva = Reservas.objects.select_for_update().select_related(
                            'huespedes__usuarios',
                        ).get(id=reserva_id)
                        if (
                            reserva.estado != 'Confirmada'
                            or reserva.fechaentrada != fecha_entrada
                            or getattr(reserva, campo_enviado)
                        ):
                            continue

                        destinatario = (reserva.huespedes.correo or '').strip()
                        if not destinatario and reserva.huespedes.usuarios_id:
                            destinatario = (
                                reserva.huespedes.usuarios.correo or ''
                            ).strip()
                        if not destinatario:
                            errores += 1
                            self.stderr.write(
                                f'La reserva CC-{reserva.id:04d} no tiene correo.'
                            )
                            continue

                        mensaje = (
                            f'Hola {reserva.huespedes.nombres},\n\n'
                            f'Te recordamos que tu estadía comienza el '
                            f'{reserva.fechaentrada:%d/%m/%Y} y termina el '
                            f'{reserva.fechasalida:%d/%m/%Y}. '
                            f'Tu reserva es CC-{reserva.id:04d}.'
                        )
                        if dias == 1:
                            mensaje += (
                                '\n\nDe acuerdo con las políticas del hotel, '
                                'si no te presentas, el abono del 50% no será '
                                'reembolsable. Te esperamos.'
                            )
                        else:
                            mensaje += (
                                '\n\nTe esperamos; si necesitas coordinar '
                                'algún detalle de llegada, comunícate con '
                                'recepción.'
                            )

                        _enviar_correo_hotel(
                            f'Recordatorio de reserva CC-{reserva.id:04d}',
                            (
                                'Tu estadía comienza mañana'
                                if dias == 1
                                else 'Tu estadía comienza en dos días'
                            ),
                            mensaje,
                            destinatario,
                        )
                        setattr(reserva, campo_enviado, True)
                        reserva.save(update_fields=[campo_enviado])
                        enviados += 1
                        self.stdout.write(
                            f'Reserva CC-{reserva.id:04d}: recordatorio de '
                            f'{dias} día(s) enviado correctamente.'
                        )
                except Exception:
                    errores += 1
                    logger.exception(
                        'No se pudo enviar el recordatorio de %s día(s) '
                        'para la reserva CC-%s.',
                        dias,
                        reserva_id,
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f'Estancias finalizadas: {finalizadas}; recordatorios enviados: {enviados}; errores: {errores}.'
            )
        )
        if errores:
            raise CommandError(
                f'No se pudieron enviar {errores} recordatorios.'
            )
