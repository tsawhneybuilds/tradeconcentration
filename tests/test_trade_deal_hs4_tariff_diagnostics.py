from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_trade_deal_hs4_tariff_diagnostics as hs4diag


def minimal_wits_json() -> dict:
    return {
        "dataSets": [
            {
                "series": {
                    "0:0:0:0:0": {"observations": {"0": [10.0, 0, None, 0, 0, 0, 0, 0, 0, 0, 0, 0]}},
                    "0:0:0:1:0": {"observations": {"0": [20.0, 0, None, 0, 0, 0, 0, 0, 0, 0, 0, 0]}},
                    "0:0:0:2:0": {"observations": {"0": [99.0, 0, None, 0, 0, 0, 0, 0, 0, 0, 0, 0]}},
                }
            }
        ],
        "structure": {
            "dimensions": {
                "series": [
                    {"id": "FREQ", "values": [{"id": "A"}]},
                    {"id": "REPORTER", "values": [{"id": "840"}]},
                    {"id": "PARTNER", "values": [{"id": "000"}]},
                    {
                        "id": "PRODUCTCODE",
                        "values": [
                            {"id": "010110"},
                            {"id": "010190"},
                            {"id": "999999"},
                        ],
                    },
                    {"id": "DATATYPE", "values": [{"id": "AVEEstimated"}]},
                ],
                "observation": [{"id": "TIME_PERIOD", "values": [{"id": "2000"}]}],
            },
            "attributes": {
                "observation": [
                    {"id": "NOMENCODE", "values": [{"id": "H1"}]},
                    {"id": "EXCLUDEDFROM", "values": []},
                    {"id": "TARIFFTYPE", "values": [{"id": "MFN"}]},
                    {"id": "SUM_OF_RATES", "values": [{"id": "0"}]},
                    {"id": "MIN_RATE", "values": [{"id": "0"}]},
                    {"id": "MAX_RATE", "values": [{"id": "0"}]},
                    {"id": "TOTALNOOFLINES", "values": [{"id": "1"}]},
                    {"id": "NBR_PREF_LINES", "values": [{"id": "0"}]},
                    {"id": "NBR_MFN_LINES", "values": [{"id": "1"}]},
                    {"id": "NBR_NA_LINES", "values": [{"id": "0"}]},
                    {"id": "OBS_VALUE_MEASURE", "values": [{"id": "SimpleAverage"}]},
                ]
            },
        },
    }


class TradeDealHs4TariffDiagnosticsTests(unittest.TestCase):
    def test_parse_wits_json_excludes_999999_and_preserves_hs4(self) -> None:
        parsed = hs4diag.parse_wits_sdmx_tariff_json(minimal_wits_json())
        self.assertEqual(len(parsed), 2)
        self.assertEqual(set(parsed["harmonized_hs4"]), {"HS4:0101"})
        self.assertNotIn("999999", set(parsed["source_product_code"]))
        self.assertEqual(parsed.iloc[0]["tariff_reporter_code"], "840")
        self.assertEqual(int(parsed.iloc[0]["year"]), 2000)

    def test_parse_wits_json_infers_product_position_when_wits_key_order_differs(self) -> None:
        obj = minimal_wits_json()
        obj["dataSets"][0]["series"] = {
            "0:0:0:0:0": {"observations": {"0": [10.0, 0, None, 0, 0, 0, 0, 0, 0, 0, 0, 0]}},
            "0:0:1:0:0": {"observations": {"0": [20.0, 0, None, 0, 0, 0, 0, 0, 0, 0, 0, 0]}},
        }
        parsed = hs4diag.parse_wits_sdmx_tariff_json(obj)
        self.assertEqual(set(parsed["source_product_code"]), {"010110", "010190"})

    def test_aggregate_tariffs_to_hs4_line_weighted(self) -> None:
        parsed = hs4diag.parse_wits_sdmx_tariff_json(minimal_wits_json())
        parsed.loc[parsed["source_product_code"].eq("010110"), "total_lines"] = 1
        parsed.loc[parsed["source_product_code"].eq("010190"), "total_lines"] = 3
        out = hs4diag.aggregate_tariffs_to_hs4(parsed)
        self.assertEqual(len(out), 1)
        self.assertEqual(out.iloc[0]["harmonized_hs4"], "HS4:0101")
        self.assertAlmostEqual(float(out.iloc[0]["tariff_aveestimated"]), 17.5)
        self.assertEqual(int(out.iloc[0]["source_product_count"]), 2)

    def test_destination_mapping_uses_eun_for_active_eu_years_and_direct_for_uk_2021(self) -> None:
        partner_ref = {
            "251": {"destination_iso3": "FRA", "destination_name": "France"},
            "826": {"destination_iso3": "GBR", "destination_name": "United Kingdom"},
            "842": {"destination_iso3": "USA", "destination_name": "United States"},
        }
        wits_by_code = {
            "251": {"wits_country_code": "251", "wits_iso3": "FRA", "wits_name": "France", "wits_is_reporter": "1"},
            "826": {
                "wits_country_code": "826",
                "wits_iso3": "GBR",
                "wits_name": "United Kingdom",
                "wits_is_reporter": "1",
            },
            "840": {
                "wits_country_code": "840",
                "wits_iso3": "USA",
                "wits_name": "United States",
                "wits_is_reporter": "1",
            },
            "918": {
                "wits_country_code": "918",
                "wits_iso3": "EUN",
                "wits_name": "European Union",
                "wits_is_reporter": "1",
            },
        }
        wits_by_iso = {row["wits_iso3"]: row for row in wits_by_code.values()}
        france = hs4diag.destination_mapping_row("251", 2010, partner_ref, wits_by_code, wits_by_iso)
        uk_2020 = hs4diag.destination_mapping_row("826", 2020, partner_ref, wits_by_code, wits_by_iso)
        uk_2021 = hs4diag.destination_mapping_row("826", 2021, partner_ref, wits_by_code, wits_by_iso)
        usa = hs4diag.destination_mapping_row("842", 2010, partner_ref, wits_by_code, wits_by_iso)
        self.assertEqual(france["destination_tariff_reporter_code"], "918")
        self.assertEqual(uk_2020["destination_tariff_reporter_code"], "918")
        self.assertEqual(uk_2021["destination_tariff_reporter_code"], "826")
        self.assertEqual(usa["destination_tariff_reporter_code"], "840")
        self.assertEqual(usa["destination_wits_match_status"], "iso3_match_different_numeric_code")

    def test_wits_lookup_prefers_reporter_country_over_same_code_preference_group(self) -> None:
        wits = pd.DataFrame(
            [
                {
                    "wits_country_code": "036",
                    "wits_iso3": "A36",
                    "wits_name": "EU 28 members 2013",
                    "wits_is_reporter": "0",
                },
                {
                    "wits_country_code": "036",
                    "wits_iso3": "AUS",
                    "wits_name": "Australia",
                    "wits_is_reporter": "1",
                },
                {
                    "wits_country_code": "036",
                    "wits_iso3": "L36",
                    "wits_name": "GSP for LDC Beneficiaries",
                    "wits_is_reporter": "0",
                },
            ]
        )
        by_code, _ = hs4diag.wits_lookup_tables(wits)
        self.assertEqual(by_code["036"]["wits_iso3"], "AUS")
        self.assertEqual(by_code["036"]["wits_is_reporter"], "1")

    def test_market_access_panel_uses_destination_tariffs_and_coverage_gate(self) -> None:
        sample = pd.DataFrame(
            [
                {"country": "Exporter", "iso3": "EXP", "reporter_code": 1, "year": 2001, "product_gini": 0.4},
            ]
        )
        weights = pd.DataFrame(
            [
                {
                    "exporter_reporter_code": 1,
                    "destination_partner_code": "840",
                    "harmonized_hs4": "HS4:0101",
                    "baseline_trade_value": 80.0,
                    "exporter_baseline_trade_value_denominator": 100.0,
                    "baseline_weight": 0.8,
                },
                {
                    "exporter_reporter_code": 1,
                    "destination_partner_code": "124",
                    "harmonized_hs4": "HS4:0201",
                    "baseline_trade_value": 20.0,
                    "exporter_baseline_trade_value_denominator": 100.0,
                    "baseline_weight": 0.2,
                },
            ]
        )
        mapping = pd.DataFrame(
            [
                {
                    "destination_partner_code": "840",
                    "year": 2001,
                    "destination_tariff_reporter_code": "840",
                    "destination_tariff_mapping_status": "ok",
                    "destination_customs_mapping_rule": "direct_wits_country_not_eu_member",
                },
                {
                    "destination_partner_code": "124",
                    "year": 2001,
                    "destination_tariff_reporter_code": "124",
                    "destination_tariff_mapping_status": "ok",
                    "destination_customs_mapping_rule": "direct_wits_country_not_eu_member",
                },
            ]
        )
        tariffs = pd.DataFrame(
            [
                {
                    "tariff_reporter_code": "840",
                    "year": 2001,
                    "harmonized_hs4": "HS4:0101",
                    "tariff_aveestimated": 10.0,
                }
            ]
        )
        panel, coverage, decomposition, destination_audit, summary = hs4diag.compute_market_access_panel(
            sample, weights, mapping, tariffs
        )
        self.assertAlmostEqual(float(panel.iloc[0]["tariff_weight_coverage_i_t"]), 0.8)
        self.assertTrue(bool(panel.iloc[0]["tariff_coverage_gate_080"]))
        self.assertAlmostEqual(float(panel.iloc[0]["market_access_tariff_avg_i_t"]), 10.0)
        self.assertEqual(int(summary["rows_passing_080"]), 1)
        self.assertEqual(len(coverage), 1)
        self.assertIn("country", coverage.columns)
        self.assertIn("coverage_reason", decomposition.columns)
        self.assertIn("destination_partner_code", destination_audit.columns)


if __name__ == "__main__":
    unittest.main()
