#!/usr/bin/env python3
"""Compute fixed-universe Product Theil over harmonized HS6 product families.

This is the Theil counterpart to `run_fixed_universe_product_gini.py`.
It deliberately uses existing country-product and world-product aggregate
parquet files to avoid a memory-heavy raw Comtrade rebuild.
"""

from __future__ import annotations

import argparse
import json
import math
import re
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
from concentration_metrics import active_theil, theil_from_positive_values  # noqa: E402


COUNTRY_SAMPLE = "rd2_countries"
BENCHMARK_SAMPLE = "world_broad"
PRODUCT_ID_MODE = "harmonized_hs6_family"
FLOW_CHOICES = ("Exports", "Imports")
DEFAULT_START_YEAR = 2000
DEFAULT_END_YEAR = 2024
DEFAULT_REQUIRE_BALANCED_COUNTRIES = 55
RESULT_DIRNAME = "fixed_universe_product_theil_tables"
PANEL_FILENAME = "fixed_universe_product_theil_panel.parquet"
EXCLUDED_PRODUCT_RE = re.compile(r"999999")
RICH_PROXY_EXCLUDE = {"JPN", "KOR", "TWN"}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        if math.isnan(float(value)):
            return None
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def value_noun(flow: str) -> str:
    return "exports" if flow == "Exports" else "imports"


def flow_slug(flow: str) -> str:
    return "exports" if flow == "Exports" else "imports"


def world_value_column(flow: str) -> str:
    return f"world_product_{value_noun(flow)}"


def artifact_stem(flow: str) -> str:
    return "world_relative_product_gini" if flow == "Exports" else "world_relative_import_product_gini"


def source_paths(flow: str) -> dict[str, Path]:
    stem = artifact_stem(flow)
    noun = value_noun(flow)
    return {
        "country_product": tcp.sample_processed_dir(COUNTRY_SAMPLE)
        / f"{stem}_{PRODUCT_ID_MODE}_rd2_product_{noun}.parquet",
        "world_product": tcp.sample_processed_dir(BENCHMARK_SAMPLE)
        / f"{stem}_{PRODUCT_ID_MODE}_world_product_{noun}.parquet",
    }


def result_dir() -> Path:
    return tcp.sample_results_dir(COUNTRY_SAMPLE) / RESULT_DIRNAME


def processed_panel_path() -> Path:
    return tcp.sample_processed_dir(COUNTRY_SAMPLE) / PANEL_FILENAME


def assert_no_excluded_product_ids(frame: pd.DataFrame, label: str) -> None:
    if "product_id" not in frame.columns:
        raise RuntimeError(f"{label} is missing product_id.")
    product_ids = frame["product_id"].astype("string")
    bad = product_ids[product_ids.str.contains(EXCLUDED_PRODUCT_RE, na=False)].drop_duplicates().head(10).tolist()
    if bad:
        raise RuntimeError(f"{label} contains excluded HS6 999999-derived product IDs: {bad}")


def duplicate_key_count(frame: pd.DataFrame, keys: list[str]) -> int:
    return int(frame.duplicated(keys, keep=False).sum())


def read_country_panel() -> pd.DataFrame:
    path = tcp.sample_processed_dir(COUNTRY_SAMPLE) / "comtrade_country_panel.csv"
    if not path.exists():
        raise RuntimeError(f"Missing rd2 country panel: {path}")
    panel = pd.read_csv(path)
    required = {"country", "iso3", "reporter_code"}
    missing = required - set(panel.columns)
    if missing:
        raise RuntimeError(f"Country panel is missing columns: {sorted(missing)}")
    panel = panel[list(required)].copy()
    panel["reporter_code"] = panel["reporter_code"].astype(int)
    if panel["reporter_code"].duplicated().any():
        raise RuntimeError("rd2 country panel has duplicate reporter_code values.")
    if len(panel) != 60:
        raise RuntimeError(f"rd2 country panel must contain 60 reporters; found {len(panel)}.")
    return panel


def read_income_metadata() -> pd.DataFrame:
    candidates = [
        tcp.sample_processed_dir(COUNTRY_SAMPLE) / "future_growth_concentration_world_bank_controls.csv",
        ROOT / "data/raw/world_bank_gdp/country_metadata.csv",
    ]
    for path in candidates:
        if not path.exists():
            continue
        data = pd.read_csv(path)
        if not {"iso3", "region", "income_group"}.issubset(data.columns):
            continue
        keep = data[["iso3", "region", "income_group"]].copy()
        keep["iso3"] = keep["iso3"].astype(str).str.upper().str.strip()
        keep["region"] = keep["region"].fillna("").astype(str)
        keep["income_group"] = keep["income_group"].fillna("").astype(str)
        return keep.sort_values(["iso3"]).drop_duplicates("iso3", keep="last")
    return pd.DataFrame(columns=["iso3", "region", "income_group"])


def read_product_frame(path: Path, columns: list[str], label: str) -> pd.DataFrame:
    if not path.exists():
        raise RuntimeError(f"Missing {label} artifact: {path}")
    frame = pd.read_parquet(path, columns=columns)
    missing = set(columns) - set(frame.columns)
    if missing:
        raise RuntimeError(f"{label} is missing columns: {sorted(missing)}")
    frame["year"] = frame["year"].astype(int)
    frame["product_id"] = frame["product_id"].astype(str)
    assert_no_excluded_product_ids(frame, label)
    return frame


def build_product_universe(
    world_product: pd.DataFrame, world_col: str, start_year: int, end_year: int
) -> tuple[list[str], pd.DataFrame]:
    world = world_product[world_product["year"].between(start_year, end_year)].copy()
    world[world_col] = pd.to_numeric(world[world_col], errors="coerce").fillna(0.0)
    world = world[world[world_col] > 0].copy()
    if world.empty:
        raise RuntimeError("world_broad product support is empty after filtering.")
    product_universe = sorted(world["product_id"].drop_duplicates().tolist())
    year_counts = (
        world.groupby("year", as_index=False)
        .agg(world_active_products=("product_id", "nunique"), world_total_trade_value=(world_col, "sum"))
        .sort_values("year")
    )
    return product_universe, year_counts


def compute_world_relative_theil_for_group(
    group: pd.DataFrame,
    world_year: pd.DataFrame,
    world_col: str,
) -> dict[str, float]:
    country = group[["product_id", "trade_value"]].copy()
    country["trade_value"] = pd.to_numeric(country["trade_value"], errors="coerce").fillna(0.0)
    country_total = float(country["trade_value"].sum())
    world_total = float(pd.to_numeric(world_year[world_col], errors="coerce").fillna(0.0).sum())
    benchmark_total = world_total - country_total
    if country_total <= 0 or world_total <= 0 or benchmark_total <= 0:
        return {
            "world_relative_product_theil": np.nan,
            "zero_weight_country_trade_share": np.nan,
            "loo_world_total_trade_value": benchmark_total,
        }

    merged = country.merge(world_year[["product_id", world_col]], on="product_id", how="left")
    if merged[world_col].isna().any():
        missing = merged.loc[merged[world_col].isna(), "product_id"].drop_duplicates().head(10).tolist()
        raise RuntimeError(f"Country product values are missing from same-year world support: {missing}")
    merged[world_col] = pd.to_numeric(merged[world_col], errors="coerce").fillna(0.0)
    merged["loo_world_product_value"] = merged[world_col] - merged["trade_value"]
    small_negative = merged["loo_world_product_value"].between(-1e-6, 0)
    merged.loc[small_negative, "loo_world_product_value"] = 0.0
    if (merged["loo_world_product_value"] < 0).any():
        bad = merged.loc[merged["loo_world_product_value"] < 0, ["product_id", world_col, "trade_value"]].head(10)
        raise RuntimeError(f"Leave-one-out world product values are negative:\n{bad}")

    merged["country_share"] = merged["trade_value"] / country_total
    valid = merged["loo_world_product_value"] > 0
    zero_weight_share = float(merged.loc[~valid, "country_share"].sum())
    if zero_weight_share > 0:
        return {
            "world_relative_product_theil": np.nan,
            "zero_weight_country_trade_share": zero_weight_share,
            "loo_world_total_trade_value": benchmark_total,
        }
    benchmark_share = merged.loc[valid, "loo_world_product_value"].to_numpy(dtype=float) / benchmark_total
    country_share = merged.loc[valid, "country_share"].to_numpy(dtype=float)
    metric = float(np.sum(country_share * np.log(country_share / benchmark_share)))
    return {
        "world_relative_product_theil": metric,
        "zero_weight_country_trade_share": zero_weight_share,
        "loo_world_total_trade_value": benchmark_total,
    }


def compute_fixed_universe_metrics(
    group: pd.DataFrame,
    universe_set: set[str],
    universe_count: int,
    world_year: pd.DataFrame | None = None,
    world_col: str | None = None,
) -> dict[str, float | int]:
    products = group["product_id"].astype(str)
    outside = sorted(set(products) - universe_set)
    if outside:
        raise RuntimeError(f"Product values contain product IDs outside the fixed universe: {outside[:10]}")
    trade_values = pd.to_numeric(group["trade_value"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    if np.any(trade_values < 0):
        raise RuntimeError("Product trade values must be nonnegative.")
    positive = trade_values[trade_values > 0]
    total = float(positive.sum())
    active_count = int(positive.size)
    fixed_theil = theil_from_positive_values(positive, universe_count)
    fixed_theil_norm = theil_from_positive_values(positive, universe_count, normalized=True)
    active_product_theil = active_theil(positive)
    active_product_theil_norm = active_theil(positive, normalized=True)
    inactive_product_margin = math.log(universe_count / active_count) if active_count > 0 else np.nan
    fixed_denominator = math.log(universe_count) if universe_count > 1 else np.nan
    decomposition_residual = (
        fixed_theil - active_product_theil - inactive_product_margin
        if np.isfinite(fixed_theil) and np.isfinite(active_product_theil) and np.isfinite(inactive_product_margin)
        else np.nan
    )
    world_relative = {
        "world_relative_product_theil": np.nan,
        "zero_weight_country_trade_share": np.nan,
        "loo_world_total_trade_value": np.nan,
    }
    if world_year is not None and world_col is not None:
        world_relative = compute_world_relative_theil_for_group(group, world_year, world_col)
    return {
        "fixed_universe_product_theil": fixed_theil,
        "fixed_universe_product_theil_normalized": fixed_theil_norm,
        "active_product_theil": active_product_theil,
        "active_product_theil_normalized": active_product_theil_norm,
        "active_product_margin_theil": active_product_theil,
        "inactive_product_margin_theil": inactive_product_margin,
        "active_product_margin_theil_normalized_by_fixed_universe": active_product_theil / fixed_denominator
        if np.isfinite(active_product_theil) and np.isfinite(fixed_denominator)
        else np.nan,
        "inactive_product_margin_theil_normalized_by_fixed_universe": inactive_product_margin / fixed_denominator
        if np.isfinite(inactive_product_margin) and np.isfinite(fixed_denominator)
        else np.nan,
        "product_margin_decomposition_residual": decomposition_residual,
        "theil_extensive_gap": fixed_theil - active_product_theil
        if np.isfinite(fixed_theil) and np.isfinite(active_product_theil)
        else np.nan,
        "active_product_count": active_count,
        "universe_product_count": universe_count,
        "zero_product_count": universe_count - active_count,
        "active_product_share": active_count / universe_count if universe_count else np.nan,
        "total_trade_value": total,
        **world_relative,
    }


def compute_flow_panel(
    flow: str,
    country_panel: pd.DataFrame,
    income_metadata: pd.DataFrame,
    start_year: int,
    end_year: int,
) -> tuple[pd.DataFrame, dict[str, Any], pd.DataFrame]:
    paths = source_paths(flow)
    world_col = world_value_column(flow)
    country_product = read_product_frame(
        paths["country_product"],
        ["reporter_code", "year", "product_id", "trade_value"],
        f"{flow} rd2 product values",
    )
    world_product = read_product_frame(
        paths["world_product"],
        ["year", "product_id", world_col],
        f"{flow} world product values",
    )

    country_product = country_product[country_product["year"].between(start_year, end_year)].copy()
    world_product = world_product[world_product["year"].between(start_year, end_year)].copy()
    country_product["reporter_code"] = country_product["reporter_code"].astype(int)
    country_product["trade_value"] = pd.to_numeric(country_product["trade_value"], errors="coerce").fillna(0.0)
    country_product = country_product[country_product["trade_value"] > 0].copy()
    world_product[world_col] = pd.to_numeric(world_product[world_col], errors="coerce").fillna(0.0)
    world_product = world_product[world_product[world_col] > 0].copy()

    duplicate_country_keys = duplicate_key_count(country_product, ["reporter_code", "year", "product_id"])
    duplicate_world_keys = duplicate_key_count(world_product, ["year", "product_id"])
    if duplicate_country_keys:
        raise RuntimeError(f"{flow} country product artifact has duplicate reporter-year-product rows.")
    if duplicate_world_keys:
        raise RuntimeError(f"{flow} world product artifact has duplicate year-product rows.")

    product_universe, year_counts = build_product_universe(world_product, world_col, start_year, end_year)
    universe_set = set(product_universe)
    universe_count = len(product_universe)
    outside = sorted(set(country_product["product_id"]) - universe_set)
    if outside:
        raise RuntimeError(f"{flow} country product artifact contains products outside the fixed world_broad universe: {outside[:10]}")

    world_by_year = {
        int(year): frame[["product_id", world_col]].copy()
        for year, frame in world_product.groupby("year", sort=True)
    }
    meta = country_panel.merge(income_metadata, on="iso3", how="left")
    meta["region"] = meta["region"].fillna("").astype(str)
    meta["income_group"] = meta["income_group"].fillna("").astype(str)
    country_meta = meta.set_index("reporter_code")[["country", "iso3", "region", "income_group"]].to_dict("index")

    rows: list[dict[str, Any]] = []
    for (reporter_code, year), group in country_product.groupby(["reporter_code", "year"], sort=True):
        year = int(year)
        world_year = world_by_year.get(year)
        if world_year is None:
            raise RuntimeError(f"{flow} world support has no rows for year {year}.")
        metrics = compute_fixed_universe_metrics(group, universe_set, universe_count, world_year, world_col)
        meta_row = country_meta.get(
            int(reporter_code),
            {"country": str(reporter_code), "iso3": "", "region": "", "income_group": ""},
        )
        rows.append(
            {
                "country": meta_row["country"],
                "iso3": meta_row["iso3"],
                "reporter_code": int(reporter_code),
                "year": year,
                "flow": flow,
                "variant": "fixed_universe",
                "product_id_mode": PRODUCT_ID_MODE,
                **metrics,
                "region": meta_row["region"],
                "income_group": meta_row["income_group"],
            }
        )

    panel = pd.DataFrame(rows)
    if panel.empty:
        raise RuntimeError(f"{flow} fixed-universe Theil panel has no rows.")
    duplicate_panel_keys = duplicate_key_count(panel, ["reporter_code", "year", "flow"])
    if duplicate_panel_keys:
        raise RuntimeError(f"{flow} fixed-universe Theil panel has duplicate reporter-year-flow keys.")
    positive = panel["total_trade_value"] > 0
    if panel.loc[positive, "fixed_universe_product_theil"].isna().any():
        raise RuntimeError(f"{flow} fixed-universe Theil is missing for positive-total reporter-years.")

    zero_weight_rows = int((panel["zero_weight_country_trade_share"].fillna(0) > 0).sum())
    diagnostics = {
        "flow": flow,
        "country_sample": COUNTRY_SAMPLE,
        "benchmark_sample": BENCHMARK_SAMPLE,
        "product_id_mode": PRODUCT_ID_MODE,
        "start_year": start_year,
        "end_year": end_year,
        "country_product_rows": int(len(country_product)),
        "country_reporter_year_rows": int(panel[["reporter_code", "year"]].drop_duplicates().shape[0]),
        "country_reporters": int(panel["reporter_code"].nunique()),
        "country_products": int(country_product["product_id"].nunique()),
        "world_product_rows": int(len(world_product)),
        "world_products_union": universe_count,
        "world_products_min_by_year": int(year_counts["world_active_products"].min()),
        "world_products_max_by_year": int(year_counts["world_active_products"].max()),
        "duplicate_country_product_keys": duplicate_country_keys,
        "duplicate_world_product_keys": duplicate_world_keys,
        "country_products_outside_universe": int(len(outside)),
        "world_relative_zero_weight_rows": zero_weight_rows,
        "excluded_999999_product_id_rows": 0,
        "status": "ok",
    }
    return panel.sort_values(["flow", "country", "year"]).reset_index(drop=True), diagnostics, year_counts.assign(flow=flow)


def add_balanced_flags(
    panel: pd.DataFrame,
    start_year: int,
    end_year: int,
    require_balanced_countries: int | None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    required_years = set(range(start_year, end_year + 1))
    out = panel.copy()
    out["balanced_panel_flag"] = False
    balance: dict[str, Any] = {
        "balanced_start_year": start_year,
        "balanced_end_year": end_year,
        "balanced_years": len(required_years),
        "flows": {},
    }
    for flow, flow_frame in out.groupby("flow", sort=True):
        in_window = flow_frame[flow_frame["year"].between(start_year, end_year)]
        country_years = in_window.groupby("reporter_code")["year"].apply(lambda years: set(years.astype(int)))
        balanced_codes = sorted(int(code) for code, years in country_years.items() if required_years.issubset(years))
        if require_balanced_countries is not None and len(balanced_codes) < require_balanced_countries:
            raise RuntimeError(
                f"{flow} balanced window has {len(balanced_codes)} reporters, below required {require_balanced_countries}."
            )
        mask = out["flow"].eq(flow) & out["reporter_code"].isin(balanced_codes) & out["year"].between(start_year, end_year)
        out.loc[mask, "balanced_panel_flag"] = True
        balance["flows"][flow] = {
            "balanced_countries": len(balanced_codes),
            "balanced_reporter_codes": balanced_codes,
            "balanced_rows": int(mask.sum()),
            "all_available_rows_before_balance": int(len(flow_frame)),
            "all_available_countries_before_balance": int(flow_frame["reporter_code"].nunique()),
        }
    return out, balance


def make_yearly_summary(panel: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for label, frame in [
        ("all_available", panel),
        ("balanced_2000_2024", panel[panel["balanced_panel_flag"]].copy()),
    ]:
        if frame.empty:
            continue
        summary = (
            frame.groupby(["flow", "year"], as_index=False)
            .agg(
                countries=("reporter_code", "nunique"),
                median_fixed_universe_product_theil=("fixed_universe_product_theil", "median"),
                mean_fixed_universe_product_theil=("fixed_universe_product_theil", "mean"),
                p10_fixed_universe_product_theil=("fixed_universe_product_theil", lambda x: float(np.nanpercentile(x, 10))),
                p90_fixed_universe_product_theil=("fixed_universe_product_theil", lambda x: float(np.nanpercentile(x, 90))),
                median_fixed_universe_product_theil_normalized=("fixed_universe_product_theil_normalized", "median"),
                median_active_product_theil=("active_product_theil", "median"),
                median_active_product_margin_theil=("active_product_margin_theil", "median"),
                median_inactive_product_margin_theil=("inactive_product_margin_theil", "median"),
                median_inactive_product_margin_theil_normalized_by_fixed_universe=(
                    "inactive_product_margin_theil_normalized_by_fixed_universe",
                    "median",
                ),
                median_theil_extensive_gap=("theil_extensive_gap", "median"),
                median_world_relative_product_theil=("world_relative_product_theil", "median"),
                median_active_product_share=("active_product_share", "median"),
                median_active_product_count=("active_product_count", "median"),
                median_total_trade_value=("total_trade_value", "median"),
            )
            .sort_values(["flow", "year"])
        )
        summary.insert(0, "sample_window", label)
        frames.append(summary)
    return pd.concat(frames, ignore_index=True)


def make_latest_rankings(panel: pd.DataFrame) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for flow, flow_frame in panel.groupby("flow", sort=True):
        latest_year = int(flow_frame["year"].max())
        latest = flow_frame[flow_frame["year"].eq(latest_year)].copy()
        latest = latest.sort_values("fixed_universe_product_theil", ascending=False).reset_index(drop=True)
        latest.insert(0, "fixed_universe_theil_rank_desc", np.arange(1, len(latest) + 1))
        rows.append(latest)
    return pd.concat(rows, ignore_index=True)


def make_rich_proxy_summary(panel: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (flow, year), group in panel.groupby(["flow", "year"], sort=True):
        rich = group[group["income_group"].eq("High income") & ~group["iso3"].isin(RICH_PROXY_EXCLUDE)].copy()
        jk = group[group["iso3"].isin(["JPN", "KOR"])].copy()
        if rich.empty or jk.empty:
            continue
        rich_mean = float(rich["fixed_universe_product_theil"].mean())
        jk_mean = float(jk["fixed_universe_product_theil"].mean())
        rows.append(
            {
                "flow": flow,
                "year": int(year),
                "rich_proxy_countries_excluding_japan_korea": int(rich["iso3"].nunique()),
                "japan_korea_countries_present": int(jk["iso3"].nunique()),
                "rich_proxy_mean_fixed_universe_product_theil": rich_mean,
                "japan_korea_mean_fixed_universe_product_theil": jk_mean,
                "japan_korea_vs_rich_proxy_pct_gap": float(jk_mean / rich_mean - 1.0) if rich_mean > 0 else np.nan,
                "rich_proxy_mean_fixed_universe_product_theil_normalized": float(
                    rich["fixed_universe_product_theil_normalized"].mean()
                ),
                "japan_korea_mean_fixed_universe_product_theil_normalized": float(
                    jk["fixed_universe_product_theil_normalized"].mean()
                ),
                "rich_proxy_mean_active_product_theil": float(rich["active_product_theil"].mean()),
                "japan_korea_mean_active_product_theil": float(jk["active_product_theil"].mean()),
                "rich_proxy_mean_world_relative_product_theil": float(rich["world_relative_product_theil"].mean()),
                "japan_korea_mean_world_relative_product_theil": float(jk["world_relative_product_theil"].mean()),
                "rich_proxy_mean_active_product_share": float(rich["active_product_share"].mean()),
                "japan_korea_mean_active_product_share": float(jk["active_product_share"].mean()),
            }
        )
    return pd.DataFrame(rows)


def compare_to_existing_gini(panel: pd.DataFrame) -> pd.DataFrame:
    paths = [
        tcp.sample_processed_dir(COUNTRY_SAMPLE) / "fixed_universe_product_gini_panel.parquet",
        tcp.sample_processed_dir(COUNTRY_SAMPLE) / "concentration_all_years.parquet",
    ]
    frames: list[pd.DataFrame] = []
    if paths[0].exists():
        gini = pd.read_parquet(
            paths[0],
            columns=[
                "reporter_code",
                "year",
                "flow",
                "fixed_universe_product_gini",
                "active_product_gini",
            ],
        )
        frames.append(gini)
    if paths[1].exists():
        active = pd.read_parquet(
            paths[1],
            columns=[
                "reporter_code",
                "year",
                "flow",
                "product_gini",
                "partner_gini",
                "product_partner_cell_gini",
            ],
        )
        frames.append(active)
    out = panel[["reporter_code", "year", "flow", "fixed_universe_product_theil", "active_product_theil"]].copy()
    for frame in frames:
        out = out.merge(frame, on=["reporter_code", "year", "flow"], how="left")
    return out


def write_report(panel: pd.DataFrame, diagnostics: pd.DataFrame, balance: dict[str, Any], out_dir: Path) -> None:
    latest = make_latest_rankings(panel)
    exports_latest = latest[latest["flow"].eq("Exports")].head(5)
    imports_latest = latest[latest["flow"].eq("Imports")].head(5)
    universe_counts = diagnostics.set_index("flow")["world_products_union"].to_dict()
    zero_weight_rows = diagnostics.set_index("flow")["world_relative_zero_weight_rows"].to_dict()
    rich = make_rich_proxy_summary(panel)
    rich_2024_exports = rich[(rich["flow"].eq("Exports")) & (rich["year"].eq(2024))]
    if rich_2024_exports.empty:
        rich_line = "- 2024 export Japan/Korea comparison unavailable."
    else:
        row = rich_2024_exports.iloc[0]
        rich_line = (
            "- 2024 exports: Japan/Korea fixed-universe Product Theil mean "
            f"{row['japan_korea_mean_fixed_universe_product_theil']:.3f}; "
            f"high-income rd2 proxy excluding Japan/Korea mean {row['rich_proxy_mean_fixed_universe_product_theil']:.3f}; "
            f"gap {row['japan_korea_vs_rich_proxy_pct_gap'] * 100:.1f}%."
        )
    lines = [
        "# Fixed-Universe Harmonized-HS6 Product Theil",
        "",
        f"Generated: {now_utc()}",
        "",
        "## Definition",
        "",
        "Unit: rd2 reporter-year-flow product basket over LT/HGL-weighted HS1992 product families.",
        "",
        "Product universe: for each flow, the fixed universe is the 2000-2024 union of positive `world_broad` harmonized product-family trade. All reported country rows are `rd2_countries`; `world_broad` is only a benchmark product-universe source, plus the denominator for the separately reported leave-one-out world-relative diagnostic.",
        "",
        "`x_cfpt` is harmonized product trade value for reporter `c`, flow `f`, year `t`, and product family `p`; missing products are set to zero.",
        "",
        "`T_fixed_cft = sum_p s_cpft * log(s_cpft * K_f)`, where zero-share products contribute zero.",
        "",
        "Active/inactive product-margin decomposition: `T_fixed = T_active + log(K_f / A_cft)`, where `A_cft` is the number of active positive product families.",
        "",
        "`T_norm = T_fixed / log(K_f)`.",
        "",
        "`T_world_relative = sum_p s_cpft * log(s_cpft / w_-c,pft)`, where `w_-c,pft` is the leave-one-out world product share.",
        "",
        "Higher fixed-universe Theil means the country trades in fewer eligible products or places more trade value in a few products. HS6 `999999` is excluded before harmonization and aggregation.",
        "",
        "## Universe Counts",
        "",
        f"- Export product universe: {int(universe_counts.get('Exports', 0)):,}",
        f"- Import product universe: {int(universe_counts.get('Imports', 0)):,}",
        "",
        "## Balanced Window",
        "",
        f"- Window: {balance.get('balanced_start_year')}-{balance.get('balanced_end_year')}",
        *[
            f"- {flow}: {details.get('balanced_countries')} balanced countries, {details.get('balanced_rows')} rows"
            for flow, details in balance.get("flows", {}).items()
        ],
        "",
        "## Latest Highest Fixed-Universe Product Theil",
        "",
        "Exports:",
        "",
        *[
            f"- {row.country} ({row.iso3}): {row.fixed_universe_product_theil:.3f}"
            for row in exports_latest.itertuples(index=False)
        ],
        "",
        "Imports:",
        "",
        *[
            f"- {row.country} ({row.iso3}): {row.fixed_universe_product_theil:.3f}"
            for row in imports_latest.itertuples(index=False)
        ],
        "",
        "## Japan/Korea And The Economist Question",
        "",
        rich_line,
        "",
        "This product-only Theil is closer to UNCTAD's product component than to UNCTAD's full overall Theil. UNCTAD's headline overall measure also adds market concentration within each product, so a full UNCTAD-style replication still needs product-destination cells.",
        "",
        "## World-Relative Diagnostics",
        "",
        f"- Export reporter-years with positive country trade on zero leave-one-out world support: {int(zero_weight_rows.get('Exports', 0))}",
        f"- Import reporter-years with positive country trade on zero leave-one-out world support: {int(zero_weight_rows.get('Imports', 0))}",
        "",
        "Rows with positive zero-weight share have undefined KL divergence and keep `world_relative_product_theil` missing.",
        "",
        "## Outputs",
        "",
        "- `fixed_universe_product_theil_all_years.csv`",
        "- `fixed_universe_product_theil_latest_rankings.csv`",
        "- `fixed_universe_product_theil_yearly_summary.csv`",
        "- `fixed_universe_product_theil_rich_proxy_summary.csv`",
        "- `fixed_universe_product_theil_gini_comparison.csv`",
        "- `fixed_universe_product_theil_diagnostics.csv`",
        "- `fixed_universe_product_theil_manifest.json`",
    ]
    (out_dir / "fixed_universe_product_theil.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_outputs(panel: pd.DataFrame, diagnostics: pd.DataFrame, start_year: int, end_year: int) -> None:
    if set(panel["flow"].dropna().unique()) != set(FLOW_CHOICES):
        raise RuntimeError("Panel must contain both Exports and Imports.")
    if not panel["product_id_mode"].eq(PRODUCT_ID_MODE).all():
        raise RuntimeError("Panel contains a non-harmonized product_id_mode.")
    duplicate_keys = duplicate_key_count(panel, ["reporter_code", "year", "flow"])
    if duplicate_keys:
        raise RuntimeError("Panel has duplicate reporter-year-flow keys.")
    positive = panel["total_trade_value"] > 0
    if panel.loc[positive, "fixed_universe_product_theil"].isna().any():
        raise RuntimeError("Panel has missing fixed-universe Theil for positive-total rows.")
    if (panel["fixed_universe_product_theil"] < -1e-12).any():
        raise RuntimeError("Fixed-universe Theil values must be nonnegative.")
    norm = panel["fixed_universe_product_theil_normalized"].dropna()
    if (norm < -1e-12).any() or (norm > 1 + 1e-12).any():
        raise RuntimeError("Normalized fixed-universe Theil values must be inside [0, 1].")
    if (panel["active_product_share"] <= 0).any() or (panel["active_product_share"] > 1).any():
        raise RuntimeError("Active product shares must lie inside (0, 1].")
    if (panel["active_product_count"] > panel["universe_product_count"]).any():
        raise RuntimeError("Active product count cannot exceed universe product count.")
    residual = panel["product_margin_decomposition_residual"].dropna().abs()
    if (residual > 1e-10).any():
        raise RuntimeError("Product Theil active/inactive decomposition residual exceeds tolerance.")
    for flow, flow_frame in panel.groupby("flow"):
        universe_counts = flow_frame.groupby("year")["universe_product_count"].nunique()
        if not universe_counts.eq(1).all():
            raise RuntimeError(f"{flow} universe count varies within year.")
        if flow_frame["universe_product_count"].nunique() != 1:
            raise RuntimeError(f"{flow} fixed universe count varies over {start_year}-{end_year}.")
    if not diagnostics["status"].eq("ok").all():
        raise RuntimeError("Diagnostics contain non-ok statuses.")


def write_outputs(
    panel: pd.DataFrame,
    diagnostics: pd.DataFrame,
    world_year_counts: pd.DataFrame,
    balance: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Path]:
    out_dir = result_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    processed_panel_path().parent.mkdir(parents=True, exist_ok=True)
    validate_outputs(panel, diagnostics, args.start_year, args.end_year)

    panel.to_parquet(processed_panel_path(), index=False)
    all_years = out_dir / "fixed_universe_product_theil_all_years.csv"
    latest = out_dir / "fixed_universe_product_theil_latest_rankings.csv"
    yearly = out_dir / "fixed_universe_product_theil_yearly_summary.csv"
    diagnostics_path = out_dir / "fixed_universe_product_theil_diagnostics.csv"
    manifest_path = out_dir / "fixed_universe_product_theil_manifest.json"
    rich_proxy = out_dir / "fixed_universe_product_theil_rich_proxy_summary.csv"
    world_counts = out_dir / "fixed_universe_product_theil_world_product_support_by_year.csv"
    gini_comparison = out_dir / "fixed_universe_product_theil_gini_comparison.csv"

    panel.to_csv(all_years, index=False)
    make_latest_rankings(panel).to_csv(latest, index=False)
    make_yearly_summary(panel).to_csv(yearly, index=False)
    diagnostics.to_csv(diagnostics_path, index=False)
    make_rich_proxy_summary(panel).to_csv(rich_proxy, index=False)
    world_year_counts.to_csv(world_counts, index=False)
    compare_to_existing_gini(panel).to_csv(gini_comparison, index=False)

    source = {flow: {key: str(path.relative_to(ROOT)) for key, path in source_paths(flow).items()} for flow in FLOW_CHOICES}
    manifest = {
        "status": "complete",
        "generated_at_utc": now_utc(),
        "country_sample": COUNTRY_SAMPLE,
        "benchmark_sample": BENCHMARK_SAMPLE,
        "benchmark_role": "benchmark product-universe source only for fixed-universe outputs; also used as the denominator for the separately reported leave-one-out world-relative diagnostic; never the reporter sample",
        "product_id_mode": PRODUCT_ID_MODE,
        "harmonization": {
            "method": "LT/HGL weighted conversion to HS1992/H0 before product aggregation",
            "source_doi": tcp.LT_HGL_DATASET_DOI,
            "source_version": tcp.LT_HGL_DATASET_VERSION,
            "target": f"{tcp.LT_HGL_TARGET_LABEL}/{tcp.LT_HGL_TARGET_REVISION}",
        },
        "measures": {
            "fixed_universe_product_theil": {
                "unit": "reporter-year-flow over harmonized product families",
                "universe_definition": "2000-2024 union of positive world_broad product-family trade within flow",
                "zero_policy": "missing reporter-year-product values are zero and contribute zero to the Theil sum",
                "formula": "T = sum_p s_p * log(s_p * K)",
                "normalization": "T / log(K)",
                "active_inactive_decomposition": "T_fixed = T_active + log(K / active_product_count)",
            },
            "world_relative_product_theil": {
                "unit": "reporter-year-flow over active country product families",
                "denominator": "leave-one-out world_broad product shares by year and flow",
                "formula": "sum_p s_country,p * log(s_country,p / s_world_minus_country,p)",
            },
        },
        "exclusions": {
            "hs6_999999": "excluded before harmonization and aggregation",
            "partner_code_0_world": "not applicable; product-only input artifacts already exclude partner World before product aggregation",
        },
        "years": {"start_year": args.start_year, "end_year": args.end_year},
        "balanced_window": balance,
        "diagnostics": diagnostics.to_dict(orient="records"),
        "source_files": source,
        "outputs": {
            "processed_panel": str(processed_panel_path().relative_to(ROOT)),
            "all_years": str(all_years.relative_to(ROOT)),
            "latest_rankings": str(latest.relative_to(ROOT)),
            "yearly_summary": str(yearly.relative_to(ROOT)),
            "diagnostics": str(diagnostics_path.relative_to(ROOT)),
            "rich_proxy_summary": str(rich_proxy.relative_to(ROOT)),
            "gini_comparison": str(gini_comparison.relative_to(ROOT)),
            "world_product_support_by_year": str(world_counts.relative_to(ROOT)),
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, default=json_default) + "\n", encoding="utf-8")
    write_report(panel, diagnostics, balance, out_dir)
    return {
        "processed_panel": processed_panel_path(),
        "all_years": all_years,
        "latest_rankings": latest,
        "yearly_summary": yearly,
        "diagnostics": diagnostics_path,
        "manifest": manifest_path,
        "rich_proxy_summary": rich_proxy,
        "gini_comparison": gini_comparison,
        "world_product_support_by_year": world_counts,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country-sample", default=COUNTRY_SAMPLE, choices=tcp.COUNTRY_SAMPLE_CHOICES)
    parser.add_argument("--benchmark-sample", default=BENCHMARK_SAMPLE, choices=tcp.COUNTRY_SAMPLE_CHOICES)
    parser.add_argument("--product-id-mode", default=PRODUCT_ID_MODE, choices=[PRODUCT_ID_MODE])
    parser.add_argument("--flow", default="all", choices=["all", *FLOW_CHOICES])
    parser.add_argument("--start-year", type=int, default=DEFAULT_START_YEAR)
    parser.add_argument("--end-year", type=int, default=DEFAULT_END_YEAR)
    parser.add_argument("--balanced-start-year", type=int, default=DEFAULT_START_YEAR)
    parser.add_argument("--balanced-end-year", type=int, default=DEFAULT_END_YEAR)
    parser.add_argument("--require-balanced-countries", type=int, default=DEFAULT_REQUIRE_BALANCED_COUNTRIES)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.country_sample != COUNTRY_SAMPLE:
        raise RuntimeError("Website-facing fixed-universe outputs must use --country-sample rd2_countries.")
    if args.benchmark_sample != BENCHMARK_SAMPLE:
        raise RuntimeError("Fixed-universe product support must use --benchmark-sample world_broad.")
    if args.product_id_mode != PRODUCT_ID_MODE:
        raise RuntimeError("Fixed-universe website outputs must use harmonized_hs6_family.")
    if args.start_year != DEFAULT_START_YEAR or args.end_year != DEFAULT_END_YEAR:
        raise RuntimeError("Official fixed-universe outputs use the 2000-2024 harmonized product-universe window.")
    if args.balanced_start_year != args.start_year or args.balanced_end_year != args.end_year:
        raise RuntimeError("Balanced window must match the fixed-universe 2000-2024 window.")

    country_panel = read_country_panel()
    income_metadata = read_income_metadata()
    flows = list(FLOW_CHOICES) if args.flow == "all" else [args.flow]
    panels: list[pd.DataFrame] = []
    diagnostics: list[dict[str, Any]] = []
    world_counts: list[pd.DataFrame] = []
    for flow in flows:
        print(f"Computing fixed-universe Product Theil for {flow}...", flush=True)
        flow_panel, flow_diagnostics, flow_world_counts = compute_flow_panel(
            flow, country_panel, income_metadata, args.start_year, args.end_year
        )
        panels.append(flow_panel)
        diagnostics.append(flow_diagnostics)
        world_counts.append(flow_world_counts)

    panel = pd.concat(panels, ignore_index=True).sort_values(["flow", "country", "year"]).reset_index(drop=True)
    panel, balance = add_balanced_flags(panel, args.balanced_start_year, args.balanced_end_year, args.require_balanced_countries)
    diagnostics_df = pd.DataFrame(diagnostics)
    world_counts_df = pd.concat(world_counts, ignore_index=True).sort_values(["flow", "year"])
    paths = write_outputs(panel, diagnostics_df, world_counts_df, balance, args)
    print("Fixed-universe Product Theil outputs written:")
    for name, path in paths.items():
        print(f"- {name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
