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

from concentration_metrics import (
    active_effective_count,
    active_gini,
    active_hhi,
    active_normalized_gini,
    active_normalized_hhi,
    active_loo_gini_contributions,
    active_loo_hhi_contributions,
    active_top_share,
    active_theil,
    fixed_universe_theil,
    product_market_theil_decomposition,
    theil_from_positive_values,
    weighted_gini,
    weighted_loo_gini_contributions,
    world_relative_theil,
)


def zero_inclusive_pairwise_gini(values: list[float] | np.ndarray) -> float:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0 or np.any(arr < 0) or arr.sum() <= 0:
        return np.nan
    return float(np.abs(arr[:, None] - arr[None, :]).sum() / (2 * arr.size * arr.sum()))


def brute_weighted_gini(values: list[float] | np.ndarray, weights: list[float] | np.ndarray) -> float:
    arr = np.asarray(values, dtype=float)
    weight_arr = np.asarray(weights, dtype=float)
    mask = np.isfinite(arr) & np.isfinite(weight_arr) & (weight_arr > 0)
    arr = arr[mask]
    weight_arr = weight_arr[mask]
    if arr.size == 0 or np.any(arr < 0):
        return np.nan
    weighted_total = np.sum(weight_arr * arr)
    total_weight = np.sum(weight_arr)
    if weighted_total <= 0 or total_weight <= 0:
        return np.nan
    pairwise = np.abs(arr[:, None] - arr[None, :])
    weight_pairs = weight_arr[:, None] * weight_arr[None, :]
    return float((pairwise * weight_pairs).sum() / (2 * total_weight * weighted_total))


class ActiveGiniTests(unittest.TestCase):
    def test_equal_positive_values_return_zero(self) -> None:
        self.assertEqual(active_gini([5, 5, 5]), 0.0)

    def test_matches_pairwise_reference(self) -> None:
        self.assertAlmostEqual(active_gini([1, 2, 3]), zero_inclusive_pairwise_gini([1, 2, 3]))

    def test_zero_is_not_part_of_active_only_gini(self) -> None:
        self.assertEqual(active_gini([0, 1]), 0.0)
        self.assertEqual(zero_inclusive_pairwise_gini([0, 1]), 0.5)

    def test_top_share_uses_active_positive_denominator(self) -> None:
        values = [0, np.nan, 1, 2, 7]
        self.assertAlmostEqual(active_top_share(values, n=1), 0.7)
        self.assertAlmostEqual(active_top_share(values, n=2), 0.9)
        self.assertAlmostEqual(active_top_share(values, pct=0.10), 0.7)

    def test_nullable_series_missing_values_are_ignored(self) -> None:
        values = pd.Series([1, pd.NA, 2, 0], dtype="Float64")
        self.assertAlmostEqual(active_gini(values), active_gini([1, 2]))

    def test_active_gini_respects_active_count_upper_bound(self) -> None:
        rng = np.random.default_rng(1729)
        for n in range(2, 50):
            values = rng.lognormal(size=n)
            gini = active_gini(values)
            self.assertGreaterEqual(gini, 0.0)
            self.assertLessEqual(gini, (n - 1) / n + 1e-12)

    def test_normalized_gini_rescales_by_finite_sample_upper_bound(self) -> None:
        values = np.array([1.0, 2.0, 7.0])
        raw = active_gini(values)
        expected = raw / ((len(values) - 1) / len(values))
        self.assertAlmostEqual(active_normalized_gini(values), expected)
        self.assertEqual(active_normalized_gini([5.0, 5.0, 5.0]), 0.0)

    def test_weighted_gini_matches_pairwise_reference(self) -> None:
        samples = [
            (np.array([0.0, 1.0]), np.array([1.0, 1.0])),
            (np.array([1.0, 2.0, 3.0]), np.array([0.2, 0.3, 0.5])),
            (np.array([4.0, 4.0, 4.0]), np.array([10.0, 1.0, 2.0])),
            (np.array([np.nan, 0.0, 5.0, 9.0]), np.array([1.0, 2.0, 3.0, 4.0])),
        ]
        rng = np.random.default_rng(2027)
        samples.extend((rng.lognormal(size=n), rng.uniform(0.01, 2.0, size=n)) for n in range(2, 30))
        for values, weights in samples:
            self.assertAlmostEqual(weighted_gini(values, weights), brute_weighted_gini(values, weights))

    def test_weighted_gini_rejects_mismatched_lengths(self) -> None:
        with self.assertRaisesRegex(ValueError, "same length"):
            weighted_gini([1, 2], [1])

    def test_loo_contributions_match_bruteforce(self) -> None:
        samples = [
            np.array([1.0, 2.0, 3.0, 4.0]),
            np.array([2.0, 2.0, 5.0, 5.0, 10.0]),
            np.array([0.0, 1.0, 3.0, np.nan, 9.0]),
        ]
        rng = np.random.default_rng(2026)
        samples.extend(rng.lognormal(size=n) for n in range(2, 12))

        for values in samples:
            fast = active_loo_gini_contributions(values)
            brute = np.full(values.size, np.nan, dtype=float)
            full = active_gini(values)
            for idx, value in enumerate(values):
                if np.isfinite(value) and value > 0:
                    brute[idx] = full - active_gini(np.delete(values, idx))
            np.testing.assert_allclose(fast, brute, equal_nan=True, atol=1e-12)

    def test_weighted_loo_contributions_match_bruteforce(self) -> None:
        samples = [
            (np.array([1.0, 1.0, 1.0]), np.array([0.2, 0.3, 0.5])),
            (np.array([0.0, 1.0, 5.0]), np.array([0.7, 0.2, 0.1])),
            (np.array([np.nan, 0.0, 2.0, 9.0]), np.array([1.0, 2.0, 3.0, 4.0])),
        ]
        rng = np.random.default_rng(2028)
        samples.extend((rng.lognormal(size=n), rng.uniform(0.01, 2.0, size=n)) for n in range(2, 20))

        for values, weights in samples:
            fast = weighted_loo_gini_contributions(values, weights)
            brute = np.full(values.size, np.nan, dtype=float)
            full = weighted_gini(values, weights)
            for idx, value in enumerate(values):
                if np.isfinite(value) and np.isfinite(weights[idx]) and value >= 0 and weights[idx] > 0:
                    brute[idx] = full - weighted_gini(np.delete(values, idx), np.delete(weights, idx))
            np.testing.assert_allclose(fast, brute, equal_nan=True, atol=1e-12)


class TheilTests(unittest.TestCase):
    def test_active_equal_positive_values_return_zero(self) -> None:
        self.assertAlmostEqual(active_theil([5.0, 5.0, 5.0]), 0.0)

    def test_fixed_universe_monopoly_equals_log_k(self) -> None:
        self.assertAlmostEqual(theil_from_positive_values([10.0], universe_count=4), np.log(4.0))
        self.assertAlmostEqual(fixed_universe_theil([0.0, 0.0, 10.0, 0.0]), np.log(4.0))

    def test_normalized_fixed_universe_monopoly_equals_one(self) -> None:
        self.assertAlmostEqual(theil_from_positive_values([10.0], universe_count=4, normalized=True), 1.0)
        self.assertAlmostEqual(fixed_universe_theil([0.0, 0.0, 10.0, 0.0], normalized=True), 1.0)

    def test_active_only_theil_does_not_capture_missing_products(self) -> None:
        self.assertAlmostEqual(active_theil([10.0]), 0.0)
        self.assertGreater(theil_from_positive_values([10.0], universe_count=4), 0.0)

    def test_theil_rejects_negative_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            fixed_universe_theil([1.0, -1.0])
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            theil_from_positive_values([1.0, -1.0], universe_count=2)

    def test_world_relative_theil_is_zero_when_shares_match(self) -> None:
        self.assertAlmostEqual(world_relative_theil([2.0, 3.0, 5.0], [20.0, 30.0, 50.0]), 0.0)

    def test_world_relative_theil_rejects_positive_country_zero_benchmark(self) -> None:
        with self.assertRaisesRegex(ValueError, "positive wherever"):
            world_relative_theil([1.0, 0.0], [0.0, 2.0])

    def test_product_market_decomposition_identity(self) -> None:
        result = product_market_theil_decomposition(
            ["A", "A", "B"],
            ["US", "FR", "US"],
            [4.0, 2.0, 2.0],
            product_universe_count=2,
            market_universe_count=2,
        )
        self.assertAlmostEqual(
            result["overall_theil"],
            result["product_component_theil"] + result["market_within_product_theil"],
        )
        self.assertEqual(result["active_product_count"], 2)
        self.assertEqual(result["active_market_count"], 2)
        self.assertEqual(result["active_cell_count"], 3)


class HHITests(unittest.TestCase):
    def test_equal_positive_values_return_inverse_active_count(self) -> None:
        self.assertAlmostEqual(active_hhi([5.0, 5.0, 5.0, 5.0]), 0.25)

    def test_monopoly_returns_one(self) -> None:
        self.assertAlmostEqual(active_hhi([0.0, np.nan, 10.0]), 1.0)

    def test_hhi_bounds(self) -> None:
        rng = np.random.default_rng(2031)
        for n in range(1, 50):
            values = rng.lognormal(size=n)
            hhi = active_hhi(values)
            self.assertGreaterEqual(hhi, 1.0 / n - 1e-12)
            self.assertLessEqual(hhi, 1.0 + 1e-12)

    def test_normalized_hhi_and_effective_count(self) -> None:
        values = np.array([5.0, 5.0, 5.0, 5.0])
        self.assertAlmostEqual(active_normalized_hhi(values), 0.0)
        self.assertAlmostEqual(active_effective_count(values), 4.0)

        uneven = np.array([1.0, 1.0, 8.0])
        raw_hhi = active_hhi(uneven)
        expected = (raw_hhi - (1 / 3)) / (1 - (1 / 3))
        self.assertAlmostEqual(active_normalized_hhi(uneven), expected)
        self.assertAlmostEqual(active_effective_count(uneven), 1.0 / raw_hhi)

    def test_loo_hhi_contributions_match_bruteforce(self) -> None:
        samples = [
            np.array([1.0, 2.0, 3.0, 4.0]),
            np.array([2.0, 2.0, 5.0, 5.0, 10.0]),
            np.array([0.0, 1.0, 3.0, np.nan, 9.0]),
        ]
        rng = np.random.default_rng(2032)
        samples.extend(rng.lognormal(size=n) for n in range(2, 12))

        for values in samples:
            fast = active_loo_hhi_contributions(values)
            brute = np.full(values.size, np.nan, dtype=float)
            full = active_hhi(values)
            for idx, value in enumerate(values):
                if np.isfinite(value) and value > 0:
                    brute[idx] = full - active_hhi(np.delete(values, idx))
            np.testing.assert_allclose(fast, brute, equal_nan=True, atol=1e-12)


if __name__ == "__main__":
    unittest.main()
