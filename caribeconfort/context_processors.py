from caribeconfort.models import Hoteles, Reservas, ServicioReserva


def identidad_hotel(request):
    hotel = Hoteles.objects.order_by('id').first()
    return {
        'nombre_hotel': hotel.nombre if hotel else 'Caribe Confort',
        'logo_hotel_url': hotel.logo.url if hotel and hotel.logo else '',
        'direccion_hotel': hotel.direccion if hotel else '',
        'municipio_hotel': hotel.municipio if hotel else 'Riohacha',
        'telefono_hotel': hotel.telefono if hotel else '',
        'correo_hotel': hotel.correo if hotel else '',
        'whatsapp_hotel': hotel.whatsapp if hotel else '',
        'descripcion_hotel': hotel.descripcion if hotel else '',
        'checkin_hotel': hotel.checkin if hotel else '3:00 PM',
        'checkout_hotel': hotel.checkout if hotel else '12:00 PM',
        'recepcion_hotel': hotel.recepcion if hotel else '24 horas',
        'desayuno_hotel': hotel.desayuno if hotel else '7:00 AM - 10:00 AM',
    }


def notificaciones_administracion(request):
    if request.session.get('rol') not in {'Administrador', 'Recepcionista'}:
        return {}
    reservas = Reservas.objects.filter(
        estado='Pagada - Por validar',
    ).select_related(
        'huespedes',
        'habitaciones',
        'planes',
    ).order_by('-fechasolicitud')
    servicios = ServicioReserva.objects.filter(
        estado='Pendiente',
        pago__metodopago='Pendiente',
    ).select_related(
        'reservas__huespedes',
        'reservas__habitaciones',
        'reservas__planes',
        'servicios',
    ).order_by('-fecha')
    total_reservas = reservas.count()
    total_servicios = servicios.count()
    return {
        'notificaciones_pendientes': total_reservas,
        'notificaciones_servicios': total_servicios,
        'total_notificaciones': total_reservas + total_servicios,
        'reservas_notificaciones': reservas[:5],
        'servicios_notificaciones': servicios[:5],
    }
