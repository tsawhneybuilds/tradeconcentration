# Adversarial Econometrics Review: Cadot Technical Audit

Generated: 2026-06-16T09:55:01+00:00

This was a local adversarial review, not an independent fresh-agent pass. Subagent delegation was not explicitly requested in the current user instruction.

## 1. Executive verdict

**Do not trust yet.**

- The audit report is trustworthy as a file-state and source-search inventory, and the modern broad-156 outputs can be checked from current artifacts.
- Modern broad-156 concentration and PPP regression artifacts are present when generated, but they are not a literal Cadot 1988-2006 replication.
- Prior review notes are secondary; current manifests and validation tables should be the source of truth.
- The original Cadot country list and mirror-data construction are unresolved.
- Constant PPP is correctly identified as required, but the available runner uses current WDI constant-2021 PPP, not Cadot's constant-2005 PPP vintage.

## 2. Highest-risk findings

Severity: High. Literal original-period generated panels are missing.
Why it matters: modern broad coefficients, turning points, attrition, and country coverage can be checked, but they do not answer whether the 1988-2006 Cadot paper is replicated.
Fix: implement or recover `cadot_original_1988_2006` panels, then rerun duplicate-key, attrition, and independent regression checks.

Severity: High. Original Cadot sample is not recovered.
Why it matters: a broad modern 156-country sample is not the same as Cadot's 1988-2006 mirror-data country universe.
Fix: recover the 156 list from appendix/author materials or reconstruct it from transparent Comtrade coverage rules and publish a mismatch table.

Severity: Medium. PPP base-year drift is unavoidable with current WDI.
Why it matters: turning-point dollar values are not directly comparable across constant-2005 and constant-2021 international dollars.
Fix: label the WDI vintage/base and, if possible, convert benchmark discussion using a documented PPP deflator bridge.

Severity: Medium. Product-code harmonization is not Cadot-equivalent yet.
Why it matters: Cadot harmonized HS1/HS2 to HS0 and worked on 4,991 fixed lines. Current final-data HS6 extraction can change active-line counts and Theil decomposition.
Fix: implement HS0 fixed-universe reconstruction or state that the analysis is a modern extension, not a literal replication.

## 3. Data lineage and sample audit

Current lineage has complete modern broad-156 concentration outputs when `results/samples/cadot_broad_156/three_metric_tables/` is present, plus blocked original-track status artifacts. The current `cadot_broad_156_public_availability.csv` diagnostic is:

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

Expected final units are reporter-year for regression panels and reporter-year-product for measure construction. Modern broad reporter-year panels can be audited from current outputs; literal original-period reporter-year-product panels are not present.

## 4. Merge/join audit

Expected joins are reporter metadata to Comtrade availability, reporter/ISO3 to WDI controls, and country-year outcomes to controls. Current broad runner code contains uniqueness checks and attrition tables; original-period match rates and unmatched examples are not available because that track is blocked.

## 5. Variable construction audit

Headline income should be `NY.GDP.PCAP.PP.KD`, constant PPP GDP per capita. Product-dependent measures must exclude HS6 `999999` before aggregation. Cadot-equivalent Theil requires a fixed product universe with inactive lines represented as zeros.

## 6. Specification audit

Required Cadot-comparable model form:

`Y_ct = alpha + beta_1 GDPpcPPP_ct + beta_2 GDPpcPPP_ct^2 + gamma oilshare_ct + delta_t + epsilon_ct`

with pooled, country fixed-effect/within, and between variants. Clustered or robust inference should be explicit, and turning points should be reported as `-beta_1 / (2 beta_2)` with support checks.

## 7. Inference and identification audit

The exercise is descriptive, not causal. Country fixed effects identify within-country income changes and can differ materially from pooled development-stage differences. Cluster counts, cluster-size distribution, serial correlation, and high-income leverage must be reported from the saved analytic panel.

## 8. Replication checklist

- Keep current broad artifacts regenerated from scripts; implement or reconstruct the original-period sample artifacts before making a literal Cadot claim.
- Verify no duplicate reporter-year keys and no duplicate ISO3 mappings.
- Verify no HS6 `999999` in product-dependent panels.
- Re-estimate one pooled and one within model directly from the saved panel.
- Report complete attrition from selected countries to analytic rows/clusters.
- Run Section 16 and microstate robustness.

## 9. Minimal patch plan

- Add original Cadot country-list recovery/reconstruction code before exposing new pipeline choices.
- Add a sample manifest that stores country-list provenance, HS harmonization, PPP indicator/base, residual-code rule, and mirror/direct data rule.
- Add regression-panel validation outputs and independent re-estimation scripts.

## 10. Questions for the researcher

- Is a current Comtrade subscription key available for original-period HS6 mirror-data reconstruction?
- Should the paper-level replication prioritize literal Cadot HS0 harmonization, or is a modern HS final-data extension acceptable if clearly labeled?
