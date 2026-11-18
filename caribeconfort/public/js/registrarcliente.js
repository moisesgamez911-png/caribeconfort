(function () {

    document.querySelectorAll(".rg-toggle").forEach((btn) => {
        btn.addEventListener("click", () => {
            const input = document.getElementById(btn.dataset.toggle);
            if (!input) return;

            const mostrar = input.type === "password";
            input.type = mostrar ? "text" : "password";
            btn.classList.toggle("activo", mostrar);
        });
    });


    const form = document.querySelector(".registro-form");

    if (form) {
        form.addEventListener("submit", (e) => {
            const nombre     = form.querySelector("[name='nombre']").value.trim();
            const apellido   = form.querySelector("[name='apellido']").value.trim();
            const correo     = form.querySelector("[name='correo']").value.trim();
            const telefono   = form.querySelector("[name='telefono']").value.trim();
            const tipoDoc    = form.querySelector("[name='tipo_documento']").value;
            const numDoc     = form.querySelector("[name='numero_documento']").value.trim();
            const nacionalid = form.querySelector("[name='nacionalidad']").value;
            const pass1      = form.querySelector("[name='password']").value;
            const pass2      = form.querySelector("[name='password2']").value;

            const errores = [];

            if (!nombre)     errores.push("El nombre es obligatorio.");
            if (!apellido)   errores.push("El apellido es obligatorio.");
            if (!correo)     errores.push("El correo es obligatorio.");
            if (!telefono)   errores.push("El teléfono es obligatorio.");
            if (!tipoDoc)    errores.push("Selecciona el tipo de documento.");
            if (!numDoc)     errores.push("El número de documento es obligatorio.");
            if (!nacionalid) errores.push("Selecciona tu nacionalidad.");
            if (pass1.length < 6) errores.push("La contraseña debe tener al menos 6 caracteres.");
            if (pass1 !== pass2)  errores.push("Las contraseñas no coinciden.");

            if (errores.length) {
                e.preventDefault();
                window.ccAlert("Por favor corrige:\n\n• " + errores.join("\n• "));
                return;
            }

            const btn = form.querySelector(".rg-submit");
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = "Creando cuenta...";
            }
        });
    }


})();

(function () {

    const modal  = document.getElementById("modalCodigo");
    const btnX   = document.getElementById("cerrarModalCodigo");

    if (!modal) return;

    function cerrarModal() {
        modal.style.display = "none";
    }

    function abrirModal() {
        modal.style.display = "flex";
        const input = modal.querySelector(".modal-codigo-input");
        if (input) setTimeout(() => input.focus(), 100);
    }

    if (btnX) btnX.addEventListener("click", cerrarModal);

    modal.addEventListener("click", (e) => {
        if (e.target === modal) cerrarModal();
    });

    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && modal.style.display === "flex") {
            cerrarModal();
        }
    });

    if (modal.style.display === "flex") {
        const input = modal.querySelector(".modal-codigo-input");
        if (input) setTimeout(() => input.focus(), 150);
    }

})();