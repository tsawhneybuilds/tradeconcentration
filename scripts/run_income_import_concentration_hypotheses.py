#!/usr/bin/env python3
"""Run question-led income/import-concentration hypothesis checks.

The exercise is descriptive. It asks whether the negative relationship between
income and import concentration survives a set of mechanism and data-quality
checks in the rd2_countries balanced 2000-2024 panel.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import statsmodels.formula.api as smf

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from concentration_metrics import active_gini, active_top_share  # noqa: E402

START_YEAR = 2000
END_YEAR = 2024
BASE = ROOT / "results" / "samples" / "rd2_countries"
OUT_DIR = BASE / "income_import_concentration_hypotheses"
FIG_DIR = OUT_DIR / "figures"

CLASSIFICATION = (
    BASE
    / "import_energy_gini_diagnostics"
    / "ex_energy_rank_bucket_gini_driver_classification_balanced_2000_2024.csv"
)
CONCENTRATION = ROOT / "data" / "processed" / "samples" / "rd2_countries" / "concentration_all_years.parquet"
IMPORT_BIN_DECOMP = ROOT / "data" / "processed" / "samples" / "rd2_countries" / "exercise_03_import_bin_decomposition.parquet"
EX06_EXCLUSIONS = BASE / "exercise_06_tables" / "concentration_exclusions_all_years.csv"
EX06_REMOVED = BASE / "exercise_06_tables" / "trade_share_removed_by_category.csv"
EX04_PARTNER_COUNTERFACTUAL = BASE / "exercise_04_tables" / "partner_gini_counterfactual_country_year.csv"
WDI_CONTROLS = BASE / "import_concentration_explanatory_regressions" / "wdi_controls_2000_2024.csv"
FUTURE_GROWTH_CONTROLS = (
    ROOT / "data" / "processed" / "samples" / "rd2_countries" / "future_growth_concentration_world_bank_controls.csv"
)
COUNTRY_METADATA = ROOT / "data" / "raw" / "world_bank_gdp" / "country_metadata.csv"
IMPORT_CELL_DIR = ROOT / "data" / "processed" / "samples" / "rd2_countries" / "checkpoints" / "exercise_11_file_aggregates" / "import_cells"
CEPII_DIR = ROOT / "data" / "raw" / "cepii"
CEPII_DIST = CEPII_DIR / "dist_cepii.dta"
CEPII_GEO = CEPII_DIR / "geo_cepii.dta"

WDI_URL = "https://api.worldbank.org/v2/country/{countries}/indicator/{indicator}"
BATTLE_DEATHS_INDICATOR = "VC.BTL.DETH"
BATCH_SIZE = 20

FOOD_STAPLE_HS2 = {f"{i:02d}" for i in range(1, 25)}
ISLAND_OR_ISLAND_ECONOMY_ISO3 = {"AUS", "GBR", "HKG", "IRL", "ISL", "JPN", "NZL", "SGP"}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def safe_log(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    return np.where(numeric > 0, np.log(numeric), np.nan)


def validate_unique(df: pd.DataFrame, keys: list[str], label: str) -> None:
    missing = [col for col in keys if col not in df.columns]
    if missing:
        raise RuntimeError(f"{label} missing key columns: {missing}")
    dupes = int(df.duplicated(keys).sum())
    if dupes:
        examples = df.loc[df.duplicated(keys, keep=False), keys].head(8).to_dict("records")
        raise RuntimeError(f"{label} has duplicate keys on {keys}: {examples}")


def normalize_iso3(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.upper()


def fetch_url(url: str, destination: Path) -> Path:
    if destination.exists() and destination.stat().st_size > 1000:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(url, timeout=90)
    response.raise_for_status()
    if len(response.content) <= 1000:
        raise RuntimeError(f"Downloaded CEPII file looks too small: {url}")
    tmp = destination.with_suffix(destination.suffix + ".part")
    tmp.write_bytes(response.content)
    tmp.replace(destination)
    return destination


def ensure_cepii_files() -> None:
    fetch_url("https://www.cepii.fr/distance/dist_cepii.dta", CEPII_DIST)
    fetch_url("https://www.cepii.fr/distance/geo_cepii.dta", CEPII_GEO)


def load_balanced_countries() -> pd.DataFrame:
    if not CLASSIFICATION.exists():
        raise FileNotFoundError(f"Missing balanced rd2 classification file: {CLASSIFICATION}")
    countries = pd.read_csv(CLASSIFICATION, usecols=["country", "iso3", "reporter_code"])
    countries["iso3"] = normalize_iso3(countries["iso3"])
    countries["reporter_code"] = pd.to_numeric(countries["reporter_code"], errors="coerce").astype(int)
    validate_unique(countries, ["iso3"], "balanced rd2 countries")
    return countries


def load_region_controls(iso3s: list[str]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    if FUTURE_GROWTH_CONTROLS.exists():
        fg = pd.read_csv(FUTURE_GROWTH_CONTROLS, usecols=["iso3", "year", "region", "income_group"])
        fg["iso3"] = normalize_iso3(fg["iso3"])
        fg = fg[fg["year"].between(START_YEAR, END_YEAR)].copy()
        frames.append(
            fg.groupby("iso3", as_index=False)
            .agg(region=("region", lambda x: x.dropna().astype(str).mode().iloc[0] if not x.dropna().empty else "Unclassified"),
                 income_group=("income_group", lambda x: x.dropna().astype(str).mode().iloc[0] if not x.dropna().empty else ""))
        )
    if COUNTRY_METADATA.exists():
        meta = pd.read_csv(COUNTRY_METADATA, usecols=["iso3", "region", "income_group"])
        meta["iso3"] = normalize_iso3(meta["iso3"])
        frames.append(meta)
    if not frames:
        return pd.DataFrame({"iso3": iso3s, "region": "Unclassified", "income_group": ""})
    out = pd.concat(frames, ignore_index=True)
    out["region"] = out["region"].replace("", np.nan).fillna("Unclassified").astype(str)
    out["income_group"] = out["income_group"].replace("", np.nan).fillna("").astype(str)
    out = out.drop_duplicates("iso3", keep="first")
    return pd.DataFrame({"iso3": iso3s}).merge(out, on="iso3", how="left").fillna(
        {"region": "Unclassified", "income_group": ""}
    )


def load_geography_controls(iso3s: list[str], wdi: pd.DataFrame) -> pd.DataFrame:
    ensure_cepii_files()
    geo = pd.read_stata(CEPII_GEO, preserve_dtypes=False)
    geo["iso3"] = normalize_iso3(geo["iso3"])
    geo = (
        geo[geo["iso3"].isin(iso3s)]
        .groupby("iso3", as_index=False)
        .agg(landlocked=("landlocked", "max"))
    )
    geo["landlocked"] = pd.to_numeric(geo["landlocked"], errors="coerce").fillna(0).astype(int)
    geo["island_economy"] = geo["iso3"].isin(ISLAND_OR_ISLAND_ECONOMY_ISO3).astype(int)

    dist = pd.read_stata(CEPII_DIST, preserve_dtypes=False)
    dist["iso_o"] = normalize_iso3(dist["iso_o"])
    dist["iso_d"] = normalize_iso3(dist["iso_d"])
    dist_col = "distw" if "distw" in dist.columns else "dist"
    dist[dist_col] = pd.to_numeric(dist[dist_col], errors="coerce")
    dist = dist.groupby(["iso_o", "iso_d"], as_index=False)[dist_col].mean()
    gdp2000 = (
        wdi[wdi["year"].eq(START_YEAR)][["iso3", "gdp_current_usd"]]
        .assign(iso3=lambda x: normalize_iso3(x["iso3"]))
        .rename(columns={"iso3": "iso_d", "gdp_current_usd": "destination_gdp_current_usd_2000"})
    )
    work = dist[dist["iso_o"].isin(iso3s) & dist["iso_d"].isin(iso3s) & dist["iso_o"].ne(dist["iso_d"])].copy()
    work = work.merge(gdp2000, on="iso_d", how="left")
    work["destination_gdp_current_usd_2000"] = pd.to_numeric(work["destination_gdp_current_usd_2000"], errors="coerce")
    work = work[(work[dist_col] > 0) & (work["destination_gdp_current_usd_2000"] > 0)].copy()
    work["weighted_log_distance"] = work["destination_gdp_current_usd_2000"] * np.log(work[dist_col])
    remote = (
        work.groupby("iso_o", as_index=False)
        .agg(
            rd2_gdp_weighted_log_distance_2000=("weighted_log_distance", "sum"),
            rd2_destination_gdp_weight_sum_2000=("destination_gdp_current_usd_2000", "sum"),
        )
        .rename(columns={"iso_o": "iso3"})
    )
    remote["rd2_gdp_weighted_log_distance_2000"] = (
        remote["rd2_gdp_weighted_log_distance_2000"] / remote["rd2_destination_gdp_weight_sum_2000"]
    )
    out = pd.DataFrame({"iso3": iso3s}).merge(geo, on="iso3", how="left").merge(
        remote[["iso3", "rd2_gdp_weighted_log_distance_2000"]], on="iso3", how="left"
    )
    if out[["landlocked", "island_economy", "rd2_gdp_weighted_log_distance_2000"]].isna().any().any():
        missing = out[out[["landlocked", "island_economy", "rd2_gdp_weighted_log_distance_2000"]].isna().any(axis=1)][
            "iso3"
        ].tolist()
        raise RuntimeError(f"Missing geography controls for: {missing}")
    return out


def fetch_wdi_indicator(iso3s: list[str], indicator: str, value_col: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for start in range(0, len(iso3s), BATCH_SIZE):
        countries = ";".join(sorted(set(iso3s[start : start + BATCH_SIZE])))
        page = 1
        pages = 1
        while page <= pages:
            response = requests.get(
                WDI_URL.format(countries=countries, indicator=indicator),
                params={"format": "json", "per_page": 20000, "page": page, "date": f"{START_YEAR}:{END_YEAR}"},
                timeout=60,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list) or len(payload) < 2:
                break
            meta = payload[0] if isinstance(payload[0], dict) else {}
            pages = int(meta.get("pages") or pages)
            for item in payload[1]:
                iso3 = str(item.get("countryiso3code") or "").strip().upper()
                value = item.get("value")
                if iso3:
                    rows.append({"iso3": iso3, "year": int(item["date"]), value_col: value})
            page += 1
            time.sleep(0.05)
    out = pd.DataFrame(rows, columns=["iso3", "year", value_col])
    out[value_col] = pd.to_numeric(out[value_col], errors="coerce")
    out["iso3"] = normalize_iso3(out["iso3"])
    out["year"] = pd.to_numeric(out["year"], errors="coerce").astype("Int64")
    out = out.dropna(subset=["iso3", "year"]).copy()
    out["year"] = out["year"].astype(int)
    return out.drop_duplicates(["iso3", "year"], keep="last")


def load_conflict_controls(iso3s: list[str], refresh: bool = False) -> pd.DataFrame:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cache = OUT_DIR / "world_bank_battle_deaths_2000_2024.csv"
    if cache.exists() and not refresh:
        out = pd.read_csv(cache)
        out["iso3"] = normalize_iso3(out["iso3"])
        out["year"] = pd.to_numeric(out["year"], errors="coerce").astype(int)
    else:
        out = fetch_wdi_indicator(iso3s, BATTLE_DEATHS_INDICATOR, "battle_related_deaths")
        out.to_csv(cache, index=False)
    complete = pd.DataFrame([(iso3, year) for iso3 in iso3s for year in range(START_YEAR, END_YEAR + 1)], columns=["iso3", "year"])
    complete = complete.merge(out, on=["iso3", "year"], how="left", validate="one_to_one")
    complete["battle_related_deaths"] = pd.to_numeric(complete["battle_related_deaths"], errors="coerce")
    complete["conflict_year"] = complete["battle_related_deaths"].fillna(0).gt(0).astype(int)
    return complete


def load_wdi_controls(iso3s: list[str]) -> pd.DataFrame:
    if not WDI_CONTROLS.exists():
        raise FileNotFoundError(f"Missing WDI controls: {WDI_CONTROLS}")
    wdi = pd.read_csv(WDI_CONTROLS)
    wdi["iso3"] = normalize_iso3(wdi["iso3"])
    wdi["year"] = pd.to_numeric(wdi["year"], errors="coerce").astype(int)
    wdi = wdi[wdi["iso3"].isin(iso3s) & wdi["year"].between(START_YEAR, END_YEAR)].copy()
    validate_unique(wdi, ["iso3", "year"], "WDI controls")
    return wdi


def load_import_concentration(iso3s: list[str]) -> pd.DataFrame:
    if not CONCENTRATION.exists():
        raise FileNotFoundError(f"Missing concentration panel: {CONCENTRATION}")
    df = pd.read_parquet(CONCENTRATION)
    df["iso3"] = normalize_iso3(df["iso3"])
    df = df[
        df["iso3"].isin(iso3s)
        & df["year"].between(START_YEAR, END_YEAR)
        & df["flow"].eq("Imports")
        & df["variant"].eq("baseline")
    ].copy()
    df = df.rename(
        columns={
            "total_trade_value": "product_total_imports",
            "partner_total_trade_value": "partner_total_imports",
            "product_gini": "import_product_gini",
            "partner_gini": "import_partner_gini",
            "product_active_count": "active_hs6_products",
            "partner_active_count": "active_partners",
        }
    )
    keep = [
        "country",
        "iso3",
        "reporter_code",
        "year",
        "product_total_imports",
        "partner_total_imports",
        "import_product_gini",
        "import_partner_gini",
        "active_hs6_products",
        "active_partners",
        "top_5_partner_share",
    ]
    out = df[keep].copy()
    validate_unique(out, ["iso3", "year"], "baseline import concentration")
    return out


def load_product_top_shares(iso3s: list[str]) -> pd.DataFrame:
    if not IMPORT_BIN_DECOMP.exists():
        raise FileNotFoundError(f"Missing import-bin decomposition: {IMPORT_BIN_DECOMP}")
    decomp = pd.read_parquet(IMPORT_BIN_DECOMP)
    decomp["iso3"] = normalize_iso3(decomp["iso3"])
    energy = decomp[
        decomp["iso3"].isin(iso3s)
        & decomp["year"].between(START_YEAR, END_YEAR)
        & decomp["import_bin"].eq("energy")
    ].copy()
    cols = [
        "iso3",
        "year",
        "total_top_1_product_share",
        "total_top_5_product_share",
        "product_gini_without_bin",
        "active_products_without_bin",
        "top_1_product_share_without_bin",
        "top_5_product_share_without_bin",
        "total_imports_without_bin",
        "import_value_share",
    ]
    out = energy[cols].rename(
        columns={
            "total_top_1_product_share": "top_1_product_share",
            "total_top_5_product_share": "top_5_product_share",
            "product_gini_without_bin": "ex_energy_product_gini",
            "active_products_without_bin": "ex_energy_active_hs6_products",
            "top_1_product_share_without_bin": "ex_energy_top_1_product_share",
            "top_5_product_share_without_bin": "ex_energy_top_5_product_share",
            "total_imports_without_bin": "ex_energy_total_imports",
            "import_value_share": "energy_bin_import_share",
        }
    )
    validate_unique(out, ["iso3", "year"], "product top-share/ex-energy panel")
    return out


def load_fuel_exclusion(iso3s: list[str]) -> pd.DataFrame:
    if not EX06_EXCLUSIONS.exists():
        raise FileNotFoundError(f"Missing Exercise 6 exclusions: {EX06_EXCLUSIONS}")
    ex06 = pd.read_csv(EX06_EXCLUSIONS)
    ex06["iso3"] = normalize_iso3(ex06["iso3"])
    nofuel = ex06[
        ex06["iso3"].isin(iso3s)
        & ex06["year"].between(START_YEAR, END_YEAR)
        & ex06["flow"].eq("Imports")
        & ex06["variant"].eq("oil_only")
    ].copy()
    out = nofuel[
        [
            "iso3",
            "year",
            "total_trade_value",
            "product_gini",
            "partner_gini",
            "product_active_count",
            "partner_active_count",
            "top_5_partner_share",
            "trade_share_removed",
        ]
    ].rename(
        columns={
            "total_trade_value": "no_fuel_total_imports",
            "product_gini": "no_fuel_product_gini",
            "partner_gini": "no_fuel_partner_gini",
            "product_active_count": "no_fuel_active_hs6_products",
            "partner_active_count": "no_fuel_active_partners",
            "top_5_partner_share": "no_fuel_top_5_partner_share",
            "trade_share_removed": "fuel_import_share",
        }
    )
    validate_unique(out, ["iso3", "year"], "no-fuel Exercise 6 panel")
    if EX06_REMOVED.exists():
        removed = pd.read_csv(EX06_REMOVED)
        removed["iso3"] = normalize_iso3(removed["iso3"])
        fuel = removed[
            removed["iso3"].isin(iso3s)
            & removed["year"].between(START_YEAR, END_YEAR)
            & removed["flow"].eq("Imports")
            & removed["exclusion_category"].eq("oil_petroleum_hs27")
        ][["iso3", "year", "trade_share"]].rename(columns={"trade_share": "fuel_import_share_from_removed_table"})
        validate_unique(fuel, ["iso3", "year"], "fuel removed-share panel")
        out = out.merge(fuel, on=["iso3", "year"], how="left", validate="one_to_one")
        out["fuel_share_gap"] = (out["fuel_import_share"] - out["fuel_import_share_from_removed_table"]).abs()
    return out


def load_unspecified_share(iso3s: list[str]) -> pd.DataFrame:
    if not EX04_PARTNER_COUNTERFACTUAL.exists():
        raise FileNotFoundError(f"Missing Exercise 4 partner counterfactual panel: {EX04_PARTNER_COUNTERFACTUAL}")
    df = pd.read_csv(EX04_PARTNER_COUNTERFACTUAL)
    df["iso3"] = normalize_iso3(df["iso3"])
    df = df[df["iso3"].isin(iso3s) & df["year"].between(START_YEAR, END_YEAR)].copy()
    out = df[
        [
            "iso3",
            "year",
            "total_imports_cells",
            "total_imports_cells_excluding_999999",
            "unspecified_imports_cells",
            "unspecified_import_share",
        ]
    ].copy()
    validate_unique(out, ["iso3", "year"], "HS6 999999 share panel")
    return out


def parse_reporter_year_from_file(path: Path) -> tuple[int | None, int | None]:
    match = re.search(r"CA(\d{3})(\d{4})", path.name)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def filtered_cell_metrics(prefix: str, cells: pd.DataFrame, baseline_total: float) -> dict[str, Any]:
    if cells.empty or baseline_total <= 0:
        product_values = pd.Series(dtype=float)
        partner_values = pd.Series(dtype=float)
        total = np.nan
    else:
        product_values = cells.groupby("cmd_code")["trade_value"].sum()
        partner_values = cells.groupby("partner_code")["trade_value"].sum()
        total = float(cells["trade_value"].sum())
    return {
        f"{prefix}_total_imports": total,
        f"{prefix}_import_share_removed": 1 - (total / baseline_total) if np.isfinite(total) and baseline_total > 0 else np.nan,
        f"{prefix}_product_gini": active_gini(product_values),
        f"{prefix}_partner_gini": active_gini(partner_values),
        f"{prefix}_active_hs6_products": int((product_values > 0).sum()) if len(product_values) else 0,
        f"{prefix}_active_partners": int((partner_values > 0).sum()) if len(partner_values) else 0,
        f"{prefix}_top_1_product_share": active_top_share(product_values, n=1),
        f"{prefix}_top_5_product_share": active_top_share(product_values, n=5),
        f"{prefix}_top_1_partner_share": active_top_share(partner_values, n=1),
        f"{prefix}_top_5_partner_share": active_top_share(partner_values, n=5),
    }


def compute_filtered_import_cell_panel(countries: pd.DataFrame, refresh: bool = False) -> pd.DataFrame:
    cache = OUT_DIR / "filtered_import_cell_concentration.csv"
    if cache.exists() and not refresh:
        out = pd.read_csv(cache)
        out["iso3"] = normalize_iso3(out["iso3"])
        out["year"] = pd.to_numeric(out["year"], errors="coerce").astype(int)
        validate_unique(out, ["iso3", "year"], "cached filtered import-cell panel")
        return out
    if not IMPORT_CELL_DIR.exists():
        raise FileNotFoundError(f"Missing import-cell checkpoint directory: {IMPORT_CELL_DIR}")
    reporter_to_iso = countries.set_index("reporter_code")["iso3"].to_dict()
    reporter_to_country = countries.set_index("reporter_code")["country"].to_dict()
    valid_reporters = set(reporter_to_iso)
    rows: list[dict[str, Any]] = []
    files = sorted(IMPORT_CELL_DIR.glob("*.parquet"))
    for idx, path in enumerate(files, start=1):
        reporter_code, year = parse_reporter_year_from_file(path)
        if reporter_code not in valid_reporters or year is None or not (START_YEAR <= year <= END_YEAR):
            continue
        cells = pd.read_parquet(path, columns=["cmd_code", "partner_code", "trade_value"])
        if cells.empty:
            continue
        cells["cmd_code"] = cells["cmd_code"].astype(str).str.extract(r"(\d{1,6})", expand=False).str.zfill(6)
        cells = cells[cells["cmd_code"].ne("999999")].copy()
        cells["hs2"] = cells["cmd_code"].str[:2]
        cells["trade_value"] = pd.to_numeric(cells["trade_value"], errors="coerce")
        cells["partner_code"] = pd.to_numeric(cells["partner_code"], errors="coerce")
        cells = cells.dropna(subset=["cmd_code", "partner_code", "trade_value"])
        cells = cells[(cells["trade_value"] > 0) & (cells["partner_code"] != 0)].copy()
        if cells.empty:
            continue
        baseline_total = float(cells["trade_value"].sum())
        no_food = cells[~cells["hs2"].isin(FOOD_STAPLE_HS2)].copy()
        no_fuel = cells[~cells["hs2"].eq("27")].copy()
        row = {
            "country": reporter_to_country[reporter_code],
            "iso3": reporter_to_iso[reporter_code],
            "reporter_code": int(reporter_code),
            "year": int(year),
            "food_staple_proxy": "HS chapters 01-24",
            "fuel_proxy": "HS chapter 27",
        }
        row.update(filtered_cell_metrics("no_food", no_food, baseline_total))
        row.update(filtered_cell_metrics("no_fuel", no_fuel, baseline_total))
        row["food_staple_import_share_removed"] = row.pop("no_food_import_share_removed")
        row["fuel_import_share"] = row.pop("no_fuel_import_share_removed")
        rows.append(row)
        if idx % 250 == 0:
            print(f"processed {idx}/{len(files)} import-cell files", flush=True)
    out = pd.DataFrame(rows)
    validate_unique(out, ["iso3", "year"], "filtered import-cell concentration panel")
    expected_rows = countries["iso3"].nunique() * (END_YEAR - START_YEAR + 1)
    if len(out) != expected_rows:
        raise RuntimeError(f"Filtered import-cell panel has {len(out)} rows; expected {expected_rows}.")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out.to_csv(cache, index=False)
    return out


def merge_country_year_source(
    panel: pd.DataFrame,
    frame: pd.DataFrame,
    label: str,
    audit_rows: list[dict[str, Any]],
) -> pd.DataFrame:
    supplemental = frame.drop(columns=[col for col in ["country", "reporter_code"] if col in frame.columns])
    validate_unique(supplemental, ["iso3", "year"], f"{label} merge source")
    before_keys = panel[["iso3", "year"]].drop_duplicates()
    source_keys = supplemental[["iso3", "year"]].drop_duplicates()
    matched_keys = before_keys.merge(source_keys, on=["iso3", "year"], how="inner")
    audit_rows.append(
        {
            "merge_step": label,
            "merge_keys": "iso3,year",
            "rows_before": int(len(panel)),
            "unique_keys_before": int(len(before_keys)),
            "source_rows": int(len(supplemental)),
            "source_unique_keys": int(len(source_keys)),
            "matched_base_keys": int(len(matched_keys)),
            "unmatched_base_keys": int(len(before_keys) - len(matched_keys)),
            "rows_after": int(len(panel)),
            "merge_type": "left one_to_one",
        }
    )
    return panel.merge(supplemental, on=["iso3", "year"], how="left", validate="one_to_one")


def merge_country_source(
    panel: pd.DataFrame,
    frame: pd.DataFrame,
    label: str,
    audit_rows: list[dict[str, Any]],
) -> pd.DataFrame:
    supplemental = frame.drop(columns=[col for col in ["country", "reporter_code"] if col in frame.columns])
    validate_unique(supplemental, ["iso3"], f"{label} merge source")
    before_keys = panel[["iso3"]].drop_duplicates()
    source_keys = supplemental[["iso3"]].drop_duplicates()
    matched_keys = before_keys.merge(source_keys, on="iso3", how="inner")
    audit_rows.append(
        {
            "merge_step": label,
            "merge_keys": "iso3",
            "rows_before": int(len(panel)),
            "unique_keys_before": int(len(before_keys)),
            "source_rows": int(len(supplemental)),
            "source_unique_keys": int(len(source_keys)),
            "matched_base_keys": int(len(matched_keys)),
            "unmatched_base_keys": int(len(before_keys) - len(matched_keys)),
            "rows_after": int(len(panel)),
            "merge_type": "left many_to_one",
        }
    )
    return panel.merge(supplemental, on="iso3", how="left", validate="many_to_one")


def build_analysis_panel(refresh_food: bool = False, refresh_conflict: bool = False) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    countries = load_balanced_countries()
    iso3s = sorted(countries["iso3"].unique().tolist())
    wdi = load_wdi_controls(iso3s)
    geo = load_geography_controls(iso3s, wdi)
    region = load_region_controls(iso3s)
    conflict = load_conflict_controls(iso3s, refresh=refresh_conflict)
    panel = load_import_concentration(iso3s)
    audit_rows: list[dict[str, Any]] = [
        {
            "merge_step": "baseline_import_concentration",
            "merge_keys": "iso3,year",
            "rows_before": 0,
            "unique_keys_before": 0,
            "source_rows": int(len(panel)),
            "source_unique_keys": int(panel[["iso3", "year"]].drop_duplicates().shape[0]),
            "matched_base_keys": int(panel[["iso3", "year"]].drop_duplicates().shape[0]),
            "unmatched_base_keys": 0,
            "rows_after": int(len(panel)),
            "merge_type": "base",
        }
    ]
    for label, frame in [
        ("product_top_shares_and_ex_energy", load_product_top_shares(iso3s)),
        ("hs6_999999_unspecified_share", load_unspecified_share(iso3s)),
        ("filtered_import_cell_sensitivities", compute_filtered_import_cell_panel(countries, refresh=refresh_food)),
        ("wdi_controls", wdi),
        ("world_bank_battle_deaths", conflict),
    ]:
        panel = merge_country_year_source(panel, frame, label, audit_rows)
    panel = merge_country_source(panel, region, "world_bank_region_metadata", audit_rows)
    panel = merge_country_source(panel, geo, "cepii_geography_controls", audit_rows)

    panel["log_gdp_pc_ppp"] = safe_log(panel["gdp_pc_ppp_constant_2021_intl_usd"])
    panel["log_population"] = safe_log(panel["population"])
    panel["log_total_imports_product"] = safe_log(panel["product_total_imports"])
    panel["log_total_imports_partner"] = safe_log(panel["partner_total_imports"])
    panel["log_active_hs6_products"] = safe_log(panel["active_hs6_products"])
    panel["log_active_partners"] = safe_log(panel["active_partners"])
    panel["log_no_fuel_active_hs6_products"] = safe_log(panel["no_fuel_active_hs6_products"])
    panel["log_no_food_active_hs6_products"] = safe_log(panel["no_food_active_hs6_products"])
    panel["fuel_import_share"] = pd.to_numeric(panel["fuel_import_share"], errors="coerce").fillna(0)
    panel["region"] = panel["region"].fillna("Unclassified").astype(str)
    panel["income_group"] = panel["income_group"].fillna("").astype(str)
    validate_unique(panel, ["iso3", "year"], "analysis panel")

    diagnostics = make_sample_diagnostics(panel, geo)
    return panel, diagnostics, pd.DataFrame(audit_rows)


def formula_columns(formula: str, df: pd.DataFrame) -> list[str]:
    tokens = set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", formula))
    tokens -= {"C"}
    return sorted(token for token in tokens if token in df.columns)


def model_fit(df: pd.DataFrame, formula: str, cluster_col: str | None) -> tuple[Any, pd.DataFrame, list[str]]:
    needed = formula_columns(formula, df)
    work = df.replace([np.inf, -np.inf], np.nan).dropna(subset=needed).copy()
    if work.empty:
        raise RuntimeError("No complete rows for model.")
    fitted = smf.ols(formula, data=work).fit()
    if cluster_col is not None:
        robust = fitted.get_robustcov_results(cov_type="cluster", groups=work[cluster_col])
    else:
        robust = fitted.get_robustcov_results(cov_type="HC3")
    return robust, work, needed


def run_one_model(
    df: pd.DataFrame,
    *,
    question: str,
    spec: str,
    outcome: str,
    outcome_label: str,
    formula: str,
    total_import_control: str,
    cluster_col: str | None = "iso3",
) -> dict[str, Any]:
    try:
        robust, work, needed = model_fit(df, formula, cluster_col=cluster_col)
        names = robust.model.exog_names
        if "log_gdp_pc_ppp" not in names:
            raise RuntimeError("log_gdp_pc_ppp term missing from fitted model")
        idx = names.index("log_gdp_pc_ppp")
        coef = float(np.asarray(robust.params)[idx])
        se = float(np.asarray(robust.bse)[idx])
        pval = float(np.asarray(robust.pvalues)[idx])
        tval = float(np.asarray(robust.tvalues)[idx])
        status = "ok"
        nobs = int(robust.nobs)
        rsq = float(getattr(robust, "rsquared", np.nan))
    except Exception as exc:
        work = pd.DataFrame()
        needed = formula_columns(formula, df)
        coef = se = pval = tval = rsq = np.nan
        status = f"failed: {exc}"
        nobs = 0
    return {
        "question": question,
        "spec": spec,
        "outcome": outcome,
        "outcome_label": outcome_label,
        "formula": formula,
        "total_import_control": total_import_control,
        "status": status,
        "nobs": nobs,
        "countries": int(work["iso3"].nunique()) if not work.empty and "iso3" in work.columns else 0,
        "years": int(work["year"].nunique()) if not work.empty and "year" in work.columns else 0,
        "coef_log_income": coef,
        "se_log_income": se,
        "t_log_income": tval,
        "p_log_income": pval,
        "effect_per_income_doubling": coef * math.log(2) if np.isfinite(coef) else np.nan,
        "se_per_income_doubling": se * math.log(2) if np.isfinite(se) else np.nan,
        "p_lt_0_05": bool(pval < 0.05) if np.isfinite(pval) else False,
        "rsquared": rsq,
        "cluster": cluster_col or "HC3",
        "needed_columns": "; ".join(needed),
        "input_rows": int(len(df)),
        "complete_rows": int(len(work)),
        "dropped_rows": int(len(df) - len(work)),
    }


def build_specs(panel: pd.DataFrame) -> pd.DataFrame:
    controls = (
        "log_gdp_pc_ppp + {total_col} + log_population + fuel_import_share + "
        "landlocked + island_economy + rd2_gdp_weighted_log_distance_2000 + C(region) + C(year)"
    )
    country_fe_controls = "log_gdp_pc_ppp + {total_col} + log_population + fuel_import_share + C(iso3) + C(year)"
    year_fe_only = "log_gdp_pc_ppp + C(year)"
    between_controls = (
        "log_gdp_pc_ppp + {total_col} + log_population + fuel_import_share + "
        "landlocked + island_economy + rd2_gdp_weighted_log_distance_2000 + C(region)"
    )

    outcomes = [
        ("split", "import_product_gini", "Product Gini", "log_total_imports_product"),
        ("split", "import_partner_gini", "Partner Gini", "log_total_imports_partner"),
        ("extensive_margin", "log_active_hs6_products", "log active HS6 products", "log_total_imports_product"),
        ("extensive_margin", "log_active_partners", "log active partners", "log_total_imports_partner"),
        ("top_share_margin", "top_1_product_share", "top-1 HS6 product import share", "log_total_imports_product"),
        ("top_share_margin", "top_5_product_share", "top-5 HS6 product import share", "log_total_imports_product"),
        ("top_share_margin", "top_5_partner_share", "top-5 partner import share", "log_total_imports_partner"),
        ("data_quality", "unspecified_import_share", "HS6 999999 import share", "log_total_imports_partner"),
        ("exclusions", "no_fuel_product_gini", "Product Gini excluding HS27 fuels", "log_total_imports_product"),
        ("exclusions", "no_fuel_partner_gini", "Partner Gini excluding HS27 fuels", "log_total_imports_partner"),
        ("exclusions", "no_food_product_gini", "Product Gini excluding HS01-24 food/staples proxy", "log_total_imports_product"),
        ("exclusions", "no_food_partner_gini", "Partner Gini excluding HS01-24 food/staples proxy", "log_total_imports_partner"),
        ("exclusions", "ex_energy_product_gini", "Product Gini excluding Exercise 3 energy bin", "log_total_imports_product"),
    ]
    rows: list[dict[str, Any]] = []
    country_means = make_country_mean_panel(panel)
    for question, outcome, label, total_col in outcomes:
        rows.append(
            run_one_model(
                panel,
                question=question,
                spec="pooled_year_fe",
                outcome=outcome,
                outcome_label=label,
                formula=f"{outcome} ~ {year_fe_only}",
                total_import_control="none",
            )
        )
        rows.append(
            run_one_model(
                panel,
                question=question,
                spec="controlled_region_year_fe",
                outcome=outcome,
                outcome_label=label,
                formula=f"{outcome} ~ {controls.format(total_col=total_col)}",
                total_import_control=total_col,
            )
        )
        rows.append(
            run_one_model(
                country_means,
                question=question,
                spec="between_country_means",
                outcome=outcome,
                outcome_label=label,
                formula=f"{outcome} ~ {between_controls.format(total_col=total_col)}",
                total_import_control=total_col,
                cluster_col=None,
            )
        )
        rows.append(
            run_one_model(
                panel,
                question="country_fixed_effects" if question in {"split", "extensive_margin", "top_share_margin"} else question,
                spec="country_year_fe",
                outcome=outcome,
                outcome_label=label,
                formula=f"{outcome} ~ {country_fe_controls.format(total_col=total_col)}",
                total_import_control=total_col,
            )
        )
        if question in {"split", "extensive_margin", "top_share_margin"}:
            no_conflict = panel[panel["conflict_year"].eq(0)].copy()
            rows.append(
                run_one_model(
                    no_conflict,
                    question="conflict_filter",
                    spec="controlled_region_year_fe_no_conflict_years",
                    outcome=outcome,
                    outcome_label=label,
                    formula=f"{outcome} ~ {controls.format(total_col=total_col)}",
                    total_import_control=total_col,
                )
            )
    return pd.DataFrame(rows)


def make_country_mean_panel(panel: pd.DataFrame) -> pd.DataFrame:
    numeric = [
        "import_product_gini",
        "import_partner_gini",
        "log_active_hs6_products",
        "log_active_partners",
        "top_1_product_share",
        "top_5_product_share",
        "top_5_partner_share",
        "unspecified_import_share",
        "no_fuel_product_gini",
        "no_fuel_partner_gini",
        "no_food_product_gini",
        "no_food_partner_gini",
        "ex_energy_product_gini",
        "log_gdp_pc_ppp",
        "log_total_imports_product",
        "log_total_imports_partner",
        "log_population",
        "fuel_import_share",
        "landlocked",
        "island_economy",
        "rd2_gdp_weighted_log_distance_2000",
    ]
    base = panel.groupby("iso3", as_index=False)[numeric].mean(numeric_only=True)
    labels = panel[["iso3", "country", "region", "income_group"]].drop_duplicates("iso3")
    return base.merge(labels, on="iso3", how="left", validate="one_to_one")


def attenuation_checks(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    checks = [
        (
            "product_gini_add_product_count",
            "Does product extensive margin absorb the income slope?",
            "import_product_gini",
            "Product Gini",
            "log_total_imports_product",
            "log_active_hs6_products",
        ),
        (
            "partner_gini_add_partner_count",
            "Does partner extensive margin absorb the income slope?",
            "import_partner_gini",
            "Partner Gini",
            "log_total_imports_partner",
            "log_active_partners",
        ),
    ]
    base_controls = (
        "log_gdp_pc_ppp + {total_col} + log_population + fuel_import_share + "
        "landlocked + island_economy + rd2_gdp_weighted_log_distance_2000 + C(region) + C(year)"
    )
    for check_id, question, outcome, label, total_col, margin_col in checks:
        base_formula = f"{outcome} ~ {base_controls.format(total_col=total_col)}"
        augmented_formula = f"{outcome} ~ {base_controls.format(total_col=total_col)} + {margin_col}"
        for spec, formula in [("controlled", base_formula), ("controlled_plus_extensive_margin", augmented_formula)]:
            result = run_one_model(
                panel,
                question=question,
                spec=spec,
                outcome=outcome,
                outcome_label=label,
                formula=formula,
                total_import_control=total_col,
            )
            result["check_id"] = check_id
            result["added_margin"] = margin_col if spec.endswith("extensive_margin") else ""
            rows.append(result)
    out = pd.DataFrame(rows)
    if not out.empty:
        piv = out.pivot_table(
            index="check_id", columns="spec", values="coef_log_income", aggfunc="first"
        ).reset_index()
        if {"controlled", "controlled_plus_extensive_margin"}.issubset(piv.columns):
            piv["income_coef_change_after_margin"] = piv["controlled_plus_extensive_margin"] - piv["controlled"]
            out = out.merge(piv[["check_id", "income_coef_change_after_margin"]], on="check_id", how="left")
    return out


def make_sample_diagnostics(panel: pd.DataFrame, geo: pd.DataFrame) -> pd.DataFrame:
    rows = [
        ("panel_rows", len(panel)),
        ("countries", panel["iso3"].nunique()),
        ("year_min", panel["year"].min()),
        ("year_max", panel["year"].max()),
        ("balanced_country_years", int(panel.groupby("iso3")["year"].nunique().eq(END_YEAR - START_YEAR + 1).sum())),
        ("conflict_year_rows", int(panel.get("conflict_year", pd.Series(dtype=int)).sum()) if "conflict_year" in panel else np.nan),
        ("conflict_countries", int(panel.loc[panel.get("conflict_year", 0).eq(1), "iso3"].nunique()) if "conflict_year" in panel else np.nan),
        ("missing_battle_related_deaths_values", int(panel["battle_related_deaths"].isna().sum()) if "battle_related_deaths" in panel else np.nan),
        ("mean_fuel_import_share", panel["fuel_import_share"].mean() if "fuel_import_share" in panel else np.nan),
        ("mean_food_staple_import_share_removed", panel["food_staple_import_share_removed"].mean() if "food_staple_import_share_removed" in panel else np.nan),
        ("mean_hs6_999999_share", panel["unspecified_import_share"].mean() if "unspecified_import_share" in panel else np.nan),
        ("max_hs6_999999_share", panel["unspecified_import_share"].max() if "unspecified_import_share" in panel else np.nan),
        ("landlocked_countries", int(geo["landlocked"].sum()) if "landlocked" in geo else np.nan),
        ("island_or_island_economies", int(geo["island_economy"].sum()) if "island_economy" in geo else np.nan),
    ]
    missing_cols = [
        "import_product_gini",
        "import_partner_gini",
        "log_gdp_pc_ppp",
        "log_total_imports_product",
        "log_total_imports_partner",
        "log_population",
        "fuel_import_share",
        "unspecified_import_share",
        "no_food_product_gini",
    ]
    for col in missing_cols:
        if col in panel.columns:
            rows.append((f"missing_{col}", int(panel[col].isna().sum())))
    return pd.DataFrame(rows, columns=["diagnostic", "value"])


def format_p(value: float) -> str:
    if not np.isfinite(value):
        return "n/a"
    if value < 0.001:
        return "<0.001"
    return f"{value:.3f}"


def fmt_num(value: float, digits: int = 4) -> str:
    if not np.isfinite(value):
        return "n/a"
    return f"{value:.{digits}f}"


def markdown_result_row(row: pd.Series) -> str:
    coef = row["effect_per_income_doubling"]
    se = row["se_per_income_doubling"]
    pval = row["p_log_income"]
    star = "**" if np.isfinite(pval) and pval < 0.05 else ""
    return (
        f"| {row['outcome_label']} | {row['spec']} | "
        f"{star}{fmt_num(coef)}{star} | {fmt_num(se)} | {star}{format_p(pval)}{star} | "
        f"{int(row['nobs'])} | {int(row['countries'])} |"
    )


def interpret_direction(result: pd.DataFrame, outcome: str, spec: str) -> str:
    sub = result[(result["outcome"].eq(outcome)) & (result["spec"].eq(spec)) & result["status"].eq("ok")]
    if sub.empty:
        return "not estimated"
    row = sub.iloc[0]
    effect = row["effect_per_income_doubling"]
    p = row["p_log_income"]
    direction = "negative" if effect < 0 else "positive"
    sig = "statistically distinguishable from zero" if p < 0.05 else "not statistically distinguishable from zero"
    return f"{direction}, {sig}, effect per doubling {effect:.4f}"


def write_markdown(panel: pd.DataFrame, results: pd.DataFrame, attenuation: pd.DataFrame, diagnostics: pd.DataFrame) -> None:
    ok = results[results["status"].eq("ok")].copy()
    controlled = ok[ok["spec"].eq("controlled_region_year_fe")].copy()
    country_fe = ok[ok["spec"].eq("country_year_fe")].copy()
    between = ok[ok["spec"].eq("between_country_means")].copy()
    no_conflict = ok[ok["spec"].eq("controlled_region_year_fe_no_conflict_years")].copy()

    split_rows = controlled[controlled["question"].eq("split")]
    margin_rows = controlled[controlled["question"].isin(["extensive_margin", "top_share_margin"])]
    exclusion_rows = controlled[controlled["question"].eq("exclusions")]
    data_rows = controlled[controlled["question"].eq("data_quality")]

    country_fe_compare = ok[
        ok["outcome"].isin(["import_product_gini", "import_partner_gini", "log_active_hs6_products", "log_active_partners"])
        & ok["spec"].isin(["between_country_means", "country_year_fe"])
    ].copy()
    country_fe_compare["order"] = country_fe_compare["spec"].map({"between_country_means": 0, "country_year_fe": 1})
    country_fe_compare = country_fe_compare.sort_values(["outcome", "order"])

    def table(frame: pd.DataFrame) -> str:
        if frame.empty:
            return "No estimates."
        lines = ["| Outcome | Spec | Effect per income doubling | SE | p | N | Countries |", "| --- | --- | ---: | ---: | ---: | ---: | ---: |"]
        lines.extend(markdown_result_row(row) for _, row in frame.iterrows())
        return "\n".join(lines)

    product_control = interpret_direction(results, "import_product_gini", "controlled_region_year_fe")
    partner_control = interpret_direction(results, "import_partner_gini", "controlled_region_year_fe")
    product_fe = interpret_direction(results, "import_product_gini", "country_year_fe")
    partner_fe = interpret_direction(results, "import_partner_gini", "country_year_fe")
    product_between = interpret_direction(results, "import_product_gini", "between_country_means")
    partner_between = interpret_direction(results, "import_partner_gini", "between_country_means")
    no_conflict_product = interpret_direction(no_conflict, "import_product_gini", "controlled_region_year_fe_no_conflict_years")
    no_conflict_partner = interpret_direction(no_conflict, "import_partner_gini", "controlled_region_year_fe_no_conflict_years")

    attenuation_lines = []
    if not attenuation.empty:
        view = attenuation[attenuation["status"].eq("ok")].copy()
        view = view.sort_values(["check_id", "spec"])
        attenuation_lines = [
            "| Check | Spec | Income effect per doubling | p | Change after adding margin |",
            "| --- | --- | ---: | ---: | ---: |",
        ]
        for _, row in view.iterrows():
            star = "**" if row["p_log_income"] < 0.05 else ""
            attenuation_lines.append(
                f"| {row['check_id']} | {row['spec']} | {star}{fmt_num(row['effect_per_income_doubling'])}{star} | "
                f"{star}{format_p(row['p_log_income'])}{star} | {fmt_num(row.get('income_coef_change_after_margin', np.nan))} |"
            )

    diag_lines = ["| Diagnostic | Value |", "| --- | ---: |"]
    for _, row in diagnostics.iterrows():
        val = row["value"]
        if isinstance(val, float):
            val_text = fmt_num(val, 6)
        else:
            val_text = str(val)
        diag_lines.append(f"| {row['diagnostic']} | {val_text} |")

    text = f"""# Income and Import Concentration Hypothesis Checks

Created UTC: `{now_utc()}`

## Purpose

This memo runs the checklist behind the question: why do we see a strong negative relationship between income and import concentration? The exercise is descriptive, not causal. Unit of observation is country-year for the balanced `rd2_countries` import panel, {START_YEAR}-{END_YEAR}.

## Bottom Line

- Product concentration: controlled product-Gini slope is {product_control}.
- Partner concentration: controlled partner-Gini slope is {partner_control}.
- Between versus within: product Gini is {product_between} in country means but {product_fe} with country fixed effects. Partner Gini is {partner_between} in country means but {partner_fe} with country fixed effects.
- Conflict filter: product Gini is {no_conflict_product}; partner Gini is {no_conflict_partner}.

Best reading: the simple variety story is only partly supported. In year-FE-only models, richer countries do have more active import products and partners, but after controlling for total imports, population, geography, region, year, and fuel share, active-count slopes are small and not statistically distinguishable from zero. The stronger controlled signal is lower dominance by the largest items, especially the top-five partner share and, more weakly, the top-five product share. Adding active-count controls does not attenuate the income-Gini coefficient, so do not present the mechanism as "more active products/partners" alone.

## Question 1: Product or Partner Concentration?

{table(split_rows)}

## Question 2: Extensive Margin and Top Shares

{table(margin_rows)}

## Question 3: Full Controls

The controlled specification is:

`outcome ~ log PPP GDP per capita + log total imports + log population + HS27 fuel import share + landlocked + island economy + rd2 GDP-weighted log distance + World Bank region FE + year FE`

Standard errors are clustered by country. Product-level outcomes use product totals that exclude HS6 `999999`; partner concentration follows the project convention of summing products into reporter-partner totals.

## Question 4: Fuel, Food-Staple, and Conflict Sensitivities

{table(exclusion_rows)}

Conflict-year sensitivity estimates rerun the same controlled model after dropping country-years with World Bank `VC.BTL.DETH > 0`.

{table(no_conflict)}

## Question 5: HS6 999999 Data-Quality Check

{table(data_rows)}

HS6 `999999` means commodities not specified. It is excluded from product-dependent concentration measures before aggregation. The row above asks whether the share of imports coded as `999999` is itself correlated with income.

## Question 6: Mostly Cross-Country or Within-Country?

{table(country_fe_compare)}

Country fixed effects use:

`outcome ~ log PPP GDP per capita + log total imports + log population + HS27 fuel import share + country FE + year FE`

## Extensive-Margin Attenuation

{chr(10).join(attenuation_lines) if attenuation_lines else "No attenuation estimates."}

## Data and Measure Notes

- Income: World Bank constant PPP GDP per capita from `{rel(WDI_CONTROLS)}`.
- Product concentration: import Product Gini and product counts exclude HS6 `999999`.
- Partner concentration: baseline partner totals include HS6 `999999` by partner-total convention; `partnerCode == 0` is excluded upstream.
- Fuel sensitivity: product-filtered import-cell sensitivity excluding HS chapter 27, mineral fuels/oils/petroleum.
- Food-staple proxy: product-filtered sensitivity excluding HS chapters 01-24, a broad food/agriculture/beverages/tobacco proxy rather than a narrow nutrition-staple list.
- Conflict years: World Bank `VC.BTL.DETH`, battle-related deaths greater than zero; missing indicator values are treated as no reported battle deaths for the filter.
- Geography: CEPII GeoDist `landlocked` and CEPII dyadic `distw`; remoteness is the GDP-weighted mean log distance from a reporter to other rd2 sample economies using 2000 GDP weights. Island economy is a documented ISO3 flag for island or island-like rd2 economies: `{", ".join(sorted(ISLAND_OR_ISLAND_ECONOMY_ISO3))}`.

## Diagnostics

{chr(10).join(diag_lines)}

## Outputs

- Analysis panel: `{rel(OUT_DIR / "analysis_panel.csv")}`
- Regression results: `{rel(OUT_DIR / "income_import_concentration_model_results.csv")}`
- Merge audit: `{rel(OUT_DIR / "merge_audit.csv")}`
- Attenuation checks: `{rel(OUT_DIR / "extensive_margin_attenuation_checks.csv")}`
- Filtered import-cell sensitivity cache: `{rel(OUT_DIR / "filtered_import_cell_concentration.csv")}`
- Figure: `{rel(FIG_DIR / "income_coefficients_by_question.png")}`
"""
    (OUT_DIR / "income_import_concentration_hypotheses.md").write_text(text, encoding="utf-8")


def plot_results(results: pd.DataFrame) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    sub = results[
        results["status"].eq("ok")
        & results["spec"].isin(["controlled_region_year_fe", "country_year_fe", "between_country_means"])
        & results["outcome"].isin(
            [
                "import_product_gini",
                "import_partner_gini",
                "log_active_hs6_products",
                "log_active_partners",
                "top_1_product_share",
                "top_5_product_share",
                "top_5_partner_share",
                "no_fuel_product_gini",
                "no_food_product_gini",
                "unspecified_import_share",
            ]
        )
    ].copy()
    if sub.empty:
        return
    sub["label"] = sub["outcome_label"] + "\n" + sub["spec"]
    sub = sub.sort_values(["question", "outcome", "spec"])
    y = np.arange(len(sub))
    fig_h = max(7, len(sub) * 0.36)
    fig, ax = plt.subplots(figsize=(12, fig_h))
    ax.axvline(0, color="#30343b", linewidth=1)
    ax.errorbar(
        sub["effect_per_income_doubling"],
        y,
        xerr=1.96 * sub["se_per_income_doubling"],
        fmt="o",
        color="#1f5f8b",
        ecolor="#9ab4c7",
        capsize=3,
    )
    ax.set_yticks(y)
    ax.set_yticklabels(sub["label"], fontsize=8)
    ax.set_xlabel("Income coefficient per GDP-per-capita doubling")
    ax.set_title("Income and import concentration hypothesis checks")
    ax.grid(axis="x", color="#e5e9f0", linewidth=0.8)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "income_coefficients_by_question.png", dpi=180)
    plt.close(fig)


def write_manifest(results: pd.DataFrame, panel: pd.DataFrame) -> None:
    manifest = {
        "created_at_utc": now_utc(),
        "country_sample": "rd2_countries",
        "start_year": START_YEAR,
        "end_year": END_YEAR,
        "rows_panel": int(len(panel)),
        "countries_panel": int(panel["iso3"].nunique()),
        "models": int(len(results)),
        "models_ok": int(results["status"].eq("ok").sum()),
        "sources": {
            "balanced_countries": rel(CLASSIFICATION),
            "concentration": rel(CONCENTRATION),
            "import_bin_decomposition": rel(IMPORT_BIN_DECOMP),
            "filtered_import_cells": rel(IMPORT_CELL_DIR),
            "exercise_04_partner_counterfactual": rel(EX04_PARTNER_COUNTERFACTUAL),
            "wdi_controls": rel(WDI_CONTROLS),
            "filtered_import_cell_concentration": rel(OUT_DIR / "filtered_import_cell_concentration.csv"),
            "cepii_dist": rel(CEPII_DIST),
            "cepii_geo": rel(CEPII_GEO),
            "world_bank_battle_deaths": rel(OUT_DIR / "world_bank_battle_deaths_2000_2024.csv"),
        },
        "output_files": {
            "analysis_panel": rel(OUT_DIR / "analysis_panel.csv"),
            "model_results": rel(OUT_DIR / "income_import_concentration_model_results.csv"),
            "attenuation_checks": rel(OUT_DIR / "extensive_margin_attenuation_checks.csv"),
            "diagnostics": rel(OUT_DIR / "sample_diagnostics.csv"),
            "merge_audit": rel(OUT_DIR / "merge_audit.csv"),
            "markdown": rel(OUT_DIR / "income_import_concentration_hypotheses.md"),
            "figure": rel(FIG_DIR / "income_coefficients_by_question.png"),
        },
        "measurement_rules": [
            "Product-dependent outcomes exclude HS6 999999 before aggregation.",
            "Baseline partner concentration follows partner-total convention and includes HS6 999999.",
            "Food-staple sensitivity is product-filtered and therefore excludes HS6 999999 by construction.",
            "World partner code 0 is excluded upstream.",
        ],
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run income/import-concentration hypothesis checks.")
    parser.add_argument("--refresh-food", action="store_true", help="Recompute the HS01-24 no-food import-cell cache.")
    parser.add_argument("--refresh-conflict", action="store_true", help="Re-fetch World Bank battle-related deaths.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    panel, diagnostics, merge_audit = build_analysis_panel(refresh_food=args.refresh_food, refresh_conflict=args.refresh_conflict)
    results = build_specs(panel)
    attenuation = attenuation_checks(panel)
    panel.to_csv(OUT_DIR / "analysis_panel.csv", index=False)
    results.to_csv(OUT_DIR / "income_import_concentration_model_results.csv", index=False)
    attenuation.to_csv(OUT_DIR / "extensive_margin_attenuation_checks.csv", index=False)
    diagnostics.to_csv(OUT_DIR / "sample_diagnostics.csv", index=False)
    merge_audit.to_csv(OUT_DIR / "merge_audit.csv", index=False)
    plot_results(results)
    write_markdown(panel, results, attenuation, diagnostics)
    write_manifest(results, panel)
    print(f"Wrote {rel(OUT_DIR / 'income_import_concentration_hypotheses.md')}")
    print(f"Panel rows: {len(panel)}; countries: {panel['iso3'].nunique()}; models ok: {results['status'].eq('ok').sum()}/{len(results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
