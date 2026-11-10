/* Event details page: editable saved schedule (with AI generation) and AI checklist -> tasks. */
(function () {
  const {el} = App;
  const editor = document.getElementById("schedule-editor");
  if (!editor) return;
  const eventId = editor.dataset.eventId, canManage = editor.dataset.canManage === "true";
  const base = JSON.parse(editor.dataset.event);
  const items = JSON.parse(editor.dataset.items);      // [[time, title, description], ...]

  const fmt = (hhmm) => { const [h, m] = hhmm.split(":").map(Number); return `${String(h % 12 || 12).padStart(2, "0")}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`; };
  const message = el("p", {class: "inline-msg", role: "status", hidden: true});
  const say = (text, bad) => { message.textContent = text; message.className = "inline-msg " + (bad ? "bad" : "ok"); message.hidden = false; };

  /* ---------- schedule ---------- */
  if (!canManage) {
    editor.replaceChildren(items.length
      ? el("table", {class: "table"}, el("tbody", {}, items.map(([t, title, d]) => el("tr", {}, el("td", {text: fmt(t)}), el("td", {}, el("b", {text: title}), d ? el("small", {class: "muted block", text: d}) : null)))))
      : el("div", {class: "empty-state small"}, el("p", {text: "No schedule saved yet."})));
    return;
  }

  const body = el("tbody");
  const trashIcon = () => { const s = document.createElementNS("http://www.w3.org/2000/svg", "svg"); s.innerHTML = '<use href="#i-trash"/>'; return s; };
  function addRow(time = "", title = "", description = "") {
    const del = el("button", {type: "button", class: "btn soft icon", "aria-label": "Remove row"}, trashIcon());
    const row = el("tr", {},
      el("td", {}, el("input", {type: "time", value: time, "aria-label": "Time"})),
      el("td", {}, el("input", {type: "text", value: title, maxlength: 120, "aria-label": "Activity"})),
      el("td", {}, el("input", {type: "text", value: description, maxlength: 200, "aria-label": "Details"})),
      el("td", {}, del));
    del.addEventListener("click", () => row.remove());
    body.append(row);
  }
  const rows = () => [...body.querySelectorAll("tr")].map((r) => {
    const [t, title, d] = r.querySelectorAll("input");
    return {time: t.value, title: title.value.trim(), description: d.value.trim()};
  }).filter((r) => r.time || r.title);
  const fill = (list) => { body.replaceChildren(); list.forEach((r) => addRow(...r)); if (!list.length) body.append(el("tr", {class: "empty-row"})); };
  items.forEach(([t, ti, d]) => addRow(t, ti, d));

  const busyButton = (btn, text, fn) => async () => {
    const old = btn.textContent; btn.disabled = true; btn.textContent = text;
    try { await fn(); } finally { btn.disabled = false; btn.textContent = old; }
  };
  const addBtn = el("button", {type: "button", class: "btn soft sm", text: "+ Add row"});
  addBtn.addEventListener("click", () => addRow());
  const aiBtn = el("button", {type: "button", class: "btn soft sm", text: "Generate with AI"});
  aiBtn.addEventListener("click", busyButton(aiBtn, "Generating…", async () => {
    if (rows().length && !(await App.confirm("Replace the current rows with an AI-generated schedule? (Nothing is saved until you click Save.)", {confirmLabel: "Replace"}))) return;
    try {
      const d = await App.postJSON("/api/ai/schedule", {...base, language: App.getLang()});
      body.replaceChildren(); d.items.forEach((r) => addRow(r.time, r.title, r.description));
      say("AI schedule loaded. Edit it if you like, then click Save schedule.", false);
    } catch (ex) { say(ex.message, true); }
  }));
  const saveBtn = el("button", {type: "button", class: "btn primary sm", text: "Save schedule"});
  saveBtn.addEventListener("click", busyButton(saveBtn, "Saving…", async () => {
    try {
      const out = await App.postJSON(`/api/events/${eventId}/schedule`, {items: rows()});
      say(`Schedule saved (${out.saved} item${out.saved === 1 ? "" : "s"}).`, false);
      App.toast("Schedule saved.", "success");
    } catch (ex) { say(ex.message, true); }
  }));
  editor.replaceChildren(el("table", {class: "sched"}, body), el("div", {class: "res-actions"}, addBtn, aiBtn, saveBtn), message);

  /* ---------- AI checklist -> tasks ---------- */
  const aiChecklist = document.getElementById("ai-checklist"), preview = document.getElementById("checklist-preview");
  if (!aiChecklist) return;
  const PHASES = {before: "Before the event", during: "During the event", after: "After the event"};
  aiChecklist.addEventListener("click", busyButton(aiChecklist, "Generating…", async () => {
    preview.hidden = true;
    try {
      const d = await App.postJSON("/api/ai/checklist", {name: base.name, event_type: base.event_type, participants: base.participants, language: App.getLang()});
      const err = el("p", {class: "inline-msg", hidden: true});
      const groups = Object.entries(PHASES).map(([k, label]) => el("div", {class: "check-col"}, el("h3", {text: label}),
        d[k].map((text) => el("label", {class: "check-item"}, el("input", {type: "checkbox", checked: true, "data-phase": k}), el("span", {text})))));
      const add = el("button", {type: "button", class: "btn primary sm", text: "Add selected as tasks"});
      add.addEventListener("click", async () => {
        const chosen = [...preview.querySelectorAll("input:checked")].map((i) => ({title: i.nextSibling.textContent, phase: i.dataset.phase}));
        if (!chosen.length) { err.textContent = "Select at least one item."; err.className = "inline-msg bad"; err.hidden = false; return; }
        add.disabled = true;
        try { await App.postJSON(`/api/events/${eventId}/tasks/bulk`, {tasks: chosen}); location.hash = "tasks"; location.reload(); }
        catch (ex) { err.textContent = ex.message; err.className = "inline-msg bad"; err.hidden = false; add.disabled = false; }
      });
      preview.replaceChildren(el("p", {class: "disclaimer", text: "Untick anything you do not need, then add the rest as tasks."}), el("div", {class: "checklist"}, groups), add, err);
      preview.hidden = false;
    } catch (ex) { preview.replaceChildren(el("p", {class: "inline-msg bad", text: ex.message})); preview.hidden = false; }
  }));
})();
