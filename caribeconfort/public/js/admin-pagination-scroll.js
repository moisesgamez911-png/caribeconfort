(function () {
    var storageKey = 'cc-admin-pagination-scroll';

    function currentUrl() {
        return window.location.pathname + window.location.search;
    }

    function restoreScroll() {
        var stored = sessionStorage.getItem(storageKey);
        if (!stored) return;

        var position = JSON.parse(stored);
        if (position.url !== currentUrl()) {
            sessionStorage.removeItem(storageKey);
            return;
        }

        sessionStorage.removeItem(storageKey);
        window.history.scrollRestoration = 'manual';
        window.requestAnimationFrame(function () {
            window.scrollTo(0, position.scrollY);
        });
    }

    document.addEventListener('click', function (event) {
        if (
            event.defaultPrevented ||
            event.button !== 0 ||
            event.metaKey ||
            event.ctrlKey ||
            event.shiftKey ||
            event.altKey
        ) return;

        var link = event.target.closest('.adm-pagination a, .rv-pagination a');
        if (!link || link.target) return;

        var destination = new URL(link.href, window.location.href);
        if (destination.origin !== window.location.origin) return;

        sessionStorage.setItem(storageKey, JSON.stringify({
            url: destination.pathname + destination.search,
            scrollY: window.scrollY
        }));
        window.history.scrollRestoration = 'manual';
    });

    window.addEventListener('pageshow', restoreScroll);
})();
