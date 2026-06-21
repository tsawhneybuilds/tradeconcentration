# Adversarial econometric review: nested production-core old-cone test

## Executive verdict

**Mostly trustworthy** for a descriptive mechanism sensitivity. This was a local rather than fresh-agent review because delegation was not permitted.

- Benchmark and focal samples use the same explicit nested screen.
- PRODY is recomputed inside every benchmark rather than inherited from the broad world.
- The baseline coefficient is reproduced before screened estimates are accepted.
- The design remains noncausal and sensitive to the rich-side and product-activity definitions.

## Highest-risk findings

1. **Sample selection (high):** production-core screens change the population represented; they diagnose composition but do not recover a causal production sample.
2. **Generated regressor (medium):** PRODY is estimated from exporter shares and income, so conventional model uncertainty does not include PRODY estimation error.
3. **Overlapping windows (medium):** five-year adjacent-window observations overlap. Reporter clustering addresses within-country dependence; reporter/product two-way clustering addresses common product shocks but not every temporal dependence structure.
4. **Belgium classification (acceptable only if explicit):** Belgium is included in the named Screen-B sensitivity by researcher choice; the page must not imply it lacks substantial domestic production.

## Data lineage and sample audit

Harmonized world_broad country-product exports -> fixed country screens -> screen-specific PRODY. Harmonized cadot_broad_156 HS4 adjacent 2+2 windows -> identical focal screens -> exit LPM. Coverage rows: 4; classification rows: 181.

## Merge/join audit

PRODY attaches on reporter, base year, and HS4 product with many-to-one validation. Country classifications use reporter codes plus ISO3 population controls; missing classifications block execution.

## Variable construction audit

Exit requires activity above $50,000 constant-2024 USD in both base years and inactivity in at least one future-window year. Mismatch is log(country PPP GDP per capita / screen-specific level-income PRODY).

## Specification audit

The LPM includes mismatch, rich-side indicator, and their interaction, with reporter, product, and base-year fixed effects. The interaction is the old-cone diagnostic.

## Inference and identification audit

Country-clustered and country/product two-way-clustered intervals are reported. The coefficient is descriptive because income, specialization, and exit are jointly determined.

## Replication checklist

- Rebuild country classifications and verify nested sets.
- Recompute each PRODY benchmark from surviving reporters.
- Reproduce the broad baseline coefficient.
- Inspect fixed-cutoff and screen-p75 alternatives.
- Inspect named-country drop/add-back results.

## Minimal patch plan

No blocking patch remains. Preserve full exclusion tables and avoid calling Screen B domestic-production data.

## Questions for the researcher

No unresolved decision blocks reporting. A value-added-export extension would be a different estimand.
