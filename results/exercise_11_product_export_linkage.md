# Exercise 11: Product Contribution and Export Linkage

Generated from checkpointed aggregate files.

## Question

Do the HS6 products that make a country's total import basket more concentrated also link to exports, especially through intermediate goods?

## Sample

- Product-level rows: 5,524,696
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
| product_export_value_gini                     | asinh_export_value | loo_gini_contribution_z        | -4.9265 |      0.5528 |     0     | 5524696 |         33 |      0.1539 |
| product_export_any_gini                       | export_any         | loo_gini_contribution_z        | -0.1296 |      0.022  |     0     | 5524696 |         33 |      0.037  |
| product_export_value_partner_hhi              | asinh_export_value | loo_partner_hhi_contribution_z |  0.2237 |      0.0777 |     0.004 | 5524696 |         33 |      0.034  |
| product_export_value_intermediate_interaction | asinh_export_value | loo_gini_contribution_z        | -4.8294 |      0.542  |     0     | 5524696 |         33 |      0.1556 |
| product_export_value_intermediate_interaction | asinh_export_value | loo_gini_x_intermediate_z      | -0.7053 |      0.169  |     0     | 5524696 |         33 |      0.1556 |

## Broader HS2 Robustness

The HS6 exact-product outcome may be too narrow for an intermediate-processing claim because imported inputs and exported outputs can sit in different HS6 product lines inside the same broader production chain. The HS2 robustness aggregates HS6 concentration contributions and exports to HS chapters, then reruns export-linkage regressions with country-year and HS2 fixed effects.

| model_label                             | outcome                | term                                            |    coef |   std_error |   p_value |   nobs |   clusters |   r2_within |
|:----------------------------------------|:-----------------------|:------------------------------------------------|--------:|------------:|----------:|-------:|-----------:|------------:|
| hs2_export_value_gini                   | asinh_hs2_export_value | hs2_product_loo_gini_sum_z                      | -0.1862 |      0.0684 |    0.0065 | 108965 |         33 |      0.5721 |
| hs2_export_any_gini                     | hs2_export_any         | hs2_product_loo_gini_sum_z                      | -0.002  |      0.002  |    0.3238 | 108965 |         33 |      0.0185 |
| hs2_export_share_gini                   | hs2_export_share       | hs2_product_loo_gini_sum_z                      |  0.0022 |      0.0017 |    0.1851 | 108965 |         33 |      0.4502 |
| hs2_export_value_intermediate_intensity | asinh_hs2_export_value | hs2_product_loo_gini_sum_z                      | -0.179  |      0.0659 |    0.0066 | 108965 |         33 |      0.5732 |
| hs2_export_value_intermediate_intensity | asinh_hs2_export_value | hs2_product_loo_gini_sum_x_intermediate_share_z |  0.0198 |      0.0349 |    0.57   | 108965 |         33 |      0.5732 |

## Commodity-Outlier Exclusion

The narrow HS6 regressions were also rerun after excluding coal (`2701`), crude and refined petroleum (`2709`, `2710`), petroleum gases/natural gas (`2711`), and gold (`7108`). This checks whether the main result is just an oil/gas/gold/coal result.

| sample                      | check                                         |    coef |   std_error |   ci_low |   ci_high |    nobs |   r2_within |
|:----------------------------|:----------------------------------------------|--------:|------------:|---------:|----------:|--------:|------------:|
| baseline                    | Export value: product-Gini contribution       | -4.9265 |      0.5528 |  -6.01   |   -3.843  | 5524696 |      0.1539 |
| baseline                    | Export probability: product-Gini contribution | -0.1296 |      0.022  |  -0.1727 |   -0.0866 | 5524696 |      0.037  |
| baseline                    | Export value: partner-HHI contribution        |  0.2237 |      0.0777 |   0.0715 |    0.3759 | 5524696 |      0.034  |
| baseline                    | Intermediate interaction                      | -0.7053 |      0.169  |  -1.0366 |   -0.374  | 5524696 |      0.1556 |
| excluding oil/gas/gold/coal | Export value: product-Gini contribution       | -4.1133 |      0.2784 |  -4.6589 |   -3.5677 | 5503557 |      0.1897 |
| excluding oil/gas/gold/coal | Export probability: product-Gini contribution | -0.1095 |      0.0155 |  -0.1398 |   -0.0791 | 5503557 |      0.0437 |
| excluding oil/gas/gold/coal | Export value: partner-HHI contribution        |  0.1504 |      0.0415 |   0.0689 |    0.2318 | 5503557 |      0.0427 |
| excluding oil/gas/gold/coal | Intermediate interaction                      | -0.7789 |      0.1438 |  -1.0607 |   -0.4972 | 5503557 |      0.1939 |

## Files

- Data: `data/processed/exercise_11_product_export_linkage_panel.parquet`, `data/processed/exercise_11_sector_export_linkage_panel.parquet`, `data/processed/exercise_11_hs2_export_linkage_panel.parquet`
- Tables: `results/exercise_11_product_export_linkage_tables`
- Figures: `results/exercise_11_product_export_linkage_figures`

## Interpretation

The regressions are descriptive. Positive coefficients support the idea that concentration-driving import products are export-linked. They do not prove that import concentration causes exports.
