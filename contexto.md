# Contexto actual del proyecto Caribe Confort

Actualizado: 20 de noviembre de 2026

## Estado general

Se está uniformando el panel de administración y recepción con una apariencia más compacta y profesional, además de atender problemas de carga, paginación, contadores y correo SMTP. Los cambios actuales siguen sin commit. No se ha hecho una revisión visual reciente en navegador.

## Cambios realizados

- **Sesiones y configuración de Django:** la clave de desarrollo se conserva en `.dev-secret-key` (ignorada por Git); en producción se exige definir `SECRET_KEY`.
- **SMTP:** el sistema puede usar la configuración SMTP guardada para el hotel o las variables de entorno `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` y `DEFAULT_FROM_EMAIL`. La contraseña guardada desde el panel se cifra con `EMAIL_CREDENTIAL_ENCRYPTION_KEY`. El puerto 587 usa STARTTLS; el puerto 465 usa SSL implícito. No hay credenciales de un proveedor real configuradas, así que los correos reales requieren completar esa configuración.
- **Carga del dashboard:** la vista de administrador finaliza reservas vencidas sin enviar invitaciones de reseña durante la carga. Los errores de configuración SMTP al intentar enviar una invitación se registran como advertencias, no como tracebacks repetidos.
- **Contadores de reservas:** en administración los KPIs se calculan después de aplicar filtros, para que correspondan a los resultados mostrados. En recepción, `total_reservas` se basa en las filas incluidas en `reservas_hotel`.
- **Paneles administrativos y de recepción:** se añadió `admin-panel-shell.css` como estilo compartido en las plantillas administrativas y de recepción. `admin_nav.html` se mantiene intacto. Se incrementaron a `v=2` las referencias CSS pertinentes para evitar servir estilos cacheados.
- **Panel general:** `admin-panel-general.css` amplía el ancho disponible y reorganiza las tarjetas de soporte; se corrigieron selectores del tema oscuro y el tamaño de la tarjeta de estado del hotel.
- **Paginación:** `admin-pagination-scroll.js` guarda y restaura la posición de desplazamiento en dashboard, huéspedes, reservas y usuarios.
- **Modal de reservas administrativas:** los botones de cierre previenen el envío accidental del formulario antes de cerrar el modal.
- **SMTP en la configuración:** la plantilla explica STARTTLS en 587 y SSL automático en 465.

## Pendiente / comprobar

1. Configurar el SMTP real del hotel y conservar una `EMAIL_CREDENTIAL_ENCRYPTION_KEY` estable; luego probar el envío desde la aplicación. No compartir contraseñas ni claves en el chat ni subirlas al repositorio.
2. Revisar visualmente el panel general y las vistas administrativas/de recepción en tamaños de escritorio y móvil. La última validación fue de código, no visual.
3. En `public/css/dashboard.css`, `.card-ocupacion` tiene `width: 600px` y `min-width: 450px`; comprobar que no provoque desbordamiento en pantallas estrechas.
4. Verificar manualmente los botones de cancelar y check-in en recepción; la corrección registrada en `reservas_admin.js` es para el modal de reservas administrativas.
5. Si vuelve a fallar la paginación, confirmar que la página destino carga y restaura la posición con los filtros y parámetros de URL utilizados.

## Validación registrada

- `python manage.py test`: 23 pruebas aprobadas.
- `python manage.py check`: sin errores.
- `node --check` de `admin-pagination-scroll.js`, comprobación de balance de llaves CSS y `git diff --check`: aprobados.
- No se inició el servidor ni se usó Playwright para la última validación.

## Archivos de referencia

- `caribeconfort/settings.py`: clave de desarrollo y opciones SMTP de entorno.
- `caribeconfort/views.py`: conexión SMTP, envío de reseñas, contadores y dashboard.
- `caribeconfort/tests.py`: pruebas de SMTP, contadores y reservas vencidas.
- `caribeconfort/public/css/admin-panel-general.css`: estilo y distribución del panel general.
- `caribeconfort/public/css/admin-panel-shell.css`: estilos compartidos de administración y recepción.
- `caribeconfort/public/css/dashboard.css`: estilos del dashboard, incluida la tarjeta de ocupación.
- `caribeconfort/public/js/admin-pagination-scroll.js`: restauración de posición al paginar.
- `caribeconfort/public/js/administrador/reservas_admin.js`: controles de cierre del modal de reservas administrativas.
- `caribeconfort/templates/admini/configuracion.html`: formulario y guía SMTP.
