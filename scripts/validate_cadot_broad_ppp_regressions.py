#!/usr/bin/env python3
"""Independent saved-panel checks for Cadot broad PPP hump regressions."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
TABLE_DIR = ROOT / "results" / "samples" / "cadot_broad_156" / "cadot_broad_ppp_hump_regression_tables"
PANEL = TABLE_DIR / "ppp_hump_analysis_panel.csv"
MODELS = TABLE_DIR / "ppp_hump_regression_models.csv"
OUT_CSV = TABLE_DIR / "ppp_hump_independent_reestimate_checks.csv"
OUT_MD = TABLE_DIR / "ppp_hump_independent_reestimate_checks.md"

TERMS = [
    "gdp_pc_ppp_constant_2021_intl_usd_10k",
    "gdp_pc_ppp_constant_2021_intl_usd_10k_sq",
    "log_population",
    "oil_export_share",
]


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def full_rank_columns(x: pd.DataFrame) -> pd.DataFrame:
    kept: list[str] = []
    current: pd.DataFrame | None = None
    current_rank = 0
    for col in x.columns:
        candidate = x[[col]] if current is None else pd.concat([current, x[[col]]], axis=1)
        rank = int(np.linalg.matrix_rank(candidate.to_numpy(dtype=float)))
        if rank > current_rank:
            kept.append(col)
            current = candidate
            current_rank = rank
    return x[kept]


def design_matrix(work: pd.DataFrame, terms: list[str], fixed_effects: list[str]) -> pd.DataFrame:
    parts = [pd.Series(1.0, index=work.index, name="intercept")]
    for term in terms:
        parts.append(pd.to_numeric(work[term], errors="coerce").rename(term))
    for fe_col in fixed_effects:
        dummies = pd.get_dummies(work[fe_col].astype(str), prefix=fe_col, drop_first=True, dtype=float)
        if not dummies.empty:
            parts.append(dummies)
    return full_rank_columns(pd.concat(parts, axis=1).astype(float))


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


def hc1_covariance(x: np.ndarray, resid: np.ndarray) -> np.ndarray:
    xtx_inv = np.linalg.pinv(x.T @ x)
    meat = x.T @ ((resid[:, None] ** 2) * x)
    nobs, k = x.shape
    scale = nobs / (nobs - k) if nobs > k else 1.0
    return scale * xtx_inv @ meat @ xtx_inv


def estimate(df: pd.DataFrame, outcome: str, fixed_effects: list[str], cluster_col: str) -> dict[str, Any]:
    required = [outcome, *TERMS, *fixed_effects]
    if cluster_col:
        required.append(cluster_col)
    work = df.replace([np.inf, -np.inf], np.nan).dropna(subset=list(dict.fromkeys(required))).copy()
    y = pd.to_numeric(work[outcome], errors="coerce").to_numpy(dtype=float)
    x_df = design_matrix(work, TERMS, fixed_effects)
    x = x_df.to_numpy(dtype=float)
    beta_all, *_ = np.linalg.lstsq(x, y, rcond=None)
    resid = y - x @ beta_all
    cov = cluster_robust_covariance(x, resid, work[cluster_col]) if cluster_col else hc1_covariance(x, resid)
    se_all = np.sqrt(np.maximum(np.diag(cov), 0))
    return {
        "nobs": int(len(work)),
        "clusters": int(work[cluster_col].nunique()) if cluster_col else 0,
        "beta": {term: float(beta_all[x_df.columns.get_loc(term)]) for term in TERMS if term in x_df.columns},
        "se": {term: float(se_all[x_df.columns.get_loc(term)]) for term in TERMS if term in x_df.columns},
    }


def main() -> None:
    panel = pd.read_csv(PANEL)
    models = pd.read_csv(MODELS)
    checks = [
        {
            "check": "pooled_export_product_gini_level_ppp",
            "model_label": "level_ppp_controls_year_fe_country_cluster",
            "outcome": "product_gini",
            "panel_col": "export_product_gini",
            "fixed_effects": ["year"],
            "cluster_col": "reporter_code",
        },
        {
            "check": "country_fe_import_product_gini_level_ppp",
            "model_label": "level_ppp_controls_country_year_fe_country_cluster",
            "outcome": "product_gini",
            "panel_col": "import_product_gini",
            "fixed_effects": ["reporter_code", "year"],
            "cluster_col": "reporter_code",
        },
    ]
    rows: list[dict[str, Any]] = []
    for check in checks:
        work = panel.rename(columns={check["panel_col"]: check["outcome"]})
        estimated = estimate(work, check["outcome"], check["fixed_effects"], check["cluster_col"])
        saved = models[
            models["model_label"].eq(check["model_label"])
            & models["outcome"].eq(check["outcome"])
            & models["term"].isin(TERMS)
            & models["flow"].eq("Exports" if check["panel_col"].startswith("export_") else "Imports")
        ]
        for term in TERMS:
            saved_row = saved[saved["term"].eq(term)].iloc[0]
            coef_diff = float(estimated["beta"][term] - saved_row["coefficient"])
            se_diff = float(estimated["se"][term] - saved_row["std_error"])
            rows.append(
                {
                    "check": check["check"],
                    "term": term,
                    "saved_coefficient": float(saved_row["coefficient"]),
                    "reestimated_coefficient": estimated["beta"][term],
                    "abs_coefficient_diff": abs(coef_diff),
                    "saved_std_error": float(saved_row["std_error"]),
                    "reestimated_std_error": estimated["se"][term],
                    "abs_std_error_diff": abs(se_diff),
                    "nobs": estimated["nobs"],
                    "clusters": estimated["clusters"],
                    "passed": abs(coef_diff) < 1e-8 and abs(se_diff) < 1e-8,
                }
            )
    out = pd.DataFrame(rows)
    out.to_csv(OUT_CSV, index=False)
    passed = bool(out["passed"].all())
    md = [
        "# Cadot Broad PPP Independent Re-estimation Checks",
        "",
        f"Generated: {now_utc()}",
        "",
        f"Overall status: {'passed' if passed else 'failed'}",
        "",
        "These checks re-estimate one pooled/year-FE model and one country+year-FE model from the saved analytic panel without importing `run_ppp_hump_regressions.py`.",
        "",
        out.to_markdown(index=False),
    ]
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps({"passed": passed, "rows": int(len(out)), "output": str(OUT_CSV.relative_to(ROOT))}, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
