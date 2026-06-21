#!/usr/bin/env python3
"""Validate alternate HS4 WITS tariff diagnostics against AVEEstimated.

This compares an alternate WITS TRAINS datatype, such as `reported`, with the
existing AVEEstimated HS4 tariff build. It does not run regressions.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_trade_deal_hs4_tariff_diagnostics as hs4diag  # noqa: E402

COUNTRY_SAMPLE = "rd2_countries"
PROCESSED_DIR = ROOT / "data" / "processed" / "samples" / COUNTRY_SAMPLE
RESULTS_DIR = ROOT / "results" / "samples" / COUNTRY_SAMPLE / "trade_deal_market_access"


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


def tariff_path(datatype: str) -> Path:
    return PROCESSED_DIR / f"trade_deal_wits_hs4_tariffs_{datatype_slug(datatype)}.parquet"


def coverage_path(datatype: str) -> Path:
    return PROCESSED_DIR / f"trade_deal_hs4_tariff_coverage_by_exporter_year{datatype_suffix(datatype)}.csv"


def overlap_cells_path(alternate: str) -> Path:
    return PROCESSED_DIR / f"trade_deal_hs4_tariff_overlap_cells_{datatype_slug(alternate)}_vs_aveestimated.csv"


def coverage_comparison_path(alternate: str) -> Path:
    return PROCESSED_DIR / f"trade_deal_hs4_tariff_coverage_comparison_{datatype_slug(alternate)}_vs_aveestimated.csv"


def manifest_path(alternate: str) -> Path:
    return PROCESSED_DIR / f"trade_deal_hs4_tariff_overlap_validation_{datatype_slug(alternate)}_vs_aveestimated.json"


def markdown_path(alternate: str) -> Path:
    return RESULTS_DIR / f"hs4_tariff_overlap_validation_{datatype_slug(alternate)}_vs_aveestimated.md"


def read_tariffs(datatype: str) -> tuple[pd.DataFrame, str]:
    path = tariff_path(datatype)
    if not path.exists():
        raise FileNotFoundError(f"Missing tariff file: {relative_path(path)}")
    df = pd.read_parquet(path)
    rate_col = f"tariff_{datatype_slug(datatype)}"
    if rate_col not in df.columns:
        if "tariff_rate_hs4" in df.columns:
            rate_col = "tariff_rate_hs4"
        elif "tariff_aveestimated" in df.columns:
            rate_col = "tariff_aveestimated"
        else:
            raise ValueError(f"No tariff rate column found in {relative_path(path)}")
    keys = ["tariff_reporter_code", "year", "harmonized_hs4"]
    duplicate_keys = int(df.duplicated(keys).sum())
    if duplicate_keys:
        raise ValueError(f"{relative_path(path)} has duplicate tariff reporter-year-HS4 keys: {duplicate_keys}")
    out = df[keys + [rate_col]].copy()
    out["tariff_reporter_code"] = out["tariff_reporter_code"].astype(str).str.zfill(3)
    out["year"] = pd.to_numeric(out["year"], errors="coerce").astype("Int64")
    out[rate_col] = pd.to_numeric(out[rate_col], errors="coerce")
    out = out.dropna(subset=[rate_col])
    out = out.rename(columns={rate_col: f"tariff_{datatype_slug(datatype)}"})
    return out, f"tariff_{datatype_slug(datatype)}"


def read_coverage(datatype: str) -> pd.DataFrame:
    path = coverage_path(datatype)
    if not path.exists():
        raise FileNotFoundError(f"Missing coverage file: {relative_path(path)}")
    df = pd.read_csv(path)
    keys = ["iso3", "reporter_code", "year"]
    duplicate_keys = int(df.duplicated(keys).sum())
    if duplicate_keys:
        raise ValueError(f"{relative_path(path)} has duplicate country-year coverage keys: {duplicate_keys}")
    return df


def finite_float(value: Any) -> float | None:
    if pd.isna(value):
        return None
    return float(value)


def threshold_counts(df: pd.DataFrame, coverage_col: str) -> dict[str, int]:
    values = pd.to_numeric(df[coverage_col], errors="coerce")
    return {
        "rows": int(len(df)),
        "pass_070": int((values >= 0.70).sum()),
        "pass_075": int((values >= 0.75).sum()),
        "pass_080": int((values >= 0.80).sum()),
        "pass_090": int((values >= 0.90).sum()),
        "pass_095": int((values >= 0.95).sum()),
    }


def build_markdown(summary: dict[str, Any]) -> str:
    alt = summary["alternate_datatype"]
    tariff = summary["tariff_overlap"]
    coverage = summary["coverage_comparison"]
    diff = tariff["difference_reported_minus_aveestimated"]
    lines = [
        f"# HS4 Tariff Overlap Validation: {alt} vs AVEEstimated",
        "",
        f"Created UTC: `{summary['created_at_utc']}`",
        "",
        "## Verdict",
        "",
        "- This is diagnostics-only output. It validates source overlap and coverage; it does not authorize regression tables by itself.",
        "- Tariffs are destination/importer-side WITS TRAINS MFN/world rates collapsed to harmonized HS4.",
        "- Units are tariff percentage points.",
        "",
        "## Tariff Cell Overlap",
        "",
        f"- AVEEstimated HS4 tariff cells: `{tariff['aveestimated_cells']}`.",
        f"- {alt} HS4 tariff cells: `{tariff['alternate_cells']}`.",
        f"- Overlapping reporter-year-HS4 cells: `{tariff['overlap_cells']}`.",
        f"- Overlap share of AVEEstimated cells: `{tariff['overlap_share_of_aveestimated']}`.",
        f"- Overlap share of {alt} cells: `{tariff['overlap_share_of_alternate']}`.",
        f"- Pearson correlation on overlap: `{diff['pearson_corr']}`.",
        f"- Spearman correlation on overlap: `{diff['spearman_corr']}`.",
        f"- Mean absolute difference: `{diff['mean_abs']}`.",
        f"- Median absolute difference: `{diff['median_abs']}`.",
        f"- 90th percentile absolute difference: `{diff['p90_abs']}`.",
        "",
        "## Exporter-Year Coverage",
        "",
        f"- AVEEstimated rows passing 0.80: `{coverage['aveestimated_counts']['pass_080']}` / `{coverage['aveestimated_counts']['rows']}`.",
        f"- {alt} rows passing 0.80: `{coverage['alternate_counts']['pass_080']}` / `{coverage['alternate_counts']['rows']}`.",
        f"- Rows newly passing 0.80 under {alt}: `{coverage['newly_pass_080_alternate_only']}`.",
        f"- Rows passing 0.80 under AVEEstimated only: `{coverage['pass_080_aveestimated_only']}`.",
        f"- Countries with zero 0.80-pass rows under {alt}: `{coverage['alternate_zero_pass_country_count']}`.",
        "",
        "## Outputs",
        "",
        f"- Overlap cell file: `{summary['outputs']['overlap_cells']}`.",
        f"- Coverage comparison file: `{summary['outputs']['coverage_comparison']}`.",
        "",
        "## Use Rule",
        "",
        "- Use the alternate datatype only if the overlap differences are substantively acceptable and the coverage gain changes the sample in a transparent way.",
        "- If the alternate datatype improves coverage but differs materially from AVEEstimated, report it as robustness rather than replacing the primary WITS-AVE sample.",
    ]
    return "\n".join(lines) + "\n"


def run(args: argparse.Namespace) -> dict[str, Any]:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    alternate = args.alternate_datatype
    ave, ave_col = read_tariffs("AVEEstimated")
    alt, alt_col = read_tariffs(alternate)
    keys = ["tariff_reporter_code", "year", "harmonized_hs4"]
    merged = ave.merge(alt, on=keys, how="inner", validate="one_to_one")
    if merged.empty:
        raise ValueError("No overlapping reporter-year-HS4 tariff cells between AVEEstimated and alternate datatype.")
    merged["diff_alternate_minus_aveestimated"] = merged[alt_col] - merged[ave_col]
    merged["abs_diff"] = merged["diff_alternate_minus_aveestimated"].abs()
    merged.to_csv(overlap_cells_path(alternate), index=False)

    ave_cov = read_coverage("AVEEstimated").rename(
        columns={
            "tariff_weight_coverage_i_t": "coverage_aveestimated",
            "market_access_tariff_avg_i_t": "market_access_tariff_avg_aveestimated",
        }
    )
    alt_cov = read_coverage(alternate).rename(
        columns={
            "tariff_weight_coverage_i_t": f"coverage_{datatype_slug(alternate)}",
            "market_access_tariff_avg_i_t": f"market_access_tariff_avg_{datatype_slug(alternate)}",
        }
    )
    cov_keys = ["country", "iso3", "reporter_code", "year"]
    coverage_compare = ave_cov[cov_keys + ["coverage_aveestimated", "market_access_tariff_avg_aveestimated"]].merge(
        alt_cov[
            cov_keys
            + [
                f"coverage_{datatype_slug(alternate)}",
                f"market_access_tariff_avg_{datatype_slug(alternate)}",
            ]
        ],
        on=cov_keys,
        how="outer",
        validate="one_to_one",
    )
    alt_coverage_col = f"coverage_{datatype_slug(alternate)}"
    coverage_compare["pass_080_aveestimated"] = coverage_compare["coverage_aveestimated"] >= 0.80
    coverage_compare[f"pass_080_{datatype_slug(alternate)}"] = coverage_compare[alt_coverage_col] >= 0.80
    coverage_compare["coverage_gain_alternate_minus_aveestimated"] = (
        coverage_compare[alt_coverage_col] - coverage_compare["coverage_aveestimated"]
    )
    coverage_compare.to_csv(coverage_comparison_path(alternate), index=False)

    alt_country_pass = coverage_compare.groupby("iso3")[f"pass_080_{datatype_slug(alternate)}"].sum()
    zero_pass_alt = alt_country_pass[alt_country_pass == 0]

    diff = merged["diff_alternate_minus_aveestimated"]
    abs_diff = merged["abs_diff"]
    summary = {
        "created_at_utc": now_utc(),
        "script": relative_path(Path(__file__)),
        "country_sample": COUNTRY_SAMPLE,
        "alternate_datatype": alternate,
        "tariff_overlap": {
            "aveestimated_cells": int(len(ave)),
            "alternate_cells": int(len(alt)),
            "overlap_cells": int(len(merged)),
            "overlap_share_of_aveestimated": finite_float(len(merged) / len(ave)) if len(ave) else None,
            "overlap_share_of_alternate": finite_float(len(merged) / len(alt)) if len(alt) else None,
            "reporter_years_overlap": int(merged[["tariff_reporter_code", "year"]].drop_duplicates().shape[0]),
            "reporters_overlap": int(merged["tariff_reporter_code"].nunique()),
            "years_overlap_min": int(merged["year"].min()),
            "years_overlap_max": int(merged["year"].max()),
            "difference_reported_minus_aveestimated": {
                "mean": finite_float(diff.mean()),
                "median": finite_float(diff.median()),
                "mean_abs": finite_float(abs_diff.mean()),
                "median_abs": finite_float(abs_diff.median()),
                "p90_abs": finite_float(abs_diff.quantile(0.90)),
                "p95_abs": finite_float(abs_diff.quantile(0.95)),
                "pearson_corr": finite_float(merged[[ave_col, alt_col]].corr(method="pearson").iloc[0, 1]),
                "spearman_corr": finite_float(merged[[ave_col, alt_col]].corr(method="spearman").iloc[0, 1]),
            },
        },
        "coverage_comparison": {
            "rows": int(len(coverage_compare)),
            "aveestimated_counts": threshold_counts(coverage_compare, "coverage_aveestimated"),
            "alternate_counts": threshold_counts(coverage_compare, alt_coverage_col),
            "newly_pass_080_alternate_only": int(
                ((~coverage_compare["pass_080_aveestimated"]) & coverage_compare[f"pass_080_{datatype_slug(alternate)}"]).sum()
            ),
            "pass_080_aveestimated_only": int(
                (coverage_compare["pass_080_aveestimated"] & (~coverage_compare[f"pass_080_{datatype_slug(alternate)}"])).sum()
            ),
            "pass_080_both": int(
                (coverage_compare["pass_080_aveestimated"] & coverage_compare[f"pass_080_{datatype_slug(alternate)}"]).sum()
            ),
            "alternate_zero_pass_country_count": int(len(zero_pass_alt)),
            "alternate_zero_pass_countries": sorted(zero_pass_alt.index.astype(str).tolist()),
            "coverage_gain_mean": finite_float(coverage_compare["coverage_gain_alternate_minus_aveestimated"].mean()),
            "coverage_gain_median": finite_float(
                coverage_compare["coverage_gain_alternate_minus_aveestimated"].median()
            ),
        },
        "outputs": {
            "overlap_cells": relative_path(overlap_cells_path(alternate)),
            "coverage_comparison": relative_path(coverage_comparison_path(alternate)),
            "manifest": relative_path(manifest_path(alternate)),
            "markdown": relative_path(markdown_path(alternate)),
        },
        "regression_policy": "No regression table is trusted until diagnostics and adversarial econometrics review clear.",
    }
    manifest_path(alternate).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path(alternate).write_text(build_markdown(summary), encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alternate-datatype", default="reported", help="Alternate WITS datatype to validate.")
    return parser.parse_args()


def main() -> None:
    summary = run(parse_args())
    print(
        json.dumps(
            {
                "created_at_utc": summary["created_at_utc"],
                "alternate_datatype": summary["alternate_datatype"],
                "tariff_overlap": summary["tariff_overlap"],
                "coverage_comparison": summary["coverage_comparison"],
                "outputs": summary["outputs"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
