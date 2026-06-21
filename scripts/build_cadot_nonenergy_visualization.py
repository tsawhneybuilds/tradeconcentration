#!/usr/bin/env python3
"""Build Cadot 156 non-energy import visualization artifacts.

The runner streams the world_broad raw Comtrade file set once. Every file
contributes positive harmonized non-energy product support to the fixed
universe; files belonging to Cadot reporters also retain compact import
product values for annual metrics and start/mid/end rank-bucket views.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
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
from concentration_metrics import active_gini, active_hhi  # noqa: E402


SAMPLE = tcp.CADOT_BROAD_SAMPLE
BENCHMARK_SAMPLE = tcp.WORLD_BROAD_SAMPLE
START_YEAR = 2000
END_YEAR = 2024
EXPECTED_REPORTERS = tcp.CADOT_BROAD_EXPECTED_REPORTERS
CHECKPOINT_NAME = "cadot_nonenergy_hs1992_visualization_checkpoints"
TABLE_NAME = "three_metric_tables"
BUCKETS = ("top5", "rank6_50", "rank51_200", "rank201_plus")
BUCKET_LABELS = {
    "top5": "Top 5",
    "rank6_50": "Ranks 6-50",
    "rank51_200": "Ranks 51-200",
    "rank201_plus": "Rank 201+ tail",
}
METRICS = ("gini", "theil", "hhi")
NONENERGY_BINS = ("capital_goods", "intermediates", "final_consumption")

_WORKER_MAPPING: pd.DataFrame | None = None
_WORKER_WEIGHTS: pd.DataFrame | None = None
_WORKER_CADOT_CODES: set[int] = set()
_WORKER_CHECKPOINT_ROOT: Path | None = None
_WORKER_CHUNK_ROWS = tcp.DEFAULT_CHUNK_ROWS


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=json_default) + "\n",
        encoding="utf-8",
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if math.isnan(float(value)) else float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    raise TypeError(type(value).__name__)


def result_dir() -> Path:
    return tcp.sample_results_dir(SAMPLE) / TABLE_NAME


def checkpoint_root() -> Path:
    return tcp.sample_processed_dir(SAMPLE) / "checkpoints" / CHECKPOINT_NAME


def checkpoint_path(kind: str, raw_path: Path) -> Path:
    return checkpoint_root() / kind / tcp.checkpoint_name_for_raw(raw_path)


def checkpoint_complete(raw_path: Path) -> bool:
    return all(
        checkpoint_path(kind, raw_path).exists()
        for kind in ("world_support", "diagnostics")
    ) and (
        checkpoint_path("cadot_import_products", raw_path).exists()
        or checkpoint_path("not_cadot", raw_path).exists()
    )


def prepare_dirs(fresh: bool) -> None:
    root = checkpoint_root()
    if fresh and root.exists():
        shutil.rmtree(root)
    for kind in ("world_support", "cadot_import_products", "diagnostics", "not_cadot"):
        (root / kind).mkdir(parents=True, exist_ok=True)
    result_dir().mkdir(parents=True, exist_ok=True)


def load_mapping() -> pd.DataFrame:
    mapping = tcp.load_approved_bec5_mapping()[
        ["classification_code", "cmd_code", "exercise_03_bin", "mapping_status"]
    ].copy()
    mapping["classification_code"] = mapping["classification_code"].map(
        tcp.normalize_hs_classification_code
    )
    mapping["cmd_code"] = tcp.hs6_code_series(mapping["cmd_code"])
    return mapping.drop_duplicates(["classification_code", "cmd_code"])


def init_worker(
    mapping: pd.DataFrame,
    weights: pd.DataFrame,
    cadot_codes: set[int],
    root: str,
    chunk_rows: int,
) -> None:
    global _WORKER_MAPPING, _WORKER_WEIGHTS, _WORKER_CADOT_CODES
    global _WORKER_CHECKPOINT_ROOT, _WORKER_CHUNK_ROWS
    _WORKER_MAPPING = mapping
    _WORKER_WEIGHTS = weights
    _WORKER_CADOT_CODES = cadot_codes
    _WORKER_CHECKPOINT_ROOT = Path(root)
    _WORKER_CHUNK_ROWS = chunk_rows


def worker_checkpoint_path(kind: str, raw_path: Path) -> Path:
    assert _WORKER_CHECKPOINT_ROOT is not None
    return _WORKER_CHECKPOINT_ROOT / kind / tcp.checkpoint_name_for_raw(raw_path)


def add_product_values(
    current: pd.DataFrame | None,
    converted: pd.DataFrame,
) -> pd.DataFrame:
    grouped = (
        converted.groupby(["flow", "cmd_code"], as_index=False)["trade_value"]
        .sum()
    )
    if current is None or current.empty:
        return grouped
    return (
        pd.concat([current, grouped], ignore_index=True)
        .groupby(["flow", "cmd_code"], as_index=False)["trade_value"]
        .sum()
    )


def process_file(raw_path_text: str) -> dict[str, Any]:
    raw_path = Path(raw_path_text)
    metadata = tcp.bulk_file_metadata(raw_path)
    if metadata is None:
        raise RuntimeError(f"Could not parse raw metadata: {raw_path.name}")
    assert _WORKER_MAPPING is not None
    assert _WORKER_WEIGHTS is not None

    product_values: pd.DataFrame | None = None
    source_value = 0.0
    converted_value = 0.0
    source_rows = 0
    converted_rows = 0
    ambiguous_rows = 0
    ambiguous_value = 0.0
    energy_rows = 0
    energy_value = 0.0
    for leaf in tcp.iter_leaf_trade_chunks(raw_path, chunk_rows=_WORKER_CHUNK_ROWS):
        leaf["classification_code"] = leaf["classification_code"].map(
            tcp.normalize_hs_classification_code
        )
        leaf["cmd_code"] = tcp.hs6_code_series(leaf["cmd_code"])
        leaf = tcp.drop_excluded_hs6(leaf)
        if leaf.empty:
            continue
        mapped = leaf.merge(
            _WORKER_MAPPING,
            on=["classification_code", "cmd_code"],
            how="left",
            validate="many_to_one",
        )
        mapped["exercise_03_bin"] = (
            mapped["exercise_03_bin"]
            .fillna("unmapped_or_ambiguous")
            .replace("", "unmapped_or_ambiguous")
        )
        ambiguous = mapped["exercise_03_bin"].eq("unmapped_or_ambiguous")
        energy = mapped["exercise_03_bin"].eq("energy")
        ambiguous_rows += int(ambiguous.sum())
        ambiguous_value += float(mapped.loc[ambiguous, "trade_value"].sum())
        energy_rows += int(energy.sum())
        energy_value += float(mapped.loc[energy, "trade_value"].sum())
        nonenergy = mapped[
            mapped["exercise_03_bin"].isin(NONENERGY_BINS)
        ].copy()
        if nonenergy.empty:
            continue
        source_value += float(nonenergy["trade_value"].sum())
        source_rows += len(nonenergy)
        converted = tcp.apply_lt_hgl_hs1992_conversion(
            nonenergy[["classification_code", "cmd_code", "flow", "trade_value"]],
            weights=_WORKER_WEIGHTS,
        )
        converted_value += float(converted["trade_value"].sum())
        converted_rows += len(converted)
        product_values = add_product_values(product_values, converted)

    if product_values is None:
        product_values = pd.DataFrame(columns=["flow", "cmd_code", "trade_value"])
    product_values = product_values[product_values["trade_value"] > 0].copy()
    product_values["cmd_code"] = tcp.hs6_code_series(product_values["cmd_code"])
    if product_values["cmd_code"].eq("999999").any():
        raise RuntimeError(f"Excluded HS6 999999 reached harmonized output: {raw_path.name}")

    support = product_values[["flow", "cmd_code"]].drop_duplicates()
    support["product_id"] = "HS1992:" + support["cmd_code"]
    support.to_parquet(worker_checkpoint_path("world_support", raw_path), index=False)

    reporter_code = int(metadata["reporter_code"])
    if reporter_code in _WORKER_CADOT_CODES:
        imports = product_values[product_values["flow"].eq("Imports")].copy()
        imports["reporter_code"] = reporter_code
        imports["year"] = int(metadata["year"])
        imports["source_classification_code"] = str(metadata["classification_code"])
        imports["source_raw_file"] = raw_path.name
        imports.to_parquet(
            worker_checkpoint_path("cadot_import_products", raw_path),
            index=False,
        )
    else:
        worker_checkpoint_path("not_cadot", raw_path).write_text("", encoding="utf-8")

    diagnostics = pd.DataFrame(
        [
            {
                "reporter_code": reporter_code,
                "year": int(metadata["year"]),
                "source_classification_code": str(metadata["classification_code"]),
                "source_raw_file": raw_path.name,
                "is_cadot_reporter": reporter_code in _WORKER_CADOT_CODES,
                "source_nonenergy_rows": source_rows,
                "converted_nonenergy_rows": converted_rows,
                "source_nonenergy_value": source_value,
                "converted_nonenergy_value": converted_value,
                "conversion_value_residual": converted_value - source_value,
                "excluded_ambiguous_rows": ambiguous_rows,
                "excluded_ambiguous_value": ambiguous_value,
                "excluded_energy_rows": energy_rows,
                "excluded_energy_value": energy_value,
                "world_support_rows": len(support),
                "cadot_import_product_rows": (
                    int((product_values["flow"] == "Imports").sum())
                    if reporter_code in _WORKER_CADOT_CODES
                    else 0
                ),
            }
        ]
    )
    diagnostics.to_parquet(worker_checkpoint_path("diagnostics", raw_path), index=False)
    return {
        "raw_file": raw_path.name,
        "reporter_code": reporter_code,
        "year": int(metadata["year"]),
        "is_cadot_reporter": reporter_code in _WORKER_CADOT_CODES,
        "world_support_rows": len(support),
        "cadot_import_product_rows": int(diagnostics.iloc[0]["cadot_import_product_rows"]),
        "conversion_value_residual": float(converted_value - source_value),
    }


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
    labels = pd.DataFrame(rows).drop_duplicates("cmd_code")
    return labels


def rank_bucket_masks(rank: pd.Series) -> dict[str, pd.Series]:
    return {
        "top5": rank <= 5,
        "rank6_50": rank.between(6, 50),
        "rank51_200": rank.between(51, 200),
        "rank201_plus": rank > 200,
    }


def metric_decomposition(
    product: pd.DataFrame,
    fixed_universe_count: int,
) -> tuple[dict[str, Any], pd.DataFrame]:
    work = product.groupby("cmd_code", as_index=False)["trade_value"].sum()
    work = work[work["trade_value"] > 0].sort_values(
        ["trade_value", "cmd_code"], ascending=[False, True]
    )
    total = float(work["trade_value"].sum())
    if total <= 0:
        return {}, work
    work["rank"] = np.arange(1, len(work) + 1)
    work["share"] = work["trade_value"] / total
    n = len(work)
    work["gini_contribution"] = (
        (n - 2 * work["rank"] + 1) / n
    ) * work["share"]
    work["theil_contribution"] = work["share"] * np.log(
        work["share"] * fixed_universe_count
    )
    work["hhi_contribution"] = np.square(work["share"])
    row: dict[str, Any] = {
        "active_nonenergy_products": n,
        "total_nonenergy_imports": total,
        "gini": float(work["gini_contribution"].sum()),
        "theil": float(work["theil_contribution"].sum()),
        "hhi": float(work["hhi_contribution"].sum()),
        "direct_active_gini": active_gini(work["trade_value"]),
        "direct_active_hhi": active_hhi(work["trade_value"]),
        "fixed_nonenergy_universe_count": fixed_universe_count,
        "top10_share": float(work.loc[work["rank"] <= 10, "share"].sum()),
    }
    for bucket, mask in rank_bucket_masks(work["rank"]).items():
        row[f"{bucket}_share"] = float(work.loc[mask, "share"].sum())
        for metric in METRICS:
            row[f"{bucket}_{metric}_contribution"] = float(
                work.loc[mask, f"{metric}_contribution"].sum()
            )
    return row, work


def driver_group(direction: str, bucket: str) -> str:
    labels = {
        "top5": "top-5 superstar concentration",
        "rank6_50": "broader upper-tier concentration",
        "rank51_200": "middle-tail change",
        "rank201_plus": "long-tail compression or expansion",
    }
    if direction == "stable":
        return "stable / small metric change"
    return labels[bucket]


def finalize(files: list[Path], cadot_panel: pd.DataFrame) -> dict[str, Any]:
    support_frames = [
        pd.read_parquet(checkpoint_path("world_support", path))
        for path in files
        if checkpoint_path("world_support", path).exists()
    ]
    support = pd.concat(support_frames, ignore_index=True).drop_duplicates(
        ["flow", "cmd_code"]
    )
    universe_counts = support.groupby("flow")["cmd_code"].nunique().to_dict()
    if "Imports" not in universe_counts or universe_counts["Imports"] <= 0:
        raise RuntimeError("World non-energy import fixed universe is empty.")
    support.sort_values(["flow", "cmd_code"]).to_csv(
        result_dir() / "nonenergy_world_hs1992_product_universe.csv", index=False
    )

    meta = cadot_panel.set_index("reporter_code")[["country", "iso3"]].to_dict("index")
    product_paths = [
        checkpoint_path("cadot_import_products", path)
        for path in files
        if checkpoint_path("cadot_import_products", path).exists()
    ]
    annual_rows: list[dict[str, Any]] = []
    available: dict[int, list[tuple[int, Path]]] = {}
    max_direct_metric_residual = 0.0
    max_contribution_residual = 0.0
    max_share_residual = 0.0
    for path in product_paths:
        product = pd.read_parquet(path)
        if product.empty:
            continue
        reporter_code = int(product["reporter_code"].iloc[0])
        year = int(product["year"].iloc[0])
        available.setdefault(reporter_code, []).append((year, path))
        metrics, _ = metric_decomposition(
            product, int(universe_counts["Imports"])
        )
        country = meta[reporter_code]
        row = {
            "country": country["country"],
            "iso3": country["iso3"],
            "reporter_code": reporter_code,
            "year": year,
            "flow": "Imports",
            "source_raw_file": product["source_raw_file"].iloc[0],
            **metrics,
        }
        annual_rows.append(row)
        max_direct_metric_residual = max(
            max_direct_metric_residual,
            abs(float(metrics["gini"]) - float(metrics["direct_active_gini"])),
            abs(float(metrics["hhi"]) - float(metrics["direct_active_hhi"])),
        )
        max_contribution_residual = max(
            max_contribution_residual,
            *[
                abs(
                    sum(
                        float(metrics[f"{bucket}_{metric}_contribution"])
                        for bucket in BUCKETS
                    )
                    - float(metrics[metric])
                )
                for metric in METRICS
            ],
        )
        max_share_residual = max(
            max_share_residual,
            abs(
                sum(float(metrics[f"{bucket}_share"]) for bucket in BUCKETS)
                - 1.0
            ),
        )

    annual = pd.DataFrame(annual_rows).sort_values(
        ["country", "year"]
    ).reset_index(drop=True)
    annual.to_csv(result_dir() / "nonenergy_import_metric_annual.csv", index=False)
    coverage = (
        annual.groupby(
            ["country", "iso3", "reporter_code", "flow"], as_index=False
        )
        .agg(
            first_available_year=("year", "min"),
            last_available_year=("year", "max"),
            available_years=("year", "nunique"),
        )
        .sort_values(["country", "reporter_code"])
    )
    coverage["has_2000"] = coverage["first_available_year"].le(START_YEAR)
    coverage["has_2024"] = coverage["last_available_year"].ge(END_YEAR)
    coverage.to_csv(
        result_dir() / "nonenergy_import_reporter_coverage.csv", index=False
    )

    labels = h0_product_labels()
    snapshot_rows: list[dict[str, Any]] = []
    top_rows: list[pd.DataFrame] = []
    for reporter_code, entries in sorted(available.items()):
        entries = sorted(entries)
        positions = [
            ("start", entries[0]),
            ("mid", entries[len(entries) // 2]),
            ("end", entries[-1]),
        ]
        seen: set[tuple[str, int]] = set()
        for snapshot, (year, path) in positions:
            if (snapshot, year) in seen:
                continue
            seen.add((snapshot, year))
            product = pd.read_parquet(path)
            metrics, ranked = metric_decomposition(
                product, int(universe_counts["Imports"])
            )
            country = meta[reporter_code]
            snapshot_rows.append(
                {
                    "country": country["country"],
                    "iso3": country["iso3"],
                    "reporter_code": reporter_code,
                    "snapshot": snapshot,
                    "year": year,
                    "flow": "Imports",
                    "source_raw_file": product["source_raw_file"].iloc[0],
                    **metrics,
                }
            )
            top = ranked.head(10).copy()
            top["country"] = country["country"]
            top["iso3"] = country["iso3"]
            top["reporter_code"] = reporter_code
            top["snapshot"] = snapshot
            top["year"] = year
            top["total_nonenergy_imports"] = metrics[
                "total_nonenergy_imports"
            ]
            top_rows.append(top)

    snapshots = pd.DataFrame(snapshot_rows).sort_values(
        ["country", "year", "snapshot"]
    )
    snapshots.to_csv(
        result_dir() / "nonenergy_import_rank_bucket_snapshots.csv", index=False
    )
    top_products = pd.concat(top_rows, ignore_index=True).merge(
        labels, on="cmd_code", how="left"
    )
    missing_official_labels = top_products["product_label"].fillna("").str.strip().eq("")
    top_products["product_label"] = top_products["product_label"].fillna(
        "HS1992 " + top_products["cmd_code"].astype(str)
    )
    top_products.to_csv(
        result_dir() / "nonenergy_import_top_products_snapshots.csv", index=False
    )

    driver_rows: list[dict[str, Any]] = []
    for reporter_code, group in snapshots.groupby("reporter_code"):
        start = group[group["snapshot"].eq("start")]
        end = group[group["snapshot"].eq("end")]
        if start.empty or end.empty:
            continue
        start_row = start.iloc[0]
        end_row = end.iloc[-1]
        for metric in METRICS:
            deltas = {
                bucket: float(
                    end_row[f"{bucket}_{metric}_contribution"]
                    - start_row[f"{bucket}_{metric}_contribution"]
                )
                for bucket in BUCKETS
            }
            bucket = max(BUCKETS, key=lambda item: abs(deltas[item]))
            delta_metric = float(end_row[metric] - start_row[metric])
            direction = (
                "stable"
                if abs(delta_metric) < 1e-9
                else ("increase" if delta_metric > 0 else "decrease")
            )
            driver_rows.append(
                {
                    "country": end_row["country"],
                    "iso3": end_row["iso3"],
                    "reporter_code": reporter_code,
                    "metric": metric,
                    "start_year": int(start_row["year"]),
                    "end_year": int(end_row["year"]),
                    "start_metric": float(start_row[metric]),
                    "end_metric": float(end_row[metric]),
                    "delta_metric": delta_metric,
                    "metric_change_direction": direction,
                    "main_driver_bucket": bucket,
                    "main_driver_bucket_label": BUCKET_LABELS[bucket],
                    "main_driver_group": driver_group(direction, bucket),
                    **{
                        f"delta_{key}_contribution": value
                        for key, value in deltas.items()
                    },
                }
            )
    drivers = pd.DataFrame(driver_rows).sort_values(["metric", "country"])
    drivers.to_csv(
        result_dir() / "nonenergy_import_rank_bucket_drivers.csv", index=False
    )
    driver_delta_columns = [
        f"delta_{bucket}_contribution" for bucket in BUCKETS
    ]
    max_driver_residual = float(
        (
            drivers[driver_delta_columns].sum(axis=1)
            - drivers["delta_metric"]
        )
        .abs()
        .max()
    )

    diagnostics = pd.concat(
        [
            pd.read_parquet(checkpoint_path("diagnostics", path))
            for path in files
            if checkpoint_path("diagnostics", path).exists()
        ],
        ignore_index=True,
    )
    conversion_residual = float(
        diagnostics["conversion_value_residual"].abs().max()
    )
    conversion_scale = float(
        diagnostics["source_nonenergy_value"].abs().max()
    )
    conversion_tolerance = max(1e-4, conversion_scale * 1e-10)
    checks = [
        {
            "check": "cadot_reporter_count_exact",
            "passed": cadot_panel["reporter_code"].nunique() == EXPECTED_REPORTERS,
            "value": cadot_panel["reporter_code"].nunique(),
            "expected": EXPECTED_REPORTERS,
        },
        {
            "check": "annual_reporters_exact",
            "passed": annual["reporter_code"].nunique() == EXPECTED_REPORTERS,
            "value": annual["reporter_code"].nunique(),
            "expected": EXPECTED_REPORTERS,
        },
        {
            "check": "years_within_2000_2024",
            "passed": bool(annual["year"].between(START_YEAR, END_YEAR).all()),
            "value": f"{annual['year'].min()}-{annual['year'].max()}",
            "expected": f"{START_YEAR}-{END_YEAR}",
        },
        {
            "check": "global_coverage_reaches_2000_2024",
            "passed": (
                int(annual["year"].min()) == START_YEAR
                and int(annual["year"].max()) == END_YEAR
            ),
            "value": f"{annual['year'].min()}-{annual['year'].max()}",
            "expected": f"{START_YEAR}-{END_YEAR}",
        },
        {
            "check": "annual_key_unique",
            "passed": not annual.duplicated(["reporter_code", "year", "flow"]).any(),
            "value": int(annual.duplicated(["reporter_code", "year", "flow"]).sum()),
            "expected": 0,
        },
        {
            "check": "snapshot_bucket_shares_sum_to_one",
            "passed": max_share_residual <= 1e-10,
            "value": max_share_residual,
            "expected": "<=1e-10",
        },
        {
            "check": "three_snapshots_per_reporter",
            "passed": bool(
                snapshots.groupby("reporter_code").size().eq(3).all()
                and snapshots["reporter_code"].nunique() == EXPECTED_REPORTERS
            ),
            "value": (
                f"{snapshots['reporter_code'].nunique()} reporters; "
                f"{snapshots.groupby('reporter_code').size().min()}-"
                f"{snapshots.groupby('reporter_code').size().max()} snapshots"
            ),
            "expected": f"{EXPECTED_REPORTERS} reporters; 3 snapshots",
        },
        {
            "check": "ten_top_products_per_snapshot",
            "passed": bool(
                top_products.groupby(["reporter_code", "snapshot"])
                .size()
                .eq(10)
                .all()
            ),
            "value": (
                f"{top_products.groupby(['reporter_code', 'snapshot']).size().min()}-"
                f"{top_products.groupby(['reporter_code', 'snapshot']).size().max()}"
            ),
            "expected": "10",
        },
        {
            "check": "driver_contributions_reconcile",
            "passed": max_driver_residual <= 1e-10,
            "value": max_driver_residual,
            "expected": "<=1e-10",
        },
        {
            "check": "metric_contributions_reconcile",
            "passed": max_contribution_residual <= 1e-10,
            "value": max_contribution_residual,
            "expected": "<=1e-10",
        },
        {
            "check": "direct_gini_hhi_reconcile",
            "passed": max_direct_metric_residual <= 1e-10,
            "value": max_direct_metric_residual,
            "expected": "<=1e-10",
        },
        {
            "check": "conversion_value_preserved",
            "passed": conversion_residual <= conversion_tolerance,
            "value": conversion_residual,
            "expected": f"<={conversion_tolerance}",
        },
        {
            "check": "no_999999_product_output",
            "passed": not top_products["cmd_code"].astype(str).str.zfill(6).eq("999999").any(),
            "value": int(
                top_products["cmd_code"].astype(str).str.zfill(6).eq("999999").sum()
            ),
            "expected": 0,
        },
        {
            "check": "official_hs1992_plain_english_labels_complete",
            "passed": not missing_official_labels.any(),
            "value": int(missing_official_labels.sum()),
            "expected": 0,
        },
        {
            "check": "world_universe_has_no_999999",
            "passed": not support["cmd_code"].astype(str).str.zfill(6).eq("999999").any(),
            "value": int(
                support["cmd_code"].astype(str).str.zfill(6).eq("999999").sum()
            ),
            "expected": 0,
        },
        {
            "check": "fixed_universe_import_positive",
            "passed": int(universe_counts["Imports"]) > 0,
            "value": int(universe_counts["Imports"]),
            "expected": ">0",
        },
    ]
    validation = pd.DataFrame(checks)
    validation.to_csv(
        result_dir() / "nonenergy_visualization_validation_checks.csv", index=False
    )
    if not validation["passed"].all():
        failed = validation.loc[~validation["passed"], "check"].tolist()
        raise RuntimeError(f"Non-energy visualization validation failed: {failed}")

    output_names = [
        "nonenergy_import_metric_annual.csv",
        "nonenergy_import_reporter_coverage.csv",
        "nonenergy_import_rank_bucket_snapshots.csv",
        "nonenergy_import_top_products_snapshots.csv",
        "nonenergy_import_rank_bucket_drivers.csv",
        "nonenergy_world_hs1992_product_universe.csv",
        "nonenergy_visualization_validation_checks.csv",
    ]
    output_artifacts = {
        name: {
            "size_bytes": int((result_dir() / name).stat().st_size),
            "sha256": file_sha256(result_dir() / name),
        }
        for name in output_names
    }
    manifest = {
        "created_at_utc": now_utc(),
        "country_sample": SAMPLE,
        "benchmark_sample": BENCHMARK_SAMPLE,
        "reporters": int(cadot_panel["reporter_code"].nunique()),
        "year_start": START_YEAR,
        "year_end": END_YEAR,
        "world_raw_files": len(files),
        "cadot_annual_rows": len(annual),
        "reporter_coverage": {
            "reporters_with_2000": int(coverage["has_2000"].sum()),
            "reporters_with_2024": int(coverage["has_2024"].sum()),
            "minimum_available_years": int(coverage["available_years"].min()),
            "maximum_available_years": int(coverage["available_years"].max()),
        },
        "snapshot_rows": len(snapshots),
        "top_product_rows": len(top_products),
        "driver_rows": len(drivers),
        "product_id_mode": "harmonized_hs6_family",
        "harmonization_method": "lt_hgl_weighted_hs1992",
        "harmonization_target": "HS1992/H0",
        "harmonization_doi": "10.7910/DVN/6AADMR",
        "harmonization_version": "2.1",
        "fixed_universe_source": BENCHMARK_SAMPLE,
        "fixed_universe_counts": {
            str(flow): int(count) for flow, count in universe_counts.items()
        },
        "nonenergy_filter": "mapped_nonenergy_bins_only",
        "nonenergy_bins": list(NONENERGY_BINS),
        "nonenergy_rule": (
            "approved Exercise 3 BEC mapping; retain only mapped capital goods, "
            "intermediates, and final consumption before LT/HGL conversion"
        ),
        "product_exclusion": "source HS6 999999 excluded before product-dependent aggregation",
        "partner_exclusion": "partnerCode 0 excluded by leaf extraction",
        "checkpoint_namespace": CHECKPOINT_NAME,
        "checkpoint_inventory": {
            kind: len(list((checkpoint_root() / kind).glob("*")))
            for kind in [
                "world_support",
                "cadot_import_products",
                "diagnostics",
                "not_cadot",
            ]
        },
        "pipeline_entry_point": "scripts/build_cadot_nonenergy_visualization.py",
        "shared_extraction_module": "scripts/trade_concentration_pipeline.py",
        "metric_module": "scripts/concentration_metrics.py",
        "bec_mapping_approval": (
            "results/samples/cadot_broad_156/exercise_03_tables/"
            "bec5_mapping_approval.json"
        ),
        "hs1992_label_source": "data/raw/classifications/H0.json",
        "software_versions": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
        "outputs": output_names,
        "output_artifacts": output_artifacts,
    }
    write_json(result_dir() / "nonenergy_visualization_manifest.json", manifest)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--chunk-rows", type=int, default=500_000)
    parser.add_argument("--max-files", type=int, default=None)
    parser.add_argument("--fresh-checkpoints", action="store_true")
    parser.add_argument("--finalize-only", action="store_true")
    parser.add_argument("--checkpoint-only", action="store_true")
    parser.add_argument("--manifest-every", type=int, default=50)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")

    tcp.configure_country_sample(
        country_sample=SAMPLE, start_year=START_YEAR, end_year=END_YEAR
    )
    cadot_panel = tcp.save_country_panel()
    if cadot_panel["reporter_code"].nunique() != EXPECTED_REPORTERS:
        raise RuntimeError(
            f"Expected {EXPECTED_REPORTERS} Cadot reporters; "
            f"found {cadot_panel['reporter_code'].nunique()}."
        )
    cadot_codes = set(cadot_panel["reporter_code"].astype(int))

    tcp.configure_country_sample(
        country_sample=BENCHMARK_SAMPLE, start_year=START_YEAR, end_year=END_YEAR
    )
    files = tcp.hs_bulk_files(max_files=args.max_files)
    if not files:
        raise RuntimeError("No world_broad raw files are available.")
    missing = tcp.missing_bulk_keys_for_active_sample(files)
    if missing and args.max_files is None:
        raise RuntimeError(
            f"world_broad is missing {len(missing)} required raw keys."
        )

    prepare_dirs(args.fresh_checkpoints)
    mapping = load_mapping()
    weights = tcp.load_lt_hgl_hs1992_conversion_weights()
    pending = [path for path in files if not checkpoint_complete(path)]
    if args.finalize_only and pending:
        raise RuntimeError(
            f"Cannot finalize: {len(pending)} raw checkpoints are missing."
        )
    if not args.finalize_only and pending:
        completed = 0
        with ProcessPoolExecutor(
            max_workers=max(1, args.workers),
            initializer=init_worker,
            initargs=(
                mapping,
                weights,
                cadot_codes,
                str(checkpoint_root()),
                args.chunk_rows,
            ),
        ) as pool:
            futures = {pool.submit(process_file, str(path)): path for path in pending}
            tail: list[dict[str, Any]] = []
            for future in as_completed(futures):
                row = future.result()
                completed += 1
                tail.append(row)
                if completed % args.manifest_every == 0 or completed == len(pending):
                    write_json(
                        result_dir() / "nonenergy_visualization_checkpoint_manifest.json",
                        {
                            "updated_at_utc": now_utc(),
                            "raw_files_total": len(files),
                            "pending_at_start": len(pending),
                            "completed_this_run": completed,
                            "tail": tail[-50:],
                        },
                    )
                    print(
                        f"[{completed}/{len(pending)}] "
                        f"non-energy checkpoints complete",
                        flush=True,
                    )

    if args.checkpoint_only:
        return 0
    manifest = finalize(files, cadot_panel)
    print(json.dumps(manifest, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
