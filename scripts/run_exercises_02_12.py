#!/usr/bin/env python3
"""Optimized runner for Exercises 2 and 12.

This runner follows the project performance rules:

- parse each raw Comtrade file once;
- write one resumable aggregate Parquet checkpoint per raw file;
- use DuckDB to regroup checkpoints before final analysis;
- regenerate the canonical Exercise 2 and Exercise 12 outputs.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import re
import shutil
import sys
import time
from collections import OrderedDict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from trade_concentration_pipeline import (
    DATA_PROCESSED,
    EX12_FIGURES,
    EX12_TABLES,
    EX12_TOP_DEFINITIONS,
    RESULTS,
    add_country_metadata,
    apply_dynamic_memory_guard,
    apply_memory_limit,
    assign_size_state_columns,
    assign_size_states,
    attach_hs_harmonized_product_id,
    attach_inferred_classification_code,
    configure_country_sample,
    COUNTRY_SAMPLE_CHOICES,
    drop_excluded_hs6,
    ensure_dirs,
    exercise_12_headline_decomposition,
    exercise_12_accounting_from_pair,
    exercise_12_item_modes_for_dimension,
    exercise_12_pair_merge_wide_for_base_year,
    exercise_02_panel_rows_for_leaf,
    extract_leaf_trade,
    growth_decomposition,
    hs_bulk_files,
    iter_exercise_12_accounting_output_chunks,
    item_columns_for_dimension,
    load_btige_cpa_mapping,
    load_lt_hgl_hs1992_conversion_weights,
    make_exercise_12_figures,
    merge_metric_tables,
    now_utc,
    normalize_columns,
    normalize_hs_classification_code,
    prepare_exercise_12_item_values,
    product_scope_states,
    read_comtrade_file,
    run_exercise_02_from_panel,
    save_country_panel,
    sample_processed_dir,
    sample_processed_path,
    sample_results_dir,
    transition_matrix,
    write_exercise_12_memo,
    write_json,
)


BASE_PARTIAL_DIR = DATA_PROCESSED / "exercise_02_12_file_aggregates"
PARTIAL_DIR = BASE_PARTIAL_DIR
BASE_EX12_AGGREGATE_PARQUET = DATA_PROCESSED / "exercise_12_export_aggregates.parquet"
BASE_EX12_DECOMPOSITION_PARQUET = DATA_PROCESSED / "exercise_12_growth_decomposition.parquet"
EX12_AGGREGATE_PARQUET = BASE_EX12_AGGREGATE_PARQUET
EX12_DECOMPOSITION_PARQUET = BASE_EX12_DECOMPOSITION_PARQUET
EX12_SPILL_SPEC_VERSION = "exercise12_spill_v1"
DEFAULT_CHUNK_ROWS = 25_000
PARTIAL_COLUMNS = ["reporter_code", "year", "flow", "classification_code", "dimension", "cmd_code", "partner_code", "hs2", "trade_value"]
DIMENSIONS = ("product", "partner", "product_partner_cell")
FAST_READ_CANDIDATES = (
    ["cmdCode", "commodityCode", "Commodity Code"],
    ["primaryValue", "Trade Value (US$)", "Trade Value", "tradeValue", "fobvalue", "cifvalue"],
    ["reporterCode", "Reporter Code"],
    ["period", "refYear", "year"],
    ["partnerCode", "Partner Code"],
)
FAST_READ_OPTIONAL_CANDIDATES = (
    ["classificationCode", "Classification Code"],
    ["isAggregate"],
)
FAST_READ_FLOW_CANDIDATES = (
    ["flowCode", "Trade Flow Code"],
    ["flowDesc", "Trade Flow"],
)
EX12_EXISTING_AGGREGATE_STREAM_ROWS = int(os.getenv("EX12_EXISTING_AGGREGATE_STREAM_ROWS", "0"))


def configure_runner_sample(args: argparse.Namespace) -> None:
    configure_country_sample(
        country_sample=args.country_sample,
        min_available_years=args.min_available_years,
        start_year=args.start_year,
        end_year=args.end_year,
        refresh_availability=args.refresh_availability,
    )
    global PARTIAL_DIR
    global EX12_AGGREGATE_PARQUET
    global EX12_DECOMPOSITION_PARQUET
    global EX12_TABLES
    global EX12_FIGURES
    results_base = sample_results_dir(args.country_sample)
    EX12_TABLES = results_base / "exercise_12_tables"
    EX12_FIGURES = results_base / "exercise_12_figures"
    if args.country_sample == "prof_p_33":
        PARTIAL_DIR = BASE_PARTIAL_DIR
        EX12_AGGREGATE_PARQUET = BASE_EX12_AGGREGATE_PARQUET
        EX12_DECOMPOSITION_PARQUET = BASE_EX12_DECOMPOSITION_PARQUET
    else:
        base = sample_processed_dir(args.country_sample)
        PARTIAL_DIR = base / "exercise_02_12_file_aggregates"
        EX12_AGGREGATE_PARQUET = base / "exercise_12_export_aggregates.parquet"
        EX12_DECOMPOSITION_PARQUET = base / "exercise_12_growth_decomposition.parquet"


def import_duckdb():
    try:
        import duckdb
    except ImportError as exc:  # pragma: no cover - runtime dependency guard
        raise SystemExit("Missing dependency 'duckdb'. Run: python3 -m pip install -r requirements.txt") from exc
    return duckdb


def configure_duckdb_limits(con, workers: int, memory_limit_gb: float | None = None) -> None:
    con.execute(f"SET threads TO {max(1, workers)}")
    if memory_limit_gb is not None and memory_limit_gb > 0:
        duckdb_limit_gb = max(1, int(memory_limit_gb * 0.70))
        con.execute(f"SET memory_limit='{duckdb_limit_gb}GB'")


def parquet_schema_names(path: Path) -> list[str]:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - runtime dependency guard
        raise SystemExit("Missing dependency 'pyarrow'. Run: python3 -m pip install -r requirements.txt") from exc
    return list(pq.read_schema(path).names)


def parquet_flow_values(path: Path) -> set[str]:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - runtime dependency guard
        raise SystemExit("Missing dependency 'pyarrow'. Run: python3 -m pip install -r requirements.txt") from exc
    table = pq.read_table(path, columns=["flow"])
    return {str(value) for value in table.column("flow").to_pylist() if value is not None}


def normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def normalized_column_map(columns: Iterable[str]) -> dict[str, str]:
    return {normalized_key(str(col)): str(col) for col in columns}


def original_column_for_candidates(norm_to_original: dict[str, str], candidates: Iterable[str]) -> str:
    for candidate in candidates:
        key = normalized_key(candidate)
        if key in norm_to_original:
            return norm_to_original[key]
    raise KeyError(f"None of these columns found: {list(candidates)}")


def sniff_raw_csv(path: Path) -> tuple[str | None, str | None, pd.DataFrame]:
    compression = "gzip" if path.suffix == ".gz" else None
    try:
        header = pd.read_csv(path, compression=compression, nrows=0)
        if len(header.columns) == 1:
            raise ValueError("single column after comma parse")
        return compression, None, header
    except Exception:
        header = pd.read_csv(path, sep="\t", compression=compression, nrows=0)
        return compression, "\t", header


def fast_read_kwargs(path: Path) -> dict:
    compression, sep, header = sniff_raw_csv(path)
    norm_to_original = normalized_column_map(header.columns)
    usecols = []
    for candidates in FAST_READ_CANDIDATES:
        usecols.append(original_column_for_candidates(norm_to_original, candidates))

    flow_col = None
    for candidates in FAST_READ_FLOW_CANDIDATES:
        try:
            flow_col = original_column_for_candidates(norm_to_original, candidates)
            break
        except KeyError:
            continue
    if flow_col is None:
        raise KeyError(f"No flow column found in {path}")
    usecols.append(flow_col)

    for candidates in FAST_READ_OPTIONAL_CANDIDATES:
        try:
            usecols.append(original_column_for_candidates(norm_to_original, candidates))
        except KeyError:
            continue

    read_kwargs = {"compression": compression, "usecols": sorted(set(usecols)), "low_memory": False}
    if sep is not None:
        read_kwargs["sep"] = sep
    return read_kwargs


def read_leaf_trade_fast(path: Path) -> pd.DataFrame:
    read_kwargs = fast_read_kwargs(path)
    raw = pd.read_csv(path, **read_kwargs)
    normalized = attach_inferred_classification_code(normalize_columns(raw), path)
    return extract_leaf_trade(normalized)


def empty_aggregate_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "reporter_code": pd.Series(dtype="Int64"),
            "year": pd.Series(dtype="Int64"),
            "flow": pd.Series(dtype="string"),
            "classification_code": pd.Series(dtype="string"),
            "dimension": pd.Series(dtype="string"),
            "cmd_code": pd.Series(dtype="string"),
            "partner_code": pd.Series(dtype="Int64"),
            "hs2": pd.Series(dtype="string"),
            "trade_value": pd.Series(dtype="float64"),
        }
    )


def standardize_aggregate_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return empty_aggregate_frame()
    out = df.copy()
    for col in PARTIAL_COLUMNS:
        if col not in out.columns:
            out[col] = pd.NA
    out = out[PARTIAL_COLUMNS].copy()
    out["reporter_code"] = pd.to_numeric(out["reporter_code"], errors="coerce").astype("Int64")
    out["year"] = pd.to_numeric(out["year"], errors="coerce").astype("Int64")
    out["flow"] = out["flow"].astype("string")
    out["classification_code"] = out["classification_code"].astype("string").fillna("")
    out["dimension"] = out["dimension"].astype("string")
    out["cmd_code"] = out["cmd_code"].astype("string")
    out["partner_code"] = pd.to_numeric(out["partner_code"], errors="coerce").astype("Int64")
    out["hs2"] = out["hs2"].astype("string")
    out["trade_value"] = pd.to_numeric(out["trade_value"], errors="coerce")
    out = out.dropna(subset=["reporter_code", "year", "flow", "dimension", "trade_value"])
    product_dependent = out["dimension"].isin(["product", "product_partner_cell"])
    excluded_code = out["cmd_code"].astype("string").str.extract(r"(\d{1,6})", expand=False).str.zfill(6).eq("999999")
    return out.loc[~(product_dependent & excluded_code)].copy()


def aggregate_leaf_for_exercises_02_12(leaf: pd.DataFrame) -> pd.DataFrame:
    if leaf.empty:
        return empty_aggregate_frame()
    leaf = leaf[leaf["flow"] == "Exports"].copy()
    if leaf.empty:
        return empty_aggregate_frame()
    product_leaf = drop_excluded_hs6(leaf)

    frames = []
    if "classification_code" not in product_leaf.columns:
        product_leaf["classification_code"] = ""
    product_leaf["classification_code"] = product_leaf["classification_code"].astype(str).str.strip().str.upper()

    if not product_leaf.empty:
        product = product_leaf.groupby(["reporter_code", "year", "flow", "classification_code", "cmd_code", "hs2"], as_index=False)["trade_value"].sum()
        product["dimension"] = "product"
        product["partner_code"] = pd.NA
        frames.append(product)

    partner = leaf.groupby(["reporter_code", "year", "flow", "partner_code"], as_index=False)["trade_value"].sum()
    partner["dimension"] = "partner"
    partner["classification_code"] = ""
    partner["cmd_code"] = pd.NA
    partner["hs2"] = pd.NA
    frames.append(partner)

    if product_leaf.empty:
        return standardize_aggregate_frame(pd.concat(frames, ignore_index=True))

    cell = product_leaf.groupby(["reporter_code", "year", "flow", "classification_code", "cmd_code", "partner_code", "hs2"], as_index=False)[
        "trade_value"
    ].sum()
    cell["dimension"] = "product_partner_cell"
    frames.append(cell)

    return standardize_aggregate_frame(pd.concat(frames, ignore_index=True))


def combine_aggregate_chunks(chunks: list[pd.DataFrame]) -> pd.DataFrame:
    if not chunks:
        return empty_aggregate_frame()
    combined = standardize_aggregate_frame(pd.concat(chunks, ignore_index=True))
    if combined.empty:
        return empty_aggregate_frame()
    group_cols = [col for col in PARTIAL_COLUMNS if col != "trade_value"]
    grouped = combined.groupby(group_cols, as_index=False, dropna=False)["trade_value"].sum()
    return standardize_aggregate_frame(grouped)


def aggregate_raw_for_exercises_02_12(path: Path, chunk_rows: int) -> tuple[pd.DataFrame, int]:
    read_kwargs = fast_read_kwargs(path)
    read_kwargs["chunksize"] = max(1, int(chunk_rows))
    aggregate_chunks: list[pd.DataFrame] = []
    leaf_rows = 0

    for raw in pd.read_csv(path, **read_kwargs):
        normalized = attach_inferred_classification_code(normalize_columns(raw), path)
        leaf = extract_leaf_trade(normalized)
        leaf_rows += int(len(leaf))
        aggregate = aggregate_leaf_for_exercises_02_12(leaf)
        if not aggregate.empty:
            aggregate_chunks.append(aggregate)
        del raw, normalized, leaf, aggregate
        gc.collect()

    return combine_aggregate_chunks(aggregate_chunks), leaf_rows


def output_path_for_raw(path: Path) -> Path:
    name = re.sub(r"\.(gz|txt)$", "", path.name)
    return PARTIAL_DIR / f"{name}.parquet"


def partial_is_valid(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        return set(PARTIAL_COLUMNS).issubset(parquet_schema_names(path)) and parquet_flow_values(path) <= {"Exports"}
    except Exception:
        return False


def write_one_partial(raw_path_text: str, partial_path_text: str, chunk_rows: int) -> dict:
    raw_path = Path(raw_path_text)
    partial_path = Path(partial_path_text)
    partial_path.parent.mkdir(parents=True, exist_ok=True)

    aggregate, leaf_rows = aggregate_raw_for_exercises_02_12(raw_path, chunk_rows=chunk_rows)
    tmp_path = partial_path.with_suffix(partial_path.suffix + ".tmp")
    aggregate.to_parquet(tmp_path, index=False)
    tmp_path.replace(partial_path)
    return {
        "raw_file": raw_path.name,
        "partial_file": partial_path.name,
        "status": "written",
        "leaf_rows": int(leaf_rows),
        "aggregate_rows": int(len(aggregate)),
    }


def write_partials(files: list[Path], workers: int, fresh: bool, chunk_rows: int) -> tuple[list[Path], dict]:
    if fresh and PARTIAL_DIR.exists():
        shutil.rmtree(PARTIAL_DIR)
    PARTIAL_DIR.mkdir(parents=True, exist_ok=True)

    partials = [output_path_for_raw(path) for path in files]
    pending = [(raw, partial) for raw, partial in zip(files, partials) if not partial_is_valid(partial)]
    skipped = len(files) - len(pending)
    stats = {
        "raw_files_seen": len(files),
        "partials_existing": skipped,
        "partials_written": 0,
        "aggregate_rows_written": 0,
        "leaf_rows_processed": 0,
        "manifest_tail": [],
    }

    if not pending:
        return partials, stats

    if workers <= 1:
        for idx, (raw, partial) in enumerate(pending, start=1):
            print(f"[{idx}/{len(pending)}] aggregate Exercises 2+12 from {raw.name}", flush=True)
            row = write_one_partial(str(raw), str(partial), chunk_rows)
            stats["partials_written"] += 1
            stats["aggregate_rows_written"] += row["aggregate_rows"]
            stats["leaf_rows_processed"] += row["leaf_rows"]
            stats["manifest_tail"] = [*stats["manifest_tail"], row][-25:]
    else:
        with ProcessPoolExecutor(max_workers=max(1, workers)) as executor:
            futures = {executor.submit(write_one_partial, str(raw), str(partial), chunk_rows): raw for raw, partial in pending}
            for idx, future in enumerate(as_completed(futures), start=1):
                raw = futures[future]
                row = future.result()
                stats["partials_written"] += 1
                stats["aggregate_rows_written"] += row["aggregate_rows"]
                stats["leaf_rows_processed"] += row["leaf_rows"]
                stats["manifest_tail"] = [*stats["manifest_tail"], row][-25:]
                print(f"[{idx}/{len(pending)}] wrote aggregate checkpoint for {raw.name}", flush=True)

    write_json(
        RESULTS / "run_manifest_exercises_02_12_partials.json",
        {
            "created_at_utc": now_utc(),
            "mode": "exercises_02_12_partial_aggregation",
            "command": " ".join([Path(sys.executable).name, *sys.argv]),
            "partial_dir": str(PARTIAL_DIR.relative_to(RESULTS.parent)),
            "product_excluded_hs6_codes": ["999999"],
            "partner_concentration_includes_hs6_codes": ["999999"],
            "hs6_999999_rows": {
                "product_and_product_partner_partial_checkpoints": 0,
                "partner_dimension": "included in partner totals before partner aggregation",
            },
            "workers": workers,
            "chunk_rows": int(chunk_rows),
            **stats,
            "partials_present": len(list(PARTIAL_DIR.glob("*.parquet"))),
            "exercises_md_updated": False,
        },
    )
    return partials, stats


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def parquet_list_sql(paths: Iterable[Path]) -> str:
    return "[" + ", ".join(sql_literal(str(path)) for path in paths) + "]"


def create_grouped_view(con, partials: list[Path]) -> None:
    if not partials:
        raise RuntimeError("No Exercise 2+12 aggregate partials found.")
    missing = [str(path) for path in partials if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing Exercise 2+12 aggregate partials: {missing[:5]}")
    schemas = [set(parquet_schema_names(path)) for path in partials]
    has_classification_code = any("classification_code" in schema for schema in schemas)
    classification_expr = (
        "CAST(classification_code AS VARCHAR)"
        if has_classification_code
        else "CAST(NULL AS VARCHAR)"
    )
    con.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW grouped_aggregates AS
        SELECT
            CAST(reporter_code AS BIGINT) AS reporter_code,
            CAST(year AS BIGINT) AS year,
            CAST(flow AS VARCHAR) AS flow,
            {classification_expr} AS classification_code,
            CAST(dimension AS VARCHAR) AS dimension,
            CAST(cmd_code AS VARCHAR) AS cmd_code,
            CAST(partner_code AS BIGINT) AS partner_code,
            CAST(hs2 AS VARCHAR) AS hs2,
            SUM(CAST(trade_value AS DOUBLE)) AS trade_value
        FROM read_parquet({parquet_list_sql(partials)}, union_by_name=true)
        WHERE trade_value IS NOT NULL
          AND (
            CAST(dimension AS VARCHAR) NOT IN ('product', 'product_partner_cell')
            OR cmd_code IS NULL
            OR CAST(cmd_code AS VARCHAR) <> '999999'
          )
          AND (partner_code IS NULL OR CAST(partner_code AS BIGINT) <> 0)
        GROUP BY 1, 2, 3, 4, 5, 6, 7, 8
        """
    )


def create_grouped_view_from_ex12_aggregate(con) -> int:
    if not EX12_AGGREGATE_PARQUET.exists():
        raise FileNotFoundError(f"Missing Exercise 12 export aggregate parquet: {EX12_AGGREGATE_PARQUET}")
    con.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW grouped_aggregates AS
        SELECT
            CAST(reporter_code AS BIGINT) AS reporter_code,
            CAST(year AS BIGINT) AS year,
            'Exports' AS flow,
            CAST(classification_code AS VARCHAR) AS classification_code,
            CAST(dimension AS VARCHAR) AS dimension,
            CAST(cmd_code AS VARCHAR) AS cmd_code,
            CAST(partner_code AS BIGINT) AS partner_code,
            CASE
                WHEN cmd_code IS NULL THEN NULL
                ELSE SUBSTR(CAST(cmd_code AS VARCHAR), 1, 2)
            END AS hs2,
            SUM(CAST(trade_value AS DOUBLE)) AS trade_value
        FROM read_parquet({sql_literal(str(EX12_AGGREGATE_PARQUET))})
        WHERE trade_value IS NOT NULL
          AND (
            CAST(dimension AS VARCHAR) NOT IN ('product', 'product_partner_cell')
            OR cmd_code IS NULL
            OR CAST(cmd_code AS VARCHAR) <> '999999'
          )
          AND (partner_code IS NULL OR CAST(partner_code AS BIGINT) <> 0)
        GROUP BY 1, 2, 3, 4, 5, 6, 7, 8
        """
    )
    return int(con.execute("SELECT COUNT(*) FROM grouped_aggregates").fetchone()[0])


def country_panel() -> pd.DataFrame:
    return save_country_panel()[["reporter_code", "country", "iso3"]].copy()


def add_country_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.merge(country_panel(), on="reporter_code", how="left")
    out["country"] = out["country"].fillna(out["reporter_code"].astype(str))
    out["iso3"] = out["iso3"].fillna("")
    return out


def metric_table_from_duckdb(con, dimension: str, prefix: str) -> pd.DataFrame:
    extra_top5 = (
        ", SUM(CASE WHEN desc_rank <= LEAST(5, n) THEN trade_value ELSE 0 END) / MAX(total) AS top_5_partner_share"
        if prefix == "partner"
        else ""
    )
    metrics = con.execute(
        f"""
        WITH ranked AS (
            SELECT
                reporter_code,
                year,
                flow,
                trade_value,
                ROW_NUMBER() OVER (
                    PARTITION BY reporter_code, year, flow
                    ORDER BY trade_value ASC
                ) AS asc_rank,
                ROW_NUMBER() OVER (
                    PARTITION BY reporter_code, year, flow
                    ORDER BY trade_value DESC
                ) AS desc_rank,
                COUNT(*) OVER (PARTITION BY reporter_code, year, flow) AS n,
                SUM(trade_value) OVER (PARTITION BY reporter_code, year, flow) AS total
            FROM grouped_aggregates
            WHERE dimension = ? AND trade_value > 0
        )
        SELECT
            reporter_code,
            year,
            flow,
            'baseline' AS variant,
            MAX(total) AS total_trade_value,
            ((2.0 * SUM(asc_rank * trade_value)) / (MAX(n) * MAX(total))) - ((MAX(n) + 1.0) / MAX(n)) AS {prefix}_gini,
            SUM(CASE WHEN desc_rank <= GREATEST(1, CAST(CEIL(n * 0.01) AS BIGINT)) THEN trade_value ELSE 0 END) / MAX(total)
                AS {prefix}_top_1pct_share,
            SUM(CASE WHEN desc_rank <= GREATEST(1, CAST(CEIL(n * 0.02) AS BIGINT)) THEN trade_value ELSE 0 END) / MAX(total)
                AS {prefix}_top_2pct_share,
            SUM(CASE WHEN desc_rank <= GREATEST(1, CAST(CEIL(n * 0.05) AS BIGINT)) THEN trade_value ELSE 0 END) / MAX(total)
                AS {prefix}_top_5pct_share,
            SUM(CASE WHEN desc_rank <= GREATEST(1, CAST(CEIL(n * 0.10) AS BIGINT)) THEN trade_value ELSE 0 END) / MAX(total)
                AS {prefix}_top_10pct_share,
            SUM(CASE WHEN desc_rank <= LEAST(200, n) THEN trade_value ELSE 0 END) / MAX(total) AS {prefix}_top_200_share,
            CAST(MAX(n) AS BIGINT) AS {prefix}_active_count
            {extra_top5}
        FROM ranked
        GROUP BY reporter_code, year, flow
        ORDER BY reporter_code, year, flow
        """,
        [dimension],
    ).df()
    if metrics.empty:
        return metrics
    metrics = add_country_columns(metrics)
    ordered = ["country", "iso3", "reporter_code", "year", "flow", "variant", "total_trade_value"]
    return metrics[ordered + [col for col in metrics.columns if col not in ordered]]


def build_exercise_02_panel_from_duckdb(con) -> pd.DataFrame:
    product = metric_table_from_duckdb(con, "product", "product")
    partner = metric_table_from_duckdb(con, "partner", "partner")
    cell = metric_table_from_duckdb(con, "product_partner_cell", "product_partner_cell")
    panel = merge_metric_tables(product, partner, cell)
    if panel.empty:
        return pd.DataFrame()

    oil = con.execute(
        """
        SELECT reporter_code, year, flow, SUM(trade_value) AS oil_exports
        FROM grouped_aggregates
        WHERE dimension = 'product' AND flow = 'Exports' AND hs2 = '27'
        GROUP BY reporter_code, year, flow
        """
    ).df()
    panel = panel[panel["flow"] == "Exports"].copy()
    panel = panel.merge(oil, on=["reporter_code", "year", "flow"], how="left")
    panel["oil_exports"] = panel["oil_exports"].fillna(0.0)
    panel["oil_export_share"] = panel["oil_exports"] / panel["total_trade_value"].replace(0, np.nan)
    panel = panel.rename(columns={"total_trade_value": "total_exports"})
    return panel.sort_values(["reporter_code", "year"]).reset_index(drop=True)


def write_exercise_12_export_aggregate(con) -> int:
    con.register("country_panel", country_panel())
    EX12_AGGREGATE_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    con.execute(
        f"""
        COPY (
            SELECT
                g.reporter_code,
                g.year,
                g.classification_code,
                g.cmd_code,
                g.partner_code,
                g.trade_value,
                g.dimension,
                c.country,
                c.iso3
            FROM grouped_aggregates AS g
            LEFT JOIN country_panel AS c
                ON g.reporter_code = c.reporter_code
            WHERE g.flow = 'Exports'
            ORDER BY g.reporter_code, g.year, g.dimension, g.cmd_code, g.partner_code
        )
        TO {sql_literal(str(EX12_AGGREGATE_PARQUET))}
        (FORMAT PARQUET)
        """
    )
    return int(
        con.execute("SELECT COUNT(*) FROM grouped_aggregates WHERE flow = 'Exports'").fetchone()[0]
    )


def read_dimension_values_for_reporter(con, reporter_code: int, dimension: str) -> pd.DataFrame:
    item_cols = item_columns_for_dimension(dimension)
    select_item_cols = [*item_cols]
    if dimension in {"product", "product_partner_cell"}:
        select_item_cols = ["classification_code", *select_item_cols]
    select_cols = ", ".join(["reporter_code", "year", *item_cols, "trade_value"])
    select_cols = ", ".join(["reporter_code", "year", *select_item_cols, "trade_value"])
    values = con.execute(
        f"""
        SELECT {select_cols}
        FROM grouped_aggregates
        WHERE flow = 'Exports'
          AND dimension = ?
          AND reporter_code = ?
          AND trade_value > 0
        ORDER BY year, {", ".join(item_cols)}
        """,
        [dimension, reporter_code],
    ).df()
    if values.empty:
        return values
    values["reporter_code"] = pd.to_numeric(values["reporter_code"], errors="coerce").astype(int)
    values["year"] = pd.to_numeric(values["year"], errors="coerce").astype(int)
    if "partner_code" in values.columns:
        values["partner_code"] = pd.to_numeric(values["partner_code"], errors="coerce").astype(int)
    if "cmd_code" in values.columns:
        values["cmd_code"] = values["cmd_code"].astype(str)
    if "classification_code" in values.columns:
        values["classification_code"] = values["classification_code"].fillna("").astype(str)
    values["trade_value"] = pd.to_numeric(values["trade_value"], errors="coerce")
    return values.dropna(subset=["trade_value"]).copy()


def aggregate_dataset_counts() -> dict[str, int]:
    try:
        import pyarrow.dataset as ds
    except ImportError as exc:  # pragma: no cover - runtime dependency guard
        raise SystemExit("Missing dependency 'pyarrow'. Run: python3 -m pip install -r requirements.txt") from exc
    dataset = ds.dataset(EX12_AGGREGATE_PARQUET)
    not_world = ds.field("partner_code").is_null() | (ds.field("partner_code") != 0)
    product_dependent = ds.field("dimension").isin(["product", "product_partner_cell"])
    is_999999 = ds.field("cmd_code") == "999999"
    product_dependent_999999 = product_dependent & is_999999
    return {
        "aggregate_rows": int(dataset.count_rows(filter=(~product_dependent_999999) & not_world)),
        "partner_code_0_rows": int(dataset.count_rows(filter=ds.field("partner_code") == 0)),
        "product_dependent_hs6_999999_rows": int(dataset.count_rows(filter=product_dependent_999999)),
    }


def reporter_codes_from_existing_ex12_aggregate() -> list[int]:
    panel = save_country_panel()
    codes = sorted(pd.to_numeric(panel["reporter_code"], errors="coerce").dropna().astype(int).unique().tolist())
    if codes:
        return codes
    try:
        codes_df = pd.read_parquet(EX12_AGGREGATE_PARQUET, columns=["reporter_code"])
    except Exception:
        return []
    return sorted(pd.to_numeric(codes_df["reporter_code"], errors="coerce").dropna().astype(int).unique().tolist())


def read_existing_aggregate_dimension_for_reporter(reporter_code: int, dimension: str) -> pd.DataFrame:
    item_cols = item_columns_for_dimension(dimension)
    select_item_cols = [*item_cols]
    if dimension in {"product", "product_partner_cell"}:
        select_item_cols = ["classification_code", *select_item_cols]
    cols = ["reporter_code", "year", *select_item_cols, "trade_value"]
    values = pd.read_parquet(
        EX12_AGGREGATE_PARQUET,
        columns=cols,
        filters=[("reporter_code", "=", int(reporter_code)), ("dimension", "=", dimension)],
    )
    if values.empty:
        return values
    values["reporter_code"] = pd.to_numeric(values["reporter_code"], errors="coerce").astype(int)
    values["year"] = pd.to_numeric(values["year"], errors="coerce").astype(int)
    if "partner_code" in values.columns:
        values["partner_code"] = pd.to_numeric(values["partner_code"], errors="coerce").astype("Int64")
        values = values[(values["partner_code"].isna()) | (values["partner_code"] != 0)].copy()
        values["partner_code"] = values["partner_code"].astype(int)
    if "cmd_code" in values.columns:
        values["cmd_code"] = values["cmd_code"].astype(str)
        if dimension in {"product", "product_partner_cell"}:
            values = values[values["cmd_code"] != "999999"].copy()
    if "classification_code" in values.columns:
        values["classification_code"] = values["classification_code"].fillna("").astype(str)
    values["trade_value"] = pd.to_numeric(values["trade_value"], errors="coerce")
    return values.dropna(subset=["trade_value"]).copy()


def existing_aggregate_dimension_row_count(reporter_code: int, dimension: str) -> int:
    try:
        import pyarrow.dataset as ds
    except ImportError as exc:  # pragma: no cover - runtime dependency guard
        raise SystemExit("Missing dependency 'pyarrow'. Run: python3 -m pip install -r requirements.txt") from exc
    dataset = ds.dataset(EX12_AGGREGATE_PARQUET)
    row_filter = (ds.field("reporter_code") == int(reporter_code)) & (ds.field("dimension") == dimension)
    return int(dataset.count_rows(filter=row_filter))


def existing_aggregate_years_for_reporter_dimension(reporter_code: int, dimension: str) -> list[int]:
    years = pd.read_parquet(
        EX12_AGGREGATE_PARQUET,
        columns=["year"],
        filters=[("reporter_code", "=", int(reporter_code)), ("dimension", "=", dimension)],
    )
    if years.empty:
        return []
    return sorted(pd.to_numeric(years["year"], errors="coerce").dropna().astype(int).unique().tolist())


def read_existing_aggregate_dimension_year_for_reporter(reporter_code: int, dimension: str, year: int) -> pd.DataFrame:
    item_cols = item_columns_for_dimension(dimension)
    select_item_cols = [*item_cols]
    if dimension in {"product", "product_partner_cell"}:
        select_item_cols = ["classification_code", *select_item_cols]
    cols = ["reporter_code", "year", *select_item_cols, "trade_value"]
    values = pd.read_parquet(
        EX12_AGGREGATE_PARQUET,
        columns=cols,
        filters=[
            ("reporter_code", "=", int(reporter_code)),
            ("dimension", "=", dimension),
            ("year", "=", int(year)),
        ],
    )
    if values.empty:
        return values
    values["reporter_code"] = pd.to_numeric(values["reporter_code"], errors="coerce").astype(int)
    values["year"] = pd.to_numeric(values["year"], errors="coerce").astype(int)
    if "partner_code" in values.columns:
        values["partner_code"] = pd.to_numeric(values["partner_code"], errors="coerce").astype("Int64")
        values = values[(values["partner_code"].isna()) | (values["partner_code"] != 0)].copy()
        if not values.empty:
            values["partner_code"] = values["partner_code"].astype(int)
    if "cmd_code" in values.columns:
        values["cmd_code"] = values["cmd_code"].astype(str)
        if dimension in {"product", "product_partner_cell"}:
            values = values[values["cmd_code"] != "999999"].copy()
    if "classification_code" in values.columns:
        values["classification_code"] = values["classification_code"].fillna("").astype(str)
    values["trade_value"] = pd.to_numeric(values["trade_value"], errors="coerce")
    values = values.dropna(subset=["trade_value"])
    return values[values["trade_value"] > 0].copy()


def classification_signature(values: pd.DataFrame) -> tuple[str, ...]:
    if values.empty or "classification_code" not in values.columns:
        return ("UNKNOWN",)
    codes = values["classification_code"].map(normalize_hs_classification_code).replace("", "UNKNOWN")
    return tuple(sorted(set(codes.dropna().astype(str))))


def empty_hs_harmonization_accumulator() -> dict[str, object]:
    return {
        "observed_rows": 0,
        "observed_trade_value": 0.0,
        "matched_trade_value": 0.0,
        "unmatched_trade_value": 0.0,
        "ambiguous_trade_value": 0.0,
        "observed_nodes": set(),
        "unmatched_nodes": set(),
        "ambiguous_nodes": set(),
        "collapsed_nodes": set(),
        "families": set(),
        "max_source_component_node_count": np.nan,
        "family_records": [],
    }


def accumulate_hs_harmonization_diagnostics(
    accumulator: dict[str, object],
    values: pd.DataFrame,
    hs_family_mapping: pd.DataFrame,
) -> None:
    if values.empty:
        return
    work = values.copy()
    if "classification_code" not in work.columns:
        work["classification_code"] = ""
    if "cmd_code" not in work.columns:
        return
    work["reporter_code"] = pd.to_numeric(work["reporter_code"], errors="coerce")
    work["year"] = pd.to_numeric(work["year"], errors="coerce")
    work["trade_value"] = pd.to_numeric(work["trade_value"], errors="coerce")
    work["classification_code"] = work["classification_code"].map(normalize_hs_classification_code).replace("", "UNKNOWN")
    work["cmd_code"] = work["cmd_code"].astype(str).str.extract(r"(\d{6})", expand=False)
    work = work.dropna(subset=["reporter_code", "year", "trade_value", "cmd_code"])
    work = drop_excluded_hs6(work)
    if work.empty:
        return
    if "harmonized_product_id" not in hs_family_mapping.columns:
        weights = hs_family_mapping
        keys = weights[["source_classification_code", "source_cmd_code"]].drop_duplicates()
        targets = weights[
            ["source_classification_code", "source_cmd_code", "target_product_id"]
        ].drop_duplicates()
        target_counts = (
            targets.groupby(["source_classification_code", "source_cmd_code"], observed=True)["target_product_id"]
            .nunique()
            .reset_index(name="source_component_node_count")
        )
        matched = work.merge(
            keys.assign(_lt_hgl_match=True),
            left_on=["classification_code", "cmd_code"],
            right_on=["source_classification_code", "source_cmd_code"],
            how="left",
            validate="many_to_one",
        ).merge(
            target_counts,
            left_on=["classification_code", "cmd_code"],
            right_on=["source_classification_code", "source_cmd_code"],
            how="left",
        )
        matched["node_id"] = matched["classification_code"] + ":" + matched["cmd_code"]
        matched["is_unmatched"] = matched["_lt_hgl_match"].isna()
        matched["harmonization_status"] = np.where(
            matched["is_unmatched"],
            "lt_hgl_missing_weight",
            "lt_hgl_weighted_hs1992",
        )

        accumulator["observed_rows"] = int(accumulator["observed_rows"]) + int(len(matched))
        accumulator["observed_trade_value"] = float(accumulator["observed_trade_value"]) + float(matched["trade_value"].sum())
        unmatched_value = float(matched.loc[matched["is_unmatched"], "trade_value"].sum())
        accumulator["unmatched_trade_value"] = float(accumulator["unmatched_trade_value"]) + unmatched_value
        accumulator["matched_trade_value"] = float(accumulator["matched_trade_value"]) + float(matched["trade_value"].sum() - unmatched_value)
        accumulator["ambiguous_trade_value"] = float(accumulator["ambiguous_trade_value"])
        accumulator["observed_nodes"].update(matched["node_id"].dropna().astype(str).unique().tolist())
        accumulator["unmatched_nodes"].update(matched.loc[matched["is_unmatched"], "node_id"].dropna().astype(str).unique().tolist())
        matched_targets = matched[["classification_code", "cmd_code"]].drop_duplicates().merge(
            targets,
            left_on=["classification_code", "cmd_code"],
            right_on=["source_classification_code", "source_cmd_code"],
            how="left",
        )
        matched_targets["node_id"] = matched_targets["classification_code"] + ":" + matched_targets["cmd_code"]
        accumulator["families"].update(matched_targets["target_product_id"].dropna().astype(str).unique().tolist())
        max_targets = pd.to_numeric(matched["source_component_node_count"], errors="coerce").max()
        if pd.notna(max_targets):
            existing = accumulator["max_source_component_node_count"]
            accumulator["max_source_component_node_count"] = float(max_targets) if pd.isna(existing) else max(float(existing), float(max_targets))
        family_records = matched[["node_id", "harmonization_status", "source_component_node_count"]].drop_duplicates().merge(
            matched_targets[["node_id", "target_product_id"]].drop_duplicates(),
            on="node_id",
            how="left",
        )
        family_records = family_records.rename(columns={"target_product_id": "harmonized_product_id"})[
            ["node_id", "harmonized_product_id", "harmonization_status", "source_component_node_count"]
        ]
        accumulator["family_records"].append(family_records)
        return

    work = attach_hs_harmonized_product_id(work, hs_family_mapping)
    work["node_id"] = work["classification_code"] + ":" + work["cmd_code"]
    work["is_unmatched"] = work["harmonization_status"].astype(str).str.startswith("unmatched")
    work["is_ambiguous"] = work["harmonization_status"].eq("ambiguous_oversized_component")
    work["is_collapsed_family"] = pd.to_numeric(work["analysis_family_node_count"], errors="coerce").fillna(1) > 1

    accumulator["observed_rows"] = int(accumulator["observed_rows"]) + int(len(work))
    accumulator["observed_trade_value"] = float(accumulator["observed_trade_value"]) + float(work["trade_value"].sum())
    accumulator["matched_trade_value"] = float(accumulator["matched_trade_value"]) + float(
        work.loc[~work["is_unmatched"] & ~work["is_ambiguous"], "trade_value"].sum()
    )
    accumulator["unmatched_trade_value"] = float(accumulator["unmatched_trade_value"]) + float(
        work.loc[work["is_unmatched"], "trade_value"].sum()
    )
    accumulator["ambiguous_trade_value"] = float(accumulator["ambiguous_trade_value"]) + float(
        work.loc[work["is_ambiguous"], "trade_value"].sum()
    )
    accumulator["observed_nodes"].update(work["node_id"].dropna().astype(str).unique().tolist())
    accumulator["unmatched_nodes"].update(work.loc[work["is_unmatched"], "node_id"].dropna().astype(str).unique().tolist())
    accumulator["ambiguous_nodes"].update(work.loc[work["is_ambiguous"], "node_id"].dropna().astype(str).unique().tolist())
    accumulator["collapsed_nodes"].update(work.loc[work["is_collapsed_family"], "node_id"].dropna().astype(str).unique().tolist())
    accumulator["families"].update(work["harmonized_product_id"].dropna().astype(str).unique().tolist())
    max_component = pd.to_numeric(work["source_component_node_count"], errors="coerce").max()
    if pd.notna(max_component):
        existing = accumulator["max_source_component_node_count"]
        accumulator["max_source_component_node_count"] = float(max_component) if pd.isna(existing) else max(float(existing), float(max_component))
    family_records = work.drop_duplicates(
        ["node_id", "harmonized_product_id", "harmonization_status", "source_component_node_count"]
    )[["node_id", "harmonized_product_id", "harmonization_status", "source_component_node_count"]]
    accumulator["family_records"].append(family_records)


def hs_harmonization_diagnostics_from_accumulator(
    accumulator: dict[str, object],
    reporter_code: int,
    dimension: str,
) -> pd.DataFrame:
    if int(accumulator["observed_rows"]) == 0:
        return pd.DataFrame()
    observed_nodes = accumulator["observed_nodes"]
    unmatched_nodes = accumulator["unmatched_nodes"]
    ambiguous_nodes = accumulator["ambiguous_nodes"]
    collapsed_nodes = accumulator["collapsed_nodes"]
    families = accumulator["families"]
    observed_codes = len(observed_nodes)
    observed_value = float(accumulator["observed_trade_value"])
    family_records = accumulator["family_records"]
    lt_hgl_mode = bool(
        family_records
        and any(
            frame.get("harmonization_status", pd.Series(dtype=str)).astype(str).str.startswith("lt_hgl_").any()
            for frame in family_records
            if not frame.empty
        )
    )
    rows = [
        {
            "diagnostic_type": "coverage",
            "reporter_code": int(reporter_code),
            "dimension": dimension,
            "harmonization_status": "lt_hgl_weighted_hs1992" if lt_hgl_mode else "all_observed",
            "source_component_node_count": np.nan,
            "observed_rows": int(accumulator["observed_rows"]),
            "observed_revision_codes": observed_codes,
            "analysis_families": len(families),
            "observed_trade_value": observed_value,
            "matched_trade_value": float(accumulator["matched_trade_value"]),
            "unmatched_trade_value": float(accumulator["unmatched_trade_value"]),
            "ambiguous_trade_value": float(accumulator["ambiguous_trade_value"]),
            "unmatched_code_share": len(unmatched_nodes) / observed_codes if observed_codes else np.nan,
            "unmatched_value_share": float(accumulator["unmatched_trade_value"]) / observed_value if observed_value else np.nan,
            "ambiguous_code_share": len(ambiguous_nodes) / observed_codes if observed_codes else np.nan,
            "ambiguous_value_share": float(accumulator["ambiguous_trade_value"]) / observed_value if observed_value else np.nan,
            "collapsed_family_code_share": len(collapsed_nodes) / observed_codes if observed_codes else np.nan,
            "max_source_component_node_count": accumulator["max_source_component_node_count"],
            "old_same_revision_exclusion_comparison": (
                "LT/HGL weighted conversion to HS1992/H0; harmonized mode does not drop pairs solely because HS revision changes."
                if lt_hgl_mode
                else "See hs_revision_pair_diagnostics.csv; harmonized mode does not drop pairs solely because HS revision changes."
            ),
        }
    ]
    if family_records:
        family_sizes = (
            pd.concat(family_records, ignore_index=True)
            .drop_duplicates(["node_id", "harmonized_product_id", "harmonization_status", "source_component_node_count"])
            .groupby(["harmonization_status", "source_component_node_count"], dropna=False, as_index=False)
            .agg(observed_revision_codes=("node_id", "nunique"), analysis_families=("harmonized_product_id", "nunique"))
        )
        for row in family_sizes.itertuples(index=False):
            rows.append(
                {
                    "diagnostic_type": "family_size_distribution",
                    "reporter_code": int(reporter_code),
                    "dimension": dimension,
                    "harmonization_status": row.harmonization_status,
                    "source_component_node_count": row.source_component_node_count,
                    "observed_rows": np.nan,
                    "observed_revision_codes": int(row.observed_revision_codes),
                    "analysis_families": int(row.analysis_families),
                    "observed_trade_value": np.nan,
                    "matched_trade_value": np.nan,
                    "unmatched_trade_value": np.nan,
                    "ambiguous_trade_value": np.nan,
                    "unmatched_code_share": np.nan,
                    "unmatched_value_share": np.nan,
                    "ambiguous_code_share": np.nan,
                    "ambiguous_value_share": np.nan,
                    "collapsed_family_code_share": np.nan,
                    "max_source_component_node_count": row.source_component_node_count,
                    "old_same_revision_exclusion_comparison": "See hs_revision_pair_diagnostics.csv.",
                }
            )
    return pd.DataFrame(rows)


def spill_large_product_partner_cell_from_existing_aggregate(
    reporter_code: int,
    horizons: tuple[int, ...],
    cpa_mapping: pd.DataFrame,
    spill_paths: dict[str, list[Path]],
    spill_dir: Path,
    scope_states_path: Path,
    scope_header_written: bool,
) -> bool:
    dimension = "product_partner_cell"
    years = existing_aggregate_years_for_reporter_dimension(reporter_code, dimension)
    if not years:
        return scope_header_written
    year_set = set(years)
    year_cache: OrderedDict[int, pd.DataFrame] = OrderedDict()
    hs_family_mapping = load_lt_hgl_hs1992_conversion_weights()

    def get_year_values(year: int) -> pd.DataFrame:
        year = int(year)
        if year in year_cache:
            year_cache.move_to_end(year)
            return year_cache[year]
        values = read_existing_aggregate_dimension_year_for_reporter(reporter_code, dimension, year)
        year_cache[year] = values
        while len(year_cache) > 3:
            old_year, old_values = year_cache.popitem(last=False)
            del old_year, old_values
            gc.collect()
        return values

    item_year_cache: OrderedDict[tuple[str, int], pd.DataFrame] = OrderedDict()

    def get_item_year_values(item_id_mode: str, year: int) -> pd.DataFrame:
        year = int(year)
        key = (item_id_mode, year)
        if key in item_year_cache:
            item_year_cache.move_to_end(key)
            return item_year_cache[key]
        values = get_year_values(year)
        item_values = prepare_exercise_12_item_values(
            values,
            dimension,
            item_id_mode,
            cpa_mapping=cpa_mapping,
            hs_family_mapping=hs_family_mapping,
        )
        item_year_cache[key] = item_values
        while len(item_year_cache) > 4:
            old_key, old_values = item_year_cache.popitem(last=False)
            del old_key, old_values
            gc.collect()
        return item_values

    def flush_chunks(chunks_by_kind: dict[str, list[pd.DataFrame]]) -> None:
        for kind, chunks in list(chunks_by_kind.items()):
            if not chunks:
                continue
            combined = pd.concat(chunks, ignore_index=True) if len(chunks) > 1 else chunks[0]
            spill_exercise_12_frame(combined, spill_paths, spill_dir, kind, reporter_code, dimension)
            del combined, chunks
            chunks_by_kind[kind] = []
            gc.collect()

    harmonization_accumulator = empty_hs_harmonization_accumulator()
    scope_frames: list[pd.DataFrame] = []
    for year in years:
        year_values = get_year_values(year)
        accumulate_hs_harmonization_diagnostics(harmonization_accumulator, year_values, hs_family_mapping)
        scope = product_scope_states(year_values)
        if not scope.empty:
            scope.to_csv(scope_states_path, mode="a", header=not scope_header_written, index=False)
            scope_header_written = True
            scope_frames.append(scope)
        del scope
        gc.collect()
    harmonization_diagnostics = hs_harmonization_diagnostics_from_accumulator(
        harmonization_accumulator,
        reporter_code,
        dimension,
    )
    if not harmonization_diagnostics.empty:
        spill_exercise_12_frame(
            harmonization_diagnostics,
            spill_paths,
            spill_dir,
            "hs_harmonization_diagnostics",
            reporter_code,
            dimension,
        )

    if scope_frames:
        scope_all = pd.concat(scope_frames, ignore_index=True)
        scope_item_cols = ["product_identity"] if "product_identity" in scope_all.columns else ["cmd_code"]
        for state_col in ["destination_state", "region_state"]:
            scope_transition = transition_matrix(scope_all, scope_item_cols, state_col, horizons)
            if not scope_transition.empty:
                spill_exercise_12_frame(scope_transition, spill_paths, spill_dir, "scope_transition", reporter_code, state_col)
            del scope_transition
        del scope_all, scope_frames
        gc.collect()

    hs_revision_diagnostics: list[dict[str, object]] = []
    for item_id_mode in exercise_12_item_modes_for_dimension(dimension):
        print(f"  product_partner_cell streaming mode={item_id_mode}", flush=True)
        chunks_by_kind: dict[str, list[pd.DataFrame]] = {}
        pairs_processed = 0
        for horizon in horizons:
            for base_year in years:
                future_year = int(base_year) + int(horizon)
                if future_year not in year_set:
                    continue
                if item_id_mode == "hs6_revision":
                    base_values = get_year_values(base_year)
                    future_values = get_year_values(future_year)
                    base_signature = classification_signature(base_values)
                    future_signature = classification_signature(future_values)
                    if base_signature != future_signature:
                        hs_revision_diagnostics.append(
                            {
                                "reporter_code": int(reporter_code),
                                "base_year": int(base_year),
                                "future_year": int(future_year),
                                "horizon": int(horizon),
                                "dimension": dimension,
                                "item_id_mode": "hs6_revision",
                                "base_classification_code": "|".join(base_signature),
                                "future_classification_code": "|".join(future_signature),
                                "excluded_base_items": int(base_values[["cmd_code", "partner_code"]].drop_duplicates().shape[0]),
                                "excluded_future_items": int(future_values[["cmd_code", "partner_code"]].drop_duplicates().shape[0]),
                                "excluded_base_value": float(base_values["trade_value"].sum()),
                                "excluded_future_value": float(future_values["trade_value"].sum()),
                            }
                        )
                        continue
                base_item_values = get_item_year_values(item_id_mode, base_year)
                future_item_values = get_item_year_values(item_id_mode, future_year)
                item_frames = [frame for frame in [base_item_values, future_item_values] if not frame.empty]
                item_values = pd.concat(item_frames, ignore_index=True) if item_frames else pd.DataFrame()
                if item_values.empty:
                    del item_values
                    continue
                states = assign_size_state_columns(item_values)
                del item_values
                paired = exercise_12_pair_merge_wide_for_base_year(states, reporter_code, int(base_year), int(horizon))
                del states
                if paired.empty:
                    del paired
                    continue
                for top_definition in EX12_TOP_DEFINITIONS:
                    net, gross, transitions = exercise_12_accounting_from_pair(
                        paired,
                        dimension,
                        int(horizon),
                        item_id_mode,
                        top_definition,
                    )
                    if not net.empty:
                        chunks_by_kind.setdefault("net", []).append(net)
                    if not gross.empty:
                        chunks_by_kind.setdefault("gross", []).append(gross)
                    if not transitions.empty:
                        chunks_by_kind.setdefault("size_transition", []).append(transitions)
                    del net, gross, transitions
                del paired
                pairs_processed += 1
                if pairs_processed % 20 == 0:
                    flush_chunks(chunks_by_kind)
                gc.collect()
        flush_chunks(chunks_by_kind)
        item_year_cache.clear()
        gc.collect()

    if hs_revision_diagnostics:
        spill_exercise_12_frame(
            pd.DataFrame(hs_revision_diagnostics),
            spill_paths,
            spill_dir,
            "hs_revision_diagnostics",
            reporter_code,
            dimension,
        )
    year_cache.clear()
    gc.collect()
    return scope_header_written


def spill_exercise_12_frame(
    df: pd.DataFrame,
    spill_paths: dict[str, list[Path]],
    spill_dir: Path,
    kind: str,
    reporter_code: int,
    dimension: str | None = None,
) -> None:
    if df.empty:
        return
    target_dir = spill_dir / kind
    target_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"_{dimension}" if dimension else ""
    path = target_dir / f"reporter_{int(reporter_code)}{suffix}.csv"
    exists = path.exists()
    df.to_csv(path, index=False, mode="a" if exists else "w", header=not exists)
    paths = spill_paths.setdefault(kind, [])
    if path not in paths:
        paths.append(path)


def spill_path_for(spill_dir: Path, kind: str, reporter_code: int, dimension: str | None = None) -> Path:
    suffix = f"_{dimension}" if dimension else ""
    return spill_dir / kind / f"reporter_{int(reporter_code)}{suffix}.csv"


def nonempty_path(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def collect_existing_spill_paths(spill_dir: Path) -> dict[str, list[Path]]:
    spill_paths = {
        "net": [],
        "gross": [],
        "size_transition": [],
        "hs_revision_diagnostics": [],
        "hs_harmonization_diagnostics": [],
        "scope_transition": [],
    }
    for kind in spill_paths:
        kind_dir = spill_dir / kind
        if kind_dir.exists():
            spill_paths[kind] = sorted(path for path in kind_dir.glob("*.csv") if nonempty_path(path))
    return spill_paths


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def exercise_12_spill_spec(source_details: dict) -> dict[str, object]:
    aggregate_stat = EX12_AGGREGATE_PARQUET.stat() if EX12_AGGREGATE_PARQUET.exists() else None
    script_paths = [Path(__file__), Path(__file__).with_name("trade_concentration_pipeline.py")]
    return {
        "version": EX12_SPILL_SPEC_VERSION,
        "country_sample": source_details.get("country_sample"),
        "aggregate_path": str(EX12_AGGREGATE_PARQUET.relative_to(RESULTS.parent)),
        "aggregate_size": int(aggregate_stat.st_size) if aggregate_stat else None,
        "aggregate_mtime_ns": int(aggregate_stat.st_mtime_ns) if aggregate_stat else None,
        "dimensions": list(DIMENSIONS),
        "top_definitions": list(EX12_TOP_DEFINITIONS),
        "product_item_modes": list(exercise_12_item_modes_for_dimension("product")),
        "partner_item_modes": list(exercise_12_item_modes_for_dimension("partner")),
        "product_excluded_hs6_codes": ["999999"],
        "partner_concentration_includes_hs6_codes": ["999999"],
        "partner_code_0_excluded": True,
        "stream_threshold_rows": int(EX12_EXISTING_AGGREGATE_STREAM_ROWS),
        "script_hashes": {
            str(path.relative_to(RESULTS.parent)): sha256_file(path)
            for path in script_paths
        },
    }


def spill_manifest_path(spill_dir: Path) -> Path:
    return spill_dir / "_manifest.json"


def prepare_spill_directory(spill_dir: Path, source_details: dict, resume_spill: bool) -> None:
    expected_spec = exercise_12_spill_spec(source_details)
    manifest_path = spill_manifest_path(spill_dir)
    if resume_spill and spill_dir.exists():
        if not manifest_path.exists():
            raise RuntimeError(
                "Cannot resume Exercise 12 spill files without a spill manifest. "
                "Rerun without --resume-exercise-12-spill to rebuild spill outputs."
            )
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("spec") != expected_spec:
            raise RuntimeError(
                "Existing Exercise 12 spill manifest does not match the current aggregate/code/spec. "
                "Rerun without --resume-exercise-12-spill to rebuild spill outputs."
            )
        return
    if spill_dir.exists():
        shutil.rmtree(spill_dir)
    spill_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        manifest_path,
        {
            "created_at_utc": now_utc(),
            "spec": expected_spec,
            "source_details": source_details,
        },
    )


def clear_spill_outputs_for_dimension(
    spill_paths: dict[str, list[Path]],
    spill_dir: Path,
    reporter_code: int,
    dimension: str,
) -> None:
    for kind in ["net", "gross", "size_transition", "hs_revision_diagnostics", "hs_harmonization_diagnostics"]:
        path = spill_path_for(spill_dir, kind, reporter_code, dimension)
        if path.exists():
            path.unlink()
        if path in spill_paths.get(kind, []):
            spill_paths[kind] = [existing for existing in spill_paths[kind] if existing != path]
    if dimension == "product_partner_cell":
        for state_col in ["destination_state", "region_state"]:
            path = spill_path_for(spill_dir, "scope_transition", reporter_code, state_col)
            if path.exists():
                path.unlink()
            if path in spill_paths.get("scope_transition", []):
                spill_paths["scope_transition"] = [
                    existing for existing in spill_paths["scope_transition"] if existing != path
                ]


def remove_scope_state_rows_for_reporter(scope_states_path: Path, reporter_code: int) -> None:
    if not scope_states_path.exists() or scope_states_path.stat().st_size == 0:
        return
    scope = pd.read_csv(scope_states_path)
    if scope.empty or "reporter_code" not in scope.columns:
        return
    reporter_values = pd.to_numeric(scope["reporter_code"], errors="coerce")
    scope = scope[reporter_values != int(reporter_code)].copy()
    scope.to_csv(scope_states_path, index=False)


def dimension_spill_complete(spill_dir: Path, reporter_code: int, dimension: str) -> bool:
    required = ["net", "gross", "size_transition"]
    if dimension in {"product", "product_partner_cell"}:
        required.append("hs_harmonization_diagnostics")
        required.append("hs_revision_diagnostics")
    for kind in required:
        if not nonempty_path(spill_path_for(spill_dir, kind, reporter_code, dimension)):
            return False
    if dimension == "product_partner_cell":
        for state_col in ["destination_state", "region_state"]:
            if not nonempty_path(spill_path_for(spill_dir, "scope_transition", reporter_code, state_col)):
                return False
    return True


def read_spilled_exercise_12_frames(paths: list[Path]) -> pd.DataFrame:
    if not paths:
        return pd.DataFrame()
    frames = []
    for path in paths:
        frames.append(pd.read_csv(path))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def spill_exercise_12_chunks_for_values(
    values: pd.DataFrame,
    dimension: str,
    reporter_code: int,
    horizons: tuple[int, ...],
    cpa_mapping: pd.DataFrame,
    spill_paths: dict[str, list[Path]],
    spill_dir: Path,
) -> None:
    chunks_by_kind: dict[str, list[pd.DataFrame]] = {}
    for kind, chunk in iter_exercise_12_accounting_output_chunks(values, dimension, horizons, cpa_mapping=cpa_mapping):
        if not chunk.empty:
            chunks_by_kind.setdefault(kind, []).append(chunk)
        gc.collect()
    for kind, chunks in chunks_by_kind.items():
        combined = pd.concat(chunks, ignore_index=True) if len(chunks) > 1 else chunks[0]
        spill_exercise_12_frame(combined, spill_paths, spill_dir, kind, reporter_code, dimension)
        del combined, chunks
        gc.collect()


def finalize_exercise_12_from_existing_aggregate(
    source_details: dict,
    resume_spill: bool = False,
) -> tuple[pd.DataFrame, dict]:
    counts = aggregate_dataset_counts()
    reporter_codes = reporter_codes_from_existing_ex12_aggregate()
    horizons = (5, 10)
    spill_dir = EX12_AGGREGATE_PARQUET.parent / "exercise_12_finalize_spill"
    prepare_spill_directory(spill_dir, source_details, resume_spill=resume_spill)
    spill_paths = collect_existing_spill_paths(spill_dir)
    cpa_mapping = load_btige_cpa_mapping()
    scope_states_path = EX12_TABLES / "product_destination_region_states.csv"
    if scope_states_path.exists() and not resume_spill:
        scope_states_path.unlink()
    scope_header_written = scope_states_path.exists() and scope_states_path.stat().st_size > 0

    for idx, reporter_code in enumerate(reporter_codes, start=1):
        print(f"finalizing Exercise 12 reporter {idx}/{len(reporter_codes)}: {reporter_code}", flush=True)
        for dimension in ("product_partner_cell", "product", "partner"):
            if resume_spill and dimension_spill_complete(spill_dir, reporter_code, dimension):
                print(f"  reusing existing spill for {dimension}", flush=True)
                continue
            if resume_spill:
                clear_spill_outputs_for_dimension(spill_paths, spill_dir, reporter_code, dimension)
                if dimension == "product_partner_cell":
                    remove_scope_state_rows_for_reporter(scope_states_path, reporter_code)
                    scope_header_written = scope_states_path.exists() and scope_states_path.stat().st_size > 0
            if dimension == "product_partner_cell":
                dimension_rows = existing_aggregate_dimension_row_count(reporter_code, dimension)
                if dimension_rows > EX12_EXISTING_AGGREGATE_STREAM_ROWS:
                    print(
                        f"  streaming product_partner_cell from existing aggregate ({dimension_rows:,} rows)",
                        flush=True,
                    )
                    scope_header_written = spill_large_product_partner_cell_from_existing_aggregate(
                        reporter_code,
                        horizons,
                        cpa_mapping,
                        spill_paths,
                        spill_dir,
                        scope_states_path,
                        scope_header_written,
                    )
                    continue
            dimension_values = read_existing_aggregate_dimension_for_reporter(reporter_code, dimension)
            if dimension_values.empty:
                continue
            spill_exercise_12_chunks_for_values(
                dimension_values,
                dimension,
                reporter_code,
                horizons,
                cpa_mapping,
                spill_paths,
                spill_dir,
            )
            del dimension_values
            gc.collect()

        product_partner_rows = existing_aggregate_dimension_row_count(reporter_code, "product_partner_cell")
        if product_partner_rows > EX12_EXISTING_AGGREGATE_STREAM_ROWS:
            gc.collect()
            continue
        product_partner = read_existing_aggregate_dimension_for_reporter(reporter_code, "product_partner_cell")
        if not product_partner.empty:
            scope = product_scope_states(product_partner)
            if not scope.empty:
                scope.to_csv(scope_states_path, mode="a", header=not scope_header_written, index=False)
                scope_header_written = True
                scope_item_cols = ["product_identity"] if "product_identity" in scope.columns else ["cmd_code"]
                for state_col in ["destination_state", "region_state"]:
                    scope_transition = transition_matrix(scope, scope_item_cols, state_col, horizons)
                    if not scope_transition.empty:
                        spill_exercise_12_frame(scope_transition, spill_paths, spill_dir, "scope_transition", reporter_code, state_col)
                    del scope_transition
            del scope
        del product_partner
        gc.collect()

    decomposition = read_spilled_exercise_12_frames(spill_paths["net"])
    gross_decomposition = read_spilled_exercise_12_frames(spill_paths["gross"])
    hs_diagnostics = read_spilled_exercise_12_frames(spill_paths["hs_revision_diagnostics"])
    hs_harmonization_diagnostics = read_spilled_exercise_12_frames(spill_paths["hs_harmonization_diagnostics"])

    if not decomposition.empty:
        decomposition = add_country_metadata(decomposition)
    if not gross_decomposition.empty:
        gross_decomposition = add_country_metadata(gross_decomposition)
    if not hs_diagnostics.empty:
        hs_diagnostics = add_country_metadata(hs_diagnostics)
    main_decomposition = exercise_12_headline_decomposition(decomposition) if not decomposition.empty else decomposition
    decomposition.to_csv(EX12_TABLES / "growth_decomposition_net.csv", index=False)
    gross_decomposition.to_csv(EX12_TABLES / "growth_decomposition_gross.csv", index=False)
    hs_diagnostics.to_csv(EX12_TABLES / "hs_revision_pair_diagnostics.csv", index=False)
    hs_harmonization_diagnostics.to_csv(EX12_TABLES / "hs_harmonization_diagnostics.csv", index=False)
    main_decomposition.to_parquet(EX12_DECOMPOSITION_PARQUET, index=False)
    main_decomposition.to_csv(EX12_TABLES / "growth_decomposition.csv", index=False)

    size_transitions = (
        read_spilled_exercise_12_frames(spill_paths["size_transition"])
        if spill_paths["size_transition"]
        else pd.DataFrame(columns=["base_state", "future_state", "item_count", "horizon", "transition_type"])
    )
    if not size_transitions.empty:
        size_transitions = add_country_metadata(size_transitions)
    size_transitions.to_csv(EX12_TABLES / "transition_matrices_detailed.csv", index=False)
    size_transitions.to_csv(EX12_TABLES / "size_transition_matrices.csv", index=False)

    scope_transitions = (
        read_spilled_exercise_12_frames(spill_paths["scope_transition"])
        if spill_paths["scope_transition"]
        else pd.DataFrame(columns=["base_state", "future_state", "size", "horizon", "transition_type"])
    )
    scope_transitions = scope_transitions.groupby(
        ["base_state", "future_state", "horizon", "transition_type"], as_index=False
    )["size"].sum()
    scope_transitions.to_csv(EX12_TABLES / "product_scope_transition_matrices.csv", index=False)

    make_exercise_12_figures(main_decomposition, size_transitions, scope_transitions)
    write_exercise_12_memo(
        main_decomposition,
        size_transitions,
        scope_transitions,
        source_details,
        gross_decomposition=gross_decomposition,
        hs_diagnostics=hs_diagnostics,
        hs_harmonization_diagnostics=hs_harmonization_diagnostics,
    )
    stats = {
        "rows_ex12_export_aggregates": counts["aggregate_rows"],
        "rows_ex12_decomposition": int(len(main_decomposition)),
        "rows_ex12_decomposition_net_all": int(len(decomposition)),
        "rows_ex12_decomposition_gross": int(len(gross_decomposition)),
        "rows_ex12_size_transitions": int(len(size_transitions)),
        "rows_ex12_scope_transitions": int(len(scope_transitions)),
        "rows_ex12_hs_revision_diagnostics": int(len(hs_diagnostics)),
        "rows_ex12_hs_harmonization_diagnostics": int(len(hs_harmonization_diagnostics)),
        "partner_code_0_rows": counts["partner_code_0_rows"],
        "product_dependent_hs6_999999_rows": counts["product_dependent_hs6_999999_rows"],
    }
    shutil.rmtree(spill_dir, ignore_errors=True)
    return main_decomposition, stats


def finalize_exercise_12_from_duckdb(con, source_details: dict, rewrite_export_aggregate: bool = True) -> tuple[pd.DataFrame, dict]:
    aggregate_rows = (
        write_exercise_12_export_aggregate(con)
        if rewrite_export_aggregate
        else int(con.execute("SELECT COUNT(*) FROM grouped_aggregates WHERE flow = 'Exports'").fetchone()[0])
    )
    reporter_codes = [
        int(row[0])
        for row in con.execute(
            "SELECT DISTINCT reporter_code FROM grouped_aggregates WHERE flow = 'Exports' ORDER BY reporter_code"
        ).fetchall()
    ]
    horizons = (5, 10)
    spill_dir = EX12_AGGREGATE_PARQUET.parent / "exercise_12_finalize_spill"
    if spill_dir.exists():
        shutil.rmtree(spill_dir)
    spill_paths: dict[str, list[Path]] = {
        "net": [],
        "gross": [],
        "size_transition": [],
        "hs_revision_diagnostics": [],
        "hs_harmonization_diagnostics": [],
        "scope_transition": [],
    }
    cpa_mapping = load_btige_cpa_mapping()
    scope_states_path = EX12_TABLES / "product_destination_region_states.csv"
    if scope_states_path.exists():
        scope_states_path.unlink()
    scope_header_written = False

    for idx, reporter_code in enumerate(reporter_codes, start=1):
        print(f"finalizing Exercise 12 reporter {idx}/{len(reporter_codes)}: {reporter_code}", flush=True)
        for dimension in DIMENSIONS:
            dimension_values = read_dimension_values_for_reporter(con, reporter_code, dimension)
            if dimension_values.empty:
                continue
            spill_exercise_12_chunks_for_values(
                dimension_values,
                dimension,
                reporter_code,
                horizons,
                cpa_mapping,
                spill_paths,
                spill_dir,
            )
            del dimension_values
            gc.collect()

        product_partner = read_dimension_values_for_reporter(con, reporter_code, "product_partner_cell")
        if not product_partner.empty:
            scope = product_scope_states(product_partner)
            if not scope.empty:
                scope.to_csv(scope_states_path, mode="a", header=not scope_header_written, index=False)
                scope_header_written = True
                scope_item_cols = ["product_identity"] if "product_identity" in scope.columns else ["cmd_code"]
                for state_col in ["destination_state", "region_state"]:
                    scope_transition = transition_matrix(scope, scope_item_cols, state_col, horizons)
                    if not scope_transition.empty:
                        spill_exercise_12_frame(scope_transition, spill_paths, spill_dir, "scope_transition", reporter_code, state_col)
                    del scope_transition
            del scope
        del product_partner
        gc.collect()

    decomposition = read_spilled_exercise_12_frames(spill_paths["net"])
    gross_decomposition = read_spilled_exercise_12_frames(spill_paths["gross"])
    hs_diagnostics = read_spilled_exercise_12_frames(spill_paths["hs_revision_diagnostics"])
    hs_harmonization_diagnostics = read_spilled_exercise_12_frames(spill_paths["hs_harmonization_diagnostics"])
    if not decomposition.empty:
        decomposition = add_country_metadata(decomposition)
    if not gross_decomposition.empty:
        gross_decomposition = add_country_metadata(gross_decomposition)
    if not hs_diagnostics.empty:
        hs_diagnostics = add_country_metadata(hs_diagnostics)
    main_decomposition = exercise_12_headline_decomposition(decomposition) if not decomposition.empty else decomposition
    decomposition.to_csv(EX12_TABLES / "growth_decomposition_net.csv", index=False)
    gross_decomposition.to_csv(EX12_TABLES / "growth_decomposition_gross.csv", index=False)
    hs_diagnostics.to_csv(EX12_TABLES / "hs_revision_pair_diagnostics.csv", index=False)
    hs_harmonization_diagnostics.to_csv(EX12_TABLES / "hs_harmonization_diagnostics.csv", index=False)
    main_decomposition.to_parquet(EX12_DECOMPOSITION_PARQUET, index=False)
    main_decomposition.to_csv(EX12_TABLES / "growth_decomposition.csv", index=False)

    size_transitions = (
        read_spilled_exercise_12_frames(spill_paths["size_transition"])
        if spill_paths["size_transition"]
        else pd.DataFrame(columns=["base_state", "future_state", "item_count", "horizon", "transition_type"])
    )
    if not size_transitions.empty:
        size_transitions = add_country_metadata(size_transitions)
    size_transitions.to_csv(EX12_TABLES / "transition_matrices_detailed.csv", index=False)
    size_transitions.to_csv(EX12_TABLES / "size_transition_matrices.csv", index=False)

    scope_transitions = (
        read_spilled_exercise_12_frames(spill_paths["scope_transition"])
        if spill_paths["scope_transition"]
        else pd.DataFrame(columns=["base_state", "future_state", "size", "horizon", "transition_type"])
    )
    scope_transitions = scope_transitions.groupby(
        ["base_state", "future_state", "horizon", "transition_type"], as_index=False
    )["size"].sum()
    scope_transitions.to_csv(EX12_TABLES / "product_scope_transition_matrices.csv", index=False)

    make_exercise_12_figures(main_decomposition, size_transitions, scope_transitions)
    write_exercise_12_memo(
        main_decomposition,
        size_transitions,
        scope_transitions,
        source_details,
        gross_decomposition=gross_decomposition,
        hs_diagnostics=hs_diagnostics,
        hs_harmonization_diagnostics=hs_harmonization_diagnostics,
    )
    stats = {
        "rows_ex12_export_aggregates": aggregate_rows,
        "rows_ex12_decomposition": int(len(main_decomposition)),
        "rows_ex12_decomposition_net_all": int(len(decomposition)),
        "rows_ex12_decomposition_gross": int(len(gross_decomposition)),
        "rows_ex12_size_transitions": int(len(size_transitions)),
        "rows_ex12_scope_transitions": int(len(scope_transitions)),
        "rows_ex12_hs_revision_diagnostics": int(len(hs_diagnostics)),
        "rows_ex12_hs_harmonization_diagnostics": int(len(hs_harmonization_diagnostics)),
        "partner_code_0_rows": int(
            con.execute("SELECT COUNT(*) FROM grouped_aggregates WHERE flow = 'Exports' AND partner_code = 0").fetchone()[0]
        ),
    }
    shutil.rmtree(spill_dir, ignore_errors=True)
    return main_decomposition, stats


def finalize_from_partials(
    partials: list[Path],
    workers: int,
    source_details: dict,
    memory_limit_gb: float | None = None,
    exercise_12_only: bool = False,
    reuse_exercise_12_aggregate: bool = False,
    resume_exercise_12_spill: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    if reuse_exercise_12_aggregate and exercise_12_only:
        ex12_decomposition, ex12_stats = finalize_exercise_12_from_existing_aggregate(
            source_details,
            resume_spill=resume_exercise_12_spill,
        )
        return pd.DataFrame(), ex12_decomposition, ex12_stats

    duckdb = import_duckdb()
    con = duckdb.connect()
    try:
        configure_duckdb_limits(con, workers, memory_limit_gb=memory_limit_gb)
        if reuse_exercise_12_aggregate:
            create_grouped_view_from_ex12_aggregate(con)
        else:
            create_grouped_view(con, partials)
        if exercise_12_only:
            ex02_growth = pd.DataFrame()
        else:
            ex02_panel = build_exercise_02_panel_from_duckdb(con)
            ex02_growth = run_exercise_02_from_panel(ex02_panel, source_details=source_details)
        ex12_decomposition, ex12_stats = finalize_exercise_12_from_duckdb(
            con,
            source_details,
            rewrite_export_aggregate=not reuse_exercise_12_aggregate,
        )
        return ex02_growth, ex12_decomposition, ex12_stats
    finally:
        con.close()


def grouped_aggregate_from_duckdb(partials: list[Path], workers: int) -> pd.DataFrame:
    duckdb = import_duckdb()
    con = duckdb.connect()
    try:
        configure_duckdb_limits(con, workers)
        create_grouped_view(con, partials)
        return con.execute(
            """
            SELECT *
            FROM grouped_aggregates
            ORDER BY reporter_code, year, flow, dimension, cmd_code, partner_code, hs2
            """
        ).df()
    finally:
        con.close()


def legacy_aggregate_for_files(files: list[Path]) -> tuple[pd.DataFrame, pd.DataFrame]:
    aggregate_frames = []
    ex02_panels = []
    for idx, path in enumerate(files, start=1):
        print(f"[{idx}/{len(files)}] legacy validation from {path.name}", flush=True)
        leaf = extract_leaf_trade(read_comtrade_file(path))
        if leaf.empty:
            continue
        aggregate_frames.append(aggregate_leaf_for_exercises_02_12(leaf))
        panel = exercise_02_panel_rows_for_leaf(leaf)
        if not panel.empty:
            ex02_panels.append(panel)

    aggregate = (
        pd.concat(aggregate_frames, ignore_index=True)
        if aggregate_frames
        else empty_aggregate_frame()
    )
    if not aggregate.empty:
        aggregate = (
            aggregate.groupby(PARTIAL_COLUMNS[:-1], dropna=False, as_index=False)["trade_value"]
            .sum()
            .sort_values(PARTIAL_COLUMNS[:-1])
            .reset_index(drop=True)
        )
    panel = pd.concat(ex02_panels, ignore_index=True) if ex02_panels else pd.DataFrame()
    return standardize_aggregate_frame(aggregate), panel


def normalize_for_compare(df: pd.DataFrame) -> pd.DataFrame:
    out = standardize_aggregate_frame(df)
    for col in ["flow", "dimension", "cmd_code", "hs2"]:
        out[col] = out[col].astype("string").fillna("<NA>")
    out["partner_code"] = out["partner_code"].astype("Int64")
    return out.sort_values(PARTIAL_COLUMNS[:-1]).reset_index(drop=True)


def compare_aggregates(optimized: pd.DataFrame, legacy: pd.DataFrame) -> dict:
    opt = normalize_for_compare(optimized)
    old = normalize_for_compare(legacy)
    keys = PARTIAL_COLUMNS[:-1]
    merged = opt.merge(old, on=keys, how="outer", suffixes=("_optimized", "_legacy"), indicator=True)
    missing = merged[merged["_merge"] != "both"]
    if not missing.empty:
        raise RuntimeError(f"Aggregate key mismatch in {len(missing)} rows during validation.")
    diff = (merged["trade_value_optimized"] - merged["trade_value_legacy"]).abs()
    max_abs_diff = float(diff.max()) if len(diff) else 0.0
    if max_abs_diff > 1e-6:
        raise RuntimeError(f"Aggregate value mismatch during validation; max_abs_diff={max_abs_diff}.")
    return {
        "aggregate_rows": int(len(merged)),
        "aggregate_max_abs_diff": max_abs_diff,
    }


def compare_ex02_panels(optimized: pd.DataFrame, legacy: pd.DataFrame) -> dict:
    if optimized.empty or legacy.empty:
        if len(optimized) != len(legacy):
            raise RuntimeError("Exercise 2 validation panel emptiness mismatch.")
        return {"ex02_panel_rows": int(len(optimized)), "ex02_panel_max_abs_diff": 0.0}

    key_cols = ["reporter_code", "year", "flow"]
    metric_cols = [
        col
        for col in optimized.columns
        if col in legacy.columns and (col.endswith("_share") or col.endswith("_gini") or col.endswith("_count") or col == "total_exports")
    ]
    opt = optimized[key_cols + metric_cols].sort_values(key_cols).reset_index(drop=True)
    old = legacy[key_cols + metric_cols].sort_values(key_cols).reset_index(drop=True)
    merged = opt.merge(old, on=key_cols, how="outer", suffixes=("_optimized", "_legacy"), indicator=True)
    missing = merged[merged["_merge"] != "both"]
    if not missing.empty:
        raise RuntimeError(f"Exercise 2 panel key mismatch in {len(missing)} rows during validation.")
    max_abs_diff = 0.0
    for col in metric_cols:
        diff = (merged[f"{col}_optimized"] - merged[f"{col}_legacy"]).abs()
        if len(diff):
            max_abs_diff = max(max_abs_diff, float(diff.max()))
    if max_abs_diff > 1e-6:
        raise RuntimeError(f"Exercise 2 panel mismatch during validation; max_abs_diff={max_abs_diff}.")
    return {
        "ex02_panel_rows": int(len(merged)),
        "ex02_panel_max_abs_diff": max_abs_diff,
    }


def validate_against_legacy(max_files: int, workers: int, chunk_rows: int) -> None:
    ensure_dirs()
    save_country_panel()
    files = hs_bulk_files(max_files=max_files)
    if not files:
        raise FileNotFoundError("No HS Comtrade bulk files found.")
    partials, partial_stats = write_partials(files, workers=workers, fresh=False, chunk_rows=chunk_rows)
    optimized_aggregate = grouped_aggregate_from_duckdb(partials, workers=workers)
    legacy_aggregate, legacy_ex02_panel = legacy_aggregate_for_files(files)
    aggregate_stats = compare_aggregates(optimized_aggregate, legacy_aggregate)

    duckdb = import_duckdb()
    con = duckdb.connect()
    try:
        configure_duckdb_limits(con, workers)
        create_grouped_view(con, partials)
        optimized_ex02_panel = build_exercise_02_panel_from_duckdb(con)
    finally:
        con.close()
    ex02_stats = compare_ex02_panels(optimized_ex02_panel, legacy_ex02_panel)
    manifest = {
        "created_at_utc": now_utc(),
        "mode": "exercises_02_12_validation",
        "status": "passed",
        "max_files": max_files,
        "workers": workers,
        "chunk_rows": int(chunk_rows),
        "dependency_engine": "duckdb",
        "canonical_outputs_written": False,
        **partial_stats,
        **aggregate_stats,
        **ex02_stats,
        "exercises_md_updated": False,
    }
    write_json(RESULTS / "run_manifest_exercises_02_12_validation.json", manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True), flush=True)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Exercises 2 and 12 from resumable per-file aggregate checkpoints.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("legacy_max_files", nargs="?", type=int, help="Backward-compatible alias for --max-files.")
    parser.add_argument("--max-files", type=int, default=None)
    parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    parser.add_argument("--chunk-rows", type=int, default=DEFAULT_CHUNK_ROWS, help="Raw CSV rows per chunk for per-file checkpoint aggregation.")
    parser.add_argument("--fresh", action="store_true", help="Delete only the Exercise 2+12 aggregate cache first.")
    parser.add_argument("--finalize-only", action="store_true", help="Skip raw parsing and finalize from existing checkpoints.")
    parser.add_argument("--validate-against-legacy", type=int, default=None)
    parser.add_argument("--country-sample", choices=COUNTRY_SAMPLE_CHOICES, default="rd2_countries")
    parser.add_argument("--min-available-years", type=int, default=10)
    parser.add_argument("--start-year", type=int, default=1988)
    parser.add_argument("--end-year", type=int, default=None)
    parser.add_argument("--refresh-availability", action="store_true")
    parser.add_argument("--memory-limit-gb", type=float, default=None, help="Optional process memory cap to prevent laptop-wide memory exhaustion.")
    parser.add_argument("--memory-reserve-gb", type=float, default=None, help="Exit if macOS available memory falls below this reserve.")
    parser.add_argument("--exercise-12-only", action="store_true", help="Finalize only Exercise 12 from the combined checkpoints.")
    parser.add_argument(
        "--reuse-exercise-12-aggregate",
        action="store_true",
        help="Finalize from the existing Exercise 12 export aggregate parquet instead of rewriting it from checkpoints.",
    )
    parser.add_argument(
        "--resume-exercise-12-spill",
        action="store_true",
        help="Preserve existing Exercise 12 finalize spill files and rebuild only missing or partial reporter outputs.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    max_files = args.max_files if args.max_files is not None else args.legacy_max_files
    workers = max(1, int(args.workers))
    if args.memory_reserve_gb is not None:
        apply_dynamic_memory_guard(reserve_gb=args.memory_reserve_gb, max_process_gb=args.memory_limit_gb)
    else:
        apply_memory_limit(args.memory_limit_gb)
    configure_runner_sample(args)

    if args.validate_against_legacy is not None:
        validate_against_legacy(max_files=int(args.validate_against_legacy), workers=workers, chunk_rows=args.chunk_rows)
        return 0

    ensure_dirs()
    save_country_panel()
    start = time.time()
    if args.finalize_only:
        partials = sorted(PARTIAL_DIR.glob("*.parquet"))
        if max_files is not None:
            partials = partials[:max_files]
        partial_stats = {
            "raw_files_seen": len(partials),
            "partials_existing": len(partials),
            "partials_written": 0,
            "aggregate_rows_written": 0,
            "leaf_rows_processed": 0,
            "manifest_tail": [],
        }
    else:
        files = hs_bulk_files(max_files=max_files)
        if not files:
            raise FileNotFoundError("No HS Comtrade bulk files found.")
        partials, partial_stats = write_partials(files, workers=workers, fresh=args.fresh, chunk_rows=args.chunk_rows)

    if not partials:
        raise RuntimeError(f"No Exercise 2+12 aggregate partial files found in {PARTIAL_DIR}.")

    debug_run = max_files is not None
    source_details = {
        "mode": "exercises_02_12_duckdb_checkpointed",
        "dependency_engine": "duckdb",
        "country_sample": args.country_sample,
        "partial_dir": str(PARTIAL_DIR.relative_to(RESULTS.parent)),
        "partial_files_used": len(partials),
        "workers": workers,
        "chunk_rows": int(args.chunk_rows),
        "memory_limit_gb": args.memory_limit_gb,
        "memory_reserve_gb": args.memory_reserve_gb,
        "max_files": max_files,
        "debug_run": debug_run,
        "fresh": args.fresh,
        "finalize_only": args.finalize_only,
        "exercise_12_only": args.exercise_12_only,
        "reuse_exercise_12_aggregate": args.reuse_exercise_12_aggregate,
        "resume_exercise_12_spill": args.resume_exercise_12_spill,
    }
    ex02_growth, ex12_decomposition, ex12_stats = finalize_from_partials(
        partials,
        workers=workers,
        source_details=source_details,
        memory_limit_gb=args.memory_limit_gb,
        exercise_12_only=args.exercise_12_only,
        reuse_exercise_12_aggregate=args.reuse_exercise_12_aggregate,
        resume_exercise_12_spill=args.resume_exercise_12_spill,
    )
    manifest = {
        "created_at_utc": now_utc(),
        "command": " ".join([Path(sys.executable).name, *sys.argv]),
        "mode": "exercises_02_12_duckdb_checkpointed",
        "dependency_engine": "duckdb",
        "country_sample": args.country_sample,
        "product_excluded_hs6_codes": ["999999"],
        "partner_concentration_includes_hs6_codes": ["999999"],
        "hs6_999999_rows": {
            "product_and_product_partner_partial_checkpoints": 0,
            "product_and_product_partner_exercise_12_export_aggregates": 0,
            "product_and_product_partner_exercise_12_growth_decomposition": 0,
            "partner_dimension": "included in partner totals before partner aggregation",
        },
        "workers": workers,
        "debug_run": debug_run,
        "finalize_only": args.finalize_only,
        "exercise_12_only": args.exercise_12_only,
        "reuse_exercise_12_aggregate": args.reuse_exercise_12_aggregate,
        "resume_exercise_12_spill": args.resume_exercise_12_spill,
        "canonical_outputs_written": True,
        "runtime_seconds": round(time.time() - start, 3),
        **partial_stats,
        "partial_files_used": len(partials),
        "rows_ex02_growth": int(len(ex02_growth)),
        **ex12_stats,
        "strict_exercise_10_preserved": True,
        "exercises_md_updated": False,
        "processed_outputs": {
            "exercise_02": str(sample_processed_path("exercise_02_bucket_growth_panel.parquet").relative_to(RESULTS.parent)),
            "exercise_12": str(EX12_DECOMPOSITION_PARQUET.relative_to(RESULTS.parent)),
        },
    }
    write_json(RESULTS / "run_manifest_exercises_02_12.json", manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
