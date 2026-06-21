#!/usr/bin/env python3
"""Audit rd2 regression inputs, attrition, standardization, and weights.

This script is intentionally report-only. It reads current rd2 artifacts and
writes audit tables plus a Markdown report without changing canonical panels or
regression outputs.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.stats import t as student_t


ROOT = Path(__file__).resolve().parents[1]
DATA_PROCESSED = ROOT / "data" / "processed"
RESULTS = ROOT / "results"
EXCLUDED_HS6_CODES = {"999999"}

OUTCOME_SPECS = (
    ("product", "gini", "product_gini", "Product Gini"),
    ("partner", "gini", "partner_gini", "Partner Gini"),
    ("product", "top_1pct_share", "product_top_1pct_share", "Product top 1% share"),
    ("product", "top_5pct_share", "product_top_5pct_share", "Product top 5% share"),
    ("partner", "top_1pct_share", "partner_top_1pct_share", "Partner top 1% share"),
    ("partner", "top_5pct_share", "partner_top_5pct_share", "Partner top 5% share"),
)
FLOWS = ("Imports", "Exports")
E2_BUCKET_TERMS = (
    "bucket_high_product_high_partner",
    "bucket_high_product_low_partner",
    "bucket_low_product_high_partner",
)
E2_TOP_SHARE_TERMS = (
    "top_share_bucket_high_product_high_partner",
    "top_share_bucket_high_product_low_partner",
    "top_share_bucket_low_product_high_partner",
)


@dataclass
class FitSummary:
    coefficient: float
    std_error: float
    p_value: float
    nobs: int
    clusters: int
    dropped_rows: int
    status: str


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


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def read_csv_if_exists(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def sample_processed_path(country_sample: str, filename: str) -> Path:
    return DATA_PROCESSED / "samples" / country_sample / filename


def sample_results_dir(country_sample: str) -> Path:
    return RESULTS / "samples" / country_sample


def normalize_cmd(series: pd.Series) -> pd.Series:
    return series.astype(str).str.extract(r"(\d{1,6})", expand=False).str.zfill(6)


def finite_numeric(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").astype(float)
    return values.replace([np.inf, -np.inf], np.nan)


def zscore(series: pd.Series) -> pd.Series:
    values = finite_numeric(series)
    sd = float(values.std(ddof=0))
    if not np.isfinite(sd) or sd == 0:
        return values * np.nan
    return (values - float(values.mean())) / sd


def within_zscore(df: pd.DataFrame, value_col: str, group_cols: list[str]) -> pd.Series:
    values = finite_numeric(df[value_col])
    grouped = values.groupby([df[col] for col in group_cols], dropna=False)
    means = grouped.transform("mean")
    sds = grouped.transform(lambda s: s.std(ddof=0))
    return (values - means) / sds.replace(0, np.nan)


def severity_from_conditions(red: Iterable[bool], yellow: Iterable[bool]) -> str:
    if any(red):
        return "red"
    if any(yellow):
        return "yellow"
    return "green"


def parquet_row_count(path: Path) -> int | None:
    if not path.exists():
        return None
    return int(pq.ParquetFile(path).metadata.num_rows)


def csv_row_count(path: Path) -> int | None:
    if not path.exists():
        return None
    return int(len(pd.read_csv(path)))


def validate_rd2_manifests(base_results: Path) -> list[str]:
    exercise_02_manifest = (
        base_results / "run_manifest_exercise_02_bucket_growth.json"
        if (base_results / "run_manifest_exercise_02_bucket_growth.json").exists()
        else RESULTS / "run_manifest_exercises_02_12.json"
    )
    required = {
        "country_size": base_results / "run_manifest_country_size_effect.json",
        "growth_effect": base_results / "run_manifest_growth_effect.json",
        "exercise_11": base_results / "run_manifest_exercise_11_product_export_linkage.json",
        "exercise_02_12": exercise_02_manifest,
    }
    blockers: list[str] = []
    for label, path in required.items():
        if not path.exists():
            blockers.append(f"Missing required manifest for {label}: {rel(path)}")
            continue
        manifest = read_json(path)
        if manifest.get("country_sample") != "rd2_countries":
            blockers.append(f"Manifest for {label} is not rd2_countries: {rel(path)}")
    return blockers


def artifact_row(
    family: str,
    artifact: str,
    path: Path,
    kind: str,
    df: pd.DataFrame | None = None,
    manifest: dict[str, Any] | None = None,
    key_cols: list[str] | None = None,
    product_code_col: str | None = None,
) -> dict[str, Any]:
    exists = path.exists()
    row_count: int | None
    if df is not None:
        row_count = int(len(df))
    elif kind == "parquet":
        row_count = parquet_row_count(path)
    elif kind == "csv":
        row_count = csv_row_count(path)
    else:
        row_count = None

    year_min = year_max = countries = country_years = duplicate_keys = None
    hs6_999999_rows = 0
    if df is not None and not df.empty:
        if "year" in df.columns:
            years = pd.to_numeric(df["year"], errors="coerce").dropna()
            if not years.empty:
                year_min, year_max = int(years.min()), int(years.max())
        if "reporter_code" in df.columns:
            countries = int(pd.to_numeric(df["reporter_code"], errors="coerce").nunique())
        if {"reporter_code", "year"}.issubset(df.columns):
            country_years = int(df[["reporter_code", "year"]].drop_duplicates().shape[0])
        if key_cols and set(key_cols).issubset(df.columns):
            duplicate_keys = int(df.duplicated(key_cols).sum())
        if product_code_col and product_code_col in df.columns:
            hs6_999999_rows = int(normalize_cmd(df[product_code_col]).isin(EXCLUDED_HS6_CODES).sum())

    sample = (manifest or {}).get("country_sample", "rd2_countries" if "samples/rd2_countries" in rel(path) else "")
    severity = severity_from_conditions(
        red=[not exists, bool(sample and sample != "rd2_countries"), hs6_999999_rows > 0],
        yellow=[],
    )
    return {
        "family": family,
        "artifact": artifact,
        "kind": kind,
        "path": rel(path),
        "exists": exists,
        "row_count": row_count,
        "country_sample": sample,
        "manifest_created_at_utc": (manifest or {}).get("created_at_utc", ""),
        "manifest_command": (manifest or {}).get("command", ""),
        "year_min": year_min,
        "year_max": year_max,
        "countries": countries,
        "country_years": country_years,
        "duplicate_key_count": duplicate_keys,
        "product_dependent_hs6_999999_rows": hs6_999999_rows,
        "severity": severity,
    }


def load_panels(country_sample: str) -> dict[str, pd.DataFrame]:
    return {
        "country_size": pd.read_parquet(sample_processed_path(country_sample, "country_size_effect_panel.parquet")),
        "growth": pd.read_parquet(sample_processed_path(country_sample, "growth_effect_panel.parquet")),
        "exercise_02": pd.read_parquet(sample_processed_path(country_sample, "exercise_02_bucket_growth_panel.parquet")),
        "ex11_product": pd.read_parquet(
            sample_processed_path(country_sample, "exercise_11_product_export_linkage_panel.parquet"),
            columns=[
                "reporter_code",
                "country",
                "iso3",
                "year",
                "cmd_code",
                "import_bin",
                "import_value",
                "import_value_share",
                "loo_gini_contribution",
                "loo_partner_hhi_contribution",
                "export_value",
                "export_any",
                "asinh_export_value",
                "is_intermediate",
            ],
        ),
        "ex11_hs2": pd.read_parquet(sample_processed_path(country_sample, "exercise_11_hs2_export_linkage_panel.parquet")),
        "ex11_sector": pd.read_parquet(sample_processed_path(country_sample, "exercise_11_sector_export_linkage_panel.parquet")),
    }


def build_artifact_inventory(country_sample: str, panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    base_results = sample_results_dir(country_sample)
    exercise_02_manifest = (
        base_results / "run_manifest_exercise_02_bucket_growth.json"
        if (base_results / "run_manifest_exercise_02_bucket_growth.json").exists()
        else RESULTS / "run_manifest_exercises_02_12.json"
    )
    manifests = {
        "country_size": read_json(base_results / "run_manifest_country_size_effect.json"),
        "growth": read_json(base_results / "run_manifest_growth_effect.json"),
        "exercise_02": read_json(exercise_02_manifest),
        "exercise_11": read_json(base_results / "run_manifest_exercise_11_product_export_linkage.json"),
    }
    artifacts = [
        ("country_size", "processed panel", sample_processed_path(country_sample, "country_size_effect_panel.parquet"), "parquet", panels["country_size"], manifests["country_size"], ["reporter_code", "year", "flow", "variant"], None),
        ("country_size", "main models", base_results / "country_size_effect_tables" / "main_models.csv", "csv", None, manifests["country_size"], None, None),
        ("country_size", "robustness models", base_results / "country_size_effect_tables" / "robustness_models.csv", "csv", None, manifests["country_size"], None, None),
        ("country_size", "two-way cluster models", base_results / "country_size_effect_tables" / "two_way_cluster_models.csv", "csv", None, manifests["country_size"], None, None),
        ("growth_effect", "processed panel", sample_processed_path(country_sample, "growth_effect_panel.parquet"), "parquet", panels["growth"], manifests["growth"], ["reporter_code", "year", "flow", "variant", "horizon"], None),
        ("growth_effect", "main models", base_results / "growth_effect_tables" / "main_models.csv", "csv", None, manifests["growth"], None, None),
        ("growth_effect", "robustness models", base_results / "growth_effect_tables" / "robustness_models.csv", "csv", None, manifests["growth"], None, None),
        ("growth_effect", "income-bin slopes", base_results / "growth_effect_tables" / "income_bin_slopes.csv", "csv", None, manifests["growth"], None, None),
        ("growth_effect", "threshold scan", base_results / "growth_effect_tables" / "threshold_scan.csv", "csv", None, manifests["growth"], None, None),
        ("exercise_02", "bucket growth panel", sample_processed_path(country_sample, "exercise_02_bucket_growth_panel.parquet"), "parquet", panels["exercise_02"], manifests["exercise_02"], ["reporter_code", "year", "horizon"], None),
        ("exercise_02", "bucket growth models", base_results / "exercise_02_tables" / "bucket_growth_models.csv", "csv", None, manifests["exercise_02"], None, None),
        ("exercise_02", "bucket growth diagnostics", base_results / "exercise_02_tables" / "bucket_growth_diagnostics.csv", "csv", None, manifests["exercise_02"], None, None),
        ("exercise_11", "product panel", sample_processed_path(country_sample, "exercise_11_product_export_linkage_panel.parquet"), "parquet", panels["ex11_product"], manifests["exercise_11"], ["reporter_code", "year", "cmd_code"], "cmd_code"),
        ("exercise_11", "HS2 panel", sample_processed_path(country_sample, "exercise_11_hs2_export_linkage_panel.parquet"), "parquet", panels["ex11_hs2"], manifests["exercise_11"], ["reporter_code", "year", "hs2"], None),
        ("exercise_11", "sector panel", sample_processed_path(country_sample, "exercise_11_sector_export_linkage_panel.parquet"), "parquet", panels["ex11_sector"], manifests["exercise_11"], ["reporter_code", "year", "io_sector_code"], None),
        ("exercise_11", "product regressions", base_results / "exercise_11_product_export_linkage_tables" / "product_regressions.csv", "csv", None, manifests["exercise_11"], None, None),
        ("exercise_11", "HS2 regressions", base_results / "exercise_11_product_export_linkage_tables" / "hs2_regressions.csv", "csv", None, manifests["exercise_11"], None, None),
        ("exercise_11", "sector regressions", base_results / "exercise_11_product_export_linkage_tables" / "sector_regressions.csv", "csv", None, manifests["exercise_11"], None, None),
    ]
    rows = [artifact_row(*args) for args in artifacts]
    rows.append(
        {
            "family": "exercise_13",
            "artifact": "root-level legacy outputs",
            "kind": "blocker_note",
            "path": "results/exercise_13_import_hypotheses_tables/",
            "exists": (RESULTS / "exercise_13_import_hypotheses_tables").exists(),
            "row_count": None,
            "country_sample": "not_rd2_current_output",
            "manifest_created_at_utc": read_json(RESULTS / "run_manifest_exercise_13_import_hypotheses.json").get("created_at_utc", ""),
            "manifest_command": read_json(RESULTS / "run_manifest_exercise_13_import_hypotheses.json").get("command", ""),
            "year_min": None,
            "year_max": None,
            "countries": None,
            "country_years": None,
            "duplicate_key_count": None,
            "product_dependent_hs6_999999_rows": None,
            "severity": "yellow",
        }
    )
    return pd.DataFrame(rows)


def design_matrix(work: pd.DataFrame, terms: list[str], fixed_effects: list[str]) -> tuple[pd.DataFrame, list[str]]:
    parts: list[pd.DataFrame | pd.Series] = [pd.Series(1.0, index=work.index, name="intercept")]
    for term in terms:
        parts.append(finite_numeric(work[term]).rename(term))
    for fe_col in fixed_effects:
        dummies = pd.get_dummies(work[fe_col].astype(str), prefix=fe_col, drop_first=True, dtype=float)
        if not dummies.empty:
            parts.append(dummies)
    x = pd.concat(parts, axis=1).astype(float)
    return full_rank_columns(x)


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


def cluster_wls_fit(
    y: np.ndarray,
    x: np.ndarray,
    clusters: np.ndarray,
    weights: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, int, str]:
    nobs, k = x.shape
    if nobs <= k or k == 0:
        return np.full(k, np.nan), np.full(k, np.nan), int(pd.Series(clusters).nunique()), "too_many_regressors"
    w = np.ones(nobs, dtype=float) if weights is None else np.asarray(weights, dtype=float)
    valid = np.isfinite(y) & np.isfinite(x).all(axis=1) & np.isfinite(w) & (w > 0)
    y, x, w, clusters = y[valid], x[valid], w[valid], clusters[valid]
    nobs, k = x.shape
    if nobs <= k or k == 0:
        return np.full(k, np.nan), np.full(k, np.nan), int(pd.Series(clusters).nunique()), "too_many_regressors"
    xw = x * w[:, None]
    xtwx_inv = np.linalg.pinv(x.T @ xw)
    beta = xtwx_inv @ (xw.T @ y)
    resid = y - x @ beta
    cluster_codes = pd.factorize(clusters, sort=False)[0].astype(np.int64)
    cluster_count = int(cluster_codes.max() + 1) if nobs else 0
    if cluster_count <= 1:
        return beta, np.full(k, np.nan), cluster_count, "insufficient_clusters"
    score = x * (w * resid)[:, None]
    score_sums = np.vstack(
        [np.bincount(cluster_codes, weights=score[:, col], minlength=cluster_count) for col in range(k)]
    ).T
    meat = score_sums.T @ score_sums
    scale = (cluster_count / (cluster_count - 1)) * ((nobs - 1) / (nobs - k)) if nobs > k else 1.0
    cov = scale * xtwx_inv @ meat @ xtwx_inv
    se = np.sqrt(np.maximum(np.diag(cov), 0))
    return beta, se, cluster_count, "ok"


def fit_dummy_ols(
    df: pd.DataFrame,
    outcome: str,
    terms: list[str],
    fixed_effects: list[str],
    cluster_col: str,
    target_term: str,
    weight_col: str | None = None,
) -> FitSummary:
    required = list(dict.fromkeys([outcome, *terms, *fixed_effects, cluster_col] + ([weight_col] if weight_col else [])))
    work = df.replace([np.inf, -np.inf], np.nan).dropna(subset=required).copy()
    dropped = int(len(df) - len(work))
    if work.empty:
        return FitSummary(np.nan, np.nan, np.nan, 0, 0, dropped, "empty_sample")
    x_df, _dropped_cols = design_matrix(work, terms, fixed_effects)
    y = finite_numeric(work[outcome]).to_numpy(dtype=float)
    weights = finite_numeric(work[weight_col]).to_numpy(dtype=float) if weight_col else None
    beta, se, clusters, status = cluster_wls_fit(y, x_df.to_numpy(dtype=float), work[cluster_col].to_numpy(), weights)
    if target_term not in x_df.columns:
        return FitSummary(np.nan, np.nan, np.nan, int(len(work)), clusters, dropped, "target_absorbed")
    idx = x_df.columns.get_loc(target_term)
    coef = float(beta[idx])
    stderr = float(se[idx])
    p_value = p_from_t(coef, stderr, clusters)
    return FitSummary(coef, stderr, p_value, int(len(work)), clusters, dropped, status)


def demean_by_codes(values: np.ndarray, codes: np.ndarray, weights: np.ndarray | None = None) -> np.ndarray:
    if weights is None:
        counts = np.bincount(codes).astype(float)
        out = values.copy()
        for col in range(values.shape[1]):
            sums = np.bincount(codes, weights=values[:, col], minlength=counts.size)
            means = np.divide(sums, counts, out=np.zeros_like(sums), where=counts > 0)
            out[:, col] -= means[codes]
        return out
    counts = np.bincount(codes, weights=weights).astype(float)
    out = values.copy()
    for col in range(values.shape[1]):
        sums = np.bincount(codes, weights=values[:, col] * weights, minlength=counts.size)
        means = np.divide(sums, counts, out=np.zeros_like(sums), where=counts > 0)
        out[:, col] -= means[codes]
    return out


def fit_country_year_fe_ols(
    df: pd.DataFrame,
    outcome: str,
    terms: list[str],
    fe_col: str,
    cluster_col: str,
    target_term: str,
    weight_col: str | None = None,
) -> FitSummary:
    required = list(dict.fromkeys([outcome, *terms, fe_col, cluster_col] + ([weight_col] if weight_col else [])))
    work = df[required].replace([np.inf, -np.inf], np.nan).dropna().copy()
    work = work.groupby(fe_col, sort=False).filter(lambda group: len(group) > 1)
    dropped = int(len(df) - len(work))
    if work.empty:
        return FitSummary(np.nan, np.nan, np.nan, 0, 0, dropped, "empty_sample")
    yx = work[[outcome, *terms]].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    weights = finite_numeric(work[weight_col]).to_numpy(dtype=float) if weight_col else None
    fe_codes = pd.factorize(work[fe_col], sort=False)[0].astype(np.int64)
    resid = demean_by_codes(yx, fe_codes, weights if weight_col else None)
    y = resid[:, 0]
    x = resid[:, 1:]
    beta, se, clusters, status = cluster_wls_fit(y, x, work[cluster_col].to_numpy(), weights)
    if target_term not in terms:
        return FitSummary(np.nan, np.nan, np.nan, int(len(work)), clusters, dropped, "missing_target")
    idx = terms.index(target_term)
    coef = float(beta[idx])
    stderr = float(se[idx])
    return FitSummary(coef, stderr, p_from_t(coef, stderr, clusters), int(len(work)), clusters, dropped, status)


def p_from_t(coef: float, stderr: float, clusters: int) -> float:
    if not np.isfinite(coef) or not np.isfinite(stderr) or stderr <= 0 or clusters <= 1:
        return np.nan
    return float(2 * student_t.sf(abs(coef / stderr), clusters - 1))


def add_equal_year_weight(df: pd.DataFrame, group_cols: list[str], out_col: str = "equal_year_weight") -> pd.DataFrame:
    out = df.copy()
    sizes = out.groupby(group_cols, dropna=False)[group_cols[0]].transform("size")
    out[out_col] = 1.0 / sizes.replace(0, np.nan)
    return out


def add_equal_cy_weight(df: pd.DataFrame, out_col: str = "equal_country_year_weight") -> pd.DataFrame:
    out = df.copy()
    sizes = out.groupby(["reporter_code", "year"], dropna=False)["year"].transform("size")
    out[out_col] = 1.0 / sizes.replace(0, np.nan)
    return out


def year_country_counts(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df[["year", "reporter_code"]]
        .drop_duplicates()
        .groupby("year", as_index=False)["reporter_code"]
        .nunique()
        .rename(columns={"reporter_code": "countries_in_year"})
    )


def build_sample_attrition(country_sample: str, panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    base_results = sample_results_dir(country_sample)
    rows: list[dict[str, Any]] = []

    for family, table_path in [
        ("country_size", base_results / "country_size_effect_tables" / "main_models.csv"),
        ("country_size", base_results / "country_size_effect_tables" / "robustness_models.csv"),
        ("country_size", base_results / "country_size_effect_tables" / "two_way_cluster_models.csv"),
        ("growth_effect", base_results / "growth_effect_tables" / "main_models.csv"),
        ("growth_effect", base_results / "growth_effect_tables" / "robustness_models.csv"),
        ("exercise_02", base_results / "exercise_02_tables" / "bucket_growth_diagnostics.csv"),
    ]:
        table = read_csv_if_exists(table_path)
        if table.empty:
            continue
        group_cols = [col for col in ["model_label", "sample", "exposure", "flow", "dimension", "metric", "outcome", "horizon"] if col in table.columns]
        for keys, group in table.groupby(group_cols, dropna=False):
            if not isinstance(keys, tuple):
                keys = (keys,)
            key_map = dict(zip(group_cols, keys))
            candidate = pd.to_numeric(group.get("candidate_rows", pd.Series(dtype=float)), errors="coerce").max()
            nobs = pd.to_numeric(group.get("nobs", pd.Series(dtype=float)), errors="coerce").max()
            dropped = pd.to_numeric(group.get("dropped_rows", pd.Series(dtype=float)), errors="coerce").max()
            clusters = pd.to_numeric(group.get("clusters", group.get("countries", pd.Series(dtype=float))), errors="coerce").max()
            attrition = float(dropped / candidate) if pd.notna(candidate) and candidate else np.nan
            rows.append(
                {
                    "family": family,
                    **key_map,
                    "candidate_rows": candidate,
                    "analytic_rows": nobs,
                    "dropped_rows": dropped,
                    "drop_share": attrition,
                    "clusters": clusters,
                    "missing_variables": group.get("missing_required_columns", pd.Series([""])).fillna("").astype(str).iloc[0]
                    if "missing_required_columns" in group.columns
                    else "",
                    "severity": severity_from_conditions(
                        red=[pd.notna(attrition) and attrition > 0.25, pd.notna(clusters) and clusters < 30],
                        yellow=[pd.notna(attrition) and attrition > 0.10, pd.notna(clusters) and clusters < 50],
                    ),
                }
            )

    ex11_specs = [
        (
            "exercise_11_product",
            panels["ex11_product"],
            "product_export_value_gini",
            "asinh_export_value",
            ["loo_gini_contribution", "import_value_share", "import_bin"],
            "reporter_code",
        ),
        (
            "exercise_11_product",
            panels["ex11_product"],
            "product_export_any_gini",
            "export_any",
            ["loo_gini_contribution", "import_value_share", "import_bin"],
            "reporter_code",
        ),
        (
            "exercise_11_hs2",
            panels["ex11_hs2"],
            "hs2_export_value_gini",
            "asinh_hs2_export_value",
            ["hs2_product_loo_gini_sum", "hs2_import_value_share", "hs2"],
            "reporter_code",
        ),
        (
            "exercise_11_sector",
            panels["ex11_sector"],
            "sector_export_share_gini",
            "sector_export_share",
            ["sector_loo_gini_contribution", "sector_import_value_share", "io_sector_code"],
            "reporter_code",
        ),
    ]
    for family, panel, model_label, outcome, required, cluster_col in ex11_specs:
        candidate = len(panel)
        work = panel.replace([np.inf, -np.inf], np.nan).dropna(subset=[outcome, *required, cluster_col]).copy()
        if {"reporter_code", "year"}.issubset(work.columns):
            sizes = work.groupby(["reporter_code", "year"])["year"].transform("size")
            work = work[sizes > 1].copy()
        dropped = candidate - len(work)
        clusters = int(work[cluster_col].nunique()) if not work.empty else 0
        attrition = dropped / candidate if candidate else np.nan
        rows.append(
            {
                "family": family,
                "model_label": model_label,
                "outcome": outcome,
                "candidate_rows": candidate,
                "analytic_rows": len(work),
                "dropped_rows": dropped,
                "drop_share": attrition,
                "clusters": clusters,
                "missing_variables": "",
                "severity": severity_from_conditions(
                    red=[attrition > 0.25, clusters < 30],
                    yellow=[attrition > 0.10, clusters < 50],
                ),
            }
        )
    return pd.DataFrame(rows)


def build_missingness(country_sample: str, panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    records: list[pd.DataFrame] = []

    specs = {
        "country_size": (panels["country_size"], ["log_population", "log_gdp_per_capita", *[spec[2] for spec in OUTCOME_SPECS]]),
        "growth_effect": (
            panels["growth"],
            [
                "prior_export_growth",
                "contemporaneous_export_growth",
                "future_export_growth",
                "lag_log_real_exports",
                "lag_log_population",
                *[spec[2] for spec in OUTCOME_SPECS],
            ],
        ),
        "exercise_02": (
            panels["exercise_02"],
            [
                "annualized_export_growth_log",
                "annualized_export_growth_log_ex_oil",
                "annualized_export_growth_log_us_deflated",
                "log_initial_exports",
                "oil_export_share",
                "log_gdp_current_usd",
                "log_population",
                "log_gni_per_capita_current_usd",
            ],
        ),
        "exercise_11_product": (
            panels["ex11_product"],
            ["loo_gini_contribution", "loo_partner_hhi_contribution", "import_value_share", "export_any", "asinh_export_value"],
        ),
        "exercise_11_hs2": (
            panels["ex11_hs2"],
            ["hs2_product_loo_gini_sum", "hs2_import_value_share", "hs2_export_any", "asinh_hs2_export_value"],
        ),
        "exercise_11_sector": (
            panels["ex11_sector"],
            ["sector_loo_gini_contribution", "sector_import_value_share", "sector_export_share"],
        ),
    }
    for family, (df, cols) in specs.items():
        keep = ["reporter_code", "country", "iso3", "year"] + [col for col in cols if col in df.columns]
        work = df[keep].copy()
        complete_cols = [col for col in cols if col in work.columns]
        work["rows"] = 1
        for col in complete_cols:
            work[f"{col}_missing"] = finite_numeric(work[col]).isna().astype(int)
        agg = work.groupby(["reporter_code", "country", "iso3", "year"], dropna=False, as_index=False).agg(
            rows=("rows", "sum"),
            **{f"{col}_missing_rows": (f"{col}_missing", "sum") for col in complete_cols},
        )
        agg.insert(0, "family", family)
        records.append(agg)
    return pd.concat(records, ignore_index=True, sort=False) if records else pd.DataFrame()


def build_standardization_audit(panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    rows.extend(
        [
            {
                "family": "country_size",
                "variable": "log_population/log_gdp_per_capita",
                "standardization_scope": "not standardized",
                "mean": np.nan,
                "sd": np.nan,
                "within_year_corr_with_global_z": np.nan,
                "within_country_year_corr_with_global_z": np.nan,
                "zero_sd_groups": np.nan,
                "severity": "green",
                "notes": "Level/log controls are intentionally interpreted in original units.",
            },
            {
                "family": "growth_effect",
                "variable": "growth and lagged income terms",
                "standardization_scope": "not standardized",
                "mean": np.nan,
                "sd": np.nan,
                "within_year_corr_with_global_z": np.nan,
                "within_country_year_corr_with_global_z": np.nan,
                "zero_sd_groups": np.nan,
                "severity": "green",
                "notes": "Growth coefficients are interpreted per log-point growth, not per standard deviation.",
            },
            {
                "family": "exercise_02",
                "variable": "bucket dummies / raw Gini controls",
                "standardization_scope": "not standardized",
                "mean": np.nan,
                "sd": np.nan,
                "within_year_corr_with_global_z": np.nan,
                "within_country_year_corr_with_global_z": np.nan,
                "zero_sd_groups": np.nan,
                "severity": "green",
                "notes": "Main predictors are discrete concentration buckets.",
            },
        ]
    )

    audit_specs = [
        ("exercise_11_product", panels["ex11_product"], ["loo_gini_contribution", "loo_partner_hhi_contribution", "import_value_share"]),
        ("exercise_11_hs2", panels["ex11_hs2"], ["hs2_product_loo_gini_sum", "hs2_import_value_share", "hs2_intermediate_import_share"]),
        ("exercise_11_sector", panels["ex11_sector"], ["sector_loo_gini_contribution", "sector_import_value_share"]),
    ]
    for family, df, cols in audit_specs:
        for col in cols:
            if col not in df.columns:
                continue
            values = finite_numeric(df[col])
            global_z = zscore(values)
            year_z = within_zscore(df.assign(_value=values), "_value", ["year"])
            cy_z = within_zscore(df.assign(_value=values), "_value", ["reporter_code", "year"])
            cy_sd = values.groupby([df["reporter_code"], df["year"]], dropna=False).transform(lambda s: s.std(ddof=0))
            zero_sd_groups = int(
                pd.DataFrame({"reporter_code": df["reporter_code"], "year": df["year"], "sd": cy_sd})
                .drop_duplicates(["reporter_code", "year"])["sd"]
                .fillna(0)
                .eq(0)
                .sum()
            )
            cy_corr = float(global_z.corr(cy_z)) if global_z.notna().any() and cy_z.notna().any() else np.nan
            severity = severity_from_conditions(
                red=[],
                yellow=[zero_sd_groups > 0, cy_corr < 0.95 if np.isfinite(cy_corr) else False],
            )
            rows.append(
                {
                    "family": family,
                    "variable": col,
                    "standardization_scope": "global in canonical Exercise 11 output",
                    "mean": float(values.mean()) if values.notna().any() else np.nan,
                    "sd": float(values.std(ddof=0)) if values.notna().any() else np.nan,
                    "within_year_corr_with_global_z": float(global_z.corr(year_z)) if global_z.notna().any() and year_z.notna().any() else np.nan,
                    "within_country_year_corr_with_global_z": cy_corr,
                    "zero_sd_groups": zero_sd_groups,
                    "severity": severity,
                    "notes": "Global scale differs from within-country-year ranking; inspect within-country-year-z alternatives."
                    if severity != "green"
                    else "Global and within-country-year scales are close in this artifact.",
                }
            )
    return pd.DataFrame(rows)


def build_weighting_audit(panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    specs = [
        ("country_size", panels["country_size"]),
        ("growth_effect", panels["growth"]),
        ("exercise_02", panels["exercise_02"]),
        ("exercise_11_product", panels["ex11_product"]),
        ("exercise_11_hs2", panels["ex11_hs2"]),
        ("exercise_11_sector", panels["ex11_sector"]),
    ]
    for family, df in specs:
        if not {"reporter_code", "year"}.issubset(df.columns):
            continue
        cy = df.groupby(["reporter_code", "country", "iso3", "year"], dropna=False).size().reset_index(name="rows")
        year_counts = cy.groupby("year", as_index=False).agg(countries=("reporter_code", "nunique"), rows=("rows", "sum"))
        top_cy = cy.sort_values("rows", ascending=False).head(1)
        total_rows = float(cy["rows"].sum())
        top_share = float(top_cy["rows"].iloc[0] / total_rows) if total_rows else np.nan
        rows.append(
            {
                "family": family,
                "unit_weighted_in_canonical_rows": "row",
                "country_years": int(len(cy)),
                "rows": int(total_rows),
                "min_countries_per_year": int(year_counts["countries"].min()) if not year_counts.empty else 0,
                "median_countries_per_year": float(year_counts["countries"].median()) if not year_counts.empty else np.nan,
                "max_countries_per_year": int(year_counts["countries"].max()) if not year_counts.empty else 0,
                "min_rows_per_country_year": int(cy["rows"].min()) if not cy.empty else 0,
                "median_rows_per_country_year": float(cy["rows"].median()) if not cy.empty else np.nan,
                "max_rows_per_country_year": int(cy["rows"].max()) if not cy.empty else 0,
                "top_country_year": f"{top_cy['country'].iloc[0]} ({top_cy['iso3'].iloc[0]}), {int(top_cy['year'].iloc[0])}"
                if not top_cy.empty
                else "",
                "top_country_year_row_share": top_share,
                "top_10pct_country_year_row_share": float(cy.sort_values("rows", ascending=False).head(max(1, math.ceil(len(cy) * 0.10)))["rows"].sum() / total_rows)
                if total_rows
                else np.nan,
                "severity": severity_from_conditions(
                    red=[],
                    yellow=[int(year_counts["countries"].min()) < 30 if not year_counts.empty else False, top_share > 0.01 if family.startswith("exercise_11") else False],
                ),
            }
        )
    return pd.DataFrame(rows)


def canonical_coef(table: pd.DataFrame, term: str, filters: dict[str, Any], coef_col: str = "coefficient") -> FitSummary | None:
    if table.empty:
        return None
    mask = pd.Series(True, index=table.index)
    for col, value in filters.items():
        if col not in table.columns:
            return None
        mask &= table[col].eq(value)
    mask &= table["term"].eq(term)
    hit = table[mask]
    if hit.empty:
        return None
    row = hit.iloc[0]
    coef_name = coef_col if coef_col in hit.columns else "coef"
    return FitSummary(
        float(row.get(coef_name, np.nan)),
        float(row.get("std_error", np.nan)),
        float(row.get("p_value", np.nan)),
        int(row.get("nobs", 0)),
        int(row.get("clusters", row.get("countries", 0))),
        int(row.get("dropped_rows", 0)) if pd.notna(row.get("dropped_rows", np.nan)) else 0,
        str(row.get("status", "ok")),
    )


def append_fit_row(
    rows: list[dict[str, Any]],
    family: str,
    model_label: str,
    outcome: str,
    term: str,
    variant: str,
    fit: FitSummary | None,
    flow: str = "",
    dimension: str = "",
    metric: str = "",
    exposure: str = "",
    horizon: int | None = None,
) -> None:
    rows.append(
        {
            "family": family,
            "model_label": model_label,
            "flow": flow,
            "dimension": dimension,
            "metric": metric,
            "exposure": exposure,
            "horizon": horizon,
            "outcome": outcome,
            "term": term,
            "audit_variant": variant,
            "coefficient": fit.coefficient if fit else np.nan,
            "std_error": fit.std_error if fit else np.nan,
            "p_value": fit.p_value if fit else np.nan,
            "nobs": fit.nobs if fit else np.nan,
            "clusters": fit.clusters if fit else np.nan,
            "dropped_rows": fit.dropped_rows if fit else np.nan,
            "status": fit.status if fit else "missing",
        }
    )


def build_alternative_estimates(country_sample: str, panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    base_results = sample_results_dir(country_sample)
    rows: list[dict[str, Any]] = []

    country_main = read_csv_if_exists(base_results / "country_size_effect_tables" / "main_models.csv")
    cs_panel = panels["country_size"]
    cs_counts = year_country_counts(cs_panel)
    cs_good_years = set(cs_counts.loc[cs_counts["countries_in_year"] >= 50, "year"])
    for flow in FLOWS:
        flow_panel = cs_panel[cs_panel["flow"].eq(flow)].copy()
        flow_panel = add_equal_year_weight(flow_panel, ["year"])
        for dimension, metric, outcome, _label in OUTCOME_SPECS:
            term = "log_population"
            filters = {"model_label": "main_year_fe", "flow": flow, "dimension": dimension, "metric": metric, "term": term}
            append_fit_row(rows, "country_size", "main_year_fe", outcome, term, "canonical_current", canonical_coef(country_main, term, filters), flow, dimension, metric)
            terms = ["log_population", "log_gdp_per_capita"]
            append_fit_row(
                rows,
                "country_size",
                "main_year_fe",
                outcome,
                term,
                "equal_year_weighted",
                fit_dummy_ols(flow_panel, outcome, terms, ["year"], "reporter_code", term, "equal_year_weight"),
                flow,
                dimension,
                metric,
            )
            restricted = flow_panel[flow_panel["year"].isin(cs_good_years)].copy()
            append_fit_row(
                rows,
                "country_size",
                "main_year_fe",
                outcome,
                term,
                "years_with_at_least_50_countries",
                fit_dummy_ols(restricted, outcome, terms, ["year"], "reporter_code", term),
                flow,
                dimension,
                metric,
            )

    growth_main = read_csv_if_exists(base_results / "growth_effect_tables" / "main_models.csv")
    growth_panel = panels["growth"]
    common_growth_cols = [
        "prior_export_growth",
        "contemporaneous_export_growth",
        "future_export_growth",
        "lag_log_real_exports",
        "lag_log_population",
    ]
    term = "prior_export_growth"
    terms = [term, "lag_log_real_exports", "lag_log_population"]
    for horizon in sorted(pd.to_numeric(growth_panel.get("horizon", pd.Series([1])), errors="coerce").dropna().astype(int).unique()):
        horizon_panel = growth_panel[growth_panel.get("horizon", 1).eq(horizon)].copy() if "horizon" in growth_panel.columns else growth_panel.copy()
        year_col = "base_year" if "base_year" in horizon_panel.columns else "year"
        counts_panel = horizon_panel.copy()
        counts_panel["year"] = counts_panel[year_col]
        growth_counts = year_country_counts(counts_panel)
        growth_good_years = set(growth_counts.loc[growth_counts["countries_in_year"] >= 50, "year"])
        for flow in FLOWS:
            flow_panel = horizon_panel[horizon_panel["flow"].eq(flow)].copy()
            flow_panel = add_equal_year_weight(flow_panel, [year_col])
            common_panel = flow_panel.replace([np.inf, -np.inf], np.nan).dropna(subset=common_growth_cols).copy()
            for dimension, metric, outcome, _label in OUTCOME_SPECS:
                filters = {
                    "model_label": "main_lagged_export_growth",
                    "horizon": horizon,
                    "flow": flow,
                    "dimension": dimension,
                    "metric": metric,
                    "term": term,
                }
                append_fit_row(rows, "growth_effect", "main_lagged_export_growth", outcome, term, "canonical_current", canonical_coef(growth_main, term, filters), flow, dimension, metric, horizon=horizon)
                append_fit_row(
                    rows,
                    "growth_effect",
                    "main_lagged_export_growth",
                    outcome,
                    term,
                    "equal_year_weighted",
                    fit_dummy_ols(flow_panel, outcome, terms, ["reporter_code", year_col], "reporter_code", term, "equal_year_weight"),
                    flow,
                    dimension,
                    metric,
                    horizon=horizon,
                )
                append_fit_row(
                    rows,
                    "growth_effect",
                    "main_lagged_export_growth",
                    outcome,
                    term,
                    "years_with_at_least_50_countries",
                    fit_dummy_ols(flow_panel[flow_panel[year_col].isin(growth_good_years)].copy(), outcome, terms, ["reporter_code", year_col], "reporter_code", term),
                    flow,
                    dimension,
                    metric,
                    horizon=horizon,
                )
                append_fit_row(
                    rows,
                    "growth_effect",
                    "main_lagged_export_growth",
                    outcome,
                    term,
                    "common_growth_timing_complete_sample",
                    fit_dummy_ols(common_panel, outcome, terms, ["reporter_code", year_col], "reporter_code", term),
                    flow,
                    dimension,
                    metric,
                    horizon=horizon,
                )

    ex02_models = read_csv_if_exists(base_results / "exercise_02_tables" / "bucket_growth_models.csv")
    ex02_panel = panels["exercise_02"].copy()
    ex02_common_keys = (
        ex02_panel.groupby(["reporter_code", "year"])["horizon"].nunique().reset_index(name="horizons")
    )
    ex02_common = ex02_panel.merge(ex02_common_keys[ex02_common_keys["horizons"] == 3][["reporter_code", "year"]], on=["reporter_code", "year"], how="inner")
    ex02_specs = {
        "bucket_country_year_fe_core": ("E2-2", "annualized_export_growth_log", E2_BUCKET_TERMS, ["log_initial_exports", "oil_export_share"]),
        "bucket_country_year_fe_controls": (
            "E2-3",
            "annualized_export_growth_log",
            E2_BUCKET_TERMS,
            ["log_initial_exports", "oil_export_share", "log_gdp_current_usd", "log_population", "log_gni_per_capita_current_usd"],
        ),
    }
    for model_label, (_model_id, outcome, bucket_terms, controls) in ex02_specs.items():
        for horizon in sorted(ex02_panel["horizon"].dropna().astype(int).unique()):
            base = ex02_panel[ex02_panel["horizon"].eq(horizon)].copy()
            base = add_equal_year_weight(base, ["year"])
            common = ex02_common[ex02_common["horizon"].eq(horizon)].copy()
            for term in bucket_terms:
                filters = {"model_label": model_label, "horizon": horizon, "variable": term}
                append_fit_row(rows, "exercise_02", model_label, outcome, term, "canonical_current", canonical_coef(ex02_models.rename(columns={"variable": "term"}), term, {k: v for k, v in filters.items() if k != "variable"}), horizon=horizon)
                predictor_terms = list(bucket_terms) + controls
                append_fit_row(
                    rows,
                    "exercise_02",
                    model_label,
                    outcome,
                    term,
                    "equal_year_weighted",
                    fit_dummy_ols(add_e2_predictors(base), outcome, predictor_terms, ["reporter_code", "year"], "reporter_code", term, "equal_year_weight"),
                    horizon=horizon,
                )
                append_fit_row(
                    rows,
                    "exercise_02",
                    model_label,
                    outcome,
                    term,
                    "common_horizon_sample",
                    fit_dummy_ols(add_e2_predictors(common), outcome, predictor_terms, ["reporter_code", "year"], "reporter_code", term),
                    horizon=horizon,
                )

    rows.extend(exercise_11_alternatives(country_sample, panels))
    return pd.DataFrame(rows)


def add_e2_predictors(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "concentration_bucket" in out.columns:
        for term in E2_BUCKET_TERMS:
            bucket = term.replace("bucket_", "")
            out[term] = out["concentration_bucket"].eq(bucket).astype(float)
    if "concentration_bucket_top_share" in out.columns:
        for term in E2_TOP_SHARE_TERMS:
            bucket = term.replace("top_share_bucket_", "")
            out[term] = out["concentration_bucket_top_share"].eq(bucket).astype(float)
    return out


def exercise_11_alternatives(country_sample: str, panels: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    base_results = sample_results_dir(country_sample)

    product = panels["ex11_product"].copy()
    product["country_year"] = product["reporter_code"].astype(str) + "_" + product["year"].astype(str)
    product["loo_gini_contribution_z"] = zscore(product["loo_gini_contribution"])
    product["loo_partner_hhi_contribution_z"] = zscore(product["loo_partner_hhi_contribution"])
    product["import_value_share_z"] = zscore(product["import_value_share"])
    product["loo_gini_contribution_cy_z"] = within_zscore(product, "loo_gini_contribution", ["reporter_code", "year"])
    product["loo_partner_hhi_contribution_cy_z"] = within_zscore(product, "loo_partner_hhi_contribution", ["reporter_code", "year"])
    product["import_value_share_cy_z"] = within_zscore(product, "import_value_share", ["reporter_code", "year"])
    product["loo_gini_x_intermediate_z"] = product["loo_gini_contribution_z"] * product["is_intermediate"]
    product["loo_gini_x_intermediate_cy_z"] = product["loo_gini_contribution_cy_z"] * product["is_intermediate"]
    product["bin_energy"] = product["import_bin"].eq("energy").astype(int)
    product["bin_capital_goods"] = product["import_bin"].eq("capital_goods").astype(int)
    product["bin_final_consumption"] = product["import_bin"].eq("final_consumption").astype(int)
    product["bin_unmapped"] = product["import_bin"].eq("unmapped_or_ambiguous").astype(int)
    product = add_equal_cy_weight(product)
    product_reg = read_csv_if_exists(base_results / "exercise_11_product_export_linkage_tables" / "product_regressions.csv")
    bin_terms = ["bin_energy", "bin_capital_goods", "bin_final_consumption", "bin_unmapped"]
    product_models = [
        ("product_export_value_gini", "asinh_export_value", "loo_gini_contribution_z", "loo_gini_contribution_cy_z", ["import_value_share_z", *bin_terms], ["import_value_share_cy_z", *bin_terms]),
        ("product_export_any_gini", "export_any", "loo_gini_contribution_z", "loo_gini_contribution_cy_z", ["import_value_share_z", *bin_terms], ["import_value_share_cy_z", *bin_terms]),
        ("product_export_value_partner_hhi", "asinh_export_value", "loo_partner_hhi_contribution_z", "loo_partner_hhi_contribution_cy_z", ["import_value_share_z", *bin_terms], ["import_value_share_cy_z", *bin_terms]),
        ("product_export_value_intermediate_interaction", "asinh_export_value", "loo_gini_x_intermediate_z", "loo_gini_x_intermediate_cy_z", ["loo_gini_contribution_z", "is_intermediate", "import_value_share_z"], ["loo_gini_contribution_cy_z", "is_intermediate", "import_value_share_cy_z"]),
    ]
    for model_label, outcome, current_term, cy_term, current_controls, cy_controls in product_models:
        append_fit_row(rows, "exercise_11_product", model_label, outcome, current_term, "canonical_current", canonical_coef(product_reg, current_term, {"model_label": model_label}, coef_col="coef"))
        append_fit_row(
            rows,
            "exercise_11_product",
            model_label,
            outcome,
            current_term,
            "global_z_equal_country_year_weighted",
            fit_country_year_fe_ols(product, outcome, [current_term, *current_controls], "country_year", "reporter_code", current_term, "equal_country_year_weight"),
        )
        append_fit_row(
            rows,
            "exercise_11_product",
            model_label,
            outcome,
            cy_term,
            "within_country_year_z_unweighted",
            fit_country_year_fe_ols(product, outcome, [cy_term, *cy_controls], "country_year", "reporter_code", cy_term),
        )
        append_fit_row(
            rows,
            "exercise_11_product",
            model_label,
            outcome,
            cy_term,
            "within_country_year_z_equal_country_year_weighted",
            fit_country_year_fe_ols(product, outcome, [cy_term, *cy_controls], "country_year", "reporter_code", cy_term, "equal_country_year_weight"),
        )

    hs2 = panels["ex11_hs2"].copy()
    hs2["country_year"] = hs2["reporter_code"].astype(str) + "_" + hs2["year"].astype(str)
    hs2["hs2_product_loo_gini_sum_z"] = zscore(hs2["hs2_product_loo_gini_sum"])
    hs2["hs2_import_value_share_z"] = zscore(hs2["hs2_import_value_share"])
    hs2["hs2_product_loo_gini_sum_cy_z"] = within_zscore(hs2, "hs2_product_loo_gini_sum", ["reporter_code", "year"])
    hs2["hs2_import_value_share_cy_z"] = within_zscore(hs2, "hs2_import_value_share", ["reporter_code", "year"])
    hs2 = add_equal_cy_weight(hs2)
    hs2_reg = read_csv_if_exists(base_results / "exercise_11_product_export_linkage_tables" / "hs2_regressions.csv")
    hs2_dummies = pd.get_dummies(hs2["hs2"], prefix="hs2", drop_first=True, dtype=int)
    hs2 = pd.concat([hs2, hs2_dummies], axis=1)
    hs2_terms = hs2_dummies.columns.tolist()
    for model_label, outcome in [
        ("hs2_export_value_gini", "asinh_hs2_export_value"),
        ("hs2_export_any_gini", "hs2_export_any"),
        ("hs2_export_share_gini", "hs2_export_share"),
    ]:
        term = "hs2_product_loo_gini_sum_z"
        cy_term = "hs2_product_loo_gini_sum_cy_z"
        append_fit_row(rows, "exercise_11_hs2", model_label, outcome, term, "canonical_current", canonical_coef(hs2_reg, term, {"model_label": model_label}, coef_col="coef"))
        append_fit_row(
            rows,
            "exercise_11_hs2",
            model_label,
            outcome,
            term,
            "global_z_equal_country_year_weighted",
            fit_country_year_fe_ols(hs2, outcome, [term, "hs2_import_value_share_z", *hs2_terms], "country_year", "reporter_code", term, "equal_country_year_weight"),
        )
        append_fit_row(
            rows,
            "exercise_11_hs2",
            model_label,
            outcome,
            cy_term,
            "within_country_year_z_unweighted",
            fit_country_year_fe_ols(hs2, outcome, [cy_term, "hs2_import_value_share_cy_z", *hs2_terms], "country_year", "reporter_code", cy_term),
        )

    sector = panels["ex11_sector"].copy()
    sector["country_year"] = sector["reporter_code"].astype(str) + "_" + sector["year"].astype(str)
    sector["sector_loo_gini_contribution_z"] = zscore(sector["sector_loo_gini_contribution"])
    sector["sector_import_value_share_z"] = zscore(sector["sector_import_value_share"])
    sector["sector_loo_gini_contribution_cy_z"] = within_zscore(sector, "sector_loo_gini_contribution", ["reporter_code", "year"])
    sector["sector_import_value_share_cy_z"] = within_zscore(sector, "sector_import_value_share", ["reporter_code", "year"])
    sector = add_equal_cy_weight(sector)
    sector_reg = read_csv_if_exists(base_results / "exercise_11_product_export_linkage_tables" / "sector_regressions.csv")
    sector_dummies = pd.get_dummies(sector["io_sector_code"], prefix="sector", drop_first=True, dtype=int)
    sector = pd.concat([sector, sector_dummies], axis=1)
    sector_terms = sector_dummies.columns.tolist()
    term = "sector_loo_gini_contribution_z"
    cy_term = "sector_loo_gini_contribution_cy_z"
    model_label = "sector_export_share_gini"
    outcome = "sector_export_share"
    append_fit_row(rows, "exercise_11_sector", model_label, outcome, term, "canonical_current", canonical_coef(sector_reg, term, {"model_label": model_label}, coef_col="coef"))
    append_fit_row(
        rows,
        "exercise_11_sector",
        model_label,
        outcome,
        term,
        "global_z_equal_country_year_weighted",
        fit_country_year_fe_ols(sector, outcome, [term, "sector_import_value_share_z", *sector_terms], "country_year", "reporter_code", term, "equal_country_year_weight"),
    )
    append_fit_row(
        rows,
        "exercise_11_sector",
        model_label,
        outcome,
        cy_term,
        "within_country_year_z_unweighted",
        fit_country_year_fe_ols(sector, outcome, [cy_term, "sector_import_value_share_cy_z", *sector_terms], "country_year", "reporter_code", cy_term),
    )
    return rows


def build_threat_register(
    artifact_inventory: pd.DataFrame,
    attrition: pd.DataFrame,
    standardization: pd.DataFrame,
    weighting: pd.DataFrame,
    alternatives: pd.DataFrame,
) -> pd.DataFrame:
    threats: list[dict[str, Any]] = []

    high_attrition = attrition[attrition["severity"].eq("red")]
    threats.append(
        {
            "rank": 1,
            "threat": "Complete-case attrition can change the estimand.",
            "category": "data integrity",
            "diagnostic_or_robustness_check": "Compare candidate rows, analytic rows, dropped rows, clusters, and common-sample alternatives by model.",
            "expected_failure_signal": "Drop share above 25%, fewer than 30 clusters, or coefficient changes sign/materially under common-sample checks.",
            "interpretation_if_fails": "The reported coefficient is partly a selected-sample estimate, not the intended rd2 country-year or product panel estimate.",
            "main_text_or_appendix": "main text",
            "severity": "red" if not high_attrition.empty else "yellow",
            "evidence": f"{len(high_attrition)} red attrition rows; largest drop share {attrition['drop_share'].max():.3f}.",
        }
    )

    ex11_weight = weighting[weighting["family"].eq("exercise_11_product")]
    top_share = float(ex11_weight["top_10pct_country_year_row_share"].iloc[0]) if not ex11_weight.empty else np.nan
    threats.append(
        {
            "rank": 2,
            "threat": "Exercise 11 product-row weighting may overweight country-years with more active HS6 product rows.",
            "category": "specification / weights",
            "diagnostic_or_robustness_check": "Compare canonical product-row estimates with equal-country-year weighted estimates.",
            "expected_failure_signal": "Large sign or magnitude shift under equal-country-year weights.",
            "interpretation_if_fails": "The estimate describes the average product row more than the average reporter-year product basket.",
            "main_text_or_appendix": "main text",
            "severity": "yellow" if pd.notna(top_share) and top_share > 0.20 else "green",
            "evidence": f"Top 10 percent of Exercise 11 country-years account for {top_share:.1%} of product rows." if pd.notna(top_share) else "",
        }
    )

    std_yellow = standardization[standardization["severity"].isin(["yellow", "red"])]
    threats.append(
        {
            "rank": 3,
            "threat": "Global standardization may mix within-country-year variation with cross-year/product-composition variation.",
            "category": "specification / transformations",
            "diagnostic_or_robustness_check": "Compare global z-score Exercise 11 regressions with within-country-year z-score regressions.",
            "expected_failure_signal": "Low correlation between global and within-country-year z-scores, or coefficient instability under within-country-year z-scores.",
            "interpretation_if_fails": "The standardized coefficient may not represent within-reporter-year product ranking cleanly.",
            "main_text_or_appendix": "main text",
            "severity": "yellow" if not std_yellow.empty else "green",
            "evidence": f"{len(std_yellow)} standardization rows flagged yellow/red.",
        }
    )

    low_years = weighting[pd.to_numeric(weighting["min_countries_per_year"], errors="coerce") < 30]
    threats.append(
        {
            "rank": 4,
            "threat": "Sparse early years can overweight limited country coverage in year fixed-effect panels.",
            "category": "data quality / panel balance",
            "diagnostic_or_robustness_check": "Restrict country-size and growth models to years with at least 50 reporters and compare equal-year weighted estimates.",
            "expected_failure_signal": "Large changes after dropping sparse years or equalizing years.",
            "interpretation_if_fails": "Early sparse years are not interchangeable with later near-complete rd2 years.",
            "main_text_or_appendix": "main text",
            "severity": "yellow" if not low_years.empty else "green",
            "evidence": f"{len(low_years)} families have at least one year with fewer than 30 countries.",
        }
    )

    bad_artifacts = artifact_inventory[artifact_inventory["severity"].eq("red")]
    threats.append(
        {
            "rank": 5,
            "threat": "Wrong-sample or product-code leakage would invalidate the report.",
            "category": "data lineage",
            "diagnostic_or_robustness_check": "Verify rd2 manifests, artifact paths, duplicate keys, and product-dependent exclusion of HS6 999999 (Commodities not specified).",
            "expected_failure_signal": "Missing rd2 manifest, non-rd2 sample, duplicate analytic keys, or HS6 999999 (Commodities not specified) in product-dependent panels.",
            "interpretation_if_fails": "Stop and rebuild from rd2 artifacts before interpreting coefficients.",
            "main_text_or_appendix": "appendix",
            "severity": "red" if not bad_artifacts.empty else "green",
            "evidence": f"{len(bad_artifacts)} red artifact inventory rows.",
        }
    )

    max_delta = coefficient_delta_summary(alternatives)
    threats.append(
        {
            "rank": 6,
            "threat": "Audit-only alternatives may materially change selected coefficients.",
            "category": "sensitivity",
            "diagnostic_or_robustness_check": "Compare canonical coefficients with equal-year, common-sample, within-country-year-z, and equal-country-year-weight alternatives.",
            "expected_failure_signal": "Absolute coefficient delta is large relative to the canonical coefficient or sign reverses.",
            "interpretation_if_fails": "Report the canonical result as descriptive and sensitive to sample/weighting choices.",
            "main_text_or_appendix": "main text",
            "severity": "yellow" if max_delta["max_abs_relative_delta"] > 0.5 or max_delta["sign_flips"] > 0 else "green",
            "evidence": f"Max relative delta {max_delta['max_abs_relative_delta']:.2f}; sign flips {max_delta['sign_flips']}.",
        }
    )
    return pd.DataFrame(threats)


def coefficient_delta_summary(alternatives: pd.DataFrame) -> dict[str, float | int]:
    if alternatives.empty:
        return {"max_abs_relative_delta": np.nan, "sign_flips": 0}
    keys = ["family", "model_label", "flow", "dimension", "metric", "exposure", "horizon", "outcome"]
    base = alternatives[alternatives["audit_variant"].eq("canonical_current")]
    comp = alternatives[~alternatives["audit_variant"].eq("canonical_current")]
    merged = comp.merge(
        base[keys + ["coefficient"]].rename(columns={"coefficient": "canonical_coefficient"}),
        on=keys,
        how="left",
    )
    denom = merged["canonical_coefficient"].abs().replace(0, np.nan)
    rel_delta = ((merged["coefficient"] - merged["canonical_coefficient"]).abs() / denom).replace([np.inf, -np.inf], np.nan)
    sign_flips = int(
        (
            np.sign(merged["coefficient"])
            .replace(0, np.nan)
            .ne(np.sign(merged["canonical_coefficient"]).replace(0, np.nan))
            & merged["coefficient"].notna()
            & merged["canonical_coefficient"].notna()
        ).sum()
    )
    return {"max_abs_relative_delta": float(rel_delta.max()) if rel_delta.notna().any() else 0.0, "sign_flips": sign_flips}


def format_coef_table(alternatives: pd.DataFrame) -> str:
    if alternatives.empty:
        return "No alternative estimate comparisons were generated."
    pieces = [
        alternatives[
            alternatives["family"].eq("country_size")
            & alternatives["outcome"].eq("product_gini")
            & alternatives["term"].eq("log_population")
            & alternatives["audit_variant"].isin(["canonical_current", "equal_year_weighted", "years_with_at_least_50_countries"])
        ],
        alternatives[
            alternatives["family"].eq("growth_effect")
            & alternatives["outcome"].eq("product_gini")
            & alternatives["term"].eq("prior_export_growth")
            & alternatives["audit_variant"].isin(["canonical_current", "equal_year_weighted", "common_growth_timing_complete_sample"])
        ],
        alternatives[
            alternatives["family"].eq("exercise_02")
            & alternatives["model_label"].isin(["bucket_country_year_fe_core", "bucket_country_year_fe_controls"])
            & alternatives["term"].eq("bucket_high_product_low_partner")
            & alternatives["audit_variant"].isin(["canonical_current", "equal_year_weighted", "common_horizon_sample"])
        ],
        alternatives[
            alternatives["family"].str.startswith("exercise_11", na=False)
            & alternatives["audit_variant"].isin(["canonical_current", "global_z_equal_country_year_weighted", "within_country_year_z_unweighted"])
        ],
    ]
    focus = pd.concat(pieces, ignore_index=True)
    display = focus[
        [
            "family",
            "model_label",
            "flow",
            "exposure",
            "horizon",
            "outcome",
            "term",
            "audit_variant",
            "coefficient",
            "std_error",
            "nobs",
            "clusters",
        ]
    ].copy()
    for col in ["coefficient", "std_error"]:
        display[col] = pd.to_numeric(display[col], errors="coerce").round(4)
    for col in ["flow", "exposure", "horizon"]:
        display[col] = display[col].fillna("")
    display["horizon"] = display["horizon"].apply(lambda value: "" if value == "" else str(int(float(value))))
    return display.to_markdown(index=False)


def format_family_judgments(
    artifact_inventory: pd.DataFrame,
    attrition: pd.DataFrame,
    standardization: pd.DataFrame,
    weighting: pd.DataFrame,
) -> str:
    def max_drop(families: list[str]) -> float:
        work = attrition[attrition["family"].isin(families)]
        values = pd.to_numeric(work["drop_share"], errors="coerce")
        return float(values.max()) if values.notna().any() else 0.0

    def min_clusters(families: list[str]) -> int | None:
        work = attrition[attrition["family"].isin(families)]
        values = pd.to_numeric(work["clusters"], errors="coerce")
        return int(values.min()) if values.notna().any() else None

    def has_red_artifact(families: list[str]) -> bool:
        return bool(
            artifact_inventory[
                artifact_inventory["family"].isin(families) & artifact_inventory["severity"].eq("red")
            ].shape[0]
        )

    def sparse_years(family: str) -> bool:
        row = weighting[weighting["family"].eq(family)]
        if row.empty:
            return False
        min_countries = pd.to_numeric(row["min_countries_per_year"], errors="coerce")
        return bool(min_countries.notna().any() and min_countries.min() < 30)

    rows = [
        {
            "family": "Country-size",
            "input_judgment": "usable with sparse-year caveat"
            if sparse_years("country_size") and not has_red_artifact(["country_size"])
            else "usable",
            "evidence": f"rd2 processed panel and tables present; max complete-case attrition {max_drop(['country_size']):.1%}; min clusters {min_clusters(['country_size'])}.",
            "required_action": "Main results should show sparse-year or equal-year robustness when discussed.",
        },
        {
            "family": "Growth-effect",
            "input_judgment": "usable with sparse-year/common-sample caveat"
            if sparse_years("growth_effect") and not has_red_artifact(["growth_effect"])
            else "usable",
            "evidence": f"rd2 processed panel and tables present; max complete-case attrition {max_drop(['growth_effect']):.1%}; min clusters {min_clusters(['growth_effect'])}.",
            "required_action": "Compare equal-year, sparse-year, and common growth-timing samples before making strong claims.",
        },
        {
            "family": "Exercise 2 export-growth buckets",
            "input_judgment": "usable after macro-control refresh"
            if max_drop(["exercise_02"]) <= 0.10 and (min_clusters(["exercise_02"]) or 0) >= 50
            else "core model usable; full-control model not trust-ready",
            "evidence": f"rd2 bucket panel is current; full controls have max attrition {max_drop(['exercise_02']):.1%} and min clusters {min_clusters(['exercise_02'])}.",
            "required_action": "Keep the macro-control refresh manifest with the outputs and report common-horizon robustness when discussing horizons.",
        },
        {
            "family": "Exercise 11 product/export linkage",
            "input_judgment": "right rd2 product input; standardization-sensitive",
            "evidence": "Product-dependent panel excludes HS6 999999 (Commodities not specified); global-to-within-country-year z-score correlations are yellow for product rows.",
            "required_action": "Report global-z estimates with within-country-year-z and equal-country-year-weight alternatives.",
        },
        {
            "family": "Exercise 13",
            "input_judgment": "blocked",
            "evidence": "Only root-level legacy outputs are present; no current rd2 Exercise 13 artifact is generated under results/samples/rd2_countries.",
            "required_action": "Rebuild Exercise 13 for rd2 before auditing or citing it as current.",
        },
    ]
    std_bad = standardization[standardization["family"].eq("exercise_11_product") & standardization["severity"].isin(["yellow", "red"])]
    if std_bad.empty:
        rows[3]["input_judgment"] = "right rd2 product input"
        rows[3]["evidence"] = "Product-dependent panel excludes HS6 999999 (Commodities not specified); standardization diagnostics are green."
    return pd.DataFrame(rows).to_markdown(index=False)


def write_report(
    path: Path,
    country_sample: str,
    artifact_inventory: pd.DataFrame,
    attrition: pd.DataFrame,
    standardization: pd.DataFrame,
    weighting: pd.DataFrame,
    alternatives: pd.DataFrame,
    threat_register: pd.DataFrame,
) -> None:
    red_threats = int(threat_register["severity"].eq("red").sum())
    yellow_threats = int(threat_register["severity"].eq("yellow").sum())
    attrition_max = float(pd.to_numeric(attrition["drop_share"], errors="coerce").max())
    ex13_note = (
        "Exercise 13 is not audited as a current rd2 regression output because the available manifest is root-level "
        "and not generated under `results/samples/rd2_countries/`. Rebuild Exercise 13 for rd2 before treating it as current."
    )
    std_display = standardization[
        [
            "family",
            "variable",
            "standardization_scope",
            "within_country_year_corr_with_global_z",
            "zero_sd_groups",
            "severity",
            "notes",
        ]
    ].copy()
    std_display["within_country_year_corr_with_global_z"] = pd.to_numeric(
        std_display["within_country_year_corr_with_global_z"], errors="coerce"
    ).round(6)
    std_display["zero_sd_groups"] = pd.to_numeric(std_display["zero_sd_groups"], errors="coerce")
    std_display = std_display.where(pd.notna(std_display), "")
    lines = [
        "# RD2 Regression Input Audit",
        "",
        f"Generated: `{now_utc()}`",
        f"Country sample: `{country_sample}`",
        "",
        "## Bottom Line",
        "",
        f"- Audit verdict: **{'Do not trust yet' if red_threats else 'Mostly trustworthy for current descriptive purpose'}**.",
        f"- Ranked threats: {red_threats} red, {yellow_threats} yellow.",
        f"- Largest model-level drop share observed: {attrition_max:.1%}.",
        "- Audit-only estimates in this report did not overwrite canonical regression outputs; any upstream canonical refresh is recorded in source manifests.",
        f"- {ex13_note}",
        "",
        "## Preferred Specifications And Estimands",
        "",
        "- Country-size: descriptive association between log population and concentration outcomes within year, controlling for log GDP per capita.",
        "- Growth-effect: descriptive association between prior real export growth and concentration outcomes with reporter and year fixed effects.",
        "- Exercise 2: descriptive export-growth differences by initial product/partner concentration bucket over 1-, 5-, and 10-year horizons.",
        "- Exercise 11: descriptive within-reporter-year product/HS2/sector linkage between import concentration contribution and export outcomes.",
        "",
        "## Family Input Judgments",
        "",
        format_family_judgments(artifact_inventory, attrition, standardization, weighting),
        "",
        "## Ranked Threat List",
        "",
        threat_register.sort_values("rank")[
            [
                "rank",
                "severity",
                "threat",
                "diagnostic_or_robustness_check",
                "expected_failure_signal",
                "interpretation_if_fails",
                "main_text_or_appendix",
            ]
        ].to_markdown(index=False),
        "",
        "## Key Alternative Estimate Checks",
        "",
        format_coef_table(alternatives),
        "",
        "## Sample And Weighting Highlights",
        "",
        weighting[
            [
                "family",
                "country_years",
                "rows",
                "min_countries_per_year",
                "median_rows_per_country_year",
                "max_rows_per_country_year",
                "top_country_year",
                "top_10pct_country_year_row_share",
                "severity",
            ]
        ].to_markdown(index=False),
        "",
        "## Standardization Highlights",
        "",
        std_display.to_markdown(index=False),
        "",
        "## Appendix Tables",
        "",
        "- `artifact_inventory.csv`: artifact lineage, rd2 manifest checks, duplicate keys, and HS6 `999999` (`Commodities not specified`) leakage checks.",
        "- `sample_attrition.csv`: candidate rows, analytic rows, dropped rows, clusters, and severity by model.",
        "- `missingness_by_year_country.csv`: country-year missingness for model inputs.",
        "- `standardization_audit.csv`: global versus within-year and within-country-year scaling diagnostics.",
        "- `weighting_audit.csv`: row weight concentration by year and country-year.",
        "- `alternative_estimate_comparison.csv`: canonical versus audit-only alternative estimates.",
        "- `threat_register.csv`: structured diagnostics skill threat register.",
        "- Exercise 2 macro-control refresh provenance: `run_manifest_exercise_02_bucket_growth.json` when present.",
        "",
        "## Interpretation Rules",
        "",
        "- Red means stop before using that regression family as evidence.",
        "- Yellow means usable only with explicit caveat or a robustness table.",
        "- Green means the audit found no input/sample/weighting issue at this layer; it is not a causal-identification endorsement.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_outputs(country_sample: str, outputs: dict[str, pd.DataFrame]) -> dict[str, Path]:
    base_results = sample_results_dir(country_sample)
    table_dir = base_results / "regression_input_audit_tables"
    ensure_dirs(table_dir)
    paths: dict[str, Path] = {}
    for name, frame in outputs.items():
        path = table_dir / f"{name}.csv"
        frame.to_csv(path, index=False)
        paths[name] = path
    return paths


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit current rd2 regression input panels and outputs.")
    parser.add_argument("--country-sample", default="rd2_countries", choices=["rd2_countries"])
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    base_results = sample_results_dir(args.country_sample)
    blockers = validate_rd2_manifests(base_results)
    required_paths = [
        sample_processed_path(args.country_sample, "country_size_effect_panel.parquet"),
        sample_processed_path(args.country_sample, "growth_effect_panel.parquet"),
        sample_processed_path(args.country_sample, "exercise_02_bucket_growth_panel.parquet"),
        sample_processed_path(args.country_sample, "exercise_11_product_export_linkage_panel.parquet"),
        sample_processed_path(args.country_sample, "exercise_11_hs2_export_linkage_panel.parquet"),
        sample_processed_path(args.country_sample, "exercise_11_sector_export_linkage_panel.parquet"),
    ]
    blockers.extend([f"Missing required rd2 artifact: {rel(path)}" for path in required_paths if not path.exists()])
    if blockers:
        raise SystemExit("RD2 regression input audit blocked:\n- " + "\n- ".join(blockers))

    panels = load_panels(args.country_sample)
    artifact_inventory = build_artifact_inventory(args.country_sample, panels)
    attrition = build_sample_attrition(args.country_sample, panels)
    missingness = build_missingness(args.country_sample, panels)
    standardization = build_standardization_audit(panels)
    weighting = build_weighting_audit(panels)
    alternatives = build_alternative_estimates(args.country_sample, panels)
    threat_register = build_threat_register(artifact_inventory, attrition, standardization, weighting, alternatives)

    write_outputs(
        args.country_sample,
        {
            "artifact_inventory": artifact_inventory,
            "sample_attrition": attrition,
            "missingness_by_year_country": missingness,
            "standardization_audit": standardization,
            "weighting_audit": weighting,
            "alternative_estimate_comparison": alternatives,
            "threat_register": threat_register,
        },
    )
    report_path = base_results / "regression_input_audit.md"
    write_report(report_path, args.country_sample, artifact_inventory, attrition, standardization, weighting, alternatives, threat_register)
    print(json.dumps({"report": rel(report_path), "tables": rel(report_path.parent / "regression_input_audit_tables")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
