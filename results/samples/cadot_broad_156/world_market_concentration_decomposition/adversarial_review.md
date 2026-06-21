# Adversarial review: world-market concentration decomposition

Review date: 2026-06-21

This was a local adversarial review. It was not an independent fresh-agent pass because subagent delegation was not authorized.

## 1. Executive verdict

**Mostly trustworthy**

- The preferred result is an exact accounting decomposition, not a causal estimator: observed fixed-universe Theil equals the global-market component plus country-specific KL divergence to numerical precision.
- The main panel uses the intended `cadot_broad_156` reporter sample, 2000-2024 exports, LT/HGL-weighted HS1992/H0 products, and excludes HS6 `999999` before product aggregation.
- The main population patterns survive country-and-year two-way clustering, a balanced-panel restriction, exclusion of the five largest reporters, inclusive-world benchmarking, broad-primary exclusion, and a full-current-raw sensitivity.
- No single reporter drives the result. The population coefficient retains its sign in every leave-one-country-out estimate.
- Two data-lineage problems are real and disclosed: 86 country-years have raw-file revision drift relative to the published three-metric checkpoints, and 56 country-years have material leave-one-out benchmark conflicts. These rows are excluded from the preferred sample.
- The evidence supports a descriptive benchmark explanation. It does not identify a causal effect of population, GDP, or world demand.

## 2. Highest-risk findings

### High severity: source files changed after the published checkpoint run

**What happened:** The pre-existing country-product cache failed to reproduce the published three-metric concentration panel in 270 of 3,753 reporter-years. Rebuilding those rows from the exact published `source_raw_file` restored metric parity in 184 cases. The remaining 86 rows still differed because the current raw file contents no longer reproduce the earlier checkpoint despite having the same filename.

**Why it matters:** Mixing product distributions from different raw revisions could create artificial concentration and benchmark differences. The unresolved rows disproportionately include some large European reporters.

**Verification:** `source_alignment_audit.csv` reports 3,483 original matches, 184 rebuilt matches, and 86 unresolved raw-revision rows.

**Fix applied:** The preferred sample requires `source_metric_parity == True`. The full-current-raw sensitivity retains the current raw rows. Its population coefficients are nearly unchanged: specialization KL is -0.551 versus -0.554 in the preferred sample, and the market-component share coefficient is 0.063 versus 0.063.

**Remaining fix:** For a frozen replication package, archive checksums of every selected Comtrade raw file and regenerate both country and world caches from that immutable snapshot.

### High severity: stale or zero leave-one-out world-product values

**What happened:** In 56 baseline reporter-years, more than 0.1% of exports fall in products with zero rest-of-world exports or where the current country value exceeds the cached broad-world total. The maximum affected share is 19.1%.

**Why it matters:** KL divergence is undefined when a country has positive exports but the benchmark share is zero. A floor can otherwise make results depend on an arbitrary regularization.

**Verification:** `world_market_concentration_diagnostics.csv` and the panel columns `exclusive_product_trade_share` and `world_benchmark_inconsistent_trade_share`.

**Fix applied:** These rows are excluded from the preferred leave-one-out sample. The inclusive-world sensitivity, which does not require a leave-one-out floor, gives the same qualitative result: specialization KL coefficient -0.567 and market-component share coefficient 0.070.

**Remaining fix:** Rebuild world-product totals from the same immutable raw snapshot as the country product values.

### Medium severity: the result is mainly cross-sectional

**What happened:** The preferred year-fixed-effects model finds a specialization-KL coefficient of -0.554, but the country-and-year fixed-effects diagnostic is -0.421 with raw p = 0.118. For the non-commodity variant it is -0.064 with raw p = 0.879.

**Why it matters:** The evidence compares generally large and small countries; it does not show that population growth within a country reduces specialization.

**Fix:** Report the year-FE model as a descriptive cross-country size gradient. Do not describe it as a causal or within-country effect.

### Medium severity: global exports are a product-trade benchmark, not pure demand

**What happened:** The benchmark uses broad-world product exports because a harmonized world-import-demand cache was not available.

**Why it matters:** Export supply, reporting asymmetries, and demand jointly determine world export shares.

**Fix:** Use “global product-trade size” or “world export-market benchmark,” not “exogenous world demand.” A future robustness check should construct rest-of-world import demand from a synchronized raw snapshot.

## 3. Data lineage and sample audit

Data path:

1. Country product values: `data/processed/samples/cadot_broad_156/world_relative_product_gini_harmonized_hs6_family_cadot_broad_156_product_exports.parquet`.
2. Published concentration and exact source-file metadata: `results/samples/cadot_broad_156/three_metric_tables/metric_headline_product_panel.parquet`.
3. Source alignment: 270 mismatched reporter-years rebuilt from the published raw filename and cached under `checkpoints/source_aligned_products/`.
4. World benchmark: `data/processed/samples/world_broad/world_relative_product_gini_harmonized_hs6_family_world_product_exports.parquet`.
5. Country controls: baseline rows from `world_large_product_exposure_panel.parquet`.
6. Final decomposition panel and regression outputs in this directory.

Counts:

- Country-product input: 9,984,589 positive rows.
- Reporters: 156.
- Years: 25, from 2000 through 2024.
- Harmonized product universe: 5,037 HS1992/H0 products.
- Baseline reporter-years: 3,753.
- Complete-control reporter-years: 3,728.
- Preferred regression rows: 3,589.
- Preferred reporter clusters: 155.
- Cluster size: minimum 5, median 25, maximum 25.
- Balanced-control reporters before other quality restrictions: 108.
- Duplicate final panel keys: zero.

The preferred sample loss is explicit: missing controls, unresolved source revisions, and unreliable leave-one-out benchmarks. The full-current-raw and inclusive-world sensitivities show that these exclusions do not drive the headline signs or magnitudes.

## 4. Merge/join audit

- Country product keys are unique at reporter-year-product.
- World product keys are unique at year-product.
- The country-to-world merge is many-to-one and has zero unmatched country-product rows.
- Controls are unique at reporter-year and merge many-to-one without changing row counts.
- Published metric validation is one-to-one at reporter-year.
- Product classification is unique at harmonized product ID.
- No many-to-many merge is used in the final decomposition panel.
- The country-product source alignment is audited separately rather than silently overwriting mismatched rows.

## 5. Variable construction audit

For country product share \(s_{cpt}\), smoothed leave-one-country-out world share \(w_{-c,pt}\), and fixed universe \(K\):

\[
T_{ct}=\sum_p s_{cpt}\log(Ks_{cpt})
\]

is decomposed as

\[
T_{ct}
=
\sum_p s_{cpt}\log(Kw_{-c,pt})
+
\sum_p s_{cpt}\log(s_{cpt}/w_{-c,pt}).
\]

The first term is the global-market component. The second is KL divergence and is nonnegative. The maximum absolute numerical identity residual is \(7.99\times10^{-15}\).

Construction checks:

- Unit: reporter-year exports.
- Product inputs: positive harmonized product values.
- HS6 `999999`: excluded upstream before harmonization.
- Universe: 5,037 products for the baseline; the broad-primary variant rebuilds and renormalizes the filtered universe.
- Leave-one-out benchmark: reporter exports are subtracted before product shares are calculated.
- Zero benchmark treatment: a documented floor is used in the full panel, but rows with more than 0.1% affected export share are excluded from preferred results.
- No winsorization or outcome trimming is used.
- Size bins are population quintiles formed separately within each year before quality exclusions.
- Population and GDP per capita are logged World Bank controls inherited from the validated exposure panel.

The active Gini benchmark is not presented as an additive decomposition. It holds the active product set fixed and asks what Gini would result if values followed rest-of-world product shares within that set.

## 6. Specification audit

The preferred descriptive regression is:

\[
Y_{ct}=\alpha_t+\beta\log Population_{ct}
+\gamma\log GDPpc_{ct}+\varepsilon_{ct}.
\]

Outcomes include observed Theil, the global-market component, specialization KL, the market-component share, observed active Gini, benchmark active Gini, and their gap.

- Fixed effects: year.
- Main inference: reporter-country clustered standard errors.
- Two-way diagnostic: reporter and year clustering, with Student-t reference based on 25 year clusters.
- Main population interpretation: comparison of larger and smaller reporters within the same year, holding GDP per capita constant.
- Country-and-year fixed effects are diagnostic only because they answer a different, within-country question and absorb most persistent size variation.
- No trade-value control is included because total trade is mechanically related to the product-share distribution.

## 7. Inference and identification audit

The main results remain statistically distinct from zero under two-way clustering:

- Observed Theil: beta -0.377, two-way raw p < 0.001.
- Global-market component: beta 0.177, two-way raw p < 0.001.
- Specialization KL: beta -0.554, two-way raw p < 0.001.
- Market-component share: beta 0.063, two-way raw p < 0.001.
- Gini gap: beta -0.0084, two-way raw p < 0.001.

Economic magnitude:

- Doubling population is associated with a 0.384 decline in specialization KL, approximately 0.22 outcome standard deviations.
- Doubling population is associated with a 0.044 increase in the global-market share of observed Theil, approximately 0.18 standard deviations.
- In the size-bin accounting summary, the global-market component is 16.6% of mean Theil in the smallest quintile and 45.2% in the largest.

Influence:

- Every country jackknife retains the headline coefficient signs.
- Specialization-KL coefficients range from -0.562 to -0.535.
- Market-component-share coefficients range from 0.061 to 0.065.

Identification limit:

There is no exogenous treatment assignment. Population, capabilities, institutions, geography, and trade composition are jointly determined. The regressions are descriptive summaries of an accounting decomposition.

## 8. Replication checklist

Run:

```bash
python3 -m py_compile scripts/run_world_market_concentration_decomposition.py
pytest -q tests/test_world_market_concentration_decomposition.py
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 \
python3 scripts/run_world_market_concentration_decomposition.py
```

Before trusting a rerun, verify:

1. All rows in `world_market_concentration_validation.csv` pass.
2. `run_manifest.json` reports `status: complete`.
3. The maximum Theil identity residual remains below \(10^{-10}\).
4. Source alignment status counts are reported.
5. No HS6 `999999`-derived product remains.
6. Preferred-sample row and cluster counts are reported.
7. Country-clustered and two-way-clustered conclusions agree.
8. Full-current-raw, inclusive-world, balanced, top-five exclusion, and non-commodity results retain the headline pattern.
9. All country jackknife coefficients retain the headline sign.
10. Figures are visually inspected after rendering.

## 9. Minimal patch plan

The pipeline is adequate for the current descriptive purpose. The smallest upgrades for publication-quality evidence are:

1. Freeze and checksum the selected Comtrade raw files.
2. Rebuild country and broad-world product totals from the same snapshot.
3. Construct a rest-of-world import-demand benchmark as a robustness check.
4. Add a source-attrition table to the appendix showing exclusions by country and population quintile.
5. Keep the country-FE null result visible so readers do not infer a within-country causal relationship.

## 10. Questions for the researcher

1. Should the paper’s object be called “global product-market size” or the narrower and more accurate “global product-trade size”?
2. Is the project willing to freeze a full raw-data snapshot before treating this decomposition as a final paper result?
