# Detailed Export Margins Project Notes

This is the long-form, notes-first companion to the compact export margins study guide. It is written for this repo's trade concentration work, not as a generic literature summary. The recurring objects are product margins, partner margins, product-partner cells, entry, exit, survival, concentration, quality and unit values, and the firm mechanisms that can sit underneath aggregate country-product data.

Keep the repo rule fixed throughout: for product-level or product-dependent analysis, exclude HS6 `999999` before product or product-partner aggregation. Partner-only concentration summaries may include `999999` by repo convention because product identity is not part of the final partner measure.

## Shared Project Objects And Formulas

At the country-year level, the basic accounting object is total exports:

<div class="formula-block">
  <div class="formula-line"><var>X</var><sub>ct</sub> = <span class="op">&sum;</span><sub>p</sub> <span class="op">&sum;</span><sub>d</sub> <var>x</var><sub>cpdt</sub></div>
</div>

Here `p` is a product, `d` is a destination or partner, and the observation underneath the total is the country-product-partner-year cell. The margin vocabulary changes depending on whether the active object is a product, a partner, or a product-partner cell.

<div class="formula-block">
  <div class="formula-line"><var>X</var><sub>ct</sub> = <var>N</var><sub>ct</sub> <span class="op">&times;</span> <span class="func">mean</span>(<var>x</var><sub>cpdt</sub> <span class="op">&mid;</span> <var>x</var><sub>cpdt</sub> &gt; 0)</div>
</div>

This is the simplest Hummels-Klenow intuition: countries export more because they have more active relationships, higher value per relationship, or both. Exercise 12 is the repo's direct transition version of this identity:

<div class="formula-block">
  <div class="formula-line"><span class="op">&Delta;</span><var>X</var> = <span class="op">&sum;</span><sub>continuing</sub>(<var>x</var><sub>t</sub> - <var>x</var><sub>0</sub>)</div>
  <div class="formula-line indent">+ <span class="op">&sum;</span><sub>entries</sub> <var>x</var><sub>t</sub></div>
  <div class="formula-line indent">- <span class="op">&sum;</span><sub>exits</sub> <var>x</var><sub>0</sub></div>
</div>

Survival is the dynamic correction to the entry story:

<div class="formula-block">
  <div class="formula-line"><span class="func">survival</span><sub>h</sub> = <strong>1</strong>[<var>x</var><sub>p,d,t+h</sub> &gt; 0 <span class="op">&mid;</span> <var>x</var><sub>p,d,t</sub> <span class="text-term">first becomes active</span>]</div>
</div>

The main discipline for this project is to never say "diversification" without naming the object: product diversification, partner diversification, product-partner diversification, firm diversification, or quality upgrading.

## 1. Hummels And Klenow 2005: Variety And Quality Of A Nation's Exports

### Why This Paper Matters For My Project

Hummels and Klenow is the clean starting point because it makes the core accounting question unavoidable: when one country exports more than another, how much of the gap is because it exports more product categories, how much is because it sells more within each category, and how much is because the same measured category contains higher-quality or higher-price goods? That is exactly the issue behind this repo's product concentration and export-transition work. If a country's export value is concentrated in a few products, that can mean low product variety, high intensive scale in a few products, quality upgrading within a stable set of products, or some mix of all three.

For Exercise 12, this paper gives the language for separating new product scope from growth of continuing products. The Exercise 12 headline product rows show large median `new_item` shares: about 0.424 of net 5-year product growth and 0.391 of net 10-year product growth under the harmonized HS6-family measure. Hummels-Klenow says to interpret those numbers as extensive-margin movement, but not as the full export story. You still need the intensive component, and you need to ask whether value growth is quantity or quality. For Exercise 11, the same idea matters because the imported products that raise concentration may or may not be linked to export activity. If a product raises the import Gini but has weak export linkage, the mechanism is not a simple import-input-to-export-output story.

### Big Question And Intuition

The Feynman-style version is this: imagine two countries selling to the world. The large or rich country can look bigger in three ways. It can show up in more aisles of the global supermarket. It can sell more boxes in each aisle. Or its boxes can be more expensive because they are better, more specialized, or contain hidden variety inside a coarse product code. Hummels and Klenow ask which of those channels explains why bigger and richer countries export more.

The misconception they correct is that "more exports" is only an intensive-margin story. Traditional Armington-style models treat each country as selling a differentiated bundle, but they do not naturally generate a product extensive margin. Krugman-style variety models generate an extensive margin, but the paper shows that the relationship between size, variety, prices, and quantities is not exactly what a simple model predicts. The quality interpretation is crucial because richer countries often sell at higher unit values rather than lower prices, even though a pure scale story might predict lower prices.

### Data And Unit Of Observation

The paper uses shipments by 126 exporting countries to 59 importing countries in 1995 across 5,017 six-digit product categories. The empirical object is exporter-importer-product trade. That is close to this repo's country-product-partner-year export cell, except Hummels and Klenow work in a cross section and use a specific set of import markets with matching exporter characteristics.

Their construction is not just a count of product codes. They build an extensive margin in a way connected to consumer price theory. A category that is very important in world trade gets more weight than a tiny category. This matters for the repo because a raw active-line count and a value-weighted extensive margin can tell different stories. The Section 16 issue in Cadot, Carrere, and Strauss-Kahn is an example of why product-code counts can be mechanical: machinery and electrical equipment can contain many lines and high value per line.

### Core Decomposition Or Model Logic

The empirical logic starts from a product-level decomposition of exporter sales to import markets. For an exporter `j`, importer `m`, and product `i`, value is price times quantity:

<div class="formula-block">
  <div class="formula-line"><var>x</var><sub>jmi</sub> = <var>p</var><sub>jmi</sub><var>q</var><sub>jmi</sub></div>
</div>

Total exports can be decomposed into an extensive margin, which captures the set of product categories exported, and an intensive margin, which captures sales within the common product set. Then the intensive margin can be split into price and quantity components. For this project, the useful translation is:

<div class="formula-block">
  <div class="formula-line"><span class="text-term">export value growth</span> = <span class="text-term">active product/cell expansion</span> + <span class="text-term">sales growth inside active products/cells</span></div>
  <div class="formula-line"><span class="text-term">sales growth</span> = <span class="text-term">quantity growth</span> + <span class="text-term">unit-value or quality growth</span></div>
</div>

The paper also compares model predictions. Armington has no product extensive margin. Krugman gives an extensive margin but can overstate how variety responds to size. A quality-differentiation model helps explain why richer exporters sell goods at modestly higher prices and higher quantities, rather than simply selling the same goods cheaply.

### Main Findings

The headline result is that the extensive margin accounts for a large share of why larger economies export more. In their Table 2, roughly 60 percent of the greater exports of larger economies is associated with the extensive margin, with estimates around the high 50s to mid 60s depending on whether the exporter characteristic is GDP, labor force, or GDP per worker. That means larger countries are not merely selling more of the same measured goods; they are present in a wider set of product categories and destination-product markets.

The intensive margin still matters. Within products exported by both countries, larger countries sell more. But richer countries do not fit a simple low-price, high-quantity story. Their unit values tend to be higher, and their quantities are higher as well. This is why the quality interpretation is useful. The paper does not directly observe quality; it infers quality from patterns in prices, quantities, and income. That is a measurement caveat, but the conceptual point is central: value-based concentration can hide upgrading within a product category.

Table 4 is also important for this repo because it shows that the level of product aggregation affects the measured extensive margin. Moving from six-digit to more aggregated product codes changes how much variety is visible. That is directly related to this repo's use of HS6 harmonized families and robustness views at HS4, HS2, and CPA-sector levels.

### What To Borrow For This Repo

Borrow the discipline of writing every export result as an extensive/intensive decomposition. In Exercise 12, product entry, partner entry, and product-partner-cell entry are separate extensive margins. Product-partner-cell entry is the closest aggregate-data analogue of "new relationships." The Exercise 12 median net results show that new product-partner cells account for a very large share of net growth, about 0.759 at 5 years and 0.714 at 10 years. Hummels-Klenow tells you that this is economically meaningful, but it does not tell you whether the new cells are durable, large, or quality-upgrading.

Borrow the quality warning for any later unit-value work. If this repo adds quantities, do not read higher unit values mechanically as higher quality. Unit values can move because of composition within HS6, measurement error, pricing-to-market, transport costs, or quality. But Hummels-Klenow gives a strong reason to ask the question rather than stopping at values.

Borrow the aggregation sensitivity. For any product concentration graph, report whether the result is HS6, harmonized HS6 family, HS4, HS2, or sectoral. Since product-code granularity can create artificial extensive-margin action, Exercise 12's HS revision and harmonization diagnostics are not housekeeping; they are part of the interpretation.

### Limits, Measurement Problems, And Cautions

The first caution is that HS6 product categories are not true varieties. A single code can contain many varieties, quality levels, brands, and firm products. This is why a product extensive margin is not the same as the true variety margin. A country can upgrade within a code while the HS6 product count is unchanged.

The second caution is that product counts are classification-dependent. If one section of the HS has more lines than another, a country specialized in that section may look more diversified mechanically. This connects to the user's Section 16 concern. In this repo's own rd2 2021 diagnostic, HS Section 16, chapters 84-85, accounts for 14.5 percent of distinct export lines and 28.9 percent of export value after excluding `999999`. That means it is both line-rich and value-rich in our data too. Hummels-Klenow's weighting approach is a reminder that raw line counts should not be the only measure.

The third caution is `999999`. It is "Commodities not specified," not a real product. Keeping it in product or product-partner analysis would create a fake product category that can alter totals, shares, ranks, concentration, and entry/exit. Exclude it before product aggregation.

### Concrete Next Empirical Moves

1. For Exercise 12, produce a Hummels-Klenow-style table by country and horizon: change in total exports, active product count, active partner count, active product-partner cells, average value per active product, and average value per active cell.
2. Report the same table at harmonized HS6 family, HS4, and HS2 levels to see how much of "new product" growth is sensitive to aggregation.
3. Add a line-count/value-share diagnostic by HS section for multiple years, not only 2021, and mark Section 16 separately.
4. If quantity data become usable, decompose continuing-product growth into value, quantity, and unit-value changes. Treat unit value as a signal, not proof, of quality.
5. For Exercise 11, compare whether products with high import-concentration contributions also have high export value, export probability, and unit-value changes if quantities exist.

### Reading Notes / What To Remember

Remember the supermarket analogy: more aisles, more boxes per aisle, better boxes. The paper's central lesson is that product scope is a major part of export scale, but value per product and quality cannot be ignored. For this repo, Hummels-Klenow is the reason to make Exercise 12's product and product-partner-cell accounting the base layer before moving to survival, firms, or welfare.

## 2. Kehoe And Ruhl 2013: The New Goods Margin

### Why This Paper Matters For My Project

Kehoe and Ruhl is the key paper for interpreting Exercise 12's `new_item` shares. The repo currently measures entry in products, partners, and product-partner cells over 5- and 10-year horizons. That creates an immediate question: are "new" items truly new, or were they tiny and noisy in the base year? Kehoe and Ruhl's answer is that literal zeros are often too fragile. Trade data have reporting thresholds, small shipments, lumpy deliveries, reclassification, and sparse small-country flows. Their "least-traded goods" method is designed precisely for this problem.

This is especially important because the Exercise 12 product results show large entry shares, while partner entry shares are small. Median net `new_item` contribution shares are about 0.424 for products at 5 years, 0.391 for products at 10 years, 0.759 for product-partner cells at 5 years, and 0.714 for cells at 10 years. Kehoe and Ruhl says: do not immediately interpret those as literal discovery. Some may be low-base products becoming meaningful, and some may be code or reporting artifacts.

### Big Question And Intuition

The Feynman-style intuition is: if a product went from one dollar to one million dollars, calling it "existing trade" misses the economic novelty. If a product went from zero to one dollar, calling it "new trade" exaggerates novelty. The right idea is to look at goods that were barely traded at the start and ask whether they became important later.

The paper asks how much of trade growth comes from the new goods margin, especially after trade liberalization or structural transformation. The misconception it corrects is that the extensive margin should be measured only by goods with zero initial trade. Zero is not a clean economic category in customs data. A tiny positive flow may be economically indistinguishable from zero, while a reported zero may hide shipments below reporting thresholds.

### Data And Unit Of Observation

Kehoe and Ruhl use bilateral goods trade at the five-digit SITC revision 2 level. They build a broad sample of 1,913 bilateral country pairs that account for more than 80 percent of world trade in their benchmark period. They also study specific liberalization and transformation episodes, including NAFTA, the Canada-U.S. FTA, China-U.S. trade around WTO-era reforms, and earlier Chile and Korea transitions.

The unit is importer-exporter-product-year. For this repo, the closest object is reporter-partner-HS6-year export value, with the caveat that this repo uses HS data and harmonized HS6 families where possible, while Kehoe and Ruhl use SITC to reduce classification problems over time.

### Core Decomposition Or Model Logic

The central method is to sort products within a bilateral pair by their base-period trade value and form product groups that each account for 10 percent of initial trade. The first group is the "least-traded goods" group: all zero or tiny flows, plus enough small positive flows to make the group exactly 10 percent of base trade. Then the researcher tracks that base least-traded group forward:

<div class="formula-block">
  <div class="formula-line"><span class="text-term">new-goods margin</span> = <span class="func">share</span><sub>t</sub>(<span class="text-term">base least-traded goods</span>) - <span class="func">share</span><sub>0</sub>(<span class="text-term">base least-traded goods</span>)</div>
</div>

If the least-traded group rises from 10 percent to 25 percent of trade, that is evidence that initially marginal goods became important. This is different from simply counting new codes. It is a value-share approach to economic emergence.

### Main Findings

The paper finds that the least-traded goods margin matters substantially in episodes of liberalization or structural change. In the abstract-level headline, it accounts for about 10 percent of trade growth for NAFTA country pairs and about 26 percent for trade between the United States and Chile, China, and Korea. The paper also shows that the timing of increases often lines up with policy or development episodes, such as NAFTA implementation or China's WTO-era opening.

The Korea example is especially useful conceptually. Least-traded Korean exports to the United States rose dramatically during Korea's transformation from commodities and light manufactures toward a wider set of manufactured goods. The point is not just that Korea added codes; it is that the base marginal set became a much larger part of exports.

The paper also shows why zero-only measures can miss the action. Goods with small positive base flows may be exactly the ones that become important after liberalization. A strict zero rule would ignore them.

### What To Borrow For This Repo

Borrow the least-traded goods diagnostic for Exercise 12. Instead of only classifying products or product-partner cells as base-zero versus base-positive, create base-period bins by value share. For each country and horizon, sort product or product-partner cells by base export value, define a bottom group that accounts for 10 percent of base exports, and ask how its share changes by the end year. This will reveal whether Exercise 12's "new" growth is really from base-zero cells or from initially tiny cells becoming meaningful.

Borrow the idea for low-base robustness. A product entering from zero can have a huge percentage growth rate but tiny economic importance. Report value shares, not only counts or growth rates. In Exercise 12, the net contribution share already helps, but a least-traded analysis would make the low-base issue explicit.

Borrow the classification caution. The repo's harmonized HS6-family approach is already aligned with this concern. The old same-revision diagnostic and HS4/HS2 robustness views should be discussed as responses to the Kehoe-Ruhl problem.

### Limits, Measurement Problems, And Cautions

The method depends on product classifications. Kehoe and Ruhl use SITC because HS revisions can create artificial new goods. This repo uses HS6 because Comtrade and the project pipeline are built around HS codes, so the harmonized-family logic is essential. Never interpret raw HS6 entry without checking harmonization diagnostics.

The least-traded method is also relative to the base period. If the base year is unusual, crisis-hit, or missing large flows, the bottom 10 percent group can be misleading. For this repo, use multi-year base averages where possible, not a single noisy base year, especially for smaller countries.

Zeros are not all the same. A zero can mean no trade, unreported trade, below-threshold trade, reclassification, sanctions, data gaps, or temporary shipment lumpiness. The product-partner-cell margin is particularly vulnerable because bilateral product flows are sparse.

Finally, apply the `999999` rule before building least-traded product groups. If `999999` is kept, the residual category can become an artificial "good" that enters or exits in ways unrelated to real product discovery.

### Concrete Next Empirical Moves

1. Build a Kehoe-Ruhl diagnostic for Exercise 12: for each country, horizon, and dimension, compute the end-year share of base least-traded items that accounted for 10 percent of base exports.
2. Run the diagnostic for products and product-partner cells separately. Product-partner cells should show more churn; products should be more stable.
3. Use three base definitions: base-zero only, base least-traded 10 percent, and base least-traded 20 percent.
4. Compare harmonized HS6 family results with HS4 and HS2 results. If the "new goods" margin collapses at HS4 or HS2, much of it may be code-level reshuffling.
5. Flag countries or years where a single product or Section 16 dominates the least-traded-to-important transition.

### Reading Notes / What To Remember

The key phrase is "barely traded, not only never traded." For this repo, Kehoe and Ruhl is the correction that keeps Exercise 12 from becoming a naive entry-count exercise. It teaches you to focus on the economic rise of initially marginal products and cells, measured by value share and checked against code instability.

## 3. Evenett And Venables 2002: Export Growth, Market Entry, And Bilateral Flows

### Why This Paper Matters For My Project

Evenett and Venables is the classic new-destination paper. It matters because "export diversification" is often used loosely, but product diversification and destination diversification are not the same. This repo's Exercise 12 separates the partner margin from the product margin and the product-partner-cell margin. That separation is exactly the Evenett-Venables contribution: a country can grow exports by selling long-standing products to new foreign markets without discovering new products.

The current Exercise 12 pattern makes this distinction important. Partner-level net `new_item` shares are tiny in the headline median results, around 0.003 at 5 years and 0.011 at 10 years, while product-partner-cell new shares are very large. That combination suggests much of the cell-level action may be recombination within existing product and partner sets, or entry into new cells rather than truly new partners. Evenett and Venables gives the conceptual and empirical framework to study that.

### Big Question And Intuition

The Feynman-style version is: suppose a firm or country already knows how to make shirts. Export growth can come from inventing a new product, or from selling shirts to more countries. Evenett and Venables ask how important the second channel is for developing countries.

The misconception they correct is that export growth in developing countries mainly means new product discovery. They show that a large share of growth can come from geographic spread: established products finding new buyers. That is a learning and market-access story, not necessarily a production-discovery story.

### Data And Unit Of Observation

The paper studies 23 developing and middle-income economies from 1970 to 1997. It uses bilateral trade data at the three-digit product-line level for trade among 93 nations. For the decomposition, they compare early-period averages around 1970-1974 with later-period averages around 1993-1997 and use a cutoff, such as $50,000 per year, to avoid treating tiny flows as meaningful trade.

For the econometric part, the unit is product-line, exporter, destination, and year. They estimate whether a country exports a given product line to a given destination, using lagged experience and measures of proximity to markets already supplied.

### Core Decomposition Or Model Logic

The paper first decomposes export growth by product-line status: continuing products, dying products, and new products. Then, within long-standing product lines, it decomposes growth by partner status: continuing destinations versus new destinations.

The project translation is:

<div class="formula-block">
  <div class="formula-line"><span class="op">&Delta;</span><var>X</var><sub>i</sub> = <span class="text-term">growth in old products to old partners</span></div>
  <div class="formula-line indent">+ <span class="text-term">old products to new partners</span></div>
  <div class="formula-line indent">+ <span class="text-term">new products</span> - <span class="text-term">exits</span></div>
</div>

The econometric intuition is path dependence. If exporter `i` sells product `k` to markets near country `j`, or to markets sharing language or borders with `j`, it may be more likely to enter `j` next. This can reflect learning about demand, distribution, standards, logistics, or reputation.

### Main Findings

The paper's headline finding is that about one-third of the export growth of the 23 developing economies from 1970 to 1997 can be accounted for by sales of long-standing exportables to new trading partners. In their product-line decomposition, new products account for a much smaller share; the paper reports new products contributing only about 6.8 percent of observed export growth in one main table.

The econometric results support a path-dependent geographic spread story. Market size and proximity matter. Experience in the destination and in nearby or related markets raises the probability of serving a new market. The paper uses several proximity measures: border, language, and distance-based proximity to already supplied markets. The broad lesson is that new destination entry is not random; it follows a spatial and informational logic.

An important detail for this repo is that the paper studies the disappearance of zeros in bilateral trade matrices. That is exactly the product-partner-cell problem. A zero in a bilateral product matrix can disappear because an exporter learned about a new market, because distribution networks expanded, because a neighboring destination created information spillovers, or because the initial zero was just a reporting threshold artifact. Evenett and Venables make the first mechanism plausible by showing that prior export experience around a destination predicts later entry. For the repo, this suggests that the cell-level extensive margin should be read as a network-expansion margin, not only as a product-discovery margin.

### What To Borrow For This Repo

Borrow the product-partner-cell framing. In Exercise 12, product-partner-cell entry is not the same as product entry or partner entry. A cell can be new even if the product and partner both existed separately. That is a recombination margin, and Evenett-Venables is one of the main papers that makes recombination economically meaningful.

Borrow the geographic spread mechanism. The repo's partner and region transition outputs can be extended to ask whether new product-partner cells appear in nearby regions, same-region partners, or partners connected to the country's existing export network. This would turn the transition table into a learning/proximity test rather than just an accounting table.

Borrow the cutoff logic. Tiny product-partner flows should not be over-interpreted as real market entry. A minimum value threshold, persistence requirement, or least-traded approach can make "entry" more economically meaningful.

Borrow their distinction between old products and new partners for the exact wording of repo results. Instead of saying "new cells drove growth," say whether growth came from established products sold to additional partners, new products sold to established partners, genuinely new product-partner combinations, or scaling of continuing cells. That language will make the results much harder to misread. It will also help when comparing Exercise 12 to Exercise 11: if import-concentration products are not strongly export-linked at HS6, there may still be a broader market-expansion story inside existing exportables.

### Limits, Measurement Problems, And Cautions

The paper uses three-digit product lines, which are much broader than HS6. A "new destination for an existing product" at three digits may hide finer product changes inside the category. In this repo, HS6 harmonized family gives more detail, but also more code instability.

The $50,000 cutoff makes sense for their period and data, but thresholds should be updated or expressed in real terms for modern Comtrade. For this repo, thresholds should be sensitivity checks, not hidden defaults.

Another caution is that destination entry is not independent across products. The same exporter, logistics provider, port route, distributor, or trade agreement can affect many product lines at once. A country-product-partner regression with many observations can therefore look more precise than it really is if standard errors ignore dependence within country-partner or country-year shocks. If this repo estimates entry models, it should consider clustering at reporter country and possibly two-way clustering by reporter and partner or product, depending on the specification and sample size.

Proximity variables can capture many mechanisms: lower transport cost, cultural similarity, information spillovers, trade agreements, or regional value chains. The paper's proximity results are suggestive of learning, but not a clean causal estimate of learning.

The partner-only rule for `999999` differs from product-cell work. If analyzing product-partner cells, exclude `999999`. If only aggregating products into reporter-partner totals, partner concentration may include it by repo convention.

### Concrete Next Empirical Moves

1. For Exercise 12, split new product-partner cells into three groups: new product with existing partner, existing product with new partner, and existing product with existing partner but new cell.
2. Add a geographic spread table: among new cells for existing products, what share are in the same region as previously served partners?
3. Estimate a simple descriptive entry model at the country-product-partner-year level: entry on lagged same-product neighboring partner activity, partner market size, distance or region, and country-product fixed effects if data permit.
4. Use minimum-value and two-year persistence definitions of entry to reduce noise.
5. Compare the partner entry pattern for high-income, middle-income, and low-income country-years, since geographic spread may matter differently by development stage.

### Reading Notes / What To Remember

Evenett and Venables is the "new markets for old goods" paper. For this repo, it is the reason to decompose product-partner-cell entry rather than treating every new cell as product discovery. The main project question after reading it is: are countries discovering new products, finding new customers for existing products, or recombining existing product and partner sets?

## 4. Brenton And Newfarmer 2007: Discovery Versus Scaling

### Why This Paper Matters For My Project

Brenton and Newfarmer is a development-economics complement to Kehoe-Ruhl and Evenett-Venables. It directly asks whether export growth is mostly about discovering new products or about scaling known products and spreading them to new markets. That is one of the central interpretation problems in this repo. Exercise 12's product entries can look like discovery, but product-partner-cell entries can also reflect geographic expansion. Brenton and Newfarmer forces the distinction.

The paper also provides policy caution. If most growth comes from expanding existing flows or existing products to new markets, then a policy agenda focused only on "discovering" brand-new products is too narrow. For this project, the analogous caution is interpretive: do not treat high product or cell entry as proof that new industrial capabilities have been discovered.

### Big Question And Intuition

The Feynman-style version is: when a country's exports grow, is it because it found a brand-new thing to sell, or because it got better at selling things it already had? A farmer who starts exporting mangoes to five new countries has diversified geographically, even if no new product was discovered. A manufacturer that doubles exports of an existing product has grown through scaling, not discovery.

Brenton and Newfarmer ask whether the "discovery channel" deserves all the attention it gets. They do not deny discovery matters. They ask whether discovery is the binding margin in observed export growth, and whether post-discovery scaling may be more important.

### Data And Unit Of Observation

The paper studies developing-country exports over 1995-2004. It prefers SITC data because HS revisions in 1996 and 2002 complicate HS-based time comparisons. After consistency restrictions, the paper uses 3,078 SITC products. The unit is country-product-market flow, which maps naturally to this repo's country-product-partner-year export cell.

They decompose export growth into existing bilateral flows, exports of existing products to new markets, exports of new products to existing markets, and exports of new products to new markets. This is very close to the Exercise 12 taxonomy, except Exercise 12 also distinguishes top-10 items and reports net and gross contribution shares.

### Core Decomposition Or Model Logic

The paper's useful decomposition is:

<div class="formula-block">
  <div class="formula-line"><span class="text-term">growth</span> = <span class="text-term">existing products to existing markets</span></div>
  <div class="formula-line indent">+ <span class="text-term">existing products to new markets</span></div>
  <div class="formula-line indent">+ <span class="text-term">new products to existing markets</span></div>
  <div class="formula-line indent">+ <span class="text-term">new products to new markets</span></div>
  <div class="formula-line indent">- <span class="text-term">declines and extinct flows</span></div>
</div>

The first term is intensive growth in established trade relationships. The other terms are extensive margins, but they are not the same extensive margin. The "existing product to new market" term is the Evenett-Venables channel. The "new product" terms are closer to discovery.

### Main Findings

The main empirical result is that the intensive margin dominates in their sample. They report that existing bilateral flows account for about 80.4 percent of export growth, while the extensive margin accounts for about 19.6 percent. Within the extensive margin, exports of existing products to new markets are the important part, contributing about 18.2 percent of total export growth. New products to existing markets contribute only about 1.1 percent, and new products to new markets essentially zero in their main decomposition.

The paper also finds heterogeneity. Africa is an important exception: the extensive margin is more important there, but part of the reason is weak performance in maintaining and expanding existing flows. Low-income countries may show more product and market experimentation, but that does not automatically translate into strong growth if survival and scaling are weak.

The Africa result matters because it prevents an overly simple "intensive margin always dominates" reading. In poorer settings, new products and new markets may matter more, but the reason may be that established flows are fragile. That is a different diagnosis from saying discovery is highly successful. For this repo, when a country shows high product or cell entry shares, compare those shares with gross contraction and later survival. High entry plus high contraction is churn. High entry plus survival and later top-10 movement is stronger evidence of durable diversification.

The policy conclusion is broader than "subsidize discovery." Export success may require post-discovery support: market information, standards, logistics, finance, reliability, and the ability to scale relationships that already exist.

### What To Borrow For This Repo

Borrow the four-way cell classification. Exercise 12 should report new product-partner cells by whether the product is new to the country, the partner is new to the country, both are new, or neither is new but the pairing is new. This directly maps to Brenton-Newfarmer's discovery versus geographic expansion distinction.

Borrow the negative-flow awareness. Exercise 12 already reports gross positive and gross contraction shares. That is important because net new-item shares can hide large offsetting exits and contractions. Brenton and Newfarmer's framework supports reading gross and net together.

Borrow the policy caution as an interpretation caution. If this repo finds high concentration or reconcentration, it should not immediately conclude a lack of discovery. Countries may be choosing or being forced into scaling a small set of successful flows. That can be consistent with productivity, firm selection, or superstar mechanisms.

Borrow the export-cycle language. A product can move through discovery, rapid growth, maturation, and decline. Exercise 12 already has the building blocks for this: new items, continuing non-top items, continuing top items, shrinking items, and exited items. Reframing those categories as stages in an export cycle would make the transition exercise easier to explain. For example, a new product that survives and becomes non-top but growing is in a post-discovery phase; a continuing top product with positive growth is mature scaling; a top product with contraction is a possible decline phase.

### Limits, Measurement Problems, And Cautions

SITC is more stable than HS over this period, but it is also coarser than HS6. The paper's small new-product contribution may partly reflect broader product categories. In this repo, HS6 may show more product entry, but some of that entry is classification noise or within-category detail that SITC would hide.

Their results are descriptive decompositions. They do not prove which policies caused growth or which constraints bind. For this repo, the same applies: Exercise 12 is an accounting exercise, not a causal model.

The definition of "new market" and "new product" depends on thresholds and time windows. A product absent in 1995 but present in 2004 may have entered and exited several times in between. Gross transition files should be used when possible.

The paper also warns against treating policy implications as automatic. If growth comes mostly from existing products to new markets, the policy bottleneck might be standards, trade finance, shipping reliability, market intelligence, or diplomatic market access. If growth comes from new products but those products die, the bottleneck might be survival and scaling. The same decomposition can point to very different mechanisms, so the repo should keep its empirical language descriptive unless a separate design identifies constraints.

Again, `999999` must be excluded from product and product-partner work before constructing any discovery/scaling categories.

### Concrete Next Empirical Moves

1. Add a Brenton-Newfarmer summary table to Exercise 12 outputs: existing product-existing partner, existing product-new partner, new product-existing partner, new product-new partner.
2. Compute this table for net growth and gross positive growth. The difference will show how much contraction is hidden in net accounting.
3. Run the table by income group or GDP-per-capita bins to see whether low-income countries rely more on new products or new partners.
4. For countries with rising concentration, ask whether growth is concentrated in existing top-10 product-partner cells or in new cells that later become top-10.
5. Add a "post-discovery scaling" diagnostic: among products first appearing in a country, what share survive and reach meaningful export value by 5 or 10 years?

### Reading Notes / What To Remember

The paper's main lesson is "discovery is not the whole channel." For this repo, it means product entry is only one part of export growth. The more useful question is whether countries can scale, persist, and spread existing capabilities across markets.

## 5. Besedes And Prusa 2011: Survival, Churn, And Export Growth

### Why This Paper Matters For My Project

Besedes and Prusa is the survival warning. Exercise 12 can show a lot of new product or product-partner-cell entry, but entry alone is weak evidence. Many new export relationships die quickly. If new relationships do not survive, then measured diversification may be churn rather than durable structural change.

This paper is especially relevant because the Exercise 12 gross tables already show large contraction and exit shares. For product-partner cells, median gross contraction shares are large for exited non-top-10 cells, and gross positive shares show many new cells. Besedes and Prusa explains why gross churn is not just noise; it is a central margin of export performance.

### Big Question And Intuition

The Feynman-style version is: opening a new export relationship is like opening a new shop in a foreign market. The opening day tells you little. The question is whether the shop is still there two years later, whether sales grow, and whether the fixed costs of entry were worth it. Countries can look active because they constantly open shops, but if most close quickly, long-run exports will not grow much.

The misconception they correct is that extensive-margin growth equals export success. A country can have many new relationships and still underperform if survival is low or if surviving relationships fail to deepen.

### Data And Unit Of Observation

The paper uses disaggregated export data for 46 countries between 1975 and 2003, covering annual bilateral export observations and converting them into export spells. The unit is an export relationship, generally a country-product-destination spell. If a country exports the same product to the same destination in 1978-1984 and then again in 1989-1994, those are treated as distinct spells.

This is very close to the repo's product-partner-cell time series. The main difference is that this repo's Exercise 12 currently summarizes transitions over 5- and 10-year horizons, while Besedes and Prusa emphasize annual spell duration, hazards, survival, and deepening.

### Core Decomposition Or Model Logic

The theoretical motivation extends a Melitz-style model. Exporters face a one-time sunk entry cost and a per-period fixed cost for maintaining a destination relationship. With imperfect information, firms may enter, learn that fixed costs or demand conditions are unfavorable, and exit quickly.

The empirical decomposition separates export growth into entry, survival, and deepening:

<div class="formula-block">
  <div class="formula-line"><span class="text-term">export growth</span> = <span class="text-term">entry of new relationships</span> + <span class="text-term">survival of existing relationships</span> + <span class="text-term">deepening of survivors</span></div>
</div>

Survival is the probability a relationship remains active after a given number of years. Deepening is growth in value conditional on survival. The paper's key point is that survival is a precondition for deepening.

### Main Findings

The paper finds that most export relationships are short-lived. More than half fail within the first two years, and in some countries roughly seven out of ten new relationships fail within two years. Median survival is only one or two years across regions. Hazard rates are high early in a spell and decline with age; new relationships are much more fragile than established relationships.

The counterfactual results show that survival and deepening matter more for long-run export growth than raw entry. Developing countries often do not suffer from too little experimentation alone. They suffer because new relationships fail quickly and surviving relationships do not scale enough. For Africa, the paper highlights poor survival as a major constraint on export performance.

This reconciles the apparent conflict between papers that find extensive-margin activity and papers that find intensive-margin importance. If many entries die, then gross extensive-margin activity can be high while long-run value growth is driven by survival and deepening.

The paper's dynamic accounting is especially useful because it explains why point-to-point decompositions can be misleading. If a cell is absent in 1990 and present in 2000, a two-year comparison may call it entry, but the cell may have entered in 1992, exited in 1994, re-entered in 1997, and survived only briefly after 2000. Conversely, a cell that is present in both endpoint years may have had a long interruption between them. For this repo, endpoint Exercise 12 tables are valuable summaries, but spell files are needed to know whether the transition is durable or just intermittently observed.

### What To Borrow For This Repo

Borrow the spell approach for product-partner cells. Exercise 12 should not stop at whether a cell is new by the end of a 5- or 10-year window. It should ask whether the cell survives one, two, five, and ten years after first appearing. This is the most direct way to turn the repo's transition exercise into a durability analysis.

Borrow the age/hazard idea. A product-partner cell that has existed for 10 years is not comparable to a cell that just entered. Hazards should be estimated by spell age, not only by calendar year. This matters for interpreting high churn among non-top cells.

Borrow the distinction between survival and deepening. A country may successfully keep new cells alive but fail to scale them; or it may have few surviving entries but very strong growth among survivors. Those are different development stories.

Borrow their warning about vintage. New relationships are not comparable to old relationships because their hazard rates differ sharply. A product-partner cell that entered this year should be evaluated against other first-year cells, not against mature top-10 cells. This matters for concentration: mature top cells can dominate value partly because they have already passed the high-hazard early years. A naive comparison of top versus non-top cells may confuse age, scale, and survival selection.

### Limits, Measurement Problems, And Cautions

Annual zeros in trade data can be noisy. A relationship may appear to exit because of reporting thresholds, shipment lumpiness, temporary demand shocks, or code changes. That means survival definitions should be robust to one-year gaps, minimum value thresholds, and harmonized product families.

HS revisions can artificially end a spell and start a new one. For this repo, use harmonized HS6 families for product and product-partner spell analysis, and compare with HS4/HS2 robustness when the interpretation depends on survival.

The paper's relationships are still aggregate trade relationships, not firm-level relationships. A product-partner cell can survive even if the firms inside it change. Conversely, a firm may survive by switching HS6 codes. Firm-level data would be needed to see that.

`999999` must be excluded before spell construction for product or product-partner cells. Otherwise a residual product category can create fake long spells or fake exits.

### Concrete Next Empirical Moves

1. Build product-partner-cell spells from the Exercise 12 aggregate data using harmonized HS6 families.
2. Estimate Kaplan-Meier survival curves for product spells and product-partner-cell spells by income bin, region, and concentration trajectory.
3. Report one-year, two-year, five-year, and ten-year survival of new cells.
4. Add a gap-tolerant spell definition: allow one missing year inside a spell and compare results.
5. Measure deepening among survivors: conditional on a new cell surviving five years, what is its value growth and does it enter the top-10?
6. Link survival to concentration: do countries with rising concentration have lower survival of non-core cells, or do they drop mismatched cells more selectively?

### Reading Notes / What To Remember

The main takeaway is "entry is not success." Besedes and Prusa should sit next to every Exercise 12 chart. A high new-cell share can be exciting, but the serious question is whether those cells survive and deepen.

## 6. Cadot, Carrere, And Strauss-Kahn 2011: Export Diversification Hump

### Why This Paper Matters For My Project

This is the closest paper to the repo's product concentration question. It studies how export diversification changes over the development path using HS6 product-level data, and it finds a hump-shaped pattern: countries diversify as they grow, then eventually reconcentrate. That is directly relevant to interpreting trade concentration in this project. Rising concentration is not automatically a data error or policy failure; it may reflect development-stage reconcentration.

The paper is also central because it raises the Section 16 issue the user flagged. HS Section 16, machinery and electrical equipment, has many product lines and high export value per line. If high-income countries specialize in Section 16, raw product-line counts and value shares can mechanically affect measured concentration. The paper addresses this with robustness checks, but the user reasonably wants to understand the issue in the repo's own data. The repo now has a Section 16 diagnostic showing that in rd2 2021, Section 16 accounts for 14.5 percent of distinct HS6 export lines and 28.9 percent of export value, with `999999` excluded.

### Big Question And Intuition

The Feynman-style version is: poor countries may start with a narrow export basket. As they develop, they learn to make and sell more things, so exports diversify. Later, rich countries may stop making old, lower-factor-intensity products and concentrate in products closer to their advanced endowments. The curve is a hill: concentration falls at first, then rises.

The misconception the paper corrects is that diversification should monotonically increase with development. Instead, diversification can be a transition process. Countries may first add new products faster than they drop old ones. Later, dropping old-cone products can dominate entry, causing reconcentration.

### Data And Unit Of Observation

The paper uses a large panel of 156 countries over 1988-2006 at HS6 disaggregation, with 4,991 product lines. The main unit is country-year-product export value, aggregated to country-year concentration measures and active-line counts. They study concentration indices such as Theil, Gini, and Herfindahl, and they also count the number of active export lines.

For the factor-intensity exit analysis, they use country endowments, such as capital per worker and educational achievement, and revealed factor intensities at the HS6 product level. The unit becomes country-product closure or entry, with product intensity compared to country endowment.

### Core Decomposition Or Model Logic

The paper uses Theil's decomposability to separate concentration changes into between-group and within-group components. The broad mapping is:

<div class="formula-block">
  <div class="formula-line"><var>T</var> = <var>T</var><sub>between</sub> + <var>T</var><sub>within</sub></div>
</div>

With a partition between active and inactive lines, the between component captures extensive-margin changes related to the mass of active lines, while the within component captures concentration among active lines. This is why Theil is useful: unlike Gini, it decomposes neatly.

For the diversification-cone logic, the paper compares country endowments to product factor intensities. A simplified distance object is:

<div class="formula-block">
  <div class="formula-line"><var>d</var><sub>ikt</sub> = [(<var>H</var><sub>it</sub> - <span class="hat">H</span><sub>k</sub>)<sup>2</sup> + (<var>K</var><sub>it</sub> - <span class="hat">K</span><sub>k</sub>)<sup>2</sup>]<sup>1/2</sup></div>
</div>

If rich countries are closing old-cone lines, closed products to the right of the turning point should be farther from the country's endowment vector than ordinary closures to the left of the turning point.

### Main Findings

The paper finds a robust hump-shaped relationship between export diversification and GDP per capita. In pooled and within specifications, the turning point is around $25,000 PPP. In robustness checks using system GMM to address potential endogeneity of GDP per capita to export concentration, the turning point varies roughly between $24,000 for Herfindahl and $29,000 for Gini, with the same broad set of countries to the right of the turning point.

The decomposition result is crucial. Diversification and reconcentration occur mostly along the extensive margin. Before the turning point, countries add active lines and concentration falls. Around and after the turning point, closures become more important, and concentration rises. The within-active-lines component moves too, but the extensive margin is the main story.

The Section 16 robustness is important. The paper notes that Section 16 has an unusual classification design, with many lines and high value per line. They aggregate sections 6, 11, and 15 to broader levels and drop Section 16 in a robustness exercise. They report that the turning point remains robust in pooled and within estimates. That means they argue Section 16 does not mechanically create the hump, but it remains a measurement concern worth auditing in any new dataset.

The factor-intensity evidence supports the diversification-cone interpretation. Closed lines in countries to the right of the turning point are farther from the closing country's endowment vector than closures to the left. New lines do not show the same difference. In the signed mismatch results, closed lines to the right tend to be less intensive than the rich country's endowment, consistent with rich countries dropping products that are too low-factor-intensity for their current comparative advantage.

### What To Borrow For This Repo

Borrow the hump framing for concentration over development. When plotting product concentration against GDP per capita, include a quadratic or nonparametric fit and identify where the turning point lies in the repo sample. Do not assume concentration should always fall with income.

Borrow the Theil decomposition if the project needs a clean extensive-versus-intensive concentration decomposition. Theil can separate active-line expansion from reallocation among active lines more naturally than Gini.

Borrow the Section 16 forensic approach. The repo should compare HS section line shares and value shares, then rerun key concentration patterns excluding Section 16 or aggregating it more coarsely. The existing rd2 2021 diagnostic is the first step, but the paper suggests doing this over time and in regression-style checks.

Borrow the factor-intensity exit idea for a new empirical exercise. At the country-product-year level, define exit and measure distance between country endowments and product revealed factor intensity. Then test whether distance predicts exit more strongly after the country is on the rich/reconcentrating side.

### Limits, Measurement Problems, And Cautions

The hump is descriptive even with system GMM robustness. System GMM addresses dynamic-panel endogeneity concerns under assumptions about instruments, but it does not turn the pattern into a structural causal estimate of development causing reconcentration.

GDP per capita can proxy many things: endowments, institutions, demand, technology, market size, data quality, and trade policy. The turning point is useful, but not a universal law.

Section 16 remains a serious measurement issue. Dropping it as a robustness check shows whether the headline survives, but it also removes a real high-value modern manufacturing sector. The better repo approach is to show both: benchmark with all real HS6 products except `999999`, a Section 16-excluded sensitivity, and section-level diagnostics explaining why.

Product factor intensity is revealed, not physical. A product's average exporter endowment may reflect who currently exports it, not a technological necessity. This is still useful, but the measure should be interpreted as revealed comparative-advantage intensity.

### Concrete Next Empirical Moves

1. Replicate the Section 16 line-value scatter over multiple years for rd2 countries, labeling all HS sections in plain English.
2. Rerun product concentration trends with Section 16 included, Section 16 excluded, and Section 16 aggregated to HS4 or HS2. Label exclusions as sensitivities.
3. Construct a Theil decomposition into active-line and within-active components for product exports, excluding `999999`.
4. Estimate an exit model: product exit on factor-endowment distance, right-of-turning-point status, and their interaction, with country, product, and year fixed effects where feasible.
5. Use signed mismatch, such as country capital per worker minus revealed product capital intensity, to test whether rich countries disproportionately exit products that are "too low-tech" for their current endowments.
6. Connect the exit model to Exercise 12: are exited non-top products farther from endowments than continuing non-top products?

### Reading Notes / What To Remember

This is the development-stage reconcentration paper. Remember three pieces: the hump, the extensive-margin decomposition, and the old-cone exit mechanism. For this repo, it justifies studying concentration as a dynamic development object, while Section 16 forces careful measurement.

## 7. Eaton, Kortum, And Kramarz 2011: Firm-Destination Anatomy

### Why This Paper Matters For My Project

Eaton, Kortum, and Kramarz moves below aggregate product and partner data to the firm-destination level. This matters because a product-partner cell in Comtrade is not an actor. It is an aggregate of firms deciding whether to serve a destination and how much to sell. If this repo sees concentration across partners or product-partner cells, the mechanism may be firm selection: only some firms can profitably reach harder markets, and larger or more efficient firms serve more destinations.

The paper is especially relevant to the partner margin and product-partner-cell margin in Exercise 12. Partner entry is small in the median headline results, while cell entry is large. EKK helps explain why the number of sellers to a destination and the size of sales per seller vary systematically with market size, trade costs, and firm heterogeneity.

### Big Question And Intuition

The Feynman-style version is: not every firm can sell everywhere. Nearby, large, easy markets get many firms. Small or difficult markets get only the strongest firms. If a firm sells to many markets, that tells you something about its underlying strength. Aggregate trade patterns are the sum of many firm market-entry decisions.

The misconception they correct is that countries simply ship products to destinations as a representative exporter. In reality, the set of firms serving a destination changes with destination size, trade frictions, and firm efficiency.

### Data And Unit Of Observation

The paper uses French customs and firm data for 1986, with 229,900 French manufacturing firms and 113 destinations including France. Fewer than 34,035 firms export outside France, and the most geographically widespread firm sells to 110 destinations.

The core unit is firm-destination sales, with information on domestic sales and export participation. For this repo, the closest aggregate analogues are partner-year export totals and product-partner cells. But EKK's unit is richer because it observes which firms sit inside those cells.

### Core Decomposition Or Model Logic

The empirical regularities are organized around three objects:

<div class="formula-block">
  <div class="formula-line"><span class="text-term">number of French firms selling to destination</span> = <span class="func">f</span>(<span class="text-term">market size, trade costs, firm selection</span>)</div>
  <div class="formula-line"><span class="text-term">sales per firm</span> = <span class="func">g</span>(<span class="text-term">destination difficulty and selected firm strength</span>)</div>
</div>

The model is a heterogeneous-firm export participation model estimated by simulated moments. Firms have underlying efficiency and market-specific shocks. More efficient firms are more likely to enter more markets and harder markets, but conditional sales also contain substantial market-specific variation.

### Main Findings

Three empirical regularities stand out. First, the number of French firms selling to a market, normalized by French market share, increases with market size. Bigger markets attract more sellers. Second, average sales in France rise systematically among firms that sell to less popular destinations and among firms selling to more destinations. That means firms that reach harder or more numerous markets are stronger at home too. Third, sales distributions look surprisingly similar across markets, despite huge differences in market size and French participation.

The estimated model implies that underlying efficiency explains nearly half the variation in market entry across firms, but much less of the variation in sales conditional on entry. In other words, firm strength matters a lot for whether a firm gets into a market; once inside, market-specific sales shocks also matter.

For this project, the most useful implication is that partner participation and value per partner are jointly determined. A difficult destination can have few exporters but high average sales because only the strongest firms enter. In aggregate data, a country can therefore look concentrated across partners because only a few destination relationships clear the fixed-cost threshold, or because the value conditional on entry is very skewed. Those two cases call for different diagnostics: active partner and cell counts for the first, value per active cell and top-cell shares for the second.

### What To Borrow For This Repo

Borrow the idea that partner and cell concentration can reflect firm selection. If only a few firms can serve difficult destinations, then partner concentration may rise even without product concentration. A country may appear concentrated in a few destination-product cells because those are the cells where its strongest firms can operate.

Borrow destination-popularity diagnostics. For each country in this repo, rank partners by how many countries or product lines serve them, then ask whether new product-partner cells tend to enter popular destinations first. This would be an aggregate-data analogue of EKK's destination hierarchy.

Borrow the market-size relationship. New partner or cell entry should be compared with partner market size, distance, region, and existing trade links. If new cells mostly enter large nearby markets, that supports a selection/gravity interpretation rather than random experimentation.

Borrow the hierarchy diagnostic, but use it carefully. EKK show that firm entry across destinations is not perfectly hierarchical: selling to a hard market does not mechanically imply selling to every easier market. Still, there is a strong ordering. In aggregate data, the analogous question is whether countries enter product-partner cells in a predictable sequence: large regional partners first, then larger global partners, then smaller or more distant partners. That sequence would be useful evidence for market-learning and fixed-cost mechanisms.

Also borrow the idea that extensive and intensive partner margins are connected. A destination with few sellers can still have high average sales per seller because only strong firms enter. In aggregate data, a partner with few active products or cells may still have high value per active cell. This is a reason to report both active-cell counts and value per active cell when studying partner concentration.

### Limits, Measurement Problems, And Cautions

France in 1986 is a high-income manufacturing exporter. The mechanisms may differ for smaller developing countries, commodity exporters, or countries where state firms and intermediaries dominate trade.

The customs-firm match is also much cleaner than what aggregate Comtrade can offer. The paper sees domestic sales, export destinations, and firm identifiers. This repo sees reporter, partner, product, year, and value. That means any EKK-inspired result here should be framed as an aggregate analogue, not as evidence on firm efficiency. The point is to discipline interpretation, not to claim firm-level mechanisms have been directly measured.

Aggregate data cannot identify firm entry. A product-partner cell can grow because more firms enter, because one incumbent firm scales, because a superstar firm arrives, or because prices rise. Without firm IDs, the repo can only infer these mechanisms indirectly.

The paper is mostly cross-sectional. It helps interpret participation patterns, but Exercise 12 is dynamic. For dynamic firm product scope, Bernard, Redding, and Schott and Freund-Pierola are better complements.

Another limitation is that the paper studies destinations, not products. It tells us a lot about which firms sell where, but less about which products they sell within each market. In the repo, the product-partner-cell is both a destination decision and a product-scope decision. If a cell appears, it may reflect a firm entering a destination with a product it already exports elsewhere, a firm adding a product inside an existing destination, or a new firm. EKK helps with the first component, but it needs BRS for product scope and Freund-Pierola for top-firm concentration.

For product-partner cells, exclude `999999` before aggregation. For partner-only analysis, follow the repo convention on `999999`, but be explicit if comparing with product-dependent results.

### Concrete Next Empirical Moves

1. Build destination popularity measures: number of rd2 exporters serving each partner, total import market size, and number of active HS6 products imported by partner.
2. In Exercise 12, classify new product-partner cells by partner popularity decile.
3. Estimate descriptive entry regressions: new cell entry on partner market size, prior country-partner exports, prior country-product exports, and partner fixed effects or region controls.
4. Test whether high-concentration countries have fewer active partners because they are absent from small/difficult markets or because they concentrate within large markets.
5. If firm data become available, decompose product-partner-cell growth into number of exporters and average exports per exporter.

### Reading Notes / What To Remember

EKK is the firm-destination selection paper. For this repo, remember that every aggregate partner or product-partner cell is hiding a firm participation margin. Partner concentration may be a market-entry selection outcome, not just a country-level diversification choice.

## 8. Bernard, Redding, And Schott 2011: Multi-Product Firms And Product Dropping

### Why This Paper Matters For My Project

Bernard, Redding, and Schott is the multi-product-firm paper. It matters because a country-product export transition can be caused by existing firms changing their product scope, not only by new firms entering or old firms exiting. If the repo observes product reconcentration, one possible mechanism is that multi-product firms drop weaker products and focus on core products. That can be productivity-enhancing, not necessarily a failure of diversification.

This paper also connects product concentration to trade liberalization. Opening to trade can make competition tougher and induce firms to drop low-performing products. Aggregate product exit may therefore reflect within-firm reallocation toward stronger products.

### Big Question And Intuition

The Feynman-style version is: imagine a firm making ten products. Some are core strengths, others are side products. When competition rises or export opportunities change, the firm may stop making the weak products and focus on what it does best. At the country level, this looks like product exit and rising concentration, but inside the firm it can be rational upgrading.

The misconception the paper corrects is that firms are single-product units or that product entry/exit is only about firm birth and death. Multi-product firms can change the export basket from inside.

### Data And Unit Of Observation

The paper combines theory with U.S. microdata on firms, products, and destinations. The relevant empirical unit is firm-product-destination exports, plus firm characteristics and trade policy variation. It studies how firms choose export destinations and product ranges.

For this repo, the observable aggregate unit is country-product-partner-year. Without firm IDs, we cannot separate new products from new firms versus existing firms adding products. But the paper tells us what mechanism could be hiding inside aggregate transitions.

### Core Decomposition Or Model Logic

The model has firms with an overall ability component and firm-product-specific attributes. A firm enters if its ability is high enough, then chooses which products to supply in which markets. The product cutoff logic is:

<div class="formula-block">
  <div class="formula-line"><span class="text-term">firm supplies product</span> <span class="op">&Leftrightarrow;</span> <span class="text-term">firm ability</span> + <span class="text-term">product attribute</span> <span class="op">&ge;</span> <span class="text-term">market cutoff</span></div>
</div>

Trade liberalization changes cutoffs. Low-ability firms may exit, high-ability firms export, and surviving firms may drop weaker products as competition reallocates activity toward stronger products.

### Main Findings

The paper shows that trade liberalization can reduce the number of products firms produce by causing them to drop their least attractive products. That within-firm compositional change can raise measured firm productivity because resources shift toward stronger firm-product combinations.

The empirical patterns support selection within firms. Firms exporting many products also tend to serve many destinations and export more of a given product to a destination. The distribution of export sales across products within firms is skewed: a firm's top products account for a large share of its exports. Fixed-effect decompositions show that firm-product components matter, not just product or destination components.

The broader implication is that product scope is endogenous. Product exit is not always a sign of decline. It can be part of adjustment toward core competence.

A useful way to connect this to Cadot et al. is to treat product exit as potentially selective rather than accidental. Cadot's rich-country closures are far from current endowments; BRS gives a firm-level story for why such closures might occur. Firms facing tougher competition or better outside opportunities reallocate away from weak products. At the aggregate level, that can look like a country leaving old-cone sectors. The two papers are not the same mechanism, but they point in a similar direction: reconcentration can be active selection, not mere disappearance.

### What To Borrow For This Repo

Borrow the core-competence interpretation for reconcentration. If a country drops products and concentration rises, ask whether those products were peripheral, small, low-survival, or far from the country's factor endowments. This links BRS to Cadot et al.'s old-cone exit mechanism.

Borrow the firm-product-destination hierarchy as the ideal data structure. The repo currently has country-product-partner cells. If firm-level customs data become available, the next decomposition should split new country-product exports into new firms, existing firms adding products, existing firms adding destinations, and top firms scaling existing products.

Borrow the within-firm reallocation caution for Exercise 11. If import-concentration products are weakly linked to exports, that may be because firms import inputs for core exported products that sit in different HS6 codes. HS2 robustness partly addresses this, but firm-product input-output data would be better.

Borrow the "who adds the product?" question. A new exported HS6 code can come from a new exporter, an existing exporter adding a side product, a superstar expanding scope, or a reclassification of a continuing firm product. These cases have different implications. New firms suggest entry and entrepreneurship. Existing firms adding products suggest scope expansion. Superstars expanding scope suggest concentration underneath apparent diversification. The current repo cannot separate these yet, but the study guide should keep those mechanisms visible so future data work asks the right question.

Borrow the distinction between product count and product importance. A firm can drop many tiny peripheral products while total exports rise because core products expand. In aggregate data, that means falling active-line counts and rising concentration can coexist with healthy export growth. The repo should therefore pair active-product counts with value-weighted concentration and average value per surviving product.

### Limits, Measurement Problems, And Cautions

Aggregate HS6 data cannot identify within-firm mechanisms. A product exit in Comtrade could mean all firms stopped exporting it, one large firm reclassified its product, or a set of small firms disappeared while a large firm shifted scope.

Trade liberalization effects in the paper should not be casually applied to every concentration episode. Reconcentration could come from commodity price shocks, exchange rates, sanctions, demand shifts, or data changes.

Product definitions matter. Multi-product firms often operate at a finer level than HS6. A firm may drop a product variety without changing its HS6 code, or switch products inside a code without an observed product transition.

The model is also about responses to trade liberalization and market access, while this repo's concentration patterns may be driven by many forces. Commodity booms, exchange-rate changes, China's demand, sanctions, supply-chain relocation, or changes in reporting practice can all move product concentration. BRS is a mechanism to consider, not a universal explanation.

Exclude `999999` before product or product-partner aggregation. It cannot represent a firm's meaningful product scope.

### Concrete Next Empirical Moves

1. For country-product exits in Exercise 12, classify whether exiting products were top-10, non-top, low-value, or low-survival. Peripheral exits are more consistent with core-competence reallocation.
2. Combine the Cadot-style mismatch variable with product exit: are exits disproportionately in products far from country endowments?
3. Add a "scope narrowing" measure: among countries with rising product concentration, count whether active products fall while average value per surviving product rises.
4. If firm data become available, decompose new products into products added by incumbent exporters versus products introduced by new exporters.
5. For Exercise 11, test broader production-chain linkages at HS2 or BEC categories when exact HS6 import-export links are too narrow.

### Reading Notes / What To Remember

BRS is the "firms drop weak products" paper. For this repo, it prevents a simplistic reading of product exit. Reconcentration may reflect specialization toward core capabilities, not just loss of diversification.

## 9. Freund And Pierola 2012/2015: Export Superstars

### Why This Paper Matters For My Project

Freund and Pierola adds the superstar-firm warning. Aggregate export concentration can be driven by a small number of firms, not by broad changes across many producers. If one or two very large exporters dominate a sector or product, country-level product concentration can rise even if many smaller firms are diversified. This matters for interpreting both Exercise 11 and Exercise 12.

Exercise 12's top-10 categories already point in this direction: existing top items dominate partner-level net growth, while product and cell margins show large new-item shares. Freund and Pierola says to ask whether top items are broad national specializations or the footprint of a few giant firms. Without firm data, the repo cannot answer directly, but it can look for indirect signs: top-product shares, cell skewness, concentration among top product-partner cells, and abrupt jumps consistent with large firm entry.

### Big Question And Intuition

The Feynman-style version is: a country's exports may look like a national orchestra, but sometimes the sound is mostly one soloist with a very large amplifier. If the top one percent of exporters account for most exports, then aggregate trade patterns are partly about those firms.

The misconception the paper corrects is that sectoral export differences are mostly about the number of firms in each sector. They show that average firm size, especially the size of top firms, explains much more.

### Data And Unit Of Observation

The paper uses firm-level exporter data from 32 countries. The unit is firm-product group-country-year, with firm-level export values and sectoral/product group classifications. They focus on non-oil exports and identify the top 1 percent of exporters in each country as export superstars.

For this repo, the missing unit is the firm. The available units are product, partner, and product-partner cell. That means Freund and Pierola is mostly a mechanism paper for this project: it tells us what aggregate concentration may be hiding.

### Core Decomposition Or Model Logic

The basic decomposition is sector exports as number of firms times average firm exports:

<div class="formula-block">
  <div class="formula-line"><var>X</var><sub>cs</sub> = <var>N</var><sub>cs</sub> <span class="op">&times;</span> <span class="overline">x</span><sub>cs</sub></div>
</div>

Taking logs, sectoral export variation can be decomposed into variation in firm count and variation in average firm size. Freund and Pierola then show that variation in average firm size is largely driven by superstars:

<div class="formula-block">
  <div class="formula-line"><span class="text-term">average firm size variation</span> = <span class="text-term">superstar component</span> + <span class="text-term">non-superstar component</span></div>
</div>

### Main Findings

The headline finding is that the top 1 percent of exporters critically shape trade patterns. In their data, the top 1 percent account for about 53 percent of exports on average, the top 5 percent for nearly 80 percent, and the top 10 percent for almost 90 percent. Variation in average firm size explains over two-thirds of the variation in sectoral export shares across countries; variation in the number of firms explains the rest.

They also show that superstars drive sectoral specialization. The distribution of the number of firms across sectors is relatively similar across countries, but the distribution of export values differs because the largest firms are in different sectors. Dropping the top 1 percent of firms makes export structures across countries look more similar.

Superstars also matter for growth and diversification. They account for more than half of export growth and extensive-margin growth in their sample. New superstars tend to enter large and become top exporters quickly, often within less than three years. They are not usually tiny firms that slowly learn their way up over a long period.

That last point is important for the user's learning-effect intuition. Some export growth does involve learning, survival, and gradual market expansion, as in Evenett-Venables and Besedes-Prusa. But Freund and Pierola show a different mechanism: some dominant exporters are large almost immediately. If a country's export basket suddenly shifts toward a product, it may not be because many firms slowly learned that product. It may be because one large firm, multinational, resource project, or coordinated exporter entered at scale. Aggregate data can make both mechanisms look like "new product growth," so the repo needs diagnostics for jumps and top-cell dominance.

### What To Borrow For This Repo

Borrow the top-share discipline. Whenever the repo reports concentration, add top-product and top-cell shares. If one product-partner cell or one HS section explains much of a pattern, say so. This is the aggregate analogue of superstar dominance.

Borrow the caution that extensive-margin growth can be superstar-led. New product-partner cells may not mean broad-based diversification if they are created by a small number of large exporters. This matters for policy interpretation and for linking trade concentration to development.

Borrow the firm-size decomposition as an aspirational extension. If firm data become available, decompose sector exports into number of exporting firms and average exporter size, then split average size into top 1 percent and others. This would directly test whether repo concentration is broad or superstar-driven.

Borrow the comparative-advantage reinterpretation. In a representative-firm story, a country has a comparative advantage in a sector because many firms or the average firm are more productive there. In the superstar story, the country may look specialized because a few firms are exceptionally large in that sector. For this repo, that means product concentration could be a national capability signal, a top-firm signal, or both. The empirical write-up should avoid treating concentration as broad capability without evidence on firm breadth.

### Limits, Measurement Problems, And Cautions

Without firm IDs, this repo cannot directly identify superstars. Product concentration is not the same as firm concentration. A concentrated product could contain many firms, and a diversified product basket could be dominated by one multi-product firm.

The paper also focuses on non-oil exports, which is relevant because commodity sectors can create superstar-like concentration through deposits, state firms, or concessions. This repo already runs commodity-outlier checks in Exercise 11 by excluding oil/gas/gold/coal products. Similar commodity sensitivities should accompany any superstar-style aggregate proxy, because top-product concentration in commodities has a different interpretation from top-firm concentration in manufactures.

The paper's top 1 percent definition depends on the number of exporters. In small countries, the top 1 percent can be just a handful of firms. That makes confidentiality, outliers, and firm coding important.

Firm-level customs data can include intermediaries or trading companies, not only producers. The paper discusses this concern, and any future firm-level version of this repo would need to separate producers, traders, and multinationals where possible.

The repo's product-level exclusion rule still applies. `999999` is not a superstar product; it is a residual category.

### Concrete Next Empirical Moves

1. Add top-cell concentration diagnostics to Exercise 12: share of exports in top 1, top 5, top 10 product-partner cells by country-year.
2. Compare changes in product concentration with changes in top-cell concentration. If both move together, the pattern may be driven by a few large cells.
3. Identify abrupt jumps in product exports that create new top-10 products. These are candidates for superstar or large-project mechanisms.
4. If firm data are obtained, replicate the Freund-Pierola decomposition: sector export share variation into number of exporters and average exporter size.
5. For Exercise 11, test whether import products linked to export concentration are associated with top export products or broad export participation.

### Reading Notes / What To Remember

Freund and Pierola is the "top firms drive trade" paper. For this repo, it means aggregate product concentration should not be interpreted as broad national specialization until firm concentration has been considered.

## 10. Fieler And Eaton 2025: Quality, Unit Values, Extensive Margins, And Welfare

### Why This Paper Matters For My Project

Fieler and Eaton is the advanced layer. It combines product extensive margins, quantities, unit values, quality, and welfare in a general-equilibrium model. It is not the first paper to use for Exercise 12 accounting, but it is important if the project later moves from value decompositions to unit-value or welfare interpretation.

The current repo mostly works with trade values and concentration. That is enough for descriptive transition accounting, but it cannot tell whether export growth reflects more physical quantity, higher prices, higher quality, or changed composition inside product codes. Fieler and Eaton gives a framework for thinking about those margins together without abandoning standard gravity and gains-from-trade logic.

### Big Question And Intuition

The Feynman-style version is: two countries can export the same HS6 product, but one sells a cheap version and another sells an expensive high-quality version. A rich buyer may also choose higher-quality versions of the same product. If we only look at trade values, we mix quantity and quality. Fieler and Eaton ask how to build a model where product range, quantity, unit value, quality, and welfare all fit together.

The misconception they correct is that the product extensive margin and unit-value/quality margin have to be studied separately from standard gravity. They show a way to include both while preserving a standard aggregate gravity structure.

### Data And Unit Of Observation

The paper uses bilateral trade flows and unit values from Comtrade, focusing on HS6 products. It studies importer-exporter-product observations with both value and physical quantity where available. The unit is importer-exporter-HS6 product, with unit value calculated as value divided by quantity.

For this repo, this is directly relevant if quantity data are added. The current project should not jump to the full model, but it can borrow the measurement discipline: unit values are informative, but they require careful cleaning and interpretation.

### Core Decomposition Or Model Logic

The framework separates bilateral trade into an extensive margin of products and an intensive margin. The intensive margin is then split into quantity and unit-value margins:

<div class="formula-block">
  <div class="formula-line"><span class="text-term">trade value</span> = <span class="text-term">product extensive margin</span> <span class="op">&times;</span> <span class="text-term">quantity margin</span> <span class="op">&times;</span> <span class="text-term">unit-value margin</span></div>
</div>

The model interprets unit values through two quality dimensions. One dimension is closer to vertical quality valued more by richer buyers; another is closer to horizontal quality or effective quantity related to the seller's productivity and inputs. The key practical point is that higher unit values can reflect quality, but they are not raw proof of quality without a model and controls.

### Main Findings

The paper shows that unit values rise with both importer and exporter per capita income. Richer exporters sell higher-unit-value versions of products, and richer importers buy higher-unit-value versions. The model captures this pattern and also captures how the product extensive margin rises with importer and exporter size.

A major contribution is that the model retains standard gravity relationships for aggregate trade flows and standard gains-from-trade formulas while adding quality and product extensive margins. That makes it a frontier paper connecting detailed margins to welfare.

The paper also emphasizes the aggregation issue: HS6 products are still bundles of many varieties. The model treats HS6 products as collections of underlying varieties, which is exactly the problem faced in this repo when interpreting product counts and unit values.

### What To Borrow For This Repo

Borrow the value-quantity-unit-value ladder. If the repo adds quantities, do not stop at export values. For continuing products and product-partner cells, decompose value growth into quantity growth and unit-value growth. Then interpret unit-value growth as a candidate quality signal subject to robustness checks.

Borrow the buyer/seller income logic. If unit values are added, regress unit values on exporter income, importer income, distance, product fixed effects, exporter-product fixed effects, and importer-product fixed effects where possible. This will help separate quality from product mix and partner composition.

Borrow the welfare caution. The repo's current concentration results are descriptive. Higher concentration can be associated with welfare gains or losses depending on quality, prices, variety, and terms of trade. Fieler and Eaton is useful later, but it should not be used to overstate welfare implications from current value-only results.

### Limits, Measurement Problems, And Cautions

Unit values are noisy. Quantity units vary across products, reporting can be missing or inconsistent, and value divided by quantity can generate extreme outliers. Any unit-value analysis must clean units, winsorize or trim outliers, and check product-specific unit types.

Quality is model-inferred. Higher unit values may reflect quality, but also markups, transport costs, small shipments, composition, exchange rates, or reporting error. The project should call them unit values unless a quality model or strong controls justify quality language.

The paper is general-equilibrium and welfare-oriented. The current repo's Exercise 11 and Exercise 12 outputs are descriptive empirical artifacts. Use Fieler and Eaton to plan future work, not to reinterpret current value decompositions as welfare results.

The HS6 `999999` exclusion remains necessary for product-level work. A residual product code with missing or mixed quantities would be especially dangerous in unit-value analysis.

### Concrete Next Empirical Moves

1. Audit whether the raw data have reliable quantity fields for exports by HS6 and partner. Record missingness by product, country, year, and unit type.
2. For continuing product-partner cells, decompose value growth into quantity and unit-value components where quantities are reliable.
3. Produce unit-value outlier diagnostics by HS6, excluding `999999`, and flag products with inconsistent quantity units.
4. Estimate descriptive unit-value regressions with product fixed effects and exporter/importer income variables.
5. Compare concentration results in values versus quantities for products with reliable quantity data. If value concentration rises but quantity concentration does not, quality/unit-value changes may be part of the story.
6. Keep welfare claims out of the current write-up unless a model-based welfare exercise is explicitly added.

### Reading Notes / What To Remember

Fieler and Eaton is the "values are not enough" paper. It belongs at the end of the reading path because it adds quality and welfare after the product, partner, cell, survival, and firm mechanisms are clear. For the current repo, borrow its measurement discipline, not its full welfare machinery yet.

## Country Size, Entry, And Survival: How The New Result Fits

The country-size result should be positioned as a mechanism test within the extensive-margin literature, not as a new stand-alone claim about fixed costs. Hummels and Klenow provide the level benchmark: larger economies export more partly because they are active in a wider range of product categories and destination-product relationships. Helpman, Melitz, and Rubinstein, and Chaney provide the fixed-cost gravity logic: reductions in trade frictions can turn previously inactive relationships into positive trade flows. Evenett and Venables, Brenton and Newfarmer, and the development-diversification literature then separate product entry from market entry. Besedes and Prusa add the crucial warning that entry is not success unless relationships survive and deepen.

Read through that literature, the post-2001 common-universe test gives a more specific interpretation than the simple phrase "larger countries benefited more from lower fixed costs." If that were the main channel, larger countries should have lower concentration and higher post-2001 new-product or new-partner shares. The export results do not show that. New value shares and new active shares are lower for larger countries. The export-product size effect also survives when the calculation is restricted to products already present before 2002, which points to reallocation among established products rather than new product entry. For export partners, the size effect is stronger when the old pre-2002 partner universe is retained and exited partners are assigned zero, which points to retention of established partner networks.

The cleaner statement for Professor Panagariya is therefore:

> The post-2001 evidence does not primarily support a story in which larger countries diversified because they added more new products or partners. Smaller economies appear to show more extensive-margin adjustment and churn, while larger economies remain less concentrated because they retain broader pre-existing product and partner networks and reallocate value more evenly within them.

This framing preserves the Hummels-Klenow insight that size is associated with broader trade scope, while using Besedes-Prusa to avoid treating gross entry as durable diversification. It also keeps the claim descriptive. The current test does not identify a causal fixed-cost shock; it distinguishes entry, exit, and reallocation channels conditional on the observed post-2001 panel.

## Cross-Paper Project Map

| Project object | Best starting papers | How to use them in this repo |
|---|---|---|
| Product margin | Hummels-Klenow; Kehoe-Ruhl; Cadot-Carrere-Strauss-Kahn | Decompose export growth into product scope and value per product; handle least-traded goods; study diversification/reconcentration over development. |
| Partner margin | Evenett-Venables; Brenton-Newfarmer; Eaton-Kortum-Kramarz | Separate new destinations from new products; add market size, region, and destination popularity. |
| Product-partner cell | Kehoe-Ruhl; Evenett-Venables; Brenton-Newfarmer; Besedes-Prusa | Treat cells as export relationships; distinguish entry from survival and scaling. |
| Survival/churn | Besedes-Prusa; Brenton-Newfarmer | Build spells, hazards, gross positive growth, gross contraction, and deepening of survivors. |
| Country size and post-2001 concentration | Hummels-Klenow; Helpman-Melitz-Rubinstein; Chaney; Evenett-Venables; Besedes-Prusa | Separate the size-level fact from the mechanism: entry, retention, and intensive-margin reallocation imply different interpretations. |
| Development-stage reconcentration | Cadot-Carrere-Strauss-Kahn; Bernard-Redding-Schott | Test whether closures are old-cone, mismatched, peripheral, or core-competence reallocations. |
| Firm concentration | Eaton-Kortum-Kramarz; Bernard-Redding-Schott; Freund-Pierola | Interpret aggregate cells through firm entry, multi-product scope, and superstars. |
| Quality/unit values | Hummels-Klenow; Fieler-Eaton | Separate value, quantity, and unit-value margins when data permit; avoid casual quality claims. |
| Exercise 11 | Hummels-Klenow; Bernard-Redding-Schott; Freund-Pierola; Fieler-Eaton | Interpret import-export linkages cautiously; product links may be broader production-chain or firm mechanisms, not exact HS6 causality. |
| Exercise 12 | All papers, especially Kehoe-Ruhl, Evenett-Venables, Brenton-Newfarmer, Besedes-Prusa | Turn transition accounting into entry, recombination, survival, scaling, and concentration diagnostics. |

## Immediate Empirical Checklist

1. For all product and product-partner work, exclude HS6 `999999` before aggregation.
2. Split Exercise 12 new product-partner cells into new product, new partner, both new, and recombined existing product-existing partner sets.
3. Add least-traded goods diagnostics to distinguish true zeros from low-base growth.
4. Build product and product-partner survival curves with gap-tolerant robustness.
5. Extend the Section 16 diagnostic over time and compare benchmark, no-Section-16, and coarser-aggregation concentration measures.
6. Add top-cell and top-product concentration diagnostics as aggregate proxies for superstar mechanisms.
7. Treat Exercise 11 coefficients as descriptive. The negative product-Gini linkage results and conditional-logit convergence warning should not be narrated as causal evidence.
8. If quantity data are added, call the output unit-value evidence until a quality model justifies stronger language.
