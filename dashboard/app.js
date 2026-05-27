// Dashboard Pokémon TCG Weekly Strategy
// Legge data/latest.json e ricostruisce trend storico da data/history/*.json
// Tutto client-side: nessun backend, gira su GitHub Pages.

const DATA_LATEST_URL = "../data/latest.json";
// Lista snapshot storici da provare. La generiamo client-side ricostruendo
// le ultime 26 settimane ISO retrocedendo dalla data corrente.
function buildHistoryPaths(weeks = 26) {
  const paths = [];
  const now = new Date();
  for (let i = 0; i < weeks; i++) {
    const d = new Date(now);
    d.setDate(d.getDate() - i * 7);
    const iso = isoWeek(d);
    paths.push(`../data/history/${iso.year}-W${String(iso.week).padStart(2, "0")}.json`);
  }
  return paths;
}

function isoWeek(date) {
  const target = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const dayNum = (target.getUTCDay() + 6) % 7;
  target.setUTCDate(target.getUTCDate() - dayNum + 3);
  const firstThursday = new Date(Date.UTC(target.getUTCFullYear(), 0, 4));
  const week = 1 + Math.round(((target - firstThursday) / 86400000 - 3 + ((firstThursday.getUTCDay() + 6) % 7)) / 7);
  return { year: target.getUTCFullYear(), week };
}

async function fetchJsonOrNull(url) {
  try {
    const r = await fetch(url, { cache: "no-cache" });
    if (!r.ok) return null;
    return await r.json();
  } catch {
    return null;
  }
}

function renderSummary(data) {
  document.getElementById("generated-at").textContent =
    `Aggiornato: ${new Date(data.generated_at).toLocaleString("it-IT")} — settimana ${data.iso_week}`;
  const chips = document.getElementById("summary-chips");
  const s = data.summary;
  chips.innerHTML = `
    <span class="chip chip-preorder">${s.preorder_count} PREORDER</span>
    <span class="chip chip-accumulate">${s.accumulate_count} ACCUMULATE</span>
    <span class="chip chip-hold">${s.hold_count} HOLD</span>
    <span class="chip chip-avoid">${s.avoid_count} AVOID</span>
  `;
}

function renderTopActions(data) {
  const container = document.getElementById("top-actions");
  const top = data.summary.top_action || [];
  if (top.length === 0) {
    container.innerHTML = `<p class="muted">Nessuna azione PREORDER/ACCUMULATE in evidenza questa settimana.</p>`;
    return;
  }
  container.innerHTML = top.map(t => `
    <div class="card">
      <div class="card-header">
        <span class="card-title">${t.set_name}</span>
        <span class="card-score">${t.score}</span>
      </div>
      <div class="card-meta">
        <span class="badge badge-${t.category}">${t.category}</span>
        · ${humanType(t.product_type)} · budget ${t.budget_allocation_pct}%
      </div>
      <div class="card-rationale">${t.rationale}</div>
    </div>
  `).join("");
}

function humanType(t) {
  return ({
    booster_box: "Booster Box",
    booster_bundle: "Booster Bundle",
    etb: "ETB",
    special_set: "Special Set",
    collection_box: "Collection Box",
    premium_collection: "Premium Collection",
  })[t] || t;
}

let gridInstance = null;
function renderTable(recs) {
  const container = document.getElementById("rec-table");
  container.innerHTML = "";
  gridInstance = new gridjs.Grid({
    columns: [
      { name: "Categoria", formatter: c => gridjs.html(`<span class="badge badge-${c}">${c}</span>`) },
      "Set",
      { name: "Tipo", formatter: humanType },
      { name: "Score", sort: true },
      { name: "Budget %", sort: true },
      { name: "Prezzo €", sort: true },
      { name: "Premium %", sort: true },
      "Driver / motivazione",
    ],
    data: recs.map(r => [
      r.category,
      r.set_name,
      r.product_type,
      r.score,
      r.budget_allocation_pct,
      r.metadata?.current_price_eur ?? "—",
      r.metadata?.premium_over_msrp_pct ?? "—",
      r.rationale,
    ]),
    sort: true,
    search: true,
    pagination: { limit: 20 },
    style: { table: { width: "100%" } },
  }).render(container);
}

function applyFilters(allRecs) {
  const cat = document.getElementById("filter-category").value;
  const type = document.getElementById("filter-type").value;
  const filtered = allRecs.filter(r =>
    (!cat || r.category === cat) &&
    (!type || r.product_type === type)
  );
  renderTable(filtered);
}

async function loadHistoryAndRenderTrend() {
  const paths = buildHistoryPaths(12);
  const results = await Promise.all(paths.map(fetchJsonOrNull));
  const points = [];
  for (let i = paths.length - 1; i >= 0; i--) {
    const d = results[i];
    if (!d) continue;
    const recs = d.recommendations || [];
    const avgPreorder = avgScore(recs.filter(r => r.category === "PREORDER"));
    const avgAccumulate = avgScore(recs.filter(r => r.category === "ACCUMULATE"));
    points.push({
      label: d.iso_week,
      preorder: avgPreorder,
      accumulate: avgAccumulate,
    });
  }
  drawTrendChart(points);
}

function avgScore(arr) {
  if (arr.length === 0) return null;
  return Math.round(arr.reduce((a, b) => a + b.score, 0) / arr.length * 10) / 10;
}

function drawTrendChart(points) {
  const ctx = document.getElementById("trend-chart");
  if (!points.length) {
    ctx.replaceWith(Object.assign(document.createElement("p"),
      { className: "muted", textContent: "Storico non ancora disponibile — disponibile dopo qualche run." }));
    return;
  }
  new Chart(ctx, {
    type: "line",
    data: {
      labels: points.map(p => p.label),
      datasets: [
        { label: "Avg score PREORDER", data: points.map(p => p.preorder), borderColor: "#ef4444", backgroundColor: "rgba(239,68,68,0.2)", tension: 0.3 },
        { label: "Avg score ACCUMULATE", data: points.map(p => p.accumulate), borderColor: "#f59e0b", backgroundColor: "rgba(245,158,11,0.2)", tension: 0.3 },
      ],
    },
    options: {
      responsive: true,
      plugins: { legend: { labels: { color: "#e2e8f0" } } },
      scales: {
        x: { ticks: { color: "#94a3b8" }, grid: { color: "#334155" } },
        y: { ticks: { color: "#94a3b8" }, grid: { color: "#334155" }, suggestedMin: 0, suggestedMax: 100 },
      },
    },
  });
}

(async function main() {
  const data = await fetchJsonOrNull(DATA_LATEST_URL);
  if (!data) {
    document.getElementById("generated-at").textContent = "⚠️ Impossibile caricare data/latest.json — verifica che la pipeline sia stata eseguita almeno una volta.";
    return;
  }
  renderSummary(data);
  renderTopActions(data);
  renderTable(data.recommendations);
  document.getElementById("filter-category").addEventListener("change", () => applyFilters(data.recommendations));
  document.getElementById("filter-type").addEventListener("change", () => applyFilters(data.recommendations));
  loadHistoryAndRenderTrend();
})();
