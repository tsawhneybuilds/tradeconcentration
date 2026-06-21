# Cadot Mechanism Tribunal — Broad 156

Created: 2026-06-21T12:47:18+00:00

## Scope

The updated tribunal uses all 156 selected reporters and 156 reporters with at least one observed export year. It contains 3,753 observed country-years over 2000-2024; it is intentionally unbalanced.
The controlled income-shape regressions retain 135 reporters with complete PPP, population, and oil-share controls. The mechanism episode panel itself retains all 156.

The primary episode definition is an increase in fixed-universe Product Theil over five years. This measure rises both when exports become more unequal across active products and when the inactive-product margin expands, making it closer to Cadot's diversification question than the earlier world-relative Gini-only episode rule.

## Mechanism scorecard

| mechanism                            |   reconcentration_episodes |   flagged_episodes |   flagged_share |
|:-------------------------------------|---------------------------:|-------------------:|----------------:|
| commodity_spike                      |                       1312 |                465 |          0.3544 |
| section16_hs_design_sensitive        |                       1312 |                147 |          0.112  |
| old_cone_pruning                     |                       1312 |                 71 |          0.0541 |
| continuing_product_superstar_scaling |                       1312 |                947 |          0.7218 |
| broad_unexplained_reconcentration    |                       1312 |                188 |          0.1433 |

Flags overlap and are descriptive triage categories, so their shares do not sum to 100%.

## Old-cone test

The old-cone mismatch × rich-side coefficient is **0.0325** (clustered SE 0.0054, **raw p=1.308e-08**; 154 reporter clusters).

The primary product-sophistication object is standard full-sample PRODY: exporter basket shares are normalized across the 181-reporter `world_broad` benchmark and applied to GDP per capita in levels. The regression uses the log income ratio `log(country GDPpc / product PRODY)` for scale comparability.

### PRODY construction bridge

| prody_spec             | primary_spec   |   matched_country_product_windows |   spearman_mismatch_correlation_with_primary |   old_cone_classification_change_share |   bottom_decile_overlap_share |   top_decile_overlap_share |   exit_interaction_coefficient |   exit_interaction_std_error |   exit_interaction_raw_p_value |
|:-----------------------|:---------------|----------------------------------:|---------------------------------------------:|---------------------------------------:|------------------------------:|---------------------------:|-------------------------------:|-----------------------------:|-------------------------------:|
| world_broad_full_level | True           |                           1464385 |                                       1      |                                 0      |                        1      |                     1      |                         0.0325 |                       0.0054 |                              0 |
| world_broad_loo_level  | False          |                           1464385 |                                       0.9995 |                                 0.0003 |                        0.9872 |                     0.9842 |                         0.0293 |                       0.0052 |                              0 |
| world_broad_loo_log    | False          |                           1464385 |                                       0.9852 |                                 0.1096 |                        0.9185 |                     0.856  |                         0.0263 |                       0.0041 |                              0 |

At the product-year level, arithmetic level-income PRODY and geometric log-income PRODY have Spearman rank correlation 0.975; their bottom- and top-decile overlaps are 84.3% and 83.2%.

The rich-side split is `sample_income_p75_fallback` at approximately $39,308 in constant-2021 PPP dollars. The prior $25,000 cutoff was removed because it came from a different PPP vintage and was not unit-comparable.

## Interpretation

This expansion answers the sample question: the mechanism tribunal is now a broad-156 exercise, not a 55-country balanced-panel exercise. It still does not establish a causal effect of income. The mechanism flags identify empirical patterns that accompany reconcentration and the old-cone regression tests one specific implication; neither is a causal decomposition.
