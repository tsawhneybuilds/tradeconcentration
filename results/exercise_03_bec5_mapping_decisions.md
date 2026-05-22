# Exercise 3 BEC5 Research-Bin Mapping Decisions

Generated: 2026-05-22T12:34:38+00:00

This memo documents the mapping decisions used to turn official HS-to-BEC and BEC5 end-use information into the Exercise 3 research bins. It is descriptive and does not update `exercises.md`.

## Principle

The mapping is official where the official BEC5 end-use is decisive. When the official BEC alternatives disagree, the main specification only recodes a row if the official HS description gives a clear economic use. Remaining ambiguous rows stay excluded and are reported.

## Main-Spec Rules

- Keep HS `999999` excluded. The official description is “Commodities not specified according to kind,” so assigning it to energy, capital goods, intermediates, or final consumption would create false precision.
- Resolve same-bin official ambiguity. If all official BEC alternatives imply the same research bin, use that bin.
- Use official HS descriptions to resolve clear remaining cross-bin cases:
  - parts, accessories, components, modules, and “for use with” goods -> `intermediates`
  - production/office/network machinery, measuring/checking instruments, switching/routing equipment, static converters, and similar durable equipment -> `capital_goods`
  - mobile phones, video games/consoles, televisions, headphones/loudspeakers, household refrigerators/washing machines, apparel/footwear, toys, and clear patient/consumer appliances -> `final_consumption`
- Energy is narrow in the main specification:
  - fuel/power products and clear petroleum-oil/fuel rows -> `energy`
  - petrochemical feedstocks, coal-tar/bituminous derivatives, waxes, petroleum coke, and ethanol remain excluded unless a broader energy sensitivity is used.
- Cross-version inconsistencies and generic “Other” rows stay excluded unless the official description is specific enough for one of the rules above.

## Current Value Coverage Before These Description Rules

| exercise_03_bin       |   trade_value |   share_of_total_import_value |
|:----------------------|--------------:|------------------------------:|
| intermediates         |   1.58791e+14 |                    0.469469   |
| final_consumption     |   7.09253e+13 |                    0.209692   |
| energy                |   4.37033e+13 |                    0.12921    |
| capital_goods         |   4.19406e+13 |                    0.123999   |
| unmapped_or_ambiguous |   2.24537e+13 |                    0.0663848  |
| no_mapping_match      |   4.21369e+11 |                    0.00124579 |

## Final Main Mapping Row Counts

| bin                   |   mapping_rows |
|:----------------------|---------------:|
| intermediates         |          22075 |
| final_consumption     |           9107 |
| capital_goods         |           4510 |
| unmapped_or_ambiguous |            698 |
| energy                |            210 |

## Rows Reclassified By Description Rule

| description_rule                                          | exercise_03_bin   |   rows |
|:----------------------------------------------------------|:------------------|-------:|
| official_hs_description_clear_capital_equipment           | capital_goods     |     53 |
| official_hs_description_clear_final_consumption           | final_consumption |     39 |
| official_hs_description_clear_part_component_or_accessory | intermediates     |     93 |

## Import-Value Impact Of Description Rules

| description_rule                                          | exercise_03_bin   |   rows |   trade_value |   share_of_total_import_value |
|:----------------------------------------------------------|:------------------|-------:|--------------:|------------------------------:|
| official_hs_description_clear_capital_equipment           | capital_goods     |     53 |   3.21902e+12 |                    0.00951711 |
| official_hs_description_clear_final_consumption           | final_consumption |     39 |   2.03328e+12 |                    0.00601144 |
| official_hs_description_clear_part_component_or_accessory | intermediates     |     93 |   1.35999e+12 |                    0.00402083 |

## Estimated Value Coverage After Description Rules

| exercise_03_bin       |   trade_value |   share_of_total_import_value |
|:----------------------|--------------:|------------------------------:|
| intermediates         |   1.60151e+14 |                    0.47349    |
| final_consumption     |   7.29586e+13 |                    0.215704   |
| capital_goods         |   4.51597e+13 |                    0.133516   |
| energy                |   4.37033e+13 |                    0.12921    |
| unmapped_or_ambiguous |   1.58414e+13 |                    0.0468354  |
| no_mapping_match      |   4.21369e+11 |                    0.00124579 |

## Sensitivity Mappings

Three robustness mappings were written:

- `capital_bound`: assign remaining official cross-bin rows with a possible capital-goods alternative to `capital_goods`.
- `intermediate_bound`: assign remaining official cross-bin rows with a possible intermediate alternative to `intermediates`.
- `broad_energy_bound`: assign remaining HS27-like/energy-treatment residuals to `energy`.

|   intermediates |   final_consumption |   capital_goods |   unmapped_or_ambiguous |   energy | sensitivity        |
|----------------:|--------------------:|----------------:|------------------------:|---------:|:-------------------|
|           22075 |                9107 |            4912 |                     296 |      210 | capital_bound      |
|           22585 |                9107 |            4510 |                     188 |      210 | intermediate_bound |
|           22075 |                9107 |            4510 |                     541 |      367 | broad_energy_bound |

## Files

- Main candidate: `data/processed/exercise_03_bec5_mapping_candidate.csv`
- Main candidate copy: `data/processed/exercise_03_bec5_mapping_desc_resolved_candidate.csv`
- Change log: `results/exercise_03_tables/bec5_mapping_description_resolved_changes.csv`
- Sensitivities: `data/processed/exercise_03_bec5_mapping_sensitivity_*.csv`

## Suggested Write-Up

The main specification uses official HS-to-BEC correspondences and official BEC5 end-use labels. Ambiguous official mappings are resolved only when either all alternatives imply the same research bin or the official HS description clearly identifies the product as a component/intermediate, durable capital equipment, final consumption good, or narrow energy product. Remaining ambiguous products are excluded from the main bin comparison and reported separately; robustness checks reassign them under capital-goods, intermediate-input, and broad-energy bounds.
