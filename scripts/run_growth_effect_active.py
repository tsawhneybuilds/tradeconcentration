#!/usr/bin/env python3
"""Descriptive per-capita income-growth and trade-concentration panel exercise."""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy.linalg import qr
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
WORLD_BANK_RAW = ROOT / "data" / "raw" / "world_bank_gdp"
COUNTRY_METADATA = WORLD_BANK_RAW / "country_metadata.csv"
GDP_EXPOSURE = "gdp_pc"
GNI_EXPOSURE = "gni_pc"
EXPOSURES = {
    GDP_EXPOSURE: {"indicator": "NY.GDP.PCAP.KD", "value_col": "gdp_pc_real_2015_usd", "label": "Real GDP per capita"},
    GNI_EXPOSURE: {"indicator": "NY.GNP.PCAP.KD", "value_col": "gni_pc_real_2015_usd", "label": "Real GNI per capita"},
}
POPULATION_COL = "population"
PRIMARY_MODEL = "main_country_year_fe"
MIN_GNI_CLUSTERS = 25
MIN_GNI_USABLE_SHARE = 0.50


@dataclass(frozen=True)
class FitResult:
    model_label: str
    sample: str
    exposure: str
    flow: str
    dimension: str
    metric: str
    outcome: str
    terms: list[str]
    beta: dict[str, float]
    cov: pd.DataFrame
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
        raise RuntimeError(f"{path} is missing required columns: {missing}")
    return data


def source_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": rel(path), "exists": False}
    return {
        "path": rel(path),
        "exists": True,
        "size_bytes": path.stat().st_size,
        "mtime_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds"),
    }


def load_country_metadata(iso3s: list[str]) -> pd.DataFrame:
    if not COUNTRY_METADATA.exists():
        return pd.DataFrame({"iso3": iso3s, "region": "Unknown"})
    meta = pd.read_csv(COUNTRY_METADATA)
    if "iso3" not in meta.columns:
        return pd.DataFrame({"iso3": iso3s, "region": "Unknown"})
    if "region" not in meta.columns:
        meta["region"] = "Unknown"
    meta["iso3"] = meta["iso3"].astype(str).str.upper()
    return pd.DataFrame({"iso3": iso3s}).merge(meta[["iso3", "region"]].drop_duplicates("iso3"), on="iso3", how="left")


def load_growth_concentration_panel(country_sample: str, start_year: int, end_year: int) -> pd.DataFrame:
    path = sample_processed_path("concentration_all_years.parquet", country_sample)
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


def seed_growth_controls_from_existing_files(iso3s: list[str], start_year: int, end_year: int) -> pd.DataFrame:
    panel = pd.DataFrame([(iso3, year) for iso3 in sorted(set(iso3s)) for year in range(start_year, end_year + 1)], columns=["iso3", "year"])
    frames = []
    for path in [
        WORLD_BANK_RAW / "sp_pop_totl_1988_2024.csv",
        WORLD_BANK_RAW / "sp_pop_totl_1988_1992.csv",
        WORLD_BANK_RAW / "sp_pop_totl_1988_1988.csv",
    ]:
        frame = read_csv_if_exists(path, ["iso3", "year", POPULATION_COL])
        if frame.empty:
            continue
        frame["iso3"] = frame["iso3"].astype(str).str.upper()
        frame["year"] = pd.to_numeric(frame["year"], errors="coerce")
        frame[POPULATION_COL] = pd.to_numeric(frame[POPULATION_COL], errors="coerce")
        frames.append(frame[frame["iso3"].isin(set(iso3s)) & frame["year"].between(start_year, end_year)])
    if frames:
        combined = pd.concat(frames, ignore_index=True).dropna(subset=["iso3", "year"])
        combined = combined.sort_values(["iso3", "year", POPULATION_COL], na_position="first").drop_duplicates(["iso3", "year"], keep="last")
        panel = panel.merge(combined, on=["iso3", "year"], how="left")
    return panel


def load_or_fetch_growth_controls(iso3s: list[str], start_year: int, end_year: int, cache_path: Path, refresh: bool = False) -> pd.DataFrame:
    required = ["iso3", "year", POPULATION_COL, EXPOSURES[GDP_EXPOSURE]["value_col"], EXPOSURES[GNI_EXPOSURE]["value_col"]]
    expected = pd.DataFrame([(iso3, year) for iso3 in sorted(set(iso3s)) for year in range(start_year, end_year + 1)], columns=["iso3", "year"])
    controls = expected.merge(read_csv_if_exists(cache_path, required), on=["iso3", "year"], how="left") if cache_path.exists() and not refresh else seed_growth_controls_from_existing_files(iso3s, start_year, end_year)
    needs_fetch = refresh or controls.empty
    for col in required:
        if col in {"iso3", "year"}:
            continue
        if col not in controls.columns or controls[col].notna().mean() < 0.50:
            needs_fetch = True
        if col in controls.columns:
            latest_requested = controls["year"].eq(end_year)
            if bool(latest_requested.any()) and controls.loc[latest_requested, col].isna().all():
                needs_fetch = True
    specs = {
        POPULATION_COL: ("SP.POP.TOTL", POPULATION_COL),
        EXPOSURES[GDP_EXPOSURE]["value_col"]: (EXPOSURES[GDP_EXPOSURE]["indicator"], EXPOSURES[GDP_EXPOSURE]["value_col"]),
        EXPOSURES[GNI_EXPOSURE]["value_col"]: (EXPOSURES[GNI_EXPOSURE]["indicator"], EXPOSURES[GNI_EXPOSURE]["value_col"]),
    }
    frames = [controls]
    if needs_fetch:
        for indicator, value_col in specs.values():
            try:
                frames.append(cse.fetch_world_bank_indicator(iso3s, indicator, value_col, start_year, end_year))
            except Exception as exc:
                print(f"World Bank refresh warning for {indicator}: {exc}", file=sys.stderr)
    merged = expected.copy()
    for value_col in specs:
        value_frames = [frame[["iso3", "year", value_col]] for frame in frames if value_col in frame.columns]
        combined = pd.concat(value_frames, ignore_index=True) if value_frames else pd.DataFrame(columns=["iso3", "year", value_col])
        if combined.empty:
            merged[value_col] = np.nan
            continue
        combined["iso3"] = combined["iso3"].astype(str).str.upper()
        combined["year"] = pd.to_numeric(combined["year"], errors="coerce")
        combined[value_col] = pd.to_numeric(combined[value_col], errors="coerce")
        combined = combined.dropna(subset=["iso3", "year"]).sort_values(["iso3", "year", value_col], na_position="first").drop_duplicates(["iso3", "year"], keep="last")
        merged = merged.merge(combined, on=["iso3", "year"], how="left")
    for col in required:
        if col not in {"iso3", "year"}:
            merged[col] = pd.to_numeric(merged[col], errors="coerce")
    merged["year"] = pd.to_numeric(merged["year"], errors="coerce").astype(int)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(cache_path, index=False)
    return merged


def add_growth_features(controls: pd.DataFrame) -> pd.DataFrame:
    work = controls.copy()
    work["iso3"] = work["iso3"].astype(str).str.upper()
    work["year"] = pd.to_numeric(work["year"], errors="coerce").astype(int)
    validate_unique_keys(work, ["iso3", "year"], "growth controls")
    work = work.sort_values(["iso3", "year"]).copy()
    work["log_population"] = np.where(work[POPULATION_COL] > 0, np.log(work[POPULATION_COL]), np.nan)
    lag_year = work.groupby("iso3")["year"].shift(1)
    lead_two_year = work.groupby("iso3")["year"].shift(-2)
    for exposure, spec in EXPOSURES.items():
        log_col = f"log_{exposure}_level"
        growth_col = f"{exposure}_growth"
        work[log_col] = np.where(work[spec["value_col"]] > 0, np.log(work[spec["value_col"]]), np.nan)
        lag_log = work.groupby("iso3")[log_col].shift(1)
        work[growth_col] = work[log_col] - lag_log
        work.loc[~lag_year.eq(work["year"] - 1), growth_col] = np.nan
        work[f"future_{growth_col}"] = work.groupby("iso3")[growth_col].shift(-2)
        work.loc[~lead_two_year.eq(work["year"] + 2), f"future_{growth_col}"] = np.nan
    features = work[["iso3", "year", "log_population"]].copy()
    features["year"] = features["year"] + 1
    features = features.rename(columns={"log_population": "log_population_lag"})
    for exposure in EXPOSURES:
        part = work[["iso3", "year", f"log_{exposure}_level", f"{exposure}_growth", f"future_{exposure}_growth"]].copy()
        part["year"] = part["year"] + 1
        part = part.rename(columns={f"log_{exposure}_level": f"log_{exposure}_level_lag", f"{exposure}_growth": f"{exposure}_growth_lag", f"future_{exposure}_growth": f"{exposure}_growth_future"})
        current = work[["iso3", "year", f"{exposure}_growth"]].rename(columns={f"{exposure}_growth": f"{exposure}_growth_current"})
        part = part.merge(current, on=["iso3", "year"], how="left", validate="one_to_one")
        features = features.merge(part, on=["iso3", "year"], how="left", validate="one_to_one")
    validate_unique_keys(features, ["iso3", "year"], "lagged growth features")
    return features


def add_income_bins(panel: pd.DataFrame, exposure: str) -> pd.DataFrame:
    out = panel.copy()
    level_col = f"log_{exposure}_level_lag"
    unique = out[["iso3", "year", level_col]].drop_duplicates(["iso3", "year"]).dropna(subset=[level_col])
    q1, q2 = unique[level_col].quantile([1 / 3, 2 / 3]).to_numpy(dtype=float)
    out[f"{exposure}_income_bin"] = np.select([out[level_col] <= q1, out[level_col] <= q2], ["low", "middle"], default="high")
    out.loc[out[level_col].isna(), f"{exposure}_income_bin"] = np.nan
    out[f"{exposure}_income_low_max"] = math.exp(q1)
    out[f"{exposure}_income_middle_max"] = math.exp(q2)
    return out


def build_growth_panel(args: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    concentration = load_growth_concentration_panel(args.country_sample, args.start_year, args.end_year)
    iso3s = sorted(concentration["iso3"].dropna().astype(str).str.upper().unique())
    controls = load_or_fetch_growth_controls(iso3s, args.start_year - 2, args.end_year + 1, sample_processed_path("growth_effect_world_bank_controls.csv", args.country_sample), refresh=args.refresh_controls)
    panel = concentration.merge(add_growth_features(controls), on=["iso3", "year"], how="left", validate="many_to_one")
    panel = panel.merge(load_country_metadata(iso3s), on="iso3", how="left", validate="many_to_one")
    panel["region"] = panel["region"].fillna("Unknown").astype(str).str.strip().replace("", "Unknown")
    panel["region_year"] = panel["region"].str.replace(r"[^A-Za-z0-9]+", "_", regex=True).str.strip("_") + "_" + panel["year"].astype(str)
    for exposure in EXPOSURES:
        panel = add_income_bins(panel, exposure)
    control_cols = ["log_population_lag"]
    for exposure in EXPOSURES:
        control_cols.extend([f"log_{exposure}_level_lag", f"{exposure}_growth_lag", f"{exposure}_growth_current", f"{exposure}_growth_future"])
    missing_controls = panel[panel[control_cols].isna().any(axis=1)][["country", "iso3", "reporter_code", "year", "flow", *control_cols]].copy()
    return panel, controls, missing_controls


def full_rank_design_matrix(work: pd.DataFrame, terms: list[str], fixed_effects: list[str]) -> tuple[pd.DataFrame, list[str]]:
    parts = [pd.Series(1.0, index=work.index, name="intercept")]
    for term in terms:
        parts.append(pd.to_numeric(work[term], errors="coerce").rename(term))
    for fe_col in fixed_effects:
        dummies = pd.get_dummies(work[fe_col].astype(str), prefix=fe_col, drop_first=True, dtype=float)
        if not dummies.empty:
            parts.append(dummies)
    x = pd.concat(parts, axis=1).astype(float)
    values = x.to_numpy(dtype=float)
    _, r, piv = qr(values, mode="economic", pivoting=True, check_finite=False)
    diag = np.abs(np.diag(r)) if r.ndim == 2 else np.array([])
    tol = np.finfo(float).eps * max(values.shape) * (diag.max() if diag.size else 0.0)
    rank = int(np.sum(diag > tol))
    kept_cols = x.columns[sorted(piv[:rank].tolist())].tolist()
    priority_cols = ["intercept", *terms]
    for priority in priority_cols:
        if priority in kept_cols or priority not in x.columns:
            continue
        for candidate in reversed(kept_cols):
            if candidate in priority_cols:
                continue
            trial = [priority if col == candidate else col for col in kept_cols]
            if int(np.linalg.matrix_rank(x[trial].to_numpy(dtype=float), tol=tol)) == rank:
                kept_cols = trial
                break
    return x[kept_cols], [col for col in x.columns if col not in set(kept_cols)]


def empty_fit_result(model_label: str, sample: str, exposure: str, flow: str, dimension: str, metric: str, outcome: str, terms: list[str], fixed_effects: list[str], cluster_col: str, candidate_rows: int, dropped_rows: int, status: str) -> FitResult:
    return FitResult(model_label, sample, exposure, flow, dimension, metric, outcome, terms, {term: np.nan for term in terms}, pd.DataFrame(np.nan, index=terms, columns=terms), 0, 0, np.nan, status, dropped_rows, candidate_rows, "", "none", np.nan, ",".join(fixed_effects) or "none", cluster_col or "")


def fit_ols_model(df: pd.DataFrame, outcome: str, terms: list[str], fixed_effects: list[str], model_label: str, sample: str, exposure: str, flow: str, dimension: str, metric: str, cluster_col: str = "reporter_code", two_way_cluster_col: str | None = None) -> FitResult:
    required = list(dict.fromkeys([outcome, *terms, *fixed_effects, *([cluster_col] if cluster_col else []), *([two_way_cluster_col] if two_way_cluster_col else [])]))
    candidate_rows = int(len(df))
    cluster_label = ",".join(col for col in [cluster_col, two_way_cluster_col or ""] if col)
    missing = [col for col in required if col not in df.columns]
    if missing:
        return empty_fit_result(model_label, sample, exposure, flow, dimension, metric, outcome, terms, fixed_effects, cluster_label, candidate_rows, candidate_rows, f"missing_required_columns:{','.join(missing)}")
    work = df.replace([np.inf, -np.inf], np.nan).dropna(subset=required).copy()
    dropped_rows = int(candidate_rows - len(work))
    if len(work) < len(terms) + 3:
        return empty_fit_result(model_label, sample, exposure, flow, dimension, metric, outcome, terms, fixed_effects, cluster_label, candidate_rows, dropped_rows, "insufficient_sample")
    y = pd.to_numeric(work[outcome], errors="coerce").to_numpy(dtype=float)
    x_df, dropped_regressors = full_rank_design_matrix(work, terms, fixed_effects)
    if x_df.shape[0] <= x_df.shape[1]:
        return empty_fit_result(model_label, sample, exposure, flow, dimension, metric, outcome, terms, fixed_effects, cluster_label, candidate_rows, dropped_rows, "too_many_regressors")
    x = x_df.to_numpy(dtype=float)
    beta_all, *_ = np.linalg.lstsq(x, y, rcond=None)
    resid = y - x @ beta_all
    if cluster_col and two_way_cluster_col:
        clusters = min(int(work[cluster_col].nunique()), int(work[two_way_cluster_col].nunique()))
        cov = cse.two_way_cluster_robust_covariance(x, resid, work[cluster_col], work[two_way_cluster_col])
        se_method = f"two-way clustered by {cluster_col} and {two_way_cluster_col}"
        p_reference_df = float(max(clusters - 1, 1))
    elif cluster_col:
        clusters = int(work[cluster_col].nunique())
        cov = cse.cluster_robust_covariance(x, resid, work[cluster_col]) if clusters > 1 else np.full((x.shape[1], x.shape[1]), np.nan)
        se_method = f"clustered by {cluster_col}"
        p_reference_df = float(clusters - 1) if clusters > 1 else np.nan
    else:
        clusters = 0
        cov = cse.hc1_covariance(x, resid)
        se_method = "HC1 heteroskedasticity-robust"
        p_reference_df = float(max(x.shape[0] - x.shape[1], 1))
    total_var = float(np.sum(np.square(y - y.mean())))
    cov_df = pd.DataFrame(cov, index=x_df.columns, columns=x_df.columns)
    beta = {term: float(beta_all[x_df.columns.get_loc(term)]) if term in x_df.columns else np.nan for term in terms}
    absorbed = [term for term in terms if term not in x_df.columns]
    return FitResult(model_label, sample, exposure, flow, dimension, metric, outcome, terms, beta, cov_df, int(len(work)), clusters, float(1 - np.sum(np.square(resid)) / total_var) if total_var > 0 else np.nan, "terms_absorbed:" + ",".join(absorbed) if absorbed else "ok", dropped_rows, candidate_rows, ",".join(dropped_regressors), se_method, p_reference_df, ",".join(fixed_effects) or "none", cluster_label)


def coefficient_row(result: FitResult, term: str) -> dict[str, Any]:
    coef = result.beta.get(term, np.nan)
    variance = result.cov.loc[term, term] if term in result.cov.index and term in result.cov.columns else np.nan
    stderr = math.sqrt(max(float(variance), 0.0)) if np.isfinite(variance) else np.nan
    t_stat = coef / stderr if np.isfinite(coef) and np.isfinite(stderr) and stderr > 0 else np.nan
    p_value = 2 * student_t.sf(abs(t_stat), result.p_reference_df) if np.isfinite(t_stat) and np.isfinite(result.p_reference_df) else np.nan
    critical = student_t.ppf(0.975, result.p_reference_df) if np.isfinite(result.p_reference_df) else np.nan
    return {"model_label": result.model_label, "sample": result.sample, "exposure": result.exposure, "exposure_label": EXPOSURES[result.exposure]["label"], "flow": result.flow, "dimension": result.dimension, "metric": result.metric, "outcome": result.outcome, "term": term, "coefficient": float(coef) if np.isfinite(coef) else np.nan, "std_error": float(stderr) if np.isfinite(stderr) else np.nan, "t_stat": float(t_stat) if np.isfinite(t_stat) else np.nan, "p_value": float(p_value) if np.isfinite(p_value) else np.nan, "ci_low": float(coef - critical * stderr) if np.isfinite(coef) and np.isfinite(stderr) and np.isfinite(critical) else np.nan, "ci_high": float(coef + critical * stderr) if np.isfinite(coef) and np.isfinite(stderr) and np.isfinite(critical) else np.nan, "nobs": result.nobs, "clusters": result.clusters, "r_squared": result.r_squared, "status": result.status, "candidate_rows": result.candidate_rows, "dropped_rows": result.dropped_rows, "dropped_regressors": result.dropped_regressors, "fixed_effects": result.fixed_effects, "se_method": result.se_method, "cluster_col": result.cluster_col, "p_value_reference": f"Student t, df={int(result.p_reference_df)}" if np.isfinite(result.p_reference_df) else ""}


def fit_results_to_frame(results: list[FitResult]) -> pd.DataFrame:
    return pd.DataFrame([coefficient_row(result, term) for result in results for term in result.terms])


def primary_terms() -> dict[str, str]:
    return {exposure: f"{exposure}_growth_lag" for exposure in EXPOSURES}


def primary_term_for_model(model_label: str, exposure: str) -> str:
    if model_label == "contemporaneous_growth":
        return f"{exposure}_growth_current"
    if model_label == "future_growth_placebo":
        return f"{exposure}_growth_future"
    return f"{exposure}_growth_lag"


def add_q_values(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["bh_q_value"] = np.nan
    for (model_label, exposure), group in out.groupby(["model_label", "exposure"], dropna=False):
        primary = primary_term_for_model(str(model_label), str(exposure))
        mask = group["term"].eq(primary) & group["status"].eq("ok")
        if bool(mask.any()):
            out.loc[group.index[mask], "bh_q_value"] = cse.benjamini_hochberg(group.loc[mask, "p_value"])
    return out


def base_terms(exposure: str, growth_suffix: str = "lag") -> list[str]:
    return [f"{exposure}_growth_{growth_suffix}", f"log_{exposure}_level_lag", "log_population_lag"]


def run_main_models(panel: pd.DataFrame, country_sample: str) -> pd.DataFrame:
    results = [
        fit_ols_model(panel[panel["flow"].eq(flow)].copy(), outcome, base_terms(exposure), ["reporter_code", "year"], PRIMARY_MODEL, country_sample, exposure, flow, dimension, metric)
        for exposure in EXPOSURES
        for flow in FLOWS
        for dimension, metric, outcome, _label in OUTCOME_SPECS
    ]
    return add_q_values(fit_results_to_frame(results))


def run_robustness_models(panel: pd.DataFrame, country_sample: str) -> pd.DataFrame:
    results = []
    for exposure in EXPOSURES:
        specs = [
            ("two_way_country_year_cluster", base_terms(exposure), ["reporter_code", "year"], "reporter_code", "year"),
            ("contemporaneous_growth", base_terms(exposure, "current"), ["reporter_code", "year"], "reporter_code", None),
            ("future_growth_placebo", base_terms(exposure, "future"), ["reporter_code", "year"], "reporter_code", None),
            ("region_year_fe", base_terms(exposure), ["reporter_code", "region_year"], "reporter_code", None),
        ]
        for flow in FLOWS:
            flow_panel = panel[panel["flow"].eq(flow)].copy()
            for dimension, metric, outcome, _label in OUTCOME_SPECS:
                for model_label, terms, fixed_effects, cluster_col, two_way_col in specs:
                    results.append(fit_ols_model(flow_panel, outcome, terms, fixed_effects, model_label, country_sample, exposure, flow, dimension, metric, cluster_col=cluster_col, two_way_cluster_col=two_way_col))
    return add_q_values(fit_results_to_frame(results))


def linear_combo(result: FitResult, weights: dict[str, float]) -> tuple[float, float, float, float, float]:
    terms = [term for term in weights if term in result.cov.index and np.isfinite(result.beta.get(term, np.nan))]
    if not terms:
        return np.nan, np.nan, np.nan, np.nan, np.nan
    w = np.array([weights[term] for term in terms], dtype=float)
    coef = float(sum(weights[term] * result.beta.get(term, np.nan) for term in terms))
    variance = float(w @ result.cov.loc[terms, terms].to_numpy(dtype=float) @ w)
    stderr = math.sqrt(max(variance, 0.0)) if np.isfinite(variance) else np.nan
    t_stat = coef / stderr if np.isfinite(stderr) and stderr > 0 else np.nan
    p_value = 2 * student_t.sf(abs(t_stat), result.p_reference_df) if np.isfinite(t_stat) and np.isfinite(result.p_reference_df) else np.nan
    critical = student_t.ppf(0.975, result.p_reference_df) if np.isfinite(result.p_reference_df) else np.nan
    return coef, stderr, p_value, coef - critical * stderr if np.isfinite(critical) and np.isfinite(stderr) else np.nan, coef + critical * stderr if np.isfinite(critical) and np.isfinite(stderr) else np.nan


def run_income_bin_models(panel: pd.DataFrame, country_sample: str) -> pd.DataFrame:
    rows = []
    high_rows = []
    for exposure in EXPOSURES:
        growth = f"{exposure}_growth_lag"
        middle = f"{exposure}_growth_lag_x_middle_income"
        high = f"{exposure}_growth_lag_x_high_income"
        work = panel.copy()
        work[middle] = np.where(work[f"{exposure}_income_bin"].eq("middle"), work[growth], 0.0)
        work[high] = np.where(work[f"{exposure}_income_bin"].eq("high"), work[growth], 0.0)
        terms = [growth, middle, high, f"log_{exposure}_level_lag", "log_population_lag"]
        for flow in FLOWS:
            flow_panel = work[work["flow"].eq(flow)].copy()
            for dimension, metric, outcome, _label in OUTCOME_SPECS:
                result = fit_ols_model(flow_panel, outcome, terms, ["reporter_code", "year"], "growth_by_income_tercile", country_sample, exposure, flow, dimension, metric)
                high_diff = coefficient_row(result, high)
                low_cutoff = flow_panel[f"{exposure}_income_low_max"].dropna()
                middle_cutoff = flow_panel[f"{exposure}_income_middle_max"].dropna()
                group_start = len(rows)
                for income_bin, weights in {"low": {growth: 1.0}, "middle": {growth: 1.0, middle: 1.0}, "high": {growth: 1.0, high: 1.0}}.items():
                    coef, se, p_value, ci_low, ci_high = linear_combo(result, weights)
                    rows.append({"model_label": result.model_label, "sample": country_sample, "exposure": exposure, "exposure_label": EXPOSURES[exposure]["label"], "flow": flow, "dimension": dimension, "metric": metric, "outcome": outcome, "income_bin": income_bin, "coefficient": coef, "std_error": se, "p_value": p_value, "ci_low": ci_low, "ci_high": ci_high, "nobs": result.nobs, "clusters": result.clusters, "status": result.status, "income_low_max_2015_usd": float(low_cutoff.iloc[0]) if not low_cutoff.empty else np.nan, "income_middle_max_2015_usd": float(middle_cutoff.iloc[0]) if not middle_cutoff.empty else np.nan, "high_minus_low_coef": high_diff["coefficient"] if income_bin == "high" else np.nan, "high_minus_low_p_value": high_diff["p_value"] if income_bin == "high" else np.nan, "leveling_off_supported": False})
                    if income_bin == "high":
                        high_rows.append(len(rows) - 1)
                low_coef = rows[group_start]["coefficient"]
                high_coef = rows[group_start + 2]["coefficient"]
                rows[group_start + 2]["leveling_off_supported"] = bool(np.isfinite(low_coef) and np.isfinite(high_coef) and abs(high_coef) < abs(low_coef))
    out = pd.DataFrame(rows)
    out["high_minus_low_bh_q_value"] = np.nan
    if high_rows:
        out.loc[high_rows, "high_minus_low_bh_q_value"] = cse.benjamini_hochberg(out.loc[high_rows, "high_minus_low_p_value"])
        out.loc[high_rows, "leveling_off_supported"] = out.loc[high_rows, "leveling_off_supported"] & (out.loc[high_rows, "high_minus_low_bh_q_value"] <= 0.10)
    return out


def run_threshold_scan(panel: pd.DataFrame, country_sample: str) -> pd.DataFrame:
    rows = []
    for exposure in EXPOSURES:
        growth = f"{exposure}_growth_lag"
        level = f"log_{exposure}_level_lag"
        above_term = f"{exposure}_growth_lag_x_above_threshold"
        unique = panel[["iso3", "year", level]].drop_duplicates(["iso3", "year"]).dropna(subset=[level])
        for percentile in range(30, 71, 10):
            threshold = float(unique[level].quantile(percentile / 100))
            work = panel.copy()
            work[above_term] = np.where(work[level] > threshold, work[growth], 0.0)
            terms = [growth, above_term, level, "log_population_lag"]
            for flow in FLOWS:
                flow_panel = work[work["flow"].eq(flow)].copy()
                for dimension, metric, outcome, _label in OUTCOME_SPECS:
                    result = fit_ols_model(flow_panel, outcome, terms, ["reporter_code", "year"], "threshold_scan", country_sample, exposure, flow, dimension, metric)
                    below = coefficient_row(result, growth)
                    above = linear_combo(result, {growth: 1.0, above_term: 1.0})
                    diff = coefficient_row(result, above_term)
                    rows.append({"model_label": "threshold_scan", "sample": country_sample, "exposure": exposure, "exposure_label": EXPOSURES[exposure]["label"], "flow": flow, "dimension": dimension, "metric": metric, "outcome": outcome, "threshold_percentile": percentile, "threshold_income_2015_usd": math.exp(threshold), "below_threshold_slope": below["coefficient"], "below_threshold_std_error": below["std_error"], "above_threshold_slope": above[0], "above_threshold_std_error": above[1], "above_minus_below_coef": diff["coefficient"], "above_minus_below_p_value": diff["p_value"], "nobs": result.nobs, "clusters": result.clusters, "status": result.status})
    out = pd.DataFrame(rows)
    out["above_minus_below_bh_q_value"] = np.nan
    mask = out["status"].eq("ok")
    out.loc[mask, "above_minus_below_bh_q_value"] = cse.benjamini_hochberg(out.loc[mask, "above_minus_below_p_value"])
    return out


def validate_exposure_coverage(panel: pd.DataFrame) -> None:
    for exposure in EXPOSURES:
        required = [f"{exposure}_growth_lag", f"log_{exposure}_level_lag", "log_population_lag"]
        complete = panel[required].replace([np.inf, -np.inf], np.nan).notna().all(axis=1)
        clusters = int(panel.loc[complete, "reporter_code"].nunique())
        share = float(complete.mean()) if len(complete) else 0.0
        if exposure == GNI_EXPOSURE and (clusters < MIN_GNI_CLUSTERS or share < MIN_GNI_USABLE_SHARE):
            raise RuntimeError(f"GNI per-capita growth coverage is too incomplete for publication: {clusters} country clusters and {share:.1%} usable flow rows.")
        if exposure == GDP_EXPOSURE and clusters < MIN_GNI_CLUSTERS:
            raise RuntimeError(f"GDP per-capita growth coverage has only {clusters} country clusters.")


def sample_diagnostics(panel: pd.DataFrame, controls: pd.DataFrame, missing_controls: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    rows: list[dict[str, Any]] = [
        {"diagnostic": "country_sample", "value": args.country_sample},
        {"diagnostic": "start_year", "value": args.start_year},
        {"diagnostic": "end_year", "value": args.end_year},
        {"diagnostic": "panel_rows", "value": len(panel)},
        {"diagnostic": "countries", "value": panel["iso3"].nunique()},
        {"diagnostic": "years", "value": panel["year"].nunique()},
        {"diagnostic": "country_years", "value": len(panel[["iso3", "year"]].drop_duplicates())},
        {"diagnostic": "control_rows", "value": len(controls)},
        {"diagnostic": "control_duplicate_iso3_year_rows", "value": int(controls.duplicated(["iso3", "year"]).sum())},
        {"diagnostic": "duplicate_iso3_year_flow_rows", "value": int(panel.duplicated(["iso3", "year", "flow"]).sum())},
        {"diagnostic": "missing_control_flow_rows_any_growth_variable", "value": len(missing_controls)},
        {"diagnostic": "product_outcome_hs6_999999_rule", "value": "excluded upstream before product aggregation"},
        {"diagnostic": "partner_outcome_hs6_999999_rule", "value": "included by partner-total convention"},
    ]
    for flow in FLOWS:
        rows.append({"diagnostic": f"{flow.lower()}_rows", "value": int(panel["flow"].eq(flow).sum())})
    for exposure in EXPOSURES:
        required = [f"{exposure}_growth_lag", f"log_{exposure}_level_lag", "log_population_lag"]
        complete = panel[required].replace([np.inf, -np.inf], np.nan).notna().all(axis=1)
        share = float(complete.mean()) if len(complete) else np.nan
        rows.extend([
            {"diagnostic": f"{exposure}_main_complete_flow_rows", "value": int(complete.sum())},
            {"diagnostic": f"{exposure}_main_complete_flow_row_share", "value": share},
            {"diagnostic": f"{exposure}_main_complete_country_clusters", "value": int(panel.loc[complete, "reporter_code"].nunique())},
            {"diagnostic": f"{exposure}_main_complete_country_years", "value": int(panel.loc[complete, ["iso3", "year"]].drop_duplicates().shape[0])},
        ])
        future_required = [f"{exposure}_growth_future", f"log_{exposure}_level_lag", "log_population_lag"]
        future_complete = panel[future_required].replace([np.inf, -np.inf], np.nan).notna().all(axis=1)
        rows.append({"diagnostic": f"{exposure}_future_placebo_complete_flow_rows", "value": int(future_complete.sum())})
        if exposure == GNI_EXPOSURE:
            rows.append({"diagnostic": "gni_pc_coverage_label", "value": "main" if share >= 0.80 else "coverage_limited_sensitivity"})
    return pd.DataFrame(rows)


def make_growth_figures(main_models: pd.DataFrame, income_bins: pd.DataFrame, figure_dir: Path) -> list[Path]:
    sns.set_theme(style="whitegrid")
    paths: list[Path] = []
    primary = main_models[main_models["term"].isin(primary_terms().values()) & main_models["status"].eq("ok")].copy()
    if not primary.empty:
        primary["measure"] = primary["flow"] + " " + primary["dimension"].str.title() + " " + primary["metric"].str.replace("_", " ")
        grid = sns.catplot(data=primary, x="coefficient", y="measure", hue="exposure_label", col="flow", kind="point", errorbar=None, height=5.2, aspect=1.15, sharex=False)
        for ax in grid.axes.flat:
            ax.axvline(0, color="#111827", linewidth=1, linestyle="--")
        path = figure_dir / "main_growth_coefficients.png"
        grid.savefig(path, dpi=220, bbox_inches="tight")
        plt.close(grid.fig)
        paths.append(path)
    bins = income_bins[income_bins["status"].eq("ok")].copy()
    if not bins.empty:
        bins["measure"] = bins["flow"] + " " + bins["dimension"].str.title() + " " + bins["metric"].str.replace("_", " ")
        grid = sns.catplot(data=bins, x="coefficient", y="measure", hue="income_bin", col="exposure_label", kind="point", errorbar=None, height=5.2, aspect=1.15, sharex=False)
        for ax in grid.axes.flat:
            ax.axvline(0, color="#111827", linewidth=1, linestyle="--")
        path = figure_dir / "income_bin_slopes.png"
        grid.savefig(path, dpi=220, bbox_inches="tight")
        plt.close(grid.fig)
        paths.append(path)
    return paths


def safe_markdown(frame: pd.DataFrame) -> str:
    try:
        return frame.to_markdown(index=False)
    except Exception:
        return "```csv\n" + frame.to_csv(index=False) + "```"


def write_memo(memo_path: Path, args: argparse.Namespace, diagnostics: pd.DataFrame, main_models: pd.DataFrame, robustness: pd.DataFrame, income_bins: pd.DataFrame, threshold_scan: pd.DataFrame) -> None:
    primary = main_models[main_models["term"].isin(primary_terms().values())].round(4)
    robustness_primary = robustness[
        robustness.apply(lambda row: row["term"] == primary_term_for_model(str(row["model_label"]), str(row["exposure"])), axis=1)
    ].round(4)
    text = f"""# Growth Effect Test

Generated: {now_utc()}

This is a descriptive panel exercise. It tests whether lagged real per-capita GDP or GNI growth is associated with next-year concentration levels. It does not estimate a causal effect of income growth.

## Specification

```text
concentration_cft = beta prior_pc_income_growth_c,t-1 + theta log_pc_income_level_c,t-1 + delta log_population_c,t-1 + country FE + year FE + error_cft
```

The future-growth placebo uses post-outcome growth, `log income_c,t+1 - log income_c,t`, and therefore drops outcome-years without a consecutive post-outcome control year.

## Main Lagged Growth Coefficients

{safe_markdown(primary[["exposure_label", "flow", "dimension", "metric", "coefficient", "std_error", "p_value", "bh_q_value", "nobs", "clusters", "status"]])}

## Robustness Checks

{safe_markdown(robustness_primary[["model_label", "exposure_label", "flow", "dimension", "metric", "coefficient", "std_error", "p_value", "bh_q_value", "nobs", "clusters", "status"]])}

## Income-Level Heterogeneity

{safe_markdown(income_bins.round(4))}

## Exploratory Threshold Scan

{safe_markdown(threshold_scan.round(4))}

## Sample Diagnostics

{safe_markdown(diagnostics)}
"""
    memo_path.write_text(text, encoding="utf-8")


def write_manifest(manifest_path: Path, args: argparse.Namespace, panel: pd.DataFrame, main_models: pd.DataFrame, robustness: pd.DataFrame, income_bins: pd.DataFrame, threshold_scan: pd.DataFrame, output_paths: dict[str, Path | list[Path]]) -> None:
    robustness_primary = robustness.apply(lambda row: row["term"] == primary_term_for_model(str(row["model_label"]), str(row["exposure"])), axis=1)
    manifest = {
        "created_at_utc": now_utc(),
        "country_sample": args.country_sample,
        "start_year": args.start_year,
        "end_year": args.end_year,
        "model": "country and year fixed effects with lagged real per-capita income growth",
        "causal_claim": False,
        "rows_panel": int(len(panel)),
        "countries": int(panel["iso3"].nunique()),
        "years": [int(panel["year"].min()), int(panel["year"].max())],
        "main_models_ok": int((main_models["status"].eq("ok") & main_models["term"].isin(primary_terms().values())).sum()),
        "robustness_models_ok": int((robustness["status"].eq("ok") & robustness_primary).sum()),
        "income_bin_rows_ok": int(income_bins["status"].eq("ok").sum()) if not income_bins.empty else 0,
        "threshold_scan_rows_ok": int(threshold_scan["status"].eq("ok").sum()) if not threshold_scan.empty else 0,
        "world_bank_indicators": {exposure: spec["indicator"] for exposure, spec in EXPOSURES.items()},
        "future_placebo_definition": "log real per-capita income in t+1 minus log real per-capita income in t",
        "sources": {
            "concentration": source_manifest(sample_processed_path("concentration_all_years.parquet", args.country_sample)),
            "growth_controls_cache": source_manifest(sample_processed_path("growth_effect_world_bank_controls.csv", args.country_sample)),
            "country_metadata": source_manifest(COUNTRY_METADATA),
        },
        "outputs": {key: [rel(p) for p in value] if isinstance(value, list) else rel(value) for key, value in output_paths.items()},
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def run(args: argparse.Namespace) -> None:
    base_results = sample_results_dir(args.country_sample)
    table_dir = base_results / "growth_effect_tables"
    figure_dir = base_results / "growth_effect_figures"
    panel_path = sample_processed_path("growth_effect_panel.parquet", args.country_sample)
    ensure_dirs(table_dir, figure_dir, panel_path.parent)
    panel, controls, missing_controls = build_growth_panel(args)
    validate_exposure_coverage(panel)
    diagnostics = sample_diagnostics(panel, controls, missing_controls, args)
    panel.to_parquet(panel_path, index=False)
    missing_path = table_dir / "missing_controls.csv"
    diagnostics_path = table_dir / "sample_diagnostics.csv"
    missing_controls.to_csv(missing_path, index=False)
    diagnostics.to_csv(diagnostics_path, index=False)
    main_models = run_main_models(panel, args.country_sample)
    robustness = run_robustness_models(panel, args.country_sample)
    income_bins = run_income_bin_models(panel, args.country_sample)
    threshold_scan = run_threshold_scan(panel, args.country_sample)
    main_path = table_dir / "main_models.csv"
    robustness_path = table_dir / "robustness_models.csv"
    income_bin_path = table_dir / "income_bin_slopes.csv"
    threshold_path = table_dir / "threshold_scan.csv"
    main_models.to_csv(main_path, index=False)
    robustness.to_csv(robustness_path, index=False)
    income_bins.to_csv(income_bin_path, index=False)
    threshold_scan.to_csv(threshold_path, index=False)
    figure_paths = make_growth_figures(main_models, income_bins, figure_dir)
    memo_path = base_results / "growth_effect.md"
    manifest_path = base_results / "run_manifest_growth_effect.json"
    output_paths: dict[str, Path | list[Path]] = {"panel": panel_path, "main_models": main_path, "robustness_models": robustness_path, "income_bin_slopes": income_bin_path, "threshold_scan": threshold_path, "sample_diagnostics": diagnostics_path, "missing_controls": missing_path, "figures": figure_paths, "memo": memo_path, "manifest": manifest_path}
    write_memo(memo_path, args, diagnostics, main_models, robustness, income_bins, threshold_scan)
    write_manifest(manifest_path, args, panel, main_models, robustness, income_bins, threshold_scan, output_paths)
    print(f"Wrote {rel(memo_path)}")
    print(f"Wrote {rel(main_path)}")
    print(f"Wrote {rel(robustness_path)}")
    print(f"Wrote {rel(income_bin_path)}")
    print(f"Wrote {rel(threshold_path)}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country-sample", choices=COUNTRY_SAMPLE_CHOICES, default="rd2_countries")
    parser.add_argument("--start-year", type=int, default=1988)
    parser.add_argument("--end-year", type=int, default=2024)
    parser.add_argument("--refresh-controls", action="store_true")
    args = parser.parse_args(argv)
    if args.end_year < args.start_year:
        parser.error("--end-year must be greater than or equal to --start-year")
    return args


def main(argv: list[str] | None = None) -> None:
    run(parse_args(argv))


if __name__ == "__main__":
    main()
