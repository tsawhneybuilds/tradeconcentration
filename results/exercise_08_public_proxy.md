# Exercise 8: EDD + WBES Public Proxy

Generated: 2026-05-24T09:05:08+00:00

## What This Tests

This is a public proxy for the firm-level core-portfolio exercise. It tests whether aggregate product, partner, and product-partner concentration plausibly lines up with exporter concentration, exporter scope, and firm survey measures of export focus.

It does **not** observe firm-product-destination customs values. Therefore it cannot directly prove whether a country's concentrated export products are the core products of a few firms. That gold-standard version still requires restricted customs microdata.

## EDD Country-Year Proxy

- Merged EDD x Exercise 1 rows: 124
- Countries with overlap: 10
- Years with overlap: 1997-2014
- EDD series used: A1, B1, B2i, B2ii, B2iii, B3i, B3ii, B4i, B4ii
- India/China/US absent from EDD country-year API pull: India, China, United States

EDD tells us whether countries with concentrated exporters also have concentrated national export products, destinations, or product-destination cells. It cannot show the products and destinations inside each firm.

### Strongest EDD Correlations

| outcome | predictor | nobs | pearson | spearman |
| --- | --- | --- | --- | --- |
| product_gini | top_5pct_exporter_share | 124 | 0.6264 | 0.6768 |
| product_top_5pct_share | top_5pct_exporter_share | 124 | 0.6557 | 0.6506 |
| product_partner_cell_top_5pct_share | destinations_per_exporter_mean | 124 | -0.5684 | -0.6225 |
| product_gini | destinations_per_exporter_mean | 124 | -0.6225 | -0.6202 |
| product_top_5pct_share | destinations_per_exporter_mean | 124 | -0.6213 | -0.6051 |
| product_partner_cell_gini | top_5pct_exporter_share | 124 | 0.6621 | 0.5916 |
| product_gini | exporter_hhi | 124 | 0.3603 | 0.5762 |
| product_gini | top_1pct_exporter_share | 124 | 0.5048 | 0.5718 |
| product_partner_cell_gini | destinations_per_exporter_mean | 124 | -0.5250 | -0.5695 |
| product_gini | number_exporters | 124 | -0.6417 | -0.5643 |
| product_partner_cell_top_5pct_share | top_5pct_exporter_share | 124 | 0.6460 | 0.5629 |
| product_top_5pct_share | number_exporters | 124 | -0.5833 | -0.5626 |

### Largest EDD Standardized OLS Coefficients

Outcome and single predictor are standardized. Controls are log total exports, log active counts where available, and year fixed effects.

| outcome | predictor | coefficient | std_error_hc1 | nobs | r_squared |
| --- | --- | --- | --- | --- | --- |
| partner_gini | destinations_per_exporter_median | -0.3058 | 0.0663 | 124 | 0.7406 |
| top_5_partner_share | destinations_per_exporter_median | -0.2360 | 0.0615 | 124 | 0.7780 |
| product_gini | number_exporters | -0.2096 | 0.0333 | 124 | 0.9281 |
| top_5_partner_share | destinations_per_exporter_mean | -0.1888 | 0.0836 | 124 | 0.7537 |
| partner_gini | number_exporters | 0.1494 | 0.0803 | 124 | 0.6920 |
| product_top_5pct_share | number_exporters | -0.1372 | 0.0341 | 124 | 0.9312 |
| top_5_partner_share | top_1pct_exporter_share | -0.1353 | 0.0524 | 124 | 0.7560 |
| product_partner_cell_top_5pct_share | hs6_products_per_exporter_median | -0.1263 | 0.0348 | 124 | 0.8877 |
| partner_gini | destinations_per_exporter_mean | -0.1208 | 0.0916 | 124 | 0.6865 |
| product_partner_cell_gini | hs6_products_per_exporter_median | -0.1167 | 0.0359 | 124 | 0.8922 |
| partner_gini | top_25pct_exporter_share | 0.1122 | 0.0464 | 124 | 0.6884 |
| top_5_partner_share | top_5pct_exporter_share | -0.1113 | 0.0640 | 124 | 0.7493 |


## WBES Firm-Survey Proxy

- Normalized WBES firm rows: 0
- Countries with usable WBES rows: 0
- Expected WBES files that are missing or invalid:
- India (data/raw/wbes/India_2014_2022.dta)
- China (data/raw/wbes/China-2024-full-data.dta)
- United States (data/raw/wbes/United-States-2024-full-data.dta)

WBES tells us whether surveyed exporters in India, China, and the United States look specialized or broad by their main activity/product-line sales share, size, import status, and export intensity. It is firm survey evidence, not customs data: it does not observe every firm-product-destination export value.

### WBES Country Summary

| country_iso3 | country_name | survey_year | n_firms | weighted_firms | n_any_exporters | n_direct_exporters | weighted_any_exporter_share | weighted_direct_exporter_share | median_export_share_exporters | median_direct_export_share_direct_exporters | main_activity_mean_exporters | main_activity_mean_nonexporters | main_activity_median_exporters | main_activity_median_nonexporters | share_main_activity_ge_50_exporters | share_main_activity_ge_75_exporters | share_main_activity_ge_90_exporters | skip_reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| IND | India | 2022 | 0 | 0.0000 | 0 | 0 |  |  |  |  |  |  |  |  |  |  |  | wbes_file_missing_or_invalid |
| CHN | China | 2024 | 0 | 0.0000 | 0 | 0 |  |  |  |  |  |  |  |  |  |  |  | wbes_file_missing_or_invalid |
| USA | United States | 2024 | 0 | 0.0000 | 0 | 0 |  |  |  |  |  |  |  |  |  |  |  | wbes_file_missing_or_invalid |

### Strongest WBES Exporter-Focus Correlations

No rows.

### WBES Exporter-Focus OLS

These are weighted NumPy least-squares models when survey weights are available; otherwise all weights equal one. Predictors are standardized, outcomes stay in native units.

No rows.

### WBES Main Destination Proxy

Destination concentration is based on each surveyed direct exporter's reported main export destination. Value shares use `sales * direct_export_share / 100`, so they are survey approximations, not customs export totals.

| country_iso3 | survey_year | firms_with_main_destination | destination_count | weighted_destination_hhi_by_firms | weighted_top_5_destination_share_by_firms | top_destination_by_firms | skip_reason |
| --- | --- | --- | --- | --- | --- | --- | --- |
| IND | 2022 | 0 | 0 |  |  |  | wbes_file_missing_or_invalid |
| CHN | 2024 | 0 | 0 |  |  |  | wbes_file_missing_or_invalid |
| USA | 2024 | 0 | 0 |  |  |  | wbes_file_missing_or_invalid |

Manual WBES download targets, if auto-download fails:

- India: `data/raw/wbes/India_2014_2022.dta` from https://microdata.worldbank.org/catalog/6494
- China: `data/raw/wbes/China-2024-full-data.dta` from https://microdata.worldbank.org/catalog/6676
- United States: `data/raw/wbes/United-States-2024-full-data.dta` from https://microdata.worldbank.org/catalog/6709


## Interpretation Rule

If EDD exporter concentration lines up with aggregate concentration, and WBES exporters also look focused, firm concentration becomes a plausible mechanism. If EDD is weak or WBES exporters are broad, the explanation should lean more toward product-level comparative advantage, gravity, input-output linkages, dominant suppliers, demand, or policy. If WBES files are missing, the exercise reports that as a data-access gap rather than filling values synthetically.

## Files

- EDD panel: `results/exercise_08_tables/edd_public_proxy_panel.csv`
- EDD correlations: `results/exercise_08_tables/edd_correlations.csv`
- EDD OLS: `results/exercise_08_tables/edd_ols.csv`
- WBES firm panel: `results/exercise_08_tables/wbes_firm_proxy_panel.csv`
- WBES country summary: `results/exercise_08_tables/wbes_country_summary.csv`
- WBES correlations: `results/exercise_08_tables/wbes_exporter_focus_correlations.csv`
- WBES OLS: `results/exercise_08_tables/wbes_exporter_focus_ols.csv`
- WBES destination summary: `results/exercise_08_tables/wbes_destination_summary.csv`
- Manifest: `results/run_manifest_exercise_08_public_proxy.json`

## Source Details

```json
{
  "created_at_utc": "2026-05-24T09:05:08+00:00",
  "edd": {
    "created_at_utc": "2026-05-24T09:05:04+00:00",
    "exercise1_csv": "/Users/tanushsawhney/Desktop/profps26/results/exercise_01_tables/concentration_all_years.csv",
    "min_n": 10,
    "no_synthetic_or_inferred_trade_values": true,
    "public_proxy_limitation": "EDD is public and customs-derived, but it does not expose firm-product-destination export values.",
    "refresh": false,
    "series": {
      "A1": "number_exporters",
      "B1": "exporter_hhi",
      "B2i": "top_1pct_exporter_share",
      "B2ii": "top_5pct_exporter_share",
      "B2iii": "top_25pct_exporter_share",
      "B3i": "hs6_products_per_exporter_mean",
      "B3ii": "hs6_products_per_exporter_median",
      "B4i": "destinations_per_exporter_mean",
      "B4ii": "destinations_per_exporter_median"
    },
    "skip_figures": false,
    "source": "World Bank Exporter Dynamics Database, API source 30",
    "source_url": "https://api.worldbank.org/v2/sources/30"
  },
  "exercise1_csv": "/Users/tanushsawhney/Desktop/profps26/results/exercise_01_tables/concentration_all_years.csv",
  "min_n": 10,
  "no_synthetic_or_inferred_trade_values": true,
  "public_proxy_limitation": "Exercise 8 public proxy cannot observe full firm-product-destination customs portfolios.",
  "refresh": false,
  "skip_figures": false,
  "source_requested": "all",
  "wbes": {
    "datasets": [
      {
        "catalog_id": "6494",
        "catalog_url": "https://microdata.worldbank.org/catalog/6494",
        "country": "India",
        "data_dictionary_url": "https://microdata.worldbank.org/catalog/6494/data-dictionary/F1?file_name=India_2014_2022.dta",
        "fallback_survey_year": 2022,
        "filename": "India_2014_2022.dta",
        "iso3": "IND"
      },
      {
        "catalog_id": "6676",
        "catalog_url": "https://microdata.worldbank.org/catalog/6676",
        "country": "China",
        "data_dictionary_url": "https://microdata.worldbank.org/catalog/6676/data-dictionary/F1?file_name=China-2024-full-data.dta",
        "fallback_survey_year": 2024,
        "filename": "China-2024-full-data.dta",
        "iso3": "CHN"
      },
      {
        "catalog_id": "6709",
        "catalog_url": "https://microdata.worldbank.org/catalog/6709",
        "country": "United States",
        "data_dictionary_url": "https://microdata.worldbank.org/catalog/6709/data-dictionary/F1?file_name=United-States-2024-full-data.dta",
        "fallback_survey_year": 2024,
        "filename": "United-States-2024-full-data.dta",
        "iso3": "USA"
      }
    ],
    "min_n": 10,
    "no_synthetic_or_inferred_trade_values": true,
    "public_proxy_limitation": "WBES is firm survey data. It records export status/intensity and some focus/destination proxies, but not full firm-product-destination customs values.",
    "skip_figures": false,
    "source": "World Bank Enterprise Surveys public microdata",
    "wbes_dir": "data/raw/wbes"
  },
  "wbes_dir": "/Users/tanushsawhney/Desktop/profps26/data/raw/wbes"
}
```
