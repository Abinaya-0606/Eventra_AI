/* Light/dark theme toggle. The saved choice (or the system setting) is applied by a tiny inline script in <head>
   before the page paints, so there is no flash. This file only wires the toggle button. */
(function () {
  const root = document.documentElement;
  const current = () => (root.dataset.theme === "dark" ? "dark" : "light");
  function apply(theme, remember) {
    root.dataset.theme = theme;
    if (remember) { try { localStorage.setItem("theme", theme); } catch (_) { /* storage blocked: still works for this visit */ } }
    document.querySelectorAll("[data-theme-toggle]").forEach((b) => {
      b.setAttribute("aria-pressed", String(theme === "dark"));
      b.dataset.mode = theme;
    });
    document.dispatchEvent(new CustomEvent("themechange", {detail: theme}));
  }
  document.querySelectorAll("[data-theme-toggle]").forEach((b) => b.addEventListener("click", () => apply(current() === "dark" ? "light" : "dark", true)));
  apply(current(), false);
  // Follow the system setting until the person makes their own choice.
  const mq = window.matchMedia && matchMedia("(prefers-color-scheme: dark)");
  if (mq && mq.addEventListener) mq.addEventListener("change", (e) => {
    let saved = null; try { saved = localStorage.getItem("theme"); } catch (_) { /* ignore */ }
    if (!saved) apply(e.matches ? "dark" : "light", false);
  });
})();
