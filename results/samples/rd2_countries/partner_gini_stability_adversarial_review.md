# Adversarial Review: Partner Gini Stability

Generated: 2026-06-02

## Executive Verdict

Verdict: **Mostly trustworthy** for the current descriptive website purpose.

The independent adversarial review supports the website phrase "mostly stable, with exceptions" for active Partner Gini in the `rd2_countries` panel. It found no blocker, but flagged publication-quality caveats that should be addressed before treating the page as final.

## Highest-Risk Findings

1. **Row-count labeling.** The page's manifest table labeled the full source panel row count as "Rows used." The review recommended separating source rows, main-window rows, balanced-window rows, and country-flow counts.

2. **Coverage artifacts in endpoint exceptions.** Large endpoint changes can reflect active-partner coverage changes. The review noted that United Arab Emirates exports start with very few active partners and recommended showing first, last, minimum, and median active-partner counts in the exception table.

3. **Statistical significance versus practical stability.** Country-specific HAC tests detect many tiny trends. The review recommended keeping practical effect-size thresholds primary and treating p/q values as trend flags.

4. **Common-trend multiple testing.** Common-trend p-values were raw. The review recommended adding BH q-values or clearly labeling the p-values as unadjusted.

## Data Lineage And Sample Audit

The source table is `results/samples/rd2_countries/exercise_01_tables/partner_concentration_all_years.csv`. It has 3,845 rows, 60 countries, years 1988-2025, no duplicate reporter-year-flow keys, and no missing Partner Gini values. The main 2000-2024 window has 2,983 rows and 120 country-flow series. The balanced 2001-2021 window has 2,499 rows and 119 country-flow series.

Partner aggregation follows the repository convention: HS6 `999999` is included in partner totals because products are summed into partner-country totals, while aggregate partner `partnerCode == 0` is excluded upstream.

## Specification Audit

Country slopes estimate:

```text
PartnerGini_t = alpha + beta * (year - first_year) + error_t
```

separately by country-flow, with HAC/Newey-West standard errors.

Common trends estimate:

```text
PartnerGini_ct = beta * trend_t + country FE_c + error_ct
```

separately by flow and window, with standard errors clustered by reporter country.

## Required Fixes Applied

The follow-up patch should:

- Add source/main/balanced row counts and country-flow counts to the manifest and website diagnostic table.
- Add active-partner first, last, minimum, and median counts to country exception rows.
- Add common-trend BH q-values.
- Add a low-active-partner robustness table.

## Remaining Interpretation

The core descriptive claim is valid only with caveats: Partner Gini is relatively stable for most rd2 country-flow series over 2000-2024, but some country exceptions are meaningful and some apparent endpoint movements may reflect partner-coverage changes.
