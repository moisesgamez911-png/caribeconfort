# Contexto del proyecto Caribe Confort

## Descripción

Aplicación web para la operación de un hotel en Riohacha. Incluye una experiencia pública para clientes y herramientas de administración y recepción.

## Stack

- Backend: Django y Python.
- Base de datos: MySQL.
- Interfaz: templates HTML de Django, CSS y JavaScript.
- Archivos estáticos y multimedia: carpeta `caribeconfort/public`.
- Zona horaria: `America/Bogota`.

## Reglas de desarrollo

- No iniciar el servidor (`runserver`) ni usar Playwright para estas tareas; validar con comprobaciones locales.
- Mantener los estilos en archivos CSS externos, no dentro de los templates.
- Formatear CSS con el selector en una línea y cada propiedad en su propia línea.
- La autenticación y los roles de la aplicación usan `request.session`; no usar el modelo `User` de Django para la lógica propia del proyecto.
- Preservar etiquetas y lógica de Django, formularios, rutas, peticiones y variables de contexto existentes.
- No guardar credenciales ni datos sensibles en documentación o código nuevo.

## Roles

- **Administrador:** gestión general del hotel, usuarios, habitaciones, reservas, servicios, pagos, convenios, configuración y reportes.
- **Recepcionista:** atención de huéspedes, reservas, check-in/check-out y registro de pagos.
- **Cliente:** consulta y creación de reservas, pagos, gestión de perfil y consulta del historial de reservas.

## Diseño

- Tipografías de referencia: `Cormorant Garamond` y `Plus Jakarta Sans`.
- Colores principales: verde oscuro `#16484B`, dorado `#C6A15B` y fondo claro `#FAF8F5`.
- Los templates de cliente usan CSS separado en archivos estáticos.

## Funcionalidad existente

- Reservas de habitaciones y planes.
- Gestión de habitaciones, servicios y planes.
- Pagos, registro de acompañantes y procesos de check-in/check-out.
- Paneles separados para administración y recepción.
- Reportes de operación.
- Perfil e historial de reservas de clientes.
- Reseñas vinculadas a reservas finalizadas, mediante token UUID y calificación de 1 a 5.
- Cambio de idioma español/inglés con el middleware de localización de Django.

## Reseñas

El modelo `Resena` se relaciona uno a uno con `Reservas`; guarda token único, fecha, comentario y calificación. Al completar el check-out se intenta enviar una invitación individual por correo. Las reservas vencidas también se finalizan y se procesan para el envío de invitaciones. El cliente envía la reseña desde la ruta con token.

## Correo SMTP

El correo puede configurarse desde el panel del administrador o mediante las variables de entorno `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` y `DEFAULT_FROM_EMAIL`. La contraseña guardada desde el panel se cifra con Fernet; antes de guardarla, define `EMAIL_CREDENTIAL_ENCRYPTION_KEY` en el entorno con una clave generada así:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Mantén esa clave fuera del repositorio y consérvala sin cambios mientras haya contraseñas cifradas en la base de datos. Aplica las migraciones pendientes antes de usar la configuración SMTP o la identidad del hotel desde el panel.

## Identidad, pagos y documentos

El nombre público y el logo del hotel se actualizan desde **Administrador → Configuración**. El logo admite imágenes y se muestra junto al nombre con las tipografías de marca `Cormorant Garamond` y `Plus Jakarta Sans`.

Las facturas por reserva y los certificados de pagos se descargan en PDF con ReportLab. Los clientes solo pueden descargar documentos de sus propias reservas; administración y recepción pueden descargar facturas.

Los reembolsos pueden iniciarse desde el historial de pagos y se vinculan al pago original. El monto disponible se recalcula al registrar cada devolución y se notifica al huésped por correo.

El comando `python manage.py enviar_recordatorios_reservas` envía avisos dos días y un día antes de una reserva confirmada. El comando marca cada aviso enviado para evitar duplicados y registra en la salida cada correo enviado o fallido. Si cambia la fecha de entrada, las marcas de envío se reinician para que los avisos correspondan a la nueva fecha. El segundo correo informa la política de no reembolso del abono del 50% si el huésped no se presenta.

En Render, crea un servicio **Cron Job** diario para ejecutar el comando automáticamente. Usa el mismo repositorio y rama que el servicio web, con `Build Command: pip install -r requirements.txt`, `Command: python manage.py enviar_recordatorios_reservas` y `Schedule: 0 12 * * *` (12:00 UTC = 7:00 a. m. en Colombia). Comparte un Environment Group con el servicio web o copia al Cron Job, como mínimo, los mismos valores de `DATABASE_URL`, `SECRET_KEY` y `EMAIL_CREDENTIAL_ENCRYPTION_KEY`. Si el correo se configura por variables de entorno en vez de los datos SMTP del hotel, comparte también `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` y la configuración TLS/SSL. El Cron Job debe apuntar a la misma base de datos donde se guardan las reservas y la configuración SMTP cifrada. Revisa sus ejecuciones y logs en Render; el comando termina con error si falla algún correo para que la ejecución quede marcada como fallida.

La migración inicial es `caribeconfort/migrations/0025_resena.py`. Para crear o aplicar migraciones:

```powershell
python manage.py makemigrations caribeconfort
python manage.py migrate
```

## Idiomas

La aplicación tiene español (`es`) como idioma inicial y permite inglés (`en`). `LocaleMiddleware` debe ir después de `SessionMiddleware`. Los templates traducibles se marcan con `{% trans %}` o `{% blocktrans %}`; las traducciones se guardan bajo `locale/<idioma>/LC_MESSAGES/`.

Después de agregar o modificar cadenas:

```powershell
python manage.py makemessages -l en
python manage.py compilemessages
```

En Windows, `compilemessages` necesita las herramientas GNU gettext (`msgfmt`). El catálogo inglés de esta entrega ya está compilado en `locale/en/LC_MESSAGES/django.mo`.

Para comprobar la configuración sin iniciar el servidor:

```powershell
python manage.py check
```

## Pendientes conocidos

- Completar y revisar la traducción de todas las vistas de cliente, no solo navegación, portada, registro, inicio de sesión y reseñas.
- Completar pruebas de comportamiento y revisión responsive en las vistas de cliente.
- Definir e implementar el flujo de reembolsos.
- Rediseñar las vistas de administración.
- Aplicar y verificar migraciones y traducciones en el entorno local antes de desplegar.
