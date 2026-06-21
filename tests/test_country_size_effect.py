from __future__ import annotations

import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_country_size_effect as cse


class CountrySizeEffectTests(unittest.TestCase):
    def test_benjamini_hochberg_adjustment_is_monotone_in_sorted_pvalues(self) -> None:
        p_values = pd.Series([0.03, 0.001, np.nan, 0.02, 0.20], index=list("abcde"))
        q_values = cse.benjamini_hochberg(p_values)
        ordered = q_values.dropna().loc[p_values.dropna().sort_values().index]
        self.assertTrue(np.all(np.diff(ordered.to_numpy()) >= -1e-12))
        self.assertTrue(((q_values.dropna() >= 0) & (q_values.dropna() <= 1)).all())
        self.assertTrue(np.isnan(q_values.loc["c"]))

    def test_cluster_robust_covariance_has_expected_shape_and_finite_values(self) -> None:
        x = np.column_stack([np.ones(8), np.arange(8, dtype=float)])
        resid = np.array([0.2, -0.1, 0.0, 0.1, -0.2, 0.3, -0.1, -0.2])
        clusters = pd.Series(["A", "A", "B", "B", "C", "C", "D", "D"])
        cov = cse.cluster_robust_covariance(x, resid, clusters)
        self.assertEqual(cov.shape, (2, 2))
        self.assertTrue(np.isfinite(cov).all())
        self.assertTrue(np.allclose(cov, cov.T))

    def test_two_way_cluster_covariance_has_expected_shape_and_finite_values(self) -> None:
        x = np.column_stack([np.ones(12), np.arange(12, dtype=float), np.tile([0.0, 1.0, 2.0], 4)])
        resid = np.array([0.2, -0.1, 0.0, 0.1, -0.2, 0.3, -0.1, -0.2, 0.4, -0.3, 0.1, -0.2])
        countries = pd.Series(np.repeat(["A", "B", "C", "D"], 3))
        years = pd.Series(np.tile([2000, 2001, 2002], 4))
        cov = cse.two_way_cluster_robust_covariance(x, resid, countries, years)
        self.assertEqual(cov.shape, (3, 3))
        self.assertTrue(np.isfinite(cov).all())
        self.assertTrue(np.allclose(cov, cov.T))

    def test_population_size_variables_use_first_and_average_country_years(self) -> None:
        panel = pd.DataFrame(
            {
                "iso3": ["AAA", "AAA", "BBB", "BBB"],
                "year": [2001, 2000, 2000, 2002],
                "population": [121.0, 100.0, 25.0, 36.0],
                "gdp_current_usd": [1210.0, 1000.0, 250.0, 720.0],
            }
        )
        out = cse.construct_population_size_variables(panel)
        aaa = out[out["iso3"].eq("AAA")]
        bbb = out[out["iso3"].eq("BBB")]
        self.assertTrue(np.allclose(aaa["baseline_log_population"], np.log(100.0)))
        self.assertTrue(np.allclose(bbb["baseline_log_population"], np.log(25.0)))
        self.assertTrue(np.allclose(aaa["average_log_population"], np.mean([np.log(100.0), np.log(121.0)])))
        self.assertTrue(np.allclose(out["log_gdp_per_capita"], out["log_gdp_current_usd"] - out["log_population"]))

    def test_gmm_lag_instruments_use_exact_calendar_lags(self) -> None:
        panel = pd.DataFrame(
            {
                "iso3": ["AAA", "AAA", "AAA", "AAA", "AAA", "AAA"],
                "year": [2000, 2000, 2001, 2001, 2003, 2003],
                "flow": ["Exports", "Imports", "Exports", "Imports", "Exports", "Imports"],
                "log_population": [1.0, 1.0, 1.2, 1.2, 1.6, 1.6],
                "log_gdp_per_capita": [8.0, 8.0, 8.1, 8.1, 8.5, 8.5],
            }
        )
        out = cse.construct_gmm_lag_instruments(panel)
        row_2003 = out[(out["year"].eq(2003)) & out["flow"].eq("Exports")].iloc[0]
        self.assertAlmostEqual(row_2003["lag2_log_population"], 1.2)
        self.assertAlmostEqual(row_2003["lag3_log_population"], 1.0)
        self.assertAlmostEqual(row_2003["lag2_log_gdp_per_capita"], 8.1)
        self.assertAlmostEqual(row_2003["lag3_log_gdp_per_capita"], 8.0)
        row_2001 = out[(out["year"].eq(2001)) & out["flow"].eq("Exports")].iloc[0]
        self.assertTrue(np.isnan(row_2001["lag2_log_population"]))

    def synthetic_gmm_panel(self, countries: int = 45, years: range = range(2000, 2012)) -> pd.DataFrame:
        rng = np.random.default_rng(20260527)
        rows = []
        for country in range(countries):
            iso3 = f"C{country:03d}"
            reporter_code = country + 1
            pop_state = rng.normal()
            gdp_state = rng.normal()
            for year in years:
                t = year - min(years)
                pop_state = 0.88 * pop_state + 0.12 * rng.normal() + 0.015 * t
                gdp_state = 0.82 * gdp_state + 0.18 * rng.normal() + 0.010 * t
                log_population = 2.0 + pop_state
                log_gdp_per_capita = 8.0 + gdp_state
                year_shift = 0.02 * t
                noise = rng.normal(scale=0.015)
                base_outcome = 0.8 * log_population - 0.4 * log_gdp_per_capita + year_shift + noise
                for flow in cse.FLOWS:
                    row = {
                        "iso3": iso3,
                        "reporter_code": reporter_code,
                        "year": year,
                        "flow": flow,
                        "log_population": log_population,
                        "log_gdp_per_capita": log_gdp_per_capita,
                    }
                    for idx, (_dimension, _metric, outcome, _label) in enumerate(cse.OUTCOME_SPECS):
                        row[outcome] = base_outcome + 0.001 * idx + (0.002 if flow == "Imports" else 0.0)
                    rows.append(row)
        return cse.construct_gmm_lag_instruments(pd.DataFrame(rows))

    def test_lag_iv_gmm_output_has_model_and_first_stage_rows(self) -> None:
        panel = self.synthetic_gmm_panel(countries=12, years=range(2000, 2008))
        models, first_stage = cse.run_lag_iv_gmm_models(panel, "unit")
        self.assertEqual(len(models), len(cse.FLOWS) * len(cse.OUTCOME_SPECS) * len(cse.GMM_ENDOG_TERMS))
        self.assertEqual(len(first_stage), len(cse.FLOWS) * len(cse.OUTCOME_SPECS) * len(cse.GMM_ENDOG_TERMS))
        self.assertTrue(set(cse.GMM_ENDOG_TERMS).issubset(set(models["term"])))
        self.assertTrue({"j_stat", "j_p_value", "instrument_count"}.issubset(models.columns))
        self.assertTrue({"partial_rsquared", "shea_rsquared", "f_stat"}.issubset(first_stage.columns))

    def test_lag_iv_gmm_recovers_known_synthetic_coefficients(self) -> None:
        panel = self.synthetic_gmm_panel()
        rows, first_stage = cse.run_single_lag_iv_gmm_model(
            panel[panel["flow"].eq("Exports")],
            outcome="product_gini",
            model_label=cse.GMM_MODEL_LABEL,
            sample="unit",
            flow="Exports",
            dimension="product",
            metric="gini",
        )
        out = pd.DataFrame(rows).set_index("term")
        self.assertTrue(out["status"].astype(str).str.startswith("ok").all())
        self.assertAlmostEqual(out.loc["log_population", "coefficient"], 0.8, delta=0.12)
        self.assertAlmostEqual(out.loc["log_gdp_per_capita", "coefficient"], -0.4, delta=0.12)
        fs = pd.DataFrame(first_stage)
        self.assertTrue(fs["status"].astype(str).str.startswith("ok").all())
        self.assertTrue(np.isfinite(fs["partial_rsquared"]).all())

    def test_ols_helper_recovers_simple_slope_with_year_fixed_effects(self) -> None:
        rows = []
        for cluster in range(6):
            for year in [2000, 2001, 2002]:
                x = float(cluster)
                year_shift = {2000: 0.0, 2001: 1.0, 2002: -1.0}[year]
                rows.append(
                    {
                        "reporter_code": cluster,
                        "year": year,
                        "outcome": 2.0 * x + 0.5 * (x**2) + year_shift,
                        "x": x,
                        "z": x**2,
                    }
                )
        df = pd.DataFrame(rows)
        result = cse.run_ols_model(
            df,
            outcome="outcome",
            terms=["x", "z"],
            fixed_effects=["year"],
            model_label="test",
            sample="unit",
            flow="Exports",
            dimension="product",
            metric="gini",
            cluster_col="reporter_code",
        )
        self.assertEqual(result.status, "ok")
        self.assertAlmostEqual(result.beta[0], 2.0, places=10)
        self.assertTrue(np.isfinite(result.se[0]))
        self.assertEqual(result.clusters, 6)

    def test_ols_helper_supports_two_way_clustered_standard_errors(self) -> None:
        rows = []
        for cluster in range(6):
            for year in [2000, 2001, 2002, 2003]:
                x = float(cluster)
                rows.append(
                    {
                        "reporter_code": cluster,
                        "year": year,
                        "outcome": 1.5 * x + 0.1 * year,
                        "x": x,
                    }
                )
        result = cse.run_ols_model(
            pd.DataFrame(rows),
            outcome="outcome",
            terms=["x"],
            fixed_effects=["year"],
            model_label="test_two_way",
            sample="unit",
            flow="Exports",
            dimension="product",
            metric="gini",
            cluster_col="reporter_code",
            two_way_cluster_col="year",
        )
        self.assertEqual(result.status, "ok")
        self.assertAlmostEqual(result.beta[0], 1.5, places=10)
        self.assertTrue(np.isfinite(result.se[0]))
        self.assertEqual(result.clusters, 4)
        self.assertEqual(result.cluster_col, "reporter_code,year")

    def test_fama_macbeth_uses_hac_se_over_yearly_coefficients(self) -> None:
        yearly = pd.DataFrame(
            {
                "term": ["log_population"] * 4,
                "flow": ["Exports"] * 4,
                "dimension": ["product"] * 4,
                "metric": ["gini"] * 4,
                "outcome": ["product_gini"] * 4,
                "status": ["ok"] * 4,
                "year": [2000, 2001, 2002, 2003],
                "coefficient": [1.0, 1.2, 0.8, 1.0],
                "nobs": [10, 10, 10, 10],
                "candidate_rows": [10, 10, 10, 10],
                "dropped_rows": [0, 0, 0, 0],
                "r_squared": [0.5, 0.4, 0.6, 0.5],
            }
        )
        out = cse.run_fama_macbeth_models(yearly, "unit", hac_lags=1)
        row = out[
            out["flow"].eq("Exports") & out["dimension"].eq("product") & out["metric"].eq("gini")
        ].iloc[0]
        self.assertEqual(row["status"], "ok")
        self.assertAlmostEqual(row["coefficient"], 1.0)
        self.assertTrue(np.isfinite(row["std_error"]))
        self.assertEqual(row["years_estimated"], 4)

    def test_us_population_counterfactual_uses_log_population_delta(self) -> None:
        panel = pd.DataFrame(
            {
                "country": ["Tiny", "Tiny", "Middle", "United States", "United States"],
                "iso3": ["TNY", "TNY", "MID", "USA", "USA"],
                "year": [2020, 2021, 2021, 2020, 2021],
                "population": [1.0, 2.0, 20.0, 80.0, 100.0],
                "flow": ["Exports"] * 5,
                "product_gini": [0.20, 0.30, 0.40, 0.50, 0.60],
                "log_population": np.log([1.0, 2.0, 20.0, 80.0, 100.0]),
                "log_gdp_per_capita": [8.0, 8.1, 8.2, 8.3, 8.4],
                "reporter_code": [1, 1, 2, 3, 3],
            }
        )
        main_models = pd.DataFrame(
            {
                "term": [cse.PRIMARY_TERM],
                "metric": ["gini"],
                "status": ["ok"],
                "flow": ["Exports"],
                "dimension": ["product"],
                "outcome": ["product_gini"],
                "coefficient": [-0.25],
            }
        )
        out = cse.build_us_population_counterfactuals(panel, main_models)
        smallest = out[out["target_id"].eq("smallest")].iloc[0]
        expected = -0.25 * (math.log(2.0) - math.log(100.0))
        self.assertEqual(smallest["target_country"], "Tiny")
        self.assertEqual(smallest["target_year"], 2021)
        self.assertAlmostEqual(smallest["predicted_gini_change"], expected)
        expected_sd = pd.Series([0.20, 0.30, 0.40, 0.50, 0.60]).std(ddof=1)
        self.assertAlmostEqual(smallest["outcome_sample_sd"], expected_sd)
        self.assertAlmostEqual(smallest["predicted_gini_change_sd_share"], expected / expected_sd)
        self.assertEqual(set(out["target_id"]), {"p75", "p50", "p25", "p10", "smallest"})

    def test_hs6_primary_classifier_examples(self) -> None:
        strict_true = ["090111", "170111", "180100", "260300", "270900", "271111", "440300", "710812"]
        strict_false = ["170490", "180690", "240220", "271000", "711319", "999999"]
        broad_only = ["271000", "470321", "720110", "740311"]

        for code in strict_true:
            with self.subTest(code=code):
                flags = cse.classify_primary_hs6(code)
                self.assertTrue(flags["primary_strict"])
                self.assertTrue(flags["primary_broad"])

        for code in strict_false:
            with self.subTest(code=code):
                self.assertFalse(cse.classify_primary_hs6(code)["primary_strict"])

        for code in broad_only:
            with self.subTest(code=code):
                flags = cse.classify_primary_hs6(code)
                self.assertFalse(flags["primary_strict"])
                self.assertTrue(flags["primary_broad"])

    def test_primary_export_share_excludes_999999_from_numerator_and_denominator(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            aggregate_dir = Path(tmpdir)
            rows = pd.DataFrame(
                {
                    "reporter_code": [1, 1, 1, 1, 1, 1],
                    "year": [2000, 2000, 2000, 2000, 2000, 2000],
                    "flow": ["Exports", "Exports", "Exports", "Exports", "Imports", "Exports"],
                    "classification_code": ["H1", "H1", "H1", "H1", "H1", "H1"],
                    "dimension": ["product", "product", "product", "product", "product", "partner"],
                    "cmd_code": ["090111", "271000", "170490", "999999", "090111", "090111"],
                    "trade_value": [100.0, 50.0, 25.0, 1000.0, 999.0, 999.0],
                }
            )
            rows.to_parquet(aggregate_dir / "sample.parquet", index=False)
            mapping = pd.DataFrame(
                [
                    {"classification_code": "H1", "cmd_code": "090111", "primary_strict": True, "primary_broad": True},
                    {"classification_code": "H1", "cmd_code": "271000", "primary_strict": False, "primary_broad": True},
                    {"classification_code": "H1", "cmd_code": "170490", "primary_strict": False, "primary_broad": False},
                ]
            )

            shares, diagnostics = cse.construct_primary_export_shares(
                aggregate_dir,
                mapping,
                start_year=2000,
                end_year=2000,
            )

        row = shares.iloc[0]
        self.assertEqual(row["total_product_exports"], 175.0)
        self.assertEqual(row["strict_primary_exports"], 100.0)
        self.assertEqual(row["broad_primary_exports"], 150.0)
        self.assertAlmostEqual(row["primary_export_share_strict"], 100.0 / 175.0)
        self.assertAlmostEqual(row["primary_export_share_broad"], 150.0 / 175.0)
        self.assertAlmostEqual(row["primary_mapping_coverage_share"], 1.0)
        self.assertIn("median_strict_primary_export_share", set(diagnostics["diagnostic"]))

    def test_primary_export_share_merge_preserves_iso3_year_flow_uniqueness(self) -> None:
        panel = pd.DataFrame(
            {
                "iso3": ["AAA", "AAA", "BBB"],
                "reporter_code": [1, 1, 2],
                "year": [2000, 2000, 2000],
                "flow": ["Imports", "Exports", "Exports"],
                "product_gini": [0.2, 0.3, 0.4],
            }
        )
        shares = pd.DataFrame(
            {
                "reporter_code": [1, 2],
                "year": [2000, 2000],
                "primary_export_share_strict": [0.25, 0.50],
                "primary_export_share_broad": [0.40, 0.75],
            }
        )
        merged = cse.merge_primary_export_shares(panel, shares)
        self.assertEqual(int(merged.duplicated(["iso3", "year", "flow"]).sum()), 0)
        self.assertTrue(np.allclose(merged[merged["reporter_code"].eq(1)]["primary_export_share_strict"], 0.25))

    def test_primary_share_added_control_model_estimates_log_population_term(self) -> None:
        rows = []
        for cluster in range(8):
            for year in [2000, 2001, 2002, 2003]:
                primary_share = 0.1 + 0.03 * (cluster % 3) + 0.005 * (year - 2000)
                log_population = float(cluster + 1)
                log_gdp_per_capita = 8.5 + 0.2 * ((cluster * 2) % 5) + 0.01 * (year - 2000)
                rows.append(
                    {
                        "reporter_code": cluster,
                        "year": year,
                        "flow": "Exports",
                        "product_gini": 1.0 - 0.2 * log_population + 0.5 * primary_share + 0.03 * log_gdp_per_capita + 0.01 * year,
                        "log_population": log_population,
                        "log_gdp_per_capita": log_gdp_per_capita,
                        "primary_export_share_strict": primary_share,
                    }
                )
        out = cse.run_primary_share_control_models(pd.DataFrame(rows), "unit", "strict")
        log_pop = out[
            out["model_label"].eq("primary_share_strict_year_fe")
            & out["flow"].eq("Exports")
            & out["dimension"].eq("product")
            & out["metric"].eq("gini")
            & out["term"].eq("log_population")
        ].iloc[0]
        self.assertEqual(log_pop["status"], "ok")
        self.assertTrue(np.isfinite(log_pop["coefficient"]))
        self.assertTrue(np.isfinite(log_pop["std_error"]))


if __name__ == "__main__":
    unittest.main()
