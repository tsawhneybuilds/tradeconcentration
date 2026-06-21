#!/usr/bin/env python3
"""Plot HS2/HS4 export line shares against export value shares.

The diagnostic compares how much of the product code space a group covers with
how much of export value it accounts for. It is intended as a finer-grained
version of ``plot_hs_section_line_value_shares.py``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import pandas as pd

from plot_hs_section_line_value_shares import (
    COUNTRY_SAMPLE_CHOICES,
    EXCLUDED_HS6_CODES,
    HS_SECTION_CASE,
    ROOT,
    SECTION_LABELS,
    label_for_year,
    query_section_shares,
    sample_aggregate_glob,
)


RESULTS = ROOT / "results"
MAPPING_PATH = ROOT / "data" / "processed" / "exercise_03_bec5_mapping_approved.csv"

HS2_LABELS = {
    "01": "Live animals",
    "02": "Meat and edible meat offal",
    "03": "Fish, crustaceans, molluscs, and aquatic invertebrates",
    "04": "Dairy, eggs, honey, and other edible animal products",
    "05": "Other products of animal origin",
    "06": "Live trees, plants, bulbs, roots, and cut flowers",
    "07": "Edible vegetables and roots",
    "08": "Edible fruit and nuts",
    "09": "Coffee, tea, mate, and spices",
    "10": "Cereals",
    "11": "Milling products, malt, starches, and wheat gluten",
    "12": "Oil seeds, medicinal plants, straw, and fodder",
    "13": "Lac, gums, resins, and vegetable extracts",
    "14": "Vegetable plaiting materials and other vegetable products",
    "15": "Animal or vegetable fats and oils",
    "16": "Prepared meat, fish, or crustaceans",
    "17": "Sugars and sugar confectionery",
    "18": "Cocoa and cocoa preparations",
    "19": "Preparations of cereals, flour, starch, or milk",
    "20": "Preparations of vegetables, fruit, or nuts",
    "21": "Miscellaneous edible preparations",
    "22": "Beverages, spirits, and vinegar",
    "23": "Food-industry residues and animal fodder",
    "24": "Tobacco and manufactured tobacco substitutes",
    "25": "Salt, sulphur, earths, stone, plaster, lime, and cement",
    "26": "Ores, slag, and ash",
    "27": "Mineral fuels, oils, and related products",
    "28": "Inorganic chemicals and precious-metal compounds",
    "29": "Organic chemicals",
    "30": "Pharmaceutical products",
    "31": "Fertilizers",
    "32": "Dyes, pigments, paints, varnishes, and inks",
    "33": "Essential oils, perfumery, cosmetics, and toiletries",
    "34": "Soap, lubricants, waxes, candles, and modeling pastes",
    "35": "Albuminoids, modified starches, glues, and enzymes",
    "36": "Explosives, pyrotechnics, matches, and pyrophoric alloys",
    "37": "Photographic or cinematographic goods",
    "38": "Miscellaneous chemical products",
    "39": "Plastics and articles of plastics",
    "40": "Rubber and articles of rubber",
    "41": "Raw hides, skins, and leather",
    "42": "Leather articles, travel goods, handbags, and gut articles",
    "43": "Furskins and artificial fur",
    "44": "Wood, wood articles, and wood charcoal",
    "45": "Cork and articles of cork",
    "46": "Basketware and manufactures of plaiting materials",
    "47": "Wood pulp, recovered paper, and fibrous cellulose material",
    "48": "Paper, paperboard, and articles",
    "49": "Printed books, newspapers, pictures, and manuscripts",
    "50": "Silk",
    "51": "Wool, animal hair, horsehair yarn, and woven fabric",
    "52": "Cotton",
    "53": "Other vegetable textile fibres and paper yarn",
    "54": "Man-made filaments",
    "55": "Man-made staple fibres",
    "56": "Wadding, felt, nonwovens, special yarns, twine, and cordage",
    "57": "Carpets and textile floor coverings",
    "58": "Special woven fabrics, lace, tapestries, and embroidery",
    "59": "Coated textile fabrics and technical textile articles",
    "60": "Knitted or crocheted fabrics",
    "61": "Knitted or crocheted apparel and clothing accessories",
    "62": "Non-knitted apparel and clothing accessories",
    "63": "Other made-up textiles, worn clothing, and rags",
    "64": "Footwear",
    "65": "Headgear",
    "66": "Umbrellas, walking sticks, whips, and riding crops",
    "67": "Prepared feathers, artificial flowers, and human-hair articles",
    "68": "Stone, plaster, cement, asbestos, mica, and similar articles",
    "69": "Ceramic products",
    "70": "Glass and glassware",
    "71": "Precious stones, precious metals, jewelry, and coins",
    "72": "Iron and steel",
    "73": "Articles of iron or steel",
    "74": "Copper and articles of copper",
    "75": "Nickel and articles of nickel",
    "76": "Aluminum and articles of aluminum",
    "77": "Reserved for possible future HS use",
    "78": "Lead and articles of lead",
    "79": "Zinc and articles of zinc",
    "80": "Tin and articles of tin",
    "81": "Other base metals, cermets, and articles",
    "82": "Tools, implements, cutlery, spoons, and forks of base metal",
    "83": "Miscellaneous articles of base metal",
    "84": "Machinery, mechanical appliances, boilers, and parts",
    "85": "Electrical machinery, electronics, sound/TV equipment, and parts",
    "86": "Railway or tramway locomotives, rolling stock, and parts",
    "87": "Vehicles other than railway or tramway, and parts",
    "88": "Aircraft, spacecraft, and parts",
    "89": "Ships, boats, and floating structures",
    "90": "Optical, photographic, medical, and precision instruments",
    "91": "Clocks and watches",
    "92": "Musical instruments and parts",
    "93": "Arms and ammunition",
    "94": "Furniture, bedding, lamps, and prefabricated buildings",
    "95": "Toys, games, and sports equipment",
    "96": "Miscellaneous manufactured articles",
    "97": "Works of art, collectors' pieces, and antiques",
}


def sample_result_dir(country_sample: str) -> Path:
    if country_sample == "prof_p_33":
        return RESULTS / "hs_granularity_diagnostics"
    return RESULTS / "samples" / country_sample / "hs_granularity_diagnostics"


def line_count_spec(line_count_mode: str, granularity: str) -> tuple[str, str, str]:
    if line_count_mode == "unique_products":
        return "count(distinct cmd_code)", "distinct_hs6_lines", "distinct HS6 products"
    if line_count_mode == "active_country_year_products":
        return "count(*)", "active_country_year_hs6_lines", "active reporter-year-HS6 products"
    if line_count_mode == "native_codes":
        if granularity == "hs2":
            return "1", "distinct_hs2_codes", "distinct HS2 chapters"
        if granularity == "hs4":
            return "1", "distinct_hs4_codes", "distinct HS4 headings"
        if granularity == "hs6":
            return "1", "distinct_hs6_codes", "distinct HS6 products"
        if granularity == "hs_section":
            return "1", "distinct_hs_section_codes", "distinct HS sections"
    raise ValueError(f"Unsupported line count mode: {line_count_mode}")


def line_count_column(df: pd.DataFrame) -> str:
    candidates = [
        "distinct_hs_section_codes",
        "distinct_hs2_codes",
        "distinct_hs4_codes",
        "distinct_hs6_codes",
        "distinct_hs6_lines",
        "active_country_year_hs6_lines",
    ]
    for col in candidates:
        if col in df.columns:
            return col
    raise ValueError("No recognized line-count column found.")


def group_expr(granularity: str) -> tuple[str, str]:
    if granularity == "hs2":
        return "substr(cmd_code, 1, 2)", "HS2 chapter"
    if granularity == "hs4":
        return "substr(cmd_code, 1, 4)", "HS4 heading"
    if granularity == "hs6":
        return "cmd_code", "HS6 product"
    raise ValueError(f"Unsupported granularity: {granularity}")


def load_hs6_labels() -> dict[str, str]:
    if not MAPPING_PATH.exists():
        return {}

    cols = ["cmd_code", "hs_desc_official"]
    labels = pd.read_csv(MAPPING_PATH, usecols=cols, dtype={"cmd_code": "string", "hs_desc_official": "string"})
    labels["cmd_code"] = labels["cmd_code"].str.extract(r"(\d{1,6})", expand=False).str.zfill(6)
    labels["hs_desc_official"] = labels["hs_desc_official"].fillna("").str.strip()
    labels = labels[labels["cmd_code"].notna() & labels["hs_desc_official"].ne("")]
    if labels.empty:
        return {}

    # Prefer the most frequent official description for a code across HS vintages.
    counts = (
        labels.groupby(["cmd_code", "hs_desc_official"], dropna=False)
        .size()
        .reset_index(name="n")
        .sort_values(["cmd_code", "n", "hs_desc_official"], ascending=[True, False, True])
    )
    return counts.drop_duplicates("cmd_code").set_index("cmd_code")["hs_desc_official"].to_dict()


def query_granularity_shares(country_sample: str, year: int | None, line_count_mode: str, granularity: str) -> pd.DataFrame:
    source_glob = sample_aggregate_glob(country_sample)
    source_dir = source_glob.parent
    if not source_dir.exists() or not any(source_dir.glob("*.parquet")):
        raise FileNotFoundError(f"No aggregate parquet files found under {source_dir}")

    year_filter = "" if year is None else f"and year = {int(year)}"
    excluded_codes = ", ".join(f"'{code}'" for code in sorted(EXCLUDED_HS6_CODES))
    group_sql, group_name = group_expr(granularity)
    line_count_expr, line_count_col, _ = line_count_spec(line_count_mode, granularity)

    query = f"""
    with base as (
      select
        {group_sql} as group_code,
        substr(cmd_code, 1, 2) as hs2_code,
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
    grouped as (
      select
        group_code,
        min(hs2_code) as hs2_code,
        {HS_SECTION_CASE} as hs_section,
        {line_count_expr} as line_count,
        sum(trade_value) as export_value
      from base
      group by group_code, hs2_code, hs2
    ),
    product_values as (
      select
        group_code,
        cmd_code,
        sum(trade_value) as product_export_value
      from base
      group by group_code, cmd_code
    ),
    top_product as (
      select
        group_code,
        arg_max(cmd_code, product_export_value) as top_hs6_code,
        max(product_export_value) as top_hs6_export_value
      from product_values
      group by group_code
    ),
    totals as (
      select
        sum(line_count) as total_line_count,
        sum(export_value) as total_export_value
      from grouped
      where hs_section is not null
    )
    select
      group_code,
      hs2_code,
      hs_section,
      line_count as {line_count_col},
      export_value,
      line_count / total_line_count as line_share,
      export_value / total_export_value as export_value_share,
      export_value / nullif(line_count, 0) as export_value_per_line,
      top_hs6_code,
      top_hs6_export_value
    from grouped
    left join top_product using (group_code)
    cross join totals
    where hs_section is not null
    order by group_code
    """
    out = duckdb.connect().execute(query).fetchdf()
    if out.empty:
        raise RuntimeError(f"The {granularity} share query returned no rows.")

    label_map = load_hs6_labels()
    out["country_sample"] = country_sample
    out["year_scope"] = label_for_year(year)
    out["line_count_mode"] = line_count_mode
    out["granularity"] = granularity
    out["group_type"] = group_name
    out["hs_section"] = out["hs_section"].astype(int)
    out["hs2_code"] = out["hs2_code"].astype(str).str.zfill(2)
    out["hs2_label"] = out["hs2_code"].map(HS2_LABELS).fillna("Unlabeled HS2 chapter")
    out["hs_section_label"] = out["hs_section"].map(lambda section: SECTION_LABELS[int(section)][1])
    out["top_hs6_code"] = out["top_hs6_code"].astype(str).str.zfill(6)
    out["top_hs6_label"] = out["top_hs6_code"].map(label_map).fillna("")
    out["value_minus_line_share"] = out["export_value_share"] - out["line_share"]
    out["abs_share_gap"] = out["value_minus_line_share"].abs()
    out["value_to_line_share_ratio"] = out["export_value_share"] / out["line_share"].replace({0: pd.NA})

    if granularity == "hs6":
        out["hs6_label"] = out["group_code"].map(label_map).fillna("")
        label_cols = ["hs6_label"]
    else:
        label_cols = []

    order = [
        "country_sample",
        "year_scope",
        "line_count_mode",
        "granularity",
        "group_type",
        "group_code",
        "hs_section",
        "hs_section_label",
        "hs2_code",
        "hs2_label",
        *label_cols,
        line_count_col,
        "export_value",
        "line_share",
        "export_value_share",
        "value_minus_line_share",
        "abs_share_gap",
        "value_to_line_share_ratio",
        "export_value_per_line",
        "top_hs6_code",
        "top_hs6_label",
        "top_hs6_export_value",
    ]
    return out[order]


def labels_to_draw(df: pd.DataFrame, granularity: str, label_top_n: int) -> pd.DataFrame:
    if granularity == "hs2":
        return df
    if label_top_n <= 0:
        return df.iloc[0:0]
    by_value = df.nlargest(label_top_n, "export_value_share")
    by_gap = df.nlargest(max(5, label_top_n // 2), "abs_share_gap")
    return pd.concat([by_value, by_gap]).drop_duplicates("group_code")


def plot_granularity_shares(
    df: pd.DataFrame,
    output_path: Path,
    year: int | None,
    line_count_mode: str,
    granularity: str,
    label_top_n: int,
) -> None:
    fig, ax = plt.subplots(figsize=(8.6, 6.4))
    _, line_count_col, line_text = line_count_spec(line_count_mode, granularity)
    max_axis = max(float(df["line_share"].max()), float(df["export_value_share"].max())) * 1.10
    marker_size = 40 if granularity == "hs2" else 13
    regular = df[df["hs_section"] != 16]
    machinery = df[df["hs_section"] == 16]

    ax.scatter(regular["line_share"], regular["export_value_share"], color="#174a73", s=marker_size, alpha=0.78, zorder=3)
    if not machinery.empty:
        ax.scatter(
            machinery["line_share"],
            machinery["export_value_share"],
            color="#b8322a",
            s=marker_size * 1.35,
            alpha=0.85,
            zorder=4,
            label="HS section 16",
        )

    ax.plot([0, max_axis], [0, max_axis], color="#d62728", linewidth=1.6, zorder=2)

    for row in labels_to_draw(df, granularity, label_top_n).itertuples(index=False):
        ax.annotate(
            str(row.group_code),
            (row.line_share, row.export_value_share),
            xytext=(2, 2),
            textcoords="offset points",
            fontsize=7 if granularity == "hs2" else 6,
        )

    year_text = "all available years" if year is None else str(year)
    ax.set_title(f"{granularity.upper()} shares in {df['country_sample'].iloc[0]} exports, {year_text}", pad=12)
    ax.set_xlabel(f"Share of export lines ({line_text})")
    ax.set_ylabel("Share of export value")
    ax.set_xlim(0, max_axis)
    ax.set_ylim(0, max_axis)
    ax.grid(axis="both", color="#d7dee2", linewidth=0.8, alpha=0.8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if not machinery.empty:
        ax.legend(frameon=False, loc="upper right")
    ax.text(
        0.01,
        -0.18,
        f"Source: project Comtrade aggregates. Exports only. HS6 999999 excluded before aggregation. Line count column: {line_count_col}.",
        transform=ax.transAxes,
        fontsize=8.5,
        ha="left",
        va="top",
    )
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def summarize_granularity(df: pd.DataFrame) -> dict[str, float | int | str]:
    line_count_col = line_count_column(df)
    return {
        "granularity": str(df["granularity"].iloc[0]),
        "groups": int(len(df)),
        "total_line_count": int(df[line_count_col].sum()),
        "total_export_value": float(df["export_value"].sum()),
        "half_l1_distance_value_vs_line": float(0.5 * df["abs_share_gap"].sum()),
        "max_positive_gap": float(df["value_minus_line_share"].max()),
        "max_negative_gap": float(df["value_minus_line_share"].min()),
        "largest_positive_gap_group": str(df.loc[df["value_minus_line_share"].idxmax(), "group_code"]),
        "largest_negative_gap_group": str(df.loc[df["value_minus_line_share"].idxmin(), "group_code"]),
    }


def summarize_sections(country_sample: str, year: int | None, line_count_mode: str) -> dict[str, float | int | str]:
    if line_count_mode == "native_codes":
        section_df = query_section_shares(country_sample, year, "unique_products").rename(columns={"hs_section": "group_code"})
        line_count_col = "distinct_hs_section_codes"
        section_df[line_count_col] = 1
        section_df["line_share"] = section_df[line_count_col] / section_df[line_count_col].sum()
        section_df["export_value_per_line"] = section_df["export_value"] / section_df[line_count_col]
    else:
        section_df = query_section_shares(country_sample, year, line_count_mode).rename(columns={"hs_section": "group_code"})
        line_count_col = line_count_column(section_df)
    section_df["value_minus_line_share"] = section_df["export_value_share"] - section_df["line_share"]
    section_df["abs_share_gap"] = section_df["value_minus_line_share"].abs()
    return {
        "granularity": "hs_section",
        "groups": int(len(section_df)),
        "total_line_count": int(section_df[line_count_col].sum()),
        "total_export_value": float(section_df["export_value"].sum()),
        "half_l1_distance_value_vs_line": float(0.5 * section_df["abs_share_gap"].sum()),
        "max_positive_gap": float(section_df["value_minus_line_share"].max()),
        "max_negative_gap": float(section_df["value_minus_line_share"].min()),
        "largest_positive_gap_group": str(int(section_df.loc[section_df["value_minus_line_share"].idxmax(), "group_code"])),
        "largest_negative_gap_group": str(int(section_df.loc[section_df["value_minus_line_share"].idxmin(), "group_code"])),
    }


def write_note(
    out_dir: Path,
    country_sample: str,
    year: int | None,
    line_count_mode: str,
    tables: dict[str, Path],
    figures: dict[str, Path],
    summary_path: Path,
    summary: pd.DataFrame,
) -> Path:
    note_path = out_dir / f"hs_granularity_line_value_shares_{country_sample}_{label_for_year(year)}_{line_count_mode}.md"
    summary_md = summary.to_markdown(index=False, floatfmt=".6f")
    content = f"""# HS Granularity Line-Value Diagnostic

This diagnostic compares each product group's share of export product lines with its share of export value.

## Construction

Sample: `{country_sample}`. Flow: exports. Year: `{label_for_year(year)}`.

Unit before aggregation: reporter-year-HS6 product export value from the project Comtrade file aggregates.

Formula:

`line_share_g = line_count_g / sum_g line_count_g`

`value_share_g = export_value_g / sum_g export_value_g`

`half_l1_distance = 0.5 * sum_g abs(value_share_g - line_share_g)`

In plain English, the distance is 0 if export value is spread across groups in exactly the same proportions as product lines. Larger values mean export value is more concentrated in particular groups than the product code count would suggest.

For product-level work, HS6 `999999` is excluded before aggregation. The line-count mode for this run is `{line_count_mode}`. In `native_codes` mode, each active HS2 chapter, HS4 heading, or HS6 product receives one line-count unit at its own level; HS2/HS4 are not weighted by how many HS6 lines sit underneath them.

## Closeness Summary

{summary_md}

## Outputs

- HS2 figure: `{figures['hs2'].relative_to(ROOT)}`
- HS4 figure: `{figures['hs4'].relative_to(ROOT)}`
- HS2 raw table: `{tables['hs2'].relative_to(ROOT)}`
- HS4 raw table: `{tables['hs4'].relative_to(ROOT)}`
- HS6 raw table: `{tables['hs6'].relative_to(ROOT)}`
- Granularity summary: `{summary_path.relative_to(ROOT)}`

HS2 and HS4 tables include an HS2 chapter label and HS section label. HS4 tables also include the top HS6 product by value within each HS4 heading as a plain-English guide. HS6 tables include official product descriptions where available in the local mapping file.
"""
    note_path.write_text(content, encoding="utf-8")
    return note_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country-sample", choices=COUNTRY_SAMPLE_CHOICES, default="rd2_countries")
    parser.add_argument("--year", type=int, default=2021, help="Restrict to one year. Default is 2021.")
    parser.add_argument(
        "--line-count-mode",
        choices=("unique_products", "active_country_year_products", "native_codes"),
        default="unique_products",
        help="Use distinct HS6 products, active reporter-year-HS6 observations, or native HS2/HS4/HS6 codes as the x-axis denominator.",
    )
    parser.add_argument("--label-top-n", type=int, default=30, help="For HS4, label this many high-value/outlier points.")
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = args.output_dir or sample_result_dir(args.country_sample)
    out_dir.mkdir(parents=True, exist_ok=True)
    scope = label_for_year(args.year)
    stem = f"line_value_shares_{args.country_sample}_{scope}_{args.line_count_mode}"

    dfs: dict[str, pd.DataFrame] = {}
    tables: dict[str, Path] = {}
    figures: dict[str, Path] = {}
    for granularity in ("hs2", "hs4", "hs6"):
        df = query_granularity_shares(args.country_sample, args.year, args.line_count_mode, granularity)
        dfs[granularity] = df
        table_path = out_dir / f"{granularity}_{stem}.csv"
        df.to_csv(table_path, index=False)
        tables[granularity] = table_path
        if granularity in {"hs2", "hs4"}:
            figure_path = out_dir / f"{granularity}_{stem}.png"
            plot_granularity_shares(df, figure_path, args.year, args.line_count_mode, granularity, args.label_top_n)
            figures[granularity] = figure_path

    summary_rows = [summarize_sections(args.country_sample, args.year, args.line_count_mode)]
    summary_rows.extend(summarize_granularity(dfs[granularity]) for granularity in ("hs2", "hs4", "hs6"))
    summary = pd.DataFrame(summary_rows)
    summary_path = out_dir / f"granularity_summary_{args.country_sample}_{scope}_{args.line_count_mode}.csv"
    summary.to_csv(summary_path, index=False)
    note_path = write_note(out_dir, args.country_sample, args.year, args.line_count_mode, tables, figures, summary_path, summary)

    print(f"Wrote {figures['hs2']}")
    print(f"Wrote {figures['hs4']}")
    print(f"Wrote {tables['hs2']}")
    print(f"Wrote {tables['hs4']}")
    print(f"Wrote {tables['hs6']}")
    print(f"Wrote {summary_path}")
    print(f"Wrote {note_path}")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
