from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('caribeconfort', '0033_pending_service_totals'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pagos',
            name='metodopago',
            field=models.CharField(
                choices=[
                    ('Pendiente', 'Pendiente'),
                    ('Efectivo', 'Efectivo'),
                    ('Tarjeta', 'Tarjeta'),
                    ('Transferencia', 'Transferencia'),
                    ('Nequi', 'Nequi'),
                ],
                max_length=60,
            ),
        ),
    ]
