#!/usr/bin/env python3
"""Plot HS section shares of export lines against export value shares.

This reproduces the diagnostic behind Cadot-Carrere-Strauss-Kahn's
classification concern in the project's own Comtrade aggregates.
"""

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

SECTION_LABELS = {
    1: ("01-05", "Live animals and animal products"),
    2: ("06-14", "Vegetable products"),
    3: ("15", "Animal/vegetable fats and oils"),
    4: ("16-24", "Prepared foodstuffs, beverages, tobacco"),
    5: ("25-27", "Mineral products"),
    6: ("28-38", "Chemicals and allied industries"),
    7: ("39-40", "Plastics and rubber"),
    8: ("41-43", "Raw hides, skins, leather, furs"),
    9: ("44-46", "Wood and articles of wood"),
    10: ("47-49", "Pulp, paper, printed matter"),
    11: ("50-63", "Textiles and textile articles"),
    12: ("64-67", "Footwear, headgear, umbrellas"),
    13: ("68-70", "Stone, plaster, ceramics, glass"),
    14: ("71", "Precious metals and stones"),
    15: ("72-83", "Base metals and articles"),
    16: ("84-85", "Machinery and electrical equipment"),
    17: ("86-89", "Vehicles, aircraft, vessels"),
    18: ("90-92", "Precision, medical, musical instruments"),
    19: ("93", "Arms and ammunition"),
    20: ("94-96", "Miscellaneous manufactured articles"),
    21: ("97", "Works of art, collectors' pieces, antiques"),
}

HS_SECTION_CASE = """
case
  when hs2 between 1 and 5 then 1
  when hs2 between 6 and 14 then 2
  when hs2 = 15 then 3
  when hs2 between 16 and 24 then 4
  when hs2 between 25 and 27 then 5
  when hs2 between 28 and 38 then 6
  when hs2 between 39 and 40 then 7
  when hs2 between 41 and 43 then 8
  when hs2 between 44 and 46 then 9
  when hs2 between 47 and 49 then 10
  when hs2 between 50 and 63 then 11
  when hs2 between 64 and 67 then 12
  when hs2 between 68 and 70 then 13
  when hs2 = 71 then 14
  when hs2 between 72 and 83 then 15
  when hs2 between 84 and 85 then 16
  when hs2 between 86 and 89 then 17
  when hs2 between 90 and 92 then 18
  when hs2 = 93 then 19
  when hs2 between 94 and 96 then 20
  when hs2 = 97 then 21
  else null
end
"""


def sample_aggregate_glob(country_sample: str) -> Path:
    if country_sample == "prof_p_33":
        return DATA_PROCESSED / "exercise_02_12_file_aggregates" / "*.parquet"
    return DATA_PROCESSED / "samples" / country_sample / "exercise_02_12_file_aggregates" / "*.parquet"


def sample_result_dir(country_sample: str) -> Path:
    if country_sample == "prof_p_33":
        return RESULTS / "section_16_diagnostics"
    return RESULTS / "samples" / country_sample / "section_16_diagnostics"


def label_for_year(year: int | None) -> str:
    return "all_years" if year is None else str(year)


def query_section_shares(country_sample: str, year: int | None, line_count_mode: str) -> pd.DataFrame:
    source_glob = sample_aggregate_glob(country_sample)
    source_dir = source_glob.parent
    if not source_dir.exists() or not any(source_dir.glob("*.parquet")):
        raise FileNotFoundError(f"No aggregate parquet files found under {source_dir}")

    year_filter = "" if year is None else f"and year = {int(year)}"
    excluded_codes = ", ".join(f"'{code}'" for code in sorted(EXCLUDED_HS6_CODES))
    if line_count_mode == "unique_products":
        line_count_expr = "count(distinct cmd_code)"
        line_count_name = "distinct_hs6_lines"
    elif line_count_mode == "active_country_year_products":
        line_count_expr = "count(*)"
        line_count_name = "active_country_year_hs6_lines"
    else:
        raise ValueError(f"Unsupported line count mode: {line_count_mode}")

    query = f"""
    with base as (
      select
        try_cast(substr(cmd_code, 1, 2) as integer) as hs2,
        cmd_code,
        trade_value
      from read_parquet('{source_glob.as_posix()}')
      where dimension = 'product'
        and flow = 'Exports'
        and regexp_matches(cmd_code, '^[0-9]{{6}}$')
        and cmd_code not in ({excluded_codes})
        {year_filter}
    ),
    sectioned as (
      select
        {HS_SECTION_CASE} as hs_section,
        cmd_code,
        trade_value
      from base
    ),
    aggregate as (
      select
        hs_section,
        {line_count_expr} as line_count,
        sum(trade_value) as export_value
      from sectioned
      where hs_section is not null
      group by hs_section
    ),
    totals as (
      select
        sum(line_count) as total_line_count,
        sum(export_value) as total_export_value
      from aggregate
    )
    select
      hs_section,
      line_count as {line_count_name},
      export_value,
      line_count / total_line_count as line_share,
      export_value / total_export_value as export_value_share,
      export_value / nullif(line_count, 0) as export_value_per_line
    from aggregate, totals
    order by hs_section
    """
    out = duckdb.connect().execute(query).fetchdf()
    if out.empty:
        raise RuntimeError("The section-share query returned no rows.")

    out["hs_section"] = out["hs_section"].astype(int)
    out["hs2_range"] = out["hs_section"].map(lambda section: SECTION_LABELS[int(section)][0])
    out["section_label"] = out["hs_section"].map(lambda section: SECTION_LABELS[int(section)][1])
    out["country_sample"] = country_sample
    out["year_scope"] = label_for_year(year)
    out["line_count_mode"] = line_count_mode
    order = [
        "country_sample",
        "year_scope",
        "line_count_mode",
        "hs_section",
        "hs2_range",
        "section_label",
        out.columns[1],
        "export_value",
        "line_share",
        "export_value_share",
        "export_value_per_line",
    ]
    return out[order]


def plot_section_shares(df: pd.DataFrame, output_path: Path, year: int | None, line_count_mode: str) -> None:
    fig, ax = plt.subplots(figsize=(8.2, 6.2))
    line_col = "distinct_hs6_lines" if line_count_mode == "unique_products" else "active_country_year_hs6_lines"
    max_axis = max(float(df["line_share"].max()), float(df["export_value_share"].max())) * 1.08

    regular = df[df["hs_section"] != 16]
    section_16 = df[df["hs_section"] == 16]
    ax.scatter(regular["line_share"], regular["export_value_share"], color="#174a73", s=58, zorder=3)
    if not section_16.empty:
        ax.scatter(section_16["line_share"], section_16["export_value_share"], color="#b8322a", s=82, zorder=4)

    ax.plot([0, max_axis], [0, max_axis], color="#d62728", linewidth=1.8, zorder=2)

    for row in df.itertuples(index=False):
        dx = 0.0025
        dy = 0.0025
        if int(row.hs_section) in {11, 15, 16}:
            dx = 0.003
        ax.annotate(str(int(row.hs_section)), (row.line_share, row.export_value_share), xytext=(dx, dy), textcoords="offset fontsize", fontsize=10)

    year_text = "all available years" if year is None else str(year)
    line_text = "distinct HS6 products" if line_count_mode == "unique_products" else "active country-year-HS6 products"
    ax.set_title(f"HS section shares in {df['country_sample'].iloc[0]} exports, {year_text}", pad=12)
    ax.set_xlabel(f"Share of export lines ({line_text})")
    ax.set_ylabel("Share of export value")
    ax.set_xlim(0, max_axis)
    ax.set_ylim(0, max_axis)
    ax.grid(axis="both", color="#d7dee2", linewidth=0.8, alpha=0.8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.text(
        0.01,
        -0.18,
        f"Source: project Comtrade aggregates. Exports only. HS6 999999 excluded before aggregation. Line count column: {line_col}.",
        transform=ax.transAxes,
        fontsize=9,
        ha="left",
        va="top",
    )
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def write_note(df: pd.DataFrame, output_path: Path, figure_path: Path, table_path: Path) -> None:
    section_16 = df[df["hs_section"] == 16].iloc[0]
    line_count_col = "distinct_hs6_lines" if "distinct_hs6_lines" in df.columns else "active_country_year_hs6_lines"
    content = f"""# HS Section Line-Value Diagnostic

This diagnostic compares each HS section's share of export product lines with its share of export value.

## Construction

Unit before aggregation: reporter-year-HS6 product export value from the project Comtrade file aggregates.

Formula:

`line_share_s = line_count_s / sum_s line_count_s`

`value_share_s = export_value_s / sum_s export_value_s`

For product-level work, HS6 `999999` is excluded before aggregation. Partner `0` is already absent from the source aggregates. The line-count mode for this run is `{df['line_count_mode'].iloc[0]}`.

## Main Reading

Section 16 is HS chapters 84-85: machinery and electrical equipment. In this run, Section 16 accounts for {section_16['line_share']:.1%} of export lines and {section_16['export_value_share']:.1%} of export value. If the section lay exactly on the 45-degree line, its value share would equal its line share. Being above the line means high export value per HS6 line.

## Outputs

- Figure: `{figure_path.relative_to(ROOT)}`
- Table: `{table_path.relative_to(ROOT)}`

"""
    output_path.write_text(content, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country-sample", choices=COUNTRY_SAMPLE_CHOICES, default="rd2_countries")
    parser.add_argument("--year", type=int, default=None, help="Restrict to one year. Default uses all available years.")
    parser.add_argument(
        "--line-count-mode",
        choices=("unique_products", "active_country_year_products"),
        default="unique_products",
        help="Use distinct HS6 products or active reporter-year-HS6 product observations as the x-axis denominator.",
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = args.output_dir or sample_result_dir(args.country_sample)
    out_dir.mkdir(parents=True, exist_ok=True)
    scope = label_for_year(args.year)
    stem = f"hs_section_line_value_shares_{args.country_sample}_{scope}_{args.line_count_mode}"
    table_path = out_dir / f"{stem}.csv"
    figure_path = out_dir / f"{stem}.png"
    note_path = out_dir / f"{stem}.md"

    df = query_section_shares(args.country_sample, args.year, args.line_count_mode)
    df.to_csv(table_path, index=False)
    plot_section_shares(df, figure_path, args.year, args.line_count_mode)
    write_note(df, note_path, figure_path, table_path)

    section_16 = df[df["hs_section"] == 16].iloc[0]
    print(f"Wrote {figure_path}")
    print(f"Wrote {table_path}")
    print(f"Wrote {note_path}")
    print(f"Section 16 line share: {section_16['line_share']:.4f}")
    print(f"Section 16 export value share: {section_16['export_value_share']:.4f}")


if __name__ == "__main__":
    main()
