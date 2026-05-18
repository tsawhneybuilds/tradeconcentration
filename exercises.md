# Trade Concentration Research Exercises

Use "supports" and "weakens" rather than "proves" or "disproves." None of these exercises can prove a mechanism alone, but each can eliminate weak explanations and point toward stronger ones.

## Core Exercises

| Exercise | Hypothesis | Supports it if... | Weakens it if... | How to implement |
|---|---|---|---|---|
| **1. Update Prof P beyond 2001** | Concentration is a persistent aggregate fact, not a one-year artifact. | Product/partner Ginis stay high across countries and years. | Concentration disappears or changes sharply by year/sample. | Use country-product-partner-year trade data. Compute Gini, top 1/5/10 product shares, top 5 partner share, and product-partner concentration. |
| **2. Four-bucket growth exercise** | Product/partner concentration predicts future export growth. | High-product/high-partner concentration countries grow differently from low-low countries. | Buckets show no meaningful growth differences. | At time `t`, classify countries into high/low product concentration and high/low partner concentration. Compare export growth over `t+1`, `t+5`, `t+10`. Then add GDP, population, income, oil share, region, and initial exports as controls. |
| **3. Import bin exercise** | Import concentration is driven by energy, capital goods, or key intermediates rather than final consumption goods. | Import Ginis are highest in energy/intermediates/capital goods. | Final goods are equally or more concentrated, or all bins look similar. | Classify HS products using BEC/end-use categories: energy, capital goods, intermediates, final consumption. Compute import Gini within each bin by country-year. |
| **4. Dominant supplier by product** | Imports are concentrated because each product has one dominant global source. | For many products, country imports come mostly from the top source country. | Import concentration remains high even when source shares within products are diffuse. | For each importer-product-year, compute top source share and source-country HHI. Then aggregate by importer. |
| **5. Nearby-market/export ladder exercise** | Small or experimental exports go first to nearby/easier markets; scalable products go global later. | Low-value/new products are disproportionately exported to nearby/regional markets; surviving products later expand to richer/farther markets. | Product-destination expansion has no geographic sequencing. | Track product-destination entry over time. Measure first destination, distance, income, region, and later expansion path. |
| **6. High-unit-value/oil exclusion** | Concentration is mostly driven by aircraft, autos, oil, gold, diamonds, or other obvious high-value/high-volume products. | Ginis fall sharply after excluding these products. | Ginis remain high after exclusions. | Recompute all concentration measures after dropping obvious high-value/high-volume categories. This directly tests Prof P's claim that these are only partial explanations. |
| **7. India vs peers panel** | India's concentration pattern reflects scale, firm-size distribution, or policy rather than normal development. | India differs from peers after controlling for GDP/income/export size. | India looks normal relative to China, Vietnam, South Korea, Japan, Germany, and the United States. | Build India plus comparator panel. Compare product Gini, partner Gini, product-partner Gini, top product shares, and top partner shares. |
| **8. Firm-level/product focus exercise** | Aggregate concentration comes from a few large or focused firms. | Larger or more product-focused firms are more likely to export and dominate export value. | Exporting is not related to firm size/product concentration. | If firm data exist, regress export status/intensity on firm size, productivity, product concentration, conglomerate status, and sector. |
| **9. Policy/antidumping exercise** | Indian policy distortions affect which products scale internationally. | Protected or antidumping-heavy sectors show lower export growth or abnormal concentration changes. | Policy exposure has no relationship with concentration/growth. | Match DGFT/tariff/antidumping product codes to HS products. Use event studies around policy actions. |

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
5. Use **Exercise 8** only if credible firm-level data are available.

## Most Promising Hypothesis

Export growth is concentrated because only some product-partner-firm combinations scale. Import concentration arises when those scalable export sectors rely on concentrated intermediate inputs or dominant foreign suppliers.

This links Prof P's aggregate puzzle to the firm-level literature: the aggregate data show where concentration appears, while firm-level and input-output mechanisms explain how it is generated.
