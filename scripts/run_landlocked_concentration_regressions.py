#!/usr/bin/env python3
"""Landlocked-country regressions for import/export concentration.

This is a descriptive cross-country panel exercise. Landlocked status is a
time-invariant country attribute, so the reported specifications use year,
region, and size/income controls rather than country fixed effects.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import requests
from scipy.stats import t as student_t

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from trade_concentration_pipeline import sample_processed_path, sample_results_dir  # noqa: E402


COUNTRY_SAMPLE = "rd2_countries"
START_YEAR = 1988
END_YEAR = 2024
REST_COUNTRIES_URL = "https://restcountries.com/v3.1/all"
LANDLOCKED_FIELDS = "cca3,name,landlocked"
FLOWS = ("Imports", "Exports")
OUTCOME_SPECS = (
    ("product", "product_gini", "Product Gini"),
    ("partner", "partner_gini", "Partner Gini"),
)
MODEL_SPECS = (
    ("year_fe", ["landlocked"], ["year"], "Year FE"),
    ("year_region_fe", ["landlocked"], ["year", "region"], "Year + region FE"),
    (
        "year_size_income_fe",
        ["landlocked", "log_population", "log_gdp_per_capita"],
        ["year"],
        "Year FE + log population + log GDP per capita",
    ),
    (
        "year_region_size_income_fe",
        ["landlocked", "log_population", "log_gdp_per_capita"],
        ["year", "region"],
        "Year + region FE + log population + log GDP per capita",
    ),
)
PRIMARY_TERM = "landlocked"


@dataclass(frozen=True)
class ModelResult:
    model_label: str
    model_description: str
    flow: str
    dimension: str
    outcome: str
    outcome_label: str
    term: str
    coefficient: float
    std_error: float
    t_stat: float
    p_value: float
    ci_low: float
    ci_high: float
    nobs: int
    clusters: int
    r_squared: float
    status: str
    candidate_rows: int
    dropped_rows: int
    fixed_effects: str
    controls: str
    se_method: str
    p_value_reference: str
    dropped_regressors: str


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


def validate_unique(df: pd.DataFrame, keys: list[str], label: str) -> None:
    missing = [col for col in keys if col not in df.columns]
    if missing:
        raise RuntimeError(f"{label} is missing key columns: {missing}")
    dupes = int(df.duplicated(keys).sum())
    if dupes:
        examples = df.loc[df.duplicated(keys, keep=False), keys].head(10).to_dict("records")
        raise RuntimeError(f"{label} has duplicate keys on {keys}: {examples}")


def source_manifest(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"path": rel(path), "exists": False}
    stat = path.stat()
    return {
        "path": rel(path),
        "exists": True,
        "size_bytes": stat.st_size,
        "mtime_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat(),
    }


def load_concentration_panel(country_sample: str, start_year: int, end_year: int) -> pd.DataFrame:
    path = sample_processed_path("concentration_all_years.parquet", country_sample)
    if not path.exists():
        raise FileNotFoundError(f"Missing concentration panel: {path}")
    panel = pd.read_parquet(path)
    required = {
        "country",
        "iso3",
        "reporter_code",
        "year",
        "flow",
        "variant",
        "product_gini",
        "partner_gini",
    }
    missing = sorted(required - set(panel.columns))
    if missing:
        raise RuntimeError(f"Concentration panel is missing required columns: {missing}")
    panel = panel[panel["variant"].eq("baseline") & panel["year"].between(start_year, end_year)].copy()
    panel["iso3"] = panel["iso3"].astype(str).str.upper()
    panel["reporter_code"] = pd.to_numeric(panel["reporter_code"], errors="coerce").astype("Int64")
    panel["year"] = pd.to_numeric(panel["year"], errors="coerce").astype("Int64")
    panel = panel.dropna(subset=["iso3", "reporter_code", "year", "flow"]).copy()
    panel["reporter_code"] = panel["reporter_code"].astype(int)
    panel["year"] = panel["year"].astype(int)
    panel = panel[panel["flow"].isin(FLOWS)].copy()
    if panel.empty:
        raise RuntimeError("No baseline concentration rows remain after filters.")
    validate_unique(panel, ["iso3", "reporter_code", "year", "flow"], "concentration panel")
    for col in ["product_gini", "partner_gini"]:
        panel[col] = pd.to_numeric(panel[col], errors="coerce")
        bad = panel[col].notna() & ((panel[col] < 0) | (panel[col] > 1))
        if bool(bad.any()):
            raise RuntimeError(f"{col} has {int(bad.sum()):,} finite values outside [0, 1].")
    return panel


def load_world_bank_metadata(iso3s: Iterable[str]) -> pd.DataFrame:
    path = ROOT / "data" / "raw" / "world_bank_gdp" / "country_metadata.csv"
    requested = sorted({str(iso3).upper() for iso3 in iso3s})
    if not path.exists():
        raise FileNotFoundError(f"Missing World Bank metadata cache: {path}")
    metadata = pd.read_csv(path)
    required = {"iso3", "region", "income_group"}
    missing = sorted(required - set(metadata.columns))
    if missing:
        raise RuntimeError(f"World Bank metadata is missing columns: {missing}")
    metadata = metadata[["iso3", "region", "income_group"]].copy()
    metadata["iso3"] = metadata["iso3"].astype(str).str.upper()
    metadata["region"] = metadata["region"].replace("", np.nan).fillna("Unclassified").astype(str)
    metadata["income_group"] = metadata["income_group"].replace("", np.nan).fillna("Unclassified").astype(str)
    metadata = metadata.drop_duplicates("iso3", keep="last")
    missing_iso3s = sorted(set(requested) - set(metadata["iso3"]))
    if missing_iso3s:
        raise RuntimeError(f"World Bank metadata does not cover requested ISO3 codes: {missing_iso3s}")
    return metadata[metadata["iso3"].isin(requested)].copy()


def load_controls(country_sample: str, start_year: int, end_year: int, requested_keys: pd.DataFrame) -> pd.DataFrame:
    path = sample_processed_path("country_size_effect_world_bank_controls.csv", country_sample)
    if not path.exists():
        raise FileNotFoundError(f"Missing GDP/population controls: {path}")
    controls = pd.read_csv(path)
    required = {"iso3", "year", "gdp_current_usd", "population"}
    missing = sorted(required - set(controls.columns))
    if missing:
        raise RuntimeError(f"GDP/population controls are missing columns: {missing}")
    controls = controls[list(required)].copy()
    controls["iso3"] = controls["iso3"].astype(str).str.upper()
    controls["year"] = pd.to_numeric(controls["year"], errors="coerce")
    controls = controls.dropna(subset=["iso3", "year"]).copy()
    controls["year"] = controls["year"].astype(int)
    controls = controls[controls["year"].between(start_year, end_year)].copy()
    for col in ["gdp_current_usd", "population"]:
        controls[col] = pd.to_numeric(controls[col], errors="coerce")
    controls = controls.drop_duplicates(["iso3", "year"], keep="last")
    validate_unique(controls, ["iso3", "year"], "GDP/population controls")
    coverage = requested_keys.merge(controls, on=["iso3", "year"], how="left")
    complete = coverage[["gdp_current_usd", "population"]].notna().all(axis=1)
    if float(complete.mean()) < 0.90:
        missing_counts = coverage.loc[~complete].groupby("iso3").size().sort_values(ascending=False).head(10).to_dict()
        raise RuntimeError(f"GDP/population controls are too incomplete. Missing examples: {missing_counts}")
    return controls


def fetch_restcountries_landlocked() -> pd.DataFrame:
    response = requests.get(REST_COUNTRIES_URL, params={"fields": LANDLOCKED_FIELDS}, timeout=45)
    response.raise_for_status()
    payload = response.json()
    rows = []
    for item in payload:
        iso3 = str(item.get("cca3") or "").strip().upper()
        if not iso3:
            continue
        name = item.get("name") or {}
        rows.append(
            {
                "iso3": iso3,
                "restcountries_name": str(name.get("common") or name.get("official") or ""),
                "landlocked": bool(item.get("landlocked")),
                "landlocked_source": "REST Countries v3.1",
                "landlocked_source_url": f"{REST_COUNTRIES_URL}?fields={LANDLOCKED_FIELDS}",
                "landlocked_source_accessed_utc": now_utc(),
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        raise RuntimeError("REST Countries returned no landlocked metadata.")
    return out.drop_duplicates("iso3", keep="last")


def load_or_fetch_landlocked_metadata(
    countries: pd.DataFrame,
    country_sample: str,
    refresh: bool = False,
) -> pd.DataFrame:
    cache_path = sample_processed_path("landlocked_country_metadata.csv", country_sample)
    requested = countries[["iso3", "country", "reporter_code"]].drop_duplicates("iso3").copy()
    requested["iso3"] = requested["iso3"].astype(str).str.upper()
    if cache_path.exists() and not refresh:
        cached = pd.read_csv(cache_path)
        needed = {"iso3", "country", "reporter_code", "landlocked"}
        if needed.issubset(cached.columns):
            cached["iso3"] = cached["iso3"].astype(str).str.upper()
            if set(requested["iso3"]).issubset(set(cached["iso3"])):
                return cached[cached["iso3"].isin(requested["iso3"])].drop_duplicates("iso3", keep="last").copy()

    fetched = fetch_restcountries_landlocked()
    out = requested.merge(fetched, on="iso3", how="left", validate="one_to_one")
    missing = sorted(out.loc[out["landlocked"].isna(), "iso3"].unique())
    if missing:
        raise RuntimeError(f"REST Countries metadata does not cover requested ISO3 codes: {missing}")
    out["landlocked"] = out["landlocked"].astype(bool)
    out["landlocked_label"] = np.where(out["landlocked"], "Landlocked", "Coastal or island")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(cache_path, index=False)
    return out


def construct_panel(args: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    concentration = load_concentration_panel(args.country_sample, args.start_year, args.end_year)
    requested_keys = concentration[["iso3", "year"]].drop_duplicates()
    controls = load_controls(args.country_sample, args.start_year, args.end_year, requested_keys)
    country_metadata = load_world_bank_metadata(concentration["iso3"].unique())
    landlocked = load_or_fetch_landlocked_metadata(
        concentration[["country", "iso3", "reporter_code"]].drop_duplicates(),
        args.country_sample,
        refresh=args.refresh_landlocked,
    )

    panel = concentration.merge(controls, on=["iso3", "year"], how="left", validate="many_to_one")
    panel = panel.merge(country_metadata, on="iso3", how="left", validate="many_to_one")
    panel = panel.merge(
        landlocked[["iso3", "landlocked", "landlocked_label", "landlocked_source"]],
        on="iso3",
        how="left",
        validate="many_to_one",
    )
    panel["landlocked"] = panel["landlocked"].astype(float)
    panel["log_population"] = np.where(panel["population"] > 0, np.log(panel["population"]), np.nan)
    panel["log_gdp_current_usd"] = np.where(panel["gdp_current_usd"] > 0, np.log(panel["gdp_current_usd"]), np.nan)
    panel["log_gdp_per_capita"] = panel["log_gdp_current_usd"] - panel["log_population"]
    panel["region"] = panel["region"].replace("", np.nan).fillna("Unclassified").astype(str)
    validate_unique(panel, ["iso3", "reporter_code", "year", "flow"], "final regression panel")
    return panel, concentration, controls, landlocked


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


def empty_model_row(
    model_label: str,
    model_description: str,
    flow: str,
    dimension: str,
    outcome: str,
    outcome_label: str,
    term: str,
    fixed_effects: list[str],
    terms: list[str],
    candidate_rows: int,
    status: str,
) -> ModelResult:
    return ModelResult(
        model_label=model_label,
        model_description=model_description,
        flow=flow,
        dimension=dimension,
        outcome=outcome,
        outcome_label=outcome_label,
        term=term,
        coefficient=np.nan,
        std_error=np.nan,
        t_stat=np.nan,
        p_value=np.nan,
        ci_low=np.nan,
        ci_high=np.nan,
        nobs=0,
        clusters=0,
        r_squared=np.nan,
        status=status,
        candidate_rows=candidate_rows,
        dropped_rows=candidate_rows,
        fixed_effects=",".join(fixed_effects) or "none",
        controls=",".join(t for t in terms if t != PRIMARY_TERM) or "none",
        se_method="none",
        p_value_reference="",
        dropped_regressors="",
    )


def run_ols_model(
    df: pd.DataFrame,
    outcome: str,
    outcome_label: str,
    flow: str,
    dimension: str,
    model_label: str,
    model_description: str,
    terms: list[str],
    fixed_effects: list[str],
    cluster_col: str = "reporter_code",
) -> list[ModelResult]:
    required = list(dict.fromkeys([outcome, *terms, *fixed_effects, cluster_col]))
    candidate_rows = int(len(df))
    missing_required = [col for col in required if col not in df.columns]
    if missing_required:
        return [
            empty_model_row(
                model_label,
                model_description,
                flow,
                dimension,
                outcome,
                outcome_label,
                term,
                fixed_effects,
                terms,
                candidate_rows,
                f"missing_required_columns:{','.join(missing_required)}",
            )
            for term in terms
        ]
    work = df.replace([np.inf, -np.inf], np.nan).dropna(subset=required).copy()
    dropped_rows = int(candidate_rows - len(work))
    if len(work) < len(terms) + 3:
        return [
            empty_model_row(
                model_label,
                model_description,
                flow,
                dimension,
                outcome,
                outcome_label,
                term,
                fixed_effects,
                terms,
                candidate_rows,
                "insufficient_sample",
            )
            for term in terms
        ]
    y = pd.to_numeric(work[outcome], errors="coerce").to_numpy(dtype=float)
    x_df, dropped_regressors = design_matrix(work, terms, fixed_effects)
    if x_df.shape[0] <= x_df.shape[1]:
        return [
            empty_model_row(
                model_label,
                model_description,
                flow,
                dimension,
                outcome,
                outcome_label,
                term,
                fixed_effects,
                terms,
                candidate_rows,
                "too_many_regressors",
            )
            for term in terms
        ]

    x = x_df.to_numpy(dtype=float)
    beta_all, *_ = np.linalg.lstsq(x, y, rcond=None)
    fitted = x @ beta_all
    resid = y - fitted
    clusters = int(work[cluster_col].nunique())
    if clusters <= 1:
        cov = np.full((x.shape[1], x.shape[1]), np.nan)
        p_reference_df = np.nan
        se_method = f"clustered by {cluster_col}; insufficient clusters"
    else:
        cov = cluster_robust_covariance(x, resid, work[cluster_col])
        p_reference_df = float(clusters - 1)
        se_method = f"clustered by {cluster_col}"
    se_all = np.sqrt(np.maximum(np.diag(cov), 0)) if np.isfinite(cov).any() else np.full(x.shape[1], np.nan)
    total_var = float(np.sum(np.square(y - y.mean())))
    r_squared = float(1 - np.sum(np.square(resid)) / total_var) if total_var > 0 else np.nan
    critical = student_t.ppf(0.975, p_reference_df) if np.isfinite(p_reference_df) else np.nan
    rows: list[ModelResult] = []
    absorbed = [term for term in terms if term not in x_df.columns]
    status = "ok" if not absorbed else "terms_absorbed:" + ",".join(absorbed)
    for term in terms:
        if term in x_df.columns:
            idx = x_df.columns.get_loc(term)
            coef = float(beta_all[idx])
            stderr = float(se_all[idx])
            t_stat = coef / stderr if np.isfinite(stderr) and stderr > 0 else np.nan
            p_value = (
                float(2 * student_t.sf(abs(t_stat), p_reference_df))
                if np.isfinite(t_stat) and np.isfinite(p_reference_df)
                else np.nan
            )
            ci_low = float(coef - critical * stderr) if np.isfinite(critical) and np.isfinite(stderr) else np.nan
            ci_high = float(coef + critical * stderr) if np.isfinite(critical) and np.isfinite(stderr) else np.nan
        else:
            coef = stderr = t_stat = p_value = ci_low = ci_high = np.nan
        rows.append(
            ModelResult(
                model_label=model_label,
                model_description=model_description,
                flow=flow,
                dimension=dimension,
                outcome=outcome,
                outcome_label=outcome_label,
                term=term,
                coefficient=coef,
                std_error=stderr,
                t_stat=t_stat,
                p_value=p_value,
                ci_low=ci_low,
                ci_high=ci_high,
                nobs=int(len(work)),
                clusters=clusters,
                r_squared=r_squared,
                status=status,
                candidate_rows=candidate_rows,
                dropped_rows=dropped_rows,
                fixed_effects=",".join(fixed_effects) or "none",
                controls=",".join(t for t in terms if t != PRIMARY_TERM) or "none",
                se_method=se_method,
                p_value_reference=f"Student t, df={int(p_reference_df)}" if np.isfinite(p_reference_df) else "",
                dropped_regressors=",".join(dropped_regressors),
            )
        )
    return rows


def benjamini_hochberg(p_values: pd.Series) -> pd.Series:
    values = pd.to_numeric(p_values, errors="coerce")
    q_values = pd.Series(np.nan, index=values.index, dtype=float)
    valid = values.dropna()
    m = len(valid)
    if not m:
        return q_values
    order = valid.sort_values().index
    sorted_p = valid.loc[order].to_numpy(dtype=float)
    adjusted = sorted_p * m / np.arange(1, m + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    q_values.loc[order] = np.clip(adjusted, 0, 1)
    return q_values


def run_models(panel: pd.DataFrame) -> pd.DataFrame:
    rows: list[ModelResult] = []
    for model_label, terms, fixed_effects, model_description in MODEL_SPECS:
        for flow in FLOWS:
            flow_panel = panel[panel["flow"].eq(flow)].copy()
            for dimension, outcome, outcome_label in OUTCOME_SPECS:
                rows.extend(
                    run_ols_model(
                        flow_panel,
                        outcome=outcome,
                        outcome_label=outcome_label,
                        flow=flow,
                        dimension=dimension,
                        model_label=model_label,
                        model_description=model_description,
                        terms=list(terms),
                        fixed_effects=list(fixed_effects),
                    )
                )
    out = pd.DataFrame([row.__dict__ for row in rows])
    out["bh_q_value"] = np.nan
    for model_label in out["model_label"].dropna().unique():
        mask = out["model_label"].eq(model_label) & out["term"].eq(PRIMARY_TERM) & out["status"].eq("ok")
        out.loc[mask, "bh_q_value"] = benjamini_hochberg(out.loc[mask, "p_value"])
    out["coefficient_gini_pct_points"] = out["coefficient"] * 100
    out["ci_low_gini_pct_points"] = out["ci_low"] * 100
    out["ci_high_gini_pct_points"] = out["ci_high"] * 100
    return out


def fmt_num(value: object, digits: int = 3) -> str:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return ""
    if not np.isfinite(x):
        return ""
    return f"{x:.{digits}f}"


def fmt_p(value: object) -> str:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return ""
    if not np.isfinite(x):
        return ""
    text = "<0.001" if x < 0.001 else f"{x:.3f}"
    return f"**{text}**" if x < 0.05 else text


def fmt_coef(value: object, p_value: object, digits: int = 2) -> str:
    text = fmt_num(value, digits)
    try:
        p = float(p_value)
    except (TypeError, ValueError):
        p = np.nan
    return f"**{text}**" if text and np.isfinite(p) and p < 0.05 else text


def markdown_table(df: pd.DataFrame, columns: list[str]) -> str:
    if df.empty:
        return "_No rows._"
    return df[columns].to_markdown(index=False)


def build_diagnostics(panel: pd.DataFrame, concentration: pd.DataFrame, controls: pd.DataFrame, landlocked: pd.DataFrame) -> pd.DataFrame:
    country_frame = panel[["iso3", "country", "reporter_code", "landlocked_label", "region", "income_group"]].drop_duplicates("iso3")
    diagnostics = [
        {"diagnostic": "country_sample", "value": COUNTRY_SAMPLE, "detail": "default non-website empirical sample used for this run"},
        {"diagnostic": "start_year", "value": int(panel["year"].min()), "detail": ""},
        {"diagnostic": "end_year", "value": int(panel["year"].max()), "detail": ""},
        {"diagnostic": "concentration_rows_after_filter", "value": len(concentration), "detail": "baseline rows, Imports/Exports only"},
        {"diagnostic": "final_panel_rows", "value": len(panel), "detail": "reporter-country-year-flow rows"},
        {"diagnostic": "country_count", "value": int(panel["iso3"].nunique()), "detail": ""},
        {"diagnostic": "landlocked_country_count", "value": int(country_frame["landlocked_label"].eq("Landlocked").sum()), "detail": ""},
        {"diagnostic": "coastal_or_island_country_count", "value": int(country_frame["landlocked_label"].ne("Landlocked").sum()), "detail": ""},
        {"diagnostic": "year_count", "value": int(panel["year"].nunique()), "detail": ""},
        {"diagnostic": "controls_country_year_rows", "value": len(controls), "detail": "GDP and population cache rows"},
        {"diagnostic": "missing_log_population_rows", "value": int(panel["log_population"].isna().sum()), "detail": ""},
        {"diagnostic": "missing_log_gdp_per_capita_rows", "value": int(panel["log_gdp_per_capita"].isna().sum()), "detail": ""},
        {"diagnostic": "missing_import_product_gini_rows", "value": int(panel.loc[panel["flow"].eq("Imports"), "product_gini"].isna().sum()), "detail": ""},
        {"diagnostic": "missing_import_partner_gini_rows", "value": int(panel.loc[panel["flow"].eq("Imports"), "partner_gini"].isna().sum()), "detail": ""},
        {"diagnostic": "missing_export_product_gini_rows", "value": int(panel.loc[panel["flow"].eq("Exports"), "product_gini"].isna().sum()), "detail": ""},
        {"diagnostic": "missing_export_partner_gini_rows", "value": int(panel.loc[panel["flow"].eq("Exports"), "partner_gini"].isna().sum()), "detail": ""},
        {"diagnostic": "landlocked_metadata_rows", "value": len(landlocked), "detail": "one row per requested ISO3"},
        {
            "diagnostic": "landlocked_countries",
            "value": int(country_frame["landlocked_label"].eq("Landlocked").sum()),
            "detail": "; ".join(
                country_frame.loc[country_frame["landlocked_label"].eq("Landlocked")]
                .sort_values("country")
                .apply(lambda row: f"{row['country']} ({row['iso3']})", axis=1)
                .tolist()
            ),
        },
    ]
    for flow, count in panel["flow"].value_counts().sort_index().items():
        diagnostics.append({"diagnostic": f"flow_rows_{flow.lower()}", "value": int(count), "detail": ""})
    return pd.DataFrame(diagnostics)


def write_outputs(
    args: argparse.Namespace,
    panel: pd.DataFrame,
    concentration: pd.DataFrame,
    controls: pd.DataFrame,
    landlocked: pd.DataFrame,
    models: pd.DataFrame,
) -> dict[str, Path]:
    out_dir = sample_results_dir(args.country_sample) / "landlocked_concentration_regressions"
    table_dir = out_dir / "tables"
    ensure_dirs(out_dir, table_dir)

    diagnostics = build_diagnostics(panel, concentration, controls, landlocked)
    panel_path = table_dir / "landlocked_concentration_panel.csv"
    models_path = table_dir / "landlocked_concentration_models.csv"
    diagnostics_path = table_dir / "landlocked_concentration_diagnostics.csv"
    landlocked_path = table_dir / "landlocked_country_metadata.csv"
    memo_path = out_dir / "landlocked_concentration_regressions.md"
    manifest_path = sample_results_dir(args.country_sample) / "run_manifest_landlocked_concentration_regressions.json"

    panel.to_csv(panel_path, index=False)
    models.to_csv(models_path, index=False)
    diagnostics.to_csv(diagnostics_path, index=False)
    landlocked.to_csv(landlocked_path, index=False)

    primary = models[models["term"].eq(PRIMARY_TERM)].copy()
    primary["flow_dimension"] = primary["flow"] + " - " + primary["outcome_label"]
    primary["coef_pp_fmt"] = primary.apply(lambda row: fmt_coef(row["coefficient_gini_pct_points"], row["p_value"], 2), axis=1)
    primary["se_pp_fmt"] = primary["std_error"].mul(100).map(lambda value: fmt_num(value, 2))
    primary["p_fmt"] = primary["p_value"].map(fmt_p)
    primary["q_fmt"] = primary["bh_q_value"].map(fmt_p)
    primary["nobs_fmt"] = primary["nobs"].map(lambda value: f"{int(value):,}" if pd.notna(value) else "")
    primary["clusters_fmt"] = primary["clusters"].map(lambda value: f"{int(value):,}" if pd.notna(value) else "")
    primary["r2_fmt"] = primary["r_squared"].map(lambda value: fmt_num(value, 3))

    adjusted = primary[primary["model_label"].eq("year_region_size_income_fe")].copy()
    all_table = primary[
        [
            "model_label",
            "flow_dimension",
            "coef_pp_fmt",
            "se_pp_fmt",
            "p_fmt",
            "q_fmt",
            "nobs_fmt",
            "clusters_fmt",
            "r2_fmt",
            "status",
        ]
    ].rename(
        columns={
            "model_label": "model",
            "flow_dimension": "flow/outcome",
            "coef_pp_fmt": "landlocked coef, Gini pct-pts",
            "se_pp_fmt": "SE",
            "p_fmt": "raw p",
            "q_fmt": "BH q",
            "nobs_fmt": "N",
            "clusters_fmt": "countries",
            "r2_fmt": "R2",
        }
    )
    adjusted_table = adjusted[
        [
            "flow_dimension",
            "coef_pp_fmt",
            "se_pp_fmt",
            "p_fmt",
            "q_fmt",
            "nobs_fmt",
            "clusters_fmt",
            "r2_fmt",
        ]
    ].rename(
        columns={
            "flow_dimension": "flow/outcome",
            "coef_pp_fmt": "landlocked coef, Gini pct-pts",
            "se_pp_fmt": "SE",
            "p_fmt": "raw p",
            "q_fmt": "BH q",
            "nobs_fmt": "N",
            "clusters_fmt": "countries",
            "r2_fmt": "R2",
        }
    )

    country_counts = (
        panel[["iso3", "country", "landlocked_label"]]
        .drop_duplicates("iso3")
        .groupby("landlocked_label", as_index=False)
        .size()
        .rename(columns={"landlocked_label": "country type", "size": "countries"})
    )
    model_rows = "\n".join(f"- `{label}`: {description}." for label, _terms, _fe, description in MODEL_SPECS)
    landlocked_list = diagnostics.loc[diagnostics["diagnostic"].eq("landlocked_countries"), "detail"].iloc[0]
    memo = f"""# Landlocked Status and Import/Export Concentration

Generated: {now_utc()}

## Design

Question: are landlocked reporters more or less concentrated in imports and exports across products and partners?

Estimand: the descriptive average difference in country-year concentration between landlocked and coastal/island reporters in the `{args.country_sample}` panel, separately by flow and concentration dimension.

Unit of observation: reporter-country-year-flow. Outcomes are Gini concentration measures in `[0, 1]`; higher values mean concentration is more uneven. The coefficient table reports the landlocked coefficient in Gini percentage points, i.e. `100 * beta`.

Estimated equation:

`concentration_c,t = beta * landlocked_c + controls_c,t + fixed effects + error_c,t`

Landlocked is time invariant, so country fixed effects are not included because they would absorb the regressor. Standard errors are clustered by reporter country.

Models:
{model_rows}

## Data Rules

- Sample: `{args.country_sample}`, years {args.start_year}-{args.end_year}.
- Product concentration uses the repo's product convention: HS6 `999999` is excluded before product-level aggregation.
- Partner concentration uses the repo's partner convention: HS6 `999999` remains in reporter-partner totals, while `partnerCode == 0` / World is excluded upstream.
- Landlocked metadata source: REST Countries v3.1 field `landlocked`, cached to `{rel(sample_processed_path('landlocked_country_metadata.csv', args.country_sample))}`.
- Region and income-group labels come from the local World Bank metadata cache.

## Adjusted Result

Primary adjusted specification: `year_region_size_income_fe`.

{markdown_table(adjusted_table, list(adjusted_table.columns))}

Interpretation: positive coefficients mean landlocked reporters have higher concentration than coastal/island reporters after the listed controls. Negative coefficients mean lower concentration. Bold coefficients and raw p-values mark `p < 0.05`; bold q-values mark Benjamini-Hochberg `q < 0.05` within each model's four landlocked tests.

## All Landlocked Coefficients

{markdown_table(all_table, list(all_table.columns))}

## Sample Diagnostics

{markdown_table(country_counts, list(country_counts.columns))}

Landlocked countries in this sample: {landlocked_list}.

Key diagnostics:

{markdown_table(diagnostics[["diagnostic", "value", "detail"]], ["diagnostic", "value", "detail"])}

## Output Files

- Panel: `{rel(panel_path)}`
- Model table: `{rel(models_path)}`
- Diagnostics: `{rel(diagnostics_path)}`
- Landlocked metadata: `{rel(landlocked_path)}`
- Manifest: `{rel(manifest_path)}`

## Caveat

This is descriptive, not a causal estimate of landlocked geography. Landlocked status is correlated with region, income, colonial history, market access, infrastructure, trade agreements, resource structure, and neighbor composition; the adjusted models only absorb a limited subset of those differences.
"""
    memo_path.write_text(memo)

    manifest = {
        "created_utc": now_utc(),
        "script": rel(Path(__file__)),
        "country_sample": args.country_sample,
        "start_year": args.start_year,
        "end_year": args.end_year,
        "outputs": {
            "memo": rel(memo_path),
            "panel": rel(panel_path),
            "models": rel(models_path),
            "diagnostics": rel(diagnostics_path),
            "landlocked_metadata": rel(landlocked_path),
        },
        "sources": {
            "concentration": source_manifest(sample_processed_path("concentration_all_years.parquet", args.country_sample)),
            "controls": source_manifest(sample_processed_path("country_size_effect_world_bank_controls.csv", args.country_sample)),
            "world_bank_metadata": source_manifest(ROOT / "data" / "raw" / "world_bank_gdp" / "country_metadata.csv"),
            "landlocked_cache": source_manifest(sample_processed_path("landlocked_country_metadata.csv", args.country_sample)),
        },
        "model_specs": [
            {"model_label": label, "terms": terms, "fixed_effects": fixed_effects, "description": description}
            for label, terms, fixed_effects, description in MODEL_SPECS
        ],
        "data_rules": {
            "product_999999": "excluded upstream before product-level aggregation",
            "partner_999999": "included in partner totals by partner-only convention",
            "partner_world_code_0": "excluded upstream",
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return {
        "memo": memo_path,
        "panel": panel_path,
        "models": models_path,
        "diagnostics": diagnostics_path,
        "landlocked_metadata": landlocked_path,
        "manifest": manifest_path,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country-sample", default=COUNTRY_SAMPLE, choices=("rd2_countries", "prof_p_33"))
    parser.add_argument("--start-year", type=int, default=START_YEAR)
    parser.add_argument("--end-year", type=int, default=END_YEAR)
    parser.add_argument("--refresh-landlocked", action="store_true", help="Refresh REST Countries landlocked metadata.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    started = time.time()
    panel, concentration, controls, landlocked = construct_panel(args)
    models = run_models(panel)
    paths = write_outputs(args, panel, concentration, controls, landlocked, models)
    print(f"Wrote memo: {paths['memo']}")
    print(f"Wrote model table: {paths['models']}")
    print(f"Rows: panel={len(panel):,}, models={len(models):,}, elapsed={time.time() - started:.1f}s")


if __name__ == "__main__":
    main()
