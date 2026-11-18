// ==========================================
// CARRUSEL
// ==========================================

const carrusel = document.getElementById('heroCarousel');
const puntos = document.querySelectorAll('.hero__dots [data-bs-target]');

if (carrusel) {
    carrusel.addEventListener('slide.bs.carousel', function (e) {
        puntos.forEach(function (punto, i) {
            punto.classList.toggle('active', i === e.to);
        });
    });
}


// ==========================================
// NAVBAR AL HACER SCROLL
// ==========================================

const barra = document.querySelector('.nav-transparente');

if (barra) {

    function revisarScroll() {
        barra.classList.toggle('scrolled', window.scrollY > 50);
    }

    window.addEventListener('scroll', revisarScroll);
    revisarScroll();
}


// ==========================================
// RESERVA
// ==========================================

(function () {

    // ------------------------------------------
    // FECHAS
    // ------------------------------------------

    const meses = [
        'Enero', 'Febrero', 'Marzo', 'Abril',
        'Mayo', 'Junio', 'Julio', 'Agosto',
        'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'
    ];

    const inEntrada = document.getElementById('entrada');
    const inSalida = document.getElementById('salida');

    const btnEntrada = document.getElementById('btnEntrada');
    const btnSalida = document.getElementById('btnSalida');


    if (inEntrada && inSalida && btnEntrada && btnSalida) {

        function aISO(fecha) {
            return fecha.getFullYear() + '-' +
                String(fecha.getMonth() + 1).padStart(2, '0') + '-' +
                String(fecha.getDate()).padStart(2, '0');
        }


        function deISO(fecha) {
            const partes = fecha.split('-').map(Number);

            return new Date(
                partes[0],
                partes[1] - 1,
                partes[2]
            );
        }


        function sumarDias(fecha, cantidad) {
            const resultado = new Date(fecha);
            resultado.setDate(resultado.getDate() + cantidad);

            return resultado;
        }


        function pintar(boton, fechaISO) {

            const fecha = deISO(fechaISO);

            const numero = boton.querySelector('strong');
            const mes = boton.querySelector('.reserva-mes');

            if (numero) {
                numero.textContent = fecha.getDate();
            }

            if (mes) {
                mes.textContent =
                    meses[fecha.getMonth()] +
                    '/' +
                    fecha.getFullYear();
            }
        }


        function actualizarFechas() {

            const hoy = new Date();

            if (!inEntrada.value) {
                inEntrada.value = aISO(hoy);
            }

            const salidaMinima =
                aISO(sumarDias(deISO(inEntrada.value), 1));

            inSalida.min = salidaMinima;

            if (
                !inSalida.value ||
                inSalida.value < salidaMinima
            ) {
                inSalida.value = salidaMinima;
            }

            pintar(btnEntrada, inEntrada.value);
            pintar(btnSalida, inSalida.value);
        }


        function abrirCalendario(input) {

            try {
                input.showPicker();
            } catch (error) {
                input.focus();
            }
        }


        // Valores iniciales

        const hoy = new Date();

        inEntrada.min = aISO(hoy);
        inEntrada.value = aISO(hoy);

        inSalida.value =
            aISO(sumarDias(hoy, 1));

        actualizarFechas();


        // Botón Entrada

        btnEntrada.addEventListener('click', function () {
            abrirCalendario(inEntrada);
        });


        // Botón Salida

        btnSalida.addEventListener('click', function () {
            abrirCalendario(inSalida);
        });


        // Cuando cambia Entrada

        inEntrada.addEventListener('change', function () {
            actualizarFechas();
        });


        // Cuando cambia Salida

        inSalida.addEventListener('change', function () {
            actualizarFechas();
        });

    }


    // ==========================================
    // OCUPACIÓN
    // ==========================================

    const cantidades = {
        adultos: 1,
        ninos: 0
    };

    const limites = {
        adultos: [1, 10],
        ninos: [0, 10]
    };


    function pintarOcupacion() {

        const verAdultos = document.getElementById('verAdultos');
        const verNinos = document.getElementById('verNinos');

        const cantAdultos = document.getElementById('cantAdultos');
        const cantNinos = document.getElementById('cantNinos');

        const inAdultos = document.getElementById('inAdultos');
        const inNinos = document.getElementById('inNinos');


        if (verAdultos) {
            verAdultos.textContent = cantidades.adultos;
        }

        if (verNinos) {
            verNinos.textContent = cantidades.ninos;
        }

        if (cantAdultos) {
            cantAdultos.textContent = cantidades.adultos;
        }

        if (cantNinos) {
            cantNinos.textContent = cantidades.ninos;
        }

        if (inAdultos) {
            inAdultos.value = cantidades.adultos;
        }

        if (inNinos) {
            inNinos.value = cantidades.ninos;
        }


        document.querySelectorAll('[data-contador]').forEach(function (boton) {

            const tipo = boton.dataset.contador;
            const paso = Number(boton.dataset.paso);

            const limite = limites[tipo];

            if (!limite) {
                return;
            }

            const minimo = limite[0];
            const maximo = limite[1];

            const valor = cantidades[tipo];

            boton.disabled =
                (paso < 0 && valor <= minimo) ||
                (paso > 0 && valor >= maximo);
        });
    }


    document.querySelectorAll('[data-contador]').forEach(function (boton) {

        boton.addEventListener('click', function (e) {

            e.preventDefault();
            e.stopPropagation();

            const tipo = boton.dataset.contador;
            const paso = Number(boton.dataset.paso);

            if (!limites[tipo]) {
                return;
            }

            const minimo = limites[tipo][0];
            const maximo = limites[tipo][1];

            cantidades[tipo] += paso;

            if (cantidades[tipo] < minimo) {
                cantidades[tipo] = minimo;
            }

            if (cantidades[tipo] > maximo) {
                cantidades[tipo] = maximo;
            }

            pintarOcupacion();
        });

    });


    pintarOcupacion();


    // ==========================================
    // VENTANA DE OCUPACIÓN
    // ==========================================

    const btnOcupacion =
        document.querySelector('.reserva-ocupacion');

    const panelOcupacion =
        document.querySelector('.reserva-panel');


    if (btnOcupacion && panelOcupacion) {

        btnOcupacion.addEventListener('click', function (e) {

            e.preventDefault();
            e.stopPropagation();

            panelOcupacion.classList.toggle('mostrar-ocupacion');

        });


        document.addEventListener('click', function (e) {

            if (
                !panelOcupacion.contains(e.target) &&
                !btnOcupacion.contains(e.target)
            ) {
                panelOcupacion.classList.remove('mostrar-ocupacion');
            }

        });

    }

})();

const observador = new IntersectionObserver((entradas) => {
    entradas.forEach((e) => {
        if (e.isIntersecting) {
            e.target.classList.add('visible');}
        else {
            e.target.classList.remove('visible');  
        }
    });
}, { threshold: 0.2 });

document.querySelectorAll('.animar-izquierda, .animar-derecha')
    .forEach(el => observador.observe(el));

const track = document.getElementById('galeriaTrack');
const btnPrev = document.getElementById('btnPrev');
const btnNext = document.getElementById('btnNext');

if (track && btnPrev && btnNext) {
    const paso = 340;   // ancho de cada tarjeta + gap

    btnNext.addEventListener('click', () => {
        track.scrollBy({ left: paso, behavior: 'smooth' });
    });

    btnPrev.addEventListener('click', () => {
        track.scrollBy({ left: -paso, behavior: 'smooth' });
    });
}

/* --- Galería horizontal + Lightbox --- */
(function () {
    const track  = document.getElementById('galeriaTrack');
    const btnPrev = document.getElementById('btnPrev');
    const btnNext = document.getElementById('btnNext');
    const imagenes = track ? track.querySelectorAll('.galeria-item img') : [];

    // Flechas del carrusel
    if (track && btnPrev && btnNext) {
        const paso = 340;
        btnNext.addEventListener('click', () => track.scrollBy({ left: paso, behavior: 'smooth' }));
        btnPrev.addEventListener('click', () => track.scrollBy({ left: -paso, behavior: 'smooth' }));
    }

    // Lightbox
    const lightbox = document.getElementById('lightbox');
    const lbImg   = document.getElementById('lbImg');
    const lbCerrar = document.getElementById('lbCerrar');
    const lbPrev  = document.getElementById('lbPrev');
    const lbNext  = document.getElementById('lbNext');
    let indiceActual = 0;

    function mostrarImagen(i) {
        if (i < 0) i = imagenes.length - 1;
        if (i >= imagenes.length) i = 0;
        indiceActual = i;
        lbImg.src = imagenes[i].src;
        lbImg.alt = imagenes[i].alt;
    }

    function abrirLightbox(i) {
        mostrarImagen(i);
        lightbox.classList.add('activo');
        document.body.style.overflow = 'hidden';   // EVITA EL SCROLL DE FONDO
            }

    function cerrarLightbox() {
        lightbox.classList.remove('activo');
        document.body.style.overflow = '';
    }

    imagenes.forEach((img, i) => {
        img.parentElement.addEventListener('click', () => abrirLightbox(i));
    });

    lbCerrar.addEventListener('click', cerrarLightbox);
    lbPrev.addEventListener('click', (e) => { e.stopPropagation(); mostrarImagen(indiceActual - 1); });
    lbNext.addEventListener('click', (e) => { e.stopPropagation(); mostrarImagen(indiceActual + 1); });

    // CERRAR AL HACER CLICK EN EL FONDO
    lightbox.addEventListener('click', (e) => {
        if (e.target === lightbox) cerrarLightbox();
    });

    // NAVEGAR CON TECLADO
    document.addEventListener('keydown', (e) => {
        if (!lightbox.classList.contains('activo')) return;
        if (e.key === 'Escape')     cerrarLightbox();
        if (e.key === 'ArrowLeft')  mostrarImagen(indiceActual - 1);
        if (e.key === 'ArrowRight') mostrarImagen(indiceActual + 1);
    });
})();

/* --- Modal de ocupación --- */
(function () {
    const modal      = document.getElementById('modalOcupacion');
    const btnAbrir   = document.getElementById('btnOcupacion');
    const btnCerrar  = document.getElementById('cerrarOcupacion');
    const btnAplicar = document.getElementById('aplicarOcupacion');

    if (!modal || !btnAbrir) return;

    const cantidades = { adultos: 1, ninos: 0 };
    const limites = { adultos: [1, 10], ninos: [0, 10] };

    function pintar() {
        document.getElementById('verAdultos').textContent = cantidades.adultos;
        document.getElementById('verNinos').textContent   = cantidades.ninos;
        document.getElementById('cantAdultos').textContent = cantidades.adultos;
        document.getElementById('cantNinos').textContent   = cantidades.ninos;
        document.getElementById('inAdultos').value = cantidades.adultos;
        document.getElementById('inNinos').value   = cantidades.ninos;

        document.querySelectorAll('[data-contador]').forEach(btn => {
            const tipo = btn.dataset.contador;
            const [min, max] = limites[tipo];
            const valor = cantidades[tipo];
            btn.disabled = (Number(btn.dataset.paso) < 0 && valor <= min) ||
                           (Number(btn.dataset.paso) > 0 && valor >= max);
        });
    }

    document.querySelectorAll('[data-contador]').forEach(btn => {
        btn.addEventListener('click', () => {
            const tipo = btn.dataset.contador;
            const [min, max] = limites[tipo];
            cantidades[tipo] = Math.min(max, Math.max(min, cantidades[tipo] + Number(btn.dataset.paso)));
            pintar();
        });
    });

    function abrir() { modal.classList.add('activo'); }
    function cerrar() { modal.classList.remove('activo'); }

    btnAbrir.addEventListener('click', abrir);
    btnCerrar.addEventListener('click', cerrar);
    btnAplicar.addEventListener('click', cerrar);

    modal.addEventListener('click', (e) => {
        if (e.target === modal) cerrar();
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && modal.classList.contains('activo')) cerrar();
    });

    pintar();
})();


(function(){
    const btnFiltro = document.getElementById('btnFiltro');
    const chips     = document.getElementById('filtrosChips');
    const todosLosChips = document.querySelectorAll('.chip');
    const items     = document.querySelectorAll('.galeria-item[data-categoria]');

    if (!btnFiltro || !chips) return;


    btnFiltro.addEventListener('click', () => {
        chips.classList.toggle('visible');
        btnFiltro.classList.toggle('activo');
    });

  
    todosLosChips.forEach(chip => {
        chip.addEventListener('click', () => {
            todosLosChips.forEach(c => c.classList.remove('activo'));
            chip.classList.add('activo');

            const filtro = chip.dataset.filtro;
            items.forEach(item => {
                if (filtro === 'todos' || item.dataset.categoria === filtro) {
                    item.style.display = '';
                } else {
                    item.style.display = 'none';
                }
            });
        });
    });
})();


// GALERÍA: FILTROS

const btnFiltro = document.getElementById('btnFiltro');
const chipsBox = document.getElementById('filtrosChips');

if (btnFiltro && chipsBox) {

    btnFiltro.addEventListener('click', function () {
        chipsBox.classList.toggle('visible');
        btnFiltro.classList.toggle('activo');
    });

    const chips = chipsBox.querySelectorAll('.chip');
    const tarjetas = document.querySelectorAll('#galeriaGrid .galeria-item:not(.placeholder)');

    // MUSTRA CATEGORIAS ESPECIFICAS
    chips.forEach(function (chip) {
        chip.addEventListener('click', function () {

            chips.forEach(function (c) { c.classList.remove('activo'); });
            chip.classList.add('activo');

            const filtro = chip.dataset.filtro;

            tarjetas.forEach(function (tarjeta) {
                const mostrar = filtro === 'todos' || tarjeta.dataset.categoria === filtro;
                tarjeta.style.display = mostrar ? '' : 'none';
            });
        });
    });
}


(function () {
    const btnUser = document.getElementById('btnUser');
    const userMenu = document.getElementById('userMenu');

    if (!btnUser || !userMenu) return;

    btnUser.addEventListener('click', function (e) {
        e.stopPropagation();
        userMenu.classList.toggle('abierto');
    });

    document.addEventListener('click', function (e) {
        if (!userMenu.contains(e.target) && e.target !== btnUser) {
            userMenu.classList.remove('abierto');
        }
    });
})();


/* MENÚ DESPLEGABLE DEL USUARIO */
(function () {
    const boton = document.getElementById("btnUser");
    const menu = document.getElementById("userMenu");

    // Si no hay sesión iniciada, estos elementos no existirán.
    if (!boton || !menu) {
        return;
    }

    function cerrarMenu() {
        menu.classList.remove("abierto");
        boton.setAttribute("aria-expanded", "false");
    }

    boton.addEventListener("click", function (evento) {
        evento.preventDefault();
        evento.stopPropagation();

        const abierto = menu.classList.toggle("abierto");

        boton.setAttribute("aria-expanded", String(abierto));
    });

    menu.addEventListener("click", function (evento) {
        evento.stopPropagation();
    });

    document.addEventListener("click", function (evento) {
        if (
            !menu.contains(evento.target) &&
            !boton.contains(evento.target)
        ) {
            cerrarMenu();
        }
    });

    document.addEventListener("keydown", function (evento) {
        if (evento.key === "Escape") {
            cerrarMenu();
            boton.focus();
        }
    });
})();


/* MENÚ DESPLEGABLE DE USUARIO */
(function () {
    const boton = document.getElementById("btnUser");
    const menu = document.getElementById("userMenu");

    if (!boton || !menu) return;

    function cerrarMenu() {
        menu.classList.remove("abierto");
        boton.setAttribute("aria-expanded", "false");
    }

    boton.addEventListener("click", function (evento) {
        evento.preventDefault();
        evento.stopPropagation();
        const abierto = menu.classList.toggle("abierto");
        boton.setAttribute("aria-expanded", String(abierto));
    });

    menu.addEventListener("click", function (evento) {
        evento.stopPropagation();
    });

    document.addEventListener("click", function (evento) {
        if (!menu.contains(evento.target) && !boton.contains(evento.target)) {
            cerrarMenu();
        }
    });

    document.addEventListener("keydown", function (evento) {
        if (evento.key === "Escape") {
            cerrarMenu();
            boton.focus();
        }
    });
})();
