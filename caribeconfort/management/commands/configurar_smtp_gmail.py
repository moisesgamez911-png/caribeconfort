from getpass import getpass
from smtplib import SMTPException

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email

from caribeconfort.models import Hoteles
from caribeconfort.views import _conexion_correo_hotel


class Command(BaseCommand):
    help = 'Guarda las credenciales Gmail SMTP cifradas y comprueba la conexión.'

    def handle(self, *args, **options):
        clave = getattr(settings, 'EMAIL_CREDENTIAL_ENCRYPTION_KEY', '')
        if not clave:
            raise CommandError(
                'Django no detecta EMAIL_CREDENTIAL_ENCRYPTION_KEY. '
                'Abre una terminal nueva y vuelve a ejecutar este comando.'
            )
        try:
            fernet = Fernet(clave.encode('ascii'))
        except (ValueError, UnicodeError) as error:
            raise CommandError(
                'EMAIL_CREDENTIAL_ENCRYPTION_KEY no es una clave Fernet válida.'
            ) from error

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
        contrasena = ''.join(contrasena.split())

        if crear_hotel:
            hotel = Hoteles.objects.create(**datos_hotel)

        hotel.smtp_host = 'smtp.gmail.com'
        hotel.smtp_port = 587
        hotel.smtp_username = usuario
        hotel.smtp_from_email = remitente
        hotel.smtp_password_encrypted = fernet.encrypt(
            contrasena.encode('utf-8')
        ).decode('ascii')
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
        except (OSError, SMTPException, RuntimeError) as error:
            raise CommandError(
                'Los datos se guardaron cifrados, pero Gmail no aceptó la conexión. '
                'Verifica la contraseña de aplicación y vuelve a ejecutar el comando.'
            ) from error
        finally:
            conexion.close()

        self.stdout.write(self.style.SUCCESS(
            'Configuración Gmail guardada y conexión SMTP verificada. No se envió ningún correo.'
        ))
