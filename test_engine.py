"""Run: python -m unittest discover -s tests -v"""
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from diesel_engine import (Budget, clean_history, feature_frame, forecast_next_week,
    list_plans, load_history, parse_ec_workbook, refresh_from_ec, save_plan,
    scenario_table, store_dataset)


def sample(n=190):
    return pd.DataFrame({"date": pd.date_range("2022-01-03", periods=n, freq="W-MON"),
                         "price_eur_per_litre": 1.5 + np.arange(n) * 0.001 + np.sin(np.arange(n) / 7) * .02})


class BudgetTests(unittest.TestCase):
    def test_costs_scenarios_and_break_even(self):
        b = Budget(50000, 1.9, 180000, 65000)
        self.assertAlmostEqual(b.fuel_cost, 95000)
        self.assertAlmostEqual(b.profit, 20000)
        self.assertAlmostEqual(b.break_even_price, 2.3)
        rows = scenario_table(b, 20)
        self.assertAlmostEqual(rows.iloc[1]["Extra fuel cost (EUR)"], 9500)
        self.assertAlmostEqual(rows.iloc[1]["Operating result (EUR)"], 10500)
        self.assertAlmostEqual(rows.iloc[2]["Operating result (EUR)"], -8500)

    def test_zero_litres_and_revenue_do_not_divide_by_zero(self):
        b = Budget(0, 2, 0, 500)
        self.assertIsNone(b.margin)
        self.assertIsNone(b.break_even_price)
        self.assertEqual(b.profit, -500)
        self.assertTrue(scenario_table(b, 100)["Operating margin (%)"].isna().all())
        self.assertTrue((scenario_table(b, 100)["Extra fuel cost (EUR)"] == 0).all())

    def test_invalid_budget_and_shocks_are_rejected(self):
        for bad in (-1, float("nan"), float("inf")):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                Budget(bad, 1, 1, 1)
        with self.assertRaises(ValueError):
            scenario_table(Budget(1, 1, 1, 1), -101)


class DataTests(unittest.TestCase):
    def test_workbook_units_and_vat_extraction(self):
        raw = pd.DataFrame([
            ["Date", "DE_price_with_tax_diesel", "FR_price_with_tax_diesel"],
            [None, "Automotive diesel", "Automotive diesel"],
            [None, "1000 l", "1000 l"],
            [pd.Timestamp("2026-10-19"), 2266, 2100],
            [pd.Timestamp("2026-10-12"), 2270, 2090],
        ])
        vat = pd.DataFrame([["DE_", pd.Timestamp("2007-01-01"), 19, 19],
                            ["FR_", pd.Timestamp("2014-01-01"), 20, 20]])
        blob = io.BytesIO()
        with pd.ExcelWriter(blob, engine="openpyxl") as writer:
            raw.to_excel(writer, sheet_name="Prices with taxes", header=False, index=False)
            vat.to_excel(writer, sheet_name="VAT", header=False, index=False)
        hist, meta = parse_ec_workbook(blob.getvalue())
        self.assertEqual(len(hist), 4)
        self.assertAlmostEqual(hist.loc[hist.country == "DE", "price_eur_per_litre"].iloc[-1], 2.266)
        self.assertEqual(meta["vat_percent"]["DE"], 19)
        self.assertEqual(meta["last_observation"], "2026-10-19")

    def test_cleaning_filters_missing_and_invalid_prices(self):
        f = pd.DataFrame({"date": ["2026-01-05", "bad", "2026-01-12", "2026-01-19"],
                          "country": ["DE"] * 4, "price_eur_per_litre": [1.5, 1.6, 0, -5]})
        self.assertEqual(len(clean_history(f)), 1)

    def test_database_refresh_preserves_saved_plans_and_parameterizes_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.sqlite"
            hist = sample(80).assign(country="DE")
            store_dataset(hist, {"source": "test fixture"}, path)
            name = "Plan 'quoted'; DROP TABLE prices; --"
            save_plan(name, {"price": 1.5}, path)
            hist["price_eur_per_litre"] += 0.1
            store_dataset(hist, {"source": "revised test fixture"}, path)
            self.assertEqual(list_plans(path)[0]["name"], name)
            self.assertEqual(len(load_history("DE", path)), 80)
            self.assertAlmostEqual(load_history("DE", path).price_eur_per_litre.iloc[0], 1.6)

    def test_bad_refresh_leaves_old_prices_intact(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.sqlite"
            store_dataset(sample(80).assign(country="DE"), {}, path)
            with patch("diesel_engine.requests.get") as get:
                get.return_value.content = b"<html>Error page</html>"
                with self.assertRaises(ValueError):
                    refresh_from_ec(path)
            self.assertEqual(len(load_history("DE", path)), 80)


class ModelTests(unittest.TestCase):
    def test_current_and_future_targets_do_not_leak_into_features(self):
        h = sample()
        before, _ = feature_frame(h)
        h.loc[100:, "price_eur_per_litre"] += 3
        after, _ = feature_frame(h)
        cols = [c for c in before if not c.startswith("target_")]
        pd.testing.assert_frame_equal(before.iloc[:101][cols], after.iloc[:101][cols])

    def test_missing_week_is_not_used_as_training_target(self):
        h = sample()
        missing_date = h.loc[50, "date"]
        h = h.drop(index=50)
        f, n = feature_frame(h)
        self.assertEqual(n, 1)
        self.assertTrue(pd.isna(f.loc[missing_date, "target_price"]))
        self.assertAlmostEqual(f.loc[missing_date + pd.Timedelta(days=7), "lag_1"], h.loc[49, "price_eur_per_litre"])

    def test_walk_forward_predictions_do_not_see_test_week_target(self):
        h = sample()
        original = forecast_next_week(h)
        start = original["backtest"].date.iloc[0]
        changed = h.copy()
        changed.loc[changed.date >= start, "price_eur_per_litre"] += .3
        modified = forecast_next_week(changed)
        self.assertAlmostEqual(original["backtest"]["ML forecast"].iloc[0], modified["backtest"]["ML forecast"].iloc[0], places=10)
        self.assertEqual(original["date"], h.date.iloc[-1] + pd.Timedelta(days=7))
        self.assertTrue(np.isfinite(original["price"]))

    def test_minimum_history_is_enforced(self):
        with self.assertRaises(ValueError):
            forecast_next_week(sample(30))


if __name__ == "__main__":
    unittest.main()
