#!/usr/bin/env python3
"""Compute pairwise product-panel rank and Spearman correlations for Gini, Theil, and HHI."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, rankdata, spearmanr

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_NAME = "cadot_broad_156"
TABLE_DIRNAME = "three_metric_tables"
INPUT_NAME = "metric_headline_product_panel.parquet"
OUTPUT_CSV = "three_metric_rank_spearman_correlations.csv"
OUTPUT_MD = "three_metric_rank_spearman_correlations.md"
PANEL_LABEL = "common_product_headline_panel"
OVERALL_FLOW_LABEL = "All"
METRICS = ("gini", "theil", "hhi")
METRIC_PAIRS = (("gini", "theil"), ("gini", "hhi"), ("theil", "hhi"))
EXPECTED_NOBS = {
    OVERALL_FLOW_LABEL: 7509,
    "Exports": 3753,
    "Imports": 3756,
}
EXPECTED_POOLED_SPEARMAN = {
    ("gini", "theil"): 0.918386226693,
    ("gini", "hhi"): 0.836245300958,
    ("theil", "hhi"): 0.952105402083,
}
TOLERANCE = 1e-12


def results_dir() -> Path:
    return ROOT / "results" / "samples" / SAMPLE_NAME / TABLE_DIRNAME


def input_path() -> Path:
    return results_dir() / INPUT_NAME


def output_csv_path() -> Path:
    return results_dir() / OUTPUT_CSV


def output_md_path() -> Path:
    return results_dir() / OUTPUT_MD


def load_product_panel(path: Path) -> pd.DataFrame:
    panel = pd.read_parquet(path)
    required = {
        "sample_rule",
        "dimension",
        "variant",
        "common_gini_theil_hhi_row",
        "reporter_code",
        "year",
        "flow",
        *METRICS,
    }
    missing = sorted(required.difference(panel.columns))
    if missing:
        raise RuntimeError(f"Input panel missing required columns: {', '.join(missing)}")
    return panel


def filter_product_panel(panel: pd.DataFrame) -> pd.DataFrame:
    out = panel[
        panel["dimension"].eq("product")
        & panel["variant"].eq("baseline")
        & panel["common_gini_theil_hhi_row"].astype(bool)
    ].copy()
    out["year"] = pd.to_numeric(out["year"], errors="raise").astype(int)
    out["reporter_code"] = pd.to_numeric(out["reporter_code"], errors="raise").astype(int)
    return out


def validate_filtered_panel(panel: pd.DataFrame) -> dict[str, int]:
    duplicates = int(panel.duplicated(["reporter_code", "year", "flow"]).sum())
    if duplicates:
        raise RuntimeError(f"Filtered panel has {duplicates} duplicate reporter_code-year-flow rows.")
    missing = panel[list(METRICS)].isna().sum()
    if int(missing.sum()):
        raise RuntimeError(f"Filtered panel has metric missingness: {missing.to_dict()}")
    counts = {OVERALL_FLOW_LABEL: int(len(panel))}
    counts.update({str(flow): int(len(group)) for flow, group in panel.groupby("flow", sort=True)})
    for flow, expected in EXPECTED_NOBS.items():
        observed = counts.get(flow)
        if observed != expected:
            raise RuntimeError(f"Unexpected row count for {flow}: expected {expected}, found {observed}.")
    return counts


def compute_pairwise_correlations(panel: pd.DataFrame) -> pd.DataFrame:
    sample_rules = sorted(panel["sample_rule"].dropna().astype(str).unique().tolist())
    if sample_rules != [SAMPLE_NAME]:
        raise RuntimeError(f"Filtered panel should contain only `{SAMPLE_NAME}` rows; found {sample_rules}.")
    rows: list[dict[str, Any]] = []
    slices: list[tuple[str, pd.DataFrame]] = [(OVERALL_FLOW_LABEL, panel)]
    slices.extend((str(flow), group.copy()) for flow, group in panel.groupby("flow", sort=True))
    for flow, subset in slices:
        nobs = int(len(subset))
        if nobs == 0:
            raise RuntimeError(f"No rows available for slice `{flow}`.")
        for metric_x, metric_y in METRIC_PAIRS:
            x = subset[metric_x].to_numpy(dtype=float)
            y = subset[metric_y].to_numpy(dtype=float)
            spearman_value, spearman_p = spearmanr(x, y)
            rank_x = rankdata(x, method="average")
            rank_y = rankdata(y, method="average")
            rank_value, rank_p = pearsonr(rank_x, rank_y)
            rows.append(
                {
                    "sample_rule": SAMPLE_NAME,
                    "panel": PANEL_LABEL,
                    "flow": flow,
                    "metric_x": metric_x,
                    "metric_y": metric_y,
                    "correlation_type": "spearman_correlation",
                    "correlation_value": float(spearman_value),
                    "p_value": float(spearman_p),
                    "nobs": nobs,
                }
            )
            rows.append(
                {
                    "sample_rule": SAMPLE_NAME,
                    "panel": PANEL_LABEL,
                    "flow": flow,
                    "metric_x": metric_x,
                    "metric_y": metric_y,
                    "correlation_type": "rank_correlation",
                    "correlation_value": float(rank_value),
                    "p_value": float(rank_p),
                    "nobs": nobs,
                }
            )
    return pd.DataFrame(rows)


def validate_results(results: pd.DataFrame) -> None:
    expected_rows = len(EXPECTED_NOBS) * len(METRIC_PAIRS) * 2
    if len(results) != expected_rows:
        raise RuntimeError(f"Expected {expected_rows} correlation rows; found {len(results)}.")
    for flow, expected_nobs in EXPECTED_NOBS.items():
        flow_rows = results[results["flow"].eq(flow)].copy()
        if flow_rows.empty:
            raise RuntimeError(f"Missing correlation rows for flow `{flow}`.")
        observed_nobs = sorted(flow_rows["nobs"].astype(int).unique().tolist())
        if observed_nobs != [expected_nobs]:
            raise RuntimeError(f"Unexpected nobs for flow `{flow}`: expected {expected_nobs}, found {observed_nobs}.")
        for metric_x, metric_y in METRIC_PAIRS:
            subset = flow_rows[flow_rows["metric_x"].eq(metric_x) & flow_rows["metric_y"].eq(metric_y)].copy()
            if len(subset) != 2:
                raise RuntimeError(f"Expected 2 correlation rows for {flow} {metric_x}-{metric_y}; found {len(subset)}.")
            values = {
                row["correlation_type"]: float(row["correlation_value"])
                for row in subset[["correlation_type", "correlation_value"]].to_dict("records")
            }
            difference = abs(values["spearman_correlation"] - values["rank_correlation"])
            if difference > TOLERANCE:
                raise RuntimeError(
                    f"Rank/Spearman mismatch for {flow} {metric_x}-{metric_y}: {difference:.3e} exceeds {TOLERANCE:.1e}."
                )
    pooled = results[
        results["flow"].eq(OVERALL_FLOW_LABEL) & results["correlation_type"].eq("spearman_correlation")
    ].copy()
    for metric_pair, expected in EXPECTED_POOLED_SPEARMAN.items():
        metric_x, metric_y = metric_pair
        match = pooled[pooled["metric_x"].eq(metric_x) & pooled["metric_y"].eq(metric_y)]
        if len(match) != 1:
            raise RuntimeError(f"Missing pooled Spearman row for {metric_x}-{metric_y}.")
        observed = float(match.iloc[0]["correlation_value"])
        if not math.isclose(observed, expected, rel_tol=0.0, abs_tol=1e-9):
            raise RuntimeError(
                f"Unexpected pooled Spearman for {metric_x}-{metric_y}: expected {expected:.12f}, found {observed:.12f}."
            )


def format_corr(value: float) -> str:
    return f"{value:.6f}"


def safe_markdown(frame: pd.DataFrame) -> str:
    table = frame.copy()
    for column in ["spearman_correlation", "rank_correlation"]:
        if column in table.columns:
            table[column] = table[column].map(format_corr)
    return table.to_markdown(index=False)


def build_summary_markdown(counts: dict[str, int], results: pd.DataFrame) -> str:
    pooled = results[results["flow"].eq(OVERALL_FLOW_LABEL)].pivot(
        index=["metric_x", "metric_y"],
        columns="correlation_type",
        values="correlation_value",
    ).reset_index()
    by_flow = results[results["flow"].ne(OVERALL_FLOW_LABEL)].pivot(
        index=["flow", "metric_x", "metric_y"],
        columns="correlation_type",
        values="correlation_value",
    ).reset_index()
    lines = [
        "# Broad-156 Product-Panel Rank and Spearman Correlations",
        "",
        "This note uses the existing `cadot_broad_156` three-metric product panel in",
        f"`{input_path().relative_to(ROOT)}`.",
        "",
        "## Sample and panel",
        "",
        "- Sample: `cadot_broad_156`.",
        "- Panel: common product headline rows with `dimension == \"product\"`, `variant == \"baseline\"`, and `common_gini_theil_hhi_row == True`.",
        "- Unit of observation: reporter-year-flow.",
        f"- Rows: overall `{counts[OVERALL_FLOW_LABEL]}`, exports `{counts['Exports']}`, imports `{counts['Imports']}`.",
        "- Metrics: headline `gini`, headline fixed-universe `theil`, and raw `hhi`.",
        "",
        "## Pooled correlations",
        "",
        safe_markdown(pooled),
        "",
        "## Flow-specific correlations",
        "",
        safe_markdown(by_flow),
        "",
        "## Interpretation",
        "",
        "- Spearman is already a rank correlation.",
        "- The separate `rank_correlation` rows use Pearson correlation on average ranks from the same observations.",
        f"- In this panel they are numerically identical within tolerance `{TOLERANCE:.1e}` for every metric pair and flow slice.",
        "- These are descriptive concordance measures across headline concentration metrics; they are not causal estimates.",
        "",
    ]
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=input_path(),
        help="Path to the metric_headline_product_panel parquet file.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=results_dir(),
        help="Directory where the correlation CSV and markdown note should be written.",
    )
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> dict[str, Path]:
    panel = load_product_panel(args.input)
    filtered = filter_product_panel(panel)
    counts = validate_filtered_panel(filtered)
    correlations = compute_pairwise_correlations(filtered)
    validate_results(correlations)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.output_dir / OUTPUT_CSV
    md_path = args.output_dir / OUTPUT_MD
    correlations.to_csv(csv_path, index=False)
    md_path.write_text(build_summary_markdown(counts, correlations), encoding="utf-8")
    return {"csv": csv_path, "markdown": md_path}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    outputs = run(args)
    print(f"Wrote {outputs['csv']}")
    print(f"Wrote {outputs['markdown']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
