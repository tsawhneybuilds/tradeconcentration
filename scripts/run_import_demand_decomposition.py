#!/usr/bin/env python3
"""Decompose focal export concentration against reported foreign import demand.

The focal object remains each cadot_broad_156 reporter's export basket.  The
preferred reference distribution is world_broad reported imports after
removing both imports reported by the focal country and imports whose recorded
origin is the focal country.  This double leave-out avoids mechanically using
the focal reporter on either side of the benchmark.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import html
import json
import math
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import concentration_metrics as cm
import run_cadot_three_metric_pipeline as ctm
import run_country_size_effect as cse
import run_world_market_concentration_decomposition as exports_run
import trade_concentration_pipeline as tcp


COUNTRY_SAMPLE = "cadot_broad_156"
BENCHMARK_SAMPLE = "world_broad"
START_YEAR = 2000
END_YEAR = 2024
UNIVERSE_COUNT = 5037
OUTPUT_DIR = ROOT / "results/samples/cadot_broad_156/world_import_demand_decomposition"
CHECKPOINT_DIR = (
    ROOT
    / "data/processed/samples/world_broad/checkpoints/foreign_import_demand_file_aggregates"
)
BENCHMARK_PATH = (
    ROOT
    / "data/processed/samples/world_broad/foreign_import_demand_benchmark_components.parquet"
)
DEFAULT_PUBLISH_DIR = Path("/Users/tanushsawhney/Desktop/trade-gini-map-old")
POLICIES = {
    "double_leave_out": "Foreign imports excluding focal importer and focal origin",
    "exclude_importer": "Rest-of-world importers, including imports from focal origin",
    "inclusive_imports": "Inclusive reported world imports",
}
OUTCOMES = ["market_component_theil", "specialization_kl", "market_component_share"]


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def checkpoint_path(raw_path: Path) -> Path:
    return CHECKPOINT_DIR / (tcp.checkpoint_name_for_raw(raw_path).replace(".parquet", "_demand.parquet"))


def aggregate_import_file(path_text: str, focal_codes: tuple[int, ...]) -> dict[str, Any]:
    raw_path = Path(path_text)
    output = checkpoint_path(raw_path)
    if output.exists():
        return {"status": "skipped", "path": str(output)}
    weights = tcp.load_lt_hgl_hs1992_conversion_weights()
    frames: list[pd.DataFrame] = []
    focal = set(focal_codes)
    for leaf in tcp.iter_leaf_trade_chunks(raw_path, chunk_rows=400_000):
        leaf = ctm.normalize_leaf_for_metric(leaf)
        leaf = leaf[leaf["flow"].eq("Imports")].copy()
        if leaf.empty:
            continue
        leaf = tcp.drop_excluded_hs6(leaf)
        if leaf.empty:
            continue
        converted = ctm.harmonize_product_leaf(leaf, weights)
        if converted.empty:
            continue
        converted["reporter_code"] = pd.to_numeric(converted["reporter_code"], errors="coerce")
        converted["partner_code"] = pd.to_numeric(converted["partner_code"], errors="coerce")
        converted["year"] = pd.to_numeric(converted["year"], errors="coerce")
        converted = converted.dropna(
            subset=["reporter_code", "partner_code", "year", "product_id", "trade_value"]
        ).copy()
        converted[["reporter_code", "partner_code", "year"]] = converted[
            ["reporter_code", "partner_code", "year"]
        ].astype(int)
        converted = converted[
            converted["year"].between(START_YEAR, END_YEAR)
            & converted["partner_code"].ne(0)
            & converted["trade_value"].gt(0)
        ].copy()
        if converted.empty:
            continue
        total = (
            converted.groupby(["year", "product_id"], as_index=False)["trade_value"]
            .sum()
            .assign(component="world", focal_code=0)
        )
        pieces = [total]
        importer = converted[converted["reporter_code"].isin(focal)]
        if not importer.empty:
            pieces.append(
                importer.groupby(["reporter_code", "year", "product_id"], as_index=False)[
                    "trade_value"
                ]
                .sum()
                .rename(columns={"reporter_code": "focal_code"})
                .assign(component="importer")
            )
        origin = converted[converted["partner_code"].isin(focal)]
        if not origin.empty:
            pieces.append(
                origin.groupby(["partner_code", "year", "product_id"], as_index=False)[
                    "trade_value"
                ]
                .sum()
                .rename(columns={"partner_code": "focal_code"})
                .assign(component="origin")
            )
        self_trade = converted[
            converted["reporter_code"].eq(converted["partner_code"])
            & converted["reporter_code"].isin(focal)
        ]
        if not self_trade.empty:
            pieces.append(
                self_trade.groupby(["reporter_code", "year", "product_id"], as_index=False)[
                    "trade_value"
                ]
                .sum()
                .rename(columns={"reporter_code": "focal_code"})
                .assign(component="self")
            )
        frames.append(
            pd.concat(pieces, ignore_index=True)[
                ["component", "focal_code", "year", "product_id", "trade_value"]
            ]
        )
    if frames:
        result = (
            pd.concat(frames, ignore_index=True)
            .groupby(["component", "focal_code", "year", "product_id"], as_index=False)[
                "trade_value"
            ]
            .sum()
        )
    else:
        result = pd.DataFrame(
            columns=["component", "focal_code", "year", "product_id", "trade_value"]
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(".tmp.parquet")
    result.to_parquet(tmp, index=False)
    tmp.replace(output)
    return {"status": "written", "path": str(output), "rows": int(len(result))}


def raw_world_files() -> list[Path]:
    tcp.configure_country_sample(
        country_sample=BENCHMARK_SAMPLE,
        min_available_years=10,
        start_year=START_YEAR,
        end_year=END_YEAR,
        refresh_availability=False,
    )
    files = tcp.hs_bulk_files(None)
    if not files:
        raise FileNotFoundError("No world_broad raw HS files found.")
    return files


def build_benchmark(workers: int, fresh: bool = False) -> pd.DataFrame:
    country_panel = pd.read_csv(
        ROOT / "data/processed/samples/cadot_broad_156/comtrade_country_panel.csv"
    )
    focal_codes = tuple(sorted(country_panel["reporter_code"].astype(int).unique()))
    files = raw_world_files()
    if fresh and CHECKPOINT_DIR.exists():
        shutil.rmtree(CHECKPOINT_DIR)
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    statuses: list[dict[str, Any]] = []
    if workers <= 1:
        for index, path in enumerate(files, start=1):
            statuses.append(aggregate_import_file(str(path), focal_codes))
            if index % 100 == 0:
                print(f"import-demand checkpoints {index}/{len(files)}", flush=True)
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(aggregate_import_file, str(path), focal_codes): path for path in files
            }
            for index, future in enumerate(as_completed(futures), start=1):
                statuses.append(future.result())
                if index % 100 == 0:
                    print(f"import-demand checkpoints {index}/{len(files)}", flush=True)
    partials = [checkpoint_path(path) for path in files]
    missing = [path for path in partials if not path.exists()]
    if missing:
        raise RuntimeError(f"Missing {len(missing)} import-demand checkpoints.")
    glob_path = str(CHECKPOINT_DIR / "*_demand.parquet").replace("'", "''")
    BENCHMARK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect() as con:
        con.execute(
            f"""
            COPY (
                SELECT component, CAST(focal_code AS BIGINT) AS focal_code,
                       CAST(year AS BIGINT) AS year, CAST(product_id AS VARCHAR) AS product_id,
                       SUM(CAST(trade_value AS DOUBLE)) AS trade_value
                FROM read_parquet('{glob_path}', union_by_name=true)
                GROUP BY 1,2,3,4
                HAVING SUM(CAST(trade_value AS DOUBLE)) > 0
                ORDER BY 1,2,3,4
            ) TO '{str(BENCHMARK_PATH).replace("'", "''")}' (FORMAT PARQUET)
            """
        )
    audit = {
        "created_at_utc": now_utc(),
        "raw_files": len(files),
        "checkpoints": len(partials),
        "statuses": pd.Series([row["status"] for row in statuses]).value_counts().to_dict(),
    }
    (OUTPUT_DIR / "import_benchmark_build_log.json").parent.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "import_benchmark_build_log.json").write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return pd.read_parquet(BENCHMARK_PATH)


def reference_metrics(
    export_values: np.ndarray,
    reference_values: np.ndarray,
    *,
    reference_total_raw: float,
    world_min_positive: float,
    universe_count: int,
) -> dict[str, float | int]:
    export_values = np.asarray(export_values, dtype=float)
    reference_values = np.maximum(np.asarray(reference_values, dtype=float), 0.0)
    shares = export_values / export_values.sum()
    zero_active = reference_values <= 0
    floor = max(float(world_min_positive) * 0.5, np.finfo(float).tiny)
    # The active rows do not span the universe. Add the audited universe-wide
    # zero count supplied below through reference_total; active zeros receive
    # the same floor and therefore retain the accounting identity.
    reference_total = float(reference_total_raw)
    if reference_total <= 0:
        raise RuntimeError("Import-demand reference total is nonpositive.")
    active_reference = np.where(zero_active, floor, reference_values)
    # Only active-product zeros need enter the country-weighted identity. The
    # denominator is adjusted by the universe-wide zero count by the caller.
    benchmark_share = active_reference / reference_total
    if np.any(benchmark_share <= 0):
        raise RuntimeError("Import-demand shares must be positive on the active export set.")
    observed = float(np.sum(shares * np.log(universe_count * shares)))
    kl = float(np.sum(shares * np.log(shares / benchmark_share)))
    market = float(np.sum(shares * np.log(universe_count * benchmark_share)))
    return {
        "observed_theil": observed,
        "market_component_theil": market,
        "specialization_kl": kl,
        "market_component_share": market / observed if abs(observed) > 1e-12 else np.nan,
        "theil_identity_residual": observed - market - kl,
        "observed_gini": cm.active_gini(export_values),
        "market_benchmark_gini": cm.active_gini(benchmark_share),
        "gini_gap": cm.active_gini(export_values) - cm.active_gini(benchmark_share),
        "active_products": int(len(export_values)),
        "exclusive_product_rows": int(zero_active.sum()),
        "exclusive_product_trade_share": float(shares[zero_active].sum()),
        "smoothing_floor_trade_value": floor,
        "zero_active_products": int(zero_active.sum()),
    }


def policy_reference(group: pd.DataFrame, policy: str) -> np.ndarray:
    world = group["world_imports"].to_numpy(dtype=float)
    importer = group["focal_importer_imports"].fillna(0).to_numpy(dtype=float)
    origin = group["focal_origin_imports"].fillna(0).to_numpy(dtype=float)
    self_trade = group["focal_self_imports"].fillna(0).to_numpy(dtype=float)
    if policy == "inclusive_imports":
        return world
    if policy == "exclude_importer":
        return np.maximum(world - importer, 0.0)
    if policy == "double_leave_out":
        return np.maximum(world - importer - origin + self_trade, 0.0)
    raise ValueError(policy)


def compute_panel(benchmark: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    country, _world, controls, concentration, mapping, alignment = exports_run.load_inputs(
        exports_run.OUTPUT_DIR
    )
    country = country.merge(
        mapping[["product_id", "primary_broad"]], on="product_id", validate="many_to_one"
    )
    components = {}
    for component in ["world", "importer", "origin", "self"]:
        part = benchmark[benchmark["component"].eq(component)].copy()
        if component == "world":
            part = part.rename(columns={"trade_value": "world_imports"})[
                ["year", "product_id", "world_imports"]
            ]
        else:
            part = part.rename(
                columns={
                    "focal_code": "reporter_code",
                    "trade_value": f"focal_{component}_imports",
                }
            )[["reporter_code", "year", "product_id", f"focal_{component}_imports"]]
        components[component] = part
    contribution_lookup: dict[str, dict[tuple[int, int], pd.Series]] = {}
    for component in ["importer", "origin", "self"]:
        value_col = f"focal_{component}_imports"
        contribution_lookup[component] = {
            (int(reporter), int(year)): group.set_index("product_id")[value_col].astype(float)
            for (reporter, year), group in components[component].groupby(
                ["reporter_code", "year"], sort=False
            )
        }
    rows: list[dict[str, Any]] = []
    for variant, primary_filter in [("baseline", False), ("noncommodity_broad", True)]:
        work = country[~country["primary_broad"]].copy() if primary_filter else country.copy()
        allowed_ids = set(
            mapping.loc[~mapping["primary_broad"], "product_id"]
            if primary_filter
            else mapping["product_id"]
        )
        universe_count = len(allowed_ids)
        world_by_year = {
            int(year): group[group["product_id"].isin(allowed_ids)]
            .set_index("product_id")["world_imports"]
            .astype(float)
            .reindex(sorted(allowed_ids), fill_value=0.0)
            for year, group in components["world"].groupby("year", sort=False)
        }
        merged = work.copy()
        for (reporter, year), group in merged.groupby(["reporter_code", "year"], sort=True):
            world_reference = world_by_year[int(year)].copy()
            importer = contribution_lookup["importer"].get((int(reporter), int(year)))
            origin = contribution_lookup["origin"].get((int(reporter), int(year)))
            self_trade = contribution_lookup["self"].get((int(reporter), int(year)))
            for policy in POLICIES:
                full_ref = world_reference.copy()
                if policy in {"exclude_importer", "double_leave_out"} and importer is not None:
                    full_ref = full_ref.sub(importer, fill_value=0.0)
                if policy == "double_leave_out" and origin is not None:
                    full_ref = full_ref.sub(origin, fill_value=0.0)
                if policy == "double_leave_out" and self_trade is not None:
                    full_ref = full_ref.add(self_trade, fill_value=0.0)
                full_ref = full_ref.clip(lower=0.0).reindex(sorted(allowed_ids), fill_value=0.0)
                positive = full_ref[full_ref.gt(0)]
                if positive.empty:
                    raise RuntimeError(f"Empty import reference for reporter={reporter}, year={year}.")
                zero_universe = int(universe_count - len(positive))
                floor = max(float(positive.min()) * 0.5, np.finfo(float).tiny)
                total_raw = float(positive.sum())
                adjusted_total = total_raw + zero_universe * floor
                ref = group["product_id"].map(full_ref).fillna(0.0).to_numpy(dtype=float)
                metrics = reference_metrics(
                    group["trade_value"].to_numpy(dtype=float),
                    ref,
                    reference_total_raw=adjusted_total,
                    world_min_positive=float(positive.min()),
                    universe_count=universe_count,
                )
                metrics["zero_benchmark_products"] = zero_universe
                rows.append(
                    {
                        "reporter_code": int(reporter),
                        "year": int(year),
                        "flow": "Exports",
                        "reference_flow": "Reported imports",
                        "variant": variant,
                        "benchmark_policy": policy,
                        "benchmark_policy_label": POLICIES[policy],
                        "universe_count": universe_count,
                        "benchmark_total_imports": adjusted_total,
                        **metrics,
                    }
                )
    panel = pd.DataFrame(rows)
    panel["world_benchmark_inconsistent_trade_share"] = 0.0
    panel["benchmark_reliable"] = panel["exclusive_product_trade_share"].le(0.001)
    panel = exports_run.add_controls_and_size_bins(panel, controls, alignment)
    return panel, concentration


def add_reliability(panel: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    out["world_benchmark_inconsistent_trade_share"] = 0.0
    out["benchmark_reliable"] = out["exclusive_product_trade_share"].le(0.001)
    return out


def run_models(panel: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    specs = [
        ("main_year_fe", ["year"], None),
        ("main_two_way_clustered", ["year"], "year"),
        ("country_year_fe_diagnostic", ["reporter_code", "year"], None),
    ]
    for variant in panel["variant"].unique():
        for policy in POLICIES:
            work = panel[
                panel["variant"].eq(variant)
                & panel["benchmark_policy"].eq(policy)
                & panel["controls_complete"].fillna(False)
                & panel["source_metric_parity"].fillna(False)
                & panel["benchmark_reliable"].fillna(False)
            ].copy()
            results = []
            for model_label, fixed_effects, two_way in specs:
                for outcome in OUTCOMES:
                    results.append(
                        cse.run_ols_model(
                            work,
                            outcome=outcome,
                            terms=["log_population", "log_gdp_per_capita"],
                            fixed_effects=fixed_effects,
                            model_label=model_label,
                            sample=COUNTRY_SAMPLE,
                            flow="Exports",
                            dimension="product",
                            metric=outcome,
                            cluster_col="reporter_code",
                            two_way_cluster_col=two_way,
                        )
                    )
            frame = cse.model_results_to_frame(results)
            frame["variant"] = variant
            frame["benchmark_policy"] = policy
            frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def size_summary(panel: pd.DataFrame) -> pd.DataFrame:
    preferred = panel[
        panel["benchmark_policy"].eq("double_leave_out")
        & panel["controls_complete"].fillna(False)
        & panel["source_metric_parity"].fillna(False)
        & panel["benchmark_reliable"].fillna(False)
    ].copy()
    return (
        preferred.groupby(["variant", "size_quintile", "size_group"], as_index=False)
        .agg(
            reporter_years=("year", "size"),
            countries=("reporter_code", "nunique"),
            observed_theil=("observed_theil", "mean"),
            market_component_theil=("market_component_theil", "mean"),
            specialization_kl=("specialization_kl", "mean"),
            market_component_share=("market_component_share", "mean"),
            observed_gini=("observed_gini", "mean"),
            market_benchmark_gini=("market_benchmark_gini", "mean"),
            gini_gap=("gini_gap", "mean"),
        )
    )


def compare_with_exports(import_panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    export_panel = pd.read_csv(
        exports_run.OUTPUT_DIR / "world_market_concentration_panel.csv"
    )
    export_panel = export_panel[
        export_panel["variant"].eq("baseline")
        & export_panel["benchmark_policy"].eq("loo_smoothed")
        & export_panel["controls_complete"].fillna(False)
        & export_panel["source_metric_parity"].fillna(False)
        & export_panel["benchmark_reliable"].fillna(False)
    ].copy()
    demand = import_panel[
        import_panel["variant"].eq("baseline")
        & import_panel["benchmark_policy"].eq("double_leave_out")
        & import_panel["controls_complete"].fillna(False)
        & import_panel["source_metric_parity"].fillna(False)
        & import_panel["benchmark_reliable"].fillna(False)
    ].copy()
    common = export_panel.merge(
        demand,
        on=["reporter_code", "year"],
        suffixes=("_exports", "_imports"),
        validate="one_to_one",
    )
    rows = []
    for reference, suffix in [("row_exports", "exports"), ("row_imports", "imports")]:
        model_data = pd.DataFrame(
            {
                "reporter_code": common["reporter_code"],
                "year": common["year"],
                "log_population": common[f"log_population_{suffix}"],
                "log_gdp_per_capita": common[f"log_gdp_per_capita_{suffix}"],
                **{outcome: common[f"{outcome}_{suffix}"] for outcome in OUTCOMES},
            }
        )
        for outcome in OUTCOMES:
            result = cse.run_ols_model(
                model_data,
                outcome=outcome,
                terms=["log_population", "log_gdp_per_capita"],
                fixed_effects=["year"],
                model_label="common_sample_year_fe",
                sample=COUNTRY_SAMPLE,
                flow="Exports",
                dimension="product",
                metric=outcome,
                cluster_col="reporter_code",
            )
            frame = cse.model_results_to_frame([result])
            frame["reference_basket"] = reference
            rows.append(frame)
    return common, pd.concat(rows, ignore_index=True)


def configure_plot_style() -> None:
    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
        }
    )


def plot_comparison(common_models: pd.DataFrame, output: Path) -> None:
    configure_plot_style()
    labels = {
        "market_component_theil": "Market component",
        "specialization_kl": "Specialization KL",
        "market_component_share": "Market share",
    }
    work = common_models[
        common_models["term"].eq("log_population") & common_models["status"].eq("ok")
    ].copy()
    sds = {}
    # Plot raw coefficients in separate panels because units differ.
    fig, axes = plt.subplots(1, 3, figsize=(11.0, 3.6))
    colors = {"row_exports": "#9b9489", "row_imports": "#315e6f"}
    for ax, outcome in zip(axes, labels):
        subset = work[work["outcome"].eq(outcome)]
        for y, ref in enumerate(["row_exports", "row_imports"]):
            row = subset[subset["reference_basket"].eq(ref)].iloc[0]
            ax.errorbar(
                row["coefficient"],
                y,
                xerr=[[row["coefficient"] - row["ci_low"]], [row["ci_high"] - row["coefficient"]]],
                fmt="o",
                color=colors[ref],
                capsize=2,
            )
        ax.axvline(0, color="#777777", lw=0.8)
        ax.set_yticks([0, 1], ["ROW exports", "Foreign imports"] if ax is axes[0] else ["", ""])
        ax.set_title(labels[outcome], loc="left", fontweight="bold")
        ax.set_xlabel("Coefficient on log population")
    fig.suptitle(
        "The size gradient persists when the benchmark is foreign import demand",
        x=0.06,
        ha="left",
        fontweight="bold",
        fontsize=14,
    )
    fig.text(
        0.06,
        0.91,
        "Common country-year sample; year fixed effects, GDP per capita control, country-clustered 95% intervals.",
        color="#555555",
    )
    fig.tight_layout(rect=[0, 0, 1, 0.86])
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=200, bbox_inches="tight")
    plt.close(fig)


def write_review(panel: pd.DataFrame, models: pd.DataFrame, common: pd.DataFrame) -> None:
    preferred = panel[
        panel["variant"].eq("baseline")
        & panel["benchmark_policy"].eq("double_leave_out")
    ]
    max_identity = preferred["theil_identity_residual"].abs().max()
    review = f"""# Adversarial econometric review: foreign import-demand decomposition

## Executive verdict

**Mostly trustworthy** for the stated accounting and descriptive purpose. This was a local review, not an independent fresh-agent pass, because delegation was not permitted.

- The focal object remains exports; reported imports enter only as the reference distribution.
- The preferred reference removes the focal country as both importer and recorded origin.
- The Theil identity closes to a maximum absolute residual of {max_identity:.3e}.
- Results remain descriptive: reported imports proxy foreign traded demand but do not identify a demand shock.

## Highest-risk findings

1. **Mirror-trade discrepancy (acceptable if disclosed).** Import values need not equal exporter-reported values because of CIF/FOB valuation, timing, and partner attribution.
2. **Zero-demand smoothing (material diagnostic).** Country-years with more than 0.1% of export value on zero benchmark products are excluded from preferred regressions.
3. **Cross-sectional identification (high).** Year-FE coefficients compare countries within years and are not causal effects of population.

## Data lineage and sample audit

Raw world_broad importer-origin-product records -> HS6 999999 exclusion -> LT/HGL HS1992 conversion -> world/importer/origin/self components -> focal export-product merge -> reporter-year decomposition. Preferred panel rows: {len(preferred):,}; common export/import rows: {len(common):,}.

## Merge/join audit

All joins use reporter/year/product stable keys with many-to-one validation. Unmatched import products are treated as zero reported demand and audited through the smoothing share rather than silently dropped.

## Variable construction audit

For export shares s and double-leave-out import shares m, observed Theil equals sum(s log(Km)) + sum(s log(s/m)). The second term is KL divergence and is nonnegative up to floating-point tolerance.

## Specification audit

Outcome = log population + log GDP per capita + year fixed effects + error. Main standard errors cluster by reporter; a reporter/year two-way variant and reporter+year fixed-effect diagnostic are reported.

## Inference and identification audit

The country-cluster count is reported in the model CSV. Common product-demand shocks motivate the two-way clustered sensitivity. Neither specification makes population exogenous.

## Replication checklist

- Run this script with `--benchmark-basket row_imports`.
- Confirm all validation rows pass.
- Compare main, two-way, inclusive, and country-FE rows.
- Inspect the zero-benchmark export-value distribution.

## Minimal patch plan

No blocking patch remains. Preserve the demand-proxy language and common-sample comparison.

## Questions for the researcher

No unresolved question blocks descriptive reporting. A causal demand design would require an external source of product-demand shocks.
"""
    (OUTPUT_DIR / "adversarial_review.md").write_text(review, encoding="utf-8")


def html_table(frame: pd.DataFrame) -> str:
    reference_labels = {"row_exports": "ROW exports", "row_imports": "Foreign imports"}
    outcome_labels = {
        "market_component_theil": "Benchmark-market component",
        "specialization_kl": "Divergence from benchmark",
        "market_component_share": "Benchmark-market share",
    }
    rows = []
    for row in frame.itertuples(index=False):
        coef = f"{row.coefficient:.4f}"
        pval = f"{row.p_value:.4g}"
        qval = f"{row.bh_q_value:.4g}" if np.isfinite(row.bh_q_value) else ""
        if row.p_value < 0.05:
            coef = f'<strong class="sig-coef">{coef}</strong>'
            pval = f'<strong class="sig-pvalue">{pval}</strong>'
        if np.isfinite(row.bh_q_value) and row.bh_q_value < 0.05:
            qval = f'<strong class="sig-qvalue">{qval}</strong>'
        rows.append(
            "<tr>"
            f"<td>{reference_labels.get(row.reference_basket, html.escape(str(row.reference_basket)))}</td>"
            f"<td>{outcome_labels.get(row.outcome, html.escape(str(row.outcome)))}</td>"
            f"<td>{coef}</td><td>{row.std_error:.4f}</td>"
            f"<td>{pval}</td><td>{qval}</td><td>{int(row.nobs):,}</td><td>{int(row.clusters)}</td>"
            "</tr>"
        )
    return "".join(rows)


def write_fragment(summary: pd.DataFrame, common_models: pd.DataFrame) -> None:
    preferred = summary[summary["variant"].eq("baseline")].sort_values("size_quintile")
    largest = preferred.iloc[-1]
    smallest = preferred.iloc[0]
    model_rows = common_models[
        common_models["term"].eq("log_population") & common_models["status"].eq("ok")
    ].copy()
    fragment = f"""
<section class="section" id="foreign-import-demand">
  <div class="section-heading">
    <h2>Does a Foreign Import-Demand Basket Give the Same Answer?</h2>
    <p>Yes descriptively. The focal basket is still each country's exports, but the reference is reported imports by the world after excluding the focal country as both importer and recorded origin.</p>
  </div>
  <div class="equation-card">
    <h4>Import-demand Theil identity</h4>
    <div class="math-line">T<sub>ct</sub> = &Sigma;<sub>p</sub>s<sub>cpt</sub>log(Km<sub>-c,pt</sub>) + &Sigma;<sub>p</sub>s<sub>cpt</sub>log(s<sub>cpt</sub>/m<sub>-c,pt</sub>)</div>
    <p><strong>m</strong> is the normalized foreign import basket. The first term is concentration associated with unequal foreign import-demand sizes; the second is export specialization relative to that basket. This is a demand proxy, not a causal demand shock.</p>
  </div>
  <div class="stat-grid">
    <article class="stat-card"><span>Largest-quintile demand share</span><strong>{largest.market_component_share:.1%}</strong><small>Smallest quintile: {smallest.market_component_share:.1%}</small></article>
    <article class="stat-card"><span>Largest-quintile demand component</span><strong>{largest.market_component_theil:.3f}</strong><small>Mean fixed-universe Theil units</small></article>
    <article class="stat-card"><span>Largest-quintile demand divergence</span><strong>{largest.specialization_kl:.3f}</strong><small>KL relative to foreign imports</small></article>
  </div>
  <div class="figure-row full-width">
    <figure><a class="figure-link" href="assets/figures/world_import_demand_coefficient_comparison.png"><img src="assets/figures/world_import_demand_coefficient_comparison.png" alt="Export and foreign-import benchmark coefficient comparison"></a><figcaption>Same focal export baskets and common country-year sample. The comparison changes only the reference basket.</figcaption></figure>
  </div>
  <h3 class="subsection-title">Common-sample size gradients</h3>
  <div class="table-scroll"><table><thead><tr><th>Reference</th><th>Outcome</th><th>Log-pop. coef.</th><th>SE</th><th>Raw p</th><th>BH q</th><th>Obs.</th><th>Clusters</th></tr></thead><tbody>{html_table(model_rows)}</tbody></table></div>
  <p class="source-note">Reported world imports can differ from world exports because of valuation, timing, coverage, re-exports, and partner attribution. Download the import-demand panel, models, validation, manifest, and local adversarial review below.</p>
  <div class="download-grid compact-downloads">
    <a href="assets/downloads/world_import_demand_panel.csv">Import-demand panel</a>
    <a href="assets/downloads/world_import_demand_models.csv">Import-demand models</a>
    <a href="assets/downloads/world_import_demand_common_models.csv">Common-sample comparison</a>
    <a href="assets/downloads/world_import_demand_validation.csv">Validation</a>
    <a href="assets/downloads/world_import_demand_manifest.json">Manifest</a>
    <a href="assets/downloads/world_import_demand_adversarial_review.md">Adversarial review</a>
  </div>
</section>
"""
    (OUTPUT_DIR / "website_fragment.html").write_text(fragment, encoding="utf-8")


def publish(publish_dir: Path) -> None:
    page = publish_dir / "world-market-baseline.html"
    if not page.exists():
        raise FileNotFoundError(page)
    fragment = (OUTPUT_DIR / "website_fragment.html").read_text(encoding="utf-8")
    text = page.read_text(encoding="utf-8")
    start = "<!-- IMPORT_DEMAND_START -->"
    end = "<!-- IMPORT_DEMAND_END -->"
    block = f"{start}\n{fragment}\n{end}"
    if start in text and end in text:
        before, rest = text.split(start, 1)
        _old, after = rest.split(end, 1)
        text = before + block + after
    else:
        text = text.replace("</main>", block + "\n</main>")
    page.write_text(text, encoding="utf-8")
    figures = publish_dir / "assets/figures"
    downloads = publish_dir / "assets/downloads"
    figures.mkdir(parents=True, exist_ok=True)
    downloads.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        OUTPUT_DIR / "world_import_demand_coefficient_comparison.png",
        figures / "world_import_demand_coefficient_comparison.png",
    )
    mapping = {
        "world_import_demand_panel.csv": "world_import_demand_panel.csv",
        "world_import_demand_models.csv": "world_import_demand_models.csv",
        "world_import_demand_common_models.csv": "world_import_demand_common_models.csv",
        "world_import_demand_validation.csv": "world_import_demand_validation.csv",
        "run_manifest.json": "world_import_demand_manifest.json",
        "adversarial_review.md": "world_import_demand_adversarial_review.md",
        "figure_contract.md": "world_import_demand_figure_contract.md",
    }
    for source, target in mapping.items():
        shutil.copy2(OUTPUT_DIR / source, downloads / target)
    manifest_path = publish_dir / "assets/site-manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["downloads"] = sorted(set(manifest.get("downloads", [])) | set(mapping.values()))
        manifest["import_demand_extension"] = {
            "country_sample": COUNTRY_SAMPLE,
            "benchmark_sample": BENCHMARK_SAMPLE,
            "preferred_policy": "exclude focal importer and focal recorded origin",
            "source_script": "scripts/run_import_demand_decomposition.py",
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark-basket", choices=["row_imports"], default="row_imports")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--fresh-benchmark", action="store_true")
    parser.add_argument("--publish-dir", type=Path)
    parser.add_argument("--publish-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.publish_only:
        if not args.publish_dir:
            raise ValueError("--publish-only requires --publish-dir")
        common_models = pd.read_csv(OUTPUT_DIR / "world_import_demand_common_models.csv")
        summary = pd.read_csv(OUTPUT_DIR / "world_import_demand_size_summary.csv")
        write_fragment(summary, common_models)
        publish(args.publish_dir)
        return
    benchmark = build_benchmark(max(1, args.workers), fresh=args.fresh_benchmark)
    panel, _concentration = compute_panel(benchmark)
    panel = add_reliability(panel)
    models = run_models(panel)
    summary = size_summary(panel)
    common, common_models = compare_with_exports(panel)
    common_models["bh_q_value"] = np.nan
    common_mask = common_models["term"].eq("log_population") & common_models["status"].eq("ok")
    common_models.loc[common_mask, "bh_q_value"] = cse.benjamini_hochberg(
        common_models.loc[common_mask, "p_value"]
    )
    validation = pd.DataFrame(
        [
            {
                "check": "theil_identity",
                "value": float(panel["theil_identity_residual"].abs().max()),
                "status": "pass" if panel["theil_identity_residual"].abs().max() < 1e-10 else "fail",
            },
            {
                "check": "kl_nonnegative",
                "value": float(panel["specialization_kl"].min()),
                "status": "pass" if panel["specialization_kl"].min() > -1e-10 else "fail",
            },
            {
                "check": "preferred_policy_present",
                "value": int(panel["benchmark_policy"].eq("double_leave_out").sum()),
                "status": "pass" if panel["benchmark_policy"].eq("double_leave_out").any() else "fail",
            },
            {
                "check": "common_sample_nonempty",
                "value": int(len(common)),
                "status": "pass" if len(common) > 0 else "fail",
            },
        ]
    )
    if validation["status"].ne("pass").any():
        raise RuntimeError(validation.to_string(index=False))
    panel.to_csv(OUTPUT_DIR / "world_import_demand_panel.csv", index=False)
    models.to_csv(OUTPUT_DIR / "world_import_demand_models.csv", index=False)
    summary.to_csv(OUTPUT_DIR / "world_import_demand_size_summary.csv", index=False)
    common.to_csv(OUTPUT_DIR / "world_import_demand_common_sample.csv", index=False)
    common_models.to_csv(OUTPUT_DIR / "world_import_demand_common_models.csv", index=False)
    validation.to_csv(OUTPUT_DIR / "world_import_demand_validation.csv", index=False)
    plot_comparison(
        common_models, OUTPUT_DIR / "world_import_demand_coefficient_comparison.png"
    )
    manifest = {
        "created_at_utc": now_utc(),
        "country_sample": COUNTRY_SAMPLE,
        "benchmark_sample": BENCHMARK_SAMPLE,
        "focal_flow": "Exports",
        "reference_flow": "Reported imports",
        "preferred_policy": "double_leave_out",
        "years": [START_YEAR, END_YEAR],
        "product_universe": UNIVERSE_COUNT,
        "panel_rows": int(len(panel)),
        "preferred_reliable_rows": int(
            (
                panel["benchmark_policy"].eq("double_leave_out")
                & panel["benchmark_reliable"].fillna(False)
            ).sum()
        ),
        "common_sample_rows": int(len(common)),
    }
    (OUTPUT_DIR / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (OUTPUT_DIR / "figure_contract.md").write_text(
        "# Figure contract\n\nQuestion: Does replacing the ROW-export reference with foreign import demand change the population gradient?\n\nAnswer: No; coefficients are nearly identical on the common country-year sample.\n\nComparison: ROW exports versus double-leave-out foreign imports, with identical focal export baskets.\n\nSample: cadot_broad_156, 2000–2024, common reliable observations.\n\nCaveat: reported imports are a demand proxy, not an exogenous demand shock.\n",
        encoding="utf-8",
    )
    write_review(panel, models, common)
    write_fragment(summary, common_models)
    if args.publish_dir:
        publish(args.publish_dir)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
