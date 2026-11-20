(function () {
    const LANG_COOKIE = 'django_language';
    const POST_SCROLL_KEY = 'caribeconfort:post-scroll';
    const getLanguage = () => {
        const match = document.cookie.match(new RegExp('(?:^|; )' + LANG_COOKIE + '=([^;]*)'));
        return match ? decodeURIComponent(match[1]).split('-')[0] : 'es';
    };

    const restorePostScroll = () => {
        const saved = sessionStorage.getItem(POST_SCROLL_KEY);
        if (!saved) return;

        sessionStorage.removeItem(POST_SCROLL_KEY);
        const position = JSON.parse(saved);
        if (
            !position ||
            (
                position.path !== window.location.pathname &&
                position.sourcePath !== window.location.pathname
            ) ||
            Date.now() - position.savedAt > 60000 ||
            !Number.isFinite(position.y) ||
            position.y < 0
        ) return;

        window.requestAnimationFrame(() => window.scrollTo(0, position.y));
    };

    document.addEventListener('submit', (event) => {
        const form = event.target;
        if (
            event.defaultPrevented ||
            !form ||
            form.tagName !== 'FORM' ||
            !['get', 'post'].includes(form.method.toLowerCase())
        ) return;

        const destination = new URL(form.action, window.location.href);
        sessionStorage.setItem(POST_SCROLL_KEY, JSON.stringify({
            path: destination.pathname,
            sourcePath: window.location.pathname,
            y: window.scrollY,
            savedAt: Date.now()
        }));
    });

    const translations = {
        'Inicio': 'Home',
        'Habitaciones/Reservar': 'Rooms / Booking',
        'Habitaciones / Reservar': 'Rooms / Booking',
        'Galería': 'Gallery',
        'Servicios': 'Services',
        'Planes': 'Packages',
        'Mi Perfil': 'My Profile',
        'Mis Reservas': 'My Bookings',
        'Cerrar sesión': 'Log out',
        'Iniciar sesión': 'Log in',
        'Mi cuenta': 'My account',
        'Abrir menú': 'Open menu',
        'Abrir menú de usuario': 'Open user menu',
        'Todas': 'All',
        'Reservar': 'Book',
        'Fecha de entrada': 'Check-in date',
        'Fecha de salida': 'Check-out date',
        'Huéspedes': 'Guests',
        'adulto': 'adult',
        'niños': 'children',
        'Código promocional': 'Promo code',
        'Opcional': 'Optional',
        'Tipo de habitación': 'Room type',
        'Elegir ocupación': 'Choose occupancy',
        'Aplicar': 'Apply',
        'Ocupación': 'Occupancy',
        'Adultos': 'Adults',
        'Niños': 'Children',
        'Cerrar': 'Close',
        'Anterior': 'Previous',
        'Siguiente': 'Next',
        'Ubicación y contacto': 'Location and contact',
        'Horarios': 'Hours',
        'Check-in': 'Check-in',
        'Check-out': 'Check-out',
        'Recepción': 'Reception',
        'Desayuno': 'Breakfast',
        'Explorar': 'Explore',
        'Todos los derechos reservados': 'All rights reserved',
        'Nuestra esencia': 'Our essence',
        'Nuestra galería': 'Our gallery',
        'Colección visual': 'Visual collection',
        'Espacios pensados para el descanso': 'Spaces designed for relaxation',
        'Ver en pantalla completa': 'View fullscreen',
        'Aún no hay categorías': 'There are no categories yet',
        'Aún no hay categorías.': 'There are no categories yet.',
        'Aún no hay imágenes': 'There are no images yet',
        'Ver foto': 'View photo',
        'Servicios destacados del hotel': 'Featured hotel services',
        'Servicios & Experiencias': 'Services & Experiences',
        'Experiencias en Caribe Confort': 'Experiences at Caribe Confort',
        'Nuestros planes': 'Our packages',
        'Elige tu experiencia': 'Choose your experience',
        'Desde': 'From',
        'Reservar plan': 'Book package',
        'No disponible': 'Unavailable',
        'Agotado': 'Sold out',
        'Aún no hay planes disponibles': 'There are no packages available yet',
        'Pronto verás aquí todas las experiencias que tenemos para ti.': 'Soon you will find all our experiences here.',
        'Tu descanso, nuestra prioridad': 'Your rest, our priority',
        'Tu próxima experiencia': 'Your next experience',
        'comienza aquí': 'starts here',
        'Nombre del titular': 'Guest name',
        'Fecha de entrada': 'Check-in date',
        'Fecha de salida': 'Check-out date',
        'Cantidad': 'Quantity',
        'Total': 'Total',
        'Confirmar': 'Confirm',
        'Volver': 'Back',
        'Volver al inicio': 'Back to home',
        'Mi Perfil': 'My Profile',
        'Mis Reservas': 'My Bookings',
        'PRÓXIMA RESERVA': 'UPCOMING BOOKING',
        'Próxima reserva': 'Upcoming booking',
        'TU ESTADÍA': 'YOUR STAY',
        'Mis reservas': 'My bookings',
        'Consulta tus estancias, planes y los detalles de cada reserva.': 'View your stays, packages, and booking details.',
        'Mi reserva': 'My booking',
        'Detalle de reserva': 'Booking details',
        'Número de reserva': 'Booking number',
        'Estado': 'Status',
        'Pendiente': 'Pending',
        'Confirmada': 'Confirmed',
        'Cancelada': 'Cancelled',
        'Pagada': 'Paid',
        'Cancelar reserva': 'Cancel booking',
        'Ver detalles': 'View details',
        'Bienvenido de nuevo': 'Welcome back',
        'a tu descanso': 'to your retreat',
        'BIENVENIDO DE NUEVO': 'WELCOME BACK',
        'Correo electrónico': 'Email address',
        'Contraseña': 'Password',
        'Mostrar contraseña': 'Show password',
        '¿Olvidó su contraseña?': 'Forgot your password?',
        '¿No está registrado?': 'Not registered yet?',
        'Regístrese': 'Sign up',
        'Crear cuenta': 'Create account',
        'Nombre': 'First name',
        'Apellido': 'Last name',
        'Teléfono': 'Phone',
        'Tipo de documento': 'Document type',
        'Nacionalidad': 'Nationality',
        'Confirmar contraseña': 'Confirm password',
        'Registrarse': 'Sign up',
        '¿Ya está registrado?': 'Already registered?',
        'Inicie sesión': 'Log in',
        'Configuración': 'Settings',
        'Configuración del hotel': 'Hotel settings',
        'Datos generales': 'General information',
        'DATOS GENERALES': 'GENERAL INFORMATION',
        'Actualizar': 'Update',
        'Guardar': 'Save',
        'Guardar configuración': 'Save settings',
        'Información del hotel': 'Hotel information',
        'Nombre del hotel': 'Hotel name',
        'Ciudad / municipio': 'City / municipality',
        'Dirección': 'Address',
        'Correo electrónico': 'Email',
        'Descripción': 'Description',
        'Ruta o referencia de fotografías': 'Photo path or reference',
        'Logo del hotel': 'Hotel logo',
        'Cancelar': 'Cancel',
        'Servidor de correo (SMTP)': 'Email server (SMTP)',
        'Apariencia del sistema': 'System appearance',
        'Tema': 'Theme',
        'Claro': 'Light',
        'Oscuro': 'Dark',
        'Panel': 'Dashboard',
        'Reservas': 'Bookings',
        'Habitaciones': 'Rooms',
        'Tipos de habitación': 'Room types',
        'Pagos': 'Payments',
        'Huéspedes': 'Guests',
        'Reportes': 'Reports',
        'Convenios': 'Agreements',
        'Descuentos por estancia': 'Stay discounts',
        'Usuarios': 'Users',
        'Menú': 'Menu',
        'Mostrar menos opciones': 'Show fewer options',
        'Ver sitio del hotel': 'View hotel website',
        'Activar modo oscuro': 'Enable dark mode',
        'Acciones rápidas': 'Quick actions',
        'OPERACIÓN': 'OPERATIONS',
        'OPERACIÓN DEL HOTEL': 'HOTEL OPERATIONS',
        'Llegadas de hoy': 'Today arrivals',
        'Salidas de hoy': 'Today departures',
        'Registrar huésped': 'Register guest',
        'Crear reserva': 'Create booking',
        'Pago / servicio': 'Payment / service',
        'Cuenta': 'Account',
        'Panel de recepción': 'Reception dashboard',
        'Servicios pendientes': 'Pending services',
        'Cantidad': 'Quantity',
        'Valor': 'Amount',
        'Registrar pago': 'Register payment',
        'Buscar': 'Search',
        'Filtrar': 'Filter',
        'Editar': 'Edit',
        'Eliminar': 'Delete',
        'Guardar cambios': 'Save changes',
        'Nuevo': 'New',
        'Precio': 'Price',
        'Disponible': 'Available',
        'Ocupada': 'Occupied',
        'Bloqueada': 'Blocked',
        'Fuera de servicio': 'Out of service',
        'Activo': 'Active',
        'Inactivo': 'Inactive',
        'Sí': 'Yes',
        'No': 'No',
        'Email': 'Email',
        'Usuario': 'User',
        'Fecha': 'Date',
        'Acciones': 'Actions',
        'Seleccionar': 'Select'
        ,
        'Llegada': 'Check-in',
        'Salida': 'Check-out',
        'Convenio': 'Agreement',
        'Código': 'Code',
        'aplicado': 'applied',
        'de descuento': 'discount',
        'adultos': 'adults',
        'niño': 'child',
        'niñas': 'girls',
        'Descanso frente al Caribe': 'Relaxation facing the Caribbean',
        'Nuestras habitaciones': 'Our rooms',
        'Comodidad, naturaleza y el mejor servicio': 'Comfort, nature, and the best service',
        'Caribe Confort · Riohacha': 'Caribe Confort · Riohacha',
        'Habitación': 'Room',
        'Últimas': 'Last',
        'disponibles': 'available',
        'por noche': 'per night',
        'Añadir': 'Add',
        'Ver foto de la habitación': 'View room photo',
        'Detalle de la habitación': 'Room detail',
        'Ver todas las fotos': 'View all photos',
        'Información de la habitación': 'Room information',
        'Reseñas': 'Reviews',
        'reseñas de huéspedes': 'guest reviews',
        'Wi-Fi gratis': 'Free Wi-Fi',
        'Agregar desayuno': 'Add breakfast',
        'Aún no hay reseñas para esta habitación.': 'There are no reviews for this room yet.',
        'No hay habitaciones disponibles.': 'There are no rooms available.',
        'Cerrar galería': 'Close gallery',
        'Foto anterior': 'Previous photo',
        'Foto siguiente': 'Next photo',
        'Confirmar reserva': 'Confirm booking',
        'Revisa la información antes de confirmar.': 'Review the information before confirming.',
        'Entrada': 'Check-in',
        'Noches': 'Nights',
        'Habitaciones': 'Rooms',
        'Descuento convenio': 'Agreement discount',
        'Total a pagar': 'Total to pay',
        'Falta información': 'Missing information',
        'Debes completar las fechas y seleccionar al menos una habitación.': 'Complete the dates and select at least one room.',
        'Entendido': 'Got it',
        'Aviso': 'Notice',
        'Progreso': 'Progress',
        'Residencia': 'Residence',
        'Identificación': 'Identification',
        'Documentos': 'Documents',
        'Información adicional': 'Additional information',
        'Datos personales': 'Personal details',
        'Datos de pago': 'Payment details',
        'Método de pago': 'Payment method',
        'Resumen': 'Summary',
        'Continuar': 'Continue',
        'Siguiente': 'Next',
        'Atrás': 'Back',
        'Procesando': 'Processing',
        'Error': 'Error',
        'Éxito': 'Success',
        'Completado': 'Completed',
        'Cargando': 'Loading',
        'Selecciona': 'Select',
        'Seleccione': 'Select',
        'Requerido': 'Required',
        'Opcional': 'Optional',
        'Disponible': 'Available',
        'No disponible': 'Unavailable',
        'Sin datos': 'No data',
        'Resultados': 'Results',
        'Sin resultados': 'No results',
        'Página': 'Page',
        'Anterior': 'Previous',
        'Siguiente': 'Next',
        'Número': 'Number',
        'Nombres': 'Names',
        'Apellidos': 'Last names',
        'Correo': 'Email',
        'Dirección': 'Address',
        'Municipio': 'Municipality',
        'País': 'Country',
        'Nacimiento': 'Birth date',
        'Edad': 'Age',
        'Género': 'Gender',
        'Observaciones': 'Notes',
        'Acción': 'Action',
        'Servicios adicionales': 'Additional services',
        'Solicitar': 'Request',
        'Solicitar servicio': 'Request service',
        'Solicitar experiencia': 'Request experience',
        'Selecciona una reserva activa': 'Select an active booking',
        '¿A qué reserva deseas adjuntarlo?': 'Which booking do you want to add it to?',
        'Nombre de quien solicita': 'Name of requester',
        'Consumo': 'Consumption',
        'Notas': 'Notes',
        'Enviar solicitud': 'Send request',
        'Recuperar contraseña': 'Reset password',
        'Cambiar contraseña': 'Change password',
        'Nueva contraseña': 'New password',
        'Contraseña actual': 'Current password',
        'Confirmar nueva contraseña': 'Confirm new password',
        'Enviar': 'Send',
        'Cerrar sesión': 'Log out',
        'Ayuda': 'Help',
        'Contacto': 'Contact',
        'Inicio': 'Home',
        'Tu experiencia en el Caribe': 'Your Caribbean experience',
        'TU EXPERIENCIA EN EL CARIBE': 'YOUR CARIBBEAN EXPERIENCE',
        'TU ESTADÍA': 'YOUR STAY',
        'Consulta tus estancias, planes y los detalles de cada reserva.': 'View your stays, packages, and the details of each booking.',
        'Historial': 'History',
        'Reservas anteriores': 'Previous bookings',
        'Reserva': 'Booking',
        'Check-in': 'Check-in',
        'Check-out': 'Check-out',
        'Noches': 'Nights',
        'Huésped': 'Guest',
        'Pago': 'Payment',
        'Pendiente de pago': 'Payment pending',
        'Pagada - Por validar': 'Paid - Pending verification',
        'En curso': 'In progress',
        'Finalizada': 'Completed',
        'Volver al perfil': 'Back to profile',
        'Editar perfil': 'Edit profile',
        'Actualizar datos': 'Update details',
        'Datos guardados': 'Data saved',
        'Datos guardados correctamente': 'Data saved successfully',
        'Información del usuario': 'User information',
        'Cambiar foto': 'Change photo',
        'Configuración de cuenta': 'Account settings',
        'Eliminar cuenta': 'Delete account',
        'Seguridad': 'Security'
        ,
        'Añadida': 'Added',
        'Habitación anterior': 'Previous room',
        'Siguiente habitación': 'Next room',
        'Habitaciones y reservas': 'Rooms and bookings',
        'Llegada': 'Check-in',
        'Salida': 'Check-out',
        'Convenio': 'Agreement',
        'Código': 'Code',
        'aplicado': 'applied',
        'de descuento': 'discount',
        'Descanso frente al Caribe': 'Relaxation facing the Caribbean',
        'Nuestras habitaciones': 'Our rooms',
        'Comodidad, naturaleza y el mejor servicio': 'Comfort, nature, and the best service',
        'Últimas': 'Last',
        'disponibles': 'available',
        'por noche': 'per night',
        'Añadir': 'Add',
        'Descripción': 'Description',
        'Agregar desayuno': 'Add breakfast',
        'Aún no hay reseñas para esta habitación.': 'There are no reviews for this room yet.',
        'No hay habitaciones disponibles.': 'There are no rooms available.',
        'Confirmar reserva': 'Confirm booking',
        'Revisa la información antes de confirmar.': 'Review the information before confirming.',
        'Entrada': 'Check-in',
        'Salida': 'Check-out',
        'Noches': 'Nights',
        'Descuento convenio': 'Agreement discount',
        'Total a pagar': 'Total to pay',
        'Falta información': 'Missing information',
        'Debes completar las fechas y seleccionar al menos una habitación.': 'Complete the dates and select at least one room.',
        'Entendido': 'Got it',
        'Aviso': 'Notice',
        'El código no existe, venció o ya fue utilizado.': 'The code does not exist, has expired, or has already been used.',
        'Código de verificación': 'Verification code',
        'Verificar código': 'Verify code',
        'Nueva contraseña': 'New password',
        'Actualizar contraseña': 'Update password',
        'Restablecer contraseña': 'Reset password',
        'Revisa tu correo electrónico e ingresa el código de verificación.': 'Check your email and enter the verification code.',
        'RECUPERAR ACCESO': 'RECOVER ACCESS',
        '¿Olvidaste tu contraseña?': 'Forgot your password?',
        'Ingresa tu correo electrónico y te enviaremos un código de verificación para restablecer tu cuenta.': 'Enter your email address and we will send you a verification code to reset your account.',
        'Enviar código': 'Send code',
        'Volver al inicio de sesión': 'Back to login',
        'Cancelar y volver al login': 'Cancel and return to login',
        'SEGURIDAD': 'SECURITY',
        'Bienvenido de nuevo': 'Welcome back',
        'a tu descanso': 'to your retreat'
    };

    const translateText = (text) => {
        if (!text || text.trim() === '') return text;
        let translated = text;
        const keys = Object.keys(translations).sort((a, b) => b.length - a.length);
        keys.forEach((source) => {
            if (translated.includes(source)) {
                translated = translated.split(source).join(translations[source]);
            }
        });
        return translated;
    };

    const applyTranslations = () => {
        if (getLanguage() !== 'en') {
            document.documentElement.lang = 'es';
            return;
        }
        document.documentElement.lang = 'en';

        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        const nodes = [];
        let node;
        while ((node = walker.nextNode())) {
            if (node.parentElement && ['SCRIPT', 'STYLE', 'TEXTAREA'].includes(node.parentElement.tagName)) continue;
            nodes.push(node);
        }
        nodes.forEach((textNode) => {
            textNode.nodeValue = translateText(textNode.nodeValue);
        });

        document.querySelectorAll('[placeholder],[title],[aria-label],[data-tip]').forEach((element) => {
            ['placeholder', 'title', 'aria-label', 'data-tip'].forEach((attribute) => {
                if (element.hasAttribute(attribute)) {
                    element.setAttribute(attribute, translateText(element.getAttribute(attribute)));
                }
            });
        });
    };

    const createGlobalSwitcher = () => {
        if (document.querySelector('.language-switcher')) return;
        const form = document.createElement('form');
        form.className = 'language-switcher global-language-switcher';
        form.method = 'post';
        form.action = '/i18n/setlang/';
        form.innerHTML =
            '<input type="hidden" name="next" value="' + window.location.pathname + window.location.search + '">' +
            '<button class="language-switcher-button' + (getLanguage() === 'es' ? ' is-active' : '') + '" type="submit" name="language" value="es">ES</button>' +
            '<span class="language-switcher-separator" aria-hidden="true">|</span>' +
            '<button class="language-switcher-button' + (getLanguage() === 'en' ? ' is-active' : '') + '" type="submit" name="language" value="en">EN</button>';
        const csrf = document.querySelector('[name=csrfmiddlewaretoken]');
        if (csrf) form.querySelector('input[name=next]').insertAdjacentHTML('beforebegin',
            '<input type="hidden" name="csrfmiddlewaretoken" value="' + csrf.value + '">');
        document.body.appendChild(form);
    };

    const start = () => {
        applyTranslations();
        createGlobalSwitcher();
        restorePostScroll();
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start);
    } else {
        start();
    }

    const observer = new MutationObserver(() => {
        if (getLanguage() === 'en') applyTranslations();
    });
    observer.observe(document.documentElement, { childList: true, subtree: true, characterData: true });
})();
