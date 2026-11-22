document.addEventListener("DOMContentLoaded", function () {
    const btnUser = document.getElementById("btnUser");
    const userMenu = document.getElementById("userMenu");

    if (btnUser && userMenu) {
        btnUser.addEventListener("click", function (event) {
            event.preventDefault();
            event.stopPropagation();
            const isOpen = userMenu.classList.toggle("abierto");
            btnUser.setAttribute("aria-expanded", String(isOpen));
        });

        document.addEventListener("click", function (event) {
            if (!userMenu.contains(event.target) && !btnUser.contains(event.target)) {
                userMenu.classList.remove("abierto");
                btnUser.setAttribute("aria-expanded", "false");
            }
        });
    }

    const priceFormatter = new Intl.NumberFormat("es-CO", {
        maximumFractionDigits: 0
    });
    const paymentModal = document.getElementById("modalPagoServicio");
    const successModal = document.getElementById("modalExitoServicio");
    const quantityInput = document.getElementById("cantidadServicio");
    const formSolicitar = document.getElementById("formSolicitarServicio");
    const paymentMethodInputs = formSolicitar.querySelectorAll('input[name="metodo_pago_preferido"]');
    const paymentDetailGroups = formSolicitar.querySelectorAll('[data-payment-details]');
    const secondBeneficiaryToggle = document.getElementById("btnAgregarBeneficiario");
    const secondBeneficiaryGroup = document.getElementById("segundaPersonaServicio");

    function setSecondBeneficiaryVisible(visible) {
        if (!secondBeneficiaryToggle || !secondBeneficiaryGroup) return;
        secondBeneficiaryGroup.hidden = !visible;
        secondBeneficiaryToggle.setAttribute("aria-expanded", String(visible));
        secondBeneficiaryToggle.textContent = visible
            ? "Quitar segunda persona"
            : "Agregar segunda persona (opcional)";
        if (!visible) {
            const input = secondBeneficiaryGroup.querySelector("input");
            if (input) input.value = "";
        }
    }

    if (secondBeneficiaryToggle) {
        secondBeneficiaryToggle.addEventListener("click", function () {
            setSecondBeneficiaryVisible(secondBeneficiaryGroup.hidden);
        });
    }

    function syncPaymentDetails() {
        const selectedMethod = formSolicitar.querySelector('input[name="metodo_pago_preferido"]:checked')?.value;
        paymentDetailGroups.forEach(function (group) {
            const active = group.dataset.paymentDetails === selectedMethod;
            group.hidden = !active;
            group.querySelectorAll('[data-payment-field]').forEach(function (field) {
                field.disabled = !active;
                field.required = active;
                if (!active) field.value = '';
            });
        });
    }

    paymentMethodInputs.forEach(function (input) {
        input.addEventListener('change', syncPaymentDetails);
    });

    function updateDisplayedPrice() {
        const price = Number(document.getElementById("hdnServicioPrecio").value);
        const quantity = Number(quantityInput.value);
        if (Number.isFinite(price) && Number.isFinite(quantity) && quantity > 0) {
            document.getElementById("txtServicioPrecio").textContent =
                "$ " + priceFormatter.format(price * quantity);
        }
    }

    document.querySelectorAll(".btn-solicitar").forEach(function (button) {
        button.addEventListener("click", function (event) {
            event.preventDefault();

            const service = button.dataset.servicio;
            const serviceId = button.dataset.servicioId;
            const price = Number(button.dataset.precio);

            formSolicitar.reset();
            setSecondBeneficiaryVisible(false);
            syncPaymentDetails();
            const reservationSelect = document.getElementById("selectReservaServicio");
            if (reservationSelect.dataset.reservaPreseleccionada) {
                reservationSelect.value = reservationSelect.dataset.reservaPreseleccionada;
            }
            document.getElementById("txtServicioNombre").textContent = service;
            document.getElementById("hdnServicioId").value = serviceId;
            document.getElementById("hdnServicioNombre").value = service;
            document.getElementById("hdnServicioPrecio").value = String(price);
            quantityInput.value = "1";
            updateDisplayedPrice();
            paymentModal.classList.add("activo");
            document.getElementById("selectReservaServicio").focus();
        });
    });

    if (quantityInput) {
        quantityInput.addEventListener("input", updateDisplayedPrice);
    }

    const closePayment = function () {
        paymentModal.classList.remove("activo");
    };
    const closeSuccess = function () {
        successModal.classList.remove("activo");
        window.location.reload();
    };

    document.getElementById("btnCerrarServicio").addEventListener("click", closePayment);
    document.getElementById("btnCancelarServicio").addEventListener("click", closePayment);
    document.getElementById("btnCerrarExitoServicio").addEventListener("click", closeSuccess);

    paymentModal.addEventListener("click", function (event) {
        if (event.target === paymentModal) {
            closePayment();
        }
    });
    successModal.addEventListener("click", function (event) {
        if (event.target === successModal) {
            closeSuccess();
        }
    });
    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
            if (successModal.classList.contains("activo")) {
                closeSuccess();
            } else {
                closePayment();
            }
        }
    });

    formSolicitar.addEventListener("submit", function (event) {
        event.preventDefault();

        if (!formSolicitar.reportValidity()) return;

        const submitButton = document.getElementById("btnConfirmarPagoServicio");
        const serviceId = document.getElementById("hdnServicioId").value;
        const reservationId = document.getElementById("selectReservaServicio").value;

        if (!reservationId) {
            window.ccAlert("Por favor, selecciona una reserva activa para adjuntar el servicio.");
            return;
        }
        if (!quantityInput.reportValidity()) {
            return;
        }

        const originalText = submitButton.textContent;
        submitButton.textContent = "Procesando...";
        submitButton.disabled = true;

        const formData = new FormData(formSolicitar);
        formData.append("servicio_id", serviceId);

        fetch("/servicios/solicitar", {
            method: "POST",
            body: formData
        })
            .then(async function (response) {
                const data = await response.json();
                if (!response.ok) {
                    throw new Error(data.error || "No se pudo agregar el servicio.");
                }
                return data;
            })
            .then(function (data) {
                if (data.ok) {
                    closePayment();
                    successModal.classList.add("activo");
                } else {
                    window.ccAlert(data.error || "Ocurrió un error al procesar el servicio.");
                }
            })
            .catch(function (error) {
                window.ccAlert(error.message || "Error de conexión.");
            })
            .finally(function () {
                submitButton.textContent = originalText;
                submitButton.disabled = false;
            });
    });
});
