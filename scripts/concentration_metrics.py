"""Shared active-positive concentration metrics.

These helpers measure inequality among observed positive trade values only.
Zero-inclusive Gini is a different robustness concept because it also embeds
the size of the eligible product or partner universe.
"""

from __future__ import annotations

import math
from typing import Iterable

import numpy as np


def _numeric_array(values: Iterable[float] | np.ndarray) -> np.ndarray:
    to_numpy = getattr(values, "to_numpy", None)
    if callable(to_numpy):
        try:
            arr = to_numpy(dtype=float, na_value=np.nan)
        except TypeError:
            arr = to_numpy(dtype=float)
        return np.asarray(arr, dtype=float).reshape(-1)
    try:
        arr = np.asarray(values, dtype=float)
    except (TypeError, ValueError):
        arr = np.asarray(list(values), dtype=float)
    return arr.reshape(-1)


def _active_values(values: Iterable[float] | np.ndarray) -> np.ndarray:
    arr = _numeric_array(values)
    return arr[np.isfinite(arr) & (arr > 0)]


def active_gini(values: Iterable[float] | np.ndarray) -> float:
    """Finite-sample Gini over strictly positive finite observations."""
    arr = _active_values(values)
    if arr.size == 0:
        return np.nan
    arr.sort()
    total = arr.sum()
    if total <= 0:
        return np.nan
    n = arr.size
    ranks = np.arange(1, n + 1, dtype=float)
    return float((2 * np.sum(ranks * arr) / (n * total)) - ((n + 1) / n))


def active_normalized_gini(values: Iterable[float] | np.ndarray) -> float:
    """Finite-n normalized active Gini over strictly positive finite observations."""
    arr = _active_values(values)
    n = arr.size
    if n == 0:
        return np.nan
    if n <= 1:
        return np.nan
    raw = active_gini(arr)
    upper_bound = (n - 1) / n
    if upper_bound <= 0:
        return np.nan
    return float(raw / upper_bound)


def _nonnegative_finite_values(values: Iterable[float] | np.ndarray) -> np.ndarray:
    arr = _numeric_array(values)
    arr = arr[np.isfinite(arr)]
    if np.any(arr < 0):
        raise ValueError("Theil inputs must be nonnegative.")
    return arr


def theil_from_positive_values(
    values: Iterable[float] | np.ndarray,
    universe_count: int | None = None,
    *,
    normalized: bool = False,
) -> float:
    """Theil over a zero-inclusive universe using only positive observed values.

    Zero-valued cells contribute zero to Theil, so callers can avoid
    materializing the full fixed universe. `universe_count` is the eligible
    universe size. If omitted, the active positive count is used.
    """
    arr = _nonnegative_finite_values(values)
    arr = arr[arr > 0]
    if arr.size == 0:
        return np.nan
    k = int(universe_count) if universe_count is not None else int(arr.size)
    if k < arr.size:
        raise ValueError("universe_count cannot be smaller than the positive active count.")
    if k <= 0:
        return np.nan
    total = float(arr.sum())
    if total <= 0:
        return np.nan
    shares = arr / total
    raw = float(np.sum(shares * np.log(shares * k)))
    if not normalized:
        return raw
    if k <= 1:
        return 0.0 if abs(raw) <= 1e-12 else np.nan
    return raw / math.log(k)


def active_theil(values: Iterable[float] | np.ndarray, *, normalized: bool = False) -> float:
    """Theil over strictly positive finite observations only."""
    arr = _active_values(values)
    if arr.size == 0:
        return np.nan
    return theil_from_positive_values(arr, int(arr.size), normalized=normalized)


def active_hhi(values: Iterable[float] | np.ndarray) -> float:
    """Raw Herfindahl-Hirschman index over strictly positive finite observations."""
    arr = _active_values(values)
    if arr.size == 0:
        return np.nan
    total = float(arr.sum())
    if total <= 0:
        return np.nan
    shares = arr / total
    return float(np.sum(shares * shares))


def active_normalized_hhi(values: Iterable[float] | np.ndarray) -> float:
    """Finite-n normalized active HHI over strictly positive finite observations."""
    arr = _active_values(values)
    n = arr.size
    if n == 0:
        return np.nan
    if n <= 1:
        return np.nan
    raw = active_hhi(arr)
    baseline = 1.0 / n
    denominator = 1.0 - baseline
    if denominator <= 0:
        return np.nan
    return float((raw - baseline) / denominator)


def active_effective_count(values: Iterable[float] | np.ndarray) -> float:
    """Inverse-HHI effective count over strictly positive finite observations."""
    raw_hhi = active_hhi(values)
    if not math.isfinite(raw_hhi) or raw_hhi <= 0:
        return np.nan
    return float(1.0 / raw_hhi)


def fixed_universe_theil(values: Iterable[float] | np.ndarray, *, normalized: bool = False) -> float:
    """Theil over finite nonnegative values, including explicit zeros."""
    arr = _nonnegative_finite_values(values)
    if arr.size == 0 or float(arr.sum()) <= 0:
        return np.nan
    return theil_from_positive_values(arr, int(arr.size), normalized=normalized)


def world_relative_theil(
    country_values: Iterable[float] | np.ndarray,
    benchmark_values: Iterable[float] | np.ndarray,
) -> float:
    """KL/Theil divergence from aligned benchmark values.

    Inputs must be aligned on the same product universe. The country may have
    zeros where the benchmark is positive. A positive country value with a zero
    benchmark value makes the divergence undefined and raises ValueError.
    """
    country = _nonnegative_finite_values(country_values)
    benchmark = _nonnegative_finite_values(benchmark_values)
    if country.size != benchmark.size:
        raise ValueError("country_values and benchmark_values must have the same length.")
    country_total = float(country.sum())
    benchmark_total = float(benchmark.sum())
    if country_total <= 0 or benchmark_total <= 0:
        return np.nan
    positive_country = country > 0
    if np.any(positive_country & (benchmark <= 0)):
        raise ValueError("benchmark_values must be positive wherever country_values are positive.")
    country_share = country[positive_country] / country_total
    benchmark_share = benchmark[positive_country] / benchmark_total
    return float(np.sum(country_share * np.log(country_share / benchmark_share)))


def product_market_theil_decomposition(
    product_ids: Iterable[object] | np.ndarray,
    market_ids: Iterable[object] | np.ndarray,
    values: Iterable[float] | np.ndarray,
    *,
    product_universe_count: int | None = None,
    market_universe_count: int | None = None,
) -> dict[str, float | int]:
    """Decompose product-market Theil into product and within-product market parts.

    The decomposition assumes a uniform product-by-market universe. Zero cells
    do not need to be materialized; missing cells contribute zero.
    """
    products = np.asarray(list(product_ids), dtype=object).reshape(-1)
    markets = np.asarray(list(market_ids), dtype=object).reshape(-1)
    vals = _nonnegative_finite_values(values)
    if products.size != markets.size or products.size != vals.size:
        raise ValueError("product_ids, market_ids, and values must have the same length.")
    active = vals > 0
    products = products[active]
    markets = markets[active]
    vals = vals[active]
    if vals.size == 0:
        return {
            "overall_theil": np.nan,
            "product_component_theil": np.nan,
            "market_within_product_theil": np.nan,
            "active_product_count": 0,
            "active_market_count": 0,
            "active_cell_count": 0,
        }
    p_count = int(product_universe_count) if product_universe_count is not None else int(len(set(products)))
    m_count = int(market_universe_count) if market_universe_count is not None else int(len(set(markets)))
    if p_count <= 0 or m_count <= 0:
        return {
            "overall_theil": np.nan,
            "product_component_theil": np.nan,
            "market_within_product_theil": np.nan,
            "active_product_count": int(len(set(products))),
            "active_market_count": int(len(set(markets))),
            "active_cell_count": int(vals.size),
        }
    if p_count < len(set(products)) or m_count < len(set(markets)):
        raise ValueError("Universe counts cannot be smaller than active product or market counts.")

    total = float(vals.sum())
    cell_shares = vals / total
    overall = float(np.sum(cell_shares * np.log(cell_shares * p_count * m_count)))

    product_totals: dict[object, float] = {}
    for product, value in zip(products, vals):
        product_totals[product] = product_totals.get(product, 0.0) + float(value)
    product_values = np.fromiter(product_totals.values(), dtype=float)
    product_component = theil_from_positive_values(product_values, p_count)
    market_component = overall - product_component
    return {
        "overall_theil": overall,
        "product_component_theil": product_component,
        "market_within_product_theil": market_component,
        "active_product_count": int(len(product_totals)),
        "active_market_count": int(len(set(markets))),
        "active_cell_count": int(vals.size),
    }


def weighted_gini(values: Iterable[float] | np.ndarray, weights: Iterable[float] | np.ndarray) -> float:
    """Weighted Gini over nonnegative finite values with positive finite weights."""
    arr = _numeric_array(values)
    weight_arr = _numeric_array(weights)
    if arr.size != weight_arr.size:
        raise ValueError("values and weights must have the same length.")
    mask = np.isfinite(arr) & np.isfinite(weight_arr) & (weight_arr > 0)
    arr = arr[mask]
    weight_arr = weight_arr[mask]
    if arr.size == 0 or np.any(arr < 0):
        return np.nan
    total_weight = float(weight_arr.sum())
    weighted_total = float(np.sum(weight_arr * arr))
    if total_weight <= 0 or weighted_total <= 0:
        return np.nan

    order = np.argsort(arr, kind="mergesort")
    arr = arr[order]
    weight_arr = weight_arr[order]
    cumulative_weight = np.cumsum(weight_arr)
    cumulative_weighted_value = np.cumsum(weight_arr * arr)
    previous_weight = cumulative_weight - weight_arr
    previous_weighted_value = cumulative_weighted_value - (weight_arr * arr)
    numerator = float(np.sum(weight_arr * ((arr * previous_weight) - previous_weighted_value)))
    return numerator / (weighted_total * total_weight)


def weighted_loo_gini_contributions(values: Iterable[float] | np.ndarray, weights: Iterable[float] | np.ndarray) -> np.ndarray:
    """Weighted Gini minus weighted Gini after removing each observation."""
    raw = _numeric_array(values)
    raw_weights = _numeric_array(weights)
    if raw.size != raw_weights.size:
        raise ValueError("values and weights must have the same length.")
    out = np.full(raw.size, np.nan, dtype=float)
    active = np.isfinite(raw) & np.isfinite(raw_weights) & (raw >= 0) & (raw_weights > 0)
    active_positions = np.flatnonzero(active)
    active_values = raw[active]
    active_weights = raw_weights[active]
    n = active_values.size
    if n <= 1:
        return out

    order = np.argsort(active_values, kind="mergesort")
    sorted_values = active_values[order]
    sorted_weights = active_weights[order]
    sorted_positions = active_positions[order]

    total_weight = float(sorted_weights.sum())
    weighted_total = float(np.sum(sorted_weights * sorted_values))
    if total_weight <= 0 or weighted_total <= 0:
        return out

    cumulative_weight = np.cumsum(sorted_weights)
    cumulative_weighted_value = np.cumsum(sorted_weights * sorted_values)
    previous_weight = cumulative_weight - sorted_weights
    previous_weighted_value = cumulative_weighted_value - (sorted_weights * sorted_values)
    numerator_terms = sorted_weights * ((sorted_values * previous_weight) - previous_weighted_value)
    numerator = float(numerator_terms.sum())

    suffix_weight = total_weight - cumulative_weight
    suffix_weighted_value = weighted_total - cumulative_weighted_value
    below_pairs = numerator_terms
    above_pairs = sorted_weights * (suffix_weighted_value - (sorted_values * suffix_weight))
    pairs_touching_observation = below_pairs + above_pairs

    total_weight_without = total_weight - sorted_weights
    weighted_total_without = weighted_total - (sorted_weights * sorted_values)
    valid = (total_weight_without > 0) & (weighted_total_without > 0)

    total_gini = numerator / (weighted_total * total_weight)
    gini_without = np.full(n, np.nan, dtype=float)
    gini_without[valid] = (
        (numerator - pairs_touching_observation)[valid]
        / (weighted_total_without[valid] * total_weight_without[valid])
    )
    out[sorted_positions] = total_gini - gini_without
    return out


def active_top_share(values: Iterable[float] | np.ndarray, n: int | None = None, pct: float | None = None) -> float:
    """Top share over strictly positive finite observations."""
    arr = _active_values(values)
    if arr.size == 0:
        return np.nan
    arr.sort()
    arr = arr[::-1]
    if pct is not None:
        k = max(1, int(math.ceil(arr.size * pct)))
    elif n is not None:
        k = min(n, arr.size)
    else:
        raise ValueError("Need n or pct.")
    return float(arr[:k].sum() / arr.sum())


def active_loo_gini_contributions(values: Iterable[float] | np.ndarray) -> np.ndarray:
    """Full active Gini minus active Gini after removing each observation."""
    raw = _numeric_array(values)
    out = np.full(raw.size, np.nan, dtype=float)
    active = np.isfinite(raw) & (raw > 0)
    active_positions = np.flatnonzero(active)
    active_values = raw[active]
    n = active_values.size
    if n <= 1:
        return out

    order = np.argsort(active_values, kind="mergesort")
    sorted_values = active_values[order]
    sorted_positions = active_positions[order]

    total_gini = active_gini(sorted_values)
    total = float(sorted_values.sum())
    ranks = np.arange(1, n + 1, dtype=float)
    weighted_sum = float(np.sum(ranks * sorted_values))
    suffix_after = total - np.cumsum(sorted_values)
    total_without = total - sorted_values
    weighted_without = weighted_sum - ranks * sorted_values - suffix_after

    n2 = n - 1
    gini_without = np.full(n, np.nan, dtype=float)
    valid = total_without > 0
    gini_without[valid] = (2 * weighted_without[valid] / (n2 * total_without[valid])) - ((n2 + 1) / n2)
    out[sorted_positions] = total_gini - gini_without
    return out


def active_loo_hhi_contributions(values: Iterable[float] | np.ndarray) -> np.ndarray:
    """Full active HHI minus active HHI after removing each observation."""
    raw = _numeric_array(values)
    out = np.full(raw.size, np.nan, dtype=float)
    active = np.isfinite(raw) & (raw > 0)
    active_positions = np.flatnonzero(active)
    active_values = raw[active]
    n = active_values.size
    if n <= 1:
        return out

    total = float(active_values.sum())
    square_total = float(np.sum(active_values * active_values))
    if total <= 0:
        return out
    full_hhi = square_total / (total * total)
    total_without = total - active_values
    square_without = square_total - (active_values * active_values)
    valid = total_without > 0
    hhi_without = np.full(n, np.nan, dtype=float)
    hhi_without[valid] = square_without[valid] / (total_without[valid] * total_without[valid])
    out[active_positions] = full_hhi - hhi_without
    return out
