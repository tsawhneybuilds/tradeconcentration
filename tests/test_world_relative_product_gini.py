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

from concentration_metrics import weighted_gini
from argparse import Namespace

from run_world_relative_product_gini import (
    apply_balanced_window,
    compute_country_year_metrics,
    product_exports_from_leaf,
    product_imports_from_leaf,
)
from run_world_relative_product_contributions import (
    assert_no_excluded_product_ids,
    classify_driver_buckets,
    compute_country_year_product_frame,
)


class WorldRelativeProductGiniTests(unittest.TestCase):
    def test_world_relative_gini_is_zero_when_country_matches_world_basket(self) -> None:
        world = pd.DataFrame(
            {
                "cmd_code": ["111111", "222222", "333333"],
                "world_product_exports": [50.0, 30.0, 20.0],
            }
        )
        country = pd.DataFrame(
            {
                "cmd_code": ["111111", "222222", "333333"],
                "trade_value": [5.0, 3.0, 2.0],
            }
        )
        metrics = compute_country_year_metrics(country, world)
        self.assertAlmostEqual(metrics["world_relative_product_gini"], 0.0)
        self.assertGreater(metrics["world_weighted_share_gini"], 0.0)

    def test_leave_one_out_weights_subtract_focal_country(self) -> None:
        world = pd.DataFrame(
            {
                "cmd_code": ["111111", "222222"],
                "world_product_exports": [100.0, 100.0],
            }
        )
        country = pd.DataFrame({"cmd_code": ["111111", "222222"], "trade_value": [80.0, 20.0]})
        metrics = compute_country_year_metrics(country, world)
        expected_weights = np.array([0.2, 0.8])
        expected_shares = np.array([0.8, 0.2])
        expected_relative = expected_shares / expected_weights
        self.assertAlmostEqual(metrics["world_relative_product_gini"], weighted_gini(expected_relative, expected_weights))
        self.assertAlmostEqual(metrics["world_weighted_share_gini"], weighted_gini(expected_shares, expected_weights))

    def test_metrics_accept_harmonized_product_id_column(self) -> None:
        world = pd.DataFrame(
            {
                "product_id": ["HSF:A", "HSF:B"],
                "world_product_exports": [100.0, 100.0],
            }
        )
        country = pd.DataFrame({"product_id": ["HSF:A", "HSF:B"], "trade_value": [80.0, 20.0]})
        metrics = compute_country_year_metrics(country, world)
        expected_weights = np.array([0.2, 0.8])
        expected_shares = np.array([0.8, 0.2])
        self.assertAlmostEqual(metrics["world_relative_product_gini"], weighted_gini(expected_shares / expected_weights, expected_weights))

    def test_unique_country_product_is_diagnosed_as_zero_weight(self) -> None:
        world = pd.DataFrame({"cmd_code": ["111111"], "world_product_exports": [10.0]})
        country = pd.DataFrame({"cmd_code": ["111111", "222222"], "trade_value": [1.0, 9.0]})
        metrics = compute_country_year_metrics(country, world)
        self.assertEqual(metrics["missing_benchmark_product_count"], 1)
        self.assertAlmostEqual(metrics["zero_weight_country_export_share"], 0.9)

    def test_product_export_extraction_excludes_999999_before_aggregation(self) -> None:
        leaf = pd.DataFrame(
            {
                "reporter_code": [1, 1, 1, 1],
                "year": [2000, 2000, 2000, 2000],
                "flow": ["Exports", "Exports", "Imports", "Exports"],
                "classification_code": ["H3", "H3", "H3", "H3"],
                "cmd_code": ["123456", "999999", "123456", "123456"],
                "trade_value": [10.0, 99.0, 20.0, 5.0],
            }
        )
        out = product_exports_from_leaf(leaf)
        self.assertEqual(out["cmd_code"].tolist(), ["123456"])
        self.assertEqual(float(out["trade_value"].iloc[0]), 15.0)

    def test_import_world_relative_gini_is_zero_when_country_matches_world_import_basket(self) -> None:
        world = pd.DataFrame(
            {
                "cmd_code": ["111111", "222222", "333333"],
                "world_product_imports": [50.0, 30.0, 20.0],
            }
        )
        country = pd.DataFrame(
            {
                "cmd_code": ["111111", "222222", "333333"],
                "trade_value": [5.0, 3.0, 2.0],
            }
        )
        metrics = compute_country_year_metrics(country, world, flow="Imports")
        self.assertAlmostEqual(metrics["world_relative_import_product_gini"], 0.0)
        self.assertAlmostEqual(metrics["world_relative_product_gini"], 0.0)
        self.assertIn("country_total_imports", metrics)

    def test_import_leave_one_out_weights_subtract_focal_country_imports(self) -> None:
        world = pd.DataFrame(
            {
                "cmd_code": ["111111", "222222"],
                "world_product_imports": [100.0, 100.0],
            }
        )
        country = pd.DataFrame({"cmd_code": ["111111", "222222"], "trade_value": [80.0, 20.0]})
        metrics = compute_country_year_metrics(country, world, flow="Imports")
        expected_weights = np.array([0.2, 0.8])
        expected_shares = np.array([0.8, 0.2])
        self.assertAlmostEqual(
            metrics["world_relative_import_product_gini"],
            weighted_gini(expected_shares / expected_weights, expected_weights),
        )
        self.assertAlmostEqual(metrics["zero_weight_country_import_share"], 0.0)

    def test_product_import_extraction_excludes_999999_before_aggregation(self) -> None:
        leaf = pd.DataFrame(
            {
                "reporter_code": [1, 1, 1, 1],
                "year": [2000, 2000, 2000, 2000],
                "flow": ["Imports", "Imports", "Exports", "Imports"],
                "classification_code": ["H3", "H3", "H3", "H3"],
                "cmd_code": ["123456", "999999", "123456", "123456"],
                "trade_value": [10.0, 99.0, 20.0, 5.0],
            }
        )
        out = product_imports_from_leaf(leaf)
        self.assertEqual(out["cmd_code"].tolist(), ["123456"])
        self.assertEqual(float(out["trade_value"].iloc[0]), 15.0)

    def test_balanced_window_keeps_only_complete_countries(self) -> None:
        panel = pd.DataFrame(
            {
                "country": ["A", "A", "B"],
                "iso3": ["AAA", "AAA", "BBB"],
                "reporter_code": [1, 1, 2],
                "year": [2000, 2001, 2000],
                "flow": ["Exports", "Exports", "Exports"],
                "world_relative_product_gini": [0.1, 0.2, 0.3],
                "metric_valid": [True, True, True],
            }
        )
        args = Namespace(balanced_start_year=2000, balanced_end_year=2001, require_balanced_countries=1)
        balanced, details = apply_balanced_window(panel, args)
        self.assertEqual(balanced["reporter_code"].unique().tolist(), [1])
        self.assertEqual(details["balanced_countries"], 1)

    def test_contribution_rows_zero_when_country_matches_world_basket(self) -> None:
        world = pd.DataFrame(
            {
                "product_id": ["HSF:A", "HSF:B", "HSF:C"],
                "world_product_exports": [50.0, 30.0, 20.0],
            }
        )
        country = pd.DataFrame({"product_id": ["HSF:A", "HSF:B", "HSF:C"], "trade_value": [5.0, 3.0, 2.0]})
        rows, metrics = compute_country_year_product_frame(country, world)
        self.assertAlmostEqual(metrics["world_relative_product_gini_recomputed"], 0.0)
        self.assertLessEqual(float(rows["positive_loo_gini_contribution"].max()), 1e-12)

    def test_import_contribution_rows_accept_world_import_column(self) -> None:
        world = pd.DataFrame(
            {
                "product_id": ["HSF:A", "HSF:B", "HSF:C"],
                "world_product_imports": [50.0, 30.0, 20.0],
            }
        )
        country = pd.DataFrame({"product_id": ["HSF:A", "HSF:B", "HSF:C"], "trade_value": [5.0, 3.0, 2.0]})
        rows, metrics = compute_country_year_product_frame(country, world, flow="Imports")
        self.assertAlmostEqual(metrics["world_relative_import_product_gini_recomputed"], 0.0)
        self.assertIn("country_product_imports", rows.columns)
        self.assertIn("leave_one_out_product_imports", rows.columns)

    def test_overweight_niche_product_bucket(self) -> None:
        frame = pd.DataFrame(
            {
                "country_share": [0.60],
                "relative_intensity": [12.0],
                "world_weight_percentile": [0.25],
            }
        )
        self.assertEqual(classify_driver_buckets(frame).iloc[0], "overweight_niche_product")

    def test_missing_large_world_product_bucket(self) -> None:
        frame = pd.DataFrame(
            {
                "country_share": [0.0],
                "relative_intensity": [0.0],
                "world_weight_percentile": [0.95],
            }
        )
        self.assertEqual(classify_driver_buckets(frame).iloc[0], "missing_large_world_product")

    def test_contribution_input_rejects_999999_product_id(self) -> None:
        frame = pd.DataFrame({"product_id": ["HSF:H6_999999", "HSF:H6_010121"]})
        with self.assertRaisesRegex(RuntimeError, "999999"):
            assert_no_excluded_product_ids(frame, "toy frame")


if __name__ == "__main__":
    unittest.main()
