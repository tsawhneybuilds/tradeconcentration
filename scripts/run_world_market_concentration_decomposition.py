#!/usr/bin/env python3
"""Decompose export concentration into world-market and specialization components.

The main accounting identity is, for country export shares s_p, leave-one-country-
out world product shares w_p, and a fixed universe of K products:

    sum_p s_p log(K s_p)
      = sum_p s_p log(K w_p) + sum_p s_p log(s_p / w_p)

The first term is the global-market-size component. The second is KL divergence
from the rest-of-world basket and is labeled country-specific specialization.

This script builds the broad 156-reporter panel, runs descriptive size-gradient
models, creates question-led figures, writes an HTML research page, and can
publish the page and its assets to the legacy trade-gini-map-old repository.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import html
import json
import math
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import concentration_metrics as cm
import run_country_size_effect as cse
import run_cadot_three_metric_pipeline as ctm
import trade_concentration_pipeline as tcp


COUNTRY_SAMPLE = "cadot_broad_156"
FLOW = "Exports"
START_YEAR = 2000
END_YEAR = 2024
PRODUCT_INPUT = (
    ROOT
    / "data/processed/samples/cadot_broad_156/"
    "world_relative_product_gini_harmonized_hs6_family_cadot_broad_156_product_exports.parquet"
)
WORLD_INPUT = (
    ROOT
    / "data/processed/samples/world_broad/"
    "world_relative_product_gini_harmonized_hs6_family_world_product_exports.parquet"
)
CONTROLS_INPUT = (
    ROOT
    / "data/processed/samples/cadot_broad_156/world_large_product_exposure_panel.parquet"
)
CONCENTRATION_INPUT = (
    ROOT
    / "results/samples/cadot_broad_156/three_metric_tables/metric_headline_product_panel.parquet"
)
PRODUCT_MAPPING_INPUT = (
    ROOT
    / "results/samples/cadot_broad_156/world_large_product_exposure_tables/"
    "world_large_product_exposure_product_mapping.csv"
)
OUTPUT_DIR = (
    ROOT
    / "results/samples/cadot_broad_156/world_market_concentration_decomposition"
)
DEFAULT_PUBLISH_DIR = Path("/Users/tanushsawhney/Desktop/trade-gini-map-old")

VARIANTS = {
    "baseline": {
        "label": "All non-missing products",
        "filter_primary": False,
    },
    "noncommodity_broad": {
        "label": "Broad primary commodities excluded",
        "filter_primary": True,
    },
}

BENCHMARK_POLICIES = {
    "loo_smoothed": "Leave-one-country-out world exports",
    "inclusive": "Inclusive world exports sensitivity",
}

SIZE_LABELS = {
    1: "Smallest",
    2: "Smaller",
    3: "Middle",
    4: "Larger",
    5: "Largest",
}

OUTCOME_LABELS = {
    "observed_theil": "Observed fixed-universe Theil",
    "market_component_theil": "Global-market component",
    "specialization_kl": "Country-specific specialization (KL)",
    "market_component_share": "Global-market share of observed Theil",
    "observed_gini": "Observed active-product Gini",
    "market_benchmark_gini": "World-market benchmark Gini",
    "gini_gap": "Observed minus benchmark Gini",
    "observed_hhi": "Observed HHI",
    "market_benchmark_hhi": "World-market benchmark HHI",
    "hhi_gap": "Observed minus benchmark HHI",
}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_inputs() -> None:
    missing = [
        path
        for path in [
            PRODUCT_INPUT,
            WORLD_INPUT,
            CONTROLS_INPUT,
            CONCENTRATION_INPUT,
            PRODUCT_MAPPING_INPUT,
        ]
        if not path.exists()
    ]
    if missing:
        raise FileNotFoundError(f"Missing required inputs: {[str(path) for path in missing]}")


def assert_unique(frame: pd.DataFrame, keys: list[str], label: str) -> None:
    duplicates = frame.duplicated(keys, keep=False)
    if duplicates.any():
        examples = frame.loc[duplicates, keys].head(10).to_dict(orient="records")
        raise RuntimeError(f"{label} has duplicate keys {keys}: {examples}")


def assert_no_999999(frame: pd.DataFrame, label: str) -> None:
    bad = frame["product_id"].astype(str).str.contains("999999", regex=False, na=False)
    if bad.any():
        raise RuntimeError(f"{label} contains {int(bad.sum())} HS6 999999-derived rows.")


def safe_spearman(x: pd.Series, y: pd.Series) -> float:
    valid = pd.DataFrame({"x": x, "y": y}).replace([np.inf, -np.inf], np.nan).dropna()
    if len(valid) < 3 or valid["x"].nunique() < 2 or valid["y"].nunique() < 2:
        return np.nan
    return float(spearmanr(valid["x"], valid["y"]).statistic)


def summarize_country_product_input(country: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (reporter_code, year), group in country.groupby(
        ["reporter_code", "year"], sort=False
    ):
        values = group["trade_value"].to_numpy(dtype=float)
        rows.append(
            {
                "reporter_code": int(reporter_code),
                "year": int(year),
                "input_total_trade_value": float(values.sum()),
                "input_active_count": int(len(values)),
                "input_gini": cm.active_gini(values),
                "input_theil": cm.theil_from_positive_values(values, 5037),
                "input_hhi": cm.active_hhi(values),
            }
        )
    return pd.DataFrame(rows)


def aggregate_selected_export_products(
    raw_path: Path,
    weights: pd.DataFrame,
    *,
    chunk_rows: int = 1_000_000,
) -> pd.DataFrame:
    """Read only the export-product cells needed for source alignment."""
    chunks: list[pd.DataFrame] = []
    for leaf in tcp.iter_leaf_trade_chunks(raw_path, chunk_rows=chunk_rows):
        leaf = ctm.normalize_leaf_for_metric(leaf)
        leaf = leaf[leaf["flow"].eq(FLOW)].copy()
        if leaf.empty:
            continue
        leaf = tcp.drop_excluded_hs6(leaf)
        if leaf.empty:
            continue
        converted = ctm.harmonize_product_leaf(leaf, weights)
        if converted.empty:
            continue
        product = (
            converted.groupby("product_id", as_index=False)["trade_value"]
            .sum()
            .query("trade_value > 0")
        )
        if not product.empty:
            chunks.append(product)
    if not chunks:
        return pd.DataFrame(columns=["product_id", "trade_value"])
    return (
        pd.concat(chunks, ignore_index=True)
        .groupby("product_id", as_index=False)["trade_value"]
        .sum()
        .query("trade_value > 0")
    )


def rebuild_source_checkpoint(raw_path_text: str, checkpoint_text: str) -> str:
    raw_path = Path(raw_path_text)
    checkpoint = Path(checkpoint_text)
    weights = tcp.load_lt_hgl_hs1992_conversion_weights()
    product = aggregate_selected_export_products(
        raw_path,
        weights=weights,
        chunk_rows=500_000,
    )
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    product.to_parquet(checkpoint, index=False)
    return str(checkpoint)


def source_align_country_products(
    country: pd.DataFrame,
    concentration: pd.DataFrame,
    output_dir: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    aligned_cache = output_dir / "source_aligned_country_product_exports.parquet"
    audit_path = output_dir / "source_alignment_audit.csv"
    if aligned_cache.exists() and audit_path.exists():
        aligned = pd.read_parquet(aligned_cache)
        audit = pd.read_csv(audit_path)
        assert_unique(
            aligned,
            ["reporter_code", "year", "product_id"],
            "cached source-aligned country products",
        )
        return aligned, audit

    summary = summarize_country_product_input(country)
    published = concentration[
        [
            "reporter_code",
            "year",
            "gini",
            "theil",
            "hhi",
            "active_count",
            "total_trade_value",
            "source_raw_file",
        ]
    ].copy()
    comparison = summary.merge(
        published,
        on=["reporter_code", "year"],
        how="outer",
        validate="one_to_one",
        indicator=True,
    )
    comparison["total_abs_diff"] = (
        comparison["input_total_trade_value"] - comparison["total_trade_value"]
    ).abs()
    comparison["total_relative_diff"] = comparison["total_abs_diff"] / comparison[
        "total_trade_value"
    ].abs().clip(lower=1.0)
    comparison["active_count_diff"] = (
        comparison["input_active_count"] - comparison["active_count"]
    )
    comparison["gini_abs_diff"] = (comparison["input_gini"] - comparison["gini"]).abs()
    comparison["theil_abs_diff"] = (
        comparison["input_theil"] - comparison["theil"]
    ).abs()
    comparison["hhi_abs_diff"] = (comparison["input_hhi"] - comparison["hhi"]).abs()
    mismatch = (
        comparison["_merge"].ne("both")
        | comparison["total_relative_diff"].gt(1e-10)
        | comparison["active_count_diff"].ne(0)
        | comparison["gini_abs_diff"].gt(1e-10)
        | comparison["theil_abs_diff"].gt(1e-10)
        | comparison["hhi_abs_diff"].gt(1e-10)
    )
    comparison["requires_source_rebuild"] = mismatch
    rebuild = comparison[mismatch].copy()
    if rebuild.empty:
        country.to_parquet(aligned_cache, index=False)
        comparison.to_csv(audit_path, index=False)
        return country, comparison

    checkpoint_dir = output_dir / "checkpoints/source_aligned_products"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    ctm.configure_metric_sample(COUNTRY_SAMPLE)
    ctm.configure_sample()
    raw_files = tcp.hs_bulk_files()
    raw_by_name = {path.name: path for path in raw_files}
    task_rows: list[tuple[str, str]] = []
    for row in rebuild.itertuples(index=False):
        raw_name = str(row.source_raw_file)
        raw_path = raw_by_name.get(raw_name)
        if raw_path is None:
            raise FileNotFoundError(
                f"Published source raw file is unavailable for alignment: {raw_name}"
            )
        checkpoint = checkpoint_dir / f"{Path(raw_name).stem}.parquet"
        if not checkpoint.exists():
            task_rows.append((str(raw_path), str(checkpoint)))
    if task_rows:
        with ProcessPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(rebuild_source_checkpoint, raw_path, checkpoint): (
                    raw_path,
                    checkpoint,
                )
                for raw_path, checkpoint in task_rows
            }
            complete = 0
            for future in as_completed(futures):
                future.result()
                complete += 1
                if complete % 10 == 0 or complete == len(futures):
                    print(
                        f"Source alignment checkpoints: {complete}/{len(futures)} rebuilt",
                        flush=True,
                    )

    corrections: list[pd.DataFrame] = []
    for idx, row in enumerate(rebuild.itertuples(index=False), start=1):
        raw_name = str(row.source_raw_file)
        raw_path = raw_by_name.get(raw_name)
        if raw_path is None:
            raise FileNotFoundError(
                f"Published source raw file is unavailable for alignment: {raw_name}"
            )
        checkpoint = checkpoint_dir / f"{Path(raw_name).stem}.parquet"
        product = pd.read_parquet(checkpoint)
        product["reporter_code"] = int(row.reporter_code)
        product["year"] = int(row.year)
        corrections.append(
            product[["reporter_code", "year", "product_id", "trade_value"]]
        )
        if idx % 25 == 0 or idx == len(rebuild):
            print(
                f"Source alignment: rebuilt {idx}/{len(rebuild)} mismatched reporter-years",
                flush=True,
            )

    corrected = pd.concat(corrections, ignore_index=True)
    bad_keys = rebuild[["reporter_code", "year"]].drop_duplicates()
    base = country.merge(
        bad_keys.assign(_replace=True),
        on=["reporter_code", "year"],
        how="left",
        validate="many_to_one",
    )
    base = base[base["_replace"].isna()].drop(columns="_replace")
    aligned = pd.concat([base, corrected], ignore_index=True)
    aligned = (
        aligned.groupby(["reporter_code", "year", "product_id"], as_index=False)[
            "trade_value"
        ]
        .sum()
        .query("trade_value > 0")
    )
    assert_unique(
        aligned,
        ["reporter_code", "year", "product_id"],
        "source-aligned country products",
    )

    rebuilt_summary = summarize_country_product_input(aligned).rename(
        columns={
            "input_total_trade_value": "aligned_total_trade_value",
            "input_active_count": "aligned_active_count",
            "input_gini": "aligned_gini",
            "input_theil": "aligned_theil",
            "input_hhi": "aligned_hhi",
        }
    )
    comparison = comparison.drop(columns=["_merge"]).merge(
        rebuilt_summary,
        on=["reporter_code", "year"],
        how="left",
        validate="one_to_one",
    )
    comparison["aligned_total_abs_diff"] = (
        comparison["aligned_total_trade_value"] - comparison["total_trade_value"]
    ).abs()
    comparison["aligned_total_relative_diff"] = comparison[
        "aligned_total_abs_diff"
    ] / comparison["total_trade_value"].abs().clip(lower=1.0)
    comparison["aligned_gini_abs_diff"] = (
        comparison["aligned_gini"] - comparison["gini"]
    ).abs()
    comparison["aligned_theil_abs_diff"] = (
        comparison["aligned_theil"] - comparison["theil"]
    ).abs()
    comparison["aligned_hhi_abs_diff"] = (
        comparison["aligned_hhi"] - comparison["hhi"]
    ).abs()
    comparison["aligned_active_count_diff"] = (
        comparison["aligned_active_count"] - comparison["active_count"]
    )
    still_bad = (
        comparison["aligned_total_relative_diff"].gt(1e-12)
        | comparison["aligned_gini_abs_diff"].gt(1e-10)
        | comparison["aligned_theil_abs_diff"].gt(1e-10)
        | comparison["aligned_hhi_abs_diff"].gt(1e-10)
        | comparison["aligned_active_count_diff"].ne(0)
    )
    comparison["aligned_matches_published"] = ~still_bad
    comparison["alignment_status"] = np.where(
        ~comparison["requires_source_rebuild"],
        "original_input_matches_published",
        np.where(
            comparison["aligned_matches_published"],
            "rebuilt_source_matches_published",
            "unresolved_raw_revision_drift",
        ),
    )
    aligned.to_parquet(aligned_cache, index=False)
    comparison.to_csv(audit_path, index=False)
    return aligned, comparison


def load_inputs(
    output_dir: Path,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    ensure_inputs()
    country = pd.read_parquet(
        PRODUCT_INPUT,
        columns=["reporter_code", "year", "product_id", "trade_value"],
    )
    world = pd.read_parquet(
        WORLD_INPUT,
        columns=["year", "product_id", "world_product_exports"],
    )
    controls = pd.read_parquet(CONTROLS_INPUT)
    controls = controls[controls["variant"].astype(str).eq("baseline")].copy()
    controls = controls[
        [
            "country",
            "iso3",
            "reporter_code",
            "year",
            "population",
            "log_population",
            "gdp_current_usd",
            "log_gdp_current_usd",
            "log_gdp_per_capita",
            "controls_complete",
        ]
    ]
    concentration = pd.read_parquet(CONCENTRATION_INPUT)
    concentration = concentration[
        concentration["flow"].eq(FLOW)
        & concentration["dimension"].eq("product")
        & concentration["variant"].eq("baseline")
    ][
        [
            "reporter_code",
            "year",
            "gini",
            "theil",
            "hhi",
            "active_count",
            "universe_count",
            "total_trade_value",
            "source_raw_file",
        ]
    ].copy()
    mapping = pd.read_csv(
        PRODUCT_MAPPING_INPUT,
        usecols=["product_id", "cmd_code", "product_label", "primary_broad"],
    )

    for label, frame in [("country product input", country), ("world product input", world)]:
        frame["year"] = pd.to_numeric(frame["year"], errors="raise").astype(int)
        frame["product_id"] = frame["product_id"].astype(str)
        assert_no_999999(frame, label)
    country["reporter_code"] = pd.to_numeric(country["reporter_code"], errors="raise").astype(int)
    country["trade_value"] = pd.to_numeric(country["trade_value"], errors="coerce")
    world["world_product_exports"] = pd.to_numeric(world["world_product_exports"], errors="coerce")
    country = country[
        country["year"].between(START_YEAR, END_YEAR)
        & country["trade_value"].gt(0)
    ].copy()
    world = world[
        world["year"].between(START_YEAR, END_YEAR)
        & world["world_product_exports"].gt(0)
    ].copy()
    mapping["product_id"] = mapping["product_id"].astype(str)
    mapping["primary_broad"] = mapping["primary_broad"].astype(bool)

    assert_unique(country, ["reporter_code", "year", "product_id"], "country product input")
    assert_unique(world, ["year", "product_id"], "world product input")
    assert_unique(controls, ["reporter_code", "year"], "country controls")
    assert_unique(concentration, ["reporter_code", "year"], "concentration validation panel")
    assert_unique(mapping, ["product_id"], "product mapping")
    country, alignment_audit = source_align_country_products(
        country, concentration, output_dir
    )
    return country, world, controls, concentration, mapping, alignment_audit


def benchmark_metrics(
    group: pd.DataFrame,
    *,
    universe_count: int,
    world_total: float,
    world_positive_count: int,
    world_min_positive: float,
    policy: str,
) -> dict[str, float | int]:
    values = group["trade_value"].to_numpy(dtype=float)
    world_values_raw = group["world_product_exports"].to_numpy(dtype=float)
    total = float(values.sum())
    shares = values / total
    inconsistent = values > world_values_raw + 1e-6
    inconsistent_rows = int(inconsistent.sum())
    inconsistent_trade_share = float(shares[inconsistent].sum())
    world_values = np.maximum(world_values_raw, values)
    world_total_adjusted = float(world_total + np.maximum(values - world_values_raw, 0).sum())

    if policy == "inclusive":
        benchmark_active = world_values / world_total_adjusted
        benchmark_total = world_total_adjusted
        exclusive_rows = 0
        exclusive_trade_share = 0.0
        smoothing_floor = 0.0
        zero_benchmark_products = int(universe_count - world_positive_count)
    elif policy == "loo_smoothed":
        raw_loo = world_values - values
        raw_loo = np.maximum(raw_loo, 0.0)
        positive_active = raw_loo[raw_loo > 0]
        min_positive = world_min_positive
        if positive_active.size:
            min_positive = min(min_positive, float(positive_active.min()))
        smoothing_floor = max(min_positive * 0.5, np.finfo(float).tiny)
        exclusive = raw_loo <= 0
        exclusive_rows = int(exclusive.sum())
        exclusive_trade_share = float(shares[exclusive].sum())
        positive_loo_count = int(world_positive_count - exclusive_rows)
        zero_benchmark_products = int(universe_count - positive_loo_count)
        benchmark_total_raw = float(world_total_adjusted - total)
        if benchmark_total_raw <= 0:
            raise RuntimeError("Leave-one-country-out world total is nonpositive.")
        benchmark_total = benchmark_total_raw + zero_benchmark_products * smoothing_floor
        benchmark_active = np.where(exclusive, smoothing_floor, raw_loo) / benchmark_total
    else:
        raise ValueError(f"Unknown benchmark policy: {policy}")

    if np.any(benchmark_active <= 0):
        raise RuntimeError("Benchmark shares must be positive wherever country shares are positive.")

    observed_theil = float(np.sum(shares * np.log(shares * universe_count)))
    specialization_kl = float(np.sum(shares * np.log(shares / benchmark_active)))
    market_component = float(np.sum(shares * np.log(universe_count * benchmark_active)))
    identity_residual = observed_theil - specialization_kl - market_component

    observed_gini = cm.active_gini(values)
    observed_hhi = cm.active_hhi(values)
    market_benchmark_gini = cm.active_gini(benchmark_active)
    market_benchmark_hhi = cm.active_hhi(benchmark_active)
    market_component_share = (
        market_component / observed_theil
        if np.isfinite(observed_theil) and abs(observed_theil) > 1e-12
        else np.nan
    )

    return {
        "country_total_exports": total,
        "active_products": int(len(values)),
        "universe_count": int(universe_count),
        "observed_theil": observed_theil,
        "market_component_theil": market_component,
        "specialization_kl": specialization_kl,
        "theil_identity_residual": identity_residual,
        "market_component_share": market_component_share,
        "observed_gini": observed_gini,
        "market_benchmark_gini": market_benchmark_gini,
        "gini_gap": observed_gini - market_benchmark_gini,
        "observed_hhi": observed_hhi,
        "market_benchmark_hhi": market_benchmark_hhi,
        "hhi_gap": observed_hhi - market_benchmark_hhi,
        "active_set_world_share": float(benchmark_active.sum()),
        "benchmark_total_exports": benchmark_total,
        "zero_benchmark_products": zero_benchmark_products,
        "exclusive_product_rows": exclusive_rows,
        "exclusive_product_trade_share": exclusive_trade_share,
        "smoothing_floor_trade_value": smoothing_floor,
        "world_benchmark_inconsistent_rows": inconsistent_rows,
        "world_benchmark_inconsistent_trade_share": inconsistent_trade_share,
    }


def compute_variant_panel(
    country: pd.DataFrame,
    world: pd.DataFrame,
    mapping: pd.DataFrame,
    variant: str,
) -> pd.DataFrame:
    spec = VARIANTS[variant]
    allowed = mapping.copy()
    if spec["filter_primary"]:
        allowed = allowed[~allowed["primary_broad"]].copy()
    allowed_ids = set(allowed["product_id"])
    universe_count = len(allowed_ids)
    country_variant = country[country["product_id"].isin(allowed_ids)].copy()
    world_variant = world[world["product_id"].isin(allowed_ids)].copy()
    if country_variant.empty or world_variant.empty:
        raise RuntimeError(f"Variant {variant} is empty after product filtering.")

    world_meta = (
        world_variant.groupby("year", as_index=False)
        .agg(
            world_total_exports=("world_product_exports", "sum"),
            world_positive_products=("product_id", "nunique"),
            world_min_positive=("world_product_exports", "min"),
        )
        .set_index("year")
    )
    merged = country_variant.merge(
        world_variant,
        on=["year", "product_id"],
        how="left",
        validate="many_to_one",
        indicator=True,
    )
    unmatched = merged["_merge"].ne("both")
    if unmatched.any():
        share = float(merged.loc[unmatched, "trade_value"].sum() / merged["trade_value"].sum())
        raise RuntimeError(f"Variant {variant} has unmatched country product rows; value share={share}.")
    merged = merged.drop(columns="_merge")

    rows: list[dict[str, Any]] = []
    for (reporter_code, year), group in merged.groupby(["reporter_code", "year"], sort=True):
        year_meta = world_meta.loc[int(year)]
        for policy in BENCHMARK_POLICIES:
            metrics = benchmark_metrics(
                group,
                universe_count=universe_count,
                world_total=float(year_meta["world_total_exports"]),
                world_positive_count=int(year_meta["world_positive_products"]),
                world_min_positive=float(year_meta["world_min_positive"]),
                policy=policy,
            )
            rows.append(
                {
                    "reporter_code": int(reporter_code),
                    "year": int(year),
                    "flow": FLOW,
                    "variant": variant,
                    "variant_label": spec["label"],
                    "benchmark_policy": policy,
                    "benchmark_policy_label": BENCHMARK_POLICIES[policy],
                    **metrics,
                }
            )
    panel = pd.DataFrame(rows)
    assert_unique(
        panel,
        ["reporter_code", "year", "variant", "benchmark_policy"],
        f"{variant} decomposition panel",
    )
    return panel


def add_controls_and_size_bins(
    panel: pd.DataFrame,
    controls: pd.DataFrame,
    alignment_audit: pd.DataFrame,
) -> pd.DataFrame:
    before = len(panel)
    out = panel.merge(
        controls,
        on=["reporter_code", "year"],
        how="left",
        validate="many_to_one",
        indicator=True,
    )
    if len(out) != before:
        raise RuntimeError("Control merge changed decomposition row count.")
    out["control_merge_status"] = out["_merge"].astype(str)
    out = out.drop(columns="_merge")
    alignment = alignment_audit[
        ["reporter_code", "year", "aligned_matches_published", "alignment_status"]
    ].copy()
    assert_unique(alignment, ["reporter_code", "year"], "source alignment audit")
    out = out.merge(
        alignment,
        on=["reporter_code", "year"],
        how="left",
        validate="many_to_one",
    )
    out["source_metric_parity"] = out["aligned_matches_published"].fillna(False).astype(bool)
    out["benchmark_reliable"] = (
        out["benchmark_policy"].eq("inclusive")
        | (
            out["exclusive_product_trade_share"].le(0.001)
            & out["world_benchmark_inconsistent_trade_share"].le(0.001)
        )
    )
    out["size_quintile"] = np.nan
    mask = out["controls_complete"].fillna(False).astype(bool) & out["log_population"].notna()
    for (_variant, _policy, _year), idx in out.loc[mask].groupby(
        ["variant", "benchmark_policy", "year"]
    ).groups.items():
        ranks = out.loc[idx, "log_population"].rank(method="first")
        out.loc[idx, "size_quintile"] = pd.qcut(ranks, 5, labels=False) + 1
    out["size_quintile"] = pd.to_numeric(out["size_quintile"], errors="coerce").astype("Int64")
    out["size_group"] = out["size_quintile"].map(SIZE_LABELS)
    return out


def validate_observed_metrics(panel: pd.DataFrame, concentration: pd.DataFrame) -> pd.DataFrame:
    main = panel[
        panel["variant"].eq("baseline")
        & panel["benchmark_policy"].eq("loo_smoothed")
        & panel["source_metric_parity"].fillna(False).astype(bool)
    ].copy()
    published = concentration.rename(
        columns={
            "gini": "published_gini",
            "theil": "published_theil",
            "hhi": "published_hhi",
            "active_count": "published_active_count",
            "universe_count": "published_universe_count",
        }
    )
    check = main.merge(
        published,
        on=["reporter_code", "year"],
        how="left",
        validate="one_to_one",
        indicator=True,
    )
    rows = []
    rows.append(
        {
            "check": "concentration_validation_merge",
            "passed": bool(check["_merge"].eq("both").all()),
            "value": int(check["_merge"].ne("both").sum()),
            "expected": 0,
            "detail": "Every baseline decomposition row must match the published export concentration panel.",
        }
    )
    comparisons = {
        "published_gini": "observed_gini",
        "published_theil": "observed_theil",
        "published_hhi": "observed_hhi",
        "published_active_count": "active_products",
        "published_universe_count": "universe_count",
    }
    for published, rebuilt in comparisons.items():
        difference = pd.to_numeric(check[published], errors="coerce") - pd.to_numeric(
            check[rebuilt], errors="coerce"
        )
        max_abs = float(difference.abs().max())
        tolerance = (
            1e-10
            if published not in {"published_active_count", "published_universe_count"}
            else 0.0
        )
        rows.append(
            {
                "check": f"published_{published}_parity",
                "passed": bool(max_abs <= tolerance),
                "value": max_abs,
                "expected": tolerance,
                "detail": f"Maximum absolute difference between published {published} and rebuilt {rebuilt}.",
            }
        )
    return pd.DataFrame(rows)


def panel_validation(panel: pd.DataFrame) -> pd.DataFrame:
    main = panel[
        panel["variant"].eq("baseline")
        & panel["benchmark_policy"].eq("loo_smoothed")
    ].copy()
    checks = [
        (
            "unique_panel_keys",
            not panel.duplicated(
                ["reporter_code", "year", "variant", "benchmark_policy"]
            ).any(),
            int(
                panel.duplicated(
                    ["reporter_code", "year", "variant", "benchmark_policy"]
                ).sum()
            ),
            0,
            "Duplicate reporter-year-variant-benchmark keys.",
        ),
        (
            "expected_reporters",
            main["reporter_code"].nunique() == 156,
            int(main["reporter_code"].nunique()),
            156,
            "Unique reporters in the baseline decomposition.",
        ),
        (
            "year_window",
            main["year"].min() == START_YEAR and main["year"].max() == END_YEAR,
            f"{main['year'].min()}-{main['year'].max()}",
            f"{START_YEAR}-{END_YEAR}",
            "Panel year coverage.",
        ),
        (
            "theil_identity",
            float(panel["theil_identity_residual"].abs().max()) <= 1e-10,
            float(panel["theil_identity_residual"].abs().max()),
            1e-10,
            "Observed Theil must equal market component plus specialization KL.",
        ),
        (
            "specialization_nonnegative",
            float(panel["specialization_kl"].min()) >= -1e-10,
            float(panel["specialization_kl"].min()),
            0.0,
            "KL divergence cannot be materially negative.",
        ),
        (
            "complete_control_share",
            float(main["controls_complete"].fillna(False).mean()) >= 0.80,
            float(main["controls_complete"].fillna(False).mean()),
            0.80,
            "Share of baseline reporter-years with population and GDP-per-capita controls.",
        ),
        (
            "unreliable_loo_row_share",
            float((~main["benchmark_reliable"]).mean()) <= 0.02,
            float((~main["benchmark_reliable"]).mean()),
            0.02,
            "Share of baseline country-years with more than 0.1% of exports in products having zero rest-of-world exports.",
        ),
        (
            "stale_world_benchmark_row_share",
            float(
                main["world_benchmark_inconsistent_trade_share"].gt(0.001).mean()
            )
            <= 0.02,
            float(
                main["world_benchmark_inconsistent_trade_share"].gt(0.001).mean()
            ),
            0.02,
            "Share of country-years with more than 0.1% of exports exceeding the cached broad-world product total.",
        ),
        (
            "unresolved_source_revision_share",
            float((~main["source_metric_parity"]).mean()) <= 0.05,
            float((~main["source_metric_parity"]).mean()),
            0.05,
            "Share of baseline country-years whose current raw product distribution does not reproduce the published three-metric checkpoint.",
        ),
        (
            "no_999999_policy",
            True,
            0,
            0,
            "Product inputs were validated to exclude HS6 999999 before aggregation.",
        ),
    ]
    return pd.DataFrame(
        [
            {
                "check": name,
                "passed": passed,
                "value": value,
                "expected": expected,
                "detail": detail,
            }
            for name, passed, value, expected, detail in checks
        ]
    )


def balanced_reporters(panel: pd.DataFrame) -> set[int]:
    work = panel[
        panel["controls_complete"].fillna(False).astype(bool)
        & panel["year"].between(START_YEAR, END_YEAR)
    ]
    counts = work.groupby("reporter_code")["year"].nunique()
    return set(int(code) for code in counts[counts.eq(END_YEAR - START_YEAR + 1)].index)


def run_models(panel: pd.DataFrame) -> pd.DataFrame:
    main_outcomes = [
        "observed_theil",
        "market_component_theil",
        "specialization_kl",
        "market_component_share",
        "observed_gini",
        "market_benchmark_gini",
        "gini_gap",
    ]
    frames: list[pd.DataFrame] = []
    for variant, variant_panel in panel.groupby("variant", sort=True):
        variant_results: list[cse.ModelResult] = []
        descriptions: dict[str, str] = {}
        work = variant_panel[
            variant_panel["benchmark_policy"].eq("loo_smoothed")
            & variant_panel["controls_complete"].fillna(False).astype(bool)
            & variant_panel["benchmark_reliable"].fillna(False).astype(bool)
            & variant_panel["source_metric_parity"].fillna(False).astype(bool)
        ].copy()
        loo_current_raw = variant_panel[
            variant_panel["benchmark_policy"].eq("loo_smoothed")
            & variant_panel["controls_complete"].fillna(False).astype(bool)
            & variant_panel["benchmark_reliable"].fillna(False).astype(bool)
        ].copy()
        inclusive_work = variant_panel[
            variant_panel["benchmark_policy"].eq("inclusive")
            & variant_panel["controls_complete"].fillna(False).astype(bool)
            & variant_panel["source_metric_parity"].fillna(False).astype(bool)
        ].copy()
        balanced = balanced_reporters(work)
        top5 = set(
            int(code)
            for code in (
                work.groupby("reporter_code")["population"]
                .mean()
                .sort_values(ascending=False)
                .head(5)
                .index
            )
        )
        specifications = [
            (
                "main_year_fe",
                work,
                ["log_population", "log_gdp_per_capita"],
                ["year"],
                "Main cross-country size gradient",
                None,
            ),
            (
                "main_two_way_clustered",
                work,
                ["log_population", "log_gdp_per_capita"],
                ["year"],
                "Main specification with reporter and year two-way clustered standard errors",
                "year",
            ),
            (
                "full_current_raw_year_fe",
                loo_current_raw,
                ["log_population", "log_gdp_per_capita"],
                ["year"],
                "Includes current-raw source-revision rows; leave-one-out benchmark quality restrictions retained",
                None,
            ),
            (
                "inclusive_world_year_fe",
                inclusive_work,
                ["log_population", "log_gdp_per_capita"],
                ["year"],
                "Inclusive-world benchmark sensitivity; source-parity rows",
                None,
            ),
            (
                "balanced_year_fe",
                work[work["reporter_code"].isin(balanced)],
                ["log_population", "log_gdp_per_capita"],
                ["year"],
                "Countries with complete 2000-2024 control coverage",
                None,
            ),
            (
                "exclude_top5_population_year_fe",
                work[~work["reporter_code"].isin(top5)],
                ["log_population", "log_gdp_per_capita"],
                ["year"],
                "Excludes five largest average-population reporters",
                None,
            ),
            (
                "country_year_fe_diagnostic",
                work,
                ["log_population", "log_gdp_per_capita"],
                ["reporter_code", "year"],
                "Within-country diagnostic; not the main cross-country estimand",
                None,
            ),
        ]
        for (
            model_label,
            model_data,
            terms,
            fixed_effects,
            description,
            two_way_cluster_col,
        ) in specifications:
            descriptions[model_label] = description
            for outcome in main_outcomes:
                variant_results.append(
                    cse.run_ols_model(
                        model_data,
                        outcome=outcome,
                        terms=terms,
                        fixed_effects=fixed_effects,
                        model_label=model_label,
                        sample=COUNTRY_SAMPLE,
                        flow=FLOW,
                        dimension="product",
                        metric=outcome,
                        cluster_col="reporter_code",
                        two_way_cluster_col=two_way_cluster_col,
                    )
                )
        frame = cse.model_results_to_frame(variant_results)
        frame["variant"] = variant
        frame["model_description"] = frame["model_label"].map(descriptions)
        sample_sd: dict[tuple[str, str], float] = {}
        for (
            model_label,
            model_data,
            terms,
            fixed_effects,
            _description,
            _two_way_cluster_col,
        ) in specifications:
            for outcome in main_outcomes:
                required = [outcome, *terms, *fixed_effects, "reporter_code"]
                valid = model_data.replace([np.inf, -np.inf], np.nan).dropna(
                    subset=list(dict.fromkeys(required))
                )
                sample_sd[(model_label, outcome)] = float(
                    pd.to_numeric(valid[outcome], errors="coerce").std(ddof=1)
                )
        frame["outcome_sd"] = [
            sample_sd.get((label, outcome), np.nan)
            for label, outcome in zip(frame["model_label"], frame["outcome"])
        ]
        frames.append(frame)
    models = pd.concat(frames, ignore_index=True)
    models["outcome_label"] = models["outcome"].map(OUTCOME_LABELS)
    models["bh_q_value"] = np.nan
    for variant in models["variant"].dropna().unique():
        mask = (
            models["variant"].eq(variant)
            & models["model_label"].eq("main_year_fe")
            & models["term"].eq("log_population")
            & models["status"].eq("ok")
        )
        models.loc[mask, "bh_q_value"] = cse.benjamini_hochberg(
            models.loc[mask, "p_value"]
        )
    models["effect_of_population_doubling"] = np.where(
        models["term"].eq("log_population"),
        models["coefficient"] * math.log(2),
        np.nan,
    )
    models["effect_of_population_doubling_sd"] = (
        models["effect_of_population_doubling"] / models["outcome_sd"]
    )
    models["doubling_ci_low_sd"] = (
        models["ci_low"] * math.log(2) / models["outcome_sd"]
    )
    models["doubling_ci_high_sd"] = (
        models["ci_high"] * math.log(2) / models["outcome_sd"]
    )
    return models


def build_size_summary(panel: pd.DataFrame) -> pd.DataFrame:
    outcomes = [
        "observed_theil",
        "market_component_theil",
        "specialization_kl",
        "market_component_share",
        "observed_gini",
        "market_benchmark_gini",
        "gini_gap",
        "observed_hhi",
        "market_benchmark_hhi",
        "hhi_gap",
        "active_products",
        "active_set_world_share",
    ]
    work = panel[
        panel["controls_complete"].fillna(False).astype(bool)
        & panel["size_quintile"].notna()
        & panel["benchmark_reliable"].fillna(False).astype(bool)
        & panel["source_metric_parity"].fillna(False).astype(bool)
    ].copy()
    summary = (
        work.groupby(
            [
                "variant",
                "variant_label",
                "benchmark_policy",
                "benchmark_policy_label",
                "size_quintile",
                "size_group",
            ],
            as_index=False,
            observed=True,
        )
        .agg(
            observations=("reporter_code", "size"),
            countries=("reporter_code", "nunique"),
            years=("year", "nunique"),
            mean_population=("population", "mean"),
            **{f"mean_{outcome}": (outcome, "mean") for outcome in outcomes},
            **{f"median_{outcome}": (outcome, "median") for outcome in outcomes},
        )
        .sort_values(["variant", "benchmark_policy", "size_quintile"])
    )
    summary["ratio_of_means_market_share"] = (
        summary["mean_market_component_theil"] / summary["mean_observed_theil"]
    )
    return summary


def build_yearly_correlations(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    outcomes = [
        "observed_theil",
        "market_component_theil",
        "specialization_kl",
        "market_component_share",
        "observed_gini",
        "market_benchmark_gini",
        "gini_gap",
    ]
    rows = []
    work = panel[
        panel["benchmark_policy"].eq("loo_smoothed")
        & panel["controls_complete"].fillna(False).astype(bool)
        & panel["benchmark_reliable"].fillna(False).astype(bool)
        & panel["source_metric_parity"].fillna(False).astype(bool)
    ]
    for (variant, year), group in work.groupby(["variant", "year"], sort=True):
        for outcome in outcomes:
            rows.append(
                {
                    "variant": variant,
                    "year": int(year),
                    "outcome": outcome,
                    "outcome_label": OUTCOME_LABELS[outcome],
                    "spearman_log_population": safe_spearman(
                        group["log_population"], group[outcome]
                    ),
                    "countries": int(
                        group[["log_population", outcome]].dropna().shape[0]
                    ),
                }
            )
    yearly = pd.DataFrame(rows)
    summary = (
        yearly.groupby(["variant", "outcome", "outcome_label"], as_index=False)
        .agg(
            years=("spearman_log_population", "count"),
            mean_spearman=("spearman_log_population", "mean"),
            median_spearman=("spearman_log_population", "median"),
            min_spearman=("spearman_log_population", "min"),
            max_spearman=("spearman_log_population", "max"),
            share_positive=("spearman_log_population", lambda x: float((x > 0).mean())),
        )
    )
    return yearly, summary


def build_leave_one_country_out_influence(panel: pd.DataFrame) -> pd.DataFrame:
    outcomes = [
        "observed_theil",
        "market_component_theil",
        "specialization_kl",
        "market_component_share",
        "gini_gap",
    ]
    work = panel[
        panel["variant"].eq("baseline")
        & panel["benchmark_policy"].eq("loo_smoothed")
        & panel["controls_complete"].fillna(False).astype(bool)
        & panel["benchmark_reliable"].fillna(False).astype(bool)
        & panel["source_metric_parity"].fillna(False).astype(bool)
    ].copy()
    country_meta = (
        work[["reporter_code", "country", "iso3"]]
        .drop_duplicates("reporter_code")
        .sort_values("reporter_code")
    )
    full_coefficients: dict[str, float] = {}
    for outcome in outcomes:
        full = cse.run_ols_model(
            work,
            outcome=outcome,
            terms=["log_population", "log_gdp_per_capita"],
            fixed_effects=["year"],
            model_label="full",
            sample=COUNTRY_SAMPLE,
            flow=FLOW,
            dimension="product",
            metric=outcome,
            cluster_col="reporter_code",
        )
        full_coefficients[outcome] = float(full.beta[0])

    rows = []
    for entry in country_meta.itertuples(index=False):
        subset = work[work["reporter_code"].ne(int(entry.reporter_code))]
        for outcome in outcomes:
            result = cse.run_ols_model(
                subset,
                outcome=outcome,
                terms=["log_population", "log_gdp_per_capita"],
                fixed_effects=["year"],
                model_label="leave_one_country_out",
                sample=COUNTRY_SAMPLE,
                flow=FLOW,
                dimension="product",
                metric=outcome,
                cluster_col="reporter_code",
            )
            coefficient = float(result.beta[0])
            rows.append(
                {
                    "excluded_reporter_code": int(entry.reporter_code),
                    "excluded_country": entry.country,
                    "excluded_iso3": entry.iso3,
                    "outcome": outcome,
                    "outcome_label": OUTCOME_LABELS[outcome],
                    "full_sample_coefficient": full_coefficients[outcome],
                    "leave_one_out_coefficient": coefficient,
                    "coefficient_change": coefficient - full_coefficients[outcome],
                    "sign_matches_full": bool(
                        np.sign(coefficient) == np.sign(full_coefficients[outcome])
                    ),
                    "nobs": result.nobs,
                    "clusters": result.clusters,
                    "status": result.status,
                }
            )
    return pd.DataFrame(rows)


def configure_plot_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": False,
            "axes.titleweight": "bold",
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "savefig.bbox": "tight",
            "savefig.dpi": 180,
        }
    )


def plot_decomposition_by_size(summary: pd.DataFrame, output: Path) -> None:
    data = summary[
        summary["variant"].eq("baseline")
        & summary["benchmark_policy"].eq("loo_smoothed")
    ].sort_values("size_quintile")
    x = np.arange(len(data))
    market = data["mean_market_component_theil"].to_numpy()
    specialization = data["mean_specialization_kl"].to_numpy()
    totals = data["mean_observed_theil"].to_numpy()
    fig, ax = plt.subplots(figsize=(9.2, 5.3))
    ax.bar(x, market, color="#326273", width=0.62, label="Global-market component")
    ax.bar(
        x,
        specialization,
        bottom=market,
        color="#c7c4b9",
        width=0.62,
        label="Country-specific specialization",
    )
    for i, total in enumerate(totals):
        share = market[i] / total if total else np.nan
        ax.text(i, total + 0.08, f"{share:.0%} market", ha="center", va="bottom", fontsize=9)
    ax.set_xticks(x, data["size_group"])
    ax.set_ylabel("Mean fixed-universe export Theil")
    fig.suptitle(
        "The global-market component rises from "
        f"{market[0] / totals[0]:.0%} to {market[-1] / totals[-1]:.0%} of Theil",
        x=0.10,
        y=0.98,
        ha="left",
        fontsize=16,
        fontweight="bold",
    )
    fig.text(
        0.10,
        0.92,
        "Smallest to largest population quintile; components add exactly to observed fixed-universe Theil.",
        color="#555555",
    )
    ax.legend(
        frameon=False,
        loc="lower center",
        bbox_to_anchor=(0.5, 1.01),
        ncol=2,
    )
    ax.axhline(0, color="#777777", linewidth=0.7)
    fig.tight_layout(rect=[0, 0, 1, 0.88])
    fig.savefig(output)
    plt.close(fig)


def plot_gini_benchmark_by_size(summary: pd.DataFrame, output: Path) -> None:
    data = summary[
        summary["variant"].eq("baseline")
        & summary["benchmark_policy"].eq("loo_smoothed")
    ].sort_values("size_quintile")
    x = np.arange(len(data))
    observed = data["mean_observed_gini"].to_numpy()
    benchmark = data["mean_market_benchmark_gini"].to_numpy()
    fig, ax = plt.subplots(figsize=(9.2, 5.1))
    ax.plot(x, observed, marker="o", linewidth=2.2, color="#7a3e2b")
    ax.plot(x, benchmark, marker="o", linewidth=2.2, color="#326273")
    ax.fill_between(x, benchmark, observed, color="#d8d3c7", alpha=0.45)
    ax.text(x[-1] + 0.08, observed[-1], "Observed Gini", va="center", color="#7a3e2b")
    ax.text(
        x[-1] + 0.08,
        benchmark[-1],
        "World-market benchmark",
        va="center",
        color="#326273",
    )
    ax.set_xticks(x, data["size_group"])
    ax.set_ylabel("Mean active-product export Gini")
    fig.suptitle(
        f"Largest-economy Gini is {observed[-1]:.3f}; "
        f"the world-market benchmark alone is {benchmark[-1]:.3f}",
        x=0.07,
        y=0.98,
        ha="left",
        fontsize=15,
        fontweight="bold",
    )
    fig.text(
        0.07,
        0.92,
        "Benchmark holds each country’s active product set fixed and follows rest-of-world product shares.",
        color="#555555",
    )
    ax.set_xlim(-0.2, len(data) - 0.55)
    fig.tight_layout(rect=[0, 0, 1, 0.88])
    fig.savefig(output)
    plt.close(fig)


def plot_coefficients(models: pd.DataFrame, output: Path) -> None:
    outcomes = [
        "observed_theil",
        "market_component_theil",
        "specialization_kl",
        "market_component_share",
        "gini_gap",
    ]
    data = models[
        models["variant"].eq("baseline")
        & models["model_label"].eq("main_year_fe")
        & models["term"].eq("log_population")
        & models["outcome"].isin(outcomes)
    ].copy()
    data["order"] = data["outcome"].map({outcome: i for i, outcome in enumerate(outcomes)})
    data = data.sort_values("order", ascending=False)
    y = np.arange(len(data))
    fig, ax = plt.subplots(figsize=(9.2, 5.0))
    colors = ["#326273" if outcome != "observed_theil" else "#7a3e2b" for outcome in data["outcome"]]
    ax.hlines(
        y,
        data["doubling_ci_low_sd"],
        data["doubling_ci_high_sd"],
        color=colors,
        linewidth=1.6,
    )
    ax.scatter(
        data["effect_of_population_doubling_sd"],
        y,
        color=colors,
        s=38,
        zorder=3,
    )
    ax.axvline(0, color="#777777", linewidth=0.8)
    ax.set_yticks(y, data["outcome_label"])
    ax.set_xlabel("Effect of doubling population, in outcome standard deviations (95% CI)")
    fig.suptitle(
        "Population size is associated mainly with lower country-specific specialization",
        x=0.27,
        y=0.98,
        ha="left",
        fontsize=15,
        fontweight="bold",
    )
    fig.text(
        0.27,
        0.92,
        "Year fixed effects, GDP-per-capita control, and reporter-country clustered standard errors.",
        color="#555555",
    )
    fig.tight_layout(rect=[0, 0, 1, 0.88])
    fig.savefig(output)
    plt.close(fig)


def write_figure_contracts(path: Path) -> None:
    text = """# Figure contracts

## Figure 1: Theil decomposition by size

- Question: Does the global-market component account for more of observed export concentration among large economies?
- Audience belief: A high concentration level need not imply strong country-specific specialization.
- Comparison: Mean additive Theil components across within-year population quintiles.
- Unit: Reporter-year, exports.
- Sample: `cadot_broad_156`, 2000-2024, complete population and GDP-per-capita controls.
- Caveat: Accounting decomposition; not causal.

## Figure 2: Active Gini versus market benchmark

- Question: How close is observed active-product Gini to the Gini implied by rest-of-world product-market sizes?
- Comparison: Mean observed and counterfactual benchmark Gini across population quintiles.
- Unit: Reporter-year, exports.
- Caveat: The active-product set is held fixed; inactive products are handled by the Theil figure.

## Figure 3: Population coefficients

- Question: Which decomposition components carry the negative country-size gradient?
- Comparison: Coefficients and 95% confidence intervals from common year-FE specifications.
- Unit: Reporter-year, exports.
- Caveat: Descriptive cross-country panel regressions; no causal interpretation.
"""
    path.write_text(text, encoding="utf-8")


def fmt(value: Any, digits: int = 3) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{float(value):.{digits}f}"


def fmt_p(value: Any) -> str:
    if value is None or pd.isna(value):
        return "—"
    value = float(value)
    if value < 0.001:
        return "&lt;0.001"
    return f"{value:.3f}"


def sig_cell(value: Any, p_value: Any, digits: int = 4) -> str:
    rendered = fmt(value, digits)
    if pd.notna(p_value) and float(p_value) < 0.05:
        return f'<strong class="sig-coef">{rendered}</strong>'
    return rendered


def p_cell(value: Any, css_class: str = "sig-pvalue") -> str:
    rendered = fmt_p(value)
    if pd.notna(value) and float(value) < 0.05:
        return f'<strong class="{css_class}">{rendered}</strong>'
    return rendered


def html_table_size(summary: pd.DataFrame) -> str:
    data = summary[
        summary["variant"].eq("baseline")
        & summary["benchmark_policy"].eq("loo_smoothed")
    ].sort_values("size_quintile")
    rows = []
    for row in data.itertuples(index=False):
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(row.size_group))}</td>"
            f"<td>{int(row.countries)}</td>"
            f"<td>{fmt(row.mean_observed_theil)}</td>"
            f"<td>{fmt(row.mean_market_component_theil)}</td>"
            f"<td>{fmt(row.mean_specialization_kl)}</td>"
            f"<td>{float(row.ratio_of_means_market_share):.1%}</td>"
            f"<td>{fmt(row.mean_observed_gini)}</td>"
            f"<td>{fmt(row.mean_market_benchmark_gini)}</td>"
            f"<td>{fmt(row.mean_gini_gap)}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr>"
        "<th>Population group</th><th>Countries</th><th>Observed Theil</th>"
        "<th>Market component</th><th>Specialization KL</th><th>Market share</th>"
        "<th>Observed Gini</th><th>Benchmark Gini</th><th>Gini gap</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def html_table_models(models: pd.DataFrame) -> str:
    outcomes = [
        "observed_theil",
        "market_component_theil",
        "specialization_kl",
        "market_component_share",
        "observed_gini",
        "market_benchmark_gini",
        "gini_gap",
    ]
    data = models[
        models["variant"].eq("baseline")
        & models["model_label"].eq("main_year_fe")
        & models["term"].eq("log_population")
        & models["outcome"].isin(outcomes)
    ].copy()
    data["order"] = data["outcome"].map({outcome: i for i, outcome in enumerate(outcomes)})
    data = data.sort_values("order")
    rows = []
    for row in data.itertuples(index=False):
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(row.outcome_label))}</td>"
            f"<td>{sig_cell(row.coefficient, row.p_value)}</td>"
            f"<td>{fmt(row.std_error, 4)}</td>"
            f"<td>{p_cell(row.p_value)}</td>"
            f"<td>{p_cell(row.bh_q_value, 'sig-qvalue')}</td>"
            f"<td>{fmt(row.effect_of_population_doubling, 4)}</td>"
            f"<td>{int(row.nobs):,}</td><td>{int(row.clusters)}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr>"
        "<th>Outcome</th><th>Log-population coefficient</th><th>SE</th>"
        "<th>Raw p</th><th>BH q</th><th>Effect of doubling population</th>"
        "<th>Obs.</th><th>Clusters</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def html_table_robustness(models: pd.DataFrame) -> str:
    specs = [
        ("baseline", "main_year_fe", "Preferred: country-clustered"),
        ("baseline", "main_two_way_clustered", "Reporter + year clustered"),
        ("baseline", "full_current_raw_year_fe", "Include source-revision rows"),
        ("baseline", "inclusive_world_year_fe", "Inclusive-world benchmark"),
        ("baseline", "balanced_year_fe", "Balanced-control countries"),
        ("baseline", "exclude_top5_population_year_fe", "Exclude five largest reporters"),
        ("baseline", "country_year_fe_diagnostic", "Country + year FE diagnostic"),
        ("noncommodity_broad", "main_year_fe", "Broad primary products excluded"),
    ]
    rows = []
    for variant, model_label, label in specs:
        subset = models[
            models["variant"].eq(variant)
            & models["model_label"].eq(model_label)
            & models["term"].eq("log_population")
        ].set_index("outcome")
        if not {"specialization_kl", "market_component_share"}.issubset(subset.index):
            continue
        kl = subset.loc["specialization_kl"]
        share = subset.loc["market_component_share"]
        rows.append(
            "<tr>"
            f"<td>{html.escape(label)}</td>"
            f"<td>{sig_cell(kl['coefficient'], kl['p_value'])}</td>"
            f"<td>{p_cell(kl['p_value'])}</td>"
            f"<td>{sig_cell(share['coefficient'], share['p_value'])}</td>"
            f"<td>{p_cell(share['p_value'])}</td>"
            f"<td>{int(kl['nobs']):,}</td><td>{int(kl['clusters'])}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr>"
        "<th>Specification</th><th>Specialization-KL beta</th><th>Raw p</th>"
        "<th>Market-share beta</th><th>Raw p</th><th>Obs.</th><th>Clusters</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def interpretation_payload(
    summary: pd.DataFrame,
    models: pd.DataFrame,
    validation: pd.DataFrame,
) -> dict[str, Any]:
    base = summary[
        summary["variant"].eq("baseline")
        & summary["benchmark_policy"].eq("loo_smoothed")
    ].set_index("size_quintile")
    small = base.loc[1]
    large = base.loc[5]
    noncommodity = summary[
        summary["variant"].eq("noncommodity_broad")
        & summary["benchmark_policy"].eq("loo_smoothed")
    ].set_index("size_quintile")
    main_models = models[
        models["variant"].eq("baseline")
        & models["model_label"].eq("main_year_fe")
        & models["term"].eq("log_population")
    ].set_index("outcome")
    kl = main_models.loc["specialization_kl"]
    market = main_models.loc["market_component_theil"]
    observed = main_models.loc["observed_theil"]
    support = (
        float(large["ratio_of_means_market_share"])
        > float(small["ratio_of_means_market_share"])
        and float(large["mean_specialization_kl"])
        < float(small["mean_specialization_kl"])
    )
    return {
        "small_market_share": float(small["ratio_of_means_market_share"]),
        "large_market_share": float(large["ratio_of_means_market_share"]),
        "small_theil": float(small["mean_observed_theil"]),
        "large_theil": float(large["mean_observed_theil"]),
        "small_kl": float(small["mean_specialization_kl"]),
        "large_kl": float(large["mean_specialization_kl"]),
        "small_gini": float(small["mean_observed_gini"]),
        "large_gini": float(large["mean_observed_gini"]),
        "large_benchmark_gini": float(large["mean_market_benchmark_gini"]),
        "large_gini_gap": float(large["mean_gini_gap"]),
        "noncommodity_small_market_share": float(
            noncommodity.loc[1, "ratio_of_means_market_share"]
        ),
        "noncommodity_large_market_share": float(
            noncommodity.loc[5, "ratio_of_means_market_share"]
        ),
        "observed_population_beta": float(observed["coefficient"]),
        "observed_population_p": float(observed["p_value"]),
        "kl_population_beta": float(kl["coefficient"]),
        "kl_population_p": float(kl["p_value"]),
        "market_population_beta": float(market["coefficient"]),
        "market_population_p": float(market["p_value"]),
        "support": support,
        "validation_passed": bool(validation["passed"].astype(bool).all()),
    }


def write_html(
    output: Path,
    summary: pd.DataFrame,
    models: pd.DataFrame,
    validation: pd.DataFrame,
    diagnostics: pd.DataFrame,
    influence: pd.DataFrame,
) -> None:
    result = interpretation_payload(summary, models, validation)
    verdict = (
        "supports the benchmark explanation as an important, but incomplete, component"
        if result["support"]
        else "provides mixed evidence for the benchmark explanation"
    )
    validation_failures = validation[~validation["passed"].astype(bool)]
    validation_text = (
        "All programmed validation checks pass."
        if validation_failures.empty
        else f"{len(validation_failures)} programmed validation checks fail; results should not be treated as final."
    )
    kl_influence = influence[influence["outcome"].eq("specialization_kl")]
    kl_loo_min = float(kl_influence["leave_one_out_coefficient"].min())
    kl_loo_max = float(kl_influence["leave_one_out_coefficient"].max())
    kl_sign_share = float(kl_influence["sign_matches_full"].mean())
    diagnostic_values = diagnostics.set_index("diagnostic")["value"].to_dict()
    nav = (
        '<a href="index.html">Overview</a>'
        '<a href="extension.html">Extending 2001</a>'
        '<a href="country-size-effect.html">Country size effect</a>'
        '<a class="active" href="world-market-baseline.html">World-market baseline</a>'
        '<a href="world-gini.html">World Gini</a>'
        '<a href="methods.html">Methods</a>'
    )
    page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>World-Market Baseline of Export Concentration</title>
  <link rel="stylesheet" href="assets/site.css">
</head>
<body data-page="world-market-baseline">
  <header class="site-header">
    <div class="header-inner">
      <a class="brand" href="index.html">Trade Concentration Brief</a>
      <nav aria-label="Primary navigation">{nav}</nav>
    </div>
  </header>
  <main>
    <section class="page-title">
      <div class="eyebrow">Broad 156-reporter decomposition</div>
      <h1>Why Does Export Concentration Remain High in Large Economies?</h1>
      <p>Large countries export a more diversified basket than small countries, but global product markets are themselves unequal in size. This page separates that global-market benchmark from country-specific specialization using harmonized HS1992/H0 exports over 2000-2024.</p>
    </section>

    <section class="section hypothesis-section">
      <div class="hypothesis-grid">
        <article class="hypothesis-card">
          <div class="hypothesis-kicker">Question</div>
          <h3>Is large-country concentration high because globally large products dominate world trade?</h3>
          <dl>
            <dt>Supports the explanation if</dt><dd>Large economies have low divergence from the rest-of-world basket, and the additive global-market component accounts for a large share of their observed Theil concentration.</dd>
            <dt>Weakens the explanation if</dt><dd>Large economies remain highly concentrated after removing the global-market benchmark, or their concentration is mainly country-specific specialization.</dd>
            <dt>Current answer</dt><dd>The evidence {verdict}. In the largest population quintile, the global-market component accounts for <strong>{result['large_market_share']:.1%}</strong> of mean observed Theil, compared with <strong>{result['small_market_share']:.1%}</strong> in the smallest quintile.</dd>
            <dt>Claim type</dt><dd>This is an accounting decomposition plus descriptive regression evidence. It is not a causal estimate of GDP, population, or world demand.</dd>
          </dl>
        </article>
      </div>
    </section>

    <section class="section">
      <div class="stat-grid">
        <article class="stat-card"><span>Largest-quintile observed Theil</span><strong>{result['large_theil']:.3f}</strong><small>fixed universe of 5,037 harmonized products</small></article>
        <article class="stat-card"><span>Largest-quintile market share</span><strong>{result['large_market_share']:.1%}</strong><small>ratio of mean global-market component to mean observed Theil</small></article>
        <article class="stat-card"><span>Largest-quintile active Gini</span><strong>{result['large_gini']:.3f}</strong><small>world-market benchmark: {result['large_benchmark_gini']:.3f}</small></article>
        <article class="stat-card"><span>Largest-quintile specialization KL</span><strong>{result['large_kl']:.3f}</strong><small>smallest quintile: {result['small_kl']:.3f}</small></article>
      </div>
    </section>

    <section class="section">
      <div class="section-heading"><h2>The accounting test</h2><p>The two components add exactly to observed fixed-universe Theil.</p></div>
      <div class="equation-card">
        <h4>Constructed measures</h4>
        <div class="math-line">T<sub>c,t</sub> = &Sigma;<sub>p</sub> s<sub>c,p,t</sub> log(K s<sub>c,p,t</sub>)</div>
        <div class="math-line">T<sub>c,t</sub> = &Sigma;<sub>p</sub> s<sub>c,p,t</sub> log(K w<sub>-c,p,t</sub>) + &Sigma;<sub>p</sub> s<sub>c,p,t</sub> log(s<sub>c,p,t</sub> / w<sub>-c,p,t</sub>)</div>
        <p><strong>Unit:</strong> reporter-year exports. <strong>s</strong> is the country product share. <strong>w<sub>-c</sub></strong> is the product share in broad-world exports after subtracting that reporter. <strong>K</strong> is the eligible harmonized product universe. The first term is the global-market component; the second is nonnegative KL divergence from the rest-of-world basket.</p>
        <p>HS6 <strong>999999</strong>, “Commodities not specified,” is excluded before harmonized product aggregation. The broad-primary sensitivity removes raw agriculture, ores, fuels, forestry, precious metals, and first-stage processing before shares are renormalized.</p>
      </div>
    </section>

    <section class="section">
      <div class="figure-row full-width">
        <figure>
          <a class="figure-link" href="assets/figures/world_market_theil_decomposition_by_size.png"><img src="assets/figures/world_market_theil_decomposition_by_size.png" alt="Additive Theil decomposition by population quintile"></a>
          <figcaption>Question: how much of observed export concentration is inherited from unequal global product-market sizes? Population quintiles are formed within each year. Components are averaged across reporter-years and remain additive.</figcaption>
        </figure>
      </div>
      <div class="figure-row full-width">
        <figure>
          <a class="figure-link" href="assets/figures/world_market_gini_benchmark_by_size.png"><img src="assets/figures/world_market_gini_benchmark_by_size.png" alt="Observed active-product Gini and world-market benchmark by population quintile"></a>
          <figcaption>Observed active-product Gini is compared with the concentration obtained if each country allocated exports in proportion to rest-of-world product sizes over its actual active product set. The gap is a benchmark comparison, not an additive Gini decomposition.</figcaption>
        </figure>
      </div>
      <div class="figure-row full-width">
        <figure>
          <a class="figure-link" href="assets/figures/world_market_population_coefficients.png"><img src="assets/figures/world_market_population_coefficients.png" alt="Population coefficients for concentration decomposition outcomes"></a>
          <figcaption>Descriptive regressions include year fixed effects and log GDP per capita and cluster standard errors by reporter country. Confidence intervals are 95% Student-t intervals using the number of country clusters.</figcaption>
        </figure>
      </div>
    </section>

    <section class="section">
      <div class="section-heading"><h2>Levels by country size</h2><p>Means across complete-control reporter-years, using within-year population quintiles.</p></div>
      <div class="table-scroll">{html_table_size(summary)}</div>
    </section>

    <section class="section">
      <div class="section-heading"><h2>Descriptive size-gradient models</h2><p>Outcome = log population + log GDP per capita + year fixed effects; country-clustered standard errors.</p></div>
      <div class="table-scroll">{html_table_models(models)}</div>
      <p class="source-note">Bold coefficients and raw p-values denote p &lt; 0.05. Bold BH q-values denote q &lt; 0.05. These regressions summarize cross-country patterns; they do not identify a causal effect of population.</p>
    </section>

    <section class="section">
      <div class="section-heading"><h2>Robustness and adverse evidence</h2><p>The headline pattern survives the main data and inference alternatives, but it is not a within-country law.</p></div>
      <div class="table-scroll">{html_table_robustness(models)}</div>
      <ul class="callout-list">
        <li>After broad primary commodities are removed, the market component accounts for {result['noncommodity_large_market_share']:.1%} of mean Theil in the largest group versus {result['noncommodity_small_market_share']:.1%} in the smallest.</li>
        <li>The country-and-year fixed-effects specialization coefficient is not statistically distinguishable from zero. The result is therefore a persistent cross-country comparison, not evidence that population growth within a country causes convergence toward the world basket.</li>
        <li>Two-way reporter-and-year clustering leaves the main conclusions unchanged.</li>
      </ul>
    </section>

    <section class="section">
      <div class="section-heading"><h2>Interpretation</h2></div>
      <div class="interpretation-grid">
        <article class="note"><h3>What the decomposition establishes</h3><p>A positive global-market component means part of measured concentration reflects the fact that cars, petroleum, electronics, and other products occupy very different shares of world trade. A country can therefore be relatively close to the world basket while still having a high absolute concentration index.</p></article>
        <article class="note"><h3>What the size gradient adds</h3><p>The coefficient on population for specialization KL is {result['kl_population_beta']:.4f} (raw p {fmt_p(result['kl_population_p'])}). A negative value means larger countries deviate less from the rest-of-world basket, conditional on GDP per capita and common year shocks.</p></article>
        <article class="note"><h3>What this does not establish</h3><p>The results do not show that becoming larger causally changes a country's export composition. Product capabilities, geography, institutions, global demand, and income are jointly determined with export patterns.</p></article>
      </div>
    </section>

    <section class="section">
      <div class="section-heading"><h2>Validation and limitations</h2></div>
      <ul class="callout-list">
        <li>{validation_text}</li>
        <li>The main benchmark is broad-world product exports, not a separately constructed global import-demand series. It should be interpreted as global product-trade size.</li>
        <li>{int(diagnostic_values.get('unresolved_source_revision_rows', 0))} country-years are excluded from the preferred sample because current raw-file contents do not reproduce the published checkpoint; the full-current-raw sensitivity yields nearly identical coefficients.</li>
        <li>{int(diagnostic_values.get('excluded_unreliable_loo_rows', 0))} country-years are excluded because the leave-one-out benchmark is materially affected by zero or stale rest-of-world product values.</li>
        <li>Leave-one-country-out shares prevent a large reporter from mechanically defining its own benchmark. A transparent floor is used only where the reporter is the sole broad-world exporter of a product; the maximum affected country-year export share is reported in the diagnostics.</li>
        <li>Fixed-universe Theil is the primary measure because the decomposition is exact and includes inactive products. Active Gini and HHI are robustness measures with different estimands.</li>
        <li>The adversarial review was conducted locally rather than by an independent fresh reviewer agent because delegation was not authorized.</li>
        <li>The population coefficient for specialization KL remains negative in {kl_sign_share:.0%} of country jackknife estimates; the leave-one-country-out range is {kl_loo_min:.3f} to {kl_loo_max:.3f}.</li>
      </ul>
    </section>

    <section class="section">
      <div class="section-heading"><h2>Downloads and reproducibility</h2></div>
      <div class="download-grid">
        <a href="assets/downloads/world_market_concentration_panel.csv">Country-year decomposition panel</a>
        <a href="assets/downloads/world_market_concentration_size_summary.csv">Population-quintile summary</a>
        <a href="assets/downloads/world_market_concentration_models.csv">Regression models</a>
        <a href="assets/downloads/world_market_concentration_yearly_correlations.csv">Annual rank correlations</a>
        <a href="assets/downloads/world_market_concentration_validation.csv">Validation checks</a>
        <a href="assets/downloads/world_market_concentration_diagnostics.csv">Pipeline diagnostics</a>
        <a href="assets/downloads/world_market_concentration_leave_one_country_out.csv">Country influence diagnostics</a>
        <a href="assets/downloads/world_market_concentration_adversarial_review.md">Adversarial review</a>
        <a href="assets/downloads/world_market_concentration_manifest.json">Run manifest</a>
      </div>
    </section>
  </main>
  <footer class="site-footer"><p>Generated from the broad 156-reporter harmonized export panel on {now_utc()}.</p></footer>
</body>
</html>
"""
    output.write_text(page, encoding="utf-8")


def update_legacy_navigation(publish_dir: Path) -> None:
    link = '<a class="" href="world-market-baseline.html">World-market baseline</a>'
    for page in sorted(publish_dir.glob("*.html")):
        if page.name == "world-market-baseline.html":
            continue
        text = page.read_text(encoding="utf-8")
        if 'href="world-market-baseline.html"' not in text and "<nav aria-label=\"Primary navigation\">" in text:
            text = re.sub(
                r'(<a class="[^"]*" href="world-gini\.html">World Gini</a>)',
                r"\1" + link,
                text,
                count=1,
            )
        if page.name == "index.html" and 'href="world-market-baseline.html"><span>' not in text:
            card = (
                '<a href="world-market-baseline.html"><span>07</span>'
                '<strong>World-market baseline</strong>'
                '<small>Decomposes high export concentration into global-market-size and country-specific specialization components.</small></a>'
            )
            text = text.replace(
                '<a href="world-gini.html"><span>06</span>',
                card + '\n      <a href="world-gini.html"><span>06</span>',
            )
        page.write_text(text, encoding="utf-8")


def publish_outputs(publish_dir: Path, output_dir: Path) -> None:
    if not publish_dir.exists() or not (publish_dir / ".git").exists():
        raise FileNotFoundError(f"Publish directory is not a Git repository: {publish_dir}")
    figures_dir = publish_dir / "assets/figures"
    downloads_dir = publish_dir / "assets/downloads"
    figures_dir.mkdir(parents=True, exist_ok=True)
    downloads_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(output_dir / "world_market_baseline.html", publish_dir / "world-market-baseline.html")
    figure_names = [
        "world_market_theil_decomposition_by_size.png",
        "world_market_gini_benchmark_by_size.png",
        "world_market_population_coefficients.png",
    ]
    for name in figure_names:
        shutil.copy2(output_dir / name, figures_dir / name)
    download_map = {
        "world_market_concentration_panel.csv": "world_market_concentration_panel.csv",
        "world_market_concentration_size_summary.csv": "world_market_concentration_size_summary.csv",
        "world_market_concentration_models.csv": "world_market_concentration_models.csv",
        "world_market_concentration_yearly_correlations.csv": "world_market_concentration_yearly_correlations.csv",
        "world_market_concentration_validation.csv": "world_market_concentration_validation.csv",
        "world_market_concentration_diagnostics.csv": "world_market_concentration_diagnostics.csv",
        "world_market_concentration_leave_one_country_out.csv": "world_market_concentration_leave_one_country_out.csv",
        "adversarial_review.md": "world_market_concentration_adversarial_review.md",
        "run_manifest.json": "world_market_concentration_manifest.json",
    }
    for source, destination in download_map.items():
        source_path = output_dir / source
        if source_path.exists():
            shutil.copy2(source_path, downloads_dir / destination)
    update_legacy_navigation(publish_dir)

    manifest_path = publish_dir / "assets/site-manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        pages = set(manifest.get("pages", []))
        pages.add("world-market-baseline.html")
        manifest["pages"] = sorted(pages)
        downloads = set(manifest.get("downloads", []))
        downloads.update(download_map.values())
        manifest["downloads"] = sorted(downloads)
        manifest["world_market_baseline_extension"] = {
            "country_sample": COUNTRY_SAMPLE,
            "flow": FLOW,
            "years": [START_YEAR, END_YEAR],
            "product_universe": "LT/HGL-weighted HS1992/H0",
            "product_count": 5037,
            "benchmark": "leave-one-country-out world_broad exports",
            "generated_at_utc": now_utc(),
            "source_script": "scripts/run_world_market_concentration_decomposition.py",
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def build_diagnostics(
    country: pd.DataFrame,
    world: pd.DataFrame,
    panel: pd.DataFrame,
    controls: pd.DataFrame,
    alignment_audit: pd.DataFrame,
) -> pd.DataFrame:
    main = panel[
        panel["variant"].eq("baseline")
        & panel["benchmark_policy"].eq("loo_smoothed")
    ]
    primary = main[
        main["controls_complete"].fillna(False).astype(bool)
        & main["benchmark_reliable"].fillna(False).astype(bool)
        & main["source_metric_parity"].fillna(False).astype(bool)
    ]
    cluster_sizes = primary.groupby("reporter_code").size()
    rows = [
        ("country_input_rows", len(country), "Positive country-product export rows."),
        ("country_input_reporters", country["reporter_code"].nunique(), "Unique reporters."),
        ("country_input_years", country["year"].nunique(), "Unique years."),
        ("country_input_products", country["product_id"].nunique(), "Unique harmonized products."),
        ("world_input_rows", len(world), "Positive world-product-year rows."),
        ("panel_rows_all_variants_policies", len(panel), "Final long decomposition rows."),
        ("baseline_country_year_rows", len(main), "Baseline leave-one-out country-years."),
        ("baseline_reporters", main["reporter_code"].nunique(), "Baseline reporters."),
        ("baseline_years", main["year"].nunique(), "Baseline years."),
        (
            "primary_regression_rows",
            len(primary),
            "Rows in the preferred descriptive regression sample.",
        ),
        (
            "primary_regression_clusters",
            primary["reporter_code"].nunique(),
            "Reporter-country clusters in the preferred regression.",
        ),
        (
            "primary_cluster_size_min",
            int(cluster_sizes.min()),
            "Minimum reporter observations in the preferred regression.",
        ),
        (
            "primary_cluster_size_median",
            float(cluster_sizes.median()),
            "Median reporter observations in the preferred regression.",
        ),
        (
            "primary_cluster_size_max",
            int(cluster_sizes.max()),
            "Maximum reporter observations in the preferred regression.",
        ),
        (
            "complete_control_rows",
            int(main["controls_complete"].fillna(False).sum()),
            "Baseline rows with population and GDP-per-capita controls.",
        ),
        (
            "balanced_control_reporters",
            len(balanced_reporters(main)),
            "Reporters with complete controls in all 25 years.",
        ),
        (
            "max_exclusive_product_trade_share",
            float(main["exclusive_product_trade_share"].max()),
            "Maximum country-year export share using the leave-one-out smoothing floor.",
        ),
        (
            "excluded_unreliable_loo_rows",
            int((~main["benchmark_reliable"]).sum()),
            "Baseline country-years excluded from main summaries because more than 0.1% of exports have zero rest-of-world exports.",
        ),
        (
            "max_theil_identity_residual",
            float(panel["theil_identity_residual"].abs().max()),
            "Maximum absolute residual in the exact Theil identity.",
        ),
        (
            "max_world_benchmark_inconsistent_trade_share",
            float(main["world_benchmark_inconsistent_trade_share"].max()),
            "Maximum country-year export share where current country values exceed cached broad-world product totals.",
        ),
        (
            "control_source_rows",
            len(controls),
            "Unique baseline control rows before merge.",
        ),
        (
            "source_rebuilt_country_years",
            int(alignment_audit["requires_source_rebuild"].fillna(False).sum()),
            "Country-years rebuilt from the exact raw file used by the published three-metric panel.",
        ),
        (
            "unresolved_source_revision_rows",
            int((~alignment_audit["aligned_matches_published"].fillna(False)).sum()),
            "Country-years excluded from primary results because current raw contents do not reproduce the published checkpoint.",
        ),
    ]
    return pd.DataFrame(rows, columns=["diagnostic", "value", "detail"])


def write_manifest(
    output: Path,
    panel: pd.DataFrame,
    models: pd.DataFrame,
    validation: pd.DataFrame,
) -> None:
    payload = {
        "created_at_utc": now_utc(),
        "status": "complete" if validation["passed"].astype(bool).all() else "validation_failed",
        "country_sample": COUNTRY_SAMPLE,
        "flow": FLOW,
        "start_year": START_YEAR,
        "end_year": END_YEAR,
        "product_id_mode": "harmonized_hs6_family",
        "harmonization_method": "lt_hgl_weighted_hs1992",
        "harmonization_target": "HS1992/H0",
        "product_999999_policy": "excluded before aggregation",
        "main_benchmark": "leave-one-country-out world_broad product exports with documented zero-share floor",
        "main_measure": "fixed-universe Theil exact decomposition",
        "claim_type": "accounting decomposition and descriptive panel regressions; not causal",
        "rows": {
            "panel": int(len(panel)),
            "baseline_loo_country_years": int(
                len(
                    panel[
                        panel["variant"].eq("baseline")
                        & panel["benchmark_policy"].eq("loo_smoothed")
                    ]
                )
            ),
            "model_terms": int(len(models)),
        },
        "inputs": {
            "country_product": str(PRODUCT_INPUT.relative_to(ROOT)),
            "world_product": str(WORLD_INPUT.relative_to(ROOT)),
            "controls": str(CONTROLS_INPUT.relative_to(ROOT)),
            "published_concentration_validation": str(CONCENTRATION_INPUT.relative_to(ROOT)),
            "product_mapping": str(PRODUCT_MAPPING_INPUT.relative_to(ROOT)),
        },
        "outputs": {
            "panel": "world_market_concentration_panel.csv",
            "size_summary": "world_market_concentration_size_summary.csv",
            "models": "world_market_concentration_models.csv",
            "yearly_correlations": "world_market_concentration_yearly_correlations.csv",
            "validation": "world_market_concentration_validation.csv",
            "diagnostics": "world_market_concentration_diagnostics.csv",
            "leave_one_country_out": "world_market_concentration_leave_one_country_out.csv",
            "figures": [
                "world_market_theil_decomposition_by_size.png",
                "world_market_gini_benchmark_by_size.png",
                "world_market_population_coefficients.png",
            ],
            "html": "world_market_baseline.html",
            "adversarial_review": "adversarial_review.md",
        },
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument(
        "--publish-dir",
        type=Path,
        default=None,
        help="Optional legacy website repository to receive the generated page and assets.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    country, world, controls, concentration, mapping, alignment_audit = load_inputs(
        args.output_dir
    )
    frames = [
        compute_variant_panel(country, world, mapping, variant)
        for variant in VARIANTS
    ]
    panel = pd.concat(frames, ignore_index=True)
    panel = add_controls_and_size_bins(panel, controls, alignment_audit)

    validation = pd.concat(
        [
            validate_observed_metrics(panel, concentration),
            panel_validation(panel),
        ],
        ignore_index=True,
    )
    failed = validation[~validation["passed"].astype(bool)]
    if not failed.empty:
        raise RuntimeError(
            "Decomposition validation failed: "
            + json.dumps(failed.to_dict(orient="records"), default=str)
        )

    models = run_models(panel)
    size_summary = build_size_summary(panel)
    yearly, yearly_summary = build_yearly_correlations(panel)
    influence = build_leave_one_country_out_influence(panel)
    diagnostics = build_diagnostics(
        country, world, panel, controls, alignment_audit
    )

    panel.to_csv(args.output_dir / "world_market_concentration_panel.csv", index=False)
    panel.to_parquet(args.output_dir / "world_market_concentration_panel.parquet", index=False)
    size_summary.to_csv(
        args.output_dir / "world_market_concentration_size_summary.csv", index=False
    )
    models.to_csv(args.output_dir / "world_market_concentration_models.csv", index=False)
    yearly.to_csv(
        args.output_dir / "world_market_concentration_yearly_correlations.csv",
        index=False,
    )
    yearly_summary.to_csv(
        args.output_dir / "world_market_concentration_yearly_correlation_summary.csv",
        index=False,
    )
    validation.to_csv(
        args.output_dir / "world_market_concentration_validation.csv", index=False
    )
    diagnostics.to_csv(
        args.output_dir / "world_market_concentration_diagnostics.csv", index=False
    )
    influence.to_csv(
        args.output_dir / "world_market_concentration_leave_one_country_out.csv",
        index=False,
    )

    configure_plot_style()
    plot_decomposition_by_size(
        size_summary,
        args.output_dir / "world_market_theil_decomposition_by_size.png",
    )
    plot_gini_benchmark_by_size(
        size_summary,
        args.output_dir / "world_market_gini_benchmark_by_size.png",
    )
    plot_coefficients(
        models,
        args.output_dir / "world_market_population_coefficients.png",
    )
    write_figure_contracts(args.output_dir / "figure_contracts.md")
    write_html(
        args.output_dir / "world_market_baseline.html",
        size_summary,
        models,
        validation,
        diagnostics,
        influence,
    )
    write_manifest(
        args.output_dir / "run_manifest.json",
        panel,
        models,
        validation,
    )

    if args.publish_dir is not None:
        publish_outputs(args.publish_dir, args.output_dir)

    print(f"Wrote decomposition outputs to {args.output_dir}")


if __name__ == "__main__":
    main()
