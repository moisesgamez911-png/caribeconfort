document.addEventListener("DOMContentLoaded", function () {

    // Evita que una imagen eliminada o una ruta antigua deje el texto alternativo
    // ocupando la tarjeta. La reserva y sus datos siguen visibles con un fallback.
    document.addEventListener("error", function (event) {
        const image = event.target;
        if (!(image instanceof HTMLImageElement)) return;
        if (!image.matches(".service-image, .history-photo img")) return;

        const fallback = document.createElement("span");
        fallback.className = image.classList.contains("service-image")
            ? "service-image service-image-placeholder"
            : "history-photo-placeholder";
        fallback.setAttribute("role", "img");
        fallback.setAttribute("aria-label", "Imagen no disponible");
        fallback.innerHTML = '<i class="bi bi-image" aria-hidden="true"></i>';
        image.replaceWith(fallback);
    }, true);
    
    const btnUser = document.getElementById("btnUser");
    const userMenu = document.getElementById("userMenu");
    if (btnUser && userMenu) {
        btnUser.addEventListener("click", function (e) {
            e.preventDefault();
            e.stopPropagation();
            const abierto = userMenu.classList.toggle("abierto");
            btnUser.setAttribute("aria-expanded", String(abierto));
        });
        document.addEventListener("click", function (e) {
            if (!userMenu.contains(e.target) && !btnUser.contains(e.target)) {
                userMenu.classList.remove("abierto");
                btnUser.setAttribute("aria-expanded", "false");
            }
        });
    }

    const updateCarouselControls = (track, previous, next) => {
        const canScroll = track.scrollWidth > track.clientWidth + 1;
        previous.hidden = !canScroll;
        next.hidden = !canScroll;

        const carousel = track.parentElement;
        if (carousel) carousel.classList.toggle("carousel-no-controls", !canScroll);
    };

    const bindCarousel = (trackId, previousId, nextId) => {
        const track = document.getElementById(trackId);
        const previous = document.getElementById(previousId);
        const next = document.getElementById(nextId);
        if (!track || !previous || !next) return;

        const scroll = direction => {
            track.scrollBy({ left: direction * track.clientWidth, behavior: "smooth" });
        };
        const updateControls = () => {
            updateCarouselControls(track, previous, next);
        };

        previous.addEventListener("click", () => scroll(-1));
        next.addEventListener("click", () => scroll(1));
        updateControls();
        window.addEventListener("resize", updateControls);
    };

    bindCarousel("carouselActivas", "btnPrev", "btnNext");
    bindCarousel("carouselHistorial", "btnPrevHistorial", "btnNextHistorial");
    bindCarousel("carouselServicios", "btnPrevServicios", "btnNextServicios");

    const filterButtons = document.querySelectorAll("[data-history-filter]");
    const historyCards = document.querySelectorAll(".history-card[data-hist]");
    filterButtons.forEach(button => {
        button.addEventListener("click", () => {
            const filter = button.dataset.historyFilter;
            filterButtons.forEach(item => {
                const isActive = item === button;
                item.classList.toggle("is-active", isActive);
                item.setAttribute("aria-pressed", String(isActive));
            });
            historyCards.forEach(card => {
                card.hidden = filter !== "all" && card.dataset.hist !== filter;
            });
            const track = document.getElementById("carouselHistorial");
            if (track) {
                track.scrollTo({ left: 0, behavior: "smooth" });
                const previous = document.getElementById("btnPrevHistorial");
                const next = document.getElementById("btnNextHistorial");
                if (previous && next) updateCarouselControls(track, previous, next);
            }
        });
    });

    const printButton = document.getElementById("btnImprimir");
    if (printButton) printButton.addEventListener("click", () => window.print());

    const modales = document.querySelectorAll('.btn-ver-detalle');
    const modal = document.getElementById("modalReserva");
    const modalConfirm = document.getElementById("modalConfirmarCancelacion");

    if (modal) {
        
        let idReservaActual = null;

        const cerrarModal = () => {
            modal.classList.remove("activo");
            if (modalConfirm) modalConfirm.classList.remove("activo");
        };

        const getCookie = (name) => {
            let cookieValue = null;
            if (document.cookie && document.cookie !== '') {
                const cookies = document.cookie.split(';');
                for (let i = 0; i < cookies.length; i++) {
                    const cookie = cookies[i].trim();
                    if (cookie.substring(0, name.length + 1) === (name + '=')) {
                        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                        break;
                    }
                }
            }
            if (!cookieValue && name === 'csrftoken') {
                const meta = document.querySelector('meta[name="csrf-token"]');
                cookieValue = meta ? meta.content : null;
            }
            return cookieValue;
        };

        const setConfirmationMessage = (state) => {
            const message = document.querySelector(".mensaje-confirmacion");
            if (!message) return;

            message.classList.remove("is-cancelada", "is-validacion", "is-pendiente");
            if (state === "Cancelada") {
                message.classList.add("is-cancelada");
                message.innerHTML = `
                    <i class="bi bi-x-circle-fill"></i>
                    <div>
                        <strong>Esta reserva ya ha sido cancelada.</strong>
                        <p>Si tienes dudas, por favor contacta con atención al cliente.</p>
                    </div>
                `;
            } else if (state === "Pendiente") {
                message.classList.add("is-pendiente");
                message.innerHTML = `
                    <i class="bi bi-hourglass-split"></i>
                    <div>
                        <strong>Tu reserva está pendiente de pago o confirmación.</strong>
                        <p>Revisa el saldo pendiente para completar el pago.</p>
                    </div>
                `;
            } else if (state === "Pagada - Por validar") {
                message.classList.add("is-validacion");
                message.innerHTML = `
                    <i class="bi bi-hourglass-split"></i>
                    <div>
                        <strong>Tu pago está siendo validado por el hotel.</strong>
                        <p>Te notificaremos por correo en cuanto la reserva sea confirmada.</p>
                    </div>
                `;
            } else if (state === "En curso") {
                message.innerHTML = `
                    <i class="bi bi-check-circle-fill"></i>
                    <div>
                        <strong>Tu estadía está en curso.</strong>
                        <p>Consulta aquí los detalles y el estado de pago de tu reserva.</p>
                    </div>
                `;
            } else if (state === "Finalizada") {
                message.innerHTML = `
                    <i class="bi bi-check-circle-fill"></i>
                    <div>
                        <strong>Esta estadía ha finalizado.</strong>
                        <p>Puedes imprimir el comprobante con el resumen de la reserva.</p>
                    </div>
                `;
            } else {
                message.innerHTML = `
                    <i class="bi bi-info-circle-fill"></i>
                    <div>
                        <strong>Esta reserva está confirmada y lista para el check-in.</strong>
                        <p>Puedes imprimir tu comprobante o cancelar la reserva si tus planes cambian.</p>
                    </div>
                `;
            }
        };

        modales.forEach(btn => {
            btn.addEventListener("click", function() {
                const nombre = this.dataset.nombre || '';
                const iniciales = nombre.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase() || 'U';

                const setVal = (id, val) => {
                    const el = document.getElementById(id);
                    if (el) el.textContent = val;
                };

                idReservaActual = this.dataset.id;
                const estado = this.dataset.estado || 'Pendiente';

                setVal("mdAvatar", iniciales);
                setVal("mdNombre", nombre);
                setVal("mdCorreo", this.dataset.correo || '');
                setVal("mdDocumento", this.dataset.documento || '');
                setVal("mdNacionalidad", this.dataset.nacionalidad || '');
                setVal("mdReservaNum", "#CC-" + (this.dataset.id || '').padStart(4, '0'));
                setVal("mdEntrada", this.dataset.entrada || '');
                setVal("mdSalida", this.dataset.salida || '');
                setVal("mdAcompanantes", this.dataset.acompanantes || '0');
                setVal("mdTotal", this.dataset.total || '$ 0');
                setVal("mdFechaRegistro", this.dataset.fechaRegistro || '');
                setVal("mdTlCreada", this.dataset.fechaRegistro || '');
                setVal("mdTotalReserva", (this.dataset.total || '$ 0') + ' COP');
                setVal("mdTotalPagado", this.dataset.pagado || '$ 0 COP');
                setVal("mdTotalReembolsado", this.dataset.reembolsado || '$ 0 COP');
                setVal("mdSaldoPendiente", this.dataset.saldo || '$ 0 COP');
                const totalReembolsado = Number.parseFloat(this.dataset.reembolsadoNumerico || "0");
                const filaReembolso = document.getElementById("mdReembolsoRow");
                if (filaReembolso) filaReembolso.hidden = totalReembolsado <= 0;
                setVal(
                    "mdTlConfirmadaLabel",
                    estado === "Pagada - Por validar" ? "Pago en validación" : "Confirmada"
                );
                setVal(
                    "mdTlConfirmada",
                    estado === "Pagada - Por validar" ? "Pendiente de validación" : "Estado de la reserva"
                );
                setVal("mdTlCheckin", this.dataset.entrada || '');
                setVal("mdTlCheckout", this.dataset.salida || '');

                const pasosCompletados = [
                    true,
                    ["Confirmada", "En curso", "Finalizada"].includes(estado),
                    ["En curso", "Finalizada"].includes(estado),
                    estado === "Finalizada"
                ];
                document.querySelectorAll(".linea-tiempo .paso").forEach((paso, index) => {
                    paso.classList.toggle("completado", pasosCompletados[index]);
                    paso.classList.toggle("pendiente", !pasosCompletados[index]);
                });

                const saldoPendiente = Number.parseFloat(this.dataset.saldoNumerico || "0");
                const totalPagadoNeto = Number.parseFloat(this.dataset.pagadoNetoNumerico || "0");
                let estadoPago = "Pago pendiente";
                if (estado === "Pagada - Por validar") {
                    estadoPago = "Pago registrado · en validación";
                } else if (totalReembolsado > 0) {
                    estadoPago = "Reembolso registrado";
                } else if (saldoPendiente <= 0 && totalPagadoNeto > 0) {
                    estadoPago = "Pago completo";
                } else if (totalPagadoNeto > 0) {
                    estadoPago = "Abono registrado";
                }
                setVal("mdEstadoPago", estadoPago);

                const btnPagarSaldo = document.getElementById("btnModalPagarSaldo");
                if (btnPagarSaldo) {
                    btnPagarSaldo.href = this.dataset.pagoUrl || "#";
                    btnPagarSaldo.classList.toggle(
                        "is-hidden",
                        !(saldoPendiente > 0) || estado === "Cancelada" || estado === "Finalizada"
                    );
                }
                
                const habImg = document.getElementById("mdHabImagen");
                if(this.dataset.habNumero && this.dataset.habNumero !== 'None') {
                    setVal("mdHabNumero", this.dataset.habNumero);
                    setVal("mdHabTipo", this.dataset.habTipo || '');
                    if (habImg) habImg.src = this.dataset.habImagen || '/static/img/imagenes/foto2.png';
                    setVal("mdHabCama", this.dataset.habCama || 'Cama estándar');
                } else {
                    setVal("mdHabNumero", 'N/A');
                    setVal("mdHabTipo", this.dataset.habTipo || 'Plan / Servicio');
                    if (habImg) habImg.src = this.dataset.habImagen || '/static/img/imagenes/foto2.png';
                }

                const badges = document.querySelectorAll("#mdEstadoBadge, #mdEstadoBadge2");
                badges.forEach(b => {
                    b.textContent = estado;
                    const parent = b.closest('.estado');
                    if (parent) {
                        parent.classList.remove('estado-confirmado', 'estado-pendiente', 'estado-cancelada', 'estado-validar');
                        if (estado === 'Pendiente') {
                            parent.classList.add('estado-pendiente');
                        } else if (estado === 'Cancelada') {
                            parent.classList.add('estado-cancelada');
                        } else if (estado === 'Pagada - Por validar') {
                            parent.classList.add('estado-validar');
                        } else {
                            parent.classList.add('estado-confirmado');
                        }
                    }
                });

                const btnAbrirCancelar = document.getElementById("btnAbrirCancelar");
                if (btnAbrirCancelar) {
                    btnAbrirCancelar.classList.toggle("is-hidden", estado === "Cancelada" || estado === "Finalizada");
                }
                setConfirmationMessage(estado);

                modal.classList.add("activo");
            });
        });

        if (document.getElementById("btnAbrirCancelar")) {
            document.getElementById("btnAbrirCancelar").addEventListener("click", () => {
                if(modalConfirm) modalConfirm.classList.add("activo");
            });
        }

        if (document.getElementById("btnVolverCancelar")) {
            document.getElementById("btnVolverCancelar").addEventListener("click", () => {
                if(modalConfirm) modalConfirm.classList.remove("activo");
            });
        }

        if (document.getElementById("btnConfirmarCancelacion")) {
            document.getElementById("btnConfirmarCancelacion").addEventListener("click", function() {
                const btn = this;
                if (!idReservaActual) {
                    window.ccAlert('Abre primero los detalles de la reserva que deseas cancelar.');
                    return;
                }
                btn.innerHTML = '<i class="bi bi-hourglass-split"></i> Cancelando...';
                btn.disabled = true;

                fetch(`/api/cancelar-reserva/${idReservaActual}/`, {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: {
                        'X-CSRFToken': getCookie('csrftoken'),
                        'Content-Type': 'application/json',
                        'X-Session-Scope': 'cliente'
                    }
                })
                .then(async res => {
                    const text = await res.text();
                    let data;
                    try {
                        data = JSON.parse(text);
                    } catch (error) {
                        throw new Error(`El servidor respondió con error ${res.status}. Actualiza la página y verifica el estado antes de reintentar.`);
                    }
                    if (!res.ok) throw new Error(data.message || 'No se pudo cancelar la reserva.');
                    return data;
                })
                .then(data => {
                    if (data.success) {
                        if(modalConfirm) modalConfirm.classList.remove("activo");
                        
                        const badges = document.querySelectorAll("#mdEstadoBadge, #mdEstadoBadge2");
                        badges.forEach(b => {
                            b.textContent = 'Cancelada';
                            const parent = b.closest('.estado');
                            if (parent) {
                                parent.classList.remove('estado-confirmado', 'estado-pendiente', 'estado-validar');
                                parent.classList.add('estado-cancelada');
                            }
                        });

                        const btnAbrirCancelar = document.getElementById("btnAbrirCancelar");
                        if (btnAbrirCancelar) btnAbrirCancelar.classList.add("is-hidden");
                        setConfirmationMessage("Cancelada");

                        btn.innerHTML = '<i class="bi bi-check2-circle"></i> Sí, cancelar reserva';
                        btn.disabled = false;

                        if (!data.correo_enviado && window.ccAlert) {
                            window.ccAlert(data.message || 'La reserva se canceló, pero no se pudo enviar el correo de confirmación.')
                                .then(() => window.location.reload());
                        } else {
                            setTimeout(() => window.location.reload(), 2000);
                        }
                        
                    } else {
                        window.ccAlert(data.message || "Ocurrió un error al cancelar la reserva.");
                        btn.innerHTML = '<i class="bi bi-check2-circle"></i> Sí, cancelar reserva';
                        btn.disabled = false;
                    }
                })
                .catch(error => {
                    console.error("Error:", error);
                    window.ccAlert(error.message || "Error de red o servidor. Revisa la consola de Django.");
                    btn.innerHTML = '<i class="bi bi-check2-circle"></i> Sí, cancelar reserva';
                    btn.disabled = false;
                });
            });
        }

        if (document.getElementById("btnCerrarSuperior")) {
            document.getElementById("btnCerrarSuperior").addEventListener("click", cerrarModal);
        }
        if (document.getElementById("btnCerrarPrincipal")) {
            document.getElementById("btnCerrarPrincipal").addEventListener("click", cerrarModal);
        }
        
        modal.addEventListener("click", function(e) {
            if (e.target === modal) cerrarModal();
        });

        document.addEventListener("keydown", function(event) {
            if (event.key === "Escape" && modal.classList.contains("activo")) {
                cerrarModal();
            }
        });
    }

    const ICONOS = {
        calendar: '<rect width="18" height="18" x="3" y="4" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
        bed: '<path d="M2 20v-8a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v8"/><path d="M4 10V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v4"/><path d="M12 4v6M2 18h20"/>',
        users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
        user: '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
        mail: '<rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>',
        card: '<rect width="20" height="14" x="2" y="5" rx="2"/><path d="M2 10h20"/>',
        check: '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/>',
        star: '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>',
        eye: '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/>',
        doc: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4M10 9H8M16 13H8M16 17H8"/>',
        wifi: '<path d="M12 20h.01M2 8.82a15 15 0 0 1 20 0M5 12.86a10 10 0 0 1 14 0M8.5 16.43a5 5 0 0 1 7 0"/>',
        restaurante: '<path d="M3 2v7a2 2 0 0 0 2 2h4a2 2 0 0 0 2-2V2M7 2v20"/><path d="M21 15V2a5 5 0 0 0-5 5v6a2 2 0 0 0 2 2h3Zm0 0v7"/>',
        piscina: '<path d="M2 6c.6.5 1.2 1 2.5 1C7 7 7 5 9.5 5c2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1M2 12c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1M2 18c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1"/>',
        defecto: '<path d="M20 6 9 17l-5-5"/>'
    };

    const PALABRAS = [["piscina", "piscina"], ["restaur", "restaurante"], ["wifi", "wifi"], ["wi-fi", "wifi"]];

    function iconoPorNombre(nombre) {
        const n = (nombre || "").toLowerCase();
        for (const [clave, icono] of PALABRAS) {
            if (n.includes(clave)) return icono;
        }
        return "defecto";
    }

    function dibujar(el, nombre) {
        el.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' + (ICONOS[nombre] || ICONOS.defecto) + '</svg>';
    }

    document.querySelectorAll("[data-icon]").forEach(el => dibujar(el, el.dataset.icon));
    document.querySelectorAll("[data-servicio-icono]").forEach(el => dibujar(el, iconoPorNombre(el.dataset.servicioIcono)));
});
