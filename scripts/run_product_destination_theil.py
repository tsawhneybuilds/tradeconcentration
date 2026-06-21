#!/usr/bin/env python3
"""Compute rd2 product-destination Theil decompositions.

This is an HS6-family analogue of UNCTAD's product-plus-market Theil, not an
exact SITC Rev.3 replication. Reported rows are rd2 reporter-year-flow rows.
The world_broad sample is used only to define the fixed product universe.
"""

from __future__ import annotations

import argparse
import gc
import json
import math
import os
import resource
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import trade_concentration_pipeline as tcp  # noqa: E402


COUNTRY_SAMPLE = "rd2_countries"
BENCHMARK_SAMPLE = "world_broad"
PRODUCT_ID_MODE = "harmonized_hs6_family"
FLOW_CHOICES = ("Exports", "Imports")
DEFAULT_START_YEAR = 2000
DEFAULT_END_YEAR = 2024
DEFAULT_MEMORY_BUDGET_GB = 10.0
DEFAULT_CHUNK_ROWS = 250_000
DEFAULT_COMPACT_ROWS = 250_000
DEFAULT_REQUIRE_BALANCED_COUNTRIES = 55
RESULT_DIRNAME = "product_destination_theil_tables"
CHECKPOINT_DIRNAME = "product_destination_theil_file_aggregates"
PANEL_FILENAME = "product_destination_theil_panel.parquet"
DRYRUN_SUFFIX = "_dryrun"
RICH_PROXY_EXCLUDE = {"JPN", "KOR", "TWN"}
RESIDUAL_TOLERANCE = 1e-9
PRODUCT_PANEL_THEIL_TOLERANCE = 1e-8
PRODUCT_PANEL_REL_VALUE_TOLERANCE = 1e-9


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if math.isnan(float(value)) else float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, Path):
        return rel(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def flow_slug(flow: str) -> str:
    return "exports" if flow == "Exports" else "imports"


def value_noun(flow: str) -> str:
    return "exports" if flow == "Exports" else "imports"


def artifact_stem(flow: str) -> str:
    return "world_relative_product_gini" if flow == "Exports" else "world_relative_import_product_gini"


def world_product_column(flow: str) -> str:
    return f"world_product_{value_noun(flow)}"


def world_product_path(flow: str) -> Path:
    return (
        tcp.sample_processed_dir(BENCHMARK_SAMPLE)
        / f"{artifact_stem(flow)}_{PRODUCT_ID_MODE}_world_product_{value_noun(flow)}.parquet"
    )


def official_run(args: argparse.Namespace) -> bool:
    return args.max_files is None


def result_dir(args: argparse.Namespace) -> Path:
    suffix = "" if official_run(args) else DRYRUN_SUFFIX
    return tcp.sample_results_dir(COUNTRY_SAMPLE) / f"{RESULT_DIRNAME}{suffix}"


def processed_panel_path(args: argparse.Namespace) -> Path:
    suffix = "" if official_run(args) else DRYRUN_SUFFIX
    return tcp.sample_processed_dir(COUNTRY_SAMPLE) / f"product_destination_theil_panel{suffix}.parquet"


def checkpoint_root(args: argparse.Namespace) -> Path:
    suffix = "" if official_run(args) else DRYRUN_SUFFIX
    return tcp.sample_processed_dir(COUNTRY_SAMPLE) / "checkpoints" / f"{CHECKPOINT_DIRNAME}{suffix}"


def cell_checkpoint_dir(args: argparse.Namespace, flow: str) -> Path:
    return checkpoint_root(args) / flow_slug(flow) / "cells"


def partner_checkpoint_dir(args: argparse.Namespace, flow: str) -> Path:
    return checkpoint_root(args) / flow_slug(flow) / "standalone_partner_default"


def status_dir(args: argparse.Namespace, flow: str) -> Path:
    return checkpoint_root(args) / flow_slug(flow) / "status"


def partial_path_for_raw(raw_path: Path, args: argparse.Namespace, flow: str, kind: str) -> Path:
    base = raw_path.name
    if base.endswith(".gz"):
        base = base[:-3]
    if base.endswith(".txt"):
        base = base[:-4]
    directory = cell_checkpoint_dir(args, flow) if kind == "cells" else partner_checkpoint_dir(args, flow)
    return directory / f"{base}.parquet"


def status_path_for_raw(raw_path: Path, args: argparse.Namespace, flow: str) -> Path:
    base = raw_path.name
    if base.endswith(".gz"):
        base = base[:-3]
    return status_dir(args, flow) / f"{base}.json"


def parquet_list(paths: list[Path]) -> str:
    if not paths:
        raise FileNotFoundError("No checkpoint parquet files are available.")
    return "[" + ", ".join("'" + str(path).replace("'", "''") + "'" for path in paths) + "]"


def current_rss_mb() -> float | None:
    try:
        import psutil  # type: ignore

        return float(psutil.Process(os.getpid()).memory_info().rss / (1024**2))
    except Exception:
        try:
            rss = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        except Exception:
            return None
        return rss / (1024**2) if sys.platform == "darwin" else rss / 1024


def log_resource(label: str, memory_budget_gb: float | None = None) -> None:
    rss = current_rss_mb()
    if rss is None:
        print(f"[resource] {label}: rss unavailable", flush=True)
        return
    print(f"[resource] {label}: rss={rss:,.1f} MB", flush=True)
    if memory_budget_gb and memory_budget_gb > 0 and rss > memory_budget_gb * 1024:
        raise RuntimeError(f"Memory budget exceeded after {label}: {rss / 1024:.2f} GB > {memory_budget_gb:.2f} GB")


def safe_ln_ratio(numerator: float, denominator: float) -> float:
    if numerator <= 0 or denominator <= 0:
        return np.nan
    return math.log(numerator / denominator)


def compute_product_destination_theil_metrics(
    cells: pd.DataFrame,
    product_universe_count: int,
    destination_universe_count: int,
) -> dict[str, float | int]:
    """Compute product-first and partner-first Theil from active cells only."""
    required = {"product_id", "partner_code", "trade_value"}
    missing = required - set(cells.columns)
    if missing:
        raise ValueError(f"cells is missing columns: {sorted(missing)}")
    work = cells[["product_id", "partner_code", "trade_value"]].copy()
    work["trade_value"] = pd.to_numeric(work["trade_value"], errors="coerce")
    work = work.dropna(subset=["product_id", "partner_code", "trade_value"])
    if (work["trade_value"] < 0).any():
        raise ValueError("Theil inputs must be nonnegative.")
    work = work[work["trade_value"] > 0].copy()
    if work.empty:
        return empty_metric_row(product_universe_count, destination_universe_count)
    product_universe_count = int(product_universe_count)
    destination_universe_count = int(destination_universe_count)
    if product_universe_count <= 0 or destination_universe_count <= 0:
        return empty_metric_row(product_universe_count, destination_universe_count)
    active_product_count = int(work["product_id"].nunique())
    active_partner_count = int(work["partner_code"].nunique())
    if product_universe_count < active_product_count:
        raise ValueError("product_universe_count cannot be smaller than active product count.")
    if destination_universe_count < active_partner_count:
        raise ValueError("destination_universe_count cannot be smaller than active partner count.")

    cell_values = work.groupby(["product_id", "partner_code"], as_index=False)["trade_value"].sum()
    total = float(cell_values["trade_value"].sum())
    if total <= 0:
        return empty_metric_row(product_universe_count, destination_universe_count)
    cell_share = cell_values["trade_value"].to_numpy(dtype=float) / total
    cell_universe_count = product_universe_count * destination_universe_count
    overall = float(np.sum(cell_share * np.log(cell_share * cell_universe_count)))

    product_values = cell_values.groupby("product_id", as_index=False)["trade_value"].sum()
    product_share = product_values["trade_value"].to_numpy(dtype=float) / total
    product_theil = float(np.sum(product_share * np.log(product_share * product_universe_count)))
    active_product_theil = float(np.sum(product_share * np.log(product_share * active_product_count)))
    inactive_product_margin = math.log(product_universe_count / active_product_count)

    partner_values = cell_values.groupby("partner_code", as_index=False)["trade_value"].sum()
    partner_share = partner_values["trade_value"].to_numpy(dtype=float) / total
    partner_theil = float(np.sum(partner_share * np.log(partner_share * destination_universe_count)))
    active_partner_theil = float(np.sum(partner_share * np.log(partner_share * active_partner_count)))
    inactive_partner_margin = math.log(destination_universe_count / active_partner_count)

    return {
        "overall_product_destination_theil": overall,
        "product_theil": product_theil,
        "active_product_theil": active_product_theil,
        "inactive_product_margin_theil": inactive_product_margin,
        "destination_within_product_theil": overall - product_theil,
        "partner_theil_product_cell_based": partner_theil,
        "active_partner_theil_product_cell_based": active_partner_theil,
        "inactive_partner_margin_theil_product_cell_based": inactive_partner_margin,
        "product_within_partner_theil": overall - partner_theil,
        "overall_product_destination_theil_normalized": overall / math.log(cell_universe_count)
        if cell_universe_count > 1
        else np.nan,
        "product_theil_normalized": product_theil / math.log(product_universe_count)
        if product_universe_count > 1
        else np.nan,
        "partner_theil_product_cell_based_normalized": partner_theil / math.log(destination_universe_count)
        if destination_universe_count > 1
        else np.nan,
        "destination_within_product_component_share": (overall - product_theil) / overall if overall > 0 else np.nan,
        "product_component_share": product_theil / overall if overall > 0 else np.nan,
        "product_within_partner_component_share": (overall - partner_theil) / overall if overall > 0 else np.nan,
        "partner_component_share": partner_theil / overall if overall > 0 else np.nan,
        "product_margin_decomposition_residual": product_theil - active_product_theil - inactive_product_margin,
        "product_first_decomposition_residual": overall - product_theil - (overall - product_theil),
        "partner_first_decomposition_residual": overall - partner_theil - (overall - partner_theil),
        "total_trade_value": total,
        "active_cell_count": int(len(cell_values)),
        "universe_cell_count": int(cell_universe_count),
        "active_product_count": active_product_count,
        "universe_product_count": product_universe_count,
        "zero_product_count": int(product_universe_count - active_product_count),
        "active_product_share": active_product_count / product_universe_count,
        "active_partner_count": active_partner_count,
        "universe_partner_count": destination_universe_count,
        "zero_partner_count": int(destination_universe_count - active_partner_count),
        "active_partner_share": active_partner_count / destination_universe_count,
    }


def empty_metric_row(product_universe_count: int, destination_universe_count: int) -> dict[str, float | int]:
    cell_universe_count = int(product_universe_count) * int(destination_universe_count)
    return {
        "overall_product_destination_theil": np.nan,
        "product_theil": np.nan,
        "active_product_theil": np.nan,
        "inactive_product_margin_theil": np.nan,
        "destination_within_product_theil": np.nan,
        "partner_theil_product_cell_based": np.nan,
        "active_partner_theil_product_cell_based": np.nan,
        "inactive_partner_margin_theil_product_cell_based": np.nan,
        "product_within_partner_theil": np.nan,
        "overall_product_destination_theil_normalized": np.nan,
        "product_theil_normalized": np.nan,
        "partner_theil_product_cell_based_normalized": np.nan,
        "destination_within_product_component_share": np.nan,
        "product_component_share": np.nan,
        "product_within_partner_component_share": np.nan,
        "partner_component_share": np.nan,
        "product_margin_decomposition_residual": np.nan,
        "product_first_decomposition_residual": np.nan,
        "partner_first_decomposition_residual": np.nan,
        "total_trade_value": 0.0,
        "active_cell_count": 0,
        "universe_cell_count": cell_universe_count,
        "active_product_count": 0,
        "universe_product_count": int(product_universe_count),
        "zero_product_count": int(product_universe_count),
        "active_product_share": 0.0,
        "active_partner_count": 0,
        "universe_partner_count": int(destination_universe_count),
        "zero_partner_count": int(destination_universe_count),
        "active_partner_share": 0.0,
    }


def read_country_panel() -> pd.DataFrame:
    path = tcp.sample_processed_dir(COUNTRY_SAMPLE) / "comtrade_country_panel.csv"
    if not path.exists():
        raise RuntimeError(f"Missing rd2 country panel: {path}")
    panel = pd.read_csv(path)
    required = {"country", "iso3", "reporter_code"}
    missing = required - set(panel.columns)
    if missing:
        raise RuntimeError(f"Country panel is missing columns: {sorted(missing)}")
    panel = panel[["country", "iso3", "reporter_code"]].copy()
    panel["reporter_code"] = pd.to_numeric(panel["reporter_code"], errors="coerce").astype("Int64")
    panel = panel.dropna(subset=["reporter_code"]).copy()
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
        return keep.sort_values("iso3").drop_duplicates("iso3", keep="last")
    return pd.DataFrame(columns=["iso3", "region", "income_group"])


def read_partner_reference() -> pd.DataFrame:
    path = ROOT / "data/raw/comtrade/partner_reference.csv"
    if not path.exists():
        return pd.DataFrame(columns=["partner_code", "partner_iso3", "partner_name", "aggregate_like_partner"])
    ref = pd.read_csv(path)
    required = {"partner_code", "partner_iso3", "partner_name"}
    missing = required - set(ref.columns)
    if missing:
        raise RuntimeError(f"Partner reference is missing columns: {sorted(missing)}")
    ref = ref[["partner_code", "partner_iso3", "partner_name"]].copy()
    ref["partner_code"] = pd.to_numeric(ref["partner_code"], errors="coerce").astype("Int64")
    ref = ref.dropna(subset=["partner_code"]).copy()
    ref["partner_code"] = ref["partner_code"].astype(int)
    ref["partner_iso3"] = ref["partner_iso3"].fillna("").astype(str).str.strip()
    ref["partner_name"] = ref["partner_name"].fillna("").astype(str).str.strip()
    lower_name = ref["partner_name"].str.lower()
    ref["aggregate_like_partner"] = (
        ref["partner_iso3"].str.startswith("_")
        | lower_name.str.contains(r"\bnes\b", regex=True)
        | lower_name.str.contains("region", regex=False)
        | lower_name.str.contains("special categories", regex=False)
        | lower_name.str.contains("bunkers", regex=False)
    )
    return ref.drop_duplicates("partner_code", keep="last")


def read_product_universe(flow: str, start_year: int, end_year: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    path = world_product_path(flow)
    if not path.exists():
        raise RuntimeError(f"Missing world_broad product universe source: {path}")
    world_col = world_product_column(flow)
    world = pd.read_parquet(path, columns=["year", "product_id", world_col])
    world["year"] = pd.to_numeric(world["year"], errors="coerce").astype("Int64")
    world = world.dropna(subset=["year", "product_id"]).copy()
    world["year"] = world["year"].astype(int)
    world = world[world["year"].between(start_year, end_year)].copy()
    world[world_col] = pd.to_numeric(world[world_col], errors="coerce").fillna(0.0)
    world = world[world[world_col] > 0].copy()
    if world.empty:
        raise RuntimeError(f"{flow} world_broad product universe is empty.")
    world["product_id"] = world["product_id"].astype(str)
    bad = world[world["product_id"].str.contains("999999", na=False)]
    if not bad.empty:
        raise RuntimeError(f"{flow} world product universe contains excluded HS6 999999 product IDs.")
    universe = pd.DataFrame({"product_id": sorted(world["product_id"].drop_duplicates().tolist())})
    year_counts = (
        world.groupby("year", as_index=False)
        .agg(world_active_products=("product_id", "nunique"), world_total_trade_value=(world_col, "sum"))
        .sort_values("year")
    )
    year_counts["flow"] = flow
    return universe, year_counts


def ensure_dirs(args: argparse.Namespace, flows: list[str]) -> None:
    result_dir(args).mkdir(parents=True, exist_ok=True)
    processed_panel_path(args).parent.mkdir(parents=True, exist_ok=True)
    for flow in flows:
        cell_checkpoint_dir(args, flow).mkdir(parents=True, exist_ok=True)
        partner_checkpoint_dir(args, flow).mkdir(parents=True, exist_ok=True)
        status_dir(args, flow).mkdir(parents=True, exist_ok=True)


def maybe_fresh_checkpoint(args: argparse.Namespace) -> None:
    root = checkpoint_root(args)
    if args.fresh and root.exists():
        shutil.rmtree(root)


def configure_sample(args: argparse.Namespace) -> None:
    if args.country_sample != COUNTRY_SAMPLE:
        raise RuntimeError("Product-destination Theil outputs must use --country-sample rd2_countries.")
    if args.benchmark_sample != BENCHMARK_SAMPLE:
        raise RuntimeError("Product universe must use --benchmark-sample world_broad.")
    if args.product_id_mode != PRODUCT_ID_MODE:
        raise RuntimeError("Product-destination Theil must use harmonized_hs6_family.")
    if args.start_year != DEFAULT_START_YEAR or args.end_year != DEFAULT_END_YEAR:
        raise RuntimeError("Official product-destination Theil uses the 2000-2024 window.")
    tcp.configure_country_sample(
        country_sample=COUNTRY_SAMPLE,
        min_available_years=10,
        start_year=args.start_year,
        end_year=args.end_year,
        refresh_availability=False,
    )


def raw_files_for_run(args: argparse.Namespace) -> list[Path]:
    files = tcp.hs_bulk_files(max_files=args.max_files)
    if not files:
        raise FileNotFoundError("No rd2 Comtrade bulk files found.")
    if official_run(args):
        missing = tcp.missing_bulk_keys_for_active_sample(files)
        if missing:
            examples = [
                {"reporter_code": reporter, "year": year, "classification_code": classification}
                for reporter, year, classification in sorted(missing)[:25]
            ]
            raise RuntimeError(
                f"Missing {len(missing)} required rd2 raw bulk files; refusing to process a partial official sample. "
                f"Examples: {examples}"
            )
    return files


def preflight_raw_files(files: list[Path], args: argparse.Namespace) -> dict[str, Any]:
    sizes = [path.stat().st_size for path in files if path.exists()]
    total_size = int(sum(sizes))
    details = {
        "raw_files": len(files),
        "total_raw_file_bytes": total_size,
        "largest_raw_file_bytes": int(max(sizes)) if sizes else 0,
        "smallest_raw_file_bytes": int(min(sizes)) if sizes else 0,
        "max_files": args.max_files,
        "official_run": official_run(args),
    }
    print(
        "[preflight] "
        f"files={details['raw_files']:,}, total_size={total_size / (1024**3):,.2f} GB, "
        f"largest={details['largest_raw_file_bytes'] / (1024**2):,.1f} MB",
        flush=True,
    )
    return details


def status_from_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def write_status(path: Path, stats: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(stats, indent=2, default=json_default) + "\n", encoding="utf-8")


def aggregate_raw_file(
    raw_path: Path,
    flow: str,
    weights: pd.DataFrame,
    args: argparse.Namespace,
) -> dict[str, Any]:
    cell_path = partial_path_for_raw(raw_path, args, flow, "cells")
    partner_path = partial_path_for_raw(raw_path, args, flow, "partners")
    status_path = status_path_for_raw(raw_path, args, flow)
    if not args.fresh and cell_path.exists() and partner_path.exists() and status_path.exists():
        existing = status_from_file(status_path)
        if existing is not None and existing.get("status") == "ok":
            existing["checkpoint_reused"] = True
            return existing

    group_cols = ["reporter_code", "year", "flow", "product_id", "partner_code"]
    partner_cols = ["reporter_code", "year", "flow", "partner_code"]
    combined_cells: pd.DataFrame | None = None
    combined_partner: pd.DataFrame | None = None
    stats: dict[str, Any] = {
        "status": "started",
        "raw_file": rel(raw_path),
        "flow": flow,
        "checkpoint_reused": False,
        "chunks": 0,
        "leaf_rows": 0,
        "flow_rows": 0,
        "excluded_999999_rows": 0,
        "partner_code_0_rows_after_extract": 0,
        "product_filtered_rows": 0,
        "converted_rows": 0,
        "cell_partial_rows": 0,
        "standalone_partner_partial_rows": 0,
        "cell_trade_value": 0.0,
        "standalone_partner_trade_value": 0.0,
    }

    for leaf in tcp.iter_leaf_trade_chunks(raw_path, chunk_rows=args.chunk_rows):
        stats["chunks"] += 1
        stats["leaf_rows"] += int(len(leaf))
        work = leaf[leaf["flow"].eq(flow)].copy()
        if work.empty:
            continue
        work = work[work["year"].between(args.start_year, args.end_year)].copy()
        if work.empty:
            continue
        stats["flow_rows"] += int(len(work))
        stats["partner_code_0_rows_after_extract"] += int(pd.to_numeric(work["partner_code"], errors="coerce").eq(0).sum())

        partner_work = work[["reporter_code", "year", "flow", "partner_code", "trade_value"]].copy()
        partner_work["partner_code"] = pd.to_numeric(partner_work["partner_code"], errors="coerce")
        partner_work["trade_value"] = pd.to_numeric(partner_work["trade_value"], errors="coerce")
        partner_work = partner_work.dropna(subset=["partner_code", "trade_value"])
        partner_work = partner_work[(partner_work["partner_code"] != 0) & (partner_work["trade_value"] > 0)].copy()
        if not partner_work.empty:
            partner_work["partner_code"] = partner_work["partner_code"].astype(int)
            combined_partner = tcp.add_group_sum_frame(
                combined_partner,
                partner_work,
                partner_cols,
                value_col="trade_value",
                compact_rows=args.compact_rows,
                exclude_hs6=False,
            )

        product_work = tcp.drop_excluded_hs6(work)
        stats["excluded_999999_rows"] += int(len(work) - len(product_work))
        product_work = product_work[product_work["partner_code"] != 0].copy()
        if product_work.empty:
            continue
        stats["product_filtered_rows"] += int(len(product_work))
        product_work = product_work[
            ["reporter_code", "year", "flow", "classification_code", "cmd_code", "partner_code", "trade_value"]
        ].copy()
        converted = tcp.apply_lt_hgl_hs1992_conversion(product_work, weights=weights, value_col="trade_value")
        if converted.empty:
            continue
        if converted["product_id"].astype(str).str.contains("999999", na=False).any():
            raise RuntimeError(f"{raw_path.name} produced excluded 999999 product IDs after harmonization.")
        stats["converted_rows"] += int(len(converted))
        converted = converted[group_cols + ["trade_value"]].copy()
        converted["partner_code"] = pd.to_numeric(converted["partner_code"], errors="coerce").astype(int)
        combined_cells = tcp.add_group_sum_frame(
            combined_cells,
            converted,
            group_cols,
            value_col="trade_value",
            compact_rows=args.compact_rows,
            exclude_hs6=False,
        )
        if stats["chunks"] % 10 == 0:
            log_resource(f"{flow} {raw_path.name} chunk {stats['chunks']}", args.memory_budget_gb)

    cells = tcp.finish_group_sum_frame(combined_cells, group_cols, value_col="trade_value", exclude_hs6=False)
    partner = tcp.finish_group_sum_frame(combined_partner, partner_cols, value_col="trade_value", exclude_hs6=False)
    cell_path.parent.mkdir(parents=True, exist_ok=True)
    partner_path.parent.mkdir(parents=True, exist_ok=True)
    cells.to_parquet(cell_path, index=False)
    partner.to_parquet(partner_path, index=False)
    stats.update(
        {
            "status": "ok",
            "cell_partial_rows": int(len(cells)),
            "standalone_partner_partial_rows": int(len(partner)),
            "cell_trade_value": float(cells["trade_value"].sum()) if not cells.empty else 0.0,
            "standalone_partner_trade_value": float(partner["trade_value"].sum()) if not partner.empty else 0.0,
            "cell_checkpoint": rel(cell_path),
            "standalone_partner_checkpoint": rel(partner_path),
            "completed_at_utc": now_utc(),
        }
    )
    write_status(status_path, stats)
    del cells, partner, combined_cells, combined_partner
    gc.collect()
    log_resource(f"{flow} {raw_path.name} checkpoint", args.memory_budget_gb)
    return stats


def aggregate_flow(flow: str, files: list[Path], args: argparse.Namespace) -> pd.DataFrame:
    weights = tcp.load_lt_hgl_hs1992_conversion_weights()
    rows: list[dict[str, Any]] = []
    for idx, raw_path in enumerate(files, start=1):
        stats = aggregate_raw_file(raw_path, flow, weights, args)
        rows.append(stats)
        if stats.get("checkpoint_reused"):
            action = "reused"
        else:
            action = "wrote"
        if idx <= 10 or idx % 25 == 0:
            print(
                f"[{idx}/{len(files)}] {flow} {action}: {raw_path.name} "
                f"cell_rows={int(stats.get('cell_partial_rows', 0)):,}",
                flush=True,
            )
    status = pd.DataFrame(rows)
    status.to_csv(result_dir(args) / f"product_destination_theil_{flow_slug(flow)}_checkpoint_status.csv", index=False)
    return status


def duckdb_connect(args: argparse.Namespace) -> duckdb.DuckDBPyConnection:
    temp_dir = checkpoint_root(args) / "duckdb_tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    memory_limit = max(args.memory_budget_gb * 0.75, 1.0)
    con.execute(f"PRAGMA memory_limit='{memory_limit:.2f}GB'")
    con.execute(f"PRAGMA threads={max(1, int(args.duckdb_threads))}")
    con.execute(f"PRAGMA temp_directory='{str(temp_dir).replace(chr(39), chr(39) + chr(39))}'")
    return con


def flow_partial_paths(args: argparse.Namespace, flow: str, kind: str) -> list[Path]:
    directory = cell_checkpoint_dir(args, flow) if kind == "cells" else partner_checkpoint_dir(args, flow)
    paths = sorted(path for path in directory.glob("*.parquet") if path.stat().st_size > 0)
    if not paths:
        raise FileNotFoundError(f"No {kind} checkpoint files found for {flow}: {directory}")
    return paths


def create_product_universe_table(con: duckdb.DuckDBPyConnection, product_universe: pd.DataFrame) -> None:
    con.register("product_universe_input", product_universe)
    con.execute("CREATE OR REPLACE TEMP TABLE product_universe AS SELECT CAST(product_id AS VARCHAR) AS product_id FROM product_universe_input")
    con.unregister("product_universe_input")


def compute_flow_metrics(
    flow: str,
    product_universe: pd.DataFrame,
    args: argparse.Namespace,
) -> tuple[pd.DataFrame, dict[str, Any], pd.DataFrame]:
    cell_paths = flow_partial_paths(args, flow, "cells")
    partner_paths = flow_partial_paths(args, flow, "partners")
    cell_quoted = parquet_list(cell_paths)
    partner_quoted = parquet_list(partner_paths)
    product_universe_count = int(product_universe["product_id"].nunique())
    if product_universe_count <= 0:
        raise RuntimeError(f"{flow} product universe is empty.")
    with duckdb_connect(args) as con:
        create_product_universe_table(con, product_universe)
        print(f"[duckdb] materializing compact active product-destination cells for {flow}", flush=True)
        con.execute(
            f"""
            CREATE OR REPLACE TEMP TABLE cells AS
            SELECT
                CAST(reporter_code AS BIGINT) AS reporter_code,
                CAST(year AS BIGINT) AS year,
                CAST(flow AS VARCHAR) AS flow,
                CAST(product_id AS VARCHAR) AS product_id,
                CAST(partner_code AS BIGINT) AS partner_code,
                SUM(CAST(trade_value AS DOUBLE)) AS trade_value
            FROM read_parquet({cell_quoted}, union_by_name=true)
            WHERE CAST(trade_value AS DOUBLE) > 0
              AND CAST(partner_code AS BIGINT) <> 0
              AND CAST(flow AS VARCHAR) = '{flow}'
            GROUP BY 1, 2, 3, 4, 5
            """
        )
        log_resource(f"{flow} compact cells", args.memory_budget_gb)
        bad_products = con.execute(
            """
            SELECT COUNT(DISTINCT c.product_id)
            FROM cells AS c
            LEFT JOIN product_universe AS u USING (product_id)
            WHERE u.product_id IS NULL
            """
        ).fetchone()[0]
        if int(bad_products) != 0:
            examples = con.execute(
                """
                SELECT DISTINCT c.product_id
                FROM cells AS c
                LEFT JOIN product_universe AS u USING (product_id)
                WHERE u.product_id IS NULL
                ORDER BY 1
                LIMIT 10
                """
            ).fetchall()
            raise RuntimeError(f"{flow} cells contain products outside world_broad universe: {examples}")
        excluded_id_rows = con.execute(
            "SELECT COUNT(*) FROM cells WHERE product_id LIKE '%999999%'"
        ).fetchone()[0]
        partner_zero_rows = con.execute("SELECT COUNT(*) FROM cells WHERE partner_code = 0").fetchone()[0]
        if int(excluded_id_rows) or int(partner_zero_rows):
            raise RuntimeError(f"{flow} cell validation failed: 999999 rows={excluded_id_rows}, partner0 rows={partner_zero_rows}")
        destination_universe_count = int(con.execute("SELECT COUNT(DISTINCT partner_code) FROM cells").fetchone()[0])
        if destination_universe_count <= 0:
            raise RuntimeError(f"{flow} destination universe is empty.")
        cell_universe_count = product_universe_count * destination_universe_count

        if args.write_compacted_cells:
            out_cells = tcp.sample_processed_dir(COUNTRY_SAMPLE) / f"product_destination_theil_compacted_cells_{flow_slug(flow)}.parquet"
            con.execute(f"COPY (SELECT * FROM cells ORDER BY reporter_code, year, product_id, partner_code) TO '{str(out_cells).replace(chr(39), chr(39) + chr(39))}' (FORMAT PARQUET)")

        con.execute(
            """
            CREATE OR REPLACE TEMP TABLE totals AS
            SELECT reporter_code, year, flow, SUM(trade_value) AS total_trade_value, COUNT(*) AS active_cell_count
            FROM cells
            GROUP BY 1, 2, 3
            """
        )
        con.execute(
            """
            CREATE OR REPLACE TEMP TABLE product_totals AS
            SELECT reporter_code, year, flow, product_id, SUM(trade_value) AS trade_value
            FROM cells
            GROUP BY 1, 2, 3, 4
            """
        )
        con.execute(
            """
            CREATE OR REPLACE TEMP TABLE partner_totals AS
            SELECT reporter_code, year, flow, partner_code, SUM(trade_value) AS trade_value
            FROM cells
            GROUP BY 1, 2, 3, 4
            """
        )
        con.execute(
            """
            CREATE OR REPLACE TEMP TABLE product_counts AS
            SELECT reporter_code, year, flow, COUNT(*) AS active_product_count
            FROM product_totals
            GROUP BY 1, 2, 3
            """
        )
        con.execute(
            """
            CREATE OR REPLACE TEMP TABLE partner_counts AS
            SELECT reporter_code, year, flow, COUNT(*) AS active_partner_count
            FROM partner_totals
            GROUP BY 1, 2, 3
            """
        )
        con.execute(
            f"""
            CREATE OR REPLACE TEMP TABLE cell_metrics AS
            SELECT
                c.reporter_code,
                c.year,
                c.flow,
                SUM((c.trade_value / t.total_trade_value) * LN((c.trade_value / t.total_trade_value) * {cell_universe_count})) AS overall_product_destination_theil
            FROM cells AS c
            JOIN totals AS t USING (reporter_code, year, flow)
            GROUP BY 1, 2, 3
            """
        )
        con.execute(
            f"""
            CREATE OR REPLACE TEMP TABLE product_metrics AS
            SELECT
                p.reporter_code,
                p.year,
                p.flow,
                pc.active_product_count,
                SUM((p.trade_value / t.total_trade_value) * LN((p.trade_value / t.total_trade_value) * {product_universe_count})) AS product_theil,
                SUM((p.trade_value / t.total_trade_value) * LN((p.trade_value / t.total_trade_value) * pc.active_product_count)) AS active_product_theil
            FROM product_totals AS p
            JOIN totals AS t USING (reporter_code, year, flow)
            JOIN product_counts AS pc USING (reporter_code, year, flow)
            GROUP BY 1, 2, 3, 4
            """
        )
        con.execute(
            f"""
            CREATE OR REPLACE TEMP TABLE partner_metrics AS
            SELECT
                p.reporter_code,
                p.year,
                p.flow,
                pc.active_partner_count,
                SUM((p.trade_value / t.total_trade_value) * LN((p.trade_value / t.total_trade_value) * {destination_universe_count})) AS partner_theil_product_cell_based,
                SUM((p.trade_value / t.total_trade_value) * LN((p.trade_value / t.total_trade_value) * pc.active_partner_count)) AS active_partner_theil_product_cell_based
            FROM partner_totals AS p
            JOIN totals AS t USING (reporter_code, year, flow)
            JOIN partner_counts AS pc USING (reporter_code, year, flow)
            GROUP BY 1, 2, 3, 4
            """
        )

        print(f"[duckdb] computing standalone partner-default Theil for {flow}", flush=True)
        con.execute(
            f"""
            CREATE OR REPLACE TEMP TABLE standalone_partner AS
            SELECT
                CAST(reporter_code AS BIGINT) AS reporter_code,
                CAST(year AS BIGINT) AS year,
                CAST(flow AS VARCHAR) AS flow,
                CAST(partner_code AS BIGINT) AS partner_code,
                SUM(CAST(trade_value AS DOUBLE)) AS trade_value
            FROM read_parquet({partner_quoted}, union_by_name=true)
            WHERE CAST(trade_value AS DOUBLE) > 0
              AND CAST(partner_code AS BIGINT) <> 0
              AND CAST(flow AS VARCHAR) = '{flow}'
            GROUP BY 1, 2, 3, 4
            """
        )
        standalone_partner_universe_count = int(con.execute("SELECT COUNT(DISTINCT partner_code) FROM standalone_partner").fetchone()[0])
        con.execute(
            """
            CREATE OR REPLACE TEMP TABLE standalone_partner_totals AS
            SELECT reporter_code, year, flow, SUM(trade_value) AS total_trade_value
            FROM standalone_partner
            GROUP BY 1, 2, 3
            """
        )
        con.execute(
            """
            CREATE OR REPLACE TEMP TABLE standalone_partner_counts AS
            SELECT reporter_code, year, flow, COUNT(*) AS standalone_partner_active_count
            FROM standalone_partner
            GROUP BY 1, 2, 3
            """
        )
        con.execute(
            f"""
            CREATE OR REPLACE TEMP TABLE standalone_partner_metrics AS
            SELECT
                p.reporter_code,
                p.year,
                p.flow,
                pc.standalone_partner_active_count,
                SUM((p.trade_value / t.total_trade_value) * LN((p.trade_value / t.total_trade_value) * {standalone_partner_universe_count})) AS standalone_partner_theil_default,
                SUM((p.trade_value / t.total_trade_value) * LN((p.trade_value / t.total_trade_value) * pc.standalone_partner_active_count)) AS standalone_active_partner_theil_default
            FROM standalone_partner AS p
            JOIN standalone_partner_totals AS t USING (reporter_code, year, flow)
            JOIN standalone_partner_counts AS pc USING (reporter_code, year, flow)
            GROUP BY 1, 2, 3, 4
            """
        )
        panel = con.execute(
            f"""
            SELECT
                t.reporter_code,
                t.year,
                t.flow,
                'fixed_product_destination_universe' AS variant,
                '{PRODUCT_ID_MODE}' AS product_id_mode,
                {product_universe_count} AS universe_product_count,
                {destination_universe_count} AS universe_partner_count,
                {cell_universe_count} AS universe_cell_count,
                t.total_trade_value,
                t.active_cell_count,
                pm.active_product_count,
                {product_universe_count} - pm.active_product_count AS zero_product_count,
                pm.active_product_count::DOUBLE / {product_universe_count} AS active_product_share,
                pr.active_partner_count,
                {destination_universe_count} - pr.active_partner_count AS zero_partner_count,
                pr.active_partner_count::DOUBLE / {destination_universe_count} AS active_partner_share,
                cm.overall_product_destination_theil,
                cm.overall_product_destination_theil / LN({cell_universe_count}) AS overall_product_destination_theil_normalized,
                pm.product_theil,
                pm.product_theil / LN({product_universe_count}) AS product_theil_normalized,
                pm.active_product_theil,
                CASE WHEN pm.active_product_count > 0 THEN LN({product_universe_count}::DOUBLE / pm.active_product_count) ELSE NULL END AS inactive_product_margin_theil,
                pm.product_theil - pm.active_product_theil
                    - CASE WHEN pm.active_product_count > 0 THEN LN({product_universe_count}::DOUBLE / pm.active_product_count) ELSE NULL END
                    AS product_margin_decomposition_residual,
                cm.overall_product_destination_theil - pm.product_theil AS destination_within_product_theil,
                (cm.overall_product_destination_theil - pm.product_theil) / cm.overall_product_destination_theil AS destination_within_product_component_share,
                pm.product_theil / cm.overall_product_destination_theil AS product_component_share,
                pr.partner_theil_product_cell_based,
                pr.partner_theil_product_cell_based / LN({destination_universe_count}) AS partner_theil_product_cell_based_normalized,
                pr.active_partner_theil_product_cell_based,
                CASE WHEN pr.active_partner_count > 0 THEN LN({destination_universe_count}::DOUBLE / pr.active_partner_count) ELSE NULL END
                    AS inactive_partner_margin_theil_product_cell_based,
                cm.overall_product_destination_theil - pr.partner_theil_product_cell_based AS product_within_partner_theil,
                (cm.overall_product_destination_theil - pr.partner_theil_product_cell_based) / cm.overall_product_destination_theil AS product_within_partner_component_share,
                pr.partner_theil_product_cell_based / cm.overall_product_destination_theil AS partner_component_share,
                cm.overall_product_destination_theil - pm.product_theil - (cm.overall_product_destination_theil - pm.product_theil)
                    AS product_first_decomposition_residual,
                cm.overall_product_destination_theil - pr.partner_theil_product_cell_based - (cm.overall_product_destination_theil - pr.partner_theil_product_cell_based)
                    AS partner_first_decomposition_residual,
                spm.standalone_partner_theil_default,
                spm.standalone_partner_theil_default / LN({standalone_partner_universe_count}) AS standalone_partner_theil_default_normalized,
                spm.standalone_active_partner_theil_default,
                spm.standalone_partner_active_count,
                {standalone_partner_universe_count} AS standalone_partner_universe_count,
                {standalone_partner_universe_count} - spm.standalone_partner_active_count AS standalone_partner_zero_count
            FROM totals AS t
            JOIN cell_metrics AS cm USING (reporter_code, year, flow)
            JOIN product_metrics AS pm USING (reporter_code, year, flow)
            JOIN partner_metrics AS pr USING (reporter_code, year, flow)
            LEFT JOIN standalone_partner_metrics AS spm USING (reporter_code, year, flow)
            ORDER BY t.reporter_code, t.year
            """
        ).fetch_df()
        partner_universe = con.execute(
            """
            WITH cell_partners AS (
                SELECT DISTINCT partner_code, TRUE AS in_cell_universe FROM cells
            ),
            standalone_partners AS (
                SELECT DISTINCT partner_code, TRUE AS in_standalone_partner_universe FROM standalone_partner
            )
            SELECT
                COALESCE(c.partner_code, s.partner_code) AS partner_code,
                COALESCE(c.in_cell_universe, FALSE) AS in_cell_universe,
                COALESCE(s.in_standalone_partner_universe, FALSE) AS in_standalone_partner_universe
            FROM cell_partners AS c
            FULL OUTER JOIN standalone_partners AS s USING (partner_code)
            ORDER BY 1
            """
        ).fetch_df()
        diagnostics = {
            "flow": flow,
            "cell_checkpoint_files": len(cell_paths),
            "standalone_partner_checkpoint_files": len(partner_paths),
            "product_universe_count": product_universe_count,
            "destination_universe_count": destination_universe_count,
            "cell_universe_count": cell_universe_count,
            "standalone_partner_universe_count": standalone_partner_universe_count,
            "rows": int(len(panel)),
            "reporters": int(panel["reporter_code"].nunique()),
            "years_min": int(panel["year"].min()),
            "years_max": int(panel["year"].max()),
            "total_trade_value": float(panel["total_trade_value"].sum()),
            "excluded_999999_product_id_rows": int(excluded_id_rows),
            "partner_code_0_rows": int(partner_zero_rows),
            "status": "ok",
        }
        return panel, diagnostics, partner_universe


def enrich_panel(panel: pd.DataFrame) -> pd.DataFrame:
    country_panel = read_country_panel()
    income = read_income_metadata()
    meta = country_panel.merge(income, on="iso3", how="left")
    meta["region"] = meta["region"].fillna("").astype(str)
    meta["income_group"] = meta["income_group"].fillna("").astype(str)
    out = panel.merge(meta, on="reporter_code", how="left", validate="many_to_one")
    out["country"] = out["country"].fillna(out["reporter_code"].astype(str))
    out["iso3"] = out["iso3"].fillna("")
    first = ["country", "iso3", "reporter_code", "year", "flow"]
    return out[first + [col for col in out.columns if col not in first]].copy()


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
        window = flow_frame[flow_frame["year"].between(start_year, end_year)]
        country_years = window.groupby("reporter_code")["year"].apply(lambda years: set(years.astype(int)))
        balanced_codes = sorted(int(code) for code, years in country_years.items() if required_years.issubset(years))
        if require_balanced_countries is not None and len(balanced_codes) < require_balanced_countries:
            raise RuntimeError(
                f"{flow} balanced window has {len(balanced_codes)} countries, below required {require_balanced_countries}."
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
                median_overall_product_destination_theil=("overall_product_destination_theil", "median"),
                mean_overall_product_destination_theil=("overall_product_destination_theil", "mean"),
                p10_overall_product_destination_theil=(
                    "overall_product_destination_theil",
                    lambda x: float(np.nanpercentile(x, 10)),
                ),
                p90_overall_product_destination_theil=(
                    "overall_product_destination_theil",
                    lambda x: float(np.nanpercentile(x, 90)),
                ),
                median_product_theil=("product_theil", "median"),
                median_destination_within_product_theil=("destination_within_product_theil", "median"),
                median_partner_theil_product_cell_based=("partner_theil_product_cell_based", "median"),
                median_product_within_partner_theil=("product_within_partner_theil", "median"),
                median_standalone_partner_theil_default=("standalone_partner_theil_default", "median"),
                median_active_product_share=("active_product_share", "median"),
                median_active_partner_share=("active_partner_share", "median"),
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
        latest = latest.sort_values("overall_product_destination_theil", ascending=False).reset_index(drop=True)
        latest.insert(0, "overall_theil_rank_desc", np.arange(1, len(latest) + 1))
        rows.append(latest)
    return pd.concat(rows, ignore_index=True)


def make_rich_proxy_summary(panel: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "flow",
        "year",
        "rich_proxy_countries_excluding_japan_korea",
        "japan_korea_countries_present",
        "rich_proxy_mean_overall_product_destination_theil",
        "japan_korea_mean_overall_product_destination_theil",
        "japan_korea_vs_rich_proxy_pct_gap",
        "rich_proxy_mean_product_theil",
        "japan_korea_mean_product_theil",
        "rich_proxy_mean_destination_within_product_theil",
        "japan_korea_mean_destination_within_product_theil",
        "rich_proxy_mean_partner_theil_product_cell_based",
        "japan_korea_mean_partner_theil_product_cell_based",
        "rich_proxy_mean_standalone_partner_theil_default",
        "japan_korea_mean_standalone_partner_theil_default",
    ]
    rows: list[dict[str, Any]] = []
    for (flow, year), group in panel.groupby(["flow", "year"], sort=True):
        rich = group[group["income_group"].eq("High income") & ~group["iso3"].isin(RICH_PROXY_EXCLUDE)].copy()
        jk = group[group["iso3"].isin(["JPN", "KOR"])].copy()
        if rich.empty or jk.empty:
            continue
        rich_mean = float(rich["overall_product_destination_theil"].mean())
        jk_mean = float(jk["overall_product_destination_theil"].mean())
        row = {
            "flow": flow,
            "year": int(year),
            "rich_proxy_countries_excluding_japan_korea": int(rich["iso3"].nunique()),
            "japan_korea_countries_present": int(jk["iso3"].nunique()),
            "rich_proxy_mean_overall_product_destination_theil": rich_mean,
            "japan_korea_mean_overall_product_destination_theil": jk_mean,
            "japan_korea_vs_rich_proxy_pct_gap": float(jk_mean / rich_mean - 1.0) if rich_mean > 0 else np.nan,
            "rich_proxy_mean_product_theil": float(rich["product_theil"].mean()),
            "japan_korea_mean_product_theil": float(jk["product_theil"].mean()),
            "rich_proxy_mean_destination_within_product_theil": float(rich["destination_within_product_theil"].mean()),
            "japan_korea_mean_destination_within_product_theil": float(jk["destination_within_product_theil"].mean()),
            "rich_proxy_mean_partner_theil_product_cell_based": float(rich["partner_theil_product_cell_based"].mean()),
            "japan_korea_mean_partner_theil_product_cell_based": float(jk["partner_theil_product_cell_based"].mean()),
            "rich_proxy_mean_standalone_partner_theil_default": float(rich["standalone_partner_theil_default"].mean()),
            "japan_korea_mean_standalone_partner_theil_default": float(jk["standalone_partner_theil_default"].mean()),
        }
        rows.append(row)
    return pd.DataFrame(rows, columns=columns)


def compare_to_gini(panel: pd.DataFrame) -> pd.DataFrame:
    out = panel[
        [
            "reporter_code",
            "year",
            "flow",
            "overall_product_destination_theil",
            "product_theil",
            "destination_within_product_theil",
            "partner_theil_product_cell_based",
            "standalone_partner_theil_default",
        ]
    ].copy()
    active_path = tcp.sample_processed_dir(COUNTRY_SAMPLE) / "concentration_all_years.parquet"
    fixed_path = tcp.sample_processed_dir(COUNTRY_SAMPLE) / "fixed_universe_product_gini_panel.parquet"
    fixed_theil_path = tcp.sample_processed_dir(COUNTRY_SAMPLE) / "fixed_universe_product_theil_panel.parquet"
    if active_path.exists():
        active = pd.read_parquet(
            active_path,
            columns=["reporter_code", "year", "flow", "product_gini", "partner_gini", "product_partner_cell_gini"],
        )
        if "variant" in active.columns:
            active = active[active["variant"].astype(str).str.lower().eq("baseline")].copy()
        out = out.merge(active, on=["reporter_code", "year", "flow"], how="left")
    if fixed_path.exists():
        fixed = pd.read_parquet(
            fixed_path,
            columns=["reporter_code", "year", "flow", "fixed_universe_product_gini", "active_product_gini"],
        )
        out = out.merge(fixed, on=["reporter_code", "year", "flow"], how="left")
    if fixed_theil_path.exists():
        fixed_theil = pd.read_parquet(
            fixed_theil_path,
            columns=[
                "reporter_code",
                "year",
                "flow",
                "fixed_universe_product_theil",
                "active_product_theil",
                "inactive_product_margin_theil",
                "total_trade_value",
            ],
        ).rename(columns={"total_trade_value": "fixed_product_theil_total_trade_value"})
        out = out.merge(fixed_theil, on=["reporter_code", "year", "flow"], how="left")
        out["product_theil_minus_existing_fixed_product_theil"] = out["product_theil"] - out["fixed_universe_product_theil"]
    return out


def compare_product_component_to_existing(panel: pd.DataFrame, args: argparse.Namespace) -> dict[str, Any]:
    path = tcp.sample_processed_dir(COUNTRY_SAMPLE) / "fixed_universe_product_theil_panel.parquet"
    if not path.exists():
        if official_run(args):
            raise RuntimeError(f"Missing existing fixed-universe product Theil panel: {path}")
        return {"status": "skipped_missing_existing_product_theil_panel"}
    existing = pd.read_parquet(
        path,
        columns=[
            "reporter_code",
            "year",
            "flow",
            "fixed_universe_product_theil",
            "active_product_theil",
            "inactive_product_margin_theil",
            "total_trade_value",
        ],
    )
    merged = panel.merge(existing, on=["reporter_code", "year", "flow"], how="left", validate="one_to_one", suffixes=("", "_existing"))
    missing = int(merged["fixed_universe_product_theil"].isna().sum())
    product_diff = (merged["product_theil"] - merged["fixed_universe_product_theil"]).abs()
    total_diff = (merged["total_trade_value"] - merged["total_trade_value_existing"]).abs()
    denom = merged["total_trade_value_existing"].abs().replace(0, np.nan)
    rel_total_diff = total_diff / denom
    details = {
        "status": "ok",
        "rows_compared": int(len(merged) - missing),
        "missing_existing_rows": missing,
        "max_abs_product_theil_diff": float(product_diff.max(skipna=True)) if not product_diff.empty else np.nan,
        "max_abs_total_trade_value_diff": float(total_diff.max(skipna=True)) if not total_diff.empty else np.nan,
        "max_relative_total_trade_value_diff": float(rel_total_diff.max(skipna=True)) if not rel_total_diff.empty else np.nan,
    }
    if official_run(args):
        if missing:
            raise RuntimeError(f"Product component comparison is missing {missing} existing rows.")
        if details["max_abs_product_theil_diff"] > PRODUCT_PANEL_THEIL_TOLERANCE:
            raise RuntimeError(
                "Product component does not reproduce existing fixed-universe product Theil panel: "
                f"max abs diff={details['max_abs_product_theil_diff']:.3g}"
            )
        if details["max_relative_total_trade_value_diff"] > PRODUCT_PANEL_REL_VALUE_TOLERANCE:
            raise RuntimeError(
                "Product-destination totals do not reproduce existing product-only totals: "
                f"max rel diff={details['max_relative_total_trade_value_diff']:.3g}"
            )
    else:
        details["status"] = "dryrun_not_enforced"
    return details


def validate_outputs(panel: pd.DataFrame, diagnostics: pd.DataFrame, args: argparse.Namespace) -> None:
    if official_run(args) and set(panel["flow"].dropna().unique()) != set(FLOW_CHOICES):
        raise RuntimeError("Official panel must contain both Exports and Imports.")
    if panel[["reporter_code", "year", "flow"]].duplicated().any():
        raise RuntimeError("Panel contains duplicate reporter-year-flow keys.")
    for col in [
        "overall_product_destination_theil",
        "product_theil",
        "destination_within_product_theil",
        "partner_theil_product_cell_based",
        "product_within_partner_theil",
    ]:
        if (panel[col].dropna() < -1e-10).any():
            raise RuntimeError(f"{col} contains negative Theil values.")
    norm_cols = [col for col in panel.columns if col.endswith("_normalized")]
    for col in norm_cols:
        values = panel[col].dropna()
        if (values < -1e-10).any() or (values > 1 + 1e-10).any():
            raise RuntimeError(f"{col} must lie inside [0, 1].")
    for col in [
        "product_margin_decomposition_residual",
        "product_first_decomposition_residual",
        "partner_first_decomposition_residual",
    ]:
        residual = panel[col].dropna().abs()
        if (residual > RESIDUAL_TOLERANCE).any():
            raise RuntimeError(f"{col} exceeds tolerance.")
    for flow, group in panel.groupby("flow"):
        for col in ["universe_product_count", "universe_partner_count", "universe_cell_count"]:
            if group[col].nunique() != 1:
                raise RuntimeError(f"{flow} {col} is not fixed.")
    if not diagnostics["status"].eq("ok").all():
        raise RuntimeError("Diagnostics contain non-ok statuses.")


def write_partner_universe(partner_universe: pd.DataFrame, args: argparse.Namespace) -> Path:
    ref = read_partner_reference()
    out = partner_universe.merge(ref, on="partner_code", how="left")
    out["partner_iso3"] = out["partner_iso3"].fillna("")
    out["partner_name"] = out["partner_name"].fillna("")
    out["aggregate_like_partner"] = out["aggregate_like_partner"].fillna(False).astype(bool)
    path = result_dir(args) / "product_destination_theil_partner_universe.csv"
    out.to_csv(path, index=False)
    return path


def write_unctad_bridge(panel: pd.DataFrame, args: argparse.Namespace) -> Path:
    path = result_dir(args) / "product_destination_theil_unctad_bridge.csv"
    rows: list[dict[str, Any]] = [
        {
            "source": "UNCTAD official series",
            "year": 2024,
            "flow": "Exports",
            "series": "Overall Theil Index",
            "developed_economies": 2.891801,
            "japan": 4.496925,
            "korea": 4.851701,
            "taiwan": 5.634568,
            "japan_korea_taiwan_simple_mean": 4.994398,
            "japan_korea_taiwan_vs_developed_pct_gap": 4.994398 / 2.891801 - 1.0,
            "note": "External UNCTAD SITC Rev.3 product-market Theil bridge used to reproduce the Economist 73% figure.",
        },
        {
            "source": "UNCTAD official series",
            "year": 2024,
            "flow": "Exports",
            "series": "Product concentration Theil index",
            "developed_economies": 0.819421,
            "japan": 1.586401,
            "korea": 1.776688,
            "taiwan": 2.380092,
            "japan_korea_taiwan_simple_mean": (1.586401 + 1.776688 + 2.380092) / 3.0,
            "japan_korea_taiwan_vs_developed_pct_gap": ((1.586401 + 1.776688 + 2.380092) / 3.0) / 0.819421 - 1.0,
            "note": "Official product component, not the rd2 HS6-family measure.",
        },
        {
            "source": "UNCTAD official series",
            "year": 2024,
            "flow": "Exports",
            "series": "Market per product concentration Theil index",
            "developed_economies": 2.072380,
            "japan": 2.910524,
            "korea": 3.075014,
            "taiwan": 3.254476,
            "japan_korea_taiwan_simple_mean": (2.910524 + 3.075014 + 3.254476) / 3.0,
            "japan_korea_taiwan_vs_developed_pct_gap": ((2.910524 + 3.075014 + 3.254476) / 3.0) / 2.072380 - 1.0,
            "note": "Official market-within-product component, not the rd2 HS6-family measure.",
        },
    ]
    if not panel.empty:
        exports_2024 = panel[(panel["flow"].eq("Exports")) & (panel["year"].eq(2024))].copy()
        rich = exports_2024[exports_2024["income_group"].eq("High income") & ~exports_2024["iso3"].isin(RICH_PROXY_EXCLUDE)]
        jk = exports_2024[exports_2024["iso3"].isin(["JPN", "KOR"])]
        if not rich.empty and not jk.empty:
            for series in [
                "overall_product_destination_theil",
                "product_theil",
                "destination_within_product_theil",
                "partner_theil_product_cell_based",
                "standalone_partner_theil_default",
            ]:
                rich_mean = float(rich[series].mean())
                jk_mean = float(jk[series].mean())
                rows.append(
                    {
                        "source": "rd2 HS6-family analogue",
                        "year": 2024,
                        "flow": "Exports",
                        "series": series,
                        "developed_economies": np.nan,
                        "japan": float(exports_2024.loc[exports_2024["iso3"].eq("JPN"), series].iloc[0])
                        if exports_2024["iso3"].eq("JPN").any()
                        else np.nan,
                        "korea": float(exports_2024.loc[exports_2024["iso3"].eq("KOR"), series].iloc[0])
                        if exports_2024["iso3"].eq("KOR").any()
                        else np.nan,
                        "taiwan": np.nan,
                        "japan_korea_taiwan_simple_mean": np.nan,
                        "japan_korea_vs_rd2_high_income_proxy_mean": jk_mean,
                        "rd2_high_income_proxy_excluding_japan_korea": rich_mean,
                        "japan_korea_vs_rd2_high_income_proxy_pct_gap": jk_mean / rich_mean - 1.0
                        if rich_mean > 0
                        else np.nan,
                        "note": "Taiwan is outside rd2; rd2 comparison uses Japan and Korea against high-income rd2 proxy.",
                    }
                )
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def write_report(
    panel: pd.DataFrame,
    diagnostics: pd.DataFrame,
    product_compare: dict[str, Any],
    balance: dict[str, Any],
    args: argparse.Namespace,
) -> Path:
    out_dir = result_dir(args)
    latest = make_latest_rankings(panel)
    rich = make_rich_proxy_summary(panel)
    rich_2024 = rich[(rich["flow"].eq("Exports")) & (rich["year"].eq(2024))] if not rich.empty else pd.DataFrame()
    if rich_2024.empty:
        jk_line = "- 2024 export Japan/Korea comparison unavailable."
    else:
        row = rich_2024.iloc[0]
        jk_line = (
            "- 2024 exports: Japan/Korea overall product-destination Theil mean "
            f"{row['japan_korea_mean_overall_product_destination_theil']:.3f}; "
            f"rd2 high-income proxy excluding Japan/Korea mean "
            f"{row['rich_proxy_mean_overall_product_destination_theil']:.3f}; "
            f"gap {row['japan_korea_vs_rich_proxy_pct_gap'] * 100:.1f}%."
        )
    lines = [
        "# Product-Destination Theil",
        "",
        f"Generated: {now_utc()}",
        f"Run type: {'official rd2 run' if official_run(args) else 'dry run'}",
        "",
        "## Definition",
        "",
        "Unit: rd2 reporter-year-flow over harmonized HS6-family product-by-destination cells.",
        "",
        "Inputs exclude HS6 `999999` before product-dependent aggregation and exclude `partnerCode == 0` World before destination/cell aggregation. Products are LT/HGL-weighted to HS1992/H0 families. The fixed product universe comes from 2000-2024 `world_broad`; the destination universe is the union of non-World partner codes observed in rd2 product-destination cells.",
        "",
        "`T_cell = sum_pd s_pd * log(s_pd * K_product * K_destination)`.",
        "",
        "`T_cell = T_product + T_destination_within_product` and `T_cell = T_partner + T_product_within_partner`.",
        "",
        "`T_product = T_active_product + log(K_product / A_product)`, where `A_product` is the active positive product-family count.",
        "",
        "Higher values mean trade value is concentrated in fewer product-destination cells, products, or destinations. Zero cells are included by fixed universe counts, not by materializing an all-zero Cartesian table.",
        "",
        "## Validation",
        "",
        f"- Product component comparison status: `{product_compare.get('status')}`.",
        f"- Max product-Theil diff versus product-only panel: {product_compare.get('max_abs_product_theil_diff')}.",
        f"- Max relative total-value diff versus product-only panel: {product_compare.get('max_relative_total_trade_value_diff')}.",
        *[
            f"- {row.flow}: K_product={int(row.product_universe_count):,}, "
            f"K_destination={int(row.destination_universe_count):,}, K_cell={int(row.cell_universe_count):,}, "
            f"rows={int(row.rows):,}"
            for row in diagnostics.itertuples(index=False)
        ],
        "",
        "## Japan/Korea Bridge",
        "",
        jk_line,
        "",
        "The UNCTAD/Economist 73% figure remains an external official SITC Rev.3 comparison. This panel shows whether the rd2 HS6-family product-destination analogue moves Japan/Korea closer to that official overall-Theil result.",
        "",
        "## Latest Highest Overall Product-Destination Theil",
        "",
    ]
    for flow, group in latest.groupby("flow", sort=True):
        lines.append(flow)
        lines.append("")
        for row in group.head(10).itertuples(index=False):
            lines.append(f"- {row.country} ({row.iso3}): {row.overall_product_destination_theil:.3f}")
        lines.append("")
    lines.extend(
        [
            "## Outputs",
            "",
            "- `product_destination_theil_all_years.csv`",
            "- `product_destination_theil_latest_rankings.csv`",
            "- `product_destination_theil_yearly_summary.csv`",
            "- `product_destination_theil_rich_proxy_summary.csv`",
            "- `product_destination_theil_gini_comparison.csv`",
            "- `product_destination_theil_unctad_bridge.csv`",
            "- `product_destination_theil_partner_universe.csv`",
            "- `product_destination_theil_manifest.json`",
        ]
    )
    path = out_dir / "product_destination_theil.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_outputs(
    panel: pd.DataFrame,
    diagnostics: pd.DataFrame,
    world_counts: pd.DataFrame,
    partner_universe: pd.DataFrame,
    product_compare: dict[str, Any],
    preflight: dict[str, Any],
    checkpoint_status: pd.DataFrame,
    balance: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Path]:
    out_dir = result_dir(args)
    out_dir.mkdir(parents=True, exist_ok=True)
    validate_outputs(panel, diagnostics, args)
    processed_panel_path(args).parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(processed_panel_path(args), index=False)
    paths: dict[str, Path] = {
        "processed_panel": processed_panel_path(args),
        "all_years": out_dir / "product_destination_theil_all_years.csv",
        "latest_rankings": out_dir / "product_destination_theil_latest_rankings.csv",
        "yearly_summary": out_dir / "product_destination_theil_yearly_summary.csv",
        "rich_proxy_summary": out_dir / "product_destination_theil_rich_proxy_summary.csv",
        "gini_comparison": out_dir / "product_destination_theil_gini_comparison.csv",
        "diagnostics": out_dir / "product_destination_theil_diagnostics.csv",
        "world_product_support_by_year": out_dir / "product_destination_theil_world_product_support_by_year.csv",
        "checkpoint_status": out_dir / "product_destination_theil_checkpoint_status.csv",
    }
    panel.to_csv(paths["all_years"], index=False)
    make_latest_rankings(panel).to_csv(paths["latest_rankings"], index=False)
    make_yearly_summary(panel).to_csv(paths["yearly_summary"], index=False)
    make_rich_proxy_summary(panel).to_csv(paths["rich_proxy_summary"], index=False)
    compare_to_gini(panel).to_csv(paths["gini_comparison"], index=False)
    diagnostics.to_csv(paths["diagnostics"], index=False)
    world_counts.to_csv(paths["world_product_support_by_year"], index=False)
    checkpoint_status.to_csv(paths["checkpoint_status"], index=False)
    paths["partner_universe"] = write_partner_universe(partner_universe, args)
    paths["unctad_bridge"] = write_unctad_bridge(panel, args)
    paths["report"] = write_report(panel, diagnostics, product_compare, balance, args)

    manifest = {
        "status": "complete",
        "generated_at_utc": now_utc(),
        "official_run": official_run(args),
        "country_sample": COUNTRY_SAMPLE,
        "benchmark_sample": BENCHMARK_SAMPLE,
        "benchmark_role": "fixed product-universe source only; not the reporter sample",
        "product_id_mode": PRODUCT_ID_MODE,
        "years": {"start_year": args.start_year, "end_year": args.end_year},
        "memory_and_cpu": {
            "memory_budget_gb": args.memory_budget_gb,
            "chunk_rows": args.chunk_rows,
            "compact_rows": args.compact_rows,
            "duckdb_threads": args.duckdb_threads,
            "workers": 1,
        },
        "preflight": preflight,
        "balanced_window": balance,
        "harmonization": {
            "method": "LT/HGL weighted conversion to HS1992/H0 product families before cell aggregation",
            "source_doi": tcp.LT_HGL_DATASET_DOI,
            "source_version": tcp.LT_HGL_DATASET_VERSION,
            "target": f"{tcp.LT_HGL_TARGET_LABEL}/{tcp.LT_HGL_TARGET_REVISION}",
        },
        "exclusions": {
            "hs6_999999": "excluded before product-destination aggregation, checkpoints, panels, downloads, and site data",
            "partner_code_0_world": "excluded before product-destination and partner aggregation",
            "aggregate_like_partners": "kept in default panel and labeled in partner universe diagnostics; aggregate exclusion is a sensitivity",
        },
        "measures": {
            "overall_product_destination_theil": {
                "unit": "reporter-year-flow product-destination cells",
                "formula": "sum_pd s_pd * log(s_pd * K_product * K_destination)",
                "normalization": "divide by log(K_product * K_destination)",
            },
            "product_theil": {
                "formula": "sum_p s_p * log(s_p * K_product)",
                "decomposition": "active_product_theil + log(K_product / active_product_count)",
            },
            "destination_within_product_theil": {
                "formula": "overall_product_destination_theil - product_theil",
            },
            "partner_theil_product_cell_based": {
                "formula": "sum_d s_d * log(s_d * K_destination), using product-filtered cells",
            },
            "standalone_partner_theil_default": {
                "formula": "sum_d s_d * log(s_d * K_partner_default)",
                "partner_convention": "products summed away; HS6 999999 included; partnerCode 0 excluded",
            },
        },
        "diagnostics": diagnostics.to_dict(orient="records"),
        "product_component_comparison": product_compare,
        "outputs": {name: rel(path) for name, path in paths.items()},
    }
    manifest_path = out_dir / "product_destination_theil_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, default=json_default) + "\n", encoding="utf-8")
    paths["manifest"] = manifest_path
    return paths


def run_metrics(args: argparse.Namespace, flows: list[str], preflight: dict[str, Any], checkpoint_status: pd.DataFrame) -> dict[str, Path]:
    product_universes: dict[str, pd.DataFrame] = {}
    world_counts: list[pd.DataFrame] = []
    for flow in flows:
        universe, counts = read_product_universe(flow, args.start_year, args.end_year)
        product_universes[flow] = universe
        world_counts.append(counts)
    panels: list[pd.DataFrame] = []
    diagnostics: list[dict[str, Any]] = []
    partner_universes: list[pd.DataFrame] = []
    for flow in flows:
        print(f"Computing product-destination Theil metrics for {flow}...", flush=True)
        flow_panel, flow_diag, flow_partner_universe = compute_flow_metrics(flow, product_universes[flow], args)
        panels.append(flow_panel)
        diagnostics.append(flow_diag)
        flow_partner_universe["flow"] = flow
        partner_universes.append(flow_partner_universe)
        log_resource(f"{flow} metrics", args.memory_budget_gb)
    panel = pd.concat(panels, ignore_index=True)
    panel = enrich_panel(panel).sort_values(["flow", "country", "year"]).reset_index(drop=True)
    require_balanced = args.require_balanced_countries if official_run(args) else None
    panel, balance = add_balanced_flags(panel, args.start_year, args.end_year, require_balanced)
    diagnostics_df = pd.DataFrame(diagnostics)
    product_compare = compare_product_component_to_existing(panel, args)
    world_counts_df = pd.concat(world_counts, ignore_index=True).sort_values(["flow", "year"])
    partner_universe_df = pd.concat(partner_universes, ignore_index=True).sort_values(["flow", "partner_code"])
    return write_outputs(
        panel,
        diagnostics_df,
        world_counts_df,
        partner_universe_df,
        product_compare,
        preflight,
        checkpoint_status,
        balance,
        args,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country-sample", default=COUNTRY_SAMPLE, choices=tcp.COUNTRY_SAMPLE_CHOICES)
    parser.add_argument("--benchmark-sample", default=BENCHMARK_SAMPLE, choices=tcp.COUNTRY_SAMPLE_CHOICES)
    parser.add_argument("--product-id-mode", default=PRODUCT_ID_MODE, choices=[PRODUCT_ID_MODE])
    parser.add_argument("--flow", default="all", choices=["all", *FLOW_CHOICES])
    parser.add_argument("--stage", default="all", choices=["all", "aggregate", "metrics"])
    parser.add_argument("--start-year", type=int, default=DEFAULT_START_YEAR)
    parser.add_argument("--end-year", type=int, default=DEFAULT_END_YEAR)
    parser.add_argument("--max-files", type=int, default=None)
    parser.add_argument("--fresh", action="store_true", help="Delete and rebuild this runner's checkpoints before processing.")
    parser.add_argument("--chunk-rows", type=int, default=DEFAULT_CHUNK_ROWS)
    parser.add_argument("--compact-rows", type=int, default=DEFAULT_COMPACT_ROWS)
    parser.add_argument("--memory-budget-gb", type=float, default=DEFAULT_MEMORY_BUDGET_GB)
    parser.add_argument("--duckdb-threads", type=int, default=1)
    parser.add_argument("--workers", type=int, default=1, help="Reserved for future raw-file parallelism; must be 1.")
    parser.add_argument("--require-balanced-countries", type=int, default=DEFAULT_REQUIRE_BALANCED_COUNTRIES)
    parser.add_argument("--write-compacted-cells", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.workers != 1:
        raise RuntimeError("Raw product-destination aggregation currently processes one file at a time; use --workers 1.")
    configure_sample(args)
    flows = list(FLOW_CHOICES) if args.flow == "all" else [args.flow]
    maybe_fresh_checkpoint(args)
    ensure_dirs(args, flows)
    files = raw_files_for_run(args)
    preflight = preflight_raw_files(files, args)
    checkpoint_frames: list[pd.DataFrame] = []
    if args.stage in {"all", "aggregate"}:
        for flow in flows:
            print(f"Aggregating raw product-destination cells for {flow}...", flush=True)
            checkpoint_frames.append(aggregate_flow(flow, files, args))
    else:
        for flow in flows:
            statuses = sorted(status_dir(args, flow).glob("*.json"))
            rows = [status_from_file(path) for path in statuses]
            checkpoint_frames.append(pd.DataFrame([row for row in rows if row is not None]))
    checkpoint_status = pd.concat(checkpoint_frames, ignore_index=True) if checkpoint_frames else pd.DataFrame()
    if args.stage in {"all", "metrics"}:
        paths = run_metrics(args, flows, preflight, checkpoint_status)
        print("Product-destination Theil outputs written:")
        for name, path in paths.items():
            print(f"- {name}: {path}")
    else:
        print(f"Aggregation complete. Checkpoints: {checkpoint_root(args)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
