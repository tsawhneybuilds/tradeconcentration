#!/usr/bin/env python3
"""Exercise 12 extensive-margin decomposition for export growth.

This script starts from the Exercise 12 export aggregate and decomposes
country export growth into mutually exclusive product/partner/cell channels:

1. net-new products,
2. net-new partners for products already exported in the base year,
3. new product-partner cells where both the product and partner already existed,
4. growth or contraction in cells already active in the base year.

The preferred product identity is LT/HGL weighted HS6 conversion to HS1992/H0,
matching the main Exercise 12 longitudinal product analysis. HS4 and HS2
outputs are included as robustness checks against HS revision and
code-granularity issues.
"""

from __future__ import annotations

import argparse
import gc
import json
import math
import os
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

from trade_concentration_pipeline import (  # noqa: E402
    COUNTRY_SAMPLE_CHOICES,
    LT_HGL_DATASET_DOI,
    LT_HGL_DATASET_VERSION,
    LT_HGL_TARGET_LABEL,
    LT_HGL_TARGET_REVISION,
    apply_lt_hgl_hs1992_conversion,
    configure_country_sample,
    drop_excluded_hs6,
    load_lt_hgl_hs1992_conversion_weights,
    lt_hgl_hs1992_coverage,
    normalize_hs_classification_code,
    sample_processed_path,
    sample_results_dir,
    save_country_panel,
)


PREFERRED_IDENTITY_MODE = "hs6_harmonized_family"
DEFAULT_IDENTITY_MODES = (PREFERRED_IDENTITY_MODE, "hs4", "hs2")
DEFAULT_HORIZONS = (5, 10)
LOW_BASE_VALUE_USD = 10_000.0
LEAST_TRADED_BASE_SHARE = 0.10

CATEGORY_ORDER = {
    "net_new_product": 1,
    "net_new_partner_existing_product": 2,
    "new_product_partner_cell_existing_product_partner": 3,
    "existing_product_partner_cell_growth": 4,
    "existing_product_partner_cell_contraction": 5,
    "existing_product_partner_cell_no_change": 6,
}

CATEGORY_LABELS = {
    "net_new_product": "Net-new products",
    "net_new_partner_existing_product": "Net-new partners for existing products",
    "new_product_partner_cell_existing_product_partner": "New product-partner cells for existing products and partners",
    "existing_product_partner_cell_growth": "Growth in already-active product-partner cells",
    "existing_product_partner_cell_contraction": "Contraction in already-active product-partner cells",
    "existing_product_partner_cell_no_change": "No change in already-active product-partner cells",
}

OVERLAP_CHANNEL_LABELS = {
    "future_cells_with_new_product": "Future cells whose product was absent in the base year",
    "future_cells_with_new_partner": "Future cells whose partner was absent in the base year",
    "future_cells_with_new_product_partner_cell": "Future product-partner cells absent in the base year",
    "future_new_cell_existing_product_partner": "Future new cells where both product and partner existed in the base year",
}

PRODUCT_ROBUSTNESS_LABELS = {
    "strict_zero_base_product": "Strict new product: base exports equal zero",
    "low_base_under_10k_grower": "Low-base product grower: base exports below $10,000",
    "least_traded_10pct_grower": "Least-traded product grower: product in bottom 10% of base export value",
    "all_positive_product_growth": "All products with positive product-level growth",
}


@dataclass(frozen=True)
class CountryInfo:
    reporter_code: int
    country: str
    iso3: str


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def file_sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def safe_divide(numerator: float, denominator: float) -> float:
    if denominator == 0 or not math.isfinite(float(denominator)):
        return np.nan
    return float(numerator) / float(denominator)


def normalize_hs6_series(series: pd.Series) -> pd.Series:
    return series.astype("string").str.extract(r"(\d{1,6})", expand=False).str.zfill(6)


def country_info_records(panel: pd.DataFrame) -> list[CountryInfo]:
    required = {"reporter_code", "country", "iso3"}
    missing = required - set(panel.columns)
    if missing:
        raise RuntimeError(f"Country panel is missing columns: {sorted(missing)}")
    out = panel[["reporter_code", "country", "iso3"]].drop_duplicates().copy()
    out["reporter_code"] = pd.to_numeric(out["reporter_code"], errors="coerce").astype(int)
    return [
        CountryInfo(int(row.reporter_code), str(row.country), str(row.iso3))
        for row in out.sort_values("reporter_code").itertuples(index=False)
    ]


def memory_status() -> str:
    if psutil is None:
        return "memory diagnostic unavailable"
    vm = psutil.virtual_memory()
    return f"available={vm.available / 1e9:.1f}GB used={vm.percent:.1f}%"


def read_product_partner_for_reporter(aggregate_path: Path, reporter_code: int) -> pd.DataFrame:
    columns = [
        "reporter_code",
        "year",
        "classification_code",
        "cmd_code",
        "partner_code",
        "trade_value",
    ]
    values = pd.read_parquet(
        aggregate_path,
        columns=columns,
        filters=[("reporter_code", "=", int(reporter_code)), ("dimension", "=", "product_partner_cell")],
    )
    if values.empty:
        return values
    values["reporter_code"] = pd.to_numeric(values["reporter_code"], errors="coerce").astype(int)
    values["year"] = pd.to_numeric(values["year"], errors="coerce").astype(int)
    values["partner_code"] = pd.to_numeric(values["partner_code"], errors="coerce")
    values["trade_value"] = pd.to_numeric(values["trade_value"], errors="coerce")
    values = values.dropna(subset=["partner_code", "trade_value"]).copy()
    values["partner_code"] = values["partner_code"].astype(int)
    values = values[(values["partner_code"] != 0) & (values["trade_value"] > 0)].copy()
    values["classification_code"] = values["classification_code"].map(normalize_hs_classification_code).replace("", "UNKNOWN")
    values["cmd_code"] = normalize_hs6_series(values["cmd_code"])
    values = values.dropna(subset=["cmd_code"])
    values = drop_excluded_hs6(values)
    if values.empty:
        return values
    return values.reset_index(drop=True)


def product_ids(values: pd.DataFrame, identity_mode: str, hs_lookup: pd.DataFrame | None) -> pd.Series:
    if identity_mode == PREFERRED_IDENTITY_MODE:
        if hs_lookup is None:
            raise RuntimeError(
                "hs6_harmonized_family now defaults to row-expanding LT/HGL HS1992 conversion; "
                "use prepare_cell_values with load_lt_hgl_hs1992_conversion_weights(). "
                "Pass an explicit legacy WCO mapping only for named legacy sensitivity checks."
            )
        if "harmonized_product_id" not in hs_lookup.columns:
            raise RuntimeError("Weighted LT/HGL conversion expands rows; use prepare_cell_values for hs6_harmonized_family.")
        lookup = hs_lookup[
            ["classification_code", "cmd_code", "harmonized_product_id"]
        ].drop_duplicates(["classification_code", "cmd_code"], keep="last")
        joined = values[["classification_code", "cmd_code"]].merge(
            lookup,
            on=["classification_code", "cmd_code"],
            how="left",
            sort=False,
            validate="many_to_one",
        )
        missing = joined["harmonized_product_id"].isna()
        missing_index = missing[missing].index
        joined.loc[missing_index, "harmonized_product_id"] = (
            "HSF_UNMATCHED:"
            + values.loc[missing_index, "classification_code"].astype(str)
            + "_"
            + values.loc[missing_index, "cmd_code"].astype(str)
        )
        return joined["harmonized_product_id"].astype("string")
    if identity_mode == "hs4":
        return ("HS4:" + values["cmd_code"].astype("string").str[:4]).astype("string")
    if identity_mode == "hs2":
        return ("HS2:" + values["cmd_code"].astype("string").str[:2]).astype("string")
    raise ValueError(f"Unsupported product identity mode: {identity_mode}")


def harmonization_coverage(values: pd.DataFrame, hs_lookup: pd.DataFrame) -> dict[str, Any]:
    """Summarize LT/HGL weighted-conversion coverage for filtered product-partner rows."""
    if values.empty:
        return {
            "hs_harmonization_distinct_pairs": 0,
            "hs_harmonization_missing_distinct_pairs": 0,
            "hs_harmonization_missing_rows": 0,
            "hs_harmonization_missing_trade_value": 0.0,
            "lt_hgl_weighted_target_pairs": 0,
        }
    coverage = lt_hgl_hs1992_coverage(values, hs_lookup)
    return {
        "hs_harmonization_distinct_pairs": int(coverage["lt_hgl_distinct_source_pairs"]),
        "hs_harmonization_missing_distinct_pairs": int(coverage["lt_hgl_missing_distinct_source_pairs"]),
        "hs_harmonization_missing_rows": int(coverage["lt_hgl_missing_rows"]),
        "hs_harmonization_missing_trade_value": float(coverage["lt_hgl_missing_trade_value"]),
        "lt_hgl_weighted_target_pairs": int(coverage["lt_hgl_weighted_target_pairs"]),
    }


def prepare_cell_values(values: pd.DataFrame, identity_mode: str, hs_lookup: pd.DataFrame | None = None) -> pd.DataFrame:
    if values.empty:
        return pd.DataFrame(columns=["reporter_code", "year", "product_id", "partner_code", "trade_value"])
    work = values[["reporter_code", "year", "classification_code", "cmd_code", "partner_code", "trade_value"]].copy()
    if identity_mode == PREFERRED_IDENTITY_MODE:
        work = apply_lt_hgl_hs1992_conversion(work, weights=hs_lookup)
    else:
        work["product_id"] = product_ids(work, identity_mode, hs_lookup)
    work = work.dropna(subset=["product_id", "partner_code", "trade_value"])
    out = (
        work.groupby(["reporter_code", "year", "product_id", "partner_code"], as_index=False, observed=True)["trade_value"]
        .sum()
    )
    return out[out["trade_value"] > 0].reset_index(drop=True)


def bottom_base_product_ids(base_product_totals: pd.Series, base_share: float = LEAST_TRADED_BASE_SHARE) -> set[str]:
    base_product_totals = base_product_totals[base_product_totals > 0].sort_values(kind="mergesort")
    total = float(base_product_totals.sum())
    if total <= 0 or base_product_totals.empty:
        return set()
    cumulative_before = (base_product_totals.cumsum() - base_product_totals) / total
    selected = base_product_totals.index[cumulative_before < base_share]
    return set(str(item) for item in selected)


def paired_year_cells(cells: pd.DataFrame, base_year: int, future_year: int) -> tuple[pd.DataFrame, float, float]:
    base = cells.loc[cells["year"].eq(base_year), ["product_id", "partner_code", "trade_value"]].copy()
    future = cells.loc[cells["year"].eq(future_year), ["product_id", "partner_code", "trade_value"]].copy()
    base_total = float(base["trade_value"].sum())
    future_total = float(future["trade_value"].sum())
    paired = base.merge(
        future,
        on=["product_id", "partner_code"],
        how="outer",
        suffixes=("_base", "_future"),
        sort=False,
    )
    paired["base_value"] = pd.to_numeric(paired["trade_value_base"], errors="coerce").fillna(0.0)
    paired["future_value"] = pd.to_numeric(paired["trade_value_future"], errors="coerce").fillna(0.0)
    paired = paired.drop(columns=["trade_value_base", "trade_value_future"])
    return paired, base_total, future_total


def add_category_metrics(rows: list[dict[str, Any]], metadata: dict[str, Any], grouped: pd.DataFrame, total_base: float, total_future: float) -> None:
    total_growth = float(total_future - total_base)
    total_positive_growth = float(grouped["gross_positive"].sum()) if "gross_positive" in grouped.columns else 0.0
    total_contraction = float(grouped["gross_contraction"].sum()) if "gross_contraction" in grouped.columns else 0.0
    for category in CATEGORY_ORDER:
        if category in grouped.index:
            row = grouped.loc[category].to_dict()
        else:
            row = {
                "net_contribution": 0.0,
                "gross_positive": 0.0,
                "gross_contraction": 0.0,
                "base_value": 0.0,
                "future_value": 0.0,
                "cell_count": 0,
                "product_count": 0,
                "partner_count": 0,
            }
        net_contribution = float(row.get("net_contribution", 0.0))
        gross_positive = float(row.get("gross_positive", 0.0))
        gross_contraction = float(row.get("gross_contraction", 0.0))
        rows.append(
            {
                **metadata,
                "category": category,
                "category_label": CATEGORY_LABELS[category],
                "category_order": CATEGORY_ORDER[category],
                "base_value": float(row.get("base_value", 0.0)),
                "future_value": float(row.get("future_value", 0.0)),
                "net_contribution": net_contribution,
                "gross_positive_contribution": gross_positive,
                "gross_contraction": gross_contraction,
                "cell_count": int(row.get("cell_count", 0)),
                "product_count": int(row.get("product_count", 0)),
                "partner_count": int(row.get("partner_count", 0)),
                "total_base_exports": total_base,
                "total_future_exports": total_future,
                "total_growth": total_growth,
                "total_gross_positive_growth": total_positive_growth,
                "total_gross_contraction": total_contraction,
                "net_growth_share": safe_divide(net_contribution, total_growth),
                "gross_positive_share": safe_divide(gross_positive, total_positive_growth),
                "gross_contraction_share": safe_divide(gross_contraction, total_contraction),
                "future_export_share": safe_divide(float(row.get("future_value", 0.0)), total_future),
            }
        )


def compute_mutually_exclusive_decomposition(
    cells: pd.DataFrame,
    country: CountryInfo,
    identity_mode: str,
    horizons: Iterable[int],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if cells.empty:
        return pd.DataFrame(rows)
    years = sorted(pd.to_numeric(cells["year"], errors="coerce").dropna().astype(int).unique().tolist())
    year_set = set(years)
    for base_year in years:
        base_cells = cells.loc[cells["year"].eq(base_year)]
        base_products = set(base_cells["product_id"].astype(str).unique().tolist())
        base_partners = set(pd.to_numeric(base_cells["partner_code"], errors="coerce").dropna().astype(int).unique().tolist())
        for horizon in horizons:
            future_year = int(base_year) + int(horizon)
            if future_year not in year_set:
                continue
            paired, base_total, future_total = paired_year_cells(cells, int(base_year), int(future_year))
            if paired.empty:
                continue
            paired["product_in_base"] = paired["product_id"].astype(str).isin(base_products)
            paired["partner_in_base"] = paired["partner_code"].astype(int).isin(base_partners)
            paired["net_contribution"] = paired["future_value"] - paired["base_value"]
            paired["gross_positive"] = paired["net_contribution"].clip(lower=0.0)
            paired["gross_contraction"] = (-paired["net_contribution"]).clip(lower=0.0)
            future_positive = paired["future_value"] > 0
            base_positive = paired["base_value"] > 0
            category_conditions = [
                future_positive & ~paired["product_in_base"],
                future_positive & paired["product_in_base"] & ~paired["partner_in_base"],
                future_positive & paired["product_in_base"] & paired["partner_in_base"] & ~base_positive,
                base_positive & (paired["net_contribution"] > 0),
                base_positive & (paired["net_contribution"] < 0),
                base_positive,
            ]
            paired["category"] = np.select(
                category_conditions,
                list(CATEGORY_ORDER.keys()),
                default="unclassified",
            )
            if paired["category"].eq("unclassified").any():
                examples = paired.loc[paired["category"].eq("unclassified")].head(5).to_dict(orient="records")
                raise RuntimeError(f"Unclassified product-partner cells for {country.iso3} {base_year}: {examples}")
            grouped = (
                paired.groupby("category", observed=True)
                .agg(
                    net_contribution=("net_contribution", "sum"),
                    gross_positive=("gross_positive", "sum"),
                    gross_contraction=("gross_contraction", "sum"),
                    base_value=("base_value", "sum"),
                    future_value=("future_value", "sum"),
                    cell_count=("category", "size"),
                    product_count=("product_id", "nunique"),
                    partner_count=("partner_code", "nunique"),
                )
            )
            metadata = {
                "country": country.country,
                "iso3": country.iso3,
                "reporter_code": country.reporter_code,
                "base_year": int(base_year),
                "future_year": int(future_year),
                "horizon": int(horizon),
                "identity_mode": identity_mode,
            }
            add_category_metrics(rows, metadata, grouped, base_total, future_total)
    return pd.DataFrame(rows)


def compute_overlapping_robustness(
    cells: pd.DataFrame,
    country: CountryInfo,
    identity_mode: str,
    horizons: Iterable[int],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if cells.empty:
        return pd.DataFrame(rows)
    years = sorted(pd.to_numeric(cells["year"], errors="coerce").dropna().astype(int).unique().tolist())
    year_set = set(years)
    for base_year in years:
        base_cells = cells.loc[cells["year"].eq(base_year)]
        base_products = set(base_cells["product_id"].astype(str).unique().tolist())
        base_partners = set(pd.to_numeric(base_cells["partner_code"], errors="coerce").dropna().astype(int).unique().tolist())
        for horizon in horizons:
            future_year = int(base_year) + int(horizon)
            if future_year not in year_set:
                continue
            paired, base_total, future_total = paired_year_cells(cells, int(base_year), int(future_year))
            if paired.empty:
                continue
            paired["product_in_base"] = paired["product_id"].astype(str).isin(base_products)
            paired["partner_in_base"] = paired["partner_code"].astype(int).isin(base_partners)
            paired["net_contribution"] = paired["future_value"] - paired["base_value"]
            paired["gross_positive"] = paired["net_contribution"].clip(lower=0.0)
            future_positive = paired["future_value"] > 0
            masks = {
                "future_cells_with_new_product": future_positive & ~paired["product_in_base"],
                "future_cells_with_new_partner": future_positive & ~paired["partner_in_base"],
                "future_cells_with_new_product_partner_cell": future_positive & paired["base_value"].eq(0),
                "future_new_cell_existing_product_partner": future_positive
                & paired["base_value"].eq(0)
                & paired["product_in_base"]
                & paired["partner_in_base"],
            }
            total_growth = float(future_total - base_total)
            total_positive_growth = float(paired["gross_positive"].sum())
            for channel, mask in masks.items():
                subset = paired.loc[mask].copy()
                rows.append(
                    {
                        "country": country.country,
                        "iso3": country.iso3,
                        "reporter_code": country.reporter_code,
                        "base_year": int(base_year),
                        "future_year": int(future_year),
                        "horizon": int(horizon),
                        "identity_mode": identity_mode,
                        "overlap_channel": channel,
                        "overlap_channel_label": OVERLAP_CHANNEL_LABELS[channel],
                        "base_value": float(subset["base_value"].sum()) if not subset.empty else 0.0,
                        "future_value": float(subset["future_value"].sum()) if not subset.empty else 0.0,
                        "net_contribution": float(subset["net_contribution"].sum()) if not subset.empty else 0.0,
                        "gross_positive_contribution": float(subset["gross_positive"].sum()) if not subset.empty else 0.0,
                        "cell_count": int(len(subset)),
                        "product_count": int(subset["product_id"].nunique()) if not subset.empty else 0,
                        "partner_count": int(subset["partner_code"].nunique()) if not subset.empty else 0,
                        "total_base_exports": base_total,
                        "total_future_exports": future_total,
                        "total_growth": total_growth,
                        "total_gross_positive_growth": total_positive_growth,
                        "net_growth_share": safe_divide(float(subset["net_contribution"].sum()) if not subset.empty else 0.0, total_growth),
                        "gross_positive_share": safe_divide(
                            float(subset["gross_positive"].sum()) if not subset.empty else 0.0,
                            total_positive_growth,
                        ),
                    }
                )
    return pd.DataFrame(rows)


def compute_product_entry_robustness(
    cells: pd.DataFrame,
    country: CountryInfo,
    identity_mode: str,
    horizons: Iterable[int],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if cells.empty:
        return pd.DataFrame(rows)
    product_years = (
        cells.groupby(["year", "product_id"], as_index=False, observed=True)["trade_value"].sum()
        .sort_values(["year", "product_id"])
        .reset_index(drop=True)
    )
    years = sorted(pd.to_numeric(product_years["year"], errors="coerce").dropna().astype(int).unique().tolist())
    year_set = set(years)
    for base_year in years:
        base = product_years.loc[product_years["year"].eq(base_year), ["product_id", "trade_value"]].copy()
        base = base.rename(columns={"trade_value": "base_value"})
        base_product_totals = base.set_index("product_id")["base_value"]
        bottom_products = bottom_base_product_ids(base_product_totals)
        for horizon in horizons:
            future_year = int(base_year) + int(horizon)
            if future_year not in year_set:
                continue
            future = product_years.loc[product_years["year"].eq(future_year), ["product_id", "trade_value"]].copy()
            future = future.rename(columns={"trade_value": "future_value"})
            paired = base.merge(future, on="product_id", how="outer", sort=False)
            paired["base_value"] = pd.to_numeric(paired["base_value"], errors="coerce").fillna(0.0)
            paired["future_value"] = pd.to_numeric(paired["future_value"], errors="coerce").fillna(0.0)
            paired["net_contribution"] = paired["future_value"] - paired["base_value"]
            paired["gross_positive"] = paired["net_contribution"].clip(lower=0.0)
            total_base = float(paired["base_value"].sum())
            total_future = float(paired["future_value"].sum())
            total_growth = total_future - total_base
            total_positive_growth = float(paired["gross_positive"].sum())
            masks = {
                "strict_zero_base_product": paired["base_value"].eq(0) & paired["future_value"].gt(0),
                "low_base_under_10k_grower": paired["base_value"].gt(0)
                & paired["base_value"].lt(LOW_BASE_VALUE_USD)
                & paired["net_contribution"].gt(0),
                "least_traded_10pct_grower": paired["product_id"].astype(str).isin(bottom_products)
                & paired["net_contribution"].gt(0),
                "all_positive_product_growth": paired["net_contribution"].gt(0),
            }
            for definition, mask in masks.items():
                subset = paired.loc[mask]
                contribution = float(subset["net_contribution"].sum()) if not subset.empty else 0.0
                gross_positive = float(subset["gross_positive"].sum()) if not subset.empty else 0.0
                rows.append(
                    {
                        "country": country.country,
                        "iso3": country.iso3,
                        "reporter_code": country.reporter_code,
                        "base_year": int(base_year),
                        "future_year": int(future_year),
                        "horizon": int(horizon),
                        "identity_mode": identity_mode,
                        "product_definition": definition,
                        "product_definition_label": PRODUCT_ROBUSTNESS_LABELS[definition],
                        "base_value": float(subset["base_value"].sum()) if not subset.empty else 0.0,
                        "future_value": float(subset["future_value"].sum()) if not subset.empty else 0.0,
                        "net_contribution": contribution,
                        "gross_positive_contribution": gross_positive,
                        "product_count": int(subset["product_id"].nunique()) if not subset.empty else 0,
                        "total_base_exports": total_base,
                        "total_future_exports": total_future,
                        "total_growth": total_growth,
                        "total_gross_positive_growth": total_positive_growth,
                        "net_growth_share": safe_divide(contribution, total_growth),
                        "gross_positive_share": safe_divide(gross_positive, total_positive_growth),
                        "low_base_value_usd": LOW_BASE_VALUE_USD,
                        "least_traded_base_share_cutoff": LEAST_TRADED_BASE_SHARE,
                    }
                )
    return pd.DataFrame(rows)


def latest_country_rows(decomposition: pd.DataFrame) -> pd.DataFrame:
    if decomposition.empty:
        return pd.DataFrame()
    base = decomposition[decomposition["identity_mode"].eq(PREFERRED_IDENTITY_MODE)].copy()
    if base.empty:
        return pd.DataFrame()
    keys = ["reporter_code", "horizon"]
    latest_keys = base.groupby(keys, as_index=False)["future_year"].max()
    latest = base.merge(latest_keys, on=[*keys, "future_year"], how="inner")
    metric_cols = [
        "country",
        "iso3",
        "reporter_code",
        "horizon",
        "base_year",
        "future_year",
        "total_base_exports",
        "total_future_exports",
        "total_growth",
        "total_gross_positive_growth",
        "total_gross_contraction",
    ]
    wide_base = latest[metric_cols].drop_duplicates(keys).copy()
    share_wide = latest.pivot_table(
        index=keys,
        columns="category",
        values="gross_positive_share",
        aggfunc="first",
    ).reset_index()
    share_wide = share_wide.rename(columns={category: f"{category}_gross_positive_share" for category in CATEGORY_ORDER})
    contrib_wide = latest.pivot_table(
        index=keys,
        columns="category",
        values="net_contribution",
        aggfunc="first",
    ).reset_index()
    contrib_wide = contrib_wide.rename(columns={category: f"{category}_net_contribution" for category in CATEGORY_ORDER})
    out = wide_base.merge(share_wide, on=keys, how="left").merge(contrib_wide, on=keys, how="left")
    return out.sort_values(["horizon", "country"]).reset_index(drop=True)


def summary_rows(decomposition: pd.DataFrame) -> pd.DataFrame:
    if decomposition.empty:
        return pd.DataFrame()
    numeric_cols = [
        "net_contribution",
        "gross_positive_contribution",
        "gross_contraction",
        "net_growth_share",
        "gross_positive_share",
        "gross_contraction_share",
        "cell_count",
        "product_count",
        "partner_count",
    ]
    work = decomposition.copy()
    summary = (
        work.groupby(["identity_mode", "horizon", "category", "category_label", "category_order"], as_index=False, observed=True)
        .agg(
            country_year_pairs=("reporter_code", "size"),
            countries=("reporter_code", "nunique"),
            median_net_contribution=("net_contribution", "median"),
            median_gross_positive_contribution=("gross_positive_contribution", "median"),
            median_gross_contraction=("gross_contraction", "median"),
            median_net_growth_share=("net_growth_share", "median"),
            median_gross_positive_share=("gross_positive_share", "median"),
            median_gross_contraction_share=("gross_contraction_share", "median"),
            mean_gross_positive_share=("gross_positive_share", "mean"),
            median_cell_count=("cell_count", "median"),
            median_product_count=("product_count", "median"),
            median_partner_count=("partner_count", "median"),
        )
        .sort_values(["identity_mode", "horizon", "category_order"])
    )
    for col in numeric_cols:
        if col in summary.columns:
            summary[col] = pd.to_numeric(summary[col], errors="coerce")
    return summary.reset_index(drop=True)


def country_weighted_summary_rows(decomposition: pd.DataFrame) -> pd.DataFrame:
    """Summarize channels after giving each reporter equal weight.

    The main summary is a median over all country-year windows. This appendix
    first takes each reporter's within-country median, then takes the median
    across reporters so countries with longer time coverage do not receive more
    weight in the headline distribution.
    """
    if decomposition.empty:
        return pd.DataFrame()
    group_cols = ["identity_mode", "horizon", "category", "category_label", "category_order"]
    country = (
        decomposition.groupby([*group_cols, "reporter_code", "country", "iso3"], as_index=False, observed=True)
        .agg(
            country_year_pairs=("reporter_code", "size"),
            country_median_net_contribution=("net_contribution", "median"),
            country_median_gross_positive_contribution=("gross_positive_contribution", "median"),
            country_median_gross_contraction=("gross_contraction", "median"),
            country_median_net_growth_share=("net_growth_share", "median"),
            country_median_gross_positive_share=("gross_positive_share", "median"),
            country_median_gross_contraction_share=("gross_contraction_share", "median"),
            country_median_cell_count=("cell_count", "median"),
            country_median_product_count=("product_count", "median"),
            country_median_partner_count=("partner_count", "median"),
        )
    )
    summary = (
        country.groupby(group_cols, as_index=False, observed=True)
        .agg(
            countries=("reporter_code", "nunique"),
            min_country_year_pairs=("country_year_pairs", "min"),
            median_country_year_pairs=("country_year_pairs", "median"),
            max_country_year_pairs=("country_year_pairs", "max"),
            median_country_median_net_contribution=("country_median_net_contribution", "median"),
            median_country_median_gross_positive_contribution=("country_median_gross_positive_contribution", "median"),
            median_country_median_gross_contraction=("country_median_gross_contraction", "median"),
            median_country_median_net_growth_share=("country_median_net_growth_share", "median"),
            median_country_median_gross_positive_share=("country_median_gross_positive_share", "median"),
            median_country_median_gross_contraction_share=("country_median_gross_contraction_share", "median"),
            median_country_median_cell_count=("country_median_cell_count", "median"),
            median_country_median_product_count=("country_median_product_count", "median"),
            median_country_median_partner_count=("country_median_partner_count", "median"),
        )
        .sort_values(["identity_mode", "horizon", "category_order"])
        .reset_index(drop=True)
    )
    summary["summary_weighting"] = "equal_country_after_within_country_median"
    return summary


def validate_outputs(
    source_checks: dict[int, dict[str, Any]],
    decomposition: pd.DataFrame,
    latest: pd.DataFrame,
    product_robustness: pd.DataFrame,
    countries: list[CountryInfo],
    identity_modes: Iterable[str],
    horizons: Iterable[int],
    harmonization_pair_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    validation: dict[str, Any] = {
        "created_at_utc": now_utc(),
        "country_count_expected": int(len(countries)),
        "country_count_decomposition": int(decomposition["reporter_code"].nunique()) if not decomposition.empty else 0,
        "country_count_latest": int(latest["reporter_code"].nunique()) if not latest.empty else 0,
        "identity_modes": list(identity_modes),
        "horizons": [int(h) for h in horizons],
        "product_excluded_hs6_codes": ["999999"],
        "partner_code_0_excluded": True,
        "hs_harmonization_method": "LT/HGL weighted conversion to HS1992/H0",
        "hs_harmonization_source_doi": LT_HGL_DATASET_DOI,
        "hs_harmonization_source_version": LT_HGL_DATASET_VERSION,
        "hs_harmonization_target": f"{LT_HGL_TARGET_LABEL}/{LT_HGL_TARGET_REVISION}",
        "mutually_exclusive_categories": list(CATEGORY_ORDER.keys()),
    }
    source_rows = sum(int(check.get("rows_after_filters", 0)) for check in source_checks.values())
    excluded_rows = sum(int(check.get("hs6_999999_rows_after_filters", 0)) for check in source_checks.values())
    partner_zero_rows = sum(int(check.get("partner_code_0_rows_after_filters", 0)) for check in source_checks.values())
    validation["source_product_partner_rows_after_filters"] = int(source_rows)
    validation["source_hs6_999999_rows_after_filters"] = int(excluded_rows)
    validation["source_partner_code_0_rows_after_filters"] = int(partner_zero_rows)
    harmonization_pair_diagnostics = harmonization_pair_diagnostics or {}
    validation["hs_harmonization_distinct_pairs"] = int(
        harmonization_pair_diagnostics.get("hs_harmonization_distinct_pairs", 0)
    )
    validation["hs_harmonization_missing_distinct_pairs"] = int(
        harmonization_pair_diagnostics.get("hs_harmonization_missing_distinct_pairs", 0)
    )
    validation["hs_harmonization_missing_rows"] = int(
        sum(int(check.get("hs_harmonization_missing_rows", 0)) for check in source_checks.values())
    )
    validation["hs_harmonization_missing_trade_value"] = float(
        sum(float(check.get("hs_harmonization_missing_trade_value", 0.0)) for check in source_checks.values())
    )
    if not decomposition.empty:
        key_cols = ["reporter_code", "base_year", "future_year", "horizon", "identity_mode"]
        sums = (
            decomposition.groupby(key_cols, as_index=False, observed=True)
            .agg(
                category_net_sum=("net_contribution", "sum"),
                total_growth=("total_growth", "first"),
                total_base_exports=("total_base_exports", "first"),
                total_future_exports=("total_future_exports", "first"),
            )
        )
        sums["residual"] = sums["category_net_sum"] - sums["total_growth"]
        sums["residual_tolerance"] = np.maximum(
            10.0,
            1e-12 * (sums["total_base_exports"].abs() + sums["total_future_exports"].abs()),
        )
        sums["residual_within_tolerance"] = sums["residual"].abs() <= sums["residual_tolerance"]
        validation["max_abs_category_accounting_residual"] = float(sums["residual"].abs().max())
        validation["max_category_accounting_residual_tolerance"] = float(sums["residual_tolerance"].max())
        validation["category_accounting_residual_violations"] = int((~sums["residual_within_tolerance"]).sum())
        duplicates = decomposition.duplicated([*key_cols, "category"]).sum()
        validation["duplicate_category_keys"] = int(duplicates)
        validation["rows_by_identity_horizon"] = (
            decomposition.groupby(["identity_mode", "horizon"], observed=True)
            .size()
            .reset_index(name="rows")
            .to_dict(orient="records")
        )
    else:
        validation["max_abs_category_accounting_residual"] = None
        validation["max_category_accounting_residual_tolerance"] = None
        validation["category_accounting_residual_violations"] = 0
        validation["duplicate_category_keys"] = 0
        validation["rows_by_identity_horizon"] = []
    validation["product_robustness_rows"] = int(len(product_robustness))
    blockers = []
    if validation["country_count_decomposition"] != len(countries):
        blockers.append("decomposition country count does not equal country sample size")
    if validation["source_hs6_999999_rows_after_filters"] != 0:
        blockers.append("filtered source values still contain HS6 999999")
    if validation["source_partner_code_0_rows_after_filters"] != 0:
        blockers.append("filtered source values still contain partner_code 0")
    if validation["duplicate_category_keys"] != 0:
        blockers.append("duplicate mutually exclusive category keys")
    if validation["category_accounting_residual_violations"] != 0:
        blockers.append("mutually exclusive categories do not sum to total growth")
    if validation["hs_harmonization_missing_rows"] != 0:
        blockers.append("LT/HGL HS1992 conversion is missing filtered source rows")
    validation["blockers"] = blockers
    validation["status"] = "ok" if not blockers else "blocked"
    if blockers:
        raise RuntimeError(f"Exercise 12 extensive-margin validation failed: {blockers}")
    return validation


def write_memo(
    output_path: Path,
    validation: dict[str, Any],
    summary: pd.DataFrame,
    latest: pd.DataFrame,
    product_robustness: pd.DataFrame,
) -> None:
    preferred = summary[
        summary["identity_mode"].eq(PREFERRED_IDENTITY_MODE)
        & summary["horizon"].eq(5)
        & summary["category"].isin(
            [
                "net_new_product",
                "net_new_partner_existing_product",
                "new_product_partner_cell_existing_product_partner",
                "existing_product_partner_cell_growth",
                "existing_product_partner_cell_contraction",
            ]
        )
    ].copy()
    preferred_lines = []
    for row in preferred.sort_values("category_order").itertuples(index=False):
        share = getattr(row, "median_gross_positive_share", np.nan)
        net_share = getattr(row, "median_net_growth_share", np.nan)
        preferred_lines.append(
            f"- {row.category_label}: median gross-positive share {share:.3f}; median net-growth share {net_share:.3f}."
        )
    latest_h5 = latest[latest["horizon"].eq(5)].copy()
    top_new_products = latest_h5.sort_values("net_new_product_gross_positive_share", ascending=False).head(8)
    country_lines = []
    for row in top_new_products.itertuples(index=False):
        country_lines.append(
            f"- {row.country} ({row.iso3}), {int(row.base_year)}-{int(row.future_year)}: "
            f"net-new products {row.net_new_product_gross_positive_share:.1%}, "
            f"net-new partners {row.net_new_partner_existing_product_gross_positive_share:.1%}, "
            f"new existing-product-partner cells {row.new_product_partner_cell_existing_product_partner_gross_positive_share:.1%}."
        )

    product_pref = product_robustness[
        product_robustness["identity_mode"].eq(PREFERRED_IDENTITY_MODE)
        & product_robustness["horizon"].eq(5)
    ].copy()
    product_summary = (
        product_pref.groupby(["product_definition", "product_definition_label"], as_index=False, observed=True)
        .agg(median_gross_positive_share=("gross_positive_share", "median"), countries=("reporter_code", "nunique"))
        .sort_values("product_definition")
    )
    product_lines = [
        f"- {row.product_definition_label}: median gross-positive share {row.median_gross_positive_share:.3f} across {int(row.countries)} countries."
        for row in product_summary.itertuples(index=False)
    ]

    memo = f"""# Exercise 12 Extensive-Margin Decomposition

Generated: {validation["created_at_utc"]}

## Research Design

Question: for each rd2 country, how much export growth comes from new products, new partners, and new product-partner cells?

Estimand: for reporter country c, base year t, horizon h, and product identity p, decompose export growth

`Delta X_c,t,h = sum_(p,k) [x_c,p,k,t+h - x_c,p,k,t]`

across product-partner cells `(p,k)`. The preferred product identity is LT/HGL weighted conversion of HS6 vintages to HS1992/H0. HS4 and HS2 are robustness identities.

Harmonization: product-dependent rows exclude HS6 `999999` before conversion, use the official Harvard Dataverse weighted conversion tables (DOI `{LT_HGL_DATASET_DOI}`, version `{LT_HGL_DATASET_VERSION}`), multiply trade value by the conversion weight, aggregate to target HS1992 product code, and then run the decomposition.

The mutually exclusive rule is hierarchical:

1. A future cell whose product was absent in the base year is counted as `net_new_product`.
2. If the product existed but the partner was absent, it is counted as `net_new_partner_existing_product`.
3. If product and partner both existed but that product-partner cell was absent, it is counted as `new_product_partner_cell_existing_product_partner`.
4. Base-active cells are split into growth, contraction, and no-change categories.

This prevents double-counting. A product sold to a brand-new destination is counted as product entry first; the overlapping robustness table separately reports the non-exclusive new-partner and new-cell totals.

## Main 5-Year Medians

{chr(10).join(preferred_lines) if preferred_lines else "- No preferred summary rows produced."}

## Countries With High Latest Net-New Product Shares

{chr(10).join(country_lines) if country_lines else "- No latest rows produced."}

## Low-Base Product Robustness

The product-entry robustness table keeps the original Exercise 12 low-base idea: strict zero base, base exports below $10,000, and products accounting for the bottom 10% of base-period export value.

{chr(10).join(product_lines) if product_lines else "- No product-entry robustness rows produced."}

## Validation

- Country count in decomposition: {validation["country_count_decomposition"]} of {validation["country_count_expected"]}.
- Filtered product-partner source rows: {validation["source_product_partner_rows_after_filters"]:,}.
- HS6 999999 rows after product-dependent filtering: {validation["source_hs6_999999_rows_after_filters"]}.
- partner_code 0 rows after filtering: {validation["source_partner_code_0_rows_after_filters"]}.
- Max absolute category accounting residual: {validation["max_abs_category_accounting_residual"]}.
- Status: {validation["status"]}.

## Files

- Country-year category table: `results/samples/rd2_countries/exercise_12_extensive_margin_tables/extensive_margin_country_year.csv`
	- Latest country table: `results/samples/rd2_countries/exercise_12_extensive_margin_tables/extensive_margin_latest.csv`
	- Summary table: `results/samples/rd2_countries/exercise_12_extensive_margin_tables/extensive_margin_summary.csv`
	- Equal-country summary table: `results/samples/rd2_countries/exercise_12_extensive_margin_tables/extensive_margin_country_weighted_summary.csv`
	- Overlapping robustness table: `results/samples/rd2_countries/exercise_12_extensive_margin_tables/extensive_margin_overlapping_robustness.csv`
- Low-base product robustness table: `results/samples/rd2_countries/exercise_12_extensive_margin_tables/extensive_margin_product_entry_robustness.csv`
"""
    output_path.write_text(memo, encoding="utf-8")


def write_outputs(
    country_sample: str,
    aggregate_path: Path,
    decomposition: pd.DataFrame,
    overlapping: pd.DataFrame,
    product_robustness: pd.DataFrame,
    validation: dict[str, Any],
    started_at_utc: str,
) -> dict[str, Path]:
    processed_path = sample_processed_path("exercise_12_extensive_margin_decomposition.parquet", country_sample)
    processed_path.parent.mkdir(parents=True, exist_ok=True)
    decomposition.to_parquet(processed_path, index=False)

    tables_dir = sample_results_dir(country_sample) / "exercise_12_extensive_margin_tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    latest = latest_country_rows(decomposition)
    summary = summary_rows(decomposition)
    country_weighted_summary = country_weighted_summary_rows(decomposition)
    paths = {
        "country_year": tables_dir / "extensive_margin_country_year.csv",
        "latest": tables_dir / "extensive_margin_latest.csv",
        "summary": tables_dir / "extensive_margin_summary.csv",
        "country_weighted_summary": tables_dir / "extensive_margin_country_weighted_summary.csv",
        "overlapping_robustness": tables_dir / "extensive_margin_overlapping_robustness.csv",
        "product_entry_robustness": tables_dir / "extensive_margin_product_entry_robustness.csv",
        "validation": tables_dir / "extensive_margin_validation.json",
        "memo": sample_results_dir(country_sample) / "exercise_12_extensive_margin.md",
        "manifest": sample_results_dir(country_sample) / "run_manifest_exercise_12_extensive_margin.json",
        "processed": processed_path,
    }
    decomposition.to_csv(paths["country_year"], index=False)
    latest.to_csv(paths["latest"], index=False)
    summary.to_csv(paths["summary"], index=False)
    country_weighted_summary.to_csv(paths["country_weighted_summary"], index=False)
    overlapping.to_csv(paths["overlapping_robustness"], index=False)
    product_robustness.to_csv(paths["product_entry_robustness"], index=False)
    paths["validation"].write_text(json.dumps(validation, indent=2, sort_keys=True), encoding="utf-8")
    write_memo(paths["memo"], validation, summary, latest, product_robustness)

    manifest = {
        "created_at_utc": now_utc(),
        "started_at_utc": started_at_utc,
        "country_sample": country_sample,
        "source_aggregate": str(aggregate_path.relative_to(ROOT)),
        "source_aggregate_sha256": file_sha256(aggregate_path),
        "processed_output": str(processed_path.relative_to(ROOT)),
        "result_files": {
            key: str(path.relative_to(ROOT))
            for key, path in paths.items()
            if key not in {"processed"} and path.suffix.lower() in {".csv", ".json", ".md"}
        },
        "row_counts": {
            "decomposition": int(len(decomposition)),
            "latest": int(len(latest)),
            "summary": int(len(summary)),
            "country_weighted_summary": int(len(country_weighted_summary)),
            "overlapping_robustness": int(len(overlapping)),
            "product_entry_robustness": int(len(product_robustness)),
        },
        "definition": {
            "unit_of_observation": "reporter-country base-year future-year horizon product-identity-mode growth channel",
            "preferred_product_identity": PREFERRED_IDENTITY_MODE,
            "preferred_product_identity_plain_english": "LT/HGL weighted HS6 conversion to HS1992/H0 product codes",
            "preferred_product_identity_source_doi": LT_HGL_DATASET_DOI,
            "preferred_product_identity_source_version": LT_HGL_DATASET_VERSION,
            "preferred_product_identity_target": f"{LT_HGL_TARGET_LABEL}/{LT_HGL_TARGET_REVISION}",
            "identity_robustness_modes": [mode for mode in DEFAULT_IDENTITY_MODES if mode != PREFERRED_IDENTITY_MODE],
            "mutually_exclusive_category_order": CATEGORY_ORDER,
            "product_excluded_hs6_codes": ["999999"],
            "partner_code_0_excluded": True,
            "low_base_value_usd": LOW_BASE_VALUE_USD,
            "least_traded_base_share": LEAST_TRADED_BASE_SHARE,
        },
        "validation": validation,
    }
    paths["manifest"].write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return paths


def run_extensive_margin(
    country_sample: str,
    identity_modes: Iterable[str],
    horizons: Iterable[int],
    max_countries: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any], dict[str, Path]]:
    configure_country_sample(country_sample=country_sample)
    countries = country_info_records(save_country_panel())
    if max_countries is not None:
        countries = countries[: int(max_countries)]
    aggregate_path = sample_processed_path("exercise_12_export_aggregates.parquet", country_sample)
    if not aggregate_path.exists():
        raise FileNotFoundError(f"Exercise 12 aggregate is missing: {aggregate_path}")

    hs_lookup = load_lt_hgl_hs1992_conversion_weights()
    all_decomp: list[pd.DataFrame] = []
    all_overlap: list[pd.DataFrame] = []
    all_product_robustness: list[pd.DataFrame] = []
    source_checks: dict[int, dict[str, Any]] = {}
    harmonization_lookup_pairs = set(
        tuple(row)
        for row in hs_lookup[["source_classification_code", "source_cmd_code"]]
        .drop_duplicates()
        .itertuples(index=False, name=None)
    )
    harmonization_pairs_seen: set[tuple[str, str]] = set()
    harmonization_missing_pairs_seen: set[tuple[str, str]] = set()

    identity_modes = tuple(identity_modes)
    horizons = tuple(int(h) for h in horizons)
    started_at_utc = now_utc()
    print(
        f"Running Exercise 12 extensive-margin decomposition for {country_sample}: "
        f"{len(countries)} countries, modes={identity_modes}, horizons={horizons}",
        flush=True,
    )
    for idx, country in enumerate(countries, start=1):
        print(f"[{idx}/{len(countries)}] {country.country} ({country.iso3}) before read: {memory_status()}", flush=True)
        values = read_product_partner_for_reporter(aggregate_path, country.reporter_code)
        source_checks[country.reporter_code] = {
            "rows_after_filters": int(len(values)),
            "hs6_999999_rows_after_filters": int(normalize_hs6_series(values["cmd_code"]).eq("999999").sum()) if not values.empty else 0,
            "partner_code_0_rows_after_filters": int(pd.to_numeric(values["partner_code"], errors="coerce").eq(0).sum()) if not values.empty else 0,
            **harmonization_coverage(values, hs_lookup),
        }
        if not values.empty:
            country_pairs = set(
                tuple(row)
                for row in values[["classification_code", "cmd_code"]].drop_duplicates().itertuples(index=False, name=None)
            )
            harmonization_pairs_seen.update(country_pairs)
            harmonization_missing_pairs_seen.update(country_pairs - harmonization_lookup_pairs)
        print(f"  source rows after filters: {len(values):,}; {memory_status()}", flush=True)
        if values.empty:
            continue
        for identity_mode in identity_modes:
            cells = prepare_cell_values(values, identity_mode, hs_lookup=hs_lookup)
            decomp = compute_mutually_exclusive_decomposition(cells, country, identity_mode, horizons)
            overlap = compute_overlapping_robustness(cells, country, identity_mode, horizons)
            product_robust = compute_product_entry_robustness(cells, country, identity_mode, horizons)
            if not decomp.empty:
                all_decomp.append(decomp)
            if not overlap.empty:
                all_overlap.append(overlap)
            if not product_robust.empty:
                all_product_robustness.append(product_robust)
            print(f"  {identity_mode}: cells={len(cells):,} rows={len(decomp):,}; {memory_status()}", flush=True)
            del cells, decomp, overlap, product_robust
            gc.collect()
        del values
        gc.collect()

    decomposition = pd.concat(all_decomp, ignore_index=True) if all_decomp else pd.DataFrame()
    overlapping = pd.concat(all_overlap, ignore_index=True) if all_overlap else pd.DataFrame()
    product_robustness = pd.concat(all_product_robustness, ignore_index=True) if all_product_robustness else pd.DataFrame()
    latest = latest_country_rows(decomposition)
    validation = validate_outputs(
        source_checks,
        decomposition,
        latest,
        product_robustness,
        countries,
        identity_modes,
        horizons,
        {
            "hs_harmonization_distinct_pairs": len(harmonization_pairs_seen),
            "hs_harmonization_missing_distinct_pairs": len(harmonization_missing_pairs_seen),
        },
    )
    paths = write_outputs(
        country_sample,
        aggregate_path,
        decomposition,
        overlapping,
        product_robustness,
        validation,
        started_at_utc,
    )
    return decomposition, overlapping, product_robustness, validation, paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country-sample", choices=COUNTRY_SAMPLE_CHOICES, default="rd2_countries")
    parser.add_argument("--identity-modes", nargs="+", default=list(DEFAULT_IDENTITY_MODES), choices=list(DEFAULT_IDENTITY_MODES))
    parser.add_argument("--horizons", nargs="+", type=int, default=list(DEFAULT_HORIZONS))
    parser.add_argument("--max-countries", type=int, default=None, help="Optional smoke-test cap on countries processed.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
    _decomposition, _overlapping, _product_robustness, validation, paths = run_extensive_margin(
        country_sample=args.country_sample,
        identity_modes=args.identity_modes,
        horizons=args.horizons,
        max_countries=args.max_countries,
    )
    print("Validation:", json.dumps({k: v for k, v in validation.items() if k != "rows_by_identity_horizon"}, indent=2), flush=True)
    print("Wrote:", flush=True)
    for key, path in paths.items():
        print(f"  {key}: {path}", flush=True)


if __name__ == "__main__":
    main()
