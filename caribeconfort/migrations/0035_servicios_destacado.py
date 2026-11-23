from django.db import migrations, models


def marcar_servicio_recomendado(apps, schema_editor):
    Servicios = apps.get_model('caribeconfort', 'Servicios')
    db_alias = schema_editor.connection.alias
    destacados = Servicios.objects.using(db_alias).filter(destacado=True)
    if not destacados.exists():
        primero = Servicios.objects.using(db_alias).filter(estado=True).order_by('nombre', 'id').first()
        if primero:
            primero.destacado = True
            primero.save(using=db_alias, update_fields=['destacado'])


class Migration(migrations.Migration):

    dependencies = [
        ('caribeconfort', '0034_pagos_nequi_method'),
    ]

    operations = [
        migrations.AddField(
            model_name='servicios',
            name='destacado',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(marcar_servicio_recomendado, migrations.RunPython.noop),
    ]
