# playground

## Oil Price Dashboard 📊

An interactive Python dashboard that visualises **UK Brent crude oil prices** and
**German diesel retail prices** for the last 4 weeks, including a
**Pearson correlation analysis**.

### Features

| Feature | Details |
|---|---|
| 📈 Combined line chart | Brent crude (left axis, USD/barrel) and **five diesel lines** (right axis, EUR/litre) in a single chart: Netto-Kraftstoffpreis · Energiesteuer · CO2-Steuer · Mehrwertsteuer · Gesamt |
| 💶 Diesel data source | Real weekly data from the **EU Weekly Oil Bulletin** (European Commission) with simulation fallback; total ≈ 2.40 €/L |
| 🛢️ Brent data source | Real daily data via **yfinance** (BZ=F) with simulation fallback |
| 🔍 Zoom / Pan | Mouse-wheel zoom + drag-to-pan enabled by default |
| 🖱️ Hover tooltips | Price + date shown on mouse-over for all series |
| 📐 Correlation | Pearson *r* and p-value (Brent ↔ Diesel Gesamt) displayed at the top |
| 💾 Output | Fully self-contained `dashboard.html` – Plotly JS embedded, no internet required to view |

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
- **yfinance** – optional real Brent price feed (BZ=F)
- **requests** – fetch EU Oil Bulletin for real German diesel prices
- **openpyxl** – parse the Oil Bulletin Excel workbook
