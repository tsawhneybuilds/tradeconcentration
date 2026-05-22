# Excluding HS6 999999: Rerun Comparison

Standing rule applied: HS6 `999999` is treated as "Commodities not specified" and excluded before concentration measures, shares, bins, regressions, checkpoint/final outputs, and site downloads are computed.

## Key Result Changes

| Measure | Before | No-999999 | Change |
|---|---:|---:|---:|
| E1 median export product Gini | 0.910241 | 0.906688 | -0.003553 |
| E1 median import product Gini | 0.858570 | 0.854202 | -0.004369 |
| E2 H5 high-product/high-partner coef | -0.012227 | -0.006381 | 0.005846 |
| E2 H10 product-gini coef | -3.6452 | -3.8974 | -0.252257 |
| E3 median intermediates import Gini | 0.848108 | 0.848117 | 0.000009 |
| E4 median top supplier share | 0.502360 | 0.502044 | -0.000316 |
| E4 latest median actual partner Gini | 0.901803 | 0.901803 | 0.000000 |
| E6 baseline export product Gini | 0.910241 | 0.906688 | -0.003553 |
| E6 full-exclusion export product Gini | 0.904127 | 0.900514 | -0.003613 |
| E6 full-exclusion trade share removed | 0.083204 | 0.085841 | 0.002637 |
| E10 median actual-minus-random product Gini | n/a | 0.373036 | n/a |
| E10 product share above 95th pctile | n/a | 1.0000 | n/a |
| E11 IO top-sector weighted input Gini | 0.761734 | 0.761978 | 0.000243 |
| E11 IO matched requirement share | 0.106305 | 0.106376 | 0.000071 |
| E11 product 4% bin 1 export probability | 0.935236 | 0.934075 | -0.001161 |
| E11 product 4% bin 25 export probability | 0.749452 | 0.755310 | 0.005858 |
| E11 HS2 4% bin 1 export probability | 0.998853 | 0.998616 | -0.000237 |
| E11 HS2 4% bin 25 export probability | 0.994953 | 0.995156 | 0.000203 |
| E11 product LPM LOO-Gini coef | -0.129632 | -0.129485 | 0.000147 |
| E11 product conditional-logit LOO-Gini coef | n/a | -3.3891 | n/a |
| E12 H5 median new-product contribution share | 0.027778 | 0.195298 | 0.167521 |
| E12 H5 median existing-top-10 contribution share | 0.171979 | 0.149532 | -0.022447 |

## Exercise-Level Notes

- Exercise 1 concentration: product Ginis move only slightly after removing `999999`; export median is 0.906688 and import median is 0.854202.
- Exercise 2 growth models: the selected H5 high-product/high-partner coefficient remains negative (-0.006381), and the H10 continuous product-Gini coefficient remains negative (-3.8974).
- Exercise 3 import bins: intermediates remain highly concentrated; median product Gini is 0.848117.
- Exercise 4 supplier/counterfactuals: median top-supplier share is 0.502044; the latest-country median actual partner Gini is 0.901803.
- Exercise 6 exclusion tests: the baseline sample is now already no-`999999`; the full commodity/oil/gold exclusion still lowers median export product Gini to 0.900514.
- Exercise 10 benchmark: product concentration remains far above the symmetric-random allocation benchmark; 1.0000 of product observations sit above the 95th simulated percentile.
- Exercise 11 IO linkage: top-export-sector imported-input exposure remains high, with median weighted input product Gini 0.761978.
- Exercise 11 product-export linkage: HS6 export probability still declines across the 25 four-percent bins (0.934075 in bin 1 to 0.755310 in bin 25). The visual conclusion is unchanged from the 10%/old 4% graph: products contributing more to import concentration are less likely to be exported.
- Exercise 12 transitions: median H5 new-product contribution share is 0.195298, now above the median existing top-10 contribution share of 0.149532.

## Exercise 11 Model Check

- LPM export-any coefficient on standardized LOO Gini: -0.129632 before from the current site download, -0.129485 after. Sign did not change.
- Conditional logit coefficient on standardized LOO Gini: -3.3891 with p-value 0.000000; sign is negative and statistically significant.
- Conditional logit sample: 5,562,527 observations in 1,128 country-year groups; dropped 2 no-variation groups (5,947 observations).

## Validation

- `data/processed/exercise_11_product_export_linkage_panel.parquet`: 0 rows with `cmd_code == "999999"`.
- `data/processed/exercise_12_export_aggregates.parquet`: 0 rows with `cmd_code == "999999"`.
- Exercise 11 and Exercise 12 checkpoint partials scanned: 0 rows with `cmd_code == "999999"`.
- Result CSVs with product-code columns scanned: 0 rows with `999999`; stale auxiliary Exercise 3/adversarial example CSVs were regenerated or cleared.
- Exercise 11 HS6 and HS2 four-percent bin tables each contain 25 nonempty bins; each bin has `export_probability == exported_count / observations`.
- Syntax check passed for the main pipeline, Exercise 11 product-linkage script, site builder, and related checkpoint runners.
