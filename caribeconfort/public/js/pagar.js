document.addEventListener("DOMContentLoaded", function () {
    const container = document.getElementById("pagoContainer");
    const monto = document.getElementById("txtMontoAbono");
    if (!container || !monto) return;

    const total = Number(container.dataset.total);
    const pagado = Number(container.dataset.pagado);
    const saldo = Math.max(0, total - pagado);
    const opciones = document.querySelectorAll('input[type="radio"][name="tipo_pago"]');

    function formatearPrecio(valor) {
        return new Intl.NumberFormat('es-CO', {
            style: 'currency',
            currency: 'COP',
            maximumFractionDigits: 0
        }).format(valor);
    }

    function actualizarMonto() {
        const seleccion = document.querySelector('input[name="tipo_pago"]:checked');
        const montoPagar = seleccion && seleccion.value === '50' && pagado === 0
            ? total * 0.5
            : saldo;
        monto.textContent = formatearPrecio(montoPagar);
    }

    opciones.forEach(function (opcion) {
        opcion.addEventListener('change', actualizarMonto);
    });
    actualizarMonto();

    const metodosPago = document.querySelectorAll('input[name="metodo_pago"]');
    const panelesPago = document.querySelectorAll('[data-payment-fields]');

    function actualizarCamposPago() {
        const metodoSeleccionado = document.querySelector('input[name="metodo_pago"]:checked');
        panelesPago.forEach(function (panel) {
            const activo = metodoSeleccionado
                && panel.dataset.paymentFields === metodoSeleccionado.value;
            panel.hidden = !activo;
            panel.querySelectorAll('input, select').forEach(function (campo) {
                campo.disabled = !activo;
                campo.required = activo;
            });
        });
    }

    metodosPago.forEach(function (metodo) {
        metodo.addEventListener('change', actualizarCamposPago);
    });
    actualizarCamposPago();
});
