# Exercise 11: Input-Output Linkages

Generated: 2026-05-22T12:16:57+00:00

This memo is intentionally descriptive. `exercises.md` should only be updated after discussion.

## Coverage

- Imported input concentration rows: 86990
- Top export sector exposure rows: 35571
- Country-year summary rows: 1128
- Countries: 33
- Years: 1988-2025
- Source details: `{"approved_bec_mapping": "data/processed/exercise_03_bec5_mapping_approved.csv", "chunk_rows": 500000, "finalize_only": false, "mode": "checkpointed_streaming", "partial_dir": "data/processed/exercise_11_file_aggregates", "partial_files": {"export_sectors": 1130, "import_cells": 1130, "mapping_coverage": 1130}}`

## Import Concentration By BEC Bin

| import_bin            |   rows |   median_product_gini |   median_top_supplier_share |   median_source_hhi |
|:----------------------|-------:|----------------------:|----------------------------:|--------------------:|
| capital_goods         |  13979 |                0.6745 |                      0.3608 |              0.2001 |
| energy                |   8798 |                0.4027 |                      0.4707 |              0.3129 |
| final_consumption     |  22462 |                0.6602 |                      0.3243 |              0.1706 |
| intermediates         |  28587 |                0.7479 |                      0.2836 |              0.1415 |
| unmapped_or_ambiguous |  13164 |                0.4631 |                      0.409  |              0.2489 |

## Top Export Sector Imported-Input Exposure

|                                             |   median_country_year |
|:--------------------------------------------|----------------------:|
| weighted_top_sector_input_product_gini      |                0.762  |
| weighted_top_sector_top_supplier_share      |                0.2854 |
| weighted_top_sector_source_hhi              |                0.1494 |
| median_top_sector_matched_requirement_share |                0.1062 |

## Median Mapping Coverage

| flow    | io_mapping_status    |   trade_value_share |
|:--------|:---------------------|--------------------:|
| Exports | mapped_version_exact |              1      |
| Imports | mapped_version_exact |              0.0424 |

## Files

- Tables: `results/exercise_11_tables/`
- Figures: `results/exercise_11_figures/`
- Processed data: `data/processed/exercise_11_imported_input_concentration.parquet`, `data/processed/exercise_11_top_export_input_exposure.parquet`

## Discussion Prompt

Do concentrated intermediate imports map to the sectors where countries, especially India, have top export exposure?
