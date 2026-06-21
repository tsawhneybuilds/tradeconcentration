# Referee 2 Report: HS1992 Harmonization and the 5,037-Product Universe

**Date:** 2026-06-21
**Mode:** Code and measurement audit
**Scope:** LT/HGL weighted conversion to HS1992/H0, fixed-universe construction, and implications for concentration and diversification
**Independence note:** The available environment did not expose a fresh reviewer agent. This is a read-only local referee pass. No author code was modified; only independent replication scripts and this report were created.

## Summary

The current harmonization is defensible for value-based product concentration, but not yet fully defensible for literal extensive-margin interpretation.

The use of the Harvard Growth Lab/Lukaszuk-Torun weighted conversion to HS1992 is well motivated, value preserving, and superior to native-vintage comparisons or large connected-component product families. The observed 5,037-product universe is also numerically harmless. An official numeric HS1992 list contains 5,039 eligible six-digit leaves after excluding HS6 999999; adding the two never-observed lines would increase every fixed-universe Theil value by only log(5039/5037) = 0.000397.

The material concern is different. Chaining HS2022 back to HS1992 maps some H6 source products into hundreds of positive fractional H0 targets. The pipeline counts every positive target as active. This is appropriate for value allocation, but it can manufacture product presence and distort the extensive/intensive decomposition. The issue is visible in actual 2022-2024 observations and requires sensitivity analysis.

## Audit 1: Code and Data Construction

### Finding 1: The 5,037 count is an observed support, not the official HS1992 nomenclature

The fixed universe is the union of positive harmonized products observed in the world_broad sample during 2000-2024. It is not loaded directly from the official H0 classification list.

Independent Python and R checks agree:

| Definition | Products |
|---|---:|
| Official numeric HS1992 six-digit leaves, excluding 999999 | 5,039 |
| LT/HGL crosswalk targets currently cached | 5,041 |
| Observed world_broad fixed universe | 5,037 |

The observed universe is a subset of the official numeric list. The two official numeric lines not observed are 710820 and 711890. The two nonofficial crosswalk targets are 000077 and 009999. They arise because the classification loader extracts digits from a reserved chapter-77 record and from legacy alphanumeric code 9999AA. Neither appears in the observed 5,037-product universe, so neither contaminates the current headline panel.

**Assessment:** Minor conceptual problem, negligible numerical effect. The methods should call 5,037 the frozen 2000-2024 world-support universe, not the complete official HS1992 universe.

### Finding 2: Internal conversion checks pass

- Adjacent LT/HGL files have recorded DOI, version, file IDs, and MD5 checksums.
- Composed source weights sum to one within 2.22e-16.
- Product-dependent construction excludes 999999 before conversion.
- The three-metric manifest reports full common-row coverage, no duplicate reporter-year-flow keys, and no Theil decomposition residual failures.
- File-level diagnostics report value-conversion residuals at numerical zero.

**Assessment:** The value conversion is implemented coherently.

### Finding 3: Extreme chained mappings create synthetic positive products

The H6-to-H0 composed crosswalk contains:

| Diagnostic | Count |
|---|---:|
| H6 source codes | 5,612 |
| H6 sources mapping to at least 2 H0 targets | 668 |
| H6 sources mapping to at least 100 H0 targets | 15 |
| H6 sources mapping to at least 1,000 H0 targets | 6 |
| Maximum H0 targets from one H6 source | 1,009 |

The most extreme cases are HS2022 electronic-waste codes in headings 8524 and 8549. The high fanout is not a coding accident in the multiplication itself. It is the result of composing multiple non-one-to-one concordances back to 1992. The Lukaszuk-Torun method is expressly designed to allocate trade value across such links using estimated weights. It does not establish that every target receiving a tiny positive fraction should count as an independently active product.

**Assessment:** Major issue for active counts and extensive-margin decomposition; acceptable with caveats for value-based concentration.

## Audit 2: Independent Replication

Independent scripts:

- code/replication/referee2_audit_hs1992_universe.py
- code/replication/referee2_audit_hs1992_universe.R

Python and R exactly reproduce:

- 5,039 official numeric eligible H0 leaves.
- 5,041 cached crosswalk targets.
- 5,037 observed fixed-universe products.
- 1,009 maximum H6 targets per source.
- 15 H6 sources with at least 100 targets.
- 6 H6 sources with at least 1,000 targets.
- Median active-count changes around H6 adoption.

Stata was not available and could not be run.

### Raw-file sensitivity sample

Five 2022 H6 reporters were independently read from the raw compressed Comtrade files: Albania, Australia, Burkina Faso, China, and the United States. For each flow, metrics were recomputed under native H6 products, current weighted HS1992 values, and a maximum-weight HS1992 sensitivity.

Selected findings:

| Country-flow | Native H6 active | Weighted H0 active | Max-weight H0 active | Weighted Theil | Max-weight Theil |
|---|---:|---:|---:|---:|---:|
| Burkina Faso exports | 898 | 1,722 | 851 | 7.2207 | 7.2464 |
| Albania imports | 938 | 1,349 | 896 | 3.4782 | 3.5654 |
| China exports | 5,185 | 4,830 | 4,391 | 1.9484 | 2.1198 |
| China imports | 5,081 | 4,794 | 4,364 | 3.3650 | 3.5249 |
| USA exports | 5,521 | 4,952 | 4,522 | 2.4228 | 2.5340 |
| USA imports | 5,502 | 4,961 | 4,530 | 2.1655 | 2.2671 |

China has the largest economically material extreme mappings in this sample: 3.04 percent of export value and 5.25 percent of import value pass through H6 source codes with at least 100 H0 targets. Burkina Faso illustrates the presence problem: a very small value share in high-fanout codes can activate hundreds of target lines.

The maximum-weight mapping is not a preferred estimator; it is deliberately crude. Its role is to show that concentration levels are not invariant to how uncertain many-to-many mappings are resolved. Across the ten sampled country-flow cells, weighted Theil is 0.113 lower on average than maximum-weight Theil.

## Audit 3: Revision-Boundary Diagnostics

H6 observations account for 706 of 7,509 common product-panel rows, or 9.4 percent. There are 134 reporter transitions into H6 for each flow.

| Flow | Transition | Observations | Mean active-count change | Median active-count change |
|---|---|---:|---:|---:|
| Exports | No switch to H6, 2022-2024 | 297 | 24.4 | 4.0 |
| Exports | Switch to H6 | 134 | 167.7 | 114.5 |
| Imports | No switch to H6, 2022-2024 | 297 | 9.4 | 4.0 |
| Imports | Switch to H6 | 134 | 57.8 | 35.5 |

These differences do not prove that all changes are classification artifacts. They do show that the revision boundary is strongly associated with active-count changes and must be tested explicitly before interpreting the inactive-product Theil component.

## Audit 4: Reproducibility

Eight of ten sampled fresh weighted calculations match the saved panel to floating-point precision. Australia does not:

| Flow | Fresh minus saved active count | Fresh minus saved Theil |
|---|---:|---:|
| Australia exports, 2022 | 3 | -0.00235 |
| Australia imports, 2022 | 65 | -0.02857 |

The independent raw parser and a fresh call to the current author aggregation function agree with one another. Both differ from the saved checkpoint and headline panel. This indicates that the saved artifacts are not fully reproducible from the current code, weights, and raw files without clearing checkpoints.

**Assessment:** Publication blocker until a fresh checkpoint rebuild reproduces the final panel and the input checksums are recorded.

## Major Concerns

1. **Synthetic activation is treated as literal product entry.** Every positive fractional H0 allocation enters the active count. This overstates the precision of the extensive-margin decomposition.
2. **H6 revision effects are not isolated.** The 2022-2024 transition is associated with much larger active-count changes than nonswitching observations.
3. **Saved panel and fresh reconstruction differ for Australia.** Current outputs must be rebuilt from fresh checkpoints before publication.

## Minor Concerns

1. **Universe terminology is imprecise.** The 5,037 lines are observed world support, not the official full H0 list.
2. **Two malformed pseudo-targets exist in the cached crosswalk.** They are currently inactive but should be removed by exact leaf-code validation.
3. **The universe is sample-window dependent.** A future world_broad refresh could change K unless the file and checksum are frozen.

## Recommended Design

### Headline value-based concentration

Keep the LT/HGL weighted HS1992 allocation as the headline product-value harmonization for Gini, HHI, and total fixed-universe Theil. It is the strongest available method in the project for preserving product-level trade values across revisions.

Replace the observed-union definition of K with one of two explicit ex ante conventions:

1. Official numeric HS1992 six-digit leaves excluding 999999, K = 5,039; or
2. A substantively justified merchandise universe excluding 999999 and the two nontraded monetary/coin lines, K = 5,037.

Either convention is acceptable if frozen and documented. The coefficient-level consequences are negligible when K is constant.

### Extensive-margin interpretation

Do not use the current positive-weight active count as the only extensive-margin measure. Report at least:

1. Current positive-weight H0 activation, for continuity with the main panel.
2. A material-trade activation sensitivity, using the existing deflated 50,000-dollar threshold and a scale-neutral share threshold.
3. A maximum-weight or stable-HS4 concordance sensitivity.
4. Results excluding H6 observations and results with revision-transition indicators.

Describe the current decomposition as the extensive margin of the harmonized allocation, not necessarily the number of independently observed products.

### Validation

1. Rebuild all three-metric checkpoints from scratch.
2. Record raw-file and fixed-universe checksums in the final manifest.
3. Cross-check a 2000-2023 sample against the Growth Lab preconverted HS1992 data.
4. Re-estimate the principal development-path models under positive, thresholded, max-weight, and HS4 definitions.

## Verdict

**Value-based HS1992 harmonization:** Minor revision, defensible.

**The 5,037 fixed denominator:** Minor revision, defensible if accurately labeled and frozen.

**Literal extensive-margin interpretation from every positive weighted target:** Major revision.

**Current saved artifacts:** Major revision because the Australia checkpoint mismatch prevents full reproduction from current inputs.

