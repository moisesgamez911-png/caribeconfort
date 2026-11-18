document.addEventListener("DOMContentLoaded", function() {
    
    let habitacionesSeleccionadas = [];
    const botonesAnadir = document.querySelectorAll(".btn-anadir");

    const btnReservarGlobal = document.getElementById("btnReservarGlobal");
    const inEntrada = document.getElementById("entrada");
    const inSalida = document.getElementById("salida");
    const selectAdultos = document.getElementById("adultos");
    const selectNinos = document.getElementById("ninos");
    const selectTipo = document.getElementById("tipoHabitacion");
    const codigoConvenio = document.getElementById("codigoConvenio");
    const btnAplicarCodigo = document.getElementById("btnAplicarCodigo");
    const formBuscador = document.getElementById("bookingForm");

    const modalConfirm = document.getElementById("miModalReserva");
    const btnCerrarModal = document.getElementById("btnCerrarModal");
    const btnCancelarModal = document.getElementById("btnCancelarModal");
    const btnConfirmarReserva = document.getElementById("btnConfirmarReserva");
    const formReserva = document.getElementById("formularioReserva");

    const modalError = document.getElementById("modalErrorReserva");
    const btnCerrarError = document.getElementById("btnCerrarError");
    const modalErrorServidor = document.getElementById("modalErrorServidor");
    const btnCerrarErrorServidor = document.getElementById("btnCerrarErrorServidor");

    const roomsContainer = document.getElementById("rooms");
    const btnPrev = document.getElementById("prev");
    const btnNext = document.getElementById("next");
    const guardadas = sessionStorage.getItem('reservas_seleccionadas');
    if (guardadas) {
        const seleccionPrevia = JSON.parse(guardadas);

        seleccionPrevia.forEach(function(saved) {
            const btn = Array.from(botonesAnadir).find(b => {
                const ids = b.getAttribute('data-ids')?.split(',') || [];
                return ids.includes(saved.id);
            });

            if (btn) {
                btn.classList.add("seleccionada");
                btn.textContent = "Añadida";
                
                habitacionesSeleccionadas.push({
                    id: saved.id,
                    numero: saved.numero,
                    precio: saved.precio,
                    card: btn.closest(".room-card")
                });
            }
        });
    }

    function guardarSeleccionEnMemoria() {
        const datosAGuardar = habitacionesSeleccionadas.map(h => ({
            id: h.id,
            numero: h.numero,
            precio: h.precio
        }));
        sessionStorage.setItem('reservas_seleccionadas', JSON.stringify(datosAGuardar));
    }
    // --------------------------------------------------

    if (roomsContainer && btnPrev && btnNext) {
        btnNext.addEventListener("click", function(e) {
            e.preventDefault();
            roomsContainer.scrollBy({ left: 520, behavior: 'smooth' });
        });
        btnPrev.addEventListener("click", function(e) {
            e.preventDefault();
            roomsContainer.scrollBy({ left: -520, behavior: 'smooth' });
        });
    }

    function aplicarFiltros() {
        if (!formBuscador) return;
        const params = new URLSearchParams(new FormData(formBuscador)).toString();
        window.location.href = `/reservas?${params}`;
    }

    if (selectTipo) selectTipo.addEventListener("change", aplicarFiltros);
    if (inEntrada) inEntrada.addEventListener("change", aplicarFiltros);
    if (inSalida) inSalida.addEventListener("change", aplicarFiltros);
    if (btnAplicarCodigo) btnAplicarCodigo.addEventListener("click", aplicarFiltros);
    if (codigoConvenio) codigoConvenio.addEventListener("keydown", function(event) {
        if (event.key === "Enter") {
            event.preventDefault();
            aplicarFiltros();
        }
    });

    botonesAnadir.forEach(btn => {
        btn.addEventListener("click", function() {
            const idsString = this.getAttribute("data-ids");
            if (!idsString) return;
            
            const idsArray = idsString.split(',');
            const nombreTipo = this.getAttribute("data-nombre");
            const precio = parseFloat(this.getAttribute("data-precio"));

            const seleccionadasDeEsteTipo = habitacionesSeleccionadas.filter(h => idsArray.includes(h.id));

            if (seleccionadasDeEsteTipo.length > 0) {
                habitacionesSeleccionadas = habitacionesSeleccionadas.filter(h => !idsArray.includes(h.id));
                this.classList.remove("seleccionada");
                this.textContent = "Añadir";
            } else {
                const idParaSeleccionar = idsArray[0];
                habitacionesSeleccionadas.push({
                    id: idParaSeleccionar,
                    numero: nombreTipo,
                    precio: precio,
                    card: this.closest(".room-card") 
                });
                this.classList.add("seleccionada");
                this.textContent = "Añadida";
            }

            guardarSeleccionEnMemoria();
        });
    });

    if (btnReservarGlobal) {
        btnReservarGlobal.addEventListener("click", function() {
            let hayError = false;

            if(inEntrada) inEntrada.classList.remove("campo-error");
            if(inSalida) inSalida.classList.remove("campo-error");
            if(selectAdultos) selectAdultos.classList.remove("campo-error");
            if(selectNinos) selectNinos.classList.remove("campo-error");

            if (!inEntrada.value) { if(inEntrada) inEntrada.classList.add("campo-error"); hayError = true; }
            if (!inSalida.value) { if(inSalida) inSalida.classList.add("campo-error"); hayError = true; }
            if (!selectAdultos.value) { if(selectAdultos) selectAdultos.classList.add("campo-error"); hayError = true; }
            if (!selectNinos.value) { if(selectNinos) selectNinos.classList.add("campo-error"); hayError = true; }

            if (habitacionesSeleccionadas.length === 0) {
                hayError = true;
            }

            if (hayError) {
                if (modalError) {
                    modalError.classList.add("activo");
                }
                return; 
            }

            const formatF = (str) => {
                if(!str) return "--";
                const p = str.split('-');
                const d = new Date(p[0], p[1]-1, p[2]);
                return d.toLocaleDateString('es-ES', { day: 'numeric', month: 'long', year: 'numeric' });
            };

            const txtEntrada = document.getElementById("txtEntrada");
            const txtSalida = document.getElementById("txtSalida");
            const txtNoches = document.getElementById("txtNoches");
            const txtAdultos = document.getElementById("txtAdultos");
            const txtNinos = document.getElementById("txtNinos");
            const txtHabNumero = document.getElementById("txtHabNumero");
            const txtPrecioNoche = document.getElementById("txtPrecioNoche");
            const txtDesayuno = document.getElementById("txtDesayuno");
            const filaDesayuno = document.getElementById("filaDesayuno");
            const txtTotal = document.getElementById("txtTotal");
            const filaDescuento = document.getElementById("filaDescuento");
            const txtDescuento = document.getElementById("txtDescuento");

            if (txtEntrada) txtEntrada.textContent = formatF(inEntrada.value);
            if (txtSalida) txtSalida.textContent = formatF(inSalida.value);
            
            if (txtAdultos) txtAdultos.textContent = selectAdultos.options[selectAdultos.selectedIndex].text;
            if (txtNinos) txtNinos.textContent = selectNinos.options[selectNinos.selectedIndex].text;

            const d1 = new Date(inEntrada.value);
            const d2 = new Date(inSalida.value);
            let noches = Math.ceil((d2 - d1) / (1000 * 60 * 60 * 24));
            if (txtNoches) txtNoches.textContent = noches + " noches";
            
            let conteoNombres = {};
            let totalNoches = 0;
            let totalDesayunos = 0;
            let precioBaseNoche = 0; 

            habitacionesSeleccionadas.forEach(function(hab) {
                conteoNombres[hab.numero] = (conteoNombres[hab.numero] || 0) + 1;
                
                precioBaseNoche += hab.precio; 
                totalNoches += (hab.precio * noches);

                const checkDesayuno = hab.card.querySelector(".breakfast-check");
                if (checkDesayuno && checkDesayuno.checked) {
                    const precioDes = parseFloat(checkDesayuno.getAttribute("data-precio"));
                    totalDesayunos += (precioDes * noches);
                }
            });

            let habTexto = Object.keys(conteoNombres).map(k => `${k} (x${conteoNombres[k]})`).join(", ");
            if (txtHabNumero) txtHabNumero.textContent = habTexto;
            if (txtPrecioNoche) txtPrecioNoche.textContent = "$ " + precioBaseNoche.toLocaleString('es-CO');
            
            if (filaDesayuno && txtDesayuno) {
                if (totalDesayunos > 0) {
                    filaDesayuno.hidden = false;
                    txtDesayuno.textContent = "$ " + totalDesayunos.toLocaleString('es-CO');
                } else {
                    filaDesayuno.hidden = true;
                }
            }

            const subtotal = totalNoches + totalDesayunos;
            const porcentajeDescuento = codigoConvenio ? Number(codigoConvenio.dataset.descuento || 0) : 0;
            const valorDescuento = subtotal * porcentajeDescuento / 100;
            let granTotal = subtotal - valorDescuento;
            if (filaDescuento && txtDescuento && porcentajeDescuento > 0) {
                filaDescuento.hidden = false;
                txtDescuento.textContent = `-${porcentajeDescuento}% ($ ${valorDescuento.toLocaleString('es-CO')})`;
            } else if (filaDescuento) {
                filaDescuento.hidden = true;
            }
            if (txtTotal) txtTotal.textContent = "$ " + granTotal.toLocaleString('es-CO');
            
            if (modalConfirm) {
                modalConfirm.classList.add("activo");
            }
        });
    }

    if(btnCerrarModal && modalConfirm) btnCerrarModal.addEventListener("click", () => modalConfirm.classList.remove("activo"));
    if(btnCancelarModal && modalConfirm) btnCancelarModal.addEventListener("click", () => modalConfirm.classList.remove("activo"));
    if(btnCerrarError && modalError) btnCerrarError.addEventListener("click", () => modalError.classList.remove("activo"));
    if(btnCerrarErrorServidor && modalErrorServidor) btnCerrarErrorServidor.addEventListener("click", () => modalErrorServidor.classList.remove("activo"));

    if(inEntrada) inEntrada.addEventListener("input", () => inEntrada.classList.remove("campo-error"));
    if(inSalida) inSalida.addEventListener("input", () => inSalida.classList.remove("campo-error"));
    if(selectAdultos) selectAdultos.addEventListener("change", () => selectAdultos.classList.remove("campo-error"));
    if(selectNinos) selectNinos.addEventListener("change", () => selectNinos.classList.remove("campo-error"));

    if (btnConfirmarReserva) {
        btnConfirmarReserva.addEventListener("click", async function(e) {
            e.preventDefault();

            btnConfirmarReserva.disabled = true;
            btnConfirmarReserva.innerHTML = "Procesando...";

            const formData = new FormData(formReserva);
            const idsArray = habitacionesSeleccionadas.map(h => h.id);
            const desayunosSeleccionados = habitacionesSeleccionadas
                .filter(function(hab) {
                    const check = hab.card ? hab.card.querySelector(".breakfast-check") : null;
                    return check && check.checked;
                })
                .map(function(hab) { return hab.id; });
            
            formData.append("habitacion_ids", idsArray.join(","));
            desayunosSeleccionados.forEach(function(id) { formData.append("desayuno_ids", id); });
            formData.append("entrada", inEntrada.value);
            formData.append("salida", inSalida.value);
            formData.append("adultos", selectAdultos.value);
            formData.append("ninos", selectNinos.value);
            if (codigoConvenio && codigoConvenio.value.trim()) {
                formData.append("codigo_convenio", codigoConvenio.value.trim());
            }

            try {
                const response = await fetch('/reservas/crear', {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': formData.get('csrfmiddlewaretoken'),
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: formData
                });
                
                const data = await response.json();

                if (data.ok) {
                    sessionStorage.removeItem('reservas_seleccionadas');
                    window.location.href = `/pagar-reserva/${data.reserva_id}`;
                } else {
                    if (data.redirect) {
                        window.location.href = data.redirect;
                        return;
                    }
                    const textoErrorServidor = document.getElementById("textoErrorServidor");
                    if (textoErrorServidor) textoErrorServidor.textContent = data.error;
                    if (modalErrorServidor) modalErrorServidor.classList.add("activo");
                    
                    btnConfirmarReserva.disabled = false;
                    btnConfirmarReserva.innerHTML = 'Confirmar reserva';
                }
            } catch (error) {
                console.error("Error de conexión:", error);
                window.ccAlert("Error de conexión. Intenta de nuevo.");
                btnConfirmarReserva.disabled = false;
                btnConfirmarReserva.innerHTML = 'Confirmar reserva';
            }
        });
    }
});

document.addEventListener("DOMContentLoaded", function() {
    const btnUser = document.getElementById("btnUser");
    const userMenu = document.getElementById("userMenu");

    if (btnUser && userMenu) {
        btnUser.addEventListener("click", function(e) {
            e.preventDefault();
            e.stopPropagation(); 
            const abierto = userMenu.classList.toggle("abierto");
            btnUser.setAttribute("aria-expanded", String(abierto));
        });
        document.addEventListener("click", function(e) {
            if (!userMenu.contains(e.target) && !btnUser.contains(e.target)) {
                userMenu.classList.remove("abierto");
                btnUser.setAttribute("aria-expanded", "false");
            }
        });
    }
});

document.addEventListener("DOMContentLoaded", function() {
    const roomsContainer = document.getElementById("rooms");
    const galleryModal = document.getElementById("roomGalleryModal");
    const galleryTitle = document.getElementById("roomGalleryTitle");
    const galleryImages = document.getElementById("roomGalleryImages");
    const galleryClose = document.getElementById("btnCerrarGaleria");
    const galleryPrev = document.getElementById("roomGalleryPrev");
    const galleryNext = document.getElementById("roomGalleryNext");
    const galleryPosition = document.getElementById("roomGalleryPosition");
    let galleryTrigger = null;
    let galleryIndex = 0;

    function showGalleryGrid() {
        if (!galleryModal || !galleryImages) return;
        galleryModal.classList.remove("is-single");
        galleryImages.classList.remove("is-single");
        galleryImages.querySelectorAll(".room-gallery-modal-photo").forEach(function(photo) {
            photo.hidden = false;
        });
    }

    function showGalleryPhoto(index) {
        if (!galleryModal || !galleryImages) return;
        const photos = Array.from(galleryImages.querySelectorAll(".room-gallery-modal-photo"));
        if (!photos.length) return;

        galleryIndex = (index + photos.length) % photos.length;
        galleryModal.classList.add("is-single");
        galleryImages.classList.add("is-single");
        photos.forEach(function(photo, photoIndex) {
            photo.hidden = photoIndex !== galleryIndex;
        });
        if (galleryPosition) galleryPosition.textContent = `${galleryIndex + 1} / ${photos.length}`;
    }

    function openGallery(roomCard, trigger, selectedIndex) {
        if (!galleryModal || !galleryTitle || !galleryImages) return;
        const heading = roomCard.querySelector(".room-heading h2");
        galleryTitle.textContent = heading ? heading.textContent.trim() : "";
        galleryImages.textContent = "";

        roomCard.querySelectorAll(".room-gallery img").forEach(function(sourceImage, index) {
            const photo = document.createElement("button");
            const image = sourceImage.cloneNode(false);
            photo.type = "button";
            photo.className = "room-gallery-modal-photo";
            photo.setAttribute("aria-label", sourceImage.alt || galleryTitle.textContent);
            image.removeAttribute("loading");
            photo.appendChild(image);
            photo.addEventListener("click", function() {
                showGalleryPhoto(index);
            });
            galleryImages.appendChild(photo);
        });

        galleryTrigger = trigger;
        galleryModal.hidden = false;
        galleryModal.setAttribute("aria-hidden", "false");
        document.body.classList.add("gallery-open");
        if (selectedIndex === null) {
            showGalleryGrid();
        } else {
            showGalleryPhoto(selectedIndex);
        }
        if (galleryClose) galleryClose.focus();
    }

    function closeGallery() {
        if (!galleryModal || galleryModal.hidden) return;
        galleryModal.hidden = true;
        galleryModal.setAttribute("aria-hidden", "true");
        galleryModal.classList.remove("is-single");
        document.body.classList.remove("gallery-open");
        if (galleryTrigger) galleryTrigger.focus();
    }

    if (roomsContainer) {
        roomsContainer.addEventListener("click", function(event) {
            if (!(event.target instanceof Element)) return;

            const tab = event.target.closest("[data-room-tab]");
            if (tab && roomsContainer.contains(tab)) {
                const roomCard = tab.closest(".room-card");
                if (!roomCard) return;

                roomCard.querySelectorAll("[data-room-tab]").forEach(function(roomTab) {
                    const selected = roomTab === tab;
                    roomTab.classList.toggle("room-tab-active", selected);
                    roomTab.setAttribute("aria-selected", String(selected));
                    roomTab.setAttribute("tabindex", selected ? "0" : "-1");
                });
                roomCard.querySelectorAll("[data-room-panel]").forEach(function(panel) {
                    panel.hidden = panel.dataset.roomPanel !== tab.dataset.roomTab;
                });
                return;
            }

            const imageButton = event.target.closest("[data-gallery-image]");
            if (imageButton && roomsContainer.contains(imageButton)) {
                const roomCard = imageButton.closest(".room-card");
                if (!roomCard) return;
                const images = Array.from(roomCard.querySelectorAll(".room-gallery img"));
                const selectedIndex = images.indexOf(imageButton.querySelector("img"));
                if (selectedIndex >= 0) openGallery(roomCard, imageButton, selectedIndex);
                return;
            }

            const openButton = event.target.closest("[data-gallery-open]");
            if (!openButton || !roomsContainer.contains(openButton)) return;
            const roomCard = openButton.closest(".room-card");
            if (roomCard) openGallery(roomCard, openButton, null);
        });

        roomsContainer.addEventListener("keydown", function(event) {
            if (!(event.target instanceof Element) || !["ArrowLeft", "ArrowRight"].includes(event.key)) return;
            const tab = event.target.closest("[data-room-tab]");
            if (!tab) return;

            const tabs = Array.from(tab.closest(".room-tabs").querySelectorAll("[data-room-tab]"));
            const currentIndex = tabs.indexOf(tab);
            const direction = event.key === "ArrowRight" ? 1 : -1;
            const nextTab = tabs[(currentIndex + direction + tabs.length) % tabs.length];
            event.preventDefault();
            nextTab.focus();
            nextTab.click();
        });
    }

    if (galleryClose) galleryClose.addEventListener("click", closeGallery);
    if (galleryPrev) galleryPrev.addEventListener("click", function() {
        showGalleryPhoto(galleryIndex - 1);
    });
    if (galleryNext) galleryNext.addEventListener("click", function() {
        showGalleryPhoto(galleryIndex + 1);
    });
    if (galleryModal) {
        galleryModal.addEventListener("click", function(event) {
            if (event.target === galleryModal) closeGallery();
        });
        galleryModal.addEventListener("keydown", function(event) {
            if (event.key === "Escape") closeGallery();
            if (galleryModal.classList.contains("is-single") && event.key === "ArrowLeft") {
                event.preventDefault();
                showGalleryPhoto(galleryIndex - 1);
            }
            if (galleryModal.classList.contains("is-single") && event.key === "ArrowRight") {
                event.preventDefault();
                showGalleryPhoto(galleryIndex + 1);
            }
            if (event.key !== "Tab") return;

            const focusable = Array.from(galleryModal.querySelectorAll("button:not(:disabled)"))
                .filter(function(button) {
                    return !button.hidden && button.offsetParent !== null;
                });
            if (!focusable.length) return;
            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        });
    }
});