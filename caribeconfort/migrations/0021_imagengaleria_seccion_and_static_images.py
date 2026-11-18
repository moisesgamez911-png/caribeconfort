from django.db import migrations, models


STATIC_IMAGES = [
    ('BASO.jpg', 'servicio'),
    ('F2.jpg', 'portada'),
    ('FBAR.jpg', 'servicio'),
    ('foto1.png', 'carrusel'),
    ('foto2.png', 'carrusel'),
    ('foto3.png', 'carrusel'),
    ('foto4.png', 'carrusel'),
    ('HotelInterfaz2.png', 'portada'),
    ('LCF2FINAL2.png', 'portada'),
    ('LCFFINAL.png', 'portada'),
    ('Logo administrador c.png', 'portada'),
    ('Logo Caribe.png', 'portada'),
    ('pexels-30nudos-adicora-164429726-10877598.jpg', 'portada'),
    ('pexels-30nudos-adicora-164429726-11061846 (1).jpg', 'portada'),
    ('pexels-30nudos-adicora-164429726-11061846.jpg', 'portada'),
    ('pexels-30nudos-adicora-164429726-11061847.jpg', 'portada'),
    ('pexels-30nudos-adicora-164429726-11061866.jpg', 'portada'),
    ('pexels-30nudos-adicora-164429726-11062795.jpg', 'portada'),
    ('pexels-30nudos-adicora-164429726-11062799.jpg', 'portada'),
    ('pexels-30nudos-adicora-164429726-11063549.jpg', 'portada'),
    ('pexels-30nudos-adicora-164429726-11063553.jpg', 'portada'),
    ('pexels-30nudos-adicora-164429726-11452052.jpg', 'portada'),
    ('pexels-30nudos-adicora-164429726-13696647 (1).jpg', 'portada'),
    ('pexels-30nudos-adicora-164429726-13696647 (2).jpg', 'portada'),
    ('pexels-30nudos-adicora-164429726-13696647.jpg', 'portada'),
    ('pexels-bertellifotografia-12513475.jpg', 'portada'),
    ('pexels-bertellifotografia-9056663.jpg', 'portada'),
    ('pexels-manuel-aldana-321951004-13893887.jpg', 'portada'),
    ('pexels-muhammedtarikkahraman-17395984.jpg', 'portada'),
    ('pexels-quang-nguyen-vinh-222549-14025904.jpg', 'portada'),
    ('pexels-quang-nguyen-vinh-222549-14025907.jpg', 'portada'),
    ('pexels-rebornfilmes-27638193.jpg', 'portada'),
    ('plan1.jpg', 'portada'),
    ('plan2.jpg', 'portada'),
    ('plan3.jpg', 'portada'),
    ('planes.jpg', 'portada'),
]


def seed_static_images(apps, schema_editor):
    Category = apps.get_model('caribeconfort', 'CategoriaGaleria')
    Image = apps.get_model('caribeconfort', 'ImagenGaleria')
    database = schema_editor.connection.alias

    section_labels = {
        'carrusel': ('Carrusel', 'imagen'),
        'portada': ('Portadas', 'imagen'),
        'servicio': ('Servicios', 'estrella'),
        'galeria': ('Galería', 'imagen'),
    }
    categories = {}
    for section, (name, icon) in section_labels.items():
        category, _ = Category.objects.using(database).get_or_create(
            nombre=name,
            defaults={'icono': icon, 'orden': len(categories), 'estado': True},
        )
        categories[section] = category

    for filename, section in STATIC_IMAGES:
        image_path = f'img/imagenes/{filename}'
        Image.objects.using(database).get_or_create(
            imagen=image_path,
            defaults={
                'categoria_id': categories[section].pk,
                'titulo': filename.rsplit('.', 1)[0][:100],
                'seccion': section,
                'estado': True,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ('caribeconfort', '0020_reservas_codigosconvenio_one_to_one'),
    ]

    operations = [
        migrations.AddField(
            model_name='imagengaleria',
            name='seccion',
            field=models.CharField(
                choices=[
                    ('carrusel', 'Carrusel'),
                    ('portada', 'Portadas'),
                    ('servicio', 'Servicios'),
                    ('galeria', 'Galería pública'),
                ],
                db_index=True,
                default='galeria',
                max_length=20,
            ),
        ),
        migrations.RunPython(seed_static_images, migrations.RunPython.noop),
    ]
