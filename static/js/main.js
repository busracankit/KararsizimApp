// Small site-wide helpers. No framework on purpose.
(function () {
  "use strict";

  // Fade out flash messages after a few seconds.
  document.querySelectorAll(".flash").forEach(function (el) {
    setTimeout(function () {
      el.classList.add("is-hiding");
      el.addEventListener("transitionend", function () { el.remove(); }, { once: true });
    }, 4000);
  });

  // "Copy link" buttons (only shown when the Clipboard API is available).
  document.querySelectorAll("[data-copy-link]").forEach(function (button) {
    if (!navigator.clipboard) return;
    button.hidden = false;
    const label = button.textContent;
    button.addEventListener("click", function () {
      navigator.clipboard.writeText(button.dataset.url || window.location.href).then(
        function () { button.textContent = "✓ Kopyalandı"; },
        function () { button.textContent = "Kopyalanamadı"; }
      ).finally(function () {
        setTimeout(function () { button.textContent = label; }, 2000);
      });
    });
  });
})();

// Read a cookie value (used later for the CSRF token in AJAX requests).
function getCookie(name) {
  const match = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
  return match ? decodeURIComponent(match[1]) : null;
}
