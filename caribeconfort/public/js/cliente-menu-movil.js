document.addEventListener('DOMContentLoaded', function () {
    var menu = document.getElementById('menuPrincipal');
    var toggle = document.querySelector('.menu-toggle[aria-controls="menuPrincipal"]');
    if (!menu || !toggle) return;

    var mobile = window.matchMedia('(max-width: 767px)');
    var isEnglish = (document.documentElement.lang || '').toLowerCase().startsWith('en');

    function setOpen(open) {
        menu.classList.toggle('show', open);
        toggle.classList.toggle('collapsed', !open);
        toggle.setAttribute('aria-expanded', String(open));
        toggle.setAttribute('aria-label', open
            ? (isEnglish ? 'Close menu' : 'Cerrar menú')
            : (isEnglish ? 'Open menu' : 'Abrir menú'));
    }

    toggle.addEventListener('click', function (event) {
        if (!mobile.matches) return;
        event.preventDefault();
        event.stopPropagation();
        setOpen(toggle.getAttribute('aria-expanded') !== 'true');
    });

    document.addEventListener('click', function (event) {
        if (mobile.matches && menu.classList.contains('show') &&
            !menu.contains(event.target) && !toggle.contains(event.target)) {
            setOpen(false);
        }
    });

    menu.querySelectorAll('a').forEach(function (link) {
        link.addEventListener('click', function () { setOpen(false); });
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && mobile.matches && menu.classList.contains('show')) {
            setOpen(false);
            toggle.focus();
        }
    });

    mobile.addEventListener('change', function (event) {
        if (!event.matches) setOpen(false);
    });
    setOpen(false);
});
