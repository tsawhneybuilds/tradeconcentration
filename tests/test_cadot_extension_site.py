from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_trade_gini_site as site


class CadotExtensionSiteTests(unittest.TestCase):
    def test_all_metric_exercise_chart_questions_are_registered(self) -> None:
        expected_chart_ids = {
            "exercise1-map",
            "exercise1-lines",
            "exercise1-ranking",
            "exercise2-growth",
            "exercise2-products",
            "exercise3-trend",
            "exercise3-latest",
            "exercise3-nonenergy-map",
            "exercise3-nonenergy-lines",
            "rank-bucket-overview",
            "rank-bucket-country-chart",
            "exercise4-trend",
            "exercise4-latest",
            "exercise6-trend",
            "exercise6-sensitivity",
            "exercise10-trend",
            "exercise10-latest",
            "exercise11-trend",
            "exercise11-top",
            "exercise12-growth",
            "exercise12-components",
        }

        self.assertTrue(expected_chart_ids.issubset(site.CADOT_GRAPH_QUESTIONS))
        self.assertIn("exposure-gdp-exposure", site.CADOT_GRAPH_QUESTIONS)
        self.assertIn("exposure-gdp-alignment", site.CADOT_GRAPH_QUESTIONS)
        self.assertTrue(
            set(site.CADOT_EXERCISE_FIGURES["01"])
            .union(*[
                set(site.CADOT_EXERCISE_FIGURES[short])
                for short in ["02", "03", "04", "06", "10", "11", "12"]
            ])
            .issubset(site.CADOT_GRAPH_QUESTIONS)
        )
        self.assertEqual(len(site.EXERCISE_PAGE_SPECS) * 3, 24)

    def test_nonenergy_download_bundle_is_complete(self) -> None:
        expected = {
            "nonenergy_import_metric_annual.csv",
            "nonenergy_import_reporter_coverage.csv",
            "nonenergy_import_rank_bucket_snapshots.csv",
            "nonenergy_import_top_products_snapshots.csv",
            "nonenergy_import_rank_bucket_drivers.csv",
            "nonenergy_world_hs1992_product_universe.csv",
            "nonenergy_visualization_validation_checks.csv",
            "nonenergy_visualization_manifest.json",
            "nonenergy_visualization_adversarial_review.md",
            "archived_extension_parity_report.md",
            "world_large_product_exposure_yearly_spearman.csv",
            "world_large_product_exposure_models.csv",
            "world_large_product_exposure_validation_checks.csv",
            "world_large_product_exposure_fixed_country_2018_2024.csv",
            "world_large_product_exposure_country_commodity_shares.csv",
            "world_large_product_exposure_panel.csv",
            "world_large_product_exposure.md",
            "run_manifest_world_large_product_exposure.json",
            "world_large_product_exposure_adversarial_review.md",
        }

        self.assertTrue(expected.issubset(site.THREE_METRIC_DOWNLOAD_FILES))

    def test_metric_conventions_are_explicit(self) -> None:
        self.assertEqual(
            site.cadot_metric_convention("gini"), "active-positive Gini"
        )
        self.assertEqual(
            site.cadot_metric_convention("theil"), "fixed-universe Theil"
        )
        self.assertEqual(site.cadot_metric_convention("hhi"), "raw HHI")
        self.assertEqual(
            site.cadot_metric_convention("theil", "exercise3-trend"),
            "within-bin active-product Theil",
        )

    def test_exposure_route_is_in_cadot_navigation(self) -> None:
        nav = site.cadot_nav(0, "exposure")
        self.assertIn("Exposure", nav)
        self.assertIn('href="exposure/"', nav)


if __name__ == "__main__":
    unittest.main()
