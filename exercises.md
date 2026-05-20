# Trade Concentration Research Exercises

Use "supports" and "weakens" rather than "proves" or "disproves." None of these exercises can prove a mechanism alone, but each can eliminate weak explanations and point toward stronger ones.

## Core Exercises

| Exercise | Hypothesis | Supports it if... | Weakens it if... | How to implement |
|---|---|---|---|---|
| **1. Update Prof P beyond 2001** | Concentration is a persistent aggregate fact, not a one-year artifact. | Product/partner Ginis stay high across countries and years. | Concentration disappears or changes sharply by year/sample. | Use country-product-partner-year trade data. Compute Gini, top 1/5/10 product shares, top 5 partner share, and product-partner concentration. |
| **2. Four-bucket growth exercise** | Product/partner concentration predicts future export growth. | High-product/high-partner concentration countries grow differently from low-low countries. | Buckets show no meaningful growth differences. | At time `t`, classify countries into high/low product concentration and high/low partner concentration. Compare export growth over `t+1`, `t+5`, `t+10`. Then add GDP, population, income, oil share, region, and initial exports as controls. |
| **3. Import bin exercise** | Import concentration is driven by energy, capital goods, or key intermediates rather than final consumption goods, both because those bins are internally concentrated and because they account for aggregate import concentration. | Energy/intermediate/capital bins have high within-bin Ginis and explain large shares of top import products or reduce aggregate Gini when excluded. | Final goods are equally or more concentrated, or the high-concentration bins are too small to explain aggregate concentration. | Classify HS products using BEC/end-use categories: energy, capital goods, intermediates, final consumption. Compute import Gini within each bin, bin import value shares, top-product contribution by bin, and leave-one-bin-out aggregate concentration by country-year. |
| **4. Dominant supplier by product** | Imports are concentrated because each product has one dominant global source. | For many products, country imports come mostly from the top source country. | Import concentration remains high even when source shares within products are diffuse. | For each importer-product-year, compute top source share and source-country HHI. Then aggregate by importer. |
| **5. Nearby-market/export ladder exercise** | Small or experimental exports go first to nearby/easier markets; scalable products go global later. | Low-value/new products are disproportionately exported to nearby/regional markets; surviving products later expand to richer/farther markets. | Product-destination expansion has no geographic sequencing. | Track product-destination entry over time. Measure first destination, distance, income, region, and later expansion path. |
| **6. Oil / high-unit-value exclusion** | Concentration is mostly driven by oil, aircraft, precious metals, ships, arms, or other obvious high-unit-value/lumpy categories. | Ginis fall sharply after excluding these products. | Ginis remain high after exclusions. | Recompute all concentration measures after dropping these categories. Do not drop HS87 vehicles/parts by default because it mixes finished autos with parts and is not cleanly high-unit-value. |
| **7. India vs peers panel** | India's concentration pattern reflects scale, firm-size distribution, or policy rather than normal development. | India differs from peers after controlling for GDP/income/export size. | India looks normal relative to China, Vietnam, South Korea, Japan, Germany, and the United States. | Build India plus comparator panel. Compare product Gini, partner Gini, product-partner Gini, top product shares, and top partner shares. |
| **8. Firm-level core-portfolio decomposition** | Aggregate product and partner concentration may come from the core export portfolios of value-dominant firms, not from all exporters being single-product or single-destination. | Top exporters account for most export value and their export revenue is concentrated in a few HS products, destinations, or product-destination cells. National concentration falls sharply after accounting for these firms' core portfolios. | Top exporters are broad in value terms across products and destinations, or many firms jointly export the same top products and destinations. In that case, firm concentration does not explain aggregate product/partner concentration. | Requires firm-product-destination-year customs data. Rank firms by export value. Compute each firm's product HHI/Gini, destination HHI/Gini, top-product share, top-destination share, and product-destination concentration. Decompose national concentration into between-firm concentration and within-firm core-portfolio concentration. |
| **9. Policy/antidumping exercise** | Indian policy distortions affect which products scale internationally. | Protected or antidumping-heavy sectors show lower export growth or abnormal concentration changes. | Policy exposure has no relationship with concentration/growth. | Match DGFT/tariff/antidumping product codes to HS products. Use event studies around policy actions. I can use the Int Macro database if needed. |

### 8. Firm-Level Core-Portfolio Decomposition

**Why this replaces the old firm-size test:** We already know from the firm-trade literature that exporters are larger and more productive than non-exporters, and that the largest exporters sell more products and more destinations. Regressing export status on firm size or productivity would mostly rediscover a known exporter-premia result. It would not explain why national exports are concentrated across products or destination countries.

**Sharper question:** Among the firms that account for most export value, is export revenue itself concentrated in a few core products, destinations, or product-destination cells?

This matters because multi-product firms do not automatically weaken the firm-level explanation. A firm can export many HS codes and still earn most of its export revenue from two or three core products. Similarly, a firm can serve many destination countries and still earn most of its export revenue from one or two major markets. The relevant object is therefore value concentration inside the large exporters' portfolios, not just the number of products or countries they touch.

**How this helps resolve the aggregate puzzle:**

1. If national top products are mostly the core products of a few value-dominant firms, then product concentration is partly a firm-level industrial-organization fact.
2. If national top destinations are mostly the core destinations of those same firms, then partner concentration is partly a firm market-access and customer-network fact.
3. If top firms are broad in value terms, or if top products/destinations are supplied by many firms, then firm heterogeneity does not explain the country-level product/partner concentration. The explanation should instead come from product-level comparative advantage, gravity, input-output linkages, dominant suppliers, demand, or policy.

**Do not interpret this exercise as:** "exporters are product-focused, therefore exports are concentrated." The literature already shows that the biggest exporters are often multi-product and multi-destination. The useful test is whether their export value is concentrated in a narrow core portfolio.

## Added Priority Exercises

### 10. Random Benchmark / Null Model

**Why this is good:** It tells us whether concentration is actually surprising, or whether it mechanically arises from country size, number of active products, and total trade volume.

**Hypothesis:** Observed concentration is higher than what would arise mechanically from the scale and sparsity of trade data.

**Supports it if:** Actual concentration is far above the simulated/random benchmark for most countries and years.

**Weakens it if:** Actual concentration is close to what random reshuffling would generate.

**How to implement:**

1. For each country-year, preserve total exports and the number of active products.
2. Randomly reshuffle trade values across products many times.
3. Compute simulated Ginis, top product shares, and top partner shares.
4. Compare the actual concentration measure to the simulated distribution.
5. Repeat separately for products, partners, and product-partner cells.

**Interpretation:** If actual concentration is much higher than the benchmark, Prof P's puzzle is economically meaningful. If not, part of the puzzle may be a statistical artifact of sparse trade data.

### 11. Input-Output Linkage Exercise

**Why this is good:** It directly tests Prof P's most interesting mechanism: concentrated imports may be components or intermediates used to produce concentrated exports.

**Hypothesis:** Import concentration is tied to export production chains.

**Supports it if:** Concentrated intermediate imports map closely to top export sectors.

**Weakens it if:** Import concentration is mostly unrelated final consumption goods, oil, or goods with no clear connection to export sectors.

**How to implement:**

1. Classify imports as intermediates, capital goods, and final goods using BEC or end-use mappings.
2. Use input-output tables to link export sectors to imported input sectors.
3. For each country-year, identify whether top export sectors rely heavily on top imported input categories.
4. For India, examine whether top export sectors have concentrated imported input dependence.
5. Compare India with peers such as China, Vietnam, South Korea, Japan, Germany, and the United States.

**Interpretation:** If concentrated imports are mostly intermediates used by top export sectors, the component-fragmentation hypothesis becomes much more plausible. If concentrated imports are unrelated to exports, the explanation has to come from something else, such as energy dependence, domestic demand, or supplier dominance.

### 12. Export Transition Exercise

**Why this is good:** It separates two different stories: concentration may cause export growth, or export growth may create concentration.

**Hypothesis A:** Countries grow by scaling a few existing products.

**Hypothesis B:** Countries grow by adding new products/partners, and concentration appears later when some entrants scale.

**Supports Hypothesis A if:** Already-top products explain most future export growth.

**Supports Hypothesis B if:** Initially small or new products later become major export products.

**Weakens both if:** Growth is mostly broad-based across many products and partners with little persistence in product ranking.

**How to implement:**

1. For each country, rank products at time `t`.
2. Track which products drive export growth by `t+5` or `t+10`.
3. Decompose growth into:
   - existing top products,
   - existing non-top products,
   - new products,
   - new destinations,
   - new product-destination cells.
4. Build transition matrices:
   - small product -> large product,
   - single-destination product -> multi-destination product,
   - regional product -> global product.
5. Repeat the exercise for partners and product-partner cells.

**Interpretation:** If future growth comes from already-dominant products, concentration may be a growth strategy or a reflection of scalable comparative advantage. If growth comes from new products that later concentrate, then experimentation and selection are the key mechanisms.

## Suggested Research Sequence

1. Start with **Exercise 1**, **Exercise 6**, and **Exercise 10** to verify that the aggregate puzzle is real.
2. Use **Exercise 2** and **Exercise 12** to study whether concentration predicts growth or emerges from growth.
3. Use **Exercise 3**, **Exercise 4**, and **Exercise 11** to explain import concentration.
4. Use **Exercise 7** and **Exercise 9** for the India-specific angle.
5. Use **Exercise 8** only if credible firm-product-destination customs data are available. Survey data can provide suggestive evidence on export intensity or product focus, but it cannot decompose national product/partner concentration.

## Most Promising Hypothesis

Export growth is concentrated because only some product-partner-firm combinations scale. Import concentration arises when those scalable export sectors rely on concentrated intermediate inputs or dominant foreign suppliers.

This links Prof P's aggregate puzzle to the firm-level literature: the aggregate data show where concentration appears, while firm-level core portfolios and input-output mechanisms explain how it is generated.
