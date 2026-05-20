#!/usr/bin/env python3
"""Parallel raw-data rerun for Exercise 6.

This is a narrow helper for rerunning the oil/high-unit-value exclusion test
from raw Comtrade files when checkpoint shortcuts do not contain both flows.
"""

from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from trade_concentration_pipeline import (  # noqa: E402
    DATA_PROCESSED,
    EX06_TABLES,
    RESULTS,
    compute_exercise_06_outputs_for_leaf,
    ensure_dirs,
    extract_leaf_trade,
    hs_bulk_files,
    make_exercise_06_figures,
    now_utc,
    read_comtrade_file,
    save_country_panel,
    write_exercise_06_memo,
    write_json,
)


def process_file(path_text: str) -> tuple[str, int, list[pd.DataFrame], list[pd.DataFrame]]:
    path = Path(path_text)
    raw = read_comtrade_file(path)
    leaf = extract_leaf_trade(raw)
    if leaf.empty:
        return path.name, 0, [], []
    panel = save_country_panel()
    outputs, removed = compute_exercise_06_outputs_for_leaf(leaf, panel)
    return path.name, len(leaf), outputs, removed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parallel raw Comtrade rerun for Exercise 6.")
    parser.add_argument("--workers", type=int, default=min(6, os.cpu_count() or 1))
    parser.add_argument("--max-files", type=int, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ensure_dirs()
    files = hs_bulk_files(args.max_files)
    if not files:
        raise FileNotFoundError("No HS Comtrade bulk files found.")

    ex06_outputs: list[pd.DataFrame] = []
    ex06_removed: list[pd.DataFrame] = []
    files_with_rows = 0

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_file, str(path)): path for path in files}
        completed = 0
        for future in as_completed(futures):
            completed += 1
            path = futures[future]
            name, leaf_rows, outputs, removed = future.result()
            print(f"[{completed}/{len(files)}] Exercise 6 raw parallel: {name}", flush=True)
            if leaf_rows <= 0:
                continue
            files_with_rows += 1
            ex06_outputs.extend(outputs)
            ex06_removed.extend(removed)

    if not ex06_outputs:
        raise RuntimeError("No Exercise 6 rows were produced from HS bulk files.")

    exclusions = pd.concat(ex06_outputs, ignore_index=True)
    exclusions.to_csv(EX06_TABLES / "concentration_exclusions_all_years.csv", index=False)
    parquet_error = None
    try:
        exclusions.to_parquet(DATA_PROCESSED / "concentration_exclusions_all_years.parquet", index=False)
    except Exception as exc:
        parquet_error = f"{type(exc).__name__}: {exc}"
        (DATA_PROCESSED / "concentration_exclusions_all_years.parquet.error.txt").write_text(
            parquet_error + "\n",
            encoding="utf-8",
        )

    if ex06_removed:
        removed = pd.concat(ex06_removed, ignore_index=True)
        removed.to_csv(EX06_TABLES / "trade_share_removed_by_category.csv", index=False)

    make_exercise_06_figures(exclusions)
    write_exercise_06_memo(exclusions)
    write_json(
        RESULTS / "run_manifest_exercise_06_raw_parallel.json",
        {
            "created_at_utc": now_utc(),
            "mode": "exercise_06_raw_parallel",
            "workers": args.workers,
            "hs_bulk_files_seen": len(files),
            "hs_bulk_files_with_rows": files_with_rows,
            "rows_exclusions": int(len(exclusions)),
            "parquet_error": parquet_error,
            "exercises_md_updated": False,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
