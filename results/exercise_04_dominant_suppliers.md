# Exercise 4: Dominant Supplier By Product

Generated: 2026-05-19T12:36:29+00:00

This memo is intentionally descriptive. `exercises.md` should only be updated after discussion.

## Coverage

- Importer-product-year rows: 5524696
- Importer-year rows: 1130
- Countries: 33
- Years: 1988-2025
- Source details: `{"chunk_rows": 500000, "finalize_only": true, "hs_bulk_files_seen": 1130, "mode": "checkpointed_streaming", "partial_dir": "data/processed/exercise_04_file_aggregates", "partial_files": 1130}`

## Median Importer-Year Measures

|                                                |   median_across_importer_years |
|:-----------------------------------------------|-------------------------------:|
| weighted_mean_top_supplier_share               |                         0.4568 |
| weighted_mean_source_hhi                       |                         0.318  |
| median_top_supplier_share                      |                         0.5024 |
| share_products_top_supplier_ge_75              |                         0.2181 |
| import_value_share_products_top_supplier_ge_75 |                         0.1116 |

## Files

- Tables: `results/exercise_04_tables/`
- Figures: `results/exercise_04_figures/`
- Processed data: `data/processed/exercise_04_dominant_supplier_by_product.parquet`

## Discussion Prompt

Do countries import many products from one dominant supplier, or is import concentration still high even when suppliers within products are diffuse?
