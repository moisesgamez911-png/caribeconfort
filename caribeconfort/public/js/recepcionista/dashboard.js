document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-open-dialog]').forEach(function (button) {
        var dialog = document.getElementById(button.dataset.openDialog);
        if (dialog) button.addEventListener('click', function () { dialog.showModal(); });
    });

    document.querySelectorAll('[data-close-dialog]').forEach(function (button) {
        button.addEventListener('click', function () {
            var dialog = button.closest('dialog');
            if (dialog) dialog.close();
        });
    });

    document.querySelectorAll('.reception-dialog').forEach(function (dialog) {
        dialog.addEventListener('click', function (event) {
            if (event.target === dialog) dialog.close();
        });
    });

    var accionSelect = document.getElementById('accionPagoServicio');
    var pagoFields = document.querySelector('[data-pago-fields]');
    var servicioFields = document.querySelector('[data-servicio-fields]');
    if (accionSelect && pagoFields && servicioFields) {
        function actualizarCamposPagoServicio() {
            var esPago = accionSelect.value === 'pago';
            pagoFields.hidden = !esPago;
            servicioFields.hidden = esPago;
            pagoFields.querySelectorAll('input, select').forEach(function (field) {
                field.disabled = !esPago;
                field.required = esPago;
            });
            servicioFields.querySelectorAll('input, select').forEach(function (field) {
                field.disabled = esPago;
                field.required = !esPago;
            });
        }
        accionSelect.addEventListener('change', actualizarCamposPagoServicio);
        actualizarCamposPagoServicio();
    }

    var selectHabitacion = document.querySelector('#modalReserva [name="habitacion_id"]');
    var cantidadHuespedes = document.querySelector('#modalReserva [name="cantidad_huespedes"]');
    if (selectHabitacion && cantidadHuespedes) {
        var listaAcompanantes = document.getElementById('recepcionAcompanantes');
        var montoInicial = document.getElementById('recepcionMontoInicial');
        var metodoInicial = document.getElementById('recepcionMetodoInicial');

        function renderizarAcompanantes() {
            if (!listaAcompanantes) return;
            var cantidad = Math.max(1, parseInt(cantidadHuespedes.value, 10) || 1);
            listaAcompanantes.replaceChildren();
            for (var indice = 0; indice < cantidad - 1; indice += 1) {
                var nombre = document.createElement('label');
                nombre.textContent = 'Nombre completo';
                var nombreInput = document.createElement('input');
                nombreInput.name = 'acompanante_nombre[]';
                nombreInput.maxLength = 200;
                nombreInput.required = true;
                nombre.appendChild(nombreInput);

                var documento = document.createElement('label');
                documento.textContent = 'Documento';
                var documentoInput = document.createElement('input');
                documentoInput.name = 'acompanante_documento[]';
                documentoInput.maxLength = 50;
                documentoInput.required = true;
                documento.appendChild(documentoInput);

                var parentesco = document.createElement('label');
                parentesco.textContent = 'Parentesco';
                var parentescoInput = document.createElement('input');
                parentescoInput.name = 'acompanante_parentesco[]';
                parentescoInput.maxLength = 50;
                parentesco.appendChild(parentescoInput);

                listaAcompanantes.appendChild(nombre);
                listaAcompanantes.appendChild(documento);
                listaAcompanantes.appendChild(parentesco);
            }
        }

        selectHabitacion.addEventListener('change', function () {
            var opcion = selectHabitacion.options[selectHabitacion.selectedIndex];
            var capacidad = opcion ? Number(opcion.dataset.capacidad) : 0;
            cantidadHuespedes.max = capacidad || '';
            if (capacidad && Number(cantidadHuespedes.value) > capacidad) {
                cantidadHuespedes.value = capacidad;
            }
            if (montoInicial && opcion && opcion.dataset.precio) {
                montoInicial.value = opcion.dataset.precio;
                if (metodoInicial) {
                    metodoInicial.disabled = Number(montoInicial.value) <= 0;
                    metodoInicial.required = Number(montoInicial.value) > 0;
                }
            }
            renderizarAcompanantes();
        });
        cantidadHuespedes.addEventListener('input', renderizarAcompanantes);
        renderizarAcompanantes();

        if (montoInicial && metodoInicial) {
            montoInicial.addEventListener('input', function () {
                var requiereMetodo = Number(montoInicial.value) > 0;
                metodoInicial.disabled = !requiereMetodo;
                metodoInicial.required = requiereMetodo;
                if (!requiereMetodo) metodoInicial.value = '';
            });
        }
    }

    var checkoutDialog = document.getElementById('modalCheckout');
    if (checkoutDialog) {
        document.querySelectorAll('[data-open-checkout]').forEach(function (button) {
            button.addEventListener('click', function () {
                var saldo = Number(button.dataset.saldo);
                var tieneSaldo = saldo > 0;
                document.getElementById('checkoutGuest').textContent = button.dataset.nombre;
                document.getElementById('checkoutBalance').textContent = saldo.toLocaleString('es-CO', {
                    style: 'currency',
                    currency: 'COP',
                    minimumFractionDigits: 2
                });
                document.getElementById('checkoutAmount').value = tieneSaldo ? saldo.toFixed(2) : '';
                document.querySelector('[data-checkout-payment]').hidden = !tieneSaldo;
                document.getElementById('checkoutNoBalance').hidden = tieneSaldo;
                document.getElementById('checkoutAmount').required = tieneSaldo;
                document.getElementById('checkoutMethod').required = tieneSaldo;
                document.getElementById('checkoutAmount').disabled = !tieneSaldo;
                document.getElementById('checkoutMethod').disabled = !tieneSaldo;
                document.getElementById('formCheckout').action = '/adminreserva/checkout/' + button.dataset.id + '/';
                checkoutDialog.showModal();
            });
        });
    }
});
