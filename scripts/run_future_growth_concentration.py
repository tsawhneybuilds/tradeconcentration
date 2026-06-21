#!/usr/bin/env python3
"""Future export-growth regressions on trade concentration.

This is a descriptive/predictive panel exercise. It asks whether base-year
import or export concentration predicts later merchandise export growth in the
rd2 country sample. It does not estimate a causal effect of concentration.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import seaborn as sns

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_country_size_effect as cse  # noqa: E402
from trade_concentration_pipeline import sample_processed_path, sample_results_dir  # noqa: E402


COUNTRY_SAMPLE_CHOICES = ("rd2_countries",)
FLOWS = ("Exports", "Imports")
HORIZONS = (1, 5, 10)
WORLD_BANK_URL = "https://api.worldbank.org/v2/country/{countries}/indicator/{indicator}"
CONTROL_CACHE_COLUMNS = [
    "iso3",
    "year",
    "gdp_current_usd",
    "gdp_constant_2015_usd",
    "population",
    "gni_per_capita_current_usd",
    "gni_per_capita_constant_2015_usd",
    "region",
    "income_group",
    "metadata_source",
]
EXERCISE_02_CONTROL_CACHE = "exercise_02_world_bank_controls.csv"
CONTROL_CACHE = "future_growth_concentration_world_bank_controls.csv"
US_DEFLATOR_CACHE = "future_growth_concentration_us_gdp_deflator.csv"
MIN_COMPLETE_REAL_CONTROL_SHARE = 0.70
PRIMARY_OUTCOME = "annualized_real_export_growth_log"
OIL_EX_OUTCOME = "annualized_real_export_growth_log_ex_oil"
NOMINAL_OUTCOME = "annualized_nominal_export_growth_log"
PRIOR_GROWTH_CONTROL = "prior_export_growth_control"
SIZE_ADJUSTED_OUTCOME = "size_adjusted_annualized_real_export_growth_log"
DOLLAR_CHANGE_OUTCOME = "annualized_real_export_change_constant_2015_usd"
ASINH_CHANGE_OUTCOME = "annualized_asinh_real_export_change"
ASINH_EXPORT_SCALE = 1_000_000_000.0
BASE_CONTROL_TERMS = [
    "log_initial_exports_constant_2015_usd",
    "oil_export_share",
    "log_gdp_constant_2015_usd",
    "log_population",
    "log_gni_per_capita_constant_2015_usd",
]
SIZE_ADJUSTMENT_CONTROL_TERMS = BASE_CONTROL_TERMS
ACTIVE_COUNT_CONTROL_TERMS = [
    "log_product_active_count",
    "log_partner_active_count",
]
BASE_SIZE_BIN_COUNT = 5
PREFERRED_MECHANISM_IDENTITY_MODE = "hs6_harmonized_family"
EX12_EXTENSIVE_DIR = "exercise_12_extensive_margin_tables"
EX12_EXTENSIVE_COUNTRY_YEAR = "extensive_margin_country_year.csv"
EX12_PRODUCT_ENTRY_ROBUSTNESS = "extensive_margin_product_entry_robustness.csv"
EX12_EXTENSIVE_MANIFEST = "run_manifest_exercise_12_extensive_margin.json"
COUNTRY_SIZE_PANEL = "country_size_effect_panel.parquet"
EXTENSIVE_CHANNELS = {
    "net_new_product": "net_new_product",
    "net_new_partner_existing_product": "new_partner_existing_product",
    "new_product_partner_cell_existing_product_partner": "new_cell_existing_product_partner",
    "existing_product_partner_cell_growth": "existing_cell_growth",
}
PRODUCT_ENTRY_CHANNELS = {
    "strict_zero_base_product": "strict_zero_base_product",
    "low_base_under_10k_grower": "low_base_under_10k_grower",
    "least_traded_10pct_grower": "least_traded_10pct_grower",
}
MECHANISM_OUTCOME_LABELS = {
    "net_new_product_gross_positive_share": "Net-new product gross share",
    "new_partner_existing_product_gross_positive_share": "New-partner gross share",
    "new_cell_existing_product_partner_gross_positive_share": "New cell gross share",
    "existing_cell_growth_gross_positive_share": "Existing-cell growth gross share",
    "strict_zero_base_product_gross_positive_share": "Strict-new product gross share",
    "low_base_under_10k_grower_gross_positive_share": "Low-base product gross share",
    "least_traded_10pct_grower_gross_positive_share": "Least-traded product gross share",
    "annualized_log_product_active_count_change": "Product active-count growth",
    "annualized_log_partner_active_count_change": "Partner active-count growth",
}
MECHANISM_OUTCOME_SPECS = (
    ("net_new_product_gross_positive_share", "product_discovery"),
    ("new_partner_existing_product_gross_positive_share", "destination_diversification"),
    ("new_cell_existing_product_partner_gross_positive_share", "relationship_entry"),
    ("existing_cell_growth_gross_positive_share", "intensive_margin"),
    ("strict_zero_base_product_gross_positive_share", "strict_new_product"),
    ("low_base_under_10k_grower_gross_positive_share", "low_base_product_growth"),
    ("least_traded_10pct_grower_gross_positive_share", "least_traded_product_growth"),
    ("annualized_log_product_active_count_change", "product_active_count"),
    ("annualized_log_partner_active_count_change", "partner_active_count"),
)
EXPOSURE_SPECS = (
    ("product", "gini", "product_gini", "Product Gini"),
    ("partner", "gini", "partner_gini", "Partner Gini"),
    ("product_partner_cell", "gini", "product_partner_cell_gini", "Product-partner cell Gini"),
    ("product", "top_1pct_share", "product_top_1pct_share", "Product top 1% share"),
    ("partner", "top_1pct_share", "partner_top_1pct_share", "Partner top 1% share"),
    (
        "product_partner_cell",
        "top_1pct_share",
        "product_partner_cell_top_1pct_share",
        "Product-partner cell top 1% share",
    ),
    ("product", "top_5pct_share", "product_top_5pct_share", "Product top 5% share"),
    ("partner", "top_5pct_share", "partner_top_5pct_share", "Partner top 5% share"),
    (
        "product_partner_cell",
        "top_5pct_share",
        "product_partner_cell_top_5pct_share",
        "Product-partner cell top 5% share",
    ),
)
PAIRED_METRICS = (
    ("gini", "product_gini", "partner_gini"),
    ("top_1pct_share", "product_top_1pct_share", "partner_top_1pct_share"),
    ("top_5pct_share", "product_top_5pct_share", "partner_top_5pct_share"),
)
BUCKET_ORDER = (
    "high_product_high_partner",
    "high_product_low_partner",
    "low_product_high_partner",
)
BUCKET_TERMS = [f"bucket_{bucket}" for bucket in BUCKET_ORDER]


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_dirs(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def validate_unique_keys(df: pd.DataFrame, keys: list[str], label: str) -> None:
    missing = [col for col in keys if col not in df.columns]
    if missing:
        raise RuntimeError(f"{label} is missing key columns: {missing}")
    dupes = int(df.duplicated(keys).sum())
    if dupes:
        examples = df[df.duplicated(keys, keep=False)][keys].head(8).to_dict(orient="records")
        raise RuntimeError(f"{label} has {dupes:,} duplicate rows on {keys}. Examples: {examples}")


def read_csv_if_exists(path: Path, columns: Iterable[str]) -> pd.DataFrame:
    columns = list(columns)
    if not path.exists():
        return pd.DataFrame(columns=columns)
    data = pd.read_csv(path)
    missing = [col for col in columns if col not in data.columns]
    if missing:
        return pd.DataFrame(columns=columns)
    return data[columns].copy()


def read_control_cache_if_exists(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=CONTROL_CACHE_COLUMNS)
    data = pd.read_csv(path)
    for column in CONTROL_CACHE_COLUMNS:
        if column not in data.columns:
            data[column] = np.nan
    return data[CONTROL_CACHE_COLUMNS].copy()


def fetch_world_bank_indicator(
    iso3s: list[str],
    indicator: str,
    value_name: str,
    start_year: int,
    end_year: int,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    countries_all = sorted(set(iso3s))
    for start in range(0, len(countries_all), 20):
        countries = ";".join(countries_all[start : start + 20])
        url = WORLD_BANK_URL.format(countries=countries, indicator=indicator)
        page = 1
        pages = 1
        while page <= pages:
            last_exc: Exception | None = None
            for attempt in range(3):
                try:
                    response = requests.get(
                        url,
                        params={"format": "json", "per_page": 20000, "page": page, "date": f"{start_year}:{end_year}"},
                        timeout=60,
                    )
                    response.raise_for_status()
                    payload = response.json()
                    break
                except Exception as exc:
                    last_exc = exc
                    time.sleep(0.5 * (attempt + 1))
            else:
                raise RuntimeError(f"World Bank request failed for {indicator}, countries={countries}, page={page}: {last_exc}")
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


def standardize_controls(controls: pd.DataFrame) -> pd.DataFrame:
    out = controls.copy()
    for col in CONTROL_CACHE_COLUMNS:
        if col not in out.columns:
            out[col] = "" if col in {"region", "income_group", "metadata_source"} else np.nan
    out = out[CONTROL_CACHE_COLUMNS].copy()
    out["iso3"] = out["iso3"].astype(str).str.upper()
    out["year"] = pd.to_numeric(out["year"], errors="coerce")
    for col in [
        "gdp_current_usd",
        "gdp_constant_2015_usd",
        "population",
        "gni_per_capita_current_usd",
        "gni_per_capita_constant_2015_usd",
    ]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["iso3", "year"]).copy()
    out["year"] = out["year"].astype(int)
    out["region"] = out["region"].replace("", np.nan).fillna("Unclassified").astype(str)
    out["income_group"] = out["income_group"].replace("", np.nan).fillna("").astype(str)
    out["metadata_source"] = out["metadata_source"].replace("", np.nan).fillna("cache_or_api").astype(str)
    return out.drop_duplicates(["iso3", "year"], keep="last")


def metadata_from_control_caches(paths: Iterable[Path]) -> pd.DataFrame:
    frames = []
    for path in paths:
        if not path.exists():
            continue
        data = pd.read_csv(path)
        if {"iso3", "year", "region"}.issubset(data.columns):
            if "income_group" not in data.columns:
                data["income_group"] = ""
            frames.append(data[["iso3", "year", "region", "income_group"]].copy())
    if not frames:
        return pd.DataFrame(columns=["iso3", "year", "region", "income_group"])
    metadata = pd.concat(frames, ignore_index=True)
    metadata["iso3"] = metadata["iso3"].astype(str).str.upper()
    metadata["year"] = pd.to_numeric(metadata["year"], errors="coerce")
    metadata = metadata.dropna(subset=["iso3", "year"]).copy()
    metadata["year"] = metadata["year"].astype(int)
    metadata["region"] = metadata["region"].replace("", np.nan)
    metadata["income_group"] = metadata["income_group"].replace("", np.nan)
    metadata = metadata[metadata["region"].notna() & ~metadata["region"].astype(str).eq("Unclassified")].copy()
    return metadata.drop_duplicates(["iso3", "year"], keep="last")


def apply_control_metadata(controls: pd.DataFrame, metadata: pd.DataFrame) -> pd.DataFrame:
    if metadata.empty or controls.empty:
        return controls
    out = controls.merge(
        metadata.rename(columns={"region": "region_cached", "income_group": "income_group_cached"}),
        on=["iso3", "year"],
        how="left",
        validate="one_to_one",
    )
    use_region = out["region_cached"].notna() & out["region"].isin(["", "Unclassified"])
    out.loc[use_region, "region"] = out.loc[use_region, "region_cached"]
    use_income = out["income_group_cached"].notna() & out["income_group"].isin(["", "nan"])
    out.loc[use_income, "income_group"] = out.loc[use_income, "income_group_cached"]
    return out.drop(columns=["region_cached", "income_group_cached"])


def complete_control_share(controls: pd.DataFrame, keys: pd.DataFrame) -> float:
    if controls.empty or keys.empty:
        return 0.0
    merged = keys.merge(controls, on=["iso3", "year"], how="left")
    complete = merged[["gdp_constant_2015_usd", "population", "gni_per_capita_constant_2015_usd"]].notna().all(axis=1)
    return float(complete.mean()) if len(complete) else 0.0


def load_or_fetch_world_bank_controls(
    iso3s: list[str],
    requested_keys: pd.DataFrame,
    start_year: int,
    end_year: int,
    cache_path: Path,
    refresh: bool = False,
) -> pd.DataFrame:
    requested_keys = requested_keys[["iso3", "year"]].drop_duplicates().copy()
    requested_keys["iso3"] = requested_keys["iso3"].astype(str).str.upper()
    requested_keys["year"] = pd.to_numeric(requested_keys["year"], errors="coerce").astype(int)

    frames: list[pd.DataFrame] = []
    prior_cache = sample_processed_path(EXERCISE_02_CONTROL_CACHE, "rd2_countries")
    metadata = metadata_from_control_caches([prior_cache, cache_path])
    if prior_cache.exists() and not refresh:
        frames.append(read_control_cache_if_exists(prior_cache))
    if cache_path.exists() and not refresh:
        frames.append(read_control_cache_if_exists(cache_path))

    controls = standardize_controls(pd.concat(frames, ignore_index=True)) if frames else pd.DataFrame(columns=CONTROL_CACHE_COLUMNS)
    if refresh or complete_control_share(controls, requested_keys) < MIN_COMPLETE_REAL_CONTROL_SHARE:
        fetched_frames: list[pd.DataFrame] = []
        indicator_specs = [
            ("NY.GDP.MKTP.CD", "gdp_current_usd"),
            ("NY.GDP.MKTP.KD", "gdp_constant_2015_usd"),
            ("SP.POP.TOTL", "population"),
            ("NY.GNP.PCAP.CD", "gni_per_capita_current_usd"),
            ("NY.GNP.PCAP.KD", "gni_per_capita_constant_2015_usd"),
        ]
        for indicator, value_name in indicator_specs:
            try:
                fetched_frames.append(fetch_world_bank_indicator(iso3s, indicator, value_name, start_year, end_year))
            except Exception as exc:
                print(f"World Bank control refresh warning for {indicator}: {exc}", file=sys.stderr)
        if fetched_frames:
            base = pd.DataFrame(
                [(iso3, year) for iso3 in sorted(set(iso3s)) for year in range(start_year, end_year + 1)],
                columns=["iso3", "year"],
            )
            if not metadata.empty:
                base = base.merge(metadata, on=["iso3", "year"], how="left")
            else:
                base["region"] = "Unclassified"
                base["income_group"] = ""
            for value_name in [
                "gdp_current_usd",
                "gdp_constant_2015_usd",
                "population",
                "gni_per_capita_current_usd",
                "gni_per_capita_constant_2015_usd",
            ]:
                value_frames = [frame[["iso3", "year", value_name]] for frame in fetched_frames if value_name in frame.columns]
                if value_frames:
                    combined = pd.concat(value_frames, ignore_index=True)
                    combined["iso3"] = combined["iso3"].astype(str).str.upper()
                    combined["year"] = pd.to_numeric(combined["year"], errors="coerce")
                    combined[value_name] = pd.to_numeric(combined[value_name], errors="coerce")
                    combined = (
                        combined.dropna(subset=["iso3", "year"])
                        .sort_values(["iso3", "year", value_name], na_position="first")
                        .drop_duplicates(["iso3", "year"], keep="last")
                    )
                    base = base.merge(combined, on=["iso3", "year"], how="left")
            base["region"] = base["region"].replace("", np.nan).fillna("Unclassified")
            base["income_group"] = base["income_group"].replace("", np.nan).fillna("")
            base["metadata_source"] = "world_bank_api"
            controls = standardize_controls(pd.concat([controls, base], ignore_index=True))

    controls = apply_control_metadata(controls, metadata)
    controls = controls[controls["iso3"].isin(iso3s) & controls["year"].between(start_year, end_year)].copy()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    controls.to_csv(cache_path, index=False)
    validate_unique_keys(controls, ["iso3", "year"], "World Bank controls")
    return controls


def load_or_fetch_us_deflator(start_year: int, end_year: int, cache_path: Path, refresh: bool = False) -> pd.DataFrame:
    columns = ["year", "us_gdp_deflator"]
    deflator = read_csv_if_exists(cache_path, columns) if cache_path.exists() and not refresh else pd.DataFrame(columns=columns)
    if deflator.empty or deflator["year"].nunique() < (end_year - start_year + 1) * 0.80:
        try:
            fetched = fetch_world_bank_indicator(["USA"], "NY.GDP.DEFL.ZS", "us_gdp_deflator", start_year, end_year)
            if not fetched.empty:
                deflator = fetched[columns].copy()
        except Exception as exc:
            print(f"US GDP deflator refresh warning: {exc}", file=sys.stderr)
    if deflator.empty:
        return pd.DataFrame(columns=columns)
    deflator["year"] = pd.to_numeric(deflator["year"], errors="coerce")
    deflator["us_gdp_deflator"] = pd.to_numeric(deflator["us_gdp_deflator"], errors="coerce")
    deflator = deflator.dropna(subset=["year"]).copy()
    deflator["year"] = deflator["year"].astype(int)
    deflator = deflator.drop_duplicates(["year"], keep="last").sort_values("year")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    deflator.to_csv(cache_path, index=False)
    return deflator


def load_concentration_panel(country_sample: str, start_year: int, end_year: int) -> pd.DataFrame:
    path = sample_processed_path("concentration_all_years.parquet", country_sample)
    if not path.exists():
        raise FileNotFoundError(f"Missing concentration panel: {path}")
    panel = pd.read_parquet(path)
    needed = {
        "country",
        "iso3",
        "reporter_code",
        "year",
        "flow",
        "variant",
        "total_trade_value",
        *[spec[2] for spec in EXPOSURE_SPECS],
    }
    missing = sorted(needed - set(panel.columns))
    if missing:
        raise RuntimeError(f"Concentration panel is missing required columns: {missing}")
    panel = panel[panel["variant"].eq("baseline") & panel["year"].between(start_year, end_year)].copy()
    if panel.empty:
        raise RuntimeError("No baseline concentration rows remain after the requested year filter.")
    panel["iso3"] = panel["iso3"].astype(str).str.upper()
    panel["year"] = pd.to_numeric(panel["year"], errors="coerce").astype(int)
    panel["reporter_code"] = pd.to_numeric(panel["reporter_code"], errors="coerce").astype(int)
    validate_unique_keys(panel, ["iso3", "reporter_code", "year", "flow", "variant"], "concentration panel")
    for _dimension, _metric, column, _label in EXPOSURE_SPECS:
        values = pd.to_numeric(panel[column], errors="coerce")
        bad = values.notna() & ((values < 0) | (values > 1))
        if bool(bad.any()):
            raise RuntimeError(f"Exposure {column} has {int(bad.sum()):,} finite values outside [0, 1].")
    return panel


def load_export_totals(country_sample: str, start_year: int, end_year: int) -> pd.DataFrame:
    path = sample_processed_path("exercise_02_export_concentration_panel.parquet", country_sample)
    if not path.exists():
        raise FileNotFoundError(f"Missing export concentration panel with merchandise totals: {path}")
    exports = pd.read_parquet(path)
    needed = {"country", "iso3", "reporter_code", "year", "flow", "total_exports", "oil_exports", "oil_export_share"}
    missing = sorted(needed - set(exports.columns))
    if missing:
        raise RuntimeError(f"Export concentration panel is missing required columns: {missing}")
    exports = exports[exports["flow"].eq("Exports") & exports["year"].between(start_year - 1, end_year)].copy()
    exports["iso3"] = exports["iso3"].astype(str).str.upper()
    exports["year"] = pd.to_numeric(exports["year"], errors="coerce").astype(int)
    exports["reporter_code"] = pd.to_numeric(exports["reporter_code"], errors="coerce").astype(int)
    for col in ["total_exports", "oil_exports", "oil_export_share"]:
        exports[col] = pd.to_numeric(exports[col], errors="coerce")
    validate_unique_keys(exports, ["iso3", "reporter_code", "year"], "export totals")
    exports["total_exports_ex_oil"] = exports["total_exports"] - exports["oil_exports"].fillna(0.0)
    return exports[
        [
            "country",
            "iso3",
            "reporter_code",
            "year",
            "total_exports",
            "oil_exports",
            "oil_export_share",
            "total_exports_ex_oil",
        ]
    ].copy()


def add_log_controls(panel: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    for source, target in [
        ("gdp_current_usd", "log_gdp_current_usd"),
        ("gdp_constant_2015_usd", "log_gdp_constant_2015_usd"),
        ("population", "log_population"),
        ("gni_per_capita_current_usd", "log_gni_per_capita_current_usd"),
        ("gni_per_capita_constant_2015_usd", "log_gni_per_capita_constant_2015_usd"),
        ("product_active_count", "log_product_active_count"),
        ("partner_active_count", "log_partner_active_count"),
        ("product_partner_cell_active_count", "log_product_partner_cell_active_count"),
    ]:
        if source not in out.columns:
            out[source] = np.nan
        out[source] = pd.to_numeric(out[source], errors="coerce")
        out[target] = np.where(out[source] > 0, np.log(out[source]), np.nan)
    out["region"] = out["region"].fillna("Unclassified").astype(str)
    out["region_year"] = out["region"] + "::" + out["year"].astype(str)
    out["income_group"] = out["income_group"].fillna("Unclassified").astype(str)
    out["income_group_year"] = out["income_group"] + "::" + out["year"].astype(str)
    return out


def add_real_export_values(panel: pd.DataFrame, deflator: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    for column in [
        "base_exports_constant_2015_usd",
        "future_exports_constant_2015_usd",
        "base_exports_ex_oil_constant_2015_usd",
        "future_exports_ex_oil_constant_2015_usd",
        "prior_exports_constant_2015_usd",
        "real_export_growth_pct",
        "real_export_growth_log",
        PRIMARY_OUTCOME,
        "real_export_change_constant_2015_usd",
        DOLLAR_CHANGE_OUTCOME,
        ASINH_CHANGE_OUTCOME,
        "real_export_growth_pct_ex_oil",
        "real_export_growth_log_ex_oil",
        OIL_EX_OUTCOME,
        "log_initial_exports_constant_2015_usd",
    ]:
        out[column] = np.nan
    if deflator.empty:
        return out
    deflator = deflator[["year", "us_gdp_deflator"]].drop_duplicates("year").copy()
    out = out.merge(
        deflator.rename(columns={"year": "year", "us_gdp_deflator": "base_us_gdp_deflator"}),
        on="year",
        how="left",
        validate="many_to_one",
    )
    out = out.merge(
        deflator.rename(columns={"year": "future_year", "us_gdp_deflator": "future_us_gdp_deflator"}),
        on="future_year",
        how="left",
        validate="many_to_one",
    )
    out = out.merge(
        deflator.rename(columns={"year": "prior_year", "us_gdp_deflator": "prior_us_gdp_deflator"}),
        on="prior_year",
        how="left",
        validate="many_to_one",
    )
    out["base_exports_constant_2015_usd"] = np.where(
        (out["base_exports"] > 0) & (out["base_us_gdp_deflator"] > 0),
        out["base_exports"] / (out["base_us_gdp_deflator"] / 100.0),
        np.nan,
    )
    out["future_exports_constant_2015_usd"] = np.where(
        (out["future_exports"] > 0) & (out["future_us_gdp_deflator"] > 0),
        out["future_exports"] / (out["future_us_gdp_deflator"] / 100.0),
        np.nan,
    )
    out["base_exports_ex_oil_constant_2015_usd"] = np.where(
        (out["base_exports_ex_oil"] > 0) & (out["base_us_gdp_deflator"] > 0),
        out["base_exports_ex_oil"] / (out["base_us_gdp_deflator"] / 100.0),
        np.nan,
    )
    out["future_exports_ex_oil_constant_2015_usd"] = np.where(
        (out["future_exports_ex_oil"] > 0) & (out["future_us_gdp_deflator"] > 0),
        out["future_exports_ex_oil"] / (out["future_us_gdp_deflator"] / 100.0),
        np.nan,
    )
    out["prior_exports_constant_2015_usd"] = np.where(
        (out["prior_exports"] > 0) & (out["prior_us_gdp_deflator"] > 0),
        out["prior_exports"] / (out["prior_us_gdp_deflator"] / 100.0),
        np.nan,
    )
    valid = (out["base_exports_constant_2015_usd"] > 0) & (out["future_exports_constant_2015_usd"] > 0)
    out["real_export_growth_log"] = np.where(
        valid,
        np.log(out["future_exports_constant_2015_usd"]) - np.log(out["base_exports_constant_2015_usd"]),
        np.nan,
    )
    out["real_export_growth_pct"] = np.where(
        valid,
        (out["future_exports_constant_2015_usd"] - out["base_exports_constant_2015_usd"])
        / out["base_exports_constant_2015_usd"],
        np.nan,
    )
    out[PRIMARY_OUTCOME] = out["real_export_growth_log"] / out["horizon"]
    out["real_export_change_constant_2015_usd"] = np.where(
        valid,
        out["future_exports_constant_2015_usd"] - out["base_exports_constant_2015_usd"],
        np.nan,
    )
    out[DOLLAR_CHANGE_OUTCOME] = out["real_export_change_constant_2015_usd"] / out["horizon"]
    out[ASINH_CHANGE_OUTCOME] = np.where(
        valid,
        (
            np.arcsinh(out["future_exports_constant_2015_usd"] / ASINH_EXPORT_SCALE)
            - np.arcsinh(out["base_exports_constant_2015_usd"] / ASINH_EXPORT_SCALE)
        )
        / out["horizon"],
        np.nan,
    )
    ex_oil_valid = (out["base_exports_ex_oil_constant_2015_usd"] > 0) & (out["future_exports_ex_oil_constant_2015_usd"] > 0)
    out["real_export_growth_log_ex_oil"] = np.where(
        ex_oil_valid,
        np.log(out["future_exports_ex_oil_constant_2015_usd"]) - np.log(out["base_exports_ex_oil_constant_2015_usd"]),
        np.nan,
    )
    out["real_export_growth_pct_ex_oil"] = np.where(
        ex_oil_valid,
        (out["future_exports_ex_oil_constant_2015_usd"] - out["base_exports_ex_oil_constant_2015_usd"])
        / out["base_exports_ex_oil_constant_2015_usd"],
        np.nan,
    )
    out[OIL_EX_OUTCOME] = out["real_export_growth_log_ex_oil"] / out["horizon"]
    out["log_initial_exports_constant_2015_usd"] = np.where(
        out["base_exports_constant_2015_usd"] > 0,
        np.log(out["base_exports_constant_2015_usd"]),
        np.nan,
    )
    out[PRIOR_GROWTH_CONTROL] = np.where(
        (out["base_exports_constant_2015_usd"] > 0) & (out["prior_exports_constant_2015_usd"] > 0),
        np.log(out["base_exports_constant_2015_usd"]) - np.log(out["prior_exports_constant_2015_usd"]),
        np.nan,
    )
    return out


def add_active_count_change_variables(panel: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    pairs = [
        ("product_active_count", "future_product_active_count", "annualized_log_product_active_count_change"),
        ("partner_active_count", "future_partner_active_count", "annualized_log_partner_active_count_change"),
        (
            "product_partner_cell_active_count",
            "future_product_partner_cell_active_count",
            "annualized_log_product_partner_cell_active_count_change",
        ),
    ]
    for base_col, future_col, outcome_col in pairs:
        if base_col not in out.columns:
            out[base_col] = np.nan
        if future_col not in out.columns:
            out[future_col] = np.nan
        out[base_col] = pd.to_numeric(out[base_col], errors="coerce")
        out[future_col] = pd.to_numeric(out[future_col], errors="coerce")
        out[f"log_{base_col}"] = np.where(out[base_col] > 0, np.log(out[base_col]), np.nan)
        out[f"log_{future_col}"] = np.where(out[future_col] > 0, np.log(out[future_col]), np.nan)
        valid = (out[base_col] > 0) & (out[future_col] > 0) & (out["horizon"] > 0)
        out[outcome_col] = np.where(
            valid,
            (np.log(out[future_col]) - np.log(out[base_col])) / out["horizon"],
            np.nan,
        )
    return out


def classify_buckets(panel: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    medians = (
        out.groupby(["flow", "year"], as_index=False)[["product_gini", "partner_gini"]]
        .median()
        .rename(columns={"product_gini": "median_product_gini", "partner_gini": "median_partner_gini"})
    )
    out = out.merge(medians, on=["flow", "year"], how="left", validate="many_to_one")
    out["product_concentration_high"] = out["product_gini"] >= out["median_product_gini"]
    out["partner_concentration_high"] = out["partner_gini"] >= out["median_partner_gini"]
    out["concentration_bucket"] = np.select(
        [
            out["product_concentration_high"] & out["partner_concentration_high"],
            out["product_concentration_high"] & ~out["partner_concentration_high"],
            ~out["product_concentration_high"] & out["partner_concentration_high"],
        ],
        list(BUCKET_ORDER),
        default="low_product_low_partner",
    )
    for bucket in BUCKET_ORDER:
        out[f"bucket_{bucket}"] = out["concentration_bucket"].eq(bucket).astype(float)
    return out


def construct_future_growth_panel(
    concentration: pd.DataFrame,
    export_totals: pd.DataFrame,
    controls: pd.DataFrame,
    deflator: pd.DataFrame | None = None,
    horizons: Iterable[int] = HORIZONS,
) -> pd.DataFrame:
    validate_unique_keys(concentration, ["iso3", "reporter_code", "year", "flow", "variant"], "concentration panel")
    validate_unique_keys(export_totals, ["iso3", "reporter_code", "year"], "export totals")
    validate_unique_keys(controls, ["iso3", "year"], "World Bank controls")
    base_totals = export_totals.rename(
        columns={
            "year": "year",
            "total_exports": "base_exports",
            "oil_exports": "base_oil_exports",
            "oil_export_share": "oil_export_share",
            "total_exports_ex_oil": "base_exports_ex_oil",
        }
    )[["iso3", "reporter_code", "year", "base_exports", "base_oil_exports", "oil_export_share", "base_exports_ex_oil"]]
    prior_totals = export_totals[["iso3", "reporter_code", "year", "total_exports"]].copy()
    prior_totals["year"] += 1
    prior_totals = prior_totals.rename(columns={"total_exports": "prior_exports", "year": "year"})
    prior_totals["prior_year"] = prior_totals["year"] - 1
    panel = concentration.merge(base_totals, on=["iso3", "reporter_code", "year"], how="left", validate="many_to_one")
    panel = panel.merge(prior_totals, on=["iso3", "reporter_code", "year"], how="left", validate="many_to_one")
    panel = panel.merge(controls, on=["iso3", "year"], how="left", validate="many_to_one")
    panel = add_log_controls(panel)
    panel = classify_buckets(panel)

    rows: list[pd.DataFrame] = []
    future_base = export_totals[
        ["iso3", "reporter_code", "year", "total_exports", "total_exports_ex_oil"]
    ].copy()
    active_cols = ["product_active_count", "partner_active_count", "product_partner_cell_active_count"]
    concentration = concentration.copy()
    for col in active_cols:
        if col not in concentration.columns:
            concentration[col] = np.nan
    future_active_base = concentration[["iso3", "reporter_code", "year", "flow", *active_cols]].copy()
    for horizon in horizons:
        future = future_base.copy()
        future["year"] -= int(horizon)
        future = future.rename(
            columns={
                "total_exports": "future_exports",
                "total_exports_ex_oil": "future_exports_ex_oil",
            }
        )
        merged = panel.merge(future, on=["iso3", "reporter_code", "year"], how="left", validate="many_to_one")
        future_active = future_active_base.copy()
        future_active["year"] -= int(horizon)
        future_active = future_active.rename(columns={col: f"future_{col}" for col in active_cols})
        merged = merged.merge(
            future_active,
            on=["iso3", "reporter_code", "year", "flow"],
            how="left",
            validate="many_to_one",
        )
        merged["horizon"] = int(horizon)
        merged["future_year"] = merged["year"] + int(horizon)
        valid = (merged["base_exports"] > 0) & (merged["future_exports"] > 0)
        merged["nominal_export_growth_pct"] = np.where(valid, (merged["future_exports"] - merged["base_exports"]) / merged["base_exports"], np.nan)
        merged["nominal_export_growth_log"] = np.where(valid, np.log(merged["future_exports"]) - np.log(merged["base_exports"]), np.nan)
        merged[NOMINAL_OUTCOME] = merged["nominal_export_growth_log"] / int(horizon)
        rows.append(merged)
    out = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    out["log_initial_exports_nominal_usd"] = np.where(out["base_exports"] > 0, np.log(out["base_exports"]), np.nan)
    out = add_real_export_values(out, deflator if deflator is not None else pd.DataFrame())
    out = add_active_count_change_variables(out)
    return out.sort_values(["flow", "reporter_code", "year", "horizon"]).reset_index(drop=True)


def primary_terms_for_q(model_label: str, frame: pd.DataFrame) -> pd.Series:
    if model_label.startswith(
        (
            "bucket_",
            "base_size_",
            "drop_bottom_",
            "alternative_outcome_",
            "placebo_",
            "confounding_",
            "mechanism_",
        )
    ):
        return frame["term"].astype(str).str.startswith("bucket_")
    if model_label.startswith("paired_"):
        return frame["term"].astype(str).isin(["product_exposure", "partner_exposure", "product_x_partner"])
    if model_label.startswith("continuous_") or model_label in {
        "region_year_fe",
        "two_way_country_year_cluster",
        "lagged_growth_control",
        "oil_excluded_growth",
    }:
        exposure_cols = {spec[2] for spec in EXPOSURE_SPECS}
        return frame["term"].astype(str).isin(exposure_cols)
    return pd.Series(False, index=frame.index)


def add_grouped_q_values(models: pd.DataFrame) -> pd.DataFrame:
    if models.empty:
        return models.copy()
    out = models.copy()
    out["bh_q_value"] = np.nan
    group_cols = ["model_label", "horizon"]
    if "outcome" in out.columns:
        group_cols.append("outcome")
    for group_values, group in out.groupby(group_cols, dropna=False):
        model_label = group_values[0] if isinstance(group_values, tuple) else group_values
        mask = primary_terms_for_q(str(model_label), group) & group["status"].eq("ok")
        if bool(mask.any()):
            out.loc[group.index[mask], "bh_q_value"] = cse.benjamini_hochberg(group.loc[mask, "p_value"])
    return out


def run_continuous_models(panel: pd.DataFrame, country_sample: str) -> pd.DataFrame:
    results: list[cse.ModelResult] = []
    for horizon in sorted(panel["horizon"].dropna().astype(int).unique()):
        hpanel = panel[panel["horizon"].eq(horizon)].copy()
        for flow in FLOWS:
            fpanel = hpanel[hpanel["flow"].eq(flow)].copy()
            for dimension, metric, exposure_col, _label in EXPOSURE_SPECS:
                results.append(
                    cse.run_ols_model(
                        fpanel,
                        outcome=PRIMARY_OUTCOME,
                        terms=[exposure_col, *BASE_CONTROL_TERMS],
                        fixed_effects=["reporter_code", "year"],
                        model_label="continuous_country_year_fe",
                        sample=country_sample,
                        flow=flow,
                        dimension=dimension,
                        metric=metric,
                        cluster_col="reporter_code",
                    )
                )
                results[-1] = results[-1].__class__(**{**results[-1].__dict__, "model_label": f"continuous_country_year_fe_h{horizon}"})
    frame = cse.model_results_to_frame(results)
    frame["horizon"] = frame["model_label"].str.extract(r"_h(\d+)$")[0].astype(int)
    frame["model_label"] = "continuous_country_year_fe"
    return add_grouped_q_values(frame)


def run_bucket_models(panel: pd.DataFrame, country_sample: str) -> pd.DataFrame:
    results: list[cse.ModelResult] = []
    for horizon in sorted(panel["horizon"].dropna().astype(int).unique()):
        hpanel = panel[panel["horizon"].eq(horizon)].copy()
        for flow in FLOWS:
            fpanel = hpanel[hpanel["flow"].eq(flow)].copy()
            results.append(
                    cse.run_ols_model(
                        fpanel,
                        outcome=PRIMARY_OUTCOME,
                        terms=[*[f"bucket_{bucket}" for bucket in BUCKET_ORDER], *BASE_CONTROL_TERMS],
                        fixed_effects=["reporter_code", "year"],
                        model_label=f"bucket_country_year_fe_h{horizon}",
                    sample=country_sample,
                    flow=flow,
                    dimension="product_partner_bucket",
                    metric="gini_bucket",
                    cluster_col="reporter_code",
                )
            )
    frame = cse.model_results_to_frame(results)
    frame["horizon"] = frame["model_label"].str.extract(r"_h(\d+)$")[0].astype(int)
    frame["model_label"] = "bucket_country_year_fe"
    return add_grouped_q_values(frame)


def run_paired_models(panel: pd.DataFrame, country_sample: str) -> pd.DataFrame:
    results: list[cse.ModelResult] = []
    work = panel.copy()
    for metric, product_col, partner_col in PAIRED_METRICS:
        work[f"product_exposure_{metric}"] = pd.to_numeric(work[product_col], errors="coerce")
        work[f"partner_exposure_{metric}"] = pd.to_numeric(work[partner_col], errors="coerce")
        work[f"product_x_partner_{metric}"] = work[f"product_exposure_{metric}"] * work[f"partner_exposure_{metric}"]
    for horizon in sorted(work["horizon"].dropna().astype(int).unique()):
        hpanel = work[work["horizon"].eq(horizon)].copy()
        for flow in FLOWS:
            fpanel = hpanel[hpanel["flow"].eq(flow)].copy()
            for metric, _product_col, _partner_col in PAIRED_METRICS:
                fit = fpanel.rename(
                    columns={
                        f"product_exposure_{metric}": "product_exposure",
                        f"partner_exposure_{metric}": "partner_exposure",
                        f"product_x_partner_{metric}": "product_x_partner",
                    }
                )
                results.append(
                    cse.run_ols_model(
                        fit,
                        outcome=PRIMARY_OUTCOME,
                        terms=["product_exposure", "partner_exposure", "product_x_partner", *BASE_CONTROL_TERMS],
                        fixed_effects=["reporter_code", "year"],
                        model_label=f"paired_product_partner_h{horizon}",
                        sample=country_sample,
                        flow=flow,
                        dimension="product_partner_pair",
                        metric=metric,
                        cluster_col="reporter_code",
                    )
                )
    frame = cse.model_results_to_frame(results)
    frame["horizon"] = frame["model_label"].str.extract(r"_h(\d+)$")[0].astype(int)
    frame["model_label"] = "paired_product_partner"
    return add_grouped_q_values(frame)


def run_robustness_models(panel: pd.DataFrame, country_sample: str) -> pd.DataFrame:
    specs = [
        ("two_way_country_year_cluster", PRIMARY_OUTCOME, BASE_CONTROL_TERMS, ["reporter_code", "year"], "year"),
        ("lagged_growth_control", PRIMARY_OUTCOME, [*BASE_CONTROL_TERMS, PRIOR_GROWTH_CONTROL], ["reporter_code", "year"], None),
        ("region_year_fe", PRIMARY_OUTCOME, BASE_CONTROL_TERMS, ["reporter_code", "region_year"], None),
        ("oil_excluded_growth", OIL_EX_OUTCOME, BASE_CONTROL_TERMS, ["reporter_code", "year"], None),
    ]
    results: list[cse.ModelResult] = []
    for horizon in sorted(panel["horizon"].dropna().astype(int).unique()):
        hpanel = panel[panel["horizon"].eq(horizon)].copy()
        for flow in FLOWS:
            fpanel = hpanel[hpanel["flow"].eq(flow)].copy()
            for dimension, metric, exposure_col, _label in EXPOSURE_SPECS:
                for label, outcome, controls, fixed_effects, two_way_col in specs:
                    results.append(
                        cse.run_ols_model(
                            fpanel,
                            outcome=outcome,
                            terms=[exposure_col, *controls],
                            fixed_effects=fixed_effects,
                            model_label=f"{label}_h{horizon}",
                            sample=country_sample,
                            flow=flow,
                            dimension=dimension,
                            metric=metric,
                            cluster_col="reporter_code",
                            two_way_cluster_col=two_way_col,
                        )
                    )
    frame = cse.model_results_to_frame(results)
    frame["horizon"] = frame["model_label"].str.extract(r"_h(\d+)$")[0].astype(int)
    frame["model_label"] = frame["model_label"].str.replace(r"_h\d+$", "", regex=True)
    return add_grouped_q_values(frame)


def model_frame_with_horizon(results: list[cse.ModelResult]) -> pd.DataFrame:
    frame = cse.model_results_to_frame(results)
    if frame.empty:
        return frame
    frame["horizon"] = frame["model_label"].str.extract(r"_h(\d+)$")[0]
    frame["horizon"] = pd.to_numeric(frame["horizon"], errors="coerce").astype("Int64")
    frame["model_label"] = frame["model_label"].str.replace(r"_h\d+$", "", regex=True)
    return add_grouped_q_values(frame)


def run_base_size_sensitivity_models(panel: pd.DataFrame, country_sample: str) -> pd.DataFrame:
    work = add_base_size_bins(panel)
    work = merge_primary_export_share_controls(work, country_sample)
    specs = [
        ("base_size_bin_fe", PRIMARY_OUTCOME, BASE_CONTROL_TERMS, ["reporter_code", "year", "base_size_bin"], None),
        ("drop_bottom_10pct_base", PRIMARY_OUTCOME, BASE_CONTROL_TERMS, ["reporter_code", "year"], "bottom_10pct_base_exports"),
        ("drop_bottom_25pct_base", PRIMARY_OUTCOME, BASE_CONTROL_TERMS, ["reporter_code", "year"], "bottom_25pct_base_exports"),
        ("alternative_outcome_dollar_change", DOLLAR_CHANGE_OUTCOME, BASE_CONTROL_TERMS, ["reporter_code", "year"], None),
        ("alternative_outcome_asinh_change", ASINH_CHANGE_OUTCOME, BASE_CONTROL_TERMS, ["reporter_code", "year"], None),
        ("placebo_prior_growth", PRIOR_GROWTH_CONTROL, BASE_CONTROL_TERMS, ["reporter_code", "year"], None),
        ("confounding_drop_top_oil_quartile", PRIMARY_OUTCOME, BASE_CONTROL_TERMS, ["reporter_code", "year"], "top_oil_quartile"),
        (
            "confounding_income_group_year_fe",
            PRIMARY_OUTCOME,
            BASE_CONTROL_TERMS,
            ["reporter_code", "income_group_year"],
            None,
        ),
        (
            "confounding_primary_share_broad_control",
            PRIMARY_OUTCOME,
            [*BASE_CONTROL_TERMS, "primary_export_share_broad"],
            ["reporter_code", "year"],
            None,
        ),
    ]
    results: list[cse.ModelResult] = []
    for horizon in sorted(work["horizon"].dropna().astype(int).unique()):
        hpanel = work[work["horizon"].eq(horizon)].copy()
        for flow in FLOWS:
            fpanel = hpanel[hpanel["flow"].eq(flow)].copy()
            oil_cutoff = pd.to_numeric(fpanel["oil_export_share"], errors="coerce").quantile(0.75)
            for label, outcome, controls, fixed_effects, filter_name in specs:
                fit = fpanel
                if filter_name == "bottom_10pct_base_exports":
                    fit = fpanel[~fpanel["bottom_10pct_base_exports"].fillna(False)].copy()
                elif filter_name == "bottom_25pct_base_exports":
                    fit = fpanel[~fpanel["bottom_25pct_base_exports"].fillna(False)].copy()
                elif filter_name == "top_oil_quartile" and math.isfinite(float(oil_cutoff)):
                    fit = fpanel[pd.to_numeric(fpanel["oil_export_share"], errors="coerce") <= oil_cutoff].copy()
                results.append(
                    cse.run_ols_model(
                        fit,
                        outcome=outcome,
                        terms=[*BUCKET_TERMS, *controls],
                        fixed_effects=fixed_effects,
                        model_label=f"{label}_h{horizon}",
                        sample=country_sample,
                        flow=flow,
                        dimension="product_partner_bucket",
                        metric="gini_bucket",
                        cluster_col="reporter_code",
                    )
                )
    frame = model_frame_with_horizon(results)
    if frame.empty:
        return frame
    family_map = {
        "base_size_bin_fe": "base_size",
        "drop_bottom_10pct_base": "base_size",
        "drop_bottom_25pct_base": "base_size",
        "alternative_outcome_dollar_change": "alternative_outcome",
        "alternative_outcome_asinh_change": "alternative_outcome",
        "placebo_prior_growth": "placebo",
        "confounding_drop_top_oil_quartile": "confounding",
        "confounding_income_group_year_fe": "confounding",
        "confounding_primary_share_broad_control": "confounding",
    }
    frame["test_family"] = frame["model_label"].map(family_map).fillna("mechanism")
    return frame


def run_mechanism_channel_models(panel: pd.DataFrame, country_sample: str) -> pd.DataFrame:
    work = add_base_size_bins(panel)
    results: list[cse.ModelResult] = []
    for horizon in sorted(work["horizon"].dropna().astype(int).unique()):
        hpanel = work[work["horizon"].eq(horizon)].copy()
        for flow in FLOWS:
            fpanel = hpanel[hpanel["flow"].eq(flow)].copy()
            for outcome, family in MECHANISM_OUTCOME_SPECS:
                if outcome not in fpanel.columns:
                    continue
                results.append(
                    cse.run_ols_model(
                        fpanel,
                        outcome=outcome,
                        terms=[*BUCKET_TERMS, *BASE_CONTROL_TERMS, *ACTIVE_COUNT_CONTROL_TERMS],
                        fixed_effects=["reporter_code", "year"],
                        model_label=f"mechanism_{family}_h{horizon}",
                        sample=country_sample,
                        flow=flow,
                        dimension="product_partner_bucket",
                        metric=family,
                        cluster_col="reporter_code",
                    )
                )
    frame = model_frame_with_horizon(results)
    if frame.empty:
        return frame
    frame["outcome_label"] = frame["outcome"].map(MECHANISM_OUTCOME_LABELS).fillna(frame["outcome"])
    frame["test_family"] = frame["metric"]
    return frame


def run_leave_one_country_out_influence(panel: pd.DataFrame, country_sample: str) -> pd.DataFrame:
    work = panel[panel["flow"].eq("Exports") & panel["horizon"].eq(5)].copy()
    rows: list[dict[str, Any]] = []
    if work.empty:
        return pd.DataFrame(
            columns=[
                "omitted_reporter_code",
                "omitted_country",
                "omitted_iso3",
                "term",
                "coefficient",
                "std_error",
                "p_value",
                "nobs",
                "clusters",
                "status",
            ]
        )
    for country_row in (
        work[["reporter_code", "country", "iso3"]]
        .drop_duplicates("reporter_code")
        .sort_values("reporter_code")
        .itertuples(index=False)
    ):
        fit = work[~work["reporter_code"].eq(int(country_row.reporter_code))].copy()
        result = cse.run_ols_model(
            fit,
            outcome=PRIMARY_OUTCOME,
            terms=[*BUCKET_TERMS, *BASE_CONTROL_TERMS],
            fixed_effects=["reporter_code", "year"],
            model_label="leave_one_country_out_h5",
            sample=country_sample,
            flow="Exports",
            dimension="product_partner_bucket",
            metric="gini_bucket",
            cluster_col="reporter_code",
        )
        frame = cse.model_results_to_frame([result])
        focus = frame[frame["term"].eq("bucket_high_product_low_partner")]
        if focus.empty:
            continue
        row = focus.iloc[0].to_dict()
        rows.append(
            {
                "omitted_reporter_code": int(country_row.reporter_code),
                "omitted_country": country_row.country,
                "omitted_iso3": country_row.iso3,
                "term": row.get("term"),
                "coefficient": row.get("coefficient"),
                "std_error": row.get("std_error"),
                "p_value": row.get("p_value"),
                "nobs": row.get("nobs"),
                "clusters": row.get("clusters"),
                "status": row.get("status"),
            }
        )
    return pd.DataFrame(rows)


def add_size_adjusted_growth(panel: pd.DataFrame) -> pd.DataFrame:
    """Residualize growth on base-size controls for bucket-level display.

    The adjusted outcome is residual plus the flow-horizon mean of the raw
    outcome, so it remains in annualized log-growth units while removing the
    fitted component from initial export size and macro size controls.
    """
    out = panel.copy()
    out[SIZE_ADJUSTED_OUTCOME] = np.nan
    out["size_adjustment_complete"] = False
    required = [PRIMARY_OUTCOME, *SIZE_ADJUSTMENT_CONTROL_TERMS, "year"]
    for (_flow, _horizon), group in out.groupby(["flow", "horizon"], dropna=False):
        present_required = [col for col in required if col in out.columns]
        if len(present_required) != len(required):
            continue
        work = group.replace([np.inf, -np.inf], np.nan).dropna(subset=required).copy()
        if len(work) < len(SIZE_ADJUSTMENT_CONTROL_TERMS) + 4:
            continue
        y = pd.to_numeric(work[PRIMARY_OUTCOME], errors="coerce").to_numpy(dtype=float)
        x_df, _dropped = cse.design_matrix(work, list(SIZE_ADJUSTMENT_CONTROL_TERMS), ["year"])
        if x_df.shape[0] <= x_df.shape[1]:
            continue
        beta, *_ = np.linalg.lstsq(x_df.to_numpy(dtype=float), y, rcond=None)
        residual = y - x_df.to_numpy(dtype=float) @ beta
        out.loc[work.index, SIZE_ADJUSTED_OUTCOME] = residual + float(np.mean(y))
        out.loc[work.index, "size_adjustment_complete"] = True
    return out


def bucket_summary(panel: pd.DataFrame) -> pd.DataFrame:
    if SIZE_ADJUSTED_OUTCOME not in panel.columns:
        panel = add_size_adjusted_growth(panel)
    summary = (
        panel.groupby(["flow", "horizon", "concentration_bucket"], as_index=False)
        .agg(
            observations=(PRIMARY_OUTCOME, "count"),
            countries=("reporter_code", "nunique"),
            mean_annualized_log_growth=(PRIMARY_OUTCOME, "mean"),
            median_annualized_log_growth=(PRIMARY_OUTCOME, "median"),
            size_adjusted_observations=(SIZE_ADJUSTED_OUTCOME, "count"),
            mean_size_adjusted_annualized_log_growth=(SIZE_ADJUSTED_OUTCOME, "mean"),
            median_size_adjusted_annualized_log_growth=(SIZE_ADJUSTED_OUTCOME, "median"),
            mean_real_export_growth_pct=("real_export_growth_pct", "mean"),
            median_initial_exports_constant_2015_usd=("base_exports_constant_2015_usd", "median"),
        )
        .sort_values(["flow", "horizon", "concentration_bucket"])
    )
    return summary


def add_base_size_bins(panel: pd.DataFrame, bins: int = BASE_SIZE_BIN_COUNT) -> pd.DataFrame:
    out = panel.copy()
    out["base_size_percentile"] = np.nan
    out["base_size_bin"] = pd.Series(pd.NA, index=out.index, dtype="object")
    out["bottom_10pct_base_exports"] = False
    out["bottom_25pct_base_exports"] = False
    for (_flow, _year, _horizon), group in out.groupby(["flow", "year", "horizon"], dropna=False):
        values = pd.to_numeric(group["log_initial_exports_constant_2015_usd"], errors="coerce")
        valid = values.replace([np.inf, -np.inf], np.nan).notna()
        if not bool(valid.any()):
            continue
        pct_rank = values.loc[valid].rank(method="average", pct=True)
        bin_number = np.ceil(pct_rank * bins).clip(1, bins).astype(int)
        out.loc[pct_rank.index, "base_size_percentile"] = pct_rank
        out.loc[pct_rank.index, "base_size_bin"] = [f"Q{int(value)}" for value in bin_number]
        out.loc[pct_rank.index, "bottom_10pct_base_exports"] = pct_rank <= 0.10
        out.loc[pct_rank.index, "bottom_25pct_base_exports"] = pct_rank <= 0.25
    return out


def base_size_bin_summary(panel: pd.DataFrame) -> pd.DataFrame:
    work = add_base_size_bins(panel)
    summary = (
        work.dropna(subset=["base_size_bin"])
        .groupby(["flow", "horizon", "base_size_bin", "concentration_bucket"], as_index=False)
        .agg(
            observations=(PRIMARY_OUTCOME, "count"),
            countries=("reporter_code", "nunique"),
            mean_annualized_log_growth=(PRIMARY_OUTCOME, "mean"),
            mean_size_adjusted_annualized_log_growth=(SIZE_ADJUSTED_OUTCOME, "mean"),
            mean_annualized_real_export_change_constant_2015_usd=(DOLLAR_CHANGE_OUTCOME, "mean"),
            mean_annualized_asinh_real_export_change=(ASINH_CHANGE_OUTCOME, "mean"),
            median_initial_exports_constant_2015_usd=("base_exports_constant_2015_usd", "median"),
            mean_base_size_percentile=("base_size_percentile", "mean"),
        )
        .sort_values(["flow", "horizon", "base_size_bin", "concentration_bucket"])
    )
    return summary


def merge_primary_export_share_controls(panel: pd.DataFrame, country_sample: str) -> pd.DataFrame:
    out = panel.copy()
    for column in ["primary_export_share_strict", "primary_export_share_broad"]:
        out[column] = np.nan
    path = sample_processed_path(COUNTRY_SIZE_PANEL, country_sample)
    if not path.exists():
        return out
    primary = pd.read_parquet(
        path,
        columns=["reporter_code", "year", "primary_export_share_strict", "primary_export_share_broad"],
    )
    primary["reporter_code"] = pd.to_numeric(primary["reporter_code"], errors="coerce")
    primary["year"] = pd.to_numeric(primary["year"], errors="coerce")
    primary = primary.dropna(subset=["reporter_code", "year"]).copy()
    primary["reporter_code"] = primary["reporter_code"].astype(int)
    primary["year"] = primary["year"].astype(int)
    for column in ["primary_export_share_strict", "primary_export_share_broad"]:
        primary[column] = pd.to_numeric(primary[column], errors="coerce")
    primary = primary.drop_duplicates(["reporter_code", "year"], keep="last")
    out = out.drop(columns=["primary_export_share_strict", "primary_export_share_broad"], errors="ignore").merge(
        primary,
        on=["reporter_code", "year"],
        how="left",
        validate="many_to_one",
    )
    return out


def validate_extensive_margin_manifest(country_sample: str) -> dict[str, Any]:
    manifest_path = sample_results_dir(country_sample) / EX12_EXTENSIVE_MANIFEST
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing Exercise 12 extensive-margin manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text())
    validation = manifest.get("validation") or {}
    blockers: list[str] = []
    if validation.get("status") != "ok":
        blockers.append(f"status={validation.get('status')!r}")
    if validation.get("blockers"):
        blockers.append(f"blockers={validation.get('blockers')!r}")
    if "999999" not in set((validation.get("product_excluded_hs6_codes") or [])):
        blockers.append("HS6 999999 exclusion is not recorded")
    if int(validation.get("source_hs6_999999_rows_after_filters") or 0) != 0:
        blockers.append("HS6 999999 rows remain after product-dependent filters")
    if int(validation.get("source_partner_code_0_rows_after_filters") or 0) != 0:
        blockers.append("World partner rows remain after product-partner filters")
    if blockers:
        raise RuntimeError("Exercise 12 extensive-margin validation failed: " + "; ".join(blockers))
    return manifest


def pivot_share_table(
    data: pd.DataFrame,
    key_cols: list[str],
    category_col: str,
    category_map: dict[str, str],
    value_cols: list[str],
) -> pd.DataFrame:
    rows = data[data[category_col].astype(str).isin(category_map)].copy()
    if rows.empty:
        return pd.DataFrame(columns=key_cols)
    rows[category_col] = rows[category_col].astype(str).map(category_map)
    pieces = []
    for value_col in value_cols:
        pivot = rows.pivot_table(
            index=key_cols,
            columns=category_col,
            values=value_col,
            aggfunc="first",
        )
        pivot.columns = [f"{category}_{value_col}" for category in pivot.columns]
        pieces.append(pivot)
    out = pd.concat(pieces, axis=1).reset_index()
    validate_unique_keys(out, key_cols, f"{category_col} pivot")
    return out


def load_extensive_margin_channels(country_sample: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    manifest = validate_extensive_margin_manifest(country_sample)
    base = sample_results_dir(country_sample) / EX12_EXTENSIVE_DIR
    country_year_path = base / EX12_EXTENSIVE_COUNTRY_YEAR
    product_path = base / EX12_PRODUCT_ENTRY_ROBUSTNESS
    for path in [country_year_path, product_path]:
        if not path.exists():
            raise FileNotFoundError(f"Missing Exercise 12 mechanism input: {path}")

    key_cols = ["reporter_code", "base_year", "future_year", "horizon"]
    country_year = pd.read_csv(country_year_path)
    country_year = country_year[country_year["identity_mode"].eq(PREFERRED_MECHANISM_IDENTITY_MODE)].copy()
    for column in key_cols:
        country_year[column] = pd.to_numeric(country_year[column], errors="coerce").astype(int)
    validate_unique_keys(country_year, [*key_cols, "category"], "Exercise 12 country-year channels")
    channel_values = pivot_share_table(
        country_year,
        key_cols,
        "category",
        EXTENSIVE_CHANNELS,
        ["gross_positive_share", "net_growth_share", "product_count", "partner_count", "cell_count"],
    )

    product_entry = pd.read_csv(product_path)
    product_entry = product_entry[product_entry["identity_mode"].eq(PREFERRED_MECHANISM_IDENTITY_MODE)].copy()
    for column in key_cols:
        product_entry[column] = pd.to_numeric(product_entry[column], errors="coerce").astype(int)
    validate_unique_keys(product_entry, [*key_cols, "product_definition"], "Exercise 12 product-entry robustness")
    product_values = pivot_share_table(
        product_entry,
        key_cols,
        "product_definition",
        PRODUCT_ENTRY_CHANNELS,
        ["gross_positive_share", "net_growth_share", "product_count"],
    )
    out = channel_values.merge(product_values, on=key_cols, how="outer", validate="one_to_one")
    validate_unique_keys(out, key_cols, "Exercise 12 mechanism channel panel")
    return out, manifest


def merge_mechanism_channels(panel: pd.DataFrame, channels: pd.DataFrame) -> pd.DataFrame:
    key_cols = ["reporter_code", "base_year", "future_year", "horizon"]
    out = panel.copy()
    out["base_year"] = pd.to_numeric(out["year"], errors="coerce").astype(int)
    if channels.empty:
        return out
    merged = out.merge(
        channels,
        left_on=["reporter_code", "base_year", "future_year", "horizon"],
        right_on=key_cols,
        how="left",
        validate="many_to_one",
        suffixes=("", "_mechanism"),
    )
    return merged.drop(columns=["base_year_mechanism"], errors="ignore")


def country_examples(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (flow, horizon), group in panel.dropna(subset=[PRIMARY_OUTCOME]).groupby(["flow", "horizon"]):
        for label, frame in [("fastest_growth", group.nlargest(5, PRIMARY_OUTCOME)), ("slowest_growth", group.nsmallest(5, PRIMARY_OUTCOME))]:
            for row in frame.itertuples(index=False):
                rows.append(
                    {
                        "flow": flow,
                        "horizon": int(horizon),
                        "example_type": label,
                        "country": row.country,
                        "iso3": row.iso3,
                        "year": int(row.year),
                        "future_year": int(row.future_year),
                        "concentration_bucket": row.concentration_bucket,
                        PRIMARY_OUTCOME: getattr(row, PRIMARY_OUTCOME),
                        "base_exports": row.base_exports,
                        "future_exports": row.future_exports,
                        "base_exports_constant_2015_usd": row.base_exports_constant_2015_usd,
                        "future_exports_constant_2015_usd": row.future_exports_constant_2015_usd,
                        "product_gini": row.product_gini,
                        "partner_gini": row.partner_gini,
                        "product_partner_cell_gini": row.product_partner_cell_gini,
                    }
                )
    return pd.DataFrame(rows)


def missing_controls(panel: pd.DataFrame) -> pd.DataFrame:
    required = [PRIMARY_OUTCOME, *BASE_CONTROL_TERMS]
    cols = [
        "country",
        "iso3",
        "reporter_code",
        "year",
        "future_year",
        "horizon",
        "flow",
        *required,
    ]
    out = panel[panel[required].replace([np.inf, -np.inf], np.nan).isna().any(axis=1)][cols].copy()
    return out.sort_values(["flow", "reporter_code", "year", "horizon"])


def gap_between_buckets(
    frame: pd.DataFrame,
    value_col: str,
    *,
    flow: str = "Exports",
    horizon: int = 5,
    high_bucket: str = "high_product_low_partner",
    reference_bucket: str = "low_product_low_partner",
) -> float:
    work = frame[frame["flow"].eq(flow) & frame["horizon"].eq(horizon)].copy()
    if work.empty or value_col not in work.columns:
        return np.nan
    means = work.groupby("concentration_bucket")[value_col].mean()
    if high_bucket not in means or reference_bucket not in means:
        return np.nan
    return float(means[high_bucket] - means[reference_bucket])


def within_size_bin_gap(base_size_summary: pd.DataFrame, value_col: str, flow: str = "Exports", horizon: int = 5) -> float:
    work = base_size_summary[base_size_summary["flow"].eq(flow) & base_size_summary["horizon"].eq(horizon)].copy()
    if work.empty or value_col not in work.columns:
        return np.nan
    gaps = []
    for _bin, group in work.groupby("base_size_bin", dropna=False):
        means = group.set_index("concentration_bucket")[value_col]
        if "high_product_low_partner" in means and "low_product_low_partner" in means:
            gaps.append(float(means["high_product_low_partner"] - means["low_product_low_partner"]))
    return float(np.mean(gaps)) if gaps else np.nan


def model_focus_value(
    models: pd.DataFrame,
    model_label: str,
    term: str = "bucket_high_product_low_partner",
    *,
    flow: str = "Exports",
    horizon: int = 5,
    outcome: str | None = None,
) -> dict[str, Any]:
    if models.empty:
        return {}
    work = models[
        models["model_label"].astype(str).eq(model_label)
        & models["flow"].astype(str).eq(flow)
        & pd.to_numeric(models["horizon"], errors="coerce").eq(horizon)
        & models["term"].astype(str).eq(term)
    ].copy()
    if outcome is not None and "outcome" in work.columns:
        work = work[work["outcome"].astype(str).eq(outcome)].copy()
    if work.empty:
        return {}
    return work.iloc[0].to_dict()


def build_mechanism_summary(
    panel: pd.DataFrame,
    bucket: pd.DataFrame,
    base_size: pd.DataFrame,
    base_size_models: pd.DataFrame,
    mechanism_models: pd.DataFrame,
    influence: pd.DataFrame,
) -> pd.DataFrame:
    raw_gap = gap_between_buckets(bucket.rename(columns={"mean_annualized_log_growth": PRIMARY_OUTCOME}), PRIMARY_OUTCOME)
    adjusted_gap = gap_between_buckets(
        bucket.rename(columns={"mean_size_adjusted_annualized_log_growth": SIZE_ADJUSTED_OUTCOME}),
        SIZE_ADJUSTED_OUTCOME,
    )
    within_gap = within_size_bin_gap(base_size, "mean_annualized_log_growth")
    bottom10 = model_focus_value(base_size_models, "drop_bottom_10pct_base")
    bottom25 = model_focus_value(base_size_models, "drop_bottom_25pct_base")
    primary_control = model_focus_value(base_size_models, "confounding_primary_share_broad_control")
    prior_placebo = model_focus_value(base_size_models, "placebo_prior_growth")
    new_partner_gap = gap_between_buckets(panel, "new_partner_existing_product_gross_positive_share")
    new_cell_gap = gap_between_buckets(panel, "new_cell_existing_product_partner_gross_positive_share")
    product_entry_gap = gap_between_buckets(panel, "net_new_product_gross_positive_share")
    partner_count_gap = gap_between_buckets(panel, "annualized_log_partner_active_count_change")
    product_count_gap = gap_between_buckets(panel, "annualized_log_product_active_count_change")
    new_partner_model = model_focus_value(
        mechanism_models,
        "mechanism_destination_diversification",
        outcome="new_partner_existing_product_gross_positive_share",
    )
    product_model = model_focus_value(
        mechanism_models,
        "mechanism_product_discovery",
        outcome="net_new_product_gross_positive_share",
    )
    influence_ok = influence[pd.to_numeric(influence.get("coefficient", pd.Series(dtype=float)), errors="coerce").notna()]
    influence_min = float(influence_ok["coefficient"].min()) if not influence_ok.empty else np.nan
    influence_max = float(influence_ok["coefficient"].max()) if not influence_ok.empty else np.nan

    rows = [
        {
            "test_id": "raw_bucket_gap",
            "test_label": "Raw 5-year export bucket gap",
            "estimate": raw_gap,
            "unit": "pct",
            "p_value": np.nan,
            "bh_q_value": np.nan,
            "nobs": int(panel[panel["flow"].eq("Exports") & panel["horizon"].eq(5)][PRIMARY_OUTCOME].count()),
            "interpretation": "High-product/low-partner minus low-product/low-partner before size controls.",
        },
        {
            "test_id": "size_adjusted_bucket_gap",
            "test_label": "Size-adjusted bucket gap",
            "estimate": adjusted_gap,
            "unit": "pct",
            "p_value": np.nan,
            "bh_q_value": np.nan,
            "nobs": int(panel[panel["flow"].eq("Exports") & panel["horizon"].eq(5)][SIZE_ADJUSTED_OUTCOME].count()),
            "interpretation": "Same comparison after residualizing on initial exports and macro size controls.",
        },
        {
            "test_id": "within_size_bin_gap",
            "test_label": "Within-size-bin gap",
            "estimate": within_gap,
            "unit": "pct",
            "p_value": np.nan,
            "bh_q_value": np.nan,
            "nobs": int(base_size[base_size["flow"].eq("Exports") & base_size["horizon"].eq(5)]["observations"].sum()),
            "interpretation": "Equal average of bucket gaps inside base-export-size quintiles.",
        },
        {
            "test_id": "drop_bottom_10pct_coef",
            "test_label": "Bottom 10% excluded",
            "estimate": bottom10.get("coefficient", np.nan),
            "unit": "pct",
            "p_value": bottom10.get("p_value", np.nan),
            "bh_q_value": bottom10.get("bh_q_value", np.nan),
            "nobs": bottom10.get("nobs", np.nan),
            "interpretation": "Country/year FE bucket coefficient after excluding the lowest base-export decile.",
        },
        {
            "test_id": "drop_bottom_25pct_coef",
            "test_label": "Bottom 25% excluded",
            "estimate": bottom25.get("coefficient", np.nan),
            "unit": "pct",
            "p_value": bottom25.get("p_value", np.nan),
            "bh_q_value": bottom25.get("bh_q_value", np.nan),
            "nobs": bottom25.get("nobs", np.nan),
            "interpretation": "Country/year FE bucket coefficient after excluding the lowest base-export quartile.",
        },
        {
            "test_id": "new_partner_share_gap",
            "test_label": "New-partner channel gap",
            "estimate": new_partner_gap,
            "unit": "pct",
            "p_value": new_partner_model.get("p_value", np.nan),
            "bh_q_value": new_partner_model.get("bh_q_value", np.nan),
            "nobs": new_partner_model.get("nobs", np.nan),
            "interpretation": "Gross-positive growth share from new partners for existing products.",
        },
        {
            "test_id": "new_cell_share_gap",
            "test_label": "New product-partner cell gap",
            "estimate": new_cell_gap,
            "unit": "pct",
            "p_value": np.nan,
            "bh_q_value": np.nan,
            "nobs": int(panel[panel["flow"].eq("Exports") & panel["horizon"].eq(5)]["new_cell_existing_product_partner_gross_positive_share"].count())
            if "new_cell_existing_product_partner_gross_positive_share" in panel.columns
            else np.nan,
            "interpretation": "Gross-positive growth share from new cells where product and partner both already existed.",
        },
        {
            "test_id": "net_new_product_share_gap",
            "test_label": "Net-new product channel gap",
            "estimate": product_entry_gap,
            "unit": "pct",
            "p_value": product_model.get("p_value", np.nan),
            "bh_q_value": product_model.get("bh_q_value", np.nan),
            "nobs": product_model.get("nobs", np.nan),
            "interpretation": "Gross-positive growth share from net-new products.",
        },
        {
            "test_id": "partner_count_change_gap",
            "test_label": "Partner-count growth gap",
            "estimate": partner_count_gap,
            "unit": "pct",
            "p_value": np.nan,
            "bh_q_value": np.nan,
            "nobs": int(panel[panel["flow"].eq("Exports") & panel["horizon"].eq(5)]["annualized_log_partner_active_count_change"].count()),
            "interpretation": "Annualized log change in active partners.",
        },
        {
            "test_id": "product_count_change_gap",
            "test_label": "Product-count growth gap",
            "estimate": product_count_gap,
            "unit": "pct",
            "p_value": np.nan,
            "bh_q_value": np.nan,
            "nobs": int(panel[panel["flow"].eq("Exports") & panel["horizon"].eq(5)]["annualized_log_product_active_count_change"].count()),
            "interpretation": "Annualized log change in active products.",
        },
        {
            "test_id": "prior_growth_placebo_coef",
            "test_label": "Prior-growth placebo",
            "estimate": prior_placebo.get("coefficient", np.nan),
            "unit": "pct",
            "p_value": prior_placebo.get("p_value", np.nan),
            "bh_q_value": prior_placebo.get("bh_q_value", np.nan),
            "nobs": prior_placebo.get("nobs", np.nan),
            "interpretation": "Whether the bucket also predicts already-realized pre-period growth.",
        },
        {
            "test_id": "primary_share_control_coef",
            "test_label": "Primary-share control",
            "estimate": primary_control.get("coefficient", np.nan),
            "unit": "pct",
            "p_value": primary_control.get("p_value", np.nan),
            "bh_q_value": primary_control.get("bh_q_value", np.nan),
            "nobs": primary_control.get("nobs", np.nan),
            "interpretation": "Bucket coefficient after controlling for broad primary-product export share.",
        },
        {
            "test_id": "leave_one_country_out_range",
            "test_label": "Leave-one-country-out range",
            "estimate": influence_max - influence_min if math.isfinite(influence_min) and math.isfinite(influence_max) else np.nan,
            "unit": "pct",
            "p_value": np.nan,
            "bh_q_value": np.nan,
            "nobs": len(influence_ok),
            "interpretation": f"Range of high-product/low-partner coefficients when omitting one reporter at a time: {influence_min:.4f} to {influence_max:.4f}.",
        },
    ]
    return pd.DataFrame(rows)


def mechanism_diagnostics(
    panel: pd.DataFrame,
    channels: pd.DataFrame,
    manifest: dict[str, Any],
    base_size_models: pd.DataFrame,
    mechanism_models: pd.DataFrame,
    influence: pd.DataFrame,
) -> pd.DataFrame:
    validation = manifest.get("validation") or {}
    rows: list[dict[str, Any]] = [
        {"diagnostic": "mechanism_panel_rows", "value": len(panel)},
        {"diagnostic": "mechanism_panel_countries", "value": panel["reporter_code"].nunique()},
        {
            "diagnostic": "duplicate_mechanism_panel_keys",
            "value": int(panel.duplicated(["reporter_code", "year", "future_year", "horizon", "flow"]).sum()),
        },
        {"diagnostic": "exercise_12_channel_rows", "value": len(channels)},
        {"diagnostic": "exercise_12_validation_status", "value": validation.get("status", "")},
        {
            "diagnostic": "exercise_12_product_hs6_999999_rule",
            "value": "excluded before product-dependent aggregation; validation reports 0 rows after filters",
        },
        {
            "diagnostic": "exercise_12_partner_code_0_rule",
            "value": "World partner excluded before product-partner channel construction",
        },
        {
            "diagnostic": "primary_share_control_source",
            "value": rel(sample_processed_path(COUNTRY_SIZE_PANEL, "rd2_countries")),
        },
        {
            "diagnostic": "base_size_models_ok",
            "value": int(base_size_models["status"].eq("ok").sum()) if not base_size_models.empty else 0,
        },
        {
            "diagnostic": "mechanism_models_ok",
            "value": int(mechanism_models["status"].eq("ok").sum()) if not mechanism_models.empty else 0,
        },
        {
            "diagnostic": "leave_one_country_out_rows",
            "value": len(influence),
        },
    ]
    for horizon in sorted(panel["horizon"].dropna().astype(int).unique()):
        hpanel = panel[panel["horizon"].eq(horizon)]
        channel_complete = (
            hpanel["net_new_product_gross_positive_share"].notna().sum()
            if "net_new_product_gross_positive_share" in hpanel.columns
            else 0
        )
        rows.append({"diagnostic": f"horizon_{horizon}_mechanism_rows", "value": len(hpanel)})
        rows.append({"diagnostic": f"horizon_{horizon}_exercise_12_channel_matches", "value": int(channel_complete)})
    return pd.DataFrame(rows)


def sample_diagnostics(
    panel: pd.DataFrame,
    concentration: pd.DataFrame,
    export_totals: pd.DataFrame,
    controls: pd.DataFrame,
    missing: pd.DataFrame,
    args: argparse.Namespace,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = [
        {"diagnostic": "country_sample", "value": args.country_sample},
        {"diagnostic": "start_year", "value": args.start_year},
        {"diagnostic": "end_year", "value": args.end_year},
        {"diagnostic": "horizons", "value": ",".join(str(h) for h in args.horizons)},
        {"diagnostic": "concentration_rows", "value": len(concentration)},
        {"diagnostic": "panel_rows", "value": len(panel)},
        {"diagnostic": "countries", "value": panel["reporter_code"].nunique()},
        {"diagnostic": "base_years", "value": panel["year"].nunique()},
        {"diagnostic": "export_total_rows", "value": len(export_totals)},
        {"diagnostic": "world_bank_control_rows", "value": len(controls)},
        {"diagnostic": "missing_required_rows", "value": len(missing)},
        {"diagnostic": "duplicate_panel_keys", "value": int(panel.duplicated(["reporter_code", "year", "flow", "horizon"]).sum())},
        {"diagnostic": "product_hs6_999999_rule", "value": "excluded upstream before product and product-partner aggregation"},
        {"diagnostic": "partner_hs6_999999_rule", "value": "included in partner totals by repo convention"},
        {"diagnostic": "outcome_source", "value": "Comtrade merchandise export totals deflated with the US GDP deflator to constant 2015 USD"},
        {"diagnostic": "control_source", "value": "World Bank constant-2015 GDP, population, and constant-2015 GNI per capita"},
        {
            "diagnostic": "size_adjusted_bucket_controls",
            "value": ",".join(SIZE_ADJUSTMENT_CONTROL_TERMS),
        },
        {
            "diagnostic": "size_adjusted_bucket_method",
            "value": "within flow-horizon OLS residual plus raw flow-horizon mean, with base-year fixed effects",
        },
        {
            "diagnostic": "base_size_bin_method",
            "value": "base real export percentiles and quintiles computed within exposure flow, base year, and horizon",
        },
        {
            "diagnostic": "alternative_outcomes",
            "value": f"{DOLLAR_CHANGE_OUTCOME},{ASINH_CHANGE_OUTCOME}",
        },
        {
            "diagnostic": "mechanism_channel_source",
            "value": "Exercise 12 hs6_harmonized_family country-window decomposition and product-entry robustness",
        },
        {"diagnostic": "interpretation", "value": "descriptive predictive association, not causal identification"},
    ]
    for flow in FLOWS:
        flow_panel = panel[panel["flow"].eq(flow)]
        rows.append({"diagnostic": f"{flow.lower()}_rows", "value": len(flow_panel)})
        rows.append({"diagnostic": f"{flow.lower()}_complete_primary_rows", "value": int(flow_panel[[PRIMARY_OUTCOME, *BASE_CONTROL_TERMS]].notna().all(axis=1).sum())})
    for horizon in sorted(panel["horizon"].dropna().astype(int).unique()):
        hpanel = panel[panel["horizon"].eq(horizon)]
        rows.append({"diagnostic": f"horizon_{horizon}_rows", "value": len(hpanel)})
        rows.append({"diagnostic": f"horizon_{horizon}_complete_primary_rows", "value": int(hpanel[[PRIMARY_OUTCOME, *BASE_CONTROL_TERMS]].notna().all(axis=1).sum())})
        if SIZE_ADJUSTED_OUTCOME in hpanel.columns:
            rows.append({"diagnostic": f"horizon_{horizon}_size_adjusted_rows", "value": int(hpanel[SIZE_ADJUSTED_OUTCOME].notna().sum())})
    return pd.DataFrame(rows)


def write_manifest(paths: dict[str, Path], args: argparse.Namespace) -> dict[str, Any]:
    manifest = {
        "generated_at_utc": now_utc(),
        "country_sample": args.country_sample,
        "start_year": args.start_year,
        "end_year": args.end_year,
        "horizons": list(args.horizons),
        "inputs": {
            "concentration_panel": rel(sample_processed_path("concentration_all_years.parquet", args.country_sample)),
            "export_totals_panel": rel(sample_processed_path("exercise_02_export_concentration_panel.parquet", args.country_sample)),
        },
        "outputs": {name: rel(path) for name, path in paths.items()},
        "real_value_conventions": {
            "exports": "Comtrade merchandise export values deflated with the US GDP deflator to constant 2015 USD",
            "gdp": "World Bank NY.GDP.MKTP.KD, constant 2015 USD",
            "gni_per_capita": "World Bank NY.GNP.PCAP.KD, constant 2015 USD",
            "nominal_columns": "retained only as diagnostic/source columns, not used in the preferred regressions",
        },
        "size_adjusted_bucket_summary": {
            "outcome": SIZE_ADJUSTED_OUTCOME,
            "controls": list(SIZE_ADJUSTMENT_CONTROL_TERMS),
            "fixed_effects": ["year"],
            "method": "estimated separately by exposure flow and horizon; adjusted outcome is residual plus raw flow-horizon mean",
        },
        "mechanism_tests": {
            "base_size_bins": "base real export percentiles and quintiles computed within exposure flow, base year, and horizon",
            "bottom_base_exclusions": ["bottom_10pct_base_exports", "bottom_25pct_base_exports"],
            "alternative_outcomes": [DOLLAR_CHANGE_OUTCOME, ASINH_CHANGE_OUTCOME],
            "extensive_margin_source": rel(sample_results_dir(args.country_sample) / EX12_EXTENSIVE_DIR / EX12_EXTENSIVE_COUNTRY_YEAR),
            "preferred_extensive_margin_identity": PREFERRED_MECHANISM_IDENTITY_MODE,
            "primary_share_control_source": rel(sample_processed_path(COUNTRY_SIZE_PANEL, args.country_sample)),
            "active_count_outcomes": [
                "annualized_log_product_active_count_change",
                "annualized_log_partner_active_count_change",
            ],
        },
        "trade_data_rules": {
            "product_and_product_partner_hs6_999999": "excluded upstream before aggregation",
            "partner_hs6_999999": "included by partner-total convention",
            "partner_code_0": "excluded upstream from concentration construction",
            "exercise_12_product_channels_hs6_999999": "validated as excluded before product-dependent mechanism aggregation",
        },
    }
    manifest_path = sample_results_dir(args.country_sample) / "run_manifest_future_growth_concentration.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def make_figures(summary: pd.DataFrame, continuous: pd.DataFrame, figure_dir: Path) -> dict[str, Path]:
    ensure_dirs(figure_dir)
    sns.set_theme(style="whitegrid")
    paths: dict[str, Path] = {}

    summary_path = figure_dir / "bucket_summary_growth.png"
    fig, ax = plt.subplots(figsize=(11, 6))
    plot_data = summary[summary["horizon"].eq(5)].copy()
    if plot_data.empty:
        ax.text(0.5, 0.5, "No 5-year bucket summary", ha="center", va="center")
        ax.axis("off")
    else:
        adjusted_plot = "mean_size_adjusted_annualized_log_growth" in plot_data.columns
        growth_column = "mean_size_adjusted_annualized_log_growth" if adjusted_plot else "mean_annualized_log_growth"
        sns.barplot(
            data=plot_data,
            x="concentration_bucket",
            y=growth_column,
            hue="flow",
            ax=ax,
        )
        ax.set_xlabel("Base-year concentration bucket")
        ax.set_ylabel(
            "Size-adjusted mean annualized log real export growth"
            if adjusted_plot
            else "Mean annualized log real export growth"
        )
        ax.tick_params(axis="x", rotation=20)
    fig.tight_layout()
    fig.savefig(summary_path, dpi=180)
    plt.close(fig)
    paths["bucket_summary_growth"] = summary_path

    coef_path = figure_dir / "continuous_coefficients.png"
    fig, ax = plt.subplots(figsize=(11, 7))
    coef_data = continuous[
        continuous["model_label"].eq("continuous_country_year_fe")
        & continuous["horizon"].eq(5)
        & continuous["status"].eq("ok")
    ].copy()
    exposure_cols = {spec[2] for spec in EXPOSURE_SPECS}
    coef_data = coef_data[coef_data["term"].isin(exposure_cols)].copy()
    if coef_data.empty:
        ax.text(0.5, 0.5, "No 5-year continuous coefficients", ha="center", va="center")
        ax.axis("off")
    else:
        coef_data["measure"] = coef_data["flow"] + " " + coef_data["dimension"].str.replace("_", "-") + " " + coef_data["metric"].str.replace("_", " ")
        coef_data = coef_data.sort_values(["flow", "dimension", "metric"])
        ax.errorbar(
            coef_data["coefficient"],
            np.arange(len(coef_data)),
            xerr=1.96 * coef_data["std_error"],
            fmt="o",
            color="#0f766e",
            ecolor="#94a3b8",
            capsize=3,
        )
        ax.axvline(0, color="#475569", linewidth=1)
        ax.set_yticks(np.arange(len(coef_data)), coef_data["measure"])
        ax.set_xlabel("Coefficient on concentration exposure")
        ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(coef_path, dpi=180)
    plt.close(fig)
    paths["continuous_coefficients"] = coef_path
    return paths


def write_memo(
    summary: pd.DataFrame,
    mechanism_summary: pd.DataFrame,
    base_size_models: pd.DataFrame,
    mechanism_models: pd.DataFrame,
    influence: pd.DataFrame,
    continuous: pd.DataFrame,
    paired: pd.DataFrame,
    diagnostics: pd.DataFrame,
    manifest: dict[str, Any],
    memo_path: Path,
) -> None:
    primary = continuous[
        continuous["model_label"].eq("continuous_country_year_fe")
        & continuous["term"].isin({spec[2] for spec in EXPOSURE_SPECS})
        & continuous["status"].eq("ok")
    ].copy()
    strongest = primary.assign(abs_coef=primary["coefficient"].abs()).sort_values("abs_coef", ascending=False).head(12)
    paired_focus = paired[paired["term"].isin(["product_exposure", "partner_exposure", "product_x_partner"])].head(18)
    lines = [
        "# Future Export Growth From Trade Concentration",
        "",
        f"Generated: {now_utc()}",
        "",
        "This is descriptive predictive panel evidence, not causal identification. The exercise asks whether base-year import or export concentration predicts future real merchandise export growth for the rd2 country sample.",
        "",
        "## Specification",
        "",
        "```text",
        "g_c,t,h = beta * concentration_c,f,d,t + controls_c,t + country FE + year FE + error_c,t,h",
        "```",
        "",
        "- Outcome: annualized log real merchandise export growth from Comtrade totals deflated to constant 2015 USD with the US GDP deflator.",
        "- Exposures: base-year import or export concentration across products, partners, and product-partner cells.",
        "- Monetary controls: log initial real merchandise exports, log real GDP, log population, and log real GNI per capita.",
        "- Size-adjusted bucket columns residualize annualized growth on log initial real exports, oil share, real GDP, population, real GNI per capita, and base-year fixed effects within each exposure-flow/horizon, then add back the raw flow-horizon mean.",
        "- Product and product-partner measures exclude HS6 999999 upstream; partner measures include it by partner-total convention.",
        "- Standard errors are clustered by reporter country unless a robustness row says otherwise.",
        "",
        "## Descriptive Bucket Summary",
        "",
        summary.to_markdown(index=False),
        "",
        "## What Survives After Size Controls",
        "",
        mechanism_summary.to_markdown(index=False),
        "",
        "## Base-Size and Confounding Sensitivity",
        "",
        base_size_models[
            [
                "model_label",
                "flow",
                "horizon",
                "outcome",
                "term",
                "coefficient",
                "std_error",
                "p_value",
                "bh_q_value",
                "nobs",
                "clusters",
                "status",
            ]
        ].to_markdown(index=False),
        "",
        "## Extensive-Margin Mechanism Models",
        "",
        mechanism_models[
            [
                "model_label",
                "flow",
                "horizon",
                "outcome_label",
                "term",
                "coefficient",
                "std_error",
                "p_value",
                "bh_q_value",
                "nobs",
                "clusters",
                "status",
            ]
        ].to_markdown(index=False)
        if not mechanism_models.empty
        else "No mechanism models were estimated.",
        "",
        "## Leave-One-Country-Out Influence",
        "",
        influence.to_markdown(index=False) if not influence.empty else "No influence rows were estimated.",
        "",
        "## Strongest Continuous Coefficients",
        "",
        strongest[
            [
                "flow",
                "dimension",
                "metric",
                "horizon",
                "term",
                "coefficient",
                "std_error",
                "p_value",
                "bh_q_value",
                "nobs",
                "clusters",
                "status",
            ]
        ].to_markdown(index=False),
        "",
        "## Paired Product/Partner Rows",
        "",
        paired_focus[
            [
                "flow",
                "metric",
                "horizon",
                "term",
                "coefficient",
                "std_error",
                "p_value",
                "bh_q_value",
                "nobs",
                "clusters",
                "status",
            ]
        ].to_markdown(index=False),
        "",
        "## Diagnostics",
        "",
        diagnostics.to_markdown(index=False),
        "",
        "## Literature Context",
        "",
        "This page sits between the export-diversification literature and the repo's concentration facts. Hummels and Klenow (2005) motivate extensive and intensive margins; Cadot, Carrere, and Strauss-Kahn study export diversification over development; Brenton and Newfarmer and Amurgo-Pacheco and Pierola separate product and market diversification; Besedes and Prusa emphasize relationship survival; Hausmann, Hwang, and Rodrik connect export composition to growth; import-input work such as Benguria motivates import concentration as a possible input-supply exposure.",
        "",
        "## Files",
        "",
        *[f"- {name}: `{path}`" for name, path in sorted(manifest["outputs"].items())],
        "",
        "## Interpretation Limit",
        "",
        "These regressions support or weaken predictive relationships. They should not be described as evidence that concentration causes faster or slower export growth without a separate identification design.",
        "",
    ]
    memo_path.write_text("\n".join(lines))


def output_paths(country_sample: str) -> dict[str, Path]:
    results_base = sample_results_dir(country_sample)
    table_dir = results_base / "future_growth_concentration_tables"
    figure_dir = results_base / "future_growth_concentration_figures"
    processed_panel = sample_processed_path("future_growth_concentration_panel.parquet", country_sample)
    return {
        "table_dir": table_dir,
        "figure_dir": figure_dir,
        "processed_panel": processed_panel,
        "panel_csv": table_dir / "future_growth_concentration_panel.csv",
        "bucket_summary": table_dir / "bucket_summary.csv",
        "country_examples": table_dir / "country_examples.csv",
        "bucket_models": table_dir / "bucket_models.csv",
        "continuous_models": table_dir / "continuous_models.csv",
        "paired_models": table_dir / "paired_models.csv",
        "robustness_models": table_dir / "robustness_models.csv",
        "base_size_bin_summary": table_dir / "base_size_bin_summary.csv",
        "base_size_sensitivity_models": table_dir / "base_size_sensitivity_models.csv",
        "mechanism_channel_panel": table_dir / "mechanism_channel_panel.csv",
        "mechanism_channel_models": table_dir / "mechanism_channel_models.csv",
        "mechanism_summary": table_dir / "mechanism_summary.csv",
        "mechanism_diagnostics": table_dir / "mechanism_diagnostics.csv",
        "leave_one_country_out_influence": table_dir / "leave_one_country_out_influence.csv",
        "sample_diagnostics": table_dir / "sample_diagnostics.csv",
        "missing_controls": table_dir / "missing_controls.csv",
        "memo": results_base / "future_growth_concentration.md",
    }


def run_pipeline(args: argparse.Namespace) -> dict[str, Path]:
    paths = output_paths(args.country_sample)
    ensure_dirs(paths["table_dir"], paths["figure_dir"], paths["processed_panel"].parent)

    concentration = load_concentration_panel(args.country_sample, args.start_year, args.end_year)
    export_totals = load_export_totals(args.country_sample, args.start_year, args.end_year)
    iso3s = sorted(concentration["iso3"].dropna().astype(str).str.upper().unique())
    control_keys = concentration[["iso3", "year"]].drop_duplicates()
    controls = load_or_fetch_world_bank_controls(
        iso3s,
        control_keys,
        args.start_year,
        args.end_year,
        sample_processed_path(CONTROL_CACHE, args.country_sample),
        refresh=args.refresh_controls,
    )
    deflator = load_or_fetch_us_deflator(
        args.start_year,
        args.end_year,
        sample_processed_path(US_DEFLATOR_CACHE, args.country_sample),
        refresh=args.refresh_controls,
    )
    panel = construct_future_growth_panel(concentration, export_totals, controls, deflator, args.horizons)
    panel = add_size_adjusted_growth(panel)
    panel = add_base_size_bins(panel)
    panel = merge_primary_export_share_controls(panel, args.country_sample)
    channels, ex12_manifest = load_extensive_margin_channels(args.country_sample)
    mechanism_panel = merge_mechanism_channels(panel, channels)
    missing = missing_controls(panel)
    summary = bucket_summary(panel)
    base_size_summary = base_size_bin_summary(panel)
    examples = country_examples(panel)
    bucket_models = run_bucket_models(panel, args.country_sample)
    continuous = run_continuous_models(panel, args.country_sample)
    paired = run_paired_models(panel, args.country_sample)
    robustness = run_robustness_models(panel, args.country_sample)
    base_size_models = run_base_size_sensitivity_models(panel, args.country_sample)
    mechanism_models = run_mechanism_channel_models(mechanism_panel, args.country_sample)
    influence = run_leave_one_country_out_influence(panel, args.country_sample)
    mechanism_summary = build_mechanism_summary(
        mechanism_panel,
        summary,
        base_size_summary,
        base_size_models,
        mechanism_models,
        influence,
    )
    mechanism_diag = mechanism_diagnostics(
        mechanism_panel,
        channels,
        ex12_manifest,
        base_size_models,
        mechanism_models,
        influence,
    )
    diagnostics = sample_diagnostics(panel, concentration, export_totals, controls, missing, args)
    make_figures(summary, continuous, paths["figure_dir"])

    panel.to_parquet(paths["processed_panel"], index=False)
    panel.to_csv(paths["panel_csv"], index=False)
    summary.to_csv(paths["bucket_summary"], index=False)
    base_size_summary.to_csv(paths["base_size_bin_summary"], index=False)
    examples.to_csv(paths["country_examples"], index=False)
    bucket_models.to_csv(paths["bucket_models"], index=False)
    continuous.to_csv(paths["continuous_models"], index=False)
    paired.to_csv(paths["paired_models"], index=False)
    robustness.to_csv(paths["robustness_models"], index=False)
    base_size_models.to_csv(paths["base_size_sensitivity_models"], index=False)
    mechanism_panel.to_csv(paths["mechanism_channel_panel"], index=False)
    mechanism_models.to_csv(paths["mechanism_channel_models"], index=False)
    mechanism_summary.to_csv(paths["mechanism_summary"], index=False)
    mechanism_diag.to_csv(paths["mechanism_diagnostics"], index=False)
    influence.to_csv(paths["leave_one_country_out_influence"], index=False)
    diagnostics.to_csv(paths["sample_diagnostics"], index=False)
    missing.to_csv(paths["missing_controls"], index=False)

    public_paths = {k: v for k, v in paths.items() if k not in {"table_dir", "figure_dir"}}
    public_paths["bucket_summary_growth_figure"] = paths["figure_dir"] / "bucket_summary_growth.png"
    public_paths["continuous_coefficients_figure"] = paths["figure_dir"] / "continuous_coefficients.png"
    manifest = write_manifest(public_paths, args)
    write_memo(
        summary,
        mechanism_summary,
        base_size_models,
        mechanism_models,
        influence,
        continuous,
        paired,
        diagnostics,
        manifest,
        paths["memo"],
    )
    print(f"Wrote {rel(paths['memo'])}")
    return public_paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country-sample", choices=COUNTRY_SAMPLE_CHOICES, default="rd2_countries")
    parser.add_argument("--start-year", type=int, default=1988)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--horizons", type=int, nargs="+", default=list(HORIZONS))
    parser.add_argument("--refresh-controls", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.horizons = sorted(dict.fromkeys(int(h) for h in args.horizons if int(h) > 0))
    if not args.horizons:
        raise SystemExit("At least one positive horizon is required.")
    run_pipeline(args)


if __name__ == "__main__":
    main()
