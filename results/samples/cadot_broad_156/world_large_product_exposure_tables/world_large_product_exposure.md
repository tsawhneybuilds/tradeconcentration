# Cadot 156 World-Product Exposure

Generated: 2026-06-19T11:10:33+00:00

## Purpose

This file compares two export-only measures against GDP size in the Cadot-style 156-country sample, 2000-2024.

1. `world_share_exposure`: country export shares weighted by inclusive world product-share rank percentiles.
2. `spearman_product_alignment`: within-country Spearman correlation between country export shares and same-year world export shares across the country's active products.

The baseline uses the full harmonized export basket. The non-commodity variant removes broad primary products from both country and world baskets, renormalizes shares, and rebuilds world product ranks in the filtered universe.

## Construction

- Country basket: LT/HGL-weighted HS1992/H0 export products built from Comtrade final annual raw files.
- Country sample: `cadot_broad_156` when requested; default script behavior remains `rd2_countries` baseline only.
- Benchmark sample: `world_broad`, inclusive same-year export totals.
- Product exclusion: HS6 `999999` is excluded before product-dependent aggregation.
- Broad-primary rule: `run_country_size_effect.classify_primary_hs6` applied to harmonized HS1992/H0 product codes and official H0 labels.

### Formulas

- Baseline exposure: `E_ct = sum_p s_cpt * R_pt`, where `R_pt` is the inclusive world product-share rank percentile.
- Non-commodity exposure: `E_ct^NC = sum_{p in NC} s_cpt^NC * R_pt^NC`.
- Non-commodity alignment: `A_ct^NC = rho_p(s_cpt^NC, w_pt^NC)` across the country's active non-commodity products.

In plain English, higher exposure means a country's export basket leans more toward products that are large in world trade. Higher alignment means the country's biggest exported products line up more closely with the products that are globally large.

## Headline Results

- Inclusive world export basket, world_share_exposure: mean Spearman 0.415, median 0.418, positive in 1.000 of years.
- Inclusive world export basket, spearman_product_alignment: mean Spearman 0.736, median 0.736, positive in 1.000 of years.
- Broad-primary-excluded non-commodity basket, world_share_exposure: mean Spearman 0.380, median 0.389, positive in 1.000 of years.
- Broad-primary-excluded non-commodity basket, spearman_product_alignment: mean Spearman 0.726, median 0.728, positive in 1.000 of years.

## Main GDP Year-FE Rows

| variant            | outcome                    |   coefficient |   std_error |     p_value |   bh_q_value |   nobs |   clusters | status   |
|:-------------------|:---------------------------|--------------:|------------:|------------:|-------------:|-------:|-----------:|:---------|
| baseline           | world_share_exposure       |     0.0166857 |  0.00315044 | 4.01507e-07 |  6.02261e-07 |   3728 |        155 | ok       |
| baseline           | spearman_product_alignment |     0.0636393 |  0.00376628 | 6.75911e-37 |  4.05547e-36 |   3728 |        155 | ok       |
| noncommodity_broad | world_share_exposure       |     0.0112001 |  0.00209908 | 3.3439e-07  |  4.01268e-07 |   3721 |        155 | ok       |
| noncommodity_broad | spearman_product_alignment |     0.064064  |  0.00382285 | 1.54483e-36 |  9.269e-36   |   3717 |        155 | ok       |

## All-Available GDP Rank-Correlation Summary

| sample_window   | variant            |   year | outcome                    |   spearman_size_outcome |   n_countries |
|:----------------|:-------------------|-------:|:---------------------------|------------------------:|--------------:|
| all_available   | baseline           |   2000 | world_share_exposure       |                0.384336 |           141 |
| all_available   | baseline           |   2000 | spearman_product_alignment |                0.732904 |           141 |
| all_available   | baseline           |   2001 | world_share_exposure       |                0.411612 |           145 |
| all_available   | baseline           |   2001 | spearman_product_alignment |                0.74134  |           145 |
| all_available   | baseline           |   2002 | world_share_exposure       |                0.41077  |           145 |
| all_available   | baseline           |   2002 | spearman_product_alignment |                0.803877 |           145 |
| all_available   | baseline           |   2003 | world_share_exposure       |                0.434716 |           148 |
| all_available   | baseline           |   2003 | spearman_product_alignment |                0.782366 |           148 |
| all_available   | baseline           |   2004 | world_share_exposure       |                0.417752 |           147 |
| all_available   | baseline           |   2004 | spearman_product_alignment |                0.795658 |           147 |
| all_available   | baseline           |   2005 | world_share_exposure       |                0.420327 |           149 |
| all_available   | baseline           |   2005 | spearman_product_alignment |                0.755393 |           149 |
| all_available   | baseline           |   2006 | world_share_exposure       |                0.40887  |           149 |
| all_available   | baseline           |   2006 | spearman_product_alignment |                0.746896 |           149 |
| all_available   | baseline           |   2007 | world_share_exposure       |                0.414512 |           152 |
| all_available   | baseline           |   2007 | spearman_product_alignment |                0.744917 |           152 |
| all_available   | baseline           |   2008 | world_share_exposure       |                0.461318 |           148 |
| all_available   | baseline           |   2008 | spearman_product_alignment |                0.766363 |           148 |
| all_available   | baseline           |   2009 | world_share_exposure       |                0.455853 |           149 |
| all_available   | baseline           |   2009 | spearman_product_alignment |                0.735846 |           149 |
| all_available   | baseline           |   2010 | world_share_exposure       |                0.446398 |           152 |
| all_available   | baseline           |   2010 | spearman_product_alignment |                0.705459 |           152 |
| all_available   | baseline           |   2011 | world_share_exposure       |                0.421311 |           150 |
| all_available   | baseline           |   2011 | spearman_product_alignment |                0.700143 |           150 |
| all_available   | baseline           |   2012 | world_share_exposure       |                0.434036 |           151 |
| all_available   | baseline           |   2012 | spearman_product_alignment |                0.708906 |           151 |
| all_available   | baseline           |   2013 | world_share_exposure       |                0.434974 |           153 |
| all_available   | baseline           |   2013 | spearman_product_alignment |                0.712228 |           153 |
| all_available   | baseline           |   2014 | world_share_exposure       |                0.4598   |           152 |
| all_available   | baseline           |   2014 | spearman_product_alignment |                0.704416 |           152 |
| all_available   | baseline           |   2015 | world_share_exposure       |                0.417721 |           152 |
| all_available   | baseline           |   2015 | spearman_product_alignment |                0.714873 |           152 |
| all_available   | baseline           |   2016 | world_share_exposure       |                0.454644 |           154 |
| all_available   | baseline           |   2016 | spearman_product_alignment |                0.739445 |           154 |
| all_available   | baseline           |   2017 | world_share_exposure       |                0.417183 |           155 |
| all_available   | baseline           |   2017 | spearman_product_alignment |                0.710937 |           155 |
| all_available   | baseline           |   2018 | world_share_exposure       |                0.465596 |           153 |
| all_available   | baseline           |   2018 | spearman_product_alignment |                0.735284 |           153 |
| all_available   | baseline           |   2019 | world_share_exposure       |                0.429925 |           153 |
| all_available   | baseline           |   2019 | spearman_product_alignment |                0.72033  |           153 |
| all_available   | baseline           |   2020 | world_share_exposure       |                0.413796 |           151 |
| all_available   | baseline           |   2020 | spearman_product_alignment |                0.737152 |           151 |
| all_available   | baseline           |   2021 | world_share_exposure       |                0.402179 |           152 |
| all_available   | baseline           |   2021 | spearman_product_alignment |                0.728197 |           152 |
| all_available   | baseline           |   2022 | world_share_exposure       |                0.341633 |           149 |
| all_available   | baseline           |   2022 | spearman_product_alignment |                0.701364 |           149 |
| all_available   | baseline           |   2023 | world_share_exposure       |                0.27583  |           148 |
| all_available   | baseline           |   2023 | spearman_product_alignment |                0.745211 |           148 |
| all_available   | baseline           |   2024 | world_share_exposure       |                0.341949 |           130 |
| all_available   | baseline           |   2024 | spearman_product_alignment |                0.741163 |           130 |
| all_available   | noncommodity_broad |   2000 | world_share_exposure       |                0.443598 |           141 |
| all_available   | noncommodity_broad |   2000 | spearman_product_alignment |                0.688548 |           141 |
| all_available   | noncommodity_broad |   2001 | world_share_exposure       |                0.337057 |           145 |
| all_available   | noncommodity_broad |   2001 | spearman_product_alignment |                0.729994 |           144 |
| all_available   | noncommodity_broad |   2002 | world_share_exposure       |                0.414687 |           145 |
| all_available   | noncommodity_broad |   2002 | spearman_product_alignment |                0.770292 |           144 |
| all_available   | noncommodity_broad |   2003 | world_share_exposure       |                0.431981 |           148 |
| all_available   | noncommodity_broad |   2003 | spearman_product_alignment |                0.741857 |           147 |
| all_available   | noncommodity_broad |   2004 | world_share_exposure       |                0.400566 |           147 |
| all_available   | noncommodity_broad |   2004 | spearman_product_alignment |                0.755363 |           147 |
| all_available   | noncommodity_broad |   2005 | world_share_exposure       |                0.397134 |           149 |
| all_available   | noncommodity_broad |   2005 | spearman_product_alignment |                0.747662 |           149 |
| all_available   | noncommodity_broad |   2006 | world_share_exposure       |                0.389149 |           149 |
| all_available   | noncommodity_broad |   2006 | spearman_product_alignment |                0.738712 |           149 |
| all_available   | noncommodity_broad |   2007 | world_share_exposure       |                0.401994 |           151 |
| all_available   | noncommodity_broad |   2007 | spearman_product_alignment |                0.745678 |           150 |
| all_available   | noncommodity_broad |   2008 | world_share_exposure       |                0.458286 |           148 |
| all_available   | noncommodity_broad |   2008 | spearman_product_alignment |                0.720819 |           148 |
| all_available   | noncommodity_broad |   2009 | world_share_exposure       |                0.379126 |           148 |
| all_available   | noncommodity_broad |   2009 | spearman_product_alignment |                0.714134 |           148 |
| all_available   | noncommodity_broad |   2010 | world_share_exposure       |                0.400167 |           151 |
| all_available   | noncommodity_broad |   2010 | spearman_product_alignment |                0.70274  |           151 |
| all_available   | noncommodity_broad |   2011 | world_share_exposure       |                0.416847 |           149 |
| all_available   | noncommodity_broad |   2011 | spearman_product_alignment |                0.691395 |           149 |
| all_available   | noncommodity_broad |   2012 | world_share_exposure       |                0.373313 |           150 |
| all_available   | noncommodity_broad |   2012 | spearman_product_alignment |                0.706415 |           150 |
| all_available   | noncommodity_broad |   2013 | world_share_exposure       |                0.360708 |           152 |
| all_available   | noncommodity_broad |   2013 | spearman_product_alignment |                0.701758 |           152 |
| all_available   | noncommodity_broad |   2014 | world_share_exposure       |                0.367354 |           151 |
| all_available   | noncommodity_broad |   2014 | spearman_product_alignment |                0.703918 |           151 |
| all_available   | noncommodity_broad |   2015 | world_share_exposure       |                0.278781 |           152 |
| all_available   | noncommodity_broad |   2015 | spearman_product_alignment |                0.705954 |           152 |
| all_available   | noncommodity_broad |   2016 | world_share_exposure       |                0.312521 |           154 |
| all_available   | noncommodity_broad |   2016 | spearman_product_alignment |                0.728231 |           154 |
| all_available   | noncommodity_broad |   2017 | world_share_exposure       |                0.342213 |           155 |
| all_available   | noncommodity_broad |   2017 | spearman_product_alignment |                0.714998 |           155 |
| all_available   | noncommodity_broad |   2018 | world_share_exposure       |                0.402869 |           153 |
| all_available   | noncommodity_broad |   2018 | spearman_product_alignment |                0.732459 |           153 |
| all_available   | noncommodity_broad |   2019 | world_share_exposure       |                0.377468 |           153 |
| all_available   | noncommodity_broad |   2019 | spearman_product_alignment |                0.713867 |           153 |
| all_available   | noncommodity_broad |   2020 | world_share_exposure       |                0.393433 |           151 |
| all_available   | noncommodity_broad |   2020 | spearman_product_alignment |                0.741826 |           151 |
| all_available   | noncommodity_broad |   2021 | world_share_exposure       |                0.347023 |           152 |
| all_available   | noncommodity_broad |   2021 | spearman_product_alignment |                0.730008 |           152 |
| all_available   | noncommodity_broad |   2022 | world_share_exposure       |                0.40234  |           149 |
| all_available   | noncommodity_broad |   2022 | spearman_product_alignment |                0.707676 |           149 |
| all_available   | noncommodity_broad |   2023 | world_share_exposure       |                0.331284 |           148 |
| all_available   | noncommodity_broad |   2023 | spearman_product_alignment |                0.750105 |           148 |
| all_available   | noncommodity_broad |   2024 | world_share_exposure       |                0.345942 |           130 |
| all_available   | noncommodity_broad |   2024 | spearman_product_alignment |                0.756971 |           130 |

## Fixed-Country 2018-2024 GDP Summary

| sample_window           | variant            | variant_label                               | outcome                    | outcome_label                         | size_variable       | size_label       |   years |   mean_spearman |   median_spearman |   min_spearman |   max_spearman |   share_positive |
|:------------------------|:-------------------|:--------------------------------------------|:---------------------------|:--------------------------------------|:--------------------|:-----------------|--------:|----------------:|------------------:|---------------:|---------------:|-----------------:|
| fixed_country_2018_2024 | baseline           | Inclusive world export basket               | spearman_product_alignment | Within-country product-rank alignment | log_gdp_current_usd | GDP, current USD |       7 |        0.724872 |          0.726817 |       0.69613  |       0.753821 |                1 |
| fixed_country_2018_2024 | baseline           | Inclusive world export basket               | world_share_exposure       | World-share percentile exposure       | log_gdp_current_usd | GDP, current USD |       7 |        0.376743 |          0.399384 |       0.282305 |       0.428882 |                1 |
| fixed_country_2018_2024 | noncommodity_broad | Broad-primary-excluded non-commodity basket | spearman_product_alignment | Within-country product-rank alignment | log_gdp_current_usd | GDP, current USD |       7 |        0.731704 |          0.726355 |       0.709505 |       0.770571 |                1 |
| fixed_country_2018_2024 | noncommodity_broad | Broad-primary-excluded non-commodity basket | world_share_exposure       | World-share percentile exposure       | log_gdp_current_usd | GDP, current USD |       7 |        0.379231 |          0.387561 |       0.330029 |       0.413579 |                1 |

## Coverage And Removed Share

| variant            | variant_label                               |   year |   countries |   countries_with_exposure |   countries_with_alignment |   median_total_exports |   median_active_products |
|:-------------------|:--------------------------------------------|-------:|------------:|--------------------------:|---------------------------:|-----------------------:|-------------------------:|
| baseline           | Inclusive world export basket               |   2000 |         142 |                       142 |                        142 |            2.71264e+09 |                   2140.5 |
| baseline           | Inclusive world export basket               |   2001 |         146 |                       146 |                        146 |            2.50823e+09 |                   2024.5 |
| baseline           | Inclusive world export basket               |   2002 |         146 |                       146 |                        146 |            3.16476e+09 |                   2135.5 |
| baseline           | Inclusive world export basket               |   2003 |         149 |                       149 |                        149 |            3.78769e+09 |                   2241   |
| baseline           | Inclusive world export basket               |   2004 |         148 |                       148 |                        148 |            4.4738e+09  |                   2366   |
| baseline           | Inclusive world export basket               |   2005 |         150 |                       150 |                        150 |            4.93306e+09 |                   2436.5 |
| baseline           | Inclusive world export basket               |   2006 |         150 |                       150 |                        150 |            6.56702e+09 |                   2538   |
| baseline           | Inclusive world export basket               |   2007 |         153 |                       153 |                        153 |            7.27401e+09 |                   2448   |
| baseline           | Inclusive world export basket               |   2008 |         149 |                       149 |                        149 |            9.74453e+09 |                   2680   |
| baseline           | Inclusive world export basket               |   2009 |         150 |                       150 |                        150 |            7.08513e+09 |                   2643   |
| baseline           | Inclusive world export basket               |   2010 |         153 |                       153 |                        153 |            8.6812e+09  |                   2536   |
| baseline           | Inclusive world export basket               |   2011 |         150 |                       150 |                        150 |            1.13891e+10 |                   2631   |
| baseline           | Inclusive world export basket               |   2012 |         152 |                       152 |                        152 |            1.15935e+10 |                   2711   |
| baseline           | Inclusive world export basket               |   2013 |         154 |                       154 |                        154 |            1.25154e+10 |                   2767   |
| baseline           | Inclusive world export basket               |   2014 |         153 |                       153 |                        153 |            1.3033e+10  |                   2769   |
| baseline           | Inclusive world export basket               |   2015 |         153 |                       153 |                        153 |            1.07418e+10 |                   2761   |
| baseline           | Inclusive world export basket               |   2016 |         155 |                       155 |                        155 |            1.05382e+10 |                   2783   |
| baseline           | Inclusive world export basket               |   2017 |         156 |                       156 |                        156 |            1.10949e+10 |                   2814.5 |
| baseline           | Inclusive world export basket               |   2018 |         154 |                       154 |                        154 |            1.10576e+10 |                   2844   |
| baseline           | Inclusive world export basket               |   2019 |         154 |                       154 |                        154 |            1.13706e+10 |                   2858.5 |
| baseline           | Inclusive world export basket               |   2020 |         152 |                       152 |                        152 |            9.251e+09   |                   2781   |
| baseline           | Inclusive world export basket               |   2021 |         153 |                       153 |                        153 |            1.33312e+10 |                   2798   |
| baseline           | Inclusive world export basket               |   2022 |         150 |                       150 |                        150 |            1.51489e+10 |                   2999.5 |
| baseline           | Inclusive world export basket               |   2023 |         149 |                       149 |                        149 |            1.26939e+10 |                   3067   |
| baseline           | Inclusive world export basket               |   2024 |         132 |                       132 |                        132 |            1.9928e+10  |                   3322   |
| noncommodity_broad | Broad-primary-excluded non-commodity basket |   2000 |         142 |                       142 |                        142 |            1.05974e+09 |                   1847.5 |
| noncommodity_broad | Broad-primary-excluded non-commodity basket |   2001 |         146 |                       146 |                        145 |            9.84069e+08 |                   1701   |
| noncommodity_broad | Broad-primary-excluded non-commodity basket |   2002 |         146 |                       146 |                        145 |            1.23417e+09 |                   1791   |
| noncommodity_broad | Broad-primary-excluded non-commodity basket |   2003 |         149 |                       149 |                        148 |            1.34174e+09 |                   1796   |
| noncommodity_broad | Broad-primary-excluded non-commodity basket |   2004 |         148 |                       148 |                        148 |            1.44791e+09 |                   2004.5 |
| noncommodity_broad | Broad-primary-excluded non-commodity basket |   2005 |         150 |                       150 |                        150 |            1.89181e+09 |                   2071   |
| noncommodity_broad | Broad-primary-excluded non-commodity basket |   2006 |         150 |                       150 |                        150 |            2.13735e+09 |                   2234.5 |
| noncommodity_broad | Broad-primary-excluded non-commodity basket |   2007 |         153 |                       152 |                        151 |            2.56669e+09 |                   2066   |
| noncommodity_broad | Broad-primary-excluded non-commodity basket |   2008 |         149 |                       149 |                        149 |            3.50549e+09 |                   2277   |
| noncommodity_broad | Broad-primary-excluded non-commodity basket |   2009 |         150 |                       149 |                        149 |            2.36411e+09 |                   2198   |
| noncommodity_broad | Broad-primary-excluded non-commodity basket |   2010 |         153 |                       152 |                        152 |            2.88404e+09 |                   2154   |
| noncommodity_broad | Broad-primary-excluded non-commodity basket |   2011 |         150 |                       149 |                        149 |            3.75292e+09 |                   2209   |
| noncommodity_broad | Broad-primary-excluded non-commodity basket |   2012 |         152 |                       151 |                        151 |            3.41968e+09 |                   2245.5 |
| noncommodity_broad | Broad-primary-excluded non-commodity basket |   2013 |         154 |                       153 |                        153 |            3.96924e+09 |                   2326.5 |
| noncommodity_broad | Broad-primary-excluded non-commodity basket |   2014 |         153 |                       152 |                        152 |            5.01916e+09 |                   2304   |
| noncommodity_broad | Broad-primary-excluded non-commodity basket |   2015 |         153 |                       153 |                        153 |            4.67027e+09 |                   2296   |
| noncommodity_broad | Broad-primary-excluded non-commodity basket |   2016 |         155 |                       155 |                        155 |            4.11077e+09 |                   2296   |
| noncommodity_broad | Broad-primary-excluded non-commodity basket |   2017 |         156 |                       156 |                        156 |            3.38121e+09 |                   2330.5 |
| noncommodity_broad | Broad-primary-excluded non-commodity basket |   2018 |         154 |                       154 |                        154 |            4.05642e+09 |                   2299.5 |
| noncommodity_broad | Broad-primary-excluded non-commodity basket |   2019 |         154 |                       154 |                        154 |            5.05623e+09 |                   2412.5 |
| noncommodity_broad | Broad-primary-excluded non-commodity basket |   2020 |         152 |                       152 |                        152 |            3.99125e+09 |                   2364.5 |
| noncommodity_broad | Broad-primary-excluded non-commodity basket |   2021 |         153 |                       153 |                        153 |            4.85953e+09 |                   2375   |
| noncommodity_broad | Broad-primary-excluded non-commodity basket |   2022 |         150 |                       150 |                        150 |            4.63327e+09 |                   2569   |
| noncommodity_broad | Broad-primary-excluded non-commodity basket |   2023 |         149 |                       149 |                        149 |            4.4533e+09  |                   2612   |
| noncommodity_broad | Broad-primary-excluded non-commodity basket |   2024 |         132 |                       132 |                        132 |            7.61311e+09 |                   2833   |

| country   | iso3   |   reporter_code |   year | flow    |   baseline_total_exports |   noncommodity_total_exports |   broad_primary_exports_removed |   broad_primary_share_removed |   baseline_active_products |   noncommodity_active_products |   baseline_world_active_products |   noncommodity_world_active_products |   delta_world_share_exposure |   delta_spearman_product_alignment |
|:----------|:-------|----------------:|-------:|:--------|-------------------------:|-----------------------------:|--------------------------------:|------------------------------:|---------------------------:|-------------------------------:|---------------------------------:|-------------------------------------:|-----------------------------:|-----------------------------------:|
| Albania   | ALB    |               8 |   2000 | Exports |              2.61476e+08 |                  2.19491e+08 |                     4.19849e+07 |                      0.160569 |                       1055 |                            846 |                             5035 |                                 4076 |                 -0.000489848 |                       -0.00765244  |
| Albania   | ALB    |               8 |   2001 | Exports |              3.04931e+08 |                  2.59543e+08 |                     4.53874e+07 |                      0.148845 |                       1087 |                            862 |                             5033 |                                 4073 |                 -0.0055667   |                        0.000468901 |
| Albania   | ALB    |               8 |   2002 | Exports |              3.30241e+08 |                  2.75464e+08 |                     5.47772e+07 |                      0.16587  |                       1104 |                            909 |                             5032 |                                 4073 |                  0.00785878  |                       -0.00301991  |
| Albania   | ALB    |               8 |   2003 | Exports |              4.47221e+08 |                  3.74977e+08 |                     7.22438e+07 |                      0.161539 |                       1268 |                           1044 |                             5035 |                                 4074 |                  0.00414915  |                       -0.000786935 |
| Albania   | ALB    |               8 |   2004 | Exports |              6.02653e+08 |                  5.00202e+08 |                     1.02452e+08 |                      0.170001 |                       1338 |                           1089 |                             5027 |                                 4074 |                 -0.00542026  |                       -0.0246959   |
| Albania   | ALB    |               8 |   2005 | Exports |              6.58233e+08 |                  5.27245e+08 |                     1.30988e+08 |                      0.199    |                       1294 |                           1074 |                             5034 |                                 4074 |                 -0.0094382   |                       -0.00885122  |
| Albania   | ALB    |               8 |   2006 | Exports |              7.9263e+08  |                  6.17246e+08 |                     1.75383e+08 |                      0.221268 |                       1316 |                           1080 |                             5031 |                                 4074 |                 -0.0143413   |                       -0.00301331  |
| Albania   | ALB    |               8 |   2007 | Exports |              1.07769e+09 |                  7.86985e+08 |                     2.90705e+08 |                      0.269749 |                       1308 |                           1072 |                             5019 |                                 4074 |                 -0.0190842   |                       -0.0227289   |
| Albania   | ALB    |               8 |   2008 | Exports |              1.3521e+09  |                  9.33927e+08 |                     4.1817e+08  |                      0.309275 |                       1465 |                           1221 |                             5015 |                                 4072 |                 -0.0254433   |                        0.00379149  |
| Albania   | ALB    |               8 |   2009 | Exports |              1.08746e+09 |                  7.81719e+08 |                     3.05737e+08 |                      0.281149 |                       1669 |                           1415 |                             5011 |                                 4070 |                 -0.0237978   |                       -0.0030918   |
| Albania   | ALB    |               8 |   2010 | Exports |              1.54673e+09 |                  9.30181e+08 |                     6.16549e+08 |                      0.398614 |                       1713 |                           1431 |                             5010 |                                 4069 |                 -0.0396805   |                       -0.00958917  |
| Albania   | ALB    |               8 |   2011 | Exports |              1.94629e+09 |                  1.1249e+09  |                     8.21382e+08 |                      0.422025 |                       1781 |                           1497 |                             5011 |                                 4071 |                 -0.0490468   |                       -0.0134666   |
| Albania   | ALB    |               8 |   2012 | Exports |              1.96346e+09 |                  1.03346e+09 |                     9.29992e+08 |                      0.47365  |                       1895 |                           1579 |                             5007 |                                 4067 |                 -0.0548732   |                        0.0145696   |
| Albania   | ALB    |               8 |   2013 | Exports |              2.33e+09    |                  1.188e+09   |                     1.142e+09   |                      0.490129 |                       1884 |                           1593 |                             5006 |                                 4066 |                 -0.0556881   |                        0.0211516   |
| Albania   | ALB    |               8 |   2014 | Exports |              1.01568e+09 |                  7.95154e+08 |                     2.2053e+08  |                      0.217125 |                        489 |                            411 |                             5003 |                                 4063 |                  0.00371316  |                        0.0090944   |
| Albania   | ALB    |               8 |   2015 | Exports |              1.48519e+09 |                  9.86298e+08 |                     4.98891e+08 |                      0.335911 |                        774 |                            649 |                             5002 |                                 4062 |                 -0.0185959   |                       -0.0139997   |
| Albania   | ALB    |               8 |   2016 | Exports |              1.90272e+09 |                  1.28146e+09 |                     6.21259e+08 |                      0.32651  |                       1055 |                            877 |                             5003 |                                 4064 |                 -0.0154996   |                       -0.00821116  |
| Albania   | ALB    |               8 |   2017 | Exports |              1.21668e+09 |                  9.62809e+08 |                     2.53874e+08 |                      0.20866  |                        461 |                            383 |                             4994 |                                 4055 |                  0.00208893  |                       -0.0424708   |
| Albania   | ALB    |               8 |   2018 | Exports |              1.1983e+09  |                  9.49088e+08 |                     2.49209e+08 |                      0.20797  |                        486 |                            402 |                             4990 |                                 4051 |                 -0.00631908  |                       -0.036789    |
| Albania   | ALB    |               8 |   2019 | Exports |              1.2691e+09  |                  1.02807e+09 |                     2.41031e+08 |                      0.189922 |                        485 |                            405 |                             4987 |                                 4048 |                  0.00147343  |                       -0.0426135   |
| Albania   | ALB    |               8 |   2020 | Exports |              1.35759e+09 |                  1.01157e+09 |                     3.46027e+08 |                      0.254882 |                        543 |                            452 |                             4982 |                                 4043 |                 -0.00736403  |                       -0.0112922   |
| Albania   | ALB    |               8 |   2021 | Exports |              1.4719e+09  |                  1.15236e+09 |                     3.19546e+08 |                      0.217097 |                        558 |                            474 |                             4982 |                                 4043 |                 -0.00374188  |                        0.00875216  |
| Albania   | ALB    |               8 |   2022 | Exports |              3.34528e+08 |                  6.80937e+07 |                     2.66434e+08 |                      0.796448 |                        113 |                             75 |                             4988 |                                 4049 |                 -0.031538    |                        0.00711624  |
| Albania   | ALB    |               8 |   2023 | Exports |              3.08951e+09 |                  2.10594e+09 |                     9.83571e+08 |                      0.318358 |                        966 |                            836 |                             4982 |                                 4043 |                 -0.0202155   |                       -0.0145922   |
| Albania   | ALB    |               8 |   2024 | Exports |              2.40179e+09 |                  1.64891e+09 |                     7.52872e+08 |                      0.313464 |                        761 |                            654 |                             4982 |                                 4043 |                 -0.019601    |                       -0.00717516  |
| Algeria   | DZA    |              12 |   2000 | Exports |              2.20313e+10 |                  3.20807e+08 |                     2.17105e+10 |                      0.985439 |                       1140 |                           1010 |                             5035 |                                 4076 |                 -0.278244    |                        0.0339131   |
| Algeria   | DZA    |              12 |   2001 | Exports |              1.91476e+10 |                  3.60726e+08 |                     1.87869e+10 |                      0.981161 |                        793 |                            658 |                             5033 |                                 4073 |                 -0.284408    |                        0.0354517   |
| Algeria   | DZA    |              12 |   2002 | Exports |              1.88324e+10 |                  4.7196e+08  |                     1.83604e+10 |                      0.974939 |                       1188 |                            949 |                             5032 |                                 4073 |                 -0.330935    |                       -0.000723145 |
| Algeria   | DZA    |              12 |   2003 | Exports |              2.46537e+10 |                  3.39191e+08 |                     2.43145e+10 |                      0.986242 |                       1071 |                            835 |                             5035 |                                 4074 |                 -0.380339    |                       -0.0131377   |
| Algeria   | DZA    |              12 |   2004 | Exports |              3.20768e+10 |                  3.85943e+08 |                     3.16908e+10 |                      0.987968 |                        834 |                            652 |                             5027 |                                 4074 |                 -0.369733    |                       -0.00200925  |
| Algeria   | DZA    |              12 |   2005 | Exports |              4.60017e+10 |                  4.44753e+08 |                     4.5557e+10  |                      0.990332 |                       1003 |                            819 |                             5034 |                                 4074 |                 -0.365149    |                       -0.0115845   |
| Algeria   | DZA    |              12 |   2006 | Exports |              5.46127e+10 |                  5.79757e+08 |                     5.40329e+10 |                      0.989384 |                       1084 |                            826 |                             5031 |                                 4074 |                 -0.30211     |                       -0.00898685  |
| Algeria   | DZA    |              12 |   2007 | Exports |              6.0163e+10  |                  5.73711e+08 |                     5.95893e+10 |                      0.990464 |                       1193 |                            921 |                             5019 |                                 4074 |                 -0.306236    |                        0.0180703   |
| Algeria   | DZA    |              12 |   2008 | Exports |              7.92976e+10 |                  7.94753e+08 |                     7.85028e+10 |                      0.989978 |                       1079 |                            855 |                             5015 |                                 4072 |                 -0.292756    |                        0.0276557   |
| Algeria   | DZA    |              12 |   2009 | Exports |              4.51939e+10 |                  4.20333e+08 |                     4.47736e+10 |                      0.990699 |                       1028 |                            811 |                             5011 |                                 4070 |                 -0.331826    |                        0.0224584   |
| Algeria   | DZA    |              12 |   2010 | Exports |              5.7051e+10  |                  4.79637e+08 |                     5.65713e+10 |                      0.991593 |                        914 |                            710 |                             5010 |                                 4069 |                 -0.38849     |                       -0.0221185   |
| Algeria   | DZA    |              12 |   2011 | Exports |              7.34363e+10 |                  6.75731e+08 |                     7.27606e+10 |                      0.990798 |                        802 |                            611 |                             5011 |                                 4071 |                 -0.304787    |                       -0.0286416   |
| Algeria   | DZA    |              12 |   2012 | Exports |              7.18657e+10 |                  6.78384e+08 |                     7.11874e+10 |                      0.99056  |                        926 |                            731 |                             5007 |                                 4067 |                 -0.279407    |                        0.0147187   |
| Algeria   | DZA    |              12 |   2013 | Exports |              6.59981e+10 |                  6.15014e+08 |                     6.53831e+10 |                      0.990681 |                        946 |                            751 |                             5006 |                                 4066 |                 -0.144774    |                        0.000381376 |
| Algeria   | DZA    |              12 |   2014 | Exports |              6.03877e+10 |                  1.24793e+09 |                     5.91398e+10 |                      0.979335 |                        997 |                            796 |                             5003 |                                 4063 |                 -0.133733    |                       -0.00303321  |

## Validation Checks

| check                                     | passed   | value              | expected   | detail                                                                               |
|:------------------------------------------|:---------|:-------------------|:-----------|:-------------------------------------------------------------------------------------|
| expected_reporters                        | True     | 156                | 156        | Unique reporters represented in the final panel.                                     |
| year_min                                  | True     | 2000               | 2000       | Minimum panel year.                                                                  |
| year_max                                  | True     | 2024               | 2024       | Maximum panel year.                                                                  |
| unique_reporter_year_variant_keys         | True     | 0                  | 0          | Duplicate reporter-year-variant keys.                                                |
| no_country_product_999999                 | True     | 0                  | 0          | Country product input should already exclude HS6 999999 before aggregation.          |
| no_world_product_999999                   | True     | 0                  | 0          | World product input should already exclude HS6 999999 before aggregation.            |
| hs1992_labels_present                     | True     | 0                  | 0          | All harmonized products should have plain-English HS1992/H0 labels.                  |
| exposure_in_unit_interval                 | True     | 0                  | 0          | Exposure must stay in [0,1].                                                         |
| alignment_in_closed_interval              | True     | 0                  | 0          | Within-country alignment must stay in [-1,1].                                        |
| zero_unmatched_country_share              | True     | 0.0                | 0.0        | Country product baskets must match the filtered world basket exactly.                |
| noncommodity_country_has_no_primary_broad | True     | 0                  | 0          | No broad-primary product should remain in the non-commodity country basket.          |
| noncommodity_world_has_no_primary_broad   | True     | 0                  | 0          | No broad-primary product should remain in the non-commodity world basket.            |
| noncommodity_years_covered                | True     | 2000-2024          | 2000-2024  | Non-commodity yearly coverage window.                                                |
| fixed_country_window_nonempty             | True     | 128                | >0         | Countries observed in every year from 2018 through 2024 for every requested variant. |
| world_bank_control_row_coverage           | True     | 0.9933386624034106 | 0.8        | Share of final panel rows with complete GDP and population controls.                 |

## Outputs

- processed_panel: `data/processed/samples/cadot_broad_156/world_large_product_exposure_panel.parquet`
- panel_csv: `results/samples/cadot_broad_156/world_large_product_exposure_tables/world_large_product_exposure_panel.csv`
- yearly_spearman: `results/samples/cadot_broad_156/world_large_product_exposure_tables/world_large_product_exposure_yearly_spearman.csv`
- spearman_summary: `results/samples/cadot_broad_156/world_large_product_exposure_tables/world_large_product_exposure_spearman_summary.csv`
- models: `results/samples/cadot_broad_156/world_large_product_exposure_tables/world_large_product_exposure_models.csv`
- diagnostics: `results/samples/cadot_broad_156/world_large_product_exposure_tables/world_large_product_exposure_diagnostics.csv`
- validation_checks: `results/samples/cadot_broad_156/world_large_product_exposure_tables/world_large_product_exposure_validation_checks.csv`
- reporter_coverage: `results/samples/cadot_broad_156/world_large_product_exposure_tables/world_large_product_exposure_reporter_coverage.csv`
- fixed_country_yearly: `results/samples/cadot_broad_156/world_large_product_exposure_tables/world_large_product_exposure_fixed_country_2018_2024.csv`
- fixed_country_summary: `results/samples/cadot_broad_156/world_large_product_exposure_tables/world_large_product_exposure_fixed_country_2018_2024_summary.csv`
- leave_one_country_out: `results/samples/cadot_broad_156/world_large_product_exposure_tables/world_large_product_exposure_leave_one_country_out.csv`
- variant_comparison: `results/samples/cadot_broad_156/world_large_product_exposure_tables/world_large_product_exposure_variant_comparison.csv`
- country_commodity_shares: `results/samples/cadot_broad_156/world_large_product_exposure_tables/world_large_product_exposure_country_commodity_shares.csv`
- top_change_contributors: `results/samples/cadot_broad_156/world_large_product_exposure_tables/world_large_product_exposure_top_change_contributors.csv`
- product_mapping: `results/samples/cadot_broad_156/world_large_product_exposure_tables/world_large_product_exposure_product_mapping.csv`
- manifest: `results/samples/cadot_broad_156/world_large_product_exposure_tables/run_manifest_world_large_product_exposure.json`
- memo: `results/samples/cadot_broad_156/world_large_product_exposure_tables/world_large_product_exposure.md`
- gdp_product_alignment_scatter: `results/samples/cadot_broad_156/country_size_effect_figures/gdp_product_alignment_scatter.png`

## Manifest

```json
{
  "alignment_definition": "Within-country Spearman correlation across active harmonized export products only.",
  "benchmark_sample": "world_broad",
  "controls": {
    "control_source": "World Bank GDP current USD and population",
    "controls_cache": "data/processed/samples/cadot_broad_156/world_large_product_exposure_world_bank_controls.csv",
    "controls_complete_rows": 7456,
    "controls_complete_share": 0.9933386624034106,
    "controls_missing_examples": [
      {
        "country": "Lebanon",
        "gdp_current_usd": NaN,
        "iso3": "LBN",
        "population": 5805962.0,
        "year": 2024
      },
      {
        "country": "Lebanon",
        "gdp_current_usd": NaN,
        "iso3": "LBN",
        "population": 5805962.0,
        "year": 2024
      },
      {
        "country": "Montserrat",
        "gdp_current_usd": NaN,
        "iso3": "MSR",
        "population": NaN,
        "year": 2000
      },
      {
        "country": "Montserrat",
        "gdp_current_usd": NaN,
        "iso3": "MSR",
        "population": NaN,
        "year": 2000
      },
      {
        "country": "Montserrat",
        "gdp_current_usd": NaN,
        "iso3": "MSR",
        "population": NaN,
        "year": 2001
      },
      {
        "country": "Montserrat",
        "gdp_current_usd": NaN,
        "iso3": "MSR",
        "population": NaN,
        "year": 2001
      },
      {
        "country": "Montserrat",
        "gdp_current_usd": NaN,
        "iso3": "MSR",
        "population": NaN,
        "year": 2002
      },
      {
        "country": "Montserrat",
        "gdp_current_usd": NaN,
        "iso3": "MSR",
        "population": NaN,
        "year": 2002
      },
      {
        "country": "Montserrat",
        "gdp_current_usd": NaN,
        "iso3": "MSR",
        "population": NaN,
        "year": 2003
      },
      {
        "country": "Montserrat",
        "gdp_current_usd": NaN,
        "iso3": "MSR",
        "population": NaN,
        "year": 2003
      }
    ],
    "controls_missing_rows": 50,
    "log_gdp_per_capita_formula": "log_gdp_current_usd - log_population"
  },
  "country_sample": "cadot_broad_156",
  "created_at_utc": "2026-06-19T11:10:33+00:00",
  "end_year": 2024,
  "fixed_country_robustness": {
    "fixed_country_codes": [
      8,
      24,
      28,
      31,
      32,
      36,
      40,
      44,
      48,
      51,
      52,
      56,
      60,
      68,
      70,
      76,
      84,
      96,
      100,
      116,
      124,
      132,
      140,
      152,
      156,
      170,
      188,
      191,
      196,
      203,
      204,
      208,
      214,
      218,
      222,
      233,
      242,
      246,
      251,
      258,
      268,
      270,
      276,
      300,
      308,
      320,
      328,
      344,
      348,
      352,
      360,
      372,
      376,
      380,
      384,
      388,
      392,
      398,
      400,
      404,
      410,
      414,
      417,
      422,
      426,
      428,
      440,
      442,
      446,
      450,
      454,
      458,
      462,
      470,
      478,
      480,
      484,
      498,
      499,
      500,
      504,
      508,
      512,
      516,
      528,
      554,
      558,
      562,
      566,
      579,
      586,
      591,
      600,
      604,
      608,
      616,
      620,
      634,
      642,
      682,
      686,
      688,
      690,
      699,
      702,
      703,
      705,
      710,
      716,
      724,
      740,
      752,
      757,
      764,
      768,
      780,
      788,
      792,
      800,
      804,
      807,
      818,
      826,
      834,
      842,
      854,
      858,
      894
    ],
    "fixed_country_count": 128,
    "fixed_country_window_end": 2024,
    "fixed_country_window_start": 2018
  },
  "flow": "Exports",
  "leave_one_out": false,
  "outputs": {
    "country_commodity_shares": "results/samples/cadot_broad_156/world_large_product_exposure_tables/world_large_product_exposure_country_commodity_shares.csv",
    "diagnostics": "results/samples/cadot_broad_156/world_large_product_exposure_tables/world_large_product_exposure_diagnostics.csv",
    "fixed_country_summary": "results/samples/cadot_broad_156/world_large_product_exposure_tables/world_large_product_exposure_fixed_country_2018_2024_summary.csv",
    "fixed_country_yearly": "results/samples/cadot_broad_156/world_large_product_exposure_tables/world_large_product_exposure_fixed_country_2018_2024.csv",
    "gdp_product_alignment_scatter": "results/samples/cadot_broad_156/country_size_effect_figures/gdp_product_alignment_scatter.png",
    "leave_one_country_out": "results/samples/cadot_broad_156/world_large_product_exposure_tables/world_large_product_exposure_leave_one_country_out.csv",
    "memo": "results/samples/cadot_broad_156/world_large_product_exposure_tables/world_large_product_exposure.md",
    "models": "results/samples/cadot_broad_156/world_large_product_exposure_tables/world_large_product_exposure_models.csv",
    "panel_csv": "results/samples/cadot_broad_156/world_large_product_exposure_tables/world_large_product_exposure_panel.csv",
    "processed_panel": "data/processed/samples/cadot_broad_156/world_large_product_exposure_panel.parquet",
    "product_mapping": "results/samples/cadot_broad_156/world_large_product_exposure_tables/world_large_product_exposure_product_mapping.csv",
    "reporter_coverage": "results/samples/cadot_broad_156/world_large_product_exposure_tables/world_large_product_exposure_reporter_coverage.csv",
    "spearman_summary": "results/samples/cadot_broad_156/world_large_product_exposure_tables/world_large_product_exposure_spearman_summary.csv",
    "top_change_contributors": "results/samples/cadot_broad_156/world_large_product_exposure_tables/world_large_product_exposure_top_change_contributors.csv",
    "validation_checks": "results/samples/cadot_broad_156/world_large_product_exposure_tables/world_large_product_exposure_validation_checks.csv",
    "variant_comparison": "results/samples/cadot_broad_156/world_large_product_exposure_tables/world_large_product_exposure_variant_comparison.csv",
    "yearly_spearman": "results/samples/cadot_broad_156/world_large_product_exposure_tables/world_large_product_exposure_yearly_spearman.csv"
  },
  "primary_classifier": {
    "classification_code": "H0",
    "definition": "Broad primary includes raw agriculture, ores/minerals, fuels and refining, forestry, precious metals, and first-stage food/basic-metal processing.",
    "label_source": "data/raw/classifications/H0.json",
    "source_function": "run_country_size_effect.classify_primary_hs6"
  },
  "product_id_mode": "harmonized_hs6_family",
  "product_inputs": {
    "benchmark_conversion_diagnostics": null,
    "country_conversion_diagnostics": null,
    "country_product": "data/processed/samples/cadot_broad_156/world_relative_product_gini_harmonized_hs6_family_cadot_broad_156_product_exports.parquet",
    "source": "existing_product_inputs",
    "world_product": "data/processed/samples/world_broad/world_relative_product_gini_harmonized_hs6_family_world_product_exports.parquet"
  },
  "size_variable_headline": "log_gdp_current_usd",
  "start_year": 2000,
  "variant_labels": {
    "baseline": "Inclusive world export basket",
    "noncommodity_broad": "Broad-primary-excluded non-commodity basket"
  },
  "variants": [
    "baseline",
    "noncommodity_broad"
  ],
  "world_basket": "inclusive_world_exports"
}
```
