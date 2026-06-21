#!/usr/bin/env python3
"""Descriptive stability tests for partner Gini over time.

The exercise asks whether partner concentration is relatively stable within
countries. It is not a causal design: the target is time-series drift and
within-country dispersion in the existing concentration panel.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from trade_concentration_pipeline import sample_results_dir  # noqa: E402


DEFAULT_SAMPLE = "rd2_countries"
DEFAULT_START_YEAR = 2000
DEFAULT_END_YEAR = 2024
BALANCED_START_YEAR = 2001
BALANCED_END_YEAR = 2021
MIN_YEARS_FOR_COUNTRY_SLOPE = 10
STABILITY_SLOPE_10YR_MARGIN = 0.02
STABILITY_ENDPOINT_MARGIN = 0.05
STABILITY_SD_MARGIN = 0.02
SLOPE_MARGIN_GRID = (0.01, 0.02, 0.03, 0.05)
ENDPOINT_MARGIN_GRID = (0.03, 0.05, 0.10)
LOW_ACTIVE_PARTNER_THRESHOLD = 10
FLOW_COLORS = {"Exports": "#0f766e", "Imports": "#b45309"}


@dataclass(frozen=True)
class OutputPaths:
    table_dir: Path
    figure_dir: Path
    memo_path: Path
    manifest_path: Path
    country_slopes: Path
    summary: Path
    common_trends: Path
    variance_decomposition: Path
    low_active_partner_sensitivity: Path
    slope_distribution_figure: Path
    endpoint_change_figure: Path


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def ensure_dirs(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def p_to_stars(p_value: float) -> str:
    if not math.isfinite(p_value):
        return ""
    if p_value < 0.01:
        return "***"
    if p_value < 0.05:
        return "**"
    if p_value < 0.10:
        return "*"
    return ""


def bh_q_values(p_values: pd.Series) -> pd.Series:
    values = pd.to_numeric(p_values, errors="coerce")
    out = pd.Series(np.nan, index=values.index, dtype=float)
    valid = values.dropna().sort_values()
    m = len(valid)
    if m == 0:
        return out
    adjusted = valid * m / np.arange(1, m + 1)
    adjusted = adjusted.iloc[::-1].cummin().iloc[::-1].clip(upper=1)
    out.loc[adjusted.index] = adjusted
    return out


def markdown_table(data: pd.DataFrame, cols: list[str] | None = None) -> str:
    frame = data.copy()
    if cols is not None:
        frame = frame[cols]
    if frame.empty:
        return "_No rows._"
    try:
        return frame.to_markdown(index=False)
    except ImportError:
        return frame.to_csv(index=False)


def read_partner_panel(sample: str) -> pd.DataFrame:
    path = sample_results_dir(sample) / "exercise_01_tables" / "partner_concentration_all_years.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing partner concentration table: {path}")
    data = pd.read_csv(path)
    required = {"country", "iso3", "reporter_code", "year", "flow", "partner_gini", "partner_active_count"}
    missing = sorted(required - set(data.columns))
    if missing:
        raise ValueError(f"Missing required columns in {path}: {missing}")
    data = data[data["flow"].isin(["Exports", "Imports"])].copy()
    data["year"] = pd.to_numeric(data["year"], errors="coerce")
    data["partner_gini"] = pd.to_numeric(data["partner_gini"], errors="coerce")
    data["partner_active_count"] = pd.to_numeric(data["partner_active_count"], errors="coerce")
    data = data.dropna(subset=["year", "partner_gini", "reporter_code"])
    data["year"] = data["year"].astype(int)
    return data


def make_window(data: pd.DataFrame, label: str, start_year: int, end_year: int, balanced: bool) -> pd.DataFrame:
    work = data[data["year"].between(start_year, end_year)].copy()
    if not balanced:
        work["window"] = label
        return work
    expected_years = set(range(start_year, end_year + 1))
    keep_keys: list[tuple[int, str]] = []
    for (reporter_code, flow), group in work.groupby(["reporter_code", "flow"], sort=False):
        years = set(group["year"].astype(int))
        if expected_years.issubset(years):
            keep_keys.append((int(reporter_code), str(flow)))
    keep = pd.MultiIndex.from_tuples(keep_keys, names=["reporter_code", "flow"])
    keyed = pd.MultiIndex.from_frame(work[["reporter_code", "flow"]])
    out = work[keyed.isin(keep)].copy()
    out["window"] = label
    return out


def fit_common_trend(group: pd.DataFrame) -> dict[str, object]:
    work = group.dropna(subset=["partner_gini", "year", "reporter_code"]).copy()
    work["trend"] = work["year"] - work["year"].min()
    y = work["partner_gini"].astype(float)
    country_dummies = pd.get_dummies(work["reporter_code"].astype(str), prefix="country", drop_first=True)
    x = pd.concat([work[["trend"]].astype(float), country_dummies.astype(float)], axis=1)
    x = sm.add_constant(x, has_constant="add")
    if work["reporter_code"].nunique() < 2:
        return {
            "coefficient_per_year": np.nan,
            "coefficient_per_decade": np.nan,
            "std_error_per_year": np.nan,
            "std_error_per_decade": np.nan,
            "p_value": np.nan,
            "ci_low": np.nan,
            "ci_high": np.nan,
            "ci_low_per_decade": np.nan,
            "ci_high_per_decade": np.nan,
            "nobs": len(work),
            "countries": work["reporter_code"].nunique(),
            "r_squared": np.nan,
            "status": "too_few_clusters",
        }
    try:
        model = sm.OLS(y, x).fit(
            cov_type="cluster",
            cov_kwds={"groups": work["reporter_code"]},
            use_t=True,
        )
        coef = float(model.params.get("trend", np.nan))
        se = float(model.bse.get("trend", np.nan))
        p_value = float(model.pvalues.get("trend", np.nan))
        ci = model.conf_int().loc["trend"].tolist() if "trend" in model.params.index else [np.nan, np.nan]
        return {
            "coefficient_per_year": coef,
            "coefficient_per_decade": coef * 10,
            "std_error_per_year": se,
            "std_error_per_decade": se * 10,
            "p_value": p_value,
            "ci_low": float(ci[0]),
            "ci_high": float(ci[1]),
            "ci_low_per_decade": float(ci[0]) * 10,
            "ci_high_per_decade": float(ci[1]) * 10,
            "nobs": int(model.nobs),
            "countries": int(work["reporter_code"].nunique()),
            "r_squared": float(model.rsquared),
            "status": "ok",
        }
    except Exception as exc:  # pragma: no cover - written to diagnostics
        return {
            "coefficient_per_year": np.nan,
            "coefficient_per_decade": np.nan,
            "std_error_per_year": np.nan,
            "std_error_per_decade": np.nan,
            "p_value": np.nan,
            "ci_low": np.nan,
            "ci_high": np.nan,
            "ci_low_per_decade": np.nan,
            "ci_high_per_decade": np.nan,
            "nobs": len(work),
            "countries": work["reporter_code"].nunique(),
            "r_squared": np.nan,
            "status": f"error: {exc}",
        }


def fit_country_slope(group: pd.DataFrame) -> dict[str, object]:
    work = group.sort_values("year").dropna(subset=["partner_gini", "year"]).copy()
    first = work.iloc[0]
    last = work.iloc[-1]
    out: dict[str, object] = {
        "country": first["country"],
        "iso3": first["iso3"],
        "reporter_code": int(first["reporter_code"]),
        "flow": first["flow"],
        "n_years": int(work["year"].nunique()),
        "first_year": int(first["year"]),
        "last_year": int(last["year"]),
        "first_partner_gini": float(first["partner_gini"]),
        "last_partner_gini": float(last["partner_gini"]),
        "endpoint_change": float(last["partner_gini"] - first["partner_gini"]),
        "abs_endpoint_change": float(abs(last["partner_gini"] - first["partner_gini"])),
        "mean_partner_gini": float(work["partner_gini"].mean()),
        "sd_partner_gini": float(work["partner_gini"].std(ddof=1)),
        "min_partner_gini": float(work["partner_gini"].min()),
        "max_partner_gini": float(work["partner_gini"].max()),
        "range_partner_gini": float(work["partner_gini"].max() - work["partner_gini"].min()),
        "first_partner_active_count": float(first["partner_active_count"]),
        "last_partner_active_count": float(last["partner_active_count"]),
        "min_partner_active_count": float(work["partner_active_count"].min()),
        "median_partner_active_count": float(work["partner_active_count"].median()),
        "mean_partner_active_count": float(work["partner_active_count"].mean()),
    }
    if out["n_years"] < MIN_YEARS_FOR_COUNTRY_SLOPE:
        out.update(
            {
                "slope_per_year": np.nan,
                "slope_per_decade": np.nan,
                "slope_std_error": np.nan,
                "slope_p_value": np.nan,
                "slope_ci_low": np.nan,
                "slope_ci_high": np.nan,
                "status": "too_few_years",
            }
        )
        return out

    trend = (work["year"] - work["year"].min()).astype(float)
    x = sm.add_constant(trend, has_constant="add")
    # Newey-West/HAC p-values are a descriptive guardrail for serially
    # correlated annual country series. Practical effect sizes matter more.
    hac_maxlags = max(1, int(round(4 * (out["n_years"] / 100) ** (2 / 9))))
    model = sm.OLS(work["partner_gini"].astype(float), x).fit(cov_type="HAC", cov_kwds={"maxlags": hac_maxlags})
    slope = float(model.params.iloc[1])
    ci = model.conf_int().iloc[1].tolist()
    out.update(
        {
            "slope_per_year": slope,
            "slope_per_decade": slope * 10,
            "slope_std_error": float(model.bse.iloc[1]),
            "slope_p_value": float(model.pvalues.iloc[1]),
            "slope_ci_low": float(ci[0]),
            "slope_ci_high": float(ci[1]),
            "slope_se_method": "HAC/Newey-West",
            "slope_hac_maxlags": hac_maxlags,
            "status": "ok",
        }
    )
    return out


def variance_decomposition(group: pd.DataFrame) -> dict[str, object]:
    work = group.dropna(subset=["partner_gini", "year", "reporter_code"]).copy()
    y = work["partner_gini"].astype(float)
    country = pd.get_dummies(work["reporter_code"].astype(str), prefix="country", drop_first=True).astype(float)
    year = pd.get_dummies(work["year"].astype(str), prefix="year", drop_first=True).astype(float)
    x_country = sm.add_constant(country, has_constant="add")
    x_country_year = sm.add_constant(pd.concat([country, year], axis=1), has_constant="add")
    country_model = sm.OLS(y, x_country).fit()
    country_year_model = sm.OLS(y, x_country_year).fit()
    return {
        "nobs": int(country_year_model.nobs),
        "countries": int(work["reporter_code"].nunique()),
        "years": int(work["year"].nunique()),
        "r2_country_fe": float(country_model.rsquared),
        "r2_country_year_fe": float(country_year_model.rsquared),
        "incremental_r2_year_fe": float(country_year_model.rsquared - country_model.rsquared),
        "rmse_country_fe": float(np.sqrt(np.mean(country_model.resid**2))),
        "rmse_country_year_fe": float(np.sqrt(np.mean(country_year_model.resid**2))),
    }


def build_country_slopes(windows: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (window, reporter_code, flow), group in windows.groupby(["window", "reporter_code", "flow"], sort=True):
        row = fit_country_slope(group)
        row["window"] = window
        rows.append(row)
    out = pd.DataFrame(rows)
    out["slope_q_value"] = out.groupby(["window", "flow"])["slope_p_value"].transform(bh_q_values)
    out["abs_slope_per_decade"] = out["slope_per_decade"].abs()
    out["stable_slope_10yr_0p02"] = out["abs_slope_per_decade"].le(STABILITY_SLOPE_10YR_MARGIN)
    out["stable_endpoint_0p05"] = out["abs_endpoint_change"].le(STABILITY_ENDPOINT_MARGIN)
    out["stable_sd_0p02"] = out["sd_partner_gini"].le(STABILITY_SD_MARGIN)
    out["low_active_partner_warning"] = out["min_partner_active_count"].lt(LOW_ACTIVE_PARTNER_THRESHOLD)
    return out


def build_common_trends(windows: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (window, flow), group in windows.groupby(["window", "flow"], sort=True):
        row = fit_common_trend(group)
        row.update({"window": window, "flow": flow})
        rows.append(row)
    out = pd.DataFrame(rows)
    out["bh_q_value"] = bh_q_values(out["p_value"])
    out["stars"] = out["p_value"].map(p_to_stars)
    return out


def build_variance_decomposition(windows: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (window, flow), group in windows.groupby(["window", "flow"], sort=True):
        row = variance_decomposition(group)
        row.update({"window": window, "flow": flow})
        rows.append(row)
    return pd.DataFrame(rows)


def build_window_count_diagnostics(panel: pd.DataFrame, main_window: pd.DataFrame, balanced_window: pd.DataFrame) -> dict[str, object]:
    def count_country_flows(frame: pd.DataFrame) -> int:
        return int(frame[["reporter_code", "flow"]].drop_duplicates().shape[0])

    return {
        "source_rows": int(len(panel)),
        "source_country_flows": count_country_flows(panel),
        "source_countries": int(panel["reporter_code"].nunique()),
        "source_year_min": int(panel["year"].min()),
        "source_year_max": int(panel["year"].max()),
        "duplicate_country_year_flow_keys": int(panel.duplicated(["reporter_code", "year", "flow"]).sum()),
        "missing_partner_gini_rows": int(panel["partner_gini"].isna().sum()),
        "main_window_rows": int(len(main_window)),
        "main_window_country_flows": count_country_flows(main_window),
        "main_window_countries": int(main_window["reporter_code"].nunique()),
        "balanced_window_rows": int(len(balanced_window)),
        "balanced_window_country_flows": count_country_flows(balanced_window),
        "balanced_window_countries": int(balanced_window["reporter_code"].nunique()),
    }


def build_low_active_partner_sensitivity(windows: pd.DataFrame, threshold: int = LOW_ACTIVE_PARTNER_THRESHOLD) -> pd.DataFrame:
    filtered = windows[pd.to_numeric(windows["partner_active_count"], errors="coerce").ge(threshold)].copy()
    filtered_slopes = build_country_slopes(filtered)
    ok = filtered_slopes[filtered_slopes["status"].eq("ok")].copy()
    rows = []
    for (window, flow), original_group in windows.groupby(["window", "flow"], sort=True):
        filtered_group = filtered[(filtered["window"].eq(window)) & (filtered["flow"].eq(flow))]
        slope_group = ok[(ok["window"].eq(window)) & (ok["flow"].eq(flow))]
        row = {
            "window": window,
            "flow": flow,
            "min_partner_active_count_required": threshold,
            "original_rows": int(len(original_group)),
            "kept_rows": int(len(filtered_group)),
            "dropped_rows": int(len(original_group) - len(filtered_group)),
            "original_country_flows": int(original_group[["reporter_code", "flow"]].drop_duplicates().shape[0]),
            "eligible_country_flows": int(slope_group[["reporter_code", "flow"]].drop_duplicates().shape[0]),
            "countries": int(slope_group["reporter_code"].nunique()) if not slope_group.empty else 0,
        }
        if slope_group.empty:
            row.update(
                {
                    "median_abs_slope_per_decade": np.nan,
                    "share_stable_slope_10yr_0p02": np.nan,
                    "median_abs_endpoint_change": np.nan,
                    "share_stable_endpoint_0p05": np.nan,
                    "country_flows_with_low_partner_warning": np.nan,
                }
            )
        else:
            row.update(
                {
                    "median_abs_slope_per_decade": float(slope_group["abs_slope_per_decade"].median()),
                    "share_stable_slope_10yr_0p02": float(slope_group["stable_slope_10yr_0p02"].mean()),
                    "median_abs_endpoint_change": float(slope_group["abs_endpoint_change"].median()),
                    "share_stable_endpoint_0p05": float(slope_group["stable_endpoint_0p05"].mean()),
                    "country_flows_with_low_partner_warning": int(slope_group["low_active_partner_warning"].sum()),
                }
            )
        rows.append(row)
    return pd.DataFrame(rows)


def build_summary(slopes: pd.DataFrame) -> pd.DataFrame:
    rows = []
    ok = slopes[slopes["status"].eq("ok")].copy()
    for (window, flow), group in ok.groupby(["window", "flow"], sort=True):
        row = {
            "window": window,
            "flow": flow,
            "countries": int(group["reporter_code"].nunique()),
            "median_abs_slope_per_decade": float(group["abs_slope_per_decade"].median()),
            "p90_abs_slope_per_decade": float(group["abs_slope_per_decade"].quantile(0.90)),
            "max_abs_slope_per_decade": float(group["abs_slope_per_decade"].max()),
            "share_stable_slope_10yr_0p02": float(group["stable_slope_10yr_0p02"].mean()),
            "share_stable_endpoint_0p05": float(group["stable_endpoint_0p05"].mean()),
            "share_stable_sd_0p02": float(group["stable_sd_0p02"].mean()),
            "median_abs_endpoint_change": float(group["abs_endpoint_change"].median()),
            "p90_abs_endpoint_change": float(group["abs_endpoint_change"].quantile(0.90)),
            "max_abs_endpoint_change": float(group["abs_endpoint_change"].max()),
            "median_within_country_sd": float(group["sd_partner_gini"].median()),
            "p90_within_country_sd": float(group["sd_partner_gini"].quantile(0.90)),
            "countries_with_slope_p_lt_0p05": int(group["slope_p_value"].lt(0.05).sum()),
            "countries_with_slope_q_lt_0p05": int(group["slope_q_value"].lt(0.05).sum()),
        }
        for margin in SLOPE_MARGIN_GRID:
            key = f"share_abs_slope_10yr_le_{str(margin).replace('.', 'p')}"
            row[key] = float(group["abs_slope_per_decade"].le(margin).mean())
        for margin in ENDPOINT_MARGIN_GRID:
            key = f"share_abs_endpoint_le_{str(margin).replace('.', 'p')}"
            row[key] = float(group["abs_endpoint_change"].le(margin).mean())
        rows.append(row)
    return pd.DataFrame(rows)


def make_slope_distribution(slopes: pd.DataFrame, path: Path) -> None:
    data = slopes[(slopes["window"].eq("main_2000_2024")) & (slopes["status"].eq("ok"))].copy()
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8), dpi=180, sharey=True)
    for ax, flow in zip(axes, ["Exports", "Imports"]):
        sub = data[data["flow"].eq(flow)]
        ax.hist(sub["slope_per_decade"], bins=18, color=FLOW_COLORS[flow], alpha=0.78, edgecolor="white")
        ax.axvline(0, color="#111827", linewidth=1.1)
        ax.axvline(STABILITY_SLOPE_10YR_MARGIN, color="#6b7280", linestyle="--", linewidth=1)
        ax.axvline(-STABILITY_SLOPE_10YR_MARGIN, color="#6b7280", linestyle="--", linewidth=1)
        ax.set_title(flow)
        ax.set_xlabel("Fitted 10-year change in Partner Gini")
        ax.grid(axis="y", color="#e5e7eb")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    axes[0].set_ylabel("Countries")
    fig.suptitle("Country-Specific Partner Gini Trends, rd2 Countries, 2000-2024", fontsize=14)
    fig.text(0.01, 0.01, "Dashed lines mark the practical stability margin: +/-0.02 Gini points per decade.", fontsize=8.5)
    fig.tight_layout(rect=[0, 0.05, 1, 0.95])
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def make_endpoint_change_figure(slopes: pd.DataFrame, path: Path) -> None:
    data = slopes[(slopes["window"].eq("main_2000_2024")) & (slopes["status"].eq("ok"))].copy()
    rows = []
    for flow, group in data.groupby("flow"):
        top = group.sort_values("endpoint_change").head(5)
        bottom = group.sort_values("endpoint_change").tail(5)
        rows.append(pd.concat([top, bottom], ignore_index=True))
    plot = pd.concat(rows, ignore_index=True)
    plot["label"] = plot["iso3"] + " (" + plot["flow"].str[0] + ")"
    plot = plot.sort_values(["flow", "endpoint_change"])
    colors = plot["flow"].map(FLOW_COLORS)
    fig, ax = plt.subplots(figsize=(9.5, 6), dpi=180)
    ax.barh(plot["label"], plot["endpoint_change"], color=colors, alpha=0.82)
    ax.axvline(0, color="#111827", linewidth=1)
    ax.axvline(STABILITY_ENDPOINT_MARGIN, color="#6b7280", linestyle="--", linewidth=1)
    ax.axvline(-STABILITY_ENDPOINT_MARGIN, color="#6b7280", linestyle="--", linewidth=1)
    ax.set_xlabel("Endpoint change in Partner Gini")
    ax.set_title("Largest Partner Gini Endpoint Changes, 2000-2024")
    ax.grid(axis="x", color="#e5e7eb")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.text(0.01, 0.01, "Labels show ISO3 and flow initial. Dashed lines mark +/-0.05 endpoint-change margin.", fontsize=8.5)
    fig.tight_layout(rect=[0, 0.05, 1, 1])
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def write_memo(
    path: Path,
    args: argparse.Namespace,
    source_path: Path,
    summary: pd.DataFrame,
    common_trends: pd.DataFrame,
    variance: pd.DataFrame,
    low_active_sensitivity: pd.DataFrame,
    slopes: pd.DataFrame,
    count_diagnostics: dict[str, object],
    output_paths: OutputPaths,
) -> None:
    main_summary = summary[summary["window"].eq("main_2000_2024")].copy()
    main_common = common_trends[common_trends["window"].eq("main_2000_2024")].copy()
    main_variance = variance[variance["window"].eq("main_2000_2024")].copy()
    biggest = (
        slopes[(slopes["window"].eq("main_2000_2024")) & (slopes["status"].eq("ok"))]
        .sort_values("abs_endpoint_change", ascending=False)
        .head(12)
        .copy()
    )
    display_summary = main_summary[
        [
            "flow",
            "countries",
            "median_abs_slope_per_decade",
            "p90_abs_slope_per_decade",
            "share_stable_slope_10yr_0p02",
            "median_abs_endpoint_change",
            "p90_abs_endpoint_change",
            "share_stable_endpoint_0p05",
            "median_within_country_sd",
            "countries_with_slope_q_lt_0p05",
        ]
    ].round(4)
    display_common = main_common[
        [
            "flow",
            "coefficient_per_decade",
            "std_error_per_decade",
            "ci_low_per_decade",
            "ci_high_per_decade",
            "p_value",
            "bh_q_value",
            "nobs",
            "countries",
            "r_squared",
            "status",
        ]
    ].round(5)
    display_variance = main_variance[
        [
            "flow",
            "r2_country_fe",
            "r2_country_year_fe",
            "incremental_r2_year_fe",
            "rmse_country_fe",
            "rmse_country_year_fe",
        ]
    ].round(5)
    display_biggest = biggest[
        [
            "flow",
            "country",
            "iso3",
            "first_year",
            "last_year",
            "first_partner_gini",
            "last_partner_gini",
            "endpoint_change",
            "slope_per_decade",
            "sd_partner_gini",
            "slope_q_value",
            "first_partner_active_count",
            "last_partner_active_count",
            "min_partner_active_count",
            "median_partner_active_count",
        ]
    ].round(4)
    display_low_active = low_active_sensitivity[
        [
            "window",
            "flow",
            "min_partner_active_count_required",
            "original_rows",
            "kept_rows",
            "dropped_rows",
            "eligible_country_flows",
            "median_abs_slope_per_decade",
            "share_stable_slope_10yr_0p02",
            "median_abs_endpoint_change",
            "share_stable_endpoint_0p05",
        ]
    ].round(4)
    display_counts = pd.DataFrame(
        [
            {"diagnostic": "Source rows", "value": count_diagnostics["source_rows"]},
            {"diagnostic": "Source country-flow series", "value": count_diagnostics["source_country_flows"]},
            {"diagnostic": "Duplicate country-year-flow keys", "value": count_diagnostics["duplicate_country_year_flow_keys"]},
            {"diagnostic": "Missing Partner Gini rows", "value": count_diagnostics["missing_partner_gini_rows"]},
            {"diagnostic": f"Main-window rows ({args.start_year}-{args.end_year})", "value": count_diagnostics["main_window_rows"]},
            {"diagnostic": "Main-window country-flow series", "value": count_diagnostics["main_window_country_flows"]},
            {
                "diagnostic": f"Balanced-window rows ({BALANCED_START_YEAR}-{BALANCED_END_YEAR})",
                "value": count_diagnostics["balanced_window_rows"],
            },
            {"diagnostic": "Balanced-window country-flow series", "value": count_diagnostics["balanced_window_country_flows"]},
        ]
    )

    text = f"""# Partner Gini Stability Test

Generated: {now_utc()}

## Question

Is active Partner Gini relatively stable over time within rd2 countries?

This is a descriptive panel/time-series stability check, not a causal design. The unit is country-year-flow. Partner Gini measures concentration across observed positive destination/source partner totals. The source table inherits the project partner convention: partner totals include HS6 `999999`, while aggregate `partnerCode == 0` is excluded upstream.

## Main Test Window

- Sample: `{args.country_sample}`
- Source: `{rel(source_path)}`
- Main window: {args.start_year}-{args.end_year}, excluding partial 2025 coverage.
- Balanced sensitivity: {BALANCED_START_YEAR}-{BALANCED_END_YEAR}, country-flow rows with every year in that interval.
- Practical stability margin for slopes: absolute fitted 10-year change in Partner Gini <= {STABILITY_SLOPE_10YR_MARGIN}.
- Practical stability margin for endpoints: absolute first-to-last change <= {STABILITY_ENDPOINT_MARGIN}.

## Main Results

{markdown_table(display_summary)}

## Common Within-Country Trend

Specification: `partner_gini_ct = beta * trend_t + country_FE_c + error_ct`, estimated separately by flow with standard errors clustered by reporter country. Coefficients, standard errors, and confidence intervals are scaled to a 10-year change.

{markdown_table(display_common)}

The `p_value` column is the raw clustered-inference p-value. The `bh_q_value` column applies a Benjamini-Hochberg adjustment across the common-trend rows in this exercise.

## How Much Do Common Year Effects Add?

This compares country fixed effects alone with country plus year fixed effects. A small incremental R-squared from year fixed effects means common time movement is small relative to persistent country differences and residual year-to-year variation.

{markdown_table(display_variance)}

## Largest Country Endpoint Changes

{markdown_table(display_biggest)}

Active-partner counts in this table are diagnostic coverage warnings. A large endpoint change is less interpretable when the first or minimum active-partner count is very low.

## Low Active-Partner Sensitivity

This sensitivity drops reporter-year-flow observations with fewer than {LOW_ACTIVE_PARTNER_THRESHOLD} active trade partners, then recomputes the same country-flow stability summary. It treats very low partner counts as coverage warnings, not as proof that the original observation is invalid.

{markdown_table(display_low_active)}

## Count Diagnostics

{markdown_table(display_counts)}

## Interpretation

The hypothesis is mostly true for the cross-country median and for most country-flow series: Partner Gini is high and moves slowly. It is not true literally for every country. Some countries have large endpoint changes or statistically detectable country-specific trends, so the defensible statement is \"Partner Gini is relatively stable for most rd2 countries over 2000-2024, with meaningful country exceptions.\"

## Outputs

- `{rel(output_paths.country_slopes)}`
- `{rel(output_paths.summary)}`
- `{rel(output_paths.common_trends)}`
- `{rel(output_paths.variance_decomposition)}`
- `{rel(output_paths.low_active_partner_sensitivity)}`
- `{rel(output_paths.slope_distribution_figure)}`
- `{rel(output_paths.endpoint_change_figure)}`
"""
    path.write_text(text, encoding="utf-8")


def write_manifest(
    path: Path,
    args: argparse.Namespace,
    source_path: Path,
    panel: pd.DataFrame,
    count_diagnostics: dict[str, object],
    output_paths: OutputPaths,
) -> None:
    payload = {
        "generated_at": now_utc(),
        "country_sample": args.country_sample,
        "source": rel(source_path),
        "main_window": [args.start_year, args.end_year],
        "balanced_window": [BALANCED_START_YEAR, BALANCED_END_YEAR],
        "count_diagnostics": count_diagnostics,
        "partner_convention": {
            "hs6_999999": "included in partner totals by convention",
            "partner_code_0": "excluded upstream by concentration pipeline",
        },
        "rows": int(len(panel)),
        "year_min": int(panel["year"].min()),
        "year_max": int(panel["year"].max()),
        "outputs": {
            "memo": rel(output_paths.memo_path),
            "country_slopes": rel(output_paths.country_slopes),
            "summary": rel(output_paths.summary),
            "common_trends": rel(output_paths.common_trends),
            "variance_decomposition": rel(output_paths.variance_decomposition),
            "low_active_partner_sensitivity": rel(output_paths.low_active_partner_sensitivity),
            "slope_distribution_figure": rel(output_paths.slope_distribution_figure),
            "endpoint_change_figure": rel(output_paths.endpoint_change_figure),
        },
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country-sample", default=DEFAULT_SAMPLE)
    parser.add_argument("--start-year", type=int, default=DEFAULT_START_YEAR)
    parser.add_argument("--end-year", type=int, default=DEFAULT_END_YEAR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    base_results = sample_results_dir(args.country_sample)
    source_path = base_results / "exercise_01_tables" / "partner_concentration_all_years.csv"
    table_dir = base_results / "partner_gini_stability_tables"
    figure_dir = base_results / "partner_gini_stability_figures"
    output_paths = OutputPaths(
        table_dir=table_dir,
        figure_dir=figure_dir,
        memo_path=base_results / "partner_gini_stability.md",
        manifest_path=base_results / "run_manifest_partner_gini_stability.json",
        country_slopes=table_dir / "country_flow_stability.csv",
        summary=table_dir / "stability_summary.csv",
        common_trends=table_dir / "common_trend_models.csv",
        variance_decomposition=table_dir / "variance_decomposition.csv",
        low_active_partner_sensitivity=table_dir / "low_active_partner_sensitivity.csv",
        slope_distribution_figure=figure_dir / "country_slope_distribution.png",
        endpoint_change_figure=figure_dir / "largest_endpoint_changes.png",
    )
    ensure_dirs(table_dir, figure_dir)

    panel = read_partner_panel(args.country_sample)
    main_window = make_window(panel, "main_2000_2024", args.start_year, args.end_year, balanced=False)
    balanced_window = make_window(panel, "balanced_2001_2021", BALANCED_START_YEAR, BALANCED_END_YEAR, balanced=True)
    windows = pd.concat([main_window, balanced_window], ignore_index=True)
    count_diagnostics = build_window_count_diagnostics(panel, main_window, balanced_window)

    slopes = build_country_slopes(windows)
    summary = build_summary(slopes)
    common_trends = build_common_trends(windows)
    variance = build_variance_decomposition(windows)
    low_active_sensitivity = build_low_active_partner_sensitivity(windows)

    slopes.to_csv(output_paths.country_slopes, index=False)
    summary.to_csv(output_paths.summary, index=False)
    common_trends.to_csv(output_paths.common_trends, index=False)
    variance.to_csv(output_paths.variance_decomposition, index=False)
    low_active_sensitivity.to_csv(output_paths.low_active_partner_sensitivity, index=False)
    make_slope_distribution(slopes, output_paths.slope_distribution_figure)
    make_endpoint_change_figure(slopes, output_paths.endpoint_change_figure)
    write_memo(
        output_paths.memo_path,
        args,
        source_path,
        summary,
        common_trends,
        variance,
        low_active_sensitivity,
        slopes,
        count_diagnostics,
        output_paths,
    )
    write_manifest(output_paths.manifest_path, args, source_path, panel, count_diagnostics, output_paths)

    print(f"Wrote {rel(output_paths.memo_path)}")
    print(f"Wrote {rel(output_paths.country_slopes)}")
    print(f"Wrote {rel(output_paths.summary)}")
    print(f"Wrote {rel(output_paths.common_trends)}")
    print(f"Wrote {rel(output_paths.variance_decomposition)}")
    print(f"Wrote {rel(output_paths.slope_distribution_figure)}")
    print(f"Wrote {rel(output_paths.endpoint_change_figure)}")
    print(f"Wrote {rel(output_paths.manifest_path)}")


if __name__ == "__main__":
    main()
