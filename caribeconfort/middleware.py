import time
from importlib import import_module
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.sessions.backends.base import UpdateError
from django.contrib.sessions.exceptions import SessionInterrupted
from django.contrib.sessions.middleware import SessionMiddleware
from django.middleware.csrf import get_token
from django.utils.cache import patch_vary_headers
from django.utils.html import escape
from django.utils.http import http_date


class MultiSessionMiddleware(SessionMiddleware):
    """Mantiene una cookie de sesión independiente para clientes y personal."""

    ADMIN_PATHS = (
        '/administrador', '/admin', '/adminreserva', '/rhabitaciones',
        '/adminhabitaciones', '/adminhuespedes', '/adminhuéspedes',
        '/adminpagos', '/adminservicios', '/adminusuarios',
        '/admintiposhabitacion', '/adminconfiguracion', '/admingaleria',
        '/adminconvenios', '/adminreportes', '/recepcion',
        '/adminreglas-descuento',
    )

    def __init__(self, get_response):
        super().__init__(get_response)
        self.SessionStore = import_module(settings.SESSION_ENGINE).SessionStore
        self.admin_cookie_name = f'{settings.SESSION_COOKIE_NAME}_admin'
        self.client_cookie_name = f'{settings.SESSION_COOKIE_NAME}_cliente'

    def _is_admin_path(self, path):
        return any(path == prefix or path.startswith(prefix + '/') for prefix in self.ADMIN_PATHS)

    def _cookie_name_for_request(self, request):
        path = request.path_info
        if self._is_admin_path(path):
            return self.admin_cookie_name

        is_invoice_path = (
            path.startswith('/reservas/')
            and path.endswith('/factura/')
            and path[len('/reservas/'): -len('/factura/')].isdigit()
        )
        # Estas rutas sirven tanto a clientes como a personal. Usa el contexto
        # de la página que inició el fetch para recuperar la sesión correcta.
        if (
            path.startswith('/api/cancelar-reserva/')
            or path.startswith('/api/validar-reserva/')
            or path.startswith('/gestionar-reserva/')
            or is_invoice_path
        ):
            if (
                request.headers.get('X-Session-Scope') == 'admin'
                or (is_invoice_path and request.GET.get('scope') == 'admin')
            ):
                return self.admin_cookie_name
            referer_path = urlsplit(request.META.get('HTTP_REFERER', '')).path
            if self._is_admin_path(referer_path):
                return self.admin_cookie_name
            return self.client_cookie_name

        if path.rstrip('/') == '/logout':
            scope = request.GET.get('scope') or request.POST.get('scope')
            if scope == 'admin':
                return self.admin_cookie_name
            if scope == 'cliente':
                return self.client_cookie_name

        referer_path = urlsplit(request.META.get('HTTP_REFERER', '')).path
        if path.rstrip('/') in {'/logout', '/i18n/setlang'} and self._is_admin_path(referer_path):
            return self.admin_cookie_name

        # El login es compartido por clientes y personal. Se identifica la cuenta
        # por su rol antes de cargar la sesión, evitando reemplazar la otra cookie.
        if path.rstrip('/') == '/login' and request.method == 'POST':
            correo = (request.POST.get('correo') or '').strip()
            if correo:
                from caribeconfort.models import Usuarios

                rol = Usuarios.objects.filter(
                    correo__iexact=correo,
                    estado=True,
                ).values_list('roles__nombre', flat=True).first()
                if rol in {'Administrador', 'Recepcionista'}:
                    return self.admin_cookie_name

        if path.rstrip('/') == '/login' and self._is_admin_path(referer_path):
            return self.admin_cookie_name
        return self.client_cookie_name

    def process_request(self, request):
        cookie_name = self._cookie_name_for_request(request)
        request._session_cookie_name = cookie_name
        session_key = request.COOKIES.get(cookie_name)
        request.session = self.SessionStore(session_key)
        request._session_migrated_from_legacy = False
        legacy_cookie_name = settings.SESSION_COOKIE_NAME
        legacy_session_key = request.COOKIES.get(legacy_cookie_name)
        if not session_key and legacy_session_key and cookie_name != legacy_cookie_name:
            legacy_session = self.SessionStore(legacy_session_key)
            legacy_role = legacy_session.get('rol')
            is_staff_session = legacy_role in {'Administrador', 'Recepcionista'}
            if (cookie_name == self.admin_cookie_name) == is_staff_session:
                request.session = legacy_session
                request._session_migrated_from_legacy = True

    def process_response(self, request, response):
        try:
            accessed = request.session.accessed
            modified = request.session.modified
            empty = request.session.is_empty()
            cookie_name = request._session_cookie_name
        except AttributeError:
            return response

        if cookie_name in request.COOKIES and empty:
            response.delete_cookie(
                cookie_name,
                path=settings.SESSION_COOKIE_PATH,
                domain=settings.SESSION_COOKIE_DOMAIN,
                samesite=settings.SESSION_COOKIE_SAMESITE,
            )
            need_vary_cookie = True
        else:
            need_vary_cookie = accessed
            if (modified or settings.SESSION_SAVE_EVERY_REQUEST or request._session_migrated_from_legacy) and not empty:
                if request.session.get_expire_at_browser_close():
                    max_age = None
                    expires = None
                else:
                    max_age = request.session.get_expiry_age()
                    expires = http_date(time.time() + max_age)
                if response.status_code < 500:
                    if modified or settings.SESSION_SAVE_EVERY_REQUEST:
                        try:
                            request.session.save()
                        except UpdateError as error:
                            raise SessionInterrupted(
                                'La sesión se eliminó antes de terminar la petición.'
                            ) from error
                    response.set_cookie(
                        cookie_name,
                        request.session.session_key,
                        max_age=max_age,
                        expires=expires,
                        domain=settings.SESSION_COOKIE_DOMAIN,
                        path=settings.SESSION_COOKIE_PATH,
                        secure=settings.SESSION_COOKIE_SECURE or None,
                        httponly=settings.SESSION_COOKIE_HTTPONLY or None,
                        samesite=settings.SESSION_COOKIE_SAMESITE,
                    )
                    need_vary_cookie = True
        if need_vary_cookie:
            patch_vary_headers(response, ('Cookie',))
        return response


class IdiomaGlobalMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        csrf_token = get_token(request)
        response = self.get_response(request)

        content_type = response.get('Content-Type', '')
        if 'text/html' not in content_type:
            return response

        body = getattr(response, 'content', None)
        if body is None:
            return response

        try:
            html = body.decode(getattr(response, 'charset', 'utf-8') or 'utf-8')
        except (UnicodeDecodeError, AttributeError):
            return response

        language = getattr(request, 'LANGUAGE_CODE', 'es')
        language = 'en' if str(language).startswith('en') else 'es'

        import re
        html = re.sub(
            r'<html([^>]*)>',
            lambda match: (
                re.sub(r'\slang="[^"]*"', '', match.group(0))
                .replace('<html', '<html lang="' + escape(language) + '"', 1)
            ),
            html,
            count=1,
            flags=re.I,
        )

        csrf_meta = '<meta name="csrf-token" content="' + escape(csrf_token) + '">'
        if 'name="csrf-token"' not in html.lower():
            head_end = html.lower().find('</head>')
            if head_end >= 0:
                html = html[:head_end] + csrf_meta + html[head_end:]

        script = '<script src="/static/js/idiomas-global.js?v=9" defer></script>'
        if '</body>' in html.lower():
            lower = html.lower()
            position = lower.rfind('</body>')
            html = html[:position] + script + html[position:]
        else:
            html += script

        charset = getattr(response, 'charset', 'utf-8') or 'utf-8'
        response.content = html.encode(charset)
        response['Content-Length'] = str(len(response.content))
        return response
