#!/usr/bin/env python3
"""Build diagnostics for interpreting the modern Cadot between-country result."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm


ROOT = Path(__file__).resolve().parents[1]
INPUT = (
    ROOT
    / "results"
    / "samples"
    / "cadot_broad_156"
    / "cadot_broad_ppp_hump_regression_tables"
    / "ppp_hump_analysis_panel.csv"
)
OUTPUT_DIR = ROOT / "results" / "prof_p_replication" / "cadot_between_country_diagnostics"

INCOME = "gdp_pc_ppp_constant_2021_intl_usd"
INCOME_10K = "gdp_pc_ppp_constant_2021_intl_usd_10k"
INCOME_10K_SQ = "gdp_pc_ppp_constant_2021_intl_usd_10k_sq"
CONTROLS = ["log_population", "oil_export_share"]
OUTCOMES = {
    "export_product_gini": "Export Product Gini",
    "export_product_theil": "Export Product Theil",
    "export_product_hhi": "Export Product HHI",
    "export_active_product_count": "Export active-product count",
}


def country_means(panel: pd.DataFrame) -> pd.DataFrame:
    numeric = [
        column
        for column in panel.columns
        if column not in {"country", "iso3", "year"}
        and pd.api.types.is_numeric_dtype(panel[column])
    ]
    means = panel.groupby(["country", "iso3"], as_index=False)[numeric].mean()
    means["mean_population"] = np.exp(means["log_population"])
    return means


def variance_decomposition(panel: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, float | str | int]] = []
    for outcome, label in OUTCOMES.items():
        if outcome == "export_active_product_count":
            continue
        sample = panel[["iso3", outcome]].dropna()
        grand_mean = float(sample[outcome].mean())
        grouped = sample.groupby("iso3")[outcome]
        means = grouped.mean()
        counts = grouped.size()
        between_ss = float((((means - grand_mean) ** 2) * counts).sum())
        total_ss = float(((sample[outcome] - grand_mean) ** 2).sum())
        within_ss = float(total_ss - between_ss)
        demeaned = sample.join(means.rename("entity_mean"), on="iso3")
        within_sd = float((demeaned[outcome] - demeaned["entity_mean"]).std(ddof=1))
        rows.append(
            {
                "outcome": outcome,
                "outcome_label": label,
                "observations": int(len(sample)),
                "countries": int(sample["iso3"].nunique()),
                "between_share_total_sum_of_squares": between_ss / total_ss,
                "within_share_total_sum_of_squares": within_ss / total_ss,
                "overall_standard_deviation": float(sample[outcome].std(ddof=1)),
                "within_country_standard_deviation": within_sd,
                "country_mean_standard_deviation": float(means.std(ddof=1)),
            }
        )
    return pd.DataFrame(rows)


def fit_between(sample: pd.DataFrame, outcome: str) -> dict[str, float | int | bool]:
    columns = [outcome, INCOME, INCOME_10K, INCOME_10K_SQ, *CONTROLS]
    frame = sample[columns].replace([np.inf, -np.inf], np.nan).dropna()
    design = sm.add_constant(frame[[INCOME_10K, INCOME_10K_SQ, *CONTROLS]])
    model = sm.OLS(frame[outcome], design).fit(cov_type="HC1")
    linear = float(model.params[INCOME_10K])
    quadratic = float(model.params[INCOME_10K_SQ])
    turning_point = (
        float(-linear / (2.0 * quadratic) * 10_000.0) if quadratic != 0 else np.nan
    )
    p05 = float(frame[INCOME].quantile(0.05))
    p95 = float(frame[INCOME].quantile(0.95))
    return {
        "observations": int(model.nobs),
        "linear_coefficient": linear,
        "linear_p_value": float(model.pvalues[INCOME_10K]),
        "quadratic_coefficient": quadratic,
        "quadratic_p_value": float(model.pvalues[INCOME_10K_SQ]),
        "turning_point_ppp_constant_2021_intl_usd": turning_point,
        "income_p05": p05,
        "income_p95": p95,
        "turning_point_inside_p05_p95": bool(p05 <= turning_point <= p95),
        "r_squared": float(model.rsquared),
    }


def composition_sensitivities(means: pd.DataFrame) -> pd.DataFrame:
    variants = {
        "baseline": pd.Series(True, index=means.index),
        "population_ge_1m": means["mean_population"] >= 1_000_000,
        "oil_export_share_lt_0p5": means["oil_export_share"] < 0.5,
        "population_ge_1m_and_oil_lt_0p5": (means["mean_population"] >= 1_000_000)
        & (means["oil_export_share"] < 0.5),
        "income_below_100k": means[INCOME] < 100_000,
        "income_below_80k": means[INCOME] < 80_000,
    }
    rows: list[dict[str, float | int | bool | str]] = []
    for variant, mask in variants.items():
        for outcome, label in OUTCOMES.items():
            result = fit_between(means.loc[mask], outcome)
            rows.append(
                {
                    "variant": variant,
                    "outcome": outcome,
                    "outcome_label": label,
                    **result,
                }
            )
    return pd.DataFrame(rows)


def leave_one_out(means: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, float | int | bool | str]] = []
    for outcome, label in OUTCOMES.items():
        if outcome == "export_active_product_count":
            continue
        for omitted_iso3 in sorted(means["iso3"].dropna().unique()):
            result = fit_between(means.loc[means["iso3"] != omitted_iso3], outcome)
            rows.append(
                {
                    "outcome": outcome,
                    "outcome_label": label,
                    "omitted_iso3": omitted_iso3,
                    **result,
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    panel = pd.read_csv(INPUT)
    means = country_means(panel)
    variance = variance_decomposition(panel)
    sensitivities = composition_sensitivities(means)
    loo = leave_one_out(means)
    rich_tail = means.loc[means[INCOME] >= 70_000].sort_values(INCOME)

    variance.to_csv(OUTPUT_DIR / "between_within_variance_decomposition.csv", index=False)
    sensitivities.to_csv(OUTPUT_DIR / "between_composition_sensitivities.csv", index=False)
    loo.to_csv(OUTPUT_DIR / "between_leave_one_country_out.csv", index=False)
    rich_tail.to_csv(OUTPUT_DIR / "rich_tail_country_means.csv", index=False)

    manifest = {
        "input": str(INPUT.relative_to(ROOT)),
        "panel_rows": int(len(panel)),
        "analytic_countries": int(means["iso3"].nunique()),
        "outputs": [
            "between_within_variance_decomposition.csv",
            "between_composition_sensitivities.csv",
            "between_leave_one_country_out.csv",
            "rich_tail_country_means.csv",
        ],
        "notes": [
            "All diagnostics are descriptive.",
            "Between-country models use country means and HC1 standard errors.",
            "Composition variants are predeclared mechanical exclusions, not preferred causal specifications.",
        ],
    }
    (OUTPUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote diagnostics to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
