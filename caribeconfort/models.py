import uuid

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

class Roles(models.Model):
    nombre=models.CharField(max_length=100)
    descripcion=models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table='roles'

class Usuarios(models.Model):
    roles=models.ForeignKey(Roles, on_delete=models.PROTECT, db_column='idroles')
    nombre=models.CharField(max_length=100)
    apellido=models.CharField(max_length=100)
    correo=models.EmailField(max_length=100, unique=True)
    contrasena=models.CharField(max_length=255)
    estado=models.BooleanField(default=1)

    class Meta:
        db_table='usuarios'

class Hoteles(models.Model):
    nombre=models.CharField(max_length=100)
    descripcion=models.TextField(blank=True, null=True)
    direccion=models.CharField(max_length=100)
    municipio=models.CharField(max_length=100)
    telefono=models.CharField(max_length=20)
    correo=models.EmailField(max_length=100)
    whatsapp=models.CharField(max_length=30, blank=True, default='')
    checkin=models.CharField(max_length=30, blank=True, default='3:00 PM')
    checkout=models.CharField(max_length=30, blank=True, default='12:00 PM')
    recepcion=models.CharField(max_length=100, blank=True, default='24 horas')
    desayuno=models.CharField(max_length=100, blank=True, default='7:00 AM - 10:00 AM')
    fotografias=models.CharField(max_length=255, blank=True, null=True)
    logo=models.ImageField(upload_to='hoteles/logos/', blank=True, null=True)
    smtp_host=models.CharField(max_length=255, blank=True, default='')
    smtp_port=models.PositiveIntegerField(default=587)
    smtp_username=models.CharField(max_length=255, blank=True, default='')
    smtp_from_email=models.EmailField(max_length=254, blank=True, default='')
    smtp_password_encrypted=models.TextField(blank=True, default='')
    smtp_use_tls=models.BooleanField(default=True)

    class Meta:
        db_table='hoteles'

class TipoHabitacion(models.Model):
    nombre=models.CharField(max_length=100)
    descripcion=models.CharField(max_length=100, blank=True, null=True)
    capacidad=models.IntegerField()
    tarifa=models.DecimalField(max_digits=10, decimal_places=2)
    tipo_cama = models.CharField(max_length=50, blank=True, null=True)
    wifi = models.BooleanField(default=True)
    imagen = models.CharField(max_length=255, blank=True, null=True)
    aire = models.CharField(max_length=100, blank=True, null=True)
    televisor = models.CharField(max_length=100, blank=True, null=True)
    precio_desayuno = models.DecimalField(            
        max_digits=10, decimal_places=2,
        default=0
    )

    class Meta:
        db_table='tipohabitacion'

class Habitaciones(models.Model):
    tipohabitacion=models.ForeignKey(TipoHabitacion, on_delete=models.PROTECT, db_column='idtipohabitacion', null=True, blank=True)
    numero=models.CharField(max_length=20, unique=True)
    capacidad=models.IntegerField()
    precio=models.DecimalField(max_digits=10, decimal_places=2)
    estados=[ ('Disponible','Disponible'),
        ('Ocupada','Ocupada'),
        ('Bloqueada','Bloqueada'),
        ('Fuera-de-servicio','Fuera-de-servicio' )]
    estado=models.CharField(max_length=40, choices=estados, default='Disponible')
    imagen = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table='habitaciones'


class Huespedes(models.Model):
    usuarios=models.ForeignKey(Usuarios, on_delete=models.SET_NULL, blank=True, null=True , db_column='idusuarios')
    tipodocumento=models.CharField(max_length=100)
    identificacion=models.CharField(max_length=50, unique=True)
    nombres=models.CharField(max_length=100)
    apellidos=models.CharField(max_length=100)
    telefono=models.CharField(max_length=100)
    direccion=models.CharField(max_length=100)
    correo=models.EmailField(max_length=100, blank=True, null=True)
    nacionalidad=models.CharField(max_length=100)
    informacionadicional=models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        db_table='huespedes'


class TipoConvenio(models.Model):
    nombre=models.CharField(max_length=100)
    descripcion=models.CharField(max_length=255, blank=True, null=True)
    PorcentajeDescuento=models.DecimalField(max_digits=5, decimal_places=2)
    estado=models.BooleanField(default=1)

    class Meta:
        db_table='tipoconvenio'


class ReglaDescuento(models.Model):
    dias_minimos = models.PositiveIntegerField()
    porcentaje = models.DecimalField(max_digits=5, decimal_places=2)
    estado = models.BooleanField(default=True)

    class Meta:
        db_table = 'reglasdescuento'
        ordering = ['dias_minimos']


class CodigosConvenio(models.Model):
    tipoConvenio=models.ForeignKey(TipoConvenio, on_delete=models.PROTECT, db_column='idtipoConvenio')
    Codigo=models.CharField(max_length=20, unique=True)
    sujeto=[
            ('Empresa','Empresa'),
            ('Persona Natural','Persona Natural'),]
    tiposujeto=models.CharField(max_length=100, choices=sujeto, default='Empresa')
    nombresujeto=models.CharField(max_length=150)
    FechaGeneracion=models.DateTimeField(auto_now_add=True)
    FechaExpiracion=models.DateField()
    estados=[
        ('Activo','Activo'),
        ('Usado','Usado'),
        ('Vencido','Vencido'),
    ]
    estado=models.CharField(max_length=20, choices=estados, default='Activo')

    class Meta:
        db_table='codigosconvenio'

class Servicios(models.Model):
    CATEGORIAS = [
        ('Habitación',    'Habitación'),
        ('Alimentación',  'Alimentación'),
        ('Minibar',       'Minibar'),
        ('Recreación',    'Recreación'),
        ('Eventos',       'Eventos'),
        ('Lavandería',    'Lavandería'),
        ('Transporte',    'Transporte'),
        ('Otros',         'Otros'),
    ]
    nombre      = models.CharField(max_length=100)
    descripcion = models.CharField(max_length=255, blank=True, null=True)
    precio      = models.DecimalField(max_digits=10, decimal_places=2)
    categoria   = models.CharField(max_length=50, choices=CATEGORIAS, default='Otros')
    estado      = models.BooleanField(default=1)
    imagen      = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = 'servicios'


class Planes(models.Model):
    nombre      = models.CharField(max_length=100)
    descripcion = models.CharField(max_length=255, blank=True, null=True)
    precio      = models.DecimalField(max_digits=12, decimal_places=2)
    imagen      = models.CharField(max_length=255, null=True, blank=True)
    estado      = models.BooleanField(default=1)
    orden       = models.IntegerField(default=0)
    disponibles  = models.IntegerField(default=10) 
    tipo_habitacion = models.ForeignKey(TipoHabitacion, on_delete=models.PROTECT, db_column='idtipohabitacion', null=True, blank=True)
    Servicios_tipos = models.ManyToManyField(Servicios, blank=True)
    duracion_dias = models.IntegerField(default=5)
    max_adultos = models.PositiveSmallIntegerField(default=4)
    max_ninos = models.PositiveSmallIntegerField(default=4)

    @property
    def rango_adultos(self):
        return range(1, self.max_adultos + 1)

    @property
    def rango_ninos(self):
        return range(1, self.max_ninos + 1)

    class Meta:
            db_table = 'planes'
            ordering = ['orden', 'id']

class Reservas (models.Model):
    codigosConvenio=models.OneToOneField(CodigosConvenio, on_delete=models.SET_NULL,null=True, blank=True, db_column='idCodigosConvenio')
    huespedes=models.ForeignKey(Huespedes, on_delete=models.PROTECT, db_column='idhuespedes')
    habitaciones=models.ForeignKey(Habitaciones, on_delete=models.PROTECT, db_column='idhabitaciones', null=True, blank=True)
    planes = models.ForeignKey(Planes, on_delete=models.PROTECT, db_column='idplanes', null=True, blank=True)
    fechasolicitud=models.DateTimeField(auto_now_add=True)
    fechaentrada=models.DateField()
    fechasalida=models.DateField()
    cantidadacompañantes=models.IntegerField()
    estados=[
        ('Pendiente','Pendiente'),
        ('Confirmada','Confirmada'),
        ('En curso','En curso'),
        ('Cancelada','Cancelada'),
        ('Finalizada','Finalizada'),
        ('Pagada - Por validar','Pagada - Por validar')
    ]
    estado=models.CharField(max_length=50, choices=estados, default='Pendiente')
    valortotal=models.DecimalField(max_digits=10, decimal_places=2)
    recordatorio_dos_dias_enviado=models.BooleanField(default=False)
    recordatorio_un_dia_enviado=models.BooleanField(default=False)

    class Meta:
        db_table='reservas'

class Acompanante(models.Model):
    reserva = models.ForeignKey(Reservas, on_delete=models.CASCADE, related_name='acompanantes')
    nombre_completo = models.CharField(max_length=200)
    documento = models.CharField(max_length=50, blank=True, null=True)
    parentesco = models.CharField(max_length=50, blank=True, null=True) 
    
    def __str__(self):
        return f"{self.nombre_completo} (Reserva #{self.reserva.id})"


class Resena(models.Model):
    reserva = models.OneToOneField(
        Reservas,
        on_delete=models.CASCADE,
        related_name='resena',
    )
    calificacion = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    calificacion_habitacion = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    comentario = models.TextField(blank=True)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    fecha = models.DateTimeField(default=timezone.now)
    correo_enviado = models.BooleanField(default=False)

    class Meta:
        db_table = 'resenas'
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(calificacion__isnull=True)
                    | models.Q(calificacion__gte=1, calificacion__lte=5)
                ),
                name='resena_calificacion_1_5',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(calificacion_habitacion__isnull=True)
                    | models.Q(
                        calificacion_habitacion__gte=1,
                        calificacion_habitacion__lte=5,
                    )
                ),
                name='resena_calif_habitacion_1_5',
            ),
        ]

    def __str__(self):
        return f'Reseña de la reserva #{self.reserva_id}'


class Pagos (models.Model):
    reservas=models.ForeignKey(Reservas, on_delete=models.CASCADE, db_column='idreservas')
    pago_origen=models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='reembolsos',
    )
    fecha=models.DateTimeField(auto_now_add=True)
    valor=models.DecimalField(max_digits=10, decimal_places=2)
    estados=[('Pendiente','Pendiente'),
        ('Efectivo','Efectivo'),
        ('Tarjeta','Tarjeta'),
        ('Transferencia','Transferencia'),
        ('Nequi','Nequi'),
    ]
    metodopago=models.CharField(max_length=60, choices=estados)
    conceptos=[
        ('Reserva', 'Reserva'),
        ('Servicio', 'Servicio'),
        ('Reembolso', 'Reembolso'),
    ]
    concepto=models.CharField(max_length=20, choices=conceptos, default='Reserva')

    class Meta:
        db_table='pagos'


class ServicioReserva(models.Model):
    estados = [
        ('Pendiente', 'Pendiente'),
        ('Aprobado', 'Aprobado'),
        ('Rechazado', 'Rechazado'),
    ]
    METODOS_PAGO_PREFERIDOS = [
        ('Efectivo', 'Efectivo'),
        ('Tarjeta', 'Tarjeta'),
        ('Transferencia', 'Transferencia'),
        ('Nequi', 'Nequi'),
    ]
    reservas=models.ForeignKey(Reservas, on_delete=models.CASCADE, db_column='idreservas')
    servicios=models.ForeignKey(Servicios, on_delete=models.PROTECT, db_column='idservicios')
    pago=models.OneToOneField(Pagos, on_delete=models.SET_NULL, null=True, blank=True, related_name='servicio_reserva')
    cantidad=models.IntegerField()
    valor=models.DecimalField(max_digits=10, decimal_places=2)
    solicitado_por=models.CharField(max_length=100, blank=True, default='')
    beneficiario=models.CharField(max_length=100, blank=True, default='')
    beneficiario_segundo=models.CharField(max_length=100, blank=True, default='')
    motivo_rechazo=models.CharField(max_length=500, blank=True, default='')
    metodo_pago_preferido=models.CharField(
        max_length=20,
        choices=METODOS_PAGO_PREFERIDOS,
        blank=True,
        default='',
    )
    tarjeta_titular=models.CharField(max_length=100, blank=True, default='')
    tarjeta_ultimos4=models.CharField(max_length=4, blank=True, default='')
    nequi_titular=models.CharField(max_length=100, blank=True, default='')
    nequi_celular=models.CharField(max_length=20, blank=True, default='')
    estado=models.CharField(max_length=20, choices=estados, default='Pendiente')
    fecha=models.DateTimeField(auto_now_add=True)

    class Meta:
            db_table='servicioreserva'


class CategoriaGaleria(models.Model):
    nombre = models.CharField(max_length=100)
    icono = models.CharField(max_length=30, default='estrella')
    orden = models.IntegerField(default=0)
    estado = models.BooleanField(default=1)

    class Meta:
        db_table = 'categoriasgaleria'


class ImagenGaleria(models.Model):
    SECCIONES = [
        ('carrusel', 'Carrusel'),
        ('portada', 'Portadas'),
        ('servicio', 'Servicios'),
        ('galeria', 'Galería pública'),
    ]
    categoria = models.ForeignKey(CategoriaGaleria, on_delete=models.PROTECT, db_column='idcategoriasgaleria')
    titulo = models.CharField(max_length=100, blank=True, null=True)
    imagen = models.CharField(max_length=255)
    seccion = models.CharField(max_length=20, choices=SECCIONES, default='galeria', db_index=True)
    fecha = models.DateTimeField(auto_now_add=True)
    estado = models.BooleanField(default=1)

    class Meta:
        db_table = 'imagenesgaleria'


class CaracteristicaPlan(models.Model):
    plan   = models.ForeignKey(
        Planes,
        on_delete=models.CASCADE,
        related_name='caracteristicas',
        db_column='idplanes'
    )
    icono  = models.CharField(max_length=30, default='estrella')
    texto  = models.CharField(max_length=100)
    orden  = models.IntegerField(default=0)

    class Meta:
        db_table = 'caracteristicasplan'
        ordering = ['orden', 'id']
