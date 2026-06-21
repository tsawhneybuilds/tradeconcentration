# Adversarial Trust Review: Harmonized Cadot 156 Three-Metric Site Outputs

Review date: 2026-06-17

Scope: local adversarial review of the generated Gini/Theil/HHI Cadot-style broad-sample outputs in `results/samples/cadot_broad_156/three_metric_tables`.

Independence note: this was not a fresh subagent review. The available workflow in this run did not expose an independent reviewer agent, so the review was performed locally against the raw manifest, validation file, generated tables, and site-build inputs rather than against the builder's summary.

## Executive Verdict

Trustworthy for staging deployment with caveats. The current harmonized run satisfies the stated hard gates: 156 selected reporters, 3,787 raw files processed, LT/HGL-weighted HS1992/H0 product identities, fixed universe sourced from `world_broad`, 5,037 fixed product families for both exports and imports, no product-dependent `999999`, HHI within `[0,1]`, Theil residuals at numerical zero, cross-metric key parity, and Exercise 11 published as a compressed `.csv.gz`.

## Highest-Risk Findings

1. This review is local, not an independent fresh-agent pass. The artifact checks are concrete and reproducible, but a separate reviewer should still be used before making publication-grade claims from the site.

2. Exercise 11 is a top absolute leave-one-out product contribution table, not a full all-product long universe. It is appropriate for a website-facing download, but page copy should avoid implying that every product contribution is retained.

3. Exercise 10 uses 250 random simulations per reporter-year-flow benchmark. These are descriptive random benchmark summaries, not exact analytical null distributions.

4. The outputs are descriptive concentration measures and exercise summaries. They do not support causal identification, fixed-effects interpretation, clustered inference, or regression claims unless those analyses are separately specified and audited.

## Data Lineage And Sample Audit

- Sample rule: `cadot_broad_156`, 2000-2024, minimum 19 annual HS final-data years.
- Reporter gate: passed with exactly 156 selected reporters.
- Raw files processed: 3,787.
- Product identity: LT/HGL-weighted HS1992/H0 harmonized product families.
- Harmonization provenance: LT/HGL method `lt_hgl_weighted_hs1992`, DOI `10.7910/DVN/6AADMR`, version `2.1`, target `HS1992/H0`.
- Fixed universe source: 2000-2024 union of positive `world_broad` harmonized product-family support by flow.
- Fixed product universe counts: Exports = 5,037; Imports = 5,037.
- Availability convention: available-observation rows are retained; balanced 2000-2024 flags and exercise complete-case flags are recorded separately.
- Product-dependent outputs exclude HS6 `999999` before conversion and aggregation.
- Partner-only concentration follows the project convention: product identity is summed away, HS6 `999999` may contribute to totals, and `partnerCode == 0` is excluded.

## Merge And Key Audit

- `unique_reporter_year_flow_dimension_variant`: passed, duplicate rows = 0.
- `cross_metric_key_parity`: passed, rows with missing metric = 0.
- `raw_files_present_for_available_country_years`: passed, missing available bulk keys = 0.
- `cadot_product_universe_within_world_broad_universe`: passed for the harmonized HS1992/H0 product universe.
- Website-facing product-dependent table headers were checked for stale native-HS leakage: `classification_code` is absent and provenance uses `source_classification_code` where raw-file provenance is retained.
- Exercise 11 compressed download exists as `exercise_11_top_product_loo_contributions.csv.gz`; the raw 159 MB CSV must not be copied into the static site.

## Variable Construction Audit

- Gini: active-positive product concentration convention retained.
- Theil headline: fixed-universe product Theil, `sum_p s_cpft * log(s_cpft * K_f)`, with missing reporter products entering through the inactive margin.
- Theil decomposition: `T_fixed = T_active + log(K_f / A_cft)`; validation residual maximum absolute value is within numerical tolerance.
- HHI headline: raw `sum_i s_i^2`; validation confirms all website-facing HHI values are within `[0,1]`.
- Exercise 10: Theil benchmarks preserve the fixed universe and active count; HHI benchmarks preserve active count.
- Exercise 11: metric-specific leave-one-out product contributions use harmonized HS1992 product-family identifiers.
- Exercise 12: the product/partner growth decomposition is common, then stratified by base-year concentration buckets for Gini, Theil, and HHI.

## Specification And Reporting Audit

- The website-facing metric comparisons use common reporter-year-flow rows across Gini, Theil, and HHI.
- Exercise complete-case flags are present for Exercises 1, 2, 3, 4, 6, 10, 11, and 12.
- The manifest records sample window, reporter count, raw-file count, harmonization method, product universe source/counts, formulas, validation outputs, and table paths.
- The Theil appendix is correctly treated as a product-destination/cell HS1992-family analogue, distinct from the fixed-universe product Theil headline.

## Inference And Identification Audit

- No causal estimand is identified by these outputs.
- No regression specification, fixed-effect structure, clustering rule, or hypothesis-testing inference is being reported by the static site bundle.
- Availability and complete-case flags are the correct safeguards for descriptive comparisons, but any regression or causal extension would require a separate sample-construction and inference audit.

## Replication Checklist

- Source compile check: `python3 -m py_compile scripts/run_cadot_three_metric_pipeline.py scripts/build_trade_gini_site.py`.
- Fast finalization command: `python3 scripts/run_cadot_three_metric_pipeline.py --country-sample cadot_broad_156 --simulations 250 --chunk-rows 1000000 --manifest-every 25`.
- Manifest values checked: `product_id_mode=harmonized_hs6_family`, `harmonization_method=lt_hgl_weighted_hs1992`, `harmonization_target=HS1992/H0`, `fixed_universe_source=world_broad`.
- Validation file: `validation_checks.csv`, all 11 checks passed.
- Exercise 11 compression recreated after finalization.
- Site build command: `python3 scripts/build_trade_gini_site.py --country-sample cadot_broad_156 --output /tmp/trade-concentration-sites`.

## Minimal Patch Plan

No blocking patch remains before staging deployment if the local site validation confirms pages, links, downloads, file sizes, and stale raw Exercise 11 exclusion. Before production deployment, run an independent fresh-agent adversarial review and keep the review anchored to the final published manifest.

## Questions

No blocking empirical questions remain for staging. The main open publication question is whether a later production site should include a separate heavy-output mode for the full Exercise 11 all-product contribution universe.
