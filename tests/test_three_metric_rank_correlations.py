from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_three_metric_rank_correlations as tmrc


class ThreeMetricRankCorrelationTests(unittest.TestCase):
    def test_filtered_panel_matches_expected_counts(self) -> None:
        panel = tmrc.load_product_panel(tmrc.input_path())
        filtered = tmrc.filter_product_panel(panel)
        counts = tmrc.validate_filtered_panel(filtered)
        self.assertEqual(counts[tmrc.OVERALL_FLOW_LABEL], 7509)
        self.assertEqual(counts["Exports"], 3753)
        self.assertEqual(counts["Imports"], 3756)

    def test_correlations_match_expected_pooled_values(self) -> None:
        panel = tmrc.load_product_panel(tmrc.input_path())
        filtered = tmrc.filter_product_panel(panel)
        results = tmrc.compute_pairwise_correlations(filtered)
        tmrc.validate_results(results)
        pooled = results[
            results["flow"].eq(tmrc.OVERALL_FLOW_LABEL)
            & results["correlation_type"].eq("spearman_correlation")
        ].copy()
        expected = {
            ("gini", "theil"): 0.918386226693,
            ("gini", "hhi"): 0.836245300958,
            ("theil", "hhi"): 0.952105402083,
        }
        for metric_pair, value in expected.items():
            metric_x, metric_y = metric_pair
            observed = float(
                pooled[pooled["metric_x"].eq(metric_x) & pooled["metric_y"].eq(metric_y)]["correlation_value"].iloc[0]
            )
            self.assertAlmostEqual(observed, value, places=9)

    def test_rank_and_spearman_are_identical_within_tolerance(self) -> None:
        panel = tmrc.load_product_panel(tmrc.input_path())
        filtered = tmrc.filter_product_panel(panel)
        results = tmrc.compute_pairwise_correlations(filtered)
        wide = results.pivot_table(
            index=["flow", "metric_x", "metric_y", "nobs"],
            columns="correlation_type",
            values="correlation_value",
        ).reset_index()
        diff = (wide["spearman_correlation"] - wide["rank_correlation"]).abs()
        self.assertTrue((diff <= tmrc.TOLERANCE).all())


if __name__ == "__main__":
    unittest.main()
