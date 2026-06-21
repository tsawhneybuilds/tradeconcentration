# Post-Fix Adversarial Review: Cadot Non-Energy Visualization

## 1. Executive verdict

**Trustworthy for current purpose**

- The corrected filter retains only `capital_goods`, `intermediates`, and `final_consumption` before LT/HGL conversion.
- All checkpoint inventories, manifest hashes, cardinalities, formulas, contributions, labels, and site-loader checks pass.
- Independent raw-data recomputations spanning H1, H4, and H6 reproduce checkpoints and final metrics.
- The two HS1992 `271000` top-product rows are legitimate LT/HGL targets generated from mapped intermediate source codes, not retained energy or ambiguous source rows.
- Remaining issues concern archival reproducibility and interpretation of harmonized target labels, not the validity of the rebuilt results.

This was an independent fresh-agent pass using the `adversarial-econometrics-review` and `empirical-reporting-replication` instructions.

## 2. Highest-risk findings

### Cleared: ambiguous and energy products are excluded correctly

The builder now uses an explicit whitelist:

- `capital_goods`
- `intermediates`
- `final_consumption`

Across 4,136 world files, diagnostics record exclusion of 33,609,722 ambiguous rows worth about $67.56 trillion and 1,981,191 energy rows worth about $95.48 trillion. These exclusions occur before LT/HGL conversion.

### Cleared: HS1992 `271000` is not contamination

The only displayed occurrences are Aruba 2016 and 2023. They arise from H4 source codes `271099` and `271091`, classified as intermediates. H4 energy codes that can also map into target `271000` were excluded before conversion.

The target label remains petroleum-related because HS1992 `271000` is a harmonized family combining later-revision source codes with different BEC uses. This is a labeling caveat, not a filtering failure.

### Low: archival source provenance can be improved

The manifest records output hashes and software versions, but a publication archive should also record the final Git commit or source-script hashes.

### Low: future checkpoint reuse is existence-based

The reviewed run used `--fresh-checkpoints`, so stale reuse did not affect it. Future runs would be safer with processing-signature checks for code, mapping, weights, and raw inputs.

## 3. Data lineage and sample audit

Verified path:

1. UN Comtrade annual reporter files.
2. Positive, nonaggregate six-digit HS rows.
3. `partnerCode == 0` excluded.
4. Source HS6 `999999` excluded.
5. Approved BEC mapping joined many-to-one.
6. Only the three mapped non-energy bins retained.
7. LT/HGL weighted conversion to HS1992/H0.
8. Reporter-year product and world-support checkpoints.
9. Annual metrics, snapshots, top products, and drivers.
10. Hash-validated site payload.

Observed cardinalities:

- 4,136 world files and diagnostic checkpoints.
- 3,787 Cadot product checkpoints across exactly 156 reporters.
- 349 non-Cadot markers.
- 3,756 nonempty annual import rows with zero duplicate keys or missing metric values.
- Coverage from 2000 through 2024, with 15–25 available years per reporter.
- 143 reporters include 2000; 132 include 2024.
- Fixed universe: 4,924 products for imports and exports.
- 468 snapshots, exactly three per reporter.
- 4,680 top-product rows, exactly ten per reporter-snapshot.
- 468 driver rows, exactly three metrics per reporter.

No balanced-panel restriction is imposed.

## 4. Merge/join audit

- BEC mapping is many-to-one with unique classification–HS6 keys. Missing or ambiguous mappings are explicitly classified and excluded.
- LT/HGL conversion is an intentional many-to-many expansion. Source weights sum to one within numerical precision, missing targets trigger an error, and converted value is preserved.
- Maximum checkpoint conversion residual is `0.0009765625`, negligible at the data scale.
- Every displayed top product has an HS1992 plain-English label.
- No `999999` appears in top products or the world universe.
- All manifest-listed output hashes match the actual files.
- The site loader enforces hashes and structural invariants.

## 5. Variable construction audit

Active-positive Gini:

\[
G=\sum_{r=1}^{n}\frac{n-2r+1}{n}s_r
\]

Fixed-universe Theil:

\[
T=\sum_{i:s_i>0}s_i\log(s_iK), \qquad K=4924
\]

Raw HHI:

\[
HHI=\sum_i s_i^2
\]

Across all 3,756 nonempty checkpoints, independent recomputation produced maximum discrepancies of:

- Total value: $0.000488.
- Gini: \(1.44\times10^{-15}\).
- Theil: \(4.44\times10^{-15}\).
- HHI: \(3.33\times10^{-16}\).

Bucket shares and metric contributions reconcile at floating-point precision. Every selected driver is the bucket with the largest absolute start-to-end contribution change.

## 6. Specification audit

This is descriptive measurement rather than regression analysis.

- Unit: reporter–year–HS1992 product family.
- Flow: imports for the non-energy visualization.
- Period: available observations from 2000 through 2024.
- Sample: exact 156 Cadot reporters.
- Product treatment: mapped non-energy source products only.
- Theil universe: positive `world_broad` mapped non-energy HS1992 support.
- Snapshots: earliest, upper-middle available observation, and latest.
- Driver: largest absolute rank-bucket contribution change.

The implementation matches the intended design.

## 7. Inference and identification audit

No regression inference, standard errors, clustering, or causal identification is involved.

Interpretation must remain descriptive because reporter coverage varies by year, active-positive Gini conditions on positive products, Theil incorporates a fixed-universe inactive margin, and harmonized HS1992 labels do not necessarily describe every later-revision source product mapping into the family.

## 8. Replication checklist

Completed:

- Fresh rebuilding of all checkpoints.
- Exact raw/checkpoint inventory comparison.
- Verification of all output hashes.
- Targeted unit tests.
- Full metric reconciliation.
- Independent raw-to-output recomputation for selected H1, H4, and H6 reporter-years.
- Independent `271000` source-code decomposition.
- Site-loader execution and browser-payload inspection.
- Shared econometrics graph query for replication requirements.

For an archival release, additionally record source-script and input hashes plus the final Git commit.

## 9. Minimal patch plan

No corrective patch is required before current descriptive use.

Optional improvements:

1. Add source-script and input hashes to the manifest.
2. Add checkpoint processing signatures for future reuse.
3. Explain that HS1992 labels describe harmonized targets, not necessarily the BEC use of every contributing source code.
4. Optionally expose source-bin provenance for top harmonized products such as `271000`.

## 10. Questions for the researcher

No unresolved question materially affects the current results.

The rebuilt non-energy visualization artifacts are cleared for current descriptive use and website publication.
