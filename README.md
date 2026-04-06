# playground

## Oil Price Dashboard 📊

An interactive Python dashboard that visualises **UK Brent crude oil prices** and
**German diesel retail prices** for the last 4 weeks, including a
**Pearson correlation analysis**.

### Features

| Feature | Details |
|---|---|
| 📈 Brent chart | Daily USD/barrel – real data via *yfinance* or realistic simulation |
| ⛽ Diesel chart | Stacked bar showing daily breakdown: Netto-Kraftstoffpreis · Energiesteuer (0.4704 €/L) · CO2-Steuer (~0.15 €/L) · Mehrwertsteuer (19%) – total ≈ 2.40 €/L |
| 🔍 Zoom / Pan | Mouse-wheel zoom + drag-to-pan enabled by default |
| 🖱️ Hover tooltips | Price + date shown on mouse-over |
| 📐 Correlation | Pearson *r* and p-value displayed at the top of the dashboard |
| 💾 Output | Self-contained `dashboard.html` – open in any modern browser |

### Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Generate the dashboard
python oil_price_dashboard.py

# 3. Open in browser
open dashboard.html   # macOS
xdg-open dashboard.html  # Linux
start dashboard.html  # Windows
```

### File Overview

| File | Purpose |
|---|---|
| `oil_price_dashboard.py` | Main application |
| `requirements.txt` | Python dependencies |
| `dashboard.html` | Generated interactive dashboard (git-ignored) |

### Dependencies

- **pandas** – data manipulation
- **numpy** – numerical operations
- **plotly** – interactive charts
- **scipy** – Pearson correlation (stats)
- **yfinance** – optional real Brent price feed
