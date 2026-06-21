# Export Margins Literature Wiki and Project Study Guide

This guide turns the 10-paper wiki into a project-specific reading path for trade concentration, product-partner cells, export transitions, and import-export linkages in this repo.

## Workspace

- PDFs: `literature/export_margins/pdfs/`
- Wiki index: `literature/export_margins/wiki/index.md`
- Full converted papers: `literature/export_margins/wiki/papers/`
- Source registry: `literature/export_margins/source_registry.md`

## Project Objects to Keep Fixed

Use the literature to think in terms of explicit empirical objects:

- Product margin: HS6-level product scope, using this repo's harmonized product family when available.
- Partner margin: destination or source country scope.
- Product-destination cell margin: the `product x partner` relationship; this is the closest aggregate-data analogue of an export relationship.
- Intensive margin: value growth inside relationships that already existed.
- Entry and exit: new or disappearing products, partners, or product-destination cells.
- Survival and scaling: whether new relationships persist and become economically meaningful.
- Firm mechanism: whether aggregate changes are broad-based or driven by a few firms.
- Quality/unit-value mechanism: whether value growth reflects higher quantity, higher prices, or quality upgrading.

Repo caution: for product-level or product-dependent analysis, exclude HS6 code `999999` before product or product-partner aggregation. Partner-only summaries may include `999999` by repo convention because the product identity is not part of the final measure.

## Core Accounting Identities

At the country-year level:

```text
X_ct = sum_p sum_d x_cpdt
```

where `p` is product and `d` is destination/partner. The simplest Hummels-Klenow-style intuition is:

```text
exports = number of active relationships x average value per active relationship
X_ct = N_ct * mean(x_cpdt | x_cpdt > 0)
```

For export-transition work, decompose growth between a base year `0` and end year `t`:

```text
Delta X = sum_continuing (x_t - x_0)
        + sum_entries x_t
        - sum_exits x_0
```

The definition of "entry" depends on the dimension:

- Product entry: a product is not exported in the base year but is exported later.
- Partner entry: a partner is absent in the base year but active later.
- Product-destination entry: the product-partner cell is absent in the base year but active later.

Survival asks whether entry lasts:

```text
survival_h = 1[x_{p,d,t+h} > 0 | x_{p,d,t} first becomes active]
```

This matters because a high entry share with high exit is different from durable diversification.

## Optimized Reading Path

1. Hummels and Klenow first. Learn the language of extensive margin, intensive margin, quality, and quantity.
2. Kehoe and Ruhl second. Learn why "new goods" should often be measured with least-traded goods instead of only literal zeros.
3. Evenett and Venables third. Separate new destinations from new products.
4. Brenton and Newfarmer fourth. Distinguish discovery from post-discovery scaling and geographic expansion.
5. Besedes and Prusa fifth. Add survival and churn; entry is not success unless it persists.
6. Cadot, Carrere, and Strauss-Kahn sixth. Put diversification into a development path and connect it to HS6 concentration.
7. Eaton, Kortum, and Kramarz seventh. Move from country-product decompositions to firm-destination participation.
8. Bernard, Redding, and Schott eighth. Learn how multi-product firms change product scope.
9. Freund and Pierola ninth. Add the superstar-firm warning: aggregate export growth can be a top-firm story.
10. Fieler and Eaton last. Read the frontier GE/quality paper only after the accounting objects are clear.

## Paper-by-Paper Notes

### 1. Hummels and Klenow, 2005

- Question: Do larger/richer countries export more because they export more varieties, sell more per variety, or sell higher-quality products?
- Data unit: exporter-importer-product shipments across many product categories.
- Margin definition: export value is decomposed into extensive margin and intensive margin, with intensive value further interpretable through price/unit value and quantity.
- Main finding: the extensive margin explains a large share of why larger economies export more, while richer countries also sell higher-quality/higher-unit-value goods.
- Project use: this is the conceptual anchor for product and product-destination concentration. Exercise 12's product and product-partner rows are direct descendants of this accounting.
- Limit: unit values are not clean quality measures; they mix quality, composition, pricing, and measurement error.

### 2. Kehoe and Ruhl, 2013

- Question: How much of bilateral trade growth comes from goods that were initially not traded or barely traded?
- Data unit: bilateral goods trade over long horizons.
- Margin definition: "new goods" are operationalized through least-traded goods, not only zero initial trade.
- Main finding: the new-goods margin matters especially over longer horizons and around liberalization or structural transformation.
- Project use: Exercise 12's `new_item` rows should be read with this paper. If new product shares are large over 5- or 10-year horizons, ask whether they are true new goods or low-base products becoming meaningful.
- Limit: product-code changes can create artificial entry; this repo's HS harmonization diagnostics are therefore essential.

### 3. Evenett and Venables, 2002

- Question: How much developing-country export growth comes from entering new foreign markets?
- Data unit: product-line bilateral trade for developing economies.
- Margin definition: new partner entry for long-standing exportables.
- Main finding: a substantial share of developing-country export growth came from established products sold to new partners.
- Project use: compare Exercise 12's partner margin and product-partner-cell margin. Low partner entry but high product-partner entry can mean recombination of existing product and partner sets, not discovery of new products.
- Limit: geographic path dependence and gravity matter, so partner entry should be compared with distance, region, and market size when the project moves beyond accounting.

### 4. Brenton and Newfarmer, 2007

- Question: Is export growth mainly a discovery problem, or a scaling/market-expansion problem?
- Data unit: country-product-market export flows.
- Margin definition: growth is separated into existing products and markets, new products, and new geographic markets.
- Main finding: growth often comes less from new-product discovery and more from scaling existing products and entering additional markets.
- Project use: this is the bridge between the repo's product rows and product-partner-cell rows. It pushes you to ask whether "diversification" means products, destinations, or cells.
- Limit: policy claims about discovery require more than decomposition; they need evidence on constraints, entry costs, and spillovers.

### 5. Besedes and Prusa, 2011

- Question: Why do some countries grow exports faster even when many countries enter many export relationships?
- Data unit: disaggregated export relationships.
- Margin definition: extensive/intensive growth plus duration and survival of export relationships.
- Main finding: many new export relationships die quickly, and survival differences help explain long-run export performance.
- Project use: pair Exercise 12's `new_item` rows with gross contractions and exit rows. Durable entry is stronger evidence than entry alone.
- Limit: annual customs zeros can reflect reporting thresholds, small flows, or reclassification, so survival needs minimum-value and harmonization checks.

### 6. Cadot, Carrere, and Strauss-Kahn, 2011

- Question: How does export diversification change over the development path?
- Data unit: country-year-HS6 product exports.
- Margin definition: concentration and active product-line counts, distinguishing intensive and extensive diversification.
- Main finding: diversification follows a hump shape over development, with diversification and reconcentration mostly along the extensive margin.
- Project use: this is the closest literature match for product concentration and HS6 active-line counts. It helps interpret whether concentration is a development-stage fact rather than an anomaly.
- Limit: HS6 product counts can be mechanically affected by classification revisions and by excluding/including residual product codes.

### 7. Eaton, Kortum, and Kramarz, 2011

- Question: Which firms sell to which destinations, and how do destination size and trade costs shape participation?
- Data unit: French firm-destination sales, including the domestic market.
- Margin definition: firm entry into destinations, sales per firm, and cross-destination participation.
- Main finding: larger and easier markets attract more firms, and firm heterogeneity explains much of observed export participation.
- Project use: product-partner cells in aggregate data are likely bundles of firm-destination decisions. This paper explains why gravity and firm selection sit underneath cell concentration.
- Limit: France is a high-income exporter; mechanisms may differ in developing-country settings or where informal/small firms matter.

### 8. Bernard, Redding, and Schott, 2011

- Question: How do multi-product firms adjust product scope under trade liberalization?
- Data unit: firm-product-destination exports.
- Margin definition: firm-level and firm-product-level productivity determine which products firms export and where.
- Main finding: firms reallocate toward stronger products and may drop weaker products after liberalization.
- Project use: if the repo sees product concentration rise during export growth, that can be consistent with productive firms focusing on core products rather than a failure to diversify.
- Limit: aggregate HS6 data cannot tell whether new products come from new firms or existing firms changing product scope.

### 9. Freund and Pierola, 2012/2015

- Question: How much do top exporters shape sector export patterns?
- Data unit: firm-level exporter data across countries.
- Margin definition: intensive margin is average firm size; extensive margin is number of exporting firms.
- Main finding: the top one percent of exporters explain a large share of sector export patterns, export growth, and diversification.
- Project use: concentration may reflect superstar scaling rather than broad product discovery. Exercise 11 and Exercise 12 should therefore avoid treating aggregate product concentration as automatically broad-based specialization.
- Limit: without firm IDs, this repo can only infer superstar mechanisms indirectly from skewness, top-product shares, and product-partner concentration.

### 10. Fieler and Eaton, 2025

- Question: How should product extensive margins, quantities, qualities, unit values, and welfare be combined in a trade model?
- Data unit: bilateral product trade flows and unit values.
- Margin definition: extensive margin of products, intensive margin, quantity margin, unit-value margin, and quality.
- Main finding: extensive-margin growth and quality both matter, and quality has welfare implications that simple value decompositions miss.
- Project use: this is the advanced layer for interpreting unit-value or quality upgrading if the repo later adds unit quantities and prices.
- Limit: it is a model-based welfare paper; do not start here when the immediate project task is descriptive export-transition accounting.

## Map to This Repo

Exercise 12 export transitions:

- Product rows map to Hummels-Klenow, Kehoe-Ruhl, Cadot-Carrere-Strauss-Kahn.
- Partner rows map to Evenett-Venables and Brenton-Newfarmer.
- Product-partner-cell rows map to Kehoe-Ruhl, Evenett-Venables, Brenton-Newfarmer, and Besedes-Prusa.
- Gross contraction and exit rows are the Besedes-Prusa survival warning.
- HS revision and harmonization diagnostics are the Kehoe-Ruhl data-quality warning.

Exercise 11 product contribution and export linkage:

- `loo_gini_contribution` and export outcomes ask whether concentration-driving import products are also export-linked.
- Hummels-Klenow and Fieler-Eaton help separate value growth into product variety, quantity, and quality.
- Bernard-Redding-Schott and Freund-Pierola warn that aggregate product links may be produced by a small number of multi-product or superstar firms.
- If moving to causal claims, keep the current memo's limitation: these regressions are descriptive, not proof that import concentration causes exports.

Prof P trade concentration flowchart:

- The central puzzle is concentration across products, partners, and product-partner flows.
- Evenett-Venables and Brenton-Newfarmer explain why product diversification and destination diversification are different.
- Eaton-Kortum-Kramarz, Bernard-Redding-Schott, and Freund-Pierola supply the missing firm mechanism beneath aggregate concentration.
- Fieler-Eaton and Hummels-Klenow are the quality/unit-value layer if the project moves from values to welfare.

## Study Schedule

Day 1: Hummels-Klenow and Kehoe-Ruhl. Write down each decomposition and decide how it maps to `product`, `partner`, and `product_partner_cell`.

Day 2: Evenett-Venables and Brenton-Newfarmer. Re-label every "diversification" claim as product diversification, destination diversification, or product-destination diversification.

Day 3: Besedes-Prusa and Cadot-Carrere-Strauss-Kahn. Add survival, churn, development stage, HS6 product counts, and concentration dynamics.

Day 4: Eaton-Kortum-Kramarz, Bernard-Redding-Schott, and Freund-Pierola. Translate aggregate cells into firm participation, firm product scope, and superstar concentration.

Day 5: Fieler-Eaton plus synthesis. Decide whether the project needs unit values/quality or whether value-based decompositions are enough for the current empirical exercises.

## What to Extract While Reading

For each paper, record:

- Unit of observation: country-product, bilateral product, product-destination, firm-destination, or firm-product-destination.
- Entry definition: literal zero, least-traded good, new destination, new cell, or new firm.
- Intensive margin definition: value per active product, value per active cell, average firm size, quantity, or unit value.
- Treatment of zeros and tiny flows.
- Product-code system and any harmonization risk.
- Whether the paper measures survival, not just entry.
- Whether the mechanism is aggregate accounting, firm behavior, quality upgrading, or welfare.
- The one repo object it most directly improves.

## Immediate Project Questions After the Reading

1. In Exercise 12, are high `new_item` shares mostly product entry, partner entry, or product-partner-cell entry?
2. Do high product-partner entry shares survive over the next horizon, or do they show up as gross exit later?
3. Are product-level new items robust to HS revision diagnostics and the exclusion of HS6 `999999`?
4. Do countries with rising product concentration still expand destination coverage for existing products?
5. Are Exercise 11's concentration-driving imports linked to later export entry, export value, or neither?
6. If firm data become available, do product and partner concentration patterns come from the number of exporters or from average/top-exporter size?
7. If quantity data are usable, do high-value export transitions reflect more units, higher unit values, or likely quality upgrading?

