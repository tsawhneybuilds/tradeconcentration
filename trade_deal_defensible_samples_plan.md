# Defensible HS4 Samples Plan For Trade Deals And Export Concentration

## Summary

This is the binding sample decision for the trade-deal/export-concentration tariff work. Tariff exposure must be built at harmonized HS4 only. Do not build HS6 tariff exposures, do not assign H6 products to one H5 code, and do not use carry-forward or imputed WITS gaps in the headline specification.

Current row coverage from diagnostics:

- Strict exact-revision WITS reference, 2001-2021: 1,085 of 1,251 nonmissing export-baseline rows, or 86.7 percent.
- HS4 WITS candidate, 2001-2021 before tariff pulls: 1,162 of 1,251 nonmissing export-baseline rows, or 92.9 percent.
- WITS-unavailable rows in 2001-2021: 89 rows; HS4 harmonization cannot fix these.
- Strict exact-revision WITS reference relative to full nonmissing 1988-2025 panel: 1,085 of 1,911 rows, or 56.8 percent.

The first empirical contribution remains descriptive within-country panel evidence. Any causal claim requires a separate event-study or DiD design.

## Econometrically Defensible Samples

Preferred headline tariff sample:

```text
primary_wits_hs4_2001_2021
data/processed/samples/rd2_countries/primary_wits_hs4_2001_2021_sample.parquet
```

Rules:

- Use export-baseline rows with nonmissing `product_gini`.
- Keep years 2001-2021 only.
- Require `tariff_mapping_status == "ok"`.
- Exclude H6 revision years.
- Use `tariff_product_level == "HS4"` and `tariff_product_key == "harmonized_hs4"`.
- Require baseline export-value `hs4_bridge_trade_value_coverage >= 0.90` before tariff pulls.
- Require exporter-year `tariff_weight_coverage_i,t >= 0.80` after tariff pulls.

Long-window robustness sample:

```text
primary_wits_hs4_long
data/processed/samples/rd2_countries/primary_wits_hs4_long_sample.parquet
```

Rules:

- Same HS4-only gates as the headline sample.
- Keep all passing WITS-available non-H6 years, currently expected to be 1988-2021.
- Use as robustness, not as the headline tariff table.

Reference-only strict samples:

```text
primary_wits_2001_2021
primary_wits
```

These remain useful to show the cost of requiring exact HS revision overlap. They are no longer the preferred headline tariff samples.

Agreement-only sample:

```text
agreement_only_full
data/processed/samples/rd2_countries/agreement_only_full_sample.parquet
```

Use the full 1988-2025 export-baseline panel only for RTA timing and agreement-depth measures that do not require product-level tariffs.

Supplement candidate sample:

```text
supplement_candidate_gap_years
data/processed/samples/rd2_countries/supplement_candidate_gap_years.csv
```

Use WTO Tariff & Trade Data / ADB only as validation or robustness after overlap checks against WITS. Do not silently replace missing WITS years.

## HS4 Coverage Gates

HS4 harmonization gate:

```text
hs4_bridge_trade_value_coverage >= 0.90
```

Definition:

- Unit: fixed pre-period exporter product-partner export value.
- Baseline: earliest five available non-H6 export years per exporter.
- Denominator: positive product-partner export value after excluding HS6 `999999` and `partnerCode == 0`.
- Numerator: denominator value with a valid non-H6 HS6 code that maps into the local HS family crosswalk and can be aggregated to `harmonized_hs4`.

Tariff coverage gate:

```text
tariff_weight_coverage_i,t >= 0.80
```

Definition:

- Unit: exporter-year.
- Denominator: fixed pre-period exporter-destination-HS4 weights.
- Numerator: denominator weight with nonmissing tariff data after WITS tariff pulls.
- Report robustness thresholds at 0.90 and 0.95 if enough rows remain.

## Product-Code Policy

- Treat HS6 `999999` as "Commodities not specified", not as a product.
- Exclude `999999` before HS4 aggregation, tariff exposure construction, graphs, tables, regressions, checkpoints, and downloadable outputs.
- Preserve leading zeros when deriving `harmonized_hs4`; for example, HS6 `010121` becomes `HS4:0101`.
- Do not create tariff exposure outputs keyed by `cmd_code`, `hs6`, or `h6_cmd_code`.
- H6 years stay excluded unless a separate HS4 harmonization diagnostic clears them; current H6-to-H5 bridge evidence is not sufficient for the headline sample.

## Review Gate

No regression table is usable until:

- The HS4-only diagnostics pass.
- The tariff exposure construction reports coverage by exporter-year and baseline export weight.
- The sample, joins, HS4 aggregation, fixed effects, and clustering pass adversarial econometrics review.
- The paper labels the headline tariff result as descriptive unless a separate causal design is implemented and reviewed.
