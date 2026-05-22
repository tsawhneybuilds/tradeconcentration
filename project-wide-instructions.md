# Project-Wide Instructions

## Trade Data Rules

- Always exclude HS6 code `999999` from all analyses, graphs, tables, regressions, cached panels, checkpoint files, generated site data, and downloadable outputs.
- Treat `999999` as "Commodities not specified", not as a real product category.
- Exclude `999999` before computing concentration measures, shares, bins, leave-one-out statistics, export probabilities, or model inputs.
- Do not only filter `999999` at the final table or graph stage, because it can affect totals, ranks, Gini values, shares, and regression samples.
