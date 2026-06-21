# Adversarial review: Cadot 156 non-commodity world-product exposure

Review date: 2026-06-19

Reviewer status: local builder-side adversarial review. A fresh independent reviewer agent was attempted but failed due a usage-limit error, so this is not an independent fresh-agent pass.

## 1. Executive verdict

Verdict: Mostly trustworthy

- The final Cadot 156 panel now reflects real baseline-versus-noncommodity differences; the earlier zero-difference artifact was traced to a code-extraction bug and fixed.
- Product-dependent outputs correctly exclude HS6 `999999`, use harmonized HS1992/H0 labels, and pass the published validation checks.
- The World Bank control loader had two real failure modes for the Cadot sample; both were fixed before trusting the output.
- Final control coverage is high enough for the descriptive GDP regressions to be interpretable: 99.33% of panel rows have complete GDP and population controls.
- The main remaining caveat is sample loss in regressions from missing controls for Montserrat (`MSR`) across the window and Lebanon GDP in 2024, which leaves 155 regression clusters instead of 156.
- Because the final review was local rather than independent, I would treat the output as staging-ready rather than as a substitute for a later fresh-agent audit.

## 2. Highest-risk findings

### Finding 1 — High severity, confirmed, fixed

What happened:

- `product_id_to_cmd_code()` extracted the first digits from strings like `HS1992:010511`, yielding `1992` instead of the trailing HS6 code `010511`.

Why it mattered:

- That collapsed the harmonized product mapping onto a fake code and made the broad-primary exclusion inert.
- Baseline and noncommodity results became mechanically identical, with zero removed shares.

How it was verified:

- The first run produced zero removed shares everywhere and identical baseline/noncommodity correlations.
- Inspecting `world_large_product_exposure_product_mapping.csv` showed `cmd_code` values built from `1992`.

Fix applied:

- Changed the extractor to strip non-digits and keep the trailing six digits.
- Added a regression test for `HS1992:`-prefixed product IDs.

Current status:

- Resolved.
- The final mapping now contains 961 `primary_broad == True` products and nonzero removal shares across reporter-years.

### Finding 2 — High severity, confirmed, fixed

What happened:

- The shared World Bank control loader sent the Cadot ISO3 list as large semicolon-joined requests.
- Some large batches under-returned or returned zero rows, especially for population, which silently wiped out valid countries in the same batch.

Why it mattered:

- The first control merge had only 39.5% complete country-years.
- A later partial fix raised coverage only to 92.9% but still left entire population series missing for valid countries such as `MYS`, `MWI`, `MUS`, `NAM`, `PHL`, `PAK`, `NGA`, `OMN`, and `NIC`.

How it was verified:

- Direct single-country API calls returned complete data for those countries.
- The mixed-country batch containing `MSR` returned zero rows for the whole group.

Fix applied:

- Batched requests in groups of 20.
- Added fallback country-by-country requests for ISO3 codes missing from a batch response.

Current status:

- Resolved for practical purposes.
- Final control coverage is 0.9933 of panel rows.
- Remaining missing controls are concentrated in `MSR` and Lebanon GDP in 2024.

### Finding 3 — Medium severity, confirmed, fixed

What happened:

- `build_top_contributor_rows()` assumed both variant detail frames had the full schema.
- When one side was empty, the contributor build crashed on missing columns.

Why it mattered:

- Reporter-years with no surviving noncommodity detail could crash the whole pipeline.

Fix applied:

- Reindexed both detail frames onto the required schema before merging.
- Added a regression test covering the empty-variant case.

Current status:

- Resolved.

### Finding 4 — Medium severity, confirmed, fixed

What happened:

- The new exposure page initially displayed overly broad model/fixed-summary tables without filtering to the intended GDP headline rows.
- The scatter plot title hard-coded a positive interpretation before observing the sign.

Why it mattered:

- Website readers could see ambiguous or overstated claims.

Fix applied:

- Filtered the page tables to the intended GDP headline rows for exposure and alignment.
- Neutralized the scatter title.

Current status:

- Resolved.

## 3. Data lineage and sample audit

Raw-to-final path:

1. Cadot sample raw Comtrade annual files were processed into export product aggregates with LT/HGL-weighted HS1992/H0 harmonization.
2. Product-dependent processing excluded source HS6 `999999` before aggregation.
3. Inclusive world export totals came from `world_broad`.
4. A harmonized product mapping attached official H0 labels and broad-primary flags.
5. Reporter-year baseline and noncommodity exposure metrics were built.
6. GDP and population controls were merged from the World Bank cache.
7. Yearly correlations, pooled year-FE models, fixed-country robustness, leave-one-country-out diagnostics, removed-share diagnostics, and contributor tables were written to the Cadot results directory.

Observed sample facts from final artifacts:

- Unique reporters in final panel: 156.
- Year window: 2000–2024.
- Reporter-year-variant duplicates: 0.
- Baseline/noncommodity yearly country counts range from 132 to 156 depending on year.
- Final panel control completeness: 99.33% of rows.
- Remaining missing control keys: 25 unique `iso3`-year combinations.
- Remaining missing keys are one Lebanon GDP observation in 2024 plus mostly Montserrat rows with no World Bank controls.

Unit of observation:

- `reporter_code` × `year` × `variant`.

## 4. Merge/join audit

Product mapping joins:

- Country product inputs and world product inputs are merged onto a harmonized `product_id` mapping with `many_to_one` validation.
- This is appropriate because the mapping is one product row per harmonized `product_id`.

Country-world exposure join:

- Country product baskets are merged to same-year world product baskets with `many_to_one` validation.
- Final validation reports zero unmatched country export share against the world basket.

World Bank controls join:

- Controls are merged `many_to_one` on `iso3` and `year`.
- The original loader had under-return problems; those were fixed.
- Final merge still leaves explicit missing values for `MSR` and Lebanon GDP in 2024, which are now disclosed rather than silently blocking output.

## 5. Variable construction audit

Headline constructed measures:

- Baseline exposure:
  - \(E_{ct} = \sum_p s_{cpt} R_{pt}\)
- Noncommodity exposure:
  - \(E^{NC}_{ct} = \sum_{p \in NC} s^{NC}_{cpt} R^{NC}_{pt}\)
- Noncommodity alignment:
  - \(A^{NC}_{ct} = \rho_p(s^{NC}_{cpt}, w^{NC}_{pt})\)

Interpretation:

- Higher exposure means a country exports relatively more in products that are large in world trade.
- Higher alignment means the country’s within-basket ranking of exports lines up more closely with the global ranking of products.

Construction checks:

- `999999` exclusion is upstream and validated.
- Broad-primary exclusion is applied to both country and world baskets in the noncommodity variant.
- Noncommodity shares are renormalized because exposure is recomputed from the filtered basket, not mechanically differenced.
- World ranks are rebuilt inside the filtered world basket.
- Constant-vector Spearman cases return `NaN` rather than a fabricated correlation.

## 6. Specification audit

Yearly descriptive correlations:

- Annual cross-country Spearman correlation between `log_gdp_current_usd` and each outcome.
- Separate yearly series for baseline and noncommodity variants.

Main pooled regressions:

- Outcome:
  - `world_share_exposure` or `spearman_product_alignment`
- Regressor:
  - `log_gdp_current_usd`
- Fixed effects:
  - year FE
- Clustering:
  - reporter-code cluster

Robustness regressions:

- Conditional GDP + GDP per capita + year FE.
- Population + year FE.

Final main-regression sample size:

- Baseline exposure: 3,728 observations, 155 clusters.
- Baseline alignment: 3,728 observations, 155 clusters.
- Noncommodity exposure: 3,721 observations, 155 clusters.
- Noncommodity alignment: 3,717 observations, 155 clusters.

The loss from 156 to 155 clusters is driven by missing controls for `MSR`.

## 7. Inference and identification audit

- These are descriptive associations, not causal estimates.
- Year FE plus clustered standard errors are appropriate for the stated descriptive panel purpose.
- The output clearly separates yearly rank correlations from pooled FE regressions.
- The main identification risk was not econometric form but data construction and control availability; those were the parts that required correction.

Remaining inference caveats:

- Regressions exclude rows without complete GDP and population controls.
- The panel correlation figures therefore represent “available-control” coverage, not a perfectly balanced 156-country panel.

## 8. Replication checklist

Commands used in audit path:

- `python3 -m pytest tests/test_world_large_product_exposure.py -q`
- `python3 -m pytest tests/test_cadot_extension_site.py -q`
- `python3 scripts/run_world_large_product_exposure.py --country-sample cadot_broad_156`

Additional checks completed:

- Verified the final product mapping contains broad-primary products.
- Verified baseline versus noncommodity results differ materially in the final panel.
- Verified validation checks all pass.
- Verified final control completeness is 99.33%.
- Verified final reporter coverage is 156 unique reporters over 2000–2024.

Before treating the result as production-ready, I would still want:

- a fresh independent reviewer-agent pass when usage limits allow, and
- a final browser verification of the published staging page and downloads.

## 9. Minimal patch plan

Completed patches:

1. Fix HS1992 product-code extraction to use trailing six digits.
2. Add regression tests for `HS1992:` code extraction and empty contributor-detail handling.
3. Harden World Bank control fetching with chunking and per-country fallback for missing batch returns.
4. Relax the final exposure script gate from 100% control completeness to explicit completeness reporting with validation.
5. Filter website headline tables to the intended GDP rows and neutralize the scatter title.

No further code patch is required to generate the current staging artifacts.

## 10. Questions for the researcher

1. Do you want `MSR` retained in the website-facing coverage tables even though it drops out of all control-based regressions?
2. Do you want the exposure page to explicitly note that the FE regressions use 155 clusters because `MSR` lacks World Bank controls and Lebanon is missing GDP in 2024?
3. Once usage resets, do you want a fresh independent reviewer-agent pass recorded as a second adversarial-review artifact, or is this local adversarial review sufficient for staging?
