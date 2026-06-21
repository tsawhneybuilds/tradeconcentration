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

from run_fixed_universe_product_theil import (  # noqa: E402
    add_balanced_flags,
    assert_no_excluded_product_ids,
    compute_fixed_universe_metrics,
    compute_world_relative_theil_for_group,
    validate_outputs,
)


class FixedUniverseProductTheilTests(unittest.TestCase):
    def test_missing_products_are_zero_in_fixed_universe_theil(self) -> None:
        universe = {"HS1992:010121", "HS1992:010129", "HS1992:010130", "HS1992:010190"}
        group = pd.DataFrame(
            {
                "product_id": ["HS1992:010121"],
                "trade_value": [10.0],
            }
        )
        metrics = compute_fixed_universe_metrics(group, universe, universe_count=4)
        self.assertAlmostEqual(metrics["fixed_universe_product_theil"], np.log(4.0))
        self.assertAlmostEqual(metrics["fixed_universe_product_theil_normalized"], 1.0)
        self.assertAlmostEqual(metrics["active_product_theil"], 0.0)
        self.assertAlmostEqual(metrics["inactive_product_margin_theil"], np.log(4.0))
        self.assertAlmostEqual(metrics["product_margin_decomposition_residual"], 0.0)
        self.assertEqual(metrics["active_product_count"], 1)
        self.assertEqual(metrics["zero_product_count"], 3)

    def test_equal_active_products_have_zero_active_theil_but_positive_fixed_theil(self) -> None:
        universe = {"A", "B", "C", "D"}
        group = pd.DataFrame({"product_id": ["A", "B"], "trade_value": [5.0, 5.0]})
        metrics = compute_fixed_universe_metrics(group, universe, universe_count=4)
        self.assertAlmostEqual(metrics["active_product_theil"], 0.0)
        self.assertAlmostEqual(metrics["fixed_universe_product_theil"], np.log(2.0))
        self.assertAlmostEqual(metrics["inactive_product_margin_theil"], np.log(2.0))
        self.assertAlmostEqual(metrics["product_margin_decomposition_residual"], 0.0)

    def test_world_relative_theil_is_zero_when_leave_one_out_shares_match(self) -> None:
        country = pd.DataFrame({"product_id": ["A", "B"], "trade_value": [2.0, 8.0]})
        world = pd.DataFrame({"product_id": ["A", "B"], "world_product_exports": [4.0, 16.0]})
        metrics = compute_world_relative_theil_for_group(country, world, "world_product_exports")
        self.assertAlmostEqual(metrics["world_relative_product_theil"], 0.0)
        self.assertAlmostEqual(metrics["zero_weight_country_trade_share"], 0.0)

    def test_world_relative_theil_is_missing_for_zero_leave_one_out_support(self) -> None:
        country = pd.DataFrame({"product_id": ["A", "B"], "trade_value": [2.0, 8.0]})
        world = pd.DataFrame({"product_id": ["A", "B"], "world_product_exports": [2.0, 16.0]})
        metrics = compute_world_relative_theil_for_group(country, world, "world_product_exports")
        self.assertTrue(np.isnan(metrics["world_relative_product_theil"]))
        self.assertAlmostEqual(metrics["zero_weight_country_trade_share"], 0.2)

    def test_missing_reporter_years_are_not_created_by_balance_flagging(self) -> None:
        panel = pd.DataFrame(
            {
                "country": ["A", "A", "B"],
                "iso3": ["AAA", "AAA", "BBB"],
                "reporter_code": [1, 1, 2],
                "year": [2000, 2001, 2000],
                "flow": ["Exports", "Exports", "Exports"],
                "fixed_universe_product_theil": [0.4, 0.5, 0.6],
                "product_id_mode": ["harmonized_hs6_family"] * 3,
                "active_product_share": [0.5, 0.5, 0.5],
                "universe_product_count": [3, 3, 3],
                "active_product_count": [2, 2, 2],
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
                "fixed_universe_product_theil": [0.1, 0.2, 0.3, 0.4],
                "fixed_universe_product_theil_normalized": [0.1, 0.2, 0.3, 0.4],
                "active_product_share": [1.0, 1.0, 1.0, 1.0],
                "universe_product_count": [2, 3, 2, 2],
                "active_product_count": [2, 2, 2, 2],
                "product_margin_decomposition_residual": [0.0, 0.0, 0.0, 0.0],
                "total_trade_value": [10.0, 10.0, 20.0, 20.0],
            }
        )
        diagnostics = pd.DataFrame({"flow": ["Exports", "Imports"], "status": ["ok", "ok"]})
        with self.assertRaisesRegex(RuntimeError, "fixed universe count varies"):
            validate_outputs(panel, diagnostics, 2000, 2001)


if __name__ == "__main__":
    unittest.main()
