"""Small presentation filter for legacy strings stored with UTF-8 mojibake."""

from django import template


register = template.Library()


@register.filter
def reparar_texto(value):
    if value is None:
        return value
    texto = str(value)
    for _ in range(2):
        if not any(marca in texto for marca in ('Ã', 'Â', 'â€')):
            break
        try:
            corregido = texto.encode('cp1252').decode('utf-8')
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
        if corregido.count('�') > texto.count('�'):
            break
        texto = corregido
    return texto
