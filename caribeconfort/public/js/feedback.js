(function () {
    let activeResolve = null;
    let activeDialog = null;

    function getDialog() {
        if (activeDialog) return activeDialog;

        const dialog = document.createElement('dialog');
        dialog.className = 'cc-feedback-dialog';
        dialog.setAttribute('aria-labelledby', 'ccFeedbackTitle');
        dialog.innerHTML =
            '<div class="cc-feedback-content">' +
                '<p class="cc-feedback-eyebrow">CARIBE CONFORT</p>' +
                '<h2 id="ccFeedbackTitle"></h2>' +
                '<p class="cc-feedback-message"></p>' +
                '<footer class="cc-feedback-actions">' +
                    '<button type="button" class="cc-feedback-cancel">Cancelar</button>' +
                    '<button type="button" class="cc-feedback-accept">Entendido</button>' +
                '</footer>' +
            '</div>';
        document.body.appendChild(dialog);

        const title = dialog.querySelector('#ccFeedbackTitle');
        const message = dialog.querySelector('.cc-feedback-message');
        const cancel = dialog.querySelector('.cc-feedback-cancel');
        const accept = dialog.querySelector('.cc-feedback-accept');

        function settle(result) {
            if (dialog.open) dialog.close();
            if (activeResolve) {
                const resolve = activeResolve;
                activeResolve = null;
                resolve(result);
            }
        }

        accept.addEventListener('click', function () { settle(true); });
        cancel.addEventListener('click', function () { settle(false); });
        dialog.addEventListener('cancel', function (event) {
            event.preventDefault();
            settle(false);
        });
        dialog.addEventListener('close', function () {
            if (activeResolve) {
                const resolve = activeResolve;
                activeResolve = null;
                resolve(false);
            }
        });

        activeDialog = {
            element: dialog,
            title: title,
            message: message,
            cancel: cancel,
            accept: accept
        };
        return activeDialog;
    }

    function showFeedback(message, options) {
        const settings = options || {};
        const dialog = getDialog();
        dialog.title.textContent = settings.title || 'Aviso';
        dialog.message.textContent = message || '';
        dialog.cancel.hidden = !settings.confirm;
        dialog.accept.textContent = settings.confirm ? (settings.acceptLabel || 'Confirmar') : 'Entendido';

        return new Promise(function (resolve) {
            activeResolve = resolve;
            dialog.element.showModal();
            dialog.accept.focus();
        });
    }

    window.ccAlert = function (message, title) {
        return showFeedback(message, { title: title || 'Aviso' });
    };

    window.ccConfirm = function (message, title) {
        return showFeedback(message, {
            confirm: true,
            title: title || 'Confirma esta acción',
            acceptLabel: 'Confirmar'
        });
    };

    document.addEventListener('submit', function (event) {
        const form = event.target;
        if (!(form instanceof HTMLFormElement) || !form.dataset.confirmMessage) return;
        if (form.dataset.confirmed === 'true') return;
        if (form.dataset.confirmPending === 'true') {
            event.preventDefault();
            return;
        }

        event.preventDefault();
        form.dataset.confirmPending = 'true';
        const submitter = event.submitter;
        window.ccConfirm(form.dataset.confirmMessage).then(function (confirmed) {
            delete form.dataset.confirmPending;
            if (!confirmed) return;
            form.dataset.confirmed = 'true';
            if (typeof form.requestSubmit === 'function') {
                if (submitter && submitter.form === form) form.requestSubmit(submitter);
                else form.requestSubmit();
            } else {
                HTMLFormElement.prototype.submit.call(form);
            }
            delete form.dataset.confirmed;
        });
    });
})();
