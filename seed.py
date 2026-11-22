from caribeconfort.models import TipoHabitacion, Habitaciones

# 1. Crear los tipos
t_est, _ = TipoHabitacion.objects.get_or_create(nombre='Estándar', defaults={'capacidad': 2, 'tarifa': 120000, 'descripcion': 'Cómoda'})
t_vista, _ = TipoHabitacion.objects.get_or_create(nombre='Vista al Mar', defaults={'capacidad': 2, 'tarifa': 160000, 'descripcion': 'Vista'})
t_suite, _ = TipoHabitacion.objects.get_or_create(nombre='Suite Presidencial', defaults={'capacidad': 4, 'tarifa': 250000, 'descripcion': 'Suite'})

# 2. Crear las habitaciones (sin el campo piso)
for i in range(101, 106):
    Habitaciones.objects.get_or_create(numero=str(i), defaults={'tipohabitacion': t_est, 'capacidad': 2, 'precio': 120000, 'estado': 'Disponible'})

for i in range(201, 206):
    Habitaciones.objects.get_or_create(numero=str(i), defaults={'tipohabitacion': t_vista, 'capacidad': 2, 'precio': 160000, 'estado': 'Disponible'})

for i in range(301, 306):
    Habitaciones.objects.get_or_create(numero=str(i), defaults={'tipohabitacion': t_suite, 'capacidad': 4, 'precio': 250000, 'estado': 'Disponible'})

print(f"✅ ¡Éxito! Total en base de datos: {Habitaciones.objects.count()}")