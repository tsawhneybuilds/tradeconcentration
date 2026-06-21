#!/usr/bin/env python3
"""Build import product Gini diagnostics with and without energy.

Outputs are sample-specific for rd2_countries. Product-facing calculations keep
the project rule that HS6 999999 is not a real product category.
"""

from __future__ import annotations

import glob
import re
import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import PercentFormatter


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = ROOT / "results" / "samples" / "rd2_countries"
OUT_DIR = SAMPLE_DIR / "import_energy_gini_diagnostics"
CHECKPOINT_DIR = (
    ROOT
    / "data"
    / "processed"
    / "samples"
    / "rd2_countries"
    / "checkpoints"
    / "exercise_11_file_aggregates"
    / "import_cells"
)

RISING_COUNTRIES = [
    "Australia",
    "Finland",
    "Hungary",
    "Kyrgyzstan",
    "Norway",
    "China",
    "France",
    "Ireland",
    "Mexico",
    "Poland",
    "China, Hong Kong SAR",
    "Germany",
    "Italy",
    "New Zealand",
    "Singapore",
]

BENCHMARK_COUNTRIES = [
    "China, Hong Kong SAR",
    "China",
    "India",
    "Japan",
    "United States",
]


def load_panels() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    product = pd.read_csv(SAMPLE_DIR / "exercise_01_tables" / "product_concentration_all_years.csv")
    product = product[(product["flow"] == "Imports") & (product["variant"] == "baseline")].copy()
    product = product.rename(columns={"product_gini": "import_product_gini_with_energy"})
    product = product[
        [
            "country",
            "iso3",
            "reporter_code",
            "year",
            "total_trade_value",
            "import_product_gini_with_energy",
            "product_active_count",
        ]
    ]

    bins = pd.read_csv(SAMPLE_DIR / "exercise_03_tables" / "import_bin_decomposition.csv")
    ex_energy = bins[bins["import_bin"] == "energy"].copy()
    ex_energy = ex_energy.rename(
        columns={
            "product_gini_without_bin": "import_product_gini_ex_energy",
            "active_products_without_bin": "active_products_ex_energy",
            "top_1_product_share_without_bin": "top1_share_ex_energy",
            "top_5_product_share_without_bin": "top5_share_ex_energy",
            "import_value_share": "energy_import_share",
        }
    )
    ex_energy = ex_energy[
        [
            "country",
            "iso3",
            "reporter_code",
            "year",
            "import_product_gini_ex_energy",
            "active_products_ex_energy",
            "top1_share_ex_energy",
            "top5_share_ex_energy",
            "energy_import_share",
        ]
    ]

    merged = product.merge(
        ex_energy,
        on=["country", "iso3", "reporter_code", "year"],
        how="inner",
        validate="one_to_one",
    )
    return product, ex_energy, merged


def summarize_changes(panel: pd.DataFrame, countries: list[str]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for country in countries:
        c = panel[panel["country"] == country].sort_values("year")
        if c.empty:
            continue
        first = c.iloc[0]
        last = c.iloc[-1]
        rows.append(
            {
                "country": country,
                "start_year": int(first["year"]),
                "end_year": int(last["year"]),
                "with_energy_start": first["import_product_gini_with_energy"],
                "with_energy_end": last["import_product_gini_with_energy"],
                "with_energy_delta": last["import_product_gini_with_energy"]
                - first["import_product_gini_with_energy"],
                "ex_energy_start": first["import_product_gini_ex_energy"],
                "ex_energy_end": last["import_product_gini_ex_energy"],
                "ex_energy_delta": last["import_product_gini_ex_energy"]
                - first["import_product_gini_ex_energy"],
                "latest_energy_import_share": last["energy_import_share"],
                "latest_top1_nonenergy_share": last["top1_share_ex_energy"],
                "latest_top5_nonenergy_share": last["top5_share_ex_energy"],
                "latest_active_products_ex_energy": last["active_products_ex_energy"],
            }
        )
    return pd.DataFrame(rows)


def plot_country_lines(
    panel: pd.DataFrame,
    countries: list[str],
    value_col: str,
    title: str,
    outfile: Path,
    y_label: str = "Import product Gini",
) -> None:
    fig, ax = plt.subplots(figsize=(13, 8), constrained_layout=True)
    cmap = plt.get_cmap("tab20")
    for i, country in enumerate(countries):
        c = panel[panel["country"] == country].sort_values("year")
        if c.empty:
            continue
        ax.plot(
            c["year"],
            c[value_col],
            marker="o",
            markersize=3.5,
            linewidth=1.9,
            label=country,
            color=cmap(i % cmap.N),
        )
    ax.set_title(title, loc="left", fontsize=18, pad=12)
    ax.set_xlabel("Year")
    ax.set_ylabel(y_label)
    ax.grid(True, axis="both", color="#e5e7eb", linewidth=1)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(ncol=3, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.10))
    outfile.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(outfile, dpi=180, bbox_inches="tight")
    plt.close(fig)


def plot_with_without_small_multiples(panel: pd.DataFrame, countries: list[str], outfile: Path) -> None:
    fig, axes = plt.subplots(2, 3, figsize=(14, 8), sharex=False, sharey=True, constrained_layout=True)
    axes = axes.ravel()
    handles = labels = None
    for ax, country in zip(axes, countries):
        c = panel[panel["country"] == country].sort_values("year")
        if c.empty:
            ax.axis("off")
            continue
        ax.plot(
            c["year"],
            c["import_product_gini_with_energy"],
            color="#1f77b4",
            linewidth=2.1,
            label="With energy",
        )
        ax.plot(
            c["year"],
            c["import_product_gini_ex_energy"],
            color="#d62728",
            linewidth=2.1,
            linestyle="--",
            label="Ex energy",
        )
        ax.set_title(country, loc="left", fontsize=12)
        ax.grid(True, color="#e5e7eb", linewidth=1)
        ax.spines[["top", "right"]].set_visible(False)
        handles, labels = ax.get_legend_handles_labels()
    for ax in axes[len(countries) :]:
        ax.axis("off")
        if handles and labels:
            ax.legend(handles, labels, loc="center", frameon=False)
    fig.suptitle("Import product Gini: with energy vs excluding energy", x=0.02, ha="left", fontsize=18)
    outfile.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(outfile, dpi=180, bbox_inches="tight")
    plt.close(fig)


def latest_import_cell_file(reporter_code: int) -> Path | None:
    files = import_cell_files(reporter_code)
    if not files:
        return None
    return files[-1][1]


def import_cell_files(reporter_code: int) -> list[tuple[int, Path]]:
    pattern = CHECKPOINT_DIR / f"COMTRADE-FINAL-CA{reporter_code:03d}????H*.parquet"
    files = glob.glob(str(pattern))
    parsed: list[tuple[int, Path]] = []
    for file in files:
        match = re.search(rf"CA{reporter_code:03d}(\d{{4}})H", Path(file).name)
        if match:
            parsed.append((int(match.group(1)), Path(file)))
    parsed.sort()
    return parsed


def snapshot_import_cell_files(reporter_code: int) -> list[tuple[str, int, Path]]:
    files = import_cell_files(reporter_code)
    if not files:
        return []
    mid = len(files) // 2
    picks = [("start", files[0]), ("mid", files[mid]), ("end", files[-1])]
    out: list[tuple[str, int, Path]] = []
    seen: set[tuple[str, int]] = set()
    for snapshot, (year, file) in picks:
        key = (snapshot, year)
        if key not in seen:
            out.append((snapshot, year, file))
            seen.add(key)
    return out


def product_labels() -> pd.DataFrame:
    display_path = SAMPLE_DIR / "exercise_03_tables" / "import_bin_goods_country_share_2024.csv"
    display = pd.read_csv(display_path, usecols=["cmd_code", "display_name", "product_description"])
    display["cmd_code"] = display["cmd_code"].astype(str).str.zfill(6)
    display = display.drop_duplicates("cmd_code")

    mapping = pd.read_csv(
        ROOT / "data" / "processed" / "exercise_03_bec5_mapping_approved.csv",
        usecols=["classification_code", "cmd_code", "hs_desc_official", "hs_desc_if_available"],
    )
    mapping["cmd_code"] = mapping["cmd_code"].astype(str).str.zfill(6)
    mapping["fallback_description"] = mapping["hs_desc_official"].fillna(mapping["hs_desc_if_available"])
    mapping = mapping[["cmd_code", "fallback_description"]].dropna().drop_duplicates("cmd_code")

    labels = display.merge(mapping, on="cmd_code", how="outer")
    labels["product_label"] = labels["display_name"].fillna(labels["fallback_description"])
    labels["product_label"] = labels["product_label"].fillna("Unlabeled HS6 product")
    return labels[["cmd_code", "product_label"]]


def latest_top_nonenergy_goods(panel: pd.DataFrame, countries: list[str], top_n: int = 8) -> pd.DataFrame:
    labels = product_labels()
    rows: list[pd.DataFrame] = []
    country_codes = (
        panel[["country", "iso3", "reporter_code"]]
        .drop_duplicates()
        .set_index("country")
        .to_dict("index")
    )

    for country in countries:
        meta = country_codes.get(country)
        if not meta:
            continue
        file = latest_import_cell_file(int(meta["reporter_code"]))
        if file is None:
            continue
        cells = pd.read_parquet(file)
        cells["cmd_code"] = cells["cmd_code"].astype(str).str.zfill(6)
        cells = cells[(cells["exercise_03_bin"] != "energy") & (cells["cmd_code"] != "999999")].copy()
        product = (
            cells.groupby(["year", "cmd_code", "exercise_03_bin"], as_index=False)["trade_value"]
            .sum()
            .sort_values("trade_value", ascending=False)
        )
        total = product["trade_value"].sum()
        if total <= 0:
            continue
        product["share_nonenergy_imports"] = product["trade_value"] / total
        product = product.head(top_n).copy()
        product["rank"] = range(1, len(product) + 1)
        product["country"] = country
        product["iso3"] = meta["iso3"]
        product["reporter_code"] = int(meta["reporter_code"])
        product["source_file"] = file.name
        rows.append(product)

    if not rows:
        return pd.DataFrame()
    out = pd.concat(rows, ignore_index=True)
    out = out.merge(labels, on="cmd_code", how="left")
    out["product_label"] = out["product_label"].fillna("Unlabeled HS6 product")
    return out[
        [
            "country",
            "iso3",
            "reporter_code",
            "year",
            "rank",
            "cmd_code",
            "product_label",
            "exercise_03_bin",
            "trade_value",
            "share_nonenergy_imports",
            "source_file",
        ]
    ]


def nonenergy_product_shares(file: Path) -> pd.DataFrame:
    cells = pd.read_parquet(file)
    cells["cmd_code"] = cells["cmd_code"].astype(str).str.zfill(6)
    cells = cells[(cells["exercise_03_bin"] != "energy") & (cells["cmd_code"] != "999999")].copy()
    product = (
        cells.groupby(["year", "cmd_code", "exercise_03_bin"], as_index=False)["trade_value"]
        .sum()
        .sort_values("trade_value", ascending=False)
    )
    total = product["trade_value"].sum()
    if total <= 0:
        return pd.DataFrame()
    product["rank"] = range(1, len(product) + 1)
    product["share_nonenergy_imports"] = product["trade_value"] / total
    product["total_nonenergy_imports"] = total
    return product


def rank_bucket_metrics(file: Path) -> dict[str, float | int]:
    product = nonenergy_product_shares(file)
    if product.empty:
        return {}
    n = len(product)
    coef = (n - 2 * product["rank"] + 1) / n
    product["gini_contribution"] = coef * product["share_nonenergy_imports"]

    buckets = {
        "top5": product["rank"] <= 5,
        "rank6_50": product["rank"].between(6, 50),
        "rank51_200": product["rank"].between(51, 200),
        "rank201_plus": product["rank"] > 200,
    }
    out: dict[str, float | int] = {
        "year": int(product["year"].iloc[0]),
        "active_nonenergy_products": int(n),
        "total_nonenergy_imports": float(product["total_nonenergy_imports"].iloc[0]),
        "calculated_ex_energy_gini": float(product["gini_contribution"].sum()),
    }
    for bucket, mask in buckets.items():
        out[f"{bucket}_share"] = float(product.loc[mask, "share_nonenergy_imports"].sum())
        out[f"{bucket}_gini_contribution"] = float(product.loc[mask, "gini_contribution"].sum())
    return out


def import_cell_file_for_year(reporter_code: int, year: int) -> Path | None:
    for file_year, file in import_cell_files(reporter_code):
        if file_year == year:
            return file
    return None


def available_country_meta(panel: pd.DataFrame) -> pd.DataFrame:
    return panel[["country", "iso3", "reporter_code"]].drop_duplicates().sort_values("country")


def _driver_label(direction: str, bucket: str) -> str:
    if direction == "stable":
        return "stable / small Gini change"
    increasing = direction == "increase"
    labels = {
        "top5": "top-5 superstar concentration" if increasing else "top-5 deconcentration",
        "rank6_50": "upper-tier concentration (ranks 6-50)"
        if increasing
        else "upper-tier deconcentration (ranks 6-50)",
        "rank51_200": "broad upper-tail concentration (ranks 51-200)"
        if increasing
        else "broad upper-tail deconcentration (ranks 51-200)",
        "rank201_plus": "tail compression (rank 201+)"
        if increasing
        else "tail expansion (rank 201+)",
    }
    return labels.get(bucket, "mixed / unclassified")


def classify_driver(row: pd.Series, stable_threshold: float = 0.01) -> tuple[str, str, str]:
    buckets = ["top5", "rank6_50", "rank51_200", "rank201_plus"]
    delta_gini = float(row["delta_calculated_ex_energy_gini"])
    if abs(delta_gini) < stable_threshold:
        abs_bucket = max(buckets, key=lambda b: abs(float(row[f"delta_{b}_gini_contribution"])))
        return "stable", abs_bucket, _driver_label("stable", abs_bucket)
    if delta_gini > 0:
        bucket = max(buckets, key=lambda b: float(row[f"delta_{b}_gini_contribution"]))
        return "increase", bucket, _driver_label("increase", bucket)
    bucket = min(buckets, key=lambda b: float(row[f"delta_{b}_gini_contribution"]))
    return "decrease", bucket, _driver_label("decrease", bucket)


def gini_driver_classification(
    panel: pd.DataFrame,
    period_name: str,
    start_year: int | None = None,
    end_year: int | None = None,
    require_balanced_years: bool = False,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    meta = available_country_meta(panel)

    for item in meta.itertuples(index=False):
        files = import_cell_files(int(item.reporter_code))
        if not files:
            continue
        available_years = [year for year, _ in files]
        if start_year is None or end_year is None:
            chosen_start, start_file = files[0]
            chosen_end, end_file = files[-1]
        else:
            if require_balanced_years:
                required = set(range(start_year, end_year + 1))
                if not required.issubset(set(available_years)):
                    continue
            start_file = import_cell_file_for_year(int(item.reporter_code), start_year)
            end_file = import_cell_file_for_year(int(item.reporter_code), end_year)
            if start_file is None or end_file is None:
                continue
            chosen_start, chosen_end = start_year, end_year

        start = rank_bucket_metrics(start_file)
        end = rank_bucket_metrics(end_file)
        if not start or not end:
            continue
        row: dict[str, object] = {
            "period": period_name,
            "country": item.country,
            "iso3": item.iso3,
            "reporter_code": int(item.reporter_code),
            "start_year": chosen_start,
            "end_year": chosen_end,
            "start_source_file": start_file.name,
            "end_source_file": end_file.name,
        }
        for key, value in start.items():
            row[f"start_{key}"] = value
        for key, value in end.items():
            row[f"end_{key}"] = value
        row["delta_calculated_ex_energy_gini"] = (
            float(end["calculated_ex_energy_gini"]) - float(start["calculated_ex_energy_gini"])
        )
        row["delta_active_nonenergy_products"] = (
            int(end["active_nonenergy_products"]) - int(start["active_nonenergy_products"])
        )
        for bucket in ["top5", "rank6_50", "rank51_200", "rank201_plus"]:
            row[f"delta_{bucket}_share"] = float(end[f"{bucket}_share"]) - float(start[f"{bucket}_share"])
            row[f"delta_{bucket}_gini_contribution"] = float(
                end[f"{bucket}_gini_contribution"]
            ) - float(start[f"{bucket}_gini_contribution"])
        direction, bucket, label = classify_driver(pd.Series(row))
        row["gini_change_direction"] = direction
        row["main_driver_bucket"] = bucket
        row["main_driver_group"] = label
        rows.append(row)

    out = pd.DataFrame(rows)
    if out.empty:
        return out

    panel_gini = panel[["country", "reporter_code", "year", "import_product_gini_ex_energy"]].copy()
    start_panel = panel_gini.rename(
        columns={
            "year": "start_year",
            "import_product_gini_ex_energy": "start_panel_ex_energy_gini",
        }
    )
    end_panel = panel_gini.rename(
        columns={
            "year": "end_year",
            "import_product_gini_ex_energy": "end_panel_ex_energy_gini",
        }
    )
    out = out.merge(
        start_panel,
        on=["country", "reporter_code", "start_year"],
        how="left",
        validate="many_to_one",
    )
    out = out.merge(
        end_panel,
        on=["country", "reporter_code", "end_year"],
        how="left",
        validate="many_to_one",
    )
    out["delta_panel_ex_energy_gini"] = out["end_panel_ex_energy_gini"] - out["start_panel_ex_energy_gini"]
    out["calculated_vs_panel_delta_gap"] = (
        out["delta_calculated_ex_energy_gini"] - out["delta_panel_ex_energy_gini"]
    )
    return out.sort_values("delta_calculated_ex_energy_gini", ascending=False)


def write_driver_summary(classification: pd.DataFrame, outfile: Path) -> pd.DataFrame:
    if classification.empty:
        summary = pd.DataFrame()
    else:
        summary = (
            classification.groupby(["period", "gini_change_direction", "main_driver_group"], as_index=False)
            .agg(
                countries=("country", "nunique"),
                median_delta_gini=("delta_calculated_ex_energy_gini", "median"),
                mean_delta_gini=("delta_calculated_ex_energy_gini", "mean"),
            )
            .sort_values(["period", "gini_change_direction", "countries"], ascending=[True, True, False])
        )
    summary.to_csv(outfile, index=False)
    return summary


def plot_driver_contributions(classification: pd.DataFrame, outfile: Path, title: str) -> None:
    if classification.empty:
        return
    plot = classification.sort_values("delta_calculated_ex_energy_gini", ascending=True).copy()
    colors = {
        "top5": "#1f77b4",
        "rank6_50": "#ffbf69",
        "rank51_200": "#8ecae6",
        "rank201_plus": "#9ca3af",
    }
    labels = {
        "top5": "Top 5",
        "rank6_50": "Ranks 6-50",
        "rank51_200": "Ranks 51-200",
        "rank201_plus": "Rank 201+ tail",
    }
    y = range(len(plot))
    fig_height = max(10, len(plot) * 0.27)
    fig, ax = plt.subplots(figsize=(12, fig_height), constrained_layout=True)
    positive_left = pd.Series(0.0, index=plot.index)
    negative_left = pd.Series(0.0, index=plot.index)
    for bucket in ["top5", "rank6_50", "rank51_200", "rank201_plus"]:
        values = plot[f"delta_{bucket}_gini_contribution"]
        positive = values.clip(lower=0)
        negative = values.clip(upper=0)
        ax.barh(
            y,
            positive,
            left=positive_left,
            color=colors[bucket],
            label=labels[bucket],
            alpha=0.86,
        )
        ax.barh(y, negative, left=negative_left, color=colors[bucket], alpha=0.86)
        positive_left = positive_left + positive
        negative_left = negative_left + negative
    ax.axvline(0, color="#111827", linewidth=1)
    ax.set_yticks(list(y))
    ax.set_yticklabels(plot["country"], fontsize=8)
    ax.set_xlabel("Change in ex-energy import Product Gini contribution")
    ax.set_title(title, loc="left", fontsize=16)
    ax.grid(True, axis="x", color="#e5e7eb", linewidth=1)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(ncol=4, frameon=False, loc="lower center", bbox_to_anchor=(0.5, -0.045))
    outfile.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(outfile, dpi=180, bbox_inches="tight")
    plt.close(fig)


def plot_driver_group_counts(summary: pd.DataFrame, outfile: Path, title: str) -> None:
    if summary.empty:
        return
    plot = summary[summary["gini_change_direction"] != "stable"].copy()
    plot["label"] = plot["gini_change_direction"].str.title() + ": " + plot["main_driver_group"]
    plot = plot.sort_values("countries", ascending=True)
    fig_height = max(6, len(plot) * 0.55)
    fig, ax = plt.subplots(figsize=(10, fig_height), constrained_layout=True)
    ax.barh(plot["label"], plot["countries"], color="#2f6f9f")
    ax.set_xlabel("Countries")
    ax.set_title(title, loc="left", fontsize=16)
    ax.grid(True, axis="x", color="#e5e7eb", linewidth=1)
    ax.spines[["top", "right"]].set_visible(False)
    fig.savefig(outfile, dpi=180, bbox_inches="tight")
    plt.close(fig)


def start_mid_end_product_diagnostics(
    panel: pd.DataFrame,
    countries: list[str],
    top_n: int = 10,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    labels = product_labels()
    country_codes = (
        panel[["country", "iso3", "reporter_code"]]
        .drop_duplicates()
        .set_index("country")
        .to_dict("index")
    )
    top_rows: list[pd.DataFrame] = []
    decomp_rows: list[dict[str, object]] = []

    for country in countries:
        meta = country_codes.get(country)
        if not meta:
            continue
        for snapshot, snapshot_year, file in snapshot_import_cell_files(int(meta["reporter_code"])):
            product = nonenergy_product_shares(file)
            if product.empty:
                continue
            product["country"] = country
            product["iso3"] = meta["iso3"]
            product["reporter_code"] = int(meta["reporter_code"])
            product["snapshot"] = snapshot
            product["snapshot_year"] = snapshot_year
            product["source_file"] = file.name

            top = product.head(top_n).copy()
            top_rows.append(top)

            decomp_rows.append(
                {
                    "country": country,
                    "iso3": meta["iso3"],
                    "reporter_code": int(meta["reporter_code"]),
                    "snapshot": snapshot,
                    "year": snapshot_year,
                    "top5_share": product.loc[product["rank"] <= 5, "share_nonenergy_imports"].sum(),
                    "rank6_50_share": product.loc[
                        product["rank"].between(6, 50), "share_nonenergy_imports"
                    ].sum(),
                    "rank51_200_share": product.loc[
                        product["rank"].between(51, 200), "share_nonenergy_imports"
                    ].sum(),
                    "rank201_plus_share": product.loc[
                        product["rank"] > 200, "share_nonenergy_imports"
                    ].sum(),
                    "long_tail_rank51_plus_share": product.loc[
                        product["rank"] > 50, "share_nonenergy_imports"
                    ].sum(),
                    "top10_share": product.loc[product["rank"] <= 10, "share_nonenergy_imports"].sum(),
                    "active_nonenergy_products": len(product),
                    "total_nonenergy_imports": product["total_nonenergy_imports"].iloc[0],
                    "source_file": file.name,
                }
            )

    if top_rows:
        top_out = pd.concat(top_rows, ignore_index=True).merge(labels, on="cmd_code", how="left")
        top_out["product_label"] = top_out["product_label"].fillna("Unlabeled HS6 product")
        top_out = top_out[
            [
                "country",
                "iso3",
                "reporter_code",
                "snapshot",
                "year",
                "rank",
                "cmd_code",
                "product_label",
                "exercise_03_bin",
                "trade_value",
                "share_nonenergy_imports",
                "total_nonenergy_imports",
                "source_file",
            ]
        ]
    else:
        top_out = pd.DataFrame()

    decomp_out = pd.DataFrame(decomp_rows)
    return top_out, decomp_out


def _short_label(text: object, width: int = 34) -> str:
    cleaned = str(text).replace("\n", " ")
    return "\n".join(textwrap.wrap(cleaned, width=width, max_lines=2, placeholder="..."))


def plot_top10_snapshot_figures(top_goods: pd.DataFrame, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for country, country_df in top_goods.groupby("country", sort=False):
        snapshots = ["start", "mid", "end"]
        fig, axes = plt.subplots(1, 3, figsize=(15, 6), sharex=True, constrained_layout=True)
        for ax, snapshot in zip(axes, snapshots):
            sub = country_df[country_df["snapshot"] == snapshot].sort_values("rank", ascending=False)
            if sub.empty:
                ax.axis("off")
                continue
            labels = [f"{row.cmd_code}  {_short_label(row.product_label)}" for row in sub.itertuples()]
            ax.barh(labels, sub["share_nonenergy_imports"], color="#2f6f9f")
            year = int(sub["year"].iloc[0])
            ax.set_title(f"{snapshot.title()} ({year})", loc="left", fontsize=12)
            ax.xaxis.set_major_formatter(PercentFormatter(1.0))
            ax.grid(True, axis="x", color="#e5e7eb", linewidth=1)
            ax.spines[["top", "right"]].set_visible(False)
            ax.tick_params(axis="y", labelsize=8)
        fig.suptitle(f"{country}: top 10 non-energy HS6 import shares", x=0.02, ha="left", fontsize=16)
        filename = re.sub(r"[^A-Za-z0-9]+", "_", country).strip("_").lower()
        fig.savefig(out_dir / f"{filename}_top10_nonenergy_import_shares_start_mid_end.png", dpi=180)
        plt.close(fig)


def plot_rank_decomposition(decomp: pd.DataFrame, outfile: Path) -> None:
    if decomp.empty:
        return
    end_order = (
        decomp[decomp["snapshot"] == "end"]
        .assign(concentration_share=lambda x: x["top5_share"] + x["rank6_50_share"])
        .sort_values("top5_share", ascending=True)["country"]
        .tolist()
    )
    plot = decomp.copy()
    plot["country"] = pd.Categorical(plot["country"], categories=end_order, ordered=True)
    plot["label"] = plot["country"].astype(str) + "  " + plot["snapshot"] + " " + plot["year"].astype(str)
    plot = plot.sort_values(["country", "year"])

    fig_height = max(10, len(plot) * 0.33)
    fig, ax = plt.subplots(figsize=(12, fig_height), constrained_layout=True)
    y = range(len(plot))
    ax.barh(y, plot["top5_share"], color="#1f77b4", label="Top 5")
    ax.barh(
        y,
        plot["rank6_50_share"],
        left=plot["top5_share"],
        color="#ffbf69",
        label="Ranks 6-50",
    )
    left = plot["top5_share"] + plot["rank6_50_share"]
    ax.barh(
        y,
        plot["long_tail_rank51_plus_share"],
        left=left,
        color="#d1d5db",
        label="Rank 51+ tail",
    )
    ax.set_yticks(list(y))
    ax.set_yticklabels(plot["label"], fontsize=8)
    ax.xaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_xlabel("Share of non-energy imports")
    ax.set_title(
        "Non-energy import basket decomposition: top products versus long tail",
        loc="left",
        fontsize=16,
    )
    ax.grid(True, axis="x", color="#e5e7eb", linewidth=1)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(ncol=3, frameon=False, loc="lower center", bbox_to_anchor=(0.5, -0.04))
    outfile.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(outfile, dpi=180, bbox_inches="tight")
    plt.close(fig)


def plot_refined_rank_decomposition(decomp: pd.DataFrame, outfile: Path) -> None:
    if decomp.empty:
        return
    end_order = (
        decomp[decomp["snapshot"] == "end"]
        .sort_values("top5_share", ascending=True)["country"]
        .tolist()
    )
    plot = decomp.copy()
    plot["country"] = pd.Categorical(plot["country"], categories=end_order, ordered=True)
    plot["label"] = plot["country"].astype(str) + "  " + plot["snapshot"] + " " + plot["year"].astype(str)
    plot = plot.sort_values(["country", "year"])

    fig_height = max(10, len(plot) * 0.33)
    fig, ax = plt.subplots(figsize=(12, fig_height), constrained_layout=True)
    y = range(len(plot))
    left = pd.Series(0.0, index=plot.index)
    buckets = [
        ("top5_share", "Top 5", "#1f77b4"),
        ("rank6_50_share", "Ranks 6-50", "#ffbf69"),
        ("rank51_200_share", "Ranks 51-200", "#8ecae6"),
        ("rank201_plus_share", "Rank 201+ tail", "#d1d5db"),
    ]
    for col, label, color in buckets:
        ax.barh(y, plot[col], left=left.to_numpy(), color=color, label=label)
        left = left + plot[col]
    ax.set_yticks(list(y))
    ax.set_yticklabels(plot["label"], fontsize=8)
    ax.xaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_xlabel("Share of non-energy imports")
    ax.set_title(
        "Non-energy import basket decomposition: refined rank buckets",
        loc="left",
        fontsize=16,
    )
    ax.grid(True, axis="x", color="#e5e7eb", linewidth=1)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(ncol=4, frameon=False, loc="lower center", bbox_to_anchor=(0.5, -0.04))
    outfile.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(outfile, dpi=180, bbox_inches="tight")
    plt.close(fig)


def plot_overall_gini_trend(panel: pd.DataFrame, outfile: Path) -> pd.DataFrame:
    yearly = (
        panel.groupby("year", as_index=False)
        .agg(
            median_with_energy=("import_product_gini_with_energy", "median"),
            median_ex_energy=("import_product_gini_ex_energy", "median"),
            countries=("country", "nunique"),
        )
        .sort_values("year")
    )
    fig, ax = plt.subplots(figsize=(11, 6), constrained_layout=True)
    ax.plot(yearly["year"], yearly["median_with_energy"], color="#1f77b4", linewidth=2.4, label="With energy")
    ax.plot(
        yearly["year"],
        yearly["median_ex_energy"],
        color="#d62728",
        linewidth=2.4,
        linestyle="--",
        label="Ex energy",
    )
    ax.set_title("Median rd2 import product Gini rises over time", loc="left", fontsize=16)
    ax.set_xlabel("Year")
    ax.set_ylabel("Median import product Gini")
    ax.grid(True, color="#e5e7eb", linewidth=1)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False)
    fig.savefig(outfile, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return yearly


def plot_balanced_gini_trend(panel: pd.DataFrame, start_year: int, end_year: int, outfile: Path) -> pd.DataFrame:
    window = panel[panel["year"].between(start_year, end_year)].copy()
    complete_counts = window.groupby("country")["year"].nunique()
    complete_countries = complete_counts[complete_counts == (end_year - start_year + 1)].index
    balanced = window[window["country"].isin(complete_countries)].copy()
    yearly = (
        balanced.groupby("year", as_index=False)
        .agg(
            median_with_energy=("import_product_gini_with_energy", "median"),
            median_ex_energy=("import_product_gini_ex_energy", "median"),
            countries=("country", "nunique"),
        )
        .sort_values("year")
    )
    fig, ax = plt.subplots(figsize=(11, 6), constrained_layout=True)
    ax.plot(yearly["year"], yearly["median_with_energy"], color="#1f77b4", linewidth=2.4, label="With energy")
    ax.plot(
        yearly["year"],
        yearly["median_ex_energy"],
        color="#d62728",
        linewidth=2.4,
        linestyle="--",
        label="Ex energy",
    )
    ax.set_title(
        f"Median rd2 import product Gini rises in a balanced {start_year}-{end_year} panel",
        loc="left",
        fontsize=16,
    )
    ax.set_xlabel("Year")
    ax.set_ylabel("Median import product Gini")
    ax.grid(True, color="#e5e7eb", linewidth=1)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False)
    fig.savefig(outfile, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return yearly


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    product, ex_energy, merged = load_panels()

    plot_country_lines(
        product,
        RISING_COUNTRIES,
        "import_product_gini_with_energy",
        "Import Product Gini over time, energy included",
        OUT_DIR / "import_product_gini_with_energy_rising_countries.png",
    )
    plot_country_lines(
        product,
        BENCHMARK_COUNTRIES,
        "import_product_gini_with_energy",
        "Import Product Gini over time, energy included",
        OUT_DIR / "import_product_gini_with_energy_benchmark_countries.png",
    )
    plot_with_without_small_multiples(
        merged,
        BENCHMARK_COUNTRIES,
        OUT_DIR / "import_product_gini_with_vs_ex_energy_benchmarks.png",
    )

    all_countries = list(dict.fromkeys(RISING_COUNTRIES + BENCHMARK_COUNTRIES))
    summary = summarize_changes(merged, all_countries)
    summary.to_csv(OUT_DIR / "import_product_gini_with_vs_ex_energy_summary.csv", index=False)

    top_goods = latest_top_nonenergy_goods(merged, all_countries)
    top_goods.to_csv(OUT_DIR / "latest_top_nonenergy_import_goods.csv", index=False)

    top10_snapshots, rank_decomp = start_mid_end_product_diagnostics(merged, all_countries)
    top10_snapshots.to_csv(OUT_DIR / "top10_nonenergy_import_goods_start_mid_end.csv", index=False)
    rank_decomp.to_csv(OUT_DIR / "nonenergy_import_rank_decomposition_start_mid_end.csv", index=False)
    plot_top10_snapshot_figures(top10_snapshots, OUT_DIR / "top10_start_mid_end_figures")
    plot_rank_decomposition(
        rank_decomp,
        OUT_DIR / "nonenergy_import_rank_decomposition_start_mid_end.png",
    )
    plot_refined_rank_decomposition(
        rank_decomp,
        OUT_DIR / "nonenergy_import_rank_decomposition_start_mid_end_refined.png",
    )
    yearly_trend = plot_overall_gini_trend(
        merged,
        OUT_DIR / "median_import_product_gini_with_vs_ex_energy_all_rd2.png",
    )
    yearly_trend.to_csv(OUT_DIR / "median_import_product_gini_with_vs_ex_energy_all_rd2.csv", index=False)
    balanced_trend = plot_balanced_gini_trend(
        merged,
        2000,
        2024,
        OUT_DIR / "median_import_product_gini_with_vs_ex_energy_balanced_2000_2024.png",
    )
    balanced_trend.to_csv(
        OUT_DIR / "median_import_product_gini_with_vs_ex_energy_balanced_2000_2024.csv",
        index=False,
    )

    full_driver = gini_driver_classification(merged, "full_available")
    full_driver.to_csv(
        OUT_DIR / "ex_energy_rank_bucket_gini_driver_classification_full_available.csv",
        index=False,
    )
    full_summary = write_driver_summary(
        full_driver,
        OUT_DIR / "ex_energy_rank_bucket_gini_driver_summary_full_available.csv",
    )
    plot_driver_contributions(
        full_driver,
        OUT_DIR / "ex_energy_rank_bucket_gini_driver_contributions_full_available.png",
        "Ex-energy import Product Gini change by rank-bucket contribution, full available window",
    )
    plot_driver_group_counts(
        full_summary,
        OUT_DIR / "ex_energy_rank_bucket_gini_driver_groups_full_available.png",
        "Main drivers of ex-energy import Product Gini change, full available window",
    )

    balanced_driver = gini_driver_classification(
        merged,
        "balanced_2000_2024",
        start_year=2000,
        end_year=2024,
        require_balanced_years=True,
    )
    balanced_driver.to_csv(
        OUT_DIR / "ex_energy_rank_bucket_gini_driver_classification_balanced_2000_2024.csv",
        index=False,
    )
    balanced_summary = write_driver_summary(
        balanced_driver,
        OUT_DIR / "ex_energy_rank_bucket_gini_driver_summary_balanced_2000_2024.csv",
    )
    plot_driver_contributions(
        balanced_driver,
        OUT_DIR / "ex_energy_rank_bucket_gini_driver_contributions_balanced_2000_2024.png",
        "Ex-energy import Product Gini change by rank-bucket contribution, balanced 2000-2024",
    )
    plot_driver_group_counts(
        balanced_summary,
        OUT_DIR / "ex_energy_rank_bucket_gini_driver_groups_balanced_2000_2024.png",
        "Main drivers of ex-energy import Product Gini change, balanced 2000-2024",
    )

    print(f"Wrote {OUT_DIR}")
    print(f"Summary rows: {len(summary)}")
    print(f"Top-good rows: {len(top_goods)}")
    print(f"Top-10 snapshot rows: {len(top10_snapshots)}")
    print(f"Rank decomposition rows: {len(rank_decomp)}")
    print(f"Full driver rows: {len(full_driver)}")
    print(f"Balanced 2000-2024 driver rows: {len(balanced_driver)}")


if __name__ == "__main__":
    main()
