# Does the Cadot Rich-Tail Bend Survive Among Similarly Sized Countries?

## Design

- Descriptive between-country test using the saved `cadot_broad_156` complete-case panel.
- Unit of observation: country mean over available 2000–2024 country-years.
- Sample: 135 countries, split into fixed population terciles of 45 countries each.
- Outcomes: export active-product Gini and export fixed-universe Product Theil. Product-dependent source artifacts exclude HS6 `999999` before aggregation.
- Main specifications: separate quadratic and cubic-spline income curves by population tercile, controlling for mean oil export share.

Within each population tercile, the quadratic model is `concentration_i = beta0 + beta1 income_i + beta2 income_i^2 + theta oil_share_i + error_i`, where `i` is a country and income is mean constant-PPP GDP per capita over the observed period. A positive `beta2` with an interior minimum is evidence of a U-shaped bend. Higher Gini or Theil means greater export-product concentration.

## Support comes first

The original full-sample between-country turning points are roughly $72,600 for Gini and $73,200 for Theil. Countries at or above those thresholds are distributed as follows:

| Population tercile | Countries | Mean-population range | Countries with income >= $70k | At/above Gini turning point | At/above Theil turning point |
| --- | ---: | ---: | ---: | ---: | ---: |
| Small | 45 | 56,485–3,056,616 | 5 | 5 | 5 |
| Medium | 45 | 3,066,091–14,898,611 | 4 | 4 | 4 |
| Large | 45 | 14,942,278–1,350,676,967 | 0 | 0 | 0 |

There is therefore no common-support test of the approximately $73,000 rich tail for large countries: the large-country tercile contains no country with mean income above $70,000. The rich tail is composed entirely of small and medium-sized countries.

## Flexible population adjustment

Adding population flexibly does not eliminate the full-sample between-country quadratic:

| Outcome | Population control | Quadratic coefficient | Quadratic p-value | Turning point |
| --- | --- | ---: | ---: | ---: |
| Export Product Gini | Linear log population | **0.0011** | **0.0000** | $70,878 |
| Export Product Gini | Population spline | **0.0011** | **0.0000** | $69,507 |
| Export Product Theil | Linear log population | **0.0498** | **0.0065** | $71,428 |
| Export Product Theil | Population spline | **0.0518** | **0.0044** | $70,562 |

Population therefore shifts levels and the estimated minimum, but a flexible additive population control alone does not erase the aggregate curve. The harder test is whether the curve repeats within population groups.

## Within-size estimates

| Outcome | Size tercile | Quadratic p-value | Quadratic turning point | Turning point in group p05–p95 | Spline p95 minus trough | Spline delta p-value |
| --- | --- | ---: | ---: | --- | ---: | ---: |
| Export Product Gini | Small | 0.708 | none | no | 0.0000 | not applicable |
| Export Product Gini | Medium | **0.022** | $51,842 | yes | 0.0227 | 0.286 |
| Export Product Gini | Large | 0.545 | $87,277 | no | 0.0000 | not applicable |
| Export Product Theil | Small | 0.489 | $85,302 | yes | 0.6611 | 0.225 |
| Export Product Theil | Medium | 0.076 | $54,416 | yes | 0.5154 | 0.362 |
| Export Product Theil | Large | **0.018** | $42,468 | yes | 0.0000 | not applicable |

The medium-size Gini quadratic is not created by one of its four rich countries. Omitting Ireland, Singapore, Switzerland, or the United Arab Emirates one at a time leaves the quadratic positive and statistically significant in every run, with the estimated minimum between $46,063 and $55,247.

The stronger all-country influence check reaches the same result: omitting each of the 45 medium-size countries one at a time leaves the Gini quadratic positive and significant in 100% of runs; the largest raw p-value is **0.041**.

The exact transformation used by the existing between-country runner—averaging annual income-squared rather than squaring mean income—gives the same medium-size Gini conclusion: quadratic coefficient **0.0021**, raw p-value **0.041**, and minimum $53,457.

Restricting the analysis to the 92 countries observed in every year from 2000 through 2024 also preserves the medium-size Gini bend: quadratic coefficient **0.0022**, raw p-value **0.002**, and minimum $56,612. In contrast, the large-group Theil quadratic is no longer significant in this complete-period sample (raw p-value 0.335).

## Answer

The evidence does **not** support a clean claim that the rich-tail bend remains among countries of comparable size.

- For export Gini, the quadratic bend is present in the medium-size tercile but not in the small or large terciles.
- For export Theil, positive curvature appears in the medium and large terciles, but the large-country turning point occurs below the full-sample rich-tail threshold and cannot validate an approximately $73,000 upturn.
- Flexible splines are imprecise because each size tercile has only 45 countries and the actual rich tail contains only five small and four medium countries.
- The income curves differ across population terciles jointly for Gini at p=0.005 and for Theil at p=0.195.

The defensible conclusion is: **flexible population adjustment does not erase the aggregate bend, but the bend is not shown to be a general within-size pattern.** A robust medium-size-country Gini bend remains. The available sample lacks large rich countries, so it cannot establish whether reconcentration extends to rich economies of comparable large scale.

## Interpretation limits

- Population terciles are coarse; they improve comparability but do not create exact size matches.
- The exercise is descriptive and relies on persistent cross-country differences.
- The small number of countries above the original turning point makes rich-tail inference leverage-sensitive.
- Spline p-values condition on the estimated trough location and should be treated as descriptive approximations, not pre-specified hypothesis tests.
- Failure to find a large-country rich tail is a support failure, not evidence that large rich countries would have no bend.
