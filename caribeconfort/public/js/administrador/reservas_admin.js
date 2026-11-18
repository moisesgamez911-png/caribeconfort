document.addEventListener('DOMContentLoaded', function () {
    var modalCheckin = document.getElementById('modalCheckinConfirm');
    var modalValidar = document.getElementById('modalValidar');
    var modalCheckOut = document.getElementById('modalCheckOut');
    var modalPago = document.getElementById('modalPagoReserva');
    var modalNuevaReserva = document.getElementById('modalNuevaReserva');
    var modalReservaExitosa = document.getElementById('modalReservaExitosa');
    var modalProximasReservas = document.getElementById('modalProximasReservas');
    var modalModificarReserva = document.getElementById('modalModificarReserva');
    var tokenInput = document.querySelector('[name=csrfmiddlewaretoken]');
    var csrfToken = tokenInput ? tokenInput.value : '';

    if (modalProximasReservas) {
        var btnAbrirProximas = document.getElementById('abrirProximasReservas');
        var btnCerrarProximas = document.getElementById('cerrarProximasReservas');
        if (btnAbrirProximas) btnAbrirProximas.addEventListener('click', function () {
            modalProximasReservas.showModal();
        });
        if (btnCerrarProximas) btnCerrarProximas.addEventListener('click', function () {
            modalProximasReservas.close();
        });
        modalProximasReservas.addEventListener('click', function (event) {
            if (event.target === modalProximasReservas) modalProximasReservas.close();
        });
    }

    function cerrarModal(modal) {
        if (modal) modal.classList.remove('activo');
    }

    function configurarCierre(modal, ids) {
        if (!modal) return;
        ids.forEach(function (id) {
            var boton = document.getElementById(id);
            if (boton) boton.addEventListener('click', function () { cerrarModal(modal); });
        });
        modal.addEventListener('click', function (event) {
            if (event.target === modal) cerrarModal(modal);
        });
    }

    if (modalNuevaReserva) {
        var btnNuevaReserva = document.getElementById('btnNuevaReserva');
        if (btnNuevaReserva) btnNuevaReserva.addEventListener('click', function () {
            modalNuevaReserva.classList.add('activo');
        });
        configurarCierre(modalNuevaReserva, ['cerrarModalNueva', 'cancelarModalNueva']);

        var formNuevaReserva = modalNuevaReserva.querySelector('form');
        if (formNuevaReserva) {
            var errorNuevaReserva = document.getElementById('errorNuevaReserva');
            formNuevaReserva.addEventListener('submit', function (event) {
                event.preventDefault();
                if (errorNuevaReserva) errorNuevaReserva.textContent = '';
                var submitButton = formNuevaReserva.querySelector('[type="submit"]');
                if (submitButton) submitButton.disabled = true;

                fetch(formNuevaReserva.action, {
                    method: 'POST',
                    body: new FormData(formNuevaReserva),
                    headers: { 'X-Requested-With': 'XMLHttpRequest' }
                })
                    .then(function (response) {
                        return response.json().then(function (data) {
                            if (!response.ok || !data.ok) {
                                throw new Error(data.error || data.message || 'No se pudo guardar la reserva.');
                            }
                            return data;
                        });
                    })
                    .then(function (data) {
                        cerrarModal(modalNuevaReserva);
                        document.getElementById('mensajeReservaExitosa').textContent = data.message;
                        if (modalReservaExitosa) modalReservaExitosa.classList.add('activo');
                    })
                    .catch(function (error) {
                        if (errorNuevaReserva) {
                            errorNuevaReserva.textContent = error.message || 'No se pudo conectar con el servidor. Inténtalo nuevamente.';
                        }
                    })
                    .finally(function () {
                        if (submitButton) submitButton.disabled = false;
                    });
            });
        }

        var tipoHabitacion = document.getElementById('nuevoTipoHabitacion');
        var selectHabitacion = document.getElementById('nuevaHabitacion');
        var cantidadHuespedes = document.getElementById('cantidadAcompanantes');
        if (tipoHabitacion && selectHabitacion && cantidadHuespedes) {
            var opcionInicial = selectHabitacion.options[0];
            function filtrarHabitaciones() {
                var tipoSeleccionado = tipoHabitacion.value;
                var cantidadDisponibles = 0;
                Array.prototype.forEach.call(selectHabitacion.options, function (opcion, indice) {
                    if (indice === 0) return;
                    var coincide = Boolean(tipoSeleccionado) && opcion.dataset.tipoId === tipoSeleccionado;
                    opcion.hidden = !coincide;
                    opcion.disabled = !coincide;
                    if (coincide) cantidadDisponibles += 1;
                });
                selectHabitacion.value = '';
                selectHabitacion.disabled = !tipoSeleccionado || cantidadDisponibles === 0;
                if (opcionInicial) {
                    opcionInicial.textContent = !tipoSeleccionado
                        ? 'Primero selecciona un tipo'
                        : cantidadDisponibles
                            ? 'Selecciona una habitación'
                            : 'No hay habitaciones disponibles para este tipo';
                }
                cantidadHuespedes.value = '1';
                cantidadHuespedes.max = '';
                renderizarAcompanantes();
            }

            function renderizarAcompanantes() {
                var lista = document.getElementById('listaAcompanantes');
                var cantidad = Math.max(1, parseInt(cantidadHuespedes.value, 10) || 1);
                var requeridos = cantidad - 1;
                lista.replaceChildren();
                if (!requeridos) {
                    var vacio = document.createElement('p');
                    vacio.className = 'rv-acompanantes-empty';
                    vacio.textContent = 'No se requieren acompañantes adicionales.';
                    lista.appendChild(vacio);
                    return;
                }
                for (var indice = 0; indice < requeridos; indice += 1) {
                    var fila = document.createElement('div');
                    fila.className = 'rv-acompanante-row';
                    fila.innerHTML =
                        '<span class="rv-acompanante-title">Acompañante ' + (indice + 1) + '</span>' +
                        '<label>Nombre completo<input name="acompanante_nombre[]" maxlength="200" required></label>' +
                        '<label>Documento<input name="acompanante_documento[]" maxlength="50" required></label>' +
                        '<label>Parentesco<input name="acompanante_parentesco[]" maxlength="50"></label>';
                    lista.appendChild(fila);
                }
            }

            tipoHabitacion.addEventListener('change', filtrarHabitaciones);
            cantidadHuespedes.addEventListener('input', renderizarAcompanantes);
            selectHabitacion.addEventListener('change', function () {
                var opcion = selectHabitacion.options[selectHabitacion.selectedIndex];
                var capacidad = opcion ? Number(opcion.dataset.capacidad) : 0;
                var campoMonto = document.getElementById('nuevoMontoPagado');
                if (opcion && opcion.dataset.precio && campoMonto) {
                    campoMonto.value = opcion.dataset.precio;
                }
                cantidadHuespedes.max = capacidad || '';
                if (capacidad && Number(cantidadHuespedes.value) > capacidad) {
                    cantidadHuespedes.value = capacidad;
                }
                renderizarAcompanantes();
            });
            filtrarHabitaciones();
        }

        var montoPagado = document.getElementById('nuevoMontoPagado');
        var metodoPago = document.getElementById('nuevoMetodoPago');
        if (montoPagado && metodoPago) {
            function actualizarMetodoPago() {
                var requierePago = Number(montoPagado.value) > 0;
                metodoPago.disabled = !requierePago;
                metodoPago.required = requierePago;
                if (!requierePago) metodoPago.value = '';
            }
            montoPagado.addEventListener('input', actualizarMetodoPago);
            actualizarMetodoPago();
        }
    }

    var btnCerrarReservaExitosa = document.getElementById('cerrarReservaExitosa');
    if (btnCerrarReservaExitosa && modalReservaExitosa) {
        btnCerrarReservaExitosa.addEventListener('click', function () {
            cerrarModal(modalReservaExitosa);
            window.location.reload();
        });
    }

    function saldoDeBoton(boton) {
        var saldo = Number(boton.dataset.saldo);
        return Number.isFinite(saldo) ? Math.max(0, saldo) : 0;
    }

    if (modalCheckin) {
        document.querySelectorAll('.btn-checkin').forEach(function (boton) {
            boton.addEventListener('click', function () {
                document.getElementById('ckId').textContent = String(boton.dataset.id).padStart(4, '0');
                document.getElementById('ckNombre').textContent = boton.dataset.nombre;
                document.getElementById('ckDocumento').textContent = boton.dataset.documento;
                document.getElementById('ckHab').textContent = boton.dataset.hab;
                document.getElementById('ckEntrada').textContent = boton.dataset.entrada;
                document.getElementById('ckSalida').textContent = boton.dataset.salida;
                document.getElementById('ckEstado').textContent = boton.dataset.estado;
                document.getElementById('btnSiCheckin').href = '/adminreserva/checkin/' + boton.dataset.id;
                modalCheckin.classList.add('activo');
            });
        });
        configurarCierre(modalCheckin, ['btnCerrarCheckin', 'btnNoCheckin']);
    }

    if (modalValidar) {
        document.querySelectorAll('.btn-abrir-validacion').forEach(function (boton) {
            boton.addEventListener('click', function () {
                modalValidar.dataset.reservaId = boton.dataset.id;
                document.getElementById('valNombre').textContent = boton.dataset.nombre;
                document.getElementById('valDocumento').textContent = boton.dataset.documento;
                document.getElementById('valCorreo').textContent = boton.dataset.correo;
                document.getElementById('valTelefono').textContent = boton.dataset.telefono;
                document.getElementById('valHab').textContent = boton.dataset.hab;
                document.getElementById('valEntrada').textContent = boton.dataset.entrada;
                document.getElementById('valSalida').textContent = boton.dataset.salida;
                document.getElementById('valTotal').textContent = boton.dataset.total;
                modalValidar.classList.add('activo');
            });
        });
        configurarCierre(modalValidar, ['btnCerrarModal', 'btnCancelarValidacion']);

        function enviarAccion(accion) {
            var reservaId = modalValidar.dataset.reservaId;
            if (!reservaId || !csrfToken) {
                window.ccAlert('No se pudo validar la sesión o el token de seguridad. Recarga la página e inténtalo nuevamente.');
                return;
            }
            fetch('/gestionar-reserva/' + reservaId + '/', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken,
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: new URLSearchParams({ accion: accion }),
            })
                .then(function (response) {
                    return response.json().then(function (data) {
                        if (!response.ok) throw new Error(data.message || 'No se pudo procesar la reserva.');
                        return data;
                    });
                })
                .then(function (data) {
                    return window.ccAlert(data.message || 'Reserva actualizada.').then(function () {
                        if (data.success) window.location.reload();
                    });
                })
                .catch(function (error) { window.ccAlert(error.message); });
        }

        var btnConfirmar = document.getElementById('btnConfirmarValidacion');
        if (btnConfirmar) btnConfirmar.addEventListener('click', function () { enviarAccion('aprobar'); });
        var btnRechazar = document.getElementById('btnRechazarValidacion');
        if (btnRechazar) btnRechazar.addEventListener('click', function () {
            window.ccConfirm('¿Seguro que quieres rechazar esta reserva?').then(function (confirmado) {
                if (confirmado) enviarAccion('rechazar');
            });
        });
    }

    if (modalCheckOut) {
        document.querySelectorAll('.btn-checkout').forEach(function (boton) {
            boton.addEventListener('click', function () {
                var saldo = saldoDeBoton(boton);
                document.getElementById('checkoutHuesped').textContent = boton.dataset.nombre;
                document.getElementById('checkoutSaldo').textContent = '$ ' + saldo.toLocaleString('es-CO', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                document.getElementById('checkoutValor').value = saldo.toFixed(2);
                document.querySelector('[data-checkout-payment]').hidden = saldo <= 0;
                document.getElementById('checkoutMetodo').required = saldo > 0;
                document.getElementById('formCheckOut').action = '/adminreserva/checkout/' + boton.dataset.id + '/';
                modalCheckOut.classList.add('activo');
            });
        });
        configurarCierre(modalCheckOut, ['btnCerrarCheckOut', 'btnCancelarCheckOut']);
    }

    if (modalPago) {
        document.querySelectorAll('.btn-pago-reserva').forEach(function (boton) {
            boton.addEventListener('click', function () {
                var saldo = saldoDeBoton(boton);
                var campoMonto = document.getElementById('pagoReservaValor');
                document.getElementById('pagoReservaHuesped').textContent = boton.dataset.nombre;
                document.getElementById('pagoReservaSaldo').textContent = '$ ' + saldo.toLocaleString('es-CO', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                campoMonto.max = saldo.toFixed(2);
                campoMonto.value = saldo.toFixed(2);
                document.getElementById('formPagoReserva').action = '/adminreserva/pago/' + boton.dataset.id + '/';
                modalPago.classList.add('activo');
            });
        });
        configurarCierre(modalPago, ['btnCerrarPagoReserva', 'btnCancelarPagoReserva']);
    }

    if (modalModificarReserva) {
        var formModificar = document.getElementById('formModificarReserva');
        var errorModificar = document.getElementById('errorModificarReserva');
        var seccionReembolso = document.getElementById('seccionReembolso');
        var btnProcesarReembolso = document.getElementById('btnProcesarReembolso');

        document.querySelectorAll('.btn-modificar-reserva').forEach(function (boton) {
            boton.addEventListener('click', function () {
                modalModificarReserva.dataset.reservaId = boton.dataset.id;
                modalModificarReserva.dataset.reembolso = '';
                formModificar.action = '/adminreserva/' + boton.dataset.id + '/modificar';
                document.getElementById('modificarFechaEntrada').value = boton.dataset.entrada;
                document.getElementById('modificarFechaSalida').value = boton.dataset.salida;
                document.getElementById('modificarReservaMensaje').textContent = 'Actualiza la entrada y salida de la reserva.';
                errorModificar.textContent = '';
                seccionReembolso.hidden = true;
                btnProcesarReembolso.hidden = true;
                modalModificarReserva.classList.add('activo');
            });
        });
        configurarCierre(modalModificarReserva, ['cerrarModalModificar', 'cancelarModalModificar']);

        formModificar.addEventListener('submit', function (event) {
            event.preventDefault();
            errorModificar.textContent = '';
            var botonGuardar = document.getElementById('btnGuardarModificacion');
            botonGuardar.disabled = true;
            fetch(formModificar.action, {
                method: 'POST',
                headers: { 'X-CSRFToken': csrfToken },
                body: new FormData(formModificar)
            }).then(function (response) {
                return response.json().then(function (data) {
                    if (!response.ok && !data.success) {
                        throw new Error(data.message || 'No se pudo modificar la reserva.');
                    }
                    return data;
                });
            }).then(function (data) {
                if (data.reembolso_pendiente) {
                    modalModificarReserva.dataset.reembolso = data.reembolso;
                    seccionReembolso.hidden = false;
                    btnProcesarReembolso.hidden = false;
                    btnProcesarReembolso.textContent = 'Procesar reembolso de $' +
                        Number(data.reembolso).toLocaleString('es-CO');
                    document.getElementById('modificarReservaMensaje').textContent =
                        'Nuevo total: $' + Number(data.nuevo_total).toLocaleString('es-CO');
                    if (!data.correo_enviado) errorModificar.textContent = data.message;
                    return;
                }
                return window.ccAlert(data.message || 'Reserva modificada.').then(function () {
                    window.location.reload();
                });
            }).catch(function (error) {
                errorModificar.textContent = error.message || 'No se pudo conectar con el servidor.';
            }).finally(function () {
                botonGuardar.disabled = false;
            });
        });

        btnProcesarReembolso.addEventListener('click', function () {
            var reservaId = modalModificarReserva.dataset.reservaId;
            var monto = modalModificarReserva.dataset.reembolso;
            if (!reservaId || !monto || !csrfToken) {
                errorModificar.textContent = 'No se pudo preparar el reembolso. Recarga la página e inténtalo nuevamente.';
                return;
            }
            btnProcesarReembolso.disabled = true;
            fetch('/adminreserva/' + reservaId + '/reembolso', {
                method: 'POST',
                headers: { 'X-CSRFToken': csrfToken, 'Content-Type': 'application/x-www-form-urlencoded' },
                body: new URLSearchParams({
                    monto: monto,
                    metodo: document.getElementById('metodoReembolso').value
                })
            }).then(function (response) {
                return response.json().then(function (data) {
                    if (!response.ok || !data.success) throw new Error(data.message || 'No se pudo procesar el reembolso.');
                    return data;
                });
            }).then(function (data) {
                return window.ccAlert(data.message || 'Reembolso procesado.').then(function () {
                    window.location.reload();
                });
            }).catch(function (error) {
                errorModificar.textContent = error.message || 'No se pudo conectar con el servidor.';
            }).finally(function () {
                btnProcesarReembolso.disabled = false;
            });
        });
    }
});
