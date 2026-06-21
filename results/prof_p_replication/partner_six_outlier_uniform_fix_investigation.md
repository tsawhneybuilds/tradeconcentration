# Partner Six-Outlier Uniform-Fix Investigation

Date: 2026-05-26

Question: can the six large Table 3-4 partner top-five deviations be reduced by a rule applied uniformly to all 33 countries and both flows?

## Verdict

No uniform rule tested improves the full-sample replication relative to the current default:

- numerator: five largest actual partners;
- denominator: `partnerCode == 0` (`World`) from the all-commodity `TOTAL` row;
- partner count and partner Gini: actual partners only, excluding `World`.

The current default remains the best full-sample convention among the tested uniform variants. The six rows can be made much closer with EU/bloc aggregation or by counting `World` as a partner, but those rules badly damage the fit for the other countries and/or break the meaning of a country-partner concentration measure.

## Current Default Fit

From `partner_world_denominator_metrics_summary.csv`:

| Flow | Mean abs top-5 diff | Median abs top-5 diff | Max abs top-5 diff | Within 1pp | Within 2pp |
|---|---:|---:|---:|---:|---:|
| Exports | 2.6716 pp | 0.0425 pp | 27.9493 pp | 28/33 | 29/33 |
| Imports | 2.0446 pp | 0.0415 pp | 25.7025 pp | 26/33 | 29/33 |

The actual-partner sum equals the `World` row to numerical precision, so using `World` as denominator is effectively the same as using the sum of actual partners.

## Uniform Variants Tested

Already-tested variants:

- exclude `999999` versus include `999999` in partner totals;
- use `cmdCode == TOTAL` versus summed HS6 detail;
- include `World` as a partner uniformly;
- drop residual/non-country partner buckets;
- collapse selected historical partner aliases;
- apply positive-value thresholds;
- use alternative export/import flow codes;
- use alternative value columns for imports.

Additional variants tested here:

- top four or top six actual partners instead of top five;
- country-only partners;
- dropping `nes` and aggregate-region partner codes;
- collapsing EU15, EU25, EU27;
- collapsing EU15 plus China/Hong Kong/Macao;
- collapsing major blocs: EU15, NAFTA, China/Hong Kong/Macao, EFTA, ASEAN 2001, MERCOSUR;
- accidentally aggregating all HS hierarchy rows, including HS2/HS4/HS6 and/or `TOTAL`.

Outputs:

- `partner_uniform_additional_variant_summary.csv`
- `partner_uniform_additional_variant_detail.csv`
- `partner_uniform_six_country_top_partners.csv`
- `partner_uniform_all_hs_level_variant_summary.csv`
- `partner_uniform_all_hs_level_variant_detail.csv`

## Best Full-Sample Variant

The current default is still best.

Next-best full-sample alternatives are worse:

- country-only partners: export mean abs top-five error rises to 2.8139 pp; import rises to 2.9895 pp.
- top six actual partners: export mean abs error rises to 5.7717 pp; import rises to 5.1052 pp.
- EU15 collapse: export mean abs error rises to 18.9615 pp; import rises to 19.6114 pp.
- all HS hierarchy rows: top-five shares exceed 100 percent in many rows, so this is not a viable convention.

## Six-Outlier Behavior

EU/bloc aggregation is the only uniform family that materially helps the six rows without using `World` as a partner.

| Country | Flow | Paper | Current default | EU15 collapse | Major-bloc collapse |
|---|---|---:|---:|---:|---:|
| Finland | Exports | 69.6 | 44.9 | 72.2 | 75.6 |
| Greece | Exports | 66.6 | 38.7 | 62.1 | 63.0 |
| India | Exports | 67.8 | 40.2 | 58.1 | 64.9 |
| Slovakia | Imports | 80.4 | 65.0 | 85.4 | 85.4 |
| Switzerland | Imports | 78.2 | 61.0 | 86.3 | 87.6 |
| Turkey | Imports | 68.7 | 43.0 | 66.5 | 67.5 |

But this is not a credible default because it collapses many country partners into regional/bloc partners. That makes the full sample much worse and reduces partner counts sharply. For example, EU15 collapse changes the six-row counts by roughly 12-16 partners for several rows, while the paper's partner counts are often within one or two partners of the actual-country construction.

## Replication-Package And Vintage Search

No public author replication package was found in searches of:

- LSE Research Online metadata;
- IDEAS/RePEc and EconPapers;
- Wiley DOI/supporting-information searches;
- Dataverse, Zenodo, OpenICPSR-style searches;
- Internet Archive CDX filename searches for the six local bulk-file names.

Local raw-file publication dates are mixed: the six outlier reporters are not all late modern revisions. Greece, India, Finland, and Slovakia have local files dated 2002-2005, while Switzerland and Turkey are 2022 revisions. That weakens a pure "modern vintage" explanation for all six rows.

The stronger hypothesis remains extraction-interface/query convention: the old Comtrade/WITS interface allowed `WORLD` as a pre-aggregated partner and also allowed country groups. The six-row pattern is consistent with `World` being counted in the top-five partner list for those rows, but not consistently across the table.

## Recommended Treatment

Do not adopt EU/bloc aggregation or `World`-as-partner as the main measure. Keep the current default and document the six rows as a paper-forensic mismatch:

> Tables 3-4 are replicated with the five largest actual partner countries divided by the Comtrade World total. Most rows match extremely closely. Six rows match the paper only under a diagnostic convention that counts `World` as a partner, which is not used as the main concentration measure.
