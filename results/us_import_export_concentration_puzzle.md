# US Import Concentration Puzzle

Generated: 2026-05-24T06:51:53+00:00

This memo is a descriptive accounting package. The main object is aggregate HS6 product concentration: whether trade dollars are piled into a few product lines. Supplier concentration is supporting evidence only.

## Main Answer

The clean version of Tanush's hypothesis is not "one major provider for each type of good." The data support a weaker and more defensible story:

> US imports have historically looked product-concentrated when a few very large demand categories dominate the receipt, and some of those categories have strong supplier corridors.

Feynman version: exports are the shelf where the US sells what it is unusually good at selling to the world. Imports are the receipt from a huge buyer. A few enormous receipt lines can make the whole import basket look concentrated even when most individual products are not single-sourced.

## The Puzzle

| Country | Years | Share import product Gini > export product Gini | Median gap | Latest year | Latest gap |
| --- | ---: | ---: | ---: | ---: | ---: |
| United States | 1991-2025 | 77.1% | +0.0174 | 2025 | -0.0083 |
| China | 1992-2024 | 100.0% | +0.0631 | 2024 | +0.0910 |
| India | 1988-2024 | 81.1% | +0.0122 | 2024 | +0.0184 |
| Italy | 1994-2025 | 43.8% | -0.0002 | 2025 | -0.0077 |


For the US, the pattern is historical, not current. US import product Gini exceeded export product Gini in 77.1% of observed years from 1991-2025, with median gap +0.0174. In 2025, the gap is -0.0083, so exports are now slightly more product-concentrated.

## Recent US Timing

| year | product_gini_imports | product_gini_exports | product_gini_gap_import_minus_export | partner_gini_gap_import_minus_export |
| --- | --- | --- | --- | --- |
| 2018 | 0.8678 | 0.8688 | -0.0010 | +0.0182 |
| 2019 | 0.8694 | 0.8722 | -0.0028 | +0.0206 |
| 2020 | 0.8723 | 0.8732 | -0.0009 | +0.0188 |
| 2021 | 0.8679 | 0.8803 | -0.0124 | +0.0160 |
| 2022 | 0.8671 | 0.8878 | -0.0207 | +0.0152 |
| 2023 | 0.8734 | 0.8856 | -0.0122 | +0.0143 |
| 2024 | 0.8771 | 0.8881 | -0.0110 | +0.0163 |
| 2025 | 0.8880 | 0.8963 | -0.0083 | +0.0168 |

The product gap turns negative from 2018 onward in the current file, but the partner gap remains positive. Product concentration and partner concentration are answering different questions.

## Large-Category Diagnostics

Top pre-2018 HS2 groups by median reduction in the import-minus-export product-Gini gap when removed:

| hs2 | median_gap_reduction_when_group_removed | mean_import_value_share | mean_export_value_share | years |
| --- | --- | --- | --- | --- |
| 27 | +0.0129 | 13.3% | 4.6% | 27 |
| 87 | +0.0059 | 12.8% | 9.2% | 27 |
| 29 | +0.0025 | 2.4% | 3.0% | 27 |
| 39 | +0.0015 | 1.9% | 4.0% | 27 |
| 48 | +0.0012 | 1.2% | 1.4% | 27 |
| 38 | +0.0008 | 0.4% | 1.6% | 27 |
| 32 | +0.0007 | 0.2% | 0.6% | 27 |
| 34 | +0.0006 | 0.1% | 0.4% | 27 |

Top pre-2018 BEC/import-bin groups by the same diagnostic:

| import_bin | median_gap_reduction_when_group_removed | mean_import_value_share | mean_export_value_share | years |
| --- | --- | --- | --- | --- |
| energy | +0.0110 | 12.6% | 4.1% | 27 |
| unmapped_or_ambiguous | +0.0002 | 3.9% | 4.2% | 27 |
| capital_goods | +0.0001 | 14.3% | 18.4% | 27 |
| final_consumption | -0.0093 | 30.0% | 15.5% | 27 |
| intermediates | -0.0094 | 39.2% | 57.8% | 27 |

Reading rule: positive gap reduction means the group raises import product concentration relative to export product concentration. Negative values mean the group works the other way.

Commodity robustness in 2025: after excluding HS4 2701, 2709, 2710, 2711, 7108, the US import-minus-export product-Gini gap is +0.0065. Removed value shares are 7.1% of imports and 19.6% of exports.

## Supplier-Corridor Evidence

The supplier data support the corridor part of the story, but not a broad single-source story.

| Check | 2025 US value |
| --- | ---: |
| Weighted top-supplier share | 43.8% |
| Median top-supplier share across HS6 products | 45.6% |
| Import value with top supplier >= 50% | 33.4% |
| Import value with top supplier >= 75% | 9.2% |
| Import value with top supplier >= 90% | 4.0% |
| Exercise 13 diffuse share | 89.4% |

Latest Exercise 13 ecosystem shares:

| class | value_share |
| --- | --- |
| diffuse | 89.4% |
| economy_specific | 7.2% |
| global_dominant | 3.3% |
| global_but_importer_diffuse | 0.1% |
| global_concentrated_other_source | 0.0% |

Top 2025 import product corridors:

| rank | cmd_code | product | import_value | top_supplier_iso3 | within_product_top_supplier_share | supplier_ecosystem_class |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 847150 | Digital processing units other than those of sub-headin... | $164.6B | MEX | 48.9% | diffuse |
| 2 | 270900 | Petroleum oils and oils obtained from bituminous minera... | $146.8B | CAN | 61.4% | diffuse |
| 3 | 847330 | Parts and accessories of the machines of heading No. 84.71 | $89.4B | S19 | 52.2% | diffuse |
| 4 | 851762 | Machines for the reception, conversion and transmission... | $84.9B | VNM | 28.2% | diffuse |
| 5 | 300490 | Other | $82.5B | CHE | 17.3% | diffuse |
| 6 | 300215 | Blood, human or animal, antisera, other blood fractions... | $78.7B | IRL | 24.4% | diffuse |
| 7 | 711590 | Other | $77.6B | CHE | 63.7% | diffuse |
| 8 | 870323 | Other vehicles, with spark-ignition internal combustion... | $76.4B | MEX | 26.9% | diffuse |
| 9 | 293719 | Other | $57.8B | IRL | 97.4% | global_dominant |
| 10 | 851713 | Telephone sets; smartphones for cellular or other wirel... | $52.4B | CHN | 45.2% | diffuse |
| 11 | 847130 | Portable digital automatic data processing machines, we... | $49.3B | VNM | 61.5% | diffuse |
| 12 | 854231 | Processors and controllers, whether or not combined wit... | $32.6B | S19 | 31.3% | diffuse |

## Interpretation

The better economic interpretation is a tug between export specialization and import demand lumps. The US export basket contains large categories such as aircraft, energy, pharma, machinery, semiconductors, agriculture, and capital goods. The US import basket contains huge demand categories such as oil and gas, vehicles, computing equipment, electronics, pharmaceuticals, medical goods, and intermediate inputs.

Historically, import demand lumps often dominated the US product-Gini comparison. From 2018 onward, in the current data, they do not. That is why any statement about the US exception should say historical, not current.

## Outputs And Validation

Tables are in `results/us_import_concentration_puzzle_tables/`.

Inputs:

- `data/processed/concentration_all_years.parquet`
- `data/processed/exercise_11_product_export_linkage_panel.parquet`
- `data/processed/exercise_12_export_aggregates.parquet`
- `results/exercise_04_tables/dominant_supplier_importer_summary.csv`
- `results/exercise_13_import_hypotheses_tables/`
- `data/processed/exercise_03_bec5_mapping_approved.csv`

Validation checks passed:

- Reconstructed import product Gini max absolute difference: 0
- Reconstructed export product Gini max absolute difference: 0
- Generated product-level tables exclude HS6 `999999`.

Limits:

- Goods-only HS merchandise trade; services are outside this package.
- HS6 codes are product categories, not firms or technologies.
- Supplier evidence is source-country evidence, not firm-supplier evidence.
- `Other Asia, nes` rows are not clean bilateral country corridors.
