#!/usr/bin/env python3
"""Exercise 8 public proxy using EDD and WBES public data.

This is intentionally separate from the main Comtrade pipeline. Exercise 8's
gold-standard input is restricted firm-product-destination customs data; this
script uses public Exporter Dynamics Database country-year indicators and
World Bank Enterprise Survey firm records as proxies, and labels the limitation
in every final artifact.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests


ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
RESULTS = ROOT / "results"
EDD_RAW = DATA_RAW / "world_bank_edd"
EX08_TABLES = RESULTS / "exercise_08_tables"
EX08_FIGURES = RESULTS / "exercise_08_figures"

EDD_SOURCE_ID = "30"
EDD_API_BASE = f"https://api.worldbank.org/v2/sources/{EDD_SOURCE_ID}"
EDD_LONG_CACHE = EDD_RAW / "edd_country_year_long.csv"
EX08_PANEL_PARQUET = DATA_PROCESSED / "exercise_08_edd_public_proxy_panel.parquet"
EX08_PANEL_CSV = EX08_TABLES / "edd_public_proxy_panel.csv"
EX08_CORRELATIONS_CSV = EX08_TABLES / "edd_correlations.csv"
EX08_OLS_CSV = EX08_TABLES / "edd_ols.csv"
WBES_FIRM_PANEL_CSV = EX08_TABLES / "wbes_firm_proxy_panel.csv"
WBES_COUNTRY_SUMMARY_CSV = EX08_TABLES / "wbes_country_summary.csv"
WBES_CORRELATIONS_CSV = EX08_TABLES / "wbes_exporter_focus_correlations.csv"
WBES_OLS_CSV = EX08_TABLES / "wbes_exporter_focus_ols.csv"
WBES_DESTINATION_SUMMARY_CSV = EX08_TABLES / "wbes_destination_summary.csv"
EX08_MEMO = RESULTS / "exercise_08_public_proxy.md"
EX08_MANIFEST = RESULTS / "run_manifest_exercise_08_public_proxy.json"

SERIES = {
    "A1": "number_exporters",
    "B1": "exporter_hhi",
    "B2i": "top_1pct_exporter_share",
    "B2ii": "top_5pct_exporter_share",
    "B2iii": "top_25pct_exporter_share",
    "B3i": "hs6_products_per_exporter_mean",
    "B3ii": "hs6_products_per_exporter_median",
    "B4i": "destinations_per_exporter_mean",
    "B4ii": "destinations_per_exporter_median",
}

OUTCOMES = [
    "product_gini",
    "partner_gini",
    "product_partner_cell_gini",
    "product_top_5pct_share",
    "top_5_partner_share",
    "product_partner_cell_top_5pct_share",
]

PREDICTORS = [
    "exporter_hhi",
    "top_1pct_exporter_share",
    "top_5pct_exporter_share",
    "top_25pct_exporter_share",
    "hs6_products_per_exporter_mean",
    "hs6_products_per_exporter_median",
    "destinations_per_exporter_mean",
    "destinations_per_exporter_median",
    "number_exporters",
]

CONTROLS = [
    "log_total_exports",
    "log_product_active_count",
    "log_partner_active_count",
    "log_product_partner_cell_active_count",
]

TARGET_COUNTRIES = {
    "IND": "India",
    "CHN": "China",
    "USA": "United States",
}

WBES_DATASETS = [
    {
        "iso3": "IND",
        "country": "India",
        "catalog_id": "6494",
        "filename": "India_2014_2022.dta",
        "fallback_survey_year": 2022,
        "catalog_url": "https://microdata.worldbank.org/catalog/6494",
        "data_dictionary_url": "https://microdata.worldbank.org/catalog/6494/data-dictionary/F1?file_name=India_2014_2022.dta",
    },
    {
        "iso3": "CHN",
        "country": "China",
        "catalog_id": "6676",
        "filename": "China-2024-full-data.dta",
        "fallback_survey_year": 2024,
        "catalog_url": "https://microdata.worldbank.org/catalog/6676",
        "data_dictionary_url": "https://microdata.worldbank.org/catalog/6676/data-dictionary/F1?file_name=China-2024-full-data.dta",
    },
    {
        "iso3": "USA",
        "country": "United States",
        "catalog_id": "6709",
        "filename": "United-States-2024-full-data.dta",
        "fallback_survey_year": 2024,
        "catalog_url": "https://microdata.worldbank.org/catalog/6709",
        "data_dictionary_url": "https://microdata.worldbank.org/catalog/6709/data-dictionary/F1?file_name=United-States-2024-full-data.dta",
    },
]

WBES_NUMERIC_FIELDS = {
    "main_activity_share": "d1a3",
    "sales": "d2",
    "national_sales_share": "d3a",
    "indirect_export_share": "d3b",
    "direct_export_share": "d3c",
    "foreign_input_share": "d12b",
}

WBES_OPTIONAL_FIELDS = {
    "direct_importer_raw": "d13",
    "main_export_destination": "d31x",
    "main_import_origin": "d38x",
    "sector": "a4a",
    "region": "a2",
}

WBES_WEIGHT_CANDIDATES = [
    "wmedian",
    "wmean",
    "wstrict",
    "wweak",
    "weight",
    "weights",
    "sampling_weight",
    "wgt",
    "w",
]

WBES_YEAR_CANDIDATES = [
    "survey_year",
    "surveyyear",
    "interview_year",
    "int_year",
    "year",
]

WBES_ID_CANDIDATES = [
    "idstd",
    "id",
    "firm_id",
    "enterprise_id",
    "panelid",
]

WBES_OUTCOMES = ["any_exporter", "direct_exporter", "export_share"]
WBES_PREDICTORS = [
    "main_activity_share",
    "log_sales",
    "log_employment",
    "foreign_input_share",
    "direct_importer",
]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_dirs() -> None:
    for path in [EDD_RAW, DATA_PROCESSED, RESULTS, EX08_TABLES, EX08_FIGURES]:
        path.mkdir(parents=True, exist_ok=True)


def resolve_repo_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return ROOT / path


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def request_json(url: str, params: dict[str, object], attempts: int = 3) -> dict:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(url, params=params, timeout=(20, 120))
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, list) and payload and isinstance(payload[0], dict) and "message" in payload[0]:
                raise RuntimeError(str(payload[0]["message"]))
            if not isinstance(payload, dict):
                raise RuntimeError(f"Unexpected World Bank API payload type: {type(payload).__name__}")
            return payload
        except Exception as exc:  # pragma: no cover - exercised only on transient network failures
            last_error = exc
            if attempt < attempts:
                time.sleep(2 * attempt)
    raise RuntimeError(f"World Bank API request failed after {attempts} attempts: {last_error}")


def concept_value(record: dict, concept_name: str, field: str = "value") -> object:
    for variable in record.get("variable", []):
        if str(variable.get("concept", "")).lower() == concept_name.lower():
            return variable.get(field)
    return None


def fetch_series(series_id: str) -> list[dict]:
    rows: list[dict] = []
    page = 1
    pages = 1
    while page <= pages:
        payload = request_json(
            f"{EDD_API_BASE}/country/all/series/{series_id}/time/all",
            {"format": "json", "per_page": 20000, "page": page},
        )
        pages = int(payload.get("pages", 1) or 1)
        source = payload.get("source", {})
        for record in source.get("data", []):
            iso3 = concept_value(record, "Country", "id")
            country = concept_value(record, "Country", "value")
            series_name = concept_value(record, "Series", "value")
            year_value = concept_value(record, "Time", "value")
            if iso3 is None or year_value is None:
                continue
            try:
                year = int(year_value)
            except (TypeError, ValueError):
                continue
            value = record.get("value")
            rows.append(
                {
                    "iso3": str(iso3),
                    "country": str(country or ""),
                    "year": year,
                    "series_id": series_id,
                    "series_name": str(series_name or ""),
                    "series_slug": SERIES[series_id],
                    "value": np.nan if value is None else float(value),
                }
            )
        page += 1
    return rows


def load_or_fetch_edd(refresh: bool) -> pd.DataFrame:
    if EDD_LONG_CACHE.exists() and not refresh:
        return pd.read_csv(EDD_LONG_CACHE)

    rows: list[dict] = []
    for series_id in SERIES:
        print(f"Fetching EDD series {series_id}: {SERIES[series_id]}", flush=True)
        rows.extend(fetch_series(series_id))
    if not rows:
        raise RuntimeError("No EDD rows were returned by the World Bank API.")

    out = pd.DataFrame(rows).sort_values(["series_id", "iso3", "year"]).reset_index(drop=True)
    out.to_csv(EDD_LONG_CACHE, index=False)
    return out


def build_edd_wide(edd_long: pd.DataFrame) -> pd.DataFrame:
    required = {"iso3", "country", "year", "series_slug", "value"}
    missing = required.difference(edd_long.columns)
    if missing:
        raise RuntimeError(f"EDD cache is missing required columns: {sorted(missing)}")

    wide = (
        edd_long.pivot_table(
            index=["iso3", "country", "year"],
            columns="series_slug",
            values="value",
            aggfunc="first",
        )
        .reset_index()
        .rename_axis(None, axis=1)
    )
    for slug in SERIES.values():
        if slug not in wide.columns:
            wide[slug] = np.nan
    return wide.sort_values(["iso3", "year"]).reset_index(drop=True)


def load_exercise1_exports(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Exercise 1 concentration CSV not found: {path}")

    needed = {
        "iso3",
        "country",
        "year",
        "flow",
        "variant",
        "total_trade_value",
        "product_active_count",
        "partner_active_count",
        "product_partner_cell_active_count",
        *OUTCOMES,
    }
    header = pd.read_csv(path, nrows=0)
    missing = needed.difference(header.columns)
    if missing:
        raise RuntimeError(f"Exercise 1 CSV is missing required columns: {sorted(missing)}")

    df = pd.read_csv(path, usecols=sorted(needed))
    exports = df[(df["flow"] == "Exports") & (df["variant"] == "baseline")].copy()
    if exports.empty:
        raise RuntimeError("Exercise 1 CSV has no baseline export rows.")

    exports = exports.rename(
        columns={
            "country": "exercise1_country",
            "total_trade_value": "total_exports",
        }
    )
    return exports


def safe_log(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    return np.log(numeric.where(numeric > 0))


def build_panel(edd_wide: pd.DataFrame, exercise1_exports: pd.DataFrame) -> pd.DataFrame:
    panel = exercise1_exports.merge(edd_wide, on=["iso3", "year"], how="inner", suffixes=("", "_edd"))
    if panel.empty:
        raise RuntimeError("EDD data and Exercise 1 exports have no overlapping iso3-year rows.")
    if "country" in panel.columns:
        panel = panel.rename(columns={"country": "edd_country"})

    panel["log_total_exports"] = safe_log(panel["total_exports"])
    panel["log_product_active_count"] = safe_log(panel["product_active_count"])
    panel["log_partner_active_count"] = safe_log(panel["partner_active_count"])
    panel["log_product_partner_cell_active_count"] = safe_log(panel["product_partner_cell_active_count"])
    return panel.sort_values(["iso3", "year"]).reset_index(drop=True)


def has_variation(series: pd.Series) -> bool:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return len(values) > 1 and values.nunique(dropna=True) > 1


def compute_correlations(panel: pd.DataFrame, min_n: int) -> pd.DataFrame:
    rows = []
    for outcome in OUTCOMES:
        for predictor in PREDICTORS:
            work = panel[[outcome, predictor]].apply(pd.to_numeric, errors="coerce").dropna()
            row = {
                "outcome": outcome,
                "predictor": predictor,
                "nobs": int(len(work)),
                "pearson": np.nan,
                "spearman": np.nan,
                "skip_reason": "",
            }
            if len(work) < min_n:
                row["skip_reason"] = f"n<{min_n}"
            elif not has_variation(work[outcome]) or not has_variation(work[predictor]):
                row["skip_reason"] = "no_variation"
            else:
                row["pearson"] = float(work[outcome].corr(work[predictor], method="pearson"))
                row["spearman"] = float(work[outcome].corr(work[predictor], method="spearman"))
            rows.append(row)
    return pd.DataFrame(rows)


def zscore(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    std = values.std(ddof=0)
    if not np.isfinite(std) or std == 0:
        return pd.Series(np.nan, index=series.index)
    return (values - values.mean()) / std


def make_design_matrix(work: pd.DataFrame, predictor: str) -> tuple[pd.DataFrame, list[str]]:
    parts = [pd.Series(1.0, index=work.index, name="intercept")]
    names = ["intercept"]

    predictor_z = zscore(work[predictor]).rename(f"z_{predictor}")
    parts.append(predictor_z)
    names.append(predictor_z.name)

    for control in CONTROLS:
        if control in work.columns and has_variation(work[control]):
            control_z = zscore(work[control]).rename(f"z_{control}")
            if control_z.notna().any():
                parts.append(control_z)
                names.append(control_z.name)

    year_dummies = pd.get_dummies(work["year"].astype(str), prefix="year", drop_first=True, dtype=float)
    for column in year_dummies.columns:
        if year_dummies[column].std(ddof=0) > 0:
            parts.append(year_dummies[column].rename(column))
            names.append(column)

    x = pd.concat(parts, axis=1)
    keep = []
    for column in x.columns:
        values = pd.to_numeric(x[column], errors="coerce")
        if column == "intercept" or values.std(ddof=0) > 0:
            keep.append(column)
    x = x[keep].astype(float)
    return x, list(x.columns)


def run_ols_one(panel: pd.DataFrame, outcome: str, predictor: str, min_n: int) -> dict:
    cols = [outcome, predictor, "year", *CONTROLS]
    work = panel[[col for col in cols if col in panel.columns]].copy()
    for col in [outcome, predictor, *CONTROLS]:
        if col in work.columns:
            work[col] = pd.to_numeric(work[col], errors="coerce")
    work = work.dropna(subset=[outcome, predictor, "year"]).copy()

    row = {
        "outcome": outcome,
        "predictor": predictor,
        "coefficient": np.nan,
        "std_error_hc1": np.nan,
        "nobs": int(len(work)),
        "r_squared": np.nan,
        "controls": ",".join([control for control in CONTROLS if control in work.columns]),
        "year_fixed_effects": True,
        "standardized_outcome_and_predictor": True,
        "skip_reason": "",
    }
    if len(work) < min_n:
        row["skip_reason"] = f"n<{min_n}"
        return row
    if not has_variation(work[outcome]) or not has_variation(work[predictor]):
        row["skip_reason"] = "no_variation"
        return row

    y = zscore(work[outcome]).astype(float)
    x, names = make_design_matrix(work, predictor)
    model = pd.concat([y.rename("y"), x], axis=1).replace([np.inf, -np.inf], np.nan).dropna()
    row["nobs"] = int(len(model))
    if len(model) < min_n:
        row["skip_reason"] = f"complete_case_n<{min_n}"
        return row

    y_arr = model["y"].to_numpy(dtype=float)
    x_arr = model[names].to_numpy(dtype=float)
    if x_arr.shape[0] <= x_arr.shape[1]:
        row["skip_reason"] = "insufficient_degrees_of_freedom"
        return row

    beta, *_ = np.linalg.lstsq(x_arr, y_arr, rcond=None)
    fitted = x_arr.dot(beta)
    resid = y_arr - fitted
    sst = float(np.sum((y_arr - y_arr.mean()) ** 2))
    if sst > 0:
        row["r_squared"] = float(1 - np.sum(resid**2) / sst)

    xtx_inv = np.linalg.pinv(x_arr.T.dot(x_arr))
    meat = x_arr.T.dot(np.diag(resid**2)).dot(x_arr)
    scale = x_arr.shape[0] / max(1, x_arr.shape[0] - x_arr.shape[1])
    cov = scale * xtx_inv.dot(meat).dot(xtx_inv)
    se = np.sqrt(np.clip(np.diag(cov), 0, np.inf))

    predictor_name = f"z_{predictor}"
    if predictor_name not in names:
        row["skip_reason"] = "predictor_dropped"
        return row
    idx = names.index(predictor_name)
    row["coefficient"] = float(beta[idx])
    row["std_error_hc1"] = float(se[idx])
    row["skip_reason"] = ""
    return row


def compute_ols(panel: pd.DataFrame, min_n: int) -> pd.DataFrame:
    rows = []
    for outcome in OUTCOMES:
        for predictor in PREDICTORS:
            rows.append(run_ols_one(panel, outcome, predictor, min_n))
    return pd.DataFrame(rows)


def write_parquet_optional(df: pd.DataFrame, path: Path) -> tuple[bool, str]:
    try:
        df.to_parquet(path, index=False)
        return True, ""
    except Exception as exc:
        return False, str(exc)


def wbes_download_candidates(dataset: dict[str, object]) -> list[str]:
    catalog_id = str(dataset["catalog_id"])
    return [
        f"https://microdata.worldbank.org/index.php/catalog/{catalog_id}/download/F1",
        f"https://microdata.worldbank.org/catalog/{catalog_id}/download/F1",
    ]


def validate_stata_file(path: Path) -> tuple[bool, str]:
    try:
        import pyreadstat

        pyreadstat.read_dta(str(path), metadataonly=True)
        return True, ""
    except Exception as pyreadstat_exc:
        try:
            reader = pd.read_stata(path, iterator=True, convert_categoricals=False)
            reader.close()
            return True, ""
        except Exception as pandas_exc:
            return False, f"pyreadstat: {pyreadstat_exc}; pandas: {pandas_exc}"


def try_download_wbes_dataset(dataset: dict[str, object], wbes_dir: Path) -> dict:
    wbes_dir.mkdir(parents=True, exist_ok=True)
    path = wbes_dir / str(dataset["filename"])
    result = {
        "iso3": dataset["iso3"],
        "country": dataset["country"],
        "catalog_id": dataset["catalog_id"],
        "catalog_url": dataset["catalog_url"],
        "data_dictionary_url": dataset["data_dictionary_url"],
        "local_path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
        "found_existing": path.exists(),
        "download_attempted": False,
        "downloaded": False,
        "valid_stata_file": False,
        "attempts": [],
        "error": "",
    }
    if path.exists():
        valid, error = validate_stata_file(path)
        result["valid_stata_file"] = valid
        result["error"] = "" if valid else error
        return result

    for url in wbes_download_candidates(dataset):
        result["download_attempted"] = True
        attempt = {
            "url": url,
            "status_code": None,
            "content_type": "",
            "bytes": 0,
            "saved": False,
            "error": "",
        }
        tmp_path: Path | None = None
        try:
            response = requests.get(url, timeout=(3, 5))
            attempt["status_code"] = int(response.status_code)
            attempt["content_type"] = response.headers.get("content-type", "")
            attempt["bytes"] = int(len(response.content))
            response.raise_for_status()
            head = response.content[:2048].lstrip().lower()
            if "html" in attempt["content_type"].lower() or head.startswith(b"<!doctype") or b"<html" in head:
                attempt["error"] = "response_is_html_not_stata"
                result["attempts"].append(attempt)
                continue

            with tempfile.NamedTemporaryFile(delete=False, dir=wbes_dir, suffix=".dta") as tmp:
                tmp.write(response.content)
                tmp_path = Path(tmp.name)
            valid, error = validate_stata_file(tmp_path)
            if not valid:
                attempt["error"] = f"invalid_stata_file: {error}"
                tmp_path.unlink(missing_ok=True)
                result["attempts"].append(attempt)
                continue

            tmp_path.replace(path)
            attempt["saved"] = True
            result["downloaded"] = True
            result["valid_stata_file"] = True
            result["attempts"].append(attempt)
            return result
        except Exception as exc:
            attempt["error"] = str(exc)
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)
            result["attempts"].append(attempt)

    result["error"] = "No direct public Stata download candidate succeeded. Download manually from the catalog URL."
    return result


def column_lookup(df: pd.DataFrame) -> dict[str, str]:
    return {str(column).lower(): str(column) for column in df.columns}


def pick_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    lookup = column_lookup(df)
    for candidate in candidates:
        column = lookup.get(candidate.lower())
        if column is not None:
            return column
    return None


def get_column(df: pd.DataFrame, name: str) -> pd.Series:
    column = pick_column(df, [name])
    if column is None:
        return pd.Series(np.nan, index=df.index)
    return df[column]


def clean_numeric(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    values = values.mask(values.isin([-9, -8, -7, -6, -5, -4, -3, -2, -1]))
    return values.astype(float)


def clean_percent(series: pd.Series) -> pd.Series:
    values = clean_numeric(series)
    return values.where((values >= 0) & (values <= 100))


def clean_positive(series: pd.Series) -> pd.Series:
    values = clean_numeric(series)
    return values.where(values > 0)


def clean_text(series: pd.Series) -> pd.Series:
    values = series.astype("string").str.strip()
    missing = values.str.lower().isin(["", "nan", "none", "-9", "-8", "-7", "-6", "-5", "-4", "-3", "-2", "-1"])
    return values.mask(missing)


def yes_no_indicator(series: pd.Series) -> pd.Series:
    out = pd.Series(np.nan, index=series.index, dtype=float)
    numeric = clean_numeric(series)
    out = out.mask(numeric == 1, 1.0)
    out = out.mask(numeric.isin([0, 2]), 0.0)
    text = clean_text(series).str.lower()
    out = out.mask(text.isin(["yes", "y", "true"]), 1.0)
    out = out.mask(text.isin(["no", "n", "false"]), 0.0)
    return out


def weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    data = pd.DataFrame({"value": pd.to_numeric(values, errors="coerce"), "weight": pd.to_numeric(weights, errors="coerce")})
    data = data.dropna()
    data = data[data["weight"] > 0]
    if data.empty:
        return np.nan
    return float(np.average(data["value"], weights=data["weight"]))


def weighted_median(values: pd.Series, weights: pd.Series) -> float:
    data = pd.DataFrame({"value": pd.to_numeric(values, errors="coerce"), "weight": pd.to_numeric(weights, errors="coerce")})
    data = data.dropna().sort_values("value")
    data = data[data["weight"] > 0]
    if data.empty:
        return np.nan
    cutoff = data["weight"].sum() / 2
    return float(data.loc[data["weight"].cumsum() >= cutoff, "value"].iloc[0])


def weighted_corr(x: pd.Series, y: pd.Series, weights: pd.Series) -> float:
    data = pd.DataFrame(
        {
            "x": pd.to_numeric(x, errors="coerce"),
            "y": pd.to_numeric(y, errors="coerce"),
            "weight": pd.to_numeric(weights, errors="coerce"),
        }
    ).dropna()
    data = data[data["weight"] > 0]
    if len(data) < 2 or data["x"].nunique() < 2 or data["y"].nunique() < 2:
        return np.nan
    x_mean = np.average(data["x"], weights=data["weight"])
    y_mean = np.average(data["y"], weights=data["weight"])
    x_centered = data["x"] - x_mean
    y_centered = data["y"] - y_mean
    cov = np.average(x_centered * y_centered, weights=data["weight"])
    x_var = np.average(x_centered**2, weights=data["weight"])
    y_var = np.average(y_centered**2, weights=data["weight"])
    if x_var <= 0 or y_var <= 0:
        return np.nan
    return float(cov / math.sqrt(x_var * y_var))


def normalize_wbes_dataset(path: Path, dataset: dict[str, object]) -> tuple[pd.DataFrame, dict]:
    status = {
        "iso3": dataset["iso3"],
        "country": dataset["country"],
        "path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
        "rows_raw": 0,
        "rows_normalized": 0,
        "columns_available": [],
        "weight_column": "",
        "employment_columns_used": [],
        "survey_year_source": "fallback",
        "error": "",
    }
    try:
        raw = pd.read_stata(path, convert_categoricals=False, preserve_dtypes=False)
    except Exception as exc:
        status["error"] = str(exc)
        return pd.DataFrame(), status

    status["rows_raw"] = int(len(raw))
    status["columns_available"] = [str(column) for column in raw.columns]
    index = raw.index

    out = pd.DataFrame(index=index)
    out["country_iso3"] = str(dataset["iso3"])
    out["country_name"] = str(dataset["country"])
    out["catalog_id"] = str(dataset["catalog_id"])
    out["source_file"] = path.name

    id_col = pick_column(raw, WBES_ID_CANDIDATES)
    if id_col is None:
        out["firm_id"] = [f"{dataset['iso3']}_{i}" for i in range(len(raw))]
    else:
        out["firm_id"] = clean_text(raw[id_col]).fillna(pd.Series([f"{dataset['iso3']}_{i}" for i in range(len(raw))], index=index))

    year_col = pick_column(raw, WBES_YEAR_CANDIDATES)
    if year_col is None:
        out["survey_year"] = int(dataset["fallback_survey_year"])
    else:
        year_values = clean_numeric(raw[year_col])
        if year_values.notna().any():
            out["survey_year"] = year_values.fillna(int(dataset["fallback_survey_year"])).astype(int)
            status["survey_year_source"] = year_col
        else:
            out["survey_year"] = int(dataset["fallback_survey_year"])

    for out_col, source_col in WBES_NUMERIC_FIELDS.items():
        out[out_col] = clean_percent(get_column(raw, source_col)) if out_col.endswith("_share") else clean_positive(get_column(raw, source_col))

    out["direct_importer"] = yes_no_indicator(get_column(raw, WBES_OPTIONAL_FIELDS["direct_importer_raw"]))

    for out_col, source_col in WBES_OPTIONAL_FIELDS.items():
        if out_col == "direct_importer_raw":
            continue
        out[out_col] = clean_text(get_column(raw, source_col))

    employment_parts = []
    for employment_col in ["l1", "l6"]:
        source = get_column(raw, employment_col)
        if source.notna().any():
            cleaned = clean_positive(source)
            if cleaned.notna().any():
                employment_parts.append(cleaned)
                status["employment_columns_used"].append(employment_col)
    if employment_parts:
        employment = employment_parts[0]
        for part in employment_parts[1:]:
            employment = employment.combine_first(part)
        out["employment"] = employment
    else:
        out["employment"] = np.nan

    weight_col = pick_column(raw, WBES_WEIGHT_CANDIDATES)
    if weight_col is None:
        out["weight"] = 1.0
    else:
        weights = clean_positive(raw[weight_col]).fillna(1.0)
        out["weight"] = weights.where(weights > 0, 1.0)
        status["weight_column"] = weight_col

    export_parts = out[["indirect_export_share", "direct_export_share"]]
    out["export_share"] = export_parts.sum(axis=1, min_count=1).clip(lower=0, upper=100)
    out["any_exporter"] = (out["export_share"] > 0).astype(float).where(out["export_share"].notna())
    out["direct_exporter"] = (out["direct_export_share"] > 0).astype(float).where(out["direct_export_share"].notna())
    out["log_sales"] = safe_log(out["sales"])
    out["log_employment"] = safe_log(out["employment"])
    out["direct_export_value_proxy"] = out["sales"] * out["direct_export_share"] / 100
    out["size_class"] = pd.cut(
        out["employment"],
        bins=[-np.inf, 19, 99, np.inf],
        labels=["small_<20", "medium_20_99", "large_100_plus"],
    ).astype("string")

    ordered_cols = [
        "country_iso3",
        "country_name",
        "survey_year",
        "catalog_id",
        "source_file",
        "firm_id",
        "weight",
        "sales",
        "log_sales",
        "employment",
        "log_employment",
        "size_class",
        "sector",
        "region",
        "main_activity_share",
        "national_sales_share",
        "indirect_export_share",
        "direct_export_share",
        "export_share",
        "any_exporter",
        "direct_exporter",
        "direct_export_value_proxy",
        "foreign_input_share",
        "direct_importer",
        "main_export_destination",
        "main_import_origin",
    ]
    out = out[ordered_cols]
    status["rows_normalized"] = int(len(out))
    return out.reset_index(drop=True), status


def load_wbes_panel(wbes_dir: Path) -> tuple[pd.DataFrame, list[dict], list[dict]]:
    download_results = []
    load_statuses = []
    frames = []
    wbes_dir.mkdir(parents=True, exist_ok=True)

    for dataset in WBES_DATASETS:
        download_status = try_download_wbes_dataset(dataset, wbes_dir)
        download_results.append(download_status)
        path = wbes_dir / str(dataset["filename"])
        if not path.exists() or not download_status.get("valid_stata_file", False):
            load_statuses.append(
                {
                    "iso3": dataset["iso3"],
                    "country": dataset["country"],
                    "path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
                    "rows_raw": 0,
                    "rows_normalized": 0,
                    "columns_available": [],
                    "weight_column": "",
                    "employment_columns_used": [],
                    "survey_year_source": "",
                    "error": "file_missing_or_invalid",
                }
            )
            continue
        panel, status = normalize_wbes_dataset(path, dataset)
        load_statuses.append(status)
        if not panel.empty:
            frames.append(panel)

    if not frames:
        return pd.DataFrame(columns=wbes_panel_columns()), download_results, load_statuses
    return pd.concat(frames, ignore_index=True), download_results, load_statuses


def wbes_panel_columns() -> list[str]:
    return [
        "country_iso3",
        "country_name",
        "survey_year",
        "catalog_id",
        "source_file",
        "firm_id",
        "weight",
        "sales",
        "log_sales",
        "employment",
        "log_employment",
        "size_class",
        "sector",
        "region",
        "main_activity_share",
        "national_sales_share",
        "indirect_export_share",
        "direct_export_share",
        "export_share",
        "any_exporter",
        "direct_exporter",
        "direct_export_value_proxy",
        "foreign_input_share",
        "direct_importer",
        "main_export_destination",
        "main_import_origin",
    ]


def compute_wbes_country_summary(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if panel.empty:
        for dataset in WBES_DATASETS:
            rows.append(
                {
                    "country_iso3": dataset["iso3"],
                    "country_name": dataset["country"],
                    "survey_year": dataset["fallback_survey_year"],
                    "n_firms": 0,
                    "weighted_firms": 0.0,
                    "n_any_exporters": 0,
                    "n_direct_exporters": 0,
                    "weighted_any_exporter_share": np.nan,
                    "weighted_direct_exporter_share": np.nan,
                    "median_export_share_exporters": np.nan,
                    "median_direct_export_share_direct_exporters": np.nan,
                    "main_activity_mean_exporters": np.nan,
                    "main_activity_mean_nonexporters": np.nan,
                    "main_activity_median_exporters": np.nan,
                    "main_activity_median_nonexporters": np.nan,
                    "share_main_activity_ge_50_exporters": np.nan,
                    "share_main_activity_ge_75_exporters": np.nan,
                    "share_main_activity_ge_90_exporters": np.nan,
                    "skip_reason": "wbes_file_missing_or_invalid",
                }
            )
        return pd.DataFrame(rows)

    for keys, group in panel.groupby(["country_iso3", "country_name", "survey_year"], dropna=False):
        iso3, country, year = keys
        exporters = group[group["any_exporter"] == 1]
        nonexporters = group[group["any_exporter"] == 0]
        direct_exporters = group[group["direct_exporter"] == 1]
        rows.append(
            {
                "country_iso3": iso3,
                "country_name": country,
                "survey_year": int(year) if pd.notna(year) else np.nan,
                "n_firms": int(len(group)),
                "weighted_firms": float(pd.to_numeric(group["weight"], errors="coerce").fillna(0).sum()),
                "n_any_exporters": int((group["any_exporter"] == 1).sum()),
                "n_direct_exporters": int((group["direct_exporter"] == 1).sum()),
                "weighted_any_exporter_share": weighted_mean(group["any_exporter"], group["weight"]),
                "weighted_direct_exporter_share": weighted_mean(group["direct_exporter"], group["weight"]),
                "median_export_share_exporters": weighted_median(exporters["export_share"], exporters["weight"]) if not exporters.empty else np.nan,
                "median_direct_export_share_direct_exporters": weighted_median(direct_exporters["direct_export_share"], direct_exporters["weight"]) if not direct_exporters.empty else np.nan,
                "main_activity_mean_exporters": weighted_mean(exporters["main_activity_share"], exporters["weight"]) if not exporters.empty else np.nan,
                "main_activity_mean_nonexporters": weighted_mean(nonexporters["main_activity_share"], nonexporters["weight"]) if not nonexporters.empty else np.nan,
                "main_activity_median_exporters": weighted_median(exporters["main_activity_share"], exporters["weight"]) if not exporters.empty else np.nan,
                "main_activity_median_nonexporters": weighted_median(nonexporters["main_activity_share"], nonexporters["weight"]) if not nonexporters.empty else np.nan,
                "share_main_activity_ge_50_exporters": weighted_mean((exporters["main_activity_share"] >= 50).astype(float), exporters["weight"]) if not exporters.empty else np.nan,
                "share_main_activity_ge_75_exporters": weighted_mean((exporters["main_activity_share"] >= 75).astype(float), exporters["weight"]) if not exporters.empty else np.nan,
                "share_main_activity_ge_90_exporters": weighted_mean((exporters["main_activity_share"] >= 90).astype(float), exporters["weight"]) if not exporters.empty else np.nan,
                "skip_reason": "",
            }
        )
    return pd.DataFrame(rows).sort_values(["country_iso3", "survey_year"]).reset_index(drop=True)


def compute_wbes_correlations(panel: pd.DataFrame, min_n: int) -> pd.DataFrame:
    rows = []
    groups: list[tuple[str, str, pd.DataFrame]] = [("ALL", "All loaded WBES countries", panel)]
    if not panel.empty:
        groups.extend((str(iso3), str(group["country_name"].iloc[0]), group) for iso3, group in panel.groupby("country_iso3"))

    if panel.empty:
        groups = [(str(dataset["iso3"]), str(dataset["country"]), panel) for dataset in WBES_DATASETS]

    for iso3, country, group in groups:
        for outcome in WBES_OUTCOMES:
            for predictor in WBES_PREDICTORS:
                row = {
                    "country_iso3": iso3,
                    "country_name": country,
                    "outcome": outcome,
                    "predictor": predictor,
                    "nobs": 0,
                    "pearson": np.nan,
                    "spearman": np.nan,
                    "weighted_pearson": np.nan,
                    "skip_reason": "",
                }
                if group.empty or outcome not in group.columns or predictor not in group.columns:
                    row["skip_reason"] = "wbes_file_missing_or_invalid" if group.empty else "missing_column"
                    rows.append(row)
                    continue
                work = group[[outcome, predictor, "weight"]].apply(pd.to_numeric, errors="coerce").dropna()
                row["nobs"] = int(len(work))
                if len(work) < min_n:
                    row["skip_reason"] = f"n<{min_n}"
                elif not has_variation(work[outcome]) or not has_variation(work[predictor]):
                    row["skip_reason"] = "no_variation"
                else:
                    row["pearson"] = float(work[outcome].corr(work[predictor], method="pearson"))
                    row["spearman"] = float(work[outcome].corr(work[predictor], method="spearman"))
                    row["weighted_pearson"] = weighted_corr(work[predictor], work[outcome], work["weight"])
                rows.append(row)
    return pd.DataFrame(rows)


def limited_fe_series(series: pd.Series, max_categories: int = 40) -> pd.Series:
    values = clean_text(series).fillna("missing")
    counts = values.value_counts(dropna=False)
    if len(counts) <= max_categories:
        return values
    keep = set(counts.head(max_categories).index)
    return values.where(values.isin(keep), "other")


def make_wbes_design_matrix(work: pd.DataFrame, predictors: list[str], fixed_effects: list[str]) -> tuple[pd.DataFrame, list[str], list[str]]:
    parts = [pd.Series(1.0, index=work.index, name="intercept")]
    predictor_names = []
    for predictor in predictors:
        if predictor not in work.columns or not has_variation(work[predictor]):
            continue
        values = zscore(work[predictor]).rename(f"z_{predictor}")
        if values.notna().any():
            parts.append(values)
            predictor_names.append(values.name)

    fe_names = []
    for fixed_effect in fixed_effects:
        if fixed_effect not in work.columns:
            continue
        values = limited_fe_series(work[fixed_effect])
        if values.nunique(dropna=False) <= 1:
            continue
        dummies = pd.get_dummies(values, prefix=fixed_effect, drop_first=True, dtype=float)
        for column in dummies.columns:
            if dummies[column].std(ddof=0) > 0:
                parts.append(dummies[column].rename(column))
                fe_names.append(column)

    x = pd.concat(parts, axis=1).replace([np.inf, -np.inf], np.nan)
    keep = []
    for column in x.columns:
        values = pd.to_numeric(x[column], errors="coerce")
        if column == "intercept" or values.std(ddof=0) > 0:
            keep.append(column)
    x = x[keep].astype(float)
    return x, [column for column in x.columns if column in predictor_names], fe_names


def run_wbes_ols_for_outcome(panel: pd.DataFrame, outcome: str, min_n: int) -> pd.DataFrame:
    rows = []
    base = {
        "outcome": outcome,
        "coefficient": np.nan,
        "std_error_hc1": np.nan,
        "nobs": 0,
        "r_squared": np.nan,
        "weighted": True,
        "standardized_predictor": True,
        "outcome_scale": "native",
        "fixed_effects": "country_iso3,survey_year,sector,region",
        "skip_reason": "",
    }
    if panel.empty or outcome not in panel.columns:
        for predictor in WBES_PREDICTORS:
            rows.append({**base, "predictor": predictor, "skip_reason": "wbes_file_missing_or_invalid" if panel.empty else "missing_outcome"})
        return pd.DataFrame(rows)

    predictors = [predictor for predictor in WBES_PREDICTORS if predictor in panel.columns and has_variation(panel[predictor])]
    if not predictors:
        for predictor in WBES_PREDICTORS:
            rows.append({**base, "predictor": predictor, "skip_reason": "no_usable_predictors"})
        return pd.DataFrame(rows)

    cols = [outcome, "weight", *predictors, "country_iso3", "survey_year", "sector", "region"]
    work = panel[[col for col in cols if col in panel.columns]].copy()
    for col in [outcome, "weight", *predictors]:
        if col in work.columns:
            work[col] = pd.to_numeric(work[col], errors="coerce")
    work = work.dropna(subset=[outcome, "weight", *predictors])
    work = work[work["weight"] > 0]

    for predictor in WBES_PREDICTORS:
        rows.append({**base, "predictor": predictor, "skip_reason": "predictor_not_in_model"})

    if len(work) < min_n:
        for row in rows:
            if row["predictor"] in predictors:
                row["nobs"] = int(len(work))
                row["skip_reason"] = f"n<{min_n}"
        return pd.DataFrame(rows)
    if not has_variation(work[outcome]):
        for row in rows:
            if row["predictor"] in predictors:
                row["nobs"] = int(len(work))
                row["skip_reason"] = "no_outcome_variation"
        return pd.DataFrame(rows)

    x, predictor_names, _fe_names = make_wbes_design_matrix(work, predictors, ["country_iso3", "survey_year", "sector", "region"])
    model = pd.concat([work[outcome].rename("y"), work["weight"].rename("weight"), x], axis=1).replace([np.inf, -np.inf], np.nan).dropna()
    names = list(x.columns)
    if len(model) < min_n or len(model) <= len(names):
        reason = f"complete_case_n<{min_n}" if len(model) < min_n else "insufficient_degrees_of_freedom"
        for row in rows:
            if row["predictor"] in predictors:
                row["nobs"] = int(len(model))
                row["skip_reason"] = reason
        return pd.DataFrame(rows)

    y_arr = model["y"].to_numpy(dtype=float)
    weights = model["weight"].to_numpy(dtype=float)
    x_arr = model[names].to_numpy(dtype=float)
    sqrt_w = np.sqrt(weights)
    x_weighted = x_arr * sqrt_w[:, None]
    y_weighted = y_arr * sqrt_w
    beta, *_ = np.linalg.lstsq(x_weighted, y_weighted, rcond=None)
    fitted = x_arr.dot(beta)
    resid = y_arr - fitted
    y_bar = float(np.average(y_arr, weights=weights))
    sst = float(np.sum(weights * (y_arr - y_bar) ** 2))
    r_squared = np.nan if sst <= 0 else float(1 - np.sum(weights * resid**2) / sst)

    xtwx_inv = np.linalg.pinv(x_arr.T.dot(weights[:, None] * x_arr))
    meat_factor = weights * resid
    meat = (x_arr * meat_factor[:, None]).T.dot(x_arr * meat_factor[:, None])
    scale = x_arr.shape[0] / max(1, x_arr.shape[0] - x_arr.shape[1])
    cov = scale * xtwx_inv.dot(meat).dot(xtwx_inv)
    se = np.sqrt(np.clip(np.diag(cov), 0, np.inf))

    for row in rows:
        predictor_name = f"z_{row['predictor']}"
        if predictor_name not in predictor_names or predictor_name not in names:
            continue
        idx = names.index(predictor_name)
        row["coefficient"] = float(beta[idx])
        row["std_error_hc1"] = float(se[idx])
        row["nobs"] = int(len(model))
        row["r_squared"] = r_squared
        row["skip_reason"] = ""
    return pd.DataFrame(rows)


def compute_wbes_ols(panel: pd.DataFrame, min_n: int) -> pd.DataFrame:
    return pd.concat([run_wbes_ols_for_outcome(panel, outcome, min_n) for outcome in WBES_OUTCOMES], ignore_index=True)


def concentration_from_shares(values: pd.Series) -> tuple[float, float]:
    shares = pd.to_numeric(values, errors="coerce").dropna()
    shares = shares[shares > 0].sort_values(ascending=False)
    total = shares.sum()
    if total <= 0:
        return np.nan, np.nan
    normalized = shares / total
    return float(np.sum(normalized**2)), float(normalized.head(5).sum())


def compute_wbes_destination_summary(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if panel.empty:
        for dataset in WBES_DATASETS:
            rows.append(
                {
                    "country_iso3": dataset["iso3"],
                    "country_name": dataset["country"],
                    "survey_year": dataset["fallback_survey_year"],
                    "firms_with_main_destination": 0,
                    "destination_count": 0,
                    "weighted_destination_hhi_by_firms": np.nan,
                    "weighted_top_5_destination_share_by_firms": np.nan,
                    "proxy_value_destination_hhi": np.nan,
                    "proxy_value_top_5_destination_share": np.nan,
                    "top_destination_by_firms": "",
                    "top_destination_firm_share": np.nan,
                    "top_destination_by_proxy_value": "",
                    "top_destination_proxy_value_share": np.nan,
                    "skip_reason": "wbes_file_missing_or_invalid",
                }
            )
        return pd.DataFrame(rows)

    for keys, group in panel.groupby(["country_iso3", "country_name", "survey_year"], dropna=False):
        iso3, country, year = keys
        work = group[(group["direct_exporter"] == 1) & group["main_export_destination"].notna()].copy()
        if work.empty:
            rows.append(
                {
                    "country_iso3": iso3,
                    "country_name": country,
                    "survey_year": int(year) if pd.notna(year) else np.nan,
                    "firms_with_main_destination": 0,
                    "destination_count": 0,
                    "weighted_destination_hhi_by_firms": np.nan,
                    "weighted_top_5_destination_share_by_firms": np.nan,
                    "proxy_value_destination_hhi": np.nan,
                    "proxy_value_top_5_destination_share": np.nan,
                    "top_destination_by_firms": "",
                    "top_destination_firm_share": np.nan,
                    "top_destination_by_proxy_value": "",
                    "top_destination_proxy_value_share": np.nan,
                    "skip_reason": "no_direct_exporters_with_main_destination",
                }
            )
            continue

        destination = (
            work.groupby("main_export_destination", dropna=False)
            .agg(
                weighted_firms=("weight", "sum"),
                firm_count=("firm_id", "count"),
                proxy_value=("direct_export_value_proxy", lambda s: float(np.nansum(s * work.loc[s.index, "weight"]))),
            )
            .reset_index()
        )
        firm_hhi, firm_top5 = concentration_from_shares(destination["weighted_firms"])
        value_hhi, value_top5 = concentration_from_shares(destination["proxy_value"])
        firm_total = destination["weighted_firms"].sum()
        value_total = destination["proxy_value"].sum()
        top_firm = destination.sort_values("weighted_firms", ascending=False).iloc[0]
        top_value = destination.sort_values("proxy_value", ascending=False).iloc[0] if value_total > 0 else None
        rows.append(
            {
                "country_iso3": iso3,
                "country_name": country,
                "survey_year": int(year) if pd.notna(year) else np.nan,
                "firms_with_main_destination": int(len(work)),
                "destination_count": int(destination["main_export_destination"].nunique()),
                "weighted_destination_hhi_by_firms": firm_hhi,
                "weighted_top_5_destination_share_by_firms": firm_top5,
                "proxy_value_destination_hhi": value_hhi,
                "proxy_value_top_5_destination_share": value_top5,
                "top_destination_by_firms": str(top_firm["main_export_destination"]),
                "top_destination_firm_share": float(top_firm["weighted_firms"] / firm_total) if firm_total > 0 else np.nan,
                "top_destination_by_proxy_value": "" if top_value is None else str(top_value["main_export_destination"]),
                "top_destination_proxy_value_share": np.nan if top_value is None or value_total <= 0 else float(top_value["proxy_value"] / value_total),
                "skip_reason": "",
            }
        )
    return pd.DataFrame(rows).sort_values(["country_iso3", "survey_year"]).reset_index(drop=True)


def make_wbes_figures(
    panel: pd.DataFrame,
    destination_summary: pd.DataFrame,
    skip_figures: bool,
) -> tuple[bool, list[str], str]:
    if skip_figures:
        return False, [], "skip_figures"
    if panel.empty:
        return False, [], "no_wbes_rows"
    try:
        import matplotlib.pyplot as plt
    except Exception as exc:
        return False, [], f"plot_import_failed: {exc}"

    written: list[str] = []
    plt.style.use("default")

    size_work = panel.dropna(subset=["size_class", "any_exporter", "weight"]).copy()
    if not size_work.empty:
        size_rows = []
        for (country, size_class), group in size_work.groupby(["country_name", "size_class"], dropna=False):
            size_rows.append(
                {
                    "label": f"{country}\n{size_class}",
                    "exporter_share": weighted_mean(group["any_exporter"], group["weight"]),
                }
            )
        size_df = pd.DataFrame(size_rows).dropna()
        if not size_df.empty:
            fig, ax = plt.subplots(figsize=(9, 5))
            ax.bar(np.arange(len(size_df)), size_df["exporter_share"], color="#4C78A8")
            ax.set_xticks(np.arange(len(size_df)))
            ax.set_xticklabels(size_df["label"], rotation=35, ha="right", fontsize=8)
            ax.set_ylim(0, max(1, float(size_df["exporter_share"].max()) * 1.15))
            ax.set_ylabel("Weighted exporter share")
            ax.set_title("WBES exporter status by firm size")
            ax.grid(axis="y", linewidth=0.4, alpha=0.35)
            fig.tight_layout()
            path = EX08_FIGURES / "wbes_export_status_by_size.png"
            fig.savefig(path, dpi=200)
            plt.close(fig)
            written.append(str(path.relative_to(ROOT)))

    scatter = panel.dropna(subset=["main_activity_share", "export_share", "country_name"]).copy()
    if not scatter.empty:
        if len(scatter) > 5000:
            scatter = scatter.sample(5000, random_state=8)
        countries = sorted(scatter["country_name"].dropna().unique())
        colors = dict(zip(countries, plt.cm.tab10(np.linspace(0, 1, max(1, len(countries))))))
        fig, ax = plt.subplots(figsize=(8, 5))
        for country, group in scatter.groupby("country_name"):
            ax.scatter(
                group["main_activity_share"],
                group["export_share"],
                s=22,
                alpha=0.55,
                label=country,
                color=colors.get(country),
                edgecolors="none",
            )
        ax.set_xlabel("Main activity/product-line share of sales")
        ax.set_ylabel("Export share of sales")
        ax.set_title("WBES export intensity and product/activity focus")
        ax.grid(True, linewidth=0.4, alpha=0.35)
        ax.legend(frameon=False, fontsize=8)
        fig.tight_layout()
        path = EX08_FIGURES / "wbes_export_intensity_vs_main_activity_share.png"
        fig.savefig(path, dpi=200)
        plt.close(fig)
        written.append(str(path.relative_to(ROOT)))

    dest = destination_summary[destination_summary["skip_reason"] == ""].copy()
    if not dest.empty:
        dest["label"] = dest["country_name"].astype(str) + "\n" + dest["survey_year"].astype(str)
        fig, ax = plt.subplots(figsize=(8, 4.5))
        ax.bar(np.arange(len(dest)), dest["weighted_top_5_destination_share_by_firms"], color="#59A14F")
        ax.set_xticks(np.arange(len(dest)))
        ax.set_xticklabels(dest["label"], rotation=30, ha="right", fontsize=8)
        ax.set_ylim(0, 1)
        ax.set_ylabel("Top 5 main-destination share")
        ax.set_title("WBES main export destination concentration")
        ax.grid(axis="y", linewidth=0.4, alpha=0.35)
        fig.tight_layout()
        path = EX08_FIGURES / "wbes_main_destination_concentration.png"
        fig.savefig(path, dpi=200)
        plt.close(fig)
        written.append(str(path.relative_to(ROOT)))

    return bool(written), written, "" if written else "no_plottable_wbes_data"


def make_edd_figures(panel: pd.DataFrame, correlations: pd.DataFrame, skip_figures: bool) -> tuple[bool, list[str], str]:
    if skip_figures:
        return False, [], "skip_figures"
    try:
        import matplotlib.pyplot as plt
    except Exception as exc:
        return False, [], f"plot_import_failed: {exc}"

    written: list[str] = []
    plt.style.use("default")

    scatter_specs = [
        ("exporter_hhi", "product_gini", "exporter_hhi_vs_product_gini.png"),
        ("top_1pct_exporter_share", "product_partner_cell_gini", "top1_exporter_share_vs_cell_gini.png"),
        ("destinations_per_exporter_mean", "partner_gini", "destinations_per_exporter_vs_partner_gini.png"),
    ]
    for x_col, y_col, filename in scatter_specs:
        work = panel[[x_col, y_col, "year", "iso3"]].dropna().copy()
        if work.empty:
            continue
        fig, ax = plt.subplots(figsize=(8, 5))
        points = ax.scatter(
            work[x_col],
            work[y_col],
            c=work["year"],
            cmap="viridis",
            s=45,
            alpha=0.8,
            edgecolors="none",
        )
        x_numeric = pd.to_numeric(work[x_col], errors="coerce")
        y_numeric = pd.to_numeric(work[y_col], errors="coerce")
        if x_numeric.nunique(dropna=True) > 1 and y_numeric.nunique(dropna=True) > 1:
            slope, intercept = np.polyfit(x_numeric, y_numeric, 1)
            x_line = np.linspace(float(x_numeric.min()), float(x_numeric.max()), 100)
            ax.plot(x_line, intercept + slope * x_line, color="black", linewidth=1)
        fig.colorbar(points, ax=ax, label="Year")
        ax.set_title(f"{x_col} vs {y_col}")
        ax.set_xlabel(x_col)
        ax.set_ylabel(y_col)
        ax.grid(True, linewidth=0.4, alpha=0.35)
        fig.tight_layout()
        path = EX08_FIGURES / filename
        fig.savefig(path, dpi=200)
        plt.close(fig)
        written.append(str(path.relative_to(ROOT)))

    heat = correlations[correlations["skip_reason"] == ""].pivot(index="outcome", columns="predictor", values="spearman")
    if not heat.empty:
        fig, ax = plt.subplots(figsize=(11, 5))
        image = ax.imshow(heat.to_numpy(dtype=float), cmap="coolwarm", vmin=-1, vmax=1, aspect="auto")
        ax.set_xticks(np.arange(len(heat.columns)))
        ax.set_yticks(np.arange(len(heat.index)))
        ax.set_xticklabels(heat.columns, rotation=45, ha="right", fontsize=8)
        ax.set_yticklabels(heat.index, fontsize=8)
        ax.set_title("Exercise 8 EDD proxy correlations")
        fig.colorbar(image, ax=ax, label="Spearman correlation")
        fig.tight_layout()
        path = EX08_FIGURES / "edd_spearman_correlation_heatmap.png"
        fig.savefig(path, dpi=200)
        plt.close(fig)
        written.append(str(path.relative_to(ROOT)))

    return True, written, ""


def markdown_table(df: pd.DataFrame, max_rows: int = 12) -> str:
    if df.empty:
        return "No rows."
    view = df.head(max_rows).copy()
    cols = list(view.columns)
    lines = [
        "| " + " | ".join(cols) + " |",
        "| " + " | ".join(["---"] * len(cols)) + " |",
    ]
    for _, row in view.iterrows():
        values = []
        for col in cols:
            value = row[col]
            if isinstance(value, float):
                values.append("" if math.isnan(value) else f"{value:.4f}")
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def top_rows(df: pd.DataFrame, value_col: str, columns: list[str], max_rows: int = 12) -> pd.DataFrame:
    if df.empty or value_col not in df.columns:
        return pd.DataFrame(columns=columns)
    usable = df[df.get("skip_reason", "") == ""].copy()
    if usable.empty:
        return pd.DataFrame(columns=columns)
    usable = usable.reindex(pd.to_numeric(usable[value_col], errors="coerce").abs().sort_values(ascending=False).index)
    return usable[[col for col in columns if col in usable.columns]].head(max_rows)


def write_memo(edd_result: dict | None, wbes_result: dict | None, source_details: dict) -> None:
    if edd_result is not None:
        edd_panel = edd_result["panel"]
        edd_country_count = int(edd_panel["iso3"].nunique()) if not edd_panel.empty else 0
        edd_year_min = int(edd_panel["year"].min()) if not edd_panel.empty else None
        edd_year_max = int(edd_panel["year"].max()) if not edd_panel.empty else None
        absent_targets = edd_result["absent_targets"]
        absent_text = ", ".join(absent_targets) if absent_targets else "None of India, China, or the United States are absent from the EDD pull."
        edd_corr = top_rows(
            edd_result["correlations"],
            "spearman",
            ["outcome", "predictor", "nobs", "pearson", "spearman"],
        )
        edd_ols = top_rows(
            edd_result["ols"],
            "coefficient",
            ["outcome", "predictor", "coefficient", "std_error_hc1", "nobs", "r_squared"],
        )
        edd_section = f"""## EDD Country-Year Proxy

- Merged EDD x Exercise 1 rows: {len(edd_panel)}
- Countries with overlap: {edd_country_count}
- Years with overlap: {edd_year_min}-{edd_year_max}
- EDD series used: {", ".join(SERIES.keys())}
- India/China/US absent from EDD country-year API pull: {absent_text}

EDD tells us whether countries with concentrated exporters also have concentrated national export products, destinations, or product-destination cells. It cannot show the products and destinations inside each firm.

### Strongest EDD Correlations

{markdown_table(edd_corr, max_rows=12)}

### Largest EDD Standardized OLS Coefficients

Outcome and single predictor are standardized. Controls are log total exports, log active counts where available, and year fixed effects.

{markdown_table(edd_ols, max_rows=12)}
"""
    else:
        edd_section = "## EDD Country-Year Proxy\n\nEDD was not run in this invocation.\n"

    if wbes_result is not None:
        firm_panel = wbes_result["firm_panel"]
        country_summary = wbes_result["country_summary"]
        missing = [
            f"{status['country']} ({status['local_path']})"
            for status in wbes_result["download_results"]
            if not status.get("valid_stata_file", False)
        ]
        missing_text = "\n".join(f"- {item}" for item in missing) if missing else "- None"
        wbes_corr = top_rows(
            wbes_result["correlations"],
            "weighted_pearson",
            ["country_iso3", "outcome", "predictor", "nobs", "pearson", "spearman", "weighted_pearson"],
        )
        wbes_ols = top_rows(
            wbes_result["ols"],
            "coefficient",
            ["outcome", "predictor", "coefficient", "std_error_hc1", "nobs", "r_squared"],
        )
        destination = wbes_result["destination_summary"]
        destination_view = destination[
            [
                col
                for col in [
                    "country_iso3",
                    "survey_year",
                    "firms_with_main_destination",
                    "destination_count",
                    "weighted_destination_hhi_by_firms",
                    "weighted_top_5_destination_share_by_firms",
                    "top_destination_by_firms",
                    "skip_reason",
                ]
                if col in destination.columns
            ]
        ]
        wbes_section = f"""## WBES Firm-Survey Proxy

- Normalized WBES firm rows: {len(firm_panel)}
- Countries with usable WBES rows: {firm_panel["country_iso3"].nunique() if not firm_panel.empty else 0}
- Expected WBES files that are missing or invalid:
{missing_text}

WBES tells us whether surveyed exporters in India, China, and the United States look specialized or broad by their main activity/product-line sales share, size, import status, and export intensity. It is firm survey evidence, not customs data: it does not observe every firm-product-destination export value.

### WBES Country Summary

{markdown_table(country_summary, max_rows=12)}

### Strongest WBES Exporter-Focus Correlations

{markdown_table(wbes_corr, max_rows=12)}

### WBES Exporter-Focus OLS

These are weighted NumPy least-squares models when survey weights are available; otherwise all weights equal one. Predictors are standardized, outcomes stay in native units.

{markdown_table(wbes_ols, max_rows=12)}

### WBES Main Destination Proxy

Destination concentration is based on each surveyed direct exporter's reported main export destination. Value shares use `sales * direct_export_share / 100`, so they are survey approximations, not customs export totals.

{markdown_table(destination_view, max_rows=12)}

Manual WBES download targets, if auto-download fails:

- India: `data/raw/wbes/India_2014_2022.dta` from https://microdata.worldbank.org/catalog/6494
- China: `data/raw/wbes/China-2024-full-data.dta` from https://microdata.worldbank.org/catalog/6676
- United States: `data/raw/wbes/United-States-2024-full-data.dta` from https://microdata.worldbank.org/catalog/6709
"""
    else:
        wbes_section = "## WBES Firm-Survey Proxy\n\nWBES was not run in this invocation.\n"

    memo = f"""# Exercise 8: EDD + WBES Public Proxy

Generated: {now_utc()}

## What This Tests

This is a public proxy for the firm-level core-portfolio exercise. It tests whether aggregate product, partner, and product-partner concentration plausibly lines up with exporter concentration, exporter scope, and firm survey measures of export focus.

It does **not** observe firm-product-destination customs values. Therefore it cannot directly prove whether a country's concentrated export products are the core products of a few firms. That gold-standard version still requires restricted customs microdata.

{edd_section}

{wbes_section}

## Interpretation Rule

If EDD exporter concentration lines up with aggregate concentration, and WBES exporters also look focused, firm concentration becomes a plausible mechanism. If EDD is weak or WBES exporters are broad, the explanation should lean more toward product-level comparative advantage, gravity, input-output linkages, dominant suppliers, demand, or policy. If WBES files are missing, the exercise reports that as a data-access gap rather than filling values synthetically.

## Files

- EDD panel: `results/exercise_08_tables/edd_public_proxy_panel.csv`
- EDD correlations: `results/exercise_08_tables/edd_correlations.csv`
- EDD OLS: `results/exercise_08_tables/edd_ols.csv`
- WBES firm panel: `results/exercise_08_tables/wbes_firm_proxy_panel.csv`
- WBES country summary: `results/exercise_08_tables/wbes_country_summary.csv`
- WBES correlations: `results/exercise_08_tables/wbes_exporter_focus_correlations.csv`
- WBES OLS: `results/exercise_08_tables/wbes_exporter_focus_ols.csv`
- WBES destination summary: `results/exercise_08_tables/wbes_destination_summary.csv`
- Manifest: `results/run_manifest_exercise_08_public_proxy.json`

## Source Details

```json
{json.dumps(source_details, indent=2, sort_keys=True)}
```
"""
    write_text(EX08_MEMO, memo)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Exercise 8 public proxy using EDD and WBES public data.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--source",
        choices=["edd", "wbes", "all"],
        default="all",
        help="Which public proxy source to run.",
    )
    parser.add_argument("--refresh", action="store_true", help="Ignore cached EDD pull and re-fetch from the World Bank API.")
    parser.add_argument("--min-n", type=int, default=10, help="Minimum usable rows for correlations and regressions.")
    parser.add_argument("--skip-figures", action="store_true", help="Write tables and memo without building figures.")
    parser.add_argument(
        "--wbes-dir",
        type=Path,
        default=ROOT / "data" / "raw" / "wbes",
        help="Directory containing WBES Stata files. Missing files are auto-download attempted and otherwise reported.",
    )
    parser.add_argument(
        "--exercise1-csv",
        type=Path,
        default=ROOT / "results" / "exercise_01_tables" / "concentration_all_years.csv",
        help="Exercise 1 concentration CSV to merge with EDD.",
    )
    return parser.parse_args(argv)


def run_edd_public_proxy(args: argparse.Namespace) -> dict:
    edd_long = load_or_fetch_edd(args.refresh)
    if edd_long.empty:
        raise RuntimeError("EDD cache is empty.")

    edd_wide = build_edd_wide(edd_long)
    exercise1_exports = load_exercise1_exports(args.exercise1_csv)
    panel = build_panel(edd_wide, exercise1_exports)
    panel.to_csv(EX08_PANEL_CSV, index=False)
    parquet_written, parquet_error = write_parquet_optional(panel, EX08_PANEL_PARQUET)

    correlations = compute_correlations(panel, args.min_n)
    correlations.to_csv(EX08_CORRELATIONS_CSV, index=False)
    ols = compute_ols(panel, args.min_n)
    ols.to_csv(EX08_OLS_CSV, index=False)

    figures_written, figure_paths, figure_error = make_edd_figures(panel, correlations, args.skip_figures)

    edd_iso3s = set(edd_long["iso3"].dropna().astype(str))
    absent_targets = [name for iso3, name in TARGET_COUNTRIES.items() if iso3 not in edd_iso3s]
    source_details = {
        "created_at_utc": now_utc(),
        "source": "World Bank Exporter Dynamics Database, API source 30",
        "source_url": "https://api.worldbank.org/v2/sources/30",
        "series": SERIES,
        "exercise1_csv": str(args.exercise1_csv),
        "min_n": args.min_n,
        "refresh": bool(args.refresh),
        "skip_figures": bool(args.skip_figures),
        "public_proxy_limitation": "EDD is public and customs-derived, but it does not expose firm-product-destination export values.",
        "no_synthetic_or_inferred_trade_values": True,
    }

    manifest = {
        **source_details,
        "run": True,
        "rows_edd_long": int(len(edd_long)),
        "rows_edd_wide": int(len(edd_wide)),
        "rows_panel": int(len(panel)),
        "countries_edd": int(edd_long["iso3"].nunique()),
        "countries_overlap": int(panel["iso3"].nunique()),
        "years_overlap": [int(panel["year"].min()), int(panel["year"].max())],
        "rows_correlations": int(len(correlations)),
        "rows_correlations_usable": int((correlations["skip_reason"] == "").sum()),
        "rows_ols": int(len(ols)),
        "rows_ols_usable": int((ols["skip_reason"] == "").sum()),
        "parquet_written": parquet_written,
        "parquet_error": parquet_error,
        "figures_written": figures_written,
        "figure_paths": figure_paths,
        "figure_error": figure_error,
        "absent_target_countries": absent_targets,
        "outputs": {
            "edd_long_cache": str(EDD_LONG_CACHE.relative_to(ROOT)),
            "panel_csv": str(EX08_PANEL_CSV.relative_to(ROOT)),
            "panel_parquet": str(EX08_PANEL_PARQUET.relative_to(ROOT)),
            "correlations_csv": str(EX08_CORRELATIONS_CSV.relative_to(ROOT)),
            "ols_csv": str(EX08_OLS_CSV.relative_to(ROOT)),
            "memo": str(EX08_MEMO.relative_to(ROOT)),
        },
    }
    return {
        "panel": panel,
        "correlations": correlations,
        "ols": ols,
        "source_details": source_details,
        "absent_targets": absent_targets,
        "manifest": manifest,
    }


def run_wbes_public_proxy(args: argparse.Namespace) -> dict:
    wbes_dir = resolve_repo_path(args.wbes_dir)
    firm_panel, download_results, load_statuses = load_wbes_panel(wbes_dir)
    firm_panel.to_csv(WBES_FIRM_PANEL_CSV, index=False)

    country_summary = compute_wbes_country_summary(firm_panel)
    country_summary.to_csv(WBES_COUNTRY_SUMMARY_CSV, index=False)

    correlations = compute_wbes_correlations(firm_panel, args.min_n)
    correlations.to_csv(WBES_CORRELATIONS_CSV, index=False)

    ols = compute_wbes_ols(firm_panel, args.min_n)
    ols.to_csv(WBES_OLS_CSV, index=False)

    destination_summary = compute_wbes_destination_summary(firm_panel)
    destination_summary.to_csv(WBES_DESTINATION_SUMMARY_CSV, index=False)

    figures_written, figure_paths, figure_error = make_wbes_figures(firm_panel, destination_summary, args.skip_figures)
    files_valid = [status for status in download_results if status.get("valid_stata_file", False)]
    missing_files = [status for status in download_results if not status.get("valid_stata_file", False)]
    source_details = {
        "source": "World Bank Enterprise Surveys public microdata",
        "datasets": WBES_DATASETS,
        "wbes_dir": str(wbes_dir.relative_to(ROOT)) if wbes_dir.is_relative_to(ROOT) else str(wbes_dir),
        "min_n": args.min_n,
        "skip_figures": bool(args.skip_figures),
        "public_proxy_limitation": "WBES is firm survey data. It records export status/intensity and some focus/destination proxies, but not full firm-product-destination customs values.",
        "no_synthetic_or_inferred_trade_values": True,
    }
    manifest = {
        **source_details,
        "run": True,
        "rows_wbes_firm_panel": int(len(firm_panel)),
        "countries_wbes_loaded": int(firm_panel["country_iso3"].nunique()) if not firm_panel.empty else 0,
        "wbes_files_valid": int(len(files_valid)),
        "wbes_files_missing_or_invalid": int(len(missing_files)),
        "wbes_download_results": download_results,
        "wbes_load_statuses": load_statuses,
        "rows_country_summary": int(len(country_summary)),
        "rows_correlations": int(len(correlations)),
        "rows_correlations_usable": int((correlations["skip_reason"] == "").sum()) if "skip_reason" in correlations.columns else 0,
        "rows_ols": int(len(ols)),
        "rows_ols_usable": int((ols["skip_reason"] == "").sum()) if "skip_reason" in ols.columns else 0,
        "rows_destination_summary": int(len(destination_summary)),
        "figures_written": figures_written,
        "figure_paths": figure_paths,
        "figure_error": figure_error,
        "outputs": {
            "firm_panel_csv": str(WBES_FIRM_PANEL_CSV.relative_to(ROOT)),
            "country_summary_csv": str(WBES_COUNTRY_SUMMARY_CSV.relative_to(ROOT)),
            "correlations_csv": str(WBES_CORRELATIONS_CSV.relative_to(ROOT)),
            "ols_csv": str(WBES_OLS_CSV.relative_to(ROOT)),
            "destination_summary_csv": str(WBES_DESTINATION_SUMMARY_CSV.relative_to(ROOT)),
            "memo": str(EX08_MEMO.relative_to(ROOT)),
        },
    }
    return {
        "firm_panel": firm_panel,
        "country_summary": country_summary,
        "correlations": correlations,
        "ols": ols,
        "destination_summary": destination_summary,
        "download_results": download_results,
        "load_statuses": load_statuses,
        "source_details": source_details,
        "manifest": manifest,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    ensure_dirs()

    edd_result = run_edd_public_proxy(args) if args.source in {"edd", "all"} else None
    wbes_result = run_wbes_public_proxy(args) if args.source in {"wbes", "all"} else None

    source_details = {
        "created_at_utc": now_utc(),
        "source_requested": args.source,
        "exercise1_csv": str(args.exercise1_csv),
        "wbes_dir": str(resolve_repo_path(args.wbes_dir)),
        "min_n": args.min_n,
        "refresh": bool(args.refresh),
        "skip_figures": bool(args.skip_figures),
        "public_proxy_limitation": "Exercise 8 public proxy cannot observe full firm-product-destination customs portfolios.",
        "no_synthetic_or_inferred_trade_values": True,
        "edd": None if edd_result is None else edd_result["source_details"],
        "wbes": None if wbes_result is None else wbes_result["source_details"],
    }
    write_memo(edd_result, wbes_result, source_details)

    edd_manifest = {"run": False} if edd_result is None else edd_result["manifest"]
    wbes_manifest = {"run": False} if wbes_result is None else wbes_result["manifest"]
    manifest = {
        **source_details,
        "edd": edd_manifest,
        "wbes": wbes_manifest,
        "parquet_written": None if edd_result is None else edd_manifest.get("parquet_written"),
        "parquet_error": "" if edd_result is None else edd_manifest.get("parquet_error", ""),
        "figures_written": {
            "edd": False if edd_result is None else edd_manifest.get("figures_written", False),
            "wbes": False if wbes_result is None else wbes_manifest.get("figures_written", False),
        },
        "outputs": {
            "memo": str(EX08_MEMO.relative_to(ROOT)),
            "manifest": str(EX08_MANIFEST.relative_to(ROOT)),
            "edd_panel_csv": str(EX08_PANEL_CSV.relative_to(ROOT)),
            "edd_correlations_csv": str(EX08_CORRELATIONS_CSV.relative_to(ROOT)),
            "edd_ols_csv": str(EX08_OLS_CSV.relative_to(ROOT)),
            "wbes_firm_panel_csv": str(WBES_FIRM_PANEL_CSV.relative_to(ROOT)),
            "wbes_country_summary_csv": str(WBES_COUNTRY_SUMMARY_CSV.relative_to(ROOT)),
            "wbes_correlations_csv": str(WBES_CORRELATIONS_CSV.relative_to(ROOT)),
            "wbes_ols_csv": str(WBES_OLS_CSV.relative_to(ROOT)),
            "wbes_destination_summary_csv": str(WBES_DESTINATION_SUMMARY_CSV.relative_to(ROOT)),
        },
    }
    write_json(EX08_MANIFEST, manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
