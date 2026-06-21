# Economist Council: Corridor-Selection Model For Trade Concentration

Generated: 2026-05-29

## Council Setup

- Question: Can a components-plus-heterogeneous-firms model explain the Panagariya-Bagaria concentration puzzle across products, partners, and product-source/product-destination cells, and would such a model be novel?
- Assumptions: The model must match the current `rd2_countries` facts: high product and cell concentration above random benchmarks; large new product and product-partner-cell growth shares; tiny new-partner contribution; persistent top import suppliers; mostly economy-specific rather than globally dominant import-source concentration; and weak broad HS6/HS2 import-export linkage.
- Council seats: Trade and Spatial Economist, Industrial Organization Skeptic, Theory/Mechanism Voice, Identification Hawk, Econometrician, Macro-General-Equilibrium Skeptic, Institutions and Political Economy Voice, Writing and Positioning Editor.

## Round 1: Opening Positions

**Trade and Spatial Economist.** The strongest version is not a literal three-country model. It is a many-source, many-destination model with one highlighted triad: an assembler country, a component-source country, and a final-demand country. Gravity and fixed market access must enter destination choice; otherwise partner concentration will be left unexplained. The product-partner-cell result is the central fact: new partners barely matter, but new product-destination combinations do. That points to recombination within an existing market-access network.

**Industrial Organization Skeptic.** The model must not assume concentration by putting a Pareto distribution everywhere and then declaring victory. It needs a precise mechanism: firm-product capability, fixed product costs, fixed destination costs, and fixed or sunk supplier-relationship costs. Concentration should arise because a few firm-product-destination-source combinations have positive surplus at scale. The model is most credible if it predicts both concentration and the failure of the broad import-product linkage test.

**Theory/Mechanism Voice.** The cleanest structure is a monopolistic-competition model with heterogeneous firms and product-specific capability. Firms choose product scope, destination scope, and input-source scope. Imported inputs lower marginal costs through an input price index, but source relationships require fixed costs. The central proposition should be a threshold result: only high `phi_f * a_fj` firms serve high-fixed-cost cells, and only sufficiently productive or input-intensive firms pay for foreign sources.

**Identification Hawk.** The model is useful only if it disciplines empirical tests. The current Exercise 11 evidence weakens a broad claim that import Product Gini reflects export input dependence. The model should therefore predict a difference between broad product concentration and corridor-specific input exposure. If every result can be rationalized after the fact by changing fixed costs, the model is too flexible.

**Econometrician.** Match moments, not anecdotes. Proposed moments: Gini by product, partner, and cell; top supplier persistence; economy-specific source share; new-product, new-partner, and new-cell growth shares; and coefficients from import-concentration/export-linkage regressions. The model should also state where HS6 measurement breaks the theory: input components and final outputs usually do not share the same code.

**Macro-General-Equilibrium Skeptic.** A partial-equilibrium firm model can explain micro selection, but concentration is an aggregate object. Prices, wages, and demand matter. A full GE version can wait, but the static model should at least state which objects are taken as given: country wages, destination expenditure, source input productivity, and trade costs. Without that, the model risks confusing demand lumps with production mechanisms.

**Institutions and Political Economy Voice.** Economy-specific source concentration is not only technology. It can reflect standards, procurement rules, trade agreements, sanctions, state-owned firms, financing, and long-term buyer-supplier trust. The model should include a reduced-form relationship cost or policy wedge, but the write-up must admit that this wedge bundles institutions and firm networks. This gives the model an India/policy extension later.

**Writing and Positioning Editor.** The contribution should be phrased as "from components to corridors." Do not say "components explain trade concentration." Say: broad component stories are too coarse; the model explains why concentration appears in scalable product-destination-source corridors, while broad import Product Gini can fail to map to exports. That is a sharper and more defensible novelty claim.

## Round 2: Cross-Examination

**Trade and Spatial Economist -> Theory Voice.** If there are only three countries, there is no meaningful partner concentration. The formal model can use a three-country example, but the paper needs an `N`-source and `D`-destination environment.

**Industrial Organization Skeptic -> Writing Editor.** "Corridors" sounds good, but it must be defined: a corridor is a high-value country-product-partner or country-product-source relationship, not a metaphor.

**Identification Hawk -> Industrial Organization Skeptic.** If source fixed costs are unobserved, how do we distinguish fixed-cost sourcing from unobserved source quality? The model should yield separate predictions: persistence and scale-through-incumbents support relationship costs; global dominance supports source productivity; economy-specific dominance supports relationship or policy wedges.

**Econometrician -> Trade and Spatial Economist.** Gravity should enter both export destinations and import sources. Otherwise source concentration could be mistaken for supplier ecosystems when it is just distance, regional integration, or tariff preferences.

**Macro-GE Skeptic -> Everyone.** Product concentration may come from demand lumps, especially energy, vehicles, electronics, pharma, and capital goods. The model must have a non-export-linked import-demand term, or it will contradict the repo's own negative Exercise 11 findings.

**Institutions Voice -> Econometrician.** Do not treat policy and institutions as residual noise. If economy-specific sourcing is large, it is likely shaped by standards, agreements, or strategic procurement. This should become a second-stage empirical extension.

**Writing Editor -> Identification Hawk.** The paper should lead with facts that rule out weak stories. The model then explains the pattern left standing: not random sparsity, not pure components, not pure global dominant suppliers, but corridor selection.

## What Would Change Minds

- A direct test showing IO-weighted or product-source-specific imported-input concentration predicts export-sector growth, while broad Product Gini does not.
- A top-source persistence decomposition that separates global source dominance from importer-specific relationship persistence.
- A gravity residualization showing economy-specific source concentration remains after distance, GDP, regional agreement, and tariff controls.
- A product-partner-cell survival exercise showing new cells are not only noisy one-year flows.
- Firm or customs microdata showing top export products are the core products of value-dominant firms and that those firms rely on sticky import-source relationships.
- A model simulation showing the same parameter set can match the signs of Exercise 11, Exercise 12, and Exercise 13 moments without hand-tuning each fact separately.

## Council Verdict

- Strongest version of the idea: A corridor-selection model in which heterogeneous firms choose products, destinations, and input-source relationships under fixed costs. Concentration arises because only a small set of firm-product-destination-source combinations scale.
- Main threat: The model can become too flexible if every pattern is assigned to an unobserved fixed cost or match shock.
- Best next test: Re-estimate the input mechanism at the corridor level: source concentration and imported-input exposure by IO/HS2 sector, not broad product Gini.
- What to drop or de-emphasize: Drop the claim that components broadly explain import concentration. De-emphasize exact HS6 import-export matches as the decisive test of input dependence.
- What to read or verify next: Antras, Fort, and Tintelnot for source-set choice; Eaton, Kortum, and Kramarz plus Helpman, Melitz, and Rubinstein for destination selection; Bernard, Redding, and Schott for multi-product scope; Johnson and Noguera for production-sharing measurement; Panagariya and Bagaria for the concentration puzzle.

## Redesign Incorporated

The revised model should:

1. Use many possible source and destination countries, with a three-country triad as the exposition device.
2. Define a corridor as a country-product-partner or country-product-source cell with positive value.
3. Include four fixed costs: product, destination, product-destination, and source-relationship.
4. Include input-output mapping from component products to final products, so imported inputs need not match exported final HS6 codes.
5. Include a domestic/final-demand import component, so broad import Product Gini can be high even when export linkage is weak.
6. Deliver testable comparative statics for product concentration, partner concentration, source persistence, new-cell growth, and the failure of broad import-product linkage.

## Round 3: Review Of The Developed Model

**Trade and Spatial Economist.** The revised model now has the right geography: many sources and destinations with a highlighted assembler-source-demand triad. Keep the formal title away from "three-country model" unless the text immediately clarifies that the triad is expositional.

**Theory/Mechanism Voice.** The cutoff algebra is now strong enough for a theory section. The key result is that imported-input access shifts the export cutoff through `P_Mj`, with an elasticity scaled by `alpha_j(sigma_j - 1)`. That gives a clean reason to test input intensity heterogeneity.

**Identification Hawk.** The two-product example is doing important work. It prevents the paper from overclaiming that imports and exports must line up at HS6. The empirical design should now make a sharp contrast: broad Product Gini is a placebo-like object, while IO-weighted source-corridor exposure is the model object.

**Industrial Organization Skeptic.** The source-relationship rule is credible because it depends on revenue scale, input intensity, and source price reductions. The paper should not estimate all of these as free latent parameters. Use the model to motivate a small number of moments and reject weak versions.

**Econometrician.** The model implies a validation table with three panels: concentration moments, extensive-margin moments, and linkage moments. The toy simulation should remain labelled as a sanity check rather than evidence.

**Macro-General-Equilibrium Skeptic.** Partial equilibrium is acceptable for the first paper because the empirical facts are concentration and entry facts, not welfare. Any welfare or counterfactual tariff claims require a GE extension with wages and expenditure.

**Writing and Positioning Editor.** The best contribution language is: "We move from a components explanation to a corridor-selection explanation." The novelty is not a new building block. It is the joint object and the discipline from facts that rule out simpler stories.

## Final Council Recommendation

Develop the paper around a **corridor-selection model** with three margins:

```text
firm-product capability
product-destination access
component-source relationships
```

The model is novel enough if the paper proves and tests the joint claim: trade concentration persists because scalable corridors survive the product, destination, and source thresholds at the same time. The model is not novel enough if it is sold only as "heterogeneous firms plus imported inputs."
