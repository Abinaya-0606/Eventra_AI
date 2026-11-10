/* Per-event AI tools page: five tabs. Every result is rendered from JSON with safe DOM building. */
(function () {
  const {el, money} = App;
  const state = JSON.parse(document.getElementById("state").textContent);
  const $ = (id) => document.getElementById(id);
  const url = (p) => `/api/events/${state.eventId}/${p}`;

  /* ---- tabs ---- */
  const tabs = [...document.querySelectorAll(".tab")];
  function openTab(key) {
    tabs.forEach((t) => t.setAttribute("aria-selected", String(t.dataset.tab === key)));
    document.querySelectorAll(".panel").forEach((p) => (p.hidden = p.id !== "panel-" + key));
  }
  tabs.forEach((t) => t.addEventListener("click", () => openTab(t.dataset.tab)));

  /* ---- helpers ---- */
  const list = (items) => el("ul", {class: "res-list"}, items.map((i) => el("li", {text: i})));
  const level = (l) => el("span", {class: "pill lv-" + l, text: l[0].toUpperCase() + l.slice(1)});
  const empty = (text) => el("div", {class: "empty-state small"}, el("p", {text}));

  // Wire a "Generate" button: show a loading state, call the API, render, show errors under the button.
  function generator(key, endpoint, render, body = () => ({}), after) {
    const btn = $("gen-" + key); if (!btn) return;
    const lbl = btn.querySelector(".lbl"), err = document.querySelector(`[data-error="${key}"]`), out = $("out-" + key);
    let busy = false;
    btn.addEventListener("click", async () => {
      if (busy) return;
      busy = true; btn.disabled = true; btn.classList.add("loading"); err.hidden = true;
      const old = lbl.textContent; lbl.textContent = "Generating";
      out.replaceChildren(App.skeleton(5));
      try {
        const data = await App.postJSON(url(endpoint), {language: App.getLang(), ...body()});
        out.replaceChildren(render(data));
        if (after) after(data);
      } catch (ex) {
        out.replaceChildren(empty("Nothing generated yet."));
        err.textContent = ex.message; err.hidden = false;
      } finally { busy = false; btn.disabled = false; btn.classList.remove("loading"); lbl.textContent = old; }
    });
  }

  /* ---- budget ---- */
  const saveBudget = async (items) => { await App.postJSON(url("budget"), {items}); };
  const renderBudget = (d) => BudgetOptimizer.render(d, state.canGenerate ? {onSave: saveBudget} : {});
  if (state.budgetItems) {
    const items = state.categories.map(([c, label]) => ({category: c, label, amount: state.budgetItems[c] || 0, note: ""}));
    $("out-budget").replaceChildren(renderBudget({items, budget: state.budget}));
  }
  generator("budget", "ai/budget", renderBudget);

  /* ---- venues ---- */
  function renderVenues(d) {
    const out = el("div", {});
    out.append(el("p", {class: "disclaimer", text: d.disclaimer}));
    if (d.message) out.append(empty(d.message));
    d.recommendations.forEach((v, i) => out.append(el("div", {class: "res-card-item"},
      el("div", {class: "row-between"}, el("h3", {text: `${i + 1}. ${v.name}`}),
        el("span", {class: "pill ok", text: `Score ${v.score}`})),
      el("p", {class: "muted", text: `Capacity ${v.capacity} · ${money(v.cost_per_day)} per day · fills ${v.fills_percent}% · ${v.budget_share_percent}% of your budget`
        + (v.over_budget ? " · over your total budget" : "")}),
      v.facilities.length ? el("p", {text: "Facilities: " + v.facilities.join(", ")}) : el("p", {class: "muted", text: "No facilities listed for this venue."}),
      v.missing_facilities.length ? el("p", {class: "overdue", text: "Missing: " + v.missing_facilities.join(", ")}) : null,
      v.reason ? el("p", {text: v.reason}) : null, v.tip ? el("p", {class: "muted", text: "Tip: " + v.tip}) : null)));
    if (d.excluded.length) out.append(el("div", {class: "res-section"}, el("h3", {text: "Not suitable"}),
      list(d.excluded.map((x) => `${x.name}: ${x.reason}`))));
    return out;
  }
  if (state.venues) $("out-venues").replaceChildren(renderVenues(state.venues));
  generator("venues", "ai/venues", renderVenues, () => ({facilities: [...document.querySelectorAll('input[name="fac"]:checked')].map((c) => c.value)}));

  /* ---- risks ---- */
  const alertBox = (a) => el("div", {class: "risk-item lv-border-" + a.level}, el("div", {class: "row-between"}, el("b", {text: a.title}), level(a.level)), el("p", {text: a.detail}));
  function renderRisks(d) {
    const out = el("div", {});
    out.append(el("div", {class: "row-between"}, el("h3", {text: "Overall risk level"}), level(d.overall || "low")));
    const alerts = d.alerts || state.alerts || [];
    out.append(el("div", {class: "res-section"}, el("h3", {text: "Detected from your event data"}),
      alerts.length ? el("div", {}, alerts.map(alertBox)) : empty("No rule-based warnings. Good.")));
    if (d.risks) out.append(el("div", {class: "res-section"}, el("h3", {text: "AI risk analysis"}),
      d.risks.map((r) => el("div", {class: "risk-item lv-border-" + r.severity},
        el("div", {class: "row-between"}, el("b", {text: r.title}), level(r.severity)),
        el("small", {class: "muted", text: `${r.category} · likelihood ${r.likelihood} · impact ${r.impact}`}),
        el("p", {text: "Prevention: " + r.prevention})))));
    return out;
  }
  $("out-risks").replaceChildren(renderRisks(state.risks || {alerts: state.alerts, overall: state.overall}));
  generator("risks", "ai/risks", renderRisks);

  /* ---- improvements ---- */
  const renderImprove = (d) => el("div", {}, d.suggestions.map((s) => el("div", {class: "res-card-item"},
    el("span", {class: "pill ok", text: s.area}), el("p", {text: s.suggestion}), s.benefit ? el("p", {class: "muted", text: "Benefit: " + s.benefit}) : null)));
  if (state.improve) $("out-improve").replaceChildren(renderImprove(state.improve));
  generator("improve", "ai/improve", renderImprove);

  /* ---- proposal ---- */
  function renderProposal(p) {
    const c = p.cover, sec = (n, t, body) => el("div", {class: "res-section"}, el("h3", {text: `${n}. ${t}`}), body);
    const text = (s) => el("p", {text: s});
    return el("div", {class: "proposal"},
      el("div", {class: "cover-box"}, el("small", {text: (c.college || "").toUpperCase()}), el("h2", {text: c.title}), el("p", {text: c.event_type}),
        el("p", {class: "muted", text: `${c.date} at ${c.start_time} · ${c.venue} · ${c.participants} participants · by ${c.organizer}${c.department ? ", " + c.department : ""}`})),
      sec(1, "Introduction", text(p.introduction)), sec(2, "Objectives", list(p.objectives)), sec(3, "Event description", text(p.description)),
      sec(4, "Target participants", text(p.target_participants)),
      sec(5, "Schedule", p.schedule.length ? el("table", {class: "table"}, el("tbody", {}, p.schedule.map((r) =>
        el("tr", {}, el("td", {text: r.time_label}), el("td", {text: r.title}))))) : text("No schedule saved yet. Add one on the event page and it will appear here.")),
      sec(6, "Budget breakdown", el("table", {class: "table"}, el("tbody", {}, p.budget.lines.map((l) =>
        el("tr", {}, el("td", {text: l.label}), el("td", {text: money(l.amount)})))),
        el("tfoot", {}, el("tr", {}, el("td", {text: "Total"}), el("td", {text: money(p.budget.total)}))))),
      sec(7, "Required resources", list(p.required_resources)),
      sec(8, "Organizing committee", el("div", {class: "team"}, p.committee.map((m) => el("div", {}, el("b", {text: m.role}), m.responsibilities)))),
      sec(9, "Expected outcomes", list(p.expected_outcomes)));
  }
  if (state.proposal) $("out-proposal").replaceChildren(renderProposal(state.proposal));
  generator("proposal", "ai/proposal", renderProposal, () => ({}), () => { const a = $("pdf-link"); if (a) a.hidden = false; });
})();
