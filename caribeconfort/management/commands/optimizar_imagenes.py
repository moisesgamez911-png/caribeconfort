from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.core.management.base import BaseCommand, CommandError

from caribeconfort.image_optimization import guardar_variante_webp, ruta_variante_webp


EXTENSIONES_IMAGEN = {'.jpg', '.jpeg', '.png'}
TAMANO_MINIMO = 100_000


class Command(BaseCommand):
    help = 'Crea versiones WebP de alta calidad para las imágenes existentes en MEDIA_ROOT.'

    def handle(self, *args, **options):
        raiz = Path(settings.MEDIA_ROOT)
        if not raiz.is_dir():
            raise CommandError(f'No existe el directorio de medios: {raiz}')

        almacenamiento = FileSystemStorage(location=raiz)
        creadas = omitidas = 0
        errores = []
        for archivo in sorted(raiz.rglob('*')):
            if (
                not archivo.is_file()
                or archivo.suffix.lower() not in EXTENSIONES_IMAGEN
                or archivo.stat().st_size < TAMANO_MINIMO
            ):
                continue

            ruta = archivo.relative_to(raiz).as_posix()
            ruta_webp = ruta_variante_webp(ruta)
            if almacenamiento.exists(ruta_webp):
                omitidas += 1
                continue

            try:
                variante = guardar_variante_webp(almacenamiento, ruta)
            except (OSError, ValueError) as error:
                errores.append(f'{ruta}: {error}')
                continue
            creadas += bool(variante)

        if errores:
            for error in errores:
                self.stderr.write(self.style.ERROR(error))
            raise CommandError(
                f'No se pudieron optimizar {len(errores)} imágenes; '
                f'variantes creadas: {creadas}.'
            )

        self.stdout.write(self.style.SUCCESS(
            f'Variantes WebP creadas: {creadas}; ya existentes: {omitidas}.'
        ))
