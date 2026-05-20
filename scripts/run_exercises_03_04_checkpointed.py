#!/usr/bin/env python3
"""Run Exercises 3 and 4 together from raw Comtrade checkpoints.

The main pipeline supports these exercises separately. This wrapper shares the
raw-file pass so Exercise 3 import-bin aggregates and Exercise 4 dominant
supplier aggregates are checkpointed together.
"""

from __future__ import annotations

import argparse
from multiprocessing import get_context
from pathlib import Path

import pyarrow.parquet as pq

from trade_concentration_pipeline import (
    DEFAULT_CHUNK_ROWS,
    EX03_PARTIAL_DIR,
    EX04_PARTIAL_DIR,
    RESULTS,
    apply_memory_limit,
    ensure_dirs,
    exercise_03_partial_paths,
    exercise_04_partial_path,
    finalize_exercise_03_from_partials,
    finalize_exercise_04_from_partials,
    hs_bulk_files,
    load_approved_bec5_mapping,
    now_utc,
    write_exercises_03_04_partials_for_raw,
    write_json,
)


WORKER_MAPPING = None
WORKER_CHUNK_ROWS = DEFAULT_CHUNK_ROWS


def is_readable_parquet(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        pq.ParquetFile(path).metadata
    except Exception:
        path.unlink(missing_ok=True)
        return False
    return True


def complete_ex03_pair(path: Path) -> tuple[Path, Path] | None:
    product_partial, coverage_partial = exercise_03_partial_paths(path)
    if is_readable_parquet(product_partial) and is_readable_parquet(coverage_partial):
        return product_partial, coverage_partial
    return None


def complete_ex04_partial(path: Path) -> Path | None:
    partial = exercise_04_partial_path(path)
    return partial if is_readable_parquet(partial) else None


def init_worker(chunk_rows: int = DEFAULT_CHUNK_ROWS, memory_limit_gb: float | None = None) -> None:
    global WORKER_MAPPING
    global WORKER_CHUNK_ROWS
    apply_memory_limit(memory_limit_gb)
    WORKER_MAPPING = load_approved_bec5_mapping()
    WORKER_CHUNK_ROWS = int(chunk_rows)


def process_one_file(path_text: str) -> tuple[str, str]:
    path = Path(path_text)
    ex03_pair = complete_ex03_pair(path)
    ex04_partial = complete_ex04_partial(path)
    if ex03_pair is not None and ex04_partial is not None:
        return path.name, "skipped"

    if WORKER_MAPPING is None:
        raise RuntimeError("Worker mapping was not initialized.")
    write_exercises_03_04_partials_for_raw(path, WORKER_MAPPING, chunk_rows=WORKER_CHUNK_ROWS)
    return path.name, "processed"


def collect_complete_partials(files: list[Path]) -> tuple[list[Path], list[Path], list[Path]]:
    ex03_product_partials: list[Path] = []
    ex03_coverage_partials: list[Path] = []
    ex04_partials: list[Path] = []
    for path in files:
        ex03_pair = complete_ex03_pair(path)
        ex04_partial = complete_ex04_partial(path)
        if ex03_pair is not None:
            ex03_product_partials.append(ex03_pair[0])
            ex03_coverage_partials.append(ex03_pair[1])
        if ex04_partial is not None:
            ex04_partials.append(ex04_partial)
    return ex03_product_partials, ex03_coverage_partials, ex04_partials


def run(
    max_files: int | None = None,
    fresh: bool = False,
    finalize_only: bool = False,
    workers: int = 1,
    chunk_rows: int = DEFAULT_CHUNK_ROWS,
    memory_limit_gb: float | None = None,
) -> None:
    apply_memory_limit(memory_limit_gb)
    ensure_dirs()
    files = hs_bulk_files(max_files=max_files)
    if not files:
        raise FileNotFoundError("No HS Comtrade bulk files found.")

    if fresh:
        for directory in [EX03_PARTIAL_DIR, EX04_PARTIAL_DIR]:
            for partial in directory.glob("*.parquet"):
                partial.unlink()

    ex03_product_partials: list[Path] = []
    ex03_coverage_partials: list[Path] = []
    ex04_partials: list[Path] = []

    if finalize_only:
        ex03_product_partials, ex03_coverage_partials, ex04_partials = collect_complete_partials(files)
    else:
        if workers > 1:
            ctx = get_context("spawn")
            with ctx.Pool(processes=workers, initializer=init_worker, initargs=(chunk_rows, memory_limit_gb)) as pool:
                for idx, (name, status) in enumerate(pool.imap_unordered(process_one_file, [str(path) for path in files]), start=1):
                    print(f"[{idx}/{len(files)}] {status} {name}", flush=True)
        else:
            init_worker(chunk_rows, memory_limit_gb=None)
            for idx, path in enumerate(files, start=1):
                name, status = process_one_file(str(path))
                print(f"[{idx}/{len(files)}] {status} {name}", flush=True)

        ex03_product_partials, ex03_coverage_partials, ex04_partials = collect_complete_partials(files)

    if not ex03_product_partials or not ex03_coverage_partials:
        raise RuntimeError("No Exercise 3 checkpoint files were available.")
    if not ex04_partials:
        raise RuntimeError("No Exercise 4 checkpoint files were available.")

    ex03 = finalize_exercise_03_from_partials(
        ex03_product_partials,
        ex03_coverage_partials,
        source_details={
            "mode": "exercises_03_04_checkpointed",
            "hs_bulk_files_processed": len(files),
            "partial_dir": str(EX03_PARTIAL_DIR),
        },
    )
    ex04 = finalize_exercise_04_from_partials(
        ex04_partials,
        source_details={
            "mode": "exercises_03_04_checkpointed",
            "hs_bulk_files_processed": len(files),
            "partial_dir": str(EX04_PARTIAL_DIR),
        },
    )

    write_json(
        RESULTS / "run_manifest_exercises_03_04_checkpointed.json",
        {
            "created_at_utc": now_utc(),
            "mode": "exercises_03_04_checkpointed",
            "exercises_md_updated": False,
            "hs_bulk_files_available": len(files),
            "workers": int(workers),
            "chunk_rows": int(chunk_rows),
            "exercise_03_product_partials": len(ex03_product_partials),
            "exercise_03_coverage_partials": len(ex03_coverage_partials),
            "exercise_04_partials": len(ex04_partials),
            "rows_ex03_concentration": int(len(ex03)),
            "rows_ex04_product_supplier": int(len(ex04)),
        },
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Exercises 3 and 4 in one checkpointed raw-file pass.")
    parser.add_argument("--max-files", type=int, default=None)
    parser.add_argument("--fresh", action="store_true", help="Delete existing Exercise 3/4 partials before processing.")
    parser.add_argument("--finalize-only", action="store_true", help="Finalize from existing Exercise 3/4 partials.")
    parser.add_argument("--workers", type=int, default=1, help="Parallel raw-file workers for checkpoint creation.")
    parser.add_argument("--chunk-rows", type=int, default=DEFAULT_CHUNK_ROWS, help="Raw Comtrade rows per chunk.")
    parser.add_argument("--memory-limit-gb", type=float, default=None, help="Optional process memory cap.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run(
        max_files=args.max_files,
        fresh=args.fresh,
        finalize_only=args.finalize_only,
        workers=args.workers,
        chunk_rows=args.chunk_rows,
        memory_limit_gb=args.memory_limit_gb,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
