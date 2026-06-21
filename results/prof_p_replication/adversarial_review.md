# Adversarial Replication Review: Prof P Paper Inventory

Review timestamp: 2026-05-24 12:32 IST. This was a local review, not an independent fresh-agent pass, because no subagent delegation was requested and the repo-scoped `adversarial-econometrics-review` skill referenced by the repository instructions was not installed in this session. I used the project review checklist and focused on data lineage, sample construction, constructed concentration measures, exclusion rules, and specification drift.

## Verdict

The replication inventory is usable as an audit map and now explains the main partner-concentration failure mode. It should still be described as a split output: clean modern Comtrade/no-`999999` rerun plus a paper-like diagnostic convention. The diagnostic convention is not the preferred economic measure, but it is the right way to understand why several Table 3-4 results initially looked wrong.

## Findings

1. **Blocked HS10 objects are handled correctly.** Figures 1-2 and Table 1 require UC Davis CID HS10 data. No local HS10 files were present, and the CID page probe returned HTTP 403, so the script writes paper references and blocks exact replication instead of substituting HS6 diagnostics.

2. **World-trade claims are handled correctly as blocked.** Section 6 needs all-world 2001 HS6 totals. The local canonical panel is the 33-country Prof P sample, so the world Gini, top-20 overlap, bottom-half product share, and bottom-half country share are not reproducible from current local artifacts.

3. **Main HS6 product concentration is closer under an HS concordance diagnostic.** The clean H1 Table 2 product Ginis differ modestly, with max absolute Gini difference 0.0159, but active product counts remain higher after raw world/no-world sensitivity checks. The new WCO HS1996-to-HS2002 first-listed-target aggregation reduces mean absolute product-count error from 132.3 to 45.4 and median absolute count error from 139.5 to 47.5, while keeping mean absolute Gini error at 0.0031. This is the best Table 2 improvement found, but it should remain a sensitivity because one-to-many HS splits cannot be uniquely allocated from 2001 H1 source data.

4. **The large Table 3-4 partner mismatches are explained.** The clean no-world partner construction still has large mismatches for Greece, India, and Finland exports and Slovakia, Switzerland, and Turkey imports. In raw files, counting `partnerCode == 0` (`World`) as a destination/source almost exactly reproduces those six paper outliers: max top-5 difference 0.52 percentage points and max partner-Gini difference 0.0028 among the six rows.

5. **Key qualitative orderings now have an explicit check.** India has higher product Gini than China for both exports and imports in both paper and modern clean outputs. India only has higher export partner Gini than China under the paper-like world-partner convention; the clean no-world convention reverses that ordering.

6. **US top-product partner/source tables are effectively replicated.** Tables 5 and 6 are close: max product-Gini differences are 0.0003 and 0.0063, and max top-share differences are below 1 percentage point.

7. **Table 7 still has a localized mismatch.** Bilateral product Ginis are close, but the Japan import top-200 share differs by 29.23 percentage points. This remains a separate follow-up item and should not be hidden by the Table 3-4 diagnosis.

8. **Appendix top-25 tables mostly replicate by code and value.** Germany, Japan, China, India, and most US export/import rows are close. US import Appendix A6 has all paper codes in the modern top 25 but only 15 same-rank matches, driven by rank swaps and lower crude petroleum value in the modern data.

9. **`999999` guardrail passed.** Generated output code-column scan reports zero exact `999999` rows. The script filters HS6 `999999` before product, product-partner, appendix, raw product sensitivity, and raw partner sensitivity outputs.

## Required Follow-Ups Before Strong Claims

- Obtain or reconstruct the UC Davis CID HS10 2001 files to reproduce Figures 1-2 and Table 1 exactly.
- Build or load all-world 2001 HS6 totals for Section 6.
- Decide whether final paper-facing tables should present only the clean no-world/no-concordance rerun, or also show the paper-like HS2002 concordance and world-partner diagnostics.
- Investigate Table 7 Japan import top-200 share separately.
- Double-check manually transcribed paper targets against the PDF before using this as a publication-quality replication appendix.
