from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('caribeconfort', '0030_hoteles_campos_publicos'),
    ]

    operations = [
        migrations.AddField(
            model_name='servicioreserva',
            name='tarjeta_titular',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AddField(
            model_name='servicioreserva',
            name='tarjeta_ultimos4',
            field=models.CharField(blank=True, default='', max_length=4),
        ),
        migrations.AddField(
            model_name='servicioreserva',
            name='nequi_titular',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AddField(
            model_name='servicioreserva',
            name='nequi_celular',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
    ]
