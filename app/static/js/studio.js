/* AI Studio page: tabs, form submission, and one renderer per AI feature. */
(function () {
  const {el, money} = App;
  const slug = (s) => (s || "event").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "event";

  /* ---- tabs ---- */
  const tabs = [...document.querySelectorAll(".tab")];
  function openTab(key) {
    tabs.forEach((t) => t.setAttribute("aria-selected", String(t.dataset.tab === key)));
    document.querySelectorAll(".panel").forEach((p) => (p.hidden = p.id !== "panel-" + key));
    try { sessionStorage.setItem("studio-tab", key); } catch (_) { /* ignore */ }
  }
  tabs.forEach((t) => t.addEventListener("click", () => openTab(t.dataset.tab)));
  tabs.forEach((t, i) => t.addEventListener("keydown", (e) => {
    const n = {ArrowRight: 1, ArrowLeft: -1}[e.key];
    if (n) { const next = tabs[(i + n + tabs.length) % tabs.length]; next.focus(); openTab(next.dataset.tab); }
  }));
  try { const k = sessionStorage.getItem("studio-tab"); if (k && document.getElementById("panel-" + k)) openTab(k); } catch (_) { /* ignore */ }

  // Connect every <label> to the control that follows it (accessibility).
  let uid = 0;
  document.querySelectorAll(".form-row").forEach((row) => {
    const label = row.querySelector("label"), ctl = row.querySelector("input,select,textarea");
    if (label && ctl) { ctl.id = ctl.id || `f${++uid}`; label.htmlFor = ctl.id; }
  });

  /* ---- small render helpers ---- */
  const list = (items) => el("ul", {class: "res-list"}, items.map((i) => el("li", {text: i})));
  const section = (title, body) => el("div", {class: "res-section"}, el("h3", {text: title}), body);
  function actions(getText, filename) {
    const copy = el("button", {type: "button", class: "btn soft sm", text: "Copy"});
    copy.addEventListener("click", () => App.copy(getText(), copy));
    const dl = el("button", {type: "button", class: "btn soft sm", text: "Download .txt"});
    dl.addEventListener("click", () => App.download(filename, getText()));
    return el("div", {class: "res-actions"}, copy, dl);
  }

  /* ---- renderers: each takes the JSON from the API and returns a DOM node ---- */
  const RENDER = {
    plan(d, form) {
      const rows = d.expenses.map((e) => el("tr", {}, el("td", {text: e.item}), el("td", {text: money(e.amount)})));
      const table = el("table", {class: "table"},
        el("tbody", {}, rows),
        el("tfoot", {},
          el("tr", {}, el("td", {text: "Estimated total"}), el("td", {text: money(d.estimated_total)})),
          el("tr", {}, el("td", {text: "Your budget"}), el("td", {text: money(d.budget)})),
          el("tr", {}, el("td", {text: d.within_budget ? "Remaining" : "Over budget by"}),
            el("td", {text: money(Math.abs(d.remaining_budget))}))));
      const text = () => [
        "OBJECTIVES", ...d.objectives.map((x) => "- " + x), "", "ARRANGEMENTS", ...d.arrangements.map((x) => "- " + x), "",
        "EQUIPMENT", ...d.equipment.map((x) => "- " + x), "", "TEAM", ...d.team.map((t) => `- ${t.role}: ${t.responsibilities}`), "",
        "ESTIMATED EXPENSES", ...d.expenses.map((e) => `- ${e.item}: ${money(e.amount)}`), `Total: ${money(d.estimated_total)}`, "",
        "PREPARATION", ...d.preparation.map((x, i) => `${i + 1}. ${x}`)].join("\n");
      return el("div", {},
        section("Objectives", list(d.objectives)),
        section("Required arrangements", list(d.arrangements)),
        section("Equipment", list(d.equipment)),
        section("Organizing team", el("div", {class: "team"}, d.team.map((t) => el("div", {}, el("b", {text: t.role}), t.responsibilities)))),
        section("Estimated expenses", el("div", {},
          table, el("p", {class: "disclaimer"}, el("span", {class: "pill " + (d.within_budget ? "ok" : "bad"), text: d.within_budget ? "Within budget" : "Over budget"}),
            " Amounts are AI estimates; totals are calculated by the server."))),
        section("Preparation suggestions", el("ol", {class: "res-list"}, d.preparation.map((i) => el("li", {text: i})))),
        actions(text, `${slug(form.elements.name.value)}-plan.txt`));
    },

    names(d) {
      return el("div", {class: "name-list"}, d.names.map((n) => {
        const b = el("button", {type: "button", class: "btn soft sm icon", text: "Copy"});
        b.addEventListener("click", () => App.copy(n.name, b));
        return el("div", {class: "name-item"}, el("div", {}, el("b", {text: n.name}), n.tagline ? el("span", {text: n.tagline}) : null), b);
      }));
    },

    description(d, form) {
      const box = (title, text) => el("div", {class: "desc-box"}, el("h4", {text: title}), text);
      const all = () => [d.tagline, d.short_description, d.full_description].filter(Boolean).join("\n\n");
      return el("div", {}, d.tagline ? box("Tagline", d.tagline) : null,
        box("Short description", d.short_description), box("Full description", d.full_description),
        actions(all, `${slug(form.elements.name.value)}-description.txt`));
    },

    schedule(d, form) {
      const body = el("tbody");
      const fmt = (hhmm) => { const [h, m] = hhmm.split(":").map(Number); return `${String(h % 12 || 12).padStart(2, "0")}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`; };
      const text = () => [...body.querySelectorAll("tr")].map((r) => {
        const [t, title, desc] = r.querySelectorAll("input");
        return t.value ? `${fmt(t.value)} - ${title.value}${desc.value ? " (" + desc.value + ")" : ""}` : null;
      }).filter(Boolean).join("\n");
      const addRow = (item = {time: "", title: "", description: ""}) => {
        const del = el("button", {type: "button", class: "btn soft icon", "aria-label": "Remove row"}, (() => { const s = document.createElementNS("http://www.w3.org/2000/svg", "svg"); s.innerHTML = '<use href="#i-trash"/>'; return s; })());
        const row = el("tr", {},
          el("td", {}, el("input", {type: "time", value: item.time, "aria-label": "Time"})),
          el("td", {}, el("input", {type: "text", value: item.title, maxlength: 120, "aria-label": "Activity"})),
          el("td", {}, el("input", {type: "text", value: item.description, maxlength: 200, "aria-label": "Details"})),
          el("td", {}, del));
        del.addEventListener("click", () => row.remove());
        body.append(row);
      };
      d.items.forEach(addRow);
      const add = el("button", {type: "button", class: "btn soft sm", text: "+ Add row"});
      add.addEventListener("click", () => addRow());
      const sortBtn = el("button", {type: "button", class: "btn soft sm", text: "Sort by time"});
      sortBtn.addEventListener("click", () => [...body.querySelectorAll("tr")]
        .sort((a, b) => (a.querySelector("input").value || "99").localeCompare(b.querySelector("input").value || "99"))
        .forEach((r) => body.append(r)));
      const bar = actions(text, `${slug(form.elements.name.value)}-schedule.txt`);
      bar.prepend(add, sortBtn);
      return el("div", {}, el("p", {class: "disclaimer", text: "Edit any time, title or detail. Copy or download uses your edited version."}),
        el("table", {class: "sched"}, body), bar);
    },

    checklist(d, form) {
      const labels = {before: "Before the event", during: "During the event", after: "After the event"};
      const text = () => Object.entries(labels).map(([k, label]) =>
        [label.toUpperCase(), ...d[k].map((x) => `[ ] ${x}`)].join("\n")).join("\n\n");
      return el("div", {class: "checklist"},
        Object.entries(labels).map(([k, label]) => el("div", {class: "check-col"}, el("h3", {text: label}),
          d[k].map((item) => el("label", {class: "check-item"}, el("input", {type: "checkbox"}), el("span", {text: item}))))),
        actions(text, `${slug(form.elements.name.value)}-checklist.txt`));
    },

    letter(d, form) {
      const subject = el("input", {type: "text", value: d.subject, "aria-label": "Subject"});
      const body = el("textarea", {class: "letter-body", rows: 16, "aria-label": "Letter body"});
      body.value = d.body;
      const text = () => `Subject: ${subject.value}\n\n${body.value}`;
      return el("div", {}, el("p", {class: "disclaimer", text: "You can edit the letter below before copying. Check every detail before sending."}),
        el("div", {class: "form-row"}, el("label", {text: "Subject"}), subject),
        el("div", {class: "form-row"}, body), actions(text, `${slug(form.elements.event_name.value)}-letter.txt`));
    },
  };

  RENDER.budget = (d) => BudgetOptimizer.render(d);

  /* ---- submit handling (shared by all six forms) ---- */
  document.querySelectorAll(".ai-form").forEach((form) => {
    const kind = form.dataset.kind, err = form.querySelector(".field-error");
    const btn = form.querySelector("button[type=submit]"), lbl = btn.querySelector(".lbl");
    const target = document.querySelector(`[data-result="${kind}"]`);
    let busy = false;

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (busy) return;
      err.hidden = true;
      form.querySelectorAll(".invalid").forEach((n) => n.classList.remove("invalid"));
      const payload = {language: App.getLang()};
      new FormData(form).forEach((v, k) => (payload[k] = v));

      busy = true; btn.disabled = true; btn.classList.add("loading");
      const old = lbl.textContent; lbl.textContent = "Generating";
      target.replaceChildren(App.skeleton(6));
      try {
        const data = await App.postJSON(form.dataset.endpoint, payload);
        target.replaceChildren(RENDER[kind](data, form));
      } catch (ex) {
        target.replaceChildren(el("div", {class: "empty-state small"}, el("p", {text: "Nothing generated yet."})));
        err.textContent = ex.message; err.hidden = false;
        if (ex.field && form.elements[ex.field]) { form.elements[ex.field].classList.add("invalid"); form.elements[ex.field].focus(); }
      } finally {
        busy = false; btn.disabled = false; btn.classList.remove("loading"); lbl.textContent = old;
      }
    });
  });
})();
