# Local Adversarial Review: Table 3-4 World-Denominator Rerun

Generated after `PROF_P_RAW_HS6_CACHE_MAX_ITEMS=1 PYTHONPATH=scripts python3 scripts/replicate_prof_p_paper.py`.

This was a local review, not an independent fresh-agent pass, because subagent delegation was not explicitly requested.

## Executive Verdict

Mostly trustworthy for the current diagnostic purpose.

- The default Table 3-4 outputs now use all-commodity `TOTAL` partner rows, with the five largest actual partners in the numerator and `partnerCode == 0` (`World`) as the denominator.
- `World` is excluded from partner count and partner Gini construction.
- The actual-partner sum equals the World row to numerical precision, so the World-denominator convention is effectively identical to using the actual-partner sum as denominator.
- The six large deviations remain under the uniform World-denominator rule; they only match the paper if `World` is counted as a top-five partner, which is not a defensible uniform partner-concentration measure.

## Checks Run

- `python3 -m py_compile scripts/replicate_prof_p_paper.py`
- `python3 scripts/replicate_prof_p_paper.py --self-test`
- `PROF_P_RAW_HS6_CACHE_MAX_ITEMS=1 PYTHONPATH=scripts python3 scripts/replicate_prof_p_paper.py`
- `PYTHONPATH=scripts python3 -m unittest tests/test_concentration_metrics.py tests/test_prof_p_site_artifacts.py`
- Recomputed Table 3-4 top-five shares directly from `partner_totalcmd_2001_diagnostic.csv`.

## Data Lineage

- Raw source: `data/raw/comtrade/bulk/COMTRADE-FINAL-CA<reporter>2001H1*.gz`.
- Filter: `flowCode == X` for exports and `flowCode == M` for imports.
- Commodity scope: `cmdCode == TOTAL`, so partner totals include all commodity codes, including residual commodity buckets.
- Partner scope for numerator/count/Gini: positive actual partner rows with `partnerCode != 0`.
- Denominator: positive `partnerCode == 0` World row, with actual partner sum used only as fallback if the World row is unavailable.
- Final outputs: `table_3_export_partner_concentration_comparison.csv`, `table_4_import_partner_concentration_comparison.csv`, `partner_world_denominator_metrics_detail.csv`, and `partner_world_denominator_metrics_summary.csv`.

## Highest-Risk Findings

1. **World denominator does not explain the six large paper deviations.** Actual partner totals equal the World row to within `1.32e-09` in ratio terms, so switching the denominator to World changes essentially nothing.
2. **World-in-numerator matches those six rows but fails uniformly.** If `World` is counted as a top-five partner, the six outliers become close to the paper, but the aggregate fit becomes bad for the rest of the sample.
3. **The remaining explanation is likely a paper/extraction convention issue, not denominator arithmetic.** The diagnostic points to possible accidental inclusion of the World aggregate as a partner in specific paper rows, or some extraction-interface behavior that created that effect.

## Validation Results

- Direct recomputation from partner totals produced `0` validation errors.
- `partnerCode == 0` appears once for each country-flow: `66` World rows.
- Table 3 export mean/median/max absolute top-five difference: `2.6716 / 0.0425 / 27.9493` percentage points.
- Table 4 import mean/median/max absolute top-five difference: `2.0446 / 0.0415 / 25.7025` percentage points.

## Minimal Patch Recommendation

Keep the current default: top five actual partners over the World denominator, excluding World from partner count and Gini. Report the World-in-numerator version only as a forensic diagnostic, not as the main measure.
