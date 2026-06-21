#!/usr/bin/env python3
"""US import concentration puzzle diagnostics.

This script builds a reproducible descriptive package for the question:
why did US imports historically look more HS6-product concentrated than
US exports?
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import pyarrow.dataset as ds


ROOT = Path(__file__).resolve().parents[1]
DATA_PROCESSED = ROOT / "data" / "processed"
RESULTS = ROOT / "results"
OUT_TABLES = RESULTS / "us_import_concentration_puzzle_tables"
OUT_MEMO = RESULTS / "us_import_export_concentration_puzzle.md"

CONCENTRATION_PATH = DATA_PROCESSED / "concentration_all_years.parquet"
PRODUCT_PANEL_PATH = DATA_PROCESSED / "exercise_11_product_export_linkage_panel.parquet"
EXPORT_AGG_PATH = DATA_PROCESSED / "exercise_12_export_aggregates.parquet"
BEC_MAPPING_PATH = DATA_PROCESSED / "exercise_03_bec5_mapping_approved.csv"
EX04_IMPORTER_SUMMARY = RESULTS / "exercise_04_tables" / "dominant_supplier_importer_summary.csv"
EX13_LATEST_COUNTRY = RESULTS / "exercise_13_import_hypotheses_tables" / "h2_supplier_ecosystem_latest_country.csv"
EX13_TOP_PRODUCTS = RESULTS / "exercise_13_import_hypotheses_tables" / "h2_supplier_ecosystem_top_products_latest.csv"

EXCEPTION_ISOS = ["USA", "CHN", "IND", "ITA"]
EXCLUDED_HS6_CODES = {"999999"}
COMMODITY_OUTLIER_HS4 = {"2701", "2709", "2710", "2711", "7108"}


def ensure_dirs() -> None:
    OUT_TABLES.mkdir(parents=True, exist_ok=True)


def normalize_cmd(series: pd.Series) -> pd.Series:
    return series.astype(str).str.extract(r"(\d{1,6})", expand=False).str.zfill(6)


def drop_excluded_hs6(df: pd.DataFrame, code_col: str = "cmd_code") -> pd.DataFrame:
    if df.empty or code_col not in df.columns:
        return df.copy()
    codes = normalize_cmd(df[code_col])
    return df.loc[~codes.isin(EXCLUDED_HS6_CODES)].copy()


def assert_no_excluded_hs6(df: pd.DataFrame, label: str, code_col: str = "cmd_code") -> None:
    if code_col not in df.columns:
        return
    mask = normalize_cmd(df[code_col]).isin(EXCLUDED_HS6_CODES)
    if bool(mask.any()):
        raise RuntimeError(f"{label} contains excluded HS6 code 999999.")


def gini(values: Iterable[float] | pd.Series | np.ndarray) -> float:
    arr = np.asarray(list(values) if not isinstance(values, (pd.Series, np.ndarray)) else values, dtype=float)
    arr = arr[np.isfinite(arr) & (arr > 0)]
    if arr.size == 0:
        return np.nan
    arr.sort()
    total = arr.sum()
    if total <= 0:
        return np.nan
    n = arr.size
    ranks = np.arange(1, n + 1, dtype=float)
    return float((2 * np.sum(ranks * arr) / (n * total)) - ((n + 1) / n))


def loo_gini_contributions(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    order = np.argsort(values, kind="mergesort")
    sorted_values = values[order]
    n = sorted_values.size
    out_sorted = np.full(n, np.nan, dtype=float)
    total_gini = gini(sorted_values)
    if n <= 1:
        out = np.full(n, np.nan, dtype=float)
        out[order] = out_sorted
        return out
    total = float(sorted_values.sum())
    ranks = np.arange(1, n + 1, dtype=float)
    weighted_sum = float(np.sum(ranks * sorted_values))
    suffix_after = total - np.cumsum(sorted_values)
    total_without = total - sorted_values
    weighted_without = weighted_sum - ranks * sorted_values - suffix_after
    valid = total_without > 0
    n2 = n - 1
    gini_without = np.full(n, np.nan, dtype=float)
    gini_without[valid] = (2 * weighted_without[valid] / (n2 * total_without[valid])) - ((n2 + 1) / n2)
    out_sorted = total_gini - gini_without
    out = np.full(n, np.nan, dtype=float)
    out[order] = out_sorted
    return out


def read_filtered_dataset(path: Path, columns: list[str], filter_expr) -> pd.DataFrame:
    dataset = ds.dataset(path, format="parquet")
    return dataset.to_table(columns=columns, filter=filter_expr).to_pandas()


def pct(value: float | int | None, digits: int = 1) -> str:
    if value is None or not np.isfinite(value):
        return ""
    return f"{100 * float(value):.{digits}f}%"


def num(value: float | int | None, digits: int = 4, signed: bool = False) -> str:
    if value is None or not np.isfinite(value):
        return ""
    prefix = "+" if signed and float(value) > 0 else ""
    return f"{prefix}{float(value):.{digits}f}"


def money_b(value: float | int | None) -> str:
    if value is None or not np.isfinite(value):
        return ""
    return f"${float(value) / 1e9:,.1f}B"


def short_text(value: object, width: int = 78) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= width:
        return text
    return text[: width - 3].rstrip() + "..."


def markdown_table(df: pd.DataFrame, columns: list[str], formatters: dict[str, callable] | None = None) -> str:
    formatters = formatters or {}
    rows: list[list[str]] = []
    integer_columns = {"year", "years", "rank", "latest_year", "observed_start_year", "observed_end_year"}
    for _, row in df[columns].iterrows():
        out_row = []
        for col in columns:
            value = row[col]
            if pd.isna(value):
                out_row.append("")
            elif col in formatters:
                out_row.append(str(formatters[col](value)))
            elif col in integer_columns:
                out_row.append(str(int(value)))
            elif isinstance(value, float):
                out_row.append(num(value, 4))
            else:
                out_row.append(str(value))
        rows.append(out_row)
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([header, sep, *body])


def load_concentration() -> pd.DataFrame:
    conc = pd.read_parquet(CONCENTRATION_PATH)
    conc["flow"] = conc["flow"].astype(str)
    conc["year"] = pd.to_numeric(conc["year"], errors="coerce").astype(int)
    return conc


def mode_or_default(series: pd.Series, default: str) -> str:
    clean = series.dropna().astype(str)
    clean = clean[clean.str.len() > 0]
    if clean.empty:
        return default
    return clean.value_counts().sort_values(ascending=False).index[0]


def first_nonempty(series: pd.Series, default: str = "") -> str:
    clean = series.dropna().astype(str).str.strip()
    clean = clean[clean.str.len() > 0]
    if clean.empty:
        return default
    return clean.iloc[0]


def load_bec_mapping() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    cols = ["classification_code", "cmd_code", "exercise_03_bin", "hs_desc_official", "hs_desc_if_available"]
    raw = pd.read_csv(BEC_MAPPING_PATH, usecols=lambda col: col in cols, dtype={"cmd_code": str})
    raw["classification_code"] = raw["classification_code"].fillna("").astype(str)
    raw["cmd_code"] = normalize_cmd(raw["cmd_code"])
    raw = drop_excluded_hs6(raw)
    raw["import_bin"] = raw.get("exercise_03_bin", "unmapped_or_ambiguous")
    raw["import_bin"] = raw["import_bin"].fillna("unmapped_or_ambiguous").astype(str)
    official = raw.get("hs_desc_official", pd.Series(index=raw.index, dtype=object))
    fallback = raw.get("hs_desc_if_available", pd.Series(index=raw.index, dtype=object))
    raw["product_description"] = official.fillna(fallback).fillna("").astype(str).str.strip()

    exact = (
        raw.sort_values(["classification_code", "cmd_code", "product_description"])
        .drop_duplicates(["classification_code", "cmd_code"])
        [["classification_code", "cmd_code", "import_bin", "product_description"]]
        .copy()
    )
    by_cmd = (
        raw.groupby("cmd_code", as_index=False)
        .agg(
            import_bin=("import_bin", lambda s: mode_or_default(s, "unmapped_or_ambiguous")),
            product_description=("product_description", first_nonempty),
        )
        .copy()
    )
    desc = by_cmd[["cmd_code", "product_description"]].copy()
    return exact, by_cmd, desc


def add_product_metadata(df: pd.DataFrame, exact_map: pd.DataFrame, cmd_map: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "classification_code" not in out.columns:
        out["classification_code"] = ""
    out["classification_code"] = out["classification_code"].fillna("").astype(str)
    out["cmd_code"] = normalize_cmd(out["cmd_code"])
    out = out.merge(exact_map, on=["classification_code", "cmd_code"], how="left")
    fallback = cmd_map.rename(
        columns={
            "import_bin": "fallback_import_bin",
            "product_description": "fallback_product_description",
        }
    )
    out = out.merge(fallback, on="cmd_code", how="left")
    out["import_bin"] = out["import_bin"].fillna(out["fallback_import_bin"]).fillna("unmapped_or_ambiguous")
    out["product_description"] = (
        out["product_description"].fillna(out["fallback_product_description"]).fillna("").astype(str).str.strip()
    )
    out = out.drop(columns=["fallback_import_bin", "fallback_product_description"])
    out["hs2"] = out["cmd_code"].str[:2]
    out["hs4"] = out["cmd_code"].str[:4]
    return out


def make_country_exception_summary(conc: pd.DataFrame) -> pd.DataFrame:
    wide = conc.pivot_table(index=["iso3", "country", "year"], columns="flow", values="product_gini", aggfunc="first")
    wide = wide.rename(columns={"Imports": "import_product_gini", "Exports": "export_product_gini"}).reset_index()
    rows: list[dict[str, object]] = []
    for iso in EXCEPTION_ISOS:
        sub = wide[wide["iso3"].eq(iso)].dropna(subset=["import_product_gini", "export_product_gini"]).copy()
        if sub.empty:
            continue
        sub["import_minus_export_product_gini_gap"] = sub["import_product_gini"] - sub["export_product_gini"]
        latest = sub.sort_values("year").iloc[-1]
        rows.append(
            {
                "country": latest["country"],
                "iso3": iso,
                "observed_start_year": int(sub["year"].min()),
                "observed_end_year": int(sub["year"].max()),
                "observed_years": int(len(sub)),
                "share_years_import_product_gini_gt_export_product_gini": float(
                    sub["import_minus_export_product_gini_gap"].gt(0).mean()
                ),
                "median_import_minus_export_product_gini_gap": float(
                    sub["import_minus_export_product_gini_gap"].median()
                ),
                "latest_year": int(latest["year"]),
                "latest_import_product_gini": float(latest["import_product_gini"]),
                "latest_export_product_gini": float(latest["export_product_gini"]),
                "latest_import_minus_export_product_gini_gap": float(
                    latest["import_minus_export_product_gini_gap"]
                ),
                "latest_import_product_gini_gt_export_product_gini": bool(
                    latest["import_minus_export_product_gini_gap"] > 0
                ),
            }
        )
    return pd.DataFrame(rows)


def make_gini_gap_timeseries(conc: pd.DataFrame, country: str, start_year: int, latest_year: int, post_cutoff: int) -> pd.DataFrame:
    values = [
        "total_trade_value",
        "product_gini",
        "product_active_count",
        "partner_gini",
        "partner_active_count",
    ]
    wide = conc[conc["iso3"].eq(country)].pivot_table(
        index=["country", "iso3", "reporter_code", "year"], columns="flow", values=values, aggfunc="first"
    )
    wide.columns = [f"{metric}_{flow.lower()}" for metric, flow in wide.columns]
    out = wide.reset_index()
    out = out[out["year"].between(start_year, latest_year)].copy()
    out["product_gini_gap_import_minus_export"] = out["product_gini_imports"] - out["product_gini_exports"]
    out["partner_gini_gap_import_minus_export"] = out["partner_gini_imports"] - out["partner_gini_exports"]
    out["product_gap_positive"] = out["product_gini_gap_import_minus_export"] > 0
    out["period"] = np.where(out["year"] < post_cutoff, f"pre_{post_cutoff}", f"{post_cutoff}_onward")
    return out.sort_values("year").reset_index(drop=True)


def load_import_products(country: str, start_year: int, latest_year: int) -> pd.DataFrame:
    cols = [
        "country",
        "iso3",
        "reporter_code",
        "year",
        "cmd_code",
        "import_bin",
        "import_value",
        "total_imports",
        "import_value_share",
        "top_supplier_iso3",
        "top_supplier_name",
        "within_product_top_supplier_share",
        "within_product_source_hhi",
        "supplier_count",
    ]
    frame = read_filtered_dataset(
        PRODUCT_PANEL_PATH,
        cols,
        (ds.field("iso3") == country) & (ds.field("year") >= start_year) & (ds.field("year") <= latest_year),
    )
    frame["cmd_code"] = normalize_cmd(frame["cmd_code"])
    frame = drop_excluded_hs6(frame)
    frame["year"] = pd.to_numeric(frame["year"], errors="coerce").astype(int)
    frame["import_value"] = pd.to_numeric(frame["import_value"], errors="coerce")
    frame = frame.dropna(subset=["year", "cmd_code", "import_value"])
    frame = frame[frame["import_value"] > 0].copy()
    frame["hs2"] = frame["cmd_code"].str[:2]
    frame["hs4"] = frame["cmd_code"].str[:4]
    frame["import_bin"] = frame["import_bin"].fillna("unmapped_or_ambiguous").astype(str)
    return frame.sort_values(["year", "cmd_code"]).reset_index(drop=True)


def load_export_products(
    country: str,
    start_year: int,
    latest_year: int,
    exact_map: pd.DataFrame,
    cmd_map: pd.DataFrame,
) -> pd.DataFrame:
    cols = ["country", "iso3", "reporter_code", "year", "classification_code", "cmd_code", "trade_value", "dimension"]
    frame = read_filtered_dataset(
        EXPORT_AGG_PATH,
        cols,
        (ds.field("iso3") == country)
        & (ds.field("dimension") == "product")
        & (ds.field("year") >= start_year)
        & (ds.field("year") <= latest_year),
    )
    frame["cmd_code"] = normalize_cmd(frame["cmd_code"])
    frame = drop_excluded_hs6(frame)
    frame["year"] = pd.to_numeric(frame["year"], errors="coerce").astype(int)
    frame["trade_value"] = pd.to_numeric(frame["trade_value"], errors="coerce")
    frame = frame.dropna(subset=["year", "cmd_code", "trade_value"])
    frame = frame[frame["trade_value"] > 0].copy()
    frame = add_product_metadata(frame, exact_map, cmd_map)
    grouped = (
        frame.groupby(["country", "iso3", "reporter_code", "year", "cmd_code", "hs2", "hs4", "import_bin"], as_index=False)
        .agg(
            export_value=("trade_value", "sum"),
            product_description=("product_description", first_nonempty),
            classification_code=("classification_code", first_nonempty),
        )
        .copy()
    )
    return grouped.sort_values(["year", "cmd_code"]).reset_index(drop=True)


def gini_by_year(df: pd.DataFrame, value_col: str, out_col: str) -> pd.DataFrame:
    return (
        df.groupby("year")
        .agg(**{out_col: (value_col, gini), f"{out_col}_active_products": (value_col, "size")})
        .reset_index()
    )


def validate_reconstructed_ginis(
    concentration: pd.DataFrame,
    import_products: pd.DataFrame,
    export_products: pd.DataFrame,
    country: str,
    start_year: int,
    latest_year: int,
    tolerance: float = 1e-6,
) -> dict[str, float]:
    imp = gini_by_year(import_products, "import_value", "reconstructed_import_product_gini")
    exp = gini_by_year(export_products, "export_value", "reconstructed_export_product_gini")
    reconstructed = imp.merge(exp, on="year", how="outer")
    official = make_gini_gap_timeseries(concentration, country, start_year, latest_year, post_cutoff=2018)[
        ["year", "product_gini_imports", "product_gini_exports"]
    ]
    check = official.merge(reconstructed, on="year", how="left")
    check["import_abs_diff"] = (
        check["product_gini_imports"] - check["reconstructed_import_product_gini"]
    ).abs()
    check["export_abs_diff"] = (
        check["product_gini_exports"] - check["reconstructed_export_product_gini"]
    ).abs()
    max_import = float(check["import_abs_diff"].max())
    max_export = float(check["export_abs_diff"].max())
    if max_import > tolerance or max_export > tolerance:
        check.to_csv(OUT_TABLES / "us_reconstructed_gini_validation_failures.csv", index=False)
        raise RuntimeError(
            "Reconstructed product Ginis differ from concentration_all_years.parquet "
            f"(max import diff={max_import:g}, max export diff={max_export:g})."
        )
    check.to_csv(OUT_TABLES / "us_reconstructed_gini_validation.csv", index=False)
    return {"max_import_gini_abs_diff": max_import, "max_export_gini_abs_diff": max_export}


def values_for_flow(df: pd.DataFrame, value_col: str, group_col: str, year: int, group: str | None = None) -> pd.DataFrame:
    sub = df[df["year"].eq(year)]
    if group is not None:
        sub = sub[~sub[group_col].fillna("unknown").astype(str).eq(group)]
    return sub


def make_group_leave_one_out(
    import_products: pd.DataFrame,
    export_products: pd.DataFrame,
    group_col: str,
    group_label_col: str,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    years = sorted(set(import_products["year"]).union(set(export_products["year"])))
    for year in years:
        imp_year = import_products[import_products["year"].eq(year)].copy()
        exp_year = export_products[export_products["year"].eq(year)].copy()
        if imp_year.empty or exp_year.empty:
            continue
        imp_year[group_col] = imp_year[group_col].fillna("unknown").astype(str)
        exp_year[group_col] = exp_year[group_col].fillna("unknown").astype(str)
        groups = sorted(set(imp_year[group_col]).union(set(exp_year[group_col])))
        baseline_import_gini = gini(imp_year["import_value"])
        baseline_export_gini = gini(exp_year["export_value"])
        baseline_gap = baseline_import_gini - baseline_export_gini
        total_import = float(imp_year["import_value"].sum())
        total_export = float(exp_year["export_value"].sum())
        for group in groups:
            imp_without = imp_year[~imp_year[group_col].eq(group)]
            exp_without = exp_year[~exp_year[group_col].eq(group)]
            import_gini_without = gini(imp_without["import_value"])
            export_gini_without = gini(exp_without["export_value"])
            gap_without = import_gini_without - export_gini_without
            rows.append(
                {
                    "year": int(year),
                    group_label_col: group,
                    "baseline_import_product_gini": baseline_import_gini,
                    "baseline_export_product_gini": baseline_export_gini,
                    "baseline_import_minus_export_product_gini_gap": baseline_gap,
                    "import_product_gini_without_group": import_gini_without,
                    "export_product_gini_without_group": export_gini_without,
                    "import_minus_export_product_gini_gap_without_group": gap_without,
                    "gap_reduction_when_group_removed": baseline_gap - gap_without,
                    "import_value": float(imp_year.loc[imp_year[group_col].eq(group), "import_value"].sum()),
                    "export_value": float(exp_year.loc[exp_year[group_col].eq(group), "export_value"].sum()),
                    "import_value_share": float(imp_year.loc[imp_year[group_col].eq(group), "import_value"].sum() / total_import),
                    "export_value_share": float(exp_year.loc[exp_year[group_col].eq(group), "export_value"].sum() / total_export),
                    "import_active_products_in_group": int(imp_year[group_col].eq(group).sum()),
                    "export_active_products_in_group": int(exp_year[group_col].eq(group).sum()),
                    "import_active_products_without_group": int(len(imp_without)),
                    "export_active_products_without_group": int(len(exp_without)),
                }
            )
    out = pd.DataFrame(rows)
    return out.sort_values(["year", "gap_reduction_when_group_removed"], ascending=[False, False]).reset_index(drop=True)


def add_loo(df: pd.DataFrame, value_col: str, prefix: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for year, group in df.groupby("year", sort=True):
        work = group[["year", "cmd_code", value_col]].copy()
        work[f"{prefix}_loo_gini_contribution"] = loo_gini_contributions(work[value_col].to_numpy(dtype=float))
        work[f"{prefix}_product_gini"] = gini(work[value_col])
        work[f"{prefix}_active_products"] = int(len(work))
        frames.append(work.rename(columns={value_col: f"{prefix}_value"}))
    return pd.concat(frames, ignore_index=True)


def make_hs6_leave_one_product_out(
    import_products: pd.DataFrame,
    export_products: pd.DataFrame,
    desc: pd.DataFrame,
) -> pd.DataFrame:
    imp = add_loo(import_products[["year", "cmd_code", "import_value"]], "import_value", "import")
    exp = add_loo(export_products[["year", "cmd_code", "export_value"]], "export_value", "export")
    out = imp.merge(exp, on=["year", "cmd_code"], how="outer")
    for col in ["import_value", "export_value", "import_loo_gini_contribution", "export_loo_gini_contribution"]:
        out[col] = out[col].fillna(0.0)
    out["in_imports"] = out["import_value"] > 0
    out["in_exports"] = out["export_value"] > 0
    out["gap_loo_contribution_import_minus_export"] = (
        out["import_loo_gini_contribution"] - out["export_loo_gini_contribution"]
    )
    out["abs_gap_loo_contribution"] = out["gap_loo_contribution_import_minus_export"].abs()
    meta = (
        pd.concat(
            [
                import_products[["cmd_code", "hs2", "hs4", "import_bin"]],
                export_products[["cmd_code", "hs2", "hs4", "import_bin"]],
            ],
            ignore_index=True,
        )
        .drop_duplicates("cmd_code")
        .copy()
    )
    out = out.merge(meta, on="cmd_code", how="left").merge(desc, on="cmd_code", how="left")
    out["rank_abs_gap_loo_within_year"] = (
        out.sort_values(["year", "abs_gap_loo_contribution"], ascending=[True, False])
        .groupby("year")
        .cumcount()
        + 1
    )
    return out.sort_values(["year", "rank_abs_gap_loo_within_year"], ascending=[False, True]).reset_index(drop=True)


def make_commodity_outlier_robustness(
    import_products: pd.DataFrame,
    export_products: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    years = sorted(set(import_products["year"]).union(set(export_products["year"])))
    excluded_codes = ",".join(sorted(COMMODITY_OUTLIER_HS4))
    for year in years:
        imp = import_products[import_products["year"].eq(year)]
        exp = export_products[export_products["year"].eq(year)]
        if imp.empty or exp.empty:
            continue
        imp_out = imp["hs4"].isin(COMMODITY_OUTLIER_HS4)
        exp_out = exp["hs4"].isin(COMMODITY_OUTLIER_HS4)
        for sample, imp_sub, exp_sub in [
            ("baseline", imp, exp),
            ("excluding_oil_gas_gold_coal", imp.loc[~imp_out], exp.loc[~exp_out]),
        ]:
            rows.append(
                {
                    "year": int(year),
                    "sample": sample,
                    "excluded_hs4_codes": "" if sample == "baseline" else excluded_codes,
                    "import_product_gini": gini(imp_sub["import_value"]),
                    "export_product_gini": gini(exp_sub["export_value"]),
                    "import_minus_export_product_gini_gap": gini(imp_sub["import_value"]) - gini(exp_sub["export_value"]),
                    "import_total_value": float(imp_sub["import_value"].sum()),
                    "export_total_value": float(exp_sub["export_value"].sum()),
                    "import_active_products": int(len(imp_sub)),
                    "export_active_products": int(len(exp_sub)),
                    "removed_import_value_share": 0.0
                    if sample == "baseline"
                    else float(imp.loc[imp_out, "import_value"].sum() / imp["import_value"].sum()),
                    "removed_export_value_share": 0.0
                    if sample == "baseline"
                    else float(exp.loc[exp_out, "export_value"].sum() / exp["export_value"].sum()),
                    "removed_import_products": 0 if sample == "baseline" else int(imp_out.sum()),
                    "removed_export_products": 0 if sample == "baseline" else int(exp_out.sum()),
                }
            )
    return pd.DataFrame(rows).sort_values(["year", "sample"]).reset_index(drop=True)


def make_supplier_corridors_latest(
    import_products: pd.DataFrame,
    desc: pd.DataFrame,
    country: str,
    latest_year: int,
    top_n: int,
) -> pd.DataFrame:
    latest = import_products[import_products["year"].eq(latest_year)].copy()
    latest = latest.sort_values("import_value", ascending=False).head(top_n).copy()
    latest["cmd_code"] = normalize_cmd(latest["cmd_code"])
    if EX13_TOP_PRODUCTS.exists():
        ex13 = pd.read_csv(EX13_TOP_PRODUCTS, dtype={"cmd_code": str})
        ex13["cmd_code"] = normalize_cmd(ex13["cmd_code"])
        ex13 = drop_excluded_hs6(ex13)
        ex13 = ex13[(ex13["iso3"].eq(country)) & (ex13["year"].eq(latest_year))]
        keep = [
            "cmd_code",
            "supplier_ecosystem_class",
            "global_top_supplier_iso3",
            "global_top_supplier_share",
            "global_source_hhi",
            "is_commodity_outlier",
        ]
        latest = latest.merge(ex13[[c for c in keep if c in ex13.columns]].drop_duplicates("cmd_code"), on="cmd_code", how="left")
    latest = latest.merge(desc, on="cmd_code", how="left", suffixes=("", "_desc_map"))
    latest["product_description"] = latest["product_description"].fillna("")
    latest["supplier_ecosystem_class"] = latest.get("supplier_ecosystem_class", pd.Series(index=latest.index, dtype=object)).fillna(
        "not_in_exercise_13_top_products_table"
    )
    latest["rank"] = np.arange(1, len(latest) + 1)
    ordered = [
        "country",
        "iso3",
        "year",
        "rank",
        "cmd_code",
        "hs2",
        "hs4",
        "import_bin",
        "product_description",
        "import_value",
        "import_value_share",
        "top_supplier_iso3",
        "top_supplier_name",
        "within_product_top_supplier_share",
        "within_product_source_hhi",
        "supplier_count",
        "supplier_ecosystem_class",
        "global_top_supplier_iso3",
        "global_top_supplier_share",
        "global_source_hhi",
        "is_commodity_outlier",
    ]
    for col in ordered:
        if col not in latest.columns:
            latest[col] = np.nan
    return latest[ordered].reset_index(drop=True)


def make_supplier_threshold_summary(country: str, latest_year: int) -> pd.DataFrame:
    ex04 = pd.read_csv(EX04_IMPORTER_SUMMARY)
    ex04 = ex04[(ex04["iso3"].eq(country)) & (ex04["year"].eq(latest_year))].copy()
    if ex04.empty:
        raise RuntimeError(f"No Exercise 4 supplier summary found for {country} {latest_year}.")
    ex13 = pd.read_csv(EX13_LATEST_COUNTRY)
    ex13 = ex13[(ex13["iso3"].eq(country)) & (ex13["year"].eq(latest_year))].copy()
    pivot = ex13.pivot_table(index=["country", "iso3", "year"], columns="supplier_ecosystem_class", values="import_value_share", aggfunc="first")
    pivot = pivot.reset_index()
    pivot.columns = [
        f"ecosystem_{col}_share" if col not in {"country", "iso3", "year"} else col for col in pivot.columns
    ]
    out = ex04.merge(pivot, on=["country", "iso3", "year"], how="left")
    return out.reset_index(drop=True)


def add_period_summaries(hs2: pd.DataFrame, bec: pd.DataFrame, post_cutoff: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    def summarize(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
        work = df.copy()
        work["period"] = np.where(work["year"] < post_cutoff, f"pre_{post_cutoff}", f"{post_cutoff}_onward")
        out = (
            work.groupby(["period", group_col], as_index=False)
            .agg(
                median_gap_reduction_when_group_removed=("gap_reduction_when_group_removed", "median"),
                mean_gap_reduction_when_group_removed=("gap_reduction_when_group_removed", "mean"),
                mean_import_value_share=("import_value_share", "mean"),
                mean_export_value_share=("export_value_share", "mean"),
                years=("year", "nunique"),
            )
            .sort_values(["period", "median_gap_reduction_when_group_removed"], ascending=[True, False])
        )
        return out

    return summarize(hs2, "hs2"), summarize(bec, "import_bin")


def write_memo(
    country_exception: pd.DataFrame,
    gini_ts: pd.DataFrame,
    hs2_summary: pd.DataFrame,
    bec_summary: pd.DataFrame,
    supplier_threshold: pd.DataFrame,
    supplier_corridors: pd.DataFrame,
    commodity: pd.DataFrame,
    validations: dict[str, float],
    start_year: int,
    latest_year: int,
    post_cutoff: int,
) -> None:
    usa = country_exception[country_exception["iso3"].eq("USA")].iloc[0]
    latest_gap = gini_ts[gini_ts["year"].eq(latest_year)].iloc[0]
    supplier = supplier_threshold.iloc[0]
    diffuse_share = float(supplier.get("ecosystem_diffuse_share", np.nan))
    ecosystem_cols = [
        c for c in supplier_threshold.columns if c.startswith("ecosystem_") and c.endswith("_share")
    ]
    ecosystem_rows = pd.DataFrame(
        [
            {
                "class": col.removeprefix("ecosystem_").removesuffix("_share"),
                "value_share": float(supplier[col]),
            }
            for col in ecosystem_cols
            if pd.notna(supplier[col])
        ]
    ).sort_values("value_share", ascending=False)

    recent = gini_ts[gini_ts["year"].between(max(post_cutoff, latest_year - 7), latest_year)][
        [
            "year",
            "product_gini_imports",
            "product_gini_exports",
            "product_gini_gap_import_minus_export",
            "partner_gini_gap_import_minus_export",
        ]
    ].copy()

    hs2_pre = hs2_summary[hs2_summary["period"].eq(f"pre_{post_cutoff}")].head(8).copy()
    bec_pre = bec_summary[bec_summary["period"].eq(f"pre_{post_cutoff}")].head(8).copy()
    corridors = supplier_corridors.head(12).copy()
    corridors["product"] = corridors["product_description"].map(lambda x: short_text(x, 58))

    latest_comm = commodity[(commodity["year"].eq(latest_year)) & (commodity["sample"].eq("excluding_oil_gas_gold_coal"))].iloc[0]

    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    memo = f"""# US Import Concentration Puzzle

Generated: {generated}

This memo is a descriptive accounting package. The main object is aggregate HS6 product concentration: whether trade dollars are piled into a few product lines. Supplier concentration is supporting evidence only.

## Main Answer

The clean version of Tanush's hypothesis is not \"one major provider for each type of good.\" The data support a weaker and more defensible story:

> US imports have historically looked product-concentrated when a few very large demand categories dominate the receipt, and some of those categories have strong supplier corridors.

Feynman version: exports are the shelf where the US sells what it is unusually good at selling to the world. Imports are the receipt from a huge buyer. A few enormous receipt lines can make the whole import basket look concentrated even when most individual products are not single-sourced.

## The Puzzle

| Country | Years | Share import product Gini > export product Gini | Median gap | Latest year | Latest gap |
| --- | ---: | ---: | ---: | ---: | ---: |
"""
    for _, row in country_exception.iterrows():
        memo += (
            f"| {row['country']} | {int(row['observed_start_year'])}-{int(row['observed_end_year'])} "
            f"| {pct(row['share_years_import_product_gini_gt_export_product_gini'])} "
            f"| {num(row['median_import_minus_export_product_gini_gap'], 4, signed=True)} "
            f"| {int(row['latest_year'])} "
            f"| {num(row['latest_import_minus_export_product_gini_gap'], 4, signed=True)} |\n"
        )

    memo += f"""

For the US, the pattern is historical, not current. US import product Gini exceeded export product Gini in {pct(usa['share_years_import_product_gini_gt_export_product_gini'])} of observed years from {int(usa['observed_start_year'])}-{int(usa['observed_end_year'])}, with median gap {num(usa['median_import_minus_export_product_gini_gap'], 4, signed=True)}. In {latest_year}, the gap is {num(latest_gap['product_gini_gap_import_minus_export'], 4, signed=True)}, so exports are now slightly more product-concentrated.

## Recent US Timing

{markdown_table(recent, ['year', 'product_gini_imports', 'product_gini_exports', 'product_gini_gap_import_minus_export', 'partner_gini_gap_import_minus_export'], {'product_gini_imports': lambda x: num(x, 4), 'product_gini_exports': lambda x: num(x, 4), 'product_gini_gap_import_minus_export': lambda x: num(x, 4, signed=True), 'partner_gini_gap_import_minus_export': lambda x: num(x, 4, signed=True)})}

The product gap turns negative from {post_cutoff} onward in the current file, but the partner gap remains positive. Product concentration and partner concentration are answering different questions.

## Large-Category Diagnostics

Top pre-{post_cutoff} HS2 groups by median reduction in the import-minus-export product-Gini gap when removed:

{markdown_table(hs2_pre, ['hs2', 'median_gap_reduction_when_group_removed', 'mean_import_value_share', 'mean_export_value_share', 'years'], {'median_gap_reduction_when_group_removed': lambda x: num(x, 4, signed=True), 'mean_import_value_share': lambda x: pct(x), 'mean_export_value_share': lambda x: pct(x)})}

Top pre-{post_cutoff} BEC/import-bin groups by the same diagnostic:

{markdown_table(bec_pre, ['import_bin', 'median_gap_reduction_when_group_removed', 'mean_import_value_share', 'mean_export_value_share', 'years'], {'median_gap_reduction_when_group_removed': lambda x: num(x, 4, signed=True), 'mean_import_value_share': lambda x: pct(x), 'mean_export_value_share': lambda x: pct(x)})}

Reading rule: positive gap reduction means the group raises import product concentration relative to export product concentration. Negative values mean the group works the other way.

Commodity robustness in {latest_year}: after excluding HS4 {', '.join(sorted(COMMODITY_OUTLIER_HS4))}, the US import-minus-export product-Gini gap is {num(latest_comm['import_minus_export_product_gini_gap'], 4, signed=True)}. Removed value shares are {pct(latest_comm['removed_import_value_share'])} of imports and {pct(latest_comm['removed_export_value_share'])} of exports.

## Supplier-Corridor Evidence

The supplier data support the corridor part of the story, but not a broad single-source story.

| Check | {latest_year} US value |
| --- | ---: |
| Weighted top-supplier share | {pct(supplier['weighted_mean_top_supplier_share'])} |
| Median top-supplier share across HS6 products | {pct(supplier['median_top_supplier_share'])} |
| Import value with top supplier >= 50% | {pct(supplier['import_value_share_products_top_supplier_ge_50'])} |
| Import value with top supplier >= 75% | {pct(supplier['import_value_share_products_top_supplier_ge_75'])} |
| Import value with top supplier >= 90% | {pct(supplier['import_value_share_products_top_supplier_ge_90'])} |
| Exercise 13 diffuse share | {pct(diffuse_share)} |

Latest Exercise 13 ecosystem shares:

{markdown_table(ecosystem_rows, ['class', 'value_share'], {'value_share': lambda x: pct(x)})}

Top {latest_year} import product corridors:

{markdown_table(corridors, ['rank', 'cmd_code', 'product', 'import_value', 'top_supplier_iso3', 'within_product_top_supplier_share', 'supplier_ecosystem_class'], {'import_value': money_b, 'within_product_top_supplier_share': lambda x: pct(x)})}

## Interpretation

The better economic interpretation is a tug between export specialization and import demand lumps. The US export basket contains large categories such as aircraft, energy, pharma, machinery, semiconductors, agriculture, and capital goods. The US import basket contains huge demand categories such as oil and gas, vehicles, computing equipment, electronics, pharmaceuticals, medical goods, and intermediate inputs.

Historically, import demand lumps often dominated the US product-Gini comparison. From {post_cutoff} onward, in the current data, they do not. That is why any statement about the US exception should say historical, not current.

## Outputs And Validation

Tables are in `results/us_import_concentration_puzzle_tables/`.

Inputs:

- `data/processed/concentration_all_years.parquet`
- `data/processed/exercise_11_product_export_linkage_panel.parquet`
- `data/processed/exercise_12_export_aggregates.parquet`
- `results/exercise_04_tables/dominant_supplier_importer_summary.csv`
- `results/exercise_13_import_hypotheses_tables/`
- `data/processed/exercise_03_bec5_mapping_approved.csv`

Validation checks passed:

- Reconstructed import product Gini max absolute difference: {validations['max_import_gini_abs_diff']:.3g}
- Reconstructed export product Gini max absolute difference: {validations['max_export_gini_abs_diff']:.3g}
- Generated product-level tables exclude HS6 `999999`.

Limits:

- Goods-only HS merchandise trade; services are outside this package.
- HS6 codes are product categories, not firms or technologies.
- Supplier evidence is source-country evidence, not firm-supplier evidence.
- `Other Asia, nes` rows are not clean bilateral country corridors.
"""
    OUT_MEMO.write_text(memo, encoding="utf-8")


def write_manifest(args: argparse.Namespace, validations: dict[str, float], row_counts: dict[str, int]) -> None:
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "entrypoint": "scripts/run_us_import_concentration_puzzle.py",
        "arguments": vars(args),
        "excluded_hs6_codes": sorted(EXCLUDED_HS6_CODES),
        "commodity_outlier_hs4_codes": sorted(COMMODITY_OUTLIER_HS4),
        "validations": validations,
        "row_counts": row_counts,
        "outputs": {
            "memo": str(OUT_MEMO.relative_to(ROOT)),
            "tables_dir": str(OUT_TABLES.relative_to(ROOT)),
        },
    }
    (OUT_TABLES / "run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def run(args: argparse.Namespace) -> None:
    ensure_dirs()
    exact_map, cmd_map, desc = load_bec_mapping()
    concentration = load_concentration()

    country_exception = make_country_exception_summary(concentration)
    gini_ts = make_gini_gap_timeseries(concentration, args.country, args.start_year, args.latest_year, args.post_cutoff)
    import_products = load_import_products(args.country, args.start_year, args.latest_year)
    export_products = load_export_products(args.country, args.start_year, args.latest_year, exact_map, cmd_map)
    validations = validate_reconstructed_ginis(
        concentration,
        import_products,
        export_products,
        args.country,
        args.start_year,
        args.latest_year,
        tolerance=args.validation_tolerance,
    )

    hs2_loo = make_group_leave_one_out(import_products, export_products, "hs2", "hs2")
    bec_loo = make_group_leave_one_out(import_products, export_products, "import_bin", "import_bin")
    hs6_loo = make_hs6_leave_one_product_out(import_products, export_products, desc)
    commodity = make_commodity_outlier_robustness(import_products, export_products)
    supplier_corridors = make_supplier_corridors_latest(import_products, desc, args.country, args.latest_year, args.top_n)
    supplier_threshold = make_supplier_threshold_summary(args.country, args.latest_year)
    hs2_summary, bec_summary = add_period_summaries(hs2_loo, bec_loo, args.post_cutoff)

    outputs = {
        "country_exception_summary.csv": country_exception,
        "us_gini_gap_timeseries.csv": gini_ts,
        "us_hs2_leave_one_group_out.csv": hs2_loo,
        "us_bec_leave_one_group_out.csv": bec_loo,
        "us_hs6_leave_one_product_out.csv": hs6_loo,
        "us_commodity_outlier_robustness.csv": commodity,
        "us_supplier_corridors_latest.csv": supplier_corridors,
        "us_supplier_threshold_summary.csv": supplier_threshold,
        "us_hs2_period_summary.csv": hs2_summary,
        "us_bec_period_summary.csv": bec_summary,
    }

    for name, frame in outputs.items():
        assert_no_excluded_hs6(frame, name)
        frame.to_csv(OUT_TABLES / name, index=False)

    write_memo(
        country_exception,
        gini_ts,
        hs2_summary,
        bec_summary,
        supplier_threshold,
        supplier_corridors,
        commodity,
        validations,
        args.start_year,
        args.latest_year,
        args.post_cutoff,
    )
    row_counts = {name: int(len(frame)) for name, frame in outputs.items()}
    write_manifest(args, validations, row_counts)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country", default="USA", help="ISO3 country code to analyze.")
    parser.add_argument("--start-year", type=int, default=1991)
    parser.add_argument("--latest-year", type=int, default=2025)
    parser.add_argument("--post-cutoff", type=int, default=2018)
    parser.add_argument("--top-n", type=int, default=25)
    parser.add_argument("--validation-tolerance", type=float, default=1e-6)
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
