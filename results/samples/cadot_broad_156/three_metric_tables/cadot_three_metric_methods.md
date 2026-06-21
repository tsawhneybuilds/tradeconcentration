# cadot_broad_156 Three-Metric Run

Generated: 2026-06-17T09:28:27+00:00

This run builds the selected reporter-sample three-metric bundle for Gini,
Theil, and HHI over annual UN Comtrade final-data files in 2000-2024.
For website-facing outputs, the required sample is `rd2_countries`. The
`cadot_broad_156` sample is retained only as a clearly labeled research
sensitivity. Product-dependent outputs convert source HS6 revision-code values
with LT/HGL weighted HS1992/H0 weights before product aggregation.

## Measures

- Gini: active-positive Gini over observed positive trade values.
- Theil headline: fixed-universe product Theil, `sum_p s_cpft * log(s_cpft * K_f)`, where `K_f` is the flow-specific 2000-2024 union of positive `world_broad` LT/HGL HS1992 product-family support.
- HHI headline: raw `sum_i s_i^2` on `[0,1]`.
- Product-dependent outputs exclude HS6 `999999` before LT/HGL conversion and aggregation.
- Partner-only concentration includes `999999` after product identity is summed away; partner `0` World is excluded by the raw leaf extractor.
- Harmonization: `lt_hgl_weighted_hs1992`, source DOI `10.7910/DVN/6AADMR`, version `2.1`, target `HS1992/H0`.

## Sample

- Selected reporters: 156
- Raw files processed: 3787
- Product identity: `harmonized_hs6_family`
- Fixed universe source: `world_broad`
- Product universes: `{"Exports": 5037, "Imports": 5037}`
- Complete balanced reporter-flow cells: 221

## Validation

| check                                             | passed   | details                                  |
|:--------------------------------------------------|:---------|:-----------------------------------------|
| selected_reporter_count_expected                  | True     |                                          |
| no_product_dependent_999999                       | True     | bad_product_ids=0                        |
| fixed_universe_hs1992_product_ids                 | True     | non_hs1992_product_ids=0                 |
| sample_products_inside_world_broad_fixed_universe | True     | active_products_outside_world_universe=0 |
| unique_reporter_year_flow_dimension_variant       | True     | duplicate_rows=0                         |
| hhi_bounds_0_1                                    | True     | bad_rows=0                               |
| fixed_theil_universe_counts_by_flow               | True     | {'Exports': 5037, 'Imports': 5037}       |
| theil_decomposition_residuals                     | True     | bad_rows=0                               |
| cross_metric_key_parity                           | True     | rows_with_missing_metric=0               |
| raw_files_present_for_available_country_years     | True     | missing_available_bulk_keys=0            |
| exercise_06_unique_keys                           | True     | duplicate_rows=0                         |
