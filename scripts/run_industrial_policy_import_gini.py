#!/usr/bin/env python3
"""Link JLOP industrial-policy measures to ex-energy import Product Gini.

This is a descriptive rd2-country exercise for 2010-2022. It uses the
Juhasz-Lane-Oehlsen-Perez industrial-policy data and the existing project
ex-energy import Product Gini panel. Product-facing concentration outcomes
inherit the upstream exclusion of HS6 999999 and the Exercise 3 energy bin.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from pathlib import Path
import math
import re
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import statsmodels.formula.api as smf


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "results" / "samples" / "rd2_countries"
PROCESSED = ROOT / "data" / "processed" / "samples" / "rd2_countries"
RAW_DIR = ROOT / "data" / "raw" / "industrial_policy_jlop_2025"
OUT_DIR = BASE / "industrial_policy_import_gini"
FIG_DIR = OUT_DIR / "figures"

JLOP_DTA = RAW_DIR / "JLOP_2025.dta"
JLOP_README = RAW_DIR / "README.md"
JLOP_DTA_URL = "https://github.com/industrialpolicygroup/IndustrialPolicyData/raw/main/data/JLOP_2025.dta"
JLOP_README_URL = "https://raw.githubusercontent.com/industrialpolicygroup/IndustrialPolicyData/main/README.md"

CLASSIFICATION = (
    BASE
    / "import_energy_gini_diagnostics"
    / "ex_energy_rank_bucket_gini_driver_classification_balanced_2000_2024.csv"
)
IMPORT_BIN_DECOMP = BASE / "exercise_03_tables" / "import_bin_decomposition.csv"
PPP_CONTROLS = PROCESSED / "ppp_hump_world_bank_controls.csv"
WDI_GVC_CONTROLS = PROCESSED / "import_gini_mechanism_world_bank_controls.csv"
WDI_BASE_CONTROLS = BASE / "import_concentration_explanatory_regressions" / "wdi_controls_2000_2024.csv"

START_YEAR = 2010
END_YEAR = 2022
FULL_START_YEAR = 2000
FULL_END_YEAR = 2024

PROTECTION_CHAPTERS = {
    "Tariff measures",
    "Contingent trade-protective measures",
    "Non-automatic licensing, quotas, prohibitions",
    "Government procurement restrictions",
    "Trade-related investment measures",
}
IMPORT_SUB_MEASURE_PATTERNS = [
    "import tariff",
    "anti-dumping",
    "anti-subsidy",
    "anti-circumvention",
    "safeguard",
    "import licensing",
    "import ban",
    "import quota",
    "internal taxation of imports",
    "import-related",
    "local content",
    "local value added",
    "public procurement localisation",
    "public procurement localization",
    "localisation",
    "localization",
]
EXPORT_PROMO_PATTERNS = [
    "export",
    "foreign market",
    "trade finance",
]
SUBSIDY_PATTERNS = [
    "financial grant",
    "state loan",
    "loan guarantee",
    "production subsidy",
    "state aid",
    "capital injection",
    "tax or social insurance relief",
    "interest payment subsidy",
]
EU_RD2_MEMBERS = {
    "AUT",
    "BEL",
    "HRV",
    "CZE",
    "DNK",
    "FIN",
    "FRA",
    "DEU",
    "GRC",
    "HUN",
    "IRL",
    "ITA",
    "LUX",
    "NLD",
    "POL",
    "SVK",
    "SVN",
    "ESP",
    "SWE",
}


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    hypothesis: str
    dataset: str
    formula: str
    terms: tuple[str, ...]
    covariance: str


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def ensure_raw() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for url, path in [(JLOP_DTA_URL, JLOP_DTA), (JLOP_README_URL, JLOP_README)]:
        if path.exists() and path.stat().st_size > 0:
            continue
        response = requests.get(url, timeout=120)
        response.raise_for_status()
        path.write_bytes(response.content)


def ensure_dirs() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)


def validate_unique(df: pd.DataFrame, keys: list[str], label: str) -> None:
    missing = sorted(set(keys) - set(df.columns))
    if missing:
        raise RuntimeError(f"{label} missing keys: {missing}")
    dupes = int(df.duplicated(keys).sum())
    if dupes:
        examples = df.loc[df.duplicated(keys, keep=False), keys].head(8).to_dict("records")
        raise RuntimeError(f"{label} has duplicate keys on {keys}: {examples}")


def safe_log(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    return np.where(values > 0, np.log(values), np.nan)


def norm_token(text: object) -> str:
    out = str(text or "").strip()
    out = re.sub(r"\s+", " ", out)
    out = out.strip(" ;,")
    if out.lower().startswith("the "):
        out = out[4:].strip()
    return out


def token_to_iso(token: str, year: int, country_map: dict[str, str], include_eu: bool) -> list[str]:
    cleaned = norm_token(token)
    if not cleaned:
        return []
    aliases = {
        "United States of America": "USA",
        "United States": "USA",
        "Republic of Korea": "KOR",
        "South Republic of Korea": "KOR",
        "Hong Kong": "HKG",
        "China, Hong Kong SAR": "HKG",
        "Czechia": "CZE",
        "Czech Republic": "CZE",
    }
    if cleaned in aliases:
        return [aliases[cleaned]]
    if cleaned in country_map:
        return [country_map[cleaned]]
    if cleaned in {"EU", "EC", "EU Countries"}:
        if not include_eu:
            return []
        members = set(EU_RD2_MEMBERS)
        if year <= 2019:
            members.add("GBR")
        return sorted(members)
    return []


def split_country_tokens(country_text: object) -> list[str]:
    text = str(country_text or "")
    text = text.replace(" and ", " & ")
    text = text.replace("&&", "&")
    return [norm_token(part) for part in text.split("&") if norm_token(part)]


def contains_any(text: object, patterns: Iterable[str]) -> bool:
    low = str(text or "").lower()
    return any(pattern in low for pattern in patterns)


def read_classification() -> pd.DataFrame:
    df = pd.read_csv(CLASSIFICATION)
    required = {"country", "iso3", "reporter_code"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise RuntimeError(f"Classification missing columns: {missing}")
    df["iso3"] = df["iso3"].astype(str).str.upper()
    validate_unique(df, ["iso3"], "rd2 classification")
    return df[["country", "iso3", "reporter_code"]].copy()


def read_outcome_panel(classification: pd.DataFrame) -> pd.DataFrame:
    bins = pd.read_csv(IMPORT_BIN_DECOMP)
    required = {
        "country",
        "iso3",
        "reporter_code",
        "year",
        "import_bin",
        "total_imports",
        "total_product_gini",
        "product_gini_without_bin",
        "active_products_without_bin",
        "total_imports_without_bin",
        "top_5_product_share_without_bin",
    }
    missing = sorted(required - set(bins.columns))
    if missing:
        raise RuntimeError(f"Import-bin decomposition missing columns: {missing}")
    keep_iso = set(classification["iso3"])
    panel = bins[
        bins["import_bin"].eq("energy")
        & bins["iso3"].astype(str).str.upper().isin(keep_iso)
        & bins["year"].between(FULL_START_YEAR, FULL_END_YEAR)
    ].copy()
    panel["iso3"] = panel["iso3"].astype(str).str.upper()
    panel["year"] = pd.to_numeric(panel["year"], errors="coerce").astype(int)
    validate_unique(panel, ["iso3", "year"], "ex-energy import Gini panel")
    expected = len(keep_iso) * (FULL_END_YEAR - FULL_START_YEAR + 1)
    if len(panel) != expected:
        raise RuntimeError(f"Expected {expected} balanced rows, found {len(panel)}.")
    panel = panel.rename(
        columns={
            "total_product_gini": "with_energy_import_product_gini",
            "product_gini_without_bin": "ex_energy_import_product_gini",
            "active_products_without_bin": "active_nonenergy_import_products",
            "total_imports_without_bin": "nonenergy_import_value",
            "top_5_product_share_without_bin": "top5_share_ex_energy",
        }
    )
    panel = panel[
        [
            "country",
            "iso3",
            "reporter_code",
            "year",
            "ex_energy_import_product_gini",
            "with_energy_import_product_gini",
            "active_nonenergy_import_products",
            "top5_share_ex_energy",
            "nonenergy_import_value",
            "total_imports",
        ]
    ].copy()
    return panel


def read_controls(iso3s: Iterable[str]) -> pd.DataFrame:
    iso3s = sorted(set(str(x).upper() for x in iso3s))
    base = pd.DataFrame(
        [(iso3, year) for iso3 in iso3s for year in range(FULL_START_YEAR, FULL_END_YEAR + 1)],
        columns=["iso3", "year"],
    )
    ppp = pd.read_csv(PPP_CONTROLS)
    ppp["iso3"] = ppp["iso3"].astype(str).str.upper()
    controls = base.merge(ppp[["iso3", "year", "gdp_pc_ppp_constant_2021_intl_usd"]], on=["iso3", "year"], how="left")
    if WDI_BASE_CONTROLS.exists():
        wdi_base = pd.read_csv(WDI_BASE_CONTROLS)
        wdi_base["iso3"] = wdi_base["iso3"].astype(str).str.upper()
        controls = controls.merge(
            wdi_base[["iso3", "year", "population", "gdp_current_usd"]],
            on=["iso3", "year"],
            how="left",
        )
    if WDI_GVC_CONTROLS.exists():
        wdi = pd.read_csv(WDI_GVC_CONTROLS)
        wdi["iso3"] = wdi["iso3"].astype(str).str.upper()
        controls = controls.merge(
            wdi[
                [
                    "iso3",
                    "year",
                    "trade_openness_pct_gdp",
                    "exports_goods_services_pct_gdp",
                    "imports_goods_services_pct_gdp",
                    "applied_tariff_weighted_mean_pct",
                ]
            ],
            on=["iso3", "year"],
            how="left",
        )
    validate_unique(controls, ["iso3", "year"], "WDI controls")
    controls["log_gdp_pc_ppp"] = safe_log(controls["gdp_pc_ppp_constant_2021_intl_usd"])
    controls["log_population"] = safe_log(controls["population"])
    controls["trade_openness_share_gdp"] = pd.to_numeric(controls["trade_openness_pct_gdp"], errors="coerce") / 100
    controls["imports_goods_services_share_gdp"] = (
        pd.to_numeric(controls["imports_goods_services_pct_gdp"], errors="coerce") / 100
    )
    controls["exports_goods_services_share_gdp"] = (
        pd.to_numeric(controls["exports_goods_services_pct_gdp"], errors="coerce") / 100
    )
    return controls


def read_jlop() -> pd.DataFrame:
    ensure_raw()
    df = pd.read_stata(JLOP_DTA, convert_categoricals=False)
    required = {
        "MeasureID",
        "AnnouncedYear",
        "CountryImposing_cleaned",
        "D_IP_bert_3",
        "MeasureAffectedProducts",
        "MAST_chapterName",
        "MeasureType",
        "firm_specific",
        "ImplementationLevel",
        "same_year_published",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise RuntimeError(f"JLOP dataset missing columns: {missing}")
    df["AnnouncedYear"] = pd.to_numeric(df["AnnouncedYear"], errors="coerce").astype("Int64")
    df = df.dropna(subset=["AnnouncedYear"]).copy()
    df["AnnouncedYear"] = df["AnnouncedYear"].astype(int)
    df["is_ip"] = pd.to_numeric(df["D_IP_bert_3"], errors="coerce").fillna(0).eq(1)
    df["same_year_published"] = pd.to_numeric(df["same_year_published"], errors="coerce").fillna(0).eq(1)
    df["firm_specific_flag"] = pd.to_numeric(df["firm_specific"], errors="coerce").fillna(0).eq(1)
    df["has_affected_products"] = df["MeasureAffectedProducts"].notna() & df["MeasureAffectedProducts"].astype(str).str.strip().ne("")
    df["is_import_substitution_ip"] = df["is_ip"] & (
        df["MAST_chapterName"].isin(PROTECTION_CHAPTERS)
        | df["MeasureType"].map(lambda x: contains_any(x, IMPORT_SUB_MEASURE_PATTERNS))
    )
    df["is_export_promotion_ip"] = df["is_ip"] & (
        df["MAST_chapterName"].eq("Export-related measures")
        | df["MeasureType"].map(lambda x: contains_any(x, EXPORT_PROMO_PATTERNS))
    )
    df["is_subsidy_ip"] = df["is_ip"] & (
        df["MAST_chapterName"].eq("Subsidies (excluding export subsidies)")
        | df["MeasureType"].map(lambda x: contains_any(x, SUBSIDY_PATTERNS))
    )
    return df


def expand_jlop_to_rd2(jlop: pd.DataFrame, classification: pd.DataFrame, include_eu: bool) -> tuple[pd.DataFrame, pd.DataFrame]:
    country_map = dict(zip(classification["country"], classification["iso3"]))
    country_map.update(
        {
            "United States of America": "USA",
            "Republic of Korea": "KOR",
            "Hong Kong": "HKG",
            "Czechia": "CZE",
        }
    )
    rows: list[dict[str, object]] = []
    unmatched: list[dict[str, object]] = []
    time_series = jlop[jlop["same_year_published"] & jlop["AnnouncedYear"].between(START_YEAR, END_YEAR)].copy()
    for r in time_series.itertuples(index=False):
        tokens = split_country_tokens(getattr(r, "CountryImposing_cleaned"))
        matched_iso3s: set[str] = set()
        for token in tokens:
            iso3s = token_to_iso(token, int(getattr(r, "AnnouncedYear")), country_map, include_eu)
            if not iso3s:
                unmatched.append(
                    {
                        "scenario": "eu_allocated" if include_eu else "direct_named_only",
                        "country_token": token,
                        "country_imposing_cleaned": getattr(r, "CountryImposing_cleaned"),
                        "year": int(getattr(r, "AnnouncedYear")),
                        "measure_id": getattr(r, "MeasureID"),
                    }
                )
            matched_iso3s.update(iso3s)
        for iso3 in sorted(matched_iso3s):
            rows.append(
                {
                    "scenario": "eu_allocated" if include_eu else "direct_named_only",
                    "iso3": iso3,
                    "year": int(getattr(r, "AnnouncedYear")),
                    "measure_id": getattr(r, "MeasureID"),
                    "is_ip": bool(getattr(r, "is_ip")),
                    "is_import_substitution_ip": bool(getattr(r, "is_import_substitution_ip")),
                    "is_export_promotion_ip": bool(getattr(r, "is_export_promotion_ip")),
                    "is_subsidy_ip": bool(getattr(r, "is_subsidy_ip")),
                    "firm_specific_flag": bool(getattr(r, "firm_specific_flag")),
                    "has_affected_products": bool(getattr(r, "has_affected_products")),
                    "mast_chapter": getattr(r, "MAST_chapterName"),
                    "measure_type": getattr(r, "MeasureType"),
                }
            )
    expanded = pd.DataFrame(rows)
    unmatched_df = pd.DataFrame(unmatched).drop_duplicates() if unmatched else pd.DataFrame()
    return expanded, unmatched_df


def aggregate_policy_panel(expanded: pd.DataFrame, classification: pd.DataFrame, scenario: str) -> pd.DataFrame:
    base = pd.DataFrame(
        [(iso3, year) for iso3 in sorted(classification["iso3"]) for year in range(START_YEAR, END_YEAR + 1)],
        columns=["iso3", "year"],
    )
    base["scenario"] = scenario
    if expanded.empty:
        agg = base.copy()
        for col in [
            "all_policy_measures",
            "all_ip_measures",
            "import_substitution_ip_measures",
            "export_promotion_ip_measures",
            "subsidy_ip_measures",
            "firm_specific_ip_measures",
            "product_targeted_ip_measures",
        ]:
            agg[col] = 0
        return agg
    grouped = (
        expanded.groupby(["scenario", "iso3", "year"], as_index=False)
        .agg(
            all_policy_measures=("measure_id", "nunique"),
            all_ip_measures=("is_ip", "sum"),
            import_substitution_ip_measures=("is_import_substitution_ip", "sum"),
            export_promotion_ip_measures=("is_export_promotion_ip", "sum"),
            subsidy_ip_measures=("is_subsidy_ip", "sum"),
            firm_specific_ip_measures=("firm_specific_flag", "sum"),
            product_targeted_ip_measures=("has_affected_products", "sum"),
        )
        .copy()
    )
    agg = base.merge(grouped, on=["scenario", "iso3", "year"], how="left")
    count_cols = [c for c in agg.columns if c.endswith("_measures")]
    agg[count_cols] = agg[count_cols].fillna(0).astype(int)
    return agg


def add_policy_transforms(panel: pd.DataFrame) -> pd.DataFrame:
    panel = panel.sort_values(["scenario", "iso3", "year"]).copy()
    count_cols = [
        "all_ip_measures",
        "import_substitution_ip_measures",
        "export_promotion_ip_measures",
        "subsidy_ip_measures",
        "firm_specific_ip_measures",
        "product_targeted_ip_measures",
    ]
    for col in count_cols:
        panel[f"log1p_{col}"] = np.log1p(panel[col])
        panel[f"{col}_l1"] = panel.groupby(["scenario", "iso3"])[col].shift(1)
        panel[f"log1p_{col}_l1"] = np.log1p(panel[f"{col}_l1"])
        panel[f"cum_{col}"] = panel.groupby(["scenario", "iso3"])[col].cumsum()
        panel[f"cum_{col}_pre"] = panel.groupby(["scenario", "iso3"])[f"cum_{col}"].shift(1)
        panel[f"log1p_cum_{col}_pre"] = np.log1p(panel[f"cum_{col}_pre"])
    panel["import_substitution_share_ip"] = np.where(
        panel["all_ip_measures"] > 0,
        panel["import_substitution_ip_measures"] / panel["all_ip_measures"],
        0.0,
    )
    panel["import_substitution_share_ip_l1"] = panel.groupby(["scenario", "iso3"])[
        "import_substitution_share_ip"
    ].shift(1)
    return panel


def build_analysis_panel() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    classification = read_classification()
    outcome = read_outcome_panel(classification)
    controls = read_controls(classification["iso3"])
    jlop = read_jlop()
    expanded_frames = []
    unmatched_frames = []
    for include_eu in [False, True]:
        expanded, unmatched = expand_jlop_to_rd2(jlop, classification, include_eu=include_eu)
        scenario = "eu_allocated" if include_eu else "direct_named_only"
        expanded_frames.append(expanded)
        if not unmatched.empty:
            unmatched_frames.append(unmatched)
    expanded_all = pd.concat(expanded_frames, ignore_index=True) if expanded_frames else pd.DataFrame()
    unmatched_all = pd.concat(unmatched_frames, ignore_index=True) if unmatched_frames else pd.DataFrame()
    policy_panels = [
        aggregate_policy_panel(expanded_all[expanded_all["scenario"].eq(scenario)], classification, scenario)
        for scenario in ["direct_named_only", "eu_allocated"]
    ]
    policy = pd.concat(policy_panels, ignore_index=True)
    policy = add_policy_transforms(policy)
    panel = (
        policy.merge(outcome, on=["iso3", "year"], how="left", validate="many_to_one")
        .merge(controls, on=["iso3", "year"], how="left", validate="many_to_one")
        .merge(classification[["iso3", "country", "reporter_code"]], on="iso3", how="left", suffixes=("", "_class"))
    )
    panel["delta_ex_energy_import_product_gini"] = panel.groupby(["scenario", "iso3"])[
        "ex_energy_import_product_gini"
    ].diff()
    panel["delta_log_gdp_pc_ppp"] = panel.groupby(["scenario", "iso3"])["log_gdp_pc_ppp"].diff()
    panel["delta_trade_openness_share_gdp"] = panel.groupby(["scenario", "iso3"])[
        "trade_openness_share_gdp"
    ].diff()
    panel["delta_imports_goods_services_share_gdp"] = panel.groupby(["scenario", "iso3"])[
        "imports_goods_services_share_gdp"
    ].diff()
    validate_unique(panel, ["scenario", "iso3", "year"], "analysis panel")
    return panel, expanded_all, unmatched_all, classification


def fit_model(df: pd.DataFrame, spec: ModelSpec) -> tuple[object, pd.DataFrame, dict[str, object]]:
    cols = sorted(
        set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", spec.formula))
        - {"C"}
    )
    use_cols = [c for c in cols if c in df.columns]
    sample = df.dropna(subset=use_cols).copy()
    if sample.empty:
        raise RuntimeError(f"{spec.model_id} has empty sample after dropping missing values.")
    model = smf.ols(spec.formula, data=sample)
    if spec.covariance == "cluster_iso3":
        fit = model.fit(cov_type="cluster", cov_kwds={"groups": sample["iso3"]})
    elif spec.covariance == "HC3":
        fit = model.fit(cov_type="HC3")
    else:
        fit = model.fit()
    term_rows = []
    for term in spec.terms:
        if term not in fit.params.index:
            continue
        term_rows.append(
            {
                "model_id": spec.model_id,
                "term": term,
                "coef": fit.params[term],
                "std_error": fit.bse[term],
                "p_value": fit.pvalues[term],
                "nobs": int(fit.nobs),
                "r2": fit.rsquared,
                "clusters": int(sample["iso3"].nunique()) if spec.covariance == "cluster_iso3" else np.nan,
                "covariance": spec.covariance,
                "hypothesis": spec.hypothesis,
                "dataset": spec.dataset,
            }
        )
    summary = {
        "model_id": spec.model_id,
        "hypothesis": spec.hypothesis,
        "dataset": spec.dataset,
        "formula": spec.formula,
        "nobs": int(fit.nobs),
        "countries": int(sample["iso3"].nunique()) if "iso3" in sample else np.nan,
        "r2": fit.rsquared,
        "covariance": spec.covariance,
        "sample_year_min": int(sample["year"].min()) if "year" in sample else np.nan,
        "sample_year_max": int(sample["year"].max()) if "year" in sample else np.nan,
    }
    return fit, pd.DataFrame(term_rows), summary


def build_change_panel(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    direct = panel[panel["scenario"].eq("direct_named_only")].copy()
    for iso3, sub in direct.groupby("iso3"):
        sub = sub.sort_values("year")
        first = sub[sub["year"].eq(START_YEAR)].iloc[0]
        last = sub[sub["year"].eq(END_YEAR)].iloc[0]
        rows.append(
            {
                "iso3": iso3,
                "country": first["country"],
                "delta_ex_energy_import_product_gini_2010_2022": last["ex_energy_import_product_gini"]
                - first["ex_energy_import_product_gini"],
                "start_ex_energy_import_product_gini_2010": first["ex_energy_import_product_gini"],
                "cum_import_substitution_ip_2010_2022": sub["import_substitution_ip_measures"].sum(),
                "cum_export_promotion_ip_2010_2022": sub["export_promotion_ip_measures"].sum(),
                "cum_all_ip_2010_2022": sub["all_ip_measures"].sum(),
                "cum_subsidy_ip_2010_2022": sub["subsidy_ip_measures"].sum(),
                "log1p_cum_import_substitution_ip_2010_2022": np.log1p(
                    sub["import_substitution_ip_measures"].sum()
                ),
                "log1p_cum_export_promotion_ip_2010_2022": np.log1p(sub["export_promotion_ip_measures"].sum()),
                "log1p_cum_all_ip_2010_2022": np.log1p(sub["all_ip_measures"].sum()),
                "log_gdp_pc_ppp_2010": first["log_gdp_pc_ppp"],
                "delta_log_gdp_pc_ppp_2010_2022": last["log_gdp_pc_ppp"] - first["log_gdp_pc_ppp"],
                "log_population_2010": first["log_population"],
                "delta_trade_openness_share_gdp_2010_2022": last["trade_openness_share_gdp"]
                - first["trade_openness_share_gdp"],
                "delta_imports_goods_services_share_gdp_2010_2022": last["imports_goods_services_share_gdp"]
                - first["imports_goods_services_share_gdp"],
            }
        )
    out = pd.DataFrame(rows)
    validate_unique(out, ["iso3"], "country change panel")
    return out


def model_specs() -> list[ModelSpec]:
    return [
        ModelSpec(
            model_id="m1_pooled_year_fe_direct",
            hypothesis="Countries/years with more lagged import-substitution IP have higher import concentration after common-year shocks and controls.",
            dataset="direct_named_only policy exposure, 2011-2022 country-year panel",
            formula=(
                "ex_energy_import_product_gini ~ log1p_import_substitution_ip_measures_l1 "
                "+ log1p_export_promotion_ip_measures_l1 + log_gdp_pc_ppp + log_population "
                "+ trade_openness_share_gdp + imports_goods_services_share_gdp + C(year)"
            ),
            terms=("log1p_import_substitution_ip_measures_l1", "log1p_export_promotion_ip_measures_l1"),
            covariance="cluster_iso3",
        ),
        ModelSpec(
            model_id="m2_country_year_fe_direct",
            hypothesis="Within the same country, lagged import-substitution IP is associated with higher import concentration.",
            dataset="direct_named_only policy exposure, 2011-2022 country-year panel",
            formula=(
                "ex_energy_import_product_gini ~ log1p_import_substitution_ip_measures_l1 "
                "+ log1p_export_promotion_ip_measures_l1 + log_gdp_pc_ppp + log_population "
                "+ trade_openness_share_gdp + imports_goods_services_share_gdp + C(year) + C(iso3)"
            ),
            terms=("log1p_import_substitution_ip_measures_l1", "log1p_export_promotion_ip_measures_l1"),
            covariance="cluster_iso3",
        ),
        ModelSpec(
            model_id="m3_change_country_year_fe_direct",
            hypothesis="Lagged import-substitution IP predicts year-to-year increases in import concentration within country.",
            dataset="direct_named_only policy exposure, 2011-2022 first-difference panel",
            formula=(
                "delta_ex_energy_import_product_gini ~ log1p_import_substitution_ip_measures_l1 "
                "+ log1p_export_promotion_ip_measures_l1 + delta_log_gdp_pc_ppp "
                "+ delta_trade_openness_share_gdp + delta_imports_goods_services_share_gdp "
                "+ C(year) + C(iso3)"
            ),
            terms=("log1p_import_substitution_ip_measures_l1", "log1p_export_promotion_ip_measures_l1"),
            covariance="cluster_iso3",
        ),
        ModelSpec(
            model_id="m4_all_ip_and_share_direct",
            hypothesis="The import-substitution share of IP, not only the count of IP measures, is associated with concentration.",
            dataset="direct_named_only policy exposure, 2011-2022 country-year panel",
            formula=(
                "ex_energy_import_product_gini ~ log1p_all_ip_measures_l1 "
                "+ import_substitution_share_ip_l1 + log_gdp_pc_ppp + log_population "
                "+ trade_openness_share_gdp + imports_goods_services_share_gdp + C(year) + C(iso3)"
            ),
            terms=("log1p_all_ip_measures_l1", "import_substitution_share_ip_l1"),
            covariance="cluster_iso3",
        ),
        ModelSpec(
            model_id="m5_country_year_fe_eu_allocated",
            hypothesis="The within-country result changes if EU/EC supranational measures are assigned to rd2 EU members.",
            dataset="EU/EC allocated policy exposure, 2011-2022 country-year panel",
            formula=(
                "ex_energy_import_product_gini ~ log1p_import_substitution_ip_measures_l1 "
                "+ log1p_export_promotion_ip_measures_l1 + log_gdp_pc_ppp + log_population "
                "+ trade_openness_share_gdp + imports_goods_services_share_gdp + C(year) + C(iso3)"
            ),
            terms=("log1p_import_substitution_ip_measures_l1", "log1p_export_promotion_ip_measures_l1"),
            covariance="cluster_iso3",
        ),
        ModelSpec(
            model_id="m6_country_change_direct",
            hypothesis="Countries with more cumulative import-substitution IP over 2010-2022 experienced larger import-Gini changes.",
            dataset="direct_named_only 2010-2022 country-change cross-section",
            formula=(
                "delta_ex_energy_import_product_gini_2010_2022 ~ log1p_cum_import_substitution_ip_2010_2022 "
                "+ log1p_cum_export_promotion_ip_2010_2022 + start_ex_energy_import_product_gini_2010 "
                "+ log_gdp_pc_ppp_2010 + delta_log_gdp_pc_ppp_2010_2022 + log_population_2010 "
                "+ delta_trade_openness_share_gdp_2010_2022 + delta_imports_goods_services_share_gdp_2010_2022"
            ),
            terms=(
                "log1p_cum_import_substitution_ip_2010_2022",
                "log1p_cum_export_promotion_ip_2010_2022",
            ),
            covariance="HC3",
        ),
    ]


def p_text(p: float) -> str:
    if pd.isna(p):
        return ""
    if p < 0.001:
        return "<0.001"
    return f"{p:.3f}"


def fmt(value: object, digits: int = 4) -> str:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(x):
        return ""
    return f"{x:.{digits}f}"


def pct(value: object, digits: int = 1) -> str:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(x):
        return ""
    return f"{100 * x:.{digits}f}%"


def md_table(rows: list[list[str]], headers: list[str]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(x) for x in row) + " |")
    return "\n".join(out)


def bold_if_sig(text: str, p: object) -> str:
    try:
        pval = float(p)
    except (TypeError, ValueError):
        return text
    if math.isfinite(pval) and pval < 0.05:
        return f"**{text}**"
    return text


def write_outputs(
    panel: pd.DataFrame,
    expanded: pd.DataFrame,
    unmatched: pd.DataFrame,
    change: pd.DataFrame,
    summaries: list[dict[str, object]],
    terms: pd.DataFrame,
) -> None:
    panel.to_csv(OUT_DIR / "industrial_policy_import_gini_panel.csv", index=False)
    expanded.to_csv(OUT_DIR / "jl_industrial_policy_expanded_rd2_country_year.csv", index=False)
    if unmatched.empty:
        pd.DataFrame(columns=["scenario", "country_token", "country_imposing_cleaned", "year", "measure_id"]).to_csv(
            OUT_DIR / "unmatched_policy_country_tokens.csv", index=False
        )
    else:
        unmatched.to_csv(OUT_DIR / "unmatched_policy_country_tokens.csv", index=False)
    change.to_csv(OUT_DIR / "country_change_policy_exposure_2010_2022.csv", index=False)
    pd.DataFrame(summaries).to_csv(OUT_DIR / "model_summary.csv", index=False)
    terms.to_csv(OUT_DIR / "regression_terms.csv", index=False)

    count_summary = (
        panel.groupby("scenario", as_index=False)
        .agg(
            rows=("iso3", "size"),
            countries=("iso3", "nunique"),
            years=("year", "nunique"),
            total_ip=("all_ip_measures", "sum"),
            total_import_substitution_ip=("import_substitution_ip_measures", "sum"),
            total_export_promotion_ip=("export_promotion_ip_measures", "sum"),
            total_subsidy_ip=("subsidy_ip_measures", "sum"),
            country_years_with_import_substitution_ip=("import_substitution_ip_measures", lambda x: int((x > 0).sum())),
        )
    )
    count_summary.to_csv(OUT_DIR / "policy_exposure_summary.csv", index=False)

    plot_terms = terms[
        terms["term"].isin(
            [
                "log1p_import_substitution_ip_measures_l1",
                "log1p_export_promotion_ip_measures_l1",
                "import_substitution_share_ip_l1",
                "log1p_cum_import_substitution_ip_2010_2022",
                "log1p_cum_export_promotion_ip_2010_2022",
            ]
        )
    ].copy()
    if not plot_terms.empty:
        plot_terms["label"] = plot_terms["model_id"] + "\n" + plot_terms["term"].str.replace("_", " ")
        y = np.arange(len(plot_terms))
        fig, ax = plt.subplots(figsize=(9, max(4, len(plot_terms) * 0.42)))
        ax.errorbar(
            plot_terms["coef"],
            y,
            xerr=1.96 * plot_terms["std_error"],
            fmt="o",
            color="#275f91",
            ecolor="#8faeca",
            capsize=3,
        )
        ax.axvline(0, color="#333333", linewidth=1)
        ax.set_yticks(y)
        ax.set_yticklabels(plot_terms["label"], fontsize=8)
        ax.set_xlabel("Coefficient with 95% CI")
        ax.set_title("Industrial-policy exposure and ex-energy import Product Gini")
        fig.tight_layout()
        fig.savefig(FIG_DIR / "industrial_policy_import_gini_coefficients.png", dpi=180)
        plt.close(fig)

    write_memo(panel, expanded, unmatched, change, count_summary, pd.DataFrame(summaries), terms)
    write_adversarial_review(panel, expanded, unmatched, terms)


def write_memo(
    panel: pd.DataFrame,
    expanded: pd.DataFrame,
    unmatched: pd.DataFrame,
    change: pd.DataFrame,
    count_summary: pd.DataFrame,
    summaries: pd.DataFrame,
    terms: pd.DataFrame,
) -> None:
    direct = panel[panel["scenario"].eq("direct_named_only")].copy()
    first = direct[direct["year"].eq(START_YEAR)]
    last = direct[direct["year"].eq(END_YEAR)]
    median_change = last.set_index("iso3")["ex_energy_import_product_gini"].subtract(
        first.set_index("iso3")["ex_energy_import_product_gini"], fill_value=np.nan
    ).median()
    direct_sorted = direct.sort_values(["iso3", "year"]).copy()
    median_abs_annual_move = (
        direct_sorted.groupby("iso3")["ex_energy_import_product_gini"].diff().abs().median()
    )
    share_term = terms[
        terms["model_id"].eq("m4_all_ip_and_share_direct")
        & terms["term"].eq("import_substitution_share_ip_l1")
    ].iloc[0]
    preferred_count_term = terms[
        terms["model_id"].eq("m2_country_year_fe_direct")
        & terms["term"].eq("log1p_import_substitution_ip_measures_l1")
    ].iloc[0]
    share_coef = float(share_term["coef"])
    preferred_count_coef = float(preferred_count_term["coef"])
    effect_size_rows = [
        [
            "Significant share coefficient",
            "100 percentage-point increase in import-substitution share of IP",
            fmt(share_coef, 5),
            p_text(float(share_term["p_value"])),
        ],
        [
            "Significant share coefficient",
            "10 percentage-point increase",
            fmt(share_coef * 0.10, 5),
            p_text(float(share_term["p_value"])),
        ],
        [
            "Significant share coefficient",
            "25 percentage-point increase",
            fmt(share_coef * 0.25, 5),
            p_text(float(share_term["p_value"])),
        ],
        [
            "Preferred count coefficient",
            "0 to 1 lagged import-substitution IP measure",
            fmt(preferred_count_coef * np.log(2), 5),
            p_text(float(preferred_count_term["p_value"])),
        ],
        [
            "Preferred count coefficient",
            "0 to 10 lagged import-substitution IP measures",
            fmt(preferred_count_coef * np.log(11), 5),
            p_text(float(preferred_count_term["p_value"])),
        ],
    ]
    count_rows = []
    for r in count_summary.itertuples(index=False):
        count_rows.append(
            [
                r.scenario,
                f"{int(r.countries)}",
                f"{int(r.years)}",
                f"{int(r.total_ip):,}",
                f"{int(r.total_import_substitution_ip):,}",
                f"{int(r.total_export_promotion_ip):,}",
                f"{int(r.country_years_with_import_substitution_ip):,}",
            ]
        )
    term_rows = []
    term_labels = {
        "log1p_import_substitution_ip_measures_l1": "Lagged import-substitution IP count, log(1+x)",
        "log1p_export_promotion_ip_measures_l1": "Lagged export-promotion IP count, log(1+x)",
        "import_substitution_share_ip_l1": "Lagged import-substitution share of IP",
        "log1p_all_ip_measures_l1": "Lagged all-IP count, log(1+x)",
        "log1p_cum_import_substitution_ip_2010_2022": "Cumulative import-substitution IP, log(1+x)",
        "log1p_cum_export_promotion_ip_2010_2022": "Cumulative export-promotion IP, log(1+x)",
    }
    for r in terms.itertuples(index=False):
        term_rows.append(
            [
                r.model_id,
                term_labels.get(r.term, r.term),
                bold_if_sig(fmt(r.coef, 4), r.p_value),
                fmt(r.std_error, 4),
                bold_if_sig(p_text(r.p_value), r.p_value),
                f"{int(r.nobs):,}",
                "" if pd.isna(r.clusters) else f"{int(r.clusters):,}",
            ]
        )
    model_rows = []
    for r in summaries.itertuples(index=False):
        model_rows.append(
            [
                r.model_id,
                r.dataset,
                f"{int(r.nobs):,}",
                f"{int(r.countries):,}" if not pd.isna(r.countries) else "",
                fmt(r.r2, 3),
                r.covariance,
            ]
        )
    top_country_rows = []
    for r in change.sort_values("cum_import_substitution_ip_2010_2022", ascending=False).head(12).itertuples(index=False):
        top_country_rows.append(
            [
                r.country,
                r.iso3,
                f"{int(r.cum_import_substitution_ip_2010_2022):,}",
                f"{int(r.cum_export_promotion_ip_2010_2022):,}",
                fmt(r.delta_ex_energy_import_product_gini_2010_2022, 4),
            ]
        )
    text = f"""# Industrial Policy and Import Product Gini

Generated: {now_utc()}

## Question

Can the energy-excluded import Product Gini be explained by globalization/outsourcing, or by countries trying to import-substitute through industrial policy?

## Short Answer

The JLOP industrial-policy data are useful for this question, but they do **not** produce a clean positive import-substitution story in the rd2 panel. In the preferred country/year fixed-effect specification, lagged import-substitution/protective industrial-policy counts are not statistically significant for the level of ex-energy import Product Gini. The first-difference and 2010-2022 country-change specifications also do not support the count-based import-substitution story. The one positive signal is narrower: when the model uses the **share** of lagged IP measures that are import-substitution-like, that share is positive and statistically significant.

The safer interpretation is: import concentration is more plausibly tied to globalization/import-basket structure, hub activity, and sectoral supply-chain specialization than to the observed 2010-2022 count of import-substitution industrial-policy interventions.

## Data

- Outcome: rd2 country-year ex-energy import Product Gini, 2010-2022 subset of the 2000-2024 balanced panel.
- Product rule: HS6 `999999` is excluded upstream; the Exercise 3 energy bin is removed before the product Gini outcome.
- Industrial-policy source: Juhasz, Lane, Oehlsen, and Perez `JLOP_2025.dta`, downloaded from the authors' GitHub replication repository.
- Time-series filter: `same_year_published == 1`, following the dataset README warning about GTA backfilling.
- Main IP exposure: country-year count of BERT-labelled IP measures classified as tariffs, contingent protection, import licensing/quotas/bans, local-content/local-value-added rules, procurement localization, or related trade-investment restrictions.
- Globalization proxy: WDI trade openness and imports of goods/services as a share of GDP.

## Measurement Choices

`import_substitution_ip_measures` is not a perfect import-substitution index. It is a count of policy interventions whose instruments look protective, localizing, or import-restricting. That misses informal industrial strategy and cannot measure firms' outsourcing decisions directly. It is still a defensible first pass because it is country-year, globally comparable, and instrument-coded.

## Policy Exposure Coverage

{md_table(count_rows, ["Scenario", "Countries", "Years", "All IP", "Import-sub IP", "Export-promotion IP", "Country-years with import-sub IP"])}

The main scenario counts only countries explicitly named by the policy row. The EU sensitivity also assigns EU/EC measures to rd2 EU members, with the UK included through 2019.

## Model Inventory

{md_table(model_rows, ["Model", "Dataset", "N", "Countries", "R2", "SE"])}

## Main Regression Terms

{md_table(term_rows, ["Model", "Term", "Coef", "SE", "p", "N", "Clusters"])}

## How Big Is The Coefficient?

The only statistically significant term is the lagged import-substitution **share** of all IP measures, not the count of import-substitution measures. Its coefficient is {fmt(share_coef, 5)}. Since the regressor is a 0-to-1 share, a 10 percentage-point increase predicts only {fmt(share_coef * 0.10, 5)} more Gini and a 25 percentage-point increase predicts {fmt(share_coef * 0.25, 5)} more Gini.

For scale, the median absolute year-to-year movement in ex-energy import Product Gini is {fmt(median_abs_annual_move, 5)}, and the median 2010-2022 country change is {fmt(median_change, 5)}. So a 10 percentage-point shift in the import-substitution share is small: about {pct((share_coef * 0.10) / median_abs_annual_move)} of a typical annual move and {pct((share_coef * 0.10) / median_change)} of the median 2010-2022 change.

{md_table(effect_size_rows, ["Coefficient", "Interpretation", "Predicted Gini Change", "p"])}

## Countries With Most Import-Substitution IP Exposure

{md_table(top_country_rows, ["Country", "ISO3", "Cumulative import-sub IP", "Cumulative export-promotion IP", "Delta Gini 2010-2022"])}

## Interpretation

- **Globalization/outsourcing:** The regressions control for trade openness and import share of GDP, but those are proxies, not direct outsourcing measures. They capture how internationally exposed the economy is, not whether firms are offshoring specific production stages.
- **Import substitution:** The evidence is not consistent with a simple positive association between the count of import-substitution IP measures and import Product Gini. The one supportive result is that the lagged import-substitution share of all IP is positive in one country/year-FE specification; treat that as a clue, not a settled mechanism.
- **Industrial policy in rich countries:** The JLOP paper itself reports that modern IP is often subsidies and export promotion, not tariffs. That matters here: much observed IP may target established comparative advantage or export capacity rather than replacing imports.
- **Best theory fit:** import concentration can rise from specialized supply-chain inputs, gold/valuation channels, pharma/electronics scale, and hubs even when the country is not trying to substitute imports.

## What Would Convince Me More

1. Product-level matching: whether IP-targeted HS6 products are the same products driving import Gini.
2. Leave-one-sector checks: remove gold, pharma, aircraft, electronics, and autos.
3. A direct GVC/outsourcing dataset: OECD TiVA or UNCTAD-Eora backward GVC participation, where coverage permits.
4. Policy timing tests around big discrete policy packages rather than annual counts.
5. Separate domestic-absorption from re-export/vaulting/free-zone flows for hubs.

## Bottom Line For The Paper

Use this as a negative/disciplining result: the broad import-concentration pattern is not well explained by a simple import-substitution industrial-policy count. Do not claim industrial policy is irrelevant; claim that this particular observable IP measure does not explain the import-Gini pattern cleanly.
"""
    (OUT_DIR / "industrial_policy_import_gini.md").write_text(text, encoding="utf-8")


def write_adversarial_review(panel: pd.DataFrame, expanded: pd.DataFrame, unmatched: pd.DataFrame, terms: pd.DataFrame) -> None:
    direct = panel[panel["scenario"].eq("direct_named_only")]
    review = f"""# Adversarial Review: Industrial Policy and Import Gini

## Verdict

Usable as a descriptive screen, not as causal evidence.

This is a local adversarial review, not an independent fresh-agent pass. The active multi-agent tool only permits spawning when the user explicitly asks for sub-agents.

## Checks Passed

- Outcome panel is unique on `scenario-iso3-year`.
- Direct scenario rows: {len(direct):,}; countries: {direct['iso3'].nunique():,}; years: {direct['year'].nunique():,}.
- JLOP rows are filtered to `same_year_published == 1` for time-series comparability.
- Product-dependent outcome inherits upstream exclusion of HS6 `999999` and the Exercise 3 energy-bin exclusion.
- Standard errors are country clustered in panel regressions and HC3 in the 56-country change regression.

## Main Threats

1. The JLOP data measure policy announcements/interventions, not intensity, enforcement, or fiscal size.
2. Import substitution is inferred from instrument categories; this is not a direct government objective label.
3. EU-country exposure is undercounted in the direct scenario and mechanically common in the EU-allocated sensitivity.
4. Policy endogeneity is severe: governments may react to import concentration, trade shocks, crises, or lobbying.
5. The data cover 2010-2022, while the import-Gini story is often 2000-2024.
6. Outsourcing/globalization is proxied by openness/import share; a real GVC test needs TiVA/Eora-style input-output exposure.

## Highest-Risk Interpretation Error

Do not say “industrial policy has no effect.” The correct claim is narrower: this count-based JLOP import-substitution/protection exposure does not explain the rd2 import Product Gini pattern in a clean positive way.

## Terms With p < 0.05

{terms.loc[terms['p_value'].lt(0.05), ['model_id', 'term', 'coef', 'std_error', 'p_value', 'nobs']].to_markdown(index=False) if not terms.loc[terms['p_value'].lt(0.05)].empty else 'None.'}
"""
    (OUT_DIR / "adversarial_review.md").write_text(review, encoding="utf-8")


def main() -> None:
    ensure_dirs()
    panel, expanded, unmatched, _classification = build_analysis_panel()
    panel = panel[panel["year"].between(START_YEAR, END_YEAR)].copy()
    change = build_change_panel(panel)
    specs = model_specs()
    all_terms = []
    summaries = []
    for spec in specs:
        if spec.model_id.endswith("eu_allocated"):
            df = panel[panel["scenario"].eq("eu_allocated") & panel["year"].between(START_YEAR + 1, END_YEAR)].copy()
        elif spec.model_id == "m6_country_change_direct":
            df = change.copy()
        else:
            df = panel[panel["scenario"].eq("direct_named_only") & panel["year"].between(START_YEAR + 1, END_YEAR)].copy()
        _fit, terms, summary = fit_model(df, spec)
        all_terms.append(terms)
        summaries.append(summary)
    term_df = pd.concat(all_terms, ignore_index=True)
    write_outputs(panel, expanded, unmatched, change, summaries, term_df)
    print(OUT_DIR)


if __name__ == "__main__":
    main()
