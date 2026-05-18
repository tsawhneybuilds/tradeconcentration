#!/usr/bin/env python3
"""
Real-data pipeline for Exercises 1, 6, and 10.

Primary source: UN Comtrade final annual merchandise HS bulk files.

The script deliberately stops before analysis when no Comtrade subscription key
is available. That matches the project rule: do not substitute non-equivalent
or inferred trade values for the required HS6 reporter-product-partner data.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import os
import re
import shutil
import sys
import textwrap
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import requests

try:
    import comtradeapicall
except ImportError:  # pragma: no cover - handled at runtime for user clarity
    comtradeapicall = None


ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data" / "raw"
COMTRADE_RAW = DATA_RAW / "comtrade"
COMTRADE_BULK = COMTRADE_RAW / "bulk"
COMTRADE_AVAILABILITY = COMTRADE_RAW / "availability"
WORLD_BANK_RAW = DATA_RAW / "world_bank_gdp"
DATA_PROCESSED = ROOT / "data" / "processed"
RESULTS = ROOT / "results"
EX01_TABLES = RESULTS / "exercise_01_tables"
EX01_FIGURES = RESULTS / "exercise_01_figures"
EX06_TABLES = RESULTS / "exercise_06_tables"
EX06_FIGURES = RESULTS / "exercise_06_figures"
EX10_TABLES = RESULTS / "exercise_10_tables"
EX10_FIGURES = RESULTS / "exercise_10_figures"


@dataclass(frozen=True)
class Country:
    country: str
    iso3: str
    reporter_code: int


PROF_P_COUNTRIES = [
    Country("Australia", "AUS", 36),
    Country("Austria", "AUT", 40),
    Country("Belgium", "BEL", 56),
    Country("Brazil", "BRA", 76),
    Country("Canada", "CAN", 124),
    Country("China", "CHN", 156),
    Country("Czech Republic", "CZE", 203),
    Country("Denmark", "DNK", 208),
    Country("Finland", "FIN", 246),
    Country("France", "FRA", 251),
    Country("Germany", "DEU", 276),
    Country("Greece", "GRC", 300),
    Country("Hungary", "HUN", 348),
    Country("Iceland", "ISL", 352),
    Country("India", "IND", 699),
    Country("Ireland", "IRL", 372),
    Country("Italy", "ITA", 380),
    Country("Japan", "JPN", 392),
    Country("Korea", "KOR", 410),
    Country("Luxembourg", "LUX", 442),
    Country("Mexico", "MEX", 484),
    Country("Netherlands", "NLD", 528),
    Country("New Zealand", "NZL", 554),
    Country("Norway", "NOR", 579),
    Country("Poland", "POL", 616),
    Country("Russia", "RUS", 643),
    Country("Slovakia", "SVK", 703),
    Country("Spain", "ESP", 724),
    Country("Sweden", "SWE", 752),
    Country("Switzerland", "CHE", 757),
    Country("Turkey", "TUR", 792),
    Country("United Kingdom", "GBR", 826),
    Country("United States", "USA", 842),
]

FLOW_LABELS = {
    "X": "Exports",
    "M": "Imports",
    2: "Exports",
    1: "Imports",
    "2": "Exports",
    "1": "Imports",
}

EXCLUSION_SETS = {
    "baseline": set(),
    "oil_only": {"27"},
    "oil_aircraft_autos": {"27", "87", "88"},
    "oil_aircraft_autos_precious": {"27", "71", "87", "88"},
    "full_exclusion": {"27", "71", "87", "88", "89", "93"},
}

EXCLUSION_LABELS = {
    "27": "oil_petroleum_hs27",
    "71": "precious_stones_metals_hs71",
    "87": "vehicles_parts_hs87",
    "88": "aircraft_hs88",
    "89": "ships_hs89",
    "93": "arms_hs93",
}


def parse_file_size_to_bytes(value: object) -> float:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return 0.0
    text = str(value).strip()
    match = re.match(r"([0-9.]+)\s*([KMGT]?B)?", text, re.IGNORECASE)
    if not match:
        return 0.0
    amount = float(match.group(1))
    unit = (match.group(2) or "B").upper()
    multiplier = {
        "B": 1,
        "KB": 1_000,
        "MB": 1_000_000,
        "GB": 1_000_000_000,
        "TB": 1_000_000_000_000,
    }.get(unit, 1)
    return amount * multiplier


def ensure_dirs() -> None:
    for path in [
        COMTRADE_BULK,
        COMTRADE_AVAILABILITY,
        WORLD_BANK_RAW,
        DATA_PROCESSED,
        RESULTS,
        EX01_TABLES,
        EX01_FIGURES,
        EX06_TABLES,
        EX06_FIGURES,
        EX10_TABLES,
        EX10_FIGURES,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def get_key(args: argparse.Namespace) -> str | None:
    return args.subscription_key or os.getenv("COMTRADE_SUBSCRIPTION_KEY") or None


def write_blocker(reason: str, details: dict | None = None) -> None:
    details = details or {}
    manifest = {
        "created_at_utc": now_utc(),
        "status": "blocked",
        "reason": reason,
        "details": details,
        "required_env_var": "COMTRADE_SUBSCRIPTION_KEY",
        "raw_trade_data_policy": "No non-equivalent source or inferred trade values were substituted.",
    }
    write_json(COMTRADE_RAW / "manifest.json", manifest)
    memo = f"""# Data Access Blocker

Created: {manifest["created_at_utc"]}

The real-data exercises could not be run because the UN Comtrade API requires a valid subscription key for the HS6 bulk/final data needed here.

Reason:

{reason}

What is needed:

1. Set a valid key in the shell:

   ```bash
   export COMTRADE_SUBSCRIPTION_KEY="..."
   ```

2. Re-run:

   ```bash
   python scripts/trade_concentration_pipeline.py --stage all
   ```

Policy followed:

- No synthetic or LLM-estimated trade values were used.
- WITS or other sources were not substituted for the required Comtrade reporter-product-partner HS6 records.
- `exercises.md` was not edited because no exercise results are ready for discussion.

Details:

```json
{json.dumps(details, indent=2, sort_keys=True)}
```
"""
    write_text(RESULTS / "data_access_blocker.md", memo)


def check_comtrade_access(subscription_key: str | None) -> bool:
    if not subscription_key:
        availability = download_public_availability_without_key()
        details = {
            "public_availability_rows_saved": int(len(availability)),
            "public_availability_file": str((COMTRADE_AVAILABILITY / "prof_p_panel_public_availability.csv").relative_to(ROOT)),
        }
        write_blocker("No Comtrade subscription key found in COMTRADE_SUBSCRIPTION_KEY or --subscription-key.", details)
        return False

    if comtradeapicall is None:
        write_blocker("Python package `comtradeapicall` is not installed.")
        return False

    try:
        df = comtradeapicall.getFinalDataBulkAvailability(
            subscription_key,
            typeCode="C",
            freqCode="A",
            clCode="HS",
            period=2001,
            reporterCode=842,
        )
    except Exception as exc:  # pragma: no cover - depends on remote API
        write_blocker("Comtrade access probe failed.", {"exception": repr(exc)})
        return False

    if df is None or len(df) == 0:
        write_blocker(
            "Comtrade access probe returned no data for US annual HS 2001 bulk availability.",
            {"probe_reporter": 842, "probe_period": 2001},
        )
        return False

    return True


def download_public_availability_without_key() -> pd.DataFrame:
    """Save public Comtrade annual HS final-data availability metadata.

    This does not provide the reporter-product-partner trade values needed for
    the exercises. It only records which annual HS datasets appear available.
    """
    rows = []
    if comtradeapicall is None:
        return pd.DataFrame()
    for country in PROF_P_COUNTRIES:
        try:
            print(f"Checking public availability: {country.country} ({country.reporter_code})", flush=True)
            df = comtradeapicall._getFinalDataAvailability(
                typeCode="C",
                freqCode="A",
                clCode="HS",
                period=None,
                reporterCode=country.reporter_code,
            )
        except Exception as exc:
            rows.append(
                {
                    "country": country.country,
                    "iso3": country.iso3,
                    "reporter_code": country.reporter_code,
                    "period": None,
                    "available": False,
                    "error": repr(exc),
                }
            )
            continue
        if df is None or df.empty:
            rows.append(
                {
                    "country": country.country,
                    "iso3": country.iso3,
                    "reporter_code": country.reporter_code,
                    "period": None,
                    "available": False,
                    "error": "",
                }
            )
            continue
        df = df.copy()
        df["country"] = country.country
        df["iso3"] = country.iso3
        df["reporter_code_expected"] = country.reporter_code
        df["available"] = True
        df.to_csv(COMTRADE_AVAILABILITY / f"{country.iso3}_{country.reporter_code}_public_availability.csv", index=False)
        rows.extend(df.to_dict("records"))
    availability = pd.DataFrame(rows)
    availability.to_csv(COMTRADE_AVAILABILITY / "prof_p_panel_public_availability.csv", index=False)
    return availability


def save_country_panel() -> pd.DataFrame:
    panel = pd.DataFrame([c.__dict__ for c in PROF_P_COUNTRIES])
    panel.to_csv(DATA_PROCESSED / "prof_p_country_panel.csv", index=False)
    return panel


def download_availability(subscription_key: str) -> pd.DataFrame:
    existing = COMTRADE_AVAILABILITY / "prof_p_panel_availability.csv"
    if existing.exists():
        print(f"Using existing keyed availability: {existing}", flush=True)
        return pd.read_csv(existing)

    rows = []
    for country in PROF_P_COUNTRIES:
        print(f"Checking availability: {country.country} ({country.reporter_code})", flush=True)
        df = comtradeapicall.getFinalDataBulkAvailability(
            subscription_key,
            typeCode="C",
            freqCode="A",
            clCode="HS",
            period=None,
            reporterCode=country.reporter_code,
        )
        if df is None or df.empty:
            rows.append(
                {
                    "country": country.country,
                    "iso3": country.iso3,
                    "reporter_code": country.reporter_code,
                    "period": None,
                    "available": False,
                }
            )
            continue
        df = df.copy()
        df["country"] = country.country
        df["iso3"] = country.iso3
        df["reporter_code_expected"] = country.reporter_code
        df.to_csv(COMTRADE_AVAILABILITY / f"{country.iso3}_{country.reporter_code}_availability.csv", index=False)
        rows.extend(df.to_dict("records"))

    availability = pd.DataFrame(rows)
    availability.to_csv(COMTRADE_AVAILABILITY / "prof_p_panel_availability.csv", index=False)
    return availability


def expected_bulk_glob(country: Country, period: int) -> list[Path]:
    code = str(country.reporter_code).zfill(3)
    return sorted(COMTRADE_BULK.glob(f"COMTRADE-FINAL-CA{code}{period}H*.gz")) + sorted(
        COMTRADE_BULK.glob(f"COMTRADE-FINAL-CA{code}{period}H*.txt")
    )


def bulk_filename(row: pd.Series) -> str:
    publication_date = row.get("publicationDate")
    if publication_date is None or (isinstance(publication_date, float) and np.isnan(publication_date)):
        publication = "1900-01-01"
    else:
        publication = str(publication_date)[:10]
    return (
        "COMTRADE-FINAL-"
        + str(row["typeCode"])
        + str(row["freqCode"])
        + str(int(row["reporterCode"])).zfill(3)
        + str(int(row["period"]))
        + str(row["classificationCode"])
        + "["
        + publication
        + "].gz"
    )


def gzip_validation_error(path: Path) -> str | None:
    try:
        with gzip.open(path, "rb") as f:
            while f.read(1024 * 1024):
                pass
        return None
    except Exception as exc:
        return repr(exc)


def valid_gzip(path: Path) -> bool:
    return gzip_validation_error(path) is None


def download_one_bulk_file(row: dict, subscription_key: str, retries: int = 3) -> dict:
    filename = bulk_filename(pd.Series(row))
    destination = COMTRADE_BULK / filename
    tmp = destination.with_suffix(destination.suffix + ".part")
    if destination.exists() and valid_gzip(destination):
        return {"filename": filename, "status": "already_exists", "bytes": destination.stat().st_size}
    if destination.exists():
        destination.unlink()
    if tmp.exists():
        tmp.unlink()

    params = {"subscription-key": subscription_key}
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            with requests.get(row["fileUrl"], params=params, stream=True, timeout=(30, 600)) as resp:
                if resp.status_code != 200:
                    raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
                with tmp.open("wb") as fh:
                    for chunk in resp.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            fh.write(chunk)
            gzip_error = gzip_validation_error(tmp)
            if gzip_error is not None:
                head = tmp.read_bytes()[:24].hex() if tmp.exists() else ""
                size = tmp.stat().st_size if tmp.exists() else 0
                raise RuntimeError(f"downloaded file failed gzip validation: {gzip_error}; bytes={size}; head={head}")
            tmp.replace(destination)
            return {"filename": filename, "status": "downloaded", "bytes": destination.stat().st_size}
        except Exception as exc:
            last_error = repr(exc)
            if tmp.exists():
                tmp.unlink()
            time.sleep(min(2**attempt, 15))
    return {"filename": filename, "status": "failed", "error": last_error}


def download_bulk_files(
    subscription_key: str,
    availability: pd.DataFrame,
    max_years: int | None = None,
    workers: int = 4,
    max_file_mb: float | None = None,
    min_file_mb: float | None = None,
) -> None:
    if availability.empty:
        raise RuntimeError("No Comtrade availability rows to download.")

    available = availability.dropna(subset=["period"]).copy()
    if "classificationCode" in available.columns:
        available = available[available["classificationCode"].astype(str).str.startswith("H")].copy()
    available["period"] = available["period"].astype(int)
    available = available.sort_values(["reporter_code_expected", "period"])
    if max_years is not None:
        available = available.groupby("reporter_code_expected", as_index=False).head(max_years)
    available["file_size_bytes_sort"] = available.get("fileSize", "").map(parse_file_size_to_bytes)
    if min_file_mb is not None:
        available = available[available["file_size_bytes_sort"] >= min_file_mb * 1_000_000].copy()
    if max_file_mb is not None:
        available = available[available["file_size_bytes_sort"] <= max_file_mb * 1_000_000].copy()
    available = available.sort_values(["file_size_bytes_sort"], ascending=True)

    jobs = available.to_dict("records")
    print(f"Downloading/checking {len(jobs)} HS bulk files with {workers} workers", flush=True)
    manifest_rows = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        future_map = {executor.submit(download_one_bulk_file, row, subscription_key): row for row in jobs}
        completed = 0
        for future in as_completed(future_map):
            row = future_map[future]
            completed += 1
            try:
                result = future.result()
            except Exception as exc:
                result = {"status": "failed", "error": repr(exc), "filename": bulk_filename(pd.Series(row))}
            if completed % 25 == 0 or result["status"] in {"failed", "downloaded"}:
                print(f"[{completed}/{len(jobs)}] {result['status']}: {result.get('filename')}", flush=True)
            manifest_rows.append(
                {
                    "country": row.get("country"),
                    "iso3": row.get("iso3"),
                    "reporter_code": int(row.get("reporterCode")),
                    "period": int(row.get("period")),
                    "classification_code": row.get("classificationCode"),
                    **result,
                }
            )
    failed = [row for row in manifest_rows if row["status"] == "failed"]
    if failed:
        write_json(COMTRADE_RAW / "download_failures.json", failed)
        raise RuntimeError(f"{len(failed)} Comtrade bulk files failed to download; see data/raw/comtrade/download_failures.json")

    manifest = {
        "created_at_utc": now_utc(),
        "source": "UN Comtrade final annual HS bulk data",
        "typeCode": "C",
        "freqCode": "A",
        "clCode": "HS",
        "countries": [c.__dict__ for c in PROF_P_COUNTRIES],
        "downloads": manifest_rows,
    }
    write_json(COMTRADE_RAW / "manifest.json", manifest)


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    normalized = {}
    for col in df.columns:
        key = re.sub(r"[^a-z0-9]+", "", str(col).lower())
        normalized[key] = col
    return df.rename(columns={v: k for k, v in normalized.items()})


def pick_col(df: pd.DataFrame, candidates: Iterable[str]) -> str:
    for cand in candidates:
        key = re.sub(r"[^a-z0-9]+", "", cand.lower())
        if key in df.columns:
            return key
    raise KeyError(f"None of these columns found: {list(candidates)}")


def read_comtrade_file(path: Path) -> pd.DataFrame:
    compression = "gzip" if path.suffix == ".gz" else None
    try:
        df = pd.read_csv(path, compression=compression, low_memory=False)
        if len(df.columns) == 1:
            raise ValueError("single column after comma parse")
    except Exception:
        df = pd.read_csv(path, sep="\t", compression=compression, low_memory=False)
    return normalize_columns(df)


def extract_leaf_trade(df: pd.DataFrame) -> pd.DataFrame:
    cmd_col = pick_col(df, ["cmdCode", "commodityCode", "Commodity Code"])
    value_col = pick_col(df, ["primaryValue", "Trade Value (US$)", "Trade Value", "tradeValue", "fobvalue", "cifvalue"])
    reporter_col = pick_col(df, ["reporterCode", "Reporter Code"])
    period_col = pick_col(df, ["period", "refYear", "year"])
    partner_col = pick_col(df, ["partnerCode", "Partner Code"])

    flow_col = None
    for candidates in (["flowCode", "Trade Flow Code"], ["flowDesc", "Trade Flow"]):
        try:
            flow_col = pick_col(df, candidates)
            break
        except KeyError:
            continue
    if flow_col is None:
        raise KeyError("No flow column found.")

    out = pd.DataFrame(
        {
            "reporter_code": pd.to_numeric(df[reporter_col], errors="coerce"),
            "year": pd.to_numeric(df[period_col], errors="coerce"),
            "partner_code": pd.to_numeric(df[partner_col], errors="coerce"),
            "cmd_code": df[cmd_col].astype(str).str.replace(r"\.0$", "", regex=True),
            "flow_raw": df[flow_col],
            "trade_value": pd.to_numeric(df[value_col], errors="coerce"),
        }
    )

    if "reporteriso" in df.columns:
        out["reporter_iso"] = df["reporteriso"]
    if "reporterdesc" in df.columns:
        out["reporter_desc"] = df["reporterdesc"]
    if "partneriso" in df.columns:
        out["partner_iso"] = df["partneriso"]
    if "partnerdesc" in df.columns:
        out["partner_desc"] = df["partnerdesc"]

    out["flow"] = out["flow_raw"].map(FLOW_LABELS)
    missing_flow = out["flow"].isna()
    if missing_flow.any():
        raw_lower = out.loc[missing_flow, "flow_raw"].astype(str).str.lower()
        out.loc[missing_flow & raw_lower.str.contains("export"), "flow"] = "Exports"
        out.loc[missing_flow & raw_lower.str.contains("import"), "flow"] = "Imports"

    out = out.dropna(subset=["reporter_code", "year", "partner_code", "trade_value", "flow"])
    out = out[out["trade_value"] > 0].copy()
    out["reporter_code"] = out["reporter_code"].astype(int)
    out["year"] = out["year"].astype(int)
    out["partner_code"] = out["partner_code"].astype(int)
    if "isaggregate" in df.columns:
        out["is_aggregate"] = pd.to_numeric(df.loc[out.index, "isaggregate"], errors="coerce").fillna(0).astype(int)
        out = out[out["is_aggregate"] == 0].copy()
    out = out[out["cmd_code"].str.match(r"^\d{6}$", na=False)].copy()
    out["hs2"] = out["cmd_code"].str[:2]
    out = out[out["partner_code"] != 0]
    out = out[out["flow"].isin(["Exports", "Imports"])]
    return out


def gini(values: Iterable[float]) -> float:
    arr = np.asarray(list(values), dtype=float)
    arr = arr[np.isfinite(arr) & (arr > 0)]
    if arr.size == 0:
        return np.nan
    arr.sort()
    n = arr.size
    total = arr.sum()
    if total <= 0:
        return np.nan
    idx = np.arange(1, n + 1)
    return float((2 * np.sum(idx * arr) / (n * total)) - ((n + 1) / n))


def top_share(values: Iterable[float], n: int | None = None, pct: float | None = None) -> float:
    arr = np.asarray(list(values), dtype=float)
    arr = arr[np.isfinite(arr) & (arr > 0)]
    if arr.size == 0:
        return np.nan
    arr.sort()
    arr = arr[::-1]
    if pct is not None:
        k = max(1, int(math.ceil(arr.size * pct)))
    elif n is not None:
        k = min(n, arr.size)
    else:
        raise ValueError("Need n or pct.")
    return float(arr[:k].sum() / arr.sum())


def metric_row(values: pd.Series, prefix: str) -> dict:
    vals = values.to_numpy(dtype=float)
    return {
        f"{prefix}_gini": gini(vals),
        f"{prefix}_top_1pct_share": top_share(vals, pct=0.01),
        f"{prefix}_top_2pct_share": top_share(vals, pct=0.02),
        f"{prefix}_top_5pct_share": top_share(vals, pct=0.05),
        f"{prefix}_top_10pct_share": top_share(vals, pct=0.10),
        f"{prefix}_top_200_share": top_share(vals, n=200),
        f"{prefix}_active_count": int(np.sum(vals > 0)),
    }


def compute_concentration(leaf: pd.DataFrame, variant: str = "baseline") -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    product_rows = []
    partner_rows = []
    cell_rows = []
    panel = save_country_panel()
    country_meta = panel.set_index("reporter_code")[["country", "iso3"]].to_dict("index")

    group_cols = ["reporter_code", "year", "flow"]
    for key, group in leaf.groupby(group_cols, sort=True):
        reporter_code, year, flow = key
        meta = country_meta.get(int(reporter_code), {"country": str(reporter_code), "iso3": ""})
        base = {
            "country": meta["country"],
            "iso3": meta["iso3"],
            "reporter_code": int(reporter_code),
            "year": int(year),
            "flow": flow,
            "variant": variant,
            "total_trade_value": float(group["trade_value"].sum()),
        }
        product_values = group.groupby("cmd_code", as_index=False)["trade_value"].sum()
        partner_values = group.groupby("partner_code", as_index=False)["trade_value"].sum()
        cell_values = group.groupby(["cmd_code", "partner_code"], as_index=False)["trade_value"].sum()

        product_rows.append({**base, **metric_row(product_values["trade_value"], "product")})
        partner_rows.append({**base, **metric_row(partner_values["trade_value"], "partner"), "top_5_partner_share": top_share(partner_values["trade_value"], n=5)})
        cell_rows.append({**base, **metric_row(cell_values["trade_value"], "product_partner_cell")})

    return pd.DataFrame(product_rows), pd.DataFrame(partner_rows), pd.DataFrame(cell_rows)


def collect_leaf_data() -> pd.DataFrame:
    files = sorted(COMTRADE_BULK.glob("COMTRADE-FINAL-*H*.gz")) + sorted(COMTRADE_BULK.glob("COMTRADE-FINAL-*H*.txt"))
    if not files:
        raise FileNotFoundError(f"No Comtrade bulk files found in {COMTRADE_BULK}")
    frames = []
    for path in files:
        print(f"Reading {path.name}", flush=True)
        raw = read_comtrade_file(path)
        leaf = extract_leaf_trade(raw)
        if not leaf.empty:
            frames.append(leaf)
    if not frames:
        raise RuntimeError("No positive HS6 import/export partner records were extracted.")
    out = pd.concat(frames, ignore_index=True)
    panel_codes = {c.reporter_code for c in PROF_P_COUNTRIES}
    out = out[out["reporter_code"].isin(panel_codes)].copy()
    out.to_parquet(DATA_PROCESSED / "hs6_partner_leaf_trade_all_years.parquet", index=False)
    return out


def hs_bulk_files() -> list[Path]:
    return sorted(COMTRADE_BULK.glob("COMTRADE-FINAL-*H*.gz")) + sorted(COMTRADE_BULK.glob("COMTRADE-FINAL-*H*.txt"))


def merge_metric_tables(product: pd.DataFrame, partner: pd.DataFrame, cell: pd.DataFrame) -> pd.DataFrame:
    if product.empty:
        return pd.DataFrame()
    return product.merge(
        partner.drop(columns=["total_trade_value"], errors="ignore"),
        on=["country", "iso3", "reporter_code", "year", "flow", "variant"],
        how="outer",
    ).merge(
        cell.drop(columns=["total_trade_value"], errors="ignore"),
        on=["country", "iso3", "reporter_code", "year", "flow", "variant"],
        how="outer",
    )


def run_exercises_streaming(simulations: int, seed: int) -> None:
    files = hs_bulk_files()
    if not files:
        raise FileNotFoundError(f"No HS Comtrade bulk files found in {COMTRADE_BULK}")

    ex01_products = []
    ex01_partners = []
    ex01_cells = []
    ex06_outputs = []
    ex06_removed = []
    product_total_frames = []
    panel = save_country_panel()

    for idx, path in enumerate(files, start=1):
        print(f"[{idx}/{len(files)}] Processing {path.name}", flush=True)
        raw = read_comtrade_file(path)
        leaf = extract_leaf_trade(raw)
        if leaf.empty:
            continue

        product, partner, cell = compute_concentration(leaf, "baseline")
        ex01_products.append(product)
        ex01_partners.append(partner)
        ex01_cells.append(cell)
        product_total_frames.append(product_totals_for_benchmark(leaf))

        base_totals = leaf.groupby(["reporter_code", "year", "flow"], as_index=False)["trade_value"].sum().rename(
            columns={"trade_value": "baseline_total_trade_value"}
        )
        for variant, excluded_hs2 in EXCLUSION_SETS.items():
            sub = leaf[~leaf["hs2"].isin(excluded_hs2)].copy() if excluded_hs2 else leaf
            vp, vpartner, vcell = compute_concentration(sub, variant)
            combined = merge_metric_tables(vp, vpartner, vcell)
            if combined.empty:
                continue
            combined = combined.merge(base_totals, on=["reporter_code", "year", "flow"], how="left")
            combined["trade_share_removed"] = 1 - (combined["total_trade_value"] / combined["baseline_total_trade_value"])
            ex06_outputs.append(combined)

        category_values = leaf[leaf["hs2"].isin(EXCLUSION_LABELS)].copy()
        if not category_values.empty:
            category_values["exclusion_category"] = category_values["hs2"].map(EXCLUSION_LABELS)
            cat = category_values.groupby(
                ["reporter_code", "year", "flow", "exclusion_category"], as_index=False
            )["trade_value"].sum()
            cat = cat.merge(base_totals, on=["reporter_code", "year", "flow"], how="left")
            cat["trade_share"] = cat["trade_value"] / cat["baseline_total_trade_value"]
            cat = cat.merge(panel, on="reporter_code", how="left")
            ex06_removed.append(cat)

    if not ex01_products:
        raise RuntimeError("No exercise rows were produced from HS bulk files.")

    product = pd.concat(ex01_products, ignore_index=True)
    partner = pd.concat(ex01_partners, ignore_index=True)
    cell = pd.concat(ex01_cells, ignore_index=True)
    product.to_csv(EX01_TABLES / "product_concentration_all_years.csv", index=False)
    partner.to_csv(EX01_TABLES / "partner_concentration_all_years.csv", index=False)
    cell.to_csv(EX01_TABLES / "product_partner_cell_concentration_all_years.csv", index=False)
    concentration = merge_metric_tables(product, partner, cell)
    concentration.to_parquet(DATA_PROCESSED / "concentration_all_years.parquet", index=False)
    concentration.to_csv(EX01_TABLES / "concentration_all_years.csv", index=False)
    make_exercise_01_figures(concentration)
    write_exercise_01_memo(concentration)

    exclusions = pd.concat(ex06_outputs, ignore_index=True)
    exclusions.to_parquet(DATA_PROCESSED / "concentration_exclusions_all_years.parquet", index=False)
    exclusions.to_csv(EX06_TABLES / "concentration_exclusions_all_years.csv", index=False)
    if ex06_removed:
        removed = pd.concat(ex06_removed, ignore_index=True)
        removed.to_csv(EX06_TABLES / "trade_share_removed_by_category.csv", index=False)
    make_exercise_06_figures(exclusions)
    write_exercise_06_memo(exclusions)

    product_totals = pd.concat(product_total_frames, ignore_index=True)
    product_totals.to_parquet(DATA_PROCESSED / "product_totals_for_random_benchmark.parquet", index=False)
    run_exercise_10_from_product_totals(product_totals, simulations=simulations, seed=seed)

    write_json(
        RESULTS / "run_manifest.json",
        {
            "created_at_utc": now_utc(),
            "mode": "streaming",
            "hs_bulk_files_processed": len(files),
            "rows_concentration": int(len(concentration)),
            "rows_exclusions": int(len(exclusions)),
            "rows_product_totals": int(len(product_totals)),
            "simulations": simulations,
            "seed": seed,
            "exercises_md_updated": False,
        },
    )


def run_exercise_01(leaf: pd.DataFrame) -> pd.DataFrame:
    product, partner, cell = compute_concentration(leaf, "baseline")
    product.to_csv(EX01_TABLES / "product_concentration_all_years.csv", index=False)
    partner.to_csv(EX01_TABLES / "partner_concentration_all_years.csv", index=False)
    cell.to_csv(EX01_TABLES / "product_partner_cell_concentration_all_years.csv", index=False)

    combined = product.merge(
        partner.drop(columns=["total_trade_value"]),
        on=["country", "iso3", "reporter_code", "year", "flow", "variant"],
        how="outer",
    ).merge(
        cell.drop(columns=["total_trade_value"]),
        on=["country", "iso3", "reporter_code", "year", "flow", "variant"],
        how="outer",
    )
    combined.to_parquet(DATA_PROCESSED / "concentration_all_years.parquet", index=False)
    combined.to_csv(EX01_TABLES / "concentration_all_years.csv", index=False)
    make_exercise_01_figures(combined)
    write_exercise_01_memo(combined)
    return combined


def make_exercise_01_figures(df: pd.DataFrame) -> None:
    import matplotlib.pyplot as plt
    import seaborn as sns

    sns.set_theme(style="whitegrid")

    med = df.groupby(["year", "flow"], as_index=False)[
        ["product_gini", "partner_gini", "product_partner_cell_gini"]
    ].median()
    long = med.melt(id_vars=["year", "flow"], var_name="measure", value_name="gini")
    plt.figure(figsize=(11, 6))
    sns.lineplot(data=long, x="year", y="gini", hue="measure", style="flow", markers=False)
    plt.title("Median Trade Concentration Over Time")
    plt.tight_layout()
    plt.savefig(EX01_FIGURES / "median_concentration_over_time.png", dpi=200)
    plt.close()

    plt.figure(figsize=(11, 6))
    sns.lineplot(data=df, x="year", y="product_gini", hue="flow", estimator="median", errorbar=None)
    plt.title("Median Product Gini: Imports vs Exports")
    plt.tight_layout()
    plt.savefig(EX01_FIGURES / "import_vs_export_product_gini_over_time.png", dpi=200)
    plt.close()

    countries = sorted(df["country"].dropna().unique())
    ncols = 3
    nrows = math.ceil(len(countries) / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(15, max(8, nrows * 2.2)), sharex=True, sharey=True)
    axes = np.asarray(axes).reshape(-1)
    for ax, country in zip(axes, countries):
        sub = df[df["country"] == country]
        sns.lineplot(data=sub, x="year", y="product_gini", hue="flow", ax=ax, legend=False)
        ax.set_title(country, fontsize=9)
        ax.set_xlabel("")
        ax.set_ylabel("")
    for ax in axes[len(countries):]:
        ax.axis("off")
    fig.suptitle("Country-Level Product Gini Lines")
    fig.tight_layout()
    fig.savefig(EX01_FIGURES / "country_product_gini_lines.png", dpi=200)
    plt.close(fig)

    scatter = df.copy()
    scatter["decade"] = (scatter["year"] // 10) * 10
    plt.figure(figsize=(10, 7))
    sns.scatterplot(
        data=scatter,
        x="product_gini",
        y="partner_gini",
        hue="flow",
        style="decade",
        alpha=0.65,
    )
    plt.title("Product Concentration vs Partner Concentration by Decade")
    plt.tight_layout()
    plt.savefig(EX01_FIGURES / "product_vs_partner_concentration_by_decade.png", dpi=200)
    plt.close()

    gdp = fetch_world_bank_gdp(sorted(df["iso3"].dropna().unique()), int(df["year"].min()), int(df["year"].max()))
    if not gdp.empty:
        merged = df.merge(gdp, on=["iso3", "year"], how="left")
        merged["size_group"] = merged.groupby("year")["gdp_current_usd"].transform(
            lambda x: np.where(x >= x.median(skipna=True), "Large GDP", "Small GDP")
        )
        plt.figure(figsize=(11, 6))
        sns.lineplot(
            data=merged.dropna(subset=["gdp_current_usd"]),
            x="year",
            y="product_gini",
            hue="size_group",
            style="flow",
            estimator="median",
            errorbar=None,
        )
        plt.title("Small vs Large Country Product Gini Over Time")
        plt.tight_layout()
        plt.savefig(EX01_FIGURES / "small_vs_large_country_product_gini.png", dpi=200)
        plt.close()


def fetch_world_bank_gdp(iso3s: list[str], start: int, end: int) -> pd.DataFrame:
    rows = []
    for iso3 in iso3s:
        url = f"https://api.worldbank.org/v2/country/{iso3}/indicator/NY.GDP.MKTP.CD"
        params = {"format": "json", "per_page": 20000, "date": f"{start}:{end}"}
        try:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code != 200:
                continue
            payload = resp.json()
            if not isinstance(payload, list) or len(payload) < 2:
                continue
            for item in payload[1]:
                rows.append({"iso3": iso3, "year": int(item["date"]), "gdp_current_usd": item["value"]})
        except Exception:
            continue
    out = pd.DataFrame(rows)
    if not out.empty:
        out.to_csv(WORLD_BANK_RAW / "gdp_current_usd.csv", index=False)
    return out


def write_exercise_01_memo(df: pd.DataFrame) -> None:
    summary = df.groupby("flow")[["product_gini", "partner_gini", "product_partner_cell_gini"]].median().round(3)
    latest_year = int(df["year"].max())
    latest = df[df["year"] == latest_year].groupby("flow")[["product_gini", "partner_gini"]].median().round(3)
    memo = f"""# Exercise 1: Aggregate Persistence

Generated: {now_utc()}

This memo is intentionally descriptive. `exercises.md` should only be updated after discussion.

## Coverage

- Countries in Prof P-style panel: {df["country"].nunique()}
- Years covered in processed data: {int(df["year"].min())}-{int(df["year"].max())}
- Country-year-flow rows: {len(df)}

## Median Concentration Across All Available Years

{summary.to_markdown()}

## Median Concentration In Latest Available Year ({latest_year})

{latest.to_markdown()}

## Files

- Tables: `results/exercise_01_tables/`
- Figures: `results/exercise_01_figures/`
- Processed data: `data/processed/concentration_all_years.parquet`

## Discussion Prompt

Does the aggregate puzzle still look real across years, or does it look driven by the original 2001 sample choice?
"""
    write_text(RESULTS / "exercise_01_aggregate_persistence.md", memo)


def run_exercise_06(leaf: pd.DataFrame) -> pd.DataFrame:
    outputs = []
    removal_rows = []
    base_totals = leaf.groupby(["reporter_code", "year", "flow"], as_index=False)["trade_value"].sum().rename(
        columns={"trade_value": "baseline_total_trade_value"}
    )
    for variant, excluded_hs2 in EXCLUSION_SETS.items():
        if excluded_hs2:
            sub = leaf[~leaf["hs2"].isin(excluded_hs2)].copy()
        else:
            sub = leaf.copy()
        product, partner, cell = compute_concentration(sub, variant)
        combined = product.merge(
            partner.drop(columns=["total_trade_value"]),
            on=["country", "iso3", "reporter_code", "year", "flow", "variant"],
            how="outer",
        ).merge(
            cell.drop(columns=["total_trade_value"]),
            on=["country", "iso3", "reporter_code", "year", "flow", "variant"],
            how="outer",
        )
        combined = combined.merge(base_totals, on=["reporter_code", "year", "flow"], how="left")
        combined["trade_share_removed"] = 1 - (combined["total_trade_value"] / combined["baseline_total_trade_value"])
        outputs.append(combined)

    category_values = leaf[leaf["hs2"].isin(EXCLUSION_LABELS)].copy()
    if not category_values.empty:
        category_values["exclusion_category"] = category_values["hs2"].map(EXCLUSION_LABELS)
        cat = category_values.groupby(["reporter_code", "year", "flow", "exclusion_category"], as_index=False)["trade_value"].sum()
        cat = cat.merge(base_totals, on=["reporter_code", "year", "flow"], how="left")
        cat["trade_share"] = cat["trade_value"] / cat["baseline_total_trade_value"]
        panel = save_country_panel()
        cat = cat.merge(panel, on="reporter_code", how="left")
        removal_rows.append(cat)

    out = pd.concat(outputs, ignore_index=True)
    out.to_parquet(DATA_PROCESSED / "concentration_exclusions_all_years.parquet", index=False)
    out.to_csv(EX06_TABLES / "concentration_exclusions_all_years.csv", index=False)
    if removal_rows:
        removed = pd.concat(removal_rows, ignore_index=True)
        removed.to_csv(EX06_TABLES / "trade_share_removed_by_category.csv", index=False)
    make_exercise_06_figures(out)
    write_exercise_06_memo(out)
    return out


def make_exercise_06_figures(df: pd.DataFrame) -> None:
    import matplotlib.pyplot as plt
    import seaborn as sns

    sns.set_theme(style="whitegrid")
    med = df.groupby(["year", "flow", "variant"], as_index=False)["product_gini"].median()
    plt.figure(figsize=(12, 7))
    sns.lineplot(data=med, x="year", y="product_gini", hue="variant", style="flow", errorbar=None)
    plt.title("Product Gini Before/After Exclusions")
    plt.tight_layout()
    plt.savefig(EX06_FIGURES / "before_after_product_gini_over_time.png", dpi=200)
    plt.close()

    baseline = df[df["variant"] == "baseline"][
        ["country", "iso3", "reporter_code", "year", "flow", "product_gini"]
    ].rename(columns={"product_gini": "baseline_product_gini"})
    full = df[df["variant"] == "full_exclusion"].merge(
        baseline, on=["country", "iso3", "reporter_code", "year", "flow"], how="left"
    )
    full["gini_change"] = full["product_gini"] - full["baseline_product_gini"]
    pivot = full.pivot_table(index="country", columns="year", values="gini_change", aggfunc="mean")
    plt.figure(figsize=(14, 10))
    sns.heatmap(pivot, cmap="vlag", center=0)
    plt.title("Product Gini Change After Full Exclusion")
    plt.tight_layout()
    plt.savefig(EX06_FIGURES / "full_exclusion_gini_change_heatmap.png", dpi=200)
    plt.close()

    latest = full[full["year"] == full["year"].max()].sort_values("product_gini", ascending=False).head(20)
    plt.figure(figsize=(10, 7))
    sns.barplot(data=latest, y="country", x="product_gini", hue="flow")
    plt.title("Highest Product Gini After Full Exclusion: Latest Year")
    plt.tight_layout()
    plt.savefig(EX06_FIGURES / "highest_persistent_concentration_latest_year.png", dpi=200)
    plt.close()

    plt.figure(figsize=(12, 7))
    sns.lineplot(
        data=df[df["variant"] != "baseline"],
        x="year",
        y="trade_share_removed",
        hue="variant",
        style="flow",
        estimator="median",
        errorbar=None,
    )
    plt.title("Median Trade Share Removed By Exclusion Variant")
    plt.tight_layout()
    plt.savefig(EX06_FIGURES / "trade_share_removed_over_time.png", dpi=200)
    plt.close()


def write_exercise_06_memo(df: pd.DataFrame) -> None:
    med = df.groupby(["flow", "variant"])[["product_gini", "trade_share_removed"]].median().round(3)
    memo = f"""# Exercise 6: High-Unit-Value / Oil Exclusion Tests

Generated: {now_utc()}

This memo is intentionally descriptive. `exercises.md` should only be updated after discussion.

## Median Product Gini And Trade Share Removed

{med.to_markdown()}

## Files

- Tables: `results/exercise_06_tables/`
- Figures: `results/exercise_06_figures/`
- Processed data: `data/processed/concentration_exclusions_all_years.parquet`

## Discussion Prompt

Are oil and high-unit-value categories only partial explanations, or do they explain most of the modern concentration pattern?
"""
    write_text(RESULTS / "exercise_06_exclusion_tests.md", memo)


def product_totals_for_benchmark(leaf: pd.DataFrame) -> pd.DataFrame:
    panel = save_country_panel()
    out = leaf.groupby(["reporter_code", "year", "flow", "cmd_code", "hs2"], as_index=False)["trade_value"].sum()
    out = out.merge(panel, on="reporter_code", how="left")
    return out


def empirical_pool(product_totals: pd.DataFrame) -> dict[tuple[int | str, str, str], np.ndarray]:
    pools = {}
    totals = product_totals.groupby(["year", "flow", "hs2", "reporter_code"], as_index=False)["trade_value"].sum()
    values = product_totals.merge(
        totals.rename(columns={"trade_value": "sector_country_total"}),
        on=["year", "flow", "hs2", "reporter_code"],
        how="left",
    )
    values["within_sector_share"] = values["trade_value"] / values["sector_country_total"]
    for key, group in values.groupby(["year", "flow", "hs2"]):
        arr = group["within_sector_share"].replace([np.inf, -np.inf], np.nan).dropna().to_numpy(dtype=float)
        arr = arr[arr > 0]
        if arr.size:
            pools[key] = arr
    for key, group in values.groupby(["flow", "hs2"]):
        arr = group["within_sector_share"].replace([np.inf, -np.inf], np.nan).dropna().to_numpy(dtype=float)
        arr = arr[arr > 0]
        if arr.size:
            pools[("all_years", key[0], key[1])] = arr
    return pools


def simulate_benchmark_for_group(group: pd.DataFrame, pools: dict, simulations: int, rng: np.random.Generator) -> pd.DataFrame:
    year = int(group["year"].iloc[0])
    flow = group["flow"].iloc[0]
    country = group["country"].iloc[0]
    iso3 = group["iso3"].iloc[0]
    reporter_code = int(group["reporter_code"].iloc[0])
    actual_values = group["trade_value"].to_numpy(dtype=float)
    actual = {
        "country": country,
        "iso3": iso3,
        "reporter_code": reporter_code,
        "year": year,
        "flow": flow,
        "actual_product_gini": gini(actual_values),
        "actual_product_top_1pct_share": top_share(actual_values, pct=0.01),
        "actual_product_top_5pct_share": top_share(actual_values, pct=0.05),
        "active_products": int(group["cmd_code"].nunique()),
        "total_trade_value": float(group["trade_value"].sum()),
    }
    sectors = []
    for hs2, sector in group.groupby("hs2"):
        k = int(sector["cmd_code"].nunique())
        total = float(sector["trade_value"].sum())
        if k > 0 and total > 0:
            sectors.append((hs2, k, total))

    sim_gini = np.empty(simulations)
    sim_top1 = np.empty(simulations)
    sim_top5 = np.empty(simulations)
    for i in range(simulations):
        simulated_values = []
        for hs2, k, total in sectors:
            pool = pools.get((year, flow, hs2))
            if pool is None or pool.size == 0:
                pool = pools.get(("all_years", flow, hs2))
            if pool is None or pool.size == 0:
                weights = np.ones(k, dtype=float)
            else:
                weights = rng.choice(pool, size=k, replace=True)
            if not np.isfinite(weights).all() or weights.sum() <= 0:
                weights = np.ones(k, dtype=float)
            values = total * weights / weights.sum()
            simulated_values.append(values)
        arr = np.concatenate(simulated_values) if simulated_values else np.array([], dtype=float)
        sim_gini[i] = gini(arr)
        sim_top1[i] = top_share(arr, pct=0.01)
        sim_top5[i] = top_share(arr, pct=0.05)

    return pd.DataFrame(
        [
            {
                **actual,
                "simulations": simulations,
                "sim_product_gini_median": float(np.nanmedian(sim_gini)),
                "sim_product_gini_p05": float(np.nanpercentile(sim_gini, 5)),
                "sim_product_gini_p95": float(np.nanpercentile(sim_gini, 95)),
                "actual_product_gini_percentile": float(np.mean(sim_gini <= actual["actual_product_gini"])),
                "actual_minus_sim_median_product_gini": float(actual["actual_product_gini"] - np.nanmedian(sim_gini)),
                "sim_product_top_1pct_share_median": float(np.nanmedian(sim_top1)),
                "actual_top_1pct_percentile": float(np.mean(sim_top1 <= actual["actual_product_top_1pct_share"])),
                "sim_product_top_5pct_share_median": float(np.nanmedian(sim_top5)),
                "actual_top_5pct_percentile": float(np.mean(sim_top5 <= actual["actual_product_top_5pct_share"])),
            }
        ]
    )


def run_exercise_10(leaf: pd.DataFrame, simulations: int, seed: int) -> pd.DataFrame:
    product_totals = product_totals_for_benchmark(leaf)
    product_totals.to_parquet(DATA_PROCESSED / "product_totals_for_random_benchmark.parquet", index=False)
    return run_exercise_10_from_product_totals(product_totals, simulations, seed)


def run_exercise_10_from_product_totals(product_totals: pd.DataFrame, simulations: int, seed: int) -> pd.DataFrame:
    pools = empirical_pool(product_totals)
    rng = np.random.default_rng(seed)
    rows = []
    for key, group in product_totals.groupby(["reporter_code", "year", "flow"], sort=True):
        print(f"Simulating benchmark: reporter={key[0]} year={key[1]} flow={key[2]}", flush=True)
        rows.append(simulate_benchmark_for_group(group, pools, simulations, rng))
    out = pd.concat(rows, ignore_index=True)
    out.to_parquet(DATA_PROCESSED / "random_benchmark_all_years.parquet", index=False)
    out.to_csv(EX10_TABLES / "random_benchmark_all_years.csv", index=False)
    make_exercise_10_figures(out)
    write_exercise_10_memo(out)
    validate_benchmark(out, product_totals, seed, simulations)
    return out


def make_exercise_10_figures(df: pd.DataFrame) -> None:
    import matplotlib.pyplot as plt
    import seaborn as sns

    sns.set_theme(style="whitegrid")
    med = df.groupby(["year", "flow"], as_index=False)[["actual_product_gini", "sim_product_gini_median"]].median()
    long = med.melt(id_vars=["year", "flow"], var_name="series", value_name="product_gini")
    plt.figure(figsize=(11, 6))
    sns.lineplot(data=long, x="year", y="product_gini", hue="series", style="flow", errorbar=None)
    plt.title("Actual vs Simulated Median Product Gini")
    plt.tight_layout()
    plt.savefig(EX10_FIGURES / "actual_vs_simulated_product_gini_over_time.png", dpi=200)
    plt.close()

    pct = df.groupby(["year", "flow"], as_index=False)["actual_product_gini_percentile"].median()
    plt.figure(figsize=(11, 6))
    sns.lineplot(data=pct, x="year", y="actual_product_gini_percentile", hue="flow", errorbar=None)
    plt.axhline(0.95, color="black", linestyle="--", linewidth=1)
    plt.title("Actual Product Gini Percentile In Real-Data Benchmark")
    plt.tight_layout()
    plt.savefig(EX10_FIGURES / "actual_gini_percentile_over_time.png", dpi=200)
    plt.close()

    share95 = df.assign(above_95=df["actual_product_gini_percentile"] >= 0.95).groupby(
        ["year", "flow"], as_index=False
    )["above_95"].mean()
    plt.figure(figsize=(11, 6))
    sns.lineplot(data=share95, x="year", y="above_95", hue="flow", errorbar=None)
    plt.title("Share Of Country-Years Above 95th Benchmark Percentile")
    plt.tight_layout()
    plt.savefig(EX10_FIGURES / "share_above_95th_percentile_over_time.png", dpi=200)
    plt.close()

    countries = sorted(df["country"].dropna().unique())
    ncols = 3
    nrows = math.ceil(len(countries) / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(15, max(8, nrows * 2.2)), sharex=True, sharey=True)
    axes = np.asarray(axes).reshape(-1)
    for ax, country in zip(axes, countries):
        sub = df[df["country"] == country]
        sns.lineplot(data=sub, x="year", y="actual_minus_sim_median_product_gini", hue="flow", ax=ax, legend=False)
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_title(country, fontsize=9)
        ax.set_xlabel("")
        ax.set_ylabel("")
    for ax in axes[len(countries):]:
        ax.axis("off")
    fig.suptitle("Actual Minus Benchmark Product Gini")
    fig.tight_layout()
    fig.savefig(EX10_FIGURES / "country_actual_minus_benchmark_lines.png", dpi=200)
    plt.close(fig)


def write_exercise_10_memo(df: pd.DataFrame) -> None:
    med = df.groupby("flow")[
        ["actual_product_gini", "sim_product_gini_median", "actual_minus_sim_median_product_gini", "actual_product_gini_percentile"]
    ].median().round(3)
    share95 = df.assign(above_95=df["actual_product_gini_percentile"] >= 0.95).groupby("flow")["above_95"].mean().round(3)
    memo = f"""# Exercise 10: Real-Data Random Benchmark

Generated: {now_utc()}

This memo is intentionally descriptive. `exercises.md` should only be updated after discussion.

## Median Actual Versus Benchmark Measures

{med.to_markdown()}

## Share Of Country-Year-Flow Observations Above 95th Benchmark Percentile

{share95.to_markdown()}

## Benchmark Design

- Preserves country-year-flow total trade.
- Preserves HS2 sector totals.
- Preserves number of active HS6 products within each HS2 sector.
- Draws within-sector product shares from empirical real-data pools, not arbitrary invented distributions.
- Does not use naive relabeling, because relabeling preserves the same Gini by construction.

## Files

- Tables: `results/exercise_10_tables/`
- Figures: `results/exercise_10_figures/`
- Processed data: `data/processed/random_benchmark_all_years.parquet`

## Discussion Prompt

Is actual concentration still unusually high after preserving broad sector structure, or is much of it explained by broad comparative advantage?
"""
    write_text(RESULTS / "exercise_10_random_benchmark.md", memo)


def validate_benchmark(out: pd.DataFrame, product_totals: pd.DataFrame, seed: int, simulations: int) -> None:
    check = {
        "created_at_utc": now_utc(),
        "seed": seed,
        "simulations": simulations,
        "rows": int(len(out)),
        "actual_gini_percentile_min": float(out["actual_product_gini_percentile"].min()),
        "actual_gini_percentile_max": float(out["actual_product_gini_percentile"].max()),
        "product_totals_rows": int(len(product_totals)),
        "policy": "Benchmark simulations use real-data empirical share pools and preserve HS2 totals.",
    }
    write_json(EX10_TABLES / "benchmark_validation.json", check)


def run_all(args: argparse.Namespace) -> None:
    ensure_dirs()
    save_country_panel()
    subscription_key = get_key(args)
    if args.stage in {"download", "all"}:
        if not check_comtrade_access(subscription_key):
            return
        availability = download_availability(subscription_key)
        download_bulk_files(
            subscription_key,
            availability,
            max_years=args.max_years_per_country,
            workers=args.download_workers,
            max_file_mb=args.max_file_mb,
            min_file_mb=args.min_file_mb,
        )

    if args.stage in {"process", "all"}:
        if args.keep_leaf:
            leaf_path = DATA_PROCESSED / "hs6_partner_leaf_trade_all_years.parquet"
            if leaf_path.exists() and not args.reprocess_raw:
                leaf = pd.read_parquet(leaf_path)
            else:
                leaf = collect_leaf_data()
            concentration = run_exercise_01(leaf)
            run_exercise_06(leaf)
            run_exercise_10(leaf, simulations=args.simulations, seed=args.seed)
            write_json(
                RESULTS / "run_manifest.json",
                {
                    "created_at_utc": now_utc(),
                    "stage": args.stage,
                    "mode": "in_memory_leaf",
                    "rows_leaf_trade": int(len(leaf)),
                    "rows_concentration": int(len(concentration)),
                    "simulations": args.simulations,
                    "seed": args.seed,
                    "exercises_md_updated": False,
                },
            )
        else:
            run_exercises_streaming(simulations=args.simulations, seed=args.seed)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run real-data trade concentration Exercises 1, 6, and 10.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--stage", choices=["download", "process", "all"], default="all")
    parser.add_argument("--subscription-key", default=None, help="UN Comtrade subscription key. Defaults to COMTRADE_SUBSCRIPTION_KEY.")
    parser.add_argument("--simulations", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260518)
    parser.add_argument("--max-years-per-country", type=int, default=None, help="Debug option; leave unset for all available years.")
    parser.add_argument("--download-workers", type=int, default=4, help="Parallel Comtrade bulk downloads.")
    parser.add_argument("--max-file-mb", type=float, default=None, help="Download only files at or below this advertised size.")
    parser.add_argument("--min-file-mb", type=float, default=None, help="Download only files at or above this advertised size.")
    parser.add_argument("--reprocess-raw", action="store_true", help="Re-read raw Comtrade files even if processed parquet exists.")
    parser.add_argument("--keep-leaf", action="store_true", help="Store all HS6 partner records in one parquet; off by default to avoid high memory use.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    run_all(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
