#!/usr/bin/env python3
"""Lifecycle regressions for cross-sectional import concentration findings.

This pass re-estimates selected cross-sectional questions with within-country
variation over time in rd2_countries. The exercise is descriptive: it asks
whether a given country's ex-energy import Product Gini moves with exports,
income, openness, tariffs, or industrial-policy exposure over its own history.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

import run_country_size_effect as cse
import run_import_concentration_explanatory_regressions as macro
import run_industrial_policy_import_gini as ip

ROOT = Path(__file__).resolve().parents[1]
COUNTRY_SAMPLE = "rd2_countries"
BASE = ROOT / "results" / "samples" / COUNTRY_SAMPLE
OUT_DIR = BASE / "lifecycle_regressions"

MIN_COUNTRIES = 20
MIN_YEARS = 5
POLICY_DIRECT_SCENARIO = "direct_named_only"


@dataclass(frozen=True)
class LifecycleSpec:
    model_id: str
    family: str
    source_model_ids: tuple[str, ...]
    dataset: str
    outcome: str
    terms: tuple[str, ...]
    fixed_effects: tuple[str, ...]
    cluster_col: str
    two_way_cluster_col: str | None
    formula: str
    lifecycle_question: str
    interpretation: str
    scenario: str | None = None
    min_year: int | None = None


def lifecycle_specs() -> list[LifecycleSpec]:
    """Return the lifecycle model registry used by the runner and tests."""
    macro_controls = (
        "log_goods_exports_current_usd",
        "log_gdp_pc_ppp_constant_2021_intl_usd",
        "trade_openness_pct_gdp",
        "log_population",
        "oil_export_share",
    )
    real_export_controls = (
        "log_real_exports_goods_services_constant_2015_usd",
        "log_gdp_pc_ppp_constant_2021_intl_usd",
        "trade_openness_pct_gdp",
        "log_population",
        "oil_export_share",
    )
    wdi_openness_controls = (
        "log_goods_exports_current_usd",
        "log_gdp_pc_ppp_constant_2021_intl_usd",
        "wdi_goods_services_trade_openness_pct_gdp",
        "log_population",
        "oil_export_share",
    )
    policy_controls = (
        "log_gdp_pc_ppp",
        "log_population",
        "trade_openness_share_gdp",
        "imports_goods_services_share_gdp",
    )
    level_question = (
        "Within the same country, are years with higher exports, income, openness, "
        "population, or oil-export exposure also years with higher or lower "
        "ex-energy import Product Gini?"
    )
    change_question = (
        "Within annual country changes, do changes in exports, income, or openness "
        "move with changes in ex-energy import Product Gini?"
    )
    lagged_change_question = (
        "Do last year's changes in exports, income, or openness predict this year's "
        "change in ex-energy import Product Gini within the same country history?"
    )
    policy_question = (
        "As a country recently adopts or accumulates industrial-policy measures, "
        "does its own ex-energy import Product Gini move?"
    )

    specs = [
        LifecycleSpec(
            model_id="macro_level_goods_exports",
            family="macro_level",
            source_model_ids=("xs_exports", "xs_income", "xs_openness", "xs_full"),
            dataset="macro",
            outcome="ex_energy_import_product_gini",
            terms=macro_controls,
            fixed_effects=("iso3", "year"),
            cluster_col="iso3",
            two_way_cluster_col=None,
            formula=(
                "ex_energy_import_product_gini ~ log_goods_exports_current_usd + "
                "log_gdp_pc_ppp_constant_2021_intl_usd + trade_openness_pct_gdp + "
                "log_population + oil_export_share + C(iso3) + C(year)"
            ),
            lifecycle_question=level_question,
            interpretation=(
                "Country and year fixed effects remove permanent cross-country differences "
                "and common global shocks, leaving within-country deviations from that "
                "country's own average path."
            ),
        ),
        LifecycleSpec(
            model_id="macro_level_real_exports",
            family="macro_level",
            source_model_ids=("xs_real_exports",),
            dataset="macro",
            outcome="ex_energy_import_product_gini",
            terms=real_export_controls,
            fixed_effects=("iso3", "year"),
            cluster_col="iso3",
            two_way_cluster_col=None,
            formula=(
                "ex_energy_import_product_gini ~ log_real_exports_goods_services_constant_2015_usd + "
                "log_gdp_pc_ppp_constant_2021_intl_usd + trade_openness_pct_gdp + "
                "log_population + oil_export_share + C(iso3) + C(year)"
            ),
            lifecycle_question=level_question,
            interpretation="Same lifecycle level design, replacing current-dollar goods exports with real exports.",
        ),
        LifecycleSpec(
            model_id="macro_level_wdi_openness",
            family="macro_level",
            source_model_ids=("xs_full_wdi_openness",),
            dataset="macro",
            outcome="ex_energy_import_product_gini",
            terms=wdi_openness_controls,
            fixed_effects=("iso3", "year"),
            cluster_col="iso3",
            two_way_cluster_col=None,
            formula=(
                "ex_energy_import_product_gini ~ log_goods_exports_current_usd + "
                "log_gdp_pc_ppp_constant_2021_intl_usd + wdi_goods_services_trade_openness_pct_gdp + "
                "log_population + oil_export_share + C(iso3) + C(year)"
            ),
            lifecycle_question=level_question,
            interpretation="Same lifecycle level design, using the WDI goods-and-services openness measure.",
        ),
        LifecycleSpec(
            model_id="macro_level_tariff",
            family="macro_level",
            source_model_ids=("xs_tariff_robust",),
            dataset="macro",
            outcome="ex_energy_import_product_gini",
            terms=(
                "log_goods_exports_current_usd",
                "log_gdp_pc_ppp_constant_2021_intl_usd",
                "trade_openness_pct_gdp",
                "tariff_applied_weighted_mean_pct",
                "log_population",
                "oil_export_share",
            ),
            fixed_effects=("iso3", "year"),
            cluster_col="iso3",
            two_way_cluster_col=None,
            formula=(
                "ex_energy_import_product_gini ~ log_goods_exports_current_usd + "
                "log_gdp_pc_ppp_constant_2021_intl_usd + trade_openness_pct_gdp + "
                "tariff_applied_weighted_mean_pct + log_population + oil_export_share + C(iso3) + C(year)"
            ),
            lifecycle_question=(
                "Within the same country, are years with higher applied tariff rates also "
                "years with higher or lower ex-energy import Product Gini?"
            ),
            interpretation=(
                "Tariffs are kept as a level lifecycle model only because endpoint tariff "
                "changes are sparse and were already weak in the cross-sectional exercise."
            ),
        ),
        LifecycleSpec(
            model_id="macro_change_goods_exports",
            family="macro_change",
            source_model_ids=("xs_exports", "xs_income", "xs_openness", "xs_full"),
            dataset="macro",
            outcome="d_ex_energy_import_product_gini",
            terms=(
                "d_log_goods_exports_current_usd",
                "d_log_gdp_pc_ppp_constant_2021_intl_usd",
                "d_trade_openness_pct_gdp",
            ),
            fixed_effects=("year",),
            cluster_col="iso3",
            two_way_cluster_col=None,
            formula=(
                "d_ex_energy_import_product_gini ~ d_log_goods_exports_current_usd + "
                "d_log_gdp_pc_ppp_constant_2021_intl_usd + d_trade_openness_pct_gdp + C(year)"
            ),
            lifecycle_question=change_question,
            interpretation=(
                "First differences remove time-invariant country levels. Year fixed effects "
                "remove common annual shocks in the change equation."
            ),
        ),
        LifecycleSpec(
            model_id="macro_change_real_exports",
            family="macro_change",
            source_model_ids=("xs_real_exports",),
            dataset="macro",
            outcome="d_ex_energy_import_product_gini",
            terms=(
                "d_log_real_exports_goods_services_constant_2015_usd",
                "d_log_gdp_pc_ppp_constant_2021_intl_usd",
                "d_trade_openness_pct_gdp",
            ),
            fixed_effects=("year",),
            cluster_col="iso3",
            two_way_cluster_col=None,
            formula=(
                "d_ex_energy_import_product_gini ~ d_log_real_exports_goods_services_constant_2015_usd + "
                "d_log_gdp_pc_ppp_constant_2021_intl_usd + d_trade_openness_pct_gdp + C(year)"
            ),
            lifecycle_question=change_question,
            interpretation="Annual-change version using real exports instead of current-dollar goods exports.",
        ),
        LifecycleSpec(
            model_id="macro_change_wdi_openness",
            family="macro_change",
            source_model_ids=("xs_full_wdi_openness",),
            dataset="macro",
            outcome="d_ex_energy_import_product_gini",
            terms=(
                "d_log_goods_exports_current_usd",
                "d_log_gdp_pc_ppp_constant_2021_intl_usd",
                "d_wdi_goods_services_trade_openness_pct_gdp",
            ),
            fixed_effects=("year",),
            cluster_col="iso3",
            two_way_cluster_col=None,
            formula=(
                "d_ex_energy_import_product_gini ~ d_log_goods_exports_current_usd + "
                "d_log_gdp_pc_ppp_constant_2021_intl_usd + d_wdi_goods_services_trade_openness_pct_gdp + C(year)"
            ),
            lifecycle_question=change_question,
            interpretation="Annual-change version using WDI goods-and-services openness.",
        ),
        LifecycleSpec(
            model_id="macro_lagged_change_goods_exports",
            family="macro_lagged_change",
            source_model_ids=("xs_exports", "xs_income", "xs_openness", "xs_full"),
            dataset="macro",
            outcome="d_ex_energy_import_product_gini",
            terms=(
                "l1_d_log_goods_exports_current_usd",
                "l1_d_log_gdp_pc_ppp_constant_2021_intl_usd",
                "l1_d_trade_openness_pct_gdp",
            ),
            fixed_effects=("year",),
            cluster_col="iso3",
            two_way_cluster_col=None,
            formula=(
                "d_ex_energy_import_product_gini ~ l1_d_log_goods_exports_current_usd + "
                "l1_d_log_gdp_pc_ppp_constant_2021_intl_usd + l1_d_trade_openness_pct_gdp + C(year)"
            ),
            lifecycle_question=lagged_change_question,
            interpretation=(
                "Lagged changes reduce simultaneity relative to the same-year change model, "
                "but still do not identify a causal effect."
            ),
        ),
        LifecycleSpec(
            model_id="macro_lagged_change_real_exports",
            family="macro_lagged_change",
            source_model_ids=("xs_real_exports",),
            dataset="macro",
            outcome="d_ex_energy_import_product_gini",
            terms=(
                "l1_d_log_real_exports_goods_services_constant_2015_usd",
                "l1_d_log_gdp_pc_ppp_constant_2021_intl_usd",
                "l1_d_trade_openness_pct_gdp",
            ),
            fixed_effects=("year",),
            cluster_col="iso3",
            two_way_cluster_col=None,
            formula=(
                "d_ex_energy_import_product_gini ~ l1_d_log_real_exports_goods_services_constant_2015_usd + "
                "l1_d_log_gdp_pc_ppp_constant_2021_intl_usd + l1_d_trade_openness_pct_gdp + C(year)"
            ),
            lifecycle_question=lagged_change_question,
            interpretation="Lagged-change version using real exports instead of current-dollar goods exports.",
        ),
        LifecycleSpec(
            model_id="macro_lagged_change_wdi_openness",
            family="macro_lagged_change",
            source_model_ids=("xs_full_wdi_openness",),
            dataset="macro",
            outcome="d_ex_energy_import_product_gini",
            terms=(
                "l1_d_log_goods_exports_current_usd",
                "l1_d_log_gdp_pc_ppp_constant_2021_intl_usd",
                "l1_d_wdi_goods_services_trade_openness_pct_gdp",
            ),
            fixed_effects=("year",),
            cluster_col="iso3",
            two_way_cluster_col=None,
            formula=(
                "d_ex_energy_import_product_gini ~ l1_d_log_goods_exports_current_usd + "
                "l1_d_log_gdp_pc_ppp_constant_2021_intl_usd + l1_d_wdi_goods_services_trade_openness_pct_gdp + C(year)"
            ),
            lifecycle_question=lagged_change_question,
            interpretation="Lagged-change version using WDI goods-and-services openness.",
        ),
        LifecycleSpec(
            model_id="policy_lagged_counts_direct",
            family="industrial_policy_lifecycle",
            source_model_ids=("m6_country_change_direct",),
            dataset="policy",
            outcome="ex_energy_import_product_gini",
            terms=(
                "log1p_import_substitution_ip_measures_l1",
                "log1p_export_promotion_ip_measures_l1",
                *policy_controls,
            ),
            fixed_effects=("iso3", "year"),
            cluster_col="iso3",
            two_way_cluster_col=None,
            formula=(
                "ex_energy_import_product_gini ~ log1p_import_substitution_ip_measures_l1 + "
                "log1p_export_promotion_ip_measures_l1 + log_gdp_pc_ppp + log_population + "
                "trade_openness_share_gdp + imports_goods_services_share_gdp + C(iso3) + C(year)"
            ),
            lifecycle_question=policy_question,
            interpretation=(
                "Uses last year's named industrial-policy counts so the exposure is not "
                "contemporaneously measured against the same year's import concentration."
            ),
            scenario=POLICY_DIRECT_SCENARIO,
            min_year=ip.START_YEAR + 1,
        ),
        LifecycleSpec(
            model_id="policy_cumulative_pre_direct",
            family="industrial_policy_lifecycle",
            source_model_ids=("m6_country_change_direct",),
            dataset="policy",
            outcome="ex_energy_import_product_gini",
            terms=(
                "log1p_cum_import_substitution_ip_measures_pre",
                "log1p_cum_export_promotion_ip_measures_pre",
                *policy_controls,
            ),
            fixed_effects=("iso3", "year"),
            cluster_col="iso3",
            two_way_cluster_col=None,
            formula=(
                "ex_energy_import_product_gini ~ log1p_cum_import_substitution_ip_measures_pre + "
                "log1p_cum_export_promotion_ip_measures_pre + log_gdp_pc_ppp + log_population + "
                "trade_openness_share_gdp + imports_goods_services_share_gdp + C(iso3) + C(year)"
            ),
            lifecycle_question=policy_question,
            interpretation=(
                "Uses cumulative policy exposure through t-1, testing whether a country's "
                "pre-existing policy stock is associated with its concentration path."
            ),
            scenario=POLICY_DIRECT_SCENARIO,
            min_year=ip.START_YEAR + 1,
        ),
    ]
    return specs


def two_way_robustness_specs(specs: list[LifecycleSpec]) -> list[LifecycleSpec]:
    """Clone primary specs with two-way country-year clustered covariance."""
    return [
        replace(
            spec,
            model_id=f"{spec.model_id}_twoway_cluster",
            family=f"{spec.family}_robustness",
            two_way_cluster_col="year",
            interpretation=(
                f"{spec.interpretation} Robustness version with standard errors clustered by country and year."
            ),
        )
        for spec in specs
    ]


def lifecycle_specs_with_robustness(include_two_way: bool = True) -> list[LifecycleSpec]:
    primary = lifecycle_specs()
    if not include_two_way:
        return primary
    return [*primary, *two_way_robustness_specs(primary)]


def build_macro_panel(refresh_controls: bool = False) -> pd.DataFrame:
    classification = pd.read_csv(macro.CLASSIFICATION)
    classification["iso3"] = classification["iso3"].astype(str).str.upper()
    macro.validate_unique(classification, ["iso3"], "rd2_countries classification")
    iso3s = sorted(classification["iso3"].unique().tolist())

    outcome = macro.load_outcome_panel(classification)
    exports = macro.load_goods_export_panel(classification)
    wdi = macro.load_or_fetch_wdi_controls(iso3s, refresh=refresh_controls)
    oil = macro.load_oil_share()

    panel = outcome.merge(exports, on=["iso3", "year"], how="left", validate="one_to_one")
    panel = panel.merge(wdi, on=["iso3", "year"], how="left", validate="one_to_one")
    panel = panel.merge(oil, on=["iso3", "year"], how="left", validate="one_to_one")
    panel["oil_export_share"] = pd.to_numeric(panel["oil_export_share"], errors="coerce").fillna(0)
    panel = macro.add_panel_variables(panel)
    macro.validate_unique(panel, ["iso3", "year"], "lifecycle macro panel")
    return panel


def validate_policy_pre_exposure(panel: pd.DataFrame) -> None:
    """Confirm cumulative-pre policy variables exclude contemporaneous counts."""
    required = ["scenario", "iso3", "year"]
    missing_keys = [col for col in required if col not in panel.columns]
    if missing_keys:
        raise RuntimeError(f"policy panel is missing pre-period validation keys: {missing_keys}")

    sorted_panel = panel.sort_values(required).copy()
    for col in ["import_substitution_ip_measures", "export_promotion_ip_measures"]:
        required_cols = [col, f"cum_{col}_pre", f"log1p_cum_{col}_pre"]
        missing = [name for name in required_cols if name not in sorted_panel.columns]
        if missing:
            raise RuntimeError(f"policy panel is missing cumulative-pre columns: {missing}")
        values = pd.to_numeric(sorted_panel[col], errors="coerce").fillna(0)
        expected_cum = values.groupby([sorted_panel["scenario"], sorted_panel["iso3"]]).cumsum()
        expected_pre = expected_cum.groupby([sorted_panel["scenario"], sorted_panel["iso3"]]).shift(1)
        actual_pre = pd.to_numeric(sorted_panel[f"cum_{col}_pre"], errors="coerce")
        expected_log = np.log1p(expected_pre)
        actual_log = pd.to_numeric(sorted_panel[f"log1p_cum_{col}_pre"], errors="coerce")
        pre_match = np.isclose(actual_pre.fillna(-999999.0), expected_pre.fillna(-999999.0), equal_nan=True)
        log_match = np.isclose(actual_log.fillna(-999999.0), expected_log.fillna(-999999.0), equal_nan=True)
        if not bool(np.all(pre_match)) or not bool(np.all(log_match)):
            raise RuntimeError(
                f"policy cumulative-pre validation failed for {col}: "
                "expected exposure through t-1, not contemporaneous cumulative totals"
            )


def read_policy_lifecycle_outcome(classification: pd.DataFrame) -> pd.DataFrame:
    bins = pd.read_csv(ip.IMPORT_BIN_DECOMP)
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
    }
    missing = sorted(required - set(bins.columns))
    if missing:
        raise RuntimeError(f"Import-bin decomposition missing lifecycle policy outcome columns: {missing}")
    keep_iso = set(classification["iso3"])
    panel = bins[
        bins["import_bin"].eq("energy")
        & bins["iso3"].astype(str).str.upper().isin(keep_iso)
        & bins["year"].between(ip.FULL_START_YEAR, ip.FULL_END_YEAR)
    ].copy()
    panel["iso3"] = panel["iso3"].astype(str).str.upper()
    panel["year"] = pd.to_numeric(panel["year"], errors="coerce").astype(int)
    ip.validate_unique(panel, ["iso3", "year"], "lifecycle policy ex-energy import Gini panel")
    expected = len(keep_iso) * (ip.FULL_END_YEAR - ip.FULL_START_YEAR + 1)
    if len(panel) != expected:
        raise RuntimeError(f"Expected {expected} balanced lifecycle policy outcome rows, found {len(panel)}.")
    return panel.rename(
        columns={
            "total_product_gini": "with_energy_import_product_gini",
            "product_gini_without_bin": "ex_energy_import_product_gini",
            "active_products_without_bin": "active_nonenergy_import_products",
            "total_imports_without_bin": "nonenergy_import_value",
        }
    )[
        [
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
    ].copy()


def build_policy_panel() -> pd.DataFrame:
    classification = ip.read_classification()
    outcome = read_policy_lifecycle_outcome(classification)
    controls = ip.read_controls(classification["iso3"])
    jlop = ip.read_jlop()
    expanded_frames = []
    unmatched_frames = []
    for include_eu in [False, True]:
        expanded, unmatched = ip.expand_jlop_to_rd2(jlop, classification, include_eu=include_eu)
        expanded_frames.append(expanded)
        if not unmatched.empty:
            unmatched_frames.append(unmatched)
    expanded_all = pd.concat(expanded_frames, ignore_index=True) if expanded_frames else pd.DataFrame()
    _unmatched_all = pd.concat(unmatched_frames, ignore_index=True) if unmatched_frames else pd.DataFrame()
    policy_panels = [
        ip.aggregate_policy_panel(expanded_all[expanded_all["scenario"].eq(scenario)], classification, scenario)
        for scenario in ["direct_named_only", "eu_allocated"]
    ]
    policy = pd.concat(policy_panels, ignore_index=True)
    policy = ip.add_policy_transforms(policy)
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
    panel = panel[panel["year"].between(ip.START_YEAR, ip.END_YEAR)].copy()
    ip.validate_unique(panel, ["scenario", "iso3", "year"], "lifecycle industrial-policy panel")
    validate_policy_pre_exposure(panel)
    return panel


def validate_required_input_files() -> None:
    """Fail clearly when rd2 lifecycle inputs are not available locally."""
    missing: list[str] = []
    if not macro.CLASSIFICATION.exists():
        missing.append(str(macro.CLASSIFICATION))
    if not (macro.IMPORT_BIN_DECOMP_PARQUET.exists() or macro.IMPORT_BIN_DECOMP.exists()):
        missing.append(f"{macro.IMPORT_BIN_DECOMP_PARQUET} or {macro.IMPORT_BIN_DECOMP}")
    if not (macro.EXPORT_CONCENTRATION_PARQUET.exists() or macro.PRODUCT_CONCENTRATION.exists()):
        missing.append(f"{macro.EXPORT_CONCENTRATION_PARQUET} or {macro.PRODUCT_CONCENTRATION}")
    for path in [ip.PPP_CONTROLS, ip.WDI_GVC_CONTROLS]:
        if not path.exists():
            missing.append(str(path))
    if missing:
        details = "\n".join(f"- {path}" for path in missing)
        raise RuntimeError(
            "Lifecycle regressions require rd2_countries upstream artifacts. "
            "No fallback sample is allowed. Missing inputs:\n"
            f"{details}"
        )


def output_paths(out_dir: Path = OUT_DIR) -> dict[str, Path]:
    return {
        "terms": out_dir / "lifecycle_regression_terms.csv",
        "summary": out_dir / "lifecycle_model_summary.csv",
        "manifest": out_dir / "lifecycle_sample_manifest.csv",
        "crosswalk": out_dir / "cross_section_to_lifecycle_crosswalk.csv",
        "memo": out_dir / "lifecycle_regressions.md",
    }


def data_for_spec(macro_panel: pd.DataFrame, policy_panel: pd.DataFrame, spec: LifecycleSpec) -> pd.DataFrame:
    if spec.dataset == "macro":
        data = macro_panel.copy()
    elif spec.dataset == "policy":
        data = policy_panel.copy()
    else:
        raise ValueError(f"unknown lifecycle dataset: {spec.dataset}")
    if spec.scenario is not None and "scenario" in data.columns:
        data = data[data["scenario"].eq(spec.scenario)].copy()
    if spec.min_year is not None and "year" in data.columns:
        data = data[pd.to_numeric(data["year"], errors="coerce") >= spec.min_year].copy()
    return data


def validate_panel_keys(macro_panel: pd.DataFrame, policy_panel: pd.DataFrame) -> None:
    checks = [
        ("macro lifecycle panel", macro_panel, ["iso3", "year"]),
        ("industrial-policy lifecycle panel", policy_panel, ["scenario", "iso3", "year"]),
    ]
    for label, df, keys in checks:
        if df.empty:
            continue
        missing = [col for col in keys if col not in df.columns]
        if missing:
            raise RuntimeError(f"{label} is missing key columns: {missing}")
        dupes = int(df.duplicated(keys).sum())
        if dupes:
            examples = df.loc[df.duplicated(keys, keep=False), keys].head(8).to_dict("records")
            raise RuntimeError(f"{label} has duplicate keys on {keys}: {examples}")


def joined(values: Iterable[object]) -> str:
    clean = [str(value) for value in values if pd.notna(value)]
    return ";".join(clean)


def missing_summary(df: pd.DataFrame, required: list[str]) -> str:
    parts = []
    for col in required:
        if col not in df.columns:
            parts.append(f"{col}:missing_column")
        else:
            parts.append(f"{col}:{int(df[col].isna().sum())}")
    return ";".join(parts)


def variation_terms(df: pd.DataFrame, terms: tuple[str, ...], entity_col: str = "iso3") -> tuple[str, str]:
    if entity_col not in df.columns:
        return "", joined(terms)
    varying: list[str] = []
    no_variation: list[str] = []
    for term in terms:
        if term not in df.columns:
            no_variation.append(term)
            continue
        values = pd.to_numeric(df[term], errors="coerce")
        demeaned = values - values.groupby(df[entity_col]).transform("mean")
        if np.isfinite(demeaned.to_numpy(dtype=float, na_value=np.nan)).any() and float(np.nanmax(np.abs(demeaned))) > 1e-12:
            varying.append(term)
        else:
            no_variation.append(term)
    return joined(varying), joined(no_variation)


def base_manifest_row(spec: LifecycleSpec, df: pd.DataFrame, required: list[str], status: str) -> dict[str, object]:
    countries = int(df["iso3"].nunique()) if "iso3" in df.columns else 0
    years = int(df["year"].nunique()) if "year" in df.columns else 0
    year_min = int(df["year"].min()) if "year" in df.columns and len(df) else np.nan
    year_max = int(df["year"].max()) if "year" in df.columns and len(df) else np.nan
    country_list = joined(sorted(df["iso3"].dropna().astype(str).unique())) if "iso3" in df.columns else ""
    return {
        "model_id": spec.model_id,
        "sample": COUNTRY_SAMPLE,
        "family": spec.family,
        "source_model_ids": joined(spec.source_model_ids),
        "dataset": spec.dataset,
        "scenario": spec.scenario or "",
        "formula": spec.formula,
        "input_rows": int(len(df)),
        "complete_rows": 0,
        "dropped_rows": int(len(df)),
        "input_countries": countries,
        "countries": 0,
        "complete_countries": 0,
        "years": 0,
        "year_min": year_min,
        "year_max": year_max,
        "complete_countries_list": "",
        "input_countries_list": country_list,
        "missing_columns_summary": missing_summary(df, required),
        "within_variation_terms": "",
        "no_within_variation_terms": "",
        "absorbed_or_no_variation_terms": "",
        "status": status,
    }


def empty_terms(spec: LifecycleSpec, status: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "model_id": spec.model_id,
                "model_label": spec.model_id,
                "sample": COUNTRY_SAMPLE,
                "family": spec.family,
                "source_model_ids": joined(spec.source_model_ids),
                "dataset": spec.dataset,
                "outcome": spec.outcome,
                "term": term,
                "coefficient": np.nan,
                "std_error": np.nan,
                "t_stat": np.nan,
                "p_value": np.nan,
                "nobs": 0,
                "clusters": 0,
                "r_squared": np.nan,
                "status": status,
                "lifecycle_question": spec.lifecycle_question,
                "interpretation": spec.interpretation,
            }
            for term in spec.terms
        ]
    )


def empty_summary(spec: LifecycleSpec, status: str, candidate_rows: int, dropped_rows: int) -> dict[str, object]:
    covariance = (
        f"clustered by {spec.cluster_col} and {spec.two_way_cluster_col}"
        if spec.two_way_cluster_col
        else f"clustered by {spec.cluster_col}"
    )
    cluster_col = (
        f"{spec.cluster_col},{spec.two_way_cluster_col}"
        if spec.two_way_cluster_col
        else spec.cluster_col
    )
    return {
        "model_id": spec.model_id,
        "sample": COUNTRY_SAMPLE,
        "family": spec.family,
        "source_model_ids": joined(spec.source_model_ids),
        "dataset": spec.dataset,
        "scenario": spec.scenario or "",
        "formula": spec.formula,
        "outcome": spec.outcome,
        "terms": joined(spec.terms),
        "fixed_effects": joined(spec.fixed_effects) or "none",
        "nobs": 0,
        "countries": 0,
        "years": 0,
        "year_min": np.nan,
        "year_max": np.nan,
        "r_squared": np.nan,
        "covariance": covariance,
        "cluster_col": cluster_col,
        "clusters": 0,
        "candidate_rows": candidate_rows,
        "dropped_rows": dropped_rows,
        "status": status,
        "lifecycle_question": spec.lifecycle_question,
        "interpretation": spec.interpretation,
    }


def run_lifecycle_model(
    df: pd.DataFrame,
    spec: LifecycleSpec,
    min_countries: int = MIN_COUNTRIES,
    min_years: int = MIN_YEARS,
) -> tuple[pd.DataFrame, dict[str, object], dict[str, object]]:
    required = list(
        dict.fromkeys(
            [
                spec.outcome,
                *spec.terms,
                *spec.fixed_effects,
                spec.cluster_col,
                *([spec.two_way_cluster_col] if spec.two_way_cluster_col else []),
            ]
        )
    )
    missing_cols = [col for col in required if col not in df.columns]
    if missing_cols:
        status = "missing_required_columns:" + ",".join(missing_cols)
        manifest = base_manifest_row(spec, df, required, status)
        return empty_terms(spec, status), empty_summary(spec, status, len(df), len(df)), manifest

    work = df.replace([np.inf, -np.inf], np.nan).dropna(subset=required).copy()
    countries = int(work["iso3"].nunique()) if "iso3" in work.columns else 0
    years = int(work["year"].nunique()) if "year" in work.columns else 0
    varying_terms, no_variation_terms = variation_terms(work, spec.terms)
    dropped_rows = int(len(df) - len(work))
    status = "ok"
    if countries < min_countries:
        status = f"insufficient_countries:{countries}"
    elif years < min_years:
        status = f"insufficient_years:{years}"

    manifest = base_manifest_row(spec, df, required, status)
    manifest.update(
        {
            "complete_rows": int(len(work)),
            "dropped_rows": dropped_rows,
            "countries": countries,
            "complete_countries": countries,
            "years": years,
            "year_min": int(work["year"].min()) if len(work) and "year" in work.columns else np.nan,
            "year_max": int(work["year"].max()) if len(work) and "year" in work.columns else np.nan,
            "complete_countries_list": joined(sorted(work["iso3"].dropna().astype(str).unique()))
            if "iso3" in work.columns
            else "",
            "within_variation_terms": varying_terms,
            "no_within_variation_terms": no_variation_terms,
            "absorbed_or_no_variation_terms": no_variation_terms,
        }
    )

    if status != "ok":
        return empty_terms(spec, status), empty_summary(spec, status, len(df), dropped_rows), manifest

    result = cse.run_ols_model(
        work,
        outcome=spec.outcome,
        terms=list(spec.terms),
        fixed_effects=list(spec.fixed_effects),
        model_label=spec.model_id,
        sample=COUNTRY_SAMPLE,
        flow="Imports",
        dimension="product",
        metric="ex_energy_import_product_gini",
        cluster_col=spec.cluster_col,
        two_way_cluster_col=spec.two_way_cluster_col,
    )
    terms = cse.model_results_to_frame([result]).rename(columns={"model_label": "model_id"})
    terms["model_label"] = terms["model_id"]
    terms["family"] = spec.family
    terms["source_model_ids"] = joined(spec.source_model_ids)
    terms["dataset"] = spec.dataset
    terms["lifecycle_question"] = spec.lifecycle_question
    terms["interpretation"] = spec.interpretation

    model_status = result.status
    if result.status != "ok":
        manifest["status"] = result.status
    if result.dropped_regressors:
        manifest["absorbed_or_no_variation_terms"] = result.dropped_regressors

    summary = {
        "model_id": spec.model_id,
        "sample": COUNTRY_SAMPLE,
        "family": spec.family,
        "source_model_ids": joined(spec.source_model_ids),
        "dataset": spec.dataset,
        "scenario": spec.scenario or "",
        "formula": spec.formula,
        "outcome": spec.outcome,
        "terms": joined(spec.terms),
        "fixed_effects": result.fixed_effects,
        "nobs": result.nobs,
        "countries": countries,
        "years": years,
        "year_min": int(work["year"].min()) if len(work) and "year" in work.columns else np.nan,
        "year_max": int(work["year"].max()) if len(work) and "year" in work.columns else np.nan,
        "r_squared": result.r_squared,
        "covariance": result.se_method,
        "cluster_col": result.cluster_col,
        "clusters": result.clusters,
        "candidate_rows": result.candidate_rows,
        "dropped_rows": result.dropped_rows,
        "status": model_status,
        "lifecycle_question": spec.lifecycle_question,
        "interpretation": spec.interpretation,
    }
    return terms, summary, manifest


def run_lifecycle_models(
    macro_panel: pd.DataFrame,
    policy_panel: pd.DataFrame,
    specs: list[LifecycleSpec] | None = None,
    min_countries: int = MIN_COUNTRIES,
    min_years: int = MIN_YEARS,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    selected_specs = specs or lifecycle_specs()
    model_ids = [spec.model_id for spec in selected_specs]
    duplicates = sorted({model_id for model_id in model_ids if model_ids.count(model_id) > 1})
    if duplicates:
        raise RuntimeError(f"duplicate lifecycle model IDs: {duplicates}")
    validate_panel_keys(macro_panel, policy_panel)

    term_frames = []
    summary_rows = []
    manifest_rows = []
    for spec in selected_specs:
        df = data_for_spec(macro_panel, policy_panel, spec)
        terms, summary, manifest = run_lifecycle_model(df, spec, min_countries=min_countries, min_years=min_years)
        term_frames.append(terms)
        summary_rows.append(summary)
        manifest_rows.append(manifest)

    terms_df = pd.concat(term_frames, ignore_index=True) if term_frames else pd.DataFrame()
    summary_df = pd.DataFrame(summary_rows)
    manifest_df = pd.DataFrame(manifest_rows)
    return terms_df, summary_df, manifest_df


def crosswalk() -> pd.DataFrame:
    rows = [
        {
            "cross_section_model_id": "xs_exports",
            "lifecycle_model_ids": joined(
                ["macro_level_goods_exports", "macro_change_goods_exports", "macro_lagged_change_goods_exports"]
            ),
            "lifecycle_status": "converted",
            "rationale": "Exports are re-estimated as within-country levels, annual changes, and lagged annual changes.",
        },
        {
            "cross_section_model_id": "xs_real_exports",
            "lifecycle_model_ids": joined(
                ["macro_level_real_exports", "macro_change_real_exports", "macro_lagged_change_real_exports"]
            ),
            "lifecycle_status": "converted",
            "rationale": "Real-export version of the export lifecycle comparison.",
        },
        {
            "cross_section_model_id": "xs_income",
            "lifecycle_model_ids": joined(
                ["macro_level_goods_exports", "macro_change_goods_exports", "macro_lagged_change_goods_exports"]
            ),
            "lifecycle_status": "converted",
            "rationale": "Income enters the macro lifecycle level, change, and lagged-change specifications.",
        },
        {
            "cross_section_model_id": "xs_openness",
            "lifecycle_model_ids": joined(
                ["macro_level_goods_exports", "macro_change_goods_exports", "macro_lagged_change_goods_exports"]
            ),
            "lifecycle_status": "converted",
            "rationale": "Openness enters the macro lifecycle level, change, and lagged-change specifications.",
        },
        {
            "cross_section_model_id": "xs_full",
            "lifecycle_model_ids": joined(
                ["macro_level_goods_exports", "macro_change_goods_exports", "macro_lagged_change_goods_exports"]
            ),
            "lifecycle_status": "converted",
            "rationale": "Full macro controls are converted to lifecycle levels and changes.",
        },
        {
            "cross_section_model_id": "xs_full_wdi_openness",
            "lifecycle_model_ids": joined(
                ["macro_level_wdi_openness", "macro_change_wdi_openness", "macro_lagged_change_wdi_openness"]
            ),
            "lifecycle_status": "converted",
            "rationale": "WDI openness is kept as a parallel lifecycle macro specification.",
        },
        {
            "cross_section_model_id": "xs_tariff_robust",
            "lifecycle_model_ids": "macro_level_tariff",
            "lifecycle_status": "level_only",
            "rationale": "Tariff coverage is sparse, so the lifecycle conversion is limited to the level FE model.",
        },
        {
            "cross_section_model_id": "xs_increase_lpm",
            "lifecycle_model_ids": "",
            "lifecycle_status": "not_converted_main",
            "rationale": "The binary ever-increased outcome is inherently endpoint-based; it is not a main lifecycle design.",
        },
        {
            "cross_section_model_id": "m6_country_change_direct",
            "lifecycle_model_ids": joined(["policy_lagged_counts_direct", "policy_cumulative_pre_direct"]),
            "lifecycle_status": "converted",
            "rationale": "Direct named industrial-policy exposure is converted to lagged-flow and cumulative-pre FE models.",
        },
    ]
    return pd.DataFrame(rows)


def write_markdown(
    terms: pd.DataFrame,
    summary: pd.DataFrame,
    manifest: pd.DataFrame,
    crosswalk_df: pd.DataFrame,
    out_path: Path,
) -> None:
    def sig_cell(value: object, p_value: object) -> str:
        if pd.isna(value):
            return ""
        text = f"{float(value):.6g}"
        if pd.notna(p_value) and float(p_value) < 0.05:
            return f"**{text}**"
        return text

    ok_models = summary[summary["status"].astype(str).eq("ok")] if not summary.empty else pd.DataFrame()
    lines = [
        "# Lifecycle Regressions For Cross-Sectional Findings",
        "",
        "This pass changes the comparison from cross-country differences to within-country movement over time.",
        "The estimates are descriptive associations, not causal effects.",
        "",
        "## Design",
        "",
        "- Sample: rd2_countries only.",
        "- Outcome: ex-energy import Product Gini.",
        "- Inference: country-clustered standard errors.",
        "- Level models use country and year fixed effects.",
        "- Change models use annual differences with year fixed effects.",
        "- Industrial-policy exposure uses either t-1 counts or cumulative exposure through t-1.",
        "",
        "## Model Coverage",
        "",
        f"- Lifecycle specifications registered: {len(summary)}.",
        f"- Specifications estimated with status ok: {len(ok_models)}.",
        f"- Cross-sectional families mapped: {len(crosswalk_df)}.",
        "",
        "## How To Read These Regressions",
        "",
        "A positive lifecycle coefficient means that, within the same country's observed path, years with higher values of the regressor tend to coincide with higher import concentration. A negative coefficient means those higher-regressor years tend to coincide with lower import concentration. Because these are not quasi-experimental shocks, the estimates should be read as descriptive movement over the country lifecycle.",
        "",
    ]
    if not ok_models.empty and not terms.empty:
        focal = terms[terms["status"].astype(str).eq("ok")].copy()
        if not focal.empty:
            focal = focal[["model_id", "term", "coefficient", "std_error", "p_value"]].head(40)
            focal["coefficient"] = [
                sig_cell(value, p_value) for value, p_value in zip(focal["coefficient"], focal["p_value"])
            ]
            focal["p_value"] = [sig_cell(value, value) for value in focal["p_value"]]
            focal["std_error"] = focal["std_error"].map(lambda value: "" if pd.isna(value) else f"{float(value):.6g}")
            lines.extend(["## First 40 Reported Terms", "", focal.to_markdown(index=False), ""])
    if not manifest.empty:
        status_counts = manifest["status"].astype(str).value_counts().rename_axis("status").reset_index(name="models")
        lines.extend(["## Estimation Status", "", status_counts.to_markdown(index=False), ""])
    lines.extend(
        [
            "## Crosswalk",
            "",
            crosswalk_df.to_markdown(index=False),
            "",
            "## Files",
            "",
            "- `lifecycle_regression_terms.csv`: term-level coefficients, standard errors, and p-values.",
            "- `lifecycle_model_summary.csv`: formulas, sample sizes, fixed effects, R2, and covariance information.",
            "- `lifecycle_sample_manifest.csv`: attrition, missingness, country coverage, and within-country variation checks.",
            "- `cross_section_to_lifecycle_crosswalk.csv`: mapping from old cross-sectional models to lifecycle equivalents.",
            "",
        ]
    )
    out_path.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(
    terms: pd.DataFrame,
    summary: pd.DataFrame,
    manifest: pd.DataFrame,
    crosswalk_df: pd.DataFrame,
    out_dir: Path = OUT_DIR,
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = output_paths(out_dir)
    terms.to_csv(paths["terms"], index=False)
    summary.to_csv(paths["summary"], index=False)
    manifest.to_csv(paths["manifest"], index=False)
    crosswalk_df.to_csv(paths["crosswalk"], index=False)
    write_markdown(terms, summary, manifest, crosswalk_df, paths["memo"])
    return paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-macro-controls", action="store_true", help="Refresh WDI controls instead of using cache.")
    parser.add_argument("--min-countries", type=int, default=MIN_COUNTRIES)
    parser.add_argument("--min-years", type=int, default=MIN_YEARS)
    parser.add_argument(
        "--skip-two-way-robustness",
        action="store_true",
        help="Estimate only the default country-clustered models.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    validate_required_input_files()
    macro_panel = build_macro_panel(refresh_controls=args.refresh_macro_controls)
    policy_panel = build_policy_panel()
    specs = lifecycle_specs_with_robustness(include_two_way=not args.skip_two_way_robustness)
    terms, summary, manifest = run_lifecycle_models(
        macro_panel,
        policy_panel,
        specs=specs,
        min_countries=args.min_countries,
        min_years=args.min_years,
    )
    paths = write_outputs(terms, summary, manifest, crosswalk())
    print(f"Wrote lifecycle regressions to {paths['summary'].parent}")
    print(f"Reported {int(summary['status'].astype(str).eq('ok').sum())} ok models out of {len(summary)} specs")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
