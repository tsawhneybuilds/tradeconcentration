# Lifecycle Regressions Adversarial Review

## Executive Verdict

Mostly trustworthy for the current descriptive purpose.

- Review type: local adversarial review, not an independent fresh-agent pass.
- The outputs use `rd2_countries` only and contain no duplicate model IDs, model-term rows, or manifest rows.
- Macro panel keys are unique at `iso3-year`; policy panel keys are unique at `scenario-iso3-year`.
- All 24 registered specifications estimated with status `ok`.
- Policy cumulative-pre variables were checked against grouped cumulative sums shifted by one year; mismatches were zero.
- The results remain descriptive lifecycle associations, not causal estimates.

## Highest-Risk Findings

1. Confirmed issue fixed during review: oil-export share was initially all zero because the upstream PPP common panel was absent. I created `ppp_hump_common_sample_panel.csv` from the existing harmonized HS6 export product panel, defining oil exports as HS chapter 27 exports divided by total exports. After rerunning, oil-share variation is present and all level models estimate without absorbed oil controls.
2. Remaining caveat: the product concentration CSV was reconstructed from the existing full `concentration_all_years.csv`, not rebuilt from raw Comtrade. This is defensible because the full table already contains the product concentration columns used by the lifecycle macro builder, but the provenance should be noted.
3. Remaining caveat: World Bank tariff coverage is sparse. The tariff lifecycle model has fewer observations and years than the main macro models, as recorded in the manifest.

## Data Lineage And Sample Audit

- Macro outcome: `results/samples/rd2_countries/exercise_03_tables/import_bin_decomposition.csv`, energy-bin exclusion outcome `product_gini_without_bin`.
- Macro export controls: `results/samples/rd2_countries/exercise_01_tables/product_concentration_all_years.csv`, reconstructed from `concentration_all_years.csv`.
- WDI controls: cached under `data/processed/samples/rd2_countries/` and `results/samples/rd2_countries/import_concentration_explanatory_regressions/wdi_controls_2000_2024.csv`.
- Oil-share controls: `results/samples/rd2_countries/ppp_hump_regression_tables/ppp_hump_common_sample_panel.csv`, generated from HS27 exports in `world_relative_product_gini_harmonized_hs6_family_rd2_product_exports.parquet`.
- Industrial-policy source: `data/raw/industrial_policy_jlop_2025/JLOP_2025.dta`.
- Output sample: `rd2_countries` only.

Diagnostics after rerun:

- Macro panel: 1,400 rows, 56 countries, 2000-2024, duplicate `iso3-year` keys = 0.
- Policy panel: 1,456 rows across scenarios, duplicate `scenario-iso3-year` keys = 0.
- Lifecycle summaries: 24 models, status `ok` for all 24.
- Minimum model support: 53 countries and 12 years.

## Merge And Variable Audit

- Macro merges use one-to-one `iso3-year` validation for outcome, exports, WDI controls, and oil shares.
- Policy merges use many-to-one `iso3-year` controls and outcome merges after scenario-country-year policy aggregation.
- `cum_import_substitution_ip_measures_pre` and `cum_export_promotion_ip_measures_pre` equal cumulative exposure through `t-1`, not contemporaneous cumulative exposure.
- Lagged policy count models use `log1p_*_l1`.

## Specification Audit

- Macro level models estimate `ex_energy_import_product_gini_it` on export/income/openness controls with country and year fixed effects.
- Macro change models estimate annual changes in the outcome on annual changes or lagged annual changes in macro controls with year fixed effects.
- Policy lifecycle models estimate the outcome on lagged flow or cumulative-pre industrial-policy exposure with controls, country fixed effects, and year fixed effects.
- Default inference is country-clustered. Two-way country-year clustered robustness models are also reported.

## Inference And Identification Audit

- Cluster counts range from 53 to 56 countries.
- Two-way robustness uses the existing OLS helper's two-way clustered covariance path.
- These regressions rely on within-country over-time variation and first differences; they do not isolate quasi-random shocks.
- Serial correlation and dynamic feedback remain plausible threats, especially in level fixed-effects specifications.

## Replication Checklist

Commands run:

```bash
python3 -m unittest tests.test_lifecycle_regressions tests.test_country_size_effect
python3 scripts/run_lifecycle_regressions.py
```

Core output files:

- `lifecycle_regression_terms.csv`
- `lifecycle_model_summary.csv`
- `lifecycle_sample_manifest.csv`
- `cross_section_to_lifecycle_crosswalk.csv`
- `lifecycle_regressions.md`

## Minimal Patch Plan

No blocking patch remains for the current descriptive lifecycle outputs. A future cleanup could move the product CSV and oil-share reconstruction steps into explicit reusable upstream scripts so the lineage is less ad hoc.
