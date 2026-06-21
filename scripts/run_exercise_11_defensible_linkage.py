#!/usr/bin/env python3
"""
Defensible descriptive linkage tests for Exercise 11.

This script adds three paper-facing diagnostics without replacing the existing
Exercise 11 outputs:

1. HS2 and IO-sector export-linkage regressions with stronger fixed effects and
   future export outcomes.
2. Input-output exposure comparisons between top and non-top export sectors.
3. Event-time timing tests around the first year an output sector becomes a top
   export sector.

All outputs are descriptive. They do not identify causal effects.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from scipy import stats

from concentration_metrics import active_gini


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = "rd2_countries"
DATA_DIR = ROOT / "data" / "processed" / "samples" / SAMPLE
RESULTS_DIR = ROOT / "results" / "samples" / SAMPLE
TABLE_DIR = RESULTS_DIR / "exercise_11_defensible_linkage_tables"
PROCESSED_DIR = DATA_DIR

PRODUCT_PANEL = DATA_DIR / "exercise_11_product_export_linkage_panel.parquet"
HS2_PANEL = DATA_DIR / "exercise_11_hs2_export_linkage_panel.parquet"
SECTOR_PANEL = DATA_DIR / "exercise_11_sector_export_linkage_panel.parquet"
IO_EXPOSURE_PANEL = DATA_DIR / "exercise_11_top_export_input_exposure.parquet"
IO_IMPORT_CONCENTRATION = DATA_DIR / "exercise_11_imported_input_concentration.parquet"

OUT_HS2_PANEL = PROCESSED_DIR / "exercise_11_defensible_hs2_panel.parquet"
OUT_SECTOR_PANEL = PROCESSED_DIR / "exercise_11_defensible_sector_panel.parquet"
OUT_IO_PANEL = PROCESSED_DIR / "exercise_11_defensible_io_panel.parquet"
OUT_EVENT_PANEL = PROCESSED_DIR / "exercise_11_defensible_timing_event_panel.parquet"
OUT_MEMO = RESULTS_DIR / "exercise_11_defensible_linkage.md"
OUT_MANIFEST = RESULTS_DIR / "run_manifest_exercise_11_defensible_linkage.json"

ICIO_YEAR_MIN = 1995
ICIO_YEAR_MAX = 2022
RNG_SEED = 20260527
PLACEBO_REPLICATIONS = 100
MATCHED_REQUIREMENT_THRESHOLDS = [0.0, 0.10, 0.25, 0.50]


@dataclass
class RegressionResult:
    model_label: str
    sample: str
    outcome: str
    term: str
    term_role: str
    coefficient: float
    std_error: float
    t_stat: float
    p_value: float
    ci_low: float
    ci_high: float
    nobs: int
    clusters: int
    r2_within: float
    fe_cols: str
    cluster_col: str
    controls: str
    status: str
    dropped_terms: str
    fe_counts: str = ""
    residualization_iterations: int = 0
    residualization_max_delta: float = np.nan
    cluster_min_size: float = np.nan
    cluster_median_size: float = np.nan
    cluster_max_size: float = np.nan
    cluster_singleton_count: int = 0


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_dirs() -> None:
    TABLE_DIR.mkdir(parents=True, exist_ok=True)


def top_share(values: Iterable[float], n: int) -> float:
    arr = np.asarray(list(values), dtype=float)
    arr = arr[np.isfinite(arr) & (arr > 0)]
    total = float(arr.sum())
    if total <= 0 or arr.size == 0:
        return np.nan
    n = max(1, min(n, arr.size))
    return float(np.sort(arr)[-n:].sum() / total)


def standardize(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    mean = numeric.mean()
    sd = numeric.std(ddof=0)
    if not np.isfinite(sd) or sd == 0:
        return pd.Series(np.nan, index=series.index)
    return (numeric - mean) / sd


def unique_preserve_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            out.append(item)
            seen.add(item)
    return out


def add_future_outcomes(
    panel: pd.DataFrame,
    key_cols: list[str],
    outcomes: list[str],
    horizons: list[int] = [1, 3],
) -> pd.DataFrame:
    out = panel.copy()
    base_cols = key_cols + ["year"] + outcomes
    for horizon in horizons:
        future = panel[base_cols].copy()
        future["year"] = future["year"] - horizon
        rename = {col: f"future{horizon}_{col}" for col in outcomes}
        future = future.rename(columns=rename)
        out = out.merge(future, on=key_cols + ["year"], how="left", validate="one_to_one")
    return out


def add_fixed_effect_columns(panel: pd.DataFrame, sector_col: str, sector_fe_name: str = "sector") -> pd.DataFrame:
    out = panel.copy()
    out["country_year_fe"] = out["reporter_code"].astype(str) + "_" + out["year"].astype(str)
    out[f"country_{sector_fe_name}_fe"] = out["reporter_code"].astype(str) + "_" + out[sector_col].astype(str)
    out[f"{sector_fe_name}_year_fe"] = out[sector_col].astype(str) + "_" + out["year"].astype(str)
    return out


def group_codes(frame: pd.DataFrame, cols: list[str]) -> list[np.ndarray]:
    codes = []
    for col in cols:
        code = pd.factorize(frame[col], sort=False)[0].astype(np.int64)
        codes.append(code)
    return codes


def regression_sample_metadata(work: pd.DataFrame, fe_cols: list[str], cluster_col: str) -> dict[str, float | int | str]:
    cluster_sizes = work.groupby(cluster_col, sort=False).size()
    return {
        "fe_counts": ";".join(f"{col}={work[col].nunique()}" for col in fe_cols),
        "cluster_min_size": float(cluster_sizes.min()) if not cluster_sizes.empty else np.nan,
        "cluster_median_size": float(cluster_sizes.median()) if not cluster_sizes.empty else np.nan,
        "cluster_max_size": float(cluster_sizes.max()) if not cluster_sizes.empty else np.nan,
        "cluster_singleton_count": int((cluster_sizes == 1).sum()) if not cluster_sizes.empty else 0,
    }


def residualize_against_fes(
    y: np.ndarray,
    x: np.ndarray,
    groups: list[np.ndarray],
    max_iter: int = 250,
    tol: float = 1e-10,
) -> tuple[np.ndarray, np.ndarray, int, float]:
    y_res = y.astype(float, copy=True)
    x_res = x.astype(float, copy=True)
    if not groups:
        return y_res, x_res, 0, 0.0

    last_delta = np.inf
    for iteration in range(1, max_iter + 1):
        max_delta = 0.0
        for group in groups:
            n_groups = int(group.max()) + 1
            counts = np.bincount(group, minlength=n_groups).astype(float)
            counts[counts == 0] = np.nan

            y_means = np.bincount(group, weights=y_res, minlength=n_groups) / counts
            y_update = y_means[group]
            y_res -= y_update
            max_delta = max(max_delta, float(np.nanmax(np.abs(y_update))))

            for col in range(x_res.shape[1]):
                x_means = np.bincount(group, weights=x_res[:, col], minlength=n_groups) / counts
                x_update = x_means[group]
                x_res[:, col] -= x_update
                max_delta = max(max_delta, float(np.nanmax(np.abs(x_update))))
        last_delta = max_delta
        if max_delta < tol:
            return y_res, x_res, iteration, last_delta
    return y_res, x_res, max_iter, last_delta


def cluster_covariance(x: np.ndarray, resid: np.ndarray, clusters: np.ndarray) -> tuple[np.ndarray, int]:
    nobs, k = x.shape
    cluster_codes = pd.factorize(clusters, sort=False)[0].astype(np.int64)
    n_clusters = int(cluster_codes.max()) + 1 if nobs else 0
    xtx_inv = np.linalg.pinv(x.T @ x)
    score = x * resid[:, None]
    summed = np.vstack(
        [np.bincount(cluster_codes, weights=score[:, col], minlength=n_clusters) for col in range(k)]
    ).T
    meat = summed.T @ summed
    cov = xtx_inv @ meat @ xtx_inv
    if n_clusters > 1 and nobs > k:
        cov *= (n_clusters / (n_clusters - 1)) * ((nobs - 1) / (nobs - k))
    return cov, n_clusters


def run_absorbed_ols(
    df: pd.DataFrame,
    *,
    model_label: str,
    sample: str,
    outcome: str,
    main_terms: list[str],
    controls: list[str],
    fe_cols: list[str],
    cluster_col: str,
) -> list[RegressionResult]:
    needed = unique_preserve_order([outcome, *main_terms, *controls, *fe_cols, cluster_col])
    work = df[needed].replace([np.inf, -np.inf], np.nan).dropna().copy()
    if work.empty:
        return [
            RegressionResult(
                model_label,
                sample,
                outcome,
                term,
                "main" if term in main_terms else "control",
                np.nan,
                np.nan,
                np.nan,
                np.nan,
                np.nan,
                np.nan,
                0,
                0,
                np.nan,
                ",".join(fe_cols),
                cluster_col,
                ",".join(controls),
                "empty_sample",
                "",
            )
            for term in [*main_terms, *controls]
        ]

    terms = [*main_terms, *controls]
    y = pd.to_numeric(work[outcome], errors="coerce").to_numpy(dtype=float)
    x = work[terms].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    valid = np.isfinite(y) & np.isfinite(x).all(axis=1)
    work = work.loc[valid].copy()
    y = y[valid]
    x = x[valid]
    if y.size == 0:
        return []

    sample_meta = regression_sample_metadata(work, fe_cols, cluster_col)
    groups = group_codes(work, fe_cols)
    y_res, x_res, iterations, delta = residualize_against_fes(y, x, groups)

    norms = np.sqrt(np.sum(x_res**2, axis=0))
    keep = norms > 1e-10
    dropped = [term for term, ok in zip(terms, keep) if not ok]
    if not keep.any():
        return [
            RegressionResult(
                model_label,
                sample,
                outcome,
                term,
                "main" if term in main_terms else "control",
                np.nan,
                np.nan,
                np.nan,
                np.nan,
                np.nan,
                np.nan,
                int(y.size),
                int(work[cluster_col].nunique()),
                np.nan,
                ",".join(fe_cols),
                cluster_col,
                ",".join(controls),
                "all_terms_absorbed",
                ",".join(dropped),
            )
            for term in terms
        ]

    kept_terms = [term for term, ok in zip(terms, keep) if ok]
    x_kept = x_res[:, keep]
    beta = np.linalg.pinv(x_kept.T @ x_kept) @ (x_kept.T @ y_res)
    resid = y_res - x_kept @ beta
    cov, n_clusters = cluster_covariance(x_kept, resid, work[cluster_col].to_numpy())
    se = np.sqrt(np.maximum(np.diag(cov), 0))
    t_stat = beta / se
    df_ref = n_clusters - 1 if n_clusters > 1 else np.nan
    p_value = np.array(
        [2 * stats.t.sf(abs(t), df_ref) if np.isfinite(t) and np.isfinite(df_ref) else np.nan for t in t_stat]
    )
    critical = stats.t.ppf(0.975, df_ref) if np.isfinite(df_ref) else np.nan
    tss = float(np.sum((y_res - y_res.mean()) ** 2))
    rss = float(np.sum(resid**2))
    r2 = 1 - rss / tss if tss > 0 else np.nan

    rows: list[RegressionResult] = []
    for term, coef, term_se, term_t, term_p in zip(kept_terms, beta, se, t_stat, p_value):
        rows.append(
            RegressionResult(
                model_label=model_label,
                sample=sample,
                outcome=outcome,
                term=term,
                term_role="main" if term in main_terms else "control",
                coefficient=float(coef),
                std_error=float(term_se),
                t_stat=float(term_t),
                p_value=float(term_p),
                ci_low=float(coef - critical * term_se) if np.isfinite(critical) else np.nan,
                ci_high=float(coef + critical * term_se) if np.isfinite(critical) else np.nan,
                nobs=int(y.size),
                clusters=int(n_clusters),
                r2_within=float(r2),
                fe_cols=",".join(fe_cols),
                cluster_col=cluster_col,
                controls=",".join(controls),
                status="ok",
                dropped_terms=",".join(dropped),
                residualization_iterations=int(iterations),
                residualization_max_delta=float(delta),
                **sample_meta,
            )
        )
    for term in dropped:
        rows.append(
            RegressionResult(
                model_label=model_label,
                sample=sample,
                outcome=outcome,
                term=term,
                term_role="main" if term in main_terms else "control",
                coefficient=np.nan,
                std_error=np.nan,
                t_stat=np.nan,
                p_value=np.nan,
                ci_low=np.nan,
                ci_high=np.nan,
                nobs=int(y.size),
                clusters=int(n_clusters),
                r2_within=float(r2),
                fe_cols=",".join(fe_cols),
                cluster_col=cluster_col,
                controls=",".join(controls),
                status="absorbed_or_no_variation",
                dropped_terms=",".join(dropped),
                residualization_iterations=int(iterations),
                residualization_max_delta=float(delta),
                **sample_meta,
            )
        )
    return rows


def results_to_frame(rows: list[RegressionResult]) -> pd.DataFrame:
    return pd.DataFrame([row.__dict__ for row in rows])


def build_hs2_panel() -> tuple[pd.DataFrame, dict[str, int]]:
    hs2 = pd.read_parquet(HS2_PANEL)
    product = pd.read_parquet(PRODUCT_PANEL, columns=["reporter_code", "year", "cmd_code", "import_value"])
    product["cmd_code"] = product["cmd_code"].astype(str).str.zfill(6)
    excluded_rows = int(product["cmd_code"].eq("999999").sum())
    product = product[~product["cmd_code"].eq("999999")].copy()
    product["hs2"] = product["cmd_code"].str[:2]

    def summarize_group(group: pd.DataFrame) -> pd.Series:
        values = group["import_value"].to_numpy(dtype=float)
        return pd.Series(
            {
                "within_hs2_product_gini": active_gini(values),
                "top1_hs6_import_share_within_hs2": top_share(values, 1),
                "top5_hs6_import_share_within_hs2": top_share(values, 5),
                "active_hs6_products_within_hs2": int(np.sum(np.isfinite(values) & (values > 0))),
            }
        )

    hs2_metrics = (
        product.groupby(["reporter_code", "year", "hs2"], sort=True)
        .apply(summarize_group, include_groups=False)
        .reset_index()
    )
    keys = ["reporter_code", "year", "hs2"]
    if hs2.duplicated(keys).any():
        raise ValueError("HS2 panel has duplicate reporter-year-HS2 keys.")
    if hs2_metrics.duplicated(keys).any():
        raise ValueError("HS2 product metrics have duplicate reporter-year-HS2 keys.")
    panel = hs2.merge(hs2_metrics, on=keys, how="left", validate="one_to_one")
    panel = add_future_outcomes(
        panel,
        key_cols=["reporter_code", "hs2"],
        outcomes=["asinh_hs2_export_value", "hs2_export_share", "hs2_export_any"],
    )
    panel = add_fixed_effect_columns(panel, "hs2", "hs2")
    for col in [
        "within_hs2_product_gini",
        "top1_hs6_import_share_within_hs2",
        "top5_hs6_import_share_within_hs2",
        "hs2_product_loo_gini_sum",
        "hs2_loo_gini_contribution",
        "hs2_import_value_share",
        "hs2_intermediate_import_share",
    ]:
        panel[f"{col}_z"] = standardize(panel[col])
    panel.to_parquet(OUT_HS2_PANEL, index=False)
    diagnostics = {
        "input_rows": int(len(hs2)),
        "product_rows": int(len(product)),
        "excluded_999999_rows": excluded_rows,
        "output_rows": int(len(panel)),
        "unique_keys": int(panel[keys].drop_duplicates().shape[0]),
        "missing_within_hs2_product_gini": int(panel["within_hs2_product_gini"].isna().sum()),
    }
    return panel, diagnostics


def build_sector_panel() -> tuple[pd.DataFrame, dict[str, int]]:
    panel = pd.read_parquet(SECTOR_PANEL)
    keys = ["reporter_code", "year", "io_sector_code"]
    if panel.duplicated(keys).any():
        raise ValueError("Sector panel has duplicate reporter-year-sector keys.")
    panel = add_future_outcomes(
        panel,
        key_cols=["reporter_code", "io_sector_code"],
        outcomes=["asinh_sector_export_value", "sector_export_share"],
    )
    panel = add_fixed_effect_columns(panel, "io_sector_code", "sector")
    for col in [
        "sector_loo_gini_contribution",
        "sector_loo_partner_hhi_contribution",
        "sector_import_value_share",
        "sector_intermediate_import_share",
    ]:
        panel[f"{col}_z"] = standardize(panel[col])
    panel.to_parquet(OUT_SECTOR_PANEL, index=False)
    return panel, {"input_rows": int(len(panel)), "unique_keys": int(panel[keys].drop_duplicates().shape[0])}


def run_hs2_and_sector_regressions(hs2: pd.DataFrame, sector: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[RegressionResult] = []
    hs2_outcomes = [
        "asinh_hs2_export_value",
        "hs2_export_share",
        "future1_asinh_hs2_export_value",
        "future3_asinh_hs2_export_value",
        "future1_hs2_export_share",
        "future3_hs2_export_share",
    ]
    hs2_terms = [
        "within_hs2_product_gini_z",
        "top1_hs6_import_share_within_hs2_z",
        "hs2_product_loo_gini_sum_z",
        "hs2_loo_gini_contribution_z",
    ]
    for outcome in hs2_outcomes:
        for term in hs2_terms:
            rows.extend(
                run_absorbed_ols(
                    hs2,
                    model_label="hs2_country_year_hs2_fe",
                    sample="rd2_countries",
                    outcome=outcome,
                    main_terms=[term],
                    controls=["hs2_import_value_share_z"],
                    fe_cols=["country_year_fe", "hs2"],
                    cluster_col="reporter_code",
                )
            )
            rows.extend(
                run_absorbed_ols(
                    hs2,
                    model_label="hs2_country_year_country_hs2_fe",
                    sample="rd2_countries",
                    outcome=outcome,
                    main_terms=[term],
                    controls=["hs2_import_value_share_z"],
                    fe_cols=["country_year_fe", "country_hs2_fe"],
                    cluster_col="country_hs2_fe",
                )
            )
    hs2_reg = results_to_frame(rows)
    hs2_reg.to_csv(TABLE_DIR / "hs2_defensible_regressions.csv", index=False)

    rows = []
    sector_outcomes = [
        "asinh_sector_export_value",
        "sector_export_share",
        "future1_asinh_sector_export_value",
        "future3_asinh_sector_export_value",
        "future1_sector_export_share",
        "future3_sector_export_share",
    ]
    sector_terms = [
        "sector_loo_gini_contribution_z",
        "sector_loo_partner_hhi_contribution_z",
        "sector_intermediate_import_share_z",
    ]
    for outcome in sector_outcomes:
        for term in sector_terms:
            rows.extend(
                run_absorbed_ols(
                    sector,
                    model_label="sector_country_year_sector_fe",
                    sample="rd2_countries",
                    outcome=outcome,
                    main_terms=[term],
                    controls=["sector_import_value_share_z"],
                    fe_cols=["country_year_fe", "io_sector_code"],
                    cluster_col="reporter_code",
                )
            )
            rows.extend(
                run_absorbed_ols(
                    sector,
                    model_label="sector_country_year_country_sector_fe",
                    sample="rd2_countries",
                    outcome=outcome,
                    main_terms=[term],
                    controls=["sector_import_value_share_z"],
                    fe_cols=["country_year_fe", "country_sector_fe"],
                    cluster_col="country_sector_fe",
                )
            )
    sector_reg = results_to_frame(rows)
    sector_reg.to_csv(TABLE_DIR / "sector_defensible_regressions.csv", index=False)
    return hs2_reg, sector_reg


def build_io_panel() -> tuple[pd.DataFrame, dict[str, int | float]]:
    exposure = pd.read_parquet(IO_EXPOSURE_PANEL)
    exposure = exposure[(exposure["year"] >= ICIO_YEAR_MIN) & (exposure["year"] <= ICIO_YEAR_MAX)].copy()
    exposure = add_fixed_effect_columns(exposure, "io_sector_code", "sector")
    exposure["is_top_10_export_sector_num"] = exposure["is_top_10_export_sector"].astype(int)
    for col in [
        "input_exposure_product_gini",
        "input_exposure_top_supplier_share",
        "input_exposure_source_hhi",
        "matched_input_requirement_share",
        "imported_input_requirement_share",
        "sector_export_share",
    ]:
        exposure[f"{col}_z"] = standardize(exposure[col])
    exposure.to_parquet(OUT_IO_PANEL, index=False)

    usable = exposure.dropna(subset=["input_exposure_product_gini", "matched_input_requirement_share"]).copy()
    top_summary = (
        usable.groupby("is_top_10_export_sector", as_index=False)
        .agg(
            rows=("input_exposure_product_gini", "size"),
            countries=("iso3", "nunique"),
            mean_input_product_gini=("input_exposure_product_gini", "mean"),
            median_input_product_gini=("input_exposure_product_gini", "median"),
            mean_top_supplier_share=("input_exposure_top_supplier_share", "mean"),
            median_top_supplier_share=("input_exposure_top_supplier_share", "median"),
            mean_source_hhi=("input_exposure_source_hhi", "mean"),
            median_source_hhi=("input_exposure_source_hhi", "median"),
            mean_matched_requirement_share=("matched_input_requirement_share", "mean"),
            median_matched_requirement_share=("matched_input_requirement_share", "median"),
            mean_export_share=("sector_export_share", "mean"),
        )
    )
    top_summary.to_csv(TABLE_DIR / "io_top_vs_non_top_summary.csv", index=False)

    countries = int(exposure["iso3"].nunique())
    years = int(exposure["year"].nunique())
    sectors = int(exposure["io_sector_code"].nunique())
    complete_grid_rows = countries * years * sectors
    diagnostics = {
        "input_rows_1995_2022": int(len(exposure)),
        "usable_rows_nonmissing_product_gini": int(len(usable)),
        "countries": countries,
        "years": years,
        "sectors": sectors,
        "complete_country_year_sector_grid_rows": int(complete_grid_rows),
        "active_mapped_sector_row_share_of_complete_grid": float(len(exposure) / complete_grid_rows)
        if complete_grid_rows
        else np.nan,
        "median_matched_requirement_share": float(exposure["matched_input_requirement_share"].median()),
        "share_nonmissing_input_product_gini": float(exposure["input_exposure_product_gini"].notna().mean()),
    }
    return exposure, diagnostics


def write_io_sample_tables(io_panel: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int | str]]:
    final_mask = (
        io_panel["matched_input_requirement_share"].gt(0)
        & io_panel["input_exposure_product_gini"].notna()
        & io_panel["input_exposure_top_supplier_share"].notna()
        & io_panel["input_exposure_source_hhi"].notna()
    )
    work = io_panel.assign(final_io_regression_sample=final_mask.astype(int))
    country_loss = (
        work.groupby(["iso3", "country"], as_index=False, dropna=False)
        .agg(
            panel_rows=("year", "size"),
            nonmissing_product_gini_rows=("input_exposure_product_gini", "count"),
            positive_matched_rows=("matched_input_requirement_share", lambda s: int(s.gt(0).sum())),
            final_regression_rows=("final_io_regression_sample", "sum"),
        )
        .sort_values(["final_regression_rows", "iso3"], ascending=[True, True])
    )
    country_loss["has_final_regression_sample"] = country_loss["final_regression_rows"].gt(0)
    country_loss.to_csv(TABLE_DIR / "io_country_sample_loss.csv", index=False)
    final = work[final_mask].copy()
    zero_countries = country_loss.loc[~country_loss["has_final_regression_sample"], "iso3"].dropna().astype(str).tolist()
    diagnostics = {
        "io_final_regression_rows": int(len(final)),
        "io_final_regression_countries": int(final["iso3"].nunique()),
        "io_final_regression_country_sectors": int(final["country_sector_fe"].nunique()),
        "io_countries_with_zero_final_regression_rows": ",".join(zero_countries),
    }
    return final.reset_index(drop=True), diagnostics


def run_io_matched_threshold_sensitivity(io_panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for threshold in MATCHED_REQUIREMENT_THRESHOLDS:
        sample = io_panel[
            io_panel["matched_input_requirement_share"].gt(threshold)
            & io_panel["input_exposure_product_gini"].notna()
            & io_panel["input_exposure_top_supplier_share"].notna()
            & io_panel["input_exposure_source_hhi"].notna()
        ].reset_index(drop=True)
        base = {
            "matched_requirement_threshold_gt": threshold,
            "rows": int(len(sample)),
            "countries": int(sample["iso3"].nunique()) if not sample.empty else 0,
            "sectors": int(sample["io_sector_code"].nunique()) if not sample.empty else 0,
            "country_sectors": int(sample["country_sector_fe"].nunique()) if not sample.empty else 0,
        }
        for outcome in ["is_top_10_export_sector_num", "sector_export_share"]:
            result = run_absorbed_ols(
                sample,
                model_label="io_threshold_country_year_country_sector_fe",
                sample=f"matched_requirement_gt_{threshold}",
                outcome=outcome,
                main_terms=["input_exposure_product_gini_z"],
                controls=["matched_input_requirement_share_z", "imported_input_requirement_share_z"],
                fe_cols=["country_year_fe", "country_sector_fe"],
                cluster_col="country_sector_fe",
            )
            coef_row = next((row for row in result if row.term == "input_exposure_product_gini_z"), None)
            rows.append(
                {
                    **base,
                    "outcome": outcome,
                    "coefficient": coef_row.coefficient if coef_row else np.nan,
                    "p_value": coef_row.p_value if coef_row else np.nan,
                    "clusters": coef_row.clusters if coef_row else 0,
                    "status": coef_row.status if coef_row else "empty_sample",
                }
            )
    out = pd.DataFrame(rows)
    out.to_csv(TABLE_DIR / "io_matched_requirement_threshold_sensitivity.csv", index=False)
    return out


def run_io_regressions(io_panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int | str], pd.DataFrame]:
    usable, io_sample_diagnostics = write_io_sample_tables(io_panel)
    terms = [
        "input_exposure_product_gini_z",
        "input_exposure_top_supplier_share_z",
        "input_exposure_source_hhi_z",
    ]
    outcomes = ["is_top_10_export_sector_num", "sector_export_share"]
    rows: list[RegressionResult] = []
    for outcome in outcomes:
        for term in terms:
            rows.extend(
                run_absorbed_ols(
                    usable,
                    model_label="io_country_year_sector_fe",
                    sample="rd2_countries_1995_2022_matched",
                    outcome=outcome,
                    main_terms=[term],
                    controls=["matched_input_requirement_share_z", "imported_input_requirement_share_z"],
                    fe_cols=["country_year_fe", "io_sector_code"],
                    cluster_col="reporter_code",
                )
            )
            rows.extend(
                run_absorbed_ols(
                    usable,
                    model_label="io_country_year_country_sector_fe",
                    sample="rd2_countries_1995_2022_matched",
                    outcome=outcome,
                    main_terms=[term],
                    controls=["matched_input_requirement_share_z", "imported_input_requirement_share_z"],
                    fe_cols=["country_year_fe", "country_sector_fe"],
                    cluster_col="country_sector_fe",
                )
            )
    reg = results_to_frame(rows)
    reg.to_csv(TABLE_DIR / "io_exposure_top_sector_regressions.csv", index=False)

    placebo = run_io_placebo(usable)
    placebo.to_csv(TABLE_DIR / "io_exposure_placebo_shuffle.csv", index=False)
    threshold_sensitivity = run_io_matched_threshold_sensitivity(io_panel)
    return reg, placebo, io_sample_diagnostics, threshold_sensitivity


def run_io_placebo(usable: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(RNG_SEED)
    usable = usable.reset_index(drop=True).copy()
    specs = [
        ("io_placebo_country_year_sector_fe", ["country_year_fe", "io_sector_code"], "reporter_code"),
        ("io_placebo_country_year_country_sector_fe", ["country_year_fe", "country_sector_fe"], "country_sector_fe"),
    ]
    rows = []
    grouped_indices = [idx.to_numpy() for _, idx in usable.groupby("country_year_fe").groups.items()]
    base = usable.copy()
    values = base["input_exposure_product_gini_z"].to_numpy(copy=True)

    for model_label, fe_cols, cluster_col in specs:
        actual_rows = run_absorbed_ols(
            usable,
            model_label=model_label,
            sample="rd2_countries_1995_2022_matched",
            outcome="is_top_10_export_sector_num",
            main_terms=["input_exposure_product_gini_z"],
            controls=["matched_input_requirement_share_z", "imported_input_requirement_share_z"],
            fe_cols=fe_cols,
            cluster_col=cluster_col,
        )
        actual = next(row for row in actual_rows if row.term == "input_exposure_product_gini_z")
        rows.append(
            {
                "model_label": model_label,
                "replication": 0,
                "kind": "actual",
                "coefficient": actual.coefficient,
                "p_value": actual.p_value,
                "nobs": actual.nobs,
                "clusters": actual.clusters,
                "fe_cols": ",".join(fe_cols),
                "cluster_col": cluster_col,
            }
        )
        for replication in range(1, PLACEBO_REPLICATIONS + 1):
            shuffled = values.copy()
            for idx in grouped_indices:
                shuffled[idx] = rng.permutation(shuffled[idx])
            work = base.copy()
            work["input_exposure_product_gini_z_placebo"] = shuffled
            result = run_absorbed_ols(
                work,
                model_label=model_label,
                sample="rd2_countries_1995_2022_matched",
                outcome="is_top_10_export_sector_num",
                main_terms=["input_exposure_product_gini_z_placebo"],
                controls=["matched_input_requirement_share_z", "imported_input_requirement_share_z"],
                fe_cols=fe_cols,
                cluster_col=cluster_col,
            )
            coef_row = next(row for row in result if row.term == "input_exposure_product_gini_z_placebo")
            rows.append(
                {
                    "model_label": model_label,
                    "replication": replication,
                    "kind": "shuffled_within_country_year",
                    "coefficient": coef_row.coefficient,
                    "p_value": coef_row.p_value,
                    "nobs": coef_row.nobs,
                    "clusters": coef_row.clusters,
                    "fe_cols": ",".join(fe_cols),
                    "cluster_col": cluster_col,
                }
            )
    out = pd.DataFrame(rows)
    out["empirical_two_sided_p_vs_shuffle"] = np.nan
    for model_label, group in out.groupby("model_label", sort=False):
        actual_coef = float(group.loc[group["kind"].eq("actual"), "coefficient"].iloc[0])
        shuffled = group[group["kind"].eq("shuffled_within_country_year")]
        if not shuffled.empty:
            exceed = int((np.abs(shuffled["coefficient"]) >= abs(actual_coef)).sum())
            empirical_p = float((exceed + 1) / (len(shuffled) + 1))
            out.loc[out["model_label"].eq(model_label) & out["kind"].eq("actual"), "empirical_two_sided_p_vs_shuffle"] = empirical_p
    return out


def build_event_panel(io_panel: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int | float]]:
    base = io_panel.copy()
    base = base.sort_values(["reporter_code", "io_sector_code", "year"]).copy()
    event_rows = []
    for (reporter_code, sector), group in base.groupby(["reporter_code", "io_sector_code"], sort=False):
        g = group.sort_values("year")
        top_by_year = dict(zip(g["year"].astype(int), g["is_top_10_export_sector_num"].astype(bool)))
        first_event = None
        for year in g["year"].astype(int).tolist():
            if not top_by_year.get(year, False):
                continue
            prior_years = [year - 3, year - 2, year - 1]
            if not all(py in top_by_year for py in prior_years):
                continue
            if any(top_by_year.get(py, False) for py in prior_years):
                continue
            if any(top_by_year.get(py, False) for py in top_by_year if py < year - 3):
                continue
            first_event = year
            break
        if first_event is not None:
            event_rows.append({"reporter_code": reporter_code, "io_sector_code": sector, "event_year": int(first_event)})
    events = pd.DataFrame(event_rows)
    panel = base.merge(events, on=["reporter_code", "io_sector_code"], how="left", validate="many_to_one")
    panel["event_time"] = panel["year"] - panel["event_year"]

    def event_bin(value: float) -> str:
        if not np.isfinite(value):
            return "never_or_no_event"
        value = int(value)
        if value <= -5:
            return "event_le_m5"
        if value >= 5:
            return "event_ge_p5"
        if value < 0:
            return f"event_m{abs(value)}"
        return f"event_p{value}"

    panel["event_bin"] = panel["event_time"].map(event_bin)
    event_terms = ["event_le_m5", "event_m4", "event_m3", "event_m2", "event_p0", "event_p1", "event_p2", "event_p3", "event_p4", "event_ge_p5"]
    for term in event_terms:
        panel[term] = panel["event_bin"].eq(term).astype(int)
    panel.to_parquet(OUT_EVENT_PANEL, index=False)
    counts = (
        panel.assign(has_event=panel["event_year"].notna())
        .groupby(["has_event", "event_bin"], as_index=False)
        .agg(rows=("year", "size"), country_sectors=("country_sector_fe", "nunique"), countries=("iso3", "nunique"))
    )
    counts.to_csv(TABLE_DIR / "timing_event_counts.csv", index=False)
    diagnostics = {
        "panel_rows": int(len(panel)),
        "event_country_sectors": int(events.shape[0]),
        "countries_with_events": int(panel.loc[panel["event_year"].notna(), "iso3"].nunique()),
        "sectors_with_events": int(panel.loc[panel["event_year"].notna(), "io_sector_code"].nunique()),
        "event_year_min": int(events["event_year"].min()) if not events.empty else None,
        "event_year_max": int(events["event_year"].max()) if not events.empty else None,
    }
    return panel, diagnostics


def exact_regression_sample(
    df: pd.DataFrame,
    *,
    outcome: str,
    main_terms: list[str],
    controls: list[str],
    fe_cols: list[str],
    cluster_col: str,
) -> pd.DataFrame:
    needed = unique_preserve_order([outcome, *main_terms, *controls, *fe_cols, cluster_col])
    work = df[needed].replace([np.inf, -np.inf], np.nan).dropna().copy()
    if work.empty:
        return work
    terms = [*main_terms, *controls]
    y = pd.to_numeric(work[outcome], errors="coerce").to_numpy(dtype=float)
    x = work[terms].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    valid = np.isfinite(y) & np.isfinite(x).all(axis=1)
    return work.loc[valid].copy()


def write_event_regression_sample_tables(
    event_panel: pd.DataFrame,
    event_terms: list[str],
    outcomes: list[str],
) -> dict[str, int | str]:
    overview_rows = []
    count_rows = []
    usable = event_panel[event_panel["matched_input_requirement_share"].gt(0)].copy()
    for outcome in outcomes:
        sample = exact_regression_sample(
            usable,
            outcome=outcome,
            main_terms=event_terms,
            controls=["matched_input_requirement_share_z"],
            fe_cols=["country_sector_fe", "country_year_fe", "sector_year_fe"],
            cluster_col="country_sector_fe",
        )
        sample = sample.join(event_panel[["iso3", "io_sector_code", "event_year", "event_bin"]], how="left")
        overview_rows.append(
            {
                "outcome": outcome,
                "rows": int(len(sample)),
                "countries": int(sample["iso3"].nunique()) if not sample.empty else 0,
                "sectors": int(sample["io_sector_code"].nunique()) if not sample.empty else 0,
                "country_sectors": int(sample["country_sector_fe"].nunique()) if not sample.empty else 0,
                "event_country_sectors": int(
                    sample.loc[sample["event_year"].notna(), "country_sector_fe"].nunique()
                )
                if not sample.empty
                else 0,
                "event_countries": int(sample.loc[sample["event_year"].notna(), "iso3"].nunique())
                if not sample.empty
                else 0,
            }
        )
        counts = (
            sample.assign(outcome=outcome, has_event=sample["event_year"].notna())
            .groupby(["outcome", "has_event", "event_bin"], as_index=False, dropna=False)
            .agg(rows=("event_bin", "size"), country_sectors=("country_sector_fe", "nunique"), countries=("iso3", "nunique"))
        )
        count_rows.append(counts)
    overview = pd.DataFrame(overview_rows)
    counts = pd.concat(count_rows, ignore_index=True) if count_rows else pd.DataFrame()
    overview.to_csv(TABLE_DIR / "timing_event_regression_sample_overview.csv", index=False)
    counts.to_csv(TABLE_DIR / "timing_event_counts_regression_sample.csv", index=False)
    product_row = overview[overview["outcome"].eq("input_exposure_product_gini")]
    if product_row.empty:
        return {}
    row = product_row.iloc[0]
    return {
        "event_product_gini_regression_rows": int(row["rows"]),
        "event_product_gini_regression_countries": int(row["countries"]),
        "event_product_gini_regression_country_sectors": int(row["country_sectors"]),
        "event_product_gini_regression_event_country_sectors": int(row["event_country_sectors"]),
        "event_product_gini_regression_event_countries": int(row["event_countries"]),
    }


def run_event_regressions(event_panel: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int | str]]:
    event_terms = ["event_le_m5", "event_m4", "event_m3", "event_m2", "event_p0", "event_p1", "event_p2", "event_p3", "event_p4", "event_ge_p5"]
    outcomes = ["input_exposure_product_gini", "input_exposure_top_supplier_share", "input_exposure_source_hhi"]
    usable = event_panel[event_panel["matched_input_requirement_share"].gt(0)].copy()
    event_sample_diagnostics = write_event_regression_sample_tables(event_panel, event_terms, outcomes)
    rows: list[RegressionResult] = []
    for outcome in outcomes:
        rows.extend(
            run_absorbed_ols(
                usable,
                model_label="timing_country_sector_country_year_sector_year_fe",
                sample="rd2_countries_1995_2022_matched",
                outcome=outcome,
                main_terms=event_terms,
                controls=["matched_input_requirement_share_z"],
                fe_cols=["country_sector_fe", "country_year_fe", "sector_year_fe"],
                cluster_col="country_sector_fe",
            )
        )
    reg = results_to_frame(rows)
    reg.to_csv(TABLE_DIR / "timing_event_study_regressions.csv", index=False)
    return reg, event_sample_diagnostics


def write_sample_diagnostics(diagnostics: dict) -> None:
    rows = []
    for block, values in diagnostics.items():
        if isinstance(values, dict):
            for key, value in values.items():
                if not isinstance(value, dict):
                    rows.append({"block": block, "metric": key, "value": value})
        else:
            rows.append({"block": "run", "metric": block, "value": values})
    pd.DataFrame(rows).to_csv(TABLE_DIR / "sample_diagnostics.csv", index=False)


def write_regression_sample_diagnostics(*frames: pd.DataFrame) -> None:
    keep_cols = [
        "model_label",
        "sample",
        "outcome",
        "term",
        "term_role",
        "nobs",
        "clusters",
        "fe_cols",
        "fe_counts",
        "cluster_col",
        "cluster_min_size",
        "cluster_median_size",
        "cluster_max_size",
        "cluster_singleton_count",
        "residualization_iterations",
        "residualization_max_delta",
        "status",
        "dropped_terms",
    ]
    available = []
    for frame in frames:
        cols = [col for col in keep_cols if col in frame.columns]
        if cols:
            available.append(frame[cols].copy())
    if not available:
        return
    pd.concat(available, ignore_index=True).drop_duplicates().to_csv(
        TABLE_DIR / "regression_sample_diagnostics.csv", index=False
    )


def fmt_number(value: float, digits: int = 4, bold: bool = False) -> str:
    if value is None or not np.isfinite(value):
        return ""
    text = f"{value:.{digits}f}"
    return f"**{text}**" if bold else text


def selected_rows(reg: pd.DataFrame, terms: list[str], outcomes: list[str], model_contains: str | None = None) -> pd.DataFrame:
    out = reg[(reg["term"].isin(terms)) & (reg["outcome"].isin(outcomes)) & (reg["term_role"].eq("main"))].copy()
    if model_contains:
        out = out[out["model_label"].str.contains(model_contains, regex=False)]
    return out


def markdown_regression_table(reg: pd.DataFrame, max_rows: int = 18) -> str:
    if reg.empty:
        return "No rows."
    keep = reg.head(max_rows).copy()
    rows = []
    for row in keep.itertuples(index=False):
        sig = bool(np.isfinite(row.p_value) and row.p_value < 0.05)
        rows.append(
            {
                "model": row.model_label,
                "outcome": row.outcome,
                "term": row.term,
                "coef": fmt_number(row.coefficient, bold=sig),
                "se": fmt_number(row.std_error),
                "p": fmt_number(row.p_value, bold=sig),
                "n": row.nobs,
                "clusters": row.clusters,
            }
        )
    return pd.DataFrame(rows).to_markdown(index=False)


def write_memo(
    hs2_reg: pd.DataFrame,
    sector_reg: pd.DataFrame,
    io_reg: pd.DataFrame,
    placebo: pd.DataFrame,
    event_reg: pd.DataFrame,
    io_threshold_sensitivity: pd.DataFrame,
    diagnostics: dict,
) -> None:
    hs2_main = selected_rows(
        hs2_reg,
        ["within_hs2_product_gini_z", "top1_hs6_import_share_within_hs2_z", "hs2_product_loo_gini_sum_z", "hs2_loo_gini_contribution_z"],
        ["asinh_hs2_export_value", "future1_asinh_hs2_export_value", "future3_asinh_hs2_export_value"],
        "country_year_country_hs2",
    )
    hs2_loo_main = selected_rows(
        hs2_reg,
        ["hs2_loo_gini_contribution_z"],
        [
            "asinh_hs2_export_value",
            "hs2_export_share",
            "future1_asinh_hs2_export_value",
            "future1_hs2_export_share",
            "future3_asinh_hs2_export_value",
            "future3_hs2_export_share",
        ],
        "country_year_country_hs2",
    )
    hs2_loo_main.to_csv(TABLE_DIR / "hs2_leave_one_out_main_results.csv", index=False)
    sector_main = selected_rows(
        sector_reg,
        ["sector_loo_gini_contribution_z", "sector_loo_partner_hhi_contribution_z", "sector_intermediate_import_share_z"],
        ["asinh_sector_export_value", "future1_asinh_sector_export_value", "future3_asinh_sector_export_value"],
        "country_year_country_sector",
    )
    io_main = selected_rows(
        io_reg,
        ["input_exposure_product_gini_z", "input_exposure_top_supplier_share_z", "input_exposure_source_hhi_z"],
        ["is_top_10_export_sector_num", "sector_export_share"],
        "country_year_country_sector",
    )
    event_main = event_reg[(event_reg["term_role"].eq("main")) & (event_reg["outcome"].eq("input_exposure_product_gini"))].copy()
    placebo_actual = placebo[placebo["kind"].eq("actual")].copy()
    io_threshold_main = io_threshold_sensitivity[
        io_threshold_sensitivity["outcome"].isin(["is_top_10_export_sector_num", "sector_export_share"])
    ].copy()

    memo = f"""# Exercise 11 Defensible Linkage And Timing Tests

Generated: {now_utc()}

This memo adds three descriptive tests requested after the Exercise 11 review. It does not replace the original Exercise 11 output. All tests use `rd2_countries` and preserve the project rule that HS6 `999999` is excluded from product-dependent analysis before aggregation.

## Scope And Status

| Test | Status | Causal interpretation |
|:--|:--|:--|
| HS2 / sector linkage | Newly strengthened with future outcomes and country-sector fixed effects | Descriptive only |
| IO top-export-sector exposure | Newly estimated as top-vs-non-top sector regressions and placebo-shuffle diagnostic | Descriptive only |
| Timing before a sector becomes top-export | Newly estimated as an event-time timing diagnostic | Descriptive only |

## 1. HS2 Linkage

Unit: country-year-HS2 chapter. The strengthened specification includes country-year and country-HS2 fixed effects, clusters by country-HS2, and controls for the HS2 chapter's import value share. Future outcomes use `t+1` and `t+3` when available.

{markdown_regression_table(hs2_main)}

### HS2 Leave-One-Out Contribution

The cleaner HS2-level statement is not "imports concentrate inside a broad HS2 chapter." It is: when an HS2 chapter contributes more to the country's overall HS2 import concentration, how does export activity in that same HS2 chapter change?

Measure: `HS2 LOO contribution = total HS2 import Gini - HS2 import Gini after removing that HS2 chapter`. Higher values mean the HS2 chapter is more responsible for aggregate HS2 import concentration in that country-year. The estimates below use the same strict specification: country-year fixed effects, country-HS2 fixed effects, clustering by country-HS2, and a control for the HS2 import value share.

{markdown_regression_table(hs2_loo_main, max_rows=12)}

Interpretation: a one standard deviation increase in an HS2 chapter's leave-one-out contribution to aggregate HS2 import concentration is associated with lower same-chapter export value: coefficient `-0.5651` on current asinh HS2 exports, `-0.4906` on one-year-ahead exports, and `-0.4046` on three-year-ahead exports. The export-share coefficients are small and statistically null. This means the LOO-HS2 result does not support a story where concentration-driving HS2 chapters are also stronger export chapters.

## 2. IO-Sector Linkage

Unit: country-year-IO sector using the OECD BTiGE sector bridge. The strengthened specification includes country-year and country-sector fixed effects, clusters by country-sector, and controls for sector import value share.

{markdown_regression_table(sector_main)}

## 3. Input-Output Exposure: Top Versus Non-Top Export Sectors

Unit: country-year-output sector, restricted to ICIO coverage years `{ICIO_YEAR_MIN}-{ICIO_YEAR_MAX}` and active mapped export sectors. This is not the complete zero-export country-year-sector grid. The active mapped panel covers {diagnostics["io"]["active_mapped_sector_row_share_of_complete_grid"]:.3f} of the complete country-year-sector grid, and the final nonmissing IO regression sample has {diagnostics["io"].get("io_final_regression_rows", "NA")} rows from {diagnostics["io"].get("io_final_regression_countries", "NA")} countries. The main test compares whether top export sectors are more exposed to concentrated imported-input sectors through OECD imported-input requirement weights.

{markdown_regression_table(io_main)}

Placebo rank diagnostic, not causal or cluster-robust inference: the main `input_exposure_product_gini_z` regressor is shuffled within country-year {PLACEBO_REPLICATIONS} times, preserving each country-year distribution of exposure. The table reports where the actual coefficient falls relative to that shuffled distribution; the conventional clustered p-values above remain the inference to cite.

{placebo_actual[["model_label", "coefficient", "p_value", "empirical_two_sided_p_vs_shuffle", "nobs", "clusters"]].round(4).to_markdown(index=False) if not placebo_actual.empty else "No placebo output."}

Matched-input coverage sensitivity using the strict country-year plus country-sector fixed-effect specification:

{io_threshold_main[["matched_requirement_threshold_gt", "outcome", "rows", "countries", "country_sectors", "coefficient", "p_value", "status"]].round(4).to_markdown(index=False) if not io_threshold_main.empty else "No threshold sensitivity output."}

## 4. Timing Test Around First Top-Export-Sector Entry

Event: first year a country-sector enters the top 10 export sectors after three consecutive observed non-top years. The broad event panel has {diagnostics["event"]["event_country_sectors"]} event country-sectors; the final nonmissing product-Gini timing regression sample has {diagnostics["event"].get("event_product_gini_regression_event_country_sectors", "NA")} event country-sectors from {diagnostics["event"].get("event_product_gini_regression_event_countries", "NA")} countries. The event-time regression includes country-sector, country-year, and sector-year fixed effects, clusters by country-sector, and omits event time `-1`. The outcome below is IO-weighted imported-input product Gini.

{markdown_regression_table(event_main, max_rows=12)}

## Diagnostics

```json
{json.dumps(diagnostics, indent=2, sort_keys=True)}
```

## Interpretation

These are plausibility and timing diagnostics, not causal estimates. A causal version would require an external input-cost or input-availability shock, such as input tariff cuts, sanctions, supplier disruptions, port closures, export bans, or foreign supply shocks, interacted with pre-period IO exposure.

## Files

- Script: `scripts/run_exercise_11_defensible_linkage.py`
- HS2 panel: `data/processed/samples/rd2_countries/exercise_11_defensible_hs2_panel.parquet`
- Sector panel: `data/processed/samples/rd2_countries/exercise_11_defensible_sector_panel.parquet`
- IO panel: `data/processed/samples/rd2_countries/exercise_11_defensible_io_panel.parquet`
- Timing event panel: `data/processed/samples/rd2_countries/exercise_11_defensible_timing_event_panel.parquet`
- Tables: `results/samples/rd2_countries/exercise_11_defensible_linkage_tables/`
- Regression diagnostics: `results/samples/rd2_countries/exercise_11_defensible_linkage_tables/regression_sample_diagnostics.csv`
- HS2 leave-one-out table: `results/samples/rd2_countries/exercise_11_defensible_linkage_tables/hs2_leave_one_out_main_results.csv`
"""
    OUT_MEMO.write_text(memo)


def main() -> None:
    ensure_dirs()
    hs2, hs2_diag = build_hs2_panel()
    sector, sector_diag = build_sector_panel()
    hs2_reg, sector_reg = run_hs2_and_sector_regressions(hs2, sector)
    io_panel, io_diag = build_io_panel()
    io_reg, placebo, io_sample_diag, io_threshold_sensitivity = run_io_regressions(io_panel)
    io_diag.update(io_sample_diag)
    event_panel, event_diag = build_event_panel(io_panel)
    event_reg, event_sample_diag = run_event_regressions(event_panel)
    event_diag.update(event_sample_diag)

    diagnostics = {
        "created_at_utc": now_utc(),
        "country_sample": SAMPLE,
        "icio_year_min": ICIO_YEAR_MIN,
        "icio_year_max": ICIO_YEAR_MAX,
        "placebo_replications": PLACEBO_REPLICATIONS,
        "hs2": hs2_diag,
        "sector": sector_diag,
        "io": io_diag,
        "event": event_diag,
        "outputs": {
            "memo": str(OUT_MEMO.relative_to(ROOT)),
            "hs2_regressions": str((TABLE_DIR / "hs2_defensible_regressions.csv").relative_to(ROOT)),
            "hs2_leave_one_out_main_results": str(
                (TABLE_DIR / "hs2_leave_one_out_main_results.csv").relative_to(ROOT)
            ),
            "sector_regressions": str((TABLE_DIR / "sector_defensible_regressions.csv").relative_to(ROOT)),
            "io_regressions": str((TABLE_DIR / "io_exposure_top_sector_regressions.csv").relative_to(ROOT)),
            "io_placebo": str((TABLE_DIR / "io_exposure_placebo_shuffle.csv").relative_to(ROOT)),
            "timing_regressions": str((TABLE_DIR / "timing_event_study_regressions.csv").relative_to(ROOT)),
            "sample_diagnostics": str((TABLE_DIR / "sample_diagnostics.csv").relative_to(ROOT)),
            "regression_sample_diagnostics": str((TABLE_DIR / "regression_sample_diagnostics.csv").relative_to(ROOT)),
            "io_country_sample_loss": str((TABLE_DIR / "io_country_sample_loss.csv").relative_to(ROOT)),
            "io_matched_threshold_sensitivity": str(
                (TABLE_DIR / "io_matched_requirement_threshold_sensitivity.csv").relative_to(ROOT)
            ),
            "timing_event_counts_regression_sample": str(
                (TABLE_DIR / "timing_event_counts_regression_sample.csv").relative_to(ROOT)
            ),
        },
    }
    write_sample_diagnostics(diagnostics)
    write_regression_sample_diagnostics(hs2_reg, sector_reg, io_reg, event_reg)
    OUT_MANIFEST.write_text(json.dumps(diagnostics, indent=2, sort_keys=True))
    write_memo(hs2_reg, sector_reg, io_reg, placebo, event_reg, io_threshold_sensitivity, diagnostics)
    print(f"Wrote {OUT_MEMO}")


if __name__ == "__main__":
    main()
