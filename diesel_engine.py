"""Budget arithmetic, CSV reading and SQLite plans.

The functions use the loops, dictionaries, pandas and SQL from the course.
There is no Streamlit code here: the same functions can be used in a notebook.
"""

from pathlib import Path
import sqlite3

import pandas as pd


# Resolve paths relative to this file, even if Terminal is in another folder.
FOLDER = Path(__file__).resolve().parent
HISTORY_FILE = FOLDER / "data" / "diesel_history.csv"
DATABASE_FILE = FOLDER / "data" / "student_plans.sqlite"

COUNTRIES = {
    "AT": "Austria", "BE": "Belgium", "BG": "Bulgaria", "HR": "Croatia",
    "CY": "Cyprus", "CZ": "Czechia", "DK": "Denmark", "EE": "Estonia",
    "FI": "Finland", "FR": "France", "DE": "Germany", "GR": "Greece",
    "HU": "Hungary", "IE": "Ireland", "IT": "Italy", "LV": "Latvia",
    "LT": "Lithuania", "LU": "Luxembourg", "MT": "Malta",
    "NL": "Netherlands", "PL": "Poland", "PT": "Portugal", "RO": "Romania",
    "SK": "Slovakia", "SI": "Slovenia", "ES": "Spain", "SE": "Sweden",
}


def load_history(country, filename=HISTORY_FILE):
    """Read the CSV, select one country and sort its observations by date."""
    history = pd.read_csv(filename)
    history = history[history["country"] == country].copy()
    history["date"] = pd.to_datetime(history["date"])
    history = history.sort_values("date").reset_index(drop=True)
    if history.empty:
        raise ValueError("There are no observations for this country.")
    return history


def budget_price(pump_price, exclude_vat, vat_rate):
    """Convert a tax-inclusive benchmark to the selected budget basis."""
    if exclude_vat:
        return pump_price / (1 + vat_rate / 100)
    return pump_price


def calculate_budget(litres, price, revenue, other_costs):
    """Return the four budget results in a dictionary."""
    if litres < 0 or price < 0 or revenue < 0 or other_costs < 0:
        raise ValueError("Budget inputs cannot be negative.")

    fuel_cost = litres * price
    profit = revenue - other_costs - fuel_cost

    # A percentage of zero revenue and a price per zero litres are undefined.
    if revenue > 0:
        margin = profit / revenue * 100
    else:
        margin = None

    if litres > 0:
        break_even = (revenue - other_costs) / litres
    else:
        break_even = None

    return {"fuel_cost": fuel_cost, "profit": profit,
            "margin": margin, "break_even": break_even}


def scenario_table(litres, price, revenue, other_costs, custom_shock):
    """Change only the diesel price; hold the other business inputs constant."""
    if custom_shock < -100:
        raise ValueError("A price cannot fall by more than 100%.")
    base = calculate_budget(litres, price, revenue, other_costs)
    names = ["Current plan", "Price +10%", "Price +30%", "Custom scenario"]
    shocks = [0, 10, 30, custom_shock]
    rows = []

    for i in range(len(shocks)):
        new_price = price * (1 + shocks[i] / 100)
        result = calculate_budget(litres, new_price, revenue, other_costs)
        rows.append({
            "Scenario": names[i],
            "Price change (%)": shocks[i],
            "Diesel price (EUR/L)": new_price,
            "Diesel cost (EUR)": result["fuel_cost"],
            "Extra diesel cost (EUR)": result["fuel_cost"] - base["fuel_cost"],
            "Operating result (EUR)": result["profit"],
            "Operating margin (%)": result["margin"],
        })

    return pd.DataFrame(rows)


def initialize_database(filename=DATABASE_FILE):
    """Create one table if this is the first run (Lecture 7)."""
    connection = sqlite3.connect(filename)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS saved_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            country TEXT NOT NULL,
            litres REAL NOT NULL,
            price REAL NOT NULL,
            revenue REAL NOT NULL,
            other_costs REAL NOT NULL,
            exclude_vat INTEGER NOT NULL,
            vat_rate REAL NOT NULL,
            shock REAL NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    connection.commit()
    connection.close()


def save_plan(name, inputs, filename=DATABASE_FILE):
    """Store the actual planning price, including any manual adjustment."""
    name = name.strip()
    if name == "" or len(name) > 100:
        raise ValueError("Enter a plan name with 1 to 100 characters.")

    connection = sqlite3.connect(filename)
    # The ? placeholders keep user-entered names separate from SQL commands.
    connection.execute("""
        INSERT INTO saved_plans
        (name, country, litres, price, revenue, other_costs,
         exclude_vat, vat_rate, shock)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, inputs["country"], inputs["litres"], inputs["price"],
          inputs["revenue"], inputs["other_costs"], int(inputs["exclude_vat"]),
          inputs["vat_rate"], inputs["shock"]))
    connection.commit()
    connection.close()


def load_plans(filename=DATABASE_FILE):
    connection = sqlite3.connect(filename)
    plans = pd.read_sql("SELECT * FROM saved_plans ORDER BY id DESC", connection)
    connection.close()
    return plans
