# Partner Gini Stability Test

Generated: 2026-06-02T12:25:18+00:00

## Question

Is active Partner Gini relatively stable over time within rd2 countries?

This is a descriptive panel/time-series stability check, not a causal design. The unit is country-year-flow. Partner Gini measures concentration across observed positive destination/source partner totals. The source table inherits the project partner convention: partner totals include HS6 `999999`, while aggregate `partnerCode == 0` is excluded upstream.

## Main Test Window

- Sample: `rd2_countries`
- Source: `results/samples/rd2_countries/exercise_01_tables/partner_concentration_all_years.csv`
- Main window: 2000-2024, excluding partial 2025 coverage.
- Balanced sensitivity: 2001-2021, country-flow rows with every year in that interval.
- Practical stability margin for slopes: absolute fitted 10-year change in Partner Gini <= 0.02.
- Practical stability margin for endpoints: absolute first-to-last change <= 0.05.

## Main Results

| flow    |   countries |   median_abs_slope_per_decade |   p90_abs_slope_per_decade |   share_stable_slope_10yr_0p02 |   median_abs_endpoint_change |   p90_abs_endpoint_change |   share_stable_endpoint_0p05 |   median_within_country_sd |   countries_with_slope_q_lt_0p05 |
|:--------|------------:|------------------------------:|---------------------------:|-------------------------------:|-----------------------------:|--------------------------:|-----------------------------:|---------------------------:|---------------------------------:|
| Exports |          60 |                        0.007  |                     0.0254 |                         0.85   |                       0.0136 |                    0.0659 |                         0.85 |                     0.0115 |                               32 |
| Imports |          60 |                        0.0046 |                     0.0192 |                         0.9167 |                       0.0128 |                    0.0448 |                         0.9  |                     0.0079 |                               32 |

## Common Within-Country Trend

Specification: `partner_gini_ct = beta * trend_t + country_FE_c + error_ct`, estimated separately by flow with standard errors clustered by reporter country. Coefficients, standard errors, and confidence intervals are scaled to a 10-year change.

| flow    |   coefficient_per_decade |   std_error_per_decade |   ci_low_per_decade |   ci_high_per_decade |   p_value |   bh_q_value |   nobs |   countries |   r_squared | status   |
|:--------|-------------------------:|-----------------------:|--------------------:|---------------------:|----------:|-------------:|-------:|------------:|------------:|:---------|
| Exports |                  0.00083 |                0.00186 |            -0.0029  |              0.00456 |   0.65639 |      0.65639 |   1491 |          60 |     0.77324 | ok       |
| Imports |                  0.00305 |                0.00144 |             0.00017 |              0.00593 |   0.03826 |      0.13336 |   1492 |          60 |     0.79278 | ok       |

The `p_value` column is the raw clustered-inference p-value. The `bh_q_value` column applies a Benjamini-Hochberg adjustment across the common-trend rows in this exercise.

## How Much Do Common Year Effects Add?

This compares country fixed effects alone with country plus year fixed effects. A small incremental R-squared from year fixed effects means common time movement is small relative to persistent country differences and residual year-to-year variation.

| flow    |   r2_country_fe |   r2_country_year_fe |   incremental_r2_year_fe |   rmse_country_fe |   rmse_country_year_fe |
|:--------|----------------:|---------------------:|-------------------------:|------------------:|-----------------------:|
| Exports |         0.77292 |              0.78154 |                  0.00863 |           0.01588 |                0.01557 |
| Imports |         0.78769 |              0.79392 |                  0.00623 |           0.01413 |                0.01392 |

## Largest Country Endpoint Changes

| flow    | country              | iso3   |   first_year |   last_year |   first_partner_gini |   last_partner_gini |   endpoint_change |   slope_per_decade |   sd_partner_gini |   slope_q_value |   first_partner_active_count |   last_partner_active_count |   min_partner_active_count |   median_partner_active_count |
|:--------|:---------------------|:-------|-------------:|------------:|---------------------:|--------------------:|------------------:|-------------------:|------------------:|----------------:|-----------------------------:|----------------------------:|---------------------------:|------------------------------:|
| Imports | Armenia              | ARM    |         2000 |        2024 |               0.8164 |              0.9401 |            0.1237 |             0.0463 |            0.0356 |          0      |                           80 |                         185 |                         80 |                         156   |
| Exports | United Arab Emirates | ARE    |         2000 |        2023 |               0.8    |              0.9187 |            0.1187 |             0.0006 |            0.0388 |          0.9643 |                            5 |                         219 |                          5 |                         196   |
| Imports | Kyrgyzstan           | KGZ    |         2000 |        2024 |               0.8528 |              0.9453 |            0.0925 |             0.0303 |            0.0252 |          0      |                           86 |                         152 |                         86 |                         124   |
| Exports | Senegal              | SEN    |         2000 |        2024 |               0.8114 |              0.889  |            0.0776 |             0.0122 |            0.022  |          0.1442 |                           86 |                         137 |                         80 |                         137   |
| Exports | Egypt                | EGY    |         2000 |        2024 |               0.8853 |              0.8086 |           -0.0768 |            -0.0349 |            0.0293 |          0      |                          155 |                         179 |                        155 |                         174   |
| Exports | Mauritania           | MRT    |         2000 |        2024 |               0.8299 |              0.9055 |            0.0757 |             0.0369 |            0.0345 |          0      |                           51 |                         101 |                         32 |                          76.5 |
| Exports | Armenia              | ARM    |         2000 |        2024 |               0.8692 |              0.9434 |            0.0742 |             0.0214 |            0.0226 |          0.0035 |                           68 |                         107 |                         68 |                          93   |
| Exports | China                | CHN    |         2000 |        2024 |               0.9063 |              0.8321 |           -0.0742 |            -0.0272 |            0.0216 |          0      |                          208 |                         215 |                        208 |                         216   |
| Exports | Kyrgyzstan           | KGZ    |         2000 |        2024 |               0.87   |              0.935  |            0.065  |             0.0323 |            0.0264 |          0      |                           64 |                         102 |                         59 |                          85   |
| Imports | Rwanda               | RWA    |         2001 |        2022 |               0.8326 |              0.8932 |            0.0606 |             0.0198 |            0.0201 |          0.035  |                          107 |                         182 |                        107 |                         157.5 |
| Exports | Burkina Faso         | BFA    |         2000 |        2024 |               0.8902 |              0.9503 |            0.0601 |             0.0364 |            0.0339 |          0      |                           69 |                          98 |                         56 |                          90   |
| Imports | Cambodia             | KHM    |         2000 |        2024 |               0.8929 |              0.9526 |            0.0597 |             0.0192 |            0.0163 |          0      |                           96 |                         155 |                         92 |                         133   |

Active-partner counts in this table are diagnostic coverage warnings. A large endpoint change is less interpretable when the first or minimum active-partner count is very low.

## Low Active-Partner Sensitivity

This sensitivity drops reporter-year-flow observations with fewer than 10 active trade partners, then recomputes the same country-flow stability summary. It treats very low partner counts as coverage warnings, not as proof that the original observation is invalid.

| window             | flow    |   min_partner_active_count_required |   original_rows |   kept_rows |   dropped_rows |   eligible_country_flows |   median_abs_slope_per_decade |   share_stable_slope_10yr_0p02 |   median_abs_endpoint_change |   share_stable_endpoint_0p05 |
|:-------------------|:--------|------------------------------------:|----------------:|------------:|---------------:|-------------------------:|------------------------------:|-------------------------------:|-----------------------------:|-----------------------------:|
| balanced_2001_2021 | Exports |                                  10 |            1239 |        1239 |              0 |                       59 |                        0.0069 |                         0.8136 |                       0.0145 |                       0.8814 |
| balanced_2001_2021 | Imports |                                  10 |            1260 |        1258 |              2 |                       60 |                        0.0047 |                         0.8833 |                       0.0112 |                       0.9333 |
| main_2000_2024     | Exports |                                  10 |            1491 |        1490 |              1 |                       60 |                        0.0085 |                         0.85   |                       0.0136 |                       0.8667 |
| main_2000_2024     | Imports |                                  10 |            1492 |        1489 |              3 |                       60 |                        0.0047 |                         0.9    |                       0.0128 |                       0.8833 |

## Count Diagnostics

| diagnostic                          |   value |
|:------------------------------------|--------:|
| Source rows                         |    3845 |
| Source country-flow series          |     120 |
| Duplicate country-year-flow keys    |       0 |
| Missing Partner Gini rows           |       0 |
| Main-window rows (2000-2024)        |    2983 |
| Main-window country-flow series     |     120 |
| Balanced-window rows (2001-2021)    |    2499 |
| Balanced-window country-flow series |     119 |

## Interpretation

The hypothesis is mostly true for the cross-country median and for most country-flow series: Partner Gini is high and moves slowly. It is not true literally for every country. Some countries have large endpoint changes or statistically detectable country-specific trends, so the defensible statement is "Partner Gini is relatively stable for most rd2 countries over 2000-2024, with meaningful country exceptions."

## Outputs

- `results/samples/rd2_countries/partner_gini_stability_tables/country_flow_stability.csv`
- `results/samples/rd2_countries/partner_gini_stability_tables/stability_summary.csv`
- `results/samples/rd2_countries/partner_gini_stability_tables/common_trend_models.csv`
- `results/samples/rd2_countries/partner_gini_stability_tables/variance_decomposition.csv`
- `results/samples/rd2_countries/partner_gini_stability_tables/low_active_partner_sensitivity.csv`
- `results/samples/rd2_countries/partner_gini_stability_figures/country_slope_distribution.png`
- `results/samples/rd2_countries/partner_gini_stability_figures/largest_endpoint_changes.png`
