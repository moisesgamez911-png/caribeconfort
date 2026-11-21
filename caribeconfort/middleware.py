from django.middleware.csrf import get_token
from django.utils.html import escape


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

        script = '<script src="/static/js/idiomas-global.js?v=8" defer></script>'
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
