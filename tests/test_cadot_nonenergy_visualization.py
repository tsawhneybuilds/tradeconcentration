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

import build_cadot_nonenergy_visualization as nonenergy


class CadotNonenergyVisualizationTests(unittest.TestCase):
    def test_nonenergy_filter_excludes_energy_and_ambiguous_bins(self) -> None:
        self.assertEqual(
            set(nonenergy.NONENERGY_BINS),
            {"capital_goods", "intermediates", "final_consumption"},
        )
        self.assertNotIn("energy", nonenergy.NONENERGY_BINS)
        self.assertNotIn("unmapped_or_ambiguous", nonenergy.NONENERGY_BINS)

    def test_metric_decomposition_reconciles_all_buckets(self) -> None:
        product = pd.DataFrame(
            {
                "cmd_code": ["010101", "020202", "030303", "040404", "050505", "060606"],
                "trade_value": [60.0, 20.0, 10.0, 5.0, 3.0, 2.0],
            }
        )

        row, ranked = nonenergy.metric_decomposition(
            product, fixed_universe_count=10
        )

        self.assertAlmostEqual(
            sum(row[f"{bucket}_share"] for bucket in nonenergy.BUCKETS), 1.0
        )
        for metric in nonenergy.METRICS:
            self.assertAlmostEqual(
                sum(
                    row[f"{bucket}_{metric}_contribution"]
                    for bucket in nonenergy.BUCKETS
                ),
                row[metric],
            )
        self.assertAlmostEqual(row["gini"], row["direct_active_gini"])
        self.assertAlmostEqual(row["hhi"], row["direct_active_hhi"])
        expected_theil = float(
            np.sum(ranked["share"] * np.log(ranked["share"] * 10))
        )
        self.assertAlmostEqual(row["theil"], expected_theil)

    def test_rank_bucket_masks_partition_positive_ranks(self) -> None:
        ranks = pd.Series(np.arange(1, 251))
        masks = nonenergy.rank_bucket_masks(ranks)
        membership = sum(mask.astype(int) for mask in masks.values())

        self.assertTrue(membership.eq(1).all())
        self.assertEqual(int(masks["top5"].sum()), 5)
        self.assertEqual(int(masks["rank6_50"].sum()), 45)
        self.assertEqual(int(masks["rank51_200"].sum()), 150)
        self.assertEqual(int(masks["rank201_plus"].sum()), 50)


if __name__ == "__main__":
    unittest.main()
