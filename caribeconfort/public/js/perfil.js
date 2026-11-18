document.addEventListener("DOMContentLoaded", () => {
    const $ = (selector) => document.querySelector(selector);
    const $$ = (selector) => document.querySelectorAll(selector);

    const editButton = $("#editButton");
    const cancelButton = $("#cancelButton");
    const formActions = $("#formActions");
    
    const editableFields = ["firstName", "lastName", "email", "phone", "address"];
    let editing = false;
    let originalValues = {};

    // Pestañas
    $$(".tab").forEach((tab) => {
        tab.addEventListener("click", () => {
            if (editing) {
                editableFields.forEach(id => $("#" + id).value = originalValues[id]);
                setEditing(false);
            }

            $$(".tab").forEach((item) => item.classList.remove("active"));
            $$(".tab-panel").forEach((panel) => panel.classList.remove("active"));

            tab.classList.add("active");
            $("#panel-" + tab.dataset.tab).classList.add("active");
        });
    });

    function saveOriginalValues() {
        originalValues = {};
        editableFields.forEach((id) => {
            originalValues[id] = $("#" + id).value;
        });
    }

    function setEditing(enabled) {
        editing = enabled;
        editableFields.forEach((id) => {
            $("#" + id).readOnly = !enabled;
        });

        formActions.style.display = enabled ? "flex" : "none";

        editButton.innerHTML = enabled 
            ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:16px;height:16px;"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg><span>Cancelar</span>' 
            : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:16px;height:16px;"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg><span>Editar</span>';
    }

    if (editButton) {
        editButton.addEventListener("click", () => {
            if (!editing) {
                saveOriginalValues();
                setEditing(true);
                $("#firstName").focus();
            } else {
                editableFields.forEach(id => $("#" + id).value = originalValues[id]);
                setEditing(false);
            }
        });
    }

    if (cancelButton) {
        cancelButton.addEventListener("click", () => {
            editableFields.forEach(id => $("#" + id).value = originalValues[id]);
            setEditing(false);
        });
    }
});