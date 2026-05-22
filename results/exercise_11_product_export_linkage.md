# Exercise 11: Product Contribution and Export Linkage

Generated from checkpointed aggregate files.

## Question

Do the HS6 products that make a country's total import basket more concentrated also link to exports, especially through intermediate goods?

## Sample

- Product-level rows: 5,568,474
- Countries: 33
- Years: 1988-2025
- Unit: country-year-HS6 import product

## Main Variables

- `loo_gini_contribution`: total import product Gini minus product Gini after removing that HS6 product.
- `loo_partner_hhi_contribution`: total partner-country HHI minus partner-country HHI after removing that HS6 product.
- Export outcomes: export indicator, asinh export value, export share.

## Selected Regression Results

| model_label                                   | outcome            | term                           |    coef |   std_error |   p_value |    nobs |   clusters |   r2_within |
|:----------------------------------------------|:-------------------|:-------------------------------|--------:|------------:|----------:|--------:|-----------:|------------:|
| product_export_value_gini                     | asinh_export_value | loo_gini_contribution_z        | -4.8624 |      0.5185 |    0      | 5568474 |         33 |      0.1583 |
| product_export_any_gini                       | export_any         | loo_gini_contribution_z        | -0.1295 |      0.0213 |    0      | 5568474 |         33 |      0.0378 |
| product_export_value_partner_hhi              | asinh_export_value | loo_partner_hhi_contribution_z |  0.2345 |      0.0892 |    0.0086 | 5568474 |         33 |      0.0337 |
| product_export_value_intermediate_interaction | asinh_export_value | loo_gini_contribution_z        | -4.7737 |      0.5051 |    0      | 5568474 |         33 |      0.1584 |
| product_export_value_intermediate_interaction | asinh_export_value | loo_gini_x_intermediate_z      | -0.5203 |      0.1627 |    0.0014 | 5568474 |         33 |      0.1584 |

## Country-Year Fixed-Effect Logit

The binary export outcome is also estimated with a country-year fixed-effect logit. This is the computationally feasible nonlinear probability model for the 5.5 million-row HS6 panel; it compares imported products within the same reporter-year and drops reporter-years with no within-group variation in `export_any`.

| model_label                          | estimator                       | outcome    | term                    |    coef |   std_error |   p_value |    nobs |   groups |   dropped_no_variation_groups | converged   |
|:-------------------------------------|:--------------------------------|:-----------|:------------------------|--------:|------------:|----------:|--------:|---------:|------------------------------:|:------------|
| product_export_any_conditional_logit | country_year_fixed_effect_logit | export_any | loo_gini_contribution_z | -3.3891 |      0.009  |         0 | 5562527 |     1128 |                             2 | True        |
| product_export_any_conditional_logit | country_year_fixed_effect_logit | export_any | import_value_share_z    |  4.1779 |      0.0116 |         0 | 5562527 |     1128 |                             2 | True        |

## Broader HS2 Robustness

The HS6 exact-product outcome may be too narrow for an intermediate-processing claim because imported inputs and exported outputs can sit in different HS6 product lines inside the same broader production chain. The HS2 robustness aggregates HS6 concentration contributions and exports to HS chapters, then reruns export-linkage regressions with country-year and HS2 fixed effects.

| model_label                             | outcome                | term                                            |    coef |   std_error |   p_value |   nobs |   clusters |   r2_within |
|:----------------------------------------|:-----------------------|:------------------------------------------------|--------:|------------:|----------:|-------:|-----------:|------------:|
| hs2_export_value_gini                   | asinh_hs2_export_value | hs2_product_loo_gini_sum_z                      | -0.1818 |      0.0659 |    0.0058 | 108369 |         33 |      0.5846 |
| hs2_export_any_gini                     | hs2_export_any         | hs2_product_loo_gini_sum_z                      | -0.0021 |      0.0019 |    0.2639 | 108369 |         33 |      0.0192 |
| hs2_export_share_gini                   | hs2_export_share       | hs2_product_loo_gini_sum_z                      |  0.0026 |      0.002  |    0.1766 | 108369 |         33 |      0.4454 |
| hs2_export_value_intermediate_intensity | asinh_hs2_export_value | hs2_product_loo_gini_sum_z                      | -0.1671 |      0.065  |    0.0101 | 108369 |         33 |      0.5862 |
| hs2_export_value_intermediate_intensity | asinh_hs2_export_value | hs2_product_loo_gini_sum_x_intermediate_share_z |  0.0467 |      0.0343 |    0.1735 | 108369 |         33 |      0.5862 |

## Commodity-Outlier Exclusion

The narrow HS6 regressions were also rerun after excluding coal (`2701`), crude and refined petroleum (`2709`, `2710`), petroleum gases/natural gas (`2711`), and gold (`7108`). This checks whether the main result is just an oil/gas/gold/coal result.

| sample                      | check                                         |    coef |   std_error |   ci_low |   ci_high |    nobs |   r2_within |
|:----------------------------|:----------------------------------------------|--------:|------------:|---------:|----------:|--------:|------------:|
| baseline                    | Export value: product-Gini contribution       | -4.8624 |      0.5185 |  -5.8786 |   -3.8462 | 5568474 |      0.1583 |
| baseline                    | Export probability: product-Gini contribution | -0.1295 |      0.0213 |  -0.1712 |   -0.0877 | 5568474 |      0.0378 |
| baseline                    | Export value: partner-HHI contribution        |  0.2345 |      0.0892 |   0.0596 |    0.4094 | 5568474 |      0.0337 |
| baseline                    | Intermediate interaction                      | -0.5203 |      0.1627 |  -0.8392 |   -0.2013 | 5568474 |      0.1584 |
| excluding oil/gas/gold/coal | Export value: product-Gini contribution       | -3.6671 |      0.2219 |  -4.102  |   -3.2321 | 5547335 |      0.1981 |
| excluding oil/gas/gold/coal | Export probability: product-Gini contribution | -0.0998 |      0.0133 |  -0.126  |   -0.0737 | 5547335 |      0.0457 |
| excluding oil/gas/gold/coal | Export value: partner-HHI contribution        |  0.1199 |      0.0357 |   0.0499 |    0.1899 | 5547335 |      0.0466 |
| excluding oil/gas/gold/coal | Intermediate interaction                      | -0.4692 |      0.1432 |  -0.7499 |   -0.1885 | 5547335 |      0.1989 |

## Files

- Data: `data/processed/exercise_11_product_export_linkage_panel.parquet`, `data/processed/exercise_11_sector_export_linkage_panel.parquet`, `data/processed/exercise_11_hs2_export_linkage_panel.parquet`
- Tables: `results/exercise_11_product_export_linkage_tables`
- Figures: `results/exercise_11_product_export_linkage_figures`

## Interpretation

The regressions are descriptive. Positive coefficients support the idea that concentration-driving import products are export-linked. They do not prove that import concentration causes exports.
