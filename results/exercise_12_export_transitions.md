# Exercise 12: Export Transition Exercise

Generated: 2026-05-26T17:38:15+00:00

This memo is an accounting exercise, not a regression. It separates where export growth came from: existing top items, existing non-top items, new items, and contractions.

The headline product and product-partner-cell rows use `hs6_harmonized_family + top_10`; partner rows use `partner + top_10`. Other item modes and top definitions remain in the full CSV outputs as diagnostics and robustness checks.

## Coverage

- Growth decomposition rows: 26250
- Size transition rows: 509060
- Product destination/region transition rows: 32
- HS cross-revision diagnostic rows: 5490
- HS harmonization diagnostic rows: 7818
- Excluded base value in old same-revision HS diagnostics: 857,718,729,817,275
- Gross decomposition rows in full CSV: 476720
- Gross decomposition rows in headline memo sample: 56137
- Source details: `{"chunk_rows": 150000, "country_sample": "rd2_countries", "debug_run": false, "dependency_engine": "duckdb", "exercise_12_only": false, "finalize_only": false, "fresh": true, "max_files": null, "memory_limit_gb": 24.0, "memory_reserve_gb": 2.0, "mode": "exercises_02_12_duckdb_checkpointed", "partial_dir": "data/processed/samples/rd2_countries/exercise_02_12_file_aggregates", "partial_files_used": 1931, "resume_exercise_12_spill": false, "reuse_exercise_12_aggregate": false, "workers": 3}`

## Median Net Contribution Shares

| dimension            |   horizon | item_id_mode          | top_definition   | driver_category     |   contribution_share |
|:---------------------|----------:|:----------------------|:-----------------|:--------------------|---------------------:|
| partner              |         5 | partner               | top_10           | existing_non_top_10 |               0.3426 |
| partner              |         5 | partner               | top_10           | existing_top_10     |               0.6216 |
| partner              |         5 | partner               | top_10           | new_item            |               0.0032 |
| partner              |        10 | partner               | top_10           | existing_non_top_10 |               0.3718 |
| partner              |        10 | partner               | top_10           | existing_top_10     |               0.5668 |
| partner              |        10 | partner               | top_10           | new_item            |               0.0105 |
| product              |         5 | hs6_harmonized_family | top_10           | existing_non_top_10 |               0.2815 |
| product              |         5 | hs6_harmonized_family | top_10           | existing_top_10     |               0.14   |
| product              |         5 | hs6_harmonized_family | top_10           | new_item            |               0.4239 |
| product              |        10 | hs6_harmonized_family | top_10           | existing_non_top_10 |               0.3669 |
| product              |        10 | hs6_harmonized_family | top_10           | existing_top_10     |               0.114  |
| product              |        10 | hs6_harmonized_family | top_10           | new_item            |               0.3911 |
| product_partner_cell |         5 | hs6_harmonized_family | top_10           | existing_non_top_10 |               0.178  |
| product_partner_cell |         5 | hs6_harmonized_family | top_10           | existing_top_10     |               0.0068 |
| product_partner_cell |         5 | hs6_harmonized_family | top_10           | new_item            |               0.759  |
| product_partner_cell |        10 | hs6_harmonized_family | top_10           | existing_non_top_10 |               0.241  |
| product_partner_cell |        10 | hs6_harmonized_family | top_10           | existing_top_10     |              -0.0043 |
| product_partner_cell |        10 | hs6_harmonized_family | top_10           | new_item            |               0.7141 |

## Median Gross Contribution Shares

| dimension            |   horizon | item_id_mode          | top_definition   | accounting_type   | driver_category      |   contribution_share |
|:---------------------|----------:|:----------------------|:-----------------|:------------------|:---------------------|---------------------:|
| partner              |         5 | partner               | top_10           | gross_contraction | exited_non_top_10    |               0.0113 |
| partner              |         5 | partner               | top_10           | gross_contraction | exited_top_10        |               0.4782 |
| partner              |         5 | partner               | top_10           | gross_contraction | shrinking_non_top_10 |               0.3708 |
| partner              |         5 | partner               | top_10           | gross_contraction | shrinking_top_10     |               0.5578 |
| partner              |         5 | partner               | top_10           | gross_positive    | existing_non_top_10  |               0.3915 |
| partner              |         5 | partner               | top_10           | gross_positive    | existing_top_10      |               0.5687 |
| partner              |         5 | partner               | top_10           | gross_positive    | new_item             |               0.0045 |
| partner              |        10 | partner               | top_10           | gross_contraction | exited_non_top_10    |               0.0268 |
| partner              |        10 | partner               | top_10           | gross_contraction | exited_top_10        |               0.5459 |
| partner              |        10 | partner               | top_10           | gross_contraction | shrinking_non_top_10 |               0.2974 |
| partner              |        10 | partner               | top_10           | gross_contraction | shrinking_top_10     |               0.5449 |
| partner              |        10 | partner               | top_10           | gross_positive    | existing_non_top_10  |               0.3894 |
| partner              |        10 | partner               | top_10           | gross_positive    | existing_top_10      |               0.5565 |
| partner              |        10 | partner               | top_10           | gross_positive    | new_item             |               0.0099 |
| product              |         5 | hs6_harmonized_family | top_10           | gross_contraction | exited_non_top_10    |               0.3358 |
| product              |         5 | hs6_harmonized_family | top_10           | gross_contraction | exited_top_10        |               0.2094 |
| product              |         5 | hs6_harmonized_family | top_10           | gross_contraction | shrinking_non_top_10 |               0.2683 |
| product              |         5 | hs6_harmonized_family | top_10           | gross_contraction | shrinking_top_10     |               0.114  |
| product              |         5 | hs6_harmonized_family | top_10           | gross_positive    | existing_non_top_10  |               0.4041 |
| product              |         5 | hs6_harmonized_family | top_10           | gross_positive    | existing_top_10      |               0.1552 |
| product              |         5 | hs6_harmonized_family | top_10           | gross_positive    | new_item             |               0.34   |
| product              |        10 | hs6_harmonized_family | top_10           | gross_contraction | exited_non_top_10    |               0.3464 |
| product              |        10 | hs6_harmonized_family | top_10           | gross_contraction | exited_top_10        |               0.1904 |
| product              |        10 | hs6_harmonized_family | top_10           | gross_contraction | shrinking_non_top_10 |               0.284  |
| product              |        10 | hs6_harmonized_family | top_10           | gross_contraction | shrinking_top_10     |               0.1144 |
| product              |        10 | hs6_harmonized_family | top_10           | gross_positive    | existing_non_top_10  |               0.4523 |
| product              |        10 | hs6_harmonized_family | top_10           | gross_positive    | existing_top_10      |               0.1473 |
| product              |        10 | hs6_harmonized_family | top_10           | gross_positive    | new_item             |               0.3117 |
| product_partner_cell |         5 | hs6_harmonized_family | top_10           | gross_contraction | exited_non_top_10    |               0.4394 |
| product_partner_cell |         5 | hs6_harmonized_family | top_10           | gross_contraction | exited_top_10        |               0.0785 |
| product_partner_cell |         5 | hs6_harmonized_family | top_10           | gross_contraction | shrinking_non_top_10 |               0.3562 |
| product_partner_cell |         5 | hs6_harmonized_family | top_10           | gross_contraction | shrinking_top_10     |               0.0621 |
| product_partner_cell |         5 | hs6_harmonized_family | top_10           | gross_positive    | existing_non_top_10  |               0.4631 |
| product_partner_cell |         5 | hs6_harmonized_family | top_10           | gross_positive    | existing_top_10      |               0.0464 |
| product_partner_cell |         5 | hs6_harmonized_family | top_10           | gross_positive    | new_item             |               0.4424 |
| product_partner_cell |        10 | hs6_harmonized_family | top_10           | gross_contraction | exited_non_top_10    |               0.4539 |
| product_partner_cell |        10 | hs6_harmonized_family | top_10           | gross_contraction | exited_top_10        |               0.0808 |
| product_partner_cell |        10 | hs6_harmonized_family | top_10           | gross_contraction | shrinking_non_top_10 |               0.3485 |
| product_partner_cell |        10 | hs6_harmonized_family | top_10           | gross_contraction | shrinking_top_10     |               0.0591 |
| product_partner_cell |        10 | hs6_harmonized_family | top_10           | gross_positive    | existing_non_top_10  |               0.4719 |
| product_partner_cell |        10 | hs6_harmonized_family | top_10           | gross_positive    | existing_top_10      |               0.0395 |
| product_partner_cell |        10 | hs6_harmonized_family | top_10           | gross_positive    | new_item             |               0.4547 |

## Interpretation Limits

The main HS6 product transition is conservative: official WCO adjacent-revision links and unchanged HS6 codes define harmonized families. Oversized connected components are treated as ambiguous and remain revision-specific instead of being collapsed. The old same-revision HS6 diagnostic is retained in `hs_revision_pair_diagnostics.csv` for comparison; harmonization coverage is reported in `hs_harmonization_diagnostics.csv`. HS4, HS2, and CPA-sector outputs are robustness views for product-code instability, not replacements for harmonized HS6 detail.

Net growth can hide churn, so the gross table should be read alongside the net table. Gross positive growth shows expanding/new items; gross contraction shows shrinking or exiting items. The median gross table above is filtered to the same headline sample as the net table and keeps `item_id_mode` and `top_definition` visible.

Destination and region transitions remain descriptive. The state table reports `unknown_partner_region_share` and `region_transition_reliability`; region-transition claims should be discounted when the unknown-region share is high.

## Files

- Tables: `results/exercise_12_tables/`
- Figures: `results/exercise_12_figures/`
- Processed data: `data/processed/exercise_12_growth_decomposition.parquet`
- Net decomposition: `results/exercise_12_tables/growth_decomposition_net.csv`
- Gross decomposition: `results/exercise_12_tables/growth_decomposition_gross.csv`
- Detailed transitions: `results/exercise_12_tables/transition_matrices_detailed.csv`
- HS revision diagnostics: `results/exercise_12_tables/hs_revision_pair_diagnostics.csv`
- HS harmonization diagnostics: `results/exercise_12_tables/hs_harmonization_diagnostics.csv`

## Discussion Prompt

Does future export growth mostly come from already-top items, smaller incumbents, or new product/partner cells?
