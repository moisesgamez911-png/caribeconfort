
document.addEventListener('DOMContentLoaded', function() {
        const check = document.getElementById('tieneAcompanantes');
        const contenedor = document.getElementById('contenedorAcompanantes');
        const lista = document.getElementById('listaAcompanantes');
        const btnAgregar = document.getElementById('btnAgregarAcompanante');
        let contador = 0;


        check.addEventListener('change', function() {
            if (this.checked) {
                contenedor.style.display = 'block';
                if (lista.children.length === 0) agregarFila(); 
            } else {
                contenedor.style.display = 'none';
                lista.innerHTML = ''; 
                contador = 0;
            }
        });

        btnAgregar.addEventListener('click', agregarFila);

        function agregarFila() {
            contador++;
            const div = document.createElement('div');
            div.style.cssText = "display: grid; grid-template-columns: 1fr 1fr 1fr auto; gap: 10px; margin-bottom: 10px; align-items: end;";
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
                <button type="button" onclick="this.parentElement.remove()" style="background: transparent; border: none; color: #D6383D; cursor: pointer; padding-bottom: 12px;">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
                </button>
            `;
            lista.appendChild(div);
        }
    });