/* AI Assistant page: chat history (saved in this browser), Tamil/English, copy, clear, suggestions. */
(function () {
  const $ = (id) => document.getElementById(id);
  const box = $("messages"), input = $("question"), sendBtn = $("send");
  const SUGGESTED = JSON.parse($("chips").dataset.suggested);
  const KEY = "chat_history_v1";
  const UI = {
    en: {welcome: "Hello! I can answer questions about event proposals, venue capacity, registration, and approvals. What would you like to know?",
         placeholder: "Ask about event policies… (Enter to send, Shift+Enter for new line)", ready: "Ready", thinking: "Thinking…",
         copy: "Copy", retry: "Retry", clear: "Clear", cleared: "Conversation cleared.", sources: "Sources", confirmClear: "Clear the whole conversation?",
         empty: "Please type a question before sending.", long: "Please keep your question under 500 characters."},
    ta: {welcome: "வணக்கம்! நிகழ்வு முன்மொழிவுகள், அரங்க கொள்ளளவு, பதிவு மற்றும் ஒப்புதல்கள் பற்றிய கேள்விகளுக்கு நான் பதிலளிக்க முடியும். என்ன தெரிந்துகொள்ள விரும்புகிறீர்கள்?",
         placeholder: "நிகழ்வு விதிகள் பற்றி கேளுங்கள்… (அனுப்ப Enter)", ready: "தயார்", thinking: "யோசிக்கிறது…",
         copy: "நகலெடு", retry: "மீண்டும்", clear: "அழி", cleared: "உரையாடல் அழிக்கப்பட்டது.", sources: "ஆதாரங்கள்", confirmClear: "முழு உரையாடலையும் அழிக்கவா?",
         empty: "அனுப்பும் முன் கேள்வியை உள்ளிடவும்.", long: "கேள்வி 500 எழுத்துகளுக்குள் இருக்க வேண்டும்."},
  };
  const t = (k) => UI[App.getLang()][k];
  let busy = false;
  let history = [];   // [{role: "user"|"assistant", content, sources?, time}]

  const load = () => { try { history = JSON.parse(localStorage.getItem(KEY) || "[]"); } catch (_) { history = []; } if (!Array.isArray(history)) history = []; };
  const save = () => { try { localStorage.setItem(KEY, JSON.stringify(history.slice(-50))); } catch (_) { /* ignore */ } };
  const stamp = (d) => new Date(d || Date.now()).toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"});
  const scroll = () => { box.scrollTop = box.scrollHeight; };

  function setStatus(kind, text) {
    $("ai-status").className = "status " + kind;
    $("ai-status-text").textContent = text;
  }
  function setBusy(on) {
    busy = on; sendBtn.disabled = on;
    document.querySelectorAll(".chip").forEach((b) => (b.disabled = on));
  }

  function bubble(text, who, o = {}) {
    const meta = App.el("div", {class: "meta"}, stamp(o.time));
    if (o.sources && o.sources.length) meta.append(`${t("sources")}: ${o.sources.join(", ")}`);
    if (who === "bot" && !o.error) {
      const b = App.el("button", {type: "button", class: "link-btn", text: t("copy")});
      b.addEventListener("click", () => App.copy(text, b));
      meta.append(b);
    }
    if (o.retry) {
      const r = App.el("button", {type: "button", class: "link-btn", text: t("retry")});
      r.addEventListener("click", () => { wrap.remove(); ask(o.retry, true); });
      meta.append(r);
    }
    const wrap = App.el("div", {class: `msg ${who}${o.error ? " error" : ""}`}, App.el("div", {class: "bubble", text}), meta);
    box.append(wrap); scroll();
    return wrap;
  }

  function render() {
    box.replaceChildren();
    bubble(t("welcome"), "bot", {time: Date.now()});
    history.forEach((m) => bubble(m.content, m.role === "user" ? "user" : "bot", {sources: m.sources, time: m.time}));
    $("chips").replaceChildren(...SUGGESTED[App.getLang()].map((q) => {
      const c = App.el("button", {type: "button", class: "chip", text: q});
      c.addEventListener("click", () => ask(q));
      return c;
    }));
    input.placeholder = t("placeholder");
    $("ai-status-text").textContent = t("ready");
  }

  async function ask(question, isRetry = false) {
    question = (question || "").trim();
    const warn = $("chat-validation");
    warn.hidden = true;
    if (busy) return;
    if (!question) { warn.textContent = t("empty"); warn.hidden = false; return; }
    if (question.length > 500) { warn.textContent = t("long"); warn.hidden = false; return; }

    const prior = history.slice(-6).map(({role, content}) => ({role, content}));   // context for follow-ups
    if (!isRetry) { history.push({role: "user", content: question, time: Date.now()}); bubble(question, "user"); save(); }
    setBusy(true); setStatus("busy", t("thinking"));
    const typing = App.el("div", {class: "msg bot typing", role: "status"}, App.el("div", {class: "bubble", "aria-label": "Assistant is typing"}, App.el("i"), App.el("i"), App.el("i")));
    box.append(typing); scroll();
    try {
      const d = await App.postJSON("/api/chat", {question, language: App.getLang(), history: prior});
      typing.remove();
      history.push({role: "assistant", content: d.answer, sources: d.sources, time: Date.now()}); save();
      bubble(d.answer, "bot", {sources: d.sources});
      setStatus("ok", "Online");
    } catch (ex) {
      typing.remove();
      bubble(ex.message, "bot", {error: true, retry: question});
      setStatus("bad", "Unavailable");
    } finally {
      setBusy(false); input.focus({preventScroll: true});
    }
  }

  const resize = () => { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 140) + "px"; };
  input.addEventListener("input", resize);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("chat-form").requestSubmit(); } });
  $("chat-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const q = input.value;
    if (busy) return;
    if (q.trim()) { input.value = ""; resize(); }
    ask(q);
  });
  $("clear-chat").addEventListener("click", async () => {
    if (!history.length) return;
    if (!(await App.confirm(t("confirmClear"), {confirmLabel: t("clear"), danger: true}))) return;
    history = []; save(); render();
    App.toast(t("cleared"), "success", 2500);
  });
  document.addEventListener("langchange", render);

  load(); render();
  // Links like /assistant?q=... (dashboard quick actions) ask the question straight away.
  const q = new URLSearchParams(location.search).get("q");
  if (q) { ask(q); window.history.replaceState({}, "", location.pathname); }
})();
