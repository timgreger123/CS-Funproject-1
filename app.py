"""Data, SQLite storage, scenario arithmetic and a small trainable forecasting model.

This module deliberately has no Streamlit dependency, so its calculations can
be tested independently of the interface.
"""
from __future__ import annotations

import io
import json
import math
import os
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parent
SOURCE_PAGE = "https://energy.ec.europa.eu/data-and-analysis/weekly-oil-bulletin_en"
SOURCE_FILE = (
    "https://energy.ec.europa.eu/document/download/"
    "906e60ca-8b6a-44e7-8589-652854d2fd3f_en"
    "?filename=Weekly_Oil_Bulletin_Prices_History_matrici_4web.xlsx"
)
COUNTRIES = {
    "AT": "Austria", "BE": "Belgium", "BG": "Bulgaria", "HR": "Croatia",
    "CY": "Cyprus", "CZ": "Czechia", "DK": "Denmark", "EE": "Estonia",
    "FI": "Finland", "FR": "France", "DE": "Germany", "GR": "Greece",
    "HU": "Hungary", "IE": "Ireland", "IT": "Italy", "LV": "Latvia",
    "LT": "Lithuania", "LU": "Luxembourg", "MT": "Malta",
    "NL": "Netherlands", "PL": "Poland", "PT": "Portugal", "RO": "Romania",
    "SK": "Slovakia", "SI": "Slovenia", "ES": "Spain", "SE": "Sweden",
}


def database_path() -> Path:
    """An environment override makes automated tests use a temporary database."""
    return Path(os.environ.get("DIESEL_PLANNER_DB", str(ROOT / "data" / "planner.sqlite")))


@contextmanager
def connect_db(path=None):
    path = Path(path) if path is not None else database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path), timeout=20)
    con.execute("PRAGMA foreign_keys=ON")
    try:
        with con:
            yield con
    finally:
        con.close()


def clean_history(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate real observations; do not invent/interpolate prices here."""
    required = {"date", "country", "price_eur_per_litre"}
    if not required.issubset(frame.columns):
        raise ValueError("History must contain date, country and price_eur_per_litre.")
    out = frame[list(sorted(required))].copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce", format="mixed")
    out["price_eur_per_litre"] = pd.to_numeric(out["price_eur_per_litre"], errors="coerce")
    out["country"] = out["country"].astype(str).str.upper().str.strip()
    mask = (
        out["date"].notna() & out["country"].isin(COUNTRIES)
        & np.isfinite(out["price_eur_per_litre"])
        & out["price_eur_per_litre"].between(0.05, 30)
    )
    out = out.loc[mask].copy()
    out["date"] = out["date"].dt.normalize()
    out = out.drop_duplicates(["country", "date"], keep="last")
    if out.empty:
        raise ValueError("No valid diesel observations were found.")
    return out[["date", "country", "price_eur_per_litre"]].sort_values(
        ["country", "date"]
    ).reset_index(drop=True)


def parse_ec_workbook(content: bytes):
    """Extract automotive diesel INCLUDING taxes; EC units are EUR / 1,000 L."""
    book = pd.ExcelFile(io.BytesIO(content), engine="openpyxl")
    raw = pd.read_excel(book, sheet_name="Prices with taxes", header=0)
    dates = pd.to_datetime(raw.iloc[:, 0], errors="coerce", format="mixed")
    frames = []
    for column in raw.columns:
        match = re.fullmatch(r"([A-Z]{2})_price_with_tax_diesel", str(column))
        if match and match.group(1) in COUNTRIES:
            frames.append(pd.DataFrame({
                "date": dates,
                "country": match.group(1),
                "price_eur_per_litre": pd.to_numeric(raw[column], errors="coerce") / 1000.0,
            }))
    if not frames:
        raise ValueError("The EC workbook layout changed: no diesel columns found.")
    history = clean_history(pd.concat(frames, ignore_index=True))
    latest = history["date"].max()
    # The VAT sheet is a country/effective-date table. Column 3 is automotive diesel.
    vat_rates = {}
    vat = pd.read_excel(book, sheet_name="VAT", header=None)
    for row in vat.itertuples(index=False, name=None):
        code = str(row[0]).rstrip("_").strip()
        if code not in COUNTRIES:
            continue
        effective = pd.to_datetime(row[1], errors="coerce")
        rate = pd.to_numeric(row[3], errors="coerce")
        if pd.notna(effective) and pd.notna(rate) and effective <= latest and 0 <= rate <= 40:
            previous = vat_rates.get(code)
            if previous is None or effective >= previous[0]:
                vat_rates[code] = (effective, float(rate))
    metadata = {
        "source": "European Commission, DG Energy, Weekly Oil Bulletin",
        "source_page": SOURCE_PAGE,
        "source_file": SOURCE_FILE,
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "first_observation": history["date"].min().date().isoformat(),
        "last_observation": latest.date().isoformat(),
        "rows": len(history),
        "units": "EUR/litre",
        "price_basis": "National average consumer automotive diesel price, all taxes included",
        "conversion": "EC workbook EUR per 1,000 litres divided by 1,000",
        "vat_percent": {code: pair[1] for code, pair in vat_rates.items()},
        "vat_effective_date": {code: pair[0].date().isoformat() for code, pair in vat_rates.items()},
        "licence": "European Commission reuse policy; source acknowledged. See source website.",
    }
    return history, metadata


def store_dataset(history: pd.DataFrame, metadata: dict, path=None):
    """Replace a validated dataset atomically; a failed refresh leaves the old one intact."""
    history = clean_history(history)
    if len(history) < 52:
        raise ValueError("The dataset is unexpectedly small; the existing data was kept.")
    records = [(d.date().isoformat(), c, float(p)) for d, c, p in history.itertuples(index=False, name=None)]
    with connect_db(path) as con:
        con.execute("CREATE TABLE IF NOT EXISTS prices (date TEXT, country TEXT, price REAL NOT NULL, PRIMARY KEY(country, date))")
        con.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        con.execute("CREATE TABLE IF NOT EXISTS plans (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL)")
        con.execute("DELETE FROM prices")
        con.executemany("INSERT INTO prices (date, country, price) VALUES (?, ?, ?)", records)
        con.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)", ("dataset", json.dumps(metadata)))


def ensure_database(path=None):
    """Seed SQLite from the bundled real CSV on first launch; no network needed."""
    with connect_db(path) as con:
        exists = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='prices'").fetchone()
        if exists and con.execute("SELECT COUNT(*) FROM prices").fetchone()[0] > 0:
            return
    history = pd.read_csv(ROOT / "data" / "diesel_history.csv")
    metadata = json.loads((ROOT / "data" / "source_metadata.json").read_text(encoding="utf-8"))
    store_dataset(history, metadata, path)


def load_history(country: str, path=None) -> pd.DataFrame:
    if country not in COUNTRIES:
        raise ValueError("Choose a supported EU country.")
    ensure_database(path)
    with connect_db(path) as con:
        frame = pd.read_sql_query("SELECT date, price AS price_eur_per_litre FROM prices WHERE country=? ORDER BY date", con, params=(country,))
    frame["date"] = pd.to_datetime(frame["date"])
    return frame


def load_metadata(path=None) -> dict:
    ensure_database(path)
    with connect_db(path) as con:
        row = con.execute("SELECT value FROM metadata WHERE key='dataset'").fetchone()
    return json.loads(row[0]) if row else {}


def refresh_from_ec(path=None):
    response = requests.get(SOURCE_FILE, timeout=(10, 45), headers={"User-Agent": "DieselBudgetPlanner/1.0 (university project)"})
    response.raise_for_status()
    if len(response.content) > 20_000_000 or not response.content.startswith(b"PK"):
        raise ValueError("The data source did not return the expected Excel workbook.")
    history, metadata = parse_ec_workbook(response.content)
    # Guard against truncated downloads or an accidentally wrong sheet.
    if history["country"].nunique() < 20 or len(history) < 10_000:
        raise ValueError("The download appears incomplete; the existing dataset was kept.")
    store_dataset(history, metadata, path)
    return metadata


@dataclass(frozen=True)
class Budget:
    litres: float
    price: float
    revenue: float
    other_costs: float

    def __post_init__(self):
        for name in ("litres", "price", "revenue", "other_costs"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be a finite, non-negative number.")

    @property
    def fuel_cost(self):
        return self.litres * self.price

    @property
    def profit(self):
        return self.revenue - self.other_costs - self.fuel_cost

    @property
    def margin(self):
        return self.profit / self.revenue * 100 if self.revenue else None

    @property
    def break_even_price(self):
        return (self.revenue - self.other_costs) / self.litres if self.litres else None


def scenario_table(budget: Budget, custom_shock: float) -> pd.DataFrame:
    if not math.isfinite(custom_shock) or custom_shock < -100:
        raise ValueError("A price shock must be finite and at least -100%.")
    rows = []
    for name, shock in (("Current plan", 0), ("Price +10%", 10), ("Price +30%", 30), (f"Custom {custom_shock:+g}%", custom_shock)):
        price = budget.price * (1 + shock / 100)
        fuel = budget.litres * price
        profit = budget.revenue - budget.other_costs - fuel
        rows.append({"Scenario": name, "Price change (%)": float(shock), "Diesel price (EUR/L)": price,
                     "Diesel cost (EUR)": fuel, "Extra fuel cost (EUR)": fuel - budget.fuel_cost,
                     "Operating result (EUR)": profit,
                     "Operating margin (%)": profit / budget.revenue * 100 if budget.revenue else np.nan})
    return pd.DataFrame(rows)


def feature_frame(history: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Calendar-week features using only earlier weeks (never future prices).

    Missing publication weeks are carried forward for feature inputs only.
    They are never training targets or scored as real observations.
    """
    series = history.set_index("date")["price_eur_per_litre"].sort_index()
    if series.index.has_duplicates or series.empty:
        raise ValueError("History must have unique dates and at least one price.")
    # EC dates are Mondays; assigning the reporting week also supports user fixtures.
    series.index = series.index.to_period("W-SUN").start_time
    series = series.groupby(level=0).last()
    end = series.index[-1] + pd.Timedelta(days=7)
    weeks = pd.date_range(series.index[0], end, freq="W-MON")
    actual = series.reindex(weeks)
    filled = actual.ffill()
    f = pd.DataFrame(index=weeks)
    for lag in range(1, 9):
        f[f"lag_{lag}"] = filled.shift(lag)
    past = filled.shift(1)
    f["mean_4"] = past.rolling(4).mean()
    f["mean_8"] = past.rolling(8).mean()
    f["change_1"] = filled.shift(1) - filled.shift(2)
    f["change_4"] = filled.shift(1) - filled.shift(5)
    f["target_price"] = actual
    f["target_change"] = actual - filled.shift(1)
    f.index.name = "date"
    missing = int(actual.iloc[:-1].isna().sum())
    return f, missing


def forecast_next_week(history: pd.DataFrame, training_weeks=156, evaluation_weeks=26) -> dict:
    """Expanding-information walk-forward backtest; refit on past data each week.

    Ridge predicts the change from the latest price. Hyperparameters are fixed
    in advance; the holdout is not used to tune the model or the scaler.
    """
    if len(history) < 60:
        raise ValueError("At least 60 published weekly prices are needed for the model.")
    frame, missing = feature_frame(history)
    features = [c for c in frame.columns if not c.startswith("target_")]
    known = frame.dropna(subset=features + ["target_price", "target_change"])
    n_test = min(int(evaluation_weeks), len(known) - 32)
    if n_test < 4:
        raise ValueError("There is not enough complete history to evaluate this model.")

    def fit_before(train):
        return make_pipeline(StandardScaler(), Ridge(alpha=10.0)).fit(train[features], train["target_change"])

    predictions = []
    for i in range(len(known) - n_test, len(known)):
        train = known.iloc[max(0, i - training_weeks):i]
        current = known.iloc[[i]]
        model = fit_before(train)
        estimate = float(current["lag_1"].iloc[0] + model.predict(current[features])[0])
        predictions.append({"date": current.index[0], "Actual": float(current["target_price"].iloc[0]),
                            "ML forecast": max(0.001, estimate), "Unchanged-price baseline": float(current["lag_1"].iloc[0])})
    backtest = pd.DataFrame(predictions)
    mae = float(np.abs(backtest["Actual"] - backtest["ML forecast"]).mean())
    baseline_mae = float(np.abs(backtest["Actual"] - backtest["Unchanged-price baseline"]).mean())
    final_train = known.iloc[-training_weeks:]
    model = fit_before(final_train)
    next_row = frame.iloc[[-1]]
    estimate = max(0.001, float(next_row["lag_1"].iloc[0] + model.predict(next_row[features])[0]))
    latest = float(history["price_eur_per_litre"].iloc[-1])
    return {"price": estimate, "date": next_row.index[0], "latest": latest, "mae": mae,
            "baseline_mae": baseline_mae, "backtest": backtest, "train_rows": len(final_train),
            "train_start": final_train.index[0], "train_end": final_train.index[-1],
            "evaluation_weeks": n_test, "filled_weeks": missing, "features": features,
            "beats_baseline": mae < baseline_mae,
            "model": "Ridge regression on weekly price changes (alpha=10)"}


def save_plan(name: str, payload: dict, path=None) -> int:
    name = name.strip()
    if not name or len(name) > 100:
        raise ValueError("Enter a plan name of 1-100 characters.")
    ensure_database(path)
    with connect_db(path) as con:
        cursor = con.execute("INSERT INTO plans (name, created_at, payload) VALUES (?, ?, ?)",
                             (name, datetime.now(timezone.utc).isoformat(), json.dumps(payload, allow_nan=False)))
        return int(cursor.lastrowid)


def list_plans(path=None) -> list:
    ensure_database(path)
    with connect_db(path) as con:
        rows = con.execute("SELECT id, name, created_at, payload FROM plans ORDER BY id DESC LIMIT 100").fetchall()
    return [{"id": i, "name": n, "created_at": c, "payload": json.loads(p)} for i, n, c, p in rows]
