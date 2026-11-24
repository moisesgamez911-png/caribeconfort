document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-modal]').forEach(function (button) {
        button.addEventListener('click', function () {
            var modal = document.getElementById(button.dataset.modal);
            if (modal) {
                modal.classList.add('is-open');
                modal.setAttribute('aria-hidden', 'false');
            }
        });
    });
    document.querySelectorAll('[data-close-modal]').forEach(function (button) {
        button.addEventListener('click', function () {
            var modal = button.closest('.room-modal');
            if (modal) {
                modal.classList.remove('is-open');
                modal.setAttribute('aria-hidden', 'true');
            }
        });
    });
    document.querySelectorAll('.room-modal').forEach(function (modal) {
        modal.addEventListener('click', function (event) {
            if (event.target === modal) {
                modal.classList.remove('is-open');
                modal.setAttribute('aria-hidden', 'true');
            }
        });
    });
});