#!/usr/bin/env python3
"""Create Exercise 3 HS6 share histograms by import bin."""

from __future__ import annotations

import argparse
import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "data/processed/exercise_11_product_export_linkage_panel.parquet"
MAPPING = ROOT / "data/processed/exercise_03_bec5_mapping_approved.csv"
TABLE_OUT = ROOT / "results/exercise_03_tables/import_bin_goods_country_share_2024.csv"
FIGURE_DIR = ROOT / "results/exercise_03_figures"

IMPORT_BINS = {
    "energy": "Energy",
    "intermediates": "Intermediates",
    "capital_goods": "Capital goods",
    "final_consumption": "Final consumption",
}

SHORT_NAMES = {
    "151110": "Crude palm oil",
    "260112": "Iron ore concentrates",
    "270111": "Anthracite coal",
    "270112": "Bituminous coal",
    "270119": "Coal",
    "270900": "Crude petroleum",
    "271012": "Light petroleum oils",
    "271019": "Refined petroleum oils",
    "271111": "Liquefied natural gas",
    "271112": "Propane",
    "271113": "Butanes",
    "271121": "Natural gas, gaseous",
    "290243": "p-Xylene",
    "300490": "Medicaments",
    "040690": "Cheese",
    "190590": "Bread, pastry, biscuits",
    "210690": "Food preparations n.e.c.",
    "220421": "Wine",
    "230910": "Dog/cat food",
    "330499": "Beauty/skin preparations",
    "610910": "Cotton T-shirts",
    "640399": "Leather footwear",
    "710231": "Unworked non-industrial diamonds",
    "710239": "Other non-industrial diamonds",
    "710812": "Unwrought gold",
    "710692": "Semi-manufactured silver",
    "711319": "Precious-metal jewellery",
    "847130": "Portable computers/laptops",
    "847150": "Processing units/servers",
    "850440": "Static converters",
    "850760": "Lithium-ion batteries",
    "851713": "Smartphones",
    "851762": "Network/communication apparatus",
    "851779": "Telecom apparatus parts",
    "852872": "Television receivers",
    "854143": "Photovoltaic cells/modules",
    "854231": "Processor/controller integrated circuits",
    "854232": "Memory integrated circuits",
    "854239": "Other integrated circuits",
    "870321": "Petrol cars, <=1000cc",
    "870322": "Petrol cars, 1000-1500cc",
    "870323": "Petrol cars, 1500-3000cc",
    "870324": "Petrol cars, >3000cc",
    "870332": "Diesel cars, 1500-2500cc",
    "870340": "Hybrid petrol-electric cars",
    "870360": "Plug-in hybrid petrol cars",
    "870380": "Electric vehicles",
    "880240": "Large aircraft",
    "950300": "Toys",
}


def normalize_code(value: object) -> str:
    text = "" if value is None else str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits.zfill(6) if digits else text


def short_name(row: pd.Series) -> str:
    code = normalize_code(row["cmd_code"])
    if code in SHORT_NAMES:
        return SHORT_NAMES[code]
    desc = str(row.get("product_description", "")).strip()
    return desc if len(desc) <= 72 else desc[:69].rstrip() + "..."


def load_descriptions() -> pd.DataFrame:
    mapping = pd.read_csv(MAPPING, dtype={"cmd_code": str, "classification_code": str})
    mapping["cmd_code"] = mapping["cmd_code"].map(normalize_code)
    mapping["product_description"] = mapping["hs_desc_official"].fillna("").astype(str).str.strip()
    h6 = mapping[mapping["classification_code"].eq("H6")][["cmd_code", "product_description"]]
    fallback = mapping[["cmd_code", "product_description"]]
    descriptions = pd.concat([fallback, h6], ignore_index=True)
    descriptions = descriptions[descriptions["product_description"].ne("")]
    return descriptions.drop_duplicates("cmd_code", keep="last")


def build_table(year: int) -> pd.DataFrame:
    columns = ["iso3", "country", "year", "cmd_code", "import_bin", "import_value", "total_imports"]
    panel = pd.read_parquet(PANEL, columns=columns)
    work = panel[(panel["year"].eq(year)) & (panel["import_bin"].isin(IMPORT_BINS))].copy()
    if work.empty:
        raise RuntimeError(f"No mapped import-bin rows found for {year}.")

    work["cmd_code"] = work["cmd_code"].map(normalize_code)
    reporter_count = work["iso3"].nunique()
    bin_totals = (
        work.groupby(["iso3", "country", "import_bin"], as_index=False)["import_value"]
        .sum()
        .rename(columns={"import_value": "bin_imports"})
    )
    work = work.merge(bin_totals, on=["iso3", "country", "import_bin"], how="left")
    work["share_of_total_imports"] = work["import_value"] / work["total_imports"]
    work["share_of_bin_imports"] = work["import_value"] / work["bin_imports"]

    country_totals = work[["iso3", "total_imports"]].drop_duplicates("iso3")
    total_imports_sample = country_totals["total_imports"].sum()
    sample_bin_totals = bin_totals.groupby("import_bin")["bin_imports"].sum()

    out = (
        work.groupby(["import_bin", "cmd_code"], as_index=False)
        .agg(
            countries_with_imports=("iso3", "nunique"),
            pooled_import_value_usd=("import_value", "sum"),
            summed_total_import_share=("share_of_total_imports", "sum"),
            summed_bin_import_share=("share_of_bin_imports", "sum"),
        )
        .merge(load_descriptions(), on="cmd_code", how="left")
    )
    out.insert(0, "year", year)
    out["import_bin_label"] = out["import_bin"].map(IMPORT_BINS)
    out["reporter_count"] = reporter_count
    out["product_description"] = out["product_description"].fillna("")
    out["summed_total_import_share_pct_points"] = 100 * out["summed_total_import_share"]
    out["summed_bin_import_share_pct_points"] = 100 * out["summed_bin_import_share"]
    out["avg_total_import_share"] = out["summed_total_import_share"] / reporter_count
    out["avg_bin_import_share"] = out["summed_bin_import_share"] / reporter_count
    out["pooled_share_of_total_imports"] = out["pooled_import_value_usd"] / total_imports_sample
    out["pooled_share_of_bin_imports"] = out.apply(
        lambda row: row["pooled_import_value_usd"] / sample_bin_totals.loc[row["import_bin"]],
        axis=1,
    )
    out["display_name"] = out.apply(short_name, axis=1)

    columns = [
        "year",
        "import_bin",
        "import_bin_label",
        "cmd_code",
        "display_name",
        "product_description",
        "countries_with_imports",
        "reporter_count",
        "pooled_import_value_usd",
        "summed_total_import_share",
        "summed_total_import_share_pct_points",
        "avg_total_import_share",
        "summed_bin_import_share",
        "summed_bin_import_share_pct_points",
        "avg_bin_import_share",
        "pooled_share_of_total_imports",
        "pooled_share_of_bin_imports",
    ]
    return out[columns].sort_values(["import_bin", "summed_total_import_share"], ascending=[True, False])


def top_box_lines(frame: pd.DataFrame, metric: str, count: int = 10) -> str:
    lines = []
    for rank, row in enumerate(frame.head(count).itertuples(index=False), start=1):
        value = getattr(row, metric)
        lines.append(f"{rank}. {row.cmd_code} {row.display_name}: {value:.1f} pp")
    return "\n".join(lines)


def plot_ranked(frame: pd.DataFrame, metric: str, title: str, output: Path, color: str) -> None:
    work = frame.sort_values(metric, ascending=False).reset_index(drop=True)
    x = np.arange(1, len(work) + 1)
    y = work[metric].to_numpy()

    fig, ax = plt.subplots(figsize=(16, 7))
    ax.bar(x, y, width=1.0, color=color, edgecolor=color, linewidth=0)
    ax.set_title(title)
    ax.set_xlabel("HS6 goods in bin, sorted by contribution")
    ax.set_ylabel("Summed country share, percentage points")
    ax.set_xlim(0, len(work) + 1)
    ax.grid(axis="y", color="#e5e7eb", linewidth=0.8)
    ax.set_axisbelow(True)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)

    top_text = top_box_lines(work, metric)
    ax.text(
        0.985,
        0.965,
        "Top products\n" + top_text,
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=9,
        linespacing=1.35,
        bbox={"boxstyle": "round,pad=0.45", "facecolor": "white", "edgecolor": "#d1d5db", "alpha": 0.96},
    )
    note = (
        "All HS6 goods in this bin are included as bars. "
        "A height of 100 percentage points equals one full country-share after summing across countries."
    )
    fig.text(0.01, 0.01, textwrap.fill(note, 145), ha="left", va="bottom", fontsize=9, color="#667085")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=200)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2024)
    args = parser.parse_args()

    table = build_table(args.year)
    TABLE_OUT.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(TABLE_OUT, index=False)
    for import_bin, label in IMPORT_BINS.items():
        bin_table = table[table["import_bin"].eq(import_bin)].copy()
        plot_ranked(
            bin_table,
            "summed_total_import_share_pct_points",
            f"{label} goods by summed share of all imports ({args.year})",
            FIGURE_DIR / f"{import_bin}_goods_sum_total_import_share_{args.year}.png",
            "#2563eb",
        )
        plot_ranked(
            bin_table,
            "summed_bin_import_share_pct_points",
            f"{label} goods by summed share of {label.lower()} imports ({args.year})",
            FIGURE_DIR / f"{import_bin}_goods_sum_bin_import_share_{args.year}.png",
            "#0f766e",
        )
    print(f"Wrote {TABLE_OUT}")
    for import_bin in IMPORT_BINS:
        print(f"Wrote {FIGURE_DIR / f'{import_bin}_goods_sum_total_import_share_{args.year}.png'}")
        print(f"Wrote {FIGURE_DIR / f'{import_bin}_goods_sum_bin_import_share_{args.year}.png'}")


if __name__ == "__main__":
    main()
