#!/usr/bin/env python3
"""Compute fixed-universe Product Gini over harmonized HS6 product families.

The website-facing measure is zero-inclusive: every rd2 reporter-year is
measured over the same flow-specific product universe, defined as the 2000-2024
union of positive world_broad LT/HGL HS1992 product-family trade.
"""

from __future__ import annotations

import argparse
import gc
import json
import math
import os
import re
import resource
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import trade_concentration_pipeline as tcp  # noqa: E402
from concentration_metrics import active_gini  # noqa: E402


COUNTRY_SAMPLE = "rd2_countries"
BENCHMARK_SAMPLE = "world_broad"
PRODUCT_ID_MODE = "harmonized_hs6_family"
FLOW_CHOICES = ("Exports", "Imports")
DEFAULT_START_YEAR = 2000
DEFAULT_END_YEAR = 2024
DEFAULT_REQUIRE_BALANCED_COUNTRIES = 55
RESULT_DIRNAME = "fixed_universe_product_gini_tables"
PANEL_FILENAME = "fixed_universe_product_gini_panel.parquet"
EXCLUDED_PRODUCT_RE = re.compile(r"999999")


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        if math.isnan(float(value)):
            return None
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def current_rss_mb() -> float | None:
    try:
        import psutil  # type: ignore

        return float(psutil.Process(os.getpid()).memory_info().rss / (1024**2))
    except Exception:
        try:
            rss = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        except Exception:
            return None
        if sys.platform == "darwin":
            return rss / (1024**2)
        return rss / 1024


def log_resource(label: str, memory_budget_gb: float | None = None) -> None:
    rss = current_rss_mb()
    if rss is None:
        print(f"[resource] {label}: rss unavailable")
        return
    print(f"[resource] {label}: rss={rss:,.1f} MB")
    if memory_budget_gb is not None and memory_budget_gb > 0 and rss > memory_budget_gb * 1024:
        raise RuntimeError(f"Memory budget exceeded after {label}: {rss / 1024:.2f} GB > {memory_budget_gb:.2f} GB")


def flow_slug(flow: str) -> str:
    return "exports" if flow == "Exports" else "imports"


def value_noun(flow: str) -> str:
    return "exports" if flow == "Exports" else "imports"


def world_value_column(flow: str) -> str:
    return f"world_product_{value_noun(flow)}"


def artifact_stem(flow: str) -> str:
    return "world_relative_product_gini" if flow == "Exports" else "world_relative_import_product_gini"


def source_paths(flow: str) -> dict[str, Path]:
    stem = artifact_stem(flow)
    noun = value_noun(flow)
    return {
        "country_product": tcp.sample_processed_dir(COUNTRY_SAMPLE)
        / f"{stem}_{PRODUCT_ID_MODE}_rd2_product_{noun}.parquet",
        "world_product": tcp.sample_processed_dir(BENCHMARK_SAMPLE)
        / f"{stem}_{PRODUCT_ID_MODE}_world_product_{noun}.parquet",
    }


def result_dir() -> Path:
    return tcp.sample_results_dir(COUNTRY_SAMPLE) / RESULT_DIRNAME


def processed_panel_path() -> Path:
    return tcp.sample_processed_dir(COUNTRY_SAMPLE) / PANEL_FILENAME


def assert_no_excluded_product_ids(frame: pd.DataFrame, label: str) -> None:
    if "product_id" not in frame.columns:
        raise RuntimeError(f"{label} is missing product_id.")
    product_ids = frame["product_id"].astype("string")
    bad = product_ids[product_ids.str.contains(EXCLUDED_PRODUCT_RE, na=False)].drop_duplicates().head(10).tolist()
    if bad:
        raise RuntimeError(f"{label} contains excluded HS6 999999-derived product IDs: {bad}")


def fixed_universe_gini(values: np.ndarray | list[float] | pd.Series) -> float:
    """Finite-sample Gini over finite nonnegative values, including zeros."""
    arr = np.asarray(values, dtype=float).reshape(-1)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0 or np.any(arr < 0):
        return np.nan
    total = float(arr.sum())
    if total <= 0:
        return np.nan
    arr.sort()
    n = arr.size
    ranks = np.arange(1, n + 1, dtype=float)
    return float((2 * np.sum(ranks * arr) / (n * total)) - ((n + 1) / n))


def compute_fixed_universe_metrics(
    group: pd.DataFrame, product_position: dict[str, int], universe_count: int
) -> dict[str, float | int]:
    values = np.zeros(universe_count, dtype=float)
    missing_positions = sorted(set(group["product_id"].astype(str)) - set(product_position))
    if missing_positions:
        raise RuntimeError(f"Product values contain product IDs outside the fixed universe: {missing_positions[:10]}")
    positions = group["product_id"].astype(str).map(product_position).to_numpy(dtype=int)
    trade_values = pd.to_numeric(group["trade_value"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    if np.any(trade_values < 0):
        raise RuntimeError("Product trade values must be nonnegative.")
    values[positions] = trade_values
    total = float(values.sum())
    active_count = int((values > 0).sum())
    fixed_gini = fixed_universe_gini(values)
    active_product_gini = active_gini(values)
    return {
        "fixed_universe_product_gini": fixed_gini,
        "active_product_gini": active_product_gini,
        "gini_extensive_gap": fixed_gini - active_product_gini
        if np.isfinite(fixed_gini) and np.isfinite(active_product_gini)
        else np.nan,
        "active_product_count": active_count,
        "universe_product_count": universe_count,
        "zero_product_count": universe_count - active_count,
        "active_product_share": active_count / universe_count if universe_count else np.nan,
        "total_trade_value": total,
    }


def read_country_panel() -> pd.DataFrame:
    path = tcp.sample_processed_dir(COUNTRY_SAMPLE) / "comtrade_country_panel.csv"
    if not path.exists():
        raise RuntimeError(f"Missing rd2 country panel: {path}")
    panel = pd.read_csv(path)
    required = {"country", "iso3", "reporter_code"}
    missing = required - set(panel.columns)
    if missing:
        raise RuntimeError(f"Country panel is missing columns: {sorted(missing)}")
    panel = panel[list(required)].copy()
    panel["reporter_code"] = panel["reporter_code"].astype(int)
    if panel["reporter_code"].duplicated().any():
        raise RuntimeError("rd2 country panel has duplicate reporter_code values.")
    if len(panel) != 60:
        raise RuntimeError(f"rd2 country panel must contain 60 reporters; found {len(panel)}.")
    return panel


def read_income_metadata() -> pd.DataFrame:
    candidates = [
        tcp.sample_processed_dir(COUNTRY_SAMPLE) / "future_growth_concentration_world_bank_controls.csv",
        ROOT / "data/raw/world_bank_gdp/country_metadata.csv",
    ]
    for path in candidates:
        if not path.exists():
            continue
        data = pd.read_csv(path)
        if not {"iso3", "region", "income_group"}.issubset(data.columns):
            continue
        keep = data[["iso3", "region", "income_group"]].copy()
        keep["iso3"] = keep["iso3"].astype(str).str.upper().str.strip()
        keep["region"] = keep["region"].fillna("").astype(str)
        keep["income_group"] = keep["income_group"].fillna("").astype(str)
        return keep.sort_values(["iso3"]).drop_duplicates("iso3", keep="last")
    return pd.DataFrame(columns=["iso3", "region", "income_group"])


def read_product_frame(path: Path, columns: list[str], label: str) -> pd.DataFrame:
    if not path.exists():
        raise RuntimeError(f"Missing {label} artifact: {path}")
    frame = pd.read_parquet(path, columns=columns)
    missing = set(columns) - set(frame.columns)
    if missing:
        raise RuntimeError(f"{label} is missing columns: {sorted(missing)}")
    frame["year"] = frame["year"].astype(int)
    frame["product_id"] = frame["product_id"].astype(str)
    assert_no_excluded_product_ids(frame, label)
    return frame


def build_product_universe(world_product: pd.DataFrame, world_col: str, start_year: int, end_year: int) -> tuple[list[str], pd.DataFrame]:
    world = world_product[world_product["year"].between(start_year, end_year)].copy()
    world[world_col] = pd.to_numeric(world[world_col], errors="coerce").fillna(0.0)
    world = world[world[world_col] > 0].copy()
    if world.empty:
        raise RuntimeError("world_broad product support is empty after filtering.")
    product_universe = sorted(world["product_id"].drop_duplicates().tolist())
    year_counts = (
        world.groupby("year", as_index=False)
        .agg(world_active_products=("product_id", "nunique"), world_total_trade_value=(world_col, "sum"))
        .sort_values("year")
    )
    return product_universe, year_counts


def duplicate_key_count(frame: pd.DataFrame, keys: list[str]) -> int:
    return int(frame.duplicated(keys, keep=False).sum())


def compute_flow_panel(
    flow: str,
    country_panel: pd.DataFrame,
    income_metadata: pd.DataFrame,
    start_year: int,
    end_year: int,
) -> tuple[pd.DataFrame, dict[str, Any], pd.DataFrame]:
    paths = source_paths(flow)
    world_col = world_value_column(flow)
    country_product = read_product_frame(
        paths["country_product"], ["reporter_code", "year", "product_id", "trade_value"], f"{flow} rd2 product values"
    )
    world_product = read_product_frame(paths["world_product"], ["year", "product_id", world_col], f"{flow} world product values")

    country_product = country_product[country_product["year"].between(start_year, end_year)].copy()
    world_product = world_product[world_product["year"].between(start_year, end_year)].copy()
    country_product["reporter_code"] = country_product["reporter_code"].astype(int)
    country_product["trade_value"] = pd.to_numeric(country_product["trade_value"], errors="coerce").fillna(0.0)
    country_product = country_product[country_product["trade_value"] > 0].copy()

    duplicate_country_keys = duplicate_key_count(country_product, ["reporter_code", "year", "product_id"])
    duplicate_world_keys = duplicate_key_count(world_product, ["year", "product_id"])
    if duplicate_country_keys:
        raise RuntimeError(f"{flow} country product artifact has duplicate reporter-year-product rows.")
    if duplicate_world_keys:
        raise RuntimeError(f"{flow} world product artifact has duplicate year-product rows.")

    product_universe, year_counts = build_product_universe(world_product, world_col, start_year, end_year)
    product_position = {product_id: pos for pos, product_id in enumerate(product_universe)}
    universe_set = set(product_universe)
    outside = sorted(set(country_product["product_id"]) - universe_set)
    if outside:
        raise RuntimeError(f"{flow} country product artifact contains products outside the fixed world_broad universe: {outside[:10]}")

    meta = country_panel.merge(income_metadata, on="iso3", how="left")
    meta["region"] = meta["region"].fillna("").astype(str)
    meta["income_group"] = meta["income_group"].fillna("").astype(str)
    country_meta = meta.set_index("reporter_code")[["country", "iso3", "region", "income_group"]].to_dict("index")

    rows: list[dict[str, Any]] = []
    universe_count = len(product_universe)
    for (reporter_code, year), group in country_product.groupby(["reporter_code", "year"], sort=True):
        metrics = compute_fixed_universe_metrics(group, product_position, universe_count)
        meta_row = country_meta.get(int(reporter_code), {"country": str(reporter_code), "iso3": "", "region": "", "income_group": ""})
        rows.append(
            {
                "country": meta_row["country"],
                "iso3": meta_row["iso3"],
                "reporter_code": int(reporter_code),
                "year": int(year),
                "flow": flow,
                "variant": "fixed_universe",
                "product_id_mode": PRODUCT_ID_MODE,
                **metrics,
                "region": meta_row["region"],
                "income_group": meta_row["income_group"],
            }
        )

    panel = pd.DataFrame(rows)
    if panel.empty:
        raise RuntimeError(f"{flow} fixed-universe panel has no rows.")
    duplicate_panel_keys = duplicate_key_count(panel, ["reporter_code", "year", "flow"])
    if duplicate_panel_keys:
        raise RuntimeError(f"{flow} fixed-universe panel has duplicate reporter-year-flow keys.")
    if panel.loc[panel["total_trade_value"] > 0, "fixed_universe_product_gini"].isna().any():
        raise RuntimeError(f"{flow} fixed-universe Gini is missing for positive-total reporter-years.")

    diagnostics = {
        "flow": flow,
        "country_sample": COUNTRY_SAMPLE,
        "benchmark_sample": BENCHMARK_SAMPLE,
        "product_id_mode": PRODUCT_ID_MODE,
        "start_year": start_year,
        "end_year": end_year,
        "country_product_rows": int(len(country_product)),
        "country_reporter_year_rows": int(panel[["reporter_code", "year"]].drop_duplicates().shape[0]),
        "country_reporters": int(panel["reporter_code"].nunique()),
        "country_products": int(country_product["product_id"].nunique()),
        "world_product_rows": int(len(world_product)),
        "world_products_union": universe_count,
        "world_products_min_by_year": int(year_counts["world_active_products"].min()),
        "world_products_max_by_year": int(year_counts["world_active_products"].max()),
        "duplicate_country_product_keys": duplicate_country_keys,
        "duplicate_world_product_keys": duplicate_world_keys,
        "country_products_outside_universe": int(len(outside)),
        "excluded_999999_product_id_rows": 0,
        "status": "ok",
    }
    return panel.sort_values(["flow", "country", "year"]).reset_index(drop=True), diagnostics, year_counts.assign(flow=flow)


def add_balanced_flags(panel: pd.DataFrame, start_year: int, end_year: int, require_balanced_countries: int | None) -> tuple[pd.DataFrame, dict[str, Any]]:
    required_years = set(range(start_year, end_year + 1))
    out = panel.copy()
    out["balanced_panel_flag"] = False
    balance: dict[str, Any] = {
        "balanced_start_year": start_year,
        "balanced_end_year": end_year,
        "balanced_years": len(required_years),
        "flows": {},
    }
    for flow, flow_frame in out.groupby("flow", sort=True):
        in_window = flow_frame[flow_frame["year"].between(start_year, end_year)]
        country_years = in_window.groupby("reporter_code")["year"].apply(lambda years: set(years.astype(int)))
        balanced_codes = sorted(int(code) for code, years in country_years.items() if required_years.issubset(years))
        if require_balanced_countries is not None and len(balanced_codes) < require_balanced_countries:
            raise RuntimeError(
                f"{flow} balanced window has {len(balanced_codes)} reporters, below required {require_balanced_countries}."
            )
        mask = out["flow"].eq(flow) & out["reporter_code"].isin(balanced_codes) & out["year"].between(start_year, end_year)
        out.loc[mask, "balanced_panel_flag"] = True
        balance["flows"][flow] = {
            "balanced_countries": len(balanced_codes),
            "balanced_reporter_codes": balanced_codes,
            "balanced_rows": int(mask.sum()),
            "all_available_rows_before_balance": int(len(flow_frame)),
            "all_available_countries_before_balance": int(flow_frame["reporter_code"].nunique()),
        }
    return out, balance


def make_yearly_summary(panel: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for label, frame in [
        ("all_available", panel),
        ("balanced_2000_2024", panel[panel["balanced_panel_flag"]].copy()),
    ]:
        if frame.empty:
            continue
        summary = (
            frame.groupby(["flow", "year"], as_index=False)
            .agg(
                countries=("reporter_code", "nunique"),
                median_fixed_universe_product_gini=("fixed_universe_product_gini", "median"),
                mean_fixed_universe_product_gini=("fixed_universe_product_gini", "mean"),
                p10_fixed_universe_product_gini=("fixed_universe_product_gini", lambda x: float(np.nanpercentile(x, 10))),
                p90_fixed_universe_product_gini=("fixed_universe_product_gini", lambda x: float(np.nanpercentile(x, 90))),
                median_active_product_gini=("active_product_gini", "median"),
                median_gini_extensive_gap=("gini_extensive_gap", "median"),
                median_active_product_share=("active_product_share", "median"),
                median_active_product_count=("active_product_count", "median"),
                median_total_trade_value=("total_trade_value", "median"),
            )
            .sort_values(["flow", "year"])
        )
        summary.insert(0, "sample_window", label)
        frames.append(summary)
    return pd.concat(frames, ignore_index=True)


def make_latest_rankings(panel: pd.DataFrame) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for flow, flow_frame in panel.groupby("flow", sort=True):
        latest_year = int(flow_frame["year"].max())
        latest = flow_frame[flow_frame["year"].eq(latest_year)].copy()
        latest = latest.sort_values("fixed_universe_product_gini", ascending=False).reset_index(drop=True)
        latest.insert(0, "fixed_universe_rank_desc", np.arange(1, len(latest) + 1))
        rows.append(latest)
    return pd.concat(rows, ignore_index=True)


def make_rich_proxy_summary(panel: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (flow, year), group in panel.groupby(["flow", "year"], sort=True):
        rich = group[group["income_group"].eq("High income") & ~group["iso3"].isin(["JPN", "KOR", "TWN"])].copy()
        jk = group[group["iso3"].isin(["JPN", "KOR"])].copy()
        if rich.empty or jk.empty:
            continue
        rows.append(
            {
                "flow": flow,
                "year": int(year),
                "rich_proxy_countries_excluding_japan_korea": int(rich["iso3"].nunique()),
                "japan_korea_countries_present": int(jk["iso3"].nunique()),
                "rich_proxy_mean_fixed_universe_product_gini": float(rich["fixed_universe_product_gini"].mean()),
                "japan_korea_mean_fixed_universe_product_gini": float(jk["fixed_universe_product_gini"].mean()),
                "japan_korea_vs_rich_proxy_pct_gap": float(jk["fixed_universe_product_gini"].mean() / rich["fixed_universe_product_gini"].mean() - 1.0),
                "rich_proxy_mean_active_product_gini": float(rich["active_product_gini"].mean()),
                "japan_korea_mean_active_product_gini": float(jk["active_product_gini"].mean()),
                "rich_proxy_mean_active_product_share": float(rich["active_product_share"].mean()),
                "japan_korea_mean_active_product_share": float(jk["active_product_share"].mean()),
            }
        )
    return pd.DataFrame(rows)


def write_report(panel: pd.DataFrame, diagnostics: pd.DataFrame, balance: dict[str, Any], out_dir: Path) -> None:
    latest = make_latest_rankings(panel)
    exports_latest = latest[latest["flow"].eq("Exports")].head(5)
    imports_latest = latest[latest["flow"].eq("Imports")].head(5)
    universe_counts = diagnostics.set_index("flow")["world_products_union"].to_dict()
    lines = [
        "# Fixed-Universe Harmonized-HS6 Product Gini",
        "",
        f"Generated: {now_utc()}",
        "",
        "## Definition",
        "",
        "Unit: rd2 reporter-year-flow product basket over LT/HGL-weighted HS1992 product families.",
        "",
        "Product universe: for each flow, the fixed universe is the 2000-2024 union of positive `world_broad` harmonized product families. `world_broad` is used only to define the global product support, not as the reporting sample.",
        "",
        "`x_cfpt` is the harmonized product trade value for reporter `c`, flow `f`, year `t`, and product family `p`; missing products are set to zero.",
        "",
        "`G_fixed_cft = (2 * sum_i i * x_(i)) / (K_f * sum_i x_i) - (K_f + 1) / K_f`",
        "",
        "Higher values mean the country trades in fewer eligible products or puts most trade value into a few products. HS6 `999999` is excluded before harmonization and aggregation.",
        "",
        "## Universe Counts",
        "",
        f"- Export product universe: {int(universe_counts.get('Exports', 0)):,}",
        f"- Import product universe: {int(universe_counts.get('Imports', 0)):,}",
        "",
        "## Balanced Window",
        "",
        f"- Window: {balance.get('balanced_start_year')}-{balance.get('balanced_end_year')}",
        *[
            f"- {flow}: {details.get('balanced_countries')} balanced countries, {details.get('balanced_rows')} rows"
            for flow, details in balance.get("flows", {}).items()
        ],
        "",
        "## Latest Highest Values",
        "",
        "Exports:",
        "",
        *[
            f"- {row.country} ({row.iso3}): {row.fixed_universe_product_gini:.3f}"
            for row in exports_latest.itertuples(index=False)
        ],
        "",
        "Imports:",
        "",
        *[
            f"- {row.country} ({row.iso3}): {row.fixed_universe_product_gini:.3f}"
            for row in imports_latest.itertuples(index=False)
        ],
        "",
        "## Outputs",
        "",
        "- `fixed_universe_product_gini_all_years.csv`",
        "- `fixed_universe_product_gini_latest_rankings.csv`",
        "- `fixed_universe_product_gini_yearly_summary.csv`",
        "- `fixed_universe_product_gini_diagnostics.csv`",
        "- `fixed_universe_product_gini_manifest.json`",
    ]
    (out_dir / "fixed_universe_product_gini.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_outputs(panel: pd.DataFrame, diagnostics: pd.DataFrame, start_year: int, end_year: int) -> None:
    if set(panel["flow"].dropna().unique()) != set(FLOW_CHOICES):
        raise RuntimeError("Panel must contain both Exports and Imports.")
    if not panel["product_id_mode"].eq(PRODUCT_ID_MODE).all():
        raise RuntimeError("Panel contains a non-harmonized product_id_mode.")
    duplicate_keys = duplicate_key_count(panel, ["reporter_code", "year", "flow"])
    if duplicate_keys:
        raise RuntimeError("Panel has duplicate reporter-year-flow keys.")
    positive = panel["total_trade_value"] > 0
    if panel.loc[positive, "fixed_universe_product_gini"].isna().any():
        raise RuntimeError("Panel has missing fixed-universe Gini for positive-total rows.")
    if (panel["fixed_universe_product_gini"] < -1e-12).any() or (panel["fixed_universe_product_gini"] > 1 + 1e-12).any():
        raise RuntimeError("Fixed-universe Gini values must be inside [0, 1].")
    if (panel["active_product_share"] <= 0).any() or (panel["active_product_share"] > 1).any():
        raise RuntimeError("Active product shares must lie inside (0, 1].")
    for flow, flow_frame in panel.groupby("flow"):
        universe_counts = flow_frame.groupby("year")["universe_product_count"].nunique()
        if not universe_counts.eq(1).all():
            raise RuntimeError(f"{flow} universe count varies within year.")
        if flow_frame["universe_product_count"].nunique() != 1:
            raise RuntimeError(f"{flow} fixed universe count varies over {start_year}-{end_year}.")
    if not diagnostics["status"].eq("ok").all():
        raise RuntimeError("Diagnostics contain non-ok statuses.")


def write_outputs(
    panel: pd.DataFrame,
    diagnostics: pd.DataFrame,
    world_year_counts: pd.DataFrame,
    balance: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Path]:
    out_dir = result_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    processed_panel_path().parent.mkdir(parents=True, exist_ok=True)
    validate_outputs(panel, diagnostics, args.start_year, args.end_year)

    panel.to_parquet(processed_panel_path(), index=False)
    all_years = out_dir / "fixed_universe_product_gini_all_years.csv"
    latest = out_dir / "fixed_universe_product_gini_latest_rankings.csv"
    yearly = out_dir / "fixed_universe_product_gini_yearly_summary.csv"
    diagnostics_path = out_dir / "fixed_universe_product_gini_diagnostics.csv"
    manifest_path = out_dir / "fixed_universe_product_gini_manifest.json"
    rich_proxy = out_dir / "fixed_universe_product_gini_rich_proxy_summary.csv"
    world_counts = out_dir / "fixed_universe_product_gini_world_product_support_by_year.csv"

    panel.to_csv(all_years, index=False)
    make_latest_rankings(panel).to_csv(latest, index=False)
    make_yearly_summary(panel).to_csv(yearly, index=False)
    diagnostics.to_csv(diagnostics_path, index=False)
    make_rich_proxy_summary(panel).to_csv(rich_proxy, index=False)
    world_year_counts.to_csv(world_counts, index=False)

    source = {flow: {key: str(path.relative_to(ROOT)) for key, path in source_paths(flow).items()} for flow in FLOW_CHOICES}
    manifest = {
        "status": "complete",
        "generated_at_utc": now_utc(),
        "country_sample": COUNTRY_SAMPLE,
        "benchmark_sample": BENCHMARK_SAMPLE,
        "benchmark_role": "global product-universe source only; not the reporter sample",
        "product_id_mode": PRODUCT_ID_MODE,
        "harmonization": {
            "method": "LT/HGL weighted conversion to HS1992/H0 before product aggregation",
            "source_doi": tcp.LT_HGL_DATASET_DOI,
            "source_version": tcp.LT_HGL_DATASET_VERSION,
            "target": f"{tcp.LT_HGL_TARGET_LABEL}/{tcp.LT_HGL_TARGET_REVISION}",
        },
        "measure": {
            "name": "fixed_universe_product_gini",
            "unit": "reporter-year-flow over harmonized product families",
            "universe_definition": "2000-2024 union of positive world_broad product-family trade within flow",
            "zero_policy": "missing reporter-year-product values are filled with zero for valid reporter-years",
            "formula": "G = (2 * sum_i i * x_(i)) / (K * sum_i x_i) - (K + 1) / K",
        },
        "exclusions": {
            "hs6_999999": "excluded before harmonization and aggregation",
            "partner_code_0_world": "not applicable; product-only input artifacts already exclude partner World before product aggregation",
        },
        "years": {"start_year": args.start_year, "end_year": args.end_year},
        "balanced_window": balance,
        "diagnostics": diagnostics.to_dict(orient="records"),
        "source_files": source,
        "outputs": {
            "processed_panel": str(processed_panel_path().relative_to(ROOT)),
            "all_years": str(all_years.relative_to(ROOT)),
            "latest_rankings": str(latest.relative_to(ROOT)),
            "yearly_summary": str(yearly.relative_to(ROOT)),
            "diagnostics": str(diagnostics_path.relative_to(ROOT)),
            "rich_proxy_summary": str(rich_proxy.relative_to(ROOT)),
            "world_product_support_by_year": str(world_counts.relative_to(ROOT)),
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, default=json_default) + "\n", encoding="utf-8")
    write_report(panel, diagnostics, balance, out_dir)
    return {
        "processed_panel": processed_panel_path(),
        "all_years": all_years,
        "latest_rankings": latest,
        "yearly_summary": yearly,
        "diagnostics": diagnostics_path,
        "manifest": manifest_path,
        "rich_proxy_summary": rich_proxy,
        "world_product_support_by_year": world_counts,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country-sample", default=COUNTRY_SAMPLE, choices=tcp.COUNTRY_SAMPLE_CHOICES)
    parser.add_argument("--benchmark-sample", default=BENCHMARK_SAMPLE, choices=tcp.COUNTRY_SAMPLE_CHOICES)
    parser.add_argument("--product-id-mode", default=PRODUCT_ID_MODE, choices=[PRODUCT_ID_MODE])
    parser.add_argument("--flow", default="all", choices=["all", *FLOW_CHOICES])
    parser.add_argument("--start-year", type=int, default=DEFAULT_START_YEAR)
    parser.add_argument("--end-year", type=int, default=DEFAULT_END_YEAR)
    parser.add_argument("--balanced-start-year", type=int, default=DEFAULT_START_YEAR)
    parser.add_argument("--balanced-end-year", type=int, default=DEFAULT_END_YEAR)
    parser.add_argument("--require-balanced-countries", type=int, default=DEFAULT_REQUIRE_BALANCED_COUNTRIES)
    parser.add_argument(
        "--memory-budget-gb",
        type=float,
        default=float(os.getenv("FIXED_UNIVERSE_MEMORY_BUDGET_GB", "0") or 0),
        help="Optional soft memory budget; fail after major steps if resident memory exceeds this many GB.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.country_sample != COUNTRY_SAMPLE:
        raise RuntimeError("Website-facing fixed-universe outputs must use --country-sample rd2_countries.")
    if args.benchmark_sample != BENCHMARK_SAMPLE:
        raise RuntimeError("Fixed-universe product support must use --benchmark-sample world_broad.")
    if args.product_id_mode != PRODUCT_ID_MODE:
        raise RuntimeError("Fixed-universe website outputs must use harmonized_hs6_family.")
    if args.start_year != DEFAULT_START_YEAR or args.end_year != DEFAULT_END_YEAR:
        raise RuntimeError("Official fixed-universe outputs use the 2000-2024 harmonized product-universe window.")
    if args.balanced_start_year != args.start_year or args.balanced_end_year != args.end_year:
        raise RuntimeError("Balanced window must match the fixed-universe 2000-2024 window.")

    country_panel = read_country_panel()
    income_metadata = read_income_metadata()
    log_resource("loaded country metadata", args.memory_budget_gb)
    flows = list(FLOW_CHOICES) if args.flow == "all" else [args.flow]
    panels: list[pd.DataFrame] = []
    diagnostics: list[dict[str, Any]] = []
    world_counts: list[pd.DataFrame] = []
    for flow in flows:
        log_resource(f"starting {flow}", args.memory_budget_gb)
        flow_panel, flow_diagnostics, flow_world_counts = compute_flow_panel(
            flow, country_panel, income_metadata, args.start_year, args.end_year
        )
        panels.append(flow_panel)
        diagnostics.append(flow_diagnostics)
        world_counts.append(flow_world_counts)
        gc.collect()
        log_resource(f"finished {flow}", args.memory_budget_gb)

    panel = pd.concat(panels, ignore_index=True).sort_values(["flow", "country", "year"]).reset_index(drop=True)
    del panels
    gc.collect()
    log_resource("combined compact country-year panel", args.memory_budget_gb)
    panel, balance = add_balanced_flags(panel, args.balanced_start_year, args.balanced_end_year, args.require_balanced_countries)
    diagnostics_df = pd.DataFrame(diagnostics)
    world_counts_df = pd.concat(world_counts, ignore_index=True).sort_values(["flow", "year"])
    del diagnostics, world_counts
    gc.collect()
    log_resource("prepared summaries", args.memory_budget_gb)
    paths = write_outputs(panel, diagnostics_df, world_counts_df, balance, args)
    log_resource("wrote outputs", args.memory_budget_gb)
    print("Fixed-universe Product Gini outputs written:")
    for name, path in paths.items():
        print(f"- {name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
