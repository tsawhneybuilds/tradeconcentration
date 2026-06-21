# Referee 2 / Adversarial Econometrics Review: Cadot Broad 156 Rebuild

Date: 2026-06-02

Scope: `cadot_broad_156` sample rebuild, Exercise 1/2 rebuild, and cadot broad PPP hump regressions.

Independence note: this is a local adversarial pass by the same Codex session that ran the rebuild, not a fresh independent reviewer-agent pass. The graph lookups for panel fixed effects and clustering returned no matches, so this review used the installed checklist directly.

## Executive Verdict

Verdict: Mostly trustworthy for current purpose, with caveats before substantive interpretation.

- The selected sample has 156 unique reporters and 156 unique ISO3 codes; selected reporters have at least 19 available HS years in 2000-2024.
- Exercise 1 and Exercise 2 outputs have no duplicate country-year-flow keys, and the broad PPP regression panel has no duplicate reporter-year keys.
- The regression runner now reports attrition from 156 selected reporters to 135 complete-case reporter clusters.
- A `statsmodels` replication check for the export-product level-PPP model matched the pipeline coefficient and clustered standard error to numerical precision.
- The main caveat is substantive: complete-case controls drop 21 reporters from the selected sample, mostly through World Bank population/PPP availability. Treat results as cadot broad complete-case regressions, not as all-156-country regressions.
- Full Referee 2 cross-language replication in R/Stata was not performed in this pass.

## Highest-Risk Findings

1. Severity: Medium. Control-data attrition changes the analytic country set.
   Evidence: selected reporters = 156; final complete-case PPP panels use 135 countries/clusters. Missing controls include 70-83 PPP rows and 507-519 population rows depending on outcome/flow.
   Why it matters: the estimated PPP-concentration curve is identified on a control-complete subset, not the full Cadot 156 sample.
   Fix or diagnostic: report the attrition table with selected reporters, analytic rows, countries, and clusters; add sensitivity without population controls or with alternative population sources if the substantive claim depends on full coverage.

2. Severity: Medium. The broad PPP runner estimates descriptive year-FE curves, not causal country-growth effects.
   Evidence: model terms are PPP level/log and square, log population, oil export share, year FE, reporter-clustered SEs. There are no country fixed effects.
   Why it matters: time-invariant country heterogeneity can load onto the income curve. This is acceptable for a Cadot-style descriptive hump, but not for causal language.
   Fix or diagnostic: label tables as "Cadot broad 156-country modern replication sample, 2000-2024" and describe estimates as descriptive associations.

3. Severity: Low. Full independent Referee 2 protocol remains incomplete.
   Evidence: no R/Stata cross-language scripts were produced in this pass. A Python/statsmodels package-level check was performed for one representative model.
   Why it matters: the pipeline is mechanically checked, but not fully independently replicated across languages.
   Fix or diagnostic: before treating results as final-paper evidence, run a fresh-agent Referee 2 audit with R/Stata/Python replication scripts.

## Data Lineage and Sample Audit

- Sample artifacts: `data/processed/samples/cadot_broad_156/`.
- Results: `results/samples/cadot_broad_156/`.
- Country panel: 156 reporters, 156 ISO3 codes, no duplicate reporter codes, no duplicate ISO3 codes.
- Coverage summary: 156 rows; `available_hs_years` min = 19, max = 25.
- Exercise 1 concentration panel: 7,554 rows; 156 countries; flows = Exports and Imports; years = 2000-2024; duplicate reporter-year-flow-variant keys = 0.
- Exercise 2 export panel: 3,753 rows; duplicate reporter-year-flow keys = 0; missing oil share = 0.
- Exercise 2 growth panel: 8,686 rows; duplicate reporter-year-horizon keys = 0.
- PPP analysis panel: 3,240 reporter-year rows; 135 countries; years = 2000-2024; duplicate reporter-year keys = 0; cluster-size range = 13-25 rows.

## Merge and Join Audit

- Standard concentration panel enforces unique reporter-year-flow-variant keys.
- Oil-share controls enforce unique reporter-year keys.
- Population and PPP controls enforce unique ISO3-year and reporter-year keys.
- Regression controls merge with `validate="many_to_one"` on ISO3-year and reporter-year paths.
- Attrition table now reports selected reporters, selected ISO3 count, source rows/countries, analytic rows/countries, and clusters.

## Variable Construction Audit

- Product-dependent concentration uses `drop_excluded_hs6` before product/cell aggregation; HS6 `999999` is excluded from product-dependent outcomes.
- Partner concentration inherits the project convention: product identity is summed away, so `999999` can remain in partner totals; `partnerCode == 0` remains excluded by the concentration pipeline.
- Oil-share control is built from HS2 `27` exports after product-level `999999` exclusion.
- PPP GDP per capita is World Bank `NY.GDP.PCAP.PP.KD`, transformed into level per 10,000 and log forms, with squared terms.
- Population is World Bank `SP.POP.TOTL`, transformed to log population.

## Specification Audit

Estimated broad PPP model by outcome:

`concentration_{c,t} = beta1 income_{c,t} + beta2 income_{c,t}^2 + gamma log(population_{c,t}) + delta oil_share_{c,t} + year FE + error_{c,t}`

- Outcomes included: export product Gini, import product Gini, export partner Gini, import partner Gini.
- World-relative product Gini is not included because the cadot broad world-relative runner/output is absent.
- Standard errors: reporter-code clustered; 135 clusters in all reported models.
- Panel policy: unbalanced complete case, not forced 25-year balance.

## Inference and Identification Audit

- Cluster count is adequate at 135 reporter clusters.
- The helper uses a finite-sample-corrected cluster-robust covariance and Student-t p-values with cluster-minus-one degrees of freedom.
- A `statsmodels` replication of the export-product level-PPP model matched the pipeline:
  - linear coefficient difference: `2.57e-16`; standard-error difference: `2.69e-16`.
  - quadratic coefficient difference: `3.00e-17`; standard-error difference: `6.68e-17`.
- Identification caveat: this is a descriptive pooled panel with year fixed effects. Do not interpret as causal.

## Replication Checklist

- Passed: focused tests `tests/test_cadot_broad_sample.py`, `tests/test_cadot_hump_tribunal.py`, `tests/test_world_relative_product_gini.py` (`21 passed`).
- Passed: source compile for `trade_concentration_pipeline.py`, `run_ppp_hump_regressions.py`, and `run_cadot_broad_ppp_hump_regressions.py`.
- Passed: Exercise 2 and broad PPP outputs are under `cadot_broad_156`; no matching Exercise 2 or cadot PPP outputs are under `world_broad`.
- Remaining: independent fresh-agent Referee 2 cross-language replication.

## Minimal Patch Plan

No blocking code patches remain from this local review. Recommended next patch if these tables become paper-facing: add a no-population-control PPP sensitivity to quantify the effect of World Bank population attrition.

## Questions for the Researcher

1. Should the headline broad PPP table be explicitly labeled as the 135-cluster complete-case analytic sample, while the sample design remains the 156-reporter Cadot broad universe?
2. Do you want a robustness table that keeps PPP and oil controls but omits population to recover more of the 156-country sample?
