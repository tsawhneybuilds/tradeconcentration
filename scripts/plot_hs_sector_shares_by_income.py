#!/usr/bin/env python3
"""Plot country HS section export shares against GDP per capita measures."""

from __future__ import annotations

import argparse
import math
import sys
import time
import textwrap
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
from matplotlib.ticker import FuncFormatter, PercentFormatter

from plot_hs_section_line_value_shares import (
    COUNTRY_SAMPLE_CHOICES,
    EXCLUDED_HS6_CODES,
    HS_SECTION_CASE,
    ROOT,
    SECTION_LABELS,
    sample_aggregate_glob,
)


DATA_PROCESSED = ROOT / "data" / "processed"
RESULTS = ROOT / "results"
WORLD_BANK_URL = "https://api.worldbank.org/v2/country/{countries}/indicator/{indicator}"
WORLD_BANK_INDICATORS = {
    "gdp_pc_current_usd": {
        "indicator": "NY.GDP.PCAP.CD",
        "label": "GDP per capita (current US$)",
    },
    "gdp_pc_ppp_current_intl_usd": {
        "indicator": "NY.GDP.PCAP.PP.CD",
        "label": "GDP per capita, PPP (current international $)",
    },
}
WORLD_BANK_BATCH_SIZE = 20


def sample_country_panel_path(country_sample: str) -> Path:
    if country_sample == "prof_p_33":
        return DATA_PROCESSED / "comtrade_country_panel.csv"
    return DATA_PROCESSED / "samples" / country_sample / "comtrade_country_panel.csv"


def sample_processed_path(filename: str, country_sample: str) -> Path:
    if country_sample == "prof_p_33":
        return DATA_PROCESSED / filename
    return DATA_PROCESSED / "samples" / country_sample / filename


def sample_result_dir(country_sample: str) -> Path:
    if country_sample == "prof_p_33":
        return RESULTS / "hs_sector_income_diagnostics"
    return RESULTS / "samples" / country_sample / "hs_sector_income_diagnostics"


def read_country_panel(country_sample: str) -> pd.DataFrame:
    path = sample_country_panel_path(country_sample)
    if not path.exists():
        raise FileNotFoundError(f"No country panel found at {path}")
    countries = pd.read_csv(path)
    required = ["country", "iso3", "reporter_code"]
    missing = set(required).difference(countries.columns)
    if missing:
        raise ValueError(f"Country panel is missing columns: {sorted(missing)}")
    countries = countries[required].copy()
    countries["iso3"] = countries["iso3"].astype(str).str.upper()
    countries["reporter_code"] = pd.to_numeric(countries["reporter_code"], errors="coerce").astype("Int64")
    countries = countries.dropna(subset=["reporter_code"]).copy()
    countries["reporter_code"] = countries["reporter_code"].astype(int)
    return countries.drop_duplicates(["reporter_code", "iso3"])


def read_cached_controls(path: Path) -> pd.DataFrame:
    required = ["iso3", "year", *WORLD_BANK_INDICATORS]
    if not path.exists():
        return pd.DataFrame(columns=required)
    controls = pd.read_csv(path)
    missing = [col for col in required if col not in controls.columns]
    if missing:
        return pd.DataFrame(columns=required)
    controls = controls[required].copy()
    controls["iso3"] = controls["iso3"].astype(str).str.upper()
    controls["year"] = pd.to_numeric(controls["year"], errors="coerce")
    for col in WORLD_BANK_INDICATORS:
        controls[col] = pd.to_numeric(controls[col], errors="coerce")
    controls = controls.dropna(subset=["iso3", "year"])
    controls["year"] = controls["year"].astype(int)
    return controls.drop_duplicates(["iso3", "year"], keep="last")


def fetch_world_bank_indicator(
    iso3s: list[str],
    indicator: str,
    value_name: str,
    start_year: int,
    end_year: int,
) -> pd.DataFrame:
    rows: list[dict] = []
    unique_iso3s = sorted(set(iso3s))
    for start in range(0, len(unique_iso3s), WORLD_BANK_BATCH_SIZE):
        countries = ";".join(unique_iso3s[start : start + WORLD_BANK_BATCH_SIZE])
        url = WORLD_BANK_URL.format(countries=countries, indicator=indicator)
        page = 1
        pages = 1
        while page <= pages:
            params = {
                "format": "json",
                "per_page": 20000,
                "page": page,
                "date": f"{start_year}:{end_year}",
            }
            response = requests.get(url, params=params, timeout=45)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list) or len(payload) < 2:
                break
            meta = payload[0] if isinstance(payload[0], dict) else {}
            pages = int(meta.get("pages") or pages)
            for item in payload[1]:
                iso3 = str((item.get("countryiso3code") or "")).strip().upper()
                value = item.get("value")
                if iso3 and value is not None:
                    rows.append({"iso3": iso3, "year": int(item["date"]), value_name: value})
            page += 1
            time.sleep(0.1)
    return pd.DataFrame(rows, columns=["iso3", "year", value_name])


def fallback_nominal_gdp_pc(country_sample: str, start_year: int, end_year: int) -> pd.DataFrame:
    controls_path = sample_processed_path("country_size_effect_world_bank_controls.csv", country_sample)
    if not controls_path.exists():
        return pd.DataFrame(columns=["iso3", "year", "gdp_pc_current_usd"])
    controls = pd.read_csv(controls_path)
    required = {"iso3", "year", "gdp_current_usd", "population"}
    if not required.issubset(controls.columns):
        return pd.DataFrame(columns=["iso3", "year", "gdp_pc_current_usd"])
    controls = controls[list(required)].copy()
    controls["iso3"] = controls["iso3"].astype(str).str.upper()
    controls["year"] = pd.to_numeric(controls["year"], errors="coerce")
    controls["gdp_current_usd"] = pd.to_numeric(controls["gdp_current_usd"], errors="coerce")
    controls["population"] = pd.to_numeric(controls["population"], errors="coerce")
    controls = controls[controls["year"].between(start_year, end_year) & controls["population"].gt(0)]
    controls["gdp_pc_current_usd"] = controls["gdp_current_usd"] / controls["population"]
    controls = controls.dropna(subset=["iso3", "year", "gdp_pc_current_usd"])
    controls["year"] = controls["year"].astype(int)
    return controls[["iso3", "year", "gdp_pc_current_usd"]].drop_duplicates(["iso3", "year"], keep="last")


def load_or_fetch_income_controls(
    iso3s: list[str],
    country_sample: str,
    start_year: int,
    end_year: int,
    cache_path: Path,
    refresh: bool = False,
) -> pd.DataFrame:
    cached = read_cached_controls(cache_path)
    expected = pd.DataFrame(
        [(iso3, year) for iso3 in sorted(set(iso3s)) for year in range(start_year, end_year + 1)],
        columns=["iso3", "year"],
    )
    controls = expected.merge(cached, on=["iso3", "year"], how="left")
    complete = controls[list(WORLD_BANK_INDICATORS)].notna().all(axis=1).mean() if len(controls) else 0.0

    if refresh or complete < 1.0:
        frames: dict[str, list[pd.DataFrame]] = {value_name: [] for value_name in WORLD_BANK_INDICATORS}
        for value_name in WORLD_BANK_INDICATORS:
            if value_name in cached.columns:
                cached_value = cached[["iso3", "year", value_name]].copy()
                cached_value["_source_priority"] = 0
                frames[value_name].append(cached_value)
        for value_name, spec in WORLD_BANK_INDICATORS.items():
            try:
                fetched = fetch_world_bank_indicator(iso3s, spec["indicator"], value_name, start_year, end_year)
                fetched["_source_priority"] = 2
                frames[value_name].append(fetched)
            except Exception as exc:
                print(f"World Bank fetch warning for {spec['indicator']}: {exc}", file=sys.stderr)
        fallback = fallback_nominal_gdp_pc(country_sample, start_year, end_year)
        if "gdp_pc_current_usd" in fallback.columns:
            fallback["_source_priority"] = 1
            frames["gdp_pc_current_usd"].append(fallback)

        updated = expected.copy()
        for value_name in WORLD_BANK_INDICATORS:
            value_frames = [
                frame[["iso3", "year", value_name, "_source_priority"]]
                for frame in frames[value_name]
                if value_name in frame.columns
            ]
            if not value_frames:
                continue
            combined = pd.concat(value_frames, ignore_index=True)
            combined["iso3"] = combined["iso3"].astype(str).str.upper()
            combined["year"] = pd.to_numeric(combined["year"], errors="coerce")
            combined[value_name] = pd.to_numeric(combined[value_name], errors="coerce")
            combined = (
                combined.dropna(subset=["iso3", "year", value_name])
                .sort_values(["iso3", "year", "_source_priority"])
                .drop_duplicates(["iso3", "year"], keep="last")
            )
            combined["year"] = combined["year"].astype(int)
            updated = updated.merge(combined[["iso3", "year", value_name]], on=["iso3", "year"], how="left")
        controls = updated
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        controls.to_csv(cache_path, index=False)

    for col in WORLD_BANK_INDICATORS:
        controls[col] = pd.to_numeric(controls[col], errors="coerce")
    controls["iso3"] = controls["iso3"].astype(str).str.upper()
    controls["year"] = pd.to_numeric(controls["year"], errors="coerce").astype(int)
    return controls.drop_duplicates(["iso3", "year"], keep="last")


def query_sector_export_shares(country_sample: str, year: int) -> pd.DataFrame:
    source_glob = sample_aggregate_glob(country_sample)
    source_dir = source_glob.parent
    if not source_dir.exists() or not any(source_dir.glob("*.parquet")):
        raise FileNotFoundError(f"No aggregate parquet files found under {source_dir}")

    excluded_codes = ", ".join(f"'{code}'" for code in sorted(EXCLUDED_HS6_CODES))
    section_values = ", ".join(f"({section})" for section in sorted(SECTION_LABELS))
    query = f"""
    with base as (
      select
        reporter_code,
        year,
        try_cast(substr(cmd_code, 1, 2) as integer) as hs2,
        cmd_code,
        trade_value
      from read_parquet('{source_glob.as_posix()}')
      where dimension = 'product'
        and flow = 'Exports'
        and year = {int(year)}
        and regexp_matches(cmd_code, '^[0-9]{{6}}$')
        and cmd_code not in ({excluded_codes})
    ),
    sectioned as (
      select
        reporter_code,
        year,
        {HS_SECTION_CASE} as hs_section,
        trade_value
      from base
    ),
    sector_values as (
      select
        reporter_code,
        year,
        hs_section,
        sum(trade_value) as sector_export_value
      from sectioned
      where hs_section is not null
      group by reporter_code, year, hs_section
    ),
    totals as (
      select
        reporter_code,
        year,
        sum(sector_export_value) as total_export_value
      from sector_values
      group by reporter_code, year
    ),
    sections(hs_section) as (
      values {section_values}
    )
    select
      totals.reporter_code,
      totals.year,
      sections.hs_section,
      coalesce(sector_values.sector_export_value, 0.0) as sector_export_value,
      totals.total_export_value,
      coalesce(sector_values.sector_export_value, 0.0) / nullif(totals.total_export_value, 0) as sector_export_value_share
    from totals
    cross join sections
    left join sector_values
      on totals.reporter_code = sector_values.reporter_code
      and totals.year = sector_values.year
      and sections.hs_section = sector_values.hs_section
    order by totals.reporter_code, sections.hs_section
    """
    out = duckdb.connect().execute(query).fetchdf()
    if out.empty:
        raise RuntimeError(f"No sector export rows returned for {country_sample}, {year}.")
    out["hs_section"] = out["hs_section"].astype(int)
    out["hs2_range"] = out["hs_section"].map(lambda section: SECTION_LABELS[int(section)][0])
    out["hs_section_label"] = out["hs_section"].map(lambda section: SECTION_LABELS[int(section)][1])
    return out


def assemble_panel(country_sample: str, year: int, refresh_controls: bool) -> tuple[pd.DataFrame, pd.DataFrame]:
    countries = read_country_panel(country_sample)
    shares = query_sector_export_shares(country_sample, year)
    panel = shares.merge(countries, on="reporter_code", how="left", validate="many_to_one")
    missing_countries = panel[panel["iso3"].isna()]["reporter_code"].drop_duplicates().tolist()
    if missing_countries:
        raise RuntimeError(f"Missing country metadata for reporter codes: {missing_countries[:10]}")

    controls_path = sample_processed_path("sector_income_world_bank_controls.csv", country_sample)
    controls = load_or_fetch_income_controls(
        panel["iso3"].dropna().unique().tolist(),
        country_sample,
        year,
        year,
        controls_path,
        refresh=refresh_controls,
    )
    panel = panel.merge(controls, on=["iso3", "year"], how="left", validate="many_to_one")
    panel["country_sample"] = country_sample
    panel["flow"] = "Exports"
    panel["hs6_999999_rule"] = "excluded_before_aggregation"
    for col in WORLD_BANK_INDICATORS:
        panel[f"log_{col}"] = np.where(panel[col] > 0, np.log(panel[col]), np.nan)

    order = [
        "country_sample",
        "flow",
        "year",
        "country",
        "iso3",
        "reporter_code",
        "hs_section",
        "hs2_range",
        "hs_section_label",
        "sector_export_value",
        "total_export_value",
        "sector_export_value_share",
        "gdp_pc_current_usd",
        "gdp_pc_ppp_current_intl_usd",
        "log_gdp_pc_current_usd",
        "log_gdp_pc_ppp_current_intl_usd",
        "hs6_999999_rule",
    ]
    return panel[order], controls


def money_tick(value: float, _position: int) -> str:
    if value <= 0 or not math.isfinite(value):
        return ""
    if value >= 1000:
        return f"${value / 1000:.0f}k"
    return f"${value:.0f}"


def section_title(section: int) -> str:
    label = SECTION_LABELS[section][1]
    return f"{section}. {textwrap.shorten(label, width=34, placeholder='...')}"


def add_fit_line(ax: plt.Axes, data: pd.DataFrame, x_col: str, y_col: str, color: str) -> None:
    complete = data[[x_col, y_col]].dropna()
    complete = complete[(complete[x_col] > 0) & np.isfinite(complete[x_col]) & np.isfinite(complete[y_col])]
    if len(complete) < 5 or complete[x_col].nunique() < 3:
        return
    x_log = np.log10(complete[x_col].to_numpy())
    y = complete[y_col].to_numpy() * 100
    slope, intercept = np.polyfit(x_log, y, 1)
    x_grid = np.geomspace(float(complete[x_col].min()), float(complete[x_col].max()), 120)
    y_hat = intercept + slope * np.log10(x_grid)
    ax.plot(x_grid, y_hat, color=color, linewidth=1.1, alpha=0.75, zorder=2)


def section_color(section: int) -> tuple[float, float, float, float]:
    if section == 16:
        return (0.75, 0.16, 0.13, 1.0)
    cmap = plt.get_cmap("turbo")
    return cmap((section - 1) / 20)


def combined_line_data(panel: pd.DataFrame, x_col: str, bins: int = 6) -> pd.DataFrame:
    country_income = (
        panel[["iso3", x_col]]
        .drop_duplicates()
        .dropna(subset=[x_col])
        .loc[lambda data: data[x_col] > 0]
        .copy()
    )
    if country_income.empty:
        raise RuntimeError(f"No complete country income values available for {x_col}.")
    country_income["income_bin"] = pd.qcut(country_income[x_col], q=bins, duplicates="drop")
    country_income["income_bin_order"] = country_income["income_bin"].cat.codes
    bin_stats = (
        country_income.groupby(["income_bin", "income_bin_order"], observed=True)
        .agg(
            bin_x=(x_col, "median"),
            bin_min=(x_col, "min"),
            bin_max=(x_col, "max"),
            countries=("iso3", "nunique"),
        )
        .reset_index()
    )
    work = panel.merge(country_income[["iso3", "income_bin", "income_bin_order"]], on="iso3", how="inner")
    means = (
        work.groupby(["hs_section", "hs2_range", "hs_section_label", "income_bin", "income_bin_order"], observed=True)
        .agg(
            mean_sector_export_value_share=("sector_export_value_share", "mean"),
            median_sector_export_value_share=("sector_export_value_share", "median"),
            countries=("iso3", "nunique"),
        )
        .reset_index()
        .merge(bin_stats, on=["income_bin", "income_bin_order"], how="left", validate="many_to_one")
        .sort_values(["hs_section", "income_bin_order"])
    )
    means["income_variable"] = x_col
    return means[
        [
            "income_variable",
            "hs_section",
            "hs2_range",
            "hs_section_label",
            "income_bin_order",
            "bin_x",
            "bin_min",
            "bin_max",
            "countries_x",
            "mean_sector_export_value_share",
            "median_sector_export_value_share",
        ]
    ].rename(columns={"countries_x": "countries"})


def plot_combined_lines(panel: pd.DataFrame, x_col: str, output_path: Path, title: str) -> pd.DataFrame:
    lines = combined_line_data(panel, x_col)
    fig, ax = plt.subplots(figsize=(12.5, 8.0))
    for section in sorted(SECTION_LABELS):
        data = lines[lines["hs_section"] == section].sort_values("income_bin_order")
        if data.empty:
            continue
        label = f"{section}: {textwrap.shorten(SECTION_LABELS[section][1], width=27, placeholder='...')}"
        ax.plot(
            data["bin_x"],
            data["mean_sector_export_value_share"] * 100,
            color=section_color(section),
            marker="o",
            markersize=4.0,
            linewidth=2.4 if section == 16 else 1.45,
            alpha=0.96 if section == 16 else 0.82,
            label=label,
            zorder=4 if section == 16 else 3,
        )

    country_sample = str(panel["country_sample"].iloc[0])
    year = int(panel["year"].iloc[0])
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(FuncFormatter(money_tick))
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=100, decimals=0))
    ax.set_xlabel(title)
    ax.set_ylabel("Mean export value share within income bin")
    ax.set_title(f"All HS section export shares vs {title}, {country_sample}, {year}", pad=12)
    ax.grid(axis="both", color="#d7dee2", linewidth=0.7, alpha=0.8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(
        loc="center left",
        bbox_to_anchor=(1.01, 0.5),
        frameon=False,
        fontsize=7.5,
        ncol=1,
        title="HS section",
        title_fontsize=8.5,
    )
    fig.text(
        0.01,
        0.01,
        "Source: project Comtrade aggregates and World Bank indicators. Each line connects income-bin mean sector shares; HS6 999999 excluded before sector aggregation.",
        fontsize=9,
        ha="left",
        va="bottom",
    )
    fig.tight_layout(rect=(0, 0.025, 0.78, 1))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return lines


def plot_facets(panel: pd.DataFrame, x_col: str, output_path: Path, title: str) -> None:
    complete_panel = panel.dropna(subset=[x_col, "sector_export_value_share"]).copy()
    complete_panel = complete_panel[complete_panel[x_col] > 0]
    if complete_panel.empty:
        raise RuntimeError(f"No complete rows available to plot {x_col}.")

    fig, axes = plt.subplots(7, 3, figsize=(15, 18.5), sharex=True, sharey=False)
    axes_flat = axes.flatten()
    min_x = float(complete_panel[x_col].min())
    max_x = float(complete_panel[x_col].max())
    x_pad_low = 10 ** (math.log10(min_x) - 0.08)
    x_pad_high = 10 ** (math.log10(max_x) + 0.08)

    for section, ax in zip(sorted(SECTION_LABELS), axes_flat):
        data = complete_panel[complete_panel["hs_section"] == section]
        color = "#b8322a" if section == 16 else "#174a73"
        max_y = float((data["sector_export_value_share"] * 100).max()) if not data.empty else 0.0
        y_decimals = 1 if max_y <= 5 else 0
        ax.scatter(
            data[x_col],
            data["sector_export_value_share"] * 100,
            s=20,
            color=color,
            alpha=0.72,
            linewidths=0,
            zorder=3,
        )
        add_fit_line(ax, data, x_col, "sector_export_value_share", "#202020")
        ax.set_xscale("log")
        ax.set_xlim(x_pad_low, x_pad_high)
        ax.set_title(section_title(section), fontsize=9.5, pad=5)
        ax.yaxis.set_major_formatter(PercentFormatter(xmax=100, decimals=y_decimals))
        ax.grid(axis="both", color="#d7dee2", linewidth=0.6, alpha=0.75)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        if section % 3 == 1:
            ax.set_ylabel("Export value share")
        if section >= 19:
            ax.set_xlabel(title)
        ax.xaxis.set_major_formatter(FuncFormatter(money_tick))

    country_sample = str(panel["country_sample"].iloc[0])
    year = int(panel["year"].iloc[0])
    fig.suptitle(f"HS section export shares vs {title}, {country_sample}, {year}", fontsize=16, y=0.995)
    fig.text(
        0.01,
        0.005,
        "Source: project Comtrade aggregates and World Bank indicators. Exports only. HS6 999999 excluded before sector aggregation. X axis is log-scaled.",
        fontsize=9,
        ha="left",
        va="bottom",
    )
    fig.tight_layout(rect=(0, 0.018, 1, 0.982))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def sector_correlations(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for section, data in panel.groupby("hs_section"):
        row = {
            "hs_section": int(section),
            "hs2_range": SECTION_LABELS[int(section)][0],
            "hs_section_label": SECTION_LABELS[int(section)][1],
            "countries": int(data["iso3"].nunique()),
        }
        for x_col in WORLD_BANK_INDICATORS:
            complete = data[[x_col, f"log_{x_col}", "sector_export_value_share"]].dropna()
            complete = complete[(complete[x_col] > 0) & np.isfinite(complete[f"log_{x_col}"])]
            row[f"complete_countries_{x_col}"] = int(len(complete))
            if len(complete) >= 3 and complete[f"log_{x_col}"].nunique() > 1:
                row[f"corr_share_log_{x_col}"] = float(
                    complete[f"log_{x_col}"].corr(complete["sector_export_value_share"])
                )
            else:
                row[f"corr_share_log_{x_col}"] = np.nan
        rows.append(row)
    return pd.DataFrame(rows).sort_values("hs_section")


def diagnostics(panel: pd.DataFrame, controls: pd.DataFrame) -> pd.DataFrame:
    country_controls = panel[["country", "iso3", "year", *WORLD_BANK_INDICATORS]].drop_duplicates()
    share_sums = panel.groupby(["iso3", "year"], as_index=False)["sector_export_value_share"].sum()
    rows = [
        {"diagnostic": "country_section_rows", "value": len(panel)},
        {"diagnostic": "countries", "value": int(panel["iso3"].nunique())},
        {"diagnostic": "hs_sections_per_country", "value": int(panel.groupby("iso3")["hs_section"].nunique().min())},
        {"diagnostic": "world_bank_control_rows", "value": len(controls)},
        {
            "diagnostic": "countries_complete_gdp_pc_current_usd",
            "value": int(country_controls["gdp_pc_current_usd"].notna().sum()),
        },
        {
            "diagnostic": "countries_complete_gdp_pc_ppp_current_intl_usd",
            "value": int(country_controls["gdp_pc_ppp_current_intl_usd"].notna().sum()),
        },
        {
            "diagnostic": "max_abs_country_sector_share_sum_minus_one",
            "value": float((share_sums["sector_export_value_share"] - 1.0).abs().max()),
        },
        {
            "diagnostic": "output_hs6_999999_rows",
            "value": int(panel["hs6_999999_rule"].eq("included").sum()),
        },
    ]
    return pd.DataFrame(rows)


def write_note(
    output_path: Path,
    country_sample: str,
    year: int,
    panel_path: Path,
    corr_path: Path,
    diag_path: Path,
    missing_path: Path,
    combined_line_data_path: Path,
    figures: dict[str, Path],
    diag: pd.DataFrame,
) -> None:
    diag_md = diag.to_markdown(index=False)
    content = f"""# HS Section Export Shares by Income

This diagnostic plots each country's HS section export value share against income per capita.

## Construction

Sample: `{country_sample}`. Flow: exports. Year: `{year}`.

Formula:

`sector_share_c,s = export_value_c,s / sum_s export_value_c,s`

In plain English, this is the share of a country's identified HS6 export value that falls in HS section `s`. HS6 `999999` is excluded before the section sums and country totals are calculated.

Income variables:

- `gdp_pc_current_usd`: World Bank `NY.GDP.PCAP.CD`, GDP per capita in current US dollars. If the direct indicator is unavailable during refresh, the script fills gaps with World Bank current-dollar GDP divided by population from the repo cache.
- `gdp_pc_ppp_current_intl_usd`: World Bank `NY.GDP.PCAP.PP.CD`, GDP per capita at PPP in current international dollars.

The plots use a log-scaled x axis. The thin black line in each faceted panel is a simple visual fit of section share on log10 income; it is not a causal estimate. The combined-line figures connect income-bin mean sector shares, not raw country-to-country paths.

## Diagnostics

{diag_md}

## Outputs

- GDP per capita figure: `{figures['gdp_pc_current_usd'].relative_to(ROOT)}`
- PPP GDP per capita figure: `{figures['gdp_pc_ppp_current_intl_usd'].relative_to(ROOT)}`
- GDP per capita combined-line figure: `{figures['gdp_pc_current_usd_combined_lines'].relative_to(ROOT)}`
- PPP GDP per capita combined-line figure: `{figures['gdp_pc_ppp_current_intl_usd_combined_lines'].relative_to(ROOT)}`
- Country-section raw table: `{panel_path.relative_to(ROOT)}`
- Combined-line binned data: `{combined_line_data_path.relative_to(ROOT)}`
- Sector-income correlations: `{corr_path.relative_to(ROOT)}`
- Diagnostics: `{diag_path.relative_to(ROOT)}`
- Missing income controls: `{missing_path.relative_to(ROOT)}`
"""
    output_path.write_text(content, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country-sample", choices=COUNTRY_SAMPLE_CHOICES, default="rd2_countries")
    parser.add_argument("--year", type=int, default=2021)
    parser.add_argument("--refresh-controls", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = args.output_dir or sample_result_dir(args.country_sample)
    out_dir.mkdir(parents=True, exist_ok=True)

    panel, controls = assemble_panel(args.country_sample, args.year, args.refresh_controls)
    stem = f"hs_section_export_shares_by_income_{args.country_sample}_{args.year}"

    panel_path = out_dir / f"{stem}.csv"
    corr_path = out_dir / f"{stem}_correlations.csv"
    diag_path = out_dir / f"{stem}_diagnostics.csv"
    missing_path = out_dir / f"{stem}_missing_income_controls.csv"
    combined_line_data_path = out_dir / f"{stem}_combined_line_data.csv"
    note_path = out_dir / f"{stem}.md"

    panel.to_csv(panel_path, index=False)
    corr = sector_correlations(panel)
    corr.to_csv(corr_path, index=False)
    diag = diagnostics(panel, controls)
    diag.to_csv(diag_path, index=False)
    missing = (
        panel[["country", "iso3", "year", *WORLD_BANK_INDICATORS]]
        .drop_duplicates()
        .loc[lambda data: data[list(WORLD_BANK_INDICATORS)].isna().any(axis=1)]
    )
    missing.to_csv(missing_path, index=False)

    figures: dict[str, Path] = {}
    combined_line_frames: list[pd.DataFrame] = []
    for x_col, spec in WORLD_BANK_INDICATORS.items():
        fig_path = out_dir / f"{stem}_{x_col}.png"
        plot_facets(panel, x_col, fig_path, spec["label"])
        figures[x_col] = fig_path
        combined_fig_path = out_dir / f"{stem}_{x_col}_combined_lines.png"
        combined_line_frames.append(plot_combined_lines(panel, x_col, combined_fig_path, spec["label"]))
        figures[f"{x_col}_combined_lines"] = combined_fig_path
    pd.concat(combined_line_frames, ignore_index=True).to_csv(combined_line_data_path, index=False)

    write_note(
        note_path,
        args.country_sample,
        args.year,
        panel_path,
        corr_path,
        diag_path,
        missing_path,
        combined_line_data_path,
        figures,
        diag,
    )

    print(f"Wrote {figures['gdp_pc_current_usd']}")
    print(f"Wrote {figures['gdp_pc_ppp_current_intl_usd']}")
    print(f"Wrote {figures['gdp_pc_current_usd_combined_lines']}")
    print(f"Wrote {figures['gdp_pc_ppp_current_intl_usd_combined_lines']}")
    print(f"Wrote {panel_path}")
    print(f"Wrote {combined_line_data_path}")
    print(f"Wrote {corr_path}")
    print(f"Wrote {diag_path}")
    print(f"Wrote {missing_path}")
    print(f"Wrote {note_path}")
    print(diag.to_string(index=False))


if __name__ == "__main__":
    main()
