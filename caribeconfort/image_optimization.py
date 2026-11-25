from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile
from PIL import Image, ImageOps


EXTENSIONES_OPTIMIZABLES = {'.jpg', '.jpeg', '.png'}


def ruta_variante_webp(ruta):
    if Path(ruta).suffix.lower() in EXTENSIONES_OPTIMIZABLES:
        return Path(ruta).with_suffix('.webp').as_posix()
    return ruta


def guardar_variante_webp(almacenamiento, ruta):
    if Path(ruta).suffix.lower() not in EXTENSIONES_OPTIMIZABLES:
        return ''

    with Image.open(almacenamiento.path(ruta)) as original:
        imagen = ImageOps.exif_transpose(original)
        imagen.thumbnail((2560, 2560), Image.Resampling.LANCZOS)
        if imagen.mode not in {'RGB', 'RGBA'}:
            imagen = imagen.convert('RGBA' if 'A' in imagen.getbands() else 'RGB')
        salida = BytesIO()
        imagen.save(salida, format='WEBP', quality=92, method=4)

    contenido = salida.getvalue()
    if len(contenido) >= almacenamiento.size(ruta):
        return ''
    ruta_webp = ruta_variante_webp(ruta)
    try:
        return almacenamiento.save(ruta_webp, ContentFile(contenido))
    except OSError:
        almacenamiento.delete(ruta_webp)
        raise


def eliminar_variante_webp(almacenamiento, ruta):
    if ruta_variante_webp(ruta) != ruta:
        almacenamiento.delete(ruta_variante_webp(ruta))
