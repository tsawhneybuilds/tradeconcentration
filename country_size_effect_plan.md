# Country Size Effect Plan

## Goal

Test whether larger countries have systematically different levels of trade concentration than smaller countries. This is a descriptive panel test, not a causal design.

The outcomes are concentration levels for imports and exports across:

- Product Gini
- Partner Gini
- Product top 1% share
- Product top 5% share
- Partner top 1% share
- Partner top 5% share

## Main Test

Use a pooled cross-sectional panel with year fixed effects:

```text
concentration_it =
    beta log_population_it
  + gamma log_gdp_per_capita_it
  + year FE
  + error_it
```

This compares large and small countries within the same year. Year fixed effects absorb global changes in trade reporting, HS revisions, globalization, commodity cycles, and other shocks common to all countries in a given year.

The coefficient of interest is `beta`. It answers:

```text
Within a given year, are countries with larger populations more or less concentrated,
holding GDP per capita fixed?
```

Do not include country fixed effects in the main model. Country fixed effects would absorb the large-country versus small-country comparison, which is the object of interest.

## Inference

Cluster standard errors by country.

Each country appears repeatedly over time, so concentration shocks and measurement errors are likely correlated within country. Country-clustered standard errors should be the default inference method.

## Diagnostic: Year-By-Year Slopes

Estimate separate cross-sectional regressions for each year:

```text
concentration_i =
    beta_t log_population_i
  + gamma_t log_gdp_per_capita_i
  + error_i
```

Then plot `beta_t` over time for each outcome. This checks whether the country-size effect is stable over time or driven by a few particular years.

## Robustness Checks

Run both of these size definitions as robustness checks:

1. Baseline population size:

```text
size_i = log population in the country's first available estimation year
```

2. Average population size:

```text
size_i = average log population across the country's available estimation years
```

Then re-estimate:

```text
concentration_it =
    beta size_i
  + gamma log_gdp_per_capita_it
  + year FE
  + error_it
```

These robustness checks make the interpretation even clearer: they compare countries that are generally larger with countries that are generally smaller, rather than relying on year-to-year population movement.

## Data And Validation Notes

- Use `rd2_countries` as the primary sample unless explicitly testing the legacy 33-country sample.
- Use concentration outcomes from the existing `concentration_all_years.parquet` panel.
- Join population and GDP from World Bank controls, then construct:

```text
log_gdp_per_capita_it = log_gdp_current_usd_it - log_population_it
```

- Do not use GNI per capita as a main control.
- Do not control for total trade value in the main model because it is mechanically related to the concentration denominator.
- Product-level concentration outputs must exclude HS6 `999999` before aggregation. Partner concentration may include `999999` when products are only summed into reporter-partner totals, consistent with the repo rules.
