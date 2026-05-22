# Exercise 3: Import Bin Exercise

Generated: 2026-05-22T08:48:47+00:00

This memo is intentionally descriptive. `exercises.md` should only be updated after discussion.

## Coverage

- Country-year-bin rows: 5650
- Countries: 33
- Years: 1988-2025
- Approved mapping: `data/processed/exercise_03_bec5_mapping_approved.csv`
- Source details: `{"hs_bulk_files_processed": 1130, "mode": "streaming_all_exercises_checkpointed", "partial_dir": "data/processed/exercise_03_file_aggregates"}`

## Median Concentration By Import Bin

| import_bin        |   rows |   median_product_gini |   median_top_1_product_share |   median_active_products |
|:------------------|-------:|----------------------:|-----------------------------:|-------------------------:|
| capital_goods     |   1130 |                0.801  |                       0.0885 |                    599   |
| energy            |   1130 |                0.8837 |                       0.5403 |                     27   |
| final_consumption |   1130 |                0.8229 |                       0.0995 |                   1219   |
| intermediates     |   1130 |                0.8481 |                       0.0501 |                   2992.5 |

## Median Aggregate Import Concentration

|                      |   median_country_year |
|:---------------------|----------------------:|
| product_gini         |                0.8542 |
| top_1_product_share  |                0.0586 |
| top_5_product_share  |                0.1575 |
| top_10_product_share |                0.2192 |
| active_products      |             4959      |

## Median Import Value Share By Bin

| import_bin        |   rows |   median_import_value_share |   median_total_imports_in_bin |
|:------------------|-------:|----------------------------:|------------------------------:|
| capital_goods     |   1130 |                      0.1394 |                   2.00132e+10 |
| energy            |   1130 |                      0.0959 |                   1.21094e+10 |
| final_consumption |   1130 |                      0.2406 |                   2.68934e+10 |
| intermediates     |   1130 |                      0.4863 |                   7.37582e+10 |

## Median Top-Product Share Contribution By Bin

| import_bin        |   median_top_1_product_share_contribution |   median_top_5_product_share_contribution |   median_top_10_product_share_contribution |
|:------------------|------------------------------------------:|------------------------------------------:|-------------------------------------------:|
| capital_goods     |                                    0      |                                    0      |                                     0.014  |
| energy            |                                    0.0486 |                                    0.0729 |                                     0.0825 |
| final_consumption |                                    0      |                                    0.0231 |                                     0.0362 |
| intermediates     |                                    0      |                                    0.0368 |                                     0.0631 |

## Median Leave-One-Bin-Out Contribution

Positive `product_gini_reduction_when_excluded` means the bin raises aggregate import concentration; negative means it dilutes aggregate concentration.

| import_bin        |   median_product_gini_without_bin |   median_product_gini_reduction_when_excluded |   median_top_10_product_share_reduction_when_excluded |
|:------------------|----------------------------------:|----------------------------------------------:|------------------------------------------------------:|
| capital_goods     |                            0.8594 |                                       -0.0064 |                                               -0.0269 |
| energy            |                            0.8401 |                                        0.013  |                                                0.0432 |
| final_consumption |                            0.8587 |                                       -0.006  |                                               -0.0322 |
| intermediates     |                            0.8528 |                                       -0.0004 |                                               -0.1326 |

## Median Import Value Share By Mapping Status

| mapping_status   |   import_value_share |
|:-----------------|---------------------:|
| ambiguous        |               0.0208 |
| mapped           |               0.1315 |
| unmapped         |               0.0164 |

## Files

- Tables: `results/exercise_03_tables/`
- Figures: `results/exercise_03_figures/`
- Processed data: `data/processed/exercise_03_import_bin_concentration.parquet`, `data/processed/exercise_03_total_import_concentration.parquet`, `data/processed/exercise_03_import_bin_decomposition.parquet`

## Discussion Prompt

Which bins are internally concentrated, and which bins actually account for aggregate import concentration?
