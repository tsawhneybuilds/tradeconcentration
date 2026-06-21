# LT/HGL HS1992 Harmonization Adversarial Review

Review date: 2026-06-03

Review mode: read-only adversarial pass. I did not assume the builder's claims were correct. I inspected source code, generated manifests, generated CSV/parquet artifacts, the current staging website, and compact diagnostics. Write ownership for this review was limited to this file.

Econometrics reference context used: `/Users/tanushsawhney/.codex/reference-library/econometrics/query_graph.py --type diagnostic`. The graph emphasized replication-package provenance, robust/clustered inference for panel fixed-effects work, and diagnostics for sample construction, attrition, and clustered dependence.

## 1. Executive Verdict

Verdict: Trust only after fixes.

- The core LT/HGL conversion table itself is internally coherent: 50,523 source-target weight rows, 36,658 source revision-code pairs, 5,041 HS1992 targets, no `999999` source or target rows, no duplicate source-target keys, and source weights sum to one within `2.22e-16`.
- Exercise 12 extensive-margin and EV-style HS6 outputs pass their own validation gates: 60 rd2 countries, zero filtered `999999`, zero `partner_code == 0`, zero LT/HGL missing rows/value, and zero accounting residual violations.
- World-relative export/import product Gini panels pass the main panel gates: 55 balanced countries, 1,375 country-year rows, 2000-2024, zero duplicate country-year keys, zero `999999` product IDs in product parquets, and zero LT/HGL missing-weight value.
- Publication should stop until the staging site is rebuilt. `/Users/tanushsawhney/Desktop/trade-gini-map` is stale and still tells users the HS6 headline uses WCO-family harmonization rather than full LT/HGL weights.
- Trade-deal market-access diagnostics remain blocked. The HS4 LT/HGL bridge coverage itself passed, but WITS availability was not fetched or had no nomenclature codes, leaving primary WITS tariff samples at zero rows.
- There are latent code-path risks: one DuckDB rebuild path drops `999999` for partner concentration, and one helper can still fall back to the old WCO family lookup if called directly.

## 2. Highest-Risk Findings

### Finding 1: Current staging website contradicts the LT/HGL rerun

Severity: high, stop-publication.

What happened: The staged site at `/Users/tanushsawhney/Desktop/trade-gini-map` was not rebuilt from the updated source after the LT/HGL rerun. It still contains the old WCO caveat and old product labels:

- `/Users/tanushsawhney/Desktop/trade-gini-map/exercise-12.html:89` says the run uses "current WCO-family harmonization, not the full LT/HGL optimized weighted conversion."
- `/Users/tanushsawhney/Desktop/trade-gini-map/methods.html:67` says product identity is a WCO connected component.
- `/Users/tanushsawhney/Desktop/trade-gini-map/world-gini.html:44` says the unit is "harmonized HS6 product families" rather than LT/HGL HS1992 products.
- `/Users/tanushsawhney/Desktop/trade-gini-map/assets/site-manifest.json:476-479` labels the Exercise 12 method as "EV-style harmonized-HS6" and `product_level_label` as "harmonized HS6 families."

Why it matters: This directly reverses the intended methods statement and would mislead users about the product identity used in the headline results.

How to verify: `stat` shows the staged pages were modified at Jun 2 20:09:35 2026, while key rerun artifacts are newer, for example `results/samples/rd2_countries/world_relative_product_gini_tables/run_manifest_world_relative_product_gini.json` at Jun 3 01:48:13 2026.

Exact fix: Rebuild with `scripts/build_trade_gini_site.py --country-sample rd2_countries`, then verify no staged HTML or `assets/site-manifest.json` contains stale phrases such as `WCO-family`, `not the full LT/HGL`, `connected component`, or unqualified `harmonized HS6 families`.

### Finding 2: Trade-deal diagnostics are blocked by WITS availability, not by LT/HGL HS4 coverage

Severity: high for trade-deal/tariff outputs; not a blocker for the core LT/HGL product outputs.

What happened: `results/samples/rd2_countries/trade_deal_market_access/source_manifest.json` reports blockers `["hs4_harmonization_coverage_gate_failed", "wits_availability_not_complete"]`. Direct inspection shows the HS4 coverage gate passed: `data/processed/samples/rd2_countries/trade_deal_hs4_baseline_harmonization_coverage.csv` has 60 reporters, min/mean/max `hs4_bridge_trade_value_coverage == 1.0`, and zero uncovered rows. The manifest's `referee_calibrated_samples.hs4_harmonization.status` is also `passed`.

Why it matters: The blocker label is misleading. The actual failure is WITS availability: `source_manifest.json` reports `wits_availability.rows == 0`, no nomenclature codes, and primary WITS HS4 samples have zero rows. Downstream tariff regressions should not be run or published from these artifacts.

Code evidence:

- `/Users/tanushsawhney/Desktop/profps26/scripts/build_trade_deal_market_access_diagnostics.py:1562-1568` blocks when WITS revisions are empty.
- `/Users/tanushsawhney/Desktop/profps26/scripts/build_trade_deal_market_access_diagnostics.py:1219-1227` marks HS4 baseline coverage passed/blocked based on coverage, short baselines, and missing reporters.
- `/Users/tanushsawhney/Desktop/profps26/scripts/build_trade_deal_market_access_diagnostics.py:2530-2550` converts any blocked concordance gate into the `hs4_harmonization_coverage_gate_failed` blocker, even when the concordance gate is blocked for WITS availability.

How to verify: Inspect `source_manifest.json` fields `hs_concordance_gate.reason`, `wits_availability`, and `referee_calibrated_samples.attrition`. The attrition table drops 1,911 nonmissing-product-Gini rows at "keep WITS-available tariff reporter-years."

Exact fix: Split the blocker labels. Use an `hs4_harmonization_coverage_gate_failed` blocker only when `hs4_coverage_summary.status != "passed"` or coverage is below the threshold. Use a separate `wits_nomenclature_availability_missing` blocker when WITS availability is empty. Do not publish trade-deal/tariff outputs until WITS availability and tariff sample rows are nonzero and audited.

### Finding 3: A DuckDB rebuild path violates the partner-only `999999` convention

Severity: medium-high if `scripts/run_exercises_02_12.py` is used to rebuild partner concentration or website-facing partner outputs.

What happened: `/Users/tanushsawhney/Desktop/profps26/scripts/run_exercises_02_12.py:496-499` creates `grouped_aggregates` with `cmd_code <> '999999'` before any dimension-specific metric table is built. Then `/Users/tanushsawhney/Desktop/profps26/scripts/run_exercises_02_12.py:574-577` builds product, partner, and product-partner-cell metric tables from that same filtered view.

Why it matters: Repo rules say product-dependent analysis excludes `999999`, but partner-only concentration includes `999999` in reporter-partner totals while excluding partner `0`. This path would understate partner totals and change partner Ginis/top shares if used for canonical partner concentration. The original aggregate builder is correct: `/Users/tanushsawhney/Desktop/profps26/scripts/trade_concentration_pipeline.py:5749-5766` drops `999999` only for product/product-partner-cell frames and builds partner totals from full exports.

How to verify: Rerun the DuckDB path on a small reporter-year with known `999999` partner trade and compare partner totals to the original aggregate convention.

Exact fix: Make the DuckDB filter dimension-specific. Product and product-partner-cell rows should exclude `cmd_code == '999999'`; partner rows should not apply that product-code filter. Keep `partner_code != 0` for all canonical bilateral outputs.

### Finding 4: Old WCO-family lookup remains reachable through helper fallback paths

Severity: medium latent risk.

What happened: The default runners appear to load LT/HGL weights, but old WCO helpers remain reachable:

- `/Users/tanushsawhney/Desktop/profps26/scripts/run_exercise_12_extensive_margin.py:197-202` calls `hs_harmonization_lookup()` if `product_ids(..., "hs6_harmonized_family", hs_lookup=None)` is called directly. That lookup is the legacy WCO family map.
- `/Users/tanushsawhney/Desktop/profps26/scripts/trade_concentration_pipeline.py:6610-6616` intentionally uses legacy `harmonized_product_id` if such a mapping is passed, otherwise LT/HGL weights.
- `/Users/tanushsawhney/Desktop/profps26/scripts/run_world_relative_product_gini.py:358-363` still defines a WCO mapping SQL path helper, although I did not find it used in the LT/HGL default path.

Why it matters: The intended default is official LT/HGL weighted HS1992 conversion. A helper-level fallback makes it possible for a future caller or test to silently revive old WCO semantics while still using the same `hs6_harmonized_family` label.

How to verify: Search for `hs_harmonization_lookup`, `load_hs_harmonized_family_mapping`, and `attach_hs_harmonized_product_id` before future rebuilds.

Exact fix: Remove the WCO fallback from default helper paths. Require an explicit `legacy_wco_family` or `legacy_sensitivity` mode/name before accepting mappings with `harmonized_product_id`.

### Finding 5: Cached LT/HGL parquet provenance validation is not strong enough for future reproducibility

Severity: medium.

What happened: `/Users/tanushsawhney/Desktop/profps26/scripts/trade_concentration_pipeline.py:5987-5991` returns an existing `data/processed/lt_hgl_hs6_to_hs1992_weights.parquet` if required columns exist and weight sums validate. It does not check cached `conversion_method`, DOI, version, target revision, or raw file checksums before trusting the cache.

Why it matters: The current cached artifact is correct by direct inspection, but future runs could reuse a stale parquet with the same columns and valid weight sums but wrong source version or target.

How to verify: Inspect `data/processed/lt_hgl_hs6_to_hs1992_weights_manifest.json`; it records DOI `10.7910/DVN/6AADMR`, version `2.1`, and all six MD5s. The loader should enforce these, not just write them.

Exact fix: On cached load, assert `conversion_method == "lt_hgl_weighted_hs1992"`, `source_dataset_doi == "10.7910/DVN/6AADMR"`, `source_dataset_version == "2.1"`, `target_classification_code == "H0"`, and manifest/source-file MD5 consistency. If any check fails, rebuild or block.

### Finding 6: World-relative manifests do not record an explicit source-versus-converted value residual

Severity: medium-low, auditability gap rather than demonstrated error.

What happened: World-relative export/import aggregation preflights missing LT/HGL source pairs and then uses an inner join to weighted targets. Manifests report `lt_hgl_missing_weight_trade_value == 0.0`, duplicate-key checks, and zero `999999` panel rows. They do not record a direct source total, converted total, and residual analogous to the EV validation.

Why it matters: Weight sums imply conservation, and my direct checks found no duplicate product keys or `999999` leakage. But a replication package should expose the conservation check in the manifest, especially because the SQL path uses row expansion and aggregation.

Code evidence:

- `/Users/tanushsawhney/Desktop/profps26/scripts/run_world_relative_product_gini.py:371-400` preflights missing source pairs.
- `/Users/tanushsawhney/Desktop/profps26/scripts/run_world_relative_product_gini.py:421-454` applies the weighted inner join and aggregates by target product.
- `/Users/tanushsawhney/Desktop/profps26/scripts/run_world_relative_product_gini.py:950-959` blocks on nonzero missing-weight value.

Exact fix: Add per-flow manifest fields for filtered source trade value, weighted converted trade value, conversion residual, and residual tolerance for rd2 and benchmark samples.

## 3. Data Lineage and Sample Audit

### LT/HGL weights

Lineage: official Dataverse adjacent HS CSVs -> `ensure_lt_hgl_weight_files()` checksum validation -> `load_lt_hgl_adjacent_weights()` -> identity-fill for unchanged codes -> sparse composition back to H0/HS1992 -> normalized parquet/csv/manifest.

Source code:

- `/Users/tanushsawhney/Desktop/profps26/scripts/trade_concentration_pipeline.py:5836-5849` downloads or reuses files and checks MD5.
- `/Users/tanushsawhney/Desktop/profps26/scripts/trade_concentration_pipeline.py:5861-5903` reads adjacent weights, removes `999999`, validates raw sums within tolerance, and normalizes positive outgoing weights.
- `/Users/tanushsawhney/Desktop/profps26/scripts/trade_concentration_pipeline.py:5904-5926` fills unchanged-code identities.
- `/Users/tanushsawhney/Desktop/profps26/scripts/trade_concentration_pipeline.py:6013-6075` composes adjacent chains to HS1992/H0.
- `/Users/tanushsawhney/Desktop/profps26/scripts/trade_concentration_pipeline.py:6077-6115` writes normalized weights and manifest.

Observed diagnostics:

- Artifact: `data/processed/lt_hgl_hs6_to_hs1992_weights.parquet`.
- Rows: 50,523.
- Source revision row counts: H0 5,041; H1 5,363; H2 5,580; H3 5,769; H4 6,021; H5 6,438; H6 16,311.
- Source pairs: 36,658.
- Target revision: all H0.
- Target HS1992 codes: 5,041.
- Duplicate source-target keys: 0.
- Source `999999` rows: 0.
- Target `999999` rows: 0.
- Weight-sum min/max by source pair: 0.9999999999999998 to 1.0000000000000002.
- Max absolute weight-sum error: 2.220446049250313e-16.
- Max HS1992 targets per source pair: 1,009.

### Exercise 12 extensive margin

Lineage: `data/processed/samples/rd2_countries/exercise_12_export_aggregates.parquet` -> `read_product_partner_for_reporter()` filters product-partner-cell rows to positive trade, `partner_code != 0`, valid HS6, and not `999999` -> `apply_lt_hgl_hs1992_conversion()` -> aggregate by reporter-year-target-product-partner -> decomposition.

Source code:

- `/Users/tanushsawhney/Desktop/profps26/scripts/run_exercise_12_extensive_margin.py:165-194` filters the reporter product-partner source rows.
- `/Users/tanushsawhney/Desktop/profps26/scripts/run_exercise_12_extensive_margin.py:249-262` applies LT/HGL conversion and groups target cells.
- `/Users/tanushsawhney/Desktop/profps26/scripts/run_exercise_12_extensive_margin.py:692-788` validates country counts, `999999`, partner 0, duplicate category keys, accounting residuals, and missing LT/HGL rows.

Generated validation:

- Artifact: `results/samples/rd2_countries/exercise_12_extensive_margin_tables/extensive_margin_validation.json`.
- Status: `ok`; blockers: `[]`.
- Countries: 60 expected, 60 decomposition, 60 latest.
- Filtered source rows: 161,654,903.
- Filtered source `999999` rows: 0.
- Filtered source partner 0 rows: 0.
- LT/HGL distinct source pairs: 36,637.
- LT/HGL missing rows/value: 0 / 0.0.
- Duplicate category keys: 0.
- Category accounting residual violations: 0.
- Max absolute accounting residual: 0.0009765625, below tolerance 10.0.
- Generated table `extensive_margin_country_year.csv`: 52,434 rows, 60 countries, no duplicate reporter-base-future-horizon-identity-category keys.

Unit of observation: reporter-country, base year, future year, horizon, identity mode, mutually exclusive growth category.

### EV-style HS6 appendix

Lineage: same rd2 Exercise 12 aggregate -> filtered reporter product-partner values -> LT/HGL HS1992 conversion -> deflation to 2024 USD -> adjacent 2+2 base/future windows with $50,000 active threshold -> product, partner-spread, and combined decompositions.

Source code:

- `/Users/tanushsawhney/Desktop/profps26/scripts/run_exercise_12_ev_hs6_harmonized_expansion.py:103-135` applies LT/HGL conversion, deflation, and product-partner grouping.
- `/Users/tanushsawhney/Desktop/profps26/scripts/run_exercise_12_ev_hs6_harmonized_expansion.py:138-186` reports value conservation and LT/HGL coverage.
- `/Users/tanushsawhney/Desktop/profps26/scripts/run_exercise_12_ev_hs6_harmonized_expansion.py:557-605` validates decomposition, harmonization coverage, and value residuals before writing outputs.

Generated validation:

- Artifact: `results/samples/rd2_countries/exercise_12_ev_hs6_harmonized_expansion_tables/ev_hs6_harmonized_validation.json`.
- Status: `ok`; blockers: `[]`.
- Countries: 60 expected, 60 product decomposition, 60 latest.
- Source rows after filters: 161,654,903.
- Filtered source `999999` rows: 0.
- Filtered partner 0 rows: 0.
- Observed trade value: 344,749,076,506,873.6.
- Converted trade value: 344,749,076,506,873.6.
- Conversion residual: 0.0.
- Coverage share: 1.0.
- Unmatched value share: 0.0.
- Product accounting residual violations: 0.
- Combined accounting residual violations: 0.
- Note: `source_years_without_deflator` contains 2025; the EV window output stops at future year 2023/future year 2 2024, while the non-deflated extensive-margin output includes 2025 future years.

Unit of observation: reporter-country, adjacent base window, adjacent future window, horizon, product level, channel.

### World-relative export/import product Ginis

Lineage: raw/partial product-flow parquets -> positive HS6 rows excluding `999999` -> LT/HGL weighted conversion to HS1992/H0 in DuckDB -> rd2 product totals and world_broad product totals -> leave-one-out world benchmark -> balanced 2000-2024 rd2 panel.

Source code:

- `/Users/tanushsawhney/Desktop/profps26/scripts/run_world_relative_product_gini.py:128-151` extracts positive product trade and excludes `999999`.
- `/Users/tanushsawhney/Desktop/profps26/scripts/run_world_relative_product_gini.py:371-400` preflights missing LT/HGL source pairs.
- `/Users/tanushsawhney/Desktop/profps26/scripts/run_world_relative_product_gini.py:421-454` joins weights and aggregates target products.
- `/Users/tanushsawhney/Desktop/profps26/scripts/run_world_relative_product_gini.py:980-1024` writes run manifests and diagnostics.

Generated export panel:

- Manifest: `results/samples/rd2_countries/world_relative_product_gini_tables/run_manifest_world_relative_product_gini.json`.
- Status: `complete`.
- Product harmonization: official LT/HGL weighted conversion to HS1992/H0, DOI `10.7910/DVN/6AADMR`, version `2.1`.
- Panel rows: 1,375.
- Countries: 55.
- Years: 2000-2024.
- Duplicate country-year keys: 0.
- LT/HGL missing-weight trade value: 0.0.
- Panel `999999` product rows: 0.
- Processed rd2 product export parquet: 5,278,636 rows; duplicate reporter-year-product keys: 0; product IDs containing `999999`: 0.
- Processed world product export parquet: 125,201 rows; duplicate year-product keys: 0; product IDs containing `999999`: 0.

Generated import panel:

- Manifest: `results/samples/rd2_countries/world_relative_import_product_gini_tables/run_manifest_world_relative_import_product_gini.json`.
- Status: `complete`.
- Product harmonization: official LT/HGL weighted conversion to HS1992/H0, DOI `10.7910/DVN/6AADMR`, version `2.1`.
- Panel rows: 1,375.
- Countries: 55.
- Years: 2000-2024.
- Duplicate country-year keys: 0.
- LT/HGL missing-weight trade value: 0.0.
- Panel `999999` product rows: 0.
- Processed rd2 product import parquet: 6,621,904 rows; duplicate reporter-year-product keys: 0; product IDs containing `999999`: 0.
- Processed world product import parquet: 125,353 rows; duplicate year-product keys: 0; product IDs containing `999999`: 0.

Unit of observation: reporter-country-year for panels; reporter-year-HS1992 product for country products; year-HS1992 product for world benchmark products.

### Contributions, mechanisms, robustness

World-relative contribution manifests report `complete`, `rd2_countries`, `world_broad`, `harmonized_hs6_family`, and LT/HGL HS1992/H0:

- Export contribution manifest: `world_relative_product_gini_contributions/run_manifest_world_relative_product_contributions.json`.
- Import contribution manifest: `world_relative_import_product_gini_contributions/run_manifest_world_relative_import_product_contributions.json`.
- Contribution panels use 1,375 country-years and 20,625 top-driver rows per flow.

Regression/mechanism outputs are conditional on upstream product panels:

- Future-growth diagnostics: `future_growth_concentration_tables/sample_diagnostics.csv` reports 7,690 panel rows, 60 countries, 1988-2025, horizons 5 and 10. Model tables report clustered-by-reporter standard errors and 60 clusters for core 5-year models.
- Import-size mechanism diagnostics: `import_size_mechanism_tests/import_size_mechanism_diagnostics.csv` reports 1,375 balanced rows, 55 countries x 25 years, 6,202,707 balanced country-product rows, duplicate country-product keys 0, and country-product `999999` rows 0.
- World-relative robustness diagnostics report export rows of 1,375 for country-size, 4,125 for growth, 1,375 for Exercise 11 aggregate, and 3,344 for Exercise 02 common samples; import has analogous 1,375/4,125/1,375 rows.

### Trade-deal diagnostics

LT/HGL HS4 bridge coverage is not the binding problem:

- Coverage file: `data/processed/samples/rd2_countries/trade_deal_hs4_baseline_harmonization_coverage.csv`.
- Rows: 60.
- Reporters: 60.
- Coverage min/mean/max: 1.0 / 1.0 / 1.0.
- Uncovered rows: 0.
- Uncovered value: 0.0.

But WITS availability is not available:

- `source_manifest.json` reports `wits_availability.rows == 0`, `nomenclature_codes == []`, `reporters_with_availability == 0`.
- Primary WITS HS4 2001-2021 sample rows: 0.
- Primary WITS HS4 long sample rows: 0.
- The trade-deal pipeline must remain blocked.

## 4. Merge/Join Audit

- LT/HGL adjacent composition uses many-to-many merges intentionally because one source code can split into multiple target codes and target chains can split further. `/Users/tanushsawhney/Desktop/profps26/scripts/trade_concentration_pipeline.py:6019-6047` blocks if any intermediate target cannot be composed.
- The LT/HGL application join is many-to-many by design. `/Users/tanushsawhney/Desktop/profps26/scripts/trade_concentration_pipeline.py:6173-6196` blocks if any source code has missing target weights, then multiplies trade value by `conversion_weight`.
- Exercise 12 extensive-margin grouping after conversion collapses the expanded rows by reporter-year-product-partner, eliminating duplicate target keys before decomposition.
- World-relative product aggregation uses an inner join to the weights, but first runs a missing-weight preflight. This is acceptable given the preflight, but the manifest should add source-versus-converted value residuals.
- Contribution code merges product labels onto HS1992 target products and treats labels as non-authoritative. The authoritative product ID remains `HS1992:xxxxxx`.
- Trade-deal country and tariff reporter-year mapping uses exact or documented EU customs-territory mapping, but WITS availability is not checked/populated in the current manifest, so tariff sample joins are not usable.

## 5. Variable Construction Audit

- Product identity: `product_id = "HS1992:" + target_cmd_code` after official LT/HGL weighted conversion to H0/HS1992. This is implemented in `/Users/tanushsawhney/Desktop/profps26/scripts/trade_concentration_pipeline.py:6077-6079`.
- Trade value under conversion: `converted_trade_value = source_trade_value * conversion_weight`, then aggregated to the target product. This is implemented in `/Users/tanushsawhney/Desktop/profps26/scripts/trade_concentration_pipeline.py:6197-6204`.
- Product-dependent exclusion: `999999` is removed before conversion in `apply_lt_hgl_hs1992_conversion()` and in product-flow SQL paths. Direct artifact checks found no `999999` product IDs in converted rd2/world product parquets.
- Partner convention: original Exercise 12 aggregate construction keeps `999999` in partner totals, but the later DuckDB rebuild path does not. Do not use that DuckDB path for canonical partner metrics until patched.
- Exercise 12 extensive-margin categories are mutually exclusive and validated to sum to total growth within tolerance.
- EV-style appendix deflates to 2024 USD and applies a $50,000 active threshold. The missing 2025 deflator causes 2025 EV windows to be omitted; this should be disclosed when comparing EV-style outputs to non-deflated 2025 extensive-margin outputs.
- World-relative product Gini uses `weighted_gini(s_cpt / w_-c,pt, w_-c,pt)`, with leave-one-out world product weights. This is a constructed descriptive concentration measure, not a causal estimand.

## 6. Specification Audit

For the harmonized product construction, the effective measurement equation is:

`x^H0_cpt = sum_(h,r) x_c,h,r,t * w_(h,r -> p,H0)`

where `c` is reporter country, `t` is year, `h` is source HS revision, `r` is source HS6 code, `p` is target HS1992 code, and `w` is the official LT/HGL conversion weight after documented normalization/identity handling.

For Exercise 12 extensive margin, the accounting target is:

`Delta X_c,t,horizon = sum_(p,k) [x_c,p,k,t+horizon - x_c,p,k,t]`

where `p` is LT/HGL HS1992 product and `k` is partner. Categories are mutually exclusive: new product first, then new partner for existing product, then new product-partner cell, then continuing cell growth/contraction/no-change.

For world-relative product Gini:

`s_cpt = v_cpt / sum_p v_cpt`

`w_-c,pt = (B_pt - v_cpt) / sum_p (B_pt - v_cpt)`

`WorldRelativeGini_ct = weighted_gini(s_cpt / w_-c,pt, w_-c,pt)`

For downstream panel regressions, the generic reported form is:

`y_ct = beta * concentration_ct + gamma' controls_ct + alpha_c + lambda_t + epsilon_ct`

or horizon variants for growth outcomes. The output tables report country/year fixed effects depending on the model and clustered standard errors. The econometrics graph check supports robust/clustered standard errors for panel fixed-effect settings, especially with serial correlation and cluster dependence. The reported cluster counts are generally 55 or 60 reporter clusters, with some two-way-cluster robustness using 25 year clusters.

Interpretation caveat: these mechanism regressions are descriptive unless a separate identification design is supplied. They are suitable as robustness/mechanism diagnostics, not causal evidence by themselves.

## 7. Inference and Identification Audit

- The LT/HGL conversion, Exercise 12 decomposition, and world-relative Gini construction are deterministic data transformations. Their main inferential risk is data lineage and measurement error, not standard-error calculation.
- Downstream regressions use clustered standard errors by reporter and, in some robustness tables, two-way clustering by reporter and year. This is directionally appropriate for panel dependence, but the outputs should not be read causally without an identification design.
- Cluster counts are acceptable for descriptive panel regressions: 55 balanced-country clusters in world-relative panels and 60 country clusters in future-growth models. Two-way clustering has only 25 year clusters, so year-cluster inference should be treated as robustness rather than definitive small-sample inference.
- Balanced-panel restriction matters: world-relative panels use 55 countries over 2000-2024, not all 60 rd2 countries. This is documented in manifests and should be visible on the website.
- Multiple testing is reported in several downstream tables via BH q-values. This helps, but mechanism conclusions should distinguish raw p-values from adjusted q-values.

## 8. Replication Checklist

Before publication, run or verify:

1. Weight provenance:
   - Check `data/processed/lt_hgl_hs6_to_hs1992_weights_manifest.json` DOI/version/MD5s.
   - Recompute weight sums and duplicate source-target checks.
   - Confirm source and target `999999` rows equal zero.

2. Exercise 12:
   - Verify `results/samples/rd2_countries/exercise_12_extensive_margin_tables/extensive_margin_validation.json` has `status == "ok"`.
   - Verify `results/samples/rd2_countries/exercise_12_ev_hs6_harmonized_expansion_tables/ev_hs6_harmonized_validation.json` has `status == "ok"`.
   - Check 60 countries, zero `999999`, zero partner 0, zero missing LT/HGL value, zero duplicate keys, zero accounting residual violations.

3. World-relative:
   - Verify export/import manifests have `status == "complete"`, `country_sample == "rd2_countries"`, `benchmark_sample == "world_broad"`, product harmonization DOI/version/target, 1,375 rows, 55 countries, and zero LT/HGL missing-weight value.
   - Add and verify direct source-versus-converted value residuals.

4. Trade deal:
   - Do not run or publish tariff regressions until WITS availability is fetched and primary WITS HS4 samples have nonzero rows.
   - Fix the misleading `hs4_harmonization_coverage_gate_failed` blocker when the real failure is WITS availability.

5. Partner convention:
   - Patch and test `scripts/run_exercises_02_12.py` so partner metrics include `999999` while product/product-partner metrics exclude it.

6. Website:
   - Rebuild staging from the current source with `scripts/build_trade_gini_site.py --country-sample rd2_countries`.
   - Validate `/Users/tanushsawhney/Desktop/trade-gini-map/assets/site-manifest.json`.
   - Search staged HTML and downloads for stale WCO language.
   - Only then publish staging.

## 9. Minimal Patch Plan

1. Rebuild and validate the staging site. This is the only hard publication blocker for the already-generated core LT/HGL product outputs.
2. Patch `scripts/run_exercises_02_12.py` so the `999999` filter is dimension-specific and partner metrics keep unspecified-product trade in partner totals.
3. Remove default WCO fallback behavior from `product_ids()` and any default `hs6_harmonized_family` helper path. Keep WCO only behind an explicit legacy-sensitivity name.
4. Strengthen cached LT/HGL parquet validation to enforce DOI, version, target revision, conversion method, and manifest/checksum consistency.
5. Add world-relative source-versus-converted trade-value residuals to export/import manifests.
6. Split trade-deal blocker names so LT/HGL HS4 coverage and WITS availability failures are not conflated.

## 10. Questions for the Researcher

1. Is the current staging site intended to be public-facing now, or should publication wait until the new LT/HGL site build is completed and verified?
2. Should the HGL adjacent weights be normalized within source code after excluding `999999`, as currently documented in `code_processing.md:190-197`, or should raw official weights be preserved even when rounded/raw sums differ slightly from one?
3. Should 2025 be excluded from all LT/HGL headline outputs for consistency with the EV deflator limit, or is it acceptable that extensive-margin outputs include 2025 while EV-style constant-dollar outputs stop at 2024?
4. Should trade-deal/tariff diagnostics be deferred until WITS availability is fetched, or should the current zero-row WITS outputs be removed from the publication bundle entirely?

## 11. Follow-Up Clearance Addendum

Review date: 2026-06-03

Follow-up verdict: cleared to push staging for the LT/HGL website-facing materials, with the explicit caveat that trade-deal/tariff outputs remain blocked by WITS availability and should not be presented as usable tariff evidence.

Scope: I re-checked only the issues flagged above. I did not re-audit unrelated empirical results.

Verified fixes:

1. Staging site stale-method blocker is cleared.
   - `/Users/tanushsawhney/Desktop/trade-gini-map/assets/site-manifest.json` now reports `country_sample == "rd2_countries"`, `country_count == 60`, Exercise 12 method `EV-style LT/HGL weighted HS6-to-HS1992 persistent expansion decomposition`, and product label `LT/HGL-weighted HS1992 products`.
   - Searches over staged HTML and `assets/site-manifest.json` found none of the stop-publication stale phrases: `current WCO-family harmonization`, `not the full LT/HGL`, `connected component of revision-code nodes`, or `Harmonized-HS6 persistent`.
   - Staged pages now contain the intended LT/HGL language. For example, `/Users/tanushsawhney/Desktop/trade-gini-map/exercise-12.html:43-44` describes the LT/HGL HS1992 decomposition, `/Users/tanushsawhney/Desktop/trade-gini-map/exercise-12.html:89` cites Lukaszuk and Torun and HGL/Dataverse weighted conversion, `/Users/tanushsawhney/Desktop/trade-gini-map/methods.html:69-71` gives the DOI/method, and `/Users/tanushsawhney/Desktop/trade-gini-map/world-gini.html:44` uses LT/HGL-weighted HS1992 products.
   - Staged downloads include `lt_hgl_hs1992_harmonization_adversarial_review.md`; the old `exercise_12_ev_hs6_harmonized_adversarial_review.md` is no longer present.

2. Partner-only `999999` convention fix is cleared for the checked paths.
   - `/Users/tanushsawhney/Desktop/profps26/scripts/run_exercises_02_12.py:500-506` now excludes `cmd_code == '999999'` only when `dimension` is `product` or `product_partner_cell`; partner rows are not filtered by product code.
   - `/Users/tanushsawhney/Desktop/profps26/scripts/run_exercises_02_12.py:699-724` applies the same dimension-specific `999999` filter in the parquet reader helper.
   - The new focused test at `/Users/tanushsawhney/Desktop/profps26/tests/test_exercise_12_repair.py:113-160` checks that DuckDB grouped views keep `999999` in partner totals while excluding it for product-dependent rows.

3. Old WCO default fallback risk is cleared for the checked extensive-margin helper.
   - `/Users/tanushsawhney/Desktop/profps26/scripts/run_exercise_12_extensive_margin.py:196-205` now raises when `hs6_harmonized_family` is requested without an explicit lookup and tells callers to use row-expanding LT/HGL preparation or an explicit legacy sensitivity mapping.
   - I did not find the old WCO SQL helper in `scripts/run_world_relative_product_gini.py` after the fix.

4. Trade-deal blocker labeling is corrected.
   - `results/samples/rd2_countries/trade_deal_market_access/source_manifest.json` now reports blockers `["wits_nomenclature_availability_missing", "wits_availability_not_complete"]`.
   - The same manifest reports HS4 harmonization `status == "passed"`, 60 expected/reporting exporters, coverage `1.0`, zero excluded `999999` value in the HS4 coverage denominator, and no `hs4_harmonization_coverage_gate_failed` blocker.
   - `/Users/tanushsawhney/Desktop/profps26/scripts/build_trade_deal_market_access_diagnostics.py:2530-2555` now separates WITS nomenclature availability failure from HS4 coverage failure.

5. World-relative value-conservation manifest gap is cleared.
   - `/Users/tanushsawhney/Desktop/profps26/scripts/run_world_relative_product_gini.py:459-504` computes filtered source value, weighted converted value, residual, tolerance, and status.
   - Export manifest value-conservation statuses are `ok` for both `rd2_countries` and `world_broad`; residuals are 0.5 and 0.1875 against tolerances 301,414.58 and 353,432.48.
   - Import manifest value-conservation statuses are `ok` for both `rd2_countries` and `world_broad`; residuals are -0.0625 and 0.9375 against tolerances 315,845.40 and 365,720.33.

6. Cached LT/HGL provenance validation gap is cleared for the checked loader.
   - `/Users/tanushsawhney/Desktop/profps26/scripts/trade_concentration_pipeline.py:5975-6025` now validates cached conversion method, DOI, version, H0 target, target product prefix, manifest presence, manifest metadata, manifest/parquet row count, and raw file MD5s.
   - `/Users/tanushsawhney/Desktop/profps26/scripts/trade_concentration_pipeline.py:6041-6046` calls both weight-sum validation and cached provenance validation before returning a cached parquet.

Verification commands run:

- `/opt/anaconda3/bin/python -m py_compile scripts/trade_concentration_pipeline.py scripts/run_exercise_12_extensive_margin.py scripts/run_world_relative_product_gini.py scripts/run_exercises_02_12.py scripts/build_trade_deal_market_access_diagnostics.py scripts/build_trade_gini_site.py`
- `/opt/anaconda3/bin/python -m pytest tests/test_exercise_12_repair.py tests/test_exercise_12_extensive_margin.py tests/test_world_relative_product_gini.py tests/test_trade_deal_market_access_diagnostics.py -q`
- Result: 42 passed.

Remaining caveats:

1. Trade-deal/tariff outputs remain blocked by WITS availability. The source manifest still has `wits_availability.rows == 0`, `nomenclature_codes == []`, and `reporters_with_availability == 0`. Do not publish tariff/regression claims from those zero-row WITS samples.
2. Minor wording cleanup remains optional before push: a few generated Exercise 12 table row labels still say "harmonized HS6 product families" while the surrounding headings and methods correctly say LT/HGL HS1992. I do not treat this as a stop-publication issue because the stale WCO/full-LT caveat is gone and the method text is clear, but a stricter style gate could relabel those row labels as LT/HGL HS1992 products.
