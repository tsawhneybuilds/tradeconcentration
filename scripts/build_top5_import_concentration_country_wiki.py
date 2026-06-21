#!/usr/bin/env python3
"""Build a top-5-focused country wiki for ex-energy import concentration.

This wiki is a descriptive mechanism layer over the existing balanced
2000-2012-2024 rd2 country inputs. Product-dependent analysis inherits the
project rules: HS6 999999 and the Exercise 3 energy bin are excluded upstream.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_import_energy_country_wiki import (  # noqa: E402
    INSTITUTIONAL_KEYS,
    RESOURCE_OR_SMALL_OPEN,
    SMALL_TRANSIT,
    SOURCE_CATALOG,
    fmt,
    md_table,
    money,
    pct,
    sector_tags,
    short,
    slugify,
    sources_block,
)


DIAG_DIR = ROOT / "results" / "samples" / "rd2_countries" / "import_energy_gini_diagnostics"
OUT_DIR = DIAG_DIR / "top5_country_wiki"
COUNTRY_DIR = OUT_DIR / "countries"

CLASSIFICATION = DIAG_DIR / "ex_energy_rank_bucket_gini_driver_classification_balanced_2000_2024.csv"
TOP10_ALL = DIAG_DIR / "top10_nonenergy_import_goods_balanced_2000_2012_2024_all_countries.csv"
RANK_DECOMP_ALL = DIAG_DIR / "nonenergy_import_rank_decomposition_balanced_2000_2012_2024_all_countries.csv"

SNAPSHOT_ORDER = {"start": 0, "mid": 1, "end": 2}
TOP5_RISE_THRESHOLD = 0.02
TOP5_BIG_RISE_THRESHOLD = 0.05
TOP5_FALL_THRESHOLD = -0.02

TOP5_COUNTRY_OVERRIDES = {
    "SVN": "pharma/API and biologics superstar",
    "CHE": "gold-refining/vaulting plus pharma",
    "HKG": "electronics and precious-metals trading hub",
    "CHN": "electronics, chips, and industrial-input scale",
    "UGA": "gold and informal/regional mineral-trade channel",
    "ARM": "gold and post-2022 regional re-export channel",
    "KGZ": "cars, machinery, and regional re-export channel",
    "GUY": "offshore-oil capital-equipment shock",
    "MKD": "platinum-group metals and automotive-catalyst inputs",
    "ZWE": "food-security and staple-import concentration",
    "ISL": "small-economy capital/input shock",
    "GBR": "London bullion-market and high-value manufacturing mix",
    "PAN": "logistics/free-zone and pharma/cars mix",
    "DNK": "life-sciences and pharma concentration",
    "TUR": "gold/precious-metals plus macro-financial demand",
}


def validate_inputs(classification: pd.DataFrame, top: pd.DataFrame, decomp: pd.DataFrame) -> None:
    expected_iso = set(classification["iso3"].astype(str))
    if len(expected_iso) != 56:
        raise RuntimeError(f"Expected 56 rd2 countries, got {len(expected_iso)}")
    if classification["iso3"].duplicated().any():
        raise RuntimeError("Duplicate iso3 rows in top-5 classification input.")
    if set(classification["period"].astype(str)) != {"balanced_2000_2024"}:
        raise RuntimeError("Classification must be balanced_2000_2024.")
    for name, frame in [("top10", top), ("rank decomposition", decomp)]:
        if set(frame["iso3"].astype(str)) != expected_iso:
            raise RuntimeError(f"{name} country set mismatch.")
        if sorted(frame["year"].astype(int).unique().tolist()) != [2000, 2012, 2024]:
            raise RuntimeError(f"{name} must contain exactly 2000, 2012, and 2024.")
    if top.duplicated(["iso3", "year", "rank"]).any():
        raise RuntimeError("Duplicate country-year-rank rows in top10 file.")
    if decomp.duplicated(["iso3", "year"]).any():
        raise RuntimeError("Duplicate country-year rows in rank decomposition.")
    if not top.groupby(["iso3", "year"]).size().eq(10).all():
        raise RuntimeError("Every country-year must have exactly 10 top-product rows.")
    if top["cmd_code"].astype(str).str.zfill(6).eq("999999").any():
        raise RuntimeError("Top-product file includes excluded HS6 999999.")
    if top["exercise_03_bin"].astype(str).eq("energy").any():
        raise RuntimeError("Top-product file includes the excluded Exercise 3 energy bin.")

    by_iso = classification.set_index("iso3")
    for snapshot, prefix in [("start", "start"), ("end", "end")]:
        sub = decomp[decomp["snapshot"].eq(snapshot)].set_index("iso3")
        gap = (sub["top5_share"] - by_iso[f"{prefix}_top5_share"]).abs().max()
        if gap > 1e-10:
            raise RuntimeError(f"{snapshot} top5 share mismatch; max gap {gap:.3g}")


def top5_role(row: pd.Series) -> str:
    delta = float(row["delta_top5_share"])
    if str(row["main_driver_bucket"]) == "top5" and delta > 0:
        return "dominant top-5 concentration"
    if str(row["main_driver_bucket"]) == "top5" and delta < 0:
        return "dominant top-5 deconcentration"
    if delta >= TOP5_RISE_THRESHOLD:
        return "secondary top-5 rise"
    if delta <= TOP5_FALL_THRESHOLD and float(row["delta_panel_ex_energy_gini"]) > 0:
        return "countervailing top-5 fall"
    if delta <= TOP5_FALL_THRESHOLD:
        return "top-5 fall with stable/decreasing Gini"
    return "top five not central"


def top5_direction(row: pd.Series) -> str:
    delta = float(row["delta_top5_share"])
    if delta >= TOP5_BIG_RISE_THRESHOLD:
        return "large top-5 rise"
    if delta >= TOP5_RISE_THRESHOLD:
        return "moderate top-5 rise"
    if delta <= TOP5_FALL_THRESHOLD:
        return "top-5 fall"
    return "roughly stable top five"


def top5_summary(row: pd.Series) -> str:
    return (
        f"Top-5 share moved from {pct(row['start_top5_share'])} to {pct(row['end_top5_share'])}, "
        f"a change of {pct(row['delta_top5_share'])}. The top-5 Gini-contribution change was "
        f"{fmt(row['delta_top5_gini_contribution'], 4)}, while total ex-energy Product Gini changed by "
        f"{fmt(row['delta_panel_ex_energy_gini'], 4)}."
    )


def mechanism_family(iso3: str, end_top5: pd.DataFrame, row: pd.Series) -> str:
    if iso3 in TOP5_COUNTRY_OVERRIDES:
        return TOP5_COUNTRY_OVERRIDES[iso3]
    tags = set(sector_tags(end_top5))
    delta = float(row["delta_top5_share"])
    labels = " ".join(end_top5["product_label"].astype(str).str.lower().tolist())
    codes = end_top5["cmd_code"].astype(str).str.zfill(6).tolist()
    hs2 = {code[:2] for code in codes}
    if "gold/precious metals" in tags:
        return "precious-metals, valuation, refining, or hub channel"
    if "pharma/life sciences" in tags:
        return "pharma/life-sciences supply-chain concentration"
    if "electronics/ICT/capital equipment" in tags:
        return "electronics/ICT and capital-equipment supply-chain concentration"
    if "aircraft/aerospace" in tags or "turbo" in labels:
        return "aircraft/aerospace and turbine supply-chain concentration"
    if "autos/EVs/vehicles" in tags or "850760" in codes:
        return "autos, EVs, batteries, and vehicle-input concentration"
    if hs2 & {"10", "11", "15", "17", "19"}:
        return "food-staple and macro-stress concentration"
    if hs2 & {"54", "55", "60", "61", "62", "63"}:
        return "textile/apparel-input concentration or broadening"
    if delta <= TOP5_FALL_THRESHOLD:
        return "top-product deconcentration and value-spreading"
    return "mixed top-product movement"


def top5_goods_table(top: pd.DataFrame, country: str) -> str:
    sub = top[top["country"].eq(country)].copy()
    sub = sub[sub["rank"].le(5)].copy()
    sub["snapshot_order"] = sub["snapshot"].map(SNAPSHOT_ORDER)
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


def top5_trajectory_table(decomp: pd.DataFrame, country: str) -> str:
    sub = decomp[decomp["country"].eq(country)].copy()
    sub["snapshot_order"] = sub["snapshot"].map(SNAPSHOT_ORDER)
    sub = sub.sort_values(["snapshot_order"])
    rows = []
    for _, r in sub.iterrows():
        rows.append(
            [
                str(r["snapshot"]),
                str(int(r["year"])),
                pct(r["top5_share"]),
                pct(r["top10_share"]),
                pct(r["rank6_50_share"]),
                pct(r["long_tail_rank51_plus_share"]),
                str(int(r["active_nonenergy_products"])),
                money(r["total_nonenergy_imports"]),
            ]
        )
    return md_table(
        rows,
        ["Snapshot", "Year", "Top 5", "Top 10", "Ranks 6-50", "Ranks 51+", "Active HS6", "Non-energy imports"],
    )


def institutional_notes(iso3: str) -> tuple[list[str], list[str]]:
    notes: list[str] = []
    keys: list[str] = list(INSTITUTIONAL_KEYS.get(iso3, []))
    if iso3 in SMALL_TRANSIT:
        notes.append("Hub warning: distinguish domestic absorption from re-export, vaulting, refining, free-zone, or logistics activity.")
        keys.append("oec")
    if iso3 in RESOURCE_OR_SMALL_OPEN:
        notes.append("Small-open/resource warning: one project, commodity, or import-financing shock can dominate top-five value.")
        keys.append("wto_tpr")
    if keys:
        notes.append("Use the source hooks below as verification targets, not as already-identified causal evidence.")
    if not notes:
        notes.append("No automatic country-specific institutional hook was assigned; verify the sector story with WTO TPR, national statistics, and partner-product data.")
        keys.extend(["wto_tpr", "oec"])
    return notes, list(dict.fromkeys(keys))


def council_text(row: pd.Series, end_top5: pd.DataFrame, family: str) -> str:
    country = str(row["country"])
    role = str(row["top5_role"])
    direction = str(row["top5_direction"])
    top1 = end_top5.sort_values("rank").iloc[0] if not end_top5.empty else None
    top1_text = (
        f"{str(top1['cmd_code']).zfill(6)} {top1['product_label']} at {pct(top1['share_nonenergy_imports'], 2)}"
        if top1 is not None
        else "no end-year top product available"
    )
    tags = ", ".join(sector_tags(end_top5)) or "no strong sector tag"
    return f"""## Mini Economist Council

### Council Setup

- Question: What explains {country}'s top-five non-energy import concentration pattern?
- Unit: country-level start/mid/end snapshots for 2000, 2012, and 2024.
- Council seats: Measurement Hawk; GVC Economist; Trade Historian; Development/Resource Economist; Referee 2 Skeptic.

### Round 1: Opening Positions

**Measurement Hawk.** {top5_summary(row)} This is a {direction} case and is classified as **{role}**. The first thing to test is whether the same product family is persistently large around 2024 or whether the endpoint is doing too much work.

**GVC Economist.** The end-year top-one product is {top1_text}. The sector fingerprint is {tags}. The best mechanism read is **{family}**, but it should be checked against partner flows and sector-level decompositions.

**Trade Historian.** Institutional history may matter only if it lines up with product timing. Treat WTO/EU/FTA/free-zone/re-export explanations as hypotheses until we see the top-five shift around the relevant dates.

**Development/Resource Economist.** For small economies, resource projects, gold, food staples, and capital imports can dominate top-five value without implying ordinary consumer or manufacturing specialization. For larger economies, the same top-five movement is more likely to be a genuine scale or supply-chain pattern.

**Referee 2 Skeptic.** The strongest skeptical read is endpoint, price, or reporting sensitivity. A top-five spike in gold, aircraft, platforms, food, or pharma can be real in trade value while still being a poor proxy for structural diversification.

### Round 2: Cross-Examination

**Measurement Hawk -> GVC Economist.** The sector story is only convincing if it survives a leave-one-product test. If one HS6 line explains most of the 2024 top-five share, call it a product shock first and a structural mechanism second.

**GVC Economist -> Measurement Hawk.** Endpoint sensitivity is real, but the middle snapshot matters. If the same family is already rising by 2012, the mechanism is less likely to be a one-year artifact and more likely to be a supply-chain or demand-composition shift.

**Trade Historian -> Development/Resource Economist.** Do not infer crisis, policy, accession, or re-export channels from the product list alone. The historical explanation must line up with the timing of the top-five shift and with partner-product flows.

**Development/Resource Economist -> Trade Historian.** For small, resource, or hub economies, institutional history can be the whole story: vaulting, refining, free zones, regional arbitrage, or a single project can dominate measured imports without broad domestic structural change.

**Referee 2 Skeptic -> Everyone.** The publishable claim should be the narrow one: whether {country}'s top five rose, fell, or offset the Gini. The mechanism label is a hypothesis until adjacent-year, partner, and leave-one-HS-family checks are run.

### What Would Change Minds

- Adjacent-year stability around 2024 for the top five.
- Leave-one-top-product and leave-one-HS2 sensitivity.
- Partner-by-product decomposition for the end-year top five.
- Fixed HS4/HS family robustness to reduce HS revision artifacts.
- Domestic absorption or re-export checks for hub economies.

### Redesign / Next Empirical Move

Smallest credibility upgrade: make a four-panel country diagnostic showing 2000/2012/2024 top-five product shares, leave-one-top-product Gini, partner sources for the 2024 top five, and adjacent-year stability for 2022-2024.

### Council Verdict

Strongest version: {country}'s top-five pattern is best read as **{family}**. Main threat: top-five concentration is value-weighted and can be driven by prices, re-exports, vaulting, one-off projects, or HS revisions. Best next test: leave out the largest 2024 top-five product and see whether the top-five role still holds. Paper use: report the top-five fact, then qualify the mechanism until the decisive tests above are run.
"""


def country_page(row: pd.Series, top: pd.DataFrame, decomp: pd.DataFrame) -> str:
    country = str(row["country"])
    iso3 = str(row["iso3"])
    end_top5 = top[(top["country"].eq(country)) & (top["snapshot"].eq("end")) & top["rank"].le(5)].copy()
    family = mechanism_family(iso3, end_top5, row)
    notes, keys = institutional_notes(iso3)
    notes_text = "\n".join(f"- {note}" for note in notes)
    return f"""# {country} ({iso3}) - top-5 import concentration wiki

## Local Top-5 Classification

- Period: balanced 2000-2024.
- Top-5 role: **{row['top5_role']}**.
- Top-5 direction: **{row['top5_direction']}**.
- Mechanism family: **{family}**.
- Overall ex-energy import Product Gini direction: **{row['gini_change_direction']}**.
- Original full-rank driver group: **{row['main_driver_group']}**.
- {top5_summary(row)}
- Active non-energy HS6 products: {int(row['start_active_nonenergy_products'])} to {int(row['end_active_nonenergy_products'])}; change {int(row['delta_active_nonenergy_products'])}.

## Top-5 Trajectory

{top5_trajectory_table(decomp, country)}

## Top Five Non-Energy Import Goods

{top5_goods_table(top, country)}

{council_text(row, end_top5, family)}

## Institutional and Historical Hooks

{notes_text}

## Evidence Sources To Check

{sources_block(keys)}

## Paper-Use Bottom Line

For {country}, the top-five evidence points to **{family}** and should be described as **{row['top5_role']}**. Do not claim causality from the country file alone; use it to choose leave-one-product, partner, and adjacent-year tests.
"""


def read_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    classification = pd.read_csv(CLASSIFICATION)
    top = pd.read_csv(TOP10_ALL)
    decomp = pd.read_csv(RANK_DECOMP_ALL)
    top["cmd_code"] = top["cmd_code"].astype(str).str.zfill(6)
    validate_inputs(classification, top, decomp)
    classification["top5_role"] = classification.apply(top5_role, axis=1)
    classification["top5_direction"] = classification.apply(top5_direction, axis=1)
    families = []
    for _, row in classification.iterrows():
        end_top5 = top[
            top["iso3"].astype(str).eq(str(row["iso3"]))
            & top["snapshot"].eq("end")
            & top["rank"].le(5)
        ].copy()
        families.append(mechanism_family(str(row["iso3"]), end_top5, row))
    classification["mechanism_family"] = families
    return classification, top, decomp


def write_readme(classification: pd.DataFrame) -> None:
    role_rows = []
    for role, sub in classification.groupby("top5_role", sort=True):
        role_rows.append(
            [
                str(role),
                str(len(sub)),
                fmt(sub["delta_top5_share"].median(), 4),
                fmt(sub["delta_top5_gini_contribution"].median(), 4),
                ", ".join(sorted(sub["country"].astype(str))),
            ]
        )
    family_rows = []
    for family, sub in classification.groupby("mechanism_family", sort=True):
        family_rows.append(
            [
                str(family),
                str(len(sub)),
                ", ".join(sorted(sub["country"].astype(str))),
            ]
        )
    readme = f"""# Top-5 Import Concentration Country Wiki

This wiki focuses only on the top five non-energy HS6 import products in each balanced 2000-2024 rd2 country. It asks whether the top five explain the concentration change, offset it, or merely provide sector clues while the real action happens lower in the rank distribution.

## Role Summary

{md_table(role_rows, ["Top-5 role", "Countries", "Median delta top-5 share", "Median delta top-5 Gini contribution", "Country list"])}

## Mechanism-Family Summary

{md_table(family_rows, ["Mechanism family", "Countries", "Country list"])}

## How To Read

- Start with `synthesis.md` for the aggregate story.
- Use `group_memos.md` to compare country groups.
- Use individual country files for the top-five trajectory, top products, and mini economist-council read.
- Treat historical hooks as verification targets rather than causal evidence.

## Files

- `synthesis.md`: aggregate top-five story.
- `group_memos.md`: group-by-group top-five mechanism notes.
- `countries/`: 56 per-country top-five files.
- `method_note.md`: exact construction and thresholds.
- `sources.md`: source hooks.
- `adversarial_review.md`: local trust review and caveats.
"""
    (OUT_DIR / "README.md").write_text(readme, encoding="utf-8")


def write_synthesis(classification: pd.DataFrame) -> None:
    role_counts = classification["top5_role"].value_counts().to_dict()
    family_counts = classification["mechanism_family"].value_counts().to_dict()
    top_positive = classification.sort_values("delta_top5_share", ascending=False).head(8)
    top_negative = classification.sort_values("delta_top5_share").head(8)
    pos_rows = [
        [r.country, r.iso3, pct(r.delta_top5_share), str(r.mechanism_family), str(r.main_driver_group)]
        for r in top_positive.itertuples(index=False)
    ]
    neg_rows = [
        [r.country, r.iso3, pct(r.delta_top5_share), str(r.mechanism_family), str(r.main_driver_group)]
        for r in top_negative.itertuples(index=False)
    ]
    text = f"""# Top-5 Import Concentration Synthesis

## Question

If we ignore the lower rank buckets and stare only at the top five non-energy import products, what is happening country by country?

## Short Answer

The top-five story is sharper than the full-rank story, but it is also more dangerous to overread. In the balanced rd2 panel, **{role_counts.get('dominant top-5 concentration', 0)} countries** are true top-five superstar cases, while **{role_counts.get('dominant top-5 deconcentration', 0)} countries** are top-five deconcentration cases. Another **{role_counts.get('countervailing top-5 fall', 0)} countries** become more concentrated overall even though their top five fall, which means the action moved into ranks 6-50, ranks 51-200, or the tail.

## Best Aggregate Story

1. **Top-five concentration is not one mechanism.** The top-five superstar group mixes pharma/API, electronics/semiconductors, gold/precious metals, project capital goods, and food-security shocks.
2. **Gold and precious metals need the strongest caveat.** Switzerland, the United Kingdom, Armenia, Uganda, Turkey, Hong Kong, and North Macedonia can look extremely concentrated because bullion, refining, vaulting, valuation, and regional trade channels show up as ordinary import values.
3. **Pharma and life sciences are the cleanest structural top-five story.** Slovenia and Denmark, with Switzerland partly, look like genuine high-value supply-chain concentration.
4. **Electronics and chips are hub/GVC cases.** China, Hong Kong, and Singapore-style cases need partner-product decomposition before we decide whether the imports are for domestic production, re-export, or both.
5. **Top-five deconcentration is a serious counterexample.** Cambodia and India show that integration or growth can spread value away from old top products. Several rich countries also have falling top-five shares while overall Gini rises.

## Mechanism Families

{md_table([[k, str(v)] for k, v in sorted(family_counts.items())], ["Mechanism family", "Countries"])}

## Largest Top-Five Rises

{md_table(pos_rows, ["Country", "ISO3", "Delta top-5 share", "Mechanism family", "Full-rank driver"])}

## Largest Top-Five Falls

{md_table(neg_rows, ["Country", "ISO3", "Delta top-5 share", "Mechanism family", "Full-rank driver"])}

## Economist Council Verdict

- **Measurement Hawk:** the top-five lens is useful precisely because it reveals superstar products, but it is sensitive to endpoint years, price spikes, and HS coding.
- **GVC Economist:** the most credible structural stories are sectoral supply-chain stories: pharma/API, electronics, autos/EVs, aerospace, and industrial inputs.
- **Trade Historian:** trade agreements and accession events are useful context, but they should not be written as causal explanations unless product timing lines up.
- **Development/Resource Economist:** small economies and resource economies can be dominated by one project, one mineral, one food shock, or one financing channel.
- **Referee 2 Skeptic:** the first hostile question will be whether the top-five result survives leaving out gold, aircraft/platforms, pharma, and one-year 2024 shocks.

## Best Paper Language

Use: “The top-five decomposition shows that import reconcentration is sometimes a true superstar-product phenomenon, but in many countries top products fall or stay stable while concentration rises lower in the rank distribution.”

Avoid: “Top-five concentration explains import concentration everywhere.”
"""
    (OUT_DIR / "synthesis.md").write_text(text, encoding="utf-8")


def write_group_memos(classification: pd.DataFrame) -> None:
    sections = ["# Top-5 Group Memos\n"]
    for role, sub in classification.sort_values(["top5_role", "country"]).groupby("top5_role", sort=True):
        families = sub["mechanism_family"].value_counts().to_dict()
        countries = ", ".join(sub["country"].astype(str).tolist())
        sections.append(
            f"""## {role}

Countries: {countries}.

Mechanism-family mix: {', '.join(f'{k} ({v})' for k, v in families.items())}.

Council read: this group should be interpreted through the top-five lens, but the burden of proof differs. If the role is dominant top-five concentration, the next test is leave-one-top-product and partner decomposition. If the role is countervailing or not central, the top five are clues, not the main mechanism.

Best next tests:

- Adjacent-year top-five stability.
- Leave-one-top-product sensitivity.
- Leave-one-HS2 or BEC-bin sensitivity.
- Product-partner decomposition for the top five.
- Domestic absorption versus re-export checks for hub economies.
"""
        )
    (OUT_DIR / "group_memos.md").write_text("\n".join(sections), encoding="utf-8")


def write_method_note() -> None:
    note = f"""# Method Note

## Object

Top-five non-energy HS6 import concentration for the balanced 2000-2024 rd2 countries.

## Exclusions

HS6 `999999` is excluded upstream. Products in the Exercise 3 energy bin are excluded before ranking. This top-five wiki is therefore an **ex-energy import** product analysis.

## Unit

Country snapshots in 2000, 2012, and 2024. Each country file uses the top five products in each snapshot and compares top-five share and top-five Gini contribution from 2000 to 2024.

## Main Measures

```text
top5_share_ct = sum import_share_pct over ranks 1..5

delta_top5_share_c = top5_share_c,2024 - top5_share_c,2000
```

The top-five Gini contribution uses the same rank contribution as the full country wiki:

```text
((n - 2r + 1) / n) * product_share_r
```

summed over ranks 1 through 5.

## Role Classification

- `dominant top-5 concentration`: top five are the main positive full-rank driver.
- `dominant top-5 deconcentration`: top five are the main negative full-rank driver.
- `secondary top-5 rise`: top five rise by at least {pct(TOP5_RISE_THRESHOLD)} but another bucket is the main full-rank driver.
- `countervailing top-5 fall`: overall Gini rises while top-five share falls by at least {pct(abs(TOP5_FALL_THRESHOLD))}.
- `top five not central`: top-five share changes by less than {pct(TOP5_RISE_THRESHOLD)} in either direction.

## Caveat

The threshold labels are descriptive aids, not inferential tests. The country files are economist-council mechanism hypotheses, not causal estimates.
"""
    (OUT_DIR / "method_note.md").write_text(note, encoding="utf-8")


def write_sources() -> None:
    rows = []
    for key, source in SOURCE_CATALOG.items():
        rows.append(f"- **{key}**: [{source['title']}]({source['url']}). Use: {source['use']}")
    (OUT_DIR / "sources.md").write_text(
        "# Source Hooks\n\n"
        "These links are verification hooks for the country memos. The top-five wiki does not treat them as causal proof.\n\n"
        + "\n".join(rows)
        + "\n",
        encoding="utf-8",
    )


def write_adversarial_review(classification: pd.DataFrame, top: pd.DataFrame, decomp: pd.DataFrame) -> None:
    review = f"""# Adversarial Review: Top-5 Country Wiki

## Executive Verdict

Trustworthy for current descriptive purpose, with caveats.

- The wiki is built from the same balanced 2000-2012-2024 country set as the existing ex-energy country wiki.
- It uses one row per country in the classification file, 10 top-product rows per country-year, and one rank-decomposition row per country-year.
- HS6 `999999` and Exercise 3 energy-bin products are absent from the top-product inputs.
- The top-five share in the snapshot file matches the classification file for 2000 and 2024.
- The economist-council mechanism language is explicitly descriptive and does not claim causal identification.

## Data Lineage and Sample Audit

- Countries: {classification['iso3'].nunique()}.
- Top-product rows: {len(top)} = 56 countries x 3 years x 10 products.
- Rank-decomposition rows: {len(decomp)} = 56 countries x 3 years.
- Years: {', '.join(map(str, sorted(top['year'].astype(int).unique())))}.
- Unit of observation in country files: country snapshots and 2000-2024 country change.

## Highest-Risk Findings

1. Top-five mechanisms are endpoint sensitive. A 2024 gold, platform, aircraft, food, or pharma spike can dominate the story.
2. Historical hooks are source targets, not verified causal events. They should not be used as causal language without timing and partner-product tests.
3. Hub economies require domestic-absorption checks. Hong Kong, Singapore, Panama, Netherlands, Belgium, Luxembourg, Switzerland, and the UK can mix domestic use, re-export, vaulting, refining, or free-zone flows.
4. Price effects can masquerade as structural concentration for gold, food staples, aircraft, platforms, and medicines.

## Minimal Patch Plan

- Add adjacent-year top-five stability graphs around 2024.
- Add leave-one-top-product and leave-one-HS2 sensitivity for all countries.
- Add partner-by-product decomposition for each 2024 top-five product.
- Add a harmonized HS4 family robustness layer.

## Researcher Questions

- Should the paper treat gold and non-monetary precious metals as a separate exclusion sensitivity?
- Should top-five explanations be restricted to countries where the top-five role is dominant rather than secondary?
- Do we want a country-page badge for “hub/re-export caveat” and “commodity/valuation caveat”?
"""
    (OUT_DIR / "adversarial_review.md").write_text(review, encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    COUNTRY_DIR.mkdir(parents=True, exist_ok=True)
    classification, top, decomp = read_inputs()

    index_rows = []
    for _, row in classification.sort_values(["top5_role", "mechanism_family", "country"]).iterrows():
        slug = slugify(str(row["country"]))
        path = COUNTRY_DIR / f"{slug}.md"
        path.write_text(country_page(row, top, decomp), encoding="utf-8")
        index_rows.append(
            {
                "country": row["country"],
                "iso3": row["iso3"],
                "top5_role": row["top5_role"],
                "top5_direction": row["top5_direction"],
                "mechanism_family": row["mechanism_family"],
                "main_driver_group": row["main_driver_group"],
                "gini_change_direction": row["gini_change_direction"],
                "start_top5_share": row["start_top5_share"],
                "end_top5_share": row["end_top5_share"],
                "delta_top5_share": row["delta_top5_share"],
                "delta_top5_gini_contribution": row["delta_top5_gini_contribution"],
                "delta_panel_ex_energy_gini": row["delta_panel_ex_energy_gini"],
                "wiki_file": f"countries/{slug}.md",
            }
        )

    index = pd.DataFrame(index_rows)
    index.to_csv(OUT_DIR / "country_index.csv", index=False)
    write_readme(classification)
    write_synthesis(classification)
    write_group_memos(classification)
    write_method_note()
    write_sources()
    write_adversarial_review(classification, top, decomp)
    print(f"Wrote {OUT_DIR}")
    print(f"Country files: {len(index_rows)}")


if __name__ == "__main__":
    main()
