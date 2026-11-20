from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('caribeconfort', '0029_pagos_pago_origen_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='hoteles',
            name='whatsapp',
            field=models.CharField(blank=True, default='', max_length=30),
        ),
        migrations.AddField(
            model_name='hoteles',
            name='checkin',
            field=models.CharField(blank=True, default='3:00 PM', max_length=30),
        ),
        migrations.AddField(
            model_name='hoteles',
            name='checkout',
            field=models.CharField(blank=True, default='12:00 PM', max_length=30),
        ),
        migrations.AddField(
            model_name='hoteles',
            name='recepcion',
            field=models.CharField(blank=True, default='24 horas', max_length=100),
        ),
        migrations.AddField(
            model_name='hoteles',
            name='desayuno',
            field=models.CharField(blank=True, default='7:00 AM - 10:00 AM', max_length=100),
        ),
    ]
