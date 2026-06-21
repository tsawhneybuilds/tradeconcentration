# Cadot production-core sensitivity

## Question

Does the modern Cadot pattern remain after removing country types whose customs exports or measured income are especially likely to reflect offshore finance, tax booking, re-exports, microstate structure, or oil?

## Production-core sample

Starting from the 135-country complete-case modern panel, the preferred severe screen removes:

- countries with mean population below one million;
- countries with mean oil/fuel export share of at least 30%;
- prominent finance, tax-conduit, offshore, or re-export hubs represented in the sample.

The resulting production-core sample contains 83 countries. A still broader IMF-2000-offshore-centre screen leaves 81 countries and gives essentially the same results.

This is an exclusion sensitivity, not a domestic-production measure. The surviving data are still gross customs exports rather than domestic value-added exports.

## Results

### Level-PPP quadratic

| Outcome | Pooled result | Between-country result | Country-FE result |
| --- | --- | --- | --- |
| Active-product Gini | No U-shape; concentration continues declining through p95 | No U-shape; implied trough outside support | Negative-to-positive signs, but endpoint IUT p = 0.081 |
| Fixed-universe Theil | U-shape; trough $47,721; endpoint IUT p = 0.044 | U-shape; trough $46,026; endpoint IUT p = 0.032 | No supported U-shape |
| HHI | U-shape; trough $41,202; endpoint IUT p = 0.005 | U-shape; trough $39,934; endpoint IUT p = 0.005 | No supported U-shape |
| Active-product count | Inverted U; peak $47,397; endpoint IUT p = 0.005 | Inverted U; peak $46,020; endpoint IUT p = 0.005 | Peak remains outside central support |

The between-country Theil/count post-turning group contains 12 of 83 countries, or 14.5%: United Kingdom, Italy, France, Australia, Finland, Canada, Belgium, Sweden, Germany, Austria, Denmark, and the United States. Removing the United Kingdom and Belgium as an additional re-export/conduit stress test leaves the Theil, HHI, and product-count results essentially unchanged.

### Log-PPP quadratic

None of the four production-core outcomes passes the endpoint U-shape test under log GDP per capita. The apparent level-PPP hump is therefore functional-form sensitive.

## Interpretation

Removing hubs does not eliminate every Cadot pattern. It eliminates the active-positive Gini curve, but strengthens a cross-country pattern in fixed-universe Theil, HHI, and the number of active products. The surviving rich-side countries are primarily large advanced producing economies rather than oil exporters or offshore microstates.

This points toward an extensive-margin and dominant-product interpretation: advanced production economies may stop adding product lines and place more export weight on leading products. It does not establish an income-driven within-country law, because country fixed effects do not produce a formally supported U-shape.

The strongest wording is:

> In a severe production-oriented country sample, the cross-country diversification hump remains for fixed-universe Theil, HHI, and active-product counts, but not for active-product Gini; it disappears under log income and remains unsupported within countries.

## Reproducibility

- Script: `scripts/build_cadot_production_core_sensitivity.py`
- Model summary: `results/prof_p_replication/cadot_production_core_sensitivity/production_core_model_summary.csv`
- Country classifications: `results/prof_p_replication/cadot_production_core_sensitivity/country_exclusion_classification.csv`
- Manifest: `results/prof_p_replication/cadot_production_core_sensitivity/manifest.json`
