# Lifecycle Regressions For Cross-Sectional Findings

This pass changes the comparison from cross-country differences to within-country movement over time.
The estimates are descriptive associations, not causal effects.

## Design

- Sample: rd2_countries only.
- Outcome: ex-energy import Product Gini.
- Inference: country-clustered standard errors.
- Level models use country and year fixed effects.
- Change models use annual differences with year fixed effects.
- Industrial-policy exposure uses either t-1 counts or cumulative exposure through t-1.

## Model Coverage

- Lifecycle specifications registered: 24.
- Specifications estimated with status ok: 24.
- Cross-sectional families mapped: 9.

## How To Read These Regressions

A positive lifecycle coefficient means that, within the same country's observed path, years with higher values of the regressor tend to coincide with higher import concentration. A negative coefficient means those higher-regressor years tend to coincide with lower import concentration. Because these are not quasi-experimental shocks, the estimates should be read as descriptive movement over the country lifecycle.

## First 40 Reported Terms

| model_id                          | term                                                   | coefficient     |   std_error | p_value         |
|:----------------------------------|:-------------------------------------------------------|:----------------|------------:|:----------------|
| macro_level_goods_exports         | log_goods_exports_current_usd                          | 0.000333564     | 0.00439998  | 0.939845        |
| macro_level_goods_exports         | log_gdp_pc_ppp_constant_2021_intl_usd                  | -0.010068       | 0.0117924   | 0.396935        |
| macro_level_goods_exports         | trade_openness_pct_gdp                                 | **0.000211178** | 8.62252e-05 | **0.0175337**   |
| macro_level_goods_exports         | log_population                                         | -0.0188647      | 0.0134239   | 0.165556        |
| macro_level_goods_exports         | oil_export_share                                       | -0.00677848     | 0.0129244   | 0.602059        |
| macro_level_real_exports          | log_real_exports_goods_services_constant_2015_usd      | -0.00205895     | 0.00668774  | 0.759366        |
| macro_level_real_exports          | log_gdp_pc_ppp_constant_2021_intl_usd                  | -0.0174812      | 0.0155357   | 0.265467        |
| macro_level_real_exports          | trade_openness_pct_gdp                                 | **0.000274112** | 9.83099e-05 | **0.00730248**  |
| macro_level_real_exports          | log_population                                         | -0.0121787      | 0.0123891   | 0.329983        |
| macro_level_real_exports          | oil_export_share                                       | -0.0253039      | 0.0144803   | 0.0862404       |
| macro_level_wdi_openness          | log_goods_exports_current_usd                          | 0.00592299      | 0.00418837  | 0.162954        |
| macro_level_wdi_openness          | log_gdp_pc_ppp_constant_2021_intl_usd                  | -0.0194438      | 0.0128298   | 0.135369        |
| macro_level_wdi_openness          | wdi_goods_services_trade_openness_pct_gdp              | 0.000146034     | 7.73977e-05 | 0.0644698       |
| macro_level_wdi_openness          | log_population                                         | -0.0236112      | 0.0149161   | 0.119171        |
| macro_level_wdi_openness          | oil_export_share                                       | -0.0220766      | 0.0123582   | 0.0795477       |
| macro_level_tariff                | log_goods_exports_current_usd                          | 0.00154906      | 0.0045266   | 0.733519        |
| macro_level_tariff                | log_gdp_pc_ppp_constant_2021_intl_usd                  | -0.00530208     | 0.0131806   | 0.689078        |
| macro_level_tariff                | trade_openness_pct_gdp                                 | **0.000198833** | 7.59184e-05 | **0.0114217**   |
| macro_level_tariff                | tariff_applied_weighted_mean_pct                       | **0.000740488** | 0.00034808  | **0.0379744**   |
| macro_level_tariff                | log_population                                         | -0.0132464      | 0.0145192   | 0.365647        |
| macro_level_tariff                | oil_export_share                                       | -0.0153304      | 0.0111048   | 0.173117        |
| macro_change_goods_exports        | d_log_goods_exports_current_usd                        | -0.000661499    | 0.00332995  | 0.843268        |
| macro_change_goods_exports        | d_log_gdp_pc_ppp_constant_2021_intl_usd                | **-0.0230763**  | 0.0101393   | **0.0267667**   |
| macro_change_goods_exports        | d_trade_openness_pct_gdp                               | **0.000267539** | 6.3613e-05  | **9.66552e-05** |
| macro_change_real_exports         | d_log_real_exports_goods_services_constant_2015_usd    | 0.00153028      | 0.00414382  | 0.71341         |
| macro_change_real_exports         | d_log_gdp_pc_ppp_constant_2021_intl_usd                | -0.0232654      | 0.0120221   | 0.0584104       |
| macro_change_real_exports         | d_trade_openness_pct_gdp                               | **0.00035461**  | 6.54028e-05 | **1.54864e-06** |
| macro_change_wdi_openness         | d_log_goods_exports_current_usd                        | **0.0100625**   | 0.00272049  | **0.000501754** |
| macro_change_wdi_openness         | d_log_gdp_pc_ppp_constant_2021_intl_usd                | **-0.0238128**  | 0.0110694   | **0.0358666**   |
| macro_change_wdi_openness         | d_wdi_goods_services_trade_openness_pct_gdp            | 7.83126e-05     | 5.76508e-05 | 0.179884        |
| macro_lagged_change_goods_exports | l1_d_log_goods_exports_current_usd                     | 0.00168639      | 0.00218742  | 0.444037        |
| macro_lagged_change_goods_exports | l1_d_log_gdp_pc_ppp_constant_2021_intl_usd             | -0.0018364      | 0.0159205   | 0.908589        |
| macro_lagged_change_goods_exports | l1_d_trade_openness_pct_gdp                            | -7.6808e-05     | 4.08862e-05 | 0.0656059       |
| macro_lagged_change_real_exports  | l1_d_log_real_exports_goods_services_constant_2015_usd | -0.00121283     | 0.00378795  | 0.750114        |
| macro_lagged_change_real_exports  | l1_d_log_gdp_pc_ppp_constant_2021_intl_usd             | -0.0172027      | 0.0135836   | 0.211003        |
| macro_lagged_change_real_exports  | l1_d_trade_openness_pct_gdp                            | -6.68307e-05    | 3.50906e-05 | 0.0623811       |
| macro_lagged_change_wdi_openness  | l1_d_log_goods_exports_current_usd                     | -0.0012199      | 0.0017439   | 0.487173        |
| macro_lagged_change_wdi_openness  | l1_d_log_gdp_pc_ppp_constant_2021_intl_usd             | -0.0162372      | 0.00999661  | 0.110035        |
| macro_lagged_change_wdi_openness  | l1_d_wdi_goods_services_trade_openness_pct_gdp         | 4.60453e-05     | 4.99903e-05 | 0.36103         |
| policy_lagged_counts_direct       | log1p_import_substitution_ip_measures_l1               | 0.00100909      | 0.00108988  | 0.358632        |

## Estimation Status

| status   |   models |
|:---------|---------:|
| ok       |       24 |

## Crosswalk

| cross_section_model_id   | lifecycle_model_ids                                                                    | lifecycle_status   | rationale                                                                                          |
|:-------------------------|:---------------------------------------------------------------------------------------|:-------------------|:---------------------------------------------------------------------------------------------------|
| xs_exports               | macro_level_goods_exports;macro_change_goods_exports;macro_lagged_change_goods_exports | converted          | Exports are re-estimated as within-country levels, annual changes, and lagged annual changes.      |
| xs_real_exports          | macro_level_real_exports;macro_change_real_exports;macro_lagged_change_real_exports    | converted          | Real-export version of the export lifecycle comparison.                                            |
| xs_income                | macro_level_goods_exports;macro_change_goods_exports;macro_lagged_change_goods_exports | converted          | Income enters the macro lifecycle level, change, and lagged-change specifications.                 |
| xs_openness              | macro_level_goods_exports;macro_change_goods_exports;macro_lagged_change_goods_exports | converted          | Openness enters the macro lifecycle level, change, and lagged-change specifications.               |
| xs_full                  | macro_level_goods_exports;macro_change_goods_exports;macro_lagged_change_goods_exports | converted          | Full macro controls are converted to lifecycle levels and changes.                                 |
| xs_full_wdi_openness     | macro_level_wdi_openness;macro_change_wdi_openness;macro_lagged_change_wdi_openness    | converted          | WDI openness is kept as a parallel lifecycle macro specification.                                  |
| xs_tariff_robust         | macro_level_tariff                                                                     | level_only         | Tariff coverage is sparse, so the lifecycle conversion is limited to the level FE model.           |
| xs_increase_lpm          |                                                                                        | not_converted_main | The binary ever-increased outcome is inherently endpoint-based; it is not a main lifecycle design. |
| m6_country_change_direct | policy_lagged_counts_direct;policy_cumulative_pre_direct                               | converted          | Direct named industrial-policy exposure is converted to lagged-flow and cumulative-pre FE models.  |

## Files

- `lifecycle_regression_terms.csv`: term-level coefficients, standard errors, and p-values.
- `lifecycle_model_summary.csv`: formulas, sample sizes, fixed effects, R2, and covariance information.
- `lifecycle_sample_manifest.csv`: attrition, missingness, country coverage, and within-country variation checks.
- `cross_section_to_lifecycle_crosswalk.csv`: mapping from old cross-sectional models to lifecycle equivalents.
