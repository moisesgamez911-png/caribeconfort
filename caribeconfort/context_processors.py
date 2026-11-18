from caribeconfort.models import Reservas, ServicioReserva


def notificaciones_administracion(request):
    if request.session.get('rol') not in {'Administrador', 'Recepcionista'}:
        return {}
    return {
        'notificaciones_pendientes': Reservas.objects.filter(
            estado='Pagada - Por validar',
        ).count(),
        'notificaciones_servicios': ServicioReserva.objects.filter(
            estado='Pendiente',
            pago__metodopago='Pendiente',
        ).count(),
    }
