#!/usr/bin/env python3
"""Build the static Panagariya-Bagaria trade concentration research site.

The site is generated from committed result artifacts, not from raw Comtrade
files. It writes a complete GitHub Pages-ready site to /tmp/trade-gini-map-site
by default while leaving the local research repo and the Pages repo histories
separate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from plotly.offline import get_plotlyjs


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = Path("/tmp/trade-gini-map-site")
PDF_GUIDANCE = Path("/Users/tanushsawhney/Downloads/Untitled document.pdf")

SOURCE_FILES = {
    "exercise_1_panel": ROOT / "results/exercise_01_tables/concentration_all_years.csv",
    "exercise_2_growth": ROOT / "results/exercise_02_tables/bucket_growth_summary.csv",
    "exercise_2_growth_models": ROOT / "results/exercise_02_tables/bucket_growth_models.csv",
    "exercise_2_growth_diagnostics": ROOT / "results/exercise_02_tables/bucket_growth_diagnostics.csv",
    "exercise_3_bins": ROOT / "results/exercise_03_tables/import_bin_concentration.csv",
    "exercise_3_decomposition": ROOT / "results/exercise_03_tables/import_bin_decomposition.csv",
    "exercise_3_total": ROOT / "results/exercise_03_tables/import_total_concentration.csv",
    "exercise_3_top_goods": ROOT / "results/exercise_03_tables/top_goods_by_import_bin_world_india_2024.csv",
    "exercise_3_import_bin_goods_share": ROOT / "results/exercise_03_tables/import_bin_goods_country_share_2024.csv",
    "exercise_4_suppliers": ROOT / "results/exercise_04_tables/dominant_supplier_importer_summary.csv",
    "exercise_4_partner_counterfactual_country_year": ROOT / "results/exercise_04_tables/partner_gini_counterfactual_country_year.csv",
    "exercise_4_partner_counterfactual_latest": ROOT / "results/exercise_04_tables/partner_gini_counterfactual_latest.csv",
    "h24_supplier_summary": ROOT / "results/h24_supplier_specialization_tables/yearly_concentration_summary.csv",
    "h24_supplier_comparison": ROOT / "results/h24_supplier_specialization_tables/importer_vs_world_supplier_dominance_comparison.csv",
    "exercise_6_exclusions": ROOT / "results/exercise_06_tables/concentration_exclusions_all_years.csv",
    "exercise_10_hs2": ROOT / "results/exercise_10_tables/random_benchmark_hs2_product_all_years.csv",
    "exercise_10_active": ROOT / "results/exercise_10_tables/random_benchmark_active_count_null_all_years.csv",
    "exercise_11_io_summary": ROOT / "results/exercise_11_tables/country_year_input_output_linkage_summary.csv",
    "exercise_11_coefficients": ROOT / "results/exercise_11_product_export_linkage_tables/selected_regression_coefficients.csv",
    "exercise_11_intermediate_effects": ROOT / "results/exercise_11_product_export_linkage_tables/intermediate_effects.csv",
    "exercise_11_hs2_panel": ROOT / "results/exercise_11_product_export_linkage_tables/hs2_export_linkage_panel.csv",
    "exercise_11_hs2_regressions": ROOT / "results/exercise_11_product_export_linkage_tables/hs2_regressions.csv",
    "exercise_11_hs6_4pct_bins": ROOT / "results/exercise_11_product_export_linkage_tables/ex11_export_linkage_by_loo_4pct_bin.csv",
    "exercise_11_hs2_4pct_bins": ROOT / "results/exercise_11_product_export_linkage_tables/ex11_hs2_export_linkage_by_loo_4pct_bin.csv",
    "exercise_11_commodity_comparison": ROOT / "results/exercise_11_product_export_linkage_tables/commodity_exclusion_regression_comparison.csv",
    "exercise_11_commodity_stats": ROOT / "results/exercise_11_product_export_linkage_tables/commodity_outlier_exclusion_stats.csv",
}

FIGURES = {
    "ex1_median_concentration_over_time": ROOT / "results/exercise_01_figures/median_concentration_over_time.png",
    "ex1_import_vs_export_product_gini_over_time": ROOT
    / "results/exercise_01_figures/import_vs_export_product_gini_over_time.png",
    "ex1_country_product_gini_lines": ROOT / "results/exercise_01_figures/country_product_gini_lines.png",
    "ex3_value_share": ROOT / "results/exercise_03_figures/median_import_value_share_by_bin.png",
    "ex3_leave_one_out": ROOT / "results/exercise_03_figures/latest_year_gini_reduction_when_bin_excluded.png",
    "ex3_energy_total_share_hist": ROOT / "results/exercise_03_figures/energy_goods_sum_total_import_share_2024.png",
    "ex3_energy_bin_share_hist": ROOT / "results/exercise_03_figures/energy_goods_sum_bin_import_share_2024.png",
    "ex3_intermediates_total_share_hist": ROOT / "results/exercise_03_figures/intermediates_goods_sum_total_import_share_2024.png",
    "ex3_intermediates_bin_share_hist": ROOT / "results/exercise_03_figures/intermediates_goods_sum_bin_import_share_2024.png",
    "ex3_capital_goods_total_share_hist": ROOT / "results/exercise_03_figures/capital_goods_goods_sum_total_import_share_2024.png",
    "ex3_capital_goods_bin_share_hist": ROOT / "results/exercise_03_figures/capital_goods_goods_sum_bin_import_share_2024.png",
    "ex3_final_consumption_total_share_hist": ROOT / "results/exercise_03_figures/final_consumption_goods_sum_total_import_share_2024.png",
    "ex3_final_consumption_bin_share_hist": ROOT / "results/exercise_03_figures/final_consumption_goods_sum_bin_import_share_2024.png",
    "ex4_supplier_time": ROOT / "results/exercise_04_figures/dominant_supplier_summary_over_time.png",
    "ex4_supplier_distribution": ROOT / "results/exercise_04_figures/latest_year_top_supplier_share_distribution.png",
    "h24_importer_world_supplier_comparison": ROOT / "results/h24_supplier_specialization_figures/importer_country_vs_world_supplier_dominance.png",
    "ex4_partner_counterfactual_latest": ROOT / "results/exercise_04_figures/partner_gini_counterfactual_latest.png",
    "ex4_india_partner_counterfactual": ROOT / "results/exercise_04_figures/india_partner_gini_counterfactual_timeseries.png",
    "ex6_before_after": ROOT / "results/exercise_06_figures/before_after_product_gini_over_time.png",
    "ex6_removed": ROOT / "results/exercise_06_figures/trade_share_removed_over_time.png",
    "ex10_actual_vs_benchmark": ROOT / "results/exercise_10_figures/actual_vs_simulated_gini_product_hs2_preserved.png",
    "ex10_percentile": ROOT / "results/exercise_10_figures/share_above_95th_percentile_product_hs2_preserved.png",
    "ex11_india_io": ROOT / "results/exercise_11_figures/india_top_export_input_exposure_over_time.png",
    "ex11_export_linkage_decile": ROOT / "results/exercise_11_product_export_linkage_figures/ex11_export_linkage_by_loo_decile.png",
    "ex11_hs2_linkage_decile": ROOT / "results/exercise_11_product_export_linkage_figures/ex11_hs2_export_linkage_by_loo_decile.png",
    "ex11_export_linkage_4pct": ROOT / "results/exercise_11_product_export_linkage_figures/ex11_export_linkage_by_loo_4pct_bin.png",
    "ex11_hs2_linkage_4pct": ROOT / "results/exercise_11_product_export_linkage_figures/ex11_hs2_export_linkage_by_loo_4pct_bin.png",
    "ex11_coefficients": ROOT / "results/exercise_11_product_export_linkage_figures/ex11_intermediate_channel_coefficients.png",
    "ex11_india_supplier_scatter": ROOT / "results/exercise_11_product_export_linkage_figures/ex11_india_product_supplier_loo_scatter.png",
}

DOWNLOADS = {
    "exercise_01_concentration_all_years.csv": SOURCE_FILES["exercise_1_panel"],
    "exercise_02_bucket_growth_summary.csv": SOURCE_FILES["exercise_2_growth"],
    "exercise_02_bucket_growth_models.csv": SOURCE_FILES["exercise_2_growth_models"],
    "exercise_02_bucket_growth_diagnostics.csv": SOURCE_FILES["exercise_2_growth_diagnostics"],
    "exercise_03_import_bin_concentration.csv": SOURCE_FILES["exercise_3_bins"],
    "exercise_03_top_goods_by_import_bin_world_india_2024.csv": SOURCE_FILES["exercise_3_top_goods"],
    "exercise_03_import_bin_goods_country_share_2024.csv": SOURCE_FILES["exercise_3_import_bin_goods_share"],
    "exercise_04_dominant_supplier_importer_summary.csv": SOURCE_FILES["exercise_4_suppliers"],
    "exercise_04_partner_gini_counterfactual_country_year.csv": SOURCE_FILES["exercise_4_partner_counterfactual_country_year"],
    "exercise_04_partner_gini_counterfactual_latest.csv": SOURCE_FILES["exercise_4_partner_counterfactual_latest"],
    "h24_supplier_specialization_yearly_summary.csv": SOURCE_FILES["h24_supplier_summary"],
    "h24_importer_vs_world_supplier_dominance_comparison.csv": SOURCE_FILES["h24_supplier_comparison"],
    "exercise_06_concentration_exclusions_all_years.csv": SOURCE_FILES["exercise_6_exclusions"],
    "exercise_10_hs2_product_benchmark_all_years.csv": SOURCE_FILES["exercise_10_hs2"],
    "exercise_11_country_year_input_output_linkage_summary.csv": SOURCE_FILES["exercise_11_io_summary"],
    "exercise_11_selected_regression_coefficients.csv": SOURCE_FILES["exercise_11_coefficients"],
    "exercise_11_intermediate_effects.csv": SOURCE_FILES["exercise_11_intermediate_effects"],
    "exercise_11_hs2_regressions.csv": SOURCE_FILES["exercise_11_hs2_regressions"],
    "exercise_11_export_linkage_by_loo_4pct_bin.csv": SOURCE_FILES["exercise_11_hs6_4pct_bins"],
    "exercise_11_hs2_export_linkage_by_loo_4pct_bin.csv": SOURCE_FILES["exercise_11_hs2_4pct_bins"],
    "exercise_11_commodity_exclusion_regression_comparison.csv": SOURCE_FILES["exercise_11_commodity_comparison"],
    "exercise_11_commodity_outlier_exclusion_stats.csv": SOURCE_FILES["exercise_11_commodity_stats"],
}

PROF_P_SOURCE_FILES = {
    "prof_p_top_shares": ROOT / "results/prof_p_replication/tables/prof_p_2001_hs6_top_shares_vs_table2.csv",
    "prof_p_lorenz": ROOT / "results/prof_p_replication/tables/prof_p_2001_lorenz_india_china_us.csv",
}

PROF_P_DOWNLOADS = {
    "prof_p_2001_hs6_top_shares_vs_table2.csv": PROF_P_SOURCE_FILES["prof_p_top_shares"],
    "prof_p_2001_lorenz_india_china_us.csv": PROF_P_SOURCE_FILES["prof_p_lorenz"],
    "prof_p_data_processing_cookbook.pdf": ROOT / "results/prof_p_replication/pdf/prof_p_data_processing_cookbook.pdf",
}

COUNTRY_SIZE_TABLE_FILES = {
    "country_size_main_models": Path("country_size_effect_tables/main_models.csv"),
    "country_size_robustness_models": Path("country_size_effect_tables/robustness_models.csv"),
    "country_size_two_way_cluster_models": Path("country_size_effect_tables/two_way_cluster_models.csv"),
    "country_size_fama_macbeth_models": Path("country_size_effect_tables/fama_macbeth_models.csv"),
    "country_size_gmm_lag_iv_models": Path("country_size_effect_tables/gmm_lag_iv_models.csv"),
    "country_size_gmm_lag_iv_first_stage": Path("country_size_effect_tables/gmm_lag_iv_first_stage.csv"),
    "country_size_primary_share_control_models": Path("country_size_effect_tables/primary_share_control_models.csv"),
    "country_size_primary_share_two_way_cluster_models": Path("country_size_effect_tables/primary_share_two_way_cluster_models.csv"),
    "country_size_primary_share_fama_macbeth_models": Path("country_size_effect_tables/primary_share_fama_macbeth_models.csv"),
    "country_size_primary_export_share_diagnostics": Path("country_size_effect_tables/primary_export_share_diagnostics.csv"),
    "country_size_primary_product_hs6_mapping": Path("country_size_effect_tables/primary_product_hs6_mapping.csv"),
    "country_size_us_population_counterfactuals": Path("country_size_effect_tables/us_population_counterfactuals.csv"),
    "country_size_yearly_slopes": Path("country_size_effect_tables/yearly_slopes.csv"),
    "country_size_sample_diagnostics": Path("country_size_effect_tables/sample_diagnostics.csv"),
    "country_size_common_universe_models": Path("country_size_common_universe_test_tables/common_universe_models.csv"),
    "country_size_common_universe_two_way_models": Path("country_size_common_universe_test_tables/common_universe_two_way_models.csv"),
    "country_size_common_universe_diagnostics": Path("country_size_common_universe_test_tables/diagnostics.csv"),
    "country_size_common_universe_source_differences": Path("country_size_common_universe_test_tables/source_difference_examples.csv"),
    "world_large_product_exposure_spearman_summary": Path("world_large_product_exposure_tables/world_large_product_exposure_spearman_summary.csv"),
    "world_large_product_exposure_yearly_spearman": Path("world_large_product_exposure_tables/world_large_product_exposure_yearly_spearman.csv"),
    "world_large_product_exposure_models": Path("world_large_product_exposure_tables/world_large_product_exposure_models.csv"),
    "world_large_product_exposure_diagnostics": Path("world_large_product_exposure_tables/world_large_product_exposure_diagnostics.csv"),
}

COUNTRY_SIZE_FIGURE_FILES = {
    "country_size_yearly_size_slopes_product": Path("country_size_effect_figures/yearly_size_slopes_product.png"),
    "country_size_yearly_size_slopes_partner": Path("country_size_effect_figures/yearly_size_slopes_partner.png"),
    "country_size_gdp_product_alignment_scatter": Path("country_size_effect_figures/gdp_product_alignment_scatter.png"),
}

COUNTRY_SIZE_DOWNLOAD_FILENAMES = {
    "country_size_effect_main_models.csv": "country_size_main_models",
    "country_size_effect_robustness_models.csv": "country_size_robustness_models",
    "country_size_effect_two_way_cluster_models.csv": "country_size_two_way_cluster_models",
    "country_size_effect_fama_macbeth_models.csv": "country_size_fama_macbeth_models",
    "country_size_effect_gmm_lag_iv_models.csv": "country_size_gmm_lag_iv_models",
    "country_size_effect_gmm_lag_iv_first_stage.csv": "country_size_gmm_lag_iv_first_stage",
    "country_size_effect_primary_share_control_models.csv": "country_size_primary_share_control_models",
    "country_size_effect_primary_share_two_way_cluster_models.csv": "country_size_primary_share_two_way_cluster_models",
    "country_size_effect_primary_share_fama_macbeth_models.csv": "country_size_primary_share_fama_macbeth_models",
    "country_size_effect_primary_export_share_diagnostics.csv": "country_size_primary_export_share_diagnostics",
    "country_size_effect_primary_product_hs6_mapping.csv": "country_size_primary_product_hs6_mapping",
    "country_size_effect_us_population_counterfactuals.csv": "country_size_us_population_counterfactuals",
    "country_size_effect_yearly_slopes.csv": "country_size_yearly_slopes",
    "country_size_effect_sample_diagnostics.csv": "country_size_sample_diagnostics",
    "country_size_common_universe_models.csv": "country_size_common_universe_models",
    "country_size_common_universe_two_way_models.csv": "country_size_common_universe_two_way_models",
    "country_size_common_universe_diagnostics.csv": "country_size_common_universe_diagnostics",
    "country_size_common_universe_source_difference_examples.csv": "country_size_common_universe_source_differences",
    "world_large_product_exposure_spearman_summary.csv": "world_large_product_exposure_spearman_summary",
    "world_large_product_exposure_yearly_spearman.csv": "world_large_product_exposure_yearly_spearman",
    "world_large_product_exposure_models.csv": "world_large_product_exposure_models",
    "world_large_product_exposure_diagnostics.csv": "world_large_product_exposure_diagnostics",
}

COUNTRY_SIZE_EXTRA_DOWNLOAD_FILES = {
    "world_large_product_exposure_panel.csv": Path("world_large_product_exposure_tables/world_large_product_exposure_panel.csv"),
    "world_large_product_exposure.md": Path("world_large_product_exposure_tables/world_large_product_exposure.md"),
    "world_large_product_exposure_adversarial_review.md": Path("world_large_product_exposure_tables/adversarial_review.md"),
    "run_manifest_world_large_product_exposure.json": Path("world_large_product_exposure_tables/run_manifest_world_large_product_exposure.json"),
}

GROWTH_EFFECT_TABLE_FILES = {
    "growth_effect_main_models": Path("growth_effect_tables/main_models.csv"),
    "growth_effect_sample_comparison_models": Path("growth_effect_tables/sample_comparison_models.csv"),
    "growth_effect_robustness_models": Path("growth_effect_tables/robustness_models.csv"),
    "growth_effect_income_bin_slopes": Path("growth_effect_tables/income_bin_slopes.csv"),
    "growth_effect_threshold_scan": Path("growth_effect_tables/threshold_scan.csv"),
    "growth_effect_sample_diagnostics": Path("growth_effect_tables/sample_diagnostics.csv"),
    "growth_effect_missing_controls": Path("growth_effect_tables/missing_controls.csv"),
}

GROWTH_EFFECT_FIGURE_FILES = {
    "growth_effect_main_growth_coefficients": Path("growth_effect_figures/main_growth_coefficients.png"),
    "growth_effect_income_bin_slopes": Path("growth_effect_figures/income_bin_slopes.png"),
}

GROWTH_EFFECT_DOWNLOAD_FILENAMES = {
    "growth_effect_main_models.csv": "growth_effect_main_models",
    "growth_effect_sample_comparison_models.csv": "growth_effect_sample_comparison_models",
    "growth_effect_robustness_models.csv": "growth_effect_robustness_models",
    "growth_effect_income_bin_slopes.csv": "growth_effect_income_bin_slopes",
    "growth_effect_threshold_scan.csv": "growth_effect_threshold_scan",
    "growth_effect_sample_diagnostics.csv": "growth_effect_sample_diagnostics",
    "growth_effect_missing_controls.csv": "growth_effect_missing_controls",
}

FUTURE_GROWTH_TABLE_FILES = {
    "future_growth_panel": Path("future_growth_concentration_tables/future_growth_concentration_panel.csv"),
    "future_growth_bucket_summary": Path("future_growth_concentration_tables/bucket_summary.csv"),
    "future_growth_country_examples": Path("future_growth_concentration_tables/country_examples.csv"),
    "future_growth_bucket_models": Path("future_growth_concentration_tables/bucket_models.csv"),
    "future_growth_continuous_models": Path("future_growth_concentration_tables/continuous_models.csv"),
    "future_growth_paired_models": Path("future_growth_concentration_tables/paired_models.csv"),
    "future_growth_robustness_models": Path("future_growth_concentration_tables/robustness_models.csv"),
    "future_growth_base_size_bin_summary": Path("future_growth_concentration_tables/base_size_bin_summary.csv"),
    "future_growth_base_size_sensitivity_models": Path("future_growth_concentration_tables/base_size_sensitivity_models.csv"),
    "future_growth_mechanism_channel_panel": Path("future_growth_concentration_tables/mechanism_channel_panel.csv"),
    "future_growth_mechanism_channel_models": Path("future_growth_concentration_tables/mechanism_channel_models.csv"),
    "future_growth_mechanism_summary": Path("future_growth_concentration_tables/mechanism_summary.csv"),
    "future_growth_mechanism_diagnostics": Path("future_growth_concentration_tables/mechanism_diagnostics.csv"),
    "future_growth_leave_one_country_out_influence": Path("future_growth_concentration_tables/leave_one_country_out_influence.csv"),
    "future_growth_sample_diagnostics": Path("future_growth_concentration_tables/sample_diagnostics.csv"),
    "future_growth_missing_controls": Path("future_growth_concentration_tables/missing_controls.csv"),
}

FUTURE_GROWTH_FIGURE_FILES = {
    "future_growth_bucket_summary_growth": Path("future_growth_concentration_figures/bucket_summary_growth.png"),
    "future_growth_continuous_coefficients": Path("future_growth_concentration_figures/continuous_coefficients.png"),
}

FUTURE_GROWTH_DOWNLOAD_FILENAMES = {
    "future_growth_concentration_panel.csv": "future_growth_panel",
    "future_growth_bucket_summary.csv": "future_growth_bucket_summary",
    "future_growth_country_examples.csv": "future_growth_country_examples",
    "future_growth_bucket_models.csv": "future_growth_bucket_models",
    "future_growth_continuous_models.csv": "future_growth_continuous_models",
    "future_growth_paired_models.csv": "future_growth_paired_models",
    "future_growth_robustness_models.csv": "future_growth_robustness_models",
    "future_growth_base_size_bin_summary.csv": "future_growth_base_size_bin_summary",
    "future_growth_base_size_sensitivity_models.csv": "future_growth_base_size_sensitivity_models",
    "future_growth_mechanism_channel_panel.csv": "future_growth_mechanism_channel_panel",
    "future_growth_mechanism_channel_models.csv": "future_growth_mechanism_channel_models",
    "future_growth_mechanism_summary.csv": "future_growth_mechanism_summary",
    "future_growth_mechanism_diagnostics.csv": "future_growth_mechanism_diagnostics",
    "future_growth_leave_one_country_out_influence.csv": "future_growth_leave_one_country_out_influence",
    "future_growth_sample_diagnostics.csv": "future_growth_sample_diagnostics",
    "future_growth_missing_controls.csv": "future_growth_missing_controls",
}

PARTNER_STABILITY_TABLE_FILES = {
    "partner_stability_country_flow": Path("partner_gini_stability_tables/country_flow_stability.csv"),
    "partner_stability_summary": Path("partner_gini_stability_tables/stability_summary.csv"),
    "partner_stability_common_trends": Path("partner_gini_stability_tables/common_trend_models.csv"),
    "partner_stability_variance_decomposition": Path("partner_gini_stability_tables/variance_decomposition.csv"),
    "partner_stability_low_active_sensitivity": Path("partner_gini_stability_tables/low_active_partner_sensitivity.csv"),
}

PARTNER_STABILITY_FIGURE_FILES = {
    "partner_stability_country_slope_distribution": Path("partner_gini_stability_figures/country_slope_distribution.png"),
    "partner_stability_largest_endpoint_changes": Path("partner_gini_stability_figures/largest_endpoint_changes.png"),
}

PARTNER_STABILITY_DOWNLOAD_FILENAMES = {
    "partner_gini_stability_country_flow.csv": "partner_stability_country_flow",
    "partner_gini_stability_summary.csv": "partner_stability_summary",
    "partner_gini_stability_common_trend_models.csv": "partner_stability_common_trends",
    "partner_gini_stability_variance_decomposition.csv": "partner_stability_variance_decomposition",
    "partner_gini_stability_low_active_partner_sensitivity.csv": "partner_stability_low_active_sensitivity",
}

METHODS_TABLE_FILES = {
    "methods_hs6_codes_by_year": Path("methods_tables/hs6_codes_by_year.csv"),
}

METHODS_FIGURE_FILES = {
    "methods_hs6_codes_by_year": Path("methods_figures/hs6_codes_by_year.png"),
}

METHODS_DOWNLOAD_FILENAMES = {
    "methods_hs6_codes_by_year.csv": "methods_hs6_codes_by_year",
}

WORLD_RELATIVE_TABLE_FILES = {
    "world_relative_product_gini_panel": Path("world_relative_product_gini_tables/world_relative_product_gini_all_years.csv"),
    "world_weighted_product_gini_appendix": Path("world_relative_product_gini_tables/world_weighted_product_gini_appendix.csv"),
    "world_relative_product_gini_diagnostics": Path("world_relative_product_gini_tables/world_relative_product_gini_diagnostics.csv"),
    "world_relative_product_gini_classification_diagnostics": Path(
        "world_relative_product_gini_tables/world_relative_product_gini_classification_diagnostics.csv"
    ),
    "world_relative_product_gini_harmonization_diagnostics": Path(
        "world_relative_product_gini_tables/world_relative_product_gini_harmonization_diagnostics.csv"
    ),
    "world_relative_product_gini_yearly_summary": Path("world_relative_product_gini_tables/world_relative_product_gini_yearly_summary.csv"),
    "world_relative_product_gini_latest_rankings": Path("world_relative_product_gini_tables/world_relative_product_gini_latest_rankings.csv"),
    "world_relative_product_gini_manifest": Path("world_relative_product_gini_tables/run_manifest_world_relative_product_gini.json"),
    "world_relative_product_contribution_top_drivers": Path(
        "world_relative_product_gini_contributions/world_relative_product_contribution_top_drivers.csv"
    ),
    "world_relative_product_contribution_country_year_summary": Path(
        "world_relative_product_gini_contributions/world_relative_product_contribution_country_year_summary.csv"
    ),
    "world_relative_product_contribution_latest_small_countries": Path(
        "world_relative_product_gini_contributions/world_relative_product_contribution_latest_small_countries.csv"
    ),
    "world_relative_product_contribution_bucket_summary": Path(
        "world_relative_product_gini_contributions/world_relative_product_contribution_bucket_summary.csv"
    ),
    "world_relative_product_contribution_validation": Path(
        "world_relative_product_gini_contributions/world_relative_product_contribution_validation.csv"
    ),
    "world_relative_product_contribution_manifest": Path(
        "world_relative_product_gini_contributions/run_manifest_world_relative_product_contributions.json"
    ),
    "world_relative_import_product_gini_panel": Path(
        "world_relative_import_product_gini_tables/world_relative_import_product_gini_all_years.csv"
    ),
    "world_weighted_import_product_gini_appendix": Path(
        "world_relative_import_product_gini_tables/world_weighted_import_product_gini_appendix.csv"
    ),
    "world_relative_import_product_gini_diagnostics": Path(
        "world_relative_import_product_gini_tables/world_relative_import_product_gini_diagnostics.csv"
    ),
    "world_relative_import_product_gini_classification_diagnostics": Path(
        "world_relative_import_product_gini_tables/world_relative_import_product_gini_classification_diagnostics.csv"
    ),
    "world_relative_import_product_gini_harmonization_diagnostics": Path(
        "world_relative_import_product_gini_tables/world_relative_import_product_gini_harmonization_diagnostics.csv"
    ),
    "world_relative_import_product_gini_yearly_summary": Path(
        "world_relative_import_product_gini_tables/world_relative_import_product_gini_yearly_summary.csv"
    ),
    "world_relative_import_product_gini_latest_rankings": Path(
        "world_relative_import_product_gini_tables/world_relative_import_product_gini_latest_rankings.csv"
    ),
    "world_relative_import_product_gini_manifest": Path(
        "world_relative_import_product_gini_tables/run_manifest_world_relative_import_product_gini.json"
    ),
    "world_relative_import_product_contribution_top_drivers": Path(
        "world_relative_import_product_gini_contributions/world_relative_import_product_contribution_top_drivers.csv"
    ),
    "world_relative_import_product_contribution_country_year_summary": Path(
        "world_relative_import_product_gini_contributions/world_relative_import_product_contribution_country_year_summary.csv"
    ),
    "world_relative_import_product_contribution_latest_small_countries": Path(
        "world_relative_import_product_gini_contributions/world_relative_import_product_contribution_latest_small_countries.csv"
    ),
    "world_relative_import_product_contribution_bucket_summary": Path(
        "world_relative_import_product_gini_contributions/world_relative_import_product_contribution_bucket_summary.csv"
    ),
    "world_relative_import_product_contribution_validation": Path(
        "world_relative_import_product_gini_contributions/world_relative_import_product_contribution_validation.csv"
    ),
    "world_relative_import_product_contribution_manifest": Path(
        "world_relative_import_product_gini_contributions/run_manifest_world_relative_import_product_contributions.json"
    ),
}

WORLD_RELATIVE_FIGURE_FILES = {
    "world_relative_hs_section_line_value_shares": Path(
        "section_16_diagnostics/hs_section_line_value_shares_rd2_countries_2021_unique_products.png"
    ),
}

WORLD_RELATIVE_DOWNLOAD_FILENAMES = {
    "world_relative_product_gini_all_years.csv": "world_relative_product_gini_panel",
    "world_weighted_product_gini_appendix.csv": "world_weighted_product_gini_appendix",
    "world_relative_product_gini_diagnostics.csv": "world_relative_product_gini_diagnostics",
    "world_relative_product_gini_classification_diagnostics.csv": "world_relative_product_gini_classification_diagnostics",
    "world_relative_product_gini_harmonization_diagnostics.csv": "world_relative_product_gini_harmonization_diagnostics",
    "world_relative_product_gini_yearly_summary.csv": "world_relative_product_gini_yearly_summary",
    "world_relative_product_gini_latest_rankings.csv": "world_relative_product_gini_latest_rankings",
    "run_manifest_world_relative_product_gini.json": "world_relative_product_gini_manifest",
    "world_relative_product_contribution_top_drivers.csv": "world_relative_product_contribution_top_drivers",
    "world_relative_product_contribution_country_year_summary.csv": "world_relative_product_contribution_country_year_summary",
    "world_relative_product_contribution_latest_small_countries.csv": "world_relative_product_contribution_latest_small_countries",
    "world_relative_product_contribution_bucket_summary.csv": "world_relative_product_contribution_bucket_summary",
    "world_relative_product_contribution_validation.csv": "world_relative_product_contribution_validation",
    "run_manifest_world_relative_product_contributions.json": "world_relative_product_contribution_manifest",
    "world_relative_import_product_gini_all_years.csv": "world_relative_import_product_gini_panel",
    "world_weighted_import_product_gini_appendix.csv": "world_weighted_import_product_gini_appendix",
    "world_relative_import_product_gini_diagnostics.csv": "world_relative_import_product_gini_diagnostics",
    "world_relative_import_product_gini_classification_diagnostics.csv": "world_relative_import_product_gini_classification_diagnostics",
    "world_relative_import_product_gini_harmonization_diagnostics.csv": "world_relative_import_product_gini_harmonization_diagnostics",
    "world_relative_import_product_gini_yearly_summary.csv": "world_relative_import_product_gini_yearly_summary",
    "world_relative_import_product_gini_latest_rankings.csv": "world_relative_import_product_gini_latest_rankings",
    "run_manifest_world_relative_import_product_gini.json": "world_relative_import_product_gini_manifest",
    "world_relative_import_product_contribution_top_drivers.csv": "world_relative_import_product_contribution_top_drivers",
    "world_relative_import_product_contribution_country_year_summary.csv": "world_relative_import_product_contribution_country_year_summary",
    "world_relative_import_product_contribution_latest_small_countries.csv": "world_relative_import_product_contribution_latest_small_countries",
    "world_relative_import_product_contribution_bucket_summary.csv": "world_relative_import_product_contribution_bucket_summary",
    "world_relative_import_product_contribution_validation.csv": "world_relative_import_product_contribution_validation",
    "run_manifest_world_relative_import_product_contributions.json": "world_relative_import_product_contribution_manifest",
}

CONTRIBUTIONS_TABLE_FILES = {
    "contributions_import_wr_robustness_models": Path(
        "world_relative_import_exercise_robustness/world_relative_import_exercise_robustness_models.csv"
    ),
    "contributions_import_wr_key_coefficients": Path(
        "world_relative_import_exercise_robustness/world_relative_import_exercise_robustness_key_coefficients.csv"
    ),
    "contributions_import_size_mechanism_models": Path("import_size_mechanism_tests/import_size_mechanism_models.csv"),
    "contributions_import_size_mechanism_key_coefficients": Path(
        "import_size_mechanism_tests/import_size_mechanism_key_coefficients.csv"
    ),
    "contributions_partner_gini_stability_summary": Path("partner_gini_stability_tables/stability_summary.csv"),
    "contributions_partner_gini_common_trends": Path("partner_gini_stability_tables/common_trend_models.csv"),
    "contributions_partner_gini_country_flow_stability": Path("partner_gini_stability_tables/country_flow_stability.csv"),
}

CONTRIBUTIONS_DOWNLOAD_FILENAMES = {
    "world_relative_import_exercise_robustness_models.csv": "contributions_import_wr_robustness_models",
    "world_relative_import_exercise_robustness_key_coefficients.csv": "contributions_import_wr_key_coefficients",
    "import_size_mechanism_models.csv": "contributions_import_size_mechanism_models",
    "import_size_mechanism_key_coefficients.csv": "contributions_import_size_mechanism_key_coefficients",
    "partner_gini_stability_summary.csv": "contributions_partner_gini_stability_summary",
    "partner_gini_common_trend_models.csv": "contributions_partner_gini_common_trends",
    "partner_gini_country_flow_stability.csv": "contributions_partner_gini_country_flow_stability",
}

CONTRIBUTIONS_EXTRA_DOWNLOAD_FILES = {
    "import_size_mechanism_tests.md": Path("import_size_mechanism_tests/import_size_mechanism_tests.md"),
    "import_size_mechanism_adversarial_review.md": Path("import_size_mechanism_tests/adversarial_review.md"),
}

CONTRIBUTIONS_FIGURE_FILES = {
    "contributions_partner_gini_trend": Path("exercise_01_figures/partner_gini_trend_rd2_countries.png"),
    "contributions_partner_gini_country_slope_distribution": Path(
        "partner_gini_stability_figures/country_slope_distribution.png"
    ),
    "contributions_wr_import_population_partial": Path("contributions_figures/wr_import_population_partial.png"),
    "contributions_wr_import_gdppc_partial": Path("contributions_figures/wr_import_gdppc_partial.png"),
}

EX12_EXTENSIVE_TABLE_FILES = {
    "ex12_extensive_country_year": Path("exercise_12_extensive_margin_tables/extensive_margin_country_year.csv"),
    "ex12_extensive_latest": Path("exercise_12_extensive_margin_tables/extensive_margin_latest.csv"),
    "ex12_extensive_summary": Path("exercise_12_extensive_margin_tables/extensive_margin_summary.csv"),
    "ex12_extensive_country_weighted_summary": Path(
        "exercise_12_extensive_margin_tables/extensive_margin_country_weighted_summary.csv"
    ),
    "ex12_extensive_overlapping_robustness": Path("exercise_12_extensive_margin_tables/extensive_margin_overlapping_robustness.csv"),
    "ex12_extensive_product_entry_robustness": Path("exercise_12_extensive_margin_tables/extensive_margin_product_entry_robustness.csv"),
}

EX12_EXTENSIVE_DOWNLOAD_FILENAMES = {
    "exercise_12_extensive_margin_country_year.csv": "ex12_extensive_country_year",
    "exercise_12_extensive_margin_latest.csv": "ex12_extensive_latest",
    "exercise_12_extensive_margin_summary.csv": "ex12_extensive_summary",
    "exercise_12_extensive_margin_country_weighted_summary.csv": "ex12_extensive_country_weighted_summary",
    "exercise_12_extensive_margin_overlapping_robustness.csv": "ex12_extensive_overlapping_robustness",
    "exercise_12_extensive_margin_product_entry_robustness.csv": "ex12_extensive_product_entry_robustness",
}

EX12_EV_HS4_TABLE_FILES = {
    "ex12_ev_hs4_country_window": Path("exercise_12_ev_hs4_expansion_tables/ev_hs4_country_window_decomposition.csv"),
    "ex12_ev_hs4_partner_spread": Path("exercise_12_ev_hs4_expansion_tables/ev_hs4_partner_spread_country_window.csv"),
    "ex12_ev_hs4_combined_country_window": Path("exercise_12_ev_hs4_expansion_tables/ev_hs4_combined_country_window_decomposition.csv"),
    "ex12_ev_hs4_combined_pooled_summary": Path("exercise_12_ev_hs4_expansion_tables/ev_hs4_combined_pooled_summary.csv"),
    "ex12_ev_hs4_combined_equal_country_summary": Path("exercise_12_ev_hs4_expansion_tables/ev_hs4_combined_equal_country_summary.csv"),
    "ex12_ev_hs4_combined_latest_5y": Path("exercise_12_ev_hs4_expansion_tables/ev_hs4_combined_latest_5y_country.csv"),
    "ex12_ev_hs4_pooled_summary": Path("exercise_12_ev_hs4_expansion_tables/ev_hs4_pooled_summary.csv"),
    "ex12_ev_hs4_equal_country_summary": Path("exercise_12_ev_hs4_expansion_tables/ev_hs4_equal_country_summary.csv"),
    "ex12_ev_hs4_latest_5y": Path("exercise_12_ev_hs4_expansion_tables/ev_hs4_latest_5y_country.csv"),
    "ex12_ev_hs4_bottom10_robustness": Path("exercise_12_ev_hs4_expansion_tables/ev_hs4_bottom10_robustness.csv"),
    "ex12_ev_hs4_bottom10_robustness_summary": Path(
        "exercise_12_ev_hs4_expansion_tables/ev_hs4_bottom10_robustness_summary.csv"
    ),
}

EX12_EV_HS4_DOWNLOAD_FILENAMES = {
    "exercise_12_ev_hs4_country_window_decomposition.csv": "ex12_ev_hs4_country_window",
    "exercise_12_ev_hs4_partner_spread_country_window.csv": "ex12_ev_hs4_partner_spread",
    "exercise_12_ev_hs4_combined_country_window_decomposition.csv": "ex12_ev_hs4_combined_country_window",
    "exercise_12_ev_hs4_combined_pooled_summary.csv": "ex12_ev_hs4_combined_pooled_summary",
    "exercise_12_ev_hs4_combined_equal_country_summary.csv": "ex12_ev_hs4_combined_equal_country_summary",
    "exercise_12_ev_hs4_combined_latest_5y_country.csv": "ex12_ev_hs4_combined_latest_5y",
    "exercise_12_ev_hs4_pooled_summary.csv": "ex12_ev_hs4_pooled_summary",
    "exercise_12_ev_hs4_equal_country_summary.csv": "ex12_ev_hs4_equal_country_summary",
    "exercise_12_ev_hs4_latest_5y_country.csv": "ex12_ev_hs4_latest_5y",
    "exercise_12_ev_hs4_bottom10_robustness.csv": "ex12_ev_hs4_bottom10_robustness",
    "exercise_12_ev_hs4_bottom10_robustness_summary.csv": "ex12_ev_hs4_bottom10_robustness_summary",
}

EX12_EV_HS6_HARMONIZED_TABLE_FILES = {
    "ex12_ev_hs6_harmonized_country_window": Path(
        "exercise_12_ev_hs6_harmonized_expansion_tables/ev_hs6_harmonized_country_window_decomposition.csv"
    ),
    "ex12_ev_hs6_harmonized_partner_spread": Path(
        "exercise_12_ev_hs6_harmonized_expansion_tables/ev_hs6_harmonized_partner_spread_country_window.csv"
    ),
    "ex12_ev_hs6_harmonized_combined_country_window": Path(
        "exercise_12_ev_hs6_harmonized_expansion_tables/ev_hs6_harmonized_combined_country_window_decomposition.csv"
    ),
    "ex12_ev_hs6_harmonized_combined_pooled_summary": Path(
        "exercise_12_ev_hs6_harmonized_expansion_tables/ev_hs6_harmonized_combined_pooled_summary.csv"
    ),
    "ex12_ev_hs6_harmonized_combined_equal_country_summary": Path(
        "exercise_12_ev_hs6_harmonized_expansion_tables/ev_hs6_harmonized_combined_equal_country_summary.csv"
    ),
    "ex12_ev_hs6_harmonized_combined_latest_5y": Path(
        "exercise_12_ev_hs6_harmonized_expansion_tables/ev_hs6_harmonized_combined_latest_5y_country.csv"
    ),
    "ex12_ev_hs6_harmonized_pooled_summary": Path(
        "exercise_12_ev_hs6_harmonized_expansion_tables/ev_hs6_harmonized_pooled_summary.csv"
    ),
    "ex12_ev_hs6_harmonized_equal_country_summary": Path(
        "exercise_12_ev_hs6_harmonized_expansion_tables/ev_hs6_harmonized_equal_country_summary.csv"
    ),
    "ex12_ev_hs6_harmonized_latest_5y": Path(
        "exercise_12_ev_hs6_harmonized_expansion_tables/ev_hs6_harmonized_latest_5y_country.csv"
    ),
    "ex12_ev_hs6_harmonized_bottom10_robustness": Path(
        "exercise_12_ev_hs6_harmonized_expansion_tables/ev_hs6_harmonized_bottom10_robustness.csv"
    ),
    "ex12_ev_hs6_harmonized_bottom10_robustness_summary": Path(
        "exercise_12_ev_hs6_harmonized_expansion_tables/ev_hs6_harmonized_bottom10_robustness_summary.csv"
    ),
}

EX12_EV_HS6_HARMONIZED_DOWNLOAD_FILENAMES = {
    "exercise_12_ev_hs6_harmonized_country_window_decomposition.csv": "ex12_ev_hs6_harmonized_country_window",
    "exercise_12_ev_hs6_harmonized_partner_spread_country_window.csv": "ex12_ev_hs6_harmonized_partner_spread",
    "exercise_12_ev_hs6_harmonized_combined_country_window_decomposition.csv": (
        "ex12_ev_hs6_harmonized_combined_country_window"
    ),
    "exercise_12_ev_hs6_harmonized_combined_pooled_summary.csv": (
        "ex12_ev_hs6_harmonized_combined_pooled_summary"
    ),
    "exercise_12_ev_hs6_harmonized_combined_equal_country_summary.csv": (
        "ex12_ev_hs6_harmonized_combined_equal_country_summary"
    ),
    "exercise_12_ev_hs6_harmonized_combined_latest_5y_country.csv": (
        "ex12_ev_hs6_harmonized_combined_latest_5y"
    ),
    "exercise_12_ev_hs6_harmonized_pooled_summary.csv": "ex12_ev_hs6_harmonized_pooled_summary",
    "exercise_12_ev_hs6_harmonized_equal_country_summary.csv": "ex12_ev_hs6_harmonized_equal_country_summary",
    "exercise_12_ev_hs6_harmonized_latest_5y_country.csv": "ex12_ev_hs6_harmonized_latest_5y",
    "exercise_12_ev_hs6_harmonized_bottom10_robustness.csv": "ex12_ev_hs6_harmonized_bottom10_robustness",
    "exercise_12_ev_hs6_harmonized_bottom10_robustness_summary.csv": (
        "ex12_ev_hs6_harmonized_bottom10_robustness_summary"
    ),
}

CADOT_HUMP_TABLE_FILES = {
    "cadot_hump_country_year_panel": Path("cadot_hump_tribunal_tables/cadot_hump_country_year_panel.csv"),
    "cadot_hump_sample_diagnostics": Path("cadot_hump_tribunal_tables/cadot_hump_sample_diagnostics.csv"),
    "cadot_hump_models": Path("cadot_hump_tribunal_tables/cadot_hump_models.csv"),
    "cadot_mechanical_variant_models": Path("cadot_hump_tribunal_tables/mechanical_variant_models.csv"),
    "cadot_mechanism_scorecard_summary": Path("cadot_hump_tribunal_tables/mechanism_scorecard_summary.csv"),
    "cadot_reconcentration_episode_scorecard": Path("cadot_hump_tribunal_tables/reconcentration_episode_scorecard.csv"),
    "cadot_old_cone_exit_models": Path("cadot_hump_tribunal_tables/old_cone_exit_models.csv"),
    "cadot_old_cone_channel_summary": Path("cadot_hump_tribunal_tables/old_cone_channel_summary.csv"),
    "cadot_old_cone_exit_by_mismatch_decile": Path("cadot_hump_tribunal_tables/old_cone_exit_by_mismatch_decile.csv"),
    "cadot_commodity_mechanism_panel": Path("cadot_hump_tribunal_tables/commodity_mechanism_panel.csv"),
    "cadot_mechanical_common_sample_panel": Path("cadot_hump_tribunal_tables/mechanical_common_sample_panel.csv"),
    "cadot_ppp_hump_summary": Path("ppp_hump_regression_tables/ppp_hump_regression_summary.csv"),
    "cadot_ppp_country_fe_robustness": Path("ppp_hump_regression_tables/ppp_hump_country_fe_robustness.csv"),
}

CADOT_HUMP_FIGURE_FILES = {
    "cadot_hump_curve": Path("cadot_hump_tribunal_figures/cadot_hump_curve.png"),
    "cadot_mechanism_scorecard": Path("cadot_hump_tribunal_figures/mechanism_scorecard.png"),
    "cadot_mechanical_robustness_ladder": Path("cadot_hump_tribunal_figures/mechanical_robustness_ladder.png"),
    "cadot_old_cone_exit_plot": Path("cadot_hump_tribunal_figures/old_cone_exit_plot.png"),
    "cadot_ppp_hump_level": Path("ppp_hump_regression_figures/ppp_hump_diagnostics_level_ppp_five_outcomes.png"),
    "cadot_ppp_hump_log": Path("ppp_hump_regression_figures/ppp_hump_diagnostics_log_ppp_five_outcomes.png"),
}

CADOT_HUMP_DOWNLOAD_FILENAMES = {
    "cadot_hump_country_year_panel.csv": "cadot_hump_country_year_panel",
    "cadot_hump_sample_diagnostics.csv": "cadot_hump_sample_diagnostics",
    "cadot_hump_models.csv": "cadot_hump_models",
    "cadot_mechanical_variant_models.csv": "cadot_mechanical_variant_models",
    "cadot_mechanism_scorecard_summary.csv": "cadot_mechanism_scorecard_summary",
    "cadot_reconcentration_episode_scorecard.csv": "cadot_reconcentration_episode_scorecard",
    "cadot_old_cone_exit_models.csv": "cadot_old_cone_exit_models",
    "cadot_old_cone_channel_summary.csv": "cadot_old_cone_channel_summary",
    "cadot_old_cone_exit_by_mismatch_decile.csv": "cadot_old_cone_exit_by_mismatch_decile",
    "cadot_commodity_mechanism_panel.csv": "cadot_commodity_mechanism_panel",
    "cadot_mechanical_common_sample_panel.csv": "cadot_mechanical_common_sample_panel",
    "ppp_hump_regression_summary.csv": "cadot_ppp_hump_summary",
    "ppp_hump_country_fe_robustness.csv": "cadot_ppp_country_fe_robustness",
}

CADOT_BROAD_PPP_TABLE_DIR = (
    ROOT / "results" / "samples" / "cadot_broad_156" / "cadot_broad_ppp_hump_regression_tables"
)
CADOT_BROAD_PPP_FIGURE_DIR = (
    ROOT / "results" / "samples" / "cadot_broad_156" / "cadot_broad_ppp_hump_regression_figures"
)
CADOT_BROAD_PPP_TABLE_FILES = {
    "cadot_broad_ppp_hump_summary": CADOT_BROAD_PPP_TABLE_DIR / "ppp_hump_regression_summary.csv",
    "cadot_broad_ppp_sample_attrition": CADOT_BROAD_PPP_TABLE_DIR / "ppp_hump_sample_attrition.csv",
    "cadot_broad_ppp_independent_reestimate_checks": (
        CADOT_BROAD_PPP_TABLE_DIR / "ppp_hump_independent_reestimate_checks.csv"
    ),
}
CADOT_BROAD_PPP_EXTRA_DOWNLOADS = {
    "cadot_broad_ppp_hump_diagnostics.json": CADOT_BROAD_PPP_TABLE_DIR / "ppp_hump_diagnostics.json",
    "cadot_broad_ppp_adversarial_review.md": CADOT_BROAD_PPP_TABLE_DIR / "adversarial_review.md",
}
CADOT_BROAD_PPP_DOWNLOAD_FILENAMES = {
    "cadot_broad_ppp_hump_regression_summary.csv": "cadot_broad_ppp_hump_summary",
    "cadot_broad_ppp_sample_attrition.csv": "cadot_broad_ppp_sample_attrition",
    "cadot_broad_ppp_independent_reestimate_checks.csv": "cadot_broad_ppp_independent_reestimate_checks",
}
CADOT_BROAD_PPP_FIGURE_FILES = {
    "cadot_broad_ppp_hump_level": CADOT_BROAD_PPP_FIGURE_DIR / "ppp_hump_diagnostics_level_ppp_five_outcomes.png",
    "cadot_broad_ppp_hump_log": CADOT_BROAD_PPP_FIGURE_DIR / "ppp_hump_diagnostics_log_ppp_five_outcomes.png",
}

CADOT_BROAD_TRIBUNAL_DIR = (
    ROOT / "results" / "samples" / "cadot_broad_156" / "cadot_hump_tribunal_tables"
)
CADOT_BROAD_TRIBUNAL_FIGURE_DIR = (
    ROOT / "results" / "samples" / "cadot_broad_156" / "cadot_hump_tribunal_figures"
)
CADOT_INTEGRATED_TABLE_FILES = {
    "cadot_production_core_models": (
        ROOT
        / "results"
        / "prof_p_replication"
        / "cadot_production_core_sensitivity"
        / "production_core_model_summary.csv"
    ),
    "cadot_production_core_country_classification": (
        ROOT
        / "results"
        / "prof_p_replication"
        / "cadot_production_core_sensitivity"
        / "country_exclusion_classification.csv"
    ),
    "cadot_between_within_variance": (
        ROOT
        / "results"
        / "prof_p_replication"
        / "cadot_between_country_diagnostics"
        / "between_within_variance_decomposition.csv"
    ),
    "cadot_historical_preferred_within": (
        ROOT
        / "results"
        / "historical_partner_concentration"
        / "advisor_preferred_within_results.csv"
    ),
    "cadot_historical_model_summary": (
        ROOT / "results" / "historical_partner_concentration" / "cadot_model_summary.csv"
    ),
    "cadot_broad_mechanism_summary": CADOT_BROAD_TRIBUNAL_DIR / "mechanism_scorecard_summary.csv",
    "cadot_broad_old_cone_models": CADOT_BROAD_TRIBUNAL_DIR / "old_cone_exit_models.csv",
    "cadot_broad_tribunal_validation": CADOT_BROAD_TRIBUNAL_DIR / "validation_checks.csv",
}
CADOT_INTEGRATED_FIGURE_FILES = {
    "cadot_export_gini_theil_fits": (
        CADOT_BROAD_PPP_FIGURE_DIR / "export_gini_theil_linear_quadratic_lowess.png"
    ),
    "cadot_historical_baseline_u_shape": (
        ROOT
        / "results"
        / "historical_partner_concentration"
        / "figures"
        / "advisor"
        / "baseline_u_shape_tests.png"
    ),
    "cadot_historical_sensitivity": (
        ROOT
        / "results"
        / "historical_partner_concentration"
        / "figures"
        / "advisor"
        / "within_u_shape_sensitivity.png"
    ),
    "cadot_broad_mechanism_scorecard": (
        CADOT_BROAD_TRIBUNAL_FIGURE_DIR / "mechanism_scorecard.png"
    ),
    "cadot_broad_old_cone_exit": (
        CADOT_BROAD_TRIBUNAL_FIGURE_DIR / "old_cone_exit_plot.png"
    ),
}
CADOT_PAGE_ASSET_VERSION = "broad156-20260621b"
CADOT_INTEGRATED_EXTRA_DOWNLOADS = {
    "cadot-replication.md": ROOT / "cadot-replication.md",
    "cadot_final_interpretation_report.md": (
        ROOT / "results" / "prof_p_replication" / "cadot_final_interpretation_report.md"
    ),
    "cadot_production_core_sensitivity.md": (
        ROOT / "results" / "prof_p_replication" / "cadot_production_core_sensitivity.md"
    ),
    "historical_partner_concentration_advisor_memo.md": (
        ROOT
        / "results"
        / "historical_partner_concentration"
        / "historical_partner_concentration_advisor_memo.md"
    ),
    "historical_partner_concentration_adversarial_review.md": (
        ROOT / "results" / "historical_partner_concentration" / "adversarial_review.md"
    ),
    "historical_partner_concentration_run_manifest.json": (
        ROOT / "results" / "historical_partner_concentration" / "run_manifest.json"
    ),
    "cadot_production_core_manifest.json": (
        ROOT
        / "results"
        / "prof_p_replication"
        / "cadot_production_core_sensitivity"
        / "manifest.json"
    ),
    "cadot_broad_tribunal_adversarial_review.md": (
        ROOT
        / "results"
        / "samples"
        / "cadot_broad_156"
        / "cadot_hump_tribunal_adversarial_review.md"
    ),
    "cadot_broad_tribunal_run_manifest.json": (
        ROOT
        / "results"
        / "samples"
        / "cadot_broad_156"
        / "run_manifest_cadot_hump_tribunal.json"
    ),
}
CADOT_INTEGRATED_DOWNLOAD_FILENAMES = {
    "cadot_production_core_model_summary.csv": "cadot_production_core_models",
    "cadot_production_core_country_classification.csv": (
        "cadot_production_core_country_classification"
    ),
    "cadot_between_within_variance_decomposition.csv": "cadot_between_within_variance",
    "historical_partner_preferred_within_results.csv": "cadot_historical_preferred_within",
    "historical_partner_cadot_model_summary.csv": "cadot_historical_model_summary",
    "cadot_broad_mechanism_scorecard_summary.csv": "cadot_broad_mechanism_summary",
    "cadot_broad_old_cone_exit_models.csv": "cadot_broad_old_cone_models",
    "cadot_broad_tribunal_validation_checks.csv": "cadot_broad_tribunal_validation",
}

IMPORT_ENERGY_GINI_TABLE_FILES = {
    "energy_gini_driver_classification_balanced": Path(
        "import_energy_gini_diagnostics/ex_energy_rank_bucket_gini_driver_classification_balanced_2000_2024.csv"
    ),
    "energy_gini_driver_summary_balanced": Path(
        "import_energy_gini_diagnostics/ex_energy_rank_bucket_gini_driver_summary_balanced_2000_2024.csv"
    ),
    "energy_gini_driver_classification_full": Path(
        "import_energy_gini_diagnostics/ex_energy_rank_bucket_gini_driver_classification_full_available.csv"
    ),
    "nonenergy_rank_decomposition_balanced": Path(
        "import_energy_gini_diagnostics/nonenergy_import_rank_decomposition_start_mid_end_balanced_2000_2024_all_countries.csv"
    ),
    "nonenergy_top_products_balanced": Path(
        "import_energy_gini_diagnostics/top10_nonenergy_import_goods_start_mid_end_balanced_2000_2024_all_countries.csv"
    ),
}

IMPORT_ENERGY_GINI_DOWNLOAD_FILENAMES = {
    "ex_energy_rank_bucket_gini_driver_classification_balanced_2000_2024.csv": (
        "energy_gini_driver_classification_balanced"
    ),
    "ex_energy_rank_bucket_gini_driver_summary_balanced_2000_2024.csv": "energy_gini_driver_summary_balanced",
    "ex_energy_rank_bucket_gini_driver_classification_full_available.csv": "energy_gini_driver_classification_full",
    "nonenergy_import_rank_decomposition_start_mid_end_balanced_2000_2024_all_countries.csv": (
        "nonenergy_rank_decomposition_balanced"
    ),
    "top10_nonenergy_import_goods_start_mid_end_balanced_2000_2024_all_countries.csv": (
        "nonenergy_top_products_balanced"
    ),
}

THREE_METRIC_TABLE_FILES = {
    "three_metric_validation": Path("three_metric_tables/validation_checks.csv"),
    "three_metric_headline": Path("three_metric_tables/metric_headline_product_panel.csv"),
    "three_metric_yearly": Path("three_metric_tables/metric_yearly_summary.csv"),
    "three_metric_rankings": Path("three_metric_tables/metric_latest_rankings.csv"),
    "three_metric_ex02": Path("three_metric_tables/exercise_02_bucket_growth_summary.csv"),
    "three_metric_ex03": Path("three_metric_tables/exercise_03_import_bin_metrics.csv"),
    "three_metric_ex04": Path("three_metric_tables/exercise_04_dominant_supplier_summary.csv"),
    "three_metric_ex06": Path("three_metric_tables/exercise_06_exclusion_metrics.csv"),
    "three_metric_ex10": Path("three_metric_tables/exercise_10_random_benchmarks.csv"),
    "three_metric_ex11": Path("three_metric_tables/exercise_11_top_product_loo_contributions.csv"),
    "three_metric_ex12": Path("three_metric_tables/exercise_12_growth_decomposition_summary.csv"),
}

THREE_METRIC_DOWNLOAD_FILES = {
    "cadot_three_metric_manifest.json": Path("three_metric_tables/cadot_three_metric_manifest.json"),
    "cadot_three_metric_methods.md": Path("three_metric_tables/cadot_three_metric_methods.md"),
    "validation_checks.csv": Path("three_metric_tables/validation_checks.csv"),
    "concentration_metric_all_years.csv": Path("three_metric_tables/concentration_metric_all_years.csv"),
    "metric_headline_product_panel.csv": Path("three_metric_tables/metric_headline_product_panel.csv"),
    "metric_yearly_summary.csv": Path("three_metric_tables/metric_yearly_summary.csv"),
    "metric_latest_rankings.csv": Path("three_metric_tables/metric_latest_rankings.csv"),
    "sample_attrition_by_reporter_flow.csv": Path("three_metric_tables/sample_attrition_by_reporter_flow.csv"),
    "product_universe.csv": Path("three_metric_tables/product_universe.csv"),
    "exercise_02_bucket_growth_summary.csv": Path("three_metric_tables/exercise_02_bucket_growth_summary.csv"),
    "exercise_03_import_bin_metrics.csv": Path("three_metric_tables/exercise_03_import_bin_metrics.csv"),
    "exercise_04_dominant_supplier_summary.csv": Path("three_metric_tables/exercise_04_dominant_supplier_summary.csv"),
    "exercise_06_exclusion_metrics.csv": Path("three_metric_tables/exercise_06_exclusion_metrics.csv"),
    "exercise_10_random_benchmarks.csv": Path("three_metric_tables/exercise_10_random_benchmarks.csv"),
    "exercise_11_top_product_loo_contributions.csv.gz": Path("three_metric_tables/exercise_11_top_product_loo_contributions.csv.gz"),
    "exercise_12_growth_decomposition_summary.csv": Path("three_metric_tables/exercise_12_growth_decomposition_summary.csv"),
    "three_metric_adversarial_review.md": Path("three_metric_tables/adversarial_review.md"),
    "nonenergy_import_metric_annual.csv": Path("three_metric_tables/nonenergy_import_metric_annual.csv"),
    "nonenergy_import_reporter_coverage.csv": Path(
        "three_metric_tables/nonenergy_import_reporter_coverage.csv"
    ),
    "nonenergy_import_rank_bucket_snapshots.csv": Path(
        "three_metric_tables/nonenergy_import_rank_bucket_snapshots.csv"
    ),
    "nonenergy_import_top_products_snapshots.csv": Path(
        "three_metric_tables/nonenergy_import_top_products_snapshots.csv"
    ),
    "nonenergy_import_rank_bucket_drivers.csv": Path(
        "three_metric_tables/nonenergy_import_rank_bucket_drivers.csv"
    ),
    "nonenergy_world_hs1992_product_universe.csv": Path(
        "three_metric_tables/nonenergy_world_hs1992_product_universe.csv"
    ),
    "nonenergy_visualization_validation_checks.csv": Path(
        "three_metric_tables/nonenergy_visualization_validation_checks.csv"
    ),
    "nonenergy_visualization_manifest.json": Path(
        "three_metric_tables/nonenergy_visualization_manifest.json"
    ),
    "archived_extension_parity_report.md": Path(
        "three_metric_tables/archived_extension_parity_report.md"
    ),
    "nonenergy_visualization_adversarial_review.md": Path(
        "three_metric_tables/nonenergy_visualization_adversarial_review.md"
    ),
    "world_large_product_exposure_spearman_summary.csv": Path(
        "world_large_product_exposure_tables/world_large_product_exposure_spearman_summary.csv"
    ),
    "world_large_product_exposure_yearly_spearman.csv": Path(
        "world_large_product_exposure_tables/world_large_product_exposure_yearly_spearman.csv"
    ),
    "world_large_product_exposure_models.csv": Path(
        "world_large_product_exposure_tables/world_large_product_exposure_models.csv"
    ),
    "world_large_product_exposure_diagnostics.csv": Path(
        "world_large_product_exposure_tables/world_large_product_exposure_diagnostics.csv"
    ),
    "world_large_product_exposure_validation_checks.csv": Path(
        "world_large_product_exposure_tables/world_large_product_exposure_validation_checks.csv"
    ),
    "world_large_product_exposure_reporter_coverage.csv": Path(
        "world_large_product_exposure_tables/world_large_product_exposure_reporter_coverage.csv"
    ),
    "world_large_product_exposure_fixed_country_2018_2024.csv": Path(
        "world_large_product_exposure_tables/world_large_product_exposure_fixed_country_2018_2024.csv"
    ),
    "world_large_product_exposure_fixed_country_2018_2024_summary.csv": Path(
        "world_large_product_exposure_tables/world_large_product_exposure_fixed_country_2018_2024_summary.csv"
    ),
    "world_large_product_exposure_leave_one_country_out.csv": Path(
        "world_large_product_exposure_tables/world_large_product_exposure_leave_one_country_out.csv"
    ),
    "world_large_product_exposure_variant_comparison.csv": Path(
        "world_large_product_exposure_tables/world_large_product_exposure_variant_comparison.csv"
    ),
    "world_large_product_exposure_country_commodity_shares.csv": Path(
        "world_large_product_exposure_tables/world_large_product_exposure_country_commodity_shares.csv"
    ),
    "world_large_product_exposure_top_change_contributors.csv": Path(
        "world_large_product_exposure_tables/world_large_product_exposure_top_change_contributors.csv"
    ),
    "world_large_product_exposure_product_mapping.csv": Path(
        "world_large_product_exposure_tables/world_large_product_exposure_product_mapping.csv"
    ),
    "world_large_product_exposure_panel.csv": Path(
        "world_large_product_exposure_tables/world_large_product_exposure_panel.csv"
    ),
    "world_large_product_exposure.md": Path(
        "world_large_product_exposure_tables/world_large_product_exposure.md"
    ),
    "run_manifest_world_large_product_exposure.json": Path(
        "world_large_product_exposure_tables/run_manifest_world_large_product_exposure.json"
    ),
    "world_large_product_exposure_adversarial_review.md": Path(
        "world_large_product_exposure_tables/adversarial_review.md"
    ),
}

THREE_METRIC_DEFINITIONS = {
    "gini": "Active-positive Gini over observed positive trade values.",
    "theil": "Fixed-universe Theil with inactive products represented through the flow-specific product universe.",
    "hhi": "Herfindahl-Hirschman index, the sum of squared item shares.",
}

EXERCISE_PAGE_SPECS = [
    {
        "short": "01",
        "title": "Exercise 1: Persistent Aggregate Concentration",
        "question": "Is trade concentration a persistent country-panel fact rather than a one-year cross-section artifact?",
        "supports": "Product, partner, and product-partner-cell concentration remain high across countries, flows, and years.",
        "weakens": "The high concentration pattern disappears once the sample is followed through time or measured with Theil/HHI.",
        "answer": "Use the Cadot-style Gini/Theil/HHI panel as the common headline panel; compare products, partners, and cells on common available rows.",
        "source": "metric_headline_product_panel.csv",
        "data_key": "headline",
        "figures": ["ex1_median_concentration_over_time", "ex1_import_vs_export_product_gini_over_time", "ex1_country_product_gini_lines"],
        "downloads": ["metric_headline_product_panel.csv", "metric_yearly_summary.csv", "metric_latest_rankings.csv"],
    },
    {
        "short": "02",
        "title": "Exercise 2: Concentration Buckets And Growth",
        "question": "Do high-concentration export states predict meaningfully different later export-growth paths?",
        "supports": "High-concentration buckets show systematically different later trade or active-product growth across metrics.",
        "weakens": "Bucket differences are small, unstable across metrics, or mostly sample-composition artifacts.",
        "answer": "Treat the evidence as descriptive: the page reports Gini, Theil, and HHI bucket summaries without causal interpretation.",
        "source": "exercise_02_bucket_growth_summary.csv",
        "data_key": "ex02",
        "figures": [],
        "downloads": ["exercise_02_bucket_growth_summary.csv"],
    },
    {
        "short": "03",
        "title": "Exercise 3: Import-Bin Concentration",
        "question": "Which import bins carry concentration: energy, intermediates, capital goods, or final consumption?",
        "supports": "Specific bins have high internal concentration and meaningful import-value shares across Gini, Theil, and HHI.",
        "weakens": "All bins look similar or concentrated bins are too small to matter.",
        "answer": "The import-bin tables show the same bins with Gini/Theil/HHI side by side after LT/HGL product harmonization.",
        "source": "exercise_03_import_bin_metrics.csv",
        "data_key": "ex03",
        "figures": ["ex3_value_share", "ex3_leave_one_out", "ex3_energy_total_share_hist", "ex3_intermediates_total_share_hist", "ex3_capital_goods_total_share_hist", "ex3_final_consumption_total_share_hist"],
        "downloads": ["exercise_03_import_bin_metrics.csv"],
    },
    {
        "short": "04",
        "title": "Exercise 4: Dominant Suppliers",
        "question": "How much import concentration reflects dominant source countries within products?",
        "supports": "Importer-product sourcing is dominated by one supplier and source HHI remains high in country-year summaries.",
        "weakens": "Supplier shares are diffuse within products or only globally concentrated in H2.4 rather than importer-specific.",
        "answer": "Exercise 4 remains country-specific; H2.4 is retained only as a clearly labeled global benchmark.",
        "source": "exercise_04_dominant_supplier_summary.csv",
        "data_key": "ex04",
        "figures": ["ex4_supplier_time", "ex4_supplier_distribution", "h24_importer_world_supplier_comparison", "ex4_partner_counterfactual_latest", "ex4_india_partner_counterfactual"],
        "downloads": ["exercise_04_dominant_supplier_summary.csv"],
    },
    {
        "short": "06",
        "title": "Exercise 6: HS2 Exclusion Sensitivity",
        "question": "Does concentration mostly disappear after removing obvious lumpy HS2 sectors?",
        "supports": "Gini, Theil, and HHI fall sharply after exclusions, relative to the trade share removed.",
        "weakens": "The metrics remain high after excluding oil, precious metals, aircraft, ships, and arms.",
        "answer": "The page shows before/after graphs and metric-specific exclusion sensitivity from the rerun.",
        "source": "exercise_06_exclusion_metrics.csv",
        "data_key": "ex06",
        "figures": ["ex6_before_after", "ex6_removed"],
        "downloads": ["exercise_06_exclusion_metrics.csv"],
    },
    {
        "short": "10",
        "title": "Exercise 10: Random Benchmarks",
        "question": "Is observed concentration higher than sparse-data or HS2-preserving random benchmarks?",
        "supports": "Actual Gini, Theil, and HHI sit well above simulated benchmark medians.",
        "weakens": "Actual metrics look close to random reallocations once active counts or HS2 structure are held fixed.",
        "answer": "The restored benchmark figures are paired with the rerun Gini/Theil/HHI benchmark table.",
        "source": "exercise_10_random_benchmarks.csv",
        "data_key": "ex10",
        "figures": ["ex10_actual_vs_benchmark", "ex10_percentile"],
        "downloads": ["exercise_10_random_benchmarks.csv"],
    },
    {
        "short": "11",
        "title": "Exercise 11: Leave-One-Out Product Contributions",
        "question": "Which products drive concentration, and do those concentration-driving imports map to exports?",
        "supports": "High-contribution products reveal meaningful concentration drivers across Gini, Theil, and HHI.",
        "weakens": "Leave-one-out contributions are tiny, unstable, or concentrated in uninterpretable residual codes.",
        "answer": "HS6 999999 remains excluded before conversion; tables show LT/HGL-weighted HS1992 product-family labels.",
        "source": "exercise_11_top_product_loo_contributions.csv.gz",
        "data_key": "ex11",
        "figures": ["ex11_coefficients", "ex11_export_linkage_4pct", "ex11_hs2_linkage_4pct", "ex11_india_supplier_scatter"],
        "downloads": ["exercise_11_top_product_loo_contributions.csv.gz"],
    },
    {
        "short": "12",
        "title": "Exercise 12: Growth Decomposition",
        "question": "Does later export growth come from new products, new partners, new cells, or incumbent growth?",
        "supports": "Growth decomposition patterns remain visible across base-concentration metrics and horizons.",
        "weakens": "The channel pattern disappears once base concentration is measured with Theil or HHI.",
        "answer": "The richer LT/HGL decomposition remains the headline; the rerun adds Gini/Theil/HHI base-bucket summaries.",
        "source": "exercise_12_growth_decomposition_summary.csv",
        "data_key": "ex12",
        "figures": [],
        "downloads": ["exercise_12_growth_decomposition_summary.csv"],
    },
]

SITE_COUNTRY_SAMPLE_CHOICES = ("prof_p_33", "world_broad", "rd2_countries", "cadot_broad_156")
ACTIVE_SITE_SAMPLE = "rd2_countries"
BASE_SOURCE_FILES = dict(SOURCE_FILES)
BASE_FIGURES = dict(FIGURES)
BASE_DOWNLOADS = dict(DOWNLOADS)
BASE_DOWNLOAD_SOURCE_KEYS = {filename: {path: key for key, path in BASE_SOURCE_FILES.items()}[path] for filename, path in BASE_DOWNLOADS.items()}
EXCLUDED_HS6_CODES = {"999999"}
CODE_COLUMNS = {"cmd_code", "item_code", "product_code", "hs6"}
HS6_PATTERN = re.compile(r"(\d{1,6})")


def include_prof_p_page() -> bool:
    return ACTIVE_SITE_SAMPLE == "prof_p_33"


def include_country_size_page() -> bool:
    return ACTIVE_SITE_SAMPLE == "rd2_countries"


def include_growth_effect_page() -> bool:
    return ACTIVE_SITE_SAMPLE == "rd2_countries"


def include_future_growth_page() -> bool:
    return ACTIVE_SITE_SAMPLE == "rd2_countries"


def include_partner_stability_page() -> bool:
    return ACTIVE_SITE_SAMPLE == "rd2_countries"


def include_methods_hs6_diagnostics() -> bool:
    return ACTIVE_SITE_SAMPLE == "rd2_countries"


def include_world_relative_product_gini() -> bool:
    return ACTIVE_SITE_SAMPLE == "rd2_countries"


def include_contributions_page() -> bool:
    return ACTIVE_SITE_SAMPLE == "rd2_countries"


def include_literature_takeaways_page() -> bool:
    return ACTIVE_SITE_SAMPLE == "rd2_countries"


def include_ex12_extensive_margin() -> bool:
    return ACTIVE_SITE_SAMPLE == "rd2_countries"


def include_ex12_ev_hs4_expansion() -> bool:
    return ACTIVE_SITE_SAMPLE == "rd2_countries"


def include_ex12_ev_hs6_harmonized_expansion() -> bool:
    return ACTIVE_SITE_SAMPLE == "rd2_countries"


def include_cadot_hump_page() -> bool:
    return ACTIVE_SITE_SAMPLE in {"rd2_countries", "cadot_broad_156"}


def is_world_relative_artifact_name(name: str) -> bool:
    name = str(name)
    return name.startswith(
        (
            "world_relative_product_gini",
            "world_weighted_product_gini",
            "world_relative_import_product_gini",
            "world_weighted_import_product_gini",
        )
    ) or (
        name
        in {
            "run_manifest_world_relative_product_gini.json",
            "run_manifest_world_relative_product_contributions.json",
            "run_manifest_world_relative_import_product_gini.json",
            "run_manifest_world_relative_import_product_contributions.json",
        }
    ) or (
        name.startswith(("world_relative_product_contribution", "world_relative_import_product_contribution"))
    )


def site_download_sources() -> dict[str, Path]:
    downloads = dict(DOWNLOADS)
    if include_prof_p_page():
        downloads.update(PROF_P_DOWNLOADS)
    return downloads


def sample_results_base(country_sample: str) -> Path:
    return ROOT / "results" if country_sample == "prof_p_33" else ROOT / "results" / "samples" / country_sample


def sample_result_path(path: Path, country_sample: str) -> Path:
    if country_sample == "prof_p_33":
        return path
    results_root = ROOT / "results"
    try:
        relative = path.relative_to(results_root)
    except ValueError:
        return path
    if relative.parts and relative.parts[0].startswith("h24_supplier_specialization"):
        return path
    return sample_results_base(country_sample) / relative


def country_size_source_paths(country_sample: str) -> dict[str, Path]:
    if country_sample != "rd2_countries":
        return {}
    base = sample_results_base(country_sample)
    return {name: base / relative for name, relative in COUNTRY_SIZE_TABLE_FILES.items()}


def country_size_figure_paths(country_sample: str) -> dict[str, Path]:
    if country_sample != "rd2_countries":
        return {}
    base = sample_results_base(country_sample)
    return {name: base / relative for name, relative in COUNTRY_SIZE_FIGURE_FILES.items()}


def growth_effect_source_paths(country_sample: str) -> dict[str, Path]:
    if country_sample != "rd2_countries":
        return {}
    base = sample_results_base(country_sample)
    return {name: base / relative for name, relative in GROWTH_EFFECT_TABLE_FILES.items()}


def growth_effect_figure_paths(country_sample: str) -> dict[str, Path]:
    if country_sample != "rd2_countries":
        return {}
    base = sample_results_base(country_sample)
    return {name: base / relative for name, relative in GROWTH_EFFECT_FIGURE_FILES.items()}


def future_growth_source_paths(country_sample: str) -> dict[str, Path]:
    if country_sample != "rd2_countries":
        return {}
    base = sample_results_base(country_sample)
    return {name: base / relative for name, relative in FUTURE_GROWTH_TABLE_FILES.items()}


def future_growth_figure_paths(country_sample: str) -> dict[str, Path]:
    if country_sample != "rd2_countries":
        return {}
    base = sample_results_base(country_sample)
    return {name: base / relative for name, relative in FUTURE_GROWTH_FIGURE_FILES.items()}


def partner_stability_source_paths(country_sample: str) -> dict[str, Path]:
    if country_sample != "rd2_countries":
        return {}
    base = sample_results_base(country_sample)
    return {name: base / relative for name, relative in PARTNER_STABILITY_TABLE_FILES.items()}


def partner_stability_figure_paths(country_sample: str) -> dict[str, Path]:
    if country_sample != "rd2_countries":
        return {}
    base = sample_results_base(country_sample)
    return {name: base / relative for name, relative in PARTNER_STABILITY_FIGURE_FILES.items()}


def methods_source_paths(country_sample: str) -> dict[str, Path]:
    if country_sample != "rd2_countries":
        return {}
    base = sample_results_base(country_sample)
    return {name: base / relative for name, relative in METHODS_TABLE_FILES.items()}


def methods_figure_paths(country_sample: str) -> dict[str, Path]:
    if country_sample != "rd2_countries":
        return {}
    base = sample_results_base(country_sample)
    return {name: base / relative for name, relative in METHODS_FIGURE_FILES.items()}


def world_relative_source_paths(country_sample: str) -> dict[str, Path]:
    if country_sample != "rd2_countries":
        return {}
    base = sample_results_base(country_sample)
    return {
        name: base / relative
        for name, relative in WORLD_RELATIVE_TABLE_FILES.items()
        if not name.endswith("_manifest")
    }


def world_relative_figure_paths(country_sample: str) -> dict[str, Path]:
    if country_sample != "rd2_countries":
        return {}
    base = sample_results_base(country_sample)
    return {name: base / relative for name, relative in WORLD_RELATIVE_FIGURE_FILES.items()}


def contributions_source_paths(country_sample: str) -> dict[str, Path]:
    if country_sample != "rd2_countries":
        return {}
    base = sample_results_base(country_sample)
    return {name: base / relative for name, relative in CONTRIBUTIONS_TABLE_FILES.items()}


def contributions_figure_paths(country_sample: str) -> dict[str, Path]:
    if country_sample != "rd2_countries":
        return {}
    base = sample_results_base(country_sample)
    return {name: base / relative for name, relative in CONTRIBUTIONS_FIGURE_FILES.items()}


def contributions_extra_download_paths(country_sample: str) -> dict[str, Path]:
    if country_sample != "rd2_countries":
        return {}
    base = sample_results_base(country_sample)
    return {name: base / relative for name, relative in CONTRIBUTIONS_EXTRA_DOWNLOAD_FILES.items()}


def ex12_extensive_source_paths(country_sample: str) -> dict[str, Path]:
    if country_sample != "rd2_countries":
        return {}
    base = sample_results_base(country_sample)
    return {name: base / relative for name, relative in EX12_EXTENSIVE_TABLE_FILES.items()}


def ex12_ev_hs4_source_paths(country_sample: str) -> dict[str, Path]:
    if country_sample != "rd2_countries":
        return {}
    base = sample_results_base(country_sample)
    return {name: base / relative for name, relative in EX12_EV_HS4_TABLE_FILES.items()}


def ex12_ev_hs6_harmonized_source_paths(country_sample: str) -> dict[str, Path]:
    if country_sample != "rd2_countries":
        return {}
    base = sample_results_base(country_sample)
    return {name: base / relative for name, relative in EX12_EV_HS6_HARMONIZED_TABLE_FILES.items()}


def cadot_hump_source_paths(country_sample: str) -> dict[str, Path]:
    if country_sample != "rd2_countries":
        return {}
    base = sample_results_base(country_sample)
    return {name: base / relative for name, relative in CADOT_HUMP_TABLE_FILES.items()}


def cadot_hump_figure_paths(country_sample: str) -> dict[str, Path]:
    if country_sample != "rd2_countries":
        return {}
    base = sample_results_base(country_sample)
    return {name: base / relative for name, relative in CADOT_HUMP_FIGURE_FILES.items()}


def import_energy_gini_source_paths(country_sample: str) -> dict[str, Path]:
    if country_sample != "rd2_countries":
        return {}
    base = sample_results_base(country_sample)
    return {name: base / relative for name, relative in IMPORT_ENERGY_GINI_TABLE_FILES.items()}


def three_metric_source_paths(country_sample: str) -> dict[str, Path]:
    if country_sample not in {"rd2_countries", "cadot_broad_156"}:
        return {}
    base = sample_results_base(country_sample)
    paths = {name: base / relative for name, relative in THREE_METRIC_TABLE_FILES.items()}
    if country_sample == "rd2_countries" and not all(path.exists() for path in paths.values()):
        return {}
    return paths


def three_metric_download_paths(country_sample: str) -> dict[str, Path]:
    if country_sample not in {"rd2_countries", "cadot_broad_156"}:
        return {}
    base = sample_results_base(country_sample)
    return {name: base / relative for name, relative in THREE_METRIC_DOWNLOAD_FILES.items()}


def configure_site_sample(country_sample: str) -> None:
    if country_sample not in SITE_COUNTRY_SAMPLE_CHOICES:
        raise ValueError(f"Unsupported country sample `{country_sample}`. Choose from: {', '.join(SITE_COUNTRY_SAMPLE_CHOICES)}")
    global ACTIVE_SITE_SAMPLE
    global SOURCE_FILES
    global FIGURES
    global DOWNLOADS
    ACTIVE_SITE_SAMPLE = country_sample
    SOURCE_FILES = {name: sample_result_path(path, country_sample) for name, path in BASE_SOURCE_FILES.items()}
    FIGURES = {name: sample_result_path(path, country_sample) for name, path in BASE_FIGURES.items()}
    DOWNLOADS = {filename: SOURCE_FILES[source_key] for filename, source_key in BASE_DOWNLOAD_SOURCE_KEYS.items()}
    if country_sample == "rd2_countries":
        DOWNLOADS["run_manifest_exercise_02_bucket_growth.json"] = (
            sample_results_base(country_sample) / "run_manifest_exercise_02_bucket_growth.json"
        )
    country_size_sources = country_size_source_paths(country_sample)
    if country_size_sources:
        SOURCE_FILES.update(country_size_sources)
        FIGURES.update(country_size_figure_paths(country_sample))
        DOWNLOADS.update(
            {
                filename: country_size_sources[source_key]
                for filename, source_key in COUNTRY_SIZE_DOWNLOAD_FILENAMES.items()
            }
        )
        DOWNLOADS.update(
            {
                filename: sample_results_base(country_sample) / relative
                for filename, relative in COUNTRY_SIZE_EXTRA_DOWNLOAD_FILES.items()
            }
        )
    growth_effect_sources = growth_effect_source_paths(country_sample)
    if growth_effect_sources:
        SOURCE_FILES.update(
            {
                key: value
                for key, value in growth_effect_sources.items()
                if key != "growth_effect_missing_controls"
            }
        )
        FIGURES.update(growth_effect_figure_paths(country_sample))
        DOWNLOADS.update(
            {
                filename: growth_effect_sources[source_key]
                for filename, source_key in GROWTH_EFFECT_DOWNLOAD_FILENAMES.items()
            }
        )
        DOWNLOADS["run_manifest_growth_effect.json"] = sample_results_base(country_sample) / "run_manifest_growth_effect.json"
    future_growth_sources = future_growth_source_paths(country_sample)
    if future_growth_sources:
        SOURCE_FILES.update(future_growth_sources)
        FIGURES.update(future_growth_figure_paths(country_sample))
        DOWNLOADS.update(
            {
                filename: future_growth_sources[source_key]
                for filename, source_key in FUTURE_GROWTH_DOWNLOAD_FILENAMES.items()
            }
        )
        DOWNLOADS["run_manifest_future_growth_concentration.json"] = (
            sample_results_base(country_sample) / "run_manifest_future_growth_concentration.json"
        )
    partner_stability_sources = partner_stability_source_paths(country_sample)
    if partner_stability_sources:
        SOURCE_FILES.update(partner_stability_sources)
        FIGURES.update(partner_stability_figure_paths(country_sample))
        DOWNLOADS.update(
            {
                filename: partner_stability_sources[source_key]
                for filename, source_key in PARTNER_STABILITY_DOWNLOAD_FILENAMES.items()
            }
        )
        DOWNLOADS["partner_gini_stability.md"] = sample_results_base(country_sample) / "partner_gini_stability.md"
        DOWNLOADS["partner_gini_stability_adversarial_review.md"] = (
            sample_results_base(country_sample) / "partner_gini_stability_adversarial_review.md"
        )
        DOWNLOADS["run_manifest_partner_gini_stability.json"] = (
            sample_results_base(country_sample) / "run_manifest_partner_gini_stability.json"
        )
    methods_sources = methods_source_paths(country_sample)
    if methods_sources:
        SOURCE_FILES.update(methods_sources)
        FIGURES.update(methods_figure_paths(country_sample))
        DOWNLOADS.update(
            {
                filename: methods_sources[source_key]
                for filename, source_key in METHODS_DOWNLOAD_FILENAMES.items()
            }
        )
    world_relative_sources = world_relative_source_paths(country_sample)
    if world_relative_sources:
        SOURCE_FILES.update(world_relative_sources)
        FIGURES.update(world_relative_figure_paths(country_sample))
        world_relative_download_sources = {
            name: sample_results_base(country_sample) / relative
            for name, relative in WORLD_RELATIVE_TABLE_FILES.items()
        }
        DOWNLOADS.update(
            {
                filename: world_relative_download_sources[source_key]
                for filename, source_key in WORLD_RELATIVE_DOWNLOAD_FILENAMES.items()
            }
        )
    contributions_sources = contributions_source_paths(country_sample)
    if contributions_sources:
        SOURCE_FILES.update(contributions_sources)
        FIGURES.update(contributions_figure_paths(country_sample))
        DOWNLOADS.update(
            {
                filename: contributions_sources[source_key]
                for filename, source_key in CONTRIBUTIONS_DOWNLOAD_FILENAMES.items()
            }
        )
        DOWNLOADS.update(contributions_extra_download_paths(country_sample))
    ex12_extensive_sources = ex12_extensive_source_paths(country_sample)
    if ex12_extensive_sources:
        SOURCE_FILES.update(ex12_extensive_sources)
        DOWNLOADS.update(
            {
                filename: ex12_extensive_sources[source_key]
                for filename, source_key in EX12_EXTENSIVE_DOWNLOAD_FILENAMES.items()
            }
        )
        DOWNLOADS["run_manifest_exercise_12_extensive_margin.json"] = (
            sample_results_base(country_sample) / "run_manifest_exercise_12_extensive_margin.json"
        )
    ex12_ev_hs4_sources = ex12_ev_hs4_source_paths(country_sample)
    if ex12_ev_hs4_sources:
        SOURCE_FILES.update(ex12_ev_hs4_sources)
        DOWNLOADS.update(
            {
                filename: ex12_ev_hs4_sources[source_key]
                for filename, source_key in EX12_EV_HS4_DOWNLOAD_FILENAMES.items()
            }
        )
        DOWNLOADS["run_manifest_exercise_12_ev_hs4_expansion.json"] = (
            sample_results_base(country_sample) / "run_manifest_exercise_12_ev_hs4_expansion.json"
        )
    ex12_ev_hs6_harmonized_sources = ex12_ev_hs6_harmonized_source_paths(country_sample)
    if ex12_ev_hs6_harmonized_sources:
        SOURCE_FILES.update(ex12_ev_hs6_harmonized_sources)
        DOWNLOADS.update(
            {
                filename: ex12_ev_hs6_harmonized_sources[source_key]
                for filename, source_key in EX12_EV_HS6_HARMONIZED_DOWNLOAD_FILENAMES.items()
            }
        )
        DOWNLOADS["run_manifest_exercise_12_ev_hs6_harmonized_expansion.json"] = (
            sample_results_base(country_sample) / "run_manifest_exercise_12_ev_hs6_harmonized_expansion.json"
        )
        lt_hgl_review = sample_results_base(country_sample) / "lt_hgl_hs1992_harmonization_adversarial_review.md"
        legacy_hs6_review = sample_results_base(country_sample) / "exercise_12_ev_hs6_harmonized_adversarial_review.md"
        if lt_hgl_review.exists():
            DOWNLOADS["lt_hgl_hs1992_harmonization_adversarial_review.md"] = lt_hgl_review
        elif legacy_hs6_review.exists():
            DOWNLOADS["exercise_12_ev_hs6_harmonized_adversarial_review.md"] = legacy_hs6_review
    cadot_hump_sources = cadot_hump_source_paths(country_sample)
    if cadot_hump_sources:
        SOURCE_FILES.update(cadot_hump_sources)
        FIGURES.update(cadot_hump_figure_paths(country_sample))
        DOWNLOADS.update(
            {
                filename: cadot_hump_sources[source_key]
                for filename, source_key in CADOT_HUMP_DOWNLOAD_FILENAMES.items()
            }
        )
        DOWNLOADS["run_manifest_cadot_hump_tribunal.json"] = (
            sample_results_base(country_sample) / "run_manifest_cadot_hump_tribunal.json"
        )
        DOWNLOADS["cadot_hump_tribunal_adversarial_review.md"] = (
            sample_results_base(country_sample) / "cadot_hump_tribunal_adversarial_review.md"
        )
        SOURCE_FILES.update(CADOT_BROAD_PPP_TABLE_FILES)
        FIGURES.update(CADOT_BROAD_PPP_FIGURE_FILES)
        DOWNLOADS.update(
            {
                filename: CADOT_BROAD_PPP_TABLE_FILES[source_key]
                for filename, source_key in CADOT_BROAD_PPP_DOWNLOAD_FILENAMES.items()
            }
        )
        DOWNLOADS.update(CADOT_BROAD_PPP_EXTRA_DOWNLOADS)
    if country_sample == "cadot_broad_156":
        SOURCE_FILES.update(CADOT_BROAD_PPP_TABLE_FILES)
        SOURCE_FILES.update(CADOT_INTEGRATED_TABLE_FILES)
        FIGURES.update(CADOT_BROAD_PPP_FIGURE_FILES)
        FIGURES.update(CADOT_INTEGRATED_FIGURE_FILES)
        DOWNLOADS.update(
            {
                filename: CADOT_BROAD_PPP_TABLE_FILES[source_key]
                for filename, source_key in CADOT_BROAD_PPP_DOWNLOAD_FILENAMES.items()
            }
        )
        DOWNLOADS.update(CADOT_BROAD_PPP_EXTRA_DOWNLOADS)
        DOWNLOADS.update(
            {
                filename: CADOT_INTEGRATED_TABLE_FILES[source_key]
                for filename, source_key in CADOT_INTEGRATED_DOWNLOAD_FILENAMES.items()
            }
        )
        DOWNLOADS.update(CADOT_INTEGRATED_EXTRA_DOWNLOADS)
    import_energy_gini_sources = import_energy_gini_source_paths(country_sample)
    if import_energy_gini_sources:
        SOURCE_FILES.update(import_energy_gini_sources)
        DOWNLOADS.update(
            {
                filename: import_energy_gini_sources[source_key]
                for filename, source_key in IMPORT_ENERGY_GINI_DOWNLOAD_FILENAMES.items()
            }
        )
    three_metric_sources = three_metric_source_paths(country_sample)
    if three_metric_sources:
        SOURCE_FILES.update(three_metric_sources)
        DOWNLOADS.update(three_metric_download_paths(country_sample))


FLOW_ORDER = ["Exports", "Imports"]
METRIC_LABELS = {
    "world_relative_product_gini": "World-Relative Product Gini (LT/HGL HS1992 products, balanced exports)",
    "world_relative_import_product_gini": "World-Relative Import Product Gini (LT/HGL HS1992 products, balanced imports)",
    "product_gini": "Active Product Gini (observed positive HS6 products)",
    "partner_gini": "Active Partner Gini (observed positive trade partners)",
    "product_partner_cell_gini": "Active Product-partner cell Gini (observed positive HS6-by-partner cells)",
}
EXCLUSION_LABELS = {
    "baseline": "Baseline",
    "oil_only": "No oil/mineral fuels",
    "oil_aircraft": "No oil + aircraft",
    "oil_aircraft_precious": "No oil + aircraft + precious metals",
    "full_exclusion": "No oil, precious metals, aircraft, ships, arms",
}
BIN_LABELS = {
    "capital_goods": "Capital goods",
    "energy": "Energy",
    "final_consumption": "Final consumption",
    "intermediates": "Intermediates",
    "unmapped_or_ambiguous": "Unmapped or ambiguous",
}
PRODUCT_SHORT_NAMES = {
    "080131": "Cashew nuts in shell",
    "151110": "Crude palm oil",
    "220710": "High-strength ethyl alcohol",
    "270119": "Coal",
    "270799": "Coal-tar distillation oils",
    "270900": "Crude petroleum",
    "271019": "Refined petroleum oils",
    "271111": "Liquefied natural gas",
    "271112": "Propane",
    "271113": "Butanes",
    "271311": "Petroleum coke, not calcined",
    "271320": "Petroleum bitumen",
    "300490": "Medicaments",
    "710231": "Unworked non-industrial diamonds",
    "710812": "Unwrought gold",
    "711319": "Precious-metal jewellery",
    "847130": "Portable computers/laptops",
    "847150": "Processing units/servers",
    "850440": "Static converters",
    "851713": "Smartphones",
    "851762": "Network/communication apparatus",
    "851779": "Telecom apparatus parts",
    "852589": "Television cameras",
    "854231": "Processor/controller integrated circuits",
    "870322": "Petrol cars, 1000-1500cc",
    "870323": "Petrol cars, 1500-3000cc",
    "870340": "Hybrid petrol-electric cars",
    "870380": "Electric vehicles",
    "880240": "Large aircraft",
}
DRIVER_BUCKET_LABELS = {
    "overweight_niche_product": "Overweight niche",
    "overweight_large_world_product": "Overweight large world",
    "overweight_mid_world_product": "Overweight mid-world",
    "missing_large_world_product": "Missing large world",
    "underweight_large_world_product": "Underweight large world",
    "underweight_other_product": "Underweight other",
    "near_world_share": "Near world share",
    "none": "None",
}
HS2_LABELS = {
    "01": "Live animals",
    "02": "Meat and edible meat offal",
    "03": "Fish and crustaceans",
    "04": "Dairy, eggs, honey, edible animal products",
    "05": "Other animal-origin products",
    "06": "Live trees and plants",
    "07": "Vegetables, roots, and tubers",
    "08": "Fruit and nuts",
    "09": "Coffee, tea, mate, and spices",
    "10": "Cereals",
    "11": "Milling products, malt, and starches",
    "12": "Oil seeds and medicinal plants",
    "13": "Lac, gums, resins, and saps",
    "14": "Vegetable plaiting materials",
    "15": "Animal, vegetable, or microbial fats and oils",
    "16": "Preparations of meat, fish, or crustaceans",
    "17": "Sugars and confectionery",
    "18": "Cocoa and cocoa preparations",
    "19": "Preparations of cereals, flour, or milk",
    "20": "Preparations of vegetables, fruit, or nuts",
    "21": "Miscellaneous edible preparations",
    "22": "Beverages, spirits, and vinegar",
    "23": "Food-industry residues and animal feed",
    "24": "Tobacco and manufactured tobacco substitutes",
    "25": "Salt, sulfur, earths, stone, lime, and cement",
    "26": "Ores, slag, and ash",
    "27": "Mineral fuels, oils, and petroleum",
    "28": "Inorganic chemicals",
    "29": "Organic chemicals",
    "30": "Pharmaceutical products",
    "31": "Fertilizers",
    "32": "Tanning, dyeing extracts, pigments, and paints",
    "33": "Essential oils, perfumes, and cosmetics",
    "34": "Soap, waxes, and cleaning preparations",
    "35": "Albuminoidal substances, glues, and enzymes",
    "36": "Explosives and pyrotechnics",
    "37": "Photographic and cinematographic goods",
    "38": "Miscellaneous chemical products",
    "39": "Plastics and articles thereof",
    "40": "Rubber and articles thereof",
    "41": "Raw hides, skins, and leather",
    "42": "Leather articles and travel goods",
    "43": "Furskins and artificial fur",
    "44": "Wood and wood articles",
    "45": "Cork and cork articles",
    "46": "Straw, esparto, and basketware",
    "47": "Pulp of wood and recovered paper",
    "48": "Paper and paperboard",
    "49": "Printed books and printed matter",
    "50": "Silk",
    "51": "Wool and animal hair",
    "52": "Cotton",
    "53": "Other vegetable textile fibers",
    "54": "Man-made filaments",
    "55": "Man-made staple fibers",
    "56": "Wadding, felt, nonwovens, yarns, and rope",
    "57": "Carpets and textile floor coverings",
    "58": "Special woven fabrics and lace",
    "59": "Impregnated or coated textile fabrics",
    "60": "Knitted or crocheted fabrics",
    "61": "Knitted or crocheted apparel",
    "62": "Non-knitted apparel",
    "63": "Other made-up textile articles",
    "64": "Footwear",
    "65": "Headgear",
    "66": "Umbrellas and walking sticks",
    "67": "Feathers, artificial flowers, and hair articles",
    "68": "Stone, plaster, cement, and asbestos articles",
    "69": "Ceramic products",
    "70": "Glass and glassware",
    "71": "Precious stones, metals, and jewelry",
    "72": "Iron and steel",
    "73": "Articles of iron or steel",
    "74": "Copper and articles thereof",
    "75": "Nickel and articles thereof",
    "76": "Aluminum and articles thereof",
    "78": "Lead and articles thereof",
    "79": "Zinc and articles thereof",
    "80": "Tin and articles thereof",
    "81": "Other base metals and cermets",
    "82": "Tools, cutlery, and base-metal implements",
    "83": "Miscellaneous base-metal articles",
    "84": "Machinery and mechanical appliances",
    "85": "Electrical machinery and equipment",
    "86": "Railway and tramway equipment",
    "87": "Vehicles and parts",
    "88": "Aircraft and spacecraft",
    "89": "Ships, boats, and floating structures",
    "90": "Optical, medical, and precision instruments",
    "91": "Clocks and watches",
    "92": "Musical instruments",
    "93": "Arms and ammunition",
    "94": "Furniture, bedding, and lamps",
    "95": "Toys, games, and sports equipment",
    "96": "Miscellaneous manufactured articles",
    "97": "Works of art and antiques",
    "98": "Special classification provisions",
    "99": "Commodities not elsewhere specified",
}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_hs6_series_for_validation(series: pd.Series) -> pd.Series:
    return series.astype("string").str.extract(HS6_PATTERN, expand=False).str.zfill(6)


def assert_csv_has_no_excluded_hs6(path: Path, label: str) -> None:
    if path.suffix.lower() != ".csv" and not path.name.lower().endswith(".csv.gz"):
        return
    header = pd.read_csv(path, nrows=0)
    code_cols = [col for col in header.columns if str(col) in CODE_COLUMNS]
    if not code_cols:
        return
    frame = pd.read_csv(path, usecols=code_cols, dtype={col: "string" for col in code_cols})
    for col in code_cols:
        if normalize_hs6_series_for_validation(frame[col]).isin(EXCLUDED_HS6_CODES).any():
            raise RuntimeError(f"{label} contains excluded HS6 code 999999 in column {col}: {path}")


def source_manifest_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[Path] = set()
    groups = [
        ("source", SOURCE_FILES),
        ("download", DOWNLOADS),
        ("figure", FIGURES),
    ]
    if include_prof_p_page():
        groups.extend([
            ("prof_p_source", PROF_P_SOURCE_FILES),
            ("prof_p_download", PROF_P_DOWNLOADS),
        ])
    for group, mapping in groups:
        for name, path in mapping.items():
            if path in seen and group != "download":
                continue
            seen.add(path)
            if not path.exists():
                raise FileNotFoundError(f"Required {group} artifact is missing: {path}")
            row_count = None
            columns = ""
            if path.suffix.lower() == ".csv":
                header = pd.read_csv(path, nrows=0)
                columns = "|".join(str(col) for col in header.columns)
                with path.open("rb") as fh:
                    line_count = sum(chunk.count(b"\n") for chunk in iter(lambda: fh.read(1024 * 1024), b""))
                row_count = max(line_count - 1, 0)
            rows.append(
                {
                    "group": group,
                    "name": name,
                    "path": str(path.relative_to(ROOT)),
                    "size_bytes": int(path.stat().st_size),
                    "mtime_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds"),
                    "sha256": file_sha256(path),
                    "row_count": row_count,
                    "columns": columns,
                }
            )
    return rows


def validate_publication_inputs() -> list[dict[str, Any]]:
    required = {**SOURCE_FILES, **DOWNLOADS}
    if include_prof_p_page():
        required.update(PROF_P_SOURCE_FILES)
        required.update(PROF_P_DOWNLOADS)
    for name, path in required.items():
        if not path.exists():
            raise FileNotFoundError(f"Required result artifact is missing for {ACTIVE_SITE_SAMPLE}: {path}")
        assert_csv_has_no_excluded_hs6(path, name)
    return source_manifest_rows()


def read_csv(name: str) -> pd.DataFrame:
    path = SOURCE_FILES[name]
    if not path.exists():
        raise FileNotFoundError(f"Required result table is missing: {path}")
    assert_csv_has_no_excluded_hs6(path, name)
    df = pd.read_csv(path)
    if df.empty:
        raise RuntimeError(f"Required result table has zero rows: {path}")
    return df


def read_prof_p_csv(name: str) -> pd.DataFrame:
    path = PROF_P_SOURCE_FILES[name]
    if not path.exists():
        raise FileNotFoundError(f"Required Prof P result table is missing: {path}")
    assert_csv_has_no_excluded_hs6(path, name)
    df = pd.read_csv(path)
    if df.empty:
        raise RuntimeError(f"Required Prof P result table has zero rows: {path}")
    return df


def require_columns(df: pd.DataFrame, name: str, columns: set[str]) -> None:
    missing = columns - set(df.columns)
    if missing:
        raise RuntimeError(f"{name} is missing columns: {sorted(missing)}")


def validation_passed(series: pd.Series) -> pd.Series:
    text = series.astype(str).str.strip().str.lower()
    return text.isin({"true", "1", "yes", "passed"})


def load_three_metric_data() -> dict[str, Any]:
    expected_reporters = {
        "rd2_countries": 60,
        "cadot_broad_156": 156,
    }.get(ACTIVE_SITE_SAMPLE)
    if expected_reporters is None:
        return {}
    manifest_path = DOWNLOADS.get("cadot_three_metric_manifest.json")
    review_path = DOWNLOADS.get("three_metric_adversarial_review.md")
    if manifest_path is None or review_path is None:
        if ACTIVE_SITE_SAMPLE == "rd2_countries":
            return {}
        raise FileNotFoundError(f"Required three-metric downloads are not configured for {ACTIVE_SITE_SAMPLE}.")
    if not manifest_path.exists():
        raise FileNotFoundError(f"Required three-metric manifest is missing: {manifest_path}")
    if not review_path.exists() or review_path.stat().st_size == 0:
        raise FileNotFoundError(f"Required three-metric adversarial review is missing: {review_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("country_sample") != ACTIVE_SITE_SAMPLE:
        raise RuntimeError(
            f"Website-facing three-metric artifacts must use {ACTIVE_SITE_SAMPLE}; "
            f"manifest reports {manifest.get('country_sample')!r}."
        )
    if int(manifest.get("selected_reporters") or 0) != expected_reporters:
        raise RuntimeError(
            f"{ACTIVE_SITE_SAMPLE} three-metric manifest must report {expected_reporters} selected reporters: {manifest_path}"
        )
    if ACTIVE_SITE_SAMPLE == "cadot_broad_156":
        required_manifest = {
            "product_id_mode": "harmonized_hs6_family",
            "harmonization_method": "lt_hgl_weighted_hs1992",
            "harmonization_target": "HS1992/H0",
            "fixed_universe_source": "world_broad",
        }
        mismatches = {
            key: {"expected": expected, "actual": manifest.get(key)}
            for key, expected in required_manifest.items()
            if manifest.get(key) != expected
        }
        if mismatches:
            raise RuntimeError(f"Cadot three-metric manifest has stale or non-harmonized metadata: {mismatches}")

    validation = read_csv("three_metric_validation")
    require_columns(validation, "Three-metric validation checks", {"check", "passed", "details"})
    failed = validation[~validation_passed(validation["passed"])]
    if not failed.empty:
        raise RuntimeError(f"Three-metric validation checks failed: {failed.to_dict(orient='records')}")

    headline = read_csv("three_metric_headline")
    yearly = read_csv("three_metric_yearly")
    rankings = read_csv("three_metric_rankings")
    ex02 = read_csv("three_metric_ex02")
    ex03 = read_csv("three_metric_ex03")
    ex04 = read_csv("three_metric_ex04")
    ex06 = read_csv("three_metric_ex06")
    ex10 = read_csv("three_metric_ex10")
    ex11 = read_csv("three_metric_ex11")
    ex12 = read_csv("three_metric_ex12")
    require_columns(headline, "Three-metric headline panel", {"country", "year", "flow", "dimension", "gini", "hhi"})
    require_columns(yearly, "Three-metric yearly summary", {"year", "flow", "dimension", "median_gini", "median_theil", "median_hhi"})
    require_columns(rankings, "Three-metric latest rankings", {"metric", "rank", "country", "year", "flow", "metric_value"})
    if "cmd_code" in ex11.columns:
        bad = normalize_hs6_series_for_validation(ex11["cmd_code"]).isin(EXCLUDED_HS6_CODES)
        if bad.any():
            raise RuntimeError("Three-metric Exercise 11 contains HS6 999999 in cmd_code.")
    if ACTIVE_SITE_SAMPLE == "cadot_broad_156":
        product_frames = {
            "headline": headline,
            "exercise_03": ex03,
            "exercise_04": ex04,
            "exercise_06": ex06,
            "exercise_10": ex10,
            "exercise_11": ex11,
        }
        for label, frame in product_frames.items():
            if "product_id" in frame.columns:
                product_ids = frame["product_id"].dropna().astype(str)
                if not product_ids.empty and not product_ids.str.startswith("HS1992:").all():
                    raise RuntimeError(f"{label} contains non-HS1992 product_id values.")
            if "product_label" in frame.columns:
                labels = frame["product_label"].dropna().astype(str)
                if not labels.empty and not labels.str.startswith("HS1992 ").all():
                    raise RuntimeError(f"{label} contains non-HS1992 product labels.")
    return {
        "manifest": manifest,
        "review_path": str(review_path.relative_to(ROOT)),
        "validation": clean_records(validation, list(validation.columns)),
        "headline": headline,
        "yearly": yearly,
        "rankings": rankings,
        "ex02": ex02,
        "ex03": ex03,
        "ex04": ex04,
        "ex06": ex06,
        "ex10": ex10,
        "ex11": ex11,
        "ex12": ex12,
    }


def clean_scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        if not math.isfinite(float(value)):
            return None
        return round(float(value), 12)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if pd.isna(value):
        return None
    return value


def clean_records(df: pd.DataFrame, columns: list[str]) -> list[dict[str, Any]]:
    safe = df.loc[:, columns].copy()
    rows: list[dict[str, Any]] = []
    for row in safe.to_dict(orient="records"):
        rows.append({key: clean_scalar(value) for key, value in row.items()})
    return rows


def clean_structure(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: clean_structure(val) for key, val in value.items()}
    if isinstance(value, list):
        return [clean_structure(item) for item in value]
    if isinstance(value, tuple):
        return [clean_structure(item) for item in value]
    return clean_scalar(value)


def round_map(row: pd.Series, columns: list[str]) -> dict[str, Any]:
    return {column: clean_scalar(row[column]) for column in columns}


def median_records(
    df: pd.DataFrame,
    group_cols: list[str],
    value_cols: list[str],
    rename: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    med = df.groupby(group_cols, dropna=False)[value_cols].median(numeric_only=True).reset_index()
    if rename:
        med = med.rename(columns=rename)
    return clean_records(med, list(med.columns))


def hs2_display_label(code: Any) -> str:
    clean_code = str(code).zfill(2)[:2]
    return f"HS{clean_code} - {HS2_LABELS.get(clean_code, 'HS chapter')}"


def hs2_linkage_summary(hs2: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
    if hs2.empty:
        return {"deciles": [], "chapters": []}

    work = hs2.copy()
    work["hs2"] = work["hs2"].astype(str).str.zfill(2).str[:2]
    work["hs2_label"] = work["hs2"].map(lambda code: HS2_LABELS.get(code, "HS chapter"))
    for column in [
        "hs2_product_loo_gini_sum",
        "hs2_export_any",
        "asinh_hs2_export_value",
        "hs2_export_value",
        "hs2_export_share",
        "hs2_import_value_share",
        "hs2_intermediate_import_share",
    ]:
        work[column] = pd.to_numeric(work[column], errors="coerce")
    work = work.replace([np.inf, -np.inf], np.nan).dropna(subset=["hs2_product_loo_gini_sum"])
    if work.empty:
        return {"deciles": [], "chapters": []}

    work["loo_decile"] = pd.qcut(work["hs2_product_loo_gini_sum"], 10, labels=False, duplicates="drop")
    work = work.dropna(subset=["loo_decile"]).copy()
    work["loo_decile"] = work["loo_decile"].astype(int) + 1

    decile_rows: list[dict[str, Any]] = []
    for decile, group in work.groupby("loo_decile", sort=True):
        chapter_rank = (
            group.groupby(["hs2", "hs2_label"], as_index=False)
            .agg(
                mean_import_share=("hs2_import_value_share", "mean"),
                observations=("hs2", "size"),
            )
            .sort_values(["mean_import_share", "observations", "hs2"], ascending=[False, False, True])
            .head(5)
        )
        top_chapters = "<br>".join(
            f"HS{row.hs2} {row.hs2_label} ({pct(row.mean_import_share)})"
            for row in chapter_rank.itertuples(index=False)
        )
        decile_rows.append(
            {
                "decile": int(decile),
                "mean_loo_gini": clean_scalar(group["hs2_product_loo_gini_sum"].mean()),
                "min_loo_gini": clean_scalar(group["hs2_product_loo_gini_sum"].min()),
                "max_loo_gini": clean_scalar(group["hs2_product_loo_gini_sum"].max()),
                "export_probability": clean_scalar(group["hs2_export_any"].mean()),
                "mean_asinh_export_value": clean_scalar(group["asinh_hs2_export_value"].mean()),
                "mean_export_value": clean_scalar(group["hs2_export_value"].mean()),
                "mean_export_share": clean_scalar(group["hs2_export_share"].mean()),
                "mean_import_share": clean_scalar(group["hs2_import_value_share"].mean()),
                "mean_intermediate_import_share": clean_scalar(group["hs2_intermediate_import_share"].mean()),
                "observations": int(len(group)),
                "chapter_count": int(group["hs2"].nunique()),
                "top_chapters": top_chapters,
            }
        )

    chapters = (
        work.groupby(["hs2", "hs2_label"], as_index=False)
        .agg(
            mean_loo_gini=("hs2_product_loo_gini_sum", "mean"),
            export_probability=("hs2_export_any", "mean"),
            mean_asinh_export_value=("asinh_hs2_export_value", "mean"),
            mean_export_value=("hs2_export_value", "mean"),
            mean_export_share=("hs2_export_share", "mean"),
            mean_import_share=("hs2_import_value_share", "mean"),
            mean_intermediate_import_share=("hs2_intermediate_import_share", "mean"),
            observations=("hs2", "size"),
            countries=("iso3", "nunique"),
            years=("year", "nunique"),
        )
        .sort_values("hs2")
    )
    chapters["display_label"] = chapters["hs2"].map(hs2_display_label)
    chapter_rows = clean_records(
        chapters,
        [
            "hs2",
            "hs2_label",
            "display_label",
            "mean_loo_gini",
            "export_probability",
            "mean_asinh_export_value",
            "mean_export_value",
            "mean_export_share",
            "mean_import_share",
            "mean_intermediate_import_share",
            "observations",
            "countries",
            "years",
        ],
    )
    return {"deciles": decile_rows, "chapters": chapter_rows}


def pick_regression_row(
    df: pd.DataFrame,
    model_label: str,
    term: str,
    sample: str | None = None,
) -> pd.Series:
    mask = df["model_label"].astype(str).eq(model_label) & df["term"].astype(str).eq(term)
    if sample is not None and "sample" in df.columns:
        mask &= df["sample"].astype(str).eq(sample)
    rows = df.loc[mask]
    if rows.empty:
        sample_msg = f", sample={sample}" if sample is not None else ""
        raise RuntimeError(f"Missing regression row: model_label={model_label}, term={term}{sample_msg}")
    return rows.iloc[0]


def regression_display_row(label: str, row: pd.Series, interpretation: str) -> dict[str, Any]:
    return {
        "result": label,
        "outcome": clean_scalar(row.get("outcome")),
        "term": clean_scalar(row.get("term")),
        "coef": clean_scalar(row.get("coef")),
        "std_error": clean_scalar(row.get("std_error")),
        "p_value": clean_scalar(row.get("p_value")),
        "nobs": clean_scalar(row.get("nobs")),
        "interpretation": interpretation,
    }


def pct(value: float | None, digits: int = 1) -> str:
    if value is None or not math.isfinite(float(value)):
        return "n/a"
    return f"{100 * float(value):.{digits}f}%"


def dec(value: float | None, digits: int = 3) -> str:
    if value is None or not math.isfinite(float(value)):
        return "n/a"
    return f"{float(value):.{digits}f}"


def money(value: float | None) -> str:
    if value is None or not math.isfinite(float(value)):
        return "n/a"
    value = float(value)
    sign = "-" if value < 0 else ""
    abs_value = abs(value)
    if abs_value >= 1e12:
        return f"{sign}${abs_value / 1e12:.2f}T"
    if abs_value >= 1e9:
        return f"{sign}${abs_value / 1e9:.1f}B"
    if abs_value >= 1e6:
        return f"{sign}${abs_value / 1e6:.1f}M"
    return f"{sign}${abs_value:,.0f}"


def table_rows(rows: list[dict[str, Any]], columns: list[tuple[str, str, str]]) -> str:
    head = "".join(f"<th>{label}</th>" for _, label, _ in columns)
    body = []
    for row in rows:
        try:
            p_value = float(row.get("p_value"))
        except (TypeError, ValueError):
            p_value = np.nan
        try:
            q_value = float(row.get("bh_q_value"))
        except (TypeError, ValueError):
            q_value = np.nan
        is_raw_significant = math.isfinite(p_value) and p_value < 0.05
        is_q_significant = math.isfinite(q_value) and q_value < 0.05
        row_class = ' class="sig-row"' if is_raw_significant else ""
        cells = []
        for key, _, kind in columns:
            value = row.get(key)
            if kind == "pct":
                text = pct(value)
            elif kind == "dec":
                text = dec(value)
            elif kind == "money":
                text = money(value)
            elif kind == "year":
                text = "n/a" if value is None else str(int(value))
            elif kind == "int":
                text = "n/a" if value is None else f"{int(value):,}"
            else:
                text = "" if value is None else str(value)
            if key in {"coefficient", "coef"} and is_raw_significant:
                text = f'<strong class="sig-coef">{text}</strong>'
            elif key == "p_value" and is_raw_significant:
                text = f'<strong class="sig-pvalue">{text}</strong>'
            elif key == "bh_q_value" and is_q_significant:
                text = f'<strong class="sig-qvalue">{text}</strong>'
            cells.append(f"<td>{text}</td>")
        body.append(f"<tr{row_class}>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def format_table_value(value: Any, kind: str) -> str:
    if kind == "pct":
        return pct(value)
    if kind == "dec":
        return dec(value)
    if kind == "money":
        return money(value)
    if kind == "year":
        return "n/a" if value is None else str(int(value))
    if kind == "int":
        return "n/a" if value is None else f"{int(value):,}"
    return "" if value is None else str(value)


def sortable_table_rows(
    rows: list[dict[str, Any]],
    columns: list[tuple[str, str, str, str]],
    table_id: str,
) -> str:
    head = "".join(
        f'<th><button type="button" class="sort-header" data-sort-index="{idx}" data-sort-type="{sort_type}">{label}</button></th>'
        for idx, (_, label, _, sort_type) in enumerate(columns)
    )
    body = []
    for row in rows:
        cells = []
        for key, _, kind, _ in columns:
            value = row.get(key)
            text = format_table_value(value, kind)
            sort_value = "" if value is None else str(value)
            cells.append(f'<td data-sort-value="{escape(sort_value)}">{text}</td>')
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f'<table id="{table_id}" data-sortable><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>'


def pct_points(value: Any, digits: int = 1) -> str:
    if value is None or not math.isfinite(float(value)):
        return "n/a"
    return f"{float(value):.{digits}f}%"


def money_billions(value: Any) -> str:
    if value is None or not math.isfinite(float(value)):
        return "n/a"
    value = float(value)
    if abs(value) >= 1000:
        return f"${value / 1000:.2f}T"
    return f"${value:.1f}B"


def normalize_hs6(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits.zfill(6) if digits else text


def product_name(row: dict[str, Any]) -> str:
    code = normalize_hs6(row.get("cmd_code"))
    fallback = str(row.get("desc") or "").strip()
    if code in PRODUCT_SHORT_NAMES:
        return PRODUCT_SHORT_NAMES[code]
    return fallback if len(fallback) <= 86 else fallback[:83].rstrip() + "..."


def top_goods_cards(rows: list[dict[str, Any]], max_rank: int = 3) -> str:
    scope_labels = {
        "Pooled sample 2024": "World sample",
        "India 2024": "India",
    }
    articles: list[str] = []
    for import_bin in BIN_LABELS:
        scope_blocks: list[str] = []
        for scope, label in scope_labels.items():
            subset = [
                row
                for row in rows
                if row.get("import_bin") == import_bin
                and row.get("scope") == scope
                and int(row.get("rank_in_bin") or 0) <= max_rank
            ]
            subset = sorted(subset, key=lambda row: int(row.get("rank_in_bin") or 0))
            items = []
            for row in subset:
                code = normalize_hs6(row.get("cmd_code"))
                title = escape(str(row.get("desc") or product_name(row)))
                name = escape(product_name(row))
                items.append(
                    "<li>"
                    f'<span title="{title}"><code>{escape(code)}</code> {name}</span>'
                    f"<small>{money_billions(row.get('import_value_usd_bn'))}; "
                    f"{pct_points(row.get('share_of_bin_pct'))} of bin</small>"
                    "</li>"
                )
            scope_blocks.append(
                "<div>"
                f"<h4>{escape(label)}</h4>"
                f"<ol>{''.join(items)}</ol>"
                "</div>"
            )
        articles.append(
            '<article class="top-goods-card">'
            f"<h3>{escape(BIN_LABELS[import_bin])}</h3>"
            f'<div class="top-goods-columns">{"".join(scope_blocks)}</div>'
            "</article>"
        )
    return f"""
      <div class="top-goods-block">
        <div class="top-goods-head">
          <h3>Top goods behind each import bin</h3>
          <p>2024 HS6 products ranked by import value within each bin. The world column pools reporter countries available in the active site sample for 2024; the downloadable CSV keeps the top five rows per bin.</p>
        </div>
        <div class="top-goods-grid">
          {"".join(articles)}
        </div>
        <p class="source-note"><a href="assets/downloads/exercise_03_top_goods_by_import_bin_world_india_2024.csv">Download the top-five goods table</a>.</p>
      </div>
    """


def evidence_links(items: list[tuple[str, str]]) -> str:
    return "".join(f'<a href="{href}">{label}</a>' for label, href in items)


def hypothesis_card(
    eyebrow: str,
    title: str,
    question: str,
    supports: str,
    weakens: str,
    answer: str,
    evidence: list[tuple[str, str]],
) -> str:
    return f"""
      <article class="hypothesis-card">
        <div class="hypothesis-kicker">{eyebrow}</div>
        <h3>{title}</h3>
        <dl>
          <dt>Question</dt><dd>{question}</dd>
          <dt>Supports yes if</dt><dd>{supports}</dd>
          <dt>Weakens yes if</dt><dd>{weakens}</dd>
          <dt>Current answer</dt><dd>{answer}</dd>
        </dl>
        <div class="evidence-links">{evidence_links(evidence)}</div>
      </article>
    """


def hypothesis_grid(cards: list[str]) -> str:
    return f'<div class="hypothesis-grid">{"".join(cards)}</div>'


def evidence_note(question: str, how: str, supports: str, result: str) -> str:
    return f"""
      <article class="evidence-note">
        <dl>
          <dt>Question this answers</dt><dd>{question}</dd>
          <dt>Supports the hypothesis if</dt><dd>{supports}</dd>
          <dt>Current result</dt><dd>{result}</dd>
        </dl>
      </article>
    """


def build_literature_takeaways_html(facts: dict[str, str]) -> str:
    reading_rows = [
        {
            "paper": '<a href="https://www.aeaweb.org/articles?id=10.1257%2F0002828054201396">Hummels and Klenow 2005</a>',
            "takeaway": "Export value can rise through product variety, value per active relationship, and higher unit values or quality.",
            "site_use": "Use Product Gini and Exercise 12 as value decompositions, not as pure variety measures.",
        },
        {
            "paper": '<a href="https://academic.oup.com/qje/article-lookup/doi/10.1162/qjec.2008.123.2.441">Helpman, Melitz, and Rubinstein 2008</a>; <a href="https://www.aeaweb.org/articles?id=10.1257%2Faer.98.4.1707">Chaney 2008</a>',
            "takeaway": "Fixed and variable trade costs affect whether trade relationships exist and how large surviving flows become.",
            "site_use": "Use entry results as evidence on trade-scope adjustment, but do not read them as causal fixed-cost effects without a separate shock or design.",
        },
        {
            "paper": '<a href="https://ideas.repec.org/a/ucp/jpolec/doi10.1086-670272.html">Kehoe and Ruhl 2013</a>',
            "takeaway": "New goods are often low-base goods becoming material, not only literal zero-to-positive entries.",
            "site_use": "Treat harmonized-HS6 persistent entry and bottom-10 robustness as the cleaner extensive-margin headline, with HS4 as a conservative robustness check.",
        },
        {
            "paper": '<a href="https://users.nber.org/~confer/2002/si2002/venables.pdf">Evenett and Venables 2002</a>',
            "takeaway": "Developing-country export growth often comes from existing products reaching new destinations.",
            "site_use": "Keep product, partner, and product-partner-cell margins separate in Exercise 12.",
        },
        {
            "paper": '<a href="https://www.nber.org/system/files/working_papers/w13628/w13628.pdf">Besedes and Prusa 2011</a>',
            "takeaway": "Entry alone is weak evidence because many export relationships die quickly.",
            "site_use": "Add survival, spell length, and deepening checks before interpreting entry as durable diversification.",
        },
        {
            "paper": '<a href="https://archive-ouverte.unige.ch/unige:46586">Cadot, Carrere, and Strauss-Kahn 2011</a>',
            "takeaway": "Development can bring diversification first and reconcentration later, mostly through extensive-margin changes.",
            "site_use": "Study concentration dynamically and keep Section 16 and HS-code-count diagnostics visible.",
        },
        {
            "paper": '<a href="https://www.aeaweb.org/articles?id=10.1257%2F000282803321455160">Imbs and Wacziarg 2003</a>',
            "takeaway": "Sectoral concentration falls and later rises over the development path, so concentration changes need not be monotone.",
            "site_use": "Interpret country-size and income gradients as development-stage patterns unless a causal design identifies the source of change.",
        },
        {
            "paper": '<a href="https://www.hks.harvard.edu/publications/what-you-export-matters-0">Hausmann, Hwang, and Rodrik 2007</a>',
            "takeaway": "Composition matters: countries grow faster when export baskets are weighted toward goods exported by richer economies.",
            "site_use": "Do not call high concentration good or bad until the product mix is compared with sophistication or world relevance.",
        },
        {
            "paper": "Eaton-Kortum-Kramarz; Bernard-Redding-Schott; Freund-Pierola",
            "takeaway": "Aggregate product and destination concentration can come from firm participation, multiproduct scope, and superstars.",
            "site_use": "Use top-product, top-cell, and jump diagnostics as aggregate proxies until firm data are available.",
        },
    ]
    reading_table = table_rows(reading_rows, [("paper", "Paper", "text"), ("takeaway", "Takeaway", "text"), ("site_use", "Use on this site", "text")])

    country_size_table = table_rows(
        facts.get("country_size_common_universe_rows", []),
        [
            ("mechanism", "Mechanism tested", "text"),
            ("dimension", "Export margin", "text"),
            ("outcome", "Outcome", "text"),
            ("coefficient", "Log-pop beta", "dec"),
            ("p_value", "p-value", "dec"),
            ("interpretation", "Interpretation", "text"),
        ],
    )

    measure_rows = [
        {
            "object": "Active Product Gini",
            "definition": "Inequality across positive HS6 product totals inside a country-year-flow.",
            "interpretation": "High values mean export value is concentrated across the country's observed product lines. They do not say whether the products are sophisticated.",
        },
        {
            "object": "World-Relative Product Gini",
            "definition": "Weighted Gini of country product share divided by leave-one-out world product weight.",
            "interpretation": f"Highlighted because it asks whether the basket is unusual relative to world trade. Latest median: {facts['world_relative_gini']} in {facts['world_relative_year']}.",
        },
        {
            "object": "Partner Gini",
            "definition": "Inequality across destination or source partners after summing products.",
            "interpretation": "Use for geographic concentration. It is not the same as product diversification and can move differently.",
        },
        {
            "object": "Product-partner cell Gini",
            "definition": "Inequality across positive HS6-by-partner relationships.",
            "interpretation": "Closest site object to export relationships; it combines product scope, destination scope, and intensive scale.",
        },
        {
            "object": "EXPY-style extension",
            "definition": "Export-share-weighted average of product sophistication, where sophistication is based on who exports the product.",
            "interpretation": "Future complement: tells whether concentration is in high-sophistication or low-sophistication goods.",
        },
    ]
    measure_table = table_rows(measure_rows, [("object", "Website object", "text"), ("definition", "Construction", "text"), ("interpretation", "Interpretation", "text")])

    return f"""
    <section class="page-title">
      <div class="eyebrow">Literature map</div>
      <h1>Lit-Review Takeaways For Trade Concentration</h1>
      <p>This page turns the Papers Notion notes into project-facing guidance for the trade concentration site. It is not a full literature review; it is a map from papers to the site's product, partner, product-partner, world-relative, and transition measures.</p>
    </section>

    <section class="section" id="notion-spine">
      <div class="section-heading">
        <h2>What Your Notes Say</h2>
        <p>Source spine: the private Notion page <em>Papers</em>, fetched 2026-05-27, plus the local export-margins literature wiki and verified public paper pages.</p>
      </div>
      <ul class="callout-list">
        <li><strong>Cadot et al. concentration hump:</strong> export concentration can follow a U-shape over development. The important empirical question is whether reconcentration is structural, mechanical, commodity-driven, or old-cone exit. Cadot-style reconcentration is consistent with structural exit only if the old-cone tests pass.</li>
        <li><strong>Hummels-Klenow:</strong> export growth should be separated into active product/cell expansion and sales growth inside active products/cells; value growth also mixes quantity and quality or unit-value movement.</li>
        <li><strong>Kehoe-Ruhl:</strong> the new-goods margin matters in liberalization and structural-change episodes, but the right object is often the least-traded margin rather than literal zeros.</li>
        <li><strong>Evenett-Venables:</strong> destination entry is a separate margin. A country can diversify geographically by selling old products to new partners.</li>
      </ul>
    </section>

    <section class="section" id="main-takeaways">
      <div class="section-heading">
        <h2>Seven Project Takeaways</h2>
        <p>The literature does not give one concentration story. It gives a set of competing mechanisms that the website should keep separate.</p>
      </div>
      <div class="interpretation-grid">
        <article class="note">
          <h3 class="subsection-title">1. Concentration Is Not Automatically Bad</h3>
          <p>High product concentration can mean a narrow low-productivity commodity basket, but it can also mean specialization in high-sophistication goods or superstar-scale production. The sign depends on composition, survival, prices, and quality.</p>
        </article>
        <article class="note">
          <h3 class="subsection-title">2. Product Variety And Value Concentration Are Different</h3>
          <p>A country can have many products but still place most value in a few. That is why the site reports active Product Gini, top-product logic, and World-Relative Product Gini instead of relying on product counts alone.</p>
        </article>
        <article class="note">
          <h3 class="subsection-title">3. Product And Destination Diversification Are Not The Same</h3>
          <p>Evenett-Venables is the warning. A country can grow exports by taking familiar goods to new markets. Exercise 12 therefore separates product entry, partner entry, and product-partner-cell entry.</p>
        </article>
        <article class="note">
          <h3 class="subsection-title">4. Entry Needs Survival</h3>
          <p>Kehoe-Ruhl and Besedes-Prusa imply that a one-year new HS6 cell can be noisy. Stronger evidence is persistent entry, survival, and deepening of relationships over several years.</p>
        </article>
        <article class="note">
          <h3 class="subsection-title">5. Reconcentration May Be Selection</h3>
          <p>Cadot-Carrere-Strauss-Kahn and Bernard-Redding-Schott point to rich countries dropping old or peripheral products. That can look like rising concentration even if it reflects stronger specialization.</p>
        </article>
        <article class="note">
          <h3 class="subsection-title">6. HS Classification Design Can Create Mechanical Patterns</h3>
          <p>Section 16 is the live example: machinery and electrical equipment contain many economically important lines. The site should show HS section line-value diagnostics and use world-relative weighting before making product-count claims.</p>
        </article>
        <article class="note">
          <h3 class="subsection-title">7. Aggregate Concentration Can Hide Firms</h3>
          <p>Freund-Pierola warns that a country-product spike may be a few giant exporters rather than broad capability. Until firm data are available, top-cell shares and abrupt product jumps are useful indirect diagnostics.</p>
        </article>
        <article class="note">
          <h3 class="subsection-title">Bottom Line</h3>
          <p>The site should never say "concentration rose" as a final explanation. It should ask: concentrated in what, relative to which benchmark, through entry or exit, persistent or temporary, and possibly driven by which firms?</p>
        </article>
      </div>
    </section>

    <section class="section" id="country-size-mechanism">
      <div class="section-heading">
        <h2>Country Size, Entry, And Survival</h2>
      </div>
      <p>The relevant literature separates three propositions that are often conflated. First, larger economies trade more partly because they cover more products and destination markets; this is the Hummels-Klenow level fact. Second, fixed-cost gravity models explain why a fall in trade costs can create new positive trade relationships, especially where previous fixed costs kept marginal products or markets inactive. Third, the development and export-survival literature warns that entry is not the same as durable diversification. New relationships may be numerous but small, short-lived, or unable to deepen.</p>
      <p>The post-2001 common-universe test should therefore be read as a mechanism check, not as a causal estimate of a fixed-cost shock. If larger countries had benefited disproportionately through new entry, the coefficient on country size should be negative for total concentration but positive for new product or partner shares. That is not the pattern in the export results. The size gradient remains for export product concentration even when the sample is restricted to products already present before 2002. For export partners, the stronger evidence comes when old partners that disappear are retained in the old universe as zeroes, which points toward retention of established partner networks rather than new partner entry.</p>
      <p>The more defensible interpretation is therefore narrower and more informative: smaller economies show more extensive-margin adjustment after 2001, while larger economies remain less concentrated because they start with broader trade networks and retain or rebalance those networks more effectively. In Besedes-Prusa terms, the issue is not simply entry; it is survival and deepening. This framing avoids the misleading statement that larger countries benefited more from lower fixed costs. The evidence is closer to churn and catch-up among smaller economies, and retention plus intensive-margin reallocation among larger economies.</p>
      <div class="table-scroll">{country_size_table}</div>
      <ul class="callout-list">
        <li><strong>How to phrase the result:</strong> "Post-2001, smaller countries exhibit more new-entry activity, but larger countries remain less concentrated mainly through lower exit and reallocation among established export products and partners."</li>
        <li><strong>How not to phrase it:</strong> "The fall in fixed costs benefited larger countries more." The current design does not identify that causal claim, and the entry coefficients point in the opposite direction.</li>
        <li><strong>Import caveat:</strong> the import rows in the common-universe output use mapped Exercise 11 import cells and should be treated as sensitivity evidence until a full import item-history checkpoint is built.</li>
      </ul>
      <p class="source-note">Local evidence: <a href="assets/downloads/country_size_common_universe_models.csv">common-universe models</a>, <a href="assets/downloads/country_size_common_universe_diagnostics.csv">diagnostics</a>, and <a href="assets/downloads/country_size_common_universe_source_difference_examples.csv">source-difference checks</a>.</p>
    </section>

    <section class="section" id="hausmann-hwang-rodrik">
      <div class="section-heading">
        <h2>Hausmann-Hwang-Rodrik: Composition, Not Absolute Concentration</h2>
        <p>This is the most important add-on to the current concentration pages because it says what kind of products a country exports may matter for growth.</p>
      </div>
      <p>Hausmann, Hwang, and Rodrik do not make a simple "concentration is good" or "concentration is bad" argument. Their paper says export composition matters. Countries grow faster when their export basket is weighted toward goods typically exported by richer, more productive economies. Concentration enters only indirectly: concentration in high-sophistication goods raises the basket's EXPY; concentration in crude commodities or low-productivity goods lowers it.</p>
      <div class="equation-card">
        <h4>EXPY construction</h4>
        <div class="math-line">
          PRODY<sub>p</sub> = &Sigma;<sub>c</sub> [(x<sub>cp</sub> / X<sub>c</sub>) / &Sigma;<sub>c</sub>(x<sub>cp</sub> / X<sub>c</sub>)] &times; GDPpc<sub>c</sub>
        </div>
        <div class="math-line">
          EXPY<sub>c</sub> = &Sigma;<sub>p</sub> (x<sub>cp</sub> / X<sub>c</sub>) &times; PRODY<sub>p</sub>
        </div>
        <p><strong>Plain English:</strong> first rank each product by the income level of countries that reveal specialization in it. Then average those product scores using the country's export shares.</p>
      </div>
      <ul class="callout-list">
        <li>The paper reports that a 10 percent increase in EXPY predicts roughly a half percentage point faster growth in cross-country specifications.</li>
        <li>In fixed-effects panel specifications, the implied effect is smaller: about 0.14 to 0.19 percentage points for a 10 percent EXPY increase.</li>
        <li>For this site, EXPY is a future companion measure: combine concentration with product sophistication so "high concentration" is not interpreted without knowing whether the concentration is in high- or low-sophistication products.</li>
      </ul>
      <p class="source-note">Verified against <a href="https://www.hks.harvard.edu/sites/default/files/centers/cid/files/publications/faculty-working-papers/123.pdf">CID Working Paper 123 PDF</a> and <a href="https://www.nber.org/papers/w11905">NBER Working Paper 11905 metadata</a>.</p>
    </section>

    <section class="section" id="website-measure-map">
      <div class="section-heading">
        <h2>How To Read The Website Measures</h2>
        <p>The same country can look concentrated for different reasons. These objects should not be collapsed into one story.</p>
      </div>
      <div class="table-scroll">{measure_table}</div>
      <div class="equation-card">
        <h4>Current site facts to anchor interpretation</h4>
        <p>In the {facts['sample_panel_label']}, median export Product Gini is <strong>{facts['export_product_gini']}</strong>, median import Product Gini is <strong>{facts['import_product_gini']}</strong>, and median export Product-partner cell Gini is <strong>{facts['export_cell_gini']}</strong>. In the harmonized balanced 2000-2024 benchmark, median World-Relative Product Gini is <strong>{facts['world_relative_gini']}</strong> in <strong>{facts['world_relative_year']}</strong>, while the appendix literal world-weighted share Gini is <strong>{facts['world_weighted_share_gini']}</strong>.</p>
      </div>
    </section>

    <section class="section" id="reading-map">
      <div class="section-heading">
        <h2>Reading Map</h2>
        <p>Read these as mechanisms, not just citations. Each one points to a different empirical diagnostic.</p>
      </div>
      <div class="table-scroll">{reading_table}</div>
    </section>

    """


def source_link(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def validate_source_shapes(ex1: pd.DataFrame) -> dict[str, Any]:
    countries = sorted(ex1["country"].dropna().unique())
    year_min = int(ex1["year"].min())
    year_max = int(ex1["year"].max())
    if not countries:
        raise RuntimeError("Exercise 1 panel has no countries.")
    if year_min > year_max:
        raise RuntimeError(f"Invalid Exercise 1 year range {year_min}-{year_max}.")
    year_flow_counts = ex1.groupby(["year", "flow"])["reporter_code"].nunique().unstack()
    stable_start, stable_end = 2000, 2024
    stable = ex1[ex1["year"].between(stable_start, stable_end)].copy()
    stable_counts = stable.groupby(["year", "flow"])["reporter_code"].nunique().unstack()
    stable_years = stable_end - stable_start + 1
    stable_reporter_flow_years = stable.groupby(["reporter_code", "flow"])["year"].nunique()
    stable_export_reporters = set(
        stable_reporter_flow_years[
            (stable_reporter_flow_years.index.get_level_values("flow") == "Exports")
            & stable_reporter_flow_years.eq(stable_years)
        ].index.get_level_values("reporter_code")
    )
    stable_import_reporters = set(
        stable_reporter_flow_years[
            (stable_reporter_flow_years.index.get_level_values("flow") == "Imports")
            & stable_reporter_flow_years.eq(stable_years)
        ].index.get_level_values("reporter_code")
    )
    return {
        "countries": len(countries),
        "year_min": year_min,
        "year_max": year_max,
        "min_reporters_per_year_flow": int(year_flow_counts.min().min()),
        "max_reporters_per_year_flow": int(year_flow_counts.max().max()),
        "stable_window_start": stable_start,
        "stable_window_end": stable_end,
        "stable_min_reporters_per_year_flow": int(stable_counts.min().min()),
        "stable_max_reporters_per_year_flow": int(stable_counts.max().max()),
        "stable_balanced_countries_both_flows": len(stable_export_reporters & stable_import_reporters),
    }


def numeric_columns(df: pd.DataFrame, skip: set[str]) -> pd.DataFrame:
    out = df.copy()
    for column in out.columns:
        if column not in skip:
            out[column] = pd.to_numeric(out[column], errors="coerce")
    return out


def bh_adjust_pvalues(p_values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(p_values, errors="coerce")
    adjusted = pd.Series(np.nan, index=numeric.index, dtype="float64")
    valid = numeric.dropna()
    if valid.empty:
        return adjusted
    ordered = valid.sort_values()
    ranks = np.arange(1, len(ordered) + 1)
    raw_adjusted = ordered.to_numpy(dtype=float) * len(ordered) / ranks
    monotone = np.minimum.accumulate(raw_adjusted[::-1])[::-1]
    adjusted.loc[ordered.index] = np.clip(monotone, 0, 1)
    return adjusted


def sci(value: Any, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if not math.isfinite(number):
        return "n/a"
    return f"{number:.{digits}e}"


def fixed_dec(value: Any, digits: int = 4) -> str:
    if value is None:
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if not math.isfinite(number):
        return "n/a"
    return f"{number:.{digits}f}"


def significant_decimal(value: Any, sig_digits: int = 3) -> str:
    if value is None:
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if not math.isfinite(number):
        return "n/a"
    if number == 0:
        return "0"
    exponent = math.floor(math.log10(abs(number)))
    decimals = max(sig_digits - 1 - exponent, 0)
    text = f"{number:.{decimals}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def load_contributions_data() -> dict[str, Any]:
    if not include_contributions_page():
        return {}
    import_models = read_csv("contributions_import_wr_robustness_models")
    import_key = read_csv("contributions_import_wr_key_coefficients")
    import_size_mechanism_key = read_csv("contributions_import_size_mechanism_key_coefficients")
    partner_stability_summary = read_csv("contributions_partner_gini_stability_summary")
    partner_common_trends = read_csv("contributions_partner_gini_common_trends")
    required = {
        "exercise_family",
        "model_label",
        "sample",
        "flow",
        "dimension",
        "metric",
        "outcome",
        "term",
        "coefficient",
        "std_error",
        "p_value",
        "nobs",
        "clusters",
        "status",
    }
    require_columns(import_models, "World-relative import robustness models", required)
    require_columns(import_key, "World-relative import key coefficients", required | {"family_bh_q_value"})
    require_columns(
        import_size_mechanism_key,
        "Import-size mechanism key coefficients",
        required
        | {
            "hypothesis",
            "q_value",
            "baseline_wr_log_population_beta",
            "absolute_shrink_vs_wr_baseline_pct",
            "per_population_doubling_effect",
        },
    )
    require_columns(
        partner_stability_summary,
        "Partner Gini stability summary",
        {
            "window",
            "flow",
            "countries",
            "median_abs_slope_per_decade",
            "p90_abs_slope_per_decade",
            "share_stable_slope_10yr_0p02",
            "median_abs_endpoint_change",
            "p90_abs_endpoint_change",
            "share_stable_endpoint_0p05",
            "median_within_country_sd",
            "countries_with_slope_q_lt_0p05",
        },
    )
    require_columns(
        partner_common_trends,
        "Partner Gini common trend models",
        {
            "window",
            "flow",
            "coefficient_per_decade",
            "std_error_per_decade",
            "ci_low_per_decade",
            "ci_high_per_decade",
            "p_value",
            "nobs",
            "countries",
            "r_squared",
            "status",
        },
    )
    text_cols = {
        "exercise_family",
        "model_label",
        "sample",
        "flow",
        "dimension",
        "metric",
        "outcome",
        "term",
        "status",
        "dropped_regressors",
        "fixed_effects",
        "se_method",
        "cluster_col",
        "p_value_reference",
    }
    import_models = numeric_columns(import_models, text_cols)
    import_key = numeric_columns(import_key, text_cols)
    import_size_mechanism_key = numeric_columns(import_size_mechanism_key, text_cols | {"hypothesis"})
    partner_stability_summary = numeric_columns(partner_stability_summary, {"window", "flow"})
    partner_common_trends = numeric_columns(partner_common_trends, {"window", "flow", "status", "stars"})

    key_pop = import_key[
        import_key["exercise_family"].eq("country_size")
        & import_key["outcome"].eq("world_relative_import_product_gini")
        & import_key["term"].eq("log_population")
        & import_key["status"].eq("ok")
    ].copy()
    key_pop["bh_q_value"] = key_pop["family_bh_q_value"]

    country_size_family = import_models[
        import_models["exercise_family"].eq("country_size")
        & import_models["term"].isin(["log_population", "log_gdp_per_capita"])
        & import_models["status"].eq("ok")
    ].copy()
    country_size_family["bh_q_value"] = bh_adjust_pvalues(country_size_family["p_value"])
    gdp_rows = country_size_family[
        country_size_family["outcome"].eq("world_relative_import_product_gini")
        & country_size_family["term"].eq("log_gdp_per_capita")
    ].copy()

    display_rows = pd.concat([key_pop, gdp_rows], ignore_index=True)
    model_labels = {
        "country_size_year_fe": "Year FE, country clustered",
        "country_size_two_way_cluster": "Year FE, two-way clustered",
    }
    term_labels = {
        "log_population": "Log population",
        "log_gdp_per_capita": "Log GDP per capita",
    }
    q_notes = {
        "log_population": "Key-table BH q",
        "log_gdp_per_capita": "BH q recomputed after adding GDP pc to the country-size import family",
    }
    display_rows["term_label"] = display_rows["term"].map(term_labels).fillna(display_rows["term"])
    display_rows["model_label_display"] = display_rows["model_label"].map(model_labels).fillna(display_rows["model_label"])
    display_rows["q_family"] = display_rows["term"].map(q_notes).fillna("")
    display_rows["sort_term"] = display_rows["term"].map({"log_population": 0, "log_gdp_per_capita": 1}).fillna(9)
    display_rows["sort_model"] = display_rows["model_label"].map({"country_size_year_fe": 0, "country_size_two_way_cluster": 1}).fillna(9)
    display_rows = display_rows.sort_values(["sort_term", "sort_model"]).reset_index(drop=True)

    for column in ["coefficient", "std_error"]:
        display_rows[column] = display_rows[column].map(lambda value: fixed_dec(value, 4))
    display_rows["p_value"] = display_rows["p_value"].map(lambda value: sci(value, 2))
    display_rows["bh_q_value"] = display_rows["bh_q_value"].map(lambda value: significant_decimal(value, 3))

    hub_models = {
        "wr_baseline_year_fe": "Baseline full sample",
        "wr_drop_hkg_sgp_lux_isl_guy": "Drop HKG, SGP, LUX, ISL, GUY",
    }
    hub_rows = import_size_mechanism_key[
        import_size_mechanism_key["model_label"].isin(hub_models)
        & import_size_mechanism_key["term"].eq("log_population")
        & import_size_mechanism_key["status"].eq("ok")
    ].copy()
    hub_rows["sort_model"] = hub_rows["model_label"].map({"wr_baseline_year_fe": 0, "wr_drop_hkg_sgp_lux_isl_guy": 1})
    hub_rows = hub_rows.sort_values("sort_model").reset_index(drop=True)
    hub_rows["spec"] = hub_rows["model_label"].map(hub_models).fillna(hub_rows["model_label"])
    hub_rows["coefficient"] = hub_rows["coefficient"].map(lambda value: fixed_dec(value, 4))
    hub_rows["std_error"] = hub_rows["std_error"].map(lambda value: fixed_dec(value, 4))
    hub_rows["p_value"] = hub_rows["p_value"].map(lambda value: sci(value, 2))
    hub_rows["shrink_vs_baseline"] = hub_rows["absolute_shrink_vs_wr_baseline_pct"].map(
        lambda value: "n/a" if value is None or not math.isfinite(float(value)) else f"{float(value):.1f}%"
    )

    return {
        "import_wr_country_size_rows": clean_records(
            display_rows,
            [
                "term_label",
                "model_label_display",
                "coefficient",
                "std_error",
                "p_value",
                "bh_q_value",
                "nobs",
                "clusters",
                "q_family",
            ],
        ),
        "import_wr_country_size_family": clean_records(country_size_family, list(country_size_family.columns)),
        "import_size_drop_hub_rows": clean_records(
            hub_rows,
            ["spec", "coefficient", "std_error", "p_value", "nobs", "clusters", "shrink_vs_baseline"],
        ),
        "partner_gini_stability_summary": clean_records(
            partner_stability_summary,
            list(partner_stability_summary.columns),
        ),
        "partner_gini_common_trends": clean_records(
            partner_common_trends,
            list(partner_common_trends.columns),
        ),
    }


def load_country_size_data() -> dict[str, Any]:
    if not include_country_size_page():
        return {}
    main_models = read_csv("country_size_main_models")
    robustness_models = read_csv("country_size_robustness_models")
    two_way_models = read_csv("country_size_two_way_cluster_models")
    fama_macbeth_models = read_csv("country_size_fama_macbeth_models")
    gmm_lag_iv_models = read_csv("country_size_gmm_lag_iv_models")
    gmm_lag_iv_first_stage = read_csv("country_size_gmm_lag_iv_first_stage")
    primary_share_models = read_csv("country_size_primary_share_control_models")
    primary_share_two_way_models = read_csv("country_size_primary_share_two_way_cluster_models")
    primary_share_fama_macbeth_models = read_csv("country_size_primary_share_fama_macbeth_models")
    primary_share_diagnostics = read_csv("country_size_primary_export_share_diagnostics")
    primary_product_mapping = read_csv("country_size_primary_product_hs6_mapping")
    us_counterfactuals = read_csv("country_size_us_population_counterfactuals")
    yearly_slopes = read_csv("country_size_yearly_slopes")
    diagnostics = read_csv("country_size_sample_diagnostics")
    world_large_spearman_summary = read_csv("world_large_product_exposure_spearman_summary")
    world_large_yearly_spearman = read_csv("world_large_product_exposure_yearly_spearman")
    world_large_models = read_csv("world_large_product_exposure_models")
    world_large_diagnostics = read_csv("world_large_product_exposure_diagnostics")

    model_required = {
        "model_label",
        "sample",
        "flow",
        "dimension",
        "metric",
        "outcome",
        "term",
        "coefficient",
        "std_error",
        "p_value",
        "nobs",
        "clusters",
        "status",
    }
    for name, frame in [
        ("country-size main models", main_models),
        ("country-size robustness models", robustness_models),
        ("country-size two-way cluster models", two_way_models),
        ("country-size Fama-MacBeth models", fama_macbeth_models),
        ("country-size Lag-IV GMM models", gmm_lag_iv_models),
        ("country-size primary-share models", primary_share_models),
        ("country-size primary-share two-way models", primary_share_two_way_models),
        ("country-size primary-share Fama-MacBeth models", primary_share_fama_macbeth_models),
        ("country-size yearly slopes", yearly_slopes),
    ]:
        require_columns(frame, name, model_required)
    require_columns(diagnostics, "country-size sample diagnostics", {"diagnostic", "value"})
    require_columns(
        gmm_lag_iv_models,
        "country-size Lag-IV GMM models",
        model_required | {"bh_q_value", "j_stat", "j_p_value", "instrument_count", "instrument_terms", "endogenous_terms"},
    )
    require_columns(
        gmm_lag_iv_first_stage,
        "country-size Lag-IV GMM first-stage diagnostics",
        {
            "model_label",
            "sample",
            "flow",
            "dimension",
            "metric",
            "outcome",
            "endogenous_term",
            "partial_rsquared",
            "shea_rsquared",
            "f_stat",
            "f_pval",
            "f_dist",
            "nobs",
            "clusters",
            "status",
            "instrument_terms",
            "instrument_count",
        },
    )
    require_columns(primary_share_diagnostics, "country-size primary-share diagnostics", {"row_type", "diagnostic", "value"})
    require_columns(primary_product_mapping, "country-size primary HS6 mapping", {"classification_code", "cmd_code", "primary_strict", "primary_broad"})
    require_columns(
        world_large_spearman_summary,
        "world-large-product Spearman summary",
        {
            "outcome",
            "outcome_label",
            "size_variable",
            "size_label",
            "years",
            "mean_spearman",
            "median_spearman",
            "min_spearman",
            "max_spearman",
            "share_positive",
        },
    )
    require_columns(
        world_large_yearly_spearman,
        "world-large-product yearly Spearman",
        {
            "year",
            "outcome",
            "outcome_label",
            "size_variable",
            "size_label",
            "spearman_size_outcome",
            "n_countries",
        },
    )
    require_columns(
        world_large_models,
        "world-large-product exposure models",
        model_required | {"bh_q_value", "fixed_effects", "se_method", "cluster_col", "p_value_reference"},
    )
    require_columns(world_large_diagnostics, "world-large-product exposure diagnostics", {"diagnostic", "value", "detail"})
    require_columns(
        us_counterfactuals,
        "country-size US population counterfactuals",
        {
            "target_order",
            "target_id",
            "target_label",
            "target_country",
            "target_iso3",
            "target_year",
            "target_population",
            "us_country",
            "us_iso3",
            "us_year",
            "us_population",
            "flow",
            "dimension",
            "metric",
            "outcome",
            "coefficient",
            "log_population_delta",
            "predicted_gini_change",
            "outcome_sample_sd",
            "predicted_gini_change_sd_share",
        },
    )

    text_cols = {
        "model_label",
        "sample",
        "flow",
        "dimension",
        "metric",
        "outcome",
        "term",
        "status",
        "dropped_regressors",
        "fixed_effects",
        "se_method",
        "cluster_col",
        "p_value_reference",
        "primary_share_control",
        "endogenous_terms",
        "instrument_terms",
        "endogenous_term",
        "f_dist",
        "row_type",
        "diagnostic",
        "detail",
        "classification_code",
        "cmd_code",
        "hs_desc_official",
        "bec5_label",
        "bec5_end_use",
        "exercise_03_bin",
        "mapping_status",
        "bec5_primary_flag",
        "primary_strict",
        "primary_broad",
        "primary_strict_rule",
        "primary_broad_rule",
        "target_id",
        "target_label",
        "target_country",
        "target_iso3",
        "us_country",
        "us_iso3",
        "outcome_label",
        "size_variable",
        "size_label",
    }
    main_models = numeric_columns(main_models, text_cols)
    robustness_models = numeric_columns(robustness_models, text_cols)
    two_way_models = numeric_columns(two_way_models, text_cols)
    fama_macbeth_models = numeric_columns(fama_macbeth_models, text_cols)
    gmm_lag_iv_models = numeric_columns(gmm_lag_iv_models, text_cols)
    gmm_lag_iv_first_stage = numeric_columns(gmm_lag_iv_first_stage, text_cols)
    primary_share_models = numeric_columns(primary_share_models, text_cols)
    primary_share_two_way_models = numeric_columns(primary_share_two_way_models, text_cols)
    primary_share_fama_macbeth_models = numeric_columns(primary_share_fama_macbeth_models, text_cols)
    primary_share_diagnostics = numeric_columns(primary_share_diagnostics, text_cols)
    us_counterfactuals = numeric_columns(us_counterfactuals, text_cols)
    yearly_slopes = numeric_columns(yearly_slopes, text_cols)
    world_large_spearman_summary = numeric_columns(world_large_spearman_summary, text_cols)
    world_large_yearly_spearman = numeric_columns(world_large_yearly_spearman, text_cols)
    world_large_models = numeric_columns(world_large_models, text_cols)
    world_large_diagnostics = numeric_columns(world_large_diagnostics, text_cols)

    primary = main_models[main_models["term"].eq("log_population") & main_models["status"].eq("ok")].copy()
    strongest_exports = primary[primary["flow"].eq("Exports")].sort_values("coefficient").head(1)
    strongest_imports = primary[primary["flow"].eq("Imports")].sort_values("coefficient").head(1)
    yearly_ok = yearly_slopes[yearly_slopes["term"].eq("log_population") & yearly_slopes["status"].eq("ok")].copy()
    yearly_summary = (
        yearly_ok.groupby(["flow", "dimension", "metric"], as_index=False)
        .agg(
            years_estimated=("year", "nunique"),
            mean_beta=("coefficient", "mean"),
            median_beta=("coefficient", "median"),
            min_beta=("coefficient", "min"),
            max_beta=("coefficient", "max"),
        )
        .sort_values(["flow", "dimension", "metric"])
        if not yearly_ok.empty
        else pd.DataFrame(columns=["flow", "dimension", "metric", "years_estimated", "mean_beta", "median_beta", "min_beta", "max_beta"])
    )

    return {
        "main_models": clean_records(main_models, list(main_models.columns)),
        "robustness_models": clean_records(robustness_models, list(robustness_models.columns)),
        "two_way_cluster_models": clean_records(two_way_models, list(two_way_models.columns)),
        "fama_macbeth_models": clean_records(fama_macbeth_models, list(fama_macbeth_models.columns)),
        "gmm_lag_iv_models": clean_records(gmm_lag_iv_models, list(gmm_lag_iv_models.columns)),
        "gmm_lag_iv_first_stage": clean_records(gmm_lag_iv_first_stage, list(gmm_lag_iv_first_stage.columns)),
        "primary_share_control_models": clean_records(primary_share_models, list(primary_share_models.columns)),
        "primary_share_two_way_cluster_models": clean_records(primary_share_two_way_models, list(primary_share_two_way_models.columns)),
        "primary_share_fama_macbeth_models": clean_records(primary_share_fama_macbeth_models, list(primary_share_fama_macbeth_models.columns)),
        "primary_export_share_diagnostics": clean_records(primary_share_diagnostics, list(primary_share_diagnostics.columns)),
        "primary_product_hs6_mapping": clean_records(primary_product_mapping, list(primary_product_mapping.columns)),
        "us_population_counterfactuals": clean_records(us_counterfactuals, list(us_counterfactuals.columns)),
        "yearly_summary": clean_records(yearly_summary, list(yearly_summary.columns)),
        "sample_diagnostics": clean_records(diagnostics, list(diagnostics.columns)),
        "strongest_export": clean_records(strongest_exports, list(strongest_exports.columns))[0] if not strongest_exports.empty else {},
        "strongest_import": clean_records(strongest_imports, list(strongest_imports.columns))[0] if not strongest_imports.empty else {},
        "world_large_spearman_summary": clean_records(world_large_spearman_summary, list(world_large_spearman_summary.columns)),
        "world_large_yearly_spearman": clean_records(world_large_yearly_spearman, list(world_large_yearly_spearman.columns)),
        "world_large_models": clean_records(world_large_models, list(world_large_models.columns)),
        "world_large_diagnostics": clean_records(world_large_diagnostics, list(world_large_diagnostics.columns)),
    }


def _legacy_export_growth_effect_data_unused() -> dict[str, Any]:
    if not include_growth_effect_page():
        return {}
    main_models = read_csv("growth_effect_main_models")
    sample_comparison_models = read_csv("growth_effect_sample_comparison_models")
    robustness_models = read_csv("growth_effect_robustness_models")
    income_bin_slopes = read_csv("growth_effect_income_bin_slopes")
    threshold_scan = read_csv("growth_effect_threshold_scan")
    diagnostics = read_csv("growth_effect_sample_diagnostics")

    model_required = {
        "model_label",
        "sample",
        "flow",
        "dimension",
        "metric",
        "outcome",
        "term",
        "coefficient",
        "std_error",
        "p_value",
        "nobs",
        "clusters",
        "status",
    }
    for name, frame in [
        ("growth-effect main models", main_models),
        ("growth-effect robustness models", robustness_models),
    ]:
        require_columns(frame, name, model_required)
    require_columns(
        income_bin_slopes,
        "growth-effect income-bin slopes",
        {
            "model_label",
            "sample",
            "flow",
            "dimension",
            "metric",
            "outcome",
            "row_type",
            "label",
            "export_level_bin",
            "term",
            "coefficient",
            "std_error",
            "p_value",
            "bh_q_value",
            "low_middle_export_cutoff",
            "middle_high_export_cutoff",
            "nobs",
            "clusters",
            "status",
        },
    )
    require_columns(
        threshold_scan,
        "growth-effect threshold scan",
        {
            "model_label",
            "sample",
            "flow",
            "dimension",
            "metric",
            "outcome",
            "threshold_percentile",
            "row_type",
            "label",
            "term",
            "threshold_exports_constant_2015_usd",
            "coefficient",
            "std_error",
            "p_value",
            "bh_q_value",
            "nobs",
            "clusters",
            "status",
        },
    )
    require_columns(diagnostics, "growth-effect sample diagnostics", {"diagnostic", "value"})

    text_cols = {
        "model_label",
        "sample",
        "flow",
        "dimension",
        "metric",
        "outcome",
        "term",
        "row_type",
        "label",
        "export_level_bin",
        "status",
        "dropped_regressors",
        "fixed_effects",
        "se_method",
        "cluster_col",
        "p_value_reference",
    }
    main_models = numeric_columns(main_models, text_cols)
    robustness_models = numeric_columns(robustness_models, text_cols)
    income_bin_slopes = numeric_columns(income_bin_slopes, text_cols)
    threshold_scan = numeric_columns(threshold_scan, text_cols)

    primary = main_models[main_models["term"].eq("prior_export_growth")].copy()
    primary_ok = primary[primary["status"].eq("ok")].copy()
    strongest_abs = (
        primary_ok.assign(abs_coef=primary_ok["coefficient"].abs()).sort_values("abs_coef", ascending=False).head(1)
        if not primary_ok.empty
        else pd.DataFrame()
    )
    leveling_rows = income_bin_slopes[
        income_bin_slopes["row_type"].eq("difference")
        & income_bin_slopes["status"].eq("ok")
        & income_bin_slopes["bh_q_value"].notna()
    ].copy()
    leveling_strongest = (
        leveling_rows.assign(abs_diff=leveling_rows["coefficient"].abs()).sort_values("abs_diff", ascending=False).head(1)
        if not leveling_rows.empty
        else pd.DataFrame()
    )
    main_cutoffs = {}
    slope_rows = income_bin_slopes[income_bin_slopes["row_type"].eq("slope")]
    if not slope_rows.empty:
        first = slope_rows.iloc[0]
        main_cutoffs = {
            "low_middle_export_cutoff": clean_scalar(first.get("low_middle_export_cutoff")),
            "middle_high_export_cutoff": clean_scalar(first.get("middle_high_export_cutoff")),
        }
    return {
        "main_models": clean_records(main_models, list(main_models.columns)),
        "robustness_models": clean_records(robustness_models, list(robustness_models.columns)),
        "income_bin_slopes": clean_records(income_bin_slopes, list(income_bin_slopes.columns)),
        "threshold_scan": clean_records(threshold_scan, list(threshold_scan.columns)),
        "sample_diagnostics": clean_records(diagnostics, list(diagnostics.columns)),
        "strongest_absolute": clean_records(strongest_abs, list(strongest_abs.columns))[0] if not strongest_abs.empty else {},
        "leveling_strongest": clean_records(leveling_strongest, list(leveling_strongest.columns))[0] if not leveling_strongest.empty else {},
        "cutoffs": main_cutoffs,
        "horizons": sorted(int(value) for value in pd.to_numeric(main_models["horizon"], errors="coerce").dropna().unique()),
    }


def _legacy_export_growth_effect_data_unused_2() -> dict[str, Any]:
    if not include_growth_effect_page():
        return {}
    main_models = read_csv("growth_effect_main_models")
    sample_comparison_models = read_csv("growth_effect_sample_comparison_models")
    robustness_models = read_csv("growth_effect_robustness_models")
    income_bin_slopes = read_csv("growth_effect_income_bin_slopes")
    threshold_scan = read_csv("growth_effect_threshold_scan")
    diagnostics = read_csv("growth_effect_sample_diagnostics")

    model_required = {
        "model_label", "sample", "flow", "dimension", "metric", "outcome",
        "term", "coefficient", "std_error", "p_value", "nobs", "clusters", "status",
    }
    for name, frame in [
        ("growth-effect main models", main_models),
        ("growth-effect sample-comparison models", sample_comparison_models),
        ("growth-effect robustness models", robustness_models),
    ]:
        require_columns(frame, name, model_required)
    require_columns(sample_comparison_models, "growth-effect sample-comparison models", {"sample_definition"})
    require_columns(
        income_bin_slopes,
        "growth-effect income-bin slopes",
        {
            "model_label", "sample", "flow", "dimension", "metric", "outcome", "row_type",
            "label", "export_level_bin", "term", "coefficient", "std_error", "p_value",
            "bh_q_value", "low_middle_export_cutoff", "middle_high_export_cutoff", "nobs",
            "clusters", "status",
        },
    )
    require_columns(
        threshold_scan,
        "growth-effect threshold scan",
        {
            "model_label", "sample", "flow", "dimension", "metric", "outcome",
            "threshold_percentile", "row_type", "label", "term",
            "threshold_exports_constant_2015_usd", "coefficient", "std_error", "p_value",
            "bh_q_value", "nobs", "clusters", "status",
        },
    )
    require_columns(diagnostics, "growth-effect sample diagnostics", {"diagnostic", "value"})

    text_cols = {
        "model_label", "sample", "flow", "dimension", "metric", "outcome", "term",
        "row_type", "label", "export_level_bin", "status", "dropped_regressors", "fixed_effects", "se_method",
        "cluster_col", "p_value_reference",
    }
    main_models = numeric_columns(main_models, text_cols)
    robustness_models = numeric_columns(robustness_models, text_cols)
    income_bin_slopes = numeric_columns(income_bin_slopes, text_cols)
    threshold_scan = numeric_columns(threshold_scan, text_cols)

    primary = main_models[main_models["term"].eq("prior_export_growth")].copy()
    primary_ok = primary[primary["status"].eq("ok")].copy()
    strongest_abs = primary_ok.assign(abs_coef=primary_ok["coefficient"].abs()).sort_values("abs_coef", ascending=False).head(1) if not primary_ok.empty else pd.DataFrame()
    leveling_rows = income_bin_slopes[
        income_bin_slopes["row_type"].eq("difference")
        & income_bin_slopes["status"].eq("ok")
        & income_bin_slopes["bh_q_value"].notna()
    ].copy()
    leveling_strongest = leveling_rows.assign(abs_diff=leveling_rows["coefficient"].abs()).sort_values("abs_diff", ascending=False).head(1) if not leveling_rows.empty else pd.DataFrame()
    main_cutoffs = {}
    slope_rows = income_bin_slopes[income_bin_slopes["row_type"].eq("slope")]
    if not slope_rows.empty:
        first = slope_rows.iloc[0]
        main_cutoffs = {
            "low_middle_export_cutoff": clean_scalar(first.get("low_middle_export_cutoff")),
            "middle_high_export_cutoff": clean_scalar(first.get("middle_high_export_cutoff")),
        }
    return {
        "main_models": clean_records(main_models, list(main_models.columns)),
        "robustness_models": clean_records(robustness_models, list(robustness_models.columns)),
        "income_bin_slopes": clean_records(income_bin_slopes, list(income_bin_slopes.columns)),
        "threshold_scan": clean_records(threshold_scan, list(threshold_scan.columns)),
        "sample_diagnostics": clean_records(diagnostics, list(diagnostics.columns)),
        "strongest_absolute": clean_records(strongest_abs, list(strongest_abs.columns))[0] if not strongest_abs.empty else {},
        "leveling_strongest": clean_records(leveling_strongest, list(leveling_strongest.columns))[0] if not leveling_strongest.empty else {},
        "cutoffs": main_cutoffs,
        "horizons": sorted(int(value) for value in pd.to_numeric(main_models["horizon"], errors="coerce").dropna().unique()),
    }


def _legacy_export_growth_effect_data_unused_3() -> dict[str, Any]:
    if not include_growth_effect_page():
        return {}
    main_models = read_csv("growth_effect_main_models")
    sample_comparison_models = read_csv("growth_effect_sample_comparison_models")
    robustness_models = read_csv("growth_effect_robustness_models")
    income_bin_slopes = read_csv("growth_effect_income_bin_slopes")
    threshold_scan = read_csv("growth_effect_threshold_scan")
    diagnostics = read_csv("growth_effect_sample_diagnostics")

    model_required = {
        "model_label", "sample", "flow", "dimension", "metric", "outcome",
        "term", "coefficient", "std_error", "p_value", "nobs", "clusters", "status",
    }
    for name, frame in [
        ("growth-effect main models", main_models),
        ("growth-effect sample-comparison models", sample_comparison_models),
        ("growth-effect robustness models", robustness_models),
    ]:
        require_columns(frame, name, model_required)
    require_columns(sample_comparison_models, "growth-effect sample-comparison models", {"sample_definition"})
    require_columns(
        income_bin_slopes,
        "growth-effect income-bin slopes",
        {
            "model_label", "sample", "flow", "dimension", "metric", "outcome", "row_type",
            "label", "export_level_bin", "term", "coefficient", "std_error", "p_value",
            "bh_q_value", "low_middle_export_cutoff", "middle_high_export_cutoff", "nobs",
            "clusters", "status",
        },
    )
    require_columns(
        threshold_scan,
        "growth-effect threshold scan",
        {
            "model_label", "sample", "flow", "dimension", "metric", "outcome",
            "threshold_percentile", "row_type", "label", "term",
            "threshold_exports_constant_2015_usd", "coefficient", "std_error", "p_value",
            "bh_q_value", "nobs", "clusters", "status",
        },
    )
    require_columns(diagnostics, "growth-effect sample diagnostics", {"diagnostic", "value"})

    text_cols = {
        "model_label", "sample", "flow", "dimension", "metric", "outcome", "term",
        "row_type", "label", "export_level_bin", "status", "dropped_regressors", "fixed_effects", "se_method",
        "cluster_col", "p_value_reference",
    }
    main_models = numeric_columns(main_models, text_cols)
    robustness_models = numeric_columns(robustness_models, text_cols)
    income_bin_slopes = numeric_columns(income_bin_slopes, text_cols)
    threshold_scan = numeric_columns(threshold_scan, text_cols)

    primary = main_models[main_models["term"].eq("prior_export_growth")].copy()
    primary_ok = primary[primary["status"].eq("ok")].copy()
    strongest_abs = primary_ok.assign(abs_coef=primary_ok["coefficient"].abs()).sort_values("abs_coef", ascending=False).head(1) if not primary_ok.empty else pd.DataFrame()
    leveling_rows = income_bin_slopes[
        income_bin_slopes["row_type"].eq("difference")
        & income_bin_slopes["status"].eq("ok")
        & income_bin_slopes["bh_q_value"].notna()
    ].copy()
    leveling_strongest = leveling_rows.assign(abs_diff=leveling_rows["coefficient"].abs()).sort_values("abs_diff", ascending=False).head(1) if not leveling_rows.empty else pd.DataFrame()
    main_cutoffs = {}
    slope_rows = income_bin_slopes[income_bin_slopes["row_type"].eq("slope")]
    if not slope_rows.empty:
        first = slope_rows.iloc[0]
        main_cutoffs = {
            "low_middle_export_cutoff": clean_scalar(first.get("low_middle_export_cutoff")),
            "middle_high_export_cutoff": clean_scalar(first.get("middle_high_export_cutoff")),
        }
    return {
        "main_models": clean_records(main_models, list(main_models.columns)),
        "robustness_models": clean_records(robustness_models, list(robustness_models.columns)),
        "income_bin_slopes": clean_records(income_bin_slopes, list(income_bin_slopes.columns)),
        "threshold_scan": clean_records(threshold_scan, list(threshold_scan.columns)),
        "sample_diagnostics": clean_records(diagnostics, list(diagnostics.columns)),
        "strongest_absolute": clean_records(strongest_abs, list(strongest_abs.columns))[0] if not strongest_abs.empty else {},
        "leveling_strongest": clean_records(leveling_strongest, list(leveling_strongest.columns))[0] if not leveling_strongest.empty else {},
        "cutoffs": main_cutoffs,
        "horizons": sorted(int(value) for value in pd.to_numeric(main_models["horizon"], errors="coerce").dropna().unique()),
    }


def load_growth_effect_data() -> dict[str, Any]:
    if not include_growth_effect_page():
        return {}
    main_models = read_csv("growth_effect_main_models")
    sample_comparison_models = read_csv("growth_effect_sample_comparison_models")
    robustness_models = read_csv("growth_effect_robustness_models")
    income_bin_slopes = read_csv("growth_effect_income_bin_slopes")
    threshold_scan = read_csv("growth_effect_threshold_scan")
    diagnostics = read_csv("growth_effect_sample_diagnostics")

    model_required = {
        "model_label", "sample", "flow", "dimension", "metric", "outcome",
        "term", "coefficient", "std_error", "p_value", "nobs", "clusters", "status", "horizon",
    }
    for name, frame in [
        ("growth-effect main models", main_models),
        ("growth-effect sample-comparison models", sample_comparison_models),
        ("growth-effect robustness models", robustness_models),
    ]:
        require_columns(frame, name, model_required)
    require_columns(sample_comparison_models, "growth-effect sample-comparison models", {"sample_definition"})
    require_columns(income_bin_slopes, "growth-effect income-bin slopes", {"model_label", "sample", "flow", "dimension", "metric", "outcome", "horizon", "row_type", "label", "export_level_bin", "term", "coefficient", "std_error", "p_value", "bh_q_value", "low_middle_export_cutoff", "middle_high_export_cutoff", "nobs", "clusters", "status"})
    require_columns(threshold_scan, "growth-effect threshold scan", {"model_label", "sample", "flow", "dimension", "metric", "outcome", "horizon", "threshold_percentile", "row_type", "label", "term", "threshold_exports_constant_2015_usd", "coefficient", "std_error", "p_value", "bh_q_value", "nobs", "clusters", "status"})
    require_columns(diagnostics, "growth-effect sample diagnostics", {"diagnostic", "value"})
    stale_cols = {"exposure", "exposure_label", "income_bin", "threshold_income_2015_usd"}
    stale_present = stale_cols & (
        set(main_models.columns)
        | set(sample_comparison_models.columns)
        | set(income_bin_slopes.columns)
        | set(threshold_scan.columns)
    )
    if stale_present:
        raise RuntimeError(f"growth-effect artifacts have stale GDP/GNI schema columns: {sorted(stale_present)}")

    text_cols = {"model_label", "sample", "flow", "dimension", "metric", "outcome", "term", "row_type", "label", "export_level_bin", "status", "dropped_regressors", "fixed_effects", "se_method", "cluster_col", "p_value_reference"}
    main_models = numeric_columns(main_models, text_cols)
    sample_comparison_models = numeric_columns(sample_comparison_models, text_cols | {"sample_definition"})
    robustness_models = numeric_columns(robustness_models, text_cols)
    income_bin_slopes = numeric_columns(income_bin_slopes, text_cols)
    threshold_scan = numeric_columns(threshold_scan, text_cols)

    primary = main_models[main_models["term"].eq("prior_export_growth")].copy()
    primary_ok = primary[primary["status"].eq("ok")].copy()
    strongest_abs = primary_ok.assign(abs_coef=primary_ok["coefficient"].abs()).sort_values("abs_coef", ascending=False).head(1) if not primary_ok.empty else pd.DataFrame()
    leveling_rows = income_bin_slopes[income_bin_slopes["row_type"].eq("difference") & income_bin_slopes["status"].eq("ok") & income_bin_slopes["bh_q_value"].notna()].copy()
    leveling_strongest = leveling_rows.assign(abs_diff=leveling_rows["coefficient"].abs()).sort_values("abs_diff", ascending=False).head(1) if not leveling_rows.empty else pd.DataFrame()
    slope_rows = income_bin_slopes[income_bin_slopes["row_type"].eq("slope")]
    main_cutoffs = {}
    if not slope_rows.empty:
        first = slope_rows.iloc[0]
        main_cutoffs = {"low_middle_export_cutoff": clean_scalar(first.get("low_middle_export_cutoff")), "middle_high_export_cutoff": clean_scalar(first.get("middle_high_export_cutoff"))}
    return {
        "main_models": clean_records(main_models, list(main_models.columns)),
        "sample_comparison_models": clean_records(sample_comparison_models, list(sample_comparison_models.columns)),
        "robustness_models": clean_records(robustness_models, list(robustness_models.columns)),
        "income_bin_slopes": clean_records(income_bin_slopes, list(income_bin_slopes.columns)),
        "threshold_scan": clean_records(threshold_scan, list(threshold_scan.columns)),
        "sample_diagnostics": clean_records(diagnostics, list(diagnostics.columns)),
        "strongest_absolute": clean_records(strongest_abs, list(strongest_abs.columns))[0] if not strongest_abs.empty else {},
        "leveling_strongest": clean_records(leveling_strongest, list(leveling_strongest.columns))[0] if not leveling_strongest.empty else {},
        "cutoffs": main_cutoffs,
        "horizons": sorted(int(value) for value in pd.to_numeric(main_models["horizon"], errors="coerce").dropna().unique()),
    }


def load_future_growth_data() -> dict[str, Any]:
    if not include_future_growth_page():
        return {}
    panel = read_csv("future_growth_panel")
    bucket_summary = read_csv("future_growth_bucket_summary")
    country_examples = read_csv("future_growth_country_examples")
    bucket_models = read_csv("future_growth_bucket_models")
    continuous_models = read_csv("future_growth_continuous_models")
    paired_models = read_csv("future_growth_paired_models")
    robustness_models = read_csv("future_growth_robustness_models")
    base_size_bin_summary = read_csv("future_growth_base_size_bin_summary")
    base_size_sensitivity_models = read_csv("future_growth_base_size_sensitivity_models")
    mechanism_channel_panel = read_csv("future_growth_mechanism_channel_panel")
    mechanism_channel_models = read_csv("future_growth_mechanism_channel_models")
    mechanism_summary = read_csv("future_growth_mechanism_summary")
    mechanism_diagnostics = read_csv("future_growth_mechanism_diagnostics")
    leave_one_country_out = read_csv("future_growth_leave_one_country_out_influence")
    diagnostics = read_csv("future_growth_sample_diagnostics")
    missing_controls = read_csv("future_growth_missing_controls")

    size_adjusted_cols = [
        "size_adjusted_observations",
        "mean_size_adjusted_annualized_log_growth",
        "median_size_adjusted_annualized_log_growth",
    ]
    if "size_adjusted_annualized_real_export_growth_log" not in panel.columns or any(
        col not in bucket_summary.columns for col in size_adjusted_cols
    ):
        import run_future_growth_concentration as future_growth_runner

        panel = future_growth_runner.add_size_adjusted_growth(panel)
        adjusted_summary = future_growth_runner.bucket_summary(panel)
        merge_keys = ["flow", "horizon", "concentration_bucket"]
        available_adjusted_cols = [col for col in size_adjusted_cols if col in adjusted_summary.columns]
        bucket_summary = bucket_summary.drop(columns=available_adjusted_cols, errors="ignore").merge(
            adjusted_summary[merge_keys + available_adjusted_cols],
            on=merge_keys,
            how="left",
            validate="one_to_one",
        )

    require_columns(
        panel,
        "future-growth panel",
        {
            "country",
            "iso3",
            "reporter_code",
            "year",
            "flow",
            "horizon",
            "future_year",
            "base_exports",
            "future_exports",
            "base_exports_constant_2015_usd",
            "future_exports_constant_2015_usd",
            "annualized_real_export_growth_log",
            "size_adjusted_annualized_real_export_growth_log",
            "log_initial_exports_constant_2015_usd",
            "oil_export_share",
            "log_gdp_constant_2015_usd",
            "log_population",
            "log_gni_per_capita_constant_2015_usd",
            "product_gini",
            "partner_gini",
            "product_partner_cell_gini",
            "concentration_bucket",
        },
    )
    require_columns(
        bucket_summary,
        "future-growth bucket summary",
        {
            "flow",
            "horizon",
            "concentration_bucket",
            "observations",
            "countries",
            "mean_annualized_log_growth",
            "median_annualized_log_growth",
            "size_adjusted_observations",
            "mean_size_adjusted_annualized_log_growth",
            "median_size_adjusted_annualized_log_growth",
            "mean_real_export_growth_pct",
            "median_initial_exports_constant_2015_usd",
        },
    )
    require_columns(
        country_examples,
        "future-growth country examples",
        {
            "flow",
            "horizon",
            "example_type",
            "country",
            "iso3",
            "year",
            "future_year",
            "concentration_bucket",
            "annualized_real_export_growth_log",
            "base_exports",
            "future_exports",
            "base_exports_constant_2015_usd",
            "future_exports_constant_2015_usd",
            "product_gini",
            "partner_gini",
            "product_partner_cell_gini",
        },
    )
    model_required = {
        "model_label",
        "sample",
        "flow",
        "dimension",
        "metric",
        "outcome",
        "term",
        "coefficient",
        "std_error",
        "p_value",
        "bh_q_value",
        "nobs",
        "clusters",
        "status",
        "horizon",
    }
    for name, frame in [
        ("future-growth bucket models", bucket_models),
        ("future-growth continuous models", continuous_models),
        ("future-growth paired models", paired_models),
        ("future-growth robustness models", robustness_models),
        ("future-growth base-size sensitivity models", base_size_sensitivity_models),
        ("future-growth mechanism channel models", mechanism_channel_models),
    ]:
        require_columns(frame, name, model_required)
    require_columns(
        base_size_bin_summary,
        "future-growth base-size bin summary",
        {
            "flow",
            "horizon",
            "base_size_bin",
            "concentration_bucket",
            "observations",
            "countries",
            "mean_annualized_log_growth",
            "mean_size_adjusted_annualized_log_growth",
            "mean_annualized_real_export_change_constant_2015_usd",
            "mean_annualized_asinh_real_export_change",
            "median_initial_exports_constant_2015_usd",
        },
    )
    require_columns(
        mechanism_channel_panel,
        "future-growth mechanism channel panel",
        {
            "reporter_code",
            "year",
            "future_year",
            "horizon",
            "flow",
            "concentration_bucket",
            "net_new_product_gross_positive_share",
            "new_partner_existing_product_gross_positive_share",
            "new_cell_existing_product_partner_gross_positive_share",
            "annualized_log_product_active_count_change",
            "annualized_log_partner_active_count_change",
        },
    )
    require_columns(
        mechanism_summary,
        "future-growth mechanism summary",
        {"test_id", "test_label", "estimate", "unit", "p_value", "bh_q_value", "nobs", "interpretation"},
    )
    require_columns(mechanism_diagnostics, "future-growth mechanism diagnostics", {"diagnostic", "value"})
    require_columns(
        leave_one_country_out,
        "future-growth leave-one-country-out influence",
        {"omitted_reporter_code", "omitted_country", "omitted_iso3", "term", "coefficient", "p_value", "nobs", "clusters", "status"},
    )
    require_columns(diagnostics, "future-growth sample diagnostics", {"diagnostic", "value"})
    require_columns(
        missing_controls,
        "future-growth missing controls",
        {
            "country",
            "iso3",
            "reporter_code",
            "year",
            "future_year",
            "horizon",
            "flow",
            "annualized_real_export_growth_log",
            "log_initial_exports_constant_2015_usd",
            "oil_export_share",
            "log_gdp_constant_2015_usd",
            "log_population",
            "log_gni_per_capita_constant_2015_usd",
        },
    )

    panel_key_cols = ["reporter_code", "year", "future_year", "horizon", "flow"]
    duplicates = panel.duplicated(panel_key_cols, keep=False)
    if duplicates.any():
        examples = panel.loc[duplicates, panel_key_cols].head(10).to_dict(orient="records")
        raise RuntimeError(f"Future-growth panel has duplicate website keys: {examples}")
    if set(panel["flow"].astype(str).unique()) != {"Exports", "Imports"}:
        raise RuntimeError("Future-growth panel must preserve both export and import exposure flows.")

    text_cols = {
        "country",
        "iso3",
        "flow",
        "variant",
        "region",
        "income_group",
        "metadata_source",
        "region_year",
        "concentration_bucket",
        "example_type",
        "model_label",
        "sample",
        "dimension",
        "metric",
        "outcome",
        "term",
        "status",
        "dropped_regressors",
        "fixed_effects",
        "se_method",
        "cluster_col",
        "p_value_reference",
        "diagnostic",
        "value",
    }
    bucket_summary = numeric_columns(bucket_summary, text_cols)
    country_examples = numeric_columns(country_examples, text_cols)
    bucket_models = numeric_columns(bucket_models, text_cols)
    continuous_models = numeric_columns(continuous_models, text_cols)
    paired_models = numeric_columns(paired_models, text_cols)
    robustness_models = numeric_columns(robustness_models, text_cols)
    base_size_bin_summary = numeric_columns(base_size_bin_summary, text_cols | {"base_size_bin"})
    base_size_sensitivity_models = numeric_columns(base_size_sensitivity_models, text_cols | {"test_family"})
    mechanism_channel_panel = numeric_columns(mechanism_channel_panel, text_cols | {"base_size_bin"})
    mechanism_channel_models = numeric_columns(mechanism_channel_models, text_cols | {"outcome_label", "test_family"})
    mechanism_summary = numeric_columns(mechanism_summary, text_cols | {"test_id", "test_label", "unit", "interpretation"})
    mechanism_diagnostics = numeric_columns(mechanism_diagnostics, text_cols)
    leave_one_country_out = numeric_columns(
        leave_one_country_out,
        text_cols | {"omitted_country", "omitted_iso3"},
    )
    diagnostics = numeric_columns(diagnostics, text_cols)
    missing_controls = numeric_columns(missing_controls, text_cols)

    continuous_ok = continuous_models[continuous_models["status"].eq("ok")].copy()
    strongest_abs = (
        continuous_ok.assign(abs_coef=continuous_ok["coefficient"].abs()).sort_values("abs_coef", ascending=False).head(1)
        if not continuous_ok.empty
        else pd.DataFrame()
    )
    gini_terms = {"product_gini", "partner_gini", "product_partner_cell_gini"}
    continuous_focus = continuous_models[
        continuous_models["metric"].eq("gini") & continuous_models["term"].isin(gini_terms)
    ].copy()
    paired_focus = paired_models[
        paired_models["metric"].eq("gini") & paired_models["term"].isin({"product_exposure", "partner_exposure", "product_x_partner"})
    ].copy()
    robustness_focus = robustness_models[
        robustness_models["metric"].eq("gini")
        & robustness_models["term"].isin(gini_terms | {"prior_export_growth_control"})
        & robustness_models["horizon"].eq(5)
    ].copy()
    mechanism_focus = mechanism_channel_models[
        mechanism_channel_models["term"].eq("bucket_high_product_low_partner")
        & mechanism_channel_models["horizon"].eq(5)
        & mechanism_channel_models["flow"].eq("Exports")
    ].copy()
    base_size_focus = base_size_sensitivity_models[
        base_size_sensitivity_models["term"].eq("bucket_high_product_low_partner")
        & base_size_sensitivity_models["horizon"].eq(5)
        & base_size_sensitivity_models["flow"].eq("Exports")
    ].copy()
    base_size_bin_focus = base_size_bin_summary[
        base_size_bin_summary["horizon"].eq(5)
        & base_size_bin_summary["flow"].eq("Exports")
    ].copy()
    bucket_focus = bucket_models[
        bucket_models["term"].isin(
            {
                "bucket_high_product_high_partner",
                "bucket_high_product_low_partner",
                "bucket_low_product_high_partner",
            }
        )
    ].copy()

    return {
        "bucket_summary": clean_records(bucket_summary.sort_values(["flow", "horizon", "concentration_bucket"]), list(bucket_summary.columns)),
        "country_examples": clean_records(country_examples.sort_values(["flow", "horizon", "example_type", "country"]), list(country_examples.columns)),
        "bucket_models": clean_records(bucket_models, list(bucket_models.columns)),
        "continuous_models": clean_records(continuous_models, list(continuous_models.columns)),
        "paired_models": clean_records(paired_models, list(paired_models.columns)),
        "robustness_models": clean_records(robustness_models, list(robustness_models.columns)),
        "base_size_bin_summary": clean_records(base_size_bin_summary, list(base_size_bin_summary.columns)),
        "base_size_sensitivity_models": clean_records(base_size_sensitivity_models, list(base_size_sensitivity_models.columns)),
        "mechanism_channel_models": clean_records(mechanism_channel_models, list(mechanism_channel_models.columns)),
        "mechanism_summary": clean_records(mechanism_summary, list(mechanism_summary.columns)),
        "mechanism_diagnostics": clean_records(mechanism_diagnostics, list(mechanism_diagnostics.columns)),
        "leave_one_country_out_influence": clean_records(leave_one_country_out, list(leave_one_country_out.columns)),
        "bucket_focus": clean_records(bucket_focus.sort_values(["flow", "horizon", "term"]), list(bucket_focus.columns)),
        "continuous_focus": clean_records(continuous_focus.sort_values(["flow", "horizon", "dimension"]), list(continuous_focus.columns)),
        "paired_focus": clean_records(paired_focus.sort_values(["flow", "horizon", "term"]), list(paired_focus.columns)),
        "robustness_focus": clean_records(robustness_focus.sort_values(["model_label", "flow", "dimension", "term"]), list(robustness_focus.columns)),
        "base_size_focus": clean_records(base_size_focus.sort_values(["model_label", "outcome", "term"]), list(base_size_focus.columns)),
        "mechanism_focus": clean_records(mechanism_focus.sort_values(["model_label", "outcome", "term"]), list(mechanism_focus.columns)),
        "base_size_bin_focus": clean_records(base_size_bin_focus.sort_values(["base_size_bin", "concentration_bucket"]), list(base_size_bin_focus.columns)),
        "sample_diagnostics": clean_records(diagnostics, list(diagnostics.columns)),
        "mechanism_diagnostics_focus": clean_records(mechanism_diagnostics, list(mechanism_diagnostics.columns)),
        "missing_controls_summary": clean_records(
            missing_controls.groupby(["flow", "horizon"], as_index=False).size().rename(columns={"size": "missing_required_rows"}),
            ["flow", "horizon", "missing_required_rows"],
        ),
        "strongest_absolute": clean_records(strongest_abs, list(strongest_abs.columns))[0] if not strongest_abs.empty else {},
        "panel_rows": int(len(panel)),
        "panel_countries": int(panel["reporter_code"].nunique()),
        "panel_year_min": int(pd.to_numeric(panel["year"], errors="coerce").min()),
        "panel_year_max": int(pd.to_numeric(panel["year"], errors="coerce").max()),
        "mechanism_channel_panel_rows": int(len(mechanism_channel_panel)),
    }


def load_partner_stability_data() -> dict[str, Any]:
    if not include_partner_stability_page():
        return {}
    country_flow = read_csv("partner_stability_country_flow")
    summary = read_csv("partner_stability_summary")
    common_trends = read_csv("partner_stability_common_trends")
    variance_decomposition = read_csv("partner_stability_variance_decomposition")
    low_active_sensitivity = read_csv("partner_stability_low_active_sensitivity")

    require_columns(
        country_flow,
        "Partner-Gini stability country-flow table",
        {
            "country",
            "iso3",
            "reporter_code",
            "flow",
            "n_years",
            "first_year",
            "last_year",
            "first_partner_gini",
            "last_partner_gini",
            "endpoint_change",
            "abs_endpoint_change",
            "mean_partner_gini",
            "sd_partner_gini",
            "first_partner_active_count",
            "last_partner_active_count",
            "min_partner_active_count",
            "median_partner_active_count",
            "mean_partner_active_count",
            "slope_per_decade",
            "slope_p_value",
            "slope_q_value",
            "abs_slope_per_decade",
            "stable_slope_10yr_0p02",
            "stable_endpoint_0p05",
            "window",
        },
    )
    require_columns(
        summary,
        "Partner-Gini stability summary",
        {
            "window",
            "flow",
            "countries",
            "median_abs_slope_per_decade",
            "p90_abs_slope_per_decade",
            "share_stable_slope_10yr_0p02",
            "share_stable_endpoint_0p05",
            "median_abs_endpoint_change",
            "p90_abs_endpoint_change",
            "median_within_country_sd",
            "countries_with_slope_q_lt_0p05",
            "share_abs_slope_10yr_le_0p01",
            "share_abs_slope_10yr_le_0p02",
            "share_abs_slope_10yr_le_0p03",
            "share_abs_slope_10yr_le_0p05",
            "share_abs_endpoint_le_0p03",
            "share_abs_endpoint_le_0p05",
            "share_abs_endpoint_le_0p1",
        },
    )
    require_columns(
        common_trends,
        "Partner-Gini stability common trends",
        {
            "window",
            "flow",
            "coefficient_per_decade",
            "std_error_per_decade",
            "ci_low_per_decade",
            "ci_high_per_decade",
            "p_value",
            "bh_q_value",
            "nobs",
            "countries",
            "r_squared",
            "status",
        },
    )
    require_columns(
        variance_decomposition,
        "Partner-Gini stability variance decomposition",
        {
            "window",
            "flow",
            "nobs",
            "countries",
            "years",
            "r2_country_fe",
            "r2_country_year_fe",
            "incremental_r2_year_fe",
            "rmse_country_fe",
            "rmse_country_year_fe",
        },
    )
    require_columns(
        low_active_sensitivity,
        "Partner-Gini low-active-partner sensitivity",
        {
            "window",
            "flow",
            "min_partner_active_count_required",
            "original_rows",
            "kept_rows",
            "dropped_rows",
            "original_country_flows",
            "eligible_country_flows",
            "countries",
            "median_abs_slope_per_decade",
            "share_stable_slope_10yr_0p02",
            "median_abs_endpoint_change",
            "share_stable_endpoint_0p05",
        },
    )

    text_columns = {"country", "iso3", "flow", "window", "slope_se_method", "status", "stars"}
    for frame in [country_flow, summary, common_trends, variance_decomposition, low_active_sensitivity]:
        for column in frame.columns:
            if column in text_columns:
                continue
            converted = pd.to_numeric(frame[column], errors="coerce")
            if converted.notna().any():
                frame[column] = converted

    country_flow = country_flow.sort_values(["window", "flow", "country"]).reset_index(drop=True)
    summary = summary.sort_values(["window", "flow"]).reset_index(drop=True)
    common_trends = common_trends.sort_values(["window", "flow"]).reset_index(drop=True)
    variance_decomposition = variance_decomposition.sort_values(["window", "flow"]).reset_index(drop=True)
    low_active_sensitivity = low_active_sensitivity.sort_values(["window", "flow"]).reset_index(drop=True)
    main_exceptions = (
        country_flow[country_flow["window"].eq("main_2000_2024")]
        .sort_values(["abs_endpoint_change", "abs_slope_per_decade"], ascending=[False, False])
        .head(12)
        .reset_index(drop=True)
    )
    manifest_path = sample_results_base(ACTIVE_SITE_SAMPLE) / "run_manifest_partner_gini_stability.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}

    return {
        "manifest": manifest,
        "summary": clean_records(summary, list(summary.columns)),
        "common_trends": clean_records(common_trends, list(common_trends.columns)),
        "variance_decomposition": clean_records(variance_decomposition, list(variance_decomposition.columns)),
        "low_active_sensitivity": clean_records(low_active_sensitivity, list(low_active_sensitivity.columns)),
        "country_flow": clean_records(country_flow, list(country_flow.columns)),
        "main_exceptions": clean_records(main_exceptions, list(main_exceptions.columns)),
    }


def validate_ex12_extensive_validation(
    validation: dict[str, Any],
    *,
    latest: pd.DataFrame,
    summary: pd.DataFrame,
    country_weighted_summary: pd.DataFrame,
    product_robustness: pd.DataFrame,
    overlapping: pd.DataFrame,
    expected_country_count: int = 60,
) -> None:
    """Fail the site build rather than publishing stale or blocked Ex. 12 artifacts."""
    blockers: list[str] = []
    if validation.get("status") != "ok":
        blockers.append(f"validation status is {validation.get('status')!r}")
    if validation.get("blockers"):
        blockers.append(f"validation blockers are present: {validation.get('blockers')}")
    for key in ["country_count_expected", "country_count_decomposition", "country_count_latest"]:
        if int(validation.get(key) or 0) != expected_country_count:
            blockers.append(f"{key} is {validation.get(key)!r}, expected {expected_country_count}")
    if int(latest["reporter_code"].nunique()) != expected_country_count:
        blockers.append("latest table does not include exactly 60 reporter countries")
    if len(latest) != expected_country_count * 2:
        blockers.append("latest table does not include one 5-year and one 10-year row for each reporter")
    expected_modes = {"hs6_harmonized_family", "hs4", "hs2"}
    expected_horizons = {5, 10}
    if set(validation.get("identity_modes") or []) != expected_modes:
        blockers.append(f"identity modes are {validation.get('identity_modes')!r}, expected {sorted(expected_modes)}")
    if {int(h) for h in (validation.get("horizons") or [])} != expected_horizons:
        blockers.append(f"horizons are {validation.get('horizons')!r}, expected {sorted(expected_horizons)}")
    for name, frame in [
        ("summary", summary),
        ("equal-country summary", country_weighted_summary),
        ("product robustness", product_robustness),
        ("overlap robustness", overlapping),
    ]:
        if not expected_modes.issubset(set(frame["identity_mode"].astype(str).unique())):
            blockers.append(f"{name} is missing an expected identity mode")
        present_horizons = {int(value) for value in pd.to_numeric(frame["horizon"], errors="coerce").dropna().unique()}
        if not expected_horizons.issubset(present_horizons):
            blockers.append(f"{name} is missing an expected horizon")
    if int(validation.get("source_hs6_999999_rows_after_filters") or 0) != 0:
        blockers.append("filtered source values contain HS6 999999")
    if int(validation.get("source_partner_code_0_rows_after_filters") or 0) != 0:
        blockers.append("filtered source values contain partner_code 0")
    if int(validation.get("duplicate_category_keys") or 0) != 0:
        blockers.append("duplicate mutually exclusive category keys are present")
    if int(validation.get("category_accounting_residual_violations") or 0) != 0:
        blockers.append("category accounting residual violations are present")
    if int(validation.get("hs_harmonization_missing_rows") or 0) != 0:
        blockers.append("LT/HGL HS1992 conversion is missing filtered source rows")
    if blockers:
        raise RuntimeError("Exercise 12 extensive-margin artifacts failed website validation: " + "; ".join(blockers))


def validate_ex12_ev_hs4_validation(
    validation: dict[str, Any],
    *,
    latest_5y: pd.DataFrame,
    pooled_summary: pd.DataFrame,
    expected_country_count: int = 60,
) -> None:
    blockers: list[str] = []
    if validation.get("status") != "ok":
        blockers.append(f"validation status is {validation.get('status')!r}")
    if validation.get("blockers"):
        blockers.append(f"validation blockers are present: {validation.get('blockers')}")
    for key in ["country_count_expected", "country_count_product_decomposition", "country_count_latest_5y"]:
        if int(validation.get(key) or 0) != expected_country_count:
            blockers.append(f"{key} is {validation.get(key)!r}, expected {expected_country_count}")
    for key in ["country_count_combined_decomposition", "country_count_combined_latest_5y"]:
        if int(validation.get(key) or 0) != expected_country_count:
            blockers.append(f"{key} is {validation.get(key)!r}, expected {expected_country_count}")
    if int(latest_5y["reporter_code"].nunique()) != expected_country_count:
        blockers.append("latest EV-style HS4 table does not include exactly 60 reporter countries")
    if validation.get("product_level") != "hs4":
        blockers.append(f"product level is {validation.get('product_level')!r}, expected 'hs4'")
    if float(validation.get("active_threshold_usd_2024") or 0.0) != 50_000.0:
        blockers.append("active threshold is not $50,000 in 2024 USD")
    if int(validation.get("constant_usd_year") or 0) != 2024:
        blockers.append("constant-dollar base year is not 2024")
    if {int(h) for h in (validation.get("horizons") or [])} != {5, 10}:
        blockers.append(f"horizons are {validation.get('horizons')!r}, expected [5, 10]")
    if int(validation.get("source_hs6_999999_rows_after_filters") or 0) != 0:
        blockers.append("filtered source values contain HS6 999999")
    if int(validation.get("source_partner_code_0_rows_after_filters") or 0) != 0:
        blockers.append("filtered source values contain partner_code 0")
    if int(validation.get("duplicate_product_channel_keys") or 0) != 0:
        blockers.append("duplicate product channel keys are present")
    if int(validation.get("product_accounting_residual_violations") or 0) != 0:
        blockers.append("product accounting residual violations are present")
    if int(validation.get("duplicate_combined_channel_keys") or 0) != 0:
        blockers.append("duplicate combined channel keys are present")
    if int(validation.get("combined_accounting_residual_violations") or 0) != 0:
        blockers.append("combined accounting residual violations are present")
    product_h5 = pooled_summary[
        pooled_summary["channel_type"].astype(str).eq("product") & pd.to_numeric(pooled_summary["horizon"], errors="coerce").eq(5)
    ]
    if product_h5.empty:
        blockers.append("pooled summary is missing product horizon-5 rows")
    else:
        share_sum = pd.to_numeric(product_h5["pooled_positive_expansion_share"], errors="coerce").sum()
        if not np.isfinite(share_sum) or abs(float(share_sum) - 1.0) > 1e-6:
            blockers.append(f"horizon-5 product pooled positive-expansion shares sum to {share_sum}, not 1")
    if blockers:
        raise RuntimeError("Exercise 12 EV-style HS4 artifacts failed website validation: " + "; ".join(blockers))


def load_ex12_extensive_margin_data() -> dict[str, Any]:
    if not include_ex12_extensive_margin():
        return {}
    country_year = read_csv("ex12_extensive_country_year")
    latest = read_csv("ex12_extensive_latest")
    summary = read_csv("ex12_extensive_summary")
    country_weighted_summary = read_csv("ex12_extensive_country_weighted_summary")
    overlapping = read_csv("ex12_extensive_overlapping_robustness")
    product_robustness = read_csv("ex12_extensive_product_entry_robustness")
    validation_path = sample_results_base(ACTIVE_SITE_SAMPLE) / "exercise_12_extensive_margin_tables/extensive_margin_validation.json"
    if not validation_path.exists():
        raise FileNotFoundError(f"Exercise 12 extensive-margin validation JSON is missing: {validation_path}")
    validation = json.loads(validation_path.read_text(encoding="utf-8"))

    require_columns(
        country_year,
        "Exercise 12 extensive-margin country-year",
        {
            "country",
            "iso3",
            "reporter_code",
            "base_year",
            "future_year",
            "horizon",
            "identity_mode",
            "category",
            "category_label",
            "category_order",
            "net_contribution",
            "gross_positive_contribution",
            "gross_contraction",
            "total_growth",
            "gross_positive_share",
            "net_growth_share",
        },
    )
    require_columns(
        latest,
        "Exercise 12 extensive-margin latest",
        {
            "country",
            "iso3",
            "reporter_code",
            "horizon",
            "base_year",
            "future_year",
            "total_growth",
            "total_gross_positive_growth",
            "net_new_product_gross_positive_share",
            "net_new_partner_existing_product_gross_positive_share",
            "new_product_partner_cell_existing_product_partner_gross_positive_share",
            "existing_product_partner_cell_growth_gross_positive_share",
            "existing_product_partner_cell_contraction_net_contribution",
        },
    )
    require_columns(
        summary,
        "Exercise 12 extensive-margin summary",
        {
            "identity_mode",
            "horizon",
            "category",
            "category_label",
            "category_order",
            "countries",
            "median_gross_positive_share",
            "median_net_growth_share",
            "median_cell_count",
            "median_product_count",
            "median_partner_count",
        },
    )
    require_columns(
        country_weighted_summary,
        "Exercise 12 extensive-margin equal-country summary",
        {
            "identity_mode",
            "horizon",
            "category",
            "category_label",
            "category_order",
            "countries",
            "min_country_year_pairs",
            "median_country_year_pairs",
            "max_country_year_pairs",
            "median_country_median_gross_positive_share",
            "median_country_median_net_growth_share",
            "median_country_median_cell_count",
            "summary_weighting",
        },
    )
    require_columns(
        product_robustness,
        "Exercise 12 extensive-margin product robustness",
        {
            "country",
            "iso3",
            "reporter_code",
            "horizon",
            "identity_mode",
            "product_definition",
            "product_definition_label",
            "gross_positive_share",
            "net_growth_share",
            "product_count",
        },
    )
    require_columns(
        overlapping,
        "Exercise 12 extensive-margin overlapping robustness",
        {
            "country",
            "iso3",
            "reporter_code",
            "horizon",
            "identity_mode",
            "overlap_channel",
            "overlap_channel_label",
            "gross_positive_share",
            "net_growth_share",
        },
    )

    text_cols = {
        "country",
        "iso3",
        "identity_mode",
        "category",
        "category_label",
        "product_definition",
        "product_definition_label",
        "overlap_channel",
        "overlap_channel_label",
    }


def load_ex12_ev_hs4_expansion_data() -> dict[str, Any]:
    if not include_ex12_ev_hs4_expansion():
        return {}
    country_window = read_csv("ex12_ev_hs4_country_window")
    partner_spread = read_csv("ex12_ev_hs4_partner_spread")
    combined_country_window = read_csv("ex12_ev_hs4_combined_country_window")
    combined_pooled_summary = read_csv("ex12_ev_hs4_combined_pooled_summary")
    combined_equal_country_summary = read_csv("ex12_ev_hs4_combined_equal_country_summary")
    combined_latest_5y = read_csv("ex12_ev_hs4_combined_latest_5y")
    pooled_summary = read_csv("ex12_ev_hs4_pooled_summary")
    equal_country_summary = read_csv("ex12_ev_hs4_equal_country_summary")
    latest_5y = read_csv("ex12_ev_hs4_latest_5y")
    bottom10 = read_csv("ex12_ev_hs4_bottom10_robustness")
    bottom10_summary = read_csv("ex12_ev_hs4_bottom10_robustness_summary")
    validation_path = sample_results_base(ACTIVE_SITE_SAMPLE) / "exercise_12_ev_hs4_expansion_tables/ev_hs4_validation.json"
    if not validation_path.exists():
        raise FileNotFoundError(f"Exercise 12 EV-style HS4 validation JSON is missing: {validation_path}")
    validation = json.loads(validation_path.read_text(encoding="utf-8"))

    require_columns(
        country_window,
        "Exercise 12 EV-style HS4 country-window decomposition",
        {
            "country",
            "iso3",
            "reporter_code",
            "base_window",
            "future_window",
            "horizon",
            "product_level",
            "active_threshold_usd_2024",
            "channel_type",
            "channel",
            "channel_label",
            "positive_expansion_2024_usd",
            "net_contribution_2024_usd",
            "total_positive_expansion_2024_usd",
            "total_net_growth_2024_usd",
            "positive_expansion_share",
            "net_growth_share",
        },
    )
    require_columns(
        pooled_summary,
        "Exercise 12 EV-style HS4 pooled summary",
        {
            "channel_type",
            "horizon",
            "channel",
            "channel_label",
            "countries",
            "country_windows",
            "pooled_positive_expansion_share",
            "pooled_net_growth_share",
            "pooled_within_positive_expansion_share",
            "pooled_within_net_growth_share",
            "positive_expansion_2024_usd",
            "net_contribution_2024_usd",
        },
    )
    require_columns(
        combined_country_window,
        "Exercise 12 EV-style HS4 combined country-window decomposition",
        {
            "country",
            "iso3",
            "reporter_code",
            "base_window",
            "future_window",
            "horizon",
            "channel_type",
            "channel_type_label",
            "channel",
            "channel_label",
            "positive_expansion_2024_usd",
            "net_contribution_2024_usd",
            "total_positive_expansion_2024_usd",
            "total_net_growth_2024_usd",
            "positive_expansion_share",
            "net_growth_share",
        },
    )
    require_columns(
        combined_pooled_summary,
        "Exercise 12 EV-style HS4 combined pooled summary",
        {
            "channel_type",
            "horizon",
            "channel",
            "channel_label",
            "countries",
            "country_windows",
            "pooled_positive_expansion_share",
            "pooled_net_growth_share",
            "positive_expansion_2024_usd",
            "net_contribution_2024_usd",
        },
    )
    require_columns(
        combined_equal_country_summary,
        "Exercise 12 EV-style HS4 combined equal-country summary",
        {
            "channel_type",
            "horizon",
            "channel",
            "channel_label",
            "countries",
            "median_country_windows",
            "equal_country_median_positive_expansion_share",
            "equal_country_median_net_growth_share",
            "summary_weighting",
        },
    )
    require_columns(
        combined_latest_5y,
        "Exercise 12 EV-style HS4 combined latest 5-year country table",
        {
            "country",
            "iso3",
            "reporter_code",
            "base_window",
            "future_window",
            "channel_type",
            "channel_type_label",
            "total_positive_expansion_2024_usd",
            "total_net_growth_2024_usd",
        },
    )
    require_columns(
        equal_country_summary,
        "Exercise 12 EV-style HS4 equal-country summary",
        {
            "channel_type",
            "horizon",
            "channel",
            "channel_label",
            "countries",
            "median_country_windows",
            "equal_country_median_positive_expansion_share",
            "equal_country_median_net_growth_share",
            "summary_weighting",
        },
    )
    require_columns(
        latest_5y,
        "Exercise 12 EV-style HS4 latest 5-year country table",
        {
            "country",
            "iso3",
            "reporter_code",
            "base_window",
            "future_window",
            "new_product_positive_expansion_share",
            "continuing_product_positive_expansion_share",
            "dying_product_positive_expansion_share",
            "below_threshold_residual_positive_expansion_share",
            "total_positive_expansion_2024_usd",
            "total_net_growth_2024_usd",
        },
    )
    require_columns(
        bottom10_summary,
        "Exercise 12 EV-style HS4 bottom-10 robustness summary",
        {
            "horizon",
            "product_definition",
            "product_definition_label",
            "countries",
            "pooled_positive_expansion_share",
            "pooled_net_growth_share",
        },
    )
    text_cols = {
        "country",
        "iso3",
        "base_window",
        "future_window",
        "product_level",
        "persistence_rule",
        "channel_type",
        "channel",
        "channel_label",
        "product_definition",
        "product_definition_label",
        "channel_type_label",
        "summary_weighting",
    }
    country_window = numeric_columns(country_window, text_cols)
    partner_spread = numeric_columns(partner_spread, text_cols)
    combined_country_window = numeric_columns(combined_country_window, text_cols)
    combined_pooled_summary = numeric_columns(combined_pooled_summary, text_cols)
    combined_equal_country_summary = numeric_columns(combined_equal_country_summary, text_cols)
    combined_latest_5y = numeric_columns(combined_latest_5y, text_cols)
    pooled_summary = numeric_columns(pooled_summary, text_cols)
    equal_country_summary = numeric_columns(equal_country_summary, text_cols)
    latest_5y = numeric_columns(latest_5y, text_cols)
    bottom10 = numeric_columns(bottom10, text_cols)
    bottom10_summary = numeric_columns(bottom10_summary, text_cols)
    validate_ex12_ev_hs4_validation(validation, latest_5y=latest_5y, pooled_summary=pooled_summary)
    product_summary = pooled_summary[pooled_summary["channel_type"].astype(str).eq("product")].copy()
    partner_summary = pooled_summary[pooled_summary["channel_type"].astype(str).eq("partner_spread_continuing_hs4")].copy()
    product_equal_country_summary = equal_country_summary[equal_country_summary["channel_type"].astype(str).eq("product")].copy()
    combined_product_first_summary = combined_pooled_summary[
        combined_pooled_summary["channel_type"].astype(str).eq("combined_product_first")
    ].copy()
    combined_partner_first_summary = combined_pooled_summary[
        combined_pooled_summary["channel_type"].astype(str).eq("combined_partner_first")
    ].copy()
    def clean_validation_value(value: Any) -> Any:
        if isinstance(value, list):
            return [clean_validation_value(item) for item in value]
        if isinstance(value, dict):
            return {inner_key: clean_validation_value(inner_value) for inner_key, inner_value in value.items()}
        return clean_scalar(value)

    validation_clean = {key: clean_validation_value(value) for key, value in validation.items()}
    return {
        "country_window": clean_records(country_window, list(country_window.columns)),
        "partner_spread": clean_records(partner_spread, list(partner_spread.columns)),
        "combined_country_window": clean_records(combined_country_window, list(combined_country_window.columns)),
        "combined_pooled_summary": clean_records(combined_pooled_summary, list(combined_pooled_summary.columns)),
        "combined_product_first_summary": clean_records(combined_product_first_summary, list(combined_product_first_summary.columns)),
        "combined_partner_first_summary": clean_records(combined_partner_first_summary, list(combined_partner_first_summary.columns)),
        "combined_equal_country_summary": clean_records(combined_equal_country_summary, list(combined_equal_country_summary.columns)),
        "combined_latest_5y": clean_records(combined_latest_5y.sort_values(["country", "channel_type"]), list(combined_latest_5y.columns)),
        "product_summary": clean_records(product_summary, list(product_summary.columns)),
        "partner_summary": clean_records(partner_summary, list(partner_summary.columns)),
        "equal_country_product_summary": clean_records(product_equal_country_summary, list(product_equal_country_summary.columns)),
        "latest_5y": clean_records(latest_5y.sort_values("country"), list(latest_5y.columns)),
        "bottom10": clean_records(bottom10, list(bottom10.columns)),
        "bottom10_summary": clean_records(bottom10_summary, list(bottom10_summary.columns)),
        "validation": validation_clean,
        "country_count": int(latest_5y["reporter_code"].nunique()),
    }


def validate_ex12_ev_expansion_validation(
    validation: dict[str, Any],
    *,
    latest_5y: pd.DataFrame,
    pooled_summary: pd.DataFrame,
    expected_product_level: str,
    label: str,
    expected_country_count: int = 60,
) -> None:
    blockers: list[str] = []
    if validation.get("status") != "ok":
        blockers.append(f"validation status is {validation.get('status')!r}")
    if validation.get("blockers"):
        blockers.append(f"validation blockers are present: {validation.get('blockers')}")
    for key in ["country_count_expected", "country_count_product_decomposition", "country_count_latest_5y"]:
        if int(validation.get(key) or 0) != expected_country_count:
            blockers.append(f"{key} is {validation.get(key)!r}, expected {expected_country_count}")
    for key in ["country_count_combined_decomposition", "country_count_combined_latest_5y"]:
        if int(validation.get(key) or 0) != expected_country_count:
            blockers.append(f"{key} is {validation.get(key)!r}, expected {expected_country_count}")
    if int(latest_5y["reporter_code"].nunique()) != expected_country_count:
        blockers.append(f"latest {label} table does not include exactly {expected_country_count} reporter countries")
    if validation.get("product_level") != expected_product_level:
        blockers.append(f"product level is {validation.get('product_level')!r}, expected {expected_product_level!r}")
    if float(validation.get("active_threshold_usd_2024") or 0.0) != 50_000.0:
        blockers.append("active threshold is not $50,000 in 2024 USD")
    if int(validation.get("constant_usd_year") or 0) != 2024:
        blockers.append("constant-dollar base year is not 2024")
    if {int(h) for h in (validation.get("horizons") or [])} != {5, 10}:
        blockers.append(f"horizons are {validation.get('horizons')!r}, expected [5, 10]")
    if int(validation.get("source_hs6_999999_rows_after_filters") or 0) != 0:
        blockers.append("filtered source values contain HS6 999999")
    if int(validation.get("source_partner_code_0_rows_after_filters") or 0) != 0:
        blockers.append("filtered source values contain partner_code 0")
    if int(validation.get("duplicate_product_channel_keys") or 0) != 0:
        blockers.append("duplicate product channel keys are present")
    if int(validation.get("product_accounting_residual_violations") or 0) != 0:
        blockers.append("product accounting residual violations are present")
    if int(validation.get("duplicate_combined_channel_keys") or 0) != 0:
        blockers.append("duplicate combined channel keys are present")
    if int(validation.get("combined_accounting_residual_violations") or 0) != 0:
        blockers.append("combined accounting residual violations are present")
    product_h5 = pooled_summary[
        pooled_summary["channel_type"].astype(str).eq("product")
        & pd.to_numeric(pooled_summary["horizon"], errors="coerce").eq(5)
    ]
    if product_h5.empty:
        blockers.append("pooled summary is missing product horizon-5 rows")
    else:
        share_sum = pd.to_numeric(product_h5["pooled_positive_expansion_share"], errors="coerce").sum()
        if not np.isfinite(share_sum) or abs(float(share_sum) - 1.0) > 1e-6:
            blockers.append(f"horizon-5 product pooled positive-expansion shares sum to {share_sum}, not 1")
    if expected_product_level == "hs6_harmonized_family":
        harmonization = validation.get("harmonization_value_diagnostics") or {}
        if not harmonization:
            blockers.append("HS6 harmonization diagnostics are missing")
        elif float(harmonization.get("unmatched_value_share") or 0.0) != 0.0:
            blockers.append("HS6 harmonization has unmatched trade value")
    if blockers:
        raise RuntimeError(f"Exercise 12 EV-style {label} artifacts failed website validation: " + "; ".join(blockers))


def load_ex12_ev_hs6_harmonized_expansion_data() -> dict[str, Any]:
    if not include_ex12_ev_hs6_harmonized_expansion():
        return {}
    country_window = read_csv("ex12_ev_hs6_harmonized_country_window")
    partner_spread = read_csv("ex12_ev_hs6_harmonized_partner_spread")
    combined_country_window = read_csv("ex12_ev_hs6_harmonized_combined_country_window")
    combined_pooled_summary = read_csv("ex12_ev_hs6_harmonized_combined_pooled_summary")
    combined_equal_country_summary = read_csv("ex12_ev_hs6_harmonized_combined_equal_country_summary")
    combined_latest_5y = read_csv("ex12_ev_hs6_harmonized_combined_latest_5y")
    pooled_summary = read_csv("ex12_ev_hs6_harmonized_pooled_summary")
    equal_country_summary = read_csv("ex12_ev_hs6_harmonized_equal_country_summary")
    latest_5y = read_csv("ex12_ev_hs6_harmonized_latest_5y")
    bottom10 = read_csv("ex12_ev_hs6_harmonized_bottom10_robustness")
    bottom10_summary = read_csv("ex12_ev_hs6_harmonized_bottom10_robustness_summary")
    validation_path = (
        sample_results_base(ACTIVE_SITE_SAMPLE)
        / "exercise_12_ev_hs6_harmonized_expansion_tables/ev_hs6_harmonized_validation.json"
    )
    if not validation_path.exists():
        raise FileNotFoundError(f"Exercise 12 EV-style harmonized-HS6 validation JSON is missing: {validation_path}")
    validation = json.loads(validation_path.read_text(encoding="utf-8"))

    require_columns(
        country_window,
        "Exercise 12 EV-style harmonized-HS6 country-window decomposition",
        {
            "country",
            "iso3",
            "reporter_code",
            "base_window",
            "future_window",
            "horizon",
            "product_level",
            "active_threshold_usd_2024",
            "channel_type",
            "channel",
            "channel_label",
            "positive_expansion_2024_usd",
            "net_contribution_2024_usd",
            "total_positive_expansion_2024_usd",
            "total_net_growth_2024_usd",
            "positive_expansion_share",
            "net_growth_share",
        },
    )
    require_columns(
        pooled_summary,
        "Exercise 12 EV-style harmonized-HS6 pooled summary",
        {
            "channel_type",
            "horizon",
            "channel",
            "channel_label",
            "countries",
            "country_windows",
            "pooled_positive_expansion_share",
            "pooled_net_growth_share",
            "pooled_within_positive_expansion_share",
            "pooled_within_net_growth_share",
            "positive_expansion_2024_usd",
            "net_contribution_2024_usd",
        },
    )
    require_columns(
        combined_country_window,
        "Exercise 12 EV-style harmonized-HS6 combined country-window decomposition",
        {
            "country",
            "iso3",
            "reporter_code",
            "base_window",
            "future_window",
            "horizon",
            "channel_type",
            "channel_type_label",
            "channel",
            "channel_label",
            "positive_expansion_2024_usd",
            "net_contribution_2024_usd",
            "total_positive_expansion_2024_usd",
            "total_net_growth_2024_usd",
            "positive_expansion_share",
            "net_growth_share",
        },
    )
    require_columns(
        combined_pooled_summary,
        "Exercise 12 EV-style harmonized-HS6 combined pooled summary",
        {
            "channel_type",
            "horizon",
            "channel",
            "channel_label",
            "countries",
            "country_windows",
            "pooled_positive_expansion_share",
            "pooled_net_growth_share",
            "positive_expansion_2024_usd",
            "net_contribution_2024_usd",
        },
    )
    require_columns(
        combined_equal_country_summary,
        "Exercise 12 EV-style harmonized-HS6 combined equal-country summary",
        {
            "channel_type",
            "horizon",
            "channel",
            "channel_label",
            "countries",
            "median_country_windows",
            "equal_country_median_positive_expansion_share",
            "equal_country_median_net_growth_share",
            "summary_weighting",
        },
    )
    require_columns(
        combined_latest_5y,
        "Exercise 12 EV-style harmonized-HS6 combined latest 5-year country table",
        {
            "country",
            "iso3",
            "reporter_code",
            "base_window",
            "future_window",
            "channel_type",
            "channel_type_label",
            "total_positive_expansion_2024_usd",
            "total_net_growth_2024_usd",
        },
    )
    require_columns(
        equal_country_summary,
        "Exercise 12 EV-style harmonized-HS6 equal-country summary",
        {
            "channel_type",
            "horizon",
            "channel",
            "channel_label",
            "countries",
            "median_country_windows",
            "equal_country_median_positive_expansion_share",
            "equal_country_median_net_growth_share",
            "summary_weighting",
        },
    )
    require_columns(
        latest_5y,
        "Exercise 12 EV-style harmonized-HS6 latest 5-year country table",
        {
            "country",
            "iso3",
            "reporter_code",
            "base_window",
            "future_window",
            "new_product_positive_expansion_share",
            "continuing_product_positive_expansion_share",
            "dying_product_positive_expansion_share",
            "below_threshold_residual_positive_expansion_share",
            "total_positive_expansion_2024_usd",
            "total_net_growth_2024_usd",
        },
    )
    require_columns(
        bottom10_summary,
        "Exercise 12 EV-style harmonized-HS6 bottom-10 robustness summary",
        {
            "horizon",
            "product_definition",
            "product_definition_label",
            "countries",
            "country_windows",
            "pooled_positive_expansion_share",
            "pooled_net_growth_share",
            "median_product_count",
        },
    )
    text_cols = {
        "country",
        "iso3",
        "base_window",
        "future_window",
        "product_level",
        "persistence_rule",
        "channel_type",
        "channel",
        "channel_label",
        "product_definition",
        "product_definition_label",
        "channel_type_label",
        "summary_weighting",
    }
    country_window = numeric_columns(country_window, text_cols)
    partner_spread = numeric_columns(partner_spread, text_cols)
    combined_country_window = numeric_columns(combined_country_window, text_cols)
    combined_pooled_summary = numeric_columns(combined_pooled_summary, text_cols)
    combined_equal_country_summary = numeric_columns(combined_equal_country_summary, text_cols)
    combined_latest_5y = numeric_columns(combined_latest_5y, text_cols)
    pooled_summary = numeric_columns(pooled_summary, text_cols)
    equal_country_summary = numeric_columns(equal_country_summary, text_cols)
    latest_5y = numeric_columns(latest_5y, text_cols)
    bottom10 = numeric_columns(bottom10, text_cols)
    bottom10_summary = numeric_columns(bottom10_summary, text_cols)
    validate_ex12_ev_expansion_validation(
        validation,
        latest_5y=latest_5y,
        pooled_summary=pooled_summary,
        expected_product_level="hs6_harmonized_family",
        label="harmonized-HS6",
    )
    product_summary = pooled_summary[pooled_summary["channel_type"].astype(str).eq("product")].copy()
    partner_summary = pooled_summary[
        pooled_summary["channel_type"].astype(str).eq("partner_spread_continuing_hs6_harmonized")
    ].copy()
    product_equal_country_summary = equal_country_summary[equal_country_summary["channel_type"].astype(str).eq("product")].copy()
    combined_product_first_summary = combined_pooled_summary[
        combined_pooled_summary["channel_type"].astype(str).eq("combined_product_first")
    ].copy()
    combined_partner_first_summary = combined_pooled_summary[
        combined_pooled_summary["channel_type"].astype(str).eq("combined_partner_first")
    ].copy()
    def clean_validation_value(value: Any) -> Any:
        if isinstance(value, list):
            return [clean_validation_value(item) for item in value]
        if isinstance(value, dict):
            return {inner_key: clean_validation_value(inner_value) for inner_key, inner_value in value.items()}
        return clean_scalar(value)

    validation_clean = {key: clean_validation_value(value) for key, value in validation.items()}
    return {
        "country_window": clean_records(country_window, list(country_window.columns)),
        "partner_spread": clean_records(partner_spread, list(partner_spread.columns)),
        "combined_country_window": clean_records(combined_country_window, list(combined_country_window.columns)),
        "combined_pooled_summary": clean_records(combined_pooled_summary, list(combined_pooled_summary.columns)),
        "combined_product_first_summary": clean_records(combined_product_first_summary, list(combined_product_first_summary.columns)),
        "combined_partner_first_summary": clean_records(combined_partner_first_summary, list(combined_partner_first_summary.columns)),
        "combined_equal_country_summary": clean_records(combined_equal_country_summary, list(combined_equal_country_summary.columns)),
        "combined_latest_5y": clean_records(combined_latest_5y.sort_values(["country", "channel_type"]), list(combined_latest_5y.columns)),
        "product_summary": clean_records(product_summary, list(product_summary.columns)),
        "partner_summary": clean_records(partner_summary, list(partner_summary.columns)),
        "equal_country_product_summary": clean_records(product_equal_country_summary, list(product_equal_country_summary.columns)),
        "latest_5y": clean_records(latest_5y.sort_values("country"), list(latest_5y.columns)),
        "bottom10": clean_records(bottom10, list(bottom10.columns)),
        "bottom10_summary": clean_records(bottom10_summary, list(bottom10_summary.columns)),
        "validation": validation_clean,
        "country_count": int(latest_5y["reporter_code"].nunique()),
    }


def load_cadot_integrated_data() -> dict[str, Any]:
    broad_ppp_summary = read_csv("cadot_broad_ppp_hump_summary")
    broad_ppp_attrition = read_csv("cadot_broad_ppp_sample_attrition")
    production_core = read_csv("cadot_production_core_models")
    production_countries = read_csv("cadot_production_core_country_classification")
    between_within = read_csv("cadot_between_within_variance")
    historical_preferred = read_csv("cadot_historical_preferred_within")
    historical_models = read_csv("cadot_historical_model_summary")
    mechanism_summary = read_csv("cadot_broad_mechanism_summary")
    old_cone_models = read_csv("cadot_broad_old_cone_models")
    tribunal_validation = read_csv("cadot_broad_tribunal_validation")

    require_columns(
        production_core,
        "Cadot production-core sensitivity",
        {
            "variant",
            "outcome",
            "outcome_label",
            "estimator",
            "income_form",
            "countries",
            "turning_point_ppp_constant_2021_intl_usd",
            "turning_point_inside_p05_p95",
            "intersection_union_endpoint_p",
            "countries_above_turning_point",
        },
    )
    require_columns(
        historical_preferred,
        "Historical partner preferred within results",
        {
            "flow",
            "metric_name",
            "observations",
            "entity_count",
            "slope_p05",
            "slope_p95",
            "u_test_p_value",
            "u_test_q_value",
            "classification",
        },
    )
    require_columns(
        historical_models,
        "Historical partner model summary",
        {
            "variant",
            "income_form",
            "sample_policy",
            "model_name",
            "curve_component",
            "classification",
        },
    )
    require_columns(
        between_within,
        "Cadot between-within variance decomposition",
        {
            "outcome_label",
            "observations",
            "countries",
            "between_share_total_sum_of_squares",
            "within_share_total_sum_of_squares",
        },
    )
    require_columns(
        mechanism_summary,
        "Cadot broad mechanism summary",
        {"mechanism", "reconcentration_episodes", "flagged_episodes", "flagged_share"},
    )
    require_columns(
        old_cone_models,
        "Cadot broad old-cone models",
        {"term", "coef", "std_error", "p_value", "nobs", "clusters", "primary_spec"},
    )
    require_columns(
        tribunal_validation,
        "Cadot broad tribunal validation",
        {"check", "value", "status"},
    )

    text_cols = {
        "variant",
        "outcome",
        "outcome_label",
        "expected_shape",
        "estimator",
        "income_form",
        "flow",
        "metric_name",
        "classification",
        "slope_sign_pattern",
        "mechanism",
        "term",
        "model_label",
        "status",
        "check",
        "country",
        "iso3",
        "exclusion_reasons",
    }
    broad_ppp_summary = numeric_columns(broad_ppp_summary, text_cols | {"outcome_slug", "verdict"})
    broad_ppp_attrition = numeric_columns(broad_ppp_attrition, text_cols | {"outcome_slug"})
    production_core = numeric_columns(production_core, text_cols)
    production_countries = numeric_columns(production_countries, text_cols)
    between_within = numeric_columns(between_within, text_cols)
    historical_preferred = numeric_columns(historical_preferred, text_cols)
    historical_models = numeric_columns(
        historical_models,
        text_cols
        | {
            "income_form",
            "sample_policy",
            "model_name",
            "curve_component",
            "linear_term_name",
            "square_term_name",
            "excluded_entity_id",
        },
    )
    mechanism_summary = numeric_columns(mechanism_summary, text_cols)
    old_cone_models = numeric_columns(
        old_cone_models,
        text_cols | {"outcome", "fixed_effects", "cluster_col", "prody_spec", "mismatch_definition"},
    )
    tribunal_validation = numeric_columns(tribunal_validation, text_cols)

    production_display = production_core[
        production_core["variant"].eq("production_core")
        & production_core["income_form"].eq("level_ppp")
        & production_core["estimator"].isin(["between_country", "country_year_fe"])
    ].copy()
    production_display["p_value"] = production_display["intersection_union_endpoint_p"]
    production_display["estimator_label"] = production_display["estimator"].map(
        {
            "between_country": "between countries",
            "country_year_fe": "country + year FE",
        }
    )
    production_display["inside_support"] = np.where(
        production_display["turning_point_inside_p05_p95"], "yes", "no"
    )
    production_display["result"] = np.where(
        (production_display["intersection_union_endpoint_p"] < 0.05)
        & production_display["turning_point_inside_p05_p95"],
        np.where(
            production_display["expected_shape"].eq("count_inverted_u"),
            "supported inverted U",
            "supported U-shape",
        ),
        "not supported",
    )
    primary_old_cone = old_cone_models[old_cone_models["primary_spec"].astype(bool)].copy()
    production_kept = production_countries[production_countries["production_core_keep"].astype(bool)].copy()
    historical_sensitivity = historical_models[
        historical_models["model_name"].eq("entity_year_fe_logpop")
        & historical_models["curve_component"].eq("within")
        & historical_models["income_form"].eq("gdppc_10k")
        & historical_models["sample_policy"].eq("fixed")
    ].copy()

    return {
        "broad_ppp_hump_summary": clean_records(
            broad_ppp_summary, list(broad_ppp_summary.columns)
        ),
        "broad_ppp_sample_attrition": clean_records(
            broad_ppp_attrition, list(broad_ppp_attrition.columns)
        ),
        "production_core_models": clean_records(
            production_display, list(production_display.columns)
        ),
        "production_core_country_count": int(production_kept["iso3"].nunique()),
        "between_within_variance": clean_records(
            between_within, list(between_within.columns)
        ),
        "historical_preferred_within": clean_records(
            historical_preferred, list(historical_preferred.columns)
        ),
        "historical_sensitivity_test_count": int(len(historical_sensitivity)),
        "historical_supported_u_shape_count": int(
            historical_sensitivity["classification"].eq("supported_u_shape").sum()
        ),
        "mechanism_summary": clean_records(
            mechanism_summary, list(mechanism_summary.columns)
        ),
        "old_cone_models": clean_records(
            primary_old_cone, list(primary_old_cone.columns)
        ),
        "tribunal_validation": clean_records(
            tribunal_validation, list(tribunal_validation.columns)
        ),
    }


def build_cadot_integrated_body(data: dict[str, Any]) -> str:
    estimator_labels = {
        "pooled_year_fe": "pooled + year FE",
        "between_country": "between countries",
        "country_year_fe": "country + year FE",
    }
    outcome_order = {
        "export_product_gini": 0,
        "export_product_theil": 1,
        "export_product_hhi": 2,
        "export_active_product_count": 3,
    }
    estimator_order = {key: index for index, key in enumerate(estimator_labels)}
    broad_rows = []
    for row in data.get("broad_ppp_hump_summary", []):
        if row.get("income_form") != "level_ppp":
            continue
        if row.get("outcome_slug") not in outcome_order:
            continue
        broad_rows.append(
            {
                **row,
                "estimator_label": estimator_labels.get(
                    str(row.get("estimator")), str(row.get("estimator"))
                ),
                "p_value": row.get("quadratic_p_value"),
                "inside_support": (
                    "yes" if row.get("turning_point_inside_p05_p95") else "no"
                ),
                "country_count": (
                    row.get("nobs")
                    if row.get("estimator") == "between_country"
                    else row.get("clusters")
                ),
                "sort_key": (
                    outcome_order.get(str(row.get("outcome_slug")), 99),
                    estimator_order.get(str(row.get("estimator")), 99),
                ),
            }
        )
    broad_rows = sorted(broad_rows, key=lambda row: row["sort_key"])
    broad_table = table_rows(
        broad_rows,
        [
            ("outcome_label", "Outcome", "text"),
            ("estimator_label", "Estimator", "text"),
            ("quadratic_coefficient", "Quadratic coef.", "dec"),
            ("p_value", "Raw p-value", "dec"),
            (
                "turning_point_ppp_constant_2021_intl_usd",
                "Turning point",
                "money",
            ),
            ("inside_support", "Inside p05-p95", "text"),
            ("verdict", "Result", "text"),
            ("nobs", "N", "int"),
            ("country_count", "Countries", "int"),
        ],
    )

    variance_rows = []
    for row in data.get("between_within_variance", []):
        variance_rows.append(
            {
                **row,
                "between_share": row.get(
                    "between_share_total_sum_of_squares"
                ),
                "within_share": row.get("within_share_total_sum_of_squares"),
            }
        )
    variance_table = table_rows(
        variance_rows,
        [
            ("outcome_label", "Export outcome", "text"),
            ("between_share", "Between-country share", "pct"),
            ("within_share", "Within-country share", "pct"),
            ("observations", "N", "int"),
            ("countries", "Countries", "int"),
        ],
    )

    production_rows = sorted(
        data.get("production_core_models", []),
        key=lambda row: (
            outcome_order.get(str(row.get("outcome")), 99),
            estimator_order.get(str(row.get("estimator")), 99),
        ),
    )
    production_table = table_rows(
        production_rows,
        [
            ("outcome_label", "Outcome", "text"),
            ("estimator_label", "Estimator", "text"),
            ("result", "Endpoint test", "text"),
            ("p_value", "IUT p-value", "dec"),
            (
                "turning_point_ppp_constant_2021_intl_usd",
                "Turning point/peak",
                "money",
            ),
            ("inside_support", "Inside p05-p95", "text"),
            ("countries_above_turning_point", "Countries above", "int"),
            ("countries", "Countries", "int"),
        ],
    )

    historical_rows = []
    for row in data.get("historical_preferred_within", []):
        historical_rows.append(
            {
                **row,
                "p_value": row.get("u_test_p_value"),
                "q_value": row.get("u_test_q_value"),
                "turning_point": row.get("turning_point_ppp_2011_usd"),
            }
        )
    historical_table = table_rows(
        historical_rows,
        [
            ("flow", "Flow", "text"),
            ("metric_name", "Partner measure", "text"),
            ("slope_sign_pattern", "Endpoint slopes", "text"),
            ("turning_point", "Stationary point", "money"),
            ("p_value", "Wild-bootstrap p", "dec"),
            ("q_value", "BH q-value", "dec"),
            ("classification", "Classification", "text"),
            ("observations", "N", "int"),
            ("entity_count", "Entities", "int"),
        ],
    )

    mechanism_rows = [
        {
            **row,
            "mechanism_label": str(row.get("mechanism", "")).replace("_", " "),
        }
        for row in data.get("mechanism_summary", [])
    ]
    mechanism_table = table_rows(
        mechanism_rows,
        [
            ("mechanism_label", "Mechanism flag", "text"),
            ("reconcentration_episodes", "Episodes", "int"),
            ("flagged_episodes", "Flagged", "int"),
            ("flagged_share", "Share", "pct"),
        ],
    )
    old_cone_table = table_rows(
        data.get("old_cone_models", []),
        [
            ("term", "Old-cone exit-model term", "text"),
            ("coef", "Coefficient", "dec"),
            ("std_error", "Clustered SE", "dec"),
            ("p_value", "Raw p-value", "dec"),
            ("nobs", "Product windows", "int"),
            ("clusters", "Reporter clusters", "int"),
        ],
    )

    production_country_count = int(data.get("production_core_country_count") or 0)
    historical_test_count = int(data.get("historical_sensitivity_test_count") or 0)
    historical_supported = int(data.get("historical_supported_u_shape_count") or 0)

    return f"""
    <section class="page-title">
      <div class="eyebrow">Replication, reinterpretation, and boundary tests</div>
      <h1>Cadot Diversification Hump: Combined Results</h1>
      <p>This page combines the modern 156-reporter reconstruction, pooled-versus-within tests, production-core exclusions, mechanism exercises, and the 1827-2014 historical partner-concentration boundary test.</p>
    </section>

    <section class="section" id="cadot-interpretation-results">
      <div class="section-heading">
        <h2>Interpretation and Results</h2>
        <p>The evidence refines Cadot rather than delivering a binary replication verdict.</p>
      </div>
      <div class="result-ladder">
        <article><span>Modern products</span><strong>Cross-country hump</strong><p>Level-PPP product curvature is strongest between countries.</p></article>
        <article><span>Within countries</span><strong>No robust law</strong><p>Country fixed effects remove the broad export Gini and Theil humps.</p></article>
        <article><span>Production core</span><strong>Theil, HHI, counts survive</strong><p>Active-product Gini does not; log-income forms do not.</p></article>
        <article><span>Mechanism</span><strong>Continuing-product scaling</strong><p>72.2% of broad-sample reconcentration episodes carry this flag.</p></article>
        <article><span>Historical partners</span><strong>{historical_supported}/{historical_test_count} supported</strong><p>No 1827-2014 within-country partner U-shape survives the sensitivity grid.</p></article>
      </div>
      <div class="interpretation-grid">
        <article class="note">
          <h3>What survives</h3>
          <p>Modern product concentration declines with development and bends upward in the rich-country cross section. Between-country differences account for 73.2% of Export Product Gini variation, 94.1% of Theil variation, and 81.1% of HHI variation.</p>
          <p>After removing microstates, major oil exporters, and finance, tax-conduit, offshore, and re-export hubs, the level-PPP between-country hump remains for fixed-universe Theil, HHI, and active-product counts. The Theil/count turning point is about $46,000, with 12 of {production_country_count} countries, or 14.5%, above it—close to Cadot's 21 of 141 countries, or 14.9%.</p>
        </article>
        <article class="note">
          <h3>What does not survive</h3>
          <p>The modern export Gini and Theil humps do not survive country fixed effects in the broad sample. The production-core active-product Gini has no supported cross-country U-shape, and none of the four production-core outcomes passes the endpoint test under log GDP per capita.</p>
          <p>The historical exercise is across trading partners, not products. It rules out a generic law that development eventually reconcentrates trade, but it does not constitute a historical product-level replication of Cadot.</p>
        </article>
      </div>
      <div class="note">
        <p><strong>Current econometric interpretation:</strong> Cadot captures a real equilibrium relationship across country types in product space. Our evidence does not support a universal within-country development sequence or a predominantly extensive-margin exit mechanism. Persistent differences in scale, comparative advantage, sectoral specialization, global-product demand, institutions, and trade-hub status explain much of the pooled shape.</p>
      </div>
      <div class="figure-row full-width">
        <figure><a class="figure-link" href="assets/figures/cadot_export_gini_theil_fits.png?v={CADOT_PAGE_ASSET_VERSION}"><img src="assets/figures/cadot_export_gini_theil_fits.png?v={CADOT_PAGE_ASSET_VERSION}" alt="Broad 156 export Gini and Theil against real GDP per capita with linear, quadratic, and nonparametric fits"></a><figcaption>Broad 156 sample: does modern export concentration bend upward at high income? The quadratic does; the nonparametric fit is flatter in the sparse rich tail.</figcaption></figure>
      </div>
      <div class="download-grid compact-downloads">
        <a href="assets/downloads/cadot_final_interpretation_report.md">Detailed interpretation report</a>
        <a href="assets/downloads/cadot-replication.md">Full replication record</a>
        <a href="assets/downloads/cadot_production_core_sensitivity.md">Production-core memo</a>
        <a href="assets/downloads/historical_partner_concentration_advisor_memo.md">Historical advisor memo</a>
      </div>
    </section>

    <section class="section" id="cadot-modern-156-results">
      <div class="section-heading">
        <h2>Modern 156-Reporter Product Results</h2>
        <p>Unit: reporter-year. Income is real GDP per capita in constant-2021 PPP dollars. Models include log population and oil-export share; pooled and country-FE models include year effects and reporter-clustered standard errors. Product calculations exclude HS6 999999 before aggregation.</p>
      </div>
      <div class="table-scroll">{broad_table}</div>
      <div class="figure-row">
        <figure><a class="figure-link" href="assets/figures/cadot_broad_ppp_hump_level.png?v={CADOT_PAGE_ASSET_VERSION}"><img src="assets/figures/cadot_broad_ppp_hump_level.png?v={CADOT_PAGE_ASSET_VERSION}" alt="Broad 156 level-PPP concentration curves"></a><figcaption>Broad 156 level-PPP results: export turning points lie at or beyond the central rich-country support.</figcaption></figure>
        <figure><a class="figure-link" href="assets/figures/cadot_broad_ppp_hump_log.png?v={CADOT_PAGE_ASSET_VERSION}"><img src="assets/figures/cadot_broad_ppp_hump_log.png?v={CADOT_PAGE_ASSET_VERSION}" alt="Broad 156 log-PPP concentration curves"></a><figcaption>Broad 156 log-PPP stress test: export product results weaken or move outside support.</figcaption></figure>
      </div>
      <h3 class="subsection-title">Where the variation comes from</h3>
      <div class="table-scroll">{variance_table}</div>
    </section>

    <section class="section" id="cadot-production-core">
      <div class="section-heading">
        <h2>Production-Core Exclusion Exercise</h2>
        <p>The severe screen removes countries with mean population below one million, mean oil/fuel export shares of at least 30%, and prominent finance, tax-conduit, offshore, or re-export hubs. It leaves {production_country_count} countries. This remains gross customs trade—not domestic value-added production.</p>
      </div>
      <div class="table-scroll">{production_table}</div>
      <div class="note">
        <p><strong>Read:</strong> Removing hubs does not erase the level-PPP cross-country pattern. It shifts the Theil and active-count turning point to about $46,000 and the HHI turning point to about $40,000. But active-product Gini does not turn, log-income versions fail, and no country-FE specification passes the endpoint test at 5%.</p>
      </div>
      <div class="download-grid compact-downloads">
        <a href="assets/downloads/cadot_production_core_model_summary.csv">Model summary</a>
        <a href="assets/downloads/cadot_production_core_country_classification.csv">Country exclusions</a>
        <a href="assets/downloads/cadot_production_core_manifest.json">Run manifest</a>
      </div>
    </section>

    <section class="section" id="cadot-historical-partners">
      <div class="section-heading">
        <h2>Historical Exercise: Partner Concentration, 1827-2014</h2>
        <p>CEPII TRADHIST bilateral flows are combined with Maddison GDP per capita and population for 13 source-defined reporter entities. Measures are Gini, Theil, and HHI across observed positive partners. Missing historical dyads are not converted to zero; the preferred baseline requires at least 20 active partners.</p>
      </div>
      <div class="table-scroll">{historical_table}</div>
      <div class="figure-row">
        <figure><a class="figure-link" href="assets/figures/cadot_historical_baseline_u_shape.png?v={CADOT_PAGE_ASSET_VERSION}"><img src="assets/figures/cadot_historical_baseline_u_shape.png?v={CADOT_PAGE_ASSET_VERSION}" alt="Historical 13-entity partner concentration baseline U-shape tests"></a><figcaption>Historical 13-entity exercise: none of the six preferred within-country tests passes the formal wild-cluster-bootstrap U-shape test.</figcaption></figure>
        <figure><a class="figure-link" href="assets/figures/cadot_historical_sensitivity.png?v={CADOT_PAGE_ASSET_VERSION}"><img src="assets/figures/cadot_historical_sensitivity.png?v={CADOT_PAGE_ASSET_VERSION}" alt="Historical 13-entity partner concentration sensitivity U-shape tests"></a><figcaption>Historical 13-entity exercise: across {historical_test_count} preferred within-country variant tests, zero is classified as a supported U-shape.</figcaption></figure>
      </div>
      <div class="note">
        <p><strong>Scope:</strong> This is a long-run boundary test of concentration across partners. It is not a product-level historical replication. USSR and the Russian Federation remain separate entities, and the sensitivity grid includes war exclusions, pre/post-1948 source regimes, partner-count thresholds, common-partner blocks, rank truncation, synthetic censoring, and leave-one-entity-out checks.</p>
      </div>
      <div class="download-grid compact-downloads">
        <a href="assets/downloads/historical_partner_preferred_within_results.csv">Preferred historical results</a>
        <a href="assets/downloads/historical_partner_cadot_model_summary.csv">Full historical model summary</a>
        <a href="assets/downloads/historical_partner_concentration_run_manifest.json">Historical run manifest</a>
        <a href="assets/downloads/historical_partner_concentration_adversarial_review.md">Historical adversarial review</a>
      </div>
    </section>

    <section class="section" id="cadot-latest-mechanisms">
      <div class="section-heading">
        <h2>Latest Mechanism Exercises: Broad 156 Sample</h2>
        <p>These five-year episode flags overlap and are descriptive classifications, not an additive causal decomposition. The broad tribunal uses harmonized HS1992 product families and a fixed-universe Product Theil reconcentration outcome.</p>
      </div>
      <div class="table-scroll">{mechanism_table}</div>
      <div class="figure-row">
        <figure><a class="figure-link" href="assets/figures/cadot_broad_mechanism_scorecard.png?v={CADOT_PAGE_ASSET_VERSION}"><img src="assets/figures/cadot_broad_mechanism_scorecard.png?v={CADOT_PAGE_ASSET_VERSION}" alt="Broad 156 Cadot mechanism scorecard"></a><figcaption>Broad 156 sample: continuing-product superstar scaling accompanies 72.2% of 1,312 reconcentration episodes; old-cone pruning is flagged in 5.4%.</figcaption></figure>
        <figure><a class="figure-link" href="assets/figures/cadot_broad_old_cone_exit.png?v={CADOT_PAGE_ASSET_VERSION}"><img src="assets/figures/cadot_broad_old_cone_exit.png?v={CADOT_PAGE_ASSET_VERSION}" alt="Broad 156 old-cone product exit evidence"></a><figcaption>Broad 156 sample. The x-axis is log(country GDP per capita / product PRODY): zero means the country's income matches the typical exporters of that product, while a positive value means the product is associated with poorer exporters and is therefore an “old-cone” candidate. On the rich side, exit rises with this mismatch. Read the slope difference, not the raw vertical gap.</figcaption></figure>
      </div>
      <h3 class="subsection-title">Old-Cone Exit Regression</h3>
      <div class="table-scroll">{old_cone_table}</div>
      <div class="note">
        <p><strong>How to interpret the exit-cone image:</strong> Products are grouped by their income mismatch. A value of +1 means the country's GDP per capita is about 2.7 times the product's PRODY. The orange line covers country-years above the sample income p75, approximately $39,308 in constant-2021 PPP dollars. Its upward right tail says that, among these richer country-years, products increasingly below the country's income level are more likely to disappear from the export basket within five years. The controlled mismatch × rich-side interaction is +3.25 percentage points per +1 log mismatch (reporter-clustered raw p&lt;0.001).</p>
        <p><strong>What it does not say:</strong> Rich countries do not have higher exit rates at every mismatch—the raw orange line is generally below the gray line. The evidence supports a differential slope conditional on reporter, product, and base-year fixed effects, not a causal level comparison. Overlapping windows, generated PRODY, common product shocks, and one-way reporter clustering remain limitations. The estimated log-income turning point is outside support, so “rich side” uses the observed income p75 as a labeled fallback.</p>
      </div>
      <div class="download-grid compact-downloads">
        <a href="assets/downloads/cadot_broad_mechanism_scorecard_summary.csv">Mechanism scorecard</a>
        <a href="assets/downloads/cadot_broad_old_cone_exit_models.csv">Old-cone models</a>
        <a href="assets/downloads/cadot_broad_tribunal_validation_checks.csv">Validation checks</a>
        <a href="assets/downloads/cadot_broad_tribunal_run_manifest.json">Tribunal manifest</a>
        <a href="assets/downloads/cadot_broad_tribunal_adversarial_review.md">Tribunal adversarial review</a>
      </div>
    </section>

    <section class="section" id="cadot-replication-status">
      <div class="section-heading">
        <h2>Replication Status and Remaining Test</h2>
      </div>
      <ul class="callout-list">
        <li><strong>Completed:</strong> modern 156-reporter three-metric reconstruction, level/log PPP models, pooled/within/between decomposition, production-core exclusions, mechanism tribunal, and historical partner boundary test.</li>
        <li><strong>Not completed:</strong> a literal 1988-2006 reconstruction using Cadot's exact country list, mirror-export rule, and 4,991-line product universe.</li>
        <li><strong>Best next test:</strong> domestic-value-added export concentration using OECD TiVA/ICIO, followed by a matched original-period versus modern-period product bridge.</li>
      </ul>
    </section>
    """


def load_cadot_hump_data() -> dict[str, Any]:
    if not include_cadot_hump_page():
        return {}
    if ACTIVE_SITE_SAMPLE == "cadot_broad_156":
        return load_cadot_integrated_data()
    sample_diagnostics = read_csv("cadot_hump_sample_diagnostics")
    hump_models = read_csv("cadot_hump_models")
    mechanical_models = read_csv("cadot_mechanical_variant_models")
    mechanism_summary = read_csv("cadot_mechanism_scorecard_summary")
    scorecard = read_csv("cadot_reconcentration_episode_scorecard")
    old_cone_models = read_csv("cadot_old_cone_exit_models")
    old_cone_summary = read_csv("cadot_old_cone_channel_summary")
    old_cone_deciles = read_csv("cadot_old_cone_exit_by_mismatch_decile")
    country_year = read_csv("cadot_hump_country_year_panel")
    ppp_hump_summary = read_csv("cadot_ppp_hump_summary")
    ppp_country_fe = read_csv("cadot_ppp_country_fe_robustness")
    broad_ppp_summary = read_csv("cadot_broad_ppp_hump_summary")
    broad_ppp_attrition = read_csv("cadot_broad_ppp_sample_attrition")
    broad_ppp_reestimate = read_csv("cadot_broad_ppp_independent_reestimate_checks")
    require_columns(
        sample_diagnostics,
        "Cadot hump sample diagnostics",
        {"diagnostic", "balanced_countries", "balanced_rows", "required_columns"},
    )
    require_columns(
        hump_models,
        "Cadot hump models",
        {"model_label", "metric", "outcome", "term", "coefficient", "std_error", "p_value", "nobs", "clusters"},
    )
    require_columns(
        mechanism_summary,
        "Cadot mechanism scorecard summary",
        {"mechanism", "reconcentration_episodes", "flagged_episodes", "flagged_share"},
    )
    require_columns(
        scorecard,
        "Cadot reconcentration episode scorecard",
        {
            "country",
            "iso3",
            "reporter_code",
            "base_year",
            "future_year",
            "delta_world_relative_product_gini",
            "reconcentration_episode",
            "commodity_spike",
            "section16_hs_design_sensitive",
            "old_cone_pruning",
            "continuing_product_superstar_scaling",
            "broad_unexplained_reconcentration",
        },
    )
    require_columns(
        old_cone_models,
        "Cadot old-cone exit models",
        {"model_label", "term", "coef", "std_error", "p_value", "nobs", "clusters"},
    )
    require_columns(
        ppp_hump_summary,
        "Cadot PPP hump summary",
        {
            "outcome_label",
            "income_form",
            "quadratic_coefficient",
            "quadratic_p_value",
            "turning_point_ppp_constant_2021_intl_usd",
            "turning_point_inside_p05_p95",
            "verdict",
            "nobs",
            "clusters",
        },
    )
    require_columns(
        ppp_country_fe,
        "Cadot PPP pooled/country-FE robustness",
        {
            "outcome_label",
            "income_form",
            "specification",
            "quadratic_coefficient",
            "quadratic_p_value",
            "turning_point_ppp_constant_2021_intl_usd",
            "turning_point_inside_p05_p95",
            "nobs",
            "clusters",
            "status",
        },
    )
    require_columns(
        broad_ppp_summary,
        "Cadot broad PPP hump summary",
        {
            "outcome_slug",
            "flow",
            "outcome_label",
            "estimator",
            "income_form",
            "quadratic_coefficient",
            "quadratic_p_value",
            "turning_point_ppp_constant_2021_intl_usd",
            "turning_point_inside_p05_p95",
            "verdict",
            "nobs",
            "clusters",
        },
    )
    require_columns(
        broad_ppp_attrition,
        "Cadot broad PPP sample attrition",
        {
            "outcome_slug",
            "selected_reporters",
            "selected_country_years",
            "source_rows",
            "analytic_rows_after_balance",
            "analytic_countries_after_balance",
            "analytic_clusters_after_balance",
            "missing_ppp_rows",
            "missing_population_rows",
            "missing_oil_share_rows",
        },
    )
    require_columns(
        broad_ppp_reestimate,
        "Cadot broad PPP independent re-estimation checks",
        {
            "check",
            "term",
            "abs_coefficient_diff",
            "abs_std_error_diff",
            "nobs",
            "clusters",
            "passed",
        },
    )
    text_cols = {
        "diagnostic",
        "required_columns",
        "missing_required_columns",
        "reporter_codes",
        "model_label",
        "sample",
        "flow",
        "dimension",
        "metric",
        "outcome",
        "term",
        "status",
        "fixed_effects",
        "se_method",
        "cluster_col",
        "p_value_reference",
        "mechanism",
        "country",
        "iso3",
        "product_channel",
        "outcome_label",
        "outcome_slug",
        "income_form",
        "income_label",
        "linear_term",
        "quadratic_term",
        "verdict",
        "specification",
        "estimator",
        "balance_policy",
        "cluster_col",
        "check",
        "passed",
    }
    sample_diagnostics = numeric_columns(sample_diagnostics, text_cols)
    hump_models = numeric_columns(hump_models, text_cols)
    mechanical_models = numeric_columns(mechanical_models, text_cols)
    mechanism_summary = numeric_columns(mechanism_summary, text_cols)
    scorecard = numeric_columns(scorecard, text_cols)
    old_cone_models = numeric_columns(old_cone_models, text_cols)
    old_cone_summary = numeric_columns(old_cone_summary, text_cols)
    old_cone_deciles = numeric_columns(old_cone_deciles, text_cols)
    country_year = numeric_columns(country_year, text_cols | {"region", "income_group", "sample_window"})
    ppp_hump_summary = numeric_columns(ppp_hump_summary, text_cols)
    ppp_country_fe = numeric_columns(ppp_country_fe, text_cols)
    broad_ppp_summary = numeric_columns(broad_ppp_summary, text_cols)
    broad_ppp_attrition = numeric_columns(broad_ppp_attrition, text_cols)
    broad_ppp_reestimate = numeric_columns(broad_ppp_reestimate, text_cols)
    preferred_hump = hump_models[
        hump_models["model_label"].eq("quadratic_controls_year_fe_country_cluster")
        & hump_models["metric"].eq("world_relative_product_gini")
    ].copy()
    preferred_mechanical = mechanical_models[mechanical_models["term"].eq("log_gni_pc_sq")].copy()
    old_cone_interaction = old_cone_models[old_cone_models["term"].eq("mismatch_x_rich_side")].copy()
    scorecard_display = scorecard[scorecard["reconcentration_episode"].astype(bool)].copy()
    scorecard_display = scorecard_display.sort_values(
        ["delta_world_relative_product_gini", "country"], ascending=[False, True]
    ).head(20)
    return {
        "sample_diagnostics": clean_records(sample_diagnostics, list(sample_diagnostics.columns)),
        "hump_models_preferred": clean_records(preferred_hump, list(preferred_hump.columns)),
        "mechanical_models_quadratic": clean_records(preferred_mechanical, list(preferred_mechanical.columns)),
        "mechanism_summary": clean_records(mechanism_summary, list(mechanism_summary.columns)),
        "scorecard_top_reconcentration": clean_records(scorecard_display, list(scorecard_display.columns)),
        "old_cone_models": clean_records(old_cone_models, list(old_cone_models.columns)),
        "old_cone_interaction": clean_records(old_cone_interaction, list(old_cone_interaction.columns)),
        "old_cone_summary": clean_records(old_cone_summary, list(old_cone_summary.columns)),
        "old_cone_deciles": clean_records(old_cone_deciles, list(old_cone_deciles.columns)),
        "ppp_hump_summary": clean_records(ppp_hump_summary, list(ppp_hump_summary.columns)),
        "ppp_country_fe_robustness": clean_records(ppp_country_fe, list(ppp_country_fe.columns)),
        "broad_ppp_hump_summary": clean_records(broad_ppp_summary, list(broad_ppp_summary.columns)),
        "broad_ppp_sample_attrition": clean_records(broad_ppp_attrition, list(broad_ppp_attrition.columns)),
        "broad_ppp_independent_reestimate_checks": clean_records(
            broad_ppp_reestimate,
            list(broad_ppp_reestimate.columns),
        ),
        "country_year_latest_summary": clean_records(
            country_year[country_year["year"].eq(country_year["year"].max())][
                [
                    "country",
                    "iso3",
                    "year",
                    "world_relative_product_gini",
                    "product_gini",
                    "product_active_count",
                    "product_top_1pct_share",
                    "commodity_trade_share_removed",
                    "section16_export_share",
                ]
            ].sort_values("world_relative_product_gini", ascending=False),
            [
                "country",
                "iso3",
                "year",
                "world_relative_product_gini",
                "product_gini",
                "product_active_count",
                "product_top_1pct_share",
                "commodity_trade_share_removed",
                "section16_export_share",
            ],
        ),
    }
    country_year = numeric_columns(country_year, text_cols)
    latest = numeric_columns(latest, text_cols)
    summary = numeric_columns(summary, text_cols)
    country_weighted_summary = numeric_columns(country_weighted_summary, text_cols | {"summary_weighting"})
    overlapping = numeric_columns(overlapping, text_cols)
    product_robustness = numeric_columns(product_robustness, text_cols)

    preferred_summary = summary[
        summary["identity_mode"].eq("hs6_harmonized_family")
        & summary["category"].isin(
            [
                "net_new_product",
                "net_new_partner_existing_product",
                "new_product_partner_cell_existing_product_partner",
                "existing_product_partner_cell_growth",
                "existing_product_partner_cell_contraction",
            ]
        )
    ].sort_values(["horizon", "category_order"]).reset_index(drop=True)
    preferred_country_weighted_summary = country_weighted_summary[
        country_weighted_summary["identity_mode"].eq("hs6_harmonized_family")
        & country_weighted_summary["category"].isin(
            [
                "net_new_product",
                "net_new_partner_existing_product",
                "new_product_partner_cell_existing_product_partner",
                "existing_product_partner_cell_growth",
                "existing_product_partner_cell_contraction",
            ]
        )
    ].sort_values(["horizon", "category_order"]).reset_index(drop=True)
    latest = latest.sort_values(["horizon", "country"]).reset_index(drop=True)
    for frame in [latest]:
        frame["period"] = frame["base_year"].astype("Int64").astype(str) + "-" + frame["future_year"].astype("Int64").astype(str)
    latest_h5 = latest[latest["horizon"].eq(5)].copy()
    product_robustness_summary = (
        product_robustness[
            product_robustness["identity_mode"].eq("hs6_harmonized_family")
        ]
        .groupby(["horizon", "product_definition", "product_definition_label"], as_index=False)
        .agg(
            countries=("reporter_code", "nunique"),
            median_gross_positive_share=("gross_positive_share", "median"),
            median_net_growth_share=("net_growth_share", "median"),
            median_product_count=("product_count", "median"),
        )
        .sort_values(["horizon", "product_definition"])
    )
    overlap_summary = (
        overlapping[
            overlapping["identity_mode"].eq("hs6_harmonized_family")
        ]
        .groupby(["horizon", "overlap_channel", "overlap_channel_label"], as_index=False)
        .agg(
            countries=("reporter_code", "nunique"),
            median_gross_positive_share=("gross_positive_share", "median"),
            median_net_growth_share=("net_growth_share", "median"),
        )
        .sort_values(["horizon", "overlap_channel"])
    )
    validation_clean = {}
    for key, value in validation.items():
        if key == "rows_by_identity_horizon":
            continue
        if isinstance(value, list):
            validation_clean[key] = value
        elif isinstance(value, dict):
            validation_clean[key] = {inner_key: clean_scalar(inner_value) for inner_key, inner_value in value.items()}
        else:
            validation_clean[key] = clean_scalar(value)
    validate_ex12_extensive_validation(
        validation,
        latest=latest,
        summary=summary,
        country_weighted_summary=country_weighted_summary,
        product_robustness=product_robustness,
        overlapping=overlapping,
    )
    return {
        "latest": clean_records(latest, list(latest.columns)),
        "latest_h5": clean_records(latest_h5, list(latest_h5.columns)),
        "summary_preferred": clean_records(preferred_summary, list(preferred_summary.columns)),
        "country_weighted_summary_preferred": clean_records(
            preferred_country_weighted_summary,
            list(preferred_country_weighted_summary.columns),
        ),
        "product_robustness_summary": clean_records(product_robustness_summary, list(product_robustness_summary.columns)),
        "overlap_summary": clean_records(overlap_summary, list(overlap_summary.columns)),
        "validation": validation_clean,
        "country_count": int(latest["reporter_code"].nunique()),
    }


def build_data() -> tuple[dict[str, Any], dict[str, str]]:
    ex1 = read_csv("exercise_1_panel")
    three_metric = load_three_metric_data()
    require_columns(
        ex1,
        "Exercise 1 panel",
        {
            "country",
            "iso3",
            "reporter_code",
            "year",
            "flow",
            "variant",
            "total_trade_value",
            "product_gini",
            "partner_gini",
            "product_partner_cell_gini",
            "product_top_1pct_share",
            "product_top_5pct_share",
            "top_5_partner_share",
        },
    )
    ex1 = ex1[ex1["variant"].astype(str).str.lower().eq("baseline")].copy()
    for column in [
        "year",
        "total_trade_value",
        "product_gini",
        "partner_gini",
        "product_partner_cell_gini",
        "product_top_1pct_share",
        "product_top_5pct_share",
        "top_5_partner_share",
    ]:
        ex1[column] = pd.to_numeric(ex1[column], errors="coerce")
    world_relative_panel = pd.DataFrame()
    world_relative_appendix = pd.DataFrame()
    world_relative_diagnostics = pd.DataFrame()
    world_relative_classification_diagnostics = pd.DataFrame()
    world_relative_harmonization_diagnostics = pd.DataFrame()
    world_relative_yearly = pd.DataFrame()
    world_relative_latest = pd.DataFrame()
    world_relative_contribution_top = pd.DataFrame()
    world_relative_contribution_summary = pd.DataFrame()
    world_relative_contribution_latest_small = pd.DataFrame()
    world_relative_contribution_bucket = pd.DataFrame()
    world_relative_contribution_validation = pd.DataFrame()
    world_relative_import_panel = pd.DataFrame()
    world_relative_import_appendix = pd.DataFrame()
    world_relative_import_diagnostics = pd.DataFrame()
    world_relative_import_classification_diagnostics = pd.DataFrame()
    world_relative_import_harmonization_diagnostics = pd.DataFrame()
    world_relative_import_yearly = pd.DataFrame()
    world_relative_import_latest = pd.DataFrame()
    world_relative_import_contribution_top = pd.DataFrame()
    world_relative_import_contribution_summary = pd.DataFrame()
    world_relative_import_contribution_latest_small = pd.DataFrame()
    world_relative_import_contribution_bucket = pd.DataFrame()
    world_relative_import_contribution_validation = pd.DataFrame()
    if include_world_relative_product_gini():
        world_relative_panel = read_csv("world_relative_product_gini_panel")
        world_relative_appendix = read_csv("world_weighted_product_gini_appendix")
        world_relative_diagnostics = read_csv("world_relative_product_gini_diagnostics")
        world_relative_classification_diagnostics = read_csv("world_relative_product_gini_classification_diagnostics")
        world_relative_harmonization_diagnostics = read_csv("world_relative_product_gini_harmonization_diagnostics")
        world_relative_yearly = read_csv("world_relative_product_gini_yearly_summary")
        world_relative_latest = read_csv("world_relative_product_gini_latest_rankings")
        world_relative_contribution_top = read_csv("world_relative_product_contribution_top_drivers")
        world_relative_contribution_summary = read_csv("world_relative_product_contribution_country_year_summary")
        world_relative_contribution_latest_small = read_csv("world_relative_product_contribution_latest_small_countries")
        world_relative_contribution_bucket = read_csv("world_relative_product_contribution_bucket_summary")
        world_relative_contribution_validation = read_csv("world_relative_product_contribution_validation")
        world_relative_import_panel = read_csv("world_relative_import_product_gini_panel")
        world_relative_import_appendix = read_csv("world_weighted_import_product_gini_appendix")
        world_relative_import_diagnostics = read_csv("world_relative_import_product_gini_diagnostics")
        world_relative_import_classification_diagnostics = read_csv("world_relative_import_product_gini_classification_diagnostics")
        world_relative_import_harmonization_diagnostics = read_csv("world_relative_import_product_gini_harmonization_diagnostics")
        world_relative_import_yearly = read_csv("world_relative_import_product_gini_yearly_summary")
        world_relative_import_latest = read_csv("world_relative_import_product_gini_latest_rankings")
        world_relative_import_contribution_top = read_csv("world_relative_import_product_contribution_top_drivers")
        world_relative_import_contribution_summary = read_csv("world_relative_import_product_contribution_country_year_summary")
        world_relative_import_contribution_latest_small = read_csv("world_relative_import_product_contribution_latest_small_countries")
        world_relative_import_contribution_bucket = read_csv("world_relative_import_product_contribution_bucket_summary")
        world_relative_import_contribution_validation = read_csv("world_relative_import_product_contribution_validation")
        require_columns(
            world_relative_panel,
            "World-relative product Gini panel",
            {
                "country",
                "iso3",
                "reporter_code",
                "year",
                "flow",
                "world_relative_product_gini",
                "world_weighted_share_gini",
                "world_weighted_product_coverage",
                "zero_weight_country_export_share",
                "missing_benchmark_product_count",
            },
        )
        require_columns(
            world_relative_contribution_top,
            "World-relative contribution top drivers",
            {
                "country",
                "iso3",
                "reporter_code",
                "year",
                "driver_rank",
                "product_label",
                "country_share",
                "leave_one_out_world_weight",
                "relative_intensity",
                "positive_loo_gini_contribution",
                "driver_bucket",
            },
        )
        require_columns(
            world_relative_contribution_latest_small,
            "World-relative latest small-country contribution summary",
            {
                "country",
                "iso3",
                "year",
                "population",
                "world_relative_product_gini",
                "main_positive_driver_bucket",
                "overweight_niche_product_positive_share",
                "missing_large_world_product_positive_share",
                "underweight_large_world_product_positive_share",
                "overweight_large_world_product_positive_share",
            },
        )
        require_columns(
            world_relative_import_panel,
            "World-relative import product Gini panel",
            {
                "country",
                "iso3",
                "reporter_code",
                "year",
                "flow",
                "world_relative_import_product_gini",
                "world_weighted_share_gini",
                "world_weighted_product_coverage",
                "zero_weight_country_import_share",
                "missing_benchmark_product_count",
            },
        )
        require_columns(
            world_relative_import_contribution_top,
            "World-relative import contribution top drivers",
            {
                "country",
                "iso3",
                "reporter_code",
                "year",
                "driver_rank",
                "product_label",
                "country_share",
                "leave_one_out_world_weight",
                "relative_intensity",
                "positive_loo_gini_contribution",
                "driver_bucket",
            },
        )
        require_columns(
            world_relative_import_contribution_latest_small,
            "World-relative import latest small-country contribution summary",
            {
                "country",
                "iso3",
                "year",
                "population",
                "world_relative_import_product_gini",
                "main_positive_driver_bucket",
                "overweight_niche_product_positive_share",
                "missing_large_world_product_positive_share",
                "underweight_large_world_product_positive_share",
                "overweight_large_world_product_positive_share",
            },
        )
        for frame in [
            world_relative_panel,
            world_relative_appendix,
            world_relative_diagnostics,
            world_relative_classification_diagnostics,
            world_relative_harmonization_diagnostics,
            world_relative_yearly,
            world_relative_latest,
            world_relative_contribution_top,
            world_relative_contribution_summary,
            world_relative_contribution_latest_small,
            world_relative_contribution_bucket,
            world_relative_contribution_validation,
            world_relative_import_panel,
            world_relative_import_appendix,
            world_relative_import_diagnostics,
            world_relative_import_classification_diagnostics,
            world_relative_import_harmonization_diagnostics,
            world_relative_import_yearly,
            world_relative_import_latest,
            world_relative_import_contribution_top,
            world_relative_import_contribution_summary,
            world_relative_import_contribution_latest_small,
            world_relative_import_contribution_bucket,
            world_relative_import_contribution_validation,
        ]:
            for column in frame.columns:
                if column not in {
                    "country",
                    "iso3",
                    "flow",
                    "variant",
                    "product_id",
                    "product_label",
                    "product_description",
                    "representative_classification_code",
                    "representative_cmd_code",
                    "driver_bucket",
                    "main_positive_driver_bucket",
                    "top_positive_driver_product_id",
                    "sample_window",
                    "check",
                }:
                    frame[column] = pd.to_numeric(frame[column], errors="ignore")
        merge_cols = [
            "reporter_code",
            "year",
            "flow",
            "world_relative_product_gini",
            "world_weighted_share_gini",
            "world_weighted_product_coverage",
            "zero_weight_country_export_share",
            "missing_benchmark_product_count",
            "world_relative_minus_active_product_gini",
        ]
        available_merge_cols = [col for col in merge_cols if col in world_relative_panel.columns]
        world_relative_merge = world_relative_panel[available_merge_cols].copy()
        duplicate_world_relative_keys = world_relative_merge.duplicated(["reporter_code", "year", "flow"], keep=False)
        if duplicate_world_relative_keys.any():
            examples = world_relative_merge.loc[
                duplicate_world_relative_keys, ["reporter_code", "year", "flow"]
            ].head(10).to_dict(orient="records")
            raise RuntimeError(f"Duplicate World-Relative Product Gini site keys: {examples}")
        ex1 = ex1.merge(
            world_relative_merge,
            on=["reporter_code", "year", "flow"],
            how="left",
            validate="one_to_one",
        )
        import_merge_cols = [
            "reporter_code",
            "year",
            "flow",
            "world_relative_import_product_gini",
            "world_weighted_share_gini",
            "world_weighted_product_coverage",
            "zero_weight_country_import_share",
            "missing_benchmark_product_count",
            "world_relative_import_minus_active_product_gini",
        ]
        available_import_merge_cols = [col for col in import_merge_cols if col in world_relative_import_panel.columns]
        world_relative_import_merge = world_relative_import_panel[available_import_merge_cols].copy()
        duplicate_import_world_relative_keys = world_relative_import_merge.duplicated(["reporter_code", "year", "flow"], keep=False)
        if duplicate_import_world_relative_keys.any():
            examples = world_relative_import_merge.loc[
                duplicate_import_world_relative_keys, ["reporter_code", "year", "flow"]
            ].head(10).to_dict(orient="records")
            raise RuntimeError(f"Duplicate World-Relative Import Product Gini site keys: {examples}")
        rename_import = {
            "world_weighted_share_gini": "world_weighted_import_share_gini",
            "world_weighted_product_coverage": "world_weighted_import_product_coverage",
            "missing_benchmark_product_count": "missing_import_benchmark_product_count",
        }
        world_relative_import_merge = world_relative_import_merge.rename(
            columns={key: value for key, value in rename_import.items() if key in world_relative_import_merge.columns}
        )
        ex1 = ex1.merge(
            world_relative_import_merge,
            on=["reporter_code", "year", "flow"],
            how="left",
            validate="one_to_one",
        )
    shape = validate_source_shapes(ex1)

    growth = read_csv("exercise_2_growth")
    growth_models = read_csv("exercise_2_growth_models")
    growth_diagnostics = read_csv("exercise_2_growth_diagnostics")
    bins = read_csv("exercise_3_bins")
    decomp = read_csv("exercise_3_decomposition")
    total_import = read_csv("exercise_3_total")
    top_goods = read_csv("exercise_3_top_goods")
    suppliers = read_csv("exercise_4_suppliers")
    h24_supplier_summary = read_csv("h24_supplier_summary")
    h24_supplier_comparison = read_csv("h24_supplier_comparison")
    partner_counterfactual = read_csv("exercise_4_partner_counterfactual_country_year")
    partner_counterfactual_latest = read_csv("exercise_4_partner_counterfactual_latest")
    exclusions = read_csv("exercise_6_exclusions")
    exclusion_keys = ["country", "iso3", "reporter_code", "year", "flow", "variant"]
    if exclusions.duplicated(exclusion_keys).any():
        exclusion_value_columns = [column for column in exclusions.columns if column not in exclusion_keys]
        exclusions = (
            exclusions.groupby(exclusion_keys, as_index=False)[exclusion_value_columns]
            .median(numeric_only=True)
            .sort_values(exclusion_keys)
            .reset_index(drop=True)
        )
    hs2 = read_csv("exercise_10_hs2")
    active = read_csv("exercise_10_active")
    io = read_csv("exercise_11_io_summary")
    coefs = read_csv("exercise_11_coefficients")
    intermediate_effects = read_csv("exercise_11_intermediate_effects")
    hs2_panel = read_csv("exercise_11_hs2_panel")
    hs2_regressions = read_csv("exercise_11_hs2_regressions")
    commodity_comparison = read_csv("exercise_11_commodity_comparison")
    commodity_stats = read_csv("exercise_11_commodity_stats")
    methods_hs6_counts = pd.DataFrame()
    if include_methods_hs6_diagnostics():
        methods_hs6_counts = read_csv("methods_hs6_codes_by_year")
        require_columns(
            methods_hs6_counts,
            "Methods HS6 codes by year",
            {
                "country_sample",
                "year",
                "flow",
                "observed_hs6_codes",
                "active_country_year_hs6_products",
                "reporters_with_trade",
                "reporter_year_flow_observations",
                "trade_value",
                "product_universe",
                "excluded_hs6_codes",
            },
        )
        for column in [
            "year",
            "observed_hs6_codes",
            "active_country_year_hs6_products",
            "reporters_with_trade",
            "reporter_year_flow_observations",
            "trade_value",
            "flow_order",
        ]:
            if column in methods_hs6_counts.columns:
                methods_hs6_counts[column] = pd.to_numeric(methods_hs6_counts[column], errors="coerce")
        sort_cols = ["year", "flow_order"] if "flow_order" in methods_hs6_counts.columns else ["year", "flow"]
        methods_hs6_counts = methods_hs6_counts.sort_values(sort_cols).reset_index(drop=True)
    prof_p_top_shares = pd.DataFrame(columns=["country"])
    prof_p_lorenz = pd.DataFrame()
    if include_prof_p_page():
        prof_p_top_shares = read_prof_p_csv("prof_p_top_shares")
        prof_p_lorenz = read_prof_p_csv("prof_p_lorenz")

        require_columns(
            prof_p_top_shares,
            "Prof P top-share comparison",
            {
                "country",
                "iso3",
                "reporter_code",
                "year",
                "flow",
                "sample",
                "product_universe",
                "partner_world_aggregate_excluded",
                "modern_top_1pct_product_share",
                "modern_top_5pct_product_share",
                "top_1pct_cutoff_products",
                "top_5pct_cutoff_products",
                "modern_product_gini",
                "paper_product_gini",
                "product_gini_diff",
                "modern_active_products",
                "paper_active_products",
                "active_products_diff",
                "comparison_note",
            },
        )
        require_columns(
            prof_p_lorenz,
            "Prof P Lorenz points",
            {
                "country",
                "iso3",
                "reporter_code",
                "year",
                "flow",
                "point_index",
                "cum_products_share",
                "cum_trade_value_share",
            },
        )
        for frame in [prof_p_top_shares, prof_p_lorenz]:
            for column in frame.columns:
                if column not in {
                    "country",
                    "iso3",
                    "flow",
                    "sample",
                    "product_universe",
                    "partner_world_aggregate_excluded",
                    "comparison_note",
                }:
                    frame[column] = pd.to_numeric(frame[column], errors="coerce")
        prof_p_top_shares = prof_p_top_shares.sort_values(["flow", "country"]).reset_index(drop=True)
        prof_p_lorenz = prof_p_lorenz.sort_values(["flow", "country", "point_index"]).reset_index(drop=True)

    country_size = load_country_size_data()
    growth_effect = load_growth_effect_data()
    future_growth = load_future_growth_data()
    partner_stability = load_partner_stability_data()
    ex12_extensive = load_ex12_extensive_margin_data()
    ex12_ev_hs4 = load_ex12_ev_hs4_expansion_data()
    ex12_ev_hs6_harmonized = load_ex12_ev_hs6_harmonized_expansion_data()
    cadot_hump = load_cadot_hump_data()
    contributions = load_contributions_data()

    require_columns(
        top_goods,
        "Exercise 3 top goods",
        {
            "scope",
            "import_bin",
            "rank_in_bin",
            "cmd_code",
            "desc",
            "import_value_usd_bn",
            "share_of_bin_pct",
            "share_of_total_pct",
        },
    )
    top_goods["cmd_code"] = top_goods["cmd_code"].map(normalize_hs6)
    top_goods = top_goods[~top_goods["cmd_code"].eq("999999")].copy()
    for column in ["rank_in_bin", "import_value_usd_bn", "share_of_bin_pct", "share_of_total_pct"]:
        top_goods[column] = pd.to_numeric(top_goods[column], errors="coerce")

    required_nonempty = {
        name: len(read_csv(name))
        for name in SOURCE_FILES
        if name not in {"exercise_1_panel"}
    }

    world_relative_latest_year = int(world_relative_panel["year"].max()) if not world_relative_panel.empty else None
    world_relative_import_latest_year = (
        int(world_relative_import_panel["year"].max()) if not world_relative_import_panel.empty else None
    )
    selected_years = [1988, 2001, 2024, 2025]
    ex1_metric_columns = [
        "product_gini",
        "partner_gini",
        "product_partner_cell_gini",
        "product_top_1pct_share",
        "product_top_5pct_share",
        "top_5_partner_share",
    ]
    for optional_metric in [
        "world_relative_product_gini",
        "world_relative_import_product_gini",
        "world_weighted_share_gini",
        "world_weighted_product_coverage",
        "zero_weight_country_export_share",
        "world_weighted_import_share_gini",
        "world_weighted_import_product_coverage",
        "zero_weight_country_import_share",
    ]:
        if optional_metric in ex1.columns:
            ex1_metric_columns.append(optional_metric)
    ex1_medians = (
        ex1.groupby("flow")[ex1_metric_columns]
        .median()
        .reindex(FLOW_ORDER)
        .reset_index()
    )
    ex1_year_medians = (
        ex1[ex1["year"].isin(selected_years)]
        .groupby(["flow", "year"])[ex1_metric_columns]
        .median()
        .reset_index()
        .sort_values(["flow", "year"])
    )

    map_year = int(ex1["year"].max())
    panel_columns = [
        "iso3",
        "country",
        "reporter_code",
        "year",
        "flow",
        "total_trade_value",
        "product_gini",
        "partner_gini",
        "product_partner_cell_gini",
        "world_relative_product_gini",
        "world_relative_import_product_gini",
        "world_weighted_share_gini",
        "world_weighted_product_coverage",
        "zero_weight_country_export_share",
        "world_relative_minus_active_product_gini",
        "world_weighted_import_share_gini",
        "world_weighted_import_product_coverage",
        "zero_weight_country_import_share",
        "world_relative_import_minus_active_product_gini",
        "product_top_1pct_share",
        "product_top_5pct_share",
        "top_5_partner_share",
    ]
    country_panel = clean_records(ex1.sort_values(["country", "year", "flow"]), panel_columns)
    latest_map = clean_records(ex1[ex1["year"].eq(map_year)].sort_values(["flow", "country"]), panel_columns)
    countries = clean_records(
        ex1[["country", "iso3", "reporter_code"]].drop_duplicates().sort_values("country"),
        ["country", "iso3", "reporter_code"],
    )

    growth_summary = clean_records(
        growth.sort_values(["horizon", "concentration_bucket"]),
        [
            "horizon",
            "concentration_bucket",
            "observations",
            "mean_annualized_log_growth",
            "median_annualized_log_growth",
            "mean_export_growth_pct",
            "median_initial_exports",
        ],
    )
    require_columns(
        growth_models,
        "Exercise 2 bucket-growth models",
        {
            "model_id",
            "model_label",
            "horizon",
            "outcome",
            "predictor",
            "controls",
            "nobs",
            "countries",
            "variable",
            "variable_role",
            "coefficient",
            "std_error",
            "t_stat",
            "dropped_rows",
        },
    )
    require_columns(
        growth_diagnostics,
        "Exercise 2 bucket-growth diagnostics",
        {"model_id", "model_label", "horizon", "candidate_rows", "nobs", "dropped_rows", "countries", "status"},
    )
    growth_model_focus = growth_models[
        growth_models["model_label"].isin(["bucket_country_year_fe_core", "bucket_country_year_fe_controls"])
        & growth_models["variable"].eq("bucket_high_product_low_partner")
        & growth_models["variable_role"].eq("main")
    ].copy()
    for column in ["horizon", "nobs", "countries", "coefficient", "std_error", "t_stat", "dropped_rows"]:
        growth_model_focus[column] = pd.to_numeric(growth_model_focus[column], errors="coerce")
    growth_model_focus = growth_model_focus.sort_values(["model_label", "horizon"])
    growth_diagnostic_focus = growth_diagnostics[
        growth_diagnostics["model_label"].isin(["bucket_country_year_fe_core", "bucket_country_year_fe_controls"])
    ].copy()
    for column in ["horizon", "candidate_rows", "nobs", "dropped_rows", "countries"]:
        growth_diagnostic_focus[column] = pd.to_numeric(growth_diagnostic_focus[column], errors="coerce")
    growth_diagnostic_focus = growth_diagnostic_focus.sort_values(["model_label", "horizon"])

    ex_import = exclusions[exclusions["flow"].eq("Imports")].copy()
    exclusion_medians = (
        ex_import.groupby("variant")[
            ["product_gini", "product_top_1pct_share", "product_top_5pct_share", "trade_share_removed"]
        ]
        .median(numeric_only=True)
        .reset_index()
    )
    exclusion_medians["label"] = exclusion_medians["variant"].map(EXCLUSION_LABELS).fillna(exclusion_medians["variant"])
    exclusion_order = list(EXCLUSION_LABELS)
    exclusion_medians["order"] = exclusion_medians["variant"].map({value: i for i, value in enumerate(exclusion_order)})
    exclusion_medians = exclusion_medians.sort_values("order")
    exclusion_years = (
        ex_import.groupby(["year", "variant"])[["product_gini", "trade_share_removed"]]
        .median(numeric_only=True)
        .reset_index()
    )
    exclusion_years["label"] = exclusion_years["variant"].map(EXCLUSION_LABELS).fillna(exclusion_years["variant"])
    exclusion_distribution = ex_import[
        [
            "country",
            "iso3",
            "reporter_code",
            "year",
            "variant",
            "product_gini",
            "trade_share_removed",
            "product_active_count",
        ]
    ].copy()
    exclusion_distribution["label"] = (
        exclusion_distribution["variant"].map(EXCLUSION_LABELS).fillna(exclusion_distribution["variant"])
    )
    exclusion_distribution["order"] = exclusion_distribution["variant"].map(
        {value: i for i, value in enumerate(exclusion_order)}
    )
    exclusion_distribution = (
        exclusion_distribution.dropna(subset=["product_gini"])
        .sort_values(["order", "country", "year"])
        .reset_index(drop=True)
    )

    hs2_summary = (
        hs2.groupby("flow")[["actual_gini", "sim_gini_median", "actual_minus_sim_median_gini", "actual_gini_percentile"]]
        .median(numeric_only=True)
        .reindex(FLOW_ORDER)
        .reset_index()
    )
    active_product = active[active["dimension"].eq("product")].copy()
    active_summary = (
        active_product.groupby("flow")[["actual_gini", "sim_gini_median", "actual_minus_sim_median_gini", "actual_gini_percentile"]]
        .median(numeric_only=True)
        .reindex(FLOW_ORDER)
        .reset_index()
    )
    hs2_latest = (
        hs2[hs2["year"].eq(hs2["year"].max())]
        .groupby("flow")[["actual_gini", "sim_gini_median", "actual_minus_sim_median_gini", "actual_gini_percentile"]]
        .median(numeric_only=True)
        .reindex(FLOW_ORDER)
        .reset_index()
    )
    benchmark_ladder = []
    for null_label, frame in [("Active-count-only null", active_summary), ("HS2-preserving null", hs2_summary)]:
        for row in frame.to_dict(orient="records"):
            benchmark_ladder.append(
                {
                    "benchmark": null_label,
                    "flow": row["flow"],
                    "actual_gini": clean_scalar(row["actual_gini"]),
                    "sim_gini_median": clean_scalar(row["sim_gini_median"]),
                    "gap": clean_scalar(row["actual_minus_sim_median_gini"]),
                    "percentile": clean_scalar(row["actual_gini_percentile"]),
                }
            )

    bins_summary = (
        bins.groupby("import_bin")[["product_gini", "top_1_product_share", "top_5_product_share", "active_products"]]
        .median(numeric_only=True)
        .reset_index()
    )
    decomp_summary = (
        decomp.groupby("import_bin")[
            [
                "import_value_share",
                "top_10_product_share_contribution",
                "product_gini_without_bin",
                "product_gini_reduction_when_excluded",
            ]
        ]
        .median(numeric_only=True)
        .reset_index()
    )
    bin_summary = bins_summary.merge(decomp_summary, on="import_bin", how="outer")
    bin_summary["label"] = bin_summary["import_bin"].map(BIN_LABELS).fillna(bin_summary["import_bin"])
    bin_year_country_counts = bins.groupby("year")["iso3"].nunique().sort_index()
    max_bin_country_count = int(bin_year_country_counts.max()) if not bin_year_country_counts.empty else 0
    stable_bin_country_floor = int(math.ceil(max_bin_country_count * 0.8)) if max_bin_country_count else 0
    stable_bin_years = (
        bin_year_country_counts[bin_year_country_counts.ge(stable_bin_country_floor)]
        if stable_bin_country_floor
        else pd.Series(dtype=float)
    )
    stable_latest_bin_year = (
        int(stable_bin_years.index.max())
        if not stable_bin_years.empty
        else (int(bin_year_country_counts.index.max()) if not bin_year_country_counts.empty else None)
    )
    stable_latest_bin_country_count = (
        int(bin_year_country_counts.loc[stable_latest_bin_year]) if stable_latest_bin_year is not None else 0
    )
    if stable_latest_bin_year is not None:
        stable_bins = bins[bins["year"].eq(stable_latest_bin_year)].copy()
        stable_decomp = decomp[decomp["year"].eq(stable_latest_bin_year)].copy()
        stable_bins_summary = (
            stable_bins.groupby("import_bin")[
                ["product_gini", "top_1_product_share", "top_5_product_share", "active_products"]
            ]
            .median(numeric_only=True)
            .reset_index()
        )
        stable_decomp_summary = (
            stable_decomp.groupby("import_bin")[
                [
                    "import_value_share",
                    "top_10_product_share_contribution",
                    "product_gini_without_bin",
                    "product_gini_reduction_when_excluded",
                ]
            ]
            .median(numeric_only=True)
            .reset_index()
        )
        stable_bin_country_summary = (
            stable_bins.groupby("import_bin")["iso3"].nunique().rename("countries").reset_index()
        )
        stable_bin_summary = (
            stable_bins_summary.merge(stable_decomp_summary, on="import_bin", how="outer")
            .merge(stable_bin_country_summary, on="import_bin", how="left")
        )
        stable_bin_summary["label"] = stable_bin_summary["import_bin"].map(BIN_LABELS).fillna(
            stable_bin_summary["import_bin"]
        )
    else:
        stable_bin_summary = bin_summary.iloc[0:0].copy()
        stable_bin_summary["countries"] = []
    energy_excluded_import = decomp[decomp["import_bin"].astype(str).eq("energy")].copy()
    energy_excluded_import = energy_excluded_import.rename(
        columns={
            "total_product_gini": "baseline_product_gini",
            "product_gini_without_bin": "product_gini_ex_energy",
            "import_value_share": "energy_import_share",
            "total_imports_without_bin": "total_imports_without_energy",
            "active_products_without_bin": "active_products_without_energy",
        }
    )
    energy_excluded_columns = [
        "country",
        "iso3",
        "reporter_code",
        "year",
        "baseline_product_gini",
        "product_gini_ex_energy",
        "energy_import_share",
        "total_imports",
        "total_imports_in_bin",
        "total_imports_without_energy",
        "active_products_without_energy",
    ]
    for column in [
        "reporter_code",
        "year",
        "baseline_product_gini",
        "product_gini_ex_energy",
        "energy_import_share",
        "total_imports",
        "total_imports_in_bin",
        "total_imports_without_energy",
        "active_products_without_energy",
    ]:
        energy_excluded_import[column] = pd.to_numeric(energy_excluded_import[column], errors="coerce")
    energy_excluded_import = (
        energy_excluded_import.replace([np.inf, -np.inf], np.nan)
        .dropna(subset=["iso3", "country", "year", "product_gini_ex_energy"])
        .sort_values(["country", "year"])
        .reset_index(drop=True)
    )
    energy_driver_columns = [
        "country",
        "iso3",
        "reporter_code",
        "start_year",
        "end_year",
        "gini_change_direction",
        "main_driver_bucket",
        "main_driver_group",
        "delta_calculated_ex_energy_gini",
        "delta_panel_ex_energy_gini",
        "delta_top5_share",
        "delta_top5_gini_contribution",
        "delta_rank6_50_share",
        "delta_rank6_50_gini_contribution",
        "delta_rank51_200_share",
        "delta_rank51_200_gini_contribution",
        "delta_rank201_plus_share",
        "delta_rank201_plus_gini_contribution",
    ]
    energy_driver_classification = pd.DataFrame(columns=energy_driver_columns)
    if "energy_gini_driver_classification_balanced" in SOURCE_FILES:
        energy_driver_classification = read_csv("energy_gini_driver_classification_balanced")
        require_columns(
            energy_driver_classification,
            "Energy-excluded import Gini driver classification",
            set(energy_driver_columns),
        )
        for column in [
            "reporter_code",
            "start_year",
            "end_year",
            "delta_calculated_ex_energy_gini",
            "delta_panel_ex_energy_gini",
            "delta_top5_share",
            "delta_top5_gini_contribution",
            "delta_rank6_50_share",
            "delta_rank6_50_gini_contribution",
            "delta_rank51_200_share",
            "delta_rank51_200_gini_contribution",
            "delta_rank201_plus_share",
            "delta_rank201_plus_gini_contribution",
        ]:
            energy_driver_classification[column] = pd.to_numeric(
                energy_driver_classification[column], errors="coerce"
            )
        energy_driver_classification = (
            energy_driver_classification.replace([np.inf, -np.inf], np.nan)
            .dropna(subset=["iso3", "country", "main_driver_group"])
            .sort_values(["main_driver_group", "country"])
            .reset_index(drop=True)
        )
    nonenergy_rank_columns = [
        "country",
        "iso3",
        "reporter_code",
        "snapshot",
        "year",
        "top5_share",
        "rank6_50_share",
        "rank51_200_share",
        "rank201_plus_share",
        "top10_share",
        "active_nonenergy_products",
        "total_nonenergy_imports",
    ]
    nonenergy_rank_decomposition = pd.DataFrame(columns=nonenergy_rank_columns)
    if "nonenergy_rank_decomposition_balanced" in SOURCE_FILES:
        nonenergy_rank_decomposition = read_csv("nonenergy_rank_decomposition_balanced")
        require_columns(
            nonenergy_rank_decomposition,
            "Non-energy import rank-bucket decomposition",
            set(nonenergy_rank_columns),
        )
        for column in [
            "reporter_code",
            "year",
            "top5_share",
            "rank6_50_share",
            "rank51_200_share",
            "rank201_plus_share",
            "top10_share",
            "active_nonenergy_products",
            "total_nonenergy_imports",
        ]:
            nonenergy_rank_decomposition[column] = pd.to_numeric(
                nonenergy_rank_decomposition[column], errors="coerce"
            )
        nonenergy_rank_decomposition = (
            nonenergy_rank_decomposition.replace([np.inf, -np.inf], np.nan)
            .dropna(subset=["iso3", "country", "snapshot", "year", "top5_share", "rank6_50_share", "rank51_200_share", "rank201_plus_share"])
            .sort_values(["country", "year"])
            .reset_index(drop=True)
        )
        if nonenergy_rank_decomposition.empty:
            raise RuntimeError("Non-energy import rank-bucket decomposition is empty for rd2_countries.")
        share_sum = nonenergy_rank_decomposition[
            ["top5_share", "rank6_50_share", "rank51_200_share", "rank201_plus_share"]
        ].sum(axis=1)
        max_share_gap = float((share_sum - 1).abs().max())
        if max_share_gap > 1e-6:
            raise RuntimeError(
                "Non-energy import rank-bucket decomposition shares do not sum to 1. "
                f"Max absolute gap: {max_share_gap:.6g}"
            )
    nonenergy_top_product_columns = [
        "country",
        "iso3",
        "reporter_code",
        "snapshot",
        "year",
        "rank",
        "cmd_code",
        "product_label",
        "exercise_03_bin",
        "trade_value",
        "share_nonenergy_imports",
        "total_nonenergy_imports",
    ]
    nonenergy_top_products = pd.DataFrame(columns=nonenergy_top_product_columns)
    if "nonenergy_top_products_balanced" in SOURCE_FILES:
        nonenergy_top_products = read_csv("nonenergy_top_products_balanced")
        require_columns(
            nonenergy_top_products,
            "Top non-energy import products by country snapshot",
            set(nonenergy_top_product_columns),
        )
        nonenergy_top_products["cmd_code"] = nonenergy_top_products["cmd_code"].map(normalize_hs6)
        nonenergy_top_products = nonenergy_top_products[~nonenergy_top_products["cmd_code"].eq("999999")].copy()
        for column in [
            "reporter_code",
            "year",
            "rank",
            "trade_value",
            "share_nonenergy_imports",
            "total_nonenergy_imports",
        ]:
            nonenergy_top_products[column] = pd.to_numeric(nonenergy_top_products[column], errors="coerce")
        nonenergy_top_products = (
            nonenergy_top_products.replace([np.inf, -np.inf], np.nan)
            .dropna(subset=["iso3", "country", "snapshot", "year", "rank", "cmd_code", "trade_value", "share_nonenergy_imports"])
            .sort_values(["country", "year", "rank"])
            .reset_index(drop=True)
        )
        if nonenergy_top_products.empty:
            raise RuntimeError("Top non-energy import product table is empty for rd2_countries.")
    total_import_summary = (
        total_import[["product_gini", "top_1_product_share", "top_5_product_share", "top_10_product_share", "active_products"]]
        .median(numeric_only=True)
        .to_dict()
    )

    supplier_summary = suppliers[
        [
            "weighted_mean_top_supplier_share",
            "weighted_mean_source_hhi",
            "median_top_supplier_share",
            "share_products_top_supplier_ge_75",
            "import_value_share_products_top_supplier_ge_75",
        ]
    ].median(numeric_only=True)
    india_2024 = suppliers[(suppliers["iso3"].eq("IND")) & (suppliers["year"].eq(2024))]
    india_supplier = india_2024.iloc[0] if not india_2024.empty else pd.Series(dtype=object)
    supplier_years = (
        suppliers.groupby("year")[
            [
                "weighted_mean_top_supplier_share",
                "median_top_supplier_share",
                "share_products_top_supplier_ge_75",
                "import_value_share_products_top_supplier_ge_75",
            ]
        ]
        .median(numeric_only=True)
        .reset_index()
    )
    h24_supplier_years = h24_supplier_summary[
        [
            "year",
            "median_top_supplier_share",
            "share_products_top_supplier_ge_75",
            "import_value_share_top_supplier_ge_75",
            "share_products_dominant_specialized",
            "import_value_share_dominant_specialized",
        ]
    ].copy()
    for column in h24_supplier_years.columns:
        h24_supplier_years[column] = pd.to_numeric(h24_supplier_years[column], errors="coerce")
    h24_supplier_years = h24_supplier_years.sort_values("year").reset_index(drop=True)
    h24_latest_year = int(h24_supplier_years["year"].max()) if not h24_supplier_years.empty else None
    latest_supplier_year = int(suppliers["year"].max()) if not suppliers.empty else None
    latest_supplier_reporter_count = (
        int(suppliers.loc[suppliers["year"].eq(latest_supplier_year), "iso3"].nunique()) if latest_supplier_year else None
    )
    india_latest_year = int(suppliers.loc[suppliers["iso3"].eq("IND"), "year"].max()) if not suppliers[suppliers["iso3"].eq("IND")].empty else None
    for frame in [partner_counterfactual, partner_counterfactual_latest]:
        for column in frame.columns:
            if column not in {"country", "iso3", "source_file", "exercise4_country", "exercise4_iso3"}:
                frame[column] = pd.to_numeric(frame[column], errors="coerce")
    partner_counterfactual_latest = partner_counterfactual_latest.sort_values(
        ["partner_gini_reduction", "country"], ascending=[False, True]
    ).reset_index(drop=True)
    india_partner_counterfactual = partner_counterfactual[partner_counterfactual["iso3"].eq("IND")].sort_values(
        "year"
    ).reset_index(drop=True)
    partner_counterfactual_summary = partner_counterfactual_latest[
        [
            "actual_partner_gini",
            "counterfactual_partner_gini",
            "partner_gini_reduction",
            "explained_share",
            "counterfactual_residual_share",
            "full_diffusion_reduction",
            "full_diffusion_explained_share",
            "partner_gini_validation_abs_diff",
        ]
    ].median(numeric_only=True)
    partner_counterfactual_india_latest = (
        india_partner_counterfactual.iloc[-1] if not india_partner_counterfactual.empty else pd.Series(dtype=object)
    )

    io_valid = io.dropna(subset=["weighted_top_sector_input_product_gini"]).copy()
    io_medians = io_valid[
        [
            "weighted_top_sector_input_product_gini",
            "weighted_top_sector_top_supplier_share",
            "weighted_top_sector_source_hhi",
            "median_top_sector_matched_requirement_share",
            "top_export_value_share",
        ]
    ].median(numeric_only=True)
    india_io_valid = io_valid[io_valid["iso3"].eq("IND")].sort_values("year")
    india_io_latest = india_io_valid.iloc[-1] if not india_io_valid.empty else pd.Series(dtype=object)
    io_years = (
        io_valid.groupby("year")[
            [
                "weighted_top_sector_input_product_gini",
                "weighted_top_sector_top_supplier_share",
                "median_top_sector_matched_requirement_share",
            ]
        ]
        .median(numeric_only=True)
        .reset_index()
    )

    hs6_value = pick_regression_row(coefs, "product_export_value_gini", "loo_gini_contribution_z", "baseline")
    hs6_any = pick_regression_row(coefs, "product_export_any_gini", "loo_gini_contribution_z", "baseline")
    partner_hhi = pick_regression_row(coefs, "product_export_value_partner_hhi", "loo_partner_hhi_contribution_z", "baseline")
    intermediate_base = pick_regression_row(
        coefs,
        "product_export_value_intermediate_interaction",
        "loo_gini_contribution_z",
        "baseline",
    )
    intermediate_interaction = pick_regression_row(
        coefs,
        "product_export_value_intermediate_interaction",
        "loo_gini_x_intermediate_z",
        "baseline",
    )
    hs2_value = pick_regression_row(hs2_regressions, "hs2_export_value_gini", "hs2_product_loo_gini_sum_z")
    hs2_any = pick_regression_row(hs2_regressions, "hs2_export_any_gini", "hs2_product_loo_gini_sum_z")
    hs2_share = pick_regression_row(hs2_regressions, "hs2_export_share_gini", "hs2_product_loo_gini_sum_z")
    hs2_interaction = pick_regression_row(
        hs2_regressions,
        "hs2_export_value_intermediate_intensity",
        "hs2_product_loo_gini_sum_x_intermediate_share_z",
    )
    hs2_linkage = hs2_linkage_summary(hs2_panel)

    ex11_regression_summary = [
        regression_display_row("HS6 Product-Gini contribution", hs6_value, "Negative export-value linkage"),
        regression_display_row("HS6 export probability", hs6_any, "Negative export-probability linkage"),
        regression_display_row("HS6 supplier-country HHI contribution", partner_hhi, "Positive export-value linkage"),
        regression_display_row("Intermediate interaction", intermediate_interaction, "Intermediates are not more export-linked"),
        regression_display_row("HS2 Product-Gini contribution", hs2_value, "Still negative after broadening to HS2"),
        regression_display_row("HS2 export probability", hs2_any, "Small and not statistically distinguishable from zero"),
        regression_display_row("HS2 export share", hs2_share, "Small and not statistically distinguishable from zero"),
        regression_display_row("HS2 intermediate-intensity interaction", hs2_interaction, "Does not rescue the intermediate channel"),
    ]

    commodity_summary_rows = commodity_comparison[
        (
            commodity_comparison["sample"].astype(str).isin(["baseline", "excluding oil/gas/gold/coal"])
        )
        & (
            commodity_comparison["check"].astype(str).str.lower().isin(
                [
                    "export value: product-gini contribution",
                    "export probability: product-gini contribution",
                    "export value: partner-hhi contribution",
                    "intermediate interaction",
                ]
            )
        )
    ].copy()
    commodity_summary_rows["result"] = commodity_summary_rows["sample"].astype(str) + " - " + commodity_summary_rows["check"].astype(str)
    commodity_summary_rows["result"] = (
        commodity_summary_rows["result"]
        .str.replace("product-Gini", "Product-Gini", regex=False)
        .str.replace("partner-HHI", "Partner-HHI", regex=False)
    )

    commodity_stats_map = {
        str(row["measure"]): clean_scalar(row["value"])
        for row in commodity_stats.to_dict(orient="records")
    }

    data = {
        "metadata": {
            "created_at_utc": now_utc(),
            "country_sample": ACTIVE_SITE_SAMPLE,
            "source_root": "local research repository",
            "pdf_guidance_present": PDF_GUIDANCE.exists(),
            "site_scope": (
                "Exercises 1, 2 descriptive growth note, 3, 4, 6, 10, 11, 12 harmonized-HS6 persistent expansion decomposition, plus rd2 country-size, growth-effect, and future-growth pages."
                if country_size and growth_effect and future_growth
                else (
                    "Exercises 1, 2 descriptive growth note, 3, 4, 6, 10, 11, 12 harmonized-HS6 persistent expansion decomposition, and rd2 supplemental pages."
                    if country_size or growth_effect or future_growth
                    else "Exercises 1, 2 descriptive growth note, 3, 4, 6, 10, 11, and 12 harmonized-HS6 persistent expansion decomposition."
                )
            ),
            "product_excluded_hs6_codes": sorted(EXCLUDED_HS6_CODES),
            "partner_concentration_includes_hs6_codes": sorted(EXCLUDED_HS6_CODES),
            "data_checks": {"exercise_1": shape, "required_table_rows": required_nonempty},
        },
        "labels": {
            "metrics": METRIC_LABELS,
            "exclusions": EXCLUSION_LABELS,
            "bins": BIN_LABELS,
        },
        "methods": {
            "hs6_codes_by_year": clean_records(methods_hs6_counts, list(methods_hs6_counts.columns))
            if not methods_hs6_counts.empty
            else [],
        },
        "countries": countries,
        "exercise1": {
            "panel": country_panel,
            "latest_map": latest_map,
            "median_by_flow": clean_records(ex1_medians, list(ex1_medians.columns)),
            "selected_year_medians": clean_records(ex1_year_medians, list(ex1_year_medians.columns)),
            "default_metric": "product_gini",
            "default_year": map_year,
        },
        "worldRelative": {
            "panel": clean_records(world_relative_panel, list(world_relative_panel.columns))
            if not world_relative_panel.empty
            else [],
            "appendix": clean_records(world_relative_appendix, list(world_relative_appendix.columns))
            if not world_relative_appendix.empty
            else [],
            "diagnostics": clean_records(world_relative_diagnostics, list(world_relative_diagnostics.columns))
            if not world_relative_diagnostics.empty
            else [],
            "classification_diagnostics": clean_records(
                world_relative_classification_diagnostics,
                list(world_relative_classification_diagnostics.columns),
            )
            if not world_relative_classification_diagnostics.empty
            else [],
            "harmonization_diagnostics": clean_records(
                world_relative_harmonization_diagnostics,
                list(world_relative_harmonization_diagnostics.columns),
            )
            if not world_relative_harmonization_diagnostics.empty
            else [],
            "yearly_summary": clean_records(world_relative_yearly, list(world_relative_yearly.columns))
            if not world_relative_yearly.empty
            else [],
            "latest_rankings": clean_records(world_relative_latest, list(world_relative_latest.columns))
            if not world_relative_latest.empty
            else [],
            "contribution_top_drivers": clean_records(world_relative_contribution_top, list(world_relative_contribution_top.columns))
            if not world_relative_contribution_top.empty
            else [],
            "contribution_country_year_summary": clean_records(
                world_relative_contribution_summary,
                list(world_relative_contribution_summary.columns),
            )
            if not world_relative_contribution_summary.empty
            else [],
            "contribution_latest_small_countries": clean_records(
                world_relative_contribution_latest_small,
                list(world_relative_contribution_latest_small.columns),
            )
            if not world_relative_contribution_latest_small.empty
            else [],
            "contribution_bucket_summary": clean_records(
                world_relative_contribution_bucket,
                list(world_relative_contribution_bucket.columns),
            )
            if not world_relative_contribution_bucket.empty
            else [],
            "contribution_validation": clean_records(
                world_relative_contribution_validation,
                list(world_relative_contribution_validation.columns),
            )
            if not world_relative_contribution_validation.empty
            else [],
            "latest_year": world_relative_latest_year,
            "import_panel": clean_records(world_relative_import_panel, list(world_relative_import_panel.columns))
            if not world_relative_import_panel.empty
            else [],
            "import_appendix": clean_records(world_relative_import_appendix, list(world_relative_import_appendix.columns))
            if not world_relative_import_appendix.empty
            else [],
            "import_diagnostics": clean_records(world_relative_import_diagnostics, list(world_relative_import_diagnostics.columns))
            if not world_relative_import_diagnostics.empty
            else [],
            "import_classification_diagnostics": clean_records(
                world_relative_import_classification_diagnostics,
                list(world_relative_import_classification_diagnostics.columns),
            )
            if not world_relative_import_classification_diagnostics.empty
            else [],
            "import_harmonization_diagnostics": clean_records(
                world_relative_import_harmonization_diagnostics,
                list(world_relative_import_harmonization_diagnostics.columns),
            )
            if not world_relative_import_harmonization_diagnostics.empty
            else [],
            "import_yearly_summary": clean_records(world_relative_import_yearly, list(world_relative_import_yearly.columns))
            if not world_relative_import_yearly.empty
            else [],
            "import_latest_rankings": clean_records(world_relative_import_latest, list(world_relative_import_latest.columns))
            if not world_relative_import_latest.empty
            else [],
            "import_contribution_top_drivers": clean_records(
                world_relative_import_contribution_top,
                list(world_relative_import_contribution_top.columns),
            )
            if not world_relative_import_contribution_top.empty
            else [],
            "import_contribution_country_year_summary": clean_records(
                world_relative_import_contribution_summary,
                list(world_relative_import_contribution_summary.columns),
            )
            if not world_relative_import_contribution_summary.empty
            else [],
            "import_contribution_latest_small_countries": clean_records(
                world_relative_import_contribution_latest_small,
                list(world_relative_import_contribution_latest_small.columns),
            )
            if not world_relative_import_contribution_latest_small.empty
            else [],
            "import_contribution_bucket_summary": clean_records(
                world_relative_import_contribution_bucket,
                list(world_relative_import_contribution_bucket.columns),
            )
            if not world_relative_import_contribution_bucket.empty
            else [],
            "import_contribution_validation": clean_records(
                world_relative_import_contribution_validation,
                list(world_relative_import_contribution_validation.columns),
            )
            if not world_relative_import_contribution_validation.empty
            else [],
            "import_latest_year": world_relative_import_latest_year,
        },
        "exercise2": {
            "growth_summary": growth_summary,
            "model_focus": clean_records(
                growth_model_focus,
                [
                    "model_label",
                    "horizon",
                    "nobs",
                    "countries",
                    "coefficient",
                    "std_error",
                    "t_stat",
                    "dropped_rows",
                ],
            ),
            "diagnostics": clean_records(
                growth_diagnostic_focus,
                ["model_label", "horizon", "candidate_rows", "nobs", "dropped_rows", "countries", "status"],
            ),
        },
        "exercise3": {
            "bin_summary": clean_records(bin_summary, list(bin_summary.columns)),
            "stable_latest_year": stable_latest_bin_year,
            "stable_latest_country_count": stable_latest_bin_country_count,
            "stable_latest_bin_summary": clean_records(stable_bin_summary, list(stable_bin_summary.columns)),
            "energy_excluded_import_panel": clean_records(energy_excluded_import, energy_excluded_columns),
            "energy_driver_classification": clean_records(energy_driver_classification, energy_driver_columns),
            "nonenergy_rank_decomposition": clean_records(
                nonenergy_rank_decomposition,
                nonenergy_rank_columns,
            ),
            "nonenergy_top_products": clean_records(
                nonenergy_top_products,
                nonenergy_top_product_columns,
            ),
            "total_import_summary": {key: clean_scalar(value) for key, value in total_import_summary.items()},
            "top_goods": clean_records(
                top_goods.sort_values(["scope", "import_bin", "rank_in_bin"]),
                [
                    "scope",
                    "import_bin",
                    "rank_in_bin",
                    "cmd_code",
                    "desc",
                    "import_value_usd_bn",
                    "share_of_bin_pct",
                    "share_of_total_pct",
                ],
            ),
        },
        "exercise4": {
            "summary": {key: clean_scalar(value) for key, value in supplier_summary.items()},
            "india_2024": {
                key: clean_scalar(india_supplier.get(key))
                for key in [
                    "year",
                    "total_imports",
                    "import_products",
                    "weighted_mean_top_supplier_share",
                    "weighted_mean_source_hhi",
                    "median_top_supplier_share",
                    "share_products_top_supplier_ge_75",
                    "import_value_share_products_top_supplier_ge_75",
                ]
            },
            "year_series": clean_records(supplier_years, list(supplier_years.columns)),
            "latest_year": latest_supplier_year,
            "latest_reporter_count": latest_supplier_reporter_count,
            "india_latest_year": india_latest_year,
            "partner_gini_counterfactual": {
                "summary": {key: clean_scalar(value) for key, value in partner_counterfactual_summary.items()},
                "latest": clean_records(
                    partner_counterfactual_latest,
                    [
                        "country",
                        "iso3",
                        "year",
                        "actual_partner_gini",
                        "counterfactual_partner_gini",
                        "partner_gini_reduction",
                        "explained_share",
                        "counterfactual_residual_share",
                        "full_diffusion_reduction",
                        "full_diffusion_explained_share",
                        "active_products",
                        "active_partners",
                        "partner_gini_validation_abs_diff",
                    ],
                ),
                "india_latest": {
                    key: clean_scalar(partner_counterfactual_india_latest.get(key))
                    for key in [
                        "year",
                        "actual_partner_gini",
                        "counterfactual_partner_gini",
                        "partner_gini_reduction",
                        "explained_share",
                        "counterfactual_residual_share",
                        "full_diffusion_reduction",
                        "full_diffusion_explained_share",
                        "active_products",
                        "active_partners",
                        "partner_gini_validation_abs_diff",
                    ]
                },
                "india_year_series": clean_records(
                    india_partner_counterfactual,
                    [
                        "year",
                        "actual_partner_gini",
                        "counterfactual_partner_gini",
                        "partner_gini_reduction",
                        "explained_share",
                        "full_diffusion_explained_share",
                    ],
                ),
            },
        },
        "h24Supplier": {
            "year_series": clean_records(h24_supplier_years, list(h24_supplier_years.columns)),
            "comparison": clean_records(h24_supplier_comparison, list(h24_supplier_comparison.columns)),
            "latest_year": h24_latest_year,
        },
        "profP": {
            "metadata": {
                "sample": "prof_p_33",
                "year": 2001,
                "unit": "country-flow",
                "product_universe": "Active positive HS6 product totals after WCO HS1996-to-HS2002 first-listed-target aggregation.",
                "product_excluded_hs6_codes": ["999999"],
                "partner_rule": "Rows with partnerCode 0 (World aggregate) are excluded before product aggregation.",
                "paper_comparison_limit": "Professor P Table 2 reports product Gini and active product counts only; top-1% and top-5% product shares are modern computed diagnostics.",
                "top_share_formula": "Sort active positive HS6 product totals descending; top p% share is the sum of the largest ceil(p * active_products) values divided by total trade value.",
                "source_artifacts": {
                    "top_share_comparison": source_link(PROF_P_SOURCE_FILES["prof_p_top_shares"]),
                    "lorenz_points": source_link(PROF_P_SOURCE_FILES["prof_p_lorenz"]),
                },
            },
            "top_share_comparison": clean_records(prof_p_top_shares, list(prof_p_top_shares.columns)),
            "lorenz_points": clean_records(prof_p_lorenz, list(prof_p_lorenz.columns)),
            "lorenz_summary": clean_records(
                prof_p_top_shares[prof_p_top_shares["country"].isin(["India", "China", "United States"])],
                list(prof_p_top_shares.columns),
            ),
        },
        "exercise6": {
            "median_by_variant": clean_records(exclusion_medians, list(exclusion_medians.columns)),
            "year_series": clean_records(exclusion_years, list(exclusion_years.columns)),
            "distribution": clean_records(exclusion_distribution, list(exclusion_distribution.columns)),
        },
        "exercise10": {
            "benchmark_ladder": benchmark_ladder,
            "hs2_summary": clean_records(hs2_summary, list(hs2_summary.columns)),
            "hs2_latest": clean_records(hs2_latest, list(hs2_latest.columns)),
            "active_product_summary": clean_records(active_summary, list(active_summary.columns)),
        },
        "exercise11": {
            "summary": {key: clean_scalar(value) for key, value in io_medians.items()},
            "india_latest": {
                key: clean_scalar(india_io_latest.get(key))
                for key in [
                    "year",
                    "weighted_top_sector_input_product_gini",
                    "weighted_top_sector_top_supplier_share",
                    "weighted_top_sector_source_hhi",
                    "median_top_sector_matched_requirement_share",
                    "top_export_value_share",
                    "total_exports",
                ]
            },
            "year_series": clean_records(io_years, list(io_years.columns)),
            "coefficients": ex11_regression_summary,
            "intermediate_effects": clean_records(
                intermediate_effects,
                ["effect", "coef", "std_error", "ci_low", "ci_high"],
            ),
            "hs2_linkage": hs2_linkage,
            "commodity_comparison": clean_records(
                commodity_summary_rows,
                ["result", "sample", "check", "outcome", "term", "coef", "std_error", "p_value", "nobs", "clusters", "r2_within"],
            ),
            "commodity_stats": commodity_stats_map,
        },
    }
    if three_metric:
        three_metric_for_data = dict(three_metric)
        for key in ["headline", "yearly", "rankings", "ex02", "ex03", "ex04", "ex06", "ex10", "ex11", "ex12"]:
            frame = three_metric_for_data.get(key)
            if isinstance(frame, pd.DataFrame):
                three_metric_for_data[key] = clean_records(frame, list(frame.columns))
        data["threeMetric"] = three_metric_for_data

    if not include_prof_p_page():
        data.pop("profP", None)
    if country_size:
        data["countrySize"] = country_size
    if growth_effect:
        data["growthEffect"] = growth_effect
    if future_growth:
        data["futureGrowth"] = future_growth
    if partner_stability:
        data["partnerStability"] = partner_stability
    if ex12_extensive:
        data["exercise12Extensive"] = ex12_extensive
    if ex12_ev_hs6_harmonized:
        data["exercise12EvHs6HarmonizedExpansion"] = ex12_ev_hs6_harmonized
    if ex12_ev_hs4:
        data["exercise12EvHs4Expansion"] = ex12_ev_hs4
    if cadot_hump:
        data["cadotHump"] = cadot_hump
    if contributions:
        data["contributions"] = contributions

    pages = build_page_context(data)
    return data, pages


def find_value(rows: list[dict[str, Any]], **filters: Any) -> dict[str, Any]:
    for row in rows:
        if all(row.get(key) == value for key, value in filters.items()):
            return row
    return {}


COUNTRY_SIZE_METRIC_LABELS = {
    "gini": "Gini",
    "top_1pct_share": "Top 1% share",
    "top_5pct_share": "Top 5% share",
}

COUNTRY_SIZE_MODEL_LABELS = {
    "baseline_population_year_fe": "Baseline population",
    "average_population_year_fe": "Average population",
    "primary_share_strict_year_fe": "Strict primary share",
    "primary_share_broad_year_fe": "Broad primary share",
    "primary_share_strict_two_way_cluster": "Strict primary share",
    "primary_share_broad_two_way_cluster": "Broad primary share",
    "primary_share_strict_fama_macbeth_hac3": "Strict primary share",
    "primary_share_broad_fama_macbeth_hac3": "Broad primary share",
    "gmm_lag_iv_year_fe": "Lag-IV GMM",
}

COUNTRY_SIZE_TERM_LABELS = {
    "log_population": "Log population",
    "log_gdp_per_capita": "Log GDP per capita",
}

GROWTH_EFFECT_MODEL_LABELS = {
    "main_lagged_export_growth": "Main lagged export growth",
    "balanced_common_horizon_sample": "Balanced/common support",
    "broad_available_horizon_sample": "Broad available sample",
    "two_way_country_year_cluster": "Two-way clustered SE",
    "contemporaneous_export_growth": "Contemporaneous export growth",
    "future_export_growth_placebo": "Future export-growth placebo",
    "region_year_fe": "Region-year FE",
    "growth_by_lagged_export_level_tercile": "Export-level tercile slopes",
    "exploratory_export_level_threshold_scan": "Threshold scan",
}

FUTURE_GROWTH_MODEL_LABELS = {
    "continuous_country_year_fe": "Country and year FE",
    "bucket_country_year_fe": "Bucket FE model",
    "paired_product_partner": "Product + partner + interaction",
    "two_way_country_year_cluster": "Two-way clustered SE",
    "oil_excluded_growth": "Oil-excluded export growth",
    "lagged_growth_control": "Lagged export-growth control",
    "region_year_fe": "Region-year FE",
    "base_size_bin_fe": "Base-size-bin FE",
    "drop_bottom_10pct_base": "Drop bottom 10% base",
    "drop_bottom_25pct_base": "Drop bottom 25% base",
    "alternative_outcome_dollar_change": "Dollar-change outcome",
    "alternative_outcome_asinh_change": "Asinh-change outcome",
    "placebo_prior_growth": "Prior-growth placebo",
    "confounding_drop_top_oil_quartile": "Drop top oil-share quartile",
    "confounding_income_group_year_fe": "Income-group-year FE",
    "confounding_primary_share_broad_control": "Broad primary-share control",
    "mechanism_product_discovery": "Product-discovery channel",
    "mechanism_destination_diversification": "Destination-diversification channel",
    "mechanism_relationship_entry": "Product-partner entry channel",
    "mechanism_intensive_margin": "Continuing-cell growth channel",
    "mechanism_strict_new_product": "Strict-new-product channel",
    "mechanism_low_base_product_growth": "Low-base product channel",
    "mechanism_least_traded_product_growth": "Least-traded product channel",
    "mechanism_product_active_count": "Product active-count growth",
    "mechanism_partner_active_count": "Partner active-count growth",
}

FUTURE_GROWTH_DIMENSION_LABELS = {
    "product": "Product",
    "partner": "Partner",
    "product_partner_cell": "Product-partner cell",
    "product_partner_pair": "Product and partner",
    "product_partner_bucket": "Product/partner bucket",
}

FUTURE_GROWTH_TERM_LABELS = {
    "product_gini": "Product Gini",
    "partner_gini": "Partner Gini",
    "product_partner_cell_gini": "Product-partner cell Gini",
    "product_exposure": "Product exposure",
    "partner_exposure": "Partner exposure",
    "product_x_partner": "Product x partner",
    "bucket_high_product_high_partner": "High product, high partner",
    "bucket_high_product_low_partner": "High product, low partner",
    "bucket_low_product_high_partner": "Low product, high partner",
    "prior_export_growth_control": "Lagged export growth",
    "log_initial_exports_constant_2015_usd": "Log initial exports",
    "oil_export_share": "Oil export share",
    "log_gdp_constant_2015_usd": "Log real GDP",
    "log_population": "Log population",
    "log_gni_per_capita_constant_2015_usd": "Log real GNI per capita",
    "primary_export_share_broad": "Broad primary export share",
    "log_product_active_count": "Log active products",
    "log_partner_active_count": "Log active partners",
}


def country_size_measure_label(row: dict[str, Any]) -> str:
    dimension = str(row.get("dimension") or "").title()
    metric = COUNTRY_SIZE_METRIC_LABELS.get(str(row.get("metric")), str(row.get("metric") or ""))
    return f"{row.get('flow')} {dimension} {metric}"


def country_size_rows(rows: list[dict[str, Any]], term: str = "log_population") -> list[dict[str, Any]]:
    out = []
    for row in rows:
        if row.get("term") != term:
            continue
        display = dict(row)
        display["measure"] = country_size_measure_label(row)
        display["model"] = COUNTRY_SIZE_MODEL_LABELS.get(str(row.get("model_label")), str(row.get("model_label") or ""))
        out.append(display)
    return out


def country_size_gmm_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        if row.get("term") not in COUNTRY_SIZE_TERM_LABELS:
            continue
        display = dict(row)
        display["measure"] = country_size_measure_label(row)
        display["term_label"] = COUNTRY_SIZE_TERM_LABELS.get(str(row.get("term")), str(row.get("term") or ""))
        display["model"] = COUNTRY_SIZE_MODEL_LABELS.get(str(row.get("model_label")), str(row.get("model_label") or ""))
        out.append(display)
    return out


def country_size_gmm_first_stage_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        display = dict(row)
        display["measure"] = country_size_measure_label(row)
        display["term_label"] = COUNTRY_SIZE_TERM_LABELS.get(str(row.get("endogenous_term")), str(row.get("endogenous_term") or ""))
        out.append(display)
    return out


WORLD_LARGE_PRODUCT_OUTCOME_LABELS = {
    "world_share_exposure": "Headline: exposure to globally large products",
    "spearman_product_alignment": "Diagnostic: within-country product-rank alignment",
    "top_1pct_world_product_export_share": "Export share in top 1% world products",
    "top_5pct_world_product_export_share": "Export share in top 5% world products",
    "top_10pct_world_product_export_share": "Export share in top 10% world products",
    "top_20pct_world_product_export_share": "Export share in top 20% world products",
}


def world_large_outcome_label(row: dict[str, Any]) -> str:
    outcome = str(row.get("outcome") or "")
    return WORLD_LARGE_PRODUCT_OUTCOME_LABELS.get(outcome, str(row.get("outcome_label") or outcome))


def world_large_spearman_rows(rows: list[dict[str, Any]], size_variable: str = "log_gdp_current_usd") -> list[dict[str, Any]]:
    order = {
        "world_share_exposure": 0,
        "spearman_product_alignment": 1,
        "top_1pct_world_product_export_share": 2,
        "top_5pct_world_product_export_share": 3,
        "top_10pct_world_product_export_share": 4,
        "top_20pct_world_product_export_share": 5,
    }
    out = []
    for row in rows:
        if row.get("size_variable") != size_variable:
            continue
        display = dict(row)
        display["measure"] = world_large_outcome_label(row)
        display["_sort"] = order.get(str(row.get("outcome") or ""), 99)
        out.append(display)
    return sorted(out, key=lambda item: item["_sort"])


def world_large_model_rows(rows: list[dict[str, Any]], outcome: str = "world_share_exposure") -> list[dict[str, Any]]:
    model_labels = {
        "main_gdp_year_fe": "Main GDP + year FE",
        "conditional_gdp_gdppc_year_fe": "Conditional GDP + GDP pc + year FE",
        "population_robustness_year_fe": "Population robustness + year FE",
    }
    term_labels = {
        "log_gdp_current_usd": "Log GDP, current USD",
        "log_gdp_per_capita": "Log GDP per capita",
        "log_population": "Log population",
    }
    out = []
    for row in rows:
        if row.get("outcome") != outcome:
            continue
        display = dict(row)
        display["model"] = model_labels.get(str(row.get("model_label") or ""), str(row.get("model_label") or ""))
        display["term_label"] = term_labels.get(str(row.get("term") or ""), str(row.get("term") or ""))
        out.append(display)
    return out


def short_population(value: Any) -> str:
    if value is None or not math.isfinite(float(value)):
        return "n/a"
    value = float(value)
    if abs(value) >= 1e9:
        return f"{value / 1e9:.2f}B"
    if abs(value) >= 1e6:
        return f"{value / 1e6:.1f}M"
    if abs(value) >= 1e3:
        return f"{value / 1e3:.0f}K"
    return f"{value:.0f}"


def signed_dec(value: Any, digits: int = 3) -> str:
    if value is None or not math.isfinite(float(value)):
        return "n/a"
    value = float(value)
    if abs(value) < 0.5 * 10 ** (-digits):
        value = 0.0
    return f"{value:+.{digits}f}"


def country_size_us_counterfactual_card(rows: list[dict[str, Any]]) -> str:
    gini_rows = [row for row in rows if row.get("metric") == "gini"]
    if not gini_rows:
        return """
        <aside class="size-counterfactual-card">
          <h3>US-to-smaller-country result</h3>
          <p>No US population counterfactual table is available.</p>
        </aside>
        """

    target_keys = sorted(
        {(int(row.get("target_order") or 0), str(row.get("target_id") or "")) for row in gini_rows}
    )
    outcomes = [
        ("Exports", "product", "Export product"),
        ("Exports", "partner", "Export partner"),
        ("Imports", "product", "Import product"),
        ("Imports", "partner", "Import partner"),
    ]
    by_target_outcome = {
        (str(row.get("target_id")), str(row.get("flow")), str(row.get("dimension"))): row for row in gini_rows
    }
    first = gini_rows[0]
    us_year = first.get("us_year")
    us_year_label = "" if us_year is None else f", {int(us_year)}"
    body = []
    for _order, target_id in target_keys:
        target_rows = [row for row in gini_rows if str(row.get("target_id")) == target_id]
        if not target_rows:
            continue
        target = target_rows[0]
        target_label = escape(str(target.get("target_label") or "Target"))
        target_country = escape(str(target.get("target_country") or ""))
        target_year = target.get("target_year")
        target_year_label = "" if target_year is None else f", {int(target_year)}"
        target_pop = short_population(target.get("target_population"))
        cells = [
            f"""
            <td>
              <strong>{target_label}</strong>
              <span>{target_country} ({target_pop}{target_year_label})</span>
            </td>
            """
        ]
        for flow, dimension, _label in outcomes:
            outcome_row = by_target_outcome.get((target_id, flow, dimension), {})
            value = outcome_row.get("predicted_gini_change")
            sd_share = outcome_row.get("predicted_gini_change_sd_share")
            cells.append(f"<td><strong>{signed_dec(value)}</strong><span>{pct(sd_share, 0)} SD</span></td>")
        body.append("<tr>" + "".join(cells) + "</tr>")

    headers = "".join(f"<th>{escape(label)}</th>" for _flow, _dimension, label in outcomes)
    return f"""
    <aside class="size-counterfactual-card">
      <h3>US-to-smaller-country result</h3>
      <p>Model-implied change in Gini if US population ({short_population(first.get("us_population"))}{us_year_label}) is replaced with each target size, holding the GDP-per-capita control and year fixed effect fixed.</p>
      <div class="counterfactual-table-wrap">
        <table class="counterfactual-table">
          <thead><tr><th>Target size</th>{headers}</tr></thead>
          <tbody>{"".join(body)}</tbody>
        </table>
      </div>
      <p class="counterfactual-note">Positive values mean predicted Gini is higher than at the US population. The SD line is (predicted Gini change / observed standard deviation of that Gini outcome in the rd2 main-model sample) x 100. Percentile rows use the nearest rd2 country by latest available population.</p>
    </aside>
    """


def _legacy_export_growth_effect_measure_label_unused(row: dict[str, Any]) -> str:
    dimension = str(row.get("dimension") or "").title()
    metric = COUNTRY_SIZE_METRIC_LABELS.get(str(row.get("metric")), str(row.get("metric") or ""))
    return f"{row.get('flow')} {dimension} {metric}"


def _legacy_export_growth_effect_primary_term_unused(row: dict[str, Any]) -> str:
    model_label = str(row.get("model_label") or "")
    if model_label == "contemporaneous_export_growth":
        return "contemporaneous_export_growth"
    if model_label == "future_export_growth_placebo":
        return "future_export_growth"
    return "prior_export_growth"


def growth_effect_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        if row.get("term") != growth_effect_primary_term(row):
            continue
        display = dict(row)
        display["measure"] = growth_effect_measure_label(row)
        display["model"] = GROWTH_EFFECT_MODEL_LABELS.get(str(row.get("model_label")), str(row.get("model_label") or ""))
        horizon = row.get("horizon")
        display["horizon_label"] = f"{int(horizon)}y" if isinstance(horizon, (int, float)) and math.isfinite(float(horizon)) else str(horizon or "")
        out.append(display)
    return out


def growth_effect_robustness_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in growth_effect_rows(rows):
        out.append(row)
    return out


def _legacy_export_growth_effect_bin_rows_unused(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        display = dict(row)
        display["measure"] = growth_effect_measure_label(row)
        display["bin_or_threshold"] = row.get("export_level_bin") or row.get("threshold_percentile") or row.get("label") or ""
        out.append(display)
    return out


def _legacy_export_growth_effect_measure_label_unused_2(row: dict[str, Any]) -> str:
    dimension = str(row.get("dimension") or "").title()
    metric = COUNTRY_SIZE_METRIC_LABELS.get(str(row.get("metric")), str(row.get("metric") or ""))
    return f"{row.get('flow')} {dimension} {metric}"


def _legacy_export_growth_effect_primary_term_unused_2(row: dict[str, Any]) -> str:
    model_label = str(row.get("model_label") or "")
    if model_label == "contemporaneous_export_growth":
        return "contemporaneous_export_growth"
    if model_label == "future_export_growth_placebo":
        return "future_export_growth"
    return "prior_export_growth"


def _legacy_export_growth_effect_bin_rows_unused_2(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        display = dict(row)
        display["measure"] = growth_effect_measure_label(row)
        display["bin_or_threshold"] = row.get("export_level_bin") or row.get("threshold_percentile") or row.get("label") or ""
        out.append(display)
    return out


def growth_effect_measure_label(row: dict[str, Any]) -> str:
    dimension = str(row.get("dimension") or "").title()
    metric = COUNTRY_SIZE_METRIC_LABELS.get(str(row.get("metric")), str(row.get("metric") or ""))
    return f"{row.get('flow')} {dimension} {metric}"


def growth_effect_primary_term(row: dict[str, Any]) -> str:
    model_label = str(row.get("model_label") or "")
    if model_label == "contemporaneous_export_growth":
        return "contemporaneous_export_growth"
    if model_label == "future_export_growth_placebo":
        return "future_export_growth"
    return "prior_export_growth"


def growth_effect_bin_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        display = dict(row)
        display["measure"] = growth_effect_measure_label(row)
        display["bin_or_threshold"] = row.get("export_level_bin") or row.get("threshold_percentile") or row.get("label") or ""
        horizon = row.get("horizon")
        display["horizon_label"] = f"{int(horizon)}y" if isinstance(horizon, (int, float)) and math.isfinite(float(horizon)) else str(horizon or "")
        out.append(display)
    return out


def future_growth_measure_label(row: dict[str, Any]) -> str:
    flow = str(row.get("flow") or "")
    dimension = FUTURE_GROWTH_DIMENSION_LABELS.get(str(row.get("dimension")), str(row.get("dimension") or ""))
    metric = COUNTRY_SIZE_METRIC_LABELS.get(str(row.get("metric")), str(row.get("metric") or ""))
    return f"{flow} {dimension} {metric}".strip()


def future_growth_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        display = dict(row)
        display["measure"] = future_growth_measure_label(row)
        display["model"] = FUTURE_GROWTH_MODEL_LABELS.get(str(row.get("model_label")), str(row.get("model_label") or ""))
        display["term_label"] = FUTURE_GROWTH_TERM_LABELS.get(str(row.get("term")), str(row.get("term") or ""))
        out.append(display)
    return out


def future_growth_bucket_label(value: Any) -> str:
    labels = {
        "high_product_high_partner": "High product, high partner",
        "high_product_low_partner": "High product, low partner",
        "low_product_high_partner": "Low product, high partner",
        "low_product_low_partner": "Low product, low partner",
    }
    return labels.get(str(value), str(value or ""))


def future_growth_bucket_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        display = dict(row)
        display["bucket_label"] = future_growth_bucket_label(row.get("concentration_bucket"))
        out.append(display)
    return out


def records_to_frame(rows: Any) -> pd.DataFrame:
    if isinstance(rows, pd.DataFrame):
        return rows.copy()
    if isinstance(rows, list) and rows:
        return pd.DataFrame(rows)
    return pd.DataFrame()


def metric_display_value(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        val = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if not math.isfinite(val):
        return "n/a"
    return f"{val:.3f}"


def three_metric_metric_rows(frame: pd.DataFrame, metric: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    if "metric" in frame.columns:
        metric_text = frame["metric"].astype(str).str.lower()
        if metric == "theil":
            return frame[metric_text.str.contains("theil", na=False)].copy()
        return frame[metric_text.eq(metric)].copy()
    return frame.copy()


def three_metric_value_column(frame: pd.DataFrame, metric: str) -> str | None:
    candidates = {
        "gini": ["gini", "median_gini", "actual_gini", "actual_minus_sim_median_gini", "loo_contribution"],
        "theil": ["theil", "median_theil", "theil_active", "actual_theil", "actual_minus_sim_median_theil", "loo_contribution"],
        "hhi": ["hhi", "median_hhi", "actual_hhi", "actual_minus_sim_median_hhi", "weighted_mean_source_hhi", "loo_contribution"],
    }[metric]
    for col in candidates:
        if col in frame.columns:
            return col
    return None


def three_metric_cards(rows: list[dict[str, Any]], spec: dict[str, Any]) -> str:
    frame = records_to_frame(rows)
    cards = []
    for metric, label in [("gini", "Gini"), ("theil", "Theil"), ("hhi", "HHI")]:
        metric_frame = three_metric_metric_rows(frame, metric)
        value_col = three_metric_value_column(metric_frame, metric)
        value_text = "n/a"
        detail = "Metric not defined in this exercise artifact."
        if value_col and not metric_frame.empty:
            numeric = pd.to_numeric(metric_frame[value_col], errors="coerce").dropna()
            if not numeric.empty:
                value_text = metric_display_value(float(numeric.median()))
                detail = f"Median {value_col.replace('_', ' ')} across {len(metric_frame):,} rows."
        elif metric == "hhi" and "weighted_mean_source_hhi" in frame.columns:
            numeric = pd.to_numeric(frame["weighted_mean_source_hhi"], errors="coerce").dropna()
            if not numeric.empty:
                value_text = metric_display_value(float(numeric.median()))
                detail = f"Median weighted source HHI across {len(frame):,} country-years."
        cards.append(
            f"""
            <article class="stat-card">
              <span>{label}</span>
              <strong>{value_text}</strong>
              <small>{escape(THREE_METRIC_DEFINITIONS[metric])} {escape(detail)}</small>
            </article>
            """
        )
    return '<div class="stat-grid metric-result-grid">' + "".join(cards) + "</div>"


def three_metric_evidence_table(rows: list[dict[str, Any]], spec: dict[str, Any]) -> str:
    frame = records_to_frame(rows)
    if frame.empty:
        return '<p class="empty">No three-metric rows available.</p>'
    key = spec["short"]
    if key == "01":
        work = frame[frame.get("dimension", "").astype(str).eq("product")] if "dimension" in frame.columns else frame
        latest_year = pd.to_numeric(work["year"], errors="coerce").max() if "year" in work.columns else np.nan
        work = work[pd.to_numeric(work["year"], errors="coerce").eq(latest_year)].copy() if math.isfinite(float(latest_year)) else work
        rows_out = []
        for flow, group in work.groupby("flow", sort=True):
            rows_out.append(
                {
                    "flow": flow,
                    "year": int(latest_year) if math.isfinite(float(latest_year)) else "",
                    "countries": group["country"].nunique() if "country" in group.columns else len(group),
                    "median_gini": pd.to_numeric(group.get("gini"), errors="coerce").median(),
                    "median_theil": pd.to_numeric(group.get("theil"), errors="coerce").median()
                    if "theil" in group.columns
                    else pd.to_numeric(group.get("theil_active"), errors="coerce").median(),
                    "median_hhi": pd.to_numeric(group.get("hhi"), errors="coerce").median(),
                }
            )
        return table_rows(rows_out, [("flow", "Flow", "text"), ("year", "Year", "year"), ("countries", "Countries", "int"), ("median_gini", "Median Gini", "dec"), ("median_theil", "Median Theil", "dec"), ("median_hhi", "Median HHI", "dec")])
    if key in {"02", "12"}:
        table = frame.sort_values([col for col in ["metric", "flow", "horizon"] if col in frame.columns]).head(36)
        bucket_col = "concentration_bucket" if "concentration_bucket" in table.columns else "base_concentration_bucket"
        return table_rows(clean_records(table, list(table.columns)), [("metric", "Metric", "text"), ("flow", "Flow", "text"), ("horizon", "Horizon", "int"), (bucket_col, "Bucket", "text"), ("observations", "Obs.", "int"), ("countries", "Countries", "int"), ("mean_annualized_trade_growth_log", "Mean trade growth", "pct")])
    if key == "03":
        summary = frame.groupby("import_bin", as_index=False).agg(
            rows=("country", "size"),
            countries=("country", "nunique"),
            median_import_value_share=("import_value_share", "median"),
            median_gini=("gini", "median"),
            median_theil=("theil_active", "median"),
            median_hhi=("hhi", "median"),
        )
        return table_rows(clean_records(summary.sort_values("import_bin"), list(summary.columns)), [("import_bin", "Import bin", "text"), ("countries", "Countries", "int"), ("median_import_value_share", "Median import share", "pct"), ("median_gini", "Median Gini", "dec"), ("median_theil", "Median Theil", "dec"), ("median_hhi", "Median HHI", "dec")])
    if key == "04":
        latest = frame.sort_values("weighted_mean_source_hhi", ascending=False).head(20)
        return table_rows(clean_records(latest, list(latest.columns)), [("country", "Country", "text"), ("year", "Year", "year"), ("import_products", "Import products", "int"), ("weighted_mean_top_supplier_share", "Weighted top supplier share", "pct"), ("weighted_mean_source_hhi", "Weighted source HHI", "dec"), ("share_products_top_supplier_ge_75", "Products >=75%", "pct")])
    if key == "06":
        work = frame[frame["dimension"].astype(str).eq("product")].copy() if "dimension" in frame.columns else frame
        summary = work.groupby(["variant", "flow"], as_index=False).agg(
            rows=("country", "size"),
            median_trade_share_removed=("trade_share_removed", "median"),
            median_gini=("gini", "median"),
            median_theil=("theil", "median") if "theil" in work.columns else ("theil_active", "median"),
            median_hhi=("hhi", "median"),
        )
        return table_rows(clean_records(summary.sort_values(["variant", "flow"]), list(summary.columns)), [("variant", "Variant", "text"), ("flow", "Flow", "text"), ("rows", "Rows", "int"), ("median_trade_share_removed", "Median removed share", "pct"), ("median_gini", "Median Gini", "dec"), ("median_theil", "Median Theil", "dec"), ("median_hhi", "Median HHI", "dec")])
    if key == "10":
        summary = frame.groupby(["flow", "benchmark_null"], as_index=False).agg(
            rows=("country", "size"),
            median_gini_gap=("actual_minus_sim_median_gini", "median"),
            median_theil_gap=("actual_minus_sim_median_theil", "median"),
            median_hhi_gap=("actual_minus_sim_median_hhi", "median"),
        )
        return table_rows(clean_records(summary.sort_values(["flow", "benchmark_null"]), list(summary.columns)), [("flow", "Flow", "text"), ("benchmark_null", "Benchmark", "text"), ("rows", "Rows", "int"), ("median_gini_gap", "Median Gini gap", "dec"), ("median_theil_gap", "Median Theil gap", "dec"), ("median_hhi_gap", "Median HHI gap", "dec")])
    if key == "11":
        summary = frame.groupby(["metric", "flow"], as_index=False).agg(
            rows=("country", "size"),
            products=("cmd_code", "nunique"),
            median_abs_contribution=("abs_loo_contribution", "median"),
            max_abs_contribution=("abs_loo_contribution", "max"),
        )
        return table_rows(clean_records(summary.sort_values(["metric", "flow"]), list(summary.columns)), [("metric", "Metric", "text"), ("flow", "Flow", "text"), ("rows", "Rows", "int"), ("products", "HS1992 product families", "int"), ("median_abs_contribution", "Median abs. contribution", "dec"), ("max_abs_contribution", "Max abs. contribution", "dec")])
    return table_rows(clean_records(frame.head(30), list(frame.columns)), [(col, col.replace("_", " ").title(), "text") for col in frame.columns[:8]])


def exercise_figure_section(spec: dict[str, Any]) -> str:
    if not spec["figures"]:
        return '<p class="note">No separate static figure is required for this exercise page; the evidence table and downloads carry the metric results.</p>'
    figs = []
    for key in spec["figures"]:
        figs.append(
            f"""
            <figure>
              <a class="figure-link" href="assets/figures/{key}.png"><img src="assets/figures/{key}.png" alt="{escape(key.replace('_', ' '))}"></a>
              <figcaption>{escape(key.replace('_', ' ').title())}</figcaption>
            </figure>
            """
        )
    return '<div class="figure-row">' + "".join(figs) + "</div>"


def exercise_download_links(spec: dict[str, Any]) -> str:
    links = []
    for filename in spec["downloads"]:
        links.append(f'<a href="assets/downloads/{escape(filename)}">{escape(filename)}</a>')
    links.append('<a href="assets/downloads/cadot_three_metric_manifest.json">three-metric manifest</a>')
    links.append('<a href="assets/downloads/three_metric_adversarial_review.md">three-metric adversarial review</a>')
    return '<div class="download-grid compact-downloads">' + "".join(links) + "</div>"


def build_exercise_first_pages(three_metric: dict[str, Any]) -> tuple[str, dict[str, str], str]:
    cards: list[str] = []
    pages: dict[str, str] = {}
    exercise_12_metric_section = ""
    manifest = three_metric.get("manifest", {})
    sample_label = manifest.get("country_sample") or ACTIVE_SITE_SAMPLE
    reporter_count = manifest.get("selected_reporters")
    reporter_text = f"{int(reporter_count):,} reporters" if reporter_count is not None else "available reporters"
    window = manifest.get("sample_window", {})
    sample_text = (
        f"{sample_label}; {reporter_text}; {window.get('start_year', 1988)}-{window.get('end_year', 'latest')}; "
        "available-observation rows with complete-case flags where relevant"
    )
    for spec in EXERCISE_PAGE_SPECS:
        rows = three_metric.get(spec["data_key"], []) or []
        metric_section = f"""
        <section class="section" id="metric-results">
          <div class="section-heading">
            <h2>Gini / Theil / HHI Results</h2>
            <p>Source artifact: <a href="assets/downloads/{escape(spec['source'])}">{escape(spec['source'])}</a>.</p>
          </div>
          {three_metric_cards(rows, spec)}
        </section>
        """
        evidence_table = three_metric_evidence_table(rows, spec)
        body = f"""
        <section class="page-title">
          <div class="eyebrow">{escape(spec['title'].split(':')[0])}</div>
          <h1>{escape(spec['title'])}</h1>
        </section>
        <section class="section hypothesis-section">
          {hypothesis_grid([hypothesis_card("Framing question", spec['title'].split(':', 1)[-1].strip(), spec['question'], spec['supports'], spec['weakens'], spec['answer'], [("Metric data", "#metric-results"), ("Downloads", "#exercise-downloads")])])}
        </section>
        {metric_section}
        <section class="section" id="original-graphs">
          <div class="section-heading"><h2>Reference Graphs</h2><p>Static figures are retained where available; the exercise tables are the regenerated three-metric evidence.</p></div>
          {exercise_figure_section(spec)}
        </section>
        <section class="section" id="evidence-table">
          <div class="section-heading"><h2>Evidence Table</h2><p>Small table for scanning the exercise-specific rerun output.</p></div>
          {evidence_table}
        </section>
        <section class="section" id="exercise-downloads">
          <div class="section-heading"><h2>Methods And Downloads</h2><p>Sample: {escape(sample_text)}. Product-dependent calculations exclude HS6 <strong>999999</strong> before LT/HGL weighted conversion to HS1992/H0 product families; partner-only concentration follows the project partner-total convention.</p></div>
          {exercise_download_links(spec)}
        </section>
        """
        filename = f"exercise-{spec['short']}.html"
        page_key = f"exercise-{spec['short']}"
        pages[filename] = layout(spec["title"], page_key, body)
        cards.append(
            f'<a href="{filename}"><span>{escape(spec["short"])}</span><strong>{escape(spec["title"].split(":", 1)[-1].strip())}</strong><small>{escape(spec["question"])}</small></a>'
        )
        if spec["short"] == "12":
            exercise_12_metric_section = metric_section
    index_body = f"""
    <section class="page-title">
      <div class="eyebrow">Exercise-first index</div>
      <h1>Exercises</h1>
      <p>Each exercise page starts with the framing question, then the Gini/Theil/HHI rerun output, restored figures, evidence tables, and downloads.</p>
    </section>
    <section class="section link-grid">
      {"".join(cards)}
    </section>
    """
    return layout("Exercises", "exercises", index_body), pages, exercise_12_metric_section


def build_page_context(data: dict[str, Any]) -> dict[str, str]:
    ex1 = data["exercise1"]
    ex3 = data["exercise3"]
    ex4 = data["exercise4"]
    h24 = data["h24Supplier"]
    prof_p = data.get("profP")
    ex6 = data["exercise6"]
    ex10 = data["exercise10"]
    ex11 = data["exercise11"]
    country_size = data.get("countrySize", {})
    growth_effect = data.get("growthEffect", {})
    future_growth = data.get("futureGrowth", {})
    partner_stability = data.get("partnerStability", {})
    methods = data.get("methods", {})
    world_relative = data.get("worldRelative", {})
    ex12_extensive = data.get("exercise12Extensive", {})
    ex12_ev_hs6_harmonized = data.get("exercise12EvHs6HarmonizedExpansion", {})
    ex12_ev_hs4 = data.get("exercise12EvHs4Expansion", {})
    cadot_hump = data.get("cadotHump", {})
    contributions = data.get("contributions", {})
    three_metric = data.get("threeMetric", {})
    exercises_index_page = ""
    exercise_first_pages: dict[str, str] = {}
    exercise_12_metric_section = ""
    if three_metric:
        exercises_index_page, exercise_first_pages, exercise_12_metric_section = build_exercise_first_pages(three_metric)

    exp = find_value(ex1["median_by_flow"], flow="Exports")
    imp = find_value(ex1["median_by_flow"], flow="Imports")
    shape = data["metadata"]["data_checks"]["exercise_1"]
    sample_country_count = int(shape["countries"])
    sample_year_min = int(shape["year_min"])
    sample_year_max = int(shape["year_max"])
    sample_panel_label = f"{sample_country_count}-country {sample_year_min}-{sample_year_max} panel"
    exp_start = find_value(ex1["selected_year_medians"], flow="Exports", year=sample_year_min)
    exp_end = find_value(ex1["selected_year_medians"], flow="Exports", year=sample_year_max)
    imp_start = find_value(ex1["selected_year_medians"], flow="Imports", year=sample_year_min)
    imp_end = find_value(ex1["selected_year_medians"], flow="Imports", year=sample_year_max)
    baseline = find_value(ex6["median_by_variant"], variant="baseline")
    full_excl = find_value(ex6["median_by_variant"], variant="full_exclusion")
    energy = find_value(ex3["bin_summary"], import_bin="energy")
    intermediates = find_value(ex3["bin_summary"], import_bin="intermediates")
    stable_import_bin_rows = ex3.get("stable_latest_bin_summary", []) or ex3["bin_summary"]
    stable_import_bin_year = int(ex3.get("stable_latest_year") or sample_year_max)
    stable_import_bin_country_count = int(ex3.get("stable_latest_country_count") or sample_country_count)
    stable_energy = find_value(stable_import_bin_rows, import_bin="energy") or energy
    stable_intermediates = find_value(stable_import_bin_rows, import_bin="intermediates") or intermediates
    india_supplier = ex4["india_2024"]
    partner_counterfactual = ex4.get("partner_gini_counterfactual", {})
    partner_counterfactual_summary = partner_counterfactual.get("summary", {})
    partner_counterfactual_india = partner_counterfactual.get("india_latest", {})
    latest_supplier_year = int(ex4.get("latest_year")) if ex4.get("latest_year") else 2025
    latest_supplier_reporter_count = int(ex4.get("latest_reporter_count")) if ex4.get("latest_reporter_count") else 0
    h24_latest_year = int(h24.get("latest_year")) if h24.get("latest_year") else 2024
    h24_latest = find_value(h24.get("year_series", []), year=h24_latest_year)
    stable_supplier = find_value(ex4.get("year_series", []), year=stable_import_bin_year) or ex4["summary"]
    stable_h24_supplier = find_value(h24.get("year_series", []), year=stable_import_bin_year) or h24_latest
    india_supplier_year = int(ex4.get("india_latest_year")) if ex4.get("india_latest_year") else int(india_supplier.get("year", 2024))
    india_counterfactual_year = int(partner_counterfactual_india.get("year") or india_supplier_year)
    india_io = ex11["india_latest"]
    ex11_main = find_value(ex11["coefficients"], result="HS6 Product-Gini contribution")
    ex11_any = find_value(ex11["coefficients"], result="HS6 export probability")
    ex11_supplier = find_value(ex11["coefficients"], result="HS6 supplier-country HHI contribution")
    ex11_interaction = find_value(ex11["coefficients"], result="Intermediate interaction")
    ex11_non_intermediate_slope = find_value(ex11["intermediate_effects"], effect="Non-intermediate slope")
    ex11_intermediate_slope = find_value(ex11["intermediate_effects"], effect="Intermediate slope")
    ex11_hs2_value = find_value(ex11["coefficients"], result="HS2 Product-Gini contribution")
    ex11_hs2_any = find_value(ex11["coefficients"], result="HS2 export probability")
    ex11_hs2_share = find_value(ex11["coefficients"], result="HS2 export share")
    ex11_hs2_interaction = find_value(ex11["coefficients"], result="HS2 intermediate-intensity interaction")
    commodity_stats = ex11["commodity_stats"]

    world_relative_yearly_rows = world_relative.get("yearly_summary", []) or []
    world_relative_diagnostic_rows = world_relative.get("diagnostics", []) or []
    world_relative_latest_rows = world_relative.get("latest_rankings", []) or []
    world_relative_contribution_latest_small_rows = world_relative.get("contribution_latest_small_countries", []) or []
    world_relative_contribution_top_rows = world_relative.get("contribution_top_drivers", []) or []
    world_relative_contribution_validation_rows = world_relative.get("contribution_validation", []) or []
    world_relative_import_yearly_rows = world_relative.get("import_yearly_summary", []) or []
    world_relative_import_latest_rows = world_relative.get("import_latest_rankings", []) or []
    world_relative_import_diagnostic_rows = world_relative.get("import_diagnostics", []) or []
    world_relative_import_contribution_latest_small_rows = world_relative.get("import_contribution_latest_small_countries", []) or []
    world_relative_import_contribution_validation_rows = world_relative.get("import_contribution_validation", []) or []
    world_relative_latest_year = int(world_relative.get("latest_year")) if world_relative.get("latest_year") else None
    world_relative_import_latest_year = (
        int(world_relative.get("import_latest_year")) if world_relative.get("import_latest_year") else None
    )
    world_relative_latest_summary = (
        find_value(world_relative_yearly_rows, year=world_relative_latest_year) if world_relative_latest_year else {}
    )
    world_relative_import_latest_summary = (
        find_value(world_relative_import_yearly_rows, year=world_relative_import_latest_year)
        if world_relative_import_latest_year
        else {}
    )
    world_relative_first_summary = world_relative_yearly_rows[0] if world_relative_yearly_rows else {}
    world_relative_import_first_summary = world_relative_import_yearly_rows[0] if world_relative_import_yearly_rows else {}
    world_relative_methods_section = ""
    world_relative_metric_card = ""
    world_relative_summary_text = ""
    world_relative_benchmark_warning = ""
    if world_relative_yearly_rows:
        latest_export_diagnostic = (
            find_value(world_relative_diagnostic_rows, year=world_relative_latest_year)
            if world_relative_latest_year
            else {}
        )
        prior_export_diagnostic = (
            find_value(world_relative_diagnostic_rows, year=world_relative_latest_year - 1)
            if world_relative_latest_year
            else {}
        )
        latest_world_reporters = latest_export_diagnostic.get("benchmark_reporters_with_exports")
        prior_world_reporters = prior_export_diagnostic.get("benchmark_reporters_with_exports")
        if latest_world_reporters is not None and prior_world_reporters is not None:
            try:
                latest_world_reporters_int = int(latest_world_reporters)
                prior_world_reporters_int = int(prior_world_reporters)
                if latest_world_reporters_int < prior_world_reporters_int:
                    world_relative_benchmark_warning = (
                        '<p class="source-note"><strong>Coverage warning:</strong> '
                        f"{world_relative_latest_year} latest benchmark uses fewer world reporters, "
                        f"down from {prior_world_reporters_int} in {world_relative_latest_year - 1} "
                        f"to {latest_world_reporters_int} in {world_relative_latest_year}.</p>"
                    )
            except (TypeError, ValueError):
                world_relative_benchmark_warning = ""
        world_relative_metric_card = (
            f'<article class="stat-card"><span>Median World-Relative Product Gini</span>'
            f'<strong>{dec(world_relative_latest_summary.get("median_world_relative_product_gini"))}</strong>'
            f'<small>harmonized exports, balanced 2000-2024; leave-one-out world weights</small></article>'
        )
        world_relative_summary_text = (
            f" In the balanced harmonized export benchmark, median World-Relative Product Gini is "
            f"{dec(world_relative_latest_summary.get('median_world_relative_product_gini'))} in {world_relative_latest_year}; "
            f"the appendix literal world-weighted share Gini median is "
            f"{dec(world_relative_latest_summary.get('median_world_weighted_share_gini'))}."
        )
        world_relative_yearly_table = table_rows(
            world_relative_yearly_rows,
            [
                ("year", "Year", "year"),
                ("countries", "Countries", "int"),
                ("median_world_relative_product_gini", "Median World-Relative Gini", "dec"),
                ("median_world_weighted_share_gini", "Median appendix weighted-share Gini", "dec"),
                ("median_active_product_gini", "Median active Product Gini", "dec"),
                ("median_world_relative_minus_active_product_gini", "Median difference vs active", "dec"),
            ],
        )
        latest_ranking_table = table_rows(
            world_relative_latest_rows,
            [
                ("country", "Country", "text"),
                ("iso3", "ISO3", "text"),
                ("year", "Year", "year"),
                ("world_relative_product_gini", "World-Relative Gini", "dec"),
                ("world_weighted_share_gini", "Appendix weighted-share Gini", "dec"),
                ("active_product_gini", "Active Product Gini", "dec"),
                ("zero_weight_country_export_share", "Zero-weight export share", "pct"),
            ],
        )
        import_yearly_table = table_rows(
            world_relative_import_yearly_rows,
            [
                ("year", "Year", "year"),
                ("countries", "Countries", "int"),
                ("median_world_relative_import_product_gini", "Median WR import Gini", "dec"),
                ("median_world_weighted_share_gini", "Median appendix weighted-share Gini", "dec"),
                ("median_active_product_gini", "Median active import Product Gini", "dec"),
                ("median_world_relative_import_minus_active_product_gini", "Median difference vs active", "dec"),
            ],
        )
        import_latest_ranking_table = table_rows(
            world_relative_import_latest_rows,
            [
                ("country", "Country", "text"),
                ("iso3", "ISO3", "text"),
                ("year", "Year", "year"),
                ("world_relative_import_product_gini", "WR import Gini", "dec"),
                ("world_weighted_share_gini", "Appendix weighted-share Gini", "dec"),
                ("active_product_gini", "Active import Product Gini", "dec"),
                ("zero_weight_country_import_share", "Zero-weight import share", "pct"),
            ],
        )
        recent_import_diag_rows = [
            row
            for row in world_relative_import_diagnostic_rows
            if world_relative_import_latest_year is not None and int(row.get("year") or 0) >= world_relative_import_latest_year - 9
        ]
        import_diagnostics_table = table_rows(
            recent_import_diag_rows,
            [
                ("year", "Year", "year"),
                ("benchmark_reporters_with_imports", "World reporters", "int"),
                ("benchmark_products", "World HS6 products", "int"),
                ("rd2_countries_with_metric", "rd2 countries", "int"),
                ("max_zero_weight_country_import_share", "Max zero-weight import share", "pct"),
                ("total_missing_benchmark_products", "Missing benchmark products", "int"),
            ],
        )
        recent_diag_rows = [
            row
            for row in world_relative_diagnostic_rows
            if world_relative_latest_year is not None and int(row.get("year") or 0) >= world_relative_latest_year - 9
        ]
        diagnostics_table = table_rows(
            recent_diag_rows,
            [
                ("year", "Year", "year"),
                ("benchmark_reporters_with_exports", "World reporters", "int"),
                ("benchmark_products", "World HS6 products", "int"),
                ("rd2_countries_with_metric", "rd2 countries", "int"),
                ("max_zero_weight_country_export_share", "Max zero-weight export share", "pct"),
                ("total_missing_benchmark_products", "Missing benchmark products", "int"),
            ],
        )
        contribution_small_display = [dict(row) for row in world_relative_contribution_latest_small_rows]
        for row in contribution_small_display:
            row["main_positive_driver_bucket_label"] = DRIVER_BUCKET_LABELS.get(
                str(row.get("main_positive_driver_bucket")),
                str(row.get("main_positive_driver_bucket") or ""),
            )
        contribution_small_table = table_rows(
            contribution_small_display,
            [
                ("country", "Country", "text"),
                ("iso3", "ISO3", "text"),
                ("world_relative_product_gini", "World-Relative Gini", "dec"),
                ("population", "Population", "int"),
                ("main_positive_driver_bucket_label", "Main driver", "text"),
                ("overweight_niche_product_positive_share", "Niche overwt.", "pct"),
                ("missing_large_world_product_positive_share", "Missing large", "pct"),
                ("underweight_large_world_product_positive_share", "Large underwt.", "pct"),
                ("overweight_large_world_product_positive_share", "Large overwt.", "pct"),
            ],
        )
        small_country_keys = {
            (str(row.get("country")), int(row.get("year") or 0))
            for row in world_relative_contribution_latest_small_rows
        }
        contribution_top_latest_small = [
            {**row, "driver_bucket_label": DRIVER_BUCKET_LABELS.get(str(row.get("driver_bucket")), str(row.get("driver_bucket") or ""))}
            for row in world_relative_contribution_top_rows
            if (str(row.get("country")), int(row.get("year") or 0)) in small_country_keys
            and int(row.get("driver_rank") or 0) <= 2
        ]
        contribution_top_table = table_rows(
            contribution_top_latest_small,
            [
                ("country", "Country", "text"),
                ("driver_rank", "Rank", "int"),
                ("product_label", "Product", "text"),
                ("country_share", "Country export share", "pct"),
                ("leave_one_out_world_weight", "Leave-one-out world weight", "pct"),
                ("relative_intensity", "Relative intensity", "dec"),
                ("positive_loo_gini_contribution", "LOO contribution", "dec"),
                ("driver_bucket_label", "Bucket", "text"),
            ],
        )
        contribution_validation = world_relative_contribution_validation_rows[0] if world_relative_contribution_validation_rows else {}

        def median_contribution_share(column: str) -> float | None:
            values = []
            for row in world_relative_contribution_latest_small_rows:
                try:
                    value = float(row.get(column))
                except (TypeError, ValueError):
                    continue
                if math.isfinite(value):
                    values.append(value)
            return float(np.median(values)) if values else None

        contribution_small_count = len(world_relative_contribution_latest_small_rows)
        median_underweight_large = median_contribution_share("underweight_large_world_product_positive_share")
        median_overweight_large = median_contribution_share("overweight_large_world_product_positive_share")
        median_missing_large = median_contribution_share("missing_large_world_product_positive_share")
        median_overweight_niche = median_contribution_share("overweight_niche_product_positive_share")
        world_relative_methods_section = f"""
    <section class="section" id="world-relative-product-gini">
      <div class="section-heading">
        <h2>World-Relative Product Gini</h2>
        <p>This export-only measure asks whether a country's LT/HGL-weighted HS1992 product basket is uneven relative to the product composition of world trade, rather than only unequal across its own active native HS6 lines.</p>
      </div>
      <p><strong>Idea:</strong> the scatter below is why a plain product-code Gini is not enough. The x-axis is each HS section's share of distinct HS6 export products; the y-axis is the same section's share of export value. If product codes were all similarly important economic slots, the points would sit near the 45-degree line. They do not.</p>
      <div class="figure-row full-width">
        <figure><a class="figure-link" href="assets/figures/world_relative_hs_section_line_value_shares.png"><img src="assets/figures/world_relative_hs_section_line_value_shares.png" alt="HS section shares of export lines versus export value for rd2 countries in 2021"></a><figcaption>Each point is one HS section in rd2 country exports in 2021. Section 16, machinery and electrical equipment, has 14.5% of distinct HS6 export lines but 28.9% of export value; Section 11, textiles, has 14.8% of lines but only 4.0% of value. The 45-degree line shows where line share would equal value share.</figcaption></figure>
      </div>
      <p>That gap is the intuition. Counting HS6 products equally treats a small world product and a huge world product as the same-sized slot. World-Relative Product Gini instead asks whether a country is unusually tilted relative to the product composition of world trade: big world products get a big benchmark weight, and tiny product slots do not look important merely because the classification system gives them codes.</p>
      <div class="equation-card">
        <h4>Main website measure</h4>
        <div class="math-line">
          s<sub>cpt</sub> = x<sub>cpt</sub> / &Sigma;<sub>p</sub>x<sub>cpt</sub>,
          &nbsp; w<sub>-c,pt</sub> = (B<sub>pt</sub> - x<sub>cpt</sub>) / &Sigma;<sub>p</sub>(B<sub>pt</sub> - x<sub>cpt</sub>)
        </div>
        <div class="math-line">
          WorldRelativeGini<sub>ct</sub> = weighted_gini(s<sub>cpt</sub> / w<sub>-c,pt</sub>, w<sub>-c,pt</sub>)
        </div>
        <p><strong>Unit:</strong> rd2 country-year export basket across LT/HGL-weighted HS1992 products, balanced over 2000-2024. <strong>Benchmark:</strong> leave-one-out world_broad exports in the same year. <strong>Exclusion:</strong> HS6 <strong>999999</strong> is dropped before product aggregation.</p>
      </div>
      <h3 class="subsection-title">Why the Weighted Gini Is a Standard Move</h3>
      <p>The numerator inside the index, <strong>country product share divided by world product share</strong>, is the same style of relative export-intensity comparison used in revealed comparative advantage: a product matters when it is larger in a country's export basket than it is in the world basket. The weighted Gini then summarizes how uneven those relative intensities are across products.</p>
      <p>The weighting is also analogous to survey-weighted income Ginis. In a household survey, one sampled household may represent thousands of similar households, so the Gini weights that observation by the population it represents. Here, each product's leave-one-out world export share plays that role: cars, machinery, oil, and electronics get more benchmark weight than tiny product categories because they represent larger parts of the world export basket.</p>
      <div class="equation-card">
        <h4>Appendix-only weighted-share measure</h4>
        <div class="math-line">
          AppendixGini<sub>ct</sub> = weighted_gini(s<sub>cpt</sub>, w<sub>-c,pt</sub>)
        </div>
        <p>This literal weighted-share version answers a narrower question: how unequal are country export shares after giving more attention to world-important products. It is not highlighted on the website because it can remain positive even when a country exactly mirrors the world product basket.</p>
      </div>
      <p>Latest benchmark year: <strong>{world_relative_latest_year}</strong>. Median World-Relative Product Gini is <strong>{dec(world_relative_latest_summary.get("median_world_relative_product_gini"))}</strong>; median appendix weighted-share Gini is <strong>{dec(world_relative_latest_summary.get("median_world_weighted_share_gini"))}</strong>. Balanced-window starting median is <strong>{dec(world_relative_first_summary.get("median_world_relative_product_gini"))}</strong> in {int(world_relative_first_summary.get("year"))}.</p>
      {world_relative_benchmark_warning}
      <h3 class="subsection-title">Yearly Summary</h3>
      <div class="table-scroll">{world_relative_yearly_table}</div>
      <h3 class="subsection-title">Latest-Year Ranking Extremes</h3>
      <div class="table-scroll">{latest_ranking_table}</div>
      <h3 class="subsection-title">World-Relative Import Product Gini</h3>
      <p>The import counterpart uses the same rd2 balanced window and LT/HGL-weighted HS1992 products, but replaces the benchmark with leave-one-out <strong>world_broad imports</strong>. Latest import benchmark year: <strong>{world_relative_import_latest_year}</strong>. Median World-Relative Import Product Gini is <strong>{dec(world_relative_import_latest_summary.get("median_world_relative_import_product_gini"))}</strong>; balanced-window starting median is <strong>{dec(world_relative_import_first_summary.get("median_world_relative_import_product_gini"))}</strong> in {int(world_relative_import_first_summary.get("year")) if world_relative_import_first_summary else "n/a"}.</p>
      <div class="table-scroll">{import_yearly_table}</div>
      <h3 class="subsection-title">Latest-Year Import Ranking Extremes</h3>
      <div class="table-scroll">{import_latest_ranking_table}</div>
      <h3 class="subsection-title">What Drives High World-Relative Scores?</h3>
      <p>This diagnostic addresses the small-country fairness concern. A high score can come from true over-specialization in products where the country is far above the world-normal share, or from being absent from large world-trade product categories that require scale. The table below focuses on bottom-population-quartile countries in the latest year.</p>
      <p><strong>How this was tested:</strong> for each rd2 country-year, the score is rebuilt from LT/HGL-weighted HS1992 product rows and checked against the main panel; then one product is removed at a time to see which products raise the score. For the {contribution_small_count} latest-year small countries, the median positive driver share is {pct(median_underweight_large)} for underweight large world products, {pct(median_overweight_large)} for overweight large world products, {pct(median_missing_large)} for missing large world products, and {pct(median_overweight_niche)} for overweight niche products.</p>
      <p>The contribution value is leave-one-product-out: full weighted Gini minus weighted Gini after removing that product. It is useful for diagnosing drivers, but it is not a fully additive Gini decomposition.</p>
      <div class="table-scroll">{contribution_small_table}</div>
      <h3 class="subsection-title">Top Product Drivers for Latest-Year Small Countries</h3>
      <div class="table-scroll">{contribution_top_table}</div>
      <p class="source-note">Contribution validation max absolute Gini difference versus the main panel: {dec(contribution_validation.get("max_abs_world_relative_gini_diff"))}.</p>
      <h3 class="subsection-title">Recent Benchmark Diagnostics</h3>
      <div class="table-scroll">{diagnostics_table}</div>
      <h3 class="subsection-title">Recent Import Benchmark Diagnostics</h3>
      <div class="table-scroll">{import_diagnostics_table}</div>
      <p class="source-note"><a href="assets/downloads/world_relative_product_gini_all_years.csv">Download the export panel</a>. <a href="assets/downloads/world_relative_import_product_gini_all_years.csv">Download the import panel</a>. <a href="assets/downloads/world_weighted_product_gini_appendix.csv">Download export appendix measure</a>. <a href="assets/downloads/world_weighted_import_product_gini_appendix.csv">Download import appendix measure</a>. <a href="assets/downloads/world_relative_product_gini_yearly_summary.csv">Download export yearly summary</a>. <a href="assets/downloads/world_relative_import_product_gini_yearly_summary.csv">Download import yearly summary</a>. <a href="assets/downloads/world_relative_product_contribution_latest_small_countries.csv">Download export contribution small-country summary</a>. <a href="assets/downloads/world_relative_import_product_contribution_latest_small_countries.csv">Download import contribution small-country summary</a>. <a href="assets/downloads/run_manifest_world_relative_product_gini.json">Download export run manifest</a>. <a href="assets/downloads/run_manifest_world_relative_import_product_gini.json">Download import run manifest</a>.</p>
    </section>
        """

    contributions_body = ""
    if include_contributions_page():
        contribution_import_rows = contributions.get("import_wr_country_size_rows", []) or []
        contribution_import_table = table_rows(
            contribution_import_rows,
            [
                ("term_label", "Term", "text"),
                ("model_label_display", "Inference", "text"),
                ("coefficient", "Coef.", "text"),
                ("std_error", "SE", "text"),
                ("p_value", "Raw p", "text"),
                ("bh_q_value", "BH q", "text"),
                ("nobs", "Obs.", "int"),
                ("clusters", "Clusters", "int"),
                ("q_family", "q-value source", "text"),
            ],
        )
        contribution_drop_hub_rows = contributions.get("import_size_drop_hub_rows", []) or []
        contribution_drop_hub_table = table_rows(
            contribution_drop_hub_rows,
            [
                ("spec", "Robustness check", "text"),
                ("coefficient", "log population beta", "text"),
                ("std_error", "SE", "text"),
                ("p_value", "Raw p", "text"),
                ("nobs", "Obs.", "int"),
                ("clusters", "Clusters", "int"),
                ("shrink_vs_baseline", "Absolute-beta shrink vs baseline", "text"),
            ],
        )
        partner_stability_summary_rows = contributions.get("partner_gini_stability_summary", []) or []
        partner_common_trend_rows = contributions.get("partner_gini_common_trends", []) or []
        partner_stability_exports = find_value(
            partner_stability_summary_rows,
            window="main_2000_2024",
            flow="Exports",
        )
        partner_stability_imports = find_value(
            partner_stability_summary_rows,
            window="main_2000_2024",
            flow="Imports",
        )
        partner_common_exports = find_value(
            partner_common_trend_rows,
            window="main_2000_2024",
            flow="Exports",
        )
        partner_common_imports = find_value(
            partner_common_trend_rows,
            window="main_2000_2024",
            flow="Imports",
        )
        partner_stability_rows = []
        for flow, summary_row, trend_row in [
            ("Exports", partner_stability_exports, partner_common_exports),
            ("Imports", partner_stability_imports, partner_common_imports),
        ]:
            partner_stability_rows.append(
                {
                    "flow": flow,
                    "countries": summary_row.get("countries"),
                    "median_abs_slope_per_decade": summary_row.get("median_abs_slope_per_decade"),
                    "p90_abs_slope_per_decade": summary_row.get("p90_abs_slope_per_decade"),
                    "share_stable_slope_10yr_0p02": summary_row.get("share_stable_slope_10yr_0p02"),
                    "median_abs_endpoint_change": summary_row.get("median_abs_endpoint_change"),
                    "share_stable_endpoint_0p05": summary_row.get("share_stable_endpoint_0p05"),
                    "coefficient": trend_row.get("coefficient_per_decade"),
                    "p_value": trend_row.get("p_value"),
                    "nobs": trend_row.get("nobs"),
                }
            )
        partner_stability_table = table_rows(
            partner_stability_rows,
            [
                ("flow", "Flow", "text"),
                ("countries", "Countries", "int"),
                ("median_abs_slope_per_decade", "Median |slope|/decade", "dec"),
                ("p90_abs_slope_per_decade", "P90 |slope|/decade", "dec"),
                ("share_stable_slope_10yr_0p02", "Stable slopes", "pct"),
                ("median_abs_endpoint_change", "Median endpoint change", "dec"),
                ("share_stable_endpoint_0p05", "Stable endpoints", "pct"),
                ("coefficient", "Common trend/decade", "dec"),
                ("p_value", "Raw p", "dec"),
                ("nobs", "Obs.", "int"),
            ],
        )
        contributions_body = f"""
    <section class="page-title">
      <div class="eyebrow">Project contribution map</div>
      <h1>What This Project Adds</h1>
      <p>The project contribution is four connected empirical moves: document persistence of concentration in both imports and exports; show that export-product concentration is systematically lower for larger countries, matching the Hummels-Klenow extensive-margin intuition that larger countries export more products; show that a simple intermediate-input story is not enough to explain import concentration; and construct a world-relative measure that benchmarks concentration against the actual world product basket rather than an equal-weighted product universe.</p>
    </section>

    <section class="section contribution-section" id="persistent-concentration">
      <div class="section-heading">
        <h2>1. Persistence of Trade Concentration</h2>
        <div>
          <p><strong>Claim:</strong> concentration is not just a 2001 cross-section fact. In the {sample_panel_label}, median Product Ginis across HS6 products are {dec(exp.get("product_gini"))} for exports and {dec(imp.get("product_gini"))} for imports; export Product Gini moves from {dec(exp_start.get("product_gini"))} in {sample_year_min} to {dec(exp_end.get("product_gini"))} in {sample_year_max}, while import Product Gini moves from {dec(imp_start.get("product_gini"))} to {dec(imp_end.get("product_gini"))}.</p>
          <p><strong>Literature it speaks to:</strong> Panagariya-Bagaria's product concentration evidence, <a href="https://www.aeaweb.org/articles?id=10.1257/000282803321455160">Imbs and Wacziarg's diversification path</a>, <a href="https://archive-ouverte.unige.ch/unige%3A46586">Cadot, Carrere, and Strauss-Kahn's diversification/reconcentration work</a>, and export-survival/extensive-margin evidence such as <a href="https://www.researchwithrutgers.com/en/publications/the-role-of-extensive-and-intensive-margins-and-export-growth/">Besedes and Prusa</a>.</p>
          <p><strong>What is interesting:</strong> the persistence result turns the project from a replication of a one-year fact into a panel fact. The import side also keeps concentration high, so the story is not only about export specialization.</p>
        </div>
      </div>
      <div class="figure-row">
        <figure><a class="figure-link" href="assets/figures/ex1_median_concentration_over_time.png"><img src="assets/figures/ex1_median_concentration_over_time.png" alt="Median trade concentration over time"></a><figcaption>Median concentration over time for the rd2 sample.</figcaption></figure>
        <figure><a class="figure-link" href="assets/figures/ex1_import_vs_export_product_gini_over_time.png"><img src="assets/figures/ex1_import_vs_export_product_gini_over_time.png" alt="Import versus export Product Gini over time"></a><figcaption>Import and export Product Gini are both persistent, rather than collapsing after the original cross-section year.</figcaption></figure>
      </div>
    </section>

    <section class="section contribution-section" id="partner-gini-stability">
      <div class="section-heading">
        <h2>Partner-Gini Stability, In Progress; Unconfirmed</h2>
        <div>
          <p><strong>Provisional claim:</strong> active Partner Gini appears high and slow-moving for most rd2 countries over 2000-2024. The median fitted absolute 10-year change is {dec(partner_stability_exports.get("median_abs_slope_per_decade"))} for exports and {dec(partner_stability_imports.get("median_abs_slope_per_decade"))} for imports; {pct(partner_stability_exports.get("share_stable_slope_10yr_0p02"))} of export country trends and {pct(partner_stability_imports.get("share_stable_slope_10yr_0p02"))} of import country trends fall within the +/-0.02 Gini-point-per-decade practical stability margin.</p>
          <p><strong>Why it matters:</strong> if partner concentration is stable while product concentration and extensive margins move, the project can separate persistent partner exposure from product-basket diversification. That would make Partner Gini a useful baseline control or contrast in later mechanism tests, not just another concentration outcome.</p>
          <p><strong>Status:</strong> this is descriptive and not yet a confirmed contribution. The check still needs independent review against endpoint sensitivity, reporting gaps, country exceptions, and the exact partner-total convention before it should be promoted into the headline claims.</p>
        </div>
      </div>
      <div class="stat-grid">
        <article class="stat-card"><span>Export stable slopes</span><strong>{pct(partner_stability_exports.get("share_stable_slope_10yr_0p02"))}</strong><small>within +/-0.02 Gini points per decade.</small></article>
        <article class="stat-card"><span>Import stable slopes</span><strong>{pct(partner_stability_imports.get("share_stable_slope_10yr_0p02"))}</strong><small>within the same practical stability margin.</small></article>
        <article class="stat-card"><span>Export median endpoint change</span><strong>{dec(partner_stability_exports.get("median_abs_endpoint_change"))}</strong><small>absolute first-to-last Partner-Gini change.</small></article>
        <article class="stat-card"><span>Import common trend</span><strong>{dec(partner_common_imports.get("coefficient_per_decade"))}</strong><small>Gini points per decade; raw p={dec(partner_common_imports.get("p_value"))}.</small></article>
      </div>
      <div class="figure-row full-width">
        <figure><a class="figure-link" href="assets/figures/contributions_partner_gini_trend.png"><img src="assets/figures/contributions_partner_gini_trend.png" alt="Partner Gini trend across rd2 countries"></a><figcaption>Median active Partner Gini and p25-p75 bands across rd2 countries. Partner totals include HS6 999999 by partner-total convention, and partnerCode 0 is excluded upstream.</figcaption></figure>
        <figure><a class="figure-link" href="assets/figures/contributions_partner_gini_country_slope_distribution.png"><img src="assets/figures/contributions_partner_gini_country_slope_distribution.png" alt="Country-specific Partner Gini trend distribution"></a><figcaption>Country-specific fitted 10-year Partner-Gini changes for 2000-2024. Dashed lines mark the +/-0.02 practical stability margin.</figcaption></figure>
      </div>
      <div class="table-scroll">
        {partner_stability_table}
      </div>
      <p class="source-note">Source: rd2_countries partner-gini stability artifacts. Unit of observation is country-year-flow. Partner totals include HS6 999999 by partner-total convention; partnerCode 0 is excluded. The figures and table are marked in progress and unconfirmed pending adversarial review.</p>
      <div class="download-grid compact-downloads">
        <a href="assets/downloads/partner_gini_stability_summary.csv">Partner-Gini stability summary CSV</a>
        <a href="assets/downloads/partner_gini_common_trend_models.csv">Partner-Gini common trend models CSV</a>
        <a href="assets/downloads/partner_gini_country_flow_stability.csv">Country-flow stability CSV</a>
      </div>
    </section>

    <section class="section contribution-section" id="country-size-export-products">
      <div class="section-heading">
        <h2>2. Larger Countries Have Less Concentrated Export Product Baskets</h2>
        <div>
          <p><strong>Claim:</strong> export-product concentration is systematically lower for larger countries in the country-size specification. The important visual is the yearly beta plot: it asks whether the cross-country slope on log population is repeatedly negative, not just whether one pooled regression happens to be significant.</p>
          <p><strong>Literature it speaks to:</strong> <a href="https://www.aeaweb.org/articles?id=10.1257/0002828054201396">Hummels and Klenow</a> show that larger economies export more varieties and higher-quality goods; related product-composition work includes <a href="https://doi.org/10.1162/0033553041382208">Schott's specialization evidence</a> and the broader extensive-margin literature.</p>
          <p><strong>What is interesting:</strong> a Gini result is the concentration-side counterpart of the Hummels-Klenow extensive-margin result. If larger countries export more products, their export product basket should look less lopsided across products; this page shows that negative size gradient directly.</p>
        </div>
      </div>
      <div class="figure-row full-width">
        <figure><a class="figure-link" href="assets/figures/country_size_yearly_size_slopes_product.png"><img src="assets/figures/country_size_yearly_size_slopes_product.png" alt="Year-by-year log population slopes for product concentration"></a><figcaption>Year-by-year log-population beta for product concentration. This is the best figure for the country-size contribution because it shows persistence of the negative export-product slope across time.</figcaption></figure>
      </div>
    </section>

    <section class="section contribution-section" id="import-intermediate-explanation">
      <div class="section-heading">
        <h2>3. The Simple Intermediate-Input Explanation Is Not Enough</h2>
        <div>
          <p><strong>Claim:</strong> intermediates matter by scale, but they do not fully explain import product concentration. The Exercise 11 product-level test weakens the broad processing story: concentration-driving imported intermediates are not generally more export-linked than other concentration-driving imports, while supplier-country exposure remains a narrower plausible mechanism.</p>
          <p><strong>Literature it speaks to:</strong> imported-input productivity and export-capability work, including <a href="https://doi.org/10.1162/qjec.122.4.1611">Amiti and Konings</a>, <a href="https://doi.org/10.1162/qjec.2010.125.4.1727">Goldberg, Khandelwal, Pavcnik, and Topalova</a>, <a href="https://doi.org/10.1257/aer.20150443">Halpern, Koren, and Szeidl</a>, and <a href="https://www.gov.uk/research-for-development-outputs/imported-intermediate-inputs-and-export-diversification-in-low-income-countries">Benguria's imported-intermediate-input export-diversification framing</a>.</p>
          <p><strong>What is interesting:</strong> this is a mechanism discipline result. It says imported inputs can matter for production, but high import Product Gini is not automatically evidence of a beneficial intermediate-input channel. The remaining story is more specific: supplier exposure in certain input-heavy product groups.</p>
        </div>
      </div>
      <div class="figure-row">
        <figure><a class="figure-link" href="assets/figures/ex3_leave_one_out.png"><img src="assets/figures/ex3_leave_one_out.png" alt="Gini reduction when each import bin is excluded"></a><figcaption>Import-bin leave-one-out effects separate energy, intermediates, capital goods, and final consumption goods.</figcaption></figure>
        <figure><a class="figure-link" href="assets/figures/ex11_coefficients.png"><img src="assets/figures/ex11_coefficients.png" alt="Exercise 11 intermediate channel coefficients"></a><figcaption>Exercise 11 regression coefficients: the broad intermediate-channel prediction does not rescue the import concentration story.</figcaption></figure>
      </div>
    </section>

    <section class="section contribution-section" id="world-relative-benchmark">
      <div class="section-heading">
        <h2>4. World-Relative Benchmarking</h2>
        <div>
          <p><strong>Claim:</strong> the world-relative Product Gini asks whether results survive when concentration is benchmarked against the actual world product basket rather than an equal-weighted HS6 product universe. The export benchmark uses leave-one-out world_broad exports; the import counterpart uses leave-one-out world_broad imports.</p>
          <p><strong>Literature it speaks to:</strong> export-variety and product-composition work, especially Hummels-Klenow, Schott, and <a href="https://www.nber.org/papers/w11905">Hausmann, Hwang, and Rodrik's export-composition growth framing</a>. It also speaks to measurement questions in diversification work because HS6 codes are not equal-sized economic slots.</p>
          <p><strong>What is interesting:</strong> a conventional active-product Gini treats a tiny world product and a huge world product as equal product slots. The world-relative measure makes the denominator economically meaningful: being absent from or over-weighted in large world products matters more than being unusual in tiny product categories.</p>
        </div>
      </div>
      <div class="figure-row full-width">
        <figure><a class="figure-link" href="assets/figures/world_relative_hs_section_line_value_shares.png"><img src="assets/figures/world_relative_hs_section_line_value_shares.png" alt="HS section line shares versus value shares"></a><figcaption>The motivating measurement figure: HS sections can have similar counts of product lines but very different shares of trade value.</figcaption></figure>
      </div>
      <p class="note"><strong>Why import weights need not equal export weights:</strong> world imports and world exports are theoretically two sides of the same transactions, but reported data differ by flow, valuation, timing, partner coverage, re-exports, mirror-reporting gaps, and CIF versus FOB conventions. For an import-side estimand, the benchmark is therefore the reported world import basket, not a silent reuse of export weights.</p>
    </section>

    <section class="section contribution-section" id="world-relative-import-size-gradient">
      <div class="section-heading">
        <h2>5. World-Relative Import Concentration Falls With Size and Income</h2>
        <div>
          <p><strong>Claim:</strong> in the import world-relative country-size specification, bigger and richer countries have lower world-relative import product concentration, conditional on the controls and year fixed effects in that specification.</p>
          <p><strong>What is interesting:</strong> this result is stronger than the standard import Product Gini size result. Standard import concentration is not meaningfully related to population in the same key table, but the world-relative import measure is: log population is significant and negative, and log GDP per capita is also significant and negative in the full model table.</p>
          <p><strong>Reporting note:</strong> the world-relative import rows use the balanced 55-country, 2000-2024 import panel, so the country-size rows have 1,375 observations. Raw p-values and BH q-values below 0.05 are highlighted separately. The GDP-per-capita q-values were recomputed because the key-coefficient artifact did not include that control; the table states the q-value source for each row.</p>
        </div>
      </div>
      <div class="note hypothesis-note">
        <p><strong>Hypothesis, not confirmed contribution:</strong> the negative income-import concentration relationship may be a bundle of mechanisms, not one channel.</p>
        <ul>
          <li><strong>Demand diversification:</strong> higher income broadens import demand beyond essentials.</li>
          <li><strong>Production complexity:</strong> richer economies need more varied imported inputs.</li>
          <li><strong>Market size and fixed costs:</strong> richer/larger markets can support more suppliers, routes, and importers.</li>
        </ul>
      </div>
      <div class="figure-row">
        <figure><a class="figure-link" href="assets/figures/contributions_wr_import_population_partial.png"><img src="assets/figures/contributions_wr_import_population_partial.png" alt="Partial regression plot for log population and world-relative import concentration"></a><figcaption>Partial relationship for log population after removing log GDP per capita and year fixed effects. The fitted slope is the log-population coefficient.</figcaption></figure>
        <figure><a class="figure-link" href="assets/figures/contributions_wr_import_gdppc_partial.png"><img src="assets/figures/contributions_wr_import_gdppc_partial.png" alt="Partial regression plot for log GDP per capita and world-relative import concentration"></a><figcaption>Partial relationship for log GDP per capita after removing log population and year fixed effects. Read it as a same-year cross-country association, not a within-country development path.</figcaption></figure>
      </div>
      <div class="table-scroll">
        {contribution_import_table}
      </div>
      <h3 class="subsection-title">Hub and Microstate Robustness</h3>
      <p class="note"><strong>Check:</strong> drop Hong Kong, Singapore, Luxembourg, Iceland, and Guyana from the same world-relative import size-gradient regression. This asks whether the negative population slope is mainly a hub/microstate artifact. The coefficient attenuates from -0.0341 to -0.0221 but remains negative and statistically significant.</p>
      <div class="table-scroll">
        {contribution_drop_hub_table}
      </div>
      <div class="download-grid compact-downloads">
        <a href="assets/downloads/world_relative_import_exercise_robustness_models.csv">Import WR robustness models CSV</a>
        <a href="assets/downloads/world_relative_import_exercise_robustness_key_coefficients.csv">Import WR key coefficients CSV</a>
        <a href="assets/downloads/import_size_mechanism_key_coefficients.csv">Import-size mechanism key coefficients CSV</a>
        <a href="assets/downloads/import_size_mechanism_models.csv">Import-size mechanism models CSV</a>
        <a href="assets/downloads/import_size_mechanism_tests.md">Import-size mechanism memo</a>
        <a href="assets/downloads/import_size_mechanism_adversarial_review.md">Import-size mechanism review</a>
        <a href="world-gini.html#world-relative-product-gini">World-relative methods and diagnostics</a>
      </div>
    </section>
        """

    ex12_extensive_section = ""
    ex12_extensive_hypothesis = ""
    ex12_summary_rows = ex12_extensive.get("summary_preferred", []) or []
    ex12_country_weighted_rows = ex12_extensive.get("country_weighted_summary_preferred", []) or []
    ex12_latest_h5_rows = ex12_extensive.get("latest_h5", []) or []
    ex12_product_robustness_rows = ex12_extensive.get("product_robustness_summary", []) or []
    ex12_validation = ex12_extensive.get("validation", {}) or {}
    ex12_ev_main = ex12_ev_hs6_harmonized or ex12_ev_hs4
    ex12_ev_main_is_hs6 = bool(ex12_ev_hs6_harmonized)
    ex12_ev_product_noun = "LT/HGL HS1992 product" if ex12_ev_main_is_hs6 else "HS4 product"
    ex12_ev_product_noun_plural = (
        "LT/HGL HS1992 products" if ex12_ev_main_is_hs6 else "HS4 products"
    )
    ex12_ev_product_channel_label = (
        "LT/HGL HS1992 product channel" if ex12_ev_main_is_hs6 else "HS4 product channel"
    )
    ex12_ev_partner_channel_type = (
        "partner_spread_continuing_hs6_harmonized"
        if ex12_ev_main_is_hs6
        else "partner_spread_continuing_hs4"
    )
    ex12_ev_manifest_filename = (
        "run_manifest_exercise_12_ev_hs6_harmonized_expansion.json"
        if ex12_ev_main_is_hs6
        else "run_manifest_exercise_12_ev_hs4_expansion.json"
    )
    ex12_ev_download_prefix = (
        "exercise_12_ev_hs6_harmonized" if ex12_ev_main_is_hs6 else "exercise_12_ev_hs4"
    )
    ex12_ev_product_rows = ex12_ev_main.get("product_summary", []) or []
    ex12_ev_partner_rows = ex12_ev_main.get("partner_summary", []) or []
    ex12_ev_equal_rows = ex12_ev_main.get("equal_country_product_summary", []) or []
    ex12_ev_latest_rows = ex12_ev_main.get("latest_5y", []) or []
    ex12_ev_bottom_rows = ex12_ev_main.get("bottom10_summary", []) or []
    ex12_ev_combined_product_first_rows = ex12_ev_main.get("combined_product_first_summary", []) or []
    ex12_ev_combined_partner_first_rows = ex12_ev_main.get("combined_partner_first_summary", []) or []
    ex12_ev_combined_latest_rows = ex12_ev_main.get("combined_latest_5y", []) or []
    ex12_ev_validation = ex12_ev_main.get("validation", {}) or {}
    if ex12_ev_product_rows and ex12_ev_latest_rows:
        h5_ev_new_product = find_value(
            ex12_ev_product_rows,
            channel_type="product",
            horizon=5,
            channel="new_product",
        )
        h5_ev_continuing = find_value(
            ex12_ev_product_rows,
            channel_type="product",
            horizon=5,
            channel="continuing_product",
        )
        h5_ev_dying = find_value(
            ex12_ev_product_rows,
            channel_type="product",
            horizon=5,
            channel="dying_product",
        )
        h5_ev_new_partner = find_value(
            ex12_ev_partner_rows,
            channel_type=ex12_ev_partner_channel_type,
            horizon=5,
            channel="new_product_partner",
        )
        h5_combined_net_new_product = find_value(
            ex12_ev_combined_product_first_rows,
            channel_type="combined_product_first",
            horizon=5,
            channel="net_new_product",
        )
        h5_combined_existing_product_new_specific_partner = find_value(
            ex12_ev_combined_product_first_rows,
            channel_type="combined_product_first",
            horizon=5,
            channel="existing_product_to_new_product_specific_partner",
        )
        h5_combined_new_reporter_partner_new_product = find_value(
            ex12_ev_combined_partner_first_rows,
            channel_type="combined_partner_first",
            horizon=5,
            channel="new_reporter_partner_new_product",
        )
        h5_combined_new_reporter_partner_existing_product = find_value(
            ex12_ev_combined_partner_first_rows,
            channel_type="combined_partner_first",
            horizon=5,
            channel="new_reporter_partner_existing_product",
        )
        ev_combined_product_first_table = table_rows(
            [row for row in ex12_ev_combined_product_first_rows if int(row.get("horizon") or 0) == 5],
            [
                ("channel_label", "Product-first channel", "text"),
                ("countries", "Countries", "int"),
                ("country_windows", "Country-windows", "int"),
                ("pooled_positive_expansion_share", "Pooled positive-expansion share", "pct"),
                ("pooled_net_growth_share", "Net-growth share", "pct"),
                ("positive_expansion_2024_usd", "Positive expansion", "money"),
            ],
        )
        ev_combined_partner_first_table = table_rows(
            [row for row in ex12_ev_combined_partner_first_rows if int(row.get("horizon") or 0) == 5],
            [
                ("channel_label", "Partner-first channel", "text"),
                ("countries", "Countries", "int"),
                ("country_windows", "Country-windows", "int"),
                ("pooled_positive_expansion_share", "Pooled positive-expansion share", "pct"),
                ("pooled_net_growth_share", "Net-growth share", "pct"),
                ("positive_expansion_2024_usd", "Positive expansion", "money"),
            ],
        )
        ev_product_table = table_rows(
            ex12_ev_product_rows,
            [
                ("horizon", "Horizon", "int"),
                ("channel_label", ex12_ev_product_channel_label, "text"),
                ("countries", "Countries", "int"),
                ("country_windows", "Country-windows", "int"),
                ("pooled_positive_expansion_share", "Pooled positive-expansion share", "pct"),
                ("pooled_net_growth_share", "Net-growth share", "pct"),
                ("positive_expansion_2024_usd", "Positive expansion", "money"),
            ],
        )
        ev_equal_country_table = table_rows(
            ex12_ev_equal_rows,
            [
                ("horizon", "Horizon", "int"),
                ("channel_label", ex12_ev_product_channel_label, "text"),
                ("countries", "Countries", "int"),
                ("equal_country_median_positive_expansion_share", "Equal-country positive-expansion median", "pct"),
                ("equal_country_median_net_growth_share", "Equal-country net-growth median", "pct"),
                ("median_country_windows", "Median windows per country", "int"),
            ],
        )
        ev_partner_table = table_rows(
            [row for row in ex12_ev_partner_rows if int(row.get("horizon") or 0) == 5],
            [
                ("channel_label", "Continuing-product partner channel", "text"),
                ("countries", "Countries", "int"),
                ("country_windows", "Country-windows", "int"),
                ("pooled_within_positive_expansion_share", "Within continuing-product partner expansion", "pct"),
                ("pooled_within_net_growth_share", "Within continuing-product net growth", "pct"),
                ("pooled_positive_expansion_share", "Share of all product expansion", "pct"),
                ("positive_expansion_2024_usd", "Positive expansion", "money"),
            ],
        )
        ev_latest_table = table_rows(
            ex12_ev_latest_rows,
            [
                ("country", "Country", "text"),
                ("iso3", "ISO3", "text"),
                ("base_window", "Base window", "text"),
                ("future_window", "Future window", "text"),
                ("total_positive_expansion_2024_usd", "Positive expansion", "money"),
                ("new_product_positive_expansion_share", f"New {ex12_ev_product_noun_plural}", "pct"),
                ("continuing_product_positive_expansion_share", f"Continuing {ex12_ev_product_noun_plural}", "pct"),
                ("dying_product_positive_expansion_share", f"Dying {ex12_ev_product_noun_plural}", "pct"),
                ("below_threshold_residual_positive_expansion_share", "Below-threshold residual", "pct"),
            ],
        )
        ev_heterogeneity_rows = []
        for country_name, story_type, reading in [
            (
                "Guyana",
                "New-product-heavy expansion",
                f"Positive expansion is almost entirely net-new {ex12_ev_product_noun_plural}.",
            ),
            (
                "New Zealand",
                "New-product-heavy expansion",
                "New products dominate, but continuing products and new product-specific partners are visible.",
            ),
            (
                "Mauritania",
                "Mixed new-product and product-partner entry",
                "New products dominate less completely; product-specific partner entry matters more.",
            ),
            (
                "Niger",
                "Threshold-residual case",
                "Positive expansion is mostly below-threshold residual, with negative net growth.",
            ),
            (
                "Panama",
                "Threshold-residual case",
                "Positive expansion is mostly below-threshold residual, with large negative net growth.",
            ),
        ]:
            product_row = find_value(ex12_ev_latest_rows, country=country_name)
            product_first_row = find_value(
                ex12_ev_combined_latest_rows,
                country=country_name,
                channel_type="combined_product_first",
            )
            if not product_row:
                continue
            ev_heterogeneity_rows.append(
                {
                    "country": country_name,
                    "future_window": product_row.get("future_window"),
                    "story_type": story_type,
                    "total_positive_expansion_2024_usd": product_row.get("total_positive_expansion_2024_usd"),
                    "total_net_growth_2024_usd": product_row.get("total_net_growth_2024_usd"),
                    "new_product_positive_expansion_share": product_row.get("new_product_positive_expansion_share"),
                    "continuing_product_positive_expansion_share": product_row.get(
                        "continuing_product_positive_expansion_share"
                    ),
                    "below_threshold_residual_positive_expansion_share": product_row.get(
                        "below_threshold_residual_positive_expansion_share"
                    ),
                    "net_new_product_positive_expansion_share": product_first_row.get(
                        "net_new_product_positive_expansion_share"
                    ),
                    "existing_product_to_new_product_specific_partner_positive_expansion_share": product_first_row.get(
                        "existing_product_to_new_product_specific_partner_positive_expansion_share"
                    ),
                    "reading": reading,
                }
            )
        ev_heterogeneity_table = table_rows(
            ev_heterogeneity_rows,
            [
                ("country", "Country", "text"),
                ("future_window", "Future window", "text"),
                ("story_type", "Story", "text"),
                ("total_positive_expansion_2024_usd", "Positive expansion", "money"),
                ("total_net_growth_2024_usd", "Net growth", "money"),
                ("new_product_positive_expansion_share", f"New {ex12_ev_product_noun_plural}", "pct"),
                ("continuing_product_positive_expansion_share", f"Continuing {ex12_ev_product_noun_plural}", "pct"),
                ("below_threshold_residual_positive_expansion_share", "Below-threshold residual", "pct"),
                ("net_new_product_positive_expansion_share", "Product-first net-new product", "pct"),
                (
                    "existing_product_to_new_product_specific_partner_positive_expansion_share",
                    "Existing product -> new product-specific partner",
                    "pct",
                ),
                ("reading", "Reading", "text"),
            ],
        )
        ev_bottom_table = table_rows(
            [row for row in ex12_ev_bottom_rows if int(row.get("horizon") or 0) == 5],
            [
                ("product_definition_label", "Product definition", "text"),
                ("countries", "Countries", "int"),
                ("country_windows", "Country-windows", "int"),
                ("pooled_positive_expansion_share", "Pooled positive-expansion share", "pct"),
                ("pooled_net_growth_share", "Net-growth share", "pct"),
                ("median_product_count", "Median products", "int"),
            ],
        )
        ev_hs4_robustness_block = ""
        if ex12_ev_main_is_hs6 and ex12_ev_hs4.get("product_summary"):
            hs4_product_table = table_rows(
                ex12_ev_hs4.get("product_summary", []) or [],
                [
                    ("horizon", "Horizon", "int"),
                    ("channel_label", "HS4 product channel", "text"),
                    ("countries", "Countries", "int"),
                    ("country_windows", "Country-windows", "int"),
                    ("pooled_positive_expansion_share", "Pooled positive-expansion share", "pct"),
                    ("pooled_net_growth_share", "Net-growth share", "pct"),
                    ("positive_expansion_2024_usd", "Positive expansion", "money"),
                ],
            )
            hs4_combined_product_first_table = table_rows(
                [
                    row
                    for row in (ex12_ev_hs4.get("combined_product_first_summary", []) or [])
                    if int(row.get("horizon") or 0) == 5
                ],
                [
                    ("channel_label", "Product-first HS4 channel", "text"),
                    ("countries", "Countries", "int"),
                    ("country_windows", "Country-windows", "int"),
                    ("pooled_positive_expansion_share", "Pooled positive-expansion share", "pct"),
                    ("pooled_net_growth_share", "Net-growth share", "pct"),
                    ("positive_expansion_2024_usd", "Positive expansion", "money"),
                ],
            )
            ev_hs4_robustness_block = f"""
      <h3 class="subsection-title">HS4 Robustness: Coarser Product Families</h3>
      <p>HS4 is deliberately coarser than the headline LT/HGL HS1992 product identity. It is useful as a conservative check because it suppresses fine-product discovery: if a country moves from one HS6 product to a related HS6 product inside the same HS4 chapter, HS4 treats that as continuing-product growth.</p>
      <h4>Pooled HS4 Product Expansion Shares</h4>
      <div class="table-scroll">{hs4_product_table}</div>
      <h4>HS4 Product-First Combined Expansion, 5-Year Windows</h4>
      <div class="table-scroll">{hs4_combined_product_first_table}</div>
      <p class="source-note"><a href="assets/downloads/exercise_12_ev_hs4_pooled_summary.csv">Download pooled HS4 summary</a>. <a href="assets/downloads/exercise_12_ev_hs4_combined_pooled_summary.csv">Download combined HS4 summary</a>. <a href="assets/downloads/run_manifest_exercise_12_ev_hs4_expansion.json">Download HS4 run manifest</a>.</p>
            """
        old_hs6_churn_table = ""
        if ex12_summary_rows:
            old_hs6_churn_table = table_rows(
                [row for row in ex12_summary_rows if int(row.get("horizon") or 0) == 5],
                [
                    ("category_label", "Rolling LT/HGL HS1992 churn channel", "text"),
                    ("countries", "Countries", "int"),
                    ("median_gross_positive_share", "Median gross-positive share", "pct"),
                    ("median_net_growth_share", "Median net-growth share", "pct"),
                    ("median_cell_count", "Median cells", "int"),
                ],
            )
        ex12_ev_harmonization_diag = ex12_ev_validation.get("harmonization_value_diagnostics") or {}
        ex12_extensive_hypothesis = hypothesis_grid(
            [
                hypothesis_card(
                    "Exercise 12",
                    "Where export growth comes from",
                    f"Export growth may come from persistent entry into new {ex12_ev_product_noun_plural}, product-specific destination spread for continuing products, or expansion of already-present products.",
                    f"Persistent new {ex12_ev_product_noun_plural} and new product-specific partners account for meaningful shares of pooled positive export expansion.",
                    f"Almost all positive expansion comes from continuing {ex12_ev_product_noun_plural} sold through existing product-specific partners.",
                    (
                        f"The headline now uses {ex12_ev_product_noun_plural}, adjacent 2-year base and future windows, "
                        "a $50,000 constant-2024-dollar activity threshold, and pooled positive-expansion shares. "
                        f"In 5-year rd2 windows, persistent new {ex12_ev_product_noun_plural} account for {pct(h5_ev_new_product.get('pooled_positive_expansion_share'))} "
                        f"of pooled positive expansion, while continuing {ex12_ev_product_noun_plural} account for {pct(h5_ev_continuing.get('pooled_positive_expansion_share'))}. "
                        f"In the cell-level product-first view, net-new products account for {pct(h5_combined_net_new_product.get('pooled_positive_expansion_share'))} "
                        f"and continuing {ex12_ev_product_noun_plural} to new product-specific partners account for {pct(h5_combined_existing_product_new_specific_partner.get('pooled_positive_expansion_share'))}. "
                        f"In the partner-first view, new reporter partners account for "
                        f"{pct((h5_combined_new_reporter_partner_new_product.get('pooled_positive_expansion_share') or 0) + (h5_combined_new_reporter_partner_existing_product.get('pooled_positive_expansion_share') or 0))}."
                    ),
                    [
                        ("Exercise 12 table", "#exercise-12-extensive-margin"),
                        (f"EV-style {ex12_ev_product_noun_plural} CSV", f"assets/downloads/{ex12_ev_download_prefix}_pooled_summary.csv"),
                        ("Validation manifest", f"assets/downloads/{ex12_ev_manifest_filename}"),
                    ],
                )
            ]
        )
    ex12_extensive_section = f"""
    <section class="section" id="exercise-12-extensive-margin">
      <div class="section-heading">
        <h2>Exercise 12: LT/HGL HS1992 Persistent Expansion Decomposition</h2>
        <p>This rd2-only headline table now uses official LT/HGL weighted conversion to HS1992/H0 as the main product identity. It keeps the Evenett-Venables logic: adjacent two-year base and future windows, a $50,000 constant-2024-dollar activity threshold, and pooled positive-expansion shares as the main contribution measure. HS4 is retained below only as a coarser robustness check.</p>
      </div>
      <div class="equation-card">
        <h4>Headline accounting rule</h4>
        <div class="math-line">
          ExpansionShare<sub>g</sub> = &Sigma; max(&Delta;X<sub>g,c,t,h</sub>,0) / &Sigma; max(&Delta;X<sub>c,t,h</sub>,0)
        </div>
        <p><strong>Unit:</strong> reporter-country, adjacent 2-year base window, adjacent 2-year future window, {ex12_ev_product_noun}. <strong>Active product rule:</strong> at least $50,000 in constant 2024 USD in both years of the window. <strong>Net-growth shares</strong> are shown as companion accounting and can exceed 100 percent or turn negative when contractions offset expansion.</p>
      </div>
      <ul class="callout-list">
        <li>Persistent new {ex12_ev_product_noun_plural} account for <strong>{pct(h5_ev_new_product.get("pooled_positive_expansion_share"))}</strong> of pooled positive expansion in 5-year windows.</li>
        <li>Continuing {ex12_ev_product_noun_plural} account for <strong>{pct(h5_ev_continuing.get("pooled_positive_expansion_share"))}</strong>; dying or non-persistent future products account for <strong>{pct(h5_ev_dying.get("pooled_positive_expansion_share"))}</strong>.</li>
        <li>For continuing {ex12_ev_product_noun_plural}, new product-specific partners account for <strong>{pct(h5_ev_new_partner.get("pooled_within_positive_expansion_share"))}</strong> of product-partner positive expansion within continuing product families.</li>
        <li>Cell-level combined accounting: net-new products are <strong>{pct(h5_combined_net_new_product.get("pooled_positive_expansion_share"))}</strong>, continuing products to new product-specific partners are <strong>{pct(h5_combined_existing_product_new_specific_partner.get("pooled_positive_expansion_share"))}</strong>, and new reporter partners are <strong>{pct((h5_combined_new_reporter_partner_new_product.get("pooled_positive_expansion_share") or 0) + (h5_combined_new_reporter_partner_existing_product.get("pooled_positive_expansion_share") or 0))}</strong>.</li>
        <li>Validation: <strong>{int(ex12_ev_validation.get("country_count_product_decomposition") or 0)}</strong> rd2 countries, {ex12_ev_validation.get("product_level_label") or ex12_ev_product_noun_plural}, $<strong>{int(ex12_ev_validation.get("active_threshold_usd_2024") or 0):,}</strong> threshold in 2024 USD, and <strong>{int(ex12_ev_validation.get("source_hs6_999999_rows_after_filters") or 0)}</strong> HS6 999999 rows after filtering.</li>
      </ul>
      <h3 class="subsection-title">Combined Product-Partner Expansion</h3>
      <p>The next two tables use the same product-by-partner cell accounting but answer different questions. In the product-first panel, a new partner means a new <em>product-specific</em> product-by-partner relationship. In the partner-first panel, a new partner means the reporter did not persistently export to that partner at all in the base window. These are alternative partitions and should not be added together.</p>
      <h4>Product-first: product-specific partner status</h4>
      <div class="table-scroll">{ev_combined_product_first_table}</div>
      <h4>Partner-first: reporter-partner status</h4>
      <div class="table-scroll">{ev_combined_partner_first_table}</div>
      <h3 class="subsection-title">Pooled Product Expansion Shares</h3>
      <div class="table-scroll">{ev_product_table}</div>
      <h3 class="subsection-title">Equal-Country Robustness</h3>
      <div class="table-scroll">{ev_equal_country_table}</div>
      <h3 class="subsection-title">Continuing Products: Product-Specific Partner Spread</h3>
      <div class="table-scroll">{ev_partner_table}</div>
      <h3 class="subsection-title">Heterogeneity: Discovery Cases Versus Threshold Residuals</h3>
      <p>Latest-window country results are not one story. The table flags new-product-heavy expansion cases and threshold-residual cases so the pooled result is not read as one universal mechanism.</p>
      <div class="table-scroll">{ev_heterogeneity_table}</div>
      <h3 class="subsection-title">Latest 5-Year Country Decomposition</h3>
      <div class="table-scroll">{ev_latest_table}</div>
      <h3 class="subsection-title">Bottom-10 Low-Base Robustness</h3>
      <div class="table-scroll">{ev_bottom_table}</div>
      {ev_hs4_robustness_block}
      <h3 class="subsection-title">Method Caveat: Harmonization</h3>
      <p>The HS6 headline follows the harmonization concern raised by <a href="https://econpapers.repec.org/paper/usgeconwp/2022_3a12.htm">Lukaszuk and Torun (2022)</a> and uses the Harvard Growth Lab / Dataverse weighted conversion tables to map each source HS6 revision to HS1992/H0 before aggregation. In the validation file, weighted conversion coverage is <strong>{pct(ex12_ev_harmonization_diag.get("clean_nonambiguous_value_share"))}</strong>, unmatched trade value is <strong>{pct(ex12_ev_harmonization_diag.get("unmatched_value_share"))}</strong>, and the conversion value residual is <strong>{money(ex12_ev_harmonization_diag.get("conversion_value_residual"))}</strong>.</p>
      <h3 class="subsection-title">Appendix: Rolling LT/HGL HS1992 Churn Table</h3>
      <p>The older rolling product-partner-cell table is retained as transition/churn accounting. It is not the main Evenett-Venables-style headline because it uses one-year endpoints and a different cell-level question.</p>
      <div class="table-scroll">{old_hs6_churn_table}</div>
      <p class="source-note"><a href="assets/downloads/{ex12_ev_download_prefix}_pooled_summary.csv">Download pooled headline summary</a>. <a href="assets/downloads/{ex12_ev_download_prefix}_combined_pooled_summary.csv">Download combined pooled summary</a>. <a href="assets/downloads/{ex12_ev_download_prefix}_combined_country_window_decomposition.csv">Download combined country-window table</a>. <a href="assets/downloads/{ex12_ev_download_prefix}_country_window_decomposition.csv">Download full country-window table</a>. <a href="assets/downloads/{ex12_ev_download_prefix}_partner_spread_country_window.csv">Download partner-spread table</a>. <a href="assets/downloads/{ex12_ev_download_prefix}_bottom10_robustness_summary.csv">Download bottom-10 robustness</a>. <a href="assets/downloads/{ex12_ev_manifest_filename}">Download EV-style run manifest</a>.</p>
    </section>
        """
    if not ex12_extensive_section and ex12_summary_rows and ex12_latest_h5_rows:
        h5_new_product = find_value(
            ex12_summary_rows,
            identity_mode="hs6_harmonized_family",
            horizon=5,
            category="net_new_product",
        )
        h5_new_partner = find_value(
            ex12_summary_rows,
            identity_mode="hs6_harmonized_family",
            horizon=5,
            category="net_new_partner_existing_product",
        )
        h5_new_cell = find_value(
            ex12_summary_rows,
            identity_mode="hs6_harmonized_family",
            horizon=5,
            category="new_product_partner_cell_existing_product_partner",
        )
        ex12_summary_table = table_rows(
            ex12_summary_rows,
            [
                ("horizon", "Horizon", "int"),
                ("category_label", "Growth channel", "text"),
                ("countries", "Countries", "int"),
                ("median_gross_positive_share", "Median gross-positive share", "pct"),
                ("median_net_growth_share", "Median net-growth share", "pct"),
                ("median_cell_count", "Median cells", "int"),
            ],
        )
        ex12_country_weighted_table = table_rows(
            ex12_country_weighted_rows,
            [
                ("horizon", "Horizon", "int"),
                ("category_label", "Growth channel", "text"),
                ("countries", "Countries", "int"),
                ("median_country_median_gross_positive_share", "Equal-country gross-positive median", "pct"),
                ("median_country_median_net_growth_share", "Equal-country net-growth median", "pct"),
                ("median_country_year_pairs", "Median windows per country", "int"),
            ],
        )
        latest_table = table_rows(
            ex12_latest_h5_rows,
            [
                ("country", "Country", "text"),
                ("iso3", "ISO3", "text"),
                ("period", "Latest 5-year period", "text"),
                ("total_growth", "Net export growth", "money"),
                ("net_new_product_gross_positive_share", "New products", "pct"),
                ("net_new_partner_existing_product_gross_positive_share", "New partners", "pct"),
                ("new_product_partner_cell_existing_product_partner_gross_positive_share", "New existing-product-partner cells", "pct"),
                ("existing_product_partner_cell_growth_gross_positive_share", "Existing-cell growth", "pct"),
            ],
        )
        product_robustness_table = table_rows(
            [row for row in ex12_product_robustness_rows if int(row.get("horizon") or 0) == 5],
            [
                ("product_definition_label", "Product-entry definition", "text"),
                ("countries", "Countries", "int"),
                ("median_gross_positive_share", "Median gross-positive share", "pct"),
                ("median_net_growth_share", "Median net-growth share", "pct"),
                ("median_product_count", "Median products", "int"),
            ],
        )
        ex12_extensive_hypothesis = hypothesis_grid(
            [
                hypothesis_card(
                    "Exercise 12",
                    "Where export growth comes from",
                    "Export growth comes mainly from adding new products, new partners, or new product-partner cells rather than only selling more in already-active cells.",
                    "New product, new partner, or new product-partner cell shares account for a meaningful part of gross-positive export expansion.",
                    "Almost all expansion comes from already-active product-partner cells.",
                    (
                        "Supports an extensive-margin role, especially for new product-partner cells. "
                        f"In 5-year rd2 windows, median gross-positive expansion from net-new products is {pct(h5_new_product.get('median_gross_positive_share'))}, "
                        f"net-new partners for existing products is {pct(h5_new_partner.get('median_gross_positive_share'))}, "
                        f"and new cells among already-existing products and partners is {pct(h5_new_cell.get('median_gross_positive_share'))}."
                    ),
                    [
                        ("Exercise 12 table", "#exercise-12-extensive-margin"),
                        ("Country-year CSV", "assets/downloads/exercise_12_extensive_margin_country_year.csv"),
                        ("Validation manifest", "assets/downloads/run_manifest_exercise_12_extensive_margin.json"),
                    ],
                )
            ]
        )
        ex12_extensive_section = f"""
    <section class="section" id="exercise-12-extensive-margin">
      <div class="section-heading">
        <h2>Exercise 12: Where Export Growth Comes From</h2>
        <p>This rd2-only extension decomposes country export growth into new products, new partners, and new product-partner cells. The preferred product identity is LT/HGL-weighted HS1992 product; HS4 and HS2 are robustness checks.</p>
      </div>
      <div class="equation-card">
        <h4>Mutually exclusive accounting rule</h4>
        <div class="math-line">
          &Delta;X<sub>c,t,h</sub> = &Sigma;<sub>p,k</sub>(x<sub>c,p,k,t+h</sub> - x<sub>c,p,k,t</sub>)
        </div>
        <p>Future cells are assigned in this order: product absent in the base year, then partner absent among existing products, then new product-partner cell where both product and partner existed, then already-active cell growth or contraction. This avoids double-counting. HS6 <strong>999999</strong> is excluded before product-dependent aggregation.</p>
      </div>
      <ul class="callout-list">
        <li>Across country-year 5-year windows, median gross-positive expansion from net-new products is <strong>{pct(h5_new_product.get("median_gross_positive_share"))}</strong>.</li>
        <li>Median gross-positive expansion from net-new partners for existing products is <strong>{pct(h5_new_partner.get("median_gross_positive_share"))}</strong>.</li>
        <li>Median gross-positive expansion from new cells among already-existing products and partners is <strong>{pct(h5_new_cell.get("median_gross_positive_share"))}</strong>.</li>
        <li>Validation: <strong>{int(ex12_validation.get("country_count_decomposition") or 0)}</strong> rd2 countries, <strong>{int(ex12_validation.get("source_product_partner_rows_after_filters") or 0):,}</strong> product-partner source rows, and <strong>{int(ex12_validation.get("source_hs6_999999_rows_after_filters") or 0)}</strong> HS6 999999 rows after filtering.</li>
      </ul>
      <h3 class="subsection-title">Median Channel Shares</h3>
      <div class="table-scroll">{ex12_summary_table}</div>
      <h3 class="subsection-title">Equal-Country Median Channel Shares</h3>
      <div class="table-scroll">{ex12_country_weighted_table}</div>
      <h3 class="subsection-title">Latest 5-Year Country Decomposition</h3>
      <div class="table-scroll">{latest_table}</div>
      <h3 class="subsection-title">Low-Base Product Robustness</h3>
      <div class="table-scroll">{product_robustness_table}</div>
      <p class="source-note"><a href="assets/downloads/exercise_12_extensive_margin_latest.csv">Download latest country decomposition</a>. <a href="assets/downloads/exercise_12_extensive_margin_country_year.csv">Download full country-year table</a>. <a href="assets/downloads/exercise_12_extensive_margin_country_weighted_summary.csv">Download equal-country summary</a>. <a href="assets/downloads/exercise_12_extensive_margin_product_entry_robustness.csv">Download low-base robustness</a>.</p>
    </section>
        """

    cadot_hump_body = ""
    if cadot_hump and ACTIVE_SITE_SAMPLE == "cadot_broad_156":
        cadot_hump_body = build_cadot_integrated_body(cadot_hump)
        cadot_hump = {}
    if cadot_hump:
        cadot_sample_rows = cadot_hump.get("sample_diagnostics", []) or []
        cadot_hump_rows = cadot_hump.get("hump_models_preferred", []) or []
        cadot_mechanical_rows = cadot_hump.get("mechanical_models_quadratic", []) or []
        cadot_mechanism_rows = cadot_hump.get("mechanism_summary", []) or []
        cadot_scorecard_rows = cadot_hump.get("scorecard_top_reconcentration", []) or []
        cadot_old_cone_rows = cadot_hump.get("old_cone_models", []) or []
        cadot_old_summary_rows = cadot_hump.get("old_cone_summary", []) or []
        cadot_ppp_rows = cadot_hump.get("ppp_hump_summary", []) or []
        cadot_ppp_fe_rows = cadot_hump.get("ppp_country_fe_robustness", []) or []
        cadot_broad_rows = cadot_hump.get("broad_ppp_hump_summary", []) or []
        cadot_broad_attrition_rows = cadot_hump.get("broad_ppp_sample_attrition", []) or []
        cadot_broad_reestimate_rows = cadot_hump.get("broad_ppp_independent_reestimate_checks", []) or []
        cadot_latest_rows = cadot_hump.get("country_year_latest_summary", []) or []
        old_interaction = find_value(cadot_old_cone_rows, term="mismatch_x_rich_side")
        main_sample = find_value(cadot_sample_rows, diagnostic="main_current_gni_outcomes")
        current_sample = find_value(cadot_sample_rows, diagnostic="current_gni_population_oil")
        constant_sample = find_value(cadot_sample_rows, diagnostic="constant_2015_gni_population_oil")
        recon_count = None
        if cadot_mechanism_rows:
            recon_count = cadot_mechanism_rows[0].get("reconcentration_episodes")
        cadot_hump_table = table_rows(
            cadot_hump_rows,
            [
                ("term", "Term", "text"),
                ("coefficient", "Coefficient", "dec"),
                ("std_error", "SE", "dec"),
                ("p_value", "p-value", "dec"),
                ("turning_point_gni_pc_current_usd", "Implied turning point", "money"),
                ("nobs", "N", "int"),
                ("clusters", "Countries", "int"),
            ],
        )
        cadot_sample_table = table_rows(
            cadot_sample_rows,
            [
                ("diagnostic", "Sample diagnostic", "text"),
                ("required_columns", "Required controls", "text"),
                ("balanced_countries", "Balanced countries", "int"),
                ("balanced_rows", "Rows", "int"),
                ("candidate_rows_after_required_drop", "Rows after nonmissing controls", "int"),
            ],
        )
        cadot_benchmark_table = table_rows(
            [
                {
                    "row": "Cadot, Carrere, Strauss-Kahn",
                    "sample": "156 countries, 1988-2006, HS6 exports",
                    "income": "Per-capita GDP at PPP, constant 2005 international dollars",
                    "model": "Quadratic concentration-development curves; pooled OLS in the displayed benchmark",
                    "result": "Export diversification rises then reconcentrates; concentration turning point around PPP $25k-$30k",
                },
                {
                    "row": "Our original tribunal check",
                    "sample": "rd2 balanced panel, 55 countries, 2000-2024",
                    "income": "Current-dollar log GNI per capita",
                    "model": "World-Relative Product Gini on log GNI and log GNI squared, controls, year FE, country-clustered SE",
                    "result": "No clean hump: quadratic p-value 0.735; implied turning point outside support",
                },
                {
                    "row": "Our PPP re-run",
                    "sample": "Same rd2 balanced panel, same 55 countries and years",
                    "income": "World Bank constant PPP GDP per capita, NY.GDP.PCAP.PP.KD",
                    "model": "Level PPP and log PPP quadratics, controls, year FE, country-clustered SE",
                    "result": "Level PPP restores product concentration U-shapes; log PPP does not restore the export product hump",
                },
                {
                    "row": "Cadot broad 156 modern extension",
                    "sample": "156 selected reporters, 2000-2024, complete-case analytic panels with 135 countries/clusters",
                    "income": "World Bank constant PPP GDP per capita, current constant-2021 international-dollar vintage",
                    "model": "Pooled/year-FE, country+year-FE, and between-country quadratics with population and oil-share controls",
                    "result": "Import Product Gini and Theil give the cleanest broad humps; export product evidence is edge-sensitive; this is not a literal Cadot 1988-2006 replication",
                },
            ],
            [
                ("row", "Check", "text"),
                ("sample", "Sample", "text"),
                ("income", "Income variable", "text"),
                ("model", "Model", "text"),
                ("result", "Result", "text"),
            ],
        )
        cadot_ppp_rows_display = [
            {
                **row,
                "coefficient": row.get("quadratic_coefficient"),
                "p_value": row.get("quadratic_p_value"),
            }
            for row in cadot_ppp_rows
        ]
        cadot_ppp_fe_rows_display = [
            {
                **row,
                "coefficient": row.get("quadratic_coefficient"),
                "p_value": row.get("quadratic_p_value"),
            }
            for row in cadot_ppp_fe_rows
        ]
        cadot_ppp_table = table_rows(
            cadot_ppp_rows_display,
            [
                ("outcome_label", "Outcome", "text"),
                ("income_form", "Income form", "text"),
                ("coefficient", "Quadratic coef.", "dec"),
                ("p_value", "p-value", "dec"),
                ("turning_point_ppp_constant_2021_intl_usd", "Turning point", "money"),
                ("turning_point_inside_p05_p95", "Inside p05-p95", "text"),
                ("verdict", "Verdict", "text"),
                ("nobs", "N", "int"),
                ("clusters", "Countries", "int"),
            ],
        )
        cadot_ppp_fe_table = table_rows(
            cadot_ppp_fe_rows_display,
            [
                ("outcome_label", "Outcome", "text"),
                ("income_form", "Income form", "text"),
                ("specification", "Specification", "text"),
                ("coefficient", "Quadratic coef.", "dec"),
                ("p_value", "p-value", "dec"),
                ("turning_point_ppp_constant_2021_intl_usd", "Turning point", "money"),
                ("turning_point_inside_p05_p95", "Inside p05-p95", "text"),
                ("nobs", "N", "int"),
                ("clusters", "Countries", "int"),
                ("status", "Status", "text"),
            ],
        )
        estimator_labels = {
            "pooled_year_fe": "pooled/year FE",
            "country_year_fe": "country + year FE",
            "between_country": "between countries",
        }
        estimator_order = {key: i for i, key in enumerate(estimator_labels)}
        outcome_order = {
            "export_product_gini": 0,
            "export_product_theil": 1,
            "export_product_hhi": 2,
            "export_active_product_count": 3,
            "import_product_gini": 4,
            "import_product_theil": 5,
            "import_product_hhi": 6,
            "import_active_product_count": 7,
            "export_partner_gini": 8,
            "import_partner_gini": 9,
        }

        def broad_display_row(row: dict[str, Any]) -> dict[str, Any]:
            return {
                **row,
                "coefficient": row.get("quadratic_coefficient"),
                "p_value": row.get("quadratic_p_value"),
                "income_form_label": "level PPP" if row.get("income_form") == "level_ppp" else "log PPP",
                "estimator_label": estimator_labels.get(str(row.get("estimator")), str(row.get("estimator"))),
                "inside_support": "yes" if row.get("turning_point_inside_p05_p95") else "no",
                "sort_order": outcome_order.get(str(row.get("outcome_slug")), 99),
            }

        cadot_broad_level_rows = [
            broad_display_row(row)
            for row in cadot_broad_rows
            if row.get("estimator") == "pooled_year_fe" and row.get("income_form") == "level_ppp"
        ]
        cadot_broad_level_rows = sorted(cadot_broad_level_rows, key=lambda row: row["sort_order"])
        cadot_broad_key_stress_rows = [
            broad_display_row(row)
            for row in cadot_broad_rows
            if row.get("income_form") == "level_ppp"
            and row.get("outcome_slug")
            in {
                "export_product_gini",
                "export_product_theil",
                "import_product_gini",
                "import_product_theil",
                "export_partner_gini",
                "import_partner_gini",
            }
        ]
        cadot_broad_key_stress_rows = sorted(
            cadot_broad_key_stress_rows,
            key=lambda row: (row["sort_order"], estimator_order.get(str(row.get("estimator")), 99)),
        )
        cadot_broad_headline_table = table_rows(
            cadot_broad_level_rows,
            [
                ("outcome_label", "Outcome", "text"),
                ("flow", "Flow", "text"),
                ("coefficient", "Quadratic coef.", "dec"),
                ("p_value", "p-value", "dec"),
                ("turning_point_ppp_constant_2021_intl_usd", "Turning point", "money"),
                ("inside_support", "Inside p05-p95", "text"),
                ("verdict", "Verdict", "text"),
                ("nobs", "N", "int"),
                ("clusters", "Countries", "int"),
            ],
        )
        cadot_broad_stress_table = table_rows(
            cadot_broad_key_stress_rows,
            [
                ("outcome_label", "Outcome", "text"),
                ("flow", "Flow", "text"),
                ("estimator_label", "Estimator", "text"),
                ("coefficient", "Quadratic coef.", "dec"),
                ("p_value", "p-value", "dec"),
                ("turning_point_ppp_constant_2021_intl_usd", "Turning point", "money"),
                ("inside_support", "Inside p05-p95", "text"),
                ("verdict", "Verdict", "text"),
            ],
        )
        broad_attrition_display = []
        seen_flows = set()
        for row in cadot_broad_attrition_rows:
            flow = "Exports" if str(row.get("outcome_slug", "")).startswith("export_") else "Imports"
            if flow in seen_flows:
                continue
            seen_flows.add(flow)
            broad_attrition_display.append(
                {
                    **row,
                    "flow": flow,
                    "missing_controls": (
                        int(row.get("missing_ppp_rows") or 0)
                        + int(row.get("missing_population_rows") or 0)
                        + int(row.get("missing_oil_share_rows") or 0)
                    ),
                }
            )
        cadot_broad_attrition_table = table_rows(
            broad_attrition_display,
            [
                ("flow", "Flow", "text"),
                ("selected_reporters", "Selected reporters", "int"),
                ("selected_country_years", "Selected country-years", "int"),
                ("source_rows", "Source rows", "int"),
                ("analytic_rows_after_balance", "Analytic rows", "int"),
                ("analytic_countries_after_balance", "Countries", "int"),
                ("analytic_clusters_after_balance", "Clusters", "int"),
                ("missing_controls", "Missing control rows", "int"),
            ],
        )
        reestimate_groups: dict[str, list[dict[str, Any]]] = {}
        for row in cadot_broad_reestimate_rows:
            reestimate_groups.setdefault(str(row.get("check")), []).append(row)
        cadot_broad_reestimate_summary = []
        for check, rows in sorted(reestimate_groups.items()):
            coeff_diffs = [float(row.get("abs_coefficient_diff") or 0) for row in rows]
            se_diffs = [float(row.get("abs_std_error_diff") or 0) for row in rows]
            passed = all(str(row.get("passed")).lower() in {"true", "1"} or row.get("passed") is True for row in rows)
            cadot_broad_reestimate_summary.append(
                {
                    "check": check.replace("_", " "),
                    "terms": len(rows),
                    "max_coefficient_diff": max(coeff_diffs) if coeff_diffs else None,
                    "max_std_error_diff": max(se_diffs) if se_diffs else None,
                    "nobs": rows[0].get("nobs") if rows else None,
                    "clusters": rows[0].get("clusters") if rows else None,
                    "status": "passed" if passed else "failed",
                }
            )
        cadot_broad_reestimate_table = table_rows(
            cadot_broad_reestimate_summary,
            [
                ("check", "Saved-panel check", "text"),
                ("terms", "Terms", "int"),
                ("max_coefficient_diff", "Max coef. diff", "dec"),
                ("max_std_error_diff", "Max SE diff", "dec"),
                ("nobs", "N", "int"),
                ("clusters", "Countries", "int"),
                ("status", "Status", "text"),
            ],
        )
        cadot_mechanism_table = table_rows(
            [row for row in cadot_mechanism_rows if row.get("flagged_episodes") is not None],
            [
                ("mechanism", "Mechanism flag", "text"),
                ("reconcentration_episodes", "Reconcentration episodes", "int"),
                ("flagged_episodes", "Flagged", "int"),
                ("flagged_share", "Share", "pct"),
            ],
        )
        cadot_mechanical_table = table_rows(
            cadot_mechanical_rows,
            [
                ("metric", "Robustness outcome", "text"),
                ("coefficient", "Quadratic coefficient", "dec"),
                ("std_error", "SE", "dec"),
                ("p_value", "p-value", "dec"),
                ("turning_point_gni_pc_current_usd", "Implied turning point", "money"),
                ("nobs", "N", "int"),
            ],
        )
        cadot_old_cone_table = table_rows(
            cadot_old_cone_rows,
            [
                ("term", "Exit model term", "text"),
                ("coef", "Coefficient", "dec"),
                ("std_error", "SE", "dec"),
                ("p_value", "p-value", "dec"),
                ("nobs", "N", "int"),
                ("clusters", "Countries", "int"),
            ],
        )
        cadot_old_summary_table = table_rows(
            cadot_old_summary_rows,
            [
                ("rich_side_ct", "Rich side", "int"),
                ("product_channel", "HS4 status", "text"),
                ("rows", "Rows", "int"),
                ("countries", "Countries", "int"),
                ("median_mismatch", "Median mismatch", "dec"),
                ("median_prody", "Median PRODY", "dec"),
                ("median_base_log_gni", "Median country log GNI", "dec"),
            ],
        )
        cadot_scorecard_table = table_rows(
            cadot_scorecard_rows,
            [
                ("country", "Country", "text"),
                ("base_year", "Base", "year"),
                ("future_year", "Future", "year"),
                ("delta_world_relative_product_gini", "Delta World-Relative Gini", "dec"),
                ("commodity_spike", "Commodity", "bool"),
                ("section16_hs_design_sensitive", "HS design", "bool"),
                ("old_cone_pruning", "Old cone", "bool"),
                ("continuing_product_superstar_scaling", "Continuing scale", "bool"),
                ("broad_unexplained_reconcentration", "Unexplained", "bool"),
            ],
        )
        cadot_latest_table = table_rows(
            cadot_latest_rows[:20],
            [
                ("country", "Country", "text"),
                ("year", "Year", "year"),
                ("world_relative_product_gini", "World-Relative Gini", "dec"),
                ("product_gini", "Product Gini", "dec"),
                ("product_active_count", "Active products", "int"),
                ("product_top_1pct_share", "Top 1% share", "pct"),
                ("commodity_trade_share_removed", "Lumpy share removed", "pct"),
                ("section16_export_share", "Section 16 export share", "pct"),
            ],
        )
        cadot_hump_body = f"""
    <section class="page-title">
      <div class="eyebrow">Behind the hump</div>
      <h1>Cadot Hump Mechanism Tribunal</h1>
      <p>This page reports the Cadot-style hump results and mechanism diagnostics for the rd2 country panel. It separates what Cadot did, what this project did, and which results survive stricter checks.</p>
    </section>

    <section class="section" id="cadot-results-status">
      <div class="section-heading">
        <h2>What Cadot Did, What We Did</h2>
        <p>The table reports the objects being compared. Cadot's benchmark is export diversification over development using HS6 exports and PPP income; our checks use the modern rd2 panel and the project's product-concentration measures.</p>
      </div>
      <div class="table-scroll">{cadot_benchmark_table}</div>
      <div class="note">
        <p><strong>Issue:</strong> Main issue is still pooled vs country FE. Pooled/year-FE compares countries at different development stages. Country FE asks whether the same country reconcentrates as it gets richer. The PPP hump weakens there, so do not overclaim.</p>
      </div>
    </section>

    <section class="section" id="cadot-ppp-results">
      <div class="section-heading">
        <h2>PPP GDP Hump Results</h2>
        <p>All rows use rd2 countries, 2000-2024, log population, oil export share, year fixed effects, and reporter-country clustered standard errors. Product outcomes use the HS6 999999 exclusion rule; partner outcomes use the partner-total convention.</p>
      </div>
      <div class="table-scroll">{cadot_ppp_table}</div>
      <div class="figure-row">
        <figure><a class="figure-link" href="assets/figures/cadot_ppp_hump_level.png"><img src="assets/figures/cadot_ppp_hump_level.png" alt="PPP hump diagnostics using level PPP GDP per capita"></a><figcaption>Level PPP GDP per-capita diagnostics.</figcaption></figure>
        <figure><a class="figure-link" href="assets/figures/cadot_ppp_hump_log.png"><img src="assets/figures/cadot_ppp_hump_log.png" alt="PPP hump diagnostics using log PPP GDP per capita"></a><figcaption>Log PPP GDP per-capita diagnostics.</figcaption></figure>
      </div>
    </section>

    <section class="section" id="cadot-pooled-country-fe">
      <div class="section-heading">
        <h2>Pooled Versus Country-FE Robustness</h2>
        <p>The pooled/year-FE rows compare countries at different income levels within a year. The country/year-FE rows compare each country to itself over time.</p>
      </div>
      <div class="table-scroll">{cadot_ppp_fe_table}</div>
    </section>

    <section class="section" id="cadot-broad-156-modern">
      <div class="section-heading">
        <h2>Cadot Broad 156 Modern Extension, 2000-2024</h2>
        <p>This research-only extension uses 156 selected reporters with at least 19 HS final-data years in 2000-2024. It keeps the website default sample as rd2 countries and is <strong>not a literal Cadot replication</strong>: the original 1988-2006 mirror-data, HS0, 4,991-line reconstruction is still not complete.</p>
      </div>
      <div class="note">
        <p><strong>Read:</strong> Import Product Gini and Import Product Theil give the cleanest broad-sample humps. Export-product evidence is edge-sensitive in pooled results and mostly stronger between countries than within countries. Partner concentration does not provide robust Cadot-style evidence.</p>
      </div>
      <h3 class="subsection-title">Pooled Level-PPP Headline Rows</h3>
      <div class="table-scroll">{cadot_broad_headline_table}</div>
      <h3 class="subsection-title">Estimator Stress Test, Level PPP</h3>
      <div class="table-scroll">{cadot_broad_stress_table}</div>
      <h3 class="subsection-title">Sample Attrition and Re-Estimation Checks</h3>
      <p>The selected sample has 156 reporters and 3,900 possible reporter-years. Complete-case regression panels use 135 countries/clusters after outcome and control joins.</p>
      <div class="table-scroll">{cadot_broad_attrition_table}</div>
      <div class="table-scroll">{cadot_broad_reestimate_table}</div>
      <div class="figure-row">
        <figure><a class="figure-link" href="assets/figures/cadot_broad_ppp_hump_level.png"><img src="assets/figures/cadot_broad_ppp_hump_level.png" alt="Cadot broad 156 level PPP diagnostics"></a><figcaption>Broad 156 modern extension, level PPP diagnostics.</figcaption></figure>
        <figure><a class="figure-link" href="assets/figures/cadot_broad_ppp_hump_log.png"><img src="assets/figures/cadot_broad_ppp_hump_log.png" alt="Cadot broad 156 log PPP diagnostics"></a><figcaption>Broad 156 modern extension, log PPP diagnostics.</figcaption></figure>
      </div>
      <div class="download-grid compact-downloads">
        <a href="assets/downloads/cadot_broad_ppp_hump_regression_summary.csv">Broad PPP summary</a>
        <a href="assets/downloads/cadot_broad_ppp_sample_attrition.csv">Broad attrition</a>
        <a href="assets/downloads/cadot_broad_ppp_independent_reestimate_checks.csv">Independent checks</a>
        <a href="assets/downloads/cadot_broad_ppp_hump_diagnostics.json">Diagnostics JSON</a>
        <a href="assets/downloads/cadot_broad_ppp_adversarial_review.md">Broad adversarial review</a>
      </div>
    </section>

    <section class="section" id="tribunal-answer">
      <div class="section-heading">
        <h2>Answer in One Screen</h2>
        <p>The balanced world-relative panel keeps <strong>{int(main_sample.get("balanced_countries") or 0)}</strong> rd2 countries over 2000-2024. Using current-dollar GNI keeps the intended <strong>{int(current_sample.get("balanced_countries") or 0)}</strong>-country panel; constant-2015 GNI would reduce it to <strong>{int(constant_sample.get("balanced_countries") or 0)}</strong>.</p>
      </div>
      <ul class="callout-list">
        <li>The preferred World-Relative Product Gini quadratic does <strong>not</strong> deliver a clean within-sample Cadot-style turning point; the implied turning point is outside the observed income support.</li>
        <li>Among <strong>{int(recon_count or 0)}</strong> five-year reconcentration episodes, the scorecard most often flags continuing-product scaling, then commodity and HS-design sensitivity.</li>
        <li>The old-cone test is positive but should be read cautiously: mismatch x rich-side coefficient is <strong>{dec(old_interaction.get("coef"))}</strong> with p-value <strong>{dec(old_interaction.get("p_value"))}</strong>.</li>
        <li>Cadot-style reconcentration is consistent with structural exit only if the old-cone tests pass; the page reports those tests but does not treat them as causal proof.</li>
      </ul>
      <div class="figure-row">
        <figure><a class="figure-link" href="assets/figures/cadot_hump_curve.png"><img src="assets/figures/cadot_hump_curve.png" alt="World-relative Product Gini against GNI per capita"></a><figcaption>Hump curve check using current-dollar GNI per capita and World-Relative Product Gini.</figcaption></figure>
        <figure><a class="figure-link" href="assets/figures/cadot_mechanism_scorecard.png"><img src="assets/figures/cadot_mechanism_scorecard.png" alt="Mechanism scorecard shares"></a><figcaption>Share of reconcentration episodes flagged by mechanism.</figcaption></figure>
      </div>
      <div class="figure-row">
        <figure><a class="figure-link" href="assets/figures/cadot_mechanical_robustness_ladder.png"><img src="assets/figures/cadot_mechanical_robustness_ladder.png" alt="Mechanical robustness ladder"></a><figcaption>Quadratic coefficient under HS-design, Section 16, HS4/HS2, and commodity variants.</figcaption></figure>
        <figure><a class="figure-link" href="assets/figures/cadot_old_cone_exit_plot.png"><img src="assets/figures/cadot_old_cone_exit_plot.png" alt="Old-cone exit rates by mismatch"></a><figcaption>Exit rates by mismatch decile on the rich and non-rich side of the fixed threshold.</figcaption></figure>
      </div>
    </section>

    <section class="section" id="cadot-hump-spec">
      <div class="section-heading">
        <h2>Development Hump Specification</h2>
        <p>Country-year OLS with year fixed effects and country-clustered or two-way clustered SEs. The preferred table below uses current-dollar log GNI per capita, log population, and oil export share controls.</p>
      </div>
      <div class="equation-card">
        <h4>Descriptive hump model</h4>
        <div class="math-line">Concentration<sub>ct</sub> = &beta;<sub>1</sub> logGNIpc<sub>ct</sub> + &beta;<sub>2</sub> logGNIpc<sub>ct</sub><sup>2</sup> + controls<sub>ct</sub> + year FE + &epsilon;<sub>ct</sub></div>
      </div>
      <div class="table-scroll">{cadot_hump_table}</div>
      <h3 class="subsection-title">Sample Diagnostics</h3>
      <div class="table-scroll">{cadot_sample_table}</div>
    </section>

    <section class="section" id="cadot-mechanisms">
      <div class="section-heading">
        <h2>Mechanism Scorecard</h2>
        <p>Each five-year reconcentration episode can receive multiple flags. This is a triage scorecard, not a horse-race regression.</p>
      </div>
      <div class="table-scroll">{cadot_mechanism_table}</div>
      <h3 class="subsection-title">Largest Reconcentration Episodes</h3>
      <div class="table-scroll">{cadot_scorecard_table}</div>
    </section>

    <section class="section" id="cadot-mechanical">
      <div class="section-heading">
        <h2>Mechanical and Commodity Robustness</h2>
        <p>The same country-year sample is rerun using native HS6, Section 16 excluded, HS4, HS2, lumpy-commodity-excluded, and HS2-preserving residual variants.</p>
      </div>
      <div class="table-scroll">{cadot_mechanical_table}</div>
    </section>

    <section class="section" id="cadot-old-cone">
      <div class="section-heading">
        <h2>Old-Cone Exit Test</h2>
        <p>HS4 products are assigned a leave-one-out rd2 PRODY-style sophistication score. Positive mismatch means the country is richer than the product's revealed exporter-income profile. The exit model includes country, HS4-product, and base-year fixed effects and clusters by country.</p>
      </div>
      <div class="equation-card">
        <h4>Exit test</h4>
        <div class="math-line">Exit<sub>cpt+h</sub> = &alpha;<sub>c</sub> + &alpha;<sub>p</sub> + &alpha;<sub>t</sub> + &beta;<sub>1</sub> mismatch<sub>cpt</sub> + &beta;<sub>2</sub> richSide<sub>ct</sub> + &beta;<sub>3</sub> mismatch<sub>cpt</sub> x richSide<sub>ct</sub> + &epsilon;<sub>cpt</sub></div>
      </div>
      <div class="table-scroll">{cadot_old_cone_table}</div>
      <h3 class="subsection-title">Mismatch by Product Status</h3>
      <div class="table-scroll">{cadot_old_summary_table}</div>
    </section>

    <section class="section" id="cadot-latest">
      <div class="section-heading">
        <h2>Latest-Year Country Context</h2>
      </div>
      <div class="table-scroll">{cadot_latest_table}</div>
      <div class="download-grid compact-downloads">
        <a href="assets/downloads/cadot_hump_country_year_panel.csv">Country-year panel</a>
        <a href="assets/downloads/cadot_hump_models.csv">Hump models</a>
        <a href="assets/downloads/cadot_mechanism_scorecard_summary.csv">Mechanism summary</a>
        <a href="assets/downloads/cadot_reconcentration_episode_scorecard.csv">Episode scorecard</a>
        <a href="assets/downloads/cadot_old_cone_exit_models.csv">Old-cone exit models</a>
        <a href="assets/downloads/cadot_hump_sample_diagnostics.csv">Sample diagnostics</a>
        <a href="assets/downloads/ppp_hump_regression_summary.csv">PPP hump summary</a>
        <a href="assets/downloads/ppp_hump_country_fe_robustness.csv">PPP pooled/country-FE robustness</a>
        <a href="assets/downloads/cadot_broad_ppp_hump_regression_summary.csv">Broad PPP summary</a>
        <a href="assets/downloads/cadot_broad_ppp_sample_attrition.csv">Broad attrition</a>
        <a href="assets/downloads/cadot_broad_ppp_independent_reestimate_checks.csv">Broad independent checks</a>
        <a href="assets/downloads/cadot_broad_ppp_adversarial_review.md">Broad adversarial review</a>
        <a href="assets/downloads/run_manifest_cadot_hump_tribunal.json">Run manifest</a>
        <a href="assets/downloads/cadot_hump_tribunal_adversarial_review.md">Adversarial review</a>
      </div>
    </section>
        """

    literature_world_relative_year = str(world_relative_latest_year) if world_relative_latest_year else "n/a"
    literature_world_relative_gini = dec(world_relative_latest_summary.get("median_world_relative_product_gini"))
    literature_world_weighted_share_gini = dec(world_relative_latest_summary.get("median_world_weighted_share_gini"))
    common_universe_models = read_csv("country_size_common_universe_models")

    def common_universe_row(
        mechanism: str,
        dimension: str,
        outcome: str,
        outcome_label: str,
        interpretation: str,
    ) -> dict[str, Any]:
        mask = (
            common_universe_models["term"].astype(str).eq("log_population")
            & common_universe_models["flow"].astype(str).eq("Exports")
            & common_universe_models["dimension"].astype(str).eq(dimension)
            & common_universe_models["outcome"].astype(str).eq(outcome)
            & common_universe_models["source_label"].astype(str).eq("Main export item universe")
            & common_universe_models["status"].astype(str).eq("ok")
        )
        rows = common_universe_models.loc[mask]
        if rows.empty:
            raise RuntimeError(f"Missing common-universe literature row for {dimension}/{outcome}.")
        row = rows.iloc[0]
        return {
            "mechanism": mechanism,
            "dimension": "Products" if dimension == "product" else "Partners",
            "outcome": outcome_label,
            "coefficient": clean_scalar(row.get("coefficient")),
            "p_value": clean_scalar(row.get("p_value")),
            "interpretation": interpretation,
        }

    country_size_common_universe_rows = [
        common_universe_row(
            "Total concentration",
            "product",
            "total_gini",
            "Gini over all active products",
            "Larger countries remain less concentrated in products after 2001.",
        ),
        common_universe_row(
            "Total concentration",
            "partner",
            "total_gini",
            "Gini over all active partners",
            "Larger countries remain less concentrated across export partners.",
        ),
        common_universe_row(
            "Common-universe reallocation",
            "product",
            "old_positive_gini",
            "Gini among continuing pre-2002 products",
            "The product result survives without new products, pointing to reallocation among established products.",
        ),
        common_universe_row(
            "Old-universe retention",
            "partner",
            "old_universe_gini_with_exits",
            "Gini over pre-2002 partners, exits as zero",
            "The partner result is stronger when old exits are counted, pointing to retention of established partner networks.",
        ),
        common_universe_row(
            "Entry value share",
            "product",
            "new_value_share",
            "Post-2001 value share from new products",
            "New-product value shares are lower in larger countries, not higher.",
        ),
        common_universe_row(
            "Entry value share",
            "partner",
            "new_value_share",
            "Post-2001 value share from new partners",
            "New-partner value shares are lower in larger countries.",
        ),
        common_universe_row(
            "Old-item exit",
            "product",
            "old_exit_count_share",
            "Share of pre-2002 products inactive later",
            "Larger countries lose fewer old products.",
        ),
        common_universe_row(
            "Old-item exit",
            "partner",
            "old_exit_count_share",
            "Share of pre-2002 partners inactive later",
            "Larger countries lose fewer old partners.",
        ),
    ]
    literature_facts = {
        "sample_panel_label": sample_panel_label,
        "export_product_gini": dec(exp.get("product_gini")),
        "import_product_gini": dec(imp.get("product_gini")),
        "export_partner_gini": dec(exp.get("partner_gini")),
        "export_cell_gini": dec(exp.get("product_partner_cell_gini")),
        "world_relative_year": literature_world_relative_year,
        "world_relative_gini": literature_world_relative_gini,
        "world_weighted_share_gini": literature_world_weighted_share_gini,
        "ex11_product_gini_coef": dec(ex11_main.get("coef")),
        "ex11_export_probability_coef": dec(ex11_any.get("coef")),
        "ex11_supplier_hhi_coef": dec(ex11_supplier.get("coef")),
        "country_size_common_universe_rows": country_size_common_universe_rows,
    }
    literature_takeaways = build_literature_takeaways_html(literature_facts)

    source_mappings = {label: path for label, path in SOURCE_FILES.items() if not is_world_relative_artifact_name(label)}
    if include_prof_p_page():
        source_mappings.update(PROF_P_SOURCE_FILES)
    source_table = table_rows(
        [
            {"source": label, "path": source_link(path), "rows": len(pd.read_csv(path))}
            for label, path in source_mappings.items()
        ],
        [("source", "Artifact", "text"), ("path", "Local source", "text"), ("rows", "Rows", "int")],
    )
    countries_table = table_rows(
        data["countries"],
        [("country", "Country", "text"), ("iso3", "ISO3", "text"), ("reporter_code", "Reporter code", "int")],
    )
    methods_hs6_section = ""
    methods_hs6_rows = methods.get("hs6_codes_by_year", [])
    if methods_hs6_rows:
        rows_by_year: dict[int, dict[str, dict[str, Any]]] = {}
        for row in methods_hs6_rows:
            year = int(row.get("year"))
            flow = str(row.get("flow") or "")
            rows_by_year.setdefault(year, {})[flow] = row
        hs6_table_rows = []
        for year in sorted(rows_by_year):
            flow_rows = rows_by_year[year]
            any_row = flow_rows.get("Any flow", {})
            export_row = flow_rows.get("Exports", {})
            import_row = flow_rows.get("Imports", {})
            hs6_table_rows.append(
                {
                    "year": year,
                    "any_flow_codes": any_row.get("observed_hs6_codes"),
                    "export_codes": export_row.get("observed_hs6_codes"),
                    "import_codes": import_row.get("observed_hs6_codes"),
                    "reporters_with_trade": any_row.get("reporters_with_trade"),
                    "reporter_year_flow_observations": any_row.get("reporter_year_flow_observations"),
                }
            )
        first_hs6 = hs6_table_rows[0]
        last_hs6 = hs6_table_rows[-1]
        max_hs6 = max(hs6_table_rows, key=lambda row: int(row.get("any_flow_codes") or 0))
        hs6_year_table = table_rows(
            hs6_table_rows,
            [
                ("year", "Year", "year"),
                ("any_flow_codes", "Any-flow HS6 codes", "int"),
                ("export_codes", "Export HS6 codes", "int"),
                ("import_codes", "Import HS6 codes", "int"),
                ("reporters_with_trade", "Reporters", "int"),
                ("reporter_year_flow_observations", "Reporter-year-flow obs.", "int"),
            ],
        )
        methods_hs6_section = f"""
    <section class="section" id="harmonization">
      <div class="section-heading">
        <h2>Harmonization</h2>
        <p>HS6 means a six-digit Harmonized System product code. The key problem is that the same six-digit number is not a timeless product identity: the Harmonized System is revised, codes split, codes merge, and reporters adopt revisions at different times.</p>
      </div>
      <div class="interpretation-grid">
        <article class="note">
          <h3 class="subsection-title">Why We Harmonize</h3>
          <p>For a one-year product Gini, a native HS6 code is a useful label. For a time comparison, it can be misleading. If one old code is split into three new codes, a native-code panel can make a classification edit look like product entry. If several old codes merge, it can make product exit or rising concentration appear mechanically.</p>
          <p>The estimand for product-level time results is therefore concentration or growth across economically comparable product families, not across whatever native code labels happened to be active in that year.</p>
        </article>
        <article class="note">
          <h3 class="subsection-title">Where We Do Not Harmonize</h3>
          <p>Partner-only concentration does not need a product identity after products have been summed into reporter-partner totals. In that case the ranked objects are partner countries, not products, so a value-preserving product remap leaves the partner totals unchanged.</p>
          <p>For partner-only measures, HS6 <strong>999999</strong> is included in partner totals because it is still trade with a known partner. For product-dependent measures, <strong>999999</strong> is excluded before aggregation because it means Commodities not specified, not a real product.</p>
        </article>
      </div>
      <div class="equation-card">
        <h4>Product identity rule used for longitudinal product analysis</h4>
        <div class="math-line">
          x<sup>H0</sup><sub>c,p,t</sub> = &Sigma;<sub>h,r</sub> x<sub>c,h,r,t</sub> &times; w<sub>h,r &rarr; p,H0</sub>
        </div>
        <p>In plain English, product-dependent longitudinal outputs use the official Harvard Growth Lab / Dataverse weighted conversion tables motivated by <a href="https://econpapers.repec.org/paper/usgeconwp/2022_3a12.htm">Lukaszuk and Torun (2022)</a>. Each source revision-code value is multiplied by its conversion weight and then summed into a fixed HS1992/H0 product code.</p>
        <p>The source of truth is the weighted classification conversion table DOI <a href="https://doi.org/10.7910/DVN/6AADMR">10.7910/DVN/6AADMR</a>, version 2.1. Adjacent HS conversion tables are composed back to HS1992/H0, positive outgoing weights are normalized within source code, and unchanged-code identities are filled where the official adjacent files omit them.</p>
        <p>HS6 <strong>999999</strong> is excluded before conversion for product-dependent outputs. After conversion, rows are aggregated by reporter, year, flow, partner where relevant, and target HS1992 product; validation checks weight coverage, duplicate target keys, and value conservation.</p>
      </div>
      <div class="equation-card">
        <h4>Why not convert everything to the latest HS revision?</h4>
        <p>HS1992/H0 is the target because it is the earliest HS vintage in the project window, so every later revision can be converted to the same long-run product universe. Converting the full window to a later revision would require projecting early codes into product splits that did not exist yet.</p>
        <p>Coarser HS4 or HS2 groupings are useful robustness checks, but they answer a different question. They measure concentration across headings or chapters, not across HS6-level HS1992 products. Native HS6 counts are kept as a diagnostic because they show how much the raw code universe changes over time.</p>
      </div>
      <div class="equation-card">
        <h4>HS6 code-count diagnostic</h4>
        <div class="math-line">
          N<sub>t</sub> = count distinct HS6 codes h with positive trade value in year t and h &ne; 999999
        </div>
        <p><strong>Unit before aggregation:</strong> reporter-year-flow-HS6 product value. The any-flow count treats an HS6 code as present if it appears in exports, imports, or both. HS6 <strong>999999</strong> means Commodities not specified, so it is excluded before the count.</p>
        <p><strong>Reading:</strong> the any-flow rd2 universe has <strong>{int(first_hs6["any_flow_codes"]):,}</strong> observed HS6 codes in {int(first_hs6["year"])} and <strong>{int(last_hs6["any_flow_codes"]):,}</strong> in {int(last_hs6["year"])}; the maximum is <strong>{int(max_hs6["any_flow_codes"]):,}</strong> in {int(max_hs6["year"])}.</p>
      </div>
      <div class="figure-row full-width">
        <figure><a class="figure-link" href="assets/figures/methods_hs6_codes_by_year.png"><img src="assets/figures/methods_hs6_codes_by_year.png" alt="Observed HS6 product codes by year"></a><figcaption>Distinct positive HS6 product codes observed by year. Dashed lines mark nominal HS revision starts; reporting countries may adopt revisions with lags.</figcaption></figure>
      </div>
      <h3 class="subsection-title">Year Counts</h3>
      <div class="table-scroll">
        {hs6_year_table}
      </div>
      <p class="source-note"><a href="assets/downloads/methods_hs6_codes_by_year.csv">Download the HS6 code-count CSV</a>.</p>
    </section>
        """
    prof_p_max_abs_gini_diff = 0
    prof_p_max_abs_count_diff = 0
    prof_p_top_share_table = ""
    prof_p_lorenz_summary_table = ""
    if include_prof_p_page() and prof_p:
        prof_p_rows = prof_p["top_share_comparison"]
        prof_p_lorenz_summary = prof_p["lorenz_summary"]
        prof_p_max_abs_gini_diff = max(abs(float(row["product_gini_diff"])) for row in prof_p_rows)
        prof_p_max_abs_count_diff = max(abs(int(row["active_products_diff"])) for row in prof_p_rows)
        prof_p_top_share_table = sortable_table_rows(
            prof_p_rows,
            [
                ("country", "Country", "text", "text"),
                ("flow", "Flow", "text", "text"),
                ("modern_top_1pct_product_share", "Top 1% share", "pct", "number"),
                ("modern_top_5pct_product_share", "Top 5% share", "pct", "number"),
                ("top_1pct_cutoff_products", "Top 1% products", "int", "number"),
                ("top_5pct_cutoff_products", "Top 5% products", "int", "number"),
                ("modern_product_gini", "Modern Gini", "dec", "number"),
                ("paper_product_gini", "Paper Gini", "dec", "number"),
                ("product_gini_diff", "Gini diff", "dec", "number"),
                ("modern_active_products", "Modern products", "int", "number"),
                ("paper_active_products", "Paper products", "int", "number"),
                ("active_products_diff", "Product diff", "int", "number"),
            ],
            "prof-p-top-share-table",
        )
        prof_p_lorenz_summary_table = table_rows(
            prof_p_lorenz_summary,
            [
                ("country", "Country", "text"),
                ("flow", "Flow", "text"),
                ("modern_top_1pct_product_share", "Top 1% share", "pct"),
                ("modern_top_5pct_product_share", "Top 5% share", "pct"),
                ("modern_product_gini", "Modern Gini", "dec"),
                ("paper_product_gini", "Paper Gini", "dec"),
                ("modern_active_products", "Modern products", "int"),
            ],
        )

    country_size_link = ""
    country_size_hypothesis = ""
    country_size_main_table = ""
    country_size_two_way_table = ""
    country_size_fama_macbeth_table = ""
    country_size_gmm_lag_iv_table = ""
    country_size_gmm_lag_iv_first_stage_table = ""
    country_size_primary_share_table = ""
    country_size_primary_share_two_way_table = ""
    country_size_primary_share_fama_macbeth_table = ""
    country_size_primary_share_diagnostics_table = ""
    country_size_robustness_table = ""
    country_size_us_counterfactual = ""
    country_size_yearly_summary_table = ""
    country_size_diagnostics_table = ""
    country_size_world_large_spearman_table = ""
    country_size_world_large_population_spearman_table = ""
    country_size_world_large_model_table = ""
    country_size_world_large_diagnostics_table = ""
    country_size_world_large_cards = ""
    country_size_takeaways = ""
    if country_size:
        main_rows = country_size_rows(country_size.get("main_models", []))
        two_way_rows = country_size_rows(country_size.get("two_way_cluster_models", []))
        fama_macbeth_rows = country_size_rows(country_size.get("fama_macbeth_models", []))
        gmm_lag_iv_rows = country_size_gmm_rows(country_size.get("gmm_lag_iv_models", []))
        gmm_lag_iv_first_stage_rows = country_size_gmm_first_stage_rows(country_size.get("gmm_lag_iv_first_stage", []))
        primary_share_rows = country_size_rows(country_size.get("primary_share_control_models", []))
        primary_share_two_way_rows = country_size_rows(country_size.get("primary_share_two_way_cluster_models", []))
        primary_share_fama_macbeth_rows = country_size_rows(country_size.get("primary_share_fama_macbeth_models", []))
        robustness_rows = country_size_rows(country_size.get("robustness_models", []), "baseline_log_population") + country_size_rows(
            country_size.get("robustness_models", []), "average_log_population"
        )
        yearly_summary_rows = [dict(row, measure=country_size_measure_label(row)) for row in country_size.get("yearly_summary", [])]
        world_large_gdp_spearman_rows = world_large_spearman_rows(country_size.get("world_large_spearman_summary", []), "log_gdp_current_usd")
        world_large_population_spearman_rows = world_large_spearman_rows(country_size.get("world_large_spearman_summary", []), "log_population")
        world_large_exposure_model_rows = world_large_model_rows(country_size.get("world_large_models", []), "world_share_exposure")
        primary_diag_summary_rows = [
            row for row in country_size.get("primary_export_share_diagnostics", []) if str(row.get("row_type") or "") == "summary"
        ]
        country_size_link = '<a href="country-size-effect.html"><span>04</span><strong>Country size effect</strong><small>Population-gradient tests with clustered, two-way, Fama-MacBeth, and Lag-IV GMM checks.</small></a>'
        country_size_hypothesis = hypothesis_grid(
            [
                hypothesis_card(
                    "Size effect",
                    "Country size and concentration",
                    "Are larger countries less concentrated in product or partner trade baskets?",
                    "The within-year cross-country coefficient on log population is consistently negative, especially for export product concentration.",
                    "The coefficient is unstable, flips sign, or only survives one standard-error convention.",
                    "Mostly supports an export product-size gradient. The main, two-way-clustered, and Fama-MacBeth checks point to lower export product concentration among larger countries; import and partner gradients are weaker.",
                    [
                        ("Country size effect page", "country-size-effect.html"),
                        ("Main model CSV", "assets/downloads/country_size_effect_main_models.csv"),
                        ("Fama-MacBeth CSV", "assets/downloads/country_size_effect_fama_macbeth_models.csv"),
                    ],
                )
            ]
        )
        country_size_main_table = table_rows(
            main_rows,
            [
                ("measure", "Outcome", "text"),
                ("coefficient", "Log-pop coef.", "dec"),
                ("std_error", "SE", "dec"),
                ("p_value", "p-value", "dec"),
                ("bh_q_value", "BH q", "dec"),
                ("nobs", "Obs.", "int"),
                ("clusters", "Country clusters", "int"),
                ("status", "Status", "text"),
            ],
        )
        country_size_world_large_spearman_table = table_rows(
            world_large_gdp_spearman_rows,
            [
                ("measure", "Measure", "text"),
                ("mean_spearman", "Mean Spearman", "dec"),
                ("median_spearman", "Median Spearman", "dec"),
                ("min_spearman", "Min", "dec"),
                ("max_spearman", "Max", "dec"),
                ("share_positive", "Share positive", "pct"),
                ("years", "Years", "int"),
            ],
        )
        country_size_world_large_population_spearman_table = table_rows(
            world_large_population_spearman_rows,
            [
                ("measure", "Measure", "text"),
                ("mean_spearman", "Mean Spearman", "dec"),
                ("median_spearman", "Median Spearman", "dec"),
                ("share_positive", "Share positive", "pct"),
                ("years", "Years", "int"),
            ],
        )
        country_size_world_large_model_table = table_rows(
            world_large_exposure_model_rows,
            [
                ("model", "Model", "text"),
                ("term_label", "Term", "text"),
                ("coefficient", "Coefficient", "dec"),
                ("std_error", "Clustered SE", "dec"),
                ("p_value", "p-value", "dec"),
                ("bh_q_value", "BH q", "dec"),
                ("nobs", "Obs.", "int"),
                ("clusters", "Country clusters", "int"),
                ("status", "Status", "text"),
            ],
        )
        country_size_two_way_table = table_rows(
            two_way_rows,
            [
                ("measure", "Outcome", "text"),
                ("coefficient", "Log-pop coef.", "dec"),
                ("std_error", "Two-way SE", "dec"),
                ("p_value", "p-value", "dec"),
                ("bh_q_value", "BH q", "dec"),
                ("nobs", "Obs.", "int"),
                ("clusters", "Min clusters", "int"),
                ("status", "Status", "text"),
            ],
        )
        country_size_fama_macbeth_table = table_rows(
            fama_macbeth_rows,
            [
                ("measure", "Outcome", "text"),
                ("coefficient", "Mean annual slope", "dec"),
                ("std_error", "HAC SE", "dec"),
                ("simple_std_error", "Simple SE", "dec"),
                ("p_value", "p-value", "dec"),
                ("bh_q_value", "BH q", "dec"),
                ("years_estimated", "Years", "int"),
                ("status", "Status", "text"),
            ],
        )
        country_size_gmm_lag_iv_table = table_rows(
            gmm_lag_iv_rows,
            [
                ("measure", "Outcome", "text"),
                ("term_label", "Endogenous regressor", "text"),
                ("coefficient", "GMM coef.", "dec"),
                ("std_error", "Clustered SE", "dec"),
                ("p_value", "p-value", "dec"),
                ("bh_q_value", "BH q", "dec"),
                ("j_p_value", "Hansen J p", "dec"),
                ("instrument_count", "Instr.", "int"),
                ("nobs", "Obs.", "int"),
                ("clusters", "Country clusters", "int"),
                ("status", "Status", "text"),
            ],
        )
        country_size_gmm_lag_iv_first_stage_table = table_rows(
            gmm_lag_iv_first_stage_rows,
            [
                ("measure", "Outcome", "text"),
                ("term_label", "Endogenous regressor", "text"),
                ("partial_rsquared", "Partial R2", "dec"),
                ("shea_rsquared", "Shea R2", "dec"),
                ("f_stat", "First-stage stat", "dec"),
                ("f_pval", "p-value", "dec"),
                ("f_dist", "Distribution", "text"),
                ("status", "Status", "text"),
            ],
        )
        country_size_primary_share_table = table_rows(
            primary_share_rows,
            [
                ("model", "Primary control", "text"),
                ("measure", "Outcome", "text"),
                ("coefficient", "Log-pop coef.", "dec"),
                ("std_error", "SE", "dec"),
                ("p_value", "p-value", "dec"),
                ("bh_q_value", "BH q", "dec"),
                ("nobs", "Obs.", "int"),
                ("clusters", "Country clusters", "int"),
                ("status", "Status", "text"),
            ],
        )
        country_size_primary_share_two_way_table = table_rows(
            primary_share_two_way_rows,
            [
                ("model", "Primary control", "text"),
                ("measure", "Outcome", "text"),
                ("coefficient", "Log-pop coef.", "dec"),
                ("std_error", "Two-way SE", "dec"),
                ("p_value", "p-value", "dec"),
                ("bh_q_value", "BH q", "dec"),
                ("nobs", "Obs.", "int"),
                ("clusters", "Min clusters", "int"),
                ("status", "Status", "text"),
            ],
        )
        country_size_primary_share_fama_macbeth_table = table_rows(
            primary_share_fama_macbeth_rows,
            [
                ("model", "Primary control", "text"),
                ("measure", "Outcome", "text"),
                ("coefficient", "Mean annual slope", "dec"),
                ("std_error", "HAC SE", "dec"),
                ("simple_std_error", "Simple SE", "dec"),
                ("p_value", "p-value", "dec"),
                ("bh_q_value", "BH q", "dec"),
                ("years_estimated", "Years", "int"),
                ("status", "Status", "text"),
            ],
        )
        country_size_primary_share_diagnostics_table = table_rows(
            primary_diag_summary_rows,
            [("diagnostic", "Diagnostic", "text"), ("value", "Value", "text"), ("detail", "Detail", "text")],
        )
        country_size_us_counterfactual = country_size_us_counterfactual_card(
            country_size.get("us_population_counterfactuals", [])
        )
        country_size_robustness_table = table_rows(
            robustness_rows,
            [
                ("model", "Size measure", "text"),
                ("measure", "Outcome", "text"),
                ("coefficient", "Coef.", "dec"),
                ("std_error", "SE", "dec"),
                ("p_value", "p-value", "dec"),
                ("nobs", "Obs.", "int"),
                ("clusters", "Country clusters", "int"),
                ("status", "Status", "text"),
            ],
        )
        country_size_yearly_summary_table = table_rows(
            yearly_summary_rows,
            [
                ("measure", "Outcome", "text"),
                ("years_estimated", "Years", "int"),
                ("mean_beta", "Mean beta", "dec"),
                ("median_beta", "Median beta", "dec"),
                ("min_beta", "Min beta", "dec"),
                ("max_beta", "Max beta", "dec"),
            ],
        )
        country_size_diagnostics_table = table_rows(
            country_size.get("sample_diagnostics", []),
            [("diagnostic", "Diagnostic", "text"), ("value", "Value", "text")],
        )
        country_size_world_large_diagnostics_table = table_rows(
            country_size.get("world_large_diagnostics", []),
            [("diagnostic", "Diagnostic", "text"), ("value", "Value", "dec"), ("detail", "Detail", "text")],
        )
        strongest_export = country_size.get("strongest_export", {})
        strongest_import = country_size.get("strongest_import", {})
        headline_world_large = find_value(
            world_large_gdp_spearman_rows,
            outcome="world_share_exposure",
            size_variable="log_gdp_current_usd",
        )
        product_alignment_world_large = find_value(
            world_large_gdp_spearman_rows,
            outcome="spearman_product_alignment",
            size_variable="log_gdp_current_usd",
        )
        main_world_large_model = find_value(
            world_large_exposure_model_rows,
            model_label="main_gdp_year_fe",
            term="log_gdp_current_usd",
        )
        conditional_world_large_model = find_value(
            world_large_exposure_model_rows,
            model_label="conditional_gdp_gdppc_year_fe",
            term="log_gdp_current_usd",
        )
        country_size_world_large_cards = f"""
      <div class="stat-grid">
        <article class="stat-card"><span>Headline GDP-rank test</span><strong>{dec(headline_world_large.get("mean_spearman"), 3)}</strong><small>Mean yearly Spearman between log GDP and world-share exposure; median {dec(headline_world_large.get("median_spearman"), 3)}.</small></article>
        <article class="stat-card"><span>Positive years</span><strong>{pct(headline_world_large.get("share_positive"), 0)}</strong><small>Share of years where larger GDP ranks align with higher exposure to globally large products.</small></article>
        <article class="stat-card"><span>Main GDP coefficient</span><strong>{dec(main_world_large_model.get("coefficient"), 4)}</strong><small>Year-FE model; p={dec(main_world_large_model.get("p_value"), 3)}, BH q={dec(main_world_large_model.get("bh_q_value"), 3)}.</small></article>
        <article class="stat-card"><span>Product-alignment diagnostic</span><strong>{dec(product_alignment_world_large.get("mean_spearman"), 3)}</strong><small>Not equivalent to the size test; it asks whether each country's own top products are globally large.</small></article>
      </div>
      <p class="source-note">Conditional GDP coefficient holding GDP per capita fixed: {dec(conditional_world_large_model.get("coefficient"), 4)}. Interpret this as scale conditional on development, not the total GDP-size relationship.</p>
        """
        country_size_takeaways = f"""
          <ul class="callout-list">
            <li>The main estimand is descriptive: it compares larger and smaller countries within the same year, controlling for log GDP per capita and year fixed effects.</li>
            <li>The strongest export gradient is <strong>{country_size_measure_label(strongest_export)}</strong>, with log-population coefficient <strong>{dec(strongest_export.get("coefficient"), 4)}</strong> and country-clustered SE <strong>{dec(strongest_export.get("std_error"), 4)}</strong>.</li>
            <li>The strongest import gradient is <strong>{country_size_measure_label(strongest_import)}</strong>, with log-population coefficient <strong>{dec(strongest_import.get("coefficient"), 4)}</strong> and country-clustered SE <strong>{dec(strongest_import.get("std_error"), 4)}</strong>.</li>
            <li>The GDP-based companion test asks a different question: whether large economies export globally large products. Its headline outcome is <strong>world-share exposure</strong>; the within-country product-rank Spearman is only a diagnostic.</li>
            <li>The robustness tables separate inference, Lag-IV GMM, size-measure, annual-slope, and primary-export-share controls. The GMM check is diagnostic and should not be read as proof that endogeneity is solved.</li>
          </ul>
        """

    growth_effect_link = ""
    growth_effect_hypothesis = ""
    growth_effect_main_table = ""
    growth_effect_sample_comparison_table = ""
    growth_effect_robustness_table = ""
    growth_effect_income_bin_table = ""
    growth_effect_threshold_table = ""
    growth_effect_diagnostics_table = ""
    growth_effect_takeaways = ""
    if growth_effect:
        main_rows = growth_effect_rows(growth_effect.get("main_models", []))
        sample_comparison_rows = growth_effect_rows(growth_effect.get("sample_comparison_models", []))
        robustness_rows = growth_effect_robustness_rows(growth_effect.get("robustness_models", []))
        income_bin_rows = growth_effect_bin_rows([row for row in growth_effect.get("income_bin_slopes", []) if row.get("row_type") == "slope"])
        threshold_rows = growth_effect_bin_rows([row for row in growth_effect.get("threshold_scan", []) if row.get("row_type") == "difference"])
        growth_effect_link = '<a href="growth-effect.html"><span>05</span><strong>Growth effect</strong><small>Lagged real export growth and concentration levels.</small></a>'
        strongest = growth_effect.get("strongest_absolute", {})
        leveling = growth_effect.get("leveling_strongest", {})
        cutoffs = growth_effect.get("cutoffs", {})
        horizons = growth_effect.get("horizons", [])
        horizon_text = "/".join(str(int(h)) for h in horizons) if horizons else "1/5/10"
        growth_diag = {str(row.get("diagnostic")): row.get("value") for row in growth_effect.get("sample_diagnostics", [])}
        common_base_window = (
            f"{growth_diag.get('horizon_1_first_base_year')}-{growth_diag.get('horizon_1_last_base_year')}"
            if growth_diag.get("horizon_1_first_base_year") and growth_diag.get("horizon_1_last_base_year")
            else "the matched base-year window"
        )
        growth_effect_hypothesis = hypothesis_grid(
            [
                hypothesis_card(
                    "Growth effect",
                    "Export growth and concentration",
                    f"Does lagged real aggregate export growth predict lower or higher concentration levels {horizon_text} years later?",
                    "The lagged export-growth coefficient is stable across horizons under clustered inference and timing/placebo checks.",
                    "The coefficient disappears under two-way clustering, is matched by future growth, or depends on one export-level bin.",
                    "Treat as descriptive panel evidence. The page reports country/base-year fixed effects, common-horizon sample matching, placebo, and lagged-export-level checks before making any substantive claim.",
                    [
                        ("Growth effect page", "growth-effect.html"),
                        ("Main model CSV", "assets/downloads/growth_effect_main_models.csv"),
                        ("Robustness CSV", "assets/downloads/growth_effect_robustness_models.csv"),
                    ],
                )
            ]
        )
        growth_effect_main_table = table_rows(
            main_rows,
            [
                ("horizon_label", "Horizon", "text"),
                ("measure", "Outcome", "text"),
                ("coefficient", "Lag export-growth coef.", "dec"),
                ("std_error", "SE", "dec"),
                ("p_value", "p-value", "dec"),
                ("bh_q_value", "BH q", "dec"),
                ("nobs", "Obs.", "int"),
                ("clusters", "Country clusters", "int"),
                ("status", "Status", "text"),
            ],
        )
        growth_effect_sample_comparison_table = table_rows(
            sample_comparison_rows,
            [
                ("horizon_label", "Horizon", "text"),
                ("model", "Sample", "text"),
                ("measure", "Outcome", "text"),
                ("coefficient", "Lag export-growth coef.", "dec"),
                ("std_error", "SE", "dec"),
                ("p_value", "p-value", "dec"),
                ("bh_q_value", "BH q", "dec"),
                ("nobs", "Obs.", "int"),
                ("clusters", "Country clusters", "int"),
                ("status", "Status", "text"),
            ],
        )
        growth_effect_robustness_table = table_rows(
            robustness_rows,
            [
                ("horizon_label", "Horizon", "text"),
                ("model", "Check", "text"),
                ("measure", "Outcome", "text"),
                ("coefficient", "Coef.", "dec"),
                ("std_error", "SE", "dec"),
                ("p_value", "p-value", "dec"),
                ("bh_q_value", "BH q", "dec"),
                ("nobs", "Obs.", "int"),
                ("clusters", "Clusters", "int"),
                ("status", "Status", "text"),
            ],
        )
        growth_effect_income_bin_table = table_rows(
            income_bin_rows,
            [
                ("horizon_label", "Horizon", "text"),
                ("measure", "Outcome", "text"),
                ("export_level_bin", "Lagged export-level bin", "text"),
                ("coefficient", "Growth slope", "dec"),
                ("std_error", "SE", "dec"),
                ("p_value", "p-value", "dec"),
                ("bh_q_value", "BH q", "dec"),
                ("nobs", "Obs.", "int"),
                ("status", "Status", "text"),
            ],
        )
        growth_effect_threshold_table = table_rows(
            threshold_rows,
            [
                ("horizon_label", "Horizon", "text"),
                ("measure", "Outcome", "text"),
                ("threshold_percentile", "Cutoff pctile", "int"),
                ("threshold_exports_constant_2015_usd", "Cutoff exports", "dec"),
                ("coefficient", "High-low diff.", "dec"),
                ("std_error", "SE", "dec"),
                ("p_value", "p-value", "dec"),
                ("bh_q_value", "BH q", "dec"),
                ("status", "Status", "text"),
            ],
        )
        growth_effect_diagnostics_table = table_rows(
            growth_effect.get("sample_diagnostics", []),
            [("diagnostic", "Diagnostic", "text"), ("value", "Value", "text")],
        )
        growth_effect_takeaways = f"""
          <ul class="callout-list">
            <li>The main model is descriptive: country and base-year fixed effects absorb time-invariant country differences and global base-year shocks, but time-varying confounding remains possible.</li>
            <li>Horizon means years from the export-growth base year to the concentration outcome year. The regression sample is matched across horizons, so 1-, 5-, and 10-year rows use the same country-flow-base-year support; in this run the common base-year window is <strong>{common_base_window}</strong>.</li>
            <li>The robustness section now compares this balanced/common-support sample with a broad available-horizon sample. The broad sample uses every row available for each horizon, so differences between the two tables flag possible horizon-specific selection.</li>
            <li>Export growth uses World Bank goods-and-services exports, while the concentration outcomes are merchandise concentration measures. Read the exposure as an aggregate export-growth environment, not the exact concentration denominator.</li>
            <li>The largest absolute lagged export-growth coefficient is <strong>{growth_effect_measure_label(strongest)}</strong> at horizon <strong>{dec(strongest.get("horizon"), 0)} years</strong>, coefficient <strong>{dec(strongest.get("coefficient"), 4)}</strong>, with country-clustered SE <strong>{dec(strongest.get("std_error"), 4)}</strong>.</li>
            <li>Lagged export-level terciles use World Bank real exports in constant 2015 US dollars. The first available low/middle cutoff is <strong>${dec(cutoffs.get("low_middle_export_cutoff"), 0)}</strong> and middle/high cutoff is <strong>${dec(cutoffs.get("middle_high_export_cutoff"), 0)}</strong>.</li>
            <li>The leveling-off check compares high-export-level and low-export-level growth slopes using a BH q-value threshold of 0.10. The largest high-minus-low difference is <strong>{growth_effect_measure_label(leveling)}</strong>, coefficient <strong>{dec(leveling.get("coefficient"), 4)}</strong>, BH q-value <strong>{dec(leveling.get("bh_q_value"), 4)}</strong>.</li>
          </ul>
        """

    future_growth_link = ""
    future_growth_hypothesis = ""
    future_growth_council_takeaways = ""
    future_growth_takeaways = ""
    future_growth_bucket_table = ""
    future_growth_bucket_model_table = ""
    future_growth_continuous_table = ""
    future_growth_paired_table = ""
    future_growth_robustness_table = ""
    future_growth_mechanism_survival = ""
    future_growth_base_size_table = ""
    future_growth_base_size_model_table = ""
    future_growth_mechanism_model_table = ""
    future_growth_mechanism_diagnostics_table = ""
    future_growth_examples_table = ""
    future_growth_diagnostics_table = ""
    future_growth_missing_controls_table = ""
    if future_growth:
        future_growth_link = '<a href="future-growth.html"><span>06</span><strong>Future growth</strong><small>Base concentration and later real merchandise export growth.</small></a>'
        future_growth_bucket_rows_display = future_growth_bucket_rows(future_growth.get("bucket_summary", []))
        future_growth_bucket_model_rows = future_growth_rows(future_growth.get("bucket_focus", []))
        future_growth_continuous_rows = future_growth_rows(future_growth.get("continuous_focus", []))
        future_growth_paired_rows = future_growth_rows(future_growth.get("paired_focus", []))
        future_growth_robustness_rows = future_growth_rows(future_growth.get("robustness_focus", []))
        future_growth_base_size_rows = future_growth_rows(future_growth.get("base_size_focus", []))
        future_growth_mechanism_rows = future_growth_rows(future_growth.get("mechanism_focus", []))
        future_growth_base_size_bin_rows = future_growth_bucket_rows(future_growth.get("base_size_bin_focus", []))
        future_growth_summary_rows = future_growth.get("mechanism_summary", [])
        future_growth_summary_map = {str(row.get("test_id")): row for row in future_growth_summary_rows}
        future_growth_examples = future_growth_bucket_rows(
            [row for row in future_growth.get("country_examples", []) if int(row.get("horizon") or 0) == 5]
        )
        future_growth_strongest = future_growth.get("strongest_absolute", {})
        h5_export_high_low = find_value(
            future_growth.get("bucket_summary", []),
            flow="Exports",
            horizon=5,
            concentration_bucket="high_product_low_partner",
        )
        h5_export_low_low = find_value(
            future_growth.get("bucket_summary", []),
            flow="Exports",
            horizon=5,
            concentration_bucket="low_product_low_partner",
        )
        h5_export_bucket_coef = find_value(
            future_growth.get("bucket_focus", []),
            flow="Exports",
            horizon=5,
            term="bucket_high_product_low_partner",
        )
        raw_h5_export_gap = float(h5_export_high_low.get("mean_annualized_log_growth") or math.nan) - float(
            h5_export_low_low.get("mean_annualized_log_growth") or math.nan
        )
        adjusted_h5_export_gap = float(
            h5_export_high_low.get("mean_size_adjusted_annualized_log_growth") or math.nan
        ) - float(h5_export_low_low.get("mean_size_adjusted_annualized_log_growth") or math.nan)
        within_size_bin_gap_row = future_growth_summary_map.get("within_size_bin_gap", {})
        bottom10_coef_row = future_growth_summary_map.get("drop_bottom_10pct_coef", {})
        new_partner_gap_row = future_growth_summary_map.get("new_partner_share_gap", {})
        primary_share_row = future_growth_summary_map.get("primary_share_control_coef", {})
        future_growth_council_takeaways = f"""
    <section class="section" id="future-growth-council">
      <div class="section-heading">
        <h2>Economist Council Takeaways</h2>
        <p>Advisor-mode council read using identification, econometrics, trade/spatial, political-economy, macro-GE, and writing perspectives. The council treats the size-control rerun as the decisive page update.</p>
      </div>
      <div class="stat-grid">
        <article class="stat-card"><span>Raw 5-year export bucket gap</span><strong>{pct(raw_h5_export_gap)}</strong><small>High-product/low-partner minus low-product/low-partner before size controls.</small></article>
        <article class="stat-card"><span>Size-adjusted gap</span><strong>{pct(adjusted_h5_export_gap)}</strong><small>Same comparison after residualizing on initial exports and macro size controls.</small></article>
        <article class="stat-card"><span>Country/year FE coefficient</span><strong>{pct(h5_export_bucket_coef.get("coefficient"))}</strong><small>5-year high-product/low-partner bucket; p={dec(h5_export_bucket_coef.get("p_value"), 3)}, BH q={dec(h5_export_bucket_coef.get("bh_q_value"), 3)}.</small></article>
        <article class="stat-card"><span>Council verdict</span><strong>Caution</strong><small>The raw bucket pattern looks partly like a low-base denominator effect, not a standalone concentration-growth result.</small></article>
      </div>
      <div class="interpretation-grid">
        <article class="note">
          <h3>Best reading</h3>
          <p>The credible headline is that base concentration does not robustly forecast faster future export growth once initial export scale and macro size are made explicit. The raw bucket spread is still useful, but as a diagnostic for scale effects.</p>
        </article>
        <article class="note">
          <h3>Best objection</h3>
          <p>Size controls change the effective sample and may absorb development-stage differences. The table therefore reports both raw and size-adjusted observations, and the regression rows remain the cleaner comparison.</p>
        </article>
        <article class="note">
          <h3>New mechanism tests</h3>
          <p>The page now bins by base real exports, drops low-base observations, checks dollar and asinh outcomes, merges Exercise 12 extensive-margin channels, and reports leave-one-country-out influence.</p>
        </article>
        <article class="note">
          <h3>What to emphasize</h3>
          <p>Lead with the size-adjusted and fixed-effect results. De-emphasize any claim that high concentration itself predicts growth unless a separate identification design is added.</p>
        </article>
      </div>
    </section>
        """
        future_growth_hypothesis = hypothesis_grid(
            [
                hypothesis_card(
                    "Future growth",
                    "Concentration predicts later export growth",
                    "Do base-year import/export concentration across products, partners, and product-partner cells predict future real merchandise export growth?",
                    "Concentration measures or high/low buckets forecast meaningfully different 1-, 5-, or 10-year annualized export growth after controls and country/year fixed effects.",
                    "Concentration has no stable predictive association after controls and fixed effects.",
                    (
                        "Descriptive and predictive, not causal. The page extends Exercise 2 beyond export-only buckets by adding imports, product-partner-cell measures, continuous specifications, paired product/partner regressions, and robustness checks."
                    ),
                    [
                        ("Future-growth page", "future-growth.html"),
                        ("Exercise 2 buckets", "extension.html#growth-buckets"),
                        ("Exercise 12 decomposition", "exercise-12.html"),
                    ],
                )
            ]
        )
        future_growth_bucket_table = table_rows(
            future_growth_bucket_rows_display,
            [
                ("flow", "Exposure flow", "text"),
                ("horizon", "Horizon", "int"),
                ("bucket_label", "Bucket", "text"),
                ("observations", "Obs.", "int"),
                ("countries", "Countries", "int"),
                ("mean_annualized_log_growth", "Mean annualized growth", "pct"),
                ("median_annualized_log_growth", "Median annualized growth", "pct"),
                ("size_adjusted_observations", "Size-control obs.", "int"),
                ("mean_size_adjusted_annualized_log_growth", "Size-adjusted mean growth", "pct"),
                ("median_size_adjusted_annualized_log_growth", "Size-adjusted median growth", "pct"),
                ("median_initial_exports_constant_2015_usd", "Median base real exports", "money"),
            ],
        )
        future_growth_bucket_model_table = table_rows(
            future_growth_bucket_model_rows,
            [
                ("flow", "Exposure flow", "text"),
                ("horizon", "Horizon", "int"),
                ("term_label", "Bucket term", "text"),
                ("coefficient", "Coef.", "dec"),
                ("std_error", "SE", "dec"),
                ("p_value", "p-value", "dec"),
                ("bh_q_value", "BH q", "dec"),
                ("nobs", "Obs.", "int"),
                ("clusters", "Countries", "int"),
                ("status", "Status", "text"),
            ],
        )
        future_growth_continuous_table = table_rows(
            future_growth_continuous_rows,
            [
                ("measure", "Measure", "text"),
                ("horizon", "Horizon", "int"),
                ("term_label", "Exposure", "text"),
                ("coefficient", "Coef.", "dec"),
                ("std_error", "SE", "dec"),
                ("p_value", "p-value", "dec"),
                ("bh_q_value", "BH q", "dec"),
                ("nobs", "Obs.", "int"),
                ("clusters", "Countries", "int"),
                ("status", "Status", "text"),
            ],
        )
        future_growth_paired_table = table_rows(
            future_growth_paired_rows,
            [
                ("flow", "Exposure flow", "text"),
                ("horizon", "Horizon", "int"),
                ("term_label", "Term", "text"),
                ("coefficient", "Coef.", "dec"),
                ("std_error", "SE", "dec"),
                ("p_value", "p-value", "dec"),
                ("bh_q_value", "BH q", "dec"),
                ("nobs", "Obs.", "int"),
                ("clusters", "Countries", "int"),
                ("status", "Status", "text"),
            ],
        )
        future_growth_robustness_table = table_rows(
            future_growth_robustness_rows,
            [
                ("model", "Check", "text"),
                ("measure", "Measure", "text"),
                ("term_label", "Term", "text"),
                ("coefficient", "Coef.", "dec"),
                ("std_error", "SE", "dec"),
                ("p_value", "p-value", "dec"),
                ("bh_q_value", "BH q", "dec"),
                ("nobs", "Obs.", "int"),
                ("clusters", "Clusters", "int"),
                ("status", "Status", "text"),
            ],
        )
        future_growth_base_size_table = table_rows(
            future_growth_base_size_bin_rows,
            [
                ("base_size_bin", "Base-size bin", "text"),
                ("bucket_label", "Bucket", "text"),
                ("observations", "Obs.", "int"),
                ("countries", "Countries", "int"),
                ("mean_annualized_log_growth", "Raw mean growth", "pct"),
                ("mean_size_adjusted_annualized_log_growth", "Size-adjusted mean", "pct"),
                ("mean_annualized_asinh_real_export_change", "Asinh-change mean", "pct"),
                ("median_initial_exports_constant_2015_usd", "Median base real exports", "money"),
            ],
        )
        future_growth_base_size_model_table = table_rows(
            future_growth_base_size_rows,
            [
                ("model", "Check", "text"),
                ("outcome", "Outcome", "text"),
                ("term_label", "Bucket term", "text"),
                ("coefficient", "Coef.", "dec"),
                ("std_error", "SE", "dec"),
                ("p_value", "p-value", "dec"),
                ("bh_q_value", "BH q", "dec"),
                ("nobs", "Obs.", "int"),
                ("clusters", "Countries", "int"),
                ("status", "Status", "text"),
            ],
        )
        future_growth_mechanism_model_table = table_rows(
            future_growth_mechanism_rows,
            [
                ("model", "Channel", "text"),
                ("outcome_label", "Outcome", "text"),
                ("term_label", "Bucket term", "text"),
                ("coefficient", "Coef.", "dec"),
                ("std_error", "SE", "dec"),
                ("p_value", "p-value", "dec"),
                ("bh_q_value", "BH q", "dec"),
                ("nobs", "Obs.", "int"),
                ("clusters", "Countries", "int"),
                ("status", "Status", "text"),
            ],
        )
        future_growth_mechanism_diagnostics_table = table_rows(
            future_growth.get("mechanism_diagnostics_focus", []),
            [("diagnostic", "Diagnostic", "text"), ("value", "Value", "text")],
        )
        future_growth_mechanism_summary_table = table_rows(
            future_growth_summary_rows,
            [
                ("test_label", "Test", "text"),
                ("estimate", "Estimate", "pct"),
                ("p_value", "p-value", "dec"),
                ("bh_q_value", "BH q", "dec"),
                ("nobs", "Obs.", "int"),
                ("interpretation", "Interpretation", "text"),
            ],
        )
        future_growth_mechanism_survival = f"""
    <section class="section" id="future-growth-mechanism-tests">
      <div class="section-heading">
        <h2>What survives after size controls?</h2>
        <p>This panel separates denominator mechanics from extensive-margin evidence. It keeps the claim descriptive: the test is whether the high-product/low-partner bucket still looks different after base size, low-base exclusions, entry channels, and commodity controls.</p>
      </div>
      <div class="stat-grid">
        <article class="stat-card"><span>Within-size-bin gap</span><strong>{pct(within_size_bin_gap_row.get("estimate"))}</strong><small>Equal-bin 5-year export gap after comparing buckets inside base-export quintiles.</small></article>
        <article class="stat-card"><span>Bottom 10% excluded</span><strong>{pct(bottom10_coef_row.get("estimate"))}</strong><small>Country/year FE coefficient; p={dec(bottom10_coef_row.get("p_value"), 3)}, BH q={dec(bottom10_coef_row.get("bh_q_value"), 3)}.</small></article>
        <article class="stat-card"><span>New-partner channel gap</span><strong>{pct(new_partner_gap_row.get("estimate"))}</strong><small>Exercise 12 gross-positive share from new partners for existing products.</small></article>
        <article class="stat-card"><span>Primary-share control</span><strong>{pct(primary_share_row.get("estimate"))}</strong><small>Broad primary-product share added as a commodity/development-stage control.</small></article>
      </div>
      <div class="callout">
        <p><strong>Reading:</strong> if the raw gap shrinks in the size-adjusted, within-bin, and low-base-excluded rows, base size is doing much of the work. Extensive-margin rows are still useful if new-product, new-partner, or new-cell shares remain elevated, but that supports a market-discovery interpretation rather than a causal concentration-growth claim.</p>
      </div>
      <h3 class="subsection-title">Mechanism Summary</h3>
      {future_growth_mechanism_summary_table}
      <h3 class="subsection-title">Base-Size Bin Means</h3>
      {future_growth_base_size_table}
      <h3 class="subsection-title">Base-Size, Placebo, and Commodity Checks</h3>
      {future_growth_base_size_model_table}
      <h3 class="subsection-title">Extensive-Margin Channel Regressions</h3>
      {future_growth_mechanism_model_table}
      <h3 class="subsection-title">Mechanism Diagnostics</h3>
      {future_growth_mechanism_diagnostics_table}
    </section>
        """
        future_growth_examples_table = table_rows(
            future_growth_examples,
            [
                ("flow", "Exposure flow", "text"),
                ("example_type", "Example type", "text"),
                ("country", "Country", "text"),
                ("year", "Base year", "year"),
                ("future_year", "Future year", "year"),
                ("bucket_label", "Bucket", "text"),
                ("annualized_real_export_growth_log", "Annualized real growth", "pct"),
                ("base_exports_constant_2015_usd", "Base real exports", "money"),
                ("future_exports_constant_2015_usd", "Future real exports", "money"),
                ("product_gini", "Product Gini", "dec"),
                ("partner_gini", "Partner Gini", "dec"),
            ],
        )
        future_growth_diagnostics_table = table_rows(
            future_growth.get("sample_diagnostics", []),
            [("diagnostic", "Diagnostic", "text"), ("value", "Value", "text")],
        )
        future_growth_missing_controls_table = table_rows(
            future_growth.get("missing_controls_summary", []),
            [("flow", "Exposure flow", "text"), ("horizon", "Horizon", "int"), ("missing_required_rows", "Rows missing required controls", "int")],
        )
        future_growth_takeaways = f"""
          <ul class="callout-list">
            <li>This is predictive panel evidence, not causal identification. Country and year fixed effects absorb country constants and global shocks, but time-varying policy, demand, and industrial-composition shocks can still confound the coefficients.</li>
            <li>The outcome is annualized future real merchandise export growth from Comtrade totals deflated to constant 2015 USD with the US GDP deflator: <code>[log(real exports_c,t+h) - log(real exports_c,t)] / h</code>. The base export denominator therefore matches the merchandise concentration data better than World Bank goods-and-services exports.</li>
            <li>The size-adjusted bucket columns residualize annualized growth on log initial real exports, oil share, real GDP, population, real GNI per capita, and base-year fixed effects within each exposure-flow/horizon, then add back the raw flow-horizon mean.</li>
            <li>Product Gini measures concentration across HS6 products, Partner Gini across destinations or sources, and Product-partner-cell Gini across HS6-by-partner cells. Product and cell measures exclude HS6 <strong>999999</strong> before aggregation; partner totals include it by repo convention.</li>
            <li>In the 5-year export-exposure buckets, high-product/low-partner observations have size-adjusted mean annualized growth <strong>{pct(h5_export_high_low.get("mean_size_adjusted_annualized_log_growth"))}</strong>, versus <strong>{pct(h5_export_low_low.get("mean_size_adjusted_annualized_log_growth"))}</strong> for low-product/low-partner observations; the raw means are <strong>{pct(h5_export_high_low.get("mean_annualized_log_growth"))}</strong> and <strong>{pct(h5_export_low_low.get("mean_annualized_log_growth"))}</strong>.</li>
            <li>The largest absolute continuous coefficient is <strong>{future_growth_measure_label(future_growth_strongest)}</strong>, horizon <strong>{int(future_growth_strongest.get("horizon") or 0)}</strong>, coefficient <strong>{dec(future_growth_strongest.get("coefficient"), 4)}</strong>, p-value <strong>{dec(future_growth_strongest.get("p_value"), 4)}</strong>, BH q-value <strong>{dec(future_growth_strongest.get("bh_q_value"), 4)}</strong>.</li>
          </ul>
        """

    partner_stability_link = ""
    partner_stability_hypothesis = ""
    partner_stability_takeaways = ""
    partner_stability_summary_table = ""
    partner_stability_common_trend_table = ""
    partner_stability_variance_table = ""
    partner_stability_low_active_table = ""
    partner_stability_exception_table = ""
    partner_stability_manifest_table = ""
    partner_stability_stat_cards = ""
    if partner_stability:
        partner_stability_link = '<a href="partner-stability.html"><span>05</span><strong>Partner stability</strong><small>Within-country Partner-Gini stability tests and exception countries.</small></a>'
        stability_summary_rows = partner_stability.get("summary", [])
        stability_common_rows = partner_stability.get("common_trends", [])
        stability_variance_rows = partner_stability.get("variance_decomposition", [])
        main_export_summary = find_value(stability_summary_rows, window="main_2000_2024", flow="Exports")
        main_import_summary = find_value(stability_summary_rows, window="main_2000_2024", flow="Imports")
        main_export_trend = find_value(stability_common_rows, window="main_2000_2024", flow="Exports")
        main_import_trend = find_value(stability_common_rows, window="main_2000_2024", flow="Imports")
        main_export_variance = find_value(stability_variance_rows, window="main_2000_2024", flow="Exports")
        main_import_variance = find_value(stability_variance_rows, window="main_2000_2024", flow="Imports")
        manifest = partner_stability.get("manifest", {})
        main_window = manifest.get("main_window") or [2000, 2024]
        balanced_window = manifest.get("balanced_window") or [2001, 2021]
        main_window_label = f"{int(main_window[0])}-{int(main_window[1])}" if len(main_window) == 2 else "2000-2024"
        balanced_window_label = f"{int(balanced_window[0])}-{int(balanced_window[1])}" if len(balanced_window) == 2 else "2001-2021"
        common_display = []
        for row in stability_common_rows:
            display = dict(row)
            display["coefficient"] = row.get("coefficient_per_decade")
            display["std_error"] = row.get("std_error_per_decade")
            display["ci"] = f"{dec(row.get('ci_low_per_decade'))} to {dec(row.get('ci_high_per_decade'))}"
            common_display.append(display)
        exception_display = []
        for row in partner_stability.get("main_exceptions", []):
            display = dict(row)
            display["bh_q_value"] = row.get("slope_q_value")
            exception_display.append(display)
        partner_stability_stat_cards = f"""
      <div class="stat-grid">
        <article class="stat-card"><span>Export median 10-year change</span><strong>{dec(main_export_summary.get("median_abs_slope_per_decade"))}</strong><small>absolute fitted Partner-Gini slope, {main_window_label}</small></article>
        <article class="stat-card"><span>Import median 10-year change</span><strong>{dec(main_import_summary.get("median_abs_slope_per_decade"))}</strong><small>absolute fitted Partner-Gini slope, {main_window_label}</small></article>
        <article class="stat-card"><span>Export stable share</span><strong>{pct(main_export_summary.get("share_stable_slope_10yr_0p02"))}</strong><small>countries within +/-0.02 fitted 10-year change</small></article>
        <article class="stat-card"><span>Import stable share</span><strong>{pct(main_import_summary.get("share_stable_slope_10yr_0p02"))}</strong><small>countries within +/-0.02 fitted 10-year change</small></article>
      </div>
        """
        partner_stability_hypothesis = hypothesis_grid(
            [
                hypothesis_card(
                    "Partner-Gini stability",
                    "Mostly stable, not stable for every country",
                    "Is Partner Gini relatively stable over time for rd2 countries?",
                    "Most country-flow series have small fitted 10-year changes and small endpoint changes.",
                    "Common time trends or many country-specific changes are large enough to reject stability.",
                    (
                        f"Mostly supports. In {main_window_label}, {pct(main_export_summary.get('share_stable_slope_10yr_0p02'))} of export country series and "
                        f"{pct(main_import_summary.get('share_stable_slope_10yr_0p02'))} of import country series stay within a +/-0.02 fitted 10-year change. "
                        f"The common export trend is {dec(main_export_trend.get('coefficient_per_decade'))} per decade; the common import trend is "
                        f"{dec(main_import_trend.get('coefficient_per_decade'))} per decade. The claim is not true for every country."
                    ),
                    [
                        ("Slope distribution", "#partner-stability-figures"),
                        ("Country exceptions", "#partner-stability-exceptions"),
                        ("Stability memo", "assets/downloads/partner_gini_stability.md"),
                    ],
                )
            ]
        )
        partner_stability_takeaways = f"""
          <ul class="callout-list">
            <li>The defensible statement is <strong>Partner Gini is relatively stable for most rd2 countries</strong>, not that it is stable for all countries.</li>
            <li>The main window is <strong>{main_window_label}</strong>; the test excludes the partial 2025 tail. The balanced sensitivity window is <strong>{balanced_window_label}</strong>.</li>
            <li>Partner Gini is computed across observed positive trade partners after products are summed into partner totals. HS6 <strong>999999</strong> is included in partner totals by convention; aggregate partner <code>partnerCode == 0</code> is excluded upstream.</li>
            <li>Common time movement is small relative to persistent country differences. Adding year fixed effects raises R-squared by only <strong>{dec(main_export_variance.get("incremental_r2_year_fe"))}</strong> for exports and <strong>{dec(main_import_variance.get("incremental_r2_year_fe"))}</strong> for imports.</li>
            <li>The exceptions matter: Armenia imports, United Arab Emirates exports, Kyrgyzstan imports, Egypt exports, and China exports have large endpoint changes in the main window.</li>
          </ul>
        """
        partner_stability_summary_table = table_rows(
            stability_summary_rows,
            [
                ("window", "Window", "text"),
                ("flow", "Flow", "text"),
                ("countries", "Countries", "int"),
                ("median_abs_slope_per_decade", "Median |slope| per decade", "dec"),
                ("p90_abs_slope_per_decade", "P90 |slope| per decade", "dec"),
                ("share_stable_slope_10yr_0p02", "Share |slope| <= 0.02", "pct"),
                ("median_abs_endpoint_change", "Median |endpoint change|", "dec"),
                ("share_stable_endpoint_0p05", "Share endpoint <= 0.05", "pct"),
                ("median_within_country_sd", "Median within-country SD", "dec"),
                ("countries_with_slope_q_lt_0p05", "Countries q < 0.05", "int"),
            ],
        )
        partner_stability_common_trend_table = table_rows(
            common_display,
            [
                ("window", "Window", "text"),
                ("flow", "Flow", "text"),
                ("coefficient", "Coef. per decade", "dec"),
                ("std_error", "SE per decade", "dec"),
                ("ci", "95% CI", "text"),
                ("p_value", "p-value", "dec"),
                ("bh_q_value", "BH q", "dec"),
                ("nobs", "Obs.", "int"),
                ("countries", "Countries", "int"),
                ("r_squared", "R-squared", "dec"),
                ("status", "Status", "text"),
            ],
        )
        partner_stability_variance_table = table_rows(
            stability_variance_rows,
            [
                ("window", "Window", "text"),
                ("flow", "Flow", "text"),
                ("nobs", "Obs.", "int"),
                ("countries", "Countries", "int"),
                ("years", "Years", "int"),
                ("r2_country_fe", "Country FE R2", "dec"),
                ("r2_country_year_fe", "Country + year FE R2", "dec"),
                ("incremental_r2_year_fe", "Incremental year-FE R2", "dec"),
                ("rmse_country_fe", "Country FE RMSE", "dec"),
                ("rmse_country_year_fe", "Country + year FE RMSE", "dec"),
            ],
        )
        partner_stability_exception_table = table_rows(
            exception_display,
            [
                ("flow", "Flow", "text"),
                ("country", "Country", "text"),
                ("iso3", "ISO3", "text"),
                ("first_year", "First year", "year"),
                ("last_year", "Last year", "year"),
                ("first_partner_gini", "First Gini", "dec"),
                ("last_partner_gini", "Last Gini", "dec"),
                ("endpoint_change", "Endpoint change", "dec"),
                ("slope_per_decade", "Slope per decade", "dec"),
                ("slope_p_value", "Raw p", "dec"),
                ("bh_q_value", "BH q", "dec"),
                ("first_partner_active_count", "First active partners", "dec"),
                ("last_partner_active_count", "Last active partners", "dec"),
                ("min_partner_active_count", "Min active partners", "dec"),
                ("median_partner_active_count", "Median active partners", "dec"),
                ("mean_partner_active_count", "Mean partners", "dec"),
            ],
        )
        partner_stability_low_active_table = table_rows(
            partner_stability.get("low_active_sensitivity", []),
            [
                ("window", "Window", "text"),
                ("flow", "Flow", "text"),
                ("min_partner_active_count_required", "Min partners required", "int"),
                ("original_rows", "Original rows", "int"),
                ("kept_rows", "Kept rows", "int"),
                ("dropped_rows", "Dropped rows", "int"),
                ("eligible_country_flows", "Eligible country-flows", "int"),
                ("median_abs_slope_per_decade", "Median |slope| per decade", "dec"),
                ("share_stable_slope_10yr_0p02", "Share |slope| <= 0.02", "pct"),
                ("median_abs_endpoint_change", "Median |endpoint change|", "dec"),
                ("share_stable_endpoint_0p05", "Share endpoint <= 0.05", "pct"),
            ],
        )
        count_diagnostics = manifest.get("count_diagnostics") or {}
        partner_stability_manifest_table = table_rows(
            [
                {"item": "Country sample", "value": manifest.get("country_sample")},
                {"item": "Source table", "value": manifest.get("source")},
                {"item": "Source rows", "value": count_diagnostics.get("source_rows", manifest.get("rows"))},
                {"item": "Main-window rows", "value": count_diagnostics.get("main_window_rows")},
                {"item": "Main-window country-flow series", "value": count_diagnostics.get("main_window_country_flows")},
                {"item": "Balanced-window rows", "value": count_diagnostics.get("balanced_window_rows")},
                {"item": "Balanced-window country-flow series", "value": count_diagnostics.get("balanced_window_country_flows")},
                {"item": "Duplicate country-year-flow keys", "value": count_diagnostics.get("duplicate_country_year_flow_keys")},
                {"item": "Source year range", "value": f"{manifest.get('year_min')}-{manifest.get('year_max')}"},
                {"item": "Main window", "value": main_window_label},
                {"item": "Balanced window", "value": balanced_window_label},
            ],
            [("item", "Item", "text"), ("value", "Value", "text")],
        )

    overview_cards = f"""
      <div class="stat-grid">
        <article class="stat-card"><span>Median export Product Gini</span><strong>{dec(exp.get("product_gini"))}</strong><small>across HS6 products, {sample_year_min}-{sample_year_max}</small></article>
        <article class="stat-card"><span>Median import Product Gini</span><strong>{dec(imp.get("product_gini"))}</strong><small>across HS6 products, same panel</small></article>
        <article class="stat-card"><span>Full lumpy exclusion</span><strong>{dec(full_excl.get("product_gini"))}</strong><small>import Product Gini, from {dec(baseline.get("product_gini"))}</small></article>
        <article class="stat-card"><span>Energy import-bin Product Gini</span><strong>{dec(energy.get("product_gini"))}</strong><small>within HS6 energy products; top-1 share {pct(energy.get("top_1_product_share"))}</small></article>
      </div>
    """

    index_hypothesis = hypothesis_grid(
        [
            hypothesis_card(
                "Framing question",
                "Extending the 2001 concentration",
                "Does the concentration pattern persist when the selected country sample is followed across many years rather than one central cross-section?",
                "Product Gini, Partner Gini, and Product-partner cell Gini stay high across countries and years.",
                "The high concentration pattern disappears, flips, or depends mainly on one year/sample.",
                f"Supports. In the {sample_panel_label}, median Product Ginis across HS6 products are {dec(exp.get('product_gini'))} for exports and {dec(imp.get('product_gini'))} for imports, and median Product-partner cell Ginis across HS6-by-partner cells are {dec(exp.get('product_partner_cell_gini'))} and {dec(imp.get('product_partner_cell_gini'))}.",
                [
                    ("Extension page", "extension.html#map-lines"),
                    ("Import mechanisms", "imports.html#import-bins"),
                    ("Data downloads", "methods.html#downloads"),
                ],
            )
        ]
    )

    extension_hypotheses = hypothesis_grid(
        [
            hypothesis_card(
                "Exercise 1",
                "Persistent aggregate concentration",
                "Concentration is a persistent aggregate fact, not a one-year artifact.",
                "Product Gini and Partner Gini stay high across countries and years.",
                "Concentration disappears or changes sharply by year/sample.",
                f"Supports. Median export Product Gini across HS6 products changes from {dec(exp_start.get('product_gini'))} in {sample_year_min} to {dec(exp_end.get('product_gini'))} in {sample_year_max}; import Product Gini changes from {dec(imp_start.get('product_gini'))} to {dec(imp_end.get('product_gini'))}.",
                [
                    ("Map and lines", "#map-lines"),
                    ("Panel CSV", "assets/downloads/exercise_01_concentration_all_years.csv"),
                ],
            ),
            hypothesis_card(
                "Exercise 6",
                "Lumpy-product explanation",
                "Concentration is mostly driven by oil, aircraft, precious metals/gold, ships, arms, or other obvious lumpy categories.",
                "Ginis fall sharply after excluding these product groups.",
                "Ginis remain high after the exclusions.",
                f"Weakens the mostly-lumpy explanation. The full import-side exclusion lowers median Product Gini across HS6 products only from {dec(baseline.get('product_gini'))} to {dec(full_excl.get('product_gini'))}, while removing a median {pct(full_excl.get('trade_share_removed'))} of trade value.",
                [
                    ("Exclusion table", "#lumpy-exclusions"),
                    ("Exclusion CSV", "assets/downloads/exercise_06_concentration_exclusions_all_years.csv"),
                ],
            ),
            hypothesis_card(
                "Exercise 10",
                "Benchmark/null model",
                "Observed concentration is higher than what would arise mechanically from scale, sparsity, active products, and broad HS2 sector composition.",
                "Actual concentration sits well above simulated/random benchmarks for most countries and years.",
                "Actual concentration is close to what the benchmark would generate.",
                "Supports. Actual Product Ginis across HS6 products sit above both the loose active-count-only benchmark and the conservative HS2-preserving benchmark. The HS2 benchmark is conditional, not complete randomization.",
                [
                    ("Benchmark ladder", "#benchmark-ladder"),
                    ("Benchmark CSV", "assets/downloads/exercise_10_hs2_product_benchmark_all_years.csv"),
                ],
            ),
            hypothesis_card(
                "Exercise 2",
                "Growth-bucket context",
                "Product-Gini and Partner-Gini concentration predict future export growth.",
                "High-Product-Gini/high-Partner-Gini countries grow meaningfully differently from low-low countries.",
                "Buckets show no meaningful growth differences.",
                "Mixed/descriptive. The bucket table is useful context, but this site treats it as descriptive rather than causal evidence about growth.",
                [
                    ("Growth buckets", "#growth-buckets"),
                    ("Downloads", "methods.html#downloads"),
                ],
            ),
        ]
    )

    import_mechanism_taxonomy_rows = [
        {
            "mechanism": "Energy / product concentration",
            "diagnostic": "Concentration inside the energy HS6 bin.",
            "result": (
                f"{stable_import_bin_year}: energy median Product Gini {dec(stable_energy.get('product_gini'))}; "
                f"top-1 product share {pct(stable_energy.get('top_1_product_share'))}; "
                f"top-5 product share {pct(stable_energy.get('top_5_product_share'))}; "
                f"import value share {pct(stable_energy.get('import_value_share'))}; "
                f"leave-one-out Gini effect {dec(stable_energy.get('product_gini_reduction_when_excluded'))}."
            ),
            "reading": (
                "This is the closest import-side analogue to a pure few-products story: a small bin with very large "
                "within-bin product spikes, especially fuel and related energy lines."
            ),
        },
        {
            "mechanism": "Intermediate value scale",
            "diagnostic": "Large import share, but spread across many input products.",
            "result": (
                f"{stable_import_bin_year}: intermediates are {pct(stable_intermediates.get('import_value_share'))} "
                f"of import value; top-1 product share {pct(stable_intermediates.get('top_1_product_share'))}; "
                f"top-5 product share {pct(stable_intermediates.get('top_5_product_share'))}; "
                f"Product Gini {dec(stable_intermediates.get('product_gini'))}; "
                f"Exercise 11 intermediate interaction {dec(ex11_interaction.get('coef'))}."
            ),
            "reading": (
                "Intermediates matter by scale, not because one or two input products dominate the basket. The "
                "export-linkage test does not support the broad claim that concentration-driving intermediates are "
                "systematically the export engine."
            ),
        },
        {
            "mechanism": "Supplier / partner exposure",
            "diagnostic": "Dominant source countries inside products and aggregate Partner-Gini counterfactual.",
            "result": (
                f"{stable_import_bin_year}: country-specific median top-supplier share "
                f"{pct(stable_supplier.get('median_top_supplier_share'))}; "
                f"products above 75% top-supplier share {pct(stable_supplier.get('share_products_top_supplier_ge_75'))}; "
                f"value in those rows {pct(stable_supplier.get('import_value_share_products_top_supplier_ge_75'))}. "
                f"Neutralizing within-product supplier dominance cuts latest-country Partner Gini by "
                f"{dec(partner_counterfactual_summary.get('partner_gini_reduction'))}, or "
                f"{pct(partner_counterfactual_summary.get('explained_share'))} of actual Partner Gini. "
                f"H2.4 global benchmark: world-product median top-supplier share "
                f"{pct(stable_h24_supplier.get('median_top_supplier_share'))}."
            ),
            "reading": (
                "This is the specific product-supplier-cell mechanism: the product basket need not be extremely narrow "
                "for imports to remain exposed to a few source countries within important products."
            ),
        },
    ]
    import_mechanism_taxonomy_table = table_rows(
        import_mechanism_taxonomy_rows,
        [
            ("mechanism", "Mechanism", "text"),
            ("diagnostic", "Diagnostic", "text"),
            ("result", "Result", "text"),
            ("reading", "Reading", "text"),
        ],
    )
    import_mechanism_taxonomy_section = f"""
    <section class="section" id="import-mechanism-taxonomy">
      <div class="section-heading">
        <h2>Import-Mechanism Taxonomy</h2>
        <p>Import concentration should not be read as one mechanism. The evidence separates energy/product spikes, intermediate-input scale, and supplier-country exposure.</p>
      </div>
      <div class="table-scroll">{import_mechanism_taxonomy_table}</div>
      <p class="source-note">Stable latest-year rows use {stable_import_bin_year}, with {stable_import_bin_country_count} rd2 reporters, instead of the thinner 2025 tail. H2.4 is a global world-product benchmark, not an rd2-country statistic. These are descriptive mechanism diagnostics, not causal estimates.</p>
    </section>
    """

    imports_hypotheses = hypothesis_grid(
        [
            hypothesis_card(
                "Exercise 3",
                "Import bins",
                "Import concentration is driven by energy, capital goods, or key intermediates rather than final consumption goods.",
                "Those bins are internally concentrated and explain large top-product shares or reduce aggregate Gini when excluded.",
                "Final goods are equally concentrated, or high-concentration bins are too small to explain aggregate concentration.",
                f"Supports a two-part answer. Energy is the sharpest spike, with median bin Gini {dec(energy.get('product_gini'))} and top-1 share {pct(energy.get('top_1_product_share'))}; intermediates are the largest part of the bill, with median import value share {pct(intermediates.get('import_value_share'))}.",
                [
                    ("Import-bin table", "#import-bins"),
                    ("Import-bin CSV", "assets/downloads/exercise_03_import_bin_concentration.csv"),
                ],
            ),
            hypothesis_card(
                "Exercise 4",
                "Dominant supplier by product",
                "Imports are concentrated because each product has one dominant supplier source.",
                "For many importer-product rows, country imports come mostly from the top source country; for a stricter global claim, the world product market is dominated by one supplier.",
                "Import concentration remains high even when supplier shares within products are diffuse.",
                f"Supports a meaningful but incomplete mechanism. In Exercise 4, the median importer-product top-supplier share is {pct(ex4['summary'].get('median_top_supplier_share'))}; products above 75% top-supplier share are {pct(ex4['summary'].get('share_products_top_supplier_ge_75'))} of rows but only {pct(ex4['summary'].get('import_value_share_products_top_supplier_ge_75'))} of value. In H2.4, the full-world {h24_latest_year} median top-supplier share is lower at {pct(h24_latest.get('median_top_supplier_share'))}, with only {pct(h24_latest.get('share_products_top_supplier_ge_75'))} of world product markets above 75%.",
                [
                    ("Supplier dominance", "#supplier-dominance"),
                    ("Partner-Gini counterfactual", "#partner-gini-counterfactual"),
                    ("Supplier CSV", "assets/downloads/exercise_04_dominant_supplier_importer_summary.csv"),
                ],
            ),
            hypothesis_card(
                "Exercise 11",
                "Do concentration-driving imports map to exports?",
                "Import concentration is tied to export production chains.",
                "Concentration-driving imported intermediates are more export-linked than other concentration-driving imports.",
                "They are less export-linked, or no more export-linked, than non-intermediates.",
                f"Weakens the broad processing claim, but supports a narrower supplier-exposure channel. Product-Gini contribution is negatively linked to export value ({dec(ex11_main.get('coef'))}) and export probability ({dec(ex11_any.get('coef'))}), while supplier-country HHI contribution is positively linked to export value ({dec(ex11_supplier.get('coef'))}).",
                [
                    ("Exercise 11 findings", "#io-linkage"),
                    ("Regression table", "#ex11-regressions"),
                    ("Regression coefficients", "assets/downloads/exercise_11_selected_regression_coefficients.csv"),
                ],
            ),
        ]
    )

    pages = {
        "_exercise_first_pages": exercise_first_pages,
        "exercises_index_page": exercises_index_page,
        "exercise_12_metric_section": exercise_12_metric_section,
        "index_hypothesis": index_hypothesis,
        "extension_hypotheses": extension_hypotheses,
        "imports_hypotheses": imports_hypotheses,
        "import_mechanism_taxonomy_section": import_mechanism_taxonomy_section,
        "country_size_hypothesis": country_size_hypothesis,
        "country_size_link": country_size_link,
        "country_size_takeaways": country_size_takeaways,
        "country_size_main_table": country_size_main_table,
        "country_size_two_way_table": country_size_two_way_table,
        "country_size_fama_macbeth_table": country_size_fama_macbeth_table,
        "country_size_gmm_lag_iv_table": country_size_gmm_lag_iv_table,
        "country_size_gmm_lag_iv_first_stage_table": country_size_gmm_lag_iv_first_stage_table,
        "country_size_primary_share_table": country_size_primary_share_table,
        "country_size_primary_share_two_way_table": country_size_primary_share_two_way_table,
        "country_size_primary_share_fama_macbeth_table": country_size_primary_share_fama_macbeth_table,
        "country_size_primary_share_diagnostics_table": country_size_primary_share_diagnostics_table,
        "country_size_robustness_table": country_size_robustness_table,
        "country_size_us_counterfactual": country_size_us_counterfactual,
        "country_size_yearly_summary_table": country_size_yearly_summary_table,
        "country_size_diagnostics_table": country_size_diagnostics_table,
        "country_size_world_large_cards": country_size_world_large_cards,
        "country_size_world_large_spearman_table": country_size_world_large_spearman_table,
        "country_size_world_large_model_table": country_size_world_large_model_table,
        "country_size_world_large_population_spearman_table": country_size_world_large_population_spearman_table,
        "country_size_world_large_diagnostics_table": country_size_world_large_diagnostics_table,
        "growth_effect_hypothesis": growth_effect_hypothesis,
        "growth_effect_link": growth_effect_link,
        "growth_effect_takeaways": growth_effect_takeaways,
        "growth_effect_main_table": growth_effect_main_table,
        "growth_effect_sample_comparison_table": growth_effect_sample_comparison_table,
        "growth_effect_robustness_table": growth_effect_robustness_table,
        "growth_effect_income_bin_table": growth_effect_income_bin_table,
        "growth_effect_threshold_table": growth_effect_threshold_table,
        "growth_effect_diagnostics_table": growth_effect_diagnostics_table,
        "future_growth_hypothesis": future_growth_hypothesis,
        "future_growth_link": future_growth_link,
        "future_growth_council_takeaways": future_growth_council_takeaways,
        "future_growth_takeaways": future_growth_takeaways,
        "future_growth_bucket_table": future_growth_bucket_table,
        "future_growth_bucket_model_table": future_growth_bucket_model_table,
        "future_growth_continuous_table": future_growth_continuous_table,
        "future_growth_paired_table": future_growth_paired_table,
        "future_growth_robustness_table": future_growth_robustness_table,
        "future_growth_mechanism_survival": future_growth_mechanism_survival,
        "future_growth_base_size_table": future_growth_base_size_table,
        "future_growth_base_size_model_table": future_growth_base_size_model_table,
        "future_growth_mechanism_model_table": future_growth_mechanism_model_table,
        "future_growth_mechanism_diagnostics_table": future_growth_mechanism_diagnostics_table,
        "future_growth_examples_table": future_growth_examples_table,
        "future_growth_diagnostics_table": future_growth_diagnostics_table,
        "future_growth_missing_controls_table": future_growth_missing_controls_table,
        "partner_stability_link": partner_stability_link,
        "partner_stability_hypothesis": partner_stability_hypothesis,
        "partner_stability_takeaways": partner_stability_takeaways,
        "partner_stability_summary_table": partner_stability_summary_table,
        "partner_stability_common_trend_table": partner_stability_common_trend_table,
        "partner_stability_variance_table": partner_stability_variance_table,
        "partner_stability_low_active_table": partner_stability_low_active_table,
        "partner_stability_exception_table": partner_stability_exception_table,
        "partner_stability_manifest_table": partner_stability_manifest_table,
        "partner_stability_stat_cards": partner_stability_stat_cards,
        "literature_takeaways": literature_takeaways,
        "cadot_hump_body": cadot_hump_body,
        "contributions_body": contributions_body,
        "overview_cards": overview_cards,
        "sample_country_count": str(sample_country_count),
        "sample_year_min": str(sample_year_min),
        "sample_year_max": str(sample_year_max),
        "stable_window_start": str(shape["stable_window_start"]),
        "stable_window_end": str(shape["stable_window_end"]),
        "stable_min_reporters_per_year_flow": str(shape["stable_min_reporters_per_year_flow"]),
        "stable_max_reporters_per_year_flow": str(shape["stable_max_reporters_per_year_flow"]),
        "stable_balanced_countries_both_flows": str(shape["stable_balanced_countries_both_flows"]),
        "summary_text": (
            f"The empirical extension uses a {sample_country_count}-country Comtrade reporter sample and covers "
            f"{sample_year_min}-{sample_year_max}. Median Product Ginis across HS6 products are "
            f"{dec(exp.get('product_gini'))} for exports and {dec(imp.get('product_gini'))} for imports; "
            f"the Product-partner cell Gini medians across HS6-by-partner cells are {dec(exp.get('product_partner_cell_gini'))} and "
            f"{dec(imp.get('product_partner_cell_gini'))}."
        ),
        "extension_takeaways": f"""
          <ul class="callout-list">
            <li>Product Gini measures concentration across HS6 products: exports <strong>{dec(exp.get("product_gini"))}</strong>, imports <strong>{dec(imp.get("product_gini"))}</strong>.</li>
            <li>Partner Gini measures concentration across destination/source partners and includes HS6 <strong>999999</strong> in partner totals: exports <strong>{dec(exp.get("partner_gini"))}</strong>, imports <strong>{dec(imp.get("partner_gini"))}</strong>.</li>
            <li>Product-partner cell Gini measures concentration across HS6-by-partner cells: exports <strong>{dec(exp.get("product_partner_cell_gini"))}</strong>, imports <strong>{dec(imp.get("product_partner_cell_gini"))}</strong>.</li>
            <li>Median export Product Gini changes from <strong>{dec(exp_start.get("product_gini"))}</strong> in {sample_year_min} to <strong>{dec(exp_end.get("product_gini"))}</strong> in {sample_year_max}; import Product Gini changes from <strong>{dec(imp_start.get("product_gini"))}</strong> to <strong>{dec(imp_end.get("product_gini"))}</strong>.</li>
          </ul>
        """,
        "prof_p_takeaways": f"""
          <ul class="callout-list">
            <li>This tab is fixed to the <strong>Prof P 33-country sample in 2001</strong>; it does not change the sample used by the other pages.</li>
            <li>Top-share columns are new modern HS6 diagnostics. Professor P Table 2 reports <strong>product Ginis and active-product counts</strong>, so those are the direct paper comparison columns.</li>
            <li>The product universe excludes HS6 <strong>999999</strong>, drops the partnerCode 0 world aggregate, and maps changed HS1996 codes to first-listed HS2002 targets before summing collapsed products. Partner-only concentration includes <strong>999999</strong> in partner totals.</li>
            <li>Across all 66 country-flow rows, the maximum absolute Gini difference from Table 2 is <strong>{dec(prof_p_max_abs_gini_diff, 4)}</strong>; the maximum absolute active-product-count difference is <strong>{prof_p_max_abs_count_diff:,}</strong>.</li>
          </ul>
        """,
        "prof_p_top_share_table": prof_p_top_share_table,
        "prof_p_lorenz_summary_table": prof_p_lorenz_summary_table,
        "map_note": evidence_note(
            "Are high trade Ginis broad across countries, or driven by only a few outliers?",
            "Select flow, metric, and year; darker countries have higher concentration for that country-year-flow.",
            "Many countries remain dark across the panel rather than only one or two outliers driving the picture.",
            f"High concentration appears across much of the {sample_country_count}-country sample, not just one country.",
        ),
        "line_note": evidence_note(
            "Is concentration persistent over time within countries?",
            "Select countries, flow, and metric; high, fairly flat lines mean concentration persists within countries.",
            "Country lines stay high across decades rather than collapsing after the 2001 cross-section.",
            "Many countries remain highly concentrated across decades, supporting the extension beyond 2001.",
        ),
        "energy_excluded_note": evidence_note(
            "Does import concentration persist after removing the exact Exercise 3 energy bin?",
            "Select year and countries; the map and lines show import Product Gini after excluding BEC-derived energy products.",
            "Concentration remains visible for many countries even after the energy bin is removed.",
            "This view isolates non-energy import concentration while keeping the Exercise 3 energy definition.",
        ),
        "lumpy_note": evidence_note(
            "Does concentration disappear after removing oil, gold/precious metals, aircraft, ships, and arms?",
            "Compare baseline Gini with exclusion variants and the trade share removed.",
            "The lumpy-product story would be strong if Gini fell sharply after these exclusions.",
            "Concentration falls only modestly, so lumpy products matter but do not explain the whole pattern.",
        ),
        "benchmark_note": evidence_note(
            "Is high concentration just what we would expect from sparse product counts or broad HS2 structure?",
            "Compare actual Ginis with the active-count-only and HS2-preserving null benchmarks.",
            "Actual Ginis sit well above the benchmark distributions.",
            "Actual Ginis remain above both benchmarks; HS2 preservation is a conservative benchmark, not complete randomization.",
        ),
        "growth_note": evidence_note(
            "Do more concentrated export baskets predict different later growth patterns?",
            "Compare annualized growth across concentration buckets and horizons.",
            "High-concentration buckets grow meaningfully differently from low-concentration buckets.",
            "This is descriptive only; it is useful for scoping follow-up questions, not a causal claim.",
        ),
        "lumpy_text": (
            f"The full exclusion lowers the median import Product Gini across HS6 products from {dec(baseline.get('product_gini'))} "
            f"to {dec(full_excl.get('product_gini'))}, while the median removed trade share is "
            f"{pct(full_excl.get('trade_share_removed'))}. This is currently an import-side test."
        ),
        "exclusion_table": table_rows(
            ex6["median_by_variant"],
            [
                ("label", "Specification", "text"),
                ("product_gini", "Median Product Gini (HS6 products)", "dec"),
                ("product_top_1pct_share", "Top 1% share", "pct"),
                ("product_top_5pct_share", "Top 5% share", "pct"),
                ("trade_share_removed", "Trade share removed", "pct"),
            ],
        ),
        "benchmark_table": table_rows(
            ex10["benchmark_ladder"],
            [
                ("benchmark", "Benchmark", "text"),
                ("flow", "Flow", "text"),
                ("actual_gini", "Actual", "dec"),
                ("sim_gini_median", "Benchmark median", "dec"),
                ("gap", "Actual minus benchmark", "dec"),
                ("percentile", "Percentile", "dec"),
            ],
        ),
        "growth_table": table_rows(
            data["exercise2"]["growth_summary"],
            [
                ("horizon", "Horizon", "int"),
                ("concentration_bucket", "Bucket", "text"),
                ("observations", "Obs.", "int"),
                ("mean_annualized_log_growth", "Mean annualized log growth", "pct"),
                ("median_annualized_log_growth", "Median annualized log growth", "pct"),
            ],
        ),
        "growth_model_table": table_rows(
            data["exercise2"]["model_focus"],
            [
                ("model_label", "Model", "text"),
                ("horizon", "Horizon", "int"),
                ("nobs", "Obs.", "int"),
                ("countries", "Countries", "int"),
                ("coefficient", "Coefficient", "dec"),
                ("std_error", "Std. error", "dec"),
                ("t_stat", "t-stat", "dec"),
                ("dropped_rows", "Dropped rows", "int"),
            ],
        ),
        "imports_takeaways": f"""
          <ul class="callout-list">
            <li>Energy has the sharpest within-bin Product Gini across HS6 energy products: median <strong>{dec(energy.get("product_gini"))}</strong>, median top-1 share <strong>{pct(energy.get("top_1_product_share"))}</strong>.</li>
            <li>Intermediates are the largest import bucket: median import value share <strong>{pct(intermediates.get("import_value_share"))}</strong>.</li>
            <li>Across importer-years, the median product top-supplier share is <strong>{pct(ex4["summary"].get("median_top_supplier_share"))}</strong>.</li>
            <li>Products with top supplier share at least 75% are <strong>{pct(ex4["summary"].get("share_products_top_supplier_ge_75"))}</strong> of product rows but <strong>{pct(ex4["summary"].get("import_value_share_products_top_supplier_ge_75"))}</strong> of import value.</li>
            <li>Using the stricter H2.4 world-product-market definition, the {h24_latest_year} median top-supplier share is <strong>{pct(h24_latest.get("median_top_supplier_share"))}</strong>, and only <strong>{pct(h24_latest.get("share_products_top_supplier_ge_75"))}</strong> of world HS6 product markets have a top supplier above 75%.</li>
            <li>In the latest-country counterfactual, neutralizing within-product supplier dominance reduces median import Partner Gini by <strong>{dec(partner_counterfactual_summary.get("partner_gini_reduction"))}</strong>, or <strong>{pct(partner_counterfactual_summary.get("explained_share"))}</strong> of the actual index.</li>
          </ul>
        """,
        "bin_table": table_rows(
            ex3["bin_summary"],
            [
                ("label", "Import bin", "text"),
                ("product_gini", "Median Product Gini within bin", "dec"),
                ("top_1_product_share", "Median top-1 share", "pct"),
                ("import_value_share", "Median import value share", "pct"),
                ("product_gini_reduction_when_excluded", "Leave-one-out Gini effect", "dec"),
                ("active_products", "Active HS6 products", "int"),
            ],
        ),
        "top_goods_by_bin": top_goods_cards(ex3["top_goods"]),
        "supplier_text": (
            "There are two different supplier-dominance concepts. Exercise 4 is country-specific: within an "
            "importer-country and HS6 product, it asks how much that country buys from its largest source. H2.4 is "
            "global: within an HS6 product market, it asks how much of world reported imports comes from the largest "
            "supplier country."
        ),
        "supplier_scope_note": (
            f"In Exercise 4, top-supplier share is largest-source imports divided by one importer country's imports of that HS6 product. "
            f"The interactive country-specific chart summarizes {latest_supplier_reporter_count} reporter countries with {latest_supplier_year} data, "
            f"and India in {india_supplier_year} has top-supplier share at least 75% in {pct(india_supplier.get('share_products_top_supplier_ge_75'))} "
            f"of imported HS6 rows. In H2.4, top-supplier share is largest supplier-country value divided by full-world reported imports of the HS6 product; "
            f"in {h24_latest_year}, the median world product-market top-supplier share is {pct(h24_latest.get('median_top_supplier_share'))}."
        ),
        "supplier_scope_year": str(latest_supplier_year),
        "partner_counterfactual_text": (
            f"This is the country-centric version of the supplier question. For each importer-year, we first compute actual import Partner Gini after summing all HS6 products by source country, including HS6 999999 in partner totals. Then we rebuild the same importer-year after spreading each identified product equally across its observed suppliers, with HS6 999999 held fixed because it is not a real product identity. Across latest available country-years, median actual Partner Gini is {dec(partner_counterfactual_summary.get('actual_partner_gini'))}; the conservative counterfactual median is {dec(partner_counterfactual_summary.get('counterfactual_partner_gini'))}. The median reduction is {dec(partner_counterfactual_summary.get('partner_gini_reduction'))}, or {pct(partner_counterfactual_summary.get('explained_share'))} of actual Partner Gini."
        ),
        "partner_counterfactual_india_text": (
            f"For India in {india_counterfactual_year}, actual import Partner Gini is {dec(partner_counterfactual_india.get('actual_partner_gini'))}. Equalizing suppliers within each identified HS6 product while holding HS6 999999 fixed lowers it to {dec(partner_counterfactual_india.get('counterfactual_partner_gini'))}, a reduction of {dec(partner_counterfactual_india.get('partner_gini_reduction'))} or {pct(partner_counterfactual_india.get('explained_share'))} of the actual index."
        ),
        "partner_counterfactual_definitions": """
          <div class="note">
            <p><strong>Actual Partner Gini</strong> is computed across source countries after summing imports over all HS6 products: <code>Gini_j(sum_p imports_pj)</code>.</p>
            <p><strong>Conservative counterfactual</strong> keeps each identified product's total imports and observed supplier set fixed, but gives every observed supplier the same product share: <code>imports_pj = product_total_p / observed_suppliers_p</code>. HS6 999999 remains in actual partner totals but is held fixed in the counterfactual. The remaining Gini is the residual partner concentration after within-product supplier dominance is neutralized.</p>
            <p><strong>Explained share</strong> is <code>(actual Partner Gini - counterfactual Partner Gini) / actual Partner Gini</code>. Negative values are allowed. The <strong>full-diffusion upper bound</strong> spreads every product equally across all active partners in the country-year; it is a deliberately strong benchmark and collapses Partner Gini to zero by construction.</p>
            <p><strong>Dashed 0.5 line:</strong> a symmetric random positive share vector across many active items has Gini around 0.5. In Product-Gini charts those items are active products; in these Exercise 4 Partner-Gini charts, read the line as the same rough benchmark across active source partners.</p>
          </div>
        """,
        "partner_counterfactual_latest_table": table_rows(
            partner_counterfactual.get("latest", []),
            [
                ("country", "Country", "text"),
                ("iso3", "ISO3", "text"),
                ("year", "Year", "year"),
                ("actual_partner_gini", "Actual Partner Gini", "dec"),
                ("counterfactual_partner_gini", "Counterfactual Partner Gini", "dec"),
                ("partner_gini_reduction", "Gini reduction", "dec"),
                ("explained_share", "Explained share", "pct"),
            ],
        ),
        "io_text": (
            f"Bottom line: Exercise 11 weakens the broad intermediate-processing claim. The import products that raise total Product-Gini concentration across HS6 products are generally less export-linked, including among intermediates. The stronger evidence is supplier-country concentration, not Product-Gini concentration; this leaves room for a narrower China/electronics/machinery-style supplier-exposure story."
        ),
        "benguria_io_note": """
          <div class="note">
            <p><strong>Benguria benchmark:</strong> Benguria's imported-intermediate-input work asks whether access to intermediate input varieties helps export diversification and movement downstream in supply chains. That is the right frame for this page: imported inputs can support export capabilities, but the mechanism points toward access and variety, not a blanket prediction that higher absolute import Product Gini is beneficial.</p>
            <p><strong>How to read this result:</strong> Exercise 11 tests a stricter claim. If concentration-driving HS6 inputs were the export engine, those products or their HS2 chapters should be more export-linked. They are generally less export-linked; the plausible remaining channel is narrower supplier-country exposure in specific input-heavy product groups.</p>
          </div>
        """,
        "ex11_result_ladder": f"""
          <div class="result-ladder">
            <article><span>Product-Gini linkage</span><strong>Negative</strong><p>HS6 Product-Gini contribution to export value: {dec(ex11_main.get("coef"))}; export probability: {dec(ex11_any.get("coef"))}.</p></article>
            <article><span>Intermediate channel</span><strong>Negative</strong><p>Intermediate minus non-intermediate slope: {dec(ex11_interaction.get("coef"))}; concentration-driving intermediates are not more export-linked.</p></article>
            <article><span>Supplier-country exposure</span><strong>Positive</strong><p>Partner-HHI contribution to export value: {dec(ex11_supplier.get("coef"))}.</p></article>
            <article><span>HS2 robustness</span><strong>Does not rescue</strong><p>HS2 export value remains negative ({dec(ex11_hs2_value.get("coef"))}); probability/share and intermediate intensity are small or not significant.</p></article>
            <article><span>Commodity exclusion</span><strong>Result survives</strong><p>Oil/gas/gold/coal rows are {pct(commodity_stats.get("commodity_outlier_row_share"))} of rows and {pct(commodity_stats.get("commodity_outlier_import_value_share"))} of import value; the core signs remain.</p></article>
          </div>
        """,
        "ex11_detail_blocks": f"""
          <div class="interpretation-grid">
            <article class="note">
              <h3>1. HS6 product-level result</h3>
              <p>Within the same country-year, after controlling for product import share and BEC bin, HS6 products with higher contribution to total import Product Gini tend to have lower export value. The export-value coefficient is <strong>{dec(ex11_main.get("coef"))}</strong>; the export-probability coefficient is <strong>{dec(ex11_any.get("coef"))}</strong>.</p>
            </article>
            <article class="note">
              <h3>2. Intermediate-channel test</h3>
              <p>The direct intermediate test is negative. The intermediate minus non-intermediate slope is <strong>{dec(ex11_interaction.get("coef"))}</strong>, so concentration-driving intermediate imports are not more export-linked than concentration-driving non-intermediates.</p>
            </article>
            <article class="note">
              <h3>3. Supplier-country concentration</h3>
              <p>This is the more supportive channel. Products that make import sourcing more concentrated by partner country are more export-linked; the Partner-HHI coefficient is <strong>{dec(ex11_supplier.get("coef"))}</strong>.</p>
            </article>
            <article class="note">
              <h3>4. HS2 robustness</h3>
              <p>Broadening from HS6 products to HS2 chapters does not rescue the intermediate-processing hypothesis. HS2 export value remains negative at <strong>{dec(ex11_hs2_value.get("coef"))}</strong>, export probability is <strong>{dec(ex11_hs2_any.get("coef"))}</strong>, export share is <strong>{dec(ex11_hs2_share.get("coef"))}</strong>, and the intermediate-intensity interaction is <strong>{dec(ex11_hs2_interaction.get("coef"))}</strong>.</p>
            </article>
            <article class="note">
              <h3>5. Oil/gas/gold/coal exclusion</h3>
              <p>Excluding HS4 codes 2701, 2709, 2710, 2711, and 7108 does not overturn the result. These rows are only {pct(commodity_stats.get("commodity_outlier_row_share"))} of product rows but {pct(commodity_stats.get("commodity_outlier_import_value_share"))} of import value; after excluding them, the Product-Gini and intermediate coefficients remain negative and Partner-HHI remains positive.</p>
            </article>
          </div>
        """,
        "coefs_table": table_rows(
            ex11["coefficients"],
            [
                ("result", "Result", "text"),
                ("outcome", "Outcome", "text"),
                ("coef", "Coef.", "dec"),
                ("std_error", "SE", "dec"),
                ("p_value", "p-value", "dec"),
                ("nobs", "Obs.", "int"),
                ("interpretation", "Interpretation", "text"),
            ],
        ),
        "intermediate_effects_table": table_rows(
            ex11["intermediate_effects"],
            [
                ("effect", "Effect", "text"),
                ("coef", "Coef.", "dec"),
                ("std_error", "SE", "dec"),
                ("ci_low", "CI low", "dec"),
                ("ci_high", "CI high", "dec"),
            ],
        ),
        "intermediate_equation": f"""
          <div class="equation-card">
            <h4>Regression plotted here</h4>
            <div class="math-line">
              asinh(export value)<sub>p,c,t</sub> =
              &beta;<sub>1</sub> LOO_Gini_z<sub>p,c,t</sub>
              + &beta;<sub>2</sub> Intermediate<sub>p</sub>
              + &beta;<sub>3</sub> (LOO_Gini_z<sub>p,c,t</sub> &times; Intermediate<sub>p</sub>)
              + &beta;<sub>4</sub> ImportShare_z<sub>p,c,t</sub>
              + &alpha;<sub>c,t</sub>
              + &epsilon;<sub>p,c,t</sub>
            </div>
            <p><strong>Unit:</strong> HS6 product <em>p</em> in reporter country <em>c</em> and year <em>t</em>. <strong>Fixed effects:</strong> country-year. <strong>SEs:</strong> clustered by reporter country.</p>
            <p><strong>How the dots map to the equation:</strong> non-intermediate slope = &beta;<sub>1</sub> ({dec(ex11_non_intermediate_slope.get("coef"))}); intermediate slope = &beta;<sub>1</sub> + &beta;<sub>3</sub> ({dec(ex11_intermediate_slope.get("coef"))}); intermediate minus non-intermediate = &beta;<sub>3</sub> ({dec(ex11_interaction.get("coef"))}).</p>
          </div>
        """,
        "commodity_table": table_rows(
            ex11["commodity_comparison"],
            [
                ("result", "Check", "text"),
                ("coef", "Coef.", "dec"),
                ("std_error", "SE", "dec"),
                ("p_value", "p-value", "dec"),
                ("nobs", "Obs.", "int"),
            ],
        ),
        "methods_hs6_section": methods_hs6_section,
        "world_relative_methods_section": world_relative_methods_section,
        "ex12_extensive_hypothesis": ex12_extensive_hypothesis,
        "ex12_extensive_section": ex12_extensive_section,
        "methods_source_table": source_table,
        "countries_table": countries_table,
    }
    return pages


def nav(active: str) -> str:
    links = [
        ("index.html", "Overview", "overview"),
        ("exercises.html", "Exercises", "exercises"),
        ("extension.html", "Extending 2001", "extension"),
        ("imports.html", "Import concentration", "imports"),
        ("methods.html", "Methods", "methods"),
    ]
    for spec in EXERCISE_PAGE_SPECS:
        if spec["short"] == "12":
            continue
        if active == f"exercise-{spec['short']}":
            links.insert(2, (f"exercise-{spec['short']}.html", f"Exercise {int(spec['short'])}", f"exercise-{spec['short']}"))
            break
    if include_literature_takeaways_page():
        links.insert(3, ("literature.html", "Literature", "literature"))
    if include_contributions_page():
        links.insert(3, ("contributions.html", "Contributions", "contributions"))
    if include_cadot_hump_page():
        cadot_nav_label = (
            "Cadot results" if ACTIVE_SITE_SAMPLE == "cadot_broad_156" else "Behind hump"
        )
        links.insert(3, ("cadot-hump.html", cadot_nav_label, "cadot-hump"))
    if include_world_relative_product_gini():
        links.insert(3, ("world-gini.html", "World Gini", "world-gini"))
    if include_prof_p_page():
        links.insert(3, ("prof-p.html", "Prof P 2001", "prof-p"))
    if include_country_size_page():
        links.insert(3, ("country-size-effect.html", "Country size effect", "country-size-effect"))
    if include_growth_effect_page():
        links.insert(4, ("growth-effect.html", "Growth effect", "growth-effect"))
    if include_future_growth_page():
        links.insert(5, ("future-growth.html", "Future growth", "future-growth"))
    if include_partner_stability_page():
        links.insert(6, ("partner-stability.html", "Partner stability", "partner-stability"))
    if include_ex12_extensive_margin():
        links.insert(2, ("exercise-12.html", "Exercise 12", "exercise-12"))
    return "".join(
        f'<a class="{"active" if key == active else ""}" href="{href}">{label}</a>'
        for href, label, key in links
    )


def layout(title: str, page: str, body: str) -> str:
    build_stamp = now_utc().replace("-", "").replace(":", "").replace("+", "").replace("T", "").replace("Z", "")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <link rel="stylesheet" href="assets/site.css?v={build_stamp}">
</head>
<body data-page="{page}">
  <header class="site-header">
    <div class="header-inner">
      <a class="brand" href="index.html">Trade Concentration Brief</a>
      <nav aria-label="Primary navigation">{nav(page)}</nav>
    </div>
  </header>
  <main>
{body}
  </main>
  <footer class="site-footer">
    <p>Generated from local research outputs on {now_utc()}.</p>
  </footer>
  <script src="assets/vendor/plotly.min.js"></script>
  <script src="assets/site-data.js?v={build_stamp}"></script>
  <script src="assets/site.js?v={build_stamp}"></script>
</body>
</html>
"""


def render_pages(context: dict[str, str]) -> dict[str, str]:
    prof_p_link = ""
    if include_prof_p_page():
        prof_p_link = '<a href="prof-p.html"><span>03</span><strong>Prof P 2001</strong><small>Top product-share diagnostics for the 33-country paper sample.</small></a>'
    world_gini_link = ""
    if include_world_relative_product_gini():
        world_gini_link = '<a href="world-gini.html"><span>06</span><strong>World Gini</strong><small>World-relative export concentration, diagnostics, and downloads.</small></a>'
    ex12_extensive_link = ""
    if include_ex12_extensive_margin():
        ex12_extensive_link = '<a href="exercise-12.html"><span>03</span><strong>Exercise 12</strong><small>LT/HGL HS1992 persistent expansion decomposition, with HS4 robustness.</small></a>'
    literature_link = ""
    if include_literature_takeaways_page():
        literature_link = '<a href="literature.html"><span>08</span><strong>Literature</strong><small>Project-facing takeaways from export-margins, sophistication, survival, and firm-mechanism papers.</small></a>'
    cadot_hump_link = ""
    if include_cadot_hump_page():
        if ACTIVE_SITE_SAMPLE == "cadot_broad_156":
            cadot_hump_link = '<a href="cadot-hump.html"><span>09</span><strong>Cadot Results</strong><small>Combined replication interpretation, production-core sensitivity, mechanisms, and historical partner boundary tests.</small></a>'
        else:
            cadot_hump_link = '<a href="cadot-hump.html"><span>09</span><strong>Behind the Hump</strong><small>Cadot-style reconcentration mechanism tribunal: mechanical, commodity, transition, and old-cone tests.</small></a>'
    contributions_link = ""
    if include_contributions_page():
        contributions_link = '<a href="contributions.html"><span>00</span><strong>Contributions</strong><small>Empirical claims, literature links, and the strongest figures for the project story.</small></a>'
    world_relative_metric_options = ""
    if include_world_relative_product_gini():
        world_relative_metric_options = (
            '<option value="world_relative_product_gini">World-Relative Product Gini (exports)</option>'
            '<option value="world_relative_import_product_gini">World-Relative Import Product Gini (imports)</option>'
        )
    exercise_home_section = ""
    if context.get("_exercise_first_pages"):
        exercise_home_cards = "".join(
            f'<a href="exercise-{spec["short"]}.html"><span>{escape(spec["short"])}</span>'
            f'<strong>{escape(spec["title"].split(":", 1)[-1].strip())}</strong>'
            f'<small>{escape(spec["question"])}</small></a>'
            for spec in EXERCISE_PAGE_SPECS
        )
        exercise_home_section = f"""
    <section class="section" id="exercise-pages">
      <div class="section-heading">
        <h2>Exercise Pages</h2>
        <p>Each exercise starts from the framing question, then gives the rerun Gini/Theil/HHI evidence, restored figures, tables, and downloads.</p>
      </div>
      <div class="link-grid">
        {exercise_home_cards}
      </div>
    </section>
    """
    index_body = f"""
    <section class="hero">
      <div class="eyebrow">Research memo</div>
      <h1>Extending Panagariya-Bagaria Trade Concentration Evidence Across Years</h1>
      <p>{context["summary_text"]}</p>
      <div class="hero-actions">
        <a class="button primary" href="extension.html">Explore the extension</a>
        <a class="button" href="imports.html">View import mechanisms</a>
      </div>
    </section>

    <section class="section hypothesis-section">
      {context["index_hypothesis"]}
    </section>

    {exercise_home_section}

    <section class="section" id="headline-findings">
      <div class="section-heading">
        <h2>Headline Findings</h2>
      </div>
      {context["overview_cards"]}
    </section>

    <section class="section" id="sendable-brief">
      <article>
        <h2>Purpose of This Brief</h2>
        <ul class="callout-list">
          <li><strong>Extension:</strong> the Product-Gini, Partner-Gini, and Product-partner-cell-Gini concentration facts remain visible in the country panel used by the current Exercise 1 artifact.</li>
          <li><strong>Robustness:</strong> removing oil, precious metals/gold, aircraft, ships, and arms lowers export concentration only modestly.</li>
          <li><strong>Mechanisms:</strong> import concentration has energy, supplier-dominance, and input-output pieces, but the broad intermediate-processing story is weakened by the product-level Exercise 11 regressions.</li>
        </ul>
      </article>
    </section>

    <section class="section link-grid">
      {contributions_link}
      <a href="exercises.html"><span>00</span><strong>Exercises</strong><small>One page per exercise, each with framing, Gini/Theil/HHI results, figures, tables, and downloads.</small></a>
        <a href="extension.html"><span>01</span><strong>Extending 2001</strong><small>World map, country lines, exclusions, and null benchmarks.</small></a>
      <a href="imports.html"><span>02</span><strong>Imports</strong><small>Energy, intermediates, dominant suppliers, and input-output linkages.</small></a>
      {ex12_extensive_link}
      {prof_p_link}
      {context["country_size_link"]}
      {context["growth_effect_link"]}
      {context["future_growth_link"]}
      {context["partner_stability_link"]}
      {world_gini_link}
      {literature_link}
      {cadot_hump_link}
      <a href="methods.html"><span>07</span><strong>Methods</strong><small>Data coverage, definitions, and downloadable CSVs.</small></a>
    </section>
    """

    extension_body = f"""
    <section class="page-title">
      <div class="eyebrow">Extension of the 2001 cross-section</div>
      <h1>Concentration Persists Through the Full Panel</h1>
    </section>

    <section class="section hypothesis-section">
      {context["extension_hypotheses"]}
    </section>

    <section class="section" id="extension-summary">
      <div class="section-heading">
        <h2>Interesting things</h2>
        {context["extension_takeaways"]}
      </div>
    </section>

    <section class="section tool-section" id="map-lines">
      <div class="tool-header">
        <div>
          <h2>Map and Country Lines</h2>
          <p>Click a map country or a line to identify it. Use the controls to compare selected countries.</p>
        </div>
        <div class="controls compact">
          <label>Flow <select id="map-flow"><option>Exports</option><option>Imports</option></select></label>
          <label>Metric <select id="map-metric"><option value="product_gini" selected>Product Gini (HS6 products)</option><option value="partner_gini">Partner Gini (trade partners)</option><option value="product_partner_cell_gini">Product-partner cell Gini (HS6-by-partner)</option>{world_relative_metric_options}</select></label>
          <div class="year-control">
            <div class="year-control-head"><span>Year</span><output id="map-year-label" for="map-year-slider"></output></div>
            <input id="map-year-slider" type="range" min="1988" max="2025" step="1">
            <div class="year-range-labels"><span id="map-year-min"></span><span id="map-year-max"></span></div>
            <select id="map-year" class="sr-only" aria-label="Map year"></select>
            <p class="control-note">Drag the year bar to see how country Ginis change over time.</p>
          </div>
        </div>
      </div>
      {context["map_note"]}
      <div id="world-map" class="chart tall"></div>
      <div class="tool-grid">
        <aside class="selector-panel">
          <div class="selector-actions">
            <input id="country-search" type="search" placeholder="Filter countries">
            <button type="button" id="select-all-countries">All</button>
            <button type="button" id="clear-countries">Clear</button>
          </div>
          <div id="country-checkboxes" class="country-list"></div>
        </aside>
        <div>
          <div class="controls compact">
            <label>Line flow <select id="line-flow"><option>Exports</option><option>Imports</option></select></label>
            <label>Line metric <select id="line-metric"><option value="product_gini" selected>Product Gini (HS6 products)</option><option value="partner_gini">Partner Gini (trade partners)</option><option value="product_partner_cell_gini">Product-partner cell Gini (HS6-by-partner)</option>{world_relative_metric_options}</select></label>
          </div>
          {context["line_note"]}
          <div id="country-lines" class="chart tall"></div>
          <div id="line-detail" class="detail-box">Click a line or map country to see country details.</div>
        </div>
      </div>
    </section>

    <section class="section tool-section" id="energy-excluded-map-lines">
      <div class="tool-header">
        <div>
          <h2>Map and Country Lines: Excluding Energy</h2>
          <p>Imports only. Product Gini is recomputed after removing the exact Exercise 3 energy bin.</p>
        </div>
        <div class="controls compact">
          <div class="year-control">
            <div class="year-control-head"><span>Year</span><output id="energy-map-year-label" for="energy-map-year-slider"></output></div>
            <input id="energy-map-year-slider" type="range" min="1988" max="2025" step="1">
            <div class="year-range-labels"><span id="energy-map-year-min"></span><span id="energy-map-year-max"></span></div>
            <select id="energy-map-year" class="sr-only" aria-label="Energy-excluded map year"></select>
            <p class="control-note">Drag the year bar to compare non-energy import concentration across countries.</p>
          </div>
        </div>
      </div>
      {context["energy_excluded_note"]}
      <div id="energy-world-map" class="chart tall"></div>
      <div class="tool-grid">
        <aside class="selector-panel">
          <div class="selector-actions">
            <input id="energy-country-search" type="search" placeholder="Filter countries">
            <button type="button" id="energy-select-all-countries">All</button>
            <button type="button" id="energy-clear-countries">Clear</button>
          </div>
          <div id="energy-country-checkboxes" class="country-list"></div>
        </aside>
        <div>
          <div id="energy-country-lines" class="chart tall"></div>
          <div id="energy-line-detail" class="detail-box">Click a line or map country to see energy-excluded import details.</div>
          <details class="driver-dropdown" id="energy-driver-dropdown">
            <summary>Countries by main driver of ex-energy import concentration change, 2000-2024</summary>
            <div class="driver-controls">
              <label>Driver group <select id="energy-driver-group-select" aria-label="Filter energy driver countries by group"></select></label>
            </div>
            <div id="energy-driver-country-list" class="driver-country-list"></div>
          </details>
        </div>
      </div>
    </section>

    <section class="section tool-section" id="nonenergy-rank-buckets">
      <div class="tool-header">
        <div>
          <h2>Non-Energy Import Basket Rank Buckets</h2>
          <p>Start, midpoint, and end snapshots show how each rd2 country's non-energy HS6 import basket is split across top products, the upper tier, and the long tail.</p>
        </div>
        <div class="controls compact rank-bucket-controls">
          <label>Driver group <select id="rank-bucket-group" aria-label="Filter non-energy rank buckets by driver group"></select></label>
          <label>Sort <select id="rank-bucket-sort" aria-label="Sort non-energy rank bucket chart">
            <option value="end_top5_desc">End top 5 high to low</option>
            <option value="end_tail_desc">End rank 201+ high to low</option>
            <option value="driver_group">Main driver group</option>
            <option value="country">Country A-Z</option>
          </select></label>
          <label>Country <select id="rank-bucket-country" aria-label="Focus country for non-energy rank buckets"></select></label>
          <label>Search <input id="rank-bucket-search" type="search" placeholder="Filter countries" aria-label="Search non-energy rank bucket countries"></label>
        </div>
      </div>
      <article class="evidence-note">
        <dl>
          <dt>Question this answers</dt><dd>Which part of the non-energy import basket explains concentration changes: the top five, ranks 6-50, ranks 51-200, or the rank-201+ tail?</dd>
          <dt>Supports the reading if</dt><dd>The bars show whether concentration is a top-product spike, broader upper-tier thickening, or compression of the long tail.</dd>
          <dt>Current result</dt><dd>The same rank-bucket decomposition is shown for every available rd2 country snapshot, not only the selected figure subset.</dd>
        </dl>
      </article>
      <div class="rank-bucket-layout">
        <div class="rank-bucket-main">
          <div class="rank-bucket-scroll">
            <div id="rank-bucket-overview" class="chart rank-bucket-overview"></div>
          </div>
        </div>
        <div class="rank-bucket-side">
          <h3 id="rank-bucket-focus-title">Country Focus</h3>
          <div id="rank-bucket-country-chart" class="chart rank-bucket-focus"></div>
          <div id="rank-bucket-detail" class="detail-box">Select a country to inspect latest non-energy import totals and top products.</div>
        </div>
      </div>
      <p class="source-note"><strong>Measure:</strong> unit is reporter-snapshot; products are ranked within each country-year by non-energy HS6 import value. Buckets sum to 100% of non-energy imports after excluding HS6 <strong>999999</strong> and the Exercise 3 energy bin before aggregation. Current artifact has 56 countries and 167 country-snapshot bars because Mozambique has midpoint and end snapshots only. The focus box reports the country's latest/end snapshot totals and top five non-energy HS6 products. <a href="assets/downloads/nonenergy_import_rank_decomposition_start_mid_end_balanced_2000_2024_all_countries.csv">Download the rank-bucket CSV</a>; <a href="assets/downloads/top10_nonenergy_import_goods_start_mid_end_balanced_2000_2024_all_countries.csv">download the top-product CSV</a>.</p>
    </section>

    <section class="section" id="lumpy-exclusions">
      <div class="section-heading">
        <h2>Lumpy-Product Exclusions</h2>
        <p>{context["lumpy_text"]}</p>
      </div>
      {context["lumpy_note"]}
      <div id="exclusion-chart" class="chart"></div>
      {context["exclusion_table"]}
      <div class="figure-row">
        <figure><a class="figure-link" href="assets/figures/ex6_before_after.png"><img src="assets/figures/ex6_before_after.png" alt="Before and after Product Gini over time"></a><figcaption>Product Gini across HS6 products before and after full lumpy-product exclusion; the source figure separates imports and exports by line style.</figcaption></figure>
        <figure><a class="figure-link" href="assets/figures/ex6_removed.png"><img src="assets/figures/ex6_removed.png" alt="Trade share removed over time"></a><figcaption>Trade share removed by exclusion specification.</figcaption></figure>
      </div>
    </section>

    <section class="section" id="benchmark-ladder">
      <div class="section-heading">
        <h2>Benchmark Ladder</h2>
        <p>Exercise 10 is best read as a ladder of benchmarks. The active-count-only null is a loose benchmark. The HS2-preserving null is more conservative because it keeps broad HS2 sector totals intact, so it is explicitly not complete randomization.</p>
      </div>
      {context["benchmark_note"]}
      <div id="benchmark-chart" class="chart"></div>
      {context["benchmark_table"]}
      <div class="figure-row">
        <figure><a class="figure-link" href="assets/figures/ex10_actual_vs_benchmark.png"><img src="assets/figures/ex10_actual_vs_benchmark.png" alt="Actual versus HS2-preserved benchmark Product Gini"></a><figcaption>Actual Product Ginis across HS6 products remain above the HS2-preserved random benchmark.</figcaption></figure>
        <figure><a class="figure-link" href="assets/figures/ex10_percentile.png"><img src="assets/figures/ex10_percentile.png" alt="Share above the 95th benchmark percentile"></a><figcaption>Country-year observations above the 95th simulation percentile.</figcaption></figure>
      </div>
    </section>

    <section class="section" id="growth-buckets">
      <div class="section-heading">
        <h2>Descriptive Growth Buckets</h2>
        <p>This local Exercise 2 output is included as context only: it buckets export concentration states and reports subsequent growth. It should not be read as causal evidence.</p>
      </div>
      {context["growth_note"]}
      {context["growth_table"]}
      <h3 class="subsection-title">Bucket Regression Results</h3>
      <p>The table below reports the high-product, low-partner bucket coefficient from the country and year fixed-effect models. The full-control model uses the refreshed World Bank macro controls.</p>
      {context["growth_model_table"]}
      <div class="download-grid compact-downloads">
        <a href="assets/downloads/exercise_02_bucket_growth_summary.csv">Summary CSV</a>
        <a href="assets/downloads/exercise_02_bucket_growth_models.csv">Regression models CSV</a>
        <a href="assets/downloads/exercise_02_bucket_growth_diagnostics.csv">Diagnostics CSV</a>
        <a href="assets/downloads/run_manifest_exercise_02_bucket_growth.json">Refresh manifest JSON</a>
      </div>
    </section>
    """

    exercise12_body = f"""
    <section class="page-title">
      <div class="eyebrow">Exercise 12</div>
      <h1>Where Export Growth Comes From</h1>
      <p>This rd2-only tab uses harmonized-HS6 persistent expansion as the headline. HS4 is shown as a conservative robustness check because it mechanically absorbs fine-product switching inside broader headings.</p>
    </section>

    <section class="section hypothesis-section">
      {context["ex12_extensive_hypothesis"]}
    </section>

    {context["exercise_12_metric_section"]}
    {context["ex12_extensive_section"]}
    """

    imports_body = f"""
    <section class="page-title">
      <div class="eyebrow">Import concentration mechanisms</div>
      <h1>Energy, Intermediates, Suppliers, and Input-Output Linkages</h1>
    </section>

    <section class="section hypothesis-section">
      {context["imports_hypotheses"]}
    </section>

    <section class="section" id="imports-summary">
      <div class="section-heading">
        <h2>Interesting things</h2>
        {context["imports_takeaways"]}
      </div>
    </section>

    {context["import_mechanism_taxonomy_section"]}

    <section class="section" id="import-bins">
      <div class="section-heading">
        <h2>Exercise 3: Import Bins</h2>
        <p>Energy has the strongest within-bin Product Gini across HS6 products and a positive leave-one-bin-out contribution. Intermediates matter more by scale: they are a large part of the import bill and include specialized input categories where a few HS6 lines can carry meaningful value.</p>
      </div>
      <div class="note">
        <p><strong>Import value share</strong> means the bin's share of a country's total import value in a country-year. <strong>Product Gini within bin</strong> measures concentration across HS6 products inside that bin. <strong>Top-1 product share</strong> is the largest HS6 product's share of that bin. <strong>Leave-one-out Gini effect</strong> is the change in overall import Product Gini when the bin is removed; positive values mean the bin raises concentration.</p>
      </div>
      <div id="import-bin-chart" class="chart"></div>
      {context["top_goods_by_bin"]}
      <h3 class="subsection-title">Goods inside each import bin</h3>
      <div class="note">
        <p><strong>Goods histograms:</strong> each bar is one HS6 good in the named bin in 2024, sorted by its summed contribution across countries. The blue figure sums each good's share of each country's total import value. The green figure sums each good's share of each country's imports inside that bin. A height of 100 percentage points is equivalent to one full country-share after summing across countries.</p>
        <p><a href="assets/downloads/exercise_03_import_bin_goods_country_share_2024.csv">Download the full ranked goods table for all four bins</a>.</p>
      </div>
      <h4 class="subsection-title">Energy</h4>
      <div class="figure-row">
        <figure><a class="figure-link" href="assets/figures/ex3_energy_total_share_hist.png"><img src="assets/figures/ex3_energy_total_share_hist.png" alt="Energy goods by summed share of all imports"></a><figcaption>Energy HS6 goods, with bar height equal to the sum across countries of that good's share of total imports.</figcaption></figure>
        <figure><a class="figure-link" href="assets/figures/ex3_energy_bin_share_hist.png"><img src="assets/figures/ex3_energy_bin_share_hist.png" alt="Energy goods by summed share of energy imports"></a><figcaption>Same energy goods, but each country's denominator is energy imports only.</figcaption></figure>
      </div>
      <h4 class="subsection-title">Intermediates</h4>
      <div class="figure-row">
        <figure><a class="figure-link" href="assets/figures/ex3_intermediates_total_share_hist.png"><img src="assets/figures/ex3_intermediates_total_share_hist.png" alt="Intermediate goods by summed share of all imports"></a><figcaption>Intermediate HS6 goods, with bar height equal to the sum across countries of that good's share of total imports.</figcaption></figure>
        <figure><a class="figure-link" href="assets/figures/ex3_intermediates_bin_share_hist.png"><img src="assets/figures/ex3_intermediates_bin_share_hist.png" alt="Intermediate goods by summed share of intermediate imports"></a><figcaption>Same intermediate goods, but each country's denominator is intermediate imports only.</figcaption></figure>
      </div>
      <h4 class="subsection-title">Capital goods</h4>
      <div class="figure-row">
        <figure><a class="figure-link" href="assets/figures/ex3_capital_goods_total_share_hist.png"><img src="assets/figures/ex3_capital_goods_total_share_hist.png" alt="Capital goods by summed share of all imports"></a><figcaption>Capital-goods HS6 products, with bar height equal to the sum across countries of that good's share of total imports.</figcaption></figure>
        <figure><a class="figure-link" href="assets/figures/ex3_capital_goods_bin_share_hist.png"><img src="assets/figures/ex3_capital_goods_bin_share_hist.png" alt="Capital goods by summed share of capital-goods imports"></a><figcaption>Same capital goods, but each country's denominator is capital-goods imports only.</figcaption></figure>
      </div>
      <h4 class="subsection-title">Final consumption</h4>
      <div class="figure-row">
        <figure><a class="figure-link" href="assets/figures/ex3_final_consumption_total_share_hist.png"><img src="assets/figures/ex3_final_consumption_total_share_hist.png" alt="Final-consumption goods by summed share of all imports"></a><figcaption>Final-consumption HS6 goods, with bar height equal to the sum across countries of that good's share of total imports.</figcaption></figure>
        <figure><a class="figure-link" href="assets/figures/ex3_final_consumption_bin_share_hist.png"><img src="assets/figures/ex3_final_consumption_bin_share_hist.png" alt="Final-consumption goods by summed share of final-consumption imports"></a><figcaption>Same final-consumption goods, but each country's denominator is final-consumption imports only.</figcaption></figure>
      </div>
      {context["bin_table"]}
      <div class="figure-row">
        <figure><a class="figure-link" href="assets/figures/ex3_value_share.png"><img src="assets/figures/ex3_value_share.png" alt="Median import value share by bin"></a><figcaption>Median import value share by BEC-style bin.</figcaption></figure>
        <figure><a class="figure-link" href="assets/figures/ex3_leave_one_out.png"><img src="assets/figures/ex3_leave_one_out.png" alt="Gini reduction when each bin is excluded"></a><figcaption>Leave-one-bin-out effect on latest-year import Product Gini across HS6 products.</figcaption></figure>
      </div>
    </section>

    <section class="section" id="supplier-dominance">
      <div class="section-heading">
        <h2>Exercise 4 and H2.4: Dominant Suppliers</h2>
        <p>{context["supplier_text"]}</p>
      </div>
      <div class="note">
        <p>{context["supplier_scope_note"]}</p>
      </div>
      <div class="chart-grid">
        <div id="supplier-chart" class="chart"></div>
        <div id="world-supplier-chart" class="chart"></div>
      </div>
      <div class="figure-row">
        <figure><a class="figure-link" href="assets/figures/h24_importer_world_supplier_comparison.png"><img src="assets/figures/h24_importer_world_supplier_comparison.png" alt="Importer-country versus world product-market supplier dominance"></a><figcaption>Side-by-side comparison of country-specific sourcing dominance and global product-market supplier dominance.</figcaption></figure>
        <figure><a class="figure-link" href="assets/figures/ex4_supplier_distribution.png"><img src="assets/figures/ex4_supplier_distribution.png" alt="Latest-year distribution of top supplier shares"></a><figcaption>Top-supplier-share distribution across all available {context["supplier_scope_year"]} importer-HS6 product rows.</figcaption></figure>
      </div>
    </section>

    <section class="section" id="partner-gini-counterfactual">
      <div class="section-heading">
        <h2>How Much Partner Gini Comes from Within-Product Supplier Dominance?</h2>
        <p>{context["partner_counterfactual_text"]}</p>
      </div>
      {context["partner_counterfactual_definitions"]}
      <div class="note">
        <p><strong>Interpretation rule:</strong> the teal part of the latest-country chart is the amount of aggregate Partner Gini removed by equalizing suppliers within each identified HS6 product while holding HS6 999999 fixed. The gray part is the residual Partner Gini left after that equalization. The dashed 0.5 line marks the symmetric random share-vector benchmark, not perfect equality. The full-diffusion benchmark is shown only as an upper bound because it also equalizes products across partners that were not observed supplying that product.</p>
      </div>
      <div class="figure-row">
        <figure><a class="figure-link" href="assets/figures/ex4_partner_counterfactual_latest.png"><img src="assets/figures/ex4_partner_counterfactual_latest.png" alt="Latest-year import Partner Gini counterfactual decomposition"></a><figcaption>Actual Partner Gini equals the conservative counterfactual residual plus the within-product dominance contribution.</figcaption></figure>
        <figure><a class="figure-link" href="assets/figures/ex4_india_partner_counterfactual.png"><img src="assets/figures/ex4_india_partner_counterfactual.png" alt="India import Partner Gini counterfactual over time"></a><figcaption>{context["partner_counterfactual_india_text"]}</figcaption></figure>
      </div>
      {context["partner_counterfactual_latest_table"]}
    </section>

    <section class="section" id="io-linkage">
      <div class="section-heading">
        <h2>Exercise 11: What the Import-Linkage Test Says</h2>
        <p>{context["io_text"]}</p>
      </div>
      {context["benguria_io_note"]}
      {context["ex11_result_ladder"]}
      <div id="io-chart" class="chart"></div>
      <p class="note">The IO chart is background: some top export sectors rely on concentrated imported inputs. The product-level test below is the main result: the import products that make overall import Product Gini high are usually not the products most tied to exports.</p>
    </section>

    <section class="section" id="ex11-regressions">
      <div class="section-heading">
        <h2>Exercise 11 Regression Audit Trail</h2>
        <p>The table and figures separate Product-Gini concentration from supplier-country concentration. This weakens the broad intermediate-processing claim and points to a narrower supplier-exposure channel.</p>
      </div>
      {context["ex11_detail_blocks"]}
      {context["coefs_table"]}
      <h3 class="subsection-title">Intermediate slopes</h3>
      {context["intermediate_equation"]}
      {context["intermediate_effects_table"]}
      <div class="figure-row full-width">
        <figure><a class="figure-link" href="assets/figures/ex11_coefficients.png"><img src="assets/figures/ex11_coefficients.png" alt="Intermediate channel coefficients"></a><figcaption>Intermediate-channel regression coefficients. The point estimates correspond to the slope mapping in the equation above.</figcaption></figure>
      </div>
      <h3 class="subsection-title">Commodity-exclusion robustness</h3>
      {context["commodity_table"]}
      <div class="figure-row">
        <figure><a class="figure-link" href="assets/figures/ex11_export_linkage_4pct.png"><img src="assets/figures/ex11_export_linkage_4pct.png" alt="HS6 export linkage by Product-Gini leave-one-out four-percent bins"></a><figcaption>HS6 export linkage by Product-Gini contribution, using 25 equal-count four-percent bins.</figcaption></figure>
        <figure><a class="figure-link" href="assets/figures/ex11_hs2_linkage_4pct.png"><img src="assets/figures/ex11_hs2_linkage_4pct.png" alt="HS2 export linkage by summed Product-Gini leave-one-out four-percent bins"></a><figcaption>HS2 export linkage by summed HS6 Product-Gini contribution, using 25 equal-count four-percent bins.</figcaption></figure>
      </div>
      <h3 class="subsection-title">HS2 interactive robustness</h3>
      <p class="note">HS2 means the two-digit Harmonized System chapter: a broad product sector such as HS27 mineral fuels, HS84 machinery, or HS85 electrical machinery. The static figures above use the 4% bin specification; the interactive HS2 view keeps decile and chapter views for quick scanning.</p>
      <div class="controls compact">
        <label>Dot meaning <select id="hs2-linkage-view"><option value="decile">Decile averages</option><option value="chapter">HS2 chapters</option></select></label>
      </div>
      <div class="chart-grid">
        <div id="hs2-probability-chart" class="chart"></div>
        <div id="hs2-value-chart" class="chart"></div>
      </div>
      <div class="figure-row">
        <figure><a class="figure-link" href="assets/figures/ex11_india_io.png"><img src="assets/figures/ex11_india_io.png" alt="India top export input exposure over time"></a><figcaption>India top-export-sector imported-input exposure.</figcaption></figure>
        <figure><a class="figure-link" href="assets/figures/ex11_india_supplier_scatter.png"><img src="assets/figures/ex11_india_supplier_scatter.png" alt="India supplier concentration linkage scatter"></a><figcaption>India supplier concentration and export linkage scatter.</figcaption></figure>
      </div>
    </section>
    """

    country_size_body = f"""
    <section class="page-title">
      <div class="eyebrow">Country-size effect</div>
      <h1>Country Size Effect</h1>
      <p>This page reports the descriptive population-gradient test using the rd2 country sample. The main comparison is large versus small countries within the same year, controlling for log GDP per capita and year fixed effects.</p>
    </section>

    <section class="section hypothesis-section">
      {context["country_size_hypothesis"]}
    </section>

    <section class="section" id="country-size-summary">
      <div class="section-heading">
        <h2>Reading the Test</h2>
        {context["country_size_takeaways"]}
      </div>
      <div class="equation-card">
        <h4>Main specification</h4>
        <div class="math-line">
          concentration<sub>i,t</sub> =
          &beta; log(population)<sub>i,t</sub>
          + &gamma; log(GDP per capita)<sub>i,t</sub>
          + year FE + &epsilon;<sub>i,t</sub>
        </div>
        <p><strong>Unit:</strong> country-year-flow. <strong>Inference:</strong> main table clusters by reporter country. <strong>Interpretation:</strong> negative &beta; means larger countries have lower concentration in that outcome within the same year.</p>
      </div>
    </section>

    <section class="section" id="country-size-main">
      <div class="section-heading">
        <h2>Main Models</h2>
        <p>These are the requested pooled cross-sectional panel models with year fixed effects, no country fixed effects, log GDP per capita control, and country-clustered standard errors.</p>
      </div>
      <div class="main-models-grid">
        <div class="table-scroll">
          {context["country_size_main_table"]}
        </div>
        {context["country_size_us_counterfactual"]}
      </div>
    </section>

    <section class="section" id="country-size-world-large-products">
      <div class="section-heading">
        <h2>Do Large Economies Export Globally Large Products?</h2>
        <p>This is the GDP-based companion test. It uses inclusive world export shares, not leave-one-out weights, and asks whether larger economies are more exposed to products that are large in the world export basket.</p>
      </div>
      {context["country_size_world_large_cards"]}
      <div class="equation-card">
        <h4>World-basket exposure measure</h4>
        <div class="math-line">
          exposure<sub>c,t</sub> =
          &Sigma;<sub>p</sub>
          s<sub>c,p,t</sub> rankpct(w<sub>p,t</sub>)
        </div>
        <p><strong>Country share:</strong> s<sub>c,p,t</sub> is product p's share of country c's exports in year t. <strong>World share:</strong> w<sub>p,t</sub> is product p's share of inclusive world exports in year t. Higher exposure means the country's export basket is weighted toward products that are large globally.</p>
        <p>HS6 <strong>999999</strong> is excluded before product aggregation. The world basket is inclusive: the country is not subtracted from the world product total.</p>
      </div>
      <div class="interpretation-grid">
        <article class="note">
          <h3>Headline size test</h3>
          <p><strong>Spearman(rank GDP, rank exposure)</strong> is computed separately by year and summarized across years. This answers whether larger economies are more exposed to globally large products.</p>
        </article>
        <article class="note">
          <h3>Input-style diagnostic</h3>
          <p><strong>spearman_product_alignment</strong> is computed within a country-year across products. It answers whether that country's biggest export products are also globally big products. It is not equivalent to the GDP size test.</p>
        </article>
        <article class="note">
          <h3>Conditional model caution</h3>
          <p>The conditional regression includes log GDP and log GDP per capita. Since log GDP equals log population plus log GDP per capita, the GDP coefficient there is scale holding development fixed, not the total GDP-size relationship.</p>
        </article>
      </div>
      <div class="figure-row full-width">
        <figure><a class="figure-link" href="assets/figures/country_size_gdp_product_alignment_scatter.png"><img src="assets/figures/country_size_gdp_product_alignment_scatter.png" alt="Scatter plot of log GDP and within-country product-rank alignment"></a><figcaption>Latest-year rd2 country cross-section. Each point is one country; x-axis is log GDP in current USD and y-axis is within-country product-rank alignment. The fitted line and R² are descriptive OLS summaries of the diagnostic relationship, not the headline GDP-rank exposure test.</figcaption></figure>
      </div>
      <h3 class="subsection-title">GDP rank correlations by year, summarized across years</h3>
      <div class="table-scroll">
        {context["country_size_world_large_spearman_table"]}
      </div>
      <h3 class="subsection-title">Regression rows for world-share exposure</h3>
      <div class="table-scroll">
        {context["country_size_world_large_model_table"]}
      </div>
      <h3 class="subsection-title">Population robustness rank correlations</h3>
      <div class="table-scroll">
        {context["country_size_world_large_population_spearman_table"]}
      </div>
      <h3 class="subsection-title">World-basket diagnostics</h3>
      <div class="table-scroll">
        {context["country_size_world_large_diagnostics_table"]}
      </div>
      <div class="download-grid compact-downloads">
        <a href="assets/downloads/world_large_product_exposure_spearman_summary.csv">Spearman summary CSV</a>
        <a href="assets/downloads/world_large_product_exposure_yearly_spearman.csv">Yearly Spearman CSV</a>
        <a href="assets/downloads/world_large_product_exposure_models.csv">Models CSV</a>
        <a href="assets/downloads/world_large_product_exposure_diagnostics.csv">Diagnostics CSV</a>
        <a href="assets/downloads/world_large_product_exposure_panel.csv">Country-year panel CSV</a>
        <a href="assets/downloads/world_large_product_exposure.md">Memo</a>
        <a href="assets/downloads/world_large_product_exposure_adversarial_review.md">Adversarial review</a>
        <a href="assets/downloads/run_manifest_world_large_product_exposure.json">Run manifest JSON</a>
      </div>
    </section>

    <section class="section" id="country-size-inference">
      <div class="section-heading">
        <h2>Inference Robustness</h2>
        <p>Two-way clustering allows common year-level shocks in the residuals. The Fama-MacBeth check asks whether the average annual cross-sectional slope tells the same story; it uses only years with enough countries for the annual cross-section.</p>
      </div>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Method</th>
              <th>Coefficient?</th>
              <th>Standard errors allow</th>
              <th>Interpretation</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Normal pooled / country-clustered</td>
              <td>Same beta</td>
              <td>Errors correlated within a country over time</td>
              <td>Main descriptive size gradient</td>
            </tr>
            <tr>
              <td>Two-way clustered</td>
              <td>Same beta</td>
              <td>Errors correlated within country over time and within year across countries</td>
              <td>Same size gradient, more conservative inference</td>
            </tr>
          </tbody>
        </table>
      </div>
      <h3 class="subsection-title">Country and year two-way clustering</h3>
      <div class="table-scroll">
        {context["country_size_two_way_table"]}
      </div>
      <h3 class="subsection-title">Fama-MacBeth annual slopes with HAC standard errors</h3>
      <div class="table-scroll">
        {context["country_size_fama_macbeth_table"]}
      </div>
    </section>

    <section class="section" id="country-size-gmm">
      <div class="section-heading">
        <h2>Lag-IV GMM Robustness</h2>
        <p>This check treats both log population and log GDP per capita as potentially endogenous, then instruments each with its own exact two- and three-year lags. It asks whether the country-size gradient survives an IV-GMM correction, but it does not prove that the lag instruments satisfy exclusion.</p>
      </div>
      <div class="equation-card">
        <h4>Lag-instrument specification</h4>
        <div class="math-line">
          concentration<sub>i,t</sub> =
          &beta; log(population)<sub>i,t</sub>
          + &gamma; log(GDP per capita)<sub>i,t</sub>
          + year FE + &epsilon;<sub>i,t</sub>
        </div>
        <p><strong>Endogenous regressors:</strong> log population and log GDP per capita. <strong>Excluded instruments:</strong> each variable's exact <em>t-2</em> and <em>t-3</em> lags. <strong>Inference:</strong> reporter-country clustered covariance.</p>
        <p>GMM follows <a href="https://larspeterhansen.org/lph_research/large-sample-properties-of-generalized-method-of-moments-estimators/">Hansen (1982)</a>. The lag-instrument caution follows <a href="https://journals.sagepub.com/doi/10.1177/1536867X0900900106">Roodman (2009)</a>, and the trade-diversification/development precedent is <a href="https://econpapers.repec.org/article/tprrestat/v_3a93_3ay_3a2011_3ai_3a2_3ap_3a590-605.htm">Cadot, Carrere, and Strauss-Kahn (2011)</a>.</p>
      </div>
      <h3 class="subsection-title">GMM coefficient table</h3>
      <div class="table-scroll">
        {context["country_size_gmm_lag_iv_table"]}
      </div>
      <h3 class="subsection-title">First-stage diagnostics</h3>
      <div class="table-scroll">
        {context["country_size_gmm_lag_iv_first_stage_table"]}
      </div>
    </section>

    <section class="section" id="country-size-size-measures">
      <div class="section-heading">
        <h2>Size-Measure Robustness</h2>
        <p>These keep the year fixed effects and GDP-per-capita control, but replace yearly population with each country's first available log population or average log population.</p>
      </div>
      <div class="table-scroll">
        {context["country_size_robustness_table"]}
      </div>
    </section>

    <section class="section" id="country-size-primary-share">
      <div class="section-heading">
        <h2>Primary Export-Share Control</h2>
        <p>These add a country-year control for the share of exports in HS6 primary products. The strict control covers raw or very lightly processed primary goods; the broad control adds first-stage commodity processing such as refined fuels, pulp, and basic metals.</p>
      </div>
      <div class="equation-card">
        <h4>Added-control specification</h4>
        <div class="math-line">
          concentration<sub>i,t</sub> =
          &beta; log(population)<sub>i,t</sub>
          + &gamma; log(GDP per capita)<sub>i,t</sub>
          + &theta; primary export share<sub>i,t</sub>
          + year FE + &epsilon;<sub>i,t</sub>
        </div>
        <p><strong>Purpose:</strong> check whether the country-size gradient is mostly a commodity-exporter composition effect. HS6 <strong>999999</strong> is excluded from both numerator and denominator before primary shares are computed.</p>
      </div>
      <h3 class="subsection-title">Country-clustered primary-share controls</h3>
      <div class="table-scroll">
        {context["country_size_primary_share_table"]}
      </div>
      <h3 class="subsection-title">Two-way clustered primary-share controls</h3>
      <div class="table-scroll">
        {context["country_size_primary_share_two_way_table"]}
      </div>
      <h3 class="subsection-title">Fama-MacBeth primary-share controls</h3>
      <div class="table-scroll">
        {context["country_size_primary_share_fama_macbeth_table"]}
      </div>
      <h3 class="subsection-title">Primary-share construction diagnostics</h3>
      <div class="table-scroll">
        {context["country_size_primary_share_diagnostics_table"]}
      </div>
    </section>

    <section class="section" id="country-size-yearly">
      <div class="section-heading">
        <h2>Year-by-Year Slopes</h2>
        <p>Each annual regression is a cross-section of countries. The plots show whether the size gradient is stable over time rather than driven by a few years. The 1988 diagnostic is omitted because the rd2 panel has only 8 countries that year.</p>
      </div>
      <div class="figure-row">
        <figure><a class="figure-link" href="assets/figures/country_size_yearly_size_slopes_product.png"><img src="assets/figures/country_size_yearly_size_slopes_product.png" alt="Year-by-year country-size slopes for product concentration"></a><figcaption>Annual log-population slopes for Product Gini, top 1% product share, and top 5% product share.</figcaption></figure>
        <figure><a class="figure-link" href="assets/figures/country_size_yearly_size_slopes_partner.png"><img src="assets/figures/country_size_yearly_size_slopes_partner.png" alt="Year-by-year country-size slopes for partner concentration"></a><figcaption>Annual log-population slopes for Partner Gini, top 1% partner share, and top 5% partner share.</figcaption></figure>
      </div>
      <div class="table-scroll">
        {context["country_size_yearly_summary_table"]}
      </div>
    </section>

    <section class="section" id="country-size-diagnostics">
      <div class="section-heading">
        <h2>Diagnostics and Downloads</h2>
        <p>The sample diagnostics table records the country-year coverage, missing-control checks, and duplicate-key check used by the runner.</p>
      </div>
      <div class="table-scroll">
        {context["country_size_diagnostics_table"]}
      </div>
      <div class="download-grid compact-downloads">
        <a href="assets/downloads/country_size_effect_main_models.csv">Main models CSV</a>
        <a href="assets/downloads/country_size_effect_robustness_models.csv">Size robustness CSV</a>
        <a href="assets/downloads/country_size_effect_two_way_cluster_models.csv">Two-way cluster CSV</a>
        <a href="assets/downloads/country_size_effect_fama_macbeth_models.csv">Fama-MacBeth CSV</a>
        <a href="assets/downloads/country_size_effect_gmm_lag_iv_models.csv">Lag-IV GMM CSV</a>
        <a href="assets/downloads/country_size_effect_gmm_lag_iv_first_stage.csv">Lag-IV GMM first-stage CSV</a>
        <a href="assets/downloads/country_size_effect_primary_share_control_models.csv">Primary-share controls CSV</a>
        <a href="assets/downloads/country_size_effect_primary_share_two_way_cluster_models.csv">Primary-share two-way CSV</a>
        <a href="assets/downloads/country_size_effect_primary_share_fama_macbeth_models.csv">Primary-share Fama-MacBeth CSV</a>
        <a href="assets/downloads/country_size_effect_primary_export_share_diagnostics.csv">Primary-share diagnostics CSV</a>
        <a href="assets/downloads/country_size_effect_primary_product_hs6_mapping.csv">Primary HS6 mapping CSV</a>
        <a href="assets/downloads/country_size_effect_us_population_counterfactuals.csv">US-to-size counterfactual CSV</a>
        <a href="assets/downloads/country_size_effect_yearly_slopes.csv">Yearly slopes CSV</a>
        <a href="assets/downloads/country_size_effect_sample_diagnostics.csv">Sample diagnostics CSV</a>
      </div>
    </section>
    """

    growth_effect_body = f"""
    <section class="page-title">
      <div class="eyebrow">Growth effect</div>
      <h1>Export Growth and Concentration</h1>
      <p>This page reports descriptive country-panel tests using the rd2 country sample. The main question is whether lagged real aggregate export growth predicts concentration levels one, five, and ten years later after country and base-year fixed effects.</p>
    </section>

    <section class="section hypothesis-section">
      {context["growth_effect_hypothesis"]}
    </section>

    <section class="section" id="growth-effect-summary">
      <div class="section-heading">
        <h2>Reading the Test</h2>
        {context["growth_effect_takeaways"]}
      </div>
      <div class="equation-card">
        <h4>Main specification</h4>
        <div class="math-line">
          concentration<sub>c,f,b+h</sub> =
          &beta; [log real exports<sub>c,b</sub> - log real exports<sub>c,b-1</sub>]
          + &theta; log real exports<sub>c,b</sub>
          + &delta; log population<sub>c,b</sub>
          + country FE + base-year FE + &epsilon;<sub>c,f,b,h</sub>
        </div>
        <p><strong>Unit:</strong> country-base-year-flow-horizon. <strong>Inference:</strong> main table clusters by reporter country. <strong>Interpretation:</strong> coefficients are associations, not causal effects.</p>
      </div>
    </section>

    <section class="section" id="growth-effect-main">
      <div class="section-heading">
        <h2>Main Models</h2>
        <p>Export growth uses World Bank real exports of goods and services in constant 2015 US dollars. The 1-, 5-, and 10-year columns are estimated on common horizon support to avoid horizon-specific sample selection.</p>
      </div>
      <div class="table-scroll">
        {context["growth_effect_main_table"]}
      </div>
    </section>

    <section class="section" id="growth-effect-sample-comparison">
      <div class="section-heading">
        <h2>Balanced Versus Broad Sample</h2>
        <p>The balanced/common-support rows require every country-flow-base-year to have all requested horizons. The broad rows let each horizon use all available observations with complete controls. Large sign or magnitude changes here would be a sample-selection warning.</p>
      </div>
      <div class="table-scroll">
        {context["growth_effect_sample_comparison_table"]}
      </div>
    </section>

    <section class="section" id="growth-effect-leveling">
      <div class="section-heading">
        <h2>Does the Effect Level Off?</h2>
        <p>The export-level-bin model lets the lagged-growth slope differ across low, middle, and high lagged-export-level terciles. The high-low difference is the direct leveling-off test; the threshold scan is exploratory.</p>
      </div>
      <div class="figure-row">
        <figure><a class="figure-link" href="assets/figures/growth_effect_main_growth_coefficients.png"><img src="assets/figures/growth_effect_main_growth_coefficients.png" alt="Main lagged export-growth coefficients"></a><figcaption>Main lagged real export-growth coefficients by outcome and horizon.</figcaption></figure>
        <figure><a class="figure-link" href="assets/figures/growth_effect_income_bin_slopes.png"><img src="assets/figures/growth_effect_income_bin_slopes.png" alt="Export-level-bin growth slopes"></a><figcaption>Growth slopes by lagged real export-level tercile and horizon.</figcaption></figure>
      </div>
      <h3 class="subsection-title">Export-level-bin slopes</h3>
      <div class="table-scroll">
        {context["growth_effect_income_bin_table"]}
      </div>
      <h3 class="subsection-title">Exploratory threshold scan</h3>
      <div class="table-scroll">
        {context["growth_effect_threshold_table"]}
      </div>
    </section>

    <section class="section" id="growth-effect-robustness">
      <div class="section-heading">
        <h2>Robustness and Placebos</h2>
        <p>The robustness table checks two-way country/year clustering, contemporaneous growth, a future-growth placebo, and region-year fixed effects.</p>
      </div>
      <div class="table-scroll">
        {context["growth_effect_robustness_table"]}
      </div>
    </section>

    <section class="section" id="growth-effect-diagnostics">
      <div class="section-heading">
        <h2>Diagnostics and Downloads</h2>
        <p>The diagnostics table records coverage after World Bank control merges and lag construction.</p>
      </div>
      <div class="table-scroll">
        {context["growth_effect_diagnostics_table"]}
      </div>
      <div class="download-grid compact-downloads">
        <a href="assets/downloads/growth_effect_main_models.csv">Main models CSV</a>
        <a href="assets/downloads/growth_effect_sample_comparison_models.csv">Balanced/broad sample CSV</a>
        <a href="assets/downloads/growth_effect_robustness_models.csv">Robustness CSV</a>
        <a href="assets/downloads/growth_effect_income_bin_slopes.csv">Export-level slopes CSV</a>
        <a href="assets/downloads/growth_effect_threshold_scan.csv">Threshold scan CSV</a>
        <a href="assets/downloads/growth_effect_sample_diagnostics.csv">Sample diagnostics CSV</a>
        <a href="assets/downloads/growth_effect_missing_controls.csv">Missing controls CSV</a>
        <a href="assets/downloads/run_manifest_growth_effect.json">Run manifest JSON</a>
      </div>
    </section>
    """

    future_growth_body = f"""
    <section class="page-title">
      <div class="eyebrow">Future growth</div>
      <h1>Future Export Growth From Trade Concentration</h1>
      <p>This rd2-only page asks whether base-year import or export concentration predicts later real merchandise export growth. The results are descriptive and predictive, not causal.</p>
    </section>

    {context["future_growth_council_takeaways"]}
    {context["future_growth_mechanism_survival"]}

    <section class="section hypothesis-section">
      {context["future_growth_hypothesis"]}
    </section>

    <section class="section" id="future-growth-reading">
      <div class="section-heading">
        <h2>Reading the Test</h2>
        {context["future_growth_takeaways"]}
      </div>
      <div class="equation-card">
        <h4>Main specification</h4>
        <div class="math-line">
          g<sub>c,t,h</sub> =
          &beta; concentration<sub>c,f,d,t</sub>
          + controls<sub>c,t</sub>
          + country FE + year FE + &epsilon;<sub>c,t,h</sub>
        </div>
        <p><strong>Unit:</strong> reporter country, base year, horizon, exposure flow, and concentration dimension. <strong>Outcome:</strong> annualized future Comtrade merchandise export growth deflated to constant 2015 USD with the US GDP deflator. <strong>Controls:</strong> log initial real merchandise exports, oil export share, log real GDP, log population, and log real GNI per capita. <strong>Inference:</strong> main rows cluster by reporter country.</p>
      </div>
      <div class="interpretation-grid">
        <article class="note">
          <h3>Product concentration</h3>
          <p>Unevenness across active HS6 product totals. HS6 <strong>999999</strong> means Commodities not specified, so it is excluded before aggregation.</p>
        </article>
        <article class="note">
          <h3>Partner concentration</h3>
          <p>Unevenness across export destinations or import sources after products are summed into partner totals. HS6 <strong>999999</strong> is kept by the repo's partner-total convention.</p>
        </article>
        <article class="note">
          <h3>Product-partner cell concentration</h3>
          <p>Unevenness across positive HS6-by-partner cells. It is product-dependent, so HS6 <strong>999999</strong> is excluded before aggregation.</p>
        </article>
      </div>
    </section>

    <section class="section" id="future-growth-literature">
      <div class="section-heading">
        <h2>Literature Context</h2>
        <p>The page is framed as a concentration-based companion to the export diversification and extensive-margin literature, not as a causal growth paper.</p>
      </div>
      <ul class="callout-list">
        <li><a href="https://www.aeaweb.org/articles?id=10.1257%2F0002828054201396">Hummels and Klenow (2005)</a> separate extensive and intensive export margins.</li>
        <li><a href="https://archive-ouverte.unige.ch/unige%3A46586">Cadot, Carrere, and Strauss-Kahn</a>, <a href="https://documents1.worldbank.org/curated/en/740431468314706909/pdf/WPS4302.pdf">Brenton and Newfarmer (2007)</a>, <a href="https://econpapers.repec.org/paper/wbkwbrwps/4473.htm">Amurgo-Pacheco and Pierola</a>, and <a href="https://www.researchwithrutgers.com/en/publications/the-role-of-extensive-and-intensive-margins-and-export-growth/">Besedes and Prusa (2011)</a> motivate product, market, and relationship-margin growth channels.</li>
        <li><a href="https://www.nber.org/papers/w11905">Hausmann, Hwang, and Rodrik</a> connect export composition to growth, while import-input work such as <a href="https://www.gov.uk/research-for-development-outputs/imported-intermediate-inputs-and-export-diversification-in-low-income-countries">Benguria</a> motivates import-side concentration as an input-supply exposure.</li>
      </ul>
      <p class="source-note">Cross-links: <a href="extension.html#growth-buckets">Exercise 2</a> is the earlier export-only bucket version; <a href="exercise-12.html">Exercise 12</a> decomposes where export growth comes from.</p>
    </section>

    <section class="section" id="future-growth-buckets">
      <div class="section-heading">
        <h2>Descriptive Buckets</h2>
        <p>Countries are split each year into high/low product and partner concentration buckets by exposure flow. The table reports raw future export growth and a base-size-adjusted version that removes fitted variation from initial exports and macro size controls.</p>
      </div>
      <div class="figure-row">
        <figure><a class="figure-link" href="assets/figures/future_growth_bucket_summary_growth.png"><img src="assets/figures/future_growth_bucket_summary_growth.png" alt="Size-adjusted future export growth by concentration bucket"></a><figcaption>Size-adjusted mean annualized future export growth by bucket, horizon, and exposure flow.</figcaption></figure>
        <figure><a class="figure-link" href="assets/figures/future_growth_continuous_coefficients.png"><img src="assets/figures/future_growth_continuous_coefficients.png" alt="Continuous concentration coefficients"></a><figcaption>Main continuous concentration coefficients across horizons.</figcaption></figure>
      </div>
      <div class="table-scroll">
        {context["future_growth_bucket_table"]}
      </div>
      <h3 class="subsection-title">Bucket regression rows</h3>
      <div class="table-scroll">
        {context["future_growth_bucket_model_table"]}
      </div>
    </section>

    <section class="section" id="future-growth-main">
      <div class="section-heading">
        <h2>Main Continuous Models</h2>
        <p>These rows use Gini measures and country/year fixed effects. Raw p-values below 0.05 are highlighted separately from BH q-values.</p>
      </div>
      <div class="table-scroll">
        {context["future_growth_continuous_table"]}
      </div>
    </section>

    <section class="section" id="future-growth-paired">
      <div class="section-heading">
        <h2>Paired Product and Partner Models</h2>
        <p>These specifications include product concentration, partner concentration, and their interaction for the same exposure flow and metric.</p>
      </div>
      <div class="table-scroll">
        {context["future_growth_paired_table"]}
      </div>
    </section>

    <section class="section" id="future-growth-robustness">
      <div class="section-heading">
        <h2>Robustness</h2>
        <p>Checks include oil-excluded real export growth, lagged real export growth controls, region-year fixed effects, and two-way country/year clustered standard errors. The displayed robustness rows are 5-year Gini checks; full CSVs include all horizons and metrics.</p>
      </div>
      <div class="table-scroll">
        {context["future_growth_robustness_table"]}
      </div>
    </section>

    <section class="section" id="future-growth-examples">
      <div class="section-heading">
        <h2>Country Examples</h2>
        <p>For each exposure flow and horizon, the runner records the largest positive and negative future-growth examples. The page shows the 5-year rows.</p>
      </div>
      <div class="table-scroll">
        {context["future_growth_examples_table"]}
      </div>
    </section>

    <section class="section" id="future-growth-diagnostics">
      <div class="section-heading">
        <h2>Diagnostics and Downloads</h2>
        <p>The diagnostics table records rd2 coverage, duplicate-key checks, missing-control rows, and the HS6 999999 conventions used by the runner.</p>
      </div>
      <div class="table-scroll">
        {context["future_growth_diagnostics_table"]}
      </div>
      <h3 class="subsection-title">Missing required controls by flow and horizon</h3>
      <div class="table-scroll">
        {context["future_growth_missing_controls_table"]}
      </div>
      <div class="download-grid compact-downloads">
        <a href="assets/downloads/future_growth_concentration_panel.csv">Main panel CSV</a>
        <a href="assets/downloads/future_growth_bucket_summary.csv">Bucket summary CSV</a>
        <a href="assets/downloads/future_growth_country_examples.csv">Country examples CSV</a>
        <a href="assets/downloads/future_growth_bucket_models.csv">Bucket models CSV</a>
        <a href="assets/downloads/future_growth_continuous_models.csv">Continuous models CSV</a>
        <a href="assets/downloads/future_growth_paired_models.csv">Paired models CSV</a>
        <a href="assets/downloads/future_growth_robustness_models.csv">Robustness models CSV</a>
        <a href="assets/downloads/future_growth_base_size_bin_summary.csv">Base-size bins CSV</a>
        <a href="assets/downloads/future_growth_base_size_sensitivity_models.csv">Base-size sensitivity CSV</a>
        <a href="assets/downloads/future_growth_mechanism_channel_panel.csv">Mechanism panel CSV</a>
        <a href="assets/downloads/future_growth_mechanism_channel_models.csv">Mechanism models CSV</a>
        <a href="assets/downloads/future_growth_mechanism_summary.csv">Mechanism summary CSV</a>
        <a href="assets/downloads/future_growth_mechanism_diagnostics.csv">Mechanism diagnostics CSV</a>
        <a href="assets/downloads/future_growth_leave_one_country_out_influence.csv">Influence CSV</a>
        <a href="assets/downloads/future_growth_sample_diagnostics.csv">Diagnostics CSV</a>
        <a href="assets/downloads/future_growth_missing_controls.csv">Missing controls CSV</a>
        <a href="assets/downloads/run_manifest_future_growth_concentration.json">Run manifest JSON</a>
      </div>
    </section>
    """

    partner_stability_body = f"""
    <section class="page-title">
      <div class="eyebrow">Partner-Gini stability</div>
      <h1>Partner Gini Is Mostly Stable, With Exceptions</h1>
      <p>This rd2-only page tests whether Partner Gini moves slowly within countries over time. The answer is yes for the cross-country median and most country-flow series, but not literally for every country.</p>
    </section>

    <section class="section hypothesis-section">
      {context["partner_stability_hypothesis"]}
    </section>

    <section class="section" id="partner-stability-reading">
      <div class="section-heading">
        <h2>Reading the Test</h2>
        {context["partner_stability_takeaways"]}
      </div>
      {context["partner_stability_stat_cards"]}
      <div class="equation-card">
        <h4>Common trend specification</h4>
        <div class="math-line">
          PartnerGini<sub>c,t</sub> =
          &beta; trend<sub>t</sub>
          + country FE + &epsilon;<sub>c,t</sub>
        </div>
        <p><strong>Unit:</strong> country-year-flow. <strong>Inference:</strong> common-trend rows cluster standard errors by reporter country. <strong>Practical margin:</strong> a country-flow series is called slope-stable when its fitted absolute 10-year Partner-Gini change is at most 0.02.</p>
      </div>
      <div class="interpretation-grid">
        <article class="note">
          <h3>Partner measure</h3>
          <p>Products are summed into destination or source country totals before concentration is computed. HS6 <strong>999999</strong> is included in partner totals by convention because product identity is not part of this measure.</p>
        </article>
        <article class="note">
          <h3>What the test can say</h3>
          <p>The result is a descriptive stability check. It can support a claim about slow within-country movement in the modern rd2 panel; it is not a causal model and does not explain why exceptions move.</p>
        </article>
        <article class="note">
          <h3>Historical extension caution</h3>
          <p>The historical 1900-onward question is harder because expanding partner coverage can mechanically look like falling concentration. Historical graphs need partner counts, coverage ratios, source regimes, boundary flags, residual-mass bounds, and synthetic censoring checks before they become results.</p>
        </article>
      </div>
    </section>

    <section class="section" id="partner-stability-figures">
      <div class="section-heading">
        <h2>Distribution and Exceptions</h2>
        <p>The slope distribution shows the typical country-flow movement; the endpoint-change figure highlights the largest exceptions.</p>
      </div>
      <div class="figure-row">
        <figure><a class="figure-link" href="assets/figures/partner_stability_country_slope_distribution.png"><img src="assets/figures/partner_stability_country_slope_distribution.png" alt="Distribution of country-specific Partner-Gini slopes"></a><figcaption>Country-specific fitted 10-year Partner-Gini changes, by flow and test window.</figcaption></figure>
        <figure><a class="figure-link" href="assets/figures/partner_stability_largest_endpoint_changes.png"><img src="assets/figures/partner_stability_largest_endpoint_changes.png" alt="Largest Partner-Gini endpoint changes"></a><figcaption>Largest absolute first-to-last Partner-Gini changes in the main window.</figcaption></figure>
      </div>
    </section>

    <section class="section" id="partner-stability-summary">
      <div class="section-heading">
        <h2>Country-Level Stability Summary</h2>
        <p>The main window excludes the partial 2025 tail. The balanced window requires full country-flow coverage from 2001 through 2021.</p>
      </div>
      <div class="table-scroll">
        {context["partner_stability_summary_table"]}
      </div>
    </section>

    <section class="section" id="partner-stability-common-trend">
      <div class="section-heading">
        <h2>Common Trend and Year Effects</h2>
        <p>Common time movement is tested separately from persistent country differences. The common-trend table reports raw p-values and BH q-values; the variance table asks how much explanatory power year fixed effects add after country fixed effects.</p>
      </div>
      <h3 class="subsection-title">Common trend models</h3>
      <div class="table-scroll">
        {context["partner_stability_common_trend_table"]}
      </div>
      <h3 class="subsection-title">Country fixed effects versus country plus year fixed effects</h3>
      <div class="table-scroll">
        {context["partner_stability_variance_table"]}
      </div>
    </section>

    <section class="section" id="partner-stability-low-active">
      <div class="section-heading">
        <h2>Low Active-Partner Sensitivity</h2>
        <p>This check drops reporter-year-flow observations with fewer than 10 active partners, then recomputes the country-flow stability summary. It treats very low partner counts as coverage warnings rather than automatic data errors.</p>
      </div>
      <div class="table-scroll">
        {context["partner_stability_low_active_table"]}
      </div>
    </section>

    <section class="section" id="partner-stability-exceptions">
      <div class="section-heading">
        <h2>Largest Country Exceptions</h2>
        <p>These are the main-window country-flow rows with the largest absolute endpoint changes. Raw p-values and BH q-values are reported for country-specific slope tests; active-partner counts flag cases where endpoint movement may partly reflect coverage changes.</p>
      </div>
      <div class="table-scroll">
        {context["partner_stability_exception_table"]}
      </div>
    </section>

    <section class="section" id="partner-stability-diagnostics">
      <div class="section-heading">
        <h2>Diagnostics and Downloads</h2>
        <p>The manifest records the source table, windows, row count, and partner-concentration convention.</p>
      </div>
      <div class="table-scroll">
        {context["partner_stability_manifest_table"]}
      </div>
      <div class="download-grid compact-downloads">
        <a href="assets/downloads/partner_gini_stability_country_flow.csv">Country-flow stability CSV</a>
        <a href="assets/downloads/partner_gini_stability_summary.csv">Summary CSV</a>
        <a href="assets/downloads/partner_gini_stability_common_trend_models.csv">Common-trend models CSV</a>
        <a href="assets/downloads/partner_gini_stability_variance_decomposition.csv">Variance decomposition CSV</a>
        <a href="assets/downloads/partner_gini_stability_low_active_partner_sensitivity.csv">Low-active-partner sensitivity CSV</a>
        <a href="assets/downloads/partner_gini_stability.md">Stability memo</a>
        <a href="assets/downloads/partner_gini_stability_adversarial_review.md">Adversarial review</a>
        <a href="assets/downloads/run_manifest_partner_gini_stability.json">Run manifest JSON</a>
      </div>
    </section>
    """

    prof_p_body = f"""
    <section class="page-title">
      <div class="eyebrow">Prof P 33-country sample, 2001</div>
      <h1>Top Product Shares and Table 2 Comparison</h1>
      <p>This page is fixed to the paper's 33-country 2001 HS6 sample. It is separate from the default website sample used on the other tabs.</p>
    </section>

    <section class="section" id="prof-p-summary">
      <div class="section-heading">
        <h2>What This Tab Compares</h2>
        {context["prof_p_takeaways"]}
      </div>
      <div class="note">
        <p><strong>Top 1% and top 5% product share:</strong> sort active positive HS6 product totals from largest to smallest, take the largest <code>ceil(p x active products)</code> products, and divide their value by total trade value. Higher values mean a smaller set of products accounts for more exports or imports.</p>
        <p><strong>Direct paper comparison:</strong> Professor P Table 2 reports product Ginis and active-product counts for these countries. It does not report top-1% or top-5% product shares for all 33 countries, so those share columns are modern computed diagnostics.</p>
      </div>
    </section>

    <section class="section tool-section" id="prof-p-lorenz">
      <div class="tool-header">
        <div>
          <h2>Lorenz Curves for India, China, and the United States</h2>
          <p>The curve shows cumulative trade value against cumulative active HS6 products after the same Table 2-style processing used in the table below.</p>
        </div>
        <div class="controls compact">
          <label>Flow <select id="prof-p-lorenz-flow"><option>Exports</option><option>Imports</option></select></label>
        </div>
      </div>
      <div id="prof-p-lorenz-chart" class="chart tall"></div>
      <div id="prof-p-lorenz-cards" class="mini-card-grid"></div>
      <h3 class="subsection-title">Values Used in These Curves</h3>
      {context["prof_p_lorenz_summary_table"]}
    </section>

    <section class="section" id="prof-p-table">
      <div class="section-heading">
        <h2>All Countries</h2>
        <p>Click a column header to sort. Shares are modern HS6 diagnostics; the Gini and product-count columns compare directly to Professor P Table 2.</p>
      </div>
      <div class="table-scroll">
        {context["prof_p_top_share_table"]}
      </div>
      <div class="download-grid compact-downloads">
        <a href="assets/downloads/prof_p_2001_hs6_top_shares_vs_table2.csv">Download top-share comparison CSV</a>
        <a href="assets/downloads/prof_p_2001_lorenz_india_china_us.csv">Download Lorenz points CSV</a>
        <a href="assets/downloads/prof_p_data_processing_cookbook.pdf">Download processing cookbook PDF</a>
      </div>
    </section>
    """

    world_gini_body = f"""
    <section class="page-title">
      <div class="eyebrow">World-relative export benchmark</div>
      <h1>World-Relative Product Gini</h1>
      <p>This page keeps the world-trade benchmarked export concentration measure separate from the main concentration pages while it is still being evaluated.</p>
    </section>

    {context["world_relative_methods_section"]}
    """

    download_links = "".join(
        f'<a href="assets/downloads/{name}">{name}</a>'
        for name in site_download_sources()
        if not is_world_relative_artifact_name(name)
    )

    literature_body = context["literature_takeaways"]
    cadot_hump_body = context.get("cadot_hump_body", "")
    contributions_body = context.get("contributions_body", "")

    methods_body = f"""
    <section class="page-title">
      <div class="eyebrow">Definitions and data</div>
      <h1>Methods, Coverage, and Downloads</h1>
      <p>The site is static, but it is generated from a reproducible Python script and a fixed set of local result artifacts.</p>
    </section>

    <section class="section two-col" id="definitions">
      <article>
        <h2>Coverage</h2>
        <p>The full available Exercise 1 panel covers {context["sample_country_count"]} countries, annual observations from {context["sample_year_min"]} through {context["sample_year_max"]}, and two flows: exports and imports. It is an available-observation panel, not a balanced panel.</p>
        <p>The more stable benchmark window is {context["stable_window_start"]}-{context["stable_window_end"]}: year-flow coverage ranges from {context["stable_min_reporters_per_year_flow"]} to {context["stable_max_reporters_per_year_flow"]} reporters, and {context["stable_balanced_countries_both_flows"]} countries appear in every year for both exports and imports. World-relative and several mechanism checks use this balanced-window logic rather than the thin endpoint years.</p>
        {context["countries_table"]}
      </article>
      <article>
        <h2>Definitions</h2>
        <ul class="callout-list">
          <li><strong>Active Product Gini:</strong> concentration across observed positive HS6 product totals within a country-year-flow; absent or zero-trade products are outside the Gini universe.</li>
          <li><strong>Active Partner Gini:</strong> concentration across observed positive destination or source partner totals within a country-year-flow; absent or zero-trade partners are outside the Gini universe.</li>
          <li><strong>Active Product-partner cell Gini:</strong> concentration across observed positive HS6 product-by-partner cells within a country-year-flow; this is not a zero-inclusive universe measure.</li>
          <li><strong>Within-product supplier HHI:</strong> concentration across supplier countries inside one importer-year-HS6 product.</li>
          <li><strong>Partner-Gini counterfactual:</strong> recomputes Partner Gini after each identified HS6 product is split equally across its observed suppliers; HS6 999999 stays in partner totals but is not treated as a product.</li>
          <li><strong>Full-diffusion upper bound:</strong> recomputes Partner Gini after each HS6 product is split equally across every active partner in the importer-year.</li>
          <li><strong>Lumpy-product exclusions:</strong> HS27 oil/mineral fuels, HS71 precious stones/metals, HS88 aircraft, HS89 ships, and HS93 arms.</li>
          <li><strong>HS2-preserving benchmark:</strong> randomizes within broad HS2 sectors while preserving HS2 totals and active HS6 counts; it is a conditional benchmark, not complete randomization.</li>
        </ul>
      </article>
    </section>

    {context["methods_hs6_section"]}

    <section class="section" id="world-relative-product-gini-method">
      <div class="section-heading">
        <h2>World-Relative Product Gini</h2>
        <p>This export-only measure asks whether a country's LT/HGL-weighted HS1992 product-family basket is uneven relative to the product composition of world trade, not merely unequal across the country's own active product codes.</p>
      </div>
      <div class="equation-card">
        <h4>Question</h4>
        <p>Is the country unusually tilted relative to the world product basket?</p>
      </div>

      <h3 class="subsection-title" id="wrpg-short-answer">Short Answer</h3>
      <p>A conventional Product Gini treats product codes as equal-sized slots. That is a useful first pass, but it makes a small product category and a massive product category count symmetrically as classification units. The World-Relative Product Gini changes the comparison set. It asks: after giving each product family the weight it has in leave-one-out world exports, how uneven are this country's relative export intensities?</p>
      <p class="source-note">If a country exports every product family in exactly the same proportions as the leave-one-out world basket, every relative intensity equals 1 and the World-Relative Product Gini is 0. The index rises when a country's export basket is concentrated in products that are much larger in that country than in the world benchmark, or when it is thin in large world products.</p>

      <h3 class="subsection-title" id="wrpg-motivation">Why A Product-Code Gini Is Not Enough</h3>
      <p>The motivating diagnostic is the mismatch between an HS section's share of distinct HS6 export products and its share of export value. If product codes were all similarly important economic slots, the points in the scatter would sit near the 45-degree line. They do not.</p>
      <div class="figure-row full-width">
        <figure><a class="figure-link" href="assets/figures/world_relative_hs_section_line_value_shares.png"><img src="assets/figures/world_relative_hs_section_line_value_shares.png" alt="HS section shares of export lines versus export value for rd2 countries in 2021"></a><figcaption>HS section shares of export lines versus export value for rd2 countries in 2021. Each point is one HS section. HS6 999999 is excluded before aggregation.</figcaption></figure>
      </div>
      <p>In rd2 country exports in 2021, Section 16, machinery and electrical equipment, has 14.5% of distinct HS6 export lines but 28.9% of export value. Section 11, textiles, has 14.8% of lines but only 4.0% of export value. Counting HS6 lines equally therefore gives textiles and machinery roughly equal classification mass, even though they carry very different export-value mass.</p>
      <p>That is the reason for using a world-weighted benchmark. A product family that is large in world trade gets a large benchmark weight. A small product family does not become important just because the classification system gives it a separate code.</p>
      <div class="table-scroll" aria-label="Largest section-share gaps">
        <table>
          <thead>
            <tr>
              <th>HS section</th>
              <th>Section label</th>
              <th>Line share</th>
              <th>Export value share</th>
              <th>Value minus line share</th>
            </tr>
          </thead>
          <tbody>
            <tr><td>16</td><td>Machinery and electrical equipment</td><td>14.5%</td><td>28.9%</td><td>+14.4 pp</td></tr>
            <tr><td>11</td><td>Textiles and textile articles</td><td>14.8%</td><td>4.0%</td><td>-10.8 pp</td></tr>
            <tr><td>5</td><td>Mineral products</td><td>2.7%</td><td>11.4%</td><td>+8.6 pp</td></tr>
            <tr><td>17</td><td>Vehicles, aircraft, vessels</td><td>2.7%</td><td>9.6%</td><td>+7.0 pp</td></tr>
          </tbody>
        </table>
      </div>

      <h3 class="subsection-title" id="wrpg-formula">Formal Construction</h3>
      <p>Let x<sub>cpt</sub> be exports by rd2 country c, product family p, and year t. Let B<sub>pt</sub> be same-year total benchmark exports of product family p in <code>world_broad</code>. A separate world export basket is constructed for each year t; the 2000 index is benchmarked to the 2000 world product mix, the 2024 index is benchmarked to the 2024 world product mix, and so on. The benchmark is leave-one-out, so country c's own exports are subtracted from the world benchmark before weights are formed.</p>
      <div class="equation-card">
        <h4>Main measure</h4>
        <div class="math-line">
          B<sub>pt</sub> = &Sigma;<sub>j in world_broad</sub> x<sub>jpt</sub>
          &nbsp; is recomputed separately for each year t.
        </div>
        <div class="math-line">
          s<sub>cpt</sub> = x<sub>cpt</sub> / &Sigma;<sub>q</sub>x<sub>cqt</sub>
        </div>
        <div class="math-line">
          P<sup>+</sup><sub>ct</sub> = {{p : B<sub>pt</sub> - x<sub>cpt</sub> &gt; 0}}
        </div>
        <div class="math-line">
          w<sub>-c,pt</sub> =
          (B<sub>pt</sub> - x<sub>cpt</sub>) /
          &Sigma;<sub>q in P<sup>+</sup><sub>ct</sub></sub>(B<sub>qt</sub> - x<sub>cqt</sub>)
        </div>
        <div class="math-line">
          r<sub>cpt</sub> = s<sub>cpt</sub> / w<sub>-c,pt</sub>
        </div>
        <div class="math-line">
          WorldRelativeGini<sub>ct</sub> =
          weighted_gini(r<sub>cpt</sub>, w<sub>-c,pt</sub>) over p in P<sup>+</sup><sub>ct</sub>.
        </div>
      </div>
      <p>The weighted Gini is computed over nonnegative relative intensities with positive benchmark weights. With normalized weights, the conceptual expression is:</p>
      <div class="equation-card">
        <div class="math-line">
          G<sub>w</sub>(r) =
          &Sigma;<sub>i</sub>&Sigma;<sub>j</sub>w<sub>i</sub>w<sub>j</sub>|r<sub>i</sub> - r<sub>j</sub>| / 2&mu;<sub>w</sub>,
          &nbsp; &mu;<sub>w</sub> = &Sigma;<sub>i</sub>w<sub>i</sub>r<sub>i</sub>,
          &nbsp; &Sigma;<sub>i</sub>w<sub>i</sub> = 1.
        </div>
      </div>
      <ol class="callout-list">
        <li>Compute the country's export share in each product family.</li>
        <li>Compute that product family's share in the rest-of-world benchmark.</li>
        <li>Divide the first share by the second.</li>
        <li>A value of 1 means the country exports the product in exactly the world-normal proportion.</li>
        <li>A value above 1 means the country is overweight in that product relative to the benchmark; a value below 1 means it is underweight.</li>
        <li>The Gini then summarizes how uneven those relative intensities are, giving larger world products larger weight.</li>
      </ol>
      <p class="source-note">This is Balassa-style revealed comparative advantage logic: compare a product's share in a country export basket to that product's share in the world export basket (<a href="https://doi.org/10.1111/j.1467-9957.1965.tb00050.x">Balassa 1965</a>). The index differs in two ways: the benchmark is leave-one-out <code>world_broad</code> exports, so the country itself does not enter its own world basket and large exporters do not get mechanically smaller Ginis from pulling the benchmark toward their own product mix; and the full vector of product-level relative intensities is summarized with a weighted Gini rather than reported as product-by-product RCA values.</p>

      <h3 class="subsection-title" id="wrpg-weighting">Why Weighting Is A Standard Move</h3>
      <div class="stat-grid">
        <article class="stat-card"><span>Survey-weight analogy</span><strong>World shares as weights</strong><small>A survey-weighted income Gini gives more weight to a sampled household that represents more people. Here, a product family receives more weight when it represents a larger share of leave-one-out world exports.</small></article>
        <article class="stat-card"><span>Economic slots, not code slots</span><strong>World trade mass</strong><small>Cars, machinery, oil, and electronics get more benchmark mass than tiny product categories. That prevents the HS codebook from becoming the implicit weighting scheme.</small></article>
      </div>

      <h3 class="subsection-title" id="wrpg-implementation">Implementation Details</h3>
      <p>The official website-facing version is export-only, uses the <code>rd2_countries</code> country sample, and is balanced over 2000-2024. The final panel has 55 countries observed in all 25 years, for 1,375 country-years. The all-available rd2 input has 60 countries somewhere in the period, but the balanced panel intentionally drops countries without full 2000-2024 coverage.</p>
      <div class="table-scroll">
        <table>
          <thead>
            <tr><th>Data lineage</th><th>Guardrails</th></tr>
          </thead>
          <tbody>
            <tr>
              <td>
                <ol>
                  <li>Start from Comtrade final annual HS bulk files.</li>
                  <li>Keep export flows and non-world partner rows.</li>
                  <li>Aggregate to reporter-year-classification-HS6 product export values.</li>
                  <li>Drop HS6 <code>999999</code>, "Commodities not specified", before product aggregation.</li>
                  <li>Convert product codes into LT/HGL-weighted HS1992 product families.</li>
                  <li>Aggregate to reporter-year-product-family exports.</li>
                  <li>Build same-year <code>world_broad</code> product-family benchmark exports.</li>
                  <li>For each rd2 country-year, subtract the focal country's exports from the world benchmark.</li>
                  <li>Compute the weighted Gini of relative intensities.</li>
                </ol>
              </td>
              <td>
                <ul>
                  <li><code>999999</code> is blocked in rd2 product aggregates, benchmark aggregates, and generated outputs.</li>
                  <li>The country-product vector is outer-merged with the world benchmark so absent products enter with country share zero.</li>
                  <li>Products with zero leave-one-out world weight are excluded from the ratio and recorded as <code>zero_weight_country_export_share</code>.</li>
                  <li>Negative leave-one-out weights would invalidate the country-year metric; diagnostics report zero such products.</li>
                  <li>The benchmark is <code>world_broad</code>, not rd2 countries reused as their own benchmark.</li>
                </ul>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <h3 class="subsection-title" id="wrpg-evidence">Evidence That The Measure Is Behaving Sensibly</h3>
      <div class="stat-grid">
        <article class="stat-card"><span>Highest 2024 values</span><strong>Zimbabwe 0.991</strong><small>Burkina Faso 0.988; Mozambique 0.981; Iceland 0.980; Uganda 0.970.</small></article>
        <article class="stat-card"><span>Lowest 2024 values</span><strong>United States 0.476</strong><small>Germany 0.539; Netherlands 0.589; Spain 0.609; France 0.613.</small></article>
      </div>
      <div class="table-scroll">
        <table>
          <thead>
            <tr><th>Diagnostic</th><th>2000</th><th>2021</th><th>2024</th></tr>
          </thead>
          <tbody>
            <tr><td>Countries in balanced panel</td><td>55</td><td>55</td><td>55</td></tr>
            <tr><td>Median World-Relative Product Gini</td><td>0.839</td><td>0.831</td><td>0.836</td></tr>
            <tr><td>Median active Product Gini on same country-years</td><td>0.926</td><td>0.943</td><td>0.939</td></tr>
            <tr><td>Benchmark product families</td><td>5,165</td><td>5,296</td><td>5,632</td></tr>
          </tbody>
        </table>
      </div>
      <h4 class="subsection-title">Contribution diagnostics for small countries</h4>
      <p>The contribution diagnostic asks what changes most when a product is removed from the weighted-Gini calculation. Because a Gini is nonlinear, these leave-one-out contributions are not additive structural shares. They are still useful for checking whether high values come only from tiny niche products or from large benchmark products.</p>
      <div class="table-scroll">
        <table>
          <thead>
            <tr><th>Driver bucket among latest-year small countries</th><th>Mean positive contribution share</th><th>Interpretation</th></tr>
          </thead>
          <tbody>
            <tr><td>Underweight large world products</td><td>31.6%</td><td>Large benchmark products where the country has little or no corresponding export share.</td></tr>
            <tr><td>Overweight large world products</td><td>25.4%</td><td>Large benchmark products where the country is heavily specialized relative to world weights.</td></tr>
            <tr><td>Underweight other products</td><td>15.4%</td><td>Smaller or mid-sized benchmark products with low country intensity.</td></tr>
            <tr><td>Missing large world products</td><td>13.2%</td><td>Large world product families absent from the country's export basket.</td></tr>
            <tr><td>Overweight mid-world products</td><td>13.0%</td><td>Mid-sized world products where the country is above benchmark intensity.</td></tr>
            <tr><td>Overweight niche products</td><td>1.4%</td><td>Tiny world products where the country has unusually high intensity.</td></tr>
          </tbody>
        </table>
      </div>
      <p class="source-note">Validation recomputed the World-Relative Product Gini from contribution inputs with maximum absolute difference 0.0 over 1,375 country-years, 55 countries, and 25 years.</p>
    </section>

    <section class="section" id="downloads">
      <div class="section-heading">
        <h2>Downloadable Tables</h2>
      </div>
      <div class="download-grid">
        {download_links}
      </div>
    </section>
    """

    pages = {
        "index.html": layout("Trade Concentration Brief", "overview", index_body),
        "extension.html": layout("Extending the 2001 Trade Concentration Evidence", "extension", extension_body),
        "imports.html": layout("Import Concentration Mechanisms", "imports", imports_body),
        "literature.html": layout("Lit-Review Takeaways", "literature", literature_body),
        "methods.html": layout("Methods and Downloads", "methods", methods_body),
    }
    if context.get("exercises_index_page"):
        pages["exercises.html"] = context["exercises_index_page"]
    if include_contributions_page() and contributions_body:
        pages["contributions.html"] = layout("Project Contributions", "contributions", contributions_body)
    if include_cadot_hump_page() and cadot_hump_body:
        cadot_page_title = (
            "Cadot Replication Results"
            if ACTIVE_SITE_SAMPLE == "cadot_broad_156"
            else "Behind the Hump"
        )
        pages["cadot-hump.html"] = layout(
            cadot_page_title, "cadot-hump", cadot_hump_body
        )
    if include_world_relative_product_gini():
        pages["world-gini.html"] = layout("World-Relative Product Gini", "world-gini", world_gini_body)
    if include_ex12_extensive_margin():
        pages["exercise-12.html"] = layout("Exercise 12 Export Growth Decomposition", "exercise-12", exercise12_body)
    if include_prof_p_page():
        pages["prof-p.html"] = layout("Prof P 2001 Top Product Shares", "prof-p", prof_p_body)
    if include_country_size_page():
        pages["country-size-effect.html"] = layout("Country Size Effect", "country-size-effect", country_size_body)
    if include_growth_effect_page():
        pages["growth-effect.html"] = layout("Growth Effect", "growth-effect", growth_effect_body)
    if include_future_growth_page():
        pages["future-growth.html"] = layout("Future Growth", "future-growth", future_growth_body)
    if include_partner_stability_page():
        pages["partner-stability.html"] = layout("Partner Gini Stability", "partner-stability", partner_stability_body)
    for filename, html in context.get("_exercise_first_pages", {}).items():
        pages.setdefault(filename, html)
    return pages


def site_css() -> str:
    return """
:root {
  --bg: #fbfbfa;
  --paper: #ffffff;
  --ink: #1f2933;
  --muted: #667085;
  --line: #e2e5e9;
  --accent: #0b6b62;
  --accent-dark: #064e49;
  --blue: #2563eb;
  --gold: #b7791f;
  --shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
}
* { box-sizing: border-box; }
html {
  scroll-padding-top: 112px;
  max-width: 100%;
  overflow-x: hidden;
}
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font: 16px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  max-width: 100%;
  overflow-x: hidden;
}
a { color: inherit; }
.site-header {
  position: sticky;
  top: 0;
  z-index: 10;
  background: rgba(255, 255, 255, 0.94);
  border-bottom: 1px solid var(--line);
}
.header-inner {
  max-width: 1180px;
  margin: 0 auto;
  padding: 14px 22px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}
.brand {
  font-weight: 700;
  text-decoration: none;
}
nav {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}
nav a {
  text-decoration: none;
  color: var(--muted);
  padding: 7px 10px;
  border-radius: 6px;
  font-size: 14px;
}
nav a.active, nav a:hover {
  color: var(--ink);
  background: #eef2f6;
}
main { max-width: 1160px; margin: 0 auto; padding: 24px 22px 56px; }
.section, .page-title, .hero, :target { scroll-margin-top: 112px; }
.hero, .page-title {
  padding: 34px 0 20px;
  border-bottom: 1px solid var(--line);
}
.hero h1, .page-title h1 {
  font-size: 44px;
  line-height: 1.08;
  letter-spacing: 0;
  max-width: 940px;
  margin: 8px 0 14px;
}
.hero p, .page-title p {
  max-width: 860px;
  color: var(--muted);
  font-size: 18px;
}
.eyebrow {
  color: var(--accent-dark);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-size: 12px;
}
.hero-actions { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 24px; }
.button {
  display: inline-flex;
  align-items: center;
  min-height: 42px;
  padding: 10px 14px;
  border: 1px solid var(--line);
  border-radius: 6px;
  text-decoration: none;
  background: var(--paper);
}
.button.primary {
  background: var(--accent);
  border-color: var(--accent);
  color: white;
}
.section { padding: 30px 0; border-bottom: 1px solid var(--line); }
.section-heading {
  display: grid;
  grid-template-columns: minmax(220px, 0.55fr) minmax(260px, 1fr);
  gap: 24px;
  align-items: start;
  margin-bottom: 18px;
}
.section-heading h2, .two-col h2, .tool-header h2 { margin: 0 0 8px; font-size: 24px; line-height: 1.2; }
.section-heading p, .two-col p, .tool-header p { color: var(--muted); margin-top: 0; }
.stat-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}
.stat-card, .note, .equation-card, .selector-panel, .link-grid a, .hypothesis-card {
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 8px;
  box-shadow: var(--shadow);
}
.stat-card { padding: 18px; min-height: 142px; }
.stat-card span, .stat-card small { display: block; color: var(--muted); }
.stat-card strong { display: block; font-size: 36px; line-height: 1; margin: 14px 0; }
.two-col {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 28px;
}
.note { padding: 18px; }
.equation-card {
  padding: 16px 18px;
  margin: 10px 0 16px;
}
.equation-card h4 {
  margin: 0 0 10px;
  color: var(--accent-dark);
  font-size: 14px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.math-line {
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: #f8fafc;
  color: var(--ink);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 14px;
  line-height: 1.7;
  overflow-wrap: anywhere;
}
.equation-card p {
  margin: 10px 0 0;
  color: var(--muted);
  font-size: 14px;
}
.link-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 14px;
}
.link-grid a {
  display: block;
  text-decoration: none;
  padding: 18px;
}
.link-grid span { color: var(--accent); font-weight: 700; }
.link-grid strong { display: block; font-size: 21px; margin: 8px 0; }
.link-grid small { color: var(--muted); }
.hypothesis-section { padding-top: 22px; }
.hypothesis-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}
.hypothesis-card {
  padding: 16px;
}
.hypothesis-kicker {
  color: var(--accent-dark);
  font-weight: 700;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 6px;
}
.hypothesis-card h3 {
  margin: 0 0 12px;
  font-size: 20px;
  line-height: 1.2;
}
.hypothesis-card dl {
  display: grid;
  grid-template-columns: 112px minmax(0, 1fr);
  gap: 8px 12px;
  margin: 0;
}
.hypothesis-card dt {
  color: var(--muted);
  font-weight: 700;
  font-size: 13px;
}
.hypothesis-card dd {
  margin: 0;
  color: var(--ink);
  font-size: 14px;
}
.evidence-links {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}
.evidence-links a {
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 5px 9px;
  color: var(--accent-dark);
  text-decoration: none;
  font-size: 13px;
  background: #f8faf9;
}
.evidence-links a:hover { border-color: var(--accent); }
.evidence-note {
  border: 1px solid var(--line);
  border-left: 4px solid var(--accent);
  border-radius: 8px;
  background: #f8fafc;
  padding: 12px 14px;
  margin: 12px 0 18px;
}
.evidence-note dl {
  display: grid;
  grid-template-columns: 170px minmax(0, 1fr);
  gap: 6px 14px;
  margin: 0;
}
.evidence-note dt {
  color: var(--accent-dark);
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.evidence-note dd {
  margin: 0;
  color: var(--ink);
  font-size: 14px;
}
.result-ladder {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
  margin: 16px 0 20px;
}
.result-ladder article {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--paper);
  padding: 12px;
}
.result-ladder span {
  display: block;
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.result-ladder strong {
  display: block;
  margin: 6px 0;
  color: var(--accent-dark);
  font-size: 18px;
  line-height: 1.15;
}
.result-ladder p {
  color: var(--muted);
  font-size: 13px;
  margin: 0;
}
.interpretation-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin: 18px 0;
}
.next-step-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  margin: 18px 0;
}
.subsection-title {
  margin: 24px 0 10px;
  font-size: 18px;
}
.callout-list { margin: 0; padding-left: 18px; color: var(--ink); }
.callout-list li { margin: 8px 0; }
.tool-section {
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 22px;
  margin-top: 26px;
}
.tool-header {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: flex-start;
}
.controls {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}
.controls label {
  color: var(--muted);
  font-size: 13px;
  display: grid;
  gap: 4px;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
.year-control {
  min-width: 280px;
  display: grid;
  gap: 6px;
  color: var(--muted);
  font-size: 13px;
}
.year-control-head, .year-range-labels {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
}
.year-control-head span {
  font-weight: 600;
}
#map-year-label, #energy-map-year-label {
  color: var(--ink);
  font-weight: 700;
  font-size: 18px;
}
input[type="range"] {
  width: 100%;
  accent-color: var(--accent);
  cursor: pointer;
}
.control-note {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
}
select, input[type="search"] {
  min-height: 38px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: white;
  color: var(--ink);
  padding: 8px 10px;
  font: inherit;
}
button {
  min-height: 36px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: #f8fafc;
  color: var(--ink);
  padding: 8px 11px;
  cursor: pointer;
}
button:hover { border-color: var(--accent); }
.chart {
  width: 100%;
  min-height: 430px;
  margin: 14px 0;
}
.chart.tall { min-height: 560px; }
.top-goods-block {
  margin: 18px 0 22px;
}
.top-goods-head {
  display: grid;
  grid-template-columns: minmax(220px, 0.45fr) minmax(260px, 1fr);
  gap: 18px;
  align-items: start;
  margin-bottom: 12px;
}
.top-goods-head h3 {
  margin: 0;
  font-size: 20px;
  line-height: 1.2;
}
.top-goods-head p, .source-note {
  margin: 0;
  color: var(--muted);
  font-size: 14px;
}
.source-note {
  margin-top: 10px;
}
.source-note a {
  color: var(--accent-dark);
  font-weight: 600;
}
.top-goods-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.top-goods-card {
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 14px;
  box-shadow: var(--shadow);
}
.top-goods-card h3 {
  margin: 0 0 10px;
  color: var(--accent-dark);
  font-size: 16px;
}
.top-goods-columns {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.top-goods-columns h4 {
  margin: 0 0 6px;
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--muted);
}
.top-goods-columns ol {
  margin: 0;
  padding-left: 20px;
}
.top-goods-columns li {
  margin: 0 0 8px;
  color: var(--ink);
  font-size: 13px;
}
.top-goods-columns li span {
  display: block;
  overflow-wrap: anywhere;
}
.top-goods-columns code {
  color: var(--accent-dark);
  font-size: 12px;
}
.top-goods-columns small {
  display: block;
  color: var(--muted);
  margin-top: 2px;
}
.chart-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin: 12px 0 18px;
}
.tool-grid {
  display: grid;
  grid-template-columns: 270px minmax(0, 1fr);
  gap: 18px;
  align-items: start;
}
.selector-panel { padding: 12px; max-height: 660px; overflow: hidden; }
.selector-actions {
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: 6px;
  margin-bottom: 10px;
}
.country-list {
  display: grid;
  gap: 6px;
  max-height: 570px;
  overflow: auto;
  padding-right: 4px;
}
.country-list label {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--ink);
  font-size: 14px;
}
.detail-box {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #f8fafc;
  padding: 12px;
  color: var(--muted);
}
.driver-dropdown {
  margin-top: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--paper);
  padding: 12px;
}
.driver-dropdown summary {
  cursor: pointer;
  color: var(--ink);
  font-weight: 700;
}
.driver-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 12px;
}
.driver-controls label {
  display: grid;
  gap: 4px;
  color: var(--muted);
  font-size: 13px;
}
.driver-country-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
  gap: 8px 16px;
  margin-top: 12px;
}
.driver-country-group {
  grid-column: 1 / -1;
  margin: 8px 0 4px;
  color: var(--accent-dark);
  font-size: 13px;
}
.driver-country-item {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 10px;
  border-bottom: 1px solid #eef2f6;
  padding: 5px 0;
  min-width: 0;
}
.driver-country-button {
  min-height: 0;
  border: 0;
  background: transparent;
  padding: 0;
  color: var(--ink);
  font: inherit;
  text-align: left;
  overflow-wrap: anywhere;
}
.driver-country-button:hover {
  color: var(--accent-dark);
  text-decoration: underline;
}
.driver-country-meta {
  color: var(--muted);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.rank-bucket-controls {
  justify-content: flex-end;
  max-width: 760px;
}
.rank-bucket-controls label {
  min-width: 170px;
}
.rank-bucket-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(300px, 0.36fr);
  gap: 18px;
  align-items: start;
}
.rank-bucket-main,
.rank-bucket-side {
  min-width: 0;
}
.rank-bucket-scroll {
  max-height: 780px;
  overflow-y: auto;
  overflow-x: hidden;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #ffffff;
}
.rank-bucket-overview {
  margin: 0;
  min-height: 640px;
}
.rank-bucket-side {
  position: sticky;
  top: 96px;
  display: grid;
  gap: 12px;
}
.rank-bucket-side h3 {
  margin: 0;
  font-size: 18px;
  line-height: 1.2;
}
.rank-bucket-focus {
  min-height: 320px;
  margin: 0;
}
.rank-bucket-side .detail-box {
  font-size: 13px;
}
.rank-bucket-detail-title {
  color: var(--ink);
  font-weight: 700;
  margin-bottom: 8px;
}
.rank-bucket-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin: 8px 0 12px;
}
.rank-bucket-metric {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #ffffff;
  padding: 8px;
}
.rank-bucket-metric span {
  display: block;
  color: var(--muted);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.rank-bucket-metric strong {
  display: block;
  margin-top: 3px;
  color: var(--ink);
  font-size: 17px;
}
.rank-bucket-products {
  display: grid;
  gap: 8px;
  margin: 8px 0 0;
  padding: 0;
  list-style: none;
}
.rank-bucket-product {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 6px 10px;
  border-top: 1px solid #e5e7eb;
  padding-top: 8px;
}
.rank-bucket-product:first-child {
  border-top: 0;
  padding-top: 0;
}
.rank-bucket-product-name {
  min-width: 0;
  color: var(--ink);
  font-weight: 650;
  overflow-wrap: anywhere;
}
.rank-bucket-product-code {
  color: var(--muted);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.rank-bucket-product-value {
  grid-column: 1 / -1;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}
.mini-card-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin: 10px 0 18px;
}
.mini-card-grid article {
  border-top: 3px solid var(--accent);
  background: #f8fafc;
  padding: 10px 12px;
}
.mini-card-grid h3 {
  margin: 0 0 6px;
  font-size: 16px;
}
.mini-card-grid p {
  margin: 0;
  color: var(--muted);
  font-size: 13px;
}
.table-scroll {
  width: 100%;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
.table-scroll table {
  min-width: 720px;
}
.main-models-grid {
  display: grid;
  grid-template-columns: minmax(720px, 1fr) minmax(340px, 430px);
  gap: 16px;
  align-items: start;
}
.main-models-grid .table-scroll { min-width: 0; }
.size-counterfactual-card {
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 8px;
  box-shadow: var(--shadow);
  padding: 14px;
}
.size-counterfactual-card h3 {
  margin: 0 0 8px;
  font-size: 18px;
  line-height: 1.2;
}
.size-counterfactual-card p {
  margin: 0 0 12px;
  color: var(--muted);
  font-size: 13px;
}
.counterfactual-table-wrap {
  overflow-x: auto;
  margin: 8px 0 10px;
}
.counterfactual-table {
  display: table;
  table-layout: fixed;
  width: 100%;
  min-width: 0;
  border-radius: 6px;
}
.counterfactual-table thead { display: table-header-group; }
.counterfactual-table tbody { display: table-row-group; }
.counterfactual-table tr { display: table-row; }
.counterfactual-table th,
.counterfactual-table td {
  display: table-cell;
  padding: 7px 6px;
  font-size: 11.5px;
}
.counterfactual-table th {
  white-space: normal;
  line-height: 1.2;
}
.counterfactual-table th:first-child,
.counterfactual-table td:first-child {
  width: 36%;
}
.counterfactual-table th:not(:first-child),
.counterfactual-table td:not(:first-child) {
  text-align: right;
}
.counterfactual-table td strong,
.counterfactual-table td span {
  display: block;
}
.counterfactual-table td span {
  color: var(--muted);
  font-size: 11px;
  line-height: 1.25;
}
.size-counterfactual-card .counterfactual-note {
  margin-bottom: 0;
  font-size: 12px;
}
table {
  width: 100%;
  border-collapse: collapse;
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 8px;
  display: table;
}
thead, tbody, tr { width: 100%; }
th, td {
  text-align: left;
  padding: 8px 10px;
  border-bottom: 1px solid var(--line);
  vertical-align: top;
  font-size: 13px;
}
th { background: #eef2f6; font-weight: 700; white-space: nowrap; }
.sig-row td {
  background: #fff8df;
}
.sig-coef {
  display: inline-block;
  font-weight: 800;
  color: #0f5132;
  background: #d7f4df;
  border-radius: 4px;
  padding: 1px 4px;
  white-space: nowrap;
}
.sig-pvalue {
  display: inline-block;
  font-weight: 800;
  color: #7a3d00;
  background: #ffe8a8;
  border-radius: 4px;
  padding: 1px 4px;
  white-space: nowrap;
}
.sig-qvalue {
  display: inline-block;
  font-weight: 800;
  color: #4a247a;
  background: #eadcff;
  border-radius: 4px;
  padding: 1px 4px;
  white-space: nowrap;
}
.sort-header {
  min-height: 0;
  border: 0;
  background: transparent;
  padding: 0;
  color: inherit;
  font: inherit;
  font-weight: inherit;
  text-align: left;
}
.sort-header:hover { color: var(--accent-dark); }
tbody tr:last-child td { border-bottom: 0; }
.compact-downloads { margin-top: 16px; }
.figure-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-top: 18px;
}
.figure-row.full-width { grid-template-columns: 1fr; }
.figure-row.full-width figure { max-width: 980px; margin: 0 auto; }
.figure-row figure {
  margin: 0;
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 10px;
}
.figure-link { display: block; }
.figure-row img {
  display: block;
  width: 100%;
  height: auto;
  border-radius: 4px;
}
figcaption {
  color: var(--muted);
  font-size: 13px;
  margin-top: 8px;
}
.download-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.download-grid a {
  display: block;
  padding: 12px;
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 6px;
  color: var(--accent-dark);
  overflow-wrap: anywhere;
}
.site-footer {
  max-width: 1180px;
  margin: 0 auto;
  padding: 18px 22px 40px;
  color: var(--muted);
  font-size: 13px;
}
@media (max-width: 860px) {
  .header-inner, .tool-header, .section-heading { display: block; }
  nav { justify-content: flex-start; margin-top: 12px; }
  .stat-grid, .two-col, .link-grid, .hypothesis-grid, .result-ladder, .interpretation-grid, .next-step-grid, .tool-grid, .figure-row, .chart-grid, .download-grid, .top-goods-head, .top-goods-grid, .top-goods-columns, .mini-card-grid, .main-models-grid, .rank-bucket-layout {
    grid-template-columns: 1fr;
  }
  .rank-bucket-side { position: static; }
  .rank-bucket-scroll { max-height: 620px; }
  .hero h1, .page-title h1 { font-size: 32px; }
  .hero p, .page-title p { font-size: 16px; }
  .hypothesis-card dl { grid-template-columns: 1fr; gap: 4px; }
  .evidence-note dl { grid-template-columns: 1fr; }
  .tool-section { padding: 14px; }
  .controls { align-items: stretch; }
  .controls label, .year-control { width: 100%; min-width: 0; }
  .chart, .chart.tall { min-height: 430px; }
  table { overflow-x: auto; }
}
"""


def site_js() -> str:
    return """
(function () {
  const DATA = window.TRADE_GINI_DATA || {};
  const COLORS = ['#0f766e', '#2563eb', '#b7791f', '#dc2626', '#7c3aed', '#0891b2', '#4d7c0f', '#be123c', '#4338ca', '#a16207', '#0f172a', '#ea580c'];
  const config = { responsive: true, displayModeBar: true, displaylogo: false };
  const RANK_BUCKETS = [
    { key: 'top5_share', label: 'Top 5', color: '#1f77b4' },
    { key: 'rank6_50_share', label: 'Ranks 6-50', color: '#ffbf69' },
    { key: 'rank51_200_share', label: 'Ranks 51-200', color: '#8ecae6' },
    { key: 'rank201_plus_share', label: 'Rank 201+ tail', color: '#d1d5db' }
  ];
  const SNAPSHOT_ORDER = { start: 0, mid: 1, end: 2 };
  const SNAPSHOT_REVERSE_ORDER = { end: 0, mid: 1, start: 2 };

  function fmt(value, digits = 3) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return 'n/a';
    return Number(value).toFixed(digits);
  }

  function pct(value, digits = 1) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return 'n/a';
    return (100 * Number(value)).toFixed(digits) + '%';
  }

  function usdShort(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return 'n/a';
    const abs = Math.abs(number);
    if (abs >= 1e12) return '$' + (number / 1e12).toFixed(2) + 'T';
    if (abs >= 1e9) return '$' + (number / 1e9).toFixed(1) + 'B';
    if (abs >= 1e6) return '$' + (number / 1e6).toFixed(1) + 'M';
    return '$' + number.toLocaleString(undefined, { maximumFractionDigits: 0 });
  }

  function byId(id) {
    return document.getElementById(id);
  }

  function escapeHtml(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function relayout() {
    document.querySelectorAll('.js-plotly-plot').forEach((node) => Plotly.Plots.resize(node));
  }

  function setupSortableTables() {
    document.querySelectorAll('table[data-sortable]').forEach((table) => {
      table.querySelectorAll('.sort-header').forEach((button) => {
        button.addEventListener('click', () => {
          const index = Number(button.dataset.sortIndex);
          const type = button.dataset.sortType || 'text';
          const nextDir = table.dataset.sortIndex === String(index) && table.dataset.sortDir === 'asc' ? 'desc' : 'asc';
          const tbody = table.querySelector('tbody');
          const rows = Array.from(tbody.querySelectorAll('tr'));
          rows.sort((a, b) => {
            const av = a.children[index]?.dataset.sortValue ?? '';
            const bv = b.children[index]?.dataset.sortValue ?? '';
            let cmp;
            if (type === 'number') {
              const an = Number(av);
              const bn = Number(bv);
              if (!Number.isFinite(an) && !Number.isFinite(bn)) cmp = 0;
              else if (!Number.isFinite(an)) cmp = 1;
              else if (!Number.isFinite(bn)) cmp = -1;
              else cmp = an - bn;
            } else {
              cmp = av.localeCompare(bv, undefined, { sensitivity: 'base' });
            }
            return nextDir === 'asc' ? cmp : -cmp;
          });
          rows.forEach((row) => tbody.appendChild(row));
          table.dataset.sortIndex = String(index);
          table.dataset.sortDir = nextDir;
        });
      });
    });
  }

  function layout(title, ytitle, xtitle) {
    return {
      title: { text: title, x: 0, xanchor: 'left', font: { size: 18 } },
      margin: { l: 56, r: 24, t: 52, b: 48 },
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: '#ffffff',
      hovermode: 'closest',
      xaxis: { title: xtitle || '', gridcolor: '#e5e7eb', zeroline: false },
      yaxis: { title: ytitle || '', gridcolor: '#e5e7eb', zeroline: false },
      legend: { orientation: 'h', y: -0.2 }
    };
  }

  const EXPORT_WORLD_RELATIVE_METRIC = 'world_relative_product_gini';
  const IMPORT_WORLD_RELATIVE_METRIC = 'world_relative_import_product_gini';

  function selectedFlowForMetric(flowId, metricId) {
    const flowSelect = byId(flowId);
    const metric = byId(metricId)?.value;
    if (metric === EXPORT_WORLD_RELATIVE_METRIC && flowSelect && flowSelect.value !== 'Exports') {
      flowSelect.value = 'Exports';
    }
    if (metric === IMPORT_WORLD_RELATIVE_METRIC && flowSelect && flowSelect.value !== 'Imports') {
      flowSelect.value = 'Imports';
    }
    return flowSelect?.value || 'Exports';
  }

  function rowsFor(flow, metric, year) {
    return (DATA.exercise1?.panel || []).filter((row) => row.flow === flow && Number(row.year) === Number(year) && row[metric] !== null);
  }

  function mapScaleRange(flow, metric) {
    const values = (DATA.exercise1?.panel || [])
      .filter((row) => row.flow === flow && row[metric] !== null)
      .map((row) => Number(row[metric]))
      .filter((value) => Number.isFinite(value));
    if (!values.length) return null;
    const min = Math.min(...values);
    const max = Math.max(...values);
    if (min === max) return null;
    return { min, max };
  }

  function currentMapYear() {
    return byId('map-year-slider')?.value || byId('map-year')?.value;
  }

  function setMapYear(value) {
    const slider = byId('map-year-slider');
    const select = byId('map-year');
    const label = byId('map-year-label');
    if (slider) slider.value = value;
    if (select) select.value = value;
    if (label) label.textContent = value;
  }

  function selectedCountries() {
    return Array.from(document.querySelectorAll('.country-check:checked')).map((el) => el.value);
  }

  function setDetail(row, metric) {
    const box = byId('line-detail');
    if (!box || !row) return;
    box.innerHTML = '<strong>' + row.country + '</strong> (' + row.iso3 + '), ' + row.year + ' ' + row.flow +
      '<br>' + (DATA.labels?.metrics?.[metric] || metric) + ': ' + fmt(row[metric]) +
      '<br>Product Gini (HS6 products): ' + fmt(row.product_gini) +
      ' | Partner Gini: ' + fmt(row.partner_gini) +
      ' | Cell Gini: ' + fmt(row.product_partner_cell_gini);
  }

  function renderMap() {
    const node = byId('world-map');
    if (!node) return;
    const metric = byId('map-metric').value;
    const flow = selectedFlowForMetric('map-flow', 'map-metric');
    const year = currentMapYear();
    const rows = rowsFor(flow, metric, year);
    const scaleRange = mapScaleRange(flow, metric);
    const trace = {
      type: 'choropleth',
      locations: rows.map((r) => r.iso3),
      z: rows.map((r) => r[metric]),
      text: rows.map((r) => r.country),
      customdata: rows,
      colorscale: [
        [0, '#e0f2fe'],
        [0.5, '#2dd4bf'],
        [1, '#0f172a']
      ],
      zauto: !scaleRange,
      zmin: scaleRange?.min,
      zmax: scaleRange?.max,
      colorbar: { title: DATA.labels?.metrics?.[metric] || metric },
      marker: { line: { color: '#ffffff', width: 0.4 } },
      hovertemplate: '<b>%{text}</b><br>Gini: %{z:.3f}<extra></extra>'
    };
    Plotly.react(node, [trace], {
      margin: { l: 0, r: 0, t: 10, b: 0 },
      geo: {
        projection: { type: 'natural earth' },
        showframe: false,
        showcoastlines: true,
        coastlinecolor: '#94a3b8',
        bgcolor: 'rgba(0,0,0,0)'
      },
      paper_bgcolor: 'rgba(0,0,0,0)'
    }, config);
    node.on('plotly_click', (event) => {
      const row = event.points?.[0]?.customdata;
      if (!row) return;
      const check = document.querySelector('.country-check[value="' + row.iso3 + '"]');
      if (check) check.checked = true;
      setDetail(row, metric);
      renderLines();
    });
  }

  function renderCountryList() {
    const list = byId('country-checkboxes');
    if (!list) return;
    const selectedDefaults = new Set(['IND', 'USA', 'CHN', 'DEU', 'JPN']);
    list.innerHTML = '';
    (DATA.countries || []).forEach((country) => {
      const label = document.createElement('label');
      label.dataset.country = (country.country || '').toLowerCase();
      label.dataset.iso3 = country.iso3;
      label.innerHTML = '<input class="country-check" type="checkbox" value="' + country.iso3 + '"' +
        (selectedDefaults.has(country.iso3) ? ' checked' : '') + '> ' + country.country;
      list.appendChild(label);
    });
    list.addEventListener('change', renderLines);
  }

  function filterCountryList() {
    const query = (byId('country-search')?.value || '').toLowerCase();
    document.querySelectorAll('#country-checkboxes label').forEach((label) => {
      const match = label.dataset.country.includes(query) || label.dataset.iso3.toLowerCase().includes(query);
      label.style.display = match ? 'flex' : 'none';
    });
  }

  function renderLines() {
    const node = byId('country-lines');
    if (!node) return;
    const metric = byId('line-metric').value;
    const flow = selectedFlowForMetric('line-flow', 'line-metric');
    const selected = selectedCountries();
    const rows = (DATA.exercise1?.panel || []).filter((row) => row.flow === flow && selected.includes(row.iso3));
    const grouped = new Map();
    rows.forEach((row) => {
      if (!grouped.has(row.iso3)) grouped.set(row.iso3, []);
      grouped.get(row.iso3).push(row);
    });
    const traces = Array.from(grouped.entries()).map(([iso3, group], index) => {
      group.sort((a, b) => Number(a.year) - Number(b.year));
      return {
        type: 'scatter',
        mode: 'lines+markers',
        name: group[0]?.country || iso3,
        x: group.map((r) => r.year),
        y: group.map((r) => r[metric]),
        customdata: group,
        line: { color: COLORS[index % COLORS.length], width: 2 },
        marker: { size: 5 },
        hovertemplate: '<b>%{fullData.name}</b><br>%{x}: %{y:.3f}<extra></extra>'
      };
    });
    Plotly.react(node, traces, layout((DATA.labels?.metrics?.[metric] || metric) + ' over time', 'Gini'), config);
    node.on('plotly_click', (event) => {
      const row = event.points?.[0]?.customdata;
      setDetail(row, metric);
    });
  }

  function energyPanel() {
    return DATA.exercise3?.energy_excluded_import_panel || [];
  }

  function energyRowsForYear(year) {
    return energyPanel().filter((row) => Number(row.year) === Number(year) && row.product_gini_ex_energy !== null);
  }

  function energyMapScaleRange() {
    const values = energyPanel()
      .map((row) => Number(row.product_gini_ex_energy))
      .filter((value) => Number.isFinite(value));
    if (!values.length) return null;
    const min = Math.min(...values);
    const max = Math.max(...values);
    if (min === max) return null;
    return { min, max };
  }

  function currentEnergyMapYear() {
    return byId('energy-map-year-slider')?.value || byId('energy-map-year')?.value;
  }

  function setEnergyMapYear(value) {
    const slider = byId('energy-map-year-slider');
    const select = byId('energy-map-year');
    const label = byId('energy-map-year-label');
    if (slider) slider.value = value;
    if (select) select.value = value;
    if (label) label.textContent = value;
  }

  function selectedEnergyCountries() {
    return Array.from(document.querySelectorAll('.energy-country-check:checked')).map((el) => el.value);
  }

  function setEnergyDetail(row) {
    const box = byId('energy-line-detail');
    if (!box || !row) return;
    box.innerHTML = '<strong>' + row.country + '</strong> (' + row.iso3 + '), ' + row.year + ' Imports' +
      '<br>Product Gini excluding energy: ' + fmt(row.product_gini_ex_energy) +
      '<br>Baseline import Product Gini: ' + fmt(row.baseline_product_gini) +
      ' | Energy import share: ' + pct(row.energy_import_share);
  }

  function energyDriverRows() {
    return DATA.exercise3?.energy_driver_classification || [];
  }

  function energyDriverGroupOrder(group) {
    const order = [
      'top-5 superstar concentration',
      'upper-tier concentration (ranks 6-50)',
      'broad upper-tail concentration (ranks 51-200)',
      'tail compression (rank 201+)',
      'stable / small Gini change',
      'top-5 deconcentration',
      'upper-tier deconcentration (ranks 6-50)'
    ];
    const index = order.indexOf(group);
    return index === -1 ? 999 : index;
  }

  function energyDriverDelta(row) {
    const panelDelta = Number(row.delta_panel_ex_energy_gini);
    if (Number.isFinite(panelDelta)) return panelDelta;
    const calculatedDelta = Number(row.delta_calculated_ex_energy_gini);
    return Number.isFinite(calculatedDelta) ? calculatedDelta : null;
  }

  function signedFmt(value, digits = 3) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return 'n/a';
    const number = Number(value);
    return (number > 0 ? '+' : '') + number.toFixed(digits);
  }

  function focusEnergyCountry(iso3) {
    const check = Array.from(document.querySelectorAll('.energy-country-check')).find((el) => el.value === iso3);
    if (check) check.checked = true;
    renderEnergyLines();
    const countryRows = energyPanel()
      .filter((row) => row.iso3 === iso3)
      .sort((a, b) => Number(a.year) - Number(b.year));
    if (countryRows.length) setEnergyDetail(countryRows[countryRows.length - 1]);
  }

  function renderEnergyDriverCountryList() {
    const list = byId('energy-driver-country-list');
    const select = byId('energy-driver-group-select');
    if (!list || !select) return;
    const selectedGroup = select.value || '__all__';
    const rows = energyDriverRows()
      .filter((row) => selectedGroup === '__all__' || row.main_driver_group === selectedGroup)
      .sort((a, b) => {
        const groupCmp = energyDriverGroupOrder(a.main_driver_group) - energyDriverGroupOrder(b.main_driver_group);
        if (groupCmp !== 0) return groupCmp;
        const deltaCmp = Math.abs(energyDriverDelta(b) || 0) - Math.abs(energyDriverDelta(a) || 0);
        return deltaCmp || String(a.country || '').localeCompare(String(b.country || ''));
      });
    if (!rows.length) {
      list.textContent = 'No countries available for this driver group.';
      return;
    }
    const pieces = [];
    let currentGroup = null;
    rows.forEach((row) => {
      if (selectedGroup === '__all__' && row.main_driver_group !== currentGroup) {
        currentGroup = row.main_driver_group;
        pieces.push('<h4 class="driver-country-group">' + escapeHtml(currentGroup) + '</h4>');
      }
      const delta = energyDriverDelta(row);
      const direction = row.gini_change_direction ? ' ' + row.gini_change_direction : '';
      pieces.push(
        '<div class="driver-country-item">' +
          '<button type="button" class="driver-country-button" data-iso3="' + escapeHtml(row.iso3) + '">' +
            escapeHtml(row.country) +
          '</button>' +
          '<span class="driver-country-meta">Δ ' + signedFmt(delta) + direction + '</span>' +
        '</div>'
      );
    });
    list.innerHTML = pieces.join('');
  }

  function renderEnergyDriverDropdown() {
    const dropdown = byId('energy-driver-dropdown');
    const select = byId('energy-driver-group-select');
    const list = byId('energy-driver-country-list');
    if (!dropdown || !select || !list) return;
    const rows = energyDriverRows();
    if (!rows.length) {
      dropdown.open = false;
      select.innerHTML = '';
      list.textContent = 'No rank-bucket driver classification is available for this sample.';
      return;
    }
    const counts = new Map();
    rows.forEach((row) => {
      const group = row.main_driver_group || 'Unclassified';
      counts.set(group, (counts.get(group) || 0) + 1);
    });
    const groups = Array.from(counts.keys()).sort((a, b) => {
      const orderCmp = energyDriverGroupOrder(a) - energyDriverGroupOrder(b);
      return orderCmp || a.localeCompare(b);
    });
    select.innerHTML =
      '<option value="__all__">All driver groups (' + rows.length + ' countries)</option>' +
      groups.map((group) => (
        '<option value="' + escapeHtml(group) + '">' + escapeHtml(group) + ' (' + counts.get(group) + ')</option>'
      )).join('');
    if (!select.dataset.driverBound) {
      select.addEventListener('change', renderEnergyDriverCountryList);
      select.dataset.driverBound = 'true';
    }
    if (!list.dataset.driverBound) {
      list.addEventListener('click', (event) => {
        const button = event.target.closest('button[data-iso3]');
        if (!button) return;
        focusEnergyCountry(button.dataset.iso3);
      });
      list.dataset.driverBound = 'true';
    }
    renderEnergyDriverCountryList();
  }

  function nonenergyRankRows() {
    return DATA.exercise3?.nonenergy_rank_decomposition || [];
  }

  function nonenergyTopProductRows() {
    return DATA.exercise3?.nonenergy_top_products || [];
  }

  function rankBucketDriverLookup() {
    const lookup = new Map();
    energyDriverRows().forEach((row) => {
      if (row.iso3) lookup.set(row.iso3, row);
    });
    return lookup;
  }

  function rankBucketCountrySummaries() {
    const drivers = rankBucketDriverLookup();
    const countries = new Map();
    nonenergyRankRows().forEach((row) => {
      if (!row.iso3 || !row.country) return;
      if (!countries.has(row.iso3)) {
        const driver = drivers.get(row.iso3) || {};
        countries.set(row.iso3, {
          iso3: row.iso3,
          country: row.country,
          driverGroup: driver.main_driver_group || 'Unclassified',
          delta: energyDriverDelta(driver),
          endTop5: null,
          endTail: null,
          rows: []
        });
      }
      const country = countries.get(row.iso3);
      country.rows.push(row);
      if (row.snapshot === 'end') {
        country.endTop5 = Number(row.top5_share);
        country.endTail = Number(row.rank201_plus_share);
      }
    });
    return Array.from(countries.values());
  }

  function compareRankBucketCountries(sortMode) {
    return (a, b) => {
      if (sortMode === 'country') return a.country.localeCompare(b.country);
      if (sortMode === 'driver_group') {
        const groupCmp = energyDriverGroupOrder(a.driverGroup) - energyDriverGroupOrder(b.driverGroup);
        if (groupCmp !== 0) return groupCmp;
        const deltaCmp = Math.abs(b.delta || 0) - Math.abs(a.delta || 0);
        return deltaCmp || a.country.localeCompare(b.country);
      }
      if (sortMode === 'end_tail_desc') {
        const tailCmp = (Number(b.endTail) || -1) - (Number(a.endTail) || -1);
        return tailCmp || a.country.localeCompare(b.country);
      }
      const top5Cmp = (Number(b.endTop5) || -1) - (Number(a.endTop5) || -1);
      return top5Cmp || a.country.localeCompare(b.country);
    };
  }

  function selectedRankBucketCountries() {
    const group = byId('rank-bucket-group')?.value || '__all__';
    const query = (byId('rank-bucket-search')?.value || '').trim().toLowerCase();
    const sortMode = byId('rank-bucket-sort')?.value || 'end_top5_desc';
    return rankBucketCountrySummaries()
      .filter((country) => group === '__all__' || country.driverGroup === group)
      .filter((country) => {
        if (!query) return true;
        return country.country.toLowerCase().includes(query) || country.iso3.toLowerCase().includes(query);
      })
      .sort(compareRankBucketCountries(sortMode));
  }

  function rankBucketSnapshotSort(reverse) {
    const order = reverse ? SNAPSHOT_REVERSE_ORDER : SNAPSHOT_ORDER;
    return (a, b) => {
      const orderCmp = (order[a.snapshot] ?? 99) - (order[b.snapshot] ?? 99);
      return orderCmp || Number(a.year) - Number(b.year);
    };
  }

  function rankBucketLabel(row, includeCountry) {
    const snapshot = String(row.snapshot || '').toLowerCase();
    const text = snapshot ? snapshot.charAt(0).toUpperCase() + snapshot.slice(1) : 'Snapshot';
    const prefix = includeCountry ? row.country + '  ' : '';
    return prefix + text + ' ' + row.year;
  }

  function rankBucketTraces(rows, includeCountry) {
    return RANK_BUCKETS.map((bucket) => ({
      type: 'bar',
      orientation: 'h',
      name: bucket.label,
      x: rows.map((row) => Number(row[bucket.key])),
      y: rows.map((row) => rankBucketLabel(row, includeCountry)),
      customdata: rows.map((row) => [
        row.active_nonenergy_products,
        row.total_nonenergy_imports,
        row.top10_share,
        row.iso3,
        row.snapshot,
        row.year
      ]),
      marker: { color: bucket.color },
      hovertemplate:
        '<b>%{y}</b><br>' +
        bucket.label + ': %{x:.1%}<br>' +
        'Top 10: %{customdata[2]:.1%}<br>' +
        'Active non-energy HS6: %{customdata[0]:,.0f}<br>' +
        'Non-energy imports: $%{customdata[1]:,.0f}<extra></extra>'
    }));
  }

  function renderRankBucketOverview() {
    const node = byId('rank-bucket-overview');
    if (!node) return;
    const countries = selectedRankBucketCountries();
    const rows = countries.flatMap((country) =>
      country.rows.slice().sort(rankBucketSnapshotSort(true))
    );
    if (!rows.length) {
      Plotly.purge(node);
      node.textContent = 'No countries match the current rank-bucket filters.';
      return;
    }
    const chartLayout = layout(
      'Non-energy import basket decomposition: refined rank buckets',
      '',
      'Share of non-energy imports'
    );
    chartLayout.height = Math.max(640, rows.length * 24 + 118);
    chartLayout.barmode = 'stack';
    chartLayout.margin = { l: 196, r: 24, t: 54, b: 70 };
    chartLayout.xaxis = {
      title: 'Share of non-energy imports',
      range: [0, 1],
      tickformat: '.0%',
      gridcolor: '#e5e7eb',
      zeroline: false
    };
    chartLayout.yaxis = {
      automargin: true,
      autorange: 'reversed',
      tickfont: { size: 10 },
      gridcolor: 'rgba(0,0,0,0)',
      zeroline: false
    };
    chartLayout.legend = { orientation: 'h', traceorder: 'normal', x: 0.5, xanchor: 'center', y: -0.08 };
    Plotly.react(node, rankBucketTraces(rows, true), chartLayout, { ...config, displayModeBar: false });
    if (!node.dataset.rankClickBound) {
      node.on('plotly_click', (event) => {
        const iso3 = event.points?.[0]?.customdata?.[3];
        const snapshot = event.points?.[0]?.customdata?.[4];
        const year = event.points?.[0]?.customdata?.[5];
        if (!iso3) return;
        const select = byId('rank-bucket-country');
        if (select) select.value = iso3;
        renderRankBucketCountryFocus(iso3, snapshot, year);
      });
      node.dataset.rankClickBound = 'true';
    }
  }

  function rankBucketCountryRows(iso3) {
    return nonenergyRankRows()
      .filter((row) => row.iso3 === iso3)
      .sort(rankBucketSnapshotSort(false));
  }

  function rankBucketTotalImports(row) {
    const match = (DATA.exercise3?.energy_excluded_import_panel || [])
      .find((item) => item.iso3 === row.iso3 && Number(item.year) === Number(row.year));
    return match ? Number(match.total_imports) : NaN;
  }

  function rankBucketTopProducts(row, limit = 5) {
    return nonenergyTopProductRows()
      .filter((item) =>
        item.iso3 === row.iso3 &&
        item.snapshot === row.snapshot &&
        Number(item.year) === Number(row.year)
      )
      .sort((a, b) => Number(a.rank) - Number(b.rank))
      .slice(0, limit);
  }

  function rankBucketDefaultDetailRow(rows) {
    return rows.find((row) => row.snapshot === 'end') || rows[rows.length - 1];
  }

  function renderRankBucketSnapshotDetail(row) {
    const detail = byId('rank-bucket-detail');
    if (!detail || !row) return;
    const products = rankBucketTopProducts(row, 5);
    const productHtml = products.length
      ? '<ul class="rank-bucket-products">' + products.map((product) => (
          '<li class="rank-bucket-product">' +
            '<span class="rank-bucket-product-name">' + escapeHtml(product.product_label || 'Unlabeled product') + '</span>' +
            '<span class="rank-bucket-product-code">HS ' + escapeHtml(product.cmd_code) + '</span>' +
            '<span class="rank-bucket-product-value">' +
              usdShort(product.trade_value) + ' · ' + pct(product.share_nonenergy_imports) + ' of non-energy imports' +
            '</span>' +
          '</li>'
        )).join('') + '</ul>'
      : '<p>No top-product rows are available for this snapshot.</p>';
    detail.innerHTML =
      '<div class="rank-bucket-detail-title">' + escapeHtml(row.country) + ' (' + escapeHtml(row.iso3) + ')</div>' +
      '<div>' + escapeHtml(rankBucketLabel(row, false)) + '</div>' +
      '<div class="rank-bucket-metrics">' +
        '<div class="rank-bucket-metric"><span>Non-energy imports</span><strong>' +
          usdShort(row.total_nonenergy_imports) +
        '</strong></div>' +
        '<div class="rank-bucket-metric"><span>Total imports</span><strong>' +
          usdShort(rankBucketTotalImports(row)) +
        '</strong></div>' +
      '</div>' +
      '<strong>Top non-energy products</strong>' +
      productHtml;
  }

  function renderRankBucketCountryFocus(iso3, detailSnapshot, detailYear) {
    const node = byId('rank-bucket-country-chart');
    const detail = byId('rank-bucket-detail');
    const title = byId('rank-bucket-focus-title');
    if (!node) return;
    const selectedIso = iso3 || byId('rank-bucket-country')?.value;
    const rows = rankBucketCountryRows(selectedIso);
    if (!rows.length) {
      Plotly.purge(node);
      if (detail) detail.textContent = 'No rank-bucket rows available for the selected country.';
      if (title) title.textContent = 'Country Focus';
      return;
    }
    const country = rows[0].country;
    if (title) title.textContent = 'Country Focus: ' + country;
    const chartLayout = layout('Rank-bucket shares', '', 'Share of non-energy imports');
    chartLayout.height = 330;
    chartLayout.barmode = 'stack';
    chartLayout.margin = { l: 92, r: 16, t: 52, b: 52 };
    chartLayout.xaxis = {
      title: 'Share of non-energy imports',
      range: [0, 1],
      tickformat: '.0%',
      gridcolor: '#e5e7eb',
      zeroline: false
    };
    chartLayout.yaxis = {
      automargin: true,
      autorange: 'reversed',
      gridcolor: 'rgba(0,0,0,0)',
      zeroline: false
    };
    chartLayout.legend = { orientation: 'h', traceorder: 'normal', x: 0.5, xanchor: 'center', y: -0.2 };
    Plotly.react(node, rankBucketTraces(rows, false), chartLayout, { ...config, displayModeBar: false });
    if (!node.dataset.rankFocusClickBound) {
      node.on('plotly_click', (event) => {
        const iso3Clicked = event.points?.[0]?.customdata?.[3];
        const snapshot = event.points?.[0]?.customdata?.[4];
        const year = event.points?.[0]?.customdata?.[5];
        const clickedRows = rankBucketCountryRows(iso3Clicked);
        const clickedRow = clickedRows.find((row) =>
          row.snapshot === snapshot && Number(row.year) === Number(year)
        );
        renderRankBucketSnapshotDetail(clickedRow || rankBucketDefaultDetailRow(clickedRows));
      });
      node.dataset.rankFocusClickBound = 'true';
    }
    const selectedDetailRow = rows.find((row) =>
      row.snapshot === detailSnapshot && Number(row.year) === Number(detailYear)
    );
    renderRankBucketSnapshotDetail(selectedDetailRow || rankBucketDefaultDetailRow(rows));
  }

  function setupRankBucketDecomposition() {
    const rows = nonenergyRankRows();
    const overview = byId('rank-bucket-overview');
    const countrySelect = byId('rank-bucket-country');
    const groupSelect = byId('rank-bucket-group');
    if (!overview || !countrySelect || !groupSelect) return;
    if (!rows.length) {
      overview.textContent = 'No non-energy rank-bucket decomposition data available.';
      return;
    }
    const countries = rankBucketCountrySummaries().sort((a, b) => a.country.localeCompare(b.country));
    countrySelect.innerHTML = countries.map((country) => (
      '<option value="' + escapeHtml(country.iso3) + '">' + escapeHtml(country.country) + '</option>'
    )).join('');
    const groupCounts = new Map();
    countries.forEach((country) => {
      groupCounts.set(country.driverGroup, (groupCounts.get(country.driverGroup) || 0) + 1);
    });
    const groups = Array.from(groupCounts.keys()).sort((a, b) => {
      const orderCmp = energyDriverGroupOrder(a) - energyDriverGroupOrder(b);
      return orderCmp || a.localeCompare(b);
    });
    groupSelect.innerHTML =
      '<option value="__all__">All countries (' + countries.length + ')</option>' +
      groups.map((group) => (
        '<option value="' + escapeHtml(group) + '">' + escapeHtml(group) + ' (' + groupCounts.get(group) + ')</option>'
      )).join('');
    const defaultCountry =
      countries.find((country) => country.iso3 === 'HKG') ||
      countries.slice().sort(compareRankBucketCountries('end_top5_desc'))[0];
    if (defaultCountry) countrySelect.value = defaultCountry.iso3;
    ['rank-bucket-group', 'rank-bucket-sort'].forEach((id) => {
      byId(id)?.addEventListener('change', renderRankBucketOverview);
    });
    byId('rank-bucket-search')?.addEventListener('input', renderRankBucketOverview);
    countrySelect.addEventListener('change', (event) => renderRankBucketCountryFocus(event.target.value));
    renderRankBucketOverview();
    renderRankBucketCountryFocus(countrySelect.value);
  }

  function renderEnergyMap() {
    const node = byId('energy-world-map');
    if (!node) return;
    const year = currentEnergyMapYear();
    const rows = energyRowsForYear(year);
    const scaleRange = energyMapScaleRange();
    const trace = {
      type: 'choropleth',
      locations: rows.map((r) => r.iso3),
      z: rows.map((r) => r.product_gini_ex_energy),
      text: rows.map((r) => r.country),
      customdata: rows,
      colorscale: [
        [0, '#fef3c7'],
        [0.5, '#14b8a6'],
        [1, '#0f172a']
      ],
      zauto: !scaleRange,
      zmin: scaleRange?.min,
      zmax: scaleRange?.max,
      colorbar: { title: 'Product Gini ex energy' },
      marker: { line: { color: '#ffffff', width: 0.4 } },
      hovertemplate: '<b>%{text}</b><br>Ex-energy Gini: %{z:.3f}<extra></extra>'
    };
    Plotly.react(node, [trace], {
      margin: { l: 0, r: 0, t: 10, b: 0 },
      geo: {
        projection: { type: 'natural earth' },
        showframe: false,
        showcoastlines: true,
        coastlinecolor: '#94a3b8',
        bgcolor: 'rgba(0,0,0,0)'
      },
      paper_bgcolor: 'rgba(0,0,0,0)'
    }, config);
    if (!node.dataset.energyClickBound) {
      node.on('plotly_click', (event) => {
        const row = event.points?.[0]?.customdata;
        if (!row) return;
        const check = document.querySelector('.energy-country-check[value="' + row.iso3 + '"]');
        if (check) check.checked = true;
        setEnergyDetail(row);
        renderEnergyLines();
      });
      node.dataset.energyClickBound = 'true';
    }
  }

  function renderEnergyCountryList() {
    const list = byId('energy-country-checkboxes');
    if (!list) return;
    const selectedDefaults = new Set(['IND', 'USA', 'CHN', 'DEU', 'JPN']);
    const countries = new Map();
    energyPanel().forEach((row) => {
      if (row.iso3 && row.country && !countries.has(row.iso3)) {
        countries.set(row.iso3, { iso3: row.iso3, country: row.country });
      }
    });
    list.innerHTML = '';
    Array.from(countries.values()).sort((a, b) => a.country.localeCompare(b.country)).forEach((country) => {
      const label = document.createElement('label');
      label.dataset.country = (country.country || '').toLowerCase();
      label.dataset.iso3 = country.iso3;
      label.innerHTML = '<input class="energy-country-check" type="checkbox" value="' + country.iso3 + '"' +
        (selectedDefaults.has(country.iso3) ? ' checked' : '') + '> ' + country.country;
      list.appendChild(label);
    });
    list.addEventListener('change', renderEnergyLines);
  }

  function filterEnergyCountryList() {
    const query = (byId('energy-country-search')?.value || '').toLowerCase();
    document.querySelectorAll('#energy-country-checkboxes label').forEach((label) => {
      const match = label.dataset.country.includes(query) || label.dataset.iso3.toLowerCase().includes(query);
      label.style.display = match ? 'flex' : 'none';
    });
  }

  function renderEnergyLines() {
    const node = byId('energy-country-lines');
    if (!node) return;
    const selected = selectedEnergyCountries();
    const rows = energyPanel().filter((row) => selected.includes(row.iso3));
    const grouped = new Map();
    rows.forEach((row) => {
      if (!grouped.has(row.iso3)) grouped.set(row.iso3, []);
      grouped.get(row.iso3).push(row);
    });
    const traces = Array.from(grouped.entries()).map(([iso3, group], index) => {
      group.sort((a, b) => Number(a.year) - Number(b.year));
      return {
        type: 'scatter',
        mode: 'lines+markers',
        name: group[0]?.country || iso3,
        x: group.map((r) => r.year),
        y: group.map((r) => r.product_gini_ex_energy),
        customdata: group,
        line: { color: COLORS[index % COLORS.length], width: 2 },
        marker: { size: 5 },
        hovertemplate: '<b>%{fullData.name}</b><br>%{x}: %{y:.3f}<extra></extra>'
      };
    });
    Plotly.react(node, traces, layout('Import Product Gini excluding energy over time', 'Gini'), config);
    if (!node.dataset.energyClickBound) {
      node.on('plotly_click', (event) => {
        const row = event.points?.[0]?.customdata;
        setEnergyDetail(row);
      });
      node.dataset.energyClickBound = 'true';
    }
  }

  function setupEnergyExcludedMapLines() {
    const panel = energyPanel();
    const yearSelect = byId('energy-map-year');
    const yearSlider = byId('energy-map-year-slider');
    if (!panel.length || !yearSelect || !yearSlider) {
      const detail = byId('energy-line-detail');
      if (detail) detail.textContent = 'No energy-excluded import panel data available.';
      return;
    }
    const years = Array.from(new Set(panel.map((row) => row.year))).sort((a, b) => a - b);
    const minYear = Math.min(...years);
    const maxYear = Math.max(...years);
    yearSelect.innerHTML = '';
    years.forEach((year) => {
      const option = document.createElement('option');
      option.value = year;
      option.textContent = year;
      if (year === maxYear) option.selected = true;
      yearSelect.appendChild(option);
    });
    yearSlider.min = minYear;
    yearSlider.max = maxYear;
    yearSlider.step = 1;
    yearSlider.value = maxYear;
    byId('energy-map-year-min').textContent = minYear;
    byId('energy-map-year-max').textContent = maxYear;
    setEnergyMapYear(maxYear);
    renderEnergyCountryList();
    renderEnergyDriverDropdown();
    byId('energy-map-year')?.addEventListener('change', (event) => {
      setEnergyMapYear(event.target.value);
      renderEnergyMap();
    });
    byId('energy-map-year-slider')?.addEventListener('input', (event) => {
      setEnergyMapYear(event.target.value);
      renderEnergyMap();
    });
    byId('energy-map-year-slider')?.addEventListener('change', (event) => {
      setEnergyMapYear(event.target.value);
      renderEnergyMap();
    });
    byId('energy-country-search')?.addEventListener('input', filterEnergyCountryList);
    byId('energy-select-all-countries')?.addEventListener('click', () => {
      document.querySelectorAll('.energy-country-check').forEach((el) => { el.checked = true; });
      renderEnergyLines();
    });
    byId('energy-clear-countries')?.addEventListener('click', () => {
      document.querySelectorAll('.energy-country-check').forEach((el) => { el.checked = false; });
      renderEnergyLines();
    });
    renderEnergyMap();
    renderEnergyLines();
  }

  function renderProfPLorenz() {
    const node = byId('prof-p-lorenz-chart');
    if (!node) return;
    const flow = byId('prof-p-lorenz-flow')?.value || 'Exports';
    const points = (DATA.profP?.lorenz_points || []).filter((row) => row.flow === flow);
    const summary = (DATA.profP?.lorenz_summary || []).filter((row) => row.flow === flow);
    const countryOrder = ['India', 'China', 'United States'];
    const traces = countryOrder.map((country, index) => {
      const countryPoints = points
        .filter((row) => row.country === country)
        .sort((a, b) => Number(a.point_index) - Number(b.point_index));
      const countrySummary = summary.find((row) => row.country === country) || {};
      return {
        type: 'scatter',
        mode: 'lines',
        name: country,
        x: countryPoints.map((row) => 100 * Number(row.cum_products_share)),
        y: countryPoints.map((row) => 100 * Number(row.cum_trade_value_share)),
        customdata: countryPoints.map(() => [
          countrySummary.modern_product_gini,
          countrySummary.modern_top_1pct_product_share,
          countrySummary.modern_top_5pct_product_share
        ]),
        line: { color: COLORS[index % COLORS.length], width: 3 },
        hovertemplate:
          '<b>' + country + '</b><br>' +
          'Products: %{x:.1f}%<br>' +
          'Trade value: %{y:.1f}%<br>' +
          'Gini: %{customdata[0]:.3f}<br>' +
          'Top 1% share: %{customdata[1]:.1%}<br>' +
          'Top 5% share: %{customdata[2]:.1%}<extra></extra>'
      };
    });
    traces.push({
      type: 'scatter',
      mode: 'lines',
      name: 'Equal distribution',
      x: [0, 100],
      y: [0, 100],
      line: { color: '#94a3b8', width: 1.5, dash: 'dash' },
      hoverinfo: 'skip'
    });
    const chartLayout = layout(flow + ' Lorenz curves, 2001', 'Cumulative trade value (%)', 'Cumulative active HS6 products (%)');
    chartLayout.xaxis.range = [0, 100];
    chartLayout.yaxis.range = [0, 100];
    Plotly.react(node, traces, chartLayout, { ...config, displayModeBar: false });

    const cards = byId('prof-p-lorenz-cards');
    if (cards) {
      cards.innerHTML = summary
        .sort((a, b) => countryOrder.indexOf(a.country) - countryOrder.indexOf(b.country))
        .map((row) => (
          '<article>' +
          '<h3>' + escapeHtml(row.country) + '</h3>' +
          '<p>Gini ' + fmt(row.modern_product_gini) +
          ' vs paper ' + fmt(row.paper_product_gini) +
          ' | top 1% ' + pct(row.modern_top_1pct_product_share) +
          ' | top 5% ' + pct(row.modern_top_5pct_product_share) +
          ' | products ' + Number(row.modern_active_products).toLocaleString() + '</p>' +
          '</article>'
        ))
        .join('');
    }
  }

  function setupProfP() {
    byId('prof-p-lorenz-flow')?.addEventListener('change', renderProfPLorenz);
    renderProfPLorenz();
  }

  function setupExtension() {
    const years = Array.from(new Set((DATA.exercise1?.panel || []).map((row) => row.year))).sort((a, b) => a - b);
    const yearSelect = byId('map-year');
    const yearSlider = byId('map-year-slider');
    const minYear = Math.min(...years);
    const maxYear = Math.max(...years);
    const requestedDefaultYear = Number(DATA.exercise1?.default_year) || maxYear;
    const defaultYear = years.includes(requestedDefaultYear) ? requestedDefaultYear : maxYear;
    const defaultMetric = DATA.exercise1?.default_metric || 'product_gini';
    years.forEach((year) => {
      const option = document.createElement('option');
      option.value = year;
      option.textContent = year;
      if (year === defaultYear) option.selected = true;
      yearSelect.appendChild(option);
    });
    if (yearSlider) {
      yearSlider.min = minYear;
      yearSlider.max = maxYear;
      yearSlider.step = 1;
      yearSlider.value = defaultYear;
      byId('map-year-min').textContent = minYear;
      byId('map-year-max').textContent = maxYear;
    }
    ['map-metric', 'line-metric'].forEach((id) => {
      const select = byId(id);
      if (select && Array.from(select.options).some((option) => option.value === defaultMetric)) {
        select.value = defaultMetric;
      }
    });
    setMapYear(defaultYear);
    renderCountryList();
    ['map-flow', 'map-metric'].forEach((id) => byId(id)?.addEventListener('change', renderMap));
    byId('map-year')?.addEventListener('change', (event) => {
      setMapYear(event.target.value);
      renderMap();
    });
    byId('map-year-slider')?.addEventListener('input', (event) => {
      setMapYear(event.target.value);
      renderMap();
    });
    byId('map-year-slider')?.addEventListener('change', (event) => {
      setMapYear(event.target.value);
      renderMap();
    });
    ['line-flow', 'line-metric'].forEach((id) => byId(id)?.addEventListener('change', renderLines));
    byId('country-search')?.addEventListener('input', filterCountryList);
    byId('select-all-countries')?.addEventListener('click', () => {
      document.querySelectorAll('.country-check').forEach((el) => { el.checked = true; });
      renderLines();
    });
    byId('clear-countries')?.addEventListener('click', () => {
      document.querySelectorAll('.country-check').forEach((el) => { el.checked = false; });
      renderLines();
    });
    renderMap();
    renderLines();
    setupEnergyExcludedMapLines();
    setupRankBucketDecomposition();
    renderExclusionChart();
    renderBenchmarkChart();
  }

  function renderExclusionChart() {
    const node = byId('exclusion-chart');
    if (!node) return;
    const rows = (DATA.exercise6?.distribution || []).filter((row) => Number.isFinite(Number(row.product_gini)));
    if (!rows.length) return;
    const variantOrder = (DATA.exercise6?.median_by_variant || []).map((row) => row.variant);
    const grouped = new Map();
    rows.forEach((row) => {
      if (!grouped.has(row.variant)) grouped.set(row.variant, []);
      grouped.get(row.variant).push(row);
    });
    const variants = [
      ...variantOrder.filter((variant) => grouped.has(variant)),
      ...Array.from(grouped.keys()).filter((variant) => !variantOrder.includes(variant))
    ];
    const values = rows.map((row) => Number(row.product_gini));
    const rangeMin = Math.max(0, Math.floor((Math.min(...values) - 0.02) / 0.02) * 0.02);
    const rangeMax = Math.min(1, Math.ceil((Math.max(...values) + 0.02) / 0.02) * 0.02);
    const traces = variants.map((variant, index) => {
      const group = grouped.get(variant) || [];
      const label = group[0]?.label || variant;
      return {
        type: 'histogram',
        name: label,
        x: group.map((row) => Number(row.product_gini)),
        histnorm: 'probability',
        xbins: { start: rangeMin, end: rangeMax, size: 0.015 },
        marker: { color: COLORS[index % COLORS.length], line: { color: '#ffffff', width: 0.5 } },
        opacity: 0.48,
        hovertemplate: label + '<br>Product Gini bin: %{x:.3f}<br>Country-year share: %{y:.1%}<extra></extra>'
      };
    });
    const chartLayout = layout(
      'Import Product Gini distributions after lumpy-product exclusions',
      'Share of country-years',
      'Product Gini'
    );
    chartLayout.barmode = 'overlay';
    chartLayout.xaxis.range = [rangeMin, rangeMax];
    chartLayout.xaxis.tickformat = '.2f';
    chartLayout.yaxis.tickformat = '.0%';
    chartLayout.legend = { orientation: 'h', y: -0.28 };
    Plotly.react(node, traces, chartLayout, config);
  }

  function renderBenchmarkChart() {
    const node = byId('benchmark-chart');
    if (!node) return;
    const rows = DATA.exercise10?.benchmark_ladder || [];
    const traces = ['Exports', 'Imports'].map((flow, index) => {
      const flowRows = rows.filter((r) => r.flow === flow);
      return {
        type: 'bar',
        name: flow,
        x: flowRows.map((r) => r.benchmark),
        y: flowRows.map((r) => r.gap),
        marker: { color: COLORS[index] },
        hovertemplate: flow + '<br>%{x}<br>Actual minus benchmark: %{y:.3f}<extra></extra>'
      };
    });
    const chartLayout = layout('How far actual Product Ginis sit above random benchmarks', 'Actual minus benchmark Product Gini');
    chartLayout.barmode = 'group';
    Plotly.react(node, traces, chartLayout, config);
  }

  function setupImports() {
    renderImportBins();
    renderSupplierChart();
    renderWorldSupplierChart();
    renderIoChart();
    renderHs2LinkageCharts();
    byId('hs2-linkage-view')?.addEventListener('change', renderHs2LinkageCharts);
  }

  function renderImportBins() {
    const node = byId('import-bin-chart');
    if (!node) return;
    const rows = DATA.exercise3?.bin_summary || [];
    const traces = [
      { name: 'Product Gini (within bin)', y: rows.map((r) => r.product_gini), marker: { color: '#0f766e' } },
      { name: 'Top-1 product share', y: rows.map((r) => r.top_1_product_share), marker: { color: '#b7791f' } },
      { name: 'Import value share', y: rows.map((r) => r.import_value_share), marker: { color: '#2563eb' } }
    ].map((trace) => ({
      type: 'bar',
      name: trace.name,
      x: rows.map((r) => r.label),
      y: trace.y,
      marker: trace.marker,
      hovertemplate: trace.name + '<br>%{x}: %{y:.3f}<extra></extra>'
    }));
    const chartLayout = layout('Import bins: concentration versus scale', 'Share or Gini');
    chartLayout.barmode = 'group';
    Plotly.react(node, traces, chartLayout, config);
  }

  function renderSupplierChart() {
    const node = byId('supplier-chart');
    if (!node) return;
    const rows = DATA.exercise4?.year_series || [];
    const traces = [
      ['median_top_supplier_share', 'Median top-supplier share', '#0f766e'],
      ['share_products_top_supplier_ge_75', 'Share of products with top supplier >=75%', '#b7791f'],
      ['import_value_share_products_top_supplier_ge_75', 'Import value share in >=75% rows', '#2563eb']
    ].map(([key, name, color]) => ({
      type: 'scatter',
      mode: 'lines+markers',
      name,
      x: rows.map((r) => r.year),
      y: rows.map((r) => r[key]),
      line: { color, width: 2 },
      hovertemplate: name + '<br>%{x}: %{y:.3f}<extra></extra>'
    }));
    Plotly.react(node, traces, layout('Dominant supplier to a particular country', 'Share'), config);
  }

  function renderWorldSupplierChart() {
    const node = byId('world-supplier-chart');
    if (!node) return;
    const rows = DATA.h24Supplier?.year_series || [];
    const traces = [
      ['median_top_supplier_share', 'Median top-supplier share', '#0f766e'],
      ['share_products_top_supplier_ge_75', 'Share of products with top supplier >=75%', '#b7791f'],
      ['import_value_share_top_supplier_ge_75', 'Import value share in >=75% products', '#2563eb']
    ].map(([key, name, color]) => ({
      type: 'scatter',
      mode: 'lines+markers',
      name,
      x: rows.map((r) => r.year),
      y: rows.map((r) => r[key]),
      line: { color, width: 2 },
      hovertemplate: name + '<br>%{x}: %{y:.3f}<extra></extra>'
    }));
    Plotly.react(node, traces, layout('Dominant supplier to all countries', 'Share'), config);
  }

  function renderIoChart() {
    const node = byId('io-chart');
    if (!node) return;
    const rows = DATA.exercise11?.year_series || [];
    const traces = [
      ['weighted_top_sector_input_product_gini', 'Top-sector input Product Gini', '#0f766e'],
      ['weighted_top_sector_top_supplier_share', 'Top-sector top-supplier share', '#b7791f'],
      ['median_top_sector_matched_requirement_share', 'Matched requirement share', '#2563eb']
    ].map(([key, name, color]) => ({
      type: 'scatter',
      mode: 'lines+markers',
      name,
      x: rows.map((r) => r.year),
      y: rows.map((r) => r[key]),
      line: { color, width: 2 },
      hovertemplate: name + '<br>%{x}: %{y:.3f}<extra></extra>'
    }));
    Plotly.react(node, traces, layout('Top export sector imported-input exposure', 'Share or Gini'), config);
  }

  function hs2RowsForCurrentView() {
    const view = byId('hs2-linkage-view')?.value || 'decile';
    const linkage = DATA.exercise11?.hs2_linkage || {};
    return {
      view,
      rows: view === 'chapter' ? (linkage.chapters || []) : (linkage.deciles || [])
    };
  }

  function hs2MarkerSizes(rows) {
    return rows.map((row) => {
      const share = Math.max(0, Number(row.mean_import_share) || 0);
      return 8 + Math.sqrt(share) * 90;
    });
  }

  function renderHs2LinkageChart(nodeId, outcomeKey, title, ytitle, color) {
    const node = byId(nodeId);
    if (!node) return;
    const { view, rows } = hs2RowsForCurrentView();
    const xTitle = 'Mean summed HS6 LOO Gini contribution';
    let trace;
    if (view === 'chapter') {
      trace = {
        type: 'scatter',
        mode: 'markers',
        name: 'HS2 chapters',
        x: rows.map((r) => r.mean_loo_gini),
        y: rows.map((r) => r[outcomeKey]),
        text: rows.map((r) => r.display_label),
        customdata: rows.map((r) => [
          r.mean_import_share,
          r.mean_intermediate_import_share,
          r.mean_export_share,
          r.observations,
          r.mean_export_value
        ]),
        marker: {
          size: hs2MarkerSizes(rows),
          color: rows.map((r) => r.mean_intermediate_import_share),
          colorscale: 'Viridis',
          colorbar: { title: 'Intermediate<br>import share' },
          opacity: 0.82,
          line: { color: '#ffffff', width: 0.7 }
        },
        hovertemplate:
          '<b>%{text}</b><br>' +
          xTitle + ': %{x:.4f}<br>' +
          ytitle + ': %{y:.3f}<br>' +
          'Mean import share: %{customdata[0]:.2%}<br>' +
          'Intermediate import share: %{customdata[1]:.1%}<br>' +
          'Mean export share: %{customdata[2]:.2%}<br>' +
          'Mean export value: $%{customdata[4]:,.0f}<br>' +
          'Panel rows: %{customdata[3]}<extra></extra>'
      };
    } else {
      trace = {
        type: 'scatter',
        mode: 'lines+markers',
        name: 'Decile averages',
        x: rows.map((r) => r.mean_loo_gini),
        y: rows.map((r) => r[outcomeKey]),
        text: rows.map((r) => 'Decile ' + r.decile),
        customdata: rows.map((r) => [
          r.observations,
          r.chapter_count,
          r.min_loo_gini,
          r.max_loo_gini,
          r.top_chapters,
          r.mean_import_share,
          r.mean_intermediate_import_share,
          r.mean_export_value
        ]),
        line: { color, width: 2 },
        marker: { size: 8, color },
        hovertemplate:
          '<b>%{text}</b><br>' +
          xTitle + ': %{x:.4f}<br>' +
          ytitle + ': %{y:.3f}<br>' +
          'LOO range: %{customdata[2]:.4f} to %{customdata[3]:.4f}<br>' +
          'Rows: %{customdata[0]} | HS2 chapters: %{customdata[1]}<br>' +
          'Mean import share: %{customdata[5]:.2%}<br>' +
          'Intermediate import share: %{customdata[6]:.1%}<br>' +
          'Mean export value: $%{customdata[7]:,.0f}<br>' +
          'Largest import-share chapters:<br>%{customdata[4]}<extra></extra>'
      };
    }
    const chartLayout = layout(title, ytitle, xTitle);
    chartLayout.margin = { l: 64, r: view === 'chapter' ? 84 : 24, t: 52, b: 64 };
    chartLayout.showlegend = false;
    chartLayout.xaxis.zeroline = true;
    chartLayout.xaxis.zerolinecolor = '#94a3b8';
    Plotly.react(node, [trace], chartLayout, config);
  }

  function renderHs2LinkageCharts() {
    renderHs2LinkageChart(
      'hs2-probability-chart',
      'export_probability',
      'HS2 export probability',
      'Probability HS2 chapter is exported',
      '#2f5d62'
    );
    renderHs2LinkageChart(
      'hs2-value-chart',
      'mean_asinh_export_value',
      'HS2 export value',
      'Mean transformed HS2 export value',
      '#8c4f2b'
    );
  }

  document.addEventListener('DOMContentLoaded', () => {
    const page = document.body.dataset.page;
    setupSortableTables();
    if (page === 'extension') setupExtension();
    if (page === 'imports') setupImports();
    if (page === 'prof-p') setupProfP();
    window.addEventListener('resize', relayout);
  });
})();
"""


def site_data_for_js(data: dict[str, Any]) -> dict[str, Any]:
    """Keep browser data limited to objects consumed by site.js.

    Large static pages render their tables into HTML at build time. They do not
    need to be shipped in `site-data.js`, which has previously exceeded GitHub
    Pages' file-size limits when every analysis table was embedded.
    """
    keep = {
        "metadata",
        "labels",
        "countries",
        "exercise1",
        "exercise3",
        "exercise4",
        "h24Supplier",
        "exercise6",
        "exercise10",
        "exercise11",
        "profP",
    }
    return {key: value for key, value in data.items() if key in keep}


def write_json_assets(output: Path, data: dict[str, Any]) -> None:
    browser_data = site_data_for_js(data)
    json_text = json.dumps(browser_data, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    (output / "assets/site-data.json").write_text(json_text + "\n", encoding="utf-8")
    (output / "assets/site-data.js").write_text(
        "window.TRADE_GINI_DATA=" + json_text.replace("</", "<\\/") + ";\n",
        encoding="utf-8",
    )
    for needle in ["NaN", "undefined", "__PLACEHOLDER__"]:
        if needle in json_text:
            raise RuntimeError(f"Generated site data contains forbidden token: {needle}")


def prepare_output(output: Path) -> None:
    resolved = output.resolve()
    if resolved in {Path("/"), ROOT.resolve()}:
        raise RuntimeError(f"Refusing to clean unsafe site output directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    for target in output.iterdir():
        if target.name == ".git":
            continue
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    (output / "assets/vendor").mkdir(parents=True, exist_ok=True)
    (output / "assets/figures").mkdir(parents=True, exist_ok=True)
    (output / "assets/downloads").mkdir(parents=True, exist_ok=True)


def validate_site_root(output: Path, pages: dict[str, str]) -> None:
    expected_root_files = {Path(name).name for name in pages} | {"README.md"}
    unexpected_html = sorted(path.name for path in output.glob("*.html") if path.name not in expected_root_files)
    if unexpected_html:
        raise RuntimeError(f"Unexpected stale HTML files in site output root: {unexpected_html}")


def copy_assets(output: Path) -> None:
    for key, source in FIGURES.items():
        if not source.exists():
            raise FileNotFoundError(f"Required figure is missing: {source}")
        shutil.copy2(source, output / "assets/figures" / f"{key}.png")
    downloadable_sources = site_download_sources()
    for filename, source in downloadable_sources.items():
        if not source.exists():
            raise FileNotFoundError(f"Required downloadable artifact is missing: {source}")
        assert_csv_has_no_excluded_hs6(source, filename)
        shutil.copy2(source, output / "assets/downloads" / filename)


def cadot_asset_href(depth: int, path: str) -> str:
    return "../" * depth + path.lstrip("/")


def cadot_nav(depth: int, active: str) -> str:
    links = [
        ("hub", "Hub", "index.html"),
        ("exposure", "Exposure", "exposure/"),
        ("gini", "Gini", "gini/"),
        ("theil", "Theil", "theil/"),
        ("hhi", "HHI", "hhi/"),
        ("exercises", "Exercises", "exercises/"),
        ("downloads", "Downloads", "downloads/"),
    ]
    items = []
    for key, label, href in links:
        cls = ' class="active"' if key == active else ""
        items.append(f'<a{cls} href="{cadot_asset_href(depth, href)}">{escape(label)}</a>')
    return "<nav>" + "".join(items) + "</nav>"


def cadot_footer(depth: int) -> str:
    return f"""
    <footer class="site-footer">
      <div>
        <strong>Three linked metric sites</strong>
        <p>Cadot-style 156 reporters, 2000-2024, LT/HGL-weighted HS1992/H0 product families.</p>
      </div>
      <div class="footer-links">
        <a href="{cadot_asset_href(depth, 'gini/')}">Gini site</a>
        <a href="{cadot_asset_href(depth, 'theil/')}">Theil site</a>
        <a href="{cadot_asset_href(depth, 'hhi/')}">HHI site</a>
        <a href="{cadot_asset_href(depth, 'exercises/')}">Exercises</a>
        <a href="{cadot_asset_href(depth, 'downloads/')}">Downloads</a>
      </div>
    </footer>
    """


def cadot_page(title: str, active: str, body: str, depth: int) -> str:
    css_href = cadot_asset_href(depth, "assets/site.css")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)} | Trade Concentration</title>
  <link rel="stylesheet" href="{css_href}">
</head>
<body class="cadot-site" data-page="{escape(active)}">
  <header class="site-header">
    <a class="brand" href="{cadot_asset_href(depth, 'index.html')}">Trade Concentration</a>
    {cadot_nav(depth, active)}
  </header>
  <main>
    {body}
  </main>
  {cadot_footer(depth)}
</body>
</html>
"""


def cadot_site_css() -> str:
    return """
:root {
  color-scheme: light;
  --bg: #f7f6f1;
  --ink: #1d2525;
  --muted: #5f6868;
  --line: #d9d6ca;
  --panel: #ffffff;
  --accent: #0f766e;
  --accent-2: #a43f2d;
  --accent-3: #395c99;
}
* { box-sizing: border-box; }
body { margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--ink); line-height: 1.5; }
a { color: var(--accent-3); text-decoration: none; }
a:hover { text-decoration: underline; }
.site-header { position: sticky; top: 0; z-index: 5; display: flex; align-items: center; justify-content: space-between; gap: 24px; padding: 14px 28px; border-bottom: 1px solid var(--line); background: rgba(247, 246, 241, 0.96); backdrop-filter: blur(8px); }
.brand { font-weight: 800; color: var(--ink); }
nav { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; justify-content: flex-end; }
nav a, .button { border: 1px solid var(--line); border-radius: 7px; padding: 8px 12px; background: #fff; color: var(--ink); font-weight: 650; }
nav a.active, .button.primary { background: var(--ink); color: #fff; border-color: var(--ink); }
main { max-width: 1180px; margin: 0 auto; padding: 36px 24px 54px; }
.hero, .page-title { padding: 30px 0 22px; border-bottom: 1px solid var(--line); }
.eyebrow { color: var(--accent-2); font-size: 0.78rem; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }
h1 { margin: 8px 0 12px; max-width: 980px; font-size: clamp(2rem, 5vw, 4.25rem); line-height: 1.02; letter-spacing: 0; }
h2 { margin: 0 0 10px; font-size: 1.35rem; letter-spacing: 0; }
h3 { margin: 20px 0 8px; font-size: 1rem; letter-spacing: 0; }
p { max-width: 900px; color: var(--muted); }
.section { padding: 30px 0; border-bottom: 1px solid var(--line); }
.section-heading { display: flex; justify-content: space-between; gap: 24px; align-items: end; margin-bottom: 16px; }
.section-heading p { margin: 0; }
.stat-grid, .link-grid, .download-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; }
.stat-card, .link-card, .note-card { display: block; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 16px; min-width: 0; }
.stat-card span, .link-card span { display: block; color: var(--muted); font-size: .82rem; font-weight: 700; }
.stat-card strong { display: block; margin: 4px 0; font-size: 1.8rem; line-height: 1.1; }
.stat-card small, .link-card small { display: block; color: var(--muted); }
.link-card strong { display: block; margin: 4px 0; color: var(--ink); }
.metric-band { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.metric-band a { display: block; border: 1px solid var(--line); border-radius: 8px; padding: 16px; background: #fff; color: var(--ink); }
.table-wrap { width: 100%; overflow-x: auto; border: 1px solid var(--line); border-radius: 8px; background: #fff; }
table { width: 100%; border-collapse: collapse; min-width: 720px; }
th, td { padding: 10px 12px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
th { color: var(--muted); font-size: .78rem; text-transform: uppercase; letter-spacing: .04em; background: #fbfaf7; }
td { font-size: .92rem; }
.download-grid a { display: block; background: #fff; border: 1px solid var(--line); border-radius: 7px; padding: 12px; overflow-wrap: anywhere; }
.site-footer { display: flex; justify-content: space-between; gap: 24px; padding: 28px; border-top: 1px solid var(--line); background: #ebe8dc; }
.site-footer p { margin: 4px 0 0; }
.footer-links { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; justify-content: flex-end; }
.callout { padding: 14px 16px; border-left: 4px solid var(--accent); background: #fff; border-radius: 0 8px 8px 0; }
.small { font-size: .88rem; color: var(--muted); }
@media (max-width: 760px) {
  .site-header, .site-footer, .section-heading { display: block; }
  nav, .footer-links { justify-content: flex-start; margin-top: 12px; }
  main { padding: 24px 16px 40px; }
  .metric-band { grid-template-columns: 1fr; }
}
"""


def cadot_format_size(size_bytes: int) -> str:
    if size_bytes >= 1024**3:
        return f"{size_bytes / 1024**3:.2f} GB"
    if size_bytes >= 1024**2:
        return f"{size_bytes / 1024**2:.1f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"


def cadot_three_metric_path(name: str) -> Path:
    return sample_results_base(ACTIVE_SITE_SAMPLE) / THREE_METRIC_TABLE_FILES[name]


def cadot_download_path(filename: str) -> Path:
    return sample_results_base(ACTIVE_SITE_SAMPLE) / THREE_METRIC_DOWNLOAD_FILES[filename]


def cadot_validate_three_metric_manifest(manifest: dict[str, Any]) -> None:
    expected = {
        "country_sample": "cadot_broad_156",
        "selected_reporters": 156,
        "raw_files_processed": 3787,
        "product_id_mode": "harmonized_hs6_family",
        "harmonization_method": "lt_hgl_weighted_hs1992",
        "harmonization_target": "HS1992/H0",
        "fixed_universe_source": "world_broad",
    }
    mismatches = {
        key: {"expected": value, "actual": manifest.get(key)}
        for key, value in expected.items()
        if manifest.get(key) != value
    }
    if manifest.get("product_universe_counts") != {"Exports": 5037, "Imports": 5037}:
        mismatches["product_universe_counts"] = {
            "expected": {"Exports": 5037, "Imports": 5037},
            "actual": manifest.get("product_universe_counts"),
        }
    if mismatches:
        raise RuntimeError(f"Cadot three-metric manifest has stale or invalid metadata: {mismatches}")


def cadot_load_three_metric_site_data() -> dict[str, Any]:
    manifest_path = cadot_download_path("cadot_three_metric_manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cadot_validate_three_metric_manifest(manifest)
    validation = pd.read_csv(cadot_three_metric_path("three_metric_validation"))
    require_columns(validation, "Three-metric validation checks", {"check", "passed", "details"})
    failed = validation[~validation_passed(validation["passed"])]
    if not failed.empty:
        raise RuntimeError(f"Three-metric validation checks failed: {failed.to_dict(orient='records')}")
    nonenergy_manifest_path = cadot_download_path("nonenergy_visualization_manifest.json")
    nonenergy_manifest = json.loads(nonenergy_manifest_path.read_text(encoding="utf-8"))
    expected_nonenergy = {
        "country_sample": "cadot_broad_156",
        "benchmark_sample": "world_broad",
        "reporters": 156,
        "year_start": 2000,
        "year_end": 2024,
        "product_id_mode": "harmonized_hs6_family",
        "harmonization_method": "lt_hgl_weighted_hs1992",
        "harmonization_target": "HS1992/H0",
        "fixed_universe_source": "world_broad",
        "nonenergy_filter": "mapped_nonenergy_bins_only",
    }
    stale_nonenergy = {
        key: {"expected": value, "actual": nonenergy_manifest.get(key)}
        for key, value in expected_nonenergy.items()
        if nonenergy_manifest.get(key) != value
    }
    if stale_nonenergy:
        raise RuntimeError(
            f"Cadot non-energy visualization manifest is stale or invalid: {stale_nonenergy}"
        )
    nonenergy_validation = pd.read_csv(
        cadot_download_path("nonenergy_visualization_validation_checks.csv")
    )
    require_columns(
        nonenergy_validation,
        "Non-energy visualization validation",
        {"check", "passed", "value", "expected"},
    )
    failed_nonenergy = nonenergy_validation[
        ~validation_passed(nonenergy_validation["passed"])
    ]
    if not failed_nonenergy.empty:
        raise RuntimeError(
            "Non-energy visualization validation checks failed: "
            f"{failed_nonenergy.to_dict(orient='records')}"
        )
    exposure_manifest_path = cadot_download_path("run_manifest_world_large_product_exposure.json")
    exposure_manifest = json.loads(exposure_manifest_path.read_text(encoding="utf-8"))
    expected_exposure = {
        "country_sample": "cadot_broad_156",
        "benchmark_sample": "world_broad",
        "flow": "Exports",
        "product_id_mode": "harmonized_hs6_family",
        "start_year": 2000,
        "end_year": 2024,
    }
    stale_exposure = {
        key: {"expected": value, "actual": exposure_manifest.get(key)}
        for key, value in expected_exposure.items()
        if exposure_manifest.get(key) != value
    }
    if exposure_manifest.get("variants") != ["baseline", "noncommodity_broad"]:
        stale_exposure["variants"] = {
            "expected": ["baseline", "noncommodity_broad"],
            "actual": exposure_manifest.get("variants"),
        }
    if stale_exposure:
        raise RuntimeError(
            f"Cadot world-product exposure manifest is stale or invalid: {stale_exposure}"
        )
    exposure_validation = pd.read_csv(
        cadot_download_path("world_large_product_exposure_validation_checks.csv")
    )
    require_columns(
        exposure_validation,
        "World-product exposure validation",
        {"check", "passed", "value", "expected"},
    )
    failed_exposure = exposure_validation[
        ~validation_passed(exposure_validation["passed"])
    ]
    if not failed_exposure.empty:
        raise RuntimeError(
            "World-product exposure validation checks failed: "
            f"{failed_exposure.to_dict(orient='records')}"
        )
    data = {
        "manifest": manifest,
        "validation": validation,
        "nonenergy_manifest": nonenergy_manifest,
        "nonenergy_validation": nonenergy_validation,
        "exposure_manifest": exposure_manifest,
        "exposure_validation": exposure_validation,
        "headline": pd.read_csv(cadot_three_metric_path("three_metric_headline")),
        "yearly": pd.read_csv(cadot_three_metric_path("three_metric_yearly")),
        "rankings": pd.read_csv(cadot_three_metric_path("three_metric_rankings")),
        "ex02": pd.read_csv(cadot_three_metric_path("three_metric_ex02")),
        "ex03": pd.read_csv(cadot_three_metric_path("three_metric_ex03")),
        "ex04": pd.read_csv(cadot_three_metric_path("three_metric_ex04")),
        "ex06": pd.read_csv(cadot_three_metric_path("three_metric_ex06")),
        "ex10": pd.read_csv(cadot_three_metric_path("three_metric_ex10")),
        "ex11": pd.read_csv(
            cadot_three_metric_path("three_metric_ex11"),
            usecols=["country", "iso3", "year", "flow", "metric", "cmd_code", "product_label", "trade_value", "abs_loo_contribution"],
        ),
        "ex12": pd.read_csv(cadot_three_metric_path("three_metric_ex12")),
        "nonenergy_annual": pd.read_csv(
            cadot_download_path("nonenergy_import_metric_annual.csv")
        ),
        "nonenergy_snapshots": pd.read_csv(
            cadot_download_path("nonenergy_import_rank_bucket_snapshots.csv")
        ),
        "nonenergy_top_products": pd.read_csv(
            cadot_download_path("nonenergy_import_top_products_snapshots.csv"),
            dtype={"cmd_code": "string"},
        ),
        "nonenergy_drivers": pd.read_csv(
            cadot_download_path("nonenergy_import_rank_bucket_drivers.csv")
        ),
        "exposure_yearly": pd.read_csv(
            cadot_download_path("world_large_product_exposure_yearly_spearman.csv")
        ),
        "exposure_summary": pd.read_csv(
            cadot_download_path("world_large_product_exposure_spearman_summary.csv")
        ),
        "exposure_models": pd.read_csv(
            cadot_download_path("world_large_product_exposure_models.csv")
        ),
        "exposure_diagnostics": pd.read_csv(
            cadot_download_path("world_large_product_exposure_diagnostics.csv")
        ),
        "exposure_coverage": pd.read_csv(
            cadot_download_path("world_large_product_exposure_reporter_coverage.csv")
        ),
        "exposure_fixed_yearly": pd.read_csv(
            cadot_download_path("world_large_product_exposure_fixed_country_2018_2024.csv")
        ),
        "exposure_fixed_summary": pd.read_csv(
            cadot_download_path("world_large_product_exposure_fixed_country_2018_2024_summary.csv")
        ),
        "exposure_comparison": pd.read_csv(
            cadot_download_path("world_large_product_exposure_variant_comparison.csv")
        ),
        "exposure_removed": pd.read_csv(
            cadot_download_path("world_large_product_exposure_country_commodity_shares.csv")
        ),
        "all_metrics": pd.read_csv(
            sample_results_base(ACTIVE_SITE_SAMPLE) / "three_metric_tables/concentration_metric_all_years.csv",
            usecols=["country", "year", "flow", "dimension", "variant", "active_count", "gini", "theil", "hhi"],
        ),
    }
    for filename, artifact in nonenergy_manifest.get("output_artifacts", {}).items():
        source = cadot_download_path(filename)
        if not source.exists():
            raise FileNotFoundError(f"Manifest-listed non-energy artifact is missing: {source}")
        expected_hash = str(artifact.get("sha256", ""))
        actual_hash = file_sha256(source)
        if not expected_hash or actual_hash != expected_hash:
            raise RuntimeError(
                f"Non-energy artifact hash mismatch for {filename}: "
                f"expected {expected_hash}, found {actual_hash}"
            )

    annual = data["nonenergy_annual"]
    snapshots = data["nonenergy_snapshots"]
    top_products = data["nonenergy_top_products"]
    drivers = data["nonenergy_drivers"]
    structural_errors: list[str] = []
    if annual["reporter_code"].nunique() != 156:
        structural_errors.append("annual reporter count is not 156")
    if annual.duplicated(["reporter_code", "year", "flow"]).any():
        structural_errors.append("annual reporter-year-flow keys are duplicated")
    if not pd.to_numeric(annual["year"], errors="coerce").between(2000, 2024).all():
        structural_errors.append("annual years fall outside 2000-2024")
    if snapshots["reporter_code"].nunique() != 156 or not snapshots.groupby("reporter_code").size().eq(3).all():
        structural_errors.append("snapshots are not exactly three per reporter")
    if not top_products.groupby(["reporter_code", "snapshot"]).size().eq(10).all():
        structural_errors.append("top products are not exactly ten per reporter-snapshot")
    if drivers["reporter_code"].nunique() != 156 or not drivers.groupby("reporter_code").size().eq(3).all():
        structural_errors.append("drivers are not exactly three metrics per reporter")
    if structural_errors:
        raise RuntimeError(
            "Non-energy site artifacts fail structural validation: "
            + "; ".join(structural_errors)
        )
    return data


def cadot_publication_manifest_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[Path] = set()
    grouped_paths = [
        ("source", three_metric_source_paths(ACTIVE_SITE_SAMPLE)),
        ("download", three_metric_download_paths(ACTIVE_SITE_SAMPLE)),
    ]
    for group, mapping in grouped_paths:
        for name, path in mapping.items():
            if path in seen:
                continue
            seen.add(path)
            if not path.exists():
                raise FileNotFoundError(f"Required three-metric {group} artifact is missing: {path}")
            if path.name == "exercise_11_top_product_loo_contributions.csv":
                assert_csv_has_no_excluded_hs6(path, name)
            elif path.suffix.lower() == ".csv" or path.name.lower().endswith(".csv.gz"):
                assert_csv_has_no_excluded_hs6(path, name)
            columns = ""
            row_count = None
            if path.suffix.lower() == ".csv":
                header = pd.read_csv(path, nrows=0)
                columns = "|".join(str(col) for col in header.columns)
                if path.stat().st_size < 200 * 1024 * 1024:
                    with path.open("rb") as fh:
                        line_count = sum(chunk.count(b"\n") for chunk in iter(lambda: fh.read(1024 * 1024), b""))
                    row_count = max(line_count - 1, 0)
            rows.append(
                {
                    "group": group,
                    "name": name,
                    "path": str(path.relative_to(ROOT)),
                    "size_bytes": int(path.stat().st_size),
                    "mtime_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds"),
                    "sha256": file_sha256(path),
                    "row_count": row_count,
                    "columns": columns,
                }
            )
    return rows


def cadot_table(rows: list[dict[str, Any]], columns: list[tuple[str, str, str]]) -> str:
    return '<div class="table-wrap">' + table_rows(rows, columns) + "</div>"


def cadot_metric_value_column(metric: str) -> str:
    return {"gini": "gini", "theil": "theil", "hhi": "hhi"}[metric]


def cadot_metric_label(metric: str) -> str:
    return {"gini": "Gini", "theil": "Theil", "hhi": "HHI"}[metric]


def cadot_metric_convention(metric: str, chart_id: str | None = None) -> str:
    if metric == "gini":
        return "active-positive Gini"
    if metric == "theil":
        if chart_id in {"exercise3-trend", "exercise3-latest"}:
            return "within-bin active-product Theil"
        return "fixed-universe Theil"
    return "raw HHI"


def cadot_metric_definition(metric: str) -> str:
    definitions = {
        "gini": "The Gini site keeps the active-positive product Gini convention as the reference concentration measure.",
        "theil": "The Theil site uses fixed-universe product Theil: missing reporter products enter as zeros through the inactive margin. Exercise 3's legacy within-bin comparison is labeled separately as active-product Theil because that source table does not contain bin-specific fixed universes.",
        "hhi": "The HHI site reports raw Herfindahl-Hirschman concentration, the sum of squared item shares on the [0,1] scale.",
    }
    return definitions[metric]


def cadot_download_link(depth: int, filename: str) -> str:
    return cadot_asset_href(depth, f"assets/downloads/{filename}")


def cadot_download_grid(depth: int, filenames: list[str]) -> str:
    links = []
    for filename in filenames:
        links.append(f'<a href="{cadot_download_link(depth, filename)}">{escape(filename)}</a>')
    return '<div class="download-grid">' + "".join(links) + "</div>"


def cadot_metric_cards_from_frame(frame: pd.DataFrame) -> str:
    cards = []
    for metric in ["gini", "theil", "hhi"]:
        metric_frame = frame.copy()
        if "metric" in metric_frame.columns:
            metric_frame = three_metric_metric_rows(metric_frame, metric)
        value_col = three_metric_value_column(metric_frame, metric)
        value = None
        detail = "No numeric metric column found."
        if value_col and not metric_frame.empty:
            numeric = pd.to_numeric(metric_frame[value_col], errors="coerce").dropna()
            if not numeric.empty:
                value = float(numeric.median())
                detail = f"Median {value_col.replace('_', ' ')} across {len(metric_frame):,} rows."
        cards.append(
            f"""
            <article class="stat-card">
              <span>{cadot_metric_label(metric)}</span>
              <strong>{dec(value)}</strong>
              <small>{escape(THREE_METRIC_DEFINITIONS[metric])} {escape(detail)}</small>
            </article>
            """
        )
    return '<div class="stat-grid">' + "".join(cards) + "</div>"


def cadot_exercise_evidence_table(frame: pd.DataFrame, spec: dict[str, Any]) -> str:
    if frame.empty:
        return '<p class="small">No exercise rows are available.</p>'
    key = spec["short"]
    if key == "01":
        work = frame[frame["dimension"].astype(str).eq("product")].copy() if "dimension" in frame.columns else frame.copy()
        latest_year = int(pd.to_numeric(work["year"], errors="coerce").max())
        work = work[pd.to_numeric(work["year"], errors="coerce").eq(latest_year)].copy()
        rows = []
        for flow, group in work.groupby("flow", sort=True):
            rows.append(
                {
                    "flow": flow,
                    "year": latest_year,
                    "countries": group["country"].nunique(),
                    "median_gini": pd.to_numeric(group["gini"], errors="coerce").median(),
                    "median_theil": pd.to_numeric(group["theil"], errors="coerce").median(),
                    "median_hhi": pd.to_numeric(group["hhi"], errors="coerce").median(),
                }
            )
        return cadot_table(rows, [("flow", "Flow", "text"), ("year", "Year", "year"), ("countries", "Countries", "int"), ("median_gini", "Median Gini", "dec"), ("median_theil", "Median Theil", "dec"), ("median_hhi", "Median HHI", "dec")])
    if key in {"02", "12"}:
        table = frame.sort_values([col for col in ["metric", "flow", "horizon"] if col in frame.columns]).head(36)
        bucket_col = "concentration_bucket" if "concentration_bucket" in table.columns else "base_concentration_bucket"
        return cadot_table(clean_records(table, list(table.columns)), [("metric", "Metric", "text"), ("flow", "Flow", "text"), ("horizon", "Horizon", "int"), (bucket_col, "Bucket", "text"), ("observations", "Obs.", "int"), ("countries", "Countries", "int"), ("mean_annualized_trade_growth_log", "Mean trade growth", "pct")])
    if key == "03":
        summary = frame.groupby("import_bin", as_index=False).agg(
            rows=("country", "size"),
            countries=("country", "nunique"),
            median_import_value_share=("import_value_share", "median"),
            median_gini=("gini", "median"),
            median_theil=("theil_active", "median"),
            median_hhi=("hhi", "median"),
        )
        return cadot_table(clean_records(summary.sort_values("import_bin"), list(summary.columns)), [("import_bin", "Import bin", "text"), ("rows", "Rows", "int"), ("countries", "Countries", "int"), ("median_import_value_share", "Median import share", "pct"), ("median_gini", "Median Gini", "dec"), ("median_theil", "Median Theil", "dec"), ("median_hhi", "Median HHI", "dec")])
    if key == "04":
        latest_year = int(pd.to_numeric(frame["year"], errors="coerce").max())
        latest = frame[pd.to_numeric(frame["year"], errors="coerce").eq(latest_year)].sort_values("weighted_mean_source_hhi", ascending=False).head(20)
        return cadot_table(clean_records(latest, list(latest.columns)), [("country", "Country", "text"), ("year", "Year", "year"), ("import_products", "Import products", "int"), ("weighted_mean_top_supplier_share", "Weighted top supplier share", "pct"), ("weighted_mean_source_hhi", "Weighted source HHI", "dec"), ("share_products_top_supplier_ge_75", "Products >=75%", "pct")])
    if key == "06":
        work = frame[frame["dimension"].astype(str).eq("product")].copy() if "dimension" in frame.columns else frame.copy()
        summary = work.groupby(["variant", "flow"], as_index=False).agg(
            rows=("country", "size"),
            median_trade_share_removed=("trade_share_removed", "median"),
            median_gini=("gini", "median"),
            median_theil=("theil", "median"),
            median_hhi=("hhi", "median"),
        )
        return cadot_table(clean_records(summary.sort_values(["variant", "flow"]), list(summary.columns)), [("variant", "Variant", "text"), ("flow", "Flow", "text"), ("rows", "Rows", "int"), ("median_trade_share_removed", "Median removed share", "pct"), ("median_gini", "Median Gini", "dec"), ("median_theil", "Median Theil", "dec"), ("median_hhi", "Median HHI", "dec")])
    if key == "10":
        summary = frame.groupby(["flow", "benchmark_null"], as_index=False).agg(
            rows=("country", "size"),
            median_gini_gap=("actual_minus_sim_median_gini", "median"),
            median_theil_gap=("actual_minus_sim_median_theil", "median"),
            median_hhi_gap=("actual_minus_sim_median_hhi", "median"),
        )
        return cadot_table(clean_records(summary.sort_values(["flow", "benchmark_null"]), list(summary.columns)), [("flow", "Flow", "text"), ("benchmark_null", "Benchmark", "text"), ("rows", "Rows", "int"), ("median_gini_gap", "Median Gini gap", "dec"), ("median_theil_gap", "Median Theil gap", "dec"), ("median_hhi_gap", "Median HHI gap", "dec")])
    if key == "11":
        summary = frame.groupby(["metric", "flow", "cmd_code", "product_label"], as_index=False).agg(
            rows=("country", "size"),
            median_abs_contribution=("abs_loo_contribution", "median"),
            max_abs_contribution=("abs_loo_contribution", "max"),
        )
        summary = summary.sort_values("max_abs_contribution", ascending=False).head(30)
        return cadot_table(clean_records(summary, list(summary.columns)), [("metric", "Metric", "text"), ("flow", "Flow", "text"), ("product_label", "HS1992 product family", "text"), ("rows", "Rows", "int"), ("median_abs_contribution", "Median abs. contribution", "dec"), ("max_abs_contribution", "Max abs. contribution", "dec")])
    return cadot_table(clean_records(frame.head(30), list(frame.columns)), [(col, col.replace("_", " ").title(), "text") for col in frame.columns[:8]])


def cadot_metric_page(metric: str, data: dict[str, Any]) -> str:
    manifest = data["manifest"]
    value_col = cadot_metric_value_column(metric)
    latest = data["rankings"][data["rankings"]["metric"].astype(str).str.lower().eq(metric)].copy()
    ranking_rows = clean_records(latest.sort_values(["flow", "rank"]).head(20), list(latest.columns))
    yearly = data["yearly"].copy()
    yearly = yearly[yearly["dimension"].astype(str).eq("product")]
    latest_year = int(pd.to_numeric(yearly["year"], errors="coerce").max())
    yearly = yearly[pd.to_numeric(yearly["year"], errors="coerce").ge(latest_year - 4)].copy()
    yearly_col = f"median_{metric}"
    yearly_rows = clean_records(yearly.sort_values(["flow", "year"]), list(yearly.columns))
    exercise_rows = []
    for spec in EXERCISE_PAGE_SPECS:
        exercise_rows.append(
            {
                "exercise": f"Exercise {spec['short']}",
                "question": spec["title"].split(":", 1)[-1].strip(),
                "page": f'<a href="../exercises/exercise-{spec["short"]}.html">Open page</a>',
                "download": f'<a href="../assets/downloads/{escape(spec["source"])}">{escape(spec["source"])}</a>',
            }
        )
    appendix_link = ""
    if metric == "theil":
        appendix_link = '<p><a class="button" href="appendix.html">Open Theil product-destination appendix</a></p>'
    body = f"""
    <section class="hero">
      <div class="eyebrow">{escape(cadot_metric_label(metric))} site</div>
      <h1>{escape(cadot_metric_label(metric))} Trade Concentration</h1>
      <p>{escape(cadot_metric_definition(metric))} Product-dependent outputs are LT/HGL-weighted HS1992/H0 product families, with HS6 999999 excluded before conversion.</p>
      <div class="stat-grid">
        <article class="stat-card"><span>Reporters</span><strong>{int(manifest['selected_reporters']):,}</strong><small>Cadot-style broad sample</small></article>
        <article class="stat-card"><span>Raw files</span><strong>{int(manifest['raw_files_processed']):,}</strong><small>Final Comtrade files processed</small></article>
        <article class="stat-card"><span>Product universe</span><strong>{int(manifest['product_universe_counts']['Exports']):,}</strong><small>HS1992/H0 families by flow</small></article>
      </div>
      {appendix_link}
    </section>
    <section class="section">
      <div class="section-heading"><h2>Latest Rankings</h2><p>Highest latest available values by flow.</p></div>
      {cadot_table(ranking_rows, [("flow", "Flow", "text"), ("rank", "Rank", "int"), ("country", "Country", "text"), ("year", "Year", "year"), ("metric_value", cadot_metric_label(metric), "dec"), ("active_count", "Active products", "int"), ("total_trade_value", "Trade value", "money")])}
    </section>
    <section class="section">
      <div class="section-heading"><h2>Recent Medians</h2><p>Reporter-year product rows, common Gini/Theil/HHI keys where possible.</p></div>
      {cadot_table(yearly_rows, [("flow", "Flow", "text"), ("year", "Year", "year"), ("countries", "Countries", "int"), (yearly_col, f"Median {cadot_metric_label(metric)}", "dec"), ("median_active_count", "Median active products", "int"), ("median_total_trade_value", "Median trade value", "money")])}
    </section>
    <section class="section">
      <div class="section-heading"><h2>Exercise Pages</h2><p>Every rerun exercise is linked from each metric site.</p></div>
      {cadot_table(exercise_rows, [("exercise", "Exercise", "text"), ("question", "Question", "text"), ("page", "Page", "text"), ("download", "Download", "text")])}
    </section>
    <section class="section">
      <div class="section-heading"><h2>Downloads</h2><p>Metric-level artifacts and validation outputs.</p></div>
      {cadot_download_grid(1, ["metric_headline_product_panel.csv", "metric_yearly_summary.csv", "metric_latest_rankings.csv", "validation_checks.csv", "cadot_three_metric_manifest.json"])}
    </section>
    """
    return cadot_page(f"{cadot_metric_label(metric)} Site", metric, body, depth=1)


def cadot_exercises_index_page(data: dict[str, Any]) -> str:
    cards = []
    for spec in EXERCISE_PAGE_SPECS:
        cards.append(
            f"""
            <a class="link-card" href="exercise-{spec['short']}.html">
              <span>Exercise {escape(spec['short'])}</span>
              <strong>{escape(spec['title'].split(':', 1)[-1].strip())}</strong>
              <small>{escape(spec['question'])}</small>
            </a>
            """
        )
    body = f"""
    <section class="page-title">
      <div class="eyebrow">Exercise index</div>
      <h1>Gini, Theil, and HHI Exercise Pages</h1>
      <p>Each page uses the harmonized Cadot 156 rerun and links to its source download. The exercise sample is 2000-2024 available observations with complete-case flags where relevant.</p>
    </section>
    <section class="section link-grid">
      {"".join(cards)}
    </section>
    """
    return cadot_page("Exercises", "exercises", body, depth=1)


def cadot_exercise_page(spec: dict[str, Any], data: dict[str, Any]) -> str:
    frame = data[spec["data_key"]]
    body = f"""
    <section class="page-title">
      <div class="eyebrow">Exercise {escape(spec['short'])}</div>
      <h1>{escape(spec['title'])}</h1>
      <p>{escape(spec['question'])}</p>
    </section>
    <section class="section">
      <div class="section-heading"><h2>Metric Results</h2><p>Gini, fixed-universe product Theil, and raw HHI are computed on harmonized HS1992/H0 product-family outputs where product identity matters.</p></div>
      {cadot_metric_cards_from_frame(frame)}
    </section>
    <section class="section">
      <div class="section-heading"><h2>Evidence Table</h2><p>{escape(spec['answer'])}</p></div>
      {cadot_exercise_evidence_table(frame, spec)}
    </section>
    <section class="section">
      <div class="section-heading"><h2>Downloads</h2><p>Sample: Cadot-style 156 reporters, 2000-2024, available-observation rows with complete-case flags where relevant.</p></div>
      <p class="callout">Product-dependent calculations exclude HS6 <strong>999999</strong> before LT/HGL weighted conversion to HS1992/H0 product families. Partner-only concentration follows the partner-total convention and excludes partner code 0.</p>
      {cadot_download_grid(1, list(dict.fromkeys(spec["downloads"] + ["cadot_three_metric_manifest.json", "three_metric_adversarial_review.md"])))}
    </section>
    """
    return cadot_page(spec["title"], "exercises", body, depth=1)


def cadot_downloads_page(data: dict[str, Any]) -> str:
    rows = []
    for filename, source in three_metric_download_paths(ACTIVE_SITE_SAMPLE).items():
        rows.append(
            {
                "file": f'<a href="../assets/downloads/{escape(filename)}">{escape(filename)}</a>',
                "size": cadot_format_size(source.stat().st_size),
                "kind": source.suffix.lstrip(".") or "artifact",
            }
        )
    body = f"""
    <section class="page-title">
      <div class="eyebrow">Downloads</div>
      <h1>Harmonized Cadot 156 Artifacts</h1>
      <p>The previous native-HS Cadot run is superseded by these LT/HGL-weighted HS1992/H0 outputs. Exercise 11 is published only as a compressed CSV to stay below GitHub file-size limits.</p>
    </section>
    <section class="section">
      {cadot_table(rows, [("file", "File", "text"), ("size", "Size", "text"), ("kind", "Type", "text")])}
    </section>
    """
    return cadot_page("Downloads", "downloads", body, depth=1)


def cadot_theil_appendix_page(data: dict[str, Any]) -> str:
    cell = data["all_metrics"]
    cell = cell[cell["dimension"].astype(str).eq("product_partner_cell")].copy()
    latest_year = int(pd.to_numeric(cell["year"], errors="coerce").max())
    recent = cell[pd.to_numeric(cell["year"], errors="coerce").ge(latest_year - 4)]
    summary = recent.groupby(["flow", "year"], as_index=False).agg(
        countries=("country", "nunique"),
        median_cell_theil=("theil", "median"),
        median_cell_gini=("gini", "median"),
        median_cell_hhi=("hhi", "median"),
        median_active_cells=("active_count", "median"),
    )
    body = f"""
    <section class="page-title">
      <div class="eyebrow">Theil appendix</div>
      <h1>Product-Destination / Cell Theil Analogue</h1>
      <p>This appendix is not the headline Theil. The headline remains fixed-universe product Theil; this page reports the HS1992 product-partner-cell analogue for comparison.</p>
    </section>
    <section class="section">
      <div class="section-heading"><h2>Recent Cell-Metric Medians</h2><p>Rows are reporter-year-flow product-partner-cell concentration outputs.</p></div>
      {cadot_table(clean_records(summary.sort_values(["flow", "year"]), list(summary.columns)), [("flow", "Flow", "text"), ("year", "Year", "year"), ("countries", "Countries", "int"), ("median_cell_theil", "Median cell Theil", "dec"), ("median_cell_gini", "Median cell Gini", "dec"), ("median_cell_hhi", "Median cell HHI", "dec"), ("median_active_cells", "Median active cells", "int")])}
    </section>
    <section class="section">
      <div class="section-heading"><h2>Related Downloads</h2><p>The cell rows are in the all-years concentration panel.</p></div>
      {cadot_download_grid(1, ["concentration_metric_all_years.csv", "cadot_three_metric_manifest.json", "three_metric_adversarial_review.md"])}
    </section>
    """
    return cadot_page("Theil Appendix", "theil", body, depth=1)


def cadot_root_page(data: dict[str, Any]) -> str:
    manifest = data["manifest"]
    validation = data["validation"]
    failed = validation[~validation_passed(validation["passed"])]
    latest_year = int(pd.to_numeric(data["headline"]["year"], errors="coerce").max())
    product = data["headline"][data["headline"]["dimension"].astype(str).eq("product")]
    latest = product[pd.to_numeric(product["year"], errors="coerce").eq(latest_year)]
    rows = []
    for flow, group in latest.groupby("flow", sort=True):
        rows.append(
            {
                "flow": flow,
                "year": latest_year,
                "countries": group["country"].nunique(),
                "median_gini": pd.to_numeric(group["gini"], errors="coerce").median(),
                "median_theil": pd.to_numeric(group["theil"], errors="coerce").median(),
                "median_hhi": pd.to_numeric(group["hhi"], errors="coerce").median(),
            }
        )
    exercise_cards = "".join(
        f'<a class="link-card" href="exercises/exercise-{spec["short"]}.html"><span>Exercise {escape(spec["short"])}</span><strong>{escape(spec["title"].split(":", 1)[-1].strip())}</strong><small>{escape(spec["source"])}</small></a>'
        for spec in EXERCISE_PAGE_SPECS
    )
    body = f"""
    <section class="hero">
      <div class="eyebrow">Harmonized Cadot 156 three-metric bundle</div>
      <h1>Trade Concentration Across Gini, Theil, and HHI</h1>
      <p>Three linked sites built from one harmonized LT/HGL HS1992/H0 Cadot-style 156-reporter run. Product-dependent outputs use the 2000-2024 union of positive world_broad harmonized product-family support by flow; missing reporter products are zeros for fixed-universe Theil.</p>
      <div class="stat-grid">
        <article class="stat-card"><span>Reporters</span><strong>{int(manifest['selected_reporters']):,}</strong><small>Cadot-style broad sample</small></article>
        <article class="stat-card"><span>Raw files</span><strong>{int(manifest['raw_files_processed']):,}</strong><small>Final annual files processed</small></article>
        <article class="stat-card"><span>Validation</span><strong>{len(validation) - len(failed)}/{len(validation)}</strong><small>Hard checks passed</small></article>
      </div>
    </section>
    <section class="section">
      <div class="section-heading"><h2>Metric Sites</h2><p>Each site links back to the others at the bottom and includes exercise-page links.</p></div>
      <div class="metric-band">
        <a href="gini/"><strong>Gini</strong><br><span>Active-positive Gini reference convention.</span></a>
        <a href="theil/"><strong>Theil</strong><br><span>Fixed-universe product Theil with inactive margin.</span></a>
        <a href="hhi/"><strong>HHI</strong><br><span>Raw sum of squared shares on [0,1].</span></a>
      </div>
    </section>
    <section class="section">
      <div class="section-heading"><h2>Latest Product-Metric Medians</h2><p>LT/HGL-weighted HS1992/H0 product-family rows.</p></div>
      {cadot_table(rows, [("flow", "Flow", "text"), ("year", "Year", "year"), ("countries", "Countries", "int"), ("median_gini", "Median Gini", "dec"), ("median_theil", "Median Theil", "dec"), ("median_hhi", "Median HHI", "dec")])}
    </section>
    <section class="section">
      <div class="section-heading"><h2>Exercises</h2><p>Every Gini exercise has been rerun or ported for Theil and HHI.</p></div>
      <div class="link-grid">{exercise_cards}</div>
    </section>
    """
    return cadot_page("Hub", "hub", body, depth=0)


def cadot_copy_three_metric_downloads(output: Path) -> None:
    for filename, source in three_metric_download_paths(ACTIVE_SITE_SAMPLE).items():
        if filename == "exercise_11_top_product_loo_contributions.csv":
            raise RuntimeError("Raw Exercise 11 CSV must not be published.")
        if not source.exists():
            raise FileNotFoundError(f"Required downloadable artifact is missing: {source}")
        assert_csv_has_no_excluded_hs6(source, filename)
        shutil.copy2(source, output / "assets/downloads" / filename)


def cadot_write_site_file(output: Path, relative_path: str, html: str) -> None:
    target = output / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html, encoding="utf-8")


CADOT_EXERCISE_GROUPS = {
    "extension": ["01", "02", "06", "10", "12"],
    "imports": ["03", "04", "11"],
}

CADOT_FIGURE_CAPTIONS = {
    "ex1_median_concentration_over_time": "Cadot 156 median concentration over time. The interactive chart on this page carries the selected metric; this figure is the shared visual benchmark.",
    "ex1_import_vs_export_product_gini_over_time": "Import and export product concentration over time for the Cadot 156 sample.",
    "ex1_country_product_gini_lines": "Country trajectories for product concentration in the Cadot 156 sample.",
    "ex3_value_share": "Median import value share by BEC-style bin in the Cadot 156 sample.",
    "ex3_leave_one_out": "Latest-year import-bin concentration comparison across Gini, Theil, and HHI in the Cadot sample.",
    "ex4_supplier_time": "Median dominant-supplier exposure through time for Cadot-sample importers.",
    "ex4_supplier_distribution": "Latest-year top-supplier-share distribution across Cadot-sample importer-product rows.",
    "ex6_before_after": "Before-versus-after concentration after HS2 exclusions in the Cadot rerun.",
    "ex6_removed": "Trade share removed by HS2 exclusion specification in the Cadot rerun.",
    "ex10_actual_vs_benchmark": "Observed concentration versus the HS2-preserving benchmark in the Cadot rerun.",
    "ex10_percentile": "Share of observations above the 95th percentile of the benchmark distribution in the Cadot rerun (Theil panel uses the published active-count percentile field).",
    "ex11_coefficients": "Latest-year median absolute leave-one-out product contribution by metric and flow in the Cadot rerun.",
    "ex11_export_linkage_4pct": "Latest-year product trade values by equal-count leave-one-out contribution bins in the Cadot rerun.",
    "ex11_hs2_linkage_4pct": "Latest-year HS2 trade values by equal-count summed leave-one-out contribution bins in the Cadot rerun.",
    "ex11_india_supplier_scatter": "India latest-year product trade values against absolute leave-one-out contributions in the Cadot rerun.",
}

CADOT_EXERCISE_FIGURES = {
    "01": ["ex1_median_concentration_over_time", "ex1_import_vs_export_product_gini_over_time", "ex1_country_product_gini_lines"],
    "02": [],
    "03": ["ex3_value_share", "ex3_leave_one_out"],
    "04": ["ex4_supplier_time", "ex4_supplier_distribution"],
    "06": ["ex6_before_after", "ex6_removed"],
    "10": ["ex10_actual_vs_benchmark", "ex10_percentile"],
    "11": ["ex11_coefficients", "ex11_export_linkage_4pct", "ex11_hs2_linkage_4pct", "ex11_india_supplier_scatter"],
    "12": [],
}

CADOT_GRAPH_QUESTIONS = {
    "exposure-gdp-exposure": {
        "question": "Does GDP remain positively correlated with exposure to globally large export products after broad primary commodities are removed?",
        "supports": "The non-commodity line stays positive or moves closer to zero only in isolated years, rather than flipping sign persistently.",
        "weakens": "Removing broad primary products makes the GDP-exposure relationship mostly vanish or turn negative through long stretches of the panel.",
    },
    "exposure-gdp-alignment": {
        "question": "Does GDP remain positively correlated with within-country product alignment once broad primary commodities are removed?",
        "supports": "The non-commodity alignment series remains positive and close to the baseline path across years.",
        "weakens": "The non-commodity alignment series collapses, changes sign, or diverges sharply from baseline for many years.",
    },
    "exercise1-map": {
        "question": "Is high {metric} broad across countries, or driven by only a few outliers?",
        "supports": "Many countries remain high on the common color scale rather than one or two countries driving the pattern.",
        "weakens": "Only a small number of countries have high values while most of the map remains low.",
    },
    "exercise1-lines": {
        "question": "Is {metric} persistent within countries through time?",
        "supports": "Country trajectories remain elevated across multiple years instead of collapsing after one cross-section.",
        "weakens": "Country values are dominated by isolated annual spikes or fall sharply through the panel.",
    },
    "exercise1-ranking": {
        "question": "Which countries sit at the top of the latest {metric} distribution?",
        "supports": "The ranking identifies a stable upper group rather than a single extreme country.",
        "weakens": "The upper tail is effectively one observation with a large gap to the rest.",
    },
    "exercise2-growth": {
        "question": "Do later trade-growth paths differ across base-{metric} buckets?",
        "supports": "Mean annualized growth differs systematically across ordered concentration buckets.",
        "weakens": "Bucket means are similar, unordered, or based on very different samples.",
    },
    "exercise2-products": {
        "question": "Do base-{metric} buckets predict different active-product growth?",
        "supports": "Active-product growth changes systematically across the concentration buckets.",
        "weakens": "Product-count growth is flat or unstable across buckets.",
    },
    "exercise3-trend": {
        "question": "Which BEC-style import bins remain most concentrated in {metric} through time?",
        "supports": "One or more economically meaningful bins stay above the others across years.",
        "weakens": "The bin ordering is unstable or concentrated bins carry negligible import value.",
    },
    "exercise3-latest": {
        "question": "Which import bins have the highest latest-year {metric}?",
        "supports": "The latest comparison identifies concentrated bins with material import shares.",
        "weakens": "All bins have similar values or the highest bin is economically tiny.",
    },
    "exercise3-nonenergy-map": {
        "question": "Does import {metric} remain widespread after removing the Exercise 3 energy bin?",
        "supports": "Many Cadot reporters remain concentrated on the fixed non-energy color scale.",
        "weakens": "Most countries become diffuse once energy is removed.",
    },
    "exercise3-nonenergy-lines": {
        "question": "Is non-energy import {metric} persistent within countries?",
        "supports": "Selected country lines remain elevated across the available 2000-2024 panel.",
        "weakens": "The non-energy pattern is driven by isolated years or temporary shocks.",
    },
    "rank-bucket-overview": {
        "question": "Which part of the non-energy import basket changes: the top five, upper tier, middle tail, or long tail?",
        "supports": "The start, midpoint, and end bars reveal whether change comes from top-product gains or tail compression.",
        "weakens": "All rank buckets remain nearly unchanged across the three snapshots.",
    },
    "rank-bucket-country-chart": {
        "question": "What changed inside the selected country's non-energy basket?",
        "supports": "The focused bars and top-product list identify the products and rank ranges behind the change.",
        "weakens": "The selected country's aggregate change cannot be linked to a visible rank bucket or product family.",
    },
    "exercise4-trend": {
        "question": "Does dominant sourcing remain persistent through time?",
        "supports": "Weighted top-supplier shares and source HHI remain high across years.",
        "weakens": "Supplier exposure becomes broadly diffuse through the panel.",
    },
    "exercise4-latest": {
        "question": "Which importers have the strongest latest dominant-supplier exposure?",
        "supports": "The ranking identifies multiple importers with economically large top-supplier shares.",
        "weakens": "Only one importer has high exposure or the ranked values are small.",
    },
    "exercise6-trend": {
        "question": "Does {metric} collapse after removing lumpy HS2 sectors?",
        "supports": "The full-exclusion path falls sharply relative to baseline.",
        "weakens": "The baseline and exclusion paths remain close despite removed trade value.",
    },
    "exercise6-sensitivity": {
        "question": "Which HS2 exclusions move {metric} most?",
        "supports": "Specific chapters produce large metric changes relative to their removed trade shares.",
        "weakens": "All exclusion effects are small or proportional to mechanically removed value.",
    },
    "exercise10-trend": {
        "question": "Is observed {metric} above the selected random benchmark through time?",
        "supports": "The actual series remains above the simulation median across most years.",
        "weakens": "Actual and simulated paths overlap closely.",
    },
    "exercise10-latest": {
        "question": "Which countries sit furthest above the latest {metric} benchmark?",
        "supports": "Many countries have positive, economically meaningful actual-minus-simulated gaps.",
        "weakens": "Gaps are close to zero or concentrated in one country.",
    },
    "exercise11-trend": {
        "question": "How large are product leave-one-out contributions to {metric} through time?",
        "supports": "Median or maximum absolute contributions remain economically visible across years.",
        "weakens": "Contributions are uniformly tiny or unstable.",
    },
    "exercise11-top": {
        "question": "Which HS1992 product families drive the largest latest {metric} contributions?",
        "supports": "The ranking identifies interpretable product families rather than residual codes.",
        "weakens": "Top contributions are tiny, unstable, or dominated by unidentified products.",
    },
    "exercise12-growth": {
        "question": "How does later trade growth vary across base-{metric} buckets?",
        "supports": "Trade-growth means differ systematically across ordered base-concentration buckets.",
        "weakens": "The bucket pattern is flat or changes sign across nearby horizons.",
    },
    "exercise12-components": {
        "question": "Do product, partner, and product-partner-cell growth channels differ by base-{metric} bucket?",
        "supports": "The grouped components reveal a consistent extensive-margin channel.",
        "weakens": "All components are similar or the ordering is unstable across buckets.",
    },
}

CADOT_FIGURE_QUESTION_ALIASES = {
    "ex1_median_concentration_over_time": "exercise1-lines",
    "ex1_import_vs_export_product_gini_over_time": "exercise1-lines",
    "ex1_country_product_gini_lines": "exercise1-lines",
    "ex3_value_share": "exercise3-latest",
    "ex3_leave_one_out": "exercise3-latest",
    "ex4_supplier_time": "exercise4-trend",
    "ex4_supplier_distribution": "exercise4-latest",
    "ex6_before_after": "exercise6-trend",
    "ex6_removed": "exercise6-sensitivity",
    "ex10_actual_vs_benchmark": "exercise10-trend",
    "ex10_percentile": "exercise10-latest",
    "ex11_coefficients": "exercise11-trend",
    "ex11_export_linkage_4pct": "exercise11-top",
    "ex11_hs2_linkage_4pct": "exercise11-top",
    "ex11_india_supplier_scatter": "exercise11-top",
}
for figure_key, chart_key in CADOT_FIGURE_QUESTION_ALIASES.items():
    CADOT_GRAPH_QUESTIONS[figure_key] = dict(CADOT_GRAPH_QUESTIONS[chart_key])


def cadot_nav(depth: int, active: str) -> str:
    links = [
        ("hub", "Hub", "index.html"),
        ("exposure", "Exposure", "exposure/"),
        ("gini", "Gini", "gini/"),
        ("theil", "Theil", "theil/"),
        ("hhi", "HHI", "hhi/"),
        ("exercises", "Exercises", "exercises/"),
        ("downloads", "Downloads", "downloads/"),
    ]
    items = []
    for key, label, href in links:
        cls = ' class="active"' if key == active else ""
        items.append(f'<a{cls} href="{cadot_asset_href(depth, href)}">{escape(label)}</a>')
    return '<nav aria-label="Primary navigation">' + "".join(items) + "</nav>"


def cadot_footer(depth: int) -> str:
    return f"""
  <footer class="site-footer cadot-footer">
    <div class="cadot-footer-copy">
      <strong>Three linked metric sites</strong>
      <p>Cadot-style 156 reporters, 2000-2024, LT/HGL-weighted HS1992/H0 product families. Product-dependent outputs exclude HS6 999999 before conversion; partner-only outputs exclude partner code 0.</p>
    </div>
    <div class="footer-links">
      <a href="{cadot_asset_href(depth, 'gini/')}">Gini</a>
      <a href="{cadot_asset_href(depth, 'theil/')}">Theil</a>
      <a href="{cadot_asset_href(depth, 'hhi/')}">HHI</a>
      <a href="{cadot_asset_href(depth, 'exposure/')}">Exposure</a>
      <a href="{cadot_asset_href(depth, 'exercises/')}">Exercise index</a>
      <a href="{cadot_asset_href(depth, 'downloads/')}">Downloads</a>
    </div>
  </footer>
    """


def cadot_page(title: str, active: str, body: str, depth: int, page_key: str, metric: str | None = None) -> str:
    build_stamp = now_utc().replace("-", "").replace(":", "").replace("+", "").replace("T", "").replace("Z", "")
    metric_attr = "" if metric is None else metric
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)} | Trade Concentration</title>
  <link rel="stylesheet" href="{cadot_asset_href(depth, f'assets/site.css?v={build_stamp}')}">
</head>
<body class="cadot-site" data-page="{escape(page_key)}" data-metric="{escape(metric_attr)}">
  <header class="site-header">
    <div class="header-inner">
      <a class="brand" href="{cadot_asset_href(depth, 'index.html')}">Trade Concentration</a>
      {cadot_nav(depth, active)}
    </div>
  </header>
  <main>
{body}
  </main>
  {cadot_footer(depth)}
  <script src="{cadot_asset_href(depth, 'assets/vendor/plotly.min.js')}"></script>
  <script src="{cadot_asset_href(depth, f'assets/site-data.js?v={build_stamp}')}"></script>
  <script src="{cadot_asset_href(depth, f'assets/site.js?v={build_stamp}')}"></script>
</body>
</html>
"""


def cadot_site_css() -> str:
    return site_css() + """
body.cadot-site {
  background: #f5f7fb;
}
.cadot-site .hero h1,
.cadot-site .page-title h1 {
  max-width: 980px;
}
.cadot-site .site-header {
  background: rgba(245, 247, 251, 0.96);
}
.cadot-site .site-footer {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  max-width: 1180px;
  padding-top: 28px;
  border-top: 1px solid var(--line);
}
.cadot-footer-copy {
  max-width: 760px;
}
.cadot-site .footer-links {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: flex-start;
  justify-content: flex-end;
}
.cadot-site .link-grid.three-up,
.cadot-site .metric-overview-grid,
.cadot-site .exercise-switch-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}
.cadot-site .metric-switch,
.cadot-site .subnav-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 16px;
}
.cadot-site .metric-switch a,
.cadot-site .subnav-chips a {
  display: inline-flex;
  align-items: center;
  min-height: 38px;
  padding: 8px 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--paper);
  color: var(--ink);
  font-weight: 650;
}
.cadot-site .metric-switch a.active,
.cadot-site .subnav-chips a.active {
  background: var(--ink);
  color: #fff;
  border-color: var(--ink);
}
.cadot-site .overview-band,
.cadot-site .summary-band {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
.cadot-site .chart-panel {
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 16px;
  box-shadow: var(--shadow);
}
.cadot-site .chart-panel h3 {
  margin: 0 0 6px;
  font-size: 18px;
}
.cadot-site .chart-panel p {
  margin: 0;
  font-size: 14px;
}
.cadot-site .section-note {
  margin-top: 10px;
  color: var(--muted);
  font-size: 13px;
}
.cadot-site .exercise-callout {
  background: var(--paper);
  border: 1px solid var(--line);
  border-left: 4px solid var(--accent);
  border-radius: 0 8px 8px 0;
  padding: 14px 16px;
}
.cadot-site .exercise-callout p {
  margin: 0;
}
.cadot-site .cadot-hypothesis-card {
  max-width: none;
}
.cadot-site .cadot-evidence-note {
  margin: 16px 0;
  box-shadow: none;
}
.cadot-site .chart-panel > .cadot-evidence-note {
  margin-bottom: 12px;
}
.cadot-site .embedded-tool-section {
  margin-top: 34px;
  padding-top: 30px;
  border-top: 1px solid var(--line);
}
.cadot-site .rank-bucket-side {
  top: 92px;
}
.cadot-site .rank-bucket-detail-title {
  font-weight: 800;
}
.cadot-site .rank-bucket-product-code {
  white-space: nowrap;
}
.cadot-site .year-control {
  min-width: min(320px, 100%);
}
.cadot-site .year-control input[type="range"] {
  width: 100%;
}
.cadot-site .metric-link-card,
.cadot-site .exercise-card {
  display: block;
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 16px;
  color: var(--ink);
  box-shadow: var(--shadow);
}
.cadot-site .metric-link-card span,
.cadot-site .exercise-card span {
  display: block;
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.cadot-site .metric-link-card strong,
.cadot-site .exercise-card strong {
  display: block;
  margin: 6px 0 8px;
  font-size: 18px;
  line-height: 1.2;
}
.cadot-site .metric-link-card small,
.cadot-site .exercise-card small {
  display: block;
  color: var(--muted);
}
.cadot-site .inline-link-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 12px;
}
.cadot-site .inline-link-row a {
  font-weight: 650;
}
.cadot-site .figure-stack {
  display: grid;
  gap: 18px;
}
.cadot-site .figure-stack .figure-row {
  margin-top: 0;
}
.cadot-site .metric-route-table table {
  min-width: 0;
}
.cadot-site .table-wrap {
  width: 100%;
  max-width: 100%;
  min-width: 0;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--paper);
}
.cadot-site .table-wrap table {
  min-width: 720px;
}
@media (max-width: 860px) {
  .cadot-site main,
  .cadot-site .section,
  .cadot-site .tool-section,
  .cadot-site .chart-panel,
  .cadot-site .tool-header,
  .cadot-site .controls,
  .cadot-site .year-control {
    min-width: 0;
    max-width: 100%;
  }
  .cadot-site .link-grid.three-up,
  .cadot-site .metric-overview-grid,
  .cadot-site .exercise-switch-grid,
  .cadot-site .overview-band,
  .cadot-site .summary-band {
    grid-template-columns: 1fr;
  }
  .cadot-site .site-footer {
    display: block;
  }
  .cadot-site .footer-links {
    justify-content: flex-start;
    margin-top: 12px;
  }
}
"""


def cadot_metric_exercise_path(metric: str, short: str) -> str:
    return f"{metric}/exercises/exercise-{short}.html"


def cadot_metric_exercises_index_path(metric: str) -> str:
    return f"{metric}/exercises/"


def cadot_figure_keys() -> list[str]:
    return sorted({key for keys in CADOT_EXERCISE_FIGURES.values() for key in keys})


def cadot_copy_figure_assets(output: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figures_dir = output / "assets/figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    for path in figures_dir.glob("*.png"):
        path.unlink()

    data = cadot_load_three_metric_site_data()
    metric_colors = {"gini": "#0f766e", "theil": "#2563eb", "hhi": "#b45309"}
    flow_colors = {"Exports": "#0f766e", "Imports": "#2563eb"}
    import_bin_order = ["energy", "intermediates", "capital_goods", "final_consumption", "unmapped_or_ambiguous"]
    variant_labels = {
        "baseline": "Baseline",
        "oil_only": "No HS27",
        "oil_aircraft": "No HS27+88",
        "oil_aircraft_precious": "No HS27+71+88",
        "full_exclusion": "Full exclusion",
    }

    def savefig(name: str) -> None:
        plt.tight_layout()
        plt.savefig(figures_dir / f"{name}.png", dpi=220, bbox_inches="tight")
        plt.close()

    def quantile_bins(values: pd.Series, bins: int = 25) -> pd.Series:
        numeric = pd.to_numeric(values, errors="coerce")
        valid = numeric.notna()
        out = pd.Series(index=values.index, dtype="float64")
        if int(valid.sum()) == 0:
            return out
        q = min(bins, int(valid.sum()))
        ranked = numeric[valid].rank(method="first")
        out.loc[valid] = pd.qcut(ranked, q=q, labels=False) + 1
        return out

    product_yearly = data["yearly"].copy()
    if "dimension" in product_yearly.columns:
        product_yearly = product_yearly[product_yearly["dimension"].astype(str).eq("product")].copy()
    if "variant" in product_yearly.columns:
        product_yearly = product_yearly[product_yearly["variant"].astype(str).eq("baseline")].copy()
    product_yearly["year"] = pd.to_numeric(product_yearly["year"], errors="coerce")
    product_yearly = product_yearly.dropna(subset=["year"]).copy()
    product_yearly["year"] = product_yearly["year"].astype(int)

    product_panel = data["headline"].copy()
    if "dimension" in product_panel.columns:
        product_panel = product_panel[product_panel["dimension"].astype(str).eq("product")].copy()
    if "variant" in product_panel.columns:
        product_panel = product_panel[product_panel["variant"].astype(str).eq("baseline")].copy()
    product_panel["year"] = pd.to_numeric(product_panel["year"], errors="coerce")
    product_panel = product_panel.dropna(subset=["year"]).copy()
    product_panel["year"] = product_panel["year"].astype(int)

    ex03 = data["ex03"].copy()
    ex03["year"] = pd.to_numeric(ex03["year"], errors="coerce")
    ex03 = ex03.dropna(subset=["year"]).copy()
    ex03["year"] = ex03["year"].astype(int)

    ex04 = data["ex04"].copy()
    ex04["year"] = pd.to_numeric(ex04["year"], errors="coerce")
    ex04 = ex04.dropna(subset=["year"]).copy()
    ex04["year"] = ex04["year"].astype(int)

    ex06 = data["ex06"].copy()
    if "dimension" in ex06.columns:
        ex06 = ex06[ex06["dimension"].astype(str).eq("product")].copy()
    ex06["year"] = pd.to_numeric(ex06["year"], errors="coerce")
    ex06 = ex06.dropna(subset=["year"]).copy()
    ex06["year"] = ex06["year"].astype(int)

    ex10 = data["ex10"].copy()
    ex10["year"] = pd.to_numeric(ex10["year"], errors="coerce")
    ex10 = ex10.dropna(subset=["year"]).copy()
    ex10["year"] = ex10["year"].astype(int)

    ex11 = data["ex11"].copy()
    ex11["year"] = pd.to_numeric(ex11["year"], errors="coerce")
    ex11["trade_value"] = pd.to_numeric(ex11["trade_value"], errors="coerce")
    ex11 = ex11.dropna(subset=["year", "trade_value", "abs_loo_contribution"]).copy()
    ex11["year"] = ex11["year"].astype(int)
    ex11["cmd_code"] = ex11["cmd_code"].astype(str).str.extract(r"(\d+)", expand=False).fillna("").str.zfill(6)
    ex11["hs2"] = ex11["cmd_code"].str[:2]

    plt.style.use("seaborn-v0_8-whitegrid")

    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8), sharex=True)
    for ax, metric in zip(axes, ["gini", "theil", "hhi"]):
        for flow in ["Exports", "Imports"]:
            rows = product_yearly[product_yearly["flow"].astype(str).eq(flow)].sort_values("year")
            ax.plot(rows["year"], pd.to_numeric(rows[f"median_{metric}"], errors="coerce"), label=flow, color=flow_colors[flow], linewidth=2.2)
        ax.set_title(cadot_metric_label(metric))
        ax.set_xlabel("Year")
        if metric == "gini":
            ax.set_ylabel("Median value")
    axes[0].legend(frameon=False)
    fig.suptitle("Cadot 156 product concentration medians over time", fontsize=14)
    savefig("ex1_median_concentration_over_time")

    fig, ax = plt.subplots(figsize=(11, 5.2))
    gini_yearly = product_yearly.sort_values(["flow", "year"])
    for flow in ["Exports", "Imports"]:
        rows = gini_yearly[gini_yearly["flow"].astype(str).eq(flow)]
        ax.plot(rows["year"], pd.to_numeric(rows["median_gini"], errors="coerce"), label=flow, color=flow_colors[flow], linewidth=2.4)
    ax.set_title("Cadot 156 median product Gini: exports versus imports")
    ax.set_xlabel("Year")
    ax.set_ylabel("Median Gini")
    ax.legend(frameon=False)
    savefig("ex1_import_vs_export_product_gini_over_time")

    fig, ax = plt.subplots(figsize=(11, 6))
    latest_rankings = data["rankings"].copy()
    latest_rankings = latest_rankings[
        latest_rankings["metric"].astype(str).eq("gini") & latest_rankings["flow"].astype(str).eq("Exports")
    ].sort_values("rank")
    selected_iso3 = latest_rankings["iso3"].head(8).tolist()
    country_lines = product_panel[
        product_panel["flow"].astype(str).eq("Exports") & product_panel["iso3"].astype(str).isin(selected_iso3)
    ].copy()
    for iso3 in selected_iso3:
        rows = country_lines[country_lines["iso3"].astype(str).eq(iso3)].sort_values("year")
        if rows.empty:
            continue
        ax.plot(rows["year"], pd.to_numeric(rows["gini"], errors="coerce"), linewidth=1.8, label=str(rows.iloc[0]["country"]))
    ax.set_title("Top latest-export Gini countries: product concentration trajectories")
    ax.set_xlabel("Year")
    ax.set_ylabel("Product Gini")
    ax.legend(frameon=False, ncol=2, fontsize=8)
    savefig("ex1_country_product_gini_lines")

    ex03_imports = ex03[ex03["flow"].astype(str).eq("Imports")].copy()
    latest_ex03_year = int(ex03_imports["year"].max())
    ex03_latest = (
        ex03_imports[ex03_imports["year"].eq(latest_ex03_year)]
        .groupby("import_bin", as_index=False)
        .agg(
            median_import_share=("import_value_share", "median"),
            gini=("gini", "median"),
            theil=("theil_active", "median"),
            hhi=("hhi", "median"),
        )
    )
    ex03_latest["import_bin"] = pd.Categorical(ex03_latest["import_bin"], categories=import_bin_order, ordered=True)
    ex03_latest = ex03_latest.sort_values("import_bin")

    fig, ax = plt.subplots(figsize=(10.5, 5.2))
    ax.bar(ex03_latest["import_bin"].astype(str).str.replace("_", " "), ex03_latest["median_import_share"], color="#0f766e")
    ax.set_title(f"Latest-year median import share by BEC-style bin ({latest_ex03_year})")
    ax.set_ylabel("Median import share")
    ax.tick_params(axis="x", rotation=25)
    savefig("ex3_value_share")

    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8))
    for ax, metric, title in zip(
        axes,
        ["gini", "theil", "hhi"],
        ["Gini", "Theil active", "HHI"],
    ):
        ax.bar(ex03_latest["import_bin"].astype(str).str.replace("_", " "), pd.to_numeric(ex03_latest[metric], errors="coerce"), color=metric_colors[metric], alpha=0.9)
        ax.set_title(title)
        ax.tick_params(axis="x", rotation=25)
        if metric == "gini":
            ax.set_ylabel("Latest median value")
    fig.suptitle(f"Latest-year import-bin concentration comparison ({latest_ex03_year})", fontsize=14)
    savefig("ex3_leave_one_out")

    ex04_yearly = (
        ex04.groupby("year", as_index=False)
        .agg(
            top_supplier_share=("weighted_mean_top_supplier_share", "median"),
            source_hhi=("weighted_mean_source_hhi", "median"),
        )
        .sort_values("year")
    )
    fig, ax = plt.subplots(figsize=(11, 5.2))
    ax.plot(ex04_yearly["year"], ex04_yearly["top_supplier_share"], label="Median top supplier share", color="#0f766e", linewidth=2.3)
    ax.plot(ex04_yearly["year"], ex04_yearly["source_hhi"], label="Median source HHI", color="#b45309", linewidth=2.3)
    ax.set_title("Supplier dominance in Cadot-sample imports over time")
    ax.set_xlabel("Year")
    ax.set_ylabel("Median value")
    ax.legend(frameon=False)
    savefig("ex4_supplier_time")

    latest_ex04_year = int(ex04["year"].max())
    ex04_latest = ex04[ex04["year"].eq(latest_ex04_year)].sort_values("weighted_mean_top_supplier_share", ascending=False).head(20).copy()
    fig, ax = plt.subplots(figsize=(10.5, 6.5))
    ax.barh(ex04_latest["country"][::-1], ex04_latest["weighted_mean_top_supplier_share"][::-1], color="#0f766e")
    ax.set_title(f"Highest latest-year dominant-supplier exposure ({latest_ex04_year})")
    ax.set_xlabel("Weighted mean top supplier share")
    savefig("ex4_supplier_distribution")

    ex06_yearly = (
        ex06.groupby(["variant", "flow", "year"], as_index=False)
        .agg(gini=("gini", "median"), theil=("theil", "median"), hhi=("hhi", "median"), trade_share_removed=("trade_share_removed", "median"))
        .sort_values(["variant", "flow", "year"])
    )
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8), sharex=True)
    for ax, metric in zip(axes, ["gini", "theil", "hhi"]):
        for flow in ["Exports", "Imports"]:
            for variant, style in [("baseline", "-"), ("full_exclusion", "--")]:
                rows = ex06_yearly[
                    ex06_yearly["flow"].astype(str).eq(flow) & ex06_yearly["variant"].astype(str).eq(variant)
                ].sort_values("year")
                if rows.empty:
                    continue
                ax.plot(rows["year"], pd.to_numeric(rows[metric], errors="coerce"), linestyle=style, color=flow_colors[flow], linewidth=2.0, label=f"{flow} {variant_labels[variant]}")
        ax.set_title(cadot_metric_label(metric))
        ax.set_xlabel("Year")
        if metric == "gini":
            ax.set_ylabel("Median value")
    handles, labels = axes[0].get_legend_handles_labels()
    seen = {}
    for handle, label in zip(handles, labels):
        seen.setdefault(label, handle)
    axes[0].legend(seen.values(), seen.keys(), frameon=False, fontsize=8)
    fig.suptitle("Baseline versus full HS2 exclusion", fontsize=14)
    savefig("ex6_before_after")

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8), sharey=True)
    for ax, flow in zip(axes, ["Exports", "Imports"]):
        flow_rows = ex06_yearly[
            ex06_yearly["flow"].astype(str).eq(flow) & ~ex06_yearly["variant"].astype(str).eq("baseline")
        ]
        for variant in ["oil_only", "oil_aircraft", "oil_aircraft_precious", "full_exclusion"]:
            rows = flow_rows[flow_rows["variant"].astype(str).eq(variant)].sort_values("year")
            if rows.empty:
                continue
            ax.plot(rows["year"], rows["trade_share_removed"], linewidth=2.0, label=variant_labels[variant])
        ax.set_title(flow)
        ax.set_xlabel("Year")
    axes[0].set_ylabel("Median trade share removed")
    axes[0].legend(frameon=False, fontsize=8)
    fig.suptitle("Trade share removed by exclusion rule", fontsize=14)
    savefig("ex6_removed")

    benchmark_rows = ex10[ex10["benchmark_null"].astype(str).eq("hs2_preserving_within_sector_random_allocation")].copy()
    ex10_yearly = (
        benchmark_rows.groupby(["year", "flow"], as_index=False)
        .agg(
            actual_gini=("actual_gini", "median"),
            sim_gini=("sim_gini_median", "median"),
            actual_theil=("actual_theil", "median"),
            sim_theil=("sim_theil_median", "median"),
            actual_hhi=("actual_hhi", "median"),
            sim_hhi=("sim_hhi_median", "median"),
        )
        .sort_values(["flow", "year"])
    )
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8), sharex=True)
    for ax, metric in zip(axes, ["gini", "theil", "hhi"]):
        for flow in ["Exports", "Imports"]:
            rows = ex10_yearly[ex10_yearly["flow"].astype(str).eq(flow)]
            ax.plot(rows["year"], rows[f"actual_{metric}"], color=flow_colors[flow], linewidth=2.2, label=f"{flow} actual")
            ax.plot(rows["year"], rows[f"sim_{metric}"], color=flow_colors[flow], linewidth=2.0, linestyle="--", label=f"{flow} benchmark")
        ax.set_title(cadot_metric_label(metric))
        ax.set_xlabel("Year")
        if metric == "gini":
            ax.set_ylabel("Median value")
    handles, labels = axes[0].get_legend_handles_labels()
    seen = {}
    for handle, label in zip(handles, labels):
        seen.setdefault(label, handle)
    axes[0].legend(seen.values(), seen.keys(), frameon=False, fontsize=8)
    fig.suptitle("Observed concentration versus HS2-preserving benchmark", fontsize=14)
    savefig("ex10_actual_vs_benchmark")

    percentile_fields = {
        "gini": "actual_gini_percentile",
        "theil": "actual_theil_active_percentile",
        "hhi": "actual_hhi_percentile",
    }
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8), sharex=True, sharey=True)
    for ax, metric in zip(axes, ["gini", "theil", "hhi"]):
        field = percentile_fields[metric]
        rows = (
            benchmark_rows.assign(above_95=pd.to_numeric(benchmark_rows[field], errors="coerce").ge(0.95))
            .groupby(["year", "flow"], as_index=False)["above_95"]
            .mean()
            .sort_values(["flow", "year"])
        )
        for flow in ["Exports", "Imports"]:
            flow_rows = rows[rows["flow"].astype(str).eq(flow)]
            ax.plot(flow_rows["year"], flow_rows["above_95"], color=flow_colors[flow], linewidth=2.2, label=flow)
        ax.axhline(0.95, color="#9ca3af", linestyle=":", linewidth=1.2)
        ax.set_title("Theil active" if metric == "theil" else cadot_metric_label(metric))
        ax.set_xlabel("Year")
        if metric == "gini":
            ax.set_ylabel("Share above 95th percentile")
    axes[0].legend(frameon=False)
    fig.suptitle("Share of observations above the benchmark 95th percentile", fontsize=14)
    savefig("ex10_percentile")

    latest_ex11_year = int(ex11["year"].max())
    ex11_latest = ex11[ex11["year"].eq(latest_ex11_year)].copy()
    fig, ax = plt.subplots(figsize=(10.5, 5.2))
    summary = (
        ex11_latest.groupby(["flow", "metric"], as_index=False)["abs_loo_contribution"]
        .median()
        .pivot(index="flow", columns="metric", values="abs_loo_contribution")
        .reindex(index=["Exports", "Imports"])
        .reindex(columns=["gini", "theil", "hhi"])
    )
    x = np.arange(len(summary.index))
    width = 0.24
    for offset, metric in zip([-width, 0.0, width], ["gini", "theil", "hhi"]):
        ax.bar(x + offset, summary[metric].to_numpy(dtype=float), width=width, color=metric_colors[metric], label=cadot_metric_label(metric))
    ax.set_xticks(x, summary.index.tolist())
    ax.set_ylabel("Median absolute contribution")
    ax.set_title(f"Latest-year published top-product contributions ({latest_ex11_year})")
    ax.legend(frameon=False)
    savefig("ex11_coefficients")

    ex11_export = ex11_latest[ex11_latest["flow"].astype(str).eq("Exports")].copy()
    fig, ax = plt.subplots(figsize=(10.5, 5.2))
    for metric in ["gini", "theil", "hhi"]:
        rows = ex11_export[ex11_export["metric"].astype(str).eq(metric)].copy()
        if rows.empty:
            continue
        rows["bin"] = quantile_bins(rows["abs_loo_contribution"], bins=25)
        grouped = rows.groupby("bin", as_index=False)["trade_value"].median().sort_values("bin")
        ax.plot(grouped["bin"], grouped["trade_value"], linewidth=2.2, color=metric_colors[metric], label=cadot_metric_label(metric))
    ax.set_title(f"Latest-year export trade value by contribution percentile bin ({latest_ex11_year})")
    ax.set_xlabel("Equal-count 4% contribution bin")
    ax.set_ylabel("Median trade value")
    ax.set_yscale("log")
    ax.legend(frameon=False)
    savefig("ex11_export_linkage_4pct")

    fig, ax = plt.subplots(figsize=(10.5, 5.2))
    hs2 = (
        ex11_export.groupby(["metric", "hs2"], as_index=False)
        .agg(abs_loo_contribution=("abs_loo_contribution", "sum"), trade_value=("trade_value", "sum"))
    )
    for metric in ["gini", "theil", "hhi"]:
        rows = hs2[hs2["metric"].astype(str).eq(metric)].copy()
        if rows.empty:
            continue
        rows["bin"] = quantile_bins(rows["abs_loo_contribution"], bins=25)
        grouped = rows.groupby("bin", as_index=False)["trade_value"].median().sort_values("bin")
        ax.plot(grouped["bin"], grouped["trade_value"], linewidth=2.2, color=metric_colors[metric], label=cadot_metric_label(metric))
    ax.set_title(f"Latest-year HS2 trade value by summed contribution percentile bin ({latest_ex11_year})")
    ax.set_xlabel("Equal-count 4% HS2 contribution bin")
    ax.set_ylabel("Median HS2 trade value")
    ax.set_yscale("log")
    ax.legend(frameon=False)
    savefig("ex11_hs2_linkage_4pct")

    fig, ax = plt.subplots(figsize=(10.5, 5.6))
    india = ex11_export[ex11_export["iso3"].astype(str).eq("IND")].copy()
    if india.empty:
        india = ex11_export[ex11_export["country"].astype(str).str.lower().eq("india")].copy()
    if india.empty:
        raise RuntimeError("Cadot Exercise 11 figure generation could not find India rows.")
    for metric in ["gini", "theil", "hhi"]:
        rows = india[india["metric"].astype(str).eq(metric)]
        if rows.empty:
            continue
        ax.scatter(rows["trade_value"], rows["abs_loo_contribution"], s=28, alpha=0.65, color=metric_colors[metric], label=cadot_metric_label(metric))
    ax.set_title(f"India latest-year product trade values and leave-one-out contributions ({latest_ex11_year})")
    ax.set_xlabel("Trade value")
    ax.set_ylabel("Absolute leave-one-out contribution")
    ax.set_xscale("log")
    ax.legend(frameon=False)
    savefig("ex11_india_supplier_scatter")

    missing = [key for key in cadot_figure_keys() if not (figures_dir / f"{key}.png").exists()]
    if missing:
        raise RuntimeError(f"Cadot figure generation did not produce the required figure set: {missing}")


def cadot_figure_gallery(
    depth: int,
    keys: list[str],
    metric: str | None = None,
    data: dict[str, Any] | None = None,
) -> str:
    if not keys:
        return '<p class="section-note">This page uses metric-specific Plotly charts rather than a separate static figure set.</p>'
    rows: list[str] = []
    for start in range(0, len(keys), 2):
        chunk = keys[start : start + 2]
        figures = []
        for key in chunk:
            caption = CADOT_FIGURE_CAPTIONS.get(key, key.replace("_", " ").title())
            href = cadot_asset_href(depth, f"assets/figures/{key}.png")
            figures.append(
                f"""
          <figure>
            <a class="figure-link" href="{href}"><img src="{href}" alt="{escape(caption)}"></a>
            <figcaption>{escape(caption)}</figcaption>
            {cadot_graph_evidence(key, metric, data) if metric and data is not None else ""}
          </figure>
                """
            )
        rows.append('<div class="figure-row">' + "".join(figures) + "</div>")
    return '<div class="figure-stack">' + "".join(rows) + "</div>"


def cadot_exercise_cards(metric: str, shorts: list[str], depth: int) -> str:
    cards = []
    for short in shorts:
        spec = next(item for item in EXERCISE_PAGE_SPECS if item["short"] == short)
        cards.append(
            f"""
      <a class="exercise-card" href="{cadot_asset_href(depth, cadot_metric_exercise_path(metric, short))}">
        <span>Exercise {escape(short)}</span>
        <strong>{escape(spec['title'].split(':', 1)[-1].strip())}</strong>
        <small>{escape(spec['question'])}</small>
      </a>
            """
        )
    return '<div class="link-grid">' + "".join(cards) + "</div>"


def cadot_metric_switch(current_metric: str, short: str | None, depth: int) -> str:
    links = []
    for metric in ["gini", "theil", "hhi"]:
        href = cadot_metric_exercise_path(metric, short) if short else metric + "/"
        cls = ' class="active"' if metric == current_metric else ""
        links.append(f'<a{cls} href="{cadot_asset_href(depth, href)}">{escape(cadot_metric_label(metric))}</a>')
    return '<div class="metric-switch">' + "".join(links) + "</div>"


def cadot_metric_exercise_subnav(current_metric: str, current_short: str, depth: int) -> str:
    links = []
    for spec in EXERCISE_PAGE_SPECS:
        href = cadot_metric_exercise_path(current_metric, spec["short"])
        cls = ' class="active"' if spec["short"] == current_short else ""
        links.append(f'<a{cls} href="{cadot_asset_href(depth, href)}">Ex. {int(spec["short"])}</a>')
    return '<div class="subnav-chips">' + "".join(links) + "</div>"


def cadot_graph_current_result(
    chart_id: str,
    metric: str,
    data: dict[str, Any],
) -> str:
    chart_id = CADOT_FIGURE_QUESTION_ALIASES.get(chart_id, chart_id)
    label = cadot_metric_convention(metric, chart_id)
    if chart_id in {"exposure-gdp-exposure", "exposure-gdp-alignment"}:
        outcome = "world_share_exposure" if chart_id == "exposure-gdp-exposure" else "spearman_product_alignment"
        summary = data["exposure_summary"].copy()
        summary = summary[
            summary["sample_window"].astype(str).eq("all_available")
            & summary["size_variable"].astype(str).eq("log_gdp_current_usd")
            & summary["outcome"].astype(str).eq(outcome)
        ].copy()
        if summary.empty:
            return "No validated yearly GDP comparison is available."
        baseline = summary[summary["variant"].astype(str).eq("baseline")].head(1)
        noncommodity = summary[summary["variant"].astype(str).eq("noncommodity_broad")].head(1)
        yearly = data["exposure_yearly"].copy()
        yearly = yearly[
            yearly["sample_window"].astype(str).eq("all_available")
            & yearly["size_variable"].astype(str).eq("log_gdp_current_usd")
            & yearly["outcome"].astype(str).eq(outcome)
        ].copy()
        latest_year = int(pd.to_numeric(yearly["year"], errors="coerce").max())
        latest = yearly[pd.to_numeric(yearly["year"], errors="coerce").eq(latest_year)]
        base_latest = latest[latest["variant"].astype(str).eq("baseline")]["spearman_size_outcome"]
        nc_latest = latest[latest["variant"].astype(str).eq("noncommodity_broad")]["spearman_size_outcome"]
        base_text = "n/a" if baseline.empty else dec(baseline.iloc[0]["mean_spearman"])
        nc_text = "n/a" if noncommodity.empty else dec(noncommodity.iloc[0]["mean_spearman"])
        latest_base_text = "n/a" if base_latest.empty else dec(base_latest.iloc[0])
        latest_nc_text = "n/a" if nc_latest.empty else dec(nc_latest.iloc[0])
        return (
            f"Across 2000-2024, the baseline mean yearly GDP correlation is {base_text} "
            f"and the non-commodity mean is {nc_text}. In {latest_year}, the two values are "
            f"{latest_base_text} and {latest_nc_text}."
        )
    if chart_id.startswith("exercise1-"):
        panel = data["headline"].copy()
        panel = panel[
            panel["dimension"].astype(str).eq("product")
            & panel["variant"].astype(str).eq("baseline")
        ]
        latest_year = int(pd.to_numeric(panel["year"], errors="coerce").max())
        latest = panel[pd.to_numeric(panel["year"], errors="coerce").eq(latest_year)]
        median_value = pd.to_numeric(latest[metric], errors="coerce").median()
        countries = latest["iso3"].nunique()
        return (
            f"In {latest_year}, the common product panel covers {countries} reporters "
            f"and has median {label} {dec(median_value)} across the two flows."
        )
    if chart_id.startswith("exercise2-"):
        rows = three_metric_metric_rows(data["ex02"], metric).copy()
        values = pd.to_numeric(
            rows.get(
                "mean_annualized_trade_growth_log"
                if chart_id == "exercise2-growth"
                else "mean_annualized_product_active_count_growth_log"
            ),
            errors="coerce",
        ).dropna()
        if values.empty:
            return "The published bucket summary has no comparable numeric rows."
        return (
            f"Across published buckets and horizons, the reported mean ranges from "
            f"{pct(values.min())} to {pct(values.max())}; this remains descriptive."
        )
    if chart_id in {"exercise3-trend", "exercise3-latest"}:
        frame = data["ex03"].copy()
        value_col = "theil_active" if metric == "theil" else metric
        latest_year = int(pd.to_numeric(frame["year"], errors="coerce").max())
        latest = frame[pd.to_numeric(frame["year"], errors="coerce").eq(latest_year)]
        summary = latest.groupby("import_bin", as_index=False)[value_col].median()
        top = summary.sort_values(value_col, ascending=False).head(1)
        if top.empty:
            return "No latest-year import-bin comparison is available."
        return (
            f"In {latest_year}, {str(top.iloc[0]['import_bin']).replace('_', ' ')} "
            f"has the highest median {label} at {dec(top.iloc[0][value_col])}."
        )
    if chart_id in {
        "exercise3-nonenergy-map",
        "exercise3-nonenergy-lines",
        "rank-bucket-overview",
        "rank-bucket-country-chart",
    }:
        annual = data["nonenergy_annual"].copy()
        latest_year = int(pd.to_numeric(annual["year"], errors="coerce").max())
        latest = annual[pd.to_numeric(annual["year"], errors="coerce").eq(latest_year)]
        latest_median = pd.to_numeric(latest[metric], errors="coerce").median()
        if chart_id.startswith("rank-bucket"):
            drivers = data["nonenergy_drivers"]
            drivers = drivers[drivers["metric"].astype(str).eq(metric)]
            mode = drivers["main_driver_group"].mode()
            driver = "no common driver" if mode.empty else str(mode.iloc[0])
            return (
                f"Across {drivers['iso3'].nunique()} reporter start-to-end comparisons, "
                f"the most common largest contribution change is {driver}."
            )
        return (
            f"After removing energy, {latest['iso3'].nunique()} reporters are available "
            f"in {latest_year}; median import {label} is {dec(latest_median)}."
        )
    if chart_id.startswith("exercise4-"):
        frame = data["ex04"].copy()
        latest_year = int(pd.to_numeric(frame["year"], errors="coerce").max())
        latest = frame[pd.to_numeric(frame["year"], errors="coerce").eq(latest_year)]
        top_share = pd.to_numeric(
            latest["weighted_mean_top_supplier_share"], errors="coerce"
        ).median()
        source_hhi = pd.to_numeric(
            latest["weighted_mean_source_hhi"], errors="coerce"
        ).median()
        return (
            f"In {latest_year}, median weighted top-supplier share is {pct(top_share)} "
            f"and median weighted source HHI is {dec(source_hhi)}."
        )
    if chart_id.startswith("exercise6-"):
        frame = data["ex06"].copy()
        frame = frame[frame["dimension"].astype(str).eq("product")]
        latest_year = int(pd.to_numeric(frame["year"], errors="coerce").max())
        latest = frame[pd.to_numeric(frame["year"], errors="coerce").eq(latest_year)]
        baseline = pd.to_numeric(
            latest.loc[latest["variant"].astype(str).eq("baseline"), metric],
            errors="coerce",
        ).median()
        excluded = pd.to_numeric(
            latest.loc[latest["variant"].astype(str).eq("full_exclusion"), metric],
            errors="coerce",
        ).median()
        return (
            f"In {latest_year}, median product {label} is {dec(baseline)} at baseline "
            f"and {dec(excluded)} under the full exclusion."
        )
    if chart_id.startswith("exercise10-"):
        frame = data["ex10"].copy()
        gap_col = f"actual_minus_sim_median_{metric}"
        hs2 = frame[
            frame["benchmark_null"]
            .astype(str)
            .eq("hs2_preserving_within_sector_random_allocation")
        ]
        gap = pd.to_numeric(hs2[gap_col], errors="coerce").median()
        positive = pd.to_numeric(hs2[gap_col], errors="coerce").gt(0).mean()
        return (
            f"Under the HS2-preserving benchmark, median actual-minus-simulation "
            f"{label} is {dec(gap)} and {pct(positive)} of rows have positive gaps."
        )
    if chart_id.startswith("exercise11-"):
        frame = three_metric_metric_rows(data["ex11"], metric).copy()
        summary = (
            frame.groupby(["cmd_code", "product_label"], as_index=False)[
                "abs_loo_contribution"
            ]
            .max()
            .sort_values("abs_loo_contribution", ascending=False)
        )
        if summary.empty:
            return "No leave-one-out contribution rows are available."
        top = summary.iloc[0]
        return (
            f"The largest published absolute {label} contribution is "
            f"{dec(top['abs_loo_contribution'])} for {top['product_label']}."
        )
    if chart_id.startswith("exercise12-"):
        frame = three_metric_metric_rows(data["ex12"], metric).copy()
        column = (
            "mean_annualized_trade_growth_log"
            if chart_id == "exercise12-growth"
            else "mean_annualized_product_active_count_growth_log"
        )
        values = pd.to_numeric(frame[column], errors="coerce").dropna()
        return (
            f"Across the published buckets and horizons, {column.replace('_', ' ')} "
            f"ranges from {pct(values.min())} to {pct(values.max())}."
        )
    return "The chart is computed from the validated Cadot 156 website payload."


def cadot_graph_evidence(
    chart_id: str,
    metric: str,
    data: dict[str, Any],
) -> str:
    spec = CADOT_GRAPH_QUESTIONS[chart_id]
    label = cadot_metric_convention(metric, chart_id)
    return f"""
      <article class="evidence-note cadot-evidence-note">
        <dl>
          <dt>Question this answers</dt><dd>{escape(spec['question'].format(metric=label))}</dd>
          <dt>Supports the reading if</dt><dd>{escape(spec['supports'].format(metric=label))}</dd>
          <dt>Weakens the reading if</dt><dd>{escape(spec['weakens'].format(metric=label))}</dd>
          <dt>Current result</dt><dd>{escape(cadot_graph_current_result(chart_id, metric, data))}</dd>
        </dl>
      </article>
    """


def cadot_exercise_hypothesis(
    metric: str,
    spec: dict[str, Any],
    data: dict[str, Any],
) -> str:
    first_chart = {
        "01": "exercise1-map",
        "02": "exercise2-growth",
        "03": "exercise3-trend",
        "04": "exercise4-trend",
        "06": "exercise6-trend",
        "10": "exercise10-trend",
        "11": "exercise11-trend",
        "12": "exercise12-growth",
    }[spec["short"]]
    return f"""
      <article class="hypothesis-card cadot-hypothesis-card">
        <div class="hypothesis-kicker">{escape(cadot_metric_label(metric))} Exercise {escape(spec['short'])}</div>
        <h3>{escape(spec['title'].split(':', 1)[-1].strip())}</h3>
        <dl>
          <dt>Metric convention</dt><dd>{escape(cadot_metric_convention(metric, first_chart))}</dd>
          <dt>Question</dt><dd>{escape(spec['question'])}</dd>
          <dt>Supports yes if</dt><dd>{escape(spec['supports'])}</dd>
          <dt>Weakens yes if</dt><dd>{escape(spec['weakens'])}</dd>
          <dt>Current result</dt><dd>{escape(cadot_graph_current_result(first_chart, metric, data))}</dd>
        </dl>
      </article>
    """


def cadot_chart_panel(
    title: str,
    description: str,
    chart_id: str,
    controls_html: str = "",
    tall: bool = False,
    evidence_html: str = "",
) -> str:
    classes = "chart js-plotly-plot tall" if tall else "chart js-plotly-plot"
    return f"""
      <article class="chart-panel">
        <div class="tool-header">
          <div>
            <h3>{escape(title)}</h3>
            <p>{escape(description)}</p>
          </div>
          <div class="controls">{controls_html}</div>
        </div>
        {evidence_html}
        <div id="{escape(chart_id)}" class="{classes}"></div>
      </article>
    """


def cadot_metric_focus_table(metric: str, spec: dict[str, Any], data: dict[str, Any]) -> str:
    short = spec["short"]
    if short == "01":
        frame = data["rankings"][data["rankings"]["metric"].astype(str).str.lower().eq(metric)].copy()
        frame = frame.sort_values(["flow", "rank"]).head(24)
        return cadot_table(
            clean_records(frame, list(frame.columns)),
            [
                ("flow", "Flow", "text"),
                ("rank", "Rank", "int"),
                ("country", "Country", "text"),
                ("year", "Year", "year"),
                ("metric_value", cadot_metric_label(metric), "dec"),
                ("active_count", "Active products", "int"),
                ("total_trade_value", "Trade value", "money"),
            ],
        )
    if short == "02":
        frame = three_metric_metric_rows(data["ex02"], metric).copy()
        bucket_col = "concentration_bucket" if "concentration_bucket" in frame.columns else "base_concentration_bucket"
        frame = frame.sort_values(["flow", "horizon", bucket_col]).head(40)
        return cadot_table(
            clean_records(frame, list(frame.columns)),
            [
                ("flow", "Flow", "text"),
                ("horizon", "Horizon", "int"),
                (bucket_col, "Bucket", "text"),
                ("observations", "Obs.", "int"),
                ("countries", "Countries", "int"),
                ("mean_annualized_trade_growth_log", "Mean trade growth", "pct"),
            ],
        )
    if short == "03":
        frame = data["ex03"].copy()
        value_col = "theil_active" if metric == "theil" else metric
        summary = frame.groupby("import_bin", as_index=False).agg(
            rows=("country", "size"),
            countries=("iso3", "nunique"),
            median_import_share=("import_value_share", "median"),
            metric_value=(value_col, "median"),
        )
        summary = summary.sort_values("median_import_share", ascending=False)
        return cadot_table(
            clean_records(summary, list(summary.columns)),
            [
                ("import_bin", "Import bin", "text"),
                ("rows", "Rows", "int"),
                ("countries", "Countries", "int"),
                ("median_import_share", "Median import share", "pct"),
                ("metric_value", f"Median {cadot_metric_label(metric)}", "dec"),
            ],
        )
    if short == "04":
        frame = data["ex04"].copy()
        latest_year = int(pd.to_numeric(frame["year"], errors="coerce").max())
        latest = frame[pd.to_numeric(frame["year"], errors="coerce").eq(latest_year)].sort_values(
            "weighted_mean_top_supplier_share", ascending=False
        ).head(24)
        return cadot_table(
            clean_records(latest, list(latest.columns)),
            [
                ("country", "Country", "text"),
                ("year", "Year", "year"),
                ("weighted_mean_top_supplier_share", "Weighted top supplier share", "pct"),
                ("weighted_mean_source_hhi", "Weighted source HHI", "dec"),
                ("share_products_top_supplier_ge_75", "Products >= 75%", "pct"),
                ("import_value_share_products_top_supplier_ge_75", "Import value share >= 75%", "pct"),
            ],
        )
    if short == "06":
        frame = data["ex06"].copy()
        if "dimension" in frame.columns:
            frame = frame[frame["dimension"].astype(str).eq("product")].copy()
        value_col = "theil" if metric == "theil" else metric
        summary = frame.groupby(["variant", "flow"], as_index=False).agg(
            rows=("country", "size"),
            median_trade_share_removed=("trade_share_removed", "median"),
            metric_value=(value_col, "median"),
        )
        return cadot_table(
            clean_records(summary, list(summary.columns)),
            [
                ("variant", "Variant", "text"),
                ("flow", "Flow", "text"),
                ("rows", "Rows", "int"),
                ("median_trade_share_removed", "Median removed share", "pct"),
                ("metric_value", f"Median {cadot_metric_label(metric)}", "dec"),
            ],
        )
    if short == "10":
        frame = data["ex10"].copy()
        actual_col = {"gini": "actual_gini", "theil": "actual_theil", "hhi": "actual_hhi"}[metric]
        sim_col = {"gini": "sim_gini_median", "theil": "sim_theil_median", "hhi": "sim_hhi_median"}[metric]
        gap_col = {"gini": "actual_minus_sim_median_gini", "theil": "actual_minus_sim_median_theil", "hhi": "actual_minus_sim_median_hhi"}[metric]
        summary = frame.groupby(["flow", "benchmark_null"], as_index=False).agg(
            rows=("country", "size"),
            simulations=("simulations", "median"),
            actual_value=(actual_col, "median"),
            simulated_value=(sim_col, "median"),
            median_gap=(gap_col, "median"),
        )
        return cadot_table(
            clean_records(summary, list(summary.columns)),
            [
                ("flow", "Flow", "text"),
                ("benchmark_null", "Benchmark", "text"),
                ("rows", "Rows", "int"),
                ("simulations", "Sims", "int"),
                ("actual_value", f"Median actual {cadot_metric_label(metric)}", "dec"),
                ("simulated_value", "Median simulated", "dec"),
                ("median_gap", "Median gap", "dec"),
            ],
        )
    if short == "11":
        frame = three_metric_metric_rows(data["ex11"], metric).copy()
        summary = frame.groupby(["flow", "cmd_code", "product_label"], as_index=False).agg(
            countries=("iso3", "nunique"),
            median_abs_contribution=("abs_loo_contribution", "median"),
            max_abs_contribution=("abs_loo_contribution", "max"),
        )
        summary = summary.sort_values("max_abs_contribution", ascending=False).head(30)
        return cadot_table(
            clean_records(summary, list(summary.columns)),
            [
                ("flow", "Flow", "text"),
                ("product_label", "HS1992 product family", "text"),
                ("countries", "Countries", "int"),
                ("median_abs_contribution", "Median abs. contribution", "dec"),
                ("max_abs_contribution", "Max abs. contribution", "dec"),
            ],
        )
    if short == "12":
        frame = three_metric_metric_rows(data["ex12"], metric).copy().sort_values(["flow", "horizon", "base_concentration_bucket"])
        return cadot_table(
            clean_records(frame.head(40), list(frame.columns)),
            [
                ("flow", "Flow", "text"),
                ("horizon", "Horizon", "int"),
                ("base_concentration_bucket", "Bucket", "text"),
                ("observations", "Obs.", "int"),
                ("countries", "Countries", "int"),
                ("mean_annualized_trade_growth_log", "Mean trade growth", "pct"),
                ("mean_annualized_product_active_count_growth_log", "Product growth", "pct"),
                ("mean_annualized_partner_active_count_growth_log", "Partner growth", "pct"),
                ("mean_annualized_cell_active_count_growth_log", "Cell growth", "pct"),
            ],
        )
    return cadot_exercise_evidence_table(data[spec["data_key"]], spec)

def cadot_browser_data(data: dict[str, Any]) -> dict[str, Any]:
    product_panel = data["headline"].copy()
    if "dimension" in product_panel.columns:
        product_panel = product_panel[product_panel["dimension"].astype(str).eq("product")].copy()
    if "variant" in product_panel.columns:
        product_panel = product_panel[product_panel["variant"].astype(str).eq("baseline")].copy()
    product_panel = product_panel[
        [
            "country",
            "iso3",
            "year",
            "flow",
            "gini",
            "theil",
            "hhi",
            "active_count",
            "total_trade_value",
        ]
    ].copy()
    product_panel["year"] = pd.to_numeric(product_panel["year"], errors="coerce")

    countries = (
        product_panel[["country", "iso3"]]
        .dropna()
        .drop_duplicates()
        .sort_values(["country", "iso3"])
        .reset_index(drop=True)
    )

    product_yearly = data["yearly"].copy()
    if "dimension" in product_yearly.columns:
        product_yearly = product_yearly[product_yearly["dimension"].astype(str).eq("product")].copy()
    if "variant" in product_yearly.columns:
        product_yearly = product_yearly[product_yearly["variant"].astype(str).eq("baseline")].copy()
    product_yearly = product_yearly[
        [
            "year",
            "flow",
            "countries",
            "median_gini",
            "median_theil",
            "median_hhi",
            "median_active_count",
            "median_total_trade_value",
        ]
    ].copy()

    rankings = data["rankings"][
        ["metric", "rank", "country", "iso3", "year", "flow", "metric_value", "active_count", "total_trade_value"]
    ].copy()

    ex03 = data["ex03"].copy()
    ex03_yearly = (
        ex03.groupby(["year", "import_bin"], as_index=False)
        .agg(
            countries=("iso3", "nunique"),
            median_import_share=("import_value_share", "median"),
            gini=("gini", "median"),
            theil=("theil_active", "median"),
            hhi=("hhi", "median"),
        )
        .sort_values(["year", "import_bin"])
    )
    ex03_latest_year = int(pd.to_numeric(ex03["year"], errors="coerce").max())
    ex03_latest = (
        ex03[pd.to_numeric(ex03["year"], errors="coerce").eq(ex03_latest_year)]
        .groupby("import_bin", as_index=False)
        .agg(
            countries=("iso3", "nunique"),
            median_import_share=("import_value_share", "median"),
            gini=("gini", "median"),
            theil=("theil_active", "median"),
            hhi=("hhi", "median"),
        )
        .sort_values("median_import_share", ascending=False)
    )

    ex04 = data["ex04"].copy()
    ex04_yearly = (
        ex04.groupby("year", as_index=False)
        .agg(
            countries=("iso3", "nunique"),
            top_supplier_share=("weighted_mean_top_supplier_share", "median"),
            source_hhi=("weighted_mean_source_hhi", "median"),
            products_ge_75=("share_products_top_supplier_ge_75", "median"),
        )
        .sort_values("year")
    )
    ex04_latest_year = int(pd.to_numeric(ex04["year"], errors="coerce").max())
    ex04_latest = ex04[pd.to_numeric(ex04["year"], errors="coerce").eq(ex04_latest_year)][
        [
            "country",
            "iso3",
            "year",
            "weighted_mean_top_supplier_share",
            "weighted_mean_source_hhi",
            "share_products_top_supplier_ge_75",
            "import_value_share_products_top_supplier_ge_75",
        ]
    ].sort_values("weighted_mean_top_supplier_share", ascending=False)

    ex06 = data["ex06"].copy()
    if "dimension" in ex06.columns:
        ex06 = ex06[ex06["dimension"].astype(str).eq("product")].copy()
    ex06_yearly = (
        ex06.groupby(["variant", "flow", "year"], as_index=False)
        .agg(
            trade_share_removed=("trade_share_removed", "median"),
            gini=("gini", "median"),
            theil=("theil", "median"),
            hhi=("hhi", "median"),
        )
        .sort_values(["variant", "flow", "year"])
    )
    ex06_baseline = ex06[ex06["excluded_hs2"].isna()][["country", "iso3", "year", "flow", "gini", "theil", "hhi"]].rename(
        columns={"gini": "baseline_gini", "theil": "baseline_theil", "hhi": "baseline_hhi"}
    )
    ex06_excluded = ex06[ex06["excluded_hs2"].notna()].copy()
    ex06_excluded = ex06_excluded.merge(ex06_baseline, on=["country", "iso3", "year", "flow"], how="left")
    for metric in ["gini", "theil", "hhi"]:
        ex06_excluded[f"abs_delta_{metric}"] = (
            pd.to_numeric(ex06_excluded[metric], errors="coerce")
            - pd.to_numeric(ex06_excluded[f"baseline_{metric}"], errors="coerce")
        ).abs()
    ex06_sensitivity = (
        ex06_excluded.groupby(["flow", "excluded_hs2"], as_index=False)
        .agg(
            rows=("country", "size"),
            trade_share_removed=("trade_share_removed", "median"),
            abs_delta_gini=("abs_delta_gini", "median"),
            abs_delta_theil=("abs_delta_theil", "median"),
            abs_delta_hhi=("abs_delta_hhi", "median"),
        )
        .sort_values(["flow", "abs_delta_theil"], ascending=[True, False])
    )

    ex10 = data["ex10"].copy()
    ex10_yearly = (
        ex10.groupby(["flow", "benchmark_null", "year"], as_index=False)
        .agg(
            actual_gini=("actual_gini", "median"),
            sim_gini=("sim_gini_median", "median"),
            gap_gini=("actual_minus_sim_median_gini", "median"),
            actual_theil=("actual_theil", "median"),
            sim_theil=("sim_theil_median", "median"),
            gap_theil=("actual_minus_sim_median_theil", "median"),
            actual_hhi=("actual_hhi", "median"),
            sim_hhi=("sim_hhi_median", "median"),
            gap_hhi=("actual_minus_sim_median_hhi", "median"),
        )
        .sort_values(["flow", "benchmark_null", "year"])
    )
    ex10_latest_year = int(pd.to_numeric(ex10["year"], errors="coerce").max())
    ex10_latest = ex10[pd.to_numeric(ex10["year"], errors="coerce").eq(ex10_latest_year)][
        [
            "country",
            "iso3",
            "year",
            "flow",
            "benchmark_null",
            "actual_minus_sim_median_gini",
            "actual_minus_sim_median_theil",
            "actual_minus_sim_median_hhi",
        ]
    ].copy()

    ex11 = data["ex11"].copy()
    ex11_yearly = (
        ex11.groupby(["metric", "flow", "year"], as_index=False)
        .agg(
            countries=("iso3", "nunique"),
            median_abs_contribution=("abs_loo_contribution", "median"),
            max_abs_contribution=("abs_loo_contribution", "max"),
        )
        .sort_values(["metric", "flow", "year"])
    )
    ex11_latest_year = int(pd.to_numeric(ex11["year"], errors="coerce").max())
    ex11_top = (
        ex11[pd.to_numeric(ex11["year"], errors="coerce").eq(ex11_latest_year)]
        .groupby(["metric", "flow", "cmd_code", "product_label"], as_index=False)
        .agg(
            countries=("iso3", "nunique"),
            median_abs_contribution=("abs_loo_contribution", "median"),
            max_abs_contribution=("abs_loo_contribution", "max"),
        )
        .sort_values(["metric", "flow", "max_abs_contribution"], ascending=[True, True, False])
        .groupby(["metric", "flow"], as_index=False, group_keys=False)
        .head(20)
    )

    ex12 = data["ex12"][
        [
            "metric",
            "flow",
            "horizon",
            "base_concentration_bucket",
            "observations",
            "countries",
            "mean_annualized_trade_growth_log",
            "median_annualized_trade_growth_log",
            "mean_annualized_product_active_count_growth_log",
            "mean_annualized_partner_active_count_growth_log",
            "mean_annualized_cell_active_count_growth_log",
        ]
    ].copy()

    appendix = data["all_metrics"].copy()
    appendix = appendix[appendix["dimension"].astype(str).eq("product_partner_cell")].copy()
    appendix_yearly = (
        appendix.groupby(["flow", "year"], as_index=False)
        .agg(
            countries=("country", "nunique"),
            gini=("gini", "median"),
            theil=("theil", "median"),
            hhi=("hhi", "median"),
            active_count=("active_count", "median"),
        )
        .sort_values(["flow", "year"])
    )

    nonenergy_annual = data["nonenergy_annual"].copy()
    nonenergy_annual["year"] = pd.to_numeric(nonenergy_annual["year"], errors="coerce")
    nonenergy_annual = nonenergy_annual[
        [
            "country",
            "iso3",
            "reporter_code",
            "year",
            "flow",
            "active_nonenergy_products",
            "total_nonenergy_imports",
            "gini",
            "theil",
            "hhi",
        ]
    ].copy()
    nonenergy_snapshots = data["nonenergy_snapshots"].copy()
    nonenergy_snapshots["year"] = pd.to_numeric(
        nonenergy_snapshots["year"], errors="coerce"
    )
    snapshot_columns = [
        "country",
        "iso3",
        "reporter_code",
        "snapshot",
        "year",
        "flow",
        "active_nonenergy_products",
        "total_nonenergy_imports",
        "gini",
        "theil",
        "hhi",
    ]
    for bucket in ["top5", "rank6_50", "rank51_200", "rank201_plus"]:
        snapshot_columns.append(f"{bucket}_share")
        snapshot_columns.extend(
            f"{bucket}_{metric}_contribution" for metric in ["gini", "theil", "hhi"]
        )
    nonenergy_snapshots = nonenergy_snapshots[snapshot_columns].copy()
    nonenergy_top_products = data["nonenergy_top_products"].copy()
    nonenergy_top_products["cmd_code"] = (
        nonenergy_top_products["cmd_code"].astype("string").str.zfill(6)
    )
    nonenergy_top_products = nonenergy_top_products[
        [
            "country",
            "iso3",
            "reporter_code",
            "snapshot",
            "year",
            "cmd_code",
            "product_label",
            "rank",
            "trade_value",
            "share",
            "total_nonenergy_imports",
        ]
    ].copy()
    nonenergy_drivers = data["nonenergy_drivers"].copy()
    nonenergy_drivers = nonenergy_drivers[
        [
            "country",
            "iso3",
            "reporter_code",
            "metric",
            "start_year",
            "end_year",
            "delta_metric",
            "metric_change_direction",
            "main_driver_bucket",
            "main_driver_bucket_label",
            "main_driver_group",
        ]
    ].copy()

    exposure_yearly = data["exposure_yearly"].copy()
    exposure_yearly = exposure_yearly[
        exposure_yearly["size_variable"].astype(str).eq("log_gdp_current_usd")
        & exposure_yearly["outcome"].astype(str).isin(
            ["world_share_exposure", "spearman_product_alignment"]
        )
    ][
        [
            "sample_window",
            "variant",
            "variant_label",
            "year",
            "outcome",
            "outcome_label",
            "spearman_size_outcome",
            "n_countries",
        ]
    ].copy()
    exposure_summary = data["exposure_summary"].copy()
    exposure_summary = exposure_summary[
        exposure_summary["size_variable"].astype(str).eq("log_gdp_current_usd")
        & exposure_summary["outcome"].astype(str).isin(
            ["world_share_exposure", "spearman_product_alignment"]
        )
    ].copy()
    exposure_models = data["exposure_models"].copy()
    exposure_models = exposure_models[
        exposure_models["model_label"].astype(str).eq("main_gdp_year_fe")
        & exposure_models["term"].astype(str).eq("log_gdp_current_usd")
        & exposure_models["outcome"].astype(str).isin(
            ["world_share_exposure", "spearman_product_alignment"]
        )
    ].copy()
    exposure_coverage = data["exposure_coverage"].copy()
    exposure_fixed_summary = data["exposure_fixed_summary"].copy()
    exposure_fixed_summary = exposure_fixed_summary[
        exposure_fixed_summary["size_variable"].astype(str).eq("log_gdp_current_usd")
        & exposure_fixed_summary["outcome"].astype(str).isin(
            ["world_share_exposure", "spearman_product_alignment"]
        )
    ].copy()
    exposure_removed = data["exposure_removed"].copy()
    exposure_removed = exposure_removed[
        [
            "country",
            "iso3",
            "reporter_code",
            "year",
            "broad_primary_share_removed",
            "delta_world_share_exposure",
            "delta_spearman_product_alignment",
        ]
    ].copy()

    return {
        "manifest": clean_structure(data["manifest"]),
        "nonenergyManifest": clean_structure(data["nonenergy_manifest"]),
        "exposureManifest": clean_structure(data["exposure_manifest"]),
        "countries": clean_records(countries, list(countries.columns)),
        "productPanel": clean_records(product_panel, list(product_panel.columns)),
        "productYearly": clean_records(product_yearly, list(product_yearly.columns)),
        "rankings": clean_records(rankings, list(rankings.columns)),
        "ex02": clean_records(data["ex02"], list(data["ex02"].columns)),
        "ex03Yearly": clean_records(ex03_yearly, list(ex03_yearly.columns)),
        "ex03Latest": clean_records(ex03_latest, list(ex03_latest.columns)),
        "ex04Yearly": clean_records(ex04_yearly, list(ex04_yearly.columns)),
        "ex04Latest": clean_records(ex04_latest, list(ex04_latest.columns)),
        "ex06Yearly": clean_records(ex06_yearly, list(ex06_yearly.columns)),
        "ex06Sensitivity": clean_records(ex06_sensitivity, list(ex06_sensitivity.columns)),
        "ex10Yearly": clean_records(ex10_yearly, list(ex10_yearly.columns)),
        "ex10Latest": clean_records(ex10_latest, list(ex10_latest.columns)),
        "ex11Yearly": clean_records(ex11_yearly, list(ex11_yearly.columns)),
        "ex11Top": clean_records(ex11_top, list(ex11_top.columns)),
        "ex12": clean_records(ex12, list(ex12.columns)),
        "appendixYearly": clean_records(appendix_yearly, list(appendix_yearly.columns)),
        "nonenergyAnnual": clean_records(
            nonenergy_annual, list(nonenergy_annual.columns)
        ),
        "nonenergySnapshots": clean_records(
            nonenergy_snapshots, list(nonenergy_snapshots.columns)
        ),
        "nonenergyTopProducts": clean_records(
            nonenergy_top_products, list(nonenergy_top_products.columns)
        ),
        "nonenergyDrivers": clean_records(
            nonenergy_drivers, list(nonenergy_drivers.columns)
        ),
        "cadotExposureYearly": clean_records(
            exposure_yearly, list(exposure_yearly.columns)
        ),
        "cadotExposureSummary": clean_records(
            exposure_summary, list(exposure_summary.columns)
        ),
        "cadotExposureModels": clean_records(
            exposure_models, list(exposure_models.columns)
        ),
        "cadotExposureCoverage": clean_records(
            exposure_coverage, list(exposure_coverage.columns)
        ),
        "cadotExposureFixedSummary": clean_records(
            exposure_fixed_summary, list(exposure_fixed_summary.columns)
        ),
        "cadotExposureRemoved": clean_records(
            exposure_removed, list(exposure_removed.columns)
        ),
    }


def cadot_write_json_assets(output: Path, data: dict[str, Any]) -> None:
    browser_data = cadot_browser_data(data)
    json_text = json.dumps(browser_data, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    (output / "assets/site-data.json").write_text(json_text + "\n", encoding="utf-8")
    (output / "assets/site-data.js").write_text(
        "window.TRADE_GINI_DATA=" + json_text.replace("</", "<\\/") + ";\n",
        encoding="utf-8",
    )
    for needle in ["NaN", "undefined", "__PLACEHOLDER__"]:
        if needle in json_text:
            raise RuntimeError(f"Cadot site data contains forbidden token: {needle}")


def cadot_site_js() -> str:
    return """
(function () {
  const DATA = window.TRADE_GINI_DATA || {};
  const METRICS = {
    gini: { label: 'Gini', color: '#0f766e' },
    theil: { label: 'Theil', color: '#2563eb' },
    hhi: { label: 'HHI', color: '#b45309' }
  };
  const COLORS = ['#0f766e', '#2563eb', '#b45309', '#dc2626', '#7c3aed', '#0891b2', '#4d7c0f', '#be123c'];
  const CONFIG = { responsive: true, displayModeBar: true, displaylogo: false };

  function byId(id) { return document.getElementById(id); }
  function currentMetric() { return document.body.dataset.metric || 'gini'; }
  function metricLabel(metric) { return (METRICS[metric] || {}).label || metric; }
  function medianField(metric) { return 'median_' + metric; }
  function fmt(value, digits) {
    const n = Number(value);
    if (!Number.isFinite(n)) return 'n/a';
    return n.toFixed(digits ?? 3);
  }
  function pct(value, digits) {
    const n = Number(value);
    if (!Number.isFinite(n)) return 'n/a';
    return (100 * n).toFixed(digits ?? 1) + '%';
  }
  function layout(title, ytitle, xtitle) {
    return {
      title: { text: title, x: 0, xanchor: 'left', font: { size: 18 } },
      margin: { l: 56, r: 24, t: 54, b: 52 },
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: '#ffffff',
      hovermode: 'closest',
      xaxis: { title: xtitle || '', gridcolor: '#e5e7eb', zeroline: false },
      yaxis: { title: ytitle || '', gridcolor: '#e5e7eb', zeroline: false },
      legend: { orientation: 'h', y: -0.2 }
    };
  }
  function relayout() {
    document.querySelectorAll('.js-plotly-plot').forEach((node) => Plotly.Plots.resize(node));
  }
  function groupRows(rows, key) {
    const map = new Map();
    rows.forEach((row) => {
      const id = row[key];
      if (!map.has(id)) map.set(id, []);
      map.get(id).push(row);
    });
    return map;
  }
  function escapeHtml(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
  function usdShort(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return 'n/a';
    if (Math.abs(n) >= 1e12) return '$' + (n / 1e12).toFixed(1) + 'T';
    if (Math.abs(n) >= 1e9) return '$' + (n / 1e9).toFixed(1) + 'B';
    if (Math.abs(n) >= 1e6) return '$' + (n / 1e6).toFixed(1) + 'M';
    return '$' + n.toLocaleString(undefined, { maximumFractionDigits: 0 });
  }
  function metricExtent(rows, metric) {
    const values = rows.map((row) => Number(row[metric])).filter((value) => Number.isFinite(value));
    if (!values.length) return [0, 1];
    const min = Math.min.apply(null, values);
    const max = Math.max.apply(null, values);
    return min === max ? [min - 0.01, max + 0.01] : [min, max];
  }

  function renderHubCharts() {
    const trend = byId('hub-trend-chart');
    const latest = byId('hub-latest-chart');
    if (!trend || !latest) return;
    const yearly = DATA.productYearly || [];
    const traces = [];
    ['Exports', 'Imports'].forEach((flow, flowIndex) => {
      Object.keys(METRICS).forEach((metric, index) => {
        const rows = yearly.filter((row) => row.flow === flow).sort((a, b) => Number(a.year) - Number(b.year));
        traces.push({
          type: 'scatter',
          mode: 'lines',
          name: metricLabel(metric) + ' ' + flow,
          x: rows.map((row) => row.year),
          y: rows.map((row) => row[medianField(metric)]),
          line: { color: COLORS[(flowIndex * 3 + index) % COLORS.length], width: 2 }
        });
      });
    });
    Plotly.react(trend, traces, layout('Median product concentration over time', 'Median value', 'Year'), CONFIG);

    const maxYear = Math.max.apply(null, yearly.map((row) => Number(row.year)).filter((value) => Number.isFinite(value)));
    const latestRows = yearly.filter((row) => Number(row.year) === maxYear);
    const barTraces = ['Exports', 'Imports'].map((flow, idx) => ({
      type: 'bar',
      name: flow,
      x: Object.keys(METRICS).map((metric) => metricLabel(metric)),
      y: Object.keys(METRICS).map((metric) => {
        const row = latestRows.find((item) => item.flow === flow);
        return row ? row[medianField(metric)] : null;
      }),
      marker: { color: idx === 0 ? '#0f766e' : '#2563eb' }
    }));
    const latestLayout = layout('Latest median comparison', 'Median value', '');
    latestLayout.barmode = 'group';
    Plotly.react(latest, barTraces, latestLayout, { ...CONFIG, displayModeBar: false });
  }

  function renderMetricOverview() {
    const metric = currentMetric();
    const trend = byId('metric-overview-trend');
    const ranking = byId('metric-overview-ranking');
    const growth = byId('metric-overview-growth');
    const bins = byId('metric-overview-bins');
    const suppliers = byId('metric-overview-suppliers');
    if (trend) {
      const rows = (DATA.productYearly || []).sort((a, b) => Number(a.year) - Number(b.year));
      const traces = ['Exports', 'Imports'].map((flow, idx) => {
        const flowRows = rows.filter((row) => row.flow === flow);
        return {
          type: 'scatter',
          mode: 'lines+markers',
          name: flow,
          x: flowRows.map((row) => row.year),
          y: flowRows.map((row) => row[medianField(metric)]),
          line: { color: idx === 0 ? '#0f766e' : '#2563eb', width: 2 }
        };
      });
      Plotly.react(trend, traces, layout(metricLabel(metric) + ' over time', metricLabel(metric), 'Year'), CONFIG);
    }
    if (ranking) {
      const flow = byId('metric-overview-flow')?.value || 'Exports';
      const rows = (DATA.rankings || []).filter((row) => row.metric === metric && row.flow === flow).slice(0, 15).reverse();
      Plotly.react(ranking, [{
        type: 'bar',
        orientation: 'h',
        x: rows.map((row) => row.metric_value),
        y: rows.map((row) => row.country),
        marker: { color: METRICS[metric].color },
        hovertemplate: '<b>%{y}</b><br>' + metricLabel(metric) + ': %{x:.3f}<extra></extra>'
      }], layout('Latest ' + flow + ' rankings', metricLabel(metric), ''), { ...CONFIG, displayModeBar: false });
    }
    if (growth) {
      const flow = byId('metric-overview-growth-flow')?.value || 'Exports';
      const horizon = Number(byId('metric-overview-growth-horizon')?.value || 5);
      const rows = (DATA.ex12 || []).filter((row) => row.metric === metric && row.flow === flow && Number(row.horizon) === horizon);
      Plotly.react(growth, [{
        type: 'bar',
        x: rows.map((row) => row.base_concentration_bucket),
        y: rows.map((row) => row.mean_annualized_trade_growth_log),
        marker: { color: METRICS[metric].color },
        hovertemplate: '%{x}<br>Trade growth: %{y:.3f}<extra></extra>'
      }], layout('Growth decomposition buckets', 'Mean annualized trade growth', ''), { ...CONFIG, displayModeBar: false });
    }
    if (bins) {
      const rows = DATA.ex03Yearly || [];
      const grouped = groupRows(rows, 'import_bin');
      const traces = Array.from(grouped.entries()).map(([bin, items], idx) => {
        items.sort((a, b) => Number(a.year) - Number(b.year));
        return {
          type: 'scatter',
          mode: 'lines',
          name: bin.replace(/_/g, ' '),
          x: items.map((row) => row.year),
          y: items.map((row) => row[metric]),
          line: { color: COLORS[idx % COLORS.length], width: 2 }
        };
      });
      Plotly.react(bins, traces, layout('Import-bin concentration through time', metricLabel(metric), 'Year'), CONFIG);
    }
    if (suppliers) {
      const rows = (DATA.ex04Yearly || []).sort((a, b) => Number(a.year) - Number(b.year));
      Plotly.react(suppliers, [
        {
          type: 'scatter',
          mode: 'lines',
          name: 'Weighted top supplier share',
          x: rows.map((row) => row.year),
          y: rows.map((row) => row.top_supplier_share),
          line: { color: '#0f766e', width: 2 }
        },
        {
          type: 'scatter',
          mode: 'lines',
          name: 'Weighted source HHI',
          x: rows.map((row) => row.year),
          y: rows.map((row) => row.source_hhi),
          line: { color: '#b45309', width: 2 }
        }
      ], layout('Supplier concentration through time', 'Median value', 'Year'), CONFIG);
    }
  }

  function renderExercise1() {
    const metric = currentMetric();
    const mapNode = byId('exercise1-map');
    const linesNode = byId('exercise1-lines');
    const rankNode = byId('exercise1-ranking');
    const flow = byId('exercise1-flow')?.value || 'Exports';
    const year = Number(byId('exercise1-year')?.value || 2024);
    const rows = (DATA.productPanel || []).filter((row) => row.flow === flow && Number(row.year) === year);
    const extent = metricExtent(
      (DATA.productPanel || []).filter((row) => row.flow === flow),
      metric
    );
    if (mapNode) {
      Plotly.react(mapNode, [{
        type: 'choropleth',
        locations: rows.map((row) => row.iso3),
        z: rows.map((row) => row[metric]),
        text: rows.map((row) => row.country),
        zmin: extent[0],
        zmax: extent[1],
        colorscale: [[0, '#dbeafe'], [0.5, '#60a5fa'], [1, '#0f172a']],
        hovertemplate: '<b>%{text}</b><br>' + metricLabel(metric) + ': %{z:.3f}<extra></extra>'
      }], {
        margin: { l: 0, r: 0, t: 6, b: 0 },
        geo: { projection: { type: 'natural earth' }, showframe: false, showcoastlines: true, bgcolor: 'rgba(0,0,0,0)' },
        paper_bgcolor: 'rgba(0,0,0,0)'
      }, CONFIG);
    }
    if (linesNode) {
      const selected = Array.from(document.querySelectorAll('.exercise1-country-check:checked')).map((el) => el.value);
      const lineRows = (DATA.productPanel || []).filter((row) => row.flow === flow && selected.includes(row.iso3));
      const traces = Array.from(groupRows(lineRows, 'iso3').values()).map((items, idx) => {
        items.sort((a, b) => Number(a.year) - Number(b.year));
        return {
          type: 'scatter',
          mode: 'lines+markers',
          name: items[0].country,
          x: items.map((row) => row.year),
          y: items.map((row) => row[metric]),
          line: { color: COLORS[idx % COLORS.length], width: 2 }
        };
      });
      Plotly.react(linesNode, traces, layout(metricLabel(metric) + ' country trajectories', metricLabel(metric), 'Year'), CONFIG);
    }
    if (rankNode) {
      const rankRows = (DATA.rankings || []).filter((row) => row.metric === metric && row.flow === flow).slice(0, 20).reverse();
      Plotly.react(rankNode, [{
        type: 'bar',
        orientation: 'h',
        x: rankRows.map((row) => row.metric_value),
        y: rankRows.map((row) => row.country),
        marker: { color: METRICS[metric].color }
      }], layout('Latest ' + flow + ' rankings', metricLabel(metric), ''), { ...CONFIG, displayModeBar: false });
    }
  }

  function setupExercise1() {
    const yearSelect = byId('exercise1-year');
    const countryList = byId('exercise1-country-list');
    if (!yearSelect || !countryList) return;
    const years = Array.from(new Set((DATA.productPanel || []).map((row) => Number(row.year)).filter((v) => Number.isFinite(v)))).sort((a, b) => a - b);
    yearSelect.innerHTML = years.map((year) => '<option value="' + year + '">' + year + '</option>').join('');
    yearSelect.value = String(years[years.length - 1] || '');
    const slider = byId('exercise1-year-slider');
    const label = byId('exercise1-year-label');
    if (slider && years.length) {
      slider.min = String(years[0]);
      slider.max = String(years[years.length - 1]);
      slider.value = yearSelect.value;
      byId('exercise1-year-min').textContent = String(years[0]);
      byId('exercise1-year-max').textContent = String(years[years.length - 1]);
      label.textContent = yearSelect.value;
      slider.addEventListener('input', () => {
        const requested = Number(slider.value);
        const nearest = years.reduce((best, value) =>
          Math.abs(value - requested) < Math.abs(best - requested) ? value : best
        , years[0]);
        yearSelect.value = String(nearest);
        label.textContent = String(nearest);
        renderExercise1();
      });
    }
    const defaults = new Set(['IND', 'USA', 'CHN', 'DEU', 'BRA']);
    countryList.innerHTML = (DATA.countries || []).map((row) => (
      '<label><input class="exercise1-country-check" type="checkbox" value="' + row.iso3 + '"' +
      (defaults.has(row.iso3) ? ' checked' : '') + '> ' + row.country + '</label>'
    )).join('');
    byId('exercise1-country-search')?.addEventListener('input', (event) => {
      const q = String(event.target.value || '').toLowerCase();
      countryList.querySelectorAll('label').forEach((label) => {
        label.style.display = label.textContent.toLowerCase().includes(q) ? 'flex' : 'none';
      });
    });
    byId('exercise1-select-all')?.addEventListener('click', () => {
      countryList.querySelectorAll('input').forEach((el) => { el.checked = true; });
      renderExercise1();
    });
    byId('exercise1-clear-all')?.addEventListener('click', () => {
      countryList.querySelectorAll('input').forEach((el) => { el.checked = false; });
      renderExercise1();
    });
    ['exercise1-flow', 'exercise1-year'].forEach((id) => byId(id)?.addEventListener('change', () => {
      if (slider) slider.value = yearSelect.value;
      if (label) label.textContent = yearSelect.value;
      renderExercise1();
    }));
    countryList.addEventListener('change', renderExercise1);
    renderExercise1();
  }

  function renderExercise2() {
    const node = byId('exercise2-growth');
    const node2 = byId('exercise2-products');
    if (!node || !node2) return;
    const metric = currentMetric();
    const flow = byId('exercise2-flow')?.value || 'Exports';
    const horizon = Number(byId('exercise2-horizon')?.value || 5);
    const rows = (DATA.ex02 || []).filter((row) => row.metric === metric && row.flow === flow && Number(row.horizon) === horizon);
    Plotly.react(node, [{
      type: 'bar',
      x: rows.map((row) => row.concentration_bucket),
      y: rows.map((row) => row.mean_annualized_trade_growth_log),
      marker: { color: METRICS[metric].color }
    }], layout('Trade growth by concentration bucket', 'Mean annualized trade growth', ''), { ...CONFIG, displayModeBar: false });
    Plotly.react(node2, [{
      type: 'bar',
      x: rows.map((row) => row.concentration_bucket),
      y: rows.map((row) => row.mean_annualized_product_active_count_growth_log),
      marker: { color: '#b45309' }
    }], layout('Active-product growth by concentration bucket', 'Mean annualized active-product growth', ''), { ...CONFIG, displayModeBar: false });
  }

  function renderExercise3() {
    const metric = currentMetric();
    const trend = byId('exercise3-trend');
    const latest = byId('exercise3-latest');
    if (!trend || !latest) return;
    const grouped = groupRows(DATA.ex03Yearly || [], 'import_bin');
    const traces = Array.from(grouped.entries()).map(([bin, rows], idx) => {
      rows.sort((a, b) => Number(a.year) - Number(b.year));
      return {
        type: 'scatter',
        mode: 'lines',
        name: bin.replace(/_/g, ' '),
        x: rows.map((row) => row.year),
        y: rows.map((row) => row[metric]),
        line: { color: COLORS[idx % COLORS.length], width: 2 }
      };
    });
    Plotly.react(trend, traces, layout('Import-bin concentration over time', metricLabel(metric), 'Year'), CONFIG);
    const latestRows = (DATA.ex03Latest || []).slice().sort((a, b) => Number(b[metric]) - Number(a[metric]));
    Plotly.react(latest, [{
      type: 'bar',
      x: latestRows.map((row) => row.import_bin.replace(/_/g, ' ')),
      y: latestRows.map((row) => row[metric]),
      marker: { color: METRICS[metric].color },
      customdata: latestRows.map((row) => row.median_import_share),
      hovertemplate: '%{x}<br>' + metricLabel(metric) + ': %{y:.3f}<br>Median import share: %{customdata:.1%}<extra></extra>'
    }], layout('Latest-year bin comparison', metricLabel(metric), ''), { ...CONFIG, displayModeBar: false });
  }

  function renderNonenergyExplorer() {
    const metric = currentMetric();
    const mapNode = byId('exercise3-nonenergy-map');
    const linesNode = byId('exercise3-nonenergy-lines');
    if (!mapNode || !linesNode) return;
    const year = Number(byId('exercise3-year')?.value || 2024);
    const allRows = DATA.nonenergyAnnual || [];
    const rows = allRows.filter((row) => Number(row.year) === year);
    const extent = metricExtent(allRows, metric);
    Plotly.react(mapNode, [{
      type: 'choropleth',
      locations: rows.map((row) => row.iso3),
      z: rows.map((row) => row[metric]),
      text: rows.map((row) => row.country),
      zmin: extent[0],
      zmax: extent[1],
      colorscale: [[0, '#dbeafe'], [0.5, '#2dd4bf'], [1, '#172554']],
      colorbar: { title: metricLabel(metric) },
      hovertemplate: '<b>%{text}</b><br>' + metricLabel(metric) + ': %{z:.3f}<extra></extra>'
    }], {
      margin: { l: 0, r: 0, t: 6, b: 0 },
      geo: { projection: { type: 'natural earth' }, showframe: false, showcoastlines: true, bgcolor: 'rgba(0,0,0,0)' },
      paper_bgcolor: 'rgba(0,0,0,0)'
    }, CONFIG);
    const selected = Array.from(document.querySelectorAll('.exercise3-country-check:checked')).map((el) => el.value);
    const lineRows = allRows.filter((row) => selected.includes(row.iso3));
    const traces = Array.from(groupRows(lineRows, 'iso3').values()).map((items, idx) => {
      items.sort((a, b) => Number(a.year) - Number(b.year));
      return {
        type: 'scatter',
        mode: 'lines+markers',
        name: items[0].country,
        x: items.map((row) => row.year),
        y: items.map((row) => row[metric]),
        line: { color: COLORS[idx % COLORS.length], width: 2 }
      };
    });
    Plotly.react(linesNode, traces, layout('Non-energy import ' + metricLabel(metric) + ' trajectories', metricLabel(metric), 'Year'), CONFIG);
  }

  function setupNonenergyExplorer() {
    const yearSelect = byId('exercise3-year');
    const countryList = byId('exercise3-country-list');
    if (!yearSelect || !countryList) return;
    const rows = DATA.nonenergyAnnual || [];
    const years = Array.from(new Set(rows.map((row) => Number(row.year)).filter(Number.isFinite))).sort((a, b) => a - b);
    yearSelect.innerHTML = years.map((year) => '<option value="' + year + '">' + year + '</option>').join('');
    yearSelect.value = String(years[years.length - 1] || '');
    const slider = byId('exercise3-year-slider');
    const label = byId('exercise3-year-label');
    if (slider && years.length) {
      slider.min = String(years[0]);
      slider.max = String(years[years.length - 1]);
      slider.value = yearSelect.value;
      byId('exercise3-year-min').textContent = String(years[0]);
      byId('exercise3-year-max').textContent = String(years[years.length - 1]);
      label.textContent = yearSelect.value;
      slider.addEventListener('input', () => {
        const requested = Number(slider.value);
        const nearest = years.reduce((best, value) =>
          Math.abs(value - requested) < Math.abs(best - requested) ? value : best
        , years[0]);
        yearSelect.value = String(nearest);
        label.textContent = String(nearest);
        renderNonenergyExplorer();
      });
    }
    const countries = Array.from(groupRows(rows, 'iso3').entries()).map(([iso3, items]) => ({
      iso3,
      country: items[0].country
    })).sort((a, b) => a.country.localeCompare(b.country));
    const defaults = new Set(['IND', 'USA', 'CHN', 'DEU', 'BRA']);
    countryList.innerHTML = countries.map((row) => (
      '<label><input class="exercise3-country-check" type="checkbox" value="' + escapeHtml(row.iso3) + '"' +
      (defaults.has(row.iso3) ? ' checked' : '') + '> ' + escapeHtml(row.country) + '</label>'
    )).join('');
    byId('exercise3-country-search')?.addEventListener('input', (event) => {
      const query = String(event.target.value || '').toLowerCase();
      countryList.querySelectorAll('label').forEach((node) => {
        node.style.display = node.textContent.toLowerCase().includes(query) ? 'flex' : 'none';
      });
    });
    byId('exercise3-select-all')?.addEventListener('click', () => {
      countryList.querySelectorAll('input').forEach((node) => { node.checked = true; });
      renderNonenergyExplorer();
    });
    byId('exercise3-clear-all')?.addEventListener('click', () => {
      countryList.querySelectorAll('input').forEach((node) => { node.checked = false; });
      renderNonenergyExplorer();
    });
    countryList.addEventListener('change', renderNonenergyExplorer);
    renderNonenergyExplorer();
  }

  const RANK_BUCKETS = [
    ['top5', 'Top 5', '#1f77b4'],
    ['rank6_50', 'Ranks 6-50', '#fdbf6f'],
    ['rank51_200', 'Ranks 51-200', '#86c5da'],
    ['rank201_plus', 'Rank 201+ tail', '#cfd4dc']
  ];

  function rankBucketRows() {
    const metric = currentMetric();
    const group = byId('rank-bucket-group')?.value || '__all__';
    const query = String(byId('rank-bucket-search')?.value || '').trim().toLowerCase();
    const drivers = new Map((DATA.nonenergyDrivers || [])
      .filter((row) => row.metric === metric)
      .map((row) => [row.iso3, row]));
    let rows = (DATA.nonenergySnapshots || []).map((row) => ({
      ...row,
      driver: drivers.get(row.iso3) || null
    }));
    if (group !== '__all__') rows = rows.filter((row) => row.driver && row.driver.main_driver_group === group);
    if (query) rows = rows.filter((row) => String(row.country).toLowerCase().includes(query) || String(row.iso3).toLowerCase().includes(query));
    return rows;
  }

  function renderRankBucketOverview() {
    const node = byId('rank-bucket-overview');
    if (!node) return;
    const sortMode = byId('rank-bucket-sort')?.value || 'end_top5_desc';
    const rows = rankBucketRows();
    const byCountry = Array.from(groupRows(rows, 'iso3').entries()).map(([iso3, items]) => {
      const end = items.find((row) => row.snapshot === 'end') || items[items.length - 1];
      return { iso3, country: end.country, end, driver: end.driver, items };
    });
    byCountry.sort((a, b) => {
      if (sortMode === 'country') return a.country.localeCompare(b.country);
      if (sortMode === 'driver_group') return String(a.driver?.main_driver_group || '').localeCompare(String(b.driver?.main_driver_group || '')) || a.country.localeCompare(b.country);
      if (sortMode === 'end_tail_desc') return Number(b.end.rank201_plus_share) - Number(a.end.rank201_plus_share);
      return Number(b.end.top5_share) - Number(a.end.top5_share);
    });
    const ordered = byCountry.flatMap((country) => country.items.slice().sort((a, b) => {
      const order = { start: 0, mid: 1, end: 2 };
      return order[a.snapshot] - order[b.snapshot];
    }));
    const labels = ordered.map((row) => row.country + '  ' + row.snapshot[0].toUpperCase() + row.snapshot.slice(1) + ' ' + row.year);
    const metric = currentMetric();
    const traces = RANK_BUCKETS.map(([key, label, color]) => ({
      type: 'bar',
      orientation: 'h',
      name: label,
      x: ordered.map((row) => row[key + '_share']),
      y: labels,
      marker: { color },
      customdata: ordered.map((row) => [row.iso3, row[key + '_' + metric + '_contribution'], row.active_nonenergy_products]),
      hovertemplate: '<b>%{y}</b><br>' + label + ': %{x:.1%}<br>' + metricLabel(metric) + ' contribution: %{customdata[1]:.3f}<br>Active products: %{customdata[2]:,.0f}<extra></extra>'
    }));
    const chartLayout = layout('Non-energy import basket decomposition', 'Country snapshot', 'Share of non-energy imports');
    chartLayout.barmode = 'stack';
    chartLayout.height = Math.max(520, ordered.length * 24);
    chartLayout.xaxis.tickformat = '.0%';
    chartLayout.yaxis = { automargin: true, autorange: 'reversed' };
    chartLayout.legend = { orientation: 'h', y: 1.02, x: 0 };
    Plotly.react(node, traces, chartLayout, CONFIG);
    if (node.removeAllListeners) node.removeAllListeners('plotly_click');
    node.on('plotly_click', (event) => {
      const iso3 = event?.points?.[0]?.customdata?.[0];
      if (!iso3) return;
      const select = byId('rank-bucket-country');
      if (select) select.value = iso3;
      renderRankBucketFocus(iso3);
    });
  }

  function renderRankBucketFocus(iso3) {
    const node = byId('rank-bucket-country-chart');
    const detail = byId('rank-bucket-detail');
    const title = byId('rank-bucket-focus-title');
    if (!node || !detail || !title) return;
    const selected = iso3 || byId('rank-bucket-country')?.value;
    const rows = (DATA.nonenergySnapshots || []).filter((row) => row.iso3 === selected).sort((a, b) => Number(a.year) - Number(b.year));
    if (!rows.length) return;
    title.textContent = 'Country Focus: ' + rows[0].country;
    const traces = RANK_BUCKETS.map(([key, label, color]) => ({
      type: 'bar',
      orientation: 'h',
      name: label,
      x: rows.map((row) => row[key + '_share']),
      y: rows.map((row) => row.snapshot[0].toUpperCase() + row.snapshot.slice(1) + ' ' + row.year),
      marker: { color },
      hovertemplate: label + ': %{x:.1%}<extra></extra>'
    }));
    const focusLayout = layout('Rank-bucket shares', '', 'Share of non-energy imports');
    focusLayout.barmode = 'stack';
    focusLayout.xaxis.tickformat = '.0%';
    focusLayout.yaxis = { autorange: 'reversed', automargin: true };
    focusLayout.legend = { orientation: 'h', y: -0.22 };
    Plotly.react(node, traces, focusLayout, { ...CONFIG, displayModeBar: false });
    const latest = rows[rows.length - 1];
    const metric = currentMetric();
    const driver = (DATA.nonenergyDrivers || []).find(
      (row) => row.iso3 === selected && row.metric === metric
    );
    const products = (DATA.nonenergyTopProducts || [])
      .filter((row) => row.iso3 === selected && row.snapshot === latest.snapshot && Number(row.year) === Number(latest.year))
      .sort((a, b) => Number(a.rank) - Number(b.rank));
    detail.innerHTML =
      '<div class="rank-bucket-detail-title">' + escapeHtml(latest.country) + ' (' + escapeHtml(latest.iso3) + ')</div>' +
      '<p>' + escapeHtml(latest.snapshot[0].toUpperCase() + latest.snapshot.slice(1)) + ' ' + escapeHtml(latest.year) + '</p>' +
      '<div class="rank-bucket-metrics">' +
        '<div class="rank-bucket-metric"><span>Non-energy imports</span><strong>' + usdShort(latest.total_nonenergy_imports) + '</strong></div>' +
        '<div class="rank-bucket-metric"><span>Active HS1992 families</span><strong>' + Number(latest.active_nonenergy_products).toLocaleString() + '</strong></div>' +
        '<div class="rank-bucket-metric"><span>' + escapeHtml(metricLabel(metric)) + '</span><strong>' + fmt(latest[metric], 3) + '</strong></div>' +
        '<div class="rank-bucket-metric"><span>Main driver</span><strong>' + escapeHtml(driver?.main_driver_bucket_label || 'n/a') + '</strong></div>' +
      '</div>' +
      '<p><strong>Driver classification:</strong> ' + escapeHtml(driver?.main_driver_group || 'n/a') +
      (driver ? ' · ' + escapeHtml(driver.metric_change_direction) +
        ' · start-to-end metric change ' + fmt(driver.delta_metric, 3) : '') + '</p>' +
      '<strong>Top non-energy product families</strong>' +
      '<ul class="rank-bucket-products">' + products.map((product) =>
        '<li class="rank-bucket-product">' +
          '<span class="rank-bucket-product-name">' + escapeHtml(product.product_label) + '</span>' +
          '<span class="rank-bucket-product-code">HS1992 ' + escapeHtml(product.cmd_code) + '</span>' +
          '<span class="rank-bucket-product-value">' + usdShort(product.trade_value) + ' · ' + pct(product.share) + '</span>' +
        '</li>'
      ).join('') + '</ul>';
  }

  function setupRankBucketExplorer() {
    const countrySelect = byId('rank-bucket-country');
    const groupSelect = byId('rank-bucket-group');
    if (!countrySelect || !groupSelect) return;
    const countries = Array.from(groupRows(DATA.nonenergySnapshots || [], 'iso3').entries()).map(([iso3, rows]) => ({
      iso3,
      country: rows[0].country
    })).sort((a, b) => a.country.localeCompare(b.country));
    countrySelect.innerHTML = countries.map((row) => '<option value="' + escapeHtml(row.iso3) + '">' + escapeHtml(row.country) + '</option>').join('');
    const metric = currentMetric();
    const groups = Array.from(new Set((DATA.nonenergyDrivers || []).filter((row) => row.metric === metric).map((row) => row.main_driver_group))).sort();
    groupSelect.innerHTML = '<option value="__all__">All driver groups</option>' + groups.map((group) => '<option value="' + escapeHtml(group) + '">' + escapeHtml(group) + '</option>').join('');
    if (countries.some((row) => row.iso3 === 'IND')) countrySelect.value = 'IND';
    ['rank-bucket-group', 'rank-bucket-sort'].forEach((id) => byId(id)?.addEventListener('change', renderRankBucketOverview));
    byId('rank-bucket-search')?.addEventListener('input', renderRankBucketOverview);
    countrySelect.addEventListener('change', () => renderRankBucketFocus(countrySelect.value));
    renderRankBucketOverview();
    renderRankBucketFocus(countrySelect.value);
  }

  function renderExercise4() {
    const trend = byId('exercise4-trend');
    const latest = byId('exercise4-latest');
    if (!trend || !latest) return;
    const rows = (DATA.ex04Yearly || []).sort((a, b) => Number(a.year) - Number(b.year));
    Plotly.react(trend, [
      { type: 'scatter', mode: 'lines', name: 'Top supplier share', x: rows.map((r) => r.year), y: rows.map((r) => r.top_supplier_share), line: { color: '#0f766e', width: 2 } },
      { type: 'scatter', mode: 'lines', name: 'Source HHI', x: rows.map((r) => r.year), y: rows.map((r) => r.source_hhi), line: { color: '#b45309', width: 2 } }
    ], layout('Supplier dominance over time', 'Median value', 'Year'), CONFIG);
    const latestRows = (DATA.ex04Latest || []).slice(0, 20).reverse();
    Plotly.react(latest, [{
      type: 'bar',
      orientation: 'h',
      x: latestRows.map((r) => r.weighted_mean_top_supplier_share),
      y: latestRows.map((r) => r.country),
      marker: { color: '#0f766e' },
      customdata: latestRows.map((r) => r.weighted_mean_source_hhi),
      hovertemplate: '<b>%{y}</b><br>Top supplier share: %{x:.1%}<br>Source HHI: %{customdata:.3f}<extra></extra>'
    }], layout('Latest highest supplier dominance', 'Top supplier share', ''), { ...CONFIG, displayModeBar: false });
  }

  function renderExercise6() {
    const metric = currentMetric();
    const trend = byId('exercise6-trend');
    const latest = byId('exercise6-sensitivity');
    if (!trend || !latest) return;
    const flow = byId('exercise6-flow')?.value || 'Exports';
    const rows = (DATA.ex06Yearly || []).filter((row) => row.flow === flow);
    const traces = Array.from(groupRows(rows, 'variant').entries()).map(([variant, items], idx) => {
      items.sort((a, b) => Number(a.year) - Number(b.year));
      return {
        type: 'scatter',
        mode: 'lines',
        name: variant,
        x: items.map((row) => row.year),
        y: items.map((row) => row[metric]),
        line: { color: COLORS[idx % COLORS.length], width: 2 }
      };
    });
    Plotly.react(trend, traces, layout(metricLabel(metric) + ' under HS2 exclusions', metricLabel(metric), 'Year'), CONFIG);
    const sens = (DATA.ex06Sensitivity || []).filter((row) => row.flow === flow).slice(0, 20).reverse();
    Plotly.react(latest, [{
      type: 'bar',
      orientation: 'h',
      x: sens.map((row) => row['abs_delta_' + metric]),
      y: sens.map((row) => row.excluded_hs2),
      marker: { color: METRICS[metric].color },
      customdata: sens.map((row) => row.trade_share_removed),
      hovertemplate: 'HS2 %{y}<br>|delta|: %{x:.3f}<br>Removed trade share: %{customdata:.1%}<extra></extra>'
    }], layout('Largest exclusion sensitivities', '|delta|', ''), { ...CONFIG, displayModeBar: false });
  }

  function renderExercise10() {
    const metric = currentMetric();
    const trend = byId('exercise10-trend');
    const latest = byId('exercise10-latest');
    if (!trend || !latest) return;
    const flow = byId('exercise10-flow')?.value || 'Exports';
    const benchmark = byId('exercise10-benchmark')?.value || 'hs2_preserving_within_sector_random_allocation';
    const rows = (DATA.ex10Yearly || []).filter((row) => row.flow === flow && row.benchmark_null === benchmark).sort((a, b) => Number(a.year) - Number(b.year));
    Plotly.react(trend, [
      { type: 'scatter', mode: 'lines', name: 'Actual', x: rows.map((r) => r.year), y: rows.map((r) => r['actual_' + metric]), line: { color: '#0f766e', width: 2 } },
      { type: 'scatter', mode: 'lines', name: 'Sim median', x: rows.map((r) => r.year), y: rows.map((r) => r['sim_' + metric]), line: { color: '#94a3b8', width: 2, dash: 'dash' } }
    ], layout('Actual versus benchmark median', metricLabel(metric), 'Year'), CONFIG);
    const latestRows = (DATA.ex10Latest || []).filter((row) => row.flow === flow && row.benchmark_null === benchmark).slice().sort((a, b) => Number(b['actual_minus_sim_median_' + metric]) - Number(a['actual_minus_sim_median_' + metric])).slice(0, 20).reverse();
    Plotly.react(latest, [{
      type: 'bar',
      orientation: 'h',
      x: latestRows.map((row) => row['actual_minus_sim_median_' + metric]),
      y: latestRows.map((row) => row.country),
      marker: { color: METRICS[metric].color }
    }], layout('Largest benchmark gaps', 'Actual minus simulated median', ''), { ...CONFIG, displayModeBar: false });
  }

  function renderExercise11() {
    const metric = currentMetric();
    const trend = byId('exercise11-trend');
    const latest = byId('exercise11-top');
    if (!trend || !latest) return;
    const flow = byId('exercise11-flow')?.value || 'Exports';
    const rows = (DATA.ex11Yearly || []).filter((row) => row.metric === metric && row.flow === flow).sort((a, b) => Number(a.year) - Number(b.year));
    Plotly.react(trend, [
      { type: 'scatter', mode: 'lines', name: 'Median absolute contribution', x: rows.map((r) => r.year), y: rows.map((r) => r.median_abs_contribution), line: { color: METRICS[metric].color, width: 2 } },
      { type: 'scatter', mode: 'lines', name: 'Max absolute contribution', x: rows.map((r) => r.year), y: rows.map((r) => r.max_abs_contribution), line: { color: '#b45309', width: 2 } }
    ], layout('Leave-one-out contribution scale over time', 'Absolute contribution', 'Year'), CONFIG);
    const topRows = (DATA.ex11Top || []).filter((row) => row.metric === metric && row.flow === flow).slice().reverse();
    Plotly.react(latest, [{
      type: 'bar',
      orientation: 'h',
      x: topRows.map((row) => row.max_abs_contribution),
      y: topRows.map((row) => row.product_label),
      marker: { color: METRICS[metric].color },
      hovertemplate: '<b>%{y}</b><br>Max abs. contribution: %{x:.3f}<extra></extra>'
    }], layout('Top latest product contributors', 'Max absolute contribution', ''), { ...CONFIG, displayModeBar: false });
  }

  function renderExercise12() {
    const metric = currentMetric();
    const growth = byId('exercise12-growth');
    const components = byId('exercise12-components');
    if (!growth || !components) return;
    const flow = byId('exercise12-flow')?.value || 'Exports';
    const horizon = Number(byId('exercise12-horizon')?.value || 5);
    const rows = (DATA.ex12 || []).filter((row) => row.metric === metric && row.flow === flow && Number(row.horizon) === horizon);
    Plotly.react(growth, [{
      type: 'bar',
      x: rows.map((row) => row.base_concentration_bucket),
      y: rows.map((row) => row.mean_annualized_trade_growth_log),
      marker: { color: METRICS[metric].color }
    }], layout('Trade growth by base concentration bucket', 'Mean annualized trade growth', ''), { ...CONFIG, displayModeBar: false });
    Plotly.react(components, [
      { type: 'bar', name: 'Products', x: rows.map((row) => row.base_concentration_bucket), y: rows.map((row) => row.mean_annualized_product_active_count_growth_log), marker: { color: '#0f766e' } },
      { type: 'bar', name: 'Partners', x: rows.map((row) => row.base_concentration_bucket), y: rows.map((row) => row.mean_annualized_partner_active_count_growth_log), marker: { color: '#2563eb' } },
      { type: 'bar', name: 'Cells', x: rows.map((row) => row.base_concentration_bucket), y: rows.map((row) => row.mean_annualized_cell_active_count_growth_log), marker: { color: '#b45309' } }
    ], Object.assign(layout('Growth decomposition components', 'Mean annualized growth', ''), { barmode: 'group' }), { ...CONFIG, displayModeBar: false });
  }

  function renderCadotExposurePage() {
    const exposureNode = byId('exposure-gdp-exposure');
    const alignmentNode = byId('exposure-gdp-alignment');
    if (!exposureNode || !alignmentNode) return;
    const rows = DATA.cadotExposureYearly || [];

    function tracesForOutcome(outcome) {
      const palette = {
        baseline: '#0f766e',
        noncommodity_broad: '#b45309'
      };
      const sampleStyles = {
        all_available: 'solid',
        fixed_country_2018_2024: 'dot'
      };
      const sampleLabels = {
        all_available: 'All available',
        fixed_country_2018_2024: 'Fixed-country 2018-2024'
      };
      const traces = [];
      ['baseline', 'noncommodity_broad'].forEach((variant) => {
        ['all_available', 'fixed_country_2018_2024'].forEach((window) => {
          const series = rows
            .filter((row) => row.outcome === outcome && row.variant === variant && row.sample_window === window)
            .sort((a, b) => Number(a.year) - Number(b.year));
          if (!series.length) return;
          traces.push({
            type: 'scatter',
            mode: 'lines+markers',
            name: (variant === 'baseline' ? 'Baseline' : 'Non-commodity') + ' · ' + sampleLabels[window],
            x: series.map((row) => row.year),
            y: series.map((row) => row.spearman_size_outcome),
            customdata: series.map((row) => [row.n_countries, sampleLabels[window]]),
            line: { color: palette[variant], width: window === 'all_available' ? 2.6 : 2.0, dash: sampleStyles[window] },
            marker: { size: window === 'all_available' ? 7 : 6 },
            hovertemplate:
              '<b>%{fullData.name}</b><br>Year: %{x}<br>Spearman: %{y:.3f}<br>N countries: %{customdata[0]}<br>Sample: %{customdata[1]}<extra></extra>'
          });
        });
      });
      return traces;
    }

    const exposureLayout = layout(
      'GDP correlation with world-product exposure',
      'Spearman(rank GDP, rank exposure)',
      'Year'
    );
    exposureLayout.shapes = [{ type: 'line', x0: 2000, x1: 2024, y0: 0, y1: 0, line: { color: '#9ca3af', width: 1, dash: 'dot' } }];
    Plotly.react(exposureNode, tracesForOutcome('world_share_exposure'), exposureLayout, CONFIG);

    const alignmentLayout = layout(
      'GDP correlation with within-country product alignment',
      'Spearman(rank GDP, alignment)',
      'Year'
    );
    alignmentLayout.shapes = [{ type: 'line', x0: 2000, x1: 2024, y0: 0, y1: 0, line: { color: '#9ca3af', width: 1, dash: 'dot' } }];
    Plotly.react(alignmentNode, tracesForOutcome('spearman_product_alignment'), alignmentLayout, CONFIG);
  }

  function renderTheilAppendix() {
    const node = byId('theil-appendix-chart');
    if (!node) return;
    const rows = (DATA.appendixYearly || []).sort((a, b) => Number(a.year) - Number(b.year));
    Plotly.react(node, [
      { type: 'scatter', mode: 'lines', name: 'Exports', x: rows.filter((r) => r.flow === 'Exports').map((r) => r.year), y: rows.filter((r) => r.flow === 'Exports').map((r) => r.theil), line: { color: '#2563eb', width: 2 } },
      { type: 'scatter', mode: 'lines', name: 'Imports', x: rows.filter((r) => r.flow === 'Imports').map((r) => r.year), y: rows.filter((r) => r.flow === 'Imports').map((r) => r.theil), line: { color: '#0f766e', width: 2 } }
    ], layout('Median product-destination Theil over time', 'Median Theil', 'Year'), CONFIG);
  }

  document.addEventListener('DOMContentLoaded', () => {
    renderHubCharts();
    renderMetricOverview();
    setupExercise1();
    renderExercise2();
    renderExercise3();
    setupNonenergyExplorer();
    setupRankBucketExplorer();
    renderExercise4();
    renderExercise6();
    renderExercise10();
    renderExercise11();
    renderExercise12();
    renderCadotExposurePage();
    renderTheilAppendix();
    ['metric-overview-flow', 'metric-overview-growth-flow', 'metric-overview-growth-horizon', 'exercise2-flow', 'exercise2-horizon', 'exercise6-flow', 'exercise10-flow', 'exercise10-benchmark', 'exercise11-flow', 'exercise12-flow', 'exercise12-horizon']
      .forEach((id) => byId(id)?.addEventListener('change', () => {
        renderMetricOverview();
        renderExercise2();
        renderExercise6();
        renderExercise10();
        renderExercise11();
        renderExercise12();
      }));
    window.addEventListener('resize', relayout);
  });
})();
"""


def cadot_metric_page(metric: str, data: dict[str, Any]) -> str:
    label = cadot_metric_label(metric)
    yearly = data["yearly"].copy()
    if "dimension" in yearly.columns:
        yearly = yearly[yearly["dimension"].astype(str).eq("product")].copy()
    if "variant" in yearly.columns:
        yearly = yearly[yearly["variant"].astype(str).eq("baseline")].copy()
    latest_year = int(pd.to_numeric(yearly["year"], errors="coerce").max())
    latest_rows = yearly[pd.to_numeric(yearly["year"], errors="coerce").eq(latest_year)].copy()
    export_row = latest_rows[latest_rows["flow"].astype(str).eq("Exports")].head(1)
    import_row = latest_rows[latest_rows["flow"].astype(str).eq("Imports")].head(1)
    rankings = data["rankings"][data["rankings"]["metric"].astype(str).str.lower().eq(metric)].copy()
    top_row = rankings.sort_values(["flow", "rank"]).head(1)
    appendix_link = '<a class="button" href="appendix.html">Open Theil appendix</a>' if metric == "theil" else ""
    latest_export = None if export_row.empty else float(export_row.iloc[0][f"median_{metric}"])
    latest_import = None if import_row.empty else float(import_row.iloc[0][f"median_{metric}"])
    latest_top = None if top_row.empty else float(top_row.iloc[0]["metric_value"])
    latest_top_country = "" if top_row.empty else str(top_row.iloc[0]["country"])
    body = f"""
    <section class="hero">
      <div class="eyebrow">{escape(label)} site</div>
      <h1>{escape(label)} Trade Concentration</h1>
      <p>{escape(cadot_metric_definition(metric))} The interactive charts on this page use the harmonized Cadot 156 sample and the same website-facing rows as the download bundle.</p>
      {cadot_metric_switch(metric, None, 1)}
      <div class="stat-grid">
        <article class="stat-card"><span>Latest export median</span><strong>{dec(latest_export)}</strong><small>{latest_year} product rows</small></article>
        <article class="stat-card"><span>Latest import median</span><strong>{dec(latest_import)}</strong><small>{latest_year} product rows</small></article>
        <article class="stat-card"><span>Highest latest value</span><strong>{dec(latest_top)}</strong><small>{escape(latest_top_country)}</small></article>
      </div>
      <div class="inline-link-row">
        <a href="exercises/">All {escape(label)} exercises</a>
        <a href="../exposure/">World-product exposure</a>
        <a href="../downloads/">Downloads</a>
        {appendix_link}
      </div>
    </section>
    <section class="section">
      <div class="section-heading">
        <h2>Overview</h2>
        <p>Question-led views for the selected metric, with flows and horizons selectable where they matter.</p>
      </div>
      <div class="chart-grid">
        {cadot_chart_panel(f"{label} over time", "How concentrated are product baskets through time?", "metric-overview-trend")}
        {cadot_chart_panel("Latest rankings", "Which countries sit at the top of the latest distribution?", "metric-overview-ranking", '<label><span class="sr-only">Flow</span><select id="metric-overview-flow"><option value="Exports">Exports</option><option value="Imports">Imports</option></select></label>')}
      </div>
      <div class="chart-grid">
        {cadot_chart_panel("Growth buckets", "How do base concentration buckets line up with later trade growth?", "metric-overview-growth", '<label><span class="sr-only">Flow</span><select id="metric-overview-growth-flow"><option value="Exports">Exports</option><option value="Imports">Imports</option></select></label><label><span class="sr-only">Horizon</span><select id="metric-overview-growth-horizon"><option value="1">1 year</option><option value="3">3 years</option><option value="5" selected>5 years</option><option value="10">10 years</option></select></label>')}
        {cadot_chart_panel("Import-bin concentration", "Which import bins are most concentrated in this metric?", "metric-overview-bins")}
      </div>
      <div class="chart-grid">
        {cadot_chart_panel("Supplier dominance", "How much of import concentration comes from dominant source countries?", "metric-overview-suppliers")}
      </div>
    </section>
    <section class="section">
      <div class="section-heading"><h2>Extension Track</h2><p>Exercises 1, 2, 6, 10, and 12 for the selected metric.</p></div>
      {cadot_exercise_cards(metric, CADOT_EXERCISE_GROUPS["extension"], 1)}
      <div class="section-note">These pages mirror the old extension logic with Cadot-only data, metric-specific charts, and shared static figure benchmarks.</div>
      {cadot_figure_gallery(1, ["ex1_median_concentration_over_time", "ex6_before_after", "ex10_actual_vs_benchmark", "ex1_country_product_gini_lines"])}
    </section>
    <section class="section">
      <div class="section-heading"><h2>Import Track</h2><p>Exercises 3, 4, and 11 for the selected metric.</p></div>
      {cadot_exercise_cards(metric, CADOT_EXERCISE_GROUPS["imports"], 1)}
      <div class="section-note">Descriptive figures are shared when they answer a sample-composition question; metric-specific charts are rendered from the harmonized three-metric tables.</div>
      {cadot_figure_gallery(1, ["ex3_value_share", "ex4_supplier_distribution", "ex11_export_linkage_4pct", "ex11_india_supplier_scatter"])}
    </section>
    <section class="section">
      <div class="section-heading"><h2>Latest Rankings Table</h2><p>Latest available product rows for the selected metric.</p></div>
      {cadot_metric_focus_table(metric, next(spec for spec in EXERCISE_PAGE_SPECS if spec["short"] == "01"), data)}
    </section>
    <section class="section">
      <div class="section-heading"><h2>Downloads</h2><p>Metric pages share the same validated Cadot download bundle.</p></div>
      {cadot_download_grid(1, ["metric_headline_product_panel.csv", "metric_yearly_summary.csv", "metric_latest_rankings.csv", "validation_checks.csv", "cadot_three_metric_manifest.json"])}
    </section>
    """
    return cadot_page(f"{label} Site", metric, body, depth=1, page_key=f"cadot-{metric}", metric=metric)


def cadot_exercises_index_page(data: dict[str, Any]) -> str:
    cards = []
    for spec in EXERCISE_PAGE_SPECS:
        links = "".join(
            f'<a href="{cadot_asset_href(1, cadot_metric_exercise_path(metric, spec["short"]))}">{escape(cadot_metric_label(metric))}</a>'
            for metric in ["gini", "theil", "hhi"]
        )
        cards.append(
            f"""
      <article class="exercise-card">
        <span>Exercise {escape(spec['short'])}</span>
        <strong>{escape(spec['title'].split(':', 1)[-1].strip())}</strong>
        <small>{escape(spec['question'])}</small>
        <div class="inline-link-row">{links}</div>
      </article>
            """
        )
    body = f"""
    <section class="page-title">
      <div class="eyebrow">Exercise index</div>
      <h1>Cadot 156 Exercise Pages</h1>
      <p>Each exercise is available under all three metric sites. Shared descriptive figures are rerendered on the Cadot sample; metric-specific comparisons use the harmonized Gini, Theil, and HHI tables.</p>
    </section>
    <section class="section link-grid">
      {"".join(cards)}
    </section>
    """
    return cadot_page("Exercises", "exercises", body, depth=1, page_key="cadot-exercises")


def cadot_metric_exercises_index_page(metric: str) -> str:
    cards = []
    for spec in EXERCISE_PAGE_SPECS:
        cards.append(
            f"""
      <a class="exercise-card" href="exercise-{spec['short']}.html">
        <span>Exercise {escape(spec['short'])}</span>
        <strong>{escape(spec['title'].split(':', 1)[-1].strip())}</strong>
        <small>{escape(spec['question'])}</small>
      </a>
            """
        )
    body = f"""
    <section class="page-title">
      <div class="eyebrow">{escape(cadot_metric_label(metric))} exercises</div>
      <h1>{escape(cadot_metric_label(metric))} Exercise Pages</h1>
      <p>Metric-specific exercise pages for the harmonized Cadot 156 rerun.</p>
      {cadot_metric_switch(metric, None, 2)}
    </section>
    <section class="section link-grid">
      {"".join(cards)}
    </section>
    """
    return cadot_page(f"{cadot_metric_label(metric)} Exercises", metric, body, depth=2, page_key=f"cadot-{metric}-exercises", metric=metric)


def cadot_metric_exercise_chart_block(
    metric: str,
    short: str,
    data: dict[str, Any],
) -> str:
    def panel(
        title: str,
        description: str,
        chart_id: str,
        controls_html: str = "",
        tall: bool = False,
    ) -> str:
        return cadot_chart_panel(
            title,
            description,
            chart_id,
            controls_html,
            tall,
            cadot_graph_evidence(chart_id, metric, data),
        )

    if short == "01":
        return f"""
      <div class="tool-grid">
        <article class="chart-panel selector-panel">
          <div class="selector-actions">
            <input id="exercise1-country-search" type="search" placeholder="Find country">
            <button type="button" id="exercise1-select-all">All</button>
            <button type="button" id="exercise1-clear-all">Clear</button>
          </div>
          <div id="exercise1-country-list" class="country-list"></div>
          <p class="section-note">Use the list to control the cross-country line view. The map reads the selected metric in the selected year and flow.</p>
          <p><a href="exercise-03.html#nonenergy-explorer">Open the non-energy import explorer</a></p>
        </article>
        <div>
          {panel("Interactive map", "Where is the selected metric highest in the chosen year?", "exercise1-map", '<label><span class="sr-only">Flow</span><select id="exercise1-flow"><option value="Exports">Exports</option><option value="Imports">Imports</option></select></label><div class="year-control"><div class="year-control-head"><span>Year</span><output id="exercise1-year-label" for="exercise1-year-slider"></output></div><input id="exercise1-year-slider" type="range" min="2000" max="2024" step="1"><div class="year-range-labels"><span id="exercise1-year-min"></span><span id="exercise1-year-max"></span></div><select id="exercise1-year" class="sr-only" aria-label="Map year"></select></div>')}
          {panel("Country trajectories", "How do selected countries move through time?", "exercise1-lines", tall=True)}
          {panel("Latest rankings", "Which countries lead the latest distribution?", "exercise1-ranking")}
        </div>
      </div>
        """
    if short == "02":
        return '<div class="chart-grid">' + \
            panel("Trade growth", "How does later trade growth vary across concentration buckets?", "exercise2-growth", '<label><span class="sr-only">Flow</span><select id="exercise2-flow"><option value="Exports">Exports</option><option value="Imports">Imports</option></select></label><label><span class="sr-only">Horizon</span><select id="exercise2-horizon"><option value="1">1 year</option><option value="3">3 years</option><option value="5" selected>5 years</option><option value="10">10 years</option></select></label>') + \
            panel("Active-product growth", "Do concentrated states add products more slowly or more quickly?", "exercise2-products") + \
            '</div>'
    if short == "03":
        return f"""
      <div class="chart-grid">
        {panel("Import-bin trend", "Which BEC-style bins stay most concentrated over time?", "exercise3-trend")}
        {panel("Latest bin comparison", "Which bins sit highest in the latest year?", "exercise3-latest")}
      </div>
      <section class="embedded-tool-section" id="nonenergy-explorer">
        <div class="section-heading">
          <div>
            <h2>Non-Energy Import Map and Country Lines</h2>
            <p>Imports only. Energy is removed using the approved Exercise 3 BEC mapping before LT/HGL conversion to HS1992/H0.</p>
          </div>
        </div>
        <div class="tool-grid">
          <article class="chart-panel selector-panel">
            <div class="selector-actions">
              <input id="exercise3-country-search" type="search" placeholder="Find country">
              <button type="button" id="exercise3-select-all">All</button>
              <button type="button" id="exercise3-clear-all">Clear</button>
            </div>
            <div id="exercise3-country-list" class="country-list"></div>
          </article>
          <div>
            {panel("Non-energy import map", "Where does concentration remain high after removing energy?", "exercise3-nonenergy-map", '<div class="year-control"><div class="year-control-head"><span>Year</span><output id="exercise3-year-label" for="exercise3-year-slider"></output></div><input id="exercise3-year-slider" type="range" min="2000" max="2024" step="1"><div class="year-range-labels"><span id="exercise3-year-min"></span><span id="exercise3-year-max"></span></div><select id="exercise3-year" class="sr-only" aria-label="Non-energy map year"></select></div>')}
            {panel("Non-energy country trajectories", "How persistent is the selected metric after energy is removed?", "exercise3-nonenergy-lines", tall=True)}
          </div>
        </div>
      </section>
      <section class="embedded-tool-section" id="rank-bucket-explorer">
        <div class="tool-header">
          <div>
            <h2>Non-Energy Import Basket Rank Buckets</h2>
            <p>Earliest, midpoint, and latest available snapshots split each harmonized HS1992/H0 basket into the top five, ranks 6-50, ranks 51-200, and the rank-201+ tail.</p>
          </div>
          <div class="controls compact rank-bucket-controls">
            <label>Driver group <select id="rank-bucket-group" aria-label="Filter rank buckets by metric-specific driver"></select></label>
            <label>Sort <select id="rank-bucket-sort" aria-label="Sort rank-bucket chart">
              <option value="end_top5_desc">Latest top 5 high to low</option>
              <option value="end_tail_desc">Latest rank 201+ high to low</option>
              <option value="driver_group">Main driver group</option>
              <option value="country">Country A-Z</option>
            </select></label>
            <label>Country <select id="rank-bucket-country" aria-label="Focus rank-bucket country"></select></label>
            <label>Search <input id="rank-bucket-search" type="search" placeholder="Filter countries"></label>
          </div>
        </div>
        {cadot_graph_evidence("rank-bucket-overview", metric, data)}
        <div class="rank-bucket-layout">
          <div class="rank-bucket-main">
            <div class="rank-bucket-scroll">
              <div id="rank-bucket-overview" class="chart js-plotly-plot rank-bucket-overview"></div>
            </div>
          </div>
          <aside class="rank-bucket-side">
            <h3 id="rank-bucket-focus-title">Country Focus</h3>
            {cadot_graph_evidence("rank-bucket-country-chart", metric, data)}
            <div id="rank-bucket-country-chart" class="chart js-plotly-plot rank-bucket-focus"></div>
            <div id="rank-bucket-detail" class="detail-box">Select a country to inspect non-energy totals and top HS1992 product families.</div>
          </aside>
        </div>
      </section>
        """
    if short == "04":
        return '<div class="chart-grid">' + \
            panel("Supplier dominance trend", "Does dominant sourcing stay persistent through time?", "exercise4-trend") + \
            panel("Latest exposure leaders", "Which importers have the strongest dominant-supplier exposure?", "exercise4-latest") + \
            '</div>'
    if short == "06":
        return '<div class="chart-grid">' + \
            panel("Exclusion trend", "Does the metric collapse after removing lumpy HS2 sectors?", "exercise6-trend", '<label><span class="sr-only">Flow</span><select id="exercise6-flow"><option value="Exports">Exports</option><option value="Imports">Imports</option></select></label>') + \
            panel("Largest sensitivities", "Which HS2 exclusions move the metric most?", "exercise6-sensitivity") + \
            '</div>'
    if short == "10":
        return '<div class="chart-grid">' + \
            panel("Benchmark path", "How far above the benchmark does the metric sit over time?", "exercise10-trend", '<label><span class="sr-only">Flow</span><select id="exercise10-flow"><option value="Exports">Exports</option><option value="Imports">Imports</option></select></label><label><span class="sr-only">Benchmark</span><select id="exercise10-benchmark"><option value="hs2_preserving_within_sector_random_allocation">HS2-preserving</option><option value="active_count_random_allocation">Active-count</option></select></label>') + \
            panel("Latest benchmark gaps", "Which countries sit furthest above the benchmark?", "exercise10-latest") + \
            '</div>'
    if short == "11":
        return '<div class="chart-grid">' + \
            panel("Contribution scale", "How large are leave-one-out product contributions through time?", "exercise11-trend", '<label><span class="sr-only">Flow</span><select id="exercise11-flow"><option value="Exports">Exports</option><option value="Imports">Imports</option></select></label>') + \
            panel("Top latest products", "Which products drive the largest absolute contributions?", "exercise11-top") + \
            '</div>'
    if short == "12":
        return '<div class="chart-grid">' + \
            panel("Trade growth buckets", "How does later trade growth vary by base concentration bucket?", "exercise12-growth", '<label><span class="sr-only">Flow</span><select id="exercise12-flow"><option value="Exports">Exports</option><option value="Imports">Imports</option></select></label><label><span class="sr-only">Horizon</span><select id="exercise12-horizon"><option value="1">1 year</option><option value="3">3 years</option><option value="5" selected>5 years</option><option value="10">10 years</option></select></label>') + \
            panel("Component growth", "How do product, partner, and cell growth components differ by bucket?", "exercise12-components") + \
            '</div>'
    return '<p class="section-note">No interactive chart is configured for this page.</p>'


def cadot_metric_exercise_page(metric: str, spec: dict[str, Any], data: dict[str, Any]) -> str:
    label = cadot_metric_label(metric)
    body = f"""
    <section class="page-title">
      <div class="eyebrow">{escape(label)} Exercise {escape(spec['short'])}</div>
      <h1>{escape(spec['title'])}</h1>
      <p>{escape(spec['question'])}</p>
      {cadot_metric_switch(metric, spec['short'], 2)}
      {cadot_metric_exercise_subnav(metric, spec['short'], 2)}
    </section>
    <section class="section hypothesis-section">
      {cadot_exercise_hypothesis(metric, spec, data)}
    </section>
    <section class="section">
      <div class="section-heading"><h2>Interactive Metric View</h2><p>Selected metric: {escape(label)}. Shared descriptive figures, where present, are shown below and clearly separated from the metric-specific charts.</p></div>
      {cadot_metric_exercise_chart_block(metric, spec["short"], data)}
    </section>
    <section class="section">
      <div class="section-heading"><h2>Cross-Metric Snapshot</h2><p>The selected site is metric-first, but the same harmonized exercise exists for all three metrics.</p></div>
      {cadot_metric_cards_from_frame(data[spec["data_key"]])}
    </section>
    <section class="section">
      <div class="section-heading"><h2>Cadot Figure Set</h2><p>These figures are required by the Cadot build; the build now fails if any referenced asset is missing.</p></div>
      {cadot_figure_gallery(2, CADOT_EXERCISE_FIGURES[spec["short"]], metric, data)}
    </section>
    <section class="section">
      <div class="section-heading"><h2>Evidence Table</h2><p>Metric-focused table for the selected exercise page.</p></div>
      {cadot_metric_focus_table(metric, spec, data)}
    </section>
    <section class="section">
      <div class="section-heading"><h2>Downloads</h2><p>All downloads are Cadot-only staging artifacts from the harmonized rerun.</p></div>
      {cadot_download_grid(2, list(dict.fromkeys(spec["downloads"] + ([
          "nonenergy_import_metric_annual.csv",
          "nonenergy_import_reporter_coverage.csv",
          "nonenergy_import_rank_bucket_snapshots.csv",
          "nonenergy_import_top_products_snapshots.csv",
          "nonenergy_import_rank_bucket_drivers.csv",
          "nonenergy_visualization_manifest.json",
          "nonenergy_visualization_adversarial_review.md",
      ] if spec["short"] == "03" else []) + ["cadot_three_metric_manifest.json", "three_metric_adversarial_review.md"])))}
    </section>
    """
    return cadot_page(spec["title"], metric, body, depth=2, page_key=f"cadot-{metric}-exercise-{spec['short']}", metric=metric)


def cadot_downloads_page(data: dict[str, Any]) -> str:
    rows = []
    for filename, source in three_metric_download_paths(ACTIVE_SITE_SAMPLE).items():
        rows.append(
            {
                "file": f'<a href="../assets/downloads/{escape(filename)}">{escape(filename)}</a>',
                "size": cadot_format_size(source.stat().st_size),
                "kind": source.suffix.lstrip(".") or "artifact",
            }
        )
    body = f"""
    <section class="page-title">
      <div class="eyebrow">Downloads</div>
      <h1>Harmonized Cadot 156 Downloads</h1>
      <p>The previous native-HS Cadot website outputs are superseded. Exercise 11 is published only as a compressed CSV.</p>
    </section>
    <section class="section metric-route-table">
      {cadot_table(rows, [("file", "File", "text"), ("size", "Size", "text"), ("kind", "Type", "text")])}
    </section>
    """
    return cadot_page("Downloads", "downloads", body, depth=1, page_key="cadot-downloads")


def cadot_exposure_page(data: dict[str, Any]) -> str:
    summary = data["exposure_summary"].copy()
    summary = summary[
        summary["sample_window"].astype(str).eq("all_available")
        & summary["size_variable"].astype(str).eq("log_gdp_current_usd")
        & summary["outcome"].astype(str).isin(
            ["world_share_exposure", "spearman_product_alignment"]
        )
    ].copy()
    coverage = data["exposure_coverage"].copy()
    fixed_summary = data["exposure_fixed_summary"].copy()
    fixed_summary = fixed_summary[
        fixed_summary["size_variable"].astype(str).eq("log_gdp_current_usd")
        & fixed_summary["outcome"].astype(str).isin(
            ["world_share_exposure", "spearman_product_alignment"]
        )
    ].copy()
    all_models = data["exposure_models"].copy()
    models = all_models[
        all_models["model_label"].astype(str).eq("main_gdp_year_fe")
        & all_models["term"].astype(str).eq("log_gdp_current_usd")
        & all_models["outcome"].astype(str).isin(
            ["world_share_exposure", "spearman_product_alignment"]
        )
    ].copy()
    validation = data["exposure_validation"].copy()
    removed = data["exposure_removed"].copy()
    yearly = data["exposure_yearly"].copy()
    latest_year = int(pd.to_numeric(yearly["year"], errors="coerce").max())
    latest_removed = removed[pd.to_numeric(removed["year"], errors="coerce").eq(latest_year)].copy()
    latest_removed = latest_removed.sort_values(
        "broad_primary_share_removed", ascending=False
    ).head(20)

    baseline_alignment = summary[
        summary["variant"].astype(str).eq("baseline")
        & summary["outcome"].astype(str).eq("spearman_product_alignment")
    ].iloc[0]
    baseline_exposure = summary[
        summary["variant"].astype(str).eq("baseline")
        & summary["outcome"].astype(str).eq("world_share_exposure")
    ].iloc[0]
    baseline_exposure_yearly = yearly[
        yearly["sample_window"].astype(str).eq("all_available")
        & yearly["variant"].astype(str).eq("baseline")
        & yearly["size_variable"].astype(str).eq("log_gdp_current_usd")
        & yearly["outcome"].astype(str).eq("world_share_exposure")
    ].copy()
    baseline_exposure_yearly["year"] = pd.to_numeric(
        baseline_exposure_yearly["year"], errors="raise"
    ).astype(int)
    baseline_exposure_yearly["spearman_size_outcome"] = pd.to_numeric(
        baseline_exposure_yearly["spearman_size_outcome"], errors="raise"
    )
    recent_exposure = baseline_exposure_yearly.set_index("year")[
        "spearman_size_outcome"
    ].to_dict()
    main_gdp = all_models[
        all_models["variant"].astype(str).eq("baseline")
        & all_models["outcome"].astype(str).eq("world_share_exposure")
        & all_models["model_label"].astype(str).eq("main_gdp_year_fe")
        & all_models["term"].astype(str).eq("log_gdp_current_usd")
    ].iloc[0]
    conditional_gdp = all_models[
        all_models["variant"].astype(str).eq("baseline")
        & all_models["outcome"].astype(str).eq("world_share_exposure")
        & all_models["model_label"].astype(str).eq("conditional_gdp_gdppc_year_fe")
        & all_models["term"].astype(str).eq("log_gdp_current_usd")
    ].iloc[0]

    def exposure_p_text(value: Any) -> str:
        return f"{float(value):.7f}".rstrip("0").rstrip(".")

    card_rows = []
    for outcome in ["world_share_exposure", "spearman_product_alignment"]:
        for variant in ["baseline", "noncommodity_broad"]:
            row = summary[
                summary["outcome"].astype(str).eq(outcome)
                & summary["variant"].astype(str).eq(variant)
            ].head(1)
            if row.empty:
                continue
            card_rows.append(
                f"""
          <article class="stat-card">
            <span>{escape('Exposure' if outcome == 'world_share_exposure' else 'Alignment')} · {escape('Baseline' if variant == 'baseline' else 'Non-commodity')}</span>
            <strong>{dec(row.iloc[0]['mean_spearman'])}</strong>
            <small>Mean yearly GDP Spearman, 2000-2024</small>
          </article>
                """
            )

    body = f"""
    <section class="hero">
      <div class="eyebrow">Cadot world-product exposure</div>
      <h1>World-Product Exposure After Removing Broad Primary Commodities</h1>
      <p>This export-only page compares the inclusive world-basket baseline with a non-commodity variant that removes broad primary products from both the country basket and the world benchmark before shares and ranks are rebuilt.</p>
      <div class="stat-grid">
        {"".join(card_rows)}
      </div>
      <div class="inline-link-row">
        <a href="../downloads/">Open downloads</a>
        <a href="../gini/">Back to Gini site</a>
        <a href="../theil/">Back to Theil site</a>
        <a href="../hhi/">Back to HHI site</a>
      </div>
    </section>
    <section class="section">
      <div class="section-heading"><h2>Bottom Line</h2><p>Broad 156-reporter baseline, 2000-2024.</p></div>
      <p>Across countries, the annual rank correlation between GDP and within-country product alignment averages <strong>{float(baseline_alignment['mean_spearman']):.3f}</strong> and is positive in all {int(baseline_alignment['years'])} years. The annual GDP-world-product-exposure correlation averages <strong>{float(baseline_exposure['mean_spearman']):.3f}</strong> and is also positive in all {int(baseline_exposure['years'])} years.</p>
      <p>In the pooled year-fixed-effects regression, the coefficient on log GDP is <strong>{float(main_gdp['coefficient']):.4f}</strong> (raw p = <strong>{exposure_p_text(main_gdp['p_value'])}</strong>, with standard errors clustered by country). After controlling for GDP per capita, the log-GDP coefficient is <strong>{float(conditional_gdp['coefficient']):.4f}</strong> (raw p = <strong>{exposure_p_text(conditional_gdp['p_value'])}</strong>). These estimates support a descriptive size relationship; they do not identify a causal mechanism.</p>
      <p class="callout"><strong>There is no 2023-2024 reversal in the broad sample.</strong> The annual GDP-exposure correlations are {float(recent_exposure[2023]):.3f} in 2023 and {float(recent_exposure[2024]):.3f} in 2024.</p>
    </section>
    <section class="section">
      <div class="section-heading"><h2>Construction</h2><p>The non-commodity result is not a mechanical subtraction; the country shares are renormalized and the world product-share ranks are rebuilt after the broad-primary filter is applied.</p></div>
      <div class="overview-band">
        <article class="note-card">
          <h3>Exposure</h3>
          <p><code>E^NC_{{ct}} = sum_{{p in NC}} s^NC_{{cpt}} R^NC_{{pt}}</code></p>
          <p class="small">Higher values mean the country's export basket leans more toward products that are globally large inside the filtered non-commodity universe.</p>
        </article>
        <article class="note-card">
          <h3>Alignment</h3>
          <p><code>A^NC_{{ct}} = rho_p(s^NC_{{cpt}}, w^NC_{{pt}})</code></p>
          <p class="small">This is a within-country Spearman correlation across the country's active non-commodity export products, not a cross-country GDP regression coefficient.</p>
        </article>
      </div>
      <p class="callout">Broad-primary exclusions follow the shared Cadot classifier: raw agriculture, ores and minerals, fuels and refining, forestry, precious metals, and first-stage food/basic-metal processing. HS6 <strong>999999</strong> is excluded before harmonized product aggregation.</p>
    </section>
    <section class="section">
      <div class="section-heading"><h2>Question-Led Panels</h2><p>Solid lines use the full available Cadot sample. Dotted lines hold the country set fixed over 2018-2024.</p></div>
      <div class="chart-grid">
        {cadot_chart_panel("GDP and world-product exposure", "Does the GDP-exposure relationship survive the broad-primary exclusion?", "exposure-gdp-exposure", evidence_html=cadot_graph_evidence("exposure-gdp-exposure", "gini", data))}
        {cadot_chart_panel("GDP and within-country alignment", "Does the GDP-alignment relationship survive the broad-primary exclusion?", "exposure-gdp-alignment", evidence_html=cadot_graph_evidence("exposure-gdp-alignment", "gini", data))}
      </div>
    </section>
    <section class="section">
      <div class="section-heading"><h2>Fixed-Country Robustness</h2><p>These rows use only countries present in every year from 2018 through 2024 for both variants.</p></div>
      {cadot_table(clean_records(fixed_summary, list(fixed_summary.columns)), [("variant", "Variant", "text"), ("outcome", "Outcome", "text"), ("years", "Years", "int"), ("mean_spearman", "Mean Spearman", "dec"), ("median_spearman", "Median Spearman", "dec"), ("share_positive", "Share positive", "pct")])}
    </section>
    <section class="section">
      <div class="section-heading"><h2>Yearly Country Counts</h2><p>Counts reflect the number of country-years contributing to each yearly GDP correlation.</p></div>
      {cadot_table(clean_records(coverage, list(coverage.columns)), [("variant", "Variant", "text"), ("year", "Year", "year"), ("countries", "Countries", "int"), ("countries_with_exposure", "Exposure N", "int"), ("countries_with_alignment", "Alignment N", "int"), ("median_active_products", "Median active products", "int")])}
    </section>
    <section class="section">
      <div class="section-heading"><h2>Main GDP Year-FE Models</h2><p>These are the pooled descriptive panel regressions with year fixed effects and country-clustered standard errors.</p></div>
      {cadot_table(clean_records(models, list(models.columns)), [("variant", "Variant", "text"), ("outcome", "Outcome", "text"), ("coefficient", "GDP coefficient", "dec"), ("std_error", "Std. error", "dec"), ("p_value", "p-value", "dec"), ("bh_q_value", "BH q-value", "dec"), ("nobs", "Obs.", "int"), ("clusters", "Clusters", "int"), ("status", "Status", "text")])}
      <p class="small">The downloadable models CSV also includes the conditional GDP-per-capita and population robustness specifications.</p>
    </section>
    <section class="section">
      <div class="section-heading"><h2>Largest Removed Shares In {latest_year}</h2><p>Reporter-years with the highest broad-primary export share removed in the latest year.</p></div>
      {cadot_table(clean_records(latest_removed, list(latest_removed.columns)), [("country", "Country", "text"), ("year", "Year", "year"), ("broad_primary_share_removed", "Removed share", "pct"), ("delta_world_share_exposure", "Delta exposure", "dec"), ("delta_spearman_product_alignment", "Delta alignment", "dec")])}
    </section>
    <section class="section">
      <div class="section-heading"><h2>Validation</h2><p>The page reads only the validated Cadot exposure artifacts.</p></div>
      {cadot_table(clean_records(validation, list(validation.columns)), [("check", "Check", "text"), ("passed", "Passed", "text"), ("value", "Value", "text"), ("expected", "Expected", "text"), ("detail", "Detail", "text")])}
    </section>
    <section class="section">
      <div class="section-heading"><h2>Downloads</h2><p>All published files for the Cadot non-commodity exposure run.</p></div>
      {cadot_download_grid(1, [
          "world_large_product_exposure_spearman_summary.csv",
          "world_large_product_exposure_yearly_spearman.csv",
          "world_large_product_exposure_models.csv",
          "world_large_product_exposure_diagnostics.csv",
          "world_large_product_exposure_validation_checks.csv",
          "world_large_product_exposure_reporter_coverage.csv",
          "world_large_product_exposure_fixed_country_2018_2024.csv",
          "world_large_product_exposure_fixed_country_2018_2024_summary.csv",
          "world_large_product_exposure_leave_one_country_out.csv",
          "world_large_product_exposure_variant_comparison.csv",
          "world_large_product_exposure_country_commodity_shares.csv",
          "world_large_product_exposure_top_change_contributors.csv",
          "world_large_product_exposure_product_mapping.csv",
          "world_large_product_exposure_panel.csv",
          "world_large_product_exposure.md",
          "world_large_product_exposure_adversarial_review.md",
          "run_manifest_world_large_product_exposure.json",
      ])}
    </section>
    """
    return cadot_page("World-Product Exposure", "exposure", body, depth=1, page_key="cadot-exposure")


def cadot_theil_appendix_page(data: dict[str, Any]) -> str:
    cell = data["all_metrics"]
    cell = cell[cell["dimension"].astype(str).eq("product_partner_cell")].copy()
    summary = (
        cell.groupby(["flow", "year"], as_index=False)
        .agg(
            countries=("country", "nunique"),
            median_cell_theil=("theil", "median"),
            median_cell_gini=("gini", "median"),
            median_cell_hhi=("hhi", "median"),
            median_active_cells=("active_count", "median"),
        )
        .sort_values(["flow", "year"], ascending=[True, False])
    )
    body = f"""
    <section class="page-title">
      <div class="eyebrow">Theil appendix</div>
      <h1>Product-Destination / Cell Theil</h1>
      <p>This appendix is not the headline metric. It exists to keep the product-destination analogue visible while the headline Theil remains the fixed-universe product measure.</p>
      {cadot_metric_switch("theil", None, 1)}
    </section>
    <section class="section">
      <div class="section-heading"><h2>Cell Theil Through Time</h2><p>Median product-destination Theil for Cadot reporters.</p></div>
      <div class="chart-grid">
        {cadot_chart_panel("Cell Theil trend", "How does the product-destination analogue move through time?", "theil-appendix-chart")}
      </div>
    </section>
    <section class="section">
      <div class="section-heading"><h2>Recent Cell Summary</h2><p>Median cell concentration by flow and year.</p></div>
      {cadot_table(clean_records(summary.head(40), list(summary.columns)), [("flow", "Flow", "text"), ("year", "Year", "year"), ("countries", "Countries", "int"), ("median_cell_theil", "Median cell Theil", "dec"), ("median_cell_gini", "Median cell Gini", "dec"), ("median_cell_hhi", "Median cell HHI", "dec"), ("median_active_cells", "Median active cells", "int")])}
    </section>
    """
    return cadot_page("Theil Appendix", "theil", body, depth=1, page_key="cadot-theil-appendix", metric="theil")


def cadot_root_page(data: dict[str, Any]) -> str:
    manifest = data["manifest"]
    exercise_cards = []
    for spec in EXERCISE_PAGE_SPECS:
        links = " ".join(
            f'<a href="{cadot_metric_exercise_path(metric, spec["short"])}">{escape(cadot_metric_label(metric))}</a>'
            for metric in ["gini", "theil", "hhi"]
        )
        exercise_cards.append(
            f"""
      <article class="exercise-card">
        <span>Exercise {escape(spec['short'])}</span>
        <strong>{escape(spec['title'].split(':', 1)[-1].strip())}</strong>
        <small>{escape(spec['question'])}</small>
        <div class="inline-link-row">{links}</div>
      </article>
            """
        )
    body = f"""
    <section class="hero">
      <div class="eyebrow">Cadot 156 graph-rich three-site bundle</div>
      <h1>Trade Concentration Across Gini, Theil, and HHI</h1>
      <p>Three graph-rich metric sites built from the harmonized Cadot 156 rerun. Product-dependent outputs use LT/HGL-weighted HS1992/H0 product families; Theil uses the world_broad fixed universe by flow.</p>
      <div class="stat-grid">
        <article class="stat-card"><span>Reporters</span><strong>{int(manifest['selected_reporters']):,}</strong><small>Cadot-style broad sample</small></article>
        <article class="stat-card"><span>Raw files</span><strong>{int(manifest['raw_files_processed']):,}</strong><small>Final Comtrade files processed</small></article>
        <article class="stat-card"><span>Product universe</span><strong>{int(manifest['product_universe_counts']['Exports']):,}</strong><small>HS1992/H0 families per flow</small></article>
      </div>
      <div class="metric-switch">
        <a href="gini/">Open Gini</a>
        <a href="theil/">Open Theil</a>
        <a href="hhi/">Open HHI</a>
      </div>
    </section>
    <section class="section">
      <div class="section-heading"><h2>Cadot Overview</h2><p>The hub compares the three metrics directly; each metric site then carries its own exercise pages.</p></div>
      <div class="chart-grid">
        {cadot_chart_panel("Median concentration paths", "How do median product concentration paths compare across the three metrics and two flows?", "hub-trend-chart")}
        {cadot_chart_panel("Latest median comparison", "How do the latest export and import medians line up by metric?", "hub-latest-chart")}
      </div>
    </section>
    <section class="section">
      <div class="section-heading"><h2>Metric Sites</h2><p>Each site has its own metric-local overview and exercise pages.</p></div>
      <div class="link-grid three-up">
        <a class="metric-link-card" href="gini/"><span>Metric site</span><strong>Gini</strong><small>Active-positive product Gini with full exercise coverage.</small></a>
        <a class="metric-link-card" href="theil/"><span>Metric site</span><strong>Theil</strong><small>Fixed-universe product Theil plus a separate cell appendix.</small></a>
        <a class="metric-link-card" href="hhi/"><span>Metric site</span><strong>HHI</strong><small>Raw Herfindahl-Hirschman concentration with the same exercise coverage.</small></a>
        <a class="metric-link-card" href="exposure/"><span>Companion page</span><strong>World-Product Exposure</strong><small>Baseline versus broad-primary-excluded Cadot export exposure and alignment.</small></a>
      </div>
    </section>
    <section class="section">
      <div class="section-heading"><h2>Exercise Matrix</h2><p>Every exercise is reachable through all three metric routes.</p></div>
      <div class="link-grid">
        {"".join(exercise_cards)}
      </div>
    </section>
    """
    return cadot_page("Hub", "hub", body, depth=0, page_key="cadot-hub")


def cadot_validate_generated_site(output: Path, page_paths: list[str]) -> None:
    if not (output / "assets/site.js").exists() or (output / "assets/site.js").stat().st_size == 0:
        raise RuntimeError("Cadot build must publish a non-empty assets/site.js.")
    if not (output / "assets/vendor/plotly.min.js").exists():
        raise RuntimeError("Cadot build must publish Plotly when interactive charts are present.")
    missing_pages = [path for path in page_paths if not (output / path).exists()]
    if missing_pages:
        raise RuntimeError(f"Cadot site is missing required pages: {missing_pages}")
    figure_missing: list[str] = []
    missing_visuals: list[str] = []
    forbidden_refs: list[str] = []
    missing_question_contracts: list[str] = []
    for relative in page_paths:
        page = output / relative
        text = page.read_text(encoding="utf-8")
        if "extension.html" in text or "imports.html" in text or "rd2_" in text:
            forbidden_refs.append(relative)
        if relative.startswith(("gini/exercises/", "theil/exercises/", "hhi/exercises/")) and "index.html" not in relative:
            if ("js-plotly-plot" not in text) and ("<img " not in text):
                missing_visuals.append(relative)
            chart_ids = re.findall(r'id="([^"]+)" class="chart[^"]*js-plotly-plot', text)
            evidence_count = text.count("Question this answers")
            figure_count = text.count("<figure>")
            expected_evidence_count = len(chart_ids) + figure_count
            if evidence_count < expected_evidence_count:
                missing_question_contracts.append(
                    f"{relative}: {evidence_count} question boxes for "
                    f"{len(chart_ids)} interactive charts and {figure_count} static figures"
                )
        for match in re.findall(r'(?:src|href)="([^"]*assets/figures/[^"]+\\.png)"', text):
            if not (page.parent / match).resolve().exists():
                figure_missing.append(f"{relative}: {match}")
    if figure_missing:
        raise RuntimeError(f"Cadot site references missing figures: {figure_missing}")
    if missing_visuals:
        raise RuntimeError(f"Cadot exercise pages are missing chart/image content: {missing_visuals}")
    if forbidden_refs:
        raise RuntimeError(f"Cadot pages still reference stripped rd2 routes or assets: {forbidden_refs}")
    if missing_question_contracts:
        raise RuntimeError(
            "Cadot exercise pages are missing graph-question contracts: "
            f"{missing_question_contracts}"
        )
    exposure_text = (output / "exposure/index.html").read_text(encoding="utf-8")
    required_exposure_wording = [
        "Broad 156-reporter baseline, 2000-2024.",
        "There is no 2023-2024 reversal in the broad sample.",
        "These estimates support a descriptive size relationship; they do not identify a causal mechanism.",
    ]
    missing_exposure_wording = [
        text for text in required_exposure_wording if text not in exposure_text
    ]
    if missing_exposure_wording:
        raise RuntimeError(
            "Cadot exposure page is missing required current-sample wording: "
            f"{missing_exposure_wording}"
        )


def cadot_write_archived_extension_parity_report() -> None:
    rows = [
        ("World map", "restored", "Exercise 1 on Gini, Theil, and HHI routes; fixed metric/flow scale across years."),
        ("Country trajectories", "restored", "Exercise 1 with searchable multi-country selector."),
        ("Year slider", "restored", "Exercise 1 map and Exercise 3 non-energy map."),
        ("Energy-excluded map", "restored and generalized", "Exercise 3 non-energy import map for Gini, fixed-universe Theil, and HHI."),
        ("Energy-excluded country lines", "restored and generalized", "Exercise 3 non-energy country trajectories."),
        ("Rank-bucket overview", "restored", "Exercise 3 start/mid/end scrollable stacked bars."),
        ("Rank-bucket country focus", "restored", "Exercise 3 sticky focus chart, totals, and top ten HS1992 families."),
        ("Lumpy-product exclusion chart", "replaced", "Exercise 6 metric-specific exclusion trend and sensitivity ranking."),
        ("Benchmark chart", "replaced", "Exercise 10 metric-specific benchmark path and latest gaps."),
        ("Growth buckets", "replaced", "Exercise 2 metric-specific trade and active-product growth charts."),
        ("Structured hypothesis cards", "restored", "One full Question/Supports/Weakens/Current result card on every metric exercise page."),
        ("Chart evidence boxes", "restored", "Registry-backed question boxes for every interactive exercise chart and retained static Cadot figure."),
        ("Archived Exercise 2 regression table", "intentionally excluded", "Outside the requested graph-and-question restoration and not part of the harmonized three-metric artifact bundle."),
    ]
    lines = [
        "# Archived Extension Parity Report",
        "",
        "- Archived source: `tsawhneybuilds/trade-gini-map-old` commit `9852ae9`.",
        "- Current staging baseline: `tsawhneybuilds/trade-gini-map` commit `37ab6e1`.",
        "- Restored target: harmonized Cadot 156 metric routes only; no rd2 payload or figure reuse.",
        "",
        "| Archived component | Status | Cadot 156 implementation |",
        "|---|---|---|",
    ]
    lines.extend(f"| {component} | {status} | {detail} |" for component, status, detail in rows)
    lines.extend(
        [
            "",
            "All product-dependent restored views exclude source HS6 `999999` before approved BEC filtering and LT/HGL weighted conversion to HS1992/H0. Partner code `0` is excluded by the shared leaf extractor.",
            "",
        ]
    )
    path = cadot_download_path("archived_extension_parity_report.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_cadot_three_metric_site(output: Path) -> None:
    cadot_write_archived_extension_parity_report()
    manifest_rows = cadot_publication_manifest_rows()
    data = cadot_load_three_metric_site_data()
    prepare_output(output)
    (output / "assets/site.css").write_text(cadot_site_css(), encoding="utf-8")
    (output / "assets/site.js").write_text(cadot_site_js(), encoding="utf-8")
    (output / "assets/vendor/plotly.min.js").write_text(get_plotlyjs(), encoding="utf-8")
    cadot_write_json_assets(output, data)
    cadot_copy_three_metric_downloads(output)
    cadot_copy_figure_assets(output)

    page_paths = [
        "index.html",
        "exposure/index.html",
        "gini/index.html",
        "gini/exercises/index.html",
        "theil/index.html",
        "theil/appendix.html",
        "theil/exercises/index.html",
        "hhi/index.html",
        "hhi/exercises/index.html",
        "downloads/index.html",
        "exercises/index.html",
    ]
    cadot_write_site_file(output, "index.html", cadot_root_page(data))
    cadot_write_site_file(output, "exposure/index.html", cadot_exposure_page(data))
    cadot_write_site_file(output, "downloads/index.html", cadot_downloads_page(data))
    cadot_write_site_file(output, "exercises/index.html", cadot_exercises_index_page(data))
    for metric in ["gini", "theil", "hhi"]:
        cadot_write_site_file(output, f"{metric}/index.html", cadot_metric_page(metric, data))
        cadot_write_site_file(output, f"{metric}/exercises/index.html", cadot_metric_exercises_index_page(metric))
        for spec in EXERCISE_PAGE_SPECS:
            relative = f"{metric}/exercises/exercise-{spec['short']}.html"
            page_paths.append(relative)
            cadot_write_site_file(output, relative, cadot_metric_exercise_page(metric, spec, data))
    cadot_write_site_file(output, "theil/appendix.html", cadot_theil_appendix_page(data))

    site_manifest = {
        "created_at_utc": now_utc(),
        "generator": "scripts/build_trade_gini_site.py",
        "country_sample": ACTIVE_SITE_SAMPLE,
        "site_mode": "cadot_three_metric_graph_rich_harmonized_hs1992",
        "source_artifacts": manifest_rows,
        "figure_assets": [f"assets/figures/{key}.png" for key in cadot_figure_keys()],
        "pages": sorted(page_paths),
        "downloads": sorted(three_metric_download_paths(ACTIVE_SITE_SAMPLE)),
    }
    (output / "assets/site-manifest.json").write_text(
        json.dumps(site_manifest, ensure_ascii=True, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "README.md").write_text(
        "# Cadot 156 Trade Concentration Site\n\n"
        "Generated by `scripts/build_trade_gini_site.py` from harmonized Cadot three-metric artifacts.\n",
        encoding="utf-8",
    )
    cadot_validate_generated_site(output, page_paths)


def write_site(output: Path, country_sample: str = "cadot_broad_156") -> None:
    configure_site_sample(country_sample)
    if country_sample == "cadot_broad_156":
        write_cadot_three_metric_site(output)
        return
    manifest_rows = validate_publication_inputs()
    data, context = build_data()
    row_counts = {
        str(row["name"]): int(row["row_count"])
        for row in manifest_rows
        if row.get("row_count") is not None
    }
    data["metadata"]["country_count"] = int(len(data["countries"]))
    data["metadata"]["source_artifact_count"] = int(len(manifest_rows))
    data["metadata"]["row_counts"] = row_counts
    pages = render_pages(context)
    prepare_output(output)
    for filename, html in pages.items():
        (output / filename).write_text(html, encoding="utf-8")
    (output / "assets/site.css").write_text(site_css(), encoding="utf-8")
    (output / "assets/site.js").write_text(site_js(), encoding="utf-8")
    (output / "assets/vendor/plotly.min.js").write_text(get_plotlyjs(), encoding="utf-8")
    write_json_assets(output, data)
    copy_assets(output)
    site_manifest = {
        "created_at_utc": now_utc(),
        "generator": "scripts/build_trade_gini_site.py",
        "country_sample": ACTIVE_SITE_SAMPLE,
        "country_count": int(len(data["countries"])),
        "countries": data["countries"],
        "product_excluded_hs6_codes": sorted(EXCLUDED_HS6_CODES),
        "partner_concentration_includes_hs6_codes": sorted(EXCLUDED_HS6_CODES),
        "source_artifacts": manifest_rows,
        "row_counts": row_counts,
        "pages": sorted(pages),
        "downloads": sorted(site_download_sources()),
    }
    if data.get("exercise12EvHs6HarmonizedExpansion") or data.get("exercise12EvHs4Expansion"):
        ev_data = data.get("exercise12EvHs6HarmonizedExpansion") or data["exercise12EvHs4Expansion"]
        ev_validation = ev_data.get("validation", {})
        site_manifest["exercise_12_headline"] = {
            "method": "EV-style LT/HGL weighted HS6-to-HS1992 persistent expansion decomposition"
            if data.get("exercise12EvHs6HarmonizedExpansion")
            else "EV-style HS4 persistent expansion decomposition",
            "product_level": ev_validation.get("product_level"),
            "product_level_label": ev_validation.get("product_level_label"),
            "persistence_rule": "adjacent 2+2 base/future windows",
            "active_threshold_usd_2024": ev_validation.get("active_threshold_usd_2024"),
            "constant_usd_year": ev_validation.get("constant_usd_year"),
            "headline_share": "pooled positive expansion share",
            "bottom_10pct_robustness": True,
            "hs4_robustness_available": bool(data.get("exercise12EvHs4Expansion")),
        }
    (output / "assets/site-manifest.json").write_text(
        json.dumps(site_manifest, ensure_ascii=True, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "README.md").write_text(
        "# Trade Concentration Research Brief\n\n"
        f"Generated by `scripts/build_trade_gini_site.py` from `{ACTIVE_SITE_SAMPLE}` result artifacts.\n",
        encoding="utf-8",
    )
    validate_site_root(output, pages)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output directory for the static site.")
    parser.add_argument("--country-sample", choices=SITE_COUNTRY_SAMPLE_CHOICES, default="cadot_broad_156")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    write_site(args.output, country_sample=args.country_sample)
    print(f"Wrote static site to {args.output}")


if __name__ == "__main__":
    main()
