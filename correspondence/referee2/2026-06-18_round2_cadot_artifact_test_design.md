# Referee 2 Design Review: Is the Cadot Hump a Stable Fact or a Data-Dependent Result?

Date: 2026-06-18  
Mode: code/econometrics design audit  
Review independence: local review in the active thread; not a fresh-agent implementation audit.

## Summary

The current modern `cadot_broad_156` evidence is not sufficient to call Cadot's result a data artifact. It establishes a narrower and important fact: in 2000-2024 data, the export-concentration hump is strong in pooled and between-country comparisons but weak in country fixed-effect estimates. The result is also concentrated near the rich tail, where only seven of 135 analytic countries cross the estimated export turning-point region.

A defensible challenge to Cadot does not require mechanically reproducing every original choice. It does require a bridge design capable of distinguishing four explanations: a real but period-specific relationship, a country-composition effect, a trade-reporting/product-construction artifact, and an underpowered modern within-country test.

## Current Evidence

- Sample: 156 selected reporters; 135 complete-case regression countries, 2000-2024.
- Income: WDI constant-2021 PPP GDP per capita.
- Product construction: LT/HGL harmonization to HS1992/H0; 5,037-product fixed universe for Theil.
- Trade reporting: reporter-recorded exports, not mirror exports.
- Specification: income, income squared, log population, oil export share, year effects; pooled and country-FE models cluster by reporter.
- Export Product Gini: pooled quadratic `p < 0.001`, turning point about $78.5k and outside p05-p95; country-FE quadratic `p = 0.933`; between-country hump is clear.
- Export Product Theil: pooled quadratic `p < 0.001`, turning point about $78.2k and outside p05-p95; country-FE quadratic `p = 0.608`; between-country hump is clear.
- Only seven analytic countries cross income levels around $73k-$79k. Eleven ever exceed the broad-panel p95 income of about $74.2k.

This supports a between-country development-stage pattern. It does not identify whether Cadot's stronger within-country result was period-specific, measurement-sensitive, or spurious.

## Major Concerns

### 1. A modern null is not an artifact test

Changing the period, countries, PPP vintage, reporter convention, product universe, and controls simultaneously prevents attribution. A different modern coefficient can reflect structural change, data construction, sample composition, or power.

### 2. The modern within-country test has weak rich-tail support

Only seven countries cross the export turning-point region. A fixed-effect null may therefore reflect limited identifying variation or measurement-error attenuation. Leave-one-rich-country tests and simulation-based power are required before interpreting the null substantively.

### 3. The current Gini is not the cleanest Cadot-comparable outcome

The broad methods describe Gini over active positive lines, while the fixed-universe Theil explicitly incorporates inactive-line support. Since Cadot's mechanism is extensive-margin entry and exit, fixed-universe Theil and active-line counts should be primary. A zero-inclusive/fixed-universe Gini should be added only if constructed transparently.

### 4. The control set is not diagnostic

The current runner always includes log population and oil share. It therefore cannot show whether the hump disappears because of country effects, controls, changed rows, or changed inference. Cadot's minimal quadratic and a same-sample control ladder are required.

### 5. Reporter versus mirror trade is unresolved

Cadot used mirror data to reduce exporter-reporting error. The modern bundle uses reporter flows. A result found only under one reporting convention would be evidence of measurement dependence, not a stable development law.

## Research Question and Estimand

The target is descriptive, not causal:

> Does the conditional relationship between export concentration and constant-PPP income exhibit a supported U-shape, both across countries and within countries, and is that shape stable across periods and defensible trade/product constructions?

The primary outcome should be fixed-universe export Product Theil. Secondary outcomes are active export lines, Product Gini, and HHI. Partner and import concentration are extensions, not tests of Cadot's headline claim.

## Required Bridge Design

Use a common-country/common-support design with four core cells:

| Cell | Period | Construction | Purpose |
|---|---|---|---|
| A | 1988-2006 | Cadot-like mirror, HS0/fixed universe | Calibration: can the pipeline recover the historical result? |
| B | 1988-2006 | Modern reporter/harmonized construction | Is the historical result sensitive to construction? |
| C | 2000-2024 | Cadot-like construction | Does the result survive into the modern period under similar measurement? |
| D | 2000-2024 | Modern construction | Current broad extension |

Where exact country recovery is impossible, use a transparently reconstructed common-country sample and report discrepancies. Exact country identity is less important than holding the country set fixed when isolating period and construction effects.

Estimate a stacked common-country model with period interactions on income and income squared. This directly tests whether the curve changed across periods rather than comparing significance labels across separate regressions.

## Minimum Modern-Panel Test Suite

These tests can be implemented immediately from the saved analytic panel.

### 1. Cadot-minimal and sequential-control ladder

Estimate both a fixed-sample ladder and a natural-sample ladder:

1. Income and income squared, HC1/White inference.
2. Add year effects and country-clustered inference.
3. Exclude microstates rather than controlling for population.
4. Add oil export share.
5. Add log population.
6. Add country fixed effects.

The fixed-sample ladder identifies specification changes. The natural-sample ladder identifies changes caused by control-related attrition.

### 2. Mundlak/within-between decomposition

For income `x`, estimate:

`Y_it = beta_w1 (x_it - xbar_i) + beta_w2 (x_it^2 - mean_i(x^2)) + beta_b1 xbar_i + beta_b2 mean_i(x^2) + year_FE + controls + error_it`.

Cluster by country. Report within and between curves separately and test equality of the within and between income terms. Do not infer the within curve from pooled coefficients.

### 3. Rich-tail influence and support

- Leave out each country that ever exceeds the p95 income threshold.
- Also run full leave-one-country-out influence for the primary outcome.
- Report coefficient ranges, turning-point ranges, support flags, and which omissions change the verdict.
- Report country counts and country-years below and above each turning point.
- Cluster-bootstrap the turning point and its confidence interval.

### 4. Within-country visualization and functional form

- Plot within-country/year-residualized Theil against within-country income deviations.
- Add binned means and a flexible spline/LOESS fit with country-cluster bootstrap bands.
- Estimate a restricted cubic spline as a check on the quadratic.
- Report whether the slope is negative at lower support and positive at upper support.

### 5. Formal U-shape and power tests

- Use a Sasabuchi/Lind-Mehlum-style U-shape test over prespecified central support; do not rely only on `beta_2 > 0`.
- Require the turning point to be inside common support and report its bootstrap interval.
- Simulate outcomes with a Cadot-sized within effect on the observed modern income paths and cluster structure. If detection power is low, the modern FE null is inconclusive rather than contradictory.

## Data-Construction Stress Tests

After the saved-panel tests, build matched panels that vary one dimension at a time:

1. Reporter exports versus mirror exports.
2. Native-revision product identities versus LT/HGL harmonized HS1992/H0 identities.
3. Cadot-like 4,991-product support versus the current 5,037-product support, where a defensible concordance permits it.
4. Exact/reconstructed Cadot countries versus the modern broad sample.
5. Common-country and common-product samples across periods.
6. Section 16 exclusion/coarser aggregation.

Product-dependent analyses must continue to exclude HS6 `999999` before aggregation.

## Mechanism Test

A concentration hump alone does not replicate Cadot's mechanism. For fixed-universe Theil:

- decompose changes into active/inactive (extensive) and active-line value dispersion (intensive) components;
- test whether rich-side reconcentration is accompanied by falling active-line counts;
- separate entry, exit, and continuing-product scaling;
- report whether the extensive component dominates after the turning point.

If modern reconcentration is instead continuing-product scaling, the aggregate shape may resemble Cadot while the mechanism disagrees.

## Decision Rules

### Evidence that Cadot identified a stable fact

- Historical calibration recovers pooled and within humps.
- Modern results retain supported within and between humps across reporting and product constructions.
- Turning points have adequate support and are not driven by individual rich countries.
- Extensive-margin decomposition remains consistent with line exit.

### Evidence that Cadot's result is data-construction dependent

- The historical hump appears only with mirror trade, a particular product universe, or a narrow country composition.
- It disappears under matched reporter data or alternative defensible harmonization while period and countries are held fixed.
- The extensive-margin mechanism is not robust.

### Evidence that the relationship changed over time

- The historical calibration succeeds under multiple constructions.
- The same construction and common-country sample fails in 2000-2024.
- Period-by-income interactions reject stable coefficients.
- The modern test has adequate within-country support and power.

### Inconclusive evidence

- Few countries cross the turning point.
- Turning-point confidence intervals are wide or outside common support.
- Modern simulations show low power to detect a Cadot-sized within effect.
- Results change materially when one or two rich countries are removed.

## Required Outputs

1. Specification-ladder table on fixed and natural samples.
2. Mundlak within/between table and equality tests.
3. Rich-country leave-one-out influence table and forest plot.
4. Common-support and crossing-country diagnostics.
5. Residualized within-country plot and spline comparison.
6. Period-by-construction bridge matrix.
7. Fixed-universe Theil extensive/intensive decomposition.
8. Machine-readable manifest identifying period, countries, reporter convention, harmonization, product universe, PPP vintage, controls, fixed effects, clustering, and attrition.

## Verdict

**Major Revision.** The current evidence is sufficient to question the external validity of Cadot's within-country reconcentration result in the modern period. It is not sufficient to call the original result a quirk or artifact. The minimum modern-panel tests should be run first because they are inexpensive and directly address heterogeneity, leverage, functional form, and power. A publishable claim that Cadot was data-dependent requires the period-by-construction bridge design.

