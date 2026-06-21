#!/usr/bin/env python3
"""Build a country wiki for ex-energy import Product Gini driver groups.

The wiki is descriptive mechanism research. It starts from local rd2_countries
diagnostics and adds explicitly labeled hypotheses and source hooks. Product
analysis keeps HS6 999999 excluded.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_import_energy_gini_diagnostics import (
    import_cell_file_for_year,
    nonenergy_product_shares,
    product_labels,
)

DIAG_DIR = ROOT / "results" / "samples" / "rd2_countries" / "import_energy_gini_diagnostics"
WIKI_DIR = DIAG_DIR / "country_wiki"
COUNTRY_DIR = WIKI_DIR / "countries"

CLASSIFICATION = DIAG_DIR / "ex_energy_rank_bucket_gini_driver_classification_balanced_2000_2024.csv"
TOP10_ALL = DIAG_DIR / "top10_nonenergy_import_goods_balanced_2000_2012_2024_all_countries.csv"
RANK_DECOMP_ALL = DIAG_DIR / "nonenergy_import_rank_decomposition_balanced_2000_2012_2024_all_countries.csv"
DRIVER_SUMMARY = DIAG_DIR / "ex_energy_rank_bucket_gini_driver_summary_balanced_2000_2024.csv"

BUCKETS = ["top5", "rank6_50", "rank51_200", "rank201_plus"]
SNAPSHOTS = [("start", 2000), ("mid", 2012), ("end", 2024)]
SNAPSHOT_YEARS = [year for _, year in SNAPSHOTS]
BUCKET_LABELS = {
    "top5": "Top 5",
    "rank6_50": "Ranks 6-50",
    "rank51_200": "Ranks 51-200",
    "rank201_plus": "Ranks 201+",
}

SOURCE_CATALOG = {
    "china_wto": {
        "title": "WTO: China accession package and membership date",
        "url": "https://www.wto.org/english/thewto_e/acc_e/a1_chine_e.htm",
        "use": "China's WTO accession is a credible institutional backdrop for electronics, machinery, and raw-material import scaling after 2001.",
    },
    "eu_2004": {
        "title": "European Union: 2004 enlargement",
        "url": "https://european-union.europa.eu/principles-countries-history/history-eu/2000-09/2004_en",
        "use": "EU accession and Single Market integration are key background for Central/Eastern European supply-chain reorganization.",
    },
    "eu_croatia": {
        "title": "European Union: Croatia joins the EU, 1 July 2013",
        "url": "https://european-union.europa.eu/principles-countries-history/history-eu/2010-19/2013_en",
        "use": "Croatia's EU accession is a plausible institutional break for import sourcing and product composition.",
    },
    "usmca": {
        "title": "USTR: USMCA entered into force July 1, 2020",
        "url": "https://ustr.gov/trade-agreements/free-trade-agreements/united-states-mexico-canada-agreement",
        "use": "NAFTA/USMCA background for North American auto, electronics, and intermediate-goods concentration.",
    },
    "eu_morocco": {
        "title": "European Commission: EU-Morocco trade relations",
        "url": "https://policy.trade.ec.europa.eu/eu-trade-relationships-country-and-region/countries-and-regions/morocco_en",
        "use": "EU-Morocco integration is relevant for Morocco's auto, aerospace, and intermediate-input import structure.",
    },
    "singapore_eu_fta": {
        "title": "European Commission: EU-Singapore Free Trade Agreement",
        "url": "https://policy.trade.ec.europa.eu/eu-trade-relationships-country-and-region/countries-and-regions/singapore/eu-singapore-agreement_en",
        "use": "Trade-agreement backdrop for Singapore as a high-value electronics and logistics hub.",
    },
    "rcep": {
        "title": "ASEAN: Regional Comprehensive Economic Partnership",
        "url": "https://asean.org/our-communities/economic-community/integration-with-global-economy/regional-comprehensive-economic-partnership-rcep/",
        "use": "Regional integration backdrop for Asian electronics and supply-chain trade.",
    },
    "panama_canal": {
        "title": "Panama Canal Authority: Expanded canal inaugurated in 2016",
        "url": "https://pancanal.com/en/the-expanded-canal/",
        "use": "Logistics/transshipment context for Panama's import composition and reporting interpretation.",
    },
    "norway_ev_iea": {
        "title": "IEA: Norway electric car market and policy discussion",
        "url": "https://www.iea.org/countries/norway",
        "use": "EV-policy context for Norway's large electric-vehicle import share.",
    },
    "swiss_gold": {
        "title": "Swiss Federal Customs Administration: foreign trade statistics",
        "url": "https://www.bazg.admin.ch/bazg/en/home/topics/swiss-foreign-trade-statistics.html",
        "use": "Gold and precious-metals trade are central to interpreting Switzerland's import concentration.",
    },
    "hong_kong_trade": {
        "title": "Hong Kong Census and Statistics Department: external merchandise trade statistics",
        "url": "https://www.censtatd.gov.hk/en/scode230.html",
        "use": "Hong Kong's role as a re-export/logistics hub is central to interpreting electronics and gold concentration.",
    },
    "singapore_edb_semiconductors": {
        "title": "Singapore EDB: semiconductors and electronics industry",
        "url": "https://www.edb.gov.sg/en/our-industries/semiconductors.html",
        "use": "Singapore sector context for semiconductor import concentration.",
    },
    "ida_ireland_life_sciences": {
        "title": "IDA Ireland: life sciences sector",
        "url": "https://www.idaireland.com/explore-your-sector/life-sciences",
        "use": "Ireland life-science/pharma sector context.",
    },
    "cambodia_garments": {
        "title": "World Bank: Cambodia economy and garment-sector context",
        "url": "https://www.worldbank.org/en/country/cambodia/overview",
        "use": "Cambodia's garment-oriented production structure makes textile-input imports a natural candidate mechanism.",
    },
    "denmark_life_science": {
        "title": "Invest in Denmark: life science sector",
        "url": "https://investindk.com/set-up-a-business/life-science",
        "use": "Denmark life-science/pharma context.",
    },
    "novartis_slovenia": {
        "title": "Novartis Slovenia 2024 network and investment release",
        "url": "https://www.novartis.com/si-en/news/media-releases/novartis-slovenia-sees-growth-workforce-and-enhanced-role-global-novartis-network-2024",
        "use": "Country-specific source for Slovenia pharma/API and biologics interpretation.",
    },
    "imf_guyana_oil": {
        "title": "IMF Guyana Article IV consultation, oil development context",
        "url": "https://www.imf.org/en/News/Articles/2019/09/16/pr19332-guyana-imf-executive-board-concludes-2019-article-iv-consultation",
        "use": "Context for Guyana offshore-oil boom and related non-energy capital imports.",
    },
    "eia_guyana_oil": {
        "title": "EIA Today in Energy: Guyana oil production",
        "url": "https://www.eia.gov/todayinenergy/detail.php?id=62103",
        "use": "Energy-sector context for Guyana capital-equipment import concentration.",
    },
    "fao_zimbabwe_drought": {
        "title": "FAO Zimbabwe El Nino drought response",
        "url": "https://www.fao.org/zimbabwe/news/detail-events/en/c/1680404/",
        "use": "Food-security context for Zimbabwe maize/rice/wheat import concentration.",
    },
    "imf_kyrgyz_reexports": {
        "title": "IMF Kyrgyz Republic 2024 Article IV report",
        "url": "https://www.elibrary.imf.org/view/journals/002/2024/064/article-A001-en.xml",
        "use": "Context for China-to-Russia re-export channels and EAEU trade measurement risks.",
    },
    "eaeu_kyrgyz": {
        "title": "Eurasian Economic Commission: Kyrgyzstan accession",
        "url": "https://eec.eaeunion.org/en/news/12-08-2015-1/",
        "use": "Institutional context for Kyrgyzstan regional trade integration.",
    },
    "imf_armenia": {
        "title": "IMF Armenia 2024 country report",
        "url": "https://www.imf.org/-/media/Files/Publications/CR/2024/English/1ARMEA2024001.ashx",
        "use": "Context for Armenia trade, re-export, and macro adjustment interpretation.",
    },
    "eaeu_armenia": {
        "title": "Eurasian Economic Commission: Armenia accession",
        "url": "https://eec.eaeunion.org/en/news/02-01-2015-1/",
        "use": "Institutional context for Armenia regional trade integration.",
    },
    "statistics_iceland_trade": {
        "title": "Statistics Iceland: Trade in goods 2024 final data",
        "url": "https://statice.is/publications/news-archive/external-trade/trade-in-goods-2024-final-data/",
        "use": "Country trade context for Iceland import composition.",
    },
    "century_aluminum_iceland": {
        "title": "Century Aluminum: Grundartangi Iceland",
        "url": "https://centuryaluminum.com/products-and-plants/grundartangi-iceland/default.aspx",
        "use": "Industrial context for Iceland alumina/carbon-electrode input concentration.",
    },
    "ons_precious_metals": {
        "title": "ONS UK trade quality and methodology information",
        "url": "https://www.ons.gov.uk/economy/nationalaccounts/balanceofpayments/methodologies/uktradeqmi",
        "use": "Methodological context for UK precious-metals trade interpretation.",
    },
    "invest_north_macedonia_jm": {
        "title": "Invest North Macedonia: Johnson Matthey",
        "url": "https://investnorthmacedonia.gov.mk/johnson-matthey/",
        "use": "Context for North Macedonia platinum/palladium and catalyst-related input imports.",
    },
    "eiti_uganda": {
        "title": "EITI Uganda validation",
        "url": "https://eiti.org/board-decision/2024-28",
        "use": "Context for Uganda gold data and informal-mineral-trade caveats.",
    },
    "imf_turkiye_2024": {
        "title": "IMF Turkiye 2024 Article IV consultation",
        "url": "https://www.imf.org/en/news/articles/2024/10/11/pr-24369-turkiye-imf-executive-board-concludes-2024-aiv-consultation",
        "use": "Context for Turkiye gold imports and external adjustment.",
    },
    "tradegov_panama_sez": {
        "title": "Trade.gov: Panama special economic zones",
        "url": "https://www.trade.gov/index.php/market-intelligence/panama-special-economic-zones",
        "use": "Context for Panama logistics, free zones, and re-export interpretation.",
    },
    "wto_tpr": {
        "title": "WTO: Trade policy reviews by country",
        "url": "https://www.wto.org/english/tratop_e/tpr_e/tpr_e.htm",
        "use": "Country trade-policy reviews can verify trade reforms, tariff changes, and sectoral policy context.",
    },
    "oec": {
        "title": "OEC country trade profiles",
        "url": "https://oec.world/",
        "use": "Useful descriptive cross-check for top import/export product composition; not a causal source.",
    },
}

INSTITUTIONAL_KEYS = {
    "CHN": ["china_wto", "rcep"],
    "HKG": ["hong_kong_trade", "china_wto"],
    "POL": ["eu_2004"],
    "HUN": ["eu_2004"],
    "CZE": ["eu_2004"],
    "SVK": ["eu_2004"],
    "SVN": ["eu_2004", "novartis_slovenia"],
    "HRV": ["eu_croatia"],
    "MEX": ["usmca"],
    "CAN": ["usmca"],
    "USA": ["usmca"],
    "MAR": ["eu_morocco"],
    "SGP": ["singapore_edb_semiconductors", "singapore_eu_fta", "rcep"],
    "NOR": ["norway_ev_iea"],
    "CHE": ["swiss_gold"],
    "PAN": ["panama_canal", "tradegov_panama_sez"],
    "IRL": ["ida_ireland_life_sciences"],
    "KHM": ["cambodia_garments"],
    "DNK": ["denmark_life_science"],
    "GUY": ["imf_guyana_oil", "eia_guyana_oil"],
    "ZWE": ["fao_zimbabwe_drought"],
    "KGZ": ["imf_kyrgyz_reexports", "eaeu_kyrgyz"],
    "ARM": ["imf_armenia", "eaeu_armenia"],
    "ISL": ["statistics_iceland_trade", "century_aluminum_iceland"],
    "GBR": ["ons_precious_metals"],
    "MKD": ["invest_north_macedonia_jm"],
    "UGA": ["eiti_uganda"],
    "TUR": ["imf_turkiye_2024"],
}

EU_OLD = {"AUT", "BEL", "DEU", "DNK", "ESP", "FIN", "FRA", "GRC", "IRL", "ITA", "LUX", "NLD", "SWE"}
SMALL_TRANSIT = {"HKG", "SGP", "PAN", "NLD", "BEL", "LUX"}
RESOURCE_OR_SMALL_OPEN = {"GUY", "MRT", "NER", "BFA", "MOZ", "SEN", "UGA", "ZWE", "AZE", "GEO", "ARM", "KGZ"}


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "country"


def fmt(value: object, digits: int = 3) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.{digits}f}"


def pct(value: object, digits: int = 1) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{100 * float(value):.{digits}f}%"


def money(value: object) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    value = float(value)
    if abs(value) >= 1e12:
        return f"${value / 1e12:.2f}T"
    if abs(value) >= 1e9:
        return f"${value / 1e9:.1f}B"
    if abs(value) >= 1e6:
        return f"${value / 1e6:.1f}M"
    return f"${value:,.0f}"


def short(text: object, limit: int = 92) -> str:
    text = str(text or "").replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def md_table(rows: list[list[str]], headers: list[str]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    out.extend("| " + " | ".join(str(cell) for cell in row) + " |" for row in rows)
    return "\n".join(out)


def build_balanced_snapshot_inputs(classification: pd.DataFrame) -> None:
    labels = product_labels()
    top_rows: list[pd.DataFrame] = []
    decomp_rows: list[dict[str, object]] = []

    for row in classification.itertuples(index=False):
        reporter_code = int(row.reporter_code)
        for snapshot, year in SNAPSHOTS:
            file = import_cell_file_for_year(reporter_code, year)
            if file is None:
                raise RuntimeError(f"Missing import-cell checkpoint for {row.country} ({reporter_code}) in {year}")
            product = nonenergy_product_shares(file)
            if product.empty:
                raise RuntimeError(f"No non-energy products for {row.country} ({reporter_code}) in {year}")

            product["country"] = row.country
            product["iso3"] = row.iso3
            product["reporter_code"] = reporter_code
            product["snapshot"] = snapshot
            product["source_file"] = file.name

            top_rows.append(product.head(10).copy())
            decomp_rows.append(
                {
                    "country": row.country,
                    "iso3": row.iso3,
                    "reporter_code": reporter_code,
                    "snapshot": snapshot,
                    "year": year,
                    "top5_share": product.loc[product["rank"] <= 5, "share_nonenergy_imports"].sum(),
                    "rank6_50_share": product.loc[product["rank"].between(6, 50), "share_nonenergy_imports"].sum(),
                    "rank51_200_share": product.loc[
                        product["rank"].between(51, 200), "share_nonenergy_imports"
                    ].sum(),
                    "rank201_plus_share": product.loc[product["rank"] > 200, "share_nonenergy_imports"].sum(),
                    "long_tail_rank51_plus_share": product.loc[product["rank"] > 50, "share_nonenergy_imports"].sum(),
                    "top10_share": product.loc[product["rank"] <= 10, "share_nonenergy_imports"].sum(),
                    "active_nonenergy_products": len(product),
                    "total_nonenergy_imports": product["total_nonenergy_imports"].iloc[0],
                    "source_file": file.name,
                }
            )

    if not top_rows:
        raise RuntimeError("No top-good rows were generated for the balanced wiki snapshots.")

    top_out = pd.concat(top_rows, ignore_index=True).merge(labels, on="cmd_code", how="left")
    top_out["product_label"] = top_out["product_label"].fillna("Unlabeled HS6 product")
    top_out = top_out[
        [
            "country",
            "iso3",
            "reporter_code",
            "snapshot",
            "year",
            "rank",
            "cmd_code",
            "product_label",
            "exercise_03_bin",
            "trade_value",
            "share_nonenergy_imports",
            "total_nonenergy_imports",
            "source_file",
        ]
    ]
    top_out["cmd_code"] = top_out["cmd_code"].astype(str).str.zfill(6)
    decomp_out = pd.DataFrame(decomp_rows)
    validate_wiki_inputs(classification, top_out, decomp_out)
    top_out.to_csv(TOP10_ALL, index=False)
    decomp_out.to_csv(RANK_DECOMP_ALL, index=False)


def validate_wiki_inputs(classification: pd.DataFrame, top: pd.DataFrame, decomp: pd.DataFrame) -> None:
    expected_iso = set(classification["iso3"].astype(str))
    expected_pairs = {(iso3, year) for iso3 in expected_iso for year in SNAPSHOT_YEARS}
    expected_snapshot_pairs = set(SNAPSHOTS)

    if classification["iso3"].duplicated().any():
        dupes = classification.loc[classification["iso3"].duplicated(), "iso3"].tolist()
        raise RuntimeError(f"Duplicate ISO3 rows in classification: {dupes}")
    if set(classification["start_year"].astype(int)) != {2000}:
        raise RuntimeError("Classification start years are not all 2000.")
    if set(classification["end_year"].astype(int)) != {2024}:
        raise RuntimeError("Classification end years are not all 2024.")
    if set(classification["period"].astype(str)) != {"balanced_2000_2024"}:
        raise RuntimeError("Classification period is not balanced_2000_2024 for every country.")

    for name, frame in [("top10", top), ("rank decomposition", decomp)]:
        got_iso = set(frame["iso3"].astype(str))
        if got_iso != expected_iso:
            raise RuntimeError(
                f"{name} country set mismatch: missing {sorted(expected_iso - got_iso)}, extra {sorted(got_iso - expected_iso)}"
            )
        got_years = sorted(frame["year"].astype(int).unique().tolist())
        if got_years != SNAPSHOT_YEARS:
            raise RuntimeError(f"{name} years are {got_years}, expected {SNAPSHOT_YEARS}.")
        got_snapshot_pairs = set(zip(frame["snapshot"].astype(str), frame["year"].astype(int)))
        if got_snapshot_pairs != expected_snapshot_pairs:
            raise RuntimeError(
                f"{name} snapshot/year pairs are {sorted(got_snapshot_pairs)}, expected {sorted(expected_snapshot_pairs)}."
            )

    top_pairs = set(zip(top["iso3"].astype(str), top["year"].astype(int)))
    decomp_pairs = set(zip(decomp["iso3"].astype(str), decomp["year"].astype(int)))
    if top_pairs != expected_pairs:
        raise RuntimeError("Top-10 country-year coverage does not match the balanced classification.")
    if decomp_pairs != expected_pairs:
        raise RuntimeError("Rank-decomposition country-year coverage does not match the balanced classification.")
    if top.duplicated(["iso3", "year", "rank"]).any():
        raise RuntimeError("Duplicate top-10 country-year-rank rows.")
    if decomp.duplicated(["iso3", "year"]).any():
        raise RuntimeError("Duplicate rank-decomposition country-year rows.")
    top_counts = top.groupby(["iso3", "year"]).size()
    if not top_counts.eq(10).all():
        bad = top_counts[~top_counts.eq(10)].head(10).to_dict()
        raise RuntimeError(f"Every country-year must have exactly 10 top-good rows; bad examples: {bad}")
    decomp_counts = decomp.groupby(["iso3", "year"]).size()
    if not decomp_counts.eq(1).all():
        bad = decomp_counts[~decomp_counts.eq(1)].head(10).to_dict()
        raise RuntimeError(f"Every country-year must have one rank-decomposition row; bad examples: {bad}")

    top_codes = top["cmd_code"].astype(str).str.zfill(6)
    if top_codes.eq("999999").any():
        raise RuntimeError("Top goods include excluded HS6 999999.")
    if top["exercise_03_bin"].astype(str).eq("energy").any():
        raise RuntimeError("Top goods include the excluded Exercise 3 energy bin.")

    share_cols = ["top5_share", "rank6_50_share", "rank51_200_share", "rank201_plus_share"]
    max_share_gap = (decomp[share_cols].sum(axis=1) - 1).abs().max()
    if max_share_gap > 1e-8:
        raise RuntimeError(f"Rank-bucket shares do not sum to one; max gap {max_share_gap:.3g}.")

    by_iso = classification.set_index("iso3")
    for snapshot, prefix in [("start", "start"), ("end", "end")]:
        sub = decomp[decomp["snapshot"].eq(snapshot)].set_index("iso3")
        for bucket in BUCKETS:
            gap = (sub[f"{bucket}_share"] - by_iso[f"{prefix}_{bucket}_share"]).abs().max()
            if gap > 1e-10:
                raise RuntimeError(f"{snapshot} {bucket} shares do not match classification; max gap {gap:.3g}.")


def sector_tags(top_rows: pd.DataFrame) -> list[str]:
    tags: set[str] = set()
    codes = top_rows["cmd_code"].astype(str).str.zfill(6).tolist() if not top_rows.empty else []
    labels = " ".join(top_rows["product_label"].astype(str).str.lower().tolist()) if not top_rows.empty else ""
    for code in codes:
        hs2 = code[:2]
        if hs2 in {"29", "30"}:
            tags.add("pharma/life sciences")
        if hs2 in {"84", "85"}:
            tags.add("electronics/ICT/capital equipment")
        if hs2 == "87":
            tags.add("autos/EVs/vehicles")
        if hs2 == "88":
            tags.add("aircraft/aerospace")
        if hs2 == "71":
            tags.add("gold/precious metals")
        if hs2 in {"60", "61", "62", "63", "54", "55"}:
            tags.add("textiles/apparel inputs")
        if hs2 in {"26", "72", "73", "74", "75", "76"}:
            tags.add("ores/metals/industrial materials")
        if hs2 in {"89"}:
            tags.add("ships/logistics capital goods")
    if "lithium-ion" in labels or "electric vehicle" in labels:
        tags.add("energy-transition goods")
    return sorted(tags)


def mechanism_note(row: pd.Series, tags: list[str]) -> tuple[str, str]:
    group = str(row["main_driver_group"])
    tag_text = ", ".join(tags) if tags else "the end-year top goods"
    if "top-5 superstar concentration" in group:
        return (
            "The measured rise is dominated by the top five products. The first hypothesis is not that the country imports fewer products, but that a few HS6 lines became much larger relative to the rest of the non-energy basket.",
            f"Start with {tag_text}. If those lines are semiconductors, gold, pharma, autos, aircraft, or project capital goods, the mechanism is likely intensive-margin scale in a few globally important categories.",
        )
    if "ranks 6-50" in group and "concentration" in group:
        return (
            "The measured rise is strongest in the upper tier rather than only the top five. This is consistent with a cluster of important but not always rank-1 products growing together.",
            f"Treat {tag_text} as a sector-cluster clue. For paper purposes, this is more like supply-chain thickening than one superstar good.",
        )
    if "ranks 51-200" in group:
        return (
            "The measured rise is broad upper-tail concentration. The top five often do not explain the change and can even deconcentrate.",
            f"The plausible story is many mid-sized lines becoming more unequal or sectorally clustered. Top goods such as {tag_text} are clues, but the decisive evidence is ranks 51-200.",
        )
    if "tail compression" in group:
        return (
            "The measured rise comes mainly because the rank-201-plus tail contributes less to equality. This can happen even if the country still imports many goods.",
            "Interpret this as a thinning or relative demotion of small long-tail lines, not necessarily disappearance of products. The next test should compare active-product counts and the cumulative share of ranks 201+.",
        )
    if "deconcentration" in group:
        return (
            "The measured fall means the dominant bucket became less concentrated, with value spreading away from the previously powerful top or upper-tier lines.",
            f"For paper use, this is a counterexample: {tag_text} may still be important, but the measured concentration pressure moved toward a broader basket.",
        )
    return (
        "The net Gini change is small, so offsetting bucket movements matter more than the headline delta.",
        "Use this as a balancing case: the country may have strong sectoral changes, but they offset across buckets.",
    )


def institutional_note(iso3: str) -> tuple[list[str], list[str]]:
    notes: list[str] = []
    keys: list[str] = []
    keys.extend(INSTITUTIONAL_KEYS.get(iso3, []))
    if keys:
        notes.append("Country-specific source hooks below identify plausible sectoral or institutional context; treat them as hypotheses to verify, not causal evidence.")
    if iso3 in EU_OLD:
        notes.append("EU Single Market membership makes intra-European supply-chain and regulatory integration a relevant background condition.")
        keys.append("wto_tpr")
    if iso3 in SMALL_TRANSIT:
        notes.append("Because this is a small or logistics-heavy economy, imports may mix domestic absorption with re-export, storage, refining, or distribution hub activity.")
        keys.append("oec")
    if iso3 in RESOURCE_OR_SMALL_OPEN:
        notes.append("Small-open-economy and resource/infrastructure cycles can make a few capital or intermediate imports unusually large. Treat country-year shocks and reporting changes as live caveats.")
        keys.append("wto_tpr")
    return notes, list(dict.fromkeys(keys))


def top_goods_table(top: pd.DataFrame, country: str) -> str:
    sub = top[top["country"].eq(country)].copy()
    if sub.empty:
        return "No top-10 snapshot rows are available."
    sub["snapshot_order"] = sub["snapshot"].map({"start": 0, "mid": 1, "end": 2}).fillna(99)
    sub = sub.sort_values(["snapshot_order", "rank"])
    rows = []
    for _, r in sub.iterrows():
        rows.append(
            [
                str(r["snapshot"]),
                str(int(r["year"])),
                str(int(r["rank"])),
                str(r["cmd_code"]).zfill(6),
                short(r["product_label"]),
                str(r["exercise_03_bin"]),
                pct(r["share_nonenergy_imports"], 2),
                money(r["trade_value"]),
            ]
        )
    return md_table(rows, ["Snapshot", "Year", "Rank", "HS6", "Product", "Bin", "Share", "Value"])


def rank_share_table(decomp: pd.DataFrame, country: str) -> str:
    sub = decomp[decomp["country"].eq(country)].copy()
    if sub.empty:
        return "No start/mid/end rank-share decomposition rows are available."
    sub["snapshot_order"] = sub["snapshot"].map({"start": 0, "mid": 1, "end": 2}).fillna(99)
    sub = sub.sort_values(["snapshot_order", "year"])
    rows = []
    for _, r in sub.iterrows():
        rows.append(
            [
                str(r["snapshot"]),
                str(int(r["year"])),
                pct(r["top5_share"]),
                pct(r["rank6_50_share"]),
                pct(r["rank51_200_share"]),
                pct(r["rank201_plus_share"]),
                str(int(r["active_nonenergy_products"])),
                money(r["total_nonenergy_imports"]),
            ]
        )
    return md_table(
        rows,
        ["Snapshot", "Year", "Top 5", "Ranks 6-50", "Ranks 51-200", "Ranks 201+", "Active HS6", "Non-energy imports"],
    )


def contribution_table(row: pd.Series) -> str:
    rows = []
    for bucket in BUCKETS:
        rows.append(
            [
                BUCKET_LABELS[bucket],
                pct(row[f"start_{bucket}_share"]),
                pct(row[f"end_{bucket}_share"]),
                pct(row[f"delta_{bucket}_share"]),
                fmt(row[f"delta_{bucket}_gini_contribution"], 4),
            ]
        )
    return md_table(rows, ["Bucket", "Start share", "End share", "Share change", "Gini contribution change"])


def sources_block(keys: list[str]) -> str:
    if not keys:
        keys = ["wto_tpr", "oec"]
    rows = []
    for key in keys:
        src = SOURCE_CATALOG.get(key)
        if not src:
            continue
        rows.append(f"- [{src['title']}]({src['url']}). Use: {src['use']}")
    return "\n".join(rows) if rows else "- Source verification still needed."


def country_page(row: pd.Series, top: pd.DataFrame, decomp: pd.DataFrame) -> str:
    country = str(row["country"])
    iso3 = str(row["iso3"])
    end_top = top[(top["country"].eq(country)) & (top["snapshot"].eq("end"))].sort_values("rank").head(10)
    tags = sector_tags(end_top)
    mechanism, interpretation = mechanism_note(row, tags)
    inst_notes, keys = institutional_note(iso3)
    tag_text = ", ".join(tags) if tags else "no dominant sector tag inferred from end-year top 10"
    inst_text = "\n".join(f"- {note}" for note in inst_notes) if inst_notes else "- No strong institutional note assigned automatically; use WTO TPR/OEC and country-specific sources before making a strong historical claim."

    page = f"""# {country} ({iso3}) - ex-energy import concentration wiki

## Local Classification

- Period: balanced 2000-2024.
- Main driver group: **{row['main_driver_group']}**.
- Direction: **{row['gini_change_direction']}**.
- Ex-energy import Product Gini: {fmt(row['start_panel_ex_energy_gini'])} in {int(row['start_year'])} to {fmt(row['end_panel_ex_energy_gini'])} in {int(row['end_year'])}; change {fmt(row['delta_panel_ex_energy_gini'], 4)}.
- Active non-energy HS6 products: {int(row['start_active_nonenergy_products'])} to {int(row['end_active_nonenergy_products'])}; change {int(row['delta_active_nonenergy_products'])}.
- End-year sector tags from top goods: {tag_text}.

## Rank-Bucket Contribution Decomposition

{contribution_table(row)}

Plain English: a positive contribution change means that rank bucket made the non-energy import basket more unequal. A negative contribution change means that bucket spread value more evenly or lost relative dominance.

## Start/Mid/End Rank Shares

{rank_share_table(decomp, country)}

## Top Non-Energy HS6 Goods

{top_goods_table(top, country)}

## Mechanism Read

**Measured mechanism.** {mechanism}

**Interpretation to test.** {interpretation}

**Institutional and historical hooks.**

{inst_text}

## Competing Hypotheses

- Sector-scale hypothesis: the top HS6 lines reflect real structural growth in one or more sectors rather than a product-code artifact.
- Hub/re-export hypothesis: apparent concentration partly reflects logistics, re-export, refining, storage, or entrepot activity rather than domestic final demand.
- Trade-policy/integration hypothesis: WTO accession, EU accession, FTA changes, or regional value-chain integration changed sourcing and product scale.
- Measurement hypothesis: HS revisions, reporter coverage, source-file changes, valuation, or missing small lines affected the observed long tail.

## Decisive Follow-Up Tests

- Recompute the same page with 5-year windows to see whether the driver is persistent or one-year end-point driven.
- Split top goods into BEC bins and HS2 sectors to test whether the story is pharma/electronics/autos/gold/aircraft/textiles rather than generic concentration.
- For hub countries, compare imports, re-exports, and domestic absorption if national statistics allow it.
- Check whether the top product shares are stable across adjacent years around 2024.
- Compare with with-energy Product Gini to confirm this is not just the energy basket returning through related industrial inputs.

## Evidence Sources To Check

{sources_block(keys)}

## Paper-Use Bottom Line

This is a **descriptive mechanism case**, not a causal proof. Use it as evidence that {country}'s non-energy import concentration changed through **{row['main_driver_group']}**, then qualify the historical explanation until the follow-up source checks above are complete.
"""
    return page


def read_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    classification = pd.read_csv(CLASSIFICATION)
    build_balanced_snapshot_inputs(classification)
    top = pd.read_csv(TOP10_ALL)
    decomp = pd.read_csv(RANK_DECOMP_ALL)
    summary = pd.read_csv(DRIVER_SUMMARY)

    top["cmd_code"] = top["cmd_code"].astype(str).str.zfill(6)
    validate_wiki_inputs(classification, top, decomp)
    return classification, top, decomp, summary


def write_sources() -> None:
    rows = []
    for key, source in SOURCE_CATALOG.items():
        rows.append(f"- **{key}**: [{source['title']}]({source['url']}). Use: {source['use']}")
    (WIKI_DIR / "sources.md").write_text(
        "# Source Catalog\n\n"
        "These are evidence hooks used by the country pages. They are not exhaustive. "
        "Country pages distinguish local measured facts from hypotheses that should be checked against these or more specific sources.\n\n"
        + "\n".join(rows)
        + "\n",
        encoding="utf-8",
    )


def write_method_note() -> None:
    note = """# Method Note

## Object

The wiki studies import Product Gini after removing the project Exercise 3 energy bin and excluding HS6 `999999`.

Important definition: this is not a blanket removal of all HS chapter 27 products. A petroleum-like HS27 code can remain if the upstream Exercise 3 mapping labels it as `unmapped_or_ambiguous` rather than `energy`. Those retained HS27 cases should be treated as definition-sensitive cases in paper text.

## Unit

Country-year-flow, imports only, rd2_countries balanced 2000-2024.

## Gini Contribution Logic

For each country-year, non-energy HS6 products are ranked by import value share. The rank contribution is:

```text
((n - 2r + 1) / n) * product_share_r
```

The rank-bucket contribution is the sum of this expression within top 5, ranks 6-50, ranks 51-200, and ranks 201+.

## Interpretation

Higher Product Gini means import value is more unequally distributed across observed positive HS6 products. A top-5 driver means a few products became much larger relative to the basket. A tail-compression driver means the rank-201-plus tail became less equalizing or smaller relative to upper products.

## Causal Caveat

The country pages are descriptive mechanism hypotheses. They do not identify causal effects of trade agreements, industrial policy, or shocks. Those claims need separate designs.
"""
    (WIKI_DIR / "method_note.md").write_text(note, encoding="utf-8")


def write_readme(classification: pd.DataFrame, summary: pd.DataFrame) -> None:
    group_rows = []
    for _, r in summary.sort_values(["gini_change_direction", "main_driver_group"]).iterrows():
        group_rows.append(
            [
                str(r["gini_change_direction"]),
                str(r["main_driver_group"]),
                str(int(r["countries"])),
                fmt(r["median_delta_gini"], 4),
                fmt(r["mean_delta_gini"], 4),
            ]
        )
    country_links = []
    for group, sub in classification.sort_values(["main_driver_group", "country"]).groupby("main_driver_group"):
        links = ", ".join(
            f"[{r.country}](countries/{slugify(r.country)}.md)" for r in sub.itertuples(index=False)
        )
        country_links.append(f"## {group}\n\n{links}\n")
    readme = f"""# Ex-Energy Import Concentration Country Wiki

This wiki explains why each balanced 2000-2024 `rd2_countries` reporter was assigned to its ex-energy import Product Gini driver group.

## Summary Table

{md_table(group_rows, ["Direction", "Driver group", "Countries", "Median delta Gini", "Mean delta Gini"])}

## How To Use

- Start with the local facts in each country file.
- Treat the mechanism read as a disciplined hypothesis, not as a final causal claim.
- Use `sources.md` and country-specific national statistics to verify institutional or historical claims before putting them in the paper.
- For hub economies, always distinguish imports for domestic use from re-exports or processing/refining.

## Country Files

{chr(10).join(country_links)}

## Files

- `method_note.md`: construction of the measure and rank-bucket decomposition.
- `synthesis.md`: cross-country synthesis and economist-council interpretation memo.
- `group_memos.md`: group-specific notes from the subagent research pass.
- `adversarial_review.md`: trust-review checklist, fixed issue log, and remaining caveats.
- `sources.md`: source hooks for institutional and sectoral verification.
- `country_index.csv`: machine-readable index of country assignments and wiki files.
"""
    (WIKI_DIR / "README.md").write_text(readme, encoding="utf-8")


def main() -> None:
    classification, top, decomp, summary = read_inputs()
    COUNTRY_DIR.mkdir(parents=True, exist_ok=True)

    index_rows = []
    for _, row in classification.sort_values(["main_driver_group", "country"]).iterrows():
        slug = slugify(str(row["country"]))
        path = COUNTRY_DIR / f"{slug}.md"
        path.write_text(country_page(row, top, decomp), encoding="utf-8")
        index_rows.append(
            {
                "country": row["country"],
                "iso3": row["iso3"],
                "main_driver_group": row["main_driver_group"],
                "gini_change_direction": row["gini_change_direction"],
                "delta_panel_ex_energy_gini": row["delta_panel_ex_energy_gini"],
                "wiki_file": f"countries/{slug}.md",
            }
        )

    pd.DataFrame(index_rows).to_csv(WIKI_DIR / "country_index.csv", index=False)
    write_readme(classification, summary)
    write_method_note()
    write_sources()
    print(f"Wrote {WIKI_DIR}")
    print(f"Country files: {len(index_rows)}")


if __name__ == "__main__":
    main()
