"""Growth-effect overrides for the rd2 GDP/GNI per-capita growth page."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def install_growth_effect_overrides(ns: dict[str, Any]) -> None:
    ns["GROWTH_EFFECT_MODEL_LABELS"].update(
        {
            "main_country_year_fe": "Main lagged income growth",
            "two_way_country_year_cluster": "Two-way clustered SE",
            "contemporaneous_growth": "Contemporaneous income growth",
            "future_growth_placebo": "Future income-growth placebo",
            "region_year_fe": "Region-year FE",
            "growth_by_income_tercile": "Income-tercile slopes",
            "threshold_scan": "Threshold scan",
        }
    )

    def growth_effect_measure_label(row: dict[str, Any]) -> str:
        dimension = str(row.get("dimension") or "").title()
        metric = ns["COUNTRY_SIZE_METRIC_LABELS"].get(str(row.get("metric")), str(row.get("metric") or ""))
        exposure_label = str(row.get("exposure_label") or row.get("exposure") or "").strip()
        suffix = f" ({exposure_label})" if exposure_label else ""
        return f"{row.get('flow')} {dimension} {metric}{suffix}"

    def growth_effect_primary_term(row: dict[str, Any]) -> str:
        model_label = str(row.get("model_label") or "")
        exposure = str(row.get("exposure") or "")
        if model_label == "contemporaneous_growth":
            return f"{exposure}_growth_current"
        if model_label == "future_growth_placebo":
            return f"{exposure}_growth_future"
        return f"{exposure}_growth_lag"

    def growth_effect_bin_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for row in rows:
            display = dict(row)
            display["measure"] = growth_effect_measure_label(row)
            display["bin_or_threshold"] = row.get("income_bin") or row.get("threshold_percentile") or row.get("label") or ""
            out.append(display)
        return out

    def load_growth_effect_data() -> dict[str, Any]:
        if not ns["include_growth_effect_page"]():
            return {}
        main_models = ns["read_csv"]("growth_effect_main_models")
        robustness_models = ns["read_csv"]("growth_effect_robustness_models")
        income_bin_slopes = ns["read_csv"]("growth_effect_income_bin_slopes")
        threshold_scan = ns["read_csv"]("growth_effect_threshold_scan")
        diagnostics = ns["read_csv"]("growth_effect_sample_diagnostics")

        model_required = {
            "model_label", "sample", "exposure", "exposure_label", "flow", "dimension", "metric", "outcome",
            "term", "coefficient", "std_error", "p_value", "nobs", "clusters", "status",
        }
        for name, frame in [("growth-effect main models", main_models), ("growth-effect robustness models", robustness_models)]:
            ns["require_columns"](frame, name, model_required)
        ns["require_columns"](
            income_bin_slopes,
            "growth-effect income-bin slopes",
            {
                "model_label", "sample", "exposure", "exposure_label", "flow", "dimension", "metric", "outcome",
                "income_bin", "coefficient", "std_error", "p_value", "high_minus_low_coef",
                "high_minus_low_p_value", "high_minus_low_bh_q_value", "income_low_max_2015_usd",
                "income_middle_max_2015_usd", "nobs", "clusters", "status",
            },
        )
        ns["require_columns"](
            threshold_scan,
            "growth-effect threshold scan",
            {
                "model_label", "sample", "exposure", "exposure_label", "flow", "dimension", "metric", "outcome",
                "threshold_percentile", "threshold_income_2015_usd", "below_threshold_slope",
                "below_threshold_std_error", "above_threshold_slope", "above_threshold_std_error",
                "above_minus_below_coef", "above_minus_below_p_value", "above_minus_below_bh_q_value",
                "nobs", "clusters", "status",
            },
        )
        ns["require_columns"](diagnostics, "growth-effect sample diagnostics", {"diagnostic", "value"})

        text_cols = {"model_label", "sample", "exposure", "exposure_label", "flow", "dimension", "metric", "outcome", "term", "income_bin", "status", "dropped_regressors", "fixed_effects", "se_method", "cluster_col", "p_value_reference"}
        main_models = ns["numeric_columns"](main_models, text_cols)
        robustness_models = ns["numeric_columns"](robustness_models, text_cols)
        income_bin_slopes = ns["numeric_columns"](income_bin_slopes, text_cols)
        threshold_scan = ns["numeric_columns"](threshold_scan, text_cols)

        primary = main_models[main_models.apply(lambda row: row["term"] == f"{row['exposure']}_growth_lag", axis=1)].copy()
        primary_ok = primary[primary["status"].eq("ok")].copy()
        strongest_abs = primary_ok.assign(abs_coef=primary_ok["coefficient"].abs()).sort_values("abs_coef", ascending=False).head(1) if not primary_ok.empty else pd.DataFrame()
        leveling_rows = income_bin_slopes[income_bin_slopes["income_bin"].eq("high") & income_bin_slopes["status"].eq("ok") & income_bin_slopes["high_minus_low_bh_q_value"].notna()].copy()
        leveling_strongest = leveling_rows.assign(abs_diff=leveling_rows["high_minus_low_coef"].abs()).sort_values("abs_diff", ascending=False).head(1) if not leveling_rows.empty else pd.DataFrame()

        income_display = income_bin_slopes.copy()
        income_display["row_type"] = "slope"
        income_display["label"] = income_display["income_bin"]
        income_display["export_level_bin"] = income_display["income_bin"]
        income_display["term"] = ""
        income_display["bh_q_value"] = income_display["high_minus_low_bh_q_value"]
        income_display["low_middle_export_cutoff"] = income_display["income_low_max_2015_usd"]
        income_display["middle_high_export_cutoff"] = income_display["income_middle_max_2015_usd"]

        threshold_display = threshold_scan.copy()
        threshold_display["row_type"] = "difference"
        threshold_display["label"] = "above_minus_below"
        threshold_display["term"] = ""
        threshold_display["threshold_exports_constant_2015_usd"] = threshold_display["threshold_income_2015_usd"]
        threshold_display["coefficient"] = threshold_display["above_minus_below_coef"]
        threshold_display["std_error"] = np.nan
        threshold_display["p_value"] = threshold_display["above_minus_below_p_value"]
        threshold_display["bh_q_value"] = threshold_display["above_minus_below_bh_q_value"]

        main_cutoffs = {}
        if not income_bin_slopes.empty:
            first = income_bin_slopes.iloc[0]
            main_cutoffs = {
                "income_low_max_2015_usd": ns["clean_scalar"](first.get("income_low_max_2015_usd")),
                "income_middle_max_2015_usd": ns["clean_scalar"](first.get("income_middle_max_2015_usd")),
                "low_middle_export_cutoff": ns["clean_scalar"](first.get("income_low_max_2015_usd")),
                "middle_high_export_cutoff": ns["clean_scalar"](first.get("income_middle_max_2015_usd")),
            }
        leveling_display = leveling_strongest.copy()
        if not leveling_display.empty:
            leveling_display["coefficient"] = leveling_display["high_minus_low_coef"]
            leveling_display["bh_q_value"] = leveling_display["high_minus_low_bh_q_value"]

        return {
            "main_models": ns["clean_records"](main_models, list(main_models.columns)),
            "robustness_models": ns["clean_records"](robustness_models, list(robustness_models.columns)),
            "income_bin_slopes": ns["clean_records"](income_display, list(income_display.columns)),
            "threshold_scan": ns["clean_records"](threshold_display, list(threshold_display.columns)),
            "sample_diagnostics": ns["clean_records"](diagnostics, list(diagnostics.columns)),
            "strongest_absolute": ns["clean_records"](strongest_abs, list(strongest_abs.columns))[0] if not strongest_abs.empty else {},
            "leveling_strongest": ns["clean_records"](leveling_display, list(leveling_display.columns))[0] if not leveling_display.empty else {},
            "cutoffs": main_cutoffs,
        }

    replacements = {
        "Export Growth and Concentration": "Per-Capita Income Growth and Concentration",
        "Export growth and concentration": "Income growth and concentration",
        "Export growth uses World Bank goods-and-services exports, while the concentration outcomes are merchandise concentration measures. Read the exposure as an aggregate export-growth environment, not the exact concentration denominator.": "Income growth uses World Bank real GDP per capita and real GNI per capita in constant 2015 US dollars. Read the estimates as conditional descriptive associations, not causal effects.",
        "lagged real aggregate export growth predicts next-year concentration levels": "lagged real per-capita GDP or GNI growth predicts next-year concentration levels",
        "prior export growth": "prior pc income growth",
        "log real exports": "log pc income",
        "Export growth uses World Bank real exports of goods and services in constant 2015 US dollars. The growth variable is lagged one year relative to the concentration outcome.": "Income growth uses World Bank real GDP per capita and real GNI per capita in constant 2015 US dollars. The growth variable is lagged one year relative to the concentration outcome.",
        "The export-level-bin model lets the lagged-growth slope differ across low, middle, and high lagged-export-level terciles.": "The income-bin model lets the lagged-growth slope differ across low, middle, and high lagged-income-level terciles.",
        "Export-level-bin slopes": "Income-bin slopes",
        "Export-level slopes CSV": "Income-bin slopes CSV",
        "Main lagged real export-growth coefficients by outcome.": "Main lagged real per-capita income-growth coefficients by outcome.",
        "Growth slopes by lagged real export-level tercile.": "Growth slopes by lagged real per-capita income tercile.",
        "Main lagged export-growth coefficients": "Main lagged income-growth coefficients",
        "Export-level-bin growth slopes": "Income-bin growth slopes",
        "Lag export-growth coef.": "Lag income-growth coef.",
        "Lagged export-level bin": "Lagged income bin",
        "Cutoff exports": "Cutoff income",
        "lagged real export growth and concentration levels": "lagged real per-capita income growth and concentration levels",
        "Does lagged real aggregate export growth predict lower or higher next-year concentration levels?": "Does lagged real per-capita GDP or GNI growth predict lower or higher next-year concentration levels?",
        "The lagged export-growth coefficient is stable under clustered inference and timing/placebo checks.": "The lagged income-growth coefficient is stable under clustered inference and timing/placebo checks.",
        "depends on one export-level bin": "depends on one income-level bin",
        "lagged-export-level checks": "lagged-income-level checks",
        "lagged export-growth coefficient": "lagged income-growth coefficient",
        "Lagged export-level terciles use World Bank real exports in constant 2015 US dollars.": "Lagged income-level terciles use World Bank real GDP/GNI per capita in constant 2015 US dollars.",
        "high-export-level and low-export-level": "high-income and low-income",
    }

    old_render_pages = ns["render_pages"]

    def render_pages(context: dict[str, str]) -> dict[str, str]:
        pages = old_render_pages(context)
        out = {}
        for name, html in pages.items():
            for old, new in replacements.items():
                html = html.replace(old, new)
            out[name] = html
        return out

    ns["growth_effect_measure_label"] = growth_effect_measure_label
    ns["growth_effect_primary_term"] = growth_effect_primary_term
    ns["growth_effect_bin_rows"] = growth_effect_bin_rows
    ns["load_growth_effect_data"] = load_growth_effect_data
    ns["render_pages"] = render_pages
