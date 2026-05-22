# Exercise 1: Aggregate Persistence

Generated: 2026-05-22T08:48:03+00:00

This memo is intentionally descriptive. `exercises.md` should only be updated after discussion.

## Coverage

- Countries in Prof P-style panel: 33
- Years covered in processed data: 1988-2025
- Country-year-flow rows: 2258

## Median Concentration Across All Available Years

| flow    |   product_gini |   partner_gini |   product_partner_cell_gini |
|:--------|---------------:|---------------:|----------------------------:|
| Exports |          0.907 |          0.897 |                       0.949 |
| Imports |          0.854 |          0.901 |                       0.94  |

## Median Concentration In Latest Available Year (2025)

| flow    |   product_gini |   partner_gini |
|:--------|---------------:|---------------:|
| Exports |          0.926 |          0.901 |
| Imports |          0.879 |          0.905 |

## Files

- Tables: `results/exercise_01_tables/`
- Figures: `results/exercise_01_figures/`
- Processed data: `data/processed/concentration_all_years.parquet`

## Discussion Prompt

Does the aggregate puzzle still look real across years, or does it look driven by the original 2001 sample choice?
