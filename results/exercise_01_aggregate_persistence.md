# Exercise 1: Aggregate Persistence

Generated: 2026-06-02T07:22:24+00:00

This memo is intentionally descriptive. `exercises.md` should only be updated after discussion.

## Coverage

- Countries in Prof P-style panel: 156
- Years covered in processed data: 2000-2024
- Country-year-flow rows: 7554

## Median Concentration Across All Available Years

| flow    |   product_gini |   partner_gini |   product_partner_cell_gini |
|:--------|---------------:|---------------:|----------------------------:|
| Exports |          0.956 |          0.898 |                       0.961 |
| Imports |          0.885 |          0.901 |                       0.94  |

## Median Concentration In Latest Available Year (2024)

| flow    |   product_gini |   partner_gini |
|:--------|---------------:|---------------:|
| Exports |          0.959 |          0.899 |
| Imports |          0.89  |          0.905 |

## Files

- Tables: `results/exercise_01_tables/`
- Figures: `results/exercise_01_figures/`
- Processed data: `data/processed/concentration_all_years.parquet`

## Discussion Prompt

Does the aggregate puzzle still look real across years, or does it look driven by the original 2001 sample choice?
