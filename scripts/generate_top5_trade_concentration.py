#!/usr/bin/env python3
"""Generate exact top-five product/partner concentration tables and histograms.

This uses existing checkpoints:
- imports from Exercise 4 importer-product-partner aggregate files;
- exports from Exercise 12 aggregate rows filtered to product and partner dimensions.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow.dataset as ds
import seaborn as sns
from matplotlib.ticker import PercentFormatter


ROOT = Path(__file__).resolve().parents[1]
DATA_PROCESSED = ROOT / "data/processed"
RESULTS = ROOT / "results"
EX01_FIGURES = RESULTS / "exercise_01_figures"
EX01_TABLES = RESULTS / "exercise_01_tables"

IMPORT_AGG_DIR = DATA_PROCESSED / "exercise_04_file_aggregates"
EXPORT_AGG_PATH = DATA_PROCESSED / "exercise_12_export_aggregates.parquet"
COUNTRY_PANEL_PATH = DATA_PROCESSED / "prof_p_country_panel.csv"
PARTNER_REF_PATH = ROOT / "data/raw/comtrade/partner_reference.csv"
CONCENTRATION_PATH = DATA_PROCESSED / "concentration_all_years.parquet"


PRODUCT_LABEL_OVERRIDES = {
    "151110": "Crude palm oil",
    "270119": "Other coal",
    "270900": "Crude petroleum oil",
    "271019": "Refined petroleum oils",
    "271111": "Liquefied natural gas",
    "271112": "Liquefied propane",
    "271113": "Liquefied butanes",
    "300490": "Packaged medicaments",
    "710231": "Unworked non-industrial diamonds",
    "710239": "Other non-industrial diamonds",
    "710692": "Semi-manufactured silver",
    "710812": "Unwrought non-monetary gold",
    "847130": "Portable computers/laptops",
    "847330": "Computer parts and accessories",
    "851712": "Mobile phones",
    "851762": "Communication/network equipment",
    "851779": "Communication apparatus parts",
    "854231": "Processor/controller chips",
    "870323": "Passenger cars, medium gasoline",
    "880240": "Large aircraft",
}

FREQUENCY_TOP_N = 20


def strip_hs_code(description: str) -> str:
    return description.split(" - ", 1)[1] if " - " in description else description


def gini(values: pd.Series | np.ndarray | list[float]) -> float:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr) & (arr > 0)]
    if arr.size == 0:
        return np.nan
    arr.sort()
    total = arr.sum()
    if total <= 0:
        return np.nan
    n = arr.size
    idx = np.arange(1, n + 1)
    return float((2 * np.sum(idx * arr) / (n * total)) - ((n + 1) / n))


def load_product_descriptions() -> tuple[dict[tuple[str, str], str], dict[str, str]]:
    by_class: dict[tuple[str, str], str] = {}
    fallback: dict[str, str] = {}
    for classification in ["H0", "H1", "H2", "H3", "H4", "H5", "H6"]:
        path = ROOT / "data/raw/classifications" / f"{classification}.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        for row in data.get("results", []):
            raw_code = str(row.get("id", ""))
            if not raw_code.isdigit():
                continue
            code = raw_code.zfill(6)
            text = strip_hs_code(str(row.get("text", "")).strip())
            if len(code) == 6 and text:
                by_class[(classification, code)] = text
                fallback[code] = text
    return by_class, fallback


def product_name(classification_code: object, cmd_code: object, by_class: dict[tuple[str, str], str], fallback: dict[str, str]) -> str:
    code = str(cmd_code).zfill(6)
    if code in PRODUCT_LABEL_OVERRIDES:
        return PRODUCT_LABEL_OVERRIDES[code]
    classification = str(classification_code or "").strip()
    label = by_class.get((classification, code), fallback.get(code, code))
    label = " ".join(label.replace(";", ":").split())
    return textwrap.shorten(label, width=95, placeholder="...")


def load_partner_lookup() -> dict[int, str]:
    ref = load_partner_reference()
    names = {}
    for row in ref.itertuples(index=False):
        iso = "" if pd.isna(row.partner_iso3) else str(row.partner_iso3)
        suffix = f" ({iso})" if iso else ""
        names[int(row.partner_code)] = f"{row.partner_name}{suffix}"
    return names


def load_partner_reference() -> pd.DataFrame:
    ref = pd.read_csv(PARTNER_REF_PATH)
    ref["partner_code"] = pd.to_numeric(ref["partner_code"], errors="coerce")
    ref = ref.dropna(subset=["partner_code"]).copy()
    ref["partner_code"] = ref["partner_code"].astype(int)
    ref["partner_iso3"] = ref["partner_iso3"].fillna("").astype(str).str.strip()
    ref["partner_name"] = ref["partner_name"].fillna("").astype(str).str.strip()
    return ref[["partner_code", "partner_iso3", "partner_name"]].copy()


def load_country_panel() -> pd.DataFrame:
    panel = pd.read_csv(COUNTRY_PANEL_PATH)
    panel["reporter_code"] = pd.to_numeric(panel["reporter_code"], errors="coerce").astype(int)
    return panel[["country", "iso3", "reporter_code"]].copy()


def add_item_labels(
    top: pd.DataFrame,
    dimension: str,
    by_class: dict[tuple[str, str], str],
    product_fallback: dict[str, str],
    partner_lookup: dict[int, str],
) -> pd.DataFrame:
    out = top.copy()
    if dimension == "product":
        out["item_code"] = out["cmd_code"].astype(str).str.zfill(6)
        if "classification_code" in out.columns:
            out["classification_code"] = out["classification_code"].fillna("").astype(str)
        else:
            out["classification_code"] = ""
        out["item_name"] = [
            product_name(classification, code, by_class, product_fallback)
            for classification, code in zip(out["classification_code"], out["item_code"], strict=False)
        ]
    elif dimension == "partner":
        out["partner_code"] = pd.to_numeric(out["partner_code"], errors="coerce").astype(int)
        out["item_code"] = out["partner_code"].astype(str)
        out["classification_code"] = ""
        out["item_name"] = out["partner_code"].map(partner_lookup).fillna("Partner " + out["item_code"])
    else:
        raise ValueError(f"Unexpected dimension: {dimension}")
    return out


def top5_from_values(
    values: pd.DataFrame,
    flow: str,
    dimension: str,
    item_cols: list[str],
    country_panel: pd.DataFrame,
    by_class: dict[tuple[str, str], str],
    product_fallback: dict[str, str],
    partner_lookup: dict[int, str],
) -> pd.DataFrame:
    needed = ["reporter_code", "year", "trade_value", *item_cols]
    values = values[needed].copy()
    values["trade_value"] = pd.to_numeric(values["trade_value"], errors="coerce")
    values = values.dropna(subset=["reporter_code", "year", "trade_value", *item_cols])
    values = values[values["trade_value"] > 0].copy()
    values["reporter_code"] = values["reporter_code"].astype(int)
    values["year"] = values["year"].astype(int)
    grouped = values.groupby(["reporter_code", "year", *item_cols], as_index=False)["trade_value"].sum()
    grouped["total_trade_value"] = grouped.groupby(["reporter_code", "year"])["trade_value"].transform("sum")
    grouped = grouped.sort_values(["reporter_code", "year", "trade_value"], ascending=[True, True, False])
    grouped["rank"] = grouped.groupby(["reporter_code", "year"]).cumcount() + 1
    top = grouped[grouped["rank"] <= 5].copy()
    top["share"] = top["trade_value"] / top["total_trade_value"].replace(0, np.nan)
    top["flow"] = flow
    top["dimension"] = dimension
    top = add_item_labels(top, dimension, by_class, product_fallback, partner_lookup)
    top = top.merge(country_panel, on="reporter_code", how="left")
    ordered = [
        "country",
        "iso3",
        "reporter_code",
        "year",
        "flow",
        "dimension",
        "rank",
        "item_code",
        "item_name",
        "classification_code",
        "trade_value",
        "total_trade_value",
        "share",
    ]
    return top[ordered].sort_values(["country", "year", "flow", "dimension", "rank"]).reset_index(drop=True)


def import_top5(
    country_panel: pd.DataFrame,
    by_class: dict[tuple[str, str], str],
    product_fallback: dict[str, str],
    partner_lookup: dict[int, str],
) -> pd.DataFrame:
    files = sorted(IMPORT_AGG_DIR.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No import aggregate files found in {IMPORT_AGG_DIR}")

    rows: list[pd.DataFrame] = []
    for idx, path in enumerate(files, start=1):
        df = pd.read_parquet(path, columns=["reporter_code", "year", "cmd_code", "partner_code", "trade_value"])
        rows.append(
            top5_from_values(
                df,
                "Imports",
                "product",
                ["cmd_code"],
                country_panel,
                by_class,
                product_fallback,
                partner_lookup,
            )
        )
        rows.append(
            top5_from_values(
                df,
                "Imports",
                "partner",
                ["partner_code"],
                country_panel,
                by_class,
                product_fallback,
                partner_lookup,
            )
        )
        if idx % 100 == 0:
            print(f"processed import aggregate files: {idx}/{len(files)}", flush=True)
    return pd.concat(rows, ignore_index=True)


def export_top5(
    country_panel: pd.DataFrame,
    by_class: dict[tuple[str, str], str],
    product_fallback: dict[str, str],
    partner_lookup: dict[int, str],
) -> pd.DataFrame:
    if not EXPORT_AGG_PATH.exists():
        raise FileNotFoundError(EXPORT_AGG_PATH)
    dataset = ds.dataset(EXPORT_AGG_PATH, format="parquet")
    product = dataset.to_table(
        columns=["reporter_code", "year", "classification_code", "cmd_code", "trade_value"],
        filter=ds.field("dimension") == "product",
    ).to_pandas()
    partner = dataset.to_table(
        columns=["reporter_code", "year", "partner_code", "trade_value"],
        filter=ds.field("dimension") == "partner",
    ).to_pandas()
    return pd.concat(
        [
            top5_from_values(
                product,
                "Exports",
                "product",
                ["classification_code", "cmd_code"],
                country_panel,
                by_class,
                product_fallback,
                partner_lookup,
            ),
            top5_from_values(
                partner,
                "Exports",
                "partner",
                ["partner_code"],
                country_panel,
                by_class,
                product_fallback,
                partner_lookup,
            ),
        ],
        ignore_index=True,
    )


def build_summary(top5: pd.DataFrame) -> pd.DataFrame:
    shares = (
        top5.pivot_table(
            index=["country", "iso3", "reporter_code", "year", "flow", "dimension", "total_trade_value"],
            columns="rank",
            values="share",
            aggfunc="sum",
        )
        .rename(columns={rank: f"top_{rank}_item_share" for rank in range(1, 6)})
        .reset_index()
    )
    for rank in range(1, 6):
        col = f"top_{rank}_item_share"
        if col not in shares.columns:
            shares[col] = 0.0
    rank_cols = [f"top_{rank}_item_share" for rank in range(1, 6)]
    shares["cumulative_top_5_share"] = shares[rank_cols].sum(axis=1)

    concentration = pd.read_parquet(CONCENTRATION_PATH)
    product = concentration[
        ["reporter_code", "year", "flow", "product_gini", "product_active_count"]
    ].rename(columns={"product_gini": "gini", "product_active_count": "active_count"})
    product["dimension"] = "product"
    partner = concentration[
        ["reporter_code", "year", "flow", "partner_gini", "partner_active_count", "top_5_partner_share"]
    ].rename(columns={"partner_gini": "gini", "partner_active_count": "active_count"})
    partner["dimension"] = "partner"
    metrics = pd.concat([product, partner], ignore_index=True)
    out = shares.merge(metrics, on=["reporter_code", "year", "flow", "dimension"], how="left")
    return out.sort_values(["country", "year", "flow", "dimension"]).reset_index(drop=True)


def latest_country_rows(df: pd.DataFrame) -> pd.DataFrame:
    max_year = df.groupby(["iso3", "flow", "dimension"], as_index=False)["year"].max()
    return df.merge(max_year, on=["iso3", "flow", "dimension", "year"], how="inner")


def normalize_item_code(series: pd.Series, dimension: str) -> pd.Series:
    out = series.astype(str).str.replace(r"\.0$", "", regex=True)
    return out.str.zfill(6) if dimension == "product" else out


def latest_import_dimension_values(latest_summary: pd.DataFrame) -> pd.DataFrame:
    keys = latest_summary[latest_summary["flow"].eq("Imports")][["reporter_code", "year"]].drop_duplicates().copy()
    key_set = set(keys.itertuples(index=False, name=None))
    product_frames: list[pd.DataFrame] = []
    partner_frames: list[pd.DataFrame] = []
    for path in sorted(IMPORT_AGG_DIR.glob("*.parquet")):
        df = pd.read_parquet(path, columns=["reporter_code", "year", "cmd_code", "partner_code", "trade_value"])
        if df.empty:
            continue
        reporter = int(df["reporter_code"].iloc[0])
        year = int(df["year"].iloc[0])
        if (reporter, year) not in key_set:
            continue
        product = df.groupby(["reporter_code", "year", "cmd_code"], as_index=False)["trade_value"].sum()
        product = product.rename(columns={"cmd_code": "item_code"})
        product["dimension"] = "product"
        partner = df.groupby(["reporter_code", "year", "partner_code"], as_index=False)["trade_value"].sum()
        partner = partner.rename(columns={"partner_code": "item_code"})
        partner["dimension"] = "partner"
        product_frames.append(product)
        partner_frames.append(partner)
    values = pd.concat([*product_frames, *partner_frames], ignore_index=True)
    values["flow"] = "Imports"
    return values[["reporter_code", "year", "flow", "dimension", "item_code", "trade_value"]]


def latest_export_dimension_values(latest_summary: pd.DataFrame) -> pd.DataFrame:
    if not EXPORT_AGG_PATH.exists():
        raise FileNotFoundError(EXPORT_AGG_PATH)
    keys = latest_summary[latest_summary["flow"].eq("Exports")][["reporter_code", "year", "dimension"]].drop_duplicates()
    frames: list[pd.DataFrame] = []
    dataset = ds.dataset(EXPORT_AGG_PATH, format="parquet")
    for dimension, item_col, columns in [
        ("product", "cmd_code", ["reporter_code", "year", "cmd_code", "trade_value"]),
        ("partner", "partner_code", ["reporter_code", "year", "partner_code", "trade_value"]),
    ]:
        table = dataset.to_table(columns=columns, filter=ds.field("dimension") == dimension)
        values = table.to_pandas()
        values["dimension"] = dimension
        keep = keys[keys["dimension"].eq(dimension)][["reporter_code", "year"]]
        values = values.merge(keep, on=["reporter_code", "year"], how="inner")
        values = values.groupby(["reporter_code", "year", item_col], as_index=False)["trade_value"].sum()
        values = values.rename(columns={item_col: "item_code"})
        values["dimension"] = dimension
        frames.append(values)
    out = pd.concat(frames, ignore_index=True)
    out["flow"] = "Exports"
    return out[["reporter_code", "year", "flow", "dimension", "item_code", "trade_value"]]


def latest_dimension_values(latest_summary: pd.DataFrame) -> pd.DataFrame:
    values = pd.concat(
        [latest_import_dimension_values(latest_summary), latest_export_dimension_values(latest_summary)],
        ignore_index=True,
    )
    values["reporter_code"] = values["reporter_code"].astype(int)
    values["year"] = values["year"].astype(int)
    values["trade_value"] = pd.to_numeric(values["trade_value"], errors="coerce")
    values = values.dropna(subset=["trade_value"])
    values = values[values["trade_value"] > 0].copy()
    values["item_code"] = np.where(
        values["dimension"].eq("product"),
        normalize_item_code(values["item_code"], "product"),
        normalize_item_code(values["item_code"], "partner"),
    )
    return values


def plot_cumulative_histograms(summary: pd.DataFrame) -> Path:
    EX01_FIGURES.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 2, figsize=(13, 8), sharex=True, sharey=True)
    specs = [
        ("Imports", "product", "Import products"),
        ("Imports", "partner", "Import partners"),
        ("Exports", "product", "Export products"),
        ("Exports", "partner", "Export partners"),
    ]
    for ax, (flow, dimension, title) in zip(axes.flat, specs, strict=False):
        data = summary[(summary["flow"] == flow) & (summary["dimension"] == dimension)]
        weights = np.ones(len(data)) / len(data) if len(data) else None
        ax.hist(
            data["cumulative_top_5_share"],
            bins=np.linspace(0, 1, 26),
            weights=weights,
            color="#2f5d62" if dimension == "product" else "#8c4f2b",
            alpha=0.82,
            edgecolor="white",
            linewidth=0.7,
        )
        median = data["cumulative_top_5_share"].median()
        ax.axvline(median, color="#111827", linewidth=1.4, linestyle="--", label=f"Median {median:.0%}")
        ax.set_title(title)
        ax.xaxis.set_major_formatter(PercentFormatter(1.0))
        ax.yaxis.set_major_formatter(PercentFormatter(1.0))
        ax.set_xlim(0, 1)
        ax.legend(frameon=False, fontsize=8)
    fig.supxlabel("Cumulative share of total trade value accounted for by top 5")
    fig.supylabel("Share of country-year observations")
    fig.suptitle("Exercise 1: Top-5 Trade Concentration Across Products and Partners", y=1.02)
    path = EX01_FIGURES / "top5_cumulative_share_histograms.png"
    plt.tight_layout()
    plt.savefig(path, dpi=220, bbox_inches="tight")
    plt.close()
    return path


def plot_rank_histograms(top5: pd.DataFrame) -> Path:
    EX01_FIGURES.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 2, figsize=(13, 8), sharex=True, sharey=True)
    specs = [
        ("Imports", "product", "Import products"),
        ("Imports", "partner", "Import partners"),
        ("Exports", "product", "Export products"),
        ("Exports", "partner", "Export partners"),
    ]
    palette = {1: "#111827", 2: "#2f5d62", 3: "#6b7fbd", 4: "#b7791f", 5: "#c43b3b"}
    for ax, (flow, dimension, title) in zip(axes.flat, specs, strict=False):
        data = top5[(top5["flow"] == flow) & (top5["dimension"] == dimension)].copy()
        data["rank"] = data["rank"].astype(int)
        sns.histplot(
            data=data,
            x="share",
            hue="rank",
            hue_order=[1, 2, 3, 4, 5],
            palette=palette,
            bins=np.linspace(0, 1, 31),
            stat="percent",
            common_norm=False,
            element="step",
            fill=False,
            linewidth=1.3,
            ax=ax,
        )
        ax.set_title(title)
        ax.xaxis.set_major_formatter(PercentFormatter(1.0))
        ax.set_xlabel("")
        ax.set_ylabel("")
    fig.supxlabel("Individual top-five item share of total trade value")
    fig.supylabel("Percent of observations within rank")
    fig.suptitle("Exercise 1: Distribution of Rank 1-5 Product/Partner Shares", y=1.02)
    path = EX01_FIGURES / "top5_rank_share_histograms.png"
    plt.tight_layout()
    plt.savefig(path, dpi=220, bbox_inches="tight")
    plt.close()
    return path


def concise_frequency_label(name: object, code: object, dimension: str) -> str:
    clean = " ".join(str(name).replace(";", ":").split())
    if dimension == "product":
        return f"{textwrap.shorten(clean, width=50, placeholder='...')} (HS {str(code).zfill(6)})"
    return textwrap.shorten(clean, width=44, placeholder="...")


def format_gini_contribution(value: float) -> str:
    if not np.isfinite(value):
        return ""
    if abs(value) < 0.0005:
        return "0.000"
    return f"{value:+.3f}"


def format_gini_contribution_share(value: float) -> str:
    if not np.isfinite(value):
        return ""
    if abs(value) < 0.00005:
        return "0.00%"
    return f"{100 * value:+.2f}%"


def build_latest_item_frequency(latest_items: pd.DataFrame, partner_ref: pd.DataFrame) -> pd.DataFrame:
    items = latest_items.copy()
    items["item_code_text"] = items["item_code"].astype(str).str.replace(r"\.0$", "", regex=True)
    items["item_code_norm"] = np.where(
        items["dimension"].eq("product"),
        items["item_code_text"].str.zfill(6),
        items["item_code_text"],
    )
    items["weighted_share"] = items["share"] * items["total_trade_value"]
    items["reporter_item"] = items["iso3"].astype(str) + "|" + items["flow"] + "|" + items["dimension"] + "|" + items["item_code_norm"]

    grouped = (
        items.groupby(["flow", "dimension", "item_code_norm", "item_name"], as_index=False)
        .agg(
            reporter_count=("iso3", "nunique"),
            appearances=("reporter_item", "nunique"),
            mean_rank=("rank", "mean"),
            median_share=("share", "median"),
            weighted_mean_share_numer=("weighted_share", "sum"),
            weighted_mean_share_denom=("total_trade_value", "sum"),
            total_trade_value=("trade_value", "sum"),
        )
        .rename(columns={"item_code_norm": "item_code"})
    )
    grouped["weighted_mean_share"] = grouped["weighted_mean_share_numer"] / grouped["weighted_mean_share_denom"].replace(0, np.nan)
    grouped = grouped.drop(columns=["weighted_mean_share_numer", "weighted_mean_share_denom"])

    partner = grouped[grouped["dimension"].eq("partner")].copy()
    if not partner.empty:
        ref = partner_ref.rename(columns={"partner_code": "item_code_int"}).copy()
        partner["item_code_int"] = pd.to_numeric(partner["item_code"], errors="coerce").astype("Int64")
        partner = partner.merge(ref, on="item_code_int", how="left")
        partner["partner_iso3"] = partner["partner_iso3"].fillna("")
        partner["is_real_histogram_item"] = partner["partner_iso3"].str.match(r"^[A-Z]{3}$", na=False)
        partner["display_label"] = [
            concise_frequency_label(name, code, "partner") for name, code in zip(partner["item_name"], partner["item_code"], strict=False)
        ]
        partner = partner.drop(columns=["item_code_int"])

    product = grouped[grouped["dimension"].eq("product")].copy()
    if not product.empty:
        product["partner_iso3"] = ""
        product["partner_name"] = ""
        product["is_real_histogram_item"] = ~(
            product["item_code"].eq("999999")
            | product["item_name"].str.contains("Commodities not specified", case=False, na=False)
        )
        product["display_label"] = [
            concise_frequency_label(name, code, "product") for name, code in zip(product["item_name"], product["item_code"], strict=False)
        ]

    out = pd.concat([product, partner], ignore_index=True)
    out["reporter_share"] = out["reporter_count"] / latest_items["iso3"].nunique()
    order_cols = [
        "flow",
        "dimension",
        "item_code",
        "item_name",
        "display_label",
        "partner_iso3",
        "partner_name",
        "is_real_histogram_item",
        "reporter_count",
        "reporter_share",
        "appearances",
        "mean_rank",
        "median_share",
        "weighted_mean_share",
        "total_trade_value",
    ]
    return out[order_cols].sort_values(
        ["flow", "dimension", "reporter_count", "total_trade_value", "item_name"],
        ascending=[True, True, False, False, True],
    ).reset_index(drop=True)


def panel_frequency_items(frequency: pd.DataFrame, flow: str, dimension: str) -> pd.DataFrame:
    return frequency[
        frequency["flow"].eq(flow)
        & frequency["dimension"].eq(dimension)
        & frequency["is_real_histogram_item"]
    ].nlargest(FREQUENCY_TOP_N, ["reporter_count", "total_trade_value"]).sort_values(
        ["reporter_count", "total_trade_value"], ascending=[True, True]
    )


def plot_latest_item_frequency_histograms(frequency: pd.DataFrame) -> Path:
    EX01_FIGURES.mkdir(parents=True, exist_ok=True)
    specs = [
        ("Imports", "partner", "Top supplier countries in importers' top 5"),
        ("Imports", "product", "Top imported products in importers' top 5"),
        ("Exports", "partner", "Top destination countries in exporters' top 5"),
        ("Exports", "product", "Top exported products in exporters' top 5"),
    ]
    colors = {"partner": "#8c4f2b", "product": "#2f5d62"}
    fig, axes = plt.subplots(2, 2, figsize=(15, 11))
    for ax, (flow, dimension, title) in zip(axes.flat, specs, strict=False):
        data = panel_frequency_items(frequency, flow, dimension)
        ax.barh(data["display_label"], data["reporter_count"], color=colors[dimension], alpha=0.86)
        for y_pos, value in enumerate(data["reporter_count"]):
            ax.text(value + 0.25, y_pos, f"{int(value)}", va="center", fontsize=8)
        ax.set_title(title)
        ax.set_xlabel("Number of reporter countries")
        ax.set_xlim(0, max(5, frequency["reporter_count"].max() + 2))
        ax.tick_params(axis="y", labelsize=8)
    fig.suptitle(
        "Latest Available Year: Items Appearing Most Often in Countries' Own Top 5",
        y=1.01,
    )
    path = EX01_FIGURES / "top5_item_frequency_latest_histograms.png"
    plt.tight_layout()
    plt.savefig(path, dpi=220, bbox_inches="tight")
    plt.close()
    return path


def build_latest_item_leave_one_out(
    latest_values: pd.DataFrame,
    latest_items: pd.DataFrame,
    frequency: pd.DataFrame,
) -> pd.DataFrame:
    candidate = frequency[frequency["is_real_histogram_item"]].copy()
    candidate = candidate[["flow", "dimension", "item_code", "item_name", "display_label"]].drop_duplicates()
    candidate["item_code"] = np.where(
        candidate["dimension"].eq("product"),
        normalize_item_code(candidate["item_code"], "product"),
        normalize_item_code(candidate["item_code"], "partner"),
    )
    top5 = latest_items[["reporter_code", "year", "flow", "dimension", "item_code"]].copy()
    top5["item_code"] = np.where(
        top5["dimension"].eq("product"),
        normalize_item_code(top5["item_code"], "product"),
        normalize_item_code(top5["item_code"], "partner"),
    )
    top5["top5_key"] = (
        top5["reporter_code"].astype(str)
        + "|"
        + top5["year"].astype(str)
        + "|"
        + top5["flow"]
        + "|"
        + top5["dimension"]
        + "|"
        + top5["item_code"]
    )
    top5_keys = set(top5["top5_key"])

    rows: list[dict[str, object]] = []
    for (flow, dimension), panel_candidates in candidate.groupby(["flow", "dimension"], sort=False):
        values = latest_values[latest_values["flow"].eq(flow) & latest_values["dimension"].eq(dimension)].copy()
        panel_codes = panel_candidates["item_code"].astype(str).tolist()
        labels = panel_candidates.set_index("item_code")[["item_name", "display_label"]].to_dict("index")
        for (reporter_code, year), group in values.groupby(["reporter_code", "year"], sort=False):
            item_values = group.groupby("item_code", as_index=False)["trade_value"].sum()
            full_values = item_values["trade_value"].to_numpy(dtype=float)
            full_gini = gini(full_values)
            value_by_code = item_values.set_index("item_code")["trade_value"].to_dict()
            for code in panel_codes:
                item_value = float(value_by_code.get(code, 0.0))
                is_present = item_value > 0
                without_values = item_values.loc[item_values["item_code"].ne(code), "trade_value"].to_numpy(dtype=float)
                without_gini = gini(without_values) if is_present else full_gini
                contribution = float(full_gini - without_gini) if np.isfinite(without_gini) else np.nan
                contribution_share = contribution / full_gini if np.isfinite(full_gini) and full_gini > 0 else np.nan
                top5_key = f"{int(reporter_code)}|{int(year)}|{flow}|{dimension}|{code}"
                rows.append(
                    {
                        "reporter_code": int(reporter_code),
                        "year": int(year),
                        "flow": flow,
                        "dimension": dimension,
                        "item_code": code,
                        "item_name": labels[code]["item_name"],
                        "display_label": labels[code]["display_label"],
                        "item_trade_value": item_value,
                        "item_present": is_present,
                        "item_top5_for_reporter": top5_key in top5_keys,
                        "full_gini": full_gini,
                        "gini_without_item": without_gini,
                        "gini_reduction_when_excluded": contribution,
                        "gini_reduction_when_excluded_share_of_gini": contribution_share,
                    }
                )
    detail = pd.DataFrame(rows)
    if detail.empty:
        return pd.DataFrame()

    summary_rows = []
    for keys, group in detail.groupby(["flow", "dimension", "item_code", "item_name", "display_label"], sort=False):
        top5_group = group[group["item_top5_for_reporter"]]
        present_group = group[group["item_present"]]
        summary_rows.append(
            {
                "flow": keys[0],
                "dimension": keys[1],
                "item_code": keys[2],
                "item_name": keys[3],
                "display_label": keys[4],
                "reporters_evaluated": int(group[["reporter_code", "year"]].drop_duplicates().shape[0]),
                "present_reporter_count": int(present_group[["reporter_code", "year"]].drop_duplicates().shape[0]),
                "top5_reporter_count": int(top5_group[["reporter_code", "year"]].drop_duplicates().shape[0]),
                "mean_loo_gini_contribution_all_reporters": group["gini_reduction_when_excluded"].mean(),
                "mean_loo_gini_contribution_present_reporters": present_group["gini_reduction_when_excluded"].mean(),
                "mean_loo_gini_contribution_top5_reporters": top5_group["gini_reduction_when_excluded"].mean(),
                "median_loo_gini_contribution_top5_reporters": top5_group["gini_reduction_when_excluded"].median(),
                "mean_loo_gini_contribution_share_all_reporters": group["gini_reduction_when_excluded_share_of_gini"].mean(),
                "mean_loo_gini_contribution_share_present_reporters": present_group["gini_reduction_when_excluded_share_of_gini"].mean(),
                "mean_loo_gini_contribution_share_top5_reporters": top5_group["gini_reduction_when_excluded_share_of_gini"].mean(),
                "median_loo_gini_contribution_share_top5_reporters": top5_group["gini_reduction_when_excluded_share_of_gini"].median(),
                "mean_full_gini": group["full_gini"].mean(),
            }
        )
    return pd.DataFrame(summary_rows).sort_values(["flow", "dimension", "top5_reporter_count"], ascending=[True, True, False])


def plot_latest_item_leave_one_out(
    frequency: pd.DataFrame,
    loo: pd.DataFrame,
    metric: str,
    title: str,
    path_name: str,
) -> Path:
    EX01_FIGURES.mkdir(parents=True, exist_ok=True)
    specs = [
        ("Imports", "partner", "Top supplier countries in importers' top 5"),
        ("Imports", "product", "Top imported products in importers' top 5"),
        ("Exports", "partner", "Top destination countries in exporters' top 5"),
        ("Exports", "product", "Top exported products in exporters' top 5"),
    ]
    colors = {"partner": "#8c4f2b", "product": "#2f5d62"}
    fig, axes = plt.subplots(2, 2, figsize=(15, 11))
    for ax, (flow, dimension, panel_title) in zip(axes.flat, specs, strict=False):
        base = panel_frequency_items(frequency, flow, dimension)[["flow", "dimension", "item_code", "display_label", "reporter_count", "total_trade_value"]]
        base["item_code"] = np.where(
            base["dimension"].eq("product"),
            normalize_item_code(base["item_code"], "product"),
            normalize_item_code(base["item_code"], "partner"),
        )
        data = base.merge(
            loo[["flow", "dimension", "item_code", metric]],
            on=["flow", "dimension", "item_code"],
            how="left",
        )
        data[metric] = data[metric].fillna(0.0)
        data = data.sort_values(metric, ascending=True).reset_index(drop=True)
        ax.barh(data["display_label"], data[metric], color=colors[dimension], alpha=0.86)
        ax.axvline(0, color="#111827", linewidth=0.9)
        for y_pos, value in enumerate(data[metric]):
            offset = 0.00025 if value >= 0 else -0.00025
            ha = "left" if value >= 0 else "right"
            formatter = format_gini_contribution_share if "share" in metric else format_gini_contribution
            ax.text(value + offset, y_pos, formatter(value), va="center", ha=ha, fontsize=8)
        max_abs = max(0.005, float(np.nanmax(np.abs(data[metric].to_numpy(dtype=float)))) * 1.35)
        ax.set_xlim(-max_abs, max_abs)
        if "share" in metric:
            ax.xaxis.set_major_formatter(PercentFormatter(1.0))
        ax.set_title(panel_title)
        xlabel = "Mean contribution as share of Gini" if "share" in metric else "Mean leave-one-out Gini contribution"
        ax.set_xlabel(xlabel)
        ax.tick_params(axis="y", labelsize=8)
    fig.suptitle(title, y=1.01)
    path = EX01_FIGURES / path_name
    plt.tight_layout()
    plt.savefig(path, dpi=220, bbox_inches="tight")
    plt.close()
    return path


def write_memo(
    summary: pd.DataFrame,
    top5: pd.DataFrame,
    cumulative_fig: Path,
    rank_fig: Path,
    frequency: pd.DataFrame,
    frequency_fig: Path,
    loo: pd.DataFrame,
    loo_all_fig: Path,
    loo_top5_fig: Path,
) -> None:
    latest = latest_country_rows(summary)
    med = summary.groupby(["flow", "dimension"], as_index=False).agg(
        median_cumulative_top_5_share=("cumulative_top_5_share", "median"),
        median_top_1_share=("top_1_item_share", "median"),
        median_gini=("gini", "median"),
        observations=("cumulative_top_5_share", "size"),
    )
    latest_med = latest.groupby(["flow", "dimension"], as_index=False).agg(
        latest_median_cumulative_top_5_share=("cumulative_top_5_share", "median"),
        latest_observations=("cumulative_top_5_share", "size"),
    )
    check = summary[summary["dimension"] == "partner"].copy()
    check["top5_partner_diff"] = (check["cumulative_top_5_share"] - check["top_5_partner_share"]).abs()
    max_partner_diff = check["top5_partner_diff"].max()
    median_partner_diff = check["top5_partner_diff"].median()
    p99_partner_diff = check["top5_partner_diff"].quantile(0.99)

    lines = [
        "# Exercise 1: Top-5 Product And Partner Concentration",
        "",
        "This memo reports exact top-five product and partner shares by country-year-flow.",
        "",
        "## Outputs",
        "",
        "- Top-five item table: `results/exercise_01_tables/top5_trade_concentration_items.csv`",
        "- Top-five country-year summary: `results/exercise_01_tables/top5_trade_concentration_summary.csv`",
        "- Latest-year top-five item table: `results/exercise_01_tables/top5_trade_concentration_latest_items.csv`",
        "- Latest-year item-frequency table: `results/exercise_01_tables/top5_item_frequency_latest.csv`",
        "- Latest-year item leave-one-out table: `results/exercise_01_tables/top5_item_leave_one_out_latest.csv`",
        f"- Cumulative histogram: `{cumulative_fig.relative_to(ROOT)}`",
        f"- Rank-share histogram: `{rank_fig.relative_to(ROOT)}`",
        f"- Item-frequency histogram: `{frequency_fig.relative_to(ROOT)}`",
        f"- Leave-one-out share-of-Gini histogram, all reporters: `{loo_all_fig.relative_to(ROOT)}`",
        f"- Leave-one-out share-of-Gini histogram, top-five reporters only: `{loo_top5_fig.relative_to(ROOT)}`",
        "",
        "## Median Shares Across All Country-Years",
        "",
        med.to_markdown(index=False, floatfmt=".3f"),
        "",
        "## Latest-Year Median Shares",
        "",
        latest_med.to_markdown(index=False, floatfmt=".3f"),
        "",
        "## Validation",
        "",
        "- Exact partner cumulative top-five shares were compared with the baseline "
        f"`top_5_partner_share`: median absolute difference `{median_partner_diff:.3e}`, "
        f"99th percentile `{p99_partner_diff:.3e}`, max `{max_partner_diff:.3e}`.",
        "",
        "## Latest-Year Most Common Top-Five Items",
        "",
        "Counts are the number of reporter countries whose own latest-year top five includes the item. "
        "Partner charts exclude non-country reporting buckets such as `Areas, nes`; product charts exclude HS `999999`.",
        "",
        frequency[frequency["is_real_histogram_item"]]
        .groupby(["flow", "dimension"], group_keys=False)
        .head(8)[["flow", "dimension", "item_name", "reporter_count", "mean_rank", "median_share"]]
        .to_markdown(index=False, floatfmt=".3f"),
        "",
        "## Latest-Year Mean Leave-One-Out Contributions",
        "",
        "`mean_loo_gini_contribution_share_all_reporters` first computes `(full_gini - gini_without_item) / full_gini` inside each latest reporter country, then averages those country-level ratios across all latest reporters. "
        "`mean_loo_gini_contribution_share_top5_reporters` averages the same country-level ratio only where the item is in that reporter's own top five. "
        "Positive values mean removing the item lowers Gini, so the item raises concentration as a share of the country's own Gini.",
        "",
        loo.sort_values(["flow", "dimension", "mean_loo_gini_contribution_share_top5_reporters"], ascending=[True, True, False])
        .groupby(["flow", "dimension"], group_keys=False)
        .head(8)[
            [
                "flow",
                "dimension",
                "item_name",
                "top5_reporter_count",
                "mean_loo_gini_contribution_share_all_reporters",
                "mean_loo_gini_contribution_share_top5_reporters",
            ]
        ]
        .to_markdown(index=False, floatfmt=".4f"),
    ]
    (RESULTS / "exercise_01_top5_trade_concentration.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    EX01_TABLES.mkdir(parents=True, exist_ok=True)
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    country_panel = load_country_panel()
    partner_ref = load_partner_reference()
    partner_lookup = load_partner_lookup()
    by_class, product_fallback = load_product_descriptions()

    print("Computing import top-five product and partner rows...", flush=True)
    imports = import_top5(country_panel, by_class, product_fallback, partner_lookup)
    print("Computing export top-five product and partner rows...", flush=True)
    exports = export_top5(country_panel, by_class, product_fallback, partner_lookup)

    top5 = pd.concat([imports, exports], ignore_index=True)
    top5 = top5.sort_values(["country", "year", "flow", "dimension", "rank"]).reset_index(drop=True)
    summary = build_summary(top5)
    latest_items = latest_country_rows(top5)
    latest_summary = latest_country_rows(summary)
    latest_frequency = build_latest_item_frequency(latest_items, partner_ref)
    print("Computing latest-year leave-one-out Gini contributions for common top-five items...", flush=True)
    latest_values = latest_dimension_values(latest_summary)
    latest_loo = build_latest_item_leave_one_out(latest_values, latest_items, latest_frequency)

    top5.to_parquet(DATA_PROCESSED / "top5_trade_concentration_items.parquet", index=False)
    summary.to_parquet(DATA_PROCESSED / "top5_trade_concentration_summary.parquet", index=False)
    latest_frequency.to_parquet(DATA_PROCESSED / "top5_item_frequency_latest.parquet", index=False)
    latest_loo.to_parquet(DATA_PROCESSED / "top5_item_leave_one_out_latest.parquet", index=False)
    top5.to_csv(EX01_TABLES / "top5_trade_concentration_items.csv", index=False)
    summary.to_csv(EX01_TABLES / "top5_trade_concentration_summary.csv", index=False)
    latest_items.to_csv(EX01_TABLES / "top5_trade_concentration_latest_items.csv", index=False)
    latest_summary.to_csv(EX01_TABLES / "top5_trade_concentration_latest_summary.csv", index=False)
    latest_frequency.to_csv(EX01_TABLES / "top5_item_frequency_latest.csv", index=False)
    latest_loo.to_csv(EX01_TABLES / "top5_item_leave_one_out_latest.csv", index=False)

    cumulative_fig = plot_cumulative_histograms(summary)
    rank_fig = plot_rank_histograms(top5)
    frequency_fig = plot_latest_item_frequency_histograms(latest_frequency)
    loo_all_fig = plot_latest_item_leave_one_out(
        latest_frequency,
        latest_loo,
        "mean_loo_gini_contribution_share_all_reporters",
        "Latest Available Year: Mean Item Leave-One-Out Contribution as Share of Gini Across All Reporters",
        "top5_item_leave_one_out_latest_all_reporters.png",
    )
    loo_top5_fig = plot_latest_item_leave_one_out(
        latest_frequency,
        latest_loo,
        "mean_loo_gini_contribution_share_top5_reporters",
        "Latest Available Year: Mean Item Leave-One-Out Contribution as Share of Gini Where Item Is Top 5",
        "top5_item_leave_one_out_latest_top5_reporters.png",
    )
    write_memo(summary, top5, cumulative_fig, rank_fig, latest_frequency, frequency_fig, latest_loo, loo_all_fig, loo_top5_fig)
    print(f"Wrote {len(top5):,} top-five item rows and {len(summary):,} country-year-flow-dimension summaries.", flush=True)
    print(f"Wrote {cumulative_fig.relative_to(ROOT)}", flush=True)
    print(f"Wrote {rank_fig.relative_to(ROOT)}", flush=True)
    print(f"Wrote {frequency_fig.relative_to(ROOT)}", flush=True)
    print(f"Wrote {loo_all_fig.relative_to(ROOT)}", flush=True)
    print(f"Wrote {loo_top5_fig.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
