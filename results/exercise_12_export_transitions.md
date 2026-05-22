# Exercise 12: Export Transition Exercise

Generated: 2026-05-22T10:55:06+00:00

This memo is an accounting exercise, not a regression. It separates where export growth came from: existing top items, existing non-top items, new items, and contractions.

## Coverage

- Growth decomposition rows: 15827
- Size transition rows: 16
- Product destination/region transition rows: 22
- HS cross-revision diagnostic rows: 0
- Excluded base value in HS cross-revision diagnostics: 0
- Source details: `{"country_sample": "prof_p_33", "hs_bulk_files_processed": 1130, "mode": "checkpointed", "partial_dir": "data/processed/exercise_12_file_aggregates"}`

## Median Net Contribution Shares

| dimension            |   horizon | driver_category     |   contribution_share |
|:---------------------|----------:|:--------------------|---------------------:|
| partner              |         5 | existing_non_top_10 |               0.334  |
| partner              |         5 | existing_top_10     |               0.6239 |
| partner              |         5 | new_item            |               0.0016 |
| partner              |        10 | existing_non_top_10 |               0.3592 |
| partner              |        10 | existing_top_10     |               0.5934 |
| partner              |        10 | new_item            |               0.0055 |
| product              |         5 | existing_non_top_10 |               0.6241 |
| product              |         5 | existing_top_10     |               0.1495 |
| product              |         5 | new_item            |               0.1953 |
| product              |        10 | existing_non_top_10 |               0.6084 |
| product              |        10 | existing_top_10     |               0.0977 |
| product              |        10 | new_item            |               0.2542 |
| product_partner_cell |         5 | existing_non_top_10 |               0.5489 |
| product_partner_cell |         5 | existing_top_10     |               0.0108 |
| product_partner_cell |         5 | new_item            |               0.4104 |
| product_partner_cell |        10 | existing_non_top_10 |               0.481  |
| product_partner_cell |        10 | existing_top_10     |              -0.0053 |
| product_partner_cell |        10 | new_item            |               0.4963 |

## Median Gross Contribution Shares

No gross contribution summary was produced.

## Interpretation Limits

The main HS6 product transition is conservative: product comparisons across different HS revisions are excluded and reported in `hs_revision_pair_diagnostics.csv`. HS4, HS2, and CPA-sector outputs are robustness views for product-code instability, not replacements for HS6 detail.

Net growth can hide churn, so the gross table should be read alongside the net table. Gross positive growth shows expanding/new items; gross contraction shows shrinking or exiting items.

Destination and region transitions remain descriptive. The state table reports `unknown_partner_region_share` and `region_transition_reliability`; region-transition claims should be discounted when the unknown-region share is high.

## Files

- Tables: `results/exercise_12_tables/`
- Figures: `results/exercise_12_figures/`
- Processed data: `data/processed/exercise_12_growth_decomposition.parquet`
- Net decomposition: `results/exercise_12_tables/growth_decomposition_net.csv`
- Gross decomposition: `results/exercise_12_tables/growth_decomposition_gross.csv`
- Detailed transitions: `results/exercise_12_tables/transition_matrices_detailed.csv`
- HS revision diagnostics: `results/exercise_12_tables/hs_revision_pair_diagnostics.csv`

## Discussion Prompt

Does future export growth mostly come from already-top items, smaller incumbents, or new product/partner cells?
