#!/usr/bin/env python3
"""Compute historical world-relative product Gini measures for rd2 exports or imports."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import trade_concentration_pipeline as tcp  # noqa: E402
from concentration_metrics import weighted_gini  # noqa: E402


EXCLUDED_HS6_CODES = {"999999"}
DEFAULT_FLOW = "Exports"
FLOW_CHOICES = ("Exports", "Imports")
PARTIAL_SUBDIR = "world_relative_product_gini_file_aggregates"
PRODUCT_COLUMNS = ["reporter_code", "year", "classification_code", "cmd_code", "trade_value"]
PRODUCT_ID_COLUMN = "product_id"
PRODUCT_KEY_COLUMNS = ["reporter_code", "year", PRODUCT_ID_COLUMN]
PRODUCT_ID_MODES = ("native_hs6", "harmonized_hs6_family")


def flow_slug(flow: str) -> str:
    return {"Exports": "export", "Imports": "import"}[flow]


def flow_value_noun(flow: str) -> str:
    return {"Exports": "exports", "Imports": "imports"}[flow]


def flow_total_column(flow: str, prefix: str) -> str:
    return f"{prefix}_total_{flow_value_noun(flow)}"


def world_product_column(flow: str) -> str:
    return f"world_product_{flow_value_noun(flow)}"


def zero_weight_column(flow: str) -> str:
    return f"zero_weight_country_{flow_slug(flow)}_share"


def active_total_column(flow: str) -> str:
    return f"active_product_total_{flow_value_noun(flow)}"


def artifact_stem(flow: str) -> str:
    return "world_relative_product_gini" if flow == "Exports" else "world_relative_import_product_gini"


def tables_dirname(flow: str) -> str:
    return "world_relative_product_gini_tables" if flow == "Exports" else "world_relative_import_product_gini_tables"


def metric_alias_column(flow: str) -> str:
    return "world_relative_product_gini" if flow == "Exports" else "world_relative_import_product_gini"


def product_id_label(product_id_mode: str) -> str:
    return {
        "native_hs6": "native HS6 products",
        "harmonized_hs6_family": "LT/HGL-weighted HS1992 products",
    }.get(product_id_mode, product_id_mode)


def product_key_column(frame: pd.DataFrame) -> str:
    if PRODUCT_ID_COLUMN in frame.columns:
        return PRODUCT_ID_COLUMN
    if "cmd_code" in frame.columns:
        return "cmd_code"
    raise RuntimeError("Product aggregate is missing both `product_id` and `cmd_code`.")


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def output_dirs(country_sample: str, flow: str = DEFAULT_FLOW) -> tuple[Path, Path]:
    result_dir = tcp.sample_results_dir(country_sample) / tables_dirname(flow)
    processed_dir = tcp.sample_processed_dir(country_sample)
    result_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    return result_dir, processed_dir


def partial_dir(sample_name: str, flow: str = DEFAULT_FLOW) -> Path:
    return tcp.sample_processed_dir(sample_name) / "checkpoints" / PARTIAL_SUBDIR / f"product_{flow_value_noun(flow)}"


def partial_path_for_raw(raw_path: Path, sample_name: str, flow: str = DEFAULT_FLOW) -> Path:
    return partial_dir(sample_name, flow) / tcp.checkpoint_name_for_raw(raw_path)


def write_parquet_atomic(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)


def partial_has_current_schema(path: Path) -> bool:
    """Return True only when a cached partial has the current safe schema."""
    try:
        columns = set(pq.read_schema(path).names)
    except Exception:
        return False
    return set(PRODUCT_COLUMNS).issubset(columns)


def product_trade_from_leaf(leaf: pd.DataFrame, flow: str = DEFAULT_FLOW) -> pd.DataFrame:
    """Return reporter-year-HS6 product totals for one flow, excluding HS6 999999."""
    if leaf.empty:
        return pd.DataFrame(columns=PRODUCT_COLUMNS)
    required = {"reporter_code", "year", "flow", "cmd_code", "trade_value"}
    missing = required - set(leaf.columns)
    if missing:
        raise RuntimeError(f"Leaf trade frame is missing required columns: {sorted(missing)}")
    if "classification_code" not in leaf.columns:
        leaf = leaf.assign(classification_code="")
    out = leaf.loc[leaf["flow"].eq(flow), ["reporter_code", "year", "classification_code", "cmd_code", "trade_value"]].copy()
    if out.empty:
        return pd.DataFrame(columns=PRODUCT_COLUMNS)
    out["classification_code"] = out["classification_code"].fillna("").astype(str).str.strip().str.upper()
    out["cmd_code"] = tcp.hs6_code_series(out["cmd_code"])
    out = tcp.drop_excluded_hs6(out)
    out["trade_value"] = pd.to_numeric(out["trade_value"], errors="coerce")
    out = out.dropna(subset=["reporter_code", "year", "cmd_code", "trade_value"])
    out = out[out["trade_value"] > 0].copy()
    if out.empty:
        return pd.DataFrame(columns=PRODUCT_COLUMNS)
    out["reporter_code"] = out["reporter_code"].astype(int)
    out["year"] = out["year"].astype(int)
    return out.groupby(PRODUCT_COLUMNS[:-1], as_index=False)["trade_value"].sum()


def product_exports_from_leaf(leaf: pd.DataFrame) -> pd.DataFrame:
    """Backward-compatible export extractor used by existing tests."""
    return product_trade_from_leaf(leaf, DEFAULT_FLOW)


def product_imports_from_leaf(leaf: pd.DataFrame) -> pd.DataFrame:
    return product_trade_from_leaf(leaf, "Imports")


def process_raw_file(path_text: str, sample_config: dict[str, Any], sample_name: str, chunk_rows: int, flow: str) -> dict[str, Any]:
    tcp.configure_country_sample(**sample_config)
    raw_path = Path(path_text)
    partial_path = partial_path_for_raw(raw_path, sample_name, flow)
    if partial_path.exists():
        if partial_has_current_schema(partial_path):
            return {"raw_file": raw_path.name, "status": "skipped", "leaf_rows": 0, "partial_rows": 0}
        partial_path.unlink()

    combined: pd.DataFrame | None = None
    leaf_rows = 0
    for leaf in tcp.iter_leaf_trade_chunks(raw_path, chunk_rows=chunk_rows):
        if leaf.empty:
            continue
        leaf_rows += int(len(leaf))
        product = product_trade_from_leaf(leaf, flow)
        combined = tcp.add_group_sum_frame(combined, product, PRODUCT_COLUMNS[:-1], compact_rows=250_000)

    product_values = tcp.finish_group_sum_frame(combined, PRODUCT_COLUMNS[:-1])
    if product_values.empty:
        product_values = pd.DataFrame(columns=PRODUCT_COLUMNS)
    write_parquet_atomic(partial_path, product_values[PRODUCT_COLUMNS])
    return {
        "raw_file": raw_path.name,
        "status": "written" if leaf_rows else "empty",
        "leaf_rows": int(leaf_rows),
        "partial_rows": int(len(product_values)),
    }


def configure_sample(sample_name: str, start_year: int, end_year: int, refresh_availability: bool) -> dict[str, Any]:
    config = {
        "country_sample": sample_name,
        "min_available_years": 10,
        "start_year": int(start_year),
        "end_year": int(end_year),
        "refresh_availability": bool(refresh_availability),
    }
    tcp.configure_country_sample(**config)
    tcp.save_country_panel()
    return config


def missing_bulk_summary(sample_name: str, start_year: int, end_year: int, refresh_availability: bool) -> dict[str, Any]:
    configure_sample(sample_name, start_year, end_year, refresh_availability)
    expected = tcp.expected_bulk_keys_for_active_sample()
    available = tcp.available_bulk_keys(tcp.dedupe_bulk_files(tcp.raw_bulk_file_candidates()))
    missing = sorted(expected - available)
    by_year: dict[int, dict[str, int]] = {}
    for _reporter, year, _classification in expected:
        by_year.setdefault(int(year), {"expected": 0, "available": 0, "missing": 0})
        by_year[int(year)]["expected"] += 1
    for key in expected & available:
        by_year[int(key[1])]["available"] += 1
    for _reporter, year, _classification in missing:
        by_year[int(year)]["missing"] += 1
    return {
        "expected_keys": len(expected),
        "available_expected_keys": len(expected & available),
        "missing_keys": len(missing),
        "missing_examples": [
            {"reporter_code": int(reporter), "year": int(year), "classification_code": str(classification)}
            for reporter, year, classification in missing[:25]
        ],
        "by_year": [{"year": year, **counts} for year, counts in sorted(by_year.items())],
    }


def write_blocker(result_dir: Path, processed_dir: Path, reason: str, details: dict[str, Any], flow: str = DEFAULT_FLOW) -> None:
    stem = artifact_stem(flow)
    manifest = {
        "created_at_utc": tcp.now_utc(),
        "status": "blocked",
        "reason": reason,
        "details": details,
        "flow": flow,
        "benchmark_flow": flow,
        "required_env_var": "COMTRADE_SUBSCRIPTION_KEY",
        "fallback_policy": "No rd2-only or H2.4-only benchmark was substituted for the requested historical world_broad benchmark.",
    }
    for path in [result_dir / f"run_manifest_{stem}.json", processed_dir / f"{stem}_manifest.json"]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    memo = [
        "# Historical World-Relative Product Gini Blocker",
        "",
        f"Created: {manifest['created_at_utc']}",
        "",
        reason,
        "",
        "No results were generated because the requested true historical `world_broad` benchmark is incomplete.",
        "The runner did not substitute the 60-country rd2 sample or the 2015-2024 H2.4 benchmark.",
        "",
        "## Details",
        "",
        "```json",
        json.dumps(details, indent=2, sort_keys=True),
        "```",
    ]
    (result_dir / f"{stem}_blocker.md").write_text("\n".join(memo) + "\n", encoding="utf-8")


def ensure_raw_coverage(args: argparse.Namespace, result_dir: Path, processed_dir: Path) -> dict[str, Any]:
    benchmark = missing_bulk_summary(args.benchmark_sample, args.start_year, args.end_year, args.refresh_availability)
    if benchmark["missing_keys"] and args.download_missing:
        key = args.subscription_key or os.getenv("COMTRADE_SUBSCRIPTION_KEY")
        if not key:
            write_blocker(
                result_dir,
                processed_dir,
                "Missing historical world_broad bulk files and no Comtrade subscription key is available.",
                {"benchmark_sample": args.benchmark_sample, "coverage": benchmark},
                args.flow,
            )
            raise RuntimeError("Missing historical world_broad bulk files and no COMTRADE_SUBSCRIPTION_KEY is available.")
        configure_sample(args.benchmark_sample, args.start_year, args.end_year, args.refresh_availability)
        availability = tcp.download_availability(key)
        tcp.download_bulk_files(key, availability, workers=args.download_workers)
        benchmark = missing_bulk_summary(args.benchmark_sample, args.start_year, args.end_year, False)

    if benchmark["missing_keys"]:
        write_blocker(
            result_dir,
            processed_dir,
            "Missing historical world_broad bulk files. Re-run with --download-missing and a valid Comtrade key.",
            {"benchmark_sample": args.benchmark_sample, "coverage": benchmark},
            args.flow,
        )
        raise RuntimeError("Historical world_broad bulk coverage is incomplete.")

    country = missing_bulk_summary(args.country_sample, args.start_year, args.end_year, False)
    if country["missing_keys"]:
        write_blocker(
            result_dir,
            processed_dir,
            "The rd2 country-sample raw files are incomplete for the requested period.",
            {"country_sample": args.country_sample, "coverage": country},
            args.flow,
        )
        raise RuntimeError("rd2 country-sample raw files are incomplete.")
    return {"benchmark_raw_coverage": benchmark, "country_raw_coverage": country}


def build_partials(sample_name: str, sample_config: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    tcp.configure_country_sample(**sample_config)
    files = tcp.hs_bulk_files(args.max_files)
    if not files:
        raise FileNotFoundError(f"No HS Comtrade bulk files found for {sample_name}.")
    sample_partial_dir = partial_dir(sample_name, args.flow)
    if args.fresh and sample_partial_dir.exists():
        shutil.rmtree(sample_partial_dir)
    sample_partial_dir.mkdir(parents=True, exist_ok=True)
    status_rows: list[dict[str, Any]] = []
    if args.workers <= 1:
        for idx, raw_path in enumerate(files, start=1):
            row = process_raw_file(str(raw_path), sample_config, sample_name, args.chunk_rows, args.flow)
            status_rows.append(row)
            if row["status"] != "skipped" or idx % 100 == 0:
                print(f"[{idx}/{len(files)}] {sample_name} {row['status']}: {row['raw_file']}", flush=True)
    else:
        with ProcessPoolExecutor(max_workers=max(1, args.workers)) as executor:
            future_map = {
                executor.submit(process_raw_file, str(raw_path), sample_config, sample_name, args.chunk_rows, args.flow): raw_path
                for raw_path in files
            }
            for idx, future in enumerate(as_completed(future_map), start=1):
                row = future.result()
                status_rows.append(row)
                if row["status"] != "skipped" or idx % 100 == 0:
                    print(f"[{idx}/{len(files)}] {sample_name} {row['status']}: {row['raw_file']}", flush=True)

    present_partials = [
        partial_path_for_raw(raw_path, sample_name, args.flow)
        for raw_path in files
        if partial_path_for_raw(raw_path, sample_name, args.flow).exists()
    ]
    return {
        "sample": sample_name,
        "raw_files": len(files),
        "partial_files": len(present_partials),
        "statuses": {
            status: sum(1 for row in status_rows if row["status"] == status)
            for status in sorted({row["status"] for row in status_rows})
        },
        "leaf_rows_processed": int(sum(row["leaf_rows"] for row in status_rows)),
        "partial_rows_written": int(sum(row["partial_rows"] for row in status_rows)),
    }


def parquet_list(paths: list[Path]) -> str:
    if not paths:
        raise FileNotFoundError("No product-flow partial parquet files are available.")
    return "[" + ", ".join("'" + str(path).replace("'", "''") + "'" for path in paths) + "]"


def lt_hgl_hs1992_weights_sql_path() -> str:
    tcp.load_lt_hgl_hs1992_conversion_weights()
    return str(tcp.LT_HGL_NORMALIZED_WEIGHTS_PATH).replace("'", "''")


def lt_hgl_missing_weight_query(quoted: str, mapping_path: str) -> str:
    return f"""
        WITH source AS (
            SELECT
                COALESCE(NULLIF(UPPER(TRIM(CAST(classification_code AS VARCHAR))), ''), 'UNKNOWN') AS classification_code,
                LPAD(CAST(cmd_code AS VARCHAR), 6, '0') AS cmd_code,
                SUM(CAST(trade_value AS DOUBLE)) AS trade_value,
                COUNT(*) AS rows
            FROM read_parquet({quoted}, union_by_name=true)
            WHERE trade_value IS NOT NULL
              AND CAST(trade_value AS DOUBLE) > 0
              AND LPAD(CAST(cmd_code AS VARCHAR), 6, '0') <> '999999'
            GROUP BY 1, 2
        ),
        keys AS (
            SELECT DISTINCT
                CAST(source_classification_code AS VARCHAR) AS source_classification_code,
                LPAD(CAST(source_cmd_code AS VARCHAR), 6, '0') AS source_cmd_code
            FROM read_parquet('{mapping_path}')
        )
        SELECT
            COUNT(*) AS missing_source_pairs,
            COALESCE(SUM(source.rows), 0) AS missing_rows,
            COALESCE(SUM(source.trade_value), 0.0) AS missing_trade_value
        FROM source
        LEFT JOIN keys
          ON source.classification_code = keys.source_classification_code
         AND source.cmd_code = keys.source_cmd_code
        WHERE keys.source_cmd_code IS NULL
    """


def aggregate_product_trade(
    sample_name: str,
    files: list[Path],
    output_path: Path,
    product_id_mode: str,
    flow: str = DEFAULT_FLOW,
) -> pd.DataFrame:
    paths = [
        partial_path_for_raw(raw_path, sample_name, flow)
        for raw_path in files
        if partial_path_for_raw(raw_path, sample_name, flow).exists()
    ]
    quoted = parquet_list(paths)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if product_id_mode == "native_hs6":
        product_expr = "LPAD(CAST(cmd_code AS VARCHAR), 6, '0')"
        join_clause = ""
        trade_value_expr = "CAST(p.trade_value AS DOUBLE)"
    elif product_id_mode == "harmonized_hs6_family":
        mapping_path = lt_hgl_hs1992_weights_sql_path()
        product_expr = "w.target_product_id"
        trade_value_expr = "CAST(p.trade_value AS DOUBLE) * CAST(w.weight AS DOUBLE)"
        join_clause = f"""
                INNER JOIN read_parquet('{mapping_path}') AS w
                  ON COALESCE(NULLIF(UPPER(TRIM(CAST(p.classification_code AS VARCHAR))), ''), 'UNKNOWN')
                     = CAST(w.source_classification_code AS VARCHAR)
                 AND LPAD(CAST(p.cmd_code AS VARCHAR), 6, '0') = LPAD(CAST(w.source_cmd_code AS VARCHAR), 6, '0')
        """
    else:
        raise ValueError(f"Unsupported product ID mode `{product_id_mode}`.")
    with duckdb.connect() as con:
        if product_id_mode == "harmonized_hs6_family":
            missing = con.execute(lt_hgl_missing_weight_query(quoted, mapping_path)).fetchone()
            if missing and int(missing[0]) != 0:
                raise RuntimeError(
                    "LT/HGL HS1992 conversion is missing product source pairs before aggregation: "
                    f"pairs={int(missing[0])}, rows={int(missing[1])}, trade_value={float(missing[2]):,.2f}."
                )
        con.execute(
            f"""
            COPY (
                SELECT
                    CAST(p.reporter_code AS BIGINT) AS reporter_code,
                    CAST(p.year AS BIGINT) AS year,
                    {product_expr} AS product_id,
                    SUM({trade_value_expr}) AS trade_value
                FROM read_parquet({quoted}, union_by_name=true) AS p
                {join_clause}
                WHERE p.trade_value IS NOT NULL
                  AND CAST(p.trade_value AS DOUBLE) > 0
                  AND LPAD(CAST(p.cmd_code AS VARCHAR), 6, '0') <> '999999'
                GROUP BY 1, 2, 3
                ORDER BY 1, 2, 3
            )
            TO '{str(output_path).replace("'", "''")}' (FORMAT PARQUET)
            """
        )
    return pd.read_parquet(output_path)


def aggregate_product_exports(sample_name: str, files: list[Path], output_path: Path, product_id_mode: str) -> pd.DataFrame:
    return aggregate_product_trade(sample_name, files, output_path, product_id_mode, DEFAULT_FLOW)


def filtered_source_trade_value(sample_name: str, files: list[Path], flow: str) -> float:
    paths = [
        partial_path_for_raw(raw_path, sample_name, flow)
        for raw_path in files
        if partial_path_for_raw(raw_path, sample_name, flow).exists()
    ]
    quoted = parquet_list(paths)
    with duckdb.connect() as con:
        value = con.execute(
            f"""
            SELECT COALESCE(SUM(CAST(trade_value AS DOUBLE)), 0.0)
            FROM read_parquet({quoted}, union_by_name=true)
            WHERE trade_value IS NOT NULL
              AND CAST(trade_value AS DOUBLE) > 0
              AND LPAD(CAST(cmd_code AS VARCHAR), 6, '0') <> '999999'
            """
        ).fetchone()[0]
    return float(value or 0.0)


def conversion_value_diagnostics(
    sample_name: str,
    files: list[Path],
    converted_product: pd.DataFrame,
    flow: str,
) -> dict[str, Any]:
    source_value = filtered_source_trade_value(sample_name, files, flow)
    converted_value = float(pd.to_numeric(converted_product["trade_value"], errors="coerce").fillna(0).sum())
    residual = converted_value - source_value
    tolerance = max(10.0, abs(source_value) * 1e-9)
    status = "ok" if abs(residual) <= tolerance else "blocked_value_not_conserved"
    if status != "ok":
        raise RuntimeError(
            f"World-relative {flow} LT/HGL conversion does not conserve {sample_name} source value: "
            f"source={source_value:,.6f}, converted={converted_value:,.6f}, residual={residual:,.6f}, "
            f"tolerance={tolerance:,.6f}."
        )
    return {
        "sample": sample_name,
        "flow": flow,
        "filtered_source_trade_value": source_value,
        "weighted_converted_trade_value": converted_value,
        "conversion_value_residual": residual,
        "conversion_value_residual_tolerance": tolerance,
        "status": status,
    }


def build_world_product_totals(benchmark_product: pd.DataFrame, output_path: Path, flow: str = DEFAULT_FLOW) -> pd.DataFrame:
    key_col = product_key_column(benchmark_product)
    world_col = world_product_column(flow)
    world = (
        benchmark_product.groupby(["year", key_col], as_index=False)
        .agg(**{world_col: ("trade_value", "sum")})
        .sort_values(["year", key_col])
        .reset_index(drop=True)
    )
    if key_col != PRODUCT_ID_COLUMN:
        world = world.rename(columns={key_col: PRODUCT_ID_COLUMN})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    world.to_parquet(output_path, index=False)
    return world


def classification_diagnostics_from_partials(sample_name: str, files: list[Path], output_path: Path, flow: str = DEFAULT_FLOW) -> pd.DataFrame:
    paths = [
        partial_path_for_raw(raw_path, sample_name, flow)
        for raw_path in files
        if partial_path_for_raw(raw_path, sample_name, flow).exists()
    ]
    quoted = parquet_list(paths)
    value_noun = flow_value_noun(flow)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect() as con:
        con.execute(
            f"""
            COPY (
                SELECT
                    CAST(year AS BIGINT) AS year,
                    COALESCE(NULLIF(CAST(classification_code AS VARCHAR), ''), 'UNKNOWN') AS classification_code,
                    COUNT(DISTINCT CAST(reporter_code AS BIGINT)) AS reporters_with_{value_noun},
                    COUNT(*) AS reporter_year_class_product_rows,
                    COUNT(DISTINCT LPAD(CAST(cmd_code AS VARCHAR), 6, '0')) AS hs6_products,
                    SUM(CAST(trade_value AS DOUBLE)) AS trade_value
                FROM read_parquet({quoted}, union_by_name=true)
                WHERE trade_value IS NOT NULL
                  AND CAST(trade_value AS DOUBLE) > 0
                  AND LPAD(CAST(cmd_code AS VARCHAR), 6, '0') <> '999999'
                GROUP BY 1, 2
                ORDER BY 1, 2
            )
            TO '{str(output_path).replace("'", "''")}' (FORMAT PARQUET)
            """
        )
    return pd.read_parquet(output_path)


def harmonization_diagnostics_from_partials(sample_name: str, files: list[Path], output_path: Path, flow: str = DEFAULT_FLOW) -> pd.DataFrame:
    paths = [
        partial_path_for_raw(raw_path, sample_name, flow)
        for raw_path in files
        if partial_path_for_raw(raw_path, sample_name, flow).exists()
    ]
    quoted = parquet_list(paths)
    mapping_path = lt_hgl_hs1992_weights_sql_path()
    value_noun = flow_value_noun(flow)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect() as con:
        con.execute(
            f"""
            COPY (
                WITH source AS (
                    SELECT
                        CAST(reporter_code AS BIGINT) AS reporter_code,
                        CAST(year AS BIGINT) AS year,
                        COALESCE(NULLIF(UPPER(TRIM(CAST(classification_code AS VARCHAR))), ''), 'UNKNOWN') AS classification_code,
                        LPAD(CAST(cmd_code AS VARCHAR), 6, '0') AS cmd_code,
                        SUM(CAST(trade_value AS DOUBLE)) AS trade_value
                    FROM read_parquet({quoted}, union_by_name=true)
                    WHERE trade_value IS NOT NULL
                      AND CAST(trade_value AS DOUBLE) > 0
                      AND LPAD(CAST(cmd_code AS VARCHAR), 6, '0') <> '999999'
                    GROUP BY 1, 2, 3, 4
                ),
                expanded AS (
                    SELECT
                        source.year,
                        source.reporter_code,
                        source.classification_code,
                        source.cmd_code,
                        source.trade_value,
                        CASE
                            WHEN w.target_product_id IS NULL THEN 'lt_hgl_missing_weight'
                            ELSE 'lt_hgl_weighted_hs1992'
                        END AS harmonization_status,
                        w.target_product_id,
                        CAST(w.weight AS DOUBLE) AS conversion_weight
                    FROM source
                    LEFT JOIN read_parquet('{mapping_path}') AS w
                      ON source.classification_code = CAST(w.source_classification_code AS VARCHAR)
                     AND source.cmd_code = LPAD(CAST(w.source_cmd_code AS VARCHAR), 6, '0')
                ),
                weighted AS (
                    SELECT
                        year,
                        reporter_code,
                        classification_code,
                        cmd_code,
                        harmonization_status,
                        target_product_id,
                        CASE
                            WHEN target_product_id IS NULL THEN trade_value
                            ELSE trade_value * conversion_weight
                        END AS trade_value
                    FROM expanded
                )
                SELECT
                    year,
                    harmonization_status,
                    COUNT(DISTINCT reporter_code) AS reporters_with_{value_noun},
                    COUNT(DISTINCT reporter_code || ':' || classification_code || ':' || cmd_code) AS reporter_year_hs6_rows,
                    COUNT(DISTINCT target_product_id) AS harmonized_products,
                    COUNT(DISTINCT classification_code || ':' || cmd_code) AS native_hs6_products,
                    SUM(trade_value) AS trade_value
                FROM weighted
                GROUP BY 1, 2
                ORDER BY 1, 2
            )
            TO '{str(output_path).replace("'", "''")}' (FORMAT PARQUET)
            """
        )
    diag = pd.read_parquet(output_path)
    if not diag.empty:
        year_total = diag.groupby("year")["trade_value"].transform("sum")
        diag["trade_value_share"] = diag["trade_value"] / year_total
        diag.to_parquet(output_path, index=False)
    return diag


def compute_country_year_metrics(country_group: pd.DataFrame, world_year: pd.DataFrame, flow: str = DEFAULT_FLOW) -> dict[str, Any]:
    country_key = product_key_column(country_group)
    world_key = product_key_column(world_year)
    world_col = world_product_column(flow)
    country_total_col = flow_total_column(flow, "country")
    world_total_col = flow_total_column(flow, "world")
    leave_one_out_col = flow_total_column(flow, "leave_one_out_world")
    zero_col = zero_weight_column(flow)
    weighted_relative_col = f"weighted_mean_relative_{flow_slug(flow)}_intensity"
    country = country_group[[country_key, "trade_value"]].rename(
        columns={country_key: PRODUCT_ID_COLUMN, "trade_value": "country_product_trade"}
    )
    world = world_year[[world_key, world_col]].rename(
        columns={world_key: PRODUCT_ID_COLUMN, world_col: "world_product_trade"}
    ).copy()
    merged = world.merge(country, on=PRODUCT_ID_COLUMN, how="outer")
    merged["world_product_trade"] = pd.to_numeric(merged["world_product_trade"], errors="coerce").fillna(0.0)
    merged["country_product_trade"] = pd.to_numeric(merged["country_product_trade"], errors="coerce").fillna(0.0)
    merged = merged[(merged["world_product_trade"] > 0) | (merged["country_product_trade"] > 0)].copy()
    country_total = float(merged["country_product_trade"].sum())
    world_total = float(merged["world_product_trade"].sum())
    if country_total <= 0 or world_total <= 0:
        out = {
            "world_relative_product_gini": np.nan,
            "world_weighted_share_gini": np.nan,
            "world_weighted_product_coverage": np.nan,
            "weighted_mean_relative_trade_intensity": np.nan,
            weighted_relative_col: np.nan,
            "world_weighted_mean_country_share": np.nan,
            "country_total_trade_value": country_total,
            "world_total_trade_value": world_total,
            country_total_col: country_total,
            world_total_col: world_total,
            leave_one_out_col: np.nan,
            "country_active_products": int((merged["country_product_trade"] > 0).sum()),
            "world_benchmark_products": int((merged["world_product_trade"] > 0).sum()),
            "zero_weight_country_trade_share": np.nan,
            zero_col: np.nan,
            "missing_benchmark_product_count": int(((merged["world_product_trade"] <= 0) & (merged["country_product_trade"] > 0)).sum()),
            "negative_leave_one_out_product_count": 0,
            "metric_valid": False,
            "invalid_reason": "empty_country_or_world_total",
        }
        if flow == "Imports":
            out["world_relative_import_product_gini"] = np.nan
        return out

    merged["country_share"] = merged["country_product_trade"] / country_total
    merged["leave_one_out_product_trade"] = merged["world_product_trade"] - merged["country_product_trade"]
    negative_loo = merged["leave_one_out_product_trade"] < -1e-6
    small_negative = merged["leave_one_out_product_trade"].between(-1e-6, 0, inclusive="left")
    if small_negative.any():
        merged.loc[small_negative, "leave_one_out_product_trade"] = 0.0
    negative_count = int(negative_loo.sum())

    valid = merged["leave_one_out_product_trade"] > 0
    benchmark_total = float(merged.loc[valid, "leave_one_out_product_trade"].sum())
    zero_weight_country_export_share = float(merged.loc[~valid, "country_share"].sum())
    missing_benchmark_product_count = int(((merged["world_product_trade"] <= 0) & (merged["country_product_trade"] > 0)).sum())
    if benchmark_total <= 0 or not valid.any():
        world_relative = np.nan
        weighted_share = np.nan
        coverage = np.nan
        weighted_relative_mean = np.nan
        weighted_share_mean = np.nan
        metric_valid = False
        invalid_reason = "empty_leave_one_out_benchmark"
    else:
        valid_frame = merged.loc[valid].copy()
        weights = valid_frame["leave_one_out_product_trade"].to_numpy(dtype=float) / benchmark_total
        country_shares = valid_frame["country_share"].to_numpy(dtype=float)
        relative_intensity = country_shares / weights
        if negative_count:
            world_relative = np.nan
            weighted_share = np.nan
            coverage = np.nan
            weighted_relative_mean = np.nan
            weighted_share_mean = np.nan
            metric_valid = False
            invalid_reason = f"negative_leave_one_out_product_{flow_value_noun(flow)}"
        else:
            world_relative = weighted_gini(relative_intensity, weights)
            weighted_share = weighted_gini(country_shares, weights)
            coverage = float(weights[country_shares > 0].sum())
            weighted_relative_mean = float(np.sum(weights * relative_intensity))
            weighted_share_mean = float(np.sum(weights * country_shares))
            metric_valid = True
            invalid_reason = ""

    out = {
        "world_relative_product_gini": world_relative,
        "world_weighted_share_gini": weighted_share,
        "world_weighted_product_coverage": coverage,
        "weighted_mean_relative_trade_intensity": weighted_relative_mean,
        weighted_relative_col: weighted_relative_mean,
        "world_weighted_mean_country_share": weighted_share_mean,
        "country_total_trade_value": country_total,
        "world_total_trade_value": world_total,
        country_total_col: country_total,
        world_total_col: world_total,
        leave_one_out_col: benchmark_total,
        "country_active_products": int((merged["country_product_trade"] > 0).sum()),
        "world_benchmark_products": int(valid.sum()),
        "zero_weight_country_trade_share": zero_weight_country_export_share,
        zero_col: zero_weight_country_export_share,
        "missing_benchmark_product_count": missing_benchmark_product_count,
        "negative_leave_one_out_product_count": negative_count,
        "metric_valid": metric_valid,
        "invalid_reason": invalid_reason,
    }
    if flow == "Exports":
        out["weighted_mean_relative_export_intensity"] = weighted_relative_mean
    else:
        out["world_relative_import_product_gini"] = world_relative
    return out


def compute_panel(
    country_product: pd.DataFrame,
    world_product: pd.DataFrame,
    country_panel: pd.DataFrame,
    active_product_gini: pd.DataFrame,
    flow: str = DEFAULT_FLOW,
) -> pd.DataFrame:
    world_by_year = {int(year): group.reset_index(drop=True) for year, group in world_product.groupby("year", sort=True)}
    country_meta = country_panel.set_index("reporter_code")[["country", "iso3"]].to_dict("index")
    rows: list[dict[str, Any]] = []
    for (reporter_code, year), group in country_product.groupby(["reporter_code", "year"], sort=True):
        year = int(year)
        reporter_code = int(reporter_code)
        world_year = world_by_year.get(year)
        if world_year is None or world_year.empty:
            continue
        meta = country_meta.get(reporter_code, {"country": str(reporter_code), "iso3": ""})
        row = {
            "country": meta["country"],
            "iso3": meta["iso3"],
            "reporter_code": reporter_code,
            "year": year,
            "flow": flow,
            "variant": "world_relative",
            **compute_country_year_metrics(group, world_year, flow),
        }
        rows.append(row)
    panel = pd.DataFrame(rows)
    if panel.empty:
        raise RuntimeError("World-relative product Gini panel has no rows.")
    duplicate_panel_keys = panel.duplicated(["reporter_code", "year", "flow"], keep=False)
    if duplicate_panel_keys.any():
        examples = panel.loc[duplicate_panel_keys, ["reporter_code", "year", "flow"]].head(10).to_dict(orient="records")
        raise RuntimeError(f"Duplicate world-relative panel keys before active-product merge: {examples}")
    active = active_product_gini.copy()
    if not active.empty:
        active = active[active["flow"].eq(flow)].copy()
        if "variant" in active.columns:
            active = active[active["variant"].astype(str).str.lower().eq("baseline")].copy()
        keep = ["reporter_code", "year", "flow", "product_gini", "product_active_count", "total_trade_value"]
        active = active[[col for col in keep if col in active.columns]]
        active_duplicate_keys = active.duplicated(["reporter_code", "year", "flow"], keep=False)
        if active_duplicate_keys.any():
            examples = active.loc[active_duplicate_keys, ["reporter_code", "year", "flow"]].head(10).to_dict(orient="records")
            raise RuntimeError(f"Duplicate active Product Gini keys: {examples}")
        active = active.rename(
            columns={
                "product_gini": "active_product_gini",
                "product_active_count": "active_product_count",
                "total_trade_value": active_total_column(flow),
            }
        )
        panel = panel.merge(active, on=["reporter_code", "year", "flow"], how="left", validate="one_to_one")
        panel["world_relative_minus_active_product_gini"] = panel["world_relative_product_gini"] - panel["active_product_gini"]
        if flow == "Imports":
            panel["world_relative_import_minus_active_product_gini"] = (
                panel["world_relative_import_product_gini"] - panel["active_product_gini"]
            )
    duplicate_final_keys = panel.duplicated(["reporter_code", "year", "flow"], keep=False)
    if duplicate_final_keys.any():
        examples = panel.loc[duplicate_final_keys, ["reporter_code", "year", "flow"]].head(10).to_dict(orient="records")
        raise RuntimeError(f"Duplicate world-relative panel keys after merge: {examples}")
    return panel.sort_values(["country", "year"]).reset_index(drop=True)


def load_export_balanced_reporters(country_sample: str) -> list[int]:
    manifest_path = (
        tcp.sample_results_dir(country_sample)
        / tables_dirname("Exports")
        / f"run_manifest_{artifact_stem('Exports')}.json"
    )
    if not manifest_path.exists():
        return []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    codes = manifest.get("balanced_window", {}).get("balanced_reporter_codes", [])
    return sorted(int(code) for code in codes)


def apply_balanced_window(panel: pd.DataFrame, args: argparse.Namespace) -> tuple[pd.DataFrame, dict[str, Any]]:
    start = int(args.balanced_start_year) if args.balanced_start_year is not None else int(panel["year"].min())
    end = int(args.balanced_end_year) if args.balanced_end_year is not None else int(panel["year"].max())
    if end < start:
        raise RuntimeError("--balanced-end-year must be greater than or equal to --balanced-start-year.")
    required_years = set(range(start, end + 1))
    window = panel[panel["year"].between(start, end)].copy()
    country_years = window.groupby("reporter_code")["year"].apply(lambda years: set(years.astype(int)))
    balanced_reporters = sorted(int(code) for code, years in country_years.items() if required_years.issubset(years))
    all_balanced_reporters = balanced_reporters.copy()
    reference_filter = ""
    dropped_by_reference_filter: list[int] = []
    if (
        getattr(args, "flow", DEFAULT_FLOW) == "Imports"
        and args.require_balanced_countries is not None
        and len(balanced_reporters) > int(args.require_balanced_countries)
    ):
        export_reference = load_export_balanced_reporters(args.country_sample)
        required_count = int(args.require_balanced_countries)
        if len(export_reference) == required_count and set(export_reference).issubset(set(balanced_reporters)):
            balanced_reporters = export_reference
            reference_filter = "matched_exports_world_relative_balanced_reporters"
            dropped_by_reference_filter = sorted(set(all_balanced_reporters) - set(balanced_reporters))
    balanced = window[window["reporter_code"].isin(balanced_reporters)].copy()
    expected_rows = len(balanced_reporters) * len(required_years)
    if len(balanced) != expected_rows:
        raise RuntimeError(
            f"Balanced window construction failed: expected {expected_rows} rows, found {len(balanced)} rows."
        )
    if args.require_balanced_countries is not None and len(balanced_reporters) != int(args.require_balanced_countries):
        raise RuntimeError(
            f"Balanced {start}-{end} window has {len(balanced_reporters)} countries, "
            f"not requested {int(args.require_balanced_countries)}."
        )
    details = {
        "balanced_start_year": start,
        "balanced_end_year": end,
        "balanced_years": len(required_years),
        "balanced_countries": len(balanced_reporters),
        "balanced_expected_rows": expected_rows,
        "balanced_reporter_codes": balanced_reporters,
        "all_balanced_reporter_codes_before_reference_filter": all_balanced_reporters,
        "all_balanced_countries_before_reference_filter": len(all_balanced_reporters),
        "balanced_reference_filter": reference_filter,
        "balanced_reporter_codes_dropped_by_reference_filter": dropped_by_reference_filter,
        "all_available_rows_before_balance": int(len(panel)),
        "all_available_countries_before_balance": int(panel["reporter_code"].nunique()),
        "all_available_year_min_before_balance": int(panel["year"].min()),
        "all_available_year_max_before_balance": int(panel["year"].max()),
    }
    balanced["sample_window"] = f"balanced_{start}_{end}"
    return balanced.sort_values(["country", "year"]).reset_index(drop=True), details


def duplicate_key_diagnostics(product_values: pd.DataFrame) -> dict[str, Any]:
    counts = product_values.groupby(PRODUCT_KEY_COLUMNS).size()
    duplicates = counts[counts > 1]
    return {
        "duplicate_reporter_year_product_keys": int(len(duplicates)),
        "max_duplicate_rows_per_key": int(duplicates.max()) if not duplicates.empty else 0,
    }


def validate_panel_for_output(panel: pd.DataFrame) -> None:
    duplicate_keys = panel.duplicated(["reporter_code", "year", "flow"], keep=False)
    if duplicate_keys.any():
        examples = panel.loc[duplicate_keys, ["reporter_code", "year", "flow"]].head(10).to_dict(orient="records")
        raise RuntimeError(f"Refusing to write duplicate world-relative country-year-flow keys: {examples}")
    if "metric_valid" in panel.columns:
        invalid = panel[~panel["metric_valid"].astype(bool)].copy()
        if not invalid.empty:
            examples = invalid[["country", "iso3", "reporter_code", "year", "invalid_reason"]].head(10).to_dict(orient="records")
            raise RuntimeError(f"Refusing to write invalid world-relative metrics: {examples}")


def write_outputs(
    panel: pd.DataFrame,
    benchmark_product: pd.DataFrame,
    world_product: pd.DataFrame,
    classification_diagnostics: pd.DataFrame,
    harmonization_diagnostics: pd.DataFrame,
    result_dir: Path,
    processed_dir: Path,
    args: argparse.Namespace,
    raw_coverage: dict[str, Any],
    partial_stats: dict[str, Any],
    balance_details: dict[str, Any],
    conversion_diagnostics: dict[str, Any],
) -> dict[str, Path]:
    validate_panel_for_output(panel)
    stem = artifact_stem(args.flow)
    value_noun = flow_value_noun(args.flow)
    zero_col = zero_weight_column(args.flow)
    world_col = world_product_column(args.flow)
    metric_col = metric_alias_column(args.flow)
    panel_path = processed_dir / f"{stem}_panel.parquet"
    panel.to_parquet(panel_path, index=False)
    main_csv = result_dir / f"{stem}_all_years.csv"
    appendix_csv = result_dir / (f"world_weighted_{flow_slug(args.flow)}_product_gini_appendix.csv" if args.flow == "Imports" else "world_weighted_product_gini_appendix.csv")
    diagnostics_csv = result_dir / f"{stem}_diagnostics.csv"
    classification_csv = result_dir / f"{stem}_classification_diagnostics.csv"
    harmonization_csv = result_dir / f"{stem}_harmonization_diagnostics.csv"
    yearly_csv = result_dir / f"{stem}_yearly_summary.csv"
    latest_csv = result_dir / f"{stem}_latest_rankings.csv"
    panel.to_csv(main_csv, index=False)

    appendix_cols = [
        "country",
        "iso3",
        "reporter_code",
        "year",
        "flow",
        "world_relative_product_gini",
        "world_relative_import_product_gini",
        "world_weighted_share_gini",
        "world_weighted_product_coverage",
        "active_product_gini",
        "world_relative_minus_active_product_gini",
        "world_relative_import_minus_active_product_gini",
        zero_col,
        "missing_benchmark_product_count",
        "sample_window",
    ]
    panel[[col for col in appendix_cols if col in panel.columns]].to_csv(appendix_csv, index=False)

    benchmark_years = (
        benchmark_product.groupby("year", as_index=False)
        .agg(
            **{f"benchmark_reporters_with_{value_noun}": ("reporter_code", "nunique")},
            benchmark_reporter_product_rows=(PRODUCT_ID_COLUMN, "size"),
            **{f"benchmark_total_{value_noun}": ("trade_value", "sum")},
        )
        .merge(
            world_product.groupby("year", as_index=False).agg(
                benchmark_products=(PRODUCT_ID_COLUMN, "nunique"),
                **{f"world_total_{value_noun}": (world_col, "sum")},
            ),
            on="year",
            how="left",
            validate="one_to_one",
        )
    )
    panel_years = panel.groupby("year", as_index=False).agg(
        rd2_countries_with_metric=("reporter_code", "nunique"),
        median_world_relative_product_gini=("world_relative_product_gini", "median"),
        median_world_weighted_share_gini=("world_weighted_share_gini", "median"),
        median_active_product_gini=("active_product_gini", "median"),
        **{f"max_{zero_col}": (zero_col, "max")},
        total_missing_benchmark_products=("missing_benchmark_product_count", "sum"),
        total_negative_leave_one_out_products=("negative_leave_one_out_product_count", "sum"),
    )
    diagnostics = benchmark_years.merge(panel_years, on="year", how="outer").sort_values("year")
    diagnostics.to_csv(diagnostics_csv, index=False)
    classification_diagnostics.to_csv(classification_csv, index=False)
    harmonization_diagnostics.to_csv(harmonization_csv, index=False)
    missing_harmonized_value = 0.0
    if args.product_id_mode == "harmonized_hs6_family" and not harmonization_diagnostics.empty:
        missing_harmonized_value = float(
            harmonization_diagnostics.loc[
                harmonization_diagnostics["harmonization_status"].astype(str).eq("lt_hgl_missing_weight"),
                "trade_value",
            ].sum()
        )
        if missing_harmonized_value != 0:
            raise RuntimeError(f"LT/HGL HS1992 harmonization diagnostics contain missing value: {missing_harmonized_value:,.2f}")

    yearly = panel.groupby("year", as_index=False).agg(
        countries=("reporter_code", "nunique"),
        median_world_relative_product_gini=("world_relative_product_gini", "median"),
        mean_world_relative_product_gini=("world_relative_product_gini", "mean"),
        median_world_weighted_share_gini=("world_weighted_share_gini", "median"),
        median_active_product_gini=("active_product_gini", "median"),
        median_world_relative_minus_active_product_gini=("world_relative_minus_active_product_gini", "median"),
    )
    if args.flow == "Imports":
        yearly["median_world_relative_import_product_gini"] = yearly["median_world_relative_product_gini"]
        yearly["mean_world_relative_import_product_gini"] = yearly["mean_world_relative_product_gini"]
        yearly["median_world_relative_import_minus_active_product_gini"] = yearly[
            "median_world_relative_minus_active_product_gini"
        ]
    yearly.to_csv(yearly_csv, index=False)
    latest_year = int(panel["year"].max())
    latest = panel[panel["year"].eq(latest_year)].sort_values(metric_col, ascending=False)
    pd.concat([latest.head(15), latest.tail(15)], ignore_index=True).to_csv(latest_csv, index=False)

    manifest = {
        "created_at_utc": tcp.now_utc(),
        "status": "complete",
        "command": " ".join([Path(sys.executable).name, *sys.argv]),
        "country_sample": args.country_sample,
        "benchmark_sample": args.benchmark_sample,
        "benchmark_flow": args.flow,
        "product_id_mode": args.product_id_mode,
        "product_id_label": product_id_label(args.product_id_mode),
        "product_harmonization": {
            "method": "official LT/HGL weighted conversion to HS1992/H0"
            if args.product_id_mode == "harmonized_hs6_family"
            else "native HS6 code",
            "source_doi": tcp.LT_HGL_DATASET_DOI if args.product_id_mode == "harmonized_hs6_family" else None,
            "source_version": tcp.LT_HGL_DATASET_VERSION if args.product_id_mode == "harmonized_hs6_family" else None,
            "target": f"{tcp.LT_HGL_TARGET_LABEL}/{tcp.LT_HGL_TARGET_REVISION}"
            if args.product_id_mode == "harmonized_hs6_family"
            else None,
            "missing_weight_trade_value": missing_harmonized_value,
            "value_conservation": conversion_diagnostics if args.product_id_mode == "harmonized_hs6_family" else None,
        },
        "balanced_window": balance_details,
        "start_year": int(args.start_year),
        "end_year": int(args.end_year),
        "flow": args.flow,
        "excluded_hs6_codes": sorted(EXCLUDED_HS6_CODES),
        "row_counts": {
            "panel": int(len(panel)),
            "benchmark_product": int(len(benchmark_product)),
            "world_product": int(len(world_product)),
        },
        "raw_coverage": raw_coverage,
        "partial_stats": partial_stats,
        "diagnostics": {
            "hs6_999999_rows_panel": int(panel.get(PRODUCT_ID_COLUMN, pd.Series(dtype=str)).astype(str).eq("999999").sum())
            if PRODUCT_ID_COLUMN in panel.columns
            else 0,
            f"max_{zero_col}": float(panel[zero_col].max()),
            "total_missing_benchmark_products": int(panel["missing_benchmark_product_count"].sum()),
            "total_negative_leave_one_out_products": int(panel["negative_leave_one_out_product_count"].sum()),
            "benchmark_product_duplicate_keys": duplicate_key_diagnostics(benchmark_product),
            "world_product_duplicate_year_product_keys": duplicate_key_diagnostics(
                world_product.rename(columns={world_col: "trade_value"}).assign(reporter_code=0)
            ),
            "lt_hgl_missing_weight_trade_value": missing_harmonized_value,
        },
        "outputs": {
            "processed_panel": rel(panel_path),
            "main_csv": rel(main_csv),
            "appendix_csv": rel(appendix_csv),
            "diagnostics_csv": rel(diagnostics_csv),
            "classification_diagnostics_csv": rel(classification_csv),
            "harmonization_diagnostics_csv": rel(harmonization_csv),
            "yearly_summary_csv": rel(yearly_csv),
            "latest_rankings_csv": rel(latest_csv),
        },
    }
    manifest_path = result_dir / f"run_manifest_{stem}.json"
    processed_manifest = processed_dir / f"{stem}_manifest.json"
    manifest_text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    manifest_path.write_text(manifest_text, encoding="utf-8")
    processed_manifest.write_text(manifest_text, encoding="utf-8")
    write_memo(panel, yearly, latest, result_dir, diagnostics, args.product_id_mode, balance_details, args.flow)
    return {
        "panel": panel_path,
        "main_csv": main_csv,
        "appendix_csv": appendix_csv,
        "diagnostics_csv": diagnostics_csv,
        "classification_diagnostics_csv": classification_csv,
        "harmonization_diagnostics_csv": harmonization_csv,
        "yearly_summary_csv": yearly_csv,
        "latest_rankings_csv": latest_csv,
        "manifest": manifest_path,
    }


def write_memo(
    panel: pd.DataFrame,
    yearly: pd.DataFrame,
    latest: pd.DataFrame,
    result_dir: Path,
    diagnostics: pd.DataFrame,
    product_id_mode: str,
    balance_details: dict[str, Any],
    flow: str = DEFAULT_FLOW,
) -> None:
    stem = artifact_stem(flow)
    value_noun = flow_value_noun(flow)
    metric_col = metric_alias_column(flow)
    zero_col = zero_weight_column(flow)
    latest_year = int(latest["year"].iloc[0])
    latest_median = float(latest[metric_col].median())
    latest_weighted_share = float(latest["world_weighted_share_gini"].median())
    latest_active = float(latest["active_product_gini"].median()) if "active_product_gini" in latest.columns else np.nan
    earliest_year = int(yearly["year"].min())
    earliest = yearly[yearly["year"].eq(earliest_year)].iloc[0]
    latest_diag = diagnostics[diagnostics["year"].eq(latest_year)].iloc[0]
    top = latest.head(5)[["country", "iso3", metric_col]].to_dict(orient="records")
    bottom = latest.tail(5)[["country", "iso3", metric_col]].to_dict(orient="records")
    title = "Historical World-Relative Product Gini" if flow == "Exports" else "Historical World-Relative Import Product Gini"
    basket = "export" if flow == "Exports" else "import"
    harmonization_lines: list[str] = []
    if product_id_mode == "harmonized_hs6_family":
        harmonization_lines = [
            "",
            "Product harmonization: filtered HS6 rows are converted to HS1992/H0 with official LT/HGL weighted conversion tables before product aggregation. The source is Harvard Dataverse DOI "
            f"`{tcp.LT_HGL_DATASET_DOI}`, version `{tcp.LT_HGL_DATASET_VERSION}`; HS6 `999999` is excluded before conversion.",
        ]
    lines = [
        f"# {title}",
        "",
        f"Generated: {tcp.now_utc()}",
        "",
        "## Definition",
        "",
        f"Product ID mode: `{product_id_mode}` ({product_id_label(product_id_mode)}).",
        *harmonization_lines,
        "",
        "The website-facing panel is balanced:",
        "",
        f"- Balanced window: {balance_details.get('balanced_start_year')}-{balance_details.get('balanced_end_year')}",
        f"- Balanced countries: {balance_details.get('balanced_countries')}",
        "",
        f"For rd2 country `c`, product family `p`, and year `t`, the main measure compares the country's {basket} share to the leave-one-out world {basket} product weight:",
        "",
        "`s_cpt = v_cpt / sum_p v_cpt`",
        "",
        "`w_-c,pt = (B_pt - v_cpt) / sum_p (B_pt - v_cpt)`",
        "",
        f"`{metric_col} = weighted_gini(s_cpt / w_-c,pt, w_-c,pt)`",
        "",
        "The appendix measure is `weighted_gini(s_cpt, w_-c,pt)`. HS6 `999999` is excluded before aggregation.",
        "",
        "## Why This Exists",
        "",
        f"Feynman version: imagine world {value_noun} as a recipe. If the world recipe is 10 percent cars, 5 percent chips, and 1 percent coffee, a country is not being judged against an equal pile of HS codes. It is being judged against that world recipe.",
        "",
        f"The standard Product Gini asks whether a country puts most of its {basket} value into only a few active products. That is useful, but HS product codes are not equally important in actual trade. Crude oil, cars, and small niche products each occupy product slots, even though their normal world-trade weights are very different.",
        "",
        f"The World-Relative Product Gini fixes that benchmark problem. First divide the country's product share by the leave-one-out world product share. A value of 1 means the country {value_noun.rstrip('s')}s that product in exactly the world-normal proportion. Then compute a weighted Gini across those relative intensities. The measure is low when the country looks like the world {basket} basket and high when it is unusually tilted toward a few products relative to that benchmark.",
        "",
        "This is why the main measure is more useful than the literal appendix weighted-share Gini for this question: if a country exactly matches the world product basket, the relative Gini is zero. The appendix measure can still be positive because it is measuring inequality in raw shares, not deviation from the world benchmark.",
        "",
        "## Latest-Year Results",
        "",
        f"- Latest year: {latest_year}",
        f"- Countries with metric: {latest['reporter_code'].nunique():,}",
        f"- Median World-Relative Product Gini: {latest_median:.3f}",
        f"- Median appendix world-weighted share Gini: {latest_weighted_share:.3f}",
        f"- Median standard active Product Gini on the same rows: {latest_active:.3f}",
        f"- Benchmark reporters with {value_noun}: {int(latest_diag.get(f'benchmark_reporters_with_{value_noun}', 0)):,}",
        f"- Benchmark HS6 products: {int(latest_diag.get('benchmark_products', 0)):,}",
        "",
        "Highest latest-year values:",
        "",
        *[f"- {row['country']} ({row['iso3']}): {row[metric_col]:.3f}" for row in top],
        "",
        "Lowest latest-year values:",
        "",
        *[f"- {row['country']} ({row['iso3']}): {row[metric_col]:.3f}" for row in bottom],
        "",
        "## Time Change",
        "",
        f"- Earliest usable year: {earliest_year}",
        f"- Earliest median World-Relative Product Gini: {float(earliest['median_world_relative_product_gini']):.3f}",
        f"- Latest median World-Relative Product Gini: {latest_median:.3f}",
        "",
        "## Outputs",
        "",
        f"- `{rel(result_dir / f'{stem}_all_years.csv')}`",
        f"- `{rel(result_dir / ('world_weighted_import_product_gini_appendix.csv' if flow == 'Imports' else 'world_weighted_product_gini_appendix.csv'))}`",
        f"- `{rel(result_dir / f'{stem}_diagnostics.csv')}`",
        f"- `{rel(result_dir / f'{stem}_classification_diagnostics.csv')}`",
        f"- `{rel(result_dir / f'{stem}_harmonization_diagnostics.csv')}`",
        f"- `{rel(result_dir / f'{stem}_yearly_summary.csv')}`",
        f"- `{rel(result_dir / f'{stem}_latest_rankings.csv')}`",
    ]
    (result_dir / f"{stem}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_active_product_gini(country_sample: str) -> pd.DataFrame:
    path = tcp.sample_results_dir(country_sample) / "exercise_01_tables" / "concentration_all_years.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country-sample", default="rd2_countries", choices=tcp.COUNTRY_SAMPLE_CHOICES)
    parser.add_argument("--benchmark-sample", default="world_broad", choices=tcp.COUNTRY_SAMPLE_CHOICES)
    parser.add_argument("--flow", default=DEFAULT_FLOW, choices=FLOW_CHOICES)
    parser.add_argument("--start-year", type=int, default=2000)
    parser.add_argument("--end-year", type=int, default=2024)
    parser.add_argument("--product-id-mode", choices=PRODUCT_ID_MODES, default="harmonized_hs6_family")
    parser.add_argument("--balanced-start-year", type=int, default=2000)
    parser.add_argument("--balanced-end-year", type=int, default=2024)
    parser.add_argument("--require-balanced-countries", type=int, default=55)
    parser.add_argument("--workers", type=int, default=max(1, min(4, os.cpu_count() or 1)))
    parser.add_argument("--download-workers", type=int, default=4)
    parser.add_argument("--chunk-rows", type=int, default=250_000)
    parser.add_argument("--max-files", type=int, default=None)
    parser.add_argument("--download-missing", action="store_true")
    parser.add_argument("--refresh-availability", action="store_true")
    parser.add_argument("--fresh", action="store_true", help="Rebuild world-relative product partials instead of reusing cached file aggregates.")
    parser.add_argument("--subscription-key", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.country_sample != "rd2_countries":
        raise RuntimeError("Website-facing world-relative outputs must use --country-sample rd2_countries.")
    if args.benchmark_sample != "world_broad":
        raise RuntimeError("The requested true historical benchmark must use --benchmark-sample world_broad.")
    if args.end_year > 2024:
        raise RuntimeError("Use an end year no later than 2024; 2025 coverage is incomplete.")
    if args.balanced_start_year < args.start_year or args.balanced_end_year > args.end_year:
        raise RuntimeError("Balanced window must lie inside --start-year/--end-year.")
    if args.max_files is not None:
        raise RuntimeError("--max-files is disabled for official world-relative outputs because it can create incomplete benchmark weights.")

    result_dir, processed_dir = output_dirs(args.country_sample, args.flow)
    raw_coverage = ensure_raw_coverage(args, result_dir, processed_dir)

    benchmark_config = configure_sample(args.benchmark_sample, args.start_year, args.end_year, False)
    benchmark_partial_stats = build_partials(args.benchmark_sample, benchmark_config, args)
    benchmark_files = tcp.hs_bulk_files(args.max_files)
    product_suffix = args.product_id_mode
    stem = artifact_stem(args.flow)
    value_noun = flow_value_noun(args.flow)
    benchmark_product_path = tcp.sample_processed_dir(args.benchmark_sample) / f"{stem}_{product_suffix}_benchmark_product_{value_noun}.parquet"
    benchmark_product = aggregate_product_trade(
        args.benchmark_sample, benchmark_files, benchmark_product_path, args.product_id_mode, args.flow
    )
    world_product_path = tcp.sample_processed_dir(args.benchmark_sample) / f"{stem}_{product_suffix}_world_product_{value_noun}.parquet"
    world_product = build_world_product_totals(benchmark_product, world_product_path, args.flow)
    classification_path = (
        tcp.sample_processed_dir(args.benchmark_sample) / f"{stem}_classification_diagnostics.parquet"
    )
    classification_diagnostics = classification_diagnostics_from_partials(
        args.benchmark_sample, benchmark_files, classification_path, args.flow
    )
    harmonization_path = (
        tcp.sample_processed_dir(args.benchmark_sample) / f"{stem}_harmonization_diagnostics.parquet"
    )
    harmonization_diagnostics = harmonization_diagnostics_from_partials(
        args.benchmark_sample, benchmark_files, harmonization_path, args.flow
    )

    country_config = configure_sample(args.country_sample, args.start_year, args.end_year, False)
    country_partial_stats = build_partials(args.country_sample, country_config, args)
    country_files = tcp.hs_bulk_files(args.max_files)
    country_product_path = processed_dir / f"{stem}_{product_suffix}_rd2_product_{value_noun}.parquet"
    country_product = aggregate_product_trade(args.country_sample, country_files, country_product_path, args.product_id_mode, args.flow)
    conversion_diagnostics = {
        "country_sample": conversion_value_diagnostics(args.country_sample, country_files, country_product, args.flow),
        "benchmark_sample": conversion_value_diagnostics(args.benchmark_sample, benchmark_files, benchmark_product, args.flow),
    }
    country_panel = tcp.save_country_panel()
    active_product_gini = load_active_product_gini(args.country_sample)
    all_available_panel = compute_panel(country_product, world_product, country_panel, active_product_gini, args.flow)
    panel, balance_details = apply_balanced_window(all_available_panel, args)

    partial_stats = {"benchmark": benchmark_partial_stats, "country": country_partial_stats}
    outputs = write_outputs(
        panel,
        benchmark_product,
        world_product,
        classification_diagnostics,
        harmonization_diagnostics,
        result_dir,
        processed_dir,
        args,
        raw_coverage,
        partial_stats,
        balance_details,
        conversion_diagnostics,
    )
    print(f"Wrote {rel(outputs['main_csv'])}", flush=True)
    print(f"Wrote {rel(outputs['appendix_csv'])}", flush=True)
    print(f"Wrote {rel(outputs['diagnostics_csv'])}", flush=True)
    print(f"Wrote {rel(outputs['classification_diagnostics_csv'])}", flush=True)
    print(f"Wrote {rel(outputs['harmonization_diagnostics_csv'])}", flush=True)
    print(f"Wrote {rel(outputs['manifest'])}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
