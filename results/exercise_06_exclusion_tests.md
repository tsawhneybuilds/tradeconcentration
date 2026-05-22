# Exercise 6: Oil / High-Unit-Value Exclusion Tests

Generated: 2026-05-22T08:48:05+00:00

This memo is intentionally descriptive. `exercises.md` should only be updated after discussion.

## Exclusion Definitions

- `baseline`: no HS2 product categories are removed.
- `oil_only`: excludes HS27, mineral fuels, oils, petroleum, and related products.
- `oil_aircraft`: excludes HS27 mineral fuels/oil/petroleum and HS88 aircraft/spacecraft.
- `oil_aircraft_precious`: excludes HS27 mineral fuels/oil/petroleum, HS71 precious stones/metals, and HS88 aircraft/spacecraft.
- `full_exclusion`: excludes HS27 mineral fuels/oil/petroleum; HS71 precious stones/metals; HS88 aircraft/spacecraft; HS89 ships/boats/floating structures; and HS93 arms/ammunition.

HS87 vehicles and parts are intentionally not excluded here because the chapter mixes finished autos with parts and is not cleanly a high-unit-value category.

## Median Product Gini And Trade Share Removed

|                                      |   product_gini |   trade_share_removed |
|:-------------------------------------|---------------:|----------------------:|
| ('Exports', 'baseline')              |          0.907 |                 0     |
| ('Exports', 'full_exclusion')        |          0.901 |                 0.086 |
| ('Exports', 'oil_aircraft')          |          0.904 |                 0.053 |
| ('Exports', 'oil_aircraft_precious') |          0.901 |                 0.073 |
| ('Exports', 'oil_only')              |          0.904 |                 0.04  |
| ('Imports', 'baseline')              |          0.854 |                 0     |
| ('Imports', 'full_exclusion')        |          0.836 |                 0.139 |
| ('Imports', 'oil_aircraft')          |          0.839 |                 0.115 |
| ('Imports', 'oil_aircraft_precious') |          0.837 |                 0.133 |
| ('Imports', 'oil_only')              |          0.84  |                 0.099 |

## Files

- Tables: `results/exercise_06_tables/`
- Figures: `results/exercise_06_figures/`
- Processed data: `data/processed/concentration_exclusions_all_years.parquet`

## Discussion Prompt

Are oil and high-unit-value/lumpy categories only partial explanations, or do they explain most of the modern concentration pattern?
