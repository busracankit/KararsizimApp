// Vote without reloading the page. Without JS the vote form still posts normally
// and the server redirects back to the poll page.
(function () {
  "use strict";

  const MESSAGES = {
    already_voted: "Bu ankete zaten oy vermişsin.",
    poll_closed: "Bu anketin oylaması kapandı.",
    rate_limited: "Çok hızlı gidiyorsun, biraz bekleyip tekrar dene.",
    login_required: "Bu ağdan bu ankete çok fazla oy verildi. Oy vermek için giriş yap.",
    invalid_option: "Bu seçenek geçersiz. Sayfayı yenileyip tekrar dene.",
    network: "Bağlantı sorunu oldu, oyun kaydedilmedi. Tekrar dene.",
  };

  function csrfToken(form) {
    const input = form.querySelector("input[name=csrfmiddlewaretoken]");
    return getCookie("csrftoken") || (input && input.value) || "";
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  // Build the same markup as templates/partials/poll_results.html.
  function renderResults(data) {
    const top = Math.max.apply(null, data.results.map(function (r) { return r.votes; }).concat(0));
    const list = el("ul", "results is-new");
    list.setAttribute("aria-label", "Sonuçlar");
    const fills = [];

    data.results.forEach(function (r, i) {
      const item = el("li", "result opt-" + (i + 1));
      if (top > 0 && r.votes === top) item.classList.add("is-winner");
      const mine = r.id === data.voted_option_id;
      if (mine) item.classList.add("is-mine");

      const row = el("div", "result__row");
      const label = el("span", "result__label");
      if (r.image_url) {
        const img = el("img", "result__img");
        img.src = r.image_url;
        img.alt = "";
        img.width = 28;
        img.height = 28;
        label.appendChild(img);
      }
      label.appendChild(document.createTextNode(r.text));
      if (mine) {
        label.appendChild(document.createTextNode(" "));
        label.appendChild(el("span", "result__mine", "Senin oyun ✓"));
      }
      row.appendChild(label);
      row.appendChild(el("span", "result__meta", "%" + r.percent + " · " + r.votes + " oy"));

      const track = el("div", "result__track");
      track.setAttribute("aria-hidden", "true");
      const fill = el("div", "result__fill");
      fill.style.width = "0%";
      track.appendChild(fill);
      fills.push([fill, r.percent]);

      item.appendChild(row);
      item.appendChild(track);
      list.appendChild(item);
    });

    // Grow the bars on the next frame so the CSS width transition runs.
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        fills.forEach(function (pair) { pair[0].style.width = pair[1] + "%"; });
      });
    });
    return list;
  }

  function resetForm(form) {
    delete form.dataset.busy;
    form.querySelectorAll("button").forEach(function (b) {
      b.disabled = false;
      b.classList.remove("is-picked");
    });
  }

  // "Oyumu değiştir" block: a copy of the vote buttons that posts change=1.
  function buildChangeBlock(voteForm) {
    const details = el("details", "change-vote");
    details.setAttribute("data-change-vote", "");
    details.appendChild(el("summary", "", "Oyumu değiştir"));
    const copy = voteForm.cloneNode(true);
    const flag = document.createElement("input");
    flag.type = "hidden";
    flag.name = "change";
    flag.value = "1";
    copy.insertBefore(flag, copy.firstChild);
    resetForm(copy);
    details.appendChild(copy);
    return details;
  }

  function showResults(body, form, data) {
    const results = renderResults(data);
    const current = body.querySelector(".results");
    const mainForm = body.querySelector(":scope > [data-vote-form]");
    let details = body.querySelector("[data-change-vote]");

    if (current) {
      current.replaceWith(results);
    } else if (mainForm) {
      if (data.can_change && !details) details = buildChangeBlock(mainForm);
      mainForm.replaceWith(results);
    }

    if (data.can_change && details) {
      if (!details.isConnected) results.after(details);
      details.open = false;
      resetForm(details.querySelector("[data-vote-form]"));
    } else if (details) {
      details.remove();
    }

    const total = body.querySelector("[data-total-votes]");
    if (total) total.textContent = data.total_votes;
    const hint = body.querySelector(".poll-card__hint");
    if (hint) hint.remove();
  }

  function notice(body, text) {
    const box = body.querySelector("[data-vote-notice]");
    if (!box) return;
    box.textContent = text;
    box.hidden = !text;
  }

  document.addEventListener("submit", function (event) {
    const form = event.target.closest("[data-vote-form]");
    if (!form || !window.fetch) return;
    event.preventDefault();

    const button = event.submitter;
    if (!button || !button.value || form.dataset.busy) return;
    const body = form.closest("[data-poll-body]");
    const buttons = form.querySelectorAll("button");

    form.dataset.busy = "1";
    buttons.forEach(function (b) { b.disabled = true; });
    button.classList.add("is-picked");
    notice(body, "");

    fetch(form.action, {
      method: "POST",
      headers: {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-CSRFToken": csrfToken(form),
      },
      body: (function () {
        const params = new URLSearchParams({ option_id: button.value });
        if (form.querySelector("input[name=change]")) params.set("change", "1");
        return params;
      })(),
      credentials: "same-origin",
    })
      .then(function (response) {
        return response.json().catch(function () { return { ok: false, error: "network" }; });
      })
      .then(function (data) {
        if (data.results) {
          showResults(body, form, data);
          if (!data.ok) notice(body, MESSAGES[data.error] || "");
          return;
        }
        throw new Error(data.error || "network");
      })
      .catch(function (error) {
        notice(body, MESSAGES[error.message] || MESSAGES.network);
        resetForm(form);
      });
  });
})();
