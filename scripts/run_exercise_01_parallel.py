#!/usr/bin/env python3
"""Parallel raw-data runner for Exercise 1 concentration tables."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import trade_concentration_pipeline as tcp  # noqa: E402


TABLE_KINDS = ("product", "partner", "cell")


def partial_base_dir(country_sample: str) -> Path:
    return tcp.sample_processed_dir(country_sample) / "checkpoints" / "exercise_01_file_aggregates"


def partial_paths_for_raw(raw_path: Path, country_sample: str) -> dict[str, Path]:
    base = partial_base_dir(country_sample)
    name = tcp.checkpoint_name_for_raw(raw_path)
    return {kind: base / kind / name for kind in TABLE_KINDS}


def write_partial(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)


def partials_exist(paths: dict[str, Path]) -> bool:
    return all(path.exists() for path in paths.values())


def concentration_rows_from_values(values: pd.DataFrame, prefix: str, top5_partner: bool = False) -> pd.DataFrame:
    if values.empty:
        return pd.DataFrame()
    panel = tcp.save_country_panel()
    country_meta = panel.set_index("reporter_code")[["country", "iso3"]].to_dict("index")
    rows = []
    for (reporter_code, year, flow), group in values.groupby(["reporter_code", "year", "flow"], sort=True):
        meta = country_meta.get(int(reporter_code), {"country": str(reporter_code), "iso3": ""})
        row = {
            "country": meta["country"],
            "iso3": meta["iso3"],
            "reporter_code": int(reporter_code),
            "year": int(year),
            "flow": flow,
            "variant": "baseline",
            "total_trade_value": float(group["trade_value"].sum()),
            **tcp.metric_row(group["trade_value"], prefix),
        }
        if top5_partner:
            row["top_5_partner_share"] = tcp.top_share(group["trade_value"], n=5)
        rows.append(row)
    return pd.DataFrame(rows)


def cell_rows_from_chunk_partials(paths: list[Path]) -> pd.DataFrame:
    if not paths:
        return pd.DataFrame()
    import duckdb

    quoted = "[" + ", ".join("'" + str(path).replace("'", "''") + "'" for path in paths) + "]"
    con = duckdb.connect()
    try:
        grouped_sql = f"""
            SELECT
                CAST(reporter_code AS BIGINT) AS reporter_code,
                CAST(year AS BIGINT) AS year,
                CAST(flow AS VARCHAR) AS flow,
                CAST(cmd_code AS VARCHAR) AS cmd_code,
                CAST(partner_code AS BIGINT) AS partner_code,
                SUM(CAST(trade_value AS DOUBLE)) AS trade_value
            FROM read_parquet({quoted}, union_by_name=true)
            WHERE trade_value IS NOT NULL AND trade_value > 0
              AND (cmd_code IS NULL OR CAST(cmd_code AS VARCHAR) <> '999999')
            GROUP BY 1, 2, 3, 4, 5
        """
        metrics = con.execute(
            f"""
            WITH grouped AS ({grouped_sql}),
            ranked AS (
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
                FROM grouped
                WHERE trade_value > 0
            )
            SELECT
                reporter_code,
                year,
                flow,
                'baseline' AS variant,
                MAX(total) AS total_trade_value,
                ((2.0 * SUM(asc_rank * trade_value)) / (MAX(n) * MAX(total))) - ((MAX(n) + 1.0) / MAX(n))
                    AS product_partner_cell_gini,
                SUM(CASE WHEN desc_rank <= GREATEST(1, CAST(CEIL(n * 0.01) AS BIGINT)) THEN trade_value ELSE 0 END) / MAX(total)
                    AS product_partner_cell_top_1pct_share,
                SUM(CASE WHEN desc_rank <= GREATEST(1, CAST(CEIL(n * 0.02) AS BIGINT)) THEN trade_value ELSE 0 END) / MAX(total)
                    AS product_partner_cell_top_2pct_share,
                SUM(CASE WHEN desc_rank <= GREATEST(1, CAST(CEIL(n * 0.05) AS BIGINT)) THEN trade_value ELSE 0 END) / MAX(total)
                    AS product_partner_cell_top_5pct_share,
                SUM(CASE WHEN desc_rank <= GREATEST(1, CAST(CEIL(n * 0.10) AS BIGINT)) THEN trade_value ELSE 0 END) / MAX(total)
                    AS product_partner_cell_top_10pct_share,
                SUM(CASE WHEN desc_rank <= LEAST(200, n) THEN trade_value ELSE 0 END) / MAX(total)
                    AS product_partner_cell_top_200_share,
                CAST(MAX(n) AS BIGINT) AS product_partner_cell_active_count
            FROM ranked
            GROUP BY reporter_code, year, flow
            ORDER BY reporter_code, year, flow
            """
        ).df()
    finally:
        con.close()
    if metrics.empty:
        return metrics
    panel = tcp.save_country_panel()
    out = metrics.merge(panel[["reporter_code", "country", "iso3"]], on="reporter_code", how="left")
    out["country"] = out["country"].fillna(out["reporter_code"].astype(str))
    out["iso3"] = out["iso3"].fillna("")
    ordered = ["country", "iso3", "reporter_code", "year", "flow", "variant", "total_trade_value"]
    return out[ordered + [col for col in out.columns if col not in ordered]]


def compute_concentration_chunked(path: Path, chunk_rows: int) -> tuple[int, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    product_cols = ["reporter_code", "year", "flow", "cmd_code"]
    partner_cols = ["reporter_code", "year", "flow", "partner_code"]
    cell_cols = ["reporter_code", "year", "flow", "cmd_code", "partner_code"]
    product_sum: pd.DataFrame | None = None
    partner_sum: pd.DataFrame | None = None
    leaf_rows = 0
    tmp_dir = tcp.sample_processed_dir() / "checkpoints" / "exercise_01_file_aggregates" / "_tmp_cells" / path.stem
    shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    cell_partials: list[Path] = []

    try:
        for chunk_idx, leaf in enumerate(tcp.iter_leaf_trade_chunks(path, chunk_rows=chunk_rows), start=1):
            if leaf.empty:
                continue
            leaf_rows += int(len(leaf))
            product = leaf.groupby(product_cols, as_index=False)["trade_value"].sum()
            partner = leaf.groupby(partner_cols, as_index=False)["trade_value"].sum()
            cell = leaf.groupby(cell_cols, as_index=False)["trade_value"].sum()
            product_sum = tcp.add_group_sum_frame(product_sum, product, product_cols, compact_rows=250_000)
            partner_sum = tcp.add_group_sum_frame(partner_sum, partner, partner_cols, compact_rows=250_000, exclude_hs6=False)
            if not cell.empty:
                cell_path = tmp_dir / f"cell_{chunk_idx:06d}.parquet"
                cell.to_parquet(cell_path, index=False)
                cell_partials.append(cell_path)

        product_values = tcp.finish_group_sum_frame(product_sum, product_cols)
        partner_values = tcp.finish_group_sum_frame(partner_sum, partner_cols, exclude_hs6=False)
        product = concentration_rows_from_values(product_values, "product")
        partner = concentration_rows_from_values(partner_values, "partner", top5_partner=True)
        cell = cell_rows_from_chunk_partials(cell_partials)
        return leaf_rows, product, partner, cell
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def process_file(path_text: str, sample_config: dict, country_sample: str, chunk_rows: int) -> tuple[str, int, int, str]:
    tcp.configure_country_sample(**sample_config)
    path = Path(path_text)
    paths = partial_paths_for_raw(path, country_sample)
    if partials_exist(paths):
        return path.name, 0, 0, "skipped"
    leaf_rows, product, partner, cell = compute_concentration_chunked(path, chunk_rows=chunk_rows)
    if leaf_rows <= 0:
        empty = pd.DataFrame()
        for partial in paths.values():
            write_partial(partial, empty)
        return path.name, 0, 0, "empty"
    write_partial(paths["product"], product)
    write_partial(paths["partner"], partner)
    write_partial(paths["cell"], cell)
    return path.name, leaf_rows, int(len(product) + len(partner) + len(cell)), "written"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parallel Exercise 1 concentration generation from raw Comtrade files.")
    parser.add_argument("--workers", type=int, default=min(2, os.cpu_count() or 1))
    parser.add_argument("--chunk-rows", type=int, default=250_000)
    parser.add_argument("--max-files", type=int, default=None)
    parser.add_argument("--fresh", action="store_true", help="Remove Exercise 1 partial checkpoints before running.")
    parser.add_argument("--checkpoint-only", action="store_true", help="Write per-file checkpoints and skip final CSV/figure outputs.")
    parser.add_argument("--finalize-only", action="store_true", help="Skip raw files and rebuild final outputs from existing checkpoints.")
    parser.add_argument("--country-sample", choices=tcp.COUNTRY_SAMPLE_CHOICES, default="rd2_countries")
    parser.add_argument("--min-available-years", type=int, default=10)
    parser.add_argument("--start-year", type=int, default=1988)
    parser.add_argument("--end-year", type=int, default=None)
    parser.add_argument("--refresh-availability", action="store_true")
    return parser.parse_args()


def sort_concentration_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    cols = [col for col in ["country", "iso3", "reporter_code", "year", "flow", "variant"] if col in df.columns]
    return df.sort_values(cols).reset_index(drop=True)


def read_partials(files: list[Path], country_sample: str, kind: str) -> pd.DataFrame:
    paths = [partial_paths_for_raw(path, country_sample)[kind] for path in files]
    frames = []
    for path in paths:
        if not path.exists():
            continue
        frame = pd.read_parquet(path)
        if not frame.empty:
            frames.append(frame)
    return sort_concentration_rows(pd.concat(frames, ignore_index=True)) if frames else pd.DataFrame()


def main() -> int:
    args = parse_args()
    sample_config = {
        "country_sample": args.country_sample,
        "min_available_years": args.min_available_years,
        "start_year": args.start_year,
        "end_year": args.end_year,
        "refresh_availability": args.refresh_availability,
    }
    tcp.configure_country_sample(**sample_config)
    tcp.ensure_dirs()
    if args.fresh and partial_base_dir(args.country_sample).exists():
        shutil.rmtree(partial_base_dir(args.country_sample))
    worker_sample_config = {**sample_config, "refresh_availability": False}
    files = tcp.hs_bulk_files(args.max_files)
    if not files:
        raise FileNotFoundError("No HS Comtrade bulk files found.")

    files_with_rows = 0
    leaf_rows = 0
    partial_rows = 0
    skipped = 0

    if args.finalize_only:
        skipped = len(files)
    elif args.workers <= 1:
        for completed, path in enumerate(files, start=1):
            name, file_leaf_rows, file_partial_rows, status = process_file(
                str(path),
                worker_sample_config,
                args.country_sample,
                args.chunk_rows,
            )
            if status != "skipped" or completed % 100 == 0:
                print(f"[{completed}/{len(files)}] Exercise 1 parallel {status}: {name}", flush=True)
            if status == "skipped":
                skipped += 1
            if file_leaf_rows <= 0:
                continue
            files_with_rows += 1
            leaf_rows += int(file_leaf_rows)
            partial_rows += int(file_partial_rows)
    else:
        with ProcessPoolExecutor(max_workers=max(1, args.workers)) as executor:
            futures = {
                executor.submit(process_file, str(path), worker_sample_config, args.country_sample, args.chunk_rows): path
                for path in files
            }
            for completed, future in enumerate(as_completed(futures), start=1):
                path = futures[future]
                name, file_leaf_rows, file_partial_rows, status = future.result()
                if status != "skipped" or completed % 100 == 0:
                    print(f"[{completed}/{len(files)}] Exercise 1 parallel {status}: {name}", flush=True)
                if status == "skipped":
                    skipped += 1
                if file_leaf_rows <= 0:
                    continue
                files_with_rows += 1
                leaf_rows += int(file_leaf_rows)
                partial_rows += int(file_partial_rows)

    if args.checkpoint_only and not args.finalize_only:
        present = sum(
            1
            for raw in files
            for partial in partial_paths_for_raw(raw, args.country_sample).values()
            if partial.exists()
        )
        print(
            f"Checkpointed Exercise 1 partials present for this file window: {present}/{len(files) * len(TABLE_KINDS)}",
            flush=True,
        )
        return 0

    product = read_partials(files, args.country_sample, "product")
    partner = read_partials(files, args.country_sample, "partner")
    cell = read_partials(files, args.country_sample, "cell")

    if product.empty:
        raise RuntimeError("No Exercise 1 rows were produced from HS bulk files.")

    concentration = sort_concentration_rows(tcp.merge_metric_tables(product, partner, cell))

    tcp.EX01_TABLES.mkdir(parents=True, exist_ok=True)
    product.to_csv(tcp.EX01_TABLES / "product_concentration_all_years.csv", index=False)
    partner.to_csv(tcp.EX01_TABLES / "partner_concentration_all_years.csv", index=False)
    cell.to_csv(tcp.EX01_TABLES / "product_partner_cell_concentration_all_years.csv", index=False)
    concentration.to_parquet(tcp.sample_processed_path("concentration_all_years.parquet"), index=False)
    concentration.to_csv(tcp.EX01_TABLES / "concentration_all_years.csv", index=False)

    tcp.make_exercise_01_figures(concentration)
    tcp.write_exercise_01_memo(concentration)
    manifest = {
        "created_at_utc": tcp.now_utc(),
        "mode": "exercise_01_raw_parallel",
        "country_sample": args.country_sample,
        "workers": int(args.workers),
        "hs_bulk_files_seen": len(files),
        "hs_bulk_files_with_rows": files_with_rows,
        "partials_existing_skipped": skipped,
        "partial_rows_written": partial_rows,
        "leaf_rows": leaf_rows,
        "rows_concentration": int(len(concentration)),
        "product_excluded_hs6_codes": sorted(tcp.EXCLUDED_HS6_CODES),
        "partner_concentration_includes_hs6_codes": sorted(tcp.EXCLUDED_HS6_CODES),
        "hs6_999999_rows": {"product_and_product_partner_outputs": 0},
        "exercises_md_updated": False,
    }
    tcp.write_json(tcp.sample_results_dir(args.country_sample) / "run_manifest_exercise_01_parallel.json", manifest)
    if args.max_files is None:
        tcp.mark_exercise_outputs_complete("1", details=manifest)
    print(f"Wrote Exercise 1 concentration rows: {len(concentration)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
