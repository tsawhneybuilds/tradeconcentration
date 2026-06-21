#!/usr/bin/env python3
"""Count and plot observed HS6 product codes by year."""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_PROCESSED = ROOT / "data" / "processed"
RESULTS = ROOT / "results"
COUNTRY_SAMPLE_CHOICES = ("prof_p_33", "world_broad", "rd2_countries")
EXCLUDED_HS6_CODES = {"999999"}
FLOW_ORDER = {"Any flow": 0, "Exports": 1, "Imports": 2}
HS_REVISION_STARTS = [
    (1996, "HS96"),
    (2002, "HS02"),
    (2007, "HS07"),
    (2012, "HS12"),
    (2017, "HS17"),
    (2022, "HS22"),
]


def sample_base(country_sample: str) -> Path:
    if country_sample == "prof_p_33":
        return DATA_PROCESSED
    return DATA_PROCESSED / "samples" / country_sample


def result_base(country_sample: str) -> Path:
    if country_sample == "prof_p_33":
        return RESULTS
    return RESULTS / "samples" / country_sample


def export_aggregate_glob(country_sample: str) -> Path:
    return sample_base(country_sample) / "exercise_02_12_file_aggregates" / "*.parquet"


def import_aggregate_glob(country_sample: str) -> Path:
    return sample_base(country_sample) / "checkpoints" / "exercise_03_file_aggregates" / "product_values" / "*.parquet"


def output_paths(country_sample: str) -> tuple[Path, Path, Path]:
    base = result_base(country_sample)
    table = base / "methods_tables" / "hs6_codes_by_year.csv"
    figure = base / "methods_figures" / "hs6_codes_by_year.png"
    note = base / "methods_tables" / "hs6_codes_by_year.md"
    return table, figure, note


def require_parquet_glob(path_glob: Path, label: str) -> None:
    source_dir = path_glob.parent
    if not source_dir.exists() or not any(source_dir.glob("*.parquet")):
        raise FileNotFoundError(f"No {label} parquet files found under {source_dir}")


def query_hs6_counts(country_sample: str) -> pd.DataFrame:
    export_glob = export_aggregate_glob(country_sample)
    import_glob = import_aggregate_glob(country_sample)
    require_parquet_glob(export_glob, "export aggregate")
    require_parquet_glob(import_glob, "import aggregate")
    excluded_codes = ", ".join(f"'{code}'" for code in sorted(EXCLUDED_HS6_CODES))

    query = f"""
    with export_base as (
      select
        cast(year as integer) as year,
        'Exports' as flow,
        cast(cmd_code as varchar) as hs6,
        cast(reporter_code as integer) as reporter_code,
        cast(trade_value as double) as trade_value
      from read_parquet('{export_glob.as_posix()}', union_by_name=true)
      where dimension = 'product'
        and flow = 'Exports'
        and trade_value > 0
        and regexp_matches(cast(cmd_code as varchar), '^[0-9]{{6}}$')
        and cast(cmd_code as varchar) not in ({excluded_codes})
    ),
    import_base as (
      select
        cast(year as integer) as year,
        'Imports' as flow,
        cast(cmd_code as varchar) as hs6,
        cast(reporter_code as integer) as reporter_code,
        cast(trade_value as double) as trade_value
      from read_parquet('{import_glob.as_posix()}', union_by_name=true)
      where trade_value > 0
        and regexp_matches(cast(cmd_code as varchar), '^[0-9]{{6}}$')
        and cast(cmd_code as varchar) not in ({excluded_codes})
    ),
    base as (
      select * from export_base
      union all
      select * from import_base
    ),
    flow_counts as (
      select
        year,
        flow,
        count(distinct hs6) as observed_hs6_codes,
        count(*) as active_country_year_hs6_products,
        count(distinct reporter_code) as reporters_with_trade,
        count(distinct reporter_code || '-' || year || '-' || flow) as reporter_year_flow_observations,
        sum(trade_value) as trade_value
      from base
      group by year, flow
    ),
    any_counts as (
      select
        year,
        'Any flow' as flow,
        count(distinct hs6) as observed_hs6_codes,
        count(*) as active_country_year_hs6_products,
        count(distinct reporter_code) as reporters_with_trade,
        count(distinct reporter_code || '-' || year || '-' || flow) as reporter_year_flow_observations,
        sum(trade_value) as trade_value
      from base
      group by year
    ),
    combined as (
      select * from flow_counts
      union all
      select * from any_counts
    )
    select * from combined
    order by
      year,
      case flow when 'Any flow' then 0 when 'Exports' then 1 when 'Imports' then 2 else 3 end
    """
    with duckdb.connect() as con:
        counts = con.execute(query).fetchdf()
    if counts.empty:
        raise RuntimeError("HS6 count query returned no rows.")

    counts.insert(0, "country_sample", country_sample)
    counts["product_universe"] = "Observed positive HS6 product codes"
    counts["excluded_hs6_codes"] = ",".join(sorted(EXCLUDED_HS6_CODES))
    counts["source_note"] = (
        "Exports use exercise_02_12 product aggregates; imports use Exercise 3 import product-value "
        "checkpoints. HS6 999999 is excluded before aggregation."
    )
    counts["flow_order"] = counts["flow"].map(FLOW_ORDER).fillna(99).astype(int)
    return counts.sort_values(["year", "flow_order"]).reset_index(drop=True)


def plot_hs6_counts(counts: pd.DataFrame, output_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9.2, 5.4))
    colors = {"Any flow": "#1f2933", "Exports": "#0b6b62", "Imports": "#2563eb"}
    widths = {"Any flow": 2.6, "Exports": 1.9, "Imports": 1.9}
    for flow in ["Any flow", "Exports", "Imports"]:
        group = counts[counts["flow"].eq(flow)].sort_values("year")
        if group.empty:
            continue
        ax.plot(
            group["year"],
            group["observed_hs6_codes"],
            marker="o",
            markersize=3.8,
            linewidth=widths[flow],
            color=colors[flow],
            label=flow,
        )

    ymax = float(counts["observed_hs6_codes"].max())
    ymin = float(counts["observed_hs6_codes"].min())
    for year, label in HS_REVISION_STARTS:
        if counts["year"].min() <= year <= counts["year"].max():
            ax.axvline(year, color="#cbd5dc", linewidth=0.9, linestyle="--", zorder=0)
            ax.text(year + 0.12, ymin + (ymax - ymin) * 0.03, label, rotation=90, fontsize=8, color="#667085")

    sample = str(counts["country_sample"].iloc[0])
    ax.set_title(f"Observed HS6 product codes by year, {sample}", pad=12)
    ax.set_xlabel("Year")
    ax.set_ylabel("Distinct HS6 product codes")
    ax.grid(axis="y", color="#d7dee2", linewidth=0.8, alpha=0.85)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(frameon=False, ncols=3, loc="upper left")
    ax.text(
        0,
        -0.18,
        "Unit: distinct positive HS6 product codes observed in project aggregates by year. HS6 999999 excluded before aggregation.",
        transform=ax.transAxes,
        fontsize=9,
        color="#475467",
        ha="left",
        va="top",
    )
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def write_note(counts: pd.DataFrame, note_path: Path, table_path: Path, figure_path: Path) -> None:
    any_flow = counts[counts["flow"].eq("Any flow")].sort_values("year")
    first = any_flow.iloc[0]
    last = any_flow.iloc[-1]
    content = f"""# HS6 Codes by Year

This diagnostic counts the number of observed HS6 product codes in each year of the project data.

## Construction

Unit before aggregation: reporter-year-flow-HS6 product value. Export rows come from the Exercise 02/12 export product aggregates. Import rows come from the Exercise 3 import product-value checkpoints.

Formula:

`observed_hs6_codes_t = count_distinct(hs6_code)` within year `t`

For the flow-specific rows, the count is within year and flow. For the `Any flow` row, a code is counted once if it appears in exports, imports, or both in that year.

HS6 `999999` is excluded before aggregation because it means "Commodities not specified" rather than a real product category.

## Main Reading

The rd2 sample has {int(first.observed_hs6_codes):,} observed HS6 product codes in {int(first.year)} and {int(last.observed_hs6_codes):,} in {int(last.year)} when exports and imports are pooled as `Any flow`.

## Outputs

- Figure: `{figure_path.relative_to(ROOT)}`
- Table: `{table_path.relative_to(ROOT)}`
"""
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(content, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country-sample", choices=COUNTRY_SAMPLE_CHOICES, default="rd2_countries")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    counts = query_hs6_counts(args.country_sample)
    table_path, figure_path, note_path = output_paths(args.country_sample)
    table_path.parent.mkdir(parents=True, exist_ok=True)
    counts.to_csv(table_path, index=False)
    plot_hs6_counts(counts, figure_path)
    write_note(counts, note_path, table_path, figure_path)
    print(f"Wrote {table_path}")
    print(f"Wrote {figure_path}")
    print(f"Wrote {note_path}")


if __name__ == "__main__":
    main()
