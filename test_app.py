import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


class AppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"DIESEL_PLANNER_DB": str(Path(self.tmp.name) / "app.sqlite")})
        self.env.start()
        self.at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
        self.assertEqual(len(self.at.exception), 0)

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_budget_zero_case_and_country_change(self):
        at = self.at
        at.number_input(key="litres").set_value(10000)
        at.number_input(key="price").set_value(1.5)
        at.number_input(key="revenue").set_value(100000)
        at.number_input(key="other_costs").set_value(80000)
        at.run()
        self.assertEqual(len(at.exception), 0)
        results = {m.label: m.value for m in at.metric}
        self.assertEqual(results["Monthly operating result"], "€5,000")
        at.number_input(key="litres").set_value(0)
        at.number_input(key="revenue").set_value(0)
        at.run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual({m.label: m.value for m in at.metric}["Operating margin"], "N/A")
        at.selectbox(key="country").set_value("FR").run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(at.number_input(key="vat_percent").value, 20)

    def test_save_restore_and_forecast_button(self):
        at = self.at
        original_litres = at.number_input(key="litres").value
        at.text_input(key="plan_name").set_value("Test saved plan")
        at.button(key="save_plan").click().run()
        self.assertEqual(len(at.exception), 0)
        at.number_input(key="litres").set_value(123).run()
        at.button(key="restore_1").click().run()
        self.assertEqual(at.number_input(key="litres").value, original_litres)
        at.button(key="use_forecast").click().run()
        self.assertEqual(len(at.exception), 0)
        self.assertGreater(at.number_input(key="price").value, 0)
        at.checkbox(key="remove_vat").uncheck().run()
        self.assertEqual(len(at.exception), 0)

    def test_missing_vat_rate_defaults_to_gross_planning(self):
        at = self.at
        at.selectbox(key="country").set_value("DK").run()
        self.assertEqual(len(at.exception), 0)
        self.assertFalse(at.checkbox(key="remove_vat").value)
        self.assertTrue(any("VAT rate is unavailable" in i.value for i in at.info))


if __name__ == "__main__":
    unittest.main()
