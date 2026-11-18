document.addEventListener("DOMContentLoaded", function () {
    const modal = document.getElementById("modalReembolso");
    const form = document.getElementById("formReembolso");
    if (!modal || !form) return;

    const csrfInput = form.querySelector('input[name="csrfmiddlewaretoken"]');
    const feedback = document.getElementById("reembolsoFeedback");
    const submitButton = document.getElementById("confirmarReembolso");

    function cerrarModal() {
        modal.classList.remove("activo");
        modal.setAttribute("aria-hidden", "true");
    }

    document.querySelectorAll(".btn-procesar-reembolso").forEach(function (button) {
        button.addEventListener("click", function () {
            form.dataset.reservaId = button.dataset.id;
            document.getElementById("reembolsoHuesped").textContent = button.dataset.nombre;
            document.getElementById("reembolsoReserva").textContent = "CC-" + button.dataset.id.padStart(4, "0");
            document.getElementById("reembolsoMonto").textContent = new Intl.NumberFormat("es-CO", {
                style: "currency",
                currency: "COP",
                maximumFractionDigits: 2
            }).format(Number(button.dataset.monto));
            feedback.textContent = "";
            submitButton.disabled = false;
            modal.classList.add("activo");
            modal.setAttribute("aria-hidden", "false");
        });
    });

    document.getElementById("cerrarModalReembolso").addEventListener("click", cerrarModal);
    document.getElementById("cancelarModalReembolso").addEventListener("click", cerrarModal);
    modal.addEventListener("click", function (event) {
        if (event.target === modal) cerrarModal();
    });

    form.addEventListener("submit", function (event) {
        event.preventDefault();
        const reservaId = form.dataset.reservaId;
        if (!reservaId || !csrfInput) {
            feedback.textContent = "No se pudo preparar el reembolso. Recarga la página e inténtalo nuevamente.";
            return;
        }

        const button = document.querySelector('.btn-procesar-reembolso[data-id="' + reservaId + '"]');
        submitButton.disabled = true;
        feedback.textContent = "Procesando reembolso…";
        const body = new URLSearchParams(new FormData(form));
        body.set("monto", button ? button.dataset.monto : "");
        fetch("/adminreserva/" + reservaId + "/reembolso", {
            method: "POST",
            headers: {
                "X-CSRFToken": csrfInput.value,
                "Content-Type": "application/x-www-form-urlencoded"
            },
            body: body.toString()
        }).then(function (response) {
            return response.json().then(function (data) {
                if (!response.ok || !data.success) {
                    throw new Error(data.message || "No se pudo procesar el reembolso.");
                }
                feedback.textContent = data.message;
                window.setTimeout(function () {
                    window.location.reload();
                }, 1200);
            });
        }).catch(function (error) {
            feedback.textContent = error.message || "No se pudo procesar el reembolso.";
            submitButton.disabled = false;
        });
    });
});
