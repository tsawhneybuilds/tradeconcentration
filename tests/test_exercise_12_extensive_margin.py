from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from run_exercise_12_extensive_margin import (  # noqa: E402
    CountryInfo,
    compute_mutually_exclusive_decomposition,
    compute_overlapping_robustness,
    compute_product_entry_robustness,
    country_weighted_summary_rows,
    read_product_partner_for_reporter,
)
from build_trade_gini_site import validate_ex12_extensive_validation  # noqa: E402


class Exercise12ExtensiveMarginTests(unittest.TestCase):
    def synthetic_cells(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {"reporter_code": 1, "year": 2000, "product_id": "A", "partner_code": 1, "trade_value": 100.0},
                {"reporter_code": 1, "year": 2000, "product_id": "A", "partner_code": 2, "trade_value": 20.0},
                {"reporter_code": 1, "year": 2000, "product_id": "B", "partner_code": 1, "trade_value": 50.0},
                {"reporter_code": 1, "year": 2005, "product_id": "A", "partner_code": 1, "trade_value": 140.0},
                {"reporter_code": 1, "year": 2005, "product_id": "A", "partner_code": 2, "trade_value": 5.0},
                {"reporter_code": 1, "year": 2005, "product_id": "A", "partner_code": 3, "trade_value": 30.0},
                {"reporter_code": 1, "year": 2005, "product_id": "B", "partner_code": 2, "trade_value": 70.0},
                {"reporter_code": 1, "year": 2005, "product_id": "C", "partner_code": 1, "trade_value": 80.0},
            ]
        )

    def test_mutually_exclusive_channels_sum_to_total_growth(self) -> None:
        country = CountryInfo(1, "Testland", "TST")
        out = compute_mutually_exclusive_decomposition(self.synthetic_cells(), country, "hs6_harmonized_family", [5])
        contributions = out.set_index("category")["net_contribution"]
        self.assertAlmostEqual(float(contributions["net_new_product"]), 80.0)
        self.assertAlmostEqual(float(contributions["net_new_partner_existing_product"]), 30.0)
        self.assertAlmostEqual(float(contributions["new_product_partner_cell_existing_product_partner"]), 70.0)
        self.assertAlmostEqual(float(contributions["existing_product_partner_cell_growth"]), 40.0)
        self.assertAlmostEqual(float(contributions["existing_product_partner_cell_contraction"]), -65.0)
        self.assertAlmostEqual(float(contributions.sum()), 155.0)
        self.assertAlmostEqual(float(out["total_growth"].iloc[0]), 155.0)
        self.assertAlmostEqual(float(out["gross_positive_contribution"].sum()), 220.0)

    def test_overlapping_robustness_is_nonexclusive(self) -> None:
        country = CountryInfo(1, "Testland", "TST")
        out = compute_overlapping_robustness(self.synthetic_cells(), country, "hs6_harmonized_family", [5])
        values = out.set_index("overlap_channel")["gross_positive_contribution"]
        self.assertAlmostEqual(float(values["future_cells_with_new_product"]), 80.0)
        self.assertAlmostEqual(float(values["future_cells_with_new_partner"]), 30.0)
        self.assertAlmostEqual(float(values["future_cells_with_new_product_partner_cell"]), 180.0)
        self.assertAlmostEqual(float(values["future_new_cell_existing_product_partner"]), 70.0)

    def test_product_entry_robustness_keeps_low_base_definitions(self) -> None:
        country = CountryInfo(1, "Testland", "TST")
        cells = pd.DataFrame(
            [
                {"reporter_code": 1, "year": 2000, "product_id": "A", "partner_code": 1, "trade_value": 100000.0},
                {"reporter_code": 1, "year": 2005, "product_id": "A", "partner_code": 1, "trade_value": 120000.0},
                {"reporter_code": 1, "year": 2000, "product_id": "B", "partner_code": 1, "trade_value": 50000.0},
                {"reporter_code": 1, "year": 2005, "product_id": "B", "partner_code": 1, "trade_value": 45000.0},
                {"reporter_code": 1, "year": 2000, "product_id": "D", "partner_code": 1, "trade_value": 5000.0},
                {"reporter_code": 1, "year": 2005, "product_id": "D", "partner_code": 1, "trade_value": 20000.0},
                {"reporter_code": 1, "year": 2005, "product_id": "E", "partner_code": 1, "trade_value": 80000.0},
            ]
        )
        out = compute_product_entry_robustness(cells, country, "hs6_harmonized_family", [5])
        contributions = out.set_index("product_definition")["net_contribution"]
        self.assertAlmostEqual(float(contributions["strict_zero_base_product"]), 80000.0)
        self.assertAlmostEqual(float(contributions["low_base_under_10k_grower"]), 15000.0)
        self.assertIn("least_traded_10pct_grower", contributions.index)

    def test_reader_filters_world_partner_and_hs6_999999(self) -> None:
        rows = pd.DataFrame(
            [
                {
                    "reporter_code": 1,
                    "year": 2000,
                    "dimension": "product_partner_cell",
                    "classification_code": "H2",
                    "cmd_code": "010101",
                    "partner_code": 2,
                    "trade_value": 100.0,
                },
                {
                    "reporter_code": 1,
                    "year": 2000,
                    "dimension": "product_partner_cell",
                    "classification_code": "H2",
                    "cmd_code": "999999",
                    "partner_code": 2,
                    "trade_value": 50.0,
                },
                {
                    "reporter_code": 1,
                    "year": 2000,
                    "dimension": "product_partner_cell",
                    "classification_code": "H2",
                    "cmd_code": "020202",
                    "partner_code": 0,
                    "trade_value": 75.0,
                },
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "aggregate.parquet"
            rows.to_parquet(path, index=False)
            out = read_product_partner_for_reporter(path, 1)
        self.assertEqual(len(out), 1)
        self.assertEqual(out.iloc[0]["cmd_code"], "010101")
        self.assertEqual(int(out.iloc[0]["partner_code"]), 2)

    def test_country_weighted_summary_gives_each_reporter_equal_weight(self) -> None:
        rows = []
        for base_year, share in [(2000, 0.1), (2001, 0.9)]:
            rows.append(
                {
                    "reporter_code": 1,
                    "country": "Long Coverage",
                    "iso3": "LNG",
                    "identity_mode": "hs6_harmonized_family",
                    "horizon": 5,
                    "base_year": base_year,
                    "future_year": base_year + 5,
                    "category": "net_new_product",
                    "category_label": "Net-new products",
                    "category_order": 1,
                    "net_contribution": share,
                    "gross_positive_contribution": share,
                    "gross_contraction": 0.0,
                    "net_growth_share": share,
                    "gross_positive_share": share,
                    "gross_contraction_share": 0.0,
                    "cell_count": 1,
                    "product_count": 1,
                    "partner_count": 1,
                }
            )
        rows.append(
            {
                "reporter_code": 2,
                "country": "Short Coverage",
                "iso3": "SHT",
                "identity_mode": "hs6_harmonized_family",
                "horizon": 5,
                "base_year": 2000,
                "future_year": 2005,
                "category": "net_new_product",
                "category_label": "Net-new products",
                "category_order": 1,
                "net_contribution": 0.3,
                "gross_positive_contribution": 0.3,
                "gross_contraction": 0.0,
                "net_growth_share": 0.3,
                "gross_positive_share": 0.3,
                "gross_contraction_share": 0.0,
                "cell_count": 1,
                "product_count": 1,
                "partner_count": 1,
            }
        )
        summary = country_weighted_summary_rows(pd.DataFrame(rows))
        value = float(summary.iloc[0]["median_country_median_gross_positive_share"])
        self.assertAlmostEqual(value, 0.4)
        self.assertEqual(int(summary.iloc[0]["countries"]), 2)

    def test_site_validation_rejects_blocked_exercise_12_artifacts(self) -> None:
        latest = pd.DataFrame({"reporter_code": [1, 1], "horizon": [5, 10]})
        mode_horizon_frame = pd.DataFrame(
            {
                "identity_mode": ["hs6_harmonized_family", "hs4", "hs2"],
                "horizon": [5, 10, 5],
            }
        )
        validation = {
            "status": "blocked",
            "blockers": ["test blocker"],
            "country_count_expected": 1,
            "country_count_decomposition": 1,
            "country_count_latest": 1,
            "identity_modes": ["hs6_harmonized_family", "hs4", "hs2"],
            "horizons": [5, 10],
            "source_hs6_999999_rows_after_filters": 0,
            "source_partner_code_0_rows_after_filters": 0,
            "duplicate_category_keys": 0,
            "category_accounting_residual_violations": 0,
            "hs_harmonization_missing_rows": 0,
        }
        with self.assertRaises(RuntimeError):
            validate_ex12_extensive_validation(
                validation,
                latest=latest,
                summary=mode_horizon_frame,
                country_weighted_summary=mode_horizon_frame,
                product_robustness=mode_horizon_frame,
                overlapping=mode_horizon_frame,
                expected_country_count=1,
            )


if __name__ == "__main__":
    unittest.main()
