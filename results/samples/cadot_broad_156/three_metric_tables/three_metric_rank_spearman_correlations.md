# Broad-156 Product-Panel Rank and Spearman Correlations

This note uses the existing `cadot_broad_156` three-metric product panel in
`results/samples/cadot_broad_156/three_metric_tables/metric_headline_product_panel.parquet`.

## Sample and panel

- Sample: `cadot_broad_156`.
- Panel: common product headline rows with `dimension == "product"`, `variant == "baseline"`, and `common_gini_theil_hhi_row == True`.
- Unit of observation: reporter-year-flow.
- Rows: overall `7509`, exports `3753`, imports `3756`.
- Metrics: headline `gini`, headline fixed-universe `theil`, and raw `hhi`.

## Pooled correlations

| metric_x   | metric_y   |   rank_correlation |   spearman_correlation |
|:-----------|:-----------|-------------------:|-----------------------:|
| gini       | hhi        |           0.836245 |               0.836245 |
| gini       | theil      |           0.918386 |               0.918386 |
| theil      | hhi        |           0.952105 |               0.952105 |

## Flow-specific correlations

| flow    | metric_x   | metric_y   |   rank_correlation |   spearman_correlation |
|:--------|:-----------|:-----------|-------------------:|-----------------------:|
| Exports | gini       | hhi        |           0.82495  |               0.82495  |
| Exports | gini       | theil      |           0.828674 |               0.828674 |
| Exports | theil      | hhi        |           0.978662 |               0.978662 |
| Imports | gini       | hhi        |           0.763563 |               0.763563 |
| Imports | gini       | theil      |           0.91017  |               0.91017  |
| Imports | theil      | hhi        |           0.902026 |               0.902026 |

## Interpretation

- Spearman is already a rank correlation.
- The separate `rank_correlation` rows use Pearson correlation on average ranks from the same observations.
- In this panel they are numerically identical within tolerance `1.0e-12` for every metric pair and flow slice.
- These are descriptive concordance measures across headline concentration metrics; they are not causal estimates.
