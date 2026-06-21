from __future__ import annotations

import sys
import unittest
from argparse import Namespace
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_trade_gini_site as site
import run_growth_effect as ge


def synthetic_concentration(years: list[int], iso3s: list[str]) -> pd.DataFrame:
    rows = []
    for idx, iso3 in enumerate(iso3s, start=1):
        for year in years:
            rows.append(
                {
                    "country": iso3,
                    "iso3": iso3,
                    "reporter_code": idx,
                    "year": year,
                    "flow": "Exports",
                    "variant": "baseline",
                    "product_gini": 0.4,
                    "partner_gini": 0.4,
                    "product_top_1pct_share": 0.2,
                    "product_top_5pct_share": 0.3,
                    "partner_top_1pct_share": 0.2,
                    "partner_top_5pct_share": 0.3,
                }
            )
    return pd.DataFrame(rows)


class GrowthEffectTests(unittest.TestCase):
    def test_consecutive_year_lag_construction_and_gap_handling(self) -> None:
        concentration = synthetic_concentration([2002, 2004], ["AAA"])
        controls = pd.DataFrame(
            {
                "iso3": ["AAA", "AAA", "AAA"],
                "year": [2000, 2001, 2003],
                "real_exports_constant_2015_usd": [100.0, 120.0, 180.0],
                "population": [10.0, 11.0, 13.0],
            }
        )
        out = ge.construct_lagged_export_variables(concentration, controls)
        year_2002 = out[out["year"].eq(2002)].iloc[0]
        year_2004 = out[out["year"].eq(2004)].iloc[0]
        self.assertAlmostEqual(year_2002[ge.PRIMARY_TERM], np.log(120.0) - np.log(100.0))
        self.assertAlmostEqual(year_2002[ge.LEVEL_TERM], np.log(120.0))
        self.assertTrue(np.isnan(year_2004[ge.PRIMARY_TERM]))

    def test_growth_and_lagged_export_level_definitions(self) -> None:
        concentration = synthetic_concentration([2002], ["AAA"])
        controls = pd.DataFrame(
            {
                "iso3": ["AAA", "AAA", "AAA"],
                "year": [2000, 2001, 2002],
                "real_exports_constant_2015_usd": [100.0, 150.0, 210.0],
                "population": [10.0, 12.0, 14.0],
            }
        )
        row = ge.construct_lagged_export_variables(concentration, controls).iloc[0]
        self.assertAlmostEqual(row[ge.LEVEL_TERM], np.log(150.0))
        self.assertAlmostEqual(row[ge.POP_TERM], np.log(12.0))
        self.assertAlmostEqual(row[ge.PRIMARY_TERM], np.log(150.0) - np.log(100.0))
        self.assertAlmostEqual(row[ge.CONTEMPORANEOUS_TERM], np.log(210.0) - np.log(150.0))
        self.assertEqual(row["base_year"], 2001)
        self.assertEqual(row["outcome_year"], 2002)
        self.assertEqual(row["horizon"], 1)

    def test_multi_horizon_rows_use_exact_base_year_matching(self) -> None:
        concentration = synthetic_concentration([2002, 2006, 2011], ["AAA"])
        controls = pd.DataFrame(
            {
                "iso3": ["AAA", "AAA", "AAA", "AAA", "AAA"],
                "year": [2000, 2001, 2002, 2006, 2011],
                "real_exports_constant_2015_usd": [100.0, 125.0, 130.0, 200.0, 300.0],
                "population": [10.0, 12.0, 13.0, 14.0, 15.0],
            }
        )
        out = ge.construct_lagged_export_variables(concentration, controls, horizons=[1, 5, 10])
        matched = out[out["base_year"].eq(2001)].sort_values("horizon")
        self.assertEqual(matched["horizon"].tolist(), [1, 5, 10])
        self.assertEqual(matched["year"].tolist(), [2002, 2006, 2011])
        self.assertTrue(matched["common_horizon_support"].all())
        for value in matched[ge.PRIMARY_TERM]:
            self.assertAlmostEqual(value, np.log(125.0) - np.log(100.0))

    def test_common_horizon_support_blocks_unmatched_base_years(self) -> None:
        concentration = synthetic_concentration([2002, 2006], ["AAA"])
        controls = pd.DataFrame(
            {
                "iso3": ["AAA", "AAA"],
                "year": [2000, 2001],
                "real_exports_constant_2015_usd": [100.0, 125.0],
                "population": [10.0, 12.0],
            }
        )
        out = ge.construct_lagged_export_variables(concentration, controls, horizons=[1, 5, 10])
        base_2001 = out[out["base_year"].eq(2001)]
        self.assertEqual(set(base_2001["horizon"]), {1, 5})
        self.assertFalse(base_2001["common_horizon_support"].any())
        self.assertTrue(ge.analysis_sample(out, match_horizon_sample=True).empty)

    def test_duplicate_key_check_blocks_ambiguous_controls(self) -> None:
        controls = pd.DataFrame(
            {
                "iso3": ["AAA", "AAA"],
                "year": [2000, 2000],
                "real_exports_constant_2015_usd": [100.0, 101.0],
                "population": [10.0, 10.0],
            }
        )
        with self.assertRaisesRegex(RuntimeError, "duplicate"):
            ge.construct_lagged_export_variables(synthetic_concentration([2002], ["AAA"]), controls)

    def test_main_model_recovers_known_country_year_fe_slope(self) -> None:
        rows = []
        for country in range(8):
            for year in range(2000, 2008):
                growth = 0.02 * np.sin((country + 1) * (year - 1998)) + (country - 4) * 0.001
                level = np.log(1000 + country * 100 + year)
                pop = np.log(1_000_000 + country * 1000)
                rows.append(
                    {
                        "reporter_code": country,
                        "year": year,
                        "outcome": 1.25 * growth + 0.2 * level - 0.1 * pop + country * 0.3 + (year - 2000) * -0.2,
                        ge.PRIMARY_TERM: growth,
                        ge.LEVEL_TERM: level,
                        ge.POP_TERM: pop,
                    }
                )
        result = ge.cse.run_ols_model(
            pd.DataFrame(rows),
            "outcome",
            [ge.PRIMARY_TERM, ge.LEVEL_TERM, ge.POP_TERM],
            ["reporter_code", "year"],
            "unit",
            "unit",
            "Exports",
            "product",
            "gini",
            cluster_col="reporter_code",
        )
        self.assertEqual(result.status, "ok")
        self.assertAlmostEqual(result.beta[result.terms.index(ge.PRIMARY_TERM)], 1.25, places=8)

    def test_export_level_bin_marginal_slope_construction(self) -> None:
        rows = []
        for cidx in range(1, 13):
            iso3 = f"C{cidx:02d}"
            for year in range(2000, 2008):
                for flow in ["Exports", "Imports"]:
                    growth = 0.02 * np.sin(cidx * (year - 1999)) + 0.001 * ((cidx * year) % 7)
                    rows.append(
                        {
                            "country": iso3,
                            "iso3": iso3,
                            "reporter_code": cidx,
                            "year": year,
                            "base_year": year - 1,
                            "horizon": 1,
                            "flow": flow,
                            "variant": "baseline",
                            ge.PRIMARY_TERM: growth,
                            ge.LEVEL_TERM: np.log(1_000_000_000 + cidx * 100_000_000 + year),
                            ge.POP_TERM: np.log(10_000_000 + cidx),
                            "region_year": f"R{cidx % 3}_{year}",
                            "product_gini": 0.8 * growth + 0.01 * cidx - 0.005 * year,
                            "partner_gini": 0.5 + 0.2 * growth,
                            "product_top_1pct_share": 0.4 + 0.1 * growth,
                            "product_top_5pct_share": 0.5 + 0.1 * growth,
                            "partner_top_1pct_share": 0.3 + 0.05 * growth,
                            "partner_top_5pct_share": 0.4 + 0.05 * growth,
                        }
                    )
        out, cutoffs = ge.run_income_bin_slopes(pd.DataFrame(rows), "unit", horizons=[1])
        slopes = out[
            out["row_type"].eq("slope")
            & out["flow"].eq("Exports")
            & out["dimension"].eq("product")
            & out["metric"].eq("gini")
        ]
        self.assertEqual(set(slopes["export_level_bin"]), {"low", "middle", "high"})
        self.assertTrue(np.isfinite(slopes["coefficient"]).all())
        self.assertGreater(cutoffs["middle_high_export_cutoff"], cutoffs["low_middle_export_cutoff"])

    def test_main_models_include_horizon_column(self) -> None:
        rows = []
        for country in range(8):
            for base_year in range(2000, 2005):
                for horizon in [1, 5]:
                    growth = 0.01 * (country + 1) + 0.001 * (base_year - 2000)
                    rows.append(
                        {
                            "reporter_code": country,
                            "base_year": base_year,
                            "year": base_year + horizon,
                            "horizon": horizon,
                            "flow": "Exports",
                            ge.PRIMARY_TERM: growth,
                            ge.LEVEL_TERM: np.log(1000 + country * 100),
                            ge.POP_TERM: np.log(1_000_000 + country),
                            "product_gini": 0.5 + growth,
                            "partner_gini": 0.4 + growth,
                            "product_top_1pct_share": 0.2 + growth,
                            "product_top_5pct_share": 0.3 + growth,
                            "partner_top_1pct_share": 0.2 + growth,
                            "partner_top_5pct_share": 0.3 + growth,
                        }
                    )
        models = ge.run_main_models(pd.DataFrame(rows), "unit", horizons=[1, 5])
        focus = models[models["term"].eq(ge.PRIMARY_TERM)]
        self.assertEqual(set(focus["horizon"]), {1, 5})

    def test_sample_comparison_outputs_balanced_and_broad_samples(self) -> None:
        rows = []
        for country in range(8):
            for base_year in range(2000, 2005):
                for horizon in [1, 5]:
                    growth = 0.01 * (country + 1) + 0.001 * (base_year - 2000)
                    row = {
                        "reporter_code": country,
                        "base_year": base_year,
                        "year": base_year + horizon,
                        "horizon": horizon,
                        "flow": "Exports",
                        ge.PRIMARY_TERM: growth,
                        ge.LEVEL_TERM: np.log(1000 + country * 100),
                        ge.POP_TERM: np.log(1_000_000 + country),
                        "product_gini": 0.5 + growth,
                        "partner_gini": 0.4 + growth,
                        "product_top_1pct_share": 0.2 + growth,
                        "product_top_5pct_share": 0.3 + growth,
                        "partner_top_1pct_share": 0.2 + growth,
                        "partner_top_5pct_share": 0.3 + growth,
                    }
                    rows.append(row)
        broad = pd.DataFrame(rows)
        balanced = broad[~((broad["horizon"].eq(5)) & (broad["base_year"].eq(2004)))].copy()
        models = ge.run_sample_comparison_models(broad, balanced, "unit", horizons=[1, 5])
        focus = models[models["term"].eq(ge.PRIMARY_TERM)]
        self.assertEqual(set(focus["model_label"]), {"balanced_common_horizon_sample", "broad_available_horizon_sample"})
        self.assertEqual(set(focus["horizon"]), {1, 5})
        self.assertIn("sample_definition", focus.columns)

    def test_export_coverage_blocker_behavior(self) -> None:
        panel = pd.DataFrame(
            {
                "iso3": [f"C{i:02d}" for i in range(24)],
                "reporter_code": list(range(24)),
                "year": [2000] * 24,
                ge.PRIMARY_TERM: [0.02] * 24,
                ge.LEVEL_TERM: [10.0] * 24,
                ge.POP_TERM: [12.0] * 24,
            }
        )
        args = Namespace(min_clusters=25, min_coverage=0.50, coverage_limited_threshold=0.80)
        with self.assertRaises(ge.ExportGrowthCoverageError):
            ge.enforce_export_growth_coverage(panel, args)

    def test_site_builder_adds_growth_page_only_for_rd2(self) -> None:
        context = defaultdict(str)
        site.configure_site_sample("rd2_countries")
        rd2_pages = site.render_pages(context)
        self.assertIn("growth-effect.html", rd2_pages)
        self.assertIn("Growth effect", site.nav("growth-effect"))
        self.assertIn("Export Growth and Concentration", rd2_pages["growth-effect.html"])
        self.assertIn("one, five, and ten years later", rd2_pages["growth-effect.html"])
        self.assertIn("Balanced Versus Broad Sample", rd2_pages["growth-effect.html"])
        self.assertIn("growth_effect_sample_comparison_models.csv", rd2_pages["growth-effect.html"])
        self.assertIn("growth_effect_main_models.csv", rd2_pages["growth-effect.html"])
        self.assertIn("run_manifest_growth_effect.json", rd2_pages["growth-effect.html"])

        site.configure_site_sample("prof_p_33")
        self.assertNotIn("growth-effect.html", site.render_pages(context))
        site.configure_site_sample("world_broad")
        self.assertNotIn("growth-effect.html", site.render_pages(context))
        site.configure_site_sample("rd2_countries")

    def test_site_tables_highlight_significant_p_values(self) -> None:
        html = site.table_rows(
            [
                {"outcome": "A", "coefficient": 0.12, "p_value": 0.04, "bh_q_value": 0.03},
                {"outcome": "B", "coefficient": 0.02, "p_value": 0.40, "bh_q_value": 0.80},
            ],
            [
                ("outcome", "Outcome", "text"),
                ("coefficient", "Coef.", "dec"),
                ("p_value", "p-value", "dec"),
                ("bh_q_value", "BH q", "dec"),
            ],
        )
        self.assertIn('class="sig-row"', html)
        self.assertIn('class="sig-coef"', html)
        self.assertIn('class="sig-pvalue"', html)
        self.assertIn('class="sig-qvalue"', html)


if __name__ == "__main__":
    unittest.main()
