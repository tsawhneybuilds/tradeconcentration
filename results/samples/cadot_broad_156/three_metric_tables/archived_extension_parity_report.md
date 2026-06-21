# Archived Extension Parity Report

- Archived source: `tsawhneybuilds/trade-gini-map-old` commit `9852ae9`.
- Current staging baseline: `tsawhneybuilds/trade-gini-map` commit `37ab6e1`.
- Restored target: harmonized Cadot 156 metric routes only; no rd2 payload or figure reuse.

| Archived component | Status | Cadot 156 implementation |
|---|---|---|
| World map | restored | Exercise 1 on Gini, Theil, and HHI routes; fixed metric/flow scale across years. |
| Country trajectories | restored | Exercise 1 with searchable multi-country selector. |
| Year slider | restored | Exercise 1 map and Exercise 3 non-energy map. |
| Energy-excluded map | restored and generalized | Exercise 3 non-energy import map for Gini, fixed-universe Theil, and HHI. |
| Energy-excluded country lines | restored and generalized | Exercise 3 non-energy country trajectories. |
| Rank-bucket overview | restored | Exercise 3 start/mid/end scrollable stacked bars. |
| Rank-bucket country focus | restored | Exercise 3 sticky focus chart, totals, and top ten HS1992 families. |
| Lumpy-product exclusion chart | replaced | Exercise 6 metric-specific exclusion trend and sensitivity ranking. |
| Benchmark chart | replaced | Exercise 10 metric-specific benchmark path and latest gaps. |
| Growth buckets | replaced | Exercise 2 metric-specific trade and active-product growth charts. |
| Structured hypothesis cards | restored | One full Question/Supports/Weakens/Current result card on every metric exercise page. |
| Chart evidence boxes | restored | Registry-backed question boxes for every interactive exercise chart and retained static Cadot figure. |
| Archived Exercise 2 regression table | intentionally excluded | Outside the requested graph-and-question restoration and not part of the harmonized three-metric artifact bundle. |

All product-dependent restored views exclude source HS6 `999999` before approved BEC filtering and LT/HGL weighted conversion to HS1992/H0. Partner code `0` is excluded by the shared leaf extractor.
