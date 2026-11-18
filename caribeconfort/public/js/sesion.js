function mostrarPassword() {
    var campo = document.getElementById('txtpass');
    var icono = document.getElementById('iconoOjo');
    if (campo.type === 'password') {
        campo.type = 'text';
        icono.src = icono.dataset.ojoCerrado;
    } else {
        campo.type = 'password';
        icono.src = icono.dataset.ojoAbierto;
    }
}