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
})();

// Read a cookie value (used later for the CSRF token in AJAX requests).
function getCookie(name) {
  const match = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
  return match ? decodeURIComponent(match[1]) : null;
}
