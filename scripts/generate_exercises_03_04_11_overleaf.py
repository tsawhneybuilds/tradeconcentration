#!/usr/bin/env python3
"""
Generate an Overleaf-ready report for Exercises 3, 4, and 11.
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.lines import Line2D
from matplotlib.ticker import FixedLocator, FuncFormatter, PercentFormatter


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
OUT = RESULTS / "overleaf_exercises_03_04_11"
FIGURES = OUT / "figures"
TABLES = OUT / "tables"


BIN_ORDER = ["energy", "intermediates", "capital_goods", "final_consumption", "unmapped_or_ambiguous"]
BIN_LABELS = {
    "energy": "Energy",
    "intermediates": "Intermediates",
    "capital_goods": "Capital goods",
    "final_consumption": "Final consumption",
    "unmapped_or_ambiguous": "Unmapped/ambiguous",
}

PRODUCT_LABEL_OVERRIDES = {
    "151110": "Crude palm oil",
    "270119": "Other coal",
    "270900": "Crude petroleum oil",
    "271019": "Refined petroleum oils",
    "271111": "Liquefied natural gas",
    "271112": "Liquefied propane",
    "271113": "Liquefied butanes",
    "710231": "Unworked non-industrial diamonds",
    "710239": "Other non-industrial diamonds",
    "710692": "Semi-manufactured silver",
    "710812": "Unwrought non-monetary gold",
    "847130": "Portable computers/laptops",
    "851779": "Communication apparatus parts",
    "854231": "Processor/controller chips",
    "880240": "Large aircraft",
}


def money(value: float) -> str:
    if not np.isfinite(value):
        return "--"
    for suffix, scale in [("T", 1e12), ("B", 1e9), ("M", 1e6)]:
        if abs(value) >= scale:
            return f"\\${value / scale:,.1f}{suffix}"
    return f"\\${value:,.0f}"


def pct(value: float) -> str:
    if not np.isfinite(value):
        return "--"
    return f"{100 * value:.1f}\\%"


def compact_percent_tick(value: float, _pos: int | None = None) -> str:
    if value <= 0 or not np.isfinite(value):
        return ""
    percentage = value * 100
    if percentage >= 10:
        return f"{percentage:.0f}%"
    if percentage >= 1:
        text = f"{percentage:.1f}"
    elif percentage >= 0.1:
        text = f"{percentage:.2f}"
    else:
        text = f"{percentage:.3f}"
    return f"{text.rstrip('0').rstrip('.')}%"


def strip_hs_code(description: str) -> str:
    return description.split(" - ", 1)[1] if " - " in description else description


def load_hs_product_descriptions() -> dict[str, str]:
    lookup: dict[str, str] = {}
    for classification in ["H0", "H1", "H2", "H3", "H4", "H5", "H6"]:
        path = ROOT / "data/raw/classifications" / f"{classification}.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        for row in data.get("results", []):
            code = str(row.get("id", "")).zfill(6)
            text = str(row.get("text", "")).strip()
            if code.isdigit() and len(code) == 6 and text:
                lookup[code] = strip_hs_code(text)
    return lookup


def product_label(code: object, descriptions: dict[str, str], width: int = 34, include_code: bool = True) -> str:
    hs6 = str(code).zfill(6)
    label = PRODUCT_LABEL_OVERRIDES.get(hs6, descriptions.get(hs6, hs6))
    label = " ".join(label.replace(";", ":").split())
    label = textwrap.fill(label, width=width)
    return f"{label}\nHS {hs6}" if include_code else label


def tex_escape(value: object) -> str:
    text = str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def savefig(name: str) -> str:
    FIGURES.mkdir(parents=True, exist_ok=True)
    path = FIGURES / name
    plt.tight_layout()
    plt.savefig(path, dpi=220, bbox_inches="tight")
    plt.close()
    return f"figures/{name}"


def latest_per_country(df: pd.DataFrame, key_cols: list[str]) -> pd.DataFrame:
    max_year = df.groupby(key_cols, as_index=False)["year"].max()
    return df.merge(max_year, on=[*key_cols, "year"], how="inner")


def plot_exercise_3(ex3: pd.DataFrame, ex3_decomp: pd.DataFrame) -> dict[str, str]:
    figs: dict[str, str] = {}
    plot_df = ex3[ex3["import_bin"].isin(BIN_ORDER[:4])].copy()
    plot_df["bin_label"] = plot_df["import_bin"].map(BIN_LABELS)
    decomp_df = ex3_decomp[ex3_decomp["import_bin"].isin(BIN_ORDER[:4])].copy()
    decomp_df["bin_label"] = decomp_df["import_bin"].map(BIN_LABELS)

    median = plot_df.groupby(["year", "import_bin", "bin_label"], as_index=False)["product_gini"].median()
    median_top1 = plot_df.groupby(["year", "import_bin", "bin_label"], as_index=False)["top_1_product_share"].median()
    median_value_share = decomp_df.groupby(["year", "import_bin", "bin_label"], as_index=False)["import_value_share"].median()
    median_top10_contribution = decomp_df.groupby(
        ["year", "import_bin", "bin_label"], as_index=False
    )["top_10_product_share_contribution"].median()
    palette = {
        "Energy": "#8c4f2b",
        "Intermediates": "#2f5d62",
        "Capital goods": "#6b7fbd",
        "Final consumption": "#b7791f",
    }
    plt.figure(figsize=(12, 6))
    sns.lineplot(
        data=median,
        x="year",
        y="product_gini",
        hue="bin_label",
        hue_order=[BIN_LABELS[x] for x in BIN_ORDER[:4]],
        palette=palette,
        linewidth=2.3,
    )
    plt.title("Exercise 3: Median Product Gini by Import Bin Over Time")
    plt.ylabel("Median product Gini across countries")
    plt.xlabel("Year")
    plt.ylim(0.55, 1.0)
    plt.legend(title="", frameon=False, ncol=2)
    figs["ex3_bin_gini_over_years"] = savefig("ex3_bin_gini_over_years.png")

    plt.figure(figsize=(12, 6))
    sns.lineplot(
        data=median_top1,
        x="year",
        y="top_1_product_share",
        hue="bin_label",
        hue_order=[BIN_LABELS[x] for x in BIN_ORDER[:4]],
        palette=palette,
        linewidth=2.3,
    )
    plt.title("Exercise 3: Median Top-1 Product Share by Import Bin Over Time")
    plt.ylabel("Median top-1 product share across countries")
    plt.xlabel("Year")
    plt.ylim(0, 0.75)
    plt.legend(title="", frameon=False, ncol=2)
    figs["ex3_bin_top1_over_years"] = savefig("ex3_bin_top1_over_years.png")

    plt.figure(figsize=(12, 6))
    sns.lineplot(
        data=median_value_share,
        x="year",
        y="import_value_share",
        hue="bin_label",
        hue_order=[BIN_LABELS[x] for x in BIN_ORDER[:4]],
        palette=palette,
        linewidth=2.3,
    )
    plt.title("Exercise 3: Median Import Value Share by Bin Over Time")
    plt.ylabel("Median import value share across countries")
    plt.xlabel("Year")
    plt.ylim(0, 0.65)
    plt.legend(title="", frameon=False, ncol=2)
    figs["ex3_bin_value_share_over_years"] = savefig("ex3_bin_value_share_over_years.png")

    india_top10_contribution = decomp_df[decomp_df["iso3"] == "IND"].copy()
    fig, ax = plt.subplots(figsize=(12, 6))
    top10_max = 0.18
    for import_bin in BIN_ORDER[:4]:
        label = BIN_LABELS[import_bin]
        med = median_top10_contribution[median_top10_contribution["import_bin"] == import_bin].sort_values("year")
        ind = india_top10_contribution[india_top10_contribution["import_bin"] == import_bin].sort_values("year")
        ax.plot(
            med["year"],
            med["top_10_product_share_contribution"],
            color=palette[label],
            linewidth=2.4,
            linestyle="-",
        )
        if not ind.empty:
            ax.plot(
                ind["year"],
                ind["top_10_product_share_contribution"],
                color=palette[label],
                linewidth=2.2,
                linestyle="--",
            )
            top10_max = max(top10_max, float(ind["top_10_product_share_contribution"].max()))
        if not med.empty:
            top10_max = max(top10_max, float(med["top_10_product_share_contribution"].max()))
    ax.set_title("Exercise 3: Top-10 Import Share Contribution by Bin")
    ax.set_ylabel("Contribution to aggregate top-10 product share")
    ax.set_xlabel("Year")
    ax.set_ylim(0, min(0.45, top10_max * 1.12))
    bin_handles = [Line2D([0], [0], color=palette[BIN_LABELS[bin_name]], linewidth=2.4, label=BIN_LABELS[bin_name]) for bin_name in BIN_ORDER[:4]]
    style_handles = [
        Line2D([0], [0], color="#111827", linewidth=2.4, linestyle="-", label="Country median"),
        Line2D([0], [0], color="#111827", linewidth=2.2, linestyle="--", label="India"),
    ]
    bin_legend = ax.legend(handles=bin_handles, title="Import bin", frameon=False, ncol=2, loc="upper left")
    ax.add_artist(bin_legend)
    ax.legend(handles=style_handles, title="Line", frameon=False, loc="upper right")
    figs["ex3_bin_top10_contribution_over_years"] = savefig("ex3_bin_top10_contribution_over_years.png")

    india = plot_df[plot_df["iso3"] == "IND"].copy()
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=True, sharey=True)
    for ax, import_bin in zip(axes.flat, BIN_ORDER[:4], strict=False):
        label = BIN_LABELS[import_bin]
        med = median[median["import_bin"] == import_bin]
        ind = india[india["import_bin"] == import_bin]
        ax.plot(med["year"], med["product_gini"], color="#2f5d62", linewidth=2.2, label="Country median")
        ax.plot(ind["year"], ind["product_gini"], color="#c43b3b", linewidth=2.0, linestyle="--", label="India")
        ax.set_title(label)
        ax.set_ylim(0.25, 1.0)
        ax.grid(alpha=0.25)
    axes.flat[0].legend(frameon=False, loc="lower right")
    fig.supxlabel("Year")
    fig.supylabel("Product Gini within import bin")
    figs["ex3_gini_time_by_bin"] = savefig("ex3_gini_time_by_bin.png")

    latest = latest_per_country(plot_df, ["iso3", "import_bin"])
    india_latest = latest[latest["iso3"] == "IND"]
    plt.figure(figsize=(11, 6))
    ax = sns.boxplot(data=latest, x="bin_label", y="product_gini", order=[BIN_LABELS[x] for x in BIN_ORDER[:4]], color="#d6e4e5")
    sns.stripplot(data=latest, x="bin_label", y="product_gini", order=[BIN_LABELS[x] for x in BIN_ORDER[:4]], color="#475569", alpha=0.45, jitter=0.22)
    sns.stripplot(data=india_latest, x="bin_label", y="product_gini", order=[BIN_LABELS[x] for x in BIN_ORDER[:4]], color="#c43b3b", size=9, jitter=False, ax=ax)
    ax.set_xlabel("")
    ax.set_ylabel("Latest available product Gini")
    ax.set_title("Exercise 3: Latest Import-Bin Concentration Across Countries (India highlighted)")
    figs["ex3_latest_bin_distribution"] = savefig("ex3_latest_bin_distribution.png")

    common_year = int(plot_df.loc[plot_df["iso3"].eq("IND"), "year"].max())
    common = plot_df[plot_df["year"] == common_year].copy()
    india_common = common[common["iso3"] == "IND"]
    plt.figure(figsize=(11, 6))
    ax = sns.boxplot(data=common, x="bin_label", y="product_gini", order=[BIN_LABELS[x] for x in BIN_ORDER[:4]], color="#e7ecef")
    sns.stripplot(data=common, x="bin_label", y="product_gini", order=[BIN_LABELS[x] for x in BIN_ORDER[:4]], color="#475569", alpha=0.5, jitter=0.22)
    sns.stripplot(data=india_common, x="bin_label", y="product_gini", order=[BIN_LABELS[x] for x in BIN_ORDER[:4]], color="#c43b3b", size=9, jitter=False, ax=ax)
    ax.set_xlabel("")
    ax.set_ylabel(f"{common_year} product Gini")
    ax.set_title(f"Exercise 3: Common-Year Import-Bin Concentration ({common_year}, India highlighted)")
    figs["ex3_common_year_bin_distribution"] = savefig("ex3_common_year_bin_distribution.png")

    decomp_latest = latest_per_country(decomp_df, ["iso3", "import_bin"])
    india_decomp_latest = decomp_latest[decomp_latest["iso3"] == "IND"]
    plt.figure(figsize=(11, 6))
    ax = sns.boxplot(
        data=decomp_latest,
        x="bin_label",
        y="product_gini_reduction_when_excluded",
        order=[BIN_LABELS[x] for x in BIN_ORDER[:4]],
        color="#e7ecef",
    )
    sns.stripplot(
        data=decomp_latest,
        x="bin_label",
        y="product_gini_reduction_when_excluded",
        order=[BIN_LABELS[x] for x in BIN_ORDER[:4]],
        color="#475569",
        alpha=0.5,
        jitter=0.22,
    )
    sns.stripplot(
        data=india_decomp_latest,
        x="bin_label",
        y="product_gini_reduction_when_excluded",
        order=[BIN_LABELS[x] for x in BIN_ORDER[:4]],
        color="#c43b3b",
        size=9,
        jitter=False,
        ax=ax,
    )
    ax.axhline(0, color="#111827", linewidth=1)
    ax.set_xlabel("")
    ax.set_ylabel("Aggregate Gini reduction when bin is excluded")
    ax.set_title("Exercise 3: Leave-One-Bin-Out Contribution to Aggregate Import Concentration")
    figs["ex3_leave_one_out_gini_reduction"] = savefig("ex3_leave_one_out_gini_reduction.png")

    india_share = ex3[ex3["iso3"] == "IND"].copy()
    totals = india_share.groupby("year", as_index=False)["total_imports_in_bin"].sum().rename(columns={"total_imports_in_bin": "year_total"})
    india_share = india_share.merge(totals, on="year")
    india_share["share"] = india_share["total_imports_in_bin"] / india_share["year_total"]
    pivot = india_share.pivot_table(index="year", columns="import_bin", values="share", fill_value=0)
    pivot = pivot[[col for col in BIN_ORDER if col in pivot.columns]]
    plt.figure(figsize=(12, 6))
    colors = ["#8c4f2b", "#2f5d62", "#6b7fbd", "#b7791f", "#8b8b8b"]
    plt.stackplot(pivot.index, [pivot[col] for col in pivot.columns], labels=[BIN_LABELS[col] for col in pivot.columns], colors=colors[: len(pivot.columns)], alpha=0.9)
    plt.legend(frameon=False, ncol=3, loc="upper left")
    plt.title("Exercise 3: India Import Value Shares by BEC Bin")
    plt.ylabel("Share of import value")
    plt.xlabel("Year")
    plt.ylim(0, 1)
    figs["ex3_india_import_bin_shares"] = savefig("ex3_india_import_bin_shares.png")
    return figs


def exercise_4_summary(ex4: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for key, group in ex4.groupby(["country", "iso3", "reporter_code", "year"], sort=True):
        country, iso3, reporter_code, year = key
        weights = group["total_product_imports"].to_numpy(dtype=float)
        total = weights.sum()
        rows.append(
            {
                "country": country,
                "iso3": iso3,
                "reporter_code": int(reporter_code),
                "year": int(year),
                "total_imports": total,
                "import_products": int(group["cmd_code"].nunique()),
                "weighted_mean_top_supplier_share": float(np.average(group["top_supplier_share"], weights=weights)) if total else np.nan,
                "weighted_mean_source_hhi": float(np.average(group["source_hhi"], weights=weights)) if total else np.nan,
                "median_top_supplier_share": float(group["top_supplier_share"].median()),
                "share_products_top_supplier_ge_75": float((group["top_supplier_share"] >= 0.75).mean()),
                "import_value_share_products_top_supplier_ge_75": float(group.loc[group["top_supplier_share"] >= 0.75, "total_product_imports"].sum() / total) if total else np.nan,
            }
        )
    return pd.DataFrame(rows)


def plot_exercise_4(ex4: pd.DataFrame, summary: pd.DataFrame) -> dict[str, str]:
    figs: dict[str, str] = {}
    product_descriptions = load_hs_product_descriptions()
    median = summary.groupby("year", as_index=False).agg(
        median_weighted_top_supplier_share=("weighted_mean_top_supplier_share", "median"),
        median_high_dominance_value_share=("import_value_share_products_top_supplier_ge_75", "median"),
    )
    india = summary[summary["iso3"] == "IND"].copy()

    plt.figure(figsize=(12, 6))
    plt.plot(median["year"], median["median_weighted_top_supplier_share"], color="#2f5d62", linewidth=2.4, label="Country median")
    plt.plot(india["year"], india["weighted_mean_top_supplier_share"], color="#c43b3b", linewidth=2.2, linestyle="--", label="India")
    plt.title("Exercise 4: Weighted Mean Top-Supplier Share Over Time")
    plt.ylabel("Weighted mean top supplier share")
    plt.xlabel("Year")
    plt.ylim(0, 0.75)
    plt.legend(frameon=False)
    figs["ex4_supplier_dominance_time"] = savefig("ex4_supplier_dominance_time.png")

    plt.figure(figsize=(12, 6))
    plt.plot(median["year"], median["median_high_dominance_value_share"], color="#2f5d62", linewidth=2.4, label="Country median")
    plt.plot(india["year"], india["import_value_share_products_top_supplier_ge_75"], color="#c43b3b", linewidth=2.2, linestyle="--", label="India")
    plt.title("Exercise 4: Import Value in Products with Top Supplier >= 75%")
    plt.ylabel("Import value share")
    plt.xlabel("Year")
    plt.ylim(0, 0.35)
    plt.legend(frameon=False)
    figs["ex4_high_dominance_value_share_time"] = savefig("ex4_high_dominance_value_share_time.png")

    latest = latest_per_country(summary, ["iso3"]).sort_values("weighted_mean_top_supplier_share", ascending=False)
    latest["label"] = latest["iso3"] + " (" + latest["year"].astype(str) + ")"
    latest["highlight"] = np.where(latest["iso3"] == "IND", "India", "Comparator")
    plt.figure(figsize=(10, 11))
    colors = latest["highlight"].map({"India": "#c43b3b", "Comparator": "#6b7280"})
    plt.barh(latest["label"], latest["weighted_mean_top_supplier_share"], color=colors)
    plt.gca().invert_yaxis()
    plt.xlabel("Weighted mean top supplier share")
    plt.title("Exercise 4: Latest Supplier Dominance by Importer")
    figs["ex4_latest_country_dominance"] = savefig("ex4_latest_country_dominance.png")

    latest_products_all = latest_per_country(ex4, ["iso3"]).copy()
    latest_products_all["importer_total_imports"] = latest_products_all.groupby(["iso3", "year"])["total_product_imports"].transform("sum")
    latest_products_all["import_value_share"] = latest_products_all["total_product_imports"] / latest_products_all["importer_total_imports"]

    hist_products = latest_products_all[latest_products_all["top_supplier_share"].notna()].copy()
    plt.figure(figsize=(11, 6.5))
    ax = plt.gca()
    weights = np.ones(len(hist_products)) / len(hist_products) if len(hist_products) else None
    ax.hist(
        hist_products["top_supplier_share"],
        bins=np.linspace(0, 1, 21),
        weights=weights,
        color="#2f5d62",
        alpha=0.82,
        edgecolor="white",
        linewidth=0.8,
    )
    median_share = hist_products["top_supplier_share"].median()
    ax.axvline(0.75, color="#111827", linestyle="--", linewidth=1.4, label="75% threshold")
    ax.axvline(median_share, color="#c43b3b", linestyle="-", linewidth=1.6, label=f"Median: {median_share:.0%}")
    ax.xaxis.set_major_formatter(PercentFormatter(1.0))
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_xlim(0, 1)
    ax.set_xlabel("Top supplier share within importer-HS6 product")
    ax.set_ylabel("Share of importer-HS6 product rows")
    ax.set_title("Exercise 4: Distribution of Top-Supplier Shares Across Importer-HS6 Products")
    ax.legend(frameon=False)
    figs["ex4_top_supplier_share_histogram"] = savefig("ex4_top_supplier_share_histogram.png")

    latest_products = latest_products_all[latest_products_all["import_value_share"] >= 0.001].copy()
    latest_products["large_product"] = latest_products["import_value_share"] >= 0.01
    plt.figure(figsize=(11, 7))
    ax = plt.gca()
    background = latest_products[~latest_products["large_product"]]
    foreground = latest_products[latest_products["large_product"]]
    ax.scatter(
        background["import_value_share"],
        background["top_supplier_share"],
        s=9,
        color="#94a3b8",
        alpha=0.18,
        edgecolors="none",
        label="Other importer-HS6 products",
    )
    ax.scatter(
        foreground["import_value_share"],
        foreground["top_supplier_share"],
        s=42,
        color="#c43b3b",
        alpha=0.72,
        edgecolors="white",
        linewidth=0.4,
        label="At least 1% of importer imports",
    )
    if len(latest_products) >= 2:
        fit = np.polyfit(latest_products["import_value_share"], latest_products["top_supplier_share"], deg=1)
        x_grid = np.linspace(latest_products["import_value_share"].min(), latest_products["import_value_share"].max(), 200)
        y_hat = fit[0] * x_grid + fit[1]
        ax.plot(x_grid, y_hat, color="#111827", linewidth=2.2, label="OLS fit")
    ax.axhline(0.75, color="#111827", linestyle="--", linewidth=1.1, alpha=0.75)
    ax.text(latest_products["import_value_share"].quantile(0.02), 0.765, "75% top-supplier threshold", va="bottom", fontsize=8)
    ax.xaxis.set_major_formatter(PercentFormatter(1.0))
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_xlim(0, min(0.45, latest_products["import_value_share"].max() * 1.04))
    ax.set_ylim(0, 1.02)
    ax.set_xlabel("HS6 product share of importer total imports")
    ax.set_ylabel("Top supplier share within importer-HS6 product")
    ax.set_title("Exercise 4: Supplier Dominance vs Product Import-Value Share Across Importers")
    ax.legend(frameon=False, loc="upper left")
    figs["ex4_global_supplier_share_vs_product_value_share"] = savefig("ex4_global_supplier_share_vs_product_value_share.png")

    log_products = latest_products[
        (latest_products["import_value_share"] > 0) & (latest_products["top_supplier_share"] > 0)
    ].copy()
    plt.figure(figsize=(11, 7))
    ax = plt.gca()
    background = log_products[~log_products["large_product"]]
    foreground = log_products[log_products["large_product"]]
    ax.scatter(
        background["import_value_share"],
        background["top_supplier_share"],
        s=9,
        color="#94a3b8",
        alpha=0.18,
        edgecolors="none",
        label="Other importer-HS6 products",
    )
    ax.scatter(
        foreground["import_value_share"],
        foreground["top_supplier_share"],
        s=42,
        color="#c43b3b",
        alpha=0.72,
        edgecolors="white",
        linewidth=0.4,
        label="At least 1% of importer imports",
    )
    if len(log_products) >= 2:
        fit = np.polyfit(np.log10(log_products["import_value_share"]), np.log10(log_products["top_supplier_share"]), deg=1)
        x_grid = np.geomspace(log_products["import_value_share"].min(), log_products["import_value_share"].max(), 200)
        y_hat = np.power(10, fit[0] * np.log10(x_grid) + fit[1])
        ax.plot(x_grid, y_hat, color="#111827", linewidth=2.2, label="Log-log OLS fit")
    ax.axhline(0.75, color="#111827", linestyle="--", linewidth=1.1, alpha=0.75)
    ax.text(log_products["import_value_share"].quantile(0.03), 0.78, "75% top-supplier threshold", va="bottom", fontsize=8)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(log_products["import_value_share"].min() * 0.9, min(0.45, log_products["import_value_share"].max() * 1.08))
    ax.set_ylim(max(0.02, log_products["top_supplier_share"].min() * 0.9), 1.05)
    x_ticks = [tick for tick in [0.001, 0.003, 0.01, 0.03, 0.1, 0.3] if ax.get_xlim()[0] <= tick <= ax.get_xlim()[1]]
    y_ticks = [tick for tick in [0.02, 0.05, 0.1, 0.25, 0.5, 0.75, 1.0] if ax.get_ylim()[0] <= tick <= ax.get_ylim()[1]]
    ax.xaxis.set_major_locator(FixedLocator(x_ticks))
    ax.yaxis.set_major_locator(FixedLocator(y_ticks))
    ax.xaxis.set_major_formatter(FuncFormatter(compact_percent_tick))
    ax.yaxis.set_major_formatter(FuncFormatter(compact_percent_tick))
    ax.set_xlabel("HS6 product share of importer total imports, log scale")
    ax.set_ylabel("Top supplier share within importer-HS6 product, log scale")
    ax.set_title("Exercise 4: Supplier Dominance vs Product Import-Value Share Across Importers, Log-Log")
    ax.legend(frameon=False, loc="lower right")
    figs["ex4_global_supplier_share_vs_product_value_share_loglog"] = savefig("ex4_global_supplier_share_vs_product_value_share_loglog.png")

    india_year = int(ex4.loc[ex4["iso3"] == "IND", "year"].max())
    india_products = ex4[(ex4["iso3"] == "IND") & (ex4["year"] == india_year)].nlargest(15, "total_product_imports").copy()
    india_products["label"] = india_products.apply(
        lambda row: (
            f"{product_label(row.cmd_code, product_descriptions, width=34, include_code=False)}\n"
            f"HS {str(row.cmd_code).zfill(6)} | top: {row.top_supplier_iso3 or 'Unknown'}"
        ),
        axis=1,
    )
    plt.figure(figsize=(12.5, 9))
    cmap = plt.cm.viridis
    norm = plt.Normalize(0, 1)
    plt.barh(india_products["label"], india_products["total_product_imports"] / 1e9, color=cmap(norm(india_products["top_supplier_share"])))
    plt.gca().invert_yaxis()
    plt.yticks(fontsize=8)
    plt.xlabel("India import value, USD billions")
    plt.title(f"Exercise 4: India's Largest Imported HS6 Products and Top Supplier ({india_year})")
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = plt.colorbar(sm, ax=plt.gca())
    cbar.set_label("Top supplier share")
    figs["ex4_india_top_products"] = savefig("ex4_india_top_products.png")

    india_all = ex4[(ex4["iso3"] == "IND") & (ex4["year"] == india_year)].copy()
    india_all["import_value_share"] = india_all["total_product_imports"] / india_all["total_product_imports"].sum()
    india_all["is_top_product"] = india_all["total_product_imports"].rank(method="first", ascending=False) <= 15
    plt.figure(figsize=(12.5, 7.8))
    ax = plt.gca()
    background = india_all[~india_all["is_top_product"]]
    foreground = india_all[india_all["is_top_product"]].copy()
    ax.scatter(
        background["top_supplier_share"],
        background["import_value_share"],
        s=18,
        color="#94a3b8",
        alpha=0.28,
        edgecolors="none",
        label="Other HS6 products",
    )
    ax.scatter(
        foreground["top_supplier_share"],
        foreground["import_value_share"],
        s=70,
        color="#c43b3b",
        alpha=0.86,
        edgecolors="white",
        linewidth=0.6,
        label="Top 15 by import value",
    )
    annotation_offsets = {
        "270900": (8, 20),
        "710812": (-55, 20),
        "270119": (-42, -5),
        "271111": (35, 6),
        "854231": (8, -24),
        "851779": (10, 16),
        "710231": (40, -6),
        "880240": (-46, 4),
    }
    for row in foreground.nlargest(8, "import_value_share").itertuples(index=False):
        hs6 = str(row.cmd_code).zfill(6)
        label = product_label(hs6, product_descriptions, width=18, include_code=False)
        ax.annotate(
            f"{label}\n({row.top_supplier_iso3})",
            (row.top_supplier_share, row.import_value_share),
            xytext=annotation_offsets.get(hs6, (5, 4)),
            textcoords="offset points",
            arrowprops={"arrowstyle": "-", "color": "#6b7280", "linewidth": 0.6, "alpha": 0.8},
            fontsize=7,
            color="#111827",
        )
    ax.axvline(0.75, color="#111827", linestyle="--", linewidth=1.1, alpha=0.75)
    ax.text(0.755, india_all["import_value_share"].max() * 0.5, "75% top-supplier threshold", rotation=90, va="center", fontsize=8)
    ax.set_yscale("log")
    ax.set_ylim(max(india_all["import_value_share"].min() * 0.9, 1e-6), india_all["import_value_share"].max() * 1.9)
    ax.xaxis.set_major_formatter(PercentFormatter(1.0))
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_xlim(0, 1.02)
    ax.set_xlabel("Top supplier share within HS6 product")
    ax.set_ylabel("HS6 product share of India's total import value, log scale")
    ax.set_title(f"Exercise 4: Supplier Dominance vs Product Import-Value Share, India ({india_year})", pad=22)
    ax.legend(frameon=False, loc="lower left")
    figs["ex4_india_supplier_share_vs_product_value_share"] = savefig("ex4_india_supplier_share_vs_product_value_share.png")

    supplier = india_all.groupby("top_supplier_iso3", dropna=False).agg(
        products=("cmd_code", "nunique"),
        import_value=("total_product_imports", "sum"),
    ).reset_index()
    supplier["top_supplier_iso3"] = supplier["top_supplier_iso3"].fillna("Unknown")
    supplier["product_share"] = supplier["products"] / supplier["products"].sum()
    supplier["value_share"] = supplier["import_value"] / supplier["import_value"].sum()
    top_by_products = supplier.nlargest(10, "products").sort_values("products")
    top_by_value = supplier.nlargest(10, "import_value").sort_values("import_value")
    fig, axes = plt.subplots(1, 2, figsize=(13, 6))
    axes[0].barh(top_by_products["top_supplier_iso3"], top_by_products["product_share"], color="#6b7280")
    axes[0].set_title("Share of HS6 products")
    axes[0].set_xlabel("Product-count share")
    axes[1].barh(top_by_value["top_supplier_iso3"], top_by_value["value_share"], color="#2f5d62")
    axes[1].set_title("Share of import value")
    axes[1].set_xlabel("Import-value share")
    fig.suptitle(f"Exercise 4: India's Leading Top Suppliers by Product Count and Value ({india_year})")
    figs["ex4_india_supplier_composition"] = savefig("ex4_india_supplier_composition.png")
    return figs


def copy_exercise_11_linkage_figures() -> dict[str, str]:
    figs: dict[str, str] = {}
    source_dir = RESULTS / "exercise_11_product_export_linkage_figures"
    figure_names = [
        "ex11_india_product_loo_gini_scatter.png",
        "ex11_india_product_supplier_loo_scatter.png",
        "ex11_export_linkage_by_loo_decile.png",
        "ex11_intermediate_channel_coefficients.png",
        "ex11_india_sector_linkage_scatter.png",
        "ex11_hs2_export_linkage_by_loo_decile.png",
        "ex11_india_hs2_linkage_scatter.png",
        "ex11_excluding_commodity_outlier_coefficients.png",
    ]
    FIGURES.mkdir(parents=True, exist_ok=True)
    for stale in FIGURES.glob("ex11_*.png"):
        stale.unlink()
    for name in figure_names:
        source = source_dir / name
        if not source.exists():
            raise FileNotFoundError(f"Missing Exercise 11 linkage figure: {source}")
        shutil.copy2(source, FIGURES / name)
        figs[Path(name).stem] = f"figures/{name}"
    return figs


def write_tables(ex3: pd.DataFrame, ex3_decomp: pd.DataFrame, ex4_summary: pd.DataFrame, ex11_regressions: pd.DataFrame) -> dict[str, str]:
    TABLES.mkdir(parents=True, exist_ok=True)
    for stale in TABLES.glob("exercise_11_*.csv"):
        stale.unlink()
    paths: dict[str, str] = {}

    ex3_table = ex3[ex3["import_bin"].isin(BIN_ORDER[:4])].groupby("import_bin").agg(
        rows=("import_bin", "size"),
        median_gini=("product_gini", "median"),
        median_top1=("top_1_product_share", "median"),
        median_active=("active_products", "median"),
    ).reindex(BIN_ORDER).dropna(how="all").reset_index()
    ex3_table["import_bin"] = ex3_table["import_bin"].map(BIN_LABELS)
    path = TABLES / "exercise_03_bin_medians.csv"
    ex3_table.to_csv(path, index=False)
    paths["ex3"] = f"tables/{path.name}"

    ex3_decomp_table = ex3_decomp[ex3_decomp["import_bin"].isin(BIN_ORDER[:4])].groupby("import_bin").agg(
        rows=("import_bin", "size"),
        median_import_value_share=("import_value_share", "median"),
        median_top10_contribution=("top_10_product_share_contribution", "median"),
        median_gini_reduction_when_excluded=("product_gini_reduction_when_excluded", "median"),
        median_top10_reduction_when_excluded=("top_10_product_share_reduction_when_excluded", "median"),
    ).reindex(BIN_ORDER[:4]).dropna(how="all").reset_index()
    ex3_decomp_table["import_bin"] = ex3_decomp_table["import_bin"].map(BIN_LABELS)
    path = TABLES / "exercise_03_bin_decomposition_medians.csv"
    ex3_decomp_table.to_csv(path, index=False)
    paths["ex3_decomp"] = f"tables/{path.name}"

    ex4_table = ex4_summary[[
        "weighted_mean_top_supplier_share",
        "weighted_mean_source_hhi",
        "median_top_supplier_share",
        "share_products_top_supplier_ge_75",
        "import_value_share_products_top_supplier_ge_75",
    ]].median().rename("median_across_importer_years").reset_index().rename(columns={"index": "measure"})
    path = TABLES / "exercise_04_importer_year_medians.csv"
    ex4_table.to_csv(path, index=False)
    paths["ex4"] = f"tables/{path.name}"

    ex11_table = ex11_regressions.copy()
    path = TABLES / "exercise_11_selected_regression_coefficients.csv"
    ex11_table.to_csv(path, index=False)
    paths["ex11"] = f"tables/{path.name}"
    return paths


def table_rows(rows: list[list[str]]) -> str:
    return "\n".join(" & ".join(row) + r" \\" for row in rows)


def shorten_text(value: object, width: int = 48) -> str:
    text = " ".join(str(value).replace("\n", " ").split())
    if len(text) <= width:
        return text
    return text[: max(0, width - 3)].rstrip() + "..."


REG_TERM_LABELS = {
    "loo_gini_contribution_z": "Product LOO Gini contribution",
    "loo_partner_hhi_contribution_z": "Product LOO partner-HHI contribution",
    "loo_gini_x_intermediate_z": "LOO Gini x intermediate",
    "sector_loo_gini_contribution_z": "Sector LOO Gini contribution",
    "sector_loo_partner_hhi_contribution_z": "Sector LOO partner-HHI contribution",
    "hs2_loo_gini_contribution_z": "HS2 LOO Gini contribution",
    "hs2_product_loo_gini_sum_z": "HS2 sum of HS6 LOO Gini contributions",
    "hs2_loo_gini_x_intermediate_share_z": "HS2 LOO Gini x intermediate intensity",
    "hs2_product_loo_gini_sum_x_intermediate_share_z": "HS2 summed LOO Gini x intermediate intensity",
}

REG_MODEL_LABELS = {
    "product_export_value_gini": "Product export value",
    "product_export_any_gini": "Product export indicator",
    "product_export_value_partner_hhi": "Product supplier-country linkage",
    "product_export_value_intermediate_interaction": "Intermediate interaction",
    "sector_export_share_gini": "Sector export share",
    "sector_export_share_partner_hhi": "Sector supplier-country linkage",
    "hs2_export_value_gini": "HS2 export value",
    "hs2_export_any_gini": "HS2 export indicator",
    "hs2_export_share_gini": "HS2 export share",
    "hs2_export_value_intermediate_intensity": "HS2 intermediate intensity",
}


def regression_rows(reg: pd.DataFrame) -> str:
    wanted = [
        ("product_export_value_gini", "loo_gini_contribution_z"),
        ("product_export_any_gini", "loo_gini_contribution_z"),
        ("product_export_value_partner_hhi", "loo_partner_hhi_contribution_z"),
        ("product_export_value_intermediate_interaction", "loo_gini_x_intermediate_z"),
        ("sector_export_share_gini", "sector_loo_gini_contribution_z"),
        ("sector_export_share_partner_hhi", "sector_loo_partner_hhi_contribution_z"),
    ]
    rows: list[list[str]] = []
    for model, term in wanted:
        match = reg[(reg["model_label"] == model) & (reg["term"] == term)]
        if match.empty:
            continue
        row = match.iloc[0]
        rows.append(
            [
                tex_escape(REG_MODEL_LABELS.get(model, model)),
                tex_escape(REG_TERM_LABELS.get(term, term)),
                f"{row['coef']:.3f}",
                f"({row['std_error']:.3f})",
                f"{int(row['nobs']):,}",
                f"{row['r2_within']:.3f}",
            ]
        )
    return table_rows(rows)


def hs2_regression_rows(reg: pd.DataFrame) -> str:
    wanted = [
        ("hs2_export_value_gini", "hs2_product_loo_gini_sum_z"),
        ("hs2_export_any_gini", "hs2_product_loo_gini_sum_z"),
        ("hs2_export_share_gini", "hs2_product_loo_gini_sum_z"),
        ("hs2_export_value_intermediate_intensity", "hs2_product_loo_gini_sum_x_intermediate_share_z"),
    ]
    rows: list[list[str]] = []
    for model, term in wanted:
        match = reg[(reg["model_label"] == model) & (reg["term"] == term)]
        if match.empty:
            continue
        row = match.iloc[0]
        rows.append(
            [
                tex_escape(REG_MODEL_LABELS.get(model, model)),
                tex_escape(REG_TERM_LABELS.get(term, term)),
                f"{row['coef']:.3f}",
                f"({row['std_error']:.3f})",
                f"{int(row['nobs']):,}",
                f"{row['r2_within']:.3f}",
            ]
        )
    return table_rows(rows)


def commodity_comparison_rows(comp: pd.DataFrame) -> str:
    rows: list[list[str]] = []
    order = [
        "Export value: product-Gini contribution",
        "Export probability: product-Gini contribution",
        "Export value: partner-HHI contribution",
        "Intermediate interaction",
    ]
    for check in order:
        base = comp[(comp["check"] == check) & (comp["sample"] == "baseline")]
        excl = comp[(comp["check"] == check) & (comp["sample"] == "excluding oil/gas/gold/coal")]
        if base.empty or excl.empty:
            continue
        base_row = base.iloc[0]
        excl_row = excl.iloc[0]
        rows.append(
            [
                tex_escape(check),
                f"{base_row['coef']:.3f}",
                f"({base_row['std_error']:.3f})",
                f"{excl_row['coef']:.3f}",
                f"({excl_row['std_error']:.3f})",
            ]
        )
    return table_rows(rows)


def effect_rows(effects: pd.DataFrame) -> str:
    rows = []
    for row in effects.itertuples(index=False):
        rows.append([tex_escape(row.effect), f"{row.coef:.3f}", f"({row.std_error:.3f})", f"[{row.ci_low:.3f}, {row.ci_high:.3f}]"])
    return table_rows(rows)


def top_product_rows(products: pd.DataFrame, n: int = 8) -> str:
    rows = []
    for row in products.head(n).itertuples(index=False):
        rows.append(
            [
                tex_escape(str(row.cmd_code).zfill(6)),
                tex_escape(shorten_text(getattr(row, "product_description", ""), width=46)),
                tex_escape(BIN_LABELS.get(row.import_bin, row.import_bin)),
                pct(row.import_value_share),
                f"{row.loo_gini_contribution:.4f}",
                f"{row.loo_partner_hhi_contribution:.4f}",
                pct(row.export_share),
                tex_escape(row.top_supplier_iso3),
            ]
        )
    return table_rows(rows)


def write_latex(figs: dict[str, str], stats: dict[str, object]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    text = rf"""
\documentclass[11pt]{{article}}
\usepackage[margin=1in]{{geometry}}
\usepackage{{graphicx}}
\usepackage{{booktabs}}
\usepackage{{float}}
\usepackage{{caption}}
\usepackage{{subcaption}}
\usepackage{{hyperref}}
\usepackage{{xcolor}}
\usepackage{{enumitem}}
\hypersetup{{colorlinks=true, linkcolor=blue!45!black, urlcolor=blue!45!black}}
\setlist[itemize]{{topsep=2pt,itemsep=2pt,parsep=0pt}}

\title{{Trade Concentration Exercises 3, 4, and 11}}
\author{{Generated from the checkpointed UN Comtrade/OECD pipeline}}
\date{{May 20, 2026}}

\begin{{document}}
\maketitle

\begin{{abstract}}
This report summarizes Exercises 3, 4, and 11 from the trade concentration project. Exercise 3 groups imports into BEC-style use bins and separates within-bin concentration from each bin's contribution to aggregate import concentration. Exercise 4 asks whether individual HS6 products are supplied by dominant partner countries. Exercise 11 now asks whether the HS6 products that raise total import concentration are linked to exports.
\end{{abstract}}

\section{{Executive Summary}}
\begin{{itemize}}
  \item Exercise 3 shows that energy is the sharpest single-product concentration bin and raises aggregate import concentration when excluded in reverse; intermediates are the largest import-value bin and still account for a meaningful share of the aggregate top-10 import basket.
  \item Across country-years, intermediates have median import value share {stats['ex3_intermediate_value_share']} and median top-10 contribution {stats['ex3_intermediate_top10_contribution']}; energy has median import value share {stats['ex3_energy_value_share']} but the clearest positive leave-one-out Gini contribution, {stats['ex3_energy_gini_reduction']}.
  \item Exercise 4 shows that supplier dominance is common at the product level: the median importer-year has a weighted mean top-supplier share of {stats['ex4_weighted_top_supplier']} and a median product top-supplier share of {stats['ex4_median_top_supplier']}.
  \item Exercise 11 does not support the strongest version of the intermediate-processing hypothesis. Conditional on product import-value share, products with higher leave-one-out contribution to total import Gini are less export-linked: the export-value coefficient is {stats['ex11_product_gini_coef']} and the export-indicator coefficient is {stats['ex11_product_any_coef']}.
  \item The supplier-country channel is different: products that raise aggregate partner-country HHI have a positive export-value association, {stats['ex11_partner_hhi_coef']}. For India in {stats['ex11_india_year']}, the products that most raise partner-country concentration are mostly China-linked electronics and machinery rows.
\end{{itemize}}

\section{{Data and Coverage}}
The processed data cover {stats['countries']} countries and annual UN Comtrade HS data from {stats['start_year']} to {stats['end_year']}. The low-memory checkpointed runs produced {stats['ex3_rows']:,} Exercise 3 rows, {stats['ex4_rows']:,} Exercise 4 product rows, and {stats['ex11_product_rows']:,} Exercise 11 country-year-HS6 linkage rows. Exercise 11 is built from checkpointed import product totals, import product-supplier cells, and export product totals; the OECD BTiGE bridge is used only for the sector-level export-linkage graph.

\section{{First-Principles Reading Guide}}
Think of a country's imports as a grocery bill. If most of the bill is spread across many items, concentration is low. If a few items take a huge part of the bill, concentration is high. The three exercises ask increasingly specific versions of ``what is making the bill lumpy?''

\begin{{itemize}}
  \item Exercise 3 asks: which kinds of goods create the lumpiness? Energy, intermediate inputs, capital goods, or final consumption goods?
  \item Exercise 4 asks: once we look inside each product, does one foreign supplier dominate that product?
  \item Exercise 11 asks: do the products that make total imports more concentrated also show up in exports?
\end{{itemize}}

The report is descriptive. A high Gini or high supplier share is evidence of concentration, not proof that concentration causes growth, vulnerability, or policy failure. The useful move is to narrow the mechanism: product mix in Exercise 3, supplier structure in Exercise 4, and whether concentration-driving import products are export-linked in Exercise 11.

\section{{Exercise 3: Import Bins}}
Exercise 3 now asks two related questions. First, are products concentrated within energy, intermediates, capital goods, and final consumption goods? Second, do those bins actually explain aggregate import concentration once their import-value shares and top-product contributions are considered?

\subsection*{{Feynman Translation}}
Imagine sorting all import products into four boxes. Exercise 3 asks two separate questions about the boxes. First: inside each box, is the value spread evenly or dominated by a few products? Second: is the box big enough to matter for total imports? A tiny box can be very concentrated and still not explain the country-wide pattern. A huge box can be only moderately concentrated and still matter a lot.

The median country-year has aggregate import product Gini {stats['ex3_total_gini']} and top-10 product share {stats['ex3_total_top10']}. Energy is the most ``spiky'' box: its median within-bin Gini is high and excluding it lowers aggregate concentration. Intermediates are different: they are the largest box, with median value share {stats['ex3_intermediate_value_share']}, but because the value is spread over thousands of input products, excluding intermediates can make the remaining basket look even more concentrated.

\begin{{table}}[H]
\centering
\caption{{Exercise 3 median concentration by import bin}}
\begin{{tabular}}{{lrrrr}}
\toprule
Import bin & Rows & Median Gini & Median top-1 share & Median active products \\
\midrule
{stats['ex3_table_rows']}
\bottomrule
\end{{tabular}}
\end{{table}}

\begin{{table}}[H]
\centering
\caption{{Exercise 3 median aggregate contribution by import bin}}
\resizebox{{\textwidth}}{{!}}{{%
\begin{{tabular}}{{lrrrr}}
\toprule
Import bin & Value share & Top-10 contribution & Gini reduction if excluded & Top-10 reduction if excluded \\
\midrule
{stats['ex3_decomposition_table_rows']}
\bottomrule
\end{{tabular}}
}}
\end{{table}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.92\textwidth]{{{figs['ex3_bin_gini_over_years']}}}
\caption{{Median product Gini over time for energy, intermediates, capital goods, and final consumption goods. Each line is the median across countries in that year.}}
\end{{figure}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.92\textwidth]{{{figs['ex3_bin_top1_over_years']}}}
\caption{{Median top-1 product share over time for the same four import bins. Energy is top-product driven, while intermediates remain concentrated even though the top product has a much smaller share.}}
\end{{figure}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.92\textwidth]{{{figs['ex3_bin_value_share_over_years']}}}
\caption{{Median import value share by bin. This shows whether a highly concentrated bin is large enough to matter for aggregate concentration.}}
\end{{figure}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.92\textwidth]{{{figs['ex3_bin_top10_contribution_over_years']}}}
\caption{{Contribution of each bin to the aggregate top-10 product import share. Solid lines are cross-country medians; dashed lines show India. Intermediates matter more in value-weighted top-product accounting than their top-1 within-bin share alone suggests.}}
\end{{figure}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.92\textwidth]{{{figs['ex3_leave_one_out_gini_reduction']}}}
\caption{{Leave-one-bin-out contribution to aggregate import concentration. Positive values mean the bin raises aggregate product Gini; negative values mean it dilutes aggregate product Gini. India is highlighted in red.}}
\end{{figure}}

\begin{{figure}}[H]
\centering
\includegraphics[width=\textwidth]{{{figs['ex3_gini_time_by_bin']}}}
\caption{{Median product concentration by import bin over time, with India shown separately.}}
\end{{figure}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.92\textwidth]{{{figs['ex3_latest_bin_distribution']}}}
\caption{{Latest available cross-country distribution of product Gini by import bin. India is highlighted in red.}}
\end{{figure}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.92\textwidth]{{{figs['ex3_common_year_bin_distribution']}}}
\caption{{Common-year cross-country distribution of product Gini by import bin. This is the preferred India/peer comparison because it uses {stats['india_ex3_year']}, the latest year in which India appears.}}
\end{{figure}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.92\textwidth]{{{figs['ex3_india_import_bin_shares']}}}
\caption{{India's import value composition by BEC bin. Intermediates and energy dominate the import basket in recent years.}}
\end{{figure}}

The empirical pattern is not simply that all imports are equally concentrated. Energy has very high top-product shares because the category contains relatively few high-value products, and it is the cleanest bin-level contributor to aggregate product Gini. Intermediates have lower top-product shares within the bin, but they are the largest part of the import basket and therefore account for more aggregate top-10 product concentration than the within-bin top-1 statistic implies.

For India in {stats['india_ex3_year']}, energy has product Gini {stats['india_ex3_energy_gini']}, top-product share {stats['india_ex3_energy_top1']}, import value share {stats['india_ex3_energy_share']}, and leave-one-out Gini contribution {stats['india_ex3_energy_gini_reduction']}. Intermediates have product Gini {stats['india_ex3_intermediates_gini']}, top-product share {stats['india_ex3_intermediates_top1']}, import value share {stats['india_ex3_intermediates_share']}, and top-10 contribution {stats['india_ex3_intermediates_top10_contribution']}. Final consumption goods are also concentrated, but they account for only {stats['india_ex3_final_share']} of India's import value, so the value-weighted India story is mainly energy plus intermediates.

\subsection*{{How We Should Read This Together}}
The Exercise 3 result is not ``intermediates explain everything.'' It is more precise. Energy is the clearest contributor to aggregate product concentration. Intermediates are the largest import category and are internally skewed, but they also broaden the product basket. So Exercise 3 says imports are lumpy for two reasons at once: energy creates sharp spikes, while intermediates make up the biggest production-related part of the import bill.

\section{{Exercise 4: Dominant Supplier by Product}}
Exercise 4 moves inside each HS6 product and measures whether one supplier dominates that product's imports. This distinguishes product concentration from source-country concentration.

\subsection*{{Feynman Translation}}
Exercise 3 tells us which products are big. Exercise 4 asks where each product comes from. If India imports a product from ten countries, supplier risk is diffuse. If 80 percent comes from one country, that product is supplier-concentrated. This is a different kind of concentration: not ``which products dominate imports?'' but ``who dominates supply of each product?''

The median product's top supplier accounts for {stats['ex4_median_top_supplier']} of that product's imports. But value weighting matters. Products with a top supplier above 75 percent are {stats['ex4_product_ge75']} of product rows but only {stats['ex4_value_ge75']} of import value. That means many narrow HS6 lines are highly supplier-concentrated, while the highest-dollar import basket is less single-source than the raw product count suggests.

\begin{{table}}[H]
\centering
\caption{{Exercise 4 median importer-year supplier dominance}}
\begin{{tabular}}{{lr}}
\toprule
Measure & Median \\
\midrule
Weighted mean top supplier share & {stats['ex4_weighted_top_supplier']} \\
Weighted mean source HHI & {stats['ex4_weighted_hhi']} \\
Median product top supplier share & {stats['ex4_median_top_supplier']} \\
Product share with top supplier $\geq 75\%$ & {stats['ex4_product_ge75']} \\
Import value share with top supplier $\geq 75\%$ & {stats['ex4_value_ge75']} \\
\bottomrule
\end{{tabular}}
\end{{table}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.92\textwidth]{{{figs['ex4_supplier_dominance_time']}}}
\caption{{Weighted mean top-supplier share over time. India broadly tracks the cross-country median but rises in 2023--2024.}}
\end{{figure}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.92\textwidth]{{{figs['ex4_high_dominance_value_share_time']}}}
\caption{{Import value share in products where the top supplier controls at least 75 percent.}}
\end{{figure}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.82\textwidth]{{{figs['ex4_latest_country_dominance']}}}
\caption{{Latest available weighted top-supplier share by importer. India is highlighted.}}
\end{{figure}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.92\textwidth]{{{figs['ex4_top_supplier_share_histogram']}}}
\caption{{Distribution of top-supplier shares across importer-HS6 product rows in each importer's latest available year. The dashed line marks the 75 percent single-supplier threshold and the red line marks the median product row.}}
\end{{figure}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.92\textwidth]{{{figs['ex4_global_supplier_share_vs_product_value_share']}}}
\caption{{Importer-HS6 products across all countries in each importer's latest available year, restricted to products worth at least 0.1 percent of the importer's total imports. The x-axis is that product's share of the importer's total import value; the y-axis is top-supplier share within that importer-product cell. Red points are products worth at least 1 percent of the importer's total imports. The black line is a simple OLS fit through the displayed points.}}
\end{{figure}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.92\textwidth]{{{figs['ex4_global_supplier_share_vs_product_value_share_loglog']}}}
\caption{{The same latest-year importer-HS6 product scatter on log-log axes. This version spaces out small and medium import-share products and the fitted line is estimated in logs, so the slope should be read as a proportional relationship between product import-value share and top-supplier dominance.}}
\end{{figure}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.92\textwidth]{{{figs['ex4_india_top_products']}}}
\caption{{India's largest imported HS6 products in the latest available year. Bars show import value; color shows the top supplier share. Labels give a short English product name, the HS6 code, and the leading supplier.}}
\end{{figure}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.92\textwidth]{{{figs['ex4_india_supplier_share_vs_product_value_share']}}}
\caption{{India HS6 products by top-supplier share and share of total import value. The vertical dashed line marks 75 percent top-supplier share. Red points are the largest products by import value and are annotated with English product names plus leading suppliers.}}
\end{{figure}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.92\textwidth]{{{figs['ex4_india_supplier_composition']}}}
\caption{{India's leading top suppliers by HS6 product count and by import value. This separates many small product lines from the suppliers that matter most in dollar terms.}}
\end{{figure}}

The main takeaway is that supplier dominance is widespread but not uniform. Many products have a supplier above 75 percent, yet those products account for a smaller share of total import value than the raw product count would suggest. For India, high-value commodities such as crude oil, gold, coal, LNG, and electronic components often have meaningful leading suppliers without always being completely single-source.

In India {stats['india_ex4_year']}, products with a top supplier above 75 percent represent {stats['india_ex4_product_ge75']} of HS6 product rows but {stats['india_ex4_value_ge75']} of import value. China is the leading supplier for {stats['india_ex4_china_product_share']} of India's HS6 rows and {stats['india_ex4_china_value_share']} of import value, while Russia, Switzerland, Australia, Qatar, and the UAE matter disproportionately for large commodity rows.

\subsection*{{How We Should Read This Together}}
Exercise 4 weakens the simplistic claim that every important import is single-sourced. It also weakens the opposite claim that sourcing is always diversified. The evidence is in the middle: supplier dominance is common, but the value-weighted picture is less extreme than the product-count picture. For India, China matters across many product lines, while commodity suppliers matter because a few rows are very large.

\section{{Exercise 11: Do Concentration-Driving Imports Link To Exports?}}
Exercise 11 now asks whether the products that make total imports more concentrated are also linked to exports. This replaces the previous within-IO-sector concentration exercise. The concentration object is no longer ``how concentrated are imports inside sector C26?'' It is ``how much does HS6 product \(p\) raise the concentration of the country's total import basket?''

\subsection*{{Hypotheses}}
\begin{{itemize}}
  \item \textbf{{Product-contribution hypothesis:}} if concentration-driving imports are part of production chains, products with higher leave-one-out Gini contribution should be more export-linked.
  \item \textbf{{Supplier-country hypothesis:}} if country-source exposure matters for exporters, products that raise aggregate partner-country HHI should be more export-linked.
  \item \textbf{{Intermediate-processing hypothesis:}} the product-contribution relationship should be stronger for intermediates than for energy, capital goods, final consumption, or unmapped rows.
\end{{itemize}}

\subsection*{{Feynman Translation}}
Imagine a country's import bill as one long receipt. For each HS6 product, we remove that product from the receipt and recompute concentration. If removing crude oil makes the receipt much less lumpy, crude oil had a large positive leave-one-out contribution. If removing a small product barely changes the receipt, that product is not driving aggregate concentration. We do the same for supplier countries: remove the product and ask whether the whole import bill becomes less concentrated across partner countries.

\begin{{table}}[H]
\centering
\caption{{Exercise 11 selected fixed-effect regressions}}
\resizebox{{\textwidth}}{{!}}{{%
\begin{{tabular}}{{llrrrr}}
\toprule
Model & Main term & Coef. & SE & N & Within $R^2$ \\
\midrule
{stats['ex11_regression_rows']}
\bottomrule
\end{{tabular}}
}}
\end{{table}}

\begin{{table}}[H]
\centering
\caption{{Intermediate-channel effect from the interaction model}}
\begin{{tabular}}{{lrrr}}
\toprule
Effect & Coef. & SE & 95\% CI \\
\midrule
{stats['ex11_effect_rows']}
\bottomrule
\end{{tabular}}
\end{{table}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.92\textwidth]{{{figs['ex11_india_product_loo_gini_scatter']}}}
\caption{{India {stats['ex11_india_year']}: each point is an HS6 import product. The x-axis is the product's share of total imports; the y-axis is how much that product raises total import product Gini. Point size reflects export value.}}
\end{{figure}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.92\textwidth]{{{figs['ex11_india_product_supplier_loo_scatter']}}}
\caption{{India {stats['ex11_india_year']}: product contribution to total import product Gini versus product contribution to total partner-country HHI. This shows whether the products that make the product basket lumpy also make sourcing country-concentrated.}}
\end{{figure}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.92\textwidth]{{{figs['ex11_export_linkage_by_loo_decile']}}}
\caption{{Export linkage by decile of leave-one-out Gini contribution. The figure asks whether products that raise total import concentration are more likely to be exported or have higher export value.}}
\end{{figure}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.82\textwidth]{{{figs['ex11_intermediate_channel_coefficients']}}}
\caption{{Regression-implied slopes for non-intermediate and intermediate products. A positive intermediate-minus-non-intermediate effect would strengthen the intermediate-processing claim.}}
\end{{figure}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.82\textwidth]{{{figs['ex11_india_sector_linkage_scatter']}}}
\caption{{India sector-level version using the OECD BTiGE bridge only as a product-to-sector bridge. The x-axis aggregates product leave-one-out contributions into IO sectors; the y-axis is the sector's export share.}}
\end{{figure}}

\subsection*{{Robustness: Why HS6 May Be Too Narrow}}
The narrow HS6 match asks whether the same exact imported product is also exported. That can miss intermediate processing. A country may import one HS6 input, process it, and export a different HS6 output in the same broad production chain. To document this concern while preserving the original concentration object, we aggregate HS6 leave-one-out import-concentration contributions into HS2 chapters and compare those broader chapter contributions with HS2 export outcomes. This robustness has {stats['ex11_hs2_product_rows']:,} country-year-HS2 rows and includes country-year and HS2 fixed effects.

\begin{{table}}[H]
\centering
\caption{{HS2 robustness regressions for broader product-chain linkage}}
\resizebox{{\textwidth}}{{!}}{{%
\begin{{tabular}}{{llrrrr}}
\toprule
Model & Main term & Coef. & SE & N & Within $R^2$ \\
\midrule
{stats['ex11_hs2_regression_rows']}
\bottomrule
\end{{tabular}}
}}
\end{{table}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.92\textwidth]{{{figs['ex11_hs2_export_linkage_by_loo_decile']}}}
\caption{{Broader HS2 version of the export-linkage plot. Deciles sort country-year-HS2 chapters by the sum of their HS6 products' leave-one-out contributions to total import product Gini.}}
\end{{figure}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.86\textwidth]{{{figs['ex11_india_hs2_linkage_scatter']}}}
\caption{{India HS2 robustness. The x-axis sums HS6 product leave-one-out contributions inside each HS2 chapter. Point color is the import-weighted intermediate share inside the chapter, so this view asks whether broad concentration-driving chapters with more intermediate content are also export-linked.}}
\end{{figure}}

\subsection*{{Robustness: Excluding Oil, Gas, Gold, and Coal}}
A second concern is that the HS6 result may be dominated by very large commodity rows rather than by production-chain inputs. We therefore rerun the narrow HS6 regressions after excluding coal, crude and refined petroleum, petroleum gases/natural gas, and gold: HS4 codes 2701, 2709, 2710, 2711, and 7108. These rows are {stats['ex11_commodity_row_share']} of product observations but {stats['ex11_commodity_import_share']} of import value in the HS6 panel.

\begin{{table}}[H]
\centering
\caption{{Narrow HS6 robustness after excluding commodity outliers}}
\resizebox{{\textwidth}}{{!}}{{%
\begin{{tabular}}{{lrrrr}}
\toprule
Check & Baseline coef. & Baseline SE & Excluding coef. & Excluding SE \\
\midrule
{stats['ex11_commodity_comparison_rows']}
\bottomrule
\end{{tabular}}
}}
\end{{table}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.88\textwidth]{{{figs['ex11_excluding_commodity_outlier_coefficients']}}}
\caption{{Comparison of the key HS6 regression coefficients before and after excluding oil, gas, gold, and coal. If the main finding were only a commodity artifact, these estimates would move sharply toward the intermediate-processing prediction.}}
\end{{figure}}

\begin{{table}}[H]
\centering
\caption{{India {stats['ex11_india_year']}: top products by contribution to total import product Gini}}
\resizebox{{\textwidth}}{{!}}{{%
\begin{{tabular}}{{lllrrrrl}}
\toprule
HS6 & Product & Bin & Import share & LOO Gini & LOO partner HHI & Export share & Top supplier \\
\midrule
{stats['ex11_top_gini_product_rows']}
\bottomrule
\end{{tabular}}
}}
\end{{table}}

\begin{{table}}[H]
\centering
\caption{{India {stats['ex11_india_year']}: top products by contribution to total partner-country HHI}}
\resizebox{{\textwidth}}{{!}}{{%
\begin{{tabular}}{{lllrrrrl}}
\toprule
HS6 & Product & Bin & Import share & LOO Gini & LOO partner HHI & Export share & Top supplier \\
\midrule
{stats['ex11_top_partner_product_rows']}
\bottomrule
\end{{tabular}}
}}
\end{{table}}

The results weaken the strongest intermediate-processing version of the story. In the product-level regressions with country-year fixed effects, BEC-bin controls, and import-value-share controls, the coefficient on leave-one-out Gini contribution is negative for both export value and export probability. The intermediate interaction is also negative. This says the products that mechanically raise total import product concentration are not, after controlling for size, the products most strongly linked to exports.

The supplier-country channel is more supportive. Products that raise total partner-country HHI have a positive association with export value. In India, the highest partner-HHI contributors are mostly electronics and machinery products where China is the leading supplier. That is a narrower claim: export-linked exposure appears more in supplier-country concentration for specific input-like products than in aggregate product-Gini contribution.

The robustness checks make the interpretation more disciplined. The HS2 version directly addresses the concern that exact HS6 matching is too narrow for intermediate processing. The commodity-exclusion version checks whether oil, gas, gold, and coal are mechanically driving the negative HS6 product-Gini result. Together, these checks separate two issues: broad chapter-level production-chain linkage and narrow product-level commodity dominance.

\subsection*{{How We Should Read This Together}}
Exercise 11 now clarifies what the earlier exercises can and cannot support. Exercise 3 says energy and some large products make total imports lumpy. Exercise 4 says supplier dominance exists but is not uniformly value-dominant. The new Exercise 11 says the aggregate product-Gini contributors are not generally the export-linked products, which weakens a broad intermediate-processing claim. A more defensible claim is narrower: certain supplier-concentrated intermediate products, especially electronics-related rows for India, connect import concentration to export activity.

\section{{Subagent Graph Roadmap}}
The exercise-specific agents also identified useful extensions beyond the core report figures:
\begin{{itemize}}
  \item Exercise 3: balanced-panel Gini trends for 2000--2024; top-product share versus Gini; active product counts versus concentration; and mapping-coverage plots by HS revision.
  \item Exercise 4: importer-year ECDFs of top-supplier shares; import-value decile plots; HS chapter heatmaps; and large-product outlier labels for India.
  \item Exercise 11: product-level robustness checks by HS chapter, separate energy exclusions, lagged export outcomes, and sector-level versions that use the OECD bridge only to group HS6 products.
\end{{itemize}}
These are not causal identification checks; they are descriptive diagnostics that help distinguish product concentration, supplier-country concentration, value weighting, and export linkage.

\section{{Caveats}}
\begin{{itemize}}
  \item Exercises 3 and 11 depend on the approved BEC mapping. Ambiguous and unmapped HS rows are reported separately where appropriate.
  \item Exercise 4 is HS6-product based. A dominant supplier at HS6 may hide within-product quality or variety differences.
  \item Exercise 11 is descriptive. It does not prove that concentrated imports cause exports, and the product-level regressions can still reflect product size, two-way trade, re-exports, and HS classification issues.
  \item The sector-level Exercise 11 graph uses the OECD BTiGE bridge only to group HS6 products into sectors. It does not use within-sector import concentration as the main concentration object.
\end{{itemize}}

\end{{document}}
"""
    (OUT / "main.tex").write_text(textwrap.dedent(text).strip() + "\n", encoding="utf-8")


def main() -> int:
    sns.set_theme(style="whitegrid", context="paper", font_scale=1.05)
    OUT.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    TABLES.mkdir(parents=True, exist_ok=True)

    ex3 = pd.read_parquet(ROOT / "data/processed/exercise_03_import_bin_concentration.parquet")
    ex3_total = pd.read_parquet(ROOT / "data/processed/exercise_03_total_import_concentration.parquet")
    ex3_decomp = pd.read_parquet(ROOT / "data/processed/exercise_03_import_bin_decomposition.parquet")
    ex4 = pd.read_parquet(ROOT / "data/processed/exercise_04_dominant_supplier_by_product.parquet")
    ex11_summary_stats = pd.read_csv(ROOT / "results/exercise_11_product_export_linkage_tables/summary_stats.csv")
    ex11_reg = pd.read_csv(ROOT / "results/exercise_11_product_export_linkage_tables/selected_regression_coefficients.csv")
    ex11_effects = pd.read_csv(ROOT / "results/exercise_11_product_export_linkage_tables/intermediate_effects.csv")
    ex11_top_gini = pd.read_csv(ROOT / "results/exercise_11_product_export_linkage_tables/india_top_loo_gini_products.csv")
    ex11_top_partner = pd.read_csv(ROOT / "results/exercise_11_product_export_linkage_tables/india_top_loo_partner_hhi_products.csv")
    ex11_commodity = pd.read_csv(ROOT / "results/exercise_11_product_export_linkage_tables/commodity_exclusion_regression_comparison.csv")
    ex4_summary = pd.read_csv(ROOT / "results/exercise_04_tables/dominant_supplier_importer_summary.csv")

    figs: dict[str, str] = {}
    figs.update(plot_exercise_3(ex3, ex3_decomp))
    figs.update(plot_exercise_4(ex4, ex4_summary))
    figs.update(copy_exercise_11_linkage_figures())
    write_tables(ex3, ex3_decomp, ex4_summary, ex11_reg)

    ex3_medians = ex3[ex3["import_bin"].isin(BIN_ORDER[:4])].groupby("import_bin").agg(
        rows=("import_bin", "size"),
        median_gini=("product_gini", "median"),
        median_top1=("top_1_product_share", "median"),
        median_active=("active_products", "median"),
    ).reindex(BIN_ORDER[:4]).dropna(how="all").reset_index()
    ex3_rows = []
    for row in ex3_medians.itertuples(index=False):
        ex3_rows.append(
            [
                tex_escape(BIN_LABELS[row.import_bin]),
                f"{int(row.rows):,}",
                f"{row.median_gini:.3f}",
                pct(row.median_top1),
                f"{row.median_active:,.0f}",
            ]
        )
    ex3_decomp_medians = ex3_decomp[ex3_decomp["import_bin"].isin(BIN_ORDER[:4])].groupby("import_bin").agg(
        median_value_share=("import_value_share", "median"),
        median_top10_contribution=("top_10_product_share_contribution", "median"),
        median_gini_reduction=("product_gini_reduction_when_excluded", "median"),
        median_top10_reduction=("top_10_product_share_reduction_when_excluded", "median"),
    ).reindex(BIN_ORDER[:4])
    ex3_decomp_rows = []
    for import_bin, row in ex3_decomp_medians.iterrows():
        ex3_decomp_rows.append(
            [
                tex_escape(BIN_LABELS[import_bin]),
                pct(row.median_value_share),
                pct(row.median_top10_contribution),
                f"{row.median_gini_reduction:.3f}",
                pct(row.median_top10_reduction),
            ]
        )

    ex4_medians = ex4_summary[[
        "weighted_mean_top_supplier_share",
        "weighted_mean_source_hhi",
        "median_top_supplier_share",
        "share_products_top_supplier_ge_75",
        "import_value_share_products_top_supplier_ge_75",
    ]].median()
    ex3_total_medians = ex3_total[["product_gini", "top_10_product_share"]].median()
    india_ex3_year = int(ex3.loc[ex3["iso3"] == "IND", "year"].max())
    india_ex3 = ex3[(ex3["iso3"] == "IND") & (ex3["year"] == india_ex3_year)].set_index("import_bin")
    india_ex3_total = float(india_ex3["total_imports_in_bin"].sum())
    india_ex3_decomp = ex3_decomp[(ex3_decomp["iso3"] == "IND") & (ex3_decomp["year"] == india_ex3_year)].set_index("import_bin")
    india_ex4_year = int(ex4_summary.loc[ex4_summary["iso3"] == "IND", "year"].max())
    india_ex4 = ex4_summary[(ex4_summary["iso3"] == "IND") & (ex4_summary["year"] == india_ex4_year)].iloc[0]
    india_ex4_products = ex4[(ex4["iso3"] == "IND") & (ex4["year"] == india_ex4_year)].copy()
    india_ex4_china = india_ex4_products[india_ex4_products["top_supplier_iso3"] == "CHN"]
    india_ex4_product_total = float(india_ex4_products["cmd_code"].nunique())
    india_ex4_value_total = float(india_ex4_products["total_product_imports"].sum())
    ex11_summary_map = dict(zip(ex11_summary_stats["measure"], ex11_summary_stats["value"], strict=False))

    def summary_number(measure: str, default: float = 0.0) -> float:
        value = pd.to_numeric(pd.Series([ex11_summary_map.get(measure, default)]), errors="coerce").iloc[0]
        if not np.isfinite(value):
            return default
        return float(value)

    def reg_value(model_label: str, term: str, col: str = "coef") -> float:
        match = ex11_reg[(ex11_reg["model_label"] == model_label) & (ex11_reg["term"] == term)]
        if match.empty:
            return float("nan")
        return float(match.iloc[0][col])

    stats = {
        "countries": int(ex3["iso3"].nunique()),
        "start_year": int(ex3["year"].min()),
        "end_year": int(ex3["year"].max()),
        "ex3_rows": int(len(ex3)),
        "ex4_rows": int(len(ex4)),
        "ex11_product_rows": int(summary_number("product_panel_rows")),
        "ex11_india_year": int(summary_number("india_latest_year", 2024)),
        "ex11_regression_rows": regression_rows(ex11_reg),
        "ex11_hs2_regression_rows": hs2_regression_rows(ex11_reg),
        "ex11_commodity_comparison_rows": commodity_comparison_rows(ex11_commodity),
        "ex11_effect_rows": effect_rows(ex11_effects),
        "ex11_top_gini_product_rows": top_product_rows(ex11_top_gini, n=8),
        "ex11_top_partner_product_rows": top_product_rows(ex11_top_partner, n=8),
        "ex11_product_gini_coef": f"{reg_value('product_export_value_gini', 'loo_gini_contribution_z'):.3f}",
        "ex11_product_any_coef": f"{reg_value('product_export_any_gini', 'loo_gini_contribution_z'):.3f}",
        "ex11_partner_hhi_coef": f"{reg_value('product_export_value_partner_hhi', 'loo_partner_hhi_contribution_z'):.3f}",
        "ex11_hs2_product_rows": int(summary_number("hs2_panel_rows")),
        "ex11_hs2_coef": f"{reg_value('hs2_export_value_gini', 'hs2_product_loo_gini_sum_z'):.3f}",
        "ex11_hs2_interaction_coef": f"{reg_value('hs2_export_value_intermediate_intensity', 'hs2_product_loo_gini_sum_x_intermediate_share_z'):.3f}",
        "ex11_commodity_import_share": pct(summary_number("commodity_outlier_import_value_share")),
        "ex11_commodity_row_share": pct(summary_number("commodity_outlier_row_share")),
        "ex3_table_rows": table_rows(ex3_rows),
        "ex3_decomposition_table_rows": table_rows(ex3_decomp_rows),
        "ex3_total_gini": f"{ex3_total_medians['product_gini']:.3f}",
        "ex3_total_top10": pct(ex3_total_medians["top_10_product_share"]),
        "ex3_energy_value_share": pct(ex3_decomp_medians.loc["energy", "median_value_share"]),
        "ex3_energy_gini_reduction": f"{ex3_decomp_medians.loc['energy', 'median_gini_reduction']:.3f}",
        "ex3_intermediate_value_share": pct(ex3_decomp_medians.loc["intermediates", "median_value_share"]),
        "ex3_intermediate_top10_contribution": pct(ex3_decomp_medians.loc["intermediates", "median_top10_contribution"]),
        "ex4_weighted_top_supplier": pct(ex4_medians["weighted_mean_top_supplier_share"]),
        "ex4_weighted_hhi": f"{ex4_medians['weighted_mean_source_hhi']:.3f}",
        "ex4_median_top_supplier": pct(ex4_medians["median_top_supplier_share"]),
        "ex4_product_ge75": pct(ex4_medians["share_products_top_supplier_ge_75"]),
        "ex4_value_ge75": pct(ex4_medians["import_value_share_products_top_supplier_ge_75"]),
        "india_ex3_year": india_ex3_year,
        "india_ex3_energy_gini": f"{india_ex3.loc['energy', 'product_gini']:.3f}",
        "india_ex3_energy_top1": pct(india_ex3.loc["energy", "top_1_product_share"]),
        "india_ex3_energy_share": pct(india_ex3_decomp.loc["energy", "import_value_share"]),
        "india_ex3_energy_gini_reduction": f"{india_ex3_decomp.loc['energy', 'product_gini_reduction_when_excluded']:.3f}",
        "india_ex3_intermediates_gini": f"{india_ex3.loc['intermediates', 'product_gini']:.3f}",
        "india_ex3_intermediates_top1": pct(india_ex3.loc["intermediates", "top_1_product_share"]),
        "india_ex3_intermediates_share": pct(india_ex3_decomp.loc["intermediates", "import_value_share"]),
        "india_ex3_intermediates_top10_contribution": pct(india_ex3_decomp.loc["intermediates", "top_10_product_share_contribution"]),
        "india_ex3_final_share": pct(india_ex3.loc["final_consumption", "total_imports_in_bin"] / india_ex3_total),
        "india_ex4_year": india_ex4_year,
        "india_ex4_product_ge75": pct(india_ex4["share_products_top_supplier_ge_75"]),
        "india_ex4_value_ge75": pct(india_ex4["import_value_share_products_top_supplier_ge_75"]),
        "india_ex4_china_product_share": pct(india_ex4_china["cmd_code"].nunique() / india_ex4_product_total),
        "india_ex4_china_value_share": pct(india_ex4_china["total_product_imports"].sum() / india_ex4_value_total),
    }
    write_latex(figs, stats)

    readme = """# Overleaf Report: Exercises 3, 4, and 11

Upload this folder, or `overleaf_exercises_03_04_11.zip`, to Overleaf and compile `main.tex`.

Contents:
- `main.tex`: report text and figure references.
- `main.pdf`: locally compiled report when `tectonic` is available.
- `figures/`: generated PNG figures.
- `tables/`: supporting CSV summary tables.
"""
    (OUT / "README.md").write_text(readme, encoding="utf-8")

    for stale in ["main.pdf", "main.aux", "main.log", "main.out"]:
        stale_path = OUT / stale
        if stale_path.exists():
            stale_path.unlink()

    compiler = shutil.which("tectonic")
    if compiler:
        subprocess.run([compiler, "--chatter", "minimal", "main.tex"], cwd=OUT, check=True)

    zip_path = RESULTS / "overleaf_exercises_03_04_11.zip"
    if zip_path.exists():
        zip_path.unlink()
    shutil.make_archive(str(zip_path.with_suffix("")), "zip", OUT)
    print(f"Wrote {OUT.relative_to(ROOT)}")
    print(f"Wrote {zip_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
