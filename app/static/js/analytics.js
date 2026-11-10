/* Analytics page: draws the charts with Chart.js (loaded from a CDN). The same numbers are always in the tables
   under each chart, so the page still works if the library cannot load. */
(function () {
  const data = JSON.parse(document.getElementById("analytics-data").textContent);
  const COLORS = ["#4f46e5", "#0ea5e9", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#64748b", "#ec4899"];
  const inr = (n) => "₹" + Number(n).toLocaleString("en-IN", {maximumFractionDigits: 0});

  function showFallback() {
    document.querySelectorAll(".chart-box").forEach((box) => {
      box.querySelector("canvas").hidden = true; box.style.height = "auto";
      box.querySelector(".chart-fallback").hidden = false;
      const details = box.parentElement.querySelector("details"); if (details) details.open = true;
    });
  }
  const charts = [];
  function draw() {
    if (!window.Chart) return showFallback();
    charts.splice(0).forEach((c) => { try { c.destroy(); } catch (_) { /* already gone */ } });
    const css = getComputedStyle(document.documentElement);
    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
    Chart.defaults.color = css.getPropertyValue("--muted").trim() || "#64748b";
    Chart.defaults.borderColor = css.getPropertyValue("--line").trim() || "#e2e8f0";
    const make = (key, config) => { try { charts.push(new Chart(document.getElementById("chart-" + key), config)); } catch (_) { showFallback(); } };
    const axes = (money) => ({
      x: {grid: {display: false}},
      y: {beginAtZero: true, ticks: money ? {callback: (v) => inr(v)} : {precision: 0}}});
    const bar = (labels, datasets, money, extra = {}) => ({type: "bar", data: {labels, datasets},
      options: {responsive: true, maintainAspectRatio: false, scales: axes(money),
        plugins: {legend: {display: datasets.length > 1}, tooltip: {callbacks: money ? {label: (c) => `${c.dataset.label}: ${inr(c.parsed.y)}`} : {}}}, ...extra}});
    const donut = (labels, values) => ({type: "doughnut", data: {labels, datasets: [{data: values, backgroundColor: COLORS, borderWidth: 2}]},
      options: {responsive: true, maintainAspectRatio: false, plugins: {legend: {position: "right"}}}});

    const months = data.monthly.map((m) => m.month);
    make("monthly", bar(months, [{label: "Events", data: data.monthly.map((m) => m.events), backgroundColor: COLORS[0], borderRadius: 6}], false));
    make("budget", bar(months, [{label: "Budget", data: data.monthly.map((m) => m.budget), backgroundColor: COLORS[1], borderRadius: 6}], true));
    make("types", donut(data.types.map((t) => t.label), data.types.map((t) => t.count)));
    const st = data.status.filter((s) => s.count > 0);
    make("status", donut(st.map((s) => s.label), st.map((s) => s.count)));
    make("compare", bar(data.comparison.map((c) => c.name.length > 16 ? c.name.slice(0, 15) + "…" : c.name), [
      {label: "Estimated budget", data: data.comparison.map((c) => c.budget), backgroundColor: COLORS[0], borderRadius: 6},
      {label: "Saved breakdown", data: data.comparison.map((c) => c.planned), backgroundColor: COLORS[2], borderRadius: 6}], true));
    make("categories", bar(data.categories.map((c) => c.label), [{label: "Planned", data: data.categories.map((c) => c.amount), backgroundColor: COLORS[5], borderRadius: 6}], true,
      {indexAxis: "y", scales: {x: {beginAtZero: true, ticks: {callback: (v) => inr(v)}}, y: {grid: {display: false}}}}));
  }
  document.addEventListener("themechange", () => { if (window.Chart && charts.length) draw(); });  // recolour for dark / light
  // Chart.js is loaded with `defer`, so it is ready by DOMContentLoaded; if it failed, window.Chart is undefined.
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", draw); else draw();
})();
