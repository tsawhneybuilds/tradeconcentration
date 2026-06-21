# Exercise 12 Adversarial Review

Generated: 2026-05-26

## Executive Verdict

Trust only with provenance caveats.

- The regenerated Exercise 12 outputs are internally consistent with the existing `prof_p_33` Exercise 12 aggregate.
- The run was not a raw-to-final rebuild. It finalized from `data/processed/exercise_12_export_aggregates.parquet`.
- The successful run used spill resume after an interruption. Post-review code now requires a matching spill manifest before future spill reuse.
- The validation audit passes: `results/exercise_12_tables/exercise_12_validation_audit.json`.
- Do not present the outputs as a fresh raw Comtrade rebuild unless a no-resume, no-reuse run is completed.

## Highest-Risk Findings

1. **Resolved for future runs: stale spill reuse risk.**
   The finalizer previously reused complete-looking spill CSVs without a spec fingerprint. `scripts/run_exercises_02_12.py` now writes and validates a spill manifest containing the aggregate fingerprint, item-mode/top-definition spec, sample, exclusion rules, and script hashes before `--resume-exercise-12-spill` can reuse files.

2. **Remaining caveat: existing aggregate reuse.**
   The completed run used `--reuse-exercise-12-aggregate`, so it validates the final Exercise 12 accounting from the existing aggregate, not raw Comtrade parsing. The aggregate contains 149,677,470 rows and the validation audit confirms 0 `partner_code == 0` rows and 0 `cmd_code == "999999"` rows.

3. **Resolved: alternate checkpointed runner transition schema.**
   `scripts/run_exercise_12_checkpointed.py` was still grouping size transitions on a `size` column. Current Exercise 12 transitions use `item_count`; the runner now writes the detailed transition schema consistently.

4. **Open but documented: robustness-mode merge coverage.**
   CPA robustness rows are matched-only by construction. HS harmonization diagnostics report coverage, unmatched value share, ambiguous value share, and family-size distribution. Partner-region states report World Bank and Unknown value shares.

## Data Lineage And Sample Audit

Path used by the successful run:

`exercise_12_export_aggregates.parquet -> per-reporter spill finalization -> Exercise 12 CSV/parquet/memo outputs`

Validation audit results:

- Aggregate rows: 149,677,470
- Aggregate `partner_code == 0` rows: 0
- Aggregate `cmd_code == "999999"` rows: 0
- Main headline rows: 15,827
- Net full rows: 135,300
- Gross full rows: 279,497
- Main duplicate keys: 0
- Main output equals the headline-filtered net output: true
- Net max accounting residual: 0.0001220703125
- Gross max accounting residual: 0.000244140625

The tiny accounting residuals are floating-point summation noise on dollar totals and are below the audit tolerance.

## Headline Sample Check

The headline file `results/exercise_12_tables/growth_decomposition.csv` contains only:

- `partner + top_10`
- `product + hs6_harmonized_family + top_10`
- `product_partner_cell + hs6_harmonized_family + top_10`

The gross memo table is filtered to this same headline sample and displays `item_id_mode` and `top_definition`.

## Partner-Region Check

`product_destination_region_states.csv` contains 5,046,355 rows across 33 reporters.

- Total World Bank matched value share: 0.9746677603
- Total Unknown-region value share: 0.0253322397
- Rows with usable World Bank region reliability: 4,882,012
- Rows with low reliability due to Unknown-region share above 20%: 164,343

Unknown regions are no longer mechanically 100%; they remain where World Bank matching genuinely does not cover the partner.

## Replication Checklist

Completed:

- Syntax check for the main Exercise 12 scripts.
- `python3 -m unittest discover -s tests`
- Visual explainer regeneration.
- Validation audit JSON.
- Independent adversarial review pass with the caveats above.

Not completed:

- `python3 -m pytest` because `pytest` is not installed for the repository's `python3`.
- A no-resume, no-aggregate-reuse raw-to-final rebuild.
