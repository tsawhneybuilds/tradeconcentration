# Trade Deals And Export Concentration Implementation Plan

## Summary

This plan turns the trade-deal idea into an auditable empirical build spec for the `rd2_countries` export concentration panel. The first pass should be treated as descriptive panel evidence: it asks whether broader or cheaper foreign market access is associated with export concentration within reporter countries over time. Causal claims require a separate event-study or DiD design with pre-trends, placebo leads, and staggered-treatment safeguards.

Primary empirical question:

> Within `rd2_countries`, are lower foreign tariffs, broader agreement coverage, or deeper trade agreements associated with changes in export product concentration?

Primary outcome:

`product_gini` for exports from `data/processed/samples/rd2_countries/concentration_all_years.parquet`.

Default estimand:

```text
beta is the within-reporter-country association between lagged fixed-weight foreign market-access exposure and export product concentration, net of reporter and calendar-year fixed effects, for rd2_countries export observations.
```

No regression table should be treated as usable until diagnostics-only outputs and an adversarial econometrics review are complete.

Referee-calibrated sample decision:

- The headline tariff analysis must use the HS4-only `primary_wits_hs4_2001_2021` sample documented in `trade_deal_defensible_samples_plan.md`.
- The broader `primary_wits_hs4_long` sample is a long-window tariff robustness sample, not the headline tariff table.
- Missing WITS reporter-years and H6-to-H5 ambiguity must not be solved by carry-forward, silent imputation, arbitrary one-code concordance, or HS6-level tariff exposure.
- Agreement timing/depth analysis may use the full export-baseline country-year sample because it does not require product-level tariffs.
- WTO Tariff & Trade Data / ADB can supplement WITS gaps only as robustness after overlap validation against WITS in common years.

## Analysis Sample

Use only:

```text
data/processed/samples/rd2_countries/concentration_all_years.parquet
flow == "Exports"
variant == "baseline"
```

Expected concentration-panel invariants from the current local file:

- 60 reporter countries.
- Years 1988-2025.
- 1,920 export-baseline country-year rows.
- No duplicate `iso3-reporter_code-year` keys after filtering to export-baseline rows.
- 9 missing `product_gini` rows, all for United Arab Emirates (`ARE`, reporter code 784) in 2000-2004, 2006, and 2009-2011.

Implementation rule:

- Do not fall back to `prof_p_33`, `world_broad`, root-level legacy files, stale outputs, or partial samples.
- Keep the missing-UAE rows in sample diagnostics, but exclude rows with missing primary outcomes from primary regressions only after reporting attrition.
- Use `rd2_countries` for any future website-facing artifact unless explicitly instructed otherwise.

Referee-calibrated analysis samples:

- `primary_wits_hs4_2001_2021`: preferred headline tariff sample. Export-baseline rows with nonmissing `product_gini`, years 2001-2021, `tariff_mapping_status == "ok"`, non-H6 local revision, HS4 baseline export-value coverage passing 0.90, and no HS6-level tariff exposure.
- `primary_wits_hs4_long`: long-window tariff robustness sample. Same HS4-only gates as `primary_wits_hs4_2001_2021`, but keep all passing WITS-available non-H6 years, currently 1988-2021.
- `primary_wits_2001_2021` and `primary_wits`: strict exact-revision reference samples, no longer the preferred headline tariff samples.
- `agreement_only_full`: all 1,920 export-baseline rows for RTA/depth measures that do not require product-level tariffs.
- `supplemented_tariff`: WITS plus WTO/ADB-covered missing reporter-years, allowed only after overlap validation and reported as robustness rather than the headline result.

## Data Sources

### Agreement Timing

Use the [Mario Larch Regional Trade Agreements Database](https://www.ewf.uni-bayreuth.de/en/research/RTA-data/index.html) as the default agreement timing source.

Use it to construct bilateral exporter-destination-year variables:

- `rta_active`
- `fta_active`
- `cu_active`
- `psa_active`
- `eia_active`
- first-entry year and event-time indicators

Expected raw unit:

`country1-country2-year` or equivalent directed/undirected dyad-year record.

### Agreement Depth

Use [DESTA v2.3](https://www.designoftradeagreements.org/downloads/) as the default agreement-depth source.

Use treaty or dyadic treaty fields such as:

- `depth_index`
- `depth_rasch`
- `full_fta`
- `standards`
- `investments`
- `services`
- `procurement`
- `competition`
- `iprs`
- enforcement and dispute-settlement measures

Collapse to dyad-year before merging onto exporter-destination-year data.

### Deep-Provision Robustness

Use the [World Bank Deep Trade Agreements Database 2.0](https://datatopics.worldbank.org/dta/table.html) as a robustness and mechanism source.

Use it to test whether broad regulatory, services, investment, procurement, competition, intellectual-property, or dispute-settlement provisions matter beyond tariff access.

### Annual Tariffs

Use [WITS UNCTAD TRAINS](https://wits.worldbank.org/witsapiintro.aspx?lang=en) as the main annual tariff source, aggregated to harmonized HS4 before exposure construction.

Primary tariff pull:

- importer/destination `j`
- exporter/beneficiary `i`
- harmonized HS4 product family `h`
- year `t`
- AVE-estimated tariff rates where available

Robustness tariff pull:

- reported tariff rates using the same importer-exporter-HS4-year keys after documented HS4 aggregation.

Capture at least these WITS fields when available:

- tariff type
- observed tariff value
- nomenclature code
- product code
- importer/reporter code
- exporter/partner code
- year
- number of preferential lines
- number of MFN lines
- number of unavailable lines
- excluded or suppressed observations

### Official Tariff Supplement

Add [WTO Tariff & Trade Data](https://ttd.wto.org/en/download) / Analytical Database downloads as official tariff validation or supplement data.

Use this source to validate WITS tariff coverage, preferential-tariff availability, and official tariff-line metadata. Do not replace WITS as the default annual tariff source unless WITS coverage is demonstrably inadequate and the WTO source can be accessed reproducibly under its terms.

### Sparse-Year Tariff Robustness

Use [CEPII MAcMap-HS6](https://www.cepii.fr/CEPII/en/bdd_modele/bdd_modele_item.asp?id=12) as harmonized sparse-year robustness.

Use only for years it actually covers. Do not interpolate MAcMap tariffs into missing years for primary regressions.

### Official RTA Validation

Use the [WTO RTA database](https://data.wto.org/dataset/ext_rta) to validate agreement names, parties, notification status, and entry dates. It is a validation source, not the main regression-ready pair-year backbone.

## Source Retrieval And Provenance

Before building any panel, create raw snapshots and provenance manifests. Planned raw locations:

```text
data/raw/trade_agreements/larch_rta/
data/raw/trade_agreements/desta/
data/raw/trade_agreements/world_bank_dta/
data/raw/tariffs/wits_trains/
data/raw/tariffs/wto_ttd/
data/raw/tariffs/macmap_hs6/
```

Each raw source manifest must record:

- source name and URL
- retrieval date and time
- file names and file hashes
- source version or vintage
- license or terms-of-use note
- API endpoint or download page
- query parameters
- row counts
- column names
- country-code scheme
- product-code scheme and HS revision/nomenclature

WITS preflight must run before product-level tariff pulls:

- reporter/importer availability by year
- partner/exporter availability by year
- product nomenclature availability
- HS4 product availability after aggregation
- tariff type availability
- missingness by importer-exporter-year

Build and save a country-code crosswalk covering:

- Comtrade reporter code
- ISO3
- reporter country name
- Larch country code/name
- DESTA country code/name
- World Bank DTA country code/name
- WITS reporter/partner code/name
- WTO economy label
- CEPII code/name, if needed

Block implementation if any `rd2_countries` reporter lacks a stable identifier in the source needed for the primary exposure.

WTO/ADB supplement rule:

- Pull only the WITS-gap reporter-years first.
- Validate WTO/ADB against WITS on overlapping reporter-year-product cells before any supplemented sample is used.
- Report source units, HS revision, product code, tariff type, match rate, and mean/median absolute tariff differences.
- Treat supplemented results as robustness only.

## Unit Of Observation And Data Flow

Primary concentration panel:

`exporter country-year`.

Underlying market-access construction panel:

`exporter-destination-harmonized-HS4-year`.

Direction matters:

```text
Repo export row:
  exporter/reporter = i
  destination/partner = j
  harmonized HS4 family = h

Tariff row:
  importer/reporter = j
  exporter/partner or beneficiary = i
  harmonized HS4 family = h
```

Data flow:

1. Load export-baseline concentration outcomes from the `rd2_countries` concentration file.
2. Load underlying Comtrade exporter-destination-product export values for the same reporter-year universe.
3. Exclude `partnerCode == 0` and non-positive trade values from bilateral/product construction.
4. Exclude HS6 `999999` before HS4 aggregation or any product-level market-access, tariff, product-share, or product-destination construction.
5. Aggregate products to `harmonized_hs4` and build fixed pre-period exporter-destination-HS4 weights from underlying Comtrade data.
6. Build agreement timing by exporter-destination-year from Larch.
7. Attach depth by exporter-destination-year from DESTA, using explicit dyad-year collapse rules.
8. Attach annual tariffs by importer-exporter-HS4-year from WITS after documented HS4 aggregation.
9. Aggregate market-access exposures to exporter-year using fixed pre-period weights.
10. Merge exporter-year exposures onto concentration outcomes by `iso3`, `reporter_code`, and `year`.
11. Write diagnostics-only outputs before estimating any regression.

## Market-Access Measures

### Weights

Use fixed pre-period export weights as the primary weights. Lagged export weights are robustness only.

Let:

```text
x_i,j,h,0 = exporter i's pre-period exports to destination j in harmonized HS4 family h
w_i,j,h,0 = x_i,j,h,0 / sum_j,h x_i,j,h,0
w_i,j,0 = sum_h w_i,j,h,0
```

Default pre-period:

- Use the earliest five available non-H6 export years for each exporter with valid destination-HS4 data.
- Require at least three valid years for exporter-specific baseline weights.
- If an exporter has fewer than three valid pre-period years, flag it and exclude it from primary tariff exposure regressions unless a documented fallback is explicitly added.

Weights must be computed from underlying Comtrade exporter-destination-product records after HS4 aggregation, not from the country-year concentration panel alone.

### Agreement Coverage

```text
rta_partner_share_i,t = sum_j w_i,j,0 * 1{RTA_i,j,t active}
```

Plain English:

`rta_partner_share` is the share of exporter `i`'s fixed baseline destination exposure covered by any active RTA in year `t`.

Denominator:

All baseline destinations with positive baseline export weight.

### Agreement Depth

```text
rta_depth_weighted_i,t = sum_j w_i,j,0 * depth_i,j,t
```

Plain English:

`rta_depth_weighted` is the baseline destination-weighted depth of exporter `i`'s active agreements in year `t`.

Dyad-year depth rule:

- If no active agreement exists, set depth to 0.
- If exactly one active agreement exists, use that agreement's depth.
- If multiple active agreements overlap for the same exporter-destination-year, use the maximum depth as the primary rule and report mean-depth and latest-entry-depth as robustness.

### Average Foreign Tariff

```text
market_access_tariff_avg_i,t = sum_j,h w_i,j,h,0 * tariff_j,i,h,t
```

Plain English:

`market_access_tariff_avg` is the fixed-basket average tariff that exporter `i` faces abroad in year `t`.

Unit:

Percentage points. Preserve raw source units in raw data and convert consistently in processed data.

### Preference Margin

```text
preference_margin_avg_i,t = sum_j,h w_i,j,h,0 * (MFN_j,h,t - preferential_j,i,h,t)
```

Plain English:

`preference_margin_avg` is the fixed-basket average tariff advantage exporter `i` receives relative to MFN rates.

Positive values mean the exporter faces lower tariffs than the MFN benchmark.

### Duty-Free Market Share

```text
duty_free_market_share_i,t = sum_j,h w_i,j,h,0 * 1{tariff_j,i,h,t == 0}
```

Plain English:

`duty_free_market_share` is the fixed-basket share of exporter `i`'s baseline market-access cells that are duty free in year `t`.

### Tariff Coverage

For each exporter-year exposure, report:

```text
tariff_weight_coverage_i,t = sum_j,h w_i,j,h,0 * 1{tariff_j,i,h,t nonmissing}
```

Primary tariff exposure rule:

- Use only exporter-years with at least 0.80 baseline-weight tariff coverage.
- Keep exporter-years below 0.80 in diagnostics.
- Do not silently impute missing tariffs in the primary specification.
- Robustness may impute missing preferential tariffs with MFN only when the source metadata supports that interpretation.
- Carry-forward tariffs are not allowed in the primary specification.
- H6-to-H5 one-code assignment and HS6-level tariff exposure are not allowed in the primary specification.
- H6 years remain excluded unless a separate HS4 harmonization diagnostic clears them.

## Merge Contracts

No silent inner joins are allowed.

Before every merge, write diagnostics for:

- left row count
- right row count
- expected key
- duplicate keys on both sides
- expected cardinality
- matched row count
- unmatched-left row count
- unmatched-right row count, where relevant
- unmatched examples
- post-merge row count

Expected joins:

- Country-code crosswalk to concentration panel: many-to-one on `iso3` or `reporter_code`.
- Larch dyad-year to exporter-destination-year skeleton: many-to-one after Larch is collapsed to one record per exporter-destination-year.
- DESTA/DTA treaty-depth to dyad-year skeleton: many-to-one only after explicit dyad-year collapse.
- WITS tariff to exporter-destination-HS4-year skeleton: many-to-one only after tariff records are collapsed to one tariff per importer-exporter-harmonized-HS4-year-tariff-type.
- Exporter-year exposure panel to concentration panel: one-to-one or many-to-one from concentration rows to exporter-year exposure, with no duplicate `iso3-reporter_code-year` exposure keys.

Agreement overlap rule:

- Retain raw agreement records.
- Create a collapsed dyad-year table with one row per unordered dyad-year and active-agreement indicators.
- For depth, primary collapse uses maximum depth among active agreements; robustness stores mean depth, count of active agreements, and latest-entry agreement depth.

## HS4 And Tariff Policy

Product-code rules:

- Preserve leading zeros when deriving `harmonized_hs4`; for example, HS6 `010121` becomes `HS4:0101`.
- Store HS4 tariff keys as `harmonized_hs4`.
- Exclude HS6 `999999` before product-level tariff, market-access, product-share, product-destination, or exporter-destination-HS4 aggregation.
- Continue to exclude `partnerCode == 0` World aggregates from bilateral market-access construction.

HS revision/concordance rule:

- Product-level tariff analysis is blocked until the Comtrade HS code, tariff source HS code, and year-specific nomenclature are explicitly reconciled.
- Use harmonized HS4 as the only tariff product level.
- Do not create HS6-keyed tariff exposure outputs.
- Require `hs4_bridge_trade_value_coverage >= 0.90`, measured by fixed pre-period baseline export value, before using the HS4 tariff sample.
- H6 years remain excluded unless a separate HS4 harmonization diagnostic clears them.

Coverage rule:

- Report tariff-source coverage by exporter-year, destination-year, product-year, and baseline export weight.
- Block primary tariff regressions if source coverage falls below the pre-specified threshold for too many country-years to support inference.

## Empirical Design

Primary descriptive model:

```text
Y_i,t = beta * MarketAccess_i,t-1 + alpha_i + gamma_t + epsilon_i,t
```

Where:

- `Y_i,t` is export `product_gini` for reporter `i` in year `t`.
- `MarketAccess_i,t-1` is one lag of a fixed-weight market-access measure.
- `alpha_i` are reporter fixed effects.
- `gamma_t` are calendar-year fixed effects.

Primary market-access measures:

- `market_access_tariff_avg`
- `preference_margin_avg`
- `duty_free_market_share`
- `rta_partner_share`
- `rta_depth_weighted`

Secondary outcomes:

- `product_top_1pct_share`
- `product_top_5pct_share`
- `product_active_count`
- `partner_gini`
- `product_partner_cell_gini`

Baseline controls:

- No post-treatment controls in the main descriptive fixed-effects specification.

Robustness controls:

- `log_population`
- one size/income control at a time, not `log_gdp_current_usd`, `log_gdp_per_capita`, and `log_population` together
- primary export share controls only as robustness, because they may be mediators rather than confounders

Inference:

- Default: reporter-country clustered standard errors.
- Robustness: reporter and calendar-year two-way clustering where feasible.
- If cluster counts or treatment timing are thin, report small-cluster caveats and consider wild-cluster bootstrap.

Interpretation:

- Treat coefficients as conditional within-country associations.
- Do not say trade deals caused concentration to rise or fall unless a separate causal design clears the required diagnostics.

## Causal Upgrade Requirements

A causal event-study or DiD extension must be a separate design. It must define:

- treatment event, such as first major RTA entry or large tariff-preference change
- comparison group
- event-time window
- never-treated or not-yet-treated handling
- staggered-treatment estimator
- lead and lag structure
- pre-trend tests
- placebo leads
- leave-one-agreement robustness
- leave-one-destination and leave-one-region robustness
- sensitivity to endogenous agreement timing

No causal language is allowed unless these design choices and diagnostics are explicitly satisfied.

## Diagnostics And Test Plan

The first implementation should produce diagnostics-only artifacts before any regression table.

Required diagnostics:

- row counts after every filter, merge, reshape, aggregation, and `dropna`
- unique reporter counts, year counts, dyad counts, destination counts, product counts, and exporter-year counts
- duplicate-key checks before every merge
- merge match rates and unmatched examples
- missingness before and after cleaning
- tariff coverage by exporter-year and baseline export weight
- distribution of each exposure before and after coverage restrictions
- final regression-sample attrition from the 1,920 export-baseline rows
- list of omitted reporter-years and reasons
- fixed-effect counts
- cluster counts and cluster-size distribution
- singleton drops, if any estimator drops them

Required sample checks:

- `rd2_countries` only.
- No fallback to `prof_p_33` or `world_broad`.
- No HS6 `999999` in product-level market-access inputs before HS4 aggregation.
- No `partnerCode == 0` in bilateral market-access inputs.
- No HS6-keyed tariff exposure outputs; final tariff product key must be `harmonized_hs4`.
- `iso3-reporter_code-year` remains unique in the final exporter-year exposure panel.

Required robustness checks:

- Larch agreement timing only.
- DESTA depth-weighted agreement exposure.
- WITS annual tariff exposure.
- WITS reported tariff robustness.
- WTO tariff validation or supplement check.
- CEPII MAcMap sparse-year robustness, aggregated to HS4 before use.
- Fixed pre-period weights versus lagged weights.
- Leave-one-destination, leave-one-agreement, and leave-one-region robustness.

Adversarial-review gate:

- After diagnostics and before treating results as usable, run an adversarial econometrics review.
- Give the reviewer raw files, source manifests, changed scripts, commands, logs, diagnostics, tables, and intended specification.
- Do not present coefficient tables as trusted until the review clears them or lists remaining caveats.

## Planned Outputs

Processed outputs:

```text
data/processed/samples/rd2_countries/primary_wits_tariff_sample.parquet
data/processed/samples/rd2_countries/primary_wits_2001_2021_sample.parquet
data/processed/samples/rd2_countries/primary_wits_hs4_2001_2021_sample.parquet
data/processed/samples/rd2_countries/primary_wits_hs4_long_sample.parquet
data/processed/samples/rd2_countries/agreement_only_full_sample.parquet
data/processed/samples/rd2_countries/supplement_candidate_gap_years.csv
data/processed/samples/rd2_countries/trade_deal_hs4_baseline_harmonization_coverage.csv
data/processed/samples/rd2_countries/trade_deal_market_access_panel.parquet
data/processed/samples/rd2_countries/trade_deal_market_access_diagnostics.json
data/processed/samples/rd2_countries/trade_deal_country_code_crosswalk.csv
```

Results outputs:

```text
results/samples/rd2_countries/trade_deal_market_access/
results/samples/rd2_countries/trade_deal_market_access/diagnostics.md
results/samples/rd2_countries/trade_deal_market_access/source_manifest.json
results/samples/rd2_countries/trade_deal_market_access/tariff_sample_attrition.md
```

Regression outputs should be added only after diagnostics pass.

## Assumptions

- This plan is a document/spec update only; it does not perform data pulls or regressions.
- `rd2_countries` is the only default sample.
- WITS TRAINS is the default annual tariff source.
- WTO Tariff & Trade Data/ADB is a validation or supplement source, not a default replacement.
- CEPII MAcMap is sparse-year robustness only and must be aggregated to HS4 before use.
- Carry-forward tariffs are not allowed in the primary specification.
- Fixed pre-period export weights are primary; lagged weights are robustness.
- Primary results are descriptive unless a later causal design is explicitly implemented and reviewed.
