from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('caribeconfort', '0019_alter_reservas_estado'),
    ]

    operations = [
        migrations.AlterField(
            model_name='reservas',
            name='codigosConvenio',
            field=models.OneToOneField(
                blank=True,
                db_column='idCodigosConvenio',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to='caribeconfort.codigosconvenio',
            ),
        ),
    ]
