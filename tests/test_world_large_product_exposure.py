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

import run_world_large_product_exposure as wlpe


class WorldLargeProductExposureTests(unittest.TestCase):
    def test_product_input_paths_preserve_rd2_name_and_generalize_cadot(self) -> None:
        rd2_paths = wlpe.product_input_paths("rd2_countries", "world_broad")
        cadot_paths = wlpe.product_input_paths("cadot_broad_156", "world_broad")

        self.assertIn("rd2_product_exports.parquet", rd2_paths.country_product.name)
        self.assertIn("cadot_broad_156_product_exports.parquet", cadot_paths.country_product.name)

    def test_exposure_uses_inclusive_world_product_shares(self) -> None:
        country = pd.DataFrame(
            {
                "product_id": ["A", "C"],
                "cmd_code": ["000001", "000003"],
                "product_label": ["A", "C"],
                "primary_broad": [False, False],
                "trade_value": [80.0, 20.0],
            }
        )
        world = pd.DataFrame(
            {
                "product_id": ["A", "B", "C"],
                "cmd_code": ["000001", "000002", "000003"],
                "product_label": ["A", "B", "C"],
                "primary_broad": [False, False, False],
                "world_product_exports": [100.0, 50.0, 25.0],
            }
        )
        metrics, _details = wlpe.compute_country_year_exposure(country, world)
        expected = 0.8 * 1.0 + 0.2 * (1.0 / 3.0)
        self.assertAlmostEqual(metrics["world_share_exposure"], expected)
        self.assertAlmostEqual(metrics["top_1pct_world_product_export_share"], 0.8)
        self.assertAlmostEqual(metrics["top_5pct_world_product_export_share"], 0.8)
        self.assertAlmostEqual(metrics["top_10pct_world_product_export_share"], 0.8)
        self.assertAlmostEqual(metrics["top_20pct_world_product_export_share"], 0.8)
        self.assertAlmostEqual(metrics["spearman_product_alignment"], 1.0)
        self.assertTrue(metrics["metric_valid"])

    def test_top_product_cutoffs_use_exact_descending_rank_count(self) -> None:
        country = pd.DataFrame(
            {
                "product_id": [f"P{i:03d}" for i in range(1, 101)],
                "cmd_code": [f"{i:06d}" for i in range(1, 101)],
                "product_label": [f"P{i:03d}" for i in range(1, 101)],
                "primary_broad": [False] * 100,
                "trade_value": [1.0] * 100,
            }
        )
        world = pd.DataFrame(
            {
                "product_id": [f"P{i:03d}" for i in range(1, 101)],
                "cmd_code": [f"{i:06d}" for i in range(1, 101)],
                "product_label": [f"P{i:03d}" for i in range(1, 101)],
                "primary_broad": [False] * 100,
                "world_product_exports": list(range(100, 0, -1)),
            }
        )
        metrics, _details = wlpe.compute_country_year_exposure(country, world)
        self.assertAlmostEqual(metrics["top_1pct_world_product_export_share"], 0.01)
        self.assertAlmostEqual(metrics["top_5pct_world_product_export_share"], 0.05)
        self.assertAlmostEqual(metrics["top_10pct_world_product_export_share"], 0.10)
        self.assertAlmostEqual(metrics["top_20pct_world_product_export_share"], 0.20)

    def test_exposure_flags_country_products_missing_from_world_basket(self) -> None:
        country = pd.DataFrame(
            {
                "product_id": ["A", "Z"],
                "cmd_code": ["000001", "999998"],
                "product_label": ["A", "Z"],
                "primary_broad": [False, False],
                "trade_value": [80.0, 20.0],
            }
        )
        world = pd.DataFrame(
            {
                "product_id": ["A", "B"],
                "cmd_code": ["000001", "000002"],
                "product_label": ["A", "B"],
                "primary_broad": [False, False],
                "world_product_exports": [100.0, 50.0],
            }
        )
        metrics, _details = wlpe.compute_country_year_exposure(country, world)
        self.assertFalse(metrics["metric_valid"])
        self.assertEqual(metrics["invalid_reason"], "country_products_missing_from_world_basket")
        self.assertAlmostEqual(metrics["missing_world_product_export_share"], 0.2)

    def test_apply_variant_filter_drops_primary_broad_products(self) -> None:
        frame = pd.DataFrame(
            {
                "product_id": ["HS1992:010111", "HS1992:271000", "HS1992:847130"],
                "primary_broad": [True, True, False],
                "trade_value": [10.0, 20.0, 70.0],
            }
        )

        filtered = wlpe.apply_variant_filter(frame, "noncommodity_broad")

        self.assertEqual(filtered["product_id"].tolist(), ["HS1992:847130"])

    def test_product_id_to_cmd_code_uses_trailing_hs6_digits(self) -> None:
        out = wlpe.product_id_to_cmd_code(pd.Series(["HS1992:010511", "HS1992:271000", "847130"]))
        self.assertEqual(out.tolist(), ["010511", "271000", "847130"])

    def test_top_contributor_rows_capture_removed_primary_products(self) -> None:
        meta = {"country": "A", "iso3": "AAA", "reporter_code": 1, "year": 2024}
        baseline = pd.DataFrame(
            {
                "product_id": ["HS1992:271000", "HS1992:847130"],
                "cmd_code": ["271000", "847130"],
                "product_label": ["Refined oil", "Laptop"],
                "primary_broad": [True, False],
                "trade_value": [60.0, 40.0],
                "country_product_export_share": [0.6, 0.4],
                "world_product_exports": [100.0, 100.0],
                "world_product_share": [0.5, 0.5],
                "world_share_rank_percentile": [1.0, 0.5],
                "exposure_contribution": [0.6, 0.2],
            }
        )
        noncommodity = pd.DataFrame(
            {
                "product_id": ["HS1992:847130"],
                "cmd_code": ["847130"],
                "product_label": ["Laptop"],
                "primary_broad": [False],
                "trade_value": [40.0],
                "country_product_export_share": [1.0],
                "world_product_exports": [100.0],
                "world_product_share": [1.0],
                "world_share_rank_percentile": [1.0],
                "exposure_contribution": [1.0],
            }
        )

        rows = wlpe.build_top_contributor_rows(meta, baseline, noncommodity)

        top = rows.iloc[0]
        self.assertEqual(top["cmd_code"], "271000")
        self.assertTrue(bool(top["primary_broad"]))
        self.assertFalse(bool(top["retained_in_noncommodity"]))
        self.assertLess(top["delta_exposure_contribution"], 0)

    def test_top_contributor_rows_handles_empty_variant_detail(self) -> None:
        meta = {"country": "A", "iso3": "AAA", "reporter_code": 1, "year": 2024}
        baseline = pd.DataFrame(
            {
                "product_id": ["HS1992:271000"],
                "cmd_code": ["271000"],
                "product_label": ["Refined oil"],
                "primary_broad": [True],
                "trade_value": [60.0],
                "country_product_export_share": [1.0],
                "world_product_exports": [100.0],
                "world_product_share": [1.0],
                "world_share_rank_percentile": [1.0],
                "exposure_contribution": [1.0],
            }
        )

        rows = wlpe.build_top_contributor_rows(meta, baseline, pd.DataFrame())

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.iloc[0]["cmd_code"], "271000")
        self.assertFalse(bool(rows.iloc[0]["retained_in_noncommodity"]))

    def test_safe_spearman_handles_constants(self) -> None:
        self.assertTrue(np.isnan(wlpe.safe_spearman([1, 1, 1], [1, 2, 3])))
        self.assertAlmostEqual(wlpe.safe_spearman([1, 2, 3], [3, 2, 1]), -1.0)

    def test_year_rank_correlations_distinguish_product_alignment_from_size_test(self) -> None:
        panel = pd.DataFrame(
            {
                "variant": ["baseline", "baseline", "baseline"],
                "variant_label": ["Inclusive world export basket"] * 3,
                "year": [2000, 2000, 2000],
                "log_gdp_current_usd": [1.0, 2.0, 3.0],
                "log_population": [3.0, 2.0, 1.0],
                "world_share_exposure": [0.2, 0.5, 0.8],
                "spearman_product_alignment": [0.9, 0.1, 0.4],
                "top_1pct_world_product_export_share": [0.1, 0.2, 0.3],
                "top_5pct_world_product_export_share": [0.1, 0.2, 0.3],
                "top_10pct_world_product_export_share": [0.1, 0.2, 0.3],
                "top_20pct_world_product_export_share": [0.1, 0.2, 0.3],
            }
        )
        yearly = wlpe.year_rank_correlations(panel)
        headline = yearly[
            yearly["outcome"].eq("world_share_exposure")
            & yearly["size_variable"].eq("log_gdp_current_usd")
        ].iloc[0]
        diagnostic = yearly[
            yearly["outcome"].eq("spearman_product_alignment")
            & yearly["size_variable"].eq("log_gdp_current_usd")
        ].iloc[0]
        self.assertAlmostEqual(headline["spearman_size_outcome"], 1.0)
        self.assertNotEqual(headline["outcome"], diagnostic["outcome"])
        self.assertEqual(headline["variant"], "baseline")


if __name__ == "__main__":
    unittest.main()
