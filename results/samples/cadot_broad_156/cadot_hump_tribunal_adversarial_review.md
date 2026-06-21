# Adversarial Econometrics Review: Broad-156 Cadot Mechanism Tribunal

Review date: 2026-06-21

Review independence: **not independent**. The current request did not authorize subagent delegation, so this is a local adversarial review by the implementing session.

## Executive verdict

**Mostly trustworthy for descriptive use.**

- The primary PRODY object now follows the standard construction using export-basket shares, income levels, and a common product-year benchmark.
- The benchmark uses 181 `world_broad` reporters; 176 have at least one usable PPP-income observation.
- The analyzed exit panel remains the 156-reporter modern sample and uses harmonized HS1992-HS4 identities.
- The construction bridge shows that the earlier log-income proxy changed old-cone classification for about 11% of matched observations.
- The corrected old-cone interaction remains positive and precisely estimated, but it is descriptive rather than causal.

## Findings

- Sample construction passes: all 156 selected reporters appear in the 3,753-row observed country-year panel and the 2,811-row five-year episode panel. Neither panel has duplicate keys.
- The controlled income-shape regressions retain 135 reporters because PPP, population, and oil-share controls are incomplete. The mechanism episode panel still retains all 156.
- Product-dependent calculations use the LT/HGL harmonized HS1992-family export file and a fixed universe of 5,037 products. Code `999999` was already excluded upstream and is rechecked before aggregation.
- Product sophistication now uses standard full-sample level-income PRODY:
  `PRODY_pt = sum_c(s_cpt * GDPpc_ct) / sum_c(s_cpt)`, where `s_cpt` is the product's share in country exports.
- The primary mismatch is `log(GDPpc_ct / PRODY_pt)`. This transforms the final level-income PRODY for scale, rather than averaging log incomes inside PRODY.
- Bridge specifications retain level-income leave-one-out and log-income leave-one-out versions. Relative to the primary measure, the level leave-one-out version changes 0.03% of old-cone classifications; the log leave-one-out version changes about 11%.
- An initial audit found that the pre-existing broad headline concentration panel and the newer harmonized product-export artifact differed for a minority of country-years. The final tribunal does not mix those vintages: Gini, fixed-universe Theil, HHI, totals, active counts, mechanical variants, transitions, and PRODY are recomputed from the same harmonized product input. Internal totals, active counts, and Gini now reconcile exactly.
- Positive-expansion and contraction channel shares sum to one within floating-point tolerance. The reconcentration indicator exactly equals a positive five-year change in fixed-universe Product Theil.
- The earlier $25,000 “rich side” threshold was removed because it was inherited from a different PPP vintage. The estimated Product Theil turning point is about $270,705 in constant-2021 PPP dollars and lies above the sample p95, so it is not supported. The descriptive mechanism split therefore uses the observed country-year income p75, about $39,308, and labels it as a fallback.

## Econometric cautions

- The hump regression’s positive log-income curvature is not sufficient evidence of reconcentration because its turning point is outside empirical support. It should be reported as functional-form extrapolation, not a validated U-shape.
- The corrected primary old-cone regression uses 1,464,385 product-window observations and 154 reporter clusters. Its mismatch × rich-side coefficient is 0.0325 (clustered SE 0.0054; raw p < 0.001). This is consistent with relatively low-PRODY products exiting more often on the descriptive rich side, but overlapping five-year windows, common product shocks, generated PRODY, and one-way reporter clustering prevent a causal interpretation.
- Mechanism flags are threshold-based and overlap. Their shares are classification rates, not an additive decomposition or mutually exclusive treatment effects.
- The primary episode outcome is fixed-universe Product Theil. This is defensible for Cadot-style extensive-margin analysis, but results should not be described as a literal replication of Cadot, Carrère, and Strauss-Kahn.

## Cleared use

Use the broad-156 scorecard to say what commonly accompanies observed reconcentration and to compare mechanism prevalence across reporters. Do not use it to claim that rising income causes reconcentration or that a statistically supported development turning point has been found.
