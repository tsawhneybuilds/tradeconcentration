# Long-Run Historical Trade Coverage

Source family: public RICardo raw flows from `medialab/ricardo_data` plus the CEPII TRADHIST documentation page.

| Country | First year | Last year | Distinct years | Rows | Source files | Note |
|---|---:|---:|---:|---:|---:|---|
| France | 1787 | 1938 | 146 | 17897 | 25 | Country-proper France rows only; colonial reporters excluded. |
| Denmark | 1818 | 1938 | 121 | 9417 | 59 | Includes historical Danish orthography variants; Schleswig/Holstein treated as separate boundary-sensitive entries unless explicitly merged later. |
| Sweden | 1800 | 1938 | 139 | 5468 | 27 | Includes Swedish orthography variants. |
| Norway | 1828 | 1938 | 111 | 9306 | 91 | Includes historical orthography variants. |
| Netherlands | 1800 | 1938 | 139 | 7348 | 48 | Country-proper Netherlands rows only; Dutch colonial territories excluded. |
| Spain | 1821 | 1938 | 118 | 14072 | 117 | Includes Spanish orthography variants. |
| Portugal | 1796 | 1938 | 143 | 11813 | 93 | Country-proper Portugal rows only; Portuguese colonial territories excluded. |
| United Kingdom | 1796 | 1938 | 143 | 27719 | 28 | Country-proper UK rows only; colonial reporters excluded. |
| United States | 1790 | 1938 | 149 | 29453 | 124 | Country-proper US rows only; state-/territory-specific reporters excluded. |
| Argentina | 1820 | 1938 | 119 | 7563 | 56 | Includes historical La Plata / Argentine Republic aliases. |
| Uruguay | 1820 | 1938 | 119 | 5432 | 40 | Includes Montevideo/asterisked Uruguay labels via the root prefix. |
| Russia | 1800 | 1938 | 139 | 9857 | 29 | Includes imperial and USSR-era spelling variants; boundary notes matter here. |

Notes:
- The scan uses reporter labels in the raw rows, normalized to lower case and accent-stripped.
- Netherlands excludes `netherlands east indies` and `netherlands antilles` so the series is country-proper.
- Denmark, Norway, Russia, and the Iberian cases include historical spelling variants rather than a single modern ISO label.
- For France, Spain, Portugal, UK, US, Argentina, and Uruguay, the raw source rows already give clean country-proper series.

References:
- CEPII TRADHIST: https://www.cepii.fr/cepii/en/bdd_modele/bdd_modele_item.asp?id=32
- RICardo repo: https://github.com/medialab/ricardo_data