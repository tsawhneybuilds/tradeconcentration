# Exercise 3: Import Bin Exercise

Generated: 2026-05-19T16:03:12+00:00

This memo is intentionally descriptive. `exercises.md` should only be updated after discussion.

## Coverage

- Country-year-bin rows: 5650
- Countries: 33
- Years: 1988-2025
- Approved mapping: `data/processed/exercise_03_bec5_mapping_approved.csv`
- Source details: `{"chunk_rows": 500000, "finalize_only": true, "hs_bulk_files_seen": 1130, "mode": "checkpointed_streaming", "partial_dir": "data/processed/exercise_03_file_aggregates", "partial_files": {"mapping_coverage": 1130, "product_values": 1130}}`

## Median Concentration By Import Bin

| import_bin        |   rows |   median_product_gini |   median_top_1_product_share |   median_active_products |
|:------------------|-------:|----------------------:|-----------------------------:|-------------------------:|
| capital_goods     |   1130 |                0.8009 |                       0.0885 |                      599 |
| energy            |   1130 |                0.8837 |                       0.5403 |                       27 |
| final_consumption |   1130 |                0.8235 |                       0.1015 |                     1199 |
| intermediates     |   1130 |                0.8481 |                       0.0502 |                     2984 |

## Median Aggregate Import Concentration

|                      |   median_country_year |
|:---------------------|----------------------:|
| product_gini         |                0.859  |
| top_1_product_share  |                0.065  |
| top_5_product_share  |                0.1738 |
| top_10_product_share |                0.238  |
| active_products      |             4929      |

## Median Import Value Share By Bin

| import_bin        |   rows |   median_import_value_share |   median_total_imports_in_bin |
|:------------------|-------:|----------------------------:|------------------------------:|
| capital_goods     |   1130 |                      0.1354 |                   2.00106e+10 |
| energy            |   1130 |                      0.094  |                   1.21094e+10 |
| final_consumption |   1130 |                      0.2301 |                   2.68237e+10 |
| intermediates     |   1130 |                      0.477  |                   7.3719e+10  |

## Median Top-Product Share Contribution By Bin

| import_bin        |   median_top_1_product_share_contribution |   median_top_5_product_share_contribution |   median_top_10_product_share_contribution |
|:------------------|------------------------------------------:|------------------------------------------:|-------------------------------------------:|
| capital_goods     |                                    0      |                                    0      |                                     0.013  |
| energy            |                                    0.0437 |                                    0.0689 |                                     0.0798 |
| final_consumption |                                    0      |                                    0.0213 |                                     0.0337 |
| intermediates     |                                    0      |                                    0.0326 |                                     0.0601 |

## Median Leave-One-Bin-Out Contribution

Positive `product_gini_reduction_when_excluded` means the bin raises aggregate import concentration; negative means it dilutes aggregate concentration.

| import_bin        |   median_product_gini_without_bin |   median_product_gini_reduction_when_excluded |   median_top_10_product_share_reduction_when_excluded |
|:------------------|----------------------------------:|----------------------------------------------:|------------------------------------------------------:|
| capital_goods     |                            0.8656 |                                       -0.0069 |                                               -0.0291 |
| energy            |                            0.8448 |                                        0.0121 |                                                0.0393 |
| final_consumption |                            0.864  |                                       -0.0065 |                                               -0.0356 |
| intermediates     |                            0.8605 |                                       -0.0038 |                                               -0.1437 |

## Median Import Value Share By Mapping Status

| mapping_status   |   import_value_share |
|:-----------------|---------------------:|
| ambiguous        |               0.0203 |
| mapped           |               0.1291 |
| unmapped         |               0.0163 |

## Files

- Tables: `results/exercise_03_tables/`
- Figures: `results/exercise_03_figures/`
- Processed data: `data/processed/exercise_03_import_bin_concentration.parquet`, `data/processed/exercise_03_total_import_concentration.parquet`, `data/processed/exercise_03_import_bin_decomposition.parquet`

## Discussion Prompt

Which bins are internally concentrated, and which bins actually account for aggregate import concentration?
