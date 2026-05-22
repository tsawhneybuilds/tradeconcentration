#!/usr/bin/env python3
"""HS2-preserving Exercise 10 benchmark.

This is the strict benchmark from the project plan:

- use real Comtrade HS6 product totals only;
- preserve country-year-flow total trade;
- preserve each country-year-flow HS2 sector total;
- preserve the active HS6 product count within each HS2 sector;
- randomize HS6 product shares only within HS2 sectors.

The earlier active-count benchmark is useful as a loose null, but it is not the
main Exercise 10 test requested in the plan.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from trade_concentration_pipeline import (
    EX10_FIGURES,
    EX10_TABLES,
    RESULTS,
    configure_country_sample,
    drop_excluded_hs6,
    extract_leaf_trade,
    gini,
    hs_bulk_files,
    read_comtrade_file,
    save_country_panel,
    sample_processed_path,
    sample_results_dir,
    top_share,
)


TOP_METRICS = {
    "top_1pct_share": ("pct", 0.01),
    "top_2pct_share": ("pct", 0.02),
    "top_5pct_share": ("pct", 0.05),
    "top_10pct_share": ("pct", 0.10),
    "top_200_share": ("n", 200),
}

HS2_LABELS = {
    "27": "mineral fuels/oil/petroleum",
    "71": "precious stones/metals",
    "87": "vehicles and parts",
    "88": "aircraft/spacecraft",
    "89": "ships/boats/floating structures",
    "90": "optical/medical/precision instruments",
    "91": "clocks/watches",
    "93": "arms/ammunition",
    "97": "art/antiques",
}


@dataclass(frozen=True)
class BenchmarkPaths:
    partial_csv: Path
    final_csv: Path
    hs2_csv: Path
    parquet: Path
    hs2_parquet: Path
    actual_csv: Path
    memo: Path
    validation_json: Path
    manifest_json: Path
    figure_dir: Path


def normalize_hs2_codes(codes: list[str]) -> list[str]:
    out = []
    for code in codes:
        cleaned = re.sub(r"\D", "", str(code))
        if not cleaned:
            continue
        cleaned = cleaned.zfill(2)[:2]
        if cleaned not in out:
            out.append(cleaned)
    return out


def default_output_tag(excluded_hs2: list[str]) -> str | None:
    if not excluded_hs2:
        return None
    return "no_hs" + "_".join(excluded_hs2)


def safe_tag(tag: str | None) -> str | None:
    if tag is None:
        return None
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", tag).strip("_").lower()
    return cleaned or None


def benchmark_paths(output_tag: str | None) -> BenchmarkPaths:
    tag = safe_tag(output_tag)
    if tag is None:
        return BenchmarkPaths(
            partial_csv=EX10_TABLES / "random_benchmark_hs2_product_all_years.partial.csv",
            final_csv=EX10_TABLES / "random_benchmark_all_years.csv",
            hs2_csv=EX10_TABLES / "random_benchmark_hs2_product_all_years.csv",
            parquet=sample_processed_path("random_benchmark_all_years.parquet"),
            hs2_parquet=sample_processed_path("random_benchmark_hs2_product_all_years.parquet"),
            actual_csv=EX10_TABLES / "actual_concentration_inputs.csv",
            memo=sample_results_dir() / "exercise_10_random_benchmark.md",
            validation_json=EX10_TABLES / "benchmark_validation.json",
            manifest_json=sample_results_dir() / "run_manifest_exercise_10_hs2.json",
            figure_dir=EX10_FIGURES,
        )

    return BenchmarkPaths(
        partial_csv=EX10_TABLES / f"random_benchmark_hs2_product_{tag}_all_years.partial.csv",
        final_csv=EX10_TABLES / f"random_benchmark_{tag}_all_years.csv",
        hs2_csv=EX10_TABLES / f"random_benchmark_hs2_product_{tag}_all_years.csv",
        parquet=sample_processed_path(f"random_benchmark_{tag}_all_years.parquet"),
        hs2_parquet=sample_processed_path(f"random_benchmark_hs2_product_{tag}_all_years.parquet"),
        actual_csv=EX10_TABLES / f"actual_concentration_inputs_{tag}.csv",
        memo=sample_results_dir() / f"exercise_10_random_benchmark_{tag}.md",
        validation_json=EX10_TABLES / f"benchmark_validation_{tag}.json",
        manifest_json=sample_results_dir() / f"run_manifest_exercise_10_hs2_{tag}.json",
        figure_dir=EX10_FIGURES / tag,
    )


def format_exclusions(excluded_hs2: list[str]) -> str:
    if not excluded_hs2:
        return "none"
    return ", ".join(f"HS{code} {HS2_LABELS.get(code, '')}".strip() for code in excluded_hs2)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")


def backup_active_count_outputs() -> None:
    backups = [
        (sample_processed_path("random_benchmark_all_years.parquet"), sample_processed_path("random_benchmark_active_count_null_all_years.parquet")),
        (EX10_TABLES / "random_benchmark_all_years.csv", EX10_TABLES / "random_benchmark_active_count_null_all_years.csv"),
        (EX10_TABLES / "actual_concentration_inputs.csv", EX10_TABLES / "actual_concentration_inputs_active_count_null.csv"),
        (EX10_TABLES / "benchmark_validation.json", EX10_TABLES / "benchmark_validation_active_count_null.json"),
        (sample_results_dir() / "exercise_10_random_benchmark.md", sample_results_dir() / "exercise_10_random_benchmark_active_count_null.md"),
    ]
    for src, dst in backups:
        if src.exists() and not dst.exists():
            shutil.copy2(src, dst)


def metric_row(values: np.ndarray) -> dict[str, float]:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values) & (values > 0)]
    out = {"gini": gini(values)}
    for name, (kind, value) in TOP_METRICS.items():
        if kind == "pct":
            out[name] = top_share(values, pct=float(value))
        else:
            out[name] = top_share(values, n=int(value))
    return out


def simulated_metrics_for_group(product_totals: pd.DataFrame, simulations: int, rng: np.random.Generator) -> dict[str, np.ndarray]:
    products = (
        product_totals.groupby(["hs2", "cmd_code"], as_index=False)["trade_value"].sum()
        .sort_values(["hs2", "cmd_code"])
    )
    sector = products.groupby("hs2", as_index=False).agg(
        hs2_total=("trade_value", "sum"),
        active_products=("cmd_code", "nunique"),
    )
    total = float(sector["hs2_total"].sum())
    active_items = int(sector["active_products"].sum())

    if active_items <= 0 or total <= 0:
        empty = np.full(simulations, np.nan)
        return {"gini": empty, **{name: empty.copy() for name in TOP_METRICS}}
    if active_items == 1:
        return {
            "gini": np.zeros(simulations),
            **{name: np.ones(simulations) for name in TOP_METRICS},
        }

    simulated = np.empty((simulations, active_items), dtype=np.float64)
    col = 0
    for row in sector.itertuples(index=False):
        k = int(row.active_products)
        hs2_total = float(row.hs2_total)
        if k <= 0:
            continue
        if k == 1:
            simulated[:, col] = hs2_total
            col += 1
            continue
        draws = rng.exponential(scale=1.0, size=(simulations, k))
        draws /= draws.sum(axis=1, keepdims=True)
        simulated[:, col : col + k] = draws * hs2_total
        col += k

    simulated.sort(axis=1)
    rank = np.arange(1, active_items + 1, dtype=float)
    out = {
        "gini": ((2.0 * simulated.dot(rank)) / (active_items * total)) - ((active_items + 1) / active_items)
    }
    for name, (kind, value) in TOP_METRICS.items():
        if kind == "pct":
            k = max(1, int(math.ceil(active_items * float(value))))
        else:
            k = min(int(value), active_items)
        out[name] = simulated[:, -k:].sum(axis=1) / total
    return out


def summarize_group(product_totals: pd.DataFrame, simulations: int, rng: np.random.Generator, meta: dict) -> dict:
    products = product_totals.groupby(["hs2", "cmd_code"], as_index=False)["trade_value"].sum()
    product_values = products.groupby("cmd_code", as_index=False)["trade_value"].sum()["trade_value"].to_numpy(dtype=float)
    actual = metric_row(product_values)
    sim = simulated_metrics_for_group(products, simulations, rng)

    row = {
        **meta,
        "dimension": "product_hs2_preserved",
        "benchmark_null": "hs2_preserving_within_sector_random_allocation",
        "simulations": simulations,
        "total_trade_value": float(product_values.sum()),
        "active_items": int(len(product_values)),
        "active_hs2_count": int(products["hs2"].nunique()),
    }
    for metric, actual_value in actual.items():
        simulated = sim[metric]
        row[f"actual_{metric}"] = float(actual_value)
        row[f"sim_{metric}_median"] = float(np.nanmedian(simulated))
        row[f"sim_{metric}_p05"] = float(np.nanpercentile(simulated, 5))
        row[f"sim_{metric}_p95"] = float(np.nanpercentile(simulated, 95))
        row[f"actual_{metric}_percentile"] = float(np.nanmean(simulated <= actual_value))
        row[f"actual_minus_sim_median_{metric}"] = float(actual_value - row[f"sim_{metric}_median"])
    return row


def append_rows(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    frame.to_csv(path, mode="a", index=False, header=not path.exists())


def load_done_keys(path: Path) -> set[tuple[int, int, str]]:
    if not path.exists():
        return set()
    done = pd.read_csv(path, usecols=["reporter_code", "year", "flow"])
    return {(int(r.reporter_code), int(r.year), str(r.flow)) for r in done.itertuples(index=False)}


def collect_and_simulate(
    simulations: int,
    seed: int,
    checkpoint_every: int,
    paths: BenchmarkPaths,
    excluded_hs2: list[str],
    output_tag: str | None,
    max_files: int | None = None,
) -> pd.DataFrame:
    files = hs_bulk_files(max_files=max_files)
    if not files:
        raise FileNotFoundError("No Comtrade HS bulk files found.")

    panel = save_country_panel().set_index("reporter_code")[["country", "iso3"]].to_dict("index")
    done = load_done_keys(paths.partial_csv)
    rng = np.random.default_rng(seed)
    rows: list[dict] = []
    processed_groups = 0

    for idx, path in enumerate(files, start=1):
        print(f"[{idx}/{len(files)}] HS2-preserving Exercise 10 from {path.name}", flush=True)
        leaf = extract_leaf_trade(read_comtrade_file(path))
        leaf = drop_excluded_hs6(leaf)
        if leaf.empty:
            continue
        if excluded_hs2:
            leaf = leaf[~leaf["hs2"].isin(excluded_hs2)].copy()
            if leaf.empty:
                continue
        for (reporter_code, year, flow), group in leaf.groupby(["reporter_code", "year", "flow"], sort=True):
            key = (int(reporter_code), int(year), str(flow))
            if key in done:
                continue
            meta = panel.get(int(reporter_code), {"country": str(reporter_code), "iso3": ""})
            row = summarize_group(
                group[["hs2", "cmd_code", "trade_value"]],
                simulations=simulations,
                rng=rng,
                meta={
                    "country": meta["country"],
                    "iso3": meta["iso3"],
                    "reporter_code": int(reporter_code),
                    "year": int(year),
                    "flow": str(flow),
                    "exclusion_variant": output_tag or "none",
                    "excluded_hs2": ",".join(excluded_hs2),
                },
            )
            rows.append(row)
            processed_groups += 1
            if processed_groups % checkpoint_every == 0:
                append_rows(paths.partial_csv, rows)
                done.update((int(r["reporter_code"]), int(r["year"]), str(r["flow"])) for r in rows)
                rows.clear()
                print(f"  checkpointed {processed_groups} new country-year-flow rows", flush=True)

    append_rows(paths.partial_csv, rows)
    out = pd.read_csv(paths.partial_csv)
    out = out.drop_duplicates(subset=["reporter_code", "year", "flow"], keep="last")
    out = out.sort_values(["country", "year", "flow"]).reset_index(drop=True)
    if "exclusion_variant" not in out.columns:
        out["exclusion_variant"] = output_tag or "none"
    if "excluded_hs2" not in out.columns:
        out["excluded_hs2"] = ",".join(excluded_hs2)
    out.to_csv(paths.final_csv, index=False)
    out.to_csv(paths.hs2_csv, index=False)
    out.to_parquet(paths.parquet, index=False)
    out.to_parquet(paths.hs2_parquet, index=False)

    actual = out[
        [
            "country",
            "iso3",
            "reporter_code",
            "year",
            "flow",
            "exclusion_variant",
            "excluded_hs2",
            "dimension",
            "total_trade_value",
            "active_items",
            "active_hs2_count",
            "actual_gini",
            "actual_top_1pct_share",
            "actual_top_2pct_share",
            "actual_top_5pct_share",
            "actual_top_10pct_share",
            "actual_top_200_share",
        ]
    ]
    actual.to_csv(paths.actual_csv, index=False)
    return out


def make_figures(df: pd.DataFrame, figure_dir: Path) -> None:
    import matplotlib.pyplot as plt
    import seaborn as sns

    figure_dir.mkdir(parents=True, exist_ok=True)
    for path in figure_dir.glob("*.png"):
        path.unlink()

    sns.set_theme(style="whitegrid")
    med = df.groupby(["year", "flow"], as_index=False)[["actual_gini", "sim_gini_median"]].median()
    long = med.melt(id_vars=["year", "flow"], var_name="series", value_name="gini")
    plt.figure(figsize=(11, 6))
    sns.lineplot(data=long, x="year", y="gini", hue="series", style="flow", errorbar=None)
    plt.title("Actual vs HS2-Preserved Simulated Product Gini")
    plt.tight_layout()
    plt.savefig(figure_dir / "actual_vs_simulated_gini_product_hs2_preserved.png", dpi=200)
    plt.close()

    pct = df.groupby(["year", "flow"], as_index=False)["actual_gini_percentile"].median()
    plt.figure(figsize=(11, 6))
    sns.lineplot(data=pct, x="year", y="actual_gini_percentile", hue="flow", errorbar=None)
    plt.axhline(0.95, color="black", linestyle="--", linewidth=1)
    plt.title("Actual Product Gini Percentile In HS2-Preserved Benchmark")
    plt.tight_layout()
    plt.savefig(figure_dir / "actual_gini_percentile_product_hs2_preserved.png", dpi=200)
    plt.close()

    share95 = df.assign(above_95=df["actual_gini_percentile"] >= 0.95).groupby(["year", "flow"], as_index=False)["above_95"].mean()
    plt.figure(figsize=(11, 6))
    sns.lineplot(data=share95, x="year", y="above_95", hue="flow", errorbar=None)
    plt.title("Share Above 95th Percentile: HS2-Preserved Product Benchmark")
    plt.tight_layout()
    plt.savefig(figure_dir / "share_above_95th_percentile_product_hs2_preserved.png", dpi=200)
    plt.close()

    latest_year = int(df["year"].max())
    latest = df[df["year"] == latest_year]
    plt.figure(figsize=(9, 6))
    sns.boxplot(data=latest, x="flow", y="actual_minus_sim_median_gini")
    plt.axhline(0, color="black", linewidth=0.8)
    plt.title(f"Actual Minus HS2 Benchmark Product Gini ({latest_year})")
    plt.tight_layout()
    plt.savefig(figure_dir / "latest_year_actual_minus_benchmark_gini_product_hs2_preserved.png", dpi=200)
    plt.close()


def write_memo(
    df: pd.DataFrame,
    simulations: int,
    seed: int,
    memo_path: Path,
    figure_dir: Path,
    excluded_hs2: list[str],
    output_tag: str | None,
) -> None:
    med = df.groupby("flow")[
        ["actual_gini", "sim_gini_median", "actual_minus_sim_median_gini", "actual_gini_percentile"]
    ].median().round(3)
    share95 = df.assign(above_95=df["actual_gini_percentile"] >= 0.95).groupby("flow")["above_95"].mean().round(3)
    latest_year = int(df["year"].max())
    latest = df[df["year"] == latest_year].groupby("flow")[
        ["actual_gini", "sim_gini_median", "actual_minus_sim_median_gini", "actual_gini_percentile"]
    ].median().round(3)
    exclusion_title = "No HS87 Vehicles/Parts" if excluded_hs2 == ["87"] else f"Excluding {format_exclusions(excluded_hs2)}"
    title_suffix = f" ({exclusion_title})" if excluded_hs2 else ""
    exclusion_bullet = (
        f"- Excludes {format_exclusions(excluded_hs2)} before calculating actual concentration and the benchmark.\n"
        if excluded_hs2
        else ""
    )
    result_file_note = (
        f"- Variant tag: `{output_tag}`.\n"
        if output_tag
        else ""
    )
    figure_dir_display = figure_dir.relative_to(RESULTS.parent)
    memo = f"""# Exercise 10: HS2-Preserving Product Random Benchmark{title_suffix}

Generated: {now_utc()}

This memo is intentionally descriptive. `exercises.md` should only be updated after discussion.

## Benchmark Design

- Uses real UN Comtrade HS6 annual product-partner data.
- Aggregates to HS6 product totals within each country-year-flow.
- Preserves each country-year-flow total trade value.
- Preserves each HS2 sector total within each country-year-flow.
- Preserves the active HS6 product count inside each HS2 sector.
- Randomizes HS6 product shares only within HS2 sectors.
{exclusion_bullet}- Excluded HS2 categories: {format_exclusions(excluded_hs2)}.
- Uses {simulations:,} simulations per country-year-flow with fixed seed `{seed}`.

## Median Actual Versus HS2-Preserved Benchmark

```text
{med.to_string()}
```

## Latest Available Year ({latest_year})

```text
{latest.to_string()}
```

## Share Of Country-Year-Flow Observations Above 95th Benchmark Percentile

```text
{share95.to_string()}
```

## Files

- Tables: `results/exercise_10_tables/`
- Figures: `{figure_dir_display}/`
- Processed data: `data/processed/random_benchmark{('_' + output_tag) if output_tag else ''}_all_years.parquet`
{result_file_note}

## Note

The earlier active-count-only benchmark has been backed up as `random_benchmark_active_count_null_all_years.*`.
The HS2-preserving benchmark is the main Exercise 10 result because it matches the planned non-naive null model.
"""
    memo_path.write_text(memo, encoding="utf-8")


def validate(
    df: pd.DataFrame,
    simulations: int,
    seed: int,
    files_seen: int,
    paths: BenchmarkPaths,
    excluded_hs2: list[str],
    output_tag: str | None,
) -> None:
    check = {
        "created_at_utc": now_utc(),
        "benchmark_null": "hs2_preserving_within_sector_random_allocation",
        "policy": "Preserves country-year-flow total trade, HS2 sector totals, and active HS6 product counts within HS2.",
        "output_tag": output_tag,
        "excluded_hs2": excluded_hs2,
        "excluded_hs2_labels": {code: HS2_LABELS.get(code, "") for code in excluded_hs2},
        "rows": int(len(df)),
        "countries": int(df["country"].nunique()),
        "year_min": int(df["year"].min()),
        "year_max": int(df["year"].max()),
        "flows": sorted(df["flow"].dropna().unique().tolist()),
        "simulations": simulations,
        "seed": seed,
        "hs_bulk_files_seen": files_seen,
        "actual_gini_percentile_min": float(df["actual_gini_percentile"].min()),
        "actual_gini_percentile_max": float(df["actual_gini_percentile"].max()),
        "median_by_flow": df.groupby("flow")[
            ["actual_gini", "sim_gini_median", "actual_minus_sim_median_gini", "actual_gini_percentile"]
        ].median().reset_index().to_dict("records"),
        "exercises_md_updated": False,
    }
    write_json(paths.validation_json, check)
    write_json(paths.manifest_json, check)


def publish_as_main(paths: BenchmarkPaths) -> None:
    canonical = benchmark_paths(None)
    copies = [
        (paths.final_csv, canonical.final_csv),
        (paths.hs2_csv, canonical.hs2_csv),
        (paths.parquet, canonical.parquet),
        (paths.hs2_parquet, canonical.hs2_parquet),
        (paths.actual_csv, canonical.actual_csv),
        (paths.memo, canonical.memo),
        (paths.validation_json, canonical.validation_json),
        (paths.manifest_json, canonical.manifest_json),
    ]
    for src, dst in copies:
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    canonical.figure_dir.mkdir(parents=True, exist_ok=True)
    for path in canonical.figure_dir.glob("*.png"):
        path.unlink()
    for src in paths.figure_dir.glob("*.png"):
        shutil.copy2(src, canonical.figure_dir / src.name)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--simulations", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260518)
    parser.add_argument("--checkpoint-every", type=int, default=25)
    parser.add_argument("--max-files", type=int, default=None)
    parser.add_argument("--fresh", action="store_true", help="Remove partial HS2 benchmark checkpoint before running.")
    parser.add_argument("--exclude-hs2", nargs="*", default=[], help="HS2 chapters to remove before running the benchmark, e.g. --exclude-hs2 87.")
    parser.add_argument("--output-tag", default=None, help="Output tag for variant files. Defaults to no_hs<codes> when exclusions are used.")
    parser.add_argument("--write-main", action="store_true", help="Also publish this variant to the canonical Exercise 10 output files.")
    parser.add_argument("--country-sample", choices=["prof_p_33", "world_broad"], default="prof_p_33")
    parser.add_argument("--min-available-years", type=int, default=10)
    parser.add_argument("--start-year", type=int, default=1988)
    parser.add_argument("--end-year", type=int, default=None)
    parser.add_argument("--refresh-availability", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_country_sample(
        country_sample=args.country_sample,
        min_available_years=args.min_available_years,
        start_year=args.start_year,
        end_year=args.end_year,
        refresh_availability=args.refresh_availability,
    )
    global EX10_TABLES
    global EX10_FIGURES
    result_base = sample_results_dir(args.country_sample)
    EX10_TABLES = result_base / "exercise_10_tables"
    EX10_FIGURES = result_base / "exercise_10_figures"
    backup_active_count_outputs()
    excluded_hs2 = normalize_hs2_codes(args.exclude_hs2)
    output_tag = safe_tag(args.output_tag) or default_output_tag(excluded_hs2)
    paths = benchmark_paths(output_tag)
    if args.fresh and paths.partial_csv.exists():
        paths.partial_csv.unlink()
    df = collect_and_simulate(
        simulations=args.simulations,
        seed=args.seed,
        checkpoint_every=args.checkpoint_every,
        paths=paths,
        excluded_hs2=excluded_hs2,
        output_tag=output_tag,
        max_files=args.max_files,
    )
    make_figures(df, paths.figure_dir)
    write_memo(
        df,
        simulations=args.simulations,
        seed=args.seed,
        memo_path=paths.memo,
        figure_dir=paths.figure_dir,
        excluded_hs2=excluded_hs2,
        output_tag=output_tag,
    )
    validate(
        df,
        simulations=args.simulations,
        seed=args.seed,
        files_seen=len(hs_bulk_files(max_files=args.max_files)),
        paths=paths,
        excluded_hs2=excluded_hs2,
        output_tag=output_tag,
    )
    if args.write_main:
        publish_as_main(paths)
    print(f"Wrote HS2-preserving Exercise 10 benchmark rows: {len(df)}", flush=True)


if __name__ == "__main__":
    main()
