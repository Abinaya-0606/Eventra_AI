/* Editable budget table shared by AI Studio and the per-event AI tools page.
   BudgetOptimizer.render(data, {onSave}) returns a DOM node. Totals are recalculated live in the browser
   for display only; the server recalculates everything when you save. */
(function () {
  const {el, money} = App;
  window.BudgetOptimizer = {
    render(data, opts = {}) {
      const budget = Number(data.budget), original = data.items.map((i) => Number(i.amount));
      const inputs = data.items.map((item, idx) => {
        const input = el("input", {type: "number", min: "0", step: "0.01", value: String(item.amount), class: "amt",
          "aria-label": `${item.label} amount in rupees`});
        input.addEventListener("input", update);
        return input;
      });
      const pills = data.items.map(() => el("span", {class: "muted"}));
      const totalCell = el("td"), remainCell = el("td"), statusPill = el("span", {class: "pill"});
      const remainLabel = el("td");
      const message = el("p", {class: "inline-msg", role: "status"});

      const value = (i) => Math.max(parseFloat(inputs[i].value) || 0, 0);
      function update() {
        const total = inputs.reduce((s, _, i) => s + value(i), 0);
        const remaining = budget - total;
        data.items.forEach((_, i) => (pills[i].textContent = budget ? `${((value(i) / budget) * 100).toFixed(1)}%` : "–"));
        totalCell.textContent = money(total);
        remainLabel.textContent = remaining >= 0 ? "Remaining" : "Over budget by";
        remainCell.textContent = money(Math.abs(remaining));
        statusPill.className = "pill " + (remaining >= 0 ? "ok" : "bad");
        statusPill.textContent = remaining >= 0 ? "Within budget" : "Over budget";
      }

      const rows = data.items.map((item, i) => el("tr", {},
        el("td", {}, el("b", {text: item.label}), item.note ? el("small", {class: "muted block", text: item.note}) : null),
        el("td", {}, pills[i]), el("td", {}, inputs[i])));
      const table = el("div", {class: "table-wrap"}, el("table", {class: "table budget-table"},
        el("thead", {}, el("tr", {}, el("th", {text: "Category"}), el("th", {text: "Share"}), el("th", {text: "Amount (₹)"}))),
        el("tbody", {}, rows),
        el("tfoot", {}, el("tr", {}, el("td", {text: "Total"}), el("td"), totalCell),
          el("tr", {}, el("td", {text: "Your budget"}), el("td"), el("td", {text: money(budget)})),
          el("tr", {}, remainLabel, el("td"), remainCell))));

      const reset = el("button", {type: "button", class: "btn soft sm", text: "Reset to AI suggestion"});
      reset.addEventListener("click", () => { inputs.forEach((n, i) => (n.value = String(original[i]))); message.textContent = ""; update(); });
      const bar = el("div", {class: "res-actions"}, statusPill, reset);
      if (opts.onSave) {
        const save = el("button", {type: "button", class: "btn primary sm", text: "Save breakdown"});
        save.addEventListener("click", async () => {
          save.disabled = true; message.className = "inline-msg"; message.textContent = "Saving…";
          try {
            const items = {};
            data.items.forEach((item, i) => (items[item.category] = value(i)));
            await opts.onSave(items);
            message.className = "inline-msg ok"; message.textContent = "Saved."; App.toast("Budget breakdown saved.", "success");
          } catch (ex) { message.className = "inline-msg bad"; message.textContent = ex.message; }
          finally { save.disabled = false; }
        });
        bar.append(save);
      }
      update();
      return el("div", {}, table, bar, message);
    },
  };
})();
