from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from caribeconfort.models import CategoriaGaleria, ImagenGaleria, Servicios


IMAGENES_SERVICIOS = ('foto1.png', 'foto2.png', 'foto3.png', 'foto4.png')
EXTENSIONES_IMAGEN = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}


class Command(BaseCommand):
    help = 'Asigna imágenes locales a los servicios y registra imágenes en la galería.'

    def handle(self, *args, **options):
        if not settings.STATICFILES_DIRS:
            raise CommandError('No hay directorios estáticos configurados.')

        directorio_imagenes = (
            Path(settings.STATICFILES_DIRS[0]) / 'img' / 'imagenes'
        )
        if not directorio_imagenes.is_dir():
            raise CommandError(
                f'No existe el directorio de imágenes estáticas: {directorio_imagenes}'
            )

        imagenes_servicios = [
            nombre for nombre in IMAGENES_SERVICIOS
            if (directorio_imagenes / nombre).is_file()
        ]
        if not imagenes_servicios:
            raise CommandError(
                'No se encontraron foto1.png, foto2.png, foto3.png ni foto4.png.'
            )

        imagenes_galeria = sorted(
            archivo for archivo in directorio_imagenes.iterdir()
            if archivo.is_file() and archivo.suffix.lower() in EXTENSIONES_IMAGEN
        )
        if not imagenes_galeria:
            raise CommandError(
                f'No se encontraron imágenes en {directorio_imagenes}.'
            )

        with transaction.atomic():
            categoria = CategoriaGaleria.objects.filter(
                nombre__iexact='Galería',
            ).order_by('id').first()
            if categoria is None:
                categoria = CategoriaGaleria.objects.create(
                    nombre='Galería',
                    icono='imagen',
                    orden=0,
                    estado=True,
                )
            elif not categoria.estado:
                categoria.estado = True
                categoria.save(update_fields=['estado'])

            servicios = list(Servicios.objects.order_by('id'))
            for indice, servicio in enumerate(servicios):
                nombre = imagenes_servicios[indice % len(imagenes_servicios)]
                servicio.imagen = f'img/imagenes/{nombre}'
                servicio.save(update_fields=['imagen'])

            creadas = 0
            for archivo in imagenes_galeria:
                ruta = f'img/imagenes/{archivo.name}'
                imagen, creada = ImagenGaleria.objects.get_or_create(
                    imagen=ruta,
                    seccion='galeria',
                    categoria=categoria,
                    defaults={
                        'titulo': archivo.stem[:100],
                        'estado': True,
                    },
                )
                if not creada and not imagen.estado:
                    imagen.estado = True
                    imagen.save(update_fields=['estado'])
                creadas += int(creada)

        self.stdout.write(
            self.style.SUCCESS(
                f'Servicios actualizados: {len(servicios)}; '
                f'imágenes de galería creadas: {creadas}.'
            )
        )
