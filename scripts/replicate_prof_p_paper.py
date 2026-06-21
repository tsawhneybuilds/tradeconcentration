#!/usr/bin/env python3
"""Replication inventory for Panagariya and Bagaria trade concentration facts.

The script compares paper-reported 2001 targets against the repository's current
UN Comtrade HS6 pipeline outputs. It deliberately marks US HS10 targets as
blocked unless the Center for International Data source files are made available
locally; the HS6 reruns are not used as substitutes for HS10 paper objects.
"""

from __future__ import annotations

import argparse
import ctypes
import csv
import gc
import gzip
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow.dataset as ds
import requests

from concentration_metrics import active_gini, active_top_share


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
RESULTS = ROOT / "results"
OUT = RESULTS / "prof_p_replication"
TABLES = OUT / "tables"
FIGURES = OUT / "figures"
HS10_DIR = RAW / "cid_us_hs10"
SOURCE_DIR = OUT / "sources"
PROF_P_TOP_SHARE_TABLE = TABLES / "prof_p_2001_hs6_top_shares_vs_table2.csv"
PROF_P_LORENZ_TABLE = TABLES / "prof_p_2001_lorenz_india_china_us.csv"
PARTNER_TOTALCMD_DIAGNOSTIC_TABLE = TABLES / "partner_totalcmd_2001_diagnostic.csv"
PARTNER_WORLD_DENOM_DETAIL_TABLE = TABLES / "partner_world_denominator_metrics_detail.csv"
PARTNER_WORLD_DENOM_SUMMARY_TABLE = TABLES / "partner_world_denominator_metrics_summary.csv"
RAW_HS6_CACHE_MAX_ITEMS = max(0, int(os.environ.get("PROF_P_RAW_HS6_CACHE_MAX_ITEMS", "4")))

PAPER_PDF = ROOT / "prof p with nitika.pdf"
CONCENTRATION_PATH = PROCESSED / "concentration_all_years.parquet"
EXPORT_AGG_PATH = PROCESSED / "exercise_12_export_aggregates.parquet"
IMPORT_AGG_DIR = PROCESSED / "exercise_04_file_aggregates"
COUNTRY_PANEL_PATH = PROCESSED / "prof_p_country_panel.csv"
PARTNER_REF_PATH = RAW / "comtrade" / "partner_reference.csv"
CLASSIFICATION_DIR = RAW / "classifications"

SOURCES = {
    "paper_pdf": str(PAPER_PDF),
    "lse_metadata": "https://researchonline.lse.ac.uk/49167/",
    "uc_davis_cid": "https://cid.ucdavis.edu/usixd",
    "nber_w9387": "https://www.nber.org/papers/w9387",
    "un_comtrade": "https://comtradeplus.un.org/",
    "wco_hs1996_2002_correlation": (
        "https://www.wcoomd.org/-/media/wco/public/global/pdf/topics/nomenclature/"
        "instruments-and-tools/hs-nomenclature-older-edition/2002/"
        "correlations-1996-2002/hs_correlation2002_table2_eng.pdf?la=en"
    ),
}

COUNTRY_TO_REPORTER = {
    "Australia": 36,
    "Austria": 40,
    "Belgium": 56,
    "Brazil": 76,
    "Canada": 124,
    "China": 156,
    "Czech Republic": 203,
    "Denmark": 208,
    "Finland": 246,
    "France": 251,
    "Germany": 276,
    "Greece": 300,
    "Hungary": 348,
    "Iceland": 352,
    "India": 699,
    "Ireland": 372,
    "Italy": 380,
    "Japan": 392,
    "Korea": 410,
    "Luxembourg": 442,
    "Mexico": 484,
    "Netherlands": 528,
    "New Zealand": 554,
    "Norway": 579,
    "Poland": 616,
    "Russia": 643,
    "Slovakia": 703,
    "Spain": 724,
    "Sweden": 752,
    "Switzerland": 757,
    "Turkey": 792,
    "United Kingdom": 826,
    "United States": 842,
}

APPENDIX_COUNTRIES = {
    "United States": 842,
    "Germany": 276,
    "Japan": 392,
    "China": 156,
    "India": 699,
}

US_PARTNERS = {
    "Canada": 124,
    "Mexico": 484,
    "Japan": 392,
}


@dataclass
class InventoryRow:
    target_id: str
    target_type: str
    source_section: str
    required_data: str
    paper_value: str
    reproduced_value: str
    difference: str
    status: str
    caveat: str
    output_path: str


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rel(path: Path | str | None) -> str:
    if path is None:
        return ""
    path = Path(path)
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_dirs() -> None:
    TABLES.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    HS10_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)


def release_memory_to_os() -> None:
    gc.collect()
    if sys.platform != "darwin":
        return
    try:
        libc = ctypes.CDLL("libc.dylib")
        relief = libc.malloc_zone_pressure_relief
        relief.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        relief.restype = ctypes.c_size_t
        relief(None, 0)
    except Exception:
        return


def norm_hs6(value: object) -> str:
    match = re.search(r"(\d{1,6})", str(value))
    return match.group(1).zfill(6) if match else ""


def normalize_hs6_series(series: pd.Series) -> pd.Series:
    return series.astype(str).str.extract(r"(\d{1,6})", expand=False).str.zfill(6)


def drop_999999(df: pd.DataFrame, code_col: str = "cmd_code") -> pd.DataFrame:
    if df.empty or code_col not in df.columns:
        return df
    codes = normalize_hs6_series(df[code_col])
    out = df.loc[~codes.eq("999999")].copy()
    if code_col in out.columns:
        out[code_col] = normalize_hs6_series(out[code_col])
    return out


def assert_no_999999(df: pd.DataFrame, code_col: str, label: str) -> None:
    if code_col not in df.columns:
        return
    count = int(normalize_hs6_series(df[code_col]).eq("999999").sum())
    if count:
        raise RuntimeError(f"{label} contains {count} HS6 999999 rows")


def gini(values: Iterable[float]) -> float:
    """Backward-compatible alias for active-positive Gini."""
    return active_gini(values)


def top_n_share(values: Iterable[float], n: int) -> float:
    """Backward-compatible alias for active-positive top shares."""
    return active_top_share(values, n=n)


def top_pct_cutoff(active_count: int, pct: float) -> int:
    if active_count <= 0:
        return 0
    return max(1, int(math.ceil(active_count * pct)))


def bottom_half_share(values: Iterable[float]) -> float:
    arr = np.asarray(list(values), dtype=float)
    arr = arr[np.isfinite(arr) & (arr > 0)]
    if arr.size == 0:
        return float("nan")
    arr.sort()
    n = int(math.floor(arr.size * 0.5))
    if n <= 0:
        return 0.0
    return float(arr[:n].sum() / arr.sum())


def lorenz_points(values: Iterable[float]) -> pd.DataFrame:
    arr = np.asarray(list(values), dtype=float)
    arr = arr[np.isfinite(arr) & (arr > 0)]
    if arr.size == 0:
        return pd.DataFrame({"cum_items": [0.0], "cum_value": [0.0]})
    arr.sort()
    cum_value = np.concatenate([[0.0], np.cumsum(arr) / arr.sum()])
    cum_items = np.linspace(0, 1, arr.size + 1)
    return pd.DataFrame({"cum_items": cum_items, "cum_value": cum_value})


def status_from_diff(max_abs_diff: float, close_tol: float, exact_tol: float = 1e-12) -> str:
    if not np.isfinite(max_abs_diff):
        return "blocked"
    if max_abs_diff <= exact_tol:
        return "exact_match"
    if max_abs_diff <= close_tol:
        return "close"
    return "mismatch"


def first_existing_import_file(reporter_code: int, year: int) -> Path:
    pattern = f"*CA{reporter_code:03d}{year}H*.parquet"
    matches = sorted(IMPORT_AGG_DIR.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"No import aggregate file matching {pattern}")
    return matches[0]


def read_import_cells(reporter_code: int, year: int) -> pd.DataFrame:
    path = first_existing_import_file(reporter_code, year)
    df = pd.read_parquet(path, columns=["reporter_code", "year", "cmd_code", "partner_code", "trade_value"])
    df = drop_999999(df, "cmd_code")
    assert_no_999999(df, "cmd_code", rel(path))
    df["reporter_code"] = df["reporter_code"].astype(int)
    df["year"] = df["year"].astype(int)
    df["partner_code"] = pd.to_numeric(df["partner_code"], errors="coerce").astype("Int64")
    df["trade_value"] = pd.to_numeric(df["trade_value"], errors="coerce")
    return df.dropna(subset=["partner_code", "trade_value"])


def read_export_dimension(reporter_code: int, year: int, dimension: str) -> pd.DataFrame:
    dataset = ds.dataset(EXPORT_AGG_PATH, format="parquet")
    columns = ["reporter_code", "year", "classification_code", "cmd_code", "partner_code", "trade_value", "dimension"]
    filt = (
        (ds.field("reporter_code") == reporter_code)
        & (ds.field("year") == year)
        & (ds.field("dimension") == dimension)
    )
    df = dataset.to_table(columns=columns, filter=filt).to_pandas()
    df = drop_999999(df, "cmd_code")
    assert_no_999999(df, "cmd_code", f"{rel(EXPORT_AGG_PATH)} {reporter_code}-{year}-{dimension}")
    df["reporter_code"] = df["reporter_code"].astype(int)
    df["year"] = df["year"].astype(int)
    if "partner_code" in df.columns:
        df["partner_code"] = pd.to_numeric(df["partner_code"], errors="coerce").astype("Int64")
    df["trade_value"] = pd.to_numeric(df["trade_value"], errors="coerce")
    return df.dropna(subset=["trade_value"])


def load_partner_lookup() -> dict[int, str]:
    ref = pd.read_csv(PARTNER_REF_PATH)
    ref["partner_code"] = pd.to_numeric(ref["partner_code"], errors="coerce").astype("Int64")
    ref = ref.dropna(subset=["partner_code"])
    return {int(row.partner_code): str(row.partner_name) for row in ref.itertuples(index=False)}


def load_product_lookup() -> dict[str, str]:
    lookup: dict[str, str] = {}
    for class_code in ["H0", "H1", "H2", "H3", "H4", "H5", "H6"]:
        path = CLASSIFICATION_DIR / f"{class_code}.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        for row in data.get("results", []):
            code = str(row.get("id", ""))
            if not code.isdigit() or len(code) != 6:
                continue
            text = str(row.get("text", "")).strip()
            text = text.split(" - ", 1)[1] if " - " in text else text
            if text:
                lookup[code.zfill(6)] = " ".join(text.split())
    return lookup


def load_product_lookup_for_revision(class_code: str) -> dict[str, str]:
    path = CLASSIFICATION_DIR / f"{class_code}.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    lookup: dict[str, str] = {}
    for row in data.get("results", []):
        code = str(row.get("id", ""))
        if not code.isdigit() or len(code) != 6:
            continue
        text = str(row.get("text", "")).strip()
        text = text.split(" - ", 1)[1] if " - " in text else text
        if text:
            lookup[code.zfill(6)] = " ".join(text.split())
    return lookup


def product_label(code: object, lookup: dict[str, str]) -> str:
    norm = norm_hs6(code)
    return lookup.get(norm, norm)


def write_csv(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return path


def table_to_markdown(df: pd.DataFrame, max_rows: int = 12) -> str:
    if df.empty:
        return "_No rows._"
    shown = df.head(max_rows).copy()
    return shown.to_markdown(index=False)


PAPER_TABLE_2 = pd.DataFrame(
    [
        ("Australia", 0.945, 4596, 0.849, 4738),
        ("Austria", 0.881, 4484, 0.820, 4857),
        ("Belgium", 0.864, 4799, 0.837, 4896),
        ("Brazil", 0.930, 4305, 0.871, 4641),
        ("Canada", 0.922, 4663, 0.842, 4931),
        ("China", 0.848, 4792, 0.875, 4832),
        ("Czech Republic", 0.867, 4662, 0.828, 4861),
        ("Denmark", 0.889, 4390, 0.813, 4758),
        ("Finland", 0.935, 4377, 0.848, 4756),
        ("France", 0.845, 4745, 0.805, 4936),
        ("Germany", 0.835, 4775, 0.833, 4912),
        ("Greece", 0.920, 3930, 0.859, 4751),
        ("Hungary", 0.897, 3353, 0.854, 4358),
        ("Iceland", 0.981, 1355, 0.859, 4096),
        ("India", 0.904, 4592, 0.925, 4504),
        ("Ireland", 0.966, 3748, 0.894, 4732),
        ("Italy", 0.821, 4793, 0.825, 4914),
        ("Japan", 0.908, 4570, 0.878, 4841),
        ("Korea", 0.918, 4354, 0.886, 4803),
        ("Luxembourg", 0.953, 3364, 0.886, 4528),
        ("Mexico", 0.929, 4398, 0.855, 4788),
        ("Netherlands", 0.867, 4690, 0.847, 4828),
        ("New Zealand", 0.945, 3883, 0.838, 4582),
        ("Norway", 0.973, 3868, 0.839, 4748),
        ("Poland", 0.843, 3116, 0.798, 4159),
        ("Russia", 0.971, 4362, 0.855, 4717),
        ("Slovakia", 0.915, 4140, 0.846, 4726),
        ("Spain", 0.850, 4809, 0.820, 4895),
        ("Sweden", 0.901, 4627, 0.840, 4833),
        ("Switzerland", 0.895, 4621, 0.836, 4893),
        ("Turkey", 0.901, 4389, 0.869, 4577),
        ("United Kingdom", 0.880, 4810, 0.843, 4878),
        ("United States", 0.848, 4921, 0.871, 4940),
    ],
    columns=["country", "paper_export_product_gini", "paper_export_products", "paper_import_product_gini", "paper_import_products"],
)

PAPER_TABLE_3 = pd.DataFrame(
    [
        ("Australia", 0.901, 215, 48.9),
        ("Austria", 0.910, 203, 56.6),
        ("Belgium", 0.919, 217, 63.5),
        ("Brazil", 0.872, 206, 45.9),
        ("Canada", 0.979, 213, 92.1),
        ("China", 0.903, 208, 63.2),
        ("Czech Republic", 0.925, 195, 62.6),
        ("Denmark", 0.909, 226, 51.7),
        ("Finland", 0.934, 205, 69.6),
        ("France", 0.882, 224, 51.4),
        ("Germany", 0.888, 227, 42.5),
        ("Greece", 0.924, 209, 66.6),
        ("Hungary", 0.920, 182, 60.7),
        ("Iceland", 0.883, 103, 60.1),
        ("India", 0.920, 212, 67.8),
        ("Ireland", 0.931, 203, 64.5),
        ("Italy", 0.866, 217, 49.3),
        ("Japan", 0.916, 214, 56.1),
        ("Korea", 0.887, 219, 54.1),
        ("Luxembourg", 0.928, 180, 69.8),
        ("Mexico", 0.976, 181, 91.7),
        ("Netherlands", 0.924, 231, 65.1),
        ("New Zealand", 0.891, 193, 55.4),
        ("Norway", 0.929, 202, 59.5),
        ("Poland", 0.893, 170, 55.0),
        ("Russia", 0.842, 175, 32.8),
        ("Slovakia", 0.933, 182, 66.5),
        ("Spain", 0.891, 210, 59.6),
        ("Sweden", 0.895, 212, 45.1),
        ("Switzerland", 0.907, 227, 55.8),
        ("Turkey", 0.861, 193, 47.6),
        ("United Kingdom", 0.901, 226, 53.1),
        ("United States", 0.901, 221, 53.9),
    ],
    columns=["country", "paper_export_partner_gini", "paper_export_partners", "paper_export_top5_partner_share_pct"],
)

PAPER_TABLE_4 = pd.DataFrame(
    [
        ("Australia", 0.912, 199, 51.2),
        ("Austria", 0.924, 210, 60.6),
        ("Belgium", 0.908, 197, 61.6),
        ("Brazil", 0.891, 190, 52.8),
        ("Canada", 0.955, 210, 78.5),
        ("China", 0.897, 185, 54.8),
        ("Czech Republic", 0.921, 210, 53.8),
        ("Denmark", 0.913, 204, 53.8),
        ("Finland", 0.889, 172, 47.3),
        ("France", 0.896, 228, 48.9),
        ("Germany", 0.886, 226, 37.8),
        ("Greece", 0.868, 178, 43.6),
        ("Hungary", 0.903, 178, 51.9),
        ("Iceland", 0.855, 124, 47.2),
        ("India", 0.889, 178, 51.1),
        ("Ireland", 0.936, 213, 65.3),
        ("Italy", 0.876, 206, 44.9),
        ("Japan", 0.903, 206, 48.1),
        ("Korea", 0.910, 212, 53.8),
        ("Luxembourg", 0.950, 135, 82.1),
        ("Mexico", 0.960, 194, 81.1),
        ("Netherlands", 0.899, 214, 52.2),
        ("New Zealand", 0.901, 161, 60.8),
        ("Norway", 0.894, 178, 49.9),
        ("Poland", 0.883, 162, 52.0),
        ("Russia", 0.871, 189, 45.1),
        ("Slovakia", 0.959, 191, 80.4),
        ("Spain", 0.889, 209, 53.1),
        ("Sweden", 0.912, 191, 50.6),
        ("Switzerland", 0.962, 215, 78.2),
        ("Turkey", 0.923, 180, 68.7),
        ("United Kingdom", 0.891, 219, 44.9),
        ("United States", 0.902, 219, 55.3),
    ],
    columns=["country", "paper_import_partner_gini", "paper_import_partners", "paper_import_top5_partner_share_pct"],
)

PAPER_TABLE_1 = pd.DataFrame(
    [
        ("All exports", 1, 86, 36.3),
        ("All exports", 2, 171, 46.0),
        ("All exports", 5, 428, 61.4),
        ("All exports", 20, 1712, 85.8),
        ("All exports", 50, 4281, 97.3),
        ("All exports", 100, 8562, 100.0),
        ("Two-way traded exports", 1, 54, 29.73),
        ("Two-way traded exports", 2, 109, 40.11),
        ("Two-way traded exports", 5, 272, 56.73),
        ("Two-way traded exports", 20, 1089, 83.56),
        ("Two-way traded exports", 50, 2724, 96.94),
        ("Two-way traded exports", 100, 5447, 100.0),
        ("All imports", 1, 164, 49.22),
        ("All imports", 2, 328, 59.27),
        ("All imports", 5, 819, 73.32),
        ("All imports", 20, 3276, 92.17),
        ("All imports", 50, 8190, 99.05),
        ("All imports", 100, 16380, 100.0),
        ("Two-way traded imports", 1, 54, 45.67),
        ("Two-way traded imports", 2, 109, 55.20),
        ("Two-way traded imports", 5, 272, 68.77),
        ("Two-way traded imports", 20, 1089, 89.24),
        ("Two-way traded imports", 50, 2724, 98.31),
        ("Two-way traded imports", 100, 5447, 100.0),
    ],
    columns=["panel", "product_percent", "paper_absolute_products", "paper_trade_share_pct"],
)

PAPER_TABLE_1_GINIS = {
    "All exports": 0.8269,
    "Two-way traded exports": 0.8926,
    "All imports": 0.8926,
    "Two-way traded imports": 0.8656,
}

PAPER_TABLE_5_PRODUCTS = [
    ("854213", "metal oxide semiconductor", 153, 0.9146, {5: 49.2, 10: 80.3, 20: 96.4, 50: 99.9}),
    ("880240", "fixed wing aircraft, unladen weight >15,000 kg", 61, 0.6376, {5: 44.2, 10: 61.7, 20: 80.6, 50: 99.1}),
    ("847330", "parts and accessories of data processing equipment nes", 192, 0.9066, {5: 48.4, 10: 70.4, 20: 89.9, 50: 98.6}),
    ("880330", "aircraft parts nes", 181, 0.8914, {5: 47.0, 10: 68.0, 20: 85.5, 50: 98.5}),
]

PAPER_TABLE_6_PRODUCTS = [
    ("270900", "petroleum oils, oils from bituminous minerals, crude", 44, 0.7743, {5: 66.0, 10: 87.9, 20: 97.7}),
    ("870323", "automobiles, spark-ignition engine of 1,500-3,000 cc", 28, 0.8381, {5: 89.8, 10: 98.9, 20: 100.0}),
    ("870324", "automobiles, spark-ignition engine of >3,000 cc", 34, 0.8992, {5: 96.1, 10: 99.5, 20: 100.0}),
    ("271000", "petroleum oils and oils obta", 89, 0.7326, {5: 43.4, 10: 59.7, 20: 79.6, 50: 97.3}),
]

PAPER_TABLE_7 = pd.DataFrame(
    [
        ("Canada", 0.853, 4927, 58.43, 0.925, 4430, 73.14),
        ("Mexico", 0.876, 4883, 63.13, 0.935, 3565, 79.79),
        ("Japan", 0.895, 4510, 69.66, 0.932, 3843, 53.44),
    ],
    columns=[
        "partner",
        "paper_export_gini",
        "paper_export_products",
        "paper_export_top200_share_pct",
        "paper_import_gini",
        "paper_import_products",
        "paper_import_top200_share_pct",
    ],
)

APPENDIX_PAPER = {
    "A1": {
        "country": "United States",
        "flow": "Exports",
        "rows": [
            ("854213", "Metal oxide semiconductor", 26.48),
            ("880240", "Fixed wing aircraft, unladen weight >15,000 kg", 23.98),
            ("847330", "Parts and accessories of data processing equipment nes", 19.37),
            ("880330", "Aircraft parts nes", 13.52),
            ("870899", "Motor vehicle parts nes", 9.90),
            ("870829", "Parts and accessories of bodies nes for motor vehicles", 8.40),
            ("870323", "Automobiles, spark-ignition engine of 1,500-3,000 cc", 8.36),
            ("870324", "Automobiles, spark-ignition engine of >3,000 cc", 8.14),
            ("854230", "Monolithic integrated circuits", 7.56),
            ("847180", "Units of auto data process", 7.38),
            ("841191", "Parts of turbo-jet or turbo-propeller engines", 7.04),
            ("300490", "Medicaments nes, in dosage", 6.59),
            ("271000", "Petroleum oils and oils", 6.41),
            ("120100", "Soya beans", 5.45),
            ("840734", "Engines, spark-ignition reciprocating, over 1,000 cc", 5.42),
            ("851790", "Parts of line telephone/telegraph equipment, nes", 5.34),
            ("847989", "Machines and mechanical appliances nes", 5.14),
            ("847149", "Digital auto data process units", 4.74),
            ("852520", "Transmit-receive apparatus for radio, TV, etc.", 4.73),
            ("100590", "Maize except seed corn", 4.56),
            ("841112", "Turbo-jet engines of a thrust >25 KN", 4.36),
            ("852990", "Parts for radio/tv transmit/receive equipment, nes", 4.31),
            ("710812", "Gold in unwrought forms non-monetary", 4.19),
            ("901890", "Instruments, appliances for medical, etc. science, nes", 3.99),
            ("843143", "Parts of boring or sinking machinery", 3.98),
        ],
    },
    "A2": {
        "country": "Germany",
        "flow": "Exports",
        "rows": [
            ("870323", "Automobiles, spark-ignition engine of 1,500-3,000 cc", 30.38),
            ("870332", "Automobiles, diesel engine of 1,500-2,500 cc", 17.09),
            ("880240", "Fixed wing aircraft, unladen weight >15,000 kg", 13.46),
            ("870324", "Automobiles, spark-ignition engine of >3,000 cc", 13.25),
            ("300490", "Medicaments nes, in dosage", 11.50),
            ("852520", "Transmit-receive apparatus for radio, TV, etc.", 8.31),
            ("854213", "Metal oxide semiconductors", 5.78),
            ("847330", "Parts and accessories of data processing equipment nes", 5.23),
            ("870899", "Motor vehicle parts nes", 4.71),
            ("271000", "Petroleum oils and oils", 4.03),
            ("870322", "Automobiles, spark-ignition engine of 1,000-1,500 cc", 3.78),
            ("870829", "Parts and accessories of bodies nes for motor vehicles", 3.24),
            ("841112", "Turbo-jet engines of a thrust >25 KN", 2.98),
            ("880330", "Aircraft parts nes", 2.93),
            ("840999", "Parts for diesel and semi-diesel engines", 2.82),
            ("847989", "Machines and mechanical appliances nes", 2.76),
            ("870421", "Diesel powered trucks weighing <5 tonnes", 2.70),
            ("870333", "Automobiles, diesel engine of >2,500 cc", 2.62),
            ("844319", "Offset printing machinery nes", 2.60),
            ("870840", "Transmissions for motor vehicles", 2.50),
            ("847160", "I/O units w/n storage units", 2.41),
            ("271129", "Petroleum gases and gaseous hydrocarbons nes, as gas", 2.38),
            ("870120", "Road tractors for semi-trailers", 2.31),
            ("392690", "Plastic articles nes", 2.24),
            ("382490", "Chemical prep, allied", 2.19),
        ],
    },
    "A3": {
        "country": "Japan",
        "flow": "Exports",
        "rows": [
            ("870323", "Automobiles, spark-ignition engine of 1,500-3,000 cc", 31.65),
            ("854213", "Metal oxide semiconductor", 14.14),
            ("870324", "Automobiles, spark-ignition engine of >3,000 cc", 12.29),
            ("847330", "Parts and accessories of data processing equipment nes", 9.60),
            ("852540", "Still image video camera", 6.22),
            ("847989", "Machines and mechanical appliances nes", 5.84),
            ("890190", "Cargo vessels other than tanker or refrigerated", 5.81),
            ("870899", "Motor vehicle parts nes", 4.74),
            ("870840", "Transmissions for motor vehicles", 4.63),
            ("847150", "Digital process units", 3.95),
            ("847160", "I/O units w/n storage units", 3.77),
            ("870322", "Automobiles, spark-ignition engine of 1,000-1,500 cc", 3.69),
            ("854230", "Monolithic integrated circuits", 3.59),
            ("840991", "Parts for spark-ignition engines except aircraft", 3.37),
            ("852990", "Parts for radio/tv transmit/receive equipment, nes", 3.20),
            ("900990", "Parts and accessories for photocopying apparatus", 3.05),
            ("851790", "Parts of line telephone/telegraph equipment, nes", 2.97),
            ("847170", "Storage units", 2.81),
            ("870829", "Parts and accessories of bodies nes for motor vehicles", 2.78),
            ("854389", "Electrical machines", 2.36),
            ("890120", "Tankers", 2.36),
            ("840734", "Engines, spark-ignition reciprocating, over 1,000 cc", 2.30),
            ("870333", "Automobiles, diesel engine of >2,500 cc", 2.27),
            ("854290", "Parts of electronic integrated circuits etc.", 2.22),
            ("900912", "Electrostatic photocopiers, indirect process", 2.22),
        ],
    },
    "A4": {
        "country": "China",
        "flow": "Exports",
        "rows": [
            ("847330", "Parts and accessories of data processing equipment nes", 7.98),
            ("847160", "I/O units w/n storage units", 6.84),
            ("852520", "Transmit-receive apparatus for radio, TV, etc.", 4.58),
            ("847170", "Storage units", 3.21),
            ("852990", "Parts for radio/tv transmit/receive equipment, nes", 2.87),
            ("640399", "Footwear, sole rubber, plastics uppers of leather, nes", 2.64),
            ("270112", "Bituminous coal, not agglomerated", 2.42),
            ("852290", "Parts and accessories of recorders except cartridges", 2.25),
            ("640299", "Footwear, outer soles/uppers of rubber or plastic, nes", 2.25),
            ("950390", "Toys nes", 2.22),
            ("860900", "Cargo containers designed for carriage", 2.20),
            ("420212", "Trunks, suitcases, etc., outer surface plastic/textile", 2.18),
            ("271000", "Petroleum oils and oils", 2.12),
            ("852190", "Video record/reproduction apparatus not magnetic tape", 2.02),
            ("420310", "Articles of apparel of leather or composition leather", 2.00),
            ("850440", "Static converters, nes", 1.74),
            ("611030", "Pullovers, cardigans etc. of man-made fibres, knit", 1.69),
            ("852731", "Radio-telephony receiver, with sound reproduce/record", 1.62),
            ("610910", "T-shirts, singlets and other vests, of cotton, knit", 1.60),
            ("392690", "Plastic articles nes", 1.56),
            ("853400", "Electronic printed circuits", 1.52),
            ("620342", "Men's, boys' trousers and shorts, of cotton, not knit", 1.43),
            ("950341", "Stuffed toys", 1.41),
            ("852812", "Colour television receiver", 1.41),
        ],
    },
    "A5": {
        "country": "India",
        "flow": "Exports",
        "rows": [
            ("710239", "Diamonds (jewellery) worked but not mounted or set", 5.62),
            ("271000", "Petroleum oils and oils", 2.06),
            ("711319", "Jewellery and parts of precious metal except silver", 1.05),
            ("030613", "Shrimps and prawns, frozen", 0.81),
            ("100630", "Rice, semi-milled or wholly milled", 0.61),
            ("620520", "Men's, boys' shirts, of cotton, not knit", 0.60),
            ("610910", "T-shirts, singlets and other vests, of cotton, knit", 0.53),
            ("300490", "Medicaments nes, in dosage", 0.49),
            ("620630", "Women's, girls' blouses and shirts, of cotton, not knit", 0.48),
            ("294200", "Organic compounds, nes", 0.45),
            ("630492", "Furnishing articles nes, of cotton, not knit, crochet", 0.43),
            ("420310", "Articles of apparel of leather or composition leather", 0.40),
            ("230400", "Soya bean oil cake and other solid residues", 0.38),
            ("610510", "Men's, boys shirts, of cotton, knit", 0.37),
            ("080132", "Cashew nuts, shelled", 0.36),
            ("260111", "Iron ore, concentrate, not iron pyrites, unagglomerated", 0.35),
            ("520511", "Cotton yarn >85% single uncombed >714 dtex", 0.31),
            ("520710", "Cotton yarn except sewing thread >85% cotton, retail", 0.29),
            ("630790", "Made-up articles (textile) nes", 0.26),
            ("100190", "Wheat except durum wheat, and meslin", 0.25),
            ("847330", "Parts and accessories of data processing equipment nes", 0.25),
            ("380810", "Insecticides, packaged for retail sale", 0.25),
            ("640610", "Footwear uppers and parts thereof", 0.24),
            ("030379", "Fish nes, frozen, whole", 0.24),
            ("620442", "Women's, girls' dresses, of cotton, not knit", 0.23),
        ],
    },
    "A6": {
        "country": "United States",
        "flow": "Imports",
        "rows": [
            ("270900", "Petroleum oils, oils from bituminous minerals, crude", 79.29),
            ("870323", "Automobiles, spark-ignition engine of 1,500-3,000 cc", 53.25),
            ("870324", "Automobiles, spark-ignition engine of >3,000 cc", 51.53),
            ("271000", "Petroleum oils and oils", 26.14),
            ("847330", "Parts and accessories of data processing equipment nes", 25.08),
            ("854213", "Metal oxide semiconductor", 19.80),
            ("847160", "I/O units w/n storage units", 16.21),
            ("271121", "Natural gas in gaseous state", 15.36),
            ("847170", "Storage units", 13.43),
            ("870431", "Spark-ignition engine trucks weighing <5 tonnes", 12.76),
            ("852520", "Transmit-receive apparatus for radio, TV, etc.", 12.45),
            ("710239", "Diamonds (jewellery) worked but not mounted or set", 10.05),
            ("300490", "Medicaments nes, in dosage", 10.03),
            ("870899", "Motor vehicle parts nes", 9.29),
            ("880240", "Fixed wing aircraft, unladen weight >15,000 kg", 7.61),
            ("847130", "Portable digital data processor", 7.49),
            ("440710", "Lumber, coniferous thickness <6 mm", 6.78),
            ("640399", "Footwear, sole rubber, plastics uppers of leather, nes", 6.65),
            ("880230", "Fixed wing aircraft, unladen weight 2,000-15,000 kg", 6.58),
            ("852812", "Colour television receiver", 6.54),
            ("840734", "Engines, spark-ignition reciprocating, over 1,000 cc", 6.52),
            ("611020", "Pullovers, cardigans etc. of cotton, knit", 6.05),
            ("847180", "Units of auto data processing", 5.94),
            ("293390", "Heterocyclic compounds with N-hetero-atom(s) only, nes", 5.84),
            ("293490", "Heterocyclic compounds, nes", 5.69),
        ],
    },
    "A7": {
        "country": "Germany",
        "flow": "Imports",
        "rows": [
            ("270900", "Petroleum oils, oils from bituminous minerals, crude", 19.16),
            ("271121", "Natural gas in gaseous state", 11.11),
            ("870323", "Automobiles, spark-ignition engine of 1,500-3,000 cc", 10.72),
            ("847330", "Parts and accessories of data processing equipment nes", 9.26),
            ("271000", "Petroleum oils and oils", 8.65),
            ("880240", "Fixed wing aircraft, unladen weight >15,000 kg", 7.72),
            ("854213", "Metal oxide semiconductor", 7.31),
            ("293390", "Heterocyclic compounds with N-hetero-atom(s) only, nes", 6.69),
            ("870332", "Automobiles, diesel engine of 1,500-2,500 cc", 5.77),
            ("880330", "Aircraft parts nes", 5.40),
            ("847160", "I/O units w/n storage units", 5.01),
            ("300490", "Medicaments nes, in dosage", 4.77),
            ("847170", "Storage units", 4.64),
            ("870322", "Automobiles, spark-ignition engine of 1,000-1,500 cc", 4.59),
            ("852520", "Transmit-receive apparatus for radio, TV, etc.", 4.46),
            ("870899", "Motor vehicle parts nes", 3.59),
            ("840734", "Engines, spark-ignition reciprocating, over 1,000 cc", 3.34),
            ("870829", "Parts and accessories of bodies nes for motor vehicles", 2.32),
            ("847150", "Digital process units", 2.27),
            ("854230", "Monolithic integrated circuits", 2.12),
            ("841112", "Turbo-jet engines of a thrust >25 KN", 2.05),
            ("851750", "Apparatus for carrier-current line systems", 2.03),
            ("854430", "Ignition/other wiring sets for vehicles/aircraft/ship", 2.02),
            ("847130", "Portable digital data processor", 1.89),
            ("851790", "Parts of line telephone/telegraph equipment, nes", 1.87),
        ],
    },
    "A8": {
        "country": "Japan",
        "flow": "Imports",
        "rows": [
            ("270900", "Petroleum oils, oils from bituminous minerals, crude", 38.76),
            ("271111", "Natural gas, liquefied", 13.13),
            ("854213", "Metal oxide semiconductor", 10.85),
            ("847330", "Parts and accessories of data processing equipment nes", 7.35),
            ("270112", "Bituminous coal, not agglomerated", 5.94),
            ("271019", "Light petroleum distillates nes", 5.10),
            ("847170", "Storage units", 3.93),
            ("870323", "Automobiles, spark-ignition engine of 1,500-3,000 cc", 3.77),
            ("847150", "Digital process units", 3.68),
            ("271112", "Propane, liquefied", 3.13),
            ("847160", "I/O units w/n storage units", 2.97),
            ("760110", "Aluminium unwrought, not alloyed", 2.77),
            ("260111", "Iron ore, concentrate, not iron pyrites, unagglomerated", 2.75),
            ("020329", "Swine cuts, frozen nes", 2.38),
            ("030613", "Shrimps and prawns, frozen", 2.28),
            ("440710", "Lumber, coniferous thickness <6 mm", 2.16),
            ("870324", "Automobiles, spark-ignition engine of >3,000 cc", 2.09),
            ("847180", "Units of auto data process", 2.06),
            ("260300", "Copper ores and concentrates", 2.03),
            ("240220", "Cigarettes containing tobacco", 2.00),
            ("852990", "Parts for radio/tv transmit/receive equipment, nes", 1.95),
            ("100590", "Maize except seed corn", 1.94),
            ("852812", "Colour television receiver", 1.87),
            ("300490", "Medicaments nes, in dosage", 1.85),
            ("854230", "Monolithic integrated circuits", 1.75),
        ],
    },
    "A9": {
        "country": "China",
        "flow": "Imports",
        "rows": [
            ("270900", "Petroleum oils, oils from bituminous minerals, crude", 11.66),
            ("854230", "Monolithic integrated circuits", 7.40),
            ("847330", "Parts and accessories of data processing equipment nes", 6.63),
            ("854219", "Monolithic integrated circuits, except digital", 4.05),
            ("271000", "Petroleum oils and oils", 3.75),
            ("852990", "Parts for radio/tv transmit/receive equipment, nes", 3.39),
            ("847989", "Machines and mechanical appliances nes", 3.07),
            ("851750", "Apparatus for carrier-current line systems", 2.83),
            ("120100", "Soya beans", 2.81),
            ("854240", "Hybrid integrated circuits", 2.58),
            ("880240", "Fixed wing aircraft, unladen weight >15,000 kg", 2.34),
            ("851790", "Parts of line telephone/telegraph equipment, nes", 2.24),
            ("260111", "Iron ore, concentrate, not iron pyrites, unagglomerated", 2.16),
            ("853400", "Electronic printed circuits", 1.93),
            ("852290", "Parts and accessories of recorders except cartridges", 1.89),
            ("854213", "Metal oxide semiconductor", 1.87),
            ("847170", "Storage units", 1.84),
            ("852520", "Transmit-receive apparatus for radio, TV, etc.", 1.60),
            ("854040", "Data/graphic display tubes", 1.58),
            ("390110", "Polyethylene - specific gravity <0.94 in primary forms", 1.56),
            ("870899", "Motor vehicle parts nes", 1.52),
            ("390330", "Acrylonitrile-butadiene-styrene copolymers", 1.46),
            ("291736", "Terephthalic acid, its salts", 1.39),
            ("390210", "Polypropylene in primary forms", 1.36),
            ("740311", "Copper cathodes and sections of cathodes unwrought", 1.35),
        ],
    },
    "A10": {
        "country": "India",
        "flow": "Imports",
        "rows": [
            ("270900", "Petroleum oils, oils from bituminous minerals, crude", 12.87),
            ("710812", "Gold in unwrought forms non-monetary", 4.28),
            ("710231", "Diamonds (jewellery) unworked or simply sawn, cleaved", 3.81),
            ("271000", "Petroleum oils and oils", 1.08),
            ("270119", "Coal except anthracite or bituminous, not agglomerated", 0.95),
            ("847330", "Parts and accessories of data processing equipment nes", 0.68),
            ("280920", "Phosphoric acid and polyphosphoric acids", 0.64),
            ("710813", "Gold, semi-manufactured forms, non-monetary", 0.51),
            ("270799", "Coal tar distillation products nes", 0.43),
            ("151110", "Palm oil, crude", 0.41),
            ("710691", "Silver in unwrought forms", 0.39),
            ("520100", "Cotton, not carded or combed", 0.39),
            ("151190", "Palm oil or fractions simply refined", 0.38),
            ("150710", "Soya bean oil crude, whether or not degummed", 0.37),
            ("440399", "Logs, non-coniferous nes", 0.36),
            ("710239", "Diamonds (jewellery) worked but not mounted or set", 0.36),
            ("260300", "Copper ores and concentrates", 0.32),
            ("720449", "Ferrous waste or scrap, nes", 0.30),
            ("480100", "Newsprint", 0.28),
            ("852499", "Recorded media for sound", 0.27),
            ("310420", "Potassium chloride, in packs >10 kg", 0.26),
            ("847170", "Storage units", 0.26),
            ("852520", "Transmit-receive apparatus for radio, TV, etc.", 0.25),
            ("854219", "Monolithic integrated circuits, except digital", 0.22),
            ("281410", "Anhydrous ammonia", 0.20),
        ],
    },
}


def paper_appendix_frame(table_id: str) -> pd.DataFrame:
    spec = APPENDIX_PAPER[table_id]
    rows = []
    for rank, (code, desc, value) in enumerate(spec["rows"], start=1):
        rows.append(
            {
                "table_id": table_id,
                "country": spec["country"],
                "flow": spec["flow"],
                "rank": rank,
                "paper_code": norm_hs6(code),
                "paper_description": desc,
                "paper_value_billion": value,
            }
        )
    return pd.DataFrame(rows)


def compare_table_2_4(concentration: pd.DataFrame) -> tuple[dict[str, Path], dict[str, str]]:
    current = concentration[concentration["year"].eq(2001)].copy()
    exp = current[current["flow"].eq("Exports")].set_index("country")
    imp = current[current["flow"].eq("Imports")].set_index("country")
    modern = pd.DataFrame(
        {
            "country": PAPER_TABLE_2["country"],
            "modern_export_product_gini": PAPER_TABLE_2["country"].map(exp["product_gini"]),
            "modern_export_products": PAPER_TABLE_2["country"].map(exp["product_active_count"]),
            "modern_import_product_gini": PAPER_TABLE_2["country"].map(imp["product_gini"]),
            "modern_import_products": PAPER_TABLE_2["country"].map(imp["product_active_count"]),
            "modern_export_partner_gini": PAPER_TABLE_2["country"].map(exp["partner_gini"]),
            "modern_export_partners": PAPER_TABLE_2["country"].map(exp["partner_active_count"]),
            "modern_export_top5_partner_share_pct": PAPER_TABLE_2["country"].map(exp["top_5_partner_share"]) * 100,
            "modern_import_partner_gini": PAPER_TABLE_2["country"].map(imp["partner_gini"]),
            "modern_import_partners": PAPER_TABLE_2["country"].map(imp["partner_active_count"]),
            "modern_import_top5_partner_share_pct": PAPER_TABLE_2["country"].map(imp["top_5_partner_share"]) * 100,
        }
    )

    t2 = PAPER_TABLE_2.merge(
        modern[
            [
                "country",
                "modern_export_product_gini",
                "modern_export_products",
                "modern_import_product_gini",
                "modern_import_products",
            ]
        ],
        on="country",
    )
    for col in ["export_product_gini", "import_product_gini"]:
        t2[f"{col}_diff"] = t2[f"modern_{col}"] - t2[f"paper_{col}"]
    for col in ["export_products", "import_products"]:
        t2[f"{col}_diff"] = t2[f"modern_{col}"] - t2[f"paper_{col}"]

    t3 = PAPER_TABLE_3.merge(
        modern[
            [
                "country",
                "modern_export_partner_gini",
                "modern_export_partners",
                "modern_export_top5_partner_share_pct",
            ]
        ],
        on="country",
    )
    for col in ["export_partner_gini", "export_partners", "export_top5_partner_share_pct"]:
        t3[f"{col}_diff"] = t3[f"modern_{col}"] - t3[f"paper_{col}"]

    t4 = PAPER_TABLE_4.merge(
        modern[
            [
                "country",
                "modern_import_partner_gini",
                "modern_import_partners",
                "modern_import_top5_partner_share_pct",
            ]
        ],
        on="country",
    )
    for col in ["import_partner_gini", "import_partners", "import_top5_partner_share_pct"]:
        t4[f"{col}_diff"] = t4[f"modern_{col}"] - t4[f"paper_{col}"]

    paths = {
        "table_2": write_csv(t2, TABLES / "table_2_product_concentration_comparison.csv"),
        "table_3": write_csv(t3, TABLES / "table_3_export_partner_concentration_comparison.csv"),
        "table_4": write_csv(t4, TABLES / "table_4_import_partner_concentration_comparison.csv"),
    }
    summaries = {
        "table_2": (
            f"max gini abs diff {max(t2['export_product_gini_diff'].abs().max(), t2['import_product_gini_diff'].abs().max()):.4f}; "
            f"max product-count abs diff {max(t2['export_products_diff'].abs().max(), t2['import_products_diff'].abs().max()):.0f}"
        ),
        "table_3": (
            f"max gini abs diff {t3['export_partner_gini_diff'].abs().max():.4f}; "
            f"max top-5-share abs diff {t3['export_top5_partner_share_pct_diff'].abs().max():.2f} pp"
        ),
        "table_4": (
            f"max gini abs diff {t4['import_partner_gini_diff'].abs().max():.4f}; "
            f"max top-5-share abs diff {t4['import_top5_partner_share_pct_diff'].abs().max():.2f} pp"
        ),
    }
    return paths, summaries


def product_partner_table(
    flow: str,
    reporter_code: int,
    year: int,
    paper_products: list[tuple[str, str, int, float, dict[int, float]]],
    lookup: dict[str, str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if flow == "Exports":
        cells = read_export_dimension(reporter_code, year, "product_partner_cell")
    else:
        cells = read_import_cells(reporter_code, year)
    cells["cmd_code"] = normalize_hs6_series(cells["cmd_code"])
    cells["partner_code"] = pd.to_numeric(cells["partner_code"], errors="coerce")
    cells = cells.dropna(subset=["partner_code"])
    cells["partner_code"] = cells["partner_code"].astype(int)
    summary_rows = []
    share_rows = []
    for code, paper_desc, paper_count, paper_gini, paper_shares in paper_products:
        code = norm_hs6(code)
        values = (
            cells[cells["cmd_code"].eq(code)]
            .groupby("partner_code", as_index=False)["trade_value"]
            .sum()
            .sort_values("trade_value", ascending=False)
        )
        modern_values = values["trade_value"].to_numpy(dtype=float)
        modern_count = int(len(values))
        modern_gini = gini(modern_values)
        summary_rows.append(
            {
                "flow": flow,
                "cmd_code": code,
                "paper_description": paper_desc,
                "modern_description": product_label(code, lookup),
                "paper_partner_count": paper_count,
                "modern_partner_count": modern_count,
                "partner_count_diff": modern_count - paper_count,
                "paper_gini": paper_gini,
                "modern_gini": modern_gini,
                "gini_diff": modern_gini - paper_gini if np.isfinite(modern_gini) else np.nan,
            }
        )
        for n, paper_share in paper_shares.items():
            modern_share = top_n_share(modern_values, n) * 100 if modern_count else np.nan
            share_rows.append(
                {
                    "flow": flow,
                    "cmd_code": code,
                    "paper_description": paper_desc,
                    "top_n_partners": n,
                    "paper_share_pct": paper_share,
                    "modern_share_pct": modern_share,
                    "share_diff_pp": modern_share - paper_share if np.isfinite(modern_share) else np.nan,
                }
            )
        share_rows.append(
            {
                "flow": flow,
                "cmd_code": code,
                "paper_description": paper_desc,
                "top_n_partners": "All",
                "paper_share_pct": 100.0,
                "modern_share_pct": 100.0 if modern_count else np.nan,
                "share_diff_pp": 0.0 if modern_count else np.nan,
            }
        )
    return pd.DataFrame(summary_rows), pd.DataFrame(share_rows)


def compare_tables_5_6(lookup: dict[str, str]) -> tuple[dict[str, Path], dict[str, str]]:
    t5_summary, t5_shares = product_partner_table("Exports", 842, 2001, PAPER_TABLE_5_PRODUCTS, lookup)
    t6_summary, t6_shares = product_partner_table("Imports", 842, 2001, PAPER_TABLE_6_PRODUCTS, lookup)
    paths = {
        "table_5_summary": write_csv(t5_summary, TABLES / "table_5_us_top_export_product_destination_summary.csv"),
        "table_5_shares": write_csv(t5_shares, TABLES / "table_5_us_top_export_product_destination_shares.csv"),
        "table_6_summary": write_csv(t6_summary, TABLES / "table_6_us_top_import_product_source_summary.csv"),
        "table_6_shares": write_csv(t6_shares, TABLES / "table_6_us_top_import_product_source_shares.csv"),
    }
    summaries = {
        "table_5": (
            f"max product gini abs diff {t5_summary['gini_diff'].abs().max():.4f}; "
            f"max top-share abs diff {t5_shares['share_diff_pp'].dropna().abs().max():.2f} pp"
        ),
        "table_6": (
            f"max product gini abs diff {t6_summary['gini_diff'].abs().max():.4f}; "
            f"max top-share abs diff {t6_shares['share_diff_pp'].dropna().abs().max():.2f} pp"
        ),
    }
    return paths, summaries


def bilateral_values(flow: str, partner_code: int) -> pd.Series:
    if flow == "Exports":
        cells = read_export_dimension(842, 2001, "product_partner_cell")
        values = cells[pd.to_numeric(cells["partner_code"], errors="coerce").eq(partner_code)]
    else:
        cells = read_import_cells(842, 2001)
        values = cells[pd.to_numeric(cells["partner_code"], errors="coerce").eq(partner_code)]
    if values.empty:
        return pd.Series(dtype=float)
    values = drop_999999(values, "cmd_code")
    return values.groupby("cmd_code")["trade_value"].sum()


def compare_table_7() -> tuple[Path, str]:
    rows = []
    for row in PAPER_TABLE_7.itertuples(index=False):
        partner_code = US_PARTNERS[row.partner]
        exp_vals = bilateral_values("Exports", partner_code)
        imp_vals = bilateral_values("Imports", partner_code)
        rows.append(
            {
                "partner": row.partner,
                "paper_export_gini": row.paper_export_gini,
                "modern_export_gini": gini(exp_vals),
                "export_gini_diff": gini(exp_vals) - row.paper_export_gini,
                "paper_export_products": row.paper_export_products,
                "modern_export_products": int((exp_vals > 0).sum()),
                "export_products_diff": int((exp_vals > 0).sum()) - row.paper_export_products,
                "paper_export_top200_share_pct": row.paper_export_top200_share_pct,
                "modern_export_top200_share_pct": top_n_share(exp_vals, 200) * 100,
                "export_top200_share_diff_pp": top_n_share(exp_vals, 200) * 100 - row.paper_export_top200_share_pct,
                "paper_import_gini": row.paper_import_gini,
                "modern_import_gini": gini(imp_vals),
                "import_gini_diff": gini(imp_vals) - row.paper_import_gini,
                "paper_import_products": row.paper_import_products,
                "modern_import_products": int((imp_vals > 0).sum()),
                "import_products_diff": int((imp_vals > 0).sum()) - row.paper_import_products,
                "paper_import_top200_share_pct": row.paper_import_top200_share_pct,
                "modern_import_top200_share_pct": top_n_share(imp_vals, 200) * 100,
                "import_top200_share_diff_pp": top_n_share(imp_vals, 200) * 100 - row.paper_import_top200_share_pct,
            }
        )
    out = pd.DataFrame(rows)
    path = write_csv(out, TABLES / "table_7_us_bilateral_product_concentration_comparison.csv")
    max_gini = max(out["export_gini_diff"].abs().max(), out["import_gini_diff"].abs().max())
    max_share = max(out["export_top200_share_diff_pp"].abs().max(), out["import_top200_share_diff_pp"].abs().max())
    return path, f"max gini abs diff {max_gini:.4f}; max top-200-share abs diff {max_share:.2f} pp"


def product_totals(country: str, flow: str, lookup: dict[str, str]) -> pd.DataFrame:
    reporter_code = COUNTRY_TO_REPORTER[country]
    if flow == "Exports":
        product = read_export_dimension(reporter_code, 2001, "product")
        product = product.groupby("cmd_code", as_index=False)["trade_value"].sum()
    else:
        cells = read_import_cells(reporter_code, 2001)
        product = cells.groupby("cmd_code", as_index=False)["trade_value"].sum()
    product = drop_999999(product, "cmd_code")
    assert_no_999999(product, "cmd_code", f"{country} {flow} product totals")
    product = product[product["trade_value"] > 0].sort_values("trade_value", ascending=False).reset_index(drop=True)
    product["rank"] = np.arange(1, len(product) + 1)
    product["description"] = product["cmd_code"].map(lambda code: product_label(code, lookup))
    product["value_billion"] = product["trade_value"] / 1_000_000_000
    return product[["rank", "cmd_code", "description", "trade_value", "value_billion"]]


def compare_appendix_tables(lookup: dict[str, str]) -> tuple[list[Path], pd.DataFrame]:
    paths: list[Path] = []
    summary_rows = []
    for table_id, spec in APPENDIX_PAPER.items():
        paper = paper_appendix_frame(table_id)
        modern = product_totals(spec["country"], spec["flow"], lookup)
        top25 = modern.head(25).rename(
            columns={
                "cmd_code": "modern_rank_code",
                "description": "modern_rank_description",
                "value_billion": "modern_rank_value_billion",
            }
        )
        same_rank = paper.merge(
            top25[["rank", "modern_rank_code", "modern_rank_description", "modern_rank_value_billion"]],
            on="rank",
            how="left",
        )
        code_values = modern.rename(
            columns={
                "rank": "modern_rank_for_paper_code",
                "cmd_code": "paper_code",
                "description": "modern_description_for_paper_code",
                "value_billion": "modern_value_for_paper_code_billion",
            }
        )[["paper_code", "modern_rank_for_paper_code", "modern_description_for_paper_code", "modern_value_for_paper_code_billion"]]
        out = same_rank.merge(code_values, on="paper_code", how="left")
        out["rank_code_match"] = out["paper_code"].eq(out["modern_rank_code"])
        out["paper_code_in_modern_top25"] = out["modern_rank_for_paper_code"].le(25)
        out["value_diff_for_paper_code_billion"] = out["modern_value_for_paper_code_billion"] - out["paper_value_billion"]
        path = write_csv(out, TABLES / f"table_{table_id}_appendix_top25_comparison.csv")
        paths.append(path)
        summary_rows.append(
            {
                "table_id": table_id,
                "country": spec["country"],
                "flow": spec["flow"],
                "rank_code_matches": int(out["rank_code_match"].sum()),
                "paper_codes_in_modern_top25": int(out["paper_code_in_modern_top25"].fillna(False).sum()),
                "max_abs_value_diff_for_paper_code_billion": out["value_diff_for_paper_code_billion"].abs().max(),
                "output_path": rel(path),
            }
        )
    summary = pd.DataFrame(summary_rows)
    paths.append(write_csv(summary, TABLES / "appendix_top25_summary.csv"))
    return paths, summary


def build_lorenz_figure(concentration: pd.DataFrame) -> Path:
    current = concentration[concentration["year"].eq(2001)].copy()
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), sharex=True, sharey=True)
    for ax, flow in zip(axes, ["Exports", "Imports"]):
        usa = current[(current["country"].eq("United States")) & (current["flow"].eq(flow))]
        if flow == "Exports":
            values = read_export_dimension(842, 2001, "product").groupby("cmd_code")["trade_value"].sum()
        else:
            values = read_import_cells(842, 2001).groupby("cmd_code")["trade_value"].sum()
        pts = lorenz_points(values)
        ax.plot(pts["cum_items"] * 100, pts["cum_value"] * 100, color="#1f4e5f", linewidth=2)
        ax.plot([0, 100], [0, 100], color="#777777", linewidth=1, linestyle="--")
        g = gini(values)
        panel_g = float(usa["product_gini"].iloc[0]) if not usa.empty else g
        ax.set_title(f"US HS6 {flow}, 2001\nGini {g:.3f} (panel {panel_g:.3f})")
        ax.set_xlabel("Cumulative products (%)")
        ax.grid(alpha=0.25)
    axes[0].set_ylabel("Cumulative trade value (%)")
    fig.suptitle("Modern HS6 Lorenz Curves: diagnostic only, not a substitute for paper HS10 Figures 1-2")
    path = FIGURES / "modern_us_hs6_2001_lorenz_diagnostic.png"
    plt.tight_layout()
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return path


def discover_hs10_cid_links(download: bool = False) -> dict:
    result = {
        "local_dir": str(HS10_DIR),
        "local_files": [p.name for p in sorted(HS10_DIR.glob("*")) if p.is_file()],
        "cid_page_url": SOURCES["uc_davis_cid"],
        "cid_page_status": None,
        "candidate_2001_links": [],
        "downloaded_files": [],
        "error": "",
    }
    try:
        response = requests.get(SOURCES["uc_davis_cid"], timeout=20)
        result["cid_page_status"] = response.status_code
        response.raise_for_status()
        hrefs = re.findall(r'href=["\']([^"\']+)["\']', response.text, flags=re.IGNORECASE)
        candidates = []
        for href in hrefs:
            if "2001" not in href:
                continue
            if not re.search(r"(hs|export|import|exp|imp|us)", href, re.IGNORECASE):
                continue
            if href.startswith("/"):
                href = "https://cid.ucdavis.edu" + href
            elif not href.startswith("http"):
                href = "https://cid.ucdavis.edu/" + href.lstrip("./")
            candidates.append(href)
        result["candidate_2001_links"] = sorted(set(candidates))
        if download:
            for url in result["candidate_2001_links"]:
                name = re.sub(r"[^A-Za-z0-9._-]+", "_", url.rsplit("/", 1)[-1] or "cid_2001_download")
                out = HS10_DIR / name
                if out.exists():
                    result["downloaded_files"].append(out.name)
                    continue
                r = requests.get(url, timeout=60)
                r.raise_for_status()
                out.write_bytes(r.content)
                result["downloaded_files"].append(out.name)
    except Exception as exc:  # network discovery is advisory
        result["error"] = str(exc)
    return result


def textual_claim_checks(concentration: pd.DataFrame) -> pd.DataFrame:
    current = concentration[concentration["year"].eq(2001)].copy()
    exp = current[current["flow"].eq("Exports")].copy()
    imp = current[current["flow"].eq("Imports")].copy()
    merged = exp[["country", "product_gini", "product_active_count"]].merge(
        imp[["country", "product_gini", "product_active_count"]],
        on="country",
        suffixes=("_export", "_import"),
    )
    rows = []
    rows.append(
        {
            "claim_id": "text_export_product_gini_gt_0_9_count",
            "paper_value": "18 of 33 countries",
            "modern_value": f"{int((exp['product_gini'] > 0.9).sum())} of {len(exp)} countries",
            "status": "exact_match" if int((exp["product_gini"] > 0.9).sum()) == 18 else "mismatch",
            "notes": "Computed from modern no-999999 2001 concentration panel.",
        }
    )
    rows.append(
        {
            "claim_id": "text_import_gini_exceeds_export_gini_countries",
            "paper_value": "China, India, Italy, United States",
            "modern_value": ", ".join(merged.loc[merged["product_gini_import"] > merged["product_gini_export"], "country"].tolist()),
            "status": "exact_match"
            if set(merged.loc[merged["product_gini_import"] > merged["product_gini_export"], "country"]) == {"China", "India", "Italy", "United States"}
            else "mismatch",
            "notes": "Product Gini comparison.",
        }
    )
    rows.append(
        {
            "claim_id": "text_export_partner_gini_gt_0_9_count",
            "paper_value": "21 of 33 countries",
            "modern_value": f"{int((exp['partner_gini'] > 0.9).sum())} of {len(exp)} countries",
            "status": "exact_match" if int((exp["partner_gini"] > 0.9).sum()) == 21 else "mismatch",
            "notes": "Destination concentration.",
        }
    )
    rows.append(
        {
            "claim_id": "text_import_partner_gini_gt_0_9_count",
            "paper_value": "18 of 33 countries",
            "modern_value": f"{int((imp['partner_gini'] > 0.9).sum())} of {len(imp)} countries",
            "status": "exact_match" if int((imp["partner_gini"] > 0.9).sum()) == 18 else "mismatch",
            "notes": "Source concentration.",
        }
    )
    rows.append(
        {
            "claim_id": "text_export_top5_partner_share_gt_50_count",
            "paper_value": "26 of 33 countries",
            "modern_value": f"{int((exp['top_5_partner_share'] > 0.5).sum())} of {len(exp)} countries",
            "status": "exact_match" if int((exp["top_5_partner_share"] > 0.5).sum()) == 26 else "mismatch",
            "notes": "Strictly greater than 50 percent.",
        }
    )
    rows.append(
        {
            "claim_id": "text_import_top5_partner_share_gt_50_count",
            "paper_value": "23 of 33 countries",
            "modern_value": f"{int((imp['top_5_partner_share'] > 0.5).sum())} of {len(imp)} countries",
            "status": "exact_match" if int((imp["top_5_partner_share"] > 0.5).sum()) == 23 else "mismatch",
            "notes": "Strictly greater than 50 percent.",
        }
    )
    usa = merged[merged["country"].eq("United States")].iloc[0]
    pct_more = (usa["product_active_count_import"] - usa["product_active_count_export"]) / usa["product_active_count_export"] * 100
    rows.append(
        {
            "claim_id": "text_us_import_products_exceed_exports_by_0_4_pct",
            "paper_value": "US imported 4,940 HS6 products and exported 4,921; imports exceed exports by 0.4 percent.",
            "modern_value": f"US imported {int(usa['product_active_count_import'])} and exported {int(usa['product_active_count_export'])}; imports exceed exports by {pct_more:.2f} percent.",
            "status": "close" if abs(pct_more - 0.4) <= 0.25 else "mismatch",
            "notes": "Modern no-999999 product counts.",
        }
    )
    count_1990 = concentration[concentration["year"].eq(1990)].copy()
    rows.append(
        {
            "claim_id": "text_1990_robustness_statement",
            "paper_value": "Paper says similar calculations for 1990 do not change the patterns.",
            "modern_value": (
                f"1990 modern panel rows: {len(count_1990)}; "
                f"median export product Gini {count_1990[count_1990['flow'].eq('Exports')]['product_gini'].median():.3f}; "
                f"median import product Gini {count_1990[count_1990['flow'].eq('Imports')]['product_gini'].median():.3f}."
            ),
            "status": "qualitative_check",
            "notes": "No paper 1990 table values are reported, so this checks only the direction of the robustness claim.",
        }
    )
    return pd.DataFrame(rows)


def world_trade_claims() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "claim_id": "world_hs6_export_import_gini",
                "paper_value": "World commodity export Gini = 0.7886 and import Gini = 0.7886.",
                "modern_value": "",
                "status": "blocked",
                "notes": "Requires all-world HS6 reporter data. The local canonical processed panel is the 33-country Prof P sample, not full world trade.",
            },
            {
                "claim_id": "world_top20_export_import_overlap",
                "paper_value": "18 of top 20 HS6 export and import commodities are in common.",
                "modern_value": "",
                "status": "blocked",
                "notes": "Requires world HS6 commodity totals.",
            },
            {
                "claim_id": "world_bottom_half_product_share",
                "paper_value": "Bottom half of products account for less than 5 percent of world exports in 2001.",
                "modern_value": "",
                "status": "blocked",
                "notes": "Requires world HS6 commodity totals.",
            },
            {
                "claim_id": "world_bottom_half_country_share",
                "paper_value": "Bottom half of countries account for 0.92 percent of world exports in 2001.",
                "modern_value": "",
                "status": "blocked",
                "notes": "Requires all-world country totals, not only the paper's 33-country sample.",
            },
        ]
    )


def raw_hs6_2001(
    reporter_code: int,
    flow: str,
    cache: dict[tuple[int, str], pd.DataFrame],
) -> pd.DataFrame:
    key = (int(reporter_code), flow)
    if key in cache:
        return cache[key].copy()

    flow_code = "X" if flow == "Exports" else "M"
    matches = sorted((RAW / "comtrade" / "bulk").glob(f"COMTRADE-FINAL-CA{reporter_code:03d}2001H1*.gz"))
    if not matches:
        raise FileNotFoundError(f"No 2001 H1 raw file found for reporter {reporter_code}")
    path = matches[0]
    usecols = ["flowCode", "partnerCode", "cmdCode", "primaryValue"]
    raw = pd.read_csv(path, sep="\t", compression="gzip", usecols=usecols, low_memory=False)
    raw = raw[raw["flowCode"].eq(flow_code)].copy()
    raw["trade_value"] = pd.to_numeric(raw["primaryValue"], errors="coerce")
    raw = raw[raw["trade_value"] > 0].copy()
    raw["cmd_code"] = raw["cmdCode"].astype(str).str.extract(r"(\d{6})", expand=False)
    raw = raw.dropna(subset=["cmd_code"]).copy()
    raw = raw[raw["cmd_code"].ne("999999")].copy()
    raw["partner_code"] = pd.to_numeric(raw["partnerCode"], errors="coerce")
    raw = raw.dropna(subset=["partner_code"]).copy()
    raw["partner_code"] = raw["partner_code"].astype(int)
    out = raw[["partner_code", "cmd_code", "trade_value"]].copy()
    if RAW_HS6_CACHE_MAX_ITEMS:
        while len(cache) >= RAW_HS6_CACHE_MAX_ITEMS:
            cache.pop(next(iter(cache)))
        cache[key] = out
    return out.copy()


def raw_partner_metrics(values: pd.Series) -> dict[str, float | int]:
    return {
        "partner_count": int((values > 0).sum()),
        "partner_gini": gini(values),
        "top5_partner_share_pct": top_n_share(values, 5) * 100,
    }


def raw_totalcmd_partner_2001(
    reporter_code: int,
    flow: str,
    cache: dict[tuple[int, str], pd.DataFrame],
) -> pd.DataFrame:
    """Return 2001 all-commodity partner totals, including partnerCode 0 World."""
    key = (int(reporter_code), flow)
    if key in cache:
        return cache[key].copy()

    flow_code = "X" if flow == "Exports" else "M"
    matches = sorted((RAW / "comtrade" / "bulk").glob(f"COMTRADE-FINAL-CA{reporter_code:03d}2001H1*.gz"))
    if not matches:
        raise FileNotFoundError(f"No 2001 H1 raw file found for reporter {reporter_code}")
    path = matches[0]
    totals: dict[int, float] = {}
    with gzip.open(path, "rt", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            if row.get("flowCode") != flow_code or str(row.get("cmdCode", "")).strip() != "TOTAL":
                continue
            try:
                value = float(row.get("primaryValue") or 0)
                partner_code = int(float(row.get("partnerCode")))
            except (TypeError, ValueError):
                continue
            if value <= 0:
                continue
            totals[partner_code] = totals.get(partner_code, 0.0) + value

    out = pd.DataFrame(
        [{"partner_code": partner_code, "trade_value": value} for partner_code, value in sorted(totals.items())]
    )
    cache[key] = out
    return out.copy()


def world_denominator_partner_metrics(values: pd.Series) -> dict[str, float | int | bool]:
    values = pd.to_numeric(values, errors="coerce").dropna()
    actual = values[values.index.to_series().astype(int).ne(0)]
    actual = actual[actual > 0]
    world_value = float(values.loc[0]) if 0 in values.index and float(values.loc[0]) > 0 else float("nan")
    actual_sum = float(actual.sum())
    denominator = world_value if math.isfinite(world_value) and world_value > 0 else actual_sum
    top5_value = float(actual.sort_values(ascending=False).head(5).sum())
    return {
        "partner_count": int((actual > 0).sum()),
        "partner_gini": gini(actual),
        "top5_partner_share_pct": (top5_value / denominator * 100) if denominator > 0 else float("nan"),
        "top5_partner_value": top5_value,
        "world_denominator": denominator,
        "world_denominator_available": bool(math.isfinite(world_value) and world_value > 0),
        "actual_partner_sum": actual_sum,
        "actual_sum_over_world": (actual_sum / world_value) if math.isfinite(world_value) and world_value > 0 else float("nan"),
    }


def build_partner_world_denominator_default() -> tuple[dict[str, Path], pd.DataFrame, dict[str, str]]:
    """Build default Table 3-4 partner results with top-five actual partners over World total."""
    total_cache: dict[tuple[int, str], pd.DataFrame] = {}
    diagnostic_rows: list[dict[str, object]] = []
    metric_rows: list[dict[str, object]] = []
    paper_specs = [
        (
            "Exports",
            PAPER_TABLE_3,
            "paper_export_partner_gini",
            "paper_export_partners",
            "paper_export_top5_partner_share_pct",
        ),
        (
            "Imports",
            PAPER_TABLE_4,
            "paper_import_partner_gini",
            "paper_import_partners",
            "paper_import_top5_partner_share_pct",
        ),
    ]
    for flow, paper, paper_g_col, paper_n_col, paper_top_col in paper_specs:
        for paper_row in paper.itertuples(index=False):
            reporter_code = COUNTRY_TO_REPORTER[paper_row.country]
            totals = raw_totalcmd_partner_2001(reporter_code, flow, total_cache)
            for row in totals.itertuples(index=False):
                diagnostic_rows.append(
                    {
                        "country": paper_row.country,
                        "reporter_code": reporter_code,
                        "flow": flow,
                        "partner_code": int(row.partner_code),
                        "trade_value": float(row.trade_value),
                    }
                )
            values = totals.groupby("partner_code")["trade_value"].sum()
            metrics = world_denominator_partner_metrics(values)
            paper_gini = float(getattr(paper_row, paper_g_col))
            paper_count = int(getattr(paper_row, paper_n_col))
            paper_top5 = float(getattr(paper_row, paper_top_col))
            metric_rows.append(
                {
                    "country": paper_row.country,
                    "flow": flow,
                    "paper_partner_count": paper_count,
                    "modern_partner_count": metrics["partner_count"],
                    "partner_count_diff": int(metrics["partner_count"]) - paper_count,
                    "paper_partner_gini": paper_gini,
                    "modern_partner_gini": metrics["partner_gini"],
                    "partner_gini_diff": float(metrics["partner_gini"]) - paper_gini,
                    "paper_top5_partner_share_pct": paper_top5,
                    "modern_top5_partner_share_pct": metrics["top5_partner_share_pct"],
                    "top5_partner_share_diff_pp": float(metrics["top5_partner_share_pct"]) - paper_top5,
                    "top5_partner_value": metrics["top5_partner_value"],
                    "world_denominator": metrics["world_denominator"],
                    "world_denominator_available": metrics["world_denominator_available"],
                    "actual_partner_sum": metrics["actual_partner_sum"],
                    "actual_sum_over_world": metrics["actual_sum_over_world"],
                    "comparison_note": (
                        "Top-five share uses the five largest actual partners in the numerator and "
                        "partnerCode 0 World total as the denominator; World is excluded from partner counts and Ginis."
                    ),
                }
            )

    diagnostic = pd.DataFrame(diagnostic_rows)
    metrics_df = pd.DataFrame(metric_rows)
    export_metrics = metrics_df[metrics_df["flow"].eq("Exports")].copy()
    import_metrics = metrics_df[metrics_df["flow"].eq("Imports")].copy()

    t3 = PAPER_TABLE_3.merge(
        export_metrics.drop(columns=["flow"]).rename(
            columns={
                "paper_partner_count": "paper_export_partners",
                "modern_partner_count": "modern_export_partners",
                "partner_count_diff": "export_partners_diff",
                "paper_partner_gini": "paper_export_partner_gini",
                "modern_partner_gini": "modern_export_partner_gini",
                "partner_gini_diff": "export_partner_gini_diff",
                "paper_top5_partner_share_pct": "paper_export_top5_partner_share_pct",
                "modern_top5_partner_share_pct": "modern_export_top5_partner_share_pct",
                "top5_partner_share_diff_pp": "export_top5_partner_share_pct_diff",
            }
        ),
        on=["country", "paper_export_partner_gini", "paper_export_partners", "paper_export_top5_partner_share_pct"],
    )
    t4 = PAPER_TABLE_4.merge(
        import_metrics.drop(columns=["flow"]).rename(
            columns={
                "paper_partner_count": "paper_import_partners",
                "modern_partner_count": "modern_import_partners",
                "partner_count_diff": "import_partners_diff",
                "paper_partner_gini": "paper_import_partner_gini",
                "modern_partner_gini": "modern_import_partner_gini",
                "partner_gini_diff": "import_partner_gini_diff",
                "paper_top5_partner_share_pct": "paper_import_top5_partner_share_pct",
                "modern_top5_partner_share_pct": "modern_import_top5_partner_share_pct",
                "top5_partner_share_diff_pp": "import_top5_partner_share_pct_diff",
            }
        ),
        on=["country", "paper_import_partner_gini", "paper_import_partners", "paper_import_top5_partner_share_pct"],
    )

    paths = {
        "table_3": write_csv(t3, TABLES / "table_3_export_partner_concentration_comparison.csv"),
        "table_4": write_csv(t4, TABLES / "table_4_import_partner_concentration_comparison.csv"),
        "partner_totalcmd": write_csv(diagnostic, PARTNER_TOTALCMD_DIAGNOSTIC_TABLE),
        "partner_world_denominator_detail": write_csv(metrics_df, PARTNER_WORLD_DENOM_DETAIL_TABLE),
    }
    summary_rows = []
    summaries = {}
    for flow, table, diff_col, gini_col, label in [
        ("Exports", t3, "export_top5_partner_share_pct_diff", "export_partner_gini_diff", "table_3"),
        ("Imports", t4, "import_top5_partner_share_pct_diff", "import_partner_gini_diff", "table_4"),
    ]:
        summary_rows.append(
            {
                "flow": flow,
                "mean_abs_top5_diff_pp": table[diff_col].abs().mean(),
                "median_abs_top5_diff_pp": table[diff_col].abs().median(),
                "max_abs_top5_diff_pp": table[diff_col].abs().max(),
                "within_1pp": int(table[diff_col].abs().le(1).sum()),
                "within_2pp": int(table[diff_col].abs().le(2).sum()),
                "mean_abs_partner_gini_diff": table[gini_col].abs().mean(),
                "max_abs_partner_gini_diff": table[gini_col].abs().max(),
                "max_abs_actual_sum_over_world_minus_1": (metrics_df[metrics_df["flow"].eq(flow)]["actual_sum_over_world"] - 1).abs().max(),
            }
        )
        summaries[label] = (
            f"World-denominator top-5 convention: max gini abs diff {table[gini_col].abs().max():.4f}; "
            f"mean/median/max top-5-share abs diff {table[diff_col].abs().mean():.2f}/"
            f"{table[diff_col].abs().median():.2f}/{table[diff_col].abs().max():.2f} pp"
        )
    paths["partner_world_denominator_summary"] = write_csv(pd.DataFrame(summary_rows), PARTNER_WORLD_DENOM_SUMMARY_TABLE)
    return paths, metrics_df, summaries


def build_raw_partner_sensitivity(
    cache: dict[tuple[int, str], pd.DataFrame],
) -> tuple[Path, Path, pd.DataFrame, dict[str, str]]:
    rows = []
    paper_specs = [
        (
            "Exports",
            PAPER_TABLE_3,
            "paper_export_partner_gini",
            "paper_export_partners",
            "paper_export_top5_partner_share_pct",
        ),
        (
            "Imports",
            PAPER_TABLE_4,
            "paper_import_partner_gini",
            "paper_import_partners",
            "paper_import_top5_partner_share_pct",
        ),
    ]
    for flow, paper, paper_g_col, paper_n_col, paper_top_col in paper_specs:
        for paper_row in paper.itertuples(index=False):
            reporter_code = COUNTRY_TO_REPORTER[paper_row.country]
            raw = raw_hs6_2001(reporter_code, flow, cache)
            variants = {
                "no_world_partner0": raw[raw["partner_code"].ne(0)],
                "with_world_partner0": raw,
            }
            for variant, frame in variants.items():
                values = frame.groupby("partner_code")["trade_value"].sum()
                metrics = raw_partner_metrics(values)
                paper_gini = float(getattr(paper_row, paper_g_col))
                paper_count = int(getattr(paper_row, paper_n_col))
                paper_top5 = float(getattr(paper_row, paper_top_col))
                rows.append(
                    {
                        "country": paper_row.country,
                        "flow": flow,
                        "variant": variant,
                        "paper_partner_count": paper_count,
                        "modern_partner_count": metrics["partner_count"],
                        "partner_count_diff": metrics["partner_count"] - paper_count,
                        "paper_partner_gini": paper_gini,
                        "modern_partner_gini": metrics["partner_gini"],
                        "partner_gini_diff": metrics["partner_gini"] - paper_gini,
                        "paper_top5_partner_share_pct": paper_top5,
                        "modern_top5_partner_share_pct": metrics["top5_partner_share_pct"],
                        "top5_partner_share_diff_pp": metrics["top5_partner_share_pct"] - paper_top5,
                    }
                )

    sensitivity = pd.DataFrame(rows)
    sensitivity["score"] = (
        sensitivity["partner_gini_diff"].abs() * 100
        + sensitivity["top5_partner_share_diff_pp"].abs() / 100
        + sensitivity["partner_count_diff"].abs() / 100
    )
    paper_like = (
        sensitivity.sort_values(["country", "flow", "score"])
        .groupby(["country", "flow"], as_index=False)
        .first()
        .sort_values(["flow", "country"])
        .reset_index(drop=True)
    )
    world_like = paper_like[paper_like["variant"].eq("with_world_partner0")]
    sensitivity_path = write_csv(sensitivity, TABLES / "partner_concentration_world_partner_sensitivity.csv")
    paper_like_path = write_csv(paper_like, TABLES / "partner_concentration_paper_like_variant.csv")
    summaries = {
        "partner_sensitivity": (
            "Including partnerCode 0 (`World`) best matches exactly 3 export rows "
            "and 3 import rows; those are the rows driving the large Table 3/4 mismatches."
        ),
        "world_partner_rows": (
            f"For those six world-partner rows, max abs top-5 difference is "
            f"{world_like['top5_partner_share_diff_pp'].abs().max():.2f} pp and max abs partner-Gini "
            f"difference is {world_like['partner_gini_diff'].abs().max():.4f}."
        ),
        "paper_like_partner": (
            f"Paper-like max abs top-5 difference {paper_like['top5_partner_share_diff_pp'].abs().max():.2f} pp; "
            f"max abs partner-Gini difference {paper_like['partner_gini_diff'].abs().max():.4f}."
        ),
    }
    return sensitivity_path, paper_like_path, paper_like, summaries


def build_raw_product_sensitivity(
    cache: dict[tuple[int, str], pd.DataFrame],
) -> tuple[Path, pd.DataFrame, dict[str, str]]:
    rows = []
    for flow, paper_g_col, paper_n_col in [
        ("Exports", "paper_export_product_gini", "paper_export_products"),
        ("Imports", "paper_import_product_gini", "paper_import_products"),
    ]:
        for paper_row in PAPER_TABLE_2.itertuples(index=False):
            reporter_code = COUNTRY_TO_REPORTER[paper_row.country]
            raw = raw_hs6_2001(reporter_code, flow, cache)
            variants = {
                "no_world_partner0": raw[raw["partner_code"].ne(0)],
                "with_world_partner0": raw,
            }
            for variant, frame in variants.items():
                values = frame.groupby("cmd_code")["trade_value"].sum()
                paper_gini = float(getattr(paper_row, paper_g_col))
                paper_count = int(getattr(paper_row, paper_n_col))
                modern_gini = gini(values)
                rows.append(
                    {
                        "country": paper_row.country,
                        "flow": flow,
                        "variant": variant,
                        "paper_product_count": paper_count,
                        "modern_product_count": int((values > 0).sum()),
                        "product_count_diff": int((values > 0).sum()) - paper_count,
                        "paper_product_gini": paper_gini,
                        "modern_product_gini": modern_gini,
                        "product_gini_diff": modern_gini - paper_gini,
                    }
                )
    sensitivity = pd.DataFrame(rows)
    path = write_csv(sensitivity, TABLES / "product_concentration_raw_variant_sensitivity.csv")
    no_world = sensitivity[sensitivity["variant"].eq("no_world_partner0")]
    summaries = {
        "product_sensitivity": (
            f"No-world raw product construction still has median active-count gap "
            f"{no_world['product_count_diff'].abs().median():.0f} and max gap "
            f"{no_world['product_count_diff'].abs().max():.0f}; "
            f"median abs product-Gini gap is {no_world['product_gini_diff'].abs().median():.4f}."
        )
    }
    return path, sensitivity, summaries


def parse_wco_hs1996_to_2002_mapping(text: str) -> pd.DataFrame:
    """Parse WCO Table II, correlating HS 1996 subheadings to HS 2002."""
    pattern = re.compile(r"(?:ex\s*)?(\d{4})\.(\d{2})")
    rows: list[dict[str, object]] = []
    current_h1: str | None = None
    target_order = 0
    for line in text.splitlines():
        if "Copyright" in line or "VERSION" in line or "TABLE" in line:
            continue
        matches = list(pattern.finditer(line))
        if not matches:
            continue
        left_code = None
        right_codes: list[str] = []
        for match in matches:
            code = f"{match.group(1)}{match.group(2)}"
            if match.start() < 45 and left_code is None:
                left_code = code
            else:
                right_codes.append(code)
        if left_code is not None:
            current_h1 = left_code
            target_order = 0
        if current_h1 is None:
            continue
        for code in right_codes:
            target_order += 1
            rows.append({"h1_code": current_h1, "h2_code": code, "target_order": target_order})
    mapping = pd.DataFrame(rows).drop_duplicates(["h1_code", "h2_code"]).reset_index(drop=True)
    if mapping.empty:
        raise RuntimeError("Parsed WCO HS1996-HS2002 concordance is empty.")
    return mapping


def load_wco_hs1996_to_2002_mapping() -> tuple[pd.DataFrame, list[Path], dict[str, object]]:
    pdf_path = SOURCE_DIR / "wco_hs1996_to_2002_table_ii.pdf"
    text_path = SOURCE_DIR / "wco_hs1996_to_2002_table_ii.txt"
    mapping_path = TABLES / "hs1996_to_hs2002_wco_table_ii_mapping.csv"
    meta: dict[str, object] = {
        "url": SOURCES["wco_hs1996_2002_correlation"],
        "pdf_path": rel(pdf_path),
        "text_path": rel(text_path),
        "mapping_path": rel(mapping_path),
    }
    try:
        if not pdf_path.exists():
            response = requests.get(SOURCES["wco_hs1996_2002_correlation"], timeout=30)
            response.raise_for_status()
            pdf_path.write_bytes(response.content)
            meta["download_status"] = "downloaded"
        else:
            meta["download_status"] = "reused_existing"
        subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), str(text_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        mapping = parse_wco_hs1996_to_2002_mapping(text_path.read_text())
        h1_lookup = load_product_lookup_for_revision("H1")
        h2_lookup = load_product_lookup_for_revision("H2")
        mapping["h1_description"] = mapping["h1_code"].map(h1_lookup).fillna("")
        mapping["h2_description"] = mapping["h2_code"].map(h2_lookup).fillna("")
        write_csv(mapping, mapping_path)
        meta.update(
            {
                "status": "available",
                "pdf_sha256": sha256_file(pdf_path),
                "mapping_rows": int(len(mapping)),
                "h1_codes_with_changes": int(mapping["h1_code"].nunique()),
                "h2_target_codes": int(mapping["h2_code"].nunique()),
            }
        )
        return mapping, [pdf_path, text_path, mapping_path], meta
    except Exception as exc:
        if mapping_path.exists():
            cached = pd.read_csv(mapping_path, dtype={"h1_code": "string", "h2_code": "string"})
            cached["h1_code"] = cached["h1_code"].astype(str).str.extract(r"(\d{1,6})", expand=False).str.zfill(6)
            cached["h2_code"] = cached["h2_code"].astype(str).str.extract(r"(\d{1,6})", expand=False).str.zfill(6)
            meta.update(
                {
                    "status": "available_from_cached_mapping_after_error",
                    "error": str(exc),
                    "mapping_sha256": sha256_file(mapping_path),
                    "mapping_rows": int(len(cached)),
                    "h1_codes_with_changes": int(cached["h1_code"].nunique()),
                    "h2_target_codes": int(cached["h2_code"].nunique()),
                }
            )
            return cached, [mapping_path], meta
        meta.update({"status": "blocked", "error": str(exc)})
        return pd.DataFrame(columns=["h1_code", "h2_code", "target_order"]), [], meta


def build_table2_hs2002_concordance_variant(
    cache: dict[tuple[int, str], pd.DataFrame],
    mapping: pd.DataFrame,
) -> tuple[Path, Path, pd.DataFrame, dict[str, str]]:
    first_target = (
        mapping.sort_values(["h1_code", "target_order"])
        .drop_duplicates("h1_code")
        .set_index("h1_code")["h2_code"]
        .to_dict()
    )
    rows = []
    threshold_rows = []
    thresholds = [0, 10, 100, 500, 1000]
    for flow, paper_g_col, paper_n_col in [
        ("Exports", "paper_export_product_gini", "paper_export_products"),
        ("Imports", "paper_import_product_gini", "paper_import_products"),
    ]:
        for paper_row in PAPER_TABLE_2.itertuples(index=False):
            reporter_code = COUNTRY_TO_REPORTER[paper_row.country]
            raw = raw_hs6_2001(reporter_code, flow, cache)
            raw = raw[raw["partner_code"].ne(0)].copy()
            raw["concordance_code"] = raw["cmd_code"].map(first_target).fillna(raw["cmd_code"])
            values = raw.groupby("concordance_code")["trade_value"].sum()
            baseline_values = raw.groupby("cmd_code")["trade_value"].sum()
            paper_gini = float(getattr(paper_row, paper_g_col))
            paper_count = int(getattr(paper_row, paper_n_col))
            modern_gini = gini(values)
            baseline_count_diff = int((baseline_values > 0).sum()) - paper_count
            baseline_gini_diff = gini(baseline_values) - paper_gini
            rows.append(
                {
                    "country": paper_row.country,
                    "flow": flow,
                    "variant": "wco_hs1996_to_hs2002_first_listed_target",
                    "paper_product_count": paper_count,
                    "modern_product_count": int((values > 0).sum()),
                    "product_count_diff": int((values > 0).sum()) - paper_count,
                    "baseline_h1_product_count_diff": baseline_count_diff,
                    "paper_product_gini": paper_gini,
                    "modern_product_gini": modern_gini,
                    "product_gini_diff": modern_gini - paper_gini,
                    "baseline_h1_product_gini_diff": baseline_gini_diff,
                }
            )
            for threshold in thresholds:
                threshold_values = values[values > threshold]
                threshold_rows.append(
                    {
                        "country": paper_row.country,
                        "flow": flow,
                        "threshold_usd": threshold,
                        "paper_product_count": paper_count,
                        "modern_product_count": int((threshold_values > 0).sum()),
                        "product_count_diff": int((threshold_values > 0).sum()) - paper_count,
                        "paper_product_gini": paper_gini,
                        "modern_product_gini": gini(threshold_values),
                        "product_gini_diff": gini(threshold_values) - paper_gini,
                    }
                )
    comparison = pd.DataFrame(rows)
    threshold_sensitivity = pd.DataFrame(threshold_rows)
    path = write_csv(comparison, TABLES / "table_2_product_concentration_hs2002_concordance_comparison.csv")
    threshold_path = write_csv(
        threshold_sensitivity,
        TABLES / "table_2_product_concentration_hs2002_threshold_sensitivity.csv",
    )
    baseline_mean_count = comparison["baseline_h1_product_count_diff"].abs().mean()
    concordance_mean_count = comparison["product_count_diff"].abs().mean()
    baseline_median_count = comparison["baseline_h1_product_count_diff"].abs().median()
    concordance_median_count = comparison["product_count_diff"].abs().median()
    threshold_summary = (
        threshold_sensitivity.groupby("threshold_usd")
        .agg(
            mean_abs_count=("product_count_diff", lambda values: values.abs().mean()),
            median_abs_count=("product_count_diff", lambda values: values.abs().median()),
            mean_abs_gini=("product_gini_diff", lambda values: values.abs().mean()),
        )
        .reset_index()
    )
    best_threshold = threshold_summary.sort_values(
        ["mean_abs_count", "mean_abs_gini", "threshold_usd"]
    ).iloc[0]
    summaries = {
        "table2_hs2002_concordance": (
            "WCO HS1996-to-HS2002 first-listed-target aggregation lowers mean abs product-count gap "
            f"from {baseline_mean_count:.1f} to {concordance_mean_count:.1f} and median abs gap "
            f"from {baseline_median_count:.1f} to {concordance_median_count:.1f}; "
            f"mean abs Gini gap is {comparison['product_gini_diff'].abs().mean():.4f}."
        ),
        "table2_hs2002_threshold_sensitivity": (
            f"Adding a ${best_threshold['threshold_usd']:.0f} post-concordance value floor gives the lowest "
            f"mean abs count gap ({best_threshold['mean_abs_count']:.1f}) in the tested grid, "
            "but no paper source supports imposing that floor."
        ),
    }
    return path, threshold_path, comparison, summaries


def hs2002_first_target_lookup(mapping: pd.DataFrame) -> dict[str, str]:
    if mapping.empty:
        raise RuntimeError("WCO HS1996-to-HS2002 mapping is required for Prof P top-share artifacts.")
    return (
        mapping.sort_values(["h1_code", "target_order"])
        .drop_duplicates("h1_code")
        .set_index("h1_code")["h2_code"]
        .to_dict()
    )


def prof_p_hs2002_product_values(
    reporter_code: int,
    flow: str,
    cache: dict[tuple[int, str], pd.DataFrame],
    first_target: dict[str, str],
) -> pd.Series:
    raw = raw_hs6_2001(reporter_code, flow, cache)
    raw = raw[raw["partner_code"].ne(0)].copy()
    raw["concordance_code"] = raw["cmd_code"].map(first_target).fillna(raw["cmd_code"])
    values = raw.groupby("concordance_code")["trade_value"].sum()
    values = values[pd.to_numeric(values, errors="coerce") > 0]
    if pd.Series(values.index.astype(str)).str.zfill(6).eq("999999").any():
        raise RuntimeError(f"HS6 999999 survived Prof P product aggregation for reporter {reporter_code} {flow}")
    return values


def build_prof_p_top_share_site_artifacts(
    cache: dict[tuple[int, str], pd.DataFrame],
    mapping: pd.DataFrame,
    country_panel: pd.DataFrame,
) -> tuple[Path, Path]:
    first_target = hs2002_first_target_lookup(mapping)
    iso_lookup = country_panel.drop_duplicates("country").set_index("country")["iso3"].to_dict()
    reporter_lookup = country_panel.drop_duplicates("country").set_index("country")["reporter_code"].to_dict()
    rows: list[dict[str, object]] = []
    lorenz_rows: list[dict[str, object]] = []
    lorenz_countries = {"India", "China", "United States"}
    note = "Professor P Table 2 reports Gini/count only; top-share columns are modern computed values."

    for paper_row in PAPER_TABLE_2.itertuples(index=False):
        country = str(paper_row.country)
        reporter_code = int(reporter_lookup.get(country, COUNTRY_TO_REPORTER[country]))
        for flow, paper_g_col, paper_n_col in [
            ("Exports", "paper_export_product_gini", "paper_export_products"),
            ("Imports", "paper_import_product_gini", "paper_import_products"),
        ]:
            values = prof_p_hs2002_product_values(reporter_code, flow, cache, first_target)
            active_count = int((values > 0).sum())
            modern_gini = gini(values)
            paper_gini = float(getattr(paper_row, paper_g_col))
            paper_count = int(getattr(paper_row, paper_n_col))
            rows.append(
                {
                    "country": country,
                    "iso3": iso_lookup.get(country, ""),
                    "reporter_code": reporter_code,
                    "year": 2001,
                    "flow": flow,
                    "sample": "prof_p_33",
                    "product_universe": "active_positive_hs6_products_hs1996_to_hs2002_first_listed_target",
                    "partner_world_aggregate_excluded": True,
                    "modern_top_1pct_product_share": active_top_share(values, pct=0.01),
                    "modern_top_5pct_product_share": active_top_share(values, pct=0.05),
                    "top_1pct_cutoff_products": top_pct_cutoff(active_count, 0.01),
                    "top_5pct_cutoff_products": top_pct_cutoff(active_count, 0.05),
                    "modern_product_gini": modern_gini,
                    "paper_product_gini": paper_gini,
                    "product_gini_diff": modern_gini - paper_gini,
                    "modern_active_products": active_count,
                    "paper_active_products": paper_count,
                    "active_products_diff": active_count - paper_count,
                    "comparison_note": note,
                }
            )
            if country in lorenz_countries:
                points = lorenz_points(values)
                for point_index, point in enumerate(points.itertuples(index=False)):
                    lorenz_rows.append(
                        {
                            "country": country,
                            "iso3": iso_lookup.get(country, ""),
                            "reporter_code": reporter_code,
                            "year": 2001,
                            "flow": flow,
                            "point_index": point_index,
                            "cum_products_share": round(float(point.cum_items), 12),
                            "cum_trade_value_share": round(float(point.cum_value), 12),
                        }
                    )

    top_share = pd.DataFrame(rows).sort_values(["flow", "country"]).reset_index(drop=True)
    expected_rows = len(PAPER_TABLE_2) * 2
    if len(top_share) != expected_rows:
        raise RuntimeError(f"Expected {expected_rows} Prof P top-share rows, found {len(top_share)}")
    lorenz = pd.DataFrame(lorenz_rows).sort_values(["flow", "country", "point_index"]).reset_index(drop=True)
    top_path = write_csv(top_share, PROF_P_TOP_SHARE_TABLE)
    lorenz_path = write_csv(lorenz, PROF_P_LORENZ_TABLE)
    return top_path, lorenz_path


def build_key_ordering_checks(
    table2_path: Path,
    table3_path: Path,
    table4_path: Path,
    paper_like_partner: pd.DataFrame,
) -> Path:
    t2 = pd.read_csv(table2_path)
    t3 = pd.read_csv(table3_path)
    t4 = pd.read_csv(table4_path)
    rows = []

    def pair_row(label: str, left: str, right: str, paper_left: float, paper_right: float, modern_left: float, modern_right: float) -> None:
        rows.append(
            {
                "claim": label,
                "left_country": left,
                "right_country": right,
                "paper_left": paper_left,
                "paper_right": paper_right,
                "paper_relation": ">" if paper_left > paper_right else "<=",
                "modern_left": modern_left,
                "modern_right": modern_right,
                "modern_relation": ">" if modern_left > modern_right else "<=",
                "replicates_ordering": (paper_left > paper_right) == (modern_left > modern_right),
            }
        )

    china2 = t2[t2["country"].eq("China")].iloc[0]
    india2 = t2[t2["country"].eq("India")].iloc[0]
    pair_row(
        "India vs China export product Gini",
        "India",
        "China",
        india2["paper_export_product_gini"],
        china2["paper_export_product_gini"],
        india2["modern_export_product_gini"],
        china2["modern_export_product_gini"],
    )
    pair_row(
        "India vs China import product Gini",
        "India",
        "China",
        india2["paper_import_product_gini"],
        china2["paper_import_product_gini"],
        india2["modern_import_product_gini"],
        china2["modern_import_product_gini"],
    )

    china3 = t3[t3["country"].eq("China")].iloc[0]
    india3 = t3[t3["country"].eq("India")].iloc[0]
    india3_like = paper_like_partner[(paper_like_partner["country"].eq("India")) & (paper_like_partner["flow"].eq("Exports"))].iloc[0]
    china3_like = paper_like_partner[(paper_like_partner["country"].eq("China")) & (paper_like_partner["flow"].eq("Exports"))].iloc[0]
    pair_row(
        "India vs China export partner Gini, clean no-world",
        "India",
        "China",
        india3["paper_export_partner_gini"],
        china3["paper_export_partner_gini"],
        india3["modern_export_partner_gini"],
        china3["modern_export_partner_gini"],
    )
    pair_row(
        "India vs China export partner Gini, paper-like world sensitivity",
        "India",
        "China",
        india3_like["paper_partner_gini"],
        china3_like["paper_partner_gini"],
        india3_like["modern_partner_gini"],
        china3_like["modern_partner_gini"],
    )

    china4 = t4[t4["country"].eq("China")].iloc[0]
    india4 = t4[t4["country"].eq("India")].iloc[0]
    pair_row(
        "India vs China import partner Gini, clean no-world",
        "India",
        "China",
        india4["paper_import_partner_gini"],
        china4["paper_import_partner_gini"],
        india4["modern_import_partner_gini"],
        china4["modern_import_partner_gini"],
    )
    return write_csv(pd.DataFrame(rows), TABLES / "key_qualitative_ordering_checks.csv")


def write_diagnosis_note(
    partner_sensitivity_path: Path,
    partner_like_path: Path,
    product_sensitivity_path: Path,
    ordering_path: Path,
    table2_concordance_path: Path | None,
    table2_threshold_path: Path | None,
    summaries: dict[str, str],
) -> Path:
    partner_like = pd.read_csv(partner_like_path)
    world_rows = partner_like[partner_like["variant"].eq("with_world_partner0")][
        ["country", "flow", "modern_partner_gini", "paper_partner_gini", "modern_top5_partner_share_pct", "paper_top5_partner_share_pct"]
    ]
    ordering = pd.read_csv(ordering_path)
    table2_concordance_summary = pd.DataFrame()
    if table2_concordance_path is not None and table2_concordance_path.exists():
        table2_concordance = pd.read_csv(table2_concordance_path)
        table2_concordance_summary = (
            table2_concordance.groupby("flow")
            .agg(
                baseline_mean_abs_count_diff=("baseline_h1_product_count_diff", lambda values: values.abs().mean()),
                concordance_mean_abs_count_diff=("product_count_diff", lambda values: values.abs().mean()),
                baseline_median_abs_count_diff=("baseline_h1_product_count_diff", lambda values: values.abs().median()),
                concordance_median_abs_count_diff=("product_count_diff", lambda values: values.abs().median()),
                concordance_max_abs_count_diff=("product_count_diff", lambda values: values.abs().max()),
                concordance_mean_abs_gini_diff=("product_gini_diff", lambda values: values.abs().mean()),
                concordance_max_abs_gini_diff=("product_gini_diff", lambda values: values.abs().max()),
            )
            .reset_index()
        )
    lines = [
        "# Prof P Replication Diagnosis",
        "",
        "## Main Diagnosis",
        "",
        "The default Table 3-4 rerun now uses all-commodity partner totals with the five largest actual partners in the numerator and `partnerCode == 0` (`World`) as the denominator. This is a uniform denominator convention; `World` is still excluded from the partner list, partner count, and partner Gini.",
        "",
        "The large remaining partner-concentration mismatch is not rounding. The six outlier rows only match the paper when `World` is counted as one of the partners in the top-five list. That is a paper-forensic diagnostic rather than the default economic construction.",
        "",
        "The product-count mismatch is different. Product Ginis are close, but active HS6 counts remain higher than the paper by roughly 125-170 products even after testing world/no-world raw variants. That points to Comtrade data-vintage or historical extraction differences rather than a simple filtering bug.",
        "",
        "The closest Table 2 diagnostic found so far is not a value threshold. It is a mechanical WCO HS1996-to-HS2002 concordance aggregation that maps changed 1996 HS6 codes to the first listed 2002 target, aggregating values that collapse to the same target. This reduces the active-product count gap sharply while leaving Ginis close, but it should be reported as a paper-like sensitivity because one-to-many HS splits cannot be uniquely allocated from 2001 H1 data.",
        "",
        "## Table 2 HS2002 Concordance Diagnostic",
        "",
        table_to_markdown(table2_concordance_summary, max_rows=10),
        "",
        "## World-Partner Rows That Match The Paper",
        "",
        table_to_markdown(world_rows, max_rows=20),
        "",
        "## Key Ordering Checks",
        "",
        table_to_markdown(ordering, max_rows=20),
        "",
        "## Diagnostic Files",
        "",
        f"- Partner sensitivity: `{rel(partner_sensitivity_path)}`",
        f"- Paper-like partner variant: `{rel(partner_like_path)}`",
        f"- Product sensitivity: `{rel(product_sensitivity_path)}`",
        f"- Table 2 HS2002 concordance: `{rel(table2_concordance_path) if table2_concordance_path else ''}`",
        f"- Table 2 HS2002 threshold sensitivity: `{rel(table2_threshold_path) if table2_threshold_path else ''}`",
        f"- Key ordering checks: `{rel(ordering_path)}`",
        "",
        "## Summary Stats",
        "",
    ]
    lines.extend(f"- {key}: {value}" for key, value in summaries.items())
    path = OUT / "replication_diagnosis.md"
    path.write_text("\n".join(lines) + "\n")
    return path


def is_code_column(column: str) -> bool:
    exact = {
        "cmd_code",
        "concordance_code",
        "h1_code",
        "h2_code",
        "item_code",
        "paper_code",
        "modern_code",
        "modern_rank_code",
    }
    if column in exact:
        return True
    return column.endswith("_cmd_code") or column.endswith("_item_code")


def scan_csv_code_columns_for_999999(paths: Iterable[Path]) -> pd.DataFrame:
    rows = []
    for path in paths:
        if path.suffix.lower() != ".csv":
            continue
        try:
            header = pd.read_csv(path, nrows=0)
        except Exception:
            continue
        cols = [col for col in header.columns if is_code_column(str(col))]
        if not cols:
            continue
        df = pd.read_csv(path, usecols=cols, dtype=str)
        for col in cols:
            count = int(normalize_hs6_series(df[col]).eq("999999").sum())
            rows.append({"path": rel(path), "column": col, "hs6_999999_rows": count})
    return pd.DataFrame(rows)


def write_report(
    inventory: pd.DataFrame,
    table_summaries: dict[str, str],
    appendix_summary: pd.DataFrame,
    textual: pd.DataFrame,
    world_claims_df: pd.DataFrame,
    manifest: dict,
) -> Path:
    status_counts = inventory["status"].value_counts().rename_axis("status").reset_index(name="targets")
    matrix = inventory[["target_id", "target_type", "status", "difference", "caveat", "output_path"]].copy()
    lines = [
        "# Prof P Paper Replication Inventory And Audit",
        "",
        f"Generated: {manifest['generated_at_utc']}",
        "",
        "## Summary",
        "",
        "This audit inventories every figure, table, appendix table, and numeric text claim from Panagariya and Bagaria's trade-concentration paper. It compares the paper's 2001 targets with this repository's modern UN Comtrade HS6 pipeline outputs after excluding HS6 `999999` upstream.",
        "",
        "US HS10 targets are not substituted with HS6 data. Figures 1-2 and Table 1 are marked blocked until the UC Davis CID HS10 source files are provided or parsed into a local schema.",
        "",
        "The large Table 3-4 partner-concentration discrepancies are now isolated in a separate diagnostic: six outlier rows match the paper only when Comtrade `partnerCode == 0` (`World`) is counted as a destination/source. The default rerun uses World only as the denominator and excludes World from the partner list, partner count, and partner Gini.",
        "",
        "For Table 2, the closest diagnostic is a WCO HS1996-to-HS2002 concordance aggregation. It reduces the active-product count gap substantially while preserving close product Ginis, but it remains a paper-like sensitivity because one-to-many HS revision changes require a convention.",
        "",
        "## Status Matrix",
        "",
        table_to_markdown(status_counts, max_rows=20),
        "",
        table_to_markdown(matrix, max_rows=80),
        "",
        "## Main Table Diagnostics",
        "",
    ]
    for key, value in table_summaries.items():
        lines.append(f"- {key}: {value}")
    lines.extend(
        [
            "",
            "## Appendix Top-25 Diagnostics",
            "",
            table_to_markdown(appendix_summary, max_rows=20),
            "",
            "## Textual Claims",
            "",
            table_to_markdown(textual[["claim_id", "paper_value", "modern_value", "status"]], max_rows=20),
            "",
            "## World Trade Claims",
            "",
            table_to_markdown(world_claims_df[["claim_id", "paper_value", "status", "notes"]], max_rows=20),
            "",
            "## Data Sources",
            "",
        ]
    )
    for label, source in SOURCES.items():
        lines.append(f"- {label}: {source}")
    lines.extend(
        [
            "",
            "## Caveats",
            "",
            "- Modern Comtrade vintages and project-required `999999` exclusion can produce legitimate differences from the 2013 paper's reported values.",
            "- The Table 2 HS2002 concordance diagnostic is closer than the clean H1 product-count rerun, but it should not replace the clean table unless the intended replication convention is explicitly to harmonize 2001 H1 codes forward to HS2002.",
            "- The largest clean partner-concentration discrepancies are explained by whether `partnerCode == 0` (`World`) is included for selected countries; remaining differences look like vintage or source-extract drift.",
            "- Full world-trade claims require all-world 2001 HS6 data; the canonical local processed panel is the 33-country Prof P sample.",
        ]
    )
    path = OUT / "prof_p_replication_report.md"
    path.write_text("\n".join(lines) + "\n")
    return path


def run_self_tests() -> None:
    assert abs(gini([1, 1, 1]) - 0.0) < 1e-12
    assert abs(gini([1, 2, 3]) - 2 / 9) < 1e-12
    assert abs(top_n_share([1, 2, 3], 1) - 0.5) < 1e-12
    assert top_pct_cutoff(4592, 0.01) == 46
    assert top_pct_cutoff(4592, 0.05) == 230
    assert abs(bottom_half_share([1, 2, 3, 4]) - 0.3) < 1e-12
    pts = lorenz_points([1, 1, 2])
    assert pts.iloc[0]["cum_items"] == 0
    assert abs(pts.iloc[-1]["cum_value"] - 1.0) < 1e-12
    sample = pd.DataFrame({"cmd_code": ["999999", "000001"], "x": [1, 2]})
    assert len(drop_999999(sample)) == 1
    print("self-tests passed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="Run internal utility tests and exit.")
    parser.add_argument("--download-hs10", action="store_true", help="Attempt advisory downloads of discovered UC Davis CID 2001 links.")
    args = parser.parse_args()

    if args.self_test:
        run_self_tests()
        return

    ensure_dirs()
    inventory: list[InventoryRow] = []
    written_paths: list[Path] = []

    if not CONCENTRATION_PATH.exists():
        raise FileNotFoundError(CONCENTRATION_PATH)
    concentration = pd.read_parquet(CONCENTRATION_PATH)
    country_panel = pd.read_csv(COUNTRY_PANEL_PATH)
    if set(PAPER_TABLE_2["country"]) - set(country_panel["country"]):
        missing = sorted(set(PAPER_TABLE_2["country"]) - set(country_panel["country"]))
        raise RuntimeError(f"Prof P country panel is missing countries: {missing}")

    lookup = load_product_lookup()

    table1_path = write_csv(PAPER_TABLE_1, TABLES / "table_1_hs10_paper_reference_blocked.csv")
    written_paths.append(table1_path)
    table1_gini_path = OUT / "table_1_hs10_paper_ginis.json"
    table1_gini_path.write_text(json.dumps(PAPER_TABLE_1_GINIS, indent=2, sort_keys=True) + "\n")
    written_paths.append(table1_gini_path)

    hs10_discovery = discover_hs10_cid_links(download=args.download_hs10)
    hs10_path = OUT / "hs10_cid_discovery.json"
    hs10_path.write_text(json.dumps(hs10_discovery, indent=2, sort_keys=True) + "\n")
    written_paths.append(hs10_path)

    for figure_id in ["Figure 1", "Figure 2"]:
        inventory.append(
            InventoryRow(
                figure_id,
                "figure",
                "Section 2",
                "UC Davis CID 2001 US HS10 product-level trade data",
                "Paper reports US HS10 Lorenz curve; Figure 1 export Gini 0.827, Figure 2 import Gini 0.893.",
                "",
                "",
                "blocked",
                "HS10 source files are not present locally; HS6 diagnostic is generated separately and not treated as a substitute.",
                rel(hs10_path),
            )
        )
    inventory.append(
        InventoryRow(
            "Table 1",
            "table",
            "Section 2",
            "UC Davis CID 2001 US HS10 product-level trade data with two-way-trade split",
            "Paper Table 1 shares/counts/Ginis",
            "",
            "",
            "blocked",
            "Paper reference is transcribed, but exact replication is blocked without HS10 source files.",
            rel(table1_path),
        )
    )

    table_paths, table_summaries = compare_table_2_4(concentration)
    partner_world_paths, _partner_world_metrics, partner_world_summaries = build_partner_world_denominator_default()
    table_paths.update({key: value for key, value in partner_world_paths.items() if key in {"table_3", "table_4"}})
    table_summaries.update(partner_world_summaries)
    written_paths.extend(table_paths.values())
    written_paths.extend(path for key, path in partner_world_paths.items() if key not in {"table_3", "table_4"})
    raw_cache: dict[tuple[int, str], pd.DataFrame] = {}
    partner_sensitivity_path, paper_like_partner_path, paper_like_partner, partner_diagnostic_summaries = (
        build_raw_partner_sensitivity(raw_cache)
    )
    raw_cache.clear()
    release_memory_to_os()
    product_sensitivity_path, _product_sensitivity, product_diagnostic_summaries = build_raw_product_sensitivity(raw_cache)
    raw_cache.clear()
    release_memory_to_os()
    hs_mapping, hs_concordance_source_paths, hs_concordance_meta = load_wco_hs1996_to_2002_mapping()
    table2_concordance_path: Path | None = None
    table2_threshold_path: Path | None = None
    table2_concordance_summaries: dict[str, str] = {}
    if not hs_mapping.empty:
        (
            table2_concordance_path,
            table2_threshold_path,
            _table2_concordance,
            table2_concordance_summaries,
        ) = build_table2_hs2002_concordance_variant(raw_cache, hs_mapping)
        raw_cache.clear()
        release_memory_to_os()
    prof_p_top_share_path, prof_p_lorenz_path = build_prof_p_top_share_site_artifacts(raw_cache, hs_mapping, country_panel)
    raw_cache.clear()
    release_memory_to_os()
    ordering_path = build_key_ordering_checks(
        table_paths["table_2"],
        table_paths["table_3"],
        table_paths["table_4"],
        paper_like_partner,
    )
    diagnosis_summaries = (
        table_summaries
        | partner_diagnostic_summaries
        | product_diagnostic_summaries
        | table2_concordance_summaries
    )
    diagnosis_path = write_diagnosis_note(
        partner_sensitivity_path,
        paper_like_partner_path,
        product_sensitivity_path,
        ordering_path,
        table2_concordance_path,
        table2_threshold_path,
        diagnosis_summaries,
    )
    written_paths.extend(hs_concordance_source_paths)
    written_paths.extend([partner_sensitivity_path, paper_like_partner_path, product_sensitivity_path, ordering_path, diagnosis_path])
    if table2_concordance_path is not None:
        written_paths.append(table2_concordance_path)
    if table2_threshold_path is not None:
        written_paths.append(table2_threshold_path)
    written_paths.extend([prof_p_top_share_path, prof_p_lorenz_path])
    inventory.append(
        InventoryRow(
            "Table 2",
            "table",
            "Section 3",
            "UN Comtrade HS6 2001 33-country product totals",
            "33-country export/import product Ginis and active products",
            "Modern no-999999 values generated",
            table_summaries["table_2"],
            "mismatch",
            "Product Ginis are close overall. Raw sensitivity checks show active product counts remain higher after world-partner tests, pointing to Comtrade vintage/classification differences rather than a simple filtering error.",
            rel(table_paths["table_2"]),
        )
    )
    inventory.append(
        InventoryRow(
            "Prof P 2001 top-share website diagnostic",
            "diagnostic_table",
            "Website",
            "Raw UN Comtrade HS6 2001 product totals plus WCO HS1996-to-HS2002 correlation Table II",
            "33-country export/import top-1% and top-5% product shares with Table 2 Gini/count comparison",
            "Modern paper-like top-share values generated",
            "Top shares are computed diagnostics; Professor P Table 2 reports product Gini and active product counts only.",
            "generated",
            "Uses active positive HS6 products, excludes HS6 999999 upstream, excludes partnerCode 0, and aggregates changed HS1996 codes to first-listed HS2002 targets.",
            rel(prof_p_top_share_path),
        )
    )
    inventory.append(
        InventoryRow(
            "Table 2 HS2002 concordance sensitivity",
            "diagnostic_table",
            "Section 3",
            "Raw UN Comtrade HS6 2001 product totals plus WCO HS1996-to-HS2002 correlation Table II",
            "33-country export/import product Ginis and active products",
            "Paper-like concordance values generated" if table2_concordance_path else "",
            table2_concordance_summaries.get("table2_hs2002_concordance", ""),
            "close" if table2_concordance_path else "blocked",
            "This is a diagnostic convention: changed HS1996 codes are mapped to the first listed HS2002 target and then aggregated. It is closer for active counts but not proof that the paper used this exact convention.",
            rel(table2_concordance_path) if table2_concordance_path else "",
        )
    )
    inventory.append(
        InventoryRow(
            "Table 3",
            "table",
            "Section 3",
            "UN Comtrade HS6 2001 33-country export-destination totals",
            "33-country export partner Ginis/counts/top-5 shares",
            "Modern world-denominator partner values generated",
            table_summaries["table_3"],
            "mismatch",
            "Default uses top five actual partners divided by partnerCode 0 (`World`) total. Greece/India/Finland still diverge; the paper-like diagnostic matches only when `World` is counted as a top-five partner.",
            rel(table_paths["table_3"]),
        )
    )
    inventory.append(
        InventoryRow(
            "Table 4",
            "table",
            "Section 3",
            "UN Comtrade HS6 2001 33-country import-source totals",
            "33-country import partner Ginis/counts/top-5 shares",
            "Modern world-denominator partner values generated",
            table_summaries["table_4"],
            "mismatch",
            "Default uses top five actual partners divided by partnerCode 0 (`World`) total. Slovakia/Switzerland/Turkey still diverge; the paper-like diagnostic matches only when `World` is counted as a top-five partner.",
            rel(table_paths["table_4"]),
        )
    )
    inventory.append(
        InventoryRow(
            "Tables 3-4 world-partner sensitivity",
            "diagnostic_table",
            "Sections 3-4",
            "Raw UN Comtrade HS6 2001 partner totals with and without partnerCode 0",
            "Partner Ginis/counts/top-5 shares in Tables 3-4",
            "Paper-like best-of no-world/with-world variant generated",
            partner_diagnostic_summaries["paper_like_partner"],
            "close",
            "This is a diagnostic replication convention, not the preferred clean economic measure; it identifies the rows where the paper appears to include the World aggregate as a partner.",
            rel(paper_like_partner_path),
        )
    )

    t56_paths, t56_summaries = compare_tables_5_6(lookup)
    written_paths.extend(t56_paths.values())
    inventory.append(
        InventoryRow(
            "Table 5",
            "table",
            "Section 4",
            "US 2001 HS6 export product-destination cells",
            "Top four US export products, destination concentration",
            "Modern no-999999 values generated",
            t56_summaries["table_5"],
            "close",
            "Computed on current Comtrade aggregate checkpoints; compare rows for product-level differences.",
            rel(t56_paths["table_5_summary"]),
        )
    )
    inventory.append(
        InventoryRow(
            "Table 6",
            "table",
            "Section 4",
            "US 2001 HS6 import product-source cells",
            "Top four US import products, source concentration",
            "Modern no-999999 values generated",
            t56_summaries["table_6"],
            "close",
            "Computed on current Comtrade aggregate checkpoints; compare rows for product-level differences.",
            rel(t56_paths["table_6_summary"]),
        )
    )

    table7_path, table7_summary = compare_table_7()
    written_paths.append(table7_path)
    inventory.append(
        InventoryRow(
            "Table 7",
            "table",
            "Section 4",
            "US 2001 HS6 product cells with Canada, Mexico, and Japan",
            "Bilateral export/import product Ginis/counts/top-200 shares",
            "Modern no-999999 values generated",
            table7_summary,
            "mismatch",
            "Computed on current Comtrade aggregate checkpoints; modern partner/product totals need not exactly match the paper vintage.",
            rel(table7_path),
        )
    )

    appendix_paths, appendix_summary = compare_appendix_tables(lookup)
    written_paths.extend(appendix_paths)
    for row in appendix_summary.itertuples(index=False):
        status = "close" if row.rank_code_matches >= 20 else "mismatch"
        inventory.append(
            InventoryRow(
                f"Table {row.table_id}",
                "appendix_table",
                "Appendix",
                f"{row.country} 2001 HS6 {row.flow.lower()} product totals",
                "Top 25 product codes/descriptions/values",
                f"{row.rank_code_matches}/25 same-rank code matches; {row.paper_codes_in_modern_top25}/25 paper codes in modern top 25",
                f"max abs value diff for paper code {row.max_abs_value_diff_for_paper_code_billion:.3f} billion USD",
                status,
                "Comparison is rank/code/value based against current no-999999 product totals.",
                row.output_path,
            )
        )

    textual = textual_claim_checks(concentration)
    textual_path = write_csv(textual, TABLES / "textual_claims_modern_check.csv")
    written_paths.append(textual_path)
    for row in textual.itertuples(index=False):
        inventory.append(
            InventoryRow(
                row.claim_id,
                "text_claim",
                "Summary/Text",
                "2001 and 1990 concentration panels",
                row.paper_value,
                row.modern_value,
                "",
                row.status,
                row.notes,
                rel(textual_path),
            )
        )

    world_df = world_trade_claims()
    world_path = write_csv(world_df, TABLES / "world_trade_claims_blocked.csv")
    written_paths.append(world_path)
    for row in world_df.itertuples(index=False):
        inventory.append(
            InventoryRow(
                row.claim_id,
                "world_text_claim",
                "Section 6",
                "All-world 2001 HS6 trade totals",
                row.paper_value,
                row.modern_value,
                "",
                row.status,
                row.notes,
                rel(world_path),
            )
        )

    lorenz_path = build_lorenz_figure(concentration)
    written_paths.append(lorenz_path)

    scan = scan_csv_code_columns_for_999999(written_paths)
    scan_path = write_csv(scan, TABLES / "output_code_column_999999_scan.csv")
    written_paths.append(scan_path)
    if not scan.empty and int(scan["hs6_999999_rows"].sum()) != 0:
        raise RuntimeError(f"Generated outputs contain HS6 999999 rows; see {scan_path}")

    inventory_df = pd.DataFrame([row.__dict__ for row in inventory])
    inventory_path = write_csv(inventory_df, OUT / "replication_inventory.csv")
    written_paths.append(inventory_path)

    manifest = {
        "generated_at_utc": now_utc(),
        "script": rel(Path(__file__)),
        "paper_pdf": rel(PAPER_PDF),
        "paper_pdf_sha256": sha256_file(PAPER_PDF),
        "sources": SOURCES,
        "inputs": {
            "concentration_all_years": {
                "path": rel(CONCENTRATION_PATH),
                "sha256": sha256_file(CONCENTRATION_PATH),
                "rows": int(len(concentration)),
                "year_min": int(concentration["year"].min()),
                "year_max": int(concentration["year"].max()),
            },
            "export_aggregates": {
                "path": rel(EXPORT_AGG_PATH),
                "sha256": sha256_file(EXPORT_AGG_PATH),
            },
            "import_aggregate_dir": rel(IMPORT_AGG_DIR),
            "country_panel": {
                "path": rel(COUNTRY_PANEL_PATH),
                "sha256": sha256_file(COUNTRY_PANEL_PATH),
                "rows": int(len(country_panel)),
            },
        },
        "hs10_data_acquisition": hs10_discovery,
        "hs1996_to_hs2002_concordance": hs_concordance_meta,
        "outputs": [rel(path) for path in written_paths],
        "hs6_999999_scan": {
            "path": rel(scan_path),
            "total_exact_999999_rows_in_code_columns": 0 if scan.empty else int(scan["hs6_999999_rows"].sum()),
        },
        "inventory_status_counts": inventory_df["status"].value_counts().to_dict(),
    }
    report_path = write_report(
        inventory_df,
        diagnosis_summaries | t56_summaries | {"table_7": table7_summary},
        appendix_summary,
        textual,
        world_df,
        manifest,
    )
    written_paths.append(report_path)
    manifest["outputs"] = [rel(path) for path in written_paths]
    manifest_path = OUT / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    print(f"Wrote {rel(inventory_path)}")
    print(f"Wrote {rel(report_path)}")
    print(f"Wrote {rel(manifest_path)}")


if __name__ == "__main__":
    main()
