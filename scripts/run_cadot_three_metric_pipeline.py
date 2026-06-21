#!/usr/bin/env python3
"""Build Gini/Theil/HHI panels and exercise summaries.

This runner intentionally computes the three headline concentration metrics
from the same streamed HS6 reporter-year-flow inputs. It does not materialize
the full HS6-product-partner leaf panel. Instead it writes compact per-file
checkpoints and then finalizes website-facing CSV/Parquet artifacts.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import trade_concentration_pipeline as tcp  # noqa: E402
from concentration_metrics import (  # noqa: E402
    active_gini,
    active_hhi,
    active_loo_gini_contributions,
    active_loo_hhi_contributions,
    active_theil,
    active_top_share,
)


COUNTRY_SAMPLE = tcp.RD2_SAMPLE
BENCHMARK_SAMPLE = tcp.WORLD_BROAD_SAMPLE
START_YEAR = 1988
END_YEAR: int | None = None
EXPECTED_REPORTERS = len(tcp.RD2_COUNTRIES)
PRODUCT_ID_MODE = "harmonized_hs6_family"
HARMONIZATION_METHOD = "lt_hgl_weighted_hs1992"
FLOW_ORDER = ("Exports", "Imports")
DIMENSION_ORDER = ("product", "partner", "product_partner_cell")
EXERCISES = ("1", "2", "3", "4", "6", "10", "11", "12")
TABLE_DIRNAME = "three_metric_tables"
CHECKPOINT_DIRNAME = "three_metric_harmonized_hs1992_checkpoints"
CADOT_CHECKPOINT_KINDS = [
    "metric_rows",
    "product_universe",
    "exercise_03",
    "exercise_04",
    "exercise_06",
    "exercise_10",
    "exercise_11",
]
WORLD_CHECKPOINT_KINDS = ["world_product_universe"]
TOP_SHARE_SPECS = {
    "top_1pct_share": ("pct", 0.01),
    "top_2pct_share": ("pct", 0.02),
    "top_5pct_share": ("pct", 0.05),
    "top_10pct_share": ("pct", 0.10),
    "top_200_share": ("n", 200),
}
EXCLUDED_VARIANTS = tcp.EXCLUSION_SETS


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if math.isnan(float(value)) else float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=json_default), encoding="utf-8")


def require_columns(df: pd.DataFrame, name: str, columns: set[str]) -> None:
    missing = sorted(columns.difference(df.columns))
    if missing:
        raise RuntimeError(f"{name} missing required columns: {', '.join(missing)}")


def normalize_source_metadata_columns(frame: pd.DataFrame) -> pd.DataFrame:
    if "classification_code" not in frame.columns:
        return frame
    out = frame.copy()
    if "source_classification_code" not in out.columns:
        out = out.rename(columns={"classification_code": "source_classification_code"})
    else:
        out["source_classification_code"] = out["source_classification_code"].fillna(out["classification_code"])
        out = out.drop(columns=["classification_code"])
    return out


def sample_dir() -> Path:
    return tcp.sample_processed_dir(COUNTRY_SAMPLE)


def result_dir() -> Path:
    return tcp.sample_results_dir(COUNTRY_SAMPLE) / TABLE_DIRNAME


def checkpoint_root() -> Path:
    return sample_dir() / "checkpoints" / CHECKPOINT_DIRNAME


def checkpoint_path(kind: str, raw_path: Path) -> Path:
    return checkpoint_root() / kind / tcp.checkpoint_name_for_raw(raw_path)


def world_fixed_universe_cache_path() -> Path:
    return result_dir() / "world_broad_harmonized_hs1992_product_universe.csv"


def expected_reporters_for_sample(country_sample: str) -> int:
    if country_sample == tcp.RD2_SAMPLE:
        return len(tcp.RD2_COUNTRIES)
    if country_sample == tcp.CADOT_BROAD_SAMPLE:
        return tcp.CADOT_BROAD_EXPECTED_REPORTERS
    raise ValueError(f"Unsupported three-metric country sample: {country_sample}")


def configure_metric_sample(country_sample: str) -> None:
    global COUNTRY_SAMPLE
    global START_YEAR
    global END_YEAR
    global EXPECTED_REPORTERS
    if country_sample not in {tcp.RD2_SAMPLE, tcp.CADOT_BROAD_SAMPLE}:
        raise ValueError(
            f"Unsupported three-metric country sample `{country_sample}`. "
            f"Use `{tcp.RD2_SAMPLE}` for website output or `{tcp.CADOT_BROAD_SAMPLE}` for research sensitivity."
        )
    settings = tcp.configure_country_sample(country_sample=country_sample)
    COUNTRY_SAMPLE = settings.name
    START_YEAR = settings.start_year
    END_YEAR = settings.end_year
    EXPECTED_REPORTERS = expected_reporters_for_sample(settings.name)


def configure_sample() -> pd.DataFrame:
    tcp.configure_country_sample(country_sample=COUNTRY_SAMPLE)
    panel = tcp.save_country_panel()
    if len(panel) != EXPECTED_REPORTERS:
        raise RuntimeError(f"{COUNTRY_SAMPLE} must contain {EXPECTED_REPORTERS} reporters; found {len(panel)}.")
    if panel["reporter_code"].duplicated().any():
        raise RuntimeError(f"{COUNTRY_SAMPLE} has duplicate reporter_code values.")
    if panel["iso3"].duplicated().any():
        raise RuntimeError(f"{COUNTRY_SAMPLE} has duplicate ISO3 values.")
    return panel


def configure_world_broad_sample() -> pd.DataFrame:
    tcp.configure_country_sample(country_sample=BENCHMARK_SAMPLE, start_year=START_YEAR, end_year=END_YEAR)
    return tcp.save_country_panel()


def prepare_dirs(fresh: bool = False) -> None:
    if fresh:
        for name in CADOT_CHECKPOINT_KINDS:
            path = checkpoint_root() / name
            if path.exists():
                shutil.rmtree(path)
    for name in [*CADOT_CHECKPOINT_KINDS, *WORLD_CHECKPOINT_KINDS]:
        (checkpoint_root() / name).mkdir(parents=True, exist_ok=True)
    result_dir().mkdir(parents=True, exist_ok=True)


def active_values(values: pd.Series | np.ndarray | list[float]) -> np.ndarray:
    arr = np.asarray(values, dtype=float).reshape(-1)
    return arr[np.isfinite(arr) & (arr > 0)]


def metric_summary(values: pd.Series | np.ndarray | list[float]) -> dict[str, float | int]:
    vals = active_values(values)
    total = float(vals.sum()) if vals.size else 0.0
    out: dict[str, float | int] = {
        "total_trade_value": total,
        "active_count": int(vals.size),
        "gini": active_gini(vals),
        "theil_active": active_theil(vals),
        "hhi": active_hhi(vals),
    }
    for name, (kind, value) in TOP_SHARE_SPECS.items():
        out[name] = active_top_share(vals, pct=float(value)) if kind == "pct" else active_top_share(vals, n=int(value))
    return out


def base_meta(meta: dict[str, Any], flow: str, dimension: str, variant: str = "baseline") -> dict[str, Any]:
    return {
        "country": meta["country"],
        "iso3": meta["iso3"],
        "reporter_code": int(meta["reporter_code"]),
        "year": int(meta["year"]),
        "flow": flow,
        "dimension": dimension,
        "variant": variant,
        "available_metric_row": True,
        "sample_rule": COUNTRY_SAMPLE,
    }


def add_group_sum(
    combined: pd.DataFrame | None,
    frame: pd.DataFrame,
    group_cols: list[str],
    *,
    exclude_hs6: bool = False,
) -> pd.DataFrame | None:
    if frame.empty:
        return combined
    out = frame[[*group_cols, "trade_value"]].copy()
    if exclude_hs6:
        out = tcp.drop_excluded_hs6(out)
    if out.empty:
        return combined
    out["trade_value"] = pd.to_numeric(out["trade_value"], errors="coerce")
    out = out.dropna(subset=["trade_value"])
    out = out[out["trade_value"] > 0].copy()
    if out.empty:
        return combined
    out = out.groupby(group_cols, as_index=False)["trade_value"].sum()
    combined = out if combined is None else pd.concat([combined, out], ignore_index=True)
    if len(combined) > 500_000:
        combined = combined.groupby(group_cols, as_index=False)["trade_value"].sum()
        gc.collect()
    return combined


def finish_group_sum(combined: pd.DataFrame | None, group_cols: list[str]) -> pd.DataFrame:
    if combined is None or combined.empty:
        return pd.DataFrame(columns=[*group_cols, "trade_value"])
    return combined.groupby(group_cols, as_index=False)["trade_value"].sum()


def normalize_leaf_for_metric(leaf: pd.DataFrame) -> pd.DataFrame:
    out = leaf.copy()
    out["cmd_code"] = tcp.hs6_code_series(out["cmd_code"])
    out["hs2"] = out["cmd_code"].str[:2]
    out["classification_code"] = out["classification_code"].map(tcp.normalize_hs_classification_code)
    return out


def harmonize_product_leaf(product_leaf: pd.DataFrame, weights: pd.DataFrame) -> pd.DataFrame:
    if product_leaf.empty:
        return product_leaf.copy()
    converted = tcp.apply_lt_hgl_hs1992_conversion(product_leaf, weights=weights)
    if converted.empty:
        return converted
    converted["cmd_code"] = tcp.hs6_code_series(converted["cmd_code"])
    converted["product_id"] = converted["product_id"].fillna("HS1992:" + converted["cmd_code"].astype(str))
    converted["hs2"] = converted["cmd_code"].str[:2]
    converted["classification_code"] = tcp.LT_HGL_TARGET_REVISION
    return converted


def load_bec_mapping_or_empty() -> pd.DataFrame:
    try:
        mapping = tcp.load_approved_bec5_mapping()
    except Exception as exc:
        print(f"WARNING: Exercise 3 BEC mapping unavailable; Exercise 3 rows will be marked missing: {exc}", flush=True)
        return pd.DataFrame()
    cols = ["classification_code", "cmd_code", "exercise_03_bin", "mapping_status"]
    for col in cols:
        if col not in mapping.columns:
            mapping[col] = ""
    mapping = mapping[cols].copy()
    mapping["classification_code"] = mapping["classification_code"].map(tcp.normalize_hs_classification_code)
    mapping["cmd_code"] = tcp.hs6_code_series(mapping["cmd_code"])
    mapping["exercise_03_bin"] = mapping["exercise_03_bin"].replace("", "unmapped_or_ambiguous")
    mapping["mapping_status"] = mapping["mapping_status"].replace("", "unmapped")
    return mapping.drop_duplicates(["classification_code", "cmd_code"])


def aggregate_raw_file(raw_path: Path, bec_mapping: pd.DataFrame, chunk_rows: int, weights: pd.DataFrame) -> dict[str, pd.DataFrame]:
    product: pd.DataFrame | None = None
    partner: pd.DataFrame | None = None
    cell: pd.DataFrame | None = None
    product_hs2: pd.DataFrame | None = None
    partner_hs2: pd.DataFrame | None = None
    cell_hs2: pd.DataFrame | None = None
    ex03: pd.DataFrame | None = None
    ex04_supplier: pd.DataFrame | None = None

    for leaf in tcp.iter_leaf_trade_chunks(raw_path, chunk_rows=chunk_rows):
        leaf = normalize_leaf_for_metric(leaf)
        product_source = tcp.drop_excluded_hs6(leaf)
        product_leaf = harmonize_product_leaf(product_source, weights)

        product = add_group_sum(product, product_leaf, ["flow", "cmd_code"], exclude_hs6=True)
        product_hs2 = add_group_sum(product_hs2, product_leaf, ["flow", "hs2", "cmd_code"], exclude_hs6=True)
        partner = add_group_sum(partner, leaf, ["flow", "partner_code"], exclude_hs6=False)
        cell = add_group_sum(cell, product_leaf, ["flow", "cmd_code", "partner_code"], exclude_hs6=True)
        partner_hs2 = add_group_sum(partner_hs2, product_leaf, ["flow", "hs2", "partner_code"], exclude_hs6=True)
        cell_hs2 = add_group_sum(cell_hs2, product_leaf, ["flow", "hs2", "cmd_code", "partner_code"], exclude_hs6=True)

        source_imports = product_source[product_source["flow"].eq("Imports")].copy()
        if not source_imports.empty and not bec_mapping.empty:
            mapped = source_imports.merge(bec_mapping, on=["classification_code", "cmd_code"], how="left")
            mapped["exercise_03_bin"] = mapped["exercise_03_bin"].fillna("unmapped_or_ambiguous").replace("", "unmapped_or_ambiguous")
            mapped["mapping_status"] = mapped["mapping_status"].fillna("unmapped").replace("", "unmapped")
            mapped = harmonize_product_leaf(mapped, weights)
            ex03 = add_group_sum(ex03, mapped, ["exercise_03_bin", "mapping_status", "cmd_code"], exclude_hs6=True)
        elif not source_imports.empty:
            mapped = source_imports.assign(exercise_03_bin="mapping_unavailable", mapping_status="mapping_unavailable")
            mapped = harmonize_product_leaf(mapped, weights)
            ex03 = add_group_sum(ex03, mapped, ["exercise_03_bin", "mapping_status", "cmd_code"], exclude_hs6=True)

        imports = product_leaf[product_leaf["flow"].eq("Imports")].copy()
        if not imports.empty:
            ex04_supplier = add_group_sum(ex04_supplier, imports, ["cmd_code", "partner_code"], exclude_hs6=True)

        del leaf

    return {
        "product": finish_group_sum(product, ["flow", "cmd_code"]),
        "product_hs2": finish_group_sum(product_hs2, ["flow", "hs2", "cmd_code"]),
        "partner": finish_group_sum(partner, ["flow", "partner_code"]),
        "cell": finish_group_sum(cell, ["flow", "cmd_code", "partner_code"]),
        "partner_hs2": finish_group_sum(partner_hs2, ["flow", "hs2", "partner_code"]),
        "cell_hs2": finish_group_sum(cell_hs2, ["flow", "hs2", "cmd_code", "partner_code"]),
        "exercise_03": finish_group_sum(ex03, ["exercise_03_bin", "mapping_status", "cmd_code"]),
        "exercise_04_supplier": finish_group_sum(ex04_supplier, ["cmd_code", "partner_code"]),
    }


def compute_metric_rows(aggregates: dict[str, pd.DataFrame], meta: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    specs = [
        ("product", "cmd_code", aggregates["product"]),
        ("partner", "partner_code", aggregates["partner"]),
        ("product_partner_cell", ["cmd_code", "partner_code"], aggregates["cell"]),
    ]
    for dimension, item_cols, frame in specs:
        if frame.empty:
            continue
        item_cols_list = [item_cols] if isinstance(item_cols, str) else item_cols
        for flow, group in frame.groupby("flow", sort=True):
            values = group.groupby(item_cols_list, as_index=False)["trade_value"].sum()["trade_value"]
            rows.append({**base_meta(meta, flow, dimension), **metric_summary(values)})
    return pd.DataFrame(rows)


def filtered_values(frame: pd.DataFrame, flow: str, excluded_hs2: set[str], item_cols: list[str]) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=float)
    sub = frame[frame["flow"].eq(flow)].copy()
    if excluded_hs2:
        sub = sub[~sub["hs2"].isin(excluded_hs2)].copy()
    if sub.empty:
        return pd.Series(dtype=float)
    return sub.groupby(item_cols, as_index=False)["trade_value"].sum()["trade_value"]


def compute_exercise_06_rows(aggregates: dict[str, pd.DataFrame], meta: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    product_hs2 = aggregates["product_hs2"]
    partner_hs2 = aggregates["partner_hs2"]
    cell_hs2 = aggregates["cell_hs2"]
    baseline_totals: dict[tuple[str, str], float] = {}
    for flow, group in product_hs2.groupby("flow", sort=True) if not product_hs2.empty else []:
        baseline_totals[(flow, "product")] = float(group["trade_value"].sum())
    for variant, excluded in EXCLUDED_VARIANTS.items():
        excluded_set = set(excluded)
        for flow in FLOW_ORDER:
            dimension_values = {
                "product": filtered_values(product_hs2, flow, excluded_set, ["cmd_code"]),
                "partner": filtered_values(partner_hs2, flow, excluded_set, ["partner_code"]),
                "product_partner_cell": filtered_values(cell_hs2, flow, excluded_set, ["cmd_code", "partner_code"]),
            }
            for dimension, values in dimension_values.items():
                if values.empty:
                    continue
                row = {**base_meta(meta, flow, dimension, variant=variant), **metric_summary(values)}
                baseline = baseline_totals.get((flow, "product"), np.nan)
                row["excluded_hs2"] = ",".join(sorted(excluded_set))
                row["baseline_total_trade_value"] = baseline
                row["trade_share_removed"] = 1 - (float(row["total_trade_value"]) / baseline) if baseline and baseline > 0 else np.nan
                rows.append(row)
    return pd.DataFrame(rows)


def compute_exercise_03_rows(ex03: pd.DataFrame, meta: dict[str, Any]) -> pd.DataFrame:
    if ex03.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    total = float(ex03["trade_value"].sum())
    for (import_bin, mapping_status), group in ex03.groupby(["exercise_03_bin", "mapping_status"], sort=True):
        product_values = group.groupby("cmd_code", as_index=False)["trade_value"].sum()["trade_value"]
        row = {
            "country": meta["country"],
            "iso3": meta["iso3"],
            "reporter_code": int(meta["reporter_code"]),
            "year": int(meta["year"]),
            "flow": "Imports",
            "import_bin": import_bin,
            "mapping_status": mapping_status,
            "total_imports": total,
            **metric_summary(product_values),
        }
        row["import_value_share"] = float(row["total_trade_value"]) / total if total > 0 else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    val = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
    wt = pd.to_numeric(weights, errors="coerce").to_numpy(dtype=float)
    mask = np.isfinite(val) & np.isfinite(wt) & (wt > 0)
    return float(np.average(val[mask], weights=wt[mask])) if mask.any() else np.nan


def compute_exercise_04_rows(supplier: pd.DataFrame, meta: dict[str, Any]) -> pd.DataFrame:
    if supplier.empty:
        return pd.DataFrame()
    totals = supplier.groupby("cmd_code", as_index=False)["trade_value"].sum().rename(columns={"trade_value": "product_imports"})
    shares = supplier.merge(totals, on="cmd_code", how="left")
    shares["supplier_share"] = shares["trade_value"] / shares["product_imports"].replace(0, np.nan)
    by_product = shares.groupby("cmd_code", as_index=False).agg(
        product_imports=("product_imports", "first"),
        top_supplier_share=("supplier_share", "max"),
        source_hhi=("supplier_share", lambda s: float(np.square(s.to_numpy(dtype=float)).sum())),
        supplier_count=("partner_code", "nunique"),
    )
    total_imports = float(by_product["product_imports"].sum())
    row = {
        "country": meta["country"],
        "iso3": meta["iso3"],
        "reporter_code": int(meta["reporter_code"]),
        "year": int(meta["year"]),
        "flow": "Imports",
        "total_imports": total_imports,
        "import_products": int(len(by_product)),
        "weighted_mean_top_supplier_share": weighted_mean(by_product["top_supplier_share"], by_product["product_imports"]),
        "weighted_mean_source_hhi": weighted_mean(by_product["source_hhi"], by_product["product_imports"]),
        "median_top_supplier_share": float(by_product["top_supplier_share"].median()) if not by_product.empty else np.nan,
        "median_source_hhi": float(by_product["source_hhi"].median()) if not by_product.empty else np.nan,
        "share_products_top_supplier_ge_50": float((by_product["top_supplier_share"] >= 0.50).mean()) if not by_product.empty else np.nan,
        "share_products_top_supplier_ge_75": float((by_product["top_supplier_share"] >= 0.75).mean()) if not by_product.empty else np.nan,
        "share_products_top_supplier_ge_90": float((by_product["top_supplier_share"] >= 0.90).mean()) if not by_product.empty else np.nan,
    }
    for threshold in (50, 75, 90):
        mask = by_product["top_supplier_share"] >= threshold / 100
        row[f"import_value_share_products_top_supplier_ge_{threshold}"] = (
            float(by_product.loc[mask, "product_imports"].sum() / total_imports) if total_imports > 0 else np.nan
        )
    return pd.DataFrame([row])


def share_matrix_metrics(shares: np.ndarray) -> dict[str, np.ndarray]:
    if shares.ndim != 2 or shares.shape[1] == 0:
        empty = np.full(shares.shape[0] if shares.ndim == 2 else 0, np.nan)
        return {"gini": empty, "theil_active": empty.copy(), "hhi": empty.copy()}
    sims, n = shares.shape
    sorted_shares = np.sort(shares, axis=1)
    ranks = np.arange(1, n + 1, dtype=float)
    gini = (2.0 * sorted_shares.dot(ranks) / n) - ((n + 1) / n)
    positive = shares > 0
    theil = np.zeros(sims, dtype=float)
    theil[positive.any(axis=1)] = np.sum(np.where(positive, shares * np.log(np.where(positive, shares * n, 1.0)), 0.0), axis=1)
    hhi = np.sum(shares * shares, axis=1)
    return {"gini": gini, "theil_active": theil, "hhi": hhi}


def simulate_active_count(active_items: int, simulations: int, rng: np.random.Generator) -> dict[str, np.ndarray]:
    if active_items <= 0:
        empty = np.full(simulations, np.nan)
        return {"gini": empty, "theil_active": empty.copy(), "hhi": empty.copy()}
    if active_items == 1:
        return {
            "gini": np.zeros(simulations),
            "theil_active": np.zeros(simulations),
            "hhi": np.ones(simulations),
        }
    draws = rng.exponential(scale=1.0, size=(simulations, active_items))
    shares = draws / draws.sum(axis=1, keepdims=True)
    return share_matrix_metrics(shares)


def simulate_hs2_preserved(products: pd.DataFrame, simulations: int, rng: np.random.Generator) -> dict[str, np.ndarray]:
    sector = products.groupby("hs2", as_index=False).agg(
        hs2_total=("trade_value", "sum"),
        active_products=("cmd_code", "nunique"),
    )
    total = float(sector["hs2_total"].sum())
    active_items = int(sector["active_products"].sum())
    if active_items <= 0 or total <= 0:
        empty = np.full(simulations, np.nan)
        return {"gini": empty, "theil_active": empty.copy(), "hhi": empty.copy()}
    simulated = np.empty((simulations, active_items), dtype=np.float64)
    col = 0
    for row in sector.itertuples(index=False):
        k = int(row.active_products)
        hs2_share = float(row.hs2_total) / total
        if k == 1:
            simulated[:, col] = hs2_share
            col += 1
            continue
        draws = rng.exponential(scale=1.0, size=(simulations, k))
        draws /= draws.sum(axis=1, keepdims=True)
        simulated[:, col : col + k] = draws * hs2_share
        col += k
    return share_matrix_metrics(simulated)


def summarize_sim(actual: dict[str, float], sim: dict[str, np.ndarray], prefix: str = "") -> dict[str, float]:
    out: dict[str, float] = {}
    for metric in ("gini", "theil_active", "hhi"):
        values = sim[metric]
        actual_value = float(actual[metric])
        out[f"{prefix}actual_{metric}"] = actual_value
        out[f"{prefix}sim_{metric}_median"] = float(np.nanmedian(values))
        out[f"{prefix}sim_{metric}_p05"] = float(np.nanpercentile(values, 5))
        out[f"{prefix}sim_{metric}_p95"] = float(np.nanpercentile(values, 95))
        out[f"{prefix}actual_{metric}_percentile"] = float(np.nanmean(values <= actual_value))
        out[f"{prefix}actual_minus_sim_median_{metric}"] = actual_value - out[f"{prefix}sim_{metric}_median"]
    return out


def compute_exercise_10_rows(
    product_hs2: pd.DataFrame,
    meta: dict[str, Any],
    simulations: int,
    rng: np.random.Generator,
) -> pd.DataFrame:
    if product_hs2.empty or simulations <= 0:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for flow, group in product_hs2.groupby("flow", sort=True):
        products = group.groupby(["hs2", "cmd_code"], as_index=False)["trade_value"].sum()
        values = products.groupby("cmd_code", as_index=False)["trade_value"].sum()["trade_value"]
        actual_summary = metric_summary(values)
        actual = {
            "gini": float(actual_summary["gini"]),
            "theil_active": float(actual_summary["theil_active"]),
            "hhi": float(actual_summary["hhi"]),
        }
        base = {
            "country": meta["country"],
            "iso3": meta["iso3"],
            "reporter_code": int(meta["reporter_code"]),
            "year": int(meta["year"]),
            "flow": flow,
            "simulations": int(simulations),
            "total_trade_value": float(actual_summary["total_trade_value"]),
            "active_items": int(actual_summary["active_count"]),
            "active_hs2_count": int(products["hs2"].nunique()),
        }
        hs2_sim = simulate_hs2_preserved(products, simulations, rng)
        rows.append(
            {
                **base,
                "benchmark_null": "hs2_preserving_within_sector_random_allocation",
                **summarize_sim(actual, hs2_sim),
            }
        )
        active_sim = simulate_active_count(int(actual_summary["active_count"]), simulations, rng)
        rows.append(
            {
                **base,
                "benchmark_null": "active_count_random_allocation",
                **summarize_sim(actual, active_sim),
            }
        )
    return pd.DataFrame(rows)


def active_loo_theil_contributions(values: pd.Series | np.ndarray | list[float]) -> tuple[np.ndarray, np.ndarray]:
    raw = np.asarray(values, dtype=float).reshape(-1)
    active = np.isfinite(raw) & (raw > 0)
    active_positions = np.flatnonzero(active)
    active_values = raw[active]
    out_active = np.full(raw.size, np.nan, dtype=float)
    out_fixed = np.full(raw.size, np.nan, dtype=float)
    n = active_values.size
    if n <= 1:
        return out_active, out_fixed
    total = float(active_values.sum())
    if total <= 0:
        return out_active, out_fixed
    value_log_value = active_values * np.log(active_values)
    sum_value_log_value = float(value_log_value.sum())
    active_full = (sum_value_log_value / total) - math.log(total) + math.log(n)
    total_without = total - active_values
    valid = total_without > 0
    without = np.full(n, np.nan, dtype=float)
    without[valid] = (
        ((sum_value_log_value - value_log_value)[valid] / total_without[valid])
        - np.log(total_without[valid])
        + math.log(n - 1)
    )
    active_contribution = active_full - without
    fixed_contribution = active_contribution + math.log((n - 1) / n)
    out_active[active_positions] = active_contribution
    out_fixed[active_positions] = fixed_contribution
    return out_active, out_fixed


def compute_exercise_11_rows(product: pd.DataFrame, meta: dict[str, Any], top_n: int) -> pd.DataFrame:
    if product.empty or top_n <= 0:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for flow, group in product.groupby("flow", sort=True):
        products = group.groupby("cmd_code", as_index=False)["trade_value"].sum().sort_values("cmd_code").reset_index(drop=True)
        values = products["trade_value"].to_numpy(dtype=float)
        if len(values) <= 1:
            continue
        theil_active_loo, theil_fixed_loo = active_loo_theil_contributions(values)
        contributions = {
            "gini": active_loo_gini_contributions(values),
            "theil_active": theil_active_loo,
            "theil_fixed_universe": theil_fixed_loo,
            "hhi": active_loo_hhi_contributions(values),
        }
        for metric, contribution in contributions.items():
            tmp = products[["cmd_code", "trade_value"]].copy()
            tmp["contribution"] = contribution
            tmp = tmp[np.isfinite(tmp["contribution"])].copy()
            if tmp.empty:
                continue
            tmp["abs_contribution"] = tmp["contribution"].abs()
            tmp = tmp.sort_values(["abs_contribution", "trade_value", "cmd_code"], ascending=[False, False, True]).head(top_n)
            for rank, row in enumerate(tmp.itertuples(index=False), start=1):
                rows.append(
                    {
                        "country": meta["country"],
                        "iso3": meta["iso3"],
                        "reporter_code": int(meta["reporter_code"]),
                        "year": int(meta["year"]),
                        "flow": flow,
                        "metric": metric,
                        "rank_abs_contribution": rank,
                        "cmd_code": row.cmd_code,
                        "product_label": f"HS1992 {row.cmd_code}",
                        "trade_value": float(row.trade_value),
                        "loo_contribution": float(row.contribution),
                        "abs_loo_contribution": float(row.abs_contribution),
                    }
                )
    return pd.DataFrame(rows)


def write_checkpoint(kind: str, raw_path: Path, frame: pd.DataFrame) -> None:
    path = checkpoint_path(kind, raw_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)


def checkpoint_complete(raw_path: Path) -> bool:
    return all(checkpoint_path(kind, raw_path).exists() for kind in CADOT_CHECKPOINT_KINDS)


def world_product_universe_checkpoint_complete(raw_path: Path) -> bool:
    return checkpoint_path("world_product_universe", raw_path).exists()


def process_world_product_universe_file(raw_path: Path, weights: pd.DataFrame, chunk_rows: int) -> dict[str, Any]:
    universe: pd.DataFrame | None = None
    for leaf in tcp.iter_leaf_trade_chunks(raw_path, chunk_rows=chunk_rows):
        leaf = normalize_leaf_for_metric(leaf)
        product_source = tcp.drop_excluded_hs6(leaf)
        product_leaf = harmonize_product_leaf(product_source, weights)
        if product_leaf.empty:
            continue
        universe = add_group_sum(universe, product_leaf, ["flow", "cmd_code"], exclude_hs6=True)
        del leaf
    out = finish_group_sum(universe, ["flow", "cmd_code"])
    if not out.empty:
        out["product_id"] = "HS1992:" + out["cmd_code"].astype(str)
        out = out[["flow", "product_id", "trade_value"]]
        out = out[out["trade_value"] > 0].drop_duplicates(["flow", "product_id"]).copy()
    write_checkpoint("world_product_universe", raw_path, out)
    return {"raw_file": raw_path.name, "status": "written", "world_product_universe_rows": int(len(out))}


def normalize_fixed_universe(universe: pd.DataFrame) -> pd.DataFrame:
    require_columns(universe, "world_broad fixed product universe", {"flow", "product_id"})
    out = universe[["flow", "product_id"]].dropna().drop_duplicates(["flow", "product_id"]).copy()
    out["flow"] = out["flow"].astype(str)
    out["product_id"] = out["product_id"].astype(str)
    bad = out["product_id"].str.contains("999999", na=False)
    if bad.any():
        raise RuntimeError("world_broad fixed product universe contains HS6 999999-derived products.")
    if not out["product_id"].str.startswith("HS1992:").all():
        raise RuntimeError("world_broad fixed product universe contains non-HS1992 product ids.")
    return out.sort_values(["flow", "product_id"]).reset_index(drop=True)


def build_world_product_universe(
    *,
    weights: pd.DataFrame,
    chunk_rows: int,
    max_files: int | None,
    fresh_checkpoints: bool,
    allow_missing_raw: bool,
    manifest_every: int,
) -> pd.DataFrame:
    try:
        cache_path = world_fixed_universe_cache_path()
        if cache_path.exists() and not fresh_checkpoints:
            return normalize_fixed_universe(pd.read_csv(cache_path, dtype={"flow": "string", "product_id": "string"}))

        configure_world_broad_sample()
        files = tcp.hs_bulk_files(max_files=max_files)
        if not files:
            raise FileNotFoundError(f"No Comtrade bulk files found for {BENCHMARK_SAMPLE}.")
        missing = tcp.missing_bulk_keys_for_active_sample(files)
        if missing and not allow_missing_raw:
            blocker = {
                "created_at_utc": now_utc(),
                "status": "blocked",
                "reason": "Local raw bulk files are missing for the world_broad fixed product-universe source.",
                "missing_bulk_keys": [list(key) for key in sorted(missing)[:200]],
                "missing_bulk_key_count": len(missing),
                "country_sample": BENCHMARK_SAMPLE,
                "product_id_mode": PRODUCT_ID_MODE,
            }
            write_json(result_dir() / "cadot_three_metric_world_universe_blocker.json", blocker)
            raise RuntimeError(
                f"Missing {len(missing)} world_broad raw bulk files; "
                f"see {result_dir() / 'cadot_three_metric_world_universe_blocker.json'}"
            )

        rows: list[dict[str, Any]] = []
        for idx, raw_path in enumerate(files, start=1):
            if world_product_universe_checkpoint_complete(raw_path) and not fresh_checkpoints:
                row = {"raw_file": raw_path.name, "status": "already_exists"}
            else:
                print(f"[{idx}/{len(files)}] world_broad harmonized product universe: {raw_path.name}", flush=True)
                row = process_world_product_universe_file(raw_path, weights=weights, chunk_rows=chunk_rows)
            rows.append(row)
            if idx % manifest_every == 0 or row["status"] != "already_exists":
                write_json(
                    result_dir() / "cadot_three_metric_world_universe_checkpoint_manifest.json",
                    {
                        "updated_at_utc": now_utc(),
                        "country_sample": BENCHMARK_SAMPLE,
                        "raw_files_total": len(files),
                        "raw_files_seen": idx,
                        "tail": rows[-50:],
                        "product_id_mode": PRODUCT_ID_MODE,
                        "harmonization_method": HARMONIZATION_METHOD,
                    },
                )

        universe = read_checkpoint_kind("world_product_universe", files)
        if universe.empty:
            raise RuntimeError("world_broad harmonized fixed product universe is empty.")
        universe = normalize_fixed_universe(universe)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        universe.to_csv(cache_path, index=False)
        return universe
    finally:
        configure_sample()


def process_one_file(
    raw_path: Path,
    panel_meta: dict[int, dict[str, Any]],
    bec_mapping: pd.DataFrame,
    weights: pd.DataFrame,
    simulations: int,
    seed: int,
    top_loo: int,
    chunk_rows: int,
) -> dict[str, Any]:
    metadata = tcp.bulk_file_metadata(raw_path)
    if metadata is None:
        raise RuntimeError(f"Could not parse bulk metadata from {raw_path.name}")
    reporter_code = int(metadata["reporter_code"])
    country_meta = panel_meta.get(reporter_code)
    if country_meta is None:
        raise RuntimeError(f"Raw file reporter {reporter_code} is not in {COUNTRY_SAMPLE}.")
    meta = {
        **country_meta,
        "reporter_code": reporter_code,
        "year": int(metadata["year"]),
        "source_classification_code": str(metadata["classification_code"]),
    }
    aggregates = aggregate_raw_file(raw_path, bec_mapping, chunk_rows, weights)
    metric_rows = compute_metric_rows(aggregates, meta)
    ex06_rows = compute_exercise_06_rows(aggregates, meta)
    ex03_rows = compute_exercise_03_rows(aggregates["exercise_03"], meta)
    ex04_rows = compute_exercise_04_rows(aggregates["exercise_04_supplier"], meta)
    seed_digest = hashlib.sha256(f"{seed}:{raw_path.name}".encode("utf-8")).hexdigest()
    rng_seed = (int(seed_digest[:12], 16) % (2**32 - 1)) or seed
    rng = np.random.default_rng(rng_seed)
    ex10_rows = compute_exercise_10_rows(aggregates["product_hs2"], meta, simulations, rng)
    ex11_rows = compute_exercise_11_rows(aggregates["product"], meta, top_loo)
    universe = aggregates["product"][["flow", "cmd_code"]].drop_duplicates()
    universe["product_id"] = "HS1992:" + universe["cmd_code"].astype(str)
    universe = universe[["flow", "product_id"]]

    for frame in [metric_rows, ex06_rows]:
        if not frame.empty:
            frame["source_raw_file"] = raw_path.name
            frame["source_classification_code"] = str(metadata["classification_code"])
    for frame in [ex03_rows, ex04_rows, ex10_rows, ex11_rows, universe]:
        if not frame.empty:
            frame["source_raw_file"] = raw_path.name
            frame["source_classification_code"] = str(metadata["classification_code"])

    write_checkpoint("metric_rows", raw_path, metric_rows)
    write_checkpoint("product_universe", raw_path, universe)
    write_checkpoint("exercise_03", raw_path, ex03_rows)
    write_checkpoint("exercise_04", raw_path, ex04_rows)
    write_checkpoint("exercise_06", raw_path, ex06_rows)
    write_checkpoint("exercise_10", raw_path, ex10_rows)
    write_checkpoint("exercise_11", raw_path, ex11_rows)
    return {
        "raw_file": raw_path.name,
        "status": "written",
        "metric_rows": int(len(metric_rows)),
        "exercise_03_rows": int(len(ex03_rows)),
        "exercise_04_rows": int(len(ex04_rows)),
        "exercise_06_rows": int(len(ex06_rows)),
        "exercise_10_rows": int(len(ex10_rows)),
        "exercise_11_rows": int(len(ex11_rows)),
        "product_universe_rows": int(len(universe)),
    }


def read_checkpoint_kind(kind: str, files: list[Path]) -> pd.DataFrame:
    frames = []
    for raw_path in files:
        path = checkpoint_path(kind, raw_path)
        if path.exists():
            frames.append(pd.read_parquet(path))
    return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()


def finalize_theil(panel: pd.DataFrame, universe_counts: dict[str, int]) -> pd.DataFrame:
    out = panel.copy()
    out["universe_count"] = out["active_count"]
    out["theil_inactive_margin"] = 0.0
    out["theil"] = out["theil_active"]
    product_mask = out["dimension"].eq("product")
    for flow, universe_count in universe_counts.items():
        mask = product_mask & out["flow"].eq(flow)
        active = pd.to_numeric(out.loc[mask, "active_count"], errors="coerce")
        margin = np.log(universe_count / active.replace(0, np.nan))
        out.loc[mask, "universe_count"] = int(universe_count)
        out.loc[mask, "theil_inactive_margin"] = margin
        out.loc[mask, "theil"] = out.loc[mask, "theil_active"] + margin
    out["theil_decomposition_residual"] = out["theil"] - out["theil_active"] - out["theil_inactive_margin"]
    non_product = ~product_mask
    out.loc[non_product, "theil_decomposition_residual"] = 0.0
    out["common_gini_theil_hhi_row"] = out[["gini", "theil", "hhi"]].notna().all(axis=1)
    return out


def add_availability_flags(panel: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    product = out[out["dimension"].eq("product") & out["variant"].eq("baseline")].copy()
    year_count = (
        product.groupby(["reporter_code", "flow"], as_index=False)["year"]
        .nunique()
        .rename(columns={"year": "available_year_count_2000_2024"})
    )
    year_count["balanced_2000_2024_country"] = year_count["available_year_count_2000_2024"] >= (END_YEAR - START_YEAR + 1)
    out = out.merge(year_count, on=["reporter_code", "flow"], how="left")
    out["balanced_2000_2024_country"] = out["balanced_2000_2024_country"].fillna(False).astype(bool)
    for exercise in EXERCISES:
        out[f"exercise_{exercise}_complete_case_row"] = out["common_gini_theil_hhi_row"]
    return out


def latest_rankings(headline: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for metric in ("gini", "theil", "hhi"):
        for flow, group in headline.groupby("flow", sort=True):
            latest_year = int(group["year"].max())
            latest = group[group["year"].eq(latest_year)].copy()
            latest = latest.sort_values([metric, "country"], ascending=[False, True]).reset_index(drop=True)
            latest["metric"] = metric
            latest["rank"] = np.arange(1, len(latest) + 1)
            latest["metric_value"] = latest[metric]
            rows.append(latest[["metric", "rank", "country", "iso3", "reporter_code", "year", "flow", "metric_value", "active_count", "universe_count", "total_trade_value"]])
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def yearly_summary(panel: pd.DataFrame) -> pd.DataFrame:
    return (
        panel.groupby(["year", "flow", "dimension", "variant"], as_index=False)
        .agg(
            countries=("reporter_code", "nunique"),
            rows=("reporter_code", "size"),
            median_gini=("gini", "median"),
            median_theil=("theil", "median"),
            median_hhi=("hhi", "median"),
            mean_gini=("gini", "mean"),
            mean_theil=("theil", "mean"),
            mean_hhi=("hhi", "mean"),
            median_active_count=("active_count", "median"),
            median_total_trade_value=("total_trade_value", "median"),
        )
        .sort_values(["dimension", "variant", "flow", "year"])
    )


def build_exercise_02(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    base = panel[panel["variant"].eq("baseline")].copy()
    product = base[base["dimension"].eq("product")].copy()
    partner = base[base["dimension"].eq("partner")][["reporter_code", "year", "flow", "gini", "theil", "hhi"]].copy()
    partner = partner.rename(columns={"gini": "partner_gini", "theil": "partner_theil", "hhi": "partner_hhi"})
    merged = product.merge(partner, on=["reporter_code", "year", "flow"], how="inner")
    rows = []
    detail_rows = []
    for metric in ("gini", "theil", "hhi"):
        metric_frame = merged.copy()
        metric_frame["product_metric"] = metric_frame[metric]
        metric_frame["partner_metric"] = metric_frame[f"partner_{metric}"]
        med = metric_frame.groupby(["year", "flow"], as_index=False).agg(
            median_product_metric=("product_metric", "median"),
            median_partner_metric=("partner_metric", "median"),
        )
        metric_frame = metric_frame.merge(med, on=["year", "flow"], how="left")
        metric_frame["product_high"] = metric_frame["product_metric"] >= metric_frame["median_product_metric"]
        metric_frame["partner_high"] = metric_frame["partner_metric"] >= metric_frame["median_partner_metric"]
        metric_frame["concentration_bucket"] = np.select(
            [
                metric_frame["product_high"] & metric_frame["partner_high"],
                metric_frame["product_high"] & ~metric_frame["partner_high"],
                ~metric_frame["product_high"] & metric_frame["partner_high"],
            ],
            ["high_product_high_partner", "high_product_low_partner", "low_product_high_partner"],
            default="low_product_low_partner",
        )
        future_base = metric_frame[["reporter_code", "year", "flow", "total_trade_value", "active_count"]].rename(
            columns={
                "year": "future_year",
                "total_trade_value": "future_total_trade_value",
                "active_count": "future_product_active_count",
            }
        )
        for horizon in (1, 5, 10):
            left = metric_frame.copy()
            left["future_year"] = left["year"] + horizon
            joined = left.merge(future_base, on=["reporter_code", "future_year", "flow"], how="inner")
            joined["horizon"] = horizon
            joined["metric"] = metric
            joined["annualized_trade_growth_log"] = (
                np.log(joined["future_total_trade_value"].replace(0, np.nan))
                - np.log(joined["total_trade_value"].replace(0, np.nan))
            ) / horizon
            joined["annualized_product_active_count_growth_log"] = (
                np.log(joined["future_product_active_count"].replace(0, np.nan))
                - np.log(joined["active_count"].replace(0, np.nan))
            ) / horizon
            detail_rows.append(
                joined[
                    [
                        "metric",
                        "country",
                        "iso3",
                        "reporter_code",
                        "year",
                        "future_year",
                        "flow",
                        "horizon",
                        "concentration_bucket",
                        "product_metric",
                        "partner_metric",
                        "total_trade_value",
                        "future_total_trade_value",
                        "annualized_trade_growth_log",
                        "active_count",
                        "future_product_active_count",
                        "annualized_product_active_count_growth_log",
                    ]
                ]
            )
            rows.append(
                joined.groupby(["metric", "flow", "horizon", "concentration_bucket"], as_index=False)
                .agg(
                    observations=("reporter_code", "size"),
                    countries=("reporter_code", "nunique"),
                    mean_annualized_trade_growth_log=("annualized_trade_growth_log", "mean"),
                    median_annualized_trade_growth_log=("annualized_trade_growth_log", "median"),
                    mean_annualized_product_active_count_growth_log=("annualized_product_active_count_growth_log", "mean"),
                    median_base_trade_value=("total_trade_value", "median"),
                )
            )
    summary = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    detail = pd.concat(detail_rows, ignore_index=True) if detail_rows else pd.DataFrame()
    return summary, detail


def build_exercise_12(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    base = panel[panel["variant"].eq("baseline")].copy()
    dimensions = {}
    for dimension in DIMENSION_ORDER:
        part = base[base["dimension"].eq(dimension)][
            ["country", "iso3", "reporter_code", "year", "flow", "active_count", "total_trade_value", "gini", "theil", "hhi"]
        ].copy()
        rename = {col: f"{dimension}_{col}" for col in ["active_count", "total_trade_value", "gini", "theil", "hhi"]}
        dimensions[dimension] = part.rename(columns=rename)
    merged = dimensions["product"]
    for dimension in ("partner", "product_partner_cell"):
        merged = merged.merge(
            dimensions[dimension].drop(columns=["country", "iso3"]),
            on=["reporter_code", "year", "flow"],
            how="inner",
        )
    rows = []
    summaries = []
    for metric in ("gini", "theil", "hhi"):
        work = merged.copy()
        work["base_concentration"] = work[f"product_{metric}"]
        med = work.groupby(["year", "flow"], as_index=False)["base_concentration"].median().rename(columns={"base_concentration": "median_base_concentration"})
        work = work.merge(med, on=["year", "flow"], how="left")
        work["base_concentration_bucket"] = np.where(work["base_concentration"] >= work["median_base_concentration"], "high_product_concentration", "low_product_concentration")
        future = work[
            [
                "reporter_code",
                "year",
                "flow",
                "product_total_trade_value",
                "product_active_count",
                "partner_active_count",
                "product_partner_cell_active_count",
            ]
        ].rename(
            columns={
                "year": "future_year",
                "product_total_trade_value": "future_total_trade_value",
                "product_active_count": "future_product_active_count",
                "partner_active_count": "future_partner_active_count",
                "product_partner_cell_active_count": "future_cell_active_count",
            }
        )
        for horizon in (1, 5, 10):
            left = work.copy()
            left["future_year"] = left["year"] + horizon
            joined = left.merge(future, on=["reporter_code", "future_year", "flow"], how="inner")
            joined["metric"] = metric
            joined["horizon"] = horizon
            joined["annualized_trade_growth_log"] = (
                np.log(joined["future_total_trade_value"].replace(0, np.nan))
                - np.log(joined["product_total_trade_value"].replace(0, np.nan))
            ) / horizon
            for name, base_col, future_col in [
                ("product", "product_active_count", "future_product_active_count"),
                ("partner", "partner_active_count", "future_partner_active_count"),
                ("cell", "product_partner_cell_active_count", "future_cell_active_count"),
            ]:
                joined[f"annualized_{name}_active_count_growth_log"] = (
                    np.log(joined[future_col].replace(0, np.nan)) - np.log(joined[base_col].replace(0, np.nan))
                ) / horizon
            keep = [
                "metric",
                "country",
                "iso3",
                "reporter_code",
                "year",
                "future_year",
                "flow",
                "horizon",
                "base_concentration_bucket",
                "base_concentration",
                "product_total_trade_value",
                "future_total_trade_value",
                "annualized_trade_growth_log",
                "annualized_product_active_count_growth_log",
                "annualized_partner_active_count_growth_log",
                "annualized_cell_active_count_growth_log",
            ]
            rows.append(joined[keep])
            summaries.append(
                joined.groupby(["metric", "flow", "horizon", "base_concentration_bucket"], as_index=False)
                .agg(
                    observations=("reporter_code", "size"),
                    countries=("reporter_code", "nunique"),
                    mean_annualized_trade_growth_log=("annualized_trade_growth_log", "mean"),
                    median_annualized_trade_growth_log=("annualized_trade_growth_log", "median"),
                    mean_annualized_product_active_count_growth_log=("annualized_product_active_count_growth_log", "mean"),
                    mean_annualized_partner_active_count_growth_log=("annualized_partner_active_count_growth_log", "mean"),
                    mean_annualized_cell_active_count_growth_log=("annualized_cell_active_count_growth_log", "mean"),
                )
            )
    detail = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    summary = pd.concat(summaries, ignore_index=True) if summaries else pd.DataFrame()
    return detail, summary


def finalize_ex10(ex10: pd.DataFrame, universe_counts: dict[str, int]) -> pd.DataFrame:
    if ex10.empty:
        return ex10
    out = ex10.copy()
    out["product_universe_count"] = out["flow"].map(universe_counts).astype(float)
    out["theil_fixed_universe_margin"] = np.log(out["product_universe_count"] / out["active_items"].replace(0, np.nan))
    for col in ["actual_theil_active", "sim_theil_active_median", "sim_theil_active_p05", "sim_theil_active_p95"]:
        if col in out.columns:
            fixed_col = col.replace("theil_active", "theil")
            out[fixed_col] = out[col] + out["theil_fixed_universe_margin"]
    if "actual_theil" in out.columns and "sim_theil_median" in out.columns:
        out["actual_minus_sim_median_theil"] = out["actual_theil"] - out["sim_theil_median"]
    return out


def sample_attrition(panel: pd.DataFrame, files: list[Path]) -> pd.DataFrame:
    product = panel[panel["dimension"].eq("product") & panel["variant"].eq("baseline")].copy()
    actual = product.groupby(["reporter_code", "flow"], as_index=False).agg(
        actual_metric_years=("year", "nunique"),
        first_metric_year=("year", "min"),
        last_metric_year=("year", "max"),
    )
    country_panel = pd.read_csv(sample_dir() / "comtrade_country_panel.csv")
    coverage = pd.read_csv(sample_dir() / "country_coverage_summary.csv")
    out = country_panel.merge(coverage, on=["country", "iso3", "reporter_code"], how="left")
    flows = pd.DataFrame({"flow": list(FLOW_ORDER)})
    out = out.merge(flows, how="cross")
    out = out.merge(actual, on=["reporter_code", "flow"], how="left")
    out["actual_metric_years"] = out["actual_metric_years"].fillna(0).astype(int)
    out["balanced_2000_2024_country"] = out["actual_metric_years"] >= (END_YEAR - START_YEAR + 1)
    available_keys = {(tcp.bulk_file_metadata(path)["reporter_code"], tcp.bulk_file_metadata(path)["year"]) for path in files if tcp.bulk_file_metadata(path)}
    out["raw_files_available_for_any_year"] = out["reporter_code"].map(lambda code: any(key[0] == int(code) for key in available_keys))
    return out.sort_values(["flow", "country"])


def validate_outputs(
    panel: pd.DataFrame,
    ex06: pd.DataFrame,
    universe: pd.DataFrame,
    country_universe: pd.DataFrame,
    universe_counts: dict[str, int],
    files: list[Path],
    allow_missing_raw: bool,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    def add_check(name: str, passed: bool, details: str = "") -> None:
        rows.append({"check": name, "passed": bool(passed), "details": details})

    add_check(
        "selected_reporter_count_expected",
        len(pd.read_csv(sample_dir() / "comtrade_country_panel.csv")) == EXPECTED_REPORTERS,
    )
    bad_products = universe["product_id"].astype(str).str.contains("999999", na=False).sum() if not universe.empty else 0
    add_check("no_product_dependent_999999", bad_products == 0, f"bad_product_ids={bad_products}")
    non_hs1992 = int((~universe["product_id"].astype(str).str.startswith("HS1992:")).sum()) if not universe.empty else 0
    add_check("fixed_universe_hs1992_product_ids", non_hs1992 == 0, f"non_hs1992_product_ids={non_hs1992}")
    if not country_universe.empty:
        active_outside = country_universe[["flow", "product_id"]].drop_duplicates().merge(
            universe[["flow", "product_id"]].drop_duplicates().assign(_in_fixed_universe=True),
            on=["flow", "product_id"],
            how="left",
        )
        outside_count = int(active_outside["_in_fixed_universe"].isna().sum())
    else:
        outside_count = 0
    add_check("sample_products_inside_world_broad_fixed_universe", outside_count == 0, f"active_products_outside_world_universe={outside_count}")
    key_cols = ["reporter_code", "year", "flow", "dimension", "variant"]
    dupes = int(panel.duplicated(key_cols).sum())
    add_check("unique_reporter_year_flow_dimension_variant", dupes == 0, f"duplicate_rows={dupes}")
    hhi_bad = int(((panel["hhi"] < -1e-12) | (panel["hhi"] > 1 + 1e-12)).sum())
    add_check("hhi_bounds_0_1", hhi_bad == 0, f"bad_rows={hhi_bad}")
    product = panel[panel["dimension"].eq("product")].copy()
    fixed_counts_ok = all(group["universe_count"].nunique() == 1 for _flow, group in product.groupby("flow"))
    add_check("fixed_theil_universe_counts_by_flow", fixed_counts_ok, str(universe_counts))
    residual_bad = int((product["theil_decomposition_residual"].abs() > 1e-9).sum())
    add_check("theil_decomposition_residuals", residual_bad == 0, f"bad_rows={residual_bad}")
    parity_bad = int((~panel["common_gini_theil_hhi_row"]).sum())
    add_check("cross_metric_key_parity", parity_bad == 0, f"rows_with_missing_metric={parity_bad}")
    expected_missing = tcp.missing_bulk_keys_for_active_sample(files)
    add_check(
        "raw_files_present_for_available_country_years",
        allow_missing_raw or len(expected_missing) == 0,
        f"missing_available_bulk_keys={len(expected_missing)}",
    )
    if not ex06.empty:
        ex06_dupes = int(ex06.duplicated(key_cols).sum())
        add_check("exercise_06_unique_keys", ex06_dupes == 0, f"duplicate_rows={ex06_dupes}")

    validation = pd.DataFrame(rows)
    validation.to_csv(result_dir() / "validation_checks.csv", index=False)
    failed = validation[~validation["passed"]]
    if not failed.empty:
        failed.to_csv(result_dir() / "validation_failures.csv", index=False)
        if not allow_missing_raw or not failed["check"].eq("raw_files_present_for_available_country_years").all():
            raise RuntimeError(f"Validation failed: {failed.to_dict(orient='records')}")
    return validation


def write_methods_note(manifest: dict[str, Any], validation: pd.DataFrame) -> None:
    note = f"""# {COUNTRY_SAMPLE} Three-Metric Run

Generated: {now_utc()}

This run builds the selected reporter-sample three-metric bundle for Gini,
Theil, and HHI over annual UN Comtrade final-data files in {START_YEAR}-{END_YEAR}.
For website-facing outputs, the required sample is `rd2_countries`. The
`cadot_broad_156` sample is retained only as a clearly labeled research
sensitivity. Product-dependent outputs convert source HS6 revision-code values
with LT/HGL weighted HS1992/H0 weights before product aggregation.

## Measures

- Gini: active-positive Gini over observed positive trade values.
- Theil headline: fixed-universe product Theil, `sum_p s_cpft * log(s_cpft * K_f)`, where `K_f` is the flow-specific 2000-2024 union of positive `world_broad` LT/HGL HS1992 product-family support.
- HHI headline: raw `sum_i s_i^2` on `[0,1]`.
- Product-dependent outputs exclude HS6 `999999` before LT/HGL conversion and aggregation.
- Partner-only concentration includes `999999` after product identity is summed away; partner `0` World is excluded by the raw leaf extractor.
- Harmonization: `{manifest.get("harmonization_method")}`, source DOI `{manifest.get("harmonization_source_doi")}`, version `{manifest.get("harmonization_source_version")}`, target `{manifest.get("harmonization_target")}`.

## Sample

- Selected reporters: {manifest.get("selected_reporters")}
- Raw files processed: {manifest.get("raw_files_processed")}
- Product identity: `{manifest.get("product_id_mode")}`
- Fixed universe source: `{manifest.get("fixed_universe_source")}`
- Product universes: `{json.dumps(manifest.get("product_universe_counts", {}), sort_keys=True)}`
- Complete balanced reporter-flow cells: {manifest.get("balanced_reporter_flow_cells")}

## Validation

{validation.to_markdown(index=False)}
"""
    (result_dir() / "cadot_three_metric_methods.md").write_text(note, encoding="utf-8")


def finalize(files: list[Path], fixed_universe: pd.DataFrame, allow_missing_raw: bool = False) -> dict[str, Any]:
    metrics = read_checkpoint_kind("metric_rows", files)
    country_universe = read_checkpoint_kind("product_universe", files)
    ex03 = read_checkpoint_kind("exercise_03", files)
    ex04 = read_checkpoint_kind("exercise_04", files)
    ex06 = read_checkpoint_kind("exercise_06", files)
    ex10 = read_checkpoint_kind("exercise_10", files)
    ex11 = read_checkpoint_kind("exercise_11", files)
    checkpoint_frames = [metrics, country_universe, ex03, ex04, ex06, ex10, ex11]
    (
        metrics,
        country_universe,
        ex03,
        ex04,
        ex06,
        ex10,
        ex11,
    ) = [normalize_source_metadata_columns(frame) for frame in checkpoint_frames]
    if metrics.empty:
        raise RuntimeError("No metric checkpoint rows were found.")
    if country_universe.empty:
        raise RuntimeError(f"No {COUNTRY_SAMPLE} product-universe checkpoint rows were found.")
    if fixed_universe.empty:
        raise RuntimeError("No world_broad fixed product-universe rows were found.")

    universe = fixed_universe.drop_duplicates(["flow", "product_id"]).copy()
    universe_counts = {str(flow): int(group["product_id"].nunique()) for flow, group in universe.groupby("flow")}
    metrics = finalize_theil(metrics, universe_counts)
    metrics = add_availability_flags(metrics)
    ex06 = finalize_theil(ex06, universe_counts) if not ex06.empty else ex06
    ex06 = add_availability_flags(ex06) if not ex06.empty else ex06
    ex10 = finalize_ex10(ex10, universe_counts)

    headline = metrics[metrics["dimension"].eq("product") & metrics["variant"].eq("baseline")].copy()
    rankings = latest_rankings(headline)
    yearly = yearly_summary(metrics)
    ex02_summary, ex02_panel = build_exercise_02(metrics)
    ex12_panel, ex12_summary = build_exercise_12(metrics)
    attrition = sample_attrition(metrics, files)
    validation = validate_outputs(metrics, ex06, universe, country_universe, universe_counts, files, allow_missing_raw=allow_missing_raw)

    website_frames = [metrics, headline, rankings, yearly, ex02_summary, ex02_panel, ex03, ex04, ex06, ex10, ex11, ex12_panel, ex12_summary]
    for frame in website_frames:
        if not frame.empty:
            frame["product_id_mode"] = PRODUCT_ID_MODE
            frame["harmonization_method"] = HARMONIZATION_METHOD

    outputs = {
        "concentration_metric_all_years.csv": metrics,
        "metric_headline_product_panel.csv": headline,
        "metric_latest_rankings.csv": rankings,
        "metric_yearly_summary.csv": yearly,
        "exercise_02_bucket_growth_summary.csv": ex02_summary,
        "exercise_02_bucket_growth_panel.csv": ex02_panel,
        "exercise_03_import_bin_metrics.csv": ex03,
        "exercise_04_dominant_supplier_summary.csv": ex04,
        "exercise_06_exclusion_metrics.csv": ex06,
        "exercise_10_random_benchmarks.csv": ex10,
        "exercise_11_top_product_loo_contributions.csv": ex11,
        "exercise_12_growth_decomposition_panel.csv": ex12_panel,
        "exercise_12_growth_decomposition_summary.csv": ex12_summary,
        "sample_attrition_by_reporter_flow.csv": attrition,
        "product_universe.csv": universe,
        "cadot_observed_product_support.csv": country_universe,
    }
    for filename, frame in outputs.items():
        path = result_dir() / filename
        frame.to_csv(path, index=False)
        if filename.endswith(".csv") and len(frame) > 0 and filename not in {"product_universe.csv"}:
            frame.to_parquet(path.with_suffix(".parquet"), index=False)

    balanced_cells = int(attrition["balanced_2000_2024_country"].sum()) if not attrition.empty else 0
    manifest = {
        "created_at_utc": now_utc(),
        "country_sample": COUNTRY_SAMPLE,
        "sample_window": {"start_year": START_YEAR, "end_year": END_YEAR},
        "selected_reporters": EXPECTED_REPORTERS,
        "raw_files_processed": len(files),
        "product_id_mode": PRODUCT_ID_MODE,
        "harmonization_method": HARMONIZATION_METHOD,
        "harmonization_source_doi": tcp.LT_HGL_DATASET_DOI,
        "harmonization_source_version": tcp.LT_HGL_DATASET_VERSION,
        "harmonization_target": f"{tcp.LT_HGL_TARGET_LABEL}/{tcp.LT_HGL_TARGET_REVISION}",
        "fixed_universe_source": BENCHMARK_SAMPLE,
        "product_universe_counts": universe_counts,
        "balanced_reporter_flow_cells": balanced_cells,
        "outputs": {name: rel(result_dir() / name) for name in outputs},
        "validation": rel(result_dir() / "validation_checks.csv"),
        "product_dependent_exclusion": "HS6 999999 excluded before LT/HGL HS1992 conversion and product/cell/exclusion aggregation.",
        "partner_only_convention": "partner-only concentration includes HS6 999999 after product identity is summed away; partnerCode 0 is excluded.",
        "theil_formula": "sum_p s_cpft * log(s_cpft * K_f)",
        "hhi_formula": "sum_i s_i^2",
    }
    write_json(result_dir() / "cadot_three_metric_manifest.json", manifest)
    write_methods_note(manifest, validation)
    return manifest


def run_checkpoints(args: argparse.Namespace) -> list[Path]:
    panel = configure_sample()
    prepare_dirs(fresh=args.fresh_checkpoints)
    weights = tcp.load_lt_hgl_hs1992_conversion_weights()
    files = tcp.hs_bulk_files(max_files=args.max_files)
    if not files:
        raise FileNotFoundError(f"No Comtrade bulk files found for {COUNTRY_SAMPLE}.")
    missing = tcp.missing_bulk_keys_for_active_sample(files)
    if missing and not args.allow_missing_raw:
        blocker = {
            "created_at_utc": now_utc(),
            "status": "blocked",
            "reason": f"Local raw bulk files are missing for selected available {COUNTRY_SAMPLE} reporter-year-classification keys.",
            "missing_bulk_keys": [list(key) for key in sorted(missing)[:200]],
            "missing_bulk_key_count": len(missing),
            "country_sample": COUNTRY_SAMPLE,
        }
        write_json(result_dir() / "cadot_three_metric_blocker.json", blocker)
        raise RuntimeError(f"Missing {len(missing)} required raw bulk files; see {result_dir() / 'cadot_three_metric_blocker.json'}")

    panel_meta = panel.set_index("reporter_code")[["country", "iso3"]].to_dict("index")
    bec_mapping = load_bec_mapping_or_empty()
    manifest_rows: list[dict[str, Any]] = []
    for idx, raw_path in enumerate(files, start=1):
        if checkpoint_complete(raw_path) and not args.fresh_checkpoints:
            row = {"raw_file": raw_path.name, "status": "already_exists"}
        else:
            print(f"[{idx}/{len(files)}] {COUNTRY_SAMPLE} three-metric checkpoints: {raw_path.name}", flush=True)
            row = process_one_file(
                raw_path,
                panel_meta=panel_meta,
                bec_mapping=bec_mapping,
                weights=weights,
                simulations=args.simulations,
                seed=args.seed,
                top_loo=args.top_loo_products,
                chunk_rows=args.chunk_rows,
            )
        manifest_rows.append(row)
        if idx % args.manifest_every == 0 or row["status"] != "already_exists":
            write_json(
                result_dir() / "cadot_three_metric_checkpoint_manifest.json",
                {
                    "updated_at_utc": now_utc(),
                    "country_sample": COUNTRY_SAMPLE,
                    "raw_files_total": len(files),
                    "raw_files_seen": idx,
                    "tail": manifest_rows[-50:],
                    "simulations": args.simulations,
                    "top_loo_products": args.top_loo_products,
                    "chunk_rows": args.chunk_rows,
                    "product_id_mode": PRODUCT_ID_MODE,
                    "harmonization_method": HARMONIZATION_METHOD,
                },
            )
    return files


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--country-sample",
        choices=(tcp.RD2_SAMPLE, tcp.CADOT_BROAD_SAMPLE),
        default=tcp.RD2_SAMPLE,
        help=f"Reporter sample. Use {tcp.RD2_SAMPLE} for website-facing outputs; {tcp.CADOT_BROAD_SAMPLE} is research-only.",
    )
    parser.add_argument("--max-files", type=int, default=None, help="Process only the first N raw files for debugging.")
    parser.add_argument("--chunk-rows", type=int, default=tcp.DEFAULT_CHUNK_ROWS, help="Rows per raw Comtrade read chunk.")
    parser.add_argument("--simulations", type=int, default=250, help="Random benchmark simulations per reporter-year-flow.")
    parser.add_argument("--seed", type=int, default=1729, help="Random seed for Exercise 10 benchmarks.")
    parser.add_argument("--top-loo-products", type=int, default=25, help="Top absolute leave-one-out products to retain per metric.")
    parser.add_argument("--fresh-checkpoints", action="store_true", help="Delete existing three-metric checkpoints before running.")
    parser.add_argument("--finalize-only", action="store_true", help="Skip raw processing and finalize existing checkpoints.")
    parser.add_argument("--allow-missing-raw", action="store_true", help="Allow finalization when locally available raw files do not cover all availability keys.")
    parser.add_argument("--manifest-every", type=int, default=25, help="Write checkpoint manifest every N files.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_metric_sample(args.country_sample)
    configure_sample()
    prepare_dirs(fresh=False)
    weights = tcp.load_lt_hgl_hs1992_conversion_weights()
    fixed_universe = build_world_product_universe(
        weights=weights,
        chunk_rows=args.chunk_rows,
        max_files=args.max_files,
        fresh_checkpoints=args.fresh_checkpoints,
        allow_missing_raw=args.allow_missing_raw,
        manifest_every=args.manifest_every,
    )
    files = tcp.hs_bulk_files(max_files=args.max_files)
    if args.finalize_only:
        missing_checkpoints = [path.name for path in files if not checkpoint_complete(path)]
        if missing_checkpoints:
            raise RuntimeError(f"Cannot finalize; missing checkpoints for {len(missing_checkpoints)} raw files.")
    else:
        files = run_checkpoints(args)
    manifest = finalize(files, fixed_universe=fixed_universe, allow_missing_raw=args.allow_missing_raw)
    print(json.dumps(manifest, indent=2, sort_keys=True, default=json_default), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
