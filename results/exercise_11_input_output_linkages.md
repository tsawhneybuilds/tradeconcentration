# Exercise 11: Input-Output Linkages

Generated: 2026-05-26T04:13:46+00:00

This memo is intentionally descriptive. `exercises.md` should only be updated after discussion.

## Coverage

- Imported input concentration rows: 142593
- Top export sector exposure rows: 57859
- Country-year summary rows: 1911
- Countries: 60
- Years: 1988-2025
- Source details: `{"approved_bec_mapping": "data/processed/exercise_03_bec5_mapping_approved.csv", "chunk_rows": 100000, "finalize_only": false, "mode": "checkpointed_streaming", "partial_dir": "data/processed/samples/rd2_countries/checkpoints/exercise_11_file_aggregates", "partial_files": {"export_sectors": 1931, "import_cells": 1931, "mapping_coverage": 1931}}`

## Import Concentration By BEC Bin

| import_bin            |   rows |   median_product_gini |   median_top_supplier_share |   median_source_hhi |
|:----------------------|-------:|----------------------:|----------------------------:|--------------------:|
| capital_goods         |  22285 |                0.686  |                      0.3788 |              0.2145 |
| energy                |  14310 |                0.3976 |                      0.5254 |              0.3681 |
| final_consumption     |  36515 |                0.6748 |                      0.3607 |              0.1994 |
| intermediates         |  48042 |                0.7693 |                      0.3159 |              0.1665 |
| unmapped_or_ambiguous |  21441 |                0.4623 |                      0.4544 |              0.2915 |

## Top Export Sector Imported-Input Exposure

|                                             |   median_country_year |
|:--------------------------------------------|----------------------:|
| weighted_top_sector_input_product_gini      |                0.7685 |
| weighted_top_sector_top_supplier_share      |                0.2899 |
| weighted_top_sector_source_hhi              |                0.1542 |
| median_top_sector_matched_requirement_share |                0.0613 |

## Median Mapping Coverage

| flow    | io_mapping_status    |   trade_value_share |
|:--------|:---------------------|--------------------:|
| Exports | mapped_version_exact |              1      |
| Imports | mapped_version_exact |              0.0427 |

## Files

- Tables: `results/exercise_11_tables/`
- Figures: `results/exercise_11_figures/`
- Processed data: `data/processed/exercise_11_imported_input_concentration.parquet`, `data/processed/exercise_11_top_export_input_exposure.parquet`

## Discussion Prompt

Do concentrated intermediate imports map to the sectors where countries, especially India, have top export exposure?
