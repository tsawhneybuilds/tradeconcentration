from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_trade_deal_market_access_diagnostics as diag


class TradeDealMarketAccessDiagnosticsTests(unittest.TestCase):
    def test_parse_wits_country_metadata(self) -> None:
        xml = """<?xml version="1.0" encoding="utf-8"?>
        <wits:datasource xmlns:wits="http://wits.worldbank.org">
          <wits:countries>
            <wits:country countrycode="840" isreporter="1" ispartner="1" isgroup="No" grouptype="N/A">
              <wits:iso3Code>USA</wits:iso3Code>
              <wits:name>United States</wits:name>
              <wits:notes />
            </wits:country>
          </wits:countries>
        </wits:datasource>
        """
        out = diag.parse_wits_countries_xml(xml)
        self.assertEqual(len(out), 1)
        self.assertEqual(out.iloc[0]["wits_country_code"], "840")
        self.assertEqual(out.iloc[0]["wits_iso3"], "USA")
        self.assertEqual(out.iloc[0]["wits_is_reporter"], "1")

    def test_parse_wits_dataavailability(self) -> None:
        xml = """<?xml version="1.0" encoding="utf-8"?>
        <wits:datasource xmlns:wits="http://wits.worldbank.org">
          <wits:dataavailability>
            <wits:reporter countrycode="840" iso3Code="USA" isgroup="No" grouptype="N/A">
              <wits:name>United States</wits:name>
              <wits:year>2000</wits:year>
              <wits:reporternernomenclature reporternernomenclaturecode="H1">HS 1996</wits:reporternernomenclature>
              <wits:numberofpreferentialagreement>9</wits:numberofpreferentialagreement>
              <wits:partnerlist>000;124;</wits:partnerlist>
              <wits:isspecificdutyexpressionestimatedavailable>Yes</wits:isspecificdutyexpressionestimatedavailable>
              <wits:notes />
              <wits:lastupdateddate>2024/12/12</wits:lastupdateddate>
            </wits:reporter>
          </wits:dataavailability>
        </wits:datasource>
        """
        out = diag.parse_wits_dataavailability_xml(xml)
        self.assertEqual(len(out), 1)
        self.assertEqual(out.iloc[0]["year"], 2000)
        self.assertEqual(out.iloc[0]["nomenclature_code"], "H1")
        self.assertEqual(out.iloc[0]["partner_list"], "000;124;")

    def test_crosswalk_matches_wits_code_and_iso3(self) -> None:
        rd2 = pd.DataFrame(
            [
                {
                    "country": "United States",
                    "iso3": "USA",
                    "reporter_code": 842,
                    "wits_country_code_candidate": "842",
                    "desta_iso_numeric_candidate": 842,
                    "larch_iso3_candidate": "USA",
                    "wto_economy_label_candidate": "United States",
                    "cepii_iso3_candidate": "USA",
                }
            ]
        )
        wits = pd.DataFrame(
            [
                {
                    "wits_country_code": "842",
                    "wits_iso3": "USA",
                    "wits_name": "United States",
                    "wits_is_reporter": "1",
                    "wits_is_partner": "1",
                    "wits_is_group": "No",
                    "wits_group_type": "N/A",
                    "wits_notes": "",
                }
            ]
        )
        out = diag.build_country_crosswalk(rd2, wits)
        self.assertEqual(out.iloc[0]["wits_match_status"], "exact_code_iso3_match")

    def test_crosswalk_falls_back_to_iso3_when_comtrade_code_differs(self) -> None:
        rd2 = pd.DataFrame(
            [
                {
                    "country": "United States",
                    "iso3": "USA",
                    "reporter_code": 842,
                    "wits_country_code_candidate": "842",
                    "desta_iso_numeric_candidate": 842,
                    "larch_iso3_candidate": "USA",
                    "wto_economy_label_candidate": "United States",
                    "cepii_iso3_candidate": "USA",
                }
            ]
        )
        wits = pd.DataFrame(
            [
                {
                    "wits_country_code": "840",
                    "wits_iso3": "USA",
                    "wits_name": "United States",
                    "wits_is_reporter": "1",
                    "wits_is_partner": "1",
                    "wits_is_group": "No",
                    "wits_group_type": "N/A",
                    "wits_notes": "",
                }
            ]
        )
        out = diag.build_country_crosswalk(rd2, wits)
        self.assertEqual(out.iloc[0]["wits_country_code"], "840")
        self.assertEqual(out.iloc[0]["wits_match_status"], "iso3_match_different_numeric_code")

    def test_eu_member_uses_eun_tariff_reporter_default(self) -> None:
        rd2 = pd.DataFrame(
            [
                {
                    "country": "France",
                    "iso3": "FRA",
                    "reporter_code": 251,
                    "wits_country_code_candidate": "251",
                    "desta_iso_numeric_candidate": 251,
                    "larch_iso3_candidate": "FRA",
                    "wto_economy_label_candidate": "France",
                    "cepii_iso3_candidate": "FRA",
                }
            ]
        )
        wits = pd.DataFrame(
            [
                {
                    "wits_country_code": "918",
                    "wits_iso3": "EUN",
                    "wits_name": "European Union",
                    "wits_is_reporter": "1",
                    "wits_is_partner": "1",
                    "wits_is_group": "No",
                    "wits_group_type": "N/A",
                    "wits_notes": "",
                }
            ]
        )
        out = diag.build_country_crosswalk(rd2, wits)
        self.assertEqual(out.iloc[0]["tariff_reporter_code_default"], "918")
        self.assertEqual(out.iloc[0]["tariff_reporter_mapping_status"], "needs_year_specific_eu_customs_mapping")

    def test_parse_comtrade_aggregate_filename_preserves_revision(self) -> None:
        parsed = diag.parse_comtrade_aggregate_filename(
            Path("data/processed/samples/rd2_countries/exercise_02_12_file_aggregates/COMTRADE-FINAL-CA6992023H6[2024-05-30].parquet")
        )
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["reporter_code"], 699)
        self.assertEqual(parsed["year"], 2023)
        self.assertEqual(parsed["comtrade_hs_revision"], "H6")

    def test_hs_gate_blocks_when_wits_missing_current_revisions(self) -> None:
        gate = diag.hs_concordance_gate(
            {"revisions": ["H0", "H1", "H5", "H6"]},
            {"nomenclature_codes": ["H0", "H1", "H2", "H3", "H4"]},
        )
        self.assertEqual(gate["status"], "blocked_pending_concordance")
        self.assertIn("H5", gate["comtrade_revisions_missing_in_wits_availability"])
        self.assertIn("H6", gate["comtrade_revisions_beyond_wits_supported_hs"])

    def test_tariff_reporter_year_mapping_uses_eun_only_for_active_eu_years(self) -> None:
        sample = pd.DataFrame(
            [
                {"country": "Poland", "iso3": "POL", "reporter_code": 616, "year": 2003},
                {"country": "Poland", "iso3": "POL", "reporter_code": 616, "year": 2004},
                {"country": "United Kingdom", "iso3": "GBR", "reporter_code": 826, "year": 2020},
                {"country": "United Kingdom", "iso3": "GBR", "reporter_code": 826, "year": 2021},
                {"country": "United States", "iso3": "USA", "reporter_code": 842, "year": 2020},
            ]
        )
        crosswalk = pd.DataFrame(
            [
                {
                    "iso3": "POL",
                    "reporter_code": 616,
                    "wits_country_code": "616",
                    "wits_iso3": "POL",
                    "wits_name": "Poland",
                    "wits_is_reporter": "1",
                    "wits_match_status": "exact_code_iso3_match",
                    "eu_member": True,
                    "eu_accession_year": 2004,
                    "eu_exit_year": None,
                },
                {
                    "iso3": "GBR",
                    "reporter_code": 826,
                    "wits_country_code": "826",
                    "wits_iso3": "GBR",
                    "wits_name": "United Kingdom",
                    "wits_is_reporter": "0",
                    "wits_match_status": "exact_code_iso3_match",
                    "eu_member": True,
                    "eu_accession_year": 1973,
                    "eu_exit_year": 2020,
                },
                {
                    "iso3": "USA",
                    "reporter_code": 842,
                    "wits_country_code": "840",
                    "wits_iso3": "USA",
                    "wits_name": "United States",
                    "wits_is_reporter": "1",
                    "wits_match_status": "iso3_match_different_numeric_code",
                    "eu_member": False,
                    "eu_accession_year": None,
                    "eu_exit_year": None,
                },
            ]
        )
        availability = pd.DataFrame(
            [
                {"wits_country_code": "616", "year": 2003, "nomenclature_code": "H2", "last_updated_date": ""},
                {"wits_country_code": "918", "year": 2004, "nomenclature_code": "H2", "last_updated_date": ""},
                {"wits_country_code": "918", "year": 2020, "nomenclature_code": "H5", "last_updated_date": ""},
                {"wits_country_code": "826", "year": 2021, "nomenclature_code": "H5", "last_updated_date": ""},
                {"wits_country_code": "840", "year": 2020, "nomenclature_code": "H5", "last_updated_date": ""},
            ]
        )
        out = diag.build_tariff_reporter_year_mapping(sample, crosswalk, availability)
        keyed = out.set_index(["iso3", "year"])
        self.assertEqual(keyed.loc[("POL", 2003), "tariff_reporter_code"], "616")
        self.assertEqual(keyed.loc[("POL", 2003), "customs_mapping_rule"], "direct_wits_country_pre_accession")
        self.assertEqual(keyed.loc[("POL", 2004), "tariff_reporter_code"], "918")
        self.assertEqual(keyed.loc[("GBR", 2020), "tariff_reporter_code"], "918")
        self.assertEqual(keyed.loc[("GBR", 2021), "tariff_reporter_code"], "826")
        self.assertEqual(keyed.loc[("GBR", 2021), "customs_mapping_rule"], "direct_wits_country_post_eu_customs_exit")
        self.assertEqual(keyed.loc[("USA", 2020), "tariff_reporter_code"], "840")
        self.assertTrue(bool(keyed.loc[("POL", 2004), "has_wits_availability_for_year"]))

    def test_wits_availability_gap_table_lists_missing_reporter_years(self) -> None:
        mapping = pd.DataFrame(
            [
                {
                    "country": "A",
                    "iso3": "AAA",
                    "reporter_code": 1,
                    "year": 2022,
                    "tariff_reporter_code": "001",
                    "tariff_reporter_iso3": "AAA",
                    "tariff_reporter_name": "A",
                    "customs_mapping_rule": "direct_wits_country_not_eu_member",
                    "direct_wits_country_code": "001",
                    "direct_wits_iso3": "AAA",
                    "direct_wits_is_reporter": "1",
                    "tariff_mapping_status": "missing_wits_availability_for_year",
                },
                {
                    "country": "B",
                    "iso3": "BBB",
                    "reporter_code": 2,
                    "year": 2022,
                    "tariff_reporter_code": "002",
                    "tariff_reporter_iso3": "BBB",
                    "tariff_reporter_name": "B",
                    "customs_mapping_rule": "direct_wits_country_not_eu_member",
                    "direct_wits_country_code": "002",
                    "direct_wits_iso3": "BBB",
                    "direct_wits_is_reporter": "1",
                    "tariff_mapping_status": "ok",
                },
            ]
        )
        gaps, summary, manifest = diag.build_wits_availability_gap_tables(mapping)
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps.iloc[0]["iso3"], "AAA")
        self.assertEqual(int(summary.iloc[0]["missing_reporter_years"]), 1)
        self.assertEqual(manifest["status"], "gaps_present")

    def test_h6_to_wits_bridge_preserves_leading_zeros_and_flags_ambiguity(self) -> None:
        hs_family = pd.DataFrame(
            [
                {
                    "classification_code": "H6",
                    "classification_label": "HS2022",
                    "cmd_code": "010121",
                    "harmonized_product_id": "HSF:A",
                    "harmonization_status": "matched_wco_correlation",
                    "harmonization_source": "WCO test",
                    "source_component_node_count": 2,
                    "analysis_family_node_count": 2,
                    "source_revision_count": 2,
                    "harmonization_version": "test",
                },
                {
                    "classification_code": "H5",
                    "classification_label": "HS2017",
                    "cmd_code": "010121",
                    "harmonized_product_id": "HSF:A",
                    "harmonization_status": "matched_wco_correlation",
                    "harmonization_source": "WCO test",
                    "source_component_node_count": 2,
                    "analysis_family_node_count": 2,
                    "source_revision_count": 2,
                    "harmonization_version": "test",
                },
                {
                    "classification_code": "H6",
                    "classification_label": "HS2022",
                    "cmd_code": "020840",
                    "harmonized_product_id": "HSF:B",
                    "harmonization_status": "matched_wco_correlation",
                    "harmonization_source": "WCO test",
                    "source_component_node_count": 3,
                    "analysis_family_node_count": 3,
                    "source_revision_count": 2,
                    "harmonization_version": "test",
                },
                {
                    "classification_code": "H5",
                    "classification_label": "HS2017",
                    "cmd_code": "020830",
                    "harmonized_product_id": "HSF:B",
                    "harmonization_status": "matched_wco_correlation",
                    "harmonization_source": "WCO test",
                    "source_component_node_count": 3,
                    "analysis_family_node_count": 3,
                    "source_revision_count": 2,
                    "harmonization_version": "test",
                },
                {
                    "classification_code": "H5",
                    "classification_label": "HS2017",
                    "cmd_code": "020890",
                    "harmonized_product_id": "HSF:B",
                    "harmonization_status": "matched_wco_correlation",
                    "harmonization_source": "WCO test",
                    "source_component_node_count": 3,
                    "analysis_family_node_count": 3,
                    "source_revision_count": 2,
                    "harmonization_version": "test",
                },
                {
                    "classification_code": "H6",
                    "classification_label": "HS2022",
                    "cmd_code": "999999",
                    "harmonized_product_id": "HSF:BAD",
                    "harmonization_status": "matched_wco_correlation",
                    "harmonization_source": "WCO test",
                    "source_component_node_count": 1,
                    "analysis_family_node_count": 1,
                    "source_revision_count": 1,
                    "harmonization_version": "test",
                },
            ]
        )
        hs_family["cmd_code"] = hs_family["cmd_code"].map(diag.normalize_hs6_code)
        hs_family = hs_family[~hs_family["cmd_code"].isin(diag.EXCLUDED_HS6_CODES)].copy()
        out = diag.build_h6_to_wits_revision_bridge(hs_family, ["H5"])
        keyed = out.drop_duplicates(["h6_cmd_code"]).set_index("h6_cmd_code")
        self.assertIn("010121", keyed.index)
        self.assertNotIn("999999", keyed.index)
        self.assertEqual(keyed.loc["010121", "bridge_status"], "unique_family_bridge")
        self.assertEqual(keyed.loc["020840", "bridge_status"], "ambiguous_multi_target_family_bridge")
        self.assertEqual(int(keyed.loc["020840", "target_candidate_count"]), 2)

    def test_referee_calibrated_samples_split_primary_full_and_supplement(self) -> None:
        sample = pd.DataFrame(
            [
                {"country": "A", "iso3": "AAA", "reporter_code": 1, "year": 2000, "product_gini": 0.5},
                {"country": "B", "iso3": "BBB", "reporter_code": 2, "year": 2000, "product_gini": None},
                {"country": "C", "iso3": "CCC", "reporter_code": 3, "year": 2001, "product_gini": 0.7},
                {"country": "E", "iso3": "EEE", "reporter_code": 5, "year": 2001, "product_gini": 0.6},
                {"country": "F", "iso3": "FFF", "reporter_code": 6, "year": 2001, "product_gini": 0.4},
                {"country": "D", "iso3": "DDD", "reporter_code": 4, "year": 2022, "product_gini": 0.8},
            ]
        )
        mapping = pd.DataFrame(
            [
                {
                    "iso3": "AAA",
                    "reporter_code": 1,
                    "year": 2000,
                    "tariff_reporter_code": "001",
                    "tariff_reporter_iso3": "AAA",
                    "tariff_reporter_name": "A",
                    "customs_mapping_rule": "direct_wits_country_not_eu_member",
                    "tariff_mapping_status": "ok",
                    "has_wits_availability_for_year": True,
                    "availability_nomenclature_codes": "H1",
                    "availability_last_updated_dates": "",
                    "direct_wits_country_code": "001",
                    "direct_wits_iso3": "AAA",
                    "direct_wits_is_reporter": "1",
                },
                {
                    "iso3": "BBB",
                    "reporter_code": 2,
                    "year": 2000,
                    "tariff_reporter_code": "002",
                    "tariff_reporter_iso3": "BBB",
                    "tariff_reporter_name": "B",
                    "customs_mapping_rule": "direct_wits_country_not_eu_member",
                    "tariff_mapping_status": "ok",
                    "has_wits_availability_for_year": True,
                    "availability_nomenclature_codes": "H1",
                    "availability_last_updated_dates": "",
                    "direct_wits_country_code": "002",
                    "direct_wits_iso3": "BBB",
                    "direct_wits_is_reporter": "1",
                },
                {
                    "iso3": "CCC",
                    "reporter_code": 3,
                    "year": 2001,
                    "tariff_reporter_code": "003",
                    "tariff_reporter_iso3": "CCC",
                    "tariff_reporter_name": "C",
                    "customs_mapping_rule": "direct_wits_country_not_eu_member",
                    "tariff_mapping_status": "missing_wits_availability_for_year",
                    "has_wits_availability_for_year": False,
                    "availability_nomenclature_codes": "",
                    "availability_last_updated_dates": "",
                    "direct_wits_country_code": "003",
                    "direct_wits_iso3": "CCC",
                    "direct_wits_is_reporter": "1",
                },
                {
                    "iso3": "DDD",
                    "reporter_code": 4,
                    "year": 2022,
                    "tariff_reporter_code": "004",
                    "tariff_reporter_iso3": "DDD",
                    "tariff_reporter_name": "D",
                    "customs_mapping_rule": "direct_wits_country_not_eu_member",
                    "tariff_mapping_status": "ok",
                    "has_wits_availability_for_year": True,
                    "availability_nomenclature_codes": "H5",
                    "availability_last_updated_dates": "",
                    "direct_wits_country_code": "004",
                    "direct_wits_iso3": "DDD",
                    "direct_wits_is_reporter": "1",
                },
                {
                    "iso3": "EEE",
                    "reporter_code": 5,
                    "year": 2001,
                    "tariff_reporter_code": "005",
                    "tariff_reporter_iso3": "EEE",
                    "tariff_reporter_name": "E",
                    "customs_mapping_rule": "direct_wits_country_not_eu_member",
                    "tariff_mapping_status": "ok",
                    "has_wits_availability_for_year": True,
                    "availability_nomenclature_codes": "H1",
                    "availability_last_updated_dates": "",
                    "direct_wits_country_code": "005",
                    "direct_wits_iso3": "EEE",
                    "direct_wits_is_reporter": "1",
                },
                {
                    "iso3": "FFF",
                    "reporter_code": 6,
                    "year": 2001,
                    "tariff_reporter_code": "006",
                    "tariff_reporter_iso3": "FFF",
                    "tariff_reporter_name": "F",
                    "customs_mapping_rule": "direct_wits_country_not_eu_member",
                    "tariff_mapping_status": "ok",
                    "has_wits_availability_for_year": True,
                    "availability_nomenclature_codes": "H1",
                    "availability_last_updated_dates": "",
                    "direct_wits_country_code": "006",
                    "direct_wits_iso3": "FFF",
                    "direct_wits_is_reporter": "1",
                },
            ]
        )
        revisions = pd.DataFrame(
            [
                {"reporter_code": 1, "year": 2000, "comtrade_hs_revision": "H1", "file": "a.parquet"},
                {"reporter_code": 2, "year": 2000, "comtrade_hs_revision": "H1", "file": "b.parquet"},
                {"reporter_code": 3, "year": 2001, "comtrade_hs_revision": "H1", "file": "c.parquet"},
                {"reporter_code": 4, "year": 2022, "comtrade_hs_revision": "H6", "file": "d.parquet"},
                {"reporter_code": 5, "year": 2001, "comtrade_hs_revision": "H1", "file": "e.parquet"},
                {"reporter_code": 6, "year": 2001, "comtrade_hs_revision": "H2", "file": "f.parquet"},
            ]
        )
        hs4_coverage = {
            "status": "passed",
            "hs4_bridge_trade_value_coverage": 1.0,
            "hs4_bridge_trade_value_coverage_min_required": 0.90,
        }
        hs4_headline, hs4_long, headline, primary, agreement, supplement, summary, attrition = (
            diag.build_referee_calibrated_samples(sample, mapping, revisions, hs4_coverage)
        )
        self.assertEqual(len(hs4_headline), 2)
        self.assertEqual(set(hs4_headline["iso3"]), {"EEE", "FFF"})
        self.assertEqual(hs4_headline.iloc[0]["analysis_sample"], "primary_wits_hs4_2001_2021")
        self.assertEqual(len(hs4_long), 3)
        self.assertEqual(len(headline), 1)
        self.assertEqual(headline.iloc[0]["iso3"], "EEE")
        self.assertEqual(headline.iloc[0]["analysis_sample"], "primary_wits_2001_2021")
        self.assertEqual(len(primary), 2)
        self.assertEqual(primary.iloc[0]["iso3"], "AAA")
        self.assertEqual(len(agreement), 6)
        self.assertEqual(len(supplement), 1)
        self.assertEqual(supplement.iloc[0]["iso3"], "CCC")
        self.assertEqual(summary["primary_wits_hs4_2001_2021"]["rows"], 2)
        self.assertEqual(summary["primary_wits_2001_2021"]["rows"], 1)
        self.assertEqual(summary["primary_wits"]["h6_rows"], 0)
        self.assertIn("included_primary_wits_hs4", summary["attrition"]["primary_wits_hs4_exclusion_reason_counts"])
        self.assertIn("h6_revision_not_allowed_primary", summary["attrition"]["primary_wits_exclusion_reason_counts"])
        self.assertIn("Primary WITS HS4 Sequential Attrition", attrition)

    def test_hs4_gate_blocks_primary_sample_when_coverage_is_low(self) -> None:
        sample = pd.DataFrame([{"country": "A", "iso3": "AAA", "reporter_code": 1, "year": 2001, "product_gini": 0.5}])
        mapping = pd.DataFrame(
            [
                {
                    "iso3": "AAA",
                    "reporter_code": 1,
                    "year": 2001,
                    "tariff_reporter_code": "001",
                    "tariff_mapping_status": "ok",
                    "availability_nomenclature_codes": "H1",
                }
            ]
        )
        revisions = pd.DataFrame(
            [{"reporter_code": 1, "year": 2001, "comtrade_hs_revision": "H1", "file": "a.parquet"}]
        )
        with self.assertRaisesRegex(ValueError, "HS4 harmonization coverage gate failed"):
            diag.build_referee_calibrated_samples(
                sample,
                mapping,
                revisions,
                {
                    "status": "blocked_hs4_baseline_coverage_gate_failed",
                    "hs4_bridge_trade_value_coverage": 0.89,
                    "hs4_bridge_trade_value_coverage_min_required": 0.90,
                },
            )

    def test_hard_gates_reject_bad_product_bridge_and_join_inputs(self) -> None:
        with self.assertRaisesRegex(ValueError, "999999"):
            diag.assert_no_product_level_999999(pd.DataFrame({"cmd_code": ["010121", "999999"]}))
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            diag.validate_h6_bridge_policy(
                pd.DataFrame(
                    {
                        "h6_cmd_code": ["020840"],
                        "bridge_status": ["ambiguous_multi_target_family_bridge"],
                        "harmonized_product_id": ["HSF:B"],
                    }
                )
            )
        self.assertTrue(
            diag.validate_h6_bridge_policy(
                pd.DataFrame({"harmonized_product_id": ["HSF:B"]}),
                policy="harmonized_family_extension",
            )
        )
        with self.assertRaisesRegex(ValueError, "tariff_reporter_code"):
            diag.validate_tariff_join_keys(["reporter_code", "year", "cmd_code"])
        self.assertTrue(diag.validate_tariff_join_keys(["tariff_reporter_code", "year", "cmd_code"]))
        self.assertEqual(diag.harmonized_hs4_from_hs6("010121"), "HS4:0101")
        self.assertEqual(diag.harmonized_hs4_from_hs6("999999"), "")
        with self.assertRaisesRegex(ValueError, "HS6"):
            diag.validate_hs4_tariff_output_keys(["tariff_reporter_code", "year", "cmd_code"])
        self.assertTrue(diag.validate_hs4_tariff_output_keys(["tariff_reporter_code", "year", "harmonized_hs4"]))


if __name__ == "__main__":
    unittest.main()
