# Cadot replication, modern extensions, and long-run boundary tests

Last updated: 2026-06-20

## Executive conclusion

Our work does not support either of the simple statements “Cadot replicates” or “Cadot fails.” The evidence supports a narrower conclusion:

1. We reproduce strong **pooled level-PPP curvature and between-country product-concentration patterns** in modern 2000–2024 data. Export Gini, Theil, HHI, and active counts bend in the expected direction, but the cleanest in-support results are the between-country Gini, Theil, and active-count curves.
2. We do **not** find a robust **within-country export reconcentration law**. Country fixed effects remove the modern export Gini and Theil humps, estimated export turning points are generally at or beyond common income support, and the result is sensitive to whether income enters in levels or logs.
3. The mechanism differs from Cadot's strongest interpretation. In the modern episode classification, continuing-product or “superstar” scaling is much more common than old-cone product exit. There is a statistically clean old-cone-consistent exit interaction, but it does not account for most reconcentration episodes.
4. The pattern is about **products**, not concentration in general. Modern partner Gini does not show a level-PPP hump, and the new 1827–2014 historical partner panel produces zero supported U-shapes across six baseline and 168 sensitivity tests.
5. We have **not completed a literal replication of the original 1988–2006 study**. The exact 156-country list, mirror-export construction, and original 4,991-line HS0 universe remain unrecovered. The modern evidence can test external validity and mechanisms, but it cannot establish that the original published result was a data artifact.

The most defensible statement is therefore:

> Cadot's diversification hump remains visible as a modern cross-country product pattern, but our results do not support interpreting it as a universal within-country development law or as a generic law applying to trading partners. The modern export turning point is substantially higher than Cadot's benchmark and is often weakly supported by the observed rich-country tail.

## 1. What the original Cadot paper claims

Cadot, Carrère, and Strauss-Kahn (2011) study export diversification across 156 countries from 1988 through 2006 using 4,991 Harmonized System six-digit product lines. Their main claims are:

- Product concentration follows a U-shape in GDP per capita: countries diversify and later reconcentrate.
- The number of active export products follows the inverse pattern.
- The turning point is roughly PPP $25,000 in constant 2005 international dollars, with individual specifications reported around that range.
- The pattern appears in pooled, between-country, and within-country estimates.
- Reconcentration is explained primarily by the extensive margin: rich countries close product lines that no longer fit their comparative advantage or “diversification cone.”
- The result is not explained away by oil exporters, microstates, Harmonized System design, or Section 16 machinery/electronics products.

Their exercise is descriptive. It characterizes the conditional income–diversification relationship; it does not identify a causal effect of income on product concentration.

Source used for the research target: `literature/export_margins/wiki/papers/06_cadot_carrere_strauss_kahn_2011_export_diversification_hump.md`.

## 2. Terminology: what counts as replication

We use four labels consistently:

- **Literal replication:** original period, country universe, mirror-trade rule, harmonized product universe, variables, and specifications.
- **Reconstruction:** an explicitly documented approximation to the original design when an original input is unavailable.
- **Modern extension:** the same economic question tested on modern data with transparent changes in measurement, sample, or PPP vintage.
- **Boundary test:** a related but different outcome used to determine how broadly the mechanism travels. Partner concentration is a boundary test, not a product-diversification replication.

Only the second through fourth categories have been completed. The literal replication remains blocked.

## 3. Work completed

### 3.1 Original-artifact and source audit

Scripts:

- `scripts/recover_cadot_original_status.py`
- `scripts/run_cadot_replication_technical_audit.py`

Outputs:

- `results/cadot_replication_audit/cadot_replication_technical_audit.md`
- `results/cadot_replication_audit/cadot_replication_source_audit.csv`
- `results/cadot_replication_audit/cadot_replication_artifact_inventory.csv`
- `results/cadot_replication_audit/cadot_replication_rebuild_manifest.json`
- `results/samples/cadot_original_1988_2006/cadot_original_status.json`
- `results/samples/cadot_original_countries_extended/cadot_original_status.json`

The source audit searched the article and working-paper trails, World Bank repositories, RePEc/IDEAS, SSRN, HAL/CERDI, MIT Press, and targeted replication-package queries. No usable public replication bundle was located. This does not prove that no private package exists.

The literal original tracks are marked `blocked_not_exact_replication` for three reasons:

1. The exact pre-exclusion 156-country list has not been recovered. The paper identifies 141 countries in the non-microstate regression sample but does not provide a machine-readable full list in the sources inspected.
2. The original mirror-import-to-exporter construction is not implemented for 1988–2006.
3. The original 4,991-line HS0 fixed universe has not been reproduced exactly from the available concordances.

No output from the modern `cadot_broad_156` sample should be labeled a literal replication.

### 3.2 Modern 156-reporter concentration reconstruction

Primary script:

- `scripts/run_cadot_three_metric_pipeline.py`

Canonical command:

```bash
python scripts/run_cadot_three_metric_pipeline.py \
  --country-sample cadot_broad_156 \
  --simulations 250 \
  --chunk-rows 1000000 \
  --manifest-every 25
```

Data and sample:

- UN Comtrade annual final-data files, 2000–2024.
- 156 selected reporter entities with at least 19 available Harmonized System years.
- 3,787 raw reporter-year files processed.
- Product codes converted using LT/HGL weighted harmonization to HS1992/H0 product families.
- Harmonization source: version 2.1, DOI `10.7910/DVN/6AADMR`.
- Fixed product support: the 2000–2024 union of positive `world_broad` harmonized products, 5,037 products for both exports and imports.
- Product-dependent calculations exclude HS6 `999999` (“Commodities not specified”) before conversion and aggregation.
- Partner calculations sum over product identity and therefore include `999999` by project convention; partner code 0 (“World”) is excluded.

Constructed measures for reporter (c), year (t), flow (f), and product values (x_i):

- Active-positive Gini: inequality across observed positive product values. Higher values mean more concentration among active products.
- Fixed-universe Theil: \(T_{ctf}=\sum_{i:s_i>0}s_i\log(s_iK_f)\), where \(K_f=5,037\). It incorporates the inactive-product margin through the fixed universe.
- Raw HHI: \(HHI_{ctf}=\sum_i s_i^2\), bounded by zero and one.
- Active-product count: number of products with positive trade.

The output contains 7,509 common product reporter-year-flow observations: 3,753 exports and 3,756 imports. Rank correlations show that the measures are related but not identical:

| Flow | Measures | Spearman correlation | Observations |
| --- | --- | ---: | ---: |
| Exports | Gini–Theil | 0.829 | 3,753 |
| Exports | Gini–HHI | 0.825 | 3,753 |
| Exports | Theil–HHI | 0.979 | 3,753 |
| Imports | Gini–Theil | 0.910 | 3,756 |
| Imports | Gini–HHI | 0.764 | 3,756 |
| Imports | Theil–HHI | 0.902 | 3,756 |

All 11 published construction checks pass: reporter count, `999999` exclusion, harmonized product identities, world-universe containment, unique keys, HHI bounds, fixed-universe counts, Theil decomposition, cross-metric key parity, raw-file coverage, and exclusion-table uniqueness.

Primary output directory: `results/samples/cadot_broad_156/three_metric_tables/`.

### 3.3 Modern constant-PPP hump regressions

Scripts:

- `scripts/run_ppp_hump_regressions.py`
- `scripts/run_cadot_broad_ppp_hump_regressions.py`
- `scripts/validate_cadot_broad_ppp_regressions.py`
- `code/replication/referee2_replicate_cadot_ppp.py`

Broad-sample command:

```bash
python scripts/run_cadot_broad_ppp_hump_regressions.py
python scripts/validate_cadot_broad_ppp_regressions.py
```

Regression sample and model:

- Selected universe: 156 reporters.
- Complete-case regression sample: 135 countries, 3,240 export observations and 3,236 import observations.
- Income: World Bank `NY.GDP.PCAP.PP.KD`, real GDP per capita in constant 2021 international dollars.
- Controls: log population and oil-export share.
- Pooled model: year fixed effects, country-clustered standard errors.
- Within model: country and year fixed effects, country-clustered standard errors.
- Between model: one country-mean observation, HC1 heteroskedasticity-robust standard errors.
- Income forms: level GDP per capita scaled by 10,000 and log GDP per capita; each includes a squared term.

The model is descriptive:

\[
C_{ct}=\beta_1 y_{ct}+\beta_2y_{ct}^2+\gamma\log(pop_{ct})+\theta oil_{ct}+\delta_t+u_{ct}.
\]

A positive quadratic in a concentration outcome is not sufficient by itself. The turning point must lie inside meaningful support and the slope must change from negative to positive. The broad runner labels whether the point lies inside the sample minimum–maximum and p05–p95 ranges, but it predates the later formal Lind–Mehlum/bootstrap implementation used in the historical partner analysis.

#### Level-PPP results

| Outcome | Estimator | Quadratic | Raw p | Turning point | Inside p05–p95? | Interpretation |
| --- | --- | ---: | ---: | ---: | --- | --- |
| Export Product Gini | Pooled/year FE | **0.000867** | **0.000045** | $78,520 | No | Statistical bend at rich edge |
| Export Product Gini | Country+year FE | 0.000016 | 0.933 | $471,105 | No | No within-country hump |
| Export Product Gini | Between countries | **0.001026** | **0.000004** | $72,605 | Yes | Clear between-country hump |
| Export Product Theil | Pooled/year FE | **0.041273** | **<0.000001** | $78,227 | No | Statistical bend at rich edge |
| Export Product Theil | Country+year FE | -0.002264 | 0.608 | $170,072 | No | No within-country hump |
| Export Product Theil | Between countries | **0.048584** | **0.000006** | $73,212 | Yes | Clear between-country hump |
| Export Product HHI | Pooled/year FE | **0.002556** | **0.000433** | $78,981 | No | Statistical bend at rich edge |
| Export Product HHI | Country+year FE | **-0.001660** | **0.0276** | $123,029 | No | Significant curvature in the wrong direction |
| Export active-product count | Pooled/year FE | **-51.199** | **<0.000001** | $78,198 | No | Active-line peak at rich edge |
| Export active-product count | Country+year FE | **-12.279** | **0.0021** | $95,322 | No | Peak outside central support |
| Import Product Gini | Pooled/year FE | **0.001112** | **<0.000001** | $64,971 | Yes | Clear pooled hump |
| Import Product Gini | Country+year FE | **0.000340** | **0.0210** | $76,025 | No | Within bend at rich edge |
| Import Product Theil | Pooled/year FE | **0.018671** | **0.000007** | $67,374 | Yes | Clear pooled hump |
| Import Product Theil | Country+year FE | 0.006455 | 0.080 | $98,461 | No | No clean within hump |
| Import Product HHI | Pooled/year FE | 0.000200 | 0.131 | $83,756 | No | No clean hump |
| Import active-product count | Pooled/year FE | **-26.028** | **<0.000001** | $74,825 | No | Active-line peak at edge |
| Export Partner Gini | Pooled/year FE | -0.000083 | 0.678 | $309,273 | No | No partner hump |
| Export Partner Gini | Country+year FE | 0.000264 | 0.234 | $97,194 | No | No partner hump |
| Import Partner Gini | Pooled/year FE | -0.000242 | 0.264 | $102,957 | No | No partner hump |
| Import Partner Gini | Country+year FE | **-0.000332** | **0.0491** | $82,551 | No | Curvature in the wrong direction |

The broad sample's p95 income is about $74,162. The modern pooled export turning points of approximately $78,000–$79,000 are therefore above central support and far above Cadot's roughly $25,000 benchmark. The between-country estimates are cleaner because their turning points are mostly inside the cross-country support.

#### Functional-form sensitivity

The export result is not stable when GDP per capita enters in logs:

- Export Product Gini has no hump in pooled, within, or between log-income models.
- Export Product Theil retains positive pooled curvature, but its estimated turning point is roughly $283,000 and outside support; the within quadratic has raw p = 0.083.
- Export Product HHI has positive pooled curvature with raw p = 0.016, but the turning point is about $105,000 and outside p05–p95.
- Import Product Gini and Theil are more stable in pooled and between models. Import Gini's country-FE log-income quadratic has raw p = 0.025, but its approximately $82,900 turning point remains beyond p95.

This is substantive sensitivity, not a cosmetic rescaling. Quadratic models in levels and logs impose different global shapes.

#### rd2 balanced-sample cross-check

The `rd2_countries` balanced panel has 55 countries and 1,375 country-years from 2000–2024. In pooled level-PPP regressions:

- Export World-Relative Product Gini: quadratic **0.004921**, raw p **<0.000001**, turning point $78,574 inside p05–p95.
- Export Product Gini: quadratic **0.001326**, raw p **0.000024**, turning point $75,806 inside p05–p95.
- Import Product Gini: quadratic **0.001459**, raw p **0.000006**, turning point $64,504 inside p05–p95.
- Export Partner Gini: quadratic -0.000006, raw p 0.978; no level-PPP hump.
- Import Partner Gini: quadratic 0.000036, raw p 0.867; no level-PPP hump.

After country fixed effects:

- Export World-Relative Product Gini retains a positive quadratic with raw p **0.0066**, but its $88,450 turning point is above p95.
- Export Product Gini becomes borderline: raw p = 0.0678, turning point $61,678.
- Import Product Gini is not significant in levels: raw p = 0.214.
- Product and partner conclusions remain sensitive to income form.

An independent statsmodels re-estimation from the saved panels reproduced selected coefficients and clustered standard errors to numerical precision. No R or Stata cross-language replication was completed because those executables were unavailable in that pass.

Primary outputs:

- `results/samples/cadot_broad_156/cadot_broad_ppp_hump_regression_tables/ppp_hump_regression_summary.csv`
- `results/samples/cadot_broad_156/cadot_broad_ppp_hump_regression_tables/ppp_hump_regression_models.csv`
- `results/samples/rd2_countries/ppp_hump_regression_tables/ppp_hump_country_fe_robustness.csv`

### 3.4 Mechanism tribunal

Script:

- `scripts/run_cadot_hump_tribunal.py`

Command:

```bash
python scripts/run_cadot_hump_tribunal.py --country-sample rd2_countries --start-year 2000 --end-year 2024
```

The tribunal uses the balanced 55-country export panel and asks whether observed five-year reconcentration episodes are consistent with:

- commodity or oil spikes;
- Section 16 or Harmonized System design sensitivity;
- old-cone pruning through product exit;
- continuing-product superstar scaling; or
- none of the classified mechanisms.

It classifies 472 reconcentration episodes among 1,045 five-year country windows. Flags can overlap.

| Mechanism flag | Episodes | Share of reconcentration episodes |
| --- | ---: | ---: |
| Continuing-product superstar scaling | 282 | 59.7% |
| Commodity spike | 128 | 27.1% |
| Section 16 / HS-design sensitivity | 124 | 26.3% |
| Old-cone pruning | 97 | 20.6% |
| Broad unexplained reconcentration | 67 | 14.2% |

The old-cone regression uses 831,633 HS4 product windows. It is a linear probability model with reporter, product, and base-year fixed effects, clustered by reporter. The interaction between income–PRODY mismatch and being above the fixed PPP $25,000 rich-side threshold is **0.0234**, with raw p **0.000813**. This is consistent with mismatched products being more likely to exit on the rich side.

However, the PRODY measure is a leave-one-out proxy constructed within the 55-country `rd2` sample, not a fully global sophistication measure. Native HS4 transition windows also cross product-revision environments less cleanly than the harmonized country-year concentration measures. The mechanism result is therefore suggestive, not structural identification.

The aggregate episode evidence does not reproduce Cadot's strongest mechanism claim that reconcentration is explained entirely or mostly by extensive-margin product exit. In the modern sample, continuing-product value reallocation is the dominant flag.

Primary outputs: `results/samples/rd2_countries/cadot_hump_tribunal_tables/`.

### 3.5 Non-energy and product-composition diagnostics

Scripts:

- `scripts/build_cadot_nonenergy_visualization.py`
- `scripts/run_world_large_product_exposure.py`

The non-energy import build retains only approved BEC capital-goods, intermediate, and final-consumption source products before LT/HGL conversion. It produces 3,756 annual observations for all 156 reporters and a 4,924-product fixed universe. An independent fresh-agent review recomputed selected raw files and all three concentration measures and cleared the output for descriptive use.

The world-product exposure exercise asks whether large economies place more export weight on products that are large in the world basket. For the 156-reporter sample, the year-FE association between log current GDP and the exposure index is **0.0167** with raw p **<0.000001** and BH q **<0.000001**; the non-commodity version is **0.0112**, also with raw p and q **<0.000001**. These are descriptive scale associations, not causal estimates.

This evidence matters for interpretation because it supplies an alternative to a pure income-stage mechanism: country size and alignment with globally large products can generate concentrated high-value export baskets. It does not, by itself, explain the quadratic income pattern.

Primary outputs:

- `results/samples/cadot_broad_156/three_metric_tables/nonenergy_import_metric_annual.csv`
- `results/samples/cadot_broad_156/world_large_product_exposure_tables/world_large_product_exposure_models.csv`

### 3.6 Historical 1827–2014 partner-concentration boundary test

Scripts:

- `scripts/build_historical_partner_concentration.py`
- `scripts/run_historical_partner_cadot.py`
- `scripts/build_historical_partner_advisor_results.py`

Data:

- CEPII TRADHIST bilateral flows, 1827–2014.
- France, Denmark, Sweden, Norway, Netherlands, Spain, Portugal, United Kingdom, United States, Argentina, Uruguay, Russian Empire/USSR, and Russian Federation.
- Russian Empire/USSR ends in 1991; Russian Federation begins in 1992. They are never concatenated for estimation.
- Maddison Project Database 2023 real GDP per capita in constant 2011 PPP dollars and population.
- 2,238 entity-years, or 4,476 entity-year-flow observations before model restrictions.
- Concentration across positive observed bilateral partners; absent historical dyads are not converted to zero.
- Baseline concentration requires at least 20 active partners.

Measures for positive partner values (x_j), shares (s_j=x_j/\sum_jx_j), and active count (n):

\[
G=\frac{2\sum_j jx_{(j)}}{n\sum_jx_j}-\frac{n+1}{n},\qquad
T=\sum_js_j\log(ns_j),\qquad
HHI=\sum_js_j^2.
\]

The preferred within-country models include entity and year fixed effects plus log population. Inference uses 9,999 entity-level Rademacher wild-cluster bootstrap draws. A supported U-shape requires negative and positive endpoint slopes, a joint U-test below 0.05, an in-support turning point, and adequate observations and entities on both sides.

Results:

- Zero of six preferred within-country tests is a supported U-shape.
- Export Gini and Theil have negative-to-positive endpoint signs, but their joint U-test raw p-values are 0.455 and their BH-adjusted q-values are 0.841.
- Import measures either continue declining or display inverted-U signs.
- Zero of 168 within-country sensitivity tests supports a U-shape. The smallest raw U-test p-value is 0.203.
- No country-level diversification/reconcentration episodes are classified because no preferred pooled turning point is supported.

This is not a test of Cadot's product mechanism. It is a strong boundary condition: there is no evidence that development produces a generic concentration U-shape across all dimensions of trade.

Primary outputs:

- `results/historical_partner_concentration/historical_partner_concentration_advisor_memo.md`
- `results/historical_partner_concentration/cadot_model_summary.csv`
- `results/historical_partner_concentration/figures/advisor/baseline_u_shape_tests.png`

## 4. Reproducibility and trust status

| Workstream | Status | Main remaining caveat |
| --- | --- | --- |
| Original 1988–2006 replication | Blocked | Country list, mirror construction, and exact 4,991-product universe missing |
| Modern 156 three-metric panel | Trustworthy for descriptive research use | Local rather than fresh-agent final review |
| Broad constant-PPP regressions | Mostly trustworthy for descriptive use | 135-country complete-case sample; not causal; no full cross-language audit |
| rd2 PPP regressions | Numerically independently re-estimated in Python | 55 countries; rich-tail support remains limited |
| Mechanism tribunal | First-pass descriptive mechanism diagnostic | Sample-internal PRODY and native HS4 transition windows |
| Non-energy visualization | Cleared by an independent fresh-agent review | Descriptive only; target labels can combine later-revision uses |
| World-product exposure | Mostly trustworthy | Final review local; 155 regression clusters |
| Historical partner panel | Mostly trustworthy | Only 13 entity clusters and local final review |

Focused historical-partner tests pass: 34 tests. The broad and tribunal reviews also report unique keys, validated joins, and numerical re-estimation checks. No result should be described as causal.

## 5. Econometric synthesis

### Estimand

The relevant estimand is the conditional descriptive curve relating product concentration to real GDP per capita, separately for:

- cross-country comparisons within a year;
- within-country changes over time; and
- differences in country means.

These are not interchangeable. Pooled and between-country curvature can arise from persistent differences in geography, scale, endowments, institutions, trade costs, commodity specialization, and reporting quality. Only country-FE or within-Mundlak terms describe within-country income variation, and even those are not causal because income remains endogenous and measured with error.

### What is robust

- In level-PPP specifications, richer-country cross sections exhibit a product-diversification curve across Gini, Theil, HHI, and active counts.
- The between-country component is cleaner than the within-country component.
- The pooled product pattern appears in both the 55-country balanced panel and the 135-country complete-case broad panel.
- The conclusion is not driven by one concentration index.
- Partner concentration does not reproduce the same level-PPP pattern.

### What is not robust

- The modern export turning point is not close to Cadot's $25,000 benchmark. It is generally around $73,000–$79,000 and often outside p05–p95 support.
- Country fixed effects remove the broad-sample export Gini and Theil humps.
- Log-income quadratics often remove or displace the export turning point.
- A positive quadratic is sometimes statistically significant even when the estimated turning point is outside support or the endpoint slopes do not form a U-shape.
- The old-cone extensive-margin mechanism is not the dominant modern episode classification.

### Why the between-country curve is stronger

The modern curve is not being generated by countries visibly moving through a common sequence over 2000–2024. Most measured variation is persistent across countries:

| Export outcome | Share of total variation attributable to between-country differences |
| --- | ---: |
| Product Gini | 73.2% |
| Product Theil | 94.1% |
| Product HHI | 81.1% |

This decomposition is descriptive, but it explains why country fixed effects are so consequential. The pooled regression mainly compares structurally different economies rather than tracing the same economy through a development transition.

The cross-country curve is also not a one-country outlier. In leave-one-country-out between regressions:

- the Gini quadratic remains positive and statistically distinguishable from zero in all 135 omissions; the implied turning point ranges from about $69,600 to $74,600;
- the Theil turning point ranges from about $65,000 to $74,400;
- the HHI turning point ranges from about $66,200 to $76,900.

Mechanical exclusions of sub-million-population countries and high-oil-share exporters do not remove the positive between-country curvature. They do move the turning point, sometimes substantially. This means the curve is a robust descriptive cross-sectional regularity, but its location is composition-sensitive.

The most plausible interpretation is a mixture of persistent country types:

1. Many low-income economies have narrow commodity or low-capability export baskets.
2. Middle-income industrializers span more manufacturing lines and therefore look more diversified.
3. The rich-country tail contains both broad industrial exporters and highly specialized economies: oil exporters, entrepôts, microstates, financial and tax hubs, and countries whose exports are dominated by a few globally successful products.

The countries with mean income above roughly $70,000 in the analytic sample are Switzerland, the United Arab Emirates, Ireland, Brunei, Bermuda, Singapore, Macao, Qatar, and Luxembourg. They are not a random set of countries observed later in a universal lifecycle.

The world-product exposure results reinforce this interpretation without fully explaining the quadratic. Larger economies place more weight on globally large products and have export rankings more closely aligned with the world product ranking, even after broad primary commodities are removed. The modern mechanism tribunal likewise finds continuing-product or superstar scaling in 59.7% of reconcentration episodes, compared with old-cone pruning in 20.6%. Scale, product demand, sectoral specialization, and persistent comparative advantage therefore look more important than a single income-triggered exit mechanism.

#### Production-core exclusion sensitivity

A deliberately severe production-oriented screen removes countries with mean population below one million, countries with mean oil/fuel export shares of at least 30%, and prominent finance, tax-conduit, offshore, and re-export hubs. This leaves 83 of the 135 complete-case countries.

The level-PPP between-country result remains for fixed-universe Theil, HHI, and active-product counts:

| Outcome | Turning point or peak | Endpoint IUT p | Result |
| --- | ---: | ---: | --- |
| Active-product Gini | $102,903, outside support | 0.955 | No U-shape |
| Fixed-universe Theil | $46,026 | 0.032 | Cross-country U-shape |
| HHI | $39,934 | 0.005 | Cross-country U-shape |
| Active-product count | $46,020 | 0.005 | Cross-country inverted U |

The Theil/count rich-side group contains 12 of 83 countries, or 14.5%, and consists mainly of large advanced producing economies: the United Kingdom, Italy, France, Australia, Finland, Canada, Belgium, Sweden, Germany, Austria, Denmark, and the United States. Dropping the United Kingdom and Belgium as an additional stress test leaves the result essentially unchanged.

However, none of the four outcomes passes the endpoint U-shape test when GDP per capita enters in logs, and none produces a supported country-FE U-shape at the 5% level. Removing hubs therefore does not eliminate the level-PPP cross-country pattern, but it does not rescue a robust within-country development law.

Primary diagnostics:

- `results/prof_p_replication/cadot_between_country_diagnostics/between_within_variance_decomposition.csv`
- `results/prof_p_replication/cadot_between_country_diagnostics/between_leave_one_country_out.csv`
- `results/prof_p_replication/cadot_between_country_diagnostics/between_composition_sensitivities.csv`
- `results/prof_p_replication/cadot_between_country_diagnostics/rich_tail_country_means.csv`
- `results/prof_p_replication/cadot_production_core_sensitivity.md`
- `results/prof_p_replication/cadot_production_core_sensitivity/production_core_model_summary.csv`

### Identification and inference risks

1. **Composition versus development:** the strongest result uses between-country variation.
2. **Rich-tail leverage:** few countries cross the estimated modern export turning-point region.
3. **Functional form:** level and log quadratics give materially different answers.
4. **Specification search:** multiple flows, metrics, income forms, samples, and mechanisms were examined. Only the historical-partner suite currently reports formal BH adjustment for the six primary U-tests.
5. **Original-design mismatch:** modern reporter exports, constant-2021 PPP, 5,037 harmonized products, and 2000–2024 are not the original mirror exports, constant-2005 PPP, 4,991 products, and 1988–2006.
6. **Mechanism measurement:** modern old-cone evidence uses a sample-internal PRODY proxy and cannot identify structural comparative-advantage adjustment.

### How the historical partner result changes the interpretation

Before the historical partner test, the modern evidence suggested that the Cadot curve was primarily a cross-country product pattern. The 1827–2014 result sharpens this interpretation in three ways:

1. It rejects a broad “development eventually reconcentrates trade” reading. A century-scale within-entity panel does not show the pattern across partners.
2. It increases the plausibility that the product hump is tied to product-space measurement, extensive product support, sectoral composition, or scale rather than a universal concentration mechanism.
3. It does not weaken the original product claim directly because the outcome is different. It is evidence about scope, not a failed replication.

The appropriate update is therefore not “Cadot is wrong.” It is “Cadot's result is narrower than its strongest development-law interpretation.”

### Is this an era artifact?

The answer differs by claim.

- **Modern product cross section:** not confined to Cadot's 1988–2006 era. A pooled and between-country product curve is visible in 2000–2024.
- **Turning point and mechanism:** clearly era-sensitive or construction-sensitive. The modern turning point is much higher than Cadot's benchmark, and continuing-product scaling is more common than product exit.
- **Partner concentration:** the null is not unique to the modern era. Modern partner Gini shows no level-PPP hump, and the 1827–2014 historical partner panel also shows no supported U-shape, including pre/post-1948 and war/source-regime sensitivities.
- **Historical product concentration:** unresolved. The implemented 1827–2014 bridge is a partner-concentration bridge using TRADHIST and post-1948 source-regime checks. It is not a harmonized historical product panel. We therefore cannot yet say whether the product hump existed in 1939–2014 or earlier under a Cadot-comparable product construction.

The evidence rejects a generic era-independent law of trade concentration. It does not yet distinguish whether the original product result changed because of the period, the country composition, mirror-versus-reporter reporting, or the product universe.

## 6. Economist Council — Advisor Mode

### Council setup

- Question: What do the combined replication, extension, mechanism, and partner results imply for the interpretation of Cadot and for the next message to Professor Panagariya?
- Assumption: the target claim is descriptive external validity, not causal identification.
- Seats: Identification Hawk, Econometrician, Trade and Spatial Economist, Economic Historian, Theory/Mechanism Voice, Policy/External-Validity Voice, and Writing/Positioning Editor.

### Round 1: opening diagnoses

**Identification Hawk.** The pooled coefficient does not answer whether countries reconcentrate as they develop. The cleanest modern export finding is between countries, while country fixed effects remove Gini and Theil curvature. The claim must be “development-stage cross section,” not “countries follow a common path.”

**Econometrician.** Turning-point support is the central weakness. Significant quadratic terms near or beyond p95 are not sufficient evidence of a U-shape, and level-versus-log sensitivity shows that the imposed polynomial matters. The historical partner pipeline's formal endpoint-slope, support, and bootstrap rules should be ported to the product regressions before publication claims.

**Trade and Spatial Economist.** Products and partners are different margins. The partner null does not contradict product diversification, but it shows the mechanism does not generalize to market geography. Scale, trade costs, comparative advantage, and global-product demand can produce a cross-country product curve without a universal within-country sequence.

**Economic Historian.** The modern period is not a clean falsification of 1988–2006. Trade integration, China, global value chains, HS revisions, and the composition of high-income countries changed. Without a matched period-by-construction bridge, we cannot distinguish period change from measurement change.

**Theory/Mechanism Voice.** The old-cone interaction is real evidence consistent with comparative-advantage pruning, but the episode mass is mostly continuing-product scaling. The strongest version of Cadot's extensive-margin mechanism is therefore not reproduced in modern data. A model should allow both line exit and superstar scaling.

**Policy/External-Validity Voice.** The results do not justify a policy target of maximizing product counts or treating reconcentration as a universal mature-development stage. Concentration can reflect commodities, sector design, successful large products, or pruning; welfare requires distinguishing these channels.

**Writing/Positioning Editor.** The contribution is not a binary replication verdict. The useful result is a decomposition of where the hump survives: product rather than partner, between rather than within, levels more than logs, and pooled shape more than extensive-margin mechanism.

### Round 2: cross-examination

**Identification Hawk → Economic Historian.** Period differences cannot be the default explanation until a common-country, common-product, common-reporting bridge shows coefficient instability directly.

**Economic Historian → Econometrician.** A modern fixed-effect null can be underpowered because only a few countries cross the rich tail; support and power diagnostics must precede a substantive “no within effect” conclusion.

**Econometrician → Writing Editor.** “Reproduces the hump” is too generous unless the statement includes the support failure and functional-form sensitivity in the same sentence.

**Trade Economist → Theory Voice.** The old-cone exit coefficient does not establish that old-cone exit explains aggregate reconcentration; the 20.6% episode share and proxy construction limit that interpretation.

**Theory Voice → Identification Hawk.** Country fixed effects are not automatically the only economically relevant object. Cadot's development-stage curve may intentionally describe equilibrium differences across countries. The writing should distinguish the between-country fact from a within-country law rather than discard the former.

**Policy Voice → Trade Economist.** A product-concentration increase can be benign if it reflects successful globally demanded products. Policy conclusions require volatility, productivity, and welfare outcomes, none of which are identified here.

### What would change minds

- A four-cell bridge crossing original versus modern periods with Cadot-like versus modern construction.
- A common-country, common-product stacked model with period-by-income and period-by-income-squared interactions.
- Formal Lind–Mehlum U-tests, turning-point bootstrap intervals, and rich-country leave-one-out diagnostics for fixed-universe export Theil.
- A power simulation using observed modern income paths to determine whether a Cadot-sized within effect could be detected.
- A harmonized entry/exit/continuing-product decomposition showing whether the extensive margin dominates after a supported turning point.
- Reporter-export versus mirror-export estimates holding period and country support fixed.

### Council verdict

- **Strongest defensible claim:** Cadot's product-diversification curve survives as a modern pooled and between-country descriptive pattern, especially in level PPP.
- **Main threat:** the export turning point is rich-tail and functional-form sensitive, and the within-country evidence is weak.
- **Best next test:** formal supported-U tests and rich-country influence/power diagnostics for fixed-universe export Theil, followed by the period-by-construction bridge if the goal is to evaluate the original paper.
- **What to de-emphasize:** any claim that the modern results confirm a universal within-country law or that old-cone product exit is the dominant modern mechanism.
- **What to stop doing:** adding more concentration indices without changing identification; Gini, Theil, and HHI already show that index choice is not the core problem.

## 7. Final take for Professor Panagariya

The evidence should be presented as a refinement, not a reversal, of Cadot:

> We can reproduce a modern pooled product-concentration hump, but it is mainly a between-country pattern. The export relationship weakens sharply with country fixed effects, is sensitive to the income functional form, and turns at much higher incomes than Cadot's benchmark—often at the edge of observed support. The mechanism evidence is also different: continuing-product scaling is more common than product-line exit. Finally, neither modern nor 1827–2014 partner concentration exhibits the same hump, so the result is specific to the product margin rather than a general law of trade concentration. Because the literal 1988–2006 mirror-data replication remains blocked, these findings narrow Cadot's external validity but do not establish that the original result was spurious.

### Short message ready to send

Dear Professor Panagariya,

We have now consolidated the Cadot replication and extension work. The main conclusion is more nuanced than either “Cadot replicates” or “Cadot fails.” In modern 2000–2024 data, pooled level-PPP regressions show the expected export curvature in Gini, Theil, HHI, and active product counts; the clearest in-support results are the between-country Gini, Theil, and active-count curves. However, the export turning point is around $73,000–$79,000 in constant-2021 PPP dollars—well above Cadot's roughly $25,000 benchmark and often at the edge of the observed income distribution.

The within-country evidence is much weaker. In the broad 156-reporter sample, country fixed effects eliminate the export Gini and Theil humps; the results also change materially when income enters in logs. The mechanism evidence is similarly narrower than Cadot's strongest interpretation: old-cone-consistent product exit is detectable, but continuing-product or superstar scaling is the most common feature of modern reconcentration episodes.

The new long-run partner analysis sharpens the scope condition. Across 13 historical reporter entities from 1827–2014, none of six preferred tests and none of 168 sensitivity tests supports diversification followed by partner reconcentration. This does not contradict Cadot's product result, but it shows that the hump is not a general law of trade concentration.

My current interpretation is that Cadot captures a real cross-country product-composition pattern, but our evidence does not support a universal within-country development path or a predominantly extensive-margin mechanism in the modern period. We also have not yet completed a literal 1988–2006 replication because the exact country list, mirror-export construction, and original 4,991-product universe remain unavailable. The decisive next step, if we want to evaluate the original claim directly, is a matched historical-versus-modern bridge holding countries and product construction constant.

Would you prefer that we pursue that bridge, or present the current result as a modern external-validity and mechanism reassessment?

Best,

[Your Name]

## 8. Evidence ledger

Primary machine-readable evidence inspected:

- `results/cadot_replication_audit/cadot_replication_rebuild_manifest.json`
- `results/samples/cadot_original_1988_2006/cadot_original_status.json`
- `results/samples/cadot_broad_156/three_metric_tables/cadot_three_metric_manifest.json`
- `results/samples/cadot_broad_156/three_metric_tables/validation_checks.csv`
- `results/samples/cadot_broad_156/three_metric_tables/three_metric_rank_spearman_correlations.csv`
- `results/samples/cadot_broad_156/cadot_broad_ppp_hump_regression_tables/ppp_hump_regression_summary.csv`
- `results/samples/cadot_broad_156/cadot_broad_ppp_hump_regression_tables/ppp_hump_regression_models.csv`
- `results/samples/rd2_countries/ppp_hump_regression_tables/ppp_hump_country_fe_robustness.csv`
- `results/samples/rd2_countries/cadot_hump_tribunal_tables/mechanism_scorecard_summary.csv`
- `results/samples/rd2_countries/cadot_hump_tribunal_tables/old_cone_exit_models.csv`
- `results/samples/cadot_broad_156/world_large_product_exposure_tables/world_large_product_exposure_models.csv`
- `results/historical_partner_concentration/cadot_model_summary.csv`
- `results/historical_partner_concentration/run_manifest.json`
- `results/prof_p_replication/cadot_between_country_diagnostics/between_within_variance_decomposition.csv`
- `results/prof_p_replication/cadot_between_country_diagnostics/between_leave_one_country_out.csv`
- `results/prof_p_replication/cadot_between_country_diagnostics/between_composition_sensitivities.csv`
- `results/prof_p_replication/cadot_between_country_diagnostics/rich_tail_country_means.csv`

Trust reviews inspected:

- `results/cadot_replication_audit/cadot_replication_audit_adversarial_review.md`
- `results/samples/cadot_broad_156/cadot_broad_ppp_hump_regression_tables/adversarial_review.md`
- `results/samples/cadot_broad_156/three_metric_tables/adversarial_review.md`
- `results/samples/cadot_broad_156/three_metric_tables/nonenergy_visualization_adversarial_review.md`
- `results/samples/rd2_countries/cadot_hump_tribunal_adversarial_review.md`
- `results/samples/cadot_broad_156/world_large_product_exposure_tables/adversarial_review.md`
- `results/historical_partner_concentration/adversarial_review.md`

Remaining unresolved evidence:

- exact original country list;
- original mirror-export reconstruction;
- exact original 4,991-line product universe;
- matched historical-versus-modern bridge;
- formal U-test and bootstrap support analysis for the modern product regressions;
- independent fresh-agent review of the final integrated interpretation.
