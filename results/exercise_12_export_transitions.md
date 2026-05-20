# Exercise 12: Export Transition Exercise

Generated: 2026-05-19T17:18:48+00:00

This memo is an accounting exercise, not a regression. It separates where export growth came from: existing top items, existing non-top items, new items, and contractions.

## Coverage

- Growth decomposition rows: 5701
- Size transition rows: 216166
- Product destination/region transition rows: 17
- HS cross-revision diagnostic rows: 3374
- Excluded base value in HS cross-revision diagnostics: 822,277,645,988,687
- Source details: `{"debug_run": false, "dependency_engine": "duckdb", "finalize_only": true, "fresh": false, "max_files": null, "mode": "exercises_02_12_duckdb_checkpointed", "partial_dir": "data/processed/exercise_02_12_file_aggregates", "partial_files_used": 1130, "workers": 4}`

## Median Net Contribution Shares

| dimension            |   horizon | driver_category     |   contribution_share |
|:---------------------|----------:|:--------------------|---------------------:|
| partner              |         5 | existing_non_top_10 |               0.3368 |
| partner              |         5 | existing_top_10     |               0.623  |
| partner              |         5 | new_item            |               0.002  |
| partner              |        10 | existing_non_top_10 |               0.3683 |
| partner              |        10 | existing_top_10     |               0.5813 |
| partner              |        10 | new_item            |               0.007  |
| product              |         5 | existing_non_top_10 |               0.7875 |
| product              |         5 | existing_top_10     |               0.172  |
| product              |         5 | new_item            |               0.0278 |
| product_partner_cell |         5 | existing_non_top_10 |               0.3466 |
| product_partner_cell |         5 | existing_top_10     |               0.0012 |
| product_partner_cell |         5 | new_item            |               0.6433 |

## Median Gross Contribution Shares

| dimension            |   horizon | accounting_type   | driver_category        |   contribution_share |
|:---------------------|----------:|:------------------|:-----------------------|---------------------:|
| partner              |         5 | gross_contraction | exited_non_top_10      |               0.0124 |
| partner              |         5 | gross_contraction | exited_non_top_1pct    |               0.0166 |
| partner              |         5 | gross_contraction | exited_non_top_5pct    |               0.0124 |
| partner              |         5 | gross_contraction | exited_top_10          |               0.5369 |
| partner              |         5 | gross_contraction | exited_top_1pct        |               0.6612 |
| partner              |         5 | gross_contraction | exited_top_5pct        |               0.5478 |
| partner              |         5 | gross_contraction | shrinking_non_top_10   |               0.4554 |
| partner              |         5 | gross_contraction | shrinking_non_top_1pct |               0.7597 |
| partner              |         5 | gross_contraction | shrinking_non_top_5pct |               0.4351 |
| partner              |         5 | gross_contraction | shrinking_top_10       |               0.4583 |
| partner              |         5 | gross_contraction | shrinking_top_1pct     |               0.2635 |
| partner              |         5 | gross_contraction | shrinking_top_5pct     |               0.4789 |
| partner              |         5 | gross_positive    | existing_non_top_10    |               0.3987 |
| partner              |         5 | gross_positive    | existing_non_top_1pct  |               0.6826 |
| partner              |         5 | gross_positive    | existing_non_top_5pct  |               0.3764 |
| partner              |         5 | gross_positive    | existing_top_10        |               0.5622 |
| partner              |         5 | gross_positive    | existing_top_1pct      |               0.2924 |
| partner              |         5 | gross_positive    | existing_top_5pct      |               0.5817 |
| partner              |         5 | gross_positive    | new_item               |               0.0028 |
| partner              |        10 | gross_contraction | exited_non_top_10      |               0.0499 |
| partner              |        10 | gross_contraction | exited_non_top_1pct    |               0.107  |
| partner              |        10 | gross_contraction | exited_non_top_5pct    |               0.0543 |
| partner              |        10 | gross_contraction | exited_top_10          |               0.6241 |
| partner              |        10 | gross_contraction | exited_top_1pct        |               0.5711 |
| partner              |        10 | gross_contraction | exited_top_5pct        |               0.6288 |
| partner              |        10 | gross_contraction | shrinking_non_top_10   |               0.367  |
| partner              |        10 | gross_contraction | shrinking_non_top_1pct |               0.6477 |
| partner              |        10 | gross_contraction | shrinking_non_top_5pct |               0.361  |
| partner              |        10 | gross_contraction | shrinking_top_10       |               0.4671 |
| partner              |        10 | gross_contraction | shrinking_top_1pct     |               0.269  |
| partner              |        10 | gross_contraction | shrinking_top_5pct     |               0.4853 |
| partner              |        10 | gross_positive    | existing_non_top_10    |               0.3927 |
| partner              |        10 | gross_positive    | existing_non_top_1pct  |               0.6816 |
| partner              |        10 | gross_positive    | existing_non_top_5pct  |               0.3811 |
| partner              |        10 | gross_positive    | existing_top_10        |               0.5566 |
| partner              |        10 | gross_positive    | existing_top_1pct      |               0.2709 |
| partner              |        10 | gross_positive    | existing_top_5pct      |               0.5714 |
| partner              |        10 | gross_positive    | new_item               |               0.0064 |
| product              |         5 | gross_contraction | exited_non_top_10      |               0.0082 |
| product              |         5 | gross_contraction | exited_non_top_1pct    |               0.0078 |
| product              |         5 | gross_contraction | exited_non_top_5pct    |               0.005  |
| product              |         5 | gross_contraction | exited_top_10          |               0.1782 |
| product              |         5 | gross_contraction | exited_top_1pct        |               0.1179 |
| product              |         5 | gross_contraction | exited_top_5pct        |               0.0833 |
| product              |         5 | gross_contraction | shrinking_non_top_10   |               0.5797 |
| product              |         5 | gross_contraction | shrinking_non_top_1pct |               0.9333 |
| product              |         5 | gross_contraction | shrinking_non_top_5pct |               0.5636 |
| product              |         5 | gross_contraction | shrinking_top_10       |               0.5063 |
| product              |         5 | gross_contraction | shrinking_top_1pct     |               0.3203 |
| product              |         5 | gross_contraction | shrinking_top_5pct     |               0.546  |
| product              |         5 | gross_positive    | existing_non_top_10    |               0.4201 |
| product              |         5 | gross_positive    | existing_non_top_1pct  |               0.8047 |
| product              |         5 | gross_positive    | existing_non_top_5pct  |               0.5152 |
| product              |         5 | gross_positive    | existing_top_10        |               0.5751 |
| product              |         5 | gross_positive    | existing_top_1pct      |               0.2298 |
| product              |         5 | gross_positive    | existing_top_5pct      |               0.4819 |
| product              |         5 | gross_positive    | new_item               |               0.0039 |
| product              |        10 | gross_contraction | exited_non_top_10      |               0.0188 |
| product              |        10 | gross_contraction | exited_non_top_1pct    |               0.018  |
| product              |        10 | gross_contraction | exited_non_top_5pct    |               0.0109 |
| product              |        10 | gross_contraction | exited_top_10          |               0.1548 |
| product              |        10 | gross_contraction | exited_top_1pct        |               0.1326 |
| product              |        10 | gross_contraction | exited_top_5pct        |               0.0727 |
| product              |        10 | gross_contraction | shrinking_non_top_10   |               0.6068 |
| product              |        10 | gross_contraction | shrinking_non_top_1pct |               0.9998 |
| product              |        10 | gross_contraction | shrinking_non_top_5pct |               0.5929 |
| product              |        10 | gross_contraction | shrinking_top_10       |               0.518  |
| product              |        10 | gross_contraction | shrinking_top_1pct     |               0.3493 |
| product              |        10 | gross_contraction | shrinking_top_5pct     |               0.5635 |
| product              |        10 | gross_positive    | existing_non_top_10    |               0.4195 |
| product              |        10 | gross_positive    | existing_non_top_1pct  |               0.8106 |
| product              |        10 | gross_positive    | existing_non_top_5pct  |               0.5336 |
| product              |        10 | gross_positive    | existing_top_10        |               0.5717 |
| product              |        10 | gross_positive    | existing_top_1pct      |               0.1974 |
| product              |        10 | gross_positive    | existing_top_5pct      |               0.4577 |
| product              |        10 | gross_positive    | new_item               |               0.0076 |
| product_partner_cell |         5 | gross_contraction | exited_non_top_10      |               0.0732 |
| product_partner_cell |         5 | gross_contraction | exited_non_top_1pct    |               0.0492 |
| product_partner_cell |         5 | gross_contraction | exited_non_top_5pct    |               0.0269 |
| product_partner_cell |         5 | gross_contraction | exited_top_10          |               0.107  |
| product_partner_cell |         5 | gross_contraction | exited_top_1pct        |               0.0642 |
| product_partner_cell |         5 | gross_contraction | exited_top_5pct        |               0.0671 |
| product_partner_cell |         5 | gross_contraction | shrinking_non_top_10   |               0.7397 |
| product_partner_cell |         5 | gross_contraction | shrinking_non_top_1pct |               0.4352 |
| product_partner_cell |         5 | gross_contraction | shrinking_non_top_5pct |               0.1756 |
| product_partner_cell |         5 | gross_contraction | shrinking_top_10       |               0.1317 |
| product_partner_cell |         5 | gross_contraction | shrinking_top_1pct     |               0.4288 |
| product_partner_cell |         5 | gross_contraction | shrinking_top_5pct     |               0.7107 |
| product_partner_cell |         5 | gross_positive    | existing_non_top_10    |               0.8054 |
| product_partner_cell |         5 | gross_positive    | existing_non_top_1pct  |               0.5434 |
| product_partner_cell |         5 | gross_positive    | existing_non_top_5pct  |               0.2864 |
| product_partner_cell |         5 | gross_positive    | existing_top_10        |               0.1062 |
| product_partner_cell |         5 | gross_positive    | existing_top_1pct      |               0.374  |
| product_partner_cell |         5 | gross_positive    | existing_top_5pct      |               0.6514 |
| product_partner_cell |         5 | gross_positive    | new_item               |               0.0393 |
| product_partner_cell |        10 | gross_contraction | exited_non_top_10      |               0.1019 |
| product_partner_cell |        10 | gross_contraction | exited_non_top_1pct    |               0.0669 |
| product_partner_cell |        10 | gross_contraction | exited_non_top_5pct    |               0.0336 |
| product_partner_cell |        10 | gross_contraction | exited_top_10          |               0.1129 |
| product_partner_cell |        10 | gross_contraction | exited_top_1pct        |               0.0791 |
| product_partner_cell |        10 | gross_contraction | exited_top_5pct        |               0.0916 |
| product_partner_cell |        10 | gross_contraction | shrinking_non_top_10   |               0.6911 |
| product_partner_cell |        10 | gross_contraction | shrinking_non_top_1pct |               0.3973 |
| product_partner_cell |        10 | gross_contraction | shrinking_non_top_5pct |               0.1564 |
| product_partner_cell |        10 | gross_contraction | shrinking_top_10       |               0.1369 |
| product_partner_cell |        10 | gross_contraction | shrinking_top_1pct     |               0.4278 |
| product_partner_cell |        10 | gross_contraction | shrinking_top_5pct     |               0.6982 |
| product_partner_cell |        10 | gross_positive    | existing_non_top_10    |               0.8036 |
| product_partner_cell |        10 | gross_positive    | existing_non_top_1pct  |               0.5623 |
| product_partner_cell |        10 | gross_positive    | existing_non_top_5pct  |               0.3072 |
| product_partner_cell |        10 | gross_positive    | existing_top_10        |               0.0944 |
| product_partner_cell |        10 | gross_positive    | existing_top_1pct      |               0.343  |
| product_partner_cell |        10 | gross_positive    | existing_top_5pct      |               0.6163 |
| product_partner_cell |        10 | gross_positive    | new_item               |               0.0573 |

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
