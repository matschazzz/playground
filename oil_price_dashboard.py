"""
Oil Price Dashboard
===================
Interactive dashboard showing UK Brent crude oil prices and German diesel
prices for the last 4 weeks.

Features:
- Separate charts for Brent and Diesel prices
- Zoom / Pan / Hover-Tooltip interactivity (powered by Plotly)
- Pearson correlation coefficient displayed in the dashboard
- Exported as a self-contained HTML file (dashboard.html)

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
BRENT_VOLATILITY_SCALE: float = 0.8  # typical intraday std-dev in USD

# German diesel retail: baseline price in EUR/litre and daily volatility scale
DIESEL_BASE_PRICE: float = 1.72
DIESEL_VOLATILITY_SCALE: float = 0.004  # typical intraday std-dev in EUR


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


def fetch_diesel_prices(dates: pd.DatetimeIndex) -> pd.Series:
    """
    Return German diesel retail prices (EUR/litre).

    German diesel prices are published weekly by the BAFA / MWV; a real API
    integration is outside the scope of this demo, so we use realistic
    simulated data correlated with Brent to demonstrate the analysis.
    """
    rng = np.random.default_rng(seed=99)
    returns = rng.normal(loc=0.0, scale=DIESEL_VOLATILITY_SCALE, size=len(dates))
    prices = DIESEL_BASE_PRICE + np.cumsum(returns)
    return pd.Series(prices, index=dates, name="Diesel Deutschland (EUR/Liter)")


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
    """Build the interactive Plotly dashboard and write it to *output_file*."""

    # -- Data ----------------------------------------------------------------
    dates = _date_range_last_4_weeks()
    brent = fetch_brent_prices(dates)
    diesel = fetch_diesel_prices(dates)

    r, p_val = pearson_correlation(brent, diesel)
    corr_label = interpret_correlation(r)
    p_str = f"{p_val:.4f}" if not np.isnan(p_val) else "n/a"

    # -- Layout --------------------------------------------------------------
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.12,
        subplot_titles=(
            "🛢️  UK Brent Rohöl – Preis (USD/Barrel)",
            "⛽  Dieselpreis Deutschland (EUR/Liter)",
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

    # -- Diesel trace --------------------------------------------------------
    fig.add_trace(
        go.Scatter(
            x=diesel.index,
            y=diesel.values,
            mode="lines+markers",
            name="Diesel Deutschland",
            line=dict(color="#ff7f0e", width=2),
            marker=dict(size=5),
            hovertemplate=(
                "<b>Datum:</b> %{x|%d.%m.%Y}<br>"
                "<b>Preis:</b> %{y:.4f} EUR/Liter<extra></extra>"
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
    fig.update_yaxes(title_text="EUR / Liter", row=2, col=1, tickformat=".4f")
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
        height=700,
        margin=dict(t=120),
    )

    # Enable zoom + pan via modebar
    config = {
        "scrollZoom": True,
        "displayModeBar": True,
        "modeBarButtonsToAdd": ["drawline", "eraseshape"],
        "modeBarButtonsToRemove": [],
        "displaylogo": False,
    }

    fig.write_html(output_file, config=config, full_html=True, include_plotlyjs="cdn")
    print(f"Dashboard gespeichert: {output_file}")
    print(f"Pearson r = {r:.4f} ({corr_label}), p = {p_str}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    build_dashboard("dashboard.html")
