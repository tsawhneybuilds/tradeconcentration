# Code Processing Contract

This document records the data-processing rules that canonical outputs in this repository must follow. It is meant to be read before interpreting tables, figures, panels, or website artifacts.

## HS6 `999999` Convention

HS6 code `999999` means "Commodities not specified"; it is not a real product category.

For product-level or product-dependent objects, exclude `999999` before aggregation, not only at the final table stage. This includes product concentration, product shares, product bins, leave-one-out product statistics, product regressions, top-product lists, product Lorenz curves, product transitions, product-partner-cell concentration, product-partner-cell transitions, and supplier-equalization calculations that rely on product identity. Keeping `999999` in those objects would create a false product identity.

For partner-only concentration, include `999999` by default. The final object being ranked is the partner, and the partner identity remains meaningful even when the product code is unspecified. Partner Ginis, partner top shares, and partner transition states therefore sum `999999` trade into reporter-partner totals unless an output is explicitly labeled as a no-`999999` sensitivity.

For mixed partner/product diagnostics, keep the two roles separate. Example: the import Partner-Gini counterfactual computes actual partner totals with `999999` included, but it does not equalize `999999` as a product; those unspecified-product partner cells are held fixed while identified HS6 products are equalized across observed suppliers.

Do not pool product and partner conventions silently. If one table contains both product and partner measures, document that product and product-partner-cell totals exclude `999999`, while partner totals include it.

## Leaf Trade Rows

Canonical leaf processing uses only positive trade values:

`trade_value > 0`

Rows flagged by Comtrade as aggregate rows are dropped:

`isAggregate == 0`

Clean canonical processing also excludes the World partner aggregate:

`partnerCode != 0`

`partnerCode == 0` is World. It is not a bilateral destination or supplier and must not enter canonical product, partner, product-partner-cell, concentration, transition, or panel outputs. Prof P-style world-partner inclusion may be used only as a diagnostic comparison and must be labeled as such.

## Concentration Measures

Concentration measures are active-positive measures. The unit is the active product, partner, or product-partner cell with positive trade value within a reporter-year-flow.

For top shares:

`top_share_N = sum(value_i for i in top N active items) / sum(value_i for all active items)`

For percentage cutoffs:

`cutoff = max(1, ceil(active_item_count * pct))`

Higher top shares mean more trade value is concentrated in the largest active items. Zeros are not included as a universe of possible but inactive items.

## Exercise 12 Samples

The website headline Exercise 12 is the Evenett-Venables-style HS4 persistent expansion decomposition. It is generated for `rd2_countries` only:

`OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 /usr/bin/nice -n 8 /opt/anaconda3/bin/python scripts/run_exercise_12_ev_hs4_expansion.py --country-sample rd2_countries --horizons 5 10`

This table is descriptive growth accounting, not a causal estimate. The unit is reporter country by base window by future window by HS4 product. Base windows use adjacent years `{t, t+1}` and future windows use adjacent years `{t+h, t+h+1}`. The website headline uses `h = 5`; `h = 10` is a robustness horizon.

Values are deflated to constant 2024 USD before thresholding. An HS4 product is base-active only if annual exports are at least `$50,000` in both base years, and future-active only if annual exports are at least `$50,000` in both future years. Product channels are mutually exclusive:

- `new_product`: not base-active and future-active.
- `continuing_product`: base-active and future-active.
- `dying_product`: base-active and not future-active.
- `below_threshold_residual`: not active in either window, retained for accounting diagnostics.

The headline contribution is positive expansion:

`positive_expansion_i = max(future_two_year_avg_i - base_two_year_avg_i, 0)`

The headline share is:

`positive_expansion_share_i = positive_expansion_i / sum_j positive_expansion_j`

This is the preferred "where did expansion come from" denominator because it is not inflated by offsetting contractions. The companion net-growth share is:

`net_growth_share_i = (future_two_year_avg_i - base_two_year_avg_i) / sum_j (future_two_year_avg_j - base_two_year_avg_j)`

Net-growth shares must be labeled as net accounting. They can exceed 100 percent or be negative when contractions offset expansions.

The runner also writes a product-specific partner-spread panel for continuing HS4 products only:

- `same_product_partner`
- `new_product_partner`
- `lost_product_partner`
- `below_threshold_partner_residual`

Partner-spread shares should be read with the within-continuing-HS4 denominator, because product-partner gross expansion can exceed product-level gross expansion when partners churn inside a continuing product.

The runner also writes a combined HS4-by-partner cell decomposition with two alternative panels. Both use the same cell-level base/future values, product statuses, positive-expansion denominator, and net-growth companion accounting. They differ only in what "new partner" means:

- Product-first panel (`combined_product_first`): first separates `net_new_product`, then splits continuing HS4 products by product-specific HS4-by-partner status. Here, "new partner" means a new product-specific partner relationship for that HS4 product.
- Partner-first panel (`combined_partner_first`): first uses reporter-partner totals across all HS4 products, then splits active reporter partners by HS4 product status. Here, "new partner" means the reporter did not persistently export to that partner at all in the base window.

These two panels are alternative partitions of the same cell-level accounting and must not be added together. Use them to answer different questions:

- Product-first: how much expansion came from net-new products versus continuing products reaching new product-specific partners?
- Partner-first: how much expansion came from new reporter partners versus existing reporter partners carrying new products?

The Kehoe-Ruhl-style robustness table labels the bottom 10 percent of base-window export value as `bottom_10pct_low_base_growth`. These products are low-base products, not strict new products. Do not describe them as "new products."

The fine-grained harmonized-HS6 appendix uses the same EV-style two-year windows, constant-2024-dollar threshold, and pooled positive-expansion denominator, but changes the product identity to official LT/HGL weighted HS6 conversion to HS1992/H0:

`OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 /usr/bin/nice -n 8 /opt/anaconda3/bin/python scripts/run_exercise_12_ev_hs6_harmonized_expansion.py --country-sample rd2_countries --horizons 5 10`

It writes distinct outputs under:

`results/samples/rd2_countries/exercise_12_ev_hs6_harmonized_expansion_tables/`

This appendix cites Lukaszuk and Torun (2022), "Harmonizing the Harmonized System", and uses the official Harvard Growth Lab / Dataverse weighted classification conversion tables, DOI `10.7910/DVN/6AADMR`, version `2.1`. The pipeline composes adjacent HS tables back to HS1992/H0, multiplies trade value by the conversion weight, and aggregates before decomposition. Report the LT/HGL source coverage share, missing-weight value share, and conversion value residual whenever interpreting HS6 entry results.

Main EV-style HS4 outputs:

- `results/samples/rd2_countries/exercise_12_ev_hs4_expansion_tables/ev_hs4_country_window_decomposition.csv`
- `results/samples/rd2_countries/exercise_12_ev_hs4_expansion_tables/ev_hs4_partner_spread_country_window.csv`
- `results/samples/rd2_countries/exercise_12_ev_hs4_expansion_tables/ev_hs4_combined_country_window_decomposition.csv`
- `results/samples/rd2_countries/exercise_12_ev_hs4_expansion_tables/ev_hs4_combined_pooled_summary.csv`
- `results/samples/rd2_countries/exercise_12_ev_hs4_expansion_tables/ev_hs4_combined_equal_country_summary.csv`
- `results/samples/rd2_countries/exercise_12_ev_hs4_expansion_tables/ev_hs4_combined_latest_5y_country.csv`
- `results/samples/rd2_countries/exercise_12_ev_hs4_expansion_tables/ev_hs4_pooled_summary.csv`
- `results/samples/rd2_countries/exercise_12_ev_hs4_expansion_tables/ev_hs4_equal_country_summary.csv`
- `results/samples/rd2_countries/exercise_12_ev_hs4_expansion_tables/ev_hs4_latest_5y_country.csv`
- `results/samples/rd2_countries/exercise_12_ev_hs4_expansion_tables/ev_hs4_bottom10_robustness.csv`
- `results/samples/rd2_countries/exercise_12_ev_hs4_expansion_tables/ev_hs4_bottom10_robustness_summary.csv`
- `results/samples/rd2_countries/exercise_12_ev_hs4_expansion_tables/ev_hs4_validation.json`
- `results/samples/rd2_countries/run_manifest_exercise_12_ev_hs4_expansion.json`

The older rolling top-item and HS6-family churn tables are generated from the combined Exercise 2+12 checkpoint runner:

`python3 scripts/run_exercises_02_12.py --finalize-only --workers 4 --country-sample rd2_countries`

For memory-constrained continuation from the already-built Exercise 12 aggregate, the runner can finalize with:

`python3 scripts/run_exercises_02_12.py --finalize-only --workers 1 --country-sample rd2_countries --exercise-12-only --reuse-exercise-12-aggregate`

`--resume-exercise-12-spill` is only a crash-recovery option for interrupted finalization. Resume spill files must carry a matching spill manifest with the aggregate fingerprint, item-mode/top-definition specification, script hashes, sample, and exclusion rules. Unmanifested or mismatched spill files must be rebuilt rather than reused.

The canonical older top-item/churn sample is:

- Product rows: `item_id_mode == "hs6_harmonized_family"` and `top_definition == "top_10"`
- Product-partner-cell rows: `item_id_mode == "hs6_harmonized_family"` and `top_definition == "top_10"`
- Partner rows: `item_id_mode == "partner"` and `top_definition == "top_10"`

The full net and gross CSV files keep robustness rows for `hs6_revision`, `hs4`, `hs2`, `cpa`, `top_1pct`, and `top_5pct`. Memo tables must not pool these robustness definitions into unlabeled rows.

The older top-item/churn output distinguishes strict entrants from low-base growers. Categories are mutually exclusive and ordered so the decomposition still sums:

- `existing_top_<definition>`: the item has positive base-year exports and is already in the base-year top set for the active top definition.
- `strict_new_item`: the item has `base_value == 0` and `future_value > 0`.
- `low_base_under_10k_grower`: the item is not a base-year top item, has `0 < base_value < 10,000` current USD, and has `future_value > base_value`.
- `least_traded_10pct_grower`: the item is not classified above, is not a base-year top item, belongs to the least-traded base-year basket accounting for the bottom 10 percent of base exports, and has `future_value > base_value`.
- `existing_non_<definition>`: all other positive-base non-top items.

The least-traded 10 percent basket follows the Kehoe-Ruhl style small-base margin. It is formed within each reporter-year by ranking positive-base items from smallest to largest and selecting items while cumulative base exports before the item are below 10 percent of total base exports. The threshold-crossing item is included so every positive-base reporter-year has a nonempty least-traded basket. `strict_new_item` remains separate because absent-base products are not positive-base items.

The Exercise 12 extensive-margin add-on is generated from the existing rd2 export aggregate:

`OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 /usr/bin/nice -n 8 /opt/anaconda3/bin/python scripts/run_exercise_12_extensive_margin.py --country-sample rd2_countries --identity-modes hs6_harmonized_family hs4 hs2 --horizons 5 10`

This add-on decomposes reporter-country export growth across product-partner cells. The main mutually exclusive hierarchy is:

1. `net_new_product`: future cells whose product identity was absent in the base year.
2. `net_new_partner_existing_product`: future cells whose product existed but partner was absent in the base year.
3. `new_product_partner_cell_existing_product_partner`: future cells absent in the base year where both product and partner existed somewhere in the base year.
4. Existing product-partner cells split into growth, contraction, and no-change categories.

Use gross-positive shares for the cleanest "where expansion came from" reading. Net-growth shares are also output, but they can exceed 100 percent or become negative when contractions offset expansions. The add-on also writes non-exclusive overlap diagnostics and the strict-zero, under-$10,000, and bottom-10-percent product-entry robustness checks.

Main outputs:

- `results/samples/rd2_countries/exercise_12_extensive_margin_tables/extensive_margin_country_year.csv`
- `results/samples/rd2_countries/exercise_12_extensive_margin_tables/extensive_margin_latest.csv`
- `results/samples/rd2_countries/exercise_12_extensive_margin_tables/extensive_margin_summary.csv`
- `results/samples/rd2_countries/exercise_12_extensive_margin_tables/extensive_margin_country_weighted_summary.csv`
- `results/samples/rd2_countries/exercise_12_extensive_margin_tables/extensive_margin_overlapping_robustness.csv`
- `results/samples/rd2_countries/exercise_12_extensive_margin_tables/extensive_margin_product_entry_robustness.csv`
- `results/samples/rd2_countries/exercise_12_extensive_margin.md`

The validation audit for the extensive-margin add-on is:

`results/samples/rd2_countries/exercise_12_extensive_margin_tables/extensive_margin_validation.json`

The run manifest, source hash, row counts, and measure definitions are:

`results/samples/rd2_countries/run_manifest_exercise_12_extensive_margin.json`

These files record rd2 sample checks, duplicate-key checks, category accounting residuals, partnerCode 0 scans, product-dependent `999999` scans, harmonized-HS6 lookup coverage, and whether the output is safe for website generation. The separate canonical Exercise 12 validation audit for the older top-item transition outputs remains `results/exercise_12_tables/exercise_12_validation_audit.json`.

## LT/HGL HS6 Harmonization

Exercise 12 product and product-partner-cell headline identities use `hs6_harmonized_family`, now interpreted as LT/HGL weighted conversion to HS1992/H0.

Construction:

1. Download/import the official Harvard Growth Lab / Dataverse weighted adjacent HS conversion CSVs, DOI `10.7910/DVN/6AADMR`, version `2.1`.
2. Validate file checksums and source-code weight sums; normalize positive outgoing weights where official rounded weights do not sum exactly to one.
3. Fill documented unchanged-code identity links where official adjacent files omit them.
4. Compose adjacent chains from H1-H6 back to H0/HS1992.
5. For product-dependent outputs, exclude HS6 `999999` before conversion, multiply trade value by the LT/HGL weight, aggregate to target HS1992 `cmd_code`, and then run the decomposition or Gini logic.
6. Treat missing LT/HGL source-code coverage as a blocker rather than falling back to WCO connected-component families.

Trade value is split across HS1992 targets only through official conversion weights. Validation gates require value conservation after excluding `999999`.

The old WCO connected-component family map is legacy sensitivity material only; it is no longer the website-facing `hs6_harmonized_family` default.

Diagnostics are written to:

`results/exercise_12_tables/hs_harmonization_diagnostics.csv`

The old same-revision exclusion diagnostic remains in:

`results/exercise_12_tables/hs_revision_pair_diagnostics.csv`

That old diagnostic reports value excluded when `hs6_revision` requires the same HS revision in the base and future year. It is a dimension-horizon diagnostic, not a unique trade-value total.

## Partner Regions

Partner-region metadata uses World Bank country metadata only.

Comtrade partner ISO3 codes are matched to World Bank ISO3 country records. If the ISO3 is not a World Bank country record, the partner region remains:

`Unknown`

There is no fallback regional taxonomy. Outputs include source/reliability fields:

- `partner_region_source == "world_bank"` for World Bank matches
- `partner_region_source == "unknown_no_world_bank_match"` for non-WB partners, aggregates, territories, or missing codes
- `partner_region_reliability == "world_bank_country_region"` or `unknown`

Product destination/region states report `unknown_partner_region_share`, `world_bank_partner_region_share`, and `region_transition_reliability`. Region claims should be discounted when the unknown share is high.

## Net And Gross Denominators

Exercise 12 net decomposition uses signed future-minus-base growth:

`net_contribution_i = future_value_i - base_value_i`

The net contribution share denominator is total signed growth for the reporter-year-horizon sample.

Gross positive growth and gross contraction are separate accounting totals:

`gross_positive_i = max(future_value_i - base_value_i, 0)`

`gross_contraction_i = max(base_value_i - future_value_i, 0)`

Gross positive shares use the total gross positive denominator. Gross contraction shares use the total gross contraction denominator. They are not directly comparable to net shares unless the accounting type and denominator are stated.

## Transition Zeros

Exercise 12 creates zero-filled base/future values only within the observed active item universe for a valid reporter-year pair. This lets the code label an observed active item as new, exiting, existing, growing, or shrinking.

These zeros are not a full universe of all possible HS6 products, partners, or product-partner cells. They must not be interpreted as evidence that every unobserved possible item had true zero trade.

## Website Artifacts

Website-facing generation and validation must use `rd2_countries` unless the user explicitly asks otherwise. If `rd2_countries` inputs are incomplete, stop with a clear blocker instead of silently falling back to `prof_p_33`, `world_broad`, stale outputs, or partial samples.

H2.4 world supplier specialization may remain a global benchmark, but it must be labeled as global and not as limited to `rd2_countries`.
