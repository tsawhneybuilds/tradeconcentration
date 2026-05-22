# Exercise 13: Import Concentration Hypothesis Tests

Generated: 2026-05-22T12:33:07+00:00

This memo implements current-data tests for three hypotheses: fixed-cost sourcing, granular product-source corridors, and dominant supplier ecosystems. It uses country-HS6-source-year aggregate import data, not firm customs records, so firm-level conclusions are suggestive.

## Coverage

- Product-level importer-HS6-year rows: 5,568,474 product-country-year observations across country-years
- Product-partner-cell country-year rows: 1,130
- Classified supplier-ecosystem panel: `data/processed/exercise_13_supplier_ecosystem_panel.parquet`
- Tables: `results/exercise_13_import_hypotheses_tables/`

## H1: Fixed-Cost Sourcing Proxy

This test asks whether top source relationships are persistent and whether product-market scale mainly deepens incumbent sourcing instead of diffusing sources. It proxies firm-level fixed-cost sourcing with importer-HS6 top-source persistence.

### Top Supplier Persistence

| sample   |         rows |   same_top_supplier_rate |   import_value_weighted_same_top_supplier_rate |   median_lag_top_supplier_share |   median_lag_top_supplier_age |   share_lag_top_supplier_ge_75 |   current_top_import_value_share_when_same |
|:---------|-------------:|-------------------------:|-----------------------------------------------:|--------------------------------:|------------------------------:|-------------------------------:|-------------------------------------------:|
| all      | 5265693.0000 |                   0.6901 |                                         0.8490 |                          0.5035 |                        4.0000 |                         0.2141 |                                     0.8922 |

### Persistence By Import Bin

| import_bin            |         rows |   same_top_supplier_rate |   import_value_weighted_same_top_supplier_rate |   median_lag_top_supplier_share |   median_lag_top_supplier_age |   share_lag_top_supplier_ge_75 |   current_top_import_value_share_when_same |
|:----------------------|-------------:|-------------------------:|-----------------------------------------------:|--------------------------------:|------------------------------:|-------------------------------:|-------------------------------------------:|
| capital_goods         |  657126.0000 |                   0.6141 |                                         0.8215 |                          0.4623 |                        3.0000 |                         0.1606 |                                     0.8616 |
| energy                |   28590.0000 |                   0.7227 |                                         0.8530 |                          0.5802 |                        4.0000 |                         0.3277 |                                     0.9005 |
| final_consumption     | 1314299.0000 |                   0.7343 |                                         0.8892 |                          0.4906 |                        4.0000 |                         0.1940 |                                     0.9285 |
| intermediates         | 3160272.0000 |                   0.6885 |                                         0.8393 |                          0.5181 |                        4.0000 |                         0.2332 |                                     0.8830 |
| unmapped_or_ambiguous |  105406.0000 |                   0.6529 |                                         0.7991 |                          0.4809 |                        3.0000 |                         0.1937 |                                     0.8529 |

### Outlier Robustness

| sample                      |         rows |   same_top_supplier_rate |   import_value_weighted_same_top_supplier_rate |   median_lag_top_supplier_share |   median_lag_top_supplier_age |   share_lag_top_supplier_ge_75 |   current_top_import_value_share_when_same |
|:----------------------------|-------------:|-------------------------:|-----------------------------------------------:|--------------------------------:|------------------------------:|-------------------------------:|-------------------------------------------:|
| commodity_outliers          |   19484.0000 |                   0.6773 |                                         0.8333 |                          0.6010 |                        3.0000 |                         0.3522 |                                     0.8832 |
| excluding_oil_gas_gold_coal | 5246209.0000 |                   0.6902 |                                         0.8516 |                          0.5032 |                        4.0000 |                         0.2135 |                                     0.8934 |

### Selected Fixed-Effect Model Coefficients

| sample                      | model_label                                      | outcome                           | term                                    |   coefficient |   std_error |    nobs |   r2_within |
|:----------------------------|:-------------------------------------------------|:----------------------------------|:----------------------------------------|--------------:|------------:|--------:|------------:|
| all_products                | h1_current_top_share                             | within_product_top_supplier_share | lag_within_product_top_supplier_share_z |        0.1018 |      0.0027 | 3633922 |      0.2662 |
| all_products                | h1_current_top_share                             | within_product_top_supplier_share | log_lag_top_supplier_run_age_z          |        0.0031 |      0.0007 | 3633922 |      0.2662 |
| excluding_oil_gas_gold_coal | h1_current_top_share                             | within_product_top_supplier_share | lag_within_product_top_supplier_share_z |        0.1018 |      0.0027 | 3620726 |      0.2661 |
| excluding_oil_gas_gold_coal | h1_current_top_share                             | within_product_top_supplier_share | log_lag_top_supplier_run_age_z          |        0.0031 |      0.0007 | 3620726 |      0.2661 |
| all_products                | h1_market_size_within_product_top_supplier_share | within_product_top_supplier_share | log_import_value_z                      |       -0.0034 |      0.0037 | 5568474 |      0.0001 |
| all_products                | h1_market_size_within_product_source_hhi         | within_product_source_hhi         | log_import_value_z                      |       -0.0147 |      0.0044 | 5568474 |      0.0012 |
| all_products                | h1_market_size_log_supplier_count                | log_supplier_count                | log_import_value_z                      |        0.3504 |      0.0082 | 5568474 |      0.2143 |
| excluding_oil_gas_gold_coal | h1_market_size_within_product_top_supplier_share | within_product_top_supplier_share | log_import_value_z                      |       -0.0028 |      0.0037 | 5547335 |      0.0000 |
| excluding_oil_gas_gold_coal | h1_market_size_within_product_source_hhi         | within_product_source_hhi         | log_import_value_z                      |       -0.0141 |      0.0044 | 5547335 |      0.0011 |
| excluding_oil_gas_gold_coal | h1_market_size_log_supplier_count                | log_supplier_count                | log_import_value_z                      |        0.3505 |      0.0082 | 5547335 |      0.2134 |

The saturated LPM for `same_top_supplier` is retained in the CSV for transparency, but its selected fixed effects absorb the usable binary variation. The descriptive persistence rates and the current-share model are the primary current-data evidence for top-source survival.

Interpretation rule: positive lag-share and age coefficients support sticky sourcing relationships; positive market-size effects on top share/source HHI with weak supplier-count expansion support scale through incumbents.

## H4: Granular Product-Source Corridors

This test asks whether a small set of product-source cells accounts for a large share of import value and concentration. It is a corridor-level proxy; it does not observe firms.

### Cell-Level Median Summary

| measure                            |   median |
|:-----------------------------------|---------:|
| top_1_cell_share                   |   0.0274 |
| top_5_cell_share                   |   0.0815 |
| top_10_cell_share                  |   0.1195 |
| top_25_cell_share                  |   0.1852 |
| gini_reduction_top_10_cells        |   0.0077 |
| partner_hhi_reduction_top_10_cells |   0.0001 |

### Product-Level Median Summary

| measure                                      |   median |
|:---------------------------------------------|---------:|
| top_1_product_share                          |   0.0586 |
| top_5_product_share                          |   0.1575 |
| top_10_product_share                         |   0.2192 |
| top_25_product_share                         |   0.3181 |
| top_10_positive_loo_gini_contribution        |   0.0305 |
| top_10_positive_loo_partner_hhi_contribution |   0.0079 |

### Top-Cell Persistence

| index                               |     count |   unique | top       |     freq |      mean |      std |       min |       25% |       50% |       75% |       max |
|:------------------------------------|----------:|---------:|:----------|---------:|----------:|---------:|----------:|----------:|----------:|----------:|----------:|
| iso3                                | 1096.0000 |  33.0000 | AUS       |  37.0000 |  nan      | nan      |  nan      |  nan      |  nan      |  nan      |  nan      |
| country                             | 1096.0000 |  33.0000 | Australia |  37.0000 |  nan      | nan      |  nan      |  nan      |  nan      |  nan      |  nan      |
| year                                | 1096.0000 | nan      | nan       | nan      | 2008.3385 |   9.8307 | 1989.0000 | 2000.0000 | 2008.0000 | 2017.0000 | 2025.0000 |
| top_10_jaccard_vs_previous_year     | 1096.0000 | nan      | nan       | nan      |    0.6141 |   0.1763 |    0.1111 |    0.5385 |    0.6667 |    0.6667 |    1.0000 |
| top_10_share_also_top_previous_year | 1096.0000 | nan      | nan       | nan      |    0.7456 |   0.1419 |    0.2000 |    0.7000 |    0.8000 |    0.8000 |    1.0000 |
| top_25_jaccard_vs_previous_year     | 1096.0000 | nan      | nan       | nan      |    0.6248 |   0.1333 |    0.1628 |    0.5152 |    0.6129 |    0.7241 |    0.9231 |
| top_25_share_also_top_previous_year | 1096.0000 | nan      | nan       | nan      |    0.7605 |   0.1056 |    0.2800 |    0.6800 |    0.7600 |    0.8400 |    0.9600 |
| top_100_jaccard_vs_previous_year    | 1096.0000 | nan      | nan       | nan      |    0.6368 |   0.1041 |    0.1494 |    0.5748 |    0.6529 |    0.7094 |    0.8868 |

Interpretation rule: high top-cell shares, positive concentration reductions after removing top cells, and high year-to-year top-cell overlap support the granular-corridor proxy for firm granularity.

## H2: Dominant Supplier Ecosystems

This test separates global supplier dominance from economy-specific sourcing concentration. Global metrics are computed from country-coded source partners only; importer-level concentration uses observed top-source measures.

### Latest-Country Median Import Shares By Class

| class                            |   latest_country_median_share |
|:---------------------------------|------------------------------:|
| global_dominant                  |                        0.0104 |
| economy_specific                 |                        0.1328 |
| global_concentrated_other_source |                        0.0005 |
| diffuse                          |                        0.8537 |
| non_country_top_supplier         |                        0.0000 |
| dominant_or_economy_specific     |                        0.1430 |

### Latest Country Examples

| country     | iso3   |   year |   global_dominant |   economy_specific |   global_concentrated_other_source |   dominant_or_economy_specific |   diffuse |
|:------------|:-------|-------:|------------------:|-------------------:|-----------------------------------:|-------------------------------:|----------:|
| Canada      | CAN    |   2025 |            0.0147 |             0.3195 |                             0.0004 |                         0.3347 |    0.6631 |
| Mexico      | MEX    |   2025 |            0.0095 |             0.3064 |                             0.0002 |                         0.3161 |    0.6837 |
| Luxembourg  | LUX    |   2025 |            0.0179 |             0.2970 |                             0.0006 |                         0.3156 |    0.6701 |
| Brazil      | BRA    |   2025 |            0.0174 |             0.2626 |                             0.0013 |                         0.2812 |    0.7160 |
| Japan       | JPN    |   2025 |            0.0151 |             0.2235 |                             0.0006 |                         0.2392 |    0.7595 |
| Finland     | FIN    |   2025 |            0.0075 |             0.2279 |                             0.0003 |                         0.2357 |    0.7611 |
| New Zealand | NZL    |   2025 |            0.0200 |             0.1995 |                             0.0011 |                         0.2206 |    0.7739 |
| Ireland     | IRL    |   2024 |            0.0087 |             0.2038 |                             0.0003 |                         0.2128 |    0.7813 |
| Korea       | KOR    |   2024 |            0.0226 |             0.1865 |                             0.0003 |                         0.2094 |    0.7895 |
| Russia      | RUS    |   2021 |            0.0240 |             0.1809 |                             0.0006 |                         0.2055 |    0.7899 |
| Australia   | AUS    |   2025 |            0.0112 |             0.1936 |                             0.0003 |                         0.2050 |    0.7819 |
| Belgium     | BEL    |   2024 |            0.0040 |             0.1834 |                             0.0066 |                         0.1939 |    0.8025 |

Interpretation rule: high `global_dominant` supports supplier ecosystems with few global sources; high `economy_specific` supports country-specific sourcing relationships even when global supply is diversified.

## Gold-Standard Tests Not Run

The repository does not contain firm-product-source-year customs records or foreign supplier IDs. The firm and supplier-link tests in the plan therefore remain data requirements, not implemented empirical results.

## Files

- `h1_top_supplier_persistence_overall.csv`
- `h1_top_supplier_persistence_by_bin.csv`
- `h1_fixed_cost_sourcing_models.csv`
- `h4_cell_granularity_country_year.csv`
- `h4_top_cells_latest.csv`
- `h4_product_granularity_country_year.csv`
- `h2_global_source_metrics.csv`
- `h2_supplier_ecosystem_country_year.csv`
- `h2_supplier_ecosystem_by_bin.csv`
- `h2_supplier_ecosystem_top_products_latest.csv`
