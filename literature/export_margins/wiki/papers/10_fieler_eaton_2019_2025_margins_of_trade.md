---
title: "The Margins of Trade"
authors: "Ana Cecilia Fieler; Jonathan Eaton"
year: "2025"
source_pdf: "10_fieler_eaton_2019_2025_margins_of_trade.pdf"
---

## Abstract

We introduce quality differentiation and an extensive margin of products into a standard quantitative, general equilibrium model of international trade. Both the quality and the quantity of a product play a role in its contribution both to consumption and to production. The framework allows bilateral trade to vary at the extensive and intensive margins and the intensive margin of trade to vary at the quantity and unit-value margins. We estimate the parameters of the model using bilateral data on trade flows and on unit values in trade. The model captures (i) the welldocumented increasing relation between unit values and both importer and exporter per capita income and (ii) how the extensive margin rises with importer and exporter size. But, unlike other contributions to the literature confronting these margins in international trade, our framework delivers a standard gravity formulation for trade flows and standard measures of the gains from trade apply. Jonathan Eaton Department of Economics Pennsylvania State University 303 Kern Graduate Building University Park, PA 16801 and NBER jxe22@psu.edu Ana Cecília Fieler Yale University Department of Economics 27 Hillhouse Ave New Haven, CT 06511 and NBER ana.fieler@yale.edu A data appendix is available at http://www.nber.org/data-appendix/w26124

---

NBER WORKING PAPER SERIES


THE MARGINS OF TRADE


Jonathan Eaton

Ana Cecília Fieler


Working Paper 26124
http://www.nber.org/papers/w26124


NATIONAL BUREAU OF ECONOMIC RESEARCH

1050 Massachusetts Avenue

Cambridge, MA 02138
July 2019


We thank Sam Kortum, Eduardo Morales, and David Weinstein for extremely valuable
suggestions. We also benefited from helpful comments at various presentations. Eaton gratefully
acknowledges support from the National Science Foundation under Grant Number 1426267. The
views expressed herein are those of the authors and do not necessarily reflect the views of the
National Bureau of Economic Research.


NBER working papers are circulated for discussion and comment purposes. They have not been
peer-reviewed or been subject to the review by the NBER Board of Directors that accompanies
official NBER publications.


to exceed two paragraphs, may be quoted without explicit permission provided that full credit,
including © notice, is given to the source.


The Margins of Trade
Jonathan Eaton and Ana Cecília Fieler

NBER Working Paper No. 26124
July 2019
JEL No. F11,F14


**ABSTRACT**


We introduce quality differentiation and an extensive margin of products into a standard
quantitative, general equilibrium model of international trade. Both the quality and the quantity of
a product play a role in its contribution both to consumption and to production. The framework
allows bilateral trade to vary at the extensive and intensive margins and the intensive margin of
trade to vary at the quantity and unit-value margins. We estimate the parameters of the model
using bilateral data on trade flows and on unit values in trade. The model captures (i) the welldocumented increasing relation between unit values and both importer and exporter per capita
income and (ii) how the extensive margin rises with importer and exporter size. But, unlike other
contributions to the literature confronting these margins in international trade, our framework
delivers a standard gravity formulation for trade flows and standard measures of the gains from
trade apply.


Jonathan Eaton

Department of Economics
Pennsylvania State University
303 Kern Graduate Building
University Park, PA 16801
and NBER

jxe22@psu.edu


Ana Cecília Fieler

Yale University
Department of Economics
27 Hillhouse Ave

New Haven, CT 06511
and NBER

ana.fieler@yale.edu


A data appendix is available at http://www.nber.org/data-appendix/w26124


# **1 Introduction**

Quantitative work in international trade has advanced on several fronts in the last two

decades. One line of research has developed global general equilibrium models to understand the determinants of bilateral trade flows and their implications for welfare. [1] Another

literature has delved into trade data to ask how total bilateral exports decompose into var
ious margins, such as that between number of products (the extensive margin) and sales
per product (the intensive margin), and how sales per product decompose into quantity
and unit value. [2] These studies have revealed several robust and intriguing regularities.

While both lines of research have been extremely fruitful, they remain somewhat at

odds with each other. Capturing a complex world with a general equilibrium system

has required assumptions inconsistent with richer countries paying more for the same

product and richer countries charging more for the same product, two of the most robust

regularities to emerge from this second line of inquiry. Incorporating how trade volumes

break down into their extensive and intensive margins has also proved challenging for

general equilibrium modeling.

This paper seeks to reconcile these two research fronts by developing a general equilib
rium framework consistent with observed regularities in the margins of trade. The model

delivers the same aggregate relationships governing bilateral trade that emerge in a stan
dard general equilibrium framework, in particular the Ricardian formulation of Eaton

and Kortum (2002) (henceforth EK), with a continuum of varieties, CES aggregation,

and perfect competition. Hence, at the level of total spending, our model delivers the

same observations as EK’s.

In line with previous work, we associate differences in unit values of a variety with
differences in its quality. [3] We allow for two dimensions of quality, which we call vertical

and horizontal. Horizontal quality substitutes perfectly for quantity, and is valued equally

by all users of the variety, whether a household using the variety for final consumption

or a producer using the variety as an intermediate input. Vertical quality complements

quantity. As a buyer chooses to spend more on a variety, the increased spending is divided

between more effective quantity and higher vertical quality. The framework implies that


1 Early examples are Anderson and Van Wincoop (2003), using an Armington approach, Eaton and
Kortum (2002), whose approach is Ricardian, and quantitative papers building on Melitz (2003), such as
Chaney (2008) and Eaton et al. (2011).
2 Early contributions here are by Hummels and Klenow (2005), which we build on very directly, Schott
(2004), and Hallak (2006).
3 Aside from Hummels and Klenow (2005) and Hallak (2006), other authors making this connection
are Schott (2004), Khandelwal (2010), Hallak (2010), Hallak and Schott (2011), Baldwin and Harrigan
(2011), Hummels and Skiba (2004), Choi et al. (2009), Bekkers et al. (2012), and Atrianfar (2019).


a higher wage is associated with higher quality in both dimensions.

First, a final consumer receiving a higher wage chooses to spend more on any variety,

and this higher spending divides into both a larger physical amount and a higher vertical

quality. A producer having to pay a higher wage seeks to equip her worker with more

intermediates. As she spends more on each variety of intermediate she also will seek both

more quantity and quality. Our model thus predicts that a buyer in a higher wage country

will spend more per unit and buy more units both for intermediate and for final uses.

Second, we posit that a better equipped worker produces higher horizontal quality.

Hence our model implies that vertical quality rises with the wage of the buyer while

horizontal quality rises with the wage of the seller. Our model captures these relationships

very parsimoniously with two parameters that relate closely to the observed elasticities

of unit value with respect to importer and to exporter per capita income.

A standard observation is that the ranges of products a country imports and exports

grows with its overall size. But the relationship between the extensive margin and GDP

is a nonlinear one. In particular, it dies out with importer size at quite a small level. Our
framework captures these features by introducing stochastic minimum shipping sizes. [4]


We estimate the parameters of the model using data on trade flows, product varieties,

unit values, and country characteristics. We then simulate the model to show how it

can deliver decompositions of trade into the margins identified by Hummels and Klenow

(2005) (henceforth HK).

Our conceptual framework applies to a range of situations beyond international trade.

It has implications, for example, for quantifying the role of quality improvement in eco
nomic growth. In this paper we choose a trade context in order to exploit the United

Nations COMTRADE data. COMTRADE reports annual bilateral trade between most

countries, in terms of both value and physical quantity, using a harmonized and detailed

product classification. It thus provides unique insight into how countries across all sizes

and income levels are producing (as exporters) and absorbing (as importers) a vast array

of products. We know of no other dataset that delivers such a thorough picture.

Our framework builds on the theoretical literature on quality differentiation in inter
national trade. Early on, Flam and Helpman (1987) developed a two-country, two-good

general equilibrium framework that explained why a rich country might both produce

and demand a good of higher quality. More recently Fajgelbaum et al. (2011) provided a

much richer framework that allowed for many goods and countries.

Applying these approaches to the problem at hand poses two challenges. These models


4 Here we build on Armenter and Koren (2014), who introduce granularity into a model of international
trade.


employ a discrete-choice framework in which the buyer is contemplating buying only a

single unit of the good. They thus don’t allow for increased per capita spending on a good

to reflect a combination of more quantity and higher quality. Second, with only a single

dimension of quality, if rich countries both prefer higher quality goods and are better

at making them, rich countries should have larger market shares in other rich countries

than in poor ones, and vice versa. This pattern isn’t one we observe in the data. Our

framework can deal with each issue.

Other investigators have pursued different general equilibrium approaches to under
standing the role of unit values in trade. In contrast to what we do here, these alternatives

depart from perfect competition in various directions.

Feenstra and Romalis (2014) build on the Melitz (2003) model. Their framework

is less in keeping with standard general equilibrium modeling in that they introduce

a specific trade cost as well as the iceberg costs commonly used in the literature. It

consequently doesn’t deliver the standard homothetic gravity specification for aggregate

trade implied by our approach here. While Feenstra and Romalis (2014)’s framework

provides an explanation for why unit values rise with importer per capita GDP it doesn’t

speak to the effect of exporter per capita GDP.

Atrianfar (2019) incorporates quality as well as price competition into a model of
Bertrand competition, building on Bernard et al. (2003). An intriguing implication of his

analysis is that rich and poor countries compete in different dimensions. His framework

can explain why a low-wage country might respond to increased competition from a third

party (e.g., China) by lowering price and maintaining market share, while a high-wage

country might respond by raising quality and price, allowing market share to fall. These

rich interactions preclude his framework from delivering the standard gravity specification

implied by the approach we take here.

These two papers, like ours and much of the other literature, interpret higher unit

values to reflect higher quality. Another explanation is that variation in unit values repre
sent different markups. Lashkaripour (2019b) develops a general equilibrium multicountry
version of the Krugman (1979) model in which different classes of goods have different

elasticities of substitution, so their producers charge different Dixit-Stiglitz markups. This

framework can also explain some of the empirical regularities we address here. Again the

approach maps less directly than ours into the standard gravity specification.

We also build on a large literature on the intensive and extensive margins of trade. The

distinction goes back at least to Vernon (1966)’s product cycle model and the literature
that followed. More recent contributions are Evenett and Venables (2002), Besedeˇs and
Prusa (2006) (for U.S. imports), Besedeˇs and Prusa (2011) (for exports), Amiti and Freund


(2010) (for Chinese exports), Debaere and Mostashari (2010) (looking at the effect of
tariffs on the two margins), Kehoe and Ruhl (2013) (looking at the role of the extensive
margin in growth), Baier et al. (2014) (looking at the effect of economic integration on
the two margins), and Silva et al. (2014) (who consider the role of the two margins for
gravity estimation).

We proceed as follows. Section 2 presents our data and revisits the empirical regular
ities pursued before. Section 3 presents our model and Section 4 our estimation of it. In

Section 5 we evaluate our model’s ability to capture the margins of trade. We pursue our

analysis in Sections 2 through 5 at the level of aggregate merchandise trade. In Section

6 we probe the extent to which our results survive disaggregation into finer classes of

products. Section 7 concludes.

# **2 Overview of the Data**


Our analysis applies to overall merchandise trade and its decomposition into various mar
gins. Our trade data are from the United Nations COMTRADE data set. We work with

the most disaggregated product category in these data, which is HS6. We refer to an

HS6 product category as a product. We restrict our analysis to trade among the fifty

largest countries in terms of GDP in the 2007 cross section. We ignore small countries

to avoid zero bilateral trade flows and to ensure sufficient overlap in HS6 products across
importer-exporter pairs. [5] We take data on GDP and population from the World De
velopment Indicators and data on geographical characteristics from CEPII. Appendix A
provides a list of the countries and further detail on the construction of our data set. [6]


We follow HK in decomposing the total value _X_ _ni_ of exports to each destination _n_ from

each source _i_ into an extensive, a quantity, and a price margin. We define the extensive

margin _E_ _ni_ as the fraction of HS6 products that _n_ imports from _i_ . We construct the price

margin _P_ _ni_ as


log _P_ _ni_ =
_|K_ _ni_ _|_


� [log( _p_ _nik_ ) _−_ log( _p_ world _,k_ )]

_k∈K_ _ni_


where _K_ _ni_ is the set of HS6 products _n_ imports from _i_, _p_ _nik_ is the unit value of product

_k_ imported by _n_ from _i_, and _p_ world _,k_ is the average unit value of product _k_ across all


5 Among these 50 countries COMTRADE reports total merchandise trade of US $11.1 trillion consisting
of 3,239,484 importer-exporter-HS6 triads. For various reasons described in Appendix A, we pare these
data down to to 2,611,700 triads constituting US $9.62 trillion.
6 CEPII provides a very user friendly version of the COMTRADE data which, among other things,
reconciles potentially conflicting reports from importing and exporting countries. Because of concerns
that CEPII’s procedures for processing the data might influence some of the regularities we explore here,
we decided to use the raw data downloaded directly from the COMTRADE website.


Table 1: Decomposition of trade flows


extensive

dependent variable _→_ value margin quantity price

**Panel A**

exporter GDP 1.16 0.76 0.36 0.04
importer GDP 1.11 0.34 0.73 0.05
distance -0.81 -0.43 -0.39 0.02


**Panel B**

exporter GDP per capita 1.18 0.84 0.19 0.15
exporter population 1.15 0.71 0.46 -0.02
importer GDP per capita 1.10 0.41 0.56 0.13
importer population 1.12 0.30 0.82 0.00
distance -0.81 -0.37 -0.53 0.10


number of observations 2448 2448 2448 2448


All variables are in logs. We report standard errors in Appendix B.


importer-exporter pairs in our sample. [7] We define the quantity margin as the residual
_X_ _ni_ _/_ ( _E_ _ni_ _P_ _ni_ ). [8]


Following HK we apply a standard gravity analysis to relate our margins of trade to

geographical indicators and to importer and exporter characteristics. Table 1 reports the

results. The first column of Panel A shows the coefficients of the regression of total exports

to each destination from each source against distance and importer and exporter GDP.

The subsequent three columns repeat the regression for each of the three margins. By

construction, for each independent variable, the coefficients on these last three columns

sum to the coefficient in the first column.

The results in the first column of Panel A are consistent with standard gravity results:

The coefficients on importer and exporter GDP are around one and the distance elasticity


7 We construct unit values from the COMTRADE data by dividing, for each importer-exporter-HS6
triad, the reported value by the reported quantity. Values are always in terms of current U.S. dollars.
The absence of quantity data forces us to drop a small number of observations. Of the remaining ones,
eighty percent of the triads report quantities in terms of weight (corresponding to 72 percent of the total
value of trade in our analysis). The remaining ones are nearly all in terms of counts. See Appendix A
for details. Lashkaripour (2019a) provides an analysis of alternative quantity measures in trade data.
8 These definitions differ from HK, who use a weighted definition of the extensive margin and construct the price margin using the price index introduced by Sato (1976) and Vartia (1976) and discussed
extensively by Feenstra (1994). Appendix B reports results using their methodology. Our definition of
the extensive margin is simpler, and the correlation with their measure is 0.93. The correlation between
our price index and theirs is weaker, 0.76. But the simpler, unweighted price index is more tightly linked
to our product-level analysis below.


is around minus one. How GDP relates to the extensive margin, however, differs between

importer and exporter. Larger countries export many more products than smaller coun
tries, but they don’t import so many more. At this level of aggregation, the intensive

_×_
margin (price quantity) is almost all dominated by quantity.

Panel B repeats the analysis breaking GDP down into GDP per capita and population.

The first column of Panel B shows that breaking down GDP into GDP per capita and

population has no significant effect on trade values: The elasticity with respect to income

per capita and population is close to one for both importer and exporter. But for both

importers and exporters, the elasticity of the extensive margin is greater for GDP per

capita than for population, but the population effect is not far from the elasticity with

respect to total GDP. For the price margin, however, both importer and exporter GDP
per capita have distinctly positive elasticities, while population does not. [9]

## **2.1 Price Relationships**


To probe further into the price margin of trade, we turn from the bilateral price index

to prices at the level of individual HS6 product categories. The aggregate results on the

elasticity of price with respect to exporter GDP per capita in the bottom panel of Table 1,

for example, could arise from selection. Say, for example, that countries charge the same

price to all destinations for a given product. The results in Table 1 could still arise if rich

countries sell their more expensive products disproportionately to rich destinations and

their relatively cheaper products to poor destinations. Table 2 shows that forces other

than selection are at work.

In Column (1), we report the results from a regression of unit values, for each importer
exporter-product triad, against distance, importer GDP per capita, and exporter-product

fixed effects. The coefficient on importer per capita income is 0.12, nearly as large as

in Table 1. The implication is that individual exporters sell the same product to richer

countries at systematically higher prices.

Column (2) reports the mirror regression of unit values against distance, exporter GDP

per capita, and importer-product fixed effects. The coefficient on exporter per capita GDP

is 0.22, even larger than in Table 1. Countries systematically pay higher prices for the
same products from richer countries. [10]


9 Note that distance has a positive effect on unit value which becomes large and significant once GDP
is broken down into GDP per capita and population, the Alchian-Allen effect analysed by Hummels and
Skiba (2004).
10 Schott (2004) reports similar results for imports into the United States at the level of 10-digit product
categories.


Column (3) reports what happens if we use only product fixed effects with both ex
porter and importer per capita income. The coefficients on these variables do not change

from columns (1) and (2).
Column (4) includes a term that interacts exporter and importer GDP per capita.

The coefficient is negative and statistically insignificant. Hence we find no evidence that

rich countries disproportionately pay more for goods from other rich countries.

Columns (5) and (6) consider the sensitivity of the results in column (3) to the set
of products we consider. In column (5) we restrict the sample to products classified
by Rauch (1999) as differentiated (using his liberal definition of referenced price and
organized exchange products). In column (6) we look only at manufactures. In neither

case are the results notably different.

Going back to Flam and Helpman (1987), the literature on quality and trade has

provided an explanation for why unit values rise with both exporter and importer per

capita income: Rich countries have a comparative advantage in producing high quality,

and hence charge higher prices, and, because of nonhomotheticity in preferences, rich
countries have a greater taste for quality, so pay higher prices. [11]


The assumption that rich countries have a comparative advantage in high quality

implies that, as long as quality is one dimensional, there should be no overlap in the prices

charged for a given product by a rich country and a poor country. Even if Japan sells to

Pakistan at a lower price than it sells to Norway, the price it charges in Pakistan should

still exceed the price Malaysia charges in Norway. Otherwise, why would Norwegians

prefer the high-priced Malaysian product to the low-priced product that Japan is selling

in Pakistan?

A back-of-the-envelope calculation based on the regression coefficients in Column (3)

of Table 2 suggests, however, systematic overlap in predicted prices. We calculate, for

example, that a Malaysian product should sell in Norway at 0.3 log points more than a

Japanese product in Pakistan.

Overlaps aren’t just what’s predicted by the regression. They are common in the raw

data. Figure 1 illustrates price patterns for HS6 categories HS871493 and HS845011. Code

HS871493 corresponds to hubs for motorcycles, bicycles, and vehicles for the disabled.
Code HS845011 corresponds to washing machines with capacity less than 10kg. [12] The

figures plot unit values against importer per capita income for all importer-exporter pairs.

For hubs, we highlight the three major Asian exporters: China (GDP per capita US$2,708)
with a square, Malaysia (GDP per capita US$11,358) with a triangle, and Japan (GDP per


11 Subsequent papers in this tradition are Stokey (1991) and Fajgelbaum et al. (2011).
12 See hts.usitc.gov for a more complete definition.


(a) HS871493 (b) HS845011


Figure 1: Examples of Products


capita US$34,313) with a circle. Across destinations, Japan’s unit values are higher than

Malaysia’s, which are higher than China’s. For all three exporters, unit values rise with

the importer’s GDP per capita so much that Japan is selling in the poorest destination

at a price lower than China sells in the richest destination.

For washing machines, Figure 1(b) highlights the two largest exporters, China with
squares and Germany with triangles (GDP per capita US$40,324). Note how China sells
to the richest country, Norway (GDP per capita US$82,480), at a price above that at
which Germany sells to the poorest country, Pakistan (GDP per capita US$879).

## **2.2 Trade Values**


The literature on quality and trade discussed above also has implications for trade values

between countries of different income levels. In these models, rich countries tend to sell

to rich households in all countries while poor countries tend to sell to poor households in

all countries. Since poorer countries have a larger share of poor households, exports from

rich countries to poor would systematically decline with differences in income. At the

extreme, in Flam and Helpman’s model, internal income inequality is the only reason for

international trade. Fajgelbaum et al. (2011), by introducing an idiosyncratic component

to demand, relax this strong prediction, but their model nevertheless predicts that the

average consumer in a poor country has lower demand for goods produced in rich countries.

The large coefficient on exporter per capita income in the price regression implies, through

the lens of this literature, a strong degree of specialization in income elastic quality on

the part of rich countries.

Figure 2 shows the limited scope for internal income inequality to generate substantial


Figure 2: World Income Distribution


trade between rich and poor countries. The figure plots, for 149 countries, GDP per

capita at the top and bottom deciles (on the y-axis) against average GDP per capita (on
the x-axis). [13] Note how cross-country differences in GDP per capita swamp internal ones.

The poorest decile in the United States is slightly richer than the richest in India. An

implication of the literature on quality in trade is that the only buyers of U.S. goods in

India are the narrow sliver of Indians with incomes high enough to appreciate goods that

appeal to U.S. consumers.

But do rich countries lose market share as their importing partner’s GDP per capita

declines? Table 3 reports the result of a gravity regression of total bilateral trade value

against importer and exporter fixed effects, distance, and an interaction term between

exporter and importer GDP per capita. A positive coefficient on the interaction term

would confirm, in line with the Linder (1961) hypothesis, that rich countries do indeed

have a larger client base in other rich countries. The coefficient is in fact small and
statistically insignificant. [14]


13 The data are from the World Bank’s World Development Indicators. GDP per capita is from 2007.
Income per capita at the top and bottom deciles is calculated from the share of income at these deciles
for the closest year to 2007 within a 10-year window.
14 Hallak (2010) reports the same result looking at aggregate bilateral trade. He argues that the aggregate data mask a positive interaction effect at the sectoral level, showing that the effect is significantly
positive in half of 116 sectors and significantly the opposite in only 20 percent of them. We classified our
data into 97 two-digit HS product categories, performing the regression in Table 3 separately for each
category. In contrast to Hallak, we find a significantly positive interaction effect for only 19 categories
and a significantly negative interaction for 33 categories. Running these sectoral regressions as well as


Table 3: Gravity with Interaction


**Dependent variable is the log of bilateral trade flows**


distance -1.148
(0.041)


interaction 0.0020
(0.016)


importer fixed effect yes
exporter fixed effect yes
R-squared 0.75
number of observations 2,448


Notes: Distance is in logs. As in table 2, the interaction term equals log (importer GDP per capita) _×_
log (exporter GDP per capita). It captures whether rich countries disproportionately sell more to other
rich countries.

## **2.3 The Extensive Margin**


To probe further into the extensive margin of trade, Figure 3 plots the fraction of HS6

product categories that a country imports (a) and the fraction that it exports (b) against
total GDP (both in logs). Confirming the results from Table 1 above, the extensive margin

varies much more for exporters than for importers, hence the very different scales for the

two y-axes. Not revealed by the regression is the concave relation between the extensive

margin of exports and exporter GDP: For the largest countries, the relationship between

GDP and extensive margin levels off, both for imports and for exports.

Before turning to our model, it’s useful to review what standard models say about

the extensive margin of trade for imports and exports. The EK model provides a simple

framework for breaking trade values down into the measure of varieties and spending per

variety that one country sells to another.

A stark implication of their model is that, for a given destination, all the variation in

imports across sources is at the extensive margin. If we interpret varieties in their model

as products in the data, then the coefficient on the extensive margin of exporters would

equal the coefficient on value in Table 1. In fact, the coefficient is 0.76, substantially


the aggregate one above using pseudo Poisson maximum likelihood (PPML), as in Silva and Tenreyro
(2006), or pseudo multinomial maximum likelihood (PMML), as in Eaton et al. (2013), yields similar
results.


(a) Importer (b) Exporter


Figure 3: Extensive Margin and GDP


less than the coefficient on value, 1.16. A modeling challenge, then, is to account for the
intensive margin of 0.38. [15]


Another implication of the EK model is that the extensive margin of importers for

varieties should be negative: Larger importers should source a greater range of varieties

domestically, so import fewer. Again, interpreting varieties in their model as products in

the data poses a challenge in explaining the _positive_ importer extensive margin elasticity

of 0.34 in Table 1. [16]


As panel B of Table 1 shows, the coefficients on GDP per capita and population aren’t

very different from each other, either for exporters or importers, in both the value and
extensive margin regressions. [17] This result is in line with both the EK and Melitz models,

for which this breakdown doesn’t matter.

# **3 The Model**


Having reviewed regularities in the data that pose challenges for standard trade models,

we now turn to a framework that seeks to accommodate these regularities. To explain


15 The Melitz model breaks trade down into the **firm** dimension of export participation, and sales per
firm. If we equate a firm in his model with a product in the data, it, too, predicts that all the action
across exporters in a given destination is at the extensive margin.
16 The Melitz model does predict that larger markets will attract more firms from a given source. An
issue with equating a Melitz firm with an HS6 product is that we see many countries exporting the same
HS6 product.
17 Appendix B shows formally that we cannot reject the null that these coefficients are equal in all four
cases. This result is in contrast with the role of GDP per capita and population on prices and quantities,
for which this null of equality is clearly rejected.


why unit values rise with both importer and exporter per capita income the framework

incorporates two dimensions of quality: One captures the difference in the unit values of

different exporters across importers reflected in the vertical differences in Figure 1. The

other captures the difference in unit values in what is purchased by different importers,

reflected in the slopes in Figure 1. In our framework both dimensions of quality rise

endogenously with a country’s productivity. To explain the interplay of the extensive and

intensive margins, the framework introduces granularity in shipments.

Our model begins with basic Ricardian ingredients. The world has _N_ countries, in
dexed by _i, n_ = 1 _, ..., N_, each endowed with a measure _L_ _i_ of workers who are also the

households in the economy. A worker can perform different jobs within a country but

can’t change countries. A worker in country _i_ earns a wage _w_ _i_ determined in equilibrium.

Competition is perfect, so that unit production costs determine prices in all markets.

Output consists of a measure one continuum Ωof varieties each denoted by _ω_ . A unit

of variety _ω_ has two dimensions of quality: One dimension _q_ ( _ω_ ) _∈_ [0 _, ∞_ ) complements
quantity _y_ ( _ω_ ) _∈_ [0 _, ∞_ ) while the other _Q_ ( _ω_ ) _∈_ [0 _, ∞_ ) perfectly substitutes for quantity.

Examples of the first dimension of quality might be Robert Parker’s rating of a wine or

the precision of a machine tool. Examples of the second dimension might be the heating

value of a ton of coal, the durability of a light bulb, or the caffeine content of a cup of

coffee. The same product might differ in both dimensions. For the washing machines,

aspects of _Q_ might be the durability or reliability of the machine, while aspects of _q_

might be gentleness to clothing, cycle options, electronic controls, or an automatic bleach

dispenser.

While the term has been used differently in different contexts, we refer to _Q_ as “hor
izontal quality” since, as we show below, all buyers value an increase in _Q_ equivalently,

and to _q_ as “vertical quality”, since a buyer spending more values an increase in _q_ dispro
portionately. Nevertheless, all buyers value an increase in either _Q_ or _q_ .

## **3.1 Aggregation**


We now turn to how individual varieties aggregate into the composite output. To simplify

notation we temporarily ignore the international dimension of the problem and suppress

country subscripts.

Varieties combine to form a composite in amount _Y_ according to the function:


_Y_ = _u_ ( _ω_ ) _[β]_ _dω_ (1)


where the variety-specific benefit is:


_u_ ( _ω_ ) = [( _Q_ ( _ω_ ) _y_ ( _ω_ )) _[ρ]_ + _q_ ( _ω_ ) _[ρ]_ ] [1] _[/ρ]_ _._ (2)


Here _β ≤_ 1 governs the elasticity of substitution between varieties while _ρ ≤_ 1 governs the

elasticity of substitution between effective quantity and the vertical dimension of quality.

This composite provides utility to a final consumer or equips an individual worker with

intermediates. These two dimensions of quality allow us to capture features of the price

data discussed in Section 2.1.

The cost of producing _y_ ( _w_ ) physical units of vertical quality _q_ ( _ω_ ) of variety _ω_ is


_x_ ( _ω_ ) = _y_ ( _ω_ ) _q_ ( _ω_ ) _[γ]_ _c_ ( _ω_ ) _._ (3)


Here _γ >_ 0 is a parameter reflecting the cost of producing higher vertical quality and

_c_ ( _ω_ ) _>_ 0 is the cost of creating one unit of variety _ω_ of vertical quality _q_ ( _ω_ ) = 1, which
is determined in equilibrium. [18] An agent with a budget _X_ seeks to maximize (1) subject

to:


_x_ ( _ω_ ) _dω_ = _X._ (4)

� _ω∈_ Ω


We split the problem into two parts. We first ask, for a particular variety _ω_ with given

horizontal quality _Q_ ( _ω_ ) _,_ how to choose _q_ ( _w_ ) and _y_ ( _w_ ) maximize the benefit _u_ ( _ω_ ) given
spending _x_ ( _ω_ ) on this variety. We then ask how the buyer should allocate his budget _X_
across spending on each variety _x_ ( _ω_ ) subject to the budget constraint (4).


**3.1.1** **Quality versus quantity**


Since we first focus on a given variety, we temporarily drop the _ω_ argument. If the buyer

has chosen to spend _x_ on this variety, the problem is:


max
_y,q_ [[(] _[Qy]_ [)] _[ρ]_ [ +] _[ q]_ _[ρ]_ []] [1] _[/ρ]_


subject to:

_yq_ _[γ]_ _c ≤_ _x._


18 See Bekkers et al. (2012) for a very similar formulation of preferences and the cost of what we’re
calling vertical quality, the only dimension of quality in their analysis.


To satisfy the second-order conditions for a minimum we need to impose the condition
that _ρ <_ 0 _._ [19] Taking the ratio of the two first-order conditions gives:


_q_ = _γ_ [1] _[/ρ]_ _Qy,_


which, upon substitution into the problem above, reduces it to:


max
_y_ [(1 +] _[ γ]_ [)] [1] _[/ρ]_ _[Qy]_


subject to:
_y_ [1+] _[γ]_ _Q_ _[γ]_ _c ≤_ _x._


Defining the term:
_A_ = _γ_ _[γ/]_ [[] _[ρ]_ [(1+] _[γ]_ [)]]


the implied quantity is:


_y_ = _A_ _[−]_ [1] [ �] _[x]_

_c_


� _Q_ _[−][γ/]_ [(1+] _[γ]_ [)]


with corresponding vertical quality:


_q_ = _A_ [1] _[/γ]_

_c_

�


_._
�


The price per unit is then:


and the benefit is:


_p_ = _cq_ _[γ]_ = _Ac_

_c_

�


� _γ/_ (1+ _γ_ )


_u_ = _A_ _[−]_ [1] (1 + _γ_ ) [1] _[/ρ]_

_c_

�


� 1 _/_ (1+ _γ_ )


Instead of working with the unit cost _c_ of vertical quality _q_ = 1 we introduce:


_v_ = _[Q]_

_c_ _[,]_


19 Graphically, the budget constraint:
_x ≥_ _yq_ _[γ]_ _c_


has a surface that’s Cobb-Douglas in _q_ and _y._ For a tangency to represent a minimum requires that the
isobenefit curve:
_u_ ¯ = [( _Qy_ ) _[ρ]_ + _q_ _[ρ]_ ] [1] _[/ρ]_


have an elasticity of substitution strictly below 1 _._


the effective inverse cost of variety _ω_ . We can then write these expressions more compactly

as functions of _x_ and _v_ :


_y_ ( _x, v_ ) = _A_ _[−]_ [1] _Q_ _[−]_ [1] ( _xv_ ) [1] _[/]_ [(1+] _[γ]_ [)]

_q_ ( _x, v_ ) = _A_ [1] _[/γ]_ ( _xv_ ) [1] _[/]_ [(1+] _[γ]_ [)]


_p_ ( _x, v_ ) = _Ax_ _[γ/]_ [(1+] _[γ]_ [)] _v_ _[−]_ [1] _[/]_ [(1+] _[γ]_ [)] _Q_

_u_ ( _x, v_ ) = _A_ _[−]_ [1] (1 + _γ_ ) [1] _[/ρ]_ ( _xv_ ) [1] _[/]_ [(1+] _[γ]_ [)] _._ (5)


The parameter _γ_ governs how spending _x_ gets divided into the quantity and price margins,

with quantity having an elasticity 1 _/_ (1 + _γ_ ) and price an elasticity _γ/_ (1 + _γ_ ).


**3.1.2** **How much of a variety?**


Having solved for the benefit _u_ [ _x_ ( _ω_ ) _, v_ ( _ω_ )] of spending an amount _x_ ( _ω_ ) on variety _ω_ we

turn to the problem of how much to spend on each variety. Specifically, we solve the

problem:


max
_x_ ( _ω_ )


_u_ [ _x_ ( _ω_ ) _, v_ ( _ω_ )] _[β]_ _dω_


where, from the fourth equation of (5):


_u_ [ _x_ ( _ω_ ) _, v_ ( _ω_ )] = _A_ _[−]_ [1] (1 + _γ_ ) [1] _[/ρ]_ [ _x_ ( _ω_ ) _v_ ( _ω_ )] [1] _[/]_ [(1+] _[γ]_ [)]


subject to (4).

The solution gives us:


_v_ ( _ω_ )
_x_ ( _ω_ ) =


_−_
_β/_ (1+ _γ_ _β_ )
_X_ (6)
�


_−_
(1+ _γ_ _β_ ) _/β_

_V_ = _v_ ( _ω_ _[′]_ ) _[β/]_ [(1+] _[γ][−][β]_ [)] _dω_ _[′]_ _._ (7)
�� _ω_ _[′]_ _∈_ Ω �


From (6) and its substitution into (5), we can write:


_y_ ( _ω_ ) = _A_ _[−]_ [1] _v_ ( _ω_ ) [1] _[/]_ [(1+] _[γ][−][β]_ [)] [ �] _XV_ _[−][β/]_ [(1+] _[γ][−][β]_ [)] [�] [1] _[/]_ [(1+] _[γ]_ [)] _Q_ ( _ω_ ) _[−]_ [1]

_q_ ( _ω_ ) = _A_ [1] _[/γ]_ _v_ ( _ω_ ) [1] _[/]_ [(1+] _[γ][−][β]_ [)] [ �] _XV_ _[−][β/]_ [(1+] _[γ][−][β]_ [)] [�] [1] _[/]_ [(1+] _[γ]_ [)]

_p_ ( _ω_ ) = _Av_ ( _ω_ ) _[−]_ [(1] _[−][β]_ [)] _[/]_ [(1+] _[γ][−][β]_ [)] [ �] _XV_ _[−][β/]_ [(1+] _[γ][−][β]_ [)] [�] _[γ/]_ [(1+] _[γ]_ [)] _Q_ ( _ω_ )

_u_ ( _ω_ ) = _A_ _[−]_ [1] (1 + _γ_ ) [1] _[/ρ]_ _v_ ( _ω_ ) [1] _[/]_ [(1+] _[γ][−][β]_ [)] [ �] _XV_ _[−][β/]_ [(1+] _[γ][−][β]_ [)] [�] [1] _[/]_ [(1+] _[γ]_ [)] (8)


where we continue to take horizontal quality _Q_ ( _ω_ ) as given.


We can then solve for _Y_ as a function of _X_ and _V_ :


_Y_ = _u_ ( _ω_ ) _[β]_ _dω_


= _A_ _[−]_ [1] (1 + _γ_ ) [1] _[/ρ]_ [ �] _XV_ _[−][β/]_ [(1+] _[γ][−][β]_ [)] [�] [1] _[/]_ [(1+] _[γ]_ [)] [ ��] _v_ ( _ω_ ) _[β/]_ [(1+] _[γ][−][β]_ [)] _dω_

_ω∈_ Ω �


= _A_ _[−]_ [1] (1 + _γ_ ) [1] _[/ρ]_ ( _XV_ ) [1] _[/]_ [(1+] _[γ]_ [)] (9)


To obtain a closed-form solution, we have to take a stand on the distributions of the

inverse unit costs _v_ ( _ω_ ).


**3.1.3** **The distribution of efficiency**


We now make our multicountry setting explicit by denoting a destination country by _n_

and an origin country by _i_ . We assume that vertical quality _Q_ ( _ω_ ), determined below,
depends only on origin. Thus, if country _n_ buys variety _ω_ from country _i, Q_ ( _ω_ ) = _Q_ _i_ . As

in EK, if country _n_ buys variety _ω_ from country _i_ then


_c_ ( _ω_ ) = _[d]_ _[ni]_ _[C]_ _[i]_

_Z_ _i_ ( _ω_ )


where _C_ _i_ is the unit cost of a bundle of inputs in country _i_, _d_ _ni_ is the iceberg cost of

shipping a unit from country _i_ to country _n_, and _Z_ _i_ ( _ω_ ) is country _i_ ’s efficiency producing
variety _ω_ . The probability that country _i_ ’s efficiency _Z_ _i_ ( _ω_ ) _≤_ _z_ is


_F_ _i_ ( _z_ ) = exp( _−T_ _i_ _z_ _[−][θ]_ ) _._


with the _Z_ _i_ ( _ω_ ) drawn independently across source countries _i_ for each variety _ω_ .

We define

˜
_C_ _i_ = _[C]_ _[i]_ _,_ (10)

_Q_ _i_


the cost of inputs in source _i_ adjusted for source _i_ ’s horizontal quality. Then we can write

effective inverse cost in destination _n_, taking into account iceberg transport costs:


_v_ _ni_ ( _ω_ ) = _[Z]_ _[i]_ [(] _[ω]_ [)] _._

_d_ _ni_ _C_ [˜] _i_


An agent in country _n_ sources variety _ω_ from country _i_ if


_i_ = arg max
_i_ _[′]_ =1 _,...,N_ _[{][v]_ _[ni]_ _[′]_ [(] _[ω]_ [)] _[}][ .]_


The corresponding effective inverse cost is


_v_ _n_ ( _ω_ ) = max
_i_ _[′]_ =1 _,...,N_ _[{][v]_ _[ni]_ _[′]_ [(] _[ω]_ [)] _[}][ .]_


Using the distribution of _z_, the share of varieties that country _n_ sources from country _i_ is


_π_ _ni_ = _[T]_ _[i]_ [(] _[d]_ _[ni]_ [ ˜] _[C]_ _[i]_ [)] _[−][θ]_ (11)

Φ _n_


Φ _n_ = � _T_ _i_ _′_ ( _d_ _ni_ _′_ _C_ [˜] _i_ _′_ ) _[−][θ]_ _n_ = 1 _, ..., N._ (12)


_i_ _[′]_


The distribution of _v_ _ni_ ( _ω_ ) conditional on _i_ being the lowest cost supplier to country _n_

is


_G_ _n_ ( _v_ ) = Pr _V_ _ni_ _≤_ _v| i_ = arg max
� _k≤N_ _[{][v]_ _[ni]_ _[}]_ �

= exp( _−_ Φ _n_ _v_ _[−][θ]_ ) _._ (13)


As in EK, the distribution _G_ _n_ is independent of source _i_ . Hence the unconditional dis
tribution _v_ _n_ ( _ω_ ) in equation (7) has the same cumulative distribution _G_ _n_ ( _v_ ), so that _π_ _ni_
given in (11) is also country _i_ ’s share in absorption by _n_ . Despite the nonhomothetic intri
cacies introduced by the quality dimensions of our model, it delivers the same trade-share

equation as the homothetic EK model.

We can use (13) to solve:


(1+ _γ−β_ ) _/β_ _∞_
_v_ _n_ ( _ω_ ) _[β/]_ [(1+] _[γ][−][β]_ [)] _dω_ =
_ω∈_ Ω � �� 0


_V_ _n_ =
��


_∞_ (1+ _γ−β_ ) _/β_

_v_ _[β/]_ [(1+] _[γ][−][β]_ [)] _dG_ _n_ ( _v_ ) = Γ 0 Φ [1] _n_ _[/θ]_ _[,]_
0 �


(14)

which corresponds to the inverse of the price index in EK. Here:


_β_
Γ 0 = Γ 1 _−_
� � _θ_ (1 + _γ −_ _β_ )


_−_
�� (1+ _γ_ _β_ ) _/β_


and Γ is the gamma function. For reasons similar to those in EK and Melitz, for the price

index to be well-defined we require that:


_β_
_θ >_
1 + _γ −_ _β_ _[.]_


We can rearrange (9) to solve for the expenditure _X_ _n_ required to achieve an aggregate _Y_ :


_Y_ [1+] _[γ]_
_X_ _n_ ( _Y_ ) = Γ 1 (15)

_V_ _n_


Γ 1 = � _γ_ _[γ]_ (1 + _γ_ ) _[−]_ [(1+] _[γ]_ [)] [�] [1] _[/ρ]_ _._


We introduce the term:

_ϵ_ ( _ω_ ) = _v_ _n_ ( _ω_ ) _/V_ _n_ (16)


which has the distribution:


_J_ ( _ϵ_ ) _≡_ Pr[ _E ≤_ _ϵ_ ] = Pr[ _v_ _n_ ( _ω_ ) _≤_ _ϵV_ _n_ ]


= exp � _−_ ( _ϵ_ Γ 0 ) _[−][θ]_ [�] (17)


independent of both _n_ and _i_ . By introducing _ϵ_ we can now write (6) and (8) in terms of

features _X_ _n_ and _V_ _n_ of the importer _n_, feature _Q_ _i_ of the exporter _i_, and the realization of

_ϵ_, which is our structural error:


_x_ _ni_ ( _ϵ_ ) = _X_ _n_ _ϵ_ _[β/]_ [(1+] _[γ][−][β]_ [)]

_y_ _ni_ ( _ϵ_ ) = _A_ _[−]_ [1] ( _V_ _n_ _X_ _n_ ) [1] _[/]_ [(1+] _[γ]_ [)] _Q_ _[−]_ _i_ [1] _[ϵ]_ [1] _[/]_ [(1+] _[γ][−][β]_ [)]

_q_ _ni_ ( _ϵ_ ) = _A_ [1] _[/γ]_ ( _V_ _n_ _X_ _n_ ) [1] _[/]_ [(1+] _[γ]_ [)] _ϵ_ [1] _[/]_ [(1+] _[γ][−][β]_ [)]

_p_ _ni_ ( _ϵ_ ) = _A_ ( _X_ _n_ ) _[γ/]_ [(1+] _[γ]_ [)] _V_ _n_ _[−]_ [1] _[/]_ [(1+] _[γ]_ [)] _Q_ _i_ _ϵ_ _[−]_ [(1] _[−][β]_ [)] _[/]_ [(1+] _[γ][−][β]_ [)]

_u_ _ni_ ( _ϵ_ ) = _A_ _[−]_ [1] (1 + _γ_ ) [1] _[/ρ]_ ( _V_ _n_ _X_ _n_ ) [1] _[/]_ [(1+] _[γ]_ [)] _ϵ_ [1] _[/]_ [(1+] _[γ][−][β]_ [)] _._ (18)


Since spending across varieties has to integrate to _X_ _n_, from the first line of (18), _ϵ_ _[β/]_ [(1+] _[γ][−][β]_ [)]


has mean one.

We now incorporate this demand system into both production with intermediates and

final consumption.

## **3.2 Production**


We start with the determination of production costs, _C_ [˜] _i_ in equation (10), and of horizon
tal quality _Q_ _i_ . Physical output is produced with a Cobb-Douglas combination of labor

and intermediates at constant returns to scale, with intermediates combining varieties

according to (1). The horizontal-quality adjusted output _o_ of a single worker equipped


with an amount _m_ of intermediates is


_o_ = _Qm_ [1] _[−][α]_ (19)


where 1 _−_ _α_ is the elasticity of output per worker with respect to intermediate inputs,

given _Q_, where _α ∈_ (0 _,_ 1).

A producer’s problem, then, can be stated as hiring labor in amount _l_ and inter
mediates per worker _m_ to minimize the cost of producing one unit of horizontal-quality

adjusted composite output. Dropping the country subscript _i_, the cost of hiring a worker

is the wage _w_ and the cost of equipping her is _X_ ( _m_ ), where the function _X_ is given in
equation (15). The producer’s problem is thus:


˜
_C_ = min _l,m_ _[{][l]_ [(] _[w]_ [ +] _[ X]_ [(] _[m]_ [))] _[}]_


subject to providing one efficiency unit of the composite output:


_Qlm_ [1] _[−][α]_ = 1 _._ (20)


We posit that the horizontal quality _Q_ a worker produces increases with the extent to

which she is equipped with intermediates according to:


_Q_ = _m_ _[ν]_ _,_ (21)


where _ν >_ 0 is a parameter relating intermediate use per worker to horizontal quality.
For concavity we require that _ν < α_ . [20] Substituting (21) into the constraint (20):


_lm_ [1] _[−][α]_ [+] _[ν]_ = 1 _._ (22)


As we show below, the share of labor in quality-adjusted production is:


˜ _[γ][ −]_ _[ν]_
_α_ = _[α]_ [ +]

1 + _γ_


20 Denoting effective output by _O_ we can write the quality-adjusted production function as:


_O_ = _QLm_ [1] _[−][α]_ = _Lm_ [1] _[−][α]_ [+] _[ν]_


and where _u_ ( _ω_ ) is given by (2).


_m_ = _u_ ( _ω_ ) _[β]_ _dω_


while the share of materials is:


1 _−_ _α_ ˜ = [1] _[ −]_ _[α]_ [ +] _[ ν]_

1 + _γ_


Whether the labor share in quality-adjusted production is larger or smaller than _α_ depends

on whether _γ_ exceeds or is exceeded by _ν/_ (1 _−_ _α_ ). In the first case the increased cost of

higher vertical quality intermediates dominates the effect of intermediates in enhancing

horizontal quality, and vice-versa. Our parameter estimates below put us in the range

where the second effect dominates the first, so that the labor share in quality-adjusted

production is less than _α_ .

Substituting _X_ ( _m_ ) from equation (15) and (22) into the objective function, the prob
lem becomes:
min _wl_ + [Γ] [1] _._
_l_ � _V_ _[l]_ _[−][α/]_ [˜] [(1] _[−][α]_ [˜][)] �


_wl_ + [Γ] [1]


[Γ] [1] _._

_V_ _[l]_ _[−][α/]_ [˜] [(1] _[−][α]_ [˜][)] �


The solution is:


_l_ = � 1 _−_ _α_ ˜ _[·]_ _wV_ [Γ] [1]


From the constraint _lm_ [1] _[−][α]_ [+] _[ν]_ = 1:


_m_ = _α_ ˜
�


_α_ ˜ _·_ _[wV]_ Γ


Γ 1


1 _−α_ ˜

_._
�


� 1 _/_ (1+ _γ_ )


(23)
�


so that horizontal quality is:


_Q_ = ˜

_α_

�


_α_ ˜ _·_ _[wV]_ Γ


Γ 1


which is increasing in _w_ and _V_ . From (15), spending on intermediates per worker is:


_m_ [1+] _[γ]_
_X_ ( _m_ ) = Γ 1

_V_

= ˜ _w._ (24)

_α_


The cost of producing an effective unit of the composite output is


˜
_C_ = _l_ ( _w_ + _X_ ( _m_ ))


˜ Γ 1
= _A_


1 _−α_ ˜
_w_ _[α]_ [˜] (25)
�


˜
_A_ = ˜ _α_ _[−][α]_ [˜] (1 _−_ _α_ ˜) _[−]_ [(1] _[−][α]_ [˜][)]


with labor share:
_lw_

˜ = ˜ _α_
_C_


and materials share:
_lX_ ( _m_ ) ˜

˜ = 1 _−_ _α._
_C_


We can insert _X_ ( _m_ ) from (24) and _Q_ from (23) into (18) to derive spending, quantity,

quality, price, and benefit of variety _ω_ when used as an intermediate in _n_ purchased from

_i_ :


_x_ _[M]_ _ni_ [(] _[ω]_ [)] = ˜

_α_

�


_ϵ_ ( _ω_ ) _[β/]_ [(1+] _[γ][−][β]_ [)] _w_ _n_ _L_ _n_
�


(1+ _ν_ ) _/_ (1+ _γ_ )
_ϵ_ ( _ω_ ) [1] _[/]_ [(1+] _[γ][−][β]_ [)] ( _V_ _n_ _w_ _n_ ) [1] _[/]_ [(1+] _[γ]_ [)] _L_ _n_
�


� _−ν/_ (1+ _γ_ )


_y_ _ni_ _[M]_ [(] _[ω]_ [)] = _A_ _[−]_ [1] ˜

_α_

�


_q_ _ni_ _[M]_ [(] _[ω]_ [)] = _A_ [1] _[/γ]_ ˜

_α_

�


_ϵ_ ( _ω_ ) [1] _[/]_ [(1+] _[γ][−][β]_ [)] ( _V_ _n_ _w_ _n_ ) [1] _[/]_ [(1+] _[γ]_ [)]
�


_p_ _[M]_ _ni_ [(] _[ω]_ [)] = _A_ ˜

_α_

�


( _γ−ν_ ) _/_ (1+ _γ_ )
_ϵ_ ( _ω_ ) _[−]_ [(1] _[−][β]_ [)] _[/]_ [(1+] _[γ][−][β]_ [)] _V_ _n_ _[−]_ [1] _[/]_ [(1+] _[γ]_ [)] _w_ _n_ _[γ/]_ [(1+] _[γ]_ [)]
�


� _ν/_ (1+ _γ_ )


_u_ _[M]_ _ni_ [(] _[ω]_ [)] = _A_ _[−]_ [1] (1 + _γ_ ) [1] _[/ρ]_ ˜

_α_

�


_ϵ_ ( _ω_ ) [1] _[/]_ [(1+] _[γ][−][β]_ [)] ( _V_ _n_ _w_ _n_ ) [1] _[/]_ [(1+] _[γ]_ [)] (26)
�


Note that source _i_ matters only for quantity and unit value.

## **3.3 Consumption**


Total income in country _n_ is _w_ _n_ _L_ _n_ _._ Since we assume balanced trade and income equality

within countries, spending per worker is _X_ _n_ = _w_ _n_ _._ Household utility is given by (1).
We can then use (18) to get expressions, for variety _ω_ sourced from _i_, of total household

spending, total quantity demanded, vertical quality, unit value, and benefit in destination


_n_ :


_x_ _[C]_ _ni_ [(] _[ω]_ [)] = _ϵ_ ( _ω_ ) _[β/]_ [(1+] _[γ][−][β]_ [)] _w_ _n_ _L_ _n_


� _−ν/_ (1+ _γ_ )


_y_ _ni_ _[C]_ [(] _[ω]_ [)] = _A_ _[−]_ [1] ˜

_α_

�


_ϵ_ ( _ω_ ) [1] _[/]_ [(1+] _[γ][−][β]_ [)] ( _V_ _n_ _w_ _n_ ) [1] _[/]_ [(1+] _[γ]_ [)] _L_ _n_
�


_q_ _ni_ _[C]_ [(] _[ω]_ [)] = _A_ [1] _[/γ]_ _ϵ_ ( _ω_ ) [1] _[/]_ [(1+] _[γ][−][β]_ [)] ( _V_ _n_ _w_ _n_ ) [1] _[/]_ [(1+] _[γ]_ [)]


_p_ _[C]_ _ni_ [(] _[ω]_ [)] = _A_ ˜

_α_

�


_−ν/_ (1+ _γ_ )
_ϵ_ ( _ω_ ) _[−]_ [(1] _[−][β]_ [)] _[/]_ [(1+] _[γ][−][β]_ [)] _V_ _n_ _[−]_ [1] _[/]_ [(1+] _[γ]_ [)] _w_ _n_ _[γ/]_ [(1+] _[γ]_ [)]
�


� _ν/_ (1+ _γ_ )


_u_ _[C]_ _ni_ [(] _[ω]_ [)] = _A_ _[−]_ [1] (1 + _γ_ ) [1] _[/ρ]_ _ϵ_ ( _ω_ ) [1] _[/]_ [(1+] _[γ][−][β]_ [)] ( _V_ _n_ _w_ _n_ ) [1] _[/]_ [(1+] _[γ]_ [)] (27)


Note again that source _i_ matters only for quantity and unit value.

## **3.4 Unit Values in Bilateral Trade**


Since our data don’t distinguish between imports for final and for intermediate use, we

define the value, quantity, and unit value of a variety as


_x_ _ni_ ( _ω_ ) = _x_ _[C]_ _ni_ [(] _[ω]_ [) +] _[ x]_ _[M]_ _ni_ [(] _[ω]_ [)]


_y_ _ni_ ( _ω_ ) = _y_ _ni_ _[C]_ [(] _[ω]_ [) +] _[ y]_ _ni_ _[M]_ [(] _[ω]_ [)]

_p_ _ni_ ( _ω_ ) = _[x]_ _[ni]_ [(] _[ω]_ [)]

_y_ _ni_ ( _ω_ ) _[.]_


From equations in (26) and (27) we can write the value as:


_x_ _ni_ ( _ω_ ) = [1] ˜ (28)

_α_ _[w]_ _[n]_ _[L]_ _[n]_ _[ϵ]_ [(] _[ω]_ [)] _[β/]_ [(1+] _[γ][−][β]_ [)]


and the unit value as


_p_ _ni_ ( _ω_ ) = Γ 2 _w_ _n_ _[δ]_ _[w,M]_ Φ _[δ]_ _n_ [Φ] _[,M]_ _w_ _iδ_ _w,X_ Φ _δi_ Φ _,X_ _ϵ_ ( _ω_ ) _[−]_ [(1] _[−][β]_ [)] _[/]_ [(1+] _[γ][−][β]_ [)] (29)


_γ_
_δ_ _w,M_ = 1 + _γ_ _[,]_

_δ_ Φ _,M_ = _−_
_θ_ (1 + _γ_ ) _[,]_


_ν_
_δ_ _w,X_ = 1 + _γ_ _[,]_


_ν_
_δ_ Φ _,X_ = (30)
_θ_ (1 + _γ_ ) _[,]_


Γ 2 = Γ [(] 0 _[ν][−]_ [1)] _[/]_ [(1+] _[γ]_ [)] _α_ ˜ 1 + ((1 _−_ _α_ ˜) _/α_ ˜) [1] _[/]_ [(1+] _[γ]_ [)] [��] _[−]_ [1] [ �] _α_ ˜˜
� � (1 _−_ _α_ )Γ 1


_A,_
�


and where we have used (14) to replace _V_ with Φ. The model thus implies that the unit
value varies with (i) the importer wage with an elasticity _δ_ _w,M_, (ii) the importer Φ with
an elasticity _δ_ Φ _,M_, (iii) the exporter wage with an elasticity _δ_ _w,X_, and (iv) the exporter Φ

with an elasticity _δ_ Φ _,X_ . Buyers in a destination with a high wage or a high price index
(low Φ) pay more because they demand higher vertical quality and because competition
is less intense (allowing on average a higher-priced variety to compete). Producers in
a source with a high wage or low price index (high Φ) equip their workers with more

intermediates, so produce goods with higher horizontal quality.

Expression (29) provides the basis of how we use our model to connect data on unit

values in bilateral trade to importer and exporter characteristics reflecting their wages

and price indices. Before quantifying the model we show what it says about the gains

from trade.

## **3.5 The Gains from Trade**


We can use expressions (14) and (15) to get an expression for the aggregate bundle that
a worker in country _n_ can achieve with a wage _w_ _n_ and price index Φ _n_ _[−]_ [1] _[/θ]_ :


Γ 0 _w_ _n_
_Y_ _n_ = � Γ 1 _·_ Φ _[−]_ _n_ [1] _[/θ]_


_._
(31)
�


A monotonic transformation gives us an expression for the worker’s utility _U_ _n_ that’s linear

in the wage:


_w_ _n_

_U_ _n_ = [Γ] [0] _·_ _._ (32)

Γ 1 Φ _[−]_ _n_ [1] _[/θ]_


We can substitute equation (11), with _i_ = _n_, into (32), using (25), to get:


1 _/αθ_ ˜
(33)
�


Γ 0
_U_ _n_ = � _A_ ˜Γ 1


Γ 0
_U_ _n_ = � _A_ ˜Γ


˜
1 _/α_ _−θ_

_·_ _T_ _n_ _d_ _nn_
� � _π_ _nn_


which is the standard ACR formula (Arkolakis et al. (2012)), taking into account inter
mediates and domestic trade costs. The elasticity of real income with respect to the home

˜
share is _−_ 1 _/αθ_ .


# **4 Quantification**

We estimate the Φ’s from bilateral trade flows as we describe in Section 4.1. In Section

4.2 we use our estimates of the Φ’s to estimate the parameters _γ_, _ν_, and _θ_ . In Section

4.3 we use product level prices and volumes to estimate the parameter _β_ which governs

the distribution of the structural error _ϵ_ . We turn to how we model and quantify the

extensive margin in 4.4.

## **4.1 Trade Flows and Multilateral Resistance**


We estimate the Φ’s exploiting equation (11) using data on trade flows, GDP, and distance.

We parameterize the effect of iceberg costs on trade share as


_d_ _[−]_ _ni_ _[θ]_ [=] _[ δ]_ [0] _[dist]_ _ni_ _[δ]_ _[g]_ (34)


for _i ̸_ = _n,_ where _dist_ _ni_ is the distance between _i_ and _n_ . Here _δ_ [0] is a constant and _δ_ _[g]_


is a parameter that relates trade share to distance, taking into account both the effect

of distance on trade costs and the role of _θ_ in relating trade costs to trade share. We

estimate the _d_ _nn_ individually as country fixed effects.

We construct trade shares as:
_π_ _ni_ = _[X]_ _[ni]_

_X_ _n_

for _i ̸_ = _n_ and:


_̸_


_X_ _n_ _−_ [�] _̸_
_π_ _nn_ =


_i_ _[′]_ = _̸_ _n_ _[X]_ _[ni]_ _[′]_


_̸_

_X_ _n_ _,_


_̸_


where _X_ _n_ is country _n_ ’s total absorption. [21] For all _i ̸_ = _n_, we regress:


_̸_


_π_ _ni_
log
� _π_ _nn_


_̸_


= _A_ _n_ + _B_ _i_ + _δ_ _[g]_ log _dist_ _ni_ + _ε_ _[X]_ _ni_ _[,]_ (35)
�


_̸_


where _A_ _n_ is an importer fixed effect, _B_ _i_ is an exporter fixed effect, and _ε_ _[X]_ _ni_ [is the residual.] [22]

Equivalent to Waugh (2010), and in contrast to EK, we attribute country-level differences
in openness to differences in internal trade costs ( _d_ _nn_ ). Under this interpretation, equation


21 Our absorption measure is:

_X_ _n_ = _[GDP]_ ˜ _[n]_ + _D_ _n_ _,_

_α_


where _GDP_ _n_ is country _n_ ’s GDP (corresponding to _w_ _n_ _L_ _n_ in our model) and _D_ _n_ is country _n_ ’s trade
deficit. While we’ve assumed balanced trade elsewhere our trade share measures takes deficits into
account. The term ˜ _α_, set equal to 0.5 for all countries, is to account for intermediate demand.
22 The discussion in Anderson and Van Wincoop (2004) on assumptions on the residual term holds here.


(11) implies that fixed effects correspond to:


_A_ _n_ = _−_ log _T_ _n_ _C_ [˜] _n_ _[−][θ]_ _−_ log( _d_ _[−]_ _nn_ _[θ]_ [)]
� �

_B_ _i_ = log _T_ _i_ _C_ [˜] _i_ _[−][θ]_ _._
� �


A consistent estimate of Φ _n_ is then


ˆ
ˆΦ _n_ = exp( _−A_ _n_ ) + � exp( _B_ [ˆ] _i_ + _δ_ [ˆ] _[g]_ log _dist_ _ni_ ) _,_ (36)


_i_ = _̸_ _n_


where ˆ _x_ denotes the estimate of _x._

## **4.2 Unit Values**


We think of a variety _ω_ in our model as a very finely defined product. If a variety in

our model corresponded to 6-digit HS categories in the data, our model would incorrectly

predict that, for any product, an importer would buy from only one source. We reconcile

this discrepancy between theory and data by thinking of a 6-digit product category in

the COMTRADE data as corresponding to a finite set of varieties _ω_ in our model, with

varieties within a product measured in the same units.

Taking logs of equation (29), for each product category _k_ :


log _p_ _nik_ = _δ_ _k_ + _δ_ _w,M_ log _w_ _n_ + _δ_ Φ _,M_ log Φ _n_ + _δ_ _w,X_ log _w_ _i_ + _δ_ Φ _,X_ log Φ _i_ + _ε_ _[P]_ _nik_ _[.]_ (37)


Here the product fixed effect _δ_ _k_ incorporates Γ 2 and accounts for the units in which product
_k_ is measured and _ε_ _[P]_ _nik_ [is a residual.] [23] [ We use per capita GDP to measure importer and]

exporter wages _w_ .

The top panel of Table 4 shows the results of estimating equation (37). Column (1)

reports the simple OLS estimates. The estimates satisfy the model’s restrictions, from

equation (30), that _δ_ _w,M_ _∈_ (0 _,_ 1), _δ_ Φ _,M_ _<_ 0, _δ_ _w,X_ _∈_ (0 _,_ 1), and _δ_ Φ _,X_ _>_ 0.
Column (2) reports the results of replacing _w_ _n_, Φ _n_, _w_ _i_ and Φ _i_ with importer-exporter
fixed effects. Column (3) then reports the results of regressing the importer-exporter fixed


23 If we attribute the residual to variation across realizations of _ϵ_ ( _ω_ ) in equation (29), it corresponds to:


_̸_


1 _−_ _β_
_ε_ _[P]_ _nik_ [=] _[ −]_
1 + _γ −_ _β_


_̸_


� _s_ _nik_ ( _ω_ ) ln _ϵ_ ( _ω_ )

_ω∈_ Ω _[k]_


_̸_


where Ω _[k]_ is the set of varieties constituting product _k_ and _s_ _nik_ ( _ω_ ) is the share of variety _ω_ in _i_ ’s exports
to _n_ of product _k_ .


effects from the regression in column (2) on the corresponding importer and exporter
characteristics in column (1). Note that, comparing columns (1) and (3), the coefficients

and their standard errors are almost identical.

Our model implies that three parameters _ν_, _γ_, and _θ_ determine the four coefficients

_δ_ _w,M_, _δ_ Φ _,M_, _δ_ _w,X_, and _δ_ Φ _,X_ . Hence the regression coefficients overdetermine these pa
rameters. Each column in the bottom panel of Table 4 reports the implications of the

corresponding coefficients in the top panel for the parameters _ν_, _γ_, and _θ_ .

Since the coefficients overdetermine the parameters we report their implications for _θ_

based first on the coefficient _δ_ Φ _,M_ on Φ _n_ and then on the coefficient _δ_ Φ _,X_ on Φ _i_ . Since the

variables Φ _n_ and Φ _i_ were constructed as described in subsection 4.1, their estimated coef
ficients suffer from potential attenuation bias. The bottom panel reports the implications

of correcting this bias, as described in Appendix C, for the two estimates of _θ_ . Adjusting

for attenuation lowers the implied values of _θ_ in each case. Whether we adjust or not, the

_θ_ implied by the importer coefficient is much larger than the _θ_ implied by the exporter

coefficient. Still, because the importer _θ_ is imprecisely estimated, we cannot reject the

model’s restriction that the two _θ_ ’s are the same at the 5 percent confidence level from

either the one-stage (column (1)) or two-stage (column (3)) procedures.
Column (4) reports the results of performing the regression reported in column (3)

imposing the restriction that the _θ_ ’s implied by the importer and exporter coefficients are

equal. The point estimate of _θ_ of 8.2 remains imprecisely estimated. We conclude that

our price data do not nail _θ_ precisely.

A number of authors have pointed to a value of around 4 based on various sources of
evidence. [24] This value is not rejected at the 5 percent confidence level by the procedure

reported in column (4). Column (5) reports the results of the same regression as column
(4) with the additional restriction that _θ_ = 4. The implied values of _γ_ and _ν_ barely

change.

## 4.3 Estimating β


Solving for _ϵ_ ( _ω_ ) in the price equation (29) and substituting it into the expression for value
(28), we can write the relationship between value and price in log-linear form:


_β_
log _x_ _ni_ ( _ω_ ) = _δ_ _n_ + _δ_ _i_ _−_
1 _−_ _β_ [log] _[ p]_ _[ni]_ [(] _[ω]_ [)]


24 See, for example, Bernard et al. (2003), Costinot et al. (2011), Simonovska and Waugh (2014), and
Caliendo and Parro (2015) .


Table 5: Estimate of elasticity of spending with respect to prices

|independent var → unit price<br>nik<br>dependent var ↓ OLS|value value<br>nik nik<br>dependent var ↓ OLS IV|
|---|---|
|instrument<br>0.412<br>(0.031)<br>importer ﬁxed eﬀect<br>yes<br>exporter ﬁxed eﬀect<br>yes<br>product ﬁxed eﬀect<br>yes|unit price_nik_<br>-0.252<br>-1.828<br>(0.038)<br>(0.019)<br>yes<br>yes<br>yes<br>yes<br>yes<br>yes|
|R-squared<br>0.70<br>number of observations<br>2,585,111|0.25<br>0.10<br>2,585,111<br>2,585,111|


The table shows the results from estimating the price elasticity of spending on a product. Observations

are specific to importer _n_, exporter _i_, and product _k_ . The instrument is the average price of exporter _i_ ’s

exports of product _k_ to importers other than _n_ . All variables are in logs. The first column reports the

first-stage regression of the price on the instrument. The second column reports the OLS regression of

spending on price and the third column reports the second-stage IV regression. All regressions include

exporter, importer, and product fixed effects.


Aggregating across varieties within a product _k_ we get a product level expression:


_β_
log _x_ _nik_ = _δ_ _n_ + _δ_ _i_ + _δ_ _k_ _−_ 1 _−_ _β_ [log] _[ p]_ _[nik]_ [ +] _[ ε]_ _nik_ _[X]_


where _δ_ _n_, _δ_ _i_, and _δ_ _k_ are, respectively, importer, exporter, and product fixed effects, and
_ε_ _[X]_ _nik_ [is a residual. To account for potential demand shifts in country] _[ n]_ [ for product] _[ k,]_ [ we]

instrument the price _p_ _nik_ with the average price of exporter _i_ in product _k_ to destinations

different from _n_ .

Table 5 shows the results. The first column shows that the instrument has power:

It’s highly correlated with prices even after controlling for all fixed effects. In the last

two columns, the estimated coefficient on price is -0.25 with OLS and -1.83 with IV. The

small coefficient in the OLS regression suggests large simultaneity or measurement error

in prices. The coefficient on price in the IV regression implies an elasticity of demand
with respect to prices of -2.83. [25] The implied _β_ is 0.65.

Our model has allowed us to decompose the intensive margin of trade into unit values

and quantities. Estimating the model with data on values and unit values in bilateral

trade has given us estimates of the parameter values _γ_, _ν_, _θ_, and _β_ . We now turn to the

extensive margin.


25 This figure compares with the median elasticity of 2.7 reported in Broda and Weinstein (2006) for
U.S. imports at the SITC-5 level.


## **4.4 The Extensive Margin**

We interpret equation (28) as determining destination _n_ ’s annual absorption of variety

_ω_, which is sourced from _i_ . We think of this flow, however, as provided through discrete

shipments that come in size _x_ ( _ω_ ). If _x_ _ni_ ( _ω_ ) _≥_ _x_ ( _ω_ ), then a shipment is observed every
year. Otherwise, it’s observed with probability _x_ _ni_ ( _ω_ ) _/x_ ( _ω_ ). Assuming that _x_ has a

cumulative distribution function _H_, the probability of observing the shipment of a variety

_ω_ with trade flow _x_ _ni_ ( _ω_ ) in any given year is


_∞_
_H_ ( _x_ _ni_ ( _ω_ )) + _x_ _ni_ ( _ω_ ) (1 _/x_ ) _dH_ ( _x_ ) _._ (38)
� _x_ _ni_ ( _ω_ )


Trade flow _x_ _ni_ is given by equation (28) with the distribution _J_ of _ϵ_ ( _ω_ ) given in (17).

Assuming _H_ and _J_ are independent from each other and across varieties, the share of

varieties that country _n_ sources from _i_ in a given year is


_π_ ˜ _ni_ = _π_ _ni_


� 0 _∞_


_H_ (˜ _α_ _[−]_ [1] _w_ _n_ _L_ _n_ _ϵ_ _[β/]_ [(1+] _[γ][−][β]_ [)] )
�


_∞_
+ ˜ _α_ _[−]_ [1] _w_ _n_ _L_ _n_ _ϵ_ _[β/]_ [(1+] _[γ][−][β]_ [)] _dJ_ ( _ϵ_ ) _._
� _α_ ˜ _[−]_ [1] _w_ _n_ _L_ _n_ _ϵ_ _[β/]_ [(1+] _[γ][−][β]_ [)] [(1] _[/x]_ [)] _[dH]_ [(] _[x]_ [)] �


To translate the extensive margin at the variety level into the corresponding margin at

the product level, we need to take a stance on the partition of varieties into products. We

think of a product as containing an integer number of varieties. Letting _f_ ( _M_ ) denote the

fraction of products with _M_ varieties, the share of products that country _n_ buys from _i_

in a given year is


_E_ _ni_ =


_∞_
� _f_ ( _M_ ) �1 _−_ (1 _−_ _π_ ˜ _ni_ ) _[M]_ [�] (39)

_M_ =1


We map this extensive margin in the model to the data. To do so, we parameterize _H_ as

exponential:

_H_ ( _x_ ) = 1 _−_ exp( _−λ_ 1 _x_ ) (40)


and the probability mass function _f_ as:


_f_ ( _M_ ) = exp( _−λ_ 2 ( _M −_ 1) _[λ]_ [3] ) _−_ exp( _−λ_ 2 _M_ _[λ]_ [3] ) _,_ (41)


a discretized Weibull density. We estimate the parameters _λ_ 1, _λ_ 2, and _λ_ 3 to minimize:


_̸_


_N_
�


_i_ =1 _̸_


�( _E_ _ni_ _−_ _E_ _ni_ [data] ) [2]


_n_ = _̸_ _i_


_̸_


where _E_ _ni_ [data] is the share of HS6 product categories _n_ buys from _i_ in the 2007 cross section.
The estimated parameters are _λ_ 1 = 2 _._ 26 _e_ _−_ 7 (standard error 1.21e-7), _λ_ 2 = 0 _._ 042 (0.020),
and _λ_ 3 = 0 _._ 48 (0.10). The R-squared is 0.79. Hence these three parameters explain the
extensive margin quite parsimoniously. [26]

# **5 Simulating World Trade**


Now that we’ve quantified the key parameters of our model we can turn to how well it

captures the three margins of trade discussed in Section 2. Since the margins of trade

in the data are at the HS6 product level while our model is about trade in varieties, our

simulation has two stages. The first stage simulates trade among our 50 countries in five

million varieties. The second stage aggregates the simulated varieties into products.

## **5.1 Simulating Varieties**


Continuing to index a variety by _ω_, our simulation for each _ω_ has three components:


1. **Trade in varieties with gravity** For this component of the simulation we use the

model’s prediction that the probability that country _i_ is the cheapest (horizontalquality-adjusted) source of variety _ω_ in country _n_ is:


_̸_


exp( _B_ [ˆ] _i_ ) Φ [ˆ] _[−]_ _n_ [1] _dist_ _δni_ ˆ _[g]_ _n ̸_ = _i_


exp( _A_ [ˆ] _n_ ) Φ [ˆ] _[−]_ _n_ [1] _n_ = _i_


_̸_


ˆ
_π_ _ni_ =


_̸_










_̸_


(42)


_̸_


where _dist_ _ni_ is the distance between destination _n_ and source _i_ and _B_ [ˆ] _i_, _A_ [ˆ] _n_, _δ_ [ˆ] _[g]_,
and Φ [ˆ] _n_ are taken from the estimation of the bilateral resistance terms reported in

Subsection 4.1.


26 The point estimates imply a mean shipment size of $4.42 million (median $3.07 million) and a mean
number of varities per product of 1597 (median 344). The frequency of zeros requires a large shipment
size while the frequency of multiple sources per product-destination requires the large number of varieties
per product.


(a) For each _ω_ we draw _υ_ _i_ ( _ω_ ) from the unit Fr´echet distribution:


_H_ ( _υ_ ) = exp( _−υ_ _[−]_ [1] )


for each source _i_ .


(b) For each bilateral trade pair we calculate:


_υ_ _ni_ ( _ω_ ) = ˆ _π_ _ni_ _υ_ _i_ ( _ω_ ) (43)


which is proportional to the cheapest (horizontal-quality-adjusted) cost of va
riety _ω_ in destination _n_ from source _i_ .


(c) For each destination _n_ we determine the best source _i_ _[∗]_ _n_ [(] _[ω]_ [) for variety] _[ ω]_ [:]


_i_ _[∗]_ _n_ [(] _[ω]_ [) = arg max] _υ_ _ni_ ( _ω_ ) (44)
_i_


establishing the source of variety _ω_ for each destination _n_ . The combinations of

_n_ and _i_ _[∗]_ _n_ [(] _[ω]_ [) constitute the set of bilateral trading pairs for variety] _[ ω]_ [. Since we]
are modeling only international trade we drop observations for which _i_ _[∗]_ _n_ [(] _[ω]_ [) =] _[ n]_ [.]


2. **Bilateral trade values and prices** For this component of the simulation we

calibrate, as above, _θ_ = 4 and ˜ _α_ = 0 _._ 5. Based on the estimation of unit values in

Subsection 4.2, we set _γ_ = 0 _._ 13 and _ν_ = 0 _._ 22 and, based on the results in Subsection

4.3, we set _β_ = 0 _._ 65.


(a) For each nontrading pair (for which _i ̸_ = _i_ _[∗]_ _n_ [(] _[ω]_ [)) we set] _[ x]_ _[ni]_ [(] _[ω]_ [) = 0.]


(b) For each bilateral trading pair, using (17) and (43), we calculate:


1 _/θ_ _−_ 1
_ϵ_ _ni_ ( _ω_ ) = � _υ_ _ni_ _∗n_ ( _ω_ ) ( _ω_ )� Γ 0 (45)


(c) For each bilateral trading pair we substitute (45) into equation (28) to solve
for _x_ _ni_ ( _ω_ ) and into equation (29) to solve for _p_ _ni_ ( _ω_ ).


(d) For each bilateral trading pair we set quantity _y_ _ni_ ( _ω_ ) = _x_ _ni_ ( _ω_ ) _/p_ _ni_ ( _ω_ ).


3. **Censoring due to shipment sizes** We draw a shipment size _x_ ( _ω_ ) from the distribution (40) using the value of _λ_ 1 reported in Section 4.4. For any _x_ _ni_ ( _ω_ ) from the
previous component of the simulation we set the _reported_ trade flow ˜ _x_ _ni_ ( _ω_ ) from


exporter _i_ _[∗]_ _n_ [(] _[ω]_ [) to importer] _[ n]_ [ in variety] _[ ω]_ [ as:]


_x_ ˜ _ni_ ( _ω_ ) = _x_ _ni_ ( _ω_ ) if _x_ _ni_ ( _ω_ ) _> x_ ( _ω_ )


Otherwise, if _x_ _ni_ ( _ω_ ) _≤_ _x_ ( _ω_ ) then the reported trade flow ˜ _x_ _ni_ ( _ω_ ) is randomly drawn

as


_x_ ˜ _ni_ ( _ω_ ) =






_x_ ( _ω_ ) with probability _x_ _ni_ _/x_



0 with probability 1 _−_ _x_




0 with probability 1 _−_ _x_ _ni_ _/x_


We now have, for each variety _ω_ and for each destination _n_ and foreign source _i_ =

_i_ _[∗]_ _n_ [(] _[ω]_ [)] _[ ̸]_ [=] _[ n]_ [, a reported purchase ˜] _[x]_ _[ni]_ [(] _[ω]_ [) and unit value] _[ p]_ _[ni]_ [(] _[ω]_ [). The simulated quantity]
is ˜ _y_ _ni_ ( _ω_ ) = ˜ _x_ _ni_ ( _ω_ ) _/p_ _ni_ ( _ω_ ). We may not report destination _n_ importing variety _ω_ either

because it purchases it domestically or because its simulated purchase from a foreign

source is less than the shipment size for that variety.

## **5.2 Simulating Products**


Having now simulated varieties _ω_ = 1 _,_ 2 _, ...,_ 5 _,_ 000 _,_ 000 we simulate _K_ products indexed

by _k_ = 1 _,_ 2 _, ..., K_ . We partition varieties into products as follows:


1. For product _k_ = 1 we draw its number of varieties _M_ 1 from the probability mass

function _f_ ( _M_ ) given in (41) and assign this product varieties 1 through _M_ 1 .


2. For product _k >_ 1 we draw its number of varieties _M_ _k_ from the probability mass

function _f_ ( _M_ ) and assign it varieties _ω_ _k_ through _ω_ _k_ + _M_ _k_ where


_ω_ _k_ = _ω_ _k−_ 1 + _M_ _k−_ 1 _._


with _ω_ 1 = 1.


3. Sequentially repeating step 2 we continue until we arrive at product _K_ such that

_w_ _K_ + _M_ _K_ _≥_ 5 _,_ 000 _,_ 000 and assign this product varieties _ω_ _K_ through 5,000,000.


This procedure yields 3842 simulated products. Of these, 35 products contain only va
rieties that are not traded between any importer-exporter pair, either because they are

sourced domestically or because the trade value falls below the shipment size. The re
maining 3807 traded products in our simulated dataset compares with 4973 in the COM
TRADE data.


For each importer-exporter pair _ni_ with positive trade in product _k_ we construct value,

quantity, and price as:


_x_ _[k]_ _ni_ [=]


_y_ _ni_ _[k]_ [=]


_ω_ _k_ + _M_ _k_
� _x_ ˜ _ni_ ( _ω_ )


_ω_ = _ω_ _k_


_ω_ _k_ + _M_ _k_
� _y_ ˜ _ni_ ( _ω_ )


_ω_ = _ω_ _k_


_ni_
_p_ _[k]_ _ni_ [=] _[ x]_ _[k]_ _._
_y_ _ni_ _[k]_


The results deliver our model’s analog to COMTRADE’s HS6 bilateral trade data. We

now ask how well our model captures the margins of trade in the actual data described

in Section 2.

## **5.3 Capturing the Margins of Trade**


Table 6 compares the results of regressing bilateral trade value, extensive margin, quantity,

and price on exporter and importer characteristics and distance using the simulated trade

data, in the right panel, compared with the results using the actual data (repeating the
results from Section 2), in the left.

The coefficients based on the simulated data generally mimic those from the actual

data with a couple of exceptions. The model understates the effects of both importer and

exporter per capita income on the extensive margin, shifting their effects toward quantity.

The model also understates the effect of distance on price, the Allen-Archian effect. The

second discrepancy is not surprising given that the model doesn’t incorporate any reason

for such an effect. We repeat, however, that the effect is significant only when exporter

and importer GDP are broken down into per capita GDP and population.

As we pointed out in our discussion of the extensive margin in Section 2.3, the effect of

total GDP on the extensive margin appears to be nonlinear: The range of products both

exported and imported expands rapidly with GDP for small countries, but then appears

to die out as countries get large.

Figure 4 adds observations from the simulated data to those from the actual data

reported in Figure 3. Note how the model picks up the concavity of the relationship

between GDP and the extensive margin.

To summerize, our model, taken to data, captures essential features of the extensive

and intensive margins of trade, and of how the intensive margin in turn breaks down into

quantity and unit value. It does so quite parsimoniously, with just seven parameters: _γ_,


(a) Importer (b) Exporter


Figure 4: Extensive Margin and GDP in the Data and in the Model


_ν_, _θ_, _β_, _λ_ 1, _λ_ 2, and _λ_ 3 .

Our specifications of the price equation in Section 4.2 and demand equation in Section

4.3 are at the level of variety in our model. Our estimation uses data at the level of

HS6 products in the COMTRADE data. We’ve reconciled the two levels by treating HS6

products as collections of varieties. To what extent does aggregation of varieties into

products impede identification of the model’s underlying seven parameters? To address

this question we performed a Monte Carlo analysis, applying our estimation procedure to

the simulated data described in this section to see if we can recover parameter values close

to those used to generate the data. The two sets of parameters are, with the exception of

_β_ when product fixed effects are included, close. Appendix D reports the details.

# **6 Disaggregation**


Our analysis so far, both descriptive and analytic, has been at the level of total mer
chandise trade: In estimating the effects of importer and exporter per capita income on

unit values we pooled observations across all importer-exporter-HS6-product triads in

the COMTRADE data. In estimating our model we imposed common elasticities _γ_ and

_ν_
across all merchandise. We now assess how much damage this (audacious?) level of

aggregation inflicts.

As discussed in Section 2, COMTRADE’s finest level of product categorization is

the 6-digit HS6 classification. COMTRADE also provides three courser partition tiers:

the 4-digit HS4 level, the 2-digit HS2 level, and the partition of HS2 categories into 15


Table 7: Summary of Sections


HS2 importer-exporter importer-exporter
Section Section Name [1] categories -product triads dyads
1 Animal and Animal Products 01-05 49,819 2,062
2 Vegetable Products 06-15 111,340 2,296
3 Food Items 16-24 97,394 2,296
4 Mineral Products 25-27 35,813 2,177
5 Chemicals and Allied Industries 28-38 325,045 2,374
6 Plastics, Rubbers 39-40 157,993 2,382
7 Raw Hides, Skins, Leather, Furs 41-43 34,028 2,173
8 Wood and Wood Products 44-49 126,612 2,362
9 Textiles 50-63 431,606 2,354
10 Footwear, Headgear 64-67 37,225 2,100
11 Stone, Glass 68-71 102,628 2,302
12 Metals 72-83 335,950 2,375
13 Machinery, Electrical 84-85 471,941 2,409
14 Transportation 86-89 67,927 2,305
15 Miscellaneous 90-97 226,379 2,358
**total** **2,611,700** **2,448**


1 Section names on the table are the authors’ own abbreviations of the official names, listed on the
UNCOMTRADE website.


sections. Table 7 lists the sections along with their component HS2 categories, the number

of importer-exporter-HS6 product triads in each, and the number of importer-exporter

dyads in each.

## **6.1 Heterogeneity in the Effects of Income per Capita on Prices**


Our first exercise examines variation in the effects of importer and exporter per capita

income across product categories at the HS6 level. For each of the 4,786 HS6 products

with more than 20 importer-exporter pairs we run the regression:


log _p_ _nik_ = _δ_ 0 _k_ + _δ_ 1 _k_ log _w_ _n_ + _δ_ 2 _k_ log _w_ _i_ + _ϵ_ _nik_ (46)


where _p_ _nik_ is the unit value of the imports of country _n_ from country _i_ of product _k_, _w_ _n_

is the income per capita of importer _n_, _w_ _i_ is the income per capita of exporter _i_, and

_δ_ 0 _k_, _δ_ 1 _k_, and _δ_ 2 _k_ are parameters estimated for each product _k_ . The products represented

account for 96% of the total number of HS6 products and nearly all of international trade

flows in terms of value.

Overall, 80 percent of the coefficients _δ_ 1 _k_ on importer per capita income and 94 percent


of the coefficients _δ_ 2 _k_ on exporter per capita income are positive. To summarize the results

further, Table 8 reports, for each section, the mean coefficient for that section, the fraction

that are positive, and the fraction that are significantly positive. With the exception of

Mineral Products (Section 4) on the importer side, positive coefficients on importer and
exporter per capita income are pervasive within individual sections. Textiles (Section 9)
and Footwear, Headgear (Section 10), sections where we might expect a high degree of

quality differentiation, display particularly large shares of positive coefficients.

How much of the heterogeneity in the coefficients on income per capita at the HS6

level can we attribute to courser levels of classification? To answer this question we
decompose the variances in our estimates _δ_ [ˆ] 1 _k_ and _δ_ [ˆ] 2 _k_ at the HS6 level into within and

between industry classifications for the three courser tiers of classification. Table 9 reports

the share of the variance that is between industry categories for each of the three. The
fifteen sections account for only 10% of the variance across estimates _δ_ [ˆ] 1 _k_ and 13% of the
variance across estimates _δ_ [ˆ] 2 _k_ . Although the number of HS4 product categories, 1,231, is

not much smaller than the 4,786 HS6 categories, HS4 categories account for less than half

of the variance. In sum, broader industry categories account for relatively small variation

in the income elasticities across HS6 product categories. Analysis that focuses on broader

industry classifications leaves a lot of within-industry heterogeneity on the table.

## **6.2 The Model with Sectional Heterogeneity**


The model we develop in Section 3 admits a classification of varieties into different cate
gories _s_ with individual elasticities _γ_ _[s]_ and _ν_ _[s]_, while maintaining trade barriers _d_ _ni_, tech
nology parameters _T_ _i_, and Fr´echet parameter _θ_ that are common across all categories.

This extension of the model allows us to reestimate equation (37) as:


�
log _p_ _[s]_ _nik_ [(] _[k]_ [)] [=] _[ δ]_ 0 _[s]_ [(] _[k]_ [)] + _δ_ _w,M_ _[s]_ [(] _[k]_ [)] [log] _[ w]_ _[n]_ [ +] _[ δ]_ Φ _[s]_ [(] _,M_ _[k]_ [)] log Φ [�] _n_ + _δ_ _w,X_ _[s]_ [(] _[k]_ [)] [log] _[ w]_ _[i]_ [ +] _[ δ]_ Φ _[s]_ [(] _,X_ _[k]_ [)] log Φ [�] _i_ + _ε_ _[P]_ _nik_ (47)


category by category, where _s_ ( _k_ ) is product _k_ ’s category, and:


_γ_ _[s]_
_δ_ _w,M_ _[s]_ [=] 1 + _γ_ _[s]_ _[,]_

_δ_ Φ _[s]_ _,M_ [=] _[ −]_ _θ_ (1 + _γ_ _[s]_ ) _[,]_

_ν_ _[s]_
_δ_ _w,X_ _[s]_ [=] 1 + _γ_ _[s]_ _[,]_

_ν_ _[s]_
_δ_ Φ _[s]_ _,X_ [=] _θ_ (1 + _γ_ _[s]_ ) _[.]_ (48)


Table 9: Share of the variance in _δ_ [ˆ] 1 _k_ and in _δ_ [ˆ] 2 _k_ that is between industry categories


section HS2 HS4 HS6


importer per capita income ( _δ_ [ˆ] 1 _k_ ) 0.10 0.18 0.39 1

exporter per capita income ( _δ_ [ˆ] 2 _k_ ) 0.13 0.25 0.45 1


number of categories 15 96 1,231 4,786


Here the log Φ [�] _i_ ’s are those from expression (36) above. [27]


We implement this disaggregation using COMTRADE’s sections as our categories.

Table 10 reports what results from estimating equation (47) separately by section, imposing (48) and _θ_ = 4. The conditions ˆ _γ_ _[s]_ _>_ 0 and ˆ _ν_ _[s]_ _>_ 0 are satisfied by all sections
(significantly so except for ˆ _γ_ _[Mineral Products]_ ). For many sections, estimates ˆ _γ_ _[s]_ and ˆ _ν_ _[s]_ are
not far from the pooled regression estimates ˆ _γ_ = 0 _._ 13 and ˆ _ν_ = 0 _._ 22. [28]


We conduct a quasi-likelihood ratio test of whether the _γ_ _[s]_ and _ν_ _[s]_ are equal across

sections as follows. We first run an unrestricted version of (47) imposing only that _θ_ = 4

but with _γ_ _[s]_ and _ν_ _[s]_ estimated separately for each section. We denote the resulting sum of

squared residuals as _RSS_ _U_ and calculate the average squared residual ˆ _σ_ _U_ = _RSS_ _U_ _/Obs_,
where _Obs_ = 34 _,_ 325 is the number of observations (one for each importer-exporter-section
triad). We then run a restricted version of (47) imposing _θ_ = 4 and restricting _γ_ _[s]_ = _γ_

and _ν_ _[s]_ = _ν_ . We denote the resulting sum of squared residuals as _RSS_ _R_ and calculate the

average squared residual ˆ _σ_ _R_ = _RSS_ _R_ _/Obs_ . We then calculate:


_χ_ = _Obs_ _[σ]_ [ˆ] _[U]_ _[ −]_ ˆ _[σ]_ [ˆ] _[R]_ _._

_σ_ _U_


Under the null hypothesis, _χ_ is distributed chi-squared with 28 degrees of freedom, where

28 is the number of restrictions _γ_ _[s]_ = _γ_ and _ν_ _[s]_ = _ν_ for _s_ = 1 _, ...,_ 15. Our estimated

test statistic is 1249, well above the critical cutoff 41 for a 5% significance level. The

formal rejection of the null is not surprising given the large number of observations,

ˆ ˆ
_Obs_ = 34 _,_ 325. But the change in squared residuals, (ˆ _σ_ _U_ _−_ _σ_ _R_ ) _/σ_ _U_ is only 3.6 percent.

After extracting the sector fixed effects, the R-squared increases from 0.353 to only 0.376.


27 Treating the parameters _d_ _ni_, _T_ _i_, and _θ_ as common across sections justifies our using these same
estimates of the log Φ [�] _i_ ’s. Otherwise we would have to reestimate the gravity equation (35) category
by category to obtain category-specific estimates log Φ [�] _[s]_ _i_ [. The paucity of nonzero trade flows at more]
disaggregate levels discouraged us from pursuing this alternative approach.
28 We also considered the cases (not consistent with our employing the price equation (36)) (i) in which
the _θ_ backed out from (48) can vary by section, importer, and exporter and (ii) in which _θ_ can vary by
section but is restricted to be the same for importer and exporter. The story is much as at the aggregate
level: _θ_ is poorly identified and we can’t reject _θ_ = 4 at the 5% significance level for any section.


Table 10: Results of Price Regression by Section (47) with _θ_ = 4


_γ_ _ν_
Section par se par se
1 Animal and Animal Products 0.23 0.05 0.12 0.02

2 Vegetable Products 0.18 0.04 0.16 0.02
3 Food Items 0.16 0.04 0.19 0.02

4 Mineral Products 0.03 0.03 0.13 0.02

5 Chemicals and Allied Industries 0.10 0.03 0.16 0.02

6 Plastics, Rubbers 0.12 0.03 0.20 0.02
7 Raw Hides, Skins, Leather, Furs 0.24 0.04 0.20 0.03
8 Wood and Wood Products 0.16 0.03 0.14 0.02

9 Textiles 0.21 0.04 0.28 0.03

10 Footwear, Headgear 0.29 0.06 0.25 0.04
11 Stone, Glass 0.16 0.04 0.24 0.04
12 Metals 0.12 0.04 0.23 0.03

13 Machinery, Electrical 0.11 0.03 0.24 0.04
14 Transportation 0.15 0.04 0.24 0.03
15 Miscellaneous 0.21 0.03 0.27 0.04
**Pooled** (from Table 4) **0.13** **0.01** **0.22** **0.03**


While the data do imply some statistically significant variation across sections, we find

the similarities so pronounced as to vindicate our aggregate approach, leaving further

exploration of heterogeneity across industries for future research.

# **7 Conclusion**


The COMTRADE data on bilateral trade reveal striking patterns about the range of

products that countries buy and sell as well as about the quantities and prices at which

these products are exchanged. Because the data report these magnitudes only for mer
chandise that crosses borders, we’ve applied our analysis to international trade. But the

framework has implications for a wide range of additional issues, such as the roles of dif
ferent margins in economic growth. Without a domestic equivalent of the COMTRADE

data we have only a much cloudier picture of how these different margins operate. We

leave this issue for future research.

Our approach has accommodated the HK facts, as they apply both to intermediate and

to final goods, into the perfectly competitive EK framework. As discussed in the intro
duction, several studies have interpreted these facts using very different approaches that

identify different mechanisms, most notably Feenstra and Romalis (2014), Lashkaripour


(2019b), and Atrianfar (2019). A challenge for future research is to assessing the relative

quantitative contributions of these different mechanisms.

# **References**


Amiti, M. and C. Freund (2010). The anatomy of China’s export growth. In R. Feenstra
and S.-J. Wei (Eds.), _China’s Growing Role in World Trade_, pp. 35–56. University of

Chicago Press.


Anderson, J. E. and E. Van Wincoop (2003). Gravity with gravitas: A solution to the
border puzzle. _The American Economic Review 93_ (1), 170–192.


Anderson, J. E. and E. Van Wincoop (2004). Trade costs. _The Journal of Economic_
_Literature 42_ (3), 691–751.


Arkolakis, C., A. Costinot, and A. Rodriguez-Clare (2012). New trade models, same old
gains? _The American Economic Review 102_ (1), 94–130.


Armenter, R. and M. Koren (2014). A balls-and-bins model of trade. _The American_
_Economic Review 104_ (7), 2127–51.


Atrianfar, H. (2019). Competing on price and quality: Theory and evidence from

trade data. `https://atrianfar.weebly.com/uploads/1/2/2/6/122697364/hamed_`

`atrianfar_jmp.pdf` .


Baier, S. L., J. H. Bergstrand, and M. Feng (2014). Economic integration agreements and
the margins of international trade. _Journal of International Economics 93_ (2), 339–350.


Baldwin, R. and J. Harrigan (2011). Zeros, quality, and space: Trade theory and trade
evidence. _American Economic Journal: Microeconomics 3_ (2), 60–88.


Bekkers, E., J. Francois, and M. Manchin (2012). Import prices, income, and inequality.
_European Economic Review 56_ (4), 848–869.


Bernard, A. B., J. Eaton, J. B. Jensen, and S. Kortum (2003). Plants and productivity
in international trade. _The American Economic Review 93_ (4), 1268–1290.


Besedeˇs, T. and T. J. Prusa (2006). Ins, outs, and the duration of trade. _Canadian_
_Journal of Economics/Revue canadienne d’´economique 39_ (1), 266–295.


Besedeˇs, T. and T. J. Prusa (2011). The role of extensive and intensive margins and
export growth. _Journal of Development Economics 96_ (2), 371–379.


Broda, C. and D. E. Weinstein (2006). Globalization and the gains from variety. _The_
_Quarterly Journal of Economics 121_ (2), 541–585.


Caliendo, L. and F. Parro (2015). Estimates of the trade and welfare effects of NAFTA.
_The Review of Economic Studies 82_ (1), 1–44.


Cameron, A. C., J. B. Gelbach, and D. L. Miller (2011). Robust inference with multiway
clustering. _Journal of Business & Economic Statistics 29_ (2), 238–249.


Chaney, T. (2008). Distorted gravity: The intensive and extensive margins of international
trade. _The American Economic Review 98_ (4), 1707–21.


Choi, Y. C., D. Hummels, and C. Xiang (2009). Explaining import quality: The role of
the income distribution. _Journal of International Economics 77_ (2), 265–275.


Costinot, A., D. Donaldson, and I. Komunjer (2011). What goods do countries trade?
A quantitative exploration of Ricardo’s ideas. _The Review of Economic Studies 79_ (2),

581–608.


Debaere, P. and S. Mostashari (2010). Do tariffs matter for the extensive margin of
international trade? An empirical analysis. _Journal of International Economics 81_ (2),

163–169.


Eaton, J. and S. Kortum (2002). Technology, geography, and trade. _Econometrica 70_ (5),

1741–1779.


Eaton, J., S. Kortum, and F. Kramarz (2011). An anatomy of international trade: Evidence from French firms. _Econometrica 79_ (5), 1453–1498.


Eaton, J., S. Kortum, and S. Sotelo (2013). International trade: Linking micro and
macro. In D. Acemoglu, M. Arellano, and E. Dekel (Eds.), _Advances in Economics and_

_Econometrics: Tenth World Congress_, Volume 2, pp. 329–370. Cambridge University

Press.


Evenett, S. J. and A. Venables (2002). Export growth by developing economies: Market

entry and bilateral trade. `https://www.alexandria.unisg.ch/22177/` .


Fajgelbaum, P., G. M. Grossman, and E. Helpman (2011). Income distribution, product
quality, and international trade. _The Journal of Political Economy 119_ (4), 721–765.


Feenstra, R. C. (1994). New product varieties and the measurement of international
prices. _The American Economic Review 84_ (1), 157–177.


Feenstra, R. C. and J. Romalis (2014). International prices and endogenous quality. _The_
_Quarterly Journal of Economics 129_ (2), 477–527.


Flam, H. and E. Helpman (1987). Vertical product differentiation and North-South trade.
_The American Economic Review 77_ (5), 810–822.


Hallak, J. C. (2006). Product quality and the direction of trade. _Journal of International_
_Economics 68_ (1), 238–265.


Hallak, J. C. (2010). A product-quality view of the Linder hypothesis. _The Review of_
_Economics and Statistics 92_ (3), 453–466.


Hallak, J. C. and P. K. Schott (2011). Estimating cross-country differences in product
quality. _The Quarterly Journal of Economics 126_ (1), 417–474.


Hummels, D. and P. J. Klenow (2005). The variety and quality of a nation’s exports. _The_
_American Economic Review 95_ (3), 704–723.


Hummels, D. and A. Skiba (2004). Shipping the good apples out? An empirical confirmation of the Alchian-Allen conjecture. _The Journal of Political Economy 112_ (6),

1384–1402.


Kehoe, T. J. and K. J. Ruhl (2013). How important is the new goods margin in international trade? _The Journal of Political Economy 121_ (2), 358–392.


Khandelwal, A. (2010). The long and short (of) quality ladders. _The Review of Economic_
_Studies 77_ (4), 1450–1476.


Krugman, P. R. (1979). Increasing returns, monopolistic competition, and international
trade. _Journal of International Economics 9_ (4), 469–479.


Lashkaripour, A. (2019a). Weight-based quality specialization. `http://pages.iu.edu/`


`~` `[alashkar/Lashkaripour_Weight.pdf]` [.]


Lashkaripour, A. (2019b). Within-industry specialization and global market power. _Amer-_

_ican Economic Journal: Micro,_ forthcoming.


Linder, S. B. (1961). _An Essay on Trade and Transformation_ . Almqvist & Wiksell

Stockholm.


Melitz, M. J. (2003). The impact of trade on intra-industry reallocations and aggregate
industry productivity. _Econometrica 71_ (6), 1695–1725.


Rauch, J. E. (1999). Networks versus markets in international trade. _Journal of Interna-_
_tional Economics 48_ (1), 7–35.


Sato, K. (1976). The ideal log-change index number. _The Review of Economics and_
_Statistics 58_ (2), 223–228.


Schott, P. K. (2004). Across-product versus within-product specialization in international
trade. _The Quarterly Journal of Economics 119_ (2), 647–678.


Silva, J. S. and S. Tenreyro (2006). The log of gravity. _The Review of Economics and_
_Statistics 88_ (4), 641–658.


Silva, J. S., S. Tenreyro, and K. Wei (2014). Estimating the extensive margin of trade.
_Journal of International Economics 93_ (1), 67–75.


Simonovska, I. and M. E. Waugh (2014). The elasticity of trade: Estimates and evidence.
_Journal of International Economics 92_ (1), 34–50.


Stokey, N. L. (1991). The volume and composition of trade between rich and poor countries. _The Review of Economic Studies 58_ (1), 63–80.


Vartia, Y. O. (1976). Ideal log-change index numbers. _Scandinavian Journal of Statis-_
_tics 3_ (3), 121–126.


Vernon, R. (1966). International trade and international investment in the product cycle.
_The Quarterly Journal of Economics 80_ (2), 190–207.


Waugh, M. E. (2010). International trade and income differences. _The American Economic_
_Review 100_ (5), 2093–2124.
