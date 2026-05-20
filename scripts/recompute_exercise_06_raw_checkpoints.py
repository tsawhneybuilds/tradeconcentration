#!/usr/bin/env python3
"""Resumable raw-data rerun for Exercise 6.

Each raw Comtrade file is converted to a small Exercise 6 partial first. The
final tables and memo are then rebuilt from those partials. This keeps the run
restartable if the terminal session drops during a long raw-data pass.
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
    EX06_FIGURES,
    EX06_TABLES,
    RESULTS,
    checkpoint_name_for_raw,
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

PARTIAL_DIR = DATA_PROCESSED / "exercise_06_file_aggregates"
EXCLUSIONS_PARTIAL_DIR = PARTIAL_DIR / "exclusions"
REMOVED_PARTIAL_DIR = PARTIAL_DIR / "removed_categories"
DONE_DIR = PARTIAL_DIR / "done"


def partial_name_for_raw(path: Path) -> str:
    return checkpoint_name_for_raw(path).removesuffix(".parquet") + ".csv"


def atomic_write_csv(df: pd.DataFrame, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_suffix(destination.suffix + f".{os.getpid()}.tmp")
    df.to_csv(tmp, index=False)
    tmp.replace(destination)


def process_file(path_text: str) -> dict:
    path = Path(path_text)
    partial_name = partial_name_for_raw(path)
    out_path = EXCLUSIONS_PARTIAL_DIR / partial_name
    removed_path = REMOVED_PARTIAL_DIR / partial_name
    done_path = DONE_DIR / (partial_name + ".done")

    if done_path.exists() and out_path.exists():
        return {"file": path.name, "status": "skipped", "leaf_rows": None, "rows_exclusions": None}

    raw = read_comtrade_file(path)
    leaf = extract_leaf_trade(raw)
    if leaf.empty:
        done_path.parent.mkdir(parents=True, exist_ok=True)
        done_path.write_text("empty\n", encoding="utf-8")
        return {"file": path.name, "status": "empty", "leaf_rows": 0, "rows_exclusions": 0}

    panel = save_country_panel()
    outputs, removed = compute_exercise_06_outputs_for_leaf(leaf, panel)
    if not outputs:
        done_path.parent.mkdir(parents=True, exist_ok=True)
        done_path.write_text("no_outputs\n", encoding="utf-8")
        return {"file": path.name, "status": "no_outputs", "leaf_rows": int(len(leaf)), "rows_exclusions": 0}

    exclusions = pd.concat(outputs, ignore_index=True)
    atomic_write_csv(exclusions, out_path)

    if removed:
        atomic_write_csv(pd.concat(removed, ignore_index=True), removed_path)
    elif removed_path.exists():
        removed_path.unlink()

    done_path.parent.mkdir(parents=True, exist_ok=True)
    done_path.write_text("done\n", encoding="utf-8")
    return {
        "file": path.name,
        "status": "done",
        "leaf_rows": int(len(leaf)),
        "rows_exclusions": int(len(exclusions)),
    }


def read_partials(paths: list[Path]) -> pd.DataFrame:
    frames = [pd.read_csv(path) for path in paths if path.exists() and path.stat().st_size > 0]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def finalize(files_seen: int, workers: int) -> None:
    exclusion_partials = sorted(EXCLUSIONS_PARTIAL_DIR.glob("*.csv"))
    if not exclusion_partials:
        raise RuntimeError(f"No Exercise 6 exclusion partials found in {EXCLUSIONS_PARTIAL_DIR}")

    exclusions = read_partials(exclusion_partials)
    exclusions.to_csv(EX06_TABLES / "concentration_exclusions_all_years.csv", index=False)

    parquet_error = None
    parquet_error_path = DATA_PROCESSED / "concentration_exclusions_all_years.parquet.error.txt"
    try:
        exclusions.to_parquet(DATA_PROCESSED / "concentration_exclusions_all_years.parquet", index=False)
        if parquet_error_path.exists():
            parquet_error_path.unlink()
    except Exception as exc:
        parquet_error = f"{type(exc).__name__}: {exc}"
        parquet_error_path.write_text(parquet_error + "\n", encoding="utf-8")

    removed = read_partials(sorted(REMOVED_PARTIAL_DIR.glob("*.csv")))
    if not removed.empty:
        removed.to_csv(EX06_TABLES / "trade_share_removed_by_category.csv", index=False)

    EX06_FIGURES.mkdir(parents=True, exist_ok=True)
    make_exercise_06_figures(exclusions)
    write_exercise_06_memo(exclusions)
    write_json(
        RESULTS / "run_manifest_exercise_06_raw_checkpoints.json",
        {
            "created_at_utc": now_utc(),
            "mode": "exercise_06_raw_checkpoints",
            "workers": workers,
            "raw_files_seen": files_seen,
            "partials_exclusions": len(exclusion_partials),
            "done_markers": len(list(DONE_DIR.glob("*.done"))),
            "rows_exclusions": int(len(exclusions)),
            "flows": sorted(exclusions["flow"].dropna().unique().tolist()),
            "variants": sorted(exclusions["variant"].dropna().unique().tolist()),
            "parquet_error": parquet_error,
            "exercises_md_updated": False,
        },
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resumable raw Comtrade rerun for Exercise 6.")
    parser.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument("--max-files", type=int, default=None)
    parser.add_argument("--finalize-only", action="store_true")
    parser.add_argument("--fresh", action="store_true", help="Remove existing Exercise 6 partials before processing.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ensure_dirs()
    for path in [EXCLUSIONS_PARTIAL_DIR, REMOVED_PARTIAL_DIR, DONE_DIR]:
        path.mkdir(parents=True, exist_ok=True)

    files = hs_bulk_files(args.max_files)
    if not files:
        raise FileNotFoundError("No HS Comtrade bulk files found.")

    if args.fresh:
        for path in [*EXCLUSIONS_PARTIAL_DIR.glob("*.csv"), *REMOVED_PARTIAL_DIR.glob("*.csv"), *DONE_DIR.glob("*.done")]:
            path.unlink()

    if not args.finalize_only:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(process_file, str(path)): path for path in files}
            for completed, future in enumerate(as_completed(futures), start=1):
                result = future.result()
                print(
                    f"[{completed}/{len(files)}] Exercise 6 raw checkpoint: "
                    f"{result['file']} ({result['status']})",
                    flush=True,
                )

    finalize(files_seen=len(files), workers=args.workers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
