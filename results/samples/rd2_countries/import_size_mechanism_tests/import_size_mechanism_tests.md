# Import Size Mechanism Tests

Generated: 2026-06-02T20:24:15+00:00

## Purpose

These tests ask why larger countries have lower World-Relative Import Product Gini. They are descriptive country-year regressions on the balanced `rd2_countries` 2000-2024 import panel, with year fixed effects and country-clustered standard errors. Product-level inputs exclude HS6 `999999` upstream.

Main estimating equation:

`concentration_ct = beta log_population_ct + gamma log_gdp_per_capita_ct + year_FE_t + error_ct`

Mechanism checks add active-product count, openness/tariffs, or top-driver controls; some checks change the outcome to a common-zero-universe Gini, import-bin Gini, or lumpy-product-excluded world-relative Gini.

## Bottom Line

- Baseline World-Relative Import Product Gini population coefficient: -0.0340, p=1.16e-05, n=1,375.
- Adding harmonized active import product count: -0.0227, p=0.0023, n=1,375.
- Common product universe with zeros: -0.0045, p=0.0253, n=1,375.
- Dropping Hong Kong, Singapore, Luxembourg, Iceland, and Guyana: -0.0228, p=4.90e-04, n=1,250.
- Dropping aircraft/gold/precious metals/pharma/vehicles/staples from both country and world product baskets: -0.0379, p=6.78e-06, n=1,375.

Interpretation rule: if the absolute `log_population` coefficient collapses after a mechanism control or exclusion, that mechanism is a plausible accounting channel for the population gradient. If it stays similar, that mechanism is not doing most of the explanatory work.

## Key Population Coefficients

| model | beta | p | n | clusters | doubling_effect | shrink_vs_baseline |
| --- | --- | --- | --- | --- | --- | --- |
| wr_baseline_year_fe | **-0.0340** | **1.16e-05** | 1,375 | 55 | -0.0235 | 0.0% |
| wr_plus_standard_active_count | **-0.0211** | **0.0044** | 1,375 | 55 | -0.0146 | 37.9% |
| wr_plus_harmonized_active_count | **-0.0227** | **0.0023** | 1,375 | 55 | -0.0157 | 33.2% |
| common_zero_baseline_year_fe | **-0.0045** | **0.0253** | 1,375 | 55 | -0.0031 |  |
| common_zero_plus_harmonized_active_count | 1.86e-04 | 0.9257 | 1,375 | 55 | 1.29e-04 |  |
| wr_drop_hkg_sgp_lux_isl_guy | **-0.0228** | **4.90e-04** | 1,250 | 50 | -0.0158 | 32.9% |
| wr_plus_trade_openness | **-0.0311** | **2.42e-04** | 1,375 | 55 | -0.0216 | 8.4% |
| wr_ppp_gdppc_baseline_year_fe | **-0.0359** | **7.55e-06** | 1,375 | 55 | -0.0249 | -5.8% |
| wr_ppp_gdppc_plus_trade_openness | **-0.0319** | **1.98e-04** | 1,375 | 55 | -0.0221 | 6.0% |
| wr_ppp_gdppc_plus_tariff | **-0.0345** | **4.99e-06** | 1,148 | 54 | -0.0239 | -1.7% |
| wr_after_dropping_aircraft_gold_precious_pharma_vehicles_staples | **-0.0379** | **6.78e-06** | 1,375 | 55 | -0.0263 | -11.5% |
| wr_after_dropping_lumpy_plus_energy | **-0.0355** | **1.65e-05** | 1,375 | 55 | -0.0246 | -4.5% |
| wr_plus_top_driver_lumpy_share | **-0.0326** | **7.28e-05** | 1,375 | 55 | -0.0226 | 4.0% |
| wr_plus_top_driver_lumpy_plus_energy_share | **-0.0349** | **4.19e-05** | 1,375 | 55 | -0.0242 | -2.8% |

Bold beta/p-value entries have raw p < 0.05. `doubling_effect` is the implied change in the Gini outcome from doubling population. `shrink_vs_baseline` is shown only for world-relative Gini variants, because active, common-zero, and bin-specific Ginis are on different outcome scales.

## Import-Bin Split

| bin | beta | p | n | doubling_effect |
| --- | --- | --- | --- | --- |
| capital_goods | -0.0032 | 0.2747 | 1,375 | -0.0022 |
| energy | -0.0012 | 0.6346 | 1,375 | -8.41e-04 |
| final_consumption | 8.34e-04 | 0.6620 | 1,375 | 5.78e-04 |
| intermediates | **-0.0053** | **0.0283** | 1,375 | -0.0037 |

The bin split uses the Exercise 3 BEC-style import bins and the same balanced country-year sample. It is not world-relative; it is within-bin active Product Gini.

## Validation Diagnostics

| diagnostic | value | detail |
| --- | --- | --- |
| balanced_panel_rows | 1375 | 55 countries x 25 years |
| balanced_panel_duplicate_reporter_year | 0 |  |
| country_product_rows_balanced_sample | 6202707 | 5024 harmonized product ids |
| country_product_duplicate_reporter_year_product | 0 |  |
| country_product_999999_rows | 0 | Must be zero under repo product-level rule. |
| hubs_microstates_rows_present | 125 | Country-year rows among GUY,HKG,ISL,LUX,SGP. |
| hubs_microstates_countries_present | 5 | GUY,HKG,ISL,LUX,SGP |
| import_bin_rows_balanced_sample | 5500 | capital_goods,energy,final_consumption,intermediates |
| top_driver_rows_balanced_sample | 20625 | 55 countries |
| product_lumpy_category_not_lumpy | 5800586 | products=4692; import_value=2.109e+14 |
| product_lumpy_category_aircraft | 10844 | products=10; import_value=3.618e+12 |
| product_lumpy_category_energy | 51827 | products=48; import_value=4.417e+13 |
| product_lumpy_category_food_staples | 145803 | products=118; import_value=4.02e+12 |
| product_lumpy_category_gold_precious | 54041 | products=50; import_value=1.045e+13 |
| product_lumpy_category_pharma | 38116 | products=30; import_value=1.007e+13 |
| product_lumpy_category_vehicles | 101490 | products=76; import_value=2.501e+13 |

## Output Files

- mechanism panel: `results/samples/rd2_countries/import_size_mechanism_tests/import_size_mechanism_panel.csv`
- all models: `results/samples/rd2_countries/import_size_mechanism_tests/import_size_mechanism_models.csv`
- key coefficients: `results/samples/rd2_countries/import_size_mechanism_tests/import_size_mechanism_key_coefficients.csv`
- diagnostics: `results/samples/rd2_countries/import_size_mechanism_tests/import_size_mechanism_diagnostics.csv`
- lumpy product summary: `results/samples/rd2_countries/import_size_mechanism_tests/import_size_lumpy_product_summary.csv`
- top-driver measures: `results/samples/rd2_countries/import_size_mechanism_tests/import_size_top_driver_measures.csv`
- coefficient ladder plot: `results/samples/rd2_countries/import_size_mechanism_tests/import_size_population_coefficient_ladder.png`

## Caveats

- These are descriptive accounting regressions, not causal estimates of population.
- Active-count controls are post-treatment style mechanism controls: useful for decomposition, not causal adjustment.
- The lumpy top-driver control uses the saved top-driver contribution file, so it summarizes the largest drivers rather than every product's leave-one-out contribution.
- Tariff regressions use a smaller sample because WDI/WITS tariff coverage is incomplete.
