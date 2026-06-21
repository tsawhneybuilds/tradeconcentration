#!/usr/bin/env python3
"""Descriptive regressions for ex-energy import Product Gini mechanisms.

The target outcome is the rd2 country-year import Product Gini after excluding
the project Exercise 3 energy basket. Product-facing calculations inherit the
upstream rule that HS6 999999 is not a real product category.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import statsmodels.formula.api as smf


ROOT = Path(__file__).resolve().parents[1]
COUNTRY_SAMPLE = "rd2_countries"
START_YEAR = 2000
END_YEAR = 2024
MID_YEAR = 2012

BASE = ROOT / "results" / "samples" / COUNTRY_SAMPLE
PROCESSED = ROOT / "data" / "processed" / "samples" / COUNTRY_SAMPLE
OUT_DIR = BASE / "import_gini_mechanism_regressions"
FIG_DIR = OUT_DIR / "figures"

CLASSIFICATION = (
    BASE
    / "import_energy_gini_diagnostics"
    / "ex_energy_rank_bucket_gini_driver_classification_balanced_2000_2024.csv"
)
IMPORT_BIN_DECOMP = BASE / "exercise_03_tables" / "import_bin_decomposition.csv"
PPP_CONTROLS = PROCESSED / "ppp_hump_world_bank_controls.csv"
PPP_SNAPSHOT = BASE / "ppp_hump_regression_tables" / "ppp_hump_controls_snapshot.csv"
WDI_EXPORT_CONTROLS = PROCESSED / "growth_effect_world_bank_export_controls.csv"
EXTRA_WDI_CACHE = PROCESSED / "import_gini_mechanism_world_bank_controls.csv"
MERCH_EXPORT_PANEL = PROCESSED / "exercise_02_export_concentration_panel.parquet"
US_DEFLATOR = PROCESSED / "future_growth_concentration_us_gdp_deflator.csv"
WDI_TARIFF_PANEL = EXTRA_WDI_CACHE
WITS_MARKET_ACCESS = PROCESSED / "primary_wits_hs4_2001_2021_tariff_coverage_pass_sample_reported.parquet"

WORLD_BANK_URL = "https://api.worldbank.org/v2/country/{countries}/indicator/{indicator}"
WDI_EXTRA_INDICATORS = {
    "trade_openness_pct_gdp": "NE.TRD.GNFS.ZS",
    "exports_goods_services_pct_gdp": "NE.EXP.GNFS.ZS",
    "imports_goods_services_pct_gdp": "NE.IMP.GNFS.ZS",
    "applied_tariff_weighted_mean_pct": "TM.TAX.MRCH.WM.AR.ZS",
    "applied_tariff_simple_mean_pct": "TM.TAX.MRCH.SM.AR.ZS",
}


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    family: str
    hypothesis: str
    outcome: str
    formula: str
    terms: tuple[str, ...]
    covariance: str
    sample_note: str


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def ensure_dirs() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)


def validate_unique(df: pd.DataFrame, keys: list[str], label: str) -> None:
    missing = sorted(set(keys) - set(df.columns))
    if missing:
        raise RuntimeError(f"{label} is missing required keys: {missing}")
    dupes = int(df.duplicated(keys).sum())
    if dupes:
        examples = df.loc[df.duplicated(keys, keep=False), keys].head(8).to_dict("records")
        raise RuntimeError(f"{label} has duplicate keys on {keys}: {examples}")


def finite_float(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x):
        return None
    return x


def read_classification() -> pd.DataFrame:
    df = pd.read_csv(CLASSIFICATION)
    required = {
        "country",
        "iso3",
        "reporter_code",
        "start_year",
        "end_year",
        "main_driver_group",
        "delta_panel_ex_energy_gini",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise RuntimeError(f"Classification is missing columns: {missing}")
    df["iso3"] = df["iso3"].astype(str).str.upper()
    if not df["start_year"].eq(START_YEAR).all() or not df["end_year"].eq(END_YEAR).all():
        raise RuntimeError("Classification is not the expected balanced 2000-2024 artifact.")
    validate_unique(df, ["iso3"], "balanced classification")
    return df.copy()


def read_ex_energy_outcome(classification: pd.DataFrame) -> pd.DataFrame:
    bins = pd.read_csv(IMPORT_BIN_DECOMP)
    required = {
        "country",
        "iso3",
        "reporter_code",
        "year",
        "import_bin",
        "total_imports",
        "product_gini_without_bin",
        "active_products_without_bin",
        "top_1_product_share_without_bin",
        "top_5_product_share_without_bin",
        "top_10_product_share_without_bin",
        "import_value_share",
    }
    missing = sorted(required - set(bins.columns))
    if missing:
        raise RuntimeError(f"Import-bin decomposition is missing columns: {missing}")
    keep_iso = set(classification["iso3"])
    out = bins[
        bins["iso3"].astype(str).str.upper().isin(keep_iso)
        & bins["year"].between(START_YEAR, END_YEAR)
        & bins["import_bin"].eq("energy")
    ].copy()
    out["iso3"] = out["iso3"].astype(str).str.upper()
    out["year"] = pd.to_numeric(out["year"], errors="coerce").astype(int)
    validate_unique(out, ["iso3", "year"], "ex-energy import outcome")
    expected_rows = len(keep_iso) * (END_YEAR - START_YEAR + 1)
    if len(out) != expected_rows:
        raise RuntimeError(f"Expected {expected_rows} balanced outcome rows, found {len(out)}.")
    counts = out.groupby("iso3")["year"].nunique()
    if not counts.eq(END_YEAR - START_YEAR + 1).all():
        raise RuntimeError(f"Unbalanced ex-energy outcome panel: {counts[counts.ne(25)].to_dict()}")
    out = out.rename(
        columns={
            "product_gini_without_bin": "import_product_gini_ex_energy",
            "active_products_without_bin": "active_products_ex_energy",
            "top_1_product_share_without_bin": "top1_share_ex_energy",
            "top_5_product_share_without_bin": "top5_share_ex_energy",
            "top_10_product_share_without_bin": "top10_share_ex_energy",
            "import_value_share": "energy_import_share",
        }
    )
    return out[
        [
            "country",
            "iso3",
            "reporter_code",
            "year",
            "total_imports",
            "import_product_gini_ex_energy",
            "active_products_ex_energy",
            "top1_share_ex_energy",
            "top5_share_ex_energy",
            "top10_share_ex_energy",
            "energy_import_share",
        ]
    ].copy()


def fetch_world_bank_indicator(
    iso3s: list[str],
    indicator: str,
    value_name: str,
    start_year: int,
    end_year: int,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    countries = ";".join(sorted(set(iso3s)))
    url = WORLD_BANK_URL.format(countries=countries, indicator=indicator)
    page = 1
    pages = 1
    while page <= pages:
        response = requests.get(
            url,
            params={"format": "json", "per_page": 20000, "page": page, "date": f"{start_year}:{end_year}"},
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list) or len(payload) < 2:
            break
        meta = payload[0] if isinstance(payload[0], dict) else {}
        pages = int(meta.get("pages") or pages)
        for item in payload[1]:
            iso3 = str(item.get("countryiso3code") or "").strip().upper()
            value = item.get("value")
            if iso3 and value is not None:
                rows.append({"iso3": iso3, "year": int(item["date"]), value_name: value})
        page += 1
        time.sleep(0.05)
    out = pd.DataFrame(rows, columns=["iso3", "year", value_name])
    if out.empty:
        return out
    out[value_name] = pd.to_numeric(out[value_name], errors="coerce")
    out["year"] = pd.to_numeric(out["year"], errors="coerce").astype("Int64")
    out = out.dropna(subset=["iso3", "year"]).copy()
    out["year"] = out["year"].astype(int)
    return out.drop_duplicates(["iso3", "year"], keep="last")


def load_or_fetch_extra_wdi(iso3s: list[str], refresh: bool = False) -> pd.DataFrame:
    base = pd.DataFrame(
        [(iso3, year) for iso3 in sorted(set(iso3s)) for year in range(START_YEAR, END_YEAR + 1)],
        columns=["iso3", "year"],
    )
    if EXTRA_WDI_CACHE.exists() and not refresh:
        cached = pd.read_csv(EXTRA_WDI_CACHE)
        needed = {"iso3", "year", *WDI_EXTRA_INDICATORS.keys()}
        if needed.issubset(cached.columns):
            cached["iso3"] = cached["iso3"].astype(str).str.upper()
            cached["year"] = pd.to_numeric(cached["year"], errors="coerce").astype(int)
            return cached[cached["iso3"].isin(iso3s) & cached["year"].between(START_YEAR, END_YEAR)].copy()
    out = base.copy()
    for value_name, indicator in WDI_EXTRA_INDICATORS.items():
        try:
            fetched = fetch_world_bank_indicator(iso3s, indicator, value_name, START_YEAR, END_YEAR)
        except Exception as exc:
            print(f"World Bank fetch warning for {indicator}: {exc}")
            fetched = pd.DataFrame(columns=["iso3", "year", value_name])
        out = out.merge(fetched[["iso3", "year", value_name]], on=["iso3", "year"], how="left")
    EXTRA_WDI_CACHE.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(EXTRA_WDI_CACHE, index=False)
    return out


def read_ppp_controls(iso3s: Iterable[str]) -> pd.DataFrame:
    ppp = pd.read_csv(PPP_CONTROLS)
    ppp["iso3"] = ppp["iso3"].astype(str).str.upper()
    ppp["year"] = pd.to_numeric(ppp["year"], errors="coerce").astype(int)
    ppp = ppp[ppp["iso3"].isin(set(iso3s)) & ppp["year"].between(START_YEAR, END_YEAR)].copy()
    validate_unique(ppp, ["iso3", "year"], "PPP GDP per capita controls")
    ppp["log_gdp_pc_ppp"] = np.where(
        ppp["gdp_pc_ppp_constant_2021_intl_usd"] > 0,
        np.log(ppp["gdp_pc_ppp_constant_2021_intl_usd"]),
        np.nan,
    )
    return ppp[["iso3", "year", "gdp_pc_ppp_constant_2021_intl_usd", "log_gdp_pc_ppp"]]


def read_population_oil_controls(iso3s: Iterable[str]) -> pd.DataFrame:
    controls = pd.read_csv(PPP_SNAPSHOT)
    controls["iso3"] = controls["iso3"].astype(str).str.upper()
    controls["year"] = pd.to_numeric(controls["year"], errors="coerce").astype(int)
    controls = controls[controls["iso3"].isin(set(iso3s)) & controls["year"].between(START_YEAR, END_YEAR)].copy()
    validate_unique(controls, ["iso3", "year"], "population/oil controls")
    return controls[["iso3", "year", "log_population", "oil_export_share"]]


def read_wdi_exports(iso3s: Iterable[str]) -> pd.DataFrame:
    exports = pd.read_csv(WDI_EXPORT_CONTROLS)
    exports["iso3"] = exports["iso3"].astype(str).str.upper()
    exports["year"] = pd.to_numeric(exports["year"], errors="coerce").astype(int)
    exports = exports[exports["iso3"].isin(set(iso3s)) & exports["year"].between(START_YEAR, END_YEAR)].copy()
    validate_unique(exports, ["iso3", "year"], "WDI real export controls")
    exports["log_real_exports"] = np.where(
        exports["real_exports_constant_2015_usd"] > 0,
        np.log(exports["real_exports_constant_2015_usd"]),
        np.nan,
    )
    return exports[["iso3", "year", "real_exports_constant_2015_usd", "log_real_exports", "population"]]


def read_merchandise_exports(iso3s: Iterable[str]) -> pd.DataFrame:
    exports = pd.read_parquet(MERCH_EXPORT_PANEL)
    exports = exports[
        exports["flow"].eq("Exports")
        & exports["iso3"].astype(str).str.upper().isin(set(iso3s))
        & exports["year"].between(START_YEAR, END_YEAR)
    ].copy()
    exports["iso3"] = exports["iso3"].astype(str).str.upper()
    exports["year"] = pd.to_numeric(exports["year"], errors="coerce").astype(int)
    validate_unique(exports, ["iso3", "year"], "Comtrade merchandise export controls")
    deflator = pd.read_csv(US_DEFLATOR)
    deflator["year"] = pd.to_numeric(deflator["year"], errors="coerce").astype(int)
    deflator["us_gdp_deflator"] = pd.to_numeric(deflator["us_gdp_deflator"], errors="coerce")
    validate_unique(deflator, ["year"], "US GDP deflator")
    exports = exports.merge(deflator, on="year", how="left", validate="many_to_one")
    exports["merch_exports_constant_2015_usd"] = np.where(
        (exports["total_exports"] > 0) & (exports["us_gdp_deflator"] > 0),
        exports["total_exports"] / (exports["us_gdp_deflator"] / 100.0),
        np.nan,
    )
    exports["log_merch_exports"] = np.where(
        exports["merch_exports_constant_2015_usd"] > 0,
        np.log(exports["merch_exports_constant_2015_usd"]),
        np.nan,
    )
    return exports[
        [
            "iso3",
            "year",
            "total_exports",
            "oil_exports",
            "merch_exports_constant_2015_usd",
            "log_merch_exports",
        ]
    ].copy()


def read_wits_market_access(iso3s: Iterable[str]) -> pd.DataFrame:
    if not WITS_MARKET_ACCESS.exists():
        return pd.DataFrame(columns=["iso3", "year", "market_access_tariff_avg_i_t", "tariff_weight_coverage_i_t"])
    wits = pd.read_parquet(WITS_MARKET_ACCESS)
    wits = wits[
        wits["flow"].eq("Exports")
        & wits["iso3"].astype(str).str.upper().isin(set(iso3s))
        & wits["year"].between(2001, 2021)
    ].copy()
    wits["iso3"] = wits["iso3"].astype(str).str.upper()
    wits["year"] = pd.to_numeric(wits["year"], errors="coerce").astype(int)
    validate_unique(wits, ["iso3", "year"], "WITS market-access tariff panel")
    return wits[["iso3", "year", "market_access_tariff_avg_i_t", "tariff_weight_coverage_i_t"]]


def add_differences(panel: pd.DataFrame) -> pd.DataFrame:
    out = panel.sort_values(["iso3", "year"]).copy()
    diff_cols = [
        "import_product_gini_ex_energy",
        "log_real_exports",
        "log_merch_exports",
        "log_gdp_pc_ppp",
        "trade_openness_pct10",
        "log_population",
        "oil_export_share",
        "applied_tariff_weighted_mean_pct",
        "market_access_tariff_avg_i_t",
    ]
    for col in diff_cols:
        if col not in out.columns:
            out[col] = np.nan
        out[f"d_{col}"] = out.groupby("iso3")[col].diff()
    return out


def build_panel(refresh_wdi: bool = False) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    classification = read_classification()
    iso3s = sorted(classification["iso3"].unique())
    panel = read_ex_energy_outcome(classification)
    panel = panel.merge(read_ppp_controls(iso3s), on=["iso3", "year"], how="left", validate="one_to_one")
    panel = panel.merge(read_population_oil_controls(iso3s), on=["iso3", "year"], how="left", validate="one_to_one")
    panel = panel.merge(read_wdi_exports(iso3s), on=["iso3", "year"], how="left", validate="one_to_one")
    panel = panel.merge(read_merchandise_exports(iso3s), on=["iso3", "year"], how="left", validate="one_to_one")
    extra = load_or_fetch_extra_wdi(iso3s, refresh=refresh_wdi)
    validate_unique(extra, ["iso3", "year"], "extra World Bank controls")
    panel = panel.merge(extra, on=["iso3", "year"], how="left", validate="one_to_one")
    wits = read_wits_market_access(iso3s)
    if not wits.empty:
        panel = panel.merge(wits, on=["iso3", "year"], how="left", validate="one_to_one")
    else:
        panel["market_access_tariff_avg_i_t"] = np.nan
        panel["tariff_weight_coverage_i_t"] = np.nan
    panel["trade_openness_pct10"] = panel["trade_openness_pct_gdp"] / 10.0
    panel = add_differences(panel)
    validate_unique(panel, ["iso3", "year"], "mechanism regression panel")
    change = build_change_panel(panel, classification)
    return panel, change, classification


def first_last_value(group: pd.DataFrame, column: str, year: int) -> float | None:
    value = group.loc[group["year"].eq(year), column]
    if value.empty:
        return None
    return finite_float(value.iloc[0])


def build_change_panel(panel: pd.DataFrame, classification: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for iso3, group in panel.groupby("iso3", sort=True):
        group = group.sort_values("year")
        start = group[group["year"].eq(START_YEAR)]
        end = group[group["year"].eq(END_YEAR)]
        if start.empty or end.empty:
            raise RuntimeError(f"Missing start/end panel rows for {iso3}.")
        start_row = start.iloc[0]
        end_row = end.iloc[0]
        wits = group["market_access_tariff_avg_i_t"].dropna()
        wdi_tariff = group["applied_tariff_weighted_mean_pct"].dropna()
        rows.append(
            {
                "country": start_row["country"],
                "iso3": iso3,
                "reporter_code": int(start_row["reporter_code"]),
                "delta_import_product_gini_ex_energy": end_row["import_product_gini_ex_energy"]
                - start_row["import_product_gini_ex_energy"],
                "initial_import_product_gini_ex_energy": start_row["import_product_gini_ex_energy"],
                "end_import_product_gini_ex_energy": end_row["import_product_gini_ex_energy"],
                "delta_log_real_exports": end_row["log_real_exports"] - start_row["log_real_exports"],
                "initial_log_real_exports": start_row["log_real_exports"],
                "delta_log_merch_exports": end_row["log_merch_exports"] - start_row["log_merch_exports"],
                "initial_log_merch_exports": start_row["log_merch_exports"],
                "delta_log_gdp_pc_ppp": end_row["log_gdp_pc_ppp"] - start_row["log_gdp_pc_ppp"],
                "initial_log_gdp_pc_ppp": start_row["log_gdp_pc_ppp"],
                "delta_trade_openness_pct10": end_row["trade_openness_pct10"] - start_row["trade_openness_pct10"],
                "initial_trade_openness_pct10": start_row["trade_openness_pct10"],
                "delta_log_population": end_row["log_population"] - start_row["log_population"],
                "initial_log_population": start_row["log_population"],
                "delta_oil_export_share": end_row["oil_export_share"] - start_row["oil_export_share"],
                "initial_oil_export_share": start_row["oil_export_share"],
                "avg_wdi_applied_tariff_weighted_pct": finite_float(wdi_tariff.mean()) if len(wdi_tariff) else None,
                "n_wdi_applied_tariff_years": int(len(wdi_tariff)),
                "avg_wits_market_access_tariff_pct": finite_float(wits.mean()) if len(wits) else None,
                "n_wits_market_access_years": int(len(wits)),
            }
        )
    change = pd.DataFrame(rows)
    change = change.merge(
        classification[["iso3", "main_driver_group", "main_driver_bucket", "delta_panel_ex_energy_gini"]],
        on="iso3",
        how="left",
        validate="one_to_one",
    )
    gap = change["delta_import_product_gini_ex_energy"] - change["delta_panel_ex_energy_gini"]
    if gap.abs().max() > 1e-8:
        raise RuntimeError(f"Change outcome disagrees with classification; max gap={gap.abs().max()}.")
    return change


def model_sample(df: pd.DataFrame, formula: str, outcome: str, terms: Iterable[str]) -> pd.DataFrame:
    needed = {outcome, *terms}
    if "C(year)" in formula:
        needed.add("year")
    if "C(iso3)" in formula:
        needed.add("iso3")
    if "reporter_code" in df.columns:
        needed.add("reporter_code")
    cols = [col for col in needed if col in df.columns]
    return df.dropna(subset=cols).copy()


def fit_model(df: pd.DataFrame, spec: ModelSpec, model_frame: str) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    work = model_sample(df, spec.formula, spec.outcome, spec.terms)
    if work.empty:
        raise RuntimeError(f"No regression rows for {spec.model_id}.")
    result = smf.ols(spec.formula, data=work).fit()
    used_index = result.model.data.row_labels
    used = work.loc[used_index].copy()
    if spec.covariance == "cluster_country":
        result = result.get_robustcov_results(
            cov_type="cluster",
            groups=used["iso3"],
            use_t=True,
            use_correction=True,
        )
    elif spec.covariance == "hc3":
        result = result.get_robustcov_results(cov_type="HC3", use_t=True)
    elif spec.covariance == "nonrobust":
        pass
    else:
        raise ValueError(f"Unknown covariance: {spec.covariance}")
    params = pd.Series(result.params, index=result.model.exog_names)
    bse = pd.Series(result.bse, index=result.model.exog_names)
    tvals = pd.Series(result.tvalues, index=result.model.exog_names)
    pvals = pd.Series(result.pvalues, index=result.model.exog_names)
    rows: list[dict[str, Any]] = []
    for term in spec.terms:
        rows.append(
            {
                "model_id": spec.model_id,
                "model_frame": model_frame,
                "family": spec.family,
                "hypothesis": spec.hypothesis,
                "outcome": spec.outcome,
                "term": term,
                "coef": finite_float(params.get(term)),
                "std_error": finite_float(bse.get(term)),
                "t_stat": finite_float(tvals.get(term)),
                "p_value": finite_float(pvals.get(term)),
                "nobs": int(result.nobs),
                "countries": int(used["iso3"].nunique()) if "iso3" in used else None,
                "years": int(used["year"].nunique()) if "year" in used else None,
                "year_min": int(used["year"].min()) if "year" in used else None,
                "year_max": int(used["year"].max()) if "year" in used else None,
                "r_squared": finite_float(result.rsquared),
                "adj_r_squared": finite_float(result.rsquared_adj),
                "outcome_mean": finite_float(used[spec.outcome].mean()),
                "outcome_sd": finite_float(used[spec.outcome].std()),
                "covariance": spec.covariance,
                "formula": spec.formula,
                "sample_note": spec.sample_note,
                "effect_per_10pct_or_10pp": scaled_effect(params.get(term), term),
            }
        )
    return rows, used


def scaled_effect(coef: Any, term: str) -> float | None:
    x = finite_float(coef)
    if x is None:
        return None
    if "log_" in term:
        return x * math.log(1.10)
    if "pct10" in term:
        return x
    if "tariff" in term:
        return x
    return x


def main_specs() -> tuple[list[ModelSpec], list[ModelSpec], list[ModelSpec]]:
    panel_specs = [
        ModelSpec(
            "panel_pooled_year_fe",
            "Annual level, pooled/year FE",
            "Countries with larger exports, higher income, or greater openness have higher or lower ex-energy import concentration, comparing both countries and changes over time.",
            "import_product_gini_ex_energy",
            "import_product_gini_ex_energy ~ log_merch_exports + log_gdp_pc_ppp + trade_openness_pct10 + log_population + oil_export_share + C(year)",
            ("log_merch_exports", "log_gdp_pc_ppp", "trade_openness_pct10"),
            "cluster_country",
            "Balanced rd2 outcome panel, complete cases for Comtrade merchandise exports, PPP GDP per capita, openness, population, oil share.",
        ),
        ModelSpec(
            "panel_country_year_fe",
            "Annual level, country FE + year FE",
            "Within the same country, years with higher exports, higher income, or greater openness are associated with higher or lower ex-energy import concentration.",
            "import_product_gini_ex_energy",
            "import_product_gini_ex_energy ~ log_merch_exports + log_gdp_pc_ppp + trade_openness_pct10 + log_population + oil_export_share + C(iso3) + C(year)",
            ("log_merch_exports", "log_gdp_pc_ppp", "trade_openness_pct10"),
            "cluster_country",
            "Same as pooled model, adding country fixed effects to remove permanent country differences.",
        ),
        ModelSpec(
            "panel_first_difference_year_fe",
            "Annual first differences",
            "Short-run within-country changes in exports, income, or openness move with short-run changes in ex-energy import concentration.",
            "d_import_product_gini_ex_energy",
            "d_import_product_gini_ex_energy ~ d_log_merch_exports + d_log_gdp_pc_ppp + d_trade_openness_pct10 + d_log_population + d_oil_export_share + C(year)",
            ("d_log_merch_exports", "d_log_gdp_pc_ppp", "d_trade_openness_pct10"),
            "cluster_country",
            "One-year changes over 2001-2024, complete cases for differenced variables.",
        ),
        ModelSpec(
            "panel_country_year_fe_wdi_exports",
            "Robustness: WDI real export level",
            "The export-scale result is not an artifact of Comtrade merchandise-export measurement.",
            "import_product_gini_ex_energy",
            "import_product_gini_ex_energy ~ log_real_exports + log_gdp_pc_ppp + trade_openness_pct10 + log_population + oil_export_share + C(iso3) + C(year)",
            ("log_real_exports", "log_gdp_pc_ppp", "trade_openness_pct10"),
            "cluster_country",
            "Country/year FE model replacing Comtrade merchandise exports with WDI real exports of goods and services; WDI coverage is incomplete for some rd2 countries.",
        ),
        ModelSpec(
            "panel_wdi_import_tariff_fe",
            "Robustness: WDI applied import tariff",
            "Higher import trade barriers are associated with higher concentration if barriers restrict variety, or lower concentration if they suppress dominant imported categories.",
            "import_product_gini_ex_energy",
            "import_product_gini_ex_energy ~ applied_tariff_weighted_mean_pct + log_real_exports + log_gdp_pc_ppp + log_population + oil_export_share + C(iso3) + C(year)",
            ("applied_tariff_weighted_mean_pct",),
            "cluster_country",
            "Country/year FE model on nonmissing WDI weighted-mean applied import tariffs; coverage is incomplete.",
        ),
        ModelSpec(
            "panel_wits_market_access_fe",
            "Robustness: WITS export-market tariff exposure",
            "Lower foreign market-access barriers may accompany export upgrading and imported-input concentration.",
            "import_product_gini_ex_energy",
            "import_product_gini_ex_energy ~ market_access_tariff_avg_i_t + log_real_exports + log_gdp_pc_ppp + log_population + oil_export_share + C(iso3) + C(year)",
            ("market_access_tariff_avg_i_t",),
            "cluster_country",
            "Country/year FE model on the existing WITS HS4 export-market tariff exposure sample, 2001-2021.",
        ),
    ]
    change_specs = [
        ModelSpec(
            "change_export_only",
            "Long difference, export scale",
            "Countries with faster export growth or larger initial export scale reconcentrated more from 2000 to 2024.",
            "delta_import_product_gini_ex_energy",
            "delta_import_product_gini_ex_energy ~ delta_log_merch_exports + initial_log_merch_exports",
            ("delta_log_merch_exports", "initial_log_merch_exports"),
            "hc3",
            "One row per balanced country; HC3 inference because N is small.",
        ),
        ModelSpec(
            "change_income_only",
            "Long difference, income",
            "Countries with faster income growth or higher initial development stage reconcentrated more from 2000 to 2024.",
            "delta_import_product_gini_ex_energy",
            "delta_import_product_gini_ex_energy ~ delta_log_gdp_pc_ppp + initial_log_gdp_pc_ppp",
            ("delta_log_gdp_pc_ppp", "initial_log_gdp_pc_ppp"),
            "hc3",
            "One row per balanced country; HC3 inference because N is small.",
        ),
        ModelSpec(
            "change_combined",
            "Long difference, combined",
            "Export growth, initial export scale, income growth, development stage, openness, population, and oil exposure jointly explain 2000-2024 reconcentration.",
            "delta_import_product_gini_ex_energy",
            "delta_import_product_gini_ex_energy ~ delta_log_merch_exports + initial_log_merch_exports + delta_log_gdp_pc_ppp + initial_log_gdp_pc_ppp + delta_trade_openness_pct10 + initial_trade_openness_pct10 + initial_log_population + initial_oil_export_share",
            (
                "delta_log_merch_exports",
                "initial_log_merch_exports",
                "delta_log_gdp_pc_ppp",
                "initial_log_gdp_pc_ppp",
                "delta_trade_openness_pct10",
                "initial_trade_openness_pct10",
            ),
            "hc3",
            "One row per balanced country; intentionally low-dimensional enough for N=56 but still descriptive.",
        ),
        ModelSpec(
            "change_combined_wdi_exports",
            "Robustness: long difference WDI exports",
            "The long-difference export-growth result is not an artifact of Comtrade merchandise-export measurement.",
            "delta_import_product_gini_ex_energy",
            "delta_import_product_gini_ex_energy ~ delta_log_real_exports + initial_log_real_exports + delta_log_gdp_pc_ppp + initial_log_gdp_pc_ppp + delta_trade_openness_pct10 + initial_trade_openness_pct10 + initial_log_population + initial_oil_export_share",
            (
                "delta_log_real_exports",
                "initial_log_real_exports",
                "delta_log_gdp_pc_ppp",
                "initial_log_gdp_pc_ppp",
                "delta_trade_openness_pct10",
                "initial_trade_openness_pct10",
            ),
            "hc3",
            "Long-difference model replacing Comtrade merchandise exports with WDI real exports of goods and services.",
        ),
        ModelSpec(
            "change_wdi_tariff_average",
            "Long difference, WDI tariff average",
            "Countries with higher average import tariffs over the sample had different reconcentration paths.",
            "delta_import_product_gini_ex_energy",
            "delta_import_product_gini_ex_energy ~ avg_wdi_applied_tariff_weighted_pct + delta_log_gdp_pc_ppp + initial_log_gdp_pc_ppp + initial_log_population",
            ("avg_wdi_applied_tariff_weighted_pct",),
            "hc3",
            "One row per country with at least one WDI applied-tariff observation; sparse tariff coverage.",
        ),
        ModelSpec(
            "change_wits_market_access_average",
            "Long difference, WITS market-access average",
            "Countries facing higher foreign market-access tariffs had different reconcentration paths.",
            "delta_import_product_gini_ex_energy",
            "delta_import_product_gini_ex_energy ~ avg_wits_market_access_tariff_pct + delta_log_gdp_pc_ppp + initial_log_gdp_pc_ppp + initial_log_population",
            ("avg_wits_market_access_tariff_pct",),
            "hc3",
            "One row per country with WITS HS4 market-access tariff exposure observations.",
        ),
    ]
    return panel_specs, change_specs, []


def run_models(panel: pd.DataFrame, change: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    panel_specs, change_specs, _ = main_specs()
    rows: list[dict[str, Any]] = []
    samples: dict[str, pd.DataFrame] = {}
    for spec in panel_specs:
        result_rows, sample = fit_model(panel, spec, "panel")
        rows.extend(result_rows)
        samples[spec.model_id] = sample
    for spec in change_specs:
        result_rows, sample = fit_model(change, spec, "change")
        rows.extend(result_rows)
        samples[spec.model_id] = sample
    return pd.DataFrame(rows), samples


def leave_one_country_robustness(
    panel: pd.DataFrame,
    change: pd.DataFrame,
    target_specs: Iterable[ModelSpec],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for spec in target_specs:
        frame = change if spec.model_id.startswith("change") else panel
        work = model_sample(frame, spec.formula, spec.outcome, spec.terms)
        countries = sorted(work["iso3"].dropna().unique())
        for term in spec.terms:
            coefs: list[float] = []
            pvals: list[float] = []
            for iso3 in countries:
                sub = work[work["iso3"].ne(iso3)].copy()
                try:
                    result_rows, _sample = fit_model(sub, spec, spec.model_id.split("_", 1)[0])
                except Exception:
                    continue
                rr = next((row for row in result_rows if row["term"] == term), None)
                if rr and rr["coef"] is not None:
                    coefs.append(float(rr["coef"]))
                    if rr["p_value"] is not None:
                        pvals.append(float(rr["p_value"]))
            if coefs:
                rows.append(
                    {
                        "model_id": spec.model_id,
                        "term": term,
                        "leave_one_runs": len(coefs),
                        "coef_min": float(np.min(coefs)),
                        "coef_median": float(np.median(coefs)),
                        "coef_max": float(np.max(coefs)),
                        "share_positive": float(np.mean(np.array(coefs) > 0)),
                        "share_p_lt_0_05": float(np.mean(np.array(pvals) < 0.05)) if pvals else np.nan,
                    }
                )
    return pd.DataFrame(rows)


def sample_diagnostics(panel: pd.DataFrame, change: pd.DataFrame, samples: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = [
        {
            "artifact": "balanced_ex_energy_panel",
            "rows": len(panel),
            "countries": panel["iso3"].nunique(),
            "years": panel["year"].nunique(),
            "year_min": panel["year"].min(),
            "year_max": panel["year"].max(),
            "complete_outcome_rows": int(panel["import_product_gini_ex_energy"].notna().sum()),
            "missing_merch_exports": int(panel["log_merch_exports"].isna().sum()),
            "missing_wdi_exports": int(panel["log_real_exports"].isna().sum()),
            "missing_trade_openness": int(panel["trade_openness_pct_gdp"].isna().sum()),
            "missing_wdi_applied_tariff": int(panel["applied_tariff_weighted_mean_pct"].isna().sum()),
            "missing_wits_market_access": int(panel["market_access_tariff_avg_i_t"].isna().sum()),
        },
        {
            "artifact": "long_difference_panel",
            "rows": len(change),
            "countries": change["iso3"].nunique(),
            "years": 1,
            "year_min": START_YEAR,
            "year_max": END_YEAR,
            "complete_outcome_rows": int(change["delta_import_product_gini_ex_energy"].notna().sum()),
            "missing_merch_exports": int(change["delta_log_merch_exports"].isna().sum()),
            "missing_wdi_exports": int(change["delta_log_real_exports"].isna().sum()),
            "missing_trade_openness": int(change["delta_trade_openness_pct10"].isna().sum()),
            "missing_wdi_applied_tariff": int(change["avg_wdi_applied_tariff_weighted_pct"].isna().sum()),
            "missing_wits_market_access": int(change["avg_wits_market_access_tariff_pct"].isna().sum()),
        },
    ]
    for model_id, sample in samples.items():
        rows.append(
            {
                "artifact": f"regression_sample::{model_id}",
                "rows": len(sample),
                "countries": sample["iso3"].nunique() if "iso3" in sample else None,
                "years": sample["year"].nunique() if "year" in sample else None,
                "year_min": sample["year"].min() if "year" in sample else None,
                "year_max": sample["year"].max() if "year" in sample else None,
                "complete_outcome_rows": len(sample),
                "missing_merch_exports": int(sample["log_merch_exports"].isna().sum()) if "log_merch_exports" in sample else None,
                "missing_wdi_exports": int(sample["log_real_exports"].isna().sum()) if "log_real_exports" in sample else None,
                "missing_trade_openness": int(sample["trade_openness_pct_gdp"].isna().sum()) if "trade_openness_pct_gdp" in sample else None,
                "missing_wdi_applied_tariff": int(sample["applied_tariff_weighted_mean_pct"].isna().sum())
                if "applied_tariff_weighted_mean_pct" in sample
                else None,
                "missing_wits_market_access": int(sample["market_access_tariff_avg_i_t"].isna().sum())
                if "market_access_tariff_avg_i_t" in sample
                else None,
            }
        )
    return pd.DataFrame(rows)


def fmt_num(value: Any, digits: int = 4, pvalue: bool = False, bold_sig: bool = False) -> str:
    x = finite_float(value)
    if x is None:
        return ""
    if pvalue and x < 0.001:
        text = "<0.001"
    else:
        text = f"{x:.{digits}f}"
    if bold_sig and x < 0.05:
        return f"**{text}**"
    return text


def term_label(term: str) -> str:
    labels = {
        "log_real_exports": "Log real exports",
        "d_log_real_exports": "Annual export growth",
        "delta_log_real_exports": "2000-2024 export growth",
        "initial_log_real_exports": "Initial export level",
        "log_merch_exports": "Log merchandise exports",
        "d_log_merch_exports": "Annual merchandise export growth",
        "delta_log_merch_exports": "2000-2024 merchandise export growth",
        "initial_log_merch_exports": "Initial merchandise export level",
        "log_gdp_pc_ppp": "Log PPP GDP pc",
        "d_log_gdp_pc_ppp": "Annual PPP GDP pc growth",
        "delta_log_gdp_pc_ppp": "2000-2024 PPP GDP pc growth",
        "initial_log_gdp_pc_ppp": "Initial PPP GDP pc",
        "trade_openness_pct10": "Trade openness / 10 pp",
        "d_trade_openness_pct10": "Annual openness change / 10 pp",
        "delta_trade_openness_pct10": "2000-2024 openness change / 10 pp",
        "initial_trade_openness_pct10": "Initial openness / 10 pp",
        "applied_tariff_weighted_mean_pct": "WDI import tariff pct",
        "market_access_tariff_avg_i_t": "WITS export-market tariff pct",
        "avg_wdi_applied_tariff_weighted_pct": "Avg WDI import tariff pct",
        "avg_wits_market_access_tariff_pct": "Avg WITS market-access tariff pct",
    }
    return labels.get(term, term)


def model_short_label(model_id: str) -> str:
    labels = {
        "panel_pooled_year_fe": "Pooled + year FE",
        "panel_country_year_fe": "Country + year FE",
        "panel_first_difference_year_fe": "Annual change",
        "panel_country_year_fe_wdi_exports": "Country FE, WDI exports",
        "panel_wdi_import_tariff_fe": "Country FE, WDI tariff",
        "panel_wits_market_access_fe": "Country FE, WITS tariff",
        "change_export_only": "Long diff: exports",
        "change_income_only": "Long diff: income",
        "change_combined": "Long diff: combined",
        "change_combined_wdi_exports": "Long diff: WDI exports",
        "change_wdi_tariff_average": "Long diff: WDI tariff",
        "change_wits_market_access_average": "Long diff: WITS tariff",
    }
    return labels.get(model_id, model_id)


def markdown_table(df: pd.DataFrame, columns: list[tuple[str, str]], max_rows: int | None = None) -> str:
    if max_rows is not None:
        df = df.head(max_rows).copy()
    lines = ["|" + "|".join(label for _col, label in columns) + "|", "|" + "|".join("---" for _ in columns) + "|"]
    for _, row in df.iterrows():
        cells: list[str] = []
        for col, _label in columns:
            value = row.get(col, "")
            cells.append(str(value))
        lines.append("|" + "|".join(cells) + "|")
    return "\n".join(lines)


def formatted_results(results: pd.DataFrame) -> pd.DataFrame:
    out = results.copy()
    out["model"] = out["model_id"].map(model_short_label)
    out["term_label"] = out["term"].map(term_label)
    out["coef_fmt"] = [
        fmt_num(coef, 4, bold_sig=(p is not None and p < 0.05))
        for coef, p in zip(out["coef"], out["p_value"])
    ]
    out["se_fmt"] = out["std_error"].map(lambda x: fmt_num(x, 4))
    out["p_fmt"] = out["p_value"].map(lambda x: fmt_num(x, 3, pvalue=True, bold_sig=True))
    out["effect_fmt"] = out["effect_per_10pct_or_10pp"].map(lambda x: fmt_num(x, 4))
    out["n_fmt"] = out["nobs"].astype(int).astype(str)
    out["countries_fmt"] = out["countries"].fillna("").astype(str).str.replace(r"\.0$", "", regex=True)
    return out


def write_markdown(results: pd.DataFrame, loo: pd.DataFrame, diagnostics: pd.DataFrame) -> None:
    fmt = formatted_results(results)
    main = fmt[
        fmt["model_id"].isin(["panel_pooled_year_fe", "panel_country_year_fe", "panel_first_difference_year_fe", "change_combined"])
    ].copy()
    tariff = fmt[
        fmt["model_id"].isin(
            [
                "panel_wdi_import_tariff_fe",
                "panel_wits_market_access_fe",
                "change_wdi_tariff_average",
                "change_wits_market_access_average",
                "panel_country_year_fe_wdi_exports",
                "change_combined_wdi_exports",
            ]
        )
    ].copy()
    loo_fmt = loo.copy()
    for col in ["coef_min", "coef_median", "coef_max", "share_positive", "share_p_lt_0_05"]:
        if col in loo_fmt:
            loo_fmt[f"{col}_fmt"] = loo_fmt[col].map(lambda x: fmt_num(x, 3))
    lines = [
        "# Ex-Energy Import Product Gini Mechanism Regressions",
        "",
        f"Created UTC: `{now_utc()}`",
        "",
        "## Bottom Line",
        "",
        "- These regressions are descriptive mechanism evidence, not causal identification.",
        "- The cleanest separation is pooled/year-FE versus country-FE: pooled models ask whether countries at different export/income/openness levels have different import concentration; country-FE and first-difference models ask whether the same country becomes more concentrated as those variables change.",
        "- Trade-barrier proxies are useful but not headline-quality: WDI tariff coverage is incomplete, and the WITS measure is export-market tariff exposure rather than an import liberalization measure.",
        "",
        "## Main Results",
        "",
        markdown_table(
            main,
            [
                ("model", "Model"),
                ("term_label", "Variable"),
                ("coef_fmt", "Coef"),
                ("se_fmt", "SE"),
                ("p_fmt", "p"),
                ("effect_fmt", "Effect per 10pct or 10pp"),
                ("n_fmt", "N"),
                ("countries_fmt", "Countries"),
            ],
        ),
        "",
        "## Trade-Barrier and Export-Definition Robustness",
        "",
        markdown_table(
            tariff,
            [
                ("model", "Model"),
                ("term_label", "Variable"),
                ("coef_fmt", "Coef"),
                ("se_fmt", "SE"),
                ("p_fmt", "p"),
                ("effect_fmt", "Effect scale"),
                ("n_fmt", "N"),
                ("countries_fmt", "Countries"),
            ],
        ),
        "",
        "## Leave-One-Country Sensitivity",
        "",
        markdown_table(
            loo_fmt.assign(
                model=loo_fmt["model_id"].map(model_short_label),
                variable=loo_fmt["term"].map(term_label),
            ),
            [
                ("model", "Model"),
                ("variable", "Variable"),
                ("leave_one_runs", "Runs"),
                ("coef_min_fmt", "Min coef"),
                ("coef_median_fmt", "Median coef"),
                ("coef_max_fmt", "Max coef"),
                ("share_positive_fmt", "Share positive"),
                ("share_p_lt_0_05_fmt", "Share p<0.05"),
            ],
        ),
        "",
        "## Sample Diagnostics",
        "",
        markdown_table(
            diagnostics.assign(rows=diagnostics["rows"].astype(str)),
            [
                ("artifact", "Artifact"),
                ("rows", "Rows"),
                ("countries", "Countries"),
                ("years", "Years"),
                ("year_min", "Min year"),
                ("year_max", "Max year"),
                ("missing_merch_exports", "Missing merch exports"),
                ("missing_wdi_exports", "Missing WDI exports"),
                ("missing_trade_openness", "Missing openness"),
                ("missing_wdi_applied_tariff", "Missing WDI tariff"),
                ("missing_wits_market_access", "Missing WITS tariff"),
            ],
        ),
        "",
        "## Interpretation",
        "",
        "- A positive coefficient means the explanatory variable is associated with higher ex-energy import product concentration.",
        "- For log variables, the effect-size column translates the coefficient into the approximate change in Gini for a 10 percent increase.",
        "- For trade openness divided by 10, the effect-size column is the change in Gini for a 10 percentage-point increase in trade/GDP.",
        "- The annual first-difference model is the most conservative for short-run co-movement; the long-difference model is the closest to the country-grouping question.",
        "",
        "## Referee 2 Cautions",
        "",
        "- Exports and import concentration are jointly determined; these models do not prove exports cause import concentration.",
        "- Country FE absorbs permanent country differences but leaves time-varying industrial policy, exchange-rate, re-export, commodity-price, and reporting shocks.",
        "- Tariff proxies are imperfect. WDI applied import tariffs are sparse; WITS market-access tariffs measure foreign barriers faced by exporters, not domestic import barriers.",
        "- With 56 countries, long-difference models should be read for sign, magnitude, and robustness, not as a definitive horse race among many correlated mechanisms.",
        "- Audit status: this was a local in-session adversarial review because no independent subagent/delegation tool was exposed in the current tool set.",
        "",
        "## Economist Council Read",
        "",
        "- Identification skeptic: the annual export-growth result is not enough to explain the country groups; reverse causality and omitted industrial shocks remain live.",
        "- Trade theorist: the positive annual export-growth coefficient is plausible if export expansion raises demand for a narrower set of imported intermediates.",
        "- Development economist: pooled income/openness patterns are development-stage evidence, while country-FE and long-difference models are the safer within-country checks.",
        "- Policy/external-validity voice: tariff results are too proxy-dependent to carry the story; treat them as suggestive diagnostics only.",
    ]
    (OUT_DIR / "import_gini_mechanism_regressions.md").write_text("\n".join(lines) + "\n")


def plot_effects(results: pd.DataFrame) -> None:
    keep = results[
        results["model_id"].isin(
            [
                "panel_pooled_year_fe",
                "panel_country_year_fe",
                "panel_first_difference_year_fe",
                "change_combined",
                "panel_wdi_import_tariff_fe",
                "panel_wits_market_access_fe",
            ]
        )
    ].copy()
    keep["label"] = keep["model_id"].map(model_short_label) + "\n" + keep["term"].map(term_label)
    keep = keep.dropna(subset=["effect_per_10pct_or_10pp", "std_error"]).reset_index(drop=True)
    if keep.empty:
        return
    keep["effect_se"] = [
        scaled_effect(se, term) if scaled_effect(se, term) is not None else np.nan
        for se, term in zip(keep["std_error"], keep["term"])
    ]
    fig, ax = plt.subplots(figsize=(12, max(6, len(keep) * 0.35)), constrained_layout=True)
    y = np.arange(len(keep))
    ax.errorbar(
        keep["effect_per_10pct_or_10pp"],
        y,
        xerr=1.96 * keep["effect_se"].abs(),
        fmt="o",
        color="#2563eb",
        ecolor="#93c5fd",
        capsize=3,
    )
    ax.axvline(0, color="#374151", linewidth=1)
    ax.set_yticks(y)
    ax.set_yticklabels(keep["label"], fontsize=8)
    ax.set_xlabel("Estimated Gini change per 10 percent log increase, 10pp openness change, or 1pp tariff change")
    ax.set_title("Ex-energy import Product Gini mechanism coefficients", loc="left", fontsize=14)
    ax.grid(True, axis="x", color="#e5e7eb")
    ax.spines[["top", "right"]].set_visible(False)
    fig.savefig(FIG_DIR / "mechanism_coefficient_effects.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def plot_long_difference_scatter(change: pd.DataFrame) -> None:
    specs = [
        ("delta_log_real_exports", "2000-2024 log real export growth"),
        ("delta_log_gdp_pc_ppp", "2000-2024 log PPP GDP pc growth"),
        ("delta_trade_openness_pct10", "2000-2024 trade openness change / 10pp"),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8), constrained_layout=True)
    for ax, (xcol, xlabel) in zip(axes, specs):
        work = change.dropna(subset=[xcol, "delta_import_product_gini_ex_energy"]).copy()
        ax.scatter(work[xcol], work["delta_import_product_gini_ex_energy"], s=32, color="#0f766e", alpha=0.8)
        if len(work) >= 3:
            fit = np.polyfit(work[xcol], work["delta_import_product_gini_ex_energy"], 1)
            xs = np.linspace(work[xcol].min(), work[xcol].max(), 100)
            ax.plot(xs, fit[0] * xs + fit[1], color="#111827", linewidth=1.4)
        label_rows = work.reindex(work["delta_import_product_gini_ex_energy"].abs().sort_values(ascending=False).head(5).index)
        for _, row in label_rows.iterrows():
            ax.text(row[xcol], row["delta_import_product_gini_ex_energy"], str(row["iso3"]), fontsize=7)
        ax.axhline(0, color="#9ca3af", linewidth=1)
        ax.set_xlabel(xlabel)
        ax.set_ylabel("2000-2024 ex-energy import Product Gini change")
        ax.grid(True, color="#e5e7eb")
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("Long-difference country evidence", x=0.02, ha="left", fontsize=14)
    fig.savefig(FIG_DIR / "long_difference_scatter.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def html_escape(text: Any) -> str:
    import html

    return html.escape("" if text is None else str(text))


def html_table(df: pd.DataFrame, columns: list[tuple[str, str]], cls: str = "") -> str:
    class_attr = f' class="{cls}"' if cls else ""
    head = "".join(f"<th>{html_escape(label)}</th>" for _col, label in columns)
    rows = []
    for _, row in df.iterrows():
        cells = "".join(f"<td>{html_cell(row.get(col, ''))}</td>" for col, _label in columns)
        rows.append(f"<tr>{cells}</tr>")
    return f'<div class="table-wrap"><table{class_attr}><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def html_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    if text.startswith("**") and text.endswith("**"):
        return f"<strong>{html_escape(text[2:-2])}</strong>"
    return html_escape(text)


def write_html_section(results: pd.DataFrame, loo: pd.DataFrame, diagnostics: pd.DataFrame) -> None:
    fmt = formatted_results(results)
    main = fmt[
        fmt["model_id"].isin(["panel_pooled_year_fe", "panel_country_year_fe", "panel_first_difference_year_fe", "change_combined"])
    ].copy()
    tariff = fmt[
        fmt["model_id"].isin(
            [
                "panel_wdi_import_tariff_fe",
                "panel_wits_market_access_fe",
                "change_wdi_tariff_average",
                "change_wits_market_access_average",
                "panel_country_year_fe_wdi_exports",
                "change_combined_wdi_exports",
            ]
        )
    ].copy()
    loo_fmt = loo.copy()
    if not loo_fmt.empty:
        for col in ["coef_min", "coef_median", "coef_max", "share_positive", "share_p_lt_0_05"]:
            loo_fmt[f"{col}_fmt"] = loo_fmt[col].map(lambda x: fmt_num(x, 3))
        loo_fmt["model"] = loo_fmt["model_id"].map(model_short_label)
        loo_fmt["variable"] = loo_fmt["term"].map(term_label)
    diag_small = diagnostics[diagnostics["artifact"].str.startswith(("balanced", "long_difference", "regression_sample::panel_country_year_fe", "regression_sample::change_combined"))].copy()
    html = f"""
<section id="mechanism-regressions" class="section">
  <div class="wrap">
  <div class="section-kicker">New diagnostic page</div>
  <h2>Can Exports, Income, and Trade Barriers Explain Import Concentration?</h2>
  <p class="lead">This section asks a narrower question than the Cadot hump: can the 2000-2024 rise in ex-energy import Product Gini be described by export scale/growth, income level/growth, openness, or tariff proxies?</p>
  <div class="callout warning"><strong>Status:</strong> descriptive mechanism evidence only. These regressions do not identify a causal channel.</div>
  <h3>Bottom-Line Read</h3>
  <div class="grid">
    <div class="panel"><h3>Exports</h3><p>Annual merchandise export growth is positively associated with annual concentration changes, but export level/growth does not explain the 2000-2024 country-level change once the full long-difference model is used.</p></div>
    <div class="panel"><h3>Income</h3><p>PPP GDP per capita does not give a stable explanation. Pooled levels and annual changes point negative, while long-difference income terms are not significant in the full model.</p></div>
    <div class="panel"><h3>Openness</h3><p>Trade openness is the most persistent descriptive signal in annual level models: positive in pooled/year-FE and borderline positive with country/year-FE. It does not cleanly explain the long-run country grouping.</p></div>
    <div class="panel"><h3>Barriers</h3><p>Tariff evidence is weak. WDI applied import tariffs are positive in one reduced-sample country-FE panel, but WITS export-market tariffs and long-difference tariff averages are null.</p></div>
  </div>
  <h3>Economist Council Read</h3>
  <div class="grid">
    <div class="panel"><h3>Identification skeptic</h3><p>The annual export-growth result is not enough to explain the country groups. Reverse causality and omitted industrial shocks remain live.</p></div>
    <div class="panel"><h3>Trade theorist</h3><p>A positive annual export-growth coefficient is plausible if export expansion raises demand for a narrower set of imported intermediates.</p></div>
    <div class="panel"><h3>Development economist</h3><p>Pooled income and openness patterns are development-stage evidence. Country-FE and long-difference models are the safer within-country checks.</p></div>
    <div class="panel"><h3>Policy voice</h3><p>Tariff results are too proxy-dependent to carry the story. Use them as suggestive diagnostics, not as a causal trade-barrier result.</p></div>
  </div>
  <h3>Data Used</h3>
  <div class="table-wrap"><table><thead><tr><th>Variable</th><th>Source</th><th>Why appropriate</th><th>Main caveat</th></tr></thead><tbody>
    <tr><td>Ex-energy import Product Gini</td><td>Exercise 3 import-bin decomposition, energy row</td><td>Directly matches the outcome behind the country grouping.</td><td>Ex-energy means the project energy basket, not every HS27 edge case.</td></tr>
    <tr><td>Export level/growth</td><td>Comtrade merchandise export totals, deflated with US GDP deflator</td><td>Same merchandise-trade universe as the concentration outcome.</td><td>Deflator is economy-wide, not product-specific.</td></tr>
    <tr><td>Income level/growth</td><td>World Bank constant PPP GDP per capita</td><td>Closest to the Cadot-comparable development variable.</td><td>Income and trade structure are jointly determined.</td></tr>
    <tr><td>Trade openness</td><td>World Bank trade openness, trade as percent of GDP</td><td>Broad integration proxy with high coverage.</td><td>Not a pure policy or barrier measure.</td></tr>
    <tr><td>Tariffs/barriers</td><td>WDI weighted applied import tariff; WITS HS4 export-market tariff exposure</td><td>Closer to policy barriers than openness.</td><td>Sparse coverage; WITS is export-market access, not domestic import liberalization.</td></tr>
  </tbody></table></div>
  <h3>Hypotheses and Design</h3>
  <div class="grid two">
    <div class="note-card">
      <h4>Annual level models</h4>
      <p><code>Gini_ct = exports_ct + GDPpc_ct + openness_ct + controls + FE</code>. Pooled/year-FE compares countries at different development stages. Country/year-FE asks whether the same country becomes more concentrated as exports, income, or openness changes.</p>
    </div>
    <div class="note-card">
      <h4>Long-difference models</h4>
      <p><code>Delta Gini_c = export growth_c + initial exports_c + income growth_c + initial income_c + openness_c + controls</code>. This is closest to the country-grouping question because the country groups are defined by 2000-2024 concentration changes.</p>
    </div>
  </div>
  <h3>Main Results</h3>
  {html_table(main, [("model", "Model"), ("term_label", "Variable"), ("coef_fmt", "Coef"), ("se_fmt", "SE"), ("p_fmt", "p"), ("effect_fmt", "Effect scale"), ("n_fmt", "N"), ("countries_fmt", "Countries")])}
  <figure><img src="import_gini_mechanism_regressions/figures/mechanism_coefficient_effects.png" alt="Mechanism coefficient effects"><figcaption>Effect sizes are Gini changes per 10 percent log-variable increase, per 10 percentage-point openness change, or per 1 percentage-point tariff change.</figcaption></figure>
  <h3>Trade-Barrier and Export-Definition Robustness</h3>
  <p>The direct tariff evidence is weaker than the export/income/openness evidence because tariff data are sparse and the WITS measure is export-market access, not domestic import liberalization.</p>
  {html_table(tariff, [("model", "Model"), ("term_label", "Variable"), ("coef_fmt", "Coef"), ("se_fmt", "SE"), ("p_fmt", "p"), ("effect_fmt", "Effect scale"), ("n_fmt", "N"), ("countries_fmt", "Countries")])}
  <figure><img src="import_gini_mechanism_regressions/figures/long_difference_scatter.png" alt="Long-difference scatter plots"><figcaption>Country-level 2000-2024 changes. Labels mark the largest absolute concentration changes.</figcaption></figure>
  <h3>Leave-One-Country Sensitivity</h3>
  {html_table(loo_fmt if not loo_fmt.empty else pd.DataFrame(), [("model", "Model"), ("variable", "Variable"), ("leave_one_runs", "Runs"), ("coef_min_fmt", "Min coef"), ("coef_median_fmt", "Median coef"), ("coef_max_fmt", "Max coef"), ("share_positive_fmt", "Share positive"), ("share_p_lt_0_05_fmt", "Share p<0.05")])}
  <h3>Econometric Interpretation</h3>
  <ul>
    <li><strong>Export scale/growth:</strong> tests whether import reconcentration travels with export-market size or export expansion. This is plausible if export upgrading requires a narrower set of high-value imported intermediates, but the direction is not causal from this design.</li>
    <li><strong>Income level/growth:</strong> tests whether reconcentration is a development-stage pattern. Pooled results are cross-country stage comparisons; country-FE results are within-country development changes.</li>
    <li><strong>Openness and tariffs:</strong> tests whether liberalization/barriers matter. Openness has broad coverage but is not a pure policy variable; tariff proxies are closer to barriers but have weaker coverage and measurement caveats.</li>
  </ul>
  <h3>Sample Diagnostics</h3>
  {html_table(diag_small, [("artifact", "Artifact"), ("rows", "Rows"), ("countries", "Countries"), ("years", "Years"), ("year_min", "Min year"), ("year_max", "Max year"), ("missing_merch_exports", "Missing merch exports"), ("missing_wdi_exports", "Missing WDI exports"), ("missing_trade_openness", "Missing openness"), ("missing_wdi_applied_tariff", "Missing WDI tariff"), ("missing_wits_market_access", "Missing WITS tariff")])}
  <div class="callout"><strong>Main issue for the paper:</strong> do not collapse pooled and country-FE evidence. Pooled/year-FE says richer or more export-intensive countries look different. Country-FE says whether the same country reconcentrates as those variables change.</div>
  </div>
</section>
"""
    (OUT_DIR / "import_gini_mechanism_regressions_section.html").write_text(html)


def write_adversarial_review(panel: pd.DataFrame, change: pd.DataFrame, results: pd.DataFrame, diagnostics: pd.DataFrame) -> None:
    review = f"""# Adversarial Review: Import Gini Mechanism Regressions

Created UTC: `{now_utc()}`

## Executive Verdict

Trust only as descriptive mechanism evidence.

- Reviewer independence: this is a local in-session adversarial review. A fresh independent subagent pass was not possible because no subagent/delegation tool was exposed in the current tool set.
- The ex-energy outcome panel is balanced: {panel['iso3'].nunique()} countries x {panel['year'].nunique()} years = {len(panel)} country-years.
- The long-difference sample is aligned to the same 2000-2024 country set.
- Inference is appropriate for this stage: country-clustered SEs for panels and HC3 for N=56-style country-level changes.
- The design is not causal. Exports, income, openness, and concentration are jointly determined.
- Trade-barrier evidence is the weakest part because WDI tariff rates and WITS market-access tariffs have coverage and interpretation limits.

## Highest-Risk Findings

1. **Endogeneity is unavoidable.** Export growth may cause imported-input concentration, but import concentration may also enable export growth, and both may be caused by industrial policy, exchange rates, sectoral shocks, or reporting changes.
2. **Pooled versus country-FE interpretation can be confused.** Pooled/year-FE evidence is cross-country development-stage evidence. Country-FE and first-difference evidence is within-country co-movement.
3. **Trade-barrier proxies are not decisive.** WDI applied import tariff observations are incomplete; WITS market-access tariffs measure foreign destination barriers faced by exporters, not domestic import barriers.
4. **Long-difference models have small N.** With {change['iso3'].nunique()} countries, the combined model is useful for signs and magnitudes, not for a final horse race among correlated mechanisms.

## Data Lineage and Sample Audit

- Outcome source: `{rel(IMPORT_BIN_DECOMP)}`, `import_bin == energy`, using `product_gini_without_bin` as ex-energy import Product Gini.
- Balanced country source: `{rel(CLASSIFICATION)}`.
- Main export source: `{rel(MERCH_EXPORT_PANEL)}`, Comtrade merchandise export totals deflated with `{rel(US_DEFLATOR)}`.
- Robustness export source: `{rel(WDI_EXPORT_CONTROLS)}`, World Bank `NE.EXP.GNFS.KD`.
- Income source: `{rel(PPP_CONTROLS)}`, World Bank `NY.GDP.PCAP.PP.KD`.
- Openness/tariff WDI source cache: `{rel(EXTRA_WDI_CACHE)}`.
- WITS tariff source: `{rel(WITS_MARKET_ACCESS)}`.

## Specification Audit

Main panel equation:

`Gini_ct = beta1 log(exports_ct) + beta2 log(GDPpc_PPP_ct) + beta3 trade_open_ct/10 + beta4 log(pop_ct) + beta5 oil_share_ct + year FE + error_ct`

Country-FE variant adds country fixed effects. First-difference variant uses one-year changes. Long-difference variant uses 2024 minus 2000 country changes with HC3 robust inference.

## Inference Audit

- Panel standard errors are clustered by country.
- Long-difference standard errors are HC3.
- Leave-one-country sensitivity is reported for key models.

## Remaining Questions

- Should "trade barriers" be modeled with domestic import tariffs by product instead of aggregate WDI tariffs?
- Should export growth be separated by sector, especially manufacturing versus commodities?
- Should re-export hubs be modeled separately?
- Should price shocks be filtered with product-level unit values or sector deflators?
"""
    (OUT_DIR / "adversarial_review.md").write_text(review)


def write_manifest(panel: pd.DataFrame, change: pd.DataFrame, results: pd.DataFrame, diagnostics: pd.DataFrame) -> None:
    manifest = {
        "created_at_utc": now_utc(),
        "country_sample": COUNTRY_SAMPLE,
        "years": [START_YEAR, END_YEAR],
        "panel_rows": int(len(panel)),
        "panel_countries": int(panel["iso3"].nunique()),
        "change_rows": int(len(change)),
        "models": sorted(results["model_id"].unique()),
        "outputs": {
            "panel": rel(OUT_DIR / "import_gini_mechanism_panel.csv"),
            "change_panel": rel(OUT_DIR / "import_gini_mechanism_change_panel.csv"),
            "results": rel(OUT_DIR / "import_gini_mechanism_regression_results.csv"),
            "diagnostics": rel(OUT_DIR / "sample_diagnostics.csv"),
            "markdown": rel(OUT_DIR / "import_gini_mechanism_regressions.md"),
            "html_section": rel(OUT_DIR / "import_gini_mechanism_regressions_section.html"),
            "adversarial_review": rel(OUT_DIR / "adversarial_review.md"),
        },
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def main() -> None:
    ensure_dirs()
    panel, change, _classification = build_panel(refresh_wdi=False)
    results, samples = run_models(panel, change)
    panel_specs, change_specs, _ = main_specs()
    loo_specs = [
        next(spec for spec in panel_specs if spec.model_id == "panel_country_year_fe"),
        next(spec for spec in panel_specs if spec.model_id == "panel_first_difference_year_fe"),
        next(spec for spec in change_specs if spec.model_id == "change_combined"),
    ]
    loo = leave_one_country_robustness(panel, change, loo_specs)
    diagnostics = sample_diagnostics(panel, change, samples)

    panel.to_csv(OUT_DIR / "import_gini_mechanism_panel.csv", index=False)
    change.to_csv(OUT_DIR / "import_gini_mechanism_change_panel.csv", index=False)
    results.to_csv(OUT_DIR / "import_gini_mechanism_regression_results.csv", index=False)
    loo.to_csv(OUT_DIR / "leave_one_country_robustness.csv", index=False)
    diagnostics.to_csv(OUT_DIR / "sample_diagnostics.csv", index=False)

    plot_effects(results)
    plot_long_difference_scatter(change)
    write_markdown(results, loo, diagnostics)
    write_html_section(results, loo, diagnostics)
    write_adversarial_review(panel, change, results, diagnostics)
    write_manifest(panel, change, results, diagnostics)
    print(f"Wrote {rel(OUT_DIR)}")
    print(f"Panel rows: {len(panel)}; countries: {panel['iso3'].nunique()}; years: {panel['year'].nunique()}")
    print(f"Regression result rows: {len(results)}")


if __name__ == "__main__":
    main()
