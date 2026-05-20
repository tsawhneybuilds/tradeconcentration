# Exercise 10: Random Benchmark / Null Model

Generated: 2026-05-18T08:58:39+00:00

This memo is intentionally descriptive. `exercises.md` should only be updated after discussion.

## Median Actual Versus Benchmark Measures

```text
                              actual_gini  sim_gini_median  actual_minus_sim_median_gini  actual_gini_percentile
dimension            flow                                                                                       
partner              Exports        0.897            0.498                         0.400                     1.0
                     Imports        0.901            0.498                         0.404                     1.0
product              Exports        0.910            0.500                         0.410                     1.0
                     Imports        0.859            0.500                         0.359                     1.0
product_partner_cell Exports        0.950            0.500                         0.450                     1.0
                     Imports        0.943            0.500                         0.443                     1.0
```

## Share Of Country-Year-Flow Observations Above 95th Benchmark Percentile

```text
dimension             flow   
partner               Exports    1.0
                      Imports    1.0
product               Exports    1.0
                      Imports    1.0
product_partner_cell  Exports    1.0
                      Imports    1.0
```

## Share Using Approximate Active-Count Simulation

```text
dimension
partner                 0.000
product                 0.992
product_partner_cell    1.000
```

## Benchmark Design

- Runs separately for products, partners, and product-partner cells.
- Preserves each country-year-flow total trade value.
- Preserves each country-year-flow active item count within the benchmarked dimension.
- Uses a symmetric Dirichlet random-allocation null, implemented as exponential random weights normalized to the observed total.
- Does not use naive relabeling, because relabeling preserves the same Gini by construction.
- Large active-count groups can reuse a nearby/capped simulation count with analytic centering for Gini and top-share expectations; see `results/exercise_10_tables/benchmark_validation.json`.

## Files

- Tables: `results/exercise_10_tables/`
- Figures: `results/exercise_10_figures/`
- Processed data: `data/processed/random_benchmark_all_years.parquet`

## Discussion Prompt

Is actual concentration still unusually high after preserving scale and sparsity, or is much of it explained by random allocation over a sparse set of active products, partners, and cells?
