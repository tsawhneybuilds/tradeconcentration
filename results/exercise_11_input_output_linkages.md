# Exercise 11: Input-Output Linkages

Generated: 2026-05-19T14:36:46+00:00

This memo is intentionally descriptive. `exercises.md` should only be updated after discussion.

## Coverage

- Imported input concentration rows: 86911
- Top export sector exposure rows: 35571
- Country-year summary rows: 1128
- Countries: 33
- Years: 1988-2025
- Source details: `{"approved_bec_mapping": "data/processed/exercise_03_bec5_mapping_approved.csv", "chunk_rows": 250000, "finalize_only": true, "mode": "checkpointed_streaming", "partial_dir": "data/processed/exercise_11_file_aggregates", "partial_files": {"export_sectors": 1130, "import_cells": 1130, "mapping_coverage": 1130}}`

## Import Concentration By BEC Bin

| import_bin            |   rows |   median_product_gini |   median_top_supplier_share |   median_source_hhi |
|:----------------------|-------:|----------------------:|----------------------------:|--------------------:|
| capital_goods         |  13943 |                0.6748 |                      0.3604 |              0.1995 |
| energy                |   8798 |                0.4027 |                      0.4707 |              0.3129 |
| final_consumption     |  22427 |                0.6593 |                      0.3256 |              0.1714 |
| intermediates         |  28587 |                0.748  |                      0.2839 |              0.1417 |
| unmapped_or_ambiguous |  13156 |                0.4617 |                      0.4092 |              0.2493 |

## Top Export Sector Imported-Input Exposure

|                                             |   median_country_year |
|:--------------------------------------------|----------------------:|
| weighted_top_sector_input_product_gini      |                0.7617 |
| weighted_top_sector_top_supplier_share      |                0.2855 |
| weighted_top_sector_source_hhi              |                0.1496 |
| median_top_sector_matched_requirement_share |                0.1063 |

## Median Mapping Coverage

| flow    | io_mapping_status    |   trade_value_share |
|:--------|:---------------------|--------------------:|
| Exports | mapped_version_exact |              0.9766 |
| Exports | unmapped             |              0.0258 |
| Imports | mapped_version_exact |              0.0415 |
| Imports | unmapped             |              0.0151 |

## Files

- Tables: `results/exercise_11_tables/`
- Figures: `results/exercise_11_figures/`
- Processed data: `data/processed/exercise_11_imported_input_concentration.parquet`, `data/processed/exercise_11_top_export_input_exposure.parquet`

## Discussion Prompt

Do concentrated intermediate imports map to the sectors where countries, especially India, have top export exposure?
