
document.addEventListener('DOMContentLoaded', function() {
        const check = document.getElementById('tieneAcompanantes');
        const contenedor = document.getElementById('contenedorAcompanantes');
        const lista = document.getElementById('listaAcompanantes');
        const btnAgregar = document.getElementById('btnAgregarAcompanante');
        if (!check || !contenedor || !lista || !btnAgregar) return;

        check.addEventListener('change', function() {
            if (this.checked) {
                contenedor.style.display = 'block';
                if (lista.children.length === 0) agregarFila(); 
            } else {
                contenedor.style.display = 'none';
                lista.innerHTML = ''; 
            }
        });

        btnAgregar.addEventListener('click', agregarFila);

        function agregarFila() {
            const div = document.createElement('div');
            div.className = 'ck-companion-row';
            div.innerHTML = `
                <div class="ck-field">
                    <label>Nombre completo</label>
                    <input type="text" name="acompanante_nombre[]" placeholder="Ej: Ana Pérez" required>
                </div>
                <div class="ck-field">
                    <label>Documento</label>
                    <input type="text" name="acompanante_documento[]" placeholder="Ej: 10203040">
                </div>
                <div class="ck-field">
                    <label>Parentesco</label>
                    <input type="text" name="acompanante_parentesco[]" placeholder="Ej: Esposa">
                </div>
                <button type="button" class="ck-remove-companion" aria-label="Quitar acompañante">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M18 6L6 18M6 6l12 12"/></svg>
                </button>
            `;
            div.querySelector('.ck-remove-companion').addEventListener('click', function() {
                div.remove();
            });
            lista.appendChild(div);
        }
    });