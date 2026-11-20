"""Optional HTTP download, using the requests pattern from Assignment 6.

Also uses pandas.read_excel, a small extension to the course's read_csv.
Run manually with: python refresh_data.py
"""

from datetime import datetime, timezone
from io import BytesIO
import json

import pandas as pd
import requests

from diesel_engine import COUNTRIES, FOLDER, HISTORY_FILE


SOURCE_PAGE = "https://energy.ec.europa.eu/data-and-analysis/weekly-oil-bulletin_en"
SOURCE_FILE = (
    "https://energy.ec.europa.eu/document/download/"
    "906e60ca-8b6a-44e7-8589-652854d2fd3f_en"
    "?filename=Weekly_Oil_Bulletin_Prices_History_matrici_4web.xlsx"
)


def parse_prices(content):
    """Select automotive diesel WITH taxes and convert EUR/1000 L to EUR/L."""
    raw = pd.read_excel(BytesIO(content), sheet_name="Prices with taxes")
    dates = pd.to_datetime(raw.iloc[:, 0], errors="coerce", format="mixed")
    frames = []
    for code in COUNTRIES:
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


def refresh_history():
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
