from getpass import getpass
from smtplib import SMTPAuthenticationError, SMTPException

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email

from caribeconfort.models import Hoteles
from caribeconfort.views import (
    _cifrar_contrasena_smtp,
    _conexion_correo_hotel,
    _normalizar_contrasena_smtp,
)


class Command(BaseCommand):
    help = 'Guarda las credenciales Gmail SMTP cifradas y comprueba la conexión.'

    def handle(self, *args, **options):
        hotel = Hoteles.objects.order_by('id').first()
        crear_hotel = hotel is None
        if crear_hotel:
            self.stdout.write(self.style.WARNING(
                'La base de datos no tiene los datos generales del hotel. '
                'Completa estos datos para crear el registro y guardar el SMTP.'
            ))
            datos_hotel = {
                'nombre': input('Nombre del hotel [Caribe Confort]: ').strip() or 'Caribe Confort',
                'direccion': input('Dirección física del hotel: ').strip(),
                'municipio': input('Municipio [Riohacha]: ').strip() or 'Riohacha',
                'telefono': input('Teléfono de contacto del hotel: ').strip(),
                'correo': input('Correo de contacto del hotel: ').strip(),
            }
            if not all(datos_hotel.values()):
                raise CommandError(
                    'Faltan datos generales. No se creó el hotel; ejecuta de nuevo el comando.'
                )
            try:
                validate_email(datos_hotel['correo'])
            except ValidationError as error:
                raise CommandError('Ingresa un correo de contacto válido.') from error

        usuario = input('Dirección Gmail completa: ').strip()
        remitente = input(f'Correo remitente [{usuario}]: ').strip() or usuario
        try:
            validate_email(usuario)
            validate_email(remitente)
        except ValidationError as error:
            raise CommandError('Ingresa una dirección Gmail válida.') from error

        contrasena = getpass('Contraseña de aplicación de Gmail (no se mostrará): ')
        if not contrasena:
            raise CommandError('La contraseña de aplicación no puede estar vacía.')
        contrasena = _normalizar_contrasena_smtp('smtp.gmail.com', contrasena)

        if crear_hotel:
            hotel = Hoteles.objects.create(**datos_hotel)

        hotel.smtp_host = 'smtp.gmail.com'
        hotel.smtp_port = 587
        hotel.smtp_username = usuario
        hotel.smtp_from_email = remitente
        try:
            hotel.smtp_password_encrypted = _cifrar_contrasena_smtp(contrasena)
        except ValueError as error:
            raise CommandError(str(error)) from error
        hotel.smtp_use_tls = True
        hotel.save(update_fields=[
            'smtp_host',
            'smtp_port',
            'smtp_username',
            'smtp_from_email',
            'smtp_password_encrypted',
            'smtp_use_tls',
        ])
        contrasena = None

        conexion, _ = _conexion_correo_hotel()
        try:
            conectado = conexion.open()
            if not conectado:
                raise RuntimeError('El backend SMTP no abrió la conexión.')
        except SMTPAuthenticationError as error:
            raise CommandError(
                'La contraseña quedó guardada y cifrada en esta base de datos, pero Gmail rechazó el usuario o la contraseña (535). '
                'El usuario debe ser la misma cuenta que generó la contraseña de aplicación.'
            ) from error
        except (OSError, SMTPException, RuntimeError, ValueError) as error:
            raise CommandError(
                'La contraseña quedó guardada y cifrada en esta base de datos, pero no se pudo verificar la conexión SMTP. '
                'Comprueba la conexión y la configuración.'
            ) from error
        finally:
            conexion.close()

        self.stdout.write(self.style.SUCCESS(
            'Configuración Gmail guardada y conexión SMTP autenticada. No se envió ningún correo.'
        ))
