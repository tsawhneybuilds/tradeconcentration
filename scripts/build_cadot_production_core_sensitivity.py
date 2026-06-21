#!/usr/bin/env python3
"""Test the Cadot curve after excluding non-production-oriented country types."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
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
OUTPUT_DIR = (
    ROOT / "results" / "prof_p_replication" / "cadot_production_core_sensitivity"
)

INCOME = "gdp_pc_ppp_constant_2021_intl_usd"
INCOME_10K = "gdp_pc_ppp_constant_2021_intl_usd_10k"
INCOME_10K_SQ = "gdp_pc_ppp_constant_2021_intl_usd_10k_sq"
OUTCOMES = {
    "export_product_gini": ("Export Product Gini", "concentration_u"),
    "export_product_theil": ("Export Product Theil", "concentration_u"),
    "export_product_hhi": ("Export Product HHI", "concentration_u"),
    "export_active_product_count": ("Export active-product count", "count_inverted_u"),
}

# Broad, deliberately conservative union of prominent conduit, offshore-finance,
# tax-booking, and re-export centres represented in the analytic panel.
HUB_ISO3 = {
    "ARE",
    "BHR",
    "BHS",
    "BMU",
    "BRB",
    "CHE",
    "CYP",
    "HKG",
    "IRL",
    "LUX",
    "MAC",
    "MLT",
    "SGP",
}

# Jurisdictions from the IMF/FSF 2000 offshore-centre coverage that are present
# or potentially present in the project's country universe.
IMF_2000_OFC_ISO3 = {
    "ABW",
    "AND",
    "ATG",
    "BHR",
    "BHS",
    "BLZ",
    "BMU",
    "BRB",
    "CHE",
    "CRI",
    "CYP",
    "DMA",
    "GRD",
    "HKG",
    "IRL",
    "LBN",
    "LCA",
    "LUX",
    "MAC",
    "MLT",
    "SGP",
    "SYC",
    "VCT",
    "WSM",
}


def country_classification(panel: pd.DataFrame) -> pd.DataFrame:
    country = (
        panel.groupby(["country", "iso3"], as_index=False)
        .agg(
            mean_log_population=("log_population", "mean"),
            mean_oil_export_share=("oil_export_share", "mean"),
            mean_gdp_per_capita=(INCOME, "mean"),
        )
        .copy()
    )
    country["mean_population"] = np.exp(country["mean_log_population"])
    country["microstate_lt_1m"] = country["mean_population"] < 1_000_000
    country["major_oil_exporter_ge_30pct"] = (
        country["mean_oil_export_share"] >= 0.30
    )
    country["hub_exclusion"] = country["iso3"].isin(HUB_ISO3)
    country["imf_2000_ofc"] = country["iso3"].isin(IMF_2000_OFC_ISO3)
    country["production_core_keep"] = ~(
        country["microstate_lt_1m"]
        | country["major_oil_exporter_ge_30pct"]
        | country["hub_exclusion"]
    )
    country["strict_production_core_keep"] = ~(
        country["microstate_lt_1m"]
        | country["major_oil_exporter_ge_30pct"]
        | country["imf_2000_ofc"]
    )
    country["exclusion_reasons"] = country.apply(
        lambda row: ";".join(
            reason
            for flag, reason in [
                (row["microstate_lt_1m"], "mean_population_below_1m"),
                (
                    row["major_oil_exporter_ge_30pct"],
                    "mean_oil_export_share_at_least_30pct",
                ),
                (row["hub_exclusion"], "finance_tax_or_reexport_hub"),
            ]
            if flag
        ),
        axis=1,
    )
    return country


def fit_model(
    panel: pd.DataFrame, outcome: str, estimator: str, income_form: str
) -> dict[str, float | int | bool | str]:
    if income_form == "level_ppp":
        income_term = INCOME_10K
        income_squared_term = INCOME_10K_SQ
    elif income_form == "log_ppp":
        income_term = "log_gdp_pc_ppp_constant_2021_intl_usd"
        income_squared_term = "log_gdp_pc_ppp_constant_2021_intl_usd_sq"
    else:
        raise ValueError(f"Unknown income form: {income_form}")

    columns = [
        "iso3",
        "year",
        outcome,
        INCOME,
        income_term,
        income_squared_term,
        "log_population",
        "oil_export_share",
    ]
    sample = panel[columns].replace([np.inf, -np.inf], np.nan).dropna().copy()

    if estimator == "between_country":
        sample = (
            sample.groupby("iso3", as_index=False)
            .agg(
                {
                    outcome: "mean",
                    INCOME: "mean",
                    income_term: "mean",
                    income_squared_term: "mean",
                    "log_population": "mean",
                    "oil_export_share": "mean",
                }
            )
            .copy()
        )
        formula = (
            f"{outcome} ~ {income_term} + {income_squared_term}"
            " + log_population + oil_export_share"
        )
        model = smf.ols(formula, data=sample).fit(cov_type="HC1")
    elif estimator == "pooled_year_fe":
        formula = (
            f"{outcome} ~ {income_term} + {income_squared_term}"
            " + log_population + oil_export_share + C(year)"
        )
        model = smf.ols(formula, data=sample).fit(
            cov_type="cluster", cov_kwds={"groups": sample["iso3"]}
        )
    elif estimator == "country_year_fe":
        formula = (
            f"{outcome} ~ {income_term} + {income_squared_term}"
            " + log_population + oil_export_share + C(iso3) + C(year)"
        )
        model = smf.ols(formula, data=sample).fit(
            cov_type="cluster", cov_kwds={"groups": sample["iso3"]}
        )
    else:
        raise ValueError(f"Unknown estimator: {estimator}")

    linear = float(model.params[income_term])
    quadratic = float(model.params[income_squared_term])
    stationary_point = -linear / (2.0 * quadratic) if quadratic != 0 else np.nan
    if income_form == "level_ppp":
        turning_point = float(stationary_point * 10_000.0)
    else:
        turning_point = float(np.exp(stationary_point))
    p05 = float(sample[INCOME].quantile(0.05))
    p95 = float(sample[INCOME].quantile(0.95))
    if income_form == "level_ppp":
        transformed_p05 = p05 / 10_000.0
        transformed_p95 = p95 / 10_000.0
    else:
        transformed_p05 = np.log(p05)
        transformed_p95 = np.log(p95)
    slope_low = linear + 2.0 * quadratic * transformed_p05
    slope_high = linear + 2.0 * quadratic * transformed_p95
    coefficient_names = [income_term, income_squared_term]
    covariance = model.cov_params().loc[coefficient_names, coefficient_names].to_numpy()

    def slope_standard_error(transformed_income_value: float) -> float:
        gradient = np.array([1.0, 2.0 * transformed_income_value])
        return float(np.sqrt(gradient @ covariance @ gradient))

    slope_low_standard_error = slope_standard_error(transformed_p05)
    slope_high_standard_error = slope_standard_error(transformed_p95)
    slope_low_t = slope_low / slope_low_standard_error
    slope_high_t = slope_high / slope_high_standard_error
    if OUTCOMES[outcome][1] == "count_inverted_u":
        low_endpoint_one_sided_p = float(1.0 - norm.cdf(slope_low_t))
        high_endpoint_one_sided_p = float(norm.cdf(slope_high_t))
    else:
        low_endpoint_one_sided_p = float(norm.cdf(slope_low_t))
        high_endpoint_one_sided_p = float(1.0 - norm.cdf(slope_high_t))
    intersection_union_p = max(
        low_endpoint_one_sided_p, high_endpoint_one_sided_p
    )
    above = sample[INCOME] > turning_point if np.isfinite(turning_point) else False
    if isinstance(above, bool):
        observations_above = 0
        countries_above = 0
    else:
        observations_above = int(above.sum())
        countries_above = int(sample.loc[above, "iso3"].nunique())

    return {
        "estimator": estimator,
        "income_form": income_form,
        "observations": int(model.nobs),
        "countries": int(sample["iso3"].nunique()),
        "linear_coefficient": linear,
        "linear_p_value": float(model.pvalues[income_term]),
        "quadratic_coefficient": quadratic,
        "quadratic_p_value": float(model.pvalues[income_squared_term]),
        "turning_point_ppp_constant_2021_intl_usd": turning_point,
        "income_p05": p05,
        "income_p95": p95,
        "turning_point_inside_p05_p95": bool(p05 <= turning_point <= p95),
        "slope_at_p05": slope_low,
        "slope_at_p05_standard_error": slope_low_standard_error,
        "slope_at_p05_one_sided_p": low_endpoint_one_sided_p,
        "slope_at_p95": slope_high,
        "slope_at_p95_standard_error": slope_high_standard_error,
        "slope_at_p95_one_sided_p": high_endpoint_one_sided_p,
        "intersection_union_endpoint_p": intersection_union_p,
        "observations_above_turning_point": observations_above,
        "countries_above_turning_point": countries_above,
        "r_squared": float(model.rsquared),
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    panel = pd.read_csv(INPUT)
    country = country_classification(panel)

    variants = {
        "baseline": set(country["iso3"]),
        "no_microstates": set(country.loc[~country["microstate_lt_1m"], "iso3"]),
        "no_microstates_or_major_oil": set(
            country.loc[
                ~(country["microstate_lt_1m"] | country["major_oil_exporter_ge_30pct"]),
                "iso3",
            ]
        ),
        "production_core": set(country.loc[country["production_core_keep"], "iso3"]),
        "strict_production_core": set(
            country.loc[country["strict_production_core_keep"], "iso3"]
        ),
    }

    rows: list[dict[str, float | int | bool | str]] = []
    for variant, iso3_set in variants.items():
        variant_panel = panel.loc[panel["iso3"].isin(iso3_set)].copy()
        for outcome, (label, expected_shape) in OUTCOMES.items():
            for income_form in ["level_ppp", "log_ppp"]:
                for estimator in [
                    "pooled_year_fe",
                    "between_country",
                    "country_year_fe",
                ]:
                    rows.append(
                        {
                            "variant": variant,
                            "outcome": outcome,
                            "outcome_label": label,
                            "expected_shape": expected_shape,
                            **fit_model(
                                variant_panel, outcome, estimator, income_form
                            ),
                        }
                    )

    results = pd.DataFrame(rows)
    country.to_csv(OUTPUT_DIR / "country_exclusion_classification.csv", index=False)
    results.to_csv(OUTPUT_DIR / "production_core_model_summary.csv", index=False)

    manifest = {
        "input": str(INPUT.relative_to(ROOT)),
        "microstate_rule": "mean population below 1,000,000",
        "major_oil_rule": "mean oil export share at least 30 percent",
        "hub_iso3": sorted(HUB_ISO3),
        "imf_2000_ofc_iso3": sorted(IMF_2000_OFC_ISO3),
        "baseline_countries": int(country["iso3"].nunique()),
        "production_core_countries": int(country["production_core_keep"].sum()),
        "strict_production_core_countries": int(
            country["strict_production_core_keep"].sum()
        ),
        "caveat": (
            "Country exclusions do not convert gross customs exports into "
            "domestic production or domestic value-added exports."
        ),
    }
    (OUTPUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote production-core sensitivity to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
