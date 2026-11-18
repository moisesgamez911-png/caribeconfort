from caribeconfort.models import Hoteles, Reservas, ServicioReserva


def identidad_hotel(request):
    hotel = Hoteles.objects.order_by('id').only('nombre', 'logo').first()
    return {
        'nombre_hotel': hotel.nombre if hotel else 'Caribe Confort',
        'logo_hotel_url': hotel.logo.url if hotel and hotel.logo else '',
    }


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
