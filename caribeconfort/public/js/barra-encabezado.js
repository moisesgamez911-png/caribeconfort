document.addEventListener("DOMContentLoaded", function () {

    const themeKey = "cc_admin_theme";
    const themeToggle = document.getElementById("adThemeToggle");
    const themePreference = document.getElementById("adThemePreference");
    let theme = "light";
    try {
        theme = localStorage.getItem(themeKey) === "dark" ? "dark" : "light";
    } catch (e) {}

    function aplicarTema(nuevoTema, guardar) {
        theme = nuevoTema === "dark" ? "dark" : "light";
        document.documentElement.setAttribute("data-theme", theme);
        if (themePreference) themePreference.value = theme;
        if (themeToggle) {
            const modoDestino = theme === "dark" ? "claro" : "oscuro";
            themeToggle.setAttribute("aria-label", "Activar modo " + modoDestino);
            themeToggle.title = "Activar modo " + modoDestino;
        }
        if (guardar) {
            try {
                localStorage.setItem(themeKey, theme);
            } catch (e) {}
        }
    }

    aplicarTema(theme, false);
    if (themeToggle) {
        themeToggle.addEventListener("click", function () {
            aplicarTema(theme === "dark" ? "light" : "dark", true);
        });
    }
    if (themePreference) {
        themePreference.addEventListener("change", function () {
            aplicarTema(themePreference.value, true);
        });
    }
    
    const adToggle = document.getElementById("adToggle");
    const adRail = document.getElementById("adRail");
    const adCompactToggle = document.getElementById("adCompactToggle");
    
    if (adToggle && adRail) {
        try {
            if (localStorage.getItem("cc_admin_menu_v2") === "1") {
                adRail.classList.add("abierto");
            }
        } catch (e) {}
        document.body.classList.toggle("menu-abierto", adRail.classList.contains("abierto"));
        adToggle.setAttribute("aria-expanded", adRail.classList.contains("abierto") ? "true" : "false");

        adToggle.addEventListener("click", function(e) {
            e.preventDefault();
            const abierto = adRail.classList.toggle("abierto");
            document.body.classList.toggle("menu-abierto", abierto);
            adToggle.setAttribute("aria-expanded", abierto ? "true" : "false");
            try { localStorage.setItem("cc_admin_menu_v2", abierto ? "1" : "0"); } catch (e) {}
        });
        const enlacesMenu = adRail.querySelectorAll("a.ad-item");
        enlacesMenu.forEach(enlace => {
            enlace.addEventListener("click", function() {
                try { localStorage.setItem("cc_admin_menu_v2", "0"); } catch (e) {}
            });
        });
    }

    if (adRail && adCompactToggle) {
        function aplicarMenuCompacto(compacto, guardar) {
            adRail.classList.toggle("compacto", compacto);
            const texto = compacto ? "Mostrar todas las opciones" : "Mostrar menos opciones";
            adCompactToggle.setAttribute("aria-expanded", compacto ? "false" : "true");
            adCompactToggle.setAttribute("aria-label", texto);
            adCompactToggle.setAttribute("data-tip", texto);
            const etiqueta = adCompactToggle.querySelector(".ad-txt");
            if (etiqueta) etiqueta.textContent = texto;
            if (guardar) {
                try {
                    localStorage.setItem("cc_admin_menu_compacto", compacto ? "1" : "0");
                } catch (e) {}
            }
        }

        let compacto = false;
        try {
            compacto = localStorage.getItem("cc_admin_menu_compacto") === "1";
        } catch (e) {}
        aplicarMenuCompacto(compacto, false);
        adCompactToggle.addEventListener("click", function () {
            aplicarMenuCompacto(!adRail.classList.contains("compacto"), true);
        });
    }

    const adUsuarioBtn = document.getElementById("adUsuarioBtn");
    const adUsuarioMenu = document.getElementById("adUsuarioMenu");
    
    if (adUsuarioBtn && adUsuarioMenu) {
        adUsuarioBtn.addEventListener("click", function(e) {
            e.preventDefault();
            e.stopPropagation();
            adUsuarioMenu.classList.toggle("abierto");
        });

        document.addEventListener("click", function(e) {
            if (adUsuarioMenu.classList.contains("abierto") && 
                !adUsuarioMenu.contains(e.target) && 
                !adUsuarioBtn.contains(e.target)) {
                adUsuarioMenu.classList.remove("abierto");
            }
        });
    }

    const adFecha = document.getElementById("adFecha");
    if (adFecha) {
        const f = new Date().toLocaleDateString("es-CO", {
            weekday: "long", day: "numeric", month: "long", year: "numeric"
        });
        adFecha.textContent = f.charAt(0).toUpperCase() + f.slice(1);
    }
});