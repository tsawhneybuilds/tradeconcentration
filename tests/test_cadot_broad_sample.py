from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_ppp_hump_regressions as ppp
import trade_concentration_pipeline as tcp


def reporter_reference(selected: int) -> pd.DataFrame:
    rows = [
        {
            "reporterCode": code,
            "reporterDesc": f"Country {code}",
            "reporterCodeIsoAlpha3": f"C{code:03d}"[-3:],
            "isGroup": False,
            "entryExpiredDate": "",
        }
        for code in range(1, selected + 1)
    ]
    rows.extend(
        [
            {"reporterCode": 901, "reporterDesc": "Group", "reporterCodeIsoAlpha3": "GRP", "isGroup": True, "entryExpiredDate": ""},
            {"reporterCode": 902, "reporterDesc": "Expired", "reporterCodeIsoAlpha3": "EXP", "isGroup": False, "entryExpiredDate": "2010-01-01"},
            {"reporterCode": 903, "reporterDesc": "No ISO", "reporterCodeIsoAlpha3": "", "isGroup": False, "entryExpiredDate": ""},
            {"reporterCode": 904, "reporterDesc": "Short", "reporterCodeIsoAlpha3": "SHT", "isGroup": False, "entryExpiredDate": ""},
        ]
    )
    return pd.DataFrame(rows)


def availability(selected: int) -> pd.DataFrame:
    rows = []
    for code in range(1, selected + 1):
        rows.extend({"reporterCode": code, "period": year, "classificationCode": "H6"} for year in range(2000, 2019))
    rows.extend({"reporterCode": 901, "period": year, "classificationCode": "H6"} for year in range(2000, 2025))
    rows.extend({"reporterCode": 902, "period": year, "classificationCode": "H6"} for year in range(2000, 2025))
    rows.extend({"reporterCode": 903, "period": year, "classificationCode": "H6"} for year in range(2000, 2025))
    rows.extend({"reporterCode": 904, "period": year, "classificationCode": "H6"} for year in range(2000, 2018))
    return pd.DataFrame(rows)


class CadotBroadSampleTests(unittest.TestCase):
    def test_cadot_broad_defaults_are_fixed(self) -> None:
        settings = tcp.configure_country_sample(tcp.CADOT_BROAD_SAMPLE)

        self.assertEqual(settings.name, tcp.CADOT_BROAD_SAMPLE)
        self.assertEqual(settings.start_year, tcp.CADOT_BROAD_START_YEAR)
        self.assertEqual(settings.end_year, tcp.CADOT_BROAD_END_YEAR)
        self.assertEqual(settings.min_available_years, tcp.CADOT_BROAD_MIN_AVAILABLE_YEARS)
        self.assertEqual(tcp.sample_processed_dir().name, tcp.CADOT_BROAD_SAMPLE)

    def test_cadot_original_tracks_are_fixed_but_not_broad_fallbacks(self) -> None:
        settings = tcp.configure_country_sample(tcp.CADOT_ORIGINAL_SAMPLE)
        self.assertEqual(settings.start_year, 1988)
        self.assertEqual(settings.end_year, 2006)
        with self.assertRaisesRegex(RuntimeError, "research-only Cadot replication target"):
            tcp.build_country_sample(settings)

        extended = tcp.configure_country_sample(tcp.CADOT_ORIGINAL_EXTENDED_SAMPLE)
        self.assertEqual(extended.start_year, 1988)
        self.assertIsNone(extended.end_year)
        with self.assertRaisesRegex(RuntimeError, "research-only Cadot replication target"):
            tcp.build_country_sample(extended)

    def test_cadot_broad_selects_exact_156_from_hs_availability(self) -> None:
        settings = tcp.CountrySampleSettings(
            name=tcp.CADOT_BROAD_SAMPLE,
            min_available_years=tcp.CADOT_BROAD_MIN_AVAILABLE_YEARS,
            start_year=tcp.CADOT_BROAD_START_YEAR,
            end_year=tcp.CADOT_BROAD_END_YEAR,
        )
        with patch.object(tcp, "load_reporter_reference", return_value=(reporter_reference(156), "checksum")), patch.object(
            tcp, "load_public_final_availability", return_value=availability(156)
        ):
            panel, coverage, excluded, manifest = tcp.world_broad_country_sample(settings)

        self.assertEqual(len(panel), 156)
        self.assertEqual(panel["reporter_code"].nunique(), 156)
        self.assertEqual(panel["iso3"].nunique(), 156)
        self.assertTrue((coverage.groupby("reporter_code")["year"].nunique() >= 19).all())
        self.assertEqual(manifest["country_sample"], tcp.CADOT_BROAD_SAMPLE)
        self.assertEqual(manifest["expected_selected_reporters"], 156)
        self.assertIn("insufficient_hs_years", set(excluded["exclusion_reason"]))

    def test_cadot_broad_fails_if_fixed_rule_does_not_select_156(self) -> None:
        settings = tcp.CountrySampleSettings(
            name=tcp.CADOT_BROAD_SAMPLE,
            min_available_years=tcp.CADOT_BROAD_MIN_AVAILABLE_YEARS,
            start_year=tcp.CADOT_BROAD_START_YEAR,
            end_year=tcp.CADOT_BROAD_END_YEAR,
        )
        with patch.object(tcp, "load_reporter_reference", return_value=(reporter_reference(155), "checksum")), patch.object(
            tcp, "load_public_final_availability", return_value=availability(155)
        ):
            with self.assertRaisesRegex(RuntimeError, "exactly 156"):
                tcp.world_broad_country_sample(settings)

    def test_cadot_broad_ppp_panels_are_complete_case_not_balanced(self) -> None:
        concentration = pd.DataFrame(
            [
                {"country": "A", "iso3": "AAA", "reporter_code": 1, "year": 2000, "flow": "Exports", "variant": "baseline", "product_gini": 0.4, "partner_gini": 0.5},
                {"country": "A", "iso3": "AAA", "reporter_code": 1, "year": 2001, "flow": "Exports", "variant": "baseline", "product_gini": 0.5, "partner_gini": 0.6},
                {"country": "B", "iso3": "BBB", "reporter_code": 2, "year": 2000, "flow": "Exports", "variant": "baseline", "product_gini": 0.6, "partner_gini": 0.7},
                {"country": "A", "iso3": "AAA", "reporter_code": 1, "year": 2000, "flow": "Imports", "variant": "baseline", "product_gini": 0.3, "partner_gini": 0.4},
                {"country": "B", "iso3": "BBB", "reporter_code": 2, "year": 2000, "flow": "Imports", "variant": "baseline", "product_gini": 0.7, "partner_gini": 0.8},
            ]
        )
        controls = pd.DataFrame(
            [
                {"country": "A", "iso3": "AAA", "reporter_code": 1, "year": 2000, ppp.PPP_VALUE_COL: 10_000.0, ppp.PPP_LEVEL_COL: 1.0, ppp.PPP_LEVEL_SQ_COL: 1.0, ppp.PPP_LOG_COL: 9.21, ppp.PPP_LOG_SQ_COL: 84.82, "log_population": 12.0, "oil_export_share": 0.1},
                {"country": "A", "iso3": "AAA", "reporter_code": 1, "year": 2001, ppp.PPP_VALUE_COL: 11_000.0, ppp.PPP_LEVEL_COL: 1.1, ppp.PPP_LEVEL_SQ_COL: 1.21, ppp.PPP_LOG_COL: 9.31, ppp.PPP_LOG_SQ_COL: 86.68, "log_population": 12.1, "oil_export_share": 0.2},
                {"country": "B", "iso3": "BBB", "reporter_code": 2, "year": 2000, ppp.PPP_VALUE_COL: 20_000.0, ppp.PPP_LEVEL_COL: 2.0, ppp.PPP_LEVEL_SQ_COL: 4.0, ppp.PPP_LOG_COL: 9.90, ppp.PPP_LOG_SQ_COL: 98.01, "log_population": 13.0, "oil_export_share": 0.3},
            ]
        )
        specs = tuple(spec for spec in ppp.OUTCOME_SPECS if spec.slug in {"export_product_gini", "import_product_gini"})
        with patch.object(ppp, "load_standard_concentration", return_value=concentration), patch.object(
            ppp, "load_controls_with_ppp", return_value=controls
        ):
            panels, _controls, _common_codes, attrition, selected_specs = ppp.build_outcome_panels(
                tcp.CADOT_BROAD_SAMPLE,
                2000,
                2001,
                refresh_ppp=False,
                balance_policy="complete_case",
                outcome_specs=specs,
            )

        self.assertEqual({spec.slug for spec in selected_specs}, {"export_product_gini", "import_product_gini"})
        self.assertEqual(len(panels["export_product_gini"]), 3)
        self.assertEqual(len(panels["import_product_gini"]), 2)
        self.assertFalse(panels["export_product_gini"].duplicated(["reporter_code", "year"]).any())
        rows = attrition.set_index("outcome_slug")["analytic_rows_after_balance"].to_dict()
        self.assertEqual(rows["export_product_gini"], 3)
        self.assertEqual(rows["import_product_gini"], 2)

    def test_cadot_broad_ppp_loader_reads_three_metric_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            table_dir = base / "cadot_broad_156" / "three_metric_tables"
            table_dir.mkdir(parents=True)
            rows = [
                {
                    "country": "A",
                    "iso3": "AAA",
                    "reporter_code": 1,
                    "year": 2000,
                    "flow": flow,
                    "dimension": dimension,
                    "variant": "baseline",
                    "gini": 0.4,
                    "theil": 1.2,
                    "hhi": 0.3,
                    "active_count": 10,
                }
                for flow in ["Exports", "Imports"]
                for dimension in ["product", "partner"]
            ]
            pd.DataFrame(rows).to_parquet(table_dir / "concentration_metric_all_years.parquet")
            with patch.object(ppp, "sample_results_dir", return_value=base / "cadot_broad_156"):
                out = ppp.load_standard_concentration(tcp.CADOT_BROAD_SAMPLE, 2000, 2000)

        self.assertEqual(len(out), 2)
        self.assertIn("product_theil", out.columns)
        self.assertIn("partner_gini", out.columns)
        self.assertFalse(out.duplicated(["reporter_code", "year", "flow", "variant"]).any())

    def test_cadot_broad_oil_controls_use_hs27_exclusion_share(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            table_dir = base / "cadot_broad_156" / "three_metric_tables"
            table_dir.mkdir(parents=True)
            pd.DataFrame(
                [
                    {
                        "country": "A",
                        "iso3": "AAA",
                        "reporter_code": 1,
                        "year": 2000,
                        "flow": "Exports",
                        "dimension": "product",
                        "variant": "oil_only",
                        "trade_share_removed": 0.25,
                    }
                ]
            ).to_parquet(table_dir / "exercise_06_exclusion_metrics.parquet")
            with patch.object(ppp, "sample_results_dir", return_value=base / "cadot_broad_156"):
                controls = ppp.load_export_oil_controls(tcp.CADOT_BROAD_SAMPLE, 2000, 2000)

        self.assertEqual(len(controls), 1)
        self.assertEqual(float(controls["oil_export_share"].iloc[0]), 0.25)


if __name__ == "__main__":
    unittest.main()
