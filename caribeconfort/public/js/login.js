(function () {

    document.querySelectorAll(".rg-toggle").forEach((btn) => {
        btn.addEventListener("click", () => {
            const input = document.getElementById(btn.dataset.toggle);
            if (!input) return;

            const mostrar = input.type === "password";
            input.type = mostrar ? "text" : "password";
            btn.classList.toggle("activo", mostrar);

            btn.setAttribute(
                "aria-label",
                mostrar ? "Ocultar contraseña" : "Mostrar contraseña"
            );
        });
    });

    const form = document.querySelector(".registro-form");
    if (form) {
        form.addEventListener("submit", () => {
            const btn = form.querySelector(".rg-submit");
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = "Ingresando...";
            }
        });
    }

})();