document.addEventListener("DOMContentLoaded", function () {
    
    const btnUser = document.getElementById("btnUser");
    const userMenu = document.getElementById("userMenu");
    if (btnUser && userMenu) {
        btnUser.addEventListener("click", function (e) {
            e.preventDefault();
            e.stopPropagation();
            userMenu.classList.toggle("abierto");
        });
        document.addEventListener("click", function (e) {
            if (!userMenu.contains(e.target) && !btnUser.contains(e.target)) {
                userMenu.classList.remove("abierto");
            }
        });
    }

    const modalPlan = document.getElementById('miModalPlan');
    const btnCerrarPlan = document.getElementById('btnCerrarModalPlan');
    const btnCancelarPlan = document.getElementById('btnCancelarModalPlan');
    const btnAbrirModal = document.querySelectorAll('.btn-abrir-modal-plan');
    
    const inPlanId = document.getElementById('inPlanId');
    const inPlanEntrada = document.getElementById('inPlanEntrada');
    const inPlanSalida = document.getElementById('inPlanSalida');
    const inPlanAdultos = document.getElementById('inPlanAdultos');
    const inPlanNinos = document.getElementById('inPlanNinos');
    const inPlanCodigoConvenio = document.getElementById('inPlanCodigoConvenio');
    
    const txtPlanEntrada = document.getElementById('planEntrada');
    const txtPlanSalida = document.getElementById('txtPlanSalida');
    const selectAdultos = document.getElementById('planAdultos');
    const selectNinos = document.getElementById('planNinos');
    const selectTipoHabitacion = document.getElementById('planTipoHabitacion');
    const inputCantidadHabitaciones = document.getElementById('planCantidadHabitaciones');
    const textoDisponibilidad = document.getElementById('planDisponibilidadHabitaciones');
    const txtTotal = document.getElementById('txtTotal');
    const btnConfirmarPlan = document.getElementById('btnConfirmarPlan');

    let planActual = null;
    let solicitudDisponibilidad = 0;

    const modalAlerta = document.getElementById('modalAlertaFecha');
    const btnCerrarAlerta = document.getElementById('btnCerrarAlertaFecha');

    function abrirAlertaFecha(mensaje) {
        if (modalAlerta) {
            const titulo = document.getElementById('tituloAlerta');
            const textoParrafo = document.getElementById('mensajeAlerta');
            
            if (titulo) titulo.textContent = 'Atención';
            if (textoParrafo) textoParrafo.textContent = mensaje || "Ocurrió un error inesperado.";
            
            modalAlerta.classList.add('activo');
        } else {
            window.ccAlert(mensaje);
        }
    }

    if (btnCerrarAlerta) {
        btnCerrarAlerta.addEventListener('click', function() {
            modalAlerta.classList.remove('activo');
        });
    }

    if (modalAlerta) {
        modalAlerta.addEventListener('click', function(e) {
            if (e.target === modalAlerta) {
                modalAlerta.classList.remove('activo');
            }
        });
    }

    btnAbrirModal.forEach(btn => {
        btn.addEventListener('click', function() {
            planActual = {
                id: this.dataset.id,
                nombre: this.dataset.nombre,
                duracion: parseInt(this.dataset.duracion) || 1,
                maxAdultos: parseInt(this.dataset.maxAdultos) || 2,
                maxNinos: parseInt(this.dataset.maxNinos) || 2,
                modoPrecio: this.dataset.modoPrecio || 'manual',
                precio: parseFloat(this.dataset.precio) || 0,
                tipoHabitacion: this.dataset.tipoHabitacion,
                cantidadHabitaciones: parseInt(this.dataset.cantidadHabitaciones) || 1
            };

            inPlanId.value = planActual.id;
            if (inPlanCodigoConvenio) inPlanCodigoConvenio.value = '';
            selectTipoHabitacion.value = planActual.tipoHabitacion;
            selectTipoHabitacion.disabled = true;
            inputCantidadHabitaciones.value = String(planActual.cantidadHabitaciones);
            inputCantidadHabitaciones.readOnly = true;
            inputCantidadHabitaciones.removeAttribute('max');
            delete inputCantidadHabitaciones.dataset.disponibles;
            textoDisponibilidad.textContent = 'Selecciona tipo y fechas para consultar disponibilidad.';
            
            txtPlanEntrada.value = '';
            txtPlanSalida.textContent = '--';
            inPlanSalida.value = '';
            txtTotal.textContent = '$ 0';

            selectAdultos.innerHTML = '';
            for (let i = 1; i <= planActual.maxAdultos; i++) {
                selectAdultos.innerHTML += `<option value="${i}">${i} adulto${i > 1 ? 's' : ''}</option>`;
            }

            selectNinos.innerHTML = '<option value="0">0 niños</option>';
            for (let i = 1; i <= planActual.maxNinos; i++) {
                selectNinos.innerHTML += `<option value="${i}">${i} niño${i > 1 ? 's' : ''}</option>`;
            }
            selectNinos.value = '1';

            actualizarTotal();

            if (modalPlan) modalPlan.style.display = 'flex';
        });
    });

    if (txtPlanEntrada) {
        txtPlanEntrada.addEventListener('change', function() {
            if (!this.value) {
                txtPlanSalida.textContent = '--';
                inPlanSalida.value = '';
                actualizarTotal();
                consultarDisponibilidad().catch(error => {
                    textoDisponibilidad.textContent = error.message;
                });
                return;
            }

            const fechaEntrada = new Date(this.value + 'T00:00:00');
            const fechaSalida = new Date(fechaEntrada);
            fechaSalida.setDate(fechaSalida.getDate() + (planActual ? planActual.duracion : 1));

            const opciones = { day: '2-digit', month: '2-digit', year: 'numeric' };
            txtPlanSalida.textContent = fechaSalida.toLocaleDateString('es-ES', opciones);
            
            const yyyy = fechaSalida.getFullYear();
            const mm = String(fechaSalida.getMonth() + 1).padStart(2, '0');
            const dd = String(fechaSalida.getDate()).padStart(2, '0');
            
            inPlanEntrada.value = this.value;
            inPlanSalida.value = `${yyyy}-${mm}-${dd}`;
            consultarDisponibilidad().catch(error => {
                textoDisponibilidad.textContent = error.message;
            });
        });
    }

    function actualizarTotal() {
        if (!planActual) return;
        let total = planActual.precio;
        if (planActual.modoPrecio === 'habitacion') {
            const opcionTipo = selectTipoHabitacion.selectedOptions[0];
            const tarifa = opcionTipo ? Number(opcionTipo.dataset.tarifa) : 0;
            const cantidad = Number(inputCantidadHabitaciones.value) || 0;
            total = tarifa * planActual.duracion * cantidad;
        }
        txtTotal.textContent = new Intl.NumberFormat('es-CO', {
            style: 'currency', currency: 'COP', maximumFractionDigits: 0
        }).format(total);
    }

    async function consultarDisponibilidad() {
        const solicitudActual = ++solicitudDisponibilidad;
        const tipoId = selectTipoHabitacion.value;
        const entrada = inPlanEntrada.value;
        const salida = inPlanSalida.value;
        if (!tipoId || !entrada || !salida) {
            delete inputCantidadHabitaciones.dataset.disponibles;
            inputCantidadHabitaciones.removeAttribute('max');
            textoDisponibilidad.textContent = 'Selecciona tipo y fechas para consultar disponibilidad.';
            actualizarTotal();
            return null;
        }

        textoDisponibilidad.textContent = 'Consultando disponibilidad...';
        const parametros = new URLSearchParams({ tipo_id: tipoId, entrada, salida });
        const respuesta = await fetch(`/api/disponibilidad-plan/?${parametros.toString()}`);
        const datos = await respuesta.json();
        if (!respuesta.ok || !datos.ok) {
            throw new Error(datos.error || 'No se pudo consultar la disponibilidad.');
        }
        if (solicitudActual !== solicitudDisponibilidad) return null;

        const disponibles = Number(datos.disponibles);
        inputCantidadHabitaciones.dataset.disponibles = String(disponibles);
        inputCantidadHabitaciones.max = String(disponibles);
        textoDisponibilidad.textContent = disponibles === 1
            ? 'Hay 1 habitación disponible para estas fechas.'
            : `Hay ${disponibles} habitaciones disponibles para estas fechas.`;
        actualizarTotal();
        return disponibles;
    }

    if (selectTipoHabitacion) {
        selectTipoHabitacion.addEventListener('change', function() {
            actualizarTotal();
            consultarDisponibilidad().catch(error => {
                textoDisponibilidad.textContent = error.message;
            });
        });
    }
    if (inputCantidadHabitaciones) {
        inputCantidadHabitaciones.addEventListener('input', actualizarTotal);
    }
    if (selectAdultos) selectAdultos.addEventListener('change', actualizarTotal);
    if (selectNinos) selectNinos.addEventListener('change', actualizarTotal);

    function cerrarModalReserva() {
        if (modalPlan) modalPlan.style.display = 'none';
    }

    if (btnCerrarPlan) btnCerrarPlan.addEventListener('click', cerrarModalReserva);
    if (btnCancelarPlan) btnCancelarPlan.addEventListener('click', cerrarModalReserva);

    if (btnConfirmarPlan) {
        btnConfirmarPlan.addEventListener('click', async function(e) {
            e.preventDefault();
            if (this.disabled) return;

            if (!txtPlanEntrada.value) {
                abrirAlertaFecha("Debes seleccionar la fecha de entrada para poder reservar este plan.");
                return;
            }
            if (txtPlanEntrada.value < txtPlanEntrada.min) {
                abrirAlertaFecha("La fecha de entrada no puede estar en el pasado.");
                return;
            }

            if (!inPlanSalida.value) {
                const fechaEntrada = new Date(txtPlanEntrada.value + 'T00:00:00');
                const fechaSalida = new Date(fechaEntrada);
                fechaSalida.setDate(fechaSalida.getDate() + (planActual ? planActual.duracion : 1));
                const yyyy = fechaSalida.getFullYear();
                const mm = String(fechaSalida.getMonth() + 1).padStart(2, '0');
                const dd = String(fechaSalida.getDate()).padStart(2, '0');
                inPlanSalida.value = `${yyyy}-${mm}-${dd}`;
            }

            if (!selectTipoHabitacion.value) {
                abrirAlertaFecha('Selecciona el tipo de habitación para continuar.');
                return;
            }
            const cantidadHabitaciones = Number(inputCantidadHabitaciones.value);
            if (!Number.isInteger(cantidadHabitaciones) || cantidadHabitaciones < 1) {
                abrirAlertaFecha('Indica una cantidad válida de habitaciones.');
                return;
            }
            const tipoSeleccionado = selectTipoHabitacion.selectedOptions[0];
            const huespedes = Number(selectAdultos.value) + Number(selectNinos.value);
            if (huespedes > Number(tipoSeleccionado.dataset.capacidad) * cantidadHabitaciones) {
                abrirAlertaFecha('La cantidad de habitaciones no tiene capacidad para todos los huéspedes.');
                return;
            }
            const textoOriginal = this.innerHTML;
            if (
                cantidadHabitaciones !== planActual.cantidadHabitaciones
                || selectTipoHabitacion.value !== planActual.tipoHabitacion
            ) {
                abrirAlertaFecha('La composición de habitaciones está definida por el plan. Contacta al hotel si necesitas un cambio logístico.');
                return;
            }
            this.disabled = true;
            let disponibles;
            try {
                disponibles = await consultarDisponibilidad();
            } catch (error) {
                abrirAlertaFecha(error.message || 'No se pudo consultar la disponibilidad.');
                this.disabled = false;
                return;
            }
            if (disponibles === null) {
                abrirAlertaFecha('La disponibilidad cambió. Vuelve a consultar las fechas y el tipo de habitación.');
                this.disabled = false;
                return;
            }
            if (cantidadHabitaciones > disponibles) {
                abrirAlertaFecha(disponibles === 0
                    ? 'No hay habitaciones de ese tipo disponibles para las fechas elegidas.'
                    : `Solo hay ${disponibles} habitaciones disponibles para las fechas elegidas.`);
                this.disabled = false;
                return;
            }

            inPlanAdultos.value = selectAdultos.value;
            inPlanNinos.value = selectNinos.value;

            this.innerHTML = 'Procesando...';

            const formData = new FormData();
            formData.append('plan_id', inPlanId.value);
            formData.append('entrada', txtPlanEntrada.value);
            formData.append('salida', inPlanSalida.value);
            formData.append('adultos', inPlanAdultos.value);
            formData.append('ninos', inPlanNinos.value);
            formData.append('tipo_habitacion', selectTipoHabitacion.value);
            formData.append('cantidad_habitaciones', String(cantidadHabitaciones));
            if (inPlanCodigoConvenio && inPlanCodigoConvenio.value.trim()) {
                formData.append('codigo_convenio', inPlanCodigoConvenio.value.trim());
            }
            
            const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
            if (csrfToken) {
                formData.append('csrfmiddlewaretoken', csrfToken);
            }

            fetch('/reservar-plan/crear/', {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            })
            .then(async res => {
                const text = await res.text();
                let data;
                
                try {
                    data = JSON.parse(text);
                } catch (err) {
                    console.error("El servidor devolvió HTML en lugar de JSON:", text);
                    throw new Error("Error en el servidor. Revisa la terminal de Django o vuelve a iniciar sesión.");
                }

                if (!res.ok) {
                    throw new Error(data.error || `Error del servidor (${res.status})`);
                }
                return data;
            })
            .then(data => {
                if (data.ok) {
                    window.location.href = `/pagar-reserva/${data.reserva_id}/`;
                } else {
                    abrirAlertaFecha(data.error || "Ocurrió un error al procesar la reserva.");
                    this.innerHTML = textoOriginal;
                    this.disabled = false;
                }
            })
            .catch(error => {
                console.error("Error capturado:", error);
                abrirAlertaFecha(error.message || "Error de conexión. Inténtalo de nuevo.");
                this.innerHTML = textoOriginal;
                this.disabled = false;
            });
        });
    }
});