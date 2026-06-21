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

from run_exercise_12_ev_hs4_expansion import (  # noqa: E402
    ACTIVE_THRESHOLD_USD_2024,
    build_combined_cell_window,
    CountryInfo,
    DeflatorInfo,
    build_product_window,
    compute_country_decomposition,
    hs4_product_id,
    load_us_gdp_deflator,
    pooled_summary,
    prepare_hs4_values,
)


class Exercise12EvHs4ExpansionTests(unittest.TestCase):
    def test_hs4_product_id_preserves_leading_zeroes(self) -> None:
        out = hs4_product_id(pd.Series(["101", "010199", "999999"]))
        self.assertEqual(out.tolist(), ["HS4:0001", "HS4:0101", "HS4:9999"])

    def test_deflator_threshold_uses_constant_2024_usd(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "deflator.csv"
            path.write_text(
                "iso3,year,us_gdp_deflator\n"
                "USA,2000,50\n"
                "USA,2001,100\n"
                "USA,2024,100\n",
                encoding="utf-8",
            )
            deflator = load_us_gdp_deflator(path)
        raw = pd.DataFrame(
            [
                {
                    "reporter_code": 1,
                    "year": 2000,
                    "cmd_code": "010101",
                    "partner_code": 2,
                    "trade_value": 25_000.0,
                },
                {
                    "reporter_code": 1,
                    "year": 2001,
                    "cmd_code": "010101",
                    "partner_code": 2,
                    "trade_value": 49_999.0,
                },
            ]
        )
        cells, missing = prepare_hs4_values(raw, deflator)
        self.assertEqual(missing, [])
        values = cells.sort_values("year")["trade_value_2024_usd"].tolist()
        self.assertEqual(values, [50_000.0, 49_999.0])

    def persistent_cells(self) -> pd.DataFrame:
        rows = []

        def add(year: int, product: str, value: float, partner: int = 1) -> None:
            rows.append(
                {
                    "reporter_code": 1,
                    "year": year,
                    "product_id": product,
                    "partner_code": partner,
                    "trade_value_2024_usd": value,
                }
            )

        for year in [2000, 2001]:
            add(year, "HS4:CONT", 100_000.0)
            add(year, "HS4:DIE", 80_000.0)
            add(year, "HS4:ONEBASE", 100_000.0 if year == 2000 else 0.0)
            add(year, "HS4:RESID", 10_000.0)
        for year in [2005, 2006]:
            add(year, "HS4:CONT", 150_000.0)
            add(year, "HS4:NEW", 70_000.0)
            add(year, "HS4:ONEBASE", 100_000.0)
            add(year, "HS4:RESID", 20_000.0)
        return pd.DataFrame(rows)

    def combined_cells(self) -> pd.DataFrame:
        rows = []

        def add(year: int, product: str, partner: int, value: float) -> None:
            rows.append(
                {
                    "reporter_code": 1,
                    "year": year,
                    "product_id": product,
                    "partner_code": partner,
                    "trade_value_2024_usd": value,
                }
            )

        for year in [2000, 2001]:
            add(year, "HS4:CONT", 1, 100_000.0)
            add(year, "HS4:DIE", 1, 80_000.0)
            add(year, "HS4:RESID", 1, 10_000.0)
        for year in [2005, 2006]:
            add(year, "HS4:CONT", 1, 150_000.0)
            add(year, "HS4:CONT", 2, 60_000.0)
            add(year, "HS4:NEW", 1, 70_000.0)
            add(year, "HS4:NEW", 2, 80_000.0)
            add(year, "HS4:RESID", 1, 20_000.0)
        return pd.DataFrame(rows)

    def test_adjacent_two_by_two_persistence_classifies_products(self) -> None:
        product_year = (
            self.persistent_cells()
            .groupby(["reporter_code", "year", "product_id"], as_index=False)["trade_value_2024_usd"]
            .sum()
        )
        paired, _metadata = build_product_window(product_year, CountryInfo(1, "Testland", "TST"), 2000, 5)
        channels = paired.set_index("product_id")["product_channel"].to_dict()
        self.assertEqual(channels["HS4:CONT"], "continuing_product")
        self.assertEqual(channels["HS4:DIE"], "dying_product")
        self.assertEqual(channels["HS4:NEW"], "new_product")
        self.assertEqual(channels["HS4:ONEBASE"], "new_product")
        self.assertEqual(channels["HS4:RESID"], "below_threshold_residual")
        self.assertLess(49_999.0, ACTIVE_THRESHOLD_USD_2024)

    def test_country_decomposition_accounting_and_bottom10_label(self) -> None:
        country = CountryInfo(1, "Testland", "TST")
        product_rows, partner_rows, combined_rows, robustness_rows, diagnostics = compute_country_decomposition(
            self.persistent_cells(),
            country,
            [5],
        )
        self.assertEqual(diagnostics["windows_used"], 1)
        self.assertFalse(partner_rows.empty)
        self.assertFalse(combined_rows.empty)
        totals = product_rows[["total_positive_expansion_2024_usd", "total_net_growth_2024_usd"]].iloc[0]
        self.assertAlmostEqual(
            float(product_rows["positive_expansion_2024_usd"].sum()),
            float(totals["total_positive_expansion_2024_usd"]),
        )
        self.assertAlmostEqual(
            float(product_rows["net_contribution_2024_usd"].sum()),
            float(totals["total_net_growth_2024_usd"]),
        )
        summary = pooled_summary(product_rows)
        self.assertAlmostEqual(float(summary["pooled_positive_expansion_share"].sum()), 1.0)
        self.assertIn("bottom_10pct_low_base_growth", set(robustness_rows["product_definition"]))
        self.assertNotIn("strict_new_product", set(robustness_rows["product_definition"]))

    def test_combined_product_partner_channels_do_not_double_count_overlap(self) -> None:
        cells = self.combined_cells()
        product_year = (
            cells.groupby(["reporter_code", "year", "product_id"], as_index=False)["trade_value_2024_usd"]
            .sum()
        )
        product_paired, metadata = build_product_window(product_year, CountryInfo(1, "Testland", "TST"), 2000, 5)
        combined = build_combined_cell_window(cells, product_paired, metadata)
        product_first = combined.groupby("product_first_channel")["positive_expansion_2024_usd"].sum().to_dict()
        partner_first = combined.groupby("partner_first_channel")["positive_expansion_2024_usd"].sum().to_dict()

        self.assertEqual(product_first["net_new_product"], 150_000.0)
        self.assertEqual(product_first["existing_product_to_new_product_specific_partner"], 60_000.0)
        self.assertEqual(product_first["existing_product_to_existing_product_specific_partner"], 50_000.0)
        self.assertEqual(partner_first["new_reporter_partner_new_product"], 80_000.0)
        self.assertEqual(partner_first["new_reporter_partner_existing_product"], 60_000.0)
        self.assertEqual(partner_first["existing_reporter_partner_new_product"], 70_000.0)
        self.assertEqual(partner_first["existing_reporter_partner_existing_product"], 50_000.0)
        self.assertEqual(combined["positive_expansion_2024_usd"].sum(), 270_000.0)

    def test_combined_views_accounting_sums_to_cell_growth(self) -> None:
        product_rows, _partner_rows, combined_rows, _robustness_rows, _diagnostics = compute_country_decomposition(
            self.combined_cells(),
            CountryInfo(1, "Testland", "TST"),
            [5],
        )
        total_cell_positive = float(
            combined_rows.drop_duplicates(["channel_type", "reporter_code", "base_year", "future_year", "horizon"])
            .iloc[0]["total_positive_expansion_2024_usd"]
        )
        total_cell_net = float(
            combined_rows.drop_duplicates(["channel_type", "reporter_code", "base_year", "future_year", "horizon"])
            .iloc[0]["total_net_growth_2024_usd"]
        )
        for channel_type, rows in combined_rows.groupby("channel_type"):
            self.assertAlmostEqual(float(rows["positive_expansion_2024_usd"].sum()), total_cell_positive)
            self.assertAlmostEqual(float(rows["net_contribution_2024_usd"].sum()), total_cell_net)
            self.assertAlmostEqual(float(rows["positive_expansion_share"].sum()), 1.0)
        self.assertAlmostEqual(
            float(product_rows["net_contribution_2024_usd"].sum()),
            total_cell_net,
        )


if __name__ == "__main__":
    unittest.main()
