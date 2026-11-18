let contador = 1;

// ==========================
// CARGAR DATOS GUARDADOS
// ==========================

function cargarDatos() {
    const datosGuardados = localStorage.getItem('clientes');
    
    if (datosGuardados) {
        const clientes = JSON.parse(datosGuardados);
        const tablaBody = document.getElementById('infotabla');
        tablaBody.innerHTML = '';
        
        clientes.forEach((cliente, index) => {
            const nuevaFila = document.createElement('tr');
            nuevaFila.innerHTML = `
                <th scope="row">${index + 1}</th>
                <td>${cliente.nombre}</td>
                <td>${cliente.apellido}</td>
                <td>${cliente.celular}</td>
                <td>${cliente.direccion}</td>
                <td>${cliente.tipo}</td>
                <td>${cliente.identificacion}</td>
            `;
            tablaBody.appendChild(nuevaFila);
        });
        
        contador = clientes.length + 1;
    }
}

// ==========================
// AGREGAR FILA
// ==========================

function agregarFila() {
    const nombre = document.getElementById("nombre").value;
    const apellido = document.getElementById("apellido").value;
    const celular = document.getElementById("celular").value;
    const direccion = document.getElementById("direccion").value;
    const tipo = document.getElementById("tipo").value;
    const identificacion = document.getElementById("identificacion").value;

    if (nombre === "" || apellido === "" || celular === "" || direccion === "" || tipo === "" || identificacion === "") {
        window.ccAlert("Por favor complete todos los campos");
        return;
    }

    const tablabody = document.getElementById("infotabla");
    const nuevafila = document.createElement("tr");
    nuevafila.innerHTML = `
        <th scope="row">${contador}</th>
        <td>${nombre}</td>
        <td>${apellido}</td>
        <td>${celular}</td>
        <td>${direccion}</td>
        <td>${tipo}</td>
        <td>${identificacion}</td>
    `;

    tablabody.appendChild(nuevafila);

    // 🔥 Guardar en localStorage
    guardarCliente(nombre, apellido, celular, direccion, tipo, identificacion);

    contador++;

    // Limpiar campos
    document.getElementById("nombre").value = "";
    document.getElementById("apellido").value = "";
    document.getElementById("celular").value = "";
    document.getElementById("direccion").value = "";
    document.getElementById("tipo").value = "C.C";
    document.getElementById("identificacion").value = "";
}

// ==========================
// GUARDAR EN LOCALSTORAGE
// ==========================

function guardarCliente(nombre, apellido, celular, direccion, tipo, identificacion) {
    let clientes = localStorage.getItem('clientes');
    
    if (clientes) {
        clientes = JSON.parse(clientes);
    } else {
        clientes = [];
    }
    
    clientes.push({
        nombre: nombre,
        apellido: apellido,
        celular: celular,
        direccion: direccion,
        tipo: tipo,
        identificacion: identificacion
    });
    
    localStorage.setItem('clientes', JSON.stringify(clientes));
}

// ==========================
// 🔥 CARGAR DATOS AL ABRIR LA PÁGINA
// ==========================

document.addEventListener('DOMContentLoaded', cargarDatos);