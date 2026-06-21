# Do Large Economies Export Globally Large Products?

Generated: 2026-06-15T14:02:53+00:00

## Purpose

This diagnostic tests whether larger economies allocate more export share to products that are large in the inclusive world export basket.

## Measures

- `world_share_exposure`: sum of country product export shares times the inclusive world product-share rank percentile.
- `spearman_product_alignment`: within-country-year Spearman correlation between country product export shares and inclusive world product export shares.
- Top-world-product shares: country export share in products in the top 1%, 5%, 10%, and 20% of the world product-share distribution.
- HS6 `999999` is excluded before product aggregation through the upstream product-export builders.

## Bottom Line

- Headline year-by-year GDP rank correlation: mean Spearman 0.309, median 0.364, positive in 0.920 of years.
- Main year-FE GDP coefficient on world-share exposure: beta=0.0086, SE=0.0030, p=0.0058, N=1482.
- GDP is the headline size variable. Population appears only as a labeled robustness check.
- The conditional GDP plus GDP-per-capita model is not the simple total-GDP relationship; because log GDP equals log population plus log GDP per capita, it isolates scale conditional on development.

## Headline Rank-Correlation Summary

| outcome                    | outcome_label                         | size_variable       | size_label       |   years |   mean_spearman |   median_spearman |   min_spearman |   max_spearman |   share_positive |
|:---------------------------|:--------------------------------------|:--------------------|:-----------------|--------:|----------------:|------------------:|---------------:|---------------:|-----------------:|
| spearman_product_alignment | Within-country product-rank alignment | log_gdp_current_usd | GDP, current USD |      25 |        0.77711  |          0.772826 |       0.72648  |       0.83571  |             1    |
| world_share_exposure       | World-share percentile exposure       | log_gdp_current_usd | GDP, current USD |      25 |        0.309288 |          0.364115 |      -0.037928 |       0.451607 |             0.92 |

## Main Regression Rows

| model_label                   | term                |   coefficient |   std_error |    p_value |   bh_q_value |   nobs |   clusters |   r_squared | status   |
|:------------------------------|:--------------------|--------------:|------------:|-----------:|-------------:|-------:|-----------:|------------:|:---------|
| main_gdp_year_fe              | log_gdp_current_usd |    0.00858379 |  0.00300137 | 0.00584994 |     0.015343 |   1482 |         60 |   0.178267  | ok       |
| conditional_gdp_gdppc_year_fe | log_gdp_current_usd |    0.00389218 |  0.00275555 | 0.16306    |     0.286118 |   1482 |         60 |   0.229813  | ok       |
| conditional_gdp_gdppc_year_fe | log_gdp_per_capita  |    0.010025   |  0.00485347 | 0.043274   |     0.167169 |   1482 |         60 |   0.229813  | ok       |
| population_robustness_year_fe | log_population      |    0.00217908 |  0.00252159 | 0.390994   |     0.416922 |   1482 |         60 |   0.0660671 | ok       |

## Diagnostics

| diagnostic                             |        value | detail                                                      |
|:---------------------------------------|-------------:|:------------------------------------------------------------|
| country_year_rows                      | 1482         |                                                             |
| countries                              |   60         |                                                             |
| year_min                               | 2000         |                                                             |
| year_max                               | 2024         |                                                             |
| invalid_metric_rows                    |    0         |                                                             |
| max_missing_world_product_export_share |    0         |                                                             |
| product_999999_policy                  |    0         | excluded upstream before product aggregation                |
| world_basket_policy                    |    1         | inclusive world_broad exports; no leave-one-out subtraction |
| gdp_alignment_scatter_year             | 2024         |                                                             |
| gdp_alignment_scatter_countries        |   56         |                                                             |
| gdp_alignment_scatter_slope            |    0.0645525 | OLS slope in latest-year scatter                            |
| gdp_alignment_scatter_r_squared        |    0.564988  | OLS R-squared in latest-year scatter                        |

## Outputs

- processed_panel: `data/processed/samples/rd2_countries/world_large_product_exposure_panel.parquet`
- panel_csv: `results/samples/rd2_countries/world_large_product_exposure_tables/world_large_product_exposure_panel.csv`
- yearly_spearman: `results/samples/rd2_countries/world_large_product_exposure_tables/world_large_product_exposure_yearly_spearman.csv`
- spearman_summary: `results/samples/rd2_countries/world_large_product_exposure_tables/world_large_product_exposure_spearman_summary.csv`
- models: `results/samples/rd2_countries/world_large_product_exposure_tables/world_large_product_exposure_models.csv`
- diagnostics: `results/samples/rd2_countries/world_large_product_exposure_tables/world_large_product_exposure_diagnostics.csv`
- manifest: `results/samples/rd2_countries/world_large_product_exposure_tables/run_manifest_world_large_product_exposure.json`
- memo: `results/samples/rd2_countries/world_large_product_exposure_tables/world_large_product_exposure.md`
- gdp_product_alignment_scatter: `results/samples/rd2_countries/country_size_effect_figures/gdp_product_alignment_scatter.png`

## Manifest

```json
{
  "benchmark_sample": "world_broad",
  "controls": {
    "control_source": "World Bank GDP current USD and population",
    "controls_cache": "data/processed/samples/rd2_countries/world_large_product_exposure_world_bank_controls.csv",
    "log_gdp_per_capita_formula": "log_gdp_current_usd - log_population"
  },
  "country_sample": "rd2_countries",
  "created_at_utc": "2026-06-15T14:02:53+00:00",
  "end_year": 2024,
  "flow": "Exports",
  "leave_one_out": false,
  "outputs": {
    "diagnostics": "results/samples/rd2_countries/world_large_product_exposure_tables/world_large_product_exposure_diagnostics.csv",
    "gdp_product_alignment_scatter": "results/samples/rd2_countries/country_size_effect_figures/gdp_product_alignment_scatter.png",
    "memo": "results/samples/rd2_countries/world_large_product_exposure_tables/world_large_product_exposure.md",
    "models": "results/samples/rd2_countries/world_large_product_exposure_tables/world_large_product_exposure_models.csv",
    "panel_csv": "results/samples/rd2_countries/world_large_product_exposure_tables/world_large_product_exposure_panel.csv",
    "processed_panel": "data/processed/samples/rd2_countries/world_large_product_exposure_panel.parquet",
    "spearman_summary": "results/samples/rd2_countries/world_large_product_exposure_tables/world_large_product_exposure_spearman_summary.csv",
    "yearly_spearman": "results/samples/rd2_countries/world_large_product_exposure_tables/world_large_product_exposure_yearly_spearman.csv"
  },
  "product_id_mode": "harmonized_hs6_family",
  "product_inputs": {
    "country_product": "data/processed/samples/rd2_countries/world_relative_product_gini_harmonized_hs6_family_rd2_product_exports.parquet",
    "source": "existing_product_inputs",
    "world_product": "data/processed/samples/world_broad/world_relative_product_gini_harmonized_hs6_family_world_product_exports.parquet"
  },
  "size_variable_headline": "log_gdp_current_usd",
  "start_year": 2000,
  "world_basket": "inclusive_world_exports"
}
```
