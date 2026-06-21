# Full rd2 UNCTAD-Style Theil Rerun Plan

Generated: 2026-06-03

## Summary

Build an HS6-family analogue of UNCTAD's overall product-market Theil. All reported country-year outputs use `rd2_countries`. `world_broad` is used only to define the fixed benchmark product universe and for comparison diagnostics.

Headline decomposition:

`overall_product_destination_theil = product_theil + destination_within_product_theil`

Nested product decomposition:

`product_theil = active_product_theil + inactive_product_margin_theil`

Secondary partner-first decomposition:

`overall_product_destination_theil = partner_theil_product_cell_based + product_within_partner_theil`

This is not an exact UNCTAD SITC Rev.3 replication. It is an HS6-family analogue that preserves the logic of UNCTAD's product-plus-market decomposition and can feed the existing rd2 exercise suite.

## Measurement Design

Unit of observation: reporter-year-flow.

Input cells: positive product-destination trade values after:

- excluding HS6 `999999` before product-dependent aggregation
- excluding `partnerCode == 0` World before destination/cell aggregation
- LT/HGL-weighted harmonization to HS1992/H0 product families

Fixed universes:

- product universe: 2000-2024 union of positive `world_broad` harmonized product-family support, by flow
- destination universe: 2000-2024 union of valid global partner codes observed in rd2 product-destination cells, by flow, excluding `partnerCode == 0` World. This is not limited to rd2 countries as partners. Aggregate-like partner codes are labeled in diagnostics but kept in the default panel so product marginals reconcile with existing product-only outputs; aggregate exclusions are a sensitivity, not the default.
- cell universe size: `K_product * K_destination`; never materialized as a full zero table

Definitions:

- `overall_product_destination_theil = sum_pd s_pd * log(s_pd * K_product * K_destination)`
- `product_theil = sum_p s_p * log(s_p * K_product)`
- `destination_within_product_theil = overall_product_destination_theil - product_theil`
- `active_product_theil = sum_active_p s_p * log(s_p * A_product)`
- `inactive_product_margin_theil = log(K_product / A_product)`
- `partner_theil_product_cell_based = sum_d s_d * log(s_d * K_destination)`
- `product_within_partner_theil = overall_product_destination_theil - partner_theil_product_cell_based`
- normalized overall Theil = `overall_product_destination_theil / log(K_product * K_destination)`
- normalized product Theil = `product_theil / log(K_product)`
- normalized partner Theil = `partner_theil_product_cell_based / log(K_destination)`
- component shares use `overall_product_destination_theil` as the denominator when the total is positive

Standalone partner Theil is a separate diagnostic using the repo's default partner convention: products are summed away, `partnerCode == 0` is excluded, and `999999` is included by default unless explicitly labeled as a sensitivity.

## Universe Contract

- `K_product` is fixed within flow over 2000-2024 and comes only from `world_broad` harmonized HS6-family product support.
- `K_destination` is fixed within flow over 2000-2024 and comes from the union of active rd2 reporter product-destination partners after all product-dependent filters.
- Self-partners are kept if present as valid non-World partner codes because the observed cell universe is a trade-record universe, not a political-neighbor universe.
- Aggregate-like partner groups are labeled from the partner reference but kept by default; any partner codes that cannot be classified are listed in diagnostics before use.
- All product-first and partner-first decompositions use the same filtered active product-destination cell table and the same `total_trade_value`.
- Product marginals summed from product-destination cells must reproduce the existing fixed-universe product Theil panel within tolerance, or the run stops.

## Implementation Sequence

1. Write this plan and run a Referee2-style plan review.
2. Revise this plan using the Referee2 gate findings before full execution.
3. Add/extend Theil metric tests for product-first and partner-first cell decomposition.
4. Build a bounded product-destination aggregate pipeline:
   - process one flow at a time
   - process one raw file at a time unless memory diagnostics justify a small worker count
   - write per-file or per-reporter-year checkpoints
   - compact checkpoints using DuckDB/PyArrow
5. Build the product-destination Theil panel and diagnostics:
   - processed parquet panel
   - all-years CSV
   - latest rankings
   - yearly summary
   - rich-proxy Japan/Korea comparison
   - Gini comparison
   - UNCTAD bridge comparison
   - manifest and markdown method note
6. Port the exercise suite where the Gini exercise has a country-year concentration analogue, after the base product-destination panel passes validation:
   - Exercise 1 baseline persistence
   - Exercise 2 growth buckets
   - Exercise 3 import bins
   - Exercise 4 dominant suppliers
   - Exercise 6 exclusions
   - Exercise 10 random benchmark
   - Exercise 11 input-output linkages
   - Exercise 12 export transitions
   - country-size, PPP/Cadot hump, growth, future growth, partner stability, import mechanisms, world-relative comparisons
7. Build a separate `theil-repo` static site from rd2 outputs only.
8. Run adversarial econometrics review and Referee2 code audit after outputs exist.
9. Validate the site and deploy to `tsawhneybuilds/theil-repo`. This destination is authorized by the user's explicit request and should not fall back to the default Gini staging repo.
10. Write a final "what changed vs Gini" report.

## Memory And CPU Rules

- Reuse existing harmonized product aggregates for product-only components when possible.
- For product-destination cells, stream raw chunks and checkpoint aggregates instead of holding all cells in memory.
- Do not build a full product-destination Cartesian table.
- Use active cells plus fixed universe counts to compute zero-inclusive Theil.
- Default worker count is 1. Raise to 2 only after a successful dry run on at least 10 raw files with stable memory.
- Default raw chunk size is 250,000 rows. Reduce to 100,000 if resident memory crosses 70% of the configured budget.
- Default memory budget is 10 GB unless a smaller command-line budget is supplied.
- Set DuckDB `memory_limit` to 75% of the configured budget, `threads` to the chosen worker count, and a local temp directory under the rd2 checkpoint directory.
- Log resource use after each raw file, each checkpoint compaction, and each DuckDB materialization.
- Stop if resident memory exceeds the configured budget or if free disk space falls below twice the estimated checkpoint size.
- Use checkpoint resume mode by default; `--fresh` is required to delete and rebuild existing partials.
- Stop with an explicit blocker if rd2 raw inputs, benchmark product universe, or harmonization weights are incomplete.

## Validation And Review

Unit tests:

- uniform Theil equals `0`
- monopoly Theil equals `log(K)`
- normalized monopoly equals `1`
- zero cells do not need epsilons
- product-first and partner-first decompositions equal the same total
- `product_theil = active_product_theil + inactive_product_margin_theil`

Data validation:

- no `999999` in product-dependent raw filters, checkpoints, cached panels, downloads, or site data
- no `partnerCode == 0` in cell outputs or intermediate cell checkpoints
- partner-code diagnostics include plain-English partner names and aggregate/valid-status labels
- unique reporter-year-flow keys
- unique reporter-year-flow-product-destination keys after checkpoint compaction
- fixed universe counts constant over 2000-2024
- decomposition residuals below tolerance
- source totals reconcile with checkpoint and final-panel totals within floating-point tolerance
- product marginals from product-destination cells reproduce existing fixed-universe product Theil rows within tolerance
- no stale or fallback sample artifacts used for website outputs

Empirical validation:

- compare Theil panel with existing Gini panel on identical reporter-year-flow keys
- reproduce the official UNCTAD 2024 Japan/Korea/Taiwan 73% bridge from downloaded UNCTAD series
- report whether Japan/Korea move closer to the UNCTAD result after adding destination-within-product concentration
- label the UNCTAD bridge as an external official-series comparison, not exact HS6 validation

Referee2/code-audit protocol:

- independent toy decomposition checks for uniform, monopoly, zero-inclusive, product-first, partner-first, and active/inactive product cases
- independent recomputation for selected real reporter-year-flow cells, including Japan 2024 exports, Korea 2024 exports, and at least one high-income comparator
- comparison tables for totals, `K_product`, `K_destination`, active counts, product marginals, partner marginals, overall Theil, component residuals, and normalized values
- discrepancy classification: formula bug, filter drift, harmonization drift, universe mismatch, floating-point noise, or data availability issue
- downstream regressions, if regenerated, must preserve the repo rule that raw p-values and adjusted q-values are visually highlighted when below 0.05

## Outputs

Primary processed outputs:

- `data/processed/samples/rd2_countries/product_destination_theil_panel.parquet`
- `results/samples/rd2_countries/product_destination_theil_tables/product_destination_theil_all_years.csv`
- `results/samples/rd2_countries/product_destination_theil_tables/product_destination_theil_yearly_summary.csv`
- `results/samples/rd2_countries/product_destination_theil_tables/product_destination_theil_latest_rankings.csv`
- `results/samples/rd2_countries/product_destination_theil_tables/product_destination_theil_rich_proxy_summary.csv`
- `results/samples/rd2_countries/product_destination_theil_tables/product_destination_theil_gini_comparison.csv`
- `results/samples/rd2_countries/product_destination_theil_tables/product_destination_theil_unctad_bridge.csv`
- `results/samples/rd2_countries/product_destination_theil_tables/product_destination_theil_manifest.json`
- `results/samples/rd2_countries/product_destination_theil_tables/product_destination_theil.md`

Review outputs:

- `correspondence/referee2/2026-06-03_theil_rerun_plan_review.md`
- `results/samples/rd2_countries/product_destination_theil_tables/adversarial_review.md`
- `correspondence/referee2/2026-06-03_theil_rerun_code_audit.md`

Site outputs:

- generated static site for `tsawhneybuilds/theil-repo`
- public GitHub Pages URL after deployment

## Current Implementation Notes

The existing fixed-universe product-only Theil panel has already been built. It should be treated as a component/diagnostic, not the headline UNCTAD-style product-market Theil.

The next implementation stage must build product-destination cells and the destination-within-product component. Product-only Theil showed Japan/Korea were not outliers in 2024 exports, so the key empirical test is whether destination-within-product concentration changes that conclusion.
