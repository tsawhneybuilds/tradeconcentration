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
import json
import os
import re
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from trade_concentration_pipeline import (
    DATA_PROCESSED,
    EX12_FIGURES,
    EX12_TABLES,
    RESULTS,
    add_country_metadata,
    assign_size_states,
    attach_inferred_classification_code,
    configure_country_sample,
    drop_excluded_hs6,
    ensure_dirs,
    exercise_12_accounting_outputs_for_values,
    exercise_02_panel_rows_for_leaf,
    extract_leaf_trade,
    growth_decomposition,
    hs_bulk_files,
    item_columns_for_dimension,
    load_btige_cpa_mapping,
    make_exercise_12_figures,
    merge_metric_tables,
    now_utc,
    normalize_columns,
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


def read_leaf_trade_fast(path: Path) -> pd.DataFrame:
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
    return drop_excluded_hs6(out)


def aggregate_leaf_for_exercises_02_12(leaf: pd.DataFrame) -> pd.DataFrame:
    if leaf.empty:
        return empty_aggregate_frame()
    leaf = leaf[leaf["flow"] == "Exports"].copy()
    leaf = drop_excluded_hs6(leaf)
    if leaf.empty:
        return empty_aggregate_frame()

    frames = []
    if "classification_code" not in leaf.columns:
        leaf["classification_code"] = ""
    leaf["classification_code"] = leaf["classification_code"].astype(str).str.strip().str.upper()

    product = leaf.groupby(["reporter_code", "year", "flow", "classification_code", "cmd_code", "hs2"], as_index=False)["trade_value"].sum()
    product["dimension"] = "product"
    product["partner_code"] = pd.NA
    frames.append(product)

    partner = leaf.groupby(["reporter_code", "year", "flow", "partner_code"], as_index=False)["trade_value"].sum()
    partner["dimension"] = "partner"
    partner["classification_code"] = ""
    partner["cmd_code"] = pd.NA
    partner["hs2"] = pd.NA
    frames.append(partner)

    cell = leaf.groupby(["reporter_code", "year", "flow", "classification_code", "cmd_code", "partner_code", "hs2"], as_index=False)[
        "trade_value"
    ].sum()
    cell["dimension"] = "product_partner_cell"
    frames.append(cell)

    return standardize_aggregate_frame(pd.concat(frames, ignore_index=True))


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


def write_one_partial(raw_path_text: str, partial_path_text: str) -> dict:
    raw_path = Path(raw_path_text)
    partial_path = Path(partial_path_text)
    partial_path.parent.mkdir(parents=True, exist_ok=True)

    leaf = read_leaf_trade_fast(raw_path)
    aggregate = aggregate_leaf_for_exercises_02_12(leaf)
    tmp_path = partial_path.with_suffix(partial_path.suffix + ".tmp")
    aggregate.to_parquet(tmp_path, index=False)
    tmp_path.replace(partial_path)
    return {
        "raw_file": raw_path.name,
        "partial_file": partial_path.name,
        "status": "written",
        "leaf_rows": int(len(leaf)),
        "aggregate_rows": int(len(aggregate)),
    }


def write_partials(files: list[Path], workers: int, fresh: bool) -> tuple[list[Path], dict]:
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
            row = write_one_partial(str(raw), str(partial))
            stats["partials_written"] += 1
            stats["aggregate_rows_written"] += row["aggregate_rows"]
            stats["leaf_rows_processed"] += row["leaf_rows"]
            stats["manifest_tail"] = [*stats["manifest_tail"], row][-25:]
    else:
        with ProcessPoolExecutor(max_workers=max(1, workers)) as executor:
            futures = {executor.submit(write_one_partial, str(raw), str(partial)): raw for raw, partial in pending}
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
            "partial_dir": str(PARTIAL_DIR.relative_to(RESULTS.parent)),
            "workers": workers,
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
          AND (cmd_code IS NULL OR CAST(cmd_code AS VARCHAR) <> '999999')
        GROUP BY 1, 2, 3, 4, 5, 6, 7, 8
        """
    )


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


def finalize_exercise_12_from_duckdb(con, source_details: dict) -> tuple[pd.DataFrame, dict]:
    aggregate_rows = write_exercise_12_export_aggregate(con)
    reporter_codes = [
        int(row[0])
        for row in con.execute(
            "SELECT DISTINCT reporter_code FROM grouped_aggregates WHERE flow = 'Exports' ORDER BY reporter_code"
        ).fetchall()
    ]
    horizons = (5, 10)
    net_rows = []
    gross_rows = []
    size_transition_rows = []
    diagnostic_rows = []
    scope_transition_rows = []
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
            net, gross, transitions, diagnostics = exercise_12_accounting_outputs_for_values(
                dimension_values,
                dimension,
                horizons,
                cpa_mapping=cpa_mapping,
            )
            if not net.empty:
                net_rows.append(net)
            if not gross.empty:
                gross_rows.append(gross)
            if not transitions.empty:
                size_transition_rows.append(transitions)
            if not diagnostics.empty:
                diagnostic_rows.append(diagnostics)

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
                        scope_transition_rows.append(scope_transition)

    decomposition = pd.concat(net_rows, ignore_index=True) if net_rows else pd.DataFrame()
    gross_decomposition = pd.concat(gross_rows, ignore_index=True) if gross_rows else pd.DataFrame()
    hs_diagnostics = pd.concat(diagnostic_rows, ignore_index=True) if diagnostic_rows else pd.DataFrame()
    if not decomposition.empty:
        decomposition = add_country_metadata(decomposition)
    if not gross_decomposition.empty:
        gross_decomposition = add_country_metadata(gross_decomposition)
    if not hs_diagnostics.empty:
        hs_diagnostics = add_country_metadata(hs_diagnostics)
    main_decomposition = (
        decomposition[
            (decomposition["top_definition"] == "top_10")
            & (decomposition["item_id_mode"].isin(["hs6_revision", "partner"]))
        ].copy()
        if not decomposition.empty
        else decomposition
    )
    decomposition.to_csv(EX12_TABLES / "growth_decomposition_net.csv", index=False)
    gross_decomposition.to_csv(EX12_TABLES / "growth_decomposition_gross.csv", index=False)
    hs_diagnostics.to_csv(EX12_TABLES / "hs_revision_pair_diagnostics.csv", index=False)
    main_decomposition.to_parquet(EX12_DECOMPOSITION_PARQUET, index=False)
    main_decomposition.to_csv(EX12_TABLES / "growth_decomposition.csv", index=False)

    size_transitions = (
        pd.concat(size_transition_rows, ignore_index=True)
        if size_transition_rows
        else pd.DataFrame(columns=["base_state", "future_state", "item_count", "horizon", "transition_type"])
    )
    if not size_transitions.empty:
        size_transitions = add_country_metadata(size_transitions)
    size_transitions.to_csv(EX12_TABLES / "transition_matrices_detailed.csv", index=False)
    size_transitions.to_csv(EX12_TABLES / "size_transition_matrices.csv", index=False)

    scope_transitions = (
        pd.concat(scope_transition_rows, ignore_index=True)
        if scope_transition_rows
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
    )
    stats = {
        "rows_ex12_export_aggregates": aggregate_rows,
        "rows_ex12_decomposition": int(len(main_decomposition)),
        "rows_ex12_decomposition_net_all": int(len(decomposition)),
        "rows_ex12_decomposition_gross": int(len(gross_decomposition)),
        "rows_ex12_size_transitions": int(len(size_transitions)),
        "rows_ex12_scope_transitions": int(len(scope_transitions)),
        "rows_ex12_hs_revision_diagnostics": int(len(hs_diagnostics)),
    }
    return main_decomposition, stats


def finalize_from_partials(partials: list[Path], workers: int, source_details: dict) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    duckdb = import_duckdb()
    con = duckdb.connect()
    try:
        con.execute(f"SET threads TO {max(1, workers)}")
        create_grouped_view(con, partials)
        ex02_panel = build_exercise_02_panel_from_duckdb(con)
        ex02_growth = run_exercise_02_from_panel(ex02_panel, source_details=source_details)
        ex12_decomposition, ex12_stats = finalize_exercise_12_from_duckdb(con, source_details)
        return ex02_growth, ex12_decomposition, ex12_stats
    finally:
        con.close()


def grouped_aggregate_from_duckdb(partials: list[Path], workers: int) -> pd.DataFrame:
    duckdb = import_duckdb()
    con = duckdb.connect()
    try:
        con.execute(f"SET threads TO {max(1, workers)}")
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


def validate_against_legacy(max_files: int, workers: int) -> None:
    ensure_dirs()
    save_country_panel()
    files = hs_bulk_files(max_files=max_files)
    if not files:
        raise FileNotFoundError("No HS Comtrade bulk files found.")
    partials, partial_stats = write_partials(files, workers=workers, fresh=False)
    optimized_aggregate = grouped_aggregate_from_duckdb(partials, workers=workers)
    legacy_aggregate, legacy_ex02_panel = legacy_aggregate_for_files(files)
    aggregate_stats = compare_aggregates(optimized_aggregate, legacy_aggregate)

    duckdb = import_duckdb()
    con = duckdb.connect()
    try:
        con.execute(f"SET threads TO {max(1, workers)}")
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
    parser.add_argument("--fresh", action="store_true", help="Delete only the Exercise 2+12 aggregate cache first.")
    parser.add_argument("--finalize-only", action="store_true", help="Skip raw parsing and finalize from existing checkpoints.")
    parser.add_argument("--validate-against-legacy", type=int, default=None)
    parser.add_argument("--country-sample", choices=["prof_p_33", "world_broad"], default="prof_p_33")
    parser.add_argument("--min-available-years", type=int, default=10)
    parser.add_argument("--start-year", type=int, default=1988)
    parser.add_argument("--end-year", type=int, default=None)
    parser.add_argument("--refresh-availability", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    max_files = args.max_files if args.max_files is not None else args.legacy_max_files
    workers = max(1, int(args.workers))
    configure_runner_sample(args)

    if args.validate_against_legacy is not None:
        validate_against_legacy(max_files=int(args.validate_against_legacy), workers=workers)
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
        partials, partial_stats = write_partials(files, workers=workers, fresh=args.fresh)

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
        "max_files": max_files,
        "debug_run": debug_run,
        "fresh": args.fresh,
        "finalize_only": args.finalize_only,
    }
    ex02_growth, ex12_decomposition, ex12_stats = finalize_from_partials(partials, workers=workers, source_details=source_details)
    manifest = {
        "created_at_utc": now_utc(),
        "mode": "exercises_02_12_duckdb_checkpointed",
        "dependency_engine": "duckdb",
        "country_sample": args.country_sample,
        "workers": workers,
        "debug_run": debug_run,
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
