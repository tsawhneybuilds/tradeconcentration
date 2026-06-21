# Internal evidence ledger for the advisor memo

## Figure contracts

### Figure 1 — baseline inference

- Question: Do any preferred within-country partner-concentration models pass the formal U-shape test?
- Answer: No; all six wild-cluster bootstrap p-values exceed 0.45 and all BH q-values equal 0.841.
- Comparison: Six raw U-test p-values against the 0.05 threshold, split by exports and imports.
- Unit: Flow-measure model result.
- Sample: Baseline minimum 20 active partners; entity and year fixed effects plus log population.
- Integrity caveat: A p-value plot communicates inference, not effect size; the table retains signs and turning-point support.

### Figure 2 — robustness

- Question: Does any reasonable within-country sensitivity support a U-shape?
- Answer: No; 168 tests yield zero supported U-shapes and the minimum raw p-value is 0.203.
- Comparison: Full p-value distributions across 28 variants for each of six flow-measure outcomes.
- Unit: Flow-measure-variant model result.
- Integrity caveat: The variants change samples and measurement conventions, so the graph shows robustness of the conclusion rather than a pooled sampling distribution.

## Sources inspected

- `results/historical_partner_concentration/cadot_model_summary.csv`
- `results/historical_partner_concentration/sample_attrition.csv`
- `results/historical_partner_concentration/historical_partner_mpd_merge_attrition.csv`
- `results/historical_partner_concentration/historical_partner_build_manifest.json`
- `results/historical_partner_concentration/run_manifest.json`
- `results/historical_partner_concentration/adversarial_review.md`

## Unresolved fact

- The post-fix adversarial review was local rather than a fresh independent-agent pass.
