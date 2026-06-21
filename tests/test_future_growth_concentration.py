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

import run_future_growth_concentration as fgc


def synthetic_concentration() -> pd.DataFrame:
    rows = []
    countries = [("AAA", 1, "Country A"), ("BBB", 2, "Country B")]
    for iso3, reporter_code, country in countries:
        high = reporter_code == 2
        for year in [2000, 2001]:
            for flow in ["Exports", "Imports"]:
                rows.append(
                    {
                        "country": country,
                        "iso3": iso3,
                        "reporter_code": reporter_code,
                        "year": year,
                        "flow": flow,
                        "variant": "baseline",
                        "total_trade_value": 100.0,
                        "product_gini": 0.8 if high else 0.2,
                        "partner_gini": 0.3 if high else 0.7,
                        "product_partner_cell_gini": 0.6 if high else 0.4,
                        "product_top_1pct_share": 0.5 if high else 0.1,
                        "partner_top_1pct_share": 0.4 if high else 0.2,
                        "product_partner_cell_top_1pct_share": 0.45 if high else 0.15,
                        "product_top_5pct_share": 0.6 if high else 0.2,
                        "partner_top_5pct_share": 0.5 if high else 0.3,
                        "product_partner_cell_top_5pct_share": 0.55 if high else 0.25,
                        "product_active_count": 10 + reporter_code + (year - 2000),
                        "partner_active_count": 5 + reporter_code + (year - 2000),
                        "product_partner_cell_active_count": 50 + reporter_code + (year - 2000),
                    }
                )
    return pd.DataFrame(rows)


def synthetic_export_totals() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "country": ["Country A"] * 4 + ["Country B"] * 4,
            "iso3": ["AAA"] * 4 + ["BBB"] * 4,
            "reporter_code": [1] * 4 + [2] * 4,
            "year": [1999, 2000, 2001, 2002] * 2,
            "total_exports": [80.0, 100.0, 150.0, 200.0, 40.0, 100.0, 50.0, 25.0],
            "oil_exports": [0.0, 10.0, 15.0, 20.0, 0.0, 5.0, 5.0, 5.0],
            "oil_export_share": [0.0, 0.1, 0.1, 0.1, 0.0, 0.05, 0.1, 0.2],
            "total_exports_ex_oil": [80.0, 90.0, 135.0, 180.0, 40.0, 95.0, 45.0, 20.0],
        }
    )


def synthetic_controls() -> pd.DataFrame:
    rows = []
    for iso3 in ["AAA", "BBB"]:
        for year in [2000, 2001]:
            rows.append(
                {
                    "iso3": iso3,
                    "year": year,
                    "gdp_current_usd": 1000.0 + year,
                    "gdp_constant_2015_usd": 900.0 + year,
                    "population": 100.0,
                    "gni_per_capita_current_usd": 10.0,
                    "gni_per_capita_constant_2015_usd": 9.0,
                    "region": "Unit",
                    "income_group": "Unit",
                    "metadata_source": "unit",
                }
            )
    return pd.DataFrame(rows)


def synthetic_deflator() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "year": [1999, 2000, 2001, 2002, 2003],
            "us_gdp_deflator": [100.0, 100.0, 125.0, 200.0, 200.0],
        }
    )


class FutureGrowthConcentrationTests(unittest.TestCase):
    def test_future_growth_uses_exact_future_year_and_horizon(self) -> None:
        panel = fgc.construct_future_growth_panel(
            synthetic_concentration(),
            synthetic_export_totals(),
            synthetic_controls(),
            synthetic_deflator(),
            horizons=[1, 2],
        )
        row = panel[
            panel["iso3"].eq("AAA")
            & panel["year"].eq(2000)
            & panel["horizon"].eq(2)
            & panel["flow"].eq("Exports")
        ].iloc[0]
        self.assertAlmostEqual(row[fgc.PRIMARY_OUTCOME], (np.log(100.0) - np.log(100.0)) / 2.0)
        self.assertAlmostEqual(row[fgc.NOMINAL_OUTCOME], (np.log(200.0) - np.log(100.0)) / 2.0)
        self.assertAlmostEqual(row[fgc.DOLLAR_CHANGE_OUTCOME], 0.0)
        self.assertAlmostEqual(row[fgc.ASINH_CHANGE_OUTCOME], 0.0)
        self.assertEqual(row["future_year"], 2002)
        self.assertAlmostEqual(row[fgc.PRIOR_GROWTH_CONTROL], np.log(100.0) - np.log(80.0))

    def test_future_growth_adds_active_count_change_outcomes(self) -> None:
        panel = fgc.construct_future_growth_panel(
            synthetic_concentration(),
            synthetic_export_totals(),
            synthetic_controls(),
            synthetic_deflator(),
            horizons=[1],
        )
        row = panel[
            panel["iso3"].eq("AAA")
            & panel["year"].eq(2000)
            & panel["horizon"].eq(1)
            & panel["flow"].eq("Exports")
        ].iloc[0]
        self.assertAlmostEqual(row["future_product_active_count"], 12.0)
        self.assertAlmostEqual(row["annualized_log_product_active_count_change"], np.log(12.0) - np.log(11.0))
        self.assertAlmostEqual(row["annualized_log_partner_active_count_change"], np.log(7.0) - np.log(6.0))

    def test_missing_future_year_is_not_filled_or_interpolated(self) -> None:
        totals = synthetic_export_totals()
        totals = totals[~totals["year"].eq(2002)].copy()
        panel = fgc.construct_future_growth_panel(
            synthetic_concentration(),
            totals,
            synthetic_controls(),
            synthetic_deflator(),
            horizons=[2],
        )
        row = panel[
            panel["iso3"].eq("AAA")
            & panel["year"].eq(2001)
            & panel["horizon"].eq(2)
            & panel["flow"].eq("Exports")
        ].iloc[0]
        self.assertTrue(np.isnan(row[fgc.PRIMARY_OUTCOME]))
        self.assertTrue(np.isnan(row["future_exports"]))

    def test_duplicate_export_total_keys_raise(self) -> None:
        totals = pd.concat([synthetic_export_totals(), synthetic_export_totals().head(1)], ignore_index=True)
        with self.assertRaisesRegex(RuntimeError, "duplicate"):
            fgc.construct_future_growth_panel(
            synthetic_concentration(),
            totals,
            synthetic_controls(),
            synthetic_deflator(),
            horizons=[1],
        )

    def test_import_and_export_exposures_are_preserved(self) -> None:
        panel = fgc.construct_future_growth_panel(
            synthetic_concentration(),
            synthetic_export_totals(),
            synthetic_controls(),
            synthetic_deflator(),
            horizons=[1],
        )
        exp = panel[panel["flow"].eq("Exports")].iloc[0]
        imp = panel[panel["flow"].eq("Imports")].iloc[0]
        self.assertEqual(set(panel["flow"]), {"Exports", "Imports"})
        self.assertEqual(exp["product_gini"], imp["product_gini"])
        self.assertEqual(exp["future_exports"], imp["future_exports"])

    def test_bucket_classification_uses_flow_year_medians(self) -> None:
        panel = fgc.construct_future_growth_panel(
            synthetic_concentration(),
            synthetic_export_totals(),
            synthetic_controls(),
            synthetic_deflator(),
            horizons=[1],
        )
        a = panel[panel["iso3"].eq("AAA") & panel["flow"].eq("Exports")].iloc[0]
        b = panel[panel["iso3"].eq("BBB") & panel["flow"].eq("Exports")].iloc[0]
        self.assertEqual(a["concentration_bucket"], "low_product_high_partner")
        self.assertEqual(b["concentration_bucket"], "high_product_low_partner")

    def test_bucket_summary_reports_size_adjusted_growth(self) -> None:
        rows = []
        for idx in range(20):
            year = 2000 + (idx % 2)
            low_base_bucket = idx < 10
            log_initial = 8.0 if low_base_bucket else 12.0
            rows.append(
                {
                    "flow": "Exports",
                    "horizon": 5,
                    "concentration_bucket": "high_product_low_partner" if low_base_bucket else "low_product_low_partner",
                    "reporter_code": idx,
                    fgc.PRIMARY_OUTCOME: 0.20 - 0.01 * log_initial + (0.02 if year == 2001 else 0.0),
                    "real_export_growth_pct": 0.0,
                    "base_exports_constant_2015_usd": float(np.exp(log_initial)),
                    "log_initial_exports_constant_2015_usd": log_initial,
                    "oil_export_share": 0.0,
                    "log_gdp_constant_2015_usd": log_initial + 4.0,
                    "log_population": 2.0 + 0.1 * idx,
                    "log_gni_per_capita_constant_2015_usd": log_initial + 1.0,
                    "year": year,
                }
            )
        summary = fgc.bucket_summary(pd.DataFrame(rows))
        high_low = summary[summary["concentration_bucket"].eq("high_product_low_partner")].iloc[0]
        low_low = summary[summary["concentration_bucket"].eq("low_product_low_partner")].iloc[0]
        raw_gap = high_low["mean_annualized_log_growth"] - low_low["mean_annualized_log_growth"]
        adjusted_gap = (
            high_low["mean_size_adjusted_annualized_log_growth"]
            - low_low["mean_size_adjusted_annualized_log_growth"]
        )
        self.assertGreater(abs(raw_gap), 0.01)
        self.assertAlmostEqual(adjusted_gap, 0.0, places=10)
        self.assertEqual(high_low["size_adjusted_observations"], 10)

    def test_base_size_bins_are_year_flow_horizon_specific(self) -> None:
        rows = []
        for reporter in range(1, 11):
            rows.append(
                {
                    "reporter_code": reporter,
                    "year": 2000,
                    "horizon": 5,
                    "flow": "Exports",
                    "log_initial_exports_constant_2015_usd": float(reporter),
                    "concentration_bucket": "high_product_low_partner" if reporter <= 5 else "low_product_low_partner",
                    fgc.PRIMARY_OUTCOME: 0.01 * reporter,
                    fgc.SIZE_ADJUSTED_OUTCOME: 0.01 * reporter,
                    fgc.DOLLAR_CHANGE_OUTCOME: 100.0 * reporter,
                    fgc.ASINH_CHANGE_OUTCOME: 0.01 * reporter,
                    "base_exports_constant_2015_usd": float(np.exp(reporter)),
                }
            )
        binned = fgc.add_base_size_bins(pd.DataFrame(rows))
        first = binned[binned["reporter_code"].eq(1)].iloc[0]
        third = binned[binned["reporter_code"].eq(3)].iloc[0]
        last = binned[binned["reporter_code"].eq(10)].iloc[0]
        self.assertEqual(first["base_size_bin"], "Q1")
        self.assertTrue(first["bottom_10pct_base_exports"])
        self.assertFalse(third["bottom_25pct_base_exports"])
        self.assertEqual(last["base_size_bin"], "Q5")
        summary = fgc.base_size_bin_summary(binned)
        self.assertIn("mean_annualized_asinh_real_export_change", summary.columns)

    def test_mechanism_channel_merge_uses_country_window_keys(self) -> None:
        panel = pd.DataFrame(
            [
                {
                    "reporter_code": 1,
                    "year": 2000,
                    "future_year": 2005,
                    "horizon": 5,
                    "flow": "Exports",
                    "concentration_bucket": "high_product_low_partner",
                },
                {
                    "reporter_code": 1,
                    "year": 2000,
                    "future_year": 2005,
                    "horizon": 5,
                    "flow": "Imports",
                    "concentration_bucket": "high_product_low_partner",
                },
            ]
        )
        channels = pd.DataFrame(
            [
                {
                    "reporter_code": 1,
                    "base_year": 2000,
                    "future_year": 2005,
                    "horizon": 5,
                    "net_new_product_gross_positive_share": 0.25,
                    "new_partner_existing_product_gross_positive_share": 0.10,
                }
            ]
        )
        merged = fgc.merge_mechanism_channels(panel, channels)
        self.assertEqual(len(merged), 2)
        self.assertTrue(merged["net_new_product_gross_positive_share"].eq(0.25).all())
        self.assertTrue(merged["new_partner_existing_product_gross_positive_share"].eq(0.10).all())

    def test_paired_model_outputs_product_partner_and_interaction_terms(self) -> None:
        rows = []
        for country in range(8):
            for year in range(2000, 2005):
                for flow in ["Exports", "Imports"]:
                    product = 0.1 + country * 0.03
                    partner = 0.2 + (year - 2000) * 0.02
                    rows.append(
                        {
                            "reporter_code": country,
                            "iso3": f"C{country:03d}",
                            "year": year,
                            "horizon": 1,
                            "flow": flow,
                            fgc.PRIMARY_OUTCOME: 0.5 * product - 0.2 * partner + 0.01 * country,
                            "product_gini": product,
                            "partner_gini": partner,
                            "product_top_1pct_share": product,
                            "partner_top_1pct_share": partner,
                            "product_top_5pct_share": product,
                            "partner_top_5pct_share": partner,
                            "log_initial_exports_constant_2015_usd": 10.0 + country,
                            "oil_export_share": 0.0,
                            "log_gdp_constant_2015_usd": 12.0 + country,
                            "log_population": 6.0 + country * 0.1,
                            "log_gni_per_capita_constant_2015_usd": 8.0,
                        }
                    )
        out = fgc.run_paired_models(pd.DataFrame(rows), "unit")
        terms = set(out["term"])
        self.assertTrue({"product_exposure", "partner_exposure", "product_x_partner"}.issubset(terms))
        self.assertIn("horizon", out.columns)
        self.assertTrue(out["model_label"].eq("paired_product_partner").all())


if __name__ == "__main__":
    unittest.main()
