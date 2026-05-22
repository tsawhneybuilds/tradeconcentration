# Exercise 4: Dominant Supplier By Product

Generated: 2026-05-22T08:51:24+00:00

This memo is intentionally descriptive. `exercises.md` should only be updated after discussion.

## Coverage

- Importer-product-year rows: 5568474
- Importer-year rows: 1130
- Countries: 33
- Years: 1988-2025
- Source details: `{"hs_bulk_files_processed": 1130, "mode": "streaming_all_exercises_checkpointed", "partial_dir": "data/processed/exercise_04_file_aggregates"}`

## Median Importer-Year Measures

|                                                |   median_across_importer_years |
|:-----------------------------------------------|-------------------------------:|
| weighted_mean_top_supplier_share               |                         0.4556 |
| weighted_mean_source_hhi                       |                         0.3172 |
| median_top_supplier_share                      |                         0.502  |
| share_products_top_supplier_ge_75              |                         0.2177 |
| import_value_share_products_top_supplier_ge_75 |                         0.1106 |

## Files

- Tables: `results/exercise_04_tables/`
- Figures: `results/exercise_04_figures/`
- Processed data: `data/processed/exercise_04_dominant_supplier_by_product.parquet`

## Discussion Prompt

Do countries import many products from one dominant supplier, or is import concentration still high even when suppliers within products are diffuse?
