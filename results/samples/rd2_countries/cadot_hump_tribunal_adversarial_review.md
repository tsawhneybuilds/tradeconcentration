# Adversarial Econometrics Review: Cadot Hump Tribunal

Created: 2026-06-02T12:37:41+00:00

Review independence: **not independent**. Subagent delegation was not explicitly authorized in the current request, so this is a local adversarial pass by the same Codex session.

## Verdict

Use the outputs as a first-pass descriptive tribunal, not as final causal evidence. The pipeline is useful for separating mechanisms, but the old-cone sophistication proxy is an rd2 leave-one-out PRODY proxy based on constant-PPP GDP per capita rather than a true global PRODY unless broader country income controls are added.

## Checks

- Data lineage: country-year outcomes come from Exercise 1, harmonized world-relative Product Gini, Exercise 6 lumpy exclusions, Exercise 10 HS2-preserving benchmarks, and Exercise 12 HS4 transition outputs.
- Product-dependent exclusion: native HS6 product exports exclude `999999` before HS6/HS4/HS2, Section 16, PRODY, and exit-window aggregation. Excluded rows recorded by the runner: 0.
- Main sample: balanced 2000-2024 rd2 world-relative panel has 1375 rows and 55 countries.
- Duplicate keys: runner validates country-year uniqueness for controls, standard concentration, world-relative panel, HS2 benchmark, commodity panel, and final country-year panel.
- Leave-one-out PRODY: product sophistication subtracts the focal country-product contribution from both numerator and denominator and uses World Bank `NY.GDP.PCAP.PP.KD` constant-PPP GDP per capita; products with fewer than 3 exporters are set missing.
- Exit definition: HS4 exit follows the Exercise 12-style adjacent 2+2 persistence rule with the $50,000 constant-2024-USD activity threshold.
- Inference: hump regressions are descriptive OLS with year fixed effects and clustered/two-way-clustered SE variants. The old-cone model is a linear probability model residualized by country, product, and base-year fixed effects, clustered by country.
- Website consistency: the site page reads static CSV/PNG outputs from `rd2_countries`; no result should be interpreted for `prof_p_33` or `world_broad`.

## Remaining Caveats

- The PRODY proxy is sample-internal to rd2 because the available world-broad product totals do not include a complete matched world-broad income-control panel in this runner.
- HS revision harmonization is handled in the world-relative measure, but the old-cone HS4 windows use native HS4 prefixes; that is appropriate for first-pass transition mechanics but not a final harmonized product-life-cycle test.
- Section 16 sensitivity drops chapters 84-85 at native HS6 level; it does not solve all cross-section differences in HS code density.
- Commodity classification uses the existing Exercise 6 lumpy bundle and oil export share, so commodity-driven reconcentration outside those categories may remain in the unexplained bucket.
- Mechanism flags use transparent thresholds; they should be treated as triage labels, not hypothesis tests.
