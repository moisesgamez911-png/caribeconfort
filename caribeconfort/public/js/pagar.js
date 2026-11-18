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
});
