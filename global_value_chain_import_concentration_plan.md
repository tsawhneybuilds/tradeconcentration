# From Gross Trade Concentration to Production-Network Concentration

## Research idea

### The big story

The globalisation of the 1990s and 2000s did not simply increase trade. It changed the object being traded. Production was split across countries, intermediate goods crossed borders repeatedly, and a country's gross exports increasingly contained value added previously imported from elsewhere.

Conventional product and partner concentration measures treat every recorded border crossing as a complete trade flow. They therefore mix three economically distinct objects:

1. imports absorbed by domestic consumers and firms;
2. imported inputs embodied in the country's exports; and
3. re-exports, entrepôt trade, processing trade, and repeated border crossings.

The proposed project asks whether the concentration observed in gross merchandise trade is genuine concentration of production dependence or an artefact of measuring fragmented production through gross border flows.

### Core question

> Did the rise of global value chains create persistent concentration in a small set of product–source production corridors, even while countries imported more products and their aggregate partner concentration appeared stable?

### Strongest contribution

The paper would connect two literatures that are usually kept separate:

- the literature measuring trade concentration across products, partners, and product–partner cells; and
- the global-value-chain literature decomposing gross trade into domestic and foreign value added.

The central empirical object is the **gross-to-value-added concentration wedge**:

\[
W_{it}^{d}=C_{it}^{d,\ gross}-C_{it}^{d,\ value\ added},
\]

where \(C\) is a concentration measure for dimension \(d\), such as industries, source countries, or source-country–industry cells.

In plain English, the wedge asks how much more or less concentrated trade looks when every border crossing is counted than when value added is assigned to the country in which it was actually produced.

The project becomes important if this wedge is large, changes systematically during the GVC take-off, or predicts exposure to trade shocks differently from ordinary gross-trade concentration.

## Conceptual structure

The analysis should distinguish three nested layers.

### Layer 1: Gross basket concentration

This is the existing project object:

- product concentration across HS6 products;
- partner concentration across source or destination countries;
- product–partner-cell concentration;
- active product, partner, and cell counts;
- top-product, top-partner, and top-corridor shares.

For all product-dependent measures, exclude HS6 `999999` before aggregation. For partner-only measures, include `999999` by default and exclude partner code `0` (`World`).

### Layer 2: Production-corridor concentration

Define an import corridor as an importer–HS product–source-country relationship. Measure:

- within-product source concentration;
- persistence and age of the top source;
- survival of product–source corridors;
- entry through new products, new source countries, and new product–source cells;
- concentration separately for intermediate, capital, final-consumption, and energy goods.

This layer tests whether countries obtain a wider range of products while relying on durable source relationships for the economically important products.

### Layer 3: Value-added network concentration

Using OECD Inter-Country Input-Output and TiVA data, distinguish:

- foreign value added embodied in exports – backward GVC participation;
- domestic value added embodied in partners' exports – forward GVC participation;
- imported value added absorbed in domestic final demand;
- source-country and source-industry contributions to embodied foreign value added.

Construct concentration measures over:

- source countries;
- source industries;
- source-country–industry cells;
- final destinations of domestic value added.

Gross and value-added measures must be put on a common industry classification before comparison. An HS-to-OECD-ICIO industry bridge is therefore required; HS6 and TiVA industry concentration cannot be compared directly.

## Mechanism

The proposed mechanism is **network deepening through sunk production relationships**.

Firms face costs of qualifying suppliers, coordinating specifications, meeting standards, arranging logistics, and complying with rules of origin. Once a source relationship is established, growth can occur by importing more products and components through existing country relationships rather than continually adding new partner countries.

This generates four potentially simultaneous patterns:

1. the number of active imported products and product–source cells rises;
2. value remains concentrated in a few core products or corridors;
3. top suppliers within products are persistent;
4. aggregate partner concentration moves less because new activity is recombined within an established regional or bilateral network.

This resolves the apparent tension between product proliferation and stable partner concentration.

### Competition channel

Imported inputs can affect competition through three distinct channels:

1. **Cost channel:** access to higher-quality or cheaper inputs lowers marginal costs and increases the competitiveness of connected domestic firms.
2. **Selection channel:** only sufficiently productive firms can pay the fixed costs of foreign sourcing, so import access can increase the market share of already-large firms.
3. **Dependence channel:** concentration among foreign suppliers raises exposure to disruptions, bargaining power, and cost pass-through.

Country-level HS trade data can describe the network architecture but cannot identify firm competition, markups, or productivity effects. A credible competition claim eventually requires firm–product–source customs data linked to domestic production, sales, employment, or markup measures. Until then, the paper should say “production-network concentration” rather than “market competition.”

## Testable hypotheses

### H1. GVC take-off and the extensive margin

Higher backward GVC participation is associated with more active imported intermediate products and more product–source cells.

The important contrast is that active product counts may increase without a comparable fall in value-weighted product concentration.

### H2. Network deepening rather than partner expansion

During periods of rising GVC participation, import growth comes disproportionately from:

- new products sourced from existing partners; and
- new product–source cells involving existing partners,

rather than from entirely new partner countries.

### H3. Corridor persistence

Backward GVC participation predicts greater survival of importer–product–source corridors and greater persistence of the top supplier within a product.

Persistence should be strongest for differentiated intermediates, capital goods, relationship-specific inputs, and products subject to standards or rules of origin.

### H4. Conditional concentration versus aggregate stability

GVC participation can raise source concentration within products while leaving aggregate partner concentration stable or lower.

This is the central aggregation hypothesis: diversification across many products can coexist with concentrated sourcing inside each product.

### H5. Gross-to-value-added concentration wedge

Gross bilateral trade concentration differs systematically from value-added concentration where production crosses borders repeatedly.

- A positive wedge means gross flows exaggerate concentration.
- A negative wedge means value-added dependence is more concentrated than gross flows reveal.

The wedge should be largest for processing exporters, regional production hubs, and entrepôt economies.

### H6. Trade agreements deepen existing networks

Tariff reductions and trade agreements initially increase product and product–source-cell breadth within existing partner relationships. Partner-count effects should be smaller unless an agreement opens a genuinely new regional network.

Rules of origin may subsequently concentrate sourcing inside the agreement area.

### H7. Network rewiring around major shocks

Large institutional and geopolitical changes should produce discrete changes in corridor composition:

- NAFTA implementation from 1994;
- China's WTO accession in December 2001;
- European Union enlargements in May 2004 and January 2007;
- the 2008–09 global financial crisis;
- the 2018–19 US–China tariff escalation;
- the 2020–22 pandemic disruption; and
- the post-2022 geopolitical and sanctions environment.

These episodes are useful for description and event timing. They are not automatically causal designs because treatment is anticipated, broad, and coincident with other shocks.

### H8. Re-export and hub-economy measurement

Gross concentration measures for Hong Kong, Singapore, the Netherlands, Belgium, Panama, Luxembourg, Switzerland, and similar hubs partly reflect re-export, warehousing, refining, vaulting, or processing activity rather than domestic absorption.

For these economies:

- separate domestic exports from re-exports where national data permit;
- compare gross imports with retained imports or domestic absorption;
- compare gross bilateral concentration with value-added concentration; and
- report hub economies separately rather than merely dropping them.

Hong Kong should be the first forensic case because its official statistics separately recognise domestic exports and re-exports, and its role as an entrepôt is economically central rather than a data nuisance.

## Proposed research pages or modules

### Page 1. The measurement problem

Show how a component can cross several borders and be counted repeatedly in gross trade. Introduce the difference between gross exports, domestic value added, foreign value added, re-imported domestic value added, and double-counted terms.

Key figure: a Mexico–United States automobile supply-chain example showing gross border values and underlying value added.

### Page 2. When did the trade architecture change?

Plot, by country and region:

- backward and forward GVC participation;
- intermediate-goods share of imports and exports;
- active product, partner, and product–source-cell counts;
- product, partner, and cell concentration;
- top-corridor persistence.

Use 1995–2022 as the main common OECD-ICIO window, with gross-trade series extending earlier and later where available. Do not claim a 1990s break until a formal structural-break exercise supports it.

### Page 3. Products expanded; partners persisted

Directly test whether GVC growth occurred through new products and cells within existing partner networks.

The page should distinguish:

- new product;
- new partner;
- new product–source cell involving an existing product and existing partner;
- growth of an existing corridor.

### Page 4. Imports embodied in exports

Compare ordinary import concentration with concentration of foreign value added embodied in exports. Ask whether concentration-driving imports are actually part of export production or domestic absorption.

This page supersedes broad exact-HS6 import–export matching, which is too restrictive because imported components and exported final products normally have different product codes.

### Page 5. The gross-to-value-added concentration wedge

Construct matched gross and value-added concentration at the OECD-ICIO industry and source-country level.

Rank countries by the size and sign of the wedge. Explain whether gross statistics exaggerate repeated corridor traffic or hide dependence on a small number of ultimate value-added sources.

### Page 6. Trade agreements and network formation

Study whether agreements change:

- partner entry;
- product entry within existing partners;
- source concentration within products;
- corridor survival; and
- regional sourcing shares.

Begin descriptively. Move to a causal design only where tariff phase-ins, product-level preference margins, or rules-of-origin exposure provide credible differential treatment.

### Page 7. Hub and entrepôt country forensics

Use country-specific evidence for Hong Kong first, followed by Singapore and the Netherlands or Belgium.

For each case, reconcile:

- Comtrade gross imports and exports;
- national re-export statistics;
- domestic absorption or retained imports where available;
- TiVA domestic and foreign value-added measures; and
- concentration before and after the adjustment.

### Page 8. Resilience and the post-2008 period

Test whether the network became less global, more regional, or merely more redundant after the financial crisis, the pandemic, and recent trade tensions.

Separate:

- reshoring – greater domestic value added;
- nearshoring or friend-shoring – partner reallocation;
- diversification – more suppliers per product;
- redundancy – more suppliers but unchanged value concentration; and
- inventory adjustment, which is not directly observed in annual trade data.

## Empirical design

### Descriptive estimands

The first paper should be explicit that its main contribution is measurement and decomposition.

1. Change in gross product, partner, and corridor concentration associated with a one-percentage-point change in backward GVC participation.
2. Change in active products, partners, and cells associated with GVC participation.
3. Difference between gross and value-added concentration within country–year.
4. Share of trade growth attributable to new products, new partners, new cells, and existing corridors.
5. Corridor survival and top-supplier persistence as functions of GVC intensity and product type.

### Units of observation

- country–year for aggregate concentration;
- country–industry–year for matched gross and value-added comparisons;
- importer–product–source–year for corridor entry and survival;
- importer–product–year for within-product source concentration;
- agreement–country-pair–product–year for trade-policy designs.

### Baseline panel specifications

Country–year:

\[
C_{it}=\beta GVC_{it}+\alpha_i+\lambda_t+\gamma'X_{it}+\varepsilon_{it}.
\]

Country–industry–year:

\[
C_{ist}=\beta GVC_{ist}+\alpha_{is}+\lambda_{st}+\gamma'X_{ist}+\varepsilon_{ist}.
\]

These are descriptive fixed-effects relationships unless a credible source of exogenous GVC variation is introduced. Standard errors should reflect the level at which exposure varies; country-clustered inference with a small number of countries requires wild-cluster or randomisation-style checks.

### Stronger identification routes

Prioritise designs in this order:

1. product-level tariff phase-ins within trade agreements;
2. agreement-specific rules-of-origin exposure by pre-agreement input structure;
3. foreign supply shocks interacted with predetermined input dependence;
4. shipping-cost or logistics shocks affecting particular corridors;
5. geopolitical restrictions or sanctions with clear product and partner incidence.

Avoid treating a simple pre/post dummy for NAFTA, WTO accession, or the pandemic as causal.

## Data plan

### Already in the repository

- UN Comtrade/BACI-style bilateral HS trade panels;
- harmonised HS1992 product identities;
- BEC/end-use bins;
- OECD ICIO files for 1995–2022;
- an HS-to-OECD-industry bridge;
- product, partner, and cell concentration pipelines;
- top-supplier persistence and supplier-ecosystem outputs;
- product-entry and product–partner-cell decompositions.

### New data or processing required

1. OECD TiVA 2025 indicators, including bilateral source-country value added embodied in exports.
2. A validated industry-level gross-trade panel matched to OECD ICIO industries.
3. National re-export and retained-import series for hub-country case studies.
4. Trade-agreement dates, tariff phase-ins, preference margins, and, where feasible, rules-of-origin restrictiveness.
5. A product-differentiation or relationship-specificity classification.
6. Firm customs and domestic-performance data if the paper makes claims about competition, productivity, markups, or firm selection.

### Sample convention

Website-facing outputs should use `cadot_broad_156`. OECD/TiVA analyses will necessarily use the smaller TiVA-covered sample and must be labelled as a separate matched-value-added sample rather than silently replacing the website sample.

## What the existing evidence already says

The repository has already weakened several simple stories:

- broad HS6 import concentration does not map positively to exports;
- intermediate imports are highly product-concentrated, but the current input-output mapping has limited import-value coverage;
- top suppliers are persistent, especially in value-weighted terms;
- economy-specific supplier relationships are more important than universal global dominant suppliers;
- aggregate partner concentration and product concentration behave differently;
- re-export and hub economies are material measurement cases rather than harmless outliers.

The new project should therefore not be sold as “components explain import concentration.” The stronger claim is:

> Gross trade statistics hide the architecture of production networks. Countries can diversify the number of imported products while deepening dependence on persistent product–source corridors, and the difference between gross and value-added concentration reveals where that dependence is real.

## Economist-council stress test

### Trade and spatial perspective

The project has a coherent trade mechanism if it treats products, source countries, and final destinations jointly. A product-only Gini is not a sufficient measure of GVC structure.

### Identification perspective

The gross-to-value-added wedge is a valid descriptive contribution. Claims that trade agreements or GVC participation caused concentration require sharper product-level treatment variation.

### Industrial-organisation perspective

Country-level trade data cannot show that competition changed. The competition channel needs firm outcomes and a clear market definition.

### Economic-history perspective

Do not impose “the 1990s revolution” on the data. Estimate country- and region-specific break dates and allow for earlier regional production sharing and a post-2008 slowdown.

### Measurement perspective

HS revision changes, re-exports, processing trade, CIF/FOB valuation, mirror discrepancies, and changing country borders can all generate false changes. Harmonisation and country forensics are part of the contribution, not appendix housekeeping.

### Policy perspective

The policy-relevant object is not diversity in the number of suppliers. It is the concentration of economically irreplaceable value added and the cost of substituting away from a corridor.

## Minimum viable paper

The smallest defensible first paper has four results:

1. a documented evolution of gross product, partner, and corridor concentration;
2. a decomposition showing products and cells expand more than partner sets during GVC deepening;
3. a matched gross-versus-value-added concentration comparison; and
4. one hub-country forensic case, preferably Hong Kong.

Trade-agreement causality, post-pandemic resilience, and firm competition should be follow-on modules unless the required data are immediately available.

## Decision rule

Proceed to the full paper if the first matched panel shows at least one of the following:

- a substantial and systematic gross-to-value-added concentration wedge;
- a clear link between GVC participation and corridor persistence or network deepening;
- materially different country rankings under gross and value-added concentration; or
- hub-country adjustments that overturn conventional concentration interpretations.

Reframe or stop if gross and value-added concentration are nearly identical, the wedge is dominated by classification noise, and GVC participation has no stable relationship with corridor structure.

## Immediate next step

Build a compact 1995–2022 country–industry panel for the OECD-ICIO economies that contains:

- gross imports and exports by matched industry;
- foreign value added embodied in exports;
- domestic value added embodied in foreign exports;
- gross and value-added source-country concentration;
- active source-country counts;
- product/corridor concentration aggregated from HS data; and
- flags for hub economies and major institutional episodes.

Before running regressions, produce country profiles for Mexico, the United States, China, Hong Kong, Germany, the Netherlands, Vietnam, and India. These cases span North American production sharing, processing trade, entrepôt activity, European regional chains, late GVC entry, and a large economy with relatively high domestic value-added content.

## Core references and data documentation

- Pol Antràs and Davin Chor, “Global Value Chains”: https://www.nber.org/papers/w28549
- Robert C. Johnson, “Measuring Global Value Chains”: https://www.nber.org/papers/w24027
- OECD Trade in Value Added: https://www.oecd.org/en/topics/sub-issues/trade-in-value-added.html
- OECD Guide to TiVA Indicators, 2025 edition: https://stats.oecd.org/wbos/fileview2.aspx?IDFile=2143f34e-6feb-41a9-abaf-cb52132608c4
- Hong Kong Census and Statistics Department, merchandise trade: https://www.censtatd.gov.hk/en/scode230.html
- WTO technical notes on merchandise trade and re-exports: https://www.wto.org/english/res_e/statis_e/technotes_e.htm
