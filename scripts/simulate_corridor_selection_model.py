#!/usr/bin/env python3
"""Toy simulation for the corridor-selection trade concentration model.

This is not a calibrated quantitative trade model. It is a reproducible
sanity check for the model primitives in
results/three_country_components_model.md.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

import numpy as np


def gini(values: np.ndarray) -> float:
    x = np.asarray(values, dtype=float).ravel()
    x = x[x > 0]
    if x.size == 0 or x.sum() == 0:
        return float("nan")
    xs = np.sort(x)
    n = xs.size
    return float((2 * np.arange(1, n + 1) @ xs) / (n * xs.sum()) - (n + 1) / n)


def top_share(values: np.ndarray, k: int) -> float:
    x = np.asarray(values, dtype=float).ravel()
    x = x[x > 0]
    if x.size == 0:
        return float("nan")
    return float(np.sort(x)[-k:].sum() / x.sum())


def simulate(
    *,
    seed: int,
    firms: int,
    products: int,
    destinations: int,
    sources: int,
    domestic_import_scale: float,
) -> dict[str, float | int]:
    rng = np.random.default_rng(seed)
    sigma = 4.0

    phi = rng.pareto(3.0, firms) + 1.0
    product_capability = np.exp(rng.normal(0, 1.0, (firms, products)))

    product_demand = np.exp(rng.normal(0, 0.8, products))
    destination_demand = np.exp(rng.normal(0, 1.0, destinations))
    destination_trade_cost = np.exp(rng.normal(0, 0.35, destinations))

    source_cost = np.exp(rng.normal(0, 0.75, sources))
    source_policy = np.exp(rng.normal(0, 0.65, (products, sources)))
    input_intensity = rng.beta(2, 4, products)

    domestic_import_lump = np.exp(rng.normal(0, 2.0, products))
    source_quality = 1 / (source_cost[None, :] * source_policy)
    best_source_gain = source_quality.max(axis=1)
    source_gain = best_source_gain**input_intensity

    firm_product_strength = phi[:, None] * product_capability * source_gain[None, :]
    firm_product_active = firm_product_strength > np.quantile(
        firm_product_strength, 0.88
    )

    exports = np.zeros((products, destinations))
    for j in range(products):
        active_firms = np.where(firm_product_active[:, j])[0]
        if active_firms.size == 0:
            continue
        for d in range(destinations):
            score = (
                firm_product_strength[active_firms, j]
                * product_demand[j]
                * destination_demand[d]
                * destination_trade_cost[d] ** (-(sigma - 1))
            )
            cutoff = np.quantile(score, 0.78) * (0.85 + 0.3 * rng.random())
            exports[j, d] = (score[score > cutoff] ** 0.75).sum()

    production_imports = np.zeros((products, sources))
    for j in range(products):
        product_exports = exports[j].sum()
        source_shares = source_quality[j] ** 2.2
        source_shares *= source_shares > np.quantile(source_shares, 0.82)
        if source_shares.sum() > 0:
            source_shares /= source_shares.sum()
        production_imports[j] = input_intensity[j] * product_exports * source_shares

    final_imports = np.zeros((products, sources))
    final_import_base = exports.sum() / products * domestic_import_scale
    for j in range(products):
        source_shares = (1 / source_cost) ** 1.5 * np.exp(rng.normal(0, 0.6, sources))
        source_shares *= source_shares > np.quantile(source_shares, 0.80)
        source_shares /= source_shares.sum()
        final_imports[j] = domestic_import_lump[j] * source_shares * final_import_base

    imports = production_imports + final_imports

    export_products = exports.sum(axis=1)
    export_partners = exports.sum(axis=0)
    export_cells = exports.ravel()
    import_products = imports.sum(axis=1)
    import_sources = imports.sum(axis=0)
    import_source_cells = imports.ravel()

    product_mask = (import_products > 0) & (export_products > 0)
    broad_product_corr = float(
        np.corrcoef(
            np.log1p(import_products[product_mask]),
            np.log1p(export_products[product_mask]),
        )[0, 1]
    )

    return {
        "export_product_gini": gini(export_products),
        "export_partner_gini": gini(export_partners),
        "export_product_partner_cell_gini": gini(export_cells),
        "import_product_gini": gini(import_products),
        "import_source_gini": gini(import_sources),
        "import_product_source_cell_gini": gini(import_source_cells),
        "export_top5_product_share": top_share(export_products, 5),
        "export_top5_partner_share": top_share(export_partners, 5),
        "import_top5_product_share": top_share(import_products, 5),
        "import_top5_source_share": top_share(import_sources, 5),
        "broad_log_import_export_product_corr": broad_product_corr,
        "production_input_share_of_imports": float(production_imports.sum() / imports.sum()),
        "active_export_products": int((export_products > 0).sum()),
        "active_export_partners": int((export_partners > 0).sum()),
        "active_export_cells": int((exports > 0).sum()),
        "active_import_products": int((import_products > 0).sum()),
        "active_import_sources": int((import_sources > 0).sum()),
        "active_import_source_cells": int((imports > 0).sum()),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20260529)
    parser.add_argument("--firms", type=int, default=6000)
    parser.add_argument("--products", type=int, default=80)
    parser.add_argument("--destinations", type=int, default=25)
    parser.add_argument("--sources", type=int, default=20)
    parser.add_argument("--domestic-import-scale", type=float, default=0.55)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    moments = simulate(
        seed=args.seed,
        firms=args.firms,
        products=args.products,
        destinations=args.destinations,
        sources=args.sources,
        domestic_import_scale=args.domestic_import_scale,
    )
    for key, value in moments.items():
        if isinstance(value, float):
            print(f"{key}: {value:.3f}")
        else:
            print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
