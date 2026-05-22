#!/usr/bin/env python3
"""Exercise 13: current-data tests for import concentration hypotheses.

The tests are descriptive. They use the existing country-HS6-source-year
aggregate import data and do not claim to prove firm-level mechanisms.
"""

from __future__ import annotations

import argparse
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_PROCESSED = ROOT / "data" / "processed"
RESULTS = ROOT / "results"

CELL_DIR = DATA_PROCESSED / "exercise_04_file_aggregates"
PRODUCT_PANEL = DATA_PROCESSED / "exercise_11_product_export_linkage_panel.parquet"
COUNTRY_PANEL = DATA_PROCESSED / "prof_p_country_panel.csv"
PARTNER_REF = ROOT / "data" / "raw" / "comtrade" / "partner_reference.csv"
BEC_MAPPING = DATA_PROCESSED / "exercise_03_bec5_mapping_approved.csv"

OUT_TABLES = RESULTS / "exercise_13_import_hypotheses_tables"
OUT_MEMO = RESULTS / "exercise_13_import_hypotheses.md"
OUT_CLASSIFIED_PANEL = DATA_PROCESSED / "exercise_13_supplier_ecosystem_panel.parquet"

COMMODITY_OUTLIER_HS4 = {"2701", "2709", "2710", "2711", "7108"}
TOP_NS = [1, 5, 10, 25, 100]
GLOBAL_DOMINANCE_THRESHOLD = 0.75
GLOBAL_HHI_THRESHOLD = 0.50
IMPORTER_DOMINANCE_THRESHOLD = 0.75
IMPORTER_HHI_THRESHOLD = 0.50
EXCLUDED_HS6_CODES = {"999999"}


@dataclass
class OLSResult:
    model_label: str
    sample: str
    outcome: str
    terms: list[str]
    beta: np.ndarray
    se: np.ndarray
    nobs: int
    clusters: int
    r2_within: float


def ensure_dirs() -> None:
    OUT_TABLES.mkdir(parents=True, exist_ok=True)


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def normalize_cmd(series: pd.Series) -> pd.Series:
    return series.astype(str).str.extract(r"(\d{1,6})", expand=False).str.zfill(6)


def drop_excluded_hs6(df: pd.DataFrame, code_col: str = "cmd_code") -> pd.DataFrame:
    if df.empty or code_col not in df.columns:
        return df
    mask = normalize_cmd(df[code_col]).isin(EXCLUDED_HS6_CODES)
    return df.loc[~mask].copy()


def hs2(series: pd.Series) -> pd.Series:
    return normalize_cmd(series).str[:2]


def hs4(series: pd.Series) -> pd.Series:
    return normalize_cmd(series).str[:4]


def asinh(values: pd.Series) -> pd.Series:
    return np.arcsinh(pd.to_numeric(values, errors="coerce").astype(float))


def standardize(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").astype(float)
    sd = values.std(ddof=0)
    if not np.isfinite(sd) or sd == 0:
        return values * np.nan
    return (values - values.mean()) / sd


def normal_pvalue(t_stat: float) -> float:
    if not np.isfinite(t_stat):
        return np.nan
    return math.erfc(abs(t_stat) / math.sqrt(2.0))


def gini(values: np.ndarray | pd.Series) -> float:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr) & (arr > 0)]
    if arr.size == 0:
        return np.nan
    arr.sort()
    n = arr.size
    total = arr.sum()
    if total <= 0:
        return np.nan
    ranks = np.arange(1, n + 1, dtype=float)
    return float((2 * np.sum(ranks * arr) / (n * total)) - ((n + 1) / n))


def gini_without_top(values: np.ndarray, top_indices: np.ndarray) -> float:
    keep = np.ones(values.size, dtype=bool)
    keep[top_indices] = False
    return gini(values[keep])


def loo_gini_contributions(values: np.ndarray) -> np.ndarray:
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


def hhi(values: np.ndarray | pd.Series) -> float:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr) & (arr > 0)]
    total = arr.sum()
    if total <= 0:
        return np.nan
    shares = arr / total
    return float(np.square(shares).sum())


def parse_year(path: Path) -> int:
    match = re.search(r"CA\d{3}(\d{4})", path.name)
    if not match:
        raise ValueError(f"Cannot parse year from {path.name}")
    return int(match.group(1))


def read_country_panel() -> pd.DataFrame:
    countries = pd.read_csv(COUNTRY_PANEL)
    countries["reporter_code"] = pd.to_numeric(countries["reporter_code"], errors="coerce").astype("Int64")
    return countries.dropna(subset=["reporter_code"]).astype({"reporter_code": int})


def read_partner_reference() -> pd.DataFrame:
    ref = pd.read_csv(PARTNER_REF)
    ref = ref[["partner_code", "partner_iso3", "partner_name"]].copy()
    ref["partner_code"] = pd.to_numeric(ref["partner_code"], errors="coerce")
    ref = ref.dropna(subset=["partner_code"])
    ref["partner_code"] = ref["partner_code"].astype(int)
    ref["partner_iso3"] = ref["partner_iso3"].fillna("").astype(str)
    ref["partner_name"] = ref["partner_name"].fillna("").astype(str)
    return ref


def read_product_descriptions() -> pd.DataFrame:
    if not BEC_MAPPING.exists():
        return pd.DataFrame(columns=["cmd_code", "product_description", "default_import_bin"])
    cols = ["cmd_code", "hs_desc_official", "hs_desc_if_available", "exercise_03_bin"]
    raw = pd.read_csv(BEC_MAPPING, usecols=lambda col: col in cols, dtype={"cmd_code": str})
    raw["cmd_code"] = normalize_cmd(raw["cmd_code"])
    raw = drop_excluded_hs6(raw)
    raw["product_description"] = raw.get("hs_desc_official", pd.Series(index=raw.index, dtype=object))
    if "hs_desc_if_available" in raw.columns:
        raw["product_description"] = raw["product_description"].fillna(raw["hs_desc_if_available"])
    raw["product_description"] = raw["product_description"].fillna("").astype(str).str.strip()
    raw["default_import_bin"] = raw.get("exercise_03_bin", "unmapped_or_ambiguous")
    raw["default_import_bin"] = raw["default_import_bin"].fillna("unmapped_or_ambiguous").astype(str)
    desc = (
        raw.groupby(["cmd_code", "product_description", "default_import_bin"], as_index=False)
        .size()
        .sort_values(["cmd_code", "size", "product_description"], ascending=[True, False, True])
        .groupby("cmd_code", as_index=False)
        .head(1)
    )
    return desc[["cmd_code", "product_description", "default_import_bin"]]


def read_product_panel() -> pd.DataFrame:
    columns = [
        "reporter_code",
        "year",
        "cmd_code",
        "import_bin",
        "import_value",
        "total_imports",
        "import_value_share",
        "top_supplier_code",
        "top_supplier_imports",
        "within_product_top_supplier_share",
        "within_product_source_hhi",
        "supplier_count",
        "loo_gini_contribution",
        "loo_partner_hhi_contribution",
        "top_supplier_iso3",
        "top_supplier_name",
        "country",
        "iso3",
    ]
    panel = pd.read_parquet(PRODUCT_PANEL, columns=columns)
    panel["cmd_code"] = normalize_cmd(panel["cmd_code"])
    panel = drop_excluded_hs6(panel)
    panel["hs2"] = panel["cmd_code"].str[:2]
    panel["hs4"] = panel["cmd_code"].str[:4]
    panel["is_commodity_outlier"] = panel["hs4"].isin(COMMODITY_OUTLIER_HS4)
    for col in [
        "reporter_code",
        "year",
        "top_supplier_code",
        "supplier_count",
        "import_value",
        "total_imports",
        "import_value_share",
        "top_supplier_imports",
        "within_product_top_supplier_share",
        "within_product_source_hhi",
        "loo_gini_contribution",
        "loo_partner_hhi_contribution",
    ]:
        panel[col] = pd.to_numeric(panel[col], errors="coerce")
    return panel.dropna(subset=["reporter_code", "year", "cmd_code", "import_value"]).copy()


def weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    mask = values.notna() & weights.notna() & (weights > 0)
    if not mask.any():
        return np.nan
    return float(np.average(values[mask], weights=weights[mask]))


def residualize_matrix(matrix: np.ndarray, fe_codes: list[np.ndarray], max_iter: int = 8) -> np.ndarray:
    out = matrix.astype(float, copy=True)
    for _ in range(max_iter):
        for codes in fe_codes:
            valid = codes >= 0
            if not valid.any():
                continue
            clean_codes = codes[valid]
            counts = np.bincount(clean_codes).astype(float)
            for col in range(out.shape[1]):
                sums = np.bincount(clean_codes, weights=out[valid, col], minlength=counts.size)
                means = np.divide(sums, counts, out=np.zeros_like(sums), where=counts > 0)
                out[valid, col] -= means[clean_codes]
    return out


def absorb_cluster_ols(
    df: pd.DataFrame,
    outcome: str,
    terms: list[str],
    fe_cols: list[str],
    cluster_col: str,
    model_label: str,
    sample: str,
) -> OLSResult:
    needed = [outcome, *terms, *fe_cols, cluster_col]
    work = df[needed].replace([np.inf, -np.inf], np.nan).dropna().copy()
    if work.empty:
        k = len(terms)
        return OLSResult(model_label, sample, outcome, terms, np.full(k, np.nan), np.full(k, np.nan), 0, 0, np.nan)
    yx = work[[outcome, *terms]].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    fe_codes = [pd.factorize(work[col], sort=False)[0].astype(np.int64) for col in fe_cols]
    resid = residualize_matrix(yx, fe_codes)
    y = resid[:, 0]
    x = resid[:, 1:]
    valid = np.isfinite(y) & np.isfinite(x).all(axis=1)
    y = y[valid]
    x = x[valid]
    clusters_raw = work.loc[valid, cluster_col]
    cluster_codes = pd.factorize(clusters_raw, sort=False)[0].astype(np.int64)
    nobs, k = x.shape
    clusters = int(cluster_codes.max() + 1) if nobs else 0
    if nobs <= k or k == 0:
        return OLSResult(model_label, sample, outcome, terms, np.full(k, np.nan), np.full(k, np.nan), nobs, clusters, np.nan)
    xtx_inv = np.linalg.pinv(x.T @ x)
    beta = xtx_inv @ (x.T @ y)
    err = y - x @ beta
    score = x * err[:, None]
    score_sums = np.vstack(
        [np.bincount(cluster_codes, weights=score[:, col], minlength=clusters) for col in range(k)]
    ).T
    meat = score_sums.T @ score_sums
    scale = 1.0
    if clusters > 1 and nobs > k:
        scale = (clusters / (clusters - 1)) * ((nobs - 1) / (nobs - k))
    cov = scale * xtx_inv @ meat @ xtx_inv
    se = np.sqrt(np.maximum(np.diag(cov), 0))
    tss = float(np.sum(np.square(y - y.mean())))
    rss = float(np.sum(np.square(err)))
    r2 = 1 - rss / tss if tss > 0 else np.nan
    return OLSResult(model_label, sample, outcome, terms, beta, se, nobs, clusters, r2)


def ols_results_to_frame(results: list[OLSResult]) -> pd.DataFrame:
    rows = []
    for result in results:
        for idx, term in enumerate(result.terms):
            coef = float(result.beta[idx])
            se = float(result.se[idx])
            t_stat = coef / se if se > 0 else np.nan
            rows.append(
                {
                    "sample": result.sample,
                    "model_label": result.model_label,
                    "outcome": result.outcome,
                    "term": term,
                    "coefficient": coef,
                    "std_error": se,
                    "t_stat": t_stat,
                    "p_value": normal_pvalue(t_stat),
                    "ci_low": coef - 1.96 * se if np.isfinite(se) else np.nan,
                    "ci_high": coef + 1.96 * se if np.isfinite(se) else np.nan,
                    "nobs": result.nobs,
                    "clusters": result.clusters,
                    "r2_within": result.r2_within,
                }
            )
    return pd.DataFrame(rows)


def add_top_supplier_lags(panel: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "reporter_code",
        "year",
        "cmd_code",
        "hs2",
        "hs4",
        "import_bin",
        "import_value",
        "top_supplier_code",
        "top_supplier_imports",
        "within_product_top_supplier_share",
        "within_product_source_hhi",
        "supplier_count",
        "country",
        "iso3",
        "is_commodity_outlier",
    ]
    work = panel[cols].copy()
    work = work.sort_values(["reporter_code", "cmd_code", "year"]).reset_index(drop=True)
    group = work.groupby(["reporter_code", "cmd_code"], sort=False)
    for col in [
        "year",
        "top_supplier_code",
        "within_product_top_supplier_share",
        "within_product_source_hhi",
        "supplier_count",
        "import_value",
    ]:
        work[f"lag_{col}"] = group[col].shift(1)
    work["has_calendar_lag"] = work["lag_year"].eq(work["year"] - 1)
    for col in [
        "top_supplier_code",
        "within_product_top_supplier_share",
        "within_product_source_hhi",
        "supplier_count",
        "import_value",
    ]:
        work.loc[~work["has_calendar_lag"], f"lag_{col}"] = np.nan

    previous_age = np.zeros(len(work), dtype=float)
    current_age = np.zeros(len(work), dtype=float)
    prev_key: tuple[int, str] | None = None
    prev_year = None
    prev_supplier = None
    prev_run_age = 0.0
    for idx, row in enumerate(work[["reporter_code", "cmd_code", "year", "top_supplier_code"]].itertuples(index=False)):
        key = (int(row.reporter_code), str(row.cmd_code))
        supplier = row.top_supplier_code
        if key == prev_key and prev_year == row.year - 1 and supplier == prev_supplier:
            age = prev_run_age + 1.0
            previous_age[idx] = prev_run_age
        else:
            age = 1.0
            previous_age[idx] = np.nan
        current_age[idx] = age
        prev_key = key
        prev_year = row.year
        prev_supplier = supplier
        prev_run_age = age
    work["top_supplier_run_age"] = current_age
    work["lag_top_supplier_run_age"] = previous_age
    work.loc[~work["has_calendar_lag"], "lag_top_supplier_run_age"] = np.nan
    work["same_top_supplier"] = (
        work["has_calendar_lag"] & work["top_supplier_code"].eq(work["lag_top_supplier_code"])
    ).astype(int)
    work["log_import_value"] = np.log1p(work["import_value"])
    work["log_lag_import_value"] = np.log1p(work["lag_import_value"])
    work["log_lag_top_supplier_run_age"] = np.log1p(work["lag_top_supplier_run_age"])
    work["log_supplier_count"] = np.log1p(work["supplier_count"])
    work["log_lag_supplier_count"] = np.log1p(work["lag_supplier_count"])
    for col in [
        "within_product_top_supplier_share",
        "within_product_source_hhi",
        "log_import_value",
        "log_lag_import_value",
        "lag_within_product_top_supplier_share",
        "lag_within_product_source_hhi",
        "log_lag_top_supplier_run_age",
        "log_lag_supplier_count",
    ]:
        work[f"{col}_z"] = standardize(work[col])
    work["reporter_product_fe"] = work["reporter_code"].astype(str) + "_" + work["cmd_code"].astype(str)
    work["lag_product_source_fe"] = work["cmd_code"].astype(str) + "_" + work["lag_top_supplier_code"].fillna(-1).astype(int).astype(str)
    work["reporter_year_fe"] = work["reporter_code"].astype(str) + "_" + work["year"].astype(str)
    work["hs2_year_fe"] = work["hs2"].astype(str) + "_" + work["year"].astype(str)
    return work


def summarise_h1(persist: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    lagged = persist[persist["has_calendar_lag"]].copy()
    lagged["lag_top_share_ge_75"] = lagged["lag_within_product_top_supplier_share"] >= IMPORTER_DOMINANCE_THRESHOLD

    def summarize(frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
        if frame.empty:
            return pd.DataFrame()
        grouped = frame.groupby(keys, dropna=False)
        rows = grouped.apply(
            lambda g: pd.Series(
                {
                    "rows": len(g),
                    "same_top_supplier_rate": float(g["same_top_supplier"].mean()),
                    "import_value_weighted_same_top_supplier_rate": weighted_mean(g["same_top_supplier"], g["import_value"]),
                    "median_lag_top_supplier_share": float(g["lag_within_product_top_supplier_share"].median()),
                    "median_lag_top_supplier_age": float(g["lag_top_supplier_run_age"].median()),
                    "share_lag_top_supplier_ge_75": float(g["lag_top_share_ge_75"].mean()),
                    "current_top_import_value_share_when_same": float(
                        g.loc[g["same_top_supplier"].eq(1), "top_supplier_imports"].sum() / g["top_supplier_imports"].sum()
                    )
                    if g["top_supplier_imports"].sum() > 0
                    else np.nan,
                }
            ),
            include_groups=False,
        )
        return rows.reset_index()

    overall = summarize(lagged.assign(sample="all"), ["sample"])
    by_bin = summarize(lagged, ["import_bin"])
    by_outlier = summarize(
        lagged.assign(sample=np.where(lagged["is_commodity_outlier"], "commodity_outliers", "excluding_oil_gas_gold_coal")),
        ["sample"],
    )

    regression_terms = [
        "lag_within_product_top_supplier_share_z",
        "lag_within_product_source_hhi_z",
        "log_lag_import_value_z",
        "log_lag_top_supplier_run_age_z",
        "log_lag_supplier_count_z",
    ]
    regressions: list[OLSResult] = []
    for label, frame in [
        ("all_products", lagged),
        ("excluding_oil_gas_gold_coal", lagged[~lagged["is_commodity_outlier"]]),
    ]:
        regressions.append(
            absorb_cluster_ols(
                frame,
                "same_top_supplier",
                regression_terms,
                ["reporter_product_fe", "lag_product_source_fe", "reporter_year_fe", "hs2_year_fe"],
                "reporter_code",
                "h1_top_supplier_persistence_lpm",
                label,
            )
        )
        regressions.append(
            absorb_cluster_ols(
                frame,
                "within_product_top_supplier_share",
                regression_terms,
                ["reporter_product_fe", "lag_product_source_fe", "reporter_year_fe", "hs2_year_fe"],
                "reporter_code",
                "h1_current_top_share",
                label,
            )
        )

    market = persist.copy()
    market_terms = ["log_import_value_z"]
    market_regressions: list[OLSResult] = []
    for label, frame in [
        ("all_products", market),
        ("excluding_oil_gas_gold_coal", market[~market["is_commodity_outlier"]]),
    ]:
        for outcome in ["within_product_top_supplier_share", "within_product_source_hhi", "log_supplier_count"]:
            market_regressions.append(
                absorb_cluster_ols(
                    frame,
                    outcome,
                    market_terms,
                    ["reporter_product_fe", "reporter_year_fe", "hs2_year_fe"],
                    "reporter_code",
                    f"h1_market_size_{outcome}",
                    label,
                )
            )

    return overall, by_bin, by_outlier, ols_results_to_frame(regressions + market_regressions)


def summarise_h1_hs2(panel: pd.DataFrame) -> pd.DataFrame:
    work = panel.copy()
    work["weighted_top_share_component"] = work["import_value"] * work["within_product_top_supplier_share"]
    work["weighted_hhi_component"] = work["import_value"] * work["within_product_source_hhi"]
    hs2_panel = (
        work.groupby(["reporter_code", "country", "iso3", "year", "hs2"], as_index=False)
        .agg(
            import_value=("import_value", "sum"),
            weighted_top_supplier_share_numer=("weighted_top_share_component", "sum"),
            weighted_source_hhi_numer=("weighted_hhi_component", "sum"),
            active_hs6=("cmd_code", "nunique"),
            commodity_outlier_share=("is_commodity_outlier", "mean"),
        )
    )
    hs2_panel["weighted_top_supplier_share"] = hs2_panel["weighted_top_supplier_share_numer"] / hs2_panel["import_value"]
    hs2_panel["weighted_source_hhi"] = hs2_panel["weighted_source_hhi_numer"] / hs2_panel["import_value"]
    hs2_panel["log_import_value"] = np.log1p(hs2_panel["import_value"])
    hs2_panel["log_active_hs6"] = np.log1p(hs2_panel["active_hs6"])
    hs2_panel["log_import_value_z"] = standardize(hs2_panel["log_import_value"])
    hs2_panel["reporter_hs2_fe"] = hs2_panel["reporter_code"].astype(str) + "_" + hs2_panel["hs2"].astype(str)
    hs2_panel["reporter_year_fe"] = hs2_panel["reporter_code"].astype(str) + "_" + hs2_panel["year"].astype(str)
    hs2_panel["hs2_year_fe"] = hs2_panel["hs2"].astype(str) + "_" + hs2_panel["year"].astype(str)
    results = []
    for outcome in ["weighted_top_supplier_share", "weighted_source_hhi", "log_active_hs6"]:
        results.append(
            absorb_cluster_ols(
                hs2_panel,
                outcome,
                ["log_import_value_z"],
                ["reporter_hs2_fe", "reporter_year_fe", "hs2_year_fe"],
                "reporter_code",
                f"h1_hs2_market_size_{outcome}",
                "hs2_weighted_robustness",
            )
        )
    return ols_results_to_frame(results)


def read_cell_file(path: Path) -> pd.DataFrame:
    cells = pd.read_parquet(path, columns=["reporter_code", "year", "cmd_code", "partner_code", "trade_value"])
    cells["cmd_code"] = normalize_cmd(cells["cmd_code"])
    cells = drop_excluded_hs6(cells)
    for col in ["reporter_code", "year", "partner_code", "trade_value"]:
        cells[col] = pd.to_numeric(cells[col], errors="coerce")
    cells = cells.dropna(subset=["reporter_code", "year", "cmd_code", "partner_code", "trade_value"])
    cells = cells[cells["trade_value"] > 0].copy()
    cells["reporter_code"] = cells["reporter_code"].astype(int)
    cells["year"] = cells["year"].astype(int)
    cells["partner_code"] = cells["partner_code"].astype(int)
    return cells


def compute_partner_hhi_without(partner_totals: pd.Series, removals: pd.DataFrame, total: float) -> float:
    remaining = partner_totals.copy()
    remove_by_partner = removals.groupby("partner_code")["trade_value"].sum()
    remaining.loc[remove_by_partner.index] = remaining.reindex(remove_by_partner.index).fillna(0) - remove_by_partner
    remaining = remaining[remaining > 0]
    return hhi(remaining.to_numpy(dtype=float))


def compute_cell_granularity(
    path: Path,
    countries: pd.DataFrame,
    partner_names: pd.DataFrame,
    desc: pd.DataFrame,
) -> tuple[dict[str, float | int | str], pd.DataFrame]:
    cells = read_cell_file(path)
    if cells.empty:
        return {}, pd.DataFrame()
    reporter_code = int(cells["reporter_code"].iloc[0])
    year = int(cells["year"].iloc[0])
    metadata = countries[countries["reporter_code"].eq(reporter_code)].head(1)
    country = str(metadata["country"].iloc[0]) if not metadata.empty else str(reporter_code)
    iso3 = str(metadata["iso3"].iloc[0]) if not metadata.empty else ""

    cells = cells.groupby(["reporter_code", "year", "cmd_code", "partner_code"], as_index=False)["trade_value"].sum()
    total = float(cells["trade_value"].sum())
    values = cells["trade_value"].to_numpy(dtype=float)
    order_desc = np.argsort(-values, kind="mergesort")
    partner_totals = cells.groupby("partner_code")["trade_value"].sum()
    full_gini = gini(values)
    full_partner_hhi = hhi(partner_totals)
    loo_gini = loo_gini_contributions(values)
    partner_total_for_cell = cells["partner_code"].map(partner_totals).to_numpy(dtype=float)
    sumsq = float(np.square(partner_totals.to_numpy(dtype=float)).sum())
    x = values
    numerator_without = sumsq - np.square(partner_total_for_cell) + np.square(partner_total_for_cell - x)
    denom_without = np.square(total - x)
    hhi_without_cell = np.where(denom_without > 0, numerator_without / denom_without, np.nan)
    loo_partner_hhi = full_partner_hhi - hhi_without_cell

    summary: dict[str, float | int | str] = {
        "reporter_code": reporter_code,
        "country": country,
        "iso3": iso3,
        "year": year,
        "total_imports": total,
        "active_product_partner_cells": int(len(cells)),
        "product_partner_cell_gini": full_gini,
        "partner_hhi": full_partner_hhi,
    }
    for n in TOP_NS:
        n_eff = min(n, len(cells))
        top_idx = order_desc[:n_eff]
        top_value = float(values[top_idx].sum())
        summary[f"top_{n}_cell_share"] = top_value / total if total > 0 else np.nan
        without_gini = gini_without_top(values, top_idx)
        without_partner_hhi = compute_partner_hhi_without(partner_totals, cells.iloc[top_idx], total)
        summary[f"gini_without_top_{n}_cells"] = without_gini
        summary[f"gini_reduction_top_{n}_cells"] = full_gini - without_gini
        summary[f"partner_hhi_without_top_{n}_cells"] = without_partner_hhi
        summary[f"partner_hhi_reduction_top_{n}_cells"] = full_partner_hhi - without_partner_hhi

    cells["cell_rank"] = cells["trade_value"].rank(method="first", ascending=False).astype(int)
    cells["cell_value_share"] = cells["trade_value"] / total
    cells["loo_cell_gini_contribution"] = loo_gini
    cells["loo_cell_partner_hhi_contribution"] = loo_partner_hhi
    cells["hs2"] = cells["cmd_code"].str[:2]
    cells["hs4"] = cells["cmd_code"].str[:4]
    cells["is_commodity_outlier"] = cells["hs4"].isin(COMMODITY_OUTLIER_HS4)
    top_by_value = cells.sort_values(["trade_value", "cmd_code", "partner_code"], ascending=[False, True, True]).head(100)
    top_by_loo = cells.sort_values(["loo_cell_gini_contribution", "trade_value"], ascending=[False, False]).head(100)
    top = pd.concat([top_by_value, top_by_loo], ignore_index=True).drop_duplicates(["cmd_code", "partner_code"])
    top = top.merge(partner_names, on="partner_code", how="left")
    top = top.merge(desc, on="cmd_code", how="left")
    top["country"] = country
    top["iso3"] = iso3
    top = top[
        [
            "reporter_code",
            "country",
            "iso3",
            "year",
            "cmd_code",
            "product_description",
            "default_import_bin",
            "hs2",
            "partner_code",
            "partner_iso3",
            "partner_name",
            "trade_value",
            "cell_value_share",
            "cell_rank",
            "loo_cell_gini_contribution",
            "loo_cell_partner_hhi_contribution",
            "is_commodity_outlier",
        ]
    ]
    return summary, top


def cell_persistence(top_cells: pd.DataFrame) -> pd.DataFrame:
    records = []
    if top_cells.empty:
        return pd.DataFrame()
    value_top = top_cells[top_cells["cell_rank"] <= 100].copy()
    for iso3, group in value_top.groupby("iso3"):
        by_year = {int(year): df for year, df in group.groupby("year")}
        for year in sorted(by_year):
            prev = by_year.get(year - 1)
            if prev is None:
                continue
            curr = by_year[year]
            row = {
                "iso3": iso3,
                "country": curr["country"].iloc[0],
                "year": year,
            }
            for n in [10, 25, 100]:
                curr_set = set(zip(curr[curr["cell_rank"] <= n]["cmd_code"], curr[curr["cell_rank"] <= n]["partner_code"]))
                prev_set = set(zip(prev[prev["cell_rank"] <= n]["cmd_code"], prev[prev["cell_rank"] <= n]["partner_code"]))
                if not curr_set or not prev_set:
                    row[f"top_{n}_jaccard_vs_previous_year"] = np.nan
                    row[f"top_{n}_share_also_top_previous_year"] = np.nan
                else:
                    row[f"top_{n}_jaccard_vs_previous_year"] = len(curr_set & prev_set) / len(curr_set | prev_set)
                    row[f"top_{n}_share_also_top_previous_year"] = len(curr_set & prev_set) / len(curr_set)
            records.append(row)
    return pd.DataFrame(records)


def run_h4_cell_granularity(countries: pd.DataFrame, partner_ref: pd.DataFrame, desc: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    files = sorted(CELL_DIR.glob("*.parquet"))
    summaries = []
    top_frames = []
    partner_names = partner_ref[["partner_code", "partner_iso3", "partner_name"]]
    for idx, path in enumerate(files, start=1):
        summary, top = compute_cell_granularity(path, countries, partner_names, desc)
        if summary:
            summaries.append(summary)
        if not top.empty:
            top_frames.append(top)
        if idx % 100 == 0:
            print(f"processed cell granularity {idx}/{len(files)} files", flush=True)
    country_year = pd.DataFrame(summaries).sort_values(["country", "year"]).reset_index(drop=True)
    top_cells = pd.concat(top_frames, ignore_index=True) if top_frames else pd.DataFrame()
    latest_years = country_year.groupby("iso3")["year"].max().rename("latest_year").reset_index()
    latest_top = top_cells.merge(latest_years, on="iso3", how="inner")
    latest_top = latest_top[latest_top["year"].eq(latest_top["latest_year"])].drop(columns=["latest_year"])
    latest_top = (
        latest_top.sort_values(["iso3", "cell_rank", "loo_cell_gini_contribution"], ascending=[True, True, False])
        .groupby("iso3", as_index=False)
        .head(50)
        .reset_index(drop=True)
    )
    persistence = cell_persistence(top_cells)
    return country_year, latest_top, persistence


def run_h4_product_granularity(panel: pd.DataFrame, desc: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    work = panel.copy()
    work["positive_loo_gini"] = work["loo_gini_contribution"].clip(lower=0)
    work["positive_loo_partner_hhi"] = work["loo_partner_hhi_contribution"].clip(lower=0)
    country_year = (
        work.groupby(["reporter_code", "country", "iso3", "year"], as_index=False)
        .apply(
            lambda g: pd.Series(
                {
                    "total_imports": float(g["import_value"].sum()),
                    "active_products": int(g["cmd_code"].nunique()),
                    "top_1_product_share": float(g.nlargest(1, "import_value")["import_value"].sum() / g["import_value"].sum()),
                    "top_5_product_share": float(g.nlargest(5, "import_value")["import_value"].sum() / g["import_value"].sum()),
                    "top_10_product_share": float(g.nlargest(10, "import_value")["import_value"].sum() / g["import_value"].sum()),
                    "top_25_product_share": float(g.nlargest(25, "import_value")["import_value"].sum() / g["import_value"].sum()),
                    "top_10_positive_loo_gini_contribution": float(g.nlargest(10, "positive_loo_gini")["positive_loo_gini"].sum()),
                    "top_10_positive_loo_partner_hhi_contribution": float(
                        g.nlargest(10, "positive_loo_partner_hhi")["positive_loo_partner_hhi"].sum()
                    ),
                    "commodity_outlier_import_share": float(
                        g.loc[g["is_commodity_outlier"], "import_value"].sum() / g["import_value"].sum()
                    ),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )
    latest_years = work.groupby("iso3")["year"].max().rename("latest_year").reset_index()
    latest_top = work.merge(latest_years, on="iso3", how="inner")
    latest_top = latest_top[latest_top["year"].eq(latest_top["latest_year"])].copy()
    latest_top["product_rank"] = latest_top.groupby("iso3")["import_value"].rank(method="first", ascending=False).astype(int)
    latest_top = latest_top[latest_top["product_rank"] <= 30]
    latest_top = latest_top.merge(desc[["cmd_code", "product_description"]], on="cmd_code", how="left")
    latest_top = latest_top[
        [
            "country",
            "iso3",
            "year",
            "cmd_code",
            "product_description",
            "import_bin",
            "product_rank",
            "import_value",
            "import_value_share",
            "loo_gini_contribution",
            "loo_partner_hhi_contribution",
            "top_supplier_iso3",
            "within_product_top_supplier_share",
            "is_commodity_outlier",
        ]
    ].sort_values(["country", "product_rank"])
    return country_year, latest_top.reset_index(drop=True)


def build_global_source_metrics(partner_ref: pd.DataFrame) -> pd.DataFrame:
    country_partner_codes = set(
        partner_ref.loc[
            partner_ref["partner_iso3"].str.len().eq(3) & ~partner_ref["partner_iso3"].str.startswith("_"),
            "partner_code",
        ].astype(int)
    )
    files = sorted(CELL_DIR.glob("*.parquet"))
    years = sorted({parse_year(path) for path in files})
    outputs = []
    for year in years:
        frames = []
        for path in [p for p in files if parse_year(p) == year]:
            cells = read_cell_file(path)
            cells = cells[cells["partner_code"].isin(country_partner_codes)]
            if not cells.empty:
                frames.append(cells[["year", "cmd_code", "partner_code", "trade_value"]])
        if not frames:
            continue
        all_year = pd.concat(frames, ignore_index=True)
        by_source = all_year.groupby(["year", "cmd_code", "partner_code"], as_index=False)["trade_value"].sum()
        totals = by_source.groupby(["year", "cmd_code"], as_index=False)["trade_value"].sum().rename(columns={"trade_value": "global_product_imports"})
        shares = by_source.merge(totals, on=["year", "cmd_code"], how="left")
        shares["global_source_share"] = shares["trade_value"] / shares["global_product_imports"]
        global_hhi = shares.groupby(["year", "cmd_code"], as_index=False).agg(
            global_source_hhi=("global_source_share", lambda s: float(np.square(s.to_numpy(dtype=float)).sum())),
            global_supplier_count=("partner_code", "nunique"),
        )
        top = (
            shares.sort_values(["year", "cmd_code", "trade_value", "partner_code"], ascending=[True, True, False, True])
            .groupby(["year", "cmd_code"], as_index=False)
            .head(1)
            .rename(
                columns={
                    "partner_code": "global_top_supplier_code",
                    "trade_value": "global_top_supplier_imports",
                    "global_source_share": "global_top_supplier_share",
                }
            )
        )
        metrics = totals.merge(global_hhi, on=["year", "cmd_code"], how="left").merge(
            top[
                [
                    "year",
                    "cmd_code",
                    "global_top_supplier_code",
                    "global_top_supplier_imports",
                    "global_top_supplier_share",
                ]
            ],
            on=["year", "cmd_code"],
            how="left",
        )
        outputs.append(metrics)
        print(f"built global source metrics for {year}", flush=True)
    out = pd.concat(outputs, ignore_index=True)
    out = out.merge(
        partner_ref.rename(
            columns={
                "partner_code": "global_top_supplier_code",
                "partner_iso3": "global_top_supplier_iso3",
                "partner_name": "global_top_supplier_name",
            }
        ),
        on="global_top_supplier_code",
        how="left",
    )
    return out


def classify_supplier_ecosystems(panel: pd.DataFrame, global_metrics: pd.DataFrame, desc: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    cols = [
        "reporter_code",
        "country",
        "iso3",
        "year",
        "cmd_code",
        "hs2",
        "hs4",
        "import_bin",
        "import_value",
        "import_value_share",
        "top_supplier_code",
        "top_supplier_iso3",
        "top_supplier_name",
        "within_product_top_supplier_share",
        "within_product_source_hhi",
        "supplier_count",
        "is_commodity_outlier",
    ]
    work = panel[cols].merge(global_metrics, on=["year", "cmd_code"], how="left")
    work["top_supplier_is_country"] = work["top_supplier_iso3"].fillna("").str.len().eq(3) & ~work["top_supplier_iso3"].fillna("").str.startswith("_")
    work["importer_concentrated"] = (
        work["within_product_top_supplier_share"].ge(IMPORTER_DOMINANCE_THRESHOLD)
        | work["within_product_source_hhi"].ge(IMPORTER_HHI_THRESHOLD)
    )
    work["global_concentrated"] = (
        work["global_top_supplier_share"].ge(GLOBAL_DOMINANCE_THRESHOLD)
        | work["global_source_hhi"].ge(GLOBAL_HHI_THRESHOLD)
    )
    same_global_top = work["top_supplier_code"].eq(work["global_top_supplier_code"])
    classification = np.select(
        [
            ~work["top_supplier_is_country"],
            work["importer_concentrated"] & work["global_concentrated"] & same_global_top,
            work["importer_concentrated"] & work["global_concentrated"] & ~same_global_top,
            work["importer_concentrated"] & ~work["global_concentrated"],
            ~work["importer_concentrated"] & work["global_concentrated"],
        ],
        [
            "non_country_top_supplier",
            "global_dominant",
            "global_concentrated_other_source",
            "economy_specific",
            "global_but_importer_diffuse",
        ],
        default="diffuse",
    )
    work["supplier_ecosystem_class"] = classification
    work.to_parquet(OUT_CLASSIFIED_PANEL, index=False)

    def share_summary(frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
        grouped = frame.groupby(keys + ["supplier_ecosystem_class"], as_index=False).agg(
            import_value=("import_value", "sum"),
            product_rows=("cmd_code", "count"),
        )
        totals = frame.groupby(keys, as_index=False)["import_value"].sum().rename(columns={"import_value": "total_import_value"})
        grouped = grouped.merge(totals, on=keys, how="left")
        grouped["import_value_share"] = grouped["import_value"] / grouped["total_import_value"]
        return grouped

    country_year = share_summary(work, ["country", "iso3", "year"])
    by_bin = share_summary(work, ["import_bin"])
    by_hs2 = share_summary(work, ["hs2"])
    excluding_outliers = share_summary(work[~work["is_commodity_outlier"]], ["country", "iso3", "year"])

    latest_years = work.groupby("iso3")["year"].max().rename("latest_year").reset_index()
    latest = work.merge(latest_years, on="iso3", how="inner")
    latest = latest[latest["year"].eq(latest["latest_year"])].drop(columns=["latest_year"])
    latest_country = share_summary(latest, ["country", "iso3", "year"])
    latest_top_products = (
        latest.sort_values(["supplier_ecosystem_class", "import_value"], ascending=[True, False])
        .groupby("supplier_ecosystem_class", as_index=False)
        .head(40)
        .merge(desc[["cmd_code", "product_description"]], on="cmd_code", how="left")
    )
    latest_top_products = latest_top_products[
        [
            "supplier_ecosystem_class",
            "country",
            "iso3",
            "year",
            "cmd_code",
            "product_description",
            "import_bin",
            "import_value",
            "import_value_share",
            "top_supplier_iso3",
            "within_product_top_supplier_share",
            "global_top_supplier_iso3",
            "global_top_supplier_share",
            "global_source_hhi",
            "is_commodity_outlier",
        ]
    ]
    summaries = {
        "country_year": country_year,
        "by_bin": by_bin,
        "by_hs2": by_hs2,
        "excluding_outliers_country_year": excluding_outliers,
        "latest_country": latest_country,
        "latest_top_products": latest_top_products,
    }
    return work, summaries


def write_tables(
    h1_overall: pd.DataFrame,
    h1_by_bin: pd.DataFrame,
    h1_by_outlier: pd.DataFrame,
    h1_models: pd.DataFrame,
    h1_hs2_models: pd.DataFrame,
    h4_cell_country_year: pd.DataFrame,
    h4_latest_top_cells: pd.DataFrame,
    h4_cell_persistence: pd.DataFrame,
    h4_product_country_year: pd.DataFrame,
    h4_latest_products: pd.DataFrame,
    global_metrics: pd.DataFrame,
    h2_summaries: dict[str, pd.DataFrame],
) -> None:
    outputs = {
        "h1_top_supplier_persistence_overall.csv": h1_overall,
        "h1_top_supplier_persistence_by_bin.csv": h1_by_bin,
        "h1_top_supplier_persistence_by_outlier.csv": h1_by_outlier,
        "h1_fixed_cost_sourcing_models.csv": h1_models,
        "h1_hs2_market_size_models.csv": h1_hs2_models,
        "h4_cell_granularity_country_year.csv": h4_cell_country_year,
        "h4_top_cells_latest.csv": h4_latest_top_cells,
        "h4_cell_persistence_country_year.csv": h4_cell_persistence,
        "h4_product_granularity_country_year.csv": h4_product_country_year,
        "h4_top_products_latest.csv": h4_latest_products,
        "h2_global_source_metrics.csv": global_metrics,
        "h2_supplier_ecosystem_country_year.csv": h2_summaries["country_year"],
        "h2_supplier_ecosystem_by_bin.csv": h2_summaries["by_bin"],
        "h2_supplier_ecosystem_by_hs2.csv": h2_summaries["by_hs2"],
        "h2_supplier_ecosystem_excluding_outliers_country_year.csv": h2_summaries["excluding_outliers_country_year"],
        "h2_supplier_ecosystem_latest_country.csv": h2_summaries["latest_country"],
        "h2_supplier_ecosystem_top_products_latest.csv": h2_summaries["latest_top_products"],
    }
    for name, frame in outputs.items():
        frame.to_csv(OUT_TABLES / name, index=False)


def markdown_table(frame: pd.DataFrame, max_rows: int = 8) -> str:
    if frame.empty:
        return "No rows."
    return frame.head(max_rows).to_markdown(index=False, floatfmt=".4f")


def write_memo(
    h1_overall: pd.DataFrame,
    h1_by_bin: pd.DataFrame,
    h1_by_outlier: pd.DataFrame,
    h1_models: pd.DataFrame,
    h4_cell_country_year: pd.DataFrame,
    h4_cell_persistence: pd.DataFrame,
    h4_product_country_year: pd.DataFrame,
    h2_summaries: dict[str, pd.DataFrame],
) -> None:
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    latest_h2 = h2_summaries["latest_country"]
    h2_latest_wide = latest_h2.pivot_table(
        index=["country", "iso3", "year"],
        columns="supplier_ecosystem_class",
        values="import_value_share",
        fill_value=0,
    ).reset_index()
    for col in [
        "global_dominant",
        "economy_specific",
        "global_concentrated_other_source",
        "diffuse",
        "non_country_top_supplier",
    ]:
        if col not in h2_latest_wide.columns:
            h2_latest_wide[col] = 0.0
    h2_latest_wide["dominant_or_economy_specific"] = (
        h2_latest_wide["global_dominant"]
        + h2_latest_wide["economy_specific"]
        + h2_latest_wide["global_concentrated_other_source"]
    )
    h2_medians = h2_latest_wide[
        [
            "global_dominant",
            "economy_specific",
            "global_concentrated_other_source",
            "diffuse",
            "non_country_top_supplier",
            "dominant_or_economy_specific",
        ]
    ].median().rename_axis("class").reset_index(name="latest_country_median_share")

    h4_cell_medians = h4_cell_country_year[
        [
            "top_1_cell_share",
            "top_5_cell_share",
            "top_10_cell_share",
            "top_25_cell_share",
            "gini_reduction_top_10_cells",
            "partner_hhi_reduction_top_10_cells",
        ]
    ].median().rename_axis("measure").reset_index(name="median")
    h4_product_medians = h4_product_country_year[
        [
            "top_1_product_share",
            "top_5_product_share",
            "top_10_product_share",
            "top_25_product_share",
            "top_10_positive_loo_gini_contribution",
            "top_10_positive_loo_partner_hhi_contribution",
        ]
    ].median().rename_axis("measure").reset_index(name="median")
    model_focus = h1_models[
        h1_models["term"].isin(
            [
                "lag_within_product_top_supplier_share_z",
                "log_lag_top_supplier_run_age_z",
                "log_import_value_z",
            ]
        )
        & h1_models["r2_within"].notna()
    ][["sample", "model_label", "outcome", "term", "coefficient", "std_error", "nobs", "r2_within"]]

    lines = [
        "# Exercise 13: Import Concentration Hypothesis Tests",
        "",
        f"Generated: {generated}",
        "",
        "This memo implements current-data tests for three hypotheses: fixed-cost sourcing, granular product-source corridors, and dominant supplier ecosystems. It uses country-HS6-source-year aggregate import data, not firm customs records, so firm-level conclusions are suggestive.",
        "",
        "## Coverage",
        "",
        f"- Product-level importer-HS6-year rows: {int(h4_product_country_year['active_products'].sum()):,} product-country-year observations across country-years",
        f"- Product-partner-cell country-year rows: {len(h4_cell_country_year):,}",
        f"- Classified supplier-ecosystem panel: `{rel(OUT_CLASSIFIED_PANEL)}`",
        f"- Tables: `{rel(OUT_TABLES)}/`",
        "",
        "## H1: Fixed-Cost Sourcing Proxy",
        "",
        "This test asks whether top source relationships are persistent and whether product-market scale mainly deepens incumbent sourcing instead of diffusing sources. It proxies firm-level fixed-cost sourcing with importer-HS6 top-source persistence.",
        "",
        "### Top Supplier Persistence",
        "",
        markdown_table(h1_overall),
        "",
        "### Persistence By Import Bin",
        "",
        markdown_table(h1_by_bin),
        "",
        "### Outlier Robustness",
        "",
        markdown_table(h1_by_outlier),
        "",
        "### Selected Fixed-Effect Model Coefficients",
        "",
        markdown_table(model_focus, max_rows=16),
        "",
        "The saturated LPM for `same_top_supplier` is retained in the CSV for transparency, but its selected fixed effects absorb the usable binary variation. The descriptive persistence rates and the current-share model are the primary current-data evidence for top-source survival.",
        "",
        "Interpretation rule: positive lag-share and age coefficients support sticky sourcing relationships; positive market-size effects on top share/source HHI with weak supplier-count expansion support scale through incumbents.",
        "",
        "## H4: Granular Product-Source Corridors",
        "",
        "This test asks whether a small set of product-source cells accounts for a large share of import value and concentration. It is a corridor-level proxy; it does not observe firms.",
        "",
        "### Cell-Level Median Summary",
        "",
        markdown_table(h4_cell_medians),
        "",
        "### Product-Level Median Summary",
        "",
        markdown_table(h4_product_medians),
        "",
        "### Top-Cell Persistence",
        "",
        markdown_table(h4_cell_persistence.describe(include='all').transpose().reset_index().head(12)),
        "",
        "Interpretation rule: high top-cell shares, positive concentration reductions after removing top cells, and high year-to-year top-cell overlap support the granular-corridor proxy for firm granularity.",
        "",
        "## H2: Dominant Supplier Ecosystems",
        "",
        "This test separates global supplier dominance from economy-specific sourcing concentration. Global metrics are computed from country-coded source partners only; importer-level concentration uses observed top-source measures.",
        "",
        "### Latest-Country Median Import Shares By Class",
        "",
        markdown_table(h2_medians, max_rows=10),
        "",
        "### Latest Country Examples",
        "",
        markdown_table(
            h2_latest_wide.sort_values("dominant_or_economy_specific", ascending=False)[
                [
                    "country",
                    "iso3",
                    "year",
                    "global_dominant",
                    "economy_specific",
                    "global_concentrated_other_source",
                    "dominant_or_economy_specific",
                    "diffuse",
                ]
            ],
            max_rows=12,
        ),
        "",
        "Interpretation rule: high `global_dominant` supports supplier ecosystems with few global sources; high `economy_specific` supports country-specific sourcing relationships even when global supply is diversified.",
        "",
        "## Gold-Standard Tests Not Run",
        "",
        "The repository does not contain firm-product-source-year customs records or foreign supplier IDs. The firm and supplier-link tests in the plan therefore remain data requirements, not implemented empirical results.",
        "",
        "## Files",
        "",
        "- `h1_top_supplier_persistence_overall.csv`",
        "- `h1_top_supplier_persistence_by_bin.csv`",
        "- `h1_fixed_cost_sourcing_models.csv`",
        "- `h4_cell_granularity_country_year.csv`",
        "- `h4_top_cells_latest.csv`",
        "- `h4_product_granularity_country_year.csv`",
        "- `h2_global_source_metrics.csv`",
        "- `h2_supplier_ecosystem_country_year.csv`",
        "- `h2_supplier_ecosystem_by_bin.csv`",
        "- `h2_supplier_ecosystem_top_products_latest.csv`",
    ]
    OUT_MEMO.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_outputs(
    h1_overall: pd.DataFrame,
    h4_cell_country_year: pd.DataFrame,
    h4_product_country_year: pd.DataFrame,
    global_metrics: pd.DataFrame,
    h2_panel: pd.DataFrame,
) -> None:
    for label, frame in {
        "global_metrics": global_metrics,
        "h2_panel": h2_panel,
    }.items():
        if "cmd_code" in frame.columns and normalize_cmd(frame["cmd_code"]).isin(EXCLUDED_HS6_CODES).any():
            raise RuntimeError(f"{label} contains excluded HS6 code 999999.")
    if h1_overall.empty:
        raise RuntimeError("H1 persistence summary is empty.")
    if h4_cell_country_year.empty:
        raise RuntimeError("H4 cell-granularity country-year table is empty.")
    if h4_product_country_year.empty:
        raise RuntimeError("H4 product-granularity country-year table is empty.")
    if global_metrics.empty:
        raise RuntimeError("H2 global source metrics are empty.")
    if h2_panel.empty:
        raise RuntimeError("H2 classified supplier panel is empty.")
    if not OUT_CLASSIFIED_PANEL.exists():
        raise RuntimeError(f"Missing classified panel: {OUT_CLASSIFIED_PANEL}")
    if h2_panel["supplier_ecosystem_class"].isna().any():
        raise RuntimeError("H2 supplier ecosystem classifications contain missing values.")
    for col in ["top_1_cell_share", "top_5_cell_share", "top_10_cell_share"]:
        if not h4_cell_country_year[col].between(0, 1).all():
            raise RuntimeError(f"{col} is outside [0, 1].")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-cell-granularity",
        action="store_true",
        help="Skip the expensive product-source-cell granularity pass and reuse existing tables if available.",
    )
    parser.add_argument(
        "--skip-global-rebuild",
        action="store_true",
        help="Reuse h2_global_source_metrics.csv if available.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_dirs()
    countries = read_country_panel()
    partner_ref = read_partner_reference()
    desc = read_product_descriptions()
    print("loading product panel", flush=True)
    panel = read_product_panel()

    print("running H1 fixed-cost sourcing proxies", flush=True)
    persist = add_top_supplier_lags(panel)
    h1_overall, h1_by_bin, h1_by_outlier, h1_models = summarise_h1(persist)
    h1_hs2_models = summarise_h1_hs2(panel)

    if args.skip_cell_granularity and (OUT_TABLES / "h4_cell_granularity_country_year.csv").exists():
        print("reusing existing H4 cell granularity tables", flush=True)
        h4_cell_country_year = pd.read_csv(OUT_TABLES / "h4_cell_granularity_country_year.csv")
        h4_latest_top_cells = pd.read_csv(OUT_TABLES / "h4_top_cells_latest.csv")
        h4_cell_persistence = pd.read_csv(OUT_TABLES / "h4_cell_persistence_country_year.csv")
    else:
        print("running H4 product-source-cell granularity pass", flush=True)
        h4_cell_country_year, h4_latest_top_cells, h4_cell_persistence = run_h4_cell_granularity(
            countries, partner_ref, desc
        )

    print("running H4 product granularity summaries", flush=True)
    h4_product_country_year, h4_latest_products = run_h4_product_granularity(panel, desc)

    global_path = OUT_TABLES / "h2_global_source_metrics.csv"
    if args.skip_global_rebuild and global_path.exists():
        print("reusing existing H2 global source metrics", flush=True)
        global_metrics = pd.read_csv(global_path, dtype={"cmd_code": str})
        global_metrics["cmd_code"] = normalize_cmd(global_metrics["cmd_code"])
        global_metrics = drop_excluded_hs6(global_metrics)
    else:
        print("building H2 global source metrics", flush=True)
        global_metrics = build_global_source_metrics(partner_ref)

    print("classifying H2 supplier ecosystems", flush=True)
    h2_panel, h2_summaries = classify_supplier_ecosystems(panel, global_metrics, desc)

    print("writing tables and memo", flush=True)
    write_tables(
        h1_overall,
        h1_by_bin,
        h1_by_outlier,
        h1_models,
        h1_hs2_models,
        h4_cell_country_year,
        h4_latest_top_cells,
        h4_cell_persistence,
        h4_product_country_year,
        h4_latest_products,
        global_metrics,
        h2_summaries,
    )
    validate_outputs(h1_overall, h4_cell_country_year, h4_product_country_year, global_metrics, h2_panel)
    write_memo(
        h1_overall,
        h1_by_bin,
        h1_by_outlier,
        h1_models,
        h4_cell_country_year,
        h4_cell_persistence,
        h4_product_country_year,
        h2_summaries,
    )
    print(f"wrote {rel(OUT_MEMO)}", flush=True)


if __name__ == "__main__":
    main()
