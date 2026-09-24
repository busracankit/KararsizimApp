// Poll creation form: add / remove option inputs (2–5). The server validates again.
(function () {
  "use strict";

  const form = document.querySelector("[data-poll-form]");
  if (!form) return;

  const min = Number(form.dataset.min) || 2;
  const max = Number(form.dataset.max) || 5;
  const list = form.querySelector("[data-option-list]");
  const addButton = form.querySelector("[data-add-option]");
  const template = document.getElementById("option-input-template");

  const rows = () => Array.from(list.querySelectorAll("[data-option-row]"));

  // Keep numbering, ids, colours and button states in sync after every change.
  function refresh() {
    const all = rows();
    all.forEach(function (row, i) {
      const n = i + 1;
      row.className = row.className.replace(/\bopt-\S+/, "opt-" + n);
      const input = row.querySelector("input");
      const label = row.querySelector("[data-option-label]");
      const remove = row.querySelector("[data-remove-option]");
      input.id = "option-" + i;
      input.placeholder = "Seçenek " + n;
      label.htmlFor = input.id;
      label.textContent = "Seçenek " + n;
      remove.hidden = false;
      remove.disabled = all.length <= min;
      remove.setAttribute("aria-label", "Seçenek " + n + "'i sil");
    });
    addButton.hidden = false;
    addButton.disabled = all.length >= max;
    addButton.textContent = all.length >= max ? "En fazla " + max + " seçenek" : "+ Seçenek ekle";
  }

  addButton.addEventListener("click", function () {
    if (rows().length >= max) return;
    const fragment = template.content.cloneNode(true);
    list.appendChild(fragment);
    refresh();
    const all = rows();
    all[all.length - 1].querySelector("input").focus();
  });

  list.addEventListener("click", function (event) {
    const button = event.target.closest("[data-remove-option]");
    if (!button || rows().length <= min) return;
    const row = button.closest("[data-option-row]");
    const next = row.nextElementSibling || row.previousElementSibling;
    row.remove();
    refresh();
    if (next) next.querySelector("input").focus();
  });

  // Enter in the last option adds a new one instead of submitting early.
  list.addEventListener("keydown", function (event) {
    if (event.key !== "Enter" || event.target.tagName !== "INPUT") return;
    const all = rows();
    const isLast = event.target.closest("[data-option-row]") === all[all.length - 1];
    if (isLast && all.length < max && event.target.value.trim()) {
      event.preventDefault();
      addButton.click();
    }
  });

  refresh();
})();
