#!/usr/bin/env python3
"""
Exercise 11 replacement: product leave-one-out import concentration and export linkage.

This script uses checkpointed aggregate files only. It does not reread raw
Comtrade bulk files.
"""

from __future__ import annotations

import argparse
import math
import shutil
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import seaborn as sns
from scipy.optimize import minimize


ROOT = Path(__file__).resolve().parents[1]
DATA_PROCESSED = ROOT / "data" / "processed"
RESULTS = ROOT / "results"

IMPORT_PRODUCT_DIR = DATA_PROCESSED / "exercise_03_file_aggregates" / "product_values"
IMPORT_SUPPLIER_DIR = DATA_PROCESSED / "exercise_04_file_aggregates"
EXPORT_DIR = DATA_PROCESSED / "exercise_12_file_aggregates"

OUT_DATA = DATA_PROCESSED / "exercise_11_product_export_linkage_panel.parquet"
OUT_SECTOR = DATA_PROCESSED / "exercise_11_sector_export_linkage_panel.parquet"
OUT_HS2 = DATA_PROCESSED / "exercise_11_hs2_export_linkage_panel.parquet"
OUT_TABLES = RESULTS / "exercise_11_product_export_linkage_tables"
OUT_FIGURES = RESULTS / "exercise_11_product_export_linkage_figures"
OUT_MEMO = RESULTS / "exercise_11_product_export_linkage.md"

COMMODITY_OUTLIER_HS4 = {"2701", "2709", "2710", "2711", "7108"}
EXCLUDED_HS6_CODES = {"999999"}

BIN_ORDER = ["energy", "intermediates", "capital_goods", "final_consumption", "unmapped_or_ambiguous"]
BIN_LABELS = {
    "energy": "Energy",
    "intermediates": "Intermediates",
    "capital_goods": "Capital goods",
    "final_consumption": "Final consumption",
    "unmapped_or_ambiguous": "Unmapped/ambiguous",
}
PALETTE = {
    "Energy": "#8c4f2b",
    "Intermediates": "#2f5d62",
    "Capital goods": "#6b7fbd",
    "Final consumption": "#b7791f",
    "Unmapped/ambiguous": "#8b8b8b",
}


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
    idx = np.arange(1, n + 1, dtype=float)
    return float((2 * np.sum(idx * arr) / (n * total)) - ((n + 1) / n))


def ensure_dirs() -> None:
    OUT_TABLES.mkdir(parents=True, exist_ok=True)
    OUT_FIGURES.mkdir(parents=True, exist_ok=True)


def load_partner_reference() -> pd.DataFrame:
    path = ROOT / "data" / "raw" / "comtrade" / "partner_reference.csv"
    if not path.exists():
        return pd.DataFrame(columns=["partner_code", "partner_iso3", "partner_name"])
    ref = pd.read_csv(path)
    ref.columns = [str(col).strip() for col in ref.columns]
    if not {"partner_code", "partner_iso3", "partner_name"}.issubset(ref.columns):
        return pd.DataFrame(columns=["partner_code", "partner_iso3", "partner_name"])
    ref = ref[["partner_code", "partner_iso3", "partner_name"]].copy()
    ref["partner_code"] = pd.to_numeric(ref["partner_code"], errors="coerce")
    ref = ref.dropna(subset=["partner_code"])
    ref["partner_code"] = ref["partner_code"].astype(int)
    ref["partner_iso3"] = ref["partner_iso3"].fillna("").astype(str)
    ref["partner_name"] = ref["partner_name"].fillna("").astype(str)
    return ref


def load_country_metadata() -> pd.DataFrame:
    path = DATA_PROCESSED / "prof_p_country_panel.csv"
    panel = pd.read_csv(path)
    return panel[["reporter_code", "country", "iso3"]].drop_duplicates()


def product_description_map() -> pd.DataFrame:
    path = DATA_PROCESSED / "exercise_03_bec5_mapping_approved.csv"
    if not path.exists():
        return pd.DataFrame(columns=["cmd_code", "product_description"])
    cols = ["cmd_code", "hs_desc_official", "hs_desc_if_available"]
    raw = pd.read_csv(path, usecols=lambda col: col in cols, dtype={"cmd_code": str})
    raw["cmd_code"] = raw["cmd_code"].astype(str).str.extract(r"(\d{1,6})", expand=False).str.zfill(6)
    raw = drop_excluded_hs6(raw)
    raw["product_description"] = raw.get("hs_desc_official", pd.Series(index=raw.index, dtype=object))
    if "hs_desc_if_available" in raw.columns:
        raw["product_description"] = raw["product_description"].fillna(raw["hs_desc_if_available"])
    raw = raw.dropna(subset=["cmd_code", "product_description"])
    raw["product_description"] = raw["product_description"].astype(str).str.strip()
    raw = raw[raw["product_description"] != ""]
    if raw.empty:
        return pd.DataFrame(columns=["cmd_code", "product_description"])
    desc = (
        raw.groupby(["cmd_code", "product_description"], as_index=False)
        .size()
        .sort_values(["cmd_code", "size", "product_description"], ascending=[True, False, True])
        .groupby("cmd_code", as_index=False)
        .head(1)
    )
    return desc[["cmd_code", "product_description"]]


def load_unique_io_bridge() -> pd.DataFrame:
    path = ROOT / "data" / "raw" / "oecd_icio" / "oecd_btige_hs_to_sector_bridge.csv"
    if not path.exists():
        return pd.DataFrame(columns=["cmd_code", "io_sector_code", "io_sector_label"])
    bridge = pd.read_csv(path, dtype={"cmd_code": str})
    bridge["cmd_code"] = bridge["cmd_code"].astype(str).str.extract(r"(\d{1,6})", expand=False).str.zfill(6)
    bridge = drop_excluded_hs6(bridge)
    counts = bridge.groupby("cmd_code")["io_sector_code"].nunique().reset_index(name="sector_count")
    unique_codes = counts[counts["sector_count"] == 1][["cmd_code"]]
    bridge = bridge.merge(unique_codes, on="cmd_code", how="inner")
    bridge = bridge[["cmd_code", "io_sector_code", "io_sector_label"]].drop_duplicates("cmd_code")
    return bridge


def normalize_cmd(series: pd.Series) -> pd.Series:
    return series.astype(str).str.extract(r"(\d{1,6})", expand=False).str.zfill(6)


def drop_excluded_hs6(df: pd.DataFrame, code_col: str = "cmd_code") -> pd.DataFrame:
    if df.empty or code_col not in df.columns:
        return df
    mask = normalize_cmd(df[code_col]).isin(EXCLUDED_HS6_CODES)
    if not mask.any():
        return df
    return df.loc[~mask].copy()


def loo_gini_frame(product_totals: pd.DataFrame) -> pd.DataFrame:
    work = product_totals[["cmd_code", "import_value"]].copy()
    work = drop_excluded_hs6(work)
    work = work[pd.to_numeric(work["import_value"], errors="coerce") > 0].copy()
    if work.empty:
        return pd.DataFrame()
    work["import_value"] = work["import_value"].astype(float)
    work = work.sort_values(["import_value", "cmd_code"], ascending=[True, True]).reset_index(drop=True)
    values = work["import_value"].to_numpy(dtype=float)
    n = values.size
    total = float(values.sum())
    ranks = np.arange(1, n + 1, dtype=float)
    weighted_sum = float(np.sum(ranks * values))
    total_gini = gini(values)
    suffix_after = total - np.cumsum(values)

    without = np.full(n, np.nan, dtype=float)
    if n > 1:
        n2 = n - 1
        total_without = total - values
        weighted_without = weighted_sum - ranks * values - suffix_after
        valid = total_without > 0
        without[valid] = (2 * weighted_without[valid] / (n2 * total_without[valid])) - ((n2 + 1) / n2)

    work["total_imports"] = total
    work["active_import_products"] = int(n)
    work["total_import_product_gini"] = total_gini
    work["product_gini_without_product"] = without
    work["loo_gini_contribution"] = total_gini - without
    work["import_value_share"] = work["import_value"] / total if total else np.nan
    work["import_rank"] = work["import_value"].rank(method="first", ascending=False).astype(int)
    return work


def partner_hhi_frame(supplier_values: pd.DataFrame) -> pd.DataFrame:
    if supplier_values.empty:
        return pd.DataFrame(columns=["cmd_code"])
    work = supplier_values.copy()
    work["cmd_code"] = normalize_cmd(work["cmd_code"])
    work["partner_code"] = pd.to_numeric(work["partner_code"], errors="coerce")
    work["trade_value"] = pd.to_numeric(work["trade_value"], errors="coerce")
    work = work.dropna(subset=["cmd_code", "partner_code", "trade_value"])
    work = work[work["trade_value"] > 0].copy()
    work = drop_excluded_hs6(work)
    if work.empty:
        return pd.DataFrame(columns=["cmd_code"])
    work["partner_code"] = work["partner_code"].astype(int)
    work = work.groupby(["cmd_code", "partner_code"], as_index=False)["trade_value"].sum()

    product_totals = work.groupby("cmd_code", as_index=False)["trade_value"].sum().rename(columns={"trade_value": "supplier_product_imports"})
    shares = work.merge(product_totals, on="cmd_code", how="left")
    shares["supplier_share"] = shares["trade_value"] / shares["supplier_product_imports"].replace(0, np.nan)
    top = shares.sort_values(["cmd_code", "trade_value", "partner_code"], ascending=[True, False, True])
    top = top.groupby("cmd_code", as_index=False).head(1).rename(
        columns={
            "partner_code": "top_supplier_code",
            "trade_value": "top_supplier_imports",
            "supplier_share": "within_product_top_supplier_share",
        }
    )
    within = shares.groupby("cmd_code", as_index=False).agg(
        within_product_source_hhi=("supplier_share", lambda s: float(np.square(s.to_numpy(dtype=float)).sum())),
        supplier_count=("partner_code", "nunique"),
    )

    partner_totals = work.groupby("partner_code", as_index=False)["trade_value"].sum().rename(columns={"trade_value": "partner_total"})
    total_imports = float(partner_totals["partner_total"].sum())
    partner_square_sum = float(np.square(partner_totals["partner_total"].to_numpy(dtype=float)).sum())
    total_partner_hhi = partner_square_sum / (total_imports**2) if total_imports > 0 else np.nan
    work = work.merge(partner_totals, on="partner_code", how="left")
    product_cross = work.assign(
        partner_total_times_product=work["partner_total"] * work["trade_value"],
        product_partner_square=np.square(work["trade_value"].to_numpy(dtype=float)),
    ).groupby("cmd_code", as_index=False).agg(
        cross_term=("partner_total_times_product", "sum"),
        product_partner_square_sum=("product_partner_square", "sum"),
    )
    loo = product_totals.merge(product_cross, on="cmd_code", how="left")
    denom = total_imports - loo["supplier_product_imports"]
    numerator_without = partner_square_sum - 2 * loo["cross_term"] + loo["product_partner_square_sum"]
    loo["partner_hhi_without_product"] = np.where(denom > 0, numerator_without / np.square(denom), np.nan)
    loo["total_partner_hhi"] = total_partner_hhi
    loo["loo_partner_hhi_contribution"] = loo["total_partner_hhi"] - loo["partner_hhi_without_product"]
    out = product_totals.merge(top[["cmd_code", "top_supplier_code", "top_supplier_imports", "within_product_top_supplier_share"]], on="cmd_code", how="left")
    out = out.merge(within, on="cmd_code", how="left")
    out = out.merge(loo[["cmd_code", "total_partner_hhi", "partner_hhi_without_product", "loo_partner_hhi_contribution"]], on="cmd_code", how="left")
    return out


def export_product_frame(exports: pd.DataFrame) -> pd.DataFrame:
    if exports.empty:
        return pd.DataFrame(columns=["cmd_code", "export_value", "total_exports"])
    work = exports[exports["dimension"] == "product"].copy()
    if work.empty:
        return pd.DataFrame(columns=["cmd_code", "export_value", "total_exports"])
    work["cmd_code"] = normalize_cmd(work["cmd_code"])
    work["trade_value"] = pd.to_numeric(work["trade_value"], errors="coerce")
    work = work.dropna(subset=["cmd_code", "trade_value"])
    work = work[work["trade_value"] > 0].copy()
    work = drop_excluded_hs6(work)
    if work.empty:
        return pd.DataFrame(columns=["cmd_code", "export_value", "total_exports"])
    out = work.groupby("cmd_code", as_index=False)["trade_value"].sum().rename(columns={"trade_value": "export_value"})
    total_exports = float(out["export_value"].sum())
    out["total_exports"] = total_exports
    return out


def dominant_bin_frame(imports: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    work = imports.copy()
    work["cmd_code"] = normalize_cmd(work["cmd_code"])
    work["trade_value"] = pd.to_numeric(work["trade_value"], errors="coerce")
    work = work.dropna(subset=["cmd_code", "exercise_03_bin", "trade_value"])
    work = work[work["trade_value"] > 0].copy()
    work = drop_excluded_hs6(work)
    if work.empty:
        return pd.DataFrame(columns=["cmd_code", "import_value"]), pd.DataFrame(columns=["cmd_code", "import_bin", "dominant_bin_import_value"])
    by_bin = work.groupby(["cmd_code", "exercise_03_bin"], as_index=False)["trade_value"].sum()
    by_product = by_bin.groupby("cmd_code", as_index=False)["trade_value"].sum().rename(columns={"trade_value": "import_value"})
    dom = (
        by_bin.sort_values(["cmd_code", "trade_value", "exercise_03_bin"], ascending=[True, False, True])
        .groupby("cmd_code", as_index=False)
        .head(1)
        .rename(columns={"exercise_03_bin": "import_bin", "trade_value": "dominant_bin_import_value"})
    )
    return by_product, dom[["cmd_code", "import_bin", "dominant_bin_import_value"]]


PANEL_COLUMNS = [
    "reporter_code",
    "year",
    "cmd_code",
    "import_bin",
    "import_value",
    "total_imports",
    "import_value_share",
    "active_import_products",
    "import_rank",
    "total_import_product_gini",
    "product_gini_without_product",
    "loo_gini_contribution",
    "supplier_product_imports",
    "top_supplier_code",
    "top_supplier_imports",
    "within_product_top_supplier_share",
    "within_product_source_hhi",
    "supplier_count",
    "total_partner_hhi",
    "partner_hhi_without_product",
    "loo_partner_hhi_contribution",
    "export_value",
    "total_exports",
    "export_share",
    "export_any",
    "asinh_export_value",
    "is_intermediate",
    "top_supplier_iso3",
    "top_supplier_name",
    "country",
    "iso3",
]


def panel_for_file(import_path: Path, supplier_path: Path | None, export_path: Path | None, partner_ref: pd.DataFrame, countries: pd.DataFrame) -> pd.DataFrame:
    imports = pd.read_parquet(import_path)
    if imports.empty:
        return pd.DataFrame(columns=PANEL_COLUMNS)
    reporter_code = int(pd.to_numeric(imports["reporter_code"], errors="coerce").dropna().iloc[0])
    year = int(pd.to_numeric(imports["year"], errors="coerce").dropna().iloc[0])

    product_totals, dominant_bins = dominant_bin_frame(imports)
    loo = loo_gini_frame(product_totals)
    if loo.empty:
        return pd.DataFrame(columns=PANEL_COLUMNS)
    panel = loo.merge(dominant_bins, on="cmd_code", how="left")

    if supplier_path and supplier_path.exists():
        supplier = pd.read_parquet(supplier_path)
        supplier_metrics = partner_hhi_frame(supplier)
        panel = panel.merge(supplier_metrics, on="cmd_code", how="left")
    else:
        panel = panel.assign(
            supplier_product_imports=np.nan,
            top_supplier_code=np.nan,
            top_supplier_imports=np.nan,
            within_product_top_supplier_share=np.nan,
            within_product_source_hhi=np.nan,
            supplier_count=np.nan,
            total_partner_hhi=np.nan,
            partner_hhi_without_product=np.nan,
            loo_partner_hhi_contribution=np.nan,
        )

    if export_path and export_path.exists():
        exports = pd.read_parquet(export_path)
        export_products = export_product_frame(exports)
        panel = panel.merge(export_products, on="cmd_code", how="left")
    else:
        panel = panel.assign(export_value=np.nan, total_exports=np.nan)

    panel["reporter_code"] = reporter_code
    panel["year"] = year
    panel["export_value"] = panel["export_value"].fillna(0.0)
    total_exports = panel["total_exports"].dropna()
    panel["total_exports"] = float(total_exports.iloc[0]) if not total_exports.empty else 0.0
    panel["export_share"] = np.where(panel["total_exports"] > 0, panel["export_value"] / panel["total_exports"], 0.0)
    panel["export_any"] = (panel["export_value"] > 0).astype(int)
    panel["asinh_export_value"] = np.arcsinh(panel["export_value"].to_numpy(dtype=float))
    panel["is_intermediate"] = (panel["import_bin"] == "intermediates").astype(int)

    panel["top_supplier_code"] = pd.to_numeric(panel["top_supplier_code"], errors="coerce")
    if not partner_ref.empty:
        panel = panel.merge(
            partner_ref.rename(
                columns={
                    "partner_code": "top_supplier_code",
                    "partner_iso3": "top_supplier_iso3",
                    "partner_name": "top_supplier_name",
                }
            ),
            on="top_supplier_code",
            how="left",
        )
    else:
        panel["top_supplier_iso3"] = ""
        panel["top_supplier_name"] = ""
    panel["top_supplier_iso3"] = panel["top_supplier_iso3"].fillna("").replace("", "Unknown")
    panel["top_supplier_name"] = panel["top_supplier_name"].fillna("")
    panel = panel.merge(countries, on="reporter_code", how="left")
    panel["country"] = panel["country"].fillna(panel["reporter_code"].astype(str))
    panel["iso3"] = panel["iso3"].fillna("")
    for col in PANEL_COLUMNS:
        if col not in panel.columns:
            panel[col] = np.nan
    return drop_excluded_hs6(panel[PANEL_COLUMNS].copy())


def build_product_panel() -> pd.DataFrame:
    ensure_dirs()
    partner_ref = load_partner_reference()
    countries = load_country_metadata()
    import_files = sorted(IMPORT_PRODUCT_DIR.glob("*.parquet"))
    supplier_map = {path.name: path for path in IMPORT_SUPPLIER_DIR.glob("*.parquet")}
    export_map = {path.name: path for path in EXPORT_DIR.glob("*.parquet")}
    if OUT_DATA.exists():
        OUT_DATA.unlink()

    writer: pq.ParquetWriter | None = None
    total_rows = 0
    try:
        for idx, import_path in enumerate(import_files, start=1):
            frame = panel_for_file(import_path, supplier_map.get(import_path.name), export_map.get(import_path.name), partner_ref, countries)
            if frame.empty:
                continue
            table = pa.Table.from_pandas(frame, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(OUT_DATA, table.schema, compression="zstd")
            writer.write_table(table)
            total_rows += len(frame)
            if idx % 100 == 0:
                print(f"built product-export linkage panel {idx}/{len(import_files)} files, {total_rows:,} rows", flush=True)
    finally:
        if writer is not None:
            writer.close()
    print(f"wrote {OUT_DATA.relative_to(ROOT)} with {total_rows:,} rows", flush=True)
    return pd.read_parquet(OUT_DATA)


def load_or_build_product_panel(rebuild: bool = False) -> pd.DataFrame:
    if rebuild and OUT_DATA.exists():
        OUT_DATA.unlink()
    if OUT_DATA.exists():
        print(f"loading existing {OUT_DATA.relative_to(ROOT)}", flush=True)
        return drop_excluded_hs6(pd.read_parquet(OUT_DATA))
    return build_product_panel()


def standardize(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    sd = float(values.std(ddof=0))
    if not np.isfinite(sd) or sd == 0:
        return values * np.nan
    return (values - float(values.mean())) / sd


@dataclass
class OLSResult:
    model_label: str
    outcome: str
    terms: list[str]
    beta: np.ndarray
    se: np.ndarray
    cov: np.ndarray
    nobs: int
    clusters: int
    r2_within: float


@dataclass
class FELogitResult:
    model_label: str
    outcome: str
    terms: list[str]
    beta: np.ndarray
    se: np.ndarray
    nobs: int
    groups: int
    dropped_groups: int
    dropped_obs: int
    loglike: float
    converged: bool
    iterations: int
    message: str


def normal_pvalue(t_stat: float) -> float:
    if not np.isfinite(t_stat):
        return np.nan
    return math.erfc(abs(t_stat) / math.sqrt(2.0))


def logistic_cdf(values: np.ndarray) -> np.ndarray:
    out = np.empty_like(values, dtype=float)
    positive = values >= 0
    out[positive] = 1.0 / (1.0 + np.exp(-values[positive]))
    exp_values = np.exp(values[~positive])
    out[~positive] = exp_values / (1.0 + exp_values)
    return out


def fixed_effect_cluster_ols(df: pd.DataFrame, outcome: str, terms: list[str], fe_col: str, cluster_col: str, model_label: str) -> OLSResult:
    work = df[[outcome, *terms, fe_col, cluster_col]].replace([np.inf, -np.inf], np.nan).dropna().copy()
    work = work.groupby(fe_col).filter(lambda group: len(group) > 1)
    y_raw = pd.to_numeric(work[outcome], errors="coerce")
    x_raw = work[terms].apply(pd.to_numeric, errors="coerce")
    y = y_raw - y_raw.groupby(work[fe_col]).transform("mean")
    x = x_raw - x_raw.groupby(work[fe_col]).transform("mean")
    valid = y.notna() & x.notna().all(axis=1)
    y = y.loc[valid].to_numpy(dtype=float)
    x = x.loc[valid].to_numpy(dtype=float)
    clusters = work.loc[valid, cluster_col].to_numpy()
    nobs, k = x.shape
    if nobs <= k:
        beta = np.full(k, np.nan)
        cov = np.full((k, k), np.nan)
        se = np.full(k, np.nan)
        r2 = np.nan
        cluster_count = int(pd.Series(clusters).nunique())
        return OLSResult(model_label, outcome, terms, beta, se, cov, nobs, cluster_count, r2)
    xtx = x.T @ x
    xtx_inv = np.linalg.pinv(xtx)
    beta = xtx_inv @ (x.T @ y)
    resid = y - x @ beta
    meat = np.zeros((k, k), dtype=float)
    for cluster in pd.unique(clusters):
        mask = clusters == cluster
        xu = x[mask].T @ resid[mask]
        meat += np.outer(xu, xu)
    cluster_count = int(pd.Series(clusters).nunique())
    scale = 1.0
    if cluster_count > 1 and nobs > k:
        scale = (cluster_count / (cluster_count - 1)) * ((nobs - 1) / (nobs - k))
    cov = scale * xtx_inv @ meat @ xtx_inv
    se = np.sqrt(np.maximum(np.diag(cov), 0))
    tss = float(np.sum(np.square(y - y.mean())))
    rss = float(np.sum(np.square(resid)))
    r2 = 1 - rss / tss if tss > 0 else np.nan
    return OLSResult(model_label, outcome, terms, beta, se, cov, nobs, cluster_count, r2)


def results_to_frame(results: list[OLSResult]) -> pd.DataFrame:
    rows = []
    for result in results:
        for idx, term in enumerate(result.terms):
            coef = float(result.beta[idx])
            se = float(result.se[idx])
            t_stat = coef / se if se > 0 else np.nan
            rows.append(
                {
                    "model_label": result.model_label,
                    "outcome": result.outcome,
                    "term": term,
                    "coef": coef,
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


def fe_logit_to_frame(result: FELogitResult) -> pd.DataFrame:
    rows = []
    for idx, term in enumerate(result.terms):
        coef = float(result.beta[idx])
        se = float(result.se[idx])
        z_stat = coef / se if se > 0 else np.nan
        rows.append(
            {
                "model_label": result.model_label,
                "estimator": "country_year_fixed_effect_logit",
                "outcome": result.outcome,
                "term": term,
                "coef": coef,
                "std_error": se,
                "z_stat": z_stat,
                "p_value": normal_pvalue(z_stat),
                "ci_low": coef - 1.96 * se if np.isfinite(se) else np.nan,
                "ci_high": coef + 1.96 * se if np.isfinite(se) else np.nan,
                "nobs": result.nobs,
                "groups": result.groups,
                "dropped_no_variation_groups": result.dropped_groups,
                "dropped_no_variation_obs": result.dropped_obs,
                "loglike": result.loglike,
                "converged": result.converged,
                "iterations": result.iterations,
                "message": result.message,
            }
        )
    return pd.DataFrame(rows)


def build_regression_sample(panel: pd.DataFrame) -> pd.DataFrame:
    df = panel.copy()
    df["country_year"] = df["reporter_code"].astype(str) + "_" + df["year"].astype(str)
    for col in ["loo_gini_contribution", "loo_partner_hhi_contribution", "import_value_share"]:
        df[f"{col}_z"] = standardize(df[col])
    df["loo_gini_x_intermediate_z"] = df["loo_gini_contribution_z"] * df["is_intermediate"]
    df["bin_energy"] = (df["import_bin"] == "energy").astype(int)
    df["bin_capital_goods"] = (df["import_bin"] == "capital_goods").astype(int)
    df["bin_final_consumption"] = (df["import_bin"] == "final_consumption").astype(int)
    df["bin_unmapped"] = (df["import_bin"] == "unmapped_or_ambiguous").astype(int)
    return df


def fixed_effect_logit(
    df: pd.DataFrame,
    outcome: str,
    terms: list[str],
    fe_col: str,
    model_label: str,
    maxiter: int = 200,
) -> FELogitResult:
    work = df[[outcome, *terms, fe_col]].replace([np.inf, -np.inf], np.nan).dropna().copy()
    work[outcome] = pd.to_numeric(work[outcome], errors="coerce")
    work = work[work[outcome].isin([0, 1])].copy()
    group_outcomes = work.groupby(fe_col)[outcome].agg(["sum", "size"])
    varying_groups = group_outcomes[(group_outcomes["sum"] > 0) & (group_outcomes["sum"] < group_outcomes["size"])].index
    dropped_groups = int(len(group_outcomes) - len(varying_groups))
    dropped_obs = int(group_outcomes.loc[~group_outcomes.index.isin(varying_groups), "size"].sum()) if dropped_groups else 0
    work = work[work[fe_col].isin(varying_groups)].copy()
    y = work[outcome].to_numpy(dtype=float)
    x = work[terms].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    group_codes = pd.Categorical(work[fe_col]).codes
    nobs, k = x.shape
    groups = int(group_codes.max() + 1) if nobs else 0
    if nobs == 0 or groups == 0:
        return FELogitResult(
            model_label=model_label,
            outcome=outcome,
            terms=terms,
            beta=np.full(k, np.nan),
            se=np.full(k, np.nan),
            nobs=nobs,
            groups=groups,
            dropped_groups=dropped_groups,
            dropped_obs=dropped_obs,
            loglike=np.nan,
            converged=False,
            iterations=0,
            message="no usable groups with within-group outcome variation",
        )

    def objective(params: np.ndarray) -> tuple[float, np.ndarray]:
        beta = params[:k]
        alpha = params[k:]
        eta = x @ beta + alpha[group_codes]
        nll = float(np.logaddexp(0.0, eta).sum() - y @ eta)
        mu = logistic_cdf(eta)
        resid = mu - y
        grad_beta = x.T @ resid
        grad_alpha = np.bincount(group_codes, weights=resid, minlength=groups)
        return nll, np.concatenate([grad_beta, grad_alpha])

    start = np.zeros(k + groups, dtype=float)
    fit = minimize(
        objective,
        start,
        method="L-BFGS-B",
        jac=True,
        options={"maxiter": maxiter, "ftol": 1e-8, "gtol": 1e-5, "maxls": 30},
    )
    beta = fit.x[:k]
    alpha = fit.x[k:]
    eta = x @ beta + alpha[group_codes]
    mu = logistic_cdf(eta)
    weights = np.maximum(mu * (1.0 - mu), 1e-12)

    info_beta = x.T @ (weights[:, None] * x)
    weighted_x_by_group = np.vstack(
        [
            np.bincount(group_codes, weights=weights * x[:, col], minlength=groups)
            for col in range(k)
        ]
    ).T
    weight_by_group = np.bincount(group_codes, weights=weights, minlength=groups)
    valid_weight = weight_by_group > 0
    if valid_weight.any():
        adjustment = (weighted_x_by_group[valid_weight].T / weight_by_group[valid_weight]) @ weighted_x_by_group[valid_weight]
        info_beta = info_beta - adjustment
    cov_beta = np.linalg.pinv(info_beta)
    se = np.sqrt(np.maximum(np.diag(cov_beta), 0))
    loglike = -float(fit.fun)
    return FELogitResult(
        model_label=model_label,
        outcome=outcome,
        terms=terms,
        beta=beta,
        se=se,
        nobs=nobs,
        groups=groups,
        dropped_groups=dropped_groups,
        dropped_obs=dropped_obs,
        loglike=loglike,
        converged=bool(fit.success),
        iterations=int(getattr(fit, "nit", 0)),
        message=str(fit.message),
    )


def run_conditional_logit(panel: pd.DataFrame) -> pd.DataFrame:
    df = build_regression_sample(panel)
    terms = [
        "loo_gini_contribution_z",
        "import_value_share_z",
        "bin_energy",
        "bin_capital_goods",
        "bin_final_consumption",
        "bin_unmapped",
    ]
    result = fixed_effect_logit(
        df,
        outcome="export_any",
        terms=terms,
        fe_col="country_year",
        model_label="product_export_any_conditional_logit",
    )
    out = fe_logit_to_frame(result)
    out.to_csv(OUT_TABLES / "conditional_logit_results.csv", index=False)
    return out


def run_product_regressions(panel: pd.DataFrame, table_suffix: str = "", sample_label: str = "baseline") -> tuple[pd.DataFrame, pd.DataFrame]:
    df = build_regression_sample(panel)
    bin_terms = ["bin_energy", "bin_capital_goods", "bin_final_consumption", "bin_unmapped"]
    results = [
        fixed_effect_cluster_ols(
            df,
            outcome="asinh_export_value",
            terms=["loo_gini_contribution_z", "import_value_share_z", *bin_terms],
            fe_col="country_year",
            cluster_col="reporter_code",
            model_label="product_export_value_gini",
        ),
        fixed_effect_cluster_ols(
            df,
            outcome="export_any",
            terms=["loo_gini_contribution_z", "import_value_share_z", *bin_terms],
            fe_col="country_year",
            cluster_col="reporter_code",
            model_label="product_export_any_gini",
        ),
        fixed_effect_cluster_ols(
            df,
            outcome="asinh_export_value",
            terms=["loo_partner_hhi_contribution_z", "import_value_share_z", *bin_terms],
            fe_col="country_year",
            cluster_col="reporter_code",
            model_label="product_export_value_partner_hhi",
        ),
        fixed_effect_cluster_ols(
            df,
            outcome="asinh_export_value",
            terms=["loo_gini_contribution_z", "is_intermediate", "loo_gini_x_intermediate_z", "import_value_share_z"],
            fe_col="country_year",
            cluster_col="reporter_code",
            model_label="product_export_value_intermediate_interaction",
        ),
    ]
    reg = results_to_frame(results)
    reg.insert(0, "sample", sample_label)

    interaction = next(result for result in results if result.model_label == "product_export_value_intermediate_interaction")
    idx_base = interaction.terms.index("loo_gini_contribution_z")
    idx_int = interaction.terms.index("loo_gini_x_intermediate_z")
    base = float(interaction.beta[idx_base])
    interaction_coef = float(interaction.beta[idx_int])
    cov = interaction.cov
    non_intermediate_se = float(interaction.se[idx_base])
    intermediate_se = float(np.sqrt(max(cov[idx_base, idx_base] + cov[idx_int, idx_int] + 2 * cov[idx_base, idx_int], 0)))
    effects = pd.DataFrame(
        [
            {
                "effect": "Non-intermediate slope",
                "coef": base,
                "std_error": non_intermediate_se,
                "ci_low": base - 1.96 * non_intermediate_se,
                "ci_high": base + 1.96 * non_intermediate_se,
            },
            {
                "effect": "Intermediate slope",
                "coef": base + interaction_coef,
                "std_error": intermediate_se,
                "ci_low": base + interaction_coef - 1.96 * intermediate_se,
                "ci_high": base + interaction_coef + 1.96 * intermediate_se,
            },
            {
                "effect": "Intermediate minus non-intermediate",
                "coef": interaction_coef,
                "std_error": float(interaction.se[idx_int]),
                "ci_low": interaction_coef - 1.96 * float(interaction.se[idx_int]),
                "ci_high": interaction_coef + 1.96 * float(interaction.se[idx_int]),
            },
        ]
    )
    effects.insert(0, "sample", sample_label)
    suffix = f"_{table_suffix}" if table_suffix else ""
    reg.to_csv(OUT_TABLES / f"product_regressions{suffix}.csv", index=False)
    effects.to_csv(OUT_TABLES / f"intermediate_effects{suffix}.csv", index=False)
    return reg, effects


def build_sector_panel(panel: pd.DataFrame) -> pd.DataFrame:
    bridge = load_unique_io_bridge()
    if bridge.empty:
        return pd.DataFrame()
    work = panel.merge(bridge, on="cmd_code", how="inner")
    if work.empty:
        return pd.DataFrame()
    sector = work.groupby(["reporter_code", "country", "iso3", "year", "io_sector_code", "io_sector_label"], as_index=False).agg(
        sector_loo_gini_contribution=("loo_gini_contribution", "sum"),
        sector_loo_partner_hhi_contribution=("loo_partner_hhi_contribution", "sum"),
        sector_import_value=("import_value", "sum"),
        sector_import_value_share=("import_value_share", "sum"),
        sector_export_value=("export_value", "sum"),
        sector_export_share=("export_share", "sum"),
        product_count=("cmd_code", "nunique"),
        intermediate_import_value=("import_value", lambda s: float(s[work.loc[s.index, "is_intermediate"].eq(1)].sum())),
    )
    sector["sector_intermediate_import_share"] = sector["intermediate_import_value"] / sector["sector_import_value"].replace(0, np.nan)
    sector["asinh_sector_export_value"] = np.arcsinh(sector["sector_export_value"].to_numpy(dtype=float))
    sector.to_parquet(OUT_SECTOR, index=False)
    sector.to_csv(OUT_TABLES / "sector_export_linkage_panel.csv", index=False)
    return sector


def run_sector_regressions(sector: pd.DataFrame) -> pd.DataFrame:
    if sector.empty:
        out = pd.DataFrame()
        out.to_csv(OUT_TABLES / "sector_regressions.csv", index=False)
        return out
    df = sector.copy()
    df["country_year"] = df["reporter_code"].astype(str) + "_" + df["year"].astype(str)
    df["sector_loo_gini_contribution_z"] = standardize(df["sector_loo_gini_contribution"])
    df["sector_loo_partner_hhi_contribution_z"] = standardize(df["sector_loo_partner_hhi_contribution"])
    df["sector_import_value_share_z"] = standardize(df["sector_import_value_share"])
    dummies = pd.get_dummies(df["io_sector_code"], prefix="sector", drop_first=True, dtype=int)
    df = pd.concat([df, dummies], axis=1)
    sector_terms = dummies.columns.tolist()
    results = [
        fixed_effect_cluster_ols(
            df,
            outcome="sector_export_share",
            terms=["sector_loo_gini_contribution_z", "sector_import_value_share_z", *sector_terms],
            fe_col="country_year",
            cluster_col="reporter_code",
            model_label="sector_export_share_gini",
        ),
        fixed_effect_cluster_ols(
            df,
            outcome="sector_export_share",
            terms=["sector_loo_partner_hhi_contribution_z", "sector_import_value_share_z", *sector_terms],
            fe_col="country_year",
            cluster_col="reporter_code",
            model_label="sector_export_share_partner_hhi",
        ),
    ]
    reg = results_to_frame(results)
    reg.to_csv(OUT_TABLES / "sector_regressions.csv", index=False)
    return reg


def build_hs2_panel(panel: pd.DataFrame) -> pd.DataFrame:
    work = panel[
        [
            "reporter_code",
            "country",
            "iso3",
            "year",
            "cmd_code",
            "import_value",
            "total_imports",
            "import_value_share",
            "loo_gini_contribution",
            "loo_partner_hhi_contribution",
            "export_value",
            "total_exports",
            "export_share",
            "is_intermediate",
        ]
    ].copy()
    work["hs2"] = work["cmd_code"].astype(str).str.zfill(6).str[:2]
    work["intermediate_import_value"] = np.where(work["is_intermediate"].eq(1), work["import_value"], 0.0)
    hs2 = work.groupby(["reporter_code", "country", "iso3", "year", "hs2"], as_index=False).agg(
        hs2_import_value=("import_value", "sum"),
        total_imports=("total_imports", "first"),
        hs2_import_value_share=("import_value_share", "sum"),
        hs2_product_loo_gini_sum=("loo_gini_contribution", "sum"),
        hs2_product_loo_partner_hhi_sum=("loo_partner_hhi_contribution", "sum"),
        hs2_export_value=("export_value", "sum"),
        total_exports=("total_exports", "first"),
        hs2_export_share=("export_share", "sum"),
        hs2_product_count=("cmd_code", "nunique"),
        hs2_intermediate_import_value=("intermediate_import_value", "sum"),
    )

    loo_frames: list[pd.DataFrame] = []
    for (reporter_code, year), group in hs2.groupby(["reporter_code", "year"], sort=False):
        tmp = group[["hs2", "hs2_import_value"]].rename(columns={"hs2": "cmd_code", "hs2_import_value": "import_value"})
        loo = loo_gini_frame(tmp)
        if loo.empty:
            continue
        loo["reporter_code"] = reporter_code
        loo["year"] = year
        loo = loo.rename(
            columns={
                "cmd_code": "hs2",
                "active_import_products": "active_import_hs2_chapters",
                "total_import_product_gini": "total_import_hs2_gini",
                "product_gini_without_product": "hs2_gini_without_chapter",
                "loo_gini_contribution": "hs2_loo_gini_contribution",
                "import_value_share": "hs2_direct_import_value_share",
                "import_rank": "hs2_import_rank",
            }
        )
        loo = loo.drop(columns=["import_value", "total_imports"], errors="ignore")
        loo_frames.append(loo)
    hs2_loo = pd.concat(loo_frames, ignore_index=True) if loo_frames else pd.DataFrame(columns=["reporter_code", "year", "hs2"])
    hs2 = hs2.merge(hs2_loo, on=["reporter_code", "year", "hs2"], how="left")
    hs2["hs2_import_value_share"] = hs2["hs2_direct_import_value_share"].fillna(hs2["hs2_import_value_share"])
    hs2 = hs2.drop(columns=["hs2_direct_import_value_share"], errors="ignore")
    hs2["hs2_export_any"] = (hs2["hs2_export_value"] > 0).astype(int)
    hs2["asinh_hs2_export_value"] = np.arcsinh(hs2["hs2_export_value"].to_numpy(dtype=float))
    hs2["hs2_intermediate_import_share"] = hs2["hs2_intermediate_import_value"] / hs2["hs2_import_value"].replace(0, np.nan)
    hs2.to_parquet(OUT_HS2, index=False)
    hs2.to_csv(OUT_TABLES / "hs2_export_linkage_panel.csv", index=False)
    return hs2


def run_hs2_regressions(hs2: pd.DataFrame) -> pd.DataFrame:
    if hs2.empty:
        out = pd.DataFrame()
        out.to_csv(OUT_TABLES / "hs2_regressions.csv", index=False)
        return out
    df = hs2.copy()
    df["country_year"] = df["reporter_code"].astype(str) + "_" + df["year"].astype(str)
    df["hs2_loo_gini_contribution_z"] = standardize(df["hs2_loo_gini_contribution"])
    df["hs2_product_loo_gini_sum_z"] = standardize(df["hs2_product_loo_gini_sum"])
    df["hs2_import_value_share_z"] = standardize(df["hs2_import_value_share"])
    df["hs2_intermediate_import_share_z"] = standardize(df["hs2_intermediate_import_share"])
    df["hs2_loo_gini_x_intermediate_share_z"] = df["hs2_loo_gini_contribution_z"] * df["hs2_intermediate_import_share_z"]
    df["hs2_product_loo_gini_sum_x_intermediate_share_z"] = df["hs2_product_loo_gini_sum_z"] * df["hs2_intermediate_import_share_z"]
    dummies = pd.get_dummies(df["hs2"], prefix="hs2", drop_first=True, dtype=int)
    df = pd.concat([df, dummies], axis=1)
    hs2_terms = dummies.columns.tolist()
    results = [
        fixed_effect_cluster_ols(
            df,
            outcome="asinh_hs2_export_value",
            terms=["hs2_product_loo_gini_sum_z", "hs2_import_value_share_z", *hs2_terms],
            fe_col="country_year",
            cluster_col="reporter_code",
            model_label="hs2_export_value_gini",
        ),
        fixed_effect_cluster_ols(
            df,
            outcome="hs2_export_any",
            terms=["hs2_product_loo_gini_sum_z", "hs2_import_value_share_z", *hs2_terms],
            fe_col="country_year",
            cluster_col="reporter_code",
            model_label="hs2_export_any_gini",
        ),
        fixed_effect_cluster_ols(
            df,
            outcome="hs2_export_share",
            terms=["hs2_product_loo_gini_sum_z", "hs2_import_value_share_z", *hs2_terms],
            fe_col="country_year",
            cluster_col="reporter_code",
            model_label="hs2_export_share_gini",
        ),
        fixed_effect_cluster_ols(
            df,
            outcome="asinh_hs2_export_value",
            terms=[
                "hs2_product_loo_gini_sum_z",
                "hs2_intermediate_import_share_z",
                "hs2_product_loo_gini_sum_x_intermediate_share_z",
                "hs2_import_value_share_z",
                *hs2_terms,
            ],
            fe_col="country_year",
            cluster_col="reporter_code",
            model_label="hs2_export_value_intermediate_intensity",
        ),
    ]
    reg = results_to_frame(results)
    reg.insert(0, "sample", "hs2 chapter")
    reg.to_csv(OUT_TABLES / "hs2_regressions.csv", index=False)
    return reg


def flag_commodity_outliers(panel: pd.DataFrame) -> pd.Series:
    hs4 = panel["cmd_code"].astype(str).str.zfill(6).str[:4]
    return hs4.isin(COMMODITY_OUTLIER_HS4)


def selected_comparison_rows(reg: pd.DataFrame, sample_label: str) -> pd.DataFrame:
    wanted = [
        ("product_export_value_gini", "loo_gini_contribution_z", "Export value: product-Gini contribution"),
        ("product_export_any_gini", "loo_gini_contribution_z", "Export probability: product-Gini contribution"),
        ("product_export_value_partner_hhi", "loo_partner_hhi_contribution_z", "Export value: partner-HHI contribution"),
        ("product_export_value_intermediate_interaction", "loo_gini_x_intermediate_z", "Intermediate interaction"),
    ]
    rows = []
    for model_label, term, label in wanted:
        match = reg[(reg["model_label"] == model_label) & (reg["term"] == term)]
        if match.empty:
            continue
        row = match.iloc[0].copy()
        row["sample"] = sample_label
        row["check"] = label
        rows.append(row)
    return pd.DataFrame(rows)


def run_commodity_exclusion(panel: pd.DataFrame, baseline_reg: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    outlier_mask = flag_commodity_outliers(panel)
    filtered = panel.loc[~outlier_mask].copy()
    reg, effects = run_product_regressions(
        filtered,
        table_suffix="excluding_commodity_outliers",
        sample_label="excluding oil/gas/gold/coal",
    )
    stats = pd.DataFrame(
        [
            {"measure": "commodity_outlier_hs4_codes", "value": ",".join(sorted(COMMODITY_OUTLIER_HS4))},
            {"measure": "commodity_outlier_rows", "value": int(outlier_mask.sum())},
            {"measure": "commodity_outlier_row_share", "value": float(outlier_mask.mean())},
            {
                "measure": "commodity_outlier_import_value_share",
                "value": float(panel.loc[outlier_mask, "import_value"].sum() / panel["import_value"].sum()),
            },
            {"measure": "product_rows_excluding_commodity_outliers", "value": int((~outlier_mask).sum())},
        ]
    )
    stats.to_csv(OUT_TABLES / "commodity_outlier_exclusion_stats.csv", index=False)

    comparison = pd.concat(
        [
            selected_comparison_rows(baseline_reg, "baseline"),
            selected_comparison_rows(reg, "excluding oil/gas/gold/coal"),
        ],
        ignore_index=True,
    )
    comparison.to_csv(OUT_TABLES / "commodity_exclusion_regression_comparison.csv", index=False)
    return reg, effects, comparison


def savefig(name: str) -> str:
    OUT_FIGURES.mkdir(parents=True, exist_ok=True)
    path = OUT_FIGURES / name
    plt.tight_layout()
    plt.savefig(path, dpi=220, bbox_inches="tight")
    plt.close()
    return str(path)


def label_top_points(ax: plt.Axes, df: pd.DataFrame, x: str, y: str, label_col: str, n: int = 10) -> None:
    if df.empty:
        return
    ranked = df.assign(_score=df[x].abs().rank(pct=True) + df[y].abs().rank(pct=True)).nlargest(n, "_score")
    for row in ranked.itertuples(index=False):
        ax.annotate(
            str(getattr(row, label_col)),
            (float(getattr(row, x)), float(getattr(row, y))),
            fontsize=7,
            xytext=(3, 3),
            textcoords="offset points",
            color="#111827",
        )


def quantile_export_probability_table(
    df: pd.DataFrame,
    score_col: str,
    export_any_col: str,
    export_value_col: str,
    bins: int,
    bin_label: str,
) -> pd.DataFrame:
    work = df[[score_col, export_any_col, export_value_col]].replace([np.inf, -np.inf], np.nan).dropna().copy()
    work[score_col] = pd.to_numeric(work[score_col], errors="coerce")
    work[export_any_col] = pd.to_numeric(work[export_any_col], errors="coerce")
    work[export_value_col] = pd.to_numeric(work[export_value_col], errors="coerce")
    work = work.dropna()
    if work.empty:
        return pd.DataFrame(
            columns=[
                "bin",
                "bin_label",
                "observations",
                "exported_count",
                "score_min",
                "score_max",
                "mean_loo_gini",
                "export_probability",
                "export_probability_se",
                "export_probability_ci_low",
                "export_probability_ci_high",
                "mean_asinh_export_value",
            ]
        )
    work["bin"] = pd.qcut(work[score_col], bins, labels=False, duplicates="drop") + 1
    out = work.groupby("bin", observed=True).agg(
        observations=(export_any_col, "size"),
        exported_count=(export_any_col, "sum"),
        score_min=(score_col, "min"),
        score_max=(score_col, "max"),
        mean_loo_gini=(score_col, "mean"),
        export_probability=(export_any_col, "mean"),
        mean_asinh_export_value=(export_value_col, "mean"),
    ).reset_index()
    out["bin"] = out["bin"].astype(int)
    out.insert(1, "bin_label", bin_label)
    out["export_probability_se"] = np.sqrt(
        out["export_probability"] * (1.0 - out["export_probability"]) / out["observations"].replace(0, np.nan)
    )
    out["export_probability_ci_low"] = np.maximum(0.0, out["export_probability"] - 1.96 * out["export_probability_se"])
    out["export_probability_ci_high"] = np.minimum(1.0, out["export_probability"] + 1.96 * out["export_probability_se"])
    return out


def plot_export_probability_table(
    table: pd.DataFrame,
    figure_name: str,
    score_label: str,
    probability_label: str,
    value_label: str,
    title_prefix: str,
) -> None:
    if table.empty:
        return
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    x = table["mean_loo_gini"].to_numpy(dtype=float)
    p = table["export_probability"].to_numpy(dtype=float)
    lo = table["export_probability_ci_low"].to_numpy(dtype=float)
    hi = table["export_probability_ci_high"].to_numpy(dtype=float)
    axes[0].plot(x, p, marker="o", color="#2f5d62", linewidth=1.8, markersize=4)
    axes[0].fill_between(x, lo, hi, color="#2f5d62", alpha=0.16, linewidth=0)
    axes[0].set_xlabel(score_label)
    axes[0].set_ylabel(probability_label)
    axes[0].set_title(f"{title_prefix} Export Probability")
    axes[1].plot(x, table["mean_asinh_export_value"], marker="o", color="#8c4f2b", linewidth=1.8, markersize=4)
    axes[1].set_xlabel(score_label)
    axes[1].set_ylabel(value_label)
    axes[1].set_title(f"{title_prefix} Export Value")
    savefig(figure_name)


def make_figures(panel: pd.DataFrame, sector: pd.DataFrame, effects: pd.DataFrame) -> None:
    sns.set_theme(style="whitegrid", context="paper", font_scale=1.05)
    panel = panel.copy()
    panel["bin_label"] = panel["import_bin"].map(BIN_LABELS).fillna(panel["import_bin"])
    india_year = int(panel.loc[panel["iso3"].eq("IND"), "year"].max())
    india = panel[(panel["iso3"] == "IND") & (panel["year"] == india_year)].copy()
    india["export_size"] = np.clip(np.log1p(india["export_value"]), 0, None)
    india["plot_label"] = india["cmd_code"].astype(str)

    plt.figure(figsize=(10, 7))
    ax = sns.scatterplot(
        data=india,
        x="import_value_share",
        y="loo_gini_contribution",
        hue="bin_label",
        hue_order=[BIN_LABELS[b] for b in BIN_ORDER],
        palette=PALETTE,
        size="export_size",
        sizes=(20, 260),
        alpha=0.72,
        edgecolor="none",
    )
    ax.set_xscale("log")
    ax.set_xlabel("Product share of total imports, log scale")
    ax.set_ylabel("LOO contribution to total import product Gini")
    ax.set_title(f"India {india_year}: Which Products Raise Total Import Concentration?")
    label_top_points(ax, india.nlargest(40, "import_value_share"), "import_value_share", "loo_gini_contribution", "plot_label", n=12)
    ax.legend(frameon=False, bbox_to_anchor=(1.02, 1), loc="upper left")
    savefig("ex11_india_product_loo_gini_scatter.png")

    supplier = india.copy()
    top_suppliers = supplier.groupby("top_supplier_iso3")["import_value"].sum().nlargest(8).index
    supplier["supplier_group"] = np.where(supplier["top_supplier_iso3"].isin(top_suppliers), supplier["top_supplier_iso3"], "Other")
    plt.figure(figsize=(10, 7))
    ax = sns.scatterplot(
        data=supplier,
        x="loo_gini_contribution",
        y="loo_partner_hhi_contribution",
        hue="supplier_group",
        size="import_value_share",
        sizes=(20, 260),
        alpha=0.74,
        edgecolor="none",
    )
    ax.axhline(0, color="#9ca3af", linewidth=1)
    ax.axvline(0, color="#9ca3af", linewidth=1)
    ax.set_xlabel("LOO contribution to total import product Gini")
    ax.set_ylabel("LOO contribution to total partner-country HHI")
    ax.set_title(f"India {india_year}: Product vs Supplier-Country Concentration Contributions")
    label_top_points(ax, supplier.nlargest(50, "import_value_share"), "loo_gini_contribution", "loo_partner_hhi_contribution", "plot_label", n=12)
    ax.legend(frameon=False, bbox_to_anchor=(1.02, 1), loc="upper left")
    savefig("ex11_india_product_supplier_loo_scatter.png")

    bins = panel.replace([np.inf, -np.inf], np.nan).dropna(subset=["loo_gini_contribution"]).copy()
    bins["loo_decile"] = pd.qcut(bins["loo_gini_contribution"], 10, duplicates="drop")
    dec = bins.groupby("loo_decile", observed=True).agg(
        mean_loo_gini=("loo_gini_contribution", "mean"),
        export_probability=("export_any", "mean"),
        mean_asinh_export_value=("asinh_export_value", "mean"),
    ).reset_index()
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    sns.lineplot(data=dec, x="mean_loo_gini", y="export_probability", marker="o", ax=axes[0], color="#2f5d62")
    axes[0].set_xlabel("Mean LOO Gini contribution by decile")
    axes[0].set_ylabel("Probability product is exported")
    axes[0].set_title("Export Probability by Import-Concentration Contribution")
    sns.lineplot(data=dec, x="mean_loo_gini", y="mean_asinh_export_value", marker="o", ax=axes[1], color="#8c4f2b")
    axes[1].set_xlabel("Mean LOO Gini contribution by decile")
    axes[1].set_ylabel("Mean asinh export value")
    axes[1].set_title("Export Value by Import-Concentration Contribution")
    savefig("ex11_export_linkage_by_loo_decile.png")

    pct4 = quantile_export_probability_table(
        panel,
        score_col="loo_gini_contribution",
        export_any_col="export_any",
        export_value_col="asinh_export_value",
        bins=25,
        bin_label="4pct",
    )
    pct4.to_csv(OUT_TABLES / "ex11_export_linkage_by_loo_4pct_bin.csv", index=False)
    plot_export_probability_table(
        pct4,
        "ex11_export_linkage_by_loo_4pct_bin.png",
        "Mean LOO Gini contribution by 4% bin",
        "Probability product is exported",
        "Mean asinh export value",
        "HS6 4% bins",
    )

    effects_plot = effects.copy()
    effects_plot = effects_plot[effects_plot["effect"].isin(["Non-intermediate slope", "Intermediate slope", "Intermediate minus non-intermediate"])]
    plt.figure(figsize=(9, 5.5))
    ax = plt.gca()
    y_pos = np.arange(len(effects_plot))
    ax.errorbar(
        effects_plot["coef"],
        y_pos,
        xerr=[effects_plot["coef"] - effects_plot["ci_low"], effects_plot["ci_high"] - effects_plot["coef"]],
        fmt="o",
        color="#2f5d62",
        ecolor="#6b7280",
        capsize=4,
    )
    ax.axvline(0, color="#9ca3af", linewidth=1)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(effects_plot["effect"])
    ax.set_xlabel("Coefficient on LOO Gini contribution, standardized")
    ax.set_title("Intermediate-Channel Regression Effects")
    savefig("ex11_intermediate_channel_coefficients.png")

    if not sector.empty:
        sector_india_year = int(sector.loc[sector["iso3"].eq("IND"), "year"].max())
        sec = sector[(sector["iso3"] == "IND") & (sector["year"] == sector_india_year)].copy()
        sec = sec.replace([np.inf, -np.inf], np.nan).dropna(subset=["sector_loo_gini_contribution", "sector_export_share"])
        plt.figure(figsize=(10, 7))
        ax = sns.scatterplot(
            data=sec,
            x="sector_loo_gini_contribution",
            y="sector_export_share",
            size="sector_import_value_share",
            hue="sector_intermediate_import_share",
            palette="viridis",
            sizes=(30, 320),
            alpha=0.78,
            edgecolor="none",
        )
        for row in sec.nlargest(12, "sector_import_value_share").itertuples(index=False):
            ax.annotate(str(row.io_sector_code), (row.sector_loo_gini_contribution, row.sector_export_share), fontsize=8, xytext=(3, 3), textcoords="offset points")
        ax.axvline(0, color="#9ca3af", linewidth=1)
        ax.set_xlabel("Sector sum of product LOO Gini contributions")
        ax.set_ylabel("Sector share of exports")
        ax.set_title(f"India {sector_india_year}: Sector Import-Concentration Contribution vs Export Share")
        ax.legend(frameon=False, bbox_to_anchor=(1.02, 1), loc="upper left")
        savefig("ex11_india_sector_linkage_scatter.png")


def make_hs2_figures(hs2: pd.DataFrame) -> None:
    if hs2.empty:
        return
    sns.set_theme(style="whitegrid", context="paper", font_scale=1.05)
    bins = hs2.replace([np.inf, -np.inf], np.nan).dropna(subset=["hs2_product_loo_gini_sum"]).copy()
    bins["loo_decile"] = pd.qcut(bins["hs2_product_loo_gini_sum"], 10, duplicates="drop")
    dec = bins.groupby("loo_decile", observed=True).agg(
        mean_loo_gini=("hs2_product_loo_gini_sum", "mean"),
        export_probability=("hs2_export_any", "mean"),
        mean_asinh_export_value=("asinh_hs2_export_value", "mean"),
        mean_intermediate_import_share=("hs2_intermediate_import_share", "mean"),
    ).reset_index()
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    sns.lineplot(data=dec, x="mean_loo_gini", y="export_probability", marker="o", ax=axes[0], color="#2f5d62")
    axes[0].set_xlabel("Mean summed HS6 LOO Gini contribution by HS2 decile")
    axes[0].set_ylabel("Probability HS2 chapter is exported")
    axes[0].set_title("HS2 Export Probability by Import-Concentration Contribution")
    sns.lineplot(data=dec, x="mean_loo_gini", y="mean_asinh_export_value", marker="o", ax=axes[1], color="#8c4f2b")
    axes[1].set_xlabel("Mean summed HS6 LOO Gini contribution by HS2 decile")
    axes[1].set_ylabel("Mean asinh HS2 export value")
    axes[1].set_title("HS2 Export Value by Import-Concentration Contribution")
    savefig("ex11_hs2_export_linkage_by_loo_decile.png")

    pct4 = quantile_export_probability_table(
        hs2,
        score_col="hs2_product_loo_gini_sum",
        export_any_col="hs2_export_any",
        export_value_col="asinh_hs2_export_value",
        bins=25,
        bin_label="4pct",
    )
    pct4.to_csv(OUT_TABLES / "ex11_hs2_export_linkage_by_loo_4pct_bin.csv", index=False)
    plot_export_probability_table(
        pct4,
        "ex11_hs2_export_linkage_by_loo_4pct_bin.png",
        "Mean summed HS6 LOO Gini contribution by 4% HS2 bin",
        "Probability HS2 chapter is exported",
        "Mean asinh HS2 export value",
        "HS2 4% bins",
    )

    india_year = int(hs2.loc[hs2["iso3"].eq("IND"), "year"].max())
    india = hs2[(hs2["iso3"] == "IND") & (hs2["year"] == india_year)].copy()
    india = india.replace([np.inf, -np.inf], np.nan).dropna(subset=["hs2_product_loo_gini_sum", "hs2_export_share"])
    plt.figure(figsize=(10, 7))
    ax = sns.scatterplot(
        data=india,
        x="hs2_product_loo_gini_sum",
        y="hs2_export_share",
        size="hs2_import_value_share",
        hue="hs2_intermediate_import_share",
        palette="viridis",
        sizes=(40, 360),
        alpha=0.78,
        edgecolor="none",
    )
    for row in india.nlargest(12, "hs2_import_value_share").itertuples(index=False):
        ax.annotate(f"HS {row.hs2}", (row.hs2_product_loo_gini_sum, row.hs2_export_share), fontsize=8, xytext=(3, 3), textcoords="offset points")
    ax.axvline(0, color="#9ca3af", linewidth=1)
    ax.set_xlabel("HS2 sum of HS6 LOO contributions to total import Gini")
    ax.set_ylabel("HS2 share of exports")
    ax.set_title(f"India {india_year}: HS2 Import-Concentration Contribution vs Export Share")
    ax.legend(frameon=False, bbox_to_anchor=(1.02, 1), loc="upper left")
    savefig("ex11_india_hs2_linkage_scatter.png")


def make_commodity_exclusion_figure(comparison: pd.DataFrame) -> None:
    if comparison.empty:
        return
    sns.set_theme(style="whitegrid", context="paper", font_scale=1.05)
    plot = comparison.copy()
    order = [
        "Export value: product-Gini contribution",
        "Export probability: product-Gini contribution",
        "Export value: partner-HHI contribution",
        "Intermediate interaction",
    ]
    sample_offsets = {"baseline": -0.16, "excluding oil/gas/gold/coal": 0.16}
    colors = {"baseline": "#6b7280", "excluding oil/gas/gold/coal": "#2f5d62"}
    fig, ax = plt.subplots(figsize=(10, 6))
    for sample, group in plot.groupby("sample", sort=False):
        y = group["check"].map({label: idx for idx, label in enumerate(order)}).astype(float) + sample_offsets.get(sample, 0)
        ax.errorbar(
            group["coef"],
            y,
            xerr=[group["coef"] - group["ci_low"], group["ci_high"] - group["coef"]],
            fmt="o",
            capsize=4,
            label=sample,
            color=colors.get(sample, "#111827"),
            ecolor=colors.get(sample, "#111827"),
        )
    ax.axvline(0, color="#9ca3af", linewidth=1)
    ax.set_yticks(np.arange(len(order)))
    ax.set_yticklabels(order)
    ax.set_xlabel("Coefficient with 95% CI")
    ax.set_title("HS6 Regressions With and Without Oil, Gas, Gold, and Coal")
    ax.legend(frameon=False, loc="lower right")
    savefig("ex11_excluding_commodity_outlier_coefficients.png")


def make_tables(
    panel: pd.DataFrame,
    sector: pd.DataFrame,
    hs2: pd.DataFrame,
    product_reg: pd.DataFrame,
    conditional_logit: pd.DataFrame,
    sector_reg: pd.DataFrame,
    hs2_reg: pd.DataFrame,
    commodity_stats: pd.DataFrame,
) -> None:
    desc = product_description_map()
    india_year = int(panel.loc[panel["iso3"].eq("IND"), "year"].max())
    india = panel[(panel["iso3"] == "IND") & (panel["year"] == india_year)].copy()
    india = india.merge(desc, on="cmd_code", how="left")
    keep = [
        "cmd_code",
        "product_description",
        "import_bin",
        "import_value_share",
        "loo_gini_contribution",
        "loo_partner_hhi_contribution",
        "export_share",
        "top_supplier_iso3",
        "within_product_top_supplier_share",
    ]
    india.nlargest(15, "loo_gini_contribution")[keep].to_csv(OUT_TABLES / "india_top_loo_gini_products.csv", index=False)
    india.nlargest(15, "loo_partner_hhi_contribution")[keep].to_csv(OUT_TABLES / "india_top_loo_partner_hhi_products.csv", index=False)

    summary = pd.DataFrame(
        [
            {"measure": "product_panel_rows", "value": len(panel)},
            {"measure": "countries", "value": panel["iso3"].nunique()},
            {"measure": "years_min", "value": int(panel["year"].min())},
            {"measure": "years_max", "value": int(panel["year"].max())},
            {"measure": "median_loo_gini_contribution", "value": float(panel["loo_gini_contribution"].median())},
            {"measure": "share_positive_loo_gini", "value": float((panel["loo_gini_contribution"] > 0).mean())},
            {"measure": "share_exported", "value": float(panel["export_any"].mean())},
            {"measure": "india_latest_year", "value": india_year},
            {"measure": "sector_panel_rows", "value": len(sector)},
            {"measure": "hs2_panel_rows", "value": len(hs2)},
            {"measure": "hs2_chapters", "value": int(hs2["hs2"].nunique()) if not hs2.empty else 0},
        ]
    )
    if not commodity_stats.empty:
        summary = pd.concat([summary, commodity_stats], ignore_index=True)
    summary.to_csv(OUT_TABLES / "summary_stats.csv", index=False)

    selected_terms = [
        "loo_gini_contribution_z",
        "loo_partner_hhi_contribution_z",
        "loo_gini_x_intermediate_z",
        "import_value_share_z",
        "sector_loo_gini_contribution_z",
        "sector_loo_partner_hhi_contribution_z",
        "sector_import_value_share_z",
        "hs2_loo_gini_contribution_z",
        "hs2_product_loo_gini_sum_z",
        "hs2_import_value_share_z",
        "hs2_loo_gini_x_intermediate_share_z",
        "hs2_product_loo_gini_sum_x_intermediate_share_z",
    ]
    reg_selected = pd.concat([product_reg, sector_reg, hs2_reg], ignore_index=True)
    reg_selected = reg_selected[reg_selected["term"].isin(selected_terms)].copy()
    reg_selected.to_csv(OUT_TABLES / "selected_regression_coefficients.csv", index=False)

    if not conditional_logit.empty:
        conditional_logit[conditional_logit["term"].isin(["loo_gini_contribution_z", "import_value_share_z"])].to_csv(
            OUT_TABLES / "selected_conditional_logit_coefficients.csv",
            index=False,
        )


def write_memo(
    panel: pd.DataFrame,
    product_reg: pd.DataFrame,
    conditional_logit: pd.DataFrame,
    sector: pd.DataFrame,
    sector_reg: pd.DataFrame,
    hs2: pd.DataFrame,
    hs2_reg: pd.DataFrame,
    commodity_comparison: pd.DataFrame,
) -> None:
    rows = len(panel)
    countries = panel["iso3"].nunique()
    years = f"{int(panel['year'].min())}-{int(panel['year'].max())}"
    key = product_reg[
        (product_reg["model_label"].isin(["product_export_value_gini", "product_export_any_gini", "product_export_value_partner_hhi", "product_export_value_intermediate_interaction"]))
        & (product_reg["term"].isin(["loo_gini_contribution_z", "loo_partner_hhi_contribution_z", "loo_gini_x_intermediate_z"]))
    ][["model_label", "outcome", "term", "coef", "std_error", "p_value", "nobs", "clusters", "r2_within"]].copy()
    clogit_key = conditional_logit[
        conditional_logit["term"].isin(["loo_gini_contribution_z", "import_value_share_z"])
    ][
        [
            "model_label",
            "estimator",
            "outcome",
            "term",
            "coef",
            "std_error",
            "p_value",
            "nobs",
            "groups",
            "dropped_no_variation_groups",
            "converged",
        ]
    ].copy()
    memo = f"""# Exercise 11: Product Contribution and Export Linkage

Generated from checkpointed aggregate files.

## Question

Do the HS6 products that make a country's total import basket more concentrated also link to exports, especially through intermediate goods?

## Sample

- Product-level rows: {rows:,}
- Countries: {countries}
- Years: {years}
- Unit: country-year-HS6 import product

## Main Variables

- `loo_gini_contribution`: total import product Gini minus product Gini after removing that HS6 product.
- `loo_partner_hhi_contribution`: total partner-country HHI minus partner-country HHI after removing that HS6 product.
- Export outcomes: export indicator, asinh export value, export share.

## Selected Regression Results

{key.round(4).to_markdown(index=False)}

## Country-Year Fixed-Effect Logit

The binary export outcome is also estimated with a country-year fixed-effect logit. This is the computationally feasible nonlinear probability model for the 5.5 million-row HS6 panel; it compares imported products within the same reporter-year and drops reporter-years with no within-group variation in `export_any`.

{clogit_key.round(4).to_markdown(index=False) if not clogit_key.empty else "No fixed-effect logit output."}

## Broader HS2 Robustness

The HS6 exact-product outcome may be too narrow for an intermediate-processing claim because imported inputs and exported outputs can sit in different HS6 product lines inside the same broader production chain. The HS2 robustness aggregates HS6 concentration contributions and exports to HS chapters, then reruns export-linkage regressions with country-year and HS2 fixed effects.

{hs2_reg[(hs2_reg["term"].isin(["hs2_product_loo_gini_sum_z", "hs2_product_loo_gini_sum_x_intermediate_share_z"]))][["model_label", "outcome", "term", "coef", "std_error", "p_value", "nobs", "clusters", "r2_within"]].round(4).to_markdown(index=False) if not hs2_reg.empty else "No HS2 regression output."}

## Commodity-Outlier Exclusion

The narrow HS6 regressions were also rerun after excluding coal (`2701`), crude and refined petroleum (`2709`, `2710`), petroleum gases/natural gas (`2711`), and gold (`7108`). This checks whether the main result is just an oil/gas/gold/coal result.

{commodity_comparison[["sample", "check", "coef", "std_error", "ci_low", "ci_high", "nobs", "r2_within"]].round(4).to_markdown(index=False) if not commodity_comparison.empty else "No commodity-exclusion output."}

## Files

- Data: `{OUT_DATA.relative_to(ROOT)}`, `{OUT_SECTOR.relative_to(ROOT)}`, `{OUT_HS2.relative_to(ROOT)}`
- Tables: `{OUT_TABLES.relative_to(ROOT)}`
- Figures: `{OUT_FIGURES.relative_to(ROOT)}`

## Interpretation

The regressions are descriptive. Positive coefficients support the idea that concentration-driving import products are export-linked. They do not prove that import concentration causes exports.
"""
    OUT_MEMO.write_text(memo, encoding="utf-8")


def copy_figures_to_overleaf() -> None:
    overleaf_figs = RESULTS / "overleaf_exercises_03_04_11" / "figures"
    if not overleaf_figs.exists():
        return
    for path in OUT_FIGURES.glob("*.png"):
        shutil.copy2(path, overleaf_figs / path.name)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rebuild-panel",
        action="store_true",
        help="Rebuild the product-export-linkage panel instead of reusing the cached parquet.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ensure_dirs()
    panel = load_or_build_product_panel(rebuild=args.rebuild_panel)
    product_reg, effects = run_product_regressions(panel)
    conditional_logit = run_conditional_logit(panel)
    commodity_reg, commodity_effects, commodity_comparison = run_commodity_exclusion(panel, product_reg)
    sector = build_sector_panel(panel)
    sector_reg = run_sector_regressions(sector)
    hs2 = build_hs2_panel(panel)
    hs2_reg = run_hs2_regressions(hs2)
    make_figures(panel, sector, effects)
    make_hs2_figures(hs2)
    make_commodity_exclusion_figure(commodity_comparison)
    commodity_stats = pd.read_csv(OUT_TABLES / "commodity_outlier_exclusion_stats.csv")
    make_tables(panel, sector, hs2, product_reg, conditional_logit, sector_reg, hs2_reg, commodity_stats)
    write_memo(panel, product_reg, conditional_logit, sector, sector_reg, hs2, hs2_reg, commodity_comparison)
    copy_figures_to_overleaf()
    print(f"wrote {OUT_TABLES.relative_to(ROOT)}")
    print(f"wrote {OUT_FIGURES.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
