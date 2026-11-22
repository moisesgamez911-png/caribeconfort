from decimal import Decimal

from django.db import migrations
from django.db.models import F


def remove_unapproved_service_charges(apps, schema_editor):
    ServicioReserva = apps.get_model('caribeconfort', 'ServicioReserva')
    Reservas = apps.get_model('caribeconfort', 'Reservas')
    alias = schema_editor.connection.alias

    # Before this migration, requesting a service immediately increased the
    # reservation total. Pending requests must remain separate until approved.
    pending_by_reservation = {}
    for item in ServicioReserva.objects.using(alias).filter(
        estado='Pendiente',
    ).values('reservas_id', 'valor'):
        pending_by_reservation[item['reservas_id']] = (
            pending_by_reservation.get(item['reservas_id'], Decimal('0.00'))
            + item['valor']
        )

    for reservation_id, pending_total in pending_by_reservation.items():
        reserva = Reservas.objects.using(alias).filter(id=reservation_id).first()
        if not reserva:
            continue
        reserva.valortotal = max(
            Decimal('0.00'),
            reserva.valortotal - pending_total,
        )
        reserva.save(update_fields=['valortotal'])


def restore_unapproved_service_charges(apps, schema_editor):
    ServicioReserva = apps.get_model('caribeconfort', 'ServicioReserva')
    Reservas = apps.get_model('caribeconfort', 'Reservas')
    alias = schema_editor.connection.alias

    pending_by_reservation = {}
    for item in ServicioReserva.objects.using(alias).filter(
        estado='Pendiente',
    ).values('reservas_id', 'valor'):
        pending_by_reservation[item['reservas_id']] = (
            pending_by_reservation.get(item['reservas_id'], Decimal('0.00'))
            + item['valor']
        )

    for reservation_id, pending_total in pending_by_reservation.items():
        Reservas.objects.using(alias).filter(id=reservation_id).update(
            valortotal=F('valortotal') + pending_total,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('caribeconfort', '0032_servicioreserva_beneficiario_and_more'),
    ]

    operations = [
        migrations.RunPython(
            remove_unapproved_service_charges,
            restore_unapproved_service_charges,
        ),
    ]
