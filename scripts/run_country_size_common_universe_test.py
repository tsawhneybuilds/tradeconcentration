#!/usr/bin/env python3
"""Common-universe post-2001 concentration tests.

This script distinguishes entry from reallocation among already-active products
or partners. It uses rd2 country sample aggregate files by default.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_country_size_effect as cse  # noqa: E402
from trade_concentration_pipeline import COUNTRY_SAMPLE_CHOICES, sample_processed_dir, sample_processed_path, sample_results_dir  # noqa: E402


DEFAULT_START_YEAR = 1989
DEFAULT_POST_START_YEAR = 2002
DEFAULT_END_YEAR = 2024
DIMENSIONS = ("product", "partner")
MODEL_LABEL = "post2001_common_universe_year_fe"
MODEL_LABEL_TWOWAY = "post2001_common_universe_two_way_cluster"
PRODUCT_EXCLUDED_CODE = "999999"


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_dirs(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def import_duckdb():
    try:
        import duckdb
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("Missing dependency 'duckdb'. Run: python3 -m pip install -r requirements.txt") from exc
    return duckdb


def aggregate_glob(country_sample: str) -> Path:
    return sample_processed_dir(country_sample) / "exercise_02_12_file_aggregates" / "*.parquet"


def import_cells_glob(country_sample: str) -> Path:
    return sample_processed_dir(country_sample) / "checkpoints" / "exercise_11_file_aggregates" / "import_cells" / "*.parquet"


def quoted_glob(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def build_common_universe_tables(
    country_sample: str,
    start_year: int,
    post_start_year: int,
    end_year: int,
    workers: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    glob_path = aggregate_glob(country_sample)
    aggregate_dir = glob_path.parent
    if not aggregate_dir.exists() or not list(aggregate_dir.glob("*.parquet")):
        raise FileNotFoundError(f"Missing aggregate files for common-universe test: {aggregate_dir}")
    import_glob_path = import_cells_glob(country_sample)
    import_dir = import_glob_path.parent
    has_import_cells = import_dir.exists() and bool(list(import_dir.glob("*.parquet")))

    duckdb = import_duckdb()
    con = duckdb.connect()
    try:
        con.execute(f"SET threads TO {max(1, workers)}")
        glob_sql = quoted_glob(glob_path)
        con.execute(
            f"""
            CREATE TEMP TABLE export_item_values AS
            SELECT
                CAST(reporter_code AS BIGINT) AS reporter_code,
                CAST(year AS BIGINT) AS year,
                CAST(flow AS VARCHAR) AS flow,
                CAST(dimension AS VARCHAR) AS dimension,
                'default_export_aggregate' AS source_note,
                'Main export item universe' AS source_label,
                TRUE AS source_matches_country_size_panel,
                CASE
                    WHEN CAST(dimension AS VARCHAR) = 'product'
                        THEN LPAD(CAST(cmd_code AS VARCHAR), 6, '0')
                    WHEN CAST(dimension AS VARCHAR) = 'partner'
                        THEN CAST(CAST(partner_code AS BIGINT) AS VARCHAR)
                END AS item_id,
                SUM(CAST(trade_value AS DOUBLE)) AS trade_value
            FROM read_parquet({glob_sql}, union_by_name=true)
            WHERE CAST(year AS BIGINT) BETWEEN {int(start_year)} AND {int(end_year)}
              AND CAST(dimension AS VARCHAR) IN ('product', 'partner')
              AND CAST(trade_value AS DOUBLE) > 0
              AND (
                    CAST(dimension AS VARCHAR) <> 'product'
                    OR LPAD(CAST(cmd_code AS VARCHAR), 6, '0') <> '{PRODUCT_EXCLUDED_CODE}'
                  )
              AND (
                    CAST(dimension AS VARCHAR) <> 'partner'
                    OR CAST(partner_code AS BIGINT) <> 0
                  )
            GROUP BY 1, 2, 3, 4, 5, 6, 7, 8
            """
        )
        if has_import_cells:
            import_glob_sql = quoted_glob(import_glob_path)
            con.execute(
                f"""
                CREATE TEMP TABLE import_product_item_values AS
                SELECT
                    CAST(reporter_code AS BIGINT) AS reporter_code,
                    CAST(year AS BIGINT) AS year,
                    'Imports' AS flow,
                    'product' AS dimension,
                    'exercise11_mapped_import_cells_product' AS source_note,
                    'Mapped import cells: products' AS source_label,
                    FALSE AS source_matches_country_size_panel,
                    LPAD(CAST(cmd_code AS VARCHAR), 6, '0') AS item_id,
                    SUM(CAST(trade_value AS DOUBLE)) AS trade_value
                FROM read_parquet({import_glob_sql}, union_by_name=true)
                WHERE CAST(year AS BIGINT) BETWEEN {int(start_year)} AND {int(end_year)}
                  AND CAST(trade_value AS DOUBLE) > 0
                  AND LPAD(CAST(cmd_code AS VARCHAR), 6, '0') <> '{PRODUCT_EXCLUDED_CODE}'
                GROUP BY 1, 2, 3, 4, 5, 6, 7, 8
                """
            )
            con.execute(
                f"""
                CREATE TEMP TABLE import_partner_item_values AS
                SELECT
                    CAST(reporter_code AS BIGINT) AS reporter_code,
                    CAST(year AS BIGINT) AS year,
                    'Imports' AS flow,
                    'partner' AS dimension,
                    'exercise11_mapped_import_cells_partner_no999999_sensitivity' AS source_note,
                    'Mapped import cells: partners, no-999999 sensitivity' AS source_label,
                    FALSE AS source_matches_country_size_panel,
                    CAST(CAST(partner_code AS BIGINT) AS VARCHAR) AS item_id,
                    SUM(CAST(trade_value AS DOUBLE)) AS trade_value
                FROM read_parquet({import_glob_sql}, union_by_name=true)
                WHERE CAST(year AS BIGINT) BETWEEN {int(start_year)} AND {int(end_year)}
                  AND CAST(trade_value AS DOUBLE) > 0
                  AND CAST(partner_code AS BIGINT) <> 0
                GROUP BY 1, 2, 3, 4, 5, 6, 7, 8
                """
            )
        else:
            con.execute(
                """
                CREATE TEMP TABLE import_product_item_values AS
                SELECT * FROM export_item_values WHERE FALSE
                """
            )
            con.execute(
                """
                CREATE TEMP TABLE import_partner_item_values AS
                SELECT * FROM export_item_values WHERE FALSE
                """
            )
        con.execute(
            """
            CREATE TEMP TABLE item_values AS
            SELECT * FROM export_item_values
            UNION ALL
            SELECT * FROM import_product_item_values
            UNION ALL
            SELECT * FROM import_partner_item_values
            """
        )
        con.execute(
            f"""
            CREATE TEMP TABLE old_universe AS
            SELECT
                reporter_code,
                flow,
                dimension,
                source_note,
                source_label,
                source_matches_country_size_panel,
                item_id,
                SUM(trade_value) AS pre_trade_value,
                COUNT(DISTINCT year) AS pre_active_years
            FROM item_values
            WHERE year < {int(post_start_year)}
            GROUP BY 1, 2, 3, 4, 5, 6, 7
            """
        )
        con.execute(
            f"""
            CREATE TEMP TABLE post_items AS
            SELECT
                p.reporter_code,
                p.year,
                p.flow,
                p.dimension,
                p.source_note,
                p.source_label,
                p.source_matches_country_size_panel,
                p.item_id,
                p.trade_value,
                CASE WHEN o.item_id IS NULL THEN 0 ELSE 1 END AS is_old_item
            FROM item_values p
            LEFT JOIN old_universe o
              ON p.reporter_code = o.reporter_code
             AND p.flow = o.flow
             AND p.dimension = o.dimension
             AND p.source_note = o.source_note
             AND p.item_id = o.item_id
            WHERE p.year >= {int(post_start_year)}
            """
        )
        con.execute(
            """
            CREATE TEMP TABLE old_counts AS
            SELECT
                reporter_code,
                flow,
                dimension,
                source_note,
                source_label,
                source_matches_country_size_panel,
                COUNT(*) AS old_universe_count,
                SUM(pre_trade_value) AS old_universe_pre_trade_value
            FROM old_universe
            GROUP BY 1, 2, 3, 4, 5, 6
            """
        )
        con.execute(
            """
            CREATE TEMP TABLE status_summary AS
            SELECT
                p.reporter_code,
                p.year,
                p.flow,
                p.dimension,
                p.source_note,
                p.source_label,
                p.source_matches_country_size_panel,
                SUM(p.trade_value) AS total_value,
                COUNT(*) AS total_active_count,
                SUM(CASE WHEN p.is_old_item = 1 THEN p.trade_value ELSE 0 END) AS old_value,
                SUM(CASE WHEN p.is_old_item = 0 THEN p.trade_value ELSE 0 END) AS new_value,
                SUM(CASE WHEN p.is_old_item = 1 THEN 1 ELSE 0 END) AS old_active_count,
                SUM(CASE WHEN p.is_old_item = 0 THEN 1 ELSE 0 END) AS new_active_count
            FROM post_items p
            GROUP BY 1, 2, 3, 4, 5, 6, 7
            """
        )
        con.execute(
            """
            CREATE TEMP TABLE all_gini AS
            WITH ranked AS (
                SELECT
                    reporter_code,
                    year,
                    flow,
                    dimension,
                    source_note,
                    source_label,
                    source_matches_country_size_panel,
                    trade_value,
                    ROW_NUMBER() OVER (
                        PARTITION BY reporter_code, year, flow, dimension, source_note
                        ORDER BY trade_value ASC, item_id ASC
                    ) AS asc_rank,
                    COUNT(*) OVER (PARTITION BY reporter_code, year, flow, dimension, source_note) AS n,
                    SUM(trade_value) OVER (PARTITION BY reporter_code, year, flow, dimension, source_note) AS total
                FROM post_items
                WHERE trade_value > 0
            )
            SELECT
                reporter_code,
                year,
                flow,
                dimension,
                source_note,
                source_label,
                source_matches_country_size_panel,
                ((2.0 * SUM(asc_rank * trade_value)) / (MAX(n) * MAX(total))) - ((MAX(n) + 1.0) / MAX(n)) AS total_gini
            FROM ranked
            GROUP BY 1, 2, 3, 4, 5, 6, 7
            """
        )
        con.execute(
            """
            CREATE TEMP TABLE old_positive_gini AS
            WITH ranked AS (
                SELECT
                    reporter_code,
                    year,
                    flow,
                    dimension,
                    source_note,
                    source_label,
                    source_matches_country_size_panel,
                    trade_value,
                    ROW_NUMBER() OVER (
                        PARTITION BY reporter_code, year, flow, dimension, source_note
                        ORDER BY trade_value ASC, item_id ASC
                    ) AS asc_rank,
                    COUNT(*) OVER (PARTITION BY reporter_code, year, flow, dimension, source_note) AS n,
                    SUM(trade_value) OVER (PARTITION BY reporter_code, year, flow, dimension, source_note) AS total
                FROM post_items
                WHERE trade_value > 0 AND is_old_item = 1
            )
            SELECT
                reporter_code,
                year,
                flow,
                dimension,
                source_note,
                source_label,
                source_matches_country_size_panel,
                ((2.0 * SUM(asc_rank * trade_value)) / (MAX(n) * MAX(total))) - ((MAX(n) + 1.0) / MAX(n)) AS old_positive_gini
            FROM ranked
            GROUP BY 1, 2, 3, 4, 5, 6, 7
            """
        )
        con.execute(
            f"""
            CREATE TEMP TABLE old_panel AS
            SELECT
                o.reporter_code,
                y.year,
                o.flow,
                o.dimension,
                o.source_note,
                o.source_label,
                o.source_matches_country_size_panel,
                o.item_id,
                COALESCE(p.trade_value, 0.0) AS trade_value
            FROM old_universe o
            INNER JOIN (
                SELECT DISTINCT reporter_code, year, flow, dimension, source_note
                FROM item_values
                WHERE year >= {int(post_start_year)}
            ) y
              ON o.reporter_code = y.reporter_code
             AND o.flow = y.flow
             AND o.dimension = y.dimension
             AND o.source_note = y.source_note
            LEFT JOIN post_items p
              ON o.reporter_code = p.reporter_code
             AND y.year = p.year
             AND o.flow = p.flow
             AND o.dimension = p.dimension
             AND o.source_note = p.source_note
             AND o.item_id = p.item_id
            """
        )
        con.execute(
            """
            CREATE TEMP TABLE old_universe_gini AS
            WITH ranked AS (
                SELECT
                    reporter_code,
                    year,
                    flow,
                    dimension,
                    source_note,
                    source_label,
                    source_matches_country_size_panel,
                    trade_value,
                    ROW_NUMBER() OVER (
                        PARTITION BY reporter_code, year, flow, dimension, source_note
                        ORDER BY trade_value ASC, item_id ASC
                    ) AS asc_rank,
                    COUNT(*) OVER (PARTITION BY reporter_code, year, flow, dimension, source_note) AS n,
                    SUM(trade_value) OVER (PARTITION BY reporter_code, year, flow, dimension, source_note) AS total
                FROM old_panel
            )
            SELECT
                reporter_code,
                year,
                flow,
                dimension,
                source_note,
                source_label,
                source_matches_country_size_panel,
                CASE
                    WHEN MAX(total) > 0
                    THEN ((2.0 * SUM(asc_rank * trade_value)) / (MAX(n) * MAX(total))) - ((MAX(n) + 1.0) / MAX(n))
                    ELSE NULL
                END AS old_universe_gini_with_exits
            FROM ranked
            GROUP BY 1, 2, 3, 4, 5, 6, 7
            """
        )
        metrics = con.execute(
            """
            SELECT
                s.reporter_code,
                s.year,
                s.flow,
                s.dimension,
                s.source_note,
                s.source_label,
                s.source_matches_country_size_panel,
                s.total_value,
                s.total_active_count,
                s.old_value,
                s.new_value,
                s.old_active_count,
                s.new_active_count,
                oc.old_universe_count,
                oc.old_universe_pre_trade_value,
                (s.new_value / NULLIF(s.total_value, 0)) AS new_value_share,
                (s.old_value / NULLIF(s.total_value, 0)) AS old_value_share,
                (CAST(s.new_active_count AS DOUBLE) / NULLIF(s.total_active_count, 0)) AS new_active_share,
                ((oc.old_universe_count - s.old_active_count) / NULLIF(CAST(oc.old_universe_count AS DOUBLE), 0)) AS old_exit_count_share,
                ag.total_gini,
                opg.old_positive_gini,
                oug.old_universe_gini_with_exits
            FROM status_summary s
            LEFT JOIN old_counts oc
              ON s.reporter_code = oc.reporter_code
             AND s.flow = oc.flow
             AND s.dimension = oc.dimension
             AND s.source_note = oc.source_note
            LEFT JOIN all_gini ag
              ON s.reporter_code = ag.reporter_code
             AND s.year = ag.year
             AND s.flow = ag.flow
             AND s.dimension = ag.dimension
             AND s.source_note = ag.source_note
            LEFT JOIN old_positive_gini opg
              ON s.reporter_code = opg.reporter_code
             AND s.year = opg.year
             AND s.flow = opg.flow
             AND s.dimension = opg.dimension
             AND s.source_note = opg.source_note
            LEFT JOIN old_universe_gini oug
              ON s.reporter_code = oug.reporter_code
             AND s.year = oug.year
             AND s.flow = oug.flow
             AND s.dimension = oug.dimension
             AND s.source_note = oug.source_note
            ORDER BY s.reporter_code, s.year, s.flow, s.dimension, s.source_note
            """
        ).df()
        source_diagnostics = con.execute(
            """
            SELECT
                'item_values' AS table_name,
                dimension,
                flow,
                source_note,
                source_label,
                COUNT(*) AS rows,
                COUNT(DISTINCT reporter_code) AS countries,
                COUNT(DISTINCT year) AS years,
                SUM(trade_value) AS trade_value
            FROM item_values
            GROUP BY 1, 2, 3, 4, 5
            UNION ALL
            SELECT
                'old_universe' AS table_name,
                dimension,
                flow,
                source_note,
                source_label,
                COUNT(*) AS rows,
                COUNT(DISTINCT reporter_code) AS countries,
                NULL AS years,
                SUM(pre_trade_value) AS trade_value
            FROM old_universe
            GROUP BY 1, 2, 3, 4, 5
            UNION ALL
            SELECT
                'post_items' AS table_name,
                dimension,
                flow,
                source_note,
                source_label,
                COUNT(*) AS rows,
                COUNT(DISTINCT reporter_code) AS countries,
                COUNT(DISTINCT year) AS years,
                SUM(trade_value) AS trade_value
            FROM post_items
            GROUP BY 1, 2, 3, 4, 5
            ORDER BY table_name, dimension, flow, source_note
            """
        ).df()
    finally:
        con.close()
    return metrics, source_diagnostics


def load_controls(country_sample: str, start_year: int, end_year: int) -> pd.DataFrame:
    path = sample_processed_path("country_size_effect_panel.parquet", country_sample)
    if not path.exists():
        raise FileNotFoundError(f"Missing country-size panel: {path}")
    panel = pd.read_parquet(
        path,
        columns=["country", "iso3", "reporter_code", "year", "flow", "log_population", "log_gdp_per_capita", "product_gini", "partner_gini"],
    )
    panel = panel[panel["year"].between(start_year, end_year)].copy()
    dupes = int(panel.duplicated(["reporter_code", "year", "flow"]).sum())
    if dupes:
        raise RuntimeError(f"Country-size panel has {dupes:,} duplicate reporter-year-flow rows.")
    return panel


def merge_controls(metrics: pd.DataFrame, controls: pd.DataFrame) -> pd.DataFrame:
    out = metrics.merge(
        controls,
        on=["reporter_code", "year", "flow"],
        how="left",
        validate="many_to_one",
    )
    out["source_total_gini"] = np.where(out["dimension"].eq("product"), out["product_gini"], out["partner_gini"])
    raw_diff = (out["total_gini"] - out["source_total_gini"]).abs()
    out["total_gini_abs_diff_vs_source_raw"] = raw_diff
    out["total_gini_abs_diff_vs_source"] = np.where(out["source_matches_country_size_panel"], raw_diff, np.nan)
    return out


def sample_diagnostics(panel: pd.DataFrame, source_diagnostics: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = [
        {"diagnostic": "panel_rows", "value": len(panel), "detail": ""},
        {"diagnostic": "countries", "value": panel["reporter_code"].nunique(), "detail": ""},
        {"diagnostic": "years", "value": panel["year"].nunique(), "detail": ""},
        {"diagnostic": "duplicate_reporter_year_flow_dimension_source_rows", "value": int(panel.duplicated(["reporter_code", "year", "flow", "dimension", "source_note"]).sum()), "detail": ""},
        {"diagnostic": "missing_log_population", "value": int(panel["log_population"].isna().sum()), "detail": ""},
        {"diagnostic": "missing_log_gdp_per_capita", "value": int(panel["log_gdp_per_capita"].isna().sum()), "detail": ""},
        {"diagnostic": "missing_old_universe_count", "value": int(panel["old_universe_count"].isna().sum()), "detail": ""},
        {"diagnostic": "median_total_gini_abs_diff_vs_source", "value": float(panel["total_gini_abs_diff_vs_source"].median(skipna=True)), "detail": "recomputed total Gini versus country_size_effect_panel"},
        {"diagnostic": "max_total_gini_abs_diff_vs_source", "value": float(panel["total_gini_abs_diff_vs_source"].max(skipna=True)), "detail": "recomputed total Gini versus country_size_effect_panel"},
    ]
    for (flow, dimension, source_label), group in panel.groupby(["flow", "dimension", "source_label"], observed=True):
        detail = f"{flow}/{dimension}/{source_label}"
        rows.extend(
            [
                {"diagnostic": "rows_by_flow_dimension_source", "value": len(group), "detail": detail},
                {"diagnostic": "countries_by_flow_dimension_source", "value": group["reporter_code"].nunique(), "detail": detail},
                {"diagnostic": "median_new_value_share", "value": float(group["new_value_share"].median(skipna=True)), "detail": detail},
                {"diagnostic": "median_new_active_share", "value": float(group["new_active_share"].median(skipna=True)), "detail": detail},
                {"diagnostic": "median_old_exit_count_share", "value": float(group["old_exit_count_share"].median(skipna=True)), "detail": detail},
            ]
        )
    source_rows = source_diagnostics.rename(columns={"table_name": "diagnostic", "rows": "value"}).copy()
    source_rows["detail"] = (
        source_rows["diagnostic"]
        + "/"
        + source_rows["flow"].astype(str)
        + "/"
        + source_rows["dimension"].astype(str)
        + "/"
        + source_rows["source_label"].astype(str)
    )
    source_rows = source_rows[["diagnostic", "value", "detail"]]
    return pd.concat([pd.DataFrame(rows), source_rows], ignore_index=True)


def add_q_values(models: pd.DataFrame, model_labels: Iterable[str], terms: Iterable[str]) -> pd.DataFrame:
    out = models.copy()
    out["bh_q_value"] = np.nan
    for model_label in model_labels:
        for term in terms:
            mask = out["model_label"].eq(model_label) & out["term"].eq(term) & out["status"].eq("ok")
            out.loc[mask, "bh_q_value"] = cse.benjamini_hochberg(out.loc[mask, "p_value"])
    return out


def run_models(panel: pd.DataFrame, country_sample: str, two_way: bool = False) -> pd.DataFrame:
    outcomes = [
        ("total_gini", "gini", "All active items Gini"),
        ("old_positive_gini", "gini", "Old continuing active items Gini"),
        ("old_universe_gini_with_exits", "gini", "Old pre-2002 universe Gini with exits as zeros"),
        ("new_value_share", "entry_share", "New item value share"),
        ("new_active_share", "entry_share", "New active item share"),
        ("old_exit_count_share", "exit_share", "Old item exit count share"),
    ]
    results: list[cse.ModelResult] = []
    model_label = MODEL_LABEL_TWOWAY if two_way else MODEL_LABEL
    for flow in cse.FLOWS:
        for dimension in DIMENSIONS:
            work = panel[panel["flow"].eq(flow) & panel["dimension"].eq(dimension)].copy()
            for outcome, metric, _label in outcomes:
                results.append(
                    cse.run_ols_model(
                        work,
                        outcome=outcome,
                        terms=[cse.PRIMARY_TERM, cse.CONTROL_TERM],
                        fixed_effects=["year"],
                        model_label=model_label,
                        sample=country_sample,
                        flow=flow,
                        dimension=dimension,
                        metric=metric,
                        cluster_col="reporter_code",
                        two_way_cluster_col="year" if two_way else None,
                    )
                )
    out = add_q_values(cse.model_results_to_frame(results), [model_label], [cse.PRIMARY_TERM])
    source_map = panel[["flow", "dimension", "source_note", "source_label", "source_matches_country_size_panel"]].drop_duplicates()
    out = out.merge(source_map, on=["flow", "dimension"], how="left")
    return out


def fmt_num(value: object, digits: int = 4) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value):.{digits}f}"


def fmt_sig(value: object, p_value: object, digits: int = 4) -> str:
    text = fmt_num(value, digits)
    if not text:
        return text
    if pd.notna(p_value) and float(p_value) < 0.05:
        return f"**{text}**"
    return text


def format_p(value: object) -> str:
    if pd.isna(value):
        return ""
    value = float(value)
    text = "0.0000" if value < 0.00005 else f"{value:.4f}"
    if value < 0.05:
        return f"**{text}**"
    return text


def regression_table(models: pd.DataFrame, metric: str) -> str:
    rows = []
    work = models[models["term"].eq(cse.PRIMARY_TERM) & models["metric"].eq(metric)].copy()
    for row in work.sort_values(["outcome", "flow", "dimension"]).itertuples(index=False):
        rows.append(
            {
                "Outcome": row.outcome,
                "Flow": row.flow,
                "Dimension": row.dimension,
                "Source": getattr(row, "source_label", ""),
                "Log-pop beta": fmt_sig(row.coefficient, row.p_value),
                "p": format_p(row.p_value),
                "q": format_p(row.bh_q_value),
                "N": int(row.nobs),
            }
        )
    return pd.DataFrame(rows).to_markdown(index=False)


def channel_medians(panel: pd.DataFrame) -> str:
    summary = (
        panel.groupby(["flow", "dimension", "source_label"], as_index=False, observed=True)
        .agg(
            median_new_value_share=("new_value_share", "median"),
            median_new_active_share=("new_active_share", "median"),
            median_old_exit_count_share=("old_exit_count_share", "median"),
            median_total_gini=("total_gini", "median"),
            median_old_positive_gini=("old_positive_gini", "median"),
            median_old_universe_gini_with_exits=("old_universe_gini_with_exits", "median"),
        )
        .sort_values(["flow", "dimension", "source_label"])
    )
    for col in summary.columns:
        if col.startswith("median_"):
            summary[col] = summary[col].map(lambda value: f"{value:.4f}" if pd.notna(value) else "")
    return summary.to_markdown(index=False)


def source_difference_examples(panel: pd.DataFrame, n: int = 25) -> pd.DataFrame:
    cols = [
        "country",
        "iso3",
        "reporter_code",
        "year",
        "flow",
        "dimension",
        "source_label",
        "source_matches_country_size_panel",
        "total_gini",
        "source_total_gini",
        "total_gini_abs_diff_vs_source_raw",
        "total_active_count",
        "total_value",
    ]
    available = [col for col in cols if col in panel.columns]
    return (
        panel.sort_values("total_gini_abs_diff_vs_source_raw", ascending=False)
        .loc[:, available]
        .head(n)
        .reset_index(drop=True)
    )


def write_summary(
    path: Path,
    args: argparse.Namespace,
    panel: pd.DataFrame,
    models: pd.DataFrame,
    two_way_models: pd.DataFrame,
    diagnostics: pd.DataFrame,
    output_paths: dict[str, Path],
) -> None:
    diag = diagnostics.set_index("diagnostic")["value"].to_dict()
    text = f"""# Country-Size Common-Universe Post-2001 Test

Generated: {now_utc()}

## Question

When larger countries are less concentrated after 2001, is that because they added new products/partners, or because trade value became less concentrated among products/partners that were already active before 2002?

This is a descriptive mechanism test, not a causal estimate of fixed-cost declines.

## Definitions

- `old item`: a product or partner with positive trade for the same country-flow at least once in {args.start_year}-{args.post_start_year - 1}.
- `new item`: a product or partner observed in a post-2001 country-flow-year but absent from that pre-2002 country-flow universe.
- `total_gini`: Gini over all active post-2001 items.
- `old_positive_gini`: Gini over old items that are still active in that post-2001 year. This asks about reallocation among continuing old items.
- `old_universe_gini_with_exits`: Gini over the whole old pre-2002 item universe, assigning zero to old items not active in that post-2001 year. This combines continuing-value reallocation and exits.
- `new_value_share`: post-2001 trade-value share from new items.

Product-level calculations exclude HS6 `{PRODUCT_EXCLUDED_CODE}`. Export partner calculations exclude `partner_code == 0` and otherwise follow the repo's partner-total convention.

Source note: export rows use the main Exercise 2/12 export item universe. Import rows use the Exercise 11 mapped import-cell checkpoint as a sensitivity because a full import item-universe checkpoint is not currently materialized. The mapped import-partner row is therefore a no-`{PRODUCT_EXCLUDED_CODE}` sensitivity, not the default partner convention.

## Sample

- Country sample: `{args.country_sample}`
- Pre-period old universe: {args.start_year}-{args.post_start_year - 1}
- Post period: {args.post_start_year}-{args.end_year}
- Panel rows: {int(diag.get("panel_rows", 0)):,}
- Countries: {int(diag.get("countries", 0))}
- Years: {int(diag.get("years", 0))}
- Duplicate country-year-flow-dimension-source rows: {int(diag.get("duplicate_reporter_year_flow_dimension_source_rows", 0))}
- Median absolute difference between recomputed total Gini and matching source panel Gini: {fmt_num(diag.get("median_total_gini_abs_diff_vs_source"), 8)}

## Channel Medians

{channel_medians(panel)}

## Gini Regression Results

Each row reports the post-2001 coefficient on `log_population`, controlling for `log_gdp_per_capita` and year fixed effects, with reporter-country clustered standard errors. Bold means `p < 0.05`.

{regression_table(models, "gini")}

## Entry And Exit Regression Results

{regression_table(models, "entry_share")}

{regression_table(models, "exit_share")}

## Two-Way Cluster Check For Gini Outcomes

This repeats the Gini regressions with reporter-country and year clustered standard errors.

{regression_table(two_way_models, "gini")}

## Interpretation

- If the size effect were mostly about entry, larger countries should have lower total concentration and higher `new_value_share` or `new_active_share`.
- If the size effect survives for `old_positive_gini`, then larger countries are less concentrated even among old continuing products/partners. That points to value reallocation within established trade relationships, not just entry.
- If the size effect appears mainly in `old_universe_gini_with_exits`, exits from the old universe are part of the story.

## Caveats

- Product-code revisions can affect old/new HS6 product status. This script uses the same observed HS6 code object as the existing concentration panel; a harmonized-product-family version would be a stricter follow-up.
- Import rows are sensitivity evidence from mapped Exercise 11 import cells, not the full import concentration universe. Treat them as directional checks until a full import item-history checkpoint is built from raw Comtrade.
- The old universe requires pre-2002 data for the country-flow-dimension. Late-entering reporters can have missing common-universe outcomes.
- `old_universe_gini_with_exits` is zero-inclusive by construction, unlike the repo's standard active-positive Gini.

## Files

- Panel: `{rel(output_paths["panel"])}`
- Regression models: `{rel(output_paths["models"])}`
- Two-way cluster models: `{rel(output_paths["two_way_models"])}`
- Diagnostics: `{rel(output_paths["diagnostics"])}`
- Source diagnostics: `{rel(output_paths["source_diagnostics"])}`
- Largest source-Gini differences: `{rel(output_paths["source_difference_examples"])}`
- Manifest: `{rel(output_paths["manifest"])}`
"""
    path.write_text(text, encoding="utf-8")


def write_manifest(path: Path, args: argparse.Namespace, output_paths: dict[str, Path]) -> None:
    manifest = {
        "generated_at": now_utc(),
        "script": rel(Path(__file__).resolve()),
        "country_sample": args.country_sample,
        "start_year": args.start_year,
        "post_start_year": args.post_start_year,
        "end_year": args.end_year,
        "aggregate_glob": rel(aggregate_glob(args.country_sample)),
        "import_cells_glob": rel(import_cells_glob(args.country_sample)),
        "input_controls": rel(sample_processed_path("country_size_effect_panel.parquet", args.country_sample)),
        "outputs": {key: rel(value) for key, value in output_paths.items()},
        "rules": {
            "product_999999": "excluded before item aggregation",
            "partner_code_0": "excluded before item aggregation",
            "import_partner": "Exercise 11 mapped import-cell no-999999 sensitivity, not default partner convention",
            "country_sample": args.country_sample,
        },
    }
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country-sample", default="rd2_countries", choices=COUNTRY_SAMPLE_CHOICES)
    parser.add_argument("--start-year", type=int, default=DEFAULT_START_YEAR)
    parser.add_argument("--post-start-year", type=int, default=DEFAULT_POST_START_YEAR)
    parser.add_argument("--end-year", type=int, default=DEFAULT_END_YEAR)
    parser.add_argument("--workers", type=int, default=4)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.start_year >= args.post_start_year:
        raise RuntimeError("start-year must be before post-start-year.")
    if args.end_year < args.post_start_year:
        raise RuntimeError("end-year must be at least post-start-year.")

    result_dir = sample_results_dir(args.country_sample)
    table_dir = result_dir / "country_size_common_universe_test_tables"
    ensure_dirs(result_dir, table_dir)

    raw_metrics, source_diagnostics = build_common_universe_tables(
        args.country_sample,
        args.start_year,
        args.post_start_year,
        args.end_year,
        args.workers,
    )
    controls = load_controls(args.country_sample, args.start_year, args.end_year)
    panel = merge_controls(raw_metrics, controls)
    diagnostics = sample_diagnostics(panel, source_diagnostics)
    models = run_models(panel, args.country_sample, two_way=False)
    two_way_models = run_models(panel, args.country_sample, two_way=True)

    output_paths = {
        "panel": table_dir / "common_universe_panel.csv",
        "models": table_dir / "common_universe_models.csv",
        "two_way_models": table_dir / "common_universe_two_way_models.csv",
        "diagnostics": table_dir / "diagnostics.csv",
        "source_diagnostics": table_dir / "source_diagnostics.csv",
        "source_difference_examples": table_dir / "source_difference_examples.csv",
        "manifest": result_dir / "run_manifest_country_size_common_universe_test.json",
        "summary": result_dir / "country_size_common_universe_test.md",
    }
    panel.to_csv(output_paths["panel"], index=False)
    models.to_csv(output_paths["models"], index=False)
    two_way_models.to_csv(output_paths["two_way_models"], index=False)
    diagnostics.to_csv(output_paths["diagnostics"], index=False)
    source_diagnostics.to_csv(output_paths["source_diagnostics"], index=False)
    source_difference_examples(panel).to_csv(output_paths["source_difference_examples"], index=False)
    write_manifest(output_paths["manifest"], args, output_paths)
    write_summary(output_paths["summary"], args, panel, models, two_way_models, diagnostics, output_paths)
    print(f"Wrote {output_paths['summary']}")


if __name__ == "__main__":
    main()
