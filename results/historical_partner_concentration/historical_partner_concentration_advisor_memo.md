# Advisor results memo: long-run trade-partner concentration

## Bottom line

The 1827–2014 data do **not** support a Cadot-style diversification-then-reconcentration pattern across trading partners. None of the six preferred within-country tests passes the formal U-shape test, and none survives the full sensitivity grid. The defensible interpretation is a null result for partner concentration—not evidence against Cadot's product-diversification result.

![Baseline U-shape tests](figures/advisor/baseline_u_shape_tests.png)

## What the estimates show

Only export Gini and export Theil have the required negative-to-positive endpoint slopes. Their joint U-test p-values are 0.455 and 0.455; both have BH-adjusted q = 0.841. Export Gini also lacks enough support above its estimated trough. The import measures either continue declining or have inverted-U signs.

| Flow | Measure | Endpoint slopes | Stationary point, if in support | Raw U-test p | BH q | Classification |
| --- | --- | --- | ---: | ---: | ---: | --- |
| Exports | Gini | U-shaped signs | $30,142 | 0.455 | 0.841 | insufficient support |
| Exports | Theil | U-shaped signs | $11,663 | 0.455 | 0.841 | sign pattern only |
| Exports | HHI | negative to negative | outside support | 0.770 | 0.841 | outside support |
| Imports | Gini | negative to negative | outside support | 0.770 | 0.841 | outside support |
| Imports | Theil | inverted-U signs | $20,432 | 0.731 | 0.841 | no U-shape |
| Imports | HHI | negative to negative | outside support | 0.841 | 0.841 | outside support |

Across 168 preferred within-country sensitivity tests—28 variants for each flow-measure pair—there are 0 supported U-shapes. The smallest raw U-test p-value is 0.203, still well above 0.05.

![Sensitivity U-shape tests](figures/advisor/within_u_shape_sensitivity.png)

## Interpretation and recommendation

Partner concentration does not reproduce the product-space hump in this long historical sample. A plausible substantive interpretation is that development broadens the product margin differently from the geographic partner margin; however, this exercise is descriptive and cannot identify income as the cause of either process.

I recommend presenting this as a disciplined negative result: keep the partner analysis as a boundary test of the Cadot mechanism, and make the next decision explicit—either compare product and partner concentration in the same countries and years, or move the partner result to an appendix and focus the main paper on product diversification.

## Data and inference note

The preferred models use 1,670 export and 1,634 import entity-years from 13 historical reporter entities, with entity and year fixed effects and log population. Income is Maddison real GDP per capita in 2011 PPP dollars. Inference uses 9,999 entity-level Rademacher wild-cluster bootstrap draws; the six primary tests use Benjamini–Hochberg adjustment.

For strictly positive observed partner flows \(x_j\), shares are \(s_j=x_j/\sum_jx_j\). The measures are \(G=2\sum_j jx_{(j)}/(n\sum_jx_j)-(n+1)/n\), \(T=\sum_js_j\log(ns_j)\), and \(HHI=\sum_js_j^2\). Higher values mean trade is more concentrated among active partners. Baseline estimates require at least 20 active partners; missing dyads are not coded as zero.

The remaining limitations are 13 clusters, uneven historical coverage, Maddison income/population attrition, changing source regimes, and the absence of a fresh independent-agent trust review. The completed local adversarial review rates the pipeline **mostly trustworthy** and finds no unresolved high-risk coding defect.

**Question for discussion:** Should the null partner result become an appendix boundary test, or should we build a matched product-versus-partner comparison as the next main exhibit?
