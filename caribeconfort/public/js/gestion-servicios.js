document.addEventListener('DOMContentLoaded', function () {
    var rejectionDialog = document.getElementById('modalRechazoServicio');
    var rejectionForm = document.getElementById('formRechazoServicio');
    var rejectionSelect = document.getElementById('motivoRechazoServicio');
    var rejectionDetails = document.getElementById('detalleRechazoServicio');
    var rejectionText = rejectionDetails ? rejectionDetails.querySelector('textarea') : null;

    document.querySelectorAll('[data-reject-service]').forEach(function (button) {
        button.addEventListener('click', function () {
            if (!rejectionDialog || !rejectionForm) return;
            rejectionForm.action = button.dataset.action;
            rejectionForm.querySelector('[name="next"]').value = button.dataset.next;
            rejectionForm.reset();
            if (rejectionDetails) rejectionDetails.hidden = true;
            if (rejectionText) {
                rejectionText.disabled = true;
                rejectionText.required = false;
            }
            rejectionDialog.showModal();
        });
    });

    if (rejectionSelect && rejectionDetails && rejectionText) {
        rejectionSelect.addEventListener('change', function () {
            var isOther = rejectionSelect.value === 'otro';
            rejectionDetails.hidden = !isOther;
            rejectionText.disabled = !isOther;
            rejectionText.required = isOther;
            if (!isOther) rejectionText.value = '';
        });
    }

    document.querySelectorAll('[data-open-service-manual]').forEach(function (button) {
        button.addEventListener('click', function () {
            var dialog = document.getElementById(button.dataset.openServiceManual);
            if (dialog) dialog.showModal();
        });
    });

    document.querySelectorAll('.manual-service-status').forEach(function (select) {
        function updateManualServiceFields() {
            var form = select.closest('form');
            if (!form) return;
            var rejected = select.value === 'Rechazado';
            var approved = select.value === 'Aprobado';
            var serviceInactive = select.disabled;
            var methodGroup = form.querySelector('[data-manual-payment-method]');
            var reasonGroup = form.querySelector('[data-manual-rejection-reason]');
            var methodSelect = methodGroup ? methodGroup.querySelector('select') : null;
            var reasonInput = reasonGroup ? reasonGroup.querySelector('textarea') : null;

            if (methodGroup) methodGroup.hidden = rejected;
            if (methodSelect) {
                methodSelect.disabled = serviceInactive || rejected;
                methodSelect.required = !serviceInactive && approved;
                if (rejected) methodSelect.value = '';
            }
            if (reasonGroup) reasonGroup.hidden = !rejected;
            if (reasonInput) {
                reasonInput.disabled = serviceInactive || !rejected;
                reasonInput.required = !serviceInactive && rejected;
                if (!rejected) reasonInput.value = '';
            }
        }

        select.addEventListener('change', updateManualServiceFields);
        updateManualServiceFields();
    });

    document.querySelectorAll('.service-reject-dialog, .service-management-dialog').forEach(function (dialog) {
        dialog.querySelectorAll('[data-close-dialog]').forEach(function (button) {
            button.addEventListener('click', function () {
                if (dialog.open) dialog.close();
            });
        });
        dialog.addEventListener('click', function (event) {
            if (event.target === dialog) dialog.close();
        });
    });
});
