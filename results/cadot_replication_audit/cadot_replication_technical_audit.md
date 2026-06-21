# Cadot Replication Technical Audit

Generated: 2026-06-16T09:55:01+00:00

## 1. Executive Verdict

**Verdict: do not claim a best-possible Cadot replication from this checkout yet.**

We agree with Cadot only at the level of the research target: the relevant test is a development-stage export-diversification hump using HS6 product concentration, active lines, oil controls, microstate checks, and constant-PPP income. The current checkout now contains a modern broad-156 concentration bundle, but it still does not contain a literal 1988-2006 Cadot-original replication track.

Modern broad-156 three-metric bundle present: yes. Broad-156 PPP hump regressions present: yes. The original Cadot-period replication is not implemented as a completed sample track in this checkout.

`workinprogress.html` status: not present in the checked locations. Therefore "Behind the Hump" cannot be treated as accurate and updated from this checkout alone; it needs regeneration from saved panels plus a fresh validation pass.

## 2. What Cadot Did

- Published article: Cadot, Carrere, and Strauss-Kahn, *Review of Economics and Statistics*, 2011, 93(2), 590-605.
- Public metadata and the local paper extraction report 156 countries, 19 years, HS6 exports, and 4,991 harmonized product lines.
- The paper studies country-year export concentration over development using Gini, Herfindahl-Hirschman, Theil, and the number of active HS6 export lines.
- Headline income is GDP per capita PPP in constant 2005 international dollars from WDI; current-dollar income is not Cadot-comparable.
- The local extraction says the baseline regressions exclude microstates and use 2,497 observations for 141 countries over 1988-2006, with an average of 18 observations per country.
- The annex says Cadot harmonized HS1 and HS2 back to HS0, added missing inactive lines as zeros over a 4,991-product universe, and used mirrored trade data to reduce exporter-reporting error.
- The headline result is a diversification hump: concentration falls and active product counts rise with income, then concentration rises again mostly through the extensive margin.
- Cadot reports pooled, within, and between estimates. Local notes put pooled/within/between turning points mostly around PPP $21,000-$29,000, with a common shorthand benchmark around PPP $25,000.
- Cadot treats HS Section 16 as a measurement concern and reports robustness after coarser aggregation or exclusion; we need the same sensitivity before making a paper-level claim.

Measure definitions for our replication report:

- Product Gini: inequality of export values across HS6 products within a reporter-year after excluding HS6 `999999`; higher values mean exports are more concentrated in fewer products.
- Herfindahl-Hirschman index: `HHI_{ct} = sum_p s_{cpt}^2`, where `s_{cpt}` is product `p`'s share of reporter `c` exports in year `t`; higher values mean more concentration.
- Theil: `T_{ct} = (1/N) sum_p (x_{cpt}/mu_{ct}) log(x_{cpt}/mu_{ct})` on the fixed product universe with inactive products coded zero where required by the Cadot design; higher values mean more concentration.
- Active line count: count of HS6 products with positive exports in reporter-year `ct`; higher values mean a broader extensive margin.

## 3. Replication Package Status

No public replication package was located in the targeted search as of June 16, 2026. This is a source-audit finding, not proof that no private package exists.

Searched sources included EconPapers/RePEc, IDEAS/RePEc, World Bank OKR, MIT Press Direct, SSRN, HAL/CERDI/CEPR/CEPREMAP working-paper trails, and targeted web queries for `REST_a_00078`, `Cadot Carrere Strauss-Kahn replication package`, `data`, `Stata`, `supplementary`, and `Dataverse`.

The World Bank OKR metadata has a `Link to Data Set` heading, but the inspected page has no visible dataset URL. MIT Press/RePEc/SSRN/IDEAS expose article or working-paper metadata, not code/data files.

See `cadot_replication_source_audit.csv` for the source-by-source trail.

## 4. Our Current State

Original Cadot-track artifacts missing in this checkout: 10 expected original/extended files/directories are absent.
Prior local review docs present: 3.
Data access blocker present: yes.

The codebase already contains important pieces:

- `scripts/trade_concentration_pipeline.py` defines `cadot_broad_156` as a research-only broad sample with 2000-2024, at least 19 HS final-data years, and an expected reporter count of 156.
- `results/samples/cadot_broad_156/three_metric_tables/` now contains a modern broad-156 Gini/Theil/HHI concentration bundle and validation checks.
- `scripts/run_ppp_hump_regressions.py` uses World Bank `NY.GDP.PCAP.PP.KD`, labeled GDP per capita PPP in constant 2021 international dollars. This is directionally correct for constant PPP, but its WDI vintage/base differs from Cadot's constant 2005 PPP.
- `tests/test_cadot_broad_sample.py` checks the broad sample defaults and exact-156 failure behavior under mocked availability.
- Prior referee notes report successful earlier broad and constant-PPP runs; current broad three-metric artifacts are present, while literal original-period outputs remain absent.

Blocking issues in this checkout:

- The exact Cadot 156-country list is not isolated in current public metadata or local extraction; the paper's regression sample uses 141 nonmicrostate countries after exclusions.
- Original-period mirror-import reconstruction is not implemented as a completed runnable track.
- Broad-156 PPP hump regressions are present under `results/samples/cadot_broad_156/cadot_broad_ppp_hump_regression_tables/`.

## 5. Result Comparison

| Outcome | Cadot benchmark | Current checkout status | Agree/disagree label |
|---|---|---|---|
| Export product concentration | Hump in concentration with income; reconcentration after turning point | Modern broad concentration panel exists; original-period regression panel absent | Modern extension testable, literal replication not yet |
| Active HS6 line count | Inverted concentration pattern: active lines rise, then flatten/fall | Modern active-count outcome exists; original-period active-line panel absent | Modern extension testable, literal replication not yet |
| Theil decomposition | Extensive margin is the main channel | Modern fixed-universe product Theil exists; original Cadot HS0/4,991 universe absent | Partial modern mechanism evidence only |
| Import concentration | Not Cadot's headline; useful modern extension | Existing repo has import runners, but no current Cadot result artifact | Extension only |
| Partner concentration | Not Cadot's product-diversification object | Existing partner rules are separate and may include `999999` when only summing to partner totals | Not a Cadot replication |
| Modern broad 156 | Not Cadot period; 2000-2024 modern credibility sample | Three-metric bundle present; PPP regressions present | Modern diagnostic, not literal replication |

The most defensible current statement is: the modern broad-156 concentration bundle is now present and validated, but literal Cadot-original replication remains undone until the country list, mirror data, and HS0 fixed universe are recovered/reconstructed.

## 6. Country Coverage

Required tracks:

- `cadot_original_1988_2006`: closest original-period track. Not currently present as generated data or a completed pipeline choice. Needs exact Cadot country list or a transparent reconstructed list from 1988-2006 HS/mirror coverage.
- `cadot_original_countries_extended`: same country universe extended to latest final-data availability. Not currently present. Feasible after the original list is recovered/reconstructed and HS revision breaks are documented.
- `cadot_broad_156_modern`: present in code under the current sample name `cadot_broad_156` as a modern 2000-2024 design. The modern concentration bundle is present; PPP regression outputs depend on the broad PPP runner.

Cadot-period all-country feasibility: yes in principle, but not proved here. The public paper does not expose a ready 156-country list in inspected metadata. The local extraction gives the nonmicrostate regression sample count of 141 countries, not the full pre-exclusion 156 list.

Extended-period feasibility: yes after original-country recovery, but it will necessarily be an unbalanced panel because Comtrade final-data availability, country codes, state succession, and WDI coverage differ over 1988-2024/2025.

Current availability-cache diagnostic:

```json
{
  "availability_cache_exists": true,
  "columns": [
    "datasetCode",
    "typeCode",
    "freqCode",
    "period",
    "reporterCode",
    "reporterISO",
    "reporterDesc",
    "classificationCode",
    "classificationSearchCode",
    "isOriginalClassification",
    "isExtendedFlowCode",
    "isExtendedPartnerCode",
    "isExtendedPartner2Code",
    "isExtendedCmdCode",
    "isExtendedCustomsCode",
    "isExtendedMotCode",
    "totalRecords",
    "datasetChecksum",
    "firstReleased",
    "lastReleased"
  ],
  "max_years": 25,
  "min_years_among_19plus": 19,
  "path": "data/raw/comtrade/availability/cadot_broad_156_public_availability.csv",
  "reporters_in_cache_2000_2024": 206,
  "reporters_with_19plus_hs_years_2000_2024": 158,
  "rows": 5396
}
```

Interpretation: the cached public availability file alone yields 158 reporters with at least 19 HS years in 2000-2024. The implemented `cadot_broad_156` selector is stricter because it also applies reporter-reference filters for active non-group reporters, valid ISO3, and non-expired metadata; prior tests require that final selector to fail unless it returns exactly 156.

## 7. Rebuild Implementation Plan

Use bounded stages; do not run all heavy work at once.

1. Recover or reconstruct the Cadot country list.
   - Search the paper appendix, working papers, author pages, and any table footnotes for the full 156.
   - If unavailable, reconstruct from Comtrade mirrored-import HS6 coverage in 1988-2006 and write a discrepancy table against the paper's counts.
2. Implement `cadot_original_1988_2006` only after the country-list rule is explicit.
   - Period exactly 1988-2006.
   - Harmonize HS1/HS2 to HS0 or document why current HS final-data extraction cannot reproduce that vintage.
   - Exclude `999999` from product-dependent measures before aggregation and add a labeled sensitivity if Cadot's residual-code handling remains unknown.
3. Implement `cadot_original_countries_extended` using the same country universe.
   - Do not impute absent years.
   - Report HS revision breaks and country-year coverage.
4. Keep `cadot_broad_156_modern` as a 2000-2024 sensitivity.
   - Fail loudly unless the official cached availability snapshot selects exactly 156 reporters.
5. Build saved analytic panels before regressions.
   - Enforce unique reporter-year keys.
   - Save row-count attrition at each filter, merge, and complete-case step.
6. Estimate pooled, country-FE/within, between, and sensitivity models.
   - Headline income: constant PPP GDP per capita, not current USD.
   - Report turning points in the WDI base/vintage used and support checks against min/max and p05-p95.
7. Rerun the website explainer only from current saved panels.
   - Label it as research/audit output unless it uses website-default `rd2_countries`.

CPU/memory-safe command pattern:

```bash
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1
/usr/bin/nice -n 10 python3 scripts/trade_concentration_pipeline.py --country-sample cadot_broad_156 --stage process --exercise 1 --chunk-rows 250000 --memory-limit-gb 12
/usr/bin/nice -n 10 python3 scripts/trade_concentration_pipeline.py --country-sample cadot_broad_156 --stage process --exercise 2 --chunk-rows 250000 --memory-limit-gb 12
/usr/bin/nice -n 10 python3 scripts/run_ppp_hump_regressions.py --country-sample cadot_broad_156
```

For original Cadot tracks, do not start the expensive process stage until the country-list and mirror-data rules are explicit.

## 8. Bottom-Line Assessment

We have not yet replicated Cadot in the best possible way in this checkout. We have current modern broad-156 concentration results, but not the original 1988-2006 mirror-data reconstruction, not the exact Cadot 156-country list, and not the exact Cadot HS0 4,991-line universe.

"Behind the Hump" should be treated as not currently certified. It can become accurate after regenerating from current constant-PPP panels, labeling modern versus original-period tracks, and passing an adversarial review.

Before making a paper-level claim, the project needs: exact or transparently reconstructed Cadot country coverage, 1988-2006 mirror/Harmonized-System handling, saved concentration and active-line panels, complete attrition diagnostics, constant-PPP regressions, Section 16 robustness, and independent re-estimation from saved panels.
