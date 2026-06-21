# Exercise 1: Top-5 Product And Partner Concentration

This memo reports exact top-five product and partner shares by country-year-flow.

## Outputs

- Top-five item table: `results/exercise_01_tables/top5_trade_concentration_items.csv`
- Top-five country-year summary: `results/exercise_01_tables/top5_trade_concentration_summary.csv`
- Latest-year top-five item table: `results/exercise_01_tables/top5_trade_concentration_latest_items.csv`
- Latest-year item-frequency table: `results/exercise_01_tables/top5_item_frequency_latest.csv`
- Latest-year item leave-one-out table: `results/exercise_01_tables/top5_item_leave_one_out_latest.csv`
- Cumulative histogram: `results/exercise_01_figures/top5_cumulative_share_histograms.png`
- Rank-share histogram: `results/exercise_01_figures/top5_rank_share_histograms.png`
- Item-frequency histogram: `results/exercise_01_figures/top5_item_frequency_latest_histograms.png`
- Leave-one-out share-of-Gini histogram, all reporters: `results/exercise_01_figures/top5_item_leave_one_out_latest_all_reporters.png`
- Leave-one-out share-of-Gini histogram, top-five reporters only: `results/exercise_01_figures/top5_item_leave_one_out_latest_top5_reporters.png`

## Median Shares Across All Country-Years

| flow    | dimension   |   median_cumulative_top_5_share |   median_top_1_share |   median_gini |   observations |
|:--------|:------------|--------------------------------:|---------------------:|--------------:|---------------:|
| Exports | partner     |                           0.529 |                0.204 |         0.897 |           1128 |
| Exports | product     |                           0.183 |                0.060 |         0.907 |           1128 |
| Imports | partner     |                           0.514 |                0.188 |         0.901 |           1130 |
| Imports | product     |                           0.157 |                0.059 |         0.854 |           1130 |

## Latest-Year Median Shares

| flow    | dimension   |   latest_median_cumulative_top_5_share |   latest_observations |
|:--------|:------------|---------------------------------------:|----------------------:|
| Exports | partner     |                                  0.507 |                    33 |
| Exports | product     |                                  0.183 |                    33 |
| Imports | partner     |                                  0.490 |                    33 |
| Imports | product     |                                  0.150 |                    33 |

## Validation

- Exact partner cumulative top-five shares were compared with the baseline `top_5_partner_share`: median absolute difference `0.000e+00`, 99th percentile `2.220e-16`, max `3.331e-16`.

## Latest-Year Most Common Top-Five Items

Counts are the number of reporter countries whose own latest-year top five includes the item. Partner charts exclude non-country reporting buckets such as `Areas, nes`; product charts exclude HS `999999`.

| flow    | dimension   | item_name                                                                                      |   reporter_count |   mean_rank |   median_share |
|:--------|:------------|:-----------------------------------------------------------------------------------------------|-----------------:|------------:|---------------:|
| Exports | partner     | USA (USA)                                                                                      |               24 |       2.208 |          0.110 |
| Exports | partner     | Germany (DEU)                                                                                  |               20 |       1.550 |          0.142 |
| Exports | partner     | Netherlands (NLD)                                                                              |               15 |       3.333 |          0.067 |
| Exports | partner     | China (CHN)                                                                                    |               14 |       2.786 |          0.067 |
| Exports | partner     | United Kingdom (GBR)                                                                           |               13 |       3.462 |          0.063 |
| Exports | partner     | France (FRA)                                                                                   |               10 |       2.900 |          0.074 |
| Exports | partner     | Italy (ITA)                                                                                    |                7 |       3.429 |          0.061 |
| Exports | partner     | Poland (POL)                                                                                   |                6 |       4.167 |          0.059 |
| Exports | product     | Packaged medicaments                                                                           |               14 |       2.286 |          0.035 |
| Exports | product     | Refined petroleum oils                                                                         |               13 |       2.077 |          0.043 |
| Exports | product     | Petroleum oils and oils from bituminous minerals, not containing biodiesel, not crude, not...  |                8 |       3.625 |          0.032 |
| Exports | product     | Unwrought non-monetary gold                                                                    |                7 |       3.000 |          0.037 |
| Exports | product     | Passenger cars, medium gasoline                                                                |                7 |       2.286 |          0.031 |
| Exports | product     | Blood, human or animal, antisera, other blood fractions and immunological products:...         |                7 |       3.143 |          0.031 |
| Exports | product     | Crude petroleum oil                                                                            |                6 |       1.667 |          0.159 |
| Exports | product     | Vehicles: with both spark-ignition internal combustion piston engine and electric motor for... |                5 |       3.000 |          0.023 |
| Imports | partner     | China (CHN)                                                                                    |               29 |       2.034 |          0.118 |
| Imports | partner     | USA (USA)                                                                                      |               26 |       3.115 |          0.072 |
| Imports | partner     | Germany (DEU)                                                                                  |               24 |       1.708 |          0.136 |
| Imports | partner     | Italy (ITA)                                                                                    |                8 |       4.125 |          0.068 |
| Imports | partner     | Netherlands (NLD)                                                                              |                7 |       3.286 |          0.067 |
| Imports | partner     | France (FRA)                                                                                   |                7 |       3.571 |          0.085 |
| Imports | partner     | Japan (JPN)                                                                                    |                6 |       4.000 |          0.053 |
| Imports | partner     | Rep. of Korea (KOR)                                                                            |                5 |       3.800 |          0.048 |
| Imports | product     | Packaged medicaments                                                                           |               22 |       3.364 |          0.020 |
| Imports | product     | Crude petroleum oil                                                                            |               21 |       1.476 |          0.044 |
| Imports | product     | Refined petroleum oils                                                                         |               18 |       2.722 |          0.027 |
| Imports | product     | Petroleum gases and other gaseous hydrocarbons: in gaseous state, natural gas                  |                8 |       3.375 |          0.024 |
| Imports | product     | Vehicles: with only electric motor for propulsion                                              |                8 |       3.375 |          0.024 |
| Imports | product     | Unwrought non-monetary gold                                                                    |                6 |       2.000 |          0.055 |
| Imports | product     | Liquefied natural gas                                                                          |                6 |       3.667 |          0.020 |
| Imports | product     | Petroleum oils and oils from bituminous minerals, not containing biodiesel, not crude, not...  |                6 |       4.167 |          0.022 |

## Latest-Year Mean Leave-One-Out Contributions

`mean_loo_gini_contribution_share_all_reporters` first computes `(full_gini - gini_without_item) / full_gini` inside each latest reporter country, then averages those country-level ratios across all latest reporters. `mean_loo_gini_contribution_share_top5_reporters` averages the same country-level ratio only where the item is in that reporter's own top five. Positive values mean removing the item lowers Gini, so the item raises concentration as a share of the country's own Gini.

| flow    | dimension   | item_name                                                                                      |   top5_reporter_count |   mean_loo_gini_contribution_share_all_reporters |   mean_loo_gini_contribution_share_top5_reporters |
|:--------|:------------|:-----------------------------------------------------------------------------------------------|----------------------:|-------------------------------------------------:|--------------------------------------------------:|
| Exports | partner     | USA (USA)                                                                                      |                    24 |                                           0.0112 |                                            0.0161 |
| Exports | partner     | Mexico (MEX)                                                                                   |                     1 |                                          -0.0010 |                                            0.0153 |
| Exports | partner     | Germany (DEU)                                                                                  |                    20 |                                           0.0066 |                                            0.0121 |
| Exports | partner     | United Arab Emirates (ARE)                                                                     |                     1 |                                          -0.0013 |                                            0.0093 |
| Exports | partner     | China (CHN)                                                                                    |                    14 |                                           0.0026 |                                            0.0090 |
| Exports | partner     | Canada (CAN)                                                                                   |                     2 |                                          -0.0013 |                                            0.0062 |
| Exports | partner     | Australia (AUS)                                                                                |                     1 |                                          -0.0012 |                                            0.0056 |
| Exports | partner     | Portugal (PRT)                                                                                 |                     1 |                                          -0.0011 |                                            0.0039 |
| Exports | product     | Crude petroleum oil                                                                            |                     6 |                                           0.0017 |                                            0.0086 |
| Exports | product     | Metals: gold, semi-manufactured                                                                |                     3 |                                           0.0006 |                                            0.0063 |
| Exports | product     | Petroleum gases and other gaseous hydrocarbons: in gaseous state, natural gas                  |                     2 |                                           0.0005 |                                            0.0057 |
| Exports | product     | Refined petroleum oils                                                                         |                    13 |                                           0.0024 |                                            0.0054 |
| Exports | product     | Medicaments: containing hormones (but not insulin), adrenal cortex hormones or antibiotics,... |                     1 |                                           0.0002 |                                            0.0053 |
| Exports | product     | Units of automatic data processing machines: processing units other than those of item no....  |                     3 |                                           0.0005 |                                            0.0052 |
| Exports | product     | Electronic integrated circuits: memories                                                       |                     2 |                                           0.0003 |                                            0.0052 |
| Exports | product     | Portable computers/laptops                                                                     |                     1 |                                           0.0002 |                                            0.0049 |
| Imports | partner     | China (CHN)                                                                                    |                    29 |                                           0.0075 |                                            0.0087 |
| Imports | partner     | Germany (DEU)                                                                                  |                    24 |                                           0.0055 |                                            0.0084 |
| Imports | partner     | Mexico (MEX)                                                                                   |                     2 |                                          -0.0010 |                                            0.0049 |
| Imports | partner     | Belgium (BEL)                                                                                  |                     3 |                                          -0.0013 |                                            0.0048 |
| Imports | partner     | USA (USA)                                                                                      |                    26 |                                           0.0033 |                                            0.0047 |
| Imports | partner     | Canada (CAN)                                                                                   |                     1 |                                          -0.0014 |                                            0.0040 |
| Imports | partner     | Sweden (SWE)                                                                                   |                     3 |                                          -0.0012 |                                            0.0037 |
| Imports | partner     | Netherlands (NLD)                                                                              |                     7 |                                          -0.0009 |                                            0.0025 |
| Imports | product     | Metals: gold, semi-manufactured                                                                |                     1 |                                           0.0008 |                                            0.0258 |
| Imports | product     | Large aircraft                                                                                 |                     1 |                                           0.0006 |                                            0.0132 |
| Imports | product     | Unwrought non-monetary gold                                                                    |                     6 |                                           0.0024 |                                            0.0128 |
| Imports | product     | Crude petroleum oil                                                                            |                    21 |                                           0.0059 |                                            0.0089 |
| Imports | product     | Aluminium oxide: other than artificial corundum                                                |                     1 |                                           0.0003 |                                            0.0069 |
| Imports | product     | Polypeptide hormones, protein hormones and glycoprotein hormones, their derivatives and...     |                     1 |                                           0.0003 |                                            0.0066 |
| Imports | product     | Mobile phones                                                                                  |                     1 |                                           0.0002 |                                            0.0054 |
| Imports | product     | Refined petroleum oils                                                                         |                    18 |                                           0.0031 |                                            0.0048 |
