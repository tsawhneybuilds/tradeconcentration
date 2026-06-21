# Adversarial Review: World-Large Product Exposure

## Executive verdict

Mostly trustworthy for the current descriptive purpose.

- The implemented design matches the revised question: the headline test is GDP rank versus `world_share_exposure`, not the within-country product-alignment diagnostic.
- The pipeline uses `rd2_countries`, inclusive `world_broad` product shares, and no leave-one-out subtraction.
- HS6 `999999` is excluded upstream before product aggregation; both country and world product inputs contain no `999999`-derived product IDs.
- The final panel has no duplicate country-year-flow keys, no invalid exposure rows, and no missing GDP or population controls.
- Caveat: the regressions are descriptive associations with year fixed effects, not causal estimates.

## Highest-risk findings

- Severity: Medium. The main regression is descriptive, not identified causally. Why it matters: the coefficient on log GDP can reflect scale, development, product scope, institutional capacity, and reporting composition. Verification: the script labels the model as `main_gdp_year_fe` and uses only year fixed effects. Fix: keep causal language out of the memo and paper text.
- Severity: Low after fix. Initial top-product cutoffs used a percentile boundary that could include one extra product when the cutoff was exact. Why it matters: top 1%, 5%, 10%, and 20% shares could be slightly overstated. Verification: a new unit test with 100 products now checks exact descending-rank counts. Fix applied: top sets are now `rank_desc <= ceil(cutoff * N)`.
- Severity: Low. World Bank online refresh timed out on the long run, then the script used the existing local controls cache. Why it matters: if the cache is stale, GDP values may lag the latest World Bank revision. Verification: final panel has zero missing GDP/population rows. Fix if needed: rerun with `--refresh-controls` when the API is responsive.

## Data lineage and sample audit

- Raw trade data: Comtrade bulk files under `data/raw/comtrade/bulk`.
- Country product input: `data/processed/samples/rd2_countries/world_relative_product_gini_harmonized_hs6_family_rd2_product_exports.parquet`.
- World product input: `data/processed/samples/world_broad/world_relative_product_gini_harmonized_hs6_family_world_product_exports.parquet`.
- Final panel: `data/processed/samples/rd2_countries/world_large_product_exposure_panel.parquet`.
- Unit of observation: country-year-flow, with `flow == Exports`.
- Country product input rows: 5,278,636; duplicate `reporter_code-year-product_id` keys: 0; countries: 60; years: 2000-2024.
- World product input rows: 125,201; duplicate `year-product_id` keys: 0; years: 2000-2024; mean products per year: 5,008.04.
- Final panel rows: 1,482; countries: 60; years: 2000-2024; duplicate `reporter_code-year-flow` keys: 0.
- Rows per year: minimum 56, maximum 60. Cluster size by reporter: minimum 15, maximum 25.

## Merge/join audit

- Country metadata join uses `reporter_code`; country-panel duplicates are rejected.
- Product exposure joins country product rows to world product rows on `year-product_id`; missing world-basket country export share is computed and invalid rows are rejected.
- Observed maximum missing world product export share in the final panel: 0.0.
- World Bank controls join on `iso3-year`; rows with missing GDP/current USD, population, log GDP, or log GDP per capita are rejected.
- Observed rows with any missing GDP/population control: 0.

## Variable construction audit

- `s_cpt = country product exports / country total exports`.
- `w_pt = world product exports / world total exports`, using inclusive `world_broad` exports.
- `world_share_rank_percentile` ranks `w_pt` within year, with larger world products assigned higher percentiles.
- `world_share_exposure_ct = sum_p s_cpt * rank_percentile(w_pt)`.
- `spearman_product_alignment_ct` is a within-country-year Spearman correlation between `s_cpt` and `w_pt`; it is a diagnostic, not the headline size test.
- Top-world-product shares use exact descending rank counts: top `ceil(cutoff * N)` products by `w_pt` within year.
- Final-panel range checks: `world_share_exposure` is within `[0, 1]`; top-share cutoffs are monotone; HS6 `999999` is absent.

## Specification audit

- Main descriptive rank test: within each year, Spearman correlation between `log_gdp_current_usd` and `world_share_exposure`.
- Main regression: `world_share_exposure_ct = beta log_gdp_current_usd_ct + year FE + error_ct`.
- Conditional robustness: `world_share_exposure_ct = beta log_gdp_current_usd_ct + gamma log_gdp_per_capita_ct + year FE + error_ct`.
- Population robustness: `world_share_exposure_ct = beta log_population_ct + year FE + error_ct`.
- GDP is the headline size variable; population appears only as robustness.

## Inference and identification audit

- Standard errors are clustered by `reporter_code`; observed clusters: 60.
- Year fixed effects absorb global time shocks to world product ranks and trade measurement.
- Because `log GDP = log population + log GDP per capita`, the conditional GDP-plus-GDP-per-capita model estimates scale holding development fixed; it is not the total GDP-size relationship.
- Results should be reported as descriptive correlations and associations, not causal effects.

## Replication checklist

- `python -m py_compile scripts/run_world_large_product_exposure.py`
- `python -m pytest tests/test_world_large_product_exposure.py tests/test_country_size_effect.py tests/test_world_relative_product_gini.py -q`
- `python scripts/run_world_large_product_exposure.py --workers 4`
- Inspect `results/samples/rd2_countries/world_large_product_exposure_tables/world_large_product_exposure_diagnostics.csv`.
- Confirm `max_missing_world_product_export_share == 0` and `invalid_metric_rows == 0`.

## Minimal patch plan

- No required patch remains before using the output for descriptive reporting.
- Optional robustness: rerun controls with `--refresh-controls` when the World Bank API is responsive.
- Optional reporting patch: add a LaTeX/table renderer that bolds raw p-values below 0.05 and keeps raw p-values distinct from BH q-values.

## Questions for the researcher

- Should the paper report top-product cutoffs by product count, as implemented, or by cumulative world export share?
- Should GDP current USD remain the sole headline size measure, with constant-USD GDP added only as a robustness table if the data are available?
