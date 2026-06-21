# Agent Instructions

These instructions apply to all work in this repository.

## Trade Data Rules

- Treat `999999` as "Commodities not specified", not as a real product category.
- For product-level or product-dependent analysis, always exclude HS6 code `999999` from analyses, graphs, tables, regressions, cached panels, checkpoint files, generated site data, and downloadable outputs. This includes product concentration measures, product shares, product bins, leave-one-out product statistics, export probabilities, model inputs, top-product lists, product Lorenz curves, and world/product aggregates.
- For partner/country concentration analysis where products are only being summed into reporter-partner totals, include HS6 code `999999` by default because the identity of the product is not part of the final measure. Continue to exclude `partnerCode == 0` (`World`) unless explicitly running a paper-forensic sensitivity check.
- If a partner/country concentration output excludes `999999` as a sensitivity or legacy comparison, label it clearly as a no-`999999` sensitivity rather than the default partner convention.
- Apply the relevant `999999` rule before aggregation, not only at the final table or graph stage, because it can affect totals, ranks, Gini values, shares, and regression samples.

## Website Sample Rules

- Unless the user explicitly specifies otherwise, website generation, website-facing artifacts, downloadable website outputs, and website validation must use the broad 156-reporter sample, `cadot_broad_156`.
- Do not build or validate the website from `rd2_countries`, `prof_p_33`, `world_broad`, or any other country sample unless the user specifically asks for that sample.
- If `cadot_broad_156` artifacts are incomplete or unavailable, stop with a clear blocker instead of silently falling back to `rd2_countries`, `prof_p_33`, `world_broad`, stale outputs, or partial samples.
- H2.4 world supplier specialization may remain a global benchmark, but it must be labeled clearly as global and not as limited to the `cadot_broad_156` reporter sample.

## Website Repository Map

- `tsawhneybuilds/tradeconcentration`: research/code repository. This is the source of scripts, result artifacts, and website generation logic; it is not the public GitHub Pages site.
- `tsawhneybuilds/trade-gini-map`: staging/preview static website repository for generated site files.
- `tsawhneybuilds/trade-gini-map-prod`: production static website repository. Public site: `https://tsawhneybuilds.github.io/trade-gini-map-prod/`.
- Unless the user explicitly specifies another destination, push generated website changes to the staging/preview repository `tsawhneybuilds/trade-gini-map`, whose public URL is `https://tsawhneybuilds.github.io/trade-gini-map/`.
- For website-facing changes, deploy/push the generated website by default after local validation unless the user explicitly says not to deploy.
- Deploy by generating the site from this repo with `scripts/build_trade_gini_site.py --country-sample cadot_broad_156`, validating the generated output, then publishing the generated files to the staging/production website repos.

## Codex Memory and Context Management

- For long empirical or website pipelines, process data in stages and validate each stage with compact logs.
- Dynamically manage memory, context, runtime, and compute load based on the observed system state, file sizes, command outputs, and pipeline complexity.
- Before running expensive commands, inspect expected input size and available system headroom when relevant, then choose a chunked, streaming, or staged plan instead of loading large datasets or outputs all at once.
- Prefer bounded parallelism. Cap worker counts and thread-heavy libraries when needed, avoid launching multiple heavy pipelines at the same time, and stop background servers or jobs that are no longer needed.
- For long-running jobs, write checkpoints and compact logs, resume from checkpoints when possible, and reduce batch sizes or concurrency if memory pressure, swapping, CPU saturation, repeated process kills, or instability appears.
- Balance speed and performance pragmatically, but never sacrifice correctness, reproducibility, or output quality to finish faster.

## Skill Usage Rules

- At the start of any nontrivial task, check whether the request matches an installed skill or repo-scoped skill. If it does, use the skill and briefly state which skill is being used.
- Prefer using the smallest relevant set of skills. Do not load every skill by default.

### Econometrics and Empirical Work

- Use `econometrics-research-design` when framing an empirical question, defining an estimand, choosing an identification strategy, or deciding which econometric workflow applies.
- Use `causal-econometrics` for IV, DiD, event studies, RDD, synthetic control, matching, weighting, panel causal designs, treatment timing, and identification assumptions.
- Use `econometric-models` when choosing or critiquing estimators such as OLS, GLS/WLS, MLE, GMM, logit/probit, Tobit, count models, selection models, or marginal effects.
- Use `time-series-econometrics` for time-series data, forecasting, unit roots, stationarity, cointegration, VARs, distributed lags, structural breaks, and HAC-style temporal inference.
- Use `econometrics-diagnostics-robustness` when checking heteroskedasticity, serial correlation, clustering, weak instruments, leverage, placebo tests, falsification tests, robustness tables, or sensitivity checks.
- Use `empirical-reporting-replication` when writing or reviewing regression tables, empirical claims, caveats, robustness sections, data provenance, reproducibility, or replication packages.
- Use the shared econometrics graph when judging method-assumption-diagnostic relationships:
  `python /Users/tanushsawhney/.codex/reference-library/econometrics/query_graph.py --query <topic>`.

### Trust Reviews

- Use `adversarial-econometrics-review` after major empirical pipelines, regressions, merge-heavy data builds, panel construction, or Codex-generated empirical outputs before trusting results.
- For adversarial reviews, prefer a fresh spawned reviewer agent when delegation is permitted, and give that reviewer raw artifacts rather than the builder's conclusions.

### Economics Research Support

- Use `econ-ai-data-source-planner` when planning reproducible access to economic data sources such as FRED, World Bank, IMF, BLS, Census, Eurostat, OECD, OpenEcon, or macro/policy APIs.
- Use `econ-ai-research-workflow-planner` when turning an economics research question into a staged workflow involving data, econometrics, forecasting, literature, OCR, NLP, writing, or teaching tools.
- Use `econ-ai-resource-navigator` when choosing, comparing, or operationalizing AI/economics tools from the local awesome-ai-for-economists catalog.

### Papers, PDFs, and LaTeX

- Use `pdf-chunker` whenever reading, summarizing, reviewing, or extracting content from PDFs.
- Use `audit-paper` when auditing academic economics or finance drafts for prose, structure, apparatus, and paper quality.
- Use `lit-review-verify` when checking whether citations support manuscript claims.
- Use `simulate-referee` when asked for pre-submission referee-style feedback.
- Use `compile-latex` when compiling or repairing LaTeX documents.
- Use `overleaf` only for explicit Overleaf Git pull/push/sync tasks.

### Code, Plans, Memory, and Prompts

- Use `audit-code` for systematic research-code or Stata dofile audits.
- Use `review-plan` when stress-testing a plan before implementation; use `review-plan-auto` only when the user asks for iterative or automated plan review.
- Use `solving-model` for setting up, deriving, solving, verifying, or documenting economic models.
- Use `memory` only when the user explicitly asks to update durable project memory.
- Use `restart` when the user asks to restart, wrap up, snapshot, or create pickup notes.
- Use `prompt` or `prompt-only` only when the user explicitly asks to format a rough request into a prompt.
- Use `claude-skill-creator` only for inspecting or converting Claude-style skills; use Codex's built-in `skill-creator` for native Codex skills.

## Empirical Pipeline Review

- After completing any major empirical pipeline, run an adversarial trust review before treating outputs as usable.
- Use the `adversarial-econometrics-review` skill to audit whether the results can be trusted.
- The adversarial review should be performed by a freshly spawned reviewer agent whenever subagent delegation is permitted by the active Codex instructions. The reviewer must be independent from the agent that created or modified the pipeline. If delegation is not permitted, perform the adversarial review locally and state that it was not an independent fresh-agent pass.
- Give the reviewer raw materials, not conclusions: source files, changed files, commands, logs, outputs, intended specification, and relevant data constraints. Do not tell the reviewer that the pipeline is believed to be correct.
- The reviewer must use the installed econometrics skill suite and shared econometrics reference graph when judging identification, estimator choice, fixed effects, clustering, inference, diagnostics, or reporting.
- The review must check data lineage, sample construction, merges, variable construction, fixed effects, clustering, inference, and specification drift.
- Do not present major regression, table, or pipeline outputs as final until the independent adversarial review either clears them or lists the remaining caveats.

## PDF Output Quality

- Whenever generating a PDF for the user, verify that tables fit within page boundaries.
- Tables must not overflow, clip, split awkwardly across pages, or become unreadable.
- If a table is too wide or long, adjust the layout before delivery: use landscape pages, smaller but readable font, repeated headers, wrapped labels, narrower columns, or split the table into coherent panels.
- Inspect the rendered PDF, not only the source file, before considering the PDF complete.

## Codes and Plain-English Labels

- Whenever variables contain codes, include plain-English explanations alongside them in any document, table, note, or report.
- Examples include HS codes, country codes, product codes, BEC codes, flow codes, reporter/partner IDs, and category bins.
- Do not assume the reader can interpret coded values from context alone.

## Constructed Measures and Indexes

- Whenever creating an index, score, bin, concentration measure, proxy, or other constructed measurement variable, document its construction clearly.
- State the unit of observation, input variables, exclusions, transformations, weighting, normalization, and aggregation level.
- Include a clean formula whenever possible.
- Explain the measure in plain English immediately after the formula, including how to interpret higher and lower values.

## Statistical Reporting

- In regression, model, robustness, and hypothesis-test tables, bold and visually highlight estimates and raw p-values when `p < 0.05`.
- When multiple-testing adjusted q-values are reported, also bold and visually highlight q-values when `q < 0.05`.
- Keep raw p-value significance visually distinct from adjusted q-value significance, and do not describe a result as surviving multiple-testing adjustment unless the reported adjusted q-value passes the stated threshold.
