# Adversarial econometric review: foreign import-demand decomposition

## Executive verdict

**Mostly trustworthy** for the stated accounting and descriptive purpose. This was a local review, not an independent fresh-agent pass, because delegation was not permitted.

- The focal object remains exports; reported imports enter only as the reference distribution.
- The preferred reference removes the focal country as both importer and recorded origin.
- The Theil identity closes to a maximum absolute residual of 6.217e-15.
- Results remain descriptive: reported imports proxy foreign traded demand but do not identify a demand shock.

## Highest-risk findings

1. **Mirror-trade discrepancy (acceptable if disclosed).** Import values need not equal exporter-reported values because of CIF/FOB valuation, timing, and partner attribution.
2. **Zero-demand smoothing (material diagnostic).** Country-years with more than 0.1% of export value on zero benchmark products are excluded from preferred regressions.
3. **Cross-sectional identification (high).** Year-FE coefficients compare countries within years and are not causal effects of population.

## Data lineage and sample audit

Raw world_broad importer-origin-product records -> HS6 999999 exclusion -> LT/HGL HS1992 conversion -> world/importer/origin/self components -> focal export-product merge -> reporter-year decomposition. Preferred panel rows: 3,753; common export/import rows: 3,589.

## Merge/join audit

All joins use reporter/year/product stable keys with many-to-one validation. Unmatched import products are treated as zero reported demand and audited through the smoothing share rather than silently dropped.

## Variable construction audit

For export shares s and double-leave-out import shares m, observed Theil equals sum(s log(Km)) + sum(s log(s/m)). The second term is KL divergence and is nonnegative up to floating-point tolerance.

## Specification audit

Outcome = log population + log GDP per capita + year fixed effects + error. Main standard errors cluster by reporter; a reporter/year two-way variant and reporter+year fixed-effect diagnostic are reported.

## Inference and identification audit

The country-cluster count is reported in the model CSV. Common product-demand shocks motivate the two-way clustered sensitivity. Neither specification makes population exogenous.

## Replication checklist

- Run this script with `--benchmark-basket row_imports`.
- Confirm all validation rows pass.
- Compare main, two-way, inclusive, and country-FE rows.
- Inspect the zero-benchmark export-value distribution.

## Minimal patch plan

No blocking patch remains. Preserve the demand-proxy language and common-sample comparison.

## Questions for the researcher

No unresolved question blocks descriptive reporting. A causal demand design would require an external source of product-demand shocks.
