# What the combined evidence now says about Cadot

Prepared for advisor discussion

## Bottom line

Cadot's hump survives in our work as a **modern cross-country product-composition fact**, not as a robust law describing how the typical country changes as it becomes richer.

The cleanest modern results are between countries. Export Product Gini and Theil decline across low- and middle-income economies and bend upward among rich economies in level-PPP specifications. But country fixed effects remove the export Gini and Theil humps, the turning point moves from Cadot's roughly $25,000 benchmark to about $73,000–$79,000 in constant-2021 PPP dollars, and the result is sensitive to level versus log income.

The mechanism also changes. Product exit consistent with Cadot's old-cone story is detectable, but continuing-product or superstar scaling is much more common. Finally, neither modern nor 1827–2014 historical partner concentration shows the same U-shape. The evidence therefore narrows Cadot's claim to a product-specific cross-sectional regularity.

## The econometric reading

The pooled and between estimands compare different countries at different development levels. They do not identify the path a country follows when its own income rises.

That distinction is quantitatively important. In the 135-country modern analytic panel, between-country differences account for 73.2% of Export Product Gini variation, 94.1% of Export Product Theil variation, and 81.1% of Export Product HHI variation. Once persistent country effects are removed, the export Gini and Theil curves disappear.

This does not make the cross-country curve fake. The positive between-country quadratic survives every leave-one-country-out regression. For Gini, the implied turning point remains between about $69,600 and $74,600 across all 135 country omissions. Excluding sub-million-population economies or countries with oil export shares above one-half also does not remove the curve, although it moves the estimated turning point. The right interpretation is therefore:

> The between-country curve is a stable descriptive equilibrium relationship across country types, but it is not evidence of a common within-country development transition.

## What is probably generating the cross-country pattern

The most plausible account combines four forces.

First, many low-income countries have narrow baskets because exports are dominated by a few commodities or because productive capabilities are limited. Second, middle-income industrialization expands the number and balance of manufacturing lines. Third, the rich-country tail mixes broad industrial exporters with highly specialized oil exporters, entrepôts, microstates, financial and tax hubs, and economies dominated by globally successful products. The countries above roughly $70,000 mean PPP income in the analytic sample are Switzerland, UAE, Ireland, Brunei, Bermuda, Singapore, Macao, Qatar, and Luxembourg. They are not representative later-life versions of the average middle-income country.

Fourth, size and world demand shape the product basket. In the 156-reporter exposure analysis, larger economies are more exposed to products that are large in world trade, and their within-country product rankings align more closely with the world product ranking. The relationship remains after broad primary commodities are removed. This is consistent with scale, global demand, and superstar products affecting concentration independently of an income-stage pruning mechanism.

The mechanism tribunal points in the same direction. Among 472 modern five-year reconcentration episodes, 59.7% are flagged for continuing-product superstar scaling, 27.1% for commodity spikes, 26.3% for Section 16 or HS-design sensitivity, and 20.6% for old-cone pruning. Flags overlap, but the mass of the evidence is not primarily extensive-margin product exit.

## Is the result an artifact of the era?

Not in the simple sense.

The product curve appears in modern 2000–2024 data, so it is not confined to Cadot's 1988–2006 period. But the modern turning point is much higher, the export curve is weak within countries, and the dominant reconcentration mechanism is different. Period and construction therefore matter for magnitude and interpretation.

The historical result needs a careful label. Our 1827–2014 panel measures concentration across trading partners, not products. It finds zero supported U-shapes across the six preferred tests and zero across 168 within-country sensitivity tests, including pre/post-1948 source regimes and wartime exclusions. This shows that a generic “development eventually reconcentrates trade” law is absent over a very long horizon.

It does **not** answer whether a Cadot-style product hump existed historically. The implemented 1939/postwar bridge is a partner-data and source-regime bridge, not a harmonized product panel. A matched product-period bridge remains necessary before calling the original result an era-specific artifact.

## What I would claim

The strongest defensible claim is:

> Cadot identifies a real cross-country association between development and product diversification, but our modern evidence does not support a universal within-country reconcentration law. The rich-country branch appears to reflect persistent differences in scale, specialization, global-product exposure, and country type, with continuing-product scaling more common than product-line exit. The absence of a comparable pattern in modern and long-run partner concentration shows that the hump is specific to the product margin rather than a general law of trade concentration.

I would not claim:

- that the original 1988–2006 result has been literally replicated;
- that income causally produces diversification and reconcentration;
- that the modern turning point is precisely estimated;
- that old-cone product exit is the dominant mechanism;
- or that the historical partner null disproves the historical product claim.

## Figures and website sections

Each link below answers one question.

1. **Does pooled modern product concentration bend upward at high income?**
   [Gini and Theil with linear, quadratic, and nonparametric fits](../samples/cadot_broad_156/cadot_broad_ppp_hump_regression_figures/export_gini_theil_linear_quadratic_lowess.png)

2. **Does the historical partner panel pass a formal U-shape test?**
   [No baseline partner measure passes](../historical_partner_concentration/figures/advisor/baseline_u_shape_tests.png)

3. **How do pooled and country-fixed-effect results differ?**
   [PPP hump results](https://tsawhneybuilds.github.io/trade-gini-map-old/cadot-hump.html#cadot-ppp-results) and [pooled versus country fixed effects](https://tsawhneybuilds.github.io/trade-gini-map-old/cadot-hump.html#cadot-pooled-country-fe)

4. **What mechanism is most common in modern reconcentration episodes?**
   [Mechanism scorecard](https://tsawhneybuilds.github.io/trade-gini-map-old/cadot-hump.html#cadot-mechanisms) and [old-cone evidence](https://tsawhneybuilds.github.io/trade-gini-map-old/cadot-hump.html#cadot-old-cone)

5. **Do larger economies align more closely with globally large products?**
   [World-product exposure and alignment panels](https://tsawhneybuilds.github.io/trade-gini-map/exposure/#exposure-gdp-alignment)

6. **Is partner concentration moving strongly over time in the modern panel?**
   [Partner-stability common-trend evidence](https://tsawhneybuilds.github.io/trade-gini-map-old/partner-stability.html#partner-stability-common-trend)

## Economist-council verdict

The identification view says to stop calling the pooled curve a within-country development law. The trade view says the cross section is still economically meaningful because equilibrium country types differ in comparative advantage, scale, geography, institutions, and GVC position. The mechanism view says the model must allow both product exit and superstar scaling. The economic-history view says the era question remains open until products are measured consistently across periods. The policy view says concentration itself is not a welfare target: specialization in successful products and vulnerability to commodities are economically different.

The council's common ground is that the contribution is a refinement rather than a rejection of Cadot.

## Evidence files

- `cadot-replication.md`
- `results/samples/cadot_broad_156/cadot_broad_ppp_hump_regression_tables/ppp_hump_regression_summary.csv`
- `results/samples/rd2_countries/cadot_hump_tribunal_tables/mechanism_scorecard_summary.csv`
- `results/samples/cadot_broad_156/world_large_product_exposure_tables/world_large_product_exposure_models.csv`
- `results/historical_partner_concentration/cadot_model_summary.csv`
- `results/prof_p_replication/cadot_between_country_diagnostics/`
