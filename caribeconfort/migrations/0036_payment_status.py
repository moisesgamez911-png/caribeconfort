from django.db import migrations, models


def marcar_pagos_no_confirmados(apps, schema_editor):
    Pagos = apps.get_model('caribeconfort', 'Pagos')
    Reservas = apps.get_model('caribeconfort', 'Reservas')
    db_alias = schema_editor.connection.alias

    Pagos.objects.using(db_alias).filter(
        metodopago='Pendiente',
    ).update(estado_pago='Pendiente')
    Pagos.objects.using(db_alias).filter(
        reservas__in=Reservas.objects.using(db_alias).filter(
            estado='Pagada - Por validar',
        ),
    ).exclude(
        metodopago='Pendiente',
    ).update(estado_pago='Pendiente')


class Migration(migrations.Migration):

    dependencies = [
        ('caribeconfort', '0035_servicios_destacado'),
    ]

    operations = [
        migrations.AddField(
            model_name='pagos',
            name='estado_pago',
            field=models.CharField(
                choices=[
                    ('Pendiente', 'Pendiente'),
                    ('Confirmado', 'Confirmado'),
                    ('Anulado', 'Anulado'),
                ],
                default='Confirmado',
                max_length=20,
            ),
        ),
        migrations.RunPython(
            marcar_pagos_no_confirmados,
            migrations.RunPython.noop,
        ),
    ]
