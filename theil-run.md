# Theil Replication Run Plan

Generated: 2026-06-03

## Goal

Replicate the Gini concentration project with Theil measures, keeping it separate from the existing Gini site and outputs.

The first implemented pass builds the defensible base panel:

- fixed-universe product Theil over LT/HGL-weighted HS1992 product families
- active-only product Theil as a robustness contrast
- explicit active/inactive product-margin decomposition
- world-relative product Theil, interpreted as KL divergence from the leave-one-out world product basket
- side-by-side comparison against the existing active Gini panel and the existing fixed-universe Product Gini panel
- UNCTAD bridge context for why Theil can show Japan/Korea/Taiwan as outliers while active Gini does not

## Measurement Rules

Product-dependent outputs exclude HS6 `999999` before aggregation. Partner-only outputs include `999999` by default when product identity is summed away, but still exclude `partnerCode == 0`.

The headline Theil is zero-inclusive over a fixed eligible product universe:

`T_cft = sum_p s_cpft * log(s_cpft * K_f)`

where `s_cpft` is reporter `c`, product `p`, flow `f`, year `t` trade share, and `K_f` is the fixed flow-specific product universe size. Missing products are zero. Zero terms contribute zero; no epsilon is added.

Normalized Theil is:

`T_norm = T / log(K_f)`

Active/inactive product-margin decomposition:

`T_fixed = T_active + log(K_f / A_cft)`

where `A_cft` is the active positive product count. The first term is the intensive concentration among active products; the second term is the inactive or missing-product extensive margin.

The world-relative Theil is:

`W_cft = sum_p s_cpft * log(s_cpft / w_-c,pft)`

where `w_-c,pft` is the leave-one-out world product share. Higher values mean the country's product basket differs more from the broad world product basket.

## Universe And Sample

- reporting sample: `rd2_countries`
- benchmark universe source: `world_broad`; no `world_broad` country rows are reported as Theil outputs
- product identity: `harmonized_hs6_family`
- years: 2000-2024
- flows: exports and imports
- balanced reporting window: 2000-2024
- no silent fallback to `rd2_countries`, `prof_p_33`, or stale partial universes for global support

## Dynamic Memory And CPU Rules

- Reuse existing aggregate parquet files where possible.
- Avoid materializing full product-by-country-by-year-by-zero tables.
- Compute fixed-universe Theil from positive rows plus the fixed universe count.
- Process one flow at a time.
- Use pandas group iteration over already aggregated product rows rather than raw Comtrade leaf rows for the base panel.
- Keep worker defaults conservative. Heavy raw rebuilds should be separate checkpointed jobs.
- Write outputs only after validation passes.
- If product-destination aggregates are missing, record a blocker or staged follow-up rather than forcing a memory-heavy raw rebuild.

## Implementation Stages

1. Add reusable Theil helpers:
   - active Theil
   - fixed-universe Theil from positive values
   - normalized Theil
   - world-relative Theil
   - decomposition helper for product plus destination-within-product

2. Add unit tests:
   - equal positive values have active Theil zero
   - monopoly over `K` products equals `log(K)`
   - normalized monopoly equals one
   - zero rows do not require epsilons
   - invalid negative values are rejected
   - Theil decomposition identity holds

3. Build the base Theil panel:
   - read rd2 harmonized product export/import aggregates
   - read world_broad harmonized product export/import aggregates
   - define fixed product universes from positive world support over 2000-2024
   - compute fixed, normalized, active, active-normalized, and world-relative Theil
   - merge country metadata and balanced-panel flags

4. Write outputs:
   - processed parquet panel
   - all-years CSV
   - yearly summary CSV
   - latest ranking CSV
   - Japan/Korea versus rich-proxy summary CSV
   - diagnostics CSV
   - manifest JSON
   - markdown report

5. Validate:
   - both flows present
   - no duplicate reporter-year-flow keys
   - universe size constant within each flow
   - no `999999` product IDs
   - positive-total rows have nonmissing Theil
   - normalized fixed Theil lies in `[0, 1]`
   - active product counts and universe product counts are coherent

6. Follow-up ports after the base panel is stable:
   - product-destination Theil decomposition
   - partner Theil
   - Exercises 2, 3, 4, 6, 10, 11, and 12 using the Theil panel
   - separate `theil-repo` static site
   - adversarial econometrics/trust review before treating the outputs as final

## Expected Base Outputs

- `data/processed/samples/rd2_countries/fixed_universe_product_theil_panel.parquet`
- `results/samples/rd2_countries/fixed_universe_product_theil_tables/fixed_universe_product_theil_all_years.csv`
- `results/samples/rd2_countries/fixed_universe_product_theil_tables/fixed_universe_product_theil_yearly_summary.csv`
- `results/samples/rd2_countries/fixed_universe_product_theil_tables/fixed_universe_product_theil_latest_rankings.csv`
- `results/samples/rd2_countries/fixed_universe_product_theil_tables/fixed_universe_product_theil_rich_proxy_summary.csv`
- `results/samples/rd2_countries/fixed_universe_product_theil_tables/fixed_universe_product_theil_diagnostics.csv`
- `results/samples/rd2_countries/fixed_universe_product_theil_tables/fixed_universe_product_theil_manifest.json`
- `results/samples/rd2_countries/fixed_universe_product_theil_tables/fixed_universe_product_theil.md`

## Implemented Status

Completed on 2026-06-03:

- added Theil helpers to `scripts/concentration_metrics.py`
- added `scripts/run_fixed_universe_product_theil.py`
- added `tests/test_fixed_universe_product_theil.py`
- generated the base rd2 product-Theil panel and tables
- added `results/samples/rd2_countries/fixed_universe_product_theil_tables/adversarial_review.md`

Validation:

- targeted unit tests pass under `unittest`
- fixed-universe Product Gini tests still pass
- pipeline ran single-process using existing aggregate parquet files
- latest run elapsed time: about 12 seconds
- peak memory footprint: about 2.5 GB
- product-margin decomposition residual in generated panel: max absolute value about `4.4e-15`
