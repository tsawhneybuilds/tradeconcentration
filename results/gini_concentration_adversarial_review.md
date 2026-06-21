# Gini And Concentration Adversarial Review

Created: 2026-05-25 04:30 UTC

## Executive Verdict

Trust the core non-site Gini and concentration arithmetic, with caveats.

I found no blocking arithmetic bug in the active-positive Gini, active top-share,
leave-one-out Gini, importer-product supplier HHI, or top-supplier share
formulas. Formula stress tests, unit tests, sampled recomputation from source
aggregates, and a fresh spawned reviewer all agree that the current persisted
non-site outputs match the intended calculations to numerical precision.

Do not treat the website-facing layer as fully certified yet. The repo rule
requires `rd2_countries` for website outputs, and the current
`results/samples/rd2_countries/` tree contains directories but no source CSV or
parquet artifacts to validate.

## Findings

1. High: site-facing `rd2_countries` metrics cannot be certified.

   `scripts/build_trade_gini_site.py` defaults to `rd2_countries`, but the
   `results/samples/rd2_countries/` folders do not currently contain the source
   artifacts needed for validation. Under the repo website rules, the site must
   stop rather than fall back to `prof_p_33`, `world_broad`, stale outputs, or a
   partial sample.

2. Medium: active-positive Gini is correct but must be named plainly.

   The shared helper computes inequality over finite positive observed values
   only. That is correct for the current estimand, but it is not a
   zero-inclusive universe or product-variety measure. I updated the site labels
   and definitions to say "Active" and "observed positive" explicitly.

3. Low: Exercise 4 supplier helper relied on upstream exclusion.

   Current persisted outputs were clean, but `exercise_04_supplier_values_for_leaf`
   was not self-contained. I added a local `drop_excluded_hs6` call before the
   helper groups importer-year-product-partner cells.

4. Low: diagnostics are strong but sampled.

   The recomputation audit samples persisted Exercise 1 and Exercise 4 outputs.
   It is enough to validate the formula path, but a full trust release should
   add an exhaustive recompute manifest over every persisted country-year.

## Data Lineage And Sample Audit

- HS6 `999999` is treated as "Commodities not specified" and must not enter
  concentration denominators, ranks, Gini values, leave-one-out statistics, or
  output tables.
- Reviewed artifacts scanned for relevant code columns reported zero `999999`
  rows in concentration, top-five, Exercise 3, Exercise 4, Exercise 11, and
  Exercise 13 processed outputs.
- Website outputs remain uncertified until the `rd2_countries` artifacts are
  rebuilt and scanned.

## Merge/Join Audit

No concentration-specific merge bug was found. Product labels, partner labels,
and country metadata are attached after metric construction and do not affect
Gini, HHI, or top-share denominators. The top-five validation compares partner
top-five sums back to the baseline concentration table.

## Variable Construction Audit

- `active_gini(values)` filters to finite positive values, sorts ascending, and
  applies the standard finite-sample rank formula.
- `active_top_share(values, n=...)` and `active_top_share(values, pct=...)`
  use the same active-positive denominator and cap top-`n` at the active count.
- `active_loo_gini_contributions(values)` equals total active Gini minus active
  Gini after deleting each positive item; zeros and missing values receive
  `NaN` contributions.
- Importer-product supplier HHI is `sum_j share_j^2`, where each supplier share
  is supplier imports divided by total imports for one importer-year-HS6 product.
- H24 effective supplier count equals `1 / supplier_hhi`; integrity checks found
  no formula mismatch or HHI bound violation.

## Specification Audit

The estimand is concentration among observed active products, partners, or
product-partner cells. This is defensible for observed trade concentration. It
does not measure concentration relative to the full possible HS6 universe; if
that interpretation is needed, add a separate zero-inclusive robustness measure.

## Inference/Identification

This review concerns constructed concentration measures, not causal
identification. Downstream Exercise 11 and Exercise 13 regressions still carry
their own econometric caveats from the broader trust review.

## Replication Checklist

- `python3 tests/test_concentration_metrics.py`: 7 tests OK.
- `results/adversarial_review_tables/gini_formula_stress_checks.csv`: 110
  formula checks, max absolute difference `6.44e-15`.
- `results/adversarial_review_tables/gini_metric_recompute_checks.csv`: 273
  sampled Exercise 1 recompute checks, max absolute difference `2.22e-16`, zero
  sampled source `999999` rows.
- `results/adversarial_review_tables/supplier_hhi_top_share_recompute_checks.csv`:
  240 sampled supplier checks, max absolute difference `5.96e-08`.
- `results/adversarial_review_tables/top5_concentration_integrity_checks.json`:
  zero product `999999` rows, exact share and summary consistency.
- `results/adversarial_review_tables/h24_supplier_concentration_integrity_checks.json`:
  zero `999999` rows, exact top-share/effective-count formulas, no HHI bound
  violations.

## Minimal Patch Plan

Completed in this pass:

- Made Exercise 4 supplier aggregation self-contained against `999999`.
- Made site-facing Gini labels and definitions explicit about active-positive
  observed values.
- Added direct `active_top_share` unit coverage.

Still required before full public/site certification:

- Rebuild `rd2_countries` artifacts.
- Run the site builder and scan generated downloads.
- Add an exhaustive persisted-output recompute manifest if this needs to be a
  release-grade audit rather than a sampled adversarial verification.

## Questions

- Should the paper/site include a zero-inclusive HS6-universe Gini robustness
  table, or is the active-positive observed-trade estimand the intended final
  definition?
