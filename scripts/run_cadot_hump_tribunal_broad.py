#!/usr/bin/env python3
"""Run the Cadot mechanism tribunal on the full cadot_broad_156 sample.

The broad runner uses every observed export country-year in 2000-2024. It does
not require a balanced panel. Product-dependent work uses the harmonized
HS1992-family product export file and excludes 999999 before aggregation.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import duckdb

import run_cadot_hump_tribunal as legacy
import run_country_size_effect as cse
import run_ppp_hump_regressions as ppp
import trade_concentration_pipeline as tcp
from concentration_metrics import active_gini, active_top_share
from trade_concentration_pipeline import sample_processed_dir, sample_results_dir


ROOT = Path(__file__).resolve().parents[1]
COUNTRY_SAMPLE = "cadot_broad_156"
FLOW = "Exports"
PRIMARY_EPISODE_METRIC = "product_theil"
MAIN_HORIZON = 5
PRODY_BENCHMARK_SAMPLE = "world_broad"
PRIMARY_PRODY_SPEC = "world_broad_full_level"


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clean_scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if math.isfinite(float(value)) else None
    if pd.isna(value):
        return None
    return value


def load_controls(start_year: int, end_year: int) -> pd.DataFrame:
    controls = ppp.load_controls_with_ppp(
        COUNTRY_SAMPLE,
        start_year,
        end_year,
        refresh_ppp=False,
        prefer_future_growth_controls=False,
    ).copy()
    controls[legacy.INCOME_ALIAS_COL] = controls[ppp.PPP_LOG_COL]
    controls[legacy.INCOME_ALIAS_SQ_COL] = controls[legacy.INCOME_ALIAS_COL] ** 2
    legacy.validate_unique(controls, ["reporter_code", "year"], "broad controls")
    return controls


def build_main_panel(
    products: pd.DataFrame,
    controls: pd.DataFrame,
    selected: pd.DataFrame,
) -> pd.DataFrame:
    universe_count = int(products["cmd_code"].nunique())
    grouped = products.groupby(["reporter_code", "year", "cmd_code"], as_index=False, observed=True)["trade_value"].sum()

    def theil_active(values: pd.Series) -> float:
        x = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
        x = x[np.isfinite(x) & (x > 0)]
        shares = x / x.sum()
        return float(np.sum(shares * np.log(len(shares) * shares)))

    def theil_fixed(values: pd.Series) -> float:
        x = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
        x = x[np.isfinite(x) & (x > 0)]
        shares = x / x.sum()
        return float(np.sum(shares * np.log(universe_count * shares)))

    def hhi(values: pd.Series) -> float:
        x = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
        x = x[np.isfinite(x) & (x > 0)]
        shares = x / x.sum()
        return float(np.sum(shares**2))

    panel = (
        grouped.groupby(["reporter_code", "year"], observed=True)["trade_value"]
        .agg(
            total_trade_value="sum",
            product_active_count=lambda x: int((x > 0).sum()),
            product_gini=active_gini,
            product_theil_active=theil_active,
            product_theil=theil_fixed,
            product_hhi=hhi,
            product_top_1pct_share=lambda x: active_top_share(x, pct=0.01),
        )
        .reset_index()
    )
    panel["product_universe_count"] = universe_count
    panel = panel.merge(selected, on="reporter_code", how="left", validate="many_to_one")
    panel = panel.merge(
        controls.drop(columns=["country", "iso3"], errors="ignore"),
        on=["reporter_code", "year"],
        how="left",
        validate="one_to_one",
    )
    panel["log_active_product_count"] = np.log(panel["product_active_count"].where(panel["product_active_count"] > 0))
    legacy.validate_unique(panel, ["reporter_code", "year"], "broad country-year panel")
    return panel.sort_values(["reporter_code", "year"]).reset_index(drop=True)


def load_product_exports(start_year: int, end_year: int) -> pd.DataFrame:
    path = (
        sample_processed_dir(COUNTRY_SAMPLE)
        / "world_relative_product_gini_harmonized_hs6_family_cadot_broad_156_product_exports.parquet"
    )
    products = pd.read_parquet(path)
    products["reporter_code"] = pd.to_numeric(products["reporter_code"], errors="coerce").astype("Int64")
    products["year"] = pd.to_numeric(products["year"], errors="coerce").astype("Int64")
    products["trade_value"] = pd.to_numeric(products["trade_value"], errors="coerce")
    products["cmd_code"] = products["product_id"].astype(str).str.extract(r"(\d{6})$", expand=False)
    products = products.dropna(subset=["reporter_code", "year", "trade_value", "cmd_code"]).copy()
    products["reporter_code"] = products["reporter_code"].astype(int)
    products["year"] = products["year"].astype(int)
    products = products[products["year"].between(start_year, end_year)].copy()
    before = len(products)
    products = products[
        products["trade_value"].gt(0) & ~products["cmd_code"].isin(legacy.EXCLUDED_HS6_CODES)
    ].copy()
    products.attrs["excluded_999999_rows"] = int(before - len(products))
    products["hs2"] = products["cmd_code"].str[:2]
    products["hs4_id"] = "HS1992-HS4:" + products["cmd_code"].str[:4]
    products["section16"] = products["hs2"].isin(legacy.SECTION_16_HS2)
    return products[["reporter_code", "year", "cmd_code", "hs2", "hs4_id", "section16", "trade_value"]]


def build_world_broad_harmonized_product_exports(start_year: int, end_year: int) -> pd.DataFrame:
    processed = sample_processed_dir(PRODY_BENCHMARK_SAMPLE)
    output = processed / "cadot_prody_harmonized_country_product_exports.parquet"
    if output.exists():
        cached = pd.read_parquet(output)
        required = {"reporter_code", "year", "product_id", "trade_value"}
        if required.issubset(cached.columns):
            return cached[cached["year"].between(start_year, end_year)].copy()
    partial_dir = (
        processed
        / "checkpoints"
        / "world_relative_product_gini_file_aggregates"
        / "product_exports"
    )
    partials = sorted(partial_dir.glob("*.parquet"))
    if not partials:
        raise FileNotFoundError(f"No world-broad product-export partials found under {partial_dir}")
    tcp.load_lt_hgl_hs1992_conversion_weights()
    mapping = str(tcp.LT_HGL_NORMALIZED_WEIGHTS_PATH).replace("'", "''")
    glob_path = str(partial_dir / "*.parquet").replace("'", "''")
    output.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect() as con:
        missing = con.execute(
            f"""
            SELECT COUNT(*), COALESCE(SUM(p.trade_value), 0)
            FROM read_parquet('{glob_path}', union_by_name=true) p
            LEFT JOIN read_parquet('{mapping}') w
              ON COALESCE(NULLIF(UPPER(TRIM(CAST(p.classification_code AS VARCHAR))), ''), 'UNKNOWN')
                 = CAST(w.source_classification_code AS VARCHAR)
             AND LPAD(CAST(p.cmd_code AS VARCHAR), 6, '0')
                 = LPAD(CAST(w.source_cmd_code AS VARCHAR), 6, '0')
            WHERE p.year BETWEEN {int(start_year)} AND {int(end_year)}
              AND p.trade_value > 0
              AND LPAD(CAST(p.cmd_code AS VARCHAR), 6, '0') <> '999999'
              AND w.target_product_id IS NULL
            """
        ).fetchone()
        if missing and int(missing[0]) != 0:
            raise RuntimeError(
                "World-broad LT/HGL conversion has unmapped positive rows: "
                f"rows={int(missing[0]):,}, value={float(missing[1]):,.2f}"
            )
        con.execute(
            f"""
            COPY (
                SELECT
                    CAST(p.reporter_code AS BIGINT) AS reporter_code,
                    CAST(p.year AS BIGINT) AS year,
                    CAST(w.target_product_id AS VARCHAR) AS product_id,
                    SUM(CAST(p.trade_value AS DOUBLE) * CAST(w.weight AS DOUBLE)) AS trade_value
                FROM read_parquet('{glob_path}', union_by_name=true) p
                INNER JOIN read_parquet('{mapping}') w
                  ON COALESCE(NULLIF(UPPER(TRIM(CAST(p.classification_code AS VARCHAR))), ''), 'UNKNOWN')
                     = CAST(w.source_classification_code AS VARCHAR)
                 AND LPAD(CAST(p.cmd_code AS VARCHAR), 6, '0')
                     = LPAD(CAST(w.source_cmd_code AS VARCHAR), 6, '0')
                WHERE p.year BETWEEN {int(start_year)} AND {int(end_year)}
                  AND p.trade_value > 0
                  AND LPAD(CAST(p.cmd_code AS VARCHAR), 6, '0') <> '999999'
                GROUP BY 1, 2, 3
                ORDER BY 1, 2, 3
            ) TO '{str(output).replace("'", "''")}' (FORMAT PARQUET)
            """
        )
    return pd.read_parquet(output)


def load_world_broad_prody_controls(start_year: int, end_year: int) -> pd.DataFrame:
    countries = pd.read_csv(sample_processed_dir(PRODY_BENCHMARK_SAMPLE) / "comtrade_country_panel.csv")
    income = ppp.load_or_fetch_ppp_controls(PRODY_BENCHMARK_SAMPLE, start_year, end_year, refresh=False)
    controls = countries.merge(income, on="iso3", how="left", validate="one_to_many")
    controls[ppp.PPP_VALUE_COL] = pd.to_numeric(controls[ppp.PPP_VALUE_COL], errors="coerce")
    controls[ppp.PPP_LOG_COL] = np.where(
        controls[ppp.PPP_VALUE_COL] > 0,
        np.log(controls[ppp.PPP_VALUE_COL]),
        np.nan,
    )
    legacy.validate_unique(controls, ["reporter_code", "year"], "world-broad PRODY controls")
    return controls


def build_prody_bridge(
    world_products: pd.DataFrame,
    controls: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    products = world_products.copy()
    products["product_id"] = "HS1992-HS4:" + products["product_id"].astype(str).str[-6:].str[:4]
    hs4 = (
        products.groupby(["reporter_code", "year", "product_id"], as_index=False, observed=True)["trade_value"]
        .sum()
    )
    work = hs4.merge(
        controls[["reporter_code", "year", ppp.PPP_VALUE_COL, ppp.PPP_LOG_COL]],
        on=["reporter_code", "year"],
        how="inner",
        validate="many_to_one",
    ).dropna(subset=[ppp.PPP_VALUE_COL, ppp.PPP_LOG_COL])
    totals = (
        work.groupby(["reporter_code", "year"], as_index=False, observed=True)["trade_value"]
        .sum()
        .rename(columns={"trade_value": "country_total_exports"})
    )
    work = work.merge(totals, on=["reporter_code", "year"], validate="many_to_one")
    work["country_product_export_share"] = work["trade_value"] / work["country_total_exports"]
    work["weighted_income_level"] = work["country_product_export_share"] * work[ppp.PPP_VALUE_COL]
    work["weighted_log_income"] = work["country_product_export_share"] * work[ppp.PPP_LOG_COL]
    product_year = (
        work.groupby(["year", "product_id"], as_index=False, observed=True)
        .agg(
            prody_share_sum=("country_product_export_share", "sum"),
            prody_weighted_income_sum=("weighted_income_level", "sum"),
            prody_weighted_log_income_sum=("weighted_log_income", "sum"),
            prody_exporter_count=("reporter_code", "nunique"),
        )
    )
    product_year["prody_income_level_full"] = (
        product_year["prody_weighted_income_sum"] / product_year["prody_share_sum"]
    )
    product_year["prody_log_income_full"] = (
        product_year["prody_weighted_log_income_sum"] / product_year["prody_share_sum"]
    )
    out = work.merge(product_year, on=["year", "product_id"], validate="many_to_one")
    out["loo_share_sum"] = out["prody_share_sum"] - out["country_product_export_share"]
    out["prody_income_level_loo"] = (
        out["prody_weighted_income_sum"] - out["weighted_income_level"]
    ) / out["loo_share_sum"]
    out["prody_log_income_loo"] = (
        out["prody_weighted_log_income_sum"] - out["weighted_log_income"]
    ) / out["loo_share_sum"]
    insufficient = (out["loo_share_sum"] <= 0) | (out["prody_exporter_count"] < legacy.PRODY_MIN_EXPORTERS)
    out.loc[insufficient, ["prody_income_level_loo", "prody_log_income_loo"]] = np.nan
    return product_year, out[
        [
            "reporter_code",
            "year",
            "product_id",
            "country_product_export_share",
            ppp.PPP_VALUE_COL,
            ppp.PPP_LOG_COL,
            "prody_income_level_full",
            "prody_log_income_full",
            "prody_income_level_loo",
            "prody_log_income_loo",
            "prody_exporter_count",
        ]
    ].copy()


def attach_prody_bridge_to_windows(
    windows: pd.DataFrame,
    prody_country: pd.DataFrame,
    threshold_info: dict[str, Any],
    controls: pd.DataFrame,
) -> pd.DataFrame:
    base = prody_country.rename(columns={"year": "base_year"})
    out = windows.merge(
        base,
        on=["reporter_code", "base_year", "product_id"],
        how="left",
        validate="many_to_one",
    )
    income = controls[["reporter_code", "year", ppp.PPP_VALUE_COL]].rename(
        columns={"year": "base_year", ppp.PPP_VALUE_COL: "base_income_pc"}
    )
    out = out.merge(income, on=["reporter_code", "base_year"], how="left", validate="many_to_one")
    out["mismatch_world_broad_full_level"] = np.log(
        out["base_income_pc"] / out["prody_income_level_full"]
    )
    out["mismatch_world_broad_loo_level"] = np.log(
        out["base_income_pc"] / out["prody_income_level_loo"]
    )
    out["mismatch_world_broad_loo_log"] = (
        out["base_log_income_pc"] - out["prody_log_income_loo"]
    )
    out["mismatch_log_income_minus_prody"] = out["mismatch_world_broad_full_level"]
    out["prody_log_income_pc_loo"] = np.log(out["prody_income_level_full"])
    out["prody_log_gni_pc_loo"] = out["prody_log_income_pc_loo"]
    threshold = float(threshold_info["rich_side_log_threshold_used"])
    out["rich_side_ct"] = out["base_log_income_pc"].ge(threshold).astype(int)
    out["exit_next_window"] = out["product_channel"].eq("dying_product").astype(int)
    out["entry_next_window"] = out["product_channel"].eq("new_product").astype(int)
    out["mismatch_x_rich_side"] = out["mismatch_log_income_minus_prody"] * out["rich_side_ct"]
    return out


def run_prody_bridge_models(windows: pd.DataFrame) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for spec, mismatch_col in [
        ("world_broad_full_level", "mismatch_world_broad_full_level"),
        ("world_broad_loo_level", "mismatch_world_broad_loo_level"),
        ("world_broad_loo_log", "mismatch_world_broad_loo_log"),
    ]:
        work = windows.copy()
        work["mismatch_log_income_minus_prody"] = work[mismatch_col]
        work["mismatch_x_rich_side"] = work[mismatch_col] * work["rich_side_ct"]
        model = legacy.fixed_effect_exit_regression(work)
        model["prody_spec"] = spec
        model["mismatch_definition"] = mismatch_col
        model["primary_spec"] = spec == PRIMARY_PRODY_SPEC
        rows.append(model)
    return pd.concat(rows, ignore_index=True)


def build_prody_bridge_diagnostics(windows: pd.DataFrame, models: pd.DataFrame) -> pd.DataFrame:
    specs = {
        "world_broad_full_level": "mismatch_world_broad_full_level",
        "world_broad_loo_level": "mismatch_world_broad_loo_level",
        "world_broad_loo_log": "mismatch_world_broad_loo_log",
    }
    base_col = specs[PRIMARY_PRODY_SPEC]
    sample = windows[windows["product_channel"].isin(["continuing_product", "dying_product"])].copy()
    rows: list[dict[str, Any]] = []
    for spec, col in specs.items():
        pair = sample[[base_col, col]].copy()
        pair.columns = ["primary_mismatch", "comparison_mismatch"]
        pair = pair.dropna()
        base_decile = pd.qcut(pair["primary_mismatch"], 10, labels=False, duplicates="drop")
        spec_decile = pd.qcut(pair["comparison_mismatch"], 10, labels=False, duplicates="drop")
        base_top = base_decile.max()
        spec_top = spec_decile.max()
        interaction = models[(models["prody_spec"].eq(spec)) & models["term"].eq("mismatch_x_rich_side")]
        rows.append(
            {
                "prody_spec": spec,
                "primary_spec": spec == PRIMARY_PRODY_SPEC,
                "matched_country_product_windows": int(len(pair)),
                "spearman_mismatch_correlation_with_primary": float(
                    pair.corr(method="spearman").iloc[0, 1]
                ),
                "old_cone_classification_change_share": float(
                    (pair["primary_mismatch"].gt(0) != pair["comparison_mismatch"].gt(0)).mean()
                ),
                "bottom_decile_overlap_share": float(((base_decile == 0) & (spec_decile == 0)).sum() / max((base_decile == 0).sum(), 1)),
                "top_decile_overlap_share": float(
                    ((base_decile == base_top) & (spec_decile == spec_top)).sum()
                    / max((base_decile == base_top).sum(), 1)
                ),
                "exit_interaction_coefficient": float(interaction["coef"].iloc[0]) if not interaction.empty else np.nan,
                "exit_interaction_std_error": float(interaction["std_error"].iloc[0]) if not interaction.empty else np.nan,
                "exit_interaction_raw_p_value": float(interaction["p_value"].iloc[0]) if not interaction.empty else np.nan,
            }
        )
    return pd.DataFrame(rows)


def build_product_year_prody_rank_bridge(product_year: pd.DataFrame) -> pd.DataFrame:
    work = product_year[
        ["year", "product_id", "prody_income_level_full", "prody_log_income_full"]
    ].dropna().copy()
    work["prody_geometric_income_full"] = np.exp(work["prody_log_income_full"])
    level_decile = work.groupby("year", observed=True)["prody_income_level_full"].transform(
        lambda x: pd.qcut(x, 10, labels=False, duplicates="drop")
    )
    log_decile = work.groupby("year", observed=True)["prody_geometric_income_full"].transform(
        lambda x: pd.qcut(x, 10, labels=False, duplicates="drop")
    )
    return pd.DataFrame(
        [
            {
                "comparison": "full_level_arithmetic_vs_full_log_geometric_prody",
                "product_year_rows": int(len(work)),
                "spearman_rank_correlation": float(
                    work[["prody_income_level_full", "prody_geometric_income_full"]]
                    .corr(method="spearman")
                    .iloc[0, 1]
                ),
                "bottom_decile_overlap_share": float(
                    ((level_decile == 0) & (log_decile == 0)).sum()
                    / max((level_decile == 0).sum(), 1)
                ),
                "top_decile_overlap_share": float(
                    (
                        (level_decile == level_decile.groupby(work["year"]).transform("max"))
                        & (log_decile == log_decile.groupby(work["year"]).transform("max"))
                    ).sum()
                    / max(
                        (
                            level_decile
                            == level_decile.groupby(work["year"]).transform("max")
                        ).sum(),
                        1,
                    )
                ),
            }
        ]
    )


def build_variant_panel(products: pd.DataFrame, controls: pd.DataFrame) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []

    def summarize(frame: pd.DataFrame, item: str, variant: str) -> pd.DataFrame:
        grouped = frame.groupby(["reporter_code", "year", item], as_index=False, observed=True)["trade_value"].sum()
        out = (
            grouped.groupby(["reporter_code", "year"], observed=True)["trade_value"]
            .agg(
                product_gini=active_gini,
                product_active_count=lambda x: int((x > 0).sum()),
                product_top_1pct_share=lambda x: active_top_share(x, pct=0.01),
                total_trade_value="sum",
            )
            .reset_index()
        )
        out["mechanical_variant"] = variant
        return out

    rows.append(summarize(products, "cmd_code", "harmonized_hs6"))
    rows.append(summarize(products.loc[~products["section16"]], "cmd_code", "harmonized_hs6_excluding_section16"))
    rows.append(summarize(products, "hs4_id", "harmonized_hs4"))
    rows.append(summarize(products, "hs2", "harmonized_hs2"))
    section = (
        products.assign(section16_value=np.where(products["section16"], products["trade_value"], 0.0))
        .groupby(["reporter_code", "year"], as_index=False, observed=True)
        .agg(
            section16_value=("section16_value", "sum"),
            total_value=("trade_value", "sum"),
            section16_lines=("section16", "sum"),
            total_lines=("cmd_code", "nunique"),
        )
    )
    section["section16_export_share"] = section["section16_value"] / section["total_value"]
    section["section16_line_share"] = section["section16_lines"] / section["total_lines"]
    out = pd.concat(rows, ignore_index=True)
    out = out.merge(section, on=["reporter_code", "year"], how="left", validate="many_to_one")
    out = out.merge(
        controls[
            [
                "reporter_code",
                "year",
                ppp.PPP_VALUE_COL,
                legacy.INCOME_ALIAS_COL,
                legacy.INCOME_ALIAS_SQ_COL,
                "log_population",
                "oil_export_share",
            ]
        ],
        on=["reporter_code", "year"],
        how="left",
        validate="many_to_one",
    )
    return out


def load_commodity_panel(start_year: int, end_year: int) -> pd.DataFrame:
    path = sample_results_dir(COUNTRY_SAMPLE) / "three_metric_tables" / "exercise_06_exclusion_metrics.parquet"
    panel = pd.read_parquet(path)
    panel = panel[
        panel["flow"].eq(FLOW)
        & panel["dimension"].eq("product")
        & panel["variant"].isin(["baseline", "full_exclusion"])
        & panel["year"].between(start_year, end_year)
    ].copy()
    wide = panel.pivot_table(
        index=["reporter_code", "year"],
        columns="variant",
        values=["gini", "trade_share_removed"],
        aggfunc="first",
    )
    wide.columns = [f"{metric}_{variant}" for metric, variant in wide.columns]
    wide = wide.reset_index()
    wide["commodity_gini_delta"] = wide["gini_baseline"] - wide["gini_full_exclusion"]
    wide["commodity_trade_share_removed"] = wide["trade_share_removed_full_exclusion"]
    legacy.validate_unique(wide, ["reporter_code", "year"], "broad commodity panel")
    return wide


def load_hs2_benchmark(start_year: int, end_year: int) -> pd.DataFrame:
    path = sample_results_dir(COUNTRY_SAMPLE) / "three_metric_tables" / "exercise_10_random_benchmarks.parquet"
    panel = pd.read_parquet(path)
    panel = panel[
        panel["flow"].eq(FLOW)
        & panel["benchmark_null"].eq("hs2_preserving_within_sector_random_allocation")
        & panel["year"].between(start_year, end_year)
    ].copy()
    keep = [
        "reporter_code",
        "year",
        "actual_minus_sim_median_gini",
        "actual_gini_percentile",
        "actual_minus_sim_median_theil",
        "actual_theil_active_percentile",
    ]
    out = panel[keep].copy()
    legacy.validate_unique(out, ["reporter_code", "year"], "broad HS2 benchmark")
    return out


def run_hump_models(panel: pd.DataFrame) -> pd.DataFrame:
    outcomes = [
        ("product_gini", "product_gini"),
        ("product_theil", "product_theil_fixed_universe"),
        ("product_hhi", "product_hhi"),
        ("log_active_product_count", "log_active_product_count"),
        ("product_top_1pct_share", "top_product_1pct_share"),
    ]
    results: list[cse.ModelResult] = []
    for outcome, metric in outcomes:
        results.append(
            cse.run_ols_model(
                panel,
                outcome,
                [
                    legacy.INCOME_ALIAS_COL,
                    legacy.INCOME_ALIAS_SQ_COL,
                    "log_population",
                    "oil_export_share",
                ],
                ["year"],
                "quadratic_controls_year_fe_country_cluster",
                "cadot_broad_156_available_country_years",
                FLOW,
                "product",
                metric,
                cluster_col="reporter_code",
            )
        )
    return legacy.add_turning_points(cse.model_results_to_frame(results))


def choose_rich_side_threshold(models: pd.DataFrame, panel: pd.DataFrame) -> dict[str, Any]:
    income = pd.to_numeric(panel[legacy.INCOME_ALIAS_COL], errors="coerce").dropna()
    p05 = float(income.quantile(0.05))
    p75 = float(income.quantile(0.75))
    p95 = float(income.quantile(0.95))
    preferred = models[
        models["metric"].eq("product_theil_fixed_universe")
        & models["model_label"].eq("quadratic_controls_year_fe_country_cluster")
    ]
    estimates = preferred["turning_point_log_income_pc"].dropna()
    turning = float(estimates.iloc[0]) if not estimates.empty else np.nan
    inside = bool(math.isfinite(turning) and p05 <= turning <= p95)
    threshold = turning if inside else p75
    return {
        "turning_point_log_income_pc": turning if math.isfinite(turning) else None,
        "turning_point_ppp_constant_2021_intl_usd": math.exp(turning) if math.isfinite(turning) else None,
        "turning_point_inside_5_95pct_sample_support": inside,
        "sample_log_income_pc_p05": p05,
        "sample_log_income_pc_p75": p75,
        "sample_log_income_pc_p95": p95,
        "rich_side_source": "estimated_product_theil_turning_point" if inside else "sample_income_p75_fallback",
        "rich_side_log_threshold_used": threshold,
        "rich_side_ppp_constant_2021_intl_usd_used": math.exp(threshold),
        "income_indicator": ppp.PPP_INDICATOR,
    }


def build_transition_summary(windows: pd.DataFrame) -> pd.DataFrame:
    work = windows[windows["horizon"].eq(MAIN_HORIZON)].copy()
    grouped = (
        work.groupby(["reporter_code", "base_year", "future_year", "product_channel"], observed=True)
        .agg(
            positive_expansion_2024_usd=("positive_expansion_2024_usd", "sum"),
            contraction_2024_usd=("contraction_2024_usd", "sum"),
            net_contribution_2024_usd=("net_contribution_2024_usd", "sum"),
            product_count=("product_id", "nunique"),
        )
        .reset_index()
    )
    totals = (
        grouped.groupby(["reporter_code", "base_year", "future_year"], as_index=False)
        .agg(
            total_positive_expansion_2024_usd=("positive_expansion_2024_usd", "sum"),
            total_contraction_2024_usd=("contraction_2024_usd", "sum"),
            total_abs_net_2024_usd=("net_contribution_2024_usd", lambda x: float(np.abs(x).sum())),
        )
    )
    grouped = grouped.merge(totals, on=["reporter_code", "base_year", "future_year"], validate="many_to_one")
    grouped["positive_expansion_share"] = (
        grouped["positive_expansion_2024_usd"] / grouped["total_positive_expansion_2024_usd"].replace(0, np.nan)
    )
    grouped["contraction_share"] = (
        grouped["contraction_2024_usd"] / grouped["total_contraction_2024_usd"].replace(0, np.nan)
    )
    grouped["net_growth_share"] = (
        grouped["net_contribution_2024_usd"] / grouped["total_abs_net_2024_usd"].replace(0, np.nan)
    )
    return grouped


def build_episode_scorecard(
    panel: pd.DataFrame,
    transitions: pd.DataFrame,
    commodity: pd.DataFrame,
    variants: pd.DataFrame,
    windows: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    metrics = panel[
        [
            "country",
            "iso3",
            "reporter_code",
            "year",
            "product_gini",
            "product_theil",
            "product_hhi",
            "product_active_count",
            "product_top_1pct_share",
            "oil_export_share",
        ]
    ].copy()
    base = metrics.add_prefix("base_").rename(columns={"base_reporter_code": "reporter_code"})
    future = metrics.add_prefix("future_").rename(columns={"future_reporter_code": "reporter_code"})
    base = base.rename(columns={"base_year": "base_year"})
    future = future.rename(columns={"future_year": "future_year"})
    pivot = transitions.pivot_table(
        index=["reporter_code", "base_year", "future_year"],
        columns="product_channel",
        values=["positive_expansion_share", "contraction_share", "net_growth_share", "product_count"],
        aggfunc="first",
    )
    pivot.columns = [f"{channel}_{metric}" for metric, channel in pivot.columns]
    episodes = pivot.reset_index().merge(base, on=["reporter_code", "base_year"], how="inner", validate="many_to_one")
    episodes = episodes.merge(future, on=["reporter_code", "future_year"], how="inner", validate="many_to_one")
    episodes["country"] = episodes["base_country"]
    episodes["iso3"] = episodes["base_iso3"]
    for metric in ["product_gini", "product_theil", "product_hhi", "product_active_count", "product_top_1pct_share"]:
        episodes[f"delta_{metric}"] = episodes[f"future_{metric}"] - episodes[f"base_{metric}"]
    episodes["reconcentration_episode"] = episodes[f"delta_{PRIMARY_EPISODE_METRIC}"].gt(0)

    episodes = episodes.merge(
        commodity[["reporter_code", "year", "commodity_gini_delta", "commodity_trade_share_removed"]].rename(
            columns={"year": "base_year"}
        ),
        on=["reporter_code", "base_year"],
        how="left",
        validate="many_to_one",
    )
    vwide = variants.pivot_table(
        index=["reporter_code", "year"],
        columns="mechanical_variant",
        values="product_gini",
        aggfunc="first",
    ).reset_index()
    vwide["hs_design_gini_delta_section16"] = (
        vwide["harmonized_hs6"] - vwide["harmonized_hs6_excluding_section16"]
    )
    section = variants[variants["mechanical_variant"].eq("harmonized_hs6")][
        ["reporter_code", "year", "section16_export_share"]
    ]
    vwide = vwide.merge(section, on=["reporter_code", "year"], validate="one_to_one")
    episodes = episodes.merge(vwide.rename(columns={"year": "base_year"}), on=["reporter_code", "base_year"], how="left")

    old = windows.dropna(subset=["mismatch_log_income_minus_prody"]).copy()
    old_summary = (
        old.groupby(["reporter_code", "base_year"], as_index=False)
        .agg(
            dying_median_mismatch=(
                "mismatch_log_income_minus_prody",
                lambda x: float(np.nanmedian(x[old.loc[x.index, "product_channel"].eq("dying_product")]))
                if old.loc[x.index, "product_channel"].eq("dying_product").any()
                else np.nan,
            ),
            continuing_median_mismatch=(
                "mismatch_log_income_minus_prody",
                lambda x: float(np.nanmedian(x[old.loc[x.index, "product_channel"].eq("continuing_product")]))
                if old.loc[x.index, "product_channel"].eq("continuing_product").any()
                else np.nan,
            ),
            rich_side_ct=("rich_side_ct", "max"),
        )
    )
    old_summary["old_cone_mismatch_gap"] = (
        old_summary["dying_median_mismatch"] - old_summary["continuing_median_mismatch"]
    )
    episodes = episodes.merge(old_summary, on=["reporter_code", "base_year"], how="left", validate="many_to_one")
    episodes["commodity_spike"] = (
        episodes["commodity_trade_share_removed"].fillna(0).ge(0.20)
        | episodes["base_oil_export_share"].fillna(0).ge(0.25)
        | episodes["commodity_gini_delta"].fillna(0).ge(0.05)
    )
    episodes["section16_hs_design_sensitive"] = (
        episodes["hs_design_gini_delta_section16"].abs().fillna(0).ge(0.03)
        | episodes["section16_export_share"].fillna(0).ge(0.30)
    )
    episodes["old_cone_pruning"] = (
        episodes["rich_side_ct"].fillna(0).eq(1)
        & episodes["old_cone_mismatch_gap"].fillna(0).gt(0)
        & episodes.get("dying_product_contraction_share", pd.Series(0, index=episodes.index)).fillna(0).gt(0.05)
    )
    episodes["continuing_product_superstar_scaling"] = (
        episodes.get("continuing_product_positive_expansion_share", pd.Series(0, index=episodes.index)).fillna(0).ge(0.75)
        & episodes["delta_product_top_1pct_share"].fillna(0).gt(0)
    )
    flags = [
        "commodity_spike",
        "section16_hs_design_sensitive",
        "old_cone_pruning",
        "continuing_product_superstar_scaling",
    ]
    episodes["broad_unexplained_reconcentration"] = episodes["reconcentration_episode"] & ~episodes[flags].any(axis=1)
    recon = episodes[episodes["reconcentration_episode"]]
    summary = pd.DataFrame(
        [
            {
                "mechanism": flag,
                "reconcentration_episodes": len(recon),
                "flagged_episodes": int(recon[flag].sum()),
                "flagged_share": float(recon[flag].mean()) if len(recon) else np.nan,
            }
            for flag in [*flags, "broad_unexplained_reconcentration"]
        ]
    )
    return episodes, summary


def plot_summary(summary: pd.DataFrame, output: Path) -> None:
    labels = {
        "commodity_spike": "Commodity exposure",
        "section16_hs_design_sensitive": "Machinery/electronics sensitivity",
        "old_cone_pruning": "Old-cone pruning",
        "continuing_product_superstar_scaling": "Continuing-product scaling",
        "broad_unexplained_reconcentration": "Unexplained by flags",
    }
    work = summary.copy()
    work["label"] = work["mechanism"].map(labels)
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    ax.barh(work["label"], work["flagged_share"], color="#315b7d")
    ax.set_xlim(0, 1)
    ax.set_xlabel("Share of five-year Product Theil reconcentration episodes")
    ax.set_title("What accompanies export reconcentration across the broad 156 sample?")
    for y, value in enumerate(work["flagged_share"]):
        ax.text(min(float(value) + 0.012, 0.96), y, f"{value:.0%}", va="center")
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.grid(axis="x", alpha=0.2)
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def write_memo(
    path: Path,
    diagnostics: dict[str, Any],
    summary: pd.DataFrame,
    old_models: pd.DataFrame,
    prody_bridge: pd.DataFrame,
    prody_rank_bridge: pd.DataFrame,
) -> None:
    threshold = diagnostics["turning_point"]
    old = old_models[
        old_models["term"].eq("mismatch_x_rich_side")
        & old_models["prody_spec"].eq(PRIMARY_PRODY_SPEC)
    ]
    old_text = "The old-cone interaction could not be estimated."
    if not old.empty:
        row = old.iloc[0]
        old_text = (
            f"The old-cone mismatch × rich-side coefficient is **{row['coef']:.4f}** "
            f"(clustered SE {row['std_error']:.4f}, **raw p={row['p_value']:.4g}**; "
            f"{int(row['clusters'])} reporter clusters)."
        )
    text = [
        "# Cadot Mechanism Tribunal — Broad 156",
        "",
        f"Created: {diagnostics['created_at_utc']}",
        "",
        "## Scope",
        "",
        f"The updated tribunal uses all {diagnostics['selected_reporters']} selected reporters and "
        f"{diagnostics['observed_reporters']} reporters with at least one observed export year. "
        f"It contains {diagnostics['country_year_rows']:,} observed country-years over "
        f"{diagnostics['start_year']}-{diagnostics['end_year']}; it is intentionally unbalanced.",
        f"The controlled income-shape regressions retain {diagnostics['controlled_hump_reporters']} reporters "
        "with complete PPP, population, and oil-share controls. The mechanism episode panel itself retains all 156.",
        "",
        "The primary episode definition is an increase in fixed-universe Product Theil over five years. "
        "This measure rises both when exports become more unequal across active products and when the "
        "inactive-product margin expands, making it closer to Cadot's diversification question than the "
        "earlier world-relative Gini-only episode rule.",
        "",
        "## Mechanism scorecard",
        "",
        summary.round(4).to_markdown(index=False),
        "",
        "Flags overlap and are descriptive triage categories, so their shares do not sum to 100%.",
        "",
        "## Old-cone test",
        "",
        old_text,
        "",
        "The primary product-sophistication object is standard full-sample PRODY: exporter basket "
        "shares are normalized across the 181-reporter `world_broad` benchmark and applied to GDP per "
        "capita in levels. The regression uses the log income ratio "
        "`log(country GDPpc / product PRODY)` for scale comparability.",
        "",
        "### PRODY construction bridge",
        "",
        prody_bridge.round(4).to_markdown(index=False),
        "",
        "At the product-year level, arithmetic level-income PRODY and geometric log-income PRODY "
        f"have Spearman rank correlation {prody_rank_bridge['spearman_rank_correlation'].iloc[0]:.3f}; "
        f"their bottom- and top-decile overlaps are "
        f"{prody_rank_bridge['bottom_decile_overlap_share'].iloc[0]:.1%} and "
        f"{prody_rank_bridge['top_decile_overlap_share'].iloc[0]:.1%}.",
        "",
        f"The rich-side split is `{threshold['rich_side_source']}` at approximately "
        f"${threshold['rich_side_ppp_constant_2021_intl_usd_used']:,.0f} in constant-2021 PPP dollars. "
        "The prior $25,000 cutoff was removed because it came from a different PPP vintage and was not "
        "unit-comparable.",
        "",
        "## Interpretation",
        "",
        "This expansion answers the sample question: the mechanism tribunal is now a broad-156 exercise, "
        "not a 55-country balanced-panel exercise. It still does not establish a causal effect of income. "
        "The mechanism flags identify empirical patterns that accompany reconcentration and the old-cone "
        "regression tests one specific implication; neither is a causal decomposition.",
    ]
    path.write_text("\n".join(text) + "\n", encoding="utf-8")


def run(start_year: int = 2000, end_year: int = 2024, horizon: int = MAIN_HORIZON) -> None:
    if horizon != MAIN_HORIZON:
        raise RuntimeError("The broad tribunal currently supports the five-year horizon only.")
    result_base = sample_results_dir(COUNTRY_SAMPLE)
    table_dir = result_base / "cadot_hump_tribunal_tables"
    figure_dir = result_base / "cadot_hump_tribunal_figures"
    processed_dir = sample_processed_dir(COUNTRY_SAMPLE)
    table_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)

    selected = pd.read_csv(processed_dir / "comtrade_country_panel.csv")
    if selected["reporter_code"].nunique() != 156:
        raise RuntimeError("cadot_broad_156 country panel does not contain exactly 156 reporters.")
    products = load_product_exports(start_year, end_year)
    excluded_999999 = int(products.attrs.get("excluded_999999_rows", 0))
    controls = load_controls(start_year, end_year)
    panel = build_main_panel(products, controls, selected)
    variants = build_variant_panel(products, controls)
    commodity = load_commodity_panel(start_year, end_year)
    benchmark = load_hs2_benchmark(start_year, end_year)
    models = run_hump_models(panel)
    turning = choose_rich_side_threshold(models, panel)

    hs4 = legacy.build_hs4_country_year(products)
    world_products = build_world_broad_harmonized_product_exports(start_year, end_year)
    world_prody_controls = load_world_broad_prody_controls(start_year, end_year)
    prody_product_year, prody_country = build_prody_bridge(world_products, world_prody_controls)
    windows = legacy.build_hs4_exit_windows(
        hs4,
        controls,
        legacy.ACTIVE_THRESHOLD_USD_2024,
        start_year,
        end_year,
        horizon,
    )
    windows = attach_prody_bridge_to_windows(windows, prody_country, turning, controls)
    old_models = run_prody_bridge_models(windows)
    prody_bridge_diagnostics = build_prody_bridge_diagnostics(windows, old_models)
    prody_rank_bridge = build_product_year_prody_rank_bridge(prody_product_year)
    old_summary, old_deciles = legacy.summarize_old_cone(windows)
    transitions = build_transition_summary(windows)
    episodes, mechanism_summary = build_episode_scorecard(panel, transitions, commodity, variants, windows)

    baseline_variant = variants[variants["mechanical_variant"].eq("harmonized_hs6")][
        ["reporter_code", "year", "product_gini", "total_trade_value", "product_active_count"]
    ]
    lineage_check = panel.merge(
        baseline_variant,
        on=["reporter_code", "year"],
        suffixes=("_panel", "_variant"),
        validate="one_to_one",
    )
    transition_expansion_sums = transitions.groupby(
        ["reporter_code", "base_year", "future_year"]
    )["positive_expansion_share"].sum(min_count=1)
    transition_contraction_sums = transitions.groupby(
        ["reporter_code", "base_year", "future_year"]
    )["contraction_share"].sum(min_count=1)
    validation = pd.DataFrame(
        [
            {"check": "selected_reporters_equal_156", "value": selected["reporter_code"].nunique(), "status": "pass"},
            {"check": "observed_reporters_equal_156", "value": panel["reporter_code"].nunique(), "status": "pass"},
            {
                "check": "unique_country_year_keys",
                "value": int(panel.duplicated(["reporter_code", "year"]).sum()),
                "status": "pass" if not panel.duplicated(["reporter_code", "year"]).any() else "fail",
            },
            {
                "check": "unique_episode_keys",
                "value": int(episodes.duplicated(["reporter_code", "base_year", "future_year"]).sum()),
                "status": "pass"
                if not episodes.duplicated(["reporter_code", "base_year", "future_year"]).any()
                else "fail",
            },
            {
                "check": "max_abs_gini_internal_lineage_difference",
                "value": float(
                    (lineage_check["product_gini_panel"] - lineage_check["product_gini_variant"]).abs().max()
                ),
                "status": "pass",
            },
            {
                "check": "max_abs_total_internal_lineage_difference",
                "value": float(
                    (
                        lineage_check["total_trade_value_panel"]
                        - lineage_check["total_trade_value_variant"]
                    ).abs().max()
                ),
                "status": "pass",
            },
            {
                "check": "max_transition_positive_share_sum_error",
                "value": float((transition_expansion_sums.dropna() - 1).abs().max()),
                "status": "pass",
            },
            {
                "check": "max_transition_contraction_share_sum_error",
                "value": float((transition_contraction_sums.dropna() - 1).abs().max()),
                "status": "pass",
            },
            {
                "check": "reconcentration_indicator_matches_positive_theil_change",
                "value": int(
                    (
                        episodes["reconcentration_episode"]
                        != episodes["delta_product_theil"].gt(0)
                    ).sum()
                ),
                "status": "pass",
            },
            {
                "check": "legacy_fixed_25000_threshold_removed",
                "value": int("fixed_rich_side_ct" in windows.columns),
                "status": "pass" if "fixed_rich_side_ct" not in windows.columns else "fail",
            },
            {
                "check": "primary_prody_is_world_broad_full_level",
                "value": int(PRIMARY_PRODY_SPEC == "world_broad_full_level"),
                "status": "pass" if PRIMARY_PRODY_SPEC == "world_broad_full_level" else "fail",
            },
            {
                "check": "world_broad_prody_reporters_with_income",
                "value": int(
                    world_prody_controls.loc[
                        world_prody_controls[ppp.PPP_VALUE_COL].notna(),
                        "reporter_code",
                    ].nunique()
                ),
                "status": "pass",
            },
        ]
    )
    if validation["status"].ne("pass").any():
        raise RuntimeError(f"Broad tribunal validation failed:\n{validation.to_string(index=False)}")

    coverage = selected.merge(
        panel.groupby("reporter_code", as_index=False).agg(
            observed_country_years=("year", "nunique"),
            first_observed_year=("year", "min"),
            last_observed_year=("year", "max"),
        ),
        on="reporter_code",
        how="left",
        validate="one_to_one",
    )
    coverage["included_in_country_year_panel"] = coverage["observed_country_years"].fillna(0).gt(0)
    diagnostics = {
        "created_at_utc": now_utc(),
        "country_sample": COUNTRY_SAMPLE,
        "selected_reporters": int(selected["reporter_code"].nunique()),
        "observed_reporters": int(panel["reporter_code"].nunique()),
        "country_year_rows": int(len(panel)),
        "start_year": start_year,
        "end_year": end_year,
        "balanced_panel_required": False,
        "primary_episode_metric": PRIMARY_EPISODE_METRIC,
        "five_year_episode_rows": int(len(episodes)),
        "reconcentration_episode_count": int(episodes["reconcentration_episode"].sum()),
        "reporters_in_episode_scorecard": int(episodes["reporter_code"].nunique()),
        "excluded_999999_rows_before_product_aggregation": excluded_999999,
        "excluded_999999_note": (
            "The harmonized product input was already generated with 999999 excluded; "
            "the tribunal rechecks the code and found no additional rows to remove."
        ),
        "turning_point": turning,
        "old_cone_window_rows": int(len(windows)),
        "old_cone_reporters": int(windows["reporter_code"].nunique()),
        "old_cone_regression_clusters": int(old_models["clusters"].max()),
        "primary_prody_spec": PRIMARY_PRODY_SPEC,
        "prody_benchmark_sample": PRODY_BENCHMARK_SAMPLE,
        "prody_benchmark_selected_reporters": int(
            pd.read_csv(
                sample_processed_dir(PRODY_BENCHMARK_SAMPLE) / "comtrade_country_panel.csv"
            )["reporter_code"].nunique()
        ),
        "prody_benchmark_reporters_with_any_income": int(
            world_prody_controls.loc[
                world_prody_controls[ppp.PPP_VALUE_COL].notna(),
                "reporter_code",
            ].nunique()
        ),
        "prody_product_year_rows": int(len(prody_product_year)),
        "prody_country_product_year_rows": int(len(prody_country)),
        "controlled_hump_reporters": int(models["clusters"].max()),
        "product_universe_count": int(panel["product_universe_count"].iloc[0]),
        "country_year_metrics_source": (
            "Recomputed from world_relative_product_gini_harmonized_hs6_family_"
            "cadot_broad_156_product_exports.parquet for internal lineage consistency."
        ),
        "upstream_headline_panel_use": (
            "Not used by the tribunal because a lineage audit found nonzero vintage differences "
            "for a minority of country-years."
        ),
        "product_id_mode": "LT/HGL harmonized HS1992 family; HS4 derived from harmonized HS1992 code",
    }

    panel.to_csv(table_dir / "cadot_hump_country_year_panel.csv", index=False)
    coverage.to_csv(table_dir / "cadot_hump_sample_diagnostics.csv", index=False)
    models.to_csv(table_dir / "cadot_hump_models.csv", index=False)
    variants.to_csv(table_dir / "mechanical_variant_country_year_panel.csv", index=False)
    commodity.to_csv(table_dir / "commodity_mechanism_panel.csv", index=False)
    benchmark.to_csv(table_dir / "hs2_preserving_benchmark_panel.csv", index=False)
    transitions.to_csv(table_dir / "exercise12_hs4_transition_channels.csv", index=False)
    prody_product_year.to_parquet(
        processed_dir / "cadot_hump_hs4_world_broad_full_level_prody.parquet",
        index=False,
    )
    prody_country.to_parquet(
        processed_dir / "cadot_hump_hs4_world_broad_prody_bridge.parquet",
        index=False,
    )
    windows.to_parquet(processed_dir / "cadot_hump_old_cone_exit_windows.parquet", index=False)
    old_models.to_csv(table_dir / "old_cone_exit_models.csv", index=False)
    prody_bridge_diagnostics.to_csv(table_dir / "prody_bridge_diagnostics.csv", index=False)
    prody_rank_bridge.to_csv(table_dir / "prody_product_year_rank_bridge.csv", index=False)
    old_summary.to_csv(table_dir / "old_cone_channel_summary.csv", index=False)
    old_deciles.to_csv(table_dir / "old_cone_exit_by_mismatch_decile.csv", index=False)
    episodes.to_csv(table_dir / "reconcentration_episode_scorecard.csv", index=False)
    mechanism_summary.to_csv(table_dir / "mechanism_scorecard_summary.csv", index=False)
    validation.to_csv(table_dir / "validation_checks.csv", index=False)
    (table_dir / "cadot_hump_diagnostics.json").write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True, default=clean_scalar) + "\n",
        encoding="utf-8",
    )
    (result_base / "run_manifest_cadot_hump_tribunal.json").write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True, default=clean_scalar) + "\n",
        encoding="utf-8",
    )
    plot_summary(mechanism_summary, figure_dir / "mechanism_scorecard.png")
    legacy.plot_old_cone(old_deciles, figure_dir / "old_cone_exit_plot.png")
    write_memo(
        result_base / "cadot_hump_tribunal.md",
        diagnostics,
        mechanism_summary,
        old_models,
        prody_bridge_diagnostics,
        prody_rank_bridge,
    )
    print(json.dumps(diagnostics, indent=2, default=clean_scalar))


if __name__ == "__main__":
    run()
