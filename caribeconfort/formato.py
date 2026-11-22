from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def formato_numero_colombiano(valor, decimales=0):
    """Devuelve un número con punto para miles y coma para decimales."""
    try:
        decimales = max(0, min(6, int(decimales)))
        numero = Decimal(str(valor))
        if not numero.is_finite():
            return ''
        numero = numero.quantize(
            Decimal('1').scaleb(-decimales),
            rounding=ROUND_HALF_UP,
        )
    except (InvalidOperation, TypeError, ValueError):
        return ''

    signo = '-' if numero < 0 else ''
    texto = f'{abs(numero):,.{decimales}f}'
    texto = texto.replace(',', '\0').replace('.', ',').replace('\0', '.')
    return f'{signo}{texto}'
