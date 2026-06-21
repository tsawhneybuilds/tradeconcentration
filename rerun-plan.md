# Cadot Constant-PPP Rerun Plan

## Decision

Use constant PPP GDP per capita as the headline Cadot-comparable development measure. Cadot's main income variable was GDP per capita in constant PPP international dollars, not current USD. In this project the headline modern equivalent is World Bank `NY.GDP.PCAP.PP.KD`: GDP per capita, PPP, constant 2021 international dollars.

Current-GNI/current-USD results should be treated as legacy diagnostics or sensitivities, not as headline Cadot replication evidence.

## What Needs To Change

1. Keep the existing `rd2_countries` website/default workflow unchanged.
2. Keep the existing `cadot_broad_156` sample design unchanged: selected reporters must remain exactly 156.
3. Do not rebuild raw Comtrade concentration panels unless validation shows they are missing or stale. Concentration outcomes are income-independent.
4. Reuse cached concentration, oil-share, population, and PPP-control artifacts where possible.
5. Refactor Cadot-facing mechanism code so the headline income variable is constant PPP GDPpc:
   - `gdp_pc_ppp_constant_2021_intl_usd`
   - `log_gdp_pc_ppp_constant_2021_intl_usd`
   - a common internal `log_income_pc` alias for regressions and mechanism diagnostics
6. Move any current-GNI language to legacy/sensitivity language.
7. Rebuild:
   - rd2 constant-PPP hump regressions
   - cadot broad 156-country constant-PPP hump regressions
   - rd2 Cadot mechanism tribunal with constant PPP income
   - `workinprogress.html` from the explainer generator after updating the generator
8. Re-run focused tests and validation checks.
9. Run an adversarial econometrics review before treating the rerun outputs as usable.

## Memory And CPU Rules

Run all rerun stages with single-threaded numerical libraries and lower process priority:

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
/usr/bin/nice -n 10 python3 <script>
```

Avoid raw rebuild flags by default. If a raw rebuild becomes unavoidable, use checkpoint/resume stages with a memory cap and validate after each partial stage before continuing.

## Run Order

1. Validate required cached inputs exist.
2. Patch the Cadot tribunal to use constant PPP as the headline income variable.
3. Patch generated reporting so the HTML cannot regress to current-GNI wording.
4. Run rd2 PPP hump regressions.
5. Run cadot broad PPP hump regressions.
6. Run the Cadot mechanism tribunal.
7. Rebuild `workinprogress.html`.
8. Run focused tests:
   - `tests/test_cadot_hump_tribunal.py`
   - `tests/test_cadot_broad_sample.py`
   - `tests/test_cadot_hump_tribunal.py`
9. Run targeted validation diagnostics for:
   - no duplicate reporter-year keys
   - constant PPP columns present and nonmissing in analytic panels
   - HS6 `999999` absent from product-dependent artifacts
   - broad sample remains 156 reporters
10. Run adversarial review and record the caveats.

## Expected Interpretation

The correct headline comparison is no longer "current-GNI Cadot tribunal." The headline should read:

"Cadot-style modern replication using GDP per capita at PPP in constant 2021 international dollars."

If current-GNI results are shown, they must be labeled as a legacy/sensitivity diagnostic.
