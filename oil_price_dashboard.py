"""
Oil Price Dashboard
===================
Interactive dashboard showing UK Brent crude oil prices and German diesel
prices for the last 4 weeks.

Features:
- Single line chart showing Brent crude (left axis, USD/barrel) alongside
  each diesel price component as its own line (right axis, EUR/litre):
    Netto-Kraftstoffpreis | Energiesteuer | CO2-Steuer | Mehrwertsteuer | Gesamt
- Real data sources:
    * Brent crude: FRED / EIA (primary), yfinance (secondary), simulation fallback
      - FRED series DCOILBRENTEU published by the U.S. Energy Information
        Administration via the Federal Reserve Bank of St. Louis
        https://fred.stlouisfed.org/series/DCOILBRENTEU
    * German diesel: EU Weekly Oil Bulletin (European Commission, DG Energy)
        https://energy.ec.europa.eu/data-and-analysis/weekly-oil-bulletin_en
      with simulation fallback
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
import io
import warnings

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy import stats

# ---------------------------------------------------------------------------
# Optional imports
# ---------------------------------------------------------------------------
try:
    import yfinance as yf  # type: ignore

    _YFINANCE_AVAILABLE = True
except ImportError:  # pragma: no cover
    _YFINANCE_AVAILABLE = False

try:
    import requests as _requests  # type: ignore

    _REQUESTS_AVAILABLE = True
except ImportError:  # pragma: no cover
    _REQUESTS_AVAILABLE = False


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


def _fetch_fred_brent(dates: pd.DatetimeIndex) -> pd.Series | None:
    """
    Fetch UK Brent crude oil spot prices (USD/barrel) from FRED.

    Source: U.S. Energy Information Administration (EIA), distributed by the
    Federal Reserve Bank of St. Louis (FRED).
    Series: DCOILBRENTEU – Crude Oil Prices: Brent – Europe, USD per Barrel.
    URL: https://fred.stlouisfed.org/series/DCOILBRENTEU

    Returns a daily Series aligned to *dates* on success, or None when the
    data cannot be retrieved.
    """
    if not _REQUESTS_AVAILABLE:
        return None

    # Request only the range we need; include a proper User-Agent so that
    # the FRED web server does not mistake the request for bot traffic.
    observation_start = dates[0].date().isoformat()
    observation_end = dates[-1].date().isoformat()
    url = (
        "https://fred.stlouisfed.org/graph/fredgraph.csv"
        f"?id=DCOILBRENTEU&cosd={observation_start}&coed={observation_end}"
    )
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) "
            "Gecko/20100101 Firefox/125.0"
        ),
        "Accept": "text/csv,text/plain,*/*",
    }
    try:
        resp = _requests.get(url, headers=headers, timeout=20)
        if resp.status_code != 200:
            return None

        df = pd.read_csv(io.StringIO(resp.text))
        if df.shape[1] != 2:  # guard against HTML / unexpected responses
            return None
        df.columns = ["date", "price"]
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"]).set_index("date")
        # FRED uses "." for missing observations; convert to NaN
        df["price"] = pd.to_numeric(df["price"], errors="coerce")
        series = df["price"].dropna()
        if series.empty:
            return None
        series = series.reindex(dates).ffill().bfill()
        if series.isna().all():
            return None
        series.name = "Brent (USD/barrel)"
        return series
    except Exception:  # pragma: no cover – network errors
        pass
    return None


def fetch_brent_prices(dates: pd.DatetimeIndex) -> pd.Series:
    """
    Fetch UK Brent crude oil prices (USD/barrel).

    Data-source priority:
    1. **FRED / EIA** – official daily spot prices published by the U.S. Energy
       Information Administration (EIA) via the Federal Reserve Bank of St.
       Louis (FRED), series DCOILBRENTEU.
       https://fred.stlouisfed.org/series/DCOILBRENTEU
    2. **yfinance** (BZ=F) – ICE Brent futures via Yahoo Finance, used as a
       secondary source when FRED is unavailable.
    3. **Simulated data** – realistic random-walk around ~82 USD/bbl, used only
       when both network sources are unreachable.
    """
    # 1. Official source: FRED / EIA
    print("Brent: versuche FRED/EIA (DCOILBRENTEU)...")
    fred_data = _fetch_fred_brent(dates)
    if fred_data is not None:
        print("Brent: FRED/EIA-Daten erfolgreich geladen.")
        return fred_data
    print("Brent: FRED/EIA nicht verfügbar.")

    # 2. Secondary source: yfinance
    if _YFINANCE_AVAILABLE:
        print("Brent: versuche yfinance (BZ=F)...")
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
                print("Brent: yfinance-Daten erfolgreich geladen.")
                return close.reindex(dates).ffill().bfill().rename("Brent (USD/barrel)")
        except Exception:  # pragma: no cover – network errors
            pass
        print("Brent: yfinance nicht verfügbar.")

    # 3. Simulated data – realistic Brent price movement around ~82 USD/bbl
    print("Brent: WARNUNG – verwende simulierte Daten (keine Echtdaten verfügbar).")
    rng = np.random.default_rng(seed=42)
    returns = rng.normal(loc=0.0, scale=BRENT_VOLATILITY_SCALE, size=len(dates))
    prices = BRENT_BASE_PRICE + np.cumsum(returns)
    return pd.Series(prices, index=dates, name="Brent (USD/barrel)")


def _eu_oil_bulletin_urls() -> list[str]:
    """
    Return a list of candidate EU Weekly Oil Bulletin URLs to try, in order of
    preference (most recent month first, going back up to 6 months).

    The European Commission publishes the Excel workbook with a date-stamped
    path that is updated roughly once a month.  Because there is no single
    "latest" permalink, we generate URLs for the current and the five preceding
    months and try each one until a successful HTTP 200 response is received.
    """
    today = datetime.date.today()
    urls: list[str] = []
    year, month = today.year, today.month
    for _ in range(6):
        urls.append(
            f"https://energy.ec.europa.eu/system/files/"
            f"{year}-{month:02d}/Oil_Bulletin_Prices_History.xlsx"
        )
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return urls


def _fetch_eu_oil_bulletin_diesel(dates: pd.DatetimeIndex) -> pd.Series | None:
    """
    Try to fetch official weekly German diesel consumer prices (EUR/litre,
    tax-inclusive) from the EU Weekly Oil Bulletin Excel file published by the
    European Commission (DG Energy).

    Source: https://energy.ec.europa.eu/data-and-analysis/weekly-oil-bulletin_en

    The URL of the Excel workbook is date-stamped and updated monthly.  This
    function tries candidate URLs for the current and preceding months so that
    the dashboard always fetches the most recently published file without
    requiring a manual URL update.

    Returns a daily Series (forward-filled from weekly values) on success, or
    None if the data cannot be retrieved.
    """
    if not _REQUESTS_AVAILABLE:
        return None

    # Include a proper User-Agent so the Commission's server does not mistake
    # the request for bot traffic.  The Excel file is large (~3 MB), so allow
    # a generous timeout.
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) "
            "Gecko/20100101 Firefox/125.0"
        ),
        "Accept": (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,"
            "application/vnd.ms-excel,*/*"
        ),
    }

    resp = None
    for url in _eu_oil_bulletin_urls():
        try:
            r = _requests.get(url, headers=headers, timeout=30)
            if r.status_code == 200:
                resp = r
                print(f"Diesel: EU Oil Bulletin-Datei heruntergeladen ({url})")
                break
        except Exception:  # pragma: no cover – network errors
            continue

    if resp is None:
        return None

    try:
        xl = pd.read_excel(
            io.BytesIO(resp.content),
            sheet_name=None,  # load all sheets so we can search
            header=None,
        )

        # Look for a sheet that contains German diesel consumer prices.
        # The sheet is typically named "Prices with taxes, per CTY" or similar.
        for sheet_name, df in xl.items():
            if "tax" not in str(sheet_name).lower() and "price" not in str(sheet_name).lower():
                continue

            # Search for the row that labels Germany diesel
            for row_idx in range(min(20, len(df))):
                row_str = " ".join(str(c) for c in df.iloc[row_idx].values)
                if "germany" in row_str.lower() or "deutschland" in row_str.lower():
                    if "diesel" in row_str.lower() or "gasoil" in row_str.lower():
                        # Dates are usually in the first row; values follow
                        header_row = df.iloc[0]
                        date_cols = pd.to_datetime(header_row, errors="coerce")
                        values = pd.to_numeric(df.iloc[row_idx], errors="coerce")
                        s = pd.Series(
                            values.values, index=date_cols
                        ).dropna()
                        if s.empty:
                            continue
                        # Prices in the bulletin are in EUR/1000 litres
                        s = s / 1000.0
                        s = s.reindex(dates).ffill().bfill()
                        if s.isna().all():
                            continue
                        s.name = "Gesamt"
                        return s
    except Exception:  # pragma: no cover – network / parse errors
        pass
    return None


def fetch_diesel_prices(
    dates: pd.DatetimeIndex, brent: pd.Series | None = None
) -> pd.DataFrame:
    """
    Return German diesel retail prices (EUR/litre) split into four components:

    * **Netto-Kraftstoffpreis** – net fuel cost (crude + refining + margin).
      This component fluctuates daily; it is partially driven by Brent crude
      returns when Brent data is supplied, reflecting the real-world link
      between crude oil and retail diesel prices.
    * **Energiesteuer** – fixed energy/mineral oil tax (Energiesteuergesetz
      §2 Abs.1 Nr.4: 0.4704 EUR/L).
    * **CO2-Steuer** – CO2 levy (BEHG at 55 EUR/tonne CO2; diesel ~2.65 kg/L).
    * **Mehrwertsteuer (19 %)** – VAT applied on the sum of the three components
      above, so it also fluctuates slightly with the net price.

    Data source: tries the EU Weekly Oil Bulletin first (European Commission,
    DG Energy); falls back to realistic simulated data when the bulletin is
    unavailable.  The resulting total retail price is approximately 2.40 EUR/L.

    Returns a DataFrame with columns:
        ``Netto-Kraftstoffpreis``, ``Energiesteuer``, ``CO2-Steuer``,
        ``Mehrwertsteuer (19%)``, ``Gesamt``
    """
    n = len(dates)

    # -- Try real data first -------------------------------------------------
    print("Diesel: versuche EU Weekly Oil Bulletin (Europäische Kommission)...")
    real_total = _fetch_eu_oil_bulletin_diesel(dates)

    if real_total is not None:
        print("Diesel: EU Oil Bulletin-Daten erfolgreich geladen.")
        # Decompose the real total into fixed + variable components
        before_mwst = real_total / (1.0 + DIESEL_MWST_RATE)
        mwst = real_total - before_mwst
        net_prices = (before_mwst - DIESEL_ENERGIESTEUER - DIESEL_CO2_STEUER).clip(lower=0.0)
        energiesteuer = np.full(n, DIESEL_ENERGIESTEUER)
        co2 = np.full(n, DIESEL_CO2_STEUER)
        return pd.DataFrame(
            {
                "Netto-Kraftstoffpreis": net_prices.values,
                "Energiesteuer": energiesteuer,
                "CO2-Steuer": co2,
                "Mehrwertsteuer (19%)": mwst.values,
                "Gesamt": real_total.values,
            },
            index=dates,
        )

    # -- Simulation fallback -------------------------------------------------
    print("Diesel: WARNUNG – verwende simulierte Daten (EU Oil Bulletin nicht verfügbar).")
    rng = np.random.default_rng(seed=99)

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

    The chart shows Brent crude oil and every German diesel price component
    (Netto-Kraftstoffpreis, Energiesteuer, CO2-Steuer, Mehrwertsteuer, Gesamt)
    as individual lines in a single chart.  Brent uses the left y-axis
    (USD/barrel); all diesel lines use the right y-axis (EUR/litre).

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

    # -- Layout: single chart with secondary y-axis --------------------------
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # -- Brent trace (left / primary y-axis) ---------------------------------
    fig.add_trace(
        go.Scatter(
            x=brent.index,
            y=brent.values,
            mode="lines+markers",
            name="Brent Rohöl (USD/Barrel)",
            line=dict(color="#1f77b4", width=2.5),
            marker=dict(size=5),
            hovertemplate=(
                "<b>Brent Rohöl</b><br>"
                "<b>Datum:</b> %{x|%d.%m.%Y}<br>"
                "<b>Preis:</b> %{y:.2f} USD/Barrel<extra></extra>"
            ),
        ),
        secondary_y=False,
    )

    # -- Diesel component traces (right / secondary y-axis) ------------------
    component_styles: dict[str, dict] = {
        "Netto-Kraftstoffpreis": dict(color="#4e9a8c", dash="solid", width=2),
        "Energiesteuer":         dict(color="#e07b39", dash="dot",   width=1.8),
        "CO2-Steuer":            dict(color="#c0392b", dash="dot",   width=1.8),
        "Mehrwertsteuer (19%)":  dict(color="#8e44ad", dash="dot",   width=1.8),
        "Gesamt":                dict(color="#2c3e50", dash="solid", width=2.5),
    }

    for comp, style in component_styles.items():
        fig.add_trace(
            go.Scatter(
                x=diesel_df.index,
                y=diesel_df[comp].values,
                mode="lines+markers",
                name=f"{comp} (EUR/L)",
                line=style,
                marker=dict(size=4),
                hovertemplate=(
                    f"<b>{comp}</b><br>"
                    "<b>Datum:</b> %{x|%d.%m.%Y}<br>"
                    "<b>Wert:</b> %{y:.4f} EUR/L<extra></extra>"
                ),
            ),
            secondary_y=True,
        )

    # -- Correlation annotation ----------------------------------------------
    corr_text = (
        f"Pearson r (Brent ↔ Diesel Gesamt) = {r:.4f} ({corr_label})<br>"
        f"p-Wert = {p_str}  |  n = {len(brent.dropna())} Handelstage"
    )

    fig.add_annotation(
        text=corr_text,
        xref="paper",
        yref="paper",
        x=0.5,
        y=1.08,
        showarrow=False,
        font=dict(size=12, color="#444"),
        align="center",
        bgcolor="rgba(240,240,240,0.90)",
        bordercolor="#aaa",
        borderwidth=1,
        borderpad=6,
    )

    # -- Axis labels ---------------------------------------------------------
    fig.update_yaxes(
        title_text="Brent Rohöl (USD / Barrel)",
        secondary_y=False,
        tickformat=".2f",
        title_font=dict(color="#1f77b4"),
        tickfont=dict(color="#1f77b4"),
    )
    fig.update_yaxes(
        title_text="Diesel (EUR / Liter)",
        secondary_y=True,
        tickformat=".4f",
        title_font=dict(color="#2c3e50"),
        tickfont=dict(color="#2c3e50"),
    )
    fig.update_xaxes(
        title_text="Datum",
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
            orientation="v",
            yanchor="top",
            y=1.0,
            xanchor="left",
            x=1.08,
        ),
        dragmode="pan",
        template="plotly_white",
        height=600,
        margin=dict(t=130, r=200),
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
