# Adversarial Econometrics Review: Import Size Mechanism Tests

Generated: 2026-06-02T13:36:30+00:00

## Executive Verdict

Mostly trustworthy for the current descriptive purpose, with caveats.

- The pipeline reproduces the prior World-Relative Import Product Gini population coefficient exactly up to floating point tolerance: new beta `-0.0340801206884217` versus prior beta `-0.0340801206884214`.
- The final main panel is the intended balanced `rd2_countries` sample: 1,375 country-years, 55 countries, 25 years, zero duplicate reporter-year keys.
- Product-level inputs hard-check the repo rule excluding HS6 `999999`; diagnostics report zero `999999` product rows.
- The main regression specification matches the intended descriptive design: year FE, `log_population`, GDP-per-capita control, country-clustered standard errors.
- Remaining caveats are interpretive, not fatal: active-count controls are mechanism/accounting controls, not causal controls; the top-driver test uses the saved top 15 leave-one-out drivers per country-year, not all product-level leave-one-out contributions; tariff coverage is incomplete.
- This was a local adversarial review, not a fresh independent subagent review, because the currently exposed subagent tool requires an explicit user request to spawn agents in this turn.

## Highest-Risk Findings

1. Severity: medium. Active-count controls are post-treatment mechanism controls.
   What happened: `wr_plus_standard_active_count` and `wr_plus_harmonized_active_count` add active import product counts to a concentration regression.
   Why it matters: active product count is partly constitutive of concentration. The coefficient shrinkage is useful for accounting, but it should not be interpreted as causal adjustment.
   How to verify: compare baseline beta `-0.0341` with active-count models `-0.0208` and `-0.0220`.
   Fix or diagnostic: report explicitly as a decomposition/mechanism check. The memo does this.

2. Severity: medium. Common-zero Gini is on a different outcome scale from World-Relative Gini.
   What happened: the common-universe zero-inclusive outcome has beta `-0.0028`, much smaller in level than the World-Relative beta.
   Why it matters: coefficient-size shrinkage cannot be compared directly across these two outcomes.
   How to verify: `absolute_shrink_vs_wr_baseline_pct` is now blank for common-zero and bin outcomes.
   Fix or diagnostic: keep common-zero as a separate robustness outcome; do not call it a 92% shrinkage result.

3. Severity: medium-low. Top-driver test is not a full leave-one-out product decomposition.
   What happened: the top-driver control uses `world_relative_import_product_contribution_top_drivers.csv`, which has 15 rows per country-year.
   Why it matters: a lumpy category outside the top 15 positive drivers would not enter this control.
   How to verify: mechanism panel reports `top_driver_count = 15` for all 1,375 rows.
   Fix or diagnostic: label it as a top-driver diagnostic, not a full LOO decomposition. A full all-product LOO recomputation would be the stronger but heavier test.

4. Severity: low. Tariff model has incomplete coverage.
   What happened: tariff model uses 1,148 observations instead of 1,375 because 227 rows have missing weighted applied tariffs.
   Why it matters: the tariff coefficient and population coefficient in that model are not on the full balanced sample.
   How to verify: missingness audit shows 227 missing `tariff_applied_weighted_mean_pct` values.
   Fix or diagnostic: keep tariff as secondary; openness and PPP controls retain full coverage.

## Data Lineage and Sample Audit

- World-relative outcome source: `results/samples/rd2_countries/world_relative_import_product_gini_tables/world_relative_import_product_gini_all_years.csv`.
- Product-cell source: `data/processed/samples/rd2_countries/world_relative_import_product_gini_harmonized_hs6_family_rd2_product_imports.parquet`.
- World benchmark source for lumpy exclusion: `data/processed/samples/world_broad/world_relative_import_product_gini_harmonized_hs6_family_world_product_imports.parquet`.
- Country-size controls: `data/processed/samples/rd2_countries/country_size_effect_panel.parquet`.
- Openness, PPP GDP per capita, and tariff controls: `results/samples/rd2_countries/import_concentration_explanatory_regressions/analysis_panel.csv`.
- Import-bin source: `data/processed/samples/rd2_countries/exercise_03_import_bin_concentration.parquet`.
- Top-driver source: `results/samples/rd2_countries/world_relative_import_product_gini_contributions/world_relative_import_product_contribution_top_drivers.csv`.

Final panel diagnostics:

- Rows: 1,375.
- Countries: 55.
- Years: 2000-2024, 25 years.
- Cluster sizes: every country has 25 rows.
- Duplicate reporter-year keys: 0.
- Product-cell rows in balanced sample: 5,707,739.
- Harmonized product IDs: 8,039.
- Duplicate reporter-year-product keys: 0.
- `999999` product rows: 0.

## Merge/Join Audit

- The world-relative panel is the master key set. It hard-stops unless it is exactly 1,375 rows with 55 balanced countries.
- Country-size controls merge by `reporter_code, year` with `validate="one_to_one"` after duplicate-key checks.
- Explanatory controls merge by `reporter_code, year` with `validate="one_to_one"` after duplicate-key checks.
- Product cells are restricted to the balanced master keys using `validate="many_to_one"` and then checked for duplicate `reporter_code, year, product_id`.
- Import-bin rows are restricted to balanced keys and merge controls with `validate="many_to_one"`.
- Top-driver rows are restricted to balanced keys and summarized to one row per country-year, then merged with `validate="one_to_one"`.

No silent many-to-many merge was found.

## Variable Construction Audit

- `log_population`, `log_gdp_per_capita`: inherited from the prior country-size panel.
- `log_gdp_pc_ppp_constant_2021_intl_usd`: inherited from the import explanatory panel.
- `log_standard_active_import_products`: log of standard active HS6 product count from the world-relative table.
- `log_harmonized_active_import_products`: log of harmonized product-family count used in the world-relative construction.
- Common-zero Gini: Gini over a fixed 8,039 harmonized product universe, treating inactive product families as zeros.
- Lumpy categories:
  - aircraft: HS4 8802/8803.
  - gold/precious: HS2 71.
  - pharma: HS2 30.
  - vehicles: HS2 87.
  - food staples: HS2 10/11/15/17.
  - energy sensitivity: HS2 27.
- Lumpy-excluded World-Relative Gini: recomputed after removing lumpy categories from both the country basket and world benchmark basket.
- Top-driver lumpy share: share of positive leave-one-out contribution among the saved top 15 drivers that falls into lumpy categories.

Potential issue checked and fixed: the reporting no longer compares coefficient shrinkage across different outcome scales.

## Specification Audit

Main equation:

`concentration_ct = beta log_population_ct + gamma log_gdp_per_capita_ct + year_FE_t + error_ct`

Inference:

- OLS via the project’s `run_country_size_effect.run_ols_model`.
- Year fixed effects in all main mechanism regressions.
- Country-clustered standard errors by `reporter_code`.
- 55 clusters in full-sample models; 50 clusters after dropping HKG, SGP, LUX, ISL, GUY; 54 clusters in tariff model.

The baseline World-Relative Import Product Gini regression matches the previously saved robustness table exactly, which is a strong reproducibility check.

## Inference and Identification Audit

- Cluster count is adequate for conventional country-clustered inference in the full sample.
- Serial correlation is not directly modeled beyond country clustering; this is acceptable for the descriptive year-FE panel but should be stated.
- The result remains cross-country/development-stage descriptive evidence, not causal evidence that population size causes diversification.
- A country-FE version would answer a different within-country question and is not the main estimand here.
- Multiple testing is reported with BH q-values in the model CSV, but the memo emphasizes raw p-values. That is acceptable if the text does not claim multiple-testing survival unless q < 0.05.

## Replication Checklist

Run:

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 /opt/anaconda3/bin/python scripts/run_import_size_mechanism_tests.py --country-sample rd2_countries
```

Then verify:

- `results/samples/rd2_countries/import_size_mechanism_tests/import_size_mechanism_diagnostics.csv`.
- `results/samples/rd2_countries/import_size_mechanism_tests/import_size_mechanism_key_coefficients.csv`.
- Baseline beta equals the prior `world_relative_import_exercise_robustness_key_coefficients.csv` beta for `country_size_year_fe`, `world_relative_import_product_gini`, `log_population`.
- `import_size_mechanism_panel.csv` has 1,375 rows and no duplicate `reporter_code, year` keys.
- All full-sample non-tariff models have 1,375 observations.

## Minimal Patch Plan

No required patch remains before using the result descriptively.

Recommended future additions:

- Add a country-FE appendix table to separate across-country development-stage variation from within-country changes.
- Add a full all-product leave-one-out lumpy decomposition if the top-driver diagnostic becomes central to the paper.
- Add a year-specific common-universe sensitivity if the fixed 2000-2024 product universe is seen as too demanding.

## Questions for the Researcher

- Should the main text focus on World-Relative Import Product Gini, or should common-zero Gini be presented as an appendix robustness because its scale is less intuitive?
- Do you want the mechanism story framed as “variety breadth explains part of the size gradient” rather than “population causes lower concentration”?
