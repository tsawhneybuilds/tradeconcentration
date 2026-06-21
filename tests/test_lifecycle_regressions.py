from __future__ import annotations

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

import run_lifecycle_regressions as lcr


def synthetic_macro_panel(countries: int = 22, years: range = range(2000, 2006)) -> pd.DataFrame:
    rows = []
    first_year = min(years)
    for country_id in range(countries):
        iso3 = f"C{country_id:03d}"
        for year in years:
            t = year - first_year
            wave = np.sin((country_id + 1) * (t + 1) / 5.0)
            log_goods = 10.0 + 0.03 * t + 0.002 * country_id * t + 0.01 * wave
            log_real = 9.5 + 0.025 * t + 0.0015 * country_id * t + 0.02 * np.cos((country_id + 2) * (t + 1))
            log_gdp = 8.5 + 0.015 * t + 0.001 * country_id * t + 0.006 * wave
            openness = 45.0 + 0.7 * t + 0.05 * country_id * t + 0.4 * wave
            wdi_openness = 50.0 + 0.6 * t + 0.04 * country_id * t + 0.5 * np.cos((country_id + 3) * (t + 1))
            log_population = 14.0 + 0.004 * t + 0.0007 * country_id * t
            oil_share = 0.02 * (country_id % 4) + 0.001 * t + 0.0001 * country_id * t
            tariff = 5.0 + 0.1 * (country_id % 5) + 0.03 * t + 0.004 * country_id * t
            outcome = (
                0.35
                + 0.02 * log_goods
                - 0.015 * log_gdp
                + 0.0004 * openness
                + 0.04 * oil_share
                + 0.002 * country_id
                - 0.001 * t
                + 0.002 * wave
            )
            rows.append(
                {
                    "iso3": iso3,
                    "country": f"Country {country_id:03d}",
                    "year": year,
                    "ex_energy_import_product_gini": outcome,
                    "log_goods_exports_current_usd": log_goods,
                    "log_real_exports_goods_services_constant_2015_usd": log_real,
                    "log_gdp_pc_ppp_constant_2021_intl_usd": log_gdp,
                    "trade_openness_pct_gdp": openness,
                    "wdi_goods_services_trade_openness_pct_gdp": wdi_openness,
                    "log_population": log_population,
                    "oil_export_share": oil_share,
                    "tariff_applied_weighted_mean_pct": tariff,
                }
            )
    panel = pd.DataFrame(rows).sort_values(["iso3", "year"]).reset_index(drop=True)
    diff_cols = [
        "ex_energy_import_product_gini",
        "log_goods_exports_current_usd",
        "log_real_exports_goods_services_constant_2015_usd",
        "log_gdp_pc_ppp_constant_2021_intl_usd",
        "trade_openness_pct_gdp",
        "wdi_goods_services_trade_openness_pct_gdp",
    ]
    for col in diff_cols:
        panel[f"d_{col}"] = panel.groupby("iso3")[col].diff()
        panel[f"l1_d_{col}"] = panel.groupby("iso3")[f"d_{col}"].shift(1)
    return panel


def synthetic_policy_panel(countries: int = 22, years: range = range(2010, 2016)) -> pd.DataFrame:
    rows = []
    first_year = min(years)
    for country_id in range(countries):
        iso3 = f"C{country_id:03d}"
        for year in years:
            t = year - first_year
            import_count = float((country_id + t) % 4)
            export_count = float((2 * country_id + t) % 3)
            rows.append(
                {
                    "scenario": lcr.POLICY_DIRECT_SCENARIO,
                    "iso3": iso3,
                    "country": f"Country {country_id:03d}",
                    "year": year,
                    "all_ip_measures": import_count + export_count,
                    "import_substitution_ip_measures": import_count,
                    "export_promotion_ip_measures": export_count,
                    "subsidy_ip_measures": float((country_id + 2 * t) % 2),
                    "firm_specific_ip_measures": float((country_id + t) % 2),
                    "product_targeted_ip_measures": float((country_id + t) % 3),
                    "log_gdp_pc_ppp": 8.2 + 0.01 * t + 0.001 * country_id * t,
                    "log_population": 14.0 + 0.003 * t + 0.0005 * country_id * t,
                    "trade_openness_share_gdp": 0.55 + 0.002 * t + 0.0002 * country_id * t,
                    "imports_goods_services_share_gdp": 0.25 + 0.001 * t + 0.0001 * country_id * t,
                    "ex_energy_import_product_gini": 0.45 + 0.002 * country_id - 0.001 * t + 0.004 * import_count,
                }
            )
    return lcr.ip.add_policy_transforms(pd.DataFrame(rows))


def spec(model_id: str) -> lcr.LifecycleSpec:
    return next(item for item in lcr.lifecycle_specs() if item.model_id == model_id)


class LifecycleRegressionTests(unittest.TestCase):
    def test_lifecycle_specs_have_unique_model_ids(self) -> None:
        ids = [item.model_id for item in lcr.lifecycle_specs()]
        self.assertEqual(len(ids), len(set(ids)))
        robust_ids = [item.model_id for item in lcr.lifecycle_specs_with_robustness()]
        self.assertEqual(len(robust_ids), len(set(robust_ids)))
        self.assertTrue(any(model_id.endswith("_twoway_cluster") for model_id in robust_ids))

    def test_output_paths_are_under_lifecycle_directory(self) -> None:
        default_paths = lcr.output_paths()
        for path in default_paths.values():
            self.assertEqual(path.parent, lcr.OUT_DIR)
            self.assertEqual(path.parent.name, "lifecycle_regressions")
            self.assertIn("rd2_countries", path.parts)
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "lifecycle_regressions"
            paths = lcr.output_paths(out_dir)
            self.assertEqual(
                set(paths),
                {"terms", "summary", "manifest", "crosswalk", "memo"},
            )
            for path in paths.values():
                self.assertEqual(path.parent, out_dir)

    def test_sample_manifest_includes_coverage_attrition_and_missingness(self) -> None:
        terms, summary, manifest = lcr.run_lifecycle_models(
            synthetic_macro_panel(),
            synthetic_policy_panel(),
            specs=[spec("macro_level_goods_exports"), spec("policy_cumulative_pre_direct")],
            min_countries=20,
            min_years=5,
        )
        self.assertFalse(terms.empty)
        self.assertEqual(len(summary), 2)
        required = {
            "countries",
            "years",
            "dropped_rows",
            "missing_columns_summary",
            "complete_countries_list",
            "within_variation_terms",
            "no_within_variation_terms",
        }
        self.assertTrue(required.issubset(manifest.columns))
        self.assertTrue((manifest["countries"] >= 20).all())
        self.assertTrue((manifest["years"] >= 5).all())
        self.assertTrue(manifest["missing_columns_summary"].astype(str).str.len().gt(0).all())

    def test_policy_cumulative_pre_validation_rejects_contemporaneous_cumulative_totals(self) -> None:
        panel = synthetic_policy_panel(countries=3, years=range(2010, 2014))
        lcr.validate_policy_pre_exposure(panel)
        bad = panel.copy()
        for col in ["import_substitution_ip_measures", "export_promotion_ip_measures"]:
            bad[f"cum_{col}_pre"] = bad[f"cum_{col}"]
            bad[f"log1p_cum_{col}_pre"] = np.log1p(bad[f"cum_{col}_pre"])
        with self.assertRaisesRegex(RuntimeError, "t-1"):
            lcr.validate_policy_pre_exposure(bad)

    def test_write_outputs_writes_required_files_under_output_dir(self) -> None:
        terms, summary, manifest = lcr.run_lifecycle_models(
            synthetic_macro_panel(),
            synthetic_policy_panel(),
            specs=[spec("macro_level_goods_exports")],
            min_countries=20,
            min_years=5,
        )
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "lifecycle_regressions"
            paths = lcr.write_outputs(terms, summary, manifest, lcr.crosswalk(), out_dir=out_dir)
            for path in paths.values():
                self.assertTrue(path.exists())
                self.assertEqual(path.parent, out_dir)


if __name__ == "__main__":
    unittest.main()
