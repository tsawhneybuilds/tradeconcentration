# Exercise 4: Dominant Supplier By Product

Generated: 2026-05-27T04:33:19+00:00

This memo is intentionally descriptive. `exercises.md` should only be updated after discussion.

## Coverage

- Importer-product-year rows: 8697864
- Importer-year rows: 1916
- Countries: 60
- Years: 1988-2025
- Source details: `{"chunk_rows": 300000, "finalize_only": false, "hs_bulk_files_seen": 1931, "mode": "checkpointed_streaming", "partial_dir": "data/processed/samples/rd2_countries/checkpoints/exercise_04_file_aggregates", "partial_files": 1931}`

## Median Importer-Year Measures

|                                                |   median_across_importer_years |
|:-----------------------------------------------|-------------------------------:|
| weighted_mean_top_supplier_share               |                         0.4875 |
| weighted_mean_source_hhi                       |                         0.352  |
| median_top_supplier_share                      |                         0.544  |
| share_products_top_supplier_ge_75              |                         0.2683 |
| import_value_share_products_top_supplier_ge_75 |                         0.1497 |

## Files

- Tables: `results/exercise_04_tables/`
- Figures: `results/exercise_04_figures/`
- Processed data: `data/processed/exercise_04_dominant_supplier_by_product.parquet`

## Discussion Prompt

Do countries import many products from one dominant supplier, or is import concentration still high even when suppliers within products are diffuse?
