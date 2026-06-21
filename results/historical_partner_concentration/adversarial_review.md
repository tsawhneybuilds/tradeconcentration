# Adversarial econometrics review

Local adversarial pass completed on 2026-06-19 after the corrected exact rerun. This was not a fresh delegated subagent review, because current tool policy only permits spawning subagents when the user explicitly asks for delegation.

## Executive verdict

Verdict: `Mostly trustworthy`

- The raw-to-panel lineage is now auditable and key-count checks pass: TRADHIST totals match the documented 2,495,357 rows, and all final keys are unique.
- The earlier high-risk implementation defects are fixed in the audited outputs: year-specific partner-universe filtering, unsupported pooled-turning-point country episodes, and the accidental fixed-sample `log_population` restriction.
- USSR and RUS are cleanly separated in the panel: USSR appears only through 1991 and RUS begins in 1992 with zero overlap.
- The exact runner completed successfully on the corrected panel, and the focused validation suite passes (`34 passed`).
- The main empirical conclusion is weak/null rather than overclaimed: no specification in `cadot_model_summary.csv` is classified as `supported_u_shape`.
- Remaining caution is about design limits, not an obvious coding defect: only 13 entity clusters, uneven cluster sizes, and Maddison attrition for some entities.

## Highest-risk findings

### 1. Medium severity — independent fresh-agent review requirement is still unmet

- What happened: this review is local rather than a fresh independent reviewer pass.
- Why it matters: the repo specification asked for an independent adversarial review after major empirical pipelines.
- How to verify: compare this file with the repo instruction and the current tool policy that blocks delegation absent an explicit user request.
- Exact fix / next diagnostic: run the same audit through a fresh reviewer agent or external reviewer after the user explicitly authorizes delegation.

### 2. Medium severity — inference remains fragile because there are only 13 entity clusters

- What happened: the preferred within-country baseline uses 13 entity clusters, with the smallest cluster sizes equal to 23 observations for RUS and 67–68 for USSR.
- Why it matters: fixed-effects quadratic turning-point inference is sensitive in very small-cluster panels; conventional clustered standard errors are especially weak here.
- How to verify: inspect `results/historical_partner_concentration/cadot_model_summary.csv` and cluster-size diagnostics from the primary regression sample.
- Exact fix / next diagnostic: keep wild-cluster bootstrap as the headline inferential device, avoid causal language, and treat any marginal result as fragile unless it survives additional design changes.

### 3. Medium severity — MPD coverage gaps materially change the preferred within-country sample

- What happened: Maddison GDP-per-capita is missing for 127 entity-years per flow and population is missing for 196 entity-years per flow. Missing GDP per capita is concentrated in ARG (90), PRT (24), URY (64), and USSR (76) entity-years.
- Why it matters: preferred models with `log_population` run on 1,670 export observations and 1,634 import observations rather than the full quality-eligible trade panel.
- How to verify: inspect `results/historical_partner_concentration/historical_partner_mpd_merge_attrition.csv` and `results/historical_partner_concentration/sample_attrition.csv`.
- Exact fix / next diagnostic: keep no-interpolation baseline, but report natural-sample and no-population specifications side by side whenever discussing coefficient changes.

### 4. Low severity — the label `suggestive_only` can be read too generously

- What happened: the only within-country row close to a diversification/reconcentration narrative is Export Theil in the preferred within specification, but its U-test p-value is 0.455 and BH q-value is 0.841.
- Why it matters: readers may overread the label despite non-significance.
- How to verify: inspect the preferred baseline rows in `cadot_model_summary.csv`.
- Exact fix / next diagnostic: when writing results, translate `suggestive_only` as “non-significant sign pattern only, not evidence of a supported U-shape.”

## Data lineage and sample audit

Raw-to-final path reconstructed from the audited artifacts:

1. Raw bilateral TRADHIST files 1–3 are stored under `data/raw/historical_trade/tradhist/`.
2. `scripts/build_historical_partner_concentration.py` reads the three bilateral files plus TRADHIST gravity/codebook files and MPD 2023.
3. Reporter-partner-year-flow observations are filtered to the 13 target entities, cleaned, directionally mapped to exports/imports, and written to `data/processed/historical_partner_concentration/tradhist_partner_flows.parquet`.
4. Country-year-flow concentration panels are built and written to the long and wide parquet files.
5. `scripts/run_historical_partner_cadot.py` constructs baseline and sensitivity variants, runs the regression ladder, then writes model and episode outputs.

Confirmed counts and keys:

- TRADHIST total raw rows: 2,495,357.
- Selected source rows after restricting to the 13 entities: 439,151.
- Partner-flow rows: 460,729.
- Partner-flow unique key count (`entity_id`, `partner_id`, `year`, `flow`): 460,729.
- Long panel rows: 4,476.
- Long-panel unique key count (`entity_id`, `year`, `flow`): 4,476.
- Wide panel rows: 2,238.
- Wide-panel unique key count (`entity_id`, `year`): 2,238.
- Main-panel year-universe violations: 0.

Entity boundary audit:

- USSR span: 1827–1991, 165 years.
- RUS span: 1992–2014, 23 years.
- USSR/RUS overlap years: 0.

This is not a balanced panel. Coverage varies by entity, by flow, and by whether the partner count threshold for valid concentration metrics is met.

## Merge/join audit

Main audited join:

- Merge target: MPD 2023 GDP per capita and population onto the entity-year trade panel.
- Expected cardinality: many trade-flow rows to one MPD entity-year row.
- Mapping rules: explicit countrycode/name mapping, including TRADHIST `USSR -> MPD USSR` through 1991 and TRADHIST `RUS -> MPD Russia` from 1992.

Observed attrition:

- Export rows in merge audit file: 2,238.
- Import rows in merge audit file: 2,238.
- Missing GDP per capita: 127 rows per flow.
- Missing population: 196 rows per flow.

Missing GDP per capita is concentrated in:

- ARG: 90 entity-years
- PRT: 24 entity-years
- URY: 64 entity-years
- USSR: 76 entity-years

I did not find evidence in the audited outputs of silent many-to-many joins, duplicate post-merge keys, or hidden interpolation in the baseline panel.

## Variable construction audit

Construction choices verified against code and outputs:

- Unit of concentration is partner concentration, not product concentration.
- Active partners are strictly positive bilateral flows.
- Coded/reported zero observations are retained as observability diagnostics but are not counted as active partners.
- Missing dyads are not converted into zero trade in the main panel.
- Totals are bilateral sums in current British pounds, not real aggregate trade totals.
- Metrics include Gini, normalized Gini, Theil, normalized Theil, HHI, normalized HHI, effective partner count, and top-partner shares.
- Threshold rules suppress concentration metrics when active partners are fewer than 5; the headline baseline uses 20+ active partners.

Country-turning-point construction was a prior failure mode. In the audited outputs:

- `country_turning_point_episodes.csv` now records the pooled-model support status explicitly.
- Country episodes are suppressed to `insufficient_support` when the preferred pooled turning point is unsupported.
- Count of substantive country episode rows with unsupported pooled turning points: 0.

## Specification audit

Headline regressions are run separately by flow and metric.

Primary income form:

\[
C_{it}=\alpha+\beta_1 y_{it}+\beta_2 y_{it}^2+\delta_t+\eta_i+\gamma \log(pop_{it})+\varepsilon_{it}
\]

where:

- \(C_{it}\) is partner concentration for entity \(i\) in year \(t\),
- \(y_{it}\) is GDP per capita in 10,000 PPP 2011 USD,
- \(\eta_i\) are entity fixed effects,
- \(\delta_t\) are year fixed effects,
- and \(\log(pop_{it})\) enters only in the population-control specifications.

Audited model ladder:

- pooled minimal,
- pooled + year FE,
- entity + year FE,
- entity + year FE + log population,
- Mundlak within/between decomposition,
- plus log-GDP-per-capita sensitivity versions.

Specification discipline improved materially after the fixes:

- Models without population controls no longer lose observations because of missing population.
- The pooled turning-point dataset is no longer used to manufacture country episodes when pooled support is absent.

## Inference and identification audit

Inference structure:

- Conventional entity-clustered standard errors are reported as reference.
- Preferred baseline pooled and within-country U-tests use entity-level wild-cluster bootstrap with 9,999 draws.
- Turning-point intervals use 2,000 entity-cluster bootstrap draws.
- BH adjustment is applied across the six primary tests.

Primary-sample cluster structure:

- Exports preferred within model: 1,670 observations, 13 entities.
- Imports preferred within model: 1,634 observations, 13 entities.
- Smallest cluster sizes: RUS 23, USSR 67–68.

Substantive inference result from the audited outputs:

- Number of `supported_u_shape` rows in the full model summary: 0.
- Preferred within-country baseline rows:
  - Exports Gini: `insufficient_support`
  - Exports Theil: `suggestive_only` with raw p = 0.455 and q = 0.841
  - Exports HHI: `outside_support`
  - Imports Gini: `outside_support`
  - Imports Theil: `no_u_shape`
  - Imports HHI: `outside_support`

Interpretation:

- I do not see credible evidence in the audited outputs for a supported diversification-then-reconcentration pattern in partner concentration.
- The current pipeline supports a much narrower conclusion: under the requested constructions and support rules, the historical panel does not deliver robust U-shaped partner-concentration evidence.

## Replication checklist

Before trusting a downstream writeup, rerun:

1. `python scripts/build_historical_partner_concentration.py --skip-download`
2. `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1 python scripts/run_historical_partner_cadot.py`
3. `python -m pytest tests/test_concentration_metrics.py tests/test_historical_partner_concentration.py tests/test_historical_partner_cadot.py -q`

And recheck:

- TRADHIST raw row count equals 2,495,357.
- `main_panel_year_universe_violations == 0`.
- USSR and RUS remain non-overlapping.
- No row in `country_turning_point_episodes.csv` receives a substantive classification when the preferred pooled model is unsupported.
- No row in `cadot_model_summary.csv` is described as evidence of a U-shape unless classification is actually `supported_u_shape`.

## Minimal patch plan

No new blocking code patch emerged from this local post-fix audit.

Small remaining hardening steps:

1. Obtain an explicitly authorized fresh independent reviewer pass.
2. In any human-facing memo, gloss `suggestive_only` as non-significant sign evidence only.
3. Keep the exact run command pinned to single-thread BLAS settings, because default BLAS threading was pathologically slow for the turning-point bootstrap kernel.

## Questions for the researcher

1. Do you want an explicitly delegated fresh reviewer pass once you authorize subagent use for the trust review?
2. Do you want the reporting language tightened further so the headline conclusion is stated as null evidence for partner reconcentration rather than as a weak concentration/reconcentration pattern?
