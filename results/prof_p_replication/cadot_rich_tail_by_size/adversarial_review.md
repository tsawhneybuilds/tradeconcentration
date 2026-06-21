# Adversarial Econometrics Review: Cadot Rich Tail by Country Size

Review independence: **not independent**. Active delegation rules did not permit a fresh reviewer agent without an explicit user request. This is a local adversarial pass supplemented by an independent R re-estimation of the six population-tercile quadratic models.

## 1. Executive verdict

**Mostly trustworthy for the current descriptive purpose.**

- The analysis answers the stated between-country question using the correct `cadot_broad_156` website/research sample artifact and the 135-country complete-control analytic subset.
- Product-dependent outcomes inherit the upstream exclusion of HS6 `999999` before aggregation.
- The decisive support finding is mechanical and verified: no country in the large-population tercile has mean constant-PPP income above $70,000.
- Python and R reproduce the tercile quadratic coefficients, HC3 standard errors, p-values, and turning points to numerical precision.
- The medium-population Gini bend survives the exact legacy between transformation, the 92-country complete-period restriction, omission of each rich country, and omission of every medium-size country one at a time.
- The evidence does not establish a universal within-size rich-tail bend. The rich tail has only five small and four medium countries, and no large-country overlap.

## 2. Highest-risk findings

### High: no large-country common support at the original turning point

- What happened: the large tercile has zero countries with mean income above $70,000; the two largest population quintiles also have zero.
- Why it matters: the data cannot test whether an approximately $73,000 reconcentration bend exists among comparably large countries.
- Verification: `population_tercile_support.csv` and `population_quintile_support.csv`.
- Required interpretation: call this a support failure, not evidence of no large-country bend.

### Medium: the rich tail is sparse

- What happened: only nine countries lie above $70,000—five small and four medium.
- Why it matters: flexible rich-tail estimates are imprecise and can be leverage-sensitive.
- Verification: rich-country and full leave-one-country-out files.
- Result: the medium-size Gini quadratic remains positive and significant in all 45 omissions; small-size Gini does not bend. Theil conclusions are weaker.

### Medium: population terciles remain coarse

- What happened: each tercile spans a broad size range; the small tercile runs from roughly 56,000 to 3.1 million people and the medium tercile from 3.1 million to 14.9 million.
- Why it matters: “comparable size” is improved but not exact matching.
- Next diagnostic: a nearest-neighbor or local-polynomial comparison in log population would be useful only if adequate income overlap can be demonstrated first.

### Medium: spline inference is post-selection

- What happened: the spline trough is selected from the fitted curve and the reported endpoint-minus-trough standard error conditions on that selected trough.
- Why it matters: spline p-values are descriptive approximations, not valid pre-specified tests of an unknown minimum.
- Fix applied: the report labels this limitation and relies on quadratics plus influence checks for formal inference.

### Low: unequal country-year coverage

- What happened: 92 countries have all 25 years; the remaining countries have 13–24 years.
- Why it matters: country means can represent different time windows.
- Verification: the complete-period sensitivity retains 92 countries.
- Result: medium-size Gini strengthens (`p=0.002`); the large-size Theil significance disappears.

## 3. Data lineage and sample audit

- Input: `results/samples/cadot_broad_156/cadot_broad_ppp_hump_regression_tables/ppp_hump_analysis_panel.csv`.
- Upstream lineage: harmonized product concentration artifacts and World Bank PPP/population controls assembled by the existing broad PPP runner.
- Input rows: 3,240 country-years.
- Analytic countries: 135.
- Years: 2000–2024.
- Duplicate reporter-year keys: 0.
- Missing values in income, log population, oil share, export Gini, and export Theil: 0.
- Country-year coverage: minimum 13, median 25, maximum 25; 92 countries have all 25 years.
- Final unit: one country mean.
- Size groups: fixed terciles of country-mean log population, 45 countries each.

## 4. Merge/join audit

The new analysis performs no merges. It reads the already merged, validated PPP analysis panel and collapses by stable `country`, `iso3`, and `reporter_code` identifiers. Upstream merges are outside the new script and were previously validated in the broad PPP pipeline.

## 5. Variable construction audit

- Income: mean GDP per capita at PPP in constant 2021 international dollars.
- Primary quadratic: square of country-mean income divided by 10,000. This gives an interpretable curve through country means.
- Legacy sensitivity: mean of annual income-squared, matching the existing between-country runner.
- Population: mean log population; plain-English population levels are `exp(mean log population)`, a geometric mean.
- Population terciles: equal-count bins of mean log population.
- Oil control: mean oil export share.
- Export Product Gini: inequality among positive export-product values; higher means more concentration.
- Export Product Theil: fixed-universe product concentration including inactive product support; higher means more concentration.
- Product code `999999` (“Commodities not specified”) is excluded in the upstream product-dependent construction.

## 6. Specification audit

Within population tercile \(s\), the main model is:

\[
C_i = \beta_{0s} + \beta_{1s} y_i + \beta_{2s} y_i^2
 \theta_s Oil_i + \varepsilon_i,
\]

where \(i\) is a country, \(y_i\) is mean constant-PPP GDP per capita scaled by $10,000, and \(C_i\) is export Gini or Theil.

Additional specifications:

- full-sample quadratic with linear log population;
- full-sample quadratic with a cubic population spline;
- income-curve interactions by population tercile;
- continuous income-by-population interactions;
- separate cubic income splines by population tercile;
- exact legacy between-transform sensitivity;
- complete-period and leave-one-country-out sensitivities.

## 7. Inference and identification audit

- Inference uses HC3 heteroskedasticity-robust covariance on the country cross-section.
- Python and R estimates agree to machine precision.
- The model is descriptive. Persistent geography, institutions, resource endowments, entrepôt status, sector structure, and reporting differences remain possible confounders.
- The medium-size Gini result is statistically stable, but this does not turn the income coefficient into a causal development effect.
- The large-size Theil quadratic is not a rich-tail test because its estimated minimum is near $42,000 and the group has no observations above $70,000. It also fails the complete-period sensitivity.

## 8. Replication checklist

- Run `python3 scripts/run_cadot_rich_tail_by_size.py`.
- Run `python3 -m pytest -q tests/test_cadot_rich_tail_by_size.py`.
- Run `Rscript code/replication/cadot_rich_tail_by_size_r_check.R <country_mean_analysis_panel.csv> <r_output.csv>`.
- Confirm all rows in `validation_checks.csv` pass.
- Confirm `python_r_quadratic_comparison.csv` differences remain near machine precision.
- Inspect `population_tercile_income_curves.png`, but base claims on support tables and model outputs rather than visual shape alone.

## 9. Minimal patch plan

No blocking code patch remains for the current descriptive answer. Before a publication-quality “comparable size” claim:

1. Pre-specify an overlap region in income and log population.
2. Estimate a local matching or weighting design only within that overlap.
3. Report effective sample size and covariate balance.
4. Avoid extrapolating a large-country curve beyond observed income support.

## 10. Questions for the researcher

No blocking question for the current result. A future design choice is whether “comparable size” should mean broad population strata or a pre-specified maximum log-population distance for matched countries.
