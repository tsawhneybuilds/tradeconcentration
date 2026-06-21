# Historical Partner Gini Extension Design

Generated: 2026-06-02

Revision note: updated after an independent Referee 2 design audit on 2026-06-02. The main change is to treat changing partner coverage as a measurement problem that must be bounded and stress-tested, not merely reported.

## Goal And Estimand

The descriptive question is whether country-level trade-partner concentration has been stable, rising, or falling over the long run, especially from roughly 1900 onward. This is not a causal design.

For reporter country or polity `i`, year `t`, and flow `f` in exports or imports, the main estimand is:

```text
PartnerGini_i,t,f = Gini({v_i,j,t,f : j is an observed valid partner and v_i,j,t,f > 0})
```

`v_i,j,t,f` is the nominal merchandise trade value between reporter `i` and partner `j`. In plain English, Partner Gini measures how unevenly a reporter's trade is spread across its observed positive trading partners in a given year and flow. Higher values mean trade is concentrated among fewer partners; lower values mean trade is more evenly spread.

The historical module should be separate from the Comtrade HS6 pipeline. Product identity is not part of this historical measure. If product-coded historical data ever enter, HS6 `999999` remains included in partner totals for partner-only concentration by repo convention, but aggregate partners such as World, regions, continents, "areas not elsewhere specified", and unknown partners must be excluded from the partner vector.

## Data Structure

The core unit is reporter-partner-year-flow. The derived panel is reporter-year-flow. The data are a historical panel with changing geopolitical boundaries, unbalanced reporter coverage, and changing partner coverage.

Minimum columns:

- `source`: CEPII TRADHIST, COW Trade, IMF IMTS/DOTS, UNSD spot-check table, or validation source.
- `source_version`, `download_url`, `retrieval_date`, `file_checksum`.
- `year`, `flow`, `source_reporter_code`, `source_reporter_name`, `source_partner_code`, `source_partner_name`.
- `mapped_reporter_id`, `mapped_partner_id`, `entity_boundary_note`.
- `trade_value`, `currency`, `value_unit`, `reported_or_mirror`, `estimation_flag`.
- `is_valid_partner`, `partner_exclusion_reason`.
- `source_total_trade_value`, `independent_total_trade_value`, `sum_valid_partner_trade_value`, `coverage_ratio_internal`, `coverage_ratio_independent`.
- `dyad_observability_flag`: observed positive, coded zero, unreported/missing, mirror-only, aggregate/residual, boundary-recoded, or invalid partner.
- Derived outputs: raw `partner_gini`, finite-n-normalized `partner_gini_normalized`, `partner_active_count`, `top1_partner_share`, `top5_partner_share`, `hhi`, `effective_partner_count`, and coverage diagnostics.

## Measurement Rules

Raw Partner Gini is comparable only when the observed partner universe is credible. With `n` observed partners, the finite-sample upper bound of the standard non-negative Gini is approximately `(n - 1) / n`; with one observed partner, raw Gini can be zero even though trade is maximally dependent on one recorded partner. Therefore:

- Do not publish Partner Gini for reporter-year-flow cells with fewer than 5 valid observed partners.
- Treat 5-9 partners as diagnostic only.
- Require at least 10 valid partners for historical appendices and at least 20 valid partners for headline historical trends unless a source-specific validation note justifies otherwise.
- Report raw Gini and normalized Gini, where `partner_gini_normalized = partner_gini / ((n - 1) / n)` for `n >= 2`.
- Always report HHI and effective partner count, `1 / sum_j share_j^2`, beside Gini because they are easier to interpret when coverage changes.
- Top-K partner shares use the valid-partner total as the main denominator and an independent aggregate trade total as a coverage-adjusted denominator whenever an independent total exists.

## Source Stack

1. **Primary historical bilateral source: CEPII TRADHIST.** Use for the main historical series because it covers bilateral trade and gravity data over 1827-2014.
2. **Robustness source: Correlates of War Trade v4.0.** Use for a sovereign-state-only robustness panel over 1870-2014. This is not a drop-in replacement because COW drops colonies and non-sovereign territories.
3. **Postwar bridge: IMF IMTS/DOTS.** Use from 1948 onward as a modern partner-country bridge and source cross-check.
4. **Aggregate validation: Federico-Tena World Trade Historical Database.** Use aggregate polity trade over 1800-1938 to validate totals and coverage. It cannot compute partner Gini by itself.
5. **Spot checks: UNSD historical IMTS tables, national yearbooks, and League of Nations tables.** Use selected years such as 1900, 1913, 1928, 1935, 1938, 1948, 1953, and 1959 to inspect top partners and totals.
6. **Controls: Maddison Project Database 2023.** Use GDP per capita and population controls only for descriptive income or scale splits, not for constructing Partner Gini.

## Main Samples

- `historical_unbalanced`: every reporter-year-flow with valid partners and explicit coverage diagnostics. This is a diagnostic sample, not the headline trend sample.
- `historical_core_1900`: predeclared before estimation. A reporter-flow enters a window only if it has at least 20 valid partners at both endpoints, `coverage_ratio_independent >= 0.80` where an independent aggregate total exists, no unresolved reporter-boundary break inside the window, and observations for the baseline, endpoint, and at least 60% of intervening years. Candidate entities: United Kingdom, France, Germany, Netherlands, Belgium/Belgium-Luxembourg where source-defined, Italy, Austria-Hungary/Austria, Russia, United States, Canada, Australia, Japan, British India/India, Argentina, and Brazil. Entity definitions must be source-specific and documented rather than forced into modern ISO3 without notes.
- `historical_core_high_coverage`: stricter robustness sample requiring at least 30 valid partners and `coverage_ratio_independent >= 0.90`.
- `sovereign_cow_only`: COW-only robustness panel for sovereign states, useful for checking whether the CEPII pattern depends on imperial/dependent-territory coverage. It is not a replacement for the core sample.
- `postwar_bridge`: overlapping CEPII/COW/DOTS reporter-years, mainly 1948-2014, used to measure source disagreement and bridge to the existing modern rd2 Partner Gini narrative.

## Identification And Interpretation

This is a descriptive time-series/panel exercise. The source of variation is within-country time variation in the distribution of partner trade values, plus cross-country differences in levels and trends.

The design can support statements such as:

- "In the core historical sample, median export Partner Gini moved by X between 1900 and 1913 / 1913 and 1938 / 1950 and 2000."
- "The result is robust or not robust to fixed-partner-universe checks and coverage thresholds."
- "The CEPII pattern agrees or disagrees with COW and DOTS in overlapping years."

It cannot support causal claims about globalization, war, tariffs, or income unless a separate causal design is added.

## Main Threat: Expanding Partner Coverage

The key mechanical risk is that partner coverage expands over time. If early years record only major partners but later years record many smaller partners, active Partner Gini can mechanically fall even if the underlying distribution did not truly diversify. The inverse can also happen if early sources combine many small partners into an aggregate residual partner that is excluded from the vector.

The design must therefore do more than publish Partner Gini beside partner counts and coverage ratios. It must estimate how much apparent trend can be generated by source observability itself. Historical trend language is allowed only if the sign and magnitude survive the bounding envelope, synthetic censoring checks, common-reporter checks, source-overlap checks, and predeclared sample eligibility rules.

## Required Robustness Checks

1. **Source-specific exclusion registry.** Before aggregation, build a registry of source codes and labels for World, region, colony group, customs union, continent, unknown, residual, and "not elsewhere specified" partners. Exclude aggregate partners from the partner vector and count them in diagnostics.

2. **Independent-total coverage audit.** For each reporter-year-flow, compare the sum of valid bilateral partners with an independent aggregate total from Federico-Tena, national yearbooks, League of Nations, IMF, or source metadata when available. Label coverage ratios from the same bilateral source as internal coverage, not independent validation.

3. **Coverage-ratio threshold ladder.** Recompute yearly summaries requiring independent coverage ratios at `0.70`, `0.80`, `0.90`, and `0.95`. Report surviving reporter-years, countries, and whether trend signs change. If only internal coverage is available, label the result as weaker.

4. **Partner-count threshold ladder.** Recompute with minimum valid partner counts of 5, 10, 20, and 30. Cells below 5 are non-publishable; 5-9 are diagnostic only; 20 is the default headline threshold.

5. **Finite-n normalized Gini.** Report both raw Partner Gini and normalized Partner Gini, and verify that substantive trend claims do not depend on the finite-n upper-bound correction.

6. **Coverage-bias bounding envelope.** For reporter-years with known residual trade mass, compute Gini under four explicit residual allocations: all residual mass as one "other" partner, residual split equally across `m` small partners where `m` follows later-year partner-count growth, residual allocated proportionally to observed partners, and residual allocated to the top partner. Report the envelope, not only the preferred point estimate.

7. **Synthetic censoring/placebo diagnostic.** Take high-coverage later-year partner vectors and deliberately degrade them to the partner counts, coverage ratios, and top-partner-only reporting patterns observed in early years. Recompute Gini and estimate the artificial trend produced by this censoring. A historical trend is not credible if the observed trend is similar to the synthetic coverage artifact.

8. **Common-reporter balanced panels.** For each window, e.g. 1900-1913, 1913-1938, 1950-1970, 1970-2000, and 2000-2014, restrict to reporters observed at both endpoints and then to reporters observed in all years. Compare trends with the unbalanced panel.

9. **Common-partner-set windows plus observability flags.** Within each reporter and window, compute fixed-partner-universe measures using partners observed at the baseline, endpoint, intersection, and union. Distinguish true coded zeroes from source-missing dyads, mirror-only dyads, and boundary-recoded dyads. Do not silently turn source-missing dyads into zeroes in the main measure; label zero-filled versions as bounding sensitivities.

10. **Change decomposition.** Decompose endpoint changes into common-partner intensive-margin changes, partner entry/exit, residual/unobserved mass changes, and boundary-reclassification changes. This is the most direct test of whether falling Gini reflects lower concentration or broader observability.

11. **Top-K partner concentration.** Report top-1, top-3, top-5, and top-10 partner shares using both valid-partner and independent-total denominators. These are less sensitive to adding many tiny partners than Gini, although they can miss changes in the lower tail.

12. **Rank-truncated Gini with residual mass.** Recompute Gini over the largest 5, 10, and 20 partners in each reporter-year where available, and report the omitted/residual mass. This tests whether the main trend is driven by newly recorded small partners without hiding the lower-tail expansion.

13. **Source overlap checks.** Compare CEPII vs COW in 1870-2014 and CEPII/COW vs DOTS after 1948 on matched reporter-year-flow observations. Compare not only output Ginis, but also partner-level distributions, top partners, totals, entity mappings, and source-specific partner exclusions.

14. **Mirror-flow, war, and boundary sensitivities.** Where reporter data are missing or estimated, compare with partner-reported mirror flows when metadata allow. Separately mark World War I, World War II, immediate postwar reconstruction years, decolonization episodes, customs-union/reporting-unit changes, and major state-boundary changes.

15. **Coverage-adjusted residual trend diagnostic.** Model Partner Gini as a function of `log(partner_active_count)`, independent coverage ratio, reporter fixed effects, and year or decade fixed effects. This is diagnostic only. It does not correct measurement drift and should not be used as proof of a historical trend.

## Minimum Validation Checks

- No aggregate partners in the partner vector: World, regions, continents, unknown, areas not elsewhere specified, and source-specific group codes must be excluded and counted in diagnostics.
- No negative trade values enter Gini.
- Raw Gini is within `[0, 1]`, normalized Gini is within `[0, 1]`, and the finite-n denominator is recorded.
- Gini is non-publishable below 5 partners, diagnostic only for 5-9 partners, and headline-eligible only when the predeclared sample threshold is met.
- `sum_valid_partner_trade_value <= independent_total_trade_value` except where source metadata explain reexports, mirror estimates, valuation differences, or independent total incompatibility.
- Duplicate reporter-partner-year-flow keys are resolved with documented aggregation rules.
- Every source pair has a concordance audit: reporter/partner entity mapping, flow definition, valuation convention, mirror flag, total reconciliation, and top-partner overlap.
- Every output table with coded countries includes plain-English reporter and partner labels or entity notes.
- Every generated trend graph includes Partner Gini, normalized Gini or HHI/effective-partner count, partner count, coverage ratio, source regime, and boundary flags.

## Staged Implementation

### Stage 1: Design and source registry

Create `data/raw/historical_trade/source_registry.json` and a human-readable source registry with download URLs, version, checksums, licenses, citation strings, source-specific aggregate/residual partner codes, flow definitions, valuation conventions, mirror-flow rules, and independent-total availability.

### Stage 2: Source concordance and CEPII pilot

Download CEPII TRADHIST. Build `data/processed/historical_partner_gini/cepii_partner_flows.parquet`, then derive reporter-year-flow partner-Gini tables with coverage diagnostics. Before trend graphs, run the source concordance audit against independent aggregate totals and selected top-partner spot checks. Start with 1900-2014 and the candidate `historical_core_1900` reporters.

### Stage 3: Coverage diagnostics

Run the coverage-threshold, partner-count, finite-n normalization, bounding-envelope, synthetic-censoring, common-reporter, common-partner-set, change-decomposition, rank-truncated, and top-K checks. The first publishable graph should show Partner Gini with partner counts and coverage-ratio bands.

### Stage 4: Source robustness

Build the COW sovereign-state series and DOTS bridge, then compare overlapping reporter-year-flow cells against CEPII.

### Stage 5: Website and paper-facing output

Only after coverage diagnostics clear, add a historical page or appendix. Until then, the website can include a "historical extension design" subsection, but not a historical Partner Gini trend as a result. Historical samples must be labeled separately from the modern `rd2_countries` website sample; do not silently mix `historical_core_1900`, COW sovereign, DOTS bridge, and rd2 outputs.

## Research Design Verdict

The historical extension is feasible, but only if coverage is treated as part of the measurement rather than a nuisance. The publishable object should be a bundle: raw Partner Gini, normalized Partner Gini, HHI/effective partner count, partner count, independent and internal coverage ratios, source, entity-boundary note, and robustness family. A standalone 1900-to-modern line graph remains misleading unless it survives the coverage-bias envelope, synthetic censoring placebo, source-concordance audit, and source-overlap checks above.
