document.addEventListener("DOMContentLoaded", function () {
    
    const btnUser = document.getElementById("btnUser");
    const userMenu = document.getElementById("userMenu");
    if (btnUser && userMenu) {
        btnUser.addEventListener("click", function (e) {
            e.preventDefault();
            e.stopPropagation();
            const isOpen = userMenu.classList.toggle("abierto");
            btnUser.setAttribute("aria-expanded", String(isOpen));
        });
        document.addEventListener("click", function (e) {
            if (!userMenu.contains(e.target) && !btnUser.contains(e.target)) {
                userMenu.classList.remove("abierto");
                btnUser.setAttribute("aria-expanded", "false");
            }
        });
    }

    const lightbox = document.getElementById("lightbox");
    const lbImg = document.getElementById("lbImg");
    const lbTitulo = document.getElementById("lbTitulo");
    const lbCat = document.getElementById("lbCat");
    const lbPos = document.getElementById("lbPos");
    const lbCerrar = document.getElementById("lbCerrar");
    const lbPrev = document.getElementById("lbPrev");
    const lbNext = document.getElementById("lbNext");
    
    const tiles = Array.from(document.querySelectorAll(".tile-photo"));
    let currentIndex = 0;
    let lightboxTrigger = null;

    const btnPantalla = document.getElementById("btnPantalla");

    function abrirLightbox(index, trigger) {
        if (!tiles.length || !lightbox) return;
        if (index < 0) index = tiles.length - 1;
        if (index >= tiles.length) index = 0;
        
        currentIndex = index;
        const tile = tiles[currentIndex];
        
        lbImg.src = tile.dataset.src;
        lbTitulo.textContent = tile.dataset.titulo;
        lbCat.textContent = tile.dataset.categoria;
        lbPos.textContent = `${currentIndex + 1} / ${tiles.length}`;
        if (trigger) lightboxTrigger = trigger;
        lightbox.hidden = false;
        lightbox.setAttribute("aria-hidden", "false");
        lightbox.classList.add("activo");
        document.body.classList.add("lightbox-open");
    }

    function cerrarLightbox() {
        if (!lightbox) return;
        lightbox.classList.remove("activo");
        lightbox.hidden = true;
        lightbox.setAttribute("aria-hidden", "true");
        document.body.classList.remove("lightbox-open");
        if (lightboxTrigger) lightboxTrigger.focus();
    }

    tiles.forEach((tile, index) => {
        tile.addEventListener("click", function () {
            abrirLightbox(index, tile);
        });
    });

    if (btnPantalla && tiles.length > 0) {
        btnPantalla.addEventListener("click", function () {
            abrirLightbox(0, btnPantalla);
        });
    }

    if (lbCerrar) lbCerrar.addEventListener("click", cerrarLightbox);
    if (lbPrev) lbPrev.addEventListener("click", () => abrirLightbox(currentIndex - 1));
    if (lbNext) lbNext.addEventListener("click", () => abrirLightbox(currentIndex + 1));

    if (lightbox) {
        lightbox.addEventListener("click", function (e) {
            if (e.target === lightbox) cerrarLightbox();
        });
    }

    document.addEventListener("keydown", function (e) {
        if (!lightbox || !lightbox.classList.contains("activo")) return;
        
        if (e.key === "Escape") cerrarLightbox();
        if (e.key === "ArrowLeft") abrirLightbox(currentIndex - 1);
        if (e.key === "ArrowRight") abrirLightbox(currentIndex + 1);
    });
});
