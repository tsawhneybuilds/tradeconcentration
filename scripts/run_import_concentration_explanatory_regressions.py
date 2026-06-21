#!/usr/bin/env python3
"""Explain ex-energy import Product Gini changes with exports, income, and trade barriers.

This is a descriptive mechanism exercise for rd2_countries, 2000-2024. It
does not identify causal effects. Product-dependent outcomes inherit the
project rule that HS6 999999 is excluded before aggregation.
"""

from __future__ import annotations

import json
import math
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import statsmodels.formula.api as smf

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "results" / "samples" / "rd2_countries"
OUT_DIR = BASE / "import_concentration_explanatory_regressions"
FIG_DIR = OUT_DIR / "figures"

CLASSIFICATION = (
    BASE
    / "import_energy_gini_diagnostics"
    / "ex_energy_rank_bucket_gini_driver_classification_balanced_2000_2024.csv"
)
IMPORT_BIN_DECOMP = BASE / "exercise_03_tables" / "import_bin_decomposition.csv"
PRODUCT_CONCENTRATION = BASE / "exercise_01_tables" / "product_concentration_all_years.csv"
IMPORT_BIN_DECOMP_PARQUET = ROOT / "data" / "processed" / "samples" / "rd2_countries" / "exercise_03_import_bin_decomposition.parquet"
EXPORT_CONCENTRATION_PARQUET = ROOT / "data" / "processed" / "samples" / "rd2_countries" / "exercise_02_export_concentration_panel.parquet"
PPP_CONTROLS_CACHE = ROOT / "data" / "processed" / "samples" / "rd2_countries" / "ppp_hump_world_bank_controls.csv"
FUTURE_GROWTH_WDI_CACHE = ROOT / "data" / "processed" / "samples" / "rd2_countries" / "future_growth_concentration_world_bank_controls.csv"
GROWTH_EXPORT_WDI_CACHE = ROOT / "data" / "processed" / "samples" / "rd2_countries" / "growth_effect_world_bank_export_controls.csv"
PPP_COMMON_PANEL = BASE / "ppp_hump_regression_tables" / "ppp_hump_common_sample_panel.csv"

START_YEAR = 2000
END_YEAR = 2024
WDI_URL = "https://api.worldbank.org/v2/country/{countries}/indicator/{indicator}"
WDI_BATCH_SIZE = 20
WDI_INDICATORS = {
    "NE.TRD.GNFS.ZS": "wdi_goods_services_trade_openness_pct_gdp",
    "TM.TAX.MRCH.WM.AR.ZS": "tariff_applied_weighted_mean_pct",
}
MICROSTATE_ISO3 = {"ISL", "LUX", "GUY"}
LOGISTICS_HUB_ISO3 = {"HKG", "SGP", "NLD", "BEL", "LUX", "PAN", "CHE"}
FORMULA_FUNCTION_TOKENS = {"C"}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def validate_unique(df: pd.DataFrame, keys: list[str], label: str) -> None:
    missing = [col for col in keys if col not in df.columns]
    if missing:
        raise RuntimeError(f"{label} is missing key columns: {missing}")
    dupes = int(df.duplicated(keys).sum())
    if dupes:
        examples = df.loc[df.duplicated(keys, keep=False), keys].head(8).to_dict("records")
        raise RuntimeError(f"{label} has duplicate keys on {keys}: {examples}")


def safe_log(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    return np.where(values > 0, np.log(values), np.nan)


def formula_columns(formula: str, df: pd.DataFrame) -> list[str]:
    """Return dataframe columns referenced by the simple patsy formulas used here."""
    tokens = set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", formula))
    tokens -= FORMULA_FUNCTION_TOKENS
    return sorted(token for token in tokens if token in df.columns)


def entity_labels(df: pd.DataFrame, iso3s: list[str]) -> str:
    if not iso3s:
        return ""
    if "country" not in df.columns:
        return ", ".join(sorted(iso3s))
    labels = (
        df[["iso3", "country"]]
        .dropna(subset=["iso3"])
        .drop_duplicates("iso3")
        .assign(iso3=lambda x: x["iso3"].astype(str).str.upper())
        .set_index("iso3")["country"]
        .to_dict()
    )
    return "; ".join(f"{labels.get(iso3, iso3)} ({iso3})" for iso3 in sorted(iso3s))


def fetch_wdi_indicator(iso3s: list[str], indicator: str, value_col: str, start_year: int, end_year: int) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for start in range(0, len(iso3s), WDI_BATCH_SIZE):
        countries = ";".join(sorted(set(iso3s[start : start + WDI_BATCH_SIZE])))
        page = 1
        pages = 1
        while page <= pages:
            response = requests.get(
                WDI_URL.format(countries=countries, indicator=indicator),
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
                    rows.append({"iso3": iso3, "year": int(item["date"]), value_col: value})
            page += 1
            time.sleep(0.1)
    out = pd.DataFrame(rows, columns=["iso3", "year", value_col])
    if out.empty:
        return out
    out[value_col] = pd.to_numeric(out[value_col], errors="coerce")
    out["iso3"] = out["iso3"].astype(str).str.upper()
    out["year"] = pd.to_numeric(out["year"], errors="coerce")
    out = out.dropna(subset=["iso3", "year"]).copy()
    out["year"] = out["year"].astype(int)
    return out.drop_duplicates(["iso3", "year"], keep="last")


def load_or_fetch_wdi_controls(iso3s: list[str], refresh: bool = False) -> pd.DataFrame:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cache = OUT_DIR / "wdi_controls_2000_2024.csv"
    existing_cols = [
        "iso3",
        "year",
        "gdp_pc_ppp_constant_2021_intl_usd",
        "population",
        "gdp_current_usd",
        "real_exports_goods_services_constant_2015_usd",
    ]
    expected_cols = [*existing_cols, *WDI_INDICATORS.values()]
    if cache.exists() and not refresh:
        controls = pd.read_csv(cache)
        if set(expected_cols).issubset(controls.columns):
            controls["iso3"] = controls["iso3"].astype(str).str.upper()
            controls["year"] = pd.to_numeric(controls["year"], errors="coerce").astype("Int64")
            controls = controls.dropna(subset=["iso3", "year"]).copy()
            controls["year"] = controls["year"].astype(int)
            validate_unique(controls, ["iso3", "year"], "cached WDI controls")
            return controls[expected_cols].copy()

    controls = pd.DataFrame(
        [(iso3, year) for iso3 in sorted(set(iso3s)) for year in range(START_YEAR, END_YEAR + 1)],
        columns=["iso3", "year"],
    )
    if PPP_CONTROLS_CACHE.exists():
        ppp = pd.read_csv(PPP_CONTROLS_CACHE)
        controls = controls.merge(
            ppp[["iso3", "year", "gdp_pc_ppp_constant_2021_intl_usd"]],
            on=["iso3", "year"],
            how="left",
            validate="one_to_one",
        )
    if FUTURE_GROWTH_WDI_CACHE.exists():
        fg = pd.read_csv(FUTURE_GROWTH_WDI_CACHE)
        controls = controls.merge(
            fg[["iso3", "year", "population", "gdp_current_usd"]],
            on=["iso3", "year"],
            how="left",
            validate="one_to_one",
        )
    if GROWTH_EXPORT_WDI_CACHE.exists():
        growth = pd.read_csv(GROWTH_EXPORT_WDI_CACHE)
        controls = controls.merge(
            growth[["iso3", "year", "real_exports_constant_2015_usd"]].rename(
                columns={"real_exports_constant_2015_usd": "real_exports_goods_services_constant_2015_usd"}
            ),
            on=["iso3", "year"],
            how="left",
            validate="one_to_one",
        )

    for indicator, value_col in WDI_INDICATORS.items():
        try:
            fetched = fetch_wdi_indicator(sorted(set(iso3s)), indicator, value_col, START_YEAR, END_YEAR)
            controls = controls.merge(fetched, on=["iso3", "year"], how="left", validate="one_to_one")
        except Exception as exc:
            print(f"WDI fetch warning for {indicator}: {exc}", file=sys.stderr)
            controls[value_col] = np.nan
    controls.to_csv(cache, index=False)
    validate_unique(controls, ["iso3", "year"], "WDI controls")
    return controls


def load_outcome_panel(classification: pd.DataFrame) -> pd.DataFrame:
    decomp = pd.read_parquet(IMPORT_BIN_DECOMP_PARQUET) if IMPORT_BIN_DECOMP_PARQUET.exists() else pd.read_csv(IMPORT_BIN_DECOMP)
    required = {
        "country",
        "iso3",
        "reporter_code",
        "year",
        "import_bin",
        "product_gini_without_bin",
        "active_products_without_bin",
        "total_imports_without_bin",
        "total_product_gini",
    }
    missing = sorted(required - set(decomp.columns))
    if missing:
        raise RuntimeError(f"Import bin decomposition missing columns: {missing}")
    panel = decomp[
        decomp["import_bin"].eq("energy")
        & decomp["year"].between(START_YEAR, END_YEAR)
        & decomp["iso3"].isin(classification["iso3"])
    ].copy()
    panel = panel.rename(
        columns={
            "product_gini_without_bin": "ex_energy_import_product_gini",
            "active_products_without_bin": "active_nonenergy_import_products",
            "total_imports_without_bin": "nonenergy_import_value",
            "total_product_gini": "with_energy_import_product_gini",
        }
    )
    keep = [
        "country",
        "iso3",
        "reporter_code",
        "year",
        "ex_energy_import_product_gini",
        "with_energy_import_product_gini",
        "active_nonenergy_import_products",
        "nonenergy_import_value",
        "total_imports",
    ]
    panel = panel[keep].copy()
    validate_unique(panel, ["iso3", "year"], "ex-energy import outcome panel")
    return panel


def load_goods_export_panel(classification: pd.DataFrame) -> pd.DataFrame:
    exports = (
        pd.read_parquet(EXPORT_CONCENTRATION_PARQUET)
        if EXPORT_CONCENTRATION_PARQUET.exists()
        else pd.read_csv(PRODUCT_CONCENTRATION)
    )
    value_col = "total_exports" if "total_exports" in exports.columns else "total_trade_value"
    exports = exports[
        exports["flow"].eq("Exports")
        & exports["variant"].eq("baseline")
        & exports["year"].between(START_YEAR, END_YEAR)
        & exports["iso3"].isin(classification["iso3"])
    ].copy()
    exports = exports.rename(columns={value_col: "goods_exports_current_usd"})
    exports = exports[["iso3", "year", "goods_exports_current_usd", "product_gini", "product_active_count"]].copy()
    exports = exports.rename(
        columns={
            "product_gini": "export_product_gini",
            "product_active_count": "export_active_products",
        }
    )
    validate_unique(exports, ["iso3", "year"], "goods export panel")
    return exports


def load_oil_share() -> pd.DataFrame:
    if not PPP_COMMON_PANEL.exists():
        return pd.DataFrame(columns=["iso3", "year", "oil_export_share"])
    ppp = pd.read_csv(PPP_COMMON_PANEL, usecols=["iso3", "year", "oil_export_share"])
    ppp["iso3"] = ppp["iso3"].astype(str).str.upper()
    ppp["year"] = pd.to_numeric(ppp["year"], errors="coerce").astype("Int64")
    ppp = ppp.dropna(subset=["iso3", "year"]).copy()
    ppp["year"] = ppp["year"].astype(int)
    validate_unique(ppp, ["iso3", "year"], "oil share panel")
    return ppp


def add_panel_variables(panel: pd.DataFrame) -> pd.DataFrame:
    panel = panel.sort_values(["iso3", "year"]).copy()
    for col in [
        "goods_exports_current_usd",
        "real_exports_goods_services_constant_2015_usd",
        "gdp_pc_ppp_constant_2021_intl_usd",
        "population",
    ]:
        panel[f"log_{col}"] = safe_log(panel[col])
    panel["log_goods_exports_per_capita"] = panel["log_goods_exports_current_usd"] - panel["log_population"]
    panel["log_real_exports_per_capita"] = (
        panel["log_real_exports_goods_services_constant_2015_usd"] - panel["log_population"]
    )
    panel["merchandise_trade_openness_pct_gdp"] = np.where(
        pd.to_numeric(panel["gdp_current_usd"], errors="coerce") > 0,
        100
        * (
            pd.to_numeric(panel["total_imports"], errors="coerce")
            + pd.to_numeric(panel["goods_exports_current_usd"], errors="coerce")
        )
        / pd.to_numeric(panel["gdp_current_usd"], errors="coerce"),
        np.nan,
    )
    panel["trade_openness_pct_gdp"] = panel["merchandise_trade_openness_pct_gdp"]
    diff_cols = [
        "ex_energy_import_product_gini",
        "log_goods_exports_current_usd",
        "log_real_exports_goods_services_constant_2015_usd",
        "log_gdp_pc_ppp_constant_2021_intl_usd",
        "trade_openness_pct_gdp",
        "merchandise_trade_openness_pct_gdp",
        "wdi_goods_services_trade_openness_pct_gdp",
        "tariff_applied_weighted_mean_pct",
    ]
    for col in diff_cols:
        panel[f"d_{col}"] = panel.groupby("iso3")[col].diff()
        panel[f"l1_d_{col}"] = panel.groupby("iso3")[f"d_{col}"].shift(1)
    return panel


def nearest_window_value(panel: pd.DataFrame, iso3: str, col: str, years: range, which: str) -> tuple[float, int | None]:
    sub = panel[panel["iso3"].eq(iso3) & panel["year"].isin(list(years))][["year", col]].copy()
    sub[col] = pd.to_numeric(sub[col], errors="coerce")
    sub = sub.dropna(subset=[col])
    if sub.empty:
        return np.nan, None
    sub = sub.sort_values("year")
    row = sub.iloc[0] if which == "start" else sub.iloc[-1]
    return float(row[col]), int(row["year"])


def build_country_change_panel(panel: pd.DataFrame, classification: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    panel_by = panel.set_index(["iso3", "year"])
    for row in classification.itertuples(index=False):
        iso3 = str(row.iso3)
        if (iso3, START_YEAR) not in panel_by.index or (iso3, END_YEAR) not in panel_by.index:
            continue
        start = panel_by.loc[(iso3, START_YEAR)]
        end = panel_by.loc[(iso3, END_YEAR)]
        tariff_start, tariff_start_year = nearest_window_value(
            panel, iso3, "tariff_applied_weighted_mean_pct", range(START_YEAR, START_YEAR + 6), "start"
        )
        tariff_end, tariff_end_year = nearest_window_value(
            panel, iso3, "tariff_applied_weighted_mean_pct", range(END_YEAR - 5, END_YEAR + 1), "end"
        )
        rows.append(
            {
                "country": row.country,
                "iso3": iso3,
                "reporter_code": int(row.reporter_code),
                "main_driver_group": row.main_driver_group,
                "gini_change_direction": row.gini_change_direction,
                "is_gini_increase": 1 if str(row.gini_change_direction) == "increase" else 0,
                "is_top5_superstar": 1 if str(row.main_driver_group) == "top-5 superstar concentration" else 0,
                "delta_panel_ex_energy_gini": float(row.delta_panel_ex_energy_gini),
                "delta_calculated_ex_energy_gini": float(row.delta_calculated_ex_energy_gini),
                "start_ex_energy_import_product_gini": start["ex_energy_import_product_gini"],
                "end_ex_energy_import_product_gini": end["ex_energy_import_product_gini"],
                "log_goods_exports_2000": start["log_goods_exports_current_usd"],
                "log_goods_exports_2024": end["log_goods_exports_current_usd"],
                "goods_export_growth_2000_2024": end["log_goods_exports_current_usd"]
                - start["log_goods_exports_current_usd"],
                "log_real_exports_2000": start["log_real_exports_goods_services_constant_2015_usd"],
                "real_export_growth_2000_2024": end["log_real_exports_goods_services_constant_2015_usd"]
                - start["log_real_exports_goods_services_constant_2015_usd"],
                "log_goods_exports_per_capita_2000": start["log_goods_exports_per_capita"],
                "log_gdp_pc_ppp_2000": start["log_gdp_pc_ppp_constant_2021_intl_usd"],
                "gdp_pc_ppp_growth_2000_2024": end["log_gdp_pc_ppp_constant_2021_intl_usd"]
                - start["log_gdp_pc_ppp_constant_2021_intl_usd"],
                "trade_openness_pct_gdp_2000": start["trade_openness_pct_gdp"],
                "trade_openness_change_2000_2024": end["trade_openness_pct_gdp"]
                - start["trade_openness_pct_gdp"],
                "merchandise_trade_openness_pct_gdp_2000": start["merchandise_trade_openness_pct_gdp"],
                "merchandise_trade_openness_change_2000_2024": end["merchandise_trade_openness_pct_gdp"]
                - start["merchandise_trade_openness_pct_gdp"],
                "wdi_goods_services_trade_openness_pct_gdp_2000": start[
                    "wdi_goods_services_trade_openness_pct_gdp"
                ],
                "wdi_goods_services_trade_openness_change_2000_2024": end[
                    "wdi_goods_services_trade_openness_pct_gdp"
                ]
                - start["wdi_goods_services_trade_openness_pct_gdp"],
                "tariff_applied_weighted_start_nearest": tariff_start,
                "tariff_applied_weighted_end_nearest": tariff_end,
                "tariff_applied_weighted_change_nearest": tariff_end - tariff_start
                if np.isfinite(tariff_start) and np.isfinite(tariff_end)
                else np.nan,
                "tariff_start_year": tariff_start_year,
                "tariff_end_year": tariff_end_year,
                "log_population_2000": start["log_population"],
                "oil_export_share_2000": start["oil_export_share"],
            }
        )
    out = pd.DataFrame(rows)
    validate_unique(out, ["iso3"], "country change panel")
    return out


def run_model(
    df: pd.DataFrame,
    model_id: str,
    family: str,
    formula: str,
    hypothesis: str,
    interpretation_unit: str,
    cluster_col: str | None = None,
) -> tuple[dict[str, Any], pd.DataFrame, dict[str, Any]]:
    existing_needed = formula_columns(formula, df)
    base = df.replace([np.inf, -np.inf], np.nan).copy()
    work = base.dropna(subset=existing_needed).copy()
    input_entities = sorted(base["iso3"].dropna().astype(str).str.upper().unique().tolist()) if "iso3" in base.columns else []
    complete_entities = sorted(work["iso3"].dropna().astype(str).str.upper().unique().tolist()) if "iso3" in work.columns else []
    excluded_entities = sorted(set(input_entities) - set(complete_entities))
    missing_counts = {
        col: int(base[col].isna().sum())
        for col in existing_needed
        if col in base.columns and int(base[col].isna().sum()) > 0
    }
    sample_info = {
        "model_id": model_id,
        "family": family,
        "formula_columns": "; ".join(existing_needed),
        "input_rows": int(len(base)),
        "complete_rows": int(len(work)),
        "dropped_rows": int(len(base) - len(work)),
        "input_countries": int(len(input_entities)),
        "complete_countries": int(len(complete_entities)),
        "excluded_countries_count": int(len(excluded_entities)),
        "excluded_countries": entity_labels(base, excluded_entities),
        "complete_countries_list": entity_labels(work, complete_entities),
        "missing_columns_summary": "; ".join(f"{col}:{count}" for col, count in sorted(missing_counts.items())),
    }
    if work.empty:
        return (
            {
                "model_id": model_id,
                "family": family,
                "formula": formula,
                "hypothesis": hypothesis,
                "interpretation_unit": interpretation_unit,
                "status": "no_complete_rows",
                "nobs": 0,
                "entities": 0,
                "years": 0,
                "input_rows": int(len(base)),
                "dropped_rows": int(len(base)),
                "rsquared": np.nan,
                "adj_rsquared": np.nan,
            },
            pd.DataFrame(),
            sample_info,
        )
    try:
        fitted = smf.ols(formula, data=work).fit()
        if cluster_col is not None:
            robust = fitted.get_robustcov_results(cov_type="cluster", groups=work[cluster_col])
            covariance = f"clustered by {cluster_col}"
        else:
            robust = fitted.get_robustcov_results(cov_type="HC3")
            covariance = "HC3 heteroskedasticity-robust"
    except Exception as exc:
        return (
            {
                "model_id": model_id,
                "family": family,
                "formula": formula,
                "hypothesis": hypothesis,
                "interpretation_unit": interpretation_unit,
                "status": f"failed: {exc}",
                "nobs": int(len(work)),
                "entities": int(work["iso3"].nunique()) if "iso3" in work.columns else 0,
                "years": int(work["year"].nunique()) if "year" in work.columns else 0,
                "input_rows": int(len(base)),
                "dropped_rows": int(len(base) - len(work)),
                "rsquared": np.nan,
                "adj_rsquared": np.nan,
            },
            pd.DataFrame(),
            sample_info,
        )
    names = robust.model.exog_names
    coef = pd.Series(np.asarray(robust.params), index=names)
    se = pd.Series(np.asarray(robust.bse), index=names)
    pval = pd.Series(np.asarray(robust.pvalues), index=names)
    tval = pd.Series(np.asarray(robust.tvalues), index=names)
    terms = []
    for term in names:
        if term == "Intercept" or term.startswith("C(year)") or term.startswith("C(iso3)"):
            continue
        terms.append(
            {
                "model_id": model_id,
                "family": family,
                "term": term,
                "coef": float(coef[term]),
                "std_error": float(se[term]),
                "t_stat": float(tval[term]),
                "p_value": float(pval[term]),
                "significant_05": bool(pval[term] < 0.05) if np.isfinite(pval[term]) else False,
                "interpretation_unit": interpretation_unit,
            }
        )
    summary = {
        "model_id": model_id,
        "family": family,
        "formula": formula,
        "hypothesis": hypothesis,
        "interpretation_unit": interpretation_unit,
        "status": "ok",
        "covariance": covariance,
        "nobs": int(robust.nobs),
        "entities": int(work["iso3"].nunique()) if "iso3" in work.columns else 0,
        "years": int(work["year"].nunique()) if "year" in work.columns else 0,
        "input_rows": int(len(base)),
        "dropped_rows": int(len(base) - len(work)),
        "rsquared": float(getattr(robust, "rsquared", np.nan)),
        "adj_rsquared": float(getattr(robust, "rsquared_adj", np.nan)),
    }
    return summary, pd.DataFrame(terms), sample_info


def run_regressions(country_change: pd.DataFrame, panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    no_micro = country_change[~country_change["iso3"].isin(MICROSTATE_ISO3)].copy()
    no_hubs = country_change[~country_change["iso3"].isin(LOGISTICS_HUB_ISO3)].copy()
    panel_no_hubs = panel[~panel["iso3"].isin(LOGISTICS_HUB_ISO3)].copy()
    model_specs = [
        (
            country_change,
            "xs_exports",
            "cross-country change",
            "delta_panel_ex_energy_gini ~ log_goods_exports_2000 + goods_export_growth_2000_2024 + log_population_2000",
            "Nominal merchandise export scale and export growth explain which countries' ex-energy import concentration rose from 2000 to 2024.",
            "A one-unit log change is about a 2.7x change in nominal merchandise exports.",
            None,
        ),
        (
            country_change,
            "xs_real_exports",
            "cross-country robustness",
            "delta_panel_ex_energy_gini ~ log_real_exports_2000 + real_export_growth_2000_2024 + log_population_2000",
            "WDI real export scale and growth explain country-level concentration change.",
            "A one-unit log change is about a 2.7x change in WDI real goods-and-services exports.",
            None,
        ),
        (
            country_change,
            "xs_income",
            "cross-country change",
            "delta_panel_ex_energy_gini ~ log_gdp_pc_ppp_2000 + gdp_pc_ppp_growth_2000_2024 + log_population_2000",
            "Development level and development growth explain the 2000-2024 concentration change.",
            "A one-unit log change is about a 2.7x change in PPP GDP per capita.",
            None,
        ),
        (
            country_change,
            "xs_openness",
            "cross-country change",
            "delta_panel_ex_energy_gini ~ trade_openness_pct_gdp_2000 + trade_openness_change_2000_2024 + log_population_2000",
            "More open economies, or economies that become more open, experience different import-concentration changes.",
            "Trade openness and its change are in percentage points of GDP.",
            None,
        ),
        (
            country_change,
            "xs_full",
            "cross-country change",
            "delta_panel_ex_energy_gini ~ log_goods_exports_2000 + goods_export_growth_2000_2024 + log_gdp_pc_ppp_2000 + gdp_pc_ppp_growth_2000_2024 + trade_openness_pct_gdp_2000 + trade_openness_change_2000_2024 + log_population_2000",
            "Export scale/growth, income level/growth, and openness jointly explain country-level concentration change.",
            "Continuous country-change association; outcome is Gini-point change.",
            None,
        ),
        (
            country_change,
            "xs_full_real_exports",
            "cross-country robustness",
            "delta_panel_ex_energy_gini ~ log_real_exports_2000 + real_export_growth_2000_2024 + log_gdp_pc_ppp_2000 + gdp_pc_ppp_growth_2000_2024 + trade_openness_pct_gdp_2000 + trade_openness_change_2000_2024 + log_population_2000",
            "The preferred change-model result survives when export level and growth are measured with WDI real goods-and-services exports.",
            "Real export level/growth robustness; outcome is Gini-point change.",
            None,
        ),
        (
            no_micro,
            "xs_full_no_microstates",
            "cross-country robustness",
            "delta_panel_ex_energy_gini ~ log_goods_exports_2000 + goods_export_growth_2000_2024 + log_gdp_pc_ppp_2000 + gdp_pc_ppp_growth_2000_2024 + trade_openness_pct_gdp_2000 + trade_openness_change_2000_2024 + log_population_2000",
            "The preferred change-model result is not driven by Iceland, Luxembourg, and Guyana.",
            "Same as preferred cross-country model after Cadot-style small-country exclusion.",
            None,
        ),
        (
            no_hubs,
            "xs_full_no_logistics_hubs",
            "cross-country robustness",
            "delta_panel_ex_energy_gini ~ log_goods_exports_2000 + goods_export_growth_2000_2024 + log_gdp_pc_ppp_2000 + gdp_pc_ppp_growth_2000_2024 + trade_openness_pct_gdp_2000 + trade_openness_change_2000_2024 + log_population_2000",
            "The preferred change-model result is not driven by small/logistics-heavy hub economies.",
            "Same as preferred cross-country model excluding Hong Kong, Singapore, Netherlands, Belgium, Luxembourg, Panama, and Switzerland.",
            None,
        ),
        (
            country_change,
            "xs_full_wdi_openness",
            "cross-country robustness",
            "delta_panel_ex_energy_gini ~ log_goods_exports_2000 + goods_export_growth_2000_2024 + log_gdp_pc_ppp_2000 + gdp_pc_ppp_growth_2000_2024 + wdi_goods_services_trade_openness_pct_gdp_2000 + wdi_goods_services_trade_openness_change_2000_2024 + log_population_2000",
            "The openness result survives if openness is measured with WDI goods-and-services trade rather than merchandise Comtrade openness.",
            "WDI openness and its change are in percentage points of GDP.",
            None,
        ),
        (
            country_change,
            "xs_per_capita_export_robust",
            "cross-country robustness",
            "delta_panel_ex_energy_gini ~ log_goods_exports_per_capita_2000 + goods_export_growth_2000_2024 + log_gdp_pc_ppp_2000 + gdp_pc_ppp_growth_2000_2024 + trade_openness_pct_gdp_2000 + trade_openness_change_2000_2024",
            "The export result is not just country size: use export level per person instead of export level plus population.",
            "Export-per-capita level is logged; outcome is Gini-point change.",
            None,
        ),
        (
            country_change,
            "xs_tariff_robust",
            "cross-country tariff robustness",
            "delta_panel_ex_energy_gini ~ log_goods_exports_2000 + goods_export_growth_2000_2024 + log_gdp_pc_ppp_2000 + gdp_pc_ppp_growth_2000_2024 + trade_openness_pct_gdp_2000 + trade_openness_change_2000_2024 + tariff_applied_weighted_start_nearest + tariff_applied_weighted_change_nearest + log_population_2000",
            "Applied tariff levels and changes add explanatory power once export, income, and openness are included.",
            "Tariffs are WDI weighted mean applied tariff percentage points; reduced sample.",
            None,
        ),
        (
            country_change,
            "xs_increase_lpm",
            "cross-country group LPM",
            "is_gini_increase ~ log_goods_exports_2000 + goods_export_growth_2000_2024 + log_gdp_pc_ppp_2000 + gdp_pc_ppp_growth_2000_2024 + trade_openness_pct_gdp_2000 + trade_openness_change_2000_2024 + log_population_2000",
            "The same covariates predict whether a country is classified as an increase rather than stable/decrease.",
            "Linear probability model; coefficients are probability-point changes.",
            None,
        ),
        (
            panel,
            "panel_pooled_year_fe",
            "annual panel pooled/year FE",
            "ex_energy_import_product_gini ~ log_goods_exports_current_usd + log_gdp_pc_ppp_constant_2021_intl_usd + trade_openness_pct_gdp + log_population + oil_export_share + C(year)",
            "Across countries within a given year, export level, income, and openness are associated with ex-energy import concentration levels.",
            "Country-year concentration levels; standard errors clustered by country.",
            "iso3",
        ),
        (
            panel,
            "panel_country_year_fe",
            "annual panel country+year FE",
            "ex_energy_import_product_gini ~ log_goods_exports_current_usd + log_gdp_pc_ppp_constant_2021_intl_usd + trade_openness_pct_gdp + oil_export_share + C(iso3) + C(year)",
            "Within a country over time, export level, income, and openness co-move with ex-energy import concentration after global-year shocks are absorbed.",
            "Within-country association; standard errors clustered by country.",
            "iso3",
        ),
        (
            panel,
            "panel_country_year_fe_real_exports",
            "annual panel robustness",
            "ex_energy_import_product_gini ~ log_real_exports_goods_services_constant_2015_usd + log_gdp_pc_ppp_constant_2021_intl_usd + trade_openness_pct_gdp + oil_export_share + C(iso3) + C(year)",
            "Within a country over time, WDI real exports co-move with ex-energy import concentration after global-year shocks are absorbed.",
            "Within-country association using real goods-and-services exports; standard errors clustered by country.",
            "iso3",
        ),
        (
            panel_no_hubs,
            "panel_country_year_fe_no_logistics_hubs",
            "annual panel robustness",
            "ex_energy_import_product_gini ~ log_goods_exports_current_usd + log_gdp_pc_ppp_constant_2021_intl_usd + trade_openness_pct_gdp + oil_export_share + C(iso3) + C(year)",
            "The within-country openness result is not driven only by logistics-heavy hub economies.",
            "Within-country association after excluding major hubs; standard errors clustered by country.",
            "iso3",
        ),
        (
            panel,
            "panel_country_year_fe_wdi_openness",
            "annual panel robustness",
            "ex_energy_import_product_gini ~ log_goods_exports_current_usd + log_gdp_pc_ppp_constant_2021_intl_usd + wdi_goods_services_trade_openness_pct_gdp + oil_export_share + C(iso3) + C(year)",
            "The within-country openness result survives using WDI goods-and-services openness.",
            "Within-country association using WDI openness; standard errors clustered by country.",
            "iso3",
        ),
        (
            panel,
            "panel_annual_changes",
            "annual first-difference panel",
            "d_ex_energy_import_product_gini ~ d_log_goods_exports_current_usd + d_log_gdp_pc_ppp_constant_2021_intl_usd + d_trade_openness_pct_gdp + C(year)",
            "Annual growth in exports, income, and openness explains annual changes in import concentration.",
            "Annual change in Gini points; standard errors clustered by country.",
            "iso3",
        ),
        (
            panel,
            "panel_annual_changes_real_exports",
            "annual first-difference robustness",
            "d_ex_energy_import_product_gini ~ d_log_real_exports_goods_services_constant_2015_usd + d_log_gdp_pc_ppp_constant_2021_intl_usd + d_trade_openness_pct_gdp + C(year)",
            "Annual WDI real-export growth, income growth, and openness change explain annual changes in import concentration.",
            "Annual change in Gini points; standard errors clustered by country.",
            "iso3",
        ),
        (
            panel,
            "panel_lagged_annual_changes",
            "annual lagged first-difference panel",
            "d_ex_energy_import_product_gini ~ l1_d_log_goods_exports_current_usd + l1_d_log_gdp_pc_ppp_constant_2021_intl_usd + l1_d_trade_openness_pct_gdp + C(year)",
            "Lagged annual export growth, income growth, and openness change predict the next annual concentration change.",
            "Annual change in Gini points; right-hand-side changes are lagged one year; standard errors clustered by country.",
            "iso3",
        ),
        (
            panel,
            "panel_lagged_annual_changes_real_exports",
            "annual lagged first-difference robustness",
            "d_ex_energy_import_product_gini ~ l1_d_log_real_exports_goods_services_constant_2015_usd + l1_d_log_gdp_pc_ppp_constant_2021_intl_usd + l1_d_trade_openness_pct_gdp + C(year)",
            "Lagged WDI real-export growth, income growth, and openness change predict the next annual concentration change.",
            "Annual change in Gini points; right-hand-side changes are lagged one year; standard errors clustered by country.",
            "iso3",
        ),
        (
            panel,
            "panel_tariff_country_year_fe",
            "annual tariff robustness",
            "ex_energy_import_product_gini ~ log_goods_exports_current_usd + log_gdp_pc_ppp_constant_2021_intl_usd + trade_openness_pct_gdp + tariff_applied_weighted_mean_pct + C(iso3) + C(year)",
            "Applied tariff barriers are associated with import concentration within countries over time.",
            "Tariff percentage points; reduced country-year sample.",
            "iso3",
        ),
    ]
    summaries: list[dict[str, Any]] = []
    term_frames: list[pd.DataFrame] = []
    sample_rows: list[dict[str, Any]] = []
    for data, model_id, family, formula, hypothesis, interpretation_unit, cluster in model_specs:
        summary, terms, sample_info = run_model(
            data, model_id, family, formula, hypothesis, interpretation_unit, cluster_col=cluster
        )
        summaries.append(summary)
        sample_rows.append(sample_info)
        if not terms.empty:
            term_frames.append(terms)
    return (
        pd.DataFrame(summaries),
        pd.concat(term_frames, ignore_index=True) if term_frames else pd.DataFrame(),
        pd.DataFrame(sample_rows),
    )


def fit_term_for_influence(df: pd.DataFrame, formula: str, term: str) -> dict[str, Any]:
    cols = formula_columns(formula, df)
    work = df.replace([np.inf, -np.inf], np.nan).dropna(subset=cols).copy()
    if work.empty:
        return {
            "nobs": 0,
            "countries": 0,
            "coef": np.nan,
            "std_error": np.nan,
            "p_value": np.nan,
            "status": "no_complete_rows",
        }
    try:
        fitted = smf.ols(formula, data=work).fit()
        robust = fitted.get_robustcov_results(cov_type="HC3")
        names = robust.model.exog_names
        if term not in names:
            return {
                "nobs": int(robust.nobs),
                "countries": int(work["iso3"].nunique()),
                "coef": np.nan,
                "std_error": np.nan,
                "p_value": np.nan,
                "status": "term_not_in_model",
            }
        idx = names.index(term)
        return {
            "nobs": int(robust.nobs),
            "countries": int(work["iso3"].nunique()),
            "coef": float(np.asarray(robust.params)[idx]),
            "std_error": float(np.asarray(robust.bse)[idx]),
            "p_value": float(np.asarray(robust.pvalues)[idx]),
            "status": "ok",
        }
    except Exception as exc:
        return {
            "nobs": int(len(work)),
            "countries": int(work["iso3"].nunique()) if "iso3" in work.columns else 0,
            "coef": np.nan,
            "std_error": np.nan,
            "p_value": np.nan,
            "status": f"failed: {exc}",
        }


def make_leave_one_country_influence(country_change: pd.DataFrame) -> pd.DataFrame:
    specs = [
        (
            "xs_full",
            "delta_panel_ex_energy_gini ~ log_goods_exports_2000 + goods_export_growth_2000_2024 + log_gdp_pc_ppp_2000 + gdp_pc_ppp_growth_2000_2024 + trade_openness_pct_gdp_2000 + trade_openness_change_2000_2024 + log_population_2000",
            "trade_openness_change_2000_2024",
        ),
        (
            "xs_full_real_exports",
            "delta_panel_ex_energy_gini ~ log_real_exports_2000 + real_export_growth_2000_2024 + log_gdp_pc_ppp_2000 + gdp_pc_ppp_growth_2000_2024 + trade_openness_pct_gdp_2000 + trade_openness_change_2000_2024 + log_population_2000",
            "trade_openness_change_2000_2024",
        ),
    ]
    rows: list[dict[str, Any]] = []
    country_lookup = (
        country_change[["iso3", "country"]]
        .drop_duplicates("iso3")
        .assign(iso3=lambda x: x["iso3"].astype(str).str.upper())
        .set_index("iso3")["country"]
        .to_dict()
    )
    for model_id, formula, term in specs:
        base = fit_term_for_influence(country_change, formula, term)
        rows.append(
            {
                "model_id": model_id,
                "term": term,
                "omitted_iso3": "FULL",
                "omitted_country": "Full sample",
                **base,
                "significant_05": bool(base["p_value"] < 0.05) if np.isfinite(base["p_value"]) else False,
            }
        )
        for iso3 in sorted(country_change["iso3"].dropna().astype(str).str.upper().unique()):
            sub = country_change[~country_change["iso3"].astype(str).str.upper().eq(iso3)].copy()
            result = fit_term_for_influence(sub, formula, term)
            rows.append(
                {
                    "model_id": model_id,
                    "term": term,
                    "omitted_iso3": iso3,
                    "omitted_country": country_lookup.get(iso3, iso3),
                    **result,
                    "significant_05": bool(result["p_value"] < 0.05) if np.isfinite(result["p_value"]) else False,
                }
            )
    return pd.DataFrame(rows)


def make_tariff_endpoint_diagnostics(country_change: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "country",
        "iso3",
        "tariff_start_year",
        "tariff_end_year",
        "tariff_applied_weighted_start_nearest",
        "tariff_applied_weighted_end_nearest",
        "tariff_applied_weighted_change_nearest",
    ]
    out = country_change[cols].copy()
    out["endpoint_year_span"] = out["tariff_end_year"] - out["tariff_start_year"]
    out["endpoint_note"] = np.where(
        out[["tariff_start_year", "tariff_end_year"]].notna().all(axis=1),
        out["tariff_start_year"].astype("Int64").astype(str)
        + " to "
        + out["tariff_end_year"].astype("Int64").astype(str),
        "missing endpoint",
    )
    return out


def make_diagnostics(classification: pd.DataFrame, panel: pd.DataFrame, country_change: pd.DataFrame) -> pd.DataFrame:
    rows = []
    rows.append({"diagnostic": "classification_countries", "value": int(classification["iso3"].nunique())})
    rows.append({"diagnostic": "panel_rows", "value": int(len(panel))})
    rows.append({"diagnostic": "panel_countries", "value": int(panel["iso3"].nunique())})
    rows.append({"diagnostic": "panel_year_min", "value": int(panel["year"].min())})
    rows.append({"diagnostic": "panel_year_max", "value": int(panel["year"].max())})
    rows.append({"diagnostic": "country_change_rows", "value": int(len(country_change))})
    for col in [
        "ex_energy_import_product_gini",
        "goods_exports_current_usd",
        "gdp_pc_ppp_constant_2021_intl_usd",
        "trade_openness_pct_gdp",
        "tariff_applied_weighted_mean_pct",
    ]:
        rows.append({"diagnostic": f"panel_nonmissing_{col}", "value": int(panel[col].notna().sum())})
        rows.append({"diagnostic": f"panel_countries_nonmissing_{col}", "value": int(panel.loc[panel[col].notna(), "iso3"].nunique())})
    rows.append(
        {
            "diagnostic": "tariff_country_change_complete_rows",
            "value": int(
                country_change[
                    ["tariff_applied_weighted_start_nearest", "tariff_applied_weighted_change_nearest"]
                ]
                .notna()
                .all(axis=1)
                .sum()
            ),
        }
    )
    complete_tariff = country_change[
        ["tariff_applied_weighted_start_nearest", "tariff_applied_weighted_change_nearest"]
    ].notna().all(axis=1)
    tariff_complete = country_change[complete_tariff].copy()
    if not tariff_complete.empty:
        rows.append({"diagnostic": "tariff_start_year_min", "value": int(tariff_complete["tariff_start_year"].min())})
        rows.append({"diagnostic": "tariff_start_year_max", "value": int(tariff_complete["tariff_start_year"].max())})
        rows.append({"diagnostic": "tariff_end_year_min", "value": int(tariff_complete["tariff_end_year"].min())})
        rows.append({"diagnostic": "tariff_end_year_max", "value": int(tariff_complete["tariff_end_year"].max())})
        for year in range(2019, END_YEAR + 1):
            rows.append(
                {
                    "diagnostic": f"tariff_end_year_{year}_count",
                    "value": int(tariff_complete["tariff_end_year"].eq(year).sum()),
                }
            )
    rows.append(
        {
            "diagnostic": "tariff_country_change_missing_endpoint_rows",
            "value": int((~complete_tariff).sum()),
        }
    )
    return pd.DataFrame(rows)


def format_p(value: float) -> str:
    if not np.isfinite(value):
        return "n/a"
    if value < 0.001:
        return "<0.001"
    return f"{value:.3f}"


def write_markdown(
    summary: pd.DataFrame,
    terms: pd.DataFrame,
    diagnostics: pd.DataFrame,
    sample_manifest: pd.DataFrame,
    influence: pd.DataFrame,
    tariff_endpoints: pd.DataFrame,
) -> None:
    model_notes = {
        "xs_exports": "Export scale/growth only, with initial population control.",
        "xs_real_exports": "Real WDI export scale/growth robustness.",
        "xs_income": "Income level/growth only, with initial population control.",
        "xs_openness": "Trade openness level/change only, with initial population control.",
        "xs_full": "Preferred country-change association model.",
        "xs_full_real_exports": "Preferred country-change model with WDI real goods-and-services exports.",
        "xs_full_no_microstates": "Preferred model after excluding Iceland, Luxembourg, and Guyana.",
        "xs_full_no_logistics_hubs": "Preferred model after excluding major logistics/hub economies.",
        "xs_full_wdi_openness": "Preferred model with WDI goods-and-services openness.",
        "xs_per_capita_export_robust": "Replaces export level plus population with export-per-capita level.",
        "xs_tariff_robust": "Reduced-sample tariff robustness.",
        "xs_increase_lpm": "Linear probability model for increase/stable/decrease grouping.",
        "panel_pooled_year_fe": "Pooled country-years with year fixed effects.",
        "panel_country_year_fe": "Country and year fixed effects.",
        "panel_country_year_fe_real_exports": "Country/year FE with WDI real goods-and-services exports.",
        "panel_country_year_fe_no_logistics_hubs": "Country/year FE after excluding major logistics/hub economies.",
        "panel_country_year_fe_wdi_openness": "Country/year FE with WDI goods-and-services openness.",
        "panel_annual_changes": "First-difference annual growth association.",
        "panel_annual_changes_real_exports": "First-difference robustness with WDI real goods-and-services export growth.",
        "panel_tariff_country_year_fe": "Country/year FE tariff robustness.",
    }
    ok_summary = summary[summary["status"].eq("ok")].copy()
    headline_rows = []
    for _, model in ok_summary.iterrows():
        sub = terms[terms["model_id"].eq(model["model_id"])].copy()
        sig = sub[sub["p_value"].lt(0.05)]
        sig_terms = ", ".join(sig["term"].tolist()) if not sig.empty else "none"
        headline_rows.append(
            f"| {model['model_id']} | {model['family']} | {int(model['nobs'])} | {int(model['entities'])} | {model['rsquared']:.3f} | {sig_terms} |"
        )
    selected_terms = terms[
        terms["term"].isin(
            [
                "goods_export_growth_2000_2024",
                "log_real_exports_2000",
                "real_export_growth_2000_2024",
                "log_goods_exports_2000",
                "gdp_pc_ppp_growth_2000_2024",
                "log_gdp_pc_ppp_2000",
                "trade_openness_change_2000_2024",
                "trade_openness_pct_gdp_2000",
                "wdi_goods_services_trade_openness_change_2000_2024",
                "wdi_goods_services_trade_openness_pct_gdp_2000",
                "tariff_applied_weighted_change_nearest",
                "tariff_applied_weighted_start_nearest",
                "log_goods_exports_current_usd",
                "log_real_exports_goods_services_constant_2015_usd",
                "log_gdp_pc_ppp_constant_2021_intl_usd",
                "trade_openness_pct_gdp",
                "wdi_goods_services_trade_openness_pct_gdp",
                "tariff_applied_weighted_mean_pct",
                "d_log_goods_exports_current_usd",
                "d_log_real_exports_goods_services_constant_2015_usd",
                "d_log_gdp_pc_ppp_constant_2021_intl_usd",
                "d_trade_openness_pct_gdp",
                "l1_d_log_goods_exports_current_usd",
                "l1_d_log_real_exports_goods_services_constant_2015_usd",
                "l1_d_log_gdp_pc_ppp_constant_2021_intl_usd",
                "l1_d_trade_openness_pct_gdp",
            ]
        )
    ].copy()
    selected_lines = []
    for _, r in selected_terms.iterrows():
        star = "**" if r["p_value"] < 0.05 else ""
        selected_lines.append(
            f"| {r['model_id']} | {r['term']} | {star}{r['coef']:.4f}{star} | {r['std_error']:.4f} | {star}{format_p(r['p_value'])}{star} |"
        )
    influence_lines = []
    influence_read = influence[
        influence["omitted_iso3"].ne("FULL") & influence["status"].eq("ok") & ~influence["significant_05"]
    ].copy()
    for _, r in influence_read.sort_values(["model_id", "p_value"]).iterrows():
        influence_lines.append(
            f"| {r['model_id']} | {r['omitted_country']} ({r['omitted_iso3']}) | {r['coef']:.4f} | {r['std_error']:.4f} | {format_p(r['p_value'])} |"
        )
    if not influence_lines:
        influence_lines.append("| none | none |  |  |  |")

    sample_lines = []
    for _, r in sample_manifest.sort_values("model_id").iterrows():
        sample_lines.append(
            f"| {r['model_id']} | {int(r['input_rows'])} | {int(r['complete_rows'])} | {int(r['dropped_rows'])} | {int(r['complete_countries'])} | {r['excluded_countries'] or 'none'} | {r['missing_columns_summary'] or 'none'} |"
        )

    tariff_complete = tariff_endpoints.dropna(subset=["tariff_start_year", "tariff_end_year"]).copy()
    tariff_year_lines = []
    if not tariff_complete.empty:
        for year, count in tariff_complete["tariff_end_year"].astype(int).value_counts().sort_index().items():
            tariff_year_lines.append(f"| {year} | {int(count)} |")
    else:
        tariff_year_lines.append("| no complete endpoints | 0 |")

    text = f"""# Import Concentration Explanatory Regressions

Created UTC: `{now_utc()}`

## Purpose

These regressions ask whether ex-energy import Product Gini changes are explained by export scale, export growth, income level, income growth, trade openness, and applied tariff barriers. The exercise is descriptive mechanism evidence, not causal identification.

## Bottom Line

- Nominal merchandise export level, WDI real export level, and income level each look positively related to concentration change in one-variable families, but they stop being informative once exports, income, openness, and population are entered together.
- Nominal merchandise export growth, WDI real export growth, and PPP GDP-per-capita growth do not explain the 2000-2024 concentration change in the preferred cross-country models.
- Merchandise trade openness is the only variable that survives the preferred cross-country specification: countries where merchandise openness rises more also tend to have larger ex-energy import Product Gini increases.
- That cross-country openness result is not fully robust: it survives microstate exclusion but weakens when logistics hubs are removed and disappears when WDI goods-and-services openness replaces merchandise openness.
- In annual panel specifications, within-country increases in merchandise openness are positively associated with import concentration, and this survives hub exclusion and WDI-openness robustness.
- Tariffs do not explain the cross-country change. The annual tariff coefficient is positive in a reduced-sample country/year FE robustness model, but confidence is low because tariff coverage is incomplete, endpoint tariff changes use nearest available years, and the variable is a broad all-product average.
- The cross-country merchandise-openness result is high-leverage sensitive. Leave-one-country checks show the preferred cross-country openness-change coefficient loses p<0.05 when several high-influence countries are omitted.

Best interpretation: export growth and income growth are not doing the work. The strongest descriptive signal is trade openness, especially within-country co-movement, but the cross-country result is sensitive to how openness is measured and to hub economies. Treat this as evidence for a trade-integration/import-basket channel, not proof that free-trade policy caused concentration.

## Data

- Outcome: annual ex-energy import Product Gini, built from `import_bin == energy` rows in `{rel(IMPORT_BIN_DECOMP_PARQUET if IMPORT_BIN_DECOMP_PARQUET.exists() else IMPORT_BIN_DECOMP)}` using `product_gini_without_bin`.
- Country-change outcome: `delta_panel_ex_energy_gini` from `{rel(CLASSIFICATION)}`.
- Main export level/growth: nominal Comtrade merchandise export values from `{rel(EXPORT_CONCENTRATION_PARQUET if EXPORT_CONCENTRATION_PARQUET.exists() else PRODUCT_CONCENTRATION)}`, flow `Exports`, variant `baseline`.
- Export robustness: WDI `NE.EXP.GNFS.KD`, real exports of goods and services in constant 2015 US dollars.
- Income: World Bank `NY.GDP.PCAP.PP.KD`, constant PPP GDP per capita.
- Population: World Bank `SP.POP.TOTL`.
- Trade openness: internally computed merchandise openness, `100 * (Comtrade imports + Comtrade exports) / World Bank current GDP`.
- Supplemental openness: World Bank `NE.TRD.GNFS.ZS`, goods and services trade as percent of GDP.
- Trade barrier proxy: World Bank `TM.TAX.MRCH.WM.AR.ZS`, weighted mean applied tariff, all products. This is a weak broad tariff proxy, not a direct free-trade-policy design.
- Oil control: existing PPP hump common panel where available.

## Model Summary

| Model | Family | N | Countries | R2 | p<0.05 terms |
| --- | --- | ---: | ---: | ---: | --- |
{chr(10).join(headline_rows)}

## Selected Coefficients

Raw p-values below 0.05 are bolded.

| Model | Term | Coef | SE | p |
| --- | --- | ---: | ---: | ---: |
{chr(10).join(selected_lines)}

## Leave-One-Country Influence

These rows list omissions that make the cross-country merchandise-openness-change coefficient lose p<0.05. The annual country/year FE openness result is more stable, so this is mainly a warning about the cross-country change specification.

| Model | Omitted country | Coef | SE | p |
| --- | --- | ---: | ---: | ---: |
{chr(10).join(influence_lines)}

## Model Sample Manifest

| Model | Input rows | Complete rows | Dropped rows | Complete countries | Excluded countries | Missing columns |
| --- | ---: | ---: | ---: | ---: | --- | --- |
{chr(10).join(sample_lines)}

## Tariff Endpoint Timing

Tariff country-change models use nearest available WDI tariff values in 2000-2005 and 2019-2024 windows. This means the tariff robustness is not a literal 2000-to-2024 endpoint test.

| Tariff end year used | Countries |
| ---: | ---: |
{chr(10).join(tariff_year_lines)}

## Specification Logic

The preferred country-level model is an OLS change regression because the grouping question is about a 2000-2024 country outcome. With only 55-56 countries, it uses HC3 robust standard errors and keeps controls sparse. The preferred annual panel model uses country and year fixed effects with country-clustered standard errors because it asks a different question: whether the same country becomes more concentrated when its exports, income, or openness change over time.

Other options considered but not used as baselines:

- Multinomial logit for seven driver groups: too many groups for 56 countries.
- Causal treatment/event designs for trade agreements: the current request has no clean assignment variable or event window.
- WITS HS4 market-access tariffs as the main barrier variable: existing diagnostics flag coverage blockers and the measure is exporter destination-tariff exposure, not domestic import barriers.
- A full dynamic panel: too aggressive for 25 years and 55 countries without a clearer causal estimand.

## Diagnostics

| Diagnostic | Value |
| --- | ---: |
"""
    for _, r in diagnostics.iterrows():
        text += f"| {r['diagnostic']} | {r['value']} |\n"
    text += """
## Interpretation Guardrails

- Export level is not a pure trade mechanism; it is partly country size, so population controls and export-per-capita robustness matter.
- Export growth can reflect commodity price shocks, exchange rates, and reporting changes, not only real structural export expansion.
- Trade openness is not a direct policy barrier. It mixes policy, geography, size, commodity dependence, and macro shocks.
- WDI tariff coverage is sparse and endpoint tariff changes use nearest available years; tariff results are robustness only.
- Country fixed effects answer within-country co-movement, not the pooled development-stage question.
"""
    (OUT_DIR / "import_concentration_explanatory_regressions.md").write_text(text, encoding="utf-8")


def plot_selected_coefficients(terms: pd.DataFrame) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    plot_terms = [
        "goods_export_growth_2000_2024",
        "gdp_pc_ppp_growth_2000_2024",
        "trade_openness_change_2000_2024",
        "wdi_goods_services_trade_openness_change_2000_2024",
        "real_export_growth_2000_2024",
        "log_goods_exports_current_usd",
        "log_real_exports_goods_services_constant_2015_usd",
        "log_gdp_pc_ppp_constant_2021_intl_usd",
        "trade_openness_pct_gdp",
        "wdi_goods_services_trade_openness_pct_gdp",
        "d_log_goods_exports_current_usd",
        "d_log_real_exports_goods_services_constant_2015_usd",
        "d_log_gdp_pc_ppp_constant_2021_intl_usd",
        "d_trade_openness_pct_gdp",
        "l1_d_log_goods_exports_current_usd",
        "l1_d_log_real_exports_goods_services_constant_2015_usd",
        "l1_d_log_gdp_pc_ppp_constant_2021_intl_usd",
        "l1_d_trade_openness_pct_gdp",
    ]
    sub = terms[terms["term"].isin(plot_terms)].copy()
    if sub.empty:
        return
    sub["label"] = sub["model_id"] + "\n" + sub["term"]
    sub = sub.sort_values(["family", "model_id", "term"])
    y = np.arange(len(sub))
    fig_h = max(6, len(sub) * 0.32)
    fig, ax = plt.subplots(figsize=(11, fig_h))
    ax.axvline(0, color="#2f3542", linewidth=1)
    ax.errorbar(
        sub["coef"],
        y,
        xerr=1.96 * sub["std_error"],
        fmt="o",
        color="#275f91",
        ecolor="#9cb6ce",
        capsize=3,
    )
    ax.set_yticks(y)
    ax.set_yticklabels(sub["label"], fontsize=8)
    ax.set_xlabel("Coefficient with approximate 95% interval")
    ax.set_title("Selected explanatory-regression coefficients")
    ax.grid(axis="x", color="#e3e8ef", linewidth=0.8)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "selected_explanatory_coefficients.png", dpi=180)
    plt.close(fig)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    classification = pd.read_csv(CLASSIFICATION)
    classification["iso3"] = classification["iso3"].astype(str).str.upper()
    validate_unique(classification, ["iso3"], "balanced classification")
    iso3s = sorted(classification["iso3"].unique().tolist())

    outcome = load_outcome_panel(classification)
    exports = load_goods_export_panel(classification)
    wdi = load_or_fetch_wdi_controls(iso3s)
    oil = load_oil_share()

    panel = outcome.merge(exports, on=["iso3", "year"], how="left", validate="one_to_one")
    panel = panel.merge(wdi, on=["iso3", "year"], how="left", validate="one_to_one")
    panel = panel.merge(oil, on=["iso3", "year"], how="left", validate="one_to_one")
    panel["oil_export_share"] = pd.to_numeric(panel["oil_export_share"], errors="coerce").fillna(0)
    panel = add_panel_variables(panel)
    validate_unique(panel, ["iso3", "year"], "analysis panel")

    country_change = build_country_change_panel(panel, classification)
    summary, terms, sample_manifest = run_regressions(country_change, panel)
    influence = make_leave_one_country_influence(country_change)
    tariff_endpoints = make_tariff_endpoint_diagnostics(country_change)
    diagnostics = make_diagnostics(classification, panel, country_change)

    panel.to_csv(OUT_DIR / "analysis_panel.csv", index=False)
    country_change.to_csv(OUT_DIR / "country_change_panel.csv", index=False)
    summary.to_csv(OUT_DIR / "regression_model_summary.csv", index=False)
    terms.to_csv(OUT_DIR / "regression_terms.csv", index=False)
    sample_manifest.to_csv(OUT_DIR / "model_sample_manifest.csv", index=False)
    influence.to_csv(OUT_DIR / "leave_one_country_influence.csv", index=False)
    tariff_endpoints.to_csv(OUT_DIR / "tariff_endpoint_diagnostics.csv", index=False)
    diagnostics.to_csv(OUT_DIR / "sample_diagnostics.csv", index=False)
    plot_selected_coefficients(terms)
    write_markdown(summary, terms, diagnostics, sample_manifest, influence, tariff_endpoints)
    manifest = {
        "created_at_utc": now_utc(),
        "country_sample": "rd2_countries",
        "start_year": START_YEAR,
        "end_year": END_YEAR,
        "outputs": {
            "analysis_panel": rel(OUT_DIR / "analysis_panel.csv"),
            "country_change_panel": rel(OUT_DIR / "country_change_panel.csv"),
            "regression_model_summary": rel(OUT_DIR / "regression_model_summary.csv"),
            "regression_terms": rel(OUT_DIR / "regression_terms.csv"),
            "model_sample_manifest": rel(OUT_DIR / "model_sample_manifest.csv"),
            "leave_one_country_influence": rel(OUT_DIR / "leave_one_country_influence.csv"),
            "tariff_endpoint_diagnostics": rel(OUT_DIR / "tariff_endpoint_diagnostics.csv"),
            "sample_diagnostics": rel(OUT_DIR / "sample_diagnostics.csv"),
            "markdown": rel(OUT_DIR / "import_concentration_explanatory_regressions.md"),
        },
        "wdi_indicators": WDI_INDICATORS,
        "notes": [
            "Descriptive regressions only; not causal identification.",
            "Ex-energy means the project Exercise 3 energy-bin exclusion.",
            "Tariff models are reduced-sample robustness because WDI tariff coverage is sparse.",
        ],
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote {OUT_DIR}")
    print(f"Models: {len(summary)}")
    print(f"Panel rows: {len(panel)}")
    print(f"Country-change rows: {len(country_change)}")


if __name__ == "__main__":
    main()
