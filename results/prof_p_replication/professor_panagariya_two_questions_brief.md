# Two Questions: Large Countries, World Demand, And The GDP-Per-Capita Hump

Prepared: 2026-06-18

Recipient: Professor Panagariya

## Short Answer

Yes. Both checks exist.

1. Larger-GDP countries usually export more globally large products.
2. The pooled regressions show a GDP-per-capita hump.
3. The within-country evidence is weaker.

## Question 1: Do Large Countries Export More World-Demanded Products?

The dedicated output is `results/samples/rd2_countries/world_large_product_exposure_tables/world_large_product_exposure.md`.

Sample and construction:

- Sample: `rd2_countries`, exports, 2000-2024.
- Product rule: HS6 `999999`, "Commodities not specified", is excluded before product aggregation.
- Main measure: `world_share_exposure = sum_p s_cpt * rank_percentile(w_pt)`, where `s_cpt` is country `c`'s export share in product `p` in year `t`, and `w_pt` is product `p`'s share in inclusive world exports in year `t`.
- Plain English: the measure is higher when a country puts more export weight on products that are large in the world basket.

Evidence:

| Result | Estimate |
|---|---:|
| GDP rank correlation with world-product exposure, mean Spearman across years | 0.309 |
| GDP rank correlation with world-product exposure, median Spearman across years | 0.364 |
| Share of years with positive GDP-world exposure correlation | 92% |
| Within-country product-rank alignment diagnostic, mean Spearman | 0.777 |
| Main year-FE regression: log GDP coefficient | **0.0086** |
| Main year-FE regression: standard error | 0.0030 |
| Main year-FE regression: raw p-value | **0.0058** |
| Main year-FE regression: observations / country clusters | 1,482 / 60 |
| Conditional model with GDP per capita: log GDP coefficient | 0.0039 |
| Conditional model with GDP per capita: raw p-value | 0.163 |

![The annual GDP-world-product correlation was positive in 23 of 25 years](figures/large_economies_world_product_exposure.png)

[PDF attachment](figures/large_economies_world_product_exposure.pdf)

Interpretation:

The annual correlation is positive in 23 of 25 years.

The mean annual correlation is 0.309.

The correlations are negative in 2023 and 2024.

The year-FE GDP coefficient is 0.0086.

Its raw p-value is 0.0058.

The conditional GDP coefficient is 0.0039.

Its raw p-value is 0.163.

The estimates support a descriptive association.

The estimates do not identify a mechanism.

### Product-Rank Alignment By Year

![GDP-product-rank alignment remained above 0.72 in every year](figures/yearly_within_country_product_rank_alignment.png)

[PDF attachment](figures/yearly_within_country_product_rank_alignment.pdf)

The annual GDP-alignment correlation is positive in every year.

The mean annual correlation is 0.777.

The maximum is 0.836 in 2002.

The minimum is 0.726 in 2007.

The 2024 correlation is 0.755.

## Question 2: Do We See The GDP-Per-Capita Hump Within Countries?

The main outputs are `results/samples/cadot_broad_156/cadot_broad_ppp_hump_regressions.md` and `results/samples/rd2_countries/ppp_hump_regression_tables/ppp_hump_country_fe_robustness.csv`.

Sample and construction:

- Income variable: World Bank `NY.GDP.PCAP.PP.KD`, GDP per capita at PPP in constant 2021 international dollars.
- Broad sample: modern `cadot_broad_156` sample, 2000-2024; 135 analytic countries after complete-case controls.
- Regression form: concentration on income, income squared, log population, oil-export share, and year fixed effects; country+year-FE variants add reporter fixed effects.
- Product outcomes exclude HS6 `999999`, "Commodities not specified", before aggregation.
- Plain English: a positive quadratic in a concentration outcome is a U-shape: concentration first falls with income and then rises after the turning point.

Broad-sample evidence:

| Outcome and specification | Quadratic estimate | Raw p-value | Turning point | Read |
|---|---:|---:|---:|---|
| Export Product Gini, pooled/year FE, level PPP | **0.000867** | **0.000045** | $78.5k | Significant but edge-sensitive |
| Export Product Gini, country+year FE, level PPP | 0.000016 | 0.933 | $471.1k | No within-country hump |
| Import Product Gini, pooled/year FE, level PPP | **0.001112** | **0.000000023** | $65.0k | Clear hump |
| Import Product Gini, country+year FE, level PPP | **0.000340** | **0.021** | $76.0k | Significant but edge-sensitive |
| Import Product Theil, pooled/year FE, level PPP | **0.018671** | **0.0000067** | $67.4k | Clear hump |
| Import Product Theil, country+year FE, level PPP | 0.006455 | 0.080 | $98.5k | No clean hump |

`rd2_countries` country-FE robustness:

| Outcome and specification | Quadratic estimate | Raw p-value | Turning point | Read |
|---|---:|---:|---:|---|
| Export Product Gini, country+year FE, level PPP | 0.000377 | 0.068 | $61.7k | Borderline, not clean |
| Import Product Gini, country+year FE, level PPP | 0.000314 | 0.214 | $18.6k | Not statistically clean |

![The export hump disappears after country fixed effects](figures/gdp_per_capita_hump_country_fixed_effects.png)

[PDF attachment](figures/gdp_per_capita_hump_country_fixed_effects.pdf)

Interpretation:

The pooled export quadratic is positive.

Its raw p-value is 0.000045.

The export country-FE quadratic is near zero.

Its raw p-value is 0.933.

The pooled import quadratic is positive.

Its turning point is USD 65.0k.

The import country-FE quadratic remains positive.

Its raw p-value is 0.021.

Its turning point is above the sample's 95th income percentile.

The pooled evidence supports a development-stage pattern.

The evidence does not establish a robust within-country reconcentration law.

## Professor-Ready Wording

Dear Professor Panagariya,

We have run both checks.

Larger economies were more exposed to globally large products in 23 of 25 years.

The mean annual Spearman correlation was 0.31.

The product-rank alignment diagnostic is positive in every year.

Its mean annual correlation is 0.777.

The year-fixed-effect GDP coefficient was 0.0086.

Its raw p-value was 0.0058.

The coefficient fell to 0.0039 after controlling for GDP per capita.

Its raw p-value was 0.163.

These estimates show a descriptive association.

They do not identify a mechanism.

The level-PPP regressions show product-concentration U-shapes.

The pooled evidence is strongest for imports.

Country fixed effects remove the broad-sample export hump.

The export quadratic has a raw p-value of 0.933 under country fixed effects.

The import quadratic remains positive under country fixed effects.

Its turning point lies above the 95th percentile of observed income.

The evidence supports a pooled development-stage pattern.

It does not establish a robust within-country reconcentration law.

Best,

[Your Name]

## Validation And Caveats

- Figure builder: `scripts/build_professor_panagariya_two_questions_figures.py`.
- Rebuild command: `python3 scripts/build_professor_panagariya_two_questions_figures.py`.
- World-large product exposure adversarial review: `results/samples/rd2_countries/world_large_product_exposure_tables/adversarial_review.md`.
- Broad PPP hump adversarial review: `results/samples/cadot_broad_156/cadot_broad_ppp_hump_regression_tables/adversarial_review.md`.
- The exposure and hump results are descriptive associations, not causal estimates.
- The GDP-per-capita hump should be labeled as descriptive.
- The broad PPP result is a modern extension, not a literal replication of Cadot's original 1988-2006 design.
- Raw p-values below 0.05 are bolded in the tables above; no multiple-testing-adjusted q-values are claimed as passing unless separately reported.
