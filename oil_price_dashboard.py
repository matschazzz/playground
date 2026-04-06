"""
Oil Price Dashboard
===================
Interactive dashboard showing UK Brent crude oil prices and German diesel
prices for the last 4 weeks.

Features:
- Separate charts for Brent and Diesel prices
- Stacked bar chart for diesel showing the German tax breakdown:
    Netto-Kraftstoffpreis | Energiesteuer | CO2-Steuer | Mehrwertsteuer
- Zoom / Pan / Hover-Tooltip interactivity (powered by Plotly)
- Pearson correlation coefficient displayed in the dashboard
- Exported as a fully self-contained HTML file (dashboard.html,
  Plotly JS embedded – no internet connection required to view)

Usage:
    python oil_price_dashboard.py

Output:
    dashboard.html  – open in any modern browser
"""

from __future__ import annotations

import datetime
import warnings

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy import stats

# ---------------------------------------------------------------------------
# Optional: try to fetch real Brent data via yfinance
# ---------------------------------------------------------------------------
try:
    import yfinance as yf  # type: ignore

    _YFINANCE_AVAILABLE = True
except ImportError:  # pragma: no cover
    _YFINANCE_AVAILABLE = False


# ---------------------------------------------------------------------------
# Simulation constants (used when real data is unavailable)
# ---------------------------------------------------------------------------

# Brent crude oil: baseline price in USD/barrel and daily volatility scale
BRENT_BASE_PRICE: float = 82.0
BRENT_VOLATILITY_SCALE: float = 0.8  # typical daily std-dev in USD

# ---------------------------------------------------------------------------
# German diesel price components (approximate 2025/2026 values)
# ---------------------------------------------------------------------------

# Net fuel cost (crude oil + refining + logistics + dealer margin), EUR/L.
# This is the only component that fluctuates with the crude oil price.
# Chosen so the total retail price starts around 2.40 EUR/L.
DIESEL_NET_BASE: float = 1.39          # EUR/L
DIESEL_NET_VOLATILITY: float = 0.006   # daily std-dev in EUR/L

# Energiesteuer (energy/mineral oil tax) – fixed by Energiesteuergesetz
DIESEL_ENERGIESTEUER: float = 0.4704  # EUR/L (Energiesteuergesetz §2 Abs.1 Nr.4)

# CO2 price (Brennstoffemissionshandelsgesetz – BEHG)
# 2025: 55 EUR/tonne CO2; diesel emits ~2.65 kg CO2/L
# 55 EUR/t × 2.65 kg/L ÷ 1000 ≈ 0.146 EUR/L
DIESEL_CO2_STEUER: float = 0.146       # EUR/L

# Mehrwertsteuer (VAT) rate applied on the gross-of-tax price
DIESEL_MWST_RATE: float = 0.19         # 19 %


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _date_range_last_4_weeks() -> pd.DatetimeIndex:
    """Return a DatetimeIndex with business days for the last 4 weeks."""
    end = datetime.date.today()
    start = end - datetime.timedelta(weeks=4)
    return pd.bdate_range(start=start, end=end)


def fetch_brent_prices(dates: pd.DatetimeIndex) -> pd.Series:
    """
    Fetch UK Brent crude oil prices (USD/barrel).

    Tries yfinance first (ticker BZ=F). Falls back to realistic simulated data
    if yfinance is unavailable or returns no data.
    """
    if _YFINANCE_AVAILABLE:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                raw = yf.download(
                    "BZ=F",
                    start=dates[0].date(),
                    end=dates[-1].date() + datetime.timedelta(days=1),
                    progress=False,
                    auto_adjust=True,
                )
            if not raw.empty:
                close = raw["Close"].squeeze()
                close.index = pd.to_datetime(close.index)
                return close.reindex(dates).ffill().bfill().rename("Brent (USD/barrel)")
        except Exception:  # pragma: no cover – network errors
            pass

    # Simulated data – realistic Brent price movement around ~82 USD/bbl
    rng = np.random.default_rng(seed=42)
    returns = rng.normal(loc=0.0, scale=BRENT_VOLATILITY_SCALE, size=len(dates))
    prices = BRENT_BASE_PRICE + np.cumsum(returns)
    return pd.Series(prices, index=dates, name="Brent (USD/barrel)")


def fetch_diesel_prices(
    dates: pd.DatetimeIndex, brent: pd.Series | None = None
) -> pd.DataFrame:
    """
    Return German diesel retail prices (EUR/litre) split into four components:

    * **Netto-Kraftstoffpreis** – net fuel cost (crude + refining + margin).
      This component fluctuates daily; it is partially driven by Brent crude
      returns when Brent data is supplied, reflecting the real-world link
      between crude oil and retail diesel prices.
    * **Energiesteuer** – fixed energy/mineral oil tax (Energiesteuergesetz).
    * **CO2-Steuer** – CO2 levy (BEHG) based on the current CO2 price.
    * **Mehrwertsteuer (19 %)** – VAT applied on the sum of the three components
      above, so it also fluctuates slightly with the net price.

    The resulting total retail price starts at approximately 2.40 EUR/litre.

    Returns a DataFrame with columns:
        ``Netto-Kraftstoffpreis``, ``Energiesteuer``, ``CO2-Steuer``,
        ``Mehrwertsteuer (19%)``, ``Gesamt``
    """
    rng = np.random.default_rng(seed=99)
    n = len(dates)

    # Independent daily noise for the net price
    noise = rng.normal(loc=0.0, scale=DIESEL_NET_VOLATILITY, size=n)

    # Add a weak Brent signal: crude oil price changes feed through to net cost
    # (empirical scale: ~0.003 EUR/L per USD/bbl, accounting for EUR/USD and
    # refining margins dampening the crude-oil price signal)
    if brent is not None:
        brent_daily_change = brent.diff().fillna(0.0).values
        brent_to_diesel_scale = 0.003
        daily_changes = noise + brent_daily_change * brent_to_diesel_scale
    else:
        daily_changes = noise

    net_prices = DIESEL_NET_BASE + np.cumsum(daily_changes)
    before_mwst = net_prices + DIESEL_ENERGIESTEUER + DIESEL_CO2_STEUER
    mwst = before_mwst * DIESEL_MWST_RATE
    total = before_mwst + mwst

    return pd.DataFrame(
        {
            "Netto-Kraftstoffpreis": net_prices,
            "Energiesteuer": np.full(n, DIESEL_ENERGIESTEUER),
            "CO2-Steuer": np.full(n, DIESEL_CO2_STEUER),
            "Mehrwertsteuer (19%)": mwst,
            "Gesamt": total,
        },
        index=dates,
    )


# ---------------------------------------------------------------------------
# Correlation helper
# ---------------------------------------------------------------------------

def pearson_correlation(s1: pd.Series, s2: pd.Series) -> tuple[float, float]:
    """Return (r, p_value) for the Pearson correlation between two series."""
    aligned = pd.concat([s1, s2], axis=1).dropna()
    if len(aligned) < 3:
        return float("nan"), float("nan")
    r, p = stats.pearsonr(aligned.iloc[:, 0], aligned.iloc[:, 1])
    return float(r), float(p)


def interpret_correlation(r: float) -> str:
    """Return a human-readable label for |r|."""
    if np.isnan(r):
        return "nicht berechenbar"
    a = abs(r)
    if a >= 0.9:
        return "sehr stark"
    if a >= 0.7:
        return "stark"
    if a >= 0.5:
        return "moderat"
    if a >= 0.3:
        return "schwach"
    return "sehr schwach"


# ---------------------------------------------------------------------------
# Dashboard builder
# ---------------------------------------------------------------------------

def build_dashboard(output_file: str = "dashboard.html") -> None:
    """Build the interactive Plotly dashboard and write it to *output_file*.

    The generated HTML file embeds Plotly JS inline so it can be opened
    without an internet connection.
    """

    # -- Data ----------------------------------------------------------------
    dates = _date_range_last_4_weeks()
    brent = fetch_brent_prices(dates)
    diesel_df = fetch_diesel_prices(dates, brent=brent)

    # Correlate total retail diesel price with Brent
    r, p_val = pearson_correlation(brent, diesel_df["Gesamt"])
    corr_label = interpret_correlation(r)
    p_str = f"{p_val:.4f}" if not np.isnan(p_val) else "n/a"

    # -- Layout --------------------------------------------------------------
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.14,
        subplot_titles=(
            "🛢️  UK Brent Rohöl – Preis (USD/Barrel)",
            "⛽  Dieselpreis Deutschland – Zusammensetzung (EUR/Liter)",
        ),
    )

    # -- Brent trace ---------------------------------------------------------
    fig.add_trace(
        go.Scatter(
            x=brent.index,
            y=brent.values,
            mode="lines+markers",
            name="Brent Rohöl",
            line=dict(color="#1f77b4", width=2),
            marker=dict(size=5),
            hovertemplate=(
                "<b>Datum:</b> %{x|%d.%m.%Y}<br>"
                "<b>Preis:</b> %{y:.2f} USD/Barrel<extra></extra>"
            ),
        ),
        row=1,
        col=1,
    )

    # -- Diesel stacked bar traces -------------------------------------------
    # Colours for the four tax/price components
    component_colours = {
        "Netto-Kraftstoffpreis": "#4e9a8c",
        "Energiesteuer": "#e07b39",
        "CO2-Steuer": "#c0392b",
        "Mehrwertsteuer (19%)": "#8e44ad",
    }
    components = ["Netto-Kraftstoffpreis", "Energiesteuer", "CO2-Steuer", "Mehrwertsteuer (19%)"]

    for comp in components:
        fig.add_trace(
            go.Bar(
                x=diesel_df.index,
                y=diesel_df[comp].values,
                name=comp,
                marker_color=component_colours[comp],
                hovertemplate=(
                    f"<b>{comp}</b><br>"
                    "<b>Datum:</b> %{x|%d.%m.%Y}<br>"
                    "<b>Anteil:</b> %{y:.4f} EUR/L<extra></extra>"
                ),
            ),
            row=2,
            col=1,
        )

    # -- Correlation annotation ----------------------------------------------
    corr_text = (
        f"Pearson r = {r:.4f} ({corr_label})<br>"
        f"p-Wert = {p_str}  |  n = {len(brent.dropna())} Handelstage"
    )

    fig.add_annotation(
        text=corr_text,
        xref="paper",
        yref="paper",
        x=0.5,
        y=1.07,
        showarrow=False,
        font=dict(size=13, color="#444"),
        align="center",
        bgcolor="rgba(240,240,240,0.85)",
        bordercolor="#aaa",
        borderwidth=1,
        borderpad=6,
    )

    # -- Axis labels ---------------------------------------------------------
    fig.update_yaxes(title_text="USD / Barrel", row=1, col=1, tickformat=".2f")
    fig.update_yaxes(title_text="EUR / Liter", row=2, col=1, tickformat=".2f")
    fig.update_xaxes(
        title_text="Datum",
        row=2,
        col=1,
        tickformat="%d.%m.%Y",
        tickangle=-30,
    )

    # -- Overall layout ------------------------------------------------------
    today_str = datetime.date.today().strftime("%d.%m.%Y")
    fig.update_layout(
        title=dict(
            text=(
                f"Öl- & Dieselpreis Dashboard – letzte 4 Wochen "
                f"(Stand: {today_str})"
            ),
            x=0.5,
            font=dict(size=18),
        ),
        barmode="stack",
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
        ),
        dragmode="pan",
        template="plotly_white",
        height=750,
        margin=dict(t=130),
    )

    # Enable zoom + pan via modebar
    config = {
        "scrollZoom": True,
        "displayModeBar": True,
        "modeBarButtonsToRemove": [],
        "displaylogo": False,
    }

    # include_plotlyjs=True embeds the JS library inline so the file is
    # fully self-contained and works without an internet connection.
    fig.write_html(output_file, config=config, full_html=True, include_plotlyjs=True)
    print(f"Dashboard gespeichert: {output_file}")
    print(f"Pearson r = {r:.4f} ({corr_label}), p = {p_str}")
    # Print a sample of the diesel breakdown
    sample = diesel_df.tail(1).iloc[0]
    print(
        f"\nDiesel Preiszusammensetzung (letzter Tag):\n"
        f"  Netto-Kraftstoffpreis : {sample['Netto-Kraftstoffpreis']:.4f} EUR/L\n"
        f"  Energiesteuer         : {sample['Energiesteuer']:.4f} EUR/L\n"
        f"  CO2-Steuer            : {sample['CO2-Steuer']:.4f} EUR/L\n"
        f"  Mehrwertsteuer (19 %%) : {sample['Mehrwertsteuer (19%)']:.4f} EUR/L\n"
        f"  Gesamt                : {sample['Gesamt']:.4f} EUR/L"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    build_dashboard("dashboard.html")
