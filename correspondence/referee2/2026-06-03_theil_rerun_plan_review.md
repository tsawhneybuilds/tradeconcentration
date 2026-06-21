# Referee2 Plan Review: Full rd2 UNCTAD-Style Theil Rerun

Date: 2026-06-03

## Verdict

Major revisions.

The plan is directionally implementable and the core Theil algebra is coherent under a fixed product-by-destination universe. It was not safe to execute as written because the destination universe, raw aggregation auditability, memory controls, Referee2 replication design, and deployment authorization needed to be made explicit.

## Required Revisions

1. Define the destination universe precisely: whether it is rd2-only partners, all global partners observed by rd2 reporters, or another benchmark partner universe.
2. Require all Theil decompositions to use the same filtered product-destination cells, totals, and fixed universe counts.
3. Add a hard validation that product marginals computed from product-destination cells reproduce the product-only fixed-universe Theil panel within tolerance.
4. Make memory controls operational: chunk size, worker cap, DuckDB memory limit, thread cap, temp directory, dry-run criteria, and checkpoint resume policy.
5. Predefine independent replication targets for the Referee2/code audit: toy decompositions, selected real reporter-year-flow recomputations, totals, universe counts, residuals, and comparison tables.
6. Treat `theil-repo` deployment as explicitly authorized by the user's request; otherwise the default site target remains the existing Gini staging repo.
7. Split downstream exercise ports into staged outputs after the base product-destination panel passes validation.

## Minor Revisions

- State that HS6 `999999` is excluded from raw filters, checkpoints, cached panels, downloads, and site data for every product-dependent output.
- Include plain-English labels for partner codes, reporter codes, product-family IDs, and flows in reports and downloads.
- Add normalized overall Theil and normalized component shares with explicit denominators.
- Label UNCTAD official-series comparisons as an external bridge, not a validation that the HS6 rd2 analogue exactly reproduces UNCTAD.
- Preserve the repo's regression-table p-value and q-value highlighting rule if downstream regressions are regenerated.

