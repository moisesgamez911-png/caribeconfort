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
    const txtTotal = document.getElementById('txtTotal');
    const btnConfirmarPlan = document.getElementById('btnConfirmarPlan');

    let planActual = null;

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
                precio: parseFloat(this.dataset.precio),
                duracion: parseInt(this.dataset.duracion) || 1,
                maxAdultos: parseInt(this.dataset.maxAdultos) || 2,
                maxNinos: parseInt(this.dataset.maxNinos) || 2
            };

            inPlanId.value = planActual.id;
            if (inPlanCodigoConvenio) inPlanCodigoConvenio.value = '';
            
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
        });
    }

    function actualizarTotal() {
        if (!planActual) return;
        let total = planActual.precio;
        txtTotal.textContent = new Intl.NumberFormat('es-CO', {
            style: 'currency', currency: 'COP', maximumFractionDigits: 0
        }).format(total);
    }

    if (selectAdultos) selectAdultos.addEventListener('change', actualizarTotal);
    if (selectNinos) selectNinos.addEventListener('change', actualizarTotal);

    function cerrarModalReserva() {
        if (modalPlan) modalPlan.style.display = 'none';
    }

    if (btnCerrarPlan) btnCerrarPlan.addEventListener('click', cerrarModalReserva);
    if (btnCancelarPlan) btnCancelarPlan.addEventListener('click', cerrarModalReserva);

    if (btnConfirmarPlan) {
        btnConfirmarPlan.addEventListener('click', function(e) {
            e.preventDefault();

            if (!txtPlanEntrada.value) {
                abrirAlertaFecha("Debes seleccionar la fecha de entrada para poder reservar este plan.");
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

            inPlanAdultos.value = selectAdultos.value;
            inPlanNinos.value = selectNinos.value;

            const textoOriginal = this.innerHTML;
            this.innerHTML = 'Procesando...';
            this.disabled = true;

            const formData = new FormData();
            formData.append('plan_id', inPlanId.value);
            formData.append('entrada', txtPlanEntrada.value);
            formData.append('salida', inPlanSalida.value);
            formData.append('adultos', inPlanAdultos.value);
            formData.append('ninos', inPlanNinos.value);
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