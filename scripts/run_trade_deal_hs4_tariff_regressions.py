#!/usr/bin/env python3
"""Run descriptive HS4 WITS tariff regressions for export concentration.

These regressions are descriptive fixed-effects panel evidence. They do not
implement a causal event-study or DiD design.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from linearmodels.panel import PanelOLS

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_trade_deal_hs4_tariff_diagnostics as hs4diag  # noqa: E402

COUNTRY_SAMPLE = "rd2_countries"
PROCESSED_DIR = ROOT / "data" / "processed" / "samples" / COUNTRY_SAMPLE
RESULTS_DIR = ROOT / "results" / "samples" / COUNTRY_SAMPLE / "trade_deal_market_access"

OUTCOME = "product_gini"
EXPOSURE = "market_access_tariff_avg_i_t"
WEIGHT_COVERAGE = "tariff_weight_coverage_i_t"
ENTITY = "iso3"
TIME = "year"


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def datatype_slug(datatype: str) -> str:
    return hs4diag.datatype_slug(datatype)


def datatype_suffix(datatype: str) -> str:
    return hs4diag.datatype_suffix(datatype)


def panel_path(datatype: str) -> Path:
    return PROCESSED_DIR / f"trade_deal_hs4_market_access_diagnostics_panel{datatype_suffix(datatype)}.parquet"


def read_panel(datatype: str) -> pd.DataFrame:
    path = panel_path(datatype)
    if not path.exists():
        raise FileNotFoundError(f"Missing diagnostics panel: {relative_path(path)}")
    df = pd.read_parquet(path)
    required = {ENTITY, "country", "reporter_code", TIME, OUTCOME, EXPOSURE, WEIGHT_COVERAGE}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{relative_path(path)} missing required columns: {sorted(missing)}")
    duplicate_keys = int(df.duplicated([ENTITY, "reporter_code", TIME]).sum())
    if duplicate_keys:
        raise ValueError(f"{relative_path(path)} has duplicate iso3-reporter_code-year rows: {duplicate_keys}")
    df = df.copy()
    df[TIME] = pd.to_numeric(df[TIME], errors="coerce").astype("Int64")
    df[OUTCOME] = pd.to_numeric(df[OUTCOME], errors="coerce")
    df[EXPOSURE] = pd.to_numeric(df[EXPOSURE], errors="coerce")
    df[WEIGHT_COVERAGE] = pd.to_numeric(df[WEIGHT_COVERAGE], errors="coerce")
    df["datatype"] = datatype
    df["datatype_slug"] = datatype_slug(datatype)
    return df


def sample_for_threshold(df: pd.DataFrame, threshold: float) -> pd.DataFrame:
    work = df[
        df[OUTCOME].notna()
        & df[EXPOSURE].notna()
        & df[WEIGHT_COVERAGE].ge(threshold)
        & df[ENTITY].notna()
        & df[TIME].notna()
    ].copy()
    work["tariff_coverage_threshold"] = threshold
    work = work.sort_values([ENTITY, TIME]).reset_index(drop=True)
    return work


def safe_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def fit_fe_model(work: pd.DataFrame, datatype: str, threshold: float, cov_kind: str) -> dict[str, Any]:
    if work.empty:
        raise ValueError(f"No usable rows for {datatype} threshold {threshold}")
    if work[ENTITY].nunique() < 2 or work[TIME].nunique() < 2:
        raise ValueError(f"Insufficient entity/time variation for {datatype} threshold {threshold}")

    reg = work[[ENTITY, TIME, OUTCOME, EXPOSURE]].copy()
    reg = reg.set_index([ENTITY, TIME])
    y = reg[OUTCOME]
    x = reg[[EXPOSURE]]
    model = PanelOLS(y, x, entity_effects=True, time_effects=True, drop_absorbed=True, check_rank=True)
    fit_kwargs: dict[str, Any] = {"cov_type": "clustered"}
    if cov_kind == "entity":
        fit_kwargs["cluster_entity"] = True
    elif cov_kind == "entity_time":
        fit_kwargs["cluster_entity"] = True
        fit_kwargs["cluster_time"] = True
    else:
        raise ValueError(f"Unknown covariance kind: {cov_kind}")
    result = model.fit(**fit_kwargs)
    param = safe_float(result.params.get(EXPOSURE))
    se = safe_float(result.std_errors.get(EXPOSURE))
    pvalue = safe_float(result.pvalues.get(EXPOSURE))
    tstat = safe_float(result.tstats.get(EXPOSURE))
    return {
        "model_id": f"{datatype_slug(datatype)}_coverage_{int(threshold * 100):03d}_{cov_kind}",
        "datatype": datatype,
        "datatype_slug": datatype_slug(datatype),
        "coverage_threshold": threshold,
        "covariance": cov_kind,
        "outcome": OUTCOME,
        "exposure": EXPOSURE,
        "formula": f"{OUTCOME}_it = beta * {EXPOSURE}_it + reporter FE + year FE + error_it",
        "coef": param,
        "std_error": se,
        "t_stat": tstat,
        "p_value": pvalue,
        "nobs": int(result.nobs),
        "entities": int(work[ENTITY].nunique()),
        "years": int(work[TIME].nunique()),
        "year_min": int(work[TIME].min()),
        "year_max": int(work[TIME].max()),
        "rsquared_within": safe_float(result.rsquared_within),
        "rsquared_overall": safe_float(result.rsquared_overall),
        "mean_outcome": safe_float(work[OUTCOME].mean()),
        "mean_exposure": safe_float(work[EXPOSURE].mean()),
        "median_exposure": safe_float(work[EXPOSURE].median()),
        "mean_coverage": safe_float(work[WEIGHT_COVERAGE].mean()),
        "interpretation": "Coefficient is product-Gini points per 1 percentage-point increase in destination-weighted tariff exposure.",
    }


def build_attrition(datatype: str, df: pd.DataFrame, thresholds: list[float]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    base_rows = int(len(df))
    for threshold in thresholds:
        work = sample_for_threshold(df, threshold)
        rows.append(
            {
                "datatype": datatype,
                "datatype_slug": datatype_slug(datatype),
                "coverage_threshold": threshold,
                "candidate_rows": base_rows,
                "regression_rows": int(len(work)),
                "dropped_rows": int(base_rows - len(work)),
                "countries": int(work[ENTITY].nunique()),
                "years": int(work[TIME].nunique()) if not work.empty else 0,
                "year_min": int(work[TIME].min()) if not work.empty else None,
                "year_max": int(work[TIME].max()) if not work.empty else None,
                "mean_product_gini": safe_float(work[OUTCOME].mean()) if not work.empty else None,
                "mean_tariff_exposure": safe_float(work[EXPOSURE].mean()) if not work.empty else None,
                "mean_tariff_weight_coverage": safe_float(work[WEIGHT_COVERAGE].mean()) if not work.empty else None,
            }
        )
    return pd.DataFrame(rows)


def build_pass_fail_balance(datatype: str, df: pd.DataFrame, thresholds: list[float]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for threshold in thresholds:
        work = df[df[OUTCOME].notna() & df[EXPOSURE].notna() & df[WEIGHT_COVERAGE].notna()].copy()
        work["coverage_group"] = np.where(work[WEIGHT_COVERAGE].ge(threshold), "pass", "fail")
        for group_name, group in work.groupby("coverage_group", observed=True):
            rows.append(
                {
                    "datatype": datatype,
                    "datatype_slug": datatype_slug(datatype),
                    "coverage_threshold": threshold,
                    "coverage_group": group_name,
                    "rows": int(len(group)),
                    "countries": int(group[ENTITY].nunique()),
                    "years": int(group[TIME].nunique()),
                    "year_min": int(group[TIME].min()) if not group.empty else None,
                    "year_max": int(group[TIME].max()) if not group.empty else None,
                    "mean_product_gini": safe_float(group[OUTCOME].mean()),
                    "median_product_gini": safe_float(group[OUTCOME].median()),
                    "mean_tariff_exposure": safe_float(group[EXPOSURE].mean()),
                    "median_tariff_exposure": safe_float(group[EXPOSURE].median()),
                    "mean_tariff_weight_coverage": safe_float(group[WEIGHT_COVERAGE].mean()),
                    "median_tariff_weight_coverage": safe_float(group[WEIGHT_COVERAGE].median()),
                    "mean_total_trade_value": safe_float(pd.to_numeric(group.get("total_trade_value"), errors="coerce").mean())
                    if "total_trade_value" in group
                    else None,
                }
            )
    return pd.DataFrame(rows)


def pvalue_stars(pvalue: float | None) -> str:
    if pvalue is None:
        return ""
    if pvalue < 0.01:
        return "***"
    if pvalue < 0.05:
        return "**"
    if pvalue < 0.10:
        return "*"
    return ""


def fmt_num(value: float | None, digits: int = 4, bold: bool = False) -> str:
    if value is None:
        return ""
    text = f"{value:.{digits}f}"
    return f"**{text}**" if bold else text


def build_markdown(
    results: pd.DataFrame,
    attrition: pd.DataFrame,
    diagnostics: dict[str, Any],
) -> str:
    lines = [
        "# HS4 Tariff Regressions",
        "",
        f"Created UTC: `{diagnostics['created_at_utc']}`",
        "",
        "## Verdict",
        "",
        "- These are descriptive fixed-effects regressions, not causal estimates.",
        "- Outcome: export product concentration, `product_gini`.",
        "- Exposure: destination/importer-side HS4 WITS MFN/world tariff exposure, `market_access_tariff_avg_i_t`.",
        "- Fixed effects: reporter-country and calendar-year.",
        "- Inference: reporter-country clustering is default; two-way reporter/year clustering is reported as a sensitivity.",
        "",
        "## Main Results",
        "",
        "| datatype | coverage | covariance | rows | countries | coef | se | p-value | within R2 |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    preferred_order = [
        ("AVEEstimated", 0.80, "entity"),
        ("AVEEstimated", 0.80, "entity_time"),
        ("reported", 0.80, "entity"),
        ("reported", 0.80, "entity_time"),
        ("AVEEstimated", 0.90, "entity"),
        ("reported", 0.90, "entity"),
        ("AVEEstimated", 0.95, "entity"),
        ("reported", 0.95, "entity"),
    ]
    keyed = {
        (row["datatype"], float(row["coverage_threshold"]), row["covariance"]): row
        for row in results.to_dict("records")
    }
    for key in preferred_order:
        row = keyed.get(key)
        if row is None:
            continue
        pvalue = row.get("p_value")
        sig = pvalue is not None and pvalue < 0.05
        coef = fmt_num(row.get("coef"), bold=sig) + pvalue_stars(pvalue)
        ptxt = fmt_num(pvalue, digits=4, bold=sig)
        lines.append(
            "| {datatype} | {coverage:.2f} | {covariance} | {nobs} | {entities} | {coef} | {se} | {p} | {r2} |".format(
                datatype=row["datatype"],
                coverage=float(row["coverage_threshold"]),
                covariance=row["covariance"],
                nobs=int(row["nobs"]),
                entities=int(row["entities"]),
                coef=coef,
                se=fmt_num(row.get("std_error")),
                p=ptxt,
                r2=fmt_num(row.get("rsquared_within")),
            )
        )
    lines.extend(
        [
            "",
            "Plain English: the coefficient is the within-country, over-time association between a 1 percentage-point increase in destination-weighted tariffs and export product Gini.",
            "",
            "## Attrition",
            "",
            "| datatype | coverage | candidate rows | regression rows | countries | mean coverage |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in attrition.to_dict("records"):
        lines.append(
            "| {datatype} | {threshold:.2f} | {candidate} | {rows} | {countries} | {coverage} |".format(
                datatype=row["datatype"],
                threshold=float(row["coverage_threshold"]),
                candidate=int(row["candidate_rows"]),
                rows=int(row["regression_rows"]),
                countries=int(row["countries"]),
                coverage=fmt_num(row.get("mean_tariff_weight_coverage")),
            )
        )
    lines.extend(
        [
            "",
            "## Caveats",
            "",
            "- `AVEEstimated` is the stricter measure but has less coverage.",
            "- `reported` has broader coverage, but overlap validation shows a small tail of large AVE-vs-reported differences.",
            "- Pass/fail balance diagnostics are written to `hs4_tariff_regression_pass_fail_balance.csv`.",
            "- These estimates should not be presented as causal; treatment timing and agreement selection are not addressed here.",
            "- No regression table should be treated as final until the adversarial review is read alongside this output.",
        ]
    )
    return "\n".join(lines) + "\n"


def run(args: argparse.Namespace) -> dict[str, Any]:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    datatypes = args.datatypes
    thresholds = args.thresholds
    covariances = args.covariances

    result_rows: list[dict[str, Any]] = []
    attrition_rows: list[pd.DataFrame] = []
    balance_rows: list[pd.DataFrame] = []
    sample_chunks: list[pd.DataFrame] = []
    for datatype in datatypes:
        panel = read_panel(datatype)
        attrition_rows.append(build_attrition(datatype, panel, thresholds))
        balance_rows.append(build_pass_fail_balance(datatype, panel, thresholds))
        for threshold in thresholds:
            sample = sample_for_threshold(panel, threshold)
            sample_chunks.append(sample)
            for covariance in covariances:
                result_rows.append(fit_fe_model(sample, datatype, threshold, covariance))

    results = pd.DataFrame(result_rows)
    attrition = pd.concat(attrition_rows, ignore_index=True)
    balance = pd.concat(balance_rows, ignore_index=True)
    regression_sample = pd.concat(sample_chunks, ignore_index=True) if sample_chunks else pd.DataFrame()

    outputs = {
        "results_csv": RESULTS_DIR / "hs4_tariff_regressions.csv",
        "attrition_csv": RESULTS_DIR / "hs4_tariff_regression_attrition.csv",
        "pass_fail_balance_csv": RESULTS_DIR / "hs4_tariff_regression_pass_fail_balance.csv",
        "sample_parquet": PROCESSED_DIR / "trade_deal_hs4_tariff_regression_samples.parquet",
        "manifest_json": RESULTS_DIR / "hs4_tariff_regression_manifest.json",
        "markdown": RESULTS_DIR / "hs4_tariff_regressions.md",
    }
    results.to_csv(outputs["results_csv"], index=False)
    attrition.to_csv(outputs["attrition_csv"], index=False)
    balance.to_csv(outputs["pass_fail_balance_csv"], index=False)
    regression_sample.to_parquet(outputs["sample_parquet"], index=False)

    diagnostics = {
        "created_at_utc": now_utc(),
        "script": relative_path(Path(__file__)),
        "country_sample": COUNTRY_SAMPLE,
        "diagnostics_only": False,
        "causal_claim_allowed": False,
        "model": "PanelOLS with reporter-country and calendar-year fixed effects",
        "outcome": OUTCOME,
        "exposure": EXPOSURE,
        "datatypes": datatypes,
        "coverage_thresholds": thresholds,
        "covariances": covariances,
        "outputs": {key: relative_path(path) for key, path in outputs.items()},
        "regression_policy": "Descriptive FE evidence only; causal claims require a separate event-study or DiD design.",
    }
    outputs["manifest_json"].write_text(json.dumps(diagnostics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    outputs["markdown"].write_text(build_markdown(results, attrition, diagnostics), encoding="utf-8")
    return diagnostics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--datatypes",
        nargs="+",
        default=["AVEEstimated", "reported"],
        help="Tariff diagnostics datatypes to estimate.",
    )
    parser.add_argument(
        "--thresholds",
        nargs="+",
        type=float,
        default=[0.80, 0.90, 0.95],
        help="tariff_weight_coverage_i_t thresholds to estimate.",
    )
    parser.add_argument(
        "--covariances",
        nargs="+",
        default=["entity", "entity_time"],
        choices=["entity", "entity_time"],
        help="Clustered covariance estimators.",
    )
    return parser.parse_args()


def main() -> None:
    diagnostics = run(parse_args())
    print(json.dumps(diagnostics, indent=2))


if __name__ == "__main__":
    main()
