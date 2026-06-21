# PPP GDP Hump Regressions

Generated: 2026-06-16T09:53:11+00:00

This is a descriptive Cadot-style hump check for the `cadot_broad_156` Cadot broad 156-country modern replication sample, 2000-2024. The income variable is World Bank `NY.GDP.PCAP.PP.KD`, GDP per capita at PPP in constant 2021 international dollars.

Specification:

`outcome_ct = beta1 income_ct + beta2 income_ct^2 + log_population_ct + oil_export_share_ct + year_FE_t + error_ct`

The table reports pooled year-FE, country+year-FE, and between-country variants. Pooled and country+year-FE standard errors are clustered by reporter country; between estimates are country-mean OLS. Product outcomes inherit the pipeline rule excluding HS6 `999999`; partner outcomes use the default partner-total convention.

## Results

| outcome                         | estimator       | income_form   | quadratic_sign_p   | turning_point   | inside_minmax   | inside_p05_p95   | verdict                                 |   nobs |   clusters |
|:--------------------------------|:----------------|:--------------|:-------------------|:----------------|:----------------|:-----------------|:----------------------------------------|-------:|-----------:|
| Export Product Gini             | pooled_year_fe  | level_ppp     | +, p=<0.001        | $78.5k          | True            | False            | statistical bend, edge turning point    |   3240 |        135 |
| Export Product Gini             | country_year_fe | level_ppp     | +, p=0.933         | $471.1k         | False           | False            | outside-support artifact                |   3240 |        135 |
| Export Product Gini             | between_country | level_ppp     | +, p=<0.001        | $72.6k          | True            | True             | clear hump                              |    135 |          0 |
| Export Product Gini             | pooled_year_fe  | log_ppp       | +, p=0.990         | n/a             | False           | False            | outside-support artifact                |   3240 |        135 |
| Export Product Gini             | country_year_fe | log_ppp       | -, p=0.794         | <$1             | False           | False            | no concentration U-shape                |   3240 |        135 |
| Export Product Gini             | between_country | log_ppp       | +, p=0.776         | $385477.1m      | False           | False            | outside-support artifact                |    135 |          0 |
| Export Product Theil            | pooled_year_fe  | level_ppp     | +, p=<0.001        | $78.2k          | True            | False            | statistical bend, edge turning point    |   3240 |        135 |
| Export Product Theil            | country_year_fe | level_ppp     | -, p=0.608         | $170.1k         | True            | False            | no concentration U-shape                |   3240 |        135 |
| Export Product Theil            | between_country | level_ppp     | +, p=<0.001        | $73.2k          | True            | True             | clear hump                              |    135 |          0 |
| Export Product Theil            | pooled_year_fe  | log_ppp       | +, p=0.001         | $283.2k         | False           | False            | outside-support artifact                |   3240 |        135 |
| Export Product Theil            | country_year_fe | log_ppp       | +, p=0.083         | $13.0k          | True            | True             | no clean hump                           |   3240 |        135 |
| Export Product Theil            | between_country | log_ppp       | +, p=0.001         | $204.4k         | False           | False            | outside-support artifact                |    135 |          0 |
| Export Product HHI              | pooled_year_fe  | level_ppp     | +, p=<0.001        | $79.0k          | True            | False            | statistical bend, edge turning point    |   3240 |        135 |
| Export Product HHI              | country_year_fe | level_ppp     | -, p=0.028         | $123.0k         | True            | False            | no concentration U-shape                |   3240 |        135 |
| Export Product HHI              | between_country | level_ppp     | +, p=<0.001        | $74.7k          | True            | False            | statistical bend, edge turning point    |    135 |          0 |
| Export Product HHI              | pooled_year_fe  | log_ppp       | +, p=0.016         | $104.5k         | True            | False            | statistical bend, edge turning point    |   3240 |        135 |
| Export Product HHI              | country_year_fe | log_ppp       | +, p=0.410         | $96             | False           | False            | outside-support artifact                |   3240 |        135 |
| Export Product HHI              | between_country | log_ppp       | +, p=0.018         | $95.5k          | True            | False            | statistical bend, edge turning point    |    135 |          0 |
| Export Active HS6 Product Count | pooled_year_fe  | level_ppp     | -, p=<0.001        | $78.2k          | True            | False            | statistical active-line bend, edge peak |   3240 |        135 |
| Export Active HS6 Product Count | country_year_fe | level_ppp     | -, p=0.002         | $95.3k          | True            | False            | statistical active-line bend, edge peak |   3240 |        135 |
| Export Active HS6 Product Count | between_country | level_ppp     | -, p=<0.001        | $73.3k          | True            | True             | clear active-line hump                  |    135 |          0 |
| Export Active HS6 Product Count | pooled_year_fe  | log_ppp       | -, p=0.049         | $1.8m           | False           | False            | outside-support active-line peak        |   3240 |        135 |
| Export Active HS6 Product Count | country_year_fe | log_ppp       | -, p=0.045         | $159.8k         | True            | False            | statistical active-line bend, edge peak |   3240 |        135 |
| Export Active HS6 Product Count | between_country | log_ppp       | -, p=0.044         | $1.3m           | False           | False            | outside-support active-line peak        |    135 |          0 |
| Import Product Gini             | pooled_year_fe  | level_ppp     | +, p=<0.001        | $65.0k          | True            | True             | clear hump                              |   3236 |        135 |
| Import Product Gini             | country_year_fe | level_ppp     | +, p=0.021         | $76.0k          | True            | False            | statistical bend, edge turning point    |   3236 |        135 |
| Import Product Gini             | between_country | level_ppp     | +, p=<0.001        | $61.3k          | True            | True             | clear hump                              |    135 |          0 |
| Import Product Gini             | pooled_year_fe  | log_ppp       | +, p=0.005         | $73.2k          | True            | True             | clear hump                              |   3236 |        135 |
| Import Product Gini             | country_year_fe | log_ppp       | +, p=0.025         | $82.9k          | True            | False            | statistical bend, edge turning point    |   3236 |        135 |
| Import Product Gini             | between_country | log_ppp       | +, p=0.004         | $66.8k          | True            | True             | clear hump                              |    135 |          0 |
| Import Product Theil            | pooled_year_fe  | level_ppp     | +, p=<0.001        | $67.4k          | True            | True             | clear hump                              |   3236 |        135 |
| Import Product Theil            | country_year_fe | level_ppp     | +, p=0.080         | $98.5k          | True            | False            | no clean hump                           |   3236 |        135 |
| Import Product Theil            | between_country | level_ppp     | +, p=<0.001        | $63.0k          | True            | True             | clear hump                              |    135 |          0 |
| Import Product Theil            | pooled_year_fe  | log_ppp       | +, p=<0.001        | $55.9k          | True            | True             | clear hump                              |   3236 |        135 |
| Import Product Theil            | country_year_fe | log_ppp       | +, p=0.199         | $249.9k         | False           | False            | outside-support artifact                |   3236 |        135 |
| Import Product Theil            | between_country | log_ppp       | +, p=<0.001        | $52.5k          | True            | True             | clear hump                              |    135 |          0 |
| Import Product HHI              | pooled_year_fe  | level_ppp     | +, p=0.131         | $83.8k          | True            | False            | no clean hump                           |   3236 |        135 |
| Import Product HHI              | country_year_fe | level_ppp     | +, p=0.134         | $131.7k         | True            | False            | no clean hump                           |   3236 |        135 |
| Import Product HHI              | between_country | level_ppp     | +, p=0.148         | $72.6k          | True            | True             | no clean hump                           |    135 |          0 |
| Import Product HHI              | pooled_year_fe  | log_ppp       | +, p=0.054         | $58.7k          | True            | True             | no clean hump                           |   3236 |        135 |
| Import Product HHI              | country_year_fe | log_ppp       | -, p=0.902         | <$1             | False           | False            | no concentration U-shape                |   3236 |        135 |
| Import Product HHI              | between_country | log_ppp       | +, p=0.072         | $51.0k          | True            | True             | no clean hump                           |    135 |          0 |
| Import Active HS6 Product Count | pooled_year_fe  | level_ppp     | -, p=<0.001        | $74.8k          | True            | False            | statistical active-line bend, edge peak |   3236 |        135 |
| Import Active HS6 Product Count | country_year_fe | level_ppp     | -, p=0.414         | $130.3k         | True            | False            | no clean active-line hump               |   3236 |        135 |
| Import Active HS6 Product Count | between_country | level_ppp     | -, p=<0.001        | $69.9k          | True            | True             | clear active-line hump                  |    135 |          0 |
| Import Active HS6 Product Count | pooled_year_fe  | log_ppp       | -, p=0.012         | $128.9k         | True            | False            | statistical active-line bend, edge peak |   3236 |        135 |
| Import Active HS6 Product Count | country_year_fe | log_ppp       | -, p=0.575         | $2.9m           | False           | False            | outside-support active-line peak        |   3236 |        135 |
| Import Active HS6 Product Count | between_country | log_ppp       | -, p=0.014         | $128.1k         | True            | False            | statistical active-line bend, edge peak |    135 |          0 |
| Export Partner Gini             | pooled_year_fe  | level_ppp     | -, p=0.678         | $309.3k         | False           | False            | no concentration U-shape                |   3240 |        135 |
| Export Partner Gini             | country_year_fe | level_ppp     | +, p=0.234         | $97.2k          | True            | False            | no clean hump                           |   3240 |        135 |
| Export Partner Gini             | between_country | level_ppp     | +, p=0.921         | -$725.0k        | False           | False            | outside-support artifact                |    135 |          0 |
| Export Partner Gini             | pooled_year_fe  | log_ppp       | +, p=0.053         | $3.6k           | True            | True             | no clean hump                           |   3240 |        135 |
| Export Partner Gini             | country_year_fe | log_ppp       | -, p=0.296         | $6.0k           | True            | True             | no concentration U-shape                |   3240 |        135 |
| Export Partner Gini             | between_country | log_ppp       | +, p=0.033         | $4.6k           | True            | True             | weak/borderline hump                    |    135 |          0 |
| Import Partner Gini             | pooled_year_fe  | level_ppp     | -, p=0.264         | $103.0k         | True            | False            | no concentration U-shape                |   3236 |        135 |
| Import Partner Gini             | country_year_fe | level_ppp     | -, p=0.049         | $82.6k          | True            | False            | no concentration U-shape                |   3236 |        135 |
| Import Partner Gini             | between_country | level_ppp     | -, p=0.543         | $123.0k         | True            | False            | no concentration U-shape                |    135 |          0 |
| Import Partner Gini             | pooled_year_fe  | log_ppp       | -, p=0.261         | $127.8k         | True            | False            | no concentration U-shape                |   3236 |        135 |
| Import Partner Gini             | country_year_fe | log_ppp       | -, p=0.258         | $199.6k         | False           | False            | no concentration U-shape                |   3236 |        135 |
| Import Partner Gini             | between_country | log_ppp       | -, p=0.425         | $227.9k         | False           | False            | no concentration U-shape                |    135 |          0 |

## Short Read

- In the pooled/year-FE headline, level PPP restores clear Cadot-style concentration U-shapes for: Import Product Gini, Import Product Theil.
- In the pooled/year-FE headline, log PPP restores a clear concentration U-shape for: Import Product Gini, Import Product Theil.
- In plain English, a positive quadratic is a U-shape in concentration: concentration first falls with development, then rises after the turning point. That is the concentration-side version of the Cadot diversification hump.
- The level/log split matters because logging income compresses the rich-country tail where late-stage reconcentration is expected. Level PPP therefore stays closer to Cadot's constant-PPP setup, while log PPP is a stricter functional-form stress test.
- This is the Cadot-comparable broad replication track: active non-group Comtrade reporters with ISO3 metadata and at least 19 annual HS final-data years in 2000-2024. It is not a website sample and does not replace `rd2_countries`.

## Diagnostics

- Selected reporter sample: 156 reporters; expected 156.
- Complete-case policy: outcome-specific country-years with valid concentration, PPP income, log population, oil share, and year FE.
- Analytic sample rows by outcome are reported in `results/samples/cadot_broad_156/cadot_broad_ppp_hump_regression_tables/ppp_hump_sample_attrition.csv`.
- PPP source: `NY.GDP.PCAP.PP.KD` (GDP per capita, PPP (constant 2021 international $)).
- PPP coverage rows in selected country panel: 3847 / 3900; complete countries: 151 / 156; duplicate iso3-year keys: 0.
- PPP rows after merging into the controls panel: 3703 / 3753.
- PPP support in analytic sample: $796 to $174,570; p05=$2,245, p95=$74,159.

## Interpretation

Level PPP is the closer Cadot-style functional form. Log PPP compresses the rich-country end where reconcentration is supposed to appear, so it is the stricter functional-form check.

## Outputs

- `ppp_hump_regression_summary.csv`: compact 10 outcomes x 2 income forms x 3 estimators results table.
- `ppp_hump_regression_models.csv`: term-level regression output.
- `ppp_hump_analysis_panel.csv`: analytic country-year panel used for the regressions.
- `ppp_hump_sample_attrition.csv`: outcome-level attrition diagnostics.
- `ppp_hump_diagnostics_level_ppp_five_outcomes.png`: level-PPP visual diagnostics.
- `ppp_hump_diagnostics_log_ppp_five_outcomes.png`: log-PPP visual diagnostics.
