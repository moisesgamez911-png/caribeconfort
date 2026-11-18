document.addEventListener("DOMContentLoaded", function () {

    const modalProximasReservas = document.getElementById('modalProximasReservas');
    const abrirProximasReservas = document.getElementById('abrirProximasReservas');
    const cerrarProximasReservas = document.getElementById('cerrarProximasReservas');
    if (modalProximasReservas) {
        if (abrirProximasReservas) {
            abrirProximasReservas.addEventListener('click', function () {
                modalProximasReservas.showModal();
            });
        }
        if (cerrarProximasReservas) {
            cerrarProximasReservas.addEventListener('click', function () {
                modalProximasReservas.close();
            });
        }
        modalProximasReservas.addEventListener('click', function (event) {
            if (event.target === modalProximasReservas) modalProximasReservas.close();
        });
    }

    const botonesOcupacion = document.querySelectorAll('.btn-ocupacion');
    const barrasOcupacion = document.querySelectorAll('.bar-dinamica');

    if (botonesOcupacion.length > 0 && barrasOcupacion.length > 0) {
        botonesOcupacion.forEach(boton => {
            boton.addEventListener('click', function() {
                botonesOcupacion.forEach(b => b.classList.remove('active'));
                this.classList.add('active');

                const tipo = this.getAttribute('data-tipo');

                barrasOcupacion.forEach(barra => {
                    const valor = barra.getAttribute('data-' + tipo);
                    if (valor !== null) {
                        barra.style.height = valor + '%';
                    }
                });
            });
        });
    }

    const modalNotif = document.getElementById('modalNotificacion');
    const btnNotifClose = document.getElementById('btnNotifClose');

    function mostrarNotificacion(titulo, mensaje, esExito) {
        if (!modalNotif) return;

        const icon = document.getElementById('notifIcon');
        document.getElementById('notifTitle').textContent = titulo;
        document.getElementById('notifMessage').textContent = mensaje;

        if (esExito) {
            icon.className = 'notif-icon success';
            icon.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>`;
        } else {
            icon.className = 'notif-icon error';
            icon.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`;
        }

        modalNotif.classList.add('activo');
    }

    if (btnNotifClose) {
        btnNotifClose.addEventListener('click', function() {
            modalNotif.classList.remove('activo');
            location.reload(); 
        });
    }

    const modalReserva = document.getElementById('modalReservaAdmin');
    if (modalReserva) {
        const cerrarBtns = [
            document.getElementById('cerrarModalAdmin'), 
            document.getElementById('cerrarModalAdminBtn')
        ];
        let currentReservaId = null;

        document.querySelectorAll('.btn-acciones-reserva').forEach(btn => {
            btn.addEventListener('click', function() {
                currentReservaId = this.dataset.id;
                
                document.getElementById('modalReservaId').textContent = `CC-${String(currentReservaId).padStart(4, '0')}`;
                document.getElementById('modalCliente').textContent = this.dataset.cliente;
                document.getElementById('modalEmail').textContent = this.dataset.email;
                document.getElementById('modalTelefono').textContent = this.dataset.telefono;
                document.getElementById('modalFechas').textContent = `${this.dataset.entrada} - ${this.dataset.salida}`;
                document.getElementById('modalHabitacion').textContent = this.dataset.habitacion;
                document.getElementById('modalTotal').textContent = this.dataset.total;
                
                const modalEstado = document.getElementById('modalEstado');
                modalEstado.textContent = this.dataset.estado;
                modalEstado.className = `badge-estado ${this.dataset.claseEstado}`;

                const btnAprobar = document.getElementById('btnAprobarReserva');
                const btnRechazar = document.getElementById('btnRechazarReserva');
                
                if (this.dataset.estado === 'Pagada - Por validar') {
                    btnAprobar.style.display = 'inline-block';
                    btnRechazar.style.display = 'inline-block';
                } else {
                    btnAprobar.style.display = 'none';
                    btnRechazar.style.display = 'none';
                }

                modalReserva.classList.add('activo');
            });
        });

        cerrarBtns.forEach(btn => {
            if(btn) btn.addEventListener('click', () => modalReserva.classList.remove('activo'));
        });

        modalReserva.addEventListener('click', function(e) {
            if (e.target === modalReserva) modalReserva.classList.remove('activo');
        });

        async function enviarAccionReserva(accion) {
            if (!currentReservaId) return;
            
            const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
            const url = `/gestionar-reserva/${currentReservaId}/`;
            
            const formData = new FormData();
            formData.append('accion', accion);
            formData.append('csrfmiddlewaretoken', csrfToken);

            try {
                const response = await fetch(url, {
                    method: 'POST',
                    body: formData,
                    headers: { 'X-Requested-With': 'XMLHttpRequest' }
                });
                
                if (!response.ok) throw new Error(`Error del servidor: ${response.status}`);
                
                const data = await response.json();
                
                if (data.success) {
                    modalReserva.classList.remove('activo');
                    let titulo = accion === 'aprobar' ? '¡Reserva Aprobada!' : '¡Reserva Rechazada!';
                    mostrarNotificacion(titulo, data.message, true);
                } else {
                    mostrarNotificacion('Atención', data.message, false);
                }
            } catch (error) {
                console.error("Detalle del error:", error);
                mostrarNotificacion('Error', 'No se pudo procesar la solicitud. Intenta de nuevo.', false);
            }
        }

        const btnAprobar = document.getElementById('btnAprobarReserva');
        const btnRechazar = document.getElementById('btnRechazarReserva');
        
        if (btnAprobar) btnAprobar.addEventListener('click', () => enviarAccionReserva('aprobar'));
        if (btnRechazar) btnRechazar.addEventListener('click', () => enviarAccionReserva('rechazar'));
    }
});