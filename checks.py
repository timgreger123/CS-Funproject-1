# BEGIN AI-GENERATED CODE [AI-03]
# Source: OpenAI. (2026). ChatGPT [Large language model]. https://chatgpt.com/
# Retained output: checks.py from the Diesel Budget Planner development chat.
# Scope: The entire file, including the budget and VAT checks, SQLite
# save/load checks, and weekly and Swiss monthly price-model checks.

"""Small checks you can read and run: python checks.py

TemporaryDirectory creates an isolated database for these checks. It never
changes the application's saved plans. Assertions also appear in the HSG tasks.
"""

from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from diesel_engine import (
    budget_price, calculate_budget, country_currency, initialize_database,
    load_history, load_plans, save_plan, scenario_table,
)
from price_model import MONTH, estimate_next_price, estimate_next_week, make_price_pairs


def check_budget():
    result = calculate_budget(50000, 1.9, 180000, 65000)
    assert result["fuel_cost"] == 95000
    assert result["profit"] == 20000
    assert abs(result["break_even"] - 2.3) < 0.000001
    scenarios = scenario_table(50000, 1.9, 180000, 65000, -100)
    assert abs(scenarios.iloc[1]["Operating result (EUR)"] - 10500) < 0.000001
    assert abs(scenarios.iloc[2]["Operating result (EUR)"] + 8500) < 0.000001
    assert scenarios.iloc[3]["Diesel cost (EUR)"] == 0
    zero = calculate_budget(0, 2, 0, 500)
    assert zero["profit"] == -500
    assert zero["margin"] is None and zero["break_even"] is None
    assert abs(budget_price(1.19, True, 19) - 1) < 0.000001
    assert budget_price(1.19, False, 19) == 1.19


def check_database():
    with TemporaryDirectory() as folder:
        filename = Path(folder) / "test.sqlite"
        initialize_database(filename)
        inputs = {"country": "DE", "litres": 10000.0, "price": 1.5,
                  "revenue": 100000.0, "other_costs": 80000.0,
                  "exclude_vat": False, "vat_rate": 0.0, "shock": 20.0}
        name = "Tim's plan; DROP TABLE saved_plans; --"
        save_plan(name, inputs, filename)
        plans = load_plans(filename)
        assert len(plans) == 1 and plans.iloc[0]["name"] == name
        for column in inputs:
            assert plans.iloc[0][column] == inputs[column]


def check_model():
    history = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=80, freq="7D"),
        "price_eur_per_litre": [1.3 + i * 0.001 for i in range(80)],
    })
    # Removing one week removes both pairs which would require its price.
    gapped = history.drop(index=20)
    pairs = make_price_pairs(gapped)
    assert len(pairs) == len(history) - 3
    assert history.iloc[21]["date"] not in pairs["date"].tolist()
    result = estimate_next_week(history)
    assert result["date"] == history.iloc[-1]["date"] + timedelta(days=7)
    assert result["model_error"] < 0.000001

    # Changing the first test target must not change that target's prediction.
    changed = history.copy()
    test_dates = changed["date"] >= result["test_start"]
    changed.loc[test_dates, "price_eur_per_litre"] += 0.3
    rerun = estimate_next_week(changed)
    first = result["comparison"]["Model estimate"].iloc[0]
    assert abs(first - rerun["comparison"]["Model estimate"].iloc[0]) < 0.000001
    assert len(load_history("DE")) > 30


def check_swiss_prices():
    history = load_history("CH")
    price_column = "price_chf_per_litre"
    assert len(history) > 30
    assert history["date"].dt.day.eq(1).all()
    assert history[price_column].gt(0).all()

    gapped = history.drop(index=20)
    pairs = make_price_pairs(gapped, MONTH, price_column)
    assert history.iloc[21]["date"] not in pairs["date"].tolist()
    estimate = estimate_next_price(history, MONTH, price_column)
    assert estimate["date"] == history.iloc[-1]["date"] + MONTH

    price = history.iloc[-1][price_column]
    scenarios = scenario_table(50000, price, 180000, 65000, 20, country_currency("CH"))
    assert scenarios.iloc[0]["Diesel cost (CHF)"] == 50000 * price


if __name__ == "__main__":
    check_budget()
    check_database()
    check_model()
    check_swiss_prices()
    print("Budget, database and weekly and monthly model checks passed.")

# END AI-GENERATED CODE [AI-03]