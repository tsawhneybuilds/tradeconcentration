from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from concentration_metrics import active_gini
from run_fixed_universe_product_gini import (
    add_balanced_flags,
    assert_no_excluded_product_ids,
    compute_fixed_universe_metrics,
    fixed_universe_gini,
    validate_outputs,
)


class FixedUniverseProductGiniTests(unittest.TestCase):
    def test_equal_products_have_zero_fixed_universe_gini(self) -> None:
        self.assertAlmostEqual(fixed_universe_gini(np.array([10.0, 10.0, 10.0])), 0.0)

    def test_one_positive_product_over_k_products_has_k_minus_one_over_k_gini(self) -> None:
        values = np.array([0.0, 0.0, 5.0, 0.0])
        self.assertAlmostEqual(fixed_universe_gini(values), 3 / 4)

    def test_zero_products_increase_gini_relative_to_active_positive_gini(self) -> None:
        active_values = np.array([3.0, 7.0])
        fixed_values = np.array([0.0, 0.0, 3.0, 7.0])
        self.assertGreaterEqual(fixed_universe_gini(fixed_values), active_gini(active_values))

    def test_missing_products_are_zero_filled_for_valid_reporter_year(self) -> None:
        product_position = {"HS1992:010121": 0, "HS1992:010129": 1, "HS1992:010130": 2}
        group = pd.DataFrame(
            {
                "product_id": ["HS1992:010121", "HS1992:010130"],
                "trade_value": [10.0, 30.0],
            }
        )
        metrics = compute_fixed_universe_metrics(group, product_position, universe_count=3)
        self.assertEqual(metrics["active_product_count"], 2)
        self.assertEqual(metrics["zero_product_count"], 1)
        self.assertAlmostEqual(metrics["active_product_share"], 2 / 3)
        self.assertAlmostEqual(metrics["total_trade_value"], 40.0)

    def test_missing_reporter_years_are_not_created_by_balance_flagging(self) -> None:
        panel = pd.DataFrame(
            {
                "country": ["A", "A", "B"],
                "iso3": ["AAA", "AAA", "BBB"],
                "reporter_code": [1, 1, 2],
                "year": [2000, 2001, 2000],
                "flow": ["Exports", "Exports", "Exports"],
                "fixed_universe_product_gini": [0.4, 0.5, 0.6],
                "active_product_gini": [0.2, 0.3, 0.4],
                "product_id_mode": ["harmonized_hs6_family"] * 3,
                "active_product_share": [0.5, 0.5, 0.5],
                "universe_product_count": [3, 3, 3],
                "total_trade_value": [10.0, 11.0, 12.0],
            }
        )
        out, balance = add_balanced_flags(panel, 2000, 2001, require_balanced_countries=1)
        self.assertEqual(len(out), 3)
        self.assertTrue(out.loc[out["reporter_code"].eq(1), "balanced_panel_flag"].all())
        self.assertFalse(out.loc[out["reporter_code"].eq(2), "balanced_panel_flag"].any())
        self.assertEqual(balance["flows"]["Exports"]["balanced_countries"], 1)

    def test_product_id_validation_rejects_999999(self) -> None:
        frame = pd.DataFrame({"product_id": ["HS1992:010121", "HS1992:999999"]})
        with self.assertRaisesRegex(RuntimeError, "999999"):
            assert_no_excluded_product_ids(frame, "toy products")

    def test_output_validation_rejects_nonconstant_fixed_universe(self) -> None:
        panel = pd.DataFrame(
            {
                "country": ["A", "A", "A", "A"],
                "iso3": ["AAA", "AAA", "AAA", "AAA"],
                "reporter_code": [1, 1, 1, 1],
                "year": [2000, 2001, 2000, 2001],
                "flow": ["Exports", "Exports", "Imports", "Imports"],
                "product_id_mode": ["harmonized_hs6_family"] * 4,
                "fixed_universe_product_gini": [0.1, 0.2, 0.3, 0.4],
                "active_product_gini": [0.1, 0.2, 0.3, 0.4],
                "active_product_share": [1.0, 1.0, 1.0, 1.0],
                "universe_product_count": [2, 3, 2, 2],
                "total_trade_value": [10.0, 10.0, 20.0, 20.0],
            }
        )
        diagnostics = pd.DataFrame({"flow": ["Exports", "Imports"], "status": ["ok", "ok"]})
        with self.assertRaisesRegex(RuntimeError, "fixed universe count varies"):
            validate_outputs(panel, diagnostics, 2000, 2001)


if __name__ == "__main__":
    unittest.main()
