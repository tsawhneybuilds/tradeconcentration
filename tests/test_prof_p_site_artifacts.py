from __future__ import annotations

import math
import sys
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_trade_gini_site as site
from replicate_prof_p_paper import PAPER_TABLE_2, PROF_P_LORENZ_TABLE, PROF_P_TOP_SHARE_TABLE


class ProfPWebsiteArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not PROF_P_TOP_SHARE_TABLE.exists() or not PROF_P_LORENZ_TABLE.exists():
            raise AssertionError("Run scripts/replicate_prof_p_paper.py before testing Prof P website artifacts.")
        cls.top = pd.read_csv(PROF_P_TOP_SHARE_TABLE)
        cls.lorenz = pd.read_csv(PROF_P_LORENZ_TABLE)

    def test_top_share_artifact_has_expected_prof_p_rows(self) -> None:
        self.assertEqual(len(self.top), 66)
        self.assertEqual(set(self.top["flow"]), {"Exports", "Imports"})
        self.assertEqual(set(self.top["country"]), set(PAPER_TABLE_2["country"]))

    def test_top_share_cutoffs_use_ceiling_of_active_products(self) -> None:
        for row in self.top.itertuples(index=False):
            self.assertEqual(row.top_1pct_cutoff_products, max(1, math.ceil(row.modern_active_products * 0.01)))
            self.assertEqual(row.top_5pct_cutoff_products, max(1, math.ceil(row.modern_active_products * 0.05)))
            self.assertGreaterEqual(row.modern_top_5pct_product_share, row.modern_top_1pct_product_share)
            self.assertLessEqual(row.modern_top_5pct_product_share, 1.0)

    def test_paper_table2_values_are_preserved(self) -> None:
        paper = PAPER_TABLE_2.set_index("country")
        for row in self.top.itertuples(index=False):
            paper_row = paper.loc[row.country]
            if row.flow == "Exports":
                expected_gini = paper_row["paper_export_product_gini"]
                expected_count = paper_row["paper_export_products"]
            else:
                expected_gini = paper_row["paper_import_product_gini"]
                expected_count = paper_row["paper_import_products"]
            self.assertAlmostEqual(row.paper_product_gini, expected_gini)
            self.assertEqual(row.paper_active_products, expected_count)

    def test_lorenz_points_are_monotone_and_match_table_counts(self) -> None:
        selected = self.top[self.top["country"].isin(["India", "China", "United States"])]
        lookup = selected.set_index(["country", "flow"])["modern_active_products"].to_dict()
        for (country, flow), group in self.lorenz.groupby(["country", "flow"]):
            group = group.sort_values("point_index")
            self.assertEqual(len(group), int(lookup[(country, flow)]) + 1)
            self.assertAlmostEqual(group.iloc[0]["cum_products_share"], 0.0)
            self.assertAlmostEqual(group.iloc[0]["cum_trade_value_share"], 0.0)
            self.assertAlmostEqual(group.iloc[-1]["cum_products_share"], 1.0)
            self.assertAlmostEqual(group.iloc[-1]["cum_trade_value_share"], 1.0)
            self.assertTrue(np.all(np.diff(group["cum_products_share"]) >= -1e-12))
            self.assertTrue(np.all(np.diff(group["cum_trade_value_share"]) >= -1e-12))

    def test_no_product_code_column_contains_999999(self) -> None:
        for frame in [self.top, self.lorenz]:
            code_cols = [col for col in frame.columns if col in {"cmd_code", "product_code", "hs6", "concordance_code"}]
            for col in code_cols:
                normalized = frame[col].astype("string").str.extract(r"(\d{1,6})", expand=False).str.zfill(6)
                self.assertFalse(normalized.eq("999999").any())

    def test_rd2_site_requires_country_size_gmm_artifacts(self) -> None:
        site.configure_site_sample("rd2_countries")
        required_sources = {
            "country_size_gmm_lag_iv_models": "gmm_lag_iv_models.csv",
            "country_size_gmm_lag_iv_first_stage": "gmm_lag_iv_first_stage.csv",
        }
        for source_key, filename in required_sources.items():
            self.assertIn(source_key, site.SOURCE_FILES)
            self.assertEqual(site.SOURCE_FILES[source_key].name, filename)
        self.assertIn("country_size_effect_gmm_lag_iv_models.csv", site.DOWNLOADS)
        self.assertIn("country_size_effect_gmm_lag_iv_first_stage.csv", site.DOWNLOADS)

    def test_rd2_site_requires_future_growth_artifacts(self) -> None:
        site.configure_site_sample("rd2_countries")
        required_sources = {
            "future_growth_panel": "future_growth_concentration_panel.csv",
            "future_growth_bucket_summary": "bucket_summary.csv",
            "future_growth_bucket_models": "bucket_models.csv",
            "future_growth_continuous_models": "continuous_models.csv",
            "future_growth_paired_models": "paired_models.csv",
            "future_growth_robustness_models": "robustness_models.csv",
            "future_growth_base_size_bin_summary": "base_size_bin_summary.csv",
            "future_growth_base_size_sensitivity_models": "base_size_sensitivity_models.csv",
            "future_growth_mechanism_channel_panel": "mechanism_channel_panel.csv",
            "future_growth_mechanism_channel_models": "mechanism_channel_models.csv",
            "future_growth_mechanism_summary": "mechanism_summary.csv",
            "future_growth_mechanism_diagnostics": "mechanism_diagnostics.csv",
            "future_growth_leave_one_country_out_influence": "leave_one_country_out_influence.csv",
            "future_growth_sample_diagnostics": "sample_diagnostics.csv",
            "future_growth_missing_controls": "missing_controls.csv",
        }
        for source_key, filename in required_sources.items():
            self.assertIn(source_key, site.SOURCE_FILES)
            self.assertEqual(site.SOURCE_FILES[source_key].name, filename)
        self.assertIn("future_growth_bucket_summary_growth", site.FIGURES)
        self.assertIn("future_growth_continuous_coefficients", site.FIGURES)
        for filename in [
            "future_growth_concentration_panel.csv",
            "future_growth_bucket_summary.csv",
            "future_growth_bucket_models.csv",
            "future_growth_continuous_models.csv",
            "future_growth_paired_models.csv",
            "future_growth_robustness_models.csv",
            "future_growth_base_size_bin_summary.csv",
            "future_growth_base_size_sensitivity_models.csv",
            "future_growth_mechanism_channel_panel.csv",
            "future_growth_mechanism_channel_models.csv",
            "future_growth_mechanism_summary.csv",
            "future_growth_mechanism_diagnostics.csv",
            "future_growth_leave_one_country_out_influence.csv",
            "future_growth_sample_diagnostics.csv",
            "future_growth_missing_controls.csv",
            "run_manifest_future_growth_concentration.json",
        ]:
            self.assertIn(filename, site.DOWNLOADS)

    def test_rd2_site_requires_world_relative_contribution_artifacts(self) -> None:
        site.configure_site_sample("rd2_countries")
        required_sources = {
            "world_relative_product_contribution_top_drivers": "world_relative_product_contribution_top_drivers.csv",
            "world_relative_product_contribution_country_year_summary": (
                "world_relative_product_contribution_country_year_summary.csv"
            ),
            "world_relative_product_contribution_latest_small_countries": (
                "world_relative_product_contribution_latest_small_countries.csv"
            ),
            "world_relative_product_contribution_bucket_summary": "world_relative_product_contribution_bucket_summary.csv",
            "world_relative_product_contribution_validation": "world_relative_product_contribution_validation.csv",
            "world_relative_import_product_gini_panel": "world_relative_import_product_gini_all_years.csv",
            "world_weighted_import_product_gini_appendix": "world_weighted_import_product_gini_appendix.csv",
            "world_relative_import_product_gini_diagnostics": "world_relative_import_product_gini_diagnostics.csv",
            "world_relative_import_product_gini_classification_diagnostics": (
                "world_relative_import_product_gini_classification_diagnostics.csv"
            ),
            "world_relative_import_product_gini_harmonization_diagnostics": (
                "world_relative_import_product_gini_harmonization_diagnostics.csv"
            ),
            "world_relative_import_product_gini_yearly_summary": "world_relative_import_product_gini_yearly_summary.csv",
            "world_relative_import_product_gini_latest_rankings": (
                "world_relative_import_product_gini_latest_rankings.csv"
            ),
            "world_relative_import_product_contribution_top_drivers": (
                "world_relative_import_product_contribution_top_drivers.csv"
            ),
            "world_relative_import_product_contribution_country_year_summary": (
                "world_relative_import_product_contribution_country_year_summary.csv"
            ),
            "world_relative_import_product_contribution_latest_small_countries": (
                "world_relative_import_product_contribution_latest_small_countries.csv"
            ),
            "world_relative_import_product_contribution_bucket_summary": (
                "world_relative_import_product_contribution_bucket_summary.csv"
            ),
            "world_relative_import_product_contribution_validation": (
                "world_relative_import_product_contribution_validation.csv"
            ),
        }
        for source_key, filename in required_sources.items():
            self.assertIn(source_key, site.SOURCE_FILES)
            self.assertEqual(site.SOURCE_FILES[source_key].name, filename)
            self.assertIn(filename, site.DOWNLOADS)
        self.assertIn("run_manifest_world_relative_product_contributions.json", site.DOWNLOADS)
        self.assertIn("run_manifest_world_relative_import_product_gini.json", site.DOWNLOADS)
        self.assertIn("run_manifest_world_relative_import_product_contributions.json", site.DOWNLOADS)

    def test_future_growth_page_is_rd2_only(self) -> None:
        context = defaultdict(str)
        site.configure_site_sample("rd2_countries")
        rd2_pages = site.render_pages(context)
        self.assertIn("future-growth.html", rd2_pages)
        self.assertIn("Future growth", site.nav("future-growth"))
        self.assertIn("Future Export Growth From Trade Concentration", rd2_pages["future-growth.html"])
        self.assertIn("future_growth_concentration_panel.csv", rd2_pages["future-growth.html"])
        self.assertIn("run_manifest_future_growth_concentration.json", rd2_pages["future-growth.html"])

        site.configure_site_sample("prof_p_33")
        self.assertNotIn("future-growth.html", site.render_pages(context))
        self.assertNotIn("future_growth_panel", site.SOURCE_FILES)
        self.assertNotIn("future_growth_concentration_panel.csv", site.DOWNLOADS)

        site.configure_site_sample("world_broad")
        self.assertNotIn("future-growth.html", site.render_pages(context))
        self.assertNotIn("future_growth_panel", site.SOURCE_FILES)
        self.assertNotIn("future_growth_concentration_panel.csv", site.DOWNLOADS)
        site.configure_site_sample("rd2_countries")

    def test_rd2_site_requires_partner_stability_artifacts(self) -> None:
        site.configure_site_sample("rd2_countries")
        required_sources = {
            "partner_stability_country_flow": "country_flow_stability.csv",
            "partner_stability_summary": "stability_summary.csv",
            "partner_stability_common_trends": "common_trend_models.csv",
            "partner_stability_variance_decomposition": "variance_decomposition.csv",
            "partner_stability_low_active_sensitivity": "low_active_partner_sensitivity.csv",
        }
        for source_key, filename in required_sources.items():
            self.assertIn(source_key, site.SOURCE_FILES)
            self.assertEqual(site.SOURCE_FILES[source_key].name, filename)
        self.assertIn("partner_stability_country_slope_distribution", site.FIGURES)
        self.assertIn("partner_stability_largest_endpoint_changes", site.FIGURES)
        for filename in [
            "partner_gini_stability_country_flow.csv",
            "partner_gini_stability_summary.csv",
            "partner_gini_stability_common_trend_models.csv",
            "partner_gini_stability_variance_decomposition.csv",
            "partner_gini_stability_low_active_partner_sensitivity.csv",
            "partner_gini_stability.md",
            "partner_gini_stability_adversarial_review.md",
            "run_manifest_partner_gini_stability.json",
        ]:
            self.assertIn(filename, site.DOWNLOADS)

    def test_partner_stability_page_is_rd2_only(self) -> None:
        context = defaultdict(str)
        site.configure_site_sample("rd2_countries")
        rd2_pages = site.render_pages(context)
        self.assertIn("partner-stability.html", rd2_pages)
        self.assertIn("Partner stability", site.nav("partner-stability"))
        self.assertIn("Partner Gini Is Mostly Stable", rd2_pages["partner-stability.html"])
        self.assertIn("partner_gini_stability_country_flow.csv", rd2_pages["partner-stability.html"])
        self.assertIn("partner_gini_stability_low_active_partner_sensitivity.csv", rd2_pages["partner-stability.html"])
        self.assertIn("partner_gini_stability_adversarial_review.md", rd2_pages["partner-stability.html"])
        self.assertIn("run_manifest_partner_gini_stability.json", rd2_pages["partner-stability.html"])

        site.configure_site_sample("prof_p_33")
        self.assertNotIn("partner-stability.html", site.render_pages(context))
        self.assertNotIn("partner_stability_summary", site.SOURCE_FILES)
        self.assertNotIn("partner_gini_stability_summary.csv", site.DOWNLOADS)

        site.configure_site_sample("world_broad")
        self.assertNotIn("partner-stability.html", site.render_pages(context))
        self.assertNotIn("partner_stability_summary", site.SOURCE_FILES)
        self.assertNotIn("partner_gini_stability_summary.csv", site.DOWNLOADS)
        site.configure_site_sample("rd2_countries")

    def test_rd2_site_requires_three_metric_artifacts_and_review(self) -> None:
        site.configure_site_sample("rd2_countries")
        for key in [
            "three_metric_validation",
            "three_metric_headline",
            "three_metric_yearly",
            "three_metric_rankings",
            "three_metric_ex02",
            "three_metric_ex03",
            "three_metric_ex04",
            "three_metric_ex06",
            "three_metric_ex10",
            "three_metric_ex11",
            "three_metric_ex12",
        ]:
            self.assertIn(key, site.SOURCE_FILES)
            self.assertIn("results/samples/rd2_countries/three_metric_tables", str(site.SOURCE_FILES[key]))
        self.assertIn("cadot_three_metric_manifest.json", site.DOWNLOADS)
        self.assertIn("three_metric_adversarial_review.md", site.DOWNLOADS)

        site.configure_site_sample("world_broad")
        self.assertNotIn("three_metric_validation", site.SOURCE_FILES)
        self.assertNotIn("cadot_three_metric_manifest.json", site.DOWNLOADS)
        site.configure_site_sample("rd2_countries")

    def test_publication_validation_blocks_missing_three_metric_artifact(self) -> None:
        site.configure_site_sample("rd2_countries")
        original_sources = dict(site.SOURCE_FILES)
        original_downloads = dict(site.DOWNLOADS)
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "three_metric_tables" / "validation_checks.csv"
            try:
                site.SOURCE_FILES = {"three_metric_validation": missing}
                site.DOWNLOADS = {}
                with self.assertRaisesRegex(FileNotFoundError, "three_metric_tables/validation_checks.csv"):
                    site.validate_publication_inputs()
            finally:
                site.SOURCE_FILES = original_sources
                site.DOWNLOADS = original_downloads
                site.configure_site_sample("rd2_countries")

    def test_exercise_first_pages_have_metric_sections(self) -> None:
        fake_rows = {
            "headline": [
                {
                    "country": "India",
                    "year": 2024,
                    "flow": "Exports",
                    "dimension": "product",
                    "gini": 0.9,
                    "theil": 3.2,
                    "hhi": 0.2,
                }
            ],
            "ex02": [
                {
                    "metric": "gini",
                    "flow": "Exports",
                    "horizon": 5,
                    "concentration_bucket": "high_product_high_partner",
                    "observations": 10,
                    "countries": 3,
                    "mean_annualized_trade_growth_log": 0.02,
                }
            ],
            "ex03": [
                {
                    "country": "India",
                    "import_bin": "energy",
                    "import_value_share": 0.1,
                    "gini": 0.8,
                    "theil_active": 1.5,
                    "hhi": 0.3,
                }
            ],
            "ex04": [
                {
                    "country": "India",
                    "year": 2024,
                    "import_products": 100,
                    "weighted_mean_top_supplier_share": 0.6,
                    "weighted_mean_source_hhi": 0.4,
                    "share_products_top_supplier_ge_75": 0.2,
                }
            ],
            "ex06": [
                {
                    "country": "India",
                    "flow": "Imports",
                    "dimension": "product",
                    "variant": "baseline",
                    "trade_share_removed": 0.0,
                    "gini": 0.8,
                    "theil": 2.0,
                    "hhi": 0.1,
                }
            ],
            "ex10": [
                {
                    "country": "India",
                    "flow": "Exports",
                    "benchmark_null": "active_count_random_allocation",
                    "actual_minus_sim_median_gini": 0.1,
                    "actual_minus_sim_median_theil": 0.2,
                    "actual_minus_sim_median_hhi": 0.03,
                }
            ],
            "ex11": [
                {
                    "metric": "gini",
                    "flow": "Imports",
                    "country": "India",
                    "cmd_code": "854231",
                    "abs_loo_contribution": 0.02,
                }
            ],
            "ex12": [
                {
                    "metric": "hhi",
                    "flow": "Exports",
                    "horizon": 5,
                    "base_concentration_bucket": "high_product_concentration",
                    "observations": 10,
                    "countries": 3,
                    "mean_annualized_trade_growth_log": 0.02,
                }
            ],
        }
        payload = {"manifest": {"sample_window": {"start_year": 1988, "end_year": 2025}}, **fake_rows}
        index, pages, ex12_metric = site.build_exercise_first_pages(payload)
        self.assertEqual(
            {f"exercise-{spec['short']}.html" for spec in site.EXERCISE_PAGE_SPECS},
            set(pages),
        )
        for spec in site.EXERCISE_PAGE_SPECS:
            filename = f"exercise-{spec['short']}.html"
            self.assertIn(filename, index)
            html = pages[filename]
            self.assertIn("Framing", html)
            self.assertIn("Gini / Theil / HHI Results", html)
            self.assertIn(">Gini<", html)
            self.assertIn(">Theil<", html)
            self.assertIn(">HHI<", html)
        self.assertIn("Gini / Theil / HHI Results", ex12_metric)


if __name__ == "__main__":
    unittest.main()
