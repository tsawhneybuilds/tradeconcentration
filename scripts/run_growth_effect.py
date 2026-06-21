#!/usr/bin/env python3
"""Descriptive export-growth and trade-concentration panel exercise."""

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
from scipy.stats import t as student_t

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_country_size_effect as cse  # noqa: E402
from trade_concentration_pipeline import sample_processed_path, sample_results_dir  # noqa: E402

COUNTRY_SAMPLE_CHOICES = ("rd2_countries",)
FLOWS = cse.FLOWS
OUTCOME_SPECS = cse.OUTCOME_SPECS
DEFAULT_HORIZONS = (1, 5, 10)
PRIMARY_TERM = "prior_export_growth"
LEVEL_TERM = "lag_log_real_exports"
POP_TERM = "lag_log_population"
CONTEMPORANEOUS_TERM = "contemporaneous_export_growth"
FUTURE_TERM = "future_export_growth"
WORLD_BANK_URL = "https://api.worldbank.org/v2/country/{countries}/indicator/{indicator}"
WORLD_BANK_EXPORTS_INDICATOR = "NE.EXP.GNFS.KD"
WORLD_BANK_EXPORTS_LABEL = "Exports of goods and services, constant 2015 US$"
WORLD_BANK_POPULATION_INDICATOR = "SP.POP.TOTL"
COUNTRY_METADATA = ROOT / "data" / "raw" / "world_bank_gdp" / "country_metadata.csv"
EXPORT_BIN_LABELS = ("low", "middle", "high")
EXPORT_BIN_SLOPE_TERMS = {
    "low": "prior_export_growth_low",
    "middle": "prior_export_growth_middle",
    "high": "prior_export_growth_high",
}
EXPORT_BIN_DUMMY_TERMS = {
    "middle": "export_level_bin_middle",
    "high": "export_level_bin_high",
}
THRESHOLD_GRID = tuple(range(30, 71, 5))


class ExportGrowthCoverageError(RuntimeError):
    pass


def normalize_horizons(horizons: Iterable[int]) -> list[int]:
    out = sorted({int(horizon) for horizon in horizons})
    if not out or any(horizon < 1 for horizon in out):
        raise ValueError("Horizons must be positive integers.")
    return out


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def ensure_dirs(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def validate_unique_keys(df: pd.DataFrame, keys: list[str], label: str) -> None:
    missing = [col for col in keys if col not in df.columns]
    if missing:
        raise RuntimeError(f"{label} is missing key columns: {missing}")
    dupes = int(df.duplicated(keys).sum())
    if dupes:
        examples = df[df.duplicated(keys, keep=False)][keys].head(5).to_dict(orient="records")
        raise RuntimeError(f"{label} has {dupes:,} duplicate rows on {keys}. Examples: {examples}")


def read_csv_if_exists(path: Path, required: Iterable[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=list(required))
    data = pd.read_csv(path)
    missing = [col for col in required if col not in data.columns]
    if missing:
        return pd.DataFrame(columns=list(required))
    return data[list(required)].copy()


def fetch_world_bank_indicator(
    iso3s: list[str], indicator: str, value_name: str, start_year: int, end_year: int
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    countries = ";".join(sorted(set(iso3s)))
    url = WORLD_BANK_URL.format(countries=countries, indicator=indicator)
    page = 1
    pages = 1
    while page <= pages:
        response = requests.get(
            url,
            params={"format": "json", "per_page": 20000, "page": page, "date": f"{start_year}:{end_year}"},
            timeout=45,
        )
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


def complete_control_share(controls: pd.DataFrame, keys: pd.DataFrame) -> float:
    required = keys.merge(controls, on=["iso3", "year"], how="left")
    complete = required[["real_exports_constant_2015_usd", "population"]].notna().all(axis=1)
    return float(complete.mean()) if len(complete) else 0.0


def load_or_fetch_world_bank_export_controls(
    iso3s: list[str],
    requested_keys: pd.DataFrame,
    start_year: int,
    end_year: int,
    cache_path: Path,
    refresh: bool = False,
) -> pd.DataFrame:
    columns = ["iso3", "year", "real_exports_constant_2015_usd", "population"]
    requested_keys = requested_keys[["iso3", "year"]].drop_duplicates().copy()
    requested_keys["iso3"] = requested_keys["iso3"].astype(str).str.upper()
    requested_keys["year"] = requested_keys["year"].astype(int)
    controls = read_csv_if_exists(cache_path, columns) if cache_path.exists() and not refresh else pd.DataFrame(columns=columns)
    if controls.empty or refresh or complete_control_share(controls, requested_keys) < 0.95:
        base = pd.DataFrame(
            [(iso3, year) for iso3 in sorted(set(iso3s)) for year in range(start_year, end_year + 1)],
            columns=["iso3", "year"],
        )
        frames: dict[str, list[pd.DataFrame]] = {"real_exports_constant_2015_usd": [], "population": []}
        if not controls.empty:
            for value_name in frames:
                if value_name in controls.columns:
                    frames[value_name].append(controls[["iso3", "year", value_name]])
        try:
            frames["real_exports_constant_2015_usd"].append(
                fetch_world_bank_indicator(
                    iso3s, WORLD_BANK_EXPORTS_INDICATOR, "real_exports_constant_2015_usd", start_year, end_year
                )
            )
            frames["population"].append(
                fetch_world_bank_indicator(iso3s, WORLD_BANK_POPULATION_INDICATOR, "population", start_year, end_year)
            )
        except Exception as exc:
            print(f"World Bank refresh warning: {exc}", file=sys.stderr)
        controls = base.copy()
        for value_name, value_frames in frames.items():
            value_frames = [frame[["iso3", "year", value_name]] for frame in value_frames if value_name in frame.columns]
            if not value_frames:
                continue
            combined = pd.concat(value_frames, ignore_index=True)
            combined["iso3"] = combined["iso3"].astype(str).str.upper()
            combined["year"] = pd.to_numeric(combined["year"], errors="coerce")
            combined[value_name] = pd.to_numeric(combined[value_name], errors="coerce")
            combined = (
                combined.dropna(subset=["iso3", "year"])
                .sort_values(["iso3", "year", value_name], na_position="first")
                .drop_duplicates(["iso3", "year"], keep="last")
            )
            controls = controls.merge(combined, on=["iso3", "year"], how="left")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        controls.to_csv(cache_path, index=False)
    controls["iso3"] = controls["iso3"].astype(str).str.upper()
    controls["year"] = pd.to_numeric(controls["year"], errors="coerce")
    for col in ["real_exports_constant_2015_usd", "population"]:
        controls[col] = pd.to_numeric(controls[col], errors="coerce")
    controls = controls.dropna(subset=["iso3", "year"]).copy()
    controls["year"] = controls["year"].astype(int)
    controls = controls.drop_duplicates(["iso3", "year"], keep="last")
    validate_unique_keys(controls, ["iso3", "year"], "World Bank export controls")
    return controls


def load_country_metadata(iso3s: list[str]) -> pd.DataFrame:
    if not COUNTRY_METADATA.exists():
        return pd.DataFrame({"iso3": sorted(set(iso3s)), "region": "Unclassified", "income_group": ""})
    metadata = pd.read_csv(COUNTRY_METADATA)
    if "iso3" not in metadata.columns or "region" not in metadata.columns:
        return pd.DataFrame({"iso3": sorted(set(iso3s)), "region": "Unclassified", "income_group": ""})
    keep = ["iso3", "region"] + (["income_group"] if "income_group" in metadata.columns else [])
    metadata = metadata[keep].copy()
    metadata["iso3"] = metadata["iso3"].astype(str).str.upper()
    metadata["region"] = metadata["region"].fillna("Unclassified").astype(str)
    if "income_group" not in metadata.columns:
        metadata["income_group"] = ""
    return metadata.drop_duplicates(["iso3"], keep="last")


def load_concentration_panel(country_sample: str, start_year: int, end_year: int) -> pd.DataFrame:
    path = sample_processed_path("concentration_all_years.parquet", country_sample)
    if not path.exists():
        raise FileNotFoundError(f"Missing concentration panel: {path}")
    panel = pd.read_parquet(path)
    needed = {"country", "iso3", "reporter_code", "year", "flow", "variant", *[spec[2] for spec in OUTCOME_SPECS]}
    missing = sorted(needed - set(panel.columns))
    if missing:
        raise RuntimeError(f"Concentration panel is missing required columns: {missing}")
    panel = panel[panel["variant"].eq("baseline") & panel["year"].between(start_year, end_year)].copy()
    validate_unique_keys(panel, ["iso3", "reporter_code", "year", "flow", "variant"], "concentration panel")
    for _dimension, _metric, col, _label in OUTCOME_SPECS:
        values = pd.to_numeric(panel[col], errors="coerce")
        bad = values.notna() & ((values < 0) | (values > 1))
        if bool(bad.any()):
            raise RuntimeError(f"Outcome {col} has {int(bad.sum()):,} finite values outside [0, 1].")
    return panel


def core_growth_required_columns() -> list[str]:
    return [
        "lag_real_exports_constant_2015_usd",
        "lag2_real_exports_constant_2015_usd",
        "lag_population",
        PRIMARY_TERM,
        LEVEL_TERM,
        POP_TERM,
    ]


def add_common_horizon_support(panel: pd.DataFrame, horizons: Iterable[int]) -> pd.DataFrame:
    requested = normalize_horizons(horizons)
    out = panel.copy()
    required = core_growth_required_columns()
    out["core_growth_complete"] = out[required].replace([np.inf, -np.inf], np.nan).notna().all(axis=1)
    key = ["iso3", "reporter_code", "base_year", "flow", "variant"]
    complete_horizons = out.loc[out["core_growth_complete"], key + ["horizon"]].drop_duplicates()
    support = (
        complete_horizons.groupby(key, dropna=False)["horizon"]
        .agg(
            available_horizons_for_base=lambda values: len(set(pd.to_numeric(values, errors="coerce").dropna().astype(int))),
            available_horizon_list=lambda values: ",".join(str(value) for value in sorted(set(pd.to_numeric(values, errors="coerce").dropna().astype(int)))),
        )
        .reset_index()
    )
    out = out.merge(support, on=key, how="left", validate="many_to_one")
    out["available_horizons_for_base"] = pd.to_numeric(out["available_horizons_for_base"], errors="coerce").fillna(0).astype(int)
    out["available_horizon_list"] = out["available_horizon_list"].fillna("").astype(str)
    out["requested_horizon_list"] = ",".join(str(horizon) for horizon in requested)
    out["common_horizon_support"] = out["available_horizons_for_base"].eq(len(requested))
    return out


def construct_lagged_export_variables(
    concentration: pd.DataFrame, controls: pd.DataFrame, horizons: Iterable[int] = (1,)
) -> pd.DataFrame:
    validate_unique_keys(concentration, ["iso3", "reporter_code", "year", "flow", "variant"], "concentration panel")
    validate_unique_keys(controls, ["iso3", "year"], "World Bank export controls")
    horizons = normalize_horizons(horizons)
    cy = controls.copy()
    cy["iso3"] = cy["iso3"].astype(str).str.upper()
    cy["year"] = pd.to_numeric(cy["year"], errors="coerce").astype("Int64")
    for col in ["real_exports_constant_2015_usd", "population"]:
        cy[col] = pd.to_numeric(cy[col], errors="coerce")
    cy = cy.dropna(subset=["iso3", "year"]).copy()
    cy["year"] = cy["year"].astype(int)
    cy["log_real_exports"] = np.where(cy["real_exports_constant_2015_usd"] > 0, np.log(cy["real_exports_constant_2015_usd"]), np.nan)
    cy["log_population"] = np.where(cy["population"] > 0, np.log(cy["population"]), np.nan)

    base = cy[["iso3", "year", "real_exports_constant_2015_usd", "population", "log_real_exports", "log_population"]].copy()
    base = base.rename(
        columns={
            "year": "base_year",
            "real_exports_constant_2015_usd": "lag_real_exports_constant_2015_usd",
            "population": "lag_population",
            "log_real_exports": LEVEL_TERM,
            "log_population": POP_TERM,
        }
    )
    previous = cy[["iso3", "year", "real_exports_constant_2015_usd", "log_real_exports"]].copy()
    previous["year"] += 1
    previous = previous.rename(
        columns={"real_exports_constant_2015_usd": "lag2_real_exports_constant_2015_usd", "log_real_exports": "lag2_log_real_exports"}
    )
    previous = previous.rename(columns={"year": "base_year"})
    outcome_controls = cy[["iso3", "year", "real_exports_constant_2015_usd", "log_real_exports"]].rename(
        columns={
            "year": "outcome_year",
            "real_exports_constant_2015_usd": "current_real_exports_constant_2015_usd",
            "log_real_exports": "current_log_real_exports",
        }
    )
    future = cy[["iso3", "year", "real_exports_constant_2015_usd", "log_real_exports"]].copy()
    future["year"] -= 1
    future = future.rename(
        columns={
            "year": "outcome_year",
            "real_exports_constant_2015_usd": "future_real_exports_constant_2015_usd",
            "log_real_exports": "future_log_real_exports",
        }
    )
    frames: list[pd.DataFrame] = []
    for horizon in horizons:
        work = concentration.copy()
        work["outcome_year"] = pd.to_numeric(work["year"], errors="coerce").astype("Int64")
        work["horizon"] = int(horizon)
        work["base_year"] = work["outcome_year"] - int(horizon)
        work["prior_growth_start_year"] = work["base_year"] - 1
        work["prior_growth_end_year"] = work["base_year"]
        work = work.dropna(subset=["outcome_year", "base_year"]).copy()
        work["outcome_year"] = work["outcome_year"].astype(int)
        work["base_year"] = work["base_year"].astype(int)
        work["prior_growth_start_year"] = work["prior_growth_start_year"].astype(int)
        work["prior_growth_end_year"] = work["prior_growth_end_year"].astype(int)
        work = work.merge(base, on=["iso3", "base_year"], how="left", validate="many_to_one")
        work = work.merge(previous, on=["iso3", "base_year"], how="left", validate="many_to_one")
        work = work.merge(outcome_controls, on=["iso3", "outcome_year"], how="left", validate="many_to_one")
        work = work.merge(future, on=["iso3", "outcome_year"], how="left", validate="many_to_one")
        work[PRIMARY_TERM] = work[LEVEL_TERM] - work["lag2_log_real_exports"]
        work[CONTEMPORANEOUS_TERM] = (work["current_log_real_exports"] - work[LEVEL_TERM]) / float(horizon)
        work[FUTURE_TERM] = work["future_log_real_exports"] - work["current_log_real_exports"]
        frames.append(work)
    panel = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return add_common_horizon_support(panel, horizons)


def build_growth_panel(args: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    horizons = normalize_horizons(args.horizons)
    concentration = load_concentration_panel(args.country_sample, args.start_year, args.end_year)
    iso3s = sorted(concentration["iso3"].dropna().astype(str).str.upper().unique())
    controls_start = args.start_year - max(horizons) - 1
    controls_end = args.end_year + 1
    keys = pd.DataFrame([(iso3, year) for iso3 in iso3s for year in range(controls_start, controls_end + 1)], columns=["iso3", "year"])
    controls = load_or_fetch_world_bank_export_controls(
        iso3s,
        keys,
        controls_start,
        controls_end,
        sample_processed_path("growth_effect_world_bank_export_controls.csv", args.country_sample),
        refresh=args.refresh_controls,
    )
    panel = construct_lagged_export_variables(concentration, controls, horizons=horizons)
    panel = panel.merge(load_country_metadata(iso3s), on="iso3", how="left", validate="many_to_one")
    panel["region"] = panel["region"].fillna("Unclassified").astype(str)
    panel["region_year"] = panel["region"] + "::" + panel["year"].astype(str)
    panel["base_region_year"] = panel["region"] + "::" + panel["base_year"].astype(str)
    required = core_growth_required_columns()
    missing_or_unmatched = panel[required].isna().any(axis=1)
    if args.match_horizon_sample:
        missing_or_unmatched = missing_or_unmatched | ~panel["common_horizon_support"].astype(bool)
    missing_controls = panel.loc[missing_or_unmatched, :].copy()
    missing_controls["missing_reason"] = np.select(
        [
            missing_controls[required].isna().any(axis=1),
            ~missing_controls["common_horizon_support"].astype(bool),
        ],
        ["missing_world_bank_growth_controls", "not_on_common_horizon_support"],
        default="",
    )
    missing_controls = missing_controls[
        [
            "country",
            "iso3",
            "reporter_code",
            "year",
            "outcome_year",
            "base_year",
            "horizon",
            "flow",
            "lag_real_exports_constant_2015_usd",
            "lag2_real_exports_constant_2015_usd",
            "current_real_exports_constant_2015_usd",
            "future_real_exports_constant_2015_usd",
            "lag_population",
            "core_growth_complete",
            "common_horizon_support",
            "available_horizon_list",
            "missing_reason",
        ]
    ].copy()
    return panel, controls, missing_controls


def analysis_sample(panel: pd.DataFrame, match_horizon_sample: bool = True) -> pd.DataFrame:
    if not match_horizon_sample or "common_horizon_support" not in panel.columns:
        return panel.copy()
    return panel[panel["common_horizon_support"].astype(bool)].copy()


def export_growth_coverage(panel: pd.DataFrame, match_horizon_sample: bool = True) -> dict[str, float | int]:
    panel = panel.copy()
    if "horizon" not in panel.columns:
        panel["horizon"] = 1
    if "base_year" not in panel.columns and "year" in panel.columns:
        panel["base_year"] = pd.to_numeric(panel["year"], errors="coerce") - 1
    unique_cols = ["iso3", "base_year", "horizon", PRIMARY_TERM, LEVEL_TERM, POP_TERM, "common_horizon_support"]
    present_cols = [col for col in unique_cols if col in panel.columns]
    unique = panel[present_cols].drop_duplicates([col for col in ["iso3", "base_year", "horizon"] if col in panel.columns]).copy()
    complete = unique[[PRIMARY_TERM, LEVEL_TERM, POP_TERM]].replace([np.inf, -np.inf], np.nan).notna().all(axis=1)
    if match_horizon_sample and "common_horizon_support" in unique.columns:
        usable = complete & unique["common_horizon_support"].astype(bool)
    else:
        usable = complete
    return {
        "candidate_country_years": int(len(unique)),
        "usable_country_years": int(usable.sum()),
        "usable_country_year_share": float(usable.mean()) if len(unique) else 0.0,
        "usable_country_clusters": int(unique.loc[usable, "iso3"].nunique()),
    }


def enforce_export_growth_coverage(panel: pd.DataFrame, args: argparse.Namespace) -> str:
    match_horizon_sample = bool(getattr(args, "match_horizon_sample", True))
    coverage = export_growth_coverage(panel, match_horizon_sample=match_horizon_sample)
    horizon_coverage = horizon_coverage_rows(panel, match_horizon_sample=match_horizon_sample)
    ok_rows = horizon_coverage[horizon_coverage["usable_country_years"].gt(0)].copy()
    min_share = float(ok_rows["usable_country_year_share"].min()) if not ok_rows.empty else 0.0
    min_clusters = int(ok_rows["usable_country_clusters"].min()) if not ok_rows.empty else 0
    share = float(coverage["usable_country_year_share"])
    clusters = int(coverage["usable_country_clusters"])
    if min_clusters < args.min_clusters or min_share < args.min_coverage:
        raise ExportGrowthCoverageError(
            "World Bank real-export controls or common-horizon support are too incomplete: "
            f"minimum across horizons is {min_clusters} clusters and {min_share:.1%} usable country-years."
        )
    return "coverage_limited" if share < args.coverage_limited_threshold else "standard_coverage"


def horizon_coverage_rows(panel: pd.DataFrame, match_horizon_sample: bool = True) -> pd.DataFrame:
    panel = panel.copy()
    if "horizon" not in panel.columns:
        panel["horizon"] = 1
    if "base_year" not in panel.columns and "year" in panel.columns:
        panel["base_year"] = pd.to_numeric(panel["year"], errors="coerce") - 1
    required = [PRIMARY_TERM, LEVEL_TERM, POP_TERM]
    rows: list[dict[str, Any]] = []
    key = ["iso3", "base_year", "horizon"]
    unique = panel.drop_duplicates([col for col in key if col in panel.columns]).copy()
    for horizon, group in unique.groupby("horizon", sort=True):
        complete = group[required].replace([np.inf, -np.inf], np.nan).notna().all(axis=1)
        if match_horizon_sample and "common_horizon_support" in group.columns:
            usable = complete & group["common_horizon_support"].astype(bool)
        else:
            usable = complete
        rows.append(
            {
                "horizon": int(horizon),
                "candidate_country_years": int(len(group)),
                "core_complete_country_years": int(complete.sum()),
                "usable_country_years": int(usable.sum()),
                "usable_country_year_share": float(usable.mean()) if len(group) else 0.0,
                "usable_country_clusters": int(group.loc[usable, "iso3"].nunique()),
                "first_base_year": int(pd.to_numeric(group.loc[usable, "base_year"], errors="coerce").min()) if bool(usable.any()) else np.nan,
                "last_base_year": int(pd.to_numeric(group.loc[usable, "base_year"], errors="coerce").max()) if bool(usable.any()) else np.nan,
                "first_outcome_year": int(pd.to_numeric(group.loc[usable, "year"], errors="coerce").min()) if bool(usable.any()) else np.nan,
                "last_outcome_year": int(pd.to_numeric(group.loc[usable, "year"], errors="coerce").max()) if bool(usable.any()) else np.nan,
            }
        )
    return pd.DataFrame(rows)


def p_value_from_coef(coef: float, se: float, df: float) -> tuple[float, float, float, float]:
    t_stat = coef / se if np.isfinite(coef) and np.isfinite(se) and se > 0 else np.nan
    p_value = 2 * student_t.sf(abs(t_stat), df) if np.isfinite(t_stat) and np.isfinite(df) else np.nan
    critical = student_t.ppf(0.975, df) if np.isfinite(df) else np.nan
    ci_low = coef - critical * se if np.isfinite(coef) and np.isfinite(se) and np.isfinite(critical) else np.nan
    ci_high = coef + critical * se if np.isfinite(coef) and np.isfinite(se) and np.isfinite(critical) else np.nan
    return float(t_stat) if np.isfinite(t_stat) else np.nan, float(p_value) if np.isfinite(p_value) else np.nan, ci_low, ci_high


def linear_combo_from_model(
    df: pd.DataFrame,
    outcome: str,
    terms: list[str],
    fixed_effects: list[str],
    weights: dict[str, float],
    cluster_col: str = "reporter_code",
) -> tuple[float, float, float, float, float]:
    required = list(dict.fromkeys([outcome, *terms, *fixed_effects, cluster_col]))
    missing = [col for col in required if col not in df.columns]
    if missing:
        return np.nan, np.nan, np.nan, np.nan, np.nan
    work = df.replace([np.inf, -np.inf], np.nan).dropna(subset=required).copy()
    if len(work) < len(terms) + 3:
        return np.nan, np.nan, np.nan, np.nan, np.nan
    x_df, _dropped = cse.design_matrix(work, terms, fixed_effects)
    combo_terms = [term for term in weights if term in x_df.columns]
    if set(combo_terms) != set(weights):
        return np.nan, np.nan, np.nan, np.nan, np.nan
    if x_df.shape[0] <= x_df.shape[1]:
        return np.nan, np.nan, np.nan, np.nan, np.nan
    y = pd.to_numeric(work[outcome], errors="coerce").to_numpy(dtype=float)
    x = x_df.to_numpy(dtype=float)
    beta_all, *_ = np.linalg.lstsq(x, y, rcond=None)
    resid = y - x @ beta_all
    clusters = int(work[cluster_col].nunique())
    if clusters <= 1:
        return np.nan, np.nan, np.nan, np.nan, np.nan
    cov = cse.cluster_robust_covariance(x, resid, work[cluster_col])
    cov_df = pd.DataFrame(cov, index=x_df.columns, columns=x_df.columns)
    coef = float(sum(weights[term] * beta_all[x_df.columns.get_loc(term)] for term in combo_terms))
    w = np.array([weights[term] for term in combo_terms], dtype=float)
    variance = float(w @ cov_df.loc[combo_terms, combo_terms].to_numpy(dtype=float) @ w)
    se = math.sqrt(max(variance, 0.0)) if np.isfinite(variance) else np.nan
    t_stat, p_value, ci_low, ci_high = p_value_from_coef(coef, se, float(clusters - 1))
    return coef, se, p_value, ci_low, ci_high


def add_q_values(models: pd.DataFrame, term_by_model: dict[str, str]) -> pd.DataFrame:
    out = models.copy()
    out["bh_q_value"] = np.nan
    for model_label, term in term_by_model.items():
        mask = out["model_label"].eq(model_label) & out["term"].eq(term) & out["status"].eq("ok")
        out.loc[mask, "bh_q_value"] = cse.benjamini_hochberg(out.loc[mask, "p_value"])
    return out


def attach_horizon(frame: pd.DataFrame, horizon: int) -> pd.DataFrame:
    out = frame.copy()
    out.insert(2, "horizon", int(horizon))
    return out


def run_main_models(panel: pd.DataFrame, country_sample: str, horizons: Iterable[int]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for horizon in normalize_horizons(horizons):
        results: list[cse.ModelResult] = []
        horizon_panel = panel[panel["horizon"].eq(horizon)].copy()
        for flow in FLOWS:
            flow_panel = horizon_panel[horizon_panel["flow"].eq(flow)].copy()
            for dimension, metric, outcome, _label in OUTCOME_SPECS:
                results.append(
                    cse.run_ols_model(
                        flow_panel,
                        outcome,
                        [PRIMARY_TERM, LEVEL_TERM, POP_TERM],
                        ["reporter_code", "base_year"],
                        "main_lagged_export_growth",
                        country_sample,
                        flow,
                        dimension,
                        metric,
                        cluster_col="reporter_code",
                    )
                )
        frames.append(attach_horizon(cse.model_results_to_frame(results), horizon))
    models = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return add_q_values(models, {"main_lagged_export_growth": PRIMARY_TERM})


def run_sample_comparison_models(
    broad_panel: pd.DataFrame, balanced_panel: pd.DataFrame, country_sample: str, horizons: Iterable[int]
) -> pd.DataFrame:
    samples = [
        (
            "balanced_common_horizon_sample",
            balanced_panel,
            "Balanced/common horizon support: country-flow-base-year rows must have all requested horizons.",
        ),
        (
            "broad_available_horizon_sample",
            broad_panel,
            "Broad available sample: each horizon uses all rows with that horizon outcome and complete controls.",
        ),
    ]
    frames: list[pd.DataFrame] = []
    term_by_model: dict[str, str] = {}
    for model_label, sample_panel, sample_definition in samples:
        term_by_model[model_label] = PRIMARY_TERM
        for horizon in normalize_horizons(horizons):
            results: list[cse.ModelResult] = []
            horizon_panel = sample_panel[sample_panel["horizon"].eq(horizon)].copy()
            for flow in FLOWS:
                flow_panel = horizon_panel[horizon_panel["flow"].eq(flow)].copy()
                for dimension, metric, outcome, _label in OUTCOME_SPECS:
                    results.append(
                        cse.run_ols_model(
                            flow_panel,
                            outcome,
                            [PRIMARY_TERM, LEVEL_TERM, POP_TERM],
                            ["reporter_code", "base_year"],
                            model_label,
                            country_sample,
                            flow,
                            dimension,
                            metric,
                            cluster_col="reporter_code",
                        )
                    )
            frame = attach_horizon(cse.model_results_to_frame(results), horizon)
            frame.insert(3, "sample_definition", sample_definition)
            frames.append(frame)
    models = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return add_q_values(models, term_by_model)


def run_robustness_models(panel: pd.DataFrame, country_sample: str, horizons: Iterable[int]) -> pd.DataFrame:
    specs = [
        ("two_way_country_year_cluster", PRIMARY_TERM, [PRIMARY_TERM, LEVEL_TERM, POP_TERM], ["reporter_code", "base_year"], "base_year"),
        ("contemporaneous_export_growth", CONTEMPORANEOUS_TERM, [CONTEMPORANEOUS_TERM, LEVEL_TERM, POP_TERM], ["reporter_code", "base_year"], None),
        ("future_export_growth_placebo", FUTURE_TERM, [FUTURE_TERM, LEVEL_TERM, POP_TERM], ["reporter_code", "base_year"], None),
        ("region_year_fe", PRIMARY_TERM, [PRIMARY_TERM, LEVEL_TERM, POP_TERM], ["reporter_code", "base_region_year"], None),
    ]
    frames: list[pd.DataFrame] = []
    term_by_model: dict[str, str] = {}
    for horizon in normalize_horizons(horizons):
        results: list[cse.ModelResult] = []
        horizon_panel = panel[panel["horizon"].eq(horizon)].copy()
        for flow in FLOWS:
            flow_panel = horizon_panel[horizon_panel["flow"].eq(flow)].copy()
            for dimension, metric, outcome, _label in OUTCOME_SPECS:
                for label, term, terms, fixed_effects, two_way in specs:
                    term_by_model[label] = term
                    results.append(
                        cse.run_ols_model(
                            flow_panel,
                            outcome,
                            terms,
                            fixed_effects,
                            label,
                            country_sample,
                            flow,
                            dimension,
                            metric,
                            cluster_col="reporter_code",
                            two_way_cluster_col=two_way,
                        )
                    )
        frames.append(attach_horizon(cse.model_results_to_frame(results), horizon))
    models = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return add_q_values(models, term_by_model)


def export_level_cutoffs(panel: pd.DataFrame) -> dict[str, float]:
    unique = (
        panel[["iso3", "base_year", PRIMARY_TERM, LEVEL_TERM, POP_TERM]]
        .drop_duplicates(["iso3", "base_year"])
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )
    q1, q2 = np.nanquantile(unique[LEVEL_TERM].to_numpy(dtype=float), [1 / 3, 2 / 3])
    if not q1 < q2:
        raise RuntimeError("Lagged real export levels do not have enough variation to form terciles.")
    return {
        "low_middle_log_cutoff": float(q1),
        "middle_high_log_cutoff": float(q2),
        "low_middle_export_cutoff": float(np.exp(q1)),
        "middle_high_export_cutoff": float(np.exp(q2)),
    }


def add_export_level_bins(panel: pd.DataFrame, cutoffs: dict[str, float] | None = None) -> tuple[pd.DataFrame, dict[str, float]]:
    cutoffs = cutoffs or export_level_cutoffs(panel)
    out = panel.copy()
    out["export_level_bin"] = pd.cut(
        pd.to_numeric(out[LEVEL_TERM], errors="coerce"),
        [-np.inf, cutoffs["low_middle_log_cutoff"], cutoffs["middle_high_log_cutoff"], np.inf],
        labels=list(EXPORT_BIN_LABELS),
        include_lowest=True,
    ).astype("string")
    for label, term in EXPORT_BIN_SLOPE_TERMS.items():
        out[term] = pd.to_numeric(out[PRIMARY_TERM], errors="coerce") * out["export_level_bin"].eq(label).astype(float)
    for label, term in EXPORT_BIN_DUMMY_TERMS.items():
        out[term] = out["export_level_bin"].eq(label).astype(float)
    return out, cutoffs


def result_term(result: cse.ModelResult, term: str) -> tuple[float, float]:
    if term not in result.terms:
        return np.nan, np.nan
    idx = result.terms.index(term)
    return float(result.beta[idx]), float(result.se[idx])


def slope_rows_from_result(
    result: cse.ModelResult,
    cutoffs: dict[str, float],
    fit_data: pd.DataFrame,
    terms: list[str],
    fixed_effects: list[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for label, term in EXPORT_BIN_SLOPE_TERMS.items():
        coef, se, p_value, ci_low, ci_high = linear_combo_from_model(
            fit_data, result.outcome, terms, fixed_effects, {term: 1.0}
        )
        t_stat = coef / se if np.isfinite(coef) and np.isfinite(se) and se > 0 else np.nan
        rows.append(
            {
                "model_label": result.model_label,
                "sample": result.sample,
                "flow": result.flow,
                "dimension": result.dimension,
                "metric": result.metric,
                "outcome": result.outcome,
                "row_type": "slope",
                "label": label,
                "export_level_bin": label,
                "term": term,
                "coefficient": coef,
                "std_error": se,
                "t_stat": t_stat,
                "p_value": p_value,
                "ci_low": ci_low,
                "ci_high": ci_high,
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
                "low_middle_export_cutoff": cutoffs["low_middle_export_cutoff"],
                "middle_high_export_cutoff": cutoffs["middle_high_export_cutoff"],
            }
        )
    coef, se, p_value, ci_low, ci_high = linear_combo_from_model(
        fit_data,
        result.outcome,
        terms,
        fixed_effects,
        {EXPORT_BIN_SLOPE_TERMS["high"]: 1.0, EXPORT_BIN_SLOPE_TERMS["low"]: -1.0},
    )
    t_stat = coef / se if np.isfinite(coef) and np.isfinite(se) and se > 0 else np.nan
    rows.append(
        {
            **rows[0],
            "row_type": "difference",
            "label": "high_minus_low",
            "export_level_bin": "high_minus_low",
            "term": "high_minus_low_growth_slope",
            "coefficient": coef,
            "std_error": se,
            "t_stat": t_stat,
            "p_value": p_value,
            "ci_low": ci_low,
            "ci_high": ci_high,
        }
    )
    return rows


def run_income_bin_slopes(panel: pd.DataFrame, country_sample: str, horizons: Iterable[int]) -> tuple[pd.DataFrame, dict[str, float]]:
    binned, cutoffs = add_export_level_bins(panel)
    terms = [
        EXPORT_BIN_SLOPE_TERMS["low"],
        EXPORT_BIN_SLOPE_TERMS["middle"],
        EXPORT_BIN_SLOPE_TERMS["high"],
        EXPORT_BIN_DUMMY_TERMS["middle"],
        EXPORT_BIN_DUMMY_TERMS["high"],
        LEVEL_TERM,
        POP_TERM,
    ]
    rows: list[dict[str, Any]] = []
    for horizon in normalize_horizons(horizons):
        horizon_panel = binned[binned["horizon"].eq(horizon)].copy()
        for flow in FLOWS:
            flow_panel = horizon_panel[horizon_panel["flow"].eq(flow)].copy()
            for dimension, metric, outcome, _label in OUTCOME_SPECS:
                result = cse.run_ols_model(
                    flow_panel,
                    outcome,
                    terms,
                    ["reporter_code", "base_year"],
                    "growth_by_lagged_export_level_tercile",
                    country_sample,
                    flow,
                    dimension,
                    metric,
                    cluster_col="reporter_code",
                )
                for row in slope_rows_from_result(result, cutoffs, flow_panel, terms, ["reporter_code", "base_year"]):
                    row["horizon"] = int(horizon)
                    rows.append(row)
    out = pd.DataFrame(rows)
    out["bh_q_value"] = np.nan
    slope_mask = out["row_type"].eq("slope") & out["status"].eq("ok")
    diff_mask = out["row_type"].eq("difference") & out["status"].eq("ok")
    out.loc[slope_mask, "bh_q_value"] = cse.benjamini_hochberg(out.loc[slope_mask, "p_value"])
    out.loc[diff_mask, "bh_q_value"] = cse.benjamini_hochberg(out.loc[diff_mask, "p_value"])
    out["leveling_off_supported"] = False
    for _keys, group in out.groupby(["horizon", "flow", "dimension", "metric", "outcome"], sort=False):
        slopes = group[group["row_type"].eq("slope")].set_index("export_level_bin")
        diff = group[group["row_type"].eq("difference")]
        if {"low", "high"}.issubset(slopes.index) and not diff.empty:
            low = float(slopes.loc["low", "coefficient"])
            high = float(slopes.loc["high", "coefficient"])
            q = out.loc[diff.index[0], "bh_q_value"]
            out.loc[diff.index[0], "leveling_off_supported"] = np.isfinite(low) and np.isfinite(high) and abs(high) < abs(low) and np.isfinite(q) and float(q) <= 0.10
    return out, cutoffs


def add_threshold_terms(panel: pd.DataFrame, cutoff_log_exports: float) -> pd.DataFrame:
    out = panel.copy()
    high = pd.to_numeric(out[LEVEL_TERM], errors="coerce") >= cutoff_log_exports
    out["above_threshold"] = high.astype(float)
    out["prior_export_growth_below_threshold"] = pd.to_numeric(out[PRIMARY_TERM], errors="coerce") * (~high).astype(float)
    out["prior_export_growth_above_threshold"] = pd.to_numeric(out[PRIMARY_TERM], errors="coerce") * high.astype(float)
    return out


def threshold_rows_from_result(
    result: cse.ModelResult,
    percentile: int,
    cutoff_log: float,
    fit_data: pd.DataFrame,
    terms: list[str],
    fixed_effects: list[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for term, label in [
        ("prior_export_growth_below_threshold", "below_threshold"),
        ("prior_export_growth_above_threshold", "above_threshold"),
    ]:
        coef, se, p_value, ci_low, ci_high = linear_combo_from_model(
            fit_data, result.outcome, terms, fixed_effects, {term: 1.0}
        )
        t_stat = coef / se if np.isfinite(coef) and np.isfinite(se) and se > 0 else np.nan
        rows.append(
            {
                "model_label": result.model_label,
                "sample": result.sample,
                "flow": result.flow,
                "dimension": result.dimension,
                "metric": result.metric,
                "outcome": result.outcome,
                "row_type": "slope",
                "label": label,
                "term": term,
                "coefficient": coef,
                "std_error": se,
                "t_stat": t_stat,
                "p_value": p_value,
                "ci_low": ci_low,
                "ci_high": ci_high,
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
                "threshold_percentile": percentile,
                "threshold_log_exports": cutoff_log,
                "threshold_exports_constant_2015_usd": float(np.exp(cutoff_log)),
                "exploratory": True,
            }
        )
    coef, se, p_value, ci_low, ci_high = linear_combo_from_model(
        fit_data,
        result.outcome,
        terms,
        fixed_effects,
        {"prior_export_growth_above_threshold": 1.0, "prior_export_growth_below_threshold": -1.0},
    )
    t_stat = coef / se if np.isfinite(coef) and np.isfinite(se) and se > 0 else np.nan
    rows.append(
        {
            **rows[0],
            "row_type": "difference",
            "label": "above_minus_below",
            "term": "above_minus_below_growth_slope",
            "coefficient": coef,
            "std_error": se,
            "t_stat": t_stat,
            "p_value": p_value,
            "ci_low": ci_low,
            "ci_high": ci_high,
        }
    )
    return rows


def run_threshold_scan(
    panel: pd.DataFrame, country_sample: str, horizons: Iterable[int], percentiles: Iterable[int] = THRESHOLD_GRID
) -> pd.DataFrame:
    unique = (
        panel[["iso3", "base_year", PRIMARY_TERM, LEVEL_TERM, POP_TERM]]
        .drop_duplicates(["iso3", "base_year"])
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )
    rows: list[dict[str, Any]] = []
    for percentile in percentiles:
        cutoff = float(np.nanpercentile(unique[LEVEL_TERM].to_numpy(dtype=float), percentile))
        work = add_threshold_terms(panel, cutoff)
        terms = ["prior_export_growth_below_threshold", "prior_export_growth_above_threshold", "above_threshold", LEVEL_TERM, POP_TERM]
        for horizon in normalize_horizons(horizons):
            horizon_panel = work[work["horizon"].eq(horizon)].copy()
            for flow in FLOWS:
                flow_panel = horizon_panel[horizon_panel["flow"].eq(flow)].copy()
                for dimension, metric, outcome, _label in OUTCOME_SPECS:
                    result = cse.run_ols_model(
                        flow_panel,
                        outcome,
                        terms,
                        ["reporter_code", "base_year"],
                        "exploratory_export_level_threshold_scan",
                        country_sample,
                        flow,
                        dimension,
                        metric,
                        cluster_col="reporter_code",
                    )
                    for row in threshold_rows_from_result(result, percentile, cutoff, flow_panel, terms, ["reporter_code", "base_year"]):
                        row["horizon"] = int(horizon)
                        rows.append(row)
    out = pd.DataFrame(rows)
    out["bh_q_value"] = np.nan
    mask = out["row_type"].eq("difference") & out["status"].eq("ok")
    out.loc[mask, "bh_q_value"] = cse.benjamini_hochberg(out.loc[mask, "p_value"])
    return out


def sample_diagnostics(
    panel: pd.DataFrame, controls: pd.DataFrame, missing_controls: pd.DataFrame, coverage_status: str, args: argparse.Namespace
) -> pd.DataFrame:
    coverage = export_growth_coverage(panel, match_horizon_sample=args.match_horizon_sample)
    horizon_coverage = horizon_coverage_rows(panel, match_horizon_sample=args.match_horizon_sample)
    rows: list[dict[str, Any]] = [
        {"diagnostic": "country_sample", "value": args.country_sample},
        {"diagnostic": "start_year", "value": args.start_year},
        {"diagnostic": "end_year", "value": args.end_year},
        {"diagnostic": "horizons", "value": ",".join(str(horizon) for horizon in normalize_horizons(args.horizons))},
        {"diagnostic": "horizon_definition", "value": "years from export-growth base year to concentration outcome year"},
        {"diagnostic": "prior_growth_definition", "value": "log(real exports in base year) minus log(real exports in base year minus one)"},
        {"diagnostic": "matched_horizon_sample", "value": bool(args.match_horizon_sample)},
        {"diagnostic": "world_bank_export_indicator", "value": WORLD_BANK_EXPORTS_INDICATOR},
        {"diagnostic": "world_bank_export_indicator_label", "value": WORLD_BANK_EXPORTS_LABEL},
        {"diagnostic": "panel_rows", "value": len(panel)},
        {"diagnostic": "analysis_panel_rows", "value": len(analysis_sample(panel, args.match_horizon_sample))},
        {"diagnostic": "countries", "value": panel["iso3"].nunique()},
        {"diagnostic": "years", "value": panel["year"].nunique()},
        {"diagnostic": "country_years", "value": coverage["candidate_country_years"]},
        {"diagnostic": "usable_country_years", "value": coverage["usable_country_years"]},
        {"diagnostic": "usable_country_year_share", "value": coverage["usable_country_year_share"]},
        {"diagnostic": "usable_country_clusters", "value": coverage["usable_country_clusters"]},
        {"diagnostic": "coverage_status", "value": coverage_status},
        {"diagnostic": "missing_control_flow_rows", "value": len(missing_controls)},
        {"diagnostic": "world_bank_control_rows", "value": len(controls)},
        {"diagnostic": "duplicate_iso3_year_flow_horizon_rows", "value": int(panel.duplicated(["iso3", "year", "flow", "horizon"]).sum())},
        {"diagnostic": "product_outcome_hs6_999999_rule", "value": "excluded upstream before product aggregation"},
        {"diagnostic": "partner_outcome_hs6_999999_rule", "value": "included by partner-total convention"},
    ]
    for flow in FLOWS:
        rows.append({"diagnostic": f"{flow.lower()}_rows", "value": int(panel["flow"].eq(flow).sum())})
    for record in horizon_coverage.to_dict(orient="records"):
        horizon = int(record["horizon"])
        for key, value in record.items():
            if key == "horizon":
                continue
            rows.append({"diagnostic": f"horizon_{horizon}_{key}", "value": value})
    return pd.DataFrame(rows)


def outcome_label(row: pd.Series | dict[str, Any]) -> str:
    labels = {"gini": "Gini", "top_1pct_share": "Top 1%", "top_5pct_share": "Top 5%"}
    return f"{row.get('flow')} {str(row.get('dimension')).title()} {labels.get(str(row.get('metric')), row.get('metric'))}"


def make_main_growth_figure(main_models: pd.DataFrame, figure_dir: Path) -> Path:
    sns.set_theme(style="whitegrid")
    data = main_models[main_models["term"].eq(PRIMARY_TERM) & main_models["status"].eq("ok")].copy()
    data["label"] = data.apply(outcome_label, axis=1)
    data["label"] = data["horizon"].astype(int).astype(str) + "y: " + data["label"]
    data = data.sort_values(["horizon", "flow", "dimension", "metric"])
    path = figure_dir / "main_growth_coefficients.png"
    fig, ax = plt.subplots(figsize=(11, max(7, 0.24 * len(data) + 1.5)))
    if data.empty:
        ax.text(0.5, 0.5, "No estimable main export-growth coefficients", ha="center", va="center")
        ax.axis("off")
    else:
        y = np.arange(len(data))
        ax.errorbar(
            data["coefficient"],
            y,
            xerr=[data["coefficient"] - data["ci_low"], data["ci_high"] - data["coefficient"]],
            fmt="none",
            ecolor="#64748b",
            capsize=3,
        )
        ax.scatter(data["coefficient"], y, c=data["flow"].map({"Exports": "#0b6b62", "Imports": "#8c4f2b"}), s=42, zorder=3)
        ax.axvline(0, color="#111827", linewidth=1, linestyle="--")
        ax.set_yticks(y)
        ax.set_yticklabels(data["label"])
        ax.set_xlabel("Coefficient on lagged real export growth")
        ax.set_title("Export-growth gradients in trade concentration by outcome horizon")
    fig.tight_layout()
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return path


def make_income_bin_slope_figure(income_bin_slopes: pd.DataFrame, figure_dir: Path) -> Path:
    sns.set_theme(style="whitegrid")
    data = income_bin_slopes[income_bin_slopes["row_type"].eq("slope") & income_bin_slopes["status"].eq("ok")].copy()
    data["label"] = data.apply(outcome_label, axis=1)
    data["label"] = data["horizon"].astype(int).astype(str) + "y: " + data["label"]
    data = data.sort_values(["horizon", "flow", "dimension", "metric", "export_level_bin"])
    path = figure_dir / "income_bin_slopes.png"
    fig, ax = plt.subplots(figsize=(12, max(7, 0.24 * data["label"].nunique() + 1.5)))
    if data.empty:
        ax.text(0.5, 0.5, "No estimable export-level-bin slopes", ha="center", va="center")
        ax.axis("off")
    else:
        labels = list(dict.fromkeys(data["label"]))
        offsets = {"low": -0.22, "middle": 0.0, "high": 0.22}
        colors = {"low": "#2563eb", "middle": "#64748b", "high": "#b7791f"}
        for bin_label, group in data.groupby("export_level_bin", sort=False):
            y = np.array([labels.index(label) for label in group["label"]], dtype=float) + offsets.get(str(bin_label), 0.0)
            ax.errorbar(
                group["coefficient"],
                y,
                xerr=[group["coefficient"] - group["ci_low"], group["ci_high"] - group["coefficient"]],
                fmt="o",
                label=str(bin_label).title(),
                color=colors.get(str(bin_label), "#334155"),
                ecolor=colors.get(str(bin_label), "#334155"),
                capsize=2,
                markersize=4,
            )
        ax.axvline(0, color="#111827", linewidth=1, linestyle="--")
        ax.set_yticks(np.arange(len(labels)))
        ax.set_yticklabels(labels)
        ax.set_xlabel("Marginal slope on lagged real export growth")
        ax.set_title("Export-growth slopes by lagged export-level tercile and horizon")
        ax.legend(title="Lagged export level")
    fig.tight_layout()
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return path


def safe_markdown(frame: pd.DataFrame) -> str:
    try:
        return frame.to_markdown(index=False)
    except Exception:
        return "```csv\n" + frame.to_csv(index=False) + "```"


def write_memo(
    memo_path: Path,
    args: argparse.Namespace,
    diagnostics: pd.DataFrame,
    main_models: pd.DataFrame,
    sample_comparison: pd.DataFrame,
    income_bin_slopes: pd.DataFrame,
    robustness: pd.DataFrame,
    threshold_scan: pd.DataFrame,
    cutoffs: dict[str, float],
    output_paths: dict[str, Path | list[Path]],
) -> None:
    main_table = main_models[main_models["term"].eq(PRIMARY_TERM)][
        ["horizon", "flow", "dimension", "metric", "coefficient", "std_error", "p_value", "bh_q_value", "nobs", "clusters", "status"]
    ].round(4)
    sample_comparison_table = sample_comparison[sample_comparison["term"].eq(PRIMARY_TERM)][
        [
            "sample_definition",
            "horizon",
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
    ].round(4)
    horizons = ", ".join(str(horizon) for horizon in normalize_horizons(args.horizons))
    text = f"""# Export Growth Effect Test

Generated: {now_utc()}

This is descriptive panel evidence, not causal identification. The estimand is the conditional within-country association between lagged real export growth in base year `b` and concentration `h` years later for the rd2 country panel. The requested horizons are {horizons} years.

```text
concentration_c,f,b+h = beta * [log(real exports_c,b) - log(real exports_c,b-1)]
                      + theta * log(real exports_c,b)
                      + delta * log(population_c,b)
                      + country FE + base-year FE + error_c,f,b,h
```

- Export source: World Bank `{WORLD_BANK_EXPORTS_INDICATOR}`, {WORLD_BANK_EXPORTS_LABEL}
- Horizon definition: `h` is the number of years from the lagged export-growth base year to the concentration outcome year. The 1-year specification is the previous next-year test.
- Matching rule: `match_horizon_sample={args.match_horizon_sample}`. When true, each country-flow-base-year must have all requested 1/5/10-year concentration outcomes and complete base-year export controls before entering any horizon model.
- Measurement caveat: export growth is goods-and-services exports, while the concentration outcomes are merchandise concentration measures, so the exposure is an aggregate export-growth environment rather than the exact concentration denominator.
- Product concentration excludes HS6 `999999`; partner concentration follows the partner-total convention.
- Lagged export-level tercile cutoffs: low/middle ${cutoffs["low_middle_export_cutoff"]:,.0f}; middle/high ${cutoffs["middle_high_export_cutoff"]:,.0f}.

## Main Lagged Export-Growth Coefficients

{safe_markdown(main_table)}

## Balanced Versus Broad Sample Check

{safe_markdown(sample_comparison_table)}

## Robustness Checks

{safe_markdown(robustness[robustness["term"].isin([PRIMARY_TERM, CONTEMPORANEOUS_TERM, FUTURE_TERM])].round(4))}

## Export-Level Slopes

{safe_markdown(income_bin_slopes.round(4))}

## Exploratory Threshold Scan

{safe_markdown(threshold_scan.round(4))}

## Sample Diagnostics

{safe_markdown(diagnostics)}
"""
    memo_path.write_text(text, encoding="utf-8")


def source_manifest(path: Path) -> dict[str, Any]:
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
    controls: pd.DataFrame,
    diagnostics: pd.DataFrame,
    main_models: pd.DataFrame,
    sample_comparison: pd.DataFrame,
    income_bin_slopes: pd.DataFrame,
    robustness: pd.DataFrame,
    threshold_scan: pd.DataFrame,
    cutoffs: dict[str, float],
    output_paths: dict[str, Path | list[Path]],
) -> None:
    manifest = {
        "created_at_utc": now_utc(),
        "country_sample": args.country_sample,
        "start_year": args.start_year,
        "end_year": args.end_year,
        "horizons": normalize_horizons(args.horizons),
        "horizon_definition": "years from export-growth base year to concentration outcome year",
        "prior_growth_definition": "log(real exports in base year) minus log(real exports in base year minus one)",
        "matched_horizon_sample": bool(args.match_horizon_sample),
        "world_bank_export_indicator": WORLD_BANK_EXPORTS_INDICATOR,
        "world_bank_export_indicator_label": WORLD_BANK_EXPORTS_LABEL,
        "model": "linear panel OLS with reporter-country and base-year fixed effects; country-clustered SEs",
        "causal_claim": False,
        "coverage": export_growth_coverage(panel, match_horizon_sample=args.match_horizon_sample),
        "horizon_coverage": horizon_coverage_rows(panel, match_horizon_sample=args.match_horizon_sample).to_dict(orient="records"),
        "export_level_tercile_cutoffs": cutoffs,
        "diagnostics": diagnostics.to_dict(orient="records"),
        "main_models_ok": int((main_models["status"].eq("ok") & main_models["term"].eq(PRIMARY_TERM)).sum()),
        "sample_comparison_models_ok": int((sample_comparison["status"].eq("ok") & sample_comparison["term"].eq(PRIMARY_TERM)).sum()),
        "robustness_models_ok": int(robustness["status"].eq("ok").sum()),
        "income_bin_rows_ok": int(income_bin_slopes["status"].eq("ok").sum()),
        "threshold_scan_rows_ok": int(threshold_scan["status"].eq("ok").sum()),
        "sources": {
            "concentration": source_manifest(sample_processed_path("concentration_all_years.parquet", args.country_sample)),
            "world_bank_export_controls": source_manifest(sample_processed_path("growth_effect_world_bank_export_controls.csv", args.country_sample)),
            "country_metadata": source_manifest(COUNTRY_METADATA),
        },
        "outputs": {key: [rel(p) for p in value] if isinstance(value, list) else rel(value) for key, value in output_paths.items()},
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def run(args: argparse.Namespace) -> None:
    base_results = sample_results_dir(args.country_sample)
    table_dir = base_results / "growth_effect_tables"
    figure_dir = base_results / "growth_effect_figures"
    panel_path = sample_processed_path("growth_effect_panel.parquet", args.country_sample)
    ensure_dirs(table_dir, figure_dir, panel_path.parent)

    print("Building export-growth panel...", flush=True)
    panel, controls, missing_controls = build_growth_panel(args)
    coverage_status = enforce_export_growth_coverage(panel, args)
    diagnostics = sample_diagnostics(panel, controls, missing_controls, coverage_status, args)
    missing_path = table_dir / "missing_controls.csv"
    diagnostics_path = table_dir / "sample_diagnostics.csv"
    missing_controls.to_csv(missing_path, index=False)
    diagnostics.to_csv(diagnostics_path, index=False)
    panel.to_parquet(panel_path, index=False)
    model_panel = analysis_sample(panel, args.match_horizon_sample)

    print("Estimating main export-growth models...", flush=True)
    main_models = run_main_models(model_panel, args.country_sample, args.horizons)
    print("Estimating balanced-vs-broad sample models...", flush=True)
    sample_comparison = run_sample_comparison_models(panel, model_panel, args.country_sample, args.horizons)
    print("Estimating export-level-bin slopes...", flush=True)
    income_bin_slopes, cutoffs = run_income_bin_slopes(model_panel, args.country_sample, args.horizons)
    print("Estimating robustness models...", flush=True)
    robustness = run_robustness_models(model_panel, args.country_sample, args.horizons)
    print("Running exploratory threshold scan...", flush=True)
    threshold_scan = run_threshold_scan(model_panel, args.country_sample, args.horizons)

    main_path = table_dir / "main_models.csv"
    sample_comparison_path = table_dir / "sample_comparison_models.csv"
    income_bin_path = table_dir / "income_bin_slopes.csv"
    robustness_path = table_dir / "robustness_models.csv"
    threshold_path = table_dir / "threshold_scan.csv"
    main_models.to_csv(main_path, index=False)
    sample_comparison.to_csv(sample_comparison_path, index=False)
    income_bin_slopes.to_csv(income_bin_path, index=False)
    robustness.to_csv(robustness_path, index=False)
    threshold_scan.to_csv(threshold_path, index=False)

    figure_paths = [make_main_growth_figure(main_models, figure_dir), make_income_bin_slope_figure(income_bin_slopes, figure_dir)]
    memo_path = base_results / "growth_effect.md"
    manifest_path = base_results / "run_manifest_growth_effect.json"
    output_paths: dict[str, Path | list[Path]] = {
        "panel": panel_path,
        "main_models": main_path,
        "sample_comparison_models": sample_comparison_path,
        "income_bin_slopes": income_bin_path,
        "robustness_models": robustness_path,
        "threshold_scan": threshold_path,
        "sample_diagnostics": diagnostics_path,
        "missing_controls": missing_path,
        "figures": figure_paths,
        "memo": memo_path,
        "manifest": manifest_path,
    }
    write_memo(memo_path, args, diagnostics, main_models, sample_comparison, income_bin_slopes, robustness, threshold_scan, cutoffs, output_paths)
    write_manifest(manifest_path, args, panel, controls, diagnostics, main_models, sample_comparison, income_bin_slopes, robustness, threshold_scan, cutoffs, output_paths)

    print(f"Wrote {rel(memo_path)}")
    print(f"Wrote {rel(main_path)}")
    print(f"Wrote {rel(sample_comparison_path)}")
    print(f"Wrote {rel(income_bin_path)}")
    print(f"Wrote {rel(robustness_path)}")
    print(f"Wrote {rel(threshold_path)}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country-sample", choices=COUNTRY_SAMPLE_CHOICES, default="rd2_countries")
    parser.add_argument("--start-year", type=int, default=1988)
    parser.add_argument("--end-year", type=int, default=2024)
    parser.add_argument("--horizons", type=int, nargs="+", default=list(DEFAULT_HORIZONS))
    parser.add_argument(
        "--no-match-horizon-sample",
        dest="match_horizon_sample",
        action="store_false",
        help="Use each horizon's available rows instead of the common country-flow-base-year support across horizons.",
    )
    parser.add_argument("--refresh-controls", action="store_true")
    parser.add_argument("--min-clusters", type=int, default=25)
    parser.add_argument("--min-coverage", type=float, default=0.50)
    parser.add_argument("--coverage-limited-threshold", type=float, default=0.80)
    parser.set_defaults(match_horizon_sample=True)
    args = parser.parse_args(argv)
    if args.end_year < args.start_year:
        parser.error("--end-year must be greater than or equal to --start-year")
    try:
        args.horizons = normalize_horizons(args.horizons)
    except ValueError as exc:
        parser.error(str(exc))
    if args.min_clusters < 2:
        parser.error("--min-clusters must be at least 2")
    if not (0 < args.min_coverage <= 1):
        parser.error("--min-coverage must be in (0, 1]")
    if not (args.min_coverage <= args.coverage_limited_threshold <= 1):
        parser.error("--coverage-limited-threshold must be between --min-coverage and 1")
    return args


def main(argv: list[str] | None = None) -> None:
    run(parse_args(argv))


if __name__ == "__main__":
    main()
