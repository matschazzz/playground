"""
generate_dashboard.py
Generates realistic UK Brent crude oil and German diesel price data
for the last 4 weeks, calculates Pearson correlation, and exports
a standalone interactive dashboard.html with embedded Plotly.js.

Run: python generate_dashboard.py
Output: dashboard.html
"""

import json
import math
import random
import datetime

# ── Reproducible seed for stable demo data ──────────────────────────────────
random.seed(42)

# ── Date range: last 28 days (skip weekends for commodity data) ─────────────
today = datetime.date.today()
dates_all = [today - datetime.timedelta(days=i) for i in range(27, -1, -1)]
# Keep Mon–Fri only (weekday() 0=Mon … 4=Fri)
dates = [d for d in dates_all if d.weekday() < 5]

n = len(dates)
date_strings = [d.strftime("%Y-%m-%d") for d in dates]

# ── Realistic Brent crude oil prices (USD/barrel) ───────────────────────────
# Starting around 82 USD, random walk with ±2 % daily moves
brent_prices = []
price = 82.0
for _ in range(n):
    change = random.uniform(-1.8, 1.8)
    price = round(max(70.0, min(95.0, price + change)), 2)
    brent_prices.append(price)

# ── Realistic German diesel prices (EUR/liter) ──────────────────────────────
# Starting around 1.72 €, loosely correlated with Brent (lag 0)
diesel_prices = []
d_price = 1.72
for i in range(n):
    # ~75 % driven by Brent movement, rest is local noise
    brent_effect = (brent_prices[i] - (brent_prices[i - 1] if i > 0 else 82.0)) * 0.007
    noise = random.uniform(-0.004, 0.004)
    d_price = round(max(1.45, min(2.10, d_price + brent_effect + noise)), 3)
    diesel_prices.append(d_price)

# ── Pearson correlation ──────────────────────────────────────────────────────
def pearson(x, y):
    n = len(x)
    mx = sum(x) / n
    my = sum(y) / n
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    den = math.sqrt(
        sum((xi - mx) ** 2 for xi in x) * sum((yi - my) ** 2 for yi in y)
    )
    return round(num / den, 4) if den != 0 else 0.0

correlation = pearson(brent_prices, diesel_prices)

def correlation_label(r):
    a = abs(r)
    if a >= 0.9:
        strength = "sehr stark"
    elif a >= 0.7:
        strength = "stark"
    elif a >= 0.5:
        strength = "moderat"
    elif a >= 0.3:
        strength = "schwach"
    else:
        strength = "sehr schwach"
    direction = "positiv" if r >= 0 else "negativ"
    return f"{strength} {direction}"

corr_text = correlation_label(correlation)

# ── Embed data as JSON ───────────────────────────────────────────────────────
chart_data = {
    "dates": date_strings,
    "brent": brent_prices,
    "diesel": diesel_prices,
    "correlation": correlation,
    "corr_text": corr_text,
    "generated": today.strftime("%d.%m.%Y"),
}

# ── HTML template ────────────────────────────────────────────────────────────
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Öl &amp; Diesel Dashboard</title>
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0f172a;
    color: #e2e8f0;
    min-height: 100vh;
  }
  header {
    background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
    border-bottom: 1px solid #334155;
    padding: 1rem 1.5rem;
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }
  header h1 {
    font-size: clamp(1rem, 4vw, 1.4rem);
    font-weight: 700;
    background: linear-gradient(90deg, #38bdf8, #818cf8);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }
  header .subtitle {
    font-size: 0.75rem;
    color: #94a3b8;
    margin-top: 2px;
  }
  .icon { font-size: 1.8rem; }
  main { padding: 1rem; max-width: 1200px; margin: 0 auto; }

  /* KPI cards */
  .kpi-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 0.75rem;
    margin-bottom: 1rem;
  }
  .kpi {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 0.85rem 1rem;
    text-align: center;
  }
  .kpi .label { font-size: 0.7rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; }
  .kpi .value { font-size: 1.4rem; font-weight: 700; margin-top: 4px; }
  .kpi .change { font-size: 0.75rem; margin-top: 2px; }
  .pos { color: #34d399; }
  .neg { color: #f87171; }
  .neu { color: #94a3b8; }

  /* Correlation banner */
  .corr-banner {
    background: linear-gradient(135deg, #1e293b, #0f2044);
    border: 1px solid #3b82f6;
    border-radius: 12px;
    padding: 0.85rem 1.25rem;
    margin-bottom: 1rem;
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.5rem;
  }
  .corr-badge {
    background: #3b82f6;
    color: #fff;
    font-size: 1.2rem;
    font-weight: 800;
    padding: 0.25rem 0.75rem;
    border-radius: 8px;
  }
  .corr-desc { font-size: 0.85rem; color: #cbd5e1; flex: 1; min-width: 180px; }
  .corr-desc strong { color: #e2e8f0; }

  /* Charts */
  .chart-card {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 0.5rem 0.25rem;
    margin-bottom: 1rem;
    overflow: hidden;
  }
  .chart-title {
    font-size: 0.85rem;
    font-weight: 600;
    color: #94a3b8;
    padding: 0.5rem 1rem 0;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .plotly-graph-div { width: 100% !important; }

  footer {
    text-align: center;
    padding: 1.5rem;
    font-size: 0.7rem;
    color: #475569;
    border-top: 1px solid #1e293b;
  }
</style>
</head>
<body>
<header>
  <span class="icon">🛢️</span>
  <div>
    <h1>Öl &amp; Diesel Preisdashboard</h1>
    <div class="subtitle">Letzte 4 Wochen · Stand: GENERATED_DATE</div>
  </div>
</header>

<main>
  <div class="kpi-grid" id="kpiGrid"></div>
  <div class="corr-banner" id="corrBanner"></div>
  <div class="chart-card">
    <div class="chart-title">🛢️ UK Brent Rohöl (USD / Barrel)</div>
    <div id="chartBrent"></div>
  </div>
  <div class="chart-card">
    <div class="chart-title">⛽ Diesel Deutschland (EUR / Liter)</div>
    <div id="chartDiesel"></div>
  </div>
</main>

<footer>Daten simuliert für Demo-Zwecke · Generiert am GENERATED_DATE</footer>

<script>
const DATA = CHART_DATA_JSON;

// ── KPI cards ────────────────────────────────────────────────────────────────
function kpiCard(label, value, unit, change) {
  const dir = change > 0 ? "pos" : change < 0 ? "neg" : "neu";
  const arrow = change > 0 ? "▲" : change < 0 ? "▼" : "–";
  return `<div class="kpi">
    <div class="label">${label}</div>
    <div class="value">${value} <span style="font-size:0.8rem;color:#94a3b8">${unit}</span></div>
    <div class="change ${dir}">${arrow} ${Math.abs(change).toFixed(2)} ${unit}</div>
  </div>`;
}

const bLast  = DATA.brent[DATA.brent.length - 1];
const bFirst = DATA.brent[0];
const dLast  = DATA.diesel[DATA.diesel.length - 1];
const dFirst = DATA.diesel[0];
const bMin   = Math.min(...DATA.brent);
const bMax   = Math.max(...DATA.brent);
const dMin   = Math.min(...DATA.diesel);
const dMax   = Math.max(...DATA.diesel);

document.getElementById("kpiGrid").innerHTML =
  kpiCard("Brent aktuell", bLast.toFixed(2), "USD", bLast - bFirst) +
  kpiCard("Brent Tief", bMin.toFixed(2), "USD", 0) +
  kpiCard("Brent Hoch", bMax.toFixed(2), "USD", 0) +
  kpiCard("Diesel aktuell", dLast.toFixed(3), "€", dLast - dFirst) +
  kpiCard("Diesel Tief", dMin.toFixed(3), "€", 0) +
  kpiCard("Diesel Hoch", dMax.toFixed(3), "€", 0);

// ── Correlation banner ───────────────────────────────────────────────────────
document.getElementById("corrBanner").innerHTML = `
  <span>📊 Pearson-Korrelation</span>
  <span class="corr-badge">${DATA.correlation}</span>
  <span class="corr-desc">
    <strong>${DATA.corr_text}</strong> Korrelation zwischen Brent-Rohöl und Dieselpreisen
    in Deutschland. Werte nahe +1 bedeuten, dass beide Preise fast gleichzeitig steigen und fallen.
  </span>`;

// ── Shared Plotly config ─────────────────────────────────────────────────────
const LAYOUT_BASE = {
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor:  "rgba(0,0,0,0)",
  font: { color: "#94a3b8", size: 11 },
  margin: { l: 55, r: 20, t: 20, b: 55 },
  xaxis: {
    type: "date",
    gridcolor: "#1e293b",
    linecolor: "#334155",
    tickcolor: "#334155",
    tickformat: "%d.%m.",
    tickangle: -30,
    rangeslider: { visible: false },
    rangeselector: {
      bgcolor: "#1e293b",
      activecolor: "#3b82f6",
      bordercolor: "#334155",
      font: { color: "#94a3b8", size: 10 },
      buttons: [
        { count: 7,  label: "1W",  step: "day", stepmode: "backward" },
        { count: 14, label: "2W",  step: "day", stepmode: "backward" },
        { count: 28, label: "4W",  step: "day", stepmode: "backward" },
        { step: "all", label: "All" }
      ]
    }
  },
  yaxis: {
    gridcolor: "#1e293b",
    linecolor: "#334155",
    tickcolor: "#334155",
  },
  hovermode: "x unified",
  dragmode: "zoom",
};

const CONFIG = {
  responsive: true,
  displayModeBar: true,
  modeBarButtonsToAdd: ["toggleSpikelines"],
  modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d"],
  displaylogo: false,
  scrollZoom: true,
  toImageButtonOptions: { format: "png", filename: "oil_diesel_dashboard" },
};

// ── Brent chart ──────────────────────────────────────────────────────────────
const brentTrace = {
  x: DATA.dates,
  y: DATA.brent,
  type: "scatter",
  mode: "lines+markers",
  name: "Brent (USD/Barrel)",
  line:   { color: "#38bdf8", width: 2.5, shape: "spline" },
  marker: { color: "#38bdf8", size: 5 },
  fill: "tozeroy",
  fillcolor: "rgba(56,189,248,0.08)",
  hovertemplate: "<b>%{x|%d.%m.%Y}</b><br>Brent: <b>%{y:.2f} USD</b><extra></extra>",
};

Plotly.newPlot("chartBrent", [brentTrace],
  { ...LAYOUT_BASE,
    yaxis: { ...LAYOUT_BASE.yaxis, title: { text: "USD / Barrel", standoff: 8 } }
  }, CONFIG);

// ── Diesel chart ─────────────────────────────────────────────────────────────
const dieselTrace = {
  x: DATA.dates,
  y: DATA.diesel,
  type: "scatter",
  mode: "lines+markers",
  name: "Diesel (€/Liter)",
  line:   { color: "#f59e0b", width: 2.5, shape: "spline" },
  marker: { color: "#f59e0b", size: 5 },
  fill: "tozeroy",
  fillcolor: "rgba(245,158,11,0.08)",
  hovertemplate: "<b>%{x|%d.%m.%Y}</b><br>Diesel: <b>%{y:.3f} €</b><extra></extra>",
};

Plotly.newPlot("chartDiesel", [dieselTrace],
  { ...LAYOUT_BASE,
    yaxis: { ...LAYOUT_BASE.yaxis, title: { text: "EUR / Liter", standoff: 8 } }
  }, CONFIG);

// ── Responsive resize ────────────────────────────────────────────────────────
window.addEventListener("resize", () => {
  Plotly.relayout("chartBrent",  { autosize: true });
  Plotly.relayout("chartDiesel", { autosize: true });
});
</script>
</body>
</html>
"""

# ── Fill template ────────────────────────────────────────────────────────────
html = HTML_TEMPLATE.replace("CHART_DATA_JSON", json.dumps(chart_data, ensure_ascii=False))
html = html.replace("GENERATED_DATE", today.strftime("%d.%m.%Y"))

output_path = "dashboard.html"
with open(output_path, "w", encoding="utf-8") as f:
    f.write(html)

print(f"✅  Dashboard gespeichert: {output_path}")
print(f"   Datenpunkte : {n} Handelstage")
print(f"   Brent       : {min(brent_prices):.2f} – {max(brent_prices):.2f} USD/Barrel")
print(f"   Diesel      : {min(diesel_prices):.3f} – {max(diesel_prices):.3f} EUR/Liter")
print(f"   Pearson r   : {correlation} ({corr_text})")
