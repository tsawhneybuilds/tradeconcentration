#!/usr/bin/env python3
"""Test whether the modern Cadot rich-tail bend survives within country-size groups.

This is a descriptive between-country exercise. It uses the saved complete-case
``cadot_broad_156`` PPP panel, collapses it to country means, assigns fixed
population terciles, and estimates quadratic and spline income curves for export
Product Gini and fixed-universe Product Theil.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import patsy
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy.stats import norm


ROOT = Path(__file__).resolve().parents[1]
INPUT = (
    ROOT
    / "results"
    / "samples"
    / "cadot_broad_156"
    / "cadot_broad_ppp_hump_regression_tables"
    / "ppp_hump_analysis_panel.csv"
)
BASELINE_SUMMARY = INPUT.parent / "ppp_hump_regression_summary.csv"
OUTPUT_DIR = ROOT / "results" / "prof_p_replication" / "cadot_rich_tail_by_size"

INCOME = "gdp_pc_ppp_constant_2021_intl_usd"
INCOME_10K = "income_10k"
INCOME_10K_SQ = "income_10k_sq"
BETWEEN_INCOME_10K_SQ = "mean_annual_income_10k_sq"
OUTCOMES = {
    "export_product_gini": "Export Product Gini",
    "export_product_theil": "Export Product Theil",
}
SIZE_LABELS = ["small", "medium", "large"]


def validate_unique(frame: pd.DataFrame, keys: list[str], label: str) -> None:
    duplicates = int(frame.duplicated(keys).sum())
    if duplicates:
        raise RuntimeError(f"{label} has {duplicates} duplicate rows on {keys}.")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_country_means(panel: pd.DataFrame) -> pd.DataFrame:
    required = {
        "country",
        "iso3",
        "reporter_code",
        "year",
        INCOME,
        "gdp_pc_ppp_constant_2021_intl_usd_10k_sq",
        "log_population",
        "oil_export_share",
        *OUTCOMES,
    }
    missing = required.difference(panel.columns)
    if missing:
        raise RuntimeError(f"Input panel is missing columns: {sorted(missing)}")
    validate_unique(panel, ["reporter_code", "year"], "PPP analysis panel")

    columns = [
        INCOME,
        "gdp_pc_ppp_constant_2021_intl_usd_10k_sq",
        "log_population",
        "oil_export_share",
        *OUTCOMES,
    ]
    means = panel.groupby(["country", "iso3", "reporter_code"], as_index=False)[columns].mean()
    means[INCOME_10K] = means[INCOME] / 10_000.0
    means[INCOME_10K_SQ] = means[INCOME_10K] ** 2
    means = means.rename(
        columns={
            "gdp_pc_ppp_constant_2021_intl_usd_10k_sq": BETWEEN_INCOME_10K_SQ
        }
    )
    means["mean_population"] = np.exp(means["log_population"])
    means["population_tercile"] = pd.qcut(
        means["log_population"],
        q=3,
        labels=SIZE_LABELS,
    )
    validate_unique(means, ["reporter_code"], "Country-mean panel")
    return means


def linear_combination(
    model: Any,
    weights: dict[str, float],
) -> tuple[float, float, float]:
    names = list(model.params.index)
    vector = np.array([weights.get(name, 0.0) for name in names], dtype=float)
    estimate = float(vector @ model.params.to_numpy())
    variance = float(vector @ model.cov_params().to_numpy() @ vector)
    std_error = math.sqrt(max(variance, 0.0))
    if std_error == 0:
        p_value = float("nan")
    else:
        p_value = float(2.0 * norm.sf(abs(estimate / std_error)))
    return estimate, std_error, p_value


def fit_quadratic(frame: pd.DataFrame, outcome: str, controls: list[str]) -> tuple[Any, dict[str, Any]]:
    columns = [outcome, INCOME, INCOME_10K, INCOME_10K_SQ, *controls]
    sample = frame[columns].replace([np.inf, -np.inf], np.nan).dropna()
    design = sm.add_constant(sample[[INCOME_10K, INCOME_10K_SQ, *controls]], has_constant="add")
    model = sm.OLS(sample[outcome], design).fit(cov_type="HC3")
    linear = float(model.params[INCOME_10K])
    quadratic = float(model.params[INCOME_10K_SQ])
    turning = -linear / (2.0 * quadratic) * 10_000.0 if quadratic > 0 else np.nan
    p90 = float(sample[INCOME].quantile(0.90))
    slope_weights = {
        INCOME_10K: 1.0 / 10_000.0,
        INCOME_10K_SQ: 2.0 * (p90 / 10_000.0) / 10_000.0,
    }
    slope, slope_se, slope_p = linear_combination(model, slope_weights)
    p05 = float(sample[INCOME].quantile(0.05))
    p95 = float(sample[INCOME].quantile(0.95))
    result = {
        "observations": int(model.nobs),
        "linear_coefficient": linear,
        "linear_std_error": float(model.bse[INCOME_10K]),
        "linear_p_value": float(model.pvalues[INCOME_10K]),
        "quadratic_coefficient": quadratic,
        "quadratic_std_error": float(model.bse[INCOME_10K_SQ]),
        "quadratic_p_value": float(model.pvalues[INCOME_10K_SQ]),
        "turning_point_ppp_constant_2021_intl_usd": turning,
        "turning_point_inside_p05_p95": bool(
            math.isfinite(turning) and p05 <= turning <= p95
        ),
        "income_p05": p05,
        "income_p90": p90,
        "income_p95": p95,
        "income_max": float(sample[INCOME].max()),
        "slope_at_income_p90": slope,
        "slope_at_income_p90_std_error": slope_se,
        "slope_at_income_p90_p_value": slope_p,
        "r_squared": float(model.rsquared),
    }
    return model, result


def baseline_adjustment_ladder(means: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for outcome, label in OUTCOMES.items():
        specifications = [
            ("income_only", []),
            ("income_plus_oil", ["oil_export_share"]),
            ("income_plus_linear_log_population_plus_oil", ["log_population", "oil_export_share"]),
        ]
        for specification, controls in specifications:
            _, result = fit_quadratic(means, outcome, controls)
            rows.append(
                {
                    "outcome": outcome,
                    "outcome_label": label,
                    "specification": specification,
                    **result,
                }
            )

        formula = (
            f"{outcome} ~ {INCOME_10K} + {INCOME_10K_SQ} "
            "+ bs(log_population, df=4, degree=3, include_intercept=False) "
            "+ oil_export_share"
        )
        model = smf.ols(formula, data=means).fit(cov_type="HC3")
        sample = means.dropna(subset=[outcome, INCOME, "log_population", "oil_export_share"])
        linear = float(model.params[INCOME_10K])
        quadratic = float(model.params[INCOME_10K_SQ])
        turning = -linear / (2.0 * quadratic) * 10_000.0 if quadratic > 0 else np.nan
        rows.append(
            {
                "outcome": outcome,
                "outcome_label": label,
                "specification": "income_plus_population_spline_plus_oil",
                "observations": int(model.nobs),
                "linear_coefficient": linear,
                "linear_std_error": float(model.bse[INCOME_10K]),
                "linear_p_value": float(model.pvalues[INCOME_10K]),
                "quadratic_coefficient": quadratic,
                "quadratic_std_error": float(model.bse[INCOME_10K_SQ]),
                "quadratic_p_value": float(model.pvalues[INCOME_10K_SQ]),
                "turning_point_ppp_constant_2021_intl_usd": turning,
                "turning_point_inside_p05_p95": bool(
                    math.isfinite(turning)
                    and sample[INCOME].quantile(0.05) <= turning <= sample[INCOME].quantile(0.95)
                ),
                "income_p05": float(sample[INCOME].quantile(0.05)),
                "income_p90": float(sample[INCOME].quantile(0.90)),
                "income_p95": float(sample[INCOME].quantile(0.95)),
                "income_max": float(sample[INCOME].max()),
                "slope_at_income_p90": np.nan,
                "slope_at_income_p90_std_error": np.nan,
                "slope_at_income_p90_p_value": np.nan,
                "r_squared": float(model.rsquared),
            }
        )
    return pd.DataFrame(rows)


def size_support(means: pd.DataFrame, baseline_summary: pd.DataFrame) -> pd.DataFrame:
    turning = (
        baseline_summary.loc[
            (baseline_summary["estimator"] == "between_country")
            & (baseline_summary["income_form"] == "level_ppp")
            & baseline_summary["outcome_slug"].isin(OUTCOMES),
            ["outcome_slug", "turning_point_ppp_constant_2021_intl_usd"],
        ]
        .drop_duplicates("outcome_slug")
        .set_index("outcome_slug")["turning_point_ppp_constant_2021_intl_usd"]
        .to_dict()
    )
    rows: list[dict[str, Any]] = []
    for size, group in means.groupby("population_tercile", observed=True):
        common = {
            "population_tercile": str(size),
            "countries": int(len(group)),
            "population_min": float(group["mean_population"].min()),
            "population_median": float(group["mean_population"].median()),
            "population_max": float(group["mean_population"].max()),
            "income_min": float(group[INCOME].min()),
            "income_p75": float(group[INCOME].quantile(0.75)),
            "income_p90": float(group[INCOME].quantile(0.90)),
            "income_max": float(group[INCOME].max()),
            "countries_income_ge_50000": int(group[INCOME].ge(50_000).sum()),
            "countries_income_ge_70000": int(group[INCOME].ge(70_000).sum()),
        }
        for outcome in OUTCOMES:
            threshold = float(turning[outcome])
            rows.append(
                {
                    **common,
                    "outcome": outcome,
                    "baseline_between_turning_point": threshold,
                    "countries_at_or_above_baseline_turning_point": int(
                        group[INCOME].ge(threshold).sum()
                    ),
                }
            )
    return pd.DataFrame(rows)


def population_quintile_support(means: pd.DataFrame) -> pd.DataFrame:
    work = means.copy()
    work["population_quintile"] = pd.qcut(
        work["log_population"],
        q=5,
        labels=["Q1 smallest", "Q2", "Q3", "Q4", "Q5 largest"],
    )
    return (
        work.groupby("population_quintile", observed=True)
        .agg(
            countries=("iso3", "size"),
            population_min=("mean_population", "min"),
            population_max=("mean_population", "max"),
            income_max=(INCOME, "max"),
            countries_income_ge_70000=(INCOME, lambda values: int(values.ge(70_000).sum())),
        )
        .reset_index()
    )


def size_quadratics(means: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    interaction_rows: list[dict[str, Any]] = []
    for outcome, label in OUTCOMES.items():
        for size, group in means.groupby("population_tercile", observed=True):
            _, result = fit_quadratic(group, outcome, ["oil_export_share"])
            rows.append(
                {
                    "outcome": outcome,
                    "outcome_label": label,
                    "population_tercile": str(size),
                    **result,
                }
            )

        formula = (
            f"{outcome} ~ {INCOME_10K} * C(population_tercile) "
            f"+ {INCOME_10K_SQ} * C(population_tercile) + oil_export_share"
        )
        model = smf.ols(formula, data=means).fit(cov_type="HC3")
        interaction_terms = [
            name
            for name in model.params.index
            if (INCOME_10K in name or INCOME_10K_SQ in name)
            and "C(population_tercile)" in name
        ]
        restriction = np.zeros((len(interaction_terms), len(model.params)))
        for row_index, term in enumerate(interaction_terms):
            restriction[row_index, list(model.params.index).index(term)] = 1.0
        test = model.wald_test(restriction, scalar=True)
        interaction_rows.append(
            {
                "outcome": outcome,
                "outcome_label": label,
                "test": "joint_income_curve_equality_across_population_terciles",
                "restrictions": len(interaction_terms),
                "statistic": float(np.asarray(test.statistic).squeeze()),
                "p_value": float(np.asarray(test.pvalue).squeeze()),
                "observations": int(model.nobs),
                "r_squared": float(model.rsquared),
            }
        )
    return pd.DataFrame(rows), pd.DataFrame(interaction_rows)


def baseline_between_transform_sensitivity(means: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for outcome, label in OUTCOMES.items():
        for size, group in means.groupby("population_tercile", observed=True):
            sample = group[
                [
                    outcome,
                    INCOME,
                    INCOME_10K,
                    BETWEEN_INCOME_10K_SQ,
                    "oil_export_share",
                ]
            ].dropna()
            design = sm.add_constant(
                sample[[INCOME_10K, BETWEEN_INCOME_10K_SQ, "oil_export_share"]],
                has_constant="add",
            )
            model = sm.OLS(sample[outcome], design).fit(cov_type="HC3")
            linear = float(model.params[INCOME_10K])
            quadratic = float(model.params[BETWEEN_INCOME_10K_SQ])
            turning = (
                -linear / (2.0 * quadratic) * 10_000.0
                if quadratic > 0
                else np.nan
            )
            rows.append(
                {
                    "outcome": outcome,
                    "outcome_label": label,
                    "population_tercile": str(size),
                    "observations": int(model.nobs),
                    "linear_coefficient": linear,
                    "quadratic_coefficient": quadratic,
                    "quadratic_std_error": float(model.bse[BETWEEN_INCOME_10K_SQ]),
                    "quadratic_p_value": float(model.pvalues[BETWEEN_INCOME_10K_SQ]),
                    "turning_point_ppp_constant_2021_intl_usd": turning,
                    "note": "Uses mean annual income-squared, matching the existing between-country runner.",
                }
            )
    return pd.DataFrame(rows)


def complete_period_sensitivity(panel: pd.DataFrame) -> pd.DataFrame:
    expected_years = int(panel["year"].max() - panel["year"].min() + 1)
    year_counts = panel.groupby("reporter_code")["year"].nunique()
    complete_codes = year_counts.loc[year_counts.eq(expected_years)].index
    complete_means = build_country_means(
        panel.loc[panel["reporter_code"].isin(complete_codes)].copy()
    )
    rows: list[dict[str, Any]] = []
    for outcome, label in OUTCOMES.items():
        for size, group in complete_means.groupby("population_tercile", observed=True):
            _, result = fit_quadratic(group, outcome, ["oil_export_share"])
            rows.append(
                {
                    "outcome": outcome,
                    "outcome_label": label,
                    "population_tercile": str(size),
                    "complete_period_countries": int(len(group)),
                    "countries_income_ge_70000": int(group[INCOME].ge(70_000).sum()),
                    **result,
                }
            )
    return pd.DataFrame(rows)


def rich_tail_leave_one_out(
    means: pd.DataFrame,
    baseline_summary: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    thresholds = (
        baseline_summary.loc[
            (baseline_summary["estimator"] == "between_country")
            & (baseline_summary["income_form"] == "level_ppp")
            & baseline_summary["outcome_slug"].isin(OUTCOMES),
            ["outcome_slug", "turning_point_ppp_constant_2021_intl_usd"],
        ]
        .drop_duplicates("outcome_slug")
        .set_index("outcome_slug")["turning_point_ppp_constant_2021_intl_usd"]
        .to_dict()
    )
    rows: list[dict[str, Any]] = []
    for outcome, label in OUTCOMES.items():
        threshold = float(thresholds[outcome])
        for size, group in means.groupby("population_tercile", observed=True):
            rich_countries = group.loc[group[INCOME].ge(threshold), ["iso3", "country"]]
            for omitted in rich_countries.itertuples(index=False):
                _, result = fit_quadratic(
                    group.loc[group["iso3"].ne(omitted.iso3)],
                    outcome,
                    ["oil_export_share"],
                )
                rows.append(
                    {
                        "outcome": outcome,
                        "outcome_label": label,
                        "population_tercile": str(size),
                        "baseline_turning_point": threshold,
                        "omitted_iso3": omitted.iso3,
                        "omitted_country": omitted.country,
                        **result,
                    }
                )
    details = pd.DataFrame(rows)
    summary = (
        details.groupby(["outcome", "outcome_label", "population_tercile"], as_index=False)
        .agg(
            rich_countries_tested=("omitted_iso3", "size"),
            quadratic_coefficient_min=("quadratic_coefficient", "min"),
            quadratic_coefficient_max=("quadratic_coefficient", "max"),
            share_positive_quadratic=("quadratic_coefficient", lambda values: float(values.gt(0).mean())),
            share_quadratic_p_lt_0p05=("quadratic_p_value", lambda values: float(values.lt(0.05).mean())),
            turning_point_min=("turning_point_ppp_constant_2021_intl_usd", "min"),
            turning_point_max=("turning_point_ppp_constant_2021_intl_usd", "max"),
        )
    )
    return details, summary


def full_leave_one_country_out(means: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    for outcome, label in OUTCOMES.items():
        for size, group in means.groupby("population_tercile", observed=True):
            for omitted in group[["iso3", "country"]].itertuples(index=False):
                _, result = fit_quadratic(
                    group.loc[group["iso3"].ne(omitted.iso3)],
                    outcome,
                    ["oil_export_share"],
                )
                rows.append(
                    {
                        "outcome": outcome,
                        "outcome_label": label,
                        "population_tercile": str(size),
                        "omitted_iso3": omitted.iso3,
                        "omitted_country": omitted.country,
                        **result,
                    }
                )
    details = pd.DataFrame(rows)
    summary = (
        details.groupby(["outcome", "outcome_label", "population_tercile"], as_index=False)
        .agg(
            countries_tested=("omitted_iso3", "size"),
            quadratic_coefficient_min=("quadratic_coefficient", "min"),
            quadratic_coefficient_max=("quadratic_coefficient", "max"),
            share_positive_quadratic=("quadratic_coefficient", lambda values: float(values.gt(0).mean())),
            share_quadratic_p_lt_0p05=("quadratic_p_value", lambda values: float(values.lt(0.05).mean())),
            quadratic_p_value_max=("quadratic_p_value", "max"),
            turning_point_min=("turning_point_ppp_constant_2021_intl_usd", "min"),
            turning_point_max=("turning_point_ppp_constant_2021_intl_usd", "max"),
        )
    )
    return details, summary


def continuous_size_interaction(means: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    centered = means.copy()
    centered["log_population_centered"] = (
        centered["log_population"] - centered["log_population"].median()
    )
    population_points = {
        "population_p25": float(centered["log_population"].quantile(0.25)),
        "population_p50": float(centered["log_population"].quantile(0.50)),
        "population_p75": float(centered["log_population"].quantile(0.75)),
    }
    for outcome, label in OUTCOMES.items():
        formula = (
            f"{outcome} ~ {INCOME_10K} + {INCOME_10K_SQ} "
            "+ bs(log_population, df=4, degree=3, include_intercept=False) "
            f"+ {INCOME_10K}:log_population_centered "
            f"+ {INCOME_10K_SQ}:log_population_centered + oil_export_share"
        )
        model = smf.ols(formula, data=centered).fit(cov_type="HC3")
        for point_label, log_population in population_points.items():
            centered_value = log_population - float(centered["log_population"].median())
            linear = float(
                model.params[INCOME_10K]
                + centered_value * model.params[f"{INCOME_10K}:log_population_centered"]
            )
            quadratic = float(
                model.params[INCOME_10K_SQ]
                + centered_value * model.params[f"{INCOME_10K_SQ}:log_population_centered"]
            )
            turning = -linear / (2.0 * quadratic) * 10_000.0 if quadratic > 0 else np.nan
            rows.append(
                {
                    "outcome": outcome,
                    "outcome_label": label,
                    "population_point": point_label,
                    "population": math.exp(log_population),
                    "implied_linear_coefficient": linear,
                    "implied_quadratic_coefficient": quadratic,
                    "implied_turning_point_ppp_constant_2021_intl_usd": turning,
                    "observations": int(model.nobs),
                    "r_squared": float(model.rsquared),
                }
            )
    return pd.DataFrame(rows)


def spline_curves(means: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    curve_rows: list[pd.DataFrame] = []
    summary_rows: list[dict[str, Any]] = []
    for outcome, label in OUTCOMES.items():
        for size, group in means.groupby("population_tercile", observed=True):
            sample = group[[outcome, INCOME_10K, "oil_export_share", "iso3", "country"]].dropna()
            design = patsy.dmatrix(
                f"bs({INCOME_10K}, df=4, degree=3, include_intercept=False) + oil_export_share",
                sample,
                return_type="dataframe",
            )
            model = sm.OLS(sample[outcome], design).fit(cov_type="HC3")
            income_grid = np.linspace(
                float(sample[INCOME_10K].quantile(0.05)),
                float(sample[INCOME_10K].quantile(0.95)),
                160,
            )
            prediction_frame = pd.DataFrame(
                {
                    INCOME_10K: income_grid,
                    "oil_export_share": float(sample["oil_export_share"].median()),
                }
            )
            prediction_design = patsy.build_design_matrices(
                [design.design_info],
                prediction_frame,
                return_type="dataframe",
            )[0]
            prediction = model.get_prediction(prediction_design).summary_frame(alpha=0.05)
            curve = pd.DataFrame(
                {
                    "outcome": outcome,
                    "outcome_label": label,
                    "population_tercile": str(size),
                    INCOME: income_grid * 10_000.0,
                    "predicted": prediction["mean"].to_numpy(),
                    "ci_low": prediction["mean_ci_lower"].to_numpy(),
                    "ci_high": prediction["mean_ci_upper"].to_numpy(),
                }
            )
            trough_index = int(curve["predicted"].idxmin() - curve.index.min())
            trough = curve.iloc[trough_index]
            endpoint = curve.iloc[-1]
            vector = (
                prediction_design.iloc[-1].to_numpy()
                - prediction_design.iloc[trough_index].to_numpy()
            )
            delta = float(vector @ model.params.to_numpy())
            delta_variance = float(vector @ model.cov_params().to_numpy() @ vector)
            delta_se = math.sqrt(max(delta_variance, 0.0))
            delta_p = (
                float(2.0 * norm.sf(abs(delta / delta_se)))
                if delta_se > 0
                else np.nan
            )
            summary_rows.append(
                {
                    "outcome": outcome,
                    "outcome_label": label,
                    "population_tercile": str(size),
                    "countries": int(len(sample)),
                    "income_p05": float(curve[INCOME].iloc[0]),
                    "income_p95": float(curve[INCOME].iloc[-1]),
                    "spline_trough_income": float(trough[INCOME]),
                    "spline_trough_prediction": float(trough["predicted"]),
                    "spline_p95_prediction": float(endpoint["predicted"]),
                    "p95_minus_trough": delta,
                    "p95_minus_trough_std_error": delta_se,
                    "p95_minus_trough_p_value": delta_p,
                    "trough_strictly_below_p95": bool(trough_index < len(curve) - 1),
                }
            )
            curve_rows.append(curve)
    return pd.concat(curve_rows, ignore_index=True), pd.DataFrame(summary_rows)


def plot_curves(means: pd.DataFrame, curves: pd.DataFrame, output: Path) -> None:
    colors = {"small": "#35618d", "medium": "#ba5a31", "large": "#3d7f5f"}
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.4), sharex=False)
    for axis, (outcome, label) in zip(axes, OUTCOMES.items()):
        for size in SIZE_LABELS:
            group = means.loc[means["population_tercile"].astype(str).eq(size)]
            curve = curves.loc[
                curves["outcome"].eq(outcome)
                & curves["population_tercile"].eq(size)
            ]
            axis.scatter(
                group[INCOME],
                group[outcome],
                s=21,
                alpha=0.42,
                color=colors[size],
            )
            axis.plot(curve[INCOME], curve["predicted"], lw=2.2, color=colors[size], label=size.title())
        axis.axvline(70_000, color="#444444", ls="--", lw=1.0, alpha=0.7)
        axis.set_title(label)
        axis.set_xlabel("Mean GDP per capita, PPP (constant 2021 international $)")
        axis.grid(axis="y", alpha=0.18)
    axes[0].set_ylabel("Country-mean concentration")
    axes[1].legend(title="Population tercile", frameon=False)
    fig.suptitle("Income–concentration curves within fixed country-size terciles", y=1.01)
    fig.tight_layout()
    fig.savefig(output, dpi=220, bbox_inches="tight")
    plt.close(fig)


def write_report(
    path: Path,
    support: pd.DataFrame,
    ladder: pd.DataFrame,
    quadratics: pd.DataFrame,
    between_transform: pd.DataFrame,
    complete_period: pd.DataFrame,
    interactions: pd.DataFrame,
    splines: pd.DataFrame,
    leave_one_out_summary: pd.DataFrame,
    full_leave_one_out_summary: pd.DataFrame,
) -> None:
    lines = [
        "# Does the Cadot Rich-Tail Bend Survive Among Similarly Sized Countries?",
        "",
        "## Design",
        "",
        "- Descriptive between-country test using the saved `cadot_broad_156` complete-case panel.",
        "- Unit of observation: country mean over available 2000–2024 country-years.",
        "- Sample: 135 countries, split into fixed population terciles of 45 countries each.",
        "- Outcomes: export active-product Gini and export fixed-universe Product Theil. Product-dependent source artifacts exclude HS6 `999999` before aggregation.",
        "- Main specifications: separate quadratic and cubic-spline income curves by population tercile, controlling for mean oil export share.",
        "",
        "Within each population tercile, the quadratic model is `concentration_i = beta0 + beta1 income_i + beta2 income_i^2 + theta oil_share_i + error_i`, where `i` is a country and income is mean constant-PPP GDP per capita over the observed period. A positive `beta2` with an interior minimum is evidence of a U-shaped bend. Higher Gini or Theil means greater export-product concentration.",
        "",
        "## Support comes first",
        "",
        "The original full-sample between-country turning points are roughly $72,600 for Gini and $73,200 for Theil. Countries at or above those thresholds are distributed as follows:",
        "",
        "| Population tercile | Countries | Mean-population range | Countries with income >= $70k | At/above Gini turning point | At/above Theil turning point |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for size in SIZE_LABELS:
        rows = support.loc[support["population_tercile"].eq(size)]
        first = rows.iloc[0]
        gini = rows.loc[rows["outcome"].eq("export_product_gini")].iloc[0]
        theil = rows.loc[rows["outcome"].eq("export_product_theil")].iloc[0]
        lines.append(
            f"| {size.title()} | {int(first['countries'])} "
            f"| {first['population_min']:,.0f}–{first['population_max']:,.0f} "
            f"| {int(first['countries_income_ge_70000'])} "
            f"| {int(gini['countries_at_or_above_baseline_turning_point'])} "
            f"| {int(theil['countries_at_or_above_baseline_turning_point'])} |"
        )

    lines.extend(
        [
            "",
            "There is therefore no common-support test of the approximately $73,000 rich tail for large countries: the large-country tercile contains no country with mean income above $70,000. The rich tail is composed entirely of small and medium-sized countries.",
            "",
            "## Flexible population adjustment",
            "",
            "Adding population flexibly does not eliminate the full-sample between-country quadratic:",
            "",
            "| Outcome | Population control | Quadratic coefficient | Quadratic p-value | Turning point |",
            "| --- | --- | ---: | ---: | ---: |",
        ]
    )
    for outcome in OUTCOMES:
        for specification in [
            "income_plus_linear_log_population_plus_oil",
            "income_plus_population_spline_plus_oil",
        ]:
            row = ladder.loc[
                ladder["outcome"].eq(outcome)
                & ladder["specification"].eq(specification)
            ].iloc[0]
            population_label = (
                "Linear log population"
                if "linear" in specification
                else "Population spline"
            )
            lines.append(
                f"| {OUTCOMES[outcome]} | {population_label} "
                f"| **{row['quadratic_coefficient']:.4f}** "
                f"| **{row['quadratic_p_value']:.4f}** "
                f"| ${row['turning_point_ppp_constant_2021_intl_usd']:,.0f} |"
            )

    lines.extend(
        [
            "",
            "Population therefore shifts levels and the estimated minimum, but a flexible additive population control alone does not erase the aggregate curve. The harder test is whether the curve repeats within population groups.",
            "",
            "## Within-size estimates",
            "",
            "| Outcome | Size tercile | Quadratic p-value | Quadratic turning point | Turning point in group p05–p95 | Spline p95 minus trough | Spline delta p-value |",
            "| --- | --- | ---: | ---: | --- | ---: | ---: |",
        ]
    )
    for outcome in OUTCOMES:
        for size in SIZE_LABELS:
            q = quadratics.loc[
                quadratics["outcome"].eq(outcome)
                & quadratics["population_tercile"].eq(size)
            ].iloc[0]
            s = splines.loc[
                splines["outcome"].eq(outcome)
                & splines["population_tercile"].eq(size)
            ].iloc[0]
            turning = (
                f"${q['turning_point_ppp_constant_2021_intl_usd']:,.0f}"
                if math.isfinite(q["turning_point_ppp_constant_2021_intl_usd"])
                else "none"
            )
            spline_p = (
                (
                    f"**{s['p95_minus_trough_p_value']:.3f}**"
                    if s["p95_minus_trough_p_value"] < 0.05
                    else f"{s['p95_minus_trough_p_value']:.3f}"
                )
                if math.isfinite(s["p95_minus_trough_p_value"])
                else "not applicable"
            )
            quadratic_p = (
                f"**{q['quadratic_p_value']:.3f}**"
                if q["quadratic_p_value"] < 0.05
                else f"{q['quadratic_p_value']:.3f}"
            )
            lines.append(
                f"| {OUTCOMES[outcome]} | {size.title()} "
                f"| {quadratic_p} | {turning} "
                f"| {'yes' if q['turning_point_inside_p05_p95'] else 'no'} "
                f"| {s['p95_minus_trough']:.4f} | {spline_p} |"
            )

    gini_interaction = interactions.loc[
        interactions["outcome"].eq("export_product_gini"), "p_value"
    ].iloc[0]
    theil_interaction = interactions.loc[
        interactions["outcome"].eq("export_product_theil"), "p_value"
    ].iloc[0]
    medium_gini_loo = leave_one_out_summary.loc[
        leave_one_out_summary["outcome"].eq("export_product_gini")
        & leave_one_out_summary["population_tercile"].eq("medium")
    ].iloc[0]
    medium_gini_between = between_transform.loc[
        between_transform["outcome"].eq("export_product_gini")
        & between_transform["population_tercile"].eq("medium")
    ].iloc[0]
    medium_gini_complete = complete_period.loc[
        complete_period["outcome"].eq("export_product_gini")
        & complete_period["population_tercile"].eq("medium")
    ].iloc[0]
    large_theil_complete = complete_period.loc[
        complete_period["outcome"].eq("export_product_theil")
        & complete_period["population_tercile"].eq("large")
    ].iloc[0]
    medium_gini_full_loo = full_leave_one_out_summary.loc[
        full_leave_one_out_summary["outcome"].eq("export_product_gini")
        & full_leave_one_out_summary["population_tercile"].eq("medium")
    ].iloc[0]
    lines.extend(
        [
            "",
            "The medium-size Gini quadratic is not created by one of its four rich countries. Omitting Ireland, Singapore, Switzerland, or the United Arab Emirates one at a time leaves the quadratic positive and statistically significant in every run, with the estimated minimum between "
            f"${medium_gini_loo['turning_point_min']:,.0f} and ${medium_gini_loo['turning_point_max']:,.0f}.",
            "",
            "The stronger all-country influence check reaches the same result: omitting each of the 45 medium-size countries one at a time leaves the Gini quadratic positive and significant in 100% of runs; the largest raw p-value is "
            f"**{medium_gini_full_loo['quadratic_p_value_max']:.3f}**.",
            "",
            "The exact transformation used by the existing between-country runner—averaging annual income-squared rather than squaring mean income—gives the same medium-size Gini conclusion: "
            f"quadratic coefficient **{medium_gini_between['quadratic_coefficient']:.4f}**, raw p-value **{medium_gini_between['quadratic_p_value']:.3f}**, and minimum ${medium_gini_between['turning_point_ppp_constant_2021_intl_usd']:,.0f}.",
            "",
            "Restricting the analysis to the 92 countries observed in every year from 2000 through 2024 also preserves the medium-size Gini bend: "
            f"quadratic coefficient **{medium_gini_complete['quadratic_coefficient']:.4f}**, raw p-value **{medium_gini_complete['quadratic_p_value']:.3f}**, and minimum ${medium_gini_complete['turning_point_ppp_constant_2021_intl_usd']:,.0f}. In contrast, the large-group Theil quadratic is no longer significant in this complete-period sample (raw p-value {large_theil_complete['quadratic_p_value']:.3f}).",
            "",
            "## Answer",
            "",
            "The evidence does **not** support a clean claim that the rich-tail bend remains among countries of comparable size.",
            "",
            "- For export Gini, the quadratic bend is present in the medium-size tercile but not in the small or large terciles.",
            "- For export Theil, positive curvature appears in the medium and large terciles, but the large-country turning point occurs below the full-sample rich-tail threshold and cannot validate an approximately $73,000 upturn.",
            "- Flexible splines are imprecise because each size tercile has only 45 countries and the actual rich tail contains only five small and four medium countries.",
            f"- The income curves differ across population terciles jointly for Gini at p={gini_interaction:.3f} and for Theil at p={theil_interaction:.3f}.",
            "",
            "The defensible conclusion is: **flexible population adjustment does not erase the aggregate bend, but the bend is not shown to be a general within-size pattern.** A robust medium-size-country Gini bend remains. The available sample lacks large rich countries, so it cannot establish whether reconcentration extends to rich economies of comparable large scale.",
            "",
            "## Interpretation limits",
            "",
            "- Population terciles are coarse; they improve comparability but do not create exact size matches.",
            "- The exercise is descriptive and relies on persistent cross-country differences.",
            "- The small number of countries above the original turning point makes rich-tail inference leverage-sensitive.",
            "- Spline p-values condition on the estimated trough location and should be treated as descriptive approximations, not pre-specified hypothesis tests.",
            "- Failure to find a large-country rich tail is a support failure, not evidence that large rich countries would have no bend.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    panel = pd.read_csv(INPUT)
    baseline_summary = pd.read_csv(BASELINE_SUMMARY)
    means = build_country_means(panel)

    support = size_support(means, baseline_summary)
    quintile_support = population_quintile_support(means)
    ladder = baseline_adjustment_ladder(means)
    quadratics, interaction_tests = size_quadratics(means)
    between_transform = baseline_between_transform_sensitivity(means)
    complete_period = complete_period_sensitivity(panel)
    leave_one_out, leave_one_out_summary = rich_tail_leave_one_out(
        means,
        baseline_summary,
    )
    full_leave_one_out, full_leave_one_out_summary = full_leave_one_country_out(means)
    continuous_interactions = continuous_size_interaction(means)
    curves, spline_summary = spline_curves(means)

    means.to_csv(OUTPUT_DIR / "country_mean_analysis_panel.csv", index=False)
    support.to_csv(OUTPUT_DIR / "population_tercile_support.csv", index=False)
    quintile_support.to_csv(OUTPUT_DIR / "population_quintile_support.csv", index=False)
    ladder.to_csv(OUTPUT_DIR / "population_adjustment_ladder.csv", index=False)
    quadratics.to_csv(OUTPUT_DIR / "population_tercile_quadratic_models.csv", index=False)
    between_transform.to_csv(
        OUTPUT_DIR / "population_tercile_between_transform_sensitivity.csv",
        index=False,
    )
    complete_period.to_csv(
        OUTPUT_DIR / "complete_period_population_tercile_sensitivity.csv",
        index=False,
    )
    interaction_tests.to_csv(OUTPUT_DIR / "population_tercile_curve_equality_tests.csv", index=False)
    leave_one_out.to_csv(OUTPUT_DIR / "rich_tail_leave_one_country_out.csv", index=False)
    leave_one_out_summary.to_csv(
        OUTPUT_DIR / "rich_tail_leave_one_country_out_summary.csv",
        index=False,
    )
    full_leave_one_out.to_csv(
        OUTPUT_DIR / "full_leave_one_country_out.csv",
        index=False,
    )
    full_leave_one_out_summary.to_csv(
        OUTPUT_DIR / "full_leave_one_country_out_summary.csv",
        index=False,
    )
    continuous_interactions.to_csv(OUTPUT_DIR / "continuous_population_interaction_models.csv", index=False)
    curves.to_csv(OUTPUT_DIR / "population_tercile_spline_curves.csv", index=False)
    spline_summary.to_csv(OUTPUT_DIR / "population_tercile_spline_summary.csv", index=False)
    plot_curves(means, curves, OUTPUT_DIR / "population_tercile_income_curves.png")
    write_report(
        OUTPUT_DIR / "rich_tail_by_size_report.md",
        support,
        ladder,
        quadratics,
        between_transform,
        complete_period,
        interaction_tests,
        spline_summary,
        leave_one_out_summary,
        full_leave_one_out_summary,
    )

    validations = pd.DataFrame(
        [
            {
                "check": "input_reporter_year_unique",
                "passed": not panel.duplicated(["reporter_code", "year"]).any(),
                "value": int(panel.duplicated(["reporter_code", "year"]).sum()),
            },
            {
                "check": "analytic_country_count_135",
                "passed": means["reporter_code"].nunique() == 135,
                "value": int(means["reporter_code"].nunique()),
            },
            {
                "check": "terciles_have_45_countries_each",
                "passed": means.groupby("population_tercile", observed=True).size().eq(45).all(),
                "value": json.dumps(
                    means.groupby("population_tercile", observed=True).size().astype(int).to_dict()
                ),
            },
            {
                "check": "large_tercile_has_no_country_above_70000",
                "passed": int(
                    means.loc[
                        means["population_tercile"].astype(str).eq("large"),
                        INCOME,
                    ].ge(70_000).sum()
                )
                == 0,
                "value": int(
                    means.loc[
                        means["population_tercile"].astype(str).eq("large"),
                        INCOME,
                    ].ge(70_000).sum()
                ),
            },
            {
                "check": "all_model_outputs_finite_observation_counts",
                "passed": bool(
                    ladder["observations"].notna().all()
                    and quadratics["observations"].notna().all()
                    and spline_summary["countries"].notna().all()
                ),
                "value": int(len(ladder) + len(quadratics) + len(spline_summary)),
            },
        ]
    )
    validations.to_csv(OUTPUT_DIR / "validation_checks.csv", index=False)
    if not validations["passed"].all():
        raise RuntimeError("One or more rich-tail-by-size validation checks failed.")

    manifest = {
        "input": str(INPUT.relative_to(ROOT)),
        "input_sha256": sha256(INPUT),
        "baseline_summary": str(BASELINE_SUMMARY.relative_to(ROOT)),
        "baseline_summary_sha256": sha256(BASELINE_SUMMARY),
        "panel_rows": int(len(panel)),
        "analytic_countries": int(means["reporter_code"].nunique()),
        "period": [int(panel["year"].min()), int(panel["year"].max())],
        "unit_of_observation": "country mean over available 2000-2024 country-years",
        "size_definition": "fixed terciles of country-mean log population; 45 countries per tercile",
        "outcomes": OUTCOMES,
        "product_rule": "Product-dependent source artifacts exclude HS6 999999 before aggregation.",
        "inference": "HC3 heteroskedasticity-robust covariance on country-mean regressions.",
        "causal_interpretation": False,
    }
    (OUTPUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote rich-tail-by-size diagnostics to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
