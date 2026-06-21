#!/usr/bin/env python3
"""Checkpointed full-data runner for Exercise 12.

Exercise 12 needs product, partner, and product-partner export aggregates over
all annual HS files. The regular streaming runner keeps too much intermediate
state in memory for long runs. This version writes one aggregate parquet per
raw Comtrade file and can resume from those checkpoints.
"""

from __future__ import annotations

import argparse
import gc
import json
import re
import shutil
import sys
from pathlib import Path

import pandas as pd

from trade_concentration_pipeline import (
    COUNTRY_SAMPLE_CHOICES,
    DATA_PROCESSED,
    EX12_FIGURES,
    EX12_TABLES,
    RESULTS,
    add_country_metadata,
    active_sample_name,
    assign_size_states,
    configure_country_sample,
    drop_excluded_hs6,
    ensure_dirs,
    exercise_12_accounting_outputs_for_values,
    exercise_12_export_aggregates_for_leaf,
    exercise_12_headline_decomposition,
    extract_leaf_trade,
    hs_bulk_files,
    item_columns_for_dimension,
    load_btige_cpa_mapping,
    make_exercise_12_figures,
    now_utc,
    product_scope_states,
    read_comtrade_file,
    save_country_panel,
    sample_processed_dir,
    sample_results_dir,
    transition_matrix,
    write_exercise_12_memo,
    write_json,
)


BASE_PARTIAL_DIR = DATA_PROCESSED / "exercise_12_file_aggregates"
PARTIAL_DIR = BASE_PARTIAL_DIR
BASE_AGGREGATE_PARQUET = DATA_PROCESSED / "exercise_12_export_aggregates.parquet"
BASE_DECOMPOSITION_PARQUET = DATA_PROCESSED / "exercise_12_growth_decomposition.parquet"
AGGREGATE_PARQUET = BASE_AGGREGATE_PARQUET
DECOMPOSITION_PARQUET = BASE_DECOMPOSITION_PARQUET


def configure_runner_sample(args: argparse.Namespace) -> None:
    configure_country_sample(
        country_sample=args.country_sample,
        min_available_years=args.min_available_years,
        start_year=args.start_year,
        end_year=args.end_year,
        refresh_availability=args.refresh_availability,
    )
    global PARTIAL_DIR
    global AGGREGATE_PARQUET
    global DECOMPOSITION_PARQUET
    global EX12_TABLES
    global EX12_FIGURES
    results_base = sample_results_dir(args.country_sample)
    EX12_TABLES = results_base / "exercise_12_tables"
    EX12_FIGURES = results_base / "exercise_12_figures"
    if args.country_sample == "prof_p_33":
        PARTIAL_DIR = BASE_PARTIAL_DIR
        AGGREGATE_PARQUET = BASE_AGGREGATE_PARQUET
        DECOMPOSITION_PARQUET = BASE_DECOMPOSITION_PARQUET
    else:
        base = sample_processed_dir(args.country_sample)
        PARTIAL_DIR = base / "exercise_12_file_aggregates"
        AGGREGATE_PARQUET = base / "exercise_12_export_aggregates.parquet"
        DECOMPOSITION_PARQUET = base / "exercise_12_growth_decomposition.parquet"


def output_path_for_raw(path: Path) -> Path:
    name = re.sub(r"\.(gz|txt)$", "", path.name)
    return PARTIAL_DIR / f"{name}.parquet"


def reporter_from_name(path: Path) -> int | None:
    match = re.search(r"CA(\d{3})(\d{4})H", path.name)
    return int(match.group(1)) if match else None


def standardize_aggregate_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ["reporter_code", "year", "classification_code", "cmd_code", "partner_code", "trade_value", "dimension"]:
        if col not in out.columns:
            out[col] = pd.NA
    out = out[["reporter_code", "year", "classification_code", "cmd_code", "partner_code", "trade_value", "dimension"]].copy()
    out["reporter_code"] = pd.to_numeric(out["reporter_code"], errors="coerce").astype("Int64")
    out["year"] = pd.to_numeric(out["year"], errors="coerce").astype("Int64")
    out["classification_code"] = out["classification_code"].astype("string").fillna("")
    out["cmd_code"] = out["cmd_code"].astype("string")
    out["partner_code"] = pd.to_numeric(out["partner_code"], errors="coerce").astype("Int64")
    out["trade_value"] = pd.to_numeric(out["trade_value"], errors="coerce")
    out["dimension"] = out["dimension"].astype("string")
    out = out.dropna(subset=["reporter_code", "year", "trade_value", "dimension"])
    out = out[(out["partner_code"].isna()) | (out["partner_code"] != 0)].copy()
    product_dependent = out["dimension"].isin(["product", "product_partner_cell"])
    excluded_code = out["cmd_code"].astype("string").str.extract(r"(\d{1,6})", expand=False).str.zfill(6).eq("999999")
    return out.loc[~(product_dependent & excluded_code)].copy()


def write_partials(max_files: int | None, fresh: bool) -> list[Path]:
    if fresh and PARTIAL_DIR.exists():
        shutil.rmtree(PARTIAL_DIR)
    PARTIAL_DIR.mkdir(parents=True, exist_ok=True)

    files = hs_bulk_files(max_files=max_files)
    if not files:
        raise FileNotFoundError("No HS Comtrade bulk files found.")

    manifest_rows = []
    partials = []
    for idx, path in enumerate(files, start=1):
        partial = output_path_for_raw(path)
        partials.append(partial)
        if partial.exists():
            print(f"[{idx}/{len(files)}] skip existing Exercise 12 aggregate {partial.name}", flush=True)
            manifest_rows.append({"raw_file": path.name, "partial_file": partial.name, "status": "already_exists"})
            continue

        print(f"[{idx}/{len(files)}] aggregate Exercise 12 from {path.name}", flush=True)
        raw = read_comtrade_file(path)
        leaf = extract_leaf_trade(raw)
        frames, _product_partner = exercise_12_export_aggregates_for_leaf(leaf)
        if frames:
            aggregate = standardize_aggregate_frame(pd.concat(frames.values(), ignore_index=True))
        else:
            aggregate = standardize_aggregate_frame(pd.DataFrame())
        aggregate.to_parquet(partial, index=False)
        rows = int(len(aggregate))
        manifest_rows.append(
            {
                "raw_file": path.name,
                "partial_file": partial.name,
                "status": "written",
                "rows": rows,
            }
        )
        del raw, leaf, frames, _product_partner, aggregate
        gc.collect()
        write_json(
            RESULTS / "run_manifest_exercise_12_checkpointed_partials.json",
            {
                "created_at_utc": now_utc(),
                "mode": "exercise_12_checkpointed_partials",
                "country_sample": active_sample_name(),
                "product_excluded_hs6_codes": ["999999"],
                "partner_concentration_includes_hs6_codes": ["999999"],
                "raw_files_seen": len(files),
                "raw_files_attempted": idx,
                "partials_present": len(list(PARTIAL_DIR.glob("*.parquet"))),
                "latest_raw_file": path.name,
                "manifest_tail": manifest_rows[-25:],
                "exercises_md_updated": False,
            },
        )
    return partials


def write_combined_aggregate_parquet(partials: list[Path]) -> int:
    if AGGREGATE_PARQUET.exists():
        AGGREGATE_PARQUET.unlink()

    writer = None
    total_rows = 0
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq

        schema = pa.schema(
            [
                ("reporter_code", pa.int64()),
                ("year", pa.int64()),
                ("classification_code", pa.string()),
                ("cmd_code", pa.string()),
                ("partner_code", pa.int64()),
                ("trade_value", pa.float64()),
                ("dimension", pa.string()),
            ]
        )
        for idx, partial in enumerate(partials, start=1):
            if not partial.exists():
                raise FileNotFoundError(f"Missing Exercise 12 partial: {partial}")
            raw = pd.read_parquet(partial)
            if "classification_code" not in raw.columns:
                raise RuntimeError(
                    f"Exercise 12 partial lacks classification_code and cannot be finalized safely: {partial}. "
                    "Rebuild checkpointed partials with --fresh."
                )
            df = standardize_aggregate_frame(raw)
            total_rows += len(df)
            table = pa.Table.from_pandas(df, schema=schema, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(AGGREGATE_PARQUET, schema=schema)
            writer.write_table(table)
            del df, table
            if idx % 25 == 0:
                gc.collect()
            if idx % 50 == 0 or idx == len(partials):
                print(f"combined {idx}/{len(partials)} Exercise 12 partials", flush=True)
    finally:
        if writer is not None:
            writer.close()
    return total_rows


def read_reporter_values(partials: list[Path], reporter_code: int) -> pd.DataFrame:
    frames = []
    for partial in partials:
        if reporter_from_name(partial) != reporter_code:
            continue
        frame = pd.read_parquet(partial)
        if not frame.empty:
            frames.append(standardize_aggregate_frame(frame))
        del frame
    return pd.concat(frames, ignore_index=True) if frames else standardize_aggregate_frame(pd.DataFrame())


def prepare_dimension_values(values: pd.DataFrame, dimension: str) -> pd.DataFrame:
    item_cols = item_columns_for_dimension(dimension)
    select_item_cols = [*item_cols]
    if dimension in {"product", "product_partner_cell"}:
        select_item_cols = ["classification_code", *select_item_cols]
    cols = ["reporter_code", "year", *select_item_cols, "trade_value"]
    out = values[values["dimension"] == dimension].copy()
    out = out.dropna(subset=item_cols + ["trade_value"])
    for col in ["reporter_code", "year"]:
        out[col] = pd.to_numeric(out[col], errors="coerce").astype(int)
    if "partner_code" in item_cols:
        out["partner_code"] = pd.to_numeric(out["partner_code"], errors="coerce").astype(int)
    if "cmd_code" in out.columns:
        out["cmd_code"] = out["cmd_code"].astype(str)
    if "classification_code" in out.columns:
        out["classification_code"] = out["classification_code"].fillna("").astype(str)
    return out[cols].copy()


def count_partner_code_0_rows(partials: list[Path]) -> int:
    total = 0
    for path in partials:
        if not path.exists():
            continue
        try:
            partner = pd.read_parquet(path, columns=["partner_code"])
        except Exception:
            continue
        total += int((pd.to_numeric(partner["partner_code"], errors="coerce") == 0).sum())
    return total


def finalize(partials: list[Path], source_details: dict) -> None:
    total_aggregate_rows = write_combined_aggregate_parquet(partials)
    reporter_codes = sorted(code for code in {reporter_from_name(path) for path in partials} if code is not None)
    horizons = (5, 10)

    net_rows = []
    gross_rows = []
    size_transition_rows = []
    diagnostic_rows = []
    harmonization_diagnostic_rows = []
    scope_transition_rows = []
    cpa_mapping = load_btige_cpa_mapping()
    scope_states_path = EX12_TABLES / "product_destination_region_states.csv"
    if scope_states_path.exists():
        scope_states_path.unlink()
    scope_header_written = False

    for idx, reporter_code in enumerate(reporter_codes, start=1):
        print(f"finalizing Exercise 12 reporter {idx}/{len(reporter_codes)}: {reporter_code}", flush=True)
        values = read_reporter_values(partials, reporter_code)
        if values.empty:
            del values
            gc.collect()
            continue

        for dimension in ["product", "partner", "product_partner_cell"]:
            dimension_values = prepare_dimension_values(values, dimension)
            if dimension_values.empty:
                del dimension_values
                continue
            net, gross, transitions, diagnostics, harmonization_diagnostics = exercise_12_accounting_outputs_for_values(
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
            if not harmonization_diagnostics.empty:
                harmonization_diagnostic_rows.append(harmonization_diagnostics)
            del net, gross, transitions, diagnostics, harmonization_diagnostics, dimension_values

        product_partner = prepare_dimension_values(values, "product_partner_cell")
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
                    del scope_transition
            del scope
        del values, product_partner
        gc.collect()

    decomposition = pd.concat(net_rows, ignore_index=True) if net_rows else pd.DataFrame()
    gross_decomposition = pd.concat(gross_rows, ignore_index=True) if gross_rows else pd.DataFrame()
    hs_diagnostics = pd.concat(diagnostic_rows, ignore_index=True) if diagnostic_rows else pd.DataFrame()
    hs_harmonization_diagnostics = (
        pd.concat(harmonization_diagnostic_rows, ignore_index=True) if harmonization_diagnostic_rows else pd.DataFrame()
    )
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
    main_decomposition.to_parquet(DECOMPOSITION_PARQUET, index=False)
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
        hs_harmonization_diagnostics=hs_harmonization_diagnostics,
    )
    write_json(
        RESULTS / "run_manifest_exercise_12_checkpointed.json",
        {
            "created_at_utc": now_utc(),
            "mode": "exercise_12_checkpointed",
            "country_sample": source_details.get("country_sample"),
            "product_excluded_hs6_codes": ["999999"],
            "partner_concentration_includes_hs6_codes": ["999999"],
            "hs_bulk_files_processed": len(partials),
            "partial_files": len(list(PARTIAL_DIR.glob("*.parquet"))),
            "combined_aggregate_rows": int(total_aggregate_rows),
            "rows_decomposition": int(len(main_decomposition)),
            "rows_decomposition_net_all": int(len(decomposition)),
            "rows_decomposition_gross": int(len(gross_decomposition)),
            "rows_hs_revision_diagnostics": int(len(hs_diagnostics)),
            "rows_hs_harmonization_diagnostics": int(len(hs_harmonization_diagnostics)),
            "rows_size_transitions": int(len(size_transitions)),
            "rows_scope_transitions": int(len(scope_transitions)),
            "partner_code_0_rows": count_partner_code_0_rows(partials),
            "aggregate_schema": [
                "reporter_code",
                "year",
                "classification_code",
                "cmd_code",
                "partner_code",
                "trade_value",
                "dimension",
            ],
            "exercises_md_updated": False,
        },
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Exercise 12 with per-file checkpoints.")
    parser.add_argument("--max-files", type=int, default=None)
    parser.add_argument("--fresh", action="store_true", help="Delete existing per-file Exercise 12 checkpoints first.")
    parser.add_argument("--finalize-only", action="store_true", help="Skip raw processing and finalize from existing checkpoints.")
    parser.add_argument("--country-sample", choices=COUNTRY_SAMPLE_CHOICES, default="rd2_countries")
    parser.add_argument("--min-available-years", type=int, default=10)
    parser.add_argument("--start-year", type=int, default=1988)
    parser.add_argument("--end-year", type=int, default=None)
    parser.add_argument("--refresh-availability", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    configure_runner_sample(args)
    ensure_dirs()
    save_country_panel()
    PARTIAL_DIR.mkdir(parents=True, exist_ok=True)
    if args.finalize_only:
        partials = sorted(PARTIAL_DIR.glob("*.parquet"))
    else:
        partials = write_partials(max_files=args.max_files, fresh=args.fresh)
    if not partials:
        raise RuntimeError("No Exercise 12 partial aggregate files found.")
    source_details = {
        "mode": "checkpointed",
        "country_sample": args.country_sample,
        "hs_bulk_files_processed": len(partials),
        "partial_dir": str(PARTIAL_DIR.relative_to(RESULTS.parent)),
    }
    finalize(partials, source_details)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
