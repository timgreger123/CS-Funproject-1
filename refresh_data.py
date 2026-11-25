# BEGIN AI-GENERATED CODE [AI-01]
# Source: OpenAI. (2026). ChatGPT [Large language model]. https://chatgpt.com/
# Initial version delivered on 20 November 2026.
# Swiss data support added on 24 November 2026.
# Retained output: CS-Funproject-1/refresh_data.py in
# Diesel_Planner_HSG_Updated.zip.
# Scope: The entire module, including the EU and Swiss data downloads,
# Excel parsing, validation, and writing the CSV files and metadata.

"""Optional HTTP download, using the requests pattern from Assignment 6.

Also uses pandas.read_excel, a small extension to the course's read_csv.
Run manually with: python refresh_data.py
"""

from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import BadZipFile

import pandas as pd
import requests

from diesel_engine import COUNTRIES, FOLDER, HISTORY_FILE, SWISS_HISTORY_FILE


SOURCE_PAGE = "https://energy.ec.europa.eu/data-and-analysis/weekly-oil-bulletin_en"
SOURCE_FILE = (
    "https://energy.ec.europa.eu/document/download/"
    "906e60ca-8b6a-44e7-8589-652854d2fd3f_en"
    "?filename=Weekly_Oil_Bulletin_Prices_History_matrici_4web.xlsx"
)
SWISS_SOURCE = "Swiss Federal Statistical Office (FSO), average energy and fuel prices"
SWISS_SOURCE_PAGE = "https://statistik.admin.ch/de/asset/36970598"
SWISS_SOURCE_FILE = (
    "https://dam-api.bfs.admin.ch/hub/api/dam/assets/orderNr:su-d-05.02.91/master"
)


def parse_prices(content):
    """Select automotive diesel WITH taxes and convert EUR/1000 L to EUR/L."""
    raw = pd.read_excel(BytesIO(content), sheet_name="Prices with taxes")
    dates = pd.to_datetime(raw.iloc[:, 0], errors="coerce", format="mixed")
    frames = []
    for code in COUNTRIES:
        if code == "CH":
            continue
        column = code + "_price_with_tax_diesel"
        if column in raw.columns:
            country_data = pd.DataFrame({
                "date": dates,
                "country": code,
                "price_eur_per_litre": pd.to_numeric(raw[column], errors="coerce") / 1000,
            })
            country_data = country_data.dropna()
            country_data = country_data[country_data["price_eur_per_litre"] > 0]
            frames.append(country_data)

    if len(frames) < 20:
        raise ValueError("The source format changed or the download is incomplete.")
    history = pd.concat(frames, ignore_index=True)
    history = history.drop_duplicates(["country", "date"])
    history = history.sort_values(["country", "date"])
    if len(history) < 10000:
        raise ValueError("The download contains too few observations.")
    return history


def parse_swiss_prices(content):
    """Read the FSO's monthly retail diesel prices, in CHF per litre."""
    try:
        raw = pd.read_excel(BytesIO(content), sheet_name="Monat - Mois", header=4)
    except BadZipFile as error:
        raise ValueError("The Swiss data source did not return an Excel workbook.") from error

    if not {"Monat / Mois", "Diesel"}.issubset(raw.columns) or raw.empty:
        raise ValueError("The Swiss workbook is missing its month or diesel column.")
    if str(raw["Diesel"].iloc[0]).strip() != "1 l":
        raise ValueError("The Swiss workbook no longer lists diesel prices per litre.")

    prices = pd.DataFrame({
        "date": pd.to_datetime(raw["Monat / Mois"], errors="coerce"),
        "country": "CH",
        "price_chf_per_litre": pd.to_numeric(raw["Diesel"], errors="coerce"),
    }).dropna()
    prices = prices[prices["price_chf_per_litre"] > 0].copy()
    prices["date"] = prices["date"].dt.to_period("M").dt.to_timestamp()
    prices = prices.drop_duplicates("date").sort_values("date")
    if len(prices) < 30:
        raise ValueError("The Swiss workbook contains too few monthly observations.")
    return prices


def refresh_swiss_history():
    response = requests.get(SWISS_SOURCE_FILE, timeout=30)
    response.raise_for_status()
    history = parse_swiss_prices(response.content)

    # Replace the CSV only after the new file is complete.
    with TemporaryDirectory(dir=SWISS_HISTORY_FILE.parent) as folder:
        downloaded = Path(folder) / SWISS_HISTORY_FILE.name
        history.to_csv(downloaded, index=False, date_format="%Y-%m-%d")
        downloaded.replace(SWISS_HISTORY_FILE)
    return {"last_observation": history["date"].max().strftime("%Y-%m-%d")}


def refresh_history(country="DE"):
    if country == "CH":
        return refresh_swiss_history()

    response = requests.get(SOURCE_FILE, timeout=30)
    response.raise_for_status()
    history = parse_prices(response.content)

    metadata = {
        "source": "European Commission, DG Energy, Weekly Oil Bulletin",
        "source_page": SOURCE_PAGE,
        "source_file": SOURCE_FILE,
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "first_observation": history["date"].min().strftime("%Y-%m-%d"),
        "last_observation": history["date"].max().strftime("%Y-%m-%d"),
        "rows": len(history), "units": "EUR/litre",
        "price_basis": "Automotive diesel consumer prices, all taxes included",
        "conversion": "Source EUR per 1000 litres divided by 1000",
    }
    # Download and validation finish before either local file is replaced.
    history.to_csv(HISTORY_FILE, index=False, date_format="%Y-%m-%d")
    with open(FOLDER / "data" / "source_metadata.json", "w", encoding="utf-8") as file:
        json.dump(metadata, file, indent=2)
    return metadata


if __name__ == "__main__":
    result = refresh_history()
    print("Latest reporting date:", result["last_observation"])

# END AI-GENERATED CODE [AI-01]
