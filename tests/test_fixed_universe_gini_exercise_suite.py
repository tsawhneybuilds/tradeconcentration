from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from run_fixed_universe_gini_exercise_suite import (  # noqa: E402
    add_fixed_buckets,
    applicability_matrix,
    key_coefficients,
    merge_ex11_with_controls,
)


class FixedUniverseGiniExerciseSuiteTests(unittest.TestCase):
    def test_ex11_control_merge_is_flow_specific(self) -> None:
        ex11_country_year = pd.DataFrame({"reporter_code": [1], "year": [2020], "intermediate_import_share": [0.4]})
        fixed = pd.DataFrame(
            {
                "reporter_code": [1, 1],
                "year": [2020, 2020],
                "flow": ["Exports", "Imports"],
                "fixed_universe_product_gini": [0.8, 0.7],
            }
        )
        controls_by_flow = {
            "Exports": pd.DataFrame(
                {
                    "reporter_code": [1],
                    "year": [2020],
                    "product_gini": [0.11],
                    "log_population": [2.0],
                    "log_gdp_per_capita": [3.0],
                }
            ),
            "Imports": pd.DataFrame(
                {
                    "reporter_code": [1],
                    "year": [2020],
                    "product_gini": [0.22],
                    "log_population": [2.0],
                    "log_gdp_per_capita": [3.0],
                }
            ),
        }

        export_out = merge_ex11_with_controls(ex11_country_year, fixed, controls_by_flow, "Exports")
        import_out = merge_ex11_with_controls(ex11_country_year, fixed, controls_by_flow, "Imports")

        self.assertAlmostEqual(export_out.loc[0, "fixed_universe_product_gini"], 0.8)
        self.assertAlmostEqual(export_out.loc[0, "product_gini"], 0.11)
        self.assertAlmostEqual(import_out.loc[0, "fixed_universe_product_gini"], 0.7)
        self.assertAlmostEqual(import_out.loc[0, "product_gini"], 0.22)

    def test_add_fixed_buckets_uses_flow_year_medians(self) -> None:
        panel = pd.DataFrame(
            {
                "flow": ["Exports", "Exports", "Exports", "Exports"],
                "year": [2020, 2020, 2021, 2021],
                "fixed_universe_product_gini": [0.2, 0.8, 0.9, 0.1],
                "partner_gini": [0.9, 0.1, 0.8, 0.2],
                "product_gini": [0.3, 0.7, 0.8, 0.2],
            }
        )

        out = add_fixed_buckets(panel)

        self.assertEqual(out.loc[0, "fixed_concentration_bucket"], "low_product_high_partner")
        self.assertEqual(out.loc[1, "fixed_concentration_bucket"], "high_product_low_partner")
        self.assertEqual(out.loc[2, "fixed_concentration_bucket"], "high_product_high_partner")
        self.assertEqual(out.loc[3, "fixed_concentration_bucket"], "low_product_low_partner")

    def test_key_coefficients_filters_interest_terms_and_adds_bh_flags(self) -> None:
        models = pd.DataFrame(
            {
                "exercise_family": ["country_size", "country_size", "growth_effect"],
                "term": ["log_population", "irrelevant", "prior_export_growth"],
                "p_value": [0.01, 0.02, 0.20],
            }
        )

        out = key_coefficients(models)

        self.assertEqual(set(out["term"]), {"log_population", "prior_export_growth"})
        self.assertTrue(out.loc[out["term"].eq("log_population"), "significant_5pct"].iloc[0])
        self.assertIn("family_bh_q_value", out.columns)

    def test_applicability_matrix_names_non_direct_exercises(self) -> None:
        matrix = applicability_matrix()

        self.assertIn("exercise_03_import_bins", set(matrix["exercise"]))
        self.assertIn("requires_new_product_level_design", set(matrix["fixed_universe_status"]))
        self.assertIn("exercise_01_descriptive", set(matrix["exercise"]))
        self.assertIn("direct_rerun_completed", set(matrix["fixed_universe_status"]))


if __name__ == "__main__":
    unittest.main()
