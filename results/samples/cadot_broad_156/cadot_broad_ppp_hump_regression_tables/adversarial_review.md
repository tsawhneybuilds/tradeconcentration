# Adversarial Econometrics Review: Cadot Broad PPP Hump Outputs

Generated: 2026-06-16T09:54:50+00:00

Review independence: **not independent**. This was a local adversarial pass after generating the outputs; no fresh reviewer agent was explicitly requested.

## 1. Executive verdict

**Mostly trustworthy for current modern-extension purpose, not a literal Cadot replication.**

- The current broad PPP tables are generated from saved `cadot_broad_156` artifacts and use constant PPP GDP per capita (`NY.GDP.PCAP.PP.KD`).
- The analytic panel has 3240 rows, 135 countries/clusters, years 2000-2024, and no duplicate reporter-year keys in the saved panel.
- Independent saved-panel re-estimation passed for one pooled/year-FE model and one country+year-FE model; `8/8` term checks matched coefficients and SEs within tolerance.
- The main broad result is a modern descriptive association: clear pooled level-PPP humps for Import Product Gini, Import Product Theil; edge/support-sensitive bends for Export Product Gini, Export Product Theil, Export Product HHI, Export Active HS6 Product Count, Import Active HS6 Product Count.
- This is not Cadot's original 1988-2006 mirror-data, HS0 4,991-line, constant-2005-PPP design.

## 2. Highest-risk findings

Severity: High. Original-period design drift remains.
What happened: the broad run uses 2000-2024 current Comtrade final-data reporters and current WDI constant-2021 PPP.
Why it matters: it cannot establish that Cadot's 1988-2006 paper result is replicated.
How to verify: build `cadot_original_1988_2006` and compare country/product universe counts to Cadot.
Fix: recover or reconstruct Cadot's exact country list, mirror-data construction, and HS0 4,991-line universe.

Severity: Medium. Complete-case attrition drops selected reporters from regression samples.
What happened: selected reporters = 156; analytic clusters = 135.
Why it matters: coefficients describe the complete-control subset, not every selected broad reporter.
How to verify: inspect `ppp_hump_sample_attrition.csv`.
Fix: report attrition in every table note and add no-population-control sensitivity if sample recovery is important.

Severity: Medium. Export product humps are support-edge results.
What happened: pooled level-PPP export product Gini/Theil/HHI turning points are inside min/max but outside p05-p95.
Why it matters: rich-tail leverage may drive the apparent export reconcentration.
How to verify: inspect `turning_point_inside_p05_p95` and run high-income leave-one-cluster-out sensitivity.
Fix: label export product evidence as edge-sensitive; do not call it a clean Cadot confirmation.

## 3. Data lineage and sample audit

Raw-to-final path: Comtrade final-data raw/checkpoint files -> `three_metric_tables/concentration_metric_all_years.parquet` -> broad PPP runner -> saved regression panel and tables.

Saved panel: 3240 rows; 135 reporter clusters; period 2000-2024; PPP support $796-$174,570; p05=$2,245; p95=$74,159.

Attrition rows are saved in `ppp_hump_sample_attrition.csv`; source rows range from 3753 to 3756; analytic rows after balance range from 3236 to 3240.

## 4. Merge/join audit

Joins are reporter-year outcomes to HS27 oil-share controls, population, and PPP controls. The runner validates reporter-year uniqueness for outcome panels and controls. PPP cache has 3847 complete rows out of 3900 expected selected country-years and 0 duplicate ISO3-year keys.

## 5. Variable construction audit

Product concentration outcomes exclude HS6 `999999` before aggregation. Theil uses the broad run's fixed product universes. Oil share is derived from HS27 export share through the `oil_only` exclusion diagnostic. Income is constant PPP GDP per capita in current WDI constant-2021 international dollars, not Cadot's constant-2005 vintage.

## 6. Specification audit

Estimated variants:

- pooled/year-FE: `Y_ct = beta1 income_ct + beta2 income_ct^2 + log_population_ct + oil_share_ct + year_FE_t + e_ct`, clustered by reporter.
- country+year-FE: same controls plus reporter fixed effects, clustered by reporter.
- between-country: country means, no year FE, HC1 inference.

Level PPP is the headline Cadot-comparable functional form; log PPP is sensitivity.

## 7. Inference and identification audit

The results are descriptive. They should not be interpreted as causal income effects. Country+year-FE estimates are weaker for several export outcomes, which means the pooled development-stage pattern is not the same as a within-country reconcentration law.

## 8. Replication checklist

- Passed: current broad selected reporters = 156.
- Passed: saved broad PPP panel has no duplicate reporter-year keys.
- Passed: independent re-estimation checks in `ppp_hump_independent_reestimate_checks.csv`.
- Still required for literal Cadot: original country list, mirror data, HS0 4,991-product universe, constant-2005 PPP bridge or archived WDI vintage.

## 9. Minimal patch plan

- Add leave-one-high-income-country-out sensitivity for broad export product outcomes.
- Add original-period mirror-data reconstruction only after country-list provenance is explicit.
- Keep broad output labels as modern 2000-2024 extension.

## 10. Questions for the researcher

- Is the paper claim intended to be “modern extension supports Cadot-style import-product humps,” or “we replicate Cadot 1988-2006”? The current evidence only supports the first.
