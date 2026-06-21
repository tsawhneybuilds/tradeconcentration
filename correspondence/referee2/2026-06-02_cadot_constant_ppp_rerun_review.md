# Adversarial Econometrics Review: Cadot Constant-PPP Rerun

Created: 2026-06-02

Review independence: **not independent**. Multi-agent tooling was available, but active tool rules only allow spawning a sub-agent when the user explicitly asks for delegation or sub-agents. This is therefore a local adversarial review by the same Codex session that patched and reran the pipeline.

## Executive Verdict

**Mostly trustworthy for current descriptive use, not publication-ready causal evidence.**

- The headline Cadot income axis is now constant PPP GDP per capita: World Bank `NY.GDP.PCAP.PP.KD`, constant 2021 international dollars.
- The rerun avoided a raw Comtrade rebuild and reused validated concentration/control panels, which is appropriate because the change is income-specification related.
- Broad `cadot_broad_156` sample construction still selects exactly 156 reporters with no duplicate reporter codes or ISO3 codes.
- Broad regressions use only 135 analytic countries/clusters after complete-case controls, so results must not be described as regressions on all 156 countries.
- Product-dependent mechanism artifacts checked here do not contain the `HS4:9999` proxy that would result from HS6 `999999` leaking into HS4 aggregation.
- Main interpretation risk remains functional-form and estimand drift: pooled/year-FE constant-PPP humps are descriptive development-stage patterns, not proof that the same country inevitably reconcentrates as it grows.

## Highest-Risk Findings

**Severity: High. Broad sample attrition changes the estimand.**  
Selected reporters remain 156, but broad regression panels use 3,236-3,240 rows and 135 countries/clusters after complete-case requirements. This is defensible if reported, but the regression result is not literally a 156-country regression.

**Severity: Medium. Export product result is weaker than import product result in the broad sample.**  
Broad export Product Gini has a significant level-PPP bend, but the turning point is outside p05-p95 support; log PPP gives no U-shape. Broad import Product Gini is the cleanest result in both level and log PPP.

**Severity: Medium. rd2 mechanism tribunal and rd2 PPP regression answer different questions.**  
The rd2 PPP regression table finds clear level-PPP product humps. The mechanism tribunal's preferred log-income quadratic does not give a clean world-relative product U-shape after the constant-PPP refactor. Treat the mechanism section as mechanism triage, not as the primary regression result.

**Severity: Medium. Review is local, not fresh-agent independent.**  
The validation is concrete and table-based, but it is not an independent replication by another model family or a separate R/Stata implementation.

## Data Lineage And Sample Audit

- `rd2_countries` concentration outcomes come from existing sample processed/results artifacts.
- `cadot_broad_156` concentration outcomes come from existing broad sample artifacts under `data/processed/samples/cadot_broad_156/` and `results/samples/cadot_broad_156/`.
- Constant PPP controls come from `ppp_hump_world_bank_controls.csv` using `NY.GDP.PCAP.PP.KD`.
- Population and oil-share controls are merged by stable ISO3/year and reporter/year keys.
- Broad country panel validation: 156 rows, 156 reporter codes, 156 ISO3 codes.
- Broad analysis panel validation: no duplicate `reporter_code`-`year` keys; constant PPP column present and nonmissing.
- rd2 tribunal panel validation: no duplicate `reporter_code`-`year` keys; `gdp_pc_ppp_constant_2021_intl_usd` and `log_income_pc` present and nonmissing.

## Merge And Join Audit

- The PPP controls are merged on `iso3` and `year` with many-to-one validation in the runner.
- The rd2 mechanism tribunal merges country-year controls, concentration outcomes, world-relative Product Gini, commodity diagnostics, HS2 benchmark, and transition outputs with explicit uniqueness checks on country-year panels.
- No many-to-many merge was identified in the patched Cadot rerun path.
- Attrition is reported in `ppp_hump_sample_attrition.csv`; broad complete-case loss is driven mostly by population/control availability, not the sample selector.

## Variable Construction Audit

- Headline income: `gdp_pc_ppp_constant_2021_intl_usd`.
- Regression log income: `log_gdp_pc_ppp_constant_2021_intl_usd`; the tribunal aliases this as `log_income_pc`.
- Quadratic term: `log_income_pc_sq` in the mechanism tribunal; level PPP regressions use income divided by 10,000 and squared.
- Product-dependent tribunal exports exclude HS6 `999999` before HS4/HS2, Section 16, PRODY, and exit-window aggregation.
- Product-dependent validation checked that generated HS4 PRODY and old-cone windows do not contain `HS4:9999`.
- Current-GNI variables remain only as legacy diagnostic columns where present; they are no longer the headline Cadot income axis.

## Specification Audit

The headline descriptive equation is:

`concentration_ct = beta1 income_ct + beta2 income_ct^2 + gamma log_population_ct + delta oil_share_ct + year_FE_t + error_ct`

- rd2 PPP runner: balanced 55-country panel, 2000-2024, reporter-clustered standard errors.
- broad PPP runner: complete-case panel, 2000-2024, 135 analytic countries/clusters, reporter-clustered standard errors.
- mechanism tribunal: rd2 balanced panel, year fixed effects, reporter-clustered and two-way-cluster variants in output tables.
- This is not a causal design. The fixed effects and controls reduce obvious confounding but do not identify a causal effect of income on concentration.

## Inference And Identification Audit

- Cluster counts are adequate for descriptive clustered inference: 55 clusters in rd2, 135 in broad.
- Serial correlation and cross-country dependence remain possible; clustering by reporter is a defensible default but not a complete solution.
- The econometrics reference graph flags that panel fixed effects require panel data and often need clustered inference; model tables should report sample, covariates, fixed effects, standard-error choice, units, and estimator changes.
- Turning-point support checks are essential. A significant quadratic with a turning point outside p05-p95 should be reported as edge/weak evidence.

## Replication Checklist

Commands run:

```bash
env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
/usr/bin/nice -n 10 python3 scripts/run_ppp_hump_regressions.py --country-sample rd2_countries

env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
/usr/bin/nice -n 10 python3 scripts/run_cadot_broad_ppp_hump_regressions.py

env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
/usr/bin/nice -n 10 python3 scripts/run_cadot_hump_tribunal.py

env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
/usr/bin/nice -n 10 python3 scripts/build_cadot_hump_from_scratch_explainer.py
```

Focused tests were run directly because neither the system nor bundled Python environment had `pytest` installed:

- `python3 tests/test_cadot_broad_sample.py -q`: 4 tests passed.
- Direct calls to the three assertion functions in `tests/test_cadot_hump_tribunal.py`: all passed.

## Minimal Patch Plan

- Keep current-GNI outputs visually labeled as legacy sensitivity if they remain on the page.
- Add a fresh independent replication pass when delegation is explicitly authorized or when another environment/model family is available.
- Add a formal pytest environment or document the direct-test fallback.
- Consider a sensitivity table with country fixed effects for the broad sample before making stronger within-country claims.

## Questions For The Researcher

- Should the broad 156-country headline emphasize import concentration, or should it remain secondary because Cadot's original mechanism is export diversification/reconcentration?
- Should the fixed rich-side threshold in mechanism flags use a converted Cadot 2005-PPP benchmark, or stay as a transparent modern constant-PPP threshold?
