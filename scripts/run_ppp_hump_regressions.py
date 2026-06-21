#!/usr/bin/env python3
"""PPP GDP per-capita hump regressions for rd2 and Cadot broad outcomes.

This runner deliberately writes PPP-specific outputs so the existing Cadot
tribunal artifacts remain untouched. The rd2 path remains balanced; the
Cadot broad path uses outcome-specific complete cases.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_country_size_effect as cse  # noqa: E402
from trade_concentration_pipeline import (  # noqa: E402
    CADOT_BROAD_END_YEAR,
    CADOT_BROAD_SAMPLE,
    CADOT_BROAD_START_YEAR,
    sample_processed_dir,
    sample_results_dir,
)


COUNTRY_SAMPLE = "rd2_countries"
START_YEAR = 2000
END_YEAR = 2024
PPP_INDICATOR = "NY.GDP.PCAP.PP.KD"
PPP_LABEL = "GDP per capita, PPP (constant 2021 international $)"
PPP_VALUE_COL = "gdp_pc_ppp_constant_2021_intl_usd"
PPP_LEVEL_COL = f"{PPP_VALUE_COL}_10k"
PPP_LEVEL_SQ_COL = f"{PPP_LEVEL_COL}_sq"
PPP_LOG_COL = f"log_{PPP_VALUE_COL}"
PPP_LOG_SQ_COL = f"{PPP_LOG_COL}_sq"
WORLD_BANK_ZIP_URL = f"https://api.worldbank.org/v2/en/indicator/{PPP_INDICATOR}?downloadformat=csv"
WORLD_BANK_API_URL = "https://api.worldbank.org/v2/country/{countries}/indicator/{indicator}"
WORLD_BANK_BATCH_SIZE = 20
EXPECTED_BALANCED_COUNTRIES = 55
SUPPORTED_COUNTRY_SAMPLES = (COUNTRY_SAMPLE, CADOT_BROAD_SAMPLE)
POPULATION_INDICATOR = "SP.POP.TOTL"
POPULATION_COL = "population"
RD2_MODEL_SAMPLE_LABEL = "rd2_balanced_2000_2024"
CADOT_MODEL_SAMPLE_LABEL = "cadot_broad_156_complete_case_2000_2024"


@dataclass(frozen=True)
class OutcomeSpec:
    slug: str
    flow: str
    dimension: str
    metric: str
    outcome: str
    title: str
    expected_shape: str = "concentration_u"


OUTCOME_SPECS = (
    OutcomeSpec(
        "export_world_relative_product_gini",
        "Exports",
        "product",
        "world_relative_product_gini",
        "world_relative_product_gini",
        "Export World-Relative Product Gini",
    ),
    OutcomeSpec(
        "export_product_gini",
        "Exports",
        "product",
        "product_gini",
        "product_gini",
        "Export Product Gini",
    ),
    OutcomeSpec(
        "import_product_gini",
        "Imports",
        "product",
        "product_gini",
        "product_gini",
        "Import Product Gini",
    ),
    OutcomeSpec(
        "export_partner_gini",
        "Exports",
        "partner",
        "partner_gini",
        "partner_gini",
        "Export Partner Gini",
    ),
    OutcomeSpec(
        "import_partner_gini",
        "Imports",
        "partner",
        "partner_gini",
        "partner_gini",
        "Import Partner Gini",
    ),
)

CADOT_BROAD_OUTCOME_SPECS = (
    OutcomeSpec(
        "export_product_gini",
        "Exports",
        "product",
        "product_gini",
        "product_gini",
        "Export Product Gini",
    ),
    OutcomeSpec(
        "export_product_theil",
        "Exports",
        "product",
        "product_theil",
        "product_theil",
        "Export Product Theil",
    ),
    OutcomeSpec(
        "export_product_hhi",
        "Exports",
        "product",
        "product_hhi",
        "product_hhi",
        "Export Product HHI",
    ),
    OutcomeSpec(
        "export_active_product_count",
        "Exports",
        "product",
        "active_product_count",
        "active_product_count",
        "Export Active HS6 Product Count",
        "active_inverted_u",
    ),
    OutcomeSpec(
        "import_product_gini",
        "Imports",
        "product",
        "product_gini",
        "product_gini",
        "Import Product Gini",
    ),
    OutcomeSpec(
        "import_product_theil",
        "Imports",
        "product",
        "product_theil",
        "product_theil",
        "Import Product Theil",
    ),
    OutcomeSpec(
        "import_product_hhi",
        "Imports",
        "product",
        "product_hhi",
        "product_hhi",
        "Import Product HHI",
    ),
    OutcomeSpec(
        "import_active_product_count",
        "Imports",
        "product",
        "active_product_count",
        "active_product_count",
        "Import Active HS6 Product Count",
        "active_inverted_u",
    ),
    OutcomeSpec(
        "export_partner_gini",
        "Exports",
        "partner",
        "partner_gini",
        "partner_gini",
        "Export Partner Gini",
    ),
    OutcomeSpec(
        "import_partner_gini",
        "Imports",
        "partner",
        "partner_gini",
        "partner_gini",
        "Import Partner Gini",
    ),
)


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def clean_scalar(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if math.isfinite(float(value)) else None
    if pd.isna(value):
        return None
    return value


def validate_unique(df: pd.DataFrame, keys: list[str], label: str) -> None:
    missing = sorted(set(keys) - set(df.columns))
    if missing:
        raise RuntimeError(f"{label} is missing required keys: {missing}")
    dupes = int(df.duplicated(keys).sum())
    if dupes:
        examples = df.loc[df.duplicated(keys, keep=False), keys].head(10).to_dict("records")
        raise RuntimeError(f"{label} has duplicate keys on {keys}: {examples}")


def read_country_panel(country_sample: str) -> pd.DataFrame:
    path = sample_processed_dir(country_sample) / "comtrade_country_panel.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing country panel: {path}")
    countries = pd.read_csv(path)
    required = {"country", "iso3", "reporter_code"}
    missing = sorted(required - set(countries.columns))
    if missing:
        raise RuntimeError(f"Country panel is missing columns: {missing}")
    countries = countries[list(required)].copy()
    countries["iso3"] = countries["iso3"].astype(str).str.upper()
    countries["reporter_code"] = pd.to_numeric(countries["reporter_code"], errors="coerce").astype("Int64")
    countries = countries.dropna(subset=["reporter_code"]).copy()
    countries["reporter_code"] = countries["reporter_code"].astype(int)
    return countries.drop_duplicates(["reporter_code", "iso3"])


def read_cached_ppp_controls(path: Path) -> pd.DataFrame:
    required = ["iso3", "year", PPP_VALUE_COL]
    if not path.exists():
        return pd.DataFrame(columns=required)
    controls = pd.read_csv(path)
    missing = [col for col in required if col not in controls.columns]
    if missing:
        return pd.DataFrame(columns=required)
    controls = controls[required].copy()
    controls["iso3"] = controls["iso3"].astype(str).str.upper()
    controls["year"] = pd.to_numeric(controls["year"], errors="coerce")
    controls[PPP_VALUE_COL] = pd.to_numeric(controls[PPP_VALUE_COL], errors="coerce")
    controls = controls.dropna(subset=["iso3", "year"]).copy()
    controls["year"] = controls["year"].astype(int)
    return controls.drop_duplicates(["iso3", "year"], keep="last")


def fetch_ppp_from_bulk_zip() -> pd.DataFrame:
    response = requests.get(WORLD_BANK_ZIP_URL, timeout=120)
    response.raise_for_status()
    if response.content[:2] != b"PK":
        raise RuntimeError("World Bank bulk indicator response was not a ZIP file.")
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    csv_name = next(
        (name for name in archive.namelist() if name.startswith("API_") and name.endswith(".csv")),
        None,
    )
    if csv_name is None:
        raise RuntimeError("World Bank bulk ZIP did not contain an API indicator CSV.")
    wide = pd.read_csv(archive.open(csv_name), skiprows=4)
    year_cols = [col for col in wide.columns if str(col).isdigit()]
    long = wide.melt(
        id_vars=["Country Code"],
        value_vars=year_cols,
        var_name="year",
        value_name=PPP_VALUE_COL,
    )
    long = long.rename(columns={"Country Code": "iso3"})
    long["iso3"] = long["iso3"].astype(str).str.upper()
    long["year"] = pd.to_numeric(long["year"], errors="coerce")
    long[PPP_VALUE_COL] = pd.to_numeric(long[PPP_VALUE_COL], errors="coerce")
    long = long.dropna(subset=["iso3", "year", PPP_VALUE_COL]).copy()
    long["year"] = long["year"].astype(int)
    return long[["iso3", "year", PPP_VALUE_COL]].drop_duplicates(["iso3", "year"], keep="last")


def fetch_indicator_from_country_api(
    iso3s: list[str],
    indicator: str,
    value_col: str,
    start_year: int,
    end_year: int,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for start in range(0, len(iso3s), WORLD_BANK_BATCH_SIZE):
        countries = ";".join(sorted(set(iso3s[start : start + WORLD_BANK_BATCH_SIZE])))
        page = 1
        pages = 1
        while page <= pages:
            url = WORLD_BANK_API_URL.format(countries=countries, indicator=indicator)
            response = requests.get(
                url,
                params={"format": "json", "per_page": 20000, "page": page, "date": f"{start_year}:{end_year}"},
                timeout=90,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list) or len(payload) < 2:
                break
            meta = payload[0] if isinstance(payload[0], dict) else {}
            pages = int(meta.get("pages") or pages)
            for item in payload[1]:
                iso3 = str(item.get("countryiso3code") or "").strip().upper()
                value = item.get("value")
                if iso3 and value is not None:
                    rows.append({"iso3": iso3, "year": int(item["date"]), value_col: value})
            page += 1
    out = pd.DataFrame(rows, columns=["iso3", "year", value_col])
    if out.empty:
        return out
    out[value_col] = pd.to_numeric(out[value_col], errors="coerce")
    return out.dropna(subset=[value_col]).drop_duplicates(["iso3", "year"], keep="last")


def fetch_ppp_from_country_api(iso3s: list[str], start_year: int, end_year: int) -> pd.DataFrame:
    return fetch_indicator_from_country_api(iso3s, PPP_INDICATOR, PPP_VALUE_COL, start_year, end_year)


def load_or_fetch_ppp_controls(country_sample: str, start_year: int, end_year: int, refresh: bool = False) -> pd.DataFrame:
    countries = read_country_panel(country_sample)
    iso3s = sorted(countries["iso3"].dropna().astype(str).str.upper().unique())
    expected = pd.DataFrame(
        [(iso3, year) for iso3 in iso3s for year in range(start_year, end_year + 1)],
        columns=["iso3", "year"],
    )
    cache_path = sample_processed_dir(country_sample) / "ppp_hump_world_bank_controls.csv"
    cached = read_cached_ppp_controls(cache_path)
    controls = expected.merge(cached, on=["iso3", "year"], how="left")
    complete = float(controls[PPP_VALUE_COL].notna().mean()) if len(controls) else 0.0

    if refresh or complete < 1.0:
        frames = []
        errors: list[str] = []
        try:
            frames.append(fetch_ppp_from_bulk_zip())
        except Exception as exc:  # pragma: no cover - network dependent
            errors.append(f"bulk_zip:{exc}")
        try:
            frames.append(fetch_ppp_from_country_api(iso3s, start_year, end_year))
        except Exception as exc:  # pragma: no cover - network dependent
            errors.append(f"country_api:{exc}")
        if cached[PPP_VALUE_COL].notna().any():
            frames.append(cached)
        if not frames:
            raise RuntimeError(f"Could not fetch or read PPP controls. Errors: {errors}")
        combined = pd.concat(frames, ignore_index=True)
        combined["iso3"] = combined["iso3"].astype(str).str.upper()
        combined["year"] = pd.to_numeric(combined["year"], errors="coerce")
        combined[PPP_VALUE_COL] = pd.to_numeric(combined[PPP_VALUE_COL], errors="coerce")
        combined = combined.dropna(subset=["iso3", "year", PPP_VALUE_COL]).copy()
        combined["year"] = combined["year"].astype(int)
        controls = expected.merge(combined.drop_duplicates(["iso3", "year"], keep="last"), on=["iso3", "year"], how="left")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        controls.to_csv(cache_path, index=False)

    controls[PPP_VALUE_COL] = pd.to_numeric(controls[PPP_VALUE_COL], errors="coerce")
    validate_unique(controls, ["iso3", "year"], "PPP controls")
    return controls


def read_cached_population_controls(path: Path) -> pd.DataFrame:
    required = ["iso3", "year", POPULATION_COL]
    if not path.exists():
        return pd.DataFrame(columns=required)
    controls = pd.read_csv(path)
    missing = [col for col in required if col not in controls.columns]
    if missing:
        return pd.DataFrame(columns=required)
    controls = controls[required].copy()
    controls["iso3"] = controls["iso3"].astype(str).str.upper()
    controls["year"] = pd.to_numeric(controls["year"], errors="coerce")
    controls[POPULATION_COL] = pd.to_numeric(controls[POPULATION_COL], errors="coerce")
    controls = controls.dropna(subset=["iso3", "year"]).copy()
    controls["year"] = controls["year"].astype(int)
    return controls.drop_duplicates(["iso3", "year"], keep="last")


def load_or_fetch_population_controls(country_sample: str, start_year: int, end_year: int, refresh: bool = False) -> pd.DataFrame:
    countries = read_country_panel(country_sample)
    iso3s = sorted(countries["iso3"].dropna().astype(str).str.upper().unique())
    expected = pd.DataFrame(
        [(iso3, year) for iso3 in iso3s for year in range(start_year, end_year + 1)],
        columns=["iso3", "year"],
    )
    cache_path = sample_processed_dir(country_sample) / "ppp_hump_population_controls.csv"
    cached = read_cached_population_controls(cache_path)
    controls = expected.merge(cached, on=["iso3", "year"], how="left")
    complete = float(controls[POPULATION_COL].notna().mean()) if len(controls) else 0.0

    if refresh or complete < 1.0:
        frames = []
        errors: list[str] = []
        try:
            frames.append(fetch_indicator_from_country_api(iso3s, POPULATION_INDICATOR, POPULATION_COL, start_year, end_year))
        except Exception as exc:  # pragma: no cover - network dependent
            errors.append(f"country_api:{exc}")
        if cached[POPULATION_COL].notna().any():
            frames.append(cached)
        if not frames:
            raise RuntimeError(f"Could not fetch or read population controls. Errors: {errors}")
        combined = pd.concat(frames, ignore_index=True)
        combined["iso3"] = combined["iso3"].astype(str).str.upper()
        combined["year"] = pd.to_numeric(combined["year"], errors="coerce")
        combined[POPULATION_COL] = pd.to_numeric(combined[POPULATION_COL], errors="coerce")
        combined = combined.dropna(subset=["iso3", "year", POPULATION_COL]).copy()
        combined["year"] = combined["year"].astype(int)
        controls = expected.merge(combined.drop_duplicates(["iso3", "year"], keep="last"), on=["iso3", "year"], how="left")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        controls.to_csv(cache_path, index=False)

    controls[POPULATION_COL] = pd.to_numeric(controls[POPULATION_COL], errors="coerce")
    controls["log_population"] = np.where(controls[POPULATION_COL] > 0, np.log(controls[POPULATION_COL]), np.nan)
    validate_unique(controls, ["iso3", "year"], "population controls")
    return controls


def load_standard_concentration(country_sample: str, start_year: int, end_year: int) -> pd.DataFrame:
    path = sample_processed_dir(country_sample) / "concentration_all_years.parquet"
    if not path.exists() and country_sample == CADOT_BROAD_SAMPLE:
        return load_cadot_broad_three_metric_concentration(start_year, end_year)
    if not path.exists():
        raise FileNotFoundError(f"Missing concentration panel: {path}")
    panel = pd.read_parquet(path)
    panel = panel[panel["variant"].eq("baseline") & panel["year"].between(start_year, end_year)].copy()
    validate_unique(panel, ["reporter_code", "year", "flow", "variant"], "standard concentration panel")
    return panel


def load_cadot_broad_three_metric_concentration(start_year: int, end_year: int) -> pd.DataFrame:
    path = sample_results_dir(CADOT_BROAD_SAMPLE) / "three_metric_tables" / "concentration_metric_all_years.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"Missing Cadot broad three-metric concentration panel: {path}. "
            "Run `python3 scripts/run_cadot_three_metric_pipeline.py` first."
        )
    panel = pd.read_parquet(path)
    required = {"country", "iso3", "reporter_code", "year", "flow", "dimension", "variant", "gini", "theil", "hhi", "active_count"}
    missing = sorted(required - set(panel.columns))
    if missing:
        raise RuntimeError(f"Cadot broad three-metric panel is missing columns: {missing}")
    panel = panel[panel["variant"].eq("baseline") & panel["year"].between(start_year, end_year)].copy()
    panel["iso3"] = panel["iso3"].astype(str).str.upper()
    panel["reporter_code"] = pd.to_numeric(panel["reporter_code"], errors="coerce").astype("Int64")
    panel["year"] = pd.to_numeric(panel["year"], errors="coerce").astype("Int64")
    panel = panel.dropna(subset=["reporter_code", "year", "iso3"]).copy()
    panel["reporter_code"] = panel["reporter_code"].astype(int)
    panel["year"] = panel["year"].astype(int)

    product = panel[panel["dimension"].eq("product")][
        ["country", "iso3", "reporter_code", "year", "flow", "variant", "gini", "theil", "hhi", "active_count"]
    ].rename(
        columns={
            "gini": "product_gini",
            "theil": "product_theil",
            "hhi": "product_hhi",
            "active_count": "active_product_count",
        }
    )
    partner = panel[panel["dimension"].eq("partner")][
        ["reporter_code", "year", "flow", "variant", "gini", "theil", "hhi", "active_count"]
    ].rename(
        columns={
            "gini": "partner_gini",
            "theil": "partner_theil",
            "hhi": "partner_hhi",
            "active_count": "active_partner_count",
        }
    )
    validate_unique(product, ["reporter_code", "year", "flow", "variant"], "Cadot broad product concentration panel")
    validate_unique(partner, ["reporter_code", "year", "flow", "variant"], "Cadot broad partner concentration panel")
    out = product.merge(partner, on=["reporter_code", "year", "flow", "variant"], how="left", validate="one_to_one")
    validate_unique(out, ["reporter_code", "year", "flow", "variant"], "Cadot broad wide concentration panel")
    return out


def load_world_relative(country_sample: str, start_year: int, end_year: int) -> pd.DataFrame:
    path = sample_results_dir(country_sample) / "world_relative_product_gini_tables" / "world_relative_product_gini_all_years.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing world-relative panel: {path}")
    panel = pd.read_csv(path)
    panel = panel[panel["flow"].eq("Exports") & panel["metric_valid"].astype(bool) & panel["year"].between(start_year, end_year)].copy()
    panel["reporter_code"] = pd.to_numeric(panel["reporter_code"], errors="coerce").astype("Int64")
    panel["year"] = pd.to_numeric(panel["year"], errors="coerce").astype("Int64")
    panel = panel.dropna(subset=["reporter_code", "year"]).copy()
    panel["reporter_code"] = panel["reporter_code"].astype(int)
    panel["year"] = panel["year"].astype(int)
    validate_unique(panel, ["reporter_code", "year"], "world-relative panel")
    return panel[["reporter_code", "year", "world_relative_product_gini"]].copy()


def load_export_oil_controls(country_sample: str, start_year: int, end_year: int) -> pd.DataFrame:
    path = sample_processed_dir(country_sample) / "exercise_02_export_concentration_panel.parquet"
    if not path.exists() and country_sample == CADOT_BROAD_SAMPLE:
        return load_cadot_broad_oil_controls(start_year, end_year)
    if not path.exists():
        raise FileNotFoundError(
            f"Missing HS27 oil-share controls panel: {path}. Run Exercise 2 for {country_sample} before broad PPP regressions."
        )
    panel = pd.read_parquet(path)
    needed = {"country", "iso3", "reporter_code", "year", "flow", "oil_export_share"}
    missing = sorted(needed - set(panel.columns))
    if missing:
        raise RuntimeError(f"Exercise 2 export panel is missing required oil-share columns: {missing}")
    controls = panel[panel["flow"].eq("Exports") & panel["year"].between(start_year, end_year)][
        ["country", "iso3", "reporter_code", "year", "oil_export_share"]
    ].copy()
    controls["iso3"] = controls["iso3"].astype(str).str.upper()
    controls["reporter_code"] = pd.to_numeric(controls["reporter_code"], errors="coerce").astype("Int64")
    controls["year"] = pd.to_numeric(controls["year"], errors="coerce").astype("Int64")
    controls["oil_export_share"] = pd.to_numeric(controls["oil_export_share"], errors="coerce")
    controls = controls.dropna(subset=["reporter_code", "year", "iso3"]).copy()
    controls["reporter_code"] = controls["reporter_code"].astype(int)
    controls["year"] = controls["year"].astype(int)
    controls = controls.drop_duplicates(["reporter_code", "year"], keep="last")
    validate_unique(controls, ["reporter_code", "year"], "HS27 oil-share controls")
    return controls


def load_cadot_broad_oil_controls(start_year: int, end_year: int) -> pd.DataFrame:
    path = sample_results_dir(CADOT_BROAD_SAMPLE) / "three_metric_tables" / "exercise_06_exclusion_metrics.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"Missing Cadot broad HS27 oil-share proxy: {path}. "
            "Run `python3 scripts/run_cadot_three_metric_pipeline.py` first."
        )
    panel = pd.read_parquet(path)
    needed = {"country", "iso3", "reporter_code", "year", "flow", "dimension", "variant", "trade_share_removed"}
    missing = sorted(needed - set(panel.columns))
    if missing:
        raise RuntimeError(f"Cadot broad Exercise 6 exclusion metrics are missing oil-control columns: {missing}")
    controls = panel[
        panel["flow"].eq("Exports")
        & panel["dimension"].eq("product")
        & panel["variant"].eq("oil_only")
        & panel["year"].between(start_year, end_year)
    ][["country", "iso3", "reporter_code", "year", "trade_share_removed"]].copy()
    controls = controls.rename(columns={"trade_share_removed": "oil_export_share"})
    controls["iso3"] = controls["iso3"].astype(str).str.upper()
    controls["reporter_code"] = pd.to_numeric(controls["reporter_code"], errors="coerce").astype("Int64")
    controls["year"] = pd.to_numeric(controls["year"], errors="coerce").astype("Int64")
    controls["oil_export_share"] = pd.to_numeric(controls["oil_export_share"], errors="coerce")
    controls = controls.dropna(subset=["reporter_code", "year", "iso3"]).copy()
    controls["reporter_code"] = controls["reporter_code"].astype(int)
    controls["year"] = controls["year"].astype(int)
    validate_unique(controls, ["reporter_code", "year"], "Cadot broad HS27 oil-share controls")
    return controls


def load_future_growth_controls(country_sample: str, start_year: int, end_year: int) -> pd.DataFrame:
    growth_path = sample_processed_dir(country_sample) / "future_growth_concentration_panel.parquet"
    if not growth_path.exists():
        raise FileNotFoundError(f"Missing future-growth controls panel: {growth_path}")
    panel = pd.read_parquet(growth_path)
    controls = panel[panel["flow"].eq("Exports") & panel["variant"].eq("baseline")][
        ["country", "iso3", "reporter_code", "year", "log_population", "oil_export_share"]
    ].drop_duplicates(["reporter_code", "year"]).copy()
    controls["iso3"] = controls["iso3"].astype(str).str.upper()
    controls["reporter_code"] = pd.to_numeric(controls["reporter_code"], errors="coerce").astype("Int64")
    controls["year"] = pd.to_numeric(controls["year"], errors="coerce").astype("Int64")
    controls = controls.dropna(subset=["reporter_code", "year", "iso3"]).copy()
    controls["reporter_code"] = controls["reporter_code"].astype(int)
    controls["year"] = controls["year"].astype(int)
    return controls[controls["year"].between(start_year, end_year)].copy()


def load_controls_with_ppp(
    country_sample: str,
    start_year: int,
    end_year: int,
    refresh_ppp: bool,
    prefer_future_growth_controls: bool = True,
) -> pd.DataFrame:
    if prefer_future_growth_controls:
        controls = load_future_growth_controls(country_sample, start_year, end_year)
        controls_source = "future_growth_concentration_panel"
    else:
        oil = load_export_oil_controls(country_sample, start_year, end_year)
        population = load_or_fetch_population_controls(country_sample, start_year, end_year, refresh=refresh_ppp)
        controls = oil.merge(population[["iso3", "year", POPULATION_COL, "log_population"]], on=["iso3", "year"], how="left", validate="many_to_one")
        controls_source = "exercise_02_oil_share_plus_world_bank_population"
    ppp = load_or_fetch_ppp_controls(country_sample, start_year, end_year, refresh=refresh_ppp)
    controls = controls.merge(ppp, on=["iso3", "year"], how="left", validate="many_to_one")
    controls[PPP_LEVEL_COL] = controls[PPP_VALUE_COL] / 10_000.0
    controls[PPP_LEVEL_SQ_COL] = controls[PPP_LEVEL_COL] ** 2
    controls[PPP_LOG_COL] = np.where(controls[PPP_VALUE_COL] > 0, np.log(controls[PPP_VALUE_COL]), np.nan)
    controls[PPP_LOG_SQ_COL] = controls[PPP_LOG_COL] ** 2
    controls["controls_source"] = controls_source
    validate_unique(controls, ["reporter_code", "year"], "controls with PPP")
    return controls


def outcome_specs_for_sample(country_sample: str) -> tuple[OutcomeSpec, ...]:
    if country_sample == COUNTRY_SAMPLE:
        return OUTCOME_SPECS
    if country_sample == CADOT_BROAD_SAMPLE:
        return CADOT_BROAD_OUTCOME_SPECS
    world_path = sample_results_dir(country_sample) / "world_relative_product_gini_tables" / "world_relative_product_gini_all_years.csv"
    if world_path.exists():
        return OUTCOME_SPECS
    return tuple(spec for spec in OUTCOME_SPECS if spec.outcome != "world_relative_product_gini")


def build_outcome_panels(
    country_sample: str,
    start_year: int,
    end_year: int,
    refresh_ppp: bool,
    balance_policy: str = "rd2_balanced",
    outcome_specs: Iterable[OutcomeSpec] | None = None,
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, list[int], pd.DataFrame, tuple[OutcomeSpec, ...]]:
    selected_specs = tuple(outcome_specs or outcome_specs_for_sample(country_sample))
    country_panel = read_country_panel(country_sample)
    selected_reporters = int(country_panel["reporter_code"].nunique())
    selected_iso3 = int(country_panel["iso3"].nunique())
    selected_country_years = selected_reporters * (end_year - start_year + 1)
    concentration = load_standard_concentration(country_sample, start_year, end_year)
    needs_world_relative = any(spec.outcome == "world_relative_product_gini" for spec in selected_specs)
    world = load_world_relative(country_sample, start_year, end_year) if needs_world_relative else pd.DataFrame()
    controls = load_controls_with_ppp(
        country_sample,
        start_year,
        end_year,
        refresh_ppp,
        prefer_future_growth_controls=(country_sample == COUNTRY_SAMPLE),
    )

    panels: dict[str, pd.DataFrame] = {}
    complete_codes: set[int] | None = None
    attrition_rows: list[dict[str, Any]] = []
    required_years = set(range(start_year, end_year + 1))
    for spec in selected_specs:
        if spec.outcome == "world_relative_product_gini":
            base = concentration[concentration["flow"].eq("Exports")][
                ["country", "iso3", "reporter_code", "year", "flow"]
            ].merge(world, on=["reporter_code", "year"], how="inner", validate="one_to_one")
        else:
            base = concentration[concentration["flow"].eq(spec.flow)][
                ["country", "iso3", "reporter_code", "year", "flow", spec.outcome]
            ].copy()
        panel = base.merge(
            controls.drop(columns=[col for col in ["country", "iso3"] if col in controls.columns]),
            on=["reporter_code", "year"],
            how="left",
            validate="many_to_one",
        )
        required = [spec.outcome, PPP_VALUE_COL, PPP_LEVEL_COL, PPP_LEVEL_SQ_COL, PPP_LOG_COL, PPP_LOG_SQ_COL, "log_population", "oil_export_share"]
        analytic = panel.replace([np.inf, -np.inf], np.nan).dropna(subset=required).copy()
        if balance_policy == "rd2_balanced":
            years = analytic.groupby("reporter_code")["year"].apply(lambda x: set(x.astype(int)))
            codes = {int(code) for code, years_seen in years.items() if required_years.issubset(years_seen)}
            complete_codes = codes if complete_codes is None else complete_codes.intersection(codes)
        panels[spec.slug] = analytic
        attrition_rows.append(
            {
                "outcome_slug": spec.slug,
                "outcome": spec.outcome,
                "balance_policy": balance_policy,
                "selected_reporters": selected_reporters,
                "selected_iso3": selected_iso3,
                "selected_country_years": selected_country_years,
                "source_rows": int(len(base)),
                "source_countries": int(base["reporter_code"].nunique()) if "reporter_code" in base.columns else 0,
                "after_controls_merge_rows": int(len(panel)),
                "analytic_rows_before_balance": int(len(analytic)),
                "analytic_countries_before_balance": int(analytic["reporter_code"].nunique()) if "reporter_code" in analytic.columns else 0,
                "analytic_clusters_before_balance": int(analytic["reporter_code"].nunique()) if "reporter_code" in analytic.columns else 0,
                "cluster_col": "reporter_code",
                "missing_outcome_rows": int(panel[spec.outcome].isna().sum()) if spec.outcome in panel.columns else int(len(panel)),
                "missing_ppp_rows": int(panel[PPP_VALUE_COL].isna().sum()) if PPP_VALUE_COL in panel.columns else int(len(panel)),
                "missing_population_rows": int(panel["log_population"].isna().sum()) if "log_population" in panel.columns else int(len(panel)),
                "missing_oil_share_rows": int(panel["oil_export_share"].isna().sum()) if "oil_export_share" in panel.columns else int(len(panel)),
            }
        )

    attrition = pd.DataFrame(attrition_rows)
    if balance_policy == "rd2_balanced":
        common_codes = sorted(complete_codes or [])
        if len(common_codes) != EXPECTED_BALANCED_COUNTRIES:
            missing_summary = {
                spec.slug: sorted(set(panels[spec.slug]["reporter_code"].unique()) - set(common_codes))[:20]
                for spec in selected_specs
            }
            raise RuntimeError(
                "PPP balanced sample does not match the expected 55 countries. "
                f"Found {len(common_codes)} common complete countries. Missing/extra diagnostic: {missing_summary}"
            )

        out: dict[str, pd.DataFrame] = {}
        expected_rows = len(common_codes) * len(required_years)
        for spec in selected_specs:
            panel = panels[spec.slug][panels[spec.slug]["reporter_code"].isin(common_codes)].copy()
            panel = panel.sort_values(["country", "year"]).reset_index(drop=True)
            validate_unique(panel, ["reporter_code", "year"], f"{spec.slug} analytic panel")
            if len(panel) != expected_rows:
                raise RuntimeError(f"{spec.slug} expected {expected_rows} rows after common balance, found {len(panel)}")
            out[spec.slug] = panel
            attrition.loc[attrition["outcome_slug"].eq(spec.slug), "analytic_rows_after_balance"] = int(len(panel))
            attrition.loc[attrition["outcome_slug"].eq(spec.slug), "analytic_countries_after_balance"] = int(panel["reporter_code"].nunique())
            attrition.loc[attrition["outcome_slug"].eq(spec.slug), "analytic_clusters_after_balance"] = int(panel["reporter_code"].nunique())
            attrition.loc[attrition["outcome_slug"].eq(spec.slug), "clusters"] = int(panel["reporter_code"].nunique())
        return out, controls, common_codes, attrition, selected_specs

    if balance_policy != "complete_case":
        raise ValueError(f"Unsupported balance policy: {balance_policy}")

    out = {}
    for spec in selected_specs:
        panel = panels[spec.slug].sort_values(["country", "year"]).reset_index(drop=True)
        validate_unique(panel, ["reporter_code", "year"], f"{spec.slug} analytic panel")
        out[spec.slug] = panel
        attrition.loc[attrition["outcome_slug"].eq(spec.slug), "analytic_rows_after_balance"] = int(len(panel))
        attrition.loc[attrition["outcome_slug"].eq(spec.slug), "analytic_countries_after_balance"] = int(panel["reporter_code"].nunique())
        attrition.loc[attrition["outcome_slug"].eq(spec.slug), "analytic_clusters_after_balance"] = int(panel["reporter_code"].nunique())
        attrition.loc[attrition["outcome_slug"].eq(spec.slug), "clusters"] = int(panel["reporter_code"].nunique())
    common_codes = sorted(set.intersection(*(set(panel["reporter_code"].unique()) for panel in out.values()))) if out else []
    return out, controls, common_codes, attrition, selected_specs


def add_turning_points(models: pd.DataFrame, income_form: str, linear_term: str, square_term: str) -> pd.DataFrame:
    out = models.copy()
    out["income_form"] = income_form
    out["turning_point_ppp_constant_2021_intl_usd"] = np.nan
    out["turning_point_income_variable"] = np.nan
    for keys, group in out.groupby(["model_label", "sample", "flow", "dimension", "metric", "outcome"], dropna=False):
        b1 = group.loc[group["term"].eq(linear_term), "coefficient"]
        b2 = group.loc[group["term"].eq(square_term), "coefficient"]
        if b1.empty or b2.empty:
            continue
        beta1 = float(b1.iloc[0])
        beta2 = float(b2.iloc[0])
        if not (math.isfinite(beta1) and math.isfinite(beta2)) or abs(beta2) <= 1e-12:
            continue
        tp_var = -beta1 / (2 * beta2)
        tp_usd = tp_var * 10_000.0 if income_form == "level_ppp" else math.exp(tp_var) if -50 < tp_var < 50 else np.nan
        mask = np.ones(len(out), dtype=bool)
        for col, value in zip(["model_label", "sample", "flow", "dimension", "metric", "outcome"], keys):
            mask &= out[col].eq(value).to_numpy()
        out.loc[mask, "turning_point_income_variable"] = tp_var
        out.loc[mask, "turning_point_ppp_constant_2021_intl_usd"] = tp_usd
    return out


def verdict(
    square_coef: float,
    square_p: float,
    tp: float,
    p05: float,
    p95: float,
    min_income: float,
    max_income: float,
    expected_shape: str = "concentration_u",
) -> str:
    if not math.isfinite(square_coef) or not math.isfinite(square_p):
        return "not estimated"
    if expected_shape == "active_inverted_u":
        if square_coef >= 0:
            return "no active-line inverted U"
        if not math.isfinite(tp) or tp < min_income or tp > max_income:
            return "outside-support active-line peak"
        if square_p < 0.01 and p05 <= tp <= p95:
            return "clear active-line hump"
        if square_p < 0.05 and p05 <= tp <= p95:
            return "weak/borderline active-line hump"
        if square_p < 0.05:
            return "statistical active-line bend, edge peak"
        return "no clean active-line hump"
    if square_coef <= 0:
        return "no concentration U-shape"
    if not math.isfinite(tp) or tp < min_income or tp > max_income:
        return "outside-support artifact"
    if square_p < 0.01 and p05 <= tp <= p95:
        return "clear hump"
    if square_p < 0.05 and p05 <= tp <= p95:
        return "weak/borderline hump"
    if square_p < 0.05:
        return "statistical bend, edge turning point"
    return "no clean hump"


def run_models(
    panels: dict[str, pd.DataFrame],
    outcome_specs: Iterable[OutcomeSpec] = OUTCOME_SPECS,
    model_sample_label: str = RD2_MODEL_SAMPLE_LABEL,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    frames: list[pd.DataFrame] = []
    summary_rows: list[dict[str, Any]] = []
    forms = [
        ("level_ppp", PPP_LEVEL_COL, PPP_LEVEL_SQ_COL, "PPP GDPpc level"),
        ("log_ppp", PPP_LOG_COL, PPP_LOG_SQ_COL, "log PPP GDPpc"),
    ]
    for spec in outcome_specs:
        panel = panels[spec.slug]
        support = panel[PPP_VALUE_COL].astype(float)
        p05 = float(support.quantile(0.05))
        p95 = float(support.quantile(0.95))
        min_income = float(support.min())
        max_income = float(support.max())
        for form, linear_term, square_term, label in forms:
            model_inputs: list[tuple[str, str, pd.DataFrame, list[str], str]] = [
                (
                    "pooled_year_fe",
                    f"{form}_controls_year_fe_country_cluster",
                    panel,
                    ["year"],
                    "reporter_code",
                ),
                (
                    "country_year_fe",
                    f"{form}_controls_country_year_fe_country_cluster",
                    panel,
                    ["reporter_code", "year"],
                    "reporter_code",
                ),
                (
                    "between_country",
                    f"{form}_controls_between_country",
                    build_between_panel(panel, spec.outcome),
                    [],
                    "",
                ),
            ]
            for estimator, model_label, model_panel, fixed_effects, cluster_col in model_inputs:
                result = cse.run_ols_model(
                    model_panel,
                    spec.outcome,
                    [linear_term, square_term, "log_population", "oil_export_share"],
                    fixed_effects,
                    model_label,
                    model_sample_label,
                    spec.flow,
                    spec.dimension,
                    spec.metric,
                    cluster_col=cluster_col,
                )
                model = add_turning_points(cse.model_results_to_frame([result]), form, linear_term, square_term)
                model["estimator"] = estimator
                frames.append(model)
                linear_rows = model[model["term"].eq(linear_term)]
                square_rows = model[model["term"].eq(square_term)]
                if linear_rows.empty or square_rows.empty:
                    continue
                linear = linear_rows.iloc[0]
                square = square_rows.iloc[0]
                tp = float(linear["turning_point_ppp_constant_2021_intl_usd"])
                summary_rows.append(
                    {
                        "outcome_slug": spec.slug,
                        "flow": spec.flow,
                        "outcome_label": spec.title,
                        "estimator": estimator,
                        "model_label": model_label,
                        "income_form": form,
                        "income_label": label,
                        "linear_term": linear_term,
                        "linear_coefficient": float(linear["coefficient"]),
                        "linear_std_error": float(linear["std_error"]),
                        "linear_p_value": float(linear["p_value"]),
                        "quadratic_term": square_term,
                        "quadratic_coefficient": float(square["coefficient"]),
                        "quadratic_std_error": float(square["std_error"]),
                        "quadratic_p_value": float(square["p_value"]),
                        "turning_point_ppp_constant_2021_intl_usd": tp,
                        "turning_point_inside_minmax": bool(math.isfinite(tp) and min_income <= tp <= max_income),
                        "turning_point_inside_p05_p95": bool(math.isfinite(tp) and p05 <= tp <= p95),
                        "income_min": min_income,
                        "income_p05": p05,
                        "income_p95": p95,
                        "income_max": max_income,
                        "nobs": int(linear["nobs"]),
                        "clusters": int(linear["clusters"]),
                        "r_squared": float(linear["r_squared"]),
                        "expected_shape": spec.expected_shape,
                        "verdict": verdict(
                            float(square["coefficient"]),
                            float(square["p_value"]),
                            tp,
                            p05,
                            p95,
                            min_income,
                            max_income,
                            spec.expected_shape,
                        ),
                    }
                )
    return pd.concat(frames, ignore_index=True), pd.DataFrame(summary_rows)


def build_between_panel(panel: pd.DataFrame, outcome: str) -> pd.DataFrame:
    numeric_cols = [
        outcome,
        PPP_VALUE_COL,
        PPP_LEVEL_COL,
        PPP_LEVEL_SQ_COL,
        PPP_LOG_COL,
        PPP_LOG_SQ_COL,
        "log_population",
        "oil_export_share",
    ]
    id_cols = ["country", "iso3", "reporter_code"]
    work = panel[id_cols + numeric_cols].copy()
    for col in numeric_cols:
        work[col] = pd.to_numeric(work[col], errors="coerce")
    return (
        work.groupby(id_cols, as_index=False)[numeric_cols]
        .mean()
        .replace([np.inf, -np.inf], np.nan)
        .dropna(subset=numeric_cols)
    )


def fit_line(panel: pd.DataFrame, spec: OutcomeSpec, income_form: str) -> tuple[np.ndarray, np.ndarray]:
    linear_term = PPP_LEVEL_COL if income_form == "level_ppp" else PPP_LOG_COL
    square_term = PPP_LEVEL_SQ_COL if income_form == "level_ppp" else PPP_LOG_SQ_COL
    work = panel.replace([np.inf, -np.inf], np.nan).dropna(
        subset=[spec.outcome, linear_term, square_term, "log_population", "oil_export_share", "year"]
    ).copy()
    y = pd.to_numeric(work[spec.outcome], errors="coerce").to_numpy(dtype=float)
    x = pd.DataFrame(
        {
            "const": 1.0,
            linear_term: work[linear_term].astype(float),
            square_term: work[square_term].astype(float),
            "log_population": work["log_population"].astype(float),
            "oil_export_share": work["oil_export_share"].astype(float),
        },
        index=work.index,
    )
    year_dummies = pd.get_dummies(work["year"].astype(int), prefix="year", drop_first=True, dtype=float)
    x = pd.concat([x, year_dummies], axis=1)
    beta, *_ = np.linalg.lstsq(x.to_numpy(dtype=float), y, rcond=None)
    coef = pd.Series(beta, index=x.columns)
    income_min = float(work[PPP_VALUE_COL].quantile(0.01))
    income_max = float(work[PPP_VALUE_COL].quantile(0.99))
    if income_form == "level_ppp":
        income_grid = np.linspace(income_min, income_max, 220)
    else:
        income_grid = np.exp(np.linspace(np.log(income_min), np.log(income_max), 220))
    grid = pd.DataFrame({"const": np.ones(len(income_grid), dtype=float)})
    if income_form == "level_ppp":
        grid[linear_term] = income_grid / 10_000.0
        grid[square_term] = grid[linear_term] ** 2
    else:
        grid[linear_term] = np.log(income_grid)
        grid[square_term] = grid[linear_term] ** 2
    grid["log_population"] = float(work["log_population"].median())
    grid["oil_export_share"] = float(work["oil_export_share"].median())
    latest_year = int(pd.to_numeric(work["year"], errors="coerce").max())
    for col in year_dummies.columns:
        grid[col] = 1.0 if col == f"year_{latest_year}" else 0.0
    grid = grid.reindex(columns=x.columns, fill_value=0.0)
    return income_grid, grid.to_numpy(dtype=float) @ coef.to_numpy(dtype=float)


def binned_medians(panel: pd.DataFrame, outcome: str, income_form: str, bins: int = 12) -> pd.DataFrame:
    work = panel.dropna(subset=[PPP_VALUE_COL, outcome]).copy()
    income_col = PPP_VALUE_COL if income_form == "level_ppp" else PPP_LOG_COL
    work["income_bin"] = pd.qcut(work[income_col], bins, duplicates="drop")
    return (
        work.groupby("income_bin", observed=True)
        .agg(income=(income_col, "median"), value=(outcome, "median"), rows=(outcome, "size"))
        .reset_index(drop=True)
    )


def money_tick(value: float) -> str:
    if not math.isfinite(value):
        return "n/a"
    sign = "-" if value < 0 else ""
    abs_value = abs(value)
    if 0 < abs_value < 1:
        return f"{sign}<$1"
    if abs_value >= 1_000_000:
        return f"{sign}${abs_value / 1_000_000:.1f}m"
    if abs_value >= 1_000:
        return f"{sign}${abs_value / 1_000:.1f}k"
    return f"{sign}${abs_value:.0f}"


def p_tick(value: float) -> str:
    if not math.isfinite(value):
        return "n/a"
    if value < 0.001:
        return "<0.001"
    return f"{value:.3f}"


def plot_one_diagnostic(
    ax: plt.Axes,
    panel: pd.DataFrame,
    summary_row: pd.Series,
    spec: OutcomeSpec,
    income_form: str,
    *,
    label: str | None = None,
    show_read_note: bool = False,
) -> None:
    blue = "#1f5f8b"
    red = "#a23b2a"
    black = "#111827"
    gray = "#9ca3af"
    light = "#d1d5db"

    line_x, line_y = fit_line(panel, spec, income_form)
    bins = binned_medians(panel, spec.outcome, income_form)
    if income_form == "level_ppp":
        plot_x = panel[PPP_VALUE_COL]
        fit_x = line_x
        x_label = f"{PPP_LABEL} (dollars)"
        variable_note = "Level PPP: fit uses PPP income and PPP income squared."
    else:
        plot_x = panel[PPP_LOG_COL]
        fit_x = np.log(line_x)
        x_label = f"log {PPP_LABEL}"
        variable_note = "Log PPP: fit uses log PPP income and log PPP income squared."

    ax.scatter(plot_x, panel[spec.outcome], s=10, alpha=0.18, color=gray, edgecolors="none")
    ax.plot(fit_x, line_y, color=blue, lw=2.1)
    ax.plot(bins["income"], bins["value"], color=black, lw=1.7, marker="o", markersize=4.4)
    ylo = max(0, min(panel[spec.outcome].quantile(0.005), np.nanmin(line_y)) - 0.03)
    yhi = min(1.04, max(panel[spec.outcome].quantile(0.995), np.nanmax(line_y)) + 0.03)
    ax.set_ylim(ylo, yhi)
    tp = float(summary_row["turning_point_ppp_constant_2021_intl_usd"])
    if bool(summary_row["turning_point_inside_minmax"]):
        tp_x = tp if income_form == "level_ppp" else math.log(tp)
        ax.axvline(tp_x, color=red, lw=1.2, linestyle="--")
        ax.text(
            tp_x,
            ylo + 0.025 * (yhi - ylo),
            f"TP {money_tick(tp)}",
            rotation=90,
            va="bottom",
            ha="right",
            color=red,
            fontsize=8,
        )
    else:
        ax.text(
            0.02,
            0.04,
            f"outside: TP {money_tick(tp)}",
            transform=ax.transAxes,
            fontsize=8,
            color=red,
            va="bottom",
        )
    ax.grid(axis="y", color=light, lw=0.7, alpha=0.7)
    ax.grid(axis="x", color=light, lw=0.4, alpha=0.25)
    p_val = float(summary_row["quadratic_p_value"])
    p_txt = "<0.001" if p_val < 0.001 else f"{p_val:.3f}"
    prefix = f"{label}. " if label else ""
    ax.set_title(f"{prefix}{spec.title}\n{summary_row['verdict']}; quadratic p={p_txt}", loc="left")
    ax.set_xlabel(x_label)
    ax.set_ylabel(spec.title.replace("Export ", "").replace("Import ", ""))
    if show_read_note:
        ax.text(
            0.02,
            0.96,
            "\n".join(
                [
                    "Gray dots: country-years.",
                    "Black line: income-bin medians.",
                    "Blue line: controlled quadratic.",
                    variable_note,
                ]
            ),
            transform=ax.transAxes,
            va="top",
            fontsize=9,
            color=black,
            linespacing=1.35,
            bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "edgecolor": "#d1d5db", "alpha": 0.88},
        )


def plot_diagnostics(
    panels: dict[str, pd.DataFrame],
    summary: pd.DataFrame,
    figure_dir: Path,
    diagnostics: dict[str, Any],
    outcome_specs: Iterable[OutcomeSpec] = OUTCOME_SPECS,
) -> None:
    figure_dir.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.labelsize": 10,
            "axes.titlesize": 11,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
        }
    )
    blue = "#1f5f8b"
    red = "#a23b2a"
    black = "#111827"
    gray = "#9ca3af"
    light = "#d1d5db"
    forms = [("level_ppp", "Level PPP"), ("log_ppp", "Log PPP")]

    specs = tuple(outcome_specs)
    sample_note = diagnostics.get("figure_sample_note", "country-years, 55-country balanced panel, 2000-2024.")
    for income_form, form_label in forms:
        fig, axes = plt.subplots(3, 2, figsize=(12.5, 13.0), constrained_layout=True)
        axes = axes.reshape(-1)
        plot_axes = axes[:-1]
        for ax, label, spec in zip(plot_axes, ["A", "B", "C", "D", "E"], specs):
            panel = panels[spec.slug]
            row = summary[(summary["outcome_slug"].eq(spec.slug)) & (summary["income_form"].eq(income_form))].iloc[0]
            plot_one_diagnostic(ax, panel, row, spec, income_form, label=label)
        for ax in plot_axes[len(specs) :]:
            ax.axis("off")
        ax = axes[-1]
        ax.axis("off")
        variable_note = (
            "Level PPP uses dollar income and income squared; the x-axis is linear dollars."
            if income_form == "level_ppp"
            else "Log PPP uses log income and log-income squared; the x-axis is log income."
        )
        ax.text(
            0.02,
            0.88,
            "\n".join(
                [
                    f"How to read the {form_label} figure:",
                    f"Gray dots: {sample_note}",
                    "Black line: median outcome within PPP-income bins.",
                    "Blue line: controlled quadratic with year FE, log population, oil share.",
                    variable_note,
                    "Red dashed line: implied turning point when inside observed support.",
                ]
            ),
            va="top",
            fontsize=11,
            color=black,
            linespacing=1.55,
        )
        fig.suptitle(f"PPP GDP Hump Diagnostics: {form_label} Income Form", fontsize=15, fontweight="bold")
        fig.savefig(figure_dir / f"ppp_hump_diagnostics_{income_form}_five_outcomes.png", dpi=220, bbox_inches="tight")
        plt.close(fig)


def plot_product_browser_figures(
    panels: dict[str, pd.DataFrame],
    summary: pd.DataFrame,
    figure_dir: Path,
    outcome_specs: Iterable[OutcomeSpec] = OUTCOME_SPECS,
) -> None:
    browser_dir = figure_dir / "product_browser"
    browser_dir.mkdir(parents=True, exist_ok=True)
    specs = [
        spec
        for spec in outcome_specs
        if spec.slug
        in {
            "export_world_relative_product_gini",
            "export_product_gini",
            "import_product_gini",
        }
    ]
    for income_form, form_label in [("level_ppp", "Level PPP"), ("log_ppp", "Log PPP")]:
        for spec in specs:
            fig, ax = plt.subplots(figsize=(9.2, 6.0), constrained_layout=True)
            row = summary[(summary["outcome_slug"].eq(spec.slug)) & (summary["income_form"].eq(income_form))].iloc[0]
            plot_one_diagnostic(ax, panels[spec.slug], row, spec, income_form, show_read_note=True)
            fig.suptitle(f"{spec.title}: {form_label} income form", fontsize=14, fontweight="bold")
            fig.savefig(browser_dir / f"{spec.slug}_{income_form}.png", dpi=220, bbox_inches="tight")
            plt.close(fig)


def write_markdown(
    path: Path,
    summary: pd.DataFrame,
    diagnostics: dict[str, Any],
) -> None:
    raw_show = summary[
        [
            "outcome_label",
            "estimator",
            "income_form",
            "quadratic_coefficient",
            "quadratic_p_value",
            "turning_point_ppp_constant_2021_intl_usd",
            "turning_point_inside_minmax",
            "turning_point_inside_p05_p95",
            "verdict",
            "nobs",
            "clusters",
        ]
    ].copy()
    show = pd.DataFrame(
        {
            "outcome": raw_show["outcome_label"],
            "estimator": raw_show["estimator"],
            "income_form": raw_show["income_form"],
            "quadratic_sign_p": raw_show.apply(
                lambda row: f"{'+' if row['quadratic_coefficient'] > 0 else '-'}, p={p_tick(float(row['quadratic_p_value']))}",
                axis=1,
            ),
            "turning_point": raw_show["turning_point_ppp_constant_2021_intl_usd"].map(lambda value: money_tick(float(value))),
            "inside_minmax": raw_show["turning_point_inside_minmax"],
            "inside_p05_p95": raw_show["turning_point_inside_p05_p95"],
            "verdict": raw_show["verdict"],
            "nobs": raw_show["nobs"],
            "clusters": raw_show["clusters"],
        }
    )
    headline = summary[summary["estimator"].eq("pooled_year_fe")].copy() if "estimator" in summary.columns else summary.copy()
    level = headline[headline["income_form"].eq("level_ppp")]
    log = headline[headline["income_form"].eq("log_ppp")]
    level_clear = ", ".join(level.loc[level["verdict"].eq("clear hump"), "outcome_label"].tolist()) or "none"
    log_clear = ", ".join(log.loc[log["verdict"].eq("clear hump"), "outcome_label"].tolist()) or "none"
    if diagnostics["country_sample"] == CADOT_BROAD_SAMPLE:
        sample_intro = (
            "This is a descriptive Cadot-style hump check for the `cadot_broad_156` Cadot broad "
            "156-country modern replication sample, 2000-2024. The income variable is World Bank "
            "`NY.GDP.PCAP.PP.KD`, GDP per capita at PPP in constant 2021 international dollars."
        )
        comparability_note = (
            "- This is the Cadot-comparable broad replication track: active non-group Comtrade reporters with ISO3 metadata "
            "and at least 19 annual HS final-data years in 2000-2024. It is not a website sample and does not replace `rd2_countries`."
        )
        sample_diag_lines = [
            f"- Selected reporter sample: {diagnostics['selected_reporters']} reporters; expected {diagnostics.get('expected_selected_reporters', 'n/a')}.",
            f"- Complete-case policy: outcome-specific country-years with valid concentration, PPP income, log population, oil share, and year FE.",
            f"- Analytic sample rows by outcome are reported in `{diagnostics['outputs']['attrition']}`.",
        ]
        panel_file = "ppp_hump_analysis_panel.csv"
    else:
        sample_intro = (
            "This is a descriptive Cadot-style hump check for `rd2_countries`, 2000-2024. The income variable is World Bank "
            "`NY.GDP.PCAP.PP.KD`, GDP per capita at PPP in constant 2021 international dollars."
        )
        comparability_note = (
            "- This is close to Cadot on the income variable, but not identical to Cadot's original design: it uses the modern rd2 2000-2024 panel, "
            "our product/partner concentration outcomes, log population and oil-share controls, year fixed effects, and reporter-country clustered standard errors."
        )
        sample_diag_lines = [
            f"- Common balanced sample: {diagnostics['balanced_countries']} countries x {diagnostics['balanced_years']} years = {diagnostics['balanced_rows']} rows per outcome/form.",
        ]
        panel_file = "ppp_hump_common_sample_panel.csv"
    outcome_count = int(summary["outcome_slug"].nunique()) if "outcome_slug" in summary.columns else 0
    estimator_count = int(summary["estimator"].nunique()) if "estimator" in summary.columns else 1
    text = [
        "# PPP GDP Hump Regressions",
        "",
        f"Generated: {diagnostics['created_at_utc']}",
        "",
        sample_intro,
        "",
        "Specification:",
        "",
        "`outcome_ct = beta1 income_ct + beta2 income_ct^2 + log_population_ct + oil_export_share_ct + year_FE_t + error_ct`",
        "",
        "The table reports pooled year-FE, country+year-FE, and between-country variants. Pooled and country+year-FE standard errors are clustered by reporter country; between estimates are country-mean OLS. Product outcomes inherit the pipeline rule excluding HS6 `999999`; partner outcomes use the default partner-total convention.",
        "",
        "## Results",
        "",
        show.to_markdown(index=False),
        "",
        "## Short Read",
        "",
        f"- In the pooled/year-FE headline, level PPP restores clear Cadot-style concentration U-shapes for: {level_clear}.",
        f"- In the pooled/year-FE headline, log PPP restores a clear concentration U-shape for: {log_clear}.",
        "- In plain English, a positive quadratic is a U-shape in concentration: concentration first falls with development, then rises after the turning point. That is the concentration-side version of the Cadot diversification hump.",
        "- The level/log split matters because logging income compresses the rich-country tail where late-stage reconcentration is expected. Level PPP therefore stays closer to Cadot's constant-PPP setup, while log PPP is a stricter functional-form stress test.",
        comparability_note,
        "",
        "## Diagnostics",
        "",
        *sample_diag_lines,
        f"- PPP source: `{PPP_INDICATOR}` ({PPP_LABEL}).",
        f"- PPP coverage rows in selected country panel: {diagnostics['ppp_cache_complete_rows']} / {diagnostics['ppp_cache_expected_rows']}; complete countries: {diagnostics['ppp_cache_complete_countries']} / {diagnostics['ppp_cache_countries']}; duplicate iso3-year keys: {diagnostics['ppp_cache_duplicate_iso3_year_keys']}.",
        f"- PPP rows after merging into the controls panel: {diagnostics['ppp_control_complete_rows']} / {diagnostics['ppp_control_expected_rows']}.",
        f"- PPP support in analytic sample: ${diagnostics['income_min']:,.0f} to ${diagnostics['income_max']:,.0f}; p05=${diagnostics['income_p05']:,.0f}, p95=${diagnostics['income_p95']:,.0f}.",
        "",
        "## Interpretation",
        "",
        "Level PPP is the closer Cadot-style functional form. Log PPP compresses the rich-country end where reconcentration is supposed to appear, so it is the stricter functional-form check.",
        "",
        "## Outputs",
        "",
        f"- `ppp_hump_regression_summary.csv`: compact {outcome_count} outcomes x 2 income forms x {estimator_count} estimators results table.",
        "- `ppp_hump_regression_models.csv`: term-level regression output.",
        f"- `{panel_file}`: analytic country-year panel used for the regressions.",
        "- `ppp_hump_sample_attrition.csv`: outcome-level attrition diagnostics.",
        "- `ppp_hump_diagnostics_level_ppp_five_outcomes.png`: level-PPP visual diagnostics.",
        "- `ppp_hump_diagnostics_log_ppp_five_outcomes.png`: log-PPP visual diagnostics.",
    ]
    path.write_text("\n".join(text) + "\n", encoding="utf-8")


def output_locations(country_sample: str) -> tuple[Path, Path, Path, str]:
    result_dir = sample_results_dir(country_sample)
    if country_sample == CADOT_BROAD_SAMPLE:
        return (
            result_dir / "cadot_broad_ppp_hump_regression_tables",
            result_dir / "cadot_broad_ppp_hump_regression_figures",
            result_dir / "cadot_broad_ppp_hump_regressions.md",
            "ppp_hump_analysis_panel.csv",
        )
    return (
        result_dir / "ppp_hump_regression_tables",
        result_dir / "ppp_hump_regression_figures",
        result_dir / "ppp_hump_regressions.md",
        "ppp_hump_common_sample_panel.csv",
    )


def build_saved_analysis_panel(panels: dict[str, pd.DataFrame], outcome_specs: Iterable[OutcomeSpec]) -> pd.DataFrame:
    frames = []
    for spec in outcome_specs:
        cols = [
            "country",
            "iso3",
            "reporter_code",
            "year",
            PPP_VALUE_COL,
            PPP_LEVEL_COL,
            PPP_LEVEL_SQ_COL,
            PPP_LOG_COL,
            PPP_LOG_SQ_COL,
            "log_population",
            "oil_export_share",
            spec.outcome,
        ]
        frame = panels[spec.slug][[col for col in cols if col in panels[spec.slug].columns]].copy()
        frame = frame.rename(columns={spec.outcome: spec.slug})
        frames.append(frame.drop_duplicates(["reporter_code", "year"]))
    if not frames:
        return pd.DataFrame()
    base_cols = [
        "country",
        "iso3",
        "reporter_code",
        "year",
        PPP_VALUE_COL,
        PPP_LEVEL_COL,
        PPP_LEVEL_SQ_COL,
        PPP_LOG_COL,
        PPP_LOG_SQ_COL,
        "log_population",
        "oil_export_share",
    ]
    out = frames[0]
    for frame in frames[1:]:
        value_cols = [col for col in frame.columns if col not in base_cols]
        out = out.merge(frame[["reporter_code", "year", *value_cols]], on=["reporter_code", "year"], how="outer", validate="one_to_one")
    return out.sort_values(["country", "reporter_code", "year"]).reset_index(drop=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country-sample", default=COUNTRY_SAMPLE, choices=SUPPORTED_COUNTRY_SAMPLES)
    parser.add_argument("--start-year", type=int, default=START_YEAR)
    parser.add_argument("--end-year", type=int, default=END_YEAR)
    parser.add_argument("--refresh-ppp", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if args.country_sample == COUNTRY_SAMPLE and (args.start_year != START_YEAR or args.end_year != END_YEAR):
        raise RuntimeError("PPP hump regressions currently use the rd2 2000-2024 balanced website window.")
    if args.country_sample == CADOT_BROAD_SAMPLE and (args.start_year != CADOT_BROAD_START_YEAR or args.end_year != CADOT_BROAD_END_YEAR):
        raise RuntimeError(f"{CADOT_BROAD_SAMPLE} PPP regressions use the fixed 2000-2024 Cadot broad replication window.")

    table_dir, figure_dir, markdown_path, panel_filename = output_locations(args.country_sample)
    table_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)

    balance_policy = "rd2_balanced" if args.country_sample == COUNTRY_SAMPLE else "complete_case"
    model_sample_label = RD2_MODEL_SAMPLE_LABEL if args.country_sample == COUNTRY_SAMPLE else CADOT_MODEL_SAMPLE_LABEL
    panels, controls, common_codes, attrition, outcome_specs = build_outcome_panels(
        args.country_sample,
        args.start_year,
        args.end_year,
        args.refresh_ppp,
        balance_policy=balance_policy,
    )
    models, summary = run_models(panels, outcome_specs=outcome_specs, model_sample_label=model_sample_label)
    country_panel = read_country_panel(args.country_sample)
    ppp_cache = read_cached_ppp_controls(sample_processed_dir(args.country_sample) / "ppp_hump_world_bank_controls.csv")
    ppp_cache_window = ppp_cache[ppp_cache["year"].between(args.start_year, args.end_year)].copy()
    ppp_country_count = int(country_panel["iso3"].nunique())
    ppp_expected_rows = ppp_country_count * (args.end_year - args.start_year + 1)
    ppp_complete_by_country = (
        ppp_cache_window.groupby("iso3")[PPP_VALUE_COL]
        .apply(lambda values: int(values.notna().sum()))
        .reindex(sorted(country_panel["iso3"].unique()), fill_value=0)
    )
    analysis_panel = build_saved_analysis_panel(panels, outcome_specs)

    expected_ppp = controls[controls["year"].between(args.start_year, args.end_year)]
    complete_ppp = int(expected_ppp[PPP_VALUE_COL].notna().sum())
    selected_reporters = int(country_panel["reporter_code"].nunique())
    income_support = pd.concat([panel[PPP_VALUE_COL] for panel in panels.values()], ignore_index=True).dropna()
    diagnostics = {
        "created_at_utc": now_utc(),
        "country_sample": args.country_sample,
        "start_year": args.start_year,
        "end_year": args.end_year,
        "balance_policy": balance_policy,
        "model_sample_label": model_sample_label,
        "selected_reporters": selected_reporters,
        "expected_selected_reporters": 156 if args.country_sample == CADOT_BROAD_SAMPLE else selected_reporters,
        "balanced_countries": len(common_codes),
        "balanced_years": args.end_year - args.start_year + 1,
        "balanced_rows": len(analysis_panel),
        "ppp_indicator": PPP_INDICATOR,
        "ppp_label": PPP_LABEL,
        "ppp_cache_expected_rows": int(ppp_expected_rows),
        "ppp_cache_complete_rows": int(ppp_cache_window[PPP_VALUE_COL].notna().sum()),
        "ppp_cache_countries": ppp_country_count,
        "ppp_cache_complete_countries": int((ppp_complete_by_country == (args.end_year - args.start_year + 1)).sum()),
        "ppp_cache_duplicate_iso3_year_keys": int(ppp_cache_window.duplicated(["iso3", "year"]).sum()),
        "ppp_control_expected_rows": int(len(expected_ppp)),
        "ppp_control_complete_rows": complete_ppp,
        "income_min": float(income_support.min()),
        "income_p05": float(income_support.quantile(0.05)),
        "income_p95": float(income_support.quantile(0.95)),
        "income_max": float(income_support.max()),
        "common_reporter_codes": common_codes,
        "included_outcomes": [spec.slug for spec in outcome_specs],
        "figure_sample_note": (
            "country-years, Cadot broad 156-country complete-case panels, 2000-2024."
            if args.country_sample == CADOT_BROAD_SAMPLE
            else "country-years, 55-country balanced panel, 2000-2024."
        ),
        "outputs": {
            "summary": rel(table_dir / "ppp_hump_regression_summary.csv"),
            "models": rel(table_dir / "ppp_hump_regression_models.csv"),
            "panel": rel(table_dir / panel_filename),
            "attrition": rel(table_dir / "ppp_hump_sample_attrition.csv"),
        },
    }

    summary.to_csv(table_dir / "ppp_hump_regression_summary.csv", index=False)
    models.to_csv(table_dir / "ppp_hump_regression_models.csv", index=False)
    analysis_panel.to_csv(table_dir / panel_filename, index=False)
    attrition.to_csv(table_dir / "ppp_hump_sample_attrition.csv", index=False)
    controls.to_csv(table_dir / "ppp_hump_controls_snapshot.csv", index=False)
    (table_dir / "ppp_hump_diagnostics.json").write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True, default=clean_scalar) + "\n",
        encoding="utf-8",
    )
    plot_diagnostics(panels, summary, figure_dir, diagnostics, outcome_specs=outcome_specs)
    plot_product_browser_figures(panels, summary, figure_dir, outcome_specs=outcome_specs)
    write_markdown(markdown_path, summary, diagnostics)

    print(f"Wrote {rel(table_dir)}")
    print(f"Wrote {rel(figure_dir)}")
    print(f"Wrote {rel(markdown_path)}")


if __name__ == "__main__":
    main()
