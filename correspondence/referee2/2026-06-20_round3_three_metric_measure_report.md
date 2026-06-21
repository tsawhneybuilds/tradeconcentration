# Referee 2 Report: Three-Metric Rank Correlations and Measure Choice

**Date:** 2026-06-20
**Scope:** Quick-analysis code and interpretation audit
**Primary analysis:** scripts/run_three_metric_rank_correlations.py

## Summary

The Python correlation calculations are correct and independently reproduce in R. The output is suitable as descriptive evidence of cross-metric concordance. It is not sufficient to claim that Gini, Theil, and HHI are interchangeable because the metrics use different product-universe conventions and their agreement is weaker for year-to-year changes than for pooled levels.

## Audit 1: Code

- The filter correctly retains product, baseline, common Gini-Theil-HHI rows.
- The unit of observation is uniquely reporter-year-flow; no duplicates or metric missingness were found.
- Counts match the stated sample: 7,509 overall, 3,753 exports, and 3,756 imports.
- Spearman correlation and Pearson correlation of average ranks are correctly implemented and necessarily coincide.
- The pooled spot checks and all flow-specific values reproduce.
- Product-dependent source construction excludes HS6 code 999999 before harmonization and aggregation.

### Code concern

The output writes extremely small p-values as numeric zero. This is floating-point underflow, not a literal probability of zero. Any publication table should report them as p < 0.001, or omit them because the exercise is descriptive and the very large sample makes conventional significance uninformative.

## Audit 2: Independent Replication

The independent R implementation reads the exported common panel, applies the sample restrictions, checks keys and missingness, and recomputes both correlations.

| Flow | Pair | Python | R | Absolute difference |
|---|---|---:|---:|---:|
| All | Gini-Theil | 0.918386226693 | 0.918386226693 | 0.00e+00 |
| All | Gini-HHI | 0.836245300958 | 0.836245300958 | 2.22e-16 |
| All | Theil-HHI | 0.952105402083 | 0.952105402083 | 4.44e-16 |
| Exports | Gini-Theil | 0.828674120817 | 0.828674120817 | 1.11e-16 |
| Exports | Gini-HHI | 0.824950024157 | 0.824950024157 | 3.33e-16 |
| Exports | Theil-HHI | 0.978662496573 | 0.978662496573 | 3.33e-16 |
| Imports | Gini-Theil | 0.910169873408 | 0.910169873408 | 2.22e-16 |
| Imports | Gini-HHI | 0.763563171464 | 0.763563171464 | 1.11e-16 |
| Imports | Theil-HHI | 0.902025671503 | 0.902025671503 | 3.33e-16 |

Maximum discrepancy: 4.44e-16, numerical precision only.

The Stata replication script was created but not executed because no Stata executable is installed. This is the only cross-language replication gap.

## Audit 3: Measurement and Interpretation

### Major concern 1: Different estimands

The active-positive Gini measures inequality only among products with positive trade. Raw HHI also uses positive shares. The headline Theil uses a fixed universe of 5,037 harmonized HS1992 product families:

T_fixed = sum(s_p log(s_p K)) = T_active + log(K / A),

where K = 5,037 eligible products and A is the number of active products. It therefore combines intensive-margin concentration with an explicit inactive-product margin. High correlation does not remove this conceptual difference.

A concrete diagnostic is Comoros exports in 2007. Only three products were active. Active Gini was 0.028445, which appears highly diversified among the three positive lines, while fixed-universe Theil was 7.427370, of which 7.425954 came from the inactive margin. The active Gini is not wrong; it answers a narrower question.

### Major concern 2: Pooled levels overstate substitutability

Pooled Spearman correlations are high, but first-difference correlations are lower:

| Flow | Pair | Pooled level | First difference |
|---|---|---:|---:|
| Exports | Gini-Theil | 0.828674 | 0.707412 |
| Exports | Gini-HHI | 0.824950 | 0.519351 |
| Exports | Theil-HHI | 0.978662 | 0.864074 |
| Imports | Gini-Theil | 0.910170 | 0.877756 |
| Imports | Gini-HHI | 0.763563 | 0.704252 |
| Imports | Theil-HHI | 0.902026 | 0.901881 |

The three metrics agree more on persistent cross-country ordering than on annual movements, especially for exports. They should not be swapped within a dynamic specification without re-estimating and reporting the result.

### Minor concern: Raw dispersion is not cross-metric evidence

Raw standard deviations and ranges cannot identify the best index because the scales differ. Gini and HHI are bounded; the reported Theil is unnormalized and can reach log(5,037). Dispersion statistics are informative within a metric and flow, not across metrics.

## Verdict

**Correlation implementation:** Accept.
**Claim that all three measures are interchangeable:** Major revision.
**Recommended reporting design:** Fixed-universe Theil as the primary diversification measure, active-positive Gini as the Panagariya-Bagaria replication and intuitive Lorenz benchmark, and HHI as a top-product-dominance robustness measure.

## Prioritized Recommendations

1. State the estimand before naming the index.
2. Use fixed-universe Theil for development-path and extensive/intensive-margin analysis.
3. Keep Gini for direct comparison with Panagariya and Bagaria and show active product count beside it.
4. Keep HHI as a robustness and dominant-product diagnostic, not as the sole headline index.
5. Report level and change correlations separately.
6. Label cadot_broad_156 as a research sample and avoid causal language.

