#!/usr/bin/env python3
"""Recompute Exercise 6 from existing HS6 product-partner checkpoints.

This avoids rereading all raw Comtrade files when the checkpointed
`exercise_02_12_file_aggregates` directory already contains product-partner
cell values for every raw file.
"""

from __future__ import annotations

import traceback
from pathlib import Path

import pandas as pd

from trade_concentration_pipeline import (
    DATA_PROCESSED,
    EX06_TABLES,
    RESULTS,
    checkpoint_name_for_raw,
    compute_exercise_06_outputs_for_leaf,
    hs_bulk_files,
    make_exercise_06_figures,
    now_utc,
    save_country_panel,
    write_exercise_06_memo,
    write_json,
    write_text,
)


PARTIAL_DIR = DATA_PROCESSED / "exercise_02_12_file_aggregates"


def write_parquet_best_effort(df: pd.DataFrame, path: Path) -> None:
    try:
        df.to_parquet(path, index=False)
    except Exception as exc:
        error_path = path.with_suffix(path.suffix + ".error.txt")
        write_text(
            error_path,
            "Parquet write skipped because the local pyarrow/pandas stack raised an error.\n\n"
            f"{type(exc).__name__}: {exc}\n\n"
            f"{traceback.format_exc()}",
        )
        print(f"Warning: could not write {path}; wrote {error_path} instead.", flush=True)


def load_leaf_cells(partial: Path) -> pd.DataFrame:
    df = pd.read_parquet(
        partial,
        columns=["reporter_code", "year", "flow", "dimension", "cmd_code", "partner_code", "hs2", "trade_value"],
    )
    df = df[df["dimension"] == "product_partner_cell"].drop(columns=["dimension"]).copy()
    df = df.dropna(subset=["reporter_code", "year", "flow", "cmd_code", "partner_code", "hs2", "trade_value"])
    if df.empty:
        return df
    df["reporter_code"] = df["reporter_code"].astype(int)
    df["year"] = df["year"].astype(int)
    df["partner_code"] = df["partner_code"].astype(int)
    df["cmd_code"] = df["cmd_code"].astype(str)
    df["hs2"] = df["hs2"].astype(str).str.zfill(2).str[:2]
    df["trade_value"] = pd.to_numeric(df["trade_value"], errors="coerce")
    return df[df["trade_value"] > 0].copy()


def main() -> None:
    raw_files = hs_bulk_files()
    expected_partials = [PARTIAL_DIR / checkpoint_name_for_raw(path) for path in raw_files]
    missing = [path for path in expected_partials if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing {len(missing)} checkpoint files under {PARTIAL_DIR}. First: {missing[0]}")

    panel = save_country_panel()
    output_frames: list[pd.DataFrame] = []
    removal_frames: list[pd.DataFrame] = []
    files_with_rows = 0

    for idx, partial in enumerate(expected_partials, start=1):
        print(f"[{idx}/{len(expected_partials)}] Exercise 6 from checkpoint {partial.name}", flush=True)
        leaf = load_leaf_cells(partial)
        if leaf.empty:
            continue
        files_with_rows += 1
        outputs, removed = compute_exercise_06_outputs_for_leaf(leaf, panel)
        output_frames.extend(outputs)
        removal_frames.extend(removed)

    if not output_frames:
        raise RuntimeError("No Exercise 6 rows were produced from checkpoint files.")

    exclusions = pd.concat(output_frames, ignore_index=True)
    EX06_TABLES.mkdir(parents=True, exist_ok=True)
    exclusions.to_csv(EX06_TABLES / "concentration_exclusions_all_years.csv", index=False)
    write_parquet_best_effort(exclusions, DATA_PROCESSED / "concentration_exclusions_all_years.parquet")

    if removal_frames:
        removed = pd.concat(removal_frames, ignore_index=True)
        removed.to_csv(EX06_TABLES / "trade_share_removed_by_category.csv", index=False)

    make_exercise_06_figures(exclusions)
    write_exercise_06_memo(exclusions)
    write_json(
        RESULTS / "run_manifest_exercise_06_from_checkpoints.json",
        {
            "created_at_utc": now_utc(),
            "mode": "exercise_06_from_exercise_02_12_checkpoints",
            "raw_files_seen": len(raw_files),
            "checkpoint_files_seen": len(expected_partials),
            "checkpoint_files_with_rows": files_with_rows,
            "rows_exclusions": int(len(exclusions)),
            "parquet_error_file": str(
                (DATA_PROCESSED / "concentration_exclusions_all_years.parquet.error.txt").relative_to(Path.cwd())
            )
            if (DATA_PROCESSED / "concentration_exclusions_all_years.parquet.error.txt").exists()
            else None,
            "exercises_md_updated": False,
        },
    )


if __name__ == "__main__":
    main()
