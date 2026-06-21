# Cadot Broad PPP Independent Re-estimation Checks

Generated: 2026-06-16T09:53:15+00:00

Overall status: passed

These checks re-estimate one pooled/year-FE model and one country+year-FE model from the saved analytic panel without importing `run_ppp_hump_regressions.py`.

| check                                    | term                                     |   saved_coefficient |   reestimated_coefficient |   abs_coefficient_diff |   saved_std_error |   reestimated_std_error |   abs_std_error_diff |   nobs |   clusters | passed   |
|:-----------------------------------------|:-----------------------------------------|--------------------:|--------------------------:|-----------------------:|------------------:|------------------------:|---------------------:|-------:|-----------:|:---------|
| pooled_export_product_gini_level_ppp     | gdp_pc_ppp_constant_2021_intl_usd_10k    |        -0.0136161   |              -0.0136161   |            2.39392e-16 |       0.00247911  |             0.00247911  |          1.71738e-16 |   3240 |        135 | True     |
| pooled_export_product_gini_level_ppp     | gdp_pc_ppp_constant_2021_intl_usd_10k_sq |         0.000867049 |               0.000867049 |            7.28584e-17 |       0.000205397 |             0.000205397 |          8.32396e-17 |   3240 |        135 | True     |
| pooled_export_product_gini_level_ppp     | log_population                           |        -0.00637832  |              -0.00637832  |            4.68375e-17 |       0.00126603  |             0.00126603  |          9.6494e-17  |   3240 |        135 | True     |
| pooled_export_product_gini_level_ppp     | oil_export_share                         |         0.0730522   |               0.0730522   |            1.38778e-17 |       0.00939252  |             0.00939252  |          1.73472e-18 |   3240 |        135 | True     |
| country_fe_import_product_gini_level_ppp | gdp_pc_ppp_constant_2021_intl_usd_10k    |        -0.00516422  |              -0.00516422  |            2.17708e-16 |       0.00314004  |             0.00314004  |          3.29858e-15 |   3236 |        135 | True     |
| country_fe_import_product_gini_level_ppp | gdp_pc_ppp_constant_2021_intl_usd_10k_sq |         0.000339638 |               0.000339638 |            2.11419e-17 |       0.000145367 |             0.000145367 |          1.60191e-17 |   3236 |        135 | True     |
| country_fe_import_product_gini_level_ppp | log_population                           |         0.00334935  |               0.00334935  |            2.37657e-16 |       0.00811565  |             0.00811565  |          4.00383e-13 |   3236 |        135 | True     |
| country_fe_import_product_gini_level_ppp | oil_export_share                         |         0.0192182   |               0.0192182   |            1.21431e-16 |       0.00735508  |             0.00735508  |          6.10623e-16 |   3236 |        135 | True     |
