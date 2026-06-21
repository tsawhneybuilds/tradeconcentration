# Which Trade-Concentration Measure Should Be the Headline?

## Recommendation

Use the **fixed-universe Theil index as the primary measure** when the research question is how product diversification changes across countries and over time. Retain the **active-product Gini as the main replication and comparability measure** for Panagariya and Bagaria (2013), and use **HHI as a robustness diagnostic for dominance by the largest products**.

This is not a recommendation to discard Gini. It is a recommendation to match the measure to the estimand:

| Measure | Construction in this project | What it answers best | Recommended role |
|---|---|---|---|
| Gini | Inequality of positive product trade values, bounded near 0 to 1 | How unequal is trade value among products that are actually traded? | Panagariya-Bagaria benchmark and Lorenz presentation |
| Fixed-universe Theil | T = sum(s_p log(s_p K)) = T_active + log(K / A), with K = 5,037 harmonized products | How concentrated is the full potential product basket, and how much comes from inactive versus active products? | Primary measure for diversification and development dynamics |
| HHI | HHI = sum(s_p squared), bounded 0 to 1 | How strongly do the largest product shares dominate total trade? | Robustness and dominant-product diagnostic |

Higher values mean greater product concentration for all three measures. Product-dependent construction excludes HS6 999999, “Commodities not specified,” before LT/HGL conversion and aggregation. The unit of observation is reporter-year-flow.

## What the Literature Supports

Panagariya and Bagaria (2013) use Lorenz curves and Gini coefficients to document pervasive inequality of trade value across strictly positive products and partners. This makes active-product Gini the correct direct comparison to their paper.

Cadot, Carrere, and Strauss-Kahn (2011) calculate Gini, Herfindahl, and Theil measures and report similar fitted concentration patterns, but focus on Theil because its additive decomposition maps the extensive and intensive margins. Hummels and Klenow (2005) separately show why these margins have distinct economic content, finding that the extensive margin accounts for about 60 percent of larger economies' greater exports.

Sources: [Panagariya and Bagaria (2013)](https://researchonline.lse.ac.uk/49167/), [Cadot, Carrere, and Strauss-Kahn (2011)](https://archive-ouverte.unige.ch/unige%3A46586), and [Hummels and Klenow (2005)](https://www.aeaweb.org/articles?id=10.1257%2F0002828054201396).

## Correlation Evidence

Spearman correlation is itself a rank correlation. Pearson correlation computed on average ranks is therefore numerically identical here.

| Flow | Gini-Theil | Gini-HHI | Theil-HHI | Observations |
|---|---:|---:|---:|---:|
| All | 0.918386 | 0.836245 | 0.952105 | 7,509 |
| Exports | 0.828674 | 0.824950 | 0.978662 | 3,753 |
| Imports | 0.910170 | 0.763563 | 0.902026 | 3,756 |

The level correlations show that the broad country ordering is robust. The metrics are less interchangeable for annual changes:

| Flow | Gini-Theil | Gini-HHI | Theil-HHI |
|---|---:|---:|---:|
| Exports, first differences | 0.707412 | 0.519351 | 0.864074 |
| Imports, first differences | 0.877756 | 0.704252 | 0.901881 |

The weaker export change correlations, especially Gini-HHI, mean that pooled level correlations should not be used to choose an index mechanically.

## Dispersion and 2024 Country Values

Raw standard deviations and ranges are not comparable across metrics because their scales differ. They are reported below for within-metric context. Country ranks are among the 132 reporters observed in 2024, with rank 1 denoting the most concentrated.

| Flow | Metric | SD, 2000-2024 | Range, min-max | USA 2024, rank | India 2024, rank | China 2024, rank |
|---|---|---|---|---|---|---|
| Exports | Gini | 0.042107 | 0.028445-0.998936 | 0.884652, 120 | 0.894430, 119 | 0.845128, 131 |
| Exports | Theil | 1.586360 | 1.647899-8.469358 | 2.391982, 122 | 2.785642, 106 | 1.959041, 130 |
| Exports | HHI | 0.174709 | 0.002813-0.987253 | 0.010162, 110 | 0.022145, 92 | 0.005388, 129 |
| Imports | Gini | 0.029458 | 0.795887-0.981636 | 0.873845, 96 | 0.916164, 26 | 0.938412, 9 |
| Imports | Theil | 0.604046 | 1.641979-6.586082 | 2.286003, 103 | 3.382310, 18 | 3.428246, 17 |
| Imports | HHI | 0.027739 | 0.002367-0.440610 | 0.008807, 102 | 0.052979, 10 | 0.031244, 21 |

The three measures tell the same broad 2024 story. China is among the least concentrated exporters but among the most concentrated importers. India is also much more concentrated on imports than exports. The United States is relatively diversified on both sides and is more diversified relative to peers on exports. HHI places India above China for import concentration because HHI disproportionately weights the largest individual shares, while Gini and Theil place China slightly above India because they respond to the whole distribution.

The export Gini range needs a specific caveat. Its minimum, 0.028445, is Comoros in 2007, when only three products were active. The fixed-universe Theil for that observation is 7.427370, almost entirely due to the inactive-product component. This example shows why active Gini alone cannot represent the extensive margin.

## Economist Council Verdict

The trade-measurement, econometric, inequality, industrial-organization, policy, and writing perspectives agree on the reporting hierarchy:

- The strongest version of the project uses fixed-universe Theil as the headline measure because the substantive question concerns diversification across the potential product basket.
- Gini remains essential for direct continuity with Panagariya and Bagaria and for intuitive Lorenz-curve communication.
- HHI should answer the narrower question of top-product dominance.
- The main threat is specification drift caused by discussing all three as if they used the same universe and estimand.
- The best next test is to re-estimate every dynamic or development-path result with all three outcomes and report whether signs, turning points, and within-country conclusions survive.

## Draft Response to Professor Panagariya

Professor Panagariya,

I compared Gini, fixed-universe Theil, and HHI on a common harmonized HS1992 product panel for 156 countries over 2000-2024, excluding HS6 999999 before product aggregation. The three measures produce broadly similar country rankings: pooled Spearman correlations are 0.918 for Gini-Theil, 0.836 for Gini-HHI, and 0.952 for Theil-HHI. The agreement is weaker for annual export changes, particularly Gini-HHI at 0.519, so I would not treat the measures as interchangeable.

My recommendation is to use the fixed-universe Theil index as the main measure for the diversification analysis, while retaining Gini as the direct Panagariya-Bagaria benchmark and HHI as a robustness measure for top-product dominance. The reason is conceptual. The current Gini measures inequality among products with positive trade, which matches the original paper's Lorenz-curve question. The fixed-universe Theil also incorporates inactive products and decomposes exactly into an active-product component and an inactive-product margin, which matches the Cadot extensive-versus-intensive framework.

The 2024 country comparison is substantively stable across measures. China ranks 131st, 130th, and 129th out of 132 countries in export concentration under Gini, Theil, and HHI, respectively, but 9th, 17th, and 21st in import concentration. India ranks 119th, 106th, and 92nd for exports, versus 26th, 18th, and 10th for imports. The United States ranks 120th, 122nd, and 110th for exports, and 96th, 103rd, and 102nd for imports. Thus, China and India are relatively diversified exporters but concentrated importers, while the United States is relatively diversified on both sides.

I would therefore present one headline result using fixed-universe Theil, show Gini beside it for continuity with the original paper, and use HHI only as a sensitivity check. I would also report active product counts with Gini so that an economy with very few but similarly sized active products is not incorrectly described as broadly diversified.
