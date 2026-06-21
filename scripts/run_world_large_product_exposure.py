#!/usr/bin/env python3
"""Test whether larger economies export globally large products.

The default website-facing rd2 run keeps the existing inclusive-world export
diagnostic. When `--country-sample cadot_broad_156` is used, the runner can
also compute a broad-primary-excluded non-commodity variant alongside the
baseline.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_country_size_effect as cse  # noqa: E402
import run_world_relative_product_gini as wrg  # noqa: E402
import trade_concentration_pipeline as tcp  # noqa: E402


DEFAULT_COUNTRY_SAMPLE = tcp.RD2_SAMPLE
SUPPORTED_COUNTRY_SAMPLES = (tcp.RD2_SAMPLE, tcp.CADOT_BROAD_SAMPLE)
BENCHMARK_SAMPLE = tcp.WORLD_BROAD_SAMPLE
FLOW = "Exports"
PRODUCT_ID_MODE = "harmonized_hs6_family"
START_YEAR = 2000
END_YEAR = 2024
TOP_WORLD_SHARE_CUTOFFS = (0.01, 0.05, 0.10, 0.20)
OUTPUT_DIRNAME = "world_large_product_exposure_tables"
PANEL_FILENAME = "world_large_product_exposure_panel.parquet"
FIGURE_DIRNAME = "country_size_effect_figures"
ALIGNMENT_SCATTER_FILENAME = "gdp_product_alignment_scatter.png"
FIXED_COUNTRY_WINDOW = (2018, 2024)
TOP_DELTA_PRODUCTS = 10

VARIANT_SPECS: dict[str, dict[str, Any]] = {
    "baseline": {
        "label": "Inclusive world export basket",
        "exclude_primary_broad": False,
        "basket_description": "All positive harmonized export products, with HS6 999999 excluded upstream.",
    },
    "noncommodity_broad": {
        "label": "Broad-primary-excluded non-commodity basket",
        "exclude_primary_broad": True,
        "basket_description": (
            "Removes broad primary products from both country and world baskets, then renormalizes shares "
            "and rebuilds world ranks in the remaining non-commodity universe."
        ),
    },
}
SUMMARY_OUTCOMES = ("world_share_exposure", "spearman_product_alignment")


@dataclass(frozen=True)
class ProductInputPaths:
    country_product: Path
    world_product: Path


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def now_utc() -> str:
    return tcp.now_utc()


def output_dir(country_sample: str = DEFAULT_COUNTRY_SAMPLE) -> Path:
    return tcp.sample_results_dir(country_sample) / OUTPUT_DIRNAME


def processed_panel_path(country_sample: str = DEFAULT_COUNTRY_SAMPLE) -> Path:
    return tcp.sample_processed_path(PANEL_FILENAME, country_sample)


def figure_dir(country_sample: str = DEFAULT_COUNTRY_SAMPLE) -> Path:
    return tcp.sample_results_dir(country_sample) / FIGURE_DIRNAME


def alignment_scatter_path(country_sample: str = DEFAULT_COUNTRY_SAMPLE) -> Path:
    return figure_dir(country_sample) / ALIGNMENT_SCATTER_FILENAME


def sample_product_slug(sample_name: str) -> str:
    return {
        tcp.RD2_SAMPLE: "rd2",
        tcp.CADOT_BROAD_SAMPLE: tcp.CADOT_BROAD_SAMPLE,
    }.get(sample_name, sample_name)


def product_input_paths(country_sample: str, benchmark_sample: str) -> ProductInputPaths:
    stem = wrg.artifact_stem(FLOW)
    noun = wrg.flow_value_noun(FLOW)
    country_slug = sample_product_slug(country_sample)
    return ProductInputPaths(
        country_product=tcp.sample_processed_path(
            f"{stem}_{PRODUCT_ID_MODE}_{country_slug}_product_{noun}.parquet",
            country_sample,
        ),
        world_product=tcp.sample_processed_path(
            f"{stem}_{PRODUCT_ID_MODE}_world_product_{noun}.parquet",
            benchmark_sample,
        ),
    )


def top_cutoff_col(cutoff: float) -> str:
    pct = int(round(cutoff * 100))
    return f"is_top_{pct}pct_world_product"


def share_cutoff_col(cutoff: float) -> str:
    pct = int(round(cutoff * 100))
    return f"top_{pct}pct_world_product_export_share"


def product_id_to_cmd_code(series: pd.Series) -> pd.Series:
    return (
        series.astype("string")
        .str.replace(r"\D", "", regex=True)
        .str[-6:]
        .fillna("")
        .str.zfill(6)
    )


def resolve_variants(country_sample: str, requested: list[str] | None) -> list[str]:
    if requested:
        ordered = [variant for variant in VARIANT_SPECS if variant in requested]
        if len(ordered) != len(set(requested)):
            raise RuntimeError(f"Unknown or duplicate variants requested: {requested}")
        return ordered
    if country_sample == tcp.CADOT_BROAD_SAMPLE:
        return ["baseline", "noncommodity_broad"]
    return ["baseline"]


def assert_no_999999_product_ids(frame: pd.DataFrame, label: str) -> None:
    if "product_id" not in frame.columns:
        raise RuntimeError(f"{label} is missing product_id.")
    bad = frame["product_id"].astype("string").str.contains("999999", regex=False, na=False)
    if bool(bad.any()):
        examples = frame.loc[bad, "product_id"].drop_duplicates().head(10).tolist()
        raise RuntimeError(f"{label} contains excluded HS6 999999-derived product IDs: {examples}")


def load_country_panel(country_sample: str, start_year: int, end_year: int) -> pd.DataFrame:
    settings = tcp.configure_country_sample(
        country_sample=country_sample,
        min_available_years=10,
        start_year=start_year,
        end_year=end_year,
        refresh_availability=False,
    )
    panel = tcp.save_country_panel()
    required = {"country", "iso3", "reporter_code"}
    missing = required - set(panel.columns)
    if missing:
        raise RuntimeError(f"Country panel is missing columns: {sorted(missing)}")
    panel = panel[["country", "iso3", "reporter_code"]].copy()
    panel["iso3"] = panel["iso3"].astype(str).str.upper().str.strip()
    panel["reporter_code"] = pd.to_numeric(panel["reporter_code"], errors="coerce").astype(int)
    if panel["reporter_code"].duplicated().any():
        raise RuntimeError("Country panel has duplicate reporter_code values.")
    expected_reporters = len(panel)
    if settings.name == tcp.CADOT_BROAD_SAMPLE and expected_reporters != tcp.CADOT_BROAD_EXPECTED_REPORTERS:
        raise RuntimeError(
            f"cadot_broad_156 must contain exactly {tcp.CADOT_BROAD_EXPECTED_REPORTERS} reporters; "
            f"found {expected_reporters}."
        )
    return panel


def missing_bulk_summary(sample_name: str, start_year: int, end_year: int, refresh_availability: bool) -> dict[str, Any]:
    return wrg.missing_bulk_summary(sample_name, start_year, end_year, refresh_availability)


def maybe_download_missing(sample_name: str, args: argparse.Namespace) -> None:
    key = args.subscription_key or os.getenv("COMTRADE_SUBSCRIPTION_KEY")
    if not key:
        raise RuntimeError(
            f"Missing raw files for {sample_name} and no COMTRADE_SUBSCRIPTION_KEY is available."
        )
    tcp.configure_country_sample(
        country_sample=sample_name,
        min_available_years=10,
        start_year=args.start_year,
        end_year=args.end_year,
        refresh_availability=args.refresh_availability,
    )
    availability = tcp.download_availability(key)
    tcp.download_bulk_files(key, availability, workers=args.download_workers)


def validate_raw_coverage(args: argparse.Namespace) -> dict[str, Any]:
    benchmark = missing_bulk_summary(args.benchmark_sample, args.start_year, args.end_year, args.refresh_availability)
    if benchmark["missing_keys"] and args.download_missing:
        maybe_download_missing(args.benchmark_sample, args)
        benchmark = missing_bulk_summary(args.benchmark_sample, args.start_year, args.end_year, False)
    if benchmark["missing_keys"]:
        raise RuntimeError(
            f"{args.benchmark_sample} raw bulk coverage is incomplete for {args.start_year}-{args.end_year}: "
            f"{benchmark['missing_keys']} missing keys."
        )

    country = missing_bulk_summary(args.country_sample, args.start_year, args.end_year, args.refresh_availability)
    if country["missing_keys"] and args.download_missing:
        maybe_download_missing(args.country_sample, args)
        country = missing_bulk_summary(args.country_sample, args.start_year, args.end_year, False)
    if country["missing_keys"]:
        raise RuntimeError(
            f"{args.country_sample} raw bulk coverage is incomplete for {args.start_year}-{args.end_year}: "
            f"{country['missing_keys']} missing keys."
        )
    return {"benchmark_raw_coverage": benchmark, "country_raw_coverage": country}


def build_or_load_product_inputs(args: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    paths = product_input_paths(args.country_sample, args.benchmark_sample)
    coverage_manifest: dict[str, Any] = {}
    country_conversion: dict[str, Any] | None = None
    benchmark_conversion: dict[str, Any] | None = None

    if paths.country_product.exists() and paths.world_product.exists() and not args.rebuild_product_inputs:
        country = pd.read_parquet(paths.country_product)
        world = pd.read_parquet(paths.world_product)
        manifest_source = "existing_product_inputs"
    else:
        coverage_manifest = validate_raw_coverage(args)
        country_config = wrg.configure_sample(args.country_sample, args.start_year, args.end_year, args.refresh_availability)
        benchmark_config = wrg.configure_sample(args.benchmark_sample, args.start_year, args.end_year, args.refresh_availability)

        country_partials = wrg.build_partials(args.country_sample, country_config, args)
        benchmark_partials = wrg.build_partials(args.benchmark_sample, benchmark_config, args)

        tcp.configure_country_sample(**country_config)
        country_files = tcp.hs_bulk_files(args.max_files)
        country = wrg.aggregate_product_trade(
            args.country_sample,
            country_files,
            paths.country_product,
            PRODUCT_ID_MODE,
            FLOW,
        )

        tcp.configure_country_sample(**benchmark_config)
        benchmark_files = tcp.hs_bulk_files(args.max_files)
        benchmark_tmp = paths.world_product.with_name("tmp_benchmark_product_exports.parquet")
        benchmark_product = wrg.aggregate_product_trade(
            args.benchmark_sample,
            benchmark_files,
            benchmark_tmp,
            PRODUCT_ID_MODE,
            FLOW,
        )
        world = wrg.build_world_product_totals(benchmark_product, paths.world_product, FLOW)
        benchmark_tmp.unlink(missing_ok=True)

        country_conversion = wrg.conversion_value_diagnostics(args.country_sample, country_files, country, FLOW)
        benchmark_conversion = wrg.conversion_value_diagnostics(args.benchmark_sample, benchmark_files, benchmark_product, FLOW)
        manifest_source = "rebuilt_product_inputs"
        coverage_manifest.update(
            {
                "country_partials": country_partials,
                "benchmark_partials": benchmark_partials,
            }
        )

    required_country = {"reporter_code", "year", "product_id", "trade_value"}
    required_world = {"year", "product_id", "world_product_exports"}
    missing_country = required_country - set(country.columns)
    missing_world = required_world - set(world.columns)
    if missing_country:
        raise RuntimeError(f"Country product input is missing columns: {sorted(missing_country)}")
    if missing_world:
        raise RuntimeError(f"World product input is missing columns: {sorted(missing_world)}")

    for label, frame in [("country product input", country), ("world product input", world)]:
        assert_no_999999_product_ids(frame, label)
        frame["year"] = pd.to_numeric(frame["year"], errors="coerce").astype(int)
        frame["product_id"] = frame["product_id"].astype(str)

    country["reporter_code"] = pd.to_numeric(country["reporter_code"], errors="coerce").astype(int)
    country["trade_value"] = pd.to_numeric(country["trade_value"], errors="coerce").fillna(0.0)
    world["world_product_exports"] = pd.to_numeric(world["world_product_exports"], errors="coerce").fillna(0.0)
    country = country[country["year"].between(args.start_year, args.end_year) & (country["trade_value"] > 0)].copy()
    world = world[world["year"].between(args.start_year, args.end_year) & (world["world_product_exports"] > 0)].copy()
    if country.empty or world.empty:
        raise RuntimeError("Product inputs are empty after year/value filters.")

    if country_conversion is None or benchmark_conversion is None:
        country_config = wrg.configure_sample(args.country_sample, args.start_year, args.end_year, False)
        tcp.configure_country_sample(**country_config)
        country_files = tcp.hs_bulk_files(args.max_files)
        country_conversion = wrg.conversion_value_diagnostics(args.country_sample, country_files, country, FLOW)

        benchmark_config = wrg.configure_sample(args.benchmark_sample, args.start_year, args.end_year, False)
        tcp.configure_country_sample(**benchmark_config)
        benchmark_files = tcp.hs_bulk_files(args.max_files)
        benchmark_as_product = world.rename(columns={"world_product_exports": "trade_value"})
        benchmark_conversion = wrg.conversion_value_diagnostics(args.benchmark_sample, benchmark_files, benchmark_as_product, FLOW)

    manifest = {
        "source": manifest_source,
        "country_product": rel(paths.country_product),
        "world_product": rel(paths.world_product),
        "country_conversion_diagnostics": country_conversion,
        "benchmark_conversion_diagnostics": benchmark_conversion,
    }
    manifest.update(coverage_manifest)
    return country, world, manifest


def h0_product_labels() -> pd.DataFrame:
    payload = json.loads((ROOT / "data/raw/classifications/H0.json").read_text(encoding="utf-8"))
    rows = []
    for item in payload.get("results", []):
        code = str(item.get("id", "")).strip()
        if len(code) != 6 or not code.isdigit():
            continue
        text = str(item.get("text", "")).strip()
        if " - " in text:
            text = text.split(" - ", 1)[1].strip()
        rows.append({"cmd_code": code, "product_label": text or f"HS1992 {code}"})
    return pd.DataFrame(rows).drop_duplicates("cmd_code")


def build_harmonized_product_mapping(country_product: pd.DataFrame, world_product: pd.DataFrame) -> pd.DataFrame:
    product_ids = pd.concat(
        [country_product[["product_id"]], world_product[["product_id"]]],
        ignore_index=True,
    ).drop_duplicates("product_id")
    product_ids["cmd_code"] = product_id_to_cmd_code(product_ids["product_id"])
    labels = h0_product_labels()
    mapping = product_ids.merge(labels, on="cmd_code", how="left", validate="many_to_one")
    mapping["product_label"] = mapping["product_label"].fillna("HS1992 " + mapping["cmd_code"].astype(str))
    classified = mapping.apply(
        lambda row: cse.classify_primary_hs6(row["cmd_code"], row["product_label"]),
        axis=1,
        result_type="expand",
    )
    for col in ["primary_strict", "primary_broad", "primary_strict_rule", "primary_broad_rule"]:
        mapping[col] = classified[col]
    mapping["classification_code"] = tcp.LT_HGL_TARGET_REVISION
    return mapping[
        [
            "product_id",
            "classification_code",
            "cmd_code",
            "product_label",
            "primary_strict",
            "primary_broad",
            "primary_strict_rule",
            "primary_broad_rule",
        ]
    ].drop_duplicates("product_id")


def world_rank_frame(world_year: pd.DataFrame) -> pd.DataFrame:
    world = world_year[["product_id", "cmd_code", "product_label", "primary_broad", "world_product_exports"]].copy()
    world["world_product_exports"] = pd.to_numeric(world["world_product_exports"], errors="coerce").fillna(0.0)
    world = world[world["world_product_exports"] > 0].copy()
    world_total = float(world["world_product_exports"].sum())
    if world_total <= 0:
        raise RuntimeError("World product exports are empty for a year.")
    world["world_product_share"] = world["world_product_exports"] / world_total
    world["world_share_rank_percentile"] = world["world_product_share"].rank(method="average", pct=True)
    world = world.sort_values(["world_product_share", "product_id"], ascending=[False, True]).reset_index(drop=True)
    world["world_share_rank_desc"] = np.arange(1, len(world) + 1, dtype=int)
    for cutoff in TOP_WORLD_SHARE_CUTOFFS:
        col = top_cutoff_col(cutoff)
        top_n = max(1, int(math.ceil(cutoff * len(world))))
        world[col] = world["world_share_rank_desc"] <= top_n
    return world


def safe_spearman(x: pd.Series | np.ndarray, y: pd.Series | np.ndarray) -> float:
    x_arr = pd.to_numeric(pd.Series(x), errors="coerce")
    y_arr = pd.to_numeric(pd.Series(y), errors="coerce")
    valid = x_arr.notna() & y_arr.notna()
    x_arr = x_arr[valid]
    y_arr = y_arr[valid]
    if len(x_arr) < 2 or x_arr.nunique() < 2 or y_arr.nunique() < 2:
        return np.nan
    value = spearmanr(x_arr.to_numpy(dtype=float), y_arr.to_numpy(dtype=float), nan_policy="omit").correlation
    return float(value) if value is not None and np.isfinite(value) else np.nan


def apply_variant_filter(frame: pd.DataFrame, variant: str) -> pd.DataFrame:
    spec = VARIANT_SPECS[variant]
    if spec["exclude_primary_broad"]:
        return frame[~frame["primary_broad"].astype(bool)].copy()
    return frame.copy()


def compute_country_year_exposure(
    country_group: pd.DataFrame,
    world_year: pd.DataFrame,
    *,
    return_details: bool = False,
) -> tuple[dict[str, Any], pd.DataFrame]:
    keep_cols = ["product_id", "cmd_code", "product_label", "primary_broad", "trade_value"]
    country = country_group[keep_cols].copy()
    country["trade_value"] = pd.to_numeric(country["trade_value"], errors="coerce").fillna(0.0)
    country = country[country["trade_value"] > 0].copy()
    world = world_rank_frame(world_year)
    world_total = float(world["world_product_exports"].sum())
    country_total = float(country["trade_value"].sum())
    if country_total <= 0 or world_total <= 0:
        metrics = {
            "world_share_exposure": np.nan,
            "spearman_product_alignment": np.nan,
            "country_total_exports": country_total,
            "world_total_exports": world_total,
            "country_active_products": int(len(country)),
            "matched_world_products": 0,
            "missing_world_products": 0,
            "missing_world_product_export_share": 0.0,
            "product_alignment_n": 0,
            "world_active_products": int(len(world)),
            "metric_valid": False,
            "invalid_reason": "empty_country_or_world_total",
        }
        for cutoff in TOP_WORLD_SHARE_CUTOFFS:
            metrics[share_cutoff_col(cutoff)] = np.nan
        return metrics, pd.DataFrame()

    country = (
        country.groupby(["product_id", "cmd_code", "product_label", "primary_broad"], as_index=False)["trade_value"]
        .sum()
        .sort_values(["trade_value", "product_id"], ascending=[False, True])
        .reset_index(drop=True)
    )
    country["country_product_export_share"] = country["trade_value"] / country_total
    merged = country.merge(world, on=["product_id", "cmd_code", "product_label", "primary_broad"], how="left", validate="many_to_one")
    missing = merged["world_product_share"].isna()
    missing_share = float(merged.loc[missing, "country_product_export_share"].sum())
    valid = merged.loc[~missing].copy()
    valid["exposure_contribution"] = valid["country_product_export_share"] * valid["world_share_rank_percentile"]
    exposure = float(valid["exposure_contribution"].sum())
    product_alignment = safe_spearman(valid["country_product_export_share"], valid["world_product_share"])
    out: dict[str, Any] = {
        "world_share_exposure": exposure,
        "spearman_product_alignment": product_alignment,
        "country_total_exports": country_total,
        "world_total_exports": world_total,
        "country_active_products": int(len(country)),
        "matched_world_products": int(len(valid)),
        "missing_world_products": int(missing.sum()),
        "missing_world_product_export_share": missing_share,
        "product_alignment_n": int(len(valid)),
        "world_active_products": int(len(world)),
        "metric_valid": bool(missing_share <= 1e-10),
        "invalid_reason": "" if missing_share <= 1e-10 else "country_products_missing_from_world_basket",
    }
    for cutoff in TOP_WORLD_SHARE_CUTOFFS:
        indicator = top_cutoff_col(cutoff)
        out[share_cutoff_col(cutoff)] = float(valid.loc[valid[indicator], "country_product_export_share"].sum())
    details = pd.DataFrame()
    if return_details:
        details = valid[
            [
                "product_id",
                "cmd_code",
                "product_label",
                "primary_broad",
                "trade_value",
                "country_product_export_share",
                "world_product_exports",
                "world_product_share",
                "world_share_rank_percentile",
                "exposure_contribution",
            ]
        ].sort_values(
            ["exposure_contribution", "trade_value", "product_id"],
            ascending=[False, False, True],
        )
    return out, details


def prepare_world_frames(world_product: pd.DataFrame, variants: list[str]) -> dict[str, dict[int, pd.DataFrame]]:
    world_frames: dict[str, dict[int, pd.DataFrame]] = {}
    for variant in variants:
        filtered = apply_variant_filter(world_product, variant)
        world_frames[variant] = {
            int(year): group.reset_index(drop=True)
            for year, group in filtered.groupby("year", sort=True)
        }
    return world_frames


def build_top_contributor_rows(
    meta: dict[str, Any],
    baseline_detail: pd.DataFrame,
    nc_detail: pd.DataFrame,
) -> pd.DataFrame:
    detail_cols = [
        "product_id",
        "cmd_code",
        "product_label",
        "primary_broad",
        "trade_value",
        "country_product_export_share",
        "world_product_exports",
        "world_product_share",
        "world_share_rank_percentile",
        "exposure_contribution",
    ]
    base = baseline_detail.reindex(columns=detail_cols).copy()
    nc = nc_detail.reindex(columns=detail_cols).copy()
    if base.empty and nc.empty:
        return pd.DataFrame()
    rename_base = {
        "trade_value": "baseline_trade_value",
        "country_product_export_share": "baseline_country_share",
        "world_product_exports": "baseline_world_product_exports",
        "world_product_share": "baseline_world_product_share",
        "world_share_rank_percentile": "baseline_world_rank_percentile",
        "exposure_contribution": "baseline_exposure_contribution",
    }
    rename_nc = {
        "trade_value": "noncommodity_trade_value",
        "country_product_export_share": "noncommodity_country_share",
        "world_product_exports": "noncommodity_world_product_exports",
        "world_product_share": "noncommodity_world_product_share",
        "world_share_rank_percentile": "noncommodity_world_rank_percentile",
        "exposure_contribution": "noncommodity_exposure_contribution",
    }
    base = base.rename(columns=rename_base)
    nc = nc.rename(columns=rename_nc)
    merged = base.merge(
        nc,
        on=["product_id", "cmd_code", "product_label", "primary_broad"],
        how="outer",
        validate="one_to_one",
    )
    for col in rename_base.values():
        if col in merged.columns:
            merged[col] = pd.to_numeric(merged[col], errors="coerce").fillna(0.0)
    for col in rename_nc.values():
        if col in merged.columns:
            merged[col] = pd.to_numeric(merged[col], errors="coerce").fillna(0.0)
    merged["retained_in_noncommodity"] = merged["noncommodity_trade_value"] > 0
    merged["delta_exposure_contribution"] = (
        merged["noncommodity_exposure_contribution"] - merged["baseline_exposure_contribution"]
    )
    merged["abs_delta_exposure_contribution"] = merged["delta_exposure_contribution"].abs()
    merged = merged[merged["abs_delta_exposure_contribution"] > 0].copy()
    if merged.empty:
        return pd.DataFrame()
    merged["removed_in_noncommodity"] = ~merged["retained_in_noncommodity"]
    merged = merged.sort_values(
        [
            "removed_in_noncommodity",
            "abs_delta_exposure_contribution",
            "baseline_trade_value",
            "product_id",
        ],
        ascending=[False, False, False, True],
    ).head(TOP_DELTA_PRODUCTS)
    rows = []
    for rank, row in enumerate(merged.itertuples(index=False), start=1):
        rows.append(
            {
                "country": meta["country"],
                "iso3": meta["iso3"],
                "reporter_code": int(meta["reporter_code"]),
                "year": int(meta["year"]),
                "rank_abs_delta": rank,
                "product_id": row.product_id,
                "cmd_code": row.cmd_code,
                "product_label": row.product_label,
                "primary_broad": bool(row.primary_broad),
                "retained_in_noncommodity": bool(row.retained_in_noncommodity),
                "baseline_trade_value": float(row.baseline_trade_value),
                "noncommodity_trade_value": float(row.noncommodity_trade_value),
                "baseline_country_share": float(row.baseline_country_share),
                "noncommodity_country_share": float(row.noncommodity_country_share),
                "baseline_world_product_share": float(row.baseline_world_product_share),
                "noncommodity_world_product_share": float(row.noncommodity_world_product_share),
                "baseline_world_rank_percentile": float(row.baseline_world_rank_percentile),
                "noncommodity_world_rank_percentile": float(row.noncommodity_world_rank_percentile),
                "baseline_exposure_contribution": float(row.baseline_exposure_contribution),
                "noncommodity_exposure_contribution": float(row.noncommodity_exposure_contribution),
                "delta_exposure_contribution": float(row.delta_exposure_contribution),
                "abs_delta_exposure_contribution": float(row.abs_delta_exposure_contribution),
            }
        )
    return pd.DataFrame(rows)


def compute_exposure_outputs(
    country_product: pd.DataFrame,
    world_product: pd.DataFrame,
    country_panel: pd.DataFrame,
    variants: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    world_frames = prepare_world_frames(world_product, variants)
    meta = country_panel.set_index("reporter_code")[["country", "iso3"]].to_dict("index")
    rows: list[dict[str, Any]] = []
    removed_rows: list[dict[str, Any]] = []
    contributor_rows: list[pd.DataFrame] = []

    want_delta_detail = "baseline" in variants and "noncommodity_broad" in variants
    grouped = country_product.groupby(["reporter_code", "year"], sort=True)
    for (reporter_code, year), group in grouped:
        reporter_code = int(reporter_code)
        year = int(year)
        info = meta.get(reporter_code)
        if info is None:
            continue
        row_meta = {
            "country": info["country"],
            "iso3": info["iso3"],
            "reporter_code": reporter_code,
            "year": year,
            "flow": FLOW,
        }
        variant_rows: dict[str, dict[str, Any]] = {}
        variant_details: dict[str, pd.DataFrame] = {}
        for variant in variants:
            filtered_group = apply_variant_filter(group, variant)
            world_year = world_frames[variant].get(year)
            if world_year is None or world_year.empty:
                continue
            metrics, details = compute_country_year_exposure(
                filtered_group,
                world_year,
                return_details=want_delta_detail and variant in {"baseline", "noncommodity_broad"},
            )
            out_row = {
                **row_meta,
                "variant": variant,
                "variant_label": VARIANT_SPECS[variant]["label"],
                **metrics,
            }
            rows.append(out_row)
            variant_rows[variant] = out_row
            variant_details[variant] = details

        baseline_row = variant_rows.get("baseline")
        nc_row = variant_rows.get("noncommodity_broad")
        if baseline_row is not None and nc_row is not None:
            baseline_total = float(baseline_row["country_total_exports"])
            nc_total = float(nc_row["country_total_exports"])
            removed_value = baseline_total - nc_total
            removed_share = removed_value / baseline_total if baseline_total > 0 else np.nan
            removed_rows.append(
                {
                    **row_meta,
                    "baseline_total_exports": baseline_total,
                    "noncommodity_total_exports": nc_total,
                    "broad_primary_exports_removed": removed_value,
                    "broad_primary_share_removed": removed_share,
                    "baseline_active_products": int(baseline_row["country_active_products"]),
                    "noncommodity_active_products": int(nc_row["country_active_products"]),
                    "baseline_world_active_products": int(baseline_row["world_active_products"]),
                    "noncommodity_world_active_products": int(nc_row["world_active_products"]),
                    "delta_world_share_exposure": float(nc_row["world_share_exposure"]) - float(baseline_row["world_share_exposure"]),
                    "delta_spearman_product_alignment": float(nc_row["spearman_product_alignment"]) - float(baseline_row["spearman_product_alignment"])
                    if pd.notna(nc_row["spearman_product_alignment"]) and pd.notna(baseline_row["spearman_product_alignment"])
                    else np.nan,
                }
            )
            detail = build_top_contributor_rows(row_meta, variant_details.get("baseline", pd.DataFrame()), variant_details.get("noncommodity_broad", pd.DataFrame()))
            if not detail.empty:
                contributor_rows.append(detail)

    panel = pd.DataFrame(rows)
    if panel.empty:
        raise RuntimeError("World-large-product exposure panel has no rows.")
    duplicates = panel.duplicated(["reporter_code", "year", "flow", "variant"], keep=False)
    if duplicates.any():
        examples = panel.loc[duplicates, ["reporter_code", "year", "flow", "variant"]].head(10).to_dict("records")
        raise RuntimeError(f"Duplicate country-year-flow-variant exposure rows: {examples}")
    invalid = panel[
        ~panel["metric_valid"].astype(bool)
        & panel["invalid_reason"].astype(str).eq("country_products_missing_from_world_basket")
    ].copy()
    if not invalid.empty:
        examples = invalid[
            ["country", "iso3", "year", "variant", "missing_world_product_export_share", "invalid_reason"]
        ].head(10).to_dict("records")
        raise RuntimeError(f"Invalid inclusive world-basket exposure rows: {examples}")
    removed = pd.DataFrame(removed_rows).sort_values(["country", "year"]).reset_index(drop=True)
    contributors = (
        pd.concat(contributor_rows, ignore_index=True).sort_values(["country", "year", "rank_abs_delta"])
        if contributor_rows
        else pd.DataFrame()
    )
    return panel.sort_values(["country", "year", "variant"]).reset_index(drop=True), removed, contributors


def add_world_bank_controls(panel: pd.DataFrame, args: argparse.Namespace) -> tuple[pd.DataFrame, dict[str, Any]]:
    keys = panel[["iso3", "year"]].drop_duplicates().copy()
    controls = cse.load_or_fetch_world_bank_controls(
        sorted(keys["iso3"].dropna().unique().tolist()),
        keys,
        int(args.start_year),
        int(args.end_year),
        tcp.sample_processed_path("world_large_product_exposure_world_bank_controls.csv", args.country_sample),
        refresh=args.refresh_controls,
    )
    out = panel.merge(controls, on=["iso3", "year"], how="left", validate="many_to_one")
    out = cse.construct_population_size_variables(out)
    controls_complete = ~out[["gdp_current_usd", "population", "log_gdp_current_usd", "log_gdp_per_capita"]].isna().any(axis=1)
    missing = int((~controls_complete).sum())
    examples = []
    if missing:
        examples = out.loc[~controls_complete, ["country", "iso3", "year", "gdp_current_usd", "population"]].head(10).to_dict("records")
    out["controls_complete"] = controls_complete.astype(bool)
    complete_share = float(controls_complete.mean()) if len(out) else 0.0
    if complete_share < cse.MIN_CONTROL_COVERAGE:
        raise RuntimeError(f"Missing World Bank controls for {missing:,} exposure rows: {examples}")
    manifest = {
        "controls_cache": rel(tcp.sample_processed_path("world_large_product_exposure_world_bank_controls.csv", args.country_sample)),
        "control_source": "World Bank GDP current USD and population",
        "log_gdp_per_capita_formula": "log_gdp_current_usd - log_population",
        "controls_complete_rows": int(controls_complete.sum()),
        "controls_missing_rows": missing,
        "controls_complete_share": complete_share,
        "controls_missing_examples": examples,
    }
    return out, manifest


def year_rank_correlations(panel: pd.DataFrame, sample_window: str = "all_available") -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    outcomes = [
        ("world_share_exposure", "World-share percentile exposure"),
        ("spearman_product_alignment", "Within-country product-rank alignment"),
        *[(share_cutoff_col(cutoff), f"Export share in top {int(cutoff * 100)}% world products") for cutoff in TOP_WORLD_SHARE_CUTOFFS],
    ]
    for (variant, variant_label, year), group in panel.groupby(["variant", "variant_label", "year"], sort=True):
        for outcome, label in outcomes:
            rows.append(
                {
                    "sample_window": sample_window,
                    "variant": variant,
                    "variant_label": variant_label,
                    "year": int(year),
                    "outcome": outcome,
                    "outcome_label": label,
                    "size_variable": "log_gdp_current_usd",
                    "size_label": "GDP, current USD",
                    "spearman_size_outcome": safe_spearman(group["log_gdp_current_usd"], group[outcome]),
                    "n_countries": int(group[["log_gdp_current_usd", outcome]].dropna().shape[0]),
                }
            )
            rows.append(
                {
                    "sample_window": sample_window,
                    "variant": variant,
                    "variant_label": variant_label,
                    "year": int(year),
                    "outcome": outcome,
                    "outcome_label": label,
                    "size_variable": "log_population",
                    "size_label": "Population",
                    "spearman_size_outcome": safe_spearman(group["log_population"], group[outcome]),
                    "n_countries": int(group[["log_population", outcome]].dropna().shape[0]),
                }
            )
    return pd.DataFrame(rows)


def summarize_year_rank_correlations(yearly: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    group_cols = ["sample_window", "variant", "variant_label", "outcome", "outcome_label", "size_variable", "size_label"]
    for keys, group in yearly.groupby(group_cols, sort=True):
        sample_window, variant, variant_label, outcome, outcome_label, size_variable, size_label = keys
        values = pd.to_numeric(group["spearman_size_outcome"], errors="coerce").dropna()
        rows.append(
            {
                "sample_window": sample_window,
                "variant": variant,
                "variant_label": variant_label,
                "outcome": outcome,
                "outcome_label": outcome_label,
                "size_variable": size_variable,
                "size_label": size_label,
                "years": int(len(values)),
                "mean_spearman": float(values.mean()) if len(values) else np.nan,
                "median_spearman": float(values.median()) if len(values) else np.nan,
                "min_spearman": float(values.min()) if len(values) else np.nan,
                "max_spearman": float(values.max()) if len(values) else np.nan,
                "share_positive": float((values > 0).mean()) if len(values) else np.nan,
            }
        )
    return pd.DataFrame(rows)


def run_models(panel: pd.DataFrame, country_sample: str) -> pd.DataFrame:
    outcomes = [
        ("world_share_exposure", "exposure"),
        ("spearman_product_alignment", "product_alignment"),
        *[(share_cutoff_col(cutoff), f"top_{int(cutoff * 100)}pct_world_product_share") for cutoff in TOP_WORLD_SHARE_CUTOFFS],
    ]
    frames: list[pd.DataFrame] = []
    for variant, variant_panel in panel.groupby("variant", sort=True):
        results: list[cse.ModelResult] = []
        for outcome, metric in outcomes:
            results.append(
                cse.run_ols_model(
                    variant_panel,
                    outcome=outcome,
                    terms=["log_gdp_current_usd"],
                    fixed_effects=["year"],
                    model_label="main_gdp_year_fe",
                    sample=country_sample,
                    flow=FLOW,
                    dimension="product",
                    metric=metric,
                    cluster_col="reporter_code",
                )
            )
            results.append(
                cse.run_ols_model(
                    variant_panel,
                    outcome=outcome,
                    terms=["log_gdp_current_usd", "log_gdp_per_capita"],
                    fixed_effects=["year"],
                    model_label="conditional_gdp_gdppc_year_fe",
                    sample=country_sample,
                    flow=FLOW,
                    dimension="product",
                    metric=metric,
                    cluster_col="reporter_code",
                )
            )
            results.append(
                cse.run_ols_model(
                    variant_panel,
                    outcome=outcome,
                    terms=["log_population"],
                    fixed_effects=["year"],
                    model_label="population_robustness_year_fe",
                    sample=country_sample,
                    flow=FLOW,
                    dimension="product",
                    metric=metric,
                    cluster_col="reporter_code",
                )
            )
        frame = cse.model_results_to_frame(results)
        frame["variant"] = variant
        frame["variant_label"] = VARIANT_SPECS[variant]["label"]
        frame["bh_q_value"] = np.nan
        for label in ["main_gdp_year_fe", "conditional_gdp_gdppc_year_fe", "population_robustness_year_fe"]:
            mask = frame["model_label"].eq(label) & frame["status"].eq("ok")
            frame.loc[mask, "bh_q_value"] = cse.benjamini_hochberg(frame.loc[mask, "p_value"])
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def fixed_country_window_codes(panel: pd.DataFrame, variants: list[str], start_year: int, end_year: int) -> list[int]:
    window_years = end_year - start_year + 1
    work = panel[
        panel["year"].between(start_year, end_year)
        & panel["metric_valid"].astype(bool)
    ].copy()
    coverage = (
        work.groupby(["reporter_code", "variant"], as_index=False)["year"]
        .nunique()
        .rename(columns={"year": "year_count"})
    )
    eligible = coverage[coverage["year_count"].eq(window_years)]
    counts = eligible.groupby("reporter_code")["variant"].nunique()
    codes = counts[counts.eq(len(variants))].index.tolist()
    return sorted(int(code) for code in codes)


def build_fixed_country_robustness(panel: pd.DataFrame, variants: list[str]) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    start_year, end_year = FIXED_COUNTRY_WINDOW
    codes = fixed_country_window_codes(panel, variants, start_year, end_year)
    fixed_panel = panel[
        panel["reporter_code"].isin(codes)
        & panel["year"].between(start_year, end_year)
    ].copy()
    yearly = year_rank_correlations(fixed_panel, sample_window="fixed_country_2018_2024")
    summary = summarize_year_rank_correlations(yearly)
    meta = {
        "fixed_country_window_start": start_year,
        "fixed_country_window_end": end_year,
        "fixed_country_count": len(codes),
        "fixed_country_codes": codes,
    }
    return yearly, summary, meta


def leave_one_country_out_diagnostics(panel: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    meta = panel[["reporter_code", "country", "iso3"]].drop_duplicates().sort_values(["country", "iso3"])
    for variant, variant_panel in panel.groupby("variant", sort=True):
        for outcome, label in [
            ("world_share_exposure", "World-share percentile exposure"),
            ("spearman_product_alignment", "Within-country product-rank alignment"),
        ]:
            for entry in meta.itertuples(index=False):
                sub = variant_panel[variant_panel["reporter_code"].ne(int(entry.reporter_code))].copy()
                yearly_vals: list[float] = []
                year_ns: list[int] = []
                for _year, group in sub.groupby("year", sort=True):
                    valid = group[["log_gdp_current_usd", outcome]].dropna()
                    year_ns.append(int(len(valid)))
                    corr = safe_spearman(valid["log_gdp_current_usd"], valid[outcome])
                    if pd.notna(corr):
                        yearly_vals.append(float(corr))
                values = pd.Series(yearly_vals, dtype=float)
                rows.append(
                    {
                        "variant": variant,
                        "variant_label": VARIANT_SPECS[variant]["label"],
                        "outcome": outcome,
                        "outcome_label": label,
                        "excluded_reporter_code": int(entry.reporter_code),
                        "excluded_country": entry.country,
                        "excluded_iso3": entry.iso3,
                        "years": int(values.notna().sum()),
                        "mean_spearman": float(values.mean()) if not values.empty else np.nan,
                        "median_spearman": float(values.median()) if not values.empty else np.nan,
                        "min_spearman": float(values.min()) if not values.empty else np.nan,
                        "max_spearman": float(values.max()) if not values.empty else np.nan,
                        "share_positive": float((values > 0).mean()) if not values.empty else np.nan,
                        "min_year_countries": int(min(year_ns)) if year_ns else 0,
                        "max_year_countries": int(max(year_ns)) if year_ns else 0,
                    }
                )
    return pd.DataFrame(rows)


def reporter_coverage(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (variant, variant_label, year), group in panel.groupby(["variant", "variant_label", "year"], sort=True):
        rows.append(
            {
                "variant": variant,
                "variant_label": variant_label,
                "year": int(year),
                "countries": int(group["reporter_code"].nunique()),
                "countries_with_exposure": int(group["world_share_exposure"].notna().sum()),
                "countries_with_alignment": int(group["spearman_product_alignment"].notna().sum()),
                "median_total_exports": float(pd.to_numeric(group["country_total_exports"], errors="coerce").median()),
                "median_active_products": float(pd.to_numeric(group["country_active_products"], errors="coerce").median()),
            }
        )
    return pd.DataFrame(rows)


def variant_comparison(yearly: pd.DataFrame) -> pd.DataFrame:
    gdp = yearly[yearly["size_variable"].eq("log_gdp_current_usd")].copy()
    if gdp.empty:
        return pd.DataFrame()
    wide = gdp.pivot_table(
        index=["sample_window", "year", "outcome", "outcome_label"],
        columns="variant",
        values=["spearman_size_outcome", "n_countries"],
        aggfunc="first",
    )
    wide.columns = ["_".join(str(part) for part in col if part) for col in wide.columns.to_flat_index()]
    wide = wide.reset_index()
    if {"spearman_size_outcome_baseline", "spearman_size_outcome_noncommodity_broad"}.issubset(wide.columns):
        wide["delta_noncommodity_minus_baseline"] = (
            pd.to_numeric(wide["spearman_size_outcome_noncommodity_broad"], errors="coerce")
            - pd.to_numeric(wide["spearman_size_outcome_baseline"], errors="coerce")
        )
    return wide.sort_values(["sample_window", "outcome", "year"]).reset_index(drop=True)


def plot_gdp_product_alignment_scatter(panel: pd.DataFrame, path: Path) -> dict[str, Any]:
    plot_data = panel[
        panel["variant"].eq("baseline")
        & panel["flow"].eq(FLOW)
    ].dropna(subset=["log_gdp_current_usd", "spearman_product_alignment"]).copy()
    if plot_data.empty:
        raise RuntimeError("Cannot plot GDP-product alignment scatter: no valid rows.")
    latest_year = int(plot_data["year"].max())
    plot_data = plot_data[plot_data["year"].eq(latest_year)].copy()
    if len(plot_data) < 3:
        raise RuntimeError(f"Cannot plot GDP-product alignment scatter: only {len(plot_data)} rows in {latest_year}.")

    x = plot_data["log_gdp_current_usd"].astype(float).to_numpy()
    y = plot_data["spearman_product_alignment"].astype(float).to_numpy()
    slope, intercept = np.polyfit(x, y, 1)
    fitted = intercept + slope * x
    sst = float(((y - y.mean()) ** 2).sum())
    sse = float(((y - fitted) ** 2).sum())
    r_squared = 1.0 - sse / sst if sst > 0 else np.nan

    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9.2, 6.2))
    ax.scatter(
        plot_data["log_gdp_current_usd"],
        plot_data["spearman_product_alignment"],
        s=42,
        color="#2f6f73",
        alpha=0.74,
        edgecolor="white",
        linewidth=0.55,
    )
    x_line = np.linspace(float(x.min()), float(x.max()), 100)
    ax.plot(x_line, intercept + slope * x_line, color="#b23a2f", linewidth=2.4)

    for _, row in plot_data.nlargest(6, "log_gdp_current_usd").iterrows():
        ax.annotate(
            str(row["iso3"]),
            (float(row["log_gdp_current_usd"]), float(row["spearman_product_alignment"])),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=8.5,
            color="#253238",
        )

    ax.text(
        0.03,
        0.97,
        f"{latest_year} cross-section\nN = {len(plot_data)} countries\nSlope = {slope:.3f}\nR² = {r_squared:.3f}",
        transform=ax.transAxes,
        va="top",
        ha="left",
        fontsize=10,
        bbox={"facecolor": "white", "edgecolor": "#d6dedc", "boxstyle": "round,pad=0.45", "alpha": 0.94},
    )
    ax.set_title("GDP and product alignment in the latest year", loc="left", fontsize=14, weight="bold")
    ax.set_xlabel("Log GDP, current USD")
    ax.set_ylabel("Within-country product-rank alignment")
    ax.set_ylim(-0.10, 1.02)
    ax.grid(axis="both", color="#e7eceb", linewidth=0.8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#87918f")
    ax.spines["bottom"].set_color("#87918f")
    fig.text(
        0.01,
        0.01,
        "Each point is one country. Alignment is a within-country Spearman correlation across active harmonized export products; HS6 999999 excluded.",
        fontsize=8.5,
        color="#5b6462",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return {
        "figure_year": latest_year,
        "figure_countries": int(len(plot_data)),
        "figure_slope": float(slope),
        "figure_r_squared": float(r_squared),
        "figure_path": rel(path),
    }


def format_num(value: object, digits: int = 3) -> str:
    try:
        val = float(value)
    except (TypeError, ValueError):
        return ""
    if not np.isfinite(val):
        return ""
    return f"{val:.{digits}f}"


def build_validation_checks(
    panel: pd.DataFrame,
    product_mapping: pd.DataFrame,
    country_panel: pd.DataFrame,
    country_product: pd.DataFrame,
    world_product: pd.DataFrame,
    coverage: pd.DataFrame,
    fixed_meta: dict[str, Any],
    input_manifest: dict[str, Any],
    control_manifest: dict[str, Any],
    variants: list[str],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    def add(check: str, passed: bool, value: object, expected: object, detail: str) -> None:
        rows.append(
            {
                "check": check,
                "passed": bool(passed),
                "value": value,
                "expected": expected,
                "detail": detail,
            }
        )

    expected_reporters = int(len(country_panel))
    add(
        "expected_reporters",
        panel["reporter_code"].nunique() == expected_reporters,
        int(panel["reporter_code"].nunique()),
        expected_reporters,
        "Unique reporters represented in the final panel.",
    )
    add(
        "year_min",
        int(panel["year"].min()) == START_YEAR,
        int(panel["year"].min()),
        START_YEAR,
        "Minimum panel year.",
    )
    add(
        "year_max",
        int(panel["year"].max()) == END_YEAR,
        int(panel["year"].max()),
        END_YEAR,
        "Maximum panel year.",
    )
    add(
        "unique_reporter_year_variant_keys",
        not panel.duplicated(["reporter_code", "year", "variant"]).any(),
        int(panel.duplicated(["reporter_code", "year", "variant"]).sum()),
        0,
        "Duplicate reporter-year-variant keys.",
    )
    add(
        "no_country_product_999999",
        not country_product["product_id"].astype(str).str.contains("999999", regex=False, na=False).any(),
        int(country_product["product_id"].astype(str).str.contains("999999", regex=False, na=False).sum()),
        0,
        "Country product input should already exclude HS6 999999 before aggregation.",
    )
    add(
        "no_world_product_999999",
        not world_product["product_id"].astype(str).str.contains("999999", regex=False, na=False).any(),
        int(world_product["product_id"].astype(str).str.contains("999999", regex=False, na=False).sum()),
        0,
        "World product input should already exclude HS6 999999 before aggregation.",
    )
    add(
        "hs1992_labels_present",
        product_mapping["product_label"].astype(str).str.len().gt(0).all(),
        int(product_mapping["product_label"].astype(str).str.len().eq(0).sum()),
        0,
        "All harmonized products should have plain-English HS1992/H0 labels.",
    )
    add(
        "exposure_in_unit_interval",
        pd.to_numeric(panel["world_share_exposure"], errors="coerce").dropna().between(0, 1).all(),
        int((~pd.to_numeric(panel["world_share_exposure"], errors="coerce").dropna().between(0, 1)).sum()),
        0,
        "Exposure must stay in [0,1].",
    )
    alignment = pd.to_numeric(panel["spearman_product_alignment"], errors="coerce")
    add(
        "alignment_in_closed_interval",
        alignment.dropna().between(-1, 1).all(),
        int((~alignment.dropna().between(-1, 1)).sum()),
        0,
        "Within-country alignment must stay in [-1,1].",
    )
    add(
        "zero_unmatched_country_share",
        float(pd.to_numeric(panel["missing_world_product_export_share"], errors="coerce").max()) <= 1e-10,
        float(pd.to_numeric(panel["missing_world_product_export_share"], errors="coerce").max()),
        0.0,
        "Country product baskets must match the filtered world basket exactly.",
    )
    if "noncommodity_broad" in variants:
        nc_products = apply_variant_filter(country_product, "noncommodity_broad")
        nc_world = apply_variant_filter(world_product, "noncommodity_broad")
        add(
            "noncommodity_country_has_no_primary_broad",
            not nc_products["primary_broad"].astype(bool).any(),
            int(nc_products["primary_broad"].astype(bool).sum()),
            0,
            "No broad-primary product should remain in the non-commodity country basket.",
        )
        add(
            "noncommodity_world_has_no_primary_broad",
            not nc_world["primary_broad"].astype(bool).any(),
            int(nc_world["primary_broad"].astype(bool).sum()),
            0,
            "No broad-primary product should remain in the non-commodity world basket.",
        )
    if input_manifest.get("country_conversion_diagnostics"):
        diag = input_manifest["country_conversion_diagnostics"]
        add(
            "country_conversion_value_conserved",
            abs(float(diag["conversion_value_residual"])) <= float(diag["conversion_value_residual_tolerance"]),
            float(diag["conversion_value_residual"]),
            0.0,
            "Cadot weighted HS1992 conversion should conserve filtered source export value.",
        )
    if input_manifest.get("benchmark_conversion_diagnostics"):
        diag = input_manifest["benchmark_conversion_diagnostics"]
        add(
            "benchmark_conversion_value_conserved",
            abs(float(diag["conversion_value_residual"])) <= float(diag["conversion_value_residual_tolerance"]),
            float(diag["conversion_value_residual"]),
            0.0,
            "world_broad weighted HS1992 conversion should conserve filtered source export value.",
        )
    if not coverage.empty:
        if "noncommodity_broad" in set(coverage["variant"]):
            nc_years = coverage[coverage["variant"].eq("noncommodity_broad")]
            add(
                "noncommodity_years_covered",
                int(nc_years["year"].min()) == START_YEAR and int(nc_years["year"].max()) == END_YEAR,
                f"{int(nc_years['year'].min())}-{int(nc_years['year'].max())}",
                f"{START_YEAR}-{END_YEAR}",
                "Non-commodity yearly coverage window.",
            )
    add(
        "fixed_country_window_nonempty",
        int(fixed_meta["fixed_country_count"]) > 0,
        int(fixed_meta["fixed_country_count"]),
        ">0",
        "Countries observed in every year from 2018 through 2024 for every requested variant.",
    )
    if control_manifest:
        add(
            "world_bank_control_row_coverage",
            float(control_manifest.get("controls_complete_share", 0.0)) >= cse.MIN_CONTROL_COVERAGE,
            float(control_manifest.get("controls_complete_share", 0.0)),
            cse.MIN_CONTROL_COVERAGE,
            "Share of final panel rows with complete GDP and population controls.",
        )
    return pd.DataFrame(rows)


def write_memo(
    panel: pd.DataFrame,
    yearly: pd.DataFrame,
    yearly_summary: pd.DataFrame,
    models: pd.DataFrame,
    coverage: pd.DataFrame,
    fixed_yearly: pd.DataFrame,
    fixed_summary: pd.DataFrame,
    removed: pd.DataFrame,
    validation: pd.DataFrame,
    manifest: dict[str, Any],
    paths: dict[str, Path],
) -> None:
    gdp_yearly = yearly[
        yearly["size_variable"].eq("log_gdp_current_usd")
        & yearly["outcome"].isin(SUMMARY_OUTCOMES)
    ].copy()
    headline_lines = []
    for variant, label in [(variant, VARIANT_SPECS[variant]["label"]) for variant in manifest["variants"]]:
        for outcome in SUMMARY_OUTCOMES:
            summary = yearly_summary[
                yearly_summary["sample_window"].eq("all_available")
                & yearly_summary["variant"].eq(variant)
                & yearly_summary["outcome"].eq(outcome)
                & yearly_summary["size_variable"].eq("log_gdp_current_usd")
            ]
            if summary.empty:
                continue
            row = summary.iloc[0]
            headline_lines.append(
                f"- {label}, {outcome}: mean Spearman {format_num(row['mean_spearman'])}, "
                f"median {format_num(row['median_spearman'])}, positive in {format_num(row['share_positive'])} of years."
            )

    model_rows = models[
        models["model_label"].eq("main_gdp_year_fe")
        & models["term"].eq("log_gdp_current_usd")
        & models["outcome"].isin(SUMMARY_OUTCOMES)
    ][
        [
            "variant",
            "outcome",
            "coefficient",
            "std_error",
            "p_value",
            "bh_q_value",
            "nobs",
            "clusters",
            "status",
        ]
    ]

    lines = [
        "# Cadot 156 World-Product Exposure",
        "",
        f"Generated: {now_utc()}",
        "",
        "## Purpose",
        "",
        "This file compares two export-only measures against GDP size in the Cadot-style 156-country sample, 2000-2024.",
        "",
        "1. `world_share_exposure`: country export shares weighted by inclusive world product-share rank percentiles.",
        "2. `spearman_product_alignment`: within-country Spearman correlation between country export shares and same-year world export shares across the country's active products.",
        "",
        "The baseline uses the full harmonized export basket. The non-commodity variant removes broad primary products from both country and world baskets, renormalizes shares, and rebuilds world product ranks in the filtered universe.",
        "",
        "## Construction",
        "",
        "- Country basket: LT/HGL-weighted HS1992/H0 export products built from Comtrade final annual raw files.",
        "- Country sample: `cadot_broad_156` when requested; default script behavior remains `rd2_countries` baseline only.",
        "- Benchmark sample: `world_broad`, inclusive same-year export totals.",
        "- Product exclusion: HS6 `999999` is excluded before product-dependent aggregation.",
        "- Broad-primary rule: `run_country_size_effect.classify_primary_hs6` applied to harmonized HS1992/H0 product codes and official H0 labels.",
        "",
        "### Formulas",
        "",
        "- Baseline exposure: `E_ct = sum_p s_cpt * R_pt`, where `R_pt` is the inclusive world product-share rank percentile.",
        "- Non-commodity exposure: `E_ct^NC = sum_{p in NC} s_cpt^NC * R_pt^NC`.",
        "- Non-commodity alignment: `A_ct^NC = rho_p(s_cpt^NC, w_pt^NC)` across the country's active non-commodity products.",
        "",
        "In plain English, higher exposure means a country's export basket leans more toward products that are large in world trade. Higher alignment means the country's biggest exported products line up more closely with the products that are globally large.",
        "",
        "## Headline Results",
        "",
        *headline_lines,
        "",
        "## Main GDP Year-FE Rows",
        "",
        model_rows.to_markdown(index=False),
        "",
        "## All-Available GDP Rank-Correlation Summary",
        "",
        gdp_yearly[
            ["sample_window", "variant", "year", "outcome", "spearman_size_outcome", "n_countries"]
        ].to_markdown(index=False),
        "",
        "## Fixed-Country 2018-2024 GDP Summary",
        "",
        fixed_summary[
            fixed_summary["size_variable"].eq("log_gdp_current_usd")
            & fixed_summary["outcome"].isin(SUMMARY_OUTCOMES)
        ].to_markdown(index=False),
        "",
        "## Coverage And Removed Share",
        "",
        coverage.to_markdown(index=False),
        "",
        removed.head(40).to_markdown(index=False) if not removed.empty else "No baseline-versus-noncommodity removed-share rows were produced.",
        "",
        "## Validation Checks",
        "",
        validation.to_markdown(index=False),
        "",
        "## Outputs",
        "",
    ]
    for label, path in paths.items():
        lines.append(f"- {label}: `{rel(path)}`")
    lines.extend(["", "## Manifest", "", "```json", json.dumps(manifest, indent=2, sort_keys=True), "```"])
    paths["memo"].write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> dict[str, Path]:
    variants = resolve_variants(args.country_sample, args.variants)
    out_dir = output_dir(args.country_sample)
    processed_dir = tcp.sample_processed_dir(args.country_sample)
    out_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    country_panel = load_country_panel(args.country_sample, args.start_year, args.end_year)
    country_product, world_product, input_manifest = build_or_load_product_inputs(args)
    product_mapping = build_harmonized_product_mapping(country_product, world_product)
    country_product = country_product.merge(product_mapping, on="product_id", how="left", validate="many_to_one")
    world_product = world_product.merge(product_mapping, on="product_id", how="left", validate="many_to_one")

    panel, removed, contributors = compute_exposure_outputs(country_product, world_product, country_panel, variants)
    panel, control_manifest = add_world_bank_controls(panel, args)
    coverage = reporter_coverage(panel)
    yearly = year_rank_correlations(panel)
    yearly_summary = summarize_year_rank_correlations(yearly)
    models = run_models(panel, args.country_sample)
    fixed_yearly, fixed_summary, fixed_meta = build_fixed_country_robustness(panel, variants)
    loo = leave_one_country_out_diagnostics(panel)
    comparison = variant_comparison(pd.concat([yearly, fixed_yearly], ignore_index=True))
    figure_path = alignment_scatter_path(args.country_sample)
    figure_stats = plot_gdp_product_alignment_scatter(panel, figure_path)
    validation = build_validation_checks(
        panel=panel,
        product_mapping=product_mapping,
        country_panel=country_panel,
        country_product=country_product,
        world_product=world_product,
        coverage=coverage,
        fixed_meta=fixed_meta,
        input_manifest=input_manifest,
        control_manifest=control_manifest,
        variants=variants,
    )

    diagnostics = pd.DataFrame(
        [
            {"diagnostic": "country_year_variant_rows", "value": int(len(panel)), "detail": ""},
            {"diagnostic": "countries", "value": int(panel["reporter_code"].nunique()), "detail": ""},
            {"diagnostic": "variants", "value": len(variants), "detail": ",".join(variants)},
            {"diagnostic": "year_min", "value": int(panel["year"].min()), "detail": ""},
            {"diagnostic": "year_max", "value": int(panel["year"].max()), "detail": ""},
            {"diagnostic": "invalid_metric_rows", "value": int((~panel["metric_valid"].astype(bool)).sum()), "detail": ""},
            {
                "diagnostic": "max_missing_world_product_export_share",
                "value": float(panel["missing_world_product_export_share"].max()),
                "detail": "",
            },
            {"diagnostic": "product_999999_policy", "value": 0, "detail": "excluded upstream before product aggregation"},
            {"diagnostic": "world_basket_policy", "value": 1, "detail": "inclusive world_broad exports; no leave-one-out subtraction"},
            {"diagnostic": "fixed_country_window_start", "value": fixed_meta["fixed_country_window_start"], "detail": ""},
            {"diagnostic": "fixed_country_window_end", "value": fixed_meta["fixed_country_window_end"], "detail": ""},
            {"diagnostic": "fixed_country_count", "value": fixed_meta["fixed_country_count"], "detail": ""},
            {"diagnostic": "gdp_alignment_scatter_year", "value": figure_stats["figure_year"], "detail": ""},
            {"diagnostic": "gdp_alignment_scatter_countries", "value": figure_stats["figure_countries"], "detail": ""},
            {"diagnostic": "gdp_alignment_scatter_slope", "value": figure_stats["figure_slope"], "detail": "OLS slope in latest-year scatter"},
            {"diagnostic": "gdp_alignment_scatter_r_squared", "value": figure_stats["figure_r_squared"], "detail": "OLS R-squared in latest-year scatter"},
        ]
    )

    panel_path = processed_panel_path(args.country_sample)
    panel_csv = out_dir / "world_large_product_exposure_panel.csv"
    yearly_path = out_dir / "world_large_product_exposure_yearly_spearman.csv"
    yearly_summary_path = out_dir / "world_large_product_exposure_spearman_summary.csv"
    models_path = out_dir / "world_large_product_exposure_models.csv"
    diagnostics_path = out_dir / "world_large_product_exposure_diagnostics.csv"
    validation_path = out_dir / "world_large_product_exposure_validation_checks.csv"
    coverage_path = out_dir / "world_large_product_exposure_reporter_coverage.csv"
    fixed_yearly_path = out_dir / "world_large_product_exposure_fixed_country_2018_2024.csv"
    fixed_summary_path = out_dir / "world_large_product_exposure_fixed_country_2018_2024_summary.csv"
    loo_path = out_dir / "world_large_product_exposure_leave_one_country_out.csv"
    comparison_path = out_dir / "world_large_product_exposure_variant_comparison.csv"
    removed_path = out_dir / "world_large_product_exposure_country_commodity_shares.csv"
    contributors_path = out_dir / "world_large_product_exposure_top_change_contributors.csv"
    product_mapping_path = out_dir / "world_large_product_exposure_product_mapping.csv"
    manifest_path = out_dir / "run_manifest_world_large_product_exposure.json"
    memo_path = out_dir / "world_large_product_exposure.md"

    panel.to_parquet(panel_path, index=False)
    panel.to_csv(panel_csv, index=False)
    yearly.to_csv(yearly_path, index=False)
    yearly_summary.to_csv(yearly_summary_path, index=False)
    models.to_csv(models_path, index=False)
    diagnostics.to_csv(diagnostics_path, index=False)
    validation.to_csv(validation_path, index=False)
    coverage.to_csv(coverage_path, index=False)
    fixed_yearly.to_csv(fixed_yearly_path, index=False)
    fixed_summary.to_csv(fixed_summary_path, index=False)
    loo.to_csv(loo_path, index=False)
    comparison.to_csv(comparison_path, index=False)
    removed.to_csv(removed_path, index=False)
    contributors.to_csv(contributors_path, index=False)
    product_mapping.to_csv(product_mapping_path, index=False)

    manifest = {
        "created_at_utc": now_utc(),
        "country_sample": args.country_sample,
        "benchmark_sample": args.benchmark_sample,
        "flow": FLOW,
        "product_id_mode": PRODUCT_ID_MODE,
        "start_year": int(args.start_year),
        "end_year": int(args.end_year),
        "variants": variants,
        "variant_labels": {variant: VARIANT_SPECS[variant]["label"] for variant in variants},
        "world_basket": "inclusive_world_exports",
        "leave_one_out": False,
        "size_variable_headline": "log_gdp_current_usd",
        "alignment_definition": "Within-country Spearman correlation across active harmonized export products only.",
        "controls": control_manifest,
        "product_inputs": input_manifest,
        "primary_classifier": {
            "source_function": "run_country_size_effect.classify_primary_hs6",
            "classification_code": tcp.LT_HGL_TARGET_REVISION,
            "label_source": rel(ROOT / "data/raw/classifications/H0.json"),
            "definition": (
                "Broad primary includes raw agriculture, ores/minerals, fuels and refining, forestry, "
                "precious metals, and first-stage food/basic-metal processing."
            ),
        },
        "fixed_country_robustness": fixed_meta,
        "outputs": {
            "processed_panel": rel(panel_path),
            "panel_csv": rel(panel_csv),
            "yearly_spearman": rel(yearly_path),
            "spearman_summary": rel(yearly_summary_path),
            "models": rel(models_path),
            "diagnostics": rel(diagnostics_path),
            "validation_checks": rel(validation_path),
            "reporter_coverage": rel(coverage_path),
            "fixed_country_yearly": rel(fixed_yearly_path),
            "fixed_country_summary": rel(fixed_summary_path),
            "leave_one_country_out": rel(loo_path),
            "variant_comparison": rel(comparison_path),
            "country_commodity_shares": rel(removed_path),
            "top_change_contributors": rel(contributors_path),
            "product_mapping": rel(product_mapping_path),
            "memo": rel(memo_path),
            "gdp_product_alignment_scatter": rel(figure_path),
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    paths = {
        "processed_panel": panel_path,
        "panel_csv": panel_csv,
        "yearly_spearman": yearly_path,
        "spearman_summary": yearly_summary_path,
        "models": models_path,
        "diagnostics": diagnostics_path,
        "validation_checks": validation_path,
        "reporter_coverage": coverage_path,
        "fixed_country_yearly": fixed_yearly_path,
        "fixed_country_summary": fixed_summary_path,
        "leave_one_country_out": loo_path,
        "variant_comparison": comparison_path,
        "country_commodity_shares": removed_path,
        "top_change_contributors": contributors_path,
        "product_mapping": product_mapping_path,
        "manifest": manifest_path,
        "memo": memo_path,
        "gdp_product_alignment_scatter": figure_path,
    }
    write_memo(
        panel=panel,
        yearly=yearly,
        yearly_summary=yearly_summary,
        models=models,
        coverage=coverage,
        fixed_yearly=fixed_yearly,
        fixed_summary=fixed_summary,
        removed=removed,
        validation=validation,
        manifest=manifest,
        paths=paths,
    )
    return paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country-sample", default=DEFAULT_COUNTRY_SAMPLE, choices=SUPPORTED_COUNTRY_SAMPLES)
    parser.add_argument("--benchmark-sample", default=BENCHMARK_SAMPLE)
    parser.add_argument("--start-year", type=int, default=START_YEAR)
    parser.add_argument("--end-year", type=int, default=END_YEAR)
    parser.add_argument("--variants", nargs="+", choices=sorted(VARIANT_SPECS), default=None)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--download-workers", type=int, default=2)
    parser.add_argument("--chunk-rows", type=int, default=250_000)
    parser.add_argument("--max-files", type=int, default=None)
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--rebuild-product-inputs", action="store_true")
    parser.add_argument("--refresh-availability", action="store_true")
    parser.add_argument("--refresh-controls", action="store_true")
    parser.add_argument("--download-missing", action="store_true")
    parser.add_argument("--subscription-key", default="")
    parser.add_argument("--flow", default=FLOW, choices=[FLOW], help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> None:
    paths = run(parse_args())
    print(json.dumps({key: rel(path) for key, path in paths.items()}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
