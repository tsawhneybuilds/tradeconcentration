# H2.4 Supplier Specialization Benchmark

Generated: 2026-05-24T10:32:05+00:00

Scope: this is a global H24 world-product-market benchmark. It is not limited to the rd2_countries website sample.

HS6 `999999` is excluded before tables, figures, and manifests are written.

## Measures

`top_supplier_share` is the largest country-coded supplier's share of global imports for an HS6 product-year.

`dominant_specialized` means the top supplier has revealed comparative advantage above 1 for that HS6 product. This is an RCA-specialization flag and does not require a 75% top-supplier share.

`strict_dominant_specialized` means `dominant_specialized` is true and the top supplier share is at least 75%. Higher values indicate a product market where one specialized source country dominates global observed imports.

## Latest-Year Summary

- Latest year: 2024
- Product markets: 5,929
- Median top-supplier share: 0.324
- Share of products with top supplier >= 75%: 0.058
- Import-value share with top supplier >= 75%: 0.010
- Share strict dominant specialized: 0.028
- Import-value share strict dominant specialized: 0.009

## Output Files

- `results/h24_supplier_specialization_tables/yearly_concentration_summary.csv`
- `results/h24_supplier_specialization_tables/latest_year_top_dominated_products.csv`
- `results/h24_supplier_specialization_tables/latest_year_top_dominant_specialized_suppliers.csv`
- `results/h24_supplier_specialization_tables/importer_vs_world_supplier_dominance_comparison.csv`
- `results/h24_supplier_specialization_figures/`

The two latest-year top tables are restricted to `strict_dominant_specialized == True`; the broader RCA-only flag remains in the processed parquet and yearly summary.

Rows in latest strict product table: 100
Rows in latest strict supplier table: 70
