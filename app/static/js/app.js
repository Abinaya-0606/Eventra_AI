/* Shared helpers used by every page: navigation menu, language switch, toasts, confirm dialogs,
   loading states, inline form validation, table filter and DOM + fetch helpers. */
(function () {
  const $ = (id) => document.getElementById(id);
  const App = (window.App = {});

  /* ---------- interface text in English / Tamil (page headings and AI output follow the language too) ---------- */
  const TA = {
    "Dashboard": "முகப்புப் பலகை", "My Events": "என் நிகழ்வுகள்", "Calendar": "நாட்காட்டி", "Analytics": "பகுப்பாய்வு",
    "Tasks": "பணிகள்", "AI Studio": "AI ஸ்டுடியோ", "AI Assistant": "AI உதவியாளர்", "Budget Calculator": "பட்ஜெட் கணிப்பான்",
    "Event Policies": "நிகழ்வு விதிகள்", "About": "பற்றி", "Users": "பயனர்கள்", "Venues": "அரங்குகள்", "Log out": "வெளியேறு",
    "All Events": "அனைத்து நிகழ்வுகள்", "Browse Events": "நிகழ்வுகளைப் பார்", "My Registered Events": "நான் பதிவு செய்த நிகழ்வுகள்",
    "Notifications": "அறிவிப்புகள்", "Overview": "கண்ணோட்டம்", "Event Approvals": "நிகழ்வு அனுமதிகள்", "Admin Accounts": "நிர்வாகி கணக்குகள்", "More": "மேலும்", "Approvals": "அனுமதிகள்", "AI Event Assistant": "AI நிகழ்வு உதவியாளர்",
    "Activity Logs": "செயல்பாட்டுப் பதிவுகள்", "Students": "மாணவர்கள்", "Organizers": "ஏற்பாட்டாளர்கள்",
    "AI suggestions are estimates. Always confirm rules, venues and budgets with your college.":
      "AI பரிந்துரைகள் மதிப்பீடுகளே. விதிகள், அரங்குகள், பட்ஜெட் ஆகியவற்றை எப்போதும் உங்கள் கல்லூரியுடன் உறுதிசெய்யுங்கள்.",
    "Skip to content": "உள்ளடக்கத்திற்குச் செல்",
    // dynamic strings
    "Cancel": "ரத்து செய்", "Confirm": "உறுதிசெய்", "Close": "மூடு", "Copied!": "நகலெடுக்கப்பட்டது!", "Switch colour theme": "வண்ணத் தீமை மாற்று",
    "Please fill in this field.": "இந்த புலத்தை நிரப்பவும்.", "Enter a valid email address.": "சரியான மின்னஞ்சல் முகவரியை உள்ளிடவும்.",
    "Passwords do not match.": "கடவுச்சொற்கள் பொருந்தவில்லை.", "No matches": "பொருத்தங்கள் இல்லை", "Loading": "ஏற்றுகிறது",
    "Please check the highlighted fields.": "குறிக்கப்பட்ட புலங்களைச் சரிபார்க்கவும்.",
  };
  App.t = (key) => (App.getLang() === "ta" && TA[key]) || key;
  App.translations = TA;
  function applyI18n() {
    document.querySelectorAll("[data-i18n]").forEach((node) => {
      if (!node.dataset.en) node.dataset.en = node.textContent.trim();
      node.textContent = App.t(node.dataset.en);
    });
    document.querySelectorAll("[data-theme-toggle]").forEach((b) => {
      const label = App.t("Switch colour theme"); b.setAttribute("aria-label", label); b.title = label;
    });
  }

  /* ---------- mobile navigation (only on pages that have the sidebar) ---------- */
  const sidebar = $("sidebar"), scrim = $("scrim"), menuBtn = $("menu-btn");
  if (sidebar && scrim && menuBtn) {
    const closeMenu = () => { sidebar.classList.remove("open"); scrim.classList.remove("show"); menuBtn.setAttribute("aria-expanded", "false"); };
    menuBtn.addEventListener("click", () => {
      const open = sidebar.classList.toggle("open");
      scrim.classList.toggle("show", open);
      menuBtn.setAttribute("aria-expanded", String(open));
    });
    scrim.addEventListener("click", closeMenu);
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeMenu(); });
  }

  /* ---------- after logout, the Back button must not show a cached private page ---------- */
  window.addEventListener("pageshow", (e) => { if (e.persisted) window.location.reload(); });

  /* ---------- language (English / Tamil), remembered in this browser ---------- */
  // Saved choice in this browser wins; otherwise use the language from the user's profile.
  App.getLang = () => {
    let saved = null;
    try { saved = localStorage.getItem("lang"); } catch (_) { /* storage blocked */ }
    return (saved || document.body.dataset.lang) === "ta" ? "ta" : "en";
  };
  App.setLang = (lang, remember = true) => {
    if (remember) { try { localStorage.setItem("lang", lang); } catch (_) { /* storage blocked: keep going */ } }
    document.querySelectorAll(".seg-btn").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lang === lang)));
    document.documentElement.lang = lang;
    applyI18n();
    document.dispatchEvent(new CustomEvent("langchange", {detail: lang}));
  };
  document.querySelectorAll(".seg-btn").forEach((b) => b.addEventListener("click", () => App.setLang(b.dataset.lang)));

  /* ---------- DOM + fetch helpers ---------- */
  // el("div", {class: "x", text: "hi"}, child1, child2) builds DOM safely (text is never parsed as HTML).
  App.el = (tag, props = {}, ...children) => {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (v == null || v === false) continue;
      if (k === "text") node.textContent = v;
      else if (k === "class") node.className = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v === true ? "" : v);
    }
    children.flat().forEach((c) => c != null && node.append(c));
    return node;
  };
  const {el} = App;
  App.money = (n) => Number(n).toLocaleString("en-IN", {style: "currency", currency: "INR", minimumFractionDigits: 2, maximumFractionDigits: 2});

  // POST JSON and return the parsed body. Throws Error(message) with a friendly message on failure.
  App.postJSON = async (url, body) => {
    let res;
    try {
      const csrf = document.querySelector('meta[name="csrf-token"]').content;   // proves the request came from our own page
      res = await fetch(url, {method: "POST", headers: {"Content-Type": "application/json", "X-CSRF-Token": csrf}, body: JSON.stringify(body)});
    } catch (_) {
      throw Object.assign(new Error("Could not reach the server. Check that the Flask app is running and try again."), {network: true});
    }
    let data = {};
    try { data = await res.json(); } catch (_) { /* non-JSON response */ }
    if (res.status === 401) { location.href = "/login?next=" + encodeURIComponent(location.pathname); }   // session expired
    if (!res.ok || data.error) {
      throw Object.assign(new Error(data.error || "Something went wrong on the server. Please try again."), {field: data.field, status: res.status});
    }
    return data;
  };

  /* ---------- toasts ---------- */
  let toastBox = null;
  App.toast = (message, type = "info", ms) => {
    if (!toastBox) toastBox = document.body.appendChild(el("div", {class: "toasts", id: "toasts", role: "region", "aria-live": "polite", "aria-label": "Notifications"}));
    while (toastBox.children.length >= 4) toastBox.firstChild.remove();
    const close = el("button", {type: "button", class: "toast-x", "aria-label": App.t("Close"), text: "×"});
    const node = el("div", {class: `toast ${type}`, role: type === "error" ? "alert" : "status"}, el("span", {class: "toast-msg", text: message}), close);
    toastBox.append(node);
    let timer;
    const remove = () => { clearTimeout(timer); node.classList.add("leaving"); setTimeout(() => node.remove(), 200); };
    const start = () => { timer = setTimeout(remove, ms || (type === "error" ? 7000 : 4000)); };
    close.addEventListener("click", remove);
    node.addEventListener("mouseenter", () => clearTimeout(timer));
    node.addEventListener("mouseleave", start);
    start();
    return node;
  };

  /* ---------- confirm dialog (replaces window.confirm) ---------- */
  let dialog = null;
  App.confirm = (message, {confirmLabel, danger = false} = {}) => {
    if (!window.HTMLDialogElement) return Promise.resolve(window.confirm(message));
    if (!dialog) {
      dialog = el("dialog", {class: "confirm-dialog", "aria-labelledby": "confirm-msg"},
        el("p", {id: "confirm-msg", class: "confirm-msg"}),
        el("div", {class: "confirm-actions"}, el("button", {type: "button", class: "btn soft", "data-act": "cancel"}), el("button", {type: "button", class: "btn primary", "data-act": "ok"})));
      document.body.append(dialog);
    }
    dialog.querySelector(".confirm-msg").textContent = message;
    const cancel = dialog.querySelector('[data-act="cancel"]'), ok = dialog.querySelector('[data-act="ok"]');
    cancel.textContent = App.t("Cancel"); ok.textContent = confirmLabel || App.t("Confirm");
    ok.classList.toggle("danger-fill", danger);
    return new Promise((resolve) => {
      const done = (value) => { dialog.close(); cleanup(); resolve(value); };
      const onCancel = () => done(false), onOk = () => done(true), onEsc = (e) => { e.preventDefault(); done(false); };
      const onBackdrop = (e) => { if (e.target === dialog) done(false); };
      const cleanup = () => { cancel.removeEventListener("click", onCancel); ok.removeEventListener("click", onOk); dialog.removeEventListener("cancel", onEsc); dialog.removeEventListener("click", onBackdrop); };
      cancel.addEventListener("click", onCancel); ok.addEventListener("click", onOk);
      dialog.addEventListener("cancel", onEsc); dialog.addEventListener("click", onBackdrop);
      dialog.showModal(); cancel.focus();
    });
  };
  // <form data-confirm="Are you sure?" [data-confirm-label="Delete"]>: ask first, then submit for real.
  document.addEventListener("submit", async (e) => {
    const form = e.target, msg = form.dataset && form.dataset.confirm;
    if (!msg || form.dataset.confirmed === "1") return;
    e.preventDefault(); e.stopImmediatePropagation();
    const yes = await App.confirm(msg, {confirmLabel: form.dataset.confirmLabel || "Delete", danger: true});
    if (yes) { form.dataset.confirmed = "1"; form.requestSubmit(); }
  }, true);

  /* ---------- loading skeleton for AI results ---------- */
  App.skeleton = (lines = 4) => el("div", {class: "skeleton", role: "status", "aria-label": App.t("Loading")},
    Array.from({length: lines}, (_, i) => el("i", {style: `width:${[92, 78, 86, 60, 70][i % 5]}%`})));

  /* ---------- page progress bar + double-submit guard ---------- */
  const bar = el("div", {class: "nav-progress", "aria-hidden": "true"});
  document.body.append(bar);
  const startBar = () => { bar.classList.remove("done"); bar.classList.add("run"); };
  const stopBar = () => bar.classList.remove("run");
  window.addEventListener("pageshow", () => {       // also runs when coming back with the Back button
    stopBar();
    document.querySelectorAll(".is-submitting").forEach((b) => { b.classList.remove("is-submitting"); b.disabled = false; });
    document.querySelectorAll("form[data-confirmed]").forEach((f) => delete f.dataset.confirmed);
  });
  document.addEventListener("click", (e) => {
    const a = e.target.closest && e.target.closest("a[href]");
    if (!a || e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    const href = a.getAttribute("href");
    if (a.target === "_blank" || a.hasAttribute("download") || !href.startsWith("/") || href.startsWith("//") || /\.pdf(\?|$)/.test(href)) return;
    if (href.split("#")[0] === location.pathname + location.search && href.includes("#")) return;
    startBar();
  });
  document.addEventListener("submit", (e) => {
    const form = e.target;
    if (e.defaultPrevented || form.method !== "post" || form.classList.contains("ai-form") || form.id === "chat-form") return;
    startBar();
    const btn = form.querySelector("button[type=submit]:not(.inline-btn)");
    if (btn && !form.classList.contains("inline")) setTimeout(() => { btn.classList.add("is-submitting"); btn.disabled = true; }, 0);
  });

  /* ---------- inline form validation: <form data-validate novalidate> ---------- */
  const labelOf = (field) => {
    const l = field.labels && field.labels[0] ? field.labels[0] : field.closest(".form-row") && field.closest(".form-row").querySelector("label");
    return l ? l.firstChild && l.firstChild.textContent.trim() || l.textContent.trim() : "";
  };
  const messageFor = (field) => {
    const v = field.validity, name = labelOf(field);
    if (field.validationMessage && field.validity.customError) return field.validationMessage;
    if (v.valueMissing) return name ? `${name} ${App.getLang() === "ta" ? "தேவை." : "is required."}` : App.t("Please fill in this field.");
    if (v.typeMismatch && field.type === "email") return App.t("Enter a valid email address.");
    if (v.tooShort) return App.getLang() === "ta" ? `குறைந்தது ${field.minLength} எழுத்துகள் தேவை.` : `Use at least ${field.minLength} characters.`;
    if (v.rangeUnderflow || v.rangeOverflow) {
      const lo = field.min, hi = field.max;
      return App.getLang() === "ta" ? `மதிப்பு ${lo || "…"} முதல் ${hi || "…"} வரை இருக்க வேண்டும்.` : lo && hi ? `Enter a number from ${lo} to ${hi}.` : lo ? `Enter ${lo} or more.` : `Enter ${hi} or less.`;
    }
    return field.validationMessage || App.t("Please fill in this field.");
  };
  function showFieldState(field) {
    let note = field.parentElement.querySelector(`.field-msg[data-for="${field.id}"]`);
    if (field.checkValidity()) {
      field.classList.remove("invalid"); field.removeAttribute("aria-invalid");
      if (note) note.remove();
      return true;
    }
    field.classList.add("invalid"); field.setAttribute("aria-invalid", "true");
    if (!note) { note = el("small", {class: "field-msg", "data-for": field.id, id: `${field.id}-msg`, role: "alert"}); field.after(note); }
    field.setAttribute("aria-describedby", note.id);
    note.textContent = messageFor(field);
    return false;
  }
  let fieldUid = 0;
  document.querySelectorAll("form[data-validate]").forEach((form) => {
    const fields = () => [...form.elements].filter((f) => f.willValidate && f.type !== "hidden");
    fields().forEach((f) => { if (!f.id) f.id = `fld-${++fieldUid}`; });
    const pw = form.elements.new_password || form.elements.password, confirm = form.elements.confirm_password;
    const syncMatch = () => { if (pw && confirm) confirm.setCustomValidity(confirm.value && confirm.value !== pw.value ? App.t("Passwords do not match.") : ""); };
    form.addEventListener("input", (e) => { if (e.target.classList.contains("invalid")) { syncMatch(); showFieldState(e.target); } });
    form.addEventListener("focusout", (e) => { if (e.target.willValidate && e.target.value !== "") { syncMatch(); showFieldState(e.target); } });
    form.addEventListener("submit", (e) => {
      syncMatch();
      const bad = fields().filter((f) => !showFieldState(f));
      if (bad.length) {
        e.preventDefault(); e.stopImmediatePropagation();
        document.querySelector(".nav-progress").classList.remove("run");
        bad[0].focus();
        App.toast(App.t("Please check the highlighted fields."), "error");
      }
    }, true);
  });

  /* ---------- live table filter: <input type="search" data-filter-table="table-id"> ---------- */
  document.querySelectorAll("[data-filter-table]").forEach((input) => {
    const table = $(input.dataset.filterTable); if (!table) return;
    const body = table.tBodies[0], none = el("tr", {class: "no-match", hidden: true}, el("td", {colspan: table.tHead ? table.tHead.rows[0].cells.length : 1, class: "muted", "data-i18n": "No matches", text: "No matches"}));
    body.append(none);
    input.addEventListener("input", () => {
      const q = input.value.trim().toLowerCase(); let shown = 0;
      [...body.rows].forEach((r) => { if (r === none) return; const hit = !q || r.textContent.toLowerCase().includes(q); r.hidden = !hit; shown += hit; });
      none.hidden = shown > 0; applyI18n();
    });
  });

  /* ---------- clipboard + download ---------- */
  App.copy = async (text, btn) => {
    const old = btn ? btn.textContent : "";
    try {
      await navigator.clipboard.writeText(text);
      if (btn) btn.textContent = App.t("Copied!");
      App.toast(App.t("Copied!"), "success", 1800);
    } catch (_) {
      if (btn) btn.textContent = "Copy failed";
      App.toast("Copy failed. Select the text and copy it manually.", "error");
    }
    if (btn) setTimeout(() => (btn.textContent = old), 1500);
  };
  App.download = (filename, text) => {
    const url = URL.createObjectURL(new Blob([text], {type: "text/plain;charset=utf-8"}));
    const a = Object.assign(document.createElement("a"), {href: url, download: filename});
    document.body.append(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  };

  /* ---------- server flash messages become toasts (errors stay on the page) ---------- */
  document.querySelectorAll(".flashes .flash:not(.error)").forEach((f) => { App.toast(f.textContent.trim(), f.classList.contains("success") ? "success" : "info"); f.remove(); });
  document.querySelectorAll(".flashes:empty").forEach((f) => f.remove());

  App.setLang(App.getLang(), false);   // first paint: show the current language without saving it
})();
