from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from trade_concentration_pipeline import (
    build_hs_harmonized_family_mapping_from_edges,
    exercise_12_accounting_from_pair,
    exercise_12_accounting_outputs_for_values,
    extract_leaf_trade,
    partner_region_table,
    prepare_exercise_12_item_values,
    write_exercise_12_memo,
)
from run_exercises_02_12 import create_grouped_view


class Exercise12RepairTests(unittest.TestCase):
    def synthetic_hs_mapping(self) -> pd.DataFrame:
        codes_by_revision = {
            "H1": {"100100", "100101", "100102", "100103", "200101", "200102", "300100"},
            "H2": {"100200", "100201", "100202", "100203", "200201", "200202", "300200"},
        }
        edges = [
            ("H1", "100100", "H2", "100200", "WCO test 1:1"),
            ("H1", "100101", "H2", "100201", "WCO test n:1"),
            ("H1", "100102", "H2", "100201", "WCO test n:1"),
            ("H1", "100103", "H2", "100202", "WCO test 1:n"),
            ("H1", "100103", "H2", "100203", "WCO test 1:n"),
            ("H1", "200101", "H2", "200201", "WCO test n:n"),
            ("H1", "200101", "H2", "200202", "WCO test n:n"),
            ("H1", "200102", "H2", "200201", "WCO test n:n"),
            ("H1", "200102", "H2", "200202", "WCO test n:n"),
        ]
        return build_hs_harmonized_family_mapping_from_edges(edges, codes_by_revision=codes_by_revision, max_family_nodes=20)

    def test_hs_family_collapses_revision_links_without_splitting_trade(self) -> None:
        mapping = self.synthetic_hs_mapping()
        one_to_one = mapping.set_index(["classification_code", "cmd_code"])["harmonized_product_id"]
        self.assertEqual(one_to_one[("H1", "100100")], one_to_one[("H2", "100200")])
        self.assertEqual(one_to_one[("H1", "100101")], one_to_one[("H1", "100102")])
        self.assertEqual(one_to_one[("H1", "100101")], one_to_one[("H2", "100201")])
        self.assertEqual(one_to_one[("H1", "100103")], one_to_one[("H2", "100202")])
        self.assertEqual(one_to_one[("H1", "100103")], one_to_one[("H2", "100203")])
        self.assertEqual(one_to_one[("H1", "200101")], one_to_one[("H2", "200202")])

        raw = pd.DataFrame(
            [
                {"reporter_code": 1, "year": 2000, "classification_code": "H1", "cmd_code": "200101", "trade_value": 10.0},
                {"reporter_code": 1, "year": 2000, "classification_code": "H1", "cmd_code": "200102", "trade_value": 5.0},
                {"reporter_code": 1, "year": 2005, "classification_code": "H2", "cmd_code": "200202", "trade_value": 20.0},
            ]
        )
        prepared = prepare_exercise_12_item_values(raw, "product", "hs6_harmonized_family", hs_family_mapping=mapping)
        self.assertAlmostEqual(prepared["trade_value"].sum(), raw["trade_value"].sum())
        self.assertEqual(prepared.loc[prepared["year"] == 2000, "item_id"].nunique(), 1)

    def test_hs6_harmonized_family_uses_weighted_lt_hgl_conversion_when_weights_passed(self) -> None:
        weights = pd.DataFrame(
            [
                {
                    "source_classification_code": "H1",
                    "source_cmd_code": "111111",
                    "target_classification_code": "H0",
                    "target_cmd_code": "010101",
                    "target_product_id": "HS1992:010101",
                    "weight": 0.25,
                    "conversion_method": "lt_hgl_weighted_hs1992",
                },
                {
                    "source_classification_code": "H1",
                    "source_cmd_code": "111111",
                    "target_classification_code": "H0",
                    "target_cmd_code": "020202",
                    "target_product_id": "HS1992:020202",
                    "weight": 0.75,
                    "conversion_method": "lt_hgl_weighted_hs1992",
                },
            ]
        )
        raw = pd.DataFrame(
            [
                {
                    "reporter_code": 1,
                    "year": 2000,
                    "classification_code": "H1",
                    "cmd_code": "111111",
                    "partner_code": 8,
                    "trade_value": 100.0,
                }
            ]
        )

        prepared = prepare_exercise_12_item_values(raw, "product", "hs6_harmonized_family", hs_family_mapping=weights)

        self.assertEqual(set(prepared["item_id"]), {"HS1992:010101", "HS1992:020202"})
        values = prepared.set_index("item_id")["trade_value"]
        self.assertAlmostEqual(float(values["HS1992:010101"]), 25.0)
        self.assertAlmostEqual(float(values["HS1992:020202"]), 75.0)
        self.assertAlmostEqual(prepared["trade_value"].sum(), raw["trade_value"].sum())

    def test_duckdb_grouped_view_keeps_999999_for_partner_totals_only(self) -> None:
        rows = pd.DataFrame(
            [
                {
                    "reporter_code": 1,
                    "year": 2000,
                    "flow": "Exports",
                    "classification_code": "H2",
                    "dimension": "product",
                    "cmd_code": "999999",
                    "partner_code": pd.NA,
                    "hs2": "99",
                    "trade_value": 50.0,
                },
                {
                    "reporter_code": 1,
                    "year": 2000,
                    "flow": "Exports",
                    "classification_code": "",
                    "dimension": "partner",
                    "cmd_code": "999999",
                    "partner_code": 8,
                    "hs2": pd.NA,
                    "trade_value": 50.0,
                },
                {
                    "reporter_code": 1,
                    "year": 2000,
                    "flow": "Exports",
                    "classification_code": "H2",
                    "dimension": "product_partner_cell",
                    "cmd_code": "999999",
                    "partner_code": 8,
                    "hs2": "99",
                    "trade_value": 50.0,
                },
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "partial.parquet"
            rows.to_parquet(path, index=False)
            with duckdb.connect() as con:
                create_grouped_view(con, [path])
                product_rows = con.execute(
                    "SELECT COUNT(*) FROM grouped_aggregates WHERE dimension IN ('product', 'product_partner_cell')"
                ).fetchone()[0]
                partner_value = con.execute(
                    "SELECT COALESCE(SUM(trade_value), 0) FROM grouped_aggregates WHERE dimension = 'partner'"
                ).fetchone()[0]
        self.assertEqual(int(product_rows), 0)
        self.assertAlmostEqual(float(partner_value), 50.0)

    def test_hs_harmonized_family_treats_revision_change_as_existing(self) -> None:
        mapping = build_hs_harmonized_family_mapping_from_edges(
            [("H1", "111111", "H2", "222222", "WCO test revision link")],
            codes_by_revision={"H1": {"111111"}, "H2": {"222222"}},
            max_family_nodes=20,
        )
        raw = pd.DataFrame(
            [
                {"reporter_code": 1, "year": 2000, "classification_code": "H1", "cmd_code": "111111", "trade_value": 100.0},
                {"reporter_code": 1, "year": 2005, "classification_code": "H2", "cmd_code": "222222", "trade_value": 150.0},
            ]
        )
        net, _gross, transitions, _hs_diag, harmonization_diag = exercise_12_accounting_outputs_for_values(
            raw,
            "product",
            (5,),
            cpa_mapping=pd.DataFrame(),
            hs_family_mapping=mapping,
        )
        headline = net[
            (net["item_id_mode"] == "hs6_harmonized_family")
            & (net["top_definition"] == "top_10")
            & (net["driver_category"] == "existing_top_10")
        ]
        self.assertEqual(len(headline), 1)
        self.assertAlmostEqual(float(headline.iloc[0]["contribution"]), 50.0)
        self.assertTrue(
            net[
                (net["item_id_mode"] == "hs6_harmonized_family")
                & (net["top_definition"] == "top_10")
                & (net["driver_category"] == "strict_new_item")
            ].empty
        )
        self.assertFalse(transitions[transitions["item_id_mode"] == "hs6_harmonized_family"].empty)
        self.assertFalse(harmonization_diag.empty)

    def test_exercise_12_splits_strict_new_and_low_base_growers(self) -> None:
        rows = []
        for idx in range(10):
            rows.append(
                {
                    "reporter_code": 1,
                    "year": 2000,
                    "future_year": 2005,
                    "item_id": f"large_{idx}",
                    "base_value": 100000.0,
                    "future_value": 100000.0,
                    "base_size_state_top_10": "large_top_10",
                    "future_size_state_top_10": "large_top_10",
                }
            )
        rows.extend(
            [
                {
                    "reporter_code": 1,
                    "year": 2000,
                    "future_year": 2005,
                    "item_id": "absolute_low_base",
                    "base_value": 5000.0,
                    "future_value": 20000.0,
                    "base_size_state_top_10": "small_active_non_top_10",
                    "future_size_state_top_10": "small_active_non_top_10",
                },
                {
                    "reporter_code": 1,
                    "year": 2000,
                    "future_year": 2005,
                    "item_id": "least_traded_base",
                    "base_value": 20000.0,
                    "future_value": 50000.0,
                    "base_size_state_top_10": "small_active_non_top_10",
                    "future_size_state_top_10": "small_active_non_top_10",
                },
                {
                    "reporter_code": 1,
                    "year": 2000,
                    "future_year": 2005,
                    "item_id": "strict_zero",
                    "base_value": 0.0,
                    "future_value": 30000.0,
                    "base_size_state_top_10": pd.NA,
                    "future_size_state_top_10": "small_active_non_top_10",
                },
            ]
        )
        net, gross, _transitions = exercise_12_accounting_from_pair(
            pd.DataFrame(rows),
            dimension="product",
            horizon=5,
            item_id_mode="hs6_harmonized_family",
            top_definition="top_10",
        )
        contributions = net.set_index("driver_category")["contribution"]
        self.assertAlmostEqual(float(contributions["strict_new_item"]), 30000.0)
        self.assertAlmostEqual(float(contributions["low_base_under_10k_grower"]), 15000.0)
        self.assertAlmostEqual(float(contributions["least_traded_10pct_grower"]), 30000.0)
        self.assertAlmostEqual(float(contributions["existing_top_10"]), 0.0)
        gross_categories = set(gross["driver_category"])
        self.assertIn("strict_new_item", gross_categories)
        self.assertIn("low_base_under_10k_grower", gross_categories)
        self.assertIn("least_traded_10pct_grower", gross_categories)

    def test_product_partner_cell_uses_harmonized_family_and_partner(self) -> None:
        mapping = build_hs_harmonized_family_mapping_from_edges(
            [("H1", "111111", "H2", "222222", "WCO test revision link")],
            codes_by_revision={"H1": {"111111"}, "H2": {"222222"}},
            max_family_nodes=20,
        )
        raw = pd.DataFrame(
            [
                {
                    "reporter_code": 1,
                    "year": 2000,
                    "classification_code": "H1",
                    "cmd_code": "111111",
                    "partner_code": 8,
                    "trade_value": 100.0,
                }
            ]
        )
        prepared = prepare_exercise_12_item_values(raw, "product_partner_cell", "hs6_harmonized_family", hs_family_mapping=mapping)
        self.assertRegex(prepared.iloc[0]["item_id"], r"^HSF:.*\|partner:8$")

    def test_partner_regions_are_world_bank_only_with_unknown_fallback(self) -> None:
        partner_ref = pd.DataFrame(
            [
                {"partner_code": 840, "partner_iso3": "USA", "partner_name": "USA"},
                {"partner_code": 999, "partner_iso3": "_ZZ", "partner_name": "Synthetic aggregate"},
            ]
        )
        metadata = pd.DataFrame([{"iso3": "USA", "region": "North America", "income_group": "High income", "metadata_source": "world_bank_api"}])
        with patch("trade_concentration_pipeline.partner_reference_table", return_value=partner_ref), patch(
            "trade_concentration_pipeline.fetch_world_bank_country_metadata", return_value=metadata
        ):
            regions = partner_region_table([840, 999]).set_index("partner_code")
        self.assertEqual(regions.loc[840, "partner_region"], "North America")
        self.assertEqual(regions.loc[840, "partner_region_source"], "world_bank")
        self.assertEqual(regions.loc[999, "partner_region"], "Unknown")
        self.assertEqual(regions.loc[999, "partner_region_source"], "unknown_no_world_bank_match")

    def test_partner_code_0_and_aggregate_rows_are_dropped_before_aggregation(self) -> None:
        raw = pd.DataFrame(
            [
                {"reportercode": 1, "period": 2000, "partnercode": 0, "cmdcode": "111111", "flowcode": "X", "primaryvalue": 100, "isaggregate": 0},
                {"reportercode": 1, "period": 2000, "partnercode": 8, "cmdcode": "111111", "flowcode": "X", "primaryvalue": 50, "isaggregate": 0},
                {"reportercode": 1, "period": 2000, "partnercode": 9, "cmdcode": "222222", "flowcode": "X", "primaryvalue": 75, "isaggregate": 1},
            ]
        )
        leaf = extract_leaf_trade(raw)
        self.assertEqual(set(leaf["partner_code"]), {8})
        self.assertEqual(float(leaf["trade_value"].sum()), 50.0)

    def test_gross_memo_summary_is_filtered_to_headline_sample(self) -> None:
        net = pd.DataFrame(
            [
                {
                    "dimension": "product",
                    "horizon": 5,
                    "item_id_mode": "hs6_harmonized_family",
                    "top_definition": "top_10",
                    "driver_category": "existing_top_10",
                    "contribution_share": 0.5,
                }
            ]
        )
        gross = pd.DataFrame(
            [
                {
                    "dimension": "product",
                    "horizon": 5,
                    "item_id_mode": "hs6_harmonized_family",
                    "top_definition": "top_10",
                    "accounting_type": "gross_positive",
                    "driver_category": "existing_top_10",
                    "contribution_share": 0.5,
                },
                {
                    "dimension": "product",
                    "horizon": 5,
                    "item_id_mode": "hs6_revision",
                    "top_definition": "top_5pct",
                    "accounting_type": "gross_positive",
                    "driver_category": "existing_top_5pct",
                    "contribution_share": 0.9,
                },
            ]
        )
        captured: dict[str, str] = {}

        def capture_text(path: Path, text: str) -> None:
            captured["text"] = text

        with patch("trade_concentration_pipeline.write_text", side_effect=capture_text):
            write_exercise_12_memo(net, pd.DataFrame(), pd.DataFrame(), {}, gross_decomposition=gross)

        gross_section = captured["text"].split("## Median Gross Contribution Shares", 1)[1].split("## Interpretation Limits", 1)[0]
        self.assertIn("item_id_mode", gross_section)
        self.assertIn("top_definition", gross_section)
        self.assertIn("hs6_harmonized_family", gross_section)
        self.assertNotIn("hs6_revision", gross_section)


if __name__ == "__main__":
    unittest.main()
