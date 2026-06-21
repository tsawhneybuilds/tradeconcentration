# Exercise 3: Import Bin Exercise

Generated: 2026-05-25T11:55:43+00:00

This memo is intentionally descriptive. `exercises.md` should only be updated after discussion.

## Coverage

- Country-year-bin rows: 9580
- Countries: 60
- Years: 1988-2025
- Approved mapping: `data/processed/exercise_03_bec5_mapping_approved.csv`
- Source details: `{"chunk_rows": 500000, "finalize_only": false, "hs_bulk_files_seen": 1931, "mode": "checkpointed_streaming", "partial_dir": "data/processed/samples/rd2_countries/checkpoints/exercise_03_file_aggregates", "partial_files": {"mapping_coverage": 1931, "product_values": 1931}}`

## Median Concentration By Import Bin

| import_bin        |   rows |   median_product_gini |   median_top_1_product_share |   median_active_products |
|:------------------|-------:|----------------------:|-----------------------------:|-------------------------:|
| capital_goods     |   1916 |                0.8079 |                       0.0866 |                      591 |
| energy            |   1916 |                0.8869 |                       0.5632 |                       25 |
| final_consumption |   1916 |                0.8437 |                       0.1055 |                     1187 |
| intermediates     |   1916 |                0.8624 |                       0.0601 |                     2896 |

## Median Aggregate Import Concentration

|                      |   median_country_year |
|:---------------------|----------------------:|
| product_gini         |                0.8709 |
| top_1_product_share  |                0.0723 |
| top_5_product_share  |                0.1886 |
| top_10_product_share |                0.2561 |
| active_products      |             4812.5    |

## Median Import Value Share By Bin

| import_bin        |   rows |   median_import_value_share |   median_total_imports_in_bin |
|:------------------|-------:|----------------------------:|------------------------------:|
| capital_goods     |   1916 |                      0.1342 |                   8.33648e+09 |
| energy            |   1916 |                      0.1127 |                   4.63233e+09 |
| final_consumption |   1916 |                      0.2265 |                   1.11548e+10 |
| intermediates     |   1916 |                      0.4803 |                   2.81457e+10 |

## Median Top-Product Share Contribution By Bin

| import_bin        |   median_top_1_product_share_contribution |   median_top_5_product_share_contribution |   median_top_10_product_share_contribution |
|:------------------|------------------------------------------:|------------------------------------------:|-------------------------------------------:|
| capital_goods     |                                    0      |                                    0      |                                     0.0119 |
| energy            |                                    0.0544 |                                    0.0891 |                                     0.0997 |
| final_consumption |                                    0      |                                    0.0215 |                                     0.0377 |
| intermediates     |                                    0      |                                    0.0426 |                                     0.0741 |

## Median Leave-One-Bin-Out Contribution

Positive `product_gini_reduction_when_excluded` means the bin raises aggregate import concentration; negative means it dilutes aggregate concentration.

| import_bin        |   median_product_gini_without_bin |   median_product_gini_reduction_when_excluded |   median_top_10_product_share_reduction_when_excluded |
|:------------------|----------------------------------:|----------------------------------------------:|------------------------------------------------------:|
| capital_goods     |                            0.8779 |                                       -0.0075 |                                               -0.0315 |
| energy            |                            0.8537 |                                        0.0138 |                                                0.0518 |
| final_consumption |                            0.8751 |                                       -0.0044 |                                               -0.0413 |
| intermediates     |                            0.8702 |                                       -0.0018 |                                               -0.1351 |

## Median Import Value Share By Mapping Status

| mapping_status   |   import_value_share |
|:-----------------|---------------------:|
| ambiguous        |               0.0183 |
| mapped           |               0.1342 |
| unmapped         |               0.0175 |

## Files

- Tables: `results/exercise_03_tables/`
- Figures: `results/exercise_03_figures/`
- Processed data: `data/processed/exercise_03_import_bin_concentration.parquet`, `data/processed/exercise_03_total_import_concentration.parquet`, `data/processed/exercise_03_import_bin_decomposition.parquet`

## Discussion Prompt

Which bins are internally concentrated, and which bins actually account for aggregate import concentration?
