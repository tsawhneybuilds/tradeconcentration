# Historical Partner Concentration and Cadot-Style Turning Points

Generated: 2026-06-19T12:17:30+00:00

## Design scope

- Canonical sample: CEPII TRADHIST 1827-2014 for FRA, DNK, SWE, NOR, NLD, ESP, PRT, GBR, USA, ARG, URY, USSR, and RUS.
- Trade values are bilateral sums in current British pounds; they are not real trade aggregates.
- GDP per capita comes from Maddison Project Database 2023 (`Real GDP per capita in 2011$`); population is `mid-year (thousands)`.
- This is a Cadot-style partner-concentration analogue. It is descriptive and does not identify a causal effect of income.

## Measure construction

- Unit of observation for estimation: entity-year-flow.
- Active-partner baseline uses strictly positive TRADHIST bilateral partner values only; coded zeros are retained for diagnostics and a dedicated zero-inclusive sensitivity.
- Partner Gini is the active-partner Gini; normalized Gini divides by the finite-`n` upper bound `(n-1)/n`.
- Partner Theil is `sum_j s_j log(n s_j)` over active partners; normalized Theil divides by `log(n)`.
- Partner HHI is `sum_j s_j^2`; normalized HHI uses `(HHI - 1/n) / (1 - 1/n)`.
- Baseline `metric_valid` threshold is 20 active partners. Thresholds 5, 10, and 30 are separate sensitivities.

## Baseline model summary

| Flow | Metric | Model | Component | N | Entities | TP (PPP 2011$) | Inside p05-p95 | U-test p | U-test q | Class |
| --- | --- | --- | --- | ---: | ---: | ---: | --- | ---: | ---: | --- |
| Exports | Gini | entity_year_fe_logpop | within | 1670 | 13 | 30142 | yes | 0.455 | 0.841 | insufficient_support |
| Exports | Gini | mundlak | between | 1670 | 13 | -8225 | no | 0.515 |  | outside_support |
| Exports | Gini | mundlak | within | 1670 | 13 | 64207 | no | 0.973 |  | outside_support |
| Exports | Gini | pooled_year_fe | overall | 1704 | 13 | 97043 | no | 0.830 |  | outside_support |
| Exports | HHI | entity_year_fe_logpop | within | 1670 | 13 | 47181 | no | 0.770 | 0.841 | outside_support |
| Exports | HHI | mundlak | between | 1670 | 13 | 42361 | no | 0.612 |  | outside_support |
| Exports | HHI | mundlak | within | 1670 | 13 | 42531 | no | 0.636 |  | outside_support |
| Exports | HHI | pooled_year_fe | overall | 1704 | 13 | 33206 | yes | 0.341 |  | insufficient_support |
| Exports | Theil | entity_year_fe_logpop | within | 1670 | 13 | 11663 | yes | 0.455 | 0.841 | suggestive_only |
| Exports | Theil | mundlak | between | 1670 | 13 | -9013 | no | 0.542 |  | outside_support |
| Exports | Theil | mundlak | within | 1670 | 13 | 61171 | no | 0.986 |  | outside_support |
| Exports | Theil | pooled_year_fe | overall | 1704 | 13 | 84618 | no | 0.933 |  | outside_support |
| Imports | Gini | entity_year_fe_logpop | within | 1634 | 13 | -287798 | no | 0.770 | 0.841 | outside_support |
| Imports | Gini | mundlak | between | 1634 | 13 | 44288 | no | 0.963 |  | outside_support |
| Imports | Gini | mundlak | within | 1634 | 13 | 41709 | no | 0.996 |  | outside_support |
| Imports | Gini | pooled_year_fe | overall | 1672 | 13 | 44297 | no | 0.993 |  | outside_support |
| Imports | HHI | entity_year_fe_logpop | within | 1634 | 13 | -553051 | no | 0.841 | 0.841 | outside_support |
| Imports | HHI | mundlak | between | 1634 | 13 | -3565 | no | 0.656 |  | outside_support |
| Imports | HHI | mundlak | within | 1634 | 13 | 89599 | no | 0.981 |  | outside_support |
| Imports | HHI | pooled_year_fe | overall | 1672 | 13 | 55462 | no | 0.874 |  | outside_support |
| Imports | Theil | entity_year_fe_logpop | within | 1634 | 13 | 20432 | yes | 0.731 | 0.841 | no_u_shape |
| Imports | Theil | mundlak | between | 1634 | 13 | 39343 | no | 0.984 |  | outside_support |
| Imports | Theil | mundlak | within | 1634 | 13 | 41772 | no | 0.999 |  | outside_support |
| Imports | Theil | pooled_year_fe | overall | 1672 | 13 | 42277 | no | 0.997 |  | outside_support |

## Interpretation

- `pooled_year_fe` rows describe cross-country development patterns.
- `entity_year_fe_logpop` rows are the preferred within-country interpretation because they absorb entity and year fixed effects and retain log population.
- `mundlak` separates within-country and between-country curvature; do not interpret the between component as within-country reconcentration.
- Raw p-values are bolded when `< 0.05`; adjusted q-values are italicized when `< 0.05` so they remain visually distinct.

## Country episodes

| Flow | Metric | Entity | Years | Pooled support | Crosses pooled TP | Pre slope p | Post slope p | Pre q | Post q | Class |
| --- | --- | --- | ---: | --- | --- | ---: | ---: | ---: | ---: | --- |
| Exports | Gini | ARG | 143 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Exports | Gini | DNK | 188 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Exports | Gini | ESP | 188 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Exports | Gini | FRA | 188 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Exports | Gini | GBR | 188 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Exports | Gini | NLD | 184 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Exports | Gini | NOR | 184 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Exports | Gini | PRT | 176 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Exports | Gini | RUS | 23 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Exports | Gini | SWE | 186 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Exports | Gini | URY | 147 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Exports | Gini | USA | 188 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Exports | Gini | USSR | 127 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Exports | HHI | ARG | 143 | no (insufficient_support) | no |  |  |  |  | insufficient_support |
| Exports | HHI | DNK | 188 | no (insufficient_support) | no |  |  |  |  | insufficient_support |
| Exports | HHI | ESP | 188 | no (insufficient_support) | no |  |  |  |  | insufficient_support |
| Exports | HHI | FRA | 188 | no (insufficient_support) | no |  |  |  |  | insufficient_support |
| Exports | HHI | GBR | 188 | no (insufficient_support) | no |  |  |  |  | insufficient_support |
| Exports | HHI | NLD | 184 | no (insufficient_support) | no |  |  |  |  | insufficient_support |
| Exports | HHI | NOR | 184 | no (insufficient_support) | no |  |  |  |  | insufficient_support |
| Exports | HHI | PRT | 176 | no (insufficient_support) | no |  |  |  |  | insufficient_support |
| Exports | HHI | RUS | 23 | no (insufficient_support) | no |  |  |  |  | insufficient_support |
| Exports | HHI | SWE | 186 | no (insufficient_support) | no |  |  |  |  | insufficient_support |
| Exports | HHI | URY | 147 | no (insufficient_support) | no |  |  |  |  | insufficient_support |
| Exports | HHI | USA | 188 | no (insufficient_support) | no |  |  |  |  | insufficient_support |
| Exports | HHI | USSR | 127 | no (insufficient_support) | no |  |  |  |  | insufficient_support |
| Exports | Theil | ARG | 143 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Exports | Theil | DNK | 188 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Exports | Theil | ESP | 188 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Exports | Theil | FRA | 188 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Exports | Theil | GBR | 188 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Exports | Theil | NLD | 184 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Exports | Theil | NOR | 184 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Exports | Theil | PRT | 176 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Exports | Theil | RUS | 23 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Exports | Theil | SWE | 186 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Exports | Theil | URY | 147 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Exports | Theil | USA | 188 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Exports | Theil | USSR | 127 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | Gini | ARG | 143 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | Gini | DNK | 188 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | Gini | ESP | 188 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | Gini | FRA | 188 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | Gini | GBR | 188 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | Gini | NLD | 184 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | Gini | NOR | 185 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | Gini | PRT | 176 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | Gini | RUS | 23 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | Gini | SWE | 186 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | Gini | URY | 147 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | Gini | USA | 188 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | Gini | USSR | 127 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | HHI | ARG | 143 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | HHI | DNK | 188 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | HHI | ESP | 188 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | HHI | FRA | 188 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | HHI | GBR | 188 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | HHI | NLD | 184 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | HHI | NOR | 185 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | HHI | PRT | 176 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | HHI | RUS | 23 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | HHI | SWE | 186 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | HHI | URY | 147 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | HHI | USA | 188 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | HHI | USSR | 127 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | Theil | ARG | 143 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | Theil | DNK | 188 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | Theil | ESP | 188 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | Theil | FRA | 188 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | Theil | GBR | 188 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | Theil | NLD | 184 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | Theil | NOR | 185 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | Theil | PRT | 176 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | Theil | RUS | 23 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | Theil | SWE | 186 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | Theil | URY | 147 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | Theil | USA | 188 | no (outside_support) | no |  |  |  |  | insufficient_support |
| Imports | Theil | USSR | 127 | no (outside_support) | no |  |  |  |  | insufficient_support |

## Caveats

- `USSR` and `RUS` are kept separate throughout. No country-year silently combines them.
- Missing dyads are never converted to zero in the main panel. Zero-inclusive variants use only explicit coded zeros.
- Country-episode labels are descriptive HAC slope diagnostics around supported pooled turning points; when the pooled model is unsupported, those rows are suppressed to `insufficient_support`.
- Small-cluster inference is fragile with 13 entities. Conventional clustered p-values are reference-only; the main U-tests use wild-cluster bootstrap p-values in the preferred pooled and preferred within-country baseline rows.
