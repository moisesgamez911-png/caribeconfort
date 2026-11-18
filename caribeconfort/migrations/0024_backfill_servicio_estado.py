from django.db import migrations


def marcar_servicios_pagados_como_aprobados(apps, schema_editor):
    ServicioReserva = apps.get_model('caribeconfort', 'ServicioReserva')
    alias = schema_editor.connection.alias
    ServicioReserva.objects.using(alias).filter(
        pago__isnull=False,
    ).exclude(
        pago__metodopago='Pendiente',
    ).update(estado='Aprobado')


class Migration(migrations.Migration):

    dependencies = [
        ('caribeconfort', '0023_servicioreserva_estado'),
    ]

    operations = [
        migrations.RunPython(marcar_servicios_pagados_como_aprobados, migrations.RunPython.noop),
    ]
