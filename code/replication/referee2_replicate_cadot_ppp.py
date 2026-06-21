#!/usr/bin/env python3
"""Referee 2 replication check for Cadot/PPP hump results.

This script intentionally does not import the author's runner. It reads the
saved analytic panels and re-estimates selected OLS specifications using
statsmodels formulas, then compares point estimates to the generated result
tables. It is a scoped audit script, not a replacement for the full pipeline.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import statsmodels.formula.api as smf


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "correspondence" / "referee2"


def fit_terms(panel: pd.DataFrame, formula: str, cluster_col: str, terms: list[str]) -> pd.DataFrame:
    model = smf.ols(formula, data=panel).fit(cov_type="cluster", cov_kwds={"groups": panel[cluster_col]})
    return pd.DataFrame(
        {
            "term": terms,
            "replicate_coefficient": [float(model.params[term]) for term in terms],
            "replicate_std_error": [float(model.bse[term]) for term in terms],
            "replicate_nobs": int(model.nobs),
            "replicate_clusters": int(panel[cluster_col].nunique()),
        }
    )


def compare_ppp() -> pd.DataFrame:
    panel = pd.read_csv(ROOT / "results/samples/rd2_countries/ppp_hump_regression_tables/ppp_hump_common_sample_panel.csv")
    panel["gdp_pc_ppp_constant_2021_intl_usd_10k_sq"] = panel["gdp_pc_ppp_constant_2021_intl_usd_10k"] ** 2
    panel["log_gdp_pc_ppp_constant_2021_intl_usd_sq"] = panel["log_gdp_pc_ppp_constant_2021_intl_usd"] ** 2
    saved = pd.read_csv(ROOT / "results/samples/rd2_countries/ppp_hump_regression_tables/ppp_hump_regression_models.csv")
    checks = [
        (
            "ppp_level_export_product_gini",
            "export_product_gini ~ gdp_pc_ppp_constant_2021_intl_usd_10k + gdp_pc_ppp_constant_2021_intl_usd_10k_sq + log_population + oil_export_share + C(year)",
            ["gdp_pc_ppp_constant_2021_intl_usd_10k", "gdp_pc_ppp_constant_2021_intl_usd_10k_sq"],
            "level_ppp_controls_year_fe_country_cluster",
            "product_gini",
            "Exports",
        ),
        (
            "ppp_level_export_world_relative_product_gini",
            "export_world_relative_product_gini ~ gdp_pc_ppp_constant_2021_intl_usd_10k + gdp_pc_ppp_constant_2021_intl_usd_10k_sq + log_population + oil_export_share + C(year)",
            ["gdp_pc_ppp_constant_2021_intl_usd_10k", "gdp_pc_ppp_constant_2021_intl_usd_10k_sq"],
            "level_ppp_controls_year_fe_country_cluster",
            "world_relative_product_gini",
            "Exports",
        ),
        (
            "ppp_log_export_product_gini",
            "export_product_gini ~ log_gdp_pc_ppp_constant_2021_intl_usd + log_gdp_pc_ppp_constant_2021_intl_usd_sq + log_population + oil_export_share + C(year)",
            ["log_gdp_pc_ppp_constant_2021_intl_usd", "log_gdp_pc_ppp_constant_2021_intl_usd_sq"],
            "log_ppp_controls_year_fe_country_cluster",
            "product_gini",
            "Exports",
        ),
    ]
    rows = []
    for check_name, formula, terms, model_label, metric, flow in checks:
        rep = fit_terms(panel, formula, "reporter_code", terms)
        author = saved[
            saved["model_label"].eq(model_label)
            & saved["metric"].eq(metric)
            & saved["flow"].eq(flow)
            & saved["term"].isin(terms)
        ][["term", "coefficient", "std_error", "nobs", "clusters"]]
        merged = rep.merge(author, on="term", validate="one_to_one")
        merged.insert(0, "check", check_name)
        rows.append(merged)
    return pd.concat(rows, ignore_index=True)


def compare_cadot_log_gni() -> pd.DataFrame:
    panel = pd.read_csv(ROOT / "results/samples/rd2_countries/cadot_hump_tribunal_tables/cadot_hump_country_year_panel.csv")
    saved = pd.read_csv(ROOT / "results/samples/rd2_countries/cadot_hump_tribunal_tables/cadot_hump_models.csv")
    terms = ["log_gni_pc", "log_gni_pc_sq"]
    rep = fit_terms(
        panel,
        "world_relative_product_gini ~ log_gni_pc + log_gni_pc_sq + log_population + oil_export_share + C(year)",
        "reporter_code",
        terms,
    )
    author = saved[
        saved["model_label"].eq("quadratic_controls_year_fe_country_cluster")
        & saved["metric"].eq("world_relative_product_gini")
        & saved["term"].isin(terms)
    ][["term", "coefficient", "std_error", "nobs", "clusters"]]
    merged = rep.merge(author, on="term", validate="one_to_one")
    merged.insert(0, "check", "cadot_log_gni_world_relative_product_gini")
    return merged


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    comparison = pd.concat([compare_ppp(), compare_cadot_log_gni()], ignore_index=True)
    comparison["coefficient_abs_diff"] = (comparison["replicate_coefficient"] - comparison["coefficient"]).abs()
    comparison["std_error_abs_diff"] = (comparison["replicate_std_error"] - comparison["std_error"]).abs()
    comparison["nobs_match"] = comparison["replicate_nobs"].eq(comparison["nobs"])
    comparison["clusters_match"] = comparison["replicate_clusters"].eq(comparison["clusters"])
    comparison.to_csv(OUT / "2026-05-30_cadot_ppp_referee2_replication_comparison.csv", index=False)
    print(comparison.to_string(index=False))


if __name__ == "__main__":
    main()
