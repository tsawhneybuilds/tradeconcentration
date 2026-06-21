# Prof P Replication Diagnosis

## Main Diagnosis

The default Table 3-4 rerun now uses all-commodity partner totals with the five largest actual partners in the numerator and `partnerCode == 0` (`World`) as the denominator. This is a uniform denominator convention; `World` is still excluded from the partner list, partner count, and partner Gini.

The large remaining partner-concentration mismatch is not rounding. The six outlier rows only match the paper when `World` is counted as one of the partners in the top-five list. That is a paper-forensic diagnostic rather than the default economic construction.

The product-count mismatch is different. Product Ginis are close, but active HS6 counts remain higher than the paper by roughly 125-170 products even after testing world/no-world raw variants. That points to Comtrade data-vintage or historical extraction differences rather than a simple filtering bug.

The closest Table 2 diagnostic found so far is not a value threshold. It is a mechanical WCO HS1996-to-HS2002 concordance aggregation that maps changed 1996 HS6 codes to the first listed 2002 target, aggregating values that collapse to the same target. This reduces the active-product count gap sharply while leaving Ginis close, but it should be reported as a paper-like sensitivity because one-to-many HS splits cannot be uniquely allocated from 2001 H1 data.

## Table 2 HS2002 Concordance Diagnostic

| flow    |   baseline_mean_abs_count_diff |   concordance_mean_abs_count_diff |   baseline_median_abs_count_diff |   concordance_median_abs_count_diff |   concordance_max_abs_count_diff |   concordance_mean_abs_gini_diff |   concordance_max_abs_gini_diff |
|:--------|-------------------------------:|----------------------------------:|---------------------------------:|------------------------------------:|---------------------------------:|---------------------------------:|--------------------------------:|
| Exports |                        119.394 |                           39.5758 |                              125 |                                  42 |                               60 |                       0.00275294 |                       0.0108831 |
| Imports |                        145.242 |                           51.303  |                              147 |                                  52 |                               81 |                       0.00349461 |                       0.0163994 |

## World-Partner Rows That Match The Paper

| country     | flow    |   modern_partner_gini |   paper_partner_gini |   modern_top5_partner_share_pct |   paper_top5_partner_share_pct |
|:------------|:--------|----------------------:|---------------------:|--------------------------------:|-------------------------------:|
| Finland     | Exports |              0.936808 |                0.934 |                         69.7042 |                           69.6 |
| Greece      | Exports |              0.924702 |                0.924 |                         66.6145 |                           66.6 |
| India       | Exports |              0.919587 |                0.92  |                         67.7894 |                           67.8 |
| Slovakia    | Imports |              0.958622 |                0.959 |                         80.4466 |                           80.4 |
| Switzerland | Imports |              0.961349 |                0.962 |                         78.2382 |                           78.2 |
| Turkey      | Imports |              0.921726 |                0.923 |                         68.1801 |                           68.7 |

## Key Ordering Checks

| claim                                                            | left_country   | right_country   |   paper_left |   paper_right | paper_relation   |   modern_left |   modern_right | modern_relation   | replicates_ordering   |
|:-----------------------------------------------------------------|:---------------|:----------------|-------------:|--------------:|:-----------------|--------------:|---------------:|:------------------|:----------------------|
| India vs China export product Gini                               | India          | China           |        0.904 |         0.848 | >                |      0.900964 |       0.849209 | >                 | True                  |
| India vs China import product Gini                               | India          | China           |        0.925 |         0.875 | >                |      0.926372 |       0.873294 | >                 | True                  |
| India vs China export partner Gini, clean no-world               | India          | China           |        0.92  |         0.903 | >                |      0.853183 |       0.902674 | <=                | False                 |
| India vs China export partner Gini, paper-like world sensitivity | India          | China           |        0.92  |         0.903 | >                |      0.919587 |       0.903353 | >                 | True                  |
| India vs China import partner Gini, clean no-world               | India          | China           |        0.889 |         0.897 | <=               |      0.889202 |       0.896704 | <=                | True                  |

## Diagnostic Files

- Partner sensitivity: `results/prof_p_replication/tables/partner_concentration_world_partner_sensitivity.csv`
- Paper-like partner variant: `results/prof_p_replication/tables/partner_concentration_paper_like_variant.csv`
- Product sensitivity: `results/prof_p_replication/tables/product_concentration_raw_variant_sensitivity.csv`
- Table 2 HS2002 concordance: `results/prof_p_replication/tables/table_2_product_concentration_hs2002_concordance_comparison.csv`
- Table 2 HS2002 threshold sensitivity: `results/prof_p_replication/tables/table_2_product_concentration_hs2002_threshold_sensitivity.csv`
- Key ordering checks: `results/prof_p_replication/tables/key_qualitative_ordering_checks.csv`

## Summary Stats

- table_2: max gini abs diff 0.0159; max product-count abs diff 170
- table_3: World-denominator top-5 convention: max gini abs diff 0.0668; mean/median/max top-5-share abs diff 2.67/0.04/27.95 pp
- table_4: World-denominator top-5 convention: max gini abs diff 0.0621; mean/median/max top-5-share abs diff 2.04/0.04/25.70 pp
- partner_sensitivity: Including partnerCode 0 (`World`) best matches exactly 3 export rows and 3 import rows; those are the rows driving the large Table 3/4 mismatches.
- world_partner_rows: For those six world-partner rows, max abs top-5 difference is 0.52 pp and max abs partner-Gini difference is 0.0028.
- paper_like_partner: Paper-like max abs top-5 difference 7.90 pp; max abs partner-Gini difference 0.0173.
- product_sensitivity: No-world raw product construction still has median active-count gap 140 and max gap 170; median abs product-Gini gap is 0.0017.
- table2_hs2002_concordance: WCO HS1996-to-HS2002 first-listed-target aggregation lowers mean abs product-count gap from 132.3 to 45.4 and median abs gap from 139.5 to 47.5; mean abs Gini gap is 0.0031.
- table2_hs2002_threshold_sensitivity: Adding a $10 post-concordance value floor gives the lowest mean abs count gap (42.3) in the tested grid, but no paper source supports imposing that floor.
