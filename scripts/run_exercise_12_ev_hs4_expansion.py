#!/usr/bin/env python3
"""Evenett-Venables-style HS4 persistent export expansion decomposition.

This runner builds a stricter Exercise 12 headline table for rd2 countries.
It uses HS4 products, adjacent two-year base and future windows, a $50,000
constant-2024-USD activity threshold, and pooled positive-expansion shares as
the main contribution measure.
"""

from __future__ import annotations

import argparse
import gc
import json
import math
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

try:
    import psutil
except ImportError:  # pragma: no cover - optional runtime diagnostic
    psutil = None

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from run_exercise_12_extensive_margin import (  # noqa: E402
    CountryInfo,
    bottom_base_product_ids,
    country_info_records,
    file_sha256,
    normalize_hs6_series,
    read_product_partner_for_reporter,
    safe_divide,
)
from trade_concentration_pipeline import (  # noqa: E402
    configure_country_sample,
    sample_processed_path,
    sample_results_dir,
    save_country_panel,
)


COUNTRY_SAMPLE = "rd2_countries"
DEFAULT_HORIZONS = (5, 10)
ACTIVE_THRESHOLD_USD_2024 = 50_000.0
CONSTANT_USD_YEAR = 2024
DEFLATOR_PATH = ROOT / "data/raw/world_bank_gdp/ny_gdp_defl_zs_1988_2025.csv"
LEAST_TRADED_BASE_SHARE = 0.10

PRODUCT_CHANNEL_ORDER = {
    "new_product": 1,
    "continuing_product": 2,
    "dying_product": 3,
    "below_threshold_residual": 4,
}

PRODUCT_CHANNEL_LABELS = {
    "new_product": "New HS4 products (persistent entry)",
    "continuing_product": "Continuing HS4 products",
    "dying_product": "Dying HS4 products",
    "below_threshold_residual": "Below-threshold residual",
}

PARTNER_CHANNEL_ORDER = {
    "same_product_partner": 1,
    "new_product_partner": 2,
    "lost_product_partner": 3,
    "below_threshold_partner_residual": 4,
}

PARTNER_CHANNEL_LABELS = {
    "same_product_partner": "Same product-specific partners",
    "new_product_partner": "New product-specific partners for continuing HS4 products",
    "lost_product_partner": "Lost product-specific partners for continuing HS4 products",
    "below_threshold_partner_residual": "Below-threshold product-partner residual",
}

ROBUSTNESS_DEFINITION_LABELS = {
    "persistent_new_product": "Persistent new HS4 products",
    "bottom_10pct_low_base_growth": "Low-base product growth (bottom 10% of base-window exports)",
}

COMBINED_PANEL_LABELS = {
    "combined_product_first": "Product-first: product-specific partner status",
    "combined_partner_first": "Partner-first: reporter-partner status",
}

PRODUCT_FIRST_CHANNEL_ORDER = {
    "net_new_product": 1,
    "existing_product_to_new_product_specific_partner": 2,
    "existing_product_to_existing_product_specific_partner": 3,
    "existing_product_lost_product_specific_partner": 4,
    "existing_product_below_threshold_product_specific_partner_residual": 5,
    "dying_product_cells": 6,
    "below_threshold_product_residual": 7,
}

PRODUCT_FIRST_CHANNEL_LABELS = {
    "net_new_product": "Net-new HS4 products",
    "existing_product_to_new_product_specific_partner": "Continuing HS4 products to new product-specific partners",
    "existing_product_to_existing_product_specific_partner": "Continuing HS4 products to existing product-specific partners",
    "existing_product_lost_product_specific_partner": "Continuing HS4 products to lost product-specific partners",
    "existing_product_below_threshold_product_specific_partner_residual": "Continuing HS4 products below product-specific partner threshold",
    "dying_product_cells": "Dying HS4 product cells",
    "below_threshold_product_residual": "Below-threshold product residual cells",
}

PARTNER_FIRST_CHANNEL_ORDER = {
    "new_reporter_partner_new_product": 1,
    "new_reporter_partner_existing_product": 2,
    "existing_reporter_partner_new_product": 3,
    "existing_reporter_partner_existing_product": 4,
    "lost_reporter_partner": 5,
    "reporter_partner_product_residual": 6,
}

PARTNER_FIRST_CHANNEL_LABELS = {
    "new_reporter_partner_new_product": "New reporter partners with net-new HS4 products",
    "new_reporter_partner_existing_product": "New reporter partners with continuing HS4 products",
    "existing_reporter_partner_new_product": "Existing reporter partners with net-new HS4 products",
    "existing_reporter_partner_existing_product": "Existing reporter partners with continuing HS4 products",
    "lost_reporter_partner": "Lost reporter partners",
    "reporter_partner_product_residual": "Reporter-partner/product residual cells",
}


@dataclass(frozen=True)
class DeflatorInfo:
    factors: dict[int, float]
    source_path: Path
    source_column: str
    base_year: int
    base_deflator: float


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def memory_status() -> str:
    if psutil is None:
        return "memory diagnostic unavailable"
    vm = psutil.virtual_memory()
    return f"available={vm.available / 1e9:.1f}GB used={vm.percent:.1f}%"


def clean_scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        if not math.isfinite(float(value)):
            return None
        return float(value)
    if pd.isna(value):
        return None
    return value


def hs4_product_id(cmd_code: pd.Series) -> pd.Series:
    hs6 = normalize_hs6_series(cmd_code)
    return ("HS4:" + hs6.str[:4]).astype("string")


def load_us_gdp_deflator(path: Path = DEFLATOR_PATH, base_year: int = CONSTANT_USD_YEAR) -> DeflatorInfo:
    if not path.exists():
        raise FileNotFoundError(f"US GDP deflator file is missing: {path}")
    values = pd.read_csv(path)
    required = {"year", "us_gdp_deflator"}
    missing = required - set(values.columns)
    if missing:
        raise RuntimeError(f"Deflator file is missing columns: {sorted(missing)}")
    values = values.copy()
    values["year"] = pd.to_numeric(values["year"], errors="coerce").astype("Int64")
    values["us_gdp_deflator"] = pd.to_numeric(values["us_gdp_deflator"], errors="coerce")
    values = values.dropna(subset=["year", "us_gdp_deflator"])
    base = values.loc[values["year"].eq(base_year), "us_gdp_deflator"]
    if base.empty or float(base.iloc[0]) <= 0:
        raise RuntimeError(f"Deflator file does not contain a positive {base_year} US GDP deflator")
    base_value = float(base.iloc[0])
    factors = {
        int(row.year): base_value / float(row.us_gdp_deflator)
        for row in values.itertuples(index=False)
        if float(row.us_gdp_deflator) > 0
    }
    return DeflatorInfo(
        factors=factors,
        source_path=path,
        source_column="us_gdp_deflator",
        base_year=base_year,
        base_deflator=base_value,
    )


def prepare_hs4_values(values: pd.DataFrame, deflator: DeflatorInfo) -> tuple[pd.DataFrame, list[int]]:
    if values.empty:
        columns = ["reporter_code", "year", "product_id", "partner_code", "trade_value_2024_usd"]
        return pd.DataFrame(columns=columns), []
    work = values[["reporter_code", "year", "cmd_code", "partner_code", "trade_value"]].copy()
    work["year"] = pd.to_numeric(work["year"], errors="coerce").astype("Int64")
    work["trade_value"] = pd.to_numeric(work["trade_value"], errors="coerce")
    work = work.dropna(subset=["year", "trade_value"]).copy()
    source_years = sorted(int(year) for year in work["year"].dropna().unique())
    missing_years = [year for year in source_years if year not in deflator.factors]
    work["deflator_factor_to_2024_usd"] = work["year"].map(deflator.factors)
    work = work.dropna(subset=["deflator_factor_to_2024_usd"]).copy()
    work["product_id"] = hs4_product_id(work["cmd_code"])
    work["trade_value_2024_usd"] = work["trade_value"] * work["deflator_factor_to_2024_usd"]
    work = work.dropna(subset=["product_id", "partner_code", "trade_value_2024_usd"]).copy()
    work["reporter_code"] = pd.to_numeric(work["reporter_code"], errors="coerce").astype(int)
    work["year"] = work["year"].astype(int)
    work["partner_code"] = pd.to_numeric(work["partner_code"], errors="coerce").astype(int)
    out = (
        work.groupby(["reporter_code", "year", "product_id", "partner_code"], as_index=False, observed=True)[
            "trade_value_2024_usd"
        ]
        .sum()
    )
    out = out[out["trade_value_2024_usd"] > 0].reset_index(drop=True)
    return out, missing_years


def series_for_year(df: pd.DataFrame, year: int, index_cols: list[str]) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=float)
    subset = df.loc[df["year"].eq(int(year)), [*index_cols, "trade_value_2024_usd"]]
    if subset.empty:
        return pd.Series(dtype=float)
    if len(index_cols) == 1:
        return subset.set_index(index_cols[0])["trade_value_2024_usd"].astype(float)
    return subset.set_index(index_cols)["trade_value_2024_usd"].astype(float)


def value_frame_for_year(df: pd.DataFrame, year: int, index_cols: list[str], value_col: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=[*index_cols, value_col])
    subset = df.loc[df["year"].eq(int(year)), [*index_cols, "trade_value_2024_usd"]]
    if subset.empty:
        return pd.DataFrame(columns=[*index_cols, value_col])
    return subset.rename(columns={"trade_value_2024_usd": value_col})


def add_product_channel_rows(
    rows: list[dict[str, Any]],
    *,
    metadata: dict[str, Any],
    paired: pd.DataFrame,
) -> None:
    totals = {
        "base": float(paired["base_value_2024_usd"].sum()),
        "future": float(paired["future_value_2024_usd"].sum()),
        "net": float(paired["net_contribution_2024_usd"].sum()),
        "positive": float(paired["positive_expansion_2024_usd"].sum()),
        "contraction": float(paired["contraction_2024_usd"].sum()),
    }
    for channel in PRODUCT_CHANNEL_ORDER:
        subset = paired.loc[paired["product_channel"].eq(channel)]
        net = float(subset["net_contribution_2024_usd"].sum()) if not subset.empty else 0.0
        positive = float(subset["positive_expansion_2024_usd"].sum()) if not subset.empty else 0.0
        contraction = float(subset["contraction_2024_usd"].sum()) if not subset.empty else 0.0
        rows.append(
            {
                **metadata,
                "channel_type": "product",
                "channel": channel,
                "channel_label": PRODUCT_CHANNEL_LABELS[channel],
                "channel_order": PRODUCT_CHANNEL_ORDER[channel],
                "base_value_2024_usd": float(subset["base_value_2024_usd"].sum()) if not subset.empty else 0.0,
                "future_value_2024_usd": float(subset["future_value_2024_usd"].sum()) if not subset.empty else 0.0,
                "net_contribution_2024_usd": net,
                "positive_expansion_2024_usd": positive,
                "contraction_2024_usd": contraction,
                "product_count": int(subset["product_id"].nunique()) if not subset.empty else 0,
                "partner_count": np.nan,
                "cell_count": int(len(subset)),
                "total_base_exports_2024_usd": totals["base"],
                "total_future_exports_2024_usd": totals["future"],
                "total_net_growth_2024_usd": totals["net"],
                "total_positive_expansion_2024_usd": totals["positive"],
                "total_contraction_2024_usd": totals["contraction"],
                "positive_expansion_share": safe_divide(positive, totals["positive"]),
                "net_growth_share": safe_divide(net, totals["net"]),
                "contraction_share": safe_divide(contraction, totals["contraction"]),
                "within_continuing_positive_expansion_share": np.nan,
                "within_continuing_net_growth_share": np.nan,
            }
        )


def build_product_window(
    product_year: pd.DataFrame,
    country: CountryInfo,
    base_year: int,
    horizon: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    future_year = int(base_year) + int(horizon)
    base_year_2 = int(base_year) + 1
    future_year_2 = int(future_year) + 1
    base_1 = series_for_year(product_year, base_year, ["product_id"])
    base_2 = series_for_year(product_year, base_year_2, ["product_id"])
    future_1 = series_for_year(product_year, future_year, ["product_id"])
    future_2 = series_for_year(product_year, future_year_2, ["product_id"])
    product_index = sorted(set(base_1.index) | set(base_2.index) | set(future_1.index) | set(future_2.index))
    paired = pd.DataFrame({"product_id": product_index})
    for name, series in [
        ("base_year_1_value_2024_usd", base_1),
        ("base_year_2_value_2024_usd", base_2),
        ("future_year_1_value_2024_usd", future_1),
        ("future_year_2_value_2024_usd", future_2),
    ]:
        paired[name] = paired["product_id"].map(series).fillna(0.0).astype(float)
    paired["base_active"] = (
        paired["base_year_1_value_2024_usd"].ge(ACTIVE_THRESHOLD_USD_2024)
        & paired["base_year_2_value_2024_usd"].ge(ACTIVE_THRESHOLD_USD_2024)
    )
    paired["future_active"] = (
        paired["future_year_1_value_2024_usd"].ge(ACTIVE_THRESHOLD_USD_2024)
        & paired["future_year_2_value_2024_usd"].ge(ACTIVE_THRESHOLD_USD_2024)
    )
    paired["base_value_2024_usd"] = (
        paired["base_year_1_value_2024_usd"] + paired["base_year_2_value_2024_usd"]
    ) / 2.0
    paired["future_value_2024_usd"] = (
        paired["future_year_1_value_2024_usd"] + paired["future_year_2_value_2024_usd"]
    ) / 2.0
    paired["net_contribution_2024_usd"] = paired["future_value_2024_usd"] - paired["base_value_2024_usd"]
    paired["positive_expansion_2024_usd"] = paired["net_contribution_2024_usd"].clip(lower=0.0)
    paired["contraction_2024_usd"] = (-paired["net_contribution_2024_usd"]).clip(lower=0.0)
    paired["product_channel"] = np.select(
        [
            ~paired["base_active"] & paired["future_active"],
            paired["base_active"] & paired["future_active"],
            paired["base_active"] & ~paired["future_active"],
            ~paired["base_active"] & ~paired["future_active"],
        ],
        ["new_product", "continuing_product", "dying_product", "below_threshold_residual"],
        default="unclassified",
    )
    if paired["product_channel"].eq("unclassified").any():
        raise RuntimeError(f"Unclassified HS4 products for {country.iso3} {base_year}, h={horizon}")
    metadata = {
        "country": country.country,
        "iso3": country.iso3,
        "reporter_code": int(country.reporter_code),
        "base_year": int(base_year),
        "base_year_2": int(base_year_2),
        "future_year": int(future_year),
        "future_year_2": int(future_year_2),
        "base_window": f"{base_year}-{base_year_2}",
        "future_window": f"{future_year}-{future_year_2}",
        "horizon": int(horizon),
        "product_level": "hs4",
        "active_threshold_usd_2024": ACTIVE_THRESHOLD_USD_2024,
        "persistence_rule": "adjacent_2_base_years_and_adjacent_2_future_years",
    }
    return paired, metadata


def build_partner_window(
    partner_year: pd.DataFrame,
    continuing_products: set[str],
    metadata: dict[str, Any],
) -> pd.DataFrame:
    if not continuing_products:
        return pd.DataFrame()
    base_year = int(metadata["base_year"])
    base_year_2 = int(metadata["base_year_2"])
    future_year = int(metadata["future_year"])
    future_year_2 = int(metadata["future_year_2"])
    work = partner_year[partner_year["product_id"].astype(str).isin(continuing_products)].copy()
    index_cols = ["product_id", "partner_code"]
    frames = [
        value_frame_for_year(work, base_year, index_cols, "base_year_1_value_2024_usd"),
        value_frame_for_year(work, base_year_2, index_cols, "base_year_2_value_2024_usd"),
        value_frame_for_year(work, future_year, index_cols, "future_year_1_value_2024_usd"),
        value_frame_for_year(work, future_year_2, index_cols, "future_year_2_value_2024_usd"),
    ]
    nonempty = [frame for frame in frames if not frame.empty]
    if not nonempty:
        return pd.DataFrame()
    paired = nonempty[0]
    for frame in nonempty[1:]:
        paired = paired.merge(frame, on=index_cols, how="outer", validate="one_to_one")
    for col in [
        "base_year_1_value_2024_usd",
        "base_year_2_value_2024_usd",
        "future_year_1_value_2024_usd",
        "future_year_2_value_2024_usd",
    ]:
        if col not in paired.columns:
            paired[col] = 0.0
        paired[col] = paired[col].fillna(0.0).astype(float)
    paired["base_active"] = (
        paired["base_year_1_value_2024_usd"].ge(ACTIVE_THRESHOLD_USD_2024)
        & paired["base_year_2_value_2024_usd"].ge(ACTIVE_THRESHOLD_USD_2024)
    )
    paired["future_active"] = (
        paired["future_year_1_value_2024_usd"].ge(ACTIVE_THRESHOLD_USD_2024)
        & paired["future_year_2_value_2024_usd"].ge(ACTIVE_THRESHOLD_USD_2024)
    )
    paired["base_value_2024_usd"] = (
        paired["base_year_1_value_2024_usd"] + paired["base_year_2_value_2024_usd"]
    ) / 2.0
    paired["future_value_2024_usd"] = (
        paired["future_year_1_value_2024_usd"] + paired["future_year_2_value_2024_usd"]
    ) / 2.0
    paired["net_contribution_2024_usd"] = paired["future_value_2024_usd"] - paired["base_value_2024_usd"]
    paired["positive_expansion_2024_usd"] = paired["net_contribution_2024_usd"].clip(lower=0.0)
    paired["contraction_2024_usd"] = (-paired["net_contribution_2024_usd"]).clip(lower=0.0)
    paired["partner_channel"] = np.select(
        [
            paired["base_active"] & paired["future_active"],
            ~paired["base_active"] & paired["future_active"],
            paired["base_active"] & ~paired["future_active"],
            ~paired["base_active"] & ~paired["future_active"],
        ],
        [
            "same_product_partner",
            "new_product_partner",
            "lost_product_partner",
            "below_threshold_partner_residual",
        ],
        default="unclassified",
    )
    if paired["partner_channel"].eq("unclassified").any():
        raise RuntimeError(f"Unclassified HS4-partner cells for {metadata['iso3']} {base_year}, h={metadata['horizon']}")
    return paired


def build_combined_cell_window(
    partner_year: pd.DataFrame,
    product_paired: pd.DataFrame,
    metadata: dict[str, Any],
) -> pd.DataFrame:
    base_year = int(metadata["base_year"])
    base_year_2 = int(metadata["base_year_2"])
    future_year = int(metadata["future_year"])
    future_year_2 = int(metadata["future_year_2"])
    index_cols = ["product_id", "partner_code"]
    frames = [
        value_frame_for_year(partner_year, base_year, index_cols, "base_year_1_value_2024_usd"),
        value_frame_for_year(partner_year, base_year_2, index_cols, "base_year_2_value_2024_usd"),
        value_frame_for_year(partner_year, future_year, index_cols, "future_year_1_value_2024_usd"),
        value_frame_for_year(partner_year, future_year_2, index_cols, "future_year_2_value_2024_usd"),
    ]
    nonempty = [frame for frame in frames if not frame.empty]
    if not nonempty:
        return pd.DataFrame()
    paired = nonempty[0]
    for frame in nonempty[1:]:
        paired = paired.merge(frame, on=index_cols, how="outer", validate="one_to_one")
    for col in [
        "base_year_1_value_2024_usd",
        "base_year_2_value_2024_usd",
        "future_year_1_value_2024_usd",
        "future_year_2_value_2024_usd",
    ]:
        if col not in paired.columns:
            paired[col] = 0.0
        paired[col] = paired[col].fillna(0.0).astype(float)

    paired["cell_base_active"] = (
        paired["base_year_1_value_2024_usd"].ge(ACTIVE_THRESHOLD_USD_2024)
        & paired["base_year_2_value_2024_usd"].ge(ACTIVE_THRESHOLD_USD_2024)
    )
    paired["cell_future_active"] = (
        paired["future_year_1_value_2024_usd"].ge(ACTIVE_THRESHOLD_USD_2024)
        & paired["future_year_2_value_2024_usd"].ge(ACTIVE_THRESHOLD_USD_2024)
    )
    paired["base_value_2024_usd"] = (
        paired["base_year_1_value_2024_usd"] + paired["base_year_2_value_2024_usd"]
    ) / 2.0
    paired["future_value_2024_usd"] = (
        paired["future_year_1_value_2024_usd"] + paired["future_year_2_value_2024_usd"]
    ) / 2.0
    paired["net_contribution_2024_usd"] = paired["future_value_2024_usd"] - paired["base_value_2024_usd"]
    paired["positive_expansion_2024_usd"] = paired["net_contribution_2024_usd"].clip(lower=0.0)
    paired["contraction_2024_usd"] = (-paired["net_contribution_2024_usd"]).clip(lower=0.0)

    product_channel_map = product_paired.set_index("product_id")["product_channel"].astype(str)
    paired["product_channel"] = paired["product_id"].map(product_channel_map)
    if paired["product_channel"].isna().any():
        missing = sorted(paired.loc[paired["product_channel"].isna(), "product_id"].astype(str).unique())[:5]
        raise RuntimeError(f"Missing product status for {metadata['iso3']} {base_year}, h={metadata['horizon']}: {missing}")

    reporter_partner_year = (
        partner_year.groupby(["year", "partner_code"], as_index=False, observed=True)["trade_value_2024_usd"]
        .sum()
        .sort_values(["year", "partner_code"])
        .reset_index(drop=True)
    )
    partner_base_1 = series_for_year(reporter_partner_year, base_year, ["partner_code"])
    partner_base_2 = series_for_year(reporter_partner_year, base_year_2, ["partner_code"])
    partner_future_1 = series_for_year(reporter_partner_year, future_year, ["partner_code"])
    partner_future_2 = series_for_year(reporter_partner_year, future_year_2, ["partner_code"])
    paired["reporter_partner_base_year_1_value_2024_usd"] = paired["partner_code"].map(partner_base_1).fillna(0.0).astype(float)
    paired["reporter_partner_base_year_2_value_2024_usd"] = paired["partner_code"].map(partner_base_2).fillna(0.0).astype(float)
    paired["reporter_partner_future_year_1_value_2024_usd"] = paired["partner_code"].map(partner_future_1).fillna(0.0).astype(float)
    paired["reporter_partner_future_year_2_value_2024_usd"] = paired["partner_code"].map(partner_future_2).fillna(0.0).astype(float)
    paired["reporter_partner_base_active"] = (
        paired["reporter_partner_base_year_1_value_2024_usd"].ge(ACTIVE_THRESHOLD_USD_2024)
        & paired["reporter_partner_base_year_2_value_2024_usd"].ge(ACTIVE_THRESHOLD_USD_2024)
    )
    paired["reporter_partner_future_active"] = (
        paired["reporter_partner_future_year_1_value_2024_usd"].ge(ACTIVE_THRESHOLD_USD_2024)
        & paired["reporter_partner_future_year_2_value_2024_usd"].ge(ACTIVE_THRESHOLD_USD_2024)
    )
    paired["reporter_partner_status"] = np.select(
        [
            paired["reporter_partner_base_active"] & paired["reporter_partner_future_active"],
            ~paired["reporter_partner_base_active"] & paired["reporter_partner_future_active"],
            paired["reporter_partner_base_active"] & ~paired["reporter_partner_future_active"],
            ~paired["reporter_partner_base_active"] & ~paired["reporter_partner_future_active"],
        ],
        [
            "existing_reporter_partner",
            "new_reporter_partner",
            "lost_reporter_partner",
            "below_threshold_reporter_partner_residual",
        ],
        default="unclassified",
    )
    paired["product_first_channel"] = np.select(
        [
            paired["product_channel"].eq("new_product"),
            paired["product_channel"].eq("continuing_product") & ~paired["cell_base_active"] & paired["cell_future_active"],
            paired["product_channel"].eq("continuing_product") & paired["cell_base_active"] & paired["cell_future_active"],
            paired["product_channel"].eq("continuing_product") & paired["cell_base_active"] & ~paired["cell_future_active"],
            paired["product_channel"].eq("continuing_product") & ~paired["cell_base_active"] & ~paired["cell_future_active"],
            paired["product_channel"].eq("dying_product"),
            paired["product_channel"].eq("below_threshold_residual"),
        ],
        [
            "net_new_product",
            "existing_product_to_new_product_specific_partner",
            "existing_product_to_existing_product_specific_partner",
            "existing_product_lost_product_specific_partner",
            "existing_product_below_threshold_product_specific_partner_residual",
            "dying_product_cells",
            "below_threshold_product_residual",
        ],
        default="unclassified",
    )
    paired["partner_first_channel"] = np.select(
        [
            paired["reporter_partner_status"].eq("new_reporter_partner") & paired["product_channel"].eq("new_product"),
            paired["reporter_partner_status"].eq("new_reporter_partner") & paired["product_channel"].eq("continuing_product"),
            paired["reporter_partner_status"].eq("existing_reporter_partner") & paired["product_channel"].eq("new_product"),
            paired["reporter_partner_status"].eq("existing_reporter_partner") & paired["product_channel"].eq("continuing_product"),
            paired["reporter_partner_status"].eq("lost_reporter_partner"),
        ],
        [
            "new_reporter_partner_new_product",
            "new_reporter_partner_existing_product",
            "existing_reporter_partner_new_product",
            "existing_reporter_partner_existing_product",
            "lost_reporter_partner",
        ],
        default="reporter_partner_product_residual",
    )
    if paired["product_first_channel"].eq("unclassified").any():
        raise RuntimeError(f"Unclassified product-first cells for {metadata['iso3']} {base_year}, h={metadata['horizon']}")
    if paired["reporter_partner_status"].eq("unclassified").any():
        raise RuntimeError(f"Unclassified reporter-partner status for {metadata['iso3']} {base_year}, h={metadata['horizon']}")
    return paired


def add_partner_channel_rows(
    rows: list[dict[str, Any]],
    *,
    metadata: dict[str, Any],
    paired: pd.DataFrame,
    total_product_positive_expansion: float,
    total_product_net_growth: float,
) -> None:
    if paired.empty:
        return
    totals = {
        "base": float(paired["base_value_2024_usd"].sum()),
        "future": float(paired["future_value_2024_usd"].sum()),
        "net": float(paired["net_contribution_2024_usd"].sum()),
        "positive": float(paired["positive_expansion_2024_usd"].sum()),
        "contraction": float(paired["contraction_2024_usd"].sum()),
    }
    for channel in PARTNER_CHANNEL_ORDER:
        subset = paired.loc[paired["partner_channel"].eq(channel)]
        net = float(subset["net_contribution_2024_usd"].sum()) if not subset.empty else 0.0
        positive = float(subset["positive_expansion_2024_usd"].sum()) if not subset.empty else 0.0
        contraction = float(subset["contraction_2024_usd"].sum()) if not subset.empty else 0.0
        rows.append(
            {
                **metadata,
                "channel_type": "partner_spread_continuing_hs4",
                "channel": channel,
                "channel_label": PARTNER_CHANNEL_LABELS[channel],
                "channel_order": PARTNER_CHANNEL_ORDER[channel],
                "base_value_2024_usd": float(subset["base_value_2024_usd"].sum()) if not subset.empty else 0.0,
                "future_value_2024_usd": float(subset["future_value_2024_usd"].sum()) if not subset.empty else 0.0,
                "net_contribution_2024_usd": net,
                "positive_expansion_2024_usd": positive,
                "contraction_2024_usd": contraction,
                "product_count": int(subset["product_id"].nunique()) if not subset.empty else 0,
                "partner_count": int(subset["partner_code"].nunique()) if not subset.empty else 0,
                "cell_count": int(len(subset)),
                "total_base_exports_2024_usd": totals["base"],
                "total_future_exports_2024_usd": totals["future"],
                "total_net_growth_2024_usd": total_product_net_growth,
                "total_positive_expansion_2024_usd": total_product_positive_expansion,
                "total_contraction_2024_usd": totals["contraction"],
                "positive_expansion_share": safe_divide(positive, total_product_positive_expansion),
                "net_growth_share": safe_divide(net, total_product_net_growth),
                "contraction_share": safe_divide(contraction, totals["contraction"]),
                "within_continuing_positive_expansion_share": safe_divide(positive, totals["positive"]),
                "within_continuing_net_growth_share": safe_divide(net, totals["net"]),
            }
        )


def add_combined_channel_rows(
    rows: list[dict[str, Any]],
    *,
    metadata: dict[str, Any],
    paired: pd.DataFrame,
    channel_type: str,
    channel_col: str,
    channel_order: dict[str, int],
    channel_labels: dict[str, str],
) -> None:
    if paired.empty:
        return
    totals = {
        "base": float(paired["base_value_2024_usd"].sum()),
        "future": float(paired["future_value_2024_usd"].sum()),
        "net": float(paired["net_contribution_2024_usd"].sum()),
        "positive": float(paired["positive_expansion_2024_usd"].sum()),
        "contraction": float(paired["contraction_2024_usd"].sum()),
    }
    for channel in channel_order:
        subset = paired.loc[paired[channel_col].eq(channel)]
        net = float(subset["net_contribution_2024_usd"].sum()) if not subset.empty else 0.0
        positive = float(subset["positive_expansion_2024_usd"].sum()) if not subset.empty else 0.0
        contraction = float(subset["contraction_2024_usd"].sum()) if not subset.empty else 0.0
        rows.append(
            {
                **metadata,
                "channel_type": channel_type,
                "channel_type_label": COMBINED_PANEL_LABELS[channel_type],
                "channel": channel,
                "channel_label": channel_labels[channel],
                "channel_order": channel_order[channel],
                "base_value_2024_usd": float(subset["base_value_2024_usd"].sum()) if not subset.empty else 0.0,
                "future_value_2024_usd": float(subset["future_value_2024_usd"].sum()) if not subset.empty else 0.0,
                "net_contribution_2024_usd": net,
                "positive_expansion_2024_usd": positive,
                "contraction_2024_usd": contraction,
                "product_count": int(subset["product_id"].nunique()) if not subset.empty else 0,
                "partner_count": int(subset["partner_code"].nunique()) if not subset.empty else 0,
                "cell_count": int(len(subset)),
                "total_base_exports_2024_usd": totals["base"],
                "total_future_exports_2024_usd": totals["future"],
                "total_net_growth_2024_usd": totals["net"],
                "total_positive_expansion_2024_usd": totals["positive"],
                "total_contraction_2024_usd": totals["contraction"],
                "positive_expansion_share": safe_divide(positive, totals["positive"]),
                "net_growth_share": safe_divide(net, totals["net"]),
                "contraction_share": safe_divide(contraction, totals["contraction"]),
                "within_continuing_positive_expansion_share": np.nan,
                "within_continuing_net_growth_share": np.nan,
            }
        )


def add_bottom10_rows(
    rows: list[dict[str, Any]],
    *,
    metadata: dict[str, Any],
    product_paired: pd.DataFrame,
) -> None:
    base_totals = product_paired.set_index("product_id")["base_value_2024_usd"]
    bottom_products = bottom_base_product_ids(base_totals, LEAST_TRADED_BASE_SHARE)
    total_positive = float(product_paired["positive_expansion_2024_usd"].sum())
    total_net = float(product_paired["net_contribution_2024_usd"].sum())
    masks = {
        "persistent_new_product": product_paired["product_channel"].eq("new_product"),
        "bottom_10pct_low_base_growth": product_paired["product_id"].astype(str).isin(bottom_products)
        & product_paired["net_contribution_2024_usd"].gt(0),
    }
    for definition, mask in masks.items():
        subset = product_paired.loc[mask]
        net = float(subset["net_contribution_2024_usd"].sum()) if not subset.empty else 0.0
        positive = float(subset["positive_expansion_2024_usd"].sum()) if not subset.empty else 0.0
        rows.append(
            {
                **metadata,
                "product_definition": definition,
                "product_definition_label": ROBUSTNESS_DEFINITION_LABELS[definition],
                "base_value_2024_usd": float(subset["base_value_2024_usd"].sum()) if not subset.empty else 0.0,
                "future_value_2024_usd": float(subset["future_value_2024_usd"].sum()) if not subset.empty else 0.0,
                "net_contribution_2024_usd": net,
                "positive_expansion_2024_usd": positive,
                "product_count": int(subset["product_id"].nunique()) if not subset.empty else 0,
                "total_net_growth_2024_usd": total_net,
                "total_positive_expansion_2024_usd": total_positive,
                "positive_expansion_share": safe_divide(positive, total_positive),
                "net_growth_share": safe_divide(net, total_net),
                "least_traded_base_share_cutoff": LEAST_TRADED_BASE_SHARE,
            }
        )


def compute_country_decomposition(
    cells: pd.DataFrame,
    country: CountryInfo,
    horizons: Iterable[int],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    product_rows: list[dict[str, Any]] = []
    partner_rows: list[dict[str, Any]] = []
    combined_rows: list[dict[str, Any]] = []
    robustness_rows: list[dict[str, Any]] = []
    if cells.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), {"windows_considered": 0, "windows_used": 0}
    product_year = (
        cells.groupby(["reporter_code", "year", "product_id"], as_index=False, observed=True)["trade_value_2024_usd"]
        .sum()
        .sort_values(["year", "product_id"])
        .reset_index(drop=True)
    )
    partner_year = (
        cells.groupby(["reporter_code", "year", "product_id", "partner_code"], as_index=False, observed=True)[
            "trade_value_2024_usd"
        ]
        .sum()
        .sort_values(["year", "product_id", "partner_code"])
        .reset_index(drop=True)
    )
    years = sorted(pd.to_numeric(product_year["year"], errors="coerce").dropna().astype(int).unique().tolist())
    year_set = set(years)
    windows_considered = 0
    windows_used = 0
    for base_year in years:
        for horizon in horizons:
            windows_considered += 1
            required_years = {int(base_year), int(base_year) + 1, int(base_year) + int(horizon), int(base_year) + int(horizon) + 1}
            if not required_years.issubset(year_set):
                continue
            product_paired, metadata = build_product_window(product_year, country, int(base_year), int(horizon))
            if product_paired.empty:
                continue
            windows_used += 1
            add_product_channel_rows(product_rows, metadata=metadata, paired=product_paired)
            add_bottom10_rows(robustness_rows, metadata=metadata, product_paired=product_paired)
            continuing_products = set(
                product_paired.loc[product_paired["product_channel"].eq("continuing_product"), "product_id"].astype(str)
            )
            partner_paired = build_partner_window(partner_year, continuing_products, metadata)
            add_partner_channel_rows(
                partner_rows,
                metadata=metadata,
                paired=partner_paired,
                total_product_positive_expansion=float(product_paired["positive_expansion_2024_usd"].sum()),
                total_product_net_growth=float(product_paired["net_contribution_2024_usd"].sum()),
            )
            combined_paired = build_combined_cell_window(partner_year, product_paired, metadata)
            add_combined_channel_rows(
                combined_rows,
                metadata=metadata,
                paired=combined_paired,
                channel_type="combined_product_first",
                channel_col="product_first_channel",
                channel_order=PRODUCT_FIRST_CHANNEL_ORDER,
                channel_labels=PRODUCT_FIRST_CHANNEL_LABELS,
            )
            add_combined_channel_rows(
                combined_rows,
                metadata=metadata,
                paired=combined_paired,
                channel_type="combined_partner_first",
                channel_col="partner_first_channel",
                channel_order=PARTNER_FIRST_CHANNEL_ORDER,
                channel_labels=PARTNER_FIRST_CHANNEL_LABELS,
            )
    diagnostics = {
        "windows_considered": int(windows_considered),
        "windows_used": int(windows_used),
        "product_year_rows": int(len(product_year)),
        "partner_year_rows": int(len(partner_year)),
    }
    return pd.DataFrame(product_rows), pd.DataFrame(partner_rows), pd.DataFrame(combined_rows), pd.DataFrame(robustness_rows), diagnostics


def pooled_summary(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame()
    rows = rows.copy()
    window_cols = ["channel_type", "reporter_code", "base_year", "future_year", "horizon"]
    within_totals = (
        rows.groupby(window_cols, as_index=False, observed=True)
        .agg(
            within_positive_expansion_2024_usd=("positive_expansion_2024_usd", "sum"),
            within_net_growth_2024_usd=("net_contribution_2024_usd", "sum"),
        )
    )
    rows = rows.merge(within_totals, on=window_cols, how="left", validate="many_to_one")
    group_cols = ["channel_type", "horizon", "channel", "channel_label", "channel_order"]
    summary = (
        rows.groupby(group_cols, as_index=False, observed=True)
        .agg(
            countries=("reporter_code", "nunique"),
            country_windows=("reporter_code", "size"),
            positive_expansion_2024_usd=("positive_expansion_2024_usd", "sum"),
            net_contribution_2024_usd=("net_contribution_2024_usd", "sum"),
            contraction_2024_usd=("contraction_2024_usd", "sum"),
            total_positive_expansion_2024_usd=("total_positive_expansion_2024_usd", "sum"),
            total_net_growth_2024_usd=("total_net_growth_2024_usd", "sum"),
            total_contraction_2024_usd=("total_contraction_2024_usd", "sum"),
            within_positive_expansion_2024_usd=("within_positive_expansion_2024_usd", "sum"),
            within_net_growth_2024_usd=("within_net_growth_2024_usd", "sum"),
            median_positive_expansion_share=("positive_expansion_share", "median"),
            median_net_growth_share=("net_growth_share", "median"),
            median_product_count=("product_count", "median"),
            median_partner_count=("partner_count", "median"),
        )
        .sort_values(["channel_type", "horizon", "channel_order"])
        .reset_index(drop=True)
    )
    summary["pooled_positive_expansion_share"] = summary.apply(
        lambda row: safe_divide(row["positive_expansion_2024_usd"], row["total_positive_expansion_2024_usd"]),
        axis=1,
    )
    summary["pooled_net_growth_share"] = summary.apply(
        lambda row: safe_divide(row["net_contribution_2024_usd"], row["total_net_growth_2024_usd"]),
        axis=1,
    )
    summary["pooled_within_positive_expansion_share"] = summary.apply(
        lambda row: safe_divide(row["positive_expansion_2024_usd"], row["within_positive_expansion_2024_usd"]),
        axis=1,
    )
    summary["pooled_within_net_growth_share"] = summary.apply(
        lambda row: safe_divide(row["net_contribution_2024_usd"], row["within_net_growth_2024_usd"]),
        axis=1,
    )
    return summary


def equal_country_summary(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame()
    group_cols = ["channel_type", "horizon", "channel", "channel_label", "channel_order"]
    country = (
        rows.groupby([*group_cols, "reporter_code", "country", "iso3"], as_index=False, observed=True)
        .agg(
            country_windows=("reporter_code", "size"),
            country_median_positive_expansion_share=("positive_expansion_share", "median"),
            country_median_net_growth_share=("net_growth_share", "median"),
            country_median_positive_expansion=("positive_expansion_2024_usd", "median"),
            country_median_product_count=("product_count", "median"),
            country_median_partner_count=("partner_count", "median"),
        )
    )
    summary = (
        country.groupby(group_cols, as_index=False, observed=True)
        .agg(
            countries=("reporter_code", "nunique"),
            min_country_windows=("country_windows", "min"),
            median_country_windows=("country_windows", "median"),
            max_country_windows=("country_windows", "max"),
            equal_country_median_positive_expansion_share=("country_median_positive_expansion_share", "median"),
            equal_country_median_net_growth_share=("country_median_net_growth_share", "median"),
            equal_country_median_positive_expansion=("country_median_positive_expansion", "median"),
            equal_country_median_product_count=("country_median_product_count", "median"),
            equal_country_median_partner_count=("country_median_partner_count", "median"),
        )
        .sort_values(["channel_type", "horizon", "channel_order"])
        .reset_index(drop=True)
    )
    summary["summary_weighting"] = "equal_country_after_within_country_median"
    return summary


def robustness_summary(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame()
    group_cols = ["horizon", "product_definition", "product_definition_label"]
    out = (
        rows.groupby(group_cols, as_index=False, observed=True)
        .agg(
            countries=("reporter_code", "nunique"),
            country_windows=("reporter_code", "size"),
            positive_expansion_2024_usd=("positive_expansion_2024_usd", "sum"),
            net_contribution_2024_usd=("net_contribution_2024_usd", "sum"),
            total_positive_expansion_2024_usd=("total_positive_expansion_2024_usd", "sum"),
            total_net_growth_2024_usd=("total_net_growth_2024_usd", "sum"),
            median_positive_expansion_share=("positive_expansion_share", "median"),
            median_net_growth_share=("net_growth_share", "median"),
            median_product_count=("product_count", "median"),
        )
        .sort_values(["horizon", "product_definition"])
        .reset_index(drop=True)
    )
    out["pooled_positive_expansion_share"] = out.apply(
        lambda row: safe_divide(row["positive_expansion_2024_usd"], row["total_positive_expansion_2024_usd"]),
        axis=1,
    )
    out["pooled_net_growth_share"] = out.apply(
        lambda row: safe_divide(row["net_contribution_2024_usd"], row["total_net_growth_2024_usd"]),
        axis=1,
    )
    return out


def latest_5y_country_rows(product_rows: pd.DataFrame) -> pd.DataFrame:
    if product_rows.empty:
        return pd.DataFrame()
    base = product_rows[(product_rows["channel_type"].eq("product")) & (product_rows["horizon"].eq(5))].copy()
    if base.empty:
        return pd.DataFrame()
    latest_keys = (
        base[["reporter_code", "future_year_2", "base_year", "future_year"]]
        .drop_duplicates()
        .sort_values(["reporter_code", "future_year_2", "base_year"])
        .groupby("reporter_code", as_index=False)
        .tail(1)[["reporter_code", "base_year", "future_year"]]
    )
    latest = base.merge(latest_keys, on=["reporter_code", "base_year", "future_year"], how="inner")
    wide_share = latest.pivot_table(
        index=[
            "country",
            "iso3",
            "reporter_code",
            "base_window",
            "future_window",
            "base_year",
            "base_year_2",
            "future_year",
            "future_year_2",
            "horizon",
            "total_positive_expansion_2024_usd",
            "total_net_growth_2024_usd",
        ],
        columns="channel",
        values="positive_expansion_share",
        aggfunc="first",
    ).reset_index()
    wide_share = wide_share.rename(columns={channel: f"{channel}_positive_expansion_share" for channel in PRODUCT_CHANNEL_ORDER})
    wide_net = latest.pivot_table(
        index=["reporter_code", "base_year", "future_year"],
        columns="channel",
        values="net_contribution_2024_usd",
        aggfunc="first",
    ).reset_index()
    wide_net = wide_net.rename(columns={channel: f"{channel}_net_contribution_2024_usd" for channel in PRODUCT_CHANNEL_ORDER})
    out = wide_share.merge(wide_net, on=["reporter_code", "base_year", "future_year"], how="left")
    return out.sort_values("country").reset_index(drop=True)


def latest_5y_combined_country_rows(combined_rows: pd.DataFrame) -> pd.DataFrame:
    if combined_rows.empty:
        return pd.DataFrame()
    base = combined_rows[combined_rows["horizon"].eq(5)].copy()
    if base.empty:
        return pd.DataFrame()
    latest_keys = (
        base[["reporter_code", "future_year_2", "base_year", "future_year"]]
        .drop_duplicates()
        .sort_values(["reporter_code", "future_year_2", "base_year"])
        .groupby("reporter_code", as_index=False)
        .tail(1)[["reporter_code", "base_year", "future_year"]]
    )
    latest = base.merge(latest_keys, on=["reporter_code", "base_year", "future_year"], how="inner")
    index_cols = [
        "country",
        "iso3",
        "reporter_code",
        "base_window",
        "future_window",
        "base_year",
        "base_year_2",
        "future_year",
        "future_year_2",
        "horizon",
        "channel_type",
        "channel_type_label",
        "total_positive_expansion_2024_usd",
        "total_net_growth_2024_usd",
    ]
    wide_share = latest.pivot_table(
        index=index_cols,
        columns="channel",
        values="positive_expansion_share",
        aggfunc="first",
    ).reset_index()
    wide_share = wide_share.rename(
        columns={
            channel: f"{channel}_positive_expansion_share"
            for channel in [*PRODUCT_FIRST_CHANNEL_ORDER.keys(), *PARTNER_FIRST_CHANNEL_ORDER.keys()]
        }
    )
    wide_net = latest.pivot_table(
        index=["reporter_code", "base_year", "future_year", "channel_type"],
        columns="channel",
        values="net_growth_share",
        aggfunc="first",
    ).reset_index()
    wide_net = wide_net.rename(
        columns={
            channel: f"{channel}_net_growth_share"
            for channel in [*PRODUCT_FIRST_CHANNEL_ORDER.keys(), *PARTNER_FIRST_CHANNEL_ORDER.keys()]
        }
    )
    out = wide_share.merge(wide_net, on=["reporter_code", "base_year", "future_year", "channel_type"], how="left")
    return out.sort_values(["country", "channel_type"]).reset_index(drop=True)


def validate_outputs(
    *,
    product_rows: pd.DataFrame,
    partner_rows: pd.DataFrame,
    combined_rows: pd.DataFrame,
    latest_5y: pd.DataFrame,
    combined_latest_5y: pd.DataFrame,
    robustness: pd.DataFrame,
    countries: list[CountryInfo],
    horizons: Iterable[int],
    source_checks: dict[int, dict[str, Any]],
    deflator: DeflatorInfo,
) -> dict[str, Any]:
    expected_country_count = len(countries)
    validation: dict[str, Any] = {
        "created_at_utc": now_utc(),
        "status": "ok",
        "blockers": [],
        "country_count_expected": expected_country_count,
        "country_count_product_decomposition": int(product_rows["reporter_code"].nunique()) if not product_rows.empty else 0,
        "country_count_partner_spread": int(partner_rows["reporter_code"].nunique()) if not partner_rows.empty else 0,
        "country_count_combined_decomposition": int(combined_rows["reporter_code"].nunique()) if not combined_rows.empty else 0,
        "country_count_latest_5y": int(latest_5y["reporter_code"].nunique()) if not latest_5y.empty else 0,
        "country_count_combined_latest_5y": int(combined_latest_5y["reporter_code"].nunique()) if not combined_latest_5y.empty else 0,
        "horizons": [int(h) for h in horizons],
        "product_level": "hs4",
        "active_threshold_usd_2024": ACTIVE_THRESHOLD_USD_2024,
        "constant_usd_year": CONSTANT_USD_YEAR,
        "deflator_source": str(deflator.source_path.relative_to(ROOT)),
        "deflator_source_column": deflator.source_column,
        "deflator_base_year": deflator.base_year,
        "deflator_base_value": deflator.base_deflator,
        "source_rows_after_filters": int(sum(item.get("rows_after_filters", 0) for item in source_checks.values())),
        "source_hs6_999999_rows_after_filters": int(sum(item.get("hs6_999999_rows_after_filters", 0) for item in source_checks.values())),
        "source_partner_code_0_rows_after_filters": int(sum(item.get("partner_code_0_rows_after_filters", 0) for item in source_checks.values())),
        "source_years_without_deflator": sorted(
            {year for item in source_checks.values() for year in item.get("source_years_without_deflator", [])}
        ),
        "deflator_missing_years_used": [],
    }
    blockers: list[str] = []
    if validation["country_count_product_decomposition"] != expected_country_count:
        blockers.append("product decomposition does not cover all rd2 countries")
    if validation["country_count_latest_5y"] != expected_country_count:
        blockers.append("latest 5-year product table does not cover all rd2 countries")
    if validation["country_count_combined_decomposition"] != expected_country_count:
        blockers.append("combined product-partner decomposition does not cover all rd2 countries")
    if validation["country_count_combined_latest_5y"] != expected_country_count:
        blockers.append("latest 5-year combined table does not cover all rd2 countries")
    if validation["source_hs6_999999_rows_after_filters"] != 0:
        blockers.append("filtered source values contain HS6 999999")
    if validation["source_partner_code_0_rows_after_filters"] != 0:
        blockers.append("filtered source values contain partnerCode 0")
    if product_rows.empty:
        blockers.append("product decomposition is empty")
    if partner_rows.empty:
        blockers.append("partner-spread decomposition is empty")
    if combined_rows.empty:
        blockers.append("combined product-partner decomposition is empty")
    if robustness.empty:
        blockers.append("bottom-10 robustness table is empty")

    key_cols = ["reporter_code", "base_year", "future_year", "horizon", "channel"]
    if not product_rows.empty:
        validation["duplicate_product_channel_keys"] = int(product_rows.duplicated(key_cols).sum())
        product_sum = (
            product_rows.groupby(["reporter_code", "base_year", "future_year", "horizon"], as_index=False, observed=True)
            .agg(
                category_net=("net_contribution_2024_usd", "sum"),
                category_positive=("positive_expansion_2024_usd", "sum"),
                total_net=("total_net_growth_2024_usd", "first"),
                total_positive=("total_positive_expansion_2024_usd", "first"),
            )
        )
        product_sum["net_residual"] = product_sum["category_net"] - product_sum["total_net"]
        product_sum["positive_residual"] = product_sum["category_positive"] - product_sum["total_positive"]
        product_sum["net_tolerance"] = np.maximum(1.0, product_sum["total_net"].abs() * 1e-10)
        product_sum["positive_tolerance"] = np.maximum(1.0, product_sum["total_positive"].abs() * 1e-10)
        validation["max_abs_product_net_residual"] = float(product_sum["net_residual"].abs().max())
        validation["max_abs_product_positive_residual"] = float(product_sum["positive_residual"].abs().max())
        validation["product_accounting_residual_violations"] = int(
            (
                product_sum["net_residual"].abs().gt(product_sum["net_tolerance"])
                | product_sum["positive_residual"].abs().gt(product_sum["positive_tolerance"])
            ).sum()
        )
        if validation["duplicate_product_channel_keys"] != 0:
            blockers.append("duplicate product channel keys are present")
        if validation["product_accounting_residual_violations"] != 0:
            blockers.append("product channel accounting residual violations are present")
    else:
        validation["duplicate_product_channel_keys"] = 0
        validation["max_abs_product_net_residual"] = None
        validation["max_abs_product_positive_residual"] = None
        validation["product_accounting_residual_violations"] = 0

    if not partner_rows.empty:
        partner_key_cols = ["reporter_code", "base_year", "future_year", "horizon", "channel"]
        validation["duplicate_partner_channel_keys"] = int(partner_rows.duplicated(partner_key_cols).sum())
        if validation["duplicate_partner_channel_keys"] != 0:
            blockers.append("duplicate partner channel keys are present")
    else:
        validation["duplicate_partner_channel_keys"] = 0

    if not combined_rows.empty:
        combined_key_cols = ["channel_type", "reporter_code", "base_year", "future_year", "horizon", "channel"]
        validation["duplicate_combined_channel_keys"] = int(combined_rows.duplicated(combined_key_cols).sum())
        combined_sum = (
            combined_rows.groupby(["channel_type", "reporter_code", "base_year", "future_year", "horizon"], as_index=False, observed=True)
            .agg(
                category_net=("net_contribution_2024_usd", "sum"),
                category_positive=("positive_expansion_2024_usd", "sum"),
                total_net=("total_net_growth_2024_usd", "first"),
                total_positive=("total_positive_expansion_2024_usd", "first"),
            )
        )
        combined_sum["net_residual"] = combined_sum["category_net"] - combined_sum["total_net"]
        combined_sum["positive_residual"] = combined_sum["category_positive"] - combined_sum["total_positive"]
        combined_sum["net_tolerance"] = np.maximum(1.0, combined_sum["total_net"].abs() * 1e-10)
        combined_sum["positive_tolerance"] = np.maximum(1.0, combined_sum["total_positive"].abs() * 1e-10)
        validation["max_abs_combined_net_residual"] = float(combined_sum["net_residual"].abs().max())
        validation["max_abs_combined_positive_residual"] = float(combined_sum["positive_residual"].abs().max())
        validation["combined_accounting_residual_violations"] = int(
            (
                combined_sum["net_residual"].abs().gt(combined_sum["net_tolerance"])
                | combined_sum["positive_residual"].abs().gt(combined_sum["positive_tolerance"])
            ).sum()
        )
        combined_h5 = combined_rows.loc[combined_rows["horizon"].eq(5)].copy()
        if not combined_h5.empty:
            h5_num = combined_h5.groupby("channel_type", observed=True)["positive_expansion_2024_usd"].sum()
            h5_den = (
                combined_h5.drop_duplicates(["channel_type", "reporter_code", "base_year", "future_year", "horizon"])
                .groupby("channel_type", observed=True)["total_positive_expansion_2024_usd"]
                .sum()
            )
            validation["combined_horizon_5_pooled_positive_share_sums"] = {
                str(key): safe_divide(float(h5_num.get(key, 0.0)), float(h5_den.get(key, 0.0))) for key in h5_den.index
            }
        else:
            validation["combined_horizon_5_pooled_positive_share_sums"] = {}
        if validation["duplicate_combined_channel_keys"] != 0:
            blockers.append("duplicate combined channel keys are present")
        if validation["combined_accounting_residual_violations"] != 0:
            blockers.append("combined channel accounting residual violations are present")
    else:
        validation["duplicate_combined_channel_keys"] = 0
        validation["max_abs_combined_net_residual"] = None
        validation["max_abs_combined_positive_residual"] = None
        validation["combined_accounting_residual_violations"] = 0
        validation["combined_horizon_5_pooled_positive_share_sums"] = {}

    validation["blockers"] = blockers
    validation["status"] = "blocked" if blockers else "ok"
    return validation


def write_outputs(
    *,
    country_sample: str,
    aggregate_path: Path,
    deflator: DeflatorInfo,
    product_rows: pd.DataFrame,
    partner_rows: pd.DataFrame,
    combined_rows: pd.DataFrame,
    robustness_rows: pd.DataFrame,
    validation: dict[str, Any],
    started_at_utc: str,
) -> dict[str, Path]:
    processed_path = sample_processed_path("exercise_12_ev_hs4_expansion_decomposition.parquet", country_sample)
    results_dir = sample_results_dir(country_sample)
    tables_dir = results_dir / "exercise_12_ev_hs4_expansion_tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    processed_path.parent.mkdir(parents=True, exist_ok=True)

    summary_inputs = [df for df in [product_rows, partner_rows, combined_rows] if not df.empty]
    summary_source = pd.concat(summary_inputs, ignore_index=True) if summary_inputs else pd.DataFrame()
    summary = pooled_summary(summary_source)
    equal_country = equal_country_summary(
        summary_source
    )
    combined_summary = pooled_summary(combined_rows)
    combined_equal_country = equal_country_summary(combined_rows)
    robustness = robustness_summary(robustness_rows)
    latest = latest_5y_country_rows(product_rows)
    combined_latest = latest_5y_combined_country_rows(combined_rows)

    product_rows.to_parquet(processed_path, index=False)
    paths = {
        "processed": processed_path,
        "country_window": tables_dir / "ev_hs4_country_window_decomposition.csv",
        "partner_spread_country_window": tables_dir / "ev_hs4_partner_spread_country_window.csv",
        "combined_country_window": tables_dir / "ev_hs4_combined_country_window_decomposition.csv",
        "combined_pooled_summary": tables_dir / "ev_hs4_combined_pooled_summary.csv",
        "combined_equal_country_summary": tables_dir / "ev_hs4_combined_equal_country_summary.csv",
        "combined_latest_5y": tables_dir / "ev_hs4_combined_latest_5y_country.csv",
        "pooled_summary": tables_dir / "ev_hs4_pooled_summary.csv",
        "equal_country_summary": tables_dir / "ev_hs4_equal_country_summary.csv",
        "latest_5y": tables_dir / "ev_hs4_latest_5y_country.csv",
        "bottom10_robustness": tables_dir / "ev_hs4_bottom10_robustness.csv",
        "bottom10_robustness_summary": tables_dir / "ev_hs4_bottom10_robustness_summary.csv",
        "validation": tables_dir / "ev_hs4_validation.json",
        "manifest": sample_results_dir(country_sample) / "run_manifest_exercise_12_ev_hs4_expansion.json",
    }
    product_rows.to_csv(paths["country_window"], index=False)
    partner_rows.to_csv(paths["partner_spread_country_window"], index=False)
    combined_rows.to_csv(paths["combined_country_window"], index=False)
    combined_summary.to_csv(paths["combined_pooled_summary"], index=False)
    combined_equal_country.to_csv(paths["combined_equal_country_summary"], index=False)
    combined_latest.to_csv(paths["combined_latest_5y"], index=False)
    summary.to_csv(paths["pooled_summary"], index=False)
    equal_country.to_csv(paths["equal_country_summary"], index=False)
    latest.to_csv(paths["latest_5y"], index=False)
    robustness_rows.to_csv(paths["bottom10_robustness"], index=False)
    robustness.to_csv(paths["bottom10_robustness_summary"], index=False)
    paths["validation"].write_text(json.dumps(validation, indent=2, sort_keys=True), encoding="utf-8")
    manifest = {
        "created_at_utc": now_utc(),
        "started_at_utc": started_at_utc,
        "country_sample": country_sample,
        "source_aggregate": str(aggregate_path.relative_to(ROOT)),
        "source_aggregate_sha256": file_sha256(aggregate_path),
        "deflator_source": str(deflator.source_path.relative_to(ROOT)),
        "deflator_source_sha256": file_sha256(deflator.source_path),
        "processed_output": str(processed_path.relative_to(ROOT)),
        "result_files": {
            key: str(path.relative_to(ROOT))
            for key, path in paths.items()
            if key != "processed"
        },
        "row_counts": {
            "country_window": int(len(product_rows)),
            "partner_spread_country_window": int(len(partner_rows)),
            "combined_country_window": int(len(combined_rows)),
            "combined_pooled_summary": int(len(combined_summary)),
            "combined_equal_country_summary": int(len(combined_equal_country)),
            "combined_latest_5y": int(len(combined_latest)),
            "pooled_summary": int(len(summary)),
            "equal_country_summary": int(len(equal_country)),
            "latest_5y": int(len(latest)),
            "bottom10_robustness": int(len(robustness_rows)),
            "bottom10_robustness_summary": int(len(robustness)),
        },
        "definition": {
            "unit_of_observation": "reporter-country adjacent-2-year base window adjacent-2-year future window HS4 growth channel",
            "product_level": "hs4",
            "persistence_rule": "base years t,t+1 below/above threshold and future years t+h,t+h+1 below/above threshold",
            "active_threshold_usd_2024": ACTIVE_THRESHOLD_USD_2024,
            "constant_usd_year": CONSTANT_USD_YEAR,
            "headline_share": "pooled positive expansion share",
            "net_growth_share_note": "Net-growth shares are companion accounting and can exceed 100 percent or be negative when contractions offset expansions.",
            "bottom_10pct_base_share": LEAST_TRADED_BASE_SHARE,
            "combined_decomposition": {
                "unit_of_observation": "reporter-country adjacent-2-year base window adjacent-2-year future window HS4-by-partner cell growth channel",
                "product_first_new_partner_definition": "product-specific HS4-by-partner cell not active in both base years and active in both future years",
                "partner_first_new_partner_definition": "reporter-partner total across all HS4 products not active in both base years and active in both future years",
                "note": "Product-first and partner-first panels are alternative partitions and should not be added together.",
            },
            "product_excluded_hs6_codes": ["999999"],
            "partner_code_0_excluded": True,
        },
        "validation": validation,
    }
    paths["manifest"].write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return paths


def checkpoint_paths(checkpoint_dir: Path, reporter_code: int) -> dict[str, Path]:
    prefix = checkpoint_dir / f"reporter_{int(reporter_code)}"
    return {
        "product": prefix.with_name(prefix.name + "_product.parquet"),
        "partner": prefix.with_name(prefix.name + "_partner.parquet"),
        "combined": prefix.with_name(prefix.name + "_combined.parquet"),
        "robustness": prefix.with_name(prefix.name + "_robustness.parquet"),
        "source_check": prefix.with_name(prefix.name + "_source_check.json"),
    }


def read_country_checkpoint(paths: dict[str, Path]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]] | None:
    if not all(path.exists() for path in paths.values()):
        return None
    product = pd.read_parquet(paths["product"])
    partner = pd.read_parquet(paths["partner"])
    combined = pd.read_parquet(paths["combined"])
    robustness = pd.read_parquet(paths["robustness"])
    source_check = json.loads(paths["source_check"].read_text(encoding="utf-8"))
    return product, partner, combined, robustness, source_check


def write_country_checkpoint(
    paths: dict[str, Path],
    product: pd.DataFrame,
    partner: pd.DataFrame,
    combined: pd.DataFrame,
    robustness: pd.DataFrame,
    source_check: dict[str, Any],
) -> None:
    paths["product"].parent.mkdir(parents=True, exist_ok=True)
    product.to_parquet(paths["product"], index=False)
    partner.to_parquet(paths["partner"], index=False)
    combined.to_parquet(paths["combined"], index=False)
    robustness.to_parquet(paths["robustness"], index=False)
    paths["source_check"].write_text(json.dumps(source_check, indent=2, sort_keys=True), encoding="utf-8")


def run_ev_hs4_expansion(
    *,
    country_sample: str = COUNTRY_SAMPLE,
    horizons: Iterable[int] = DEFAULT_HORIZONS,
    max_countries: int | None = None,
    fresh: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any], dict[str, Path]]:
    if country_sample != COUNTRY_SAMPLE:
        raise ValueError("The EV-style HS4 expansion runner is rd2-only; use --country-sample rd2_countries.")
    configure_country_sample(country_sample=country_sample)
    countries = country_info_records(save_country_panel())
    if max_countries is not None:
        countries = countries[: int(max_countries)]
    aggregate_path = sample_processed_path("exercise_12_export_aggregates.parquet", country_sample)
    if not aggregate_path.exists():
        raise FileNotFoundError(f"Exercise 12 aggregate is missing: {aggregate_path}")
    deflator = load_us_gdp_deflator()
    horizons = tuple(int(h) for h in horizons)
    checkpoint_dir = sample_processed_path("exercise_12_ev_hs4_checkpoints", country_sample)
    if fresh and checkpoint_dir.exists():
        shutil.rmtree(checkpoint_dir)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    started_at_utc = now_utc()
    all_product: list[pd.DataFrame] = []
    all_partner: list[pd.DataFrame] = []
    all_combined: list[pd.DataFrame] = []
    all_robustness: list[pd.DataFrame] = []
    source_checks: dict[int, dict[str, Any]] = {}
    print(
        f"Running Exercise 12 EV-style HS4 expansion decomposition for {len(countries)} rd2 countries; "
        f"horizons={horizons}, threshold=${ACTIVE_THRESHOLD_USD_2024:,.0f} in {CONSTANT_USD_YEAR} USD",
        flush=True,
    )
    for idx, country in enumerate(countries, start=1):
        print(f"[{idx}/{len(countries)}] {country.country} ({country.iso3}) before read: {memory_status()}", flush=True)
        paths = checkpoint_paths(checkpoint_dir, country.reporter_code)
        checkpoint = read_country_checkpoint(paths)
        if checkpoint is not None:
            product_rows, partner_rows, combined_rows, robustness_rows, source_check = checkpoint
            source_checks[country.reporter_code] = source_check
            if not product_rows.empty:
                all_product.append(product_rows)
            if not partner_rows.empty:
                all_partner.append(partner_rows)
            if not combined_rows.empty:
                all_combined.append(combined_rows)
            if not robustness_rows.empty:
                all_robustness.append(robustness_rows)
            print(
                f"  checkpoint: product_rows={len(product_rows):,} partner_rows={len(partner_rows):,} "
                f"combined_rows={len(combined_rows):,}; {memory_status()}",
                flush=True,
            )
            del product_rows, partner_rows, combined_rows, robustness_rows
            gc.collect()
            continue
        values = read_product_partner_for_reporter(aggregate_path, country.reporter_code)
        source_check = {
            "rows_after_filters": int(len(values)),
            "hs6_999999_rows_after_filters": int(normalize_hs6_series(values["cmd_code"]).eq("999999").sum()) if not values.empty else 0,
            "partner_code_0_rows_after_filters": int(pd.to_numeric(values["partner_code"], errors="coerce").eq(0).sum()) if not values.empty else 0,
        }
        cells, missing_deflator_years = prepare_hs4_values(values, deflator)
        source_check["source_years_without_deflator"] = missing_deflator_years
        product_rows, partner_rows, combined_rows, robustness_rows, diagnostics = compute_country_decomposition(cells, country, horizons)
        source_check.update(diagnostics)
        source_checks[country.reporter_code] = source_check
        write_country_checkpoint(paths, product_rows, partner_rows, combined_rows, robustness_rows, source_check)
        if not product_rows.empty:
            all_product.append(product_rows)
        if not partner_rows.empty:
            all_partner.append(partner_rows)
        if not combined_rows.empty:
            all_combined.append(combined_rows)
        if not robustness_rows.empty:
            all_robustness.append(robustness_rows)
        print(
            f"  cells={len(cells):,} product_rows={len(product_rows):,} partner_rows={len(partner_rows):,} "
            f"combined_rows={len(combined_rows):,}; "
            f"{memory_status()}",
            flush=True,
        )
        del values, cells, product_rows, partner_rows, combined_rows, robustness_rows
        gc.collect()

    product = pd.concat(all_product, ignore_index=True) if all_product else pd.DataFrame()
    partner = pd.concat(all_partner, ignore_index=True) if all_partner else pd.DataFrame()
    combined = pd.concat(all_combined, ignore_index=True) if all_combined else pd.DataFrame()
    robustness = pd.concat(all_robustness, ignore_index=True) if all_robustness else pd.DataFrame()
    latest = latest_5y_country_rows(product)
    combined_latest = latest_5y_combined_country_rows(combined)
    validation = validate_outputs(
        product_rows=product,
        partner_rows=partner,
        combined_rows=combined,
        latest_5y=latest,
        combined_latest_5y=combined_latest,
        robustness=robustness,
        countries=countries,
        horizons=horizons,
        source_checks=source_checks,
        deflator=deflator,
    )
    paths = write_outputs(
        country_sample=country_sample,
        aggregate_path=aggregate_path,
        deflator=deflator,
        product_rows=product,
        partner_rows=partner,
        combined_rows=combined,
        robustness_rows=robustness,
        validation=validation,
        started_at_utc=started_at_utc,
    )
    return product, partner, combined, robustness, validation, paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country-sample", choices=[COUNTRY_SAMPLE], default=COUNTRY_SAMPLE)
    parser.add_argument("--horizons", nargs="+", type=int, default=list(DEFAULT_HORIZONS))
    parser.add_argument("--max-countries", type=int, default=None, help="Optional smoke-test cap on countries processed.")
    parser.add_argument("--fresh", action="store_true", help="Delete per-country EV-style HS4 checkpoints first.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
    _product, _partner, _combined, _robustness, validation, paths = run_ev_hs4_expansion(
        country_sample=args.country_sample,
        horizons=args.horizons,
        max_countries=args.max_countries,
        fresh=args.fresh,
    )
    print("Validation:", json.dumps(validation, indent=2), flush=True)
    print("Wrote:", flush=True)
    for key, path in paths.items():
        print(f"  {key}: {path}", flush=True)


if __name__ == "__main__":
    main()
