#!/usr/bin/env python3
"""Run long-run partner concentration Cadot-style turning-point analyses."""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import scipy.linalg
import pandas as pd
import scipy.stats as stats
import statsmodels.api as sm
import statsmodels.formula.api as smf
from statsmodels.stats.sandwich_covariance import cov_cluster

from concentration_metrics import (
    active_effective_count,
    active_gini,
    active_hhi,
    active_normalized_gini,
    active_normalized_hhi,
    active_theil,
)
from historical_partner_common import (
    BOOTSTRAP_SEED,
    ENTITY_CLUSTER_COL,
    FIGURES_DIR,
    FLOW_EXPORTS,
    FLOW_IMPORTS,
    MODEL_INCOME_LEVEL,
    MODEL_INCOME_LOG,
    PRIMARY_PARTNER_THRESHOLD,
    PROCESSED_DIR,
    RESULTS_DIR,
    SUPPORTED_MIN_OBSERVATIONS,
    SUPPORTED_MIN_SIDE_ENTITIES,
    SUPPORTED_MIN_SIDE_OBSERVATIONS,
    SUPPORTED_MIN_SIDE_SHARE,
    TP_BOOTSTRAP_DRAWS,
    TRADHIST_START_YEAR,
    WCB_DRAWS,
    YEAR_COL,
    bh_adjust,
    json_default,
    now_utc,
    relpath,
    two_sided_star,
    write_json,
)

PRIMARY_VARIANT = "baseline_threshold20"
PRIMARY_MODEL = "entity_year_fe_logpop"
PRIMARY_COMPONENT = "within"
PREFERRED_POOLED_MODEL = "pooled_year_fe"


@dataclass(frozen=True)
class RegressionComponent:
    model_name: str
    curve_component: str
    linear_term: str
    square_term: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-plots", action="store_true", help="Skip figure generation.")
    return parser.parse_args()


def processed_path(name: str) -> Path:
    return PROCESSED_DIR / name


def results_path(name: str) -> Path:
    return RESULTS_DIR / name


def read_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    partner_flows = pd.read_parquet(processed_path("tradhist_partner_flows.parquet"))
    flow_panel = pd.read_parquet(processed_path("historical_partner_concentration_long.parquet"))
    partner_flows["year"] = partner_flows["year"].astype(int)
    flow_panel["year"] = flow_panel["year"].astype(int)
    return partner_flows, flow_panel


def _zero_inclusive_gini(values: np.ndarray, universe_count: int) -> float:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr) & (arr >= 0)]
    if universe_count <= 1 or arr.size == 0 or float(arr.sum()) <= 0:
        return np.nan
    padded = np.concatenate([arr[arr > 0], np.zeros(max(0, universe_count - int(np.sum(arr > 0))))])
    padded.sort()
    total = float(padded.sum())
    ranks = np.arange(1, padded.size + 1, dtype=float)
    return float((2 * np.sum(ranks * padded) / (padded.size * total)) - ((padded.size + 1) / padded.size))


def _normalized_hhi(raw_hhi: float, universe_count: int) -> float:
    if not math.isfinite(raw_hhi) or universe_count <= 1:
        return np.nan
    baseline = 1.0 / universe_count
    return float((raw_hhi - baseline) / (1.0 - baseline))


def _partner_block(year: int) -> int:
    return int((int(year) - TRADHIST_START_YEAR) // 20)


def compute_baseline_counts(flow_panel: pd.DataFrame) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    ordered = flow_panel.sort_values(["entity_id", "flow", "year"])
    for (entity_id, flow), group in ordered.groupby(["entity_id", "flow"]):
        eligible = group[group["active_partner_count"].ge(5)]
        if eligible.empty:
            counts[(str(entity_id), str(flow))] = int(group["active_partner_count"].dropna().min()) if group["active_partner_count"].notna().any() else 0
        else:
            counts[(str(entity_id), str(flow))] = int(eligible.iloc[0]["active_partner_count"])
    return counts


def apply_common_partner_blocks(flows: pd.DataFrame) -> pd.DataFrame:
    df = flows.copy()
    df["block20"] = df["year"].map(_partner_block)
    keep_masks = []
    for (_, flow, block), group in df.groupby(["entity_id", "flow", "block20"], sort=False):
        yearly_sets = []
        for _, year_group in group.groupby("year"):
            observed = year_group.loc[
                year_group["observed_positive"].astype(bool) | year_group["coded_zero"].astype(bool),
                "partner_id",
            ]
            partner_set = set(observed.astype(str))
            if partner_set:
                yearly_sets.append(partner_set)
        if not yearly_sets:
            keep_masks.append(pd.Series(False, index=group.index))
            continue
        common = set.intersection(*yearly_sets)
        keep_masks.append(group["partner_id"].astype(str).isin(common))
    if not keep_masks:
        return df.iloc[0:0].copy()
    keep = pd.concat(keep_masks).sort_index()
    return df.loc[keep].drop(columns="block20").copy()


def summarise_variant_group(
    group: pd.DataFrame,
    *,
    min_partner_count: int,
    rank_truncation: int | None,
    coded_zero_inclusive: bool,
    censor_target_count: int | None,
) -> dict[str, Any]:
    working = group.copy()
    positive_rows = working[working["observed_positive"].astype(bool)].sort_values("FLOW", ascending=False)
    if censor_target_count is not None and censor_target_count > 0:
        positive_rows = positive_rows.head(censor_target_count)
    if rank_truncation is not None and rank_truncation > 0:
        positive_rows = positive_rows.head(rank_truncation)
    keep_partner_ids = set(positive_rows["partner_id"].astype(str))
    if rank_truncation is not None or censor_target_count is not None:
        working = working[working["partner_id"].astype(str).isin(keep_partner_ids)].copy()
        positive_rows = working[working["observed_positive"].astype(bool)].sort_values("FLOW", ascending=False)

    values = positive_rows["FLOW"].to_numpy(dtype=float) if not positive_rows.empty else np.array([], dtype=float)
    active_count = int(len(positive_rows))
    coded_zero_count = int(working["coded_zero"].astype(bool).sum())
    metric_universe_count = active_count + coded_zero_count if coded_zero_inclusive else active_count
    bilateral_sum = float(np.nansum(positive_rows["FLOW"].to_numpy(dtype=float))) if not positive_rows.empty else 0.0
    raw_hhi = active_hhi(values) if active_count > 0 else np.nan

    out = {
        "entity_id": str(group["entity_id"].iloc[0]),
        "flow": str(group["flow"].iloc[0]),
        "year": int(group["year"].iloc[0]),
        "bilateral_sum_current_gbp": bilateral_sum,
        "active_partner_count": active_count,
        "coded_zero_count": coded_zero_count,
        "metric_universe_count": metric_universe_count,
        "metric_valid": active_count >= min_partner_count,
        "rank_truncation": rank_truncation,
        "coded_zero_inclusive": coded_zero_inclusive,
        "censor_target_count": censor_target_count,
    }
    if active_count == 0:
        out.update(
            {
                "partner_gini": np.nan,
                "partner_gini_normalized": np.nan,
                "partner_theil": np.nan,
                "partner_theil_normalized": np.nan,
                "partner_hhi": np.nan,
                "partner_hhi_normalized": np.nan,
                "effective_partner_count": np.nan,
            }
        )
        return out

    if coded_zero_inclusive and metric_universe_count > active_count:
        out["partner_gini"] = _zero_inclusive_gini(values, metric_universe_count)
        upper = (metric_universe_count - 1) / metric_universe_count if metric_universe_count > 1 else np.nan
        out["partner_gini_normalized"] = out["partner_gini"] / upper if upper and math.isfinite(upper) else np.nan
        shares = values / values.sum()
        out["partner_theil"] = float(np.sum(shares * np.log(shares * metric_universe_count)))
        out["partner_theil_normalized"] = out["partner_theil"] / math.log(metric_universe_count) if metric_universe_count > 1 else np.nan
        out["partner_hhi"] = raw_hhi
        out["partner_hhi_normalized"] = _normalized_hhi(raw_hhi, metric_universe_count)
    else:
        out["partner_gini"] = active_gini(values)
        out["partner_gini_normalized"] = active_normalized_gini(values) if active_count > 1 else np.nan
        out["partner_theil"] = active_theil(values, normalized=False)
        out["partner_theil_normalized"] = active_theil(values, normalized=True) if active_count > 1 else np.nan
        out["partner_hhi"] = raw_hhi
        out["partner_hhi_normalized"] = active_normalized_hhi(values) if active_count > 1 else np.nan
    out["effective_partner_count"] = active_effective_count(values)
    return out


def compute_variant_panel(
    partner_flows: pd.DataFrame,
    flow_panel: pd.DataFrame,
    *,
    variant_label: str,
    min_partner_count: int = PRIMARY_PARTNER_THRESHOLD,
    rank_truncation: int | None = None,
    common_partner_blocks: bool = False,
    coded_zero_inclusive: bool = False,
    exclude_years: tuple[int, int] | None = None,
    pre_or_post_1948: str | None = None,
    exclude_entities: set[str] | None = None,
    synthetic_censoring: bool = False,
) -> pd.DataFrame:
    df = partner_flows[partner_flows["partner_included_main_panel"].astype(bool)].copy()
    if exclude_entities:
        df = df[~df["entity_id"].isin(exclude_entities)].copy()
    if exclude_years is not None:
        start, end = exclude_years
        df = df[~df["year"].between(start, end)].copy()
    if pre_or_post_1948 == "pre":
        df = df[df["year"] < 1948].copy()
    elif pre_or_post_1948 == "post":
        df = df[df["year"] >= 1948].copy()
    if common_partner_blocks:
        df = apply_common_partner_blocks(df)

    base_controls = flow_panel[
        [
            "entity_id",
            "entity_label",
            "entity_boundary_note",
            "flow",
            "year",
            "mpd_countrycode",
            "mpd_country",
            "mpd_region",
            "mpd_gdppc_2011_usd",
            "mpd_population_thousands",
            "gdppc_10k",
            "gdppc_10k_sq",
            "log_gdppc",
            "log_gdppc_sq",
            "log_population",
        ]
    ].drop_duplicates(["entity_id", "flow", "year"])
    baseline_counts = compute_baseline_counts(flow_panel) if synthetic_censoring else {}

    rows: list[dict[str, Any]] = []
    for _, group in df.groupby(["entity_id", "flow", "year"], sort=True):
        target_count = None
        if synthetic_censoring:
            target_count = baseline_counts.get((str(group["entity_id"].iloc[0]), str(group["flow"].iloc[0])))
        rows.append(
            summarise_variant_group(
                group,
                min_partner_count=min_partner_count,
                rank_truncation=rank_truncation,
                coded_zero_inclusive=coded_zero_inclusive,
                censor_target_count=target_count,
            )
        )
    panel = pd.DataFrame.from_records(rows)
    panel = panel.merge(base_controls, on=["entity_id", "flow", "year"], how="left", validate="one_to_one")
    panel["variant"] = variant_label
    panel["minimum_partner_count"] = min_partner_count
    return panel.sort_values(["variant", "entity_id", "flow", "year"]).reset_index(drop=True)


def build_variant_collection(partner_flows: pd.DataFrame, flow_panel: pd.DataFrame) -> dict[str, pd.DataFrame]:
    variants = {
        PRIMARY_VARIANT: compute_variant_panel(partner_flows, flow_panel, variant_label=PRIMARY_VARIANT, min_partner_count=20),
        "threshold5": compute_variant_panel(partner_flows, flow_panel, variant_label="threshold5", min_partner_count=5),
        "threshold10": compute_variant_panel(partner_flows, flow_panel, variant_label="threshold10", min_partner_count=10),
        "threshold30": compute_variant_panel(partner_flows, flow_panel, variant_label="threshold30", min_partner_count=30),
        "common_partner_block20": compute_variant_panel(
            partner_flows, flow_panel, variant_label="common_partner_block20", min_partner_count=20, common_partner_blocks=True
        ),
        "coded_zero_inclusive": compute_variant_panel(
            partner_flows, flow_panel, variant_label="coded_zero_inclusive", min_partner_count=20, coded_zero_inclusive=True
        ),
        "rank_top5": compute_variant_panel(partner_flows, flow_panel, variant_label="rank_top5", min_partner_count=5, rank_truncation=5),
        "rank_top10": compute_variant_panel(partner_flows, flow_panel, variant_label="rank_top10", min_partner_count=10, rank_truncation=10),
        "rank_top20": compute_variant_panel(partner_flows, flow_panel, variant_label="rank_top20", min_partner_count=20, rank_truncation=20),
        "exclude_wwi": compute_variant_panel(
            partner_flows, flow_panel, variant_label="exclude_wwi", min_partner_count=20, exclude_years=(1914, 1918)
        ),
        "exclude_wwii": compute_variant_panel(
            partner_flows, flow_panel, variant_label="exclude_wwii", min_partner_count=20, exclude_years=(1939, 1945)
        ),
        "pre1948_only": compute_variant_panel(
            partner_flows, flow_panel, variant_label="pre1948_only", min_partner_count=20, pre_or_post_1948="pre"
        ),
        "post1948_only": compute_variant_panel(
            partner_flows, flow_panel, variant_label="post1948_only", min_partner_count=20, pre_or_post_1948="post"
        ),
        "exclude_ussr_rus": compute_variant_panel(
            partner_flows, flow_panel, variant_label="exclude_ussr_rus", min_partner_count=20, exclude_entities={"USSR", "RUS"}
        ),
        "synthetic_censoring": compute_variant_panel(
            partner_flows, flow_panel, variant_label="synthetic_censoring", min_partner_count=20, synthetic_censoring=True
        ),
    }
    return variants


def prepare_model_dataset(panel: pd.DataFrame, outcome: str, income_form: str, model_name: str, sample_policy: str) -> tuple[pd.DataFrame, list[str]]:
    linear = income_form
    square = f"{income_form}_sq"
    required = [outcome, linear, square, ENTITY_CLUSTER_COL, YEAR_COL]
    if model_name in {"entity_year_fe_logpop", "mundlak"}:
        required.append("log_population")
    required = sorted(set(required))
    df = panel.copy()
    if sample_policy == "fixed":
        df = df.dropna(subset=required).copy()
    else:
        df = df.dropna(subset=[col for col in required if col in df.columns]).copy()
    if df.empty:
        return df, required

    if model_name == "mundlak":
        group = df.groupby(ENTITY_CLUSTER_COL)
        df[f"{linear}_mean"] = group[linear].transform("mean")
        df[f"{square}_mean"] = group[square].transform("mean")
        df[f"{linear}_within"] = df[linear] - df[f"{linear}_mean"]
        df[f"{square}_within"] = df[square] - df[f"{square}_mean"]
    return df, required


def model_formula(outcome: str, income_form: str, model_name: str) -> tuple[str, list[RegressionComponent]]:
    linear = income_form
    square = f"{income_form}_sq"
    if model_name == "pooled_minimal":
        return f"{outcome} ~ {linear} + {square}", [RegressionComponent(model_name, "overall", linear, square)]
    if model_name == "pooled_year_fe":
        return f"{outcome} ~ {linear} + {square} + C(year)", [RegressionComponent(model_name, "overall", linear, square)]
    if model_name == "entity_year_fe":
        return f"{outcome} ~ {linear} + {square} + C(entity_id) + C(year)", [
            RegressionComponent(model_name, "within", linear, square)
        ]
    if model_name == "entity_year_fe_logpop":
        return f"{outcome} ~ {linear} + {square} + log_population + C(entity_id) + C(year)", [
            RegressionComponent(model_name, "within", linear, square)
        ]
    if model_name == "mundlak":
        formula = (
            f"{outcome} ~ {linear}_within + {square}_within + {linear}_mean + {square}_mean + "
            "log_population + C(year)"
        )
        return formula, [
            RegressionComponent(model_name, "within", f"{linear}_within", f"{square}_within"),
            RegressionComponent(model_name, "between", f"{linear}_mean", f"{square}_mean"),
        ]
    raise ValueError(f"Unsupported model: {model_name}")


def robust_result(result: Any, groups: pd.Series) -> Any:
    return result.get_robustcov_results(cov_type="cluster", groups=groups, use_t=True)


def param_series(robust: Any) -> tuple[pd.Series, pd.Series, pd.Series]:
    names = list(robust.model.exog_names)
    params = pd.Series(np.asarray(robust.params), index=names)
    bse = pd.Series(np.asarray(robust.bse), index=names)
    pvalues = pd.Series(np.asarray(robust.pvalues), index=names)
    return params, bse, pvalues


def cluster_contrast_se(x: np.ndarray, residuals: np.ndarray, clusters: np.ndarray, contrast: np.ndarray) -> float:
    inv_xx = np.linalg.pinv(x.T @ x)
    unique_clusters = pd.unique(clusters)
    g = len(unique_clusters)
    n, k = x.shape
    meat = np.zeros((k, k), dtype=float)
    for cluster in unique_clusters:
        mask = clusters == cluster
        score = x[mask].T @ residuals[mask]
        meat += np.outer(score, score)
    correction = 1.0
    if g > 1 and n > k:
        correction = (g / (g - 1)) * ((n - 1) / (n - k))
    variance = correction * contrast @ inv_xx @ meat @ inv_xx @ contrast
    return float(np.sqrt(max(variance, 0.0)))


def asymptotic_contrast_pvalue(
    params: pd.Series,
    x: np.ndarray,
    residuals: np.ndarray,
    clusters: np.ndarray,
    contrast: np.ndarray,
    *,
    alternative: str,
) -> tuple[float, float]:
    estimate = float(contrast @ params.reindex(list(params.index), fill_value=0.0).to_numpy(dtype=float))
    se = cluster_contrast_se(x, residuals, clusters, contrast)
    if not math.isfinite(se) or se <= 0:
        return estimate, np.nan
    t_stat = estimate / se
    df = max(len(pd.unique(clusters)) - 1, 1)
    if alternative == "less":
        p_value = stats.t.cdf(t_stat, df)
    elif alternative == "greater":
        p_value = 1.0 - stats.t.cdf(t_stat, df)
    else:
        p_value = 2.0 * (1.0 - stats.t.cdf(abs(t_stat), df))
    return estimate, float(p_value)


def wild_cluster_bootstrap_pvalue(
    result: Any,
    groups: np.ndarray,
    contrast: np.ndarray,
    *,
    null_value: float = 0.0,
    alternative: str = "two-sided",
    seed: int = BOOTSTRAP_SEED,
    draws: int = WCB_DRAWS,
) -> float:
    x = np.asarray(result.model.exog, dtype=float)
    y = np.asarray(result.model.endog, dtype=float)
    params = np.asarray(result.params, dtype=float)
    inv_xx = np.linalg.pinv(x.T @ x)

    contrast_vec = np.asarray(contrast, dtype=float).reshape(-1)
    denom = float(contrast_vec @ inv_xx @ contrast_vec)
    if not math.isfinite(denom) or abs(denom) <= 1e-15:
        return np.nan
    restricted = params - inv_xx @ contrast_vec * ((float(contrast_vec @ params) - null_value) / denom)
    restricted_residuals = y - x @ restricted

    observed_residuals = y - x @ params
    observed_se = cluster_contrast_se(x, observed_residuals, groups, contrast_vec)
    if not math.isfinite(observed_se) or observed_se <= 0:
        return np.nan
    observed_t = (float(contrast_vec @ params) - null_value) / observed_se

    cluster_ids = pd.unique(groups)
    g = len(cluster_ids)
    n, k = x.shape
    cluster_masks = [groups == cluster for cluster in cluster_ids]
    z_blocks = [restricted_residuals[mask] for mask in cluster_masks]

    a = np.zeros(g, dtype=float)
    b = np.zeros((g, g), dtype=float)
    correction = (g / (g - 1)) * ((n - 1) / (n - k)) if g > 1 and n > k else 1.0

    for h, mask_h in enumerate(cluster_masks):
        z_h = np.zeros(n, dtype=float)
        z_h[mask_h] = restricted_residuals[mask_h]
        xz = x.T @ z_h
        a[h] = float(contrast_vec @ inv_xx @ xz)
        e_h = z_h - x @ (inv_xx @ xz)
        for g_idx, mask_g in enumerate(cluster_masks):
            if not np.any(mask_g):
                continue
            score = x[mask_g].T @ e_h[mask_g]
            b[g_idx, h] = float(contrast_vec @ inv_xx @ score)

    rng = np.random.default_rng(seed)
    weights = rng.choice(np.array([-1.0, 1.0]), size=(draws, g))
    numerators = weights @ a
    score_terms = weights @ b.T
    variances = correction * np.sum(score_terms * score_terms, axis=1)
    valid = variances > 1e-16
    if not np.any(valid):
        return np.nan
    t_stats = numerators[valid] / np.sqrt(variances[valid])
    if alternative == "less":
        return float(np.mean(t_stats <= observed_t))
    if alternative == "greater":
        return float(np.mean(t_stats >= observed_t))
    return float(np.mean(np.abs(t_stats) >= abs(observed_t)))


def turning_point_value(params: pd.Series, linear_term: str, square_term: str, income_form: str) -> tuple[float, float]:
    beta1 = float(params.get(linear_term, np.nan))
    beta2 = float(params.get(square_term, np.nan))
    if not (math.isfinite(beta1) and math.isfinite(beta2)) or abs(beta2) <= 1e-15:
        return np.nan, np.nan
    tp_var = -beta1 / (2.0 * beta2)
    if income_form == MODEL_INCOME_LEVEL:
        return tp_var, tp_var * 10_000.0
    if income_form == MODEL_INCOME_LOG and -50 < tp_var < 50:
        return tp_var, float(math.exp(tp_var))
    return tp_var, np.nan


def cluster_pairs_turning_point_interval(
    result: Any,
    groups: np.ndarray,
    linear_term: str,
    square_term: str,
    income_form: str,
    *,
    seed: int = BOOTSTRAP_SEED,
    draws: int = TP_BOOTSTRAP_DRAWS,
) -> tuple[float, float]:
    x = np.asarray(result.model.exog, dtype=float)
    y = np.asarray(result.model.endog, dtype=float)
    names = list(result.model.exog_names)
    cluster_ids = pd.unique(groups)
    counts = np.zeros((len(cluster_ids), x.shape[1], x.shape[1]), dtype=float)
    xys = np.zeros((len(cluster_ids), x.shape[1]), dtype=float)
    for idx, cluster in enumerate(cluster_ids):
        mask = groups == cluster
        xg = x[mask]
        yg = y[mask]
        counts[idx] = xg.T @ xg
        xys[idx] = xg.T @ yg
    li = names.index(linear_term)
    sq = names.index(square_term)
    rng = np.random.default_rng(seed)
    draws_tp = []
    for _ in range(draws):
        sampled = rng.integers(0, len(cluster_ids), size=len(cluster_ids))
        multipliers = np.bincount(sampled, minlength=len(cluster_ids)).astype(float)
        xtx = np.tensordot(multipliers, counts, axes=(0, 0))
        xty = np.tensordot(multipliers, xys, axes=(0, 0))
        if not np.isfinite(xtx).all() or not np.isfinite(xty).all():
            continue
        try:
            beta = scipy.linalg.pinvh(xtx) @ xty
        except (np.linalg.LinAlgError, ValueError):
            continue
        beta2 = float(beta[sq])
        if not math.isfinite(beta2) or abs(beta2) <= 1e-15:
            continue
        beta1 = float(beta[li])
        tp_var = -beta1 / (2.0 * beta2)
        if income_form == MODEL_INCOME_LEVEL:
            tp = tp_var * 10_000.0
        else:
            tp = float(math.exp(tp_var)) if -50 < tp_var < 50 else np.nan
        if math.isfinite(tp):
            draws_tp.append(tp)
    if not draws_tp:
        return np.nan, np.nan
    return float(np.quantile(draws_tp, 0.025)), float(np.quantile(draws_tp, 0.975))


def classify_u_shape(
    params: pd.Series,
    robust: Any,
    data: pd.DataFrame,
    component: RegressionComponent,
    income_form: str,
    *,
    use_wcb: bool = False,
) -> dict[str, Any]:
    x = np.asarray(robust.model.exog, dtype=float)
    residuals = np.asarray(robust.model.endog - robust.model.exog @ np.asarray(robust.params, dtype=float), dtype=float)
    groups = data[ENTITY_CLUSTER_COL].to_numpy()
    exog_names = list(robust.model.exog_names)
    linear = component.linear_term
    square = component.square_term
    l = float(data[income_form].quantile(0.05))
    h = float(data[income_form].quantile(0.95))
    li = exog_names.index(linear)
    sqi = exog_names.index(square)
    contrast_l = np.zeros(len(exog_names), dtype=float)
    contrast_h = np.zeros(len(exog_names), dtype=float)
    contrast_l[li] = 1.0
    contrast_l[sqi] = 2.0 * l
    contrast_h[li] = 1.0
    contrast_h[sqi] = 2.0 * h

    slope_l, p_l_asym = asymptotic_contrast_pvalue(params, x, residuals, groups, contrast_l, alternative="less")
    slope_h, p_h_asym = asymptotic_contrast_pvalue(params, x, residuals, groups, contrast_h, alternative="greater")
    p_l = p_l_asym
    p_h = p_h_asym
    if use_wcb:
        p_l = wild_cluster_bootstrap_pvalue(robust, groups, contrast_l, alternative="less")
        p_h = wild_cluster_bootstrap_pvalue(robust, groups, contrast_h, alternative="greater")
    u_p = max(p_l, p_h)
    tp_var, tp_ppp = turning_point_value(params, linear, square, income_form)
    inside = math.isfinite(tp_var) and l <= tp_var <= h
    obs_below = int((data[income_form] < tp_var).sum()) if math.isfinite(tp_var) else 0
    obs_above = int((data[income_form] > tp_var).sum()) if math.isfinite(tp_var) else 0
    entity_below = int(data.loc[data[income_form] < tp_var, ENTITY_CLUSTER_COL].nunique()) if math.isfinite(tp_var) else 0
    entity_above = int(data.loc[data[income_form] > tp_var, ENTITY_CLUSTER_COL].nunique()) if math.isfinite(tp_var) else 0
    side_share_below = obs_below / len(data) if len(data) else 0.0
    side_share_above = obs_above / len(data) if len(data) else 0.0
    support_ok = (
        entity_below >= SUPPORTED_MIN_SIDE_ENTITIES
        and entity_above >= SUPPORTED_MIN_SIDE_ENTITIES
        and obs_below >= SUPPORTED_MIN_SIDE_OBSERVATIONS
        and obs_above >= SUPPORTED_MIN_SIDE_OBSERVATIONS
        and side_share_below >= SUPPORTED_MIN_SIDE_SHARE
        and side_share_above >= SUPPORTED_MIN_SIDE_SHARE
    )

    beta2 = float(params.get(square, np.nan))
    if not math.isfinite(tp_var) or len(data) < SUPPORTED_MIN_OBSERVATIONS:
        classification = "insufficient_support"
    elif not inside:
        classification = "outside_support"
    elif not support_ok:
        classification = "insufficient_support"
    elif beta2 <= 0 or not (slope_l < 0 and slope_h > 0):
        classification = "no_u_shape"
    elif math.isfinite(u_p) and u_p < 0.05:
        classification = "supported_u_shape"
    elif beta2 > 0:
        classification = "suggestive_only"
    else:
        classification = "no_u_shape"
    return {
        "support_p05": l,
        "support_p95": h,
        "slope_p05": slope_l,
        "slope_p95": slope_h,
        "slope_p05_p_value": p_l,
        "slope_p95_p_value": p_h,
        "u_test_p_value": u_p,
        "turning_point_income_variable": tp_var,
        "turning_point_ppp_2011_usd": tp_ppp,
        "turning_point_inside_p05_p95": inside,
        "obs_below_turning_point": obs_below,
        "obs_above_turning_point": obs_above,
        "entity_below_turning_point": entity_below,
        "entity_above_turning_point": entity_above,
        "classification": classification,
    }


def fit_suite(
    panel: pd.DataFrame,
    *,
    variant: str,
    flow: str,
    metric_name: str,
    outcome: str,
    income_form: str,
    sample_policy: str,
    run_wcb: bool,
    model_names: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    summary_rows: list[dict[str, Any]] = []
    term_rows: list[dict[str, Any]] = []
    attrition_rows: list[dict[str, Any]] = []
    fitted_lookup: dict[str, Any] = {}

    data = panel[(panel["flow"] == flow) & panel["metric_valid"].astype(bool)].copy()
    data = data.dropna(subset=[outcome]).copy()
    starting_obs = len(data)
    starting_entities = int(data[ENTITY_CLUSTER_COL].nunique())
    for model_name in model_names:
        analytic, required = prepare_model_dataset(data, outcome, income_form, model_name, sample_policy)
        attrition_rows.append(
            {
                "variant": variant,
                "flow": flow,
                "metric_name": metric_name,
                "outcome": outcome,
                "income_form": income_form,
                "sample_policy": sample_policy,
                "model_name": model_name,
                "starting_obs": starting_obs,
                "starting_entities": starting_entities,
                "analytic_obs": int(len(analytic)),
                "analytic_entities": int(analytic[ENTITY_CLUSTER_COL].nunique()) if not analytic.empty else 0,
                "required_columns": ", ".join(required),
            }
        )
        if analytic.empty or analytic[ENTITY_CLUSTER_COL].nunique() < 3 or len(analytic) <= 10:
            continue
        formula, components = model_formula(outcome, income_form, model_name)
        result = smf.ols(formula, data=analytic).fit()
        robust = robust_result(result, analytic[ENTITY_CLUSTER_COL])
        params, bse, pvalues = param_series(robust)
        groups = analytic[ENTITY_CLUSTER_COL].to_numpy()
        for component in components:
            use_wcb_component = (
                run_wcb
                and variant == PRIMARY_VARIANT
                and income_form == MODEL_INCOME_LEVEL
                and sample_policy == "fixed"
                and component.model_name in {PRIMARY_MODEL, PREFERRED_POOLED_MODEL}
            )
            classification = classify_u_shape(
                params,
                robust,
                analytic,
                component,
                income_form,
                use_wcb=use_wcb_component and component.curve_component in {"overall", "within"},
            )
            tp_low, tp_high = (np.nan, np.nan)
            if use_wcb_component and component.curve_component in {"overall", "within"}:
                tp_low, tp_high = cluster_pairs_turning_point_interval(
                    result,
                    groups,
                    component.linear_term,
                    component.square_term,
                    income_form,
                )
            model_key = f"{variant}|{flow}|{metric_name}|{income_form}|{sample_policy}|{component.model_name}|{component.curve_component}"
            fitted_lookup[model_key] = {
                "result": result,
                "robust": robust,
                "data": analytic,
                "component": component,
            }
            summary_rows.append(
                {
                    "variant": variant,
                    "flow": flow,
                    "metric_name": metric_name,
                    "outcome": outcome,
                    "income_form": income_form,
                    "sample_policy": sample_policy,
                    "model_name": component.model_name,
                    "curve_component": component.curve_component,
                    "observations": int(len(analytic)),
                    "entity_count": int(analytic[ENTITY_CLUSTER_COL].nunique()),
                    "support_p05": classification["support_p05"],
                    "support_p95": classification["support_p95"],
                    "turning_point_income_variable": classification["turning_point_income_variable"],
                    "turning_point_ppp_2011_usd": classification["turning_point_ppp_2011_usd"],
                    "turning_point_ci_low_ppp_2011_usd": tp_low,
                    "turning_point_ci_high_ppp_2011_usd": tp_high,
                    "turning_point_inside_p05_p95": classification["turning_point_inside_p05_p95"],
                    "slope_p05": classification["slope_p05"],
                    "slope_p95": classification["slope_p95"],
                    "slope_p05_p_value": classification["slope_p05_p_value"],
                    "slope_p95_p_value": classification["slope_p95_p_value"],
                    "u_test_p_value": classification["u_test_p_value"],
                    "obs_below_turning_point": classification["obs_below_turning_point"],
                    "obs_above_turning_point": classification["obs_above_turning_point"],
                    "entity_below_turning_point": classification["entity_below_turning_point"],
                    "entity_above_turning_point": classification["entity_above_turning_point"],
                    "classification": classification["classification"],
                    "cluster_count_reference": int(pd.Series(groups).nunique()),
                    "linear_term_name": component.linear_term,
                    "square_term_name": component.square_term,
                    "linear_term_coefficient": float(params.get(component.linear_term, np.nan)),
                    "linear_term_cluster_se": float(bse.get(component.linear_term, np.nan)),
                    "linear_term_cluster_p_value": float(pvalues.get(component.linear_term, np.nan)),
                    "square_term_coefficient": float(params.get(component.square_term, np.nan)),
                    "square_term_cluster_se": float(bse.get(component.square_term, np.nan)),
                    "square_term_cluster_p_value": float(pvalues.get(component.square_term, np.nan)),
                }
            )
            focal_terms = {component.linear_term, component.square_term}
            if "log_population" in params.index:
                focal_terms.add("log_population")
            for term in focal_terms:
                term_rows.append(
                    {
                        "variant": variant,
                        "flow": flow,
                        "metric_name": metric_name,
                        "outcome": outcome,
                        "income_form": income_form,
                        "sample_policy": sample_policy,
                        "model_name": component.model_name,
                        "curve_component": component.curve_component,
                        "term": term,
                        "coefficient": float(params.get(term, np.nan)),
                        "cluster_se_reference": float(bse.get(term, np.nan)),
                        "cluster_p_value_reference": float(pvalues.get(term, np.nan)),
                    }
                )
    return summary_rows, term_rows, attrition_rows, fitted_lookup


def run_regression_collection(variants: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    summary_rows: list[dict[str, Any]] = []
    term_rows: list[dict[str, Any]] = []
    attrition_rows: list[dict[str, Any]] = []
    fitted_lookup: dict[str, Any] = {}
    baseline_variants = {PRIMARY_VARIANT}
    for variant, panel in variants.items():
        print(f"[historical_partner_cadot] variant={variant}", flush=True)
        outcome_map = {
            "partner_gini": "Gini",
            "partner_theil": "Theil",
            "partner_hhi": "HHI",
        }
        if variant in baseline_variants:
            execution_grid = [
                (MODEL_INCOME_LEVEL, "fixed", ["pooled_minimal", "pooled_year_fe", "entity_year_fe", "entity_year_fe_logpop", "mundlak"]),
                (MODEL_INCOME_LEVEL, "natural", ["pooled_year_fe", "entity_year_fe_logpop"]),
                (MODEL_INCOME_LOG, "fixed", ["pooled_year_fe", "entity_year_fe_logpop", "mundlak"]),
                (MODEL_INCOME_LOG, "natural", ["pooled_year_fe", "entity_year_fe_logpop"]),
            ]
        else:
            execution_grid = [
                (MODEL_INCOME_LEVEL, "fixed", ["pooled_year_fe", "entity_year_fe_logpop"]),
            ]
        for flow in [FLOW_EXPORTS, FLOW_IMPORTS]:
            for outcome, metric_name in outcome_map.items():
                for income_form, sample_policy, model_names in execution_grid:
                        use_wcb = variant == PRIMARY_VARIANT
                        summary, terms, attrition, fitted = fit_suite(
                            panel,
                            variant=variant,
                            flow=flow,
                            metric_name=metric_name,
                            outcome=outcome,
                            income_form=income_form,
                            sample_policy=sample_policy,
                            run_wcb=use_wcb,
                            model_names=model_names,
                        )
                        summary_rows.extend(summary)
                        term_rows.extend(terms)
                        attrition_rows.extend(attrition)
                        fitted_lookup.update(fitted)
    summary_df = pd.DataFrame.from_records(summary_rows)
    term_df = pd.DataFrame.from_records(term_rows)
    attrition_df = pd.DataFrame.from_records(attrition_rows)
    if not summary_df.empty:
        primary_mask = (
            summary_df["variant"].eq(PRIMARY_VARIANT)
            & summary_df["income_form"].eq(MODEL_INCOME_LEVEL)
            & summary_df["sample_policy"].eq("fixed")
            & summary_df["model_name"].eq(PRIMARY_MODEL)
            & summary_df["curve_component"].eq(PRIMARY_COMPONENT)
        )
        q_vals = bh_adjust(summary_df.loc[primary_mask, "u_test_p_value"].tolist())
        summary_df["u_test_q_value"] = np.nan
        summary_df.loc[primary_mask, "u_test_q_value"] = q_vals
    return summary_df, term_df, attrition_df, fitted_lookup


def run_leave_one_out(primary_panel: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    entities = sorted(primary_panel["entity_id"].dropna().unique().tolist())
    outcome_map = {
        "partner_gini": "Gini",
        "partner_theil": "Theil",
        "partner_hhi": "HHI",
    }
    for excluded in entities:
        print(f"[historical_partner_cadot] leave_one_out={excluded}", flush=True)
        panel = primary_panel[primary_panel["entity_id"] != excluded].copy()
        for flow in [FLOW_EXPORTS, FLOW_IMPORTS]:
            flow_data = panel[(panel["flow"] == flow) & panel["metric_valid"].astype(bool)].copy()
            for outcome, metric_name in outcome_map.items():
                data = flow_data.dropna(subset=[outcome]).copy()
                analytic, _ = prepare_model_dataset(data, outcome, MODEL_INCOME_LEVEL, PRIMARY_MODEL, "fixed")
                if analytic.empty or analytic[ENTITY_CLUSTER_COL].nunique() < 3:
                    continue
                formula, components = model_formula(outcome, MODEL_INCOME_LEVEL, PRIMARY_MODEL)
                result = smf.ols(formula, data=analytic).fit()
                robust = robust_result(result, analytic[ENTITY_CLUSTER_COL])
                params, bse, pvalues = param_series(robust)
                component = components[0]
                classification = classify_u_shape(
                    params,
                    robust,
                    analytic,
                    component,
                    MODEL_INCOME_LEVEL,
                    use_wcb=False,
                )
                rows.append(
                    {
                        "variant": f"leave_one_out_{excluded}",
                        "excluded_entity_id": excluded,
                        "flow": flow,
                        "metric_name": metric_name,
                        "outcome": outcome,
                        "income_form": MODEL_INCOME_LEVEL,
                        "sample_policy": "fixed",
                        "model_name": PRIMARY_MODEL,
                        "curve_component": PRIMARY_COMPONENT,
                        "observations": int(len(analytic)),
                        "entity_count": int(analytic[ENTITY_CLUSTER_COL].nunique()),
                        "turning_point_ppp_2011_usd": classification["turning_point_ppp_2011_usd"],
                        "support_p05": classification["support_p05"],
                        "support_p95": classification["support_p95"],
                        "classification": classification["classification"],
                        "square_term_coefficient": float(params.get(component.square_term, np.nan)),
                        "square_term_cluster_se": float(bse.get(component.square_term, np.nan)),
                        "square_term_cluster_p_value": float(pvalues.get(component.square_term, np.nan)),
                    }
                )
    return pd.DataFrame.from_records(rows)


def preferred_pooled_turning_points(summary_df: pd.DataFrame) -> dict[tuple[str, str], dict[str, Any]]:
    preferred = summary_df[
        summary_df["variant"].eq(PRIMARY_VARIANT)
        & summary_df["income_form"].eq(MODEL_INCOME_LEVEL)
        & summary_df["sample_policy"].eq("fixed")
        & summary_df["model_name"].eq(PREFERRED_POOLED_MODEL)
        & summary_df["curve_component"].eq("overall")
    ]
    mapping: dict[tuple[str, str], dict[str, Any]] = {}
    for _, row in preferred.iterrows():
        supported = str(row["classification"]) == "supported_u_shape"
        mapping[(str(row["flow"]), str(row["metric_name"]))] = {
            "turning_point_ppp_2011_usd": float(row["turning_point_ppp_2011_usd"]) if supported else np.nan,
            "pooled_model_classification": str(row["classification"]),
            "pooled_model_supported": supported,
            "u_test_p_value": float(row["u_test_p_value"]) if pd.notna(row["u_test_p_value"]) else np.nan,
        }
    return mapping


def rolling_trough_year(group: pd.DataFrame, outcome: str) -> tuple[float, float]:
    g = group.sort_values("year")[["year", outcome, "mpd_gdppc_2011_usd"]].dropna()
    if g.empty:
        return np.nan, np.nan
    smooth = g[outcome].rolling(window=11, center=True, min_periods=3).median()
    idx = int(smooth.idxmin()) if smooth.notna().any() else int(g[outcome].idxmin())
    year = float(g.loc[idx, "year"])
    income = float(g.loc[idx, "mpd_gdppc_2011_usd"]) if math.isfinite(float(g.loc[idx, "mpd_gdppc_2011_usd"])) else np.nan
    return year, income


def fit_hac_slope(data: pd.DataFrame, outcome: str) -> tuple[float, float]:
    if len(data) < 5 or data["gdppc_10k"].nunique() < 2:
        return np.nan, np.nan
    fitted = sm.OLS(data[outcome], sm.add_constant(data["gdppc_10k"])).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
    slope = float(fitted.params.get("gdppc_10k", np.nan))
    pval = float(fitted.pvalues.get("gdppc_10k", np.nan))
    return slope, pval


def classify_country_episode(pre_slope: float, pre_p: float, post_slope: float, post_p: float, crossed: bool, n: int, below: int, above: int) -> str:
    if n < SUPPORTED_MIN_OBSERVATIONS or not crossed or below < SUPPORTED_MIN_SIDE_OBSERVATIONS or above < SUPPORTED_MIN_SIDE_OBSERVATIONS:
        return "insufficient_support"
    pre_sig = math.isfinite(pre_slope) and math.isfinite(pre_p) and pre_slope < 0 and pre_p < 0.10
    post_sig = math.isfinite(post_slope) and math.isfinite(post_p) and post_slope > 0 and post_p < 0.10
    if pre_sig and post_sig:
        return "diversification_then_reconcentration"
    if pre_sig and not post_sig:
        return "diversification_only"
    if post_sig and not pre_sig:
        return "reconcentration_only"
    return "flat/unclear"


def build_country_turning_points(primary_panel: pd.DataFrame, pooled_turning: dict[tuple[str, str], dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    metrics = {"Gini": "partner_gini", "Theil": "partner_theil", "HHI": "partner_hhi"}
    for flow in [FLOW_EXPORTS, FLOW_IMPORTS]:
        flow_panel = primary_panel[primary_panel["flow"] == flow].copy()
        for metric_name, outcome in metrics.items():
            pooled_meta = pooled_turning.get((flow, metric_name), {})
            tp = float(pooled_meta.get("turning_point_ppp_2011_usd", np.nan))
            pooled_supported = bool(pooled_meta.get("pooled_model_supported", False))
            pooled_classification = str(pooled_meta.get("pooled_model_classification", "missing"))
            for entity_id, group in flow_panel.groupby("entity_id", sort=True):
                g = group.dropna(subset=[outcome, "mpd_gdppc_2011_usd", "gdppc_10k"]).sort_values("year").copy()
                n = len(g)
                crossed = (
                    pooled_supported
                    and math.isfinite(tp)
                    and float(g["mpd_gdppc_2011_usd"].min()) <= tp <= float(g["mpd_gdppc_2011_usd"].max())
                ) if not g.empty else False
                below = int((g["mpd_gdppc_2011_usd"] < tp).sum()) if crossed else 0
                above = int((g["mpd_gdppc_2011_usd"] >= tp).sum()) if crossed else 0
                pre = g[g["mpd_gdppc_2011_usd"] < tp].copy() if crossed else g.iloc[0:0].copy()
                post = g[g["mpd_gdppc_2011_usd"] >= tp].copy() if crossed else g.iloc[0:0].copy()
                pre_slope, pre_p = fit_hac_slope(pre, outcome)
                post_slope, post_p = fit_hac_slope(post, outcome)
                trough_year, trough_income = rolling_trough_year(g, outcome)
                early_level = float(g.head(min(5, n))[outcome].median()) if n else np.nan
                endpoint_level = float(g.tail(min(5, n))[outcome].median()) if n else np.nan
                trough_level = float(g.loc[g["year"].eq(trough_year), outcome].iloc[0]) if math.isfinite(trough_year) and (g["year"] == trough_year).any() else np.nan
                rows.append(
                    {
                        "entity_id": entity_id,
                        "entity_label": str(g["entity_label"].iloc[0]) if n else entity_id,
                        "flow": flow,
                        "metric_name": metric_name,
                        "years_available": n,
                        "first_year": int(g["year"].min()) if n else np.nan,
                        "last_year": int(g["year"].max()) if n else np.nan,
                        "gdp_min_ppp_2011_usd": float(g["mpd_gdppc_2011_usd"].min()) if n else np.nan,
                        "gdp_max_ppp_2011_usd": float(g["mpd_gdppc_2011_usd"].max()) if n else np.nan,
                        "preferred_pooled_turning_point_ppp_2011_usd": tp,
                        "preferred_pooled_model_classification": pooled_classification,
                        "preferred_pooled_model_supported": pooled_supported,
                        "crosses_preferred_pooled_turning_point": crossed,
                        "observations_below_turning_point": below,
                        "observations_above_turning_point": above,
                        "pre_turning_slope_hac5": pre_slope,
                        "pre_turning_slope_p_value": pre_p,
                        "post_turning_slope_hac5": post_slope,
                        "post_turning_slope_p_value": post_p,
                        "trough_year": trough_year,
                        "trough_income_ppp_2011_usd": trough_income,
                        "concentration_change_early_to_trough": trough_level - early_level if math.isfinite(trough_level) and math.isfinite(early_level) else np.nan,
                        "concentration_change_trough_to_endpoint": endpoint_level - trough_level if math.isfinite(endpoint_level) and math.isfinite(trough_level) else np.nan,
                        "classification": classify_country_episode(pre_slope, pre_p, post_slope, post_p, crossed, n, below, above),
                        "episode_basis": "descriptive_hac_slopes_around_supported_pooled_turning_point",
                    }
                )
    out = pd.DataFrame.from_records(rows)
    if not out.empty:
        for flow in [FLOW_EXPORTS, FLOW_IMPORTS]:
            for metric in ["Gini", "Theil", "HHI"]:
                mask = out["flow"].eq(flow) & out["metric_name"].eq(metric)
                out.loc[mask, "pre_turning_slope_q_value"] = bh_adjust(out.loc[mask, "pre_turning_slope_p_value"].tolist())
                out.loc[mask, "post_turning_slope_q_value"] = bh_adjust(out.loc[mask, "post_turning_slope_p_value"].tolist())
    return out.sort_values(["flow", "metric_name", "entity_id"]).reset_index(drop=True)


def format_number(value: float | None, digits: int = 3) -> str:
    if value is None or not math.isfinite(float(value)):
        return ""
    return f"{float(value):.{digits}f}"


def bold_if(value: float | None, predicate: bool, digits: int = 3) -> str:
    rendered = format_number(value, digits)
    return f"**{rendered}**" if rendered and predicate else rendered


def italic_if(value: float | None, predicate: bool, digits: int = 3) -> str:
    rendered = format_number(value, digits)
    return f"*{rendered}*" if rendered and predicate else rendered


def build_markdown_memo(summary_df: pd.DataFrame, episodes_df: pd.DataFrame) -> str:
    primary = summary_df[
        summary_df["variant"].eq(PRIMARY_VARIANT)
        & summary_df["income_form"].eq(MODEL_INCOME_LEVEL)
        & summary_df["sample_policy"].eq("fixed")
        & summary_df["model_name"].isin([PREFERRED_POOLED_MODEL, PRIMARY_MODEL, "mundlak"])
    ].copy()
    lines = [
        "# Historical Partner Concentration and Cadot-Style Turning Points",
        "",
        f"Generated: {now_utc()}",
        "",
        "## Design scope",
        "",
        "- Canonical sample: CEPII TRADHIST 1827-2014 for FRA, DNK, SWE, NOR, NLD, ESP, PRT, GBR, USA, ARG, URY, USSR, and RUS.",
        "- Trade values are bilateral sums in current British pounds; they are not real trade aggregates.",
        "- GDP per capita comes from Maddison Project Database 2023 (`Real GDP per capita in 2011$`); population is `mid-year (thousands)`.",
        "- This is a Cadot-style partner-concentration analogue. It is descriptive and does not identify a causal effect of income.",
        "",
        "## Measure construction",
        "",
        "- Unit of observation for estimation: entity-year-flow.",
        "- Active-partner baseline uses strictly positive TRADHIST bilateral partner values only; coded zeros are retained for diagnostics and a dedicated zero-inclusive sensitivity.",
        "- Partner Gini is the active-partner Gini; normalized Gini divides by the finite-`n` upper bound `(n-1)/n`.",
        "- Partner Theil is `sum_j s_j log(n s_j)` over active partners; normalized Theil divides by `log(n)`.",
        "- Partner HHI is `sum_j s_j^2`; normalized HHI uses `(HHI - 1/n) / (1 - 1/n)`.",
        "- Baseline `metric_valid` threshold is 20 active partners. Thresholds 5, 10, and 30 are separate sensitivities.",
        "",
        "## Baseline model summary",
        "",
        "| Flow | Metric | Model | Component | N | Entities | TP (PPP 2011$) | Inside p05-p95 | U-test p | U-test q | Class |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | --- | ---: | ---: | --- |",
    ]
    for _, row in primary.sort_values(["flow", "metric_name", "model_name", "curve_component"]).iterrows():
        p = float(row["u_test_p_value"]) if pd.notna(row["u_test_p_value"]) else None
        q = float(row["u_test_q_value"]) if "u_test_q_value" in row and pd.notna(row["u_test_q_value"]) else None
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["flow"]),
                    str(row["metric_name"]),
                    str(row["model_name"]),
                    str(row["curve_component"]),
                    str(int(row["observations"])),
                    str(int(row["entity_count"])),
                    format_number(row["turning_point_ppp_2011_usd"], 0),
                    "yes" if bool(row["turning_point_inside_p05_p95"]) else "no",
                    bold_if(p, p is not None and p < 0.05, 3),
                    italic_if(q, q is not None and q < 0.05, 3),
                    str(row["classification"]),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `pooled_year_fe` rows describe cross-country development patterns.",
            "- `entity_year_fe_logpop` rows are the preferred within-country interpretation because they absorb entity and year fixed effects and retain log population.",
            "- `mundlak` separates within-country and between-country curvature; do not interpret the between component as within-country reconcentration.",
            "- Raw p-values are bolded when `< 0.05`; adjusted q-values are italicized when `< 0.05` so they remain visually distinct.",
            "",
            "## Country episodes",
            "",
            "| Flow | Metric | Entity | Years | Pooled support | Crosses pooled TP | Pre slope p | Post slope p | Pre q | Post q | Class |",
            "| --- | --- | --- | ---: | --- | --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for _, row in episodes_df.sort_values(["flow", "metric_name", "entity_id"]).iterrows():
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["flow"]),
                    str(row["metric_name"]),
                    str(row["entity_id"]),
                    str(int(row["years_available"])),
                    "yes" if bool(row.get("preferred_pooled_model_supported")) else f"no ({row.get('preferred_pooled_model_classification','')})",
                    "yes" if bool(row["crosses_preferred_pooled_turning_point"]) else "no",
                    bold_if(row["pre_turning_slope_p_value"], pd.notna(row["pre_turning_slope_p_value"]) and float(row["pre_turning_slope_p_value"]) < 0.05, 3),
                    bold_if(row["post_turning_slope_p_value"], pd.notna(row["post_turning_slope_p_value"]) and float(row["post_turning_slope_p_value"]) < 0.05, 3),
                    italic_if(row.get("pre_turning_slope_q_value"), pd.notna(row.get("pre_turning_slope_q_value")) and float(row.get("pre_turning_slope_q_value")) < 0.05, 3),
                    italic_if(row.get("post_turning_slope_q_value"), pd.notna(row.get("post_turning_slope_q_value")) and float(row.get("post_turning_slope_q_value")) < 0.05, 3),
                    str(row["classification"]),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Caveats",
            "",
            "- `USSR` and `RUS` are kept separate throughout. No country-year silently combines them.",
            "- Missing dyads are never converted to zero in the main panel. Zero-inclusive variants use only explicit coded zeros.",
            "- Country-episode labels are descriptive HAC slope diagnostics around supported pooled turning points; when the pooled model is unsupported, those rows are suppressed to `insufficient_support`.",
            "- Small-cluster inference is fragile with 13 entities. Conventional clustered p-values are reference-only; the main U-tests use wild-cluster bootstrap p-values in the preferred pooled and preferred within-country baseline rows.",
        ]
    )
    return "\n".join(lines) + "\n"


def plot_entity_metrics(primary_panel: pd.DataFrame) -> list[str]:
    metric_cols = [("partner_gini", "Gini"), ("partner_theil", "Theil"), ("partner_hhi", "HHI")]
    paths: list[str] = []
    for entity_id, group in primary_panel.groupby("entity_id", sort=True):
        fig, axes = plt.subplots(3, 2, figsize=(12, 10), sharex=True)
        for row_idx, (metric_col, title) in enumerate(metric_cols):
            for col_idx, flow in enumerate([FLOW_EXPORTS, FLOW_IMPORTS]):
                ax = axes[row_idx, col_idx]
                subset = group[group["flow"] == flow].sort_values("year")
                ax.plot(subset["year"], subset[metric_col], lw=1.4, color="#1f77b4")
                ax.set_title(f"{entity_id} {flow} {title}")
                ax.axvspan(1914, 1918, color="grey", alpha=0.12)
                ax.axvspan(1939, 1945, color="grey", alpha=0.12)
        fig.tight_layout()
        path = FIGURES_DIR / f"entity_{entity_id.lower()}_partner_metrics.png"
        fig.savefig(path, dpi=180)
        plt.close(fig)
        paths.append(relpath(path))
    return paths


def plot_partner_counts(primary_panel: pd.DataFrame) -> str:
    fig, axes = plt.subplots(7, 2, figsize=(13, 18), sharex=True)
    axes = axes.flatten()
    for ax, (entity_id, group) in zip(axes, primary_panel.groupby("entity_id", sort=True), strict=False):
        for flow, color in [(FLOW_EXPORTS, "#1f77b4"), (FLOW_IMPORTS, "#d62728")]:
            subset = group[group["flow"] == flow].sort_values("year")
            ax.plot(subset["year"], subset["active_partner_count"], lw=1.2, color=color, label=flow)
        ax.set_title(entity_id)
        ax.axvspan(1914, 1918, color="grey", alpha=0.12)
        ax.axvspan(1939, 1945, color="grey", alpha=0.12)
    for ax in axes:
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    path = FIGURES_DIR / "partner_counts_by_entity.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return relpath(path)


def predict_curve(row: pd.Series, grid: np.ndarray, model_name: str) -> np.ndarray:
    b1 = float(row["linear_term_coefficient"])
    b2 = float(row["square_term_coefficient"])
    return b1 * grid + b2 * (grid**2)


def plot_income_curves(summary_df: pd.DataFrame) -> str:
    subset = summary_df[
        summary_df["variant"].eq(PRIMARY_VARIANT)
        & summary_df["income_form"].eq(MODEL_INCOME_LEVEL)
        & summary_df["sample_policy"].eq("fixed")
        & summary_df["model_name"].isin([PREFERRED_POOLED_MODEL, PRIMARY_MODEL])
        & summary_df["curve_component"].isin(["overall", "within"])
    ].copy()
    fig, axes = plt.subplots(3, 2, figsize=(12, 11), sharex=True, sharey=False)
    metric_order = ["Gini", "Theil", "HHI"]
    for r, metric in enumerate(metric_order):
        for c, flow in enumerate([FLOW_EXPORTS, FLOW_IMPORTS]):
            ax = axes[r, c]
            rows = subset[(subset["metric_name"] == metric) & (subset["flow"] == flow)]
            if rows.empty:
                continue
            l = float(rows["support_p05"].min())
            h = float(rows["support_p95"].max())
            grid = np.linspace(l, h, 200)
            for _, row in rows.iterrows():
                curve = predict_curve(row, grid, str(row["model_name"]))
                label = f"{row['model_name']}:{row['curve_component']}"
                ax.plot(grid * 10_000.0, curve, lw=1.5, label=label)
            ax.set_title(f"{flow} {metric}")
            ax.legend(frameon=False, fontsize=8)
    fig.supxlabel("GDP per capita, PPP (2011$)")
    fig.tight_layout()
    path = FIGURES_DIR / "pooled_within_income_curves.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return relpath(path)


def plot_turning_point_support(summary_df: pd.DataFrame) -> str:
    subset = summary_df[
        summary_df["variant"].eq(PRIMARY_VARIANT)
        & summary_df["income_form"].eq(MODEL_INCOME_LEVEL)
        & summary_df["sample_policy"].eq("fixed")
        & summary_df["model_name"].eq(PRIMARY_MODEL)
        & summary_df["curve_component"].eq(PRIMARY_COMPONENT)
    ].copy()
    subset["label"] = subset["flow"].str[:3] + " " + subset["metric_name"]
    colors = subset["classification"].map(
        {
            "supported_u_shape": "#2ca02c",
            "suggestive_only": "#ff7f0e",
            "outside_support": "#d62728",
            "insufficient_support": "#9467bd",
            "no_u_shape": "#7f7f7f",
        }
    ).fillna("#7f7f7f")
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.scatter(subset["turning_point_ppp_2011_usd"], subset["label"], c=colors)
    ax.set_xlabel("Turning point, PPP 2011$")
    ax.set_ylabel("")
    fig.tight_layout()
    path = FIGURES_DIR / "turning_point_support.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return relpath(path)


def plot_leave_one_out(loo_df: pd.DataFrame) -> str:
    if loo_df.empty:
        return ""
    fig, ax = plt.subplots(figsize=(10, 6))
    subset = loo_df.copy()
    subset["label"] = subset["variant"].str.replace("leave_one_out_", "", regex=False) + " | " + subset["flow"].str[:3] + " " + subset["metric_name"]
    ax.scatter(subset["square_term_coefficient"], subset["label"], color="#1f77b4")
    ax.axvline(0.0, color="black", lw=1.0, linestyle="--")
    ax.set_xlabel("Quadratic coefficient after leaving one entity out")
    fig.tight_layout()
    path = FIGURES_DIR / "leave_one_entity_out.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return relpath(path)


def plot_country_classifications(episodes_df: pd.DataFrame) -> str:
    counts = (
        episodes_df.groupby(["flow", "metric_name", "classification"], as_index=False)
        .size()
        .rename(columns={"size": "count"})
    )
    counts["label"] = counts["flow"].str[:3] + " " + counts["metric_name"]
    fig, ax = plt.subplots(figsize=(11, 6))
    xpos = np.arange(len(counts))
    ax.bar(xpos, counts["count"], color="#1f77b4")
    ax.set_xticks(xpos)
    ax.set_xticklabels(counts["label"] + "\n" + counts["classification"], rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Country episodes")
    fig.tight_layout()
    path = FIGURES_DIR / "country_turning_classifications.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return relpath(path)


def save_outputs(
    summary_df: pd.DataFrame,
    term_df: pd.DataFrame,
    attrition_df: pd.DataFrame,
    episodes_df: pd.DataFrame,
    primary_panel: pd.DataFrame,
    figure_paths: list[str],
    variants: dict[str, pd.DataFrame],
) -> dict[str, Any]:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = results_path("cadot_model_summary.csv")
    terms_path = results_path("cadot_model_terms.csv")
    episodes_path = results_path("country_turning_point_episodes.csv")
    attrition_path = results_path("sample_attrition.csv")
    memo_path = results_path("historical_partner_concentration.md")
    manifest_path = results_path("run_manifest.json")

    summary_df.to_csv(summary_path, index=False)
    term_df.to_csv(terms_path, index=False)
    episodes_df.to_csv(episodes_path, index=False)
    attrition_df.to_csv(attrition_path, index=False)
    memo_path.write_text(build_markdown_memo(summary_df, episodes_df), encoding="utf-8")

    manifest = {
        "generated_at_utc": now_utc(),
        "seed": BOOTSTRAP_SEED,
        "wild_cluster_bootstrap_draws": WCB_DRAWS,
        "turning_point_bootstrap_draws": TP_BOOTSTRAP_DRAWS,
        "primary_variant": PRIMARY_VARIANT,
        "primary_model": PRIMARY_MODEL,
        "output_files": {
            "cadot_model_summary_csv": relpath(summary_path),
            "cadot_model_terms_csv": relpath(terms_path),
            "country_turning_point_episodes_csv": relpath(episodes_path),
            "sample_attrition_csv": relpath(attrition_path),
            "historical_partner_concentration_md": relpath(memo_path),
        },
        "figure_files": figure_paths,
        "variant_sizes": {name: int(len(panel)) for name, panel in variants.items()},
        "primary_panel_rows": int(len(primary_panel)),
    }
    write_json(manifest_path, manifest)
    return manifest


def main() -> None:
    args = parse_args()
    partner_flows, flow_panel = read_inputs()
    variants = build_variant_collection(partner_flows, flow_panel)
    summary_df, term_df, attrition_df, _ = run_regression_collection(variants)
    primary_panel = variants[PRIMARY_VARIANT].copy()
    loo_df = run_leave_one_out(primary_panel)
    if not loo_df.empty:
        summary_df = pd.concat([summary_df, loo_df], ignore_index=True)
    pooled_turning = preferred_pooled_turning_points(summary_df)
    episodes_df = build_country_turning_points(primary_panel, pooled_turning)
    figure_paths: list[str] = []
    if not args.skip_plots:
        figure_paths.extend(plot_entity_metrics(primary_panel))
        figure_paths.append(plot_partner_counts(primary_panel))
        figure_paths.append(plot_income_curves(summary_df))
        figure_paths.append(plot_turning_point_support(summary_df))
        loo_path = plot_leave_one_out(loo_df)
        if loo_path:
            figure_paths.append(loo_path)
        figure_paths.append(plot_country_classifications(episodes_df))
    manifest = save_outputs(summary_df, term_df, attrition_df, episodes_df, primary_panel, figure_paths, variants)
    print(f"Wrote historical partner Cadot outputs to {manifest['output_files']['cadot_model_summary_csv']}")


if __name__ == "__main__":
    main()
