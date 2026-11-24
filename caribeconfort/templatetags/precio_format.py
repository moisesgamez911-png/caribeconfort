from decimal import Decimal, InvalidOperation

from django import template

from caribeconfort.formato import formato_numero_colombiano


register = template.Library()


@register.filter(name='precio')
def precio(valor, decimales=0):
    return formato_numero_colombiano(valor, decimales)


@register.filter(name='absoluto')
def absoluto(valor):
    try:
        return abs(Decimal(str(valor)))
    except (InvalidOperation, TypeError, ValueError):
        return 0
