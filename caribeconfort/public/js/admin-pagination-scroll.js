(function () {
    var storageKey = 'cc-admin-pagination-scroll';

    function currentUrl() {
        return window.location.pathname + window.location.search;
    }

    function guardarPosicion(url) {
        try {
            sessionStorage.setItem(storageKey, JSON.stringify({
                url: url || currentUrl(),
                scrollY: window.scrollY
            }));
        } catch (error) {
            // La restauración es una mejora opcional si el navegador bloquea sessionStorage.
        }
    }

    function restoreScroll() {
        var stored;
        try {
            stored = sessionStorage.getItem(storageKey);
        } catch (error) {
            return;
        }
        if (!stored) return;

        var position;
        try {
            position = JSON.parse(stored);
        } catch (error) {
            sessionStorage.removeItem(storageKey);
            return;
        }

        // Los filtros cambian el query string, pero siguen en la misma pantalla.
        if (!position.url || new URL(position.url, window.location.origin).pathname !== window.location.pathname) {
            sessionStorage.removeItem(storageKey);
            return;
        }

        sessionStorage.removeItem(storageKey);
        window.history.scrollRestoration = 'manual';
        window.requestAnimationFrame(function () {
            window.scrollTo(0, position.scrollY);
        });
    }

    window.addEventListener('pagehide', function () {
        guardarPosicion();
    });

    window.addEventListener('pageshow', restoreScroll);
})();
