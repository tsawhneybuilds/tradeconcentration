#!/usr/bin/env python3
"""Country-size effect tests for trade concentration levels.

The exercise is descriptive: it asks whether larger countries have different
concentration levels within the same year, not whether country size causally
changes concentration.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import seaborn as sns
from linearmodels.iv import IVGMM
from scipy.stats import t as student_t

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from trade_concentration_pipeline import sample_processed_path, sample_results_dir  # noqa: E402


COUNTRY_SAMPLE_CHOICES = ("rd2_countries", "prof_p_33")
FLOWS = ("Imports", "Exports")
OUTCOME_SPECS = (
    ("product", "gini", "product_gini", "Product Gini"),
    ("partner", "gini", "partner_gini", "Partner Gini"),
    ("product", "top_1pct_share", "product_top_1pct_share", "Product top 1% share"),
    ("product", "top_5pct_share", "product_top_5pct_share", "Product top 5% share"),
    ("partner", "top_1pct_share", "partner_top_1pct_share", "Partner top 1% share"),
    ("partner", "top_5pct_share", "partner_top_5pct_share", "Partner top 5% share"),
)
PRIMARY_TERM = "log_population"
CONTROL_TERM = "log_gdp_per_capita"
GMM_MODEL_LABEL = "gmm_lag_iv_year_fe"
GMM_ENDOG_TERMS = (PRIMARY_TERM, CONTROL_TERM)
GMM_INSTRUMENT_TERMS = (
    "lag2_log_population",
    "lag3_log_population",
    "lag2_log_gdp_per_capita",
    "lag3_log_gdp_per_capita",
)
MIN_CONTROL_COVERAGE = 0.80
WORLD_BANK_URL = "https://api.worldbank.org/v2/country/{countries}/indicator/{indicator}"
WORLD_BANK_RAW = ROOT / "data" / "raw" / "world_bank_gdp"
RAW_CONTROL_FILES = {
    "gdp_current_usd": [
        WORLD_BANK_RAW / "gdp_current_usd.csv",
        WORLD_BANK_RAW / "ny_gdp_mktp_cd_1988_2024.csv",
    ],
    "population": [
        WORLD_BANK_RAW / "sp_pop_totl_1988_2024.csv",
    ],
}
PRIMARY_SHARE_CONTROL_CHOICES = ("both", "strict", "broad", "none")
PRIMARY_SHARE_SPECS = (
    ("strict", "primary_export_share_strict", "primary_share_strict_year_fe"),
    ("broad", "primary_export_share_broad", "primary_share_broad_year_fe"),
)
PRIMARY_BEC_MAPPING_PATH = ROOT / "data" / "processed" / "exercise_03_bec5_mapping_approved.csv"
PRIMARY_AGGREGATE_DIRNAME = "exercise_02_12_file_aggregates"
MIN_PRIMARY_MAPPING_COVERAGE = 0.95
US_POPULATION_COUNTERFACTUAL_TARGETS = (
    ("p75", "75th percentile", 0.75),
    ("p50", "50th percentile", 0.50),
    ("p25", "25th percentile", 0.25),
    ("p10", "10th percentile", 0.10),
    ("smallest", "Smallest country", 0.00),
)


@dataclass(frozen=True)
class ModelResult:
    model_label: str
    sample: str
    flow: str
    dimension: str
    metric: str
    outcome: str
    terms: list[str]
    beta: np.ndarray
    se: np.ndarray
    nobs: int
    clusters: int
    r_squared: float
    status: str
    dropped_rows: int
    candidate_rows: int
    dropped_regressors: str
    se_method: str
    p_reference_df: float
    fixed_effects: str
    cluster_col: str


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


def read_csv_if_exists(path: Path, required: Iterable[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=list(required))
    data = pd.read_csv(path)
    missing = [col for col in required if col not in data.columns]
    if missing:
        return pd.DataFrame(columns=list(required))
    return data[list(required)].copy()


def fetch_world_bank_indicator(
    iso3s: list[str],
    indicator: str,
    value_name: str,
    start_year: int,
    end_year: int,
) -> pd.DataFrame:
    def fetch_batch(country_batch: list[str]) -> pd.DataFrame:
        rows: list[dict] = []
        countries = ";".join(country_batch)
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
            last_exc: Exception | None = None
            for attempt in range(3):
                try:
                    response = requests.get(url, params=params, timeout=60)
                    response.raise_for_status()
                    payload = response.json()
                    break
                except Exception as exc:
                    last_exc = exc
                    time.sleep(0.5 * (attempt + 1))
            else:
                raise RuntimeError(
                    f"World Bank request failed for {indicator}, countries={countries}, page={page}: {last_exc}"
                )
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

    frames: list[pd.DataFrame] = []
    countries_all = sorted(set(iso3s))
    for start in range(0, len(countries_all), 20):
        batch = countries_all[start : start + 20]
        frame = fetch_batch(batch)
        returned = set(frame["iso3"].astype(str).str.upper().unique().tolist()) if not frame.empty else set()
        missing = [iso3 for iso3 in batch if iso3 not in returned]
        if frame.empty and len(batch) > 1:
            missing = batch
        if not frame.empty:
            frames.append(frame)
        for iso3 in missing:
            single = fetch_batch([iso3])
            if not single.empty:
                frames.append(single)

    if not frames:
        return pd.DataFrame(columns=["iso3", "year", value_name])
    out = pd.concat(frames, ignore_index=True)
    out = (
        out.dropna(subset=["iso3", "year"])
        .sort_values(["iso3", "year", value_name], na_position="first")
        .drop_duplicates(["iso3", "year"], keep="last")
        .reset_index(drop=True)
    )
    return out[["iso3", "year", value_name]]


def seed_controls_from_existing_files(iso3s: list[str], start_year: int, end_year: int) -> pd.DataFrame:
    requested = set(iso3s)
    panel = pd.DataFrame(
        [(iso3, year) for iso3 in sorted(requested) for year in range(start_year, end_year + 1)],
        columns=["iso3", "year"],
    )
    for value_name, paths in RAW_CONTROL_FILES.items():
        frames = []
        for path in paths:
            frame = read_csv_if_exists(path, ["iso3", "year", value_name])
            if frame.empty:
                continue
            frame["iso3"] = frame["iso3"].astype(str).str.upper()
            frame["year"] = pd.to_numeric(frame["year"], errors="coerce")
            frame[value_name] = pd.to_numeric(frame[value_name], errors="coerce")
            frame = frame[frame["iso3"].isin(requested) & frame["year"].between(start_year, end_year)]
            frames.append(frame)
        if frames:
            combined = pd.concat(frames, ignore_index=True)
            combined = (
                combined.dropna(subset=["iso3", "year"])
                .sort_values(["iso3", "year", value_name], na_position="last")
                .drop_duplicates(["iso3", "year"], keep="last")
            )
            panel = panel.merge(combined, on=["iso3", "year"], how="left")
    return panel


def complete_control_share(controls: pd.DataFrame, requested_keys: pd.DataFrame) -> float:
    required = requested_keys.merge(controls, on=["iso3", "year"], how="left")
    complete = required[["gdp_current_usd", "population"]].notna().all(axis=1)
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
    requested_keys["year"] = requested_keys["year"].astype(int)

    controls = pd.DataFrame(columns=["iso3", "year", "gdp_current_usd", "population"])
    if cache_path.exists() and not refresh:
        controls = read_csv_if_exists(cache_path, ["iso3", "year", "gdp_current_usd", "population"])
    if controls.empty or complete_control_share(controls, requested_keys) < MIN_CONTROL_COVERAGE:
        seeded = seed_controls_from_existing_files(iso3s, start_year, end_year)
        frames = [seeded]
        try:
            frames.append(fetch_world_bank_indicator(iso3s, "NY.GDP.MKTP.CD", "gdp_current_usd", start_year, end_year))
            frames.append(fetch_world_bank_indicator(iso3s, "SP.POP.TOTL", "population", start_year, end_year))
        except Exception as exc:
            print(f"World Bank refresh warning: {exc}", file=sys.stderr)
        controls = seeded[["iso3", "year"]].copy()
        for value_name in ["gdp_current_usd", "population"]:
            value_frames = [f[["iso3", "year", value_name]] for f in frames if value_name in f.columns]
            combined = pd.concat(value_frames, ignore_index=True) if value_frames else pd.DataFrame(columns=["iso3", "year", value_name])
            if not combined.empty:
                combined["iso3"] = combined["iso3"].astype(str).str.upper()
                combined["year"] = pd.to_numeric(combined["year"], errors="coerce")
                combined[value_name] = pd.to_numeric(combined[value_name], errors="coerce")
                combined = (
                    combined.dropna(subset=["iso3", "year"])
                    .sort_values(["iso3", "year", value_name], na_position="first")
                    .drop_duplicates(["iso3", "year"], keep="last")
                )
                controls = controls.drop(columns=[value_name], errors="ignore").merge(combined, on=["iso3", "year"], how="left")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        controls.to_csv(cache_path, index=False)

    controls["iso3"] = controls["iso3"].astype(str).str.upper()
    controls["year"] = pd.to_numeric(controls["year"], errors="coerce").astype("Int64")
    for col in ["gdp_current_usd", "population"]:
        controls[col] = pd.to_numeric(controls[col], errors="coerce")
    controls = controls.dropna(subset=["iso3", "year"]).copy()
    controls["year"] = controls["year"].astype(int)
    controls = controls.drop_duplicates(["iso3", "year"], keep="last")

    coverage = complete_control_share(controls, requested_keys)
    if coverage < MIN_CONTROL_COVERAGE:
        missing = requested_keys.merge(controls, on=["iso3", "year"], how="left")
        missing = missing[missing[["gdp_current_usd", "population"]].notna().all(axis=1).eq(False)]
        sample = missing.groupby("iso3").size().sort_values(ascending=False).head(10).to_dict()
        raise RuntimeError(
            "World Bank controls are too incomplete for the country-size test: "
            f"{coverage:.1%} complete country-years, below {MIN_CONTROL_COVERAGE:.0%}. "
            f"Most missing countries: {sample}. Try --refresh-controls."
        )
    return controls


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
        *[spec[2] for spec in OUTCOME_SPECS],
    }
    missing = sorted(needed - set(panel.columns))
    if missing:
        raise RuntimeError(f"Concentration panel is missing required columns: {missing}")
    panel = panel[panel["variant"].eq("baseline") & panel["year"].between(start_year, end_year)].copy()
    if panel.empty:
        raise RuntimeError("No baseline concentration rows remain after the requested year filter.")
    key = ["iso3", "reporter_code", "year", "flow", "variant"]
    dupes = int(panel.duplicated(key).sum())
    if dupes:
        raise RuntimeError(f"Concentration panel has {dupes:,} duplicate iso3-reporter-year-flow-variant rows.")
    for _dimension, _metric, col, _label in OUTCOME_SPECS:
        values = pd.to_numeric(panel[col], errors="coerce")
        bad = values.notna() & ((values < 0) | (values > 1))
        if bool(bad.any()):
            raise RuntimeError(f"Outcome {col} has {int(bad.sum()):,} finite out-of-range values.")
    return panel


def construct_population_size_variables(panel: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    for col in ["gdp_current_usd", "population"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out["log_population"] = np.where(out["population"] > 0, np.log(out["population"]), np.nan)
    out["log_gdp_current_usd"] = np.where(out["gdp_current_usd"] > 0, np.log(out["gdp_current_usd"]), np.nan)
    out["log_gdp_per_capita"] = out["log_gdp_current_usd"] - out["log_population"]

    country_year = (
        out[["iso3", "year", "log_population"]]
        .dropna(subset=["log_population"])
        .drop_duplicates(["iso3", "year"])
        .sort_values(["iso3", "year"])
    )
    baseline = country_year.groupby("iso3", as_index=False).first()[["iso3", "log_population"]].rename(
        columns={"log_population": "baseline_log_population"}
    )
    average = country_year.groupby("iso3", as_index=False)["log_population"].mean().rename(
        columns={"log_population": "average_log_population"}
    )
    out = out.merge(baseline, on="iso3", how="left").merge(average, on="iso3", how="left")
    return out


def construct_gmm_lag_instruments(panel: pd.DataFrame, lags: Iterable[int] = (2, 3)) -> pd.DataFrame:
    out = panel.copy()
    needed = ["iso3", "year", PRIMARY_TERM, CONTROL_TERM]
    missing = [col for col in needed if col not in out.columns]
    if missing:
        raise RuntimeError(f"Cannot construct GMM lag instruments; missing columns: {missing}")

    country_year = out[needed].copy()
    country_year["iso3"] = country_year["iso3"].astype(str).str.upper()
    country_year["year"] = pd.to_numeric(country_year["year"], errors="coerce")
    for col in [PRIMARY_TERM, CONTROL_TERM]:
        country_year[col] = pd.to_numeric(country_year[col], errors="coerce")
    country_year = country_year.dropna(subset=["iso3", "year"]).drop_duplicates()
    if int(country_year.duplicated(["iso3", "year"]).sum()):
        conflicts = country_year[country_year.duplicated(["iso3", "year"], keep=False)].sort_values(["iso3", "year"])
        examples = conflicts[["iso3", "year", PRIMARY_TERM, CONTROL_TERM]].head(10).to_dict("records")
        raise RuntimeError(f"Conflicting country-year controls prevent GMM lag construction. Examples: {examples}")

    country_year["year"] = country_year["year"].astype(int)
    out["iso3"] = out["iso3"].astype(str).str.upper()
    out["year"] = pd.to_numeric(out["year"], errors="coerce").astype(int)
    for lag in lags:
        lagged = country_year[["iso3", "year", PRIMARY_TERM, CONTROL_TERM]].copy()
        lagged["year"] = lagged["year"] + int(lag)
        lagged = lagged.rename(
            columns={
                PRIMARY_TERM: f"lag{int(lag)}_{PRIMARY_TERM}",
                CONTROL_TERM: f"lag{int(lag)}_{CONTROL_TERM}",
            }
        )
        out = out.merge(lagged, on=["iso3", "year"], how="left", validate="many_to_one")
    return out


def normalize_hs6_code(value: object) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    match = re.search(r"(\d{1,6})", str(value))
    return match.group(1).zfill(6) if match else ""


def normalize_classification_code(value: object) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    text = str(value).strip().upper()
    match = re.search(r"H[0-6]", text)
    return match.group(0) if match else text


def hs4_between(hs4: str, lower: str, upper: str) -> bool:
    return len(hs4) == 4 and lower <= hs4 <= upper


def description_has_any(description: object, words: Iterable[str]) -> bool:
    text = str(description or "").lower()
    return any(word in text for word in words)


STRICT_PRIMARY_HS2 = {f"{code:02d}" for code in range(1, 11)} | {"12", "13", "14"}
STRICT_RAW_SUGAR_HS6 = {"170111", "170112", "170113", "170114"}
STRICT_COCOA_HS6 = {"180100", "180200"}
STRICT_RAW_TOBACCO_HS6 = {"240110", "240120", "240130"}
STRICT_PRECIOUS_HS6 = {"710610", "710691", "710811", "710812"}
STRICT_PLATINUM_UNWROUGHT_HS6 = {"711011", "711021", "711031", "711041"}


def classify_primary_hs6(cmd_code: object, description: object = "") -> dict[str, object]:
    """Classify an HS6 row as strict/broad primary for the robustness control."""
    code = normalize_hs6_code(cmd_code)
    if not code or code == "999999":
        return {
            "cmd_code": code,
            "primary_strict": False,
            "primary_broad": False,
            "primary_strict_rule": "excluded_999999_or_invalid",
            "primary_broad_rule": "excluded_999999_or_invalid",
        }

    hs2 = code[:2]
    hs4 = code[:4]
    strict_rule = ""
    if hs2 in STRICT_PRIMARY_HS2:
        strict_rule = "strict_hs01_10_12_14_raw_agriculture"
    elif code in STRICT_RAW_SUGAR_HS6:
        strict_rule = "strict_raw_sugar_hs170111_170114"
    elif code in STRICT_COCOA_HS6:
        strict_rule = "strict_cocoa_beans_or_waste_hs1801_1802"
    elif code in STRICT_RAW_TOBACCO_HS6:
        strict_rule = "strict_raw_tobacco_hs240110_240130"
    elif hs4 == "4001":
        strict_rule = "strict_natural_rubber_hs4001"
    elif hs4_between(hs4, "4101", "4103") or hs4 == "4301":
        strict_rule = "strict_raw_hides_skins_furs"
    elif hs4_between(hs4, "5001", "5003") or hs4_between(hs4, "5101", "5105") or hs4_between(hs4, "5201", "5203") or hs4_between(hs4, "5301", "5305"):
        strict_rule = "strict_raw_textile_fibers"
    elif hs2 in {"25", "26"}:
        strict_rule = "strict_minerals_ores_hs25_26"
    elif hs4 in {"2701", "2702", "2703", "2709", "2711"}:
        strict_rule = "strict_raw_fuels_coal_crude_gas"
    elif hs4 in {"4401", "4403", "4404", "4501"}:
        strict_rule = "strict_raw_forestry_cork"
    elif hs4_between(hs4, "7101", "7105") or code in STRICT_PRECIOUS_HS6:
        strict_rule = "strict_raw_precious_stones_metals"
    elif hs4 == "7110" and (description_has_any(description, ["unwrought", "powder"]) or code in STRICT_PLATINUM_UNWROUGHT_HS6):
        strict_rule = "strict_unwrought_powder_platinum_group"

    broad_rule = strict_rule
    if not broad_rule:
        if hs2 in {"11", "15", "23"}:
            broad_rule = "broad_first_stage_food_inputs_hs11_15_23"
        elif hs4 == "1701":
            broad_rule = "broad_sugar_hs1701"
        elif hs4_between(hs4, "1803", "1805"):
            broad_rule = "broad_cocoa_first_stage_hs1803_1805"
        elif hs2 == "27":
            broad_rule = "broad_all_fuels_refinery_hs27"
        elif hs4 == "4402" or hs4_between(hs4, "4405", "4409") or hs4_between(hs4, "4701", "4707"):
            broad_rule = "broad_processed_wood_pulp_waste"
        elif hs4_between(hs4, "7201", "7205") or hs4_between(hs4, "7401", "7404") or hs4_between(hs4, "7501", "7503") or hs4_between(hs4, "7601", "7602") or hs4_between(hs4, "7801", "7802") or hs4_between(hs4, "7901", "7902") or hs4_between(hs4, "8001", "8002"):
            broad_rule = "broad_first_stage_metals_scrap"
        elif hs4_between(hs4, "8101", "8113") and description_has_any(description, ["unwrought", "powder", "waste", "scrap"]):
            broad_rule = "broad_unwrought_powder_waste_other_base_metals"
        elif hs4_between(hs4, "7106", "7112"):
            broad_rule = "broad_precious_metal_semimanufactures_waste"

    return {
        "cmd_code": code,
        "primary_strict": bool(strict_rule),
        "primary_broad": bool(broad_rule),
        "primary_strict_rule": strict_rule or "not_primary_strict",
        "primary_broad_rule": broad_rule or "not_primary_broad",
    }


def selected_primary_share_specs(selection: str) -> list[tuple[str, str, str]]:
    if selection == "none":
        return []
    if selection == "strict":
        return [PRIMARY_SHARE_SPECS[0]]
    if selection == "broad":
        return [PRIMARY_SHARE_SPECS[1]]
    return list(PRIMARY_SHARE_SPECS)


def build_primary_product_mapping(mapping_path: Path = PRIMARY_BEC_MAPPING_PATH) -> pd.DataFrame:
    if not mapping_path.exists():
        raise FileNotFoundError(f"Missing HS6/BEC mapping used to audit primary-product classification: {mapping_path}")
    usecols = {
        "classification_code",
        "cmd_code",
        "hs_desc_official",
        "hs_desc_if_available",
        "bec5_label",
        "bec5_end_use",
        "exercise_03_bin",
        "mapping_status",
    }
    mapping = pd.read_csv(mapping_path, dtype=str, usecols=lambda col: col in usecols)
    mapping["classification_code"] = mapping["classification_code"].map(normalize_classification_code)
    mapping["cmd_code"] = mapping["cmd_code"].map(normalize_hs6_code)
    mapping = mapping.dropna(subset=["classification_code", "cmd_code"])
    mapping = mapping[mapping["cmd_code"].ne("") & mapping["cmd_code"].ne("999999")].copy()
    mapping["hs_desc_official"] = mapping.get("hs_desc_official", pd.Series("", index=mapping.index)).fillna("")
    mapping["hs_desc_if_available"] = mapping.get("hs_desc_if_available", pd.Series("", index=mapping.index)).fillna("")
    mapping["primary_description"] = np.where(
        mapping["hs_desc_official"].astype(str).str.len().gt(0),
        mapping["hs_desc_official"],
        mapping["hs_desc_if_available"],
    )
    classified = mapping.apply(
        lambda row: classify_primary_hs6(row["cmd_code"], row["primary_description"]),
        axis=1,
        result_type="expand",
    )
    mapping["bec5_primary_flag"] = mapping.get("bec5_label", pd.Series("", index=mapping.index)).fillna("").str.contains(
        "Primary", case=False, na=False
    )
    for col in ["primary_strict", "primary_broad", "primary_strict_rule", "primary_broad_rule"]:
        mapping[col] = classified[col]
    keep = [
        "classification_code",
        "cmd_code",
        "hs_desc_official",
        "bec5_label",
        "bec5_end_use",
        "exercise_03_bin",
        "mapping_status",
        "bec5_primary_flag",
        "primary_strict",
        "primary_broad",
        "primary_strict_rule",
        "primary_broad_rule",
    ]
    out = mapping[keep].drop_duplicates(["classification_code", "cmd_code"], keep="last").reset_index(drop=True)
    out["primary_mapping_source"] = "bec5_audit_mapping"
    return out


def collect_observed_primary_product_codes(aggregate_dir: Path, start_year: int, end_year: int) -> pd.DataFrame:
    if not aggregate_dir.exists():
        raise FileNotFoundError(f"Missing product-export aggregate directory for primary-share control: {aggregate_dir}")
    files = sorted(aggregate_dir.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No parquet aggregate files found for primary-share control in {aggregate_dir}")

    chunks: list[pd.DataFrame] = []
    read_cols = ["year", "flow", "classification_code", "dimension", "cmd_code"]
    for path in files:
        frame = pd.read_parquet(path, columns=read_cols)
        if frame.empty:
            continue
        frame = frame[
            frame["flow"].eq("Exports")
            & frame["dimension"].eq("product")
            & pd.to_numeric(frame["year"], errors="coerce").between(start_year, end_year)
        ].copy()
        if frame.empty:
            continue
        frame["classification_code"] = frame["classification_code"].map(normalize_classification_code)
        frame["cmd_code"] = frame["cmd_code"].map(normalize_hs6_code)
        frame = frame[frame["classification_code"].ne("") & frame["cmd_code"].ne("") & frame["cmd_code"].ne("999999")]
        if not frame.empty:
            chunks.append(frame[["classification_code", "cmd_code"]].drop_duplicates())

    if not chunks:
        return pd.DataFrame(columns=["classification_code", "cmd_code"])
    return pd.concat(chunks, ignore_index=True).drop_duplicates(["classification_code", "cmd_code"]).reset_index(drop=True)


def augment_primary_mapping_with_observed_codes(
    primary_mapping: pd.DataFrame,
    aggregate_dir: Path,
    start_year: int,
    end_year: int,
) -> pd.DataFrame:
    observed = collect_observed_primary_product_codes(aggregate_dir, start_year, end_year)
    if observed.empty:
        return primary_mapping.copy()

    mapping_keys = primary_mapping[["classification_code", "cmd_code"]].copy()
    mapping_keys["classification_code"] = mapping_keys["classification_code"].map(normalize_classification_code)
    mapping_keys["cmd_code"] = mapping_keys["cmd_code"].map(normalize_hs6_code)
    missing = observed.merge(mapping_keys.drop_duplicates(), on=["classification_code", "cmd_code"], how="left", indicator=True)
    missing = missing[missing["_merge"].eq("left_only")][["classification_code", "cmd_code"]].copy()
    if missing.empty:
        return primary_mapping.copy()

    classified = missing["cmd_code"].map(lambda code: classify_primary_hs6(code, ""))
    fallback = pd.DataFrame(list(classified))
    missing = pd.concat([missing.reset_index(drop=True), fallback.drop(columns=["cmd_code"]).reset_index(drop=True)], axis=1)
    for col in ["hs_desc_official", "bec5_label", "bec5_end_use", "exercise_03_bin"]:
        missing[col] = ""
    missing["mapping_status"] = "code_rule_fallback_not_in_bec_audit"
    missing["bec5_primary_flag"] = False
    missing["primary_mapping_source"] = "observed_aggregate_code_rule_fallback"

    combined = pd.concat([primary_mapping, missing[list(primary_mapping.columns)]], ignore_index=True)
    return combined.drop_duplicates(["classification_code", "cmd_code"], keep="last").reset_index(drop=True)


def primary_export_share_columns() -> list[str]:
    return [
        "reporter_code",
        "year",
        "total_product_exports",
        "strict_primary_exports",
        "broad_primary_exports",
        "primary_export_share_strict",
        "primary_export_share_broad",
        "primary_mapping_matched_export_value",
        "primary_mapping_missing_export_value",
        "primary_mapping_coverage_share",
    ]


def empty_primary_share_outputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    diagnostics = pd.DataFrame(columns=["row_type", "diagnostic", "reporter_code", "year", "classification_code", "cmd_code", "value", "detail"])
    mapping = pd.DataFrame(
        columns=[
            "classification_code",
            "cmd_code",
            "hs_desc_official",
            "bec5_label",
            "bec5_end_use",
            "exercise_03_bin",
            "mapping_status",
            "bec5_primary_flag",
            "primary_strict",
            "primary_broad",
            "primary_strict_rule",
            "primary_broad_rule",
            "primary_mapping_source",
        ]
    )
    return pd.DataFrame(columns=primary_export_share_columns()), diagnostics, mapping


def construct_primary_export_shares(
    aggregate_dir: Path,
    primary_mapping: pd.DataFrame,
    start_year: int,
    end_year: int,
    min_mapping_coverage: float = MIN_PRIMARY_MAPPING_COVERAGE,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not aggregate_dir.exists():
        raise FileNotFoundError(f"Missing product-export aggregate directory for primary-share control: {aggregate_dir}")
    files = sorted(aggregate_dir.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No parquet aggregate files found for primary-share control in {aggregate_dir}")

    mapping_cols = ["classification_code", "cmd_code", "primary_strict", "primary_broad"]
    mapping = primary_mapping[mapping_cols].copy()
    mapping["classification_code"] = mapping["classification_code"].map(normalize_classification_code)
    mapping["cmd_code"] = mapping["cmd_code"].map(normalize_hs6_code)
    mapping = mapping.drop_duplicates(["classification_code", "cmd_code"], keep="last")

    partials: list[pd.DataFrame] = []
    missing_details: list[pd.DataFrame] = []
    read_cols = ["reporter_code", "year", "flow", "classification_code", "dimension", "cmd_code", "trade_value"]
    for path in files:
        try:
            frame = pd.read_parquet(path, columns=read_cols)
        except Exception as exc:
            raise RuntimeError(f"Could not read primary-share aggregate file {path}: {exc}") from exc
        if frame.empty:
            continue
        frame = frame[
            frame["flow"].eq("Exports")
            & frame["dimension"].eq("product")
            & pd.to_numeric(frame["year"], errors="coerce").between(start_year, end_year)
        ].copy()
        if frame.empty:
            continue
        frame["reporter_code"] = pd.to_numeric(frame["reporter_code"], errors="coerce")
        frame["year"] = pd.to_numeric(frame["year"], errors="coerce")
        frame["trade_value"] = pd.to_numeric(frame["trade_value"], errors="coerce")
        frame["classification_code"] = frame["classification_code"].map(normalize_classification_code)
        frame["cmd_code"] = frame["cmd_code"].map(normalize_hs6_code)
        frame = frame.dropna(subset=["reporter_code", "year", "trade_value"])
        frame = frame[frame["trade_value"].gt(0) & frame["cmd_code"].ne("") & frame["cmd_code"].ne("999999")].copy()
        if frame.empty:
            continue
        frame["reporter_code"] = frame["reporter_code"].astype(int)
        frame["year"] = frame["year"].astype(int)
        frame = frame.merge(mapping, on=["classification_code", "cmd_code"], how="left", indicator=True)
        matched = frame["_merge"].eq("both")
        if not bool(matched.all()):
            fallback = frame.loc[~matched, "cmd_code"].map(lambda code: classify_primary_hs6(code, ""))
            frame.loc[~matched, "primary_strict"] = fallback.map(lambda item: item["primary_strict"])
            frame.loc[~matched, "primary_broad"] = fallback.map(lambda item: item["primary_broad"])
            missing = (
                frame.loc[~matched]
                .groupby(["reporter_code", "year", "classification_code", "cmd_code"], as_index=False)["trade_value"]
                .sum()
            )
            missing_details.append(missing)
        frame["primary_strict"] = frame["primary_strict"].map(lambda value: bool(value) if pd.notna(value) else False)
        frame["primary_broad"] = frame["primary_broad"].map(lambda value: bool(value) if pd.notna(value) else False)
        frame["strict_primary_exports"] = np.where(frame["primary_strict"], frame["trade_value"], 0.0)
        frame["broad_primary_exports"] = np.where(frame["primary_broad"], frame["trade_value"], 0.0)
        frame["primary_mapping_matched_export_value"] = np.where(matched, frame["trade_value"], 0.0)
        frame["primary_mapping_missing_export_value"] = np.where(matched, 0.0, frame["trade_value"])
        partials.append(
            frame.groupby(["reporter_code", "year"], as_index=False).agg(
                total_product_exports=("trade_value", "sum"),
                strict_primary_exports=("strict_primary_exports", "sum"),
                broad_primary_exports=("broad_primary_exports", "sum"),
                primary_mapping_matched_export_value=("primary_mapping_matched_export_value", "sum"),
                primary_mapping_missing_export_value=("primary_mapping_missing_export_value", "sum"),
            )
        )

    if not partials:
        raise RuntimeError("No positive product export rows were available for the primary export-share control.")

    shares = pd.concat(partials, ignore_index=True).groupby(["reporter_code", "year"], as_index=False).sum()
    shares["primary_export_share_strict"] = shares["strict_primary_exports"] / shares["total_product_exports"]
    shares["primary_export_share_broad"] = shares["broad_primary_exports"] / shares["total_product_exports"]
    shares["primary_mapping_coverage_share"] = shares["primary_mapping_matched_export_value"] / shares["total_product_exports"]

    diagnostics_rows: list[dict] = [
        {"row_type": "summary", "diagnostic": "aggregate_dir", "reporter_code": "", "year": "", "classification_code": "", "cmd_code": "", "value": str(aggregate_dir), "detail": ""},
        {"row_type": "summary", "diagnostic": "aggregate_files", "reporter_code": "", "year": "", "classification_code": "", "cmd_code": "", "value": len(files), "detail": ""},
        {"row_type": "summary", "diagnostic": "primary_hs6_mapping_rows", "reporter_code": "", "year": "", "classification_code": "", "cmd_code": "", "value": len(primary_mapping), "detail": ""},
        {"row_type": "summary", "diagnostic": "primary_hs6_mapping_bec5_rows", "reporter_code": "", "year": "", "classification_code": "", "cmd_code": "", "value": int(primary_mapping.get("primary_mapping_source", pd.Series(dtype=str)).eq("bec5_audit_mapping").sum()), "detail": ""},
        {"row_type": "summary", "diagnostic": "primary_hs6_mapping_rule_fallback_rows", "reporter_code": "", "year": "", "classification_code": "", "cmd_code": "", "value": int(primary_mapping.get("primary_mapping_source", pd.Series(dtype=str)).eq("observed_aggregate_code_rule_fallback").sum()), "detail": "Observed aggregate classification_code+cmd_code rows absent from BEC audit file and classified by explicit HS rule."},
        {"row_type": "summary", "diagnostic": "country_years_with_exports", "reporter_code": "", "year": "", "classification_code": "", "cmd_code": "", "value": len(shares), "detail": ""},
        {"row_type": "summary", "diagnostic": "min_mapping_coverage_share", "reporter_code": "", "year": "", "classification_code": "", "cmd_code": "", "value": float(shares["primary_mapping_coverage_share"].min()), "detail": ""},
        {"row_type": "summary", "diagnostic": "median_strict_primary_export_share", "reporter_code": "", "year": "", "classification_code": "", "cmd_code": "", "value": float(shares["primary_export_share_strict"].median()), "detail": ""},
        {"row_type": "summary", "diagnostic": "median_broad_primary_export_share", "reporter_code": "", "year": "", "classification_code": "", "cmd_code": "", "value": float(shares["primary_export_share_broad"].median()), "detail": ""},
    ]
    bad_coverage = shares[shares["primary_mapping_coverage_share"].lt(min_mapping_coverage)].copy()
    diagnostics_rows.append(
        {
            "row_type": "summary",
            "diagnostic": "country_years_below_mapping_coverage_threshold",
            "reporter_code": "",
            "year": "",
            "classification_code": "",
            "cmd_code": "",
            "value": len(bad_coverage),
            "detail": f"threshold={min_mapping_coverage:.2f}",
        }
    )
    if missing_details:
        missing = pd.concat(missing_details, ignore_index=True)
        missing = missing.groupby(["reporter_code", "year", "classification_code", "cmd_code"], as_index=False)["trade_value"].sum()
        top_missing = missing.sort_values("trade_value", ascending=False).head(50)
        for row in top_missing.itertuples(index=False):
            diagnostics_rows.append(
                {
                    "row_type": "missing_mapping_hs6",
                    "diagnostic": "top_missing_mapping_export_value",
                    "reporter_code": int(row.reporter_code),
                    "year": int(row.year),
                    "classification_code": row.classification_code,
                    "cmd_code": row.cmd_code,
                    "value": float(row.trade_value),
                    "detail": "classification_code+cmd_code not found in primary_product_hs6_mapping",
                }
            )
    diagnostics = pd.DataFrame(diagnostics_rows)

    if not bad_coverage.empty:
        examples = bad_coverage.sort_values("primary_mapping_coverage_share").head(10)[
            ["reporter_code", "year", "primary_mapping_coverage_share", "primary_mapping_missing_export_value"]
        ].to_dict("records")
        raise RuntimeError(
            "Primary-product HS6 mapping coverage is below "
            f"{min_mapping_coverage:.0%} for {len(bad_coverage):,} reporter-years. "
            f"Lowest-coverage examples: {examples}"
        )
    return shares[primary_export_share_columns()].copy(), diagnostics


def build_primary_export_share_controls(
    country_sample: str,
    start_year: int,
    end_year: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    mapping = build_primary_product_mapping()
    aggregate_dir = sample_processed_path(PRIMARY_AGGREGATE_DIRNAME, country_sample)
    mapping = augment_primary_mapping_with_observed_codes(mapping, aggregate_dir, start_year, end_year)
    shares, diagnostics = construct_primary_export_shares(aggregate_dir, mapping, start_year, end_year)
    return shares, diagnostics, mapping


def merge_primary_export_shares(panel: pd.DataFrame, primary_shares: pd.DataFrame) -> pd.DataFrame:
    if primary_shares.empty:
        return panel
    dupes = int(primary_shares.duplicated(["reporter_code", "year"]).sum())
    if dupes:
        raise RuntimeError(f"Primary export-share controls have {dupes:,} duplicate reporter-year rows.")
    out = panel.merge(primary_shares, on=["reporter_code", "year"], how="left", validate="many_to_one")
    duplicate_panel_rows = int(out.duplicated(["iso3", "year", "flow"]).sum()) if {"iso3", "year", "flow"}.issubset(out.columns) else 0
    if duplicate_panel_rows:
        raise RuntimeError(f"Primary export-share merge created {duplicate_panel_rows:,} duplicate iso3-year-flow rows.")
    return out


def build_country_size_panel(
    args: argparse.Namespace,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    concentration = load_concentration_panel(args.country_sample, args.start_year, args.end_year)
    requested_keys = concentration[["iso3", "year"]].drop_duplicates().copy()
    cache_path = sample_processed_path("country_size_effect_world_bank_controls.csv", args.country_sample)
    controls = load_or_fetch_world_bank_controls(
        sorted(concentration["iso3"].dropna().astype(str).str.upper().unique()),
        requested_keys,
        args.start_year,
        args.end_year,
        cache_path,
        refresh=args.refresh_controls,
    )
    panel = concentration.merge(controls, on=["iso3", "year"], how="left", validate="many_to_one")
    panel = construct_population_size_variables(panel)
    panel = construct_gmm_lag_instruments(panel)
    primary_diagnostics, primary_mapping = empty_primary_share_outputs()[1:]
    if getattr(args, "primary_share_control", "both") != "none":
        primary_shares, primary_diagnostics, primary_mapping = build_primary_export_share_controls(
            args.country_sample,
            args.start_year,
            args.end_year,
        )
        panel = merge_primary_export_shares(panel, primary_shares)
    missing_controls = panel[
        panel[["gdp_current_usd", "population", "log_population", "log_gdp_per_capita"]].isna().any(axis=1)
    ][["country", "iso3", "reporter_code", "year", "flow", "gdp_current_usd", "population"]].copy()
    return panel, controls, missing_controls, primary_diagnostics, primary_mapping


def full_rank_columns(x: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    kept: list[str] = []
    dropped: list[str] = []
    current: pd.DataFrame | None = None
    current_rank = 0
    for col in x.columns:
        candidate = x[[col]] if current is None else pd.concat([current, x[[col]]], axis=1)
        rank = int(np.linalg.matrix_rank(candidate.to_numpy(dtype=float)))
        if rank > current_rank:
            kept.append(col)
            current = candidate
            current_rank = rank
        else:
            dropped.append(col)
    return x[kept], dropped


def full_rank_excluded_instruments(exog: pd.DataFrame, instruments: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    kept: list[str] = []
    dropped: list[str] = []
    current = exog.copy()
    current_rank = int(np.linalg.matrix_rank(current.to_numpy(dtype=float)))
    for col in instruments.columns:
        candidate = pd.concat([current, instruments[[col]]], axis=1)
        rank = int(np.linalg.matrix_rank(candidate.to_numpy(dtype=float)))
        if rank > current_rank:
            kept.append(col)
            current = candidate
            current_rank = rank
        else:
            dropped.append(col)
    return instruments[kept], dropped


def design_matrix(work: pd.DataFrame, terms: list[str], fixed_effects: list[str]) -> tuple[pd.DataFrame, list[str]]:
    parts = [pd.Series(1.0, index=work.index, name="intercept")]
    for term in terms:
        parts.append(pd.to_numeric(work[term], errors="coerce").rename(term))
    for fe_col in fixed_effects:
        dummies = pd.get_dummies(work[fe_col].astype(str), prefix=fe_col, drop_first=True, dtype=float)
        if not dummies.empty:
            parts.append(dummies)
    x = pd.concat(parts, axis=1).astype(float)
    return full_rank_columns(x)


def cluster_robust_covariance(x: np.ndarray, resid: np.ndarray, clusters: pd.Series) -> np.ndarray:
    xtx_inv = np.linalg.pinv(x.T @ x)
    cluster_values = pd.Series(clusters).to_numpy()
    unique_clusters = pd.unique(cluster_values)
    meat = np.zeros((x.shape[1], x.shape[1]))
    for cluster in unique_clusters:
        mask = cluster_values == cluster
        xu = x[mask].T @ resid[mask]
        meat += np.outer(xu, xu)
    nobs, k = x.shape
    groups = len(unique_clusters)
    scale = 1.0
    if groups > 1 and nobs > k:
        scale = (groups / (groups - 1)) * ((nobs - 1) / (nobs - k))
    return scale * xtx_inv @ meat @ xtx_inv


def two_way_cluster_robust_covariance(
    x: np.ndarray,
    resid: np.ndarray,
    clusters_a: pd.Series,
    clusters_b: pd.Series,
) -> np.ndarray:
    joint_clusters = pd.Series(pd.Series(clusters_a).astype(str).to_numpy() + "||" + pd.Series(clusters_b).astype(str).to_numpy())
    return (
        cluster_robust_covariance(x, resid, clusters_a)
        + cluster_robust_covariance(x, resid, clusters_b)
        - cluster_robust_covariance(x, resid, joint_clusters)
    )


def hc1_covariance(x: np.ndarray, resid: np.ndarray) -> np.ndarray:
    xtx_inv = np.linalg.pinv(x.T @ x)
    meat = x.T @ ((resid[:, None] ** 2) * x)
    nobs, k = x.shape
    scale = nobs / (nobs - k) if nobs > k else 1.0
    return scale * xtx_inv @ meat @ xtx_inv


def empty_result(
    model_label: str,
    sample: str,
    flow: str,
    dimension: str,
    metric: str,
    outcome: str,
    terms: list[str],
    fixed_effects: list[str],
    cluster_col: str,
    candidate_rows: int,
    dropped_rows: int,
    status: str,
) -> ModelResult:
    return ModelResult(
        model_label=model_label,
        sample=sample,
        flow=flow,
        dimension=dimension,
        metric=metric,
        outcome=outcome,
        terms=terms,
        beta=np.full(len(terms), np.nan),
        se=np.full(len(terms), np.nan),
        nobs=0,
        clusters=0,
        r_squared=np.nan,
        status=status,
        dropped_rows=dropped_rows,
        candidate_rows=candidate_rows,
        dropped_regressors="",
        se_method="none",
        p_reference_df=np.nan,
        fixed_effects=",".join(fixed_effects) or "none",
        cluster_col=cluster_col or "",
    )


def run_ols_model(
    df: pd.DataFrame,
    outcome: str,
    terms: list[str],
    fixed_effects: list[str],
    model_label: str,
    sample: str,
    flow: str,
    dimension: str,
    metric: str,
    cluster_col: str = "reporter_code",
    two_way_cluster_col: str | None = None,
) -> ModelResult:
    required = [outcome, *terms, *fixed_effects]
    if cluster_col:
        required.append(cluster_col)
    if two_way_cluster_col:
        required.append(two_way_cluster_col)
    required = list(dict.fromkeys(required))
    candidate_rows = int(len(df))
    cluster_label = ",".join(col for col in [cluster_col, two_way_cluster_col or ""] if col)
    missing_required = [col for col in required if col not in df.columns]
    if missing_required:
        return empty_result(
            model_label,
            sample,
            flow,
            dimension,
            metric,
            outcome,
            terms,
            fixed_effects,
            cluster_label,
            candidate_rows,
            candidate_rows,
            f"missing_required_columns:{','.join(missing_required)}",
        )
    work = df.replace([np.inf, -np.inf], np.nan).dropna(subset=required).copy()
    dropped_rows = int(candidate_rows - len(work))
    if len(work) < len(terms) + 3:
        return empty_result(
            model_label,
            sample,
            flow,
            dimension,
            metric,
            outcome,
            terms,
            fixed_effects,
            cluster_label,
            candidate_rows,
            dropped_rows,
            "insufficient_sample",
        )
    y = pd.to_numeric(work[outcome], errors="coerce").to_numpy(dtype=float)
    x_df, dropped_regressors = design_matrix(work, terms, fixed_effects)
    if x_df.shape[0] <= x_df.shape[1]:
        return empty_result(
            model_label,
            sample,
            flow,
            dimension,
            metric,
            outcome,
            terms,
            fixed_effects,
            cluster_label,
            candidate_rows,
            dropped_rows,
            "too_many_regressors",
        )
    x = x_df.to_numpy(dtype=float)
    beta_all, *_ = np.linalg.lstsq(x, y, rcond=None)
    fitted = x @ beta_all
    resid = y - fitted
    if cluster_col and two_way_cluster_col:
        cluster_count_a = int(work[cluster_col].nunique())
        cluster_count_b = int(work[two_way_cluster_col].nunique())
        clusters = min(cluster_count_a, cluster_count_b)
        if cluster_count_a <= 1 or cluster_count_b <= 1:
            cov = np.full((x.shape[1], x.shape[1]), np.nan)
            se_method = f"two-way clustered by {cluster_col} and {two_way_cluster_col}; insufficient clusters"
            p_reference_df = np.nan
        else:
            cov = two_way_cluster_robust_covariance(x, resid, work[cluster_col], work[two_way_cluster_col])
            se_method = f"two-way clustered by {cluster_col} and {two_way_cluster_col}"
            p_reference_df = float(max(clusters - 1, 1))
    elif cluster_col:
        clusters = int(work[cluster_col].nunique())
        if clusters <= 1:
            cov = np.full((x.shape[1], x.shape[1]), np.nan)
            se_method = f"clustered by {cluster_col}; insufficient clusters"
            p_reference_df = np.nan
        else:
            cov = cluster_robust_covariance(x, resid, work[cluster_col])
            se_method = f"clustered by {cluster_col}"
            p_reference_df = float(clusters - 1)
    else:
        clusters = 0
        cov = hc1_covariance(x, resid)
        se_method = "HC1 heteroskedasticity-robust"
        p_reference_df = float(max(x.shape[0] - x.shape[1], 1))
    se_all = np.sqrt(np.maximum(np.diag(cov), 0)) if np.isfinite(cov).any() else np.full(x.shape[1], np.nan)
    total_var = float(np.sum(np.square(y - y.mean())))
    r_squared = float(1 - np.sum(np.square(resid)) / total_var) if total_var > 0 else np.nan
    beta = np.array([beta_all[x_df.columns.get_loc(term)] if term in x_df.columns else np.nan for term in terms], dtype=float)
    se = np.array([se_all[x_df.columns.get_loc(term)] if term in x_df.columns else np.nan for term in terms], dtype=float)
    status = "ok"
    absorbed = [term for term in terms if term not in x_df.columns]
    if absorbed:
        status = "terms_absorbed:" + ",".join(absorbed)
    return ModelResult(
        model_label=model_label,
        sample=sample,
        flow=flow,
        dimension=dimension,
        metric=metric,
        outcome=outcome,
        terms=terms,
        beta=beta,
        se=se,
        nobs=int(len(work)),
        clusters=clusters,
        r_squared=r_squared,
        status=status,
        dropped_rows=dropped_rows,
        candidate_rows=candidate_rows,
        dropped_regressors=",".join(dropped_regressors),
        se_method=se_method,
        p_reference_df=p_reference_df,
        fixed_effects=",".join(fixed_effects) or "none",
        cluster_col=cluster_label,
    )


def model_results_to_frame(results: list[ModelResult]) -> pd.DataFrame:
    rows: list[dict] = []
    for result in results:
        critical = student_t.ppf(0.975, result.p_reference_df) if np.isfinite(result.p_reference_df) else np.nan
        for term, coef, stderr in zip(result.terms, result.beta, result.se):
            t_stat = coef / stderr if np.isfinite(stderr) and stderr > 0 else np.nan
            p_value = (
                2 * student_t.sf(abs(t_stat), result.p_reference_df)
                if np.isfinite(t_stat) and np.isfinite(result.p_reference_df)
                else np.nan
            )
            rows.append(
                {
                    "model_label": result.model_label,
                    "sample": result.sample,
                    "flow": result.flow,
                    "dimension": result.dimension,
                    "metric": result.metric,
                    "outcome": result.outcome,
                    "term": term,
                    "coefficient": float(coef) if np.isfinite(coef) else np.nan,
                    "std_error": float(stderr) if np.isfinite(stderr) else np.nan,
                    "t_stat": float(t_stat) if np.isfinite(t_stat) else np.nan,
                    "p_value": float(p_value) if np.isfinite(p_value) else np.nan,
                    "ci_low": float(coef - critical * stderr) if np.isfinite(coef) and np.isfinite(stderr) and np.isfinite(critical) else np.nan,
                    "ci_high": float(coef + critical * stderr) if np.isfinite(coef) and np.isfinite(stderr) and np.isfinite(critical) else np.nan,
                    "nobs": result.nobs,
                    "clusters": result.clusters,
                    "r_squared": result.r_squared,
                    "status": result.status,
                    "candidate_rows": result.candidate_rows,
                    "dropped_rows": result.dropped_rows,
                    "dropped_regressors": result.dropped_regressors,
                    "fixed_effects": result.fixed_effects,
                    "se_method": result.se_method,
                    "cluster_col": result.cluster_col,
                    "p_value_reference": f"Student t, df={int(result.p_reference_df)}" if np.isfinite(result.p_reference_df) else "",
                }
            )
    return pd.DataFrame(rows)


def benjamini_hochberg(p_values: pd.Series) -> pd.Series:
    values = pd.to_numeric(p_values, errors="coerce")
    q_values = pd.Series(np.nan, index=values.index, dtype=float)
    valid = values.dropna()
    m = len(valid)
    if m == 0:
        return q_values
    order = valid.sort_values().index
    sorted_p = valid.loc[order].to_numpy(dtype=float)
    adjusted = sorted_p * m / np.arange(1, m + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    adjusted = np.clip(adjusted, 0, 1)
    q_values.loc[order] = adjusted
    return q_values


def add_main_q_values(models: pd.DataFrame) -> pd.DataFrame:
    out = models.copy()
    out["bh_q_value"] = np.nan
    mask = out["model_label"].eq("main_year_fe") & out["term"].eq(PRIMARY_TERM) & out["status"].eq("ok")
    out.loc[mask, "bh_q_value"] = benjamini_hochberg(out.loc[mask, "p_value"])
    return out


def add_primary_q_values(models: pd.DataFrame, model_label: str) -> pd.DataFrame:
    out = models.copy()
    out["bh_q_value"] = np.nan
    mask = out["model_label"].eq(model_label) & out["term"].eq(PRIMARY_TERM) & out["status"].eq("ok")
    out.loc[mask, "bh_q_value"] = benjamini_hochberg(out.loc[mask, "p_value"])
    return out


def add_primary_q_values_for_labels(models: pd.DataFrame, model_labels: Iterable[str]) -> pd.DataFrame:
    out = models.copy()
    out["bh_q_value"] = np.nan
    for model_label in model_labels:
        mask = out["model_label"].eq(model_label) & out["term"].eq(PRIMARY_TERM) & out["status"].eq("ok")
        out.loc[mask, "bh_q_value"] = benjamini_hochberg(out.loc[mask, "p_value"])
    return out


def run_main_models(panel: pd.DataFrame, country_sample: str) -> pd.DataFrame:
    results: list[ModelResult] = []
    for flow in FLOWS:
        flow_panel = panel[panel["flow"].eq(flow)].copy()
        for dimension, metric, outcome, _label in OUTCOME_SPECS:
            results.append(
                run_ols_model(
                    flow_panel,
                    outcome=outcome,
                    terms=[PRIMARY_TERM, CONTROL_TERM],
                    fixed_effects=["year"],
                    model_label="main_year_fe",
                    sample=country_sample,
                    flow=flow,
                    dimension=dimension,
                    metric=metric,
                    cluster_col="reporter_code",
                )
            )
    return add_main_q_values(model_results_to_frame(results))


def run_robustness_models(panel: pd.DataFrame, country_sample: str) -> pd.DataFrame:
    results: list[ModelResult] = []
    robustness_terms = [
        ("baseline_population_year_fe", "baseline_log_population"),
        ("average_population_year_fe", "average_log_population"),
    ]
    for flow in FLOWS:
        flow_panel = panel[panel["flow"].eq(flow)].copy()
        for dimension, metric, outcome, _label in OUTCOME_SPECS:
            for label, size_term in robustness_terms:
                results.append(
                    run_ols_model(
                        flow_panel,
                        outcome=outcome,
                        terms=[size_term, CONTROL_TERM],
                        fixed_effects=["year"],
                        model_label=label,
                        sample=country_sample,
                        flow=flow,
                        dimension=dimension,
                        metric=metric,
                        cluster_col="reporter_code",
                    )
                )
    return model_results_to_frame(results)


def run_two_way_cluster_models(panel: pd.DataFrame, country_sample: str) -> pd.DataFrame:
    results: list[ModelResult] = []
    for flow in FLOWS:
        flow_panel = panel[panel["flow"].eq(flow)].copy()
        for dimension, metric, outcome, _label in OUTCOME_SPECS:
            results.append(
                run_ols_model(
                    flow_panel,
                    outcome=outcome,
                    terms=[PRIMARY_TERM, CONTROL_TERM],
                    fixed_effects=["year"],
                    model_label="two_way_country_year_cluster",
                    sample=country_sample,
                    flow=flow,
                    dimension=dimension,
                    metric=metric,
                    cluster_col="reporter_code",
                    two_way_cluster_col="year",
                )
            )
    return add_primary_q_values(model_results_to_frame(results), "two_way_country_year_cluster")


def gmm_model_columns() -> list[str]:
    return [
        "model_label",
        "sample",
        "flow",
        "dimension",
        "metric",
        "outcome",
        "term",
        "coefficient",
        "std_error",
        "t_stat",
        "p_value",
        "bh_q_value",
        "ci_low",
        "ci_high",
        "nobs",
        "clusters",
        "r_squared",
        "status",
        "candidate_rows",
        "dropped_rows",
        "fixed_effects",
        "se_method",
        "cluster_col",
        "endogenous_terms",
        "instrument_terms",
        "instrument_count",
        "j_stat",
        "j_p_value",
        "j_df",
        "iterations",
        "weight_type",
        "p_value_reference",
    ]


def gmm_first_stage_columns() -> list[str]:
    return [
        "model_label",
        "sample",
        "flow",
        "dimension",
        "metric",
        "outcome",
        "endogenous_term",
        "rsquared",
        "partial_rsquared",
        "shea_rsquared",
        "f_stat",
        "f_pval",
        "f_dist",
        "nobs",
        "clusters",
        "status",
        "instrument_terms",
        "instrument_count",
    ]


def float_or_nan(value: object) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return np.nan
    return out if np.isfinite(out) else np.nan


def empty_lag_iv_gmm_rows(
    model_label: str,
    sample: str,
    flow: str,
    dimension: str,
    metric: str,
    outcome: str,
    candidate_rows: int,
    dropped_rows: int,
    status: str,
    clusters: int = 0,
    instrument_terms: Iterable[str] = GMM_INSTRUMENT_TERMS,
) -> tuple[list[dict], list[dict]]:
    instrument_terms = list(instrument_terms)
    instrument_label = ",".join(instrument_terms)
    instrument_count = len(instrument_terms)
    model_rows = []
    for term in GMM_ENDOG_TERMS:
        model_rows.append(
            {
                "model_label": model_label,
                "sample": sample,
                "flow": flow,
                "dimension": dimension,
                "metric": metric,
                "outcome": outcome,
                "term": term,
                "coefficient": np.nan,
                "std_error": np.nan,
                "t_stat": np.nan,
                "p_value": np.nan,
                "bh_q_value": np.nan,
                "ci_low": np.nan,
                "ci_high": np.nan,
                "nobs": 0,
                "clusters": clusters,
                "r_squared": np.nan,
                "status": status,
                "candidate_rows": candidate_rows,
                "dropped_rows": dropped_rows,
                "fixed_effects": "year",
                "se_method": "clustered IVGMM unavailable",
                "cluster_col": "reporter_code",
                "endogenous_terms": ",".join(GMM_ENDOG_TERMS),
                "instrument_terms": instrument_label,
                "instrument_count": instrument_count,
                "j_stat": np.nan,
                "j_p_value": np.nan,
                "j_df": np.nan,
                "iterations": np.nan,
                "weight_type": "clustered",
                "p_value_reference": "",
            }
        )
    first_stage_rows = []
    for term in GMM_ENDOG_TERMS:
        first_stage_rows.append(
            {
                "model_label": model_label,
                "sample": sample,
                "flow": flow,
                "dimension": dimension,
                "metric": metric,
                "outcome": outcome,
                "endogenous_term": term,
                "rsquared": np.nan,
                "partial_rsquared": np.nan,
                "shea_rsquared": np.nan,
                "f_stat": np.nan,
                "f_pval": np.nan,
                "f_dist": "",
                "nobs": 0,
                "clusters": clusters,
                "status": status,
                "instrument_terms": instrument_label,
                "instrument_count": instrument_count,
            }
        )
    return model_rows, first_stage_rows


def run_single_lag_iv_gmm_model(
    df: pd.DataFrame,
    outcome: str,
    model_label: str,
    sample: str,
    flow: str,
    dimension: str,
    metric: str,
) -> tuple[list[dict], list[dict]]:
    required = [outcome, *GMM_ENDOG_TERMS, *GMM_INSTRUMENT_TERMS, "year", "reporter_code"]
    candidate_rows = int(len(df))
    missing_required = [col for col in required if col not in df.columns]
    if missing_required:
        return empty_lag_iv_gmm_rows(
            model_label,
            sample,
            flow,
            dimension,
            metric,
            outcome,
            candidate_rows,
            candidate_rows,
            f"missing_required_columns:{','.join(missing_required)}",
        )

    work = df.replace([np.inf, -np.inf], np.nan).dropna(subset=required).copy()
    dropped_rows = int(candidate_rows - len(work))
    clusters = int(work["reporter_code"].nunique()) if not work.empty else 0
    if len(work) < len(GMM_INSTRUMENT_TERMS) + len(GMM_ENDOG_TERMS) + 5:
        return empty_lag_iv_gmm_rows(
            model_label,
            sample,
            flow,
            dimension,
            metric,
            outcome,
            candidate_rows,
            dropped_rows,
            "insufficient_sample",
            clusters=clusters,
        )
    if clusters <= 1:
        return empty_lag_iv_gmm_rows(
            model_label,
            sample,
            flow,
            dimension,
            metric,
            outcome,
            candidate_rows,
            dropped_rows,
            "insufficient_clusters",
            clusters=clusters,
        )

    y = pd.to_numeric(work[outcome], errors="coerce")
    exog = pd.concat(
        [
            pd.Series(1.0, index=work.index, name="intercept"),
            pd.get_dummies(work["year"].astype(int).astype(str), prefix="year", drop_first=True, dtype=float),
        ],
        axis=1,
    ).astype(float)
    exog, _dropped_exog = full_rank_columns(exog)
    endog = work[list(GMM_ENDOG_TERMS)].apply(pd.to_numeric, errors="coerce").astype(float)
    instruments = work[list(GMM_INSTRUMENT_TERMS)].apply(pd.to_numeric, errors="coerce").astype(float)
    instruments, dropped_instruments = full_rank_excluded_instruments(exog, instruments)
    if instruments.shape[1] < len(GMM_ENDOG_TERMS):
        return empty_lag_iv_gmm_rows(
            model_label,
            sample,
            flow,
            dimension,
            metric,
            outcome,
            candidate_rows,
            dropped_rows,
            "underidentified_after_dropping_collinear_instruments",
            clusters=clusters,
            instrument_terms=list(instruments.columns),
        )

    try:
        result = IVGMM(
            y,
            exog,
            endog,
            instruments,
            weight_type="clustered",
            clusters=work["reporter_code"],
        ).fit(cov_type="clustered", clusters=work["reporter_code"])
    except Exception as exc:
        return empty_lag_iv_gmm_rows(
            model_label,
            sample,
            flow,
            dimension,
            metric,
            outcome,
            candidate_rows,
            dropped_rows,
            f"estimation_failed:{type(exc).__name__}:{str(exc)[:160]}",
            clusters=clusters,
            instrument_terms=list(instruments.columns),
        )

    conf = result.conf_int()
    j_stat = getattr(result, "j_stat", None)
    j_df = float_or_nan(getattr(j_stat, "df", np.nan))
    instrument_label = ",".join(instruments.columns)
    instrument_count = int(instruments.shape[1])
    model_rows = []
    for term in GMM_ENDOG_TERMS:
        model_rows.append(
            {
                "model_label": model_label,
                "sample": sample,
                "flow": flow,
                "dimension": dimension,
                "metric": metric,
                "outcome": outcome,
                "term": term,
                "coefficient": float_or_nan(result.params.get(term, np.nan)),
                "std_error": float_or_nan(result.std_errors.get(term, np.nan)),
                "t_stat": float_or_nan(result.tstats.get(term, np.nan)),
                "p_value": float_or_nan(result.pvalues.get(term, np.nan)),
                "bh_q_value": np.nan,
                "ci_low": float_or_nan(conf.loc[term].iloc[0]) if term in conf.index else np.nan,
                "ci_high": float_or_nan(conf.loc[term].iloc[1]) if term in conf.index else np.nan,
                "nobs": int(result.nobs),
                "clusters": clusters,
                "r_squared": float_or_nan(getattr(result, "rsquared", np.nan)),
                "status": "ok" if not dropped_instruments else f"ok_dropped_collinear_instruments:{','.join(dropped_instruments)}",
                "candidate_rows": candidate_rows,
                "dropped_rows": dropped_rows,
                "fixed_effects": "year",
                "se_method": "IVGMM with clustered moment weight and reporter-country clustered covariance",
                "cluster_col": "reporter_code",
                "endogenous_terms": ",".join(GMM_ENDOG_TERMS),
                "instrument_terms": instrument_label,
                "instrument_count": instrument_count,
                "j_stat": float_or_nan(getattr(j_stat, "stat", np.nan)),
                "j_p_value": float_or_nan(getattr(j_stat, "pval", np.nan)),
                "j_df": j_df,
                "iterations": float_or_nan(getattr(result, "iterations", np.nan)),
                "weight_type": str(getattr(result, "weight_type", "clustered")),
                "p_value_reference": "linearmodels IVGMM clustered covariance",
            }
        )

    first_stage_rows = []
    first_stage_status = "ok" if not dropped_instruments else f"ok_dropped_collinear_instruments:{','.join(dropped_instruments)}"
    try:
        diagnostics = result.first_stage.diagnostics
    except Exception as exc:
        diagnostics = pd.DataFrame()
        first_stage_status = f"first_stage_diagnostics_failed:{type(exc).__name__}:{str(exc)[:160]}"
    for term in GMM_ENDOG_TERMS:
        row = diagnostics.loc[term] if term in diagnostics.index else pd.Series(dtype=object)
        first_stage_rows.append(
            {
                "model_label": model_label,
                "sample": sample,
                "flow": flow,
                "dimension": dimension,
                "metric": metric,
                "outcome": outcome,
                "endogenous_term": term,
                "rsquared": float_or_nan(row.get("rsquared", np.nan)),
                "partial_rsquared": float_or_nan(row.get("partial.rsquared", np.nan)),
                "shea_rsquared": float_or_nan(row.get("shea.rsquared", np.nan)),
                "f_stat": float_or_nan(row.get("f.stat", np.nan)),
                "f_pval": float_or_nan(row.get("f.pval", np.nan)),
                "f_dist": str(row.get("f.dist", "")),
                "nobs": int(result.nobs),
                "clusters": clusters,
                "status": first_stage_status,
                "instrument_terms": instrument_label,
                "instrument_count": instrument_count,
            }
        )
    return model_rows, first_stage_rows


def add_gmm_q_values(models: pd.DataFrame) -> pd.DataFrame:
    out = models.copy()
    if out.empty:
        return out
    if "bh_q_value" not in out.columns:
        out["bh_q_value"] = np.nan
    for term in GMM_ENDOG_TERMS:
        mask = out["model_label"].eq(GMM_MODEL_LABEL) & out["term"].eq(term) & out["status"].astype(str).str.startswith("ok")
        out.loc[mask, "bh_q_value"] = benjamini_hochberg(out.loc[mask, "p_value"])
    return out


def run_lag_iv_gmm_models(panel: pd.DataFrame, country_sample: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    model_rows: list[dict] = []
    first_stage_rows: list[dict] = []
    for flow in FLOWS:
        flow_panel = panel[panel["flow"].eq(flow)].copy()
        for dimension, metric, outcome, _label in OUTCOME_SPECS:
            rows, first_stage = run_single_lag_iv_gmm_model(
                flow_panel,
                outcome=outcome,
                model_label=GMM_MODEL_LABEL,
                sample=country_sample,
                flow=flow,
                dimension=dimension,
                metric=metric,
            )
            model_rows.extend(rows)
            first_stage_rows.extend(first_stage)
    models = add_gmm_q_values(pd.DataFrame(model_rows, columns=gmm_model_columns()))
    first_stage = pd.DataFrame(first_stage_rows, columns=gmm_first_stage_columns())
    return models, first_stage


def run_primary_share_control_models(
    panel: pd.DataFrame,
    country_sample: str,
    selection: str,
    two_way: bool = False,
) -> pd.DataFrame:
    specs = selected_primary_share_specs(selection)
    if not specs:
        return pd.DataFrame(columns=model_results_to_frame([]).columns)
    results: list[ModelResult] = []
    labels: list[str] = []
    for _spec_id, control_term, base_label in specs:
        model_label = base_label if not two_way else base_label.replace("_year_fe", "_two_way_cluster")
        labels.append(model_label)
        for flow in FLOWS:
            flow_panel = panel[panel["flow"].eq(flow)].copy()
            for dimension, metric, outcome, _label in OUTCOME_SPECS:
                results.append(
                    run_ols_model(
                        flow_panel,
                        outcome=outcome,
                        terms=[PRIMARY_TERM, CONTROL_TERM, control_term],
                        fixed_effects=["year"],
                        model_label=model_label,
                        sample=country_sample,
                        flow=flow,
                        dimension=dimension,
                        metric=metric,
                        cluster_col="reporter_code",
                        two_way_cluster_col="year" if two_way else None,
                    )
                )
    return add_primary_q_values_for_labels(model_results_to_frame(results), labels)


def run_yearly_slopes_for_terms(
    panel: pd.DataFrame,
    country_sample: str,
    min_year_countries: int,
    terms: list[str],
    model_prefix: str = "yearly_cross_section",
) -> pd.DataFrame:
    results: list[ModelResult] = []
    for flow in FLOWS:
        flow_panel = panel[panel["flow"].eq(flow)].copy()
        for dimension, metric, outcome, _label in OUTCOME_SPECS:
            for year, group in flow_panel.groupby("year", sort=True):
                complete = group[[outcome, *terms, "reporter_code"]].replace([np.inf, -np.inf], np.nan).dropna()
                if complete["reporter_code"].nunique() < min_year_countries:
                    results.append(
                        empty_result(
                            f"{model_prefix}_{int(year)}",
                            country_sample,
                            flow,
                            dimension,
                            metric,
                            outcome,
                            terms,
                            [],
                            "",
                            int(len(group)),
                            int(len(group) - len(complete)),
                            "insufficient_year_countries",
                        )
                    )
                    continue
                model = run_ols_model(
                    group,
                    outcome=outcome,
                    terms=terms,
                    fixed_effects=[],
                    model_label=f"{model_prefix}_{int(year)}",
                    sample=country_sample,
                    flow=flow,
                    dimension=dimension,
                    metric=metric,
                    cluster_col="",
                )
                results.append(model)
    out = model_results_to_frame(results)
    out["year"] = out["model_label"].str.extract(r"(\d{4})").astype(float)
    return out


def run_yearly_slopes(panel: pd.DataFrame, country_sample: str, min_year_countries: int) -> pd.DataFrame:
    return run_yearly_slopes_for_terms(
        panel,
        country_sample,
        min_year_countries,
        [PRIMARY_TERM, CONTROL_TERM],
        model_prefix="yearly_cross_section",
    )


def newey_west_mean_se(values: pd.Series, max_lags: int = 3) -> float:
    beta = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna().to_numpy(dtype=float)
    periods = len(beta)
    if periods <= 1:
        return np.nan
    centered = beta - beta.mean()
    lags = min(max_lags, periods - 1)
    long_run_variance = float(np.dot(centered, centered) / periods)
    for lag in range(1, lags + 1):
        weight = 1.0 - lag / (lags + 1)
        autocov = float(np.dot(centered[lag:], centered[:-lag]) / periods)
        long_run_variance += 2.0 * weight * autocov
    return float(np.sqrt(max(long_run_variance, 0.0) / periods))


def run_fama_macbeth_models(
    yearly: pd.DataFrame,
    country_sample: str,
    hac_lags: int = 3,
    model_label: str | None = None,
) -> pd.DataFrame:
    rows: list[dict] = []
    slopes = yearly[yearly["term"].eq(PRIMARY_TERM)].copy()
    label = model_label or f"fama_macbeth_hac{hac_lags}"
    for flow in FLOWS:
        for dimension, metric, outcome, _label in OUTCOME_SPECS:
            group = slopes[
                slopes["flow"].eq(flow)
                & slopes["dimension"].eq(dimension)
                & slopes["metric"].eq(metric)
                & slopes["status"].eq("ok")
            ].sort_values("year")
            years = pd.to_numeric(group["year"], errors="coerce").dropna()
            periods = int(len(group))
            status = "ok" if periods >= 3 else "insufficient_yearly_slopes"
            coef = float(group["coefficient"].mean()) if status == "ok" else np.nan
            simple_se = float(group["coefficient"].std(ddof=1) / np.sqrt(periods)) if periods > 1 else np.nan
            hac_se = newey_west_mean_se(group["coefficient"], max_lags=hac_lags) if status == "ok" else np.nan
            p_reference_df = float(periods - 1) if status == "ok" else np.nan
            t_stat = coef / hac_se if np.isfinite(hac_se) and hac_se > 0 else np.nan
            p_value = (
                2 * student_t.sf(abs(t_stat), p_reference_df)
                if np.isfinite(t_stat) and np.isfinite(p_reference_df)
                else np.nan
            )
            critical = student_t.ppf(0.975, p_reference_df) if np.isfinite(p_reference_df) else np.nan
            rows.append(
                {
                    "model_label": label,
                    "sample": country_sample,
                    "flow": flow,
                    "dimension": dimension,
                    "metric": metric,
                    "outcome": outcome,
                    "term": PRIMARY_TERM,
                    "coefficient": coef,
                    "std_error": hac_se,
                    "simple_std_error": simple_se,
                    "t_stat": float(t_stat) if np.isfinite(t_stat) else np.nan,
                    "p_value": float(p_value) if np.isfinite(p_value) else np.nan,
                    "ci_low": float(coef - critical * hac_se) if np.isfinite(coef) and np.isfinite(hac_se) and np.isfinite(critical) else np.nan,
                    "ci_high": float(coef + critical * hac_se) if np.isfinite(coef) and np.isfinite(hac_se) and np.isfinite(critical) else np.nan,
                    "nobs": int(pd.to_numeric(group.get("nobs", pd.Series(dtype=float)), errors="coerce").sum()) if periods else 0,
                    "clusters": periods,
                    "r_squared": float(pd.to_numeric(group.get("r_squared", pd.Series(dtype=float)), errors="coerce").mean()) if periods else np.nan,
                    "status": status,
                    "candidate_rows": int(pd.to_numeric(group.get("candidate_rows", pd.Series(dtype=float)), errors="coerce").sum()) if periods else 0,
                    "dropped_rows": int(pd.to_numeric(group.get("dropped_rows", pd.Series(dtype=float)), errors="coerce").sum()) if periods else 0,
                    "dropped_regressors": "",
                    "fixed_effects": "year-by-year cross sections",
                    "se_method": f"Newey-West HAC over yearly coefficients, lag={hac_lags}",
                    "cluster_col": "yearly_coefficients",
                    "p_value_reference": f"Student t, df={int(p_reference_df)}" if np.isfinite(p_reference_df) else "",
                    "hac_lags": hac_lags,
                    "years_estimated": periods,
                    "min_year": int(years.min()) if not years.empty else np.nan,
                    "max_year": int(years.max()) if not years.empty else np.nan,
                }
            )
    out = pd.DataFrame(rows)
    out["bh_q_value"] = np.nan
    mask = out["status"].eq("ok")
    out.loc[mask, "bh_q_value"] = benjamini_hochberg(out.loc[mask, "p_value"])
    return out


def run_primary_share_fama_macbeth_models(
    panel: pd.DataFrame,
    country_sample: str,
    selection: str,
    min_year_countries: int,
    hac_lags: int = 3,
) -> pd.DataFrame:
    frames = []
    for spec_id, control_term, _base_label in selected_primary_share_specs(selection):
        yearly = run_yearly_slopes_for_terms(
            panel,
            country_sample,
            min_year_countries,
            [PRIMARY_TERM, CONTROL_TERM, control_term],
            model_prefix=f"primary_share_{spec_id}_yearly_cross_section",
        )
        fmb = run_fama_macbeth_models(
            yearly,
            country_sample,
            hac_lags=hac_lags,
            model_label=f"primary_share_{spec_id}_fama_macbeth_hac{hac_lags}",
        )
        fmb["primary_share_control"] = control_term
        frames.append(fmb)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def build_us_population_counterfactuals(panel: pd.DataFrame, main_models: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "target_order",
        "target_id",
        "target_label",
        "target_percentile",
        "target_quantile_population",
        "target_country",
        "target_iso3",
        "target_year",
        "target_population",
        "target_population_rank",
        "rd2_country_count",
        "us_country",
        "us_iso3",
        "us_year",
        "us_population",
        "flow",
        "dimension",
        "metric",
        "outcome",
        "coefficient",
        "log_population_delta",
        "predicted_gini_change",
        "outcome_sample_sd",
        "predicted_gini_change_sd_share",
    ]
    country_year = panel[["country", "iso3", "year", "population"]].drop_duplicates().copy()
    country_year["population"] = pd.to_numeric(country_year["population"], errors="coerce")
    country_year["year"] = pd.to_numeric(country_year["year"], errors="coerce")
    country_year = country_year.dropna(subset=["country", "iso3", "year", "population"])
    country_year = country_year[country_year["population"].gt(0)].copy()
    if country_year.empty:
        return pd.DataFrame(columns=columns)

    latest = (
        country_year.sort_values(["iso3", "year", "population"])
        .drop_duplicates(["iso3"], keep="last")
        .sort_values("population")
        .reset_index(drop=True)
    )
    latest["population_rank"] = np.arange(1, len(latest) + 1)
    us_rows = latest[latest["iso3"].astype(str).str.upper().eq("USA")]
    if us_rows.empty:
        raise RuntimeError("US population counterfactual requires USA in the country-size panel.")
    us = us_rows.iloc[0]
    us_population = float(us["population"])

    gini_models = main_models[
        main_models["term"].eq(PRIMARY_TERM) & main_models["metric"].eq("gini") & main_models["status"].eq("ok")
    ].copy()
    if gini_models.empty:
        return pd.DataFrame(columns=columns)

    outcome_sd: dict[tuple[str, str], float] = {}
    for model in gini_models.itertuples(index=False):
        required = [model.outcome, PRIMARY_TERM, CONTROL_TERM, "reporter_code"]
        if any(col not in panel.columns for col in required):
            outcome_sd[(model.flow, model.outcome)] = np.nan
            continue
        work = panel[panel["flow"].eq(model.flow)].replace([np.inf, -np.inf], np.nan).dropna(subset=required)
        outcome_sd[(model.flow, model.outcome)] = float(pd.to_numeric(work[model.outcome], errors="coerce").std(ddof=1))

    rows = []
    country_count = int(len(latest))
    for order, (target_id, target_label, percentile) in enumerate(US_POPULATION_COUNTERFACTUAL_TARGETS, start=1):
        quantile_population = float(latest["population"].quantile(percentile))
        if target_id == "smallest":
            target = latest.iloc[0]
        else:
            target = (
                latest.assign(distance=(latest["population"] - quantile_population).abs())
                .sort_values(["distance", "population", "iso3"])
                .iloc[0]
            )
        target_population = float(target["population"])
        log_delta = float(np.log(target_population) - np.log(us_population))
        for model in gini_models.itertuples(index=False):
            coefficient = float(model.coefficient)
            predicted_change = coefficient * log_delta
            sd = outcome_sd.get((model.flow, model.outcome), np.nan)
            sd_share = predicted_change / sd if np.isfinite(sd) and sd > 0 else np.nan
            rows.append(
                {
                    "target_order": order,
                    "target_id": target_id,
                    "target_label": target_label,
                    "target_percentile": percentile,
                    "target_quantile_population": quantile_population,
                    "target_country": target.country,
                    "target_iso3": target.iso3,
                    "target_year": int(target.year),
                    "target_population": target_population,
                    "target_population_rank": int(target.population_rank),
                    "rd2_country_count": country_count,
                    "us_country": us.country,
                    "us_iso3": us.iso3,
                    "us_year": int(us.year),
                    "us_population": us_population,
                    "flow": model.flow,
                    "dimension": model.dimension,
                    "metric": model.metric,
                    "outcome": model.outcome,
                    "coefficient": coefficient,
                    "log_population_delta": log_delta,
                    "predicted_gini_change": predicted_change,
                    "outcome_sample_sd": sd,
                    "predicted_gini_change_sd_share": sd_share,
                }
            )
    return pd.DataFrame(rows, columns=columns)


def sample_diagnostics(panel: pd.DataFrame, missing_controls: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    unique_country_year = panel[["iso3", "year"]].drop_duplicates()
    complete_country_year = (
        panel[["iso3", "year", "gdp_current_usd", "population", "log_population", "log_gdp_per_capita"]]
        .drop_duplicates(["iso3", "year"])
        .dropna(subset=["gdp_current_usd", "population", "log_population", "log_gdp_per_capita"])
    )
    rows = [
        {"diagnostic": "country_sample", "value": args.country_sample},
        {"diagnostic": "start_year", "value": args.start_year},
        {"diagnostic": "end_year", "value": args.end_year},
        {"diagnostic": "panel_rows", "value": len(panel)},
        {"diagnostic": "countries", "value": panel["iso3"].nunique()},
        {"diagnostic": "years", "value": panel["year"].nunique()},
        {"diagnostic": "country_years", "value": len(unique_country_year)},
        {"diagnostic": "complete_control_country_years", "value": len(complete_country_year)},
        {
            "diagnostic": "complete_control_country_year_share",
            "value": len(complete_country_year) / len(unique_country_year) if len(unique_country_year) else np.nan,
        },
        {"diagnostic": "primary_share_control", "value": args.primary_share_control},
        {"diagnostic": "missing_control_flow_rows", "value": len(missing_controls)},
        {"diagnostic": "duplicate_iso3_year_flow_rows", "value": int(panel.duplicated(["iso3", "year", "flow"]).sum())},
    ]
    gmm_required = [*GMM_ENDOG_TERMS, *GMM_INSTRUMENT_TERMS]
    if all(col in panel.columns for col in gmm_required):
        complete_gmm = panel[gmm_required].replace([np.inf, -np.inf], np.nan).notna().all(axis=1)
        rows.extend(
            [
                {"diagnostic": "gmm_lag_iv_complete_flow_rows", "value": int(complete_gmm.sum())},
                {"diagnostic": "gmm_lag_iv_missing_flow_rows", "value": int((~complete_gmm).sum())},
            ]
        )
    for col in GMM_INSTRUMENT_TERMS:
        if col in panel.columns:
            values = pd.to_numeric(panel[col], errors="coerce")
            rows.extend(
                [
                    {"diagnostic": f"{col}_complete_flow_rows", "value": int(values.notna().sum())},
                    {"diagnostic": f"{col}_missing_flow_rows", "value": int(values.isna().sum())},
                ]
            )
    for col in ["primary_export_share_strict", "primary_export_share_broad", "primary_mapping_coverage_share"]:
        if col in panel.columns:
            values = pd.to_numeric(panel[col], errors="coerce")
            rows.extend(
                [
                    {"diagnostic": f"{col}_complete_flow_rows", "value": int(values.notna().sum())},
                    {"diagnostic": f"{col}_missing_flow_rows", "value": int(values.isna().sum())},
                    {"diagnostic": f"{col}_min", "value": float(values.min()) if values.notna().any() else np.nan},
                    {"diagnostic": f"{col}_median", "value": float(values.median()) if values.notna().any() else np.nan},
                    {"diagnostic": f"{col}_max", "value": float(values.max()) if values.notna().any() else np.nan},
                ]
            )
    for flow in FLOWS:
        rows.append({"diagnostic": f"{flow.lower()}_rows", "value": int(panel["flow"].eq(flow).sum())})
    for _dimension, _metric, outcome, _label in OUTCOME_SPECS:
        values = pd.to_numeric(panel[outcome], errors="coerce")
        rows.append({"diagnostic": f"{outcome}_missing_rows", "value": int(values.isna().sum())})
        rows.append({"diagnostic": f"{outcome}_complete_rows", "value": int(values.notna().sum())})
    return pd.DataFrame(rows)


def make_yearly_slope_figures(yearly: pd.DataFrame, figure_dir: Path) -> list[Path]:
    sns.set_theme(style="whitegrid")
    paths: list[Path] = []
    slope = yearly[yearly["term"].eq(PRIMARY_TERM) & yearly["status"].eq("ok")].copy()
    if slope.empty:
        return paths
    for dimension in ["product", "partner"]:
        data = slope[slope["dimension"].eq(dimension)].copy()
        if data.empty:
            continue
        grid = sns.relplot(
            data=data,
            x="year",
            y="coefficient",
            hue="metric",
            col="flow",
            kind="line",
            marker="o",
            facet_kws={"sharey": False},
            height=4,
            aspect=1.35,
        )
        for ax in grid.axes.flat:
            ax.axhline(0, color="#111827", linewidth=1, linestyle="--")
            ax.set_xlabel("Year")
            ax.set_ylabel("Log population coefficient")
        grid.fig.suptitle(f"Year-by-year country-size slopes: {dimension} concentration", y=1.04)
        path = figure_dir / f"yearly_size_slopes_{dimension}.png"
        grid.savefig(path, dpi=220, bbox_inches="tight")
        plt.close(grid.fig)
        paths.append(path)
    return paths


def compact_main_table(main_models: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "flow",
        "dimension",
        "metric",
        "coefficient",
        "std_error",
        "p_value",
        "bh_q_value",
        "nobs",
        "clusters",
        "status",
    ]
    return main_models[main_models["term"].eq(PRIMARY_TERM)][cols].copy()


def write_memo(
    memo_path: Path,
    args: argparse.Namespace,
    diagnostics: pd.DataFrame,
    main_models: pd.DataFrame,
    robustness: pd.DataFrame,
    two_way: pd.DataFrame,
    fama_macbeth: pd.DataFrame,
    gmm_models: pd.DataFrame,
    gmm_first_stage: pd.DataFrame,
    primary_share: pd.DataFrame,
    primary_share_two_way: pd.DataFrame,
    primary_share_fama_macbeth: pd.DataFrame,
    primary_diagnostics: pd.DataFrame,
    yearly: pd.DataFrame,
    output_paths: dict[str, Path | list[Path]],
) -> None:
    main_table = compact_main_table(main_models).round(4)
    robustness_terms = robustness[
        robustness["term"].isin(["baseline_log_population", "average_log_population"])
    ][["model_label", "flow", "dimension", "metric", "term", "coefficient", "std_error", "p_value", "nobs", "clusters", "status"]].round(4)
    two_way_table = two_way[two_way["term"].eq(PRIMARY_TERM)][
        ["flow", "dimension", "metric", "coefficient", "std_error", "p_value", "bh_q_value", "nobs", "clusters", "status"]
    ].round(4)
    fama_macbeth_table = fama_macbeth[
        ["flow", "dimension", "metric", "coefficient", "std_error", "simple_std_error", "p_value", "bh_q_value", "years_estimated", "status"]
    ].round(4)
    gmm_table = (
        gmm_models[gmm_models["term"].isin(GMM_ENDOG_TERMS)][
            [
                "term",
                "flow",
                "dimension",
                "metric",
                "coefficient",
                "std_error",
                "p_value",
                "bh_q_value",
                "j_stat",
                "j_p_value",
                "instrument_count",
                "nobs",
                "clusters",
                "status",
            ]
        ].round(4)
        if not gmm_models.empty
        else pd.DataFrame()
    )
    gmm_first_stage_table = (
        gmm_first_stage[
            [
                "endogenous_term",
                "flow",
                "dimension",
                "metric",
                "partial_rsquared",
                "shea_rsquared",
                "f_stat",
                "f_pval",
                "f_dist",
                "status",
            ]
        ].round(4)
        if not gmm_first_stage.empty
        else pd.DataFrame()
    )
    primary_share_table = (
        primary_share[primary_share["term"].eq(PRIMARY_TERM)][
            ["model_label", "flow", "dimension", "metric", "coefficient", "std_error", "p_value", "bh_q_value", "nobs", "clusters", "status"]
        ].round(4)
        if not primary_share.empty
        else pd.DataFrame()
    )
    primary_share_two_way_table = (
        primary_share_two_way[primary_share_two_way["term"].eq(PRIMARY_TERM)][
            ["model_label", "flow", "dimension", "metric", "coefficient", "std_error", "p_value", "bh_q_value", "nobs", "clusters", "status"]
        ].round(4)
        if not primary_share_two_way.empty
        else pd.DataFrame()
    )
    primary_share_fama_macbeth_table = (
        primary_share_fama_macbeth[
            ["model_label", "flow", "dimension", "metric", "coefficient", "std_error", "simple_std_error", "p_value", "bh_q_value", "years_estimated", "status"]
        ].round(4)
        if not primary_share_fama_macbeth.empty
        else pd.DataFrame()
    )
    primary_summary = (
        primary_diagnostics[primary_diagnostics["row_type"].eq("summary")][["diagnostic", "value", "detail"]]
        if not primary_diagnostics.empty and "row_type" in primary_diagnostics.columns
        else pd.DataFrame()
    )
    yearly_ok = yearly[yearly["term"].eq(PRIMARY_TERM) & yearly["status"].eq("ok")]
    yearly_summary = (
        yearly_ok.groupby(["flow", "dimension", "metric"], as_index=False)
        .agg(years_estimated=("year", "nunique"), median_beta=("coefficient", "median"), min_beta=("coefficient", "min"), max_beta=("coefficient", "max"))
        .round(4)
        if not yearly_ok.empty
        else pd.DataFrame()
    )
    text = f"""# Country Size Effect Test

Generated: {now_utc()}

This is a descriptive panel exercise. It tests whether larger countries have different concentration levels within the same year. It does not estimate a causal effect of population.

## Specification

Main model:

```text
concentration_it = beta log_population_it + gamma log_gdp_per_capita_it + year FE + error_it
```

- Country sample: `{args.country_sample}`
- Years: {args.start_year}-{args.end_year}
- Main standard errors: clustered by reporter country
- No country fixed effects in the main model
- GDP per capita is constructed as `log_gdp_current_usd - log_population`
- Primary export-share robustness: `{args.primary_share_control}`

## Main Log-Population Coefficients

{main_table.to_markdown(index=False)}

## Robustness Checks

These replace yearly population with baseline or average log population.

{robustness_terms.to_markdown(index=False)}

## Two-Way Clustered Inference

This keeps the main coefficient estimates but clusters standard errors by reporter country and year.

{two_way_table.to_markdown(index=False)}

## Fama-MacBeth Yearly-Slope Check

This averages the year-by-year cross-sectional `log_population` slopes and uses a Newey-West HAC standard error over the annual coefficients.
Annual diagnostics require at least `{args.min_year_countries}` countries, so years below that threshold are omitted from this check.

{fama_macbeth_table.to_markdown(index=False)}

## Lag-IV GMM Robustness

This robustness treats both `log_population` and `log_gdp_per_capita` as endogenous and instruments them with their own exact `t-2` and `t-3` lags:

```text
E[lag2_log_population_it * error_it] = 0
E[lag3_log_population_it * error_it] = 0
E[lag2_log_gdp_per_capita_it * error_it] = 0
E[lag3_log_gdp_per_capita_it * error_it] = 0
```

The estimator is IV-GMM with year fixed effects and reporter-country clustered covariance. This is a diagnostic robustness check, not proof that the lag instruments satisfy exclusion.
References: [Hansen (1982)](https://larspeterhansen.org/lph_research/large-sample-properties-of-generalized-method-of-moments-estimators/) for GMM, [Roodman (2009)](https://journals.sagepub.com/doi/10.1177/1536867X0900900106) for lag-instrument and instrument-proliferation cautions, and [Cadot, Carrere, and Strauss-Kahn (2011)](https://econpapers.repec.org/article/tprrestat/v_3a93_3ay_3a2011_3ai_3a2_3ap_3a590-605.htm) as the closest export-diversification/development precedent.

{gmm_table.to_markdown(index=False) if not gmm_table.empty else "Lag-IV GMM models were not estimable."}

### Lag-IV GMM First Stages

{gmm_first_stage_table.to_markdown(index=False) if not gmm_first_stage_table.empty else "No Lag-IV GMM first-stage diagnostics were written."}

## Primary Export-Share Control

These robustness checks add a country-year export-resource-dependence control:

```text
concentration_it = beta log_population_it + gamma log_gdp_per_capita_it + theta primary_export_share_it + year FE + error_it
```

`primary_export_share_strict` is the preferred raw/lightly processed HS6 primary-products share. `primary_export_share_broad` adds first-stage commodity-processing products such as refined petroleum, pulp, and first-stage metals.

### Country-Clustered

{primary_share_table.to_markdown(index=False) if not primary_share_table.empty else "Primary export-share controls were not requested."}

### Two-Way Clustered

{primary_share_two_way_table.to_markdown(index=False) if not primary_share_two_way_table.empty else "Primary export-share controls were not requested."}

### Fama-MacBeth

{primary_share_fama_macbeth_table.to_markdown(index=False) if not primary_share_fama_macbeth_table.empty else "Primary export-share controls were not requested."}

### Primary-Share Diagnostics

{primary_summary.to_markdown(index=False) if not primary_summary.empty else "No primary-share diagnostics were written."}

## Year-By-Year Diagnostic Summary

{yearly_summary.to_markdown(index=False) if not yearly_summary.empty else "No yearly slope diagnostics were estimable."}

## Sample Diagnostics

{diagnostics.to_markdown(index=False)}

## Files

- Processed panel: `{rel(output_paths["panel"])}`
- Main models: `{rel(output_paths["main_models"])}`
- Robustness models: `{rel(output_paths["robustness_models"])}`
- Two-way cluster models: `{rel(output_paths["two_way_cluster_models"])}`
- Fama-MacBeth models: `{rel(output_paths["fama_macbeth_models"])}`
- Lag-IV GMM models: `{rel(output_paths["gmm_lag_iv_models"])}`
- Lag-IV GMM first-stage diagnostics: `{rel(output_paths["gmm_lag_iv_first_stage"])}`
- Primary export-share country-clustered models: `{rel(output_paths["primary_share_control_models"])}`
- Primary export-share two-way cluster models: `{rel(output_paths["primary_share_two_way_cluster_models"])}`
- Primary export-share Fama-MacBeth models: `{rel(output_paths["primary_share_fama_macbeth_models"])}`
- Primary export-share diagnostics: `{rel(output_paths["primary_export_share_diagnostics"])}`
- Primary HS6 mapping: `{rel(output_paths["primary_product_hs6_mapping"])}`
- US population counterfactuals: `{rel(output_paths["us_population_counterfactuals"])}`
- Yearly slopes: `{rel(output_paths["yearly_slopes"])}`
- Sample diagnostics: `{rel(output_paths["sample_diagnostics"])}`
- Missing controls: `{rel(output_paths["missing_controls"])}`
- Manifest: `{rel(output_paths["manifest"])}`

## Caveats

- This is a between-country descriptive gradient, not causal identification.
- Product concentration inherits the existing pipeline's HS6 `999999` exclusion convention.
- Partner concentration follows the repo convention that `999999` can remain when products are summed into reporter-partner totals.
- Yearly population is used in the main model; baseline and average population robustness checks test whether results are driven by year-to-year population movement.
"""
    memo_path.write_text(text, encoding="utf-8")


def source_manifest(path: Path) -> dict:
    if not path.exists():
        return {"path": rel(path), "exists": False}
    return {
        "path": rel(path),
        "exists": True,
        "size_bytes": path.stat().st_size,
        "mtime_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).replace(microsecond=0).isoformat(),
    }


def write_manifest(
    manifest_path: Path,
    args: argparse.Namespace,
    panel: pd.DataFrame,
    main_models: pd.DataFrame,
    robustness: pd.DataFrame,
    two_way: pd.DataFrame,
    fama_macbeth: pd.DataFrame,
    gmm_models: pd.DataFrame,
    gmm_first_stage: pd.DataFrame,
    primary_share: pd.DataFrame,
    primary_share_two_way: pd.DataFrame,
    primary_share_fama_macbeth: pd.DataFrame,
    yearly: pd.DataFrame,
    output_paths: dict[str, Path | list[Path]],
) -> None:
    concentration_path = sample_processed_path("concentration_all_years.parquet", args.country_sample)
    manifest = {
        "created_at_utc": now_utc(),
        "country_sample": args.country_sample,
        "start_year": args.start_year,
        "end_year": args.end_year,
        "min_year_countries": args.min_year_countries,
        "refresh_controls": args.refresh_controls,
        "primary_share_control": args.primary_share_control,
        "model": "pooled cross-sectional panel with year fixed effects; country-clustered SEs",
        "inference_robustness": [
            "two-way reporter-country and year clustered standard errors",
            "Fama-MacBeth average yearly slopes with Newey-West HAC standard errors",
            "Lag-IV GMM using exact t-2 and t-3 internal instruments for log population and log GDP per capita",
        ],
        "lag_iv_gmm_robustness": {
            "model_label": GMM_MODEL_LABEL,
            "endogenous_terms": list(GMM_ENDOG_TERMS),
            "excluded_instruments": list(GMM_INSTRUMENT_TERMS),
            "fixed_effects": "year",
            "cluster_col": "reporter_code",
            "causal_claim": False,
            "interpretation": "diagnostic robustness check; lag exclusion restrictions are not guaranteed by the estimator",
        },
        "primary_share_robustness": {
            "strict": "raw or very lightly processed HS6 primary products",
            "broad": "strict primary products plus first-stage commodity processing",
            "minimum_mapping_coverage": MIN_PRIMARY_MAPPING_COVERAGE,
        },
        "causal_claim": False,
        "rows_panel": int(len(panel)),
        "countries": int(panel["iso3"].nunique()),
        "years": [int(panel["year"].min()), int(panel["year"].max())],
        "missing_outcome_rows": {
            outcome: int(pd.to_numeric(panel[outcome], errors="coerce").isna().sum())
            for _dimension, _metric, outcome, _label in OUTCOME_SPECS
        },
        "main_models_ok": int((main_models["status"].eq("ok") & main_models["term"].eq(PRIMARY_TERM)).sum()),
        "robustness_models_ok": int((robustness["status"].eq("ok") & robustness["term"].isin(["baseline_log_population", "average_log_population"])).sum()),
        "two_way_cluster_models_ok": int((two_way["status"].eq("ok") & two_way["term"].eq(PRIMARY_TERM)).sum()),
        "fama_macbeth_models_ok": int((fama_macbeth["status"].eq("ok") & fama_macbeth["term"].eq(PRIMARY_TERM)).sum()),
        "gmm_lag_iv_models_ok": int((gmm_models["status"].astype(str).str.startswith("ok") & gmm_models["term"].isin(GMM_ENDOG_TERMS)).sum()) if not gmm_models.empty else 0,
        "gmm_lag_iv_first_stage_ok": int(gmm_first_stage["status"].astype(str).str.startswith("ok").sum()) if not gmm_first_stage.empty else 0,
        "primary_share_models_ok": int((primary_share.get("status", pd.Series(dtype=str)).eq("ok") & primary_share.get("term", pd.Series(dtype=str)).eq(PRIMARY_TERM)).sum()) if not primary_share.empty else 0,
        "primary_share_two_way_models_ok": int((primary_share_two_way.get("status", pd.Series(dtype=str)).eq("ok") & primary_share_two_way.get("term", pd.Series(dtype=str)).eq(PRIMARY_TERM)).sum()) if not primary_share_two_way.empty else 0,
        "primary_share_fama_macbeth_models_ok": int((primary_share_fama_macbeth.get("status", pd.Series(dtype=str)).eq("ok") & primary_share_fama_macbeth.get("term", pd.Series(dtype=str)).eq(PRIMARY_TERM)).sum()) if not primary_share_fama_macbeth.empty else 0,
        "yearly_slopes_ok": int((yearly["status"].eq("ok") & yearly["term"].eq(PRIMARY_TERM)).sum()),
        "sources": {
            "concentration": source_manifest(concentration_path),
            "controls_cache": source_manifest(sample_processed_path("country_size_effect_world_bank_controls.csv", args.country_sample)),
            "primary_share_aggregates": source_manifest(sample_processed_path(PRIMARY_AGGREGATE_DIRNAME, args.country_sample)),
            "primary_hs6_mapping_source": source_manifest(PRIMARY_BEC_MAPPING_PATH),
            "plan": source_manifest(ROOT / "country_size_effect_plan.md"),
        },
        "outputs": {
            key: [rel(p) for p in value] if isinstance(value, list) else rel(value)
            for key, value in output_paths.items()
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def run(args: argparse.Namespace) -> None:
    base_results = sample_results_dir(args.country_sample)
    table_dir = base_results / "country_size_effect_tables"
    figure_dir = base_results / "country_size_effect_figures"
    ensure_dirs(table_dir, figure_dir, sample_processed_path("", args.country_sample))

    panel, controls, missing_controls, primary_diagnostics, primary_mapping = build_country_size_panel(args)
    diagnostics = sample_diagnostics(panel, missing_controls, args)
    panel_path = sample_processed_path("country_size_effect_panel.parquet", args.country_sample)
    panel.to_parquet(panel_path, index=False)

    missing_path = table_dir / "missing_controls.csv"
    missing_controls.to_csv(missing_path, index=False)
    diagnostics_path = table_dir / "sample_diagnostics.csv"
    diagnostics.to_csv(diagnostics_path, index=False)
    primary_diagnostics_path = table_dir / "primary_export_share_diagnostics.csv"
    primary_diagnostics.to_csv(primary_diagnostics_path, index=False)
    primary_mapping_path = table_dir / "primary_product_hs6_mapping.csv"
    primary_mapping.to_csv(primary_mapping_path, index=False)

    main_models = run_main_models(panel, args.country_sample)
    robustness = run_robustness_models(panel, args.country_sample)
    two_way = run_two_way_cluster_models(panel, args.country_sample)
    gmm_models, gmm_first_stage = run_lag_iv_gmm_models(panel, args.country_sample)
    primary_share = run_primary_share_control_models(panel, args.country_sample, args.primary_share_control, two_way=False)
    primary_share_two_way = run_primary_share_control_models(panel, args.country_sample, args.primary_share_control, two_way=True)
    yearly = run_yearly_slopes(panel, args.country_sample, args.min_year_countries)
    fama_macbeth = run_fama_macbeth_models(yearly, args.country_sample)
    primary_share_fama_macbeth = run_primary_share_fama_macbeth_models(
        panel,
        args.country_sample,
        args.primary_share_control,
        args.min_year_countries,
    )
    us_counterfactuals = build_us_population_counterfactuals(panel, main_models)

    main_path = table_dir / "main_models.csv"
    robustness_path = table_dir / "robustness_models.csv"
    two_way_path = table_dir / "two_way_cluster_models.csv"
    gmm_path = table_dir / "gmm_lag_iv_models.csv"
    gmm_first_stage_path = table_dir / "gmm_lag_iv_first_stage.csv"
    yearly_path = table_dir / "yearly_slopes.csv"
    fama_macbeth_path = table_dir / "fama_macbeth_models.csv"
    primary_share_path = table_dir / "primary_share_control_models.csv"
    primary_share_two_way_path = table_dir / "primary_share_two_way_cluster_models.csv"
    primary_share_fama_macbeth_path = table_dir / "primary_share_fama_macbeth_models.csv"
    us_counterfactual_path = table_dir / "us_population_counterfactuals.csv"
    main_models.to_csv(main_path, index=False)
    robustness.to_csv(robustness_path, index=False)
    two_way.to_csv(two_way_path, index=False)
    gmm_models.to_csv(gmm_path, index=False)
    gmm_first_stage.to_csv(gmm_first_stage_path, index=False)
    yearly.to_csv(yearly_path, index=False)
    fama_macbeth.to_csv(fama_macbeth_path, index=False)
    primary_share.to_csv(primary_share_path, index=False)
    primary_share_two_way.to_csv(primary_share_two_way_path, index=False)
    primary_share_fama_macbeth.to_csv(primary_share_fama_macbeth_path, index=False)
    us_counterfactuals.to_csv(us_counterfactual_path, index=False)

    figure_paths = make_yearly_slope_figures(yearly, figure_dir)
    memo_path = base_results / "country_size_effect.md"
    manifest_path = base_results / "run_manifest_country_size_effect.json"
    output_paths: dict[str, Path | list[Path]] = {
        "panel": panel_path,
        "main_models": main_path,
        "robustness_models": robustness_path,
        "two_way_cluster_models": two_way_path,
        "gmm_lag_iv_models": gmm_path,
        "gmm_lag_iv_first_stage": gmm_first_stage_path,
        "fama_macbeth_models": fama_macbeth_path,
        "primary_share_control_models": primary_share_path,
        "primary_share_two_way_cluster_models": primary_share_two_way_path,
        "primary_share_fama_macbeth_models": primary_share_fama_macbeth_path,
        "primary_export_share_diagnostics": primary_diagnostics_path,
        "primary_product_hs6_mapping": primary_mapping_path,
        "us_population_counterfactuals": us_counterfactual_path,
        "yearly_slopes": yearly_path,
        "sample_diagnostics": diagnostics_path,
        "missing_controls": missing_path,
        "figures": figure_paths,
        "memo": memo_path,
        "manifest": manifest_path,
    }
    write_memo(
        memo_path,
        args,
        diagnostics,
        main_models,
        robustness,
        two_way,
        fama_macbeth,
        gmm_models,
        gmm_first_stage,
        primary_share,
        primary_share_two_way,
        primary_share_fama_macbeth,
        primary_diagnostics,
        yearly,
        output_paths,
    )
    write_manifest(
        manifest_path,
        args,
        panel,
        main_models,
        robustness,
        two_way,
        fama_macbeth,
        gmm_models,
        gmm_first_stage,
        primary_share,
        primary_share_two_way,
        primary_share_fama_macbeth,
        yearly,
        output_paths,
    )
    print(f"Wrote {rel(memo_path)}")
    print(f"Wrote {rel(main_path)}")
    print(f"Wrote {rel(robustness_path)}")
    print(f"Wrote {rel(two_way_path)}")
    print(f"Wrote {rel(gmm_path)}")
    print(f"Wrote {rel(gmm_first_stage_path)}")
    print(f"Wrote {rel(fama_macbeth_path)}")
    print(f"Wrote {rel(primary_share_path)}")
    print(f"Wrote {rel(primary_share_two_way_path)}")
    print(f"Wrote {rel(primary_share_fama_macbeth_path)}")
    print(f"Wrote {rel(yearly_path)}")
    print(f"Wrote {rel(us_counterfactual_path)}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country-sample", choices=COUNTRY_SAMPLE_CHOICES, default="rd2_countries")
    parser.add_argument("--start-year", type=int, default=1988)
    parser.add_argument("--end-year", type=int, default=2024)
    parser.add_argument("--refresh-controls", action="store_true")
    parser.add_argument("--min-year-countries", type=int, default=15)
    parser.add_argument("--primary-share-control", choices=PRIMARY_SHARE_CONTROL_CHOICES, default="both")
    args = parser.parse_args(argv)
    if args.end_year < args.start_year:
        parser.error("--end-year must be greater than or equal to --start-year")
    if args.min_year_countries < 3:
        parser.error("--min-year-countries must be at least 3")
    return args


def main(argv: list[str] | None = None) -> None:
    run(parse_args(argv))


if __name__ == "__main__":
    main()
