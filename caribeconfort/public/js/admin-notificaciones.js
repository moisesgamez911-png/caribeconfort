document.addEventListener("DOMContentLoaded", function () {
    const toggle = document.getElementById("adNotificationToggle");
    const menu = document.getElementById("adNotificationMenu");
    if (!toggle || !menu) return;

    function setOpen(open) {
        toggle.setAttribute("aria-expanded", open ? "true" : "false");
        menu.hidden = !open;
    }

    toggle.addEventListener("click", function () {
        setOpen(menu.hidden);
    });

    document.addEventListener("click", function (event) {
        if (!menu.contains(event.target) && !toggle.contains(event.target)) {
            setOpen(false);
        }
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && !menu.hidden) {
            setOpen(false);
            toggle.focus();
        }
    });
});
