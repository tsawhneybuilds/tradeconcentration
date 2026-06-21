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

from run_product_destination_theil import compute_product_destination_theil_metrics  # noqa: E402


class ProductDestinationTheilTests(unittest.TestCase):
    def test_uniform_full_cell_universe_has_zero_theil(self) -> None:
        cells = pd.DataFrame(
            {
                "product_id": ["A", "A", "B", "B"],
                "partner_code": [1, 2, 1, 2],
                "trade_value": [10.0, 10.0, 10.0, 10.0],
            }
        )
        metrics = compute_product_destination_theil_metrics(cells, product_universe_count=2, destination_universe_count=2)
        self.assertAlmostEqual(metrics["overall_product_destination_theil"], 0.0)
        self.assertAlmostEqual(metrics["product_theil"], 0.0)
        self.assertAlmostEqual(metrics["destination_within_product_theil"], 0.0)
        self.assertAlmostEqual(metrics["partner_theil_product_cell_based"], 0.0)
        self.assertAlmostEqual(metrics["product_within_partner_theil"], 0.0)

    def test_single_active_cell_decomposes_into_product_and_destination_margins(self) -> None:
        cells = pd.DataFrame({"product_id": ["A"], "partner_code": [1], "trade_value": [10.0]})
        metrics = compute_product_destination_theil_metrics(cells, product_universe_count=2, destination_universe_count=2)
        self.assertAlmostEqual(metrics["overall_product_destination_theil"], np.log(4.0))
        self.assertAlmostEqual(metrics["overall_product_destination_theil_normalized"], 1.0)
        self.assertAlmostEqual(metrics["product_theil"], np.log(2.0))
        self.assertAlmostEqual(metrics["active_product_theil"], 0.0)
        self.assertAlmostEqual(metrics["inactive_product_margin_theil"], np.log(2.0))
        self.assertAlmostEqual(metrics["destination_within_product_theil"], np.log(2.0))
        self.assertAlmostEqual(metrics["partner_theil_product_cell_based"], np.log(2.0))
        self.assertAlmostEqual(metrics["product_within_partner_theil"], np.log(2.0))
        self.assertAlmostEqual(metrics["product_margin_decomposition_residual"], 0.0)

    def test_product_first_and_partner_first_give_same_total(self) -> None:
        cells = pd.DataFrame(
            {
                "product_id": ["A", "A", "B"],
                "partner_code": [1, 2, 1],
                "trade_value": [4.0, 2.0, 2.0],
            }
        )
        metrics = compute_product_destination_theil_metrics(cells, product_universe_count=3, destination_universe_count=4)
        self.assertAlmostEqual(
            metrics["overall_product_destination_theil"],
            metrics["product_theil"] + metrics["destination_within_product_theil"],
        )
        self.assertAlmostEqual(
            metrics["overall_product_destination_theil"],
            metrics["partner_theil_product_cell_based"] + metrics["product_within_partner_theil"],
        )
        self.assertAlmostEqual(
            metrics["product_theil"],
            metrics["active_product_theil"] + metrics["inactive_product_margin_theil"],
        )
        self.assertEqual(metrics["active_cell_count"], 3)
        self.assertEqual(metrics["universe_cell_count"], 12)

    def test_zero_cells_do_not_require_epsilons(self) -> None:
        cells = pd.DataFrame(
            {
                "product_id": ["A", "B"],
                "partner_code": [1, 2],
                "trade_value": [5.0, 5.0],
            }
        )
        metrics = compute_product_destination_theil_metrics(cells, product_universe_count=2, destination_universe_count=2)
        self.assertAlmostEqual(metrics["overall_product_destination_theil"], np.log(2.0))
        self.assertAlmostEqual(metrics["product_theil"], 0.0)
        self.assertAlmostEqual(metrics["destination_within_product_theil"], np.log(2.0))

    def test_negative_values_are_rejected(self) -> None:
        cells = pd.DataFrame({"product_id": ["A"], "partner_code": [1], "trade_value": [-1.0]})
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            compute_product_destination_theil_metrics(cells, product_universe_count=1, destination_universe_count=1)

    def test_universe_counts_must_cover_active_support(self) -> None:
        cells = pd.DataFrame(
            {
                "product_id": ["A", "B"],
                "partner_code": [1, 2],
                "trade_value": [1.0, 1.0],
            }
        )
        with self.assertRaisesRegex(ValueError, "product_universe_count"):
            compute_product_destination_theil_metrics(cells, product_universe_count=1, destination_universe_count=2)
        with self.assertRaisesRegex(ValueError, "destination_universe_count"):
            compute_product_destination_theil_metrics(cells, product_universe_count=2, destination_universe_count=1)


if __name__ == "__main__":
    unittest.main()
