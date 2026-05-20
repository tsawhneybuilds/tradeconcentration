# Exercise 10: HS2-Preserving Product Random Benchmark

Generated: 2026-05-18T11:10:34+00:00

This memo is intentionally descriptive. `exercises.md` should only be updated after discussion.

## Benchmark Design

- Uses real UN Comtrade HS6 annual product-partner data.
- Aggregates to HS6 product totals within each country-year-flow.
- Preserves each country-year-flow total trade value.
- Preserves each HS2 sector total within each country-year-flow.
- Preserves the active HS6 product count inside each HS2 sector.
- Randomizes HS6 product shares only within HS2 sectors.
- Uses 1,000 simulations per country-year-flow with fixed seed `20260518`.

## Median Actual Versus HS2-Preserved Benchmark

```text
         actual_gini  sim_gini_median  actual_minus_sim_median_gini  actual_gini_percentile
flow                                                                                       
Exports        0.910            0.750                         0.148                     1.0
Imports        0.859            0.715                         0.142                     1.0
```

## Latest Available Year (2025)

```text
         actual_gini  sim_gini_median  actual_minus_sim_median_gini  actual_gini_percentile
flow                                                                                       
Exports         0.93            0.783                         0.138                     1.0
Imports         0.88            0.726                         0.150                     1.0
```

## Share Of Country-Year-Flow Observations Above 95th Benchmark Percentile

```text
flow
Exports    1.0
Imports    1.0
```

## Files

- Tables: `results/exercise_10_tables/`
- Figures: `results/exercise_10_figures/`
- Processed data: `data/processed/random_benchmark_all_years.parquet`

## Note

The earlier active-count-only benchmark has been backed up as `random_benchmark_active_count_null_all_years.*`.
The HS2-preserving benchmark is the main Exercise 10 result because it matches the planned non-naive null model.
