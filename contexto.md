# Contexto actual del proyecto Caribe Confort

Actualizado: 20 de noviembre de 2026

## Estado general

Se está uniformando el panel de administración y recepción con una apariencia más compacta y profesional, además de atender problemas de carga, paginación, contadores, notificaciones y correo SMTP. Los cambios actuales siguen sin commit. No se ha hecho una revisión visual reciente en navegador.

## Cambios realizados

- **Sesiones y configuración de Django:** la clave de desarrollo se conserva en `.dev-secret-key` (ignorada por Git); en producción se exige definir `SECRET_KEY`.
- **SMTP:** el sistema puede usar la configuración SMTP guardada para el hotel o las variables de entorno `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` y `DEFAULT_FROM_EMAIL`. La contraseña guardada desde el panel se cifra con `EMAIL_CREDENTIAL_ENCRYPTION_KEY`. El puerto 587 usa STARTTLS; el puerto 465 usa SSL implícito. No hay credenciales de un proveedor real configuradas, así que los correos reales requieren completar esa configuración.
- **Carga del dashboard:** la vista de administrador finaliza reservas vencidas sin enviar invitaciones de reseña durante la carga. Los errores de configuración SMTP al intentar enviar una invitación se registran como advertencias, no como tracebacks repetidos.
- **Contadores de reservas:** en administración los KPIs se calculan después de aplicar filtros, para que correspondan a los resultados mostrados. En recepción, `total_reservas` se basa en las filas incluidas en `reservas_hotel`.
- **Paneles administrativos y de recepción:** se añadió `admin-panel-shell.css` como estilo compartido en las plantillas administrativas y de recepción. La navegación lateral conserva su estructura y estilos, con la etiqueta de su entrada de tipos cambiada a “Tipos”. Se incrementaron a `v=2` las referencias CSS pertinentes para evitar servir estilos cacheados.
- **Panel general:** `admin-panel-general.css` amplía el ancho disponible y reorganiza las tarjetas de soporte; se corrigieron selectores del tema oscuro y el tamaño de la tarjeta de estado del hotel.
- **Paginación:** `admin-pagination-scroll.js` guarda y restaura la posición de desplazamiento en dashboard, huéspedes, reservas y usuarios.
- **Modal de reservas administrativas:** los botones de cierre previenen el envío accidental del formulario antes de cerrar el modal.
- **SMTP en la configuración:** la plantilla explica STARTTLS en 587 y SSL automático en 465.
- **Notificaciones del encabezado:** el procesador de contexto entrega conteos totales y hasta cinco reservas por validar y cinco servicios pendientes. La campana muestra el total y abre un menú con enlaces por categoría; se cierra al hacer clic fuera o pulsar Escape.
- **Catálogo “Tipos”:** se reemplazó el rótulo “Tipos de habitación” en el menú por “Tipos” y se agregaron pestañas para habitaciones y planes. La pestaña de planes administra los registros reservables del modelo existente `Planes` (sin crear un modelo duplicado), incluidos precio, disponibilidad, duración, capacidad, servicios y características.
- **Eliminación de planes:** se permite borrar planes sin reservas asociadas. Si una reserva los referencia, se bloquea el borrado y se indica que se desactive el plan.
- **Traducciones:** se agregaron al catálogo inglés las etiquetas nuevas del encabezado y de los tipos. El archivo `.po` está versionado; el `.mo` local se recompiló para probar las traducciones.
- **Caché del encabezado:** las plantillas administrativas y de recepción usan `barra-encabezado.css?v=106` (convenios `v=1001`) para solicitar los estilos del menú.
- **Aviso de reservas por validar:** se compactó la tarjeta, se reorganizó en columnas responsivas y se añadieron variables de tema claro/oscuro para el contenedor, sus textos, tarjetas y botón. La plantilla muestra también el total pendiente y distingue reservas de habitación y de plan.
- **Worktree compartido:** también hay cambios en middleware, modelos y vistas/scripts de servicios, además de la migración `0031_servicioreserva_payment_reference.py`; no se revisaron ni modificaron en esta tarea.

## Pendiente / comprobar

1. Configurar el SMTP real del hotel y conservar una `EMAIL_CREDENTIAL_ENCRYPTION_KEY` estable; luego probar el envío desde la aplicación. No compartir contraseñas ni claves en el chat ni subirlas al repositorio.
2. Revisar visualmente el aviso de reservas pendientes en ambos temas, el menú de notificaciones, las pestañas CRUD y las vistas administrativas/de recepción en escritorio y móvil. La última validación fue sin navegador ni servidor.
3. En `public/css/dashboard.css`, `.card-ocupacion` tiene `width: 600px` y `min-width: 450px`; comprobar que no provoque desbordamiento en pantallas estrechas.
4. Verificar manualmente los botones de cancelar y check-in en recepción; la corrección registrada en `reservas_admin.js` es para el modal de reservas administrativas.
5. Si vuelve a fallar la paginación, confirmar que la página destino carga y restaura la posición con los filtros y parámetros de URL utilizados.

## Validación registrada

- Las cinco pruebas nuevas de notificaciones y tipos de plan pasan.
- La última ejecución completa de `python manage.py test` encontró 28 pruebas: 25 pasaron y tres fallaron en pruebas existentes de reseñas y solicitud de servicios (mocks de huésped sin `usuarios_id` y respuesta 400 en validación); no se investigaron porque no corresponden a este cambio.
- `python manage.py check`: sin errores.
- La plantilla `admini/reservas.html` compila; `git diff --check` y el balance de llaves del CSS de reservas pasan.
- `node --check` de `admin-notificaciones.js`, balance de llaves CSS, `git diff --check` y traducciones inglesas cargadas en Django: aprobados.
- `compilemessages` no se pudo ejecutar porque falta `msgfmt`; el `.mo` se compiló con el `polib` ya disponible. No se inició el servidor ni se usó Playwright.

## Archivos de referencia

- `caribeconfort/settings.py`: clave de desarrollo y opciones SMTP de entorno.
- `caribeconfort/context_processors.py`: identidad del hotel y notificaciones compartidas.
- `caribeconfort/views.py`: conexión SMTP, envío de reseñas, contadores y dashboard.
- `caribeconfort/tests.py`: pruebas de SMTP, contadores y reservas vencidas.
- `caribeconfort/public/js/admin-notificaciones.js`: interacción del menú de campana.
- `caribeconfort/public/css/barra-encabezado.css`: estilos del menú de notificaciones.
- `caribeconfort/templates/inc/admin_header.html`: campana y categorías de avisos.
- `caribeconfort/templates/inc/admin_nav.html`: entrada “Tipos”.
- `caribeconfort/templates/admini/tipos_habitacion.html`: pestañas y CRUD de tipos.
- `caribeconfort/templates/admini/plan_tipo_campos.html`: formulario reutilizable de planes.
- `locale/en/LC_MESSAGES/django.po`: nuevas traducciones inglesas.
- `caribeconfort/public/css/admin-panel-general.css`: estilo y distribución del panel general.
- `caribeconfort/public/css/admin-panel-shell.css`: estilos compartidos de administración y recepción.
- `caribeconfort/public/css/administrador/reservas.css`: diseño responsivo y colores temáticos del aviso de reservas por validar.
- `caribeconfort/templates/admini/reservas.html`: contenido del aviso y referencia al CSS actualizado.
- `caribeconfort/public/css/dashboard.css`: estilos del dashboard, incluida la tarjeta de ocupación.
- `caribeconfort/public/js/admin-pagination-scroll.js`: restauración de posición al paginar.
- `caribeconfort/public/js/administrador/reservas_admin.js`: controles de cierre del modal de reservas administrativas.
- `caribeconfort/templates/admini/configuracion.html`: formulario y guía SMTP.
