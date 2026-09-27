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

  // Prevent double submits (double click / slow network) on normal POST forms.
  // Voting forms are excluded: vote.js handles them with fetch and its own busy state.
  document.querySelectorAll("form[method=post]:not([data-vote-form])").forEach(function (form) {
    form.addEventListener("submit", function () {
      if (form.dataset.submitting) return;
      form.dataset.submitting = "1";
      // Disable after the browser has read the clicked button's name/value.
      setTimeout(function () {
        form.querySelectorAll("button[type=submit]").forEach(function (b) { b.disabled = true; });
      }, 0);
    });
  });
  // Coming back via the browser's back button restores a page from cache: re-enable its forms.
  window.addEventListener("pageshow", function (event) {
    if (!event.persisted) return;
    document.querySelectorAll("form[data-submitting]").forEach(function (form) {
      delete form.dataset.submitting;
      form.querySelectorAll("button[type=submit]").forEach(function (b) { b.disabled = false; });
    });
  });

  // Light / dark toggle. Without a saved choice the OS setting is used.
  const toggle = document.querySelector("[data-theme-toggle]");
  if (toggle) {
    const root = document.documentElement;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const current = function () { return root.dataset.theme || (media.matches ? "dark" : "light"); };
    const paint = function () {
      const dark = current() === "dark";
      toggle.textContent = dark ? "☀️" : "🌙";
      toggle.setAttribute("aria-label", dark ? "Aydınlık moda geç" : "Karanlık moda geç");
      toggle.setAttribute("aria-pressed", String(dark));
    };
    toggle.hidden = false;
    paint();
    toggle.addEventListener("click", function () {
      const next = current() === "dark" ? "light" : "dark";
      root.dataset.theme = next;
      try { localStorage.setItem("theme", next); } catch (e) {}
      paint();
    });
    media.addEventListener("change", paint);
  }

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
