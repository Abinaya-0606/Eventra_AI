/* Budget calculator page. The Python backend validates and calculates everything. */
(function () {
  const $ = (id) => document.getElementById(id);
  const form = $("budget-form");
  const venues = JSON.parse(form.dataset.venues);   // display-only hints; same data the backend uses

  function renderVenueInfo() {
    const v = venues[$("venue").value];
    $("venue-info").replaceChildren(
      App.el("span", {text: `Capacity: ${v.capacity} participants`}),
      App.el("span", {text: `Venue cost: ${App.money(v.cost).replace(".00", "")}`}));
  }
  $("venue").addEventListener("change", renderVenueInfo);
  renderVenueInfo();

  let busy = false;
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (busy) return;
    const err = $("budget-error"), btn = $("calc"), participants = $("participants").value.trim();
    err.hidden = true;
    if (!participants) { err.textContent = "Please enter the number of participants."; err.hidden = false; $("participants").focus(); return; }

    busy = true; btn.disabled = true; btn.textContent = "Calculating…";
    try {
      const d = await App.postJSON("/api/budget", {
        venue: $("venue").value, participants,
        refreshments: $("refreshments").checked, participation_kits: $("kits").checked,
      });
      $("r-venue").textContent = App.money(d.venue_cost);
      $("r-ref").textContent = App.money(d.refreshment_cost);
      $("r-kit").textContent = App.money(d.kit_cost);
      $("r-sub").textContent = App.money(d.subtotal);
      $("r-con").textContent = App.money(d.contingency);
      $("r-total").textContent = App.money(d.total);
      $("r-approver").textContent = d.approver;
      $("approver-box").classList.toggle("principal", d.approver === "Principal");
      $("result-empty").hidden = true; $("result").hidden = false;
    } catch (ex) {
      err.textContent = ex.message; err.hidden = false;
      $("result").hidden = true; $("result-empty").hidden = false;
    } finally {
      busy = false; btn.disabled = false; btn.textContent = "Calculate Budget";
    }
  });
})();
