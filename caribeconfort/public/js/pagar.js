document.addEventListener("DOMContentLoaded", function () {
    const container = document.getElementById("pagoContainer");
    const monto = document.getElementById("txtMontoAbono");
    if (!container || !monto) return;

    const total = Number(container.dataset.total);
    const pagado = Number(container.dataset.pagado);
    const saldo = Math.max(0, total - pagado);
    const opciones = document.querySelectorAll('input[type="radio"][name="tipo_pago"]');
    const cvv = document.getElementById('cardCvv');
    const toggleCvv = document.getElementById('toggleCvv');

    if (cvv && toggleCvv) {
        const iconoVer = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M2 12s3.5-6.5 10-6.5S22 12 22 12s-3.5 6.5-10 6.5S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg>';
        const iconoOcultar = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M3 3l18 18M10.6 10.6a2 2 0 002.8 2.8M9.9 5.7A10.8 10.8 0 0112 5.5c6.5 0 10 6.5 10 6.5a15 15 0 01-3.2 3.8M6.2 6.2C3.5 8 2 12 2 12s3.5 6.5 10 6.5a10 10 0 003.1-.5"/></svg>';
        toggleCvv.addEventListener('click', function () {
            const visible = cvv.type === 'password';
            cvv.type = visible ? 'text' : 'password';
            toggleCvv.setAttribute('aria-pressed', visible ? 'true' : 'false');
            toggleCvv.setAttribute('aria-label', visible ? 'Ocultar contraseña' : 'Mostrar contraseña');
            toggleCvv.title = visible ? 'Ocultar contraseña' : 'Mostrar contraseña';
            toggleCvv.innerHTML = visible ? iconoOcultar : iconoVer;
        });
    }

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
