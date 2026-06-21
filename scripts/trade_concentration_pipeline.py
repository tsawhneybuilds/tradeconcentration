#!/usr/bin/env python3
"""
Real-data pipeline for Exercises 1, 2, 3, 4, 6, 10, 11, and 12.

Primary source: UN Comtrade final annual merchandise HS bulk files.

The script deliberately stops before analysis when no Comtrade subscription key
is available. That matches the project rule: do not substitute non-equivalent
or inferred trade values for the required HS6 reporter-product-partner data.
"""

from __future__ import annotations

import argparse
import gc
import gzip
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import requests

from concentration_metrics import active_gini, active_top_share

try:
    import comtradeapicall
except ImportError:  # pragma: no cover - handled at runtime for user clarity
    comtradeapicall = None


ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data" / "raw"
COMTRADE_RAW = DATA_RAW / "comtrade"
COMTRADE_BULK = COMTRADE_RAW / "bulk"
COMTRADE_H24_WORLD_BULK = COMTRADE_RAW / "h24_world_bulk"
COMTRADE_AVAILABILITY = COMTRADE_RAW / "availability"
WORLD_BANK_RAW = DATA_RAW / "world_bank_gdp"
CLASSIFICATION_RAW = DATA_RAW / "classifications"
DATA_PROCESSED = ROOT / "data" / "processed"
RESULTS = ROOT / "results"
EX01_TABLES = RESULTS / "exercise_01_tables"
EX01_FIGURES = RESULTS / "exercise_01_figures"
EX02_TABLES = RESULTS / "exercise_02_tables"
EX02_FIGURES = RESULTS / "exercise_02_figures"
EX03_TABLES = RESULTS / "exercise_03_tables"
EX03_FIGURES = RESULTS / "exercise_03_figures"
EX04_TABLES = RESULTS / "exercise_04_tables"
EX04_FIGURES = RESULTS / "exercise_04_figures"
EX06_TABLES = RESULTS / "exercise_06_tables"
EX06_FIGURES = RESULTS / "exercise_06_figures"
EX10_TABLES = RESULTS / "exercise_10_tables"
EX10_FIGURES = RESULTS / "exercise_10_figures"
EX11_TABLES = RESULTS / "exercise_11_tables"
EX11_FIGURES = RESULTS / "exercise_11_figures"
EX12_TABLES = RESULTS / "exercise_12_tables"
EX12_FIGURES = RESULTS / "exercise_12_figures"
OECD_ICIO_RAW = DATA_RAW / "oecd_icio"
SAMPLE_PROCESSED_ROOT = DATA_PROCESSED / "samples"
BASE_EX03_PARTIAL_DIR = DATA_PROCESSED / "exercise_03_file_aggregates"
EX03_PARTIAL_DIR = BASE_EX03_PARTIAL_DIR
EX03_PRODUCT_PARTIAL_DIR = EX03_PARTIAL_DIR / "product_values"
EX03_COVERAGE_PARTIAL_DIR = EX03_PARTIAL_DIR / "mapping_coverage"
BASE_EX04_PARTIAL_DIR = DATA_PROCESSED / "exercise_04_file_aggregates"
EX04_PARTIAL_DIR = BASE_EX04_PARTIAL_DIR
BASE_EX11_PARTIAL_DIR = DATA_PROCESSED / "exercise_11_file_aggregates"
EX11_PARTIAL_DIR = BASE_EX11_PARTIAL_DIR
EX11_IMPORT_PARTIAL_DIR = EX11_PARTIAL_DIR / "import_cells"
EX11_EXPORT_PARTIAL_DIR = EX11_PARTIAL_DIR / "export_sectors"
EX11_COVERAGE_PARTIAL_DIR = EX11_PARTIAL_DIR / "mapping_coverage"
EX11_SECTOR_BRIDGE_CANDIDATES = [
    OECD_ICIO_RAW / "oecd_btige_hs_to_sector_bridge.csv",
    OECD_ICIO_RAW / "oecd_btige_hs_to_sector_bridge.parquet",
    OECD_ICIO_RAW / "oecd_btige_hs_to_sector_bridge.xlsx",
]
EX11_INPUT_REQUIREMENTS_CANDIDATES = [
    OECD_ICIO_RAW / "oecd_icio_imported_input_requirements.csv",
    OECD_ICIO_RAW / "oecd_icio_imported_input_requirements.parquet",
    OECD_ICIO_RAW / "oecd_icio_imported_input_requirements.xlsx",
]

EX10_DIMENSIONS = {
    "product": ["cmd_code"],
    "partner": ["partner_code"],
    "product_partner_cell": ["cmd_code", "partner_code"],
}

EX10_TOP_METRICS = {
    "top_1_share": 1,
    "top_5_share": 5,
    "top_10_share": 10,
}

EX03_RESEARCH_BINS = ["energy", "intermediates", "capital_goods", "final_consumption"]
EXCLUDED_HS6_CODES = {"999999"}
EXCLUDED_HS6_LABELS = {"999999": "Commodities not specified"}
HS_REVISION_SEQUENCE = tuple(f"H{idx}" for idx in range(7))
HS_REVISION_LABELS = {
    "H0": "HS1992",
    "H1": "HS1996",
    "H2": "HS2002",
    "H3": "HS2007",
    "H4": "HS2012",
    "H5": "HS2017",
    "H6": "HS2022",
}
HS_HARMONIZATION_VERSION = "wco_adjacent_v1_oversized_cap"
HS_HARMONIZATION_MAX_FAMILY_NODES = int(os.getenv("EX12_HS_HARMONIZATION_MAX_FAMILY_NODES", "100"))
HS_HARMONIZATION_RAW = CLASSIFICATION_RAW / "hs_revision_correlations"
HS_HARMONIZATION_MAPPING_PATH = DATA_PROCESSED / "hs6_harmonized_families.csv"
LT_HGL_DATASET_DOI = "10.7910/DVN/6AADMR"
LT_HGL_DATASET_URL = f"https://doi.org/{LT_HGL_DATASET_DOI}"
LT_HGL_DATASET_VERSION = "2.1"
LT_HGL_TARGET_REVISION = "H0"
LT_HGL_TARGET_LABEL = "HS1992"
LT_HGL_WEIGHT_RAW = CLASSIFICATION_RAW / "lt_hgl_weighted_conversion_tables"
LT_HGL_NORMALIZED_WEIGHTS_PATH = DATA_PROCESSED / "lt_hgl_hs6_to_hs1992_weights.parquet"
LT_HGL_NORMALIZED_WEIGHTS_CSV = DATA_PROCESSED / "lt_hgl_hs6_to_hs1992_weights.csv"
LT_HGL_NORMALIZED_WEIGHTS_MANIFEST = DATA_PROCESSED / "lt_hgl_hs6_to_hs1992_weights_manifest.json"
LT_HGL_WEIGHT_TOLERANCE = float(os.getenv("LT_HGL_WEIGHT_TOLERANCE", "0.000001"))
LT_HGL_RAW_WEIGHT_TOLERANCE = float(os.getenv("LT_HGL_RAW_WEIGHT_TOLERANCE", "0.05"))
LT_HGL_HS_BACKWARD_SPECS = (
    {
        "source_revision": "H1",
        "source_label": "HS1996",
        "target_revision": "H0",
        "target_label": "HS1992",
        "filename": "hs96_to_hs92.csv",
        "dataverse_file_id": 13438071,
        "md5": "16a9b1ccffff740ecf1e0da9971eecc5",
    },
    {
        "source_revision": "H2",
        "source_label": "HS2002",
        "target_revision": "H1",
        "target_label": "HS1996",
        "filename": "hs02_to_hs96.csv",
        "dataverse_file_id": 13438079,
        "md5": "06fb6a9409a6e772fb0357e260b68a84",
    },
    {
        "source_revision": "H3",
        "source_label": "HS2007",
        "target_revision": "H2",
        "target_label": "HS2002",
        "filename": "hs07_to_hs02.csv",
        "dataverse_file_id": 13438068,
        "md5": "44dae73c38949f685fd3f9ba804ae968",
    },
    {
        "source_revision": "H4",
        "source_label": "HS2012",
        "target_revision": "H3",
        "target_label": "HS2007",
        "filename": "hs12_to_hs07.csv",
        "dataverse_file_id": 13438085,
        "md5": "0e7467593521637db5e1acec15527c5e",
    },
    {
        "source_revision": "H5",
        "source_label": "HS2017",
        "target_revision": "H4",
        "target_label": "HS2012",
        "filename": "hs17_to_hs12.csv",
        "dataverse_file_id": 13438081,
        "md5": "051851b27d6a3e12e620335d4b1cbefa",
    },
    {
        "source_revision": "H6",
        "source_label": "HS2022",
        "target_revision": "H5",
        "target_label": "HS2017",
        "filename": "hs22_to_hs17.csv",
        "dataverse_file_id": 13438073,
        "md5": "18d444928f134b94e5bb9aa30ab3d90b",
    },
)
HS_WCO_CORRELATION_SPECS = (
    {
        "source_revision": "H1",
        "target_revision": "H2",
        "source_label": "WCO Table II, HS1996 to HS2002",
        "url": "https://www.wcoomd.org/-/media/wco/public/global/pdf/topics/nomenclature/instruments-and-tools/hs-nomenclature-older-edition/2002/correlations-1996-2002/hs_correlation2002_table2_eng.pdf?la=en",
    },
    {
        "source_revision": "H2",
        "target_revision": "H3",
        "source_label": "WCO Table II, HS2002 to HS2007",
        "url": "https://www.wcoomd.org/-/media/wco/public/global/pdf/topics/nomenclature/instruments-and-tools/hs-nomenclature-older-edition/2007/correlations-2002-2007/hs_correlation2007_table_ii_e_rev4cor.pdf?la=en",
    },
    {
        "source_revision": "H3",
        "target_revision": "H4",
        "source_label": "WCO Table II, HS2007 to HS2012",
        "url": "https://www.wcoomd.org/-/media/wco/public/global/pdf/topics/nomenclature/instruments-and-tools/hs-nomenclature-2012/correlations-2007-2012/ii_trp0712rev3eng_fr.pdf?la=en",
    },
    {
        "source_revision": "H4",
        "target_revision": "H5",
        "source_label": "WCO Table II, HS2012 to HS2017",
        "url": "https://www.wcoomd.org/-/media/wco/public/global/pdf/topics/nomenclature/instruments-and-tools/hs-nomenclature-2017/2016/table_ii_trp1217_en_rev1.pdf?la=en",
    },
    {
        "source_revision": "H5",
        "target_revision": "H6",
        "source_label": "WCO Table II, HS2017 to HS2022",
        "url": "https://www.wcoomd.org/-/media/wco/public/global/pdf/topics/nomenclature/instruments-and-tools/hs-nomenclature-2022/table-ii_en.pdf?la=en",
    },
)

DEFAULT_CHUNK_ROWS = int(os.getenv("TRADE_PIPELINE_CHUNK_ROWS", "500000"))

COMTRADE_LEAF_COLUMN_KEYS = {
    "cmdcode",
    "commoditycode",
    "primaryvalue",
    "tradevalueus",
    "tradevalue",
    "fobvalue",
    "cifvalue",
    "reportercode",
    "period",
    "refyear",
    "year",
    "partnercode",
    "classificationcode",
    "flowcode",
    "tradeflowcode",
    "flowdesc",
    "tradeflow",
    "isaggregate",
    "reporteriso",
    "reporterdesc",
    "partneriso",
    "partnerdesc",
    "cmddesc",
}


@dataclass(frozen=True)
class Country:
    country: str
    iso3: str
    reporter_code: int


@dataclass(frozen=True)
class CountrySampleSettings:
    name: str = "prof_p_33"
    min_available_years: int = 10
    start_year: int = 1988
    end_year: int | None = None
    refresh_availability: bool = False


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

RD2_COUNTRY_ADDITIONS = [
    Country("Armenia", "ARM", 51),
    Country("Azerbaijan", "AZE", 31),
    Country("Botswana", "BWA", 72),
    Country("Burkina Faso", "BFA", 854),
    Country("Cambodia", "KHM", 116),
    Country("China, Hong Kong SAR", "HKG", 344),
    Country("Costa Rica", "CRI", 188),
    Country("Croatia", "HRV", 191),
    Country("Egypt", "EGY", 818),
    Country("Georgia", "GEO", 268),
    Country("Guyana", "GUY", 328),
    Country("Kyrgyzstan", "KGZ", 417),
    Country("Mauritania", "MRT", 478),
    Country("Morocco", "MAR", 504),
    Country("Mozambique", "MOZ", 508),
    Country("Niger", "NER", 562),
    Country("North Macedonia", "MKD", 807),
    Country("Panama", "PAN", 591),
    Country("Peru", "PER", 604),
    Country("Rwanda", "RWA", 646),
    Country("Senegal", "SEN", 686),
    Country("Singapore", "SGP", 702),
    Country("Slovenia", "SVN", 705),
    Country("South Africa", "ZAF", 710),
    Country("Uganda", "UGA", 800),
    Country("United Arab Emirates", "ARE", 784),
    Country("Zimbabwe", "ZWE", 716),
]
RD2_COUNTRIES = [*PROF_P_COUNTRIES, *RD2_COUNTRY_ADDITIONS]
RD2_REQUIRED_ISO3 = {country.iso3 for country in RD2_COUNTRY_ADDITIONS}

PROF_P_SAMPLE = "prof_p_33"
WORLD_BROAD_SAMPLE = "world_broad"
RD2_SAMPLE = "rd2_countries"
CADOT_BROAD_SAMPLE = "cadot_broad_156"
CADOT_ORIGINAL_SAMPLE = "cadot_original_1988_2006"
CADOT_ORIGINAL_EXTENDED_SAMPLE = "cadot_original_countries_extended"
CADOT_BROAD_START_YEAR = 2000
CADOT_BROAD_END_YEAR = 2024
CADOT_BROAD_MIN_AVAILABLE_YEARS = 19
CADOT_BROAD_EXPECTED_REPORTERS = 156
CADOT_ORIGINAL_START_YEAR = 1988
CADOT_ORIGINAL_END_YEAR = 2006
BROAD_COMTRADE_SAMPLE_NAMES = {WORLD_BROAD_SAMPLE, CADOT_BROAD_SAMPLE}
PUBLIC_ALL_REPORTER_AVAILABILITY_SAMPLE_NAMES = {WORLD_BROAD_SAMPLE, RD2_SAMPLE, CADOT_BROAD_SAMPLE}

COUNTRY_SAMPLE_CHOICES = (
    PROF_P_SAMPLE,
    WORLD_BROAD_SAMPLE,
    RD2_SAMPLE,
    CADOT_BROAD_SAMPLE,
    CADOT_ORIGINAL_SAMPLE,
    CADOT_ORIGINAL_EXTENDED_SAMPLE,
)
PIPELINE_EXERCISES = ["1", "2", "3", "4", "6", "10", "11", "12"]
COMTRADE_REPORTERS_URL = "https://comtradeapi.un.org/files/v1/app/reference/Reporters.json"
COMTRADE_REPORTERS_PATH = COMTRADE_RAW / "reporters_reference.json"
ACTIVE_COUNTRY_SAMPLE = CountrySampleSettings()
_COUNTRY_SAMPLE_CACHE: dict[CountrySampleSettings, tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]] = {}

FLOW_LABELS = {
    "X": "Exports",
    "M": "Imports",
    2: "Exports",
    1: "Imports",
    "2": "Exports",
    "1": "Imports",
}


def hs6_code_series(series: pd.Series) -> pd.Series:
    return series.astype(str).str.extract(r"(\d{1,6})", expand=False).str.zfill(6)


def excluded_hs6_mask(series: pd.Series) -> pd.Series:
    return hs6_code_series(series).isin(EXCLUDED_HS6_CODES)


def drop_excluded_hs6(df: pd.DataFrame, code_col: str = "cmd_code") -> pd.DataFrame:
    if df.empty or code_col not in df.columns:
        return df
    mask = excluded_hs6_mask(df[code_col])
    if not mask.any():
        return df
    return df.loc[~mask].copy()

EXCLUSION_SETS = {
    "baseline": set(),
    "oil_only": {"27"},
    "oil_aircraft": {"27", "88"},
    "oil_aircraft_precious": {"27", "71", "88"},
    "full_exclusion": {"27", "71", "88", "89", "93"},
}

EXCLUSION_LABELS = {
    "27": "oil_petroleum_hs27",
    "71": "precious_stones_metals_hs71",
    "88": "aircraft_hs88",
    "89": "ships_hs89",
    "93": "arms_hs93",
}

HS_VERSION_BY_COMTRADE_CLASSIFICATION = {
    "H0": "HS92",
    "H1": "HS96",
    "H2": "HS02",
    "H3": "HS07",
    "H4": "HS12",
    "H5": "HS17",
    "H6": "HS22",
}

COMTRADE_CLASSIFICATION_BY_HS_VERSION = {value: key for key, value in HS_VERSION_BY_COMTRADE_CLASSIFICATION.items()}

HS_BEC_CORRELATION_URL = "https://unstats.un.org/unsd/classifications/Econ/tables/HS-SITC-BEC%20Correlations_2022.xlsx"
BEC5_REFERENCE_URL = "https://comtradeapi.un.org/files/v1/app/reference/B5.json"
BEC4_REFERENCE_URL = "https://comtradeapi.un.org/files/v1/app/reference/B4.json"
HS_BEC_CORRELATION_PATH = CLASSIFICATION_RAW / "HS-SITC-BEC Correlations_2022.xlsx"
BEC5_REFERENCE_PATH = CLASSIFICATION_RAW / "B5.json"
BEC4_REFERENCE_PATH = CLASSIFICATION_RAW / "B4.json"
EX03_BEC_MAPPING_CANDIDATE = DATA_PROCESSED / "exercise_03_bec5_mapping_candidate.csv"
EX03_BEC_MAPPING_APPROVED = DATA_PROCESSED / "exercise_03_bec5_mapping_approved.csv"


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
        COMTRADE_H24_WORLD_BULK,
        COMTRADE_AVAILABILITY,
        WORLD_BANK_RAW,
        CLASSIFICATION_RAW,
        DATA_PROCESSED,
        RESULTS,
        EX01_TABLES,
        EX01_FIGURES,
        EX02_TABLES,
        EX02_FIGURES,
        EX03_TABLES,
        EX03_FIGURES,
        EX04_TABLES,
        EX04_FIGURES,
        EX06_TABLES,
        EX06_FIGURES,
        EX10_TABLES,
        EX10_FIGURES,
        EX11_TABLES,
        EX11_FIGURES,
        EX12_TABLES,
        EX12_FIGURES,
        OECD_ICIO_RAW,
        EX03_PRODUCT_PARTIAL_DIR,
        EX03_COVERAGE_PARTIAL_DIR,
        EX04_PARTIAL_DIR,
        EX11_IMPORT_PARTIAL_DIR,
        EX11_EXPORT_PARTIAL_DIR,
        EX11_COVERAGE_PARTIAL_DIR,
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


def active_sample_name() -> str:
    return ACTIVE_COUNTRY_SAMPLE.name


def sample_processed_dir(sample_name: str | None = None) -> Path:
    return SAMPLE_PROCESSED_ROOT / (sample_name or active_sample_name())


def sample_processed_path(filename: str, sample_name: str | None = None) -> Path:
    if (sample_name or active_sample_name()) == "prof_p_33":
        return DATA_PROCESSED / filename
    return sample_processed_dir(sample_name) / filename


def sample_results_dir(sample_name: str | None = None) -> Path:
    if (sample_name or active_sample_name()) == "prof_p_33":
        return RESULTS
    return RESULTS / "samples" / (sample_name or active_sample_name())


def sample_availability_path(suffix: str, sample_name: str | None = None) -> Path:
    return COMTRADE_AVAILABILITY / f"{sample_name or active_sample_name()}_{suffix}"


def sample_completion_dir(sample_name: str | None = None) -> Path:
    return sample_processed_dir(sample_name) / "completion"


def exercise_completion_manifest_path(exercise: str, sample_name: str | None = None) -> Path:
    return sample_completion_dir(sample_name) / f"exercise_{exercise}_complete.json"


def file_is_available(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def exercise_output_paths(exercise: str) -> list[Path]:
    paths = {
        "1": [EX01_TABLES / "concentration_all_years.csv", sample_processed_path("concentration_all_years.parquet")],
        "2": [EX02_TABLES / "bucket_growth_panel.csv", sample_processed_path("exercise_02_bucket_growth_panel.parquet")],
        "3": [EX03_TABLES / "import_bin_concentration.csv", sample_processed_path("exercise_03_import_bin_concentration.parquet")],
        "4": [EX04_TABLES / "dominant_supplier_importer_summary.csv", sample_processed_path("exercise_04_dominant_supplier_by_product.parquet")],
        "6": [EX06_TABLES / "concentration_exclusions_all_years.csv", sample_processed_path("concentration_exclusions_all_years.parquet")],
        "10": [EX10_TABLES / "random_benchmark_all_years.csv", sample_processed_path("random_benchmark_all_years.parquet")],
        "11": [EX11_TABLES / "top_export_sector_input_exposure.csv", sample_processed_path("exercise_11_top_export_input_exposure.parquet")],
        "12": [EX12_TABLES / "growth_decomposition.csv", sample_processed_path("exercise_12_growth_decomposition.parquet")],
    }
    if exercise == "all":
        out: list[Path] = []
        for key in PIPELINE_EXERCISES:
            out.extend(paths[key])
        return out
    return paths.get(exercise, [])


def completion_manifest_matches_sample(exercise: str) -> bool:
    manifest = exercise_completion_manifest_path(exercise)
    if not manifest.exists():
        return False
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return payload.get("country_sample") == active_sample_name()


def exercise_outputs_available(exercise: str) -> bool:
    outputs = exercise_output_paths(exercise)
    if not outputs or not all(file_is_available(path) for path in outputs):
        return False
    if active_sample_name() == "prof_p_33":
        return True
    if exercise == "all":
        return all(completion_manifest_matches_sample(key) for key in PIPELINE_EXERCISES)
    return completion_manifest_matches_sample(exercise)


def can_reuse_exercise_outputs(args: argparse.Namespace) -> bool:
    return (
        getattr(args, "max_files", None) is None
        and not getattr(args, "reprocess_raw", False)
        and not getattr(args, "fresh_checkpoints", False)
        and not getattr(args, "finalize_only", False)
    )


def mark_exercise_outputs_complete(exercise: str, details: dict | None = None) -> None:
    manifest = {
        "created_at_utc": now_utc(),
        "country_sample": active_sample_name(),
        "sample_settings": ACTIVE_COUNTRY_SAMPLE.__dict__,
        "exercise": exercise,
        "outputs": [str(path.relative_to(ROOT)) for path in exercise_output_paths(exercise)],
        "details": details or {},
    }
    write_json(exercise_completion_manifest_path(exercise), manifest)


def mark_many_exercises_complete(exercises: Iterable[str], details: dict | None = None) -> None:
    for exercise in exercises:
        mark_exercise_outputs_complete(exercise, details=details)


def configure_country_sample(
    country_sample: str = "prof_p_33",
    min_available_years: int = 10,
    start_year: int = 1988,
    end_year: int | None = None,
    refresh_availability: bool = False,
) -> CountrySampleSettings:
    if country_sample not in COUNTRY_SAMPLE_CHOICES:
        raise ValueError(f"Unsupported country sample `{country_sample}`. Choose from: {', '.join(COUNTRY_SAMPLE_CHOICES)}")
    if country_sample == CADOT_BROAD_SAMPLE:
        if min_available_years not in {10, CADOT_BROAD_MIN_AVAILABLE_YEARS}:
            raise ValueError(
                f"{CADOT_BROAD_SAMPLE} fixes --min-available-years at {CADOT_BROAD_MIN_AVAILABLE_YEARS}; "
                f"received {min_available_years}."
            )
        if start_year not in {1988, CADOT_BROAD_START_YEAR}:
            raise ValueError(f"{CADOT_BROAD_SAMPLE} fixes --start-year at {CADOT_BROAD_START_YEAR}; received {start_year}.")
        if end_year not in {None, CADOT_BROAD_END_YEAR}:
            raise ValueError(f"{CADOT_BROAD_SAMPLE} fixes --end-year at {CADOT_BROAD_END_YEAR}; received {end_year}.")
        min_available_years = CADOT_BROAD_MIN_AVAILABLE_YEARS
        start_year = CADOT_BROAD_START_YEAR
        end_year = CADOT_BROAD_END_YEAR
    if country_sample == CADOT_ORIGINAL_SAMPLE:
        if start_year not in {1988, CADOT_ORIGINAL_START_YEAR}:
            raise ValueError(f"{CADOT_ORIGINAL_SAMPLE} fixes --start-year at {CADOT_ORIGINAL_START_YEAR}; received {start_year}.")
        if end_year not in {None, CADOT_ORIGINAL_END_YEAR}:
            raise ValueError(f"{CADOT_ORIGINAL_SAMPLE} fixes --end-year at {CADOT_ORIGINAL_END_YEAR}; received {end_year}.")
        start_year = CADOT_ORIGINAL_START_YEAR
        end_year = CADOT_ORIGINAL_END_YEAR
    if country_sample == CADOT_ORIGINAL_EXTENDED_SAMPLE:
        if start_year not in {1988, CADOT_ORIGINAL_START_YEAR}:
            raise ValueError(
                f"{CADOT_ORIGINAL_EXTENDED_SAMPLE} fixes --start-year at {CADOT_ORIGINAL_START_YEAR}; received {start_year}."
            )
        start_year = CADOT_ORIGINAL_START_YEAR
    if min_available_years < 1:
        raise ValueError("--min-available-years must be positive.")
    if start_year < 1900:
        raise ValueError("--start-year must be 1900 or later.")
    if end_year is not None and end_year < start_year:
        raise ValueError("--end-year must be greater than or equal to --start-year.")

    global ACTIVE_COUNTRY_SAMPLE
    ACTIVE_COUNTRY_SAMPLE = CountrySampleSettings(
        name=country_sample,
        min_available_years=int(min_available_years),
        start_year=int(start_year),
        end_year=int(end_year) if end_year is not None else None,
        refresh_availability=bool(refresh_availability),
    )
    configure_sample_result_dirs()
    configure_sample_partial_dirs()
    return ACTIVE_COUNTRY_SAMPLE


def configure_country_sample_from_args(args: argparse.Namespace) -> CountrySampleSettings:
    return configure_country_sample(
        country_sample=getattr(args, "country_sample", "prof_p_33"),
        min_available_years=getattr(args, "min_available_years", 10),
        start_year=getattr(args, "start_year", 1988),
        end_year=getattr(args, "end_year", None),
        refresh_availability=getattr(args, "refresh_availability", False),
    )


def configure_sample_result_dirs() -> None:
    global EX01_TABLES
    global EX01_FIGURES
    global EX02_TABLES
    global EX02_FIGURES
    global EX03_TABLES
    global EX03_FIGURES
    global EX04_TABLES
    global EX04_FIGURES
    global EX06_TABLES
    global EX06_FIGURES
    global EX10_TABLES
    global EX10_FIGURES
    global EX11_TABLES
    global EX11_FIGURES
    global EX12_TABLES
    global EX12_FIGURES

    base = sample_results_dir()
    EX01_TABLES = base / "exercise_01_tables"
    EX01_FIGURES = base / "exercise_01_figures"
    EX02_TABLES = base / "exercise_02_tables"
    EX02_FIGURES = base / "exercise_02_figures"
    EX03_TABLES = base / "exercise_03_tables"
    EX03_FIGURES = base / "exercise_03_figures"
    EX04_TABLES = base / "exercise_04_tables"
    EX04_FIGURES = base / "exercise_04_figures"
    EX06_TABLES = base / "exercise_06_tables"
    EX06_FIGURES = base / "exercise_06_figures"
    EX10_TABLES = base / "exercise_10_tables"
    EX10_FIGURES = base / "exercise_10_figures"
    EX11_TABLES = base / "exercise_11_tables"
    EX11_FIGURES = base / "exercise_11_figures"
    EX12_TABLES = base / "exercise_12_tables"
    EX12_FIGURES = base / "exercise_12_figures"


def configure_sample_partial_dirs() -> None:
    global EX03_PARTIAL_DIR
    global EX03_PRODUCT_PARTIAL_DIR
    global EX03_COVERAGE_PARTIAL_DIR
    global EX04_PARTIAL_DIR
    global EX11_PARTIAL_DIR
    global EX11_IMPORT_PARTIAL_DIR
    global EX11_EXPORT_PARTIAL_DIR
    global EX11_COVERAGE_PARTIAL_DIR

    if active_sample_name() == "prof_p_33":
        EX03_PARTIAL_DIR = BASE_EX03_PARTIAL_DIR
        EX04_PARTIAL_DIR = BASE_EX04_PARTIAL_DIR
        EX11_PARTIAL_DIR = BASE_EX11_PARTIAL_DIR
    else:
        checkpoint_root = sample_processed_dir() / "checkpoints"
        EX03_PARTIAL_DIR = checkpoint_root / "exercise_03_file_aggregates"
        EX04_PARTIAL_DIR = checkpoint_root / "exercise_04_file_aggregates"
        EX11_PARTIAL_DIR = checkpoint_root / "exercise_11_file_aggregates"

    EX03_PRODUCT_PARTIAL_DIR = EX03_PARTIAL_DIR / "product_values"
    EX03_COVERAGE_PARTIAL_DIR = EX03_PARTIAL_DIR / "mapping_coverage"
    EX11_IMPORT_PARTIAL_DIR = EX11_PARTIAL_DIR / "import_cells"
    EX11_EXPORT_PARTIAL_DIR = EX11_PARTIAL_DIR / "export_sectors"
    EX11_COVERAGE_PARTIAL_DIR = EX11_PARTIAL_DIR / "mapping_coverage"


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
   python scripts/trade_concentration_pipeline.py --country-sample {active_sample_name()} --stage all
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


def prof_p_availability_path(kind: str) -> Path:
    return COMTRADE_AVAILABILITY / f"prof_p_panel_{kind}.csv"


def availability_path(kind: str, sample_name: str | None = None) -> Path:
    sample = sample_name or active_sample_name()
    if sample == "prof_p_33":
        return prof_p_availability_path(kind)
    return sample_availability_path(f"{kind}.csv", sample)


def standardize_availability_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    out = df.copy()
    col_map = {normalized_column_key(col): col for col in out.columns}

    def existing(*candidates: str) -> str | None:
        for candidate in candidates:
            key = normalized_column_key(candidate)
            if key in col_map:
                return col_map[key]
        return None

    reporter_col = existing("reporterCode", "reporter_code", "reporter_code_expected")
    period_col = existing("period", "refPeriodId", "year")
    class_col = existing("classificationCode", "classification_code")
    if reporter_col is None or period_col is None:
        return pd.DataFrame()

    out["reporter_code_expected"] = pd.to_numeric(out[reporter_col], errors="coerce")
    out["reporterCode"] = out["reporter_code_expected"]
    out["period"] = pd.to_numeric(out[period_col], errors="coerce")
    if class_col is None:
        out["classificationCode"] = ""
    else:
        out["classificationCode"] = out[class_col].fillna("").astype(str).str.strip().str.upper()
    out = out.dropna(subset=["reporter_code_expected", "period"])
    if out.empty:
        return pd.DataFrame()
    out["reporter_code_expected"] = out["reporter_code_expected"].astype(int)
    out["reporterCode"] = out["reporterCode"].astype(int)
    out["period"] = out["period"].astype(int)
    return out


def filter_hs_availability(df: pd.DataFrame, settings: CountrySampleSettings | None = None) -> pd.DataFrame:
    settings = settings or ACTIVE_COUNTRY_SAMPLE
    out = standardize_availability_columns(df)
    if out.empty:
        return out
    out = out[out["classificationCode"].astype(str).str.startswith("H")].copy()
    out = out[out["period"] >= settings.start_year].copy()
    if settings.end_year is not None:
        out = out[out["period"] <= settings.end_year].copy()
    return out


def load_reporter_reference(refresh: bool = False) -> tuple[pd.DataFrame, str]:
    if COMTRADE_REPORTERS_PATH.exists() and not refresh:
        raw = COMTRADE_REPORTERS_PATH.read_bytes()
    else:
        response = requests.get(COMTRADE_REPORTERS_URL, timeout=30)
        response.raise_for_status()
        raw = response.content
        COMTRADE_REPORTERS_PATH.parent.mkdir(parents=True, exist_ok=True)
        COMTRADE_REPORTERS_PATH.write_bytes(raw)

    checksum = hashlib.sha256(raw).hexdigest()
    payload = json.loads(raw.decode("utf-8"))
    rows = payload.get("results", payload if isinstance(payload, list) else [])
    ref = pd.DataFrame(rows)
    if ref.empty:
        raise RuntimeError("Comtrade reporter reference returned no rows.")
    return ref, checksum


def load_public_final_availability(settings: CountrySampleSettings | None = None) -> pd.DataFrame:
    settings = settings or ACTIVE_COUNTRY_SAMPLE
    path = availability_path("public_availability", settings.name)
    world_path = availability_path("public_availability", "world_broad")
    if settings.name == CADOT_BROAD_SAMPLE and world_path.exists() and not settings.refresh_availability:
        availability = pd.read_csv(world_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        availability.to_csv(path, index=False)
        return availability
    if path.exists() and not settings.refresh_availability:
        return pd.read_csv(path)
    if settings.name == RD2_SAMPLE and world_path.exists() and not settings.refresh_availability:
        availability = pd.read_csv(world_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        availability.to_csv(path, index=False)
        return availability
    if comtradeapicall is None:
        return pd.DataFrame()

    if settings.name in PUBLIC_ALL_REPORTER_AVAILABILITY_SAMPLE_NAMES:
        print("Checking public Comtrade annual HS final-data availability for all reporters", flush=True)
        df = comtradeapicall._getFinalDataAvailability(typeCode="C", freqCode="A", clCode="HS", period=None, reporterCode=None)
        availability = df.copy() if df is not None else pd.DataFrame()
        availability.to_csv(path, index=False)
        return availability

    rows = []
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
    availability.to_csv(path, index=False)
    return availability


def build_country_year_coverage(panel: pd.DataFrame, availability: pd.DataFrame, settings: CountrySampleSettings) -> tuple[pd.DataFrame, pd.DataFrame]:
    hs = filter_hs_availability(availability, settings)
    if hs.empty:
        coverage = pd.DataFrame(columns=["country", "iso3", "reporter_code", "year", "classification_code"])
        summary = panel[["country", "iso3", "reporter_code"]].copy()
        summary["available_hs_years"] = 0
        summary["first_available_year"] = pd.NA
        summary["last_available_year"] = pd.NA
        return coverage, summary

    coverage = hs[["reporter_code_expected", "period", "classificationCode"]].drop_duplicates().copy()
    coverage = coverage.rename(
        columns={
            "reporter_code_expected": "reporter_code",
            "period": "year",
            "classificationCode": "classification_code",
        }
    )
    coverage = coverage.merge(panel[["country", "iso3", "reporter_code"]], on="reporter_code", how="inner")
    coverage = coverage[["country", "iso3", "reporter_code", "year", "classification_code"]].sort_values(
        ["reporter_code", "year", "classification_code"]
    )

    summary = (
        coverage.groupby(["country", "iso3", "reporter_code"], as_index=False)
        .agg(
            available_hs_years=("year", "nunique"),
            first_available_year=("year", "min"),
            last_available_year=("year", "max"),
        )
        .sort_values(["country", "reporter_code"])
    )
    return coverage, summary


def summarize_country_coverage(panel: pd.DataFrame, coverage: pd.DataFrame) -> pd.DataFrame:
    if coverage.empty:
        summary = panel[["country", "iso3", "reporter_code"]].copy()
        summary["available_hs_years"] = 0
        summary["first_available_year"] = pd.NA
        summary["last_available_year"] = pd.NA
        return summary
    return (
        coverage.groupby(["country", "iso3", "reporter_code"], as_index=False)
        .agg(
            available_hs_years=("year", "nunique"),
            first_available_year=("year", "min"),
            last_available_year=("year", "max"),
        )
        .sort_values(["country", "reporter_code"])
    )


def write_country_sample_outputs(
    panel: pd.DataFrame,
    coverage: pd.DataFrame,
    coverage_summary: pd.DataFrame,
    excluded: pd.DataFrame,
    manifest: dict,
    settings: CountrySampleSettings,
) -> None:
    out_dir = sample_processed_dir(settings.name)
    out_dir.mkdir(parents=True, exist_ok=True)
    panel.to_csv(out_dir / "comtrade_country_panel.csv", index=False)
    coverage.to_csv(out_dir / "country_year_coverage.csv", index=False)
    coverage_summary.to_csv(out_dir / "country_coverage_summary.csv", index=False)
    excluded.to_csv(out_dir / "excluded_reporters.csv", index=False)
    write_json(out_dir / "availability_manifest.json", manifest)
    if settings.name == CADOT_BROAD_SAMPLE:
        write_cadot_broad_sample_note(out_dir, coverage_summary, excluded, manifest)
    if settings.name == "prof_p_33":
        panel.to_csv(DATA_PROCESSED / "comtrade_country_panel.csv", index=False)
        panel.to_csv(DATA_PROCESSED / "prof_p_country_panel.csv", index=False)


def write_cadot_broad_sample_note(out_dir: Path, coverage_summary: pd.DataFrame, excluded: pd.DataFrame, manifest: dict) -> None:
    reason_counts = excluded["exclusion_reason"].value_counts().sort_index().to_dict() if "exclusion_reason" in excluded.columns else {}
    selected = int(manifest.get("selected_reporters", 0))
    min_years = int(manifest.get("min_available_years", CADOT_BROAD_MIN_AVAILABLE_YEARS))
    start_year = int(manifest.get("start_year", CADOT_BROAD_START_YEAR))
    end_year = int(manifest.get("end_year", CADOT_BROAD_END_YEAR))
    complete_25 = int((pd.to_numeric(coverage_summary["available_hs_years"], errors="coerce") >= (end_year - start_year + 1)).sum())
    lines = [
        "# Cadot Broad 156-Country Sample Diagnostics",
        "",
        f"- Sample: `{CADOT_BROAD_SAMPLE}`.",
        f"- Rule: active non-group Comtrade reporters with valid ISO3 metadata, no expiry flag, and at least {min_years} annual HS final-data years in {start_year}-{end_year}.",
        f"- Selected reporters: {selected} / expected {CADOT_BROAD_EXPECTED_REPORTERS}.",
        f"- Reporter reference rows: {manifest.get('reporter_reference_rows', 'n/a')}.",
        f"- Availability rows in window: {manifest.get('hs_availability_rows_in_window', 'n/a')}.",
        f"- Selected reporters with complete {end_year - start_year + 1}-year HS coverage: {complete_25}.",
        f"- Excluded reporters by reason: {reason_counts}.",
        "",
        "Companion files:",
        "",
        "- `comtrade_country_panel.csv`: selected reporter panel.",
        "- `country_coverage_summary.csv`: selected reporter HS-year coverage.",
        "- `country_year_coverage.csv`: selected reporter-year-classification coverage.",
        "- `excluded_reporters.csv`: reporter-level exclusion reasons.",
        "- `availability_manifest.json`: machine-readable sample manifest.",
    ]
    (out_dir / "sample_diagnostics.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def prof_p_country_sample(settings: CountrySampleSettings) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    panel = pd.DataFrame([c.__dict__ for c in PROF_P_COUNTRIES])
    availability_file = availability_path("public_availability", settings.name)
    availability = (
        load_public_final_availability(settings)
        if settings.refresh_availability or availability_file.exists()
        else pd.DataFrame()
    )
    coverage, coverage_summary = build_country_year_coverage(panel, availability, settings)
    excluded = pd.DataFrame(columns=["country", "iso3", "reporter_code", "exclusion_reason"])
    manifest = {
        "created_at_utc": now_utc(),
        "country_sample": settings.name,
        "sample_rule": "Fixed Panagariya-Bagaria 33-country replication sample.",
        "selected_reporters": int(len(panel)),
        "availability_rows": int(len(availability)),
        "reporter_reference_url": COMTRADE_REPORTERS_URL,
        "availability_file": str(availability_file.relative_to(ROOT)) if availability_file.exists() else "",
        "api_params": {"typeCode": "C", "freqCode": "A", "clCode": "HS"},
        "start_year": settings.start_year,
        "end_year": settings.end_year,
        "min_available_years": settings.min_available_years,
    }
    return panel, coverage, excluded, manifest


def rd2_country_sample(settings: CountrySampleSettings) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    panel = pd.DataFrame([c.__dict__ for c in RD2_COUNTRIES])
    duplicate_codes = panel[panel.duplicated("reporter_code", keep=False)]
    if not duplicate_codes.empty:
        raise RuntimeError(f"rd2_countries has duplicate reporter codes: {duplicate_codes.to_dict('records')}")
    duplicate_iso3 = panel[panel.duplicated("iso3", keep=False)]
    if not duplicate_iso3.empty:
        raise RuntimeError(f"rd2_countries has duplicate ISO3 codes: {duplicate_iso3.to_dict('records')}")
    if len(panel) != 60:
        raise RuntimeError(f"rd2_countries must contain exactly 60 reporters; found {len(panel)}.")
    missing_additions = RD2_REQUIRED_ISO3 - set(panel["iso3"])
    if missing_additions:
        raise RuntimeError(f"rd2_countries is missing required additions: {sorted(missing_additions)}")

    availability_file = availability_path("public_availability", settings.name)
    availability = (
        load_public_final_availability(settings)
        if settings.refresh_availability or availability_file.exists() or availability_path("public_availability", "world_broad").exists()
        else pd.DataFrame()
    )
    coverage, coverage_summary = build_country_year_coverage(panel, availability, settings)
    excluded = pd.DataFrame(columns=["country", "iso3", "reporter_code", "exclusion_reason"])
    botswana = coverage_summary[coverage_summary["iso3"].eq("BWA")]
    botswana_years = int(botswana["available_hs_years"].iloc[0]) if not botswana.empty else 0
    manifest = {
        "created_at_utc": now_utc(),
        "country_sample": settings.name,
        "sample_rule": "Fixed 60-country rd2 sample: Panagariya-Bagaria 33 plus researcher-selected fast-growing, hub, and small-country additions.",
        "selected_reporters": int(len(panel)),
        "original_prof_p_reporters": int(len(PROF_P_COUNTRIES)),
        "additional_reporters": int(len(RD2_COUNTRY_ADDITIONS)),
        "required_addition_iso3": sorted(RD2_REQUIRED_ISO3),
        "explicit_coverage_overrides": [
            {
                "country": "Botswana",
                "iso3": "BWA",
                "reporter_code": 72,
                "available_hs_years": botswana_years,
                "reason": "Included by researcher request despite falling below the 25-year screening rule.",
            }
        ],
        "availability_rows": int(len(availability)),
        "reporter_reference_url": COMTRADE_REPORTERS_URL,
        "availability_file": str(availability_file.relative_to(ROOT)) if availability_file.exists() else "",
        "api_params": {"typeCode": "C", "freqCode": "A", "clCode": "HS"},
        "start_year": settings.start_year,
        "end_year": settings.end_year,
        "min_available_years": settings.min_available_years,
    }
    return panel.sort_values(["country", "reporter_code"]).reset_index(drop=True), coverage, excluded, manifest


def world_broad_country_sample(settings: CountrySampleSettings) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    reporters, reporter_checksum = load_reporter_reference(refresh=settings.refresh_availability)
    availability = load_public_final_availability(settings)
    hs = filter_hs_availability(availability, settings)
    coverage_summary = (
        hs.groupby("reporter_code_expected", as_index=False)
        .agg(
            available_hs_years=("period", "nunique"),
            first_available_year=("period", "min"),
            last_available_year=("period", "max"),
        )
        .rename(columns={"reporter_code_expected": "reporter_code"})
        if not hs.empty
        else pd.DataFrame(columns=["reporter_code", "available_hs_years", "first_available_year", "last_available_year"])
    )

    ref = reporters.copy()
    required = {"reporterCode", "reporterDesc", "reporterCodeIsoAlpha3", "isGroup"}
    missing = required.difference(ref.columns)
    if missing:
        raise RuntimeError(f"Comtrade reporter reference is missing required columns: {sorted(missing)}")
    ref = ref.rename(
        columns={
            "reporterCode": "reporter_code",
            "reporterDesc": "country",
            "reporterCodeIsoAlpha3": "iso3",
            "entryExpiredDate": "entry_expired_date",
            "isGroup": "is_group",
        }
    )
    if "entry_expired_date" not in ref.columns:
        ref["entry_expired_date"] = ""
    ref["reporter_code"] = pd.to_numeric(ref["reporter_code"], errors="coerce")
    ref["country"] = ref["country"].fillna("").astype(str).str.strip()
    ref["iso3"] = ref["iso3"].fillna("").astype(str).str.strip().str.upper()
    ref["is_group"] = ref["is_group"].fillna(False).astype(bool)
    ref["entry_expired_date"] = ref["entry_expired_date"].fillna("").astype(str).str.strip()
    ref = ref.dropna(subset=["reporter_code"]).copy()
    ref["reporter_code"] = ref["reporter_code"].astype(int)
    ref = ref.merge(coverage_summary, on="reporter_code", how="left")
    ref["available_hs_years"] = pd.to_numeric(ref["available_hs_years"], errors="coerce").fillna(0).astype(int)

    def exclusion_reason(row: pd.Series) -> str:
        if bool(row["is_group"]):
            return "group"
        if str(row["entry_expired_date"]).strip():
            return "expired"
        if not str(row["iso3"]).strip():
            return "missing_iso3"
        if int(row["available_hs_years"]) <= 0:
            return "no_availability"
        if int(row["available_hs_years"]) < settings.min_available_years:
            return "insufficient_hs_years"
        return ""

    ref["exclusion_reason"] = ref.apply(exclusion_reason, axis=1)
    selected = ref[ref["exclusion_reason"] == ""].copy()
    panel = selected[["country", "iso3", "reporter_code"]].sort_values(["country", "reporter_code"]).reset_index(drop=True)
    coverage, selected_summary = build_country_year_coverage(panel, availability, settings)
    excluded = ref[ref["exclusion_reason"] != ""][
        ["country", "iso3", "reporter_code", "exclusion_reason", "available_hs_years", "first_available_year", "last_available_year"]
    ].sort_values(["exclusion_reason", "country", "reporter_code"])

    if settings.name == CADOT_BROAD_SAMPLE:
        duplicate_codes = panel[panel.duplicated("reporter_code", keep=False)]
        if not duplicate_codes.empty:
            raise RuntimeError(f"{CADOT_BROAD_SAMPLE} has duplicate reporter codes: {duplicate_codes.to_dict('records')}")
        duplicate_iso3 = panel[panel.duplicated("iso3", keep=False)]
        if not duplicate_iso3.empty:
            raise RuntimeError(f"{CADOT_BROAD_SAMPLE} has duplicate ISO3 codes: {duplicate_iso3.to_dict('records')}")
        if len(panel) != CADOT_BROAD_EXPECTED_REPORTERS:
            reason_counts = excluded["exclusion_reason"].value_counts().sort_index().to_dict()
            raise RuntimeError(
                f"{CADOT_BROAD_SAMPLE} must select exactly {CADOT_BROAD_EXPECTED_REPORTERS} reporters under the "
                f"fixed {settings.start_year}-{settings.end_year}, min-HS-years={settings.min_available_years} rule; "
                f"found {len(panel)}. Exclusion counts: {reason_counts}"
            )

    reason_counts = ref["exclusion_reason"].replace("", "selected").value_counts().sort_index().to_dict()
    sample_rule = (
        "Cadot broad 156-country modern replication sample: active non-group Comtrade reporters with ISO3 metadata, "
        "no expiry flag, and at least 19 annual final merchandise HS availability years in 2000-2024."
        if settings.name == CADOT_BROAD_SAMPLE
        else "Active non-group Comtrade reporters with ISO3 metadata and enough annual final merchandise HS availability."
    )
    manifest = {
        "created_at_utc": now_utc(),
        "country_sample": settings.name,
        "sample_rule": sample_rule,
        "selected_reporters": int(len(panel)),
        "excluded_reporters": int(len(excluded)),
        "reporter_reference_rows": int(len(ref)),
        "reporter_exclusion_counts": {str(key): int(value) for key, value in reason_counts.items()},
        "availability_rows": int(len(availability)),
        "hs_availability_rows_in_window": int(len(hs)),
        "reporter_reference_url": COMTRADE_REPORTERS_URL,
        "reporter_reference_file": str(COMTRADE_REPORTERS_PATH.relative_to(ROOT)),
        "reporter_reference_sha256": reporter_checksum,
        "availability_file": str(availability_path("public_availability", settings.name).relative_to(ROOT)),
        "api_params": {"typeCode": "C", "freqCode": "A", "clCode": "HS"},
        "start_year": settings.start_year,
        "end_year": settings.end_year,
        "min_available_years": settings.min_available_years,
    }
    if settings.name == CADOT_BROAD_SAMPLE:
        manifest["expected_selected_reporters"] = CADOT_BROAD_EXPECTED_REPORTERS
        manifest["sample_role"] = "Cadot-comparable broad replication sample, not website-facing."
    return panel, coverage, excluded, manifest


def build_country_sample(settings: CountrySampleSettings | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    settings = settings or ACTIVE_COUNTRY_SAMPLE
    cached = _COUNTRY_SAMPLE_CACHE.get(settings)
    if cached is not None:
        return cached
    if settings.name in {CADOT_ORIGINAL_SAMPLE, CADOT_ORIGINAL_EXTENDED_SAMPLE}:
        raise RuntimeError(
            f"{settings.name} is a research-only Cadot replication target, but the exact Cadot 156-country list, "
            "mirror-import construction, and HS0 4,991-line universe have not been recovered in this checkout. "
            "Run `python3 scripts/recover_cadot_original_status.py` to write current blocker/status artifacts; "
            "do not use the broad Comtrade selector for this sample."
        )
    if settings.name == "prof_p_33":
        panel, coverage, excluded, manifest = prof_p_country_sample(settings)
    elif settings.name == "rd2_countries":
        panel, coverage, excluded, manifest = rd2_country_sample(settings)
    else:
        panel, coverage, excluded, manifest = world_broad_country_sample(settings)
    coverage_summary = summarize_country_coverage(panel, coverage)
    write_country_sample_outputs(panel, coverage, coverage_summary, excluded, manifest, settings)
    cached = (panel, coverage, excluded, manifest)
    _COUNTRY_SAMPLE_CACHE[settings] = cached
    return cached


def save_country_panel() -> pd.DataFrame:
    panel, _coverage, _excluded, _manifest = build_country_sample(ACTIVE_COUNTRY_SAMPLE)
    return panel.copy()


def download_public_availability_without_key() -> pd.DataFrame:
    """Save public Comtrade annual HS final-data availability metadata.

    This records availability only. It does not retrieve the HS6 reporter-product-
    partner trade values needed for the exercises.
    """
    availability = load_public_final_availability(ACTIVE_COUNTRY_SAMPLE)
    save_country_panel()
    return availability


def check_comtrade_access(subscription_key: str | None) -> bool:
    if not subscription_key:
        availability = download_public_availability_without_key()
        details = {
            "country_sample": active_sample_name(),
            "public_availability_rows_saved": int(len(availability)),
            "public_availability_file": str(availability_path("public_availability").relative_to(ROOT)),
            "sample_manifest": str((sample_processed_dir() / "availability_manifest.json").relative_to(ROOT)),
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


def download_availability(subscription_key: str) -> pd.DataFrame:
    existing = availability_path("availability")
    if existing.exists() and not ACTIVE_COUNTRY_SAMPLE.refresh_availability:
        print(f"Using existing keyed availability: {existing}", flush=True)
        return pd.read_csv(existing)

    panel = save_country_panel()
    rows = []
    for country in panel.itertuples(index=False):
        print(f"Checking availability: {country.country} ({country.reporter_code})", flush=True)
        df = comtradeapicall.getFinalDataBulkAvailability(
            subscription_key,
            typeCode="C",
            freqCode="A",
            clCode="HS",
            period=None,
            reporterCode=int(country.reporter_code),
        )
        if df is None or df.empty:
            rows.append(
                {
                    "country": country.country,
                    "iso3": country.iso3,
                    "reporter_code": int(country.reporter_code),
                    "period": None,
                    "available": False,
                }
            )
            continue
        df = df.copy()
        df["country"] = country.country
        df["iso3"] = country.iso3
        df["reporter_code_expected"] = int(country.reporter_code)
        if ACTIVE_COUNTRY_SAMPLE.name == "prof_p_33":
            per_country_path = COMTRADE_AVAILABILITY / f"{country.iso3}_{int(country.reporter_code)}_availability.csv"
        else:
            per_country_path = COMTRADE_AVAILABILITY / f"{ACTIVE_COUNTRY_SAMPLE.name}_{country.iso3}_{int(country.reporter_code)}_availability.csv"
        df.to_csv(per_country_path, index=False)
        rows.extend(df.to_dict("records"))

    availability = pd.DataFrame(rows)
    availability.to_csv(existing, index=False)
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


def availability_bulk_key(row: pd.Series) -> tuple[int, int, str]:
    reporter = row.get("reporter_code_expected", row.get("reporterCode"))
    return (int(reporter), int(row.get("period")), str(row.get("classificationCode")).strip().upper())


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

    panel = save_country_panel()
    panel_meta = panel.set_index("reporter_code")[["country", "iso3"]].to_dict("index")
    panel_codes = set(panel["reporter_code"].astype(int))
    available = filter_hs_availability(availability, ACTIVE_COUNTRY_SAMPLE)
    available = available[available["reporter_code_expected"].isin(panel_codes)].copy()
    if available.empty:
        raise RuntimeError("No selected annual HS bulk availability rows to download.")
    available["country"] = available["reporter_code_expected"].map(lambda code: panel_meta.get(int(code), {}).get("country", ""))
    available["iso3"] = available["reporter_code_expected"].map(lambda code: panel_meta.get(int(code), {}).get("iso3", ""))
    available = available.sort_values(["reporter_code_expected", "period"])
    if max_years is not None:
        available = available.groupby("reporter_code_expected", as_index=False).head(max_years)
    file_size_source = available["fileSize"] if "fileSize" in available.columns else pd.Series("", index=available.index)
    available["file_size_bytes_sort"] = file_size_source.map(parse_file_size_to_bytes)
    if min_file_mb is not None:
        available = available[available["file_size_bytes_sort"] >= min_file_mb * 1_000_000].copy()
    if max_file_mb is not None:
        available = available[available["file_size_bytes_sort"] <= max_file_mb * 1_000_000].copy()
    available = available.sort_values(["file_size_bytes_sort"], ascending=True)
    existing_keys = available_bulk_keys(dedupe_bulk_files(raw_bulk_file_candidates()))
    available = available[~available.apply(availability_bulk_key, axis=1).isin(existing_keys)].copy()
    if available.empty:
        print("All selected HS bulk files are already present in local raw stores.", flush=True)
        return

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
        "country_sample": active_sample_name(),
        "sample_settings": ACTIVE_COUNTRY_SAMPLE.__dict__,
        "typeCode": "C",
        "freqCode": "A",
        "clCode": "HS",
        "countries": panel.to_dict("records"),
        "downloads": manifest_rows,
    }
    write_json(COMTRADE_RAW / "manifest.json", manifest)


def normalized_column_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    normalized = {}
    for col in df.columns:
        key = normalized_column_key(col)
        normalized[key] = col
    return df.rename(columns={v: k for k, v in normalized.items()})


def pick_col(df: pd.DataFrame, candidates: Iterable[str]) -> str:
    for cand in candidates:
        key = re.sub(r"[^a-z0-9]+", "", cand.lower())
        if key in df.columns:
            return key
    raise KeyError(f"None of these columns found: {list(candidates)}")


def optional_col(df: pd.DataFrame, candidates: Iterable[str]) -> str | None:
    try:
        return pick_col(df, candidates)
    except KeyError:
        return None


def apply_memory_limit(memory_limit_gb: float | None) -> None:
    if memory_limit_gb is None:
        return
    if memory_limit_gb <= 0:
        raise RuntimeError("--memory-limit-gb must be positive.")
    requested = int(memory_limit_gb * 1024**3)
    try:
        import resource
    except ImportError:
        resource = None

    if resource is not None:
        try:
            _soft, hard = resource.getrlimit(resource.RLIMIT_AS)
            if hard != resource.RLIM_INFINITY and requested > hard:
                requested = hard
            resource.setrlimit(resource.RLIMIT_AS, (requested, hard))
            print(f"Applied process memory cap: {requested / 1024**3:.1f} GB", flush=True)
            return
        except (OSError, ValueError) as exc:
            print(f"WARNING: OS memory limit was not accepted ({exc}); using RSS monitor fallback.", flush=True)

    import threading

    try:
        import psutil

        process = psutil.Process(os.getpid())

        def current_rss_bytes() -> int:
            return int(process.memory_info().rss)

        monitor_source = "psutil"
    except ImportError:

        def current_rss_bytes() -> int:
            try:
                output = subprocess.check_output(["ps", "-o", "rss=", "-p", str(os.getpid())], text=True)
                return int(output.strip().split()[0]) * 1024
            except Exception:
                return 0

        monitor_source = "ps"

    def monitor() -> None:
        while True:
            rss = current_rss_bytes()
            if rss > requested:
                print(
                    f"ERROR: RSS memory cap exceeded ({rss / 1024**3:.1f} GB > {requested / 1024**3:.1f} GB).",
                    file=sys.stderr,
                    flush=True,
                )
                os._exit(137)
            time.sleep(0.5)

    thread = threading.Thread(target=monitor, name="memory-cap-monitor", daemon=True)
    thread.start()
    print(f"Applied RSS memory monitor cap via {monitor_source}: {requested / 1024**3:.1f} GB", flush=True)


def macos_memory_snapshot() -> dict[str, int]:
    snapshot = {
        "total_bytes": 0,
        "available_bytes": 0,
        "raw_available_bytes": 0,
        "file_backed_bytes": 0,
        "used_rss_bytes": 0,
        "compressed_bytes": 0,
        "memory_pressure_free_pct": -1,
    }
    try:
        snapshot["total_bytes"] = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip())
    except Exception:
        pass
    try:
        vm_output = subprocess.check_output(["vm_stat"], text=True)
        page_size_match = re.search(r"page size of (\d+) bytes", vm_output)
        page_size = int(page_size_match.group(1)) if page_size_match else 4096
        pages: dict[str, int] = {}
        for line in vm_output.splitlines():
            match = re.match(r"(?:Pages )?([^:]+):\s+(\d+)\.", line.strip())
            if match:
                pages[match.group(1).strip().lower()] = int(match.group(2))
        free_pages = pages.get("free", 0) + pages.get("speculative", 0) + pages.get("purgeable", 0)
        file_backed_pages = pages.get("file-backed pages", pages.get("file-backed", 0))
        snapshot["raw_available_bytes"] = free_pages * page_size
        snapshot["file_backed_bytes"] = file_backed_pages * page_size
        snapshot["available_bytes"] = (free_pages + file_backed_pages) * page_size
        snapshot["compressed_bytes"] = pages.get("occupied by compressor", 0) * page_size
    except Exception:
        pass
    try:
        pressure_output = subprocess.check_output(["memory_pressure", "-Q"], text=True, stderr=subprocess.DEVNULL)
        pct_match = re.search(r"free percentage:\s+(\d+)%", pressure_output)
        if pct_match:
            snapshot["memory_pressure_free_pct"] = int(pct_match.group(1))
    except Exception:
        pass
    try:
        ps_output = subprocess.check_output(["ps", "-axo", "rss="], text=True)
        snapshot["used_rss_bytes"] = sum(int(value) for value in ps_output.split() if value.strip().isdigit()) * 1024
    except Exception:
        pass
    return snapshot


def apply_dynamic_memory_guard(
    reserve_gb: float | None = None,
    max_process_gb: float | None = None,
    poll_seconds: float = 2.0,
) -> None:
    if reserve_gb is None and max_process_gb is None:
        return
    if reserve_gb is not None and reserve_gb <= 0:
        raise RuntimeError("--memory-reserve-gb must be positive.")
    if max_process_gb is not None and max_process_gb <= 0:
        raise RuntimeError("--memory-limit-gb must be positive.")

    import threading

    reserve_bytes = int((reserve_gb or 0) * 1024**3)
    max_process_bytes = int(max_process_gb * 1024**3) if max_process_gb is not None else None

    def current_rss_bytes() -> int:
        try:
            output = subprocess.check_output(["ps", "-o", "rss=", "-p", str(os.getpid())], text=True)
            return int(output.strip().split()[0]) * 1024
        except Exception:
            return 0

    def monitor() -> None:
        while True:
            rss = current_rss_bytes()
            snapshot = macos_memory_snapshot()
            available = snapshot.get("available_bytes", 0)
            pressure_free_pct = snapshot.get("memory_pressure_free_pct", -1)
            if max_process_bytes is not None and rss > max_process_bytes:
                print(
                    f"ERROR: process RSS cap exceeded ({rss / 1024**3:.1f} GB > {max_process_bytes / 1024**3:.1f} GB).",
                    file=sys.stderr,
                    flush=True,
                )
                os._exit(137)
            if reserve_bytes and available and available < reserve_bytes and (pressure_free_pct < 0 or pressure_free_pct < 10):
                print(
                    "ERROR: system memory reserve breached "
                    f"(available={available / 1024**3:.1f} GB < reserve={reserve_bytes / 1024**3:.1f} GB; "
                    f"process_rss={rss / 1024**3:.1f} GB; pressure_free_pct={pressure_free_pct}).",
                    file=sys.stderr,
                    flush=True,
                )
                os._exit(137)
            time.sleep(max(0.5, poll_seconds))

    initial = macos_memory_snapshot()
    thread = threading.Thread(target=monitor, name="dynamic-memory-guard", daemon=True)
    thread.start()
    print(
        "Applied dynamic memory guard: "
        f"reserve={reserve_bytes / 1024**3:.1f} GB, "
        f"process_cap={(max_process_bytes / 1024**3 if max_process_bytes else 0):.1f} GB, "
        f"initial_available={initial.get('available_bytes', 0) / 1024**3:.1f} GB, "
        f"initial_raw_available={initial.get('raw_available_bytes', 0) / 1024**3:.1f} GB, "
        f"initial_pressure_free_pct={initial.get('memory_pressure_free_pct', -1)}, "
        f"initial_total={initial.get('total_bytes', 0) / 1024**3:.1f} GB",
        flush=True,
    )


def detect_comtrade_delimiter(path: Path) -> str:
    opener = gzip.open if path.suffix == ".gz" else open
    mode = "rt"
    kwargs = {"encoding": "utf-8", "errors": "replace"}
    with opener(path, mode, **kwargs) as fh:
        header = fh.readline()
    return "\t" if header.count("\t") >= header.count(",") else ","


def comtrade_leaf_usecols(column: object) -> bool:
    return normalized_column_key(column) in COMTRADE_LEAF_COLUMN_KEYS


def normalize_hs_classification_code(value: object) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    text = str(value).strip().upper()
    if not text or text in {"NAN", "NONE", "NULL"}:
        return ""
    compact = re.sub(r"[^A-Z0-9]+", "", text)
    aliases = {
        "H0": "H0",
        "HS92": "H0",
        "HS1992": "H0",
        "H1": "H1",
        "HS96": "H1",
        "HS1996": "H1",
        "H2": "H2",
        "HS02": "H2",
        "HS2002": "H2",
        "H3": "H3",
        "HS07": "H3",
        "HS2007": "H3",
        "H4": "H4",
        "HS12": "H4",
        "HS2012": "H4",
        "H5": "H5",
        "HS17": "H5",
        "HS2017": "H5",
        "H6": "H6",
        "HS22": "H6",
        "HS2022": "H6",
    }
    return aliases.get(compact, text)


def infer_hs_classification_from_filename(path: Path) -> str:
    match = re.search(r"H([0-6])(?=\[|\.|$)", path.name.upper())
    return f"H{match.group(1)}" if match else ""


def attach_inferred_classification_code(df: pd.DataFrame, path: Path) -> pd.DataFrame:
    inferred = infer_hs_classification_from_filename(path)
    if not inferred:
        return df
    out = df.copy()
    if "classificationcode" not in out.columns:
        out["classificationcode"] = inferred
        return out
    existing = out["classificationcode"].astype("string")
    present = existing.notna() & existing.astype(str).str.strip().ne("")
    out["classificationcode"] = existing.where(present, inferred)
    return out


def read_reference_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    if path.suffix.lower() in {".xls", ".xlsx"}:
        return pd.read_excel(path, dtype=str)
    return pd.read_csv(path, dtype=str)


def read_comtrade_file(path: Path, leaf_columns_only: bool = True) -> pd.DataFrame:
    compression = "gzip" if path.suffix == ".gz" else None
    sep = detect_comtrade_delimiter(path)
    kwargs = {
        "compression": compression,
        "sep": sep,
        "low_memory": False,
    }
    if leaf_columns_only:
        kwargs["usecols"] = comtrade_leaf_usecols
    try:
        df = pd.read_csv(path, **kwargs)
        if len(df.columns) == 1 and sep != "\t":
            raise ValueError("single column after comma parse")
    except Exception:
        kwargs["sep"] = "\t"
        df = pd.read_csv(path, **kwargs)
    return attach_inferred_classification_code(normalize_columns(df), path)


def iter_comtrade_file_chunks(path: Path, chunk_rows: int = DEFAULT_CHUNK_ROWS, leaf_columns_only: bool = True) -> Iterable[pd.DataFrame]:
    if chunk_rows <= 0:
        raise RuntimeError("--chunk-rows must be positive.")
    compression = "gzip" if path.suffix == ".gz" else None
    sep = detect_comtrade_delimiter(path)
    kwargs = {
        "compression": compression,
        "sep": sep,
        "chunksize": int(chunk_rows),
        "low_memory": False,
    }
    if leaf_columns_only:
        kwargs["usecols"] = comtrade_leaf_usecols
    try:
        reader = pd.read_csv(path, **kwargs)
        for chunk in reader:
            if len(chunk.columns) == 1 and sep != "\t":
                raise ValueError("single column after comma parse")
            yield attach_inferred_classification_code(normalize_columns(chunk), path)
    except Exception:
        kwargs["sep"] = "\t"
        reader = pd.read_csv(path, **kwargs)
        for chunk in reader:
            yield attach_inferred_classification_code(normalize_columns(chunk), path)


def extract_leaf_trade(df: pd.DataFrame) -> pd.DataFrame:
    cmd_col = pick_col(df, ["cmdCode", "commodityCode", "Commodity Code"])
    value_col = pick_col(df, ["primaryValue", "Trade Value (US$)", "Trade Value", "tradeValue", "fobvalue", "cifvalue"])
    reporter_col = pick_col(df, ["reporterCode", "Reporter Code"])
    period_col = pick_col(df, ["period", "refYear", "year"])
    partner_col = pick_col(df, ["partnerCode", "Partner Code"])
    try:
        classification_col = pick_col(df, ["classificationCode", "Classification Code"])
    except KeyError:
        classification_col = None

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
    if classification_col is not None:
        out["classification_code"] = df[classification_col].astype(str).str.strip().str.upper()
    else:
        out["classification_code"] = ""

    if "reporteriso" in df.columns:
        out["reporter_iso"] = df["reporteriso"]
    if "reporterdesc" in df.columns:
        out["reporter_desc"] = df["reporterdesc"]
    if "partneriso" in df.columns:
        out["partner_iso"] = df["partneriso"]
    if "partnerdesc" in df.columns:
        out["partner_desc"] = df["partnerdesc"]
    if "cmddesc" in df.columns:
        out["cmd_desc"] = df["cmddesc"]

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


def iter_leaf_trade_chunks(path: Path, chunk_rows: int = DEFAULT_CHUNK_ROWS) -> Iterable[pd.DataFrame]:
    for raw in iter_comtrade_file_chunks(path, chunk_rows=chunk_rows, leaf_columns_only=True):
        leaf = extract_leaf_trade(raw)
        if not leaf.empty:
            yield leaf


def gini(values: Iterable[float]) -> float:
    """Backward-compatible alias for active-positive Gini."""
    return active_gini(values)


def top_share(values: Iterable[float], n: int | None = None, pct: float | None = None) -> float:
    """Backward-compatible alias for active-positive top shares."""
    return active_top_share(values, n=n, pct=pct)


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
    partner_leaf = leaf.copy()
    product_leaf = drop_excluded_hs6(leaf)
    product_rows = []
    partner_rows = []
    cell_rows = []
    panel = save_country_panel()
    country_meta = panel.set_index("reporter_code")[["country", "iso3"]].to_dict("index")

    group_cols = ["reporter_code", "year", "flow"]
    for key, group in product_leaf.groupby(group_cols, sort=True):
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
        cell_values = group.groupby(["cmd_code", "partner_code"], as_index=False)["trade_value"].sum()

        product_rows.append({**base, **metric_row(product_values["trade_value"], "product")})
        cell_rows.append({**base, **metric_row(cell_values["trade_value"], "product_partner_cell")})

    for key, group in partner_leaf.groupby(group_cols, sort=True):
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
        partner_values = group.groupby("partner_code", as_index=False)["trade_value"].sum()
        partner_rows.append({**base, **metric_row(partner_values["trade_value"], "partner"), "top_5_partner_share": top_share(partner_values["trade_value"], n=5)})

    return pd.DataFrame(product_rows), pd.DataFrame(partner_rows), pd.DataFrame(cell_rows)


def collect_leaf_data() -> pd.DataFrame:
    files = hs_bulk_files()
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
    panel_codes = set(save_country_panel()["reporter_code"].astype(int))
    out = out[out["reporter_code"].isin(panel_codes)].copy()
    out.to_parquet(sample_processed_path("hs6_partner_leaf_trade_all_years.parquet"), index=False)
    return out


def bulk_file_metadata(path: Path) -> dict | None:
    match = re.search(r"COMTRADE-FINAL-CA(\d{3})(\d{4})(H[0-6])(?=\[|\.|$)", path.name.upper())
    if not match:
        return None
    return {
        "reporter_code": int(match.group(1)),
        "year": int(match.group(2)),
        "classification_code": match.group(3),
    }


def raw_bulk_file_candidates() -> list[Path]:
    candidates: list[Path] = []
    for directory in [COMTRADE_BULK, COMTRADE_H24_WORLD_BULK]:
        candidates.extend(sorted(directory.glob("COMTRADE-FINAL-*H*.gz")))
        candidates.extend(sorted(directory.glob("COMTRADE-FINAL-*H*.txt")))
    return candidates


def bulk_file_publication_key(path: Path) -> str:
    match = re.search(r"\[(\d{4}-\d{2}-\d{2})\]", path.name)
    return match.group(1) if match else "0000-00-00"


def bulk_file_is_preferred(candidate: Path, incumbent: Path) -> bool:
    candidate_is_canonical = candidate.parent.resolve() == COMTRADE_BULK.resolve()
    incumbent_is_canonical = incumbent.parent.resolve() == COMTRADE_BULK.resolve()
    if candidate_is_canonical != incumbent_is_canonical:
        return candidate_is_canonical
    return bulk_file_publication_key(candidate) > bulk_file_publication_key(incumbent)


def dedupe_bulk_files(files: Iterable[Path]) -> list[Path]:
    selected: dict[tuple[int, int, str], Path] = {}
    for path in files:
        metadata = bulk_file_metadata(path)
        if metadata is None:
            continue
        key = (int(metadata["reporter_code"]), int(metadata["year"]), str(metadata["classification_code"]))
        incumbent = selected.get(key)
        if incumbent is None or bulk_file_is_preferred(path, incumbent):
            selected[key] = path
    return sorted(
        selected.values(),
        key=lambda path: (
            int(bulk_file_metadata(path)["reporter_code"]),  # type: ignore[index]
            int(bulk_file_metadata(path)["year"]),  # type: ignore[index]
            str(bulk_file_metadata(path)["classification_code"]),  # type: ignore[index]
            path.name,
        ),
    )


def expected_bulk_keys_for_active_sample() -> set[tuple[int, int, str]]:
    _panel, coverage, _excluded, _manifest = build_country_sample(ACTIVE_COUNTRY_SAMPLE)
    if coverage.empty:
        return set()
    return {
        (int(row.reporter_code), int(row.year), str(row.classification_code).strip().upper())
        for row in coverage.itertuples(index=False)
        if str(row.classification_code).strip()
    }


def available_bulk_keys(files: Iterable[Path]) -> set[tuple[int, int, str]]:
    keys: set[tuple[int, int, str]] = set()
    for path in files:
        metadata = bulk_file_metadata(path)
        if metadata is None:
            continue
        keys.add((int(metadata["reporter_code"]), int(metadata["year"]), str(metadata["classification_code"]).strip().upper()))
    return keys


def missing_bulk_keys_for_active_sample(files: Iterable[Path] | None = None) -> set[tuple[int, int, str]]:
    expected = expected_bulk_keys_for_active_sample()
    if not expected:
        return set()
    files = list(files) if files is not None else dedupe_bulk_files(raw_bulk_file_candidates())
    return expected - available_bulk_keys(files)


def hs_bulk_files(max_files: int | None = None) -> list[Path]:
    files = dedupe_bulk_files(raw_bulk_file_candidates())
    panel, coverage, _excluded, _manifest = build_country_sample(ACTIVE_COUNTRY_SAMPLE)
    reporter_codes = set(panel["reporter_code"].astype(int))
    allowed_pairs = None
    if active_sample_name() != "prof_p_33" and not coverage.empty:
        allowed_pairs = set(zip(coverage["reporter_code"].astype(int), coverage["year"].astype(int)))
    filtered = []
    for path in files:
        metadata = bulk_file_metadata(path)
        if metadata is None:
            continue
        reporter_code = int(metadata["reporter_code"])
        year = int(metadata["year"])
        if reporter_code not in reporter_codes:
            continue
        if year < ACTIVE_COUNTRY_SAMPLE.start_year:
            continue
        if ACTIVE_COUNTRY_SAMPLE.end_year is not None and year > ACTIVE_COUNTRY_SAMPLE.end_year:
            continue
        if allowed_pairs is not None and (reporter_code, year) not in allowed_pairs:
            continue
        filtered.append(path)
    files = filtered
    if max_files is not None:
        return files[:max_files]
    return files


def checkpoint_name_for_raw(path: Path) -> str:
    return re.sub(r"\.(gz|txt)$", "", path.name) + ".parquet"


def first_existing_path(candidates: Iterable[Path]) -> Path | None:
    for path in candidates:
        if path.exists():
            return path
    return None


def candidate_paths_text(candidates: Iterable[Path]) -> str:
    return "\n".join(f"- `{path.relative_to(ROOT)}`" for path in candidates)


def combine_partial_group_sums(partials: Iterable[Path], group_cols: list[str], value_col: str = "trade_value", compact_rows: int = 1_000_000) -> pd.DataFrame:
    columns = [*group_cols, value_col]
    combined: pd.DataFrame | None = None
    for partial in partials:
        if not partial.exists():
            continue
        frame = pd.read_parquet(partial)
        if frame.empty:
            continue
        missing = set(columns) - set(frame.columns)
        if missing:
            raise RuntimeError(f"Checkpoint {partial} is missing required columns: {sorted(missing)}")
        frame = frame[columns].copy()
        frame = drop_excluded_hs6(frame)
        frame[value_col] = pd.to_numeric(frame[value_col], errors="coerce")
        frame = frame.dropna(subset=[value_col])
        if frame.empty:
            continue
        combined = frame if combined is None else pd.concat([combined, frame], ignore_index=True)
        if len(combined) >= compact_rows:
            combined = combined.groupby(group_cols, as_index=False)[value_col].sum()
    if combined is None or combined.empty:
        return pd.DataFrame(columns=columns)
    return combined.groupby(group_cols, as_index=False)[value_col].sum()


def combine_partial_group_sums_arrow(partials: Iterable[Path], group_cols: list[str], value_col: str = "trade_value") -> pd.DataFrame:
    import pyarrow.dataset as ds

    columns = [*group_cols, value_col]
    paths = [str(partial) for partial in partials if partial.exists()]
    if not paths:
        return pd.DataFrame(columns=columns)

    dataset = ds.dataset(paths, format="parquet")
    missing = set(columns) - set(dataset.schema.names)
    if missing:
        raise RuntimeError(f"Checkpoint dataset is missing required columns: {sorted(missing)}")

    table = dataset.to_table(columns=columns)
    if table.num_rows == 0:
        return pd.DataFrame(columns=columns)

    grouped = table.group_by(group_cols).aggregate([(value_col, "sum")])
    out = grouped.to_pandas()
    sum_col = f"{value_col}_sum"
    if sum_col in out.columns:
        out = out.rename(columns={sum_col: value_col})
    out[value_col] = pd.to_numeric(out[value_col], errors="coerce")
    out = out.dropna(subset=[value_col])
    out = drop_excluded_hs6(out)
    return out[columns].copy() if not out.empty else pd.DataFrame(columns=columns)


def add_group_sum_frame(
    combined: pd.DataFrame | None,
    frame: pd.DataFrame,
    group_cols: list[str],
    value_col: str = "trade_value",
    compact_rows: int = 500_000,
    exclude_hs6: bool = True,
) -> pd.DataFrame | None:
    columns = [*group_cols, value_col]
    if frame.empty:
        return combined
    missing = set(columns) - set(frame.columns)
    if missing:
        raise RuntimeError(f"Aggregate frame is missing required columns: {sorted(missing)}")
    frame = frame[columns].copy()
    if exclude_hs6:
        frame = drop_excluded_hs6(frame)
    frame[value_col] = pd.to_numeric(frame[value_col], errors="coerce")
    frame = frame.dropna(subset=[value_col])
    frame = frame[frame[value_col] > 0].copy()
    if frame.empty:
        return combined
    frame = frame.groupby(group_cols, as_index=False)[value_col].sum()
    combined = frame if combined is None else pd.concat([combined, frame], ignore_index=True)
    if len(combined) >= compact_rows:
        combined = combined.groupby(group_cols, as_index=False)[value_col].sum()
        gc.collect()
    return combined


def finish_group_sum_frame(
    combined: pd.DataFrame | None,
    group_cols: list[str],
    value_col: str = "trade_value",
    exclude_hs6: bool = True,
) -> pd.DataFrame:
    columns = [*group_cols, value_col]
    if combined is None or combined.empty:
        return pd.DataFrame(columns=columns)
    if exclude_hs6:
        combined = drop_excluded_hs6(combined)
    if combined.empty:
        return pd.DataFrame(columns=columns)
    return combined.groupby(group_cols, as_index=False)[value_col].sum()


def merge_metric_tables(product: pd.DataFrame, partner: pd.DataFrame, cell: pd.DataFrame) -> pd.DataFrame:
    if product.empty:
        return pd.DataFrame()
    partner_for_merge = partner.rename(columns={"total_trade_value": "partner_total_trade_value"})
    return product.merge(
        partner_for_merge,
        on=["country", "iso3", "reporter_code", "year", "flow", "variant"],
        how="outer",
    ).merge(
        cell.drop(columns=["total_trade_value"], errors="ignore"),
        on=["country", "iso3", "reporter_code", "year", "flow", "variant"],
        how="outer",
    )


def compute_exercise_06_outputs_for_leaf(leaf: pd.DataFrame, panel: pd.DataFrame) -> tuple[list[pd.DataFrame], list[pd.DataFrame]]:
    outputs = []
    removal_rows = []
    product_leaf = drop_excluded_hs6(leaf)
    base_totals = product_leaf.groupby(["reporter_code", "year", "flow"], as_index=False)["trade_value"].sum().rename(
        columns={"trade_value": "baseline_total_trade_value"}
    )

    for variant, excluded_hs2 in EXCLUSION_SETS.items():
        sub = leaf[~leaf["hs2"].isin(excluded_hs2)].copy() if excluded_hs2 else leaf
        product, partner, cell = compute_concentration(sub, variant)
        combined = merge_metric_tables(product, partner, cell)
        if combined.empty:
            continue
        combined = combined.merge(base_totals, on=["reporter_code", "year", "flow"], how="left")
        combined["trade_share_removed"] = 1 - (combined["total_trade_value"] / combined["baseline_total_trade_value"])
        outputs.append(combined)

    category_values = product_leaf[product_leaf["hs2"].isin(EXCLUSION_LABELS)].copy()
    if not category_values.empty:
        category_values["exclusion_category"] = category_values["hs2"].map(EXCLUSION_LABELS)
        cat = category_values.groupby(
            ["reporter_code", "year", "flow", "exclusion_category"], as_index=False
        )["trade_value"].sum()
        cat = cat.merge(base_totals, on=["reporter_code", "year", "flow"], how="left")
        cat["trade_share"] = cat["trade_value"] / cat["baseline_total_trade_value"]
        cat = cat.merge(panel, on="reporter_code", how="left")
        removal_rows.append(cat)

    return outputs, removal_rows


def download_reference_file(url: str, destination: Path) -> Path:
    if destination.exists() and destination.stat().st_size > 0:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_suffix(destination.suffix + ".part")
    print(f"Downloading classification reference: {url}", flush=True)
    resp = requests.get(url, timeout=(30, 240))
    resp.raise_for_status()
    tmp.write_bytes(resp.content)
    tmp.replace(destination)
    return destination


def ensure_bec_reference_files() -> None:
    download_reference_file(HS_BEC_CORRELATION_URL, HS_BEC_CORRELATION_PATH)
    download_reference_file(BEC5_REFERENCE_URL, BEC5_REFERENCE_PATH)
    download_reference_file(BEC4_REFERENCE_URL, BEC4_REFERENCE_PATH)


def normalize_digit_code(value: object, digits: int | None = None) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "nat"}:
        return ""
    text = re.sub(r"\.0$", "", text)
    match = re.search(r"\d+", text)
    if not match:
        return ""
    code = match.group(0)
    if digits is not None:
        code = code.zfill(digits)
        return code if len(code) == digits else ""
    return code


def extract_hs6_codes(value: object) -> list[str]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return []
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "nat"}:
        return []
    codes = re.findall(r"\d{6}", text)
    if codes:
        return codes
    code = normalize_digit_code(text, digits=6)
    return [code] if code else []


def strip_classification_label(text: object) -> str:
    label = "" if text is None else str(text).strip()
    return re.sub(r"^\s*[^-]+\s*-\s*", "", label).strip()


def read_bec_reference(path: Path) -> pd.DataFrame:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("results", payload) if isinstance(payload, dict) else payload
    ref = pd.DataFrame(rows)
    if ref.empty:
        return pd.DataFrame(columns=["id", "text", "label", "parent", "isLeaf", "aggrlevel"])
    ref = ref.copy()
    ref["id"] = ref["id"].astype(str).str.strip()
    ref["text"] = ref["text"].astype(str)
    ref["label"] = ref["text"].map(strip_classification_label)
    ref["parent"] = ref["parent"].astype(str).str.strip()
    ref["aggrlevel"] = pd.to_numeric(ref["aggrlevel"], errors="coerce").fillna(-1).astype(int)
    return ref


def reference_ancestor_code(ref_by_id: dict[str, dict], code: str, target_level: int) -> str:
    current = str(code).strip()
    for _ in range(20):
        row = ref_by_id.get(current)
        if row is None:
            return ""
        if int(row.get("aggrlevel", -1)) == target_level:
            return current
        parent = str(row.get("parent", "")).strip()
        if not parent or parent in {"#", "TOTAL"} or parent == current:
            return ""
        current = parent
    return ""


def bec5_end_use_from_level3_label(label: str) -> str:
    parts = [part.strip() for part in str(label).split("|")]
    return parts[2] if len(parts) >= 3 else ""


def exercise_03_bin_from_labels(bec4_level1_label: str, bec5_end_use: str) -> str:
    if "fuels and lubricants" in str(bec4_level1_label).lower():
        return "energy"
    if bec5_end_use == "Gross Fixed Capital Formation":
        return "capital_goods"
    if bec5_end_use == "Intermediate Consumption":
        return "intermediates"
    if bec5_end_use == "Final Consumption":
        return "final_consumption"
    return "unmapped_or_ambiguous"


def build_bec5_mapping_review() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    ensure_bec_reference_files()
    corr = pd.read_excel(HS_BEC_CORRELATION_PATH, sheet_name=0, dtype=str)
    col_lookup = {str(col).strip().upper(): col for col in corr.columns}
    missing = [col for col in ["BEC4", "BEC5", *COMTRADE_CLASSIFICATION_BY_HS_VERSION] if col not in col_lookup]
    if missing:
        raise RuntimeError(f"Official HS-SITC-BEC correlation table is missing columns: {missing}")

    bec4_ref = read_bec_reference(BEC4_REFERENCE_PATH)
    bec5_ref = read_bec_reference(BEC5_REFERENCE_PATH)
    bec4_by_id = bec4_ref.set_index("id").to_dict("index")
    bec5_by_id = bec5_ref.set_index("id").to_dict("index")
    bec4_label = bec4_ref.set_index("id")["label"].to_dict()
    bec5_label = bec5_ref.set_index("id")["label"].to_dict()

    rows = []
    bec4_col = col_lookup["BEC4"]
    bec5_col = col_lookup["BEC5"]
    for _, row in corr.iterrows():
        bec4_code = normalize_digit_code(row.get(bec4_col))
        bec5_code = normalize_digit_code(row.get(bec5_col))
        if not bec4_code and not bec5_code:
            continue
        for hs_version, classification_code in COMTRADE_CLASSIFICATION_BY_HS_VERSION.items():
            hs_col = col_lookup[hs_version]
            for cmd_code in extract_hs6_codes(row.get(hs_col)):
                rows.append(
                    {
                        "classification_code": classification_code,
                        "hs_version": hs_version,
                        "cmd_code": cmd_code,
                        "hs_desc_if_available": "",
                        "bec4_code": bec4_code,
                        "bec5_code": bec5_code,
                    }
                )

    raw = pd.DataFrame(rows).drop_duplicates()
    if raw.empty:
        raise RuntimeError("No HS6-to-BEC rows were extracted from the official correlation table.")
    raw = drop_excluded_hs6(raw)

    raw["bec4_label"] = raw["bec4_code"].map(bec4_label).fillna("")
    raw["bec5_label"] = raw["bec5_code"].map(bec5_label).fillna("")
    raw["bec4_level1_code"] = raw["bec4_code"].map(lambda code: reference_ancestor_code(bec4_by_id, code, 1) if code else "")
    raw["bec4_level1_label"] = raw["bec4_level1_code"].map(bec4_label).fillna("")
    raw["bec5_level3_code"] = raw["bec5_code"].map(lambda code: reference_ancestor_code(bec5_by_id, code, 3) if code else "")
    raw["bec5_level3_label"] = raw["bec5_level3_code"].map(bec5_label).fillna("")
    raw["bec5_end_use"] = raw["bec5_level3_label"].map(bec5_end_use_from_level3_label)
    raw["exercise_03_bin"] = [
        exercise_03_bin_from_labels(bec4_label_value, bec5_end_use_value)
        for bec4_label_value, bec5_end_use_value in zip(raw["bec4_level1_label"], raw["bec5_end_use"])
    ]
    raw["bec_pair"] = raw["bec4_code"].fillna("") + "|" + raw["bec5_code"].fillna("")
    keys = ["classification_code", "hs_version", "cmd_code"]
    pair_counts = raw.groupby(keys, as_index=False)["bec_pair"].nunique().rename(columns={"bec_pair": "unique_bec_pairs"})
    raw = raw.merge(pair_counts, on=keys, how="left")
    raw["mapping_status"] = np.where(raw["unique_bec_pairs"] == 1, "mapped", "ambiguous")
    raw["mapping_issue"] = np.where(raw["mapping_status"] == "mapped", "", raw["unique_bec_pairs"].astype(str) + " official BEC alternatives")
    raw.loc[raw["mapping_status"] != "mapped", "exercise_03_bin"] = "unmapped_or_ambiguous"

    review_cols = [
        "classification_code",
        "hs_version",
        "cmd_code",
        "hs_desc_if_available",
        "bec4_code",
        "bec4_label",
        "bec4_level1_code",
        "bec4_level1_label",
        "bec5_code",
        "bec5_label",
        "bec5_level3_code",
        "bec5_level3_label",
        "bec5_end_use",
        "exercise_03_bin",
        "mapping_status",
        "mapping_issue",
    ]
    review = raw[review_cols].sort_values(["classification_code", "cmd_code", "bec4_code", "bec5_code"]).reset_index(drop=True)
    ambiguities = review[review["mapping_status"] == "ambiguous"].copy()

    candidate_rows = []
    for key, group in review.groupby(keys, sort=True):
        classification_code, hs_version, cmd_code = key
        if group["mapping_status"].iloc[0] == "mapped":
            candidate_rows.append(group.iloc[0].to_dict())
            continue
        alternatives = group[["bec4_code", "bec5_code", "bec5_end_use"]].drop_duplicates().head(30)
        alternative_text = "; ".join(
            f"BEC4={row.bec4_code}, BEC5={row.bec5_code}, end_use={row.bec5_end_use}"
            for row in alternatives.itertuples(index=False)
        )
        candidate_rows.append(
            {
                "classification_code": classification_code,
                "hs_version": hs_version,
                "cmd_code": cmd_code,
                "hs_desc_if_available": "",
                "bec4_code": "",
                "bec4_label": "",
                "bec4_level1_code": "",
                "bec4_level1_label": "",
                "bec5_code": "",
                "bec5_label": "",
                "bec5_level3_code": "",
                "bec5_level3_label": "",
                "bec5_end_use": "",
                "exercise_03_bin": "unmapped_or_ambiguous",
                "mapping_status": "ambiguous",
                "mapping_issue": f"{len(group[['bec4_code', 'bec5_code']].drop_duplicates())} official BEC alternatives: {alternative_text}",
            }
        )

    candidate = pd.DataFrame(candidate_rows, columns=review_cols).sort_values(["classification_code", "cmd_code"]).reset_index(drop=True)

    coverage_rows = []
    for (hs_version, classification_code), group in candidate.groupby(["hs_version", "classification_code"], sort=True):
        row = {
            "hs_version": hs_version,
            "classification_code": classification_code,
            "candidate_hs6_codes": int(len(group)),
            "mapped_hs6_codes": int((group["mapping_status"] == "mapped").sum()),
            "ambiguous_hs6_codes": int((group["mapping_status"] == "ambiguous").sum()),
        }
        for bin_name in ["energy", "capital_goods", "intermediates", "final_consumption", "unmapped_or_ambiguous"]:
            row[f"{bin_name}_hs6_codes"] = int((group["exercise_03_bin"] == bin_name).sum())
        coverage_rows.append(row)
    coverage = pd.DataFrame(coverage_rows)
    return candidate, review, ambiguities, coverage


def prepare_bec5_mapping_review() -> pd.DataFrame:
    candidate, review, ambiguities, coverage = build_bec5_mapping_review()
    review.to_csv(EX03_TABLES / "bec5_mapping_review.csv", index=False)
    ambiguities.to_csv(EX03_TABLES / "bec5_mapping_ambiguities.csv", index=False)
    coverage.to_csv(EX03_TABLES / "bec5_mapping_coverage_by_hs_version.csv", index=False)
    candidate.to_csv(EX03_BEC_MAPPING_CANDIDATE, index=False)
    write_json(
        EX03_TABLES / "bec5_mapping_review_manifest.json",
        {
            "created_at_utc": now_utc(),
            "source_hs_sitc_bec_correlation": HS_BEC_CORRELATION_URL,
            "source_bec5_reference": BEC5_REFERENCE_URL,
            "source_bec4_reference": BEC4_REFERENCE_URL,
            "candidate_mapping": str(EX03_BEC_MAPPING_CANDIDATE.relative_to(ROOT)),
            "review_rows": int(len(review)),
            "candidate_rows": int(len(candidate)),
            "ambiguous_candidate_rows": int((candidate["mapping_status"] == "ambiguous").sum()),
            "approval_required_for_exercise_03": True,
        },
    )
    print(f"Wrote BEC5 mapping candidate: {EX03_BEC_MAPPING_CANDIDATE}", flush=True)
    print(f"Review the tables in {EX03_TABLES} before approving.", flush=True)
    return candidate


def approve_bec5_mapping() -> pd.DataFrame:
    if not EX03_BEC_MAPPING_CANDIDATE.exists():
        raise FileNotFoundError(
            f"No candidate mapping found at {EX03_BEC_MAPPING_CANDIDATE}. "
            "Run `python scripts/trade_concentration_pipeline.py --prepare-bec5-mapping-review` first."
        )
    candidate = pd.read_csv(EX03_BEC_MAPPING_CANDIDATE, dtype=str).fillna("")
    duplicate_keys = candidate.duplicated(subset=["classification_code", "cmd_code"], keep=False)
    if duplicate_keys.any():
        duplicates = candidate.loc[duplicate_keys, ["classification_code", "cmd_code"]].head(10).to_dict("records")
        raise RuntimeError(f"Candidate BEC mapping is not one-to-one. First duplicate keys: {duplicates}")
    candidate.to_csv(EX03_BEC_MAPPING_APPROVED, index=False)
    write_json(
        EX03_TABLES / "bec5_mapping_approval.json",
        {
            "approved_at_utc": now_utc(),
            "approved_mapping": str(EX03_BEC_MAPPING_APPROVED.relative_to(ROOT)),
            "candidate_mapping": str(EX03_BEC_MAPPING_CANDIDATE.relative_to(ROOT)),
            "rows": int(len(candidate)),
            "ambiguous_rows_kept_as_unmapped_or_ambiguous": int((candidate["mapping_status"] == "ambiguous").sum()),
        },
    )
    print(f"Approved BEC5 mapping: {EX03_BEC_MAPPING_APPROVED}", flush=True)
    return candidate


def load_approved_bec5_mapping() -> pd.DataFrame:
    if not EX03_BEC_MAPPING_APPROVED.exists():
        raise RuntimeError(
            "Exercise 3 requires an approved official BEC mapping. "
            "Run `python scripts/trade_concentration_pipeline.py --prepare-bec5-mapping-review`, "
            "review the generated CSVs, then run `python scripts/trade_concentration_pipeline.py --approve-bec5-mapping`."
        )
    mapping = pd.read_csv(EX03_BEC_MAPPING_APPROVED, dtype=str).fillna("")
    required = {"classification_code", "cmd_code", "exercise_03_bin", "mapping_status"}
    missing = required - set(mapping.columns)
    if missing:
        raise RuntimeError(f"Approved BEC mapping is missing required columns: {sorted(missing)}")
    mapping["classification_code"] = mapping["classification_code"].astype(str).str.strip().str.upper()
    mapping["cmd_code"] = mapping["cmd_code"].astype(str).str.extract(r"(\d{6})", expand=False).fillna("")
    duplicate_keys = mapping.duplicated(subset=["classification_code", "cmd_code"], keep=False)
    if duplicate_keys.any():
        duplicates = mapping.loc[duplicate_keys, ["classification_code", "cmd_code"]].head(10).to_dict("records")
        raise RuntimeError(f"Approved BEC mapping is not one-to-one. First duplicate keys: {duplicates}")
    return mapping


def require_leaf_classification_code(leaf: pd.DataFrame) -> None:
    if "classification_code" not in leaf.columns:
        raise RuntimeError(
            "Exercise 3 needs Comtrade `classificationCode` in the HS6 leaf data. "
            "Use streaming mode or rerun with `--keep-leaf --reprocess-raw` to rebuild the cached leaf parquet."
        )
    nonblank = leaf["classification_code"].astype(str).str.strip().replace("", np.nan).dropna()
    if nonblank.empty:
        raise RuntimeError(
            "Exercise 3 found no non-empty Comtrade `classificationCode` values. "
            "Reprocess from raw Comtrade bulk files before running Exercise 3."
        )


def exercise_03_import_aggregates_for_leaf(leaf: pd.DataFrame, mapping: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    imports = leaf[leaf["flow"] == "Imports"].copy()
    if imports.empty:
        return pd.DataFrame(), pd.DataFrame()
    require_leaf_classification_code(imports)
    imports["classification_code"] = imports["classification_code"].astype(str).str.strip().str.upper()
    imports["cmd_code"] = imports["cmd_code"].astype(str).str.extract(r"(\d{6})", expand=False).fillna("")
    imports = drop_excluded_hs6(imports)
    if imports.empty:
        return pd.DataFrame(), pd.DataFrame()

    mapping_cols = [
        "classification_code",
        "cmd_code",
        "hs_version",
        "bec4_code",
        "bec4_label",
        "bec4_level1_label",
        "bec5_code",
        "bec5_label",
        "bec5_level3_code",
        "bec5_end_use",
        "exercise_03_bin",
        "mapping_status",
        "mapping_issue",
    ]
    available_mapping_cols = [col for col in mapping_cols if col in mapping.columns]
    merged = imports.merge(mapping[available_mapping_cols], on=["classification_code", "cmd_code"], how="left")
    merged["mapping_status"] = merged["mapping_status"].fillna("unmapped").replace("", "unmapped")
    merged["exercise_03_bin"] = merged["exercise_03_bin"].fillna("unmapped_or_ambiguous").replace("", "unmapped_or_ambiguous")

    product_values = merged.groupby(["reporter_code", "year", "exercise_03_bin", "cmd_code"], as_index=False)["trade_value"].sum()
    coverage_products = merged.groupby(
        ["reporter_code", "year", "exercise_03_bin", "mapping_status", "cmd_code"], as_index=False
    )["trade_value"].sum()
    return product_values, coverage_products


def compute_exercise_03_total_concentration(product_values: pd.DataFrame, country_meta: dict) -> pd.DataFrame:
    rows = []
    for key, group in product_values.groupby(["reporter_code", "year"], sort=True):
        reporter_code, year = key
        product_totals = group.groupby("cmd_code", as_index=False)["trade_value"].sum()
        values = product_totals["trade_value"].to_numpy(dtype=float)
        meta = country_meta.get(int(reporter_code), {"country": str(reporter_code), "iso3": ""})
        rows.append(
            {
                "country": meta["country"],
                "iso3": meta["iso3"],
                "reporter_code": int(reporter_code),
                "year": int(year),
                "total_imports": float(np.sum(values)),
                "active_products": int(len(product_totals)),
                "product_gini": gini(values),
                "top_1_product_share": top_share(values, n=1),
                "top_5_product_share": top_share(values, n=5),
                "top_10_product_share": top_share(values, n=10),
            }
        )
    return pd.DataFrame(rows)


def compute_exercise_03_bin_decomposition(product_values: pd.DataFrame, country_meta: dict) -> pd.DataFrame:
    rows = []
    top_ns = [1, 5, 10]
    for key, group in product_values.groupby(["reporter_code", "year"], sort=True):
        reporter_code, year = key
        product_totals = group.groupby("cmd_code", as_index=False)["trade_value"].sum()
        product_totals = product_totals.sort_values(["trade_value", "cmd_code"], ascending=[False, True])
        total_imports = float(product_totals["trade_value"].sum())
        if total_imports <= 0:
            continue

        total_values = product_totals["trade_value"].to_numpy(dtype=float)
        total_product_gini = gini(total_values)
        total_top_shares = {n: top_share(total_values, n=n) for n in top_ns}
        top_product_sets = {n: set(product_totals.head(n)["cmd_code"].tolist()) for n in top_ns}
        meta = country_meta.get(int(reporter_code), {"country": str(reporter_code), "iso3": ""})

        for bin_name, bin_group in group.groupby("exercise_03_bin", sort=True):
            bin_imports = float(bin_group["trade_value"].sum())
            without_bin = group[group["exercise_03_bin"] != bin_name]
            without_product_totals = without_bin.groupby("cmd_code", as_index=False)["trade_value"].sum()
            without_values = without_product_totals["trade_value"].to_numpy(dtype=float)
            product_gini_without_bin = gini(without_values)

            row = {
                "country": meta["country"],
                "iso3": meta["iso3"],
                "reporter_code": int(reporter_code),
                "year": int(year),
                "import_bin": bin_name,
                "total_imports": total_imports,
                "total_product_gini": total_product_gini,
                "total_top_1_product_share": total_top_shares[1],
                "total_top_5_product_share": total_top_shares[5],
                "total_top_10_product_share": total_top_shares[10],
                "total_imports_in_bin": bin_imports,
                "import_value_share": bin_imports / total_imports,
                "active_products_in_bin": int(bin_group["cmd_code"].nunique()),
                "total_imports_without_bin": float(without_product_totals["trade_value"].sum()) if not without_product_totals.empty else 0.0,
                "active_products_without_bin": int(len(without_product_totals)),
                "product_gini_without_bin": product_gini_without_bin,
                "product_gini_reduction_when_excluded": total_product_gini - product_gini_without_bin,
            }
            for n in top_ns:
                top_value = float(bin_group.loc[bin_group["cmd_code"].isin(top_product_sets[n]), "trade_value"].sum())
                top_share_without_bin = top_share(without_values, n=n) if without_values.size else np.nan
                row[f"top_{n}_product_share_contribution"] = top_value / total_imports
                row[f"top_{n}_product_share_without_bin"] = top_share_without_bin
                row[f"top_{n}_product_share_reduction_when_excluded"] = total_top_shares[n] - top_share_without_bin
            rows.append(row)
    return pd.DataFrame(rows)


def run_exercise_03_from_aggregates(
    product_values: pd.DataFrame,
    coverage_products: pd.DataFrame,
    source_details: dict | None = None,
) -> pd.DataFrame:
    if product_values.empty:
        raise RuntimeError("No Exercise 3 import product rows were produced.")
    product_values = product_values.groupby(["reporter_code", "year", "exercise_03_bin", "cmd_code"], as_index=False)["trade_value"].sum()
    coverage_products = coverage_products.groupby(
        ["reporter_code", "year", "exercise_03_bin", "mapping_status", "cmd_code"], as_index=False
    )["trade_value"].sum()

    panel = save_country_panel()
    country_meta = panel.set_index("reporter_code")[["country", "iso3"]].to_dict("index")
    rows = []
    for key, group in product_values.groupby(["reporter_code", "year", "exercise_03_bin"], sort=True):
        reporter_code, year, bin_name = key
        values = group["trade_value"].to_numpy(dtype=float)
        meta = country_meta.get(int(reporter_code), {"country": str(reporter_code), "iso3": ""})
        rows.append(
            {
                "country": meta["country"],
                "iso3": meta["iso3"],
                "reporter_code": int(reporter_code),
                "year": int(year),
                "import_bin": bin_name,
                "total_imports_in_bin": float(np.sum(values)),
                "active_products": int(len(values)),
                "product_gini": gini(values),
                "top_1_product_share": top_share(values, n=1),
                "top_5_product_share": top_share(values, n=5),
                "top_10_product_share": top_share(values, n=10),
            }
        )
    concentration = pd.DataFrame(rows)
    concentration.to_parquet(sample_processed_path("exercise_03_import_bin_concentration.parquet"), index=False)
    concentration.to_csv(EX03_TABLES / "import_bin_concentration.csv", index=False)

    total_concentration = compute_exercise_03_total_concentration(product_values, country_meta)
    total_concentration.to_parquet(sample_processed_path("exercise_03_total_import_concentration.parquet"), index=False)
    total_concentration.to_csv(EX03_TABLES / "import_total_concentration.csv", index=False)

    decomposition = compute_exercise_03_bin_decomposition(product_values, country_meta)
    decomposition.to_parquet(sample_processed_path("exercise_03_import_bin_decomposition.parquet"), index=False)
    decomposition.to_csv(EX03_TABLES / "import_bin_decomposition.csv", index=False)

    coverage = coverage_products.groupby(
        ["reporter_code", "year", "exercise_03_bin", "mapping_status"], as_index=False
    ).agg(import_value=("trade_value", "sum"), active_products=("cmd_code", "nunique"))
    totals = coverage.groupby(["reporter_code", "year"], as_index=False)["import_value"].sum().rename(
        columns={"import_value": "total_imports"}
    )
    coverage = coverage.merge(totals, on=["reporter_code", "year"], how="left")
    coverage["import_value_share"] = coverage["import_value"] / coverage["total_imports"].replace(0, np.nan)
    coverage = add_country_metadata(coverage)
    coverage = coverage.rename(columns={"exercise_03_bin": "import_bin"})
    coverage.to_csv(EX03_TABLES / "import_bin_mapping_coverage.csv", index=False)

    make_exercise_03_figures(concentration, coverage, decomposition)
    write_exercise_03_memo(concentration, coverage, total_concentration, decomposition, source_details or {})
    return concentration


def run_exercise_03(leaf: pd.DataFrame) -> pd.DataFrame:
    mapping = load_approved_bec5_mapping()
    product_values, coverage_products = exercise_03_import_aggregates_for_leaf(leaf, mapping)
    return run_exercise_03_from_aggregates(product_values, coverage_products, source_details={"mode": "in_memory_leaf"})


def standardize_exercise_03_product_values(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["reporter_code", "year", "exercise_03_bin", "cmd_code", "trade_value"]
    out = df.copy()
    for col in cols:
        if col not in out.columns:
            out[col] = pd.NA
    out = out[cols].copy()
    out["reporter_code"] = pd.to_numeric(out["reporter_code"], errors="coerce")
    out["year"] = pd.to_numeric(out["year"], errors="coerce")
    out["exercise_03_bin"] = out["exercise_03_bin"].astype(str).replace({"nan": "", "None": ""})
    out["cmd_code"] = out["cmd_code"].astype(str).str.extract(r"(\d{6})", expand=False)
    out["trade_value"] = pd.to_numeric(out["trade_value"], errors="coerce")
    out = out.dropna(subset=["reporter_code", "year", "exercise_03_bin", "cmd_code", "trade_value"])
    out = out[out["trade_value"] > 0].copy()
    out = drop_excluded_hs6(out)
    if out.empty:
        return pd.DataFrame(columns=cols)
    out["reporter_code"] = out["reporter_code"].astype(int)
    out["year"] = out["year"].astype(int)
    return out.groupby(["reporter_code", "year", "exercise_03_bin", "cmd_code"], as_index=False)["trade_value"].sum()


def standardize_exercise_03_coverage_products(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["reporter_code", "year", "exercise_03_bin", "mapping_status", "cmd_code", "trade_value"]
    out = df.copy()
    for col in cols:
        if col not in out.columns:
            out[col] = pd.NA
    out = out[cols].copy()
    out["reporter_code"] = pd.to_numeric(out["reporter_code"], errors="coerce")
    out["year"] = pd.to_numeric(out["year"], errors="coerce")
    out["exercise_03_bin"] = out["exercise_03_bin"].astype(str).replace({"nan": "", "None": ""})
    out["mapping_status"] = out["mapping_status"].astype(str).replace({"nan": "", "None": ""})
    out["cmd_code"] = out["cmd_code"].astype(str).str.extract(r"(\d{6})", expand=False)
    out["trade_value"] = pd.to_numeric(out["trade_value"], errors="coerce")
    out = out.dropna(subset=["reporter_code", "year", "exercise_03_bin", "mapping_status", "cmd_code", "trade_value"])
    out = out[out["trade_value"] > 0].copy()
    out = drop_excluded_hs6(out)
    if out.empty:
        return pd.DataFrame(columns=cols)
    out["reporter_code"] = out["reporter_code"].astype(int)
    out["year"] = out["year"].astype(int)
    return out.groupby(["reporter_code", "year", "exercise_03_bin", "mapping_status", "cmd_code"], as_index=False)["trade_value"].sum()


def exercise_03_partial_paths(raw_path: Path) -> tuple[Path, Path]:
    name = checkpoint_name_for_raw(raw_path)
    return EX03_PRODUCT_PARTIAL_DIR / name, EX03_COVERAGE_PARTIAL_DIR / name


def write_exercise_03_partial_for_leaf(raw_path: Path, leaf: pd.DataFrame, mapping: pd.DataFrame) -> tuple[Path, Path, int, int]:
    product_partial, coverage_partial = exercise_03_partial_paths(raw_path)
    product_values, coverage_products = exercise_03_import_aggregates_for_leaf(leaf, mapping)
    product_values = standardize_exercise_03_product_values(product_values)
    coverage_products = standardize_exercise_03_coverage_products(coverage_products)
    product_values.to_parquet(product_partial, index=False)
    coverage_products.to_parquet(coverage_partial, index=False)
    return product_partial, coverage_partial, int(len(product_values)), int(len(coverage_products))


def aggregate_exercises_03_04_for_raw(
    raw_path: Path,
    mapping: pd.DataFrame | None,
    include_exercise_03: bool = True,
    include_exercise_04: bool = True,
    chunk_rows: int = DEFAULT_CHUNK_ROWS,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if include_exercise_03 and mapping is None:
        raise RuntimeError("Exercise 3 raw aggregation requires an approved BEC mapping.")

    ex03_product_cols = ["reporter_code", "year", "exercise_03_bin", "cmd_code"]
    ex03_coverage_cols = ["reporter_code", "year", "exercise_03_bin", "mapping_status", "cmd_code"]
    ex04_supplier_cols = ["reporter_code", "year", "cmd_code", "partner_code"]
    product_values: pd.DataFrame | None = None
    coverage_products: pd.DataFrame | None = None
    supplier_values: pd.DataFrame | None = None

    for leaf in iter_leaf_trade_chunks(raw_path, chunk_rows=chunk_rows):
        if include_exercise_03:
            chunk_product, chunk_coverage = exercise_03_import_aggregates_for_leaf(leaf, mapping)
            chunk_product = standardize_exercise_03_product_values(chunk_product)
            chunk_coverage = standardize_exercise_03_coverage_products(chunk_coverage)
            product_values = add_group_sum_frame(product_values, chunk_product, ex03_product_cols)
            coverage_products = add_group_sum_frame(coverage_products, chunk_coverage, ex03_coverage_cols)
        if include_exercise_04:
            chunk_supplier = standardize_exercise_04_supplier_values(exercise_04_supplier_values_for_leaf(leaf))
            supplier_values = add_group_sum_frame(supplier_values, chunk_supplier, ex04_supplier_cols, exclude_hs6=False)
        del leaf

    product_out = standardize_exercise_03_product_values(finish_group_sum_frame(product_values, ex03_product_cols))
    coverage_out = standardize_exercise_03_coverage_products(finish_group_sum_frame(coverage_products, ex03_coverage_cols))
    supplier_out = standardize_exercise_04_supplier_values(finish_group_sum_frame(supplier_values, ex04_supplier_cols, exclude_hs6=False))
    return product_out, coverage_out, supplier_out


def write_exercise_03_partial_for_raw(raw_path: Path, mapping: pd.DataFrame, chunk_rows: int = DEFAULT_CHUNK_ROWS) -> tuple[Path, Path, int, int]:
    product_partial, coverage_partial = exercise_03_partial_paths(raw_path)
    product_values, coverage_products, _supplier_values = aggregate_exercises_03_04_for_raw(
        raw_path,
        mapping,
        include_exercise_03=True,
        include_exercise_04=False,
        chunk_rows=chunk_rows,
    )
    product_values.to_parquet(product_partial, index=False)
    coverage_products.to_parquet(coverage_partial, index=False)
    return product_partial, coverage_partial, int(len(product_values)), int(len(coverage_products))


def write_exercises_03_04_partials_for_raw(
    raw_path: Path,
    mapping: pd.DataFrame,
    chunk_rows: int = DEFAULT_CHUNK_ROWS,
) -> tuple[Path, Path, Path, int, int, int]:
    product_partial, coverage_partial = exercise_03_partial_paths(raw_path)
    supplier_partial = exercise_04_partial_path(raw_path)
    product_values, coverage_products, supplier_values = aggregate_exercises_03_04_for_raw(
        raw_path,
        mapping,
        include_exercise_03=True,
        include_exercise_04=True,
        chunk_rows=chunk_rows,
    )
    product_values.to_parquet(product_partial, index=False)
    coverage_products.to_parquet(coverage_partial, index=False)
    supplier_values.to_parquet(supplier_partial, index=False)
    return (
        product_partial,
        coverage_partial,
        supplier_partial,
        int(len(product_values)),
        int(len(coverage_products)),
        int(len(supplier_values)),
    )


def write_exercise_03_partials(max_files: int | None = None, fresh: bool = False, chunk_rows: int = DEFAULT_CHUNK_ROWS) -> tuple[list[Path], list[Path]]:
    if fresh and EX03_PARTIAL_DIR.exists():
        shutil.rmtree(EX03_PARTIAL_DIR)
    EX03_PRODUCT_PARTIAL_DIR.mkdir(parents=True, exist_ok=True)
    EX03_COVERAGE_PARTIAL_DIR.mkdir(parents=True, exist_ok=True)
    mapping = load_approved_bec5_mapping()
    files = hs_bulk_files(max_files=max_files)
    if not files:
        raise FileNotFoundError(f"No HS Comtrade bulk files found in {COMTRADE_BULK}")

    product_partials = []
    coverage_partials = []
    manifest_rows = []
    for idx, path in enumerate(files, start=1):
        product_partial, coverage_partial = exercise_03_partial_paths(path)
        product_partials.append(product_partial)
        coverage_partials.append(coverage_partial)
        if product_partial.exists() and coverage_partial.exists():
            print(f"[{idx}/{len(files)}] skip existing Exercise 3 checkpoints for {path.name}", flush=True)
            manifest_rows.append({"raw_file": path.name, "status": "already_exists"})
            continue

        print(f"[{idx}/{len(files)}] Exercise 3 import bins from {path.name}", flush=True)
        _, _, product_rows, coverage_rows = write_exercise_03_partial_for_raw(path, mapping, chunk_rows=chunk_rows)
        manifest_rows.append(
            {
                "raw_file": path.name,
                "status": "written",
                "product_rows": product_rows,
                "coverage_rows": coverage_rows,
            }
        )
        write_json(
            RESULTS / "run_manifest_exercise_03_checkpoints.json",
            {
                "created_at_utc": now_utc(),
                "mode": "exercise_03_checkpoint_partials",
                "raw_files_seen": len(files),
                "raw_files_attempted": idx,
                "partial_files_present": {
                    "product_values": len(list(EX03_PRODUCT_PARTIAL_DIR.glob("*.parquet"))),
                    "mapping_coverage": len(list(EX03_COVERAGE_PARTIAL_DIR.glob("*.parquet"))),
                },
                "latest_raw_file": path.name,
                "manifest_tail": manifest_rows[-25:],
                "approved_mapping": str(EX03_BEC_MAPPING_APPROVED.relative_to(ROOT)),
                "exercises_md_updated": False,
            },
        )
    return product_partials, coverage_partials


def finalize_exercise_03_from_partials(product_partials: list[Path], coverage_partials: list[Path], source_details: dict | None = None) -> pd.DataFrame:
    product_values = combine_partial_group_sums_arrow(product_partials, ["reporter_code", "year", "exercise_03_bin", "cmd_code"])
    coverage_products = combine_partial_group_sums_arrow(
        coverage_partials, ["reporter_code", "year", "exercise_03_bin", "mapping_status", "cmd_code"]
    )
    product_values = standardize_exercise_03_product_values(product_values)
    coverage_products = standardize_exercise_03_coverage_products(coverage_products)
    if product_values.empty:
        raise RuntimeError("No Exercise 3 import product rows were produced from checkpoint files.")
    return run_exercise_03_from_aggregates(product_values, coverage_products, source_details=source_details or {})


def run_exercise_03_streaming(
    max_files: int | None = None,
    fresh_checkpoints: bool = False,
    finalize_only: bool = False,
    chunk_rows: int = DEFAULT_CHUNK_ROWS,
) -> pd.DataFrame:
    if finalize_only:
        load_approved_bec5_mapping()
        files = hs_bulk_files(max_files=max_files)
        if files:
            partial_pairs = [exercise_03_partial_paths(path) for path in files]
            product_partials = [pair[0] for pair in partial_pairs]
            coverage_partials = [pair[1] for pair in partial_pairs]
        else:
            product_partials = sorted(EX03_PRODUCT_PARTIAL_DIR.glob("*.parquet"))
            coverage_partials = sorted(EX03_COVERAGE_PARTIAL_DIR.glob("*.parquet"))
        missing = [path for path in [*product_partials, *coverage_partials] if not path.exists()]
        if not product_partials or not coverage_partials or missing:
            raise RuntimeError(f"No complete Exercise 3 checkpoint set found in {EX03_PARTIAL_DIR}.")
    else:
        product_partials, coverage_partials = write_exercise_03_partials(
            max_files=max_files,
            fresh=fresh_checkpoints,
            chunk_rows=chunk_rows,
        )

    files = hs_bulk_files(max_files=max_files)
    concentration = finalize_exercise_03_from_partials(
        product_partials,
        coverage_partials,
        source_details={
            "mode": "checkpointed_streaming",
            "hs_bulk_files_seen": len(files) if files else None,
            "partial_files": {
                "product_values": len(product_partials),
                "mapping_coverage": len(coverage_partials),
            },
            "partial_dir": str(EX03_PARTIAL_DIR.relative_to(ROOT)),
            "finalize_only": finalize_only,
            "chunk_rows": int(chunk_rows),
        },
    )
    write_json(
        RESULTS / "run_manifest.json",
        {
            "created_at_utc": now_utc(),
            "mode": "exercise_03_checkpointed",
            "exercise": "3",
            "hs_bulk_files_seen": len(files) if files else None,
            "partial_files": {
                "product_values": len(product_partials),
                "mapping_coverage": len(coverage_partials),
            },
            "rows_concentration": int(len(concentration)),
            "approved_mapping": str(EX03_BEC_MAPPING_APPROVED.relative_to(ROOT)),
            "exercises_md_updated": False,
        },
    )
    return concentration


def make_exercise_03_figures(concentration: pd.DataFrame, coverage: pd.DataFrame, decomposition: pd.DataFrame) -> None:
    import matplotlib.pyplot as plt
    import seaborn as sns

    sns.set_theme(style="whitegrid")
    main = concentration[concentration["import_bin"] != "unmapped_or_ambiguous"].copy()
    if not main.empty:
        med = main.groupby(["year", "import_bin"], as_index=False)["product_gini"].median()
        plt.figure(figsize=(12, 7))
        sns.lineplot(data=med, x="year", y="product_gini", hue="import_bin", errorbar=None)
        plt.title("Exercise 3: Median Import Product Gini By BEC Bin")
        plt.tight_layout()
        plt.savefig(EX03_FIGURES / "median_import_product_gini_by_bin.png", dpi=200)
        plt.close()

        latest = main[main["year"] == main["year"].max()].copy()
        plt.figure(figsize=(11, 7))
        sns.boxplot(data=latest, x="import_bin", y="product_gini")
        plt.xticks(rotation=20, ha="right")
        plt.title(f"Exercise 3: Import Gini Distribution By Bin ({int(main['year'].max())})")
        plt.tight_layout()
        plt.savefig(EX03_FIGURES / "latest_year_import_gini_by_bin.png", dpi=200)
        plt.close()

    if not coverage.empty:
        mapped = coverage.assign(is_mapped=coverage["mapping_status"] == "mapped")
        mapped_share = mapped.groupby(["year", "mapping_status"], as_index=False)["import_value_share"].median()
        plt.figure(figsize=(12, 7))
        sns.lineplot(data=mapped_share, x="year", y="import_value_share", hue="mapping_status", errorbar=None)
        plt.title("Exercise 3: Median Import Value Share By Mapping Status")
        plt.tight_layout()
        plt.savefig(EX03_FIGURES / "mapping_status_import_value_share.png", dpi=200)
        plt.close()

    if not decomposition.empty:
        decomp_main = decomposition[decomposition["import_bin"].isin(EX03_RESEARCH_BINS)].copy()
        if not decomp_main.empty:
            value_share = decomp_main.groupby(["year", "import_bin"], as_index=False)["import_value_share"].median()
            plt.figure(figsize=(12, 7))
            sns.lineplot(data=value_share, x="year", y="import_value_share", hue="import_bin", errorbar=None)
            plt.title("Exercise 3: Median Import Value Share By Bin")
            plt.tight_layout()
            plt.savefig(EX03_FIGURES / "median_import_value_share_by_bin.png", dpi=200)
            plt.close()

            top10 = decomp_main.groupby(["year", "import_bin"], as_index=False)["top_10_product_share_contribution"].median()
            plt.figure(figsize=(12, 7))
            sns.lineplot(data=top10, x="year", y="top_10_product_share_contribution", hue="import_bin", errorbar=None)
            plt.title("Exercise 3: Median Top-10 Import Share Contribution By Bin")
            plt.tight_layout()
            plt.savefig(EX03_FIGURES / "median_top10_import_share_contribution_by_bin.png", dpi=200)
            plt.close()

            latest = decomp_main[decomp_main["year"] == decomp_main["year"].max()].copy()
            plt.figure(figsize=(11, 7))
            sns.boxplot(data=latest, x="import_bin", y="product_gini_reduction_when_excluded")
            plt.xticks(rotation=20, ha="right")
            plt.axhline(0, color="black", linewidth=1)
            plt.title(f"Exercise 3: Gini Reduction When Bin Is Excluded ({int(decomp_main['year'].max())})")
            plt.tight_layout()
            plt.savefig(EX03_FIGURES / "latest_year_gini_reduction_when_bin_excluded.png", dpi=200)
            plt.close()


def write_exercise_03_memo(
    concentration: pd.DataFrame,
    coverage: pd.DataFrame,
    total_concentration: pd.DataFrame,
    decomposition: pd.DataFrame,
    source_details: dict,
) -> None:
    main = concentration[concentration["import_bin"] != "unmapped_or_ambiguous"].copy()
    summary = (
        main.groupby("import_bin", as_index=False)
        .agg(
            rows=("product_gini", "size"),
            median_product_gini=("product_gini", "median"),
            median_top_1_product_share=("top_1_product_share", "median"),
            median_active_products=("active_products", "median"),
        )
        .round(4)
        if not main.empty
        else pd.DataFrame()
    )
    total_summary = (
        total_concentration[
            ["product_gini", "top_1_product_share", "top_5_product_share", "top_10_product_share", "active_products"]
        ]
        .median()
        .to_frame("median_country_year")
        .round(4)
        if not total_concentration.empty
        else pd.DataFrame()
    )
    decomp_main = decomposition[decomposition["import_bin"].isin(EX03_RESEARCH_BINS)].copy() if not decomposition.empty else pd.DataFrame()
    value_share_summary = (
        decomp_main.groupby("import_bin", as_index=False)
        .agg(
            rows=("import_value_share", "size"),
            median_import_value_share=("import_value_share", "median"),
            median_total_imports_in_bin=("total_imports_in_bin", "median"),
        )
        .round(4)
        if not decomp_main.empty
        else pd.DataFrame()
    )
    top_contribution_summary = (
        decomp_main.groupby("import_bin", as_index=False)
        .agg(
            median_top_1_product_share_contribution=("top_1_product_share_contribution", "median"),
            median_top_5_product_share_contribution=("top_5_product_share_contribution", "median"),
            median_top_10_product_share_contribution=("top_10_product_share_contribution", "median"),
        )
        .round(4)
        if not decomp_main.empty
        else pd.DataFrame()
    )
    leave_one_out_summary = (
        decomp_main.groupby("import_bin", as_index=False)
        .agg(
            median_product_gini_without_bin=("product_gini_without_bin", "median"),
            median_product_gini_reduction_when_excluded=("product_gini_reduction_when_excluded", "median"),
            median_top_10_product_share_reduction_when_excluded=("top_10_product_share_reduction_when_excluded", "median"),
        )
        .round(4)
        if not decomp_main.empty
        else pd.DataFrame()
    )
    coverage_summary = (
        coverage.groupby("mapping_status", as_index=False)["import_value_share"].median().round(4)
        if not coverage.empty
        else pd.DataFrame()
    )
    memo = f"""# Exercise 3: Import Bin Exercise

Generated: {now_utc()}

This memo is intentionally descriptive. `exercises.md` should only be updated after discussion.

## Coverage

- Country-year-bin rows: {len(concentration)}
- Countries: {concentration["country"].nunique() if not concentration.empty else 0}
- Years: {int(concentration["year"].min()) if not concentration.empty else "n/a"}-{int(concentration["year"].max()) if not concentration.empty else "n/a"}
- Approved mapping: `{EX03_BEC_MAPPING_APPROVED.relative_to(ROOT)}`
- Source details: `{json.dumps(source_details, sort_keys=True)}`

## Median Concentration By Import Bin

{summary.to_markdown(index=False) if not summary.empty else "No mapped import-bin summary was produced."}

## Median Aggregate Import Concentration

{total_summary.to_markdown() if not total_summary.empty else "No aggregate import concentration summary was produced."}

## Median Import Value Share By Bin

{value_share_summary.to_markdown(index=False) if not value_share_summary.empty else "No import value-share decomposition was produced."}

## Median Top-Product Share Contribution By Bin

{top_contribution_summary.to_markdown(index=False) if not top_contribution_summary.empty else "No top-product contribution decomposition was produced."}

## Median Leave-One-Bin-Out Contribution

Positive `product_gini_reduction_when_excluded` means the bin raises aggregate import concentration; negative means it dilutes aggregate concentration.

{leave_one_out_summary.to_markdown(index=False) if not leave_one_out_summary.empty else "No leave-one-bin-out decomposition was produced."}

## Median Import Value Share By Mapping Status

{coverage_summary.to_markdown(index=False) if not coverage_summary.empty else "No mapping coverage summary was produced."}

## Files

- Tables: `results/exercise_03_tables/`
- Figures: `results/exercise_03_figures/`
- Processed data: `data/processed/exercise_03_import_bin_concentration.parquet`, `data/processed/exercise_03_total_import_concentration.parquet`, `data/processed/exercise_03_import_bin_decomposition.parquet`

## Discussion Prompt

Which bins are internally concentrated, and which bins actually account for aggregate import concentration?
"""
    write_text(RESULTS / "exercise_03_import_bins.md", memo)


def exercise_04_supplier_values_for_leaf(leaf: pd.DataFrame) -> pd.DataFrame:
    imports = leaf[leaf["flow"] == "Imports"].copy()
    if imports.empty:
        return pd.DataFrame()
    return imports.groupby(["reporter_code", "year", "cmd_code", "partner_code"], as_index=False)["trade_value"].sum()


def weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    values_arr = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
    weights_arr = pd.to_numeric(weights, errors="coerce").to_numpy(dtype=float)
    mask = np.isfinite(values_arr) & np.isfinite(weights_arr) & (weights_arr > 0)
    if not mask.any():
        return np.nan
    return float(np.average(values_arr[mask], weights=weights_arr[mask]))


def exercise_04_product_metrics_from_supplier_values(supplier_values: pd.DataFrame, partner_ref: pd.DataFrame | None = None) -> pd.DataFrame:
    if supplier_values.empty:
        return pd.DataFrame()
    supplier_values = drop_excluded_hs6(supplier_values)
    if supplier_values.empty:
        return pd.DataFrame()
    supplier_values = supplier_values.groupby(["reporter_code", "year", "cmd_code", "partner_code"], as_index=False)["trade_value"].sum()
    keys = ["reporter_code", "year", "cmd_code"]
    totals = supplier_values.groupby(keys, as_index=False)["trade_value"].sum().rename(columns={"trade_value": "total_product_imports"})
    shares = supplier_values.merge(totals, on=keys, how="left")
    shares["supplier_share"] = shares["trade_value"] / shares["total_product_imports"].replace(0, np.nan)
    top = shares.sort_values(["reporter_code", "year", "cmd_code", "trade_value", "partner_code"], ascending=[True, True, True, False, True])
    top = top.groupby(keys, as_index=False).head(1).rename(
        columns={
            "partner_code": "top_supplier_code",
            "trade_value": "top_supplier_imports",
            "supplier_share": "top_supplier_share",
        }
    )
    hhi = shares.groupby(keys, as_index=False).agg(
        source_hhi=("supplier_share", lambda s: float(np.square(s.to_numpy(dtype=float)).sum())),
        supplier_count=("partner_code", "nunique"),
    )
    product = totals.merge(top[keys + ["top_supplier_code", "top_supplier_imports", "top_supplier_share"]], on=keys, how="left")
    product = product.merge(hhi, on=keys, how="left")
    ref = partner_reference_table() if partner_ref is None else partner_ref
    if not ref.empty:
        ref = ref.rename(
            columns={
                "partner_code": "top_supplier_code",
                "partner_iso3": "top_supplier_iso3",
                "partner_name": "top_supplier_name",
            }
        )
        product = product.merge(ref[["top_supplier_code", "top_supplier_iso3", "top_supplier_name"]], on="top_supplier_code", how="left")
    return add_country_metadata(product)


def write_exercise_04_outputs(product: pd.DataFrame, source_details: dict | None = None) -> pd.DataFrame:
    if product.empty:
        raise RuntimeError("No Exercise 4 import supplier rows were produced.")
    product.to_parquet(sample_processed_path("exercise_04_dominant_supplier_by_product.parquet"), index=False)
    product.to_csv(EX04_TABLES / "dominant_supplier_by_product.csv", index=False)

    summary_rows = []
    for key, group in product.groupby(["reporter_code", "year"], sort=True):
        reporter_code, year = key
        total_imports = float(group["total_product_imports"].sum())
        summary_rows.append(
            {
                "reporter_code": int(reporter_code),
                "year": int(year),
                "total_imports": total_imports,
                "import_products": int(len(group)),
                "weighted_mean_top_supplier_share": weighted_mean(group["top_supplier_share"], group["total_product_imports"]),
                "weighted_mean_source_hhi": weighted_mean(group["source_hhi"], group["total_product_imports"]),
                "median_top_supplier_share": float(group["top_supplier_share"].median()),
                "median_source_hhi": float(group["source_hhi"].median()),
                "share_products_top_supplier_ge_50": float((group["top_supplier_share"] >= 0.50).mean()),
                "share_products_top_supplier_ge_75": float((group["top_supplier_share"] >= 0.75).mean()),
                "share_products_top_supplier_ge_90": float((group["top_supplier_share"] >= 0.90).mean()),
                "import_value_share_products_top_supplier_ge_50": float(group.loc[group["top_supplier_share"] >= 0.50, "total_product_imports"].sum() / total_imports)
                if total_imports > 0
                else np.nan,
                "import_value_share_products_top_supplier_ge_75": float(group.loc[group["top_supplier_share"] >= 0.75, "total_product_imports"].sum() / total_imports)
                if total_imports > 0
                else np.nan,
                "import_value_share_products_top_supplier_ge_90": float(group.loc[group["top_supplier_share"] >= 0.90, "total_product_imports"].sum() / total_imports)
                if total_imports > 0
                else np.nan,
            }
        )
    summary = add_country_metadata(pd.DataFrame(summary_rows))
    summary.to_csv(EX04_TABLES / "dominant_supplier_importer_summary.csv", index=False)
    make_exercise_04_figures(product, summary)
    write_exercise_04_memo(product, summary, source_details or {})
    return product


def run_exercise_04_from_supplier_values(supplier_values: pd.DataFrame, source_details: dict | None = None) -> pd.DataFrame:
    product = exercise_04_product_metrics_from_supplier_values(supplier_values)
    return write_exercise_04_outputs(product, source_details=source_details or {})


def run_exercise_04(leaf: pd.DataFrame) -> pd.DataFrame:
    supplier_values = exercise_04_supplier_values_for_leaf(leaf)
    return run_exercise_04_from_supplier_values(supplier_values, source_details={"mode": "in_memory_leaf"})


def standardize_exercise_04_supplier_values(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["reporter_code", "year", "cmd_code", "partner_code", "trade_value"]
    out = df.copy()
    for col in cols:
        if col not in out.columns:
            out[col] = pd.NA
    out = out[cols].copy()
    out["reporter_code"] = pd.to_numeric(out["reporter_code"], errors="coerce")
    out["year"] = pd.to_numeric(out["year"], errors="coerce")
    out["partner_code"] = pd.to_numeric(out["partner_code"], errors="coerce")
    out["cmd_code"] = out["cmd_code"].astype(str).str.extract(r"(\d{6})", expand=False)
    out["trade_value"] = pd.to_numeric(out["trade_value"], errors="coerce")
    out = out.dropna(subset=["reporter_code", "year", "cmd_code", "partner_code", "trade_value"])
    out = out[out["trade_value"] > 0].copy()
    if out.empty:
        return pd.DataFrame(columns=cols)
    out["reporter_code"] = out["reporter_code"].astype(int)
    out["year"] = out["year"].astype(int)
    out["partner_code"] = out["partner_code"].astype(int)
    return out.groupby(["reporter_code", "year", "cmd_code", "partner_code"], as_index=False)["trade_value"].sum()


def exercise_04_partial_path(raw_path: Path) -> Path:
    return EX04_PARTIAL_DIR / checkpoint_name_for_raw(raw_path)


def write_exercise_04_partial_for_leaf(raw_path: Path, leaf: pd.DataFrame) -> tuple[Path, int]:
    partial = exercise_04_partial_path(raw_path)
    values = standardize_exercise_04_supplier_values(exercise_04_supplier_values_for_leaf(leaf))
    values.to_parquet(partial, index=False)
    return partial, int(len(values))


def write_exercise_04_partial_for_raw(raw_path: Path, chunk_rows: int = DEFAULT_CHUNK_ROWS) -> tuple[Path, int]:
    partial = exercise_04_partial_path(raw_path)
    _product_values, _coverage_products, supplier_values = aggregate_exercises_03_04_for_raw(
        raw_path,
        mapping=None,
        include_exercise_03=False,
        include_exercise_04=True,
        chunk_rows=chunk_rows,
    )
    supplier_values.to_parquet(partial, index=False)
    return partial, int(len(supplier_values))


def write_exercise_04_partials(max_files: int | None = None, fresh: bool = False, chunk_rows: int = DEFAULT_CHUNK_ROWS) -> list[Path]:
    if fresh and EX04_PARTIAL_DIR.exists():
        shutil.rmtree(EX04_PARTIAL_DIR)
    EX04_PARTIAL_DIR.mkdir(parents=True, exist_ok=True)
    files = hs_bulk_files(max_files=max_files)
    if not files:
        raise FileNotFoundError(f"No HS Comtrade bulk files found in {COMTRADE_BULK}")

    partials = []
    manifest_rows = []
    for idx, path in enumerate(files, start=1):
        partial = exercise_04_partial_path(path)
        partials.append(partial)
        if partial.exists():
            print(f"[{idx}/{len(files)}] skip existing Exercise 4 checkpoint {partial.name}", flush=True)
            manifest_rows.append({"raw_file": path.name, "partial_file": partial.name, "status": "already_exists"})
            continue
        print(f"[{idx}/{len(files)}] Exercise 4 dominant suppliers from {path.name}", flush=True)
        _, rows = write_exercise_04_partial_for_raw(path, chunk_rows=chunk_rows)
        manifest_rows.append({"raw_file": path.name, "partial_file": partial.name, "status": "written", "rows": rows})
        write_json(
            RESULTS / "run_manifest_exercise_04_checkpoints.json",
            {
                "created_at_utc": now_utc(),
                "mode": "exercise_04_checkpoint_partials",
                "raw_files_seen": len(files),
                "raw_files_attempted": idx,
                "partial_files_present": len(list(EX04_PARTIAL_DIR.glob("*.parquet"))),
                "latest_raw_file": path.name,
                "manifest_tail": manifest_rows[-25:],
                "exercises_md_updated": False,
            },
        )
    return partials


def finalize_exercise_04_from_partials(partials: list[Path], source_details: dict | None = None) -> pd.DataFrame:
    product_frames: list[pd.DataFrame] = []
    partner_ref = partner_reference_table()
    for idx, partial in enumerate(partials, start=1):
        if not partial.exists():
            continue
        supplier_values = standardize_exercise_04_supplier_values(pd.read_parquet(partial))
        if supplier_values.empty:
            continue
        product = exercise_04_product_metrics_from_supplier_values(supplier_values, partner_ref=partner_ref)
        if not product.empty:
            product_frames.append(product)
        if idx % 100 == 0:
            print(f"finalized Exercise 4 partial {idx}/{len(partials)}", flush=True)
        del supplier_values
    if not product_frames:
        raise RuntimeError("No Exercise 4 import supplier rows were produced from checkpoint files.")
    product = pd.concat(product_frames, ignore_index=True)
    duplicate_keys = product.duplicated(subset=["reporter_code", "year", "cmd_code"], keep=False)
    if duplicate_keys.any():
        examples = product.loc[duplicate_keys, ["reporter_code", "year", "cmd_code"]].head(10).to_dict("records")
        raise RuntimeError(f"Exercise 4 checkpoint set has duplicate reporter-year-product keys: {examples}")
    return write_exercise_04_outputs(product, source_details=source_details or {})


def run_exercise_04_streaming(
    max_files: int | None = None,
    fresh_checkpoints: bool = False,
    finalize_only: bool = False,
    chunk_rows: int = DEFAULT_CHUNK_ROWS,
) -> pd.DataFrame:
    if finalize_only:
        files = hs_bulk_files(max_files=max_files)
        partials = [exercise_04_partial_path(path) for path in files] if files else sorted(EX04_PARTIAL_DIR.glob("*.parquet"))
        missing = [path for path in partials if not path.exists()]
        if not partials or missing:
            raise RuntimeError(f"No Exercise 4 checkpoint files found in {EX04_PARTIAL_DIR}.")
    else:
        partials = write_exercise_04_partials(max_files=max_files, fresh=fresh_checkpoints, chunk_rows=chunk_rows)
    files = hs_bulk_files(max_files=max_files)
    product = finalize_exercise_04_from_partials(
        partials,
        source_details={
            "mode": "checkpointed_streaming",
            "hs_bulk_files_seen": len(files) if files else None,
            "partial_files": len(partials),
            "partial_dir": str(EX04_PARTIAL_DIR.relative_to(ROOT)),
            "finalize_only": finalize_only,
            "chunk_rows": int(chunk_rows),
        },
    )
    write_json(
        RESULTS / "run_manifest.json",
        {
            "created_at_utc": now_utc(),
            "mode": "exercise_04_checkpointed",
            "exercise": "4",
            "hs_bulk_files_seen": len(files) if files else None,
            "partial_files": len(partials),
            "rows_product_supplier": int(len(product)),
            "exercises_md_updated": False,
        },
    )
    return product


def make_exercise_04_figures(product: pd.DataFrame, summary: pd.DataFrame) -> None:
    import matplotlib.pyplot as plt
    import seaborn as sns

    sns.set_theme(style="whitegrid")
    if not summary.empty:
        med = summary.groupby("year", as_index=False)[
            ["weighted_mean_top_supplier_share", "weighted_mean_source_hhi", "import_value_share_products_top_supplier_ge_75"]
        ].median()
        long = med.melt(id_vars="year", var_name="measure", value_name="value")
        plt.figure(figsize=(12, 7))
        sns.lineplot(data=long, x="year", y="value", hue="measure", errorbar=None)
        plt.title("Exercise 4: Dominant Supplier Summary Over Time")
        plt.tight_layout()
        plt.savefig(EX04_FIGURES / "dominant_supplier_summary_over_time.png", dpi=200)
        plt.close()

    if not product.empty:
        latest = product[product["year"] == product["year"].max()].copy()
        plt.figure(figsize=(11, 7))
        sns.histplot(data=latest, x="top_supplier_share", bins=30)
        plt.title(f"Exercise 4: Product Top Supplier Shares ({int(product['year'].max())})")
        plt.tight_layout()
        plt.savefig(EX04_FIGURES / "latest_year_top_supplier_share_distribution.png", dpi=200)
        plt.close()


def write_exercise_04_memo(product: pd.DataFrame, summary: pd.DataFrame, source_details: dict) -> None:
    summary_table = (
        summary[
            [
                "weighted_mean_top_supplier_share",
                "weighted_mean_source_hhi",
                "median_top_supplier_share",
                "share_products_top_supplier_ge_75",
                "import_value_share_products_top_supplier_ge_75",
            ]
        ]
        .median()
        .to_frame("median_across_importer_years")
        .round(4)
        if not summary.empty
        else pd.DataFrame()
    )
    memo = f"""# Exercise 4: Dominant Supplier By Product

Generated: {now_utc()}

This memo is intentionally descriptive. `exercises.md` should only be updated after discussion.

## Coverage

- Importer-product-year rows: {len(product)}
- Importer-year rows: {len(summary)}
- Countries: {summary["country"].nunique() if not summary.empty else 0}
- Years: {int(summary["year"].min()) if not summary.empty else "n/a"}-{int(summary["year"].max()) if not summary.empty else "n/a"}
- Source details: `{json.dumps(source_details, sort_keys=True)}`

## Median Importer-Year Measures

{summary_table.to_markdown() if not summary_table.empty else "No dominant-supplier summary was produced."}

## Files

- Tables: `results/exercise_04_tables/`
- Figures: `results/exercise_04_figures/`
- Processed data: `data/processed/exercise_04_dominant_supplier_by_product.parquet`

## Discussion Prompt

Do countries import many products from one dominant supplier, or is import concentration still high even when suppliers within products are diffuse?
"""
    write_text(RESULTS / "exercise_04_dominant_suppliers.md", memo)


def write_exercise_11_reference_blocker(reason: str, details: dict | None = None) -> None:
    details = details or {}
    memo = f"""# Exercise 11: Input-Output Linkage Blocker

Generated: {now_utc()}

Exercise 11 was not run because the required official OECD input-output reference files are not available in the expected local schema.

## Reason

{reason}

## Expected Local Files

HS/product-to-IO sector bridge, one of:

{candidate_paths_text(EX11_SECTOR_BRIDGE_CANDIDATES)}

Imported input requirement table, one of:

{candidate_paths_text(EX11_INPUT_REQUIREMENTS_CANDIDATES)}

## Required Columns

- Bridge: `classification_code`, `cmd_code`, `io_sector_code`, optional `io_sector_label`.
- Input requirements: `iso3`, `year`, `output_sector_code`, `input_sector_code`, `imported_input_requirement_share`.

The bridge and input requirement files should be derived from the official OECD BTiGE conversion key and OECD ICIO tables. This runner does not invent HS-to-sector mappings.

## Details

```json
{json.dumps(details, indent=2, sort_keys=True)}
```
"""
    write_text(RESULTS / "exercise_11_reference_blocker.md", memo)


def load_exercise_11_sector_bridge() -> pd.DataFrame:
    path = first_existing_path(EX11_SECTOR_BRIDGE_CANDIDATES)
    if path is None:
        reason = "Missing Exercise 11 OECD BTiGE HS-to-sector bridge."
        write_exercise_11_reference_blocker(reason)
        raise RuntimeError(reason + f" Put a bridge file in {OECD_ICIO_RAW}.")

    raw = normalize_columns(read_reference_table(path))
    classification_col = pick_col(raw, ["classification_code", "classificationCode", "hs_version", "hsVersion", "hs_revision", "hsRevision"])
    cmd_col = pick_col(raw, ["cmd_code", "cmdCode", "hs6", "hs_code", "hsCode", "commodity_code", "commodityCode"])
    sector_col = pick_col(raw, ["io_sector_code", "icio_sector_code", "sector_code", "cpa_code", "industry_code", "input_sector_code"])
    label_col = optional_col(raw, ["io_sector_label", "icio_sector_label", "sector_label", "cpa_label", "industry_label", "sector_name"])

    out = pd.DataFrame(
        {
            "classification_code": raw[classification_col].map(normalize_hs_classification_code),
            "cmd_code": raw[cmd_col].astype(str).str.extract(r"(\d{6})", expand=False),
            "io_sector_code": raw[sector_col].astype(str).str.strip(),
            "io_sector_label": raw[label_col].astype(str).str.strip() if label_col else raw[sector_col].astype(str).str.strip(),
            "bridge_source": path.name,
        }
    )
    out = out.replace({"": np.nan}).dropna(subset=["cmd_code", "io_sector_code"]).fillna({"classification_code": "", "io_sector_label": ""})
    out["io_sector_label"] = out["io_sector_label"].replace("", np.nan).fillna(out["io_sector_code"])
    out = out.drop_duplicates()

    versioned = out[out["classification_code"] != ""]
    duplicate_versioned = versioned.duplicated(subset=["classification_code", "cmd_code"], keep=False)
    generic = out[out["classification_code"] == ""]
    duplicate_generic = generic.duplicated(subset=["cmd_code"], keep=False)
    if duplicate_versioned.any() or duplicate_generic.any():
        details = {
            "source_file": str(path.relative_to(ROOT)),
            "duplicate_versioned_examples": versioned.loc[duplicate_versioned, ["classification_code", "cmd_code"]].head(10).to_dict("records"),
            "duplicate_generic_examples": generic.loc[duplicate_generic, ["cmd_code"]].head(10).to_dict("records"),
        }
        reason = "Exercise 11 sector bridge is not one-to-one."
        write_exercise_11_reference_blocker(reason, details)
        raise RuntimeError(reason + " Review the duplicate HS-to-sector mappings.")
    if out.empty:
        reason = "Exercise 11 sector bridge loaded but contained no usable HS6 sector rows."
        write_exercise_11_reference_blocker(reason, {"source_file": str(path.relative_to(ROOT))})
        raise RuntimeError(reason)
    return out


def load_exercise_11_input_requirements() -> pd.DataFrame:
    path = first_existing_path(EX11_INPUT_REQUIREMENTS_CANDIDATES)
    if path is None:
        reason = "Missing Exercise 11 OECD ICIO imported input requirement table."
        write_exercise_11_reference_blocker(reason)
        raise RuntimeError(reason + f" Put an imported input requirement file in {OECD_ICIO_RAW}.")

    raw = normalize_columns(read_reference_table(path))
    iso_col = pick_col(raw, ["iso3", "country_iso3", "countryCode", "reporter_iso3"])
    year_col = pick_col(raw, ["year", "period", "refYear"])
    output_col = pick_col(raw, ["output_sector_code", "outputSectorCode", "output_industry_code", "using_sector_code", "industry_code"])
    input_col = pick_col(raw, ["input_sector_code", "inputSectorCode", "input_industry_code", "source_sector_code"])
    share_col = pick_col(raw, ["imported_input_requirement_share", "importRequirementShare", "input_requirement_share", "requirement_share", "coefficient", "share"])
    output_label_col = optional_col(raw, ["output_sector_label", "outputSectorLabel", "output_industry_label"])
    input_label_col = optional_col(raw, ["input_sector_label", "inputSectorLabel", "input_industry_label"])

    out = pd.DataFrame(
        {
            "iso3": raw[iso_col].astype(str).str.strip().str.upper(),
            "year": pd.to_numeric(raw[year_col], errors="coerce"),
            "output_sector_code": raw[output_col].astype(str).str.strip(),
            "input_sector_code": raw[input_col].astype(str).str.strip(),
            "imported_input_requirement_share": pd.to_numeric(raw[share_col], errors="coerce"),
            "output_sector_label": raw[output_label_col].astype(str).str.strip() if output_label_col else raw[output_col].astype(str).str.strip(),
            "input_sector_label": raw[input_label_col].astype(str).str.strip() if input_label_col else raw[input_col].astype(str).str.strip(),
            "icio_source": path.name,
        }
    )
    out = out.replace({"": np.nan}).dropna(
        subset=["iso3", "year", "output_sector_code", "input_sector_code", "imported_input_requirement_share"]
    )
    out = out[out["imported_input_requirement_share"] >= 0].copy()
    if out.empty:
        reason = "Exercise 11 ICIO requirement table loaded but contained no usable rows."
        write_exercise_11_reference_blocker(reason, {"source_file": str(path.relative_to(ROOT))})
        raise RuntimeError(reason)
    out["year"] = out["year"].astype(int)
    out["output_sector_label"] = out["output_sector_label"].fillna(out["output_sector_code"])
    out["input_sector_label"] = out["input_sector_label"].fillna(out["input_sector_code"])
    return out.groupby(
        ["iso3", "year", "output_sector_code", "input_sector_code", "output_sector_label", "input_sector_label", "icio_source"],
        as_index=False,
    )["imported_input_requirement_share"].sum()


def merge_exercise_11_sector_bridge(trade: pd.DataFrame, bridge: pd.DataFrame) -> pd.DataFrame:
    base = trade.copy()
    base["classification_code"] = base["classification_code"].map(normalize_hs_classification_code)
    base["cmd_code"] = base["cmd_code"].astype(str).str.extract(r"(\d{6})", expand=False).fillna("")
    base["_exercise_11_row"] = np.arange(len(base))

    bridge_cols = ["classification_code", "cmd_code", "io_sector_code", "io_sector_label", "bridge_source"]
    versioned = bridge[bridge["classification_code"] != ""][bridge_cols]
    exact = base.merge(versioned, on=["classification_code", "cmd_code"], how="left")
    exact["io_mapping_status"] = np.where(exact["io_sector_code"].notna(), "mapped_version_exact", "unmapped")

    matched = exact[exact["io_sector_code"].notna()].copy()
    missing = exact[exact["io_sector_code"].isna()][base.columns].copy()
    generic = bridge[bridge["classification_code"] == ""][["cmd_code", "io_sector_code", "io_sector_label", "bridge_source"]]
    if not missing.empty and not generic.empty:
        fallback = missing.merge(generic, on="cmd_code", how="left")
        fallback["io_mapping_status"] = np.where(fallback["io_sector_code"].notna(), "mapped_hs_code_only", "unmapped")
        out = pd.concat([matched, fallback], ignore_index=True, sort=False)
    else:
        out = exact

    out = out.sort_values("_exercise_11_row").drop(columns=["_exercise_11_row"], errors="ignore")
    out["io_mapping_status"] = out["io_mapping_status"].fillna("unmapped")
    out["io_sector_label"] = out["io_sector_label"].fillna(out["io_sector_code"])
    return out


def exercise_11_aggregates_for_leaf(leaf: pd.DataFrame, bec_mapping: pd.DataFrame, sector_bridge: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if leaf.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    require_leaf_classification_code(leaf)
    base = leaf.copy()
    base["classification_code"] = base["classification_code"].map(normalize_hs_classification_code)
    base["cmd_code"] = base["cmd_code"].astype(str).str.extract(r"(\d{6})", expand=False).fillna("")
    base = drop_excluded_hs6(base)
    if base.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    mapping_cols = [
        "classification_code",
        "cmd_code",
        "exercise_03_bin",
        "mapping_status",
    ]
    imports = base[base["flow"] == "Imports"].copy()
    import_cells = pd.DataFrame()
    import_coverage = pd.DataFrame()
    if not imports.empty:
        imports = imports.merge(bec_mapping[[col for col in mapping_cols if col in bec_mapping.columns]], on=["classification_code", "cmd_code"], how="left")
        imports = merge_exercise_11_sector_bridge(imports, sector_bridge)
        imports["exercise_03_bin"] = imports["exercise_03_bin"].fillna("unmapped_or_ambiguous").replace("", "unmapped_or_ambiguous")
        imports["mapping_status"] = imports["mapping_status"].fillna("unmapped").replace("", "unmapped")

        mapped_imports = imports[imports["io_sector_code"].notna()].copy()
        if not mapped_imports.empty:
            import_cells = mapped_imports.groupby(
                ["reporter_code", "year", "io_sector_code", "io_sector_label", "exercise_03_bin", "cmd_code", "partner_code"],
                as_index=False,
            )["trade_value"].sum()

        import_coverage = imports.groupby(
            ["flow", "reporter_code", "year", "exercise_03_bin", "mapping_status", "io_mapping_status", "cmd_code"],
            as_index=False,
        )["trade_value"].sum()
        import_coverage = import_coverage.rename(columns={"mapping_status": "bec_mapping_status"})

    exports = base[base["flow"] == "Exports"].copy()
    export_sectors = pd.DataFrame()
    export_coverage = pd.DataFrame()
    if not exports.empty:
        exports = merge_exercise_11_sector_bridge(exports, sector_bridge)
        mapped_exports = exports[exports["io_sector_code"].notna()].copy()
        if not mapped_exports.empty:
            export_sectors = mapped_exports.groupby(
                ["reporter_code", "year", "io_sector_code", "io_sector_label"],
                as_index=False,
            )["trade_value"].sum()
        export_coverage = exports.assign(exercise_03_bin="not_applicable_export", bec_mapping_status="not_applicable").groupby(
            ["flow", "reporter_code", "year", "exercise_03_bin", "bec_mapping_status", "io_mapping_status", "cmd_code"],
            as_index=False,
        )["trade_value"].sum()

    coverage = pd.concat([import_coverage, export_coverage], ignore_index=True) if not import_coverage.empty or not export_coverage.empty else pd.DataFrame()
    return import_cells, export_sectors, coverage


def exercise_11_partial_paths(raw_path: Path) -> tuple[Path, Path, Path]:
    name = checkpoint_name_for_raw(raw_path)
    return EX11_IMPORT_PARTIAL_DIR / name, EX11_EXPORT_PARTIAL_DIR / name, EX11_COVERAGE_PARTIAL_DIR / name


def aggregate_exercise_11_for_raw(
    raw_path: Path,
    bec_mapping: pd.DataFrame,
    sector_bridge: pd.DataFrame,
    chunk_rows: int = DEFAULT_CHUNK_ROWS,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    import_group_cols = ["reporter_code", "year", "io_sector_code", "io_sector_label", "exercise_03_bin", "cmd_code", "partner_code"]
    export_group_cols = ["reporter_code", "year", "io_sector_code", "io_sector_label"]
    coverage_group_cols = ["flow", "reporter_code", "year", "exercise_03_bin", "bec_mapping_status", "io_mapping_status", "cmd_code"]
    import_cells: pd.DataFrame | None = None
    export_sectors: pd.DataFrame | None = None
    coverage_products: pd.DataFrame | None = None

    for leaf in iter_leaf_trade_chunks(raw_path, chunk_rows=chunk_rows):
        chunk_imports, chunk_exports, chunk_coverage = exercise_11_aggregates_for_leaf(leaf, bec_mapping, sector_bridge)
        import_cells = add_group_sum_frame(import_cells, chunk_imports, import_group_cols)
        export_sectors = add_group_sum_frame(export_sectors, chunk_exports, export_group_cols)
        coverage_products = add_group_sum_frame(coverage_products, chunk_coverage, coverage_group_cols)
        del leaf

    return (
        finish_group_sum_frame(import_cells, import_group_cols),
        finish_group_sum_frame(export_sectors, export_group_cols),
        finish_group_sum_frame(coverage_products, coverage_group_cols),
    )


def write_exercise_11_partials(max_files: int | None = None, fresh: bool = False, chunk_rows: int = DEFAULT_CHUNK_ROWS) -> tuple[list[Path], list[Path], list[Path]]:
    if fresh and EX11_PARTIAL_DIR.exists():
        shutil.rmtree(EX11_PARTIAL_DIR)
    for path in [EX11_IMPORT_PARTIAL_DIR, EX11_EXPORT_PARTIAL_DIR, EX11_COVERAGE_PARTIAL_DIR]:
        path.mkdir(parents=True, exist_ok=True)

    bec_mapping = load_approved_bec5_mapping()
    sector_bridge = load_exercise_11_sector_bridge()
    files = hs_bulk_files(max_files=max_files)
    if not files:
        raise FileNotFoundError(f"No HS Comtrade bulk files found in {COMTRADE_BULK}")

    import_partials = []
    export_partials = []
    coverage_partials = []
    manifest_rows = []
    for idx, path in enumerate(files, start=1):
        import_partial, export_partial, coverage_partial = exercise_11_partial_paths(path)
        import_partials.append(import_partial)
        export_partials.append(export_partial)
        coverage_partials.append(coverage_partial)
        if import_partial.exists() and export_partial.exists() and coverage_partial.exists():
            print(f"[{idx}/{len(files)}] skip existing Exercise 11 checkpoints for {path.name}", flush=True)
            manifest_rows.append({"raw_file": path.name, "status": "already_exists"})
            continue

        print(f"[{idx}/{len(files)}] Exercise 11 input-output aggregates from {path.name}", flush=True)
        import_cells, export_sectors, coverage = aggregate_exercise_11_for_raw(
            path,
            bec_mapping,
            sector_bridge,
            chunk_rows=chunk_rows,
        )
        import_cells.to_parquet(import_partial, index=False)
        export_sectors.to_parquet(export_partial, index=False)
        coverage.to_parquet(coverage_partial, index=False)
        manifest_rows.append(
            {
                "raw_file": path.name,
                "status": "written",
                "import_rows": int(len(import_cells)),
                "export_rows": int(len(export_sectors)),
                "coverage_rows": int(len(coverage)),
            }
        )
        write_json(
            RESULTS / "run_manifest_exercise_11_checkpoints.json",
            {
                "created_at_utc": now_utc(),
                "mode": "exercise_11_checkpoint_partials",
                "raw_files_seen": len(files),
                "raw_files_attempted": idx,
                "partial_files_present": {
                    "import_cells": len(list(EX11_IMPORT_PARTIAL_DIR.glob("*.parquet"))),
                    "export_sectors": len(list(EX11_EXPORT_PARTIAL_DIR.glob("*.parquet"))),
                    "mapping_coverage": len(list(EX11_COVERAGE_PARTIAL_DIR.glob("*.parquet"))),
                },
                "latest_raw_file": path.name,
                "manifest_tail": manifest_rows[-25:],
                "approved_bec_mapping": str(EX03_BEC_MAPPING_APPROVED.relative_to(ROOT)),
                "exercises_md_updated": False,
            },
        )
    return import_partials, export_partials, coverage_partials


def compute_exercise_11_import_concentration(import_cells: pd.DataFrame) -> pd.DataFrame:
    if import_cells.empty:
        return pd.DataFrame()
    rows = []
    for key, group in import_cells.groupby(["reporter_code", "year", "io_sector_code", "io_sector_label", "exercise_03_bin"], sort=True):
        reporter_code, year, sector_code, sector_label, import_bin = key
        total = float(group["trade_value"].sum())
        if total <= 0:
            continue
        product_values = group.groupby("cmd_code", as_index=False)["trade_value"].sum()
        supplier_values = group.groupby("partner_code", as_index=False)["trade_value"].sum()
        cell_values = group.groupby(["cmd_code", "partner_code"], as_index=False)["trade_value"].sum()
        supplier_shares = supplier_values["trade_value"].to_numpy(dtype=float) / total
        rows.append(
            {
                "reporter_code": int(reporter_code),
                "year": int(year),
                "io_sector_code": sector_code,
                "io_sector_label": sector_label,
                "import_bin": import_bin,
                "main_specification": import_bin == "intermediates",
                "total_imports": total,
                "active_products": int(len(product_values)),
                "active_suppliers": int(len(supplier_values)),
                "active_product_supplier_cells": int(len(cell_values)),
                "product_gini": gini(product_values["trade_value"]),
                "top_1_product_share": top_share(product_values["trade_value"], n=1),
                "top_5_product_share": top_share(product_values["trade_value"], n=5),
                "top_10_product_share": top_share(product_values["trade_value"], n=10),
                "top_supplier_share": top_share(supplier_values["trade_value"], n=1),
                "source_hhi": float(np.square(supplier_shares).sum()) if supplier_shares.size else np.nan,
                "product_supplier_cell_hhi": float(np.square(cell_values["trade_value"].to_numpy(dtype=float) / total).sum()),
            }
        )
    out = add_country_metadata(pd.DataFrame(rows)) if rows else pd.DataFrame()
    return out


def compute_exercise_11_export_sectors(export_sectors: pd.DataFrame) -> pd.DataFrame:
    if export_sectors.empty:
        return pd.DataFrame()
    out = export_sectors.groupby(["reporter_code", "year", "io_sector_code", "io_sector_label"], as_index=False)["trade_value"].sum()
    out = out.rename(columns={"trade_value": "total_sector_exports"})
    totals = out.groupby(["reporter_code", "year"], as_index=False)["total_sector_exports"].sum().rename(columns={"total_sector_exports": "total_exports"})
    out = out.merge(totals, on=["reporter_code", "year"], how="left")
    out["sector_export_share"] = out["total_sector_exports"] / out["total_exports"].replace(0, np.nan)
    out = out.sort_values(["reporter_code", "year", "total_sector_exports", "io_sector_code"], ascending=[True, True, False, True])
    out["export_rank"] = out.groupby(["reporter_code", "year"]).cumcount() + 1
    out["is_top_10_export_sector"] = out["export_rank"] <= 10
    return add_country_metadata(out)


def compute_exercise_11_input_exposure(export_ranked: pd.DataFrame, import_concentration: pd.DataFrame, input_requirements: pd.DataFrame) -> pd.DataFrame:
    if export_ranked.empty:
        return pd.DataFrame()
    exports = export_ranked.copy()
    requirements = input_requirements.copy()
    linked = exports.merge(
        requirements,
        left_on=["iso3", "year", "io_sector_code"],
        right_on=["iso3", "year", "output_sector_code"],
        how="left",
    )
    linked["imported_input_requirement_share"] = pd.to_numeric(linked["imported_input_requirement_share"], errors="coerce").fillna(0)

    main_imports = import_concentration[import_concentration["import_bin"] == "intermediates"].copy()
    main_imports = main_imports.rename(
        columns={
            "io_sector_code": "input_sector_code",
            "io_sector_label": "matched_input_sector_label",
            "product_gini": "input_product_gini",
            "top_supplier_share": "input_top_supplier_share",
            "source_hhi": "input_source_hhi",
            "total_imports": "matched_input_imports",
        }
    )
    keep_import_cols = [
        "reporter_code",
        "year",
        "input_sector_code",
        "matched_input_sector_label",
        "input_product_gini",
        "input_top_supplier_share",
        "input_source_hhi",
        "matched_input_imports",
    ]
    linked = linked.merge(main_imports[keep_import_cols], on=["reporter_code", "year", "input_sector_code"], how="left")
    linked["matched_requirement_share"] = np.where(linked["input_product_gini"].notna(), linked["imported_input_requirement_share"], 0.0)
    for metric in ["input_product_gini", "input_top_supplier_share", "input_source_hhi"]:
        linked[f"{metric}_weighted"] = linked["imported_input_requirement_share"] * linked[metric].fillna(0)

    group_cols = [
        "reporter_code",
        "country",
        "iso3",
        "year",
        "io_sector_code",
        "io_sector_label",
        "total_sector_exports",
        "total_exports",
        "sector_export_share",
        "export_rank",
        "is_top_10_export_sector",
    ]
    exposure = linked.groupby(group_cols, as_index=False).agg(
        imported_input_requirement_share=("imported_input_requirement_share", "sum"),
        matched_input_requirement_share=("matched_requirement_share", "sum"),
        input_sectors_required=("input_sector_code", "nunique"),
        matched_input_sectors=("input_product_gini", lambda s: int(s.notna().sum())),
        input_product_gini_weighted=("input_product_gini_weighted", "sum"),
        input_top_supplier_share_weighted=("input_top_supplier_share_weighted", "sum"),
        input_source_hhi_weighted=("input_source_hhi_weighted", "sum"),
    )
    denom = exposure["matched_input_requirement_share"].replace(0, np.nan)
    exposure["input_exposure_product_gini"] = exposure["input_product_gini_weighted"] / denom
    exposure["input_exposure_top_supplier_share"] = exposure["input_top_supplier_share_weighted"] / denom
    exposure["input_exposure_source_hhi"] = exposure["input_source_hhi_weighted"] / denom
    return exposure.drop(columns=["input_product_gini_weighted", "input_top_supplier_share_weighted", "input_source_hhi_weighted"])


def summarize_exercise_11_country_year(exposure: pd.DataFrame) -> pd.DataFrame:
    if exposure.empty:
        return pd.DataFrame()
    rows = []
    for key, group in exposure.groupby(["reporter_code", "country", "iso3", "year"], sort=True):
        reporter_code, country, iso3, year = key
        top = group[group["is_top_10_export_sector"]].copy()
        if top.empty:
            continue
        rows.append(
            {
                "reporter_code": int(reporter_code),
                "country": country,
                "iso3": iso3,
                "year": int(year),
                "top_export_sectors": int(len(top)),
                "top_export_value_share": float(top["sector_export_share"].sum()),
                "weighted_top_sector_input_product_gini": weighted_mean(top["input_exposure_product_gini"], top["total_sector_exports"]),
                "weighted_top_sector_top_supplier_share": weighted_mean(top["input_exposure_top_supplier_share"], top["total_sector_exports"]),
                "weighted_top_sector_source_hhi": weighted_mean(top["input_exposure_source_hhi"], top["total_sector_exports"]),
                "median_top_sector_matched_requirement_share": float(top["matched_input_requirement_share"].median()),
                "total_exports": float(group["total_exports"].max()),
            }
        )
    return pd.DataFrame(rows)


def summarize_exercise_11_mapping_coverage(coverage_products: pd.DataFrame) -> pd.DataFrame:
    if coverage_products.empty:
        return pd.DataFrame()
    coverage = coverage_products.groupby(
        ["flow", "reporter_code", "year", "exercise_03_bin", "bec_mapping_status", "io_mapping_status"],
        as_index=False,
    ).agg(trade_value=("trade_value", "sum"), active_products=("cmd_code", "nunique"))
    totals = coverage.groupby(["flow", "reporter_code", "year"], as_index=False)["trade_value"].sum().rename(columns={"trade_value": "total_flow_value"})
    coverage = coverage.merge(totals, on=["flow", "reporter_code", "year"], how="left")
    coverage["trade_value_share"] = coverage["trade_value"] / coverage["total_flow_value"].replace(0, np.nan)
    return add_country_metadata(coverage)


def finalize_exercise_11_from_partials(
    import_partials: list[Path],
    export_partials: list[Path],
    coverage_partials: list[Path],
    source_details: dict | None = None,
) -> pd.DataFrame:
    input_requirements = load_exercise_11_input_requirements()
    import_concentration_frames: list[pd.DataFrame] = []
    for idx, partial in enumerate(import_partials, start=1):
        if not partial.exists():
            continue
        import_cells = pd.read_parquet(partial)
        if import_cells.empty:
            continue
        import_concentration = compute_exercise_11_import_concentration(import_cells)
        if not import_concentration.empty:
            import_concentration_frames.append(import_concentration)
        if idx % 100 == 0:
            print(f"finalized Exercise 11 import partial {idx}/{len(import_partials)}", flush=True)
        del import_cells
    export_sectors = combine_partial_group_sums(export_partials, ["reporter_code", "year", "io_sector_code", "io_sector_label"])
    coverage_frames: list[pd.DataFrame] = []
    for partial in coverage_partials:
        if not partial.exists():
            continue
        coverage_products = pd.read_parquet(partial)
        if coverage_products.empty:
            continue
        coverage = summarize_exercise_11_mapping_coverage(coverage_products)
        if not coverage.empty:
            coverage_frames.append(coverage)
    if not import_concentration_frames or export_sectors.empty:
        raise RuntimeError("Exercise 11 checkpoints did not contain both import input rows and export sector rows.")

    import_concentration = pd.concat(import_concentration_frames, ignore_index=True)
    export_ranked = compute_exercise_11_export_sectors(export_sectors)
    exposure = compute_exercise_11_input_exposure(export_ranked, import_concentration, input_requirements)
    summary = summarize_exercise_11_country_year(exposure)

    import_concentration.to_parquet(sample_processed_path("exercise_11_imported_input_concentration.parquet"), index=False)
    import_concentration.to_csv(EX11_TABLES / "imported_input_concentration_by_sector.csv", index=False)
    exposure.to_parquet(sample_processed_path("exercise_11_top_export_input_exposure.parquet"), index=False)
    exposure.to_csv(EX11_TABLES / "top_export_sector_input_exposure.csv", index=False)
    summary.to_csv(EX11_TABLES / "country_year_input_output_linkage_summary.csv", index=False)

    coverage = pd.concat(coverage_frames, ignore_index=True) if coverage_frames else pd.DataFrame()
    coverage.to_csv(EX11_TABLES / "exercise_11_mapping_coverage.csv", index=False)

    make_exercise_11_figures(import_concentration, exposure, summary)
    write_exercise_11_memo(import_concentration, exposure, summary, coverage, source_details or {})
    return exposure


def run_exercise_11(leaf: pd.DataFrame) -> pd.DataFrame:
    bec_mapping = load_approved_bec5_mapping()
    sector_bridge = load_exercise_11_sector_bridge()
    import_cells, export_sectors, coverage = exercise_11_aggregates_for_leaf(leaf, bec_mapping, sector_bridge)
    tmp_dir = EX11_PARTIAL_DIR / "_in_memory"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_import = tmp_dir / "import_cells.parquet"
    tmp_export = tmp_dir / "export_sectors.parquet"
    tmp_coverage = tmp_dir / "coverage.parquet"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    import_cells.to_parquet(tmp_import, index=False)
    export_sectors.to_parquet(tmp_export, index=False)
    coverage.to_parquet(tmp_coverage, index=False)
    return finalize_exercise_11_from_partials(
        [tmp_import],
        [tmp_export],
        [tmp_coverage],
        source_details={"mode": "in_memory_leaf", "approved_bec_mapping": str(EX03_BEC_MAPPING_APPROVED.relative_to(ROOT))},
    )


def run_exercise_11_streaming(
    max_files: int | None = None,
    fresh_checkpoints: bool = False,
    finalize_only: bool = False,
    chunk_rows: int = DEFAULT_CHUNK_ROWS,
) -> pd.DataFrame:
    if finalize_only:
        load_approved_bec5_mapping()
        files = hs_bulk_files(max_files=max_files)
        if files:
            partial_sets = [exercise_11_partial_paths(path) for path in files]
            import_partials = [paths[0] for paths in partial_sets]
            export_partials = [paths[1] for paths in partial_sets]
            coverage_partials = [paths[2] for paths in partial_sets]
        else:
            import_partials = sorted(EX11_IMPORT_PARTIAL_DIR.glob("*.parquet"))
            export_partials = sorted(EX11_EXPORT_PARTIAL_DIR.glob("*.parquet"))
            coverage_partials = sorted(EX11_COVERAGE_PARTIAL_DIR.glob("*.parquet"))
        missing = [path for path in [*import_partials, *export_partials, *coverage_partials] if not path.exists()]
        if not import_partials or not export_partials or not coverage_partials or missing:
            raise RuntimeError(f"No complete Exercise 11 checkpoint set found in {EX11_PARTIAL_DIR}.")
    else:
        import_partials, export_partials, coverage_partials = write_exercise_11_partials(
            max_files=max_files,
            fresh=fresh_checkpoints,
            chunk_rows=chunk_rows,
        )

    exposure = finalize_exercise_11_from_partials(
        import_partials,
        export_partials,
        coverage_partials,
        source_details={
            "mode": "checkpointed_streaming",
            "partial_dir": str(EX11_PARTIAL_DIR.relative_to(ROOT)),
            "partial_files": {
                "import_cells": len(import_partials),
                "export_sectors": len(export_partials),
                "mapping_coverage": len(coverage_partials),
            },
            "finalize_only": finalize_only,
            "chunk_rows": int(chunk_rows),
            "approved_bec_mapping": str(EX03_BEC_MAPPING_APPROVED.relative_to(ROOT)),
        },
    )
    write_json(
        RESULTS / "run_manifest.json",
        {
            "created_at_utc": now_utc(),
            "mode": "exercise_11_checkpointed",
            "exercise": "11",
            "partial_files": {
                "import_cells": len(import_partials),
                "export_sectors": len(export_partials),
                "mapping_coverage": len(coverage_partials),
            },
            "chunk_rows": int(chunk_rows),
            "rows_top_export_input_exposure": int(len(exposure)),
            "exercises_md_updated": False,
        },
    )
    return exposure


def make_exercise_11_figures(import_concentration: pd.DataFrame, exposure: pd.DataFrame, summary: pd.DataFrame) -> None:
    import matplotlib.pyplot as plt
    import seaborn as sns

    sns.set_theme(style="whitegrid")
    if not summary.empty:
        india = summary[summary["iso3"] == "IND"].copy()
        if not india.empty:
            long = india.melt(
                id_vars=["year"],
                value_vars=["weighted_top_sector_input_product_gini", "weighted_top_sector_top_supplier_share"],
                var_name="measure",
                value_name="value",
            )
            long = long[np.isfinite(pd.to_numeric(long["value"], errors="coerce"))].copy()
            if not long.empty:
                plt.figure(figsize=(11, 6))
                sns.lineplot(data=long, x="year", y="value", hue="measure", errorbar=None)
                plt.title("Exercise 11: India Top Export Sector Imported-Input Exposure")
                plt.tight_layout()
                plt.savefig(EX11_FIGURES / "india_top_export_input_exposure_over_time.png", dpi=200)
                plt.close()

        latest_year = int(summary["year"].max())
        latest = summary[summary["year"] == latest_year].copy()
        if not latest.empty:
            latest["country_group"] = np.where(latest["iso3"] == "IND", "India", "Comparator")
            latest["weighted_top_sector_input_product_gini"] = pd.to_numeric(
                latest["weighted_top_sector_input_product_gini"], errors="coerce"
            )
            latest = latest[np.isfinite(latest["weighted_top_sector_input_product_gini"])].copy()
            if not latest.empty:
                group_order = latest["country_group"].drop_duplicates().tolist()
                plt.figure(figsize=(9, 6))
                sns.boxplot(data=latest, x="country_group", y="weighted_top_sector_input_product_gini", order=group_order)
                sns.stripplot(
                    data=latest,
                    x="country_group",
                    y="weighted_top_sector_input_product_gini",
                    order=group_order,
                    color="black",
                    alpha=0.5,
                )
                plt.title(f"Exercise 11: India Versus Comparators ({latest_year})")
                plt.tight_layout()
                plt.savefig(EX11_FIGURES / "india_vs_comparators_input_exposure.png", dpi=200)
                plt.close()

    if not exposure.empty:
        india_top = exposure[(exposure["iso3"] == "IND") & (exposure["is_top_10_export_sector"])].copy()
        if not india_top.empty:
            latest_year = int(india_top["year"].max())
            latest = india_top[india_top["year"] == latest_year].sort_values("input_exposure_product_gini", ascending=False).head(10)
            latest["input_exposure_product_gini"] = pd.to_numeric(latest["input_exposure_product_gini"], errors="coerce")
            latest = latest[np.isfinite(latest["input_exposure_product_gini"])].copy()
            if not latest.empty:
                plt.figure(figsize=(12, 7))
                sns.barplot(data=latest, x="input_exposure_product_gini", y="io_sector_label")
                plt.title(f"Exercise 11: India Top Export Sectors By Imported-Input Exposure ({latest_year})")
                plt.tight_layout()
                plt.savefig(EX11_FIGURES / "india_top_export_sectors_by_input_exposure.png", dpi=200)
                plt.close()


def write_exercise_11_memo(
    import_concentration: pd.DataFrame,
    exposure: pd.DataFrame,
    summary: pd.DataFrame,
    coverage: pd.DataFrame,
    source_details: dict,
) -> None:
    import_summary = (
        import_concentration.groupby("import_bin", as_index=False)
        .agg(
            rows=("product_gini", "size"),
            median_product_gini=("product_gini", "median"),
            median_top_supplier_share=("top_supplier_share", "median"),
            median_source_hhi=("source_hhi", "median"),
        )
        .round(4)
        if not import_concentration.empty
        else pd.DataFrame()
    )
    top_summary = (
        summary[
            [
                "weighted_top_sector_input_product_gini",
                "weighted_top_sector_top_supplier_share",
                "weighted_top_sector_source_hhi",
                "median_top_sector_matched_requirement_share",
            ]
        ]
        .median()
        .to_frame("median_country_year")
        .round(4)
        if not summary.empty
        else pd.DataFrame()
    )
    coverage_summary = (
        coverage.groupby(["flow", "io_mapping_status"], as_index=False)["trade_value_share"].median().round(4)
        if not coverage.empty
        else pd.DataFrame()
    )
    memo = f"""# Exercise 11: Input-Output Linkages

Generated: {now_utc()}

This memo is intentionally descriptive. `exercises.md` should only be updated after discussion.

## Coverage

- Imported input concentration rows: {len(import_concentration)}
- Top export sector exposure rows: {len(exposure)}
- Country-year summary rows: {len(summary)}
- Countries: {summary["country"].nunique() if not summary.empty else 0}
- Years: {int(summary["year"].min()) if not summary.empty else "n/a"}-{int(summary["year"].max()) if not summary.empty else "n/a"}
- Source details: `{json.dumps(source_details, sort_keys=True)}`

## Import Concentration By BEC Bin

{import_summary.to_markdown(index=False) if not import_summary.empty else "No imported-input concentration summary was produced."}

## Top Export Sector Imported-Input Exposure

{top_summary.to_markdown() if not top_summary.empty else "No top-export exposure summary was produced."}

## Median Mapping Coverage

{coverage_summary.to_markdown(index=False) if not coverage_summary.empty else "No mapping coverage summary was produced."}

## Files

- Tables: `results/exercise_11_tables/`
- Figures: `results/exercise_11_figures/`
- Processed data: `data/processed/exercise_11_imported_input_concentration.parquet`, `data/processed/exercise_11_top_export_input_exposure.parquet`

## Discussion Prompt

Do concentrated intermediate imports map to the sectors where countries, especially India, have top export exposure?
"""
    write_text(RESULTS / "exercise_11_input_output_linkages.md", memo)


def run_exercises_streaming(
    simulations: int,
    seed: int,
    exact_max_items: int,
    grid_size: int,
    max_simulated_items: int,
    max_files: int | None = None,
) -> None:
    files = hs_bulk_files(max_files=max_files)
    if not files:
        raise FileNotFoundError(f"No HS Comtrade bulk files found in {COMTRADE_BULK}")
    bec_mapping = load_approved_bec5_mapping()

    ex01_products = []
    ex01_partners = []
    ex01_cells = []
    ex02_panels = []
    ex03_product_partials = []
    ex03_coverage_partials = []
    ex04_supplier_partials = []
    ex06_outputs = []
    ex06_removed = []
    ex10_actual_frames = []
    ex12_values_by_dimension = {"product": [], "partner": [], "product_partner_cell": []}
    ex12_product_partner_frames = []
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
        ex10_actual_frames.append(exercise_10_actual_rows_for_leaf(leaf))

        ex02_panel = exercise_02_panel_rows_for_leaf(leaf)
        if not ex02_panel.empty:
            ex02_panels.append(ex02_panel)

        ex03_product_partial, ex03_coverage_partial, _, _ = write_exercise_03_partial_for_leaf(path, leaf, bec_mapping)
        ex03_product_partials.append(ex03_product_partial)
        ex03_coverage_partials.append(ex03_coverage_partial)

        ex04_supplier_partial, _ = write_exercise_04_partial_for_leaf(path, leaf)
        ex04_supplier_partials.append(ex04_supplier_partial)

        outputs, removed = compute_exercise_06_outputs_for_leaf(leaf, panel)
        ex06_outputs.extend(outputs)
        ex06_removed.extend(removed)

        ex12_frames, ex12_product_partner = exercise_12_export_aggregates_for_leaf(leaf)
        for dimension, frame in ex12_frames.items():
            ex12_values_by_dimension[dimension].append(frame)
        if not ex12_product_partner.empty:
            ex12_product_partner_frames.append(ex12_product_partner)

    if not ex01_products:
        raise RuntimeError("No exercise rows were produced from HS bulk files.")

    product = pd.concat(ex01_products, ignore_index=True)
    partner = pd.concat(ex01_partners, ignore_index=True)
    cell = pd.concat(ex01_cells, ignore_index=True)
    product.to_csv(EX01_TABLES / "product_concentration_all_years.csv", index=False)
    partner.to_csv(EX01_TABLES / "partner_concentration_all_years.csv", index=False)
    cell.to_csv(EX01_TABLES / "product_partner_cell_concentration_all_years.csv", index=False)
    concentration = merge_metric_tables(product, partner, cell)
    concentration.to_parquet(sample_processed_path("concentration_all_years.parquet"), index=False)
    concentration.to_csv(EX01_TABLES / "concentration_all_years.csv", index=False)
    make_exercise_01_figures(concentration)
    write_exercise_01_memo(concentration)

    exclusions = pd.concat(ex06_outputs, ignore_index=True)
    exclusions.to_csv(EX06_TABLES / "concentration_exclusions_all_years.csv", index=False)
    parquet_error = None
    try:
        exclusions.to_parquet(sample_processed_path("concentration_exclusions_all_years.parquet"), index=False)
    except Exception as exc:
        parquet_error = f"{type(exc).__name__}: {exc}"
        sample_processed_path("concentration_exclusions_all_years.parquet.error.txt").write_text(
            parquet_error + "\n",
            encoding="utf-8",
        )
    if ex06_removed:
        removed = pd.concat(ex06_removed, ignore_index=True)
        removed.to_csv(EX06_TABLES / "trade_share_removed_by_category.csv", index=False)
    make_exercise_06_figures(exclusions)
    write_exercise_06_memo(exclusions)

    ex02_growth = run_exercise_02_from_panel(
        pd.concat(ex02_panels, ignore_index=True),
        source_details={"mode": "streaming_all_exercises", "hs_bulk_files_processed": len(files)},
    )

    ex03_concentration = finalize_exercise_03_from_partials(
        ex03_product_partials,
        ex03_coverage_partials,
        source_details={
            "mode": "streaming_all_exercises_checkpointed",
            "hs_bulk_files_processed": len(files),
            "partial_dir": str(EX03_PARTIAL_DIR.relative_to(ROOT)),
        },
    )

    ex04_product = finalize_exercise_04_from_partials(
        ex04_supplier_partials,
        source_details={
            "mode": "streaming_all_exercises_checkpointed",
            "hs_bulk_files_processed": len(files),
            "partial_dir": str(EX04_PARTIAL_DIR.relative_to(ROOT)),
        },
    )

    ex10_actual = pd.concat(ex10_actual_frames, ignore_index=True)
    random_benchmark = run_exercise_10_from_actual_rows(
        ex10_actual,
        simulations=simulations,
        seed=seed,
        exact_max_items=exact_max_items,
        grid_size=grid_size,
        max_simulated_items=max_simulated_items,
        source_details={"mode": "streaming_all_exercises", "hs_bulk_files_processed": len(files)},
    )

    ex12_values = {
        dimension: pd.concat(frames, ignore_index=True)
        for dimension, frames in ex12_values_by_dimension.items()
        if frames
    }
    ex12_product_partner = (
        pd.concat(ex12_product_partner_frames, ignore_index=True) if ex12_product_partner_frames else pd.DataFrame()
    )
    ex12_decomposition = run_exercise_12_from_aggregates(
        ex12_values,
        ex12_product_partner,
        source_details={"mode": "streaming_all_exercises", "hs_bulk_files_processed": len(files)},
    )
    ex11_exposure = run_exercise_11_streaming(max_files=max_files)

    write_json(
        RESULTS / "run_manifest.json",
        {
            "created_at_utc": now_utc(),
            "mode": "streaming",
            "hs_bulk_files_processed": len(files),
            "rows_concentration": int(len(concentration)),
            "rows_ex02_growth": int(len(ex02_growth)),
            "rows_ex03_concentration": int(len(ex03_concentration)),
            "rows_ex04_product_supplier": int(len(ex04_product)),
            "rows_exclusions": int(len(exclusions)),
            "rows_ex10_actual": int(len(ex10_actual)),
            "rows_random_benchmark": int(len(random_benchmark)),
            "rows_ex11_top_export_input_exposure": int(len(ex11_exposure)),
            "rows_ex12_decomposition": int(len(ex12_decomposition)),
            "simulations": simulations,
            "seed": seed,
            "benchmark_exact_max_items": exact_max_items,
            "benchmark_grid_size": grid_size,
            "benchmark_max_simulated_items": max_simulated_items,
            "exercises_md_updated": False,
        },
    )


def run_exercise_01_streaming() -> pd.DataFrame:
    files = hs_bulk_files()
    if not files:
        raise FileNotFoundError(f"No HS Comtrade bulk files found in {COMTRADE_BULK}")

    ex01_products = []
    ex01_partners = []
    ex01_cells = []

    for idx, path in enumerate(files, start=1):
        print(f"[{idx}/{len(files)}] Processing Exercise 1: {path.name}", flush=True)
        raw = read_comtrade_file(path)
        leaf = extract_leaf_trade(raw)
        if leaf.empty:
            continue
        product, partner, cell = compute_concentration(leaf, "baseline")
        ex01_products.append(product)
        ex01_partners.append(partner)
        ex01_cells.append(cell)

    if not ex01_products:
        raise RuntimeError("No Exercise 1 rows were produced from HS bulk files.")

    product = pd.concat(ex01_products, ignore_index=True)
    partner = pd.concat(ex01_partners, ignore_index=True)
    cell = pd.concat(ex01_cells, ignore_index=True)
    product.to_csv(EX01_TABLES / "product_concentration_all_years.csv", index=False)
    partner.to_csv(EX01_TABLES / "partner_concentration_all_years.csv", index=False)
    cell.to_csv(EX01_TABLES / "product_partner_cell_concentration_all_years.csv", index=False)
    concentration = merge_metric_tables(product, partner, cell)
    concentration.to_parquet(sample_processed_path("concentration_all_years.parquet"), index=False)
    concentration.to_csv(EX01_TABLES / "concentration_all_years.csv", index=False)
    make_exercise_01_figures(concentration)
    write_exercise_01_memo(concentration)
    write_json(
        RESULTS / "run_manifest.json",
        {
            "created_at_utc": now_utc(),
            "mode": "exercise_01_streaming",
            "exercise": "1",
            "hs_bulk_files_processed": len(files),
            "rows_concentration": int(len(concentration)),
            "exercises_md_updated": False,
        },
    )
    return concentration


def run_exercise_06_streaming() -> pd.DataFrame:
    files = hs_bulk_files()
    if not files:
        raise FileNotFoundError(f"No HS Comtrade bulk files found in {COMTRADE_BULK}")

    ex06_outputs = []
    ex06_removed = []
    panel = save_country_panel()
    files_with_rows = 0

    for idx, path in enumerate(files, start=1):
        print(f"[{idx}/{len(files)}] Processing Exercise 6: {path.name}", flush=True)
        raw = read_comtrade_file(path)
        leaf = extract_leaf_trade(raw)
        if leaf.empty:
            continue
        files_with_rows += 1
        outputs, removed = compute_exercise_06_outputs_for_leaf(leaf, panel)
        ex06_outputs.extend(outputs)
        ex06_removed.extend(removed)

    if not ex06_outputs:
        raise RuntimeError("No Exercise 6 rows were produced from HS bulk files.")

    exclusions = pd.concat(ex06_outputs, ignore_index=True)
    exclusions.to_parquet(sample_processed_path("concentration_exclusions_all_years.parquet"), index=False)
    exclusions.to_csv(EX06_TABLES / "concentration_exclusions_all_years.csv", index=False)
    if ex06_removed:
        removed = pd.concat(ex06_removed, ignore_index=True)
        removed.to_csv(EX06_TABLES / "trade_share_removed_by_category.csv", index=False)
    make_exercise_06_figures(exclusions)
    write_exercise_06_memo(exclusions)
    write_json(
        RESULTS / "run_manifest.json",
        {
            "created_at_utc": now_utc(),
            "mode": "exercise_06_streaming",
            "exercise": "6",
            "hs_bulk_files_seen": len(files),
            "hs_bulk_files_with_rows": files_with_rows,
            "rows_exclusions": int(len(exclusions)),
            "parquet_error": parquet_error,
            "exercises_md_updated": False,
        },
    )
    return exclusions


def run_exercise_01(leaf: pd.DataFrame) -> pd.DataFrame:
    product, partner, cell = compute_concentration(leaf, "baseline")
    product.to_csv(EX01_TABLES / "product_concentration_all_years.csv", index=False)
    partner.to_csv(EX01_TABLES / "partner_concentration_all_years.csv", index=False)
    cell.to_csv(EX01_TABLES / "product_partner_cell_concentration_all_years.csv", index=False)

    combined = merge_metric_tables(product, partner, cell)
    combined.to_parquet(sample_processed_path("concentration_all_years.parquet"), index=False)
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


def fetch_world_bank_indicator(iso3s: list[str], indicator: str, value_name: str, start: int, end: int) -> pd.DataFrame:
    cache_name = re.sub(r"[^A-Za-z0-9]+", "_", indicator).strip("_").lower()
    cache_path = WORLD_BANK_RAW / f"{cache_name}_{start}_{end}.csv"
    columns = ["iso3", "year", value_name]
    requested = sorted({str(iso3).strip().upper() for iso3 in iso3s if str(iso3).strip()})
    cached = pd.DataFrame(columns=columns)
    if cache_path.exists():
        cached = pd.read_csv(cache_path)
        if set(columns).issubset(cached.columns):
            cached = cached[columns].copy()
            cached["iso3"] = cached["iso3"].astype(str).str.strip().str.upper()
            cached["year"] = pd.to_numeric(cached["year"], errors="coerce")
            cached[value_name] = pd.to_numeric(cached[value_name], errors="coerce")
            cached = cached.dropna(subset=["iso3", "year"]).copy()
            cached["year"] = cached["year"].astype(int)
            cached = cached[cached["iso3"].isin(requested) & cached["year"].between(start, end)]
        else:
            cached = pd.DataFrame(columns=columns)

    rows = []
    cached_iso3s = set(cached.loc[cached[value_name].notna(), "iso3"])
    fetch_iso3s = requested if cached.empty else sorted(set(requested) - cached_iso3s)
    for iso3 in fetch_iso3s:
        url = f"https://api.worldbank.org/v2/country/{iso3}/indicator/{indicator}"
        params = {"format": "json", "per_page": 20000, "date": f"{start}:{end}"}
        try:
            resp = requests.get(url, params=params, timeout=5)
            if resp.status_code != 200:
                continue
            payload = resp.json()
            if not isinstance(payload, list) or len(payload) < 2:
                continue
            for item in payload[1]:
                value = item.get("value")
                if value is not None:
                    rows.append({"iso3": iso3, "year": int(item["date"]), value_name: value})
        except Exception:
            continue

    fresh = pd.DataFrame(rows, columns=columns)
    pieces = [piece for piece in (cached, fresh) if not piece.empty]
    out = pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame(columns=columns)
    if not out.empty:
        out["iso3"] = out["iso3"].astype(str).str.strip().str.upper()
        out["year"] = pd.to_numeric(out["year"], errors="coerce")
        out[value_name] = pd.to_numeric(out[value_name], errors="coerce")
        out = out.dropna(subset=["iso3", "year"]).copy()
        out["year"] = out["year"].astype(int)
        out = (
            out[out["iso3"].isin(requested) & out["year"].between(start, end)]
            .sort_values(["iso3", "year", value_name], na_position="first")
            .drop_duplicates(["iso3", "year"], keep="last")
        )
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(cache_path, index=False)
    return out


def valid_world_bank_iso3(value: object) -> bool:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return False
    text = str(value).strip().upper()
    return bool(re.fullmatch(r"[A-Z]{3}", text))


def fetch_world_bank_country_metadata(iso3s: list[str]) -> pd.DataFrame:
    cache_path = WORLD_BANK_RAW / "country_metadata.csv"
    requested = sorted({str(iso3).strip().upper() for iso3 in iso3s if valid_world_bank_iso3(iso3)})
    columns = ["iso3", "region", "income_group", "metadata_source"]
    cached = pd.DataFrame(columns=columns)
    if cache_path.exists():
        cached = pd.read_csv(cache_path)
        cached = normalize_columns(cached)
        cached = cached.rename(columns={"isocode": "iso3", "incomegroup": "income_group", "source": "metadata_source"})
        for col in columns:
            if col not in cached.columns:
                cached[col] = "world_bank_api" if col == "metadata_source" else pd.NA
        cached["iso3"] = cached["iso3"].astype(str).str.strip().str.upper()
        cached = cached[columns].dropna(subset=["iso3"]).drop_duplicates(subset=["iso3"], keep="last")
        if set(requested).issubset(set(cached["iso3"])):
            return cached[cached["iso3"].isin(requested)].copy()

    rows = []
    page = 1
    pages = 1
    while page <= pages:
        params = {"format": "json", "per_page": 400, "page": page}
        try:
            resp = requests.get("https://api.worldbank.org/v2/country", params=params, timeout=10)
            if resp.status_code != 200:
                break
            payload = resp.json()
            if not isinstance(payload, list) or len(payload) < 2:
                break
            meta = payload[0] if isinstance(payload[0], dict) else {}
            pages = int(meta.get("pages") or pages)
            for item in payload[1]:
                iso3 = str(item.get("id") or "").strip().upper()
                region = (item.get("region") or {}).get("value")
                if not valid_world_bank_iso3(iso3) or not region or region == "Aggregates":
                    continue
                rows.append(
                    {
                        "iso3": iso3,
                        "region": region,
                        "income_group": (item.get("incomeLevel") or {}).get("value"),
                        "metadata_source": "world_bank_api",
                    }
                )
        except Exception:
            break
        page += 1

    fetched = pd.DataFrame(rows, columns=columns).dropna(subset=["iso3"]) if rows else pd.DataFrame(columns=columns)
    if not fetched.empty:
        combined = pd.concat([cached, fetched], ignore_index=True)
        combined["iso3"] = combined["iso3"].astype(str).str.strip().str.upper()
        combined = combined[columns].drop_duplicates(subset=["iso3"], keep="last")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        combined.to_csv(cache_path, index=False)
        cached = combined
    return cached[cached["iso3"].isin(requested)].copy()


def fetch_world_bank_controls(iso3s: list[str], start: int, end: int) -> pd.DataFrame:
    gdp = fetch_world_bank_indicator(iso3s, "NY.GDP.MKTP.CD", "gdp_current_usd", start, end)
    population = fetch_world_bank_indicator(iso3s, "SP.POP.TOTL", "population", start, end)
    gni_pc = fetch_world_bank_indicator(iso3s, "NY.GNP.PCAP.CD", "gni_per_capita_current_usd", start, end)
    metadata = fetch_world_bank_country_metadata(iso3s)

    panel = pd.DataFrame([(iso3, year) for iso3 in sorted(set(iso3s)) for year in range(start, end + 1)], columns=["iso3", "year"])
    for df in [gdp, population, gni_pc]:
        if not df.empty:
            panel = panel.merge(df, on=["iso3", "year"], how="left")
    if not metadata.empty:
        panel = panel.merge(metadata, on="iso3", how="left")
    return panel


def exercise_02_panel_rows_for_leaf(leaf: pd.DataFrame) -> pd.DataFrame:
    exports = leaf[leaf["flow"] == "Exports"].copy()
    if exports.empty:
        return pd.DataFrame()

    product, partner, cell = compute_concentration(exports, "baseline")
    panel = merge_metric_tables(product, partner, cell)
    if panel.empty:
        return pd.DataFrame()

    product_exports = drop_excluded_hs6(exports)
    oil = product_exports[product_exports["hs2"] == "27"].groupby(["reporter_code", "year", "flow"], as_index=False)["trade_value"].sum()
    oil = oil.rename(columns={"trade_value": "oil_exports"})
    panel = panel.merge(oil, on=["reporter_code", "year", "flow"], how="left")
    panel["oil_exports"] = pd.to_numeric(panel["oil_exports"], errors="coerce").fillna(0.0)
    panel["oil_export_share"] = panel["oil_exports"] / panel["total_trade_value"].replace(0, np.nan)
    panel = panel.rename(columns={"total_trade_value": "total_exports"})
    return panel[panel["flow"] == "Exports"].copy()


def classify_exercise_02_buckets(panel: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    medians = out.groupby("year", as_index=False)[["product_gini", "partner_gini"]].median().rename(
        columns={"product_gini": "median_product_gini", "partner_gini": "median_partner_gini"}
    )
    out = out.merge(medians, on="year", how="left")
    out["product_concentration_high"] = out["product_gini"] >= out["median_product_gini"]
    out["partner_concentration_high"] = out["partner_gini"] >= out["median_partner_gini"]
    out["concentration_bucket"] = np.select(
        [
            out["product_concentration_high"] & out["partner_concentration_high"],
            out["product_concentration_high"] & ~out["partner_concentration_high"],
            ~out["product_concentration_high"] & out["partner_concentration_high"],
        ],
        ["high_product_high_partner", "high_product_low_partner", "low_product_high_partner"],
        default="low_product_low_partner",
    )
    top_share_cols = ["product_top_10pct_share", "top_5_partner_share"]
    if set(top_share_cols).issubset(out.columns):
        top_medians = out.groupby("year", as_index=False)[top_share_cols].median().rename(
            columns={
                "product_top_10pct_share": "median_product_top_10pct_share",
                "top_5_partner_share": "median_top_5_partner_share",
            }
        )
        out = out.merge(top_medians, on="year", how="left")
        out["product_top_share_high"] = out["product_top_10pct_share"] >= out["median_product_top_10pct_share"]
        out["partner_top_share_high"] = out["top_5_partner_share"] >= out["median_top_5_partner_share"]
        out["concentration_bucket_top_share"] = np.select(
            [
                out["product_top_share_high"] & out["partner_top_share_high"],
                out["product_top_share_high"] & ~out["partner_top_share_high"],
                ~out["product_top_share_high"] & out["partner_top_share_high"],
            ],
            ["high_product_high_partner", "high_product_low_partner", "low_product_high_partner"],
            default="low_product_low_partner",
        )
    return out


def build_exercise_02_growth_rows(panel: pd.DataFrame, horizons: Iterable[int] = (1, 5, 10)) -> pd.DataFrame:
    panel = classify_exercise_02_buckets(panel)
    panel["total_exports_ex_oil"] = panel["total_exports"] - panel.get("oil_exports", 0.0)
    futures = panel[["reporter_code", "year", "total_exports"]].rename(
        columns={"year": "future_year", "total_exports": "future_exports"}
    )
    futures_ex_oil = panel[["reporter_code", "year", "total_exports_ex_oil"]].rename(
        columns={"year": "future_year", "total_exports_ex_oil": "future_exports_ex_oil"}
    )
    rows = []
    for horizon in horizons:
        base = panel.copy()
        base["future_year"] = base["year"] + horizon
        merged = base.merge(futures, on=["reporter_code", "future_year"], how="left")
        merged = merged.merge(futures_ex_oil, on=["reporter_code", "future_year"], how="left")
        merged = merged.dropna(subset=["future_exports"]).copy()
        if merged.empty:
            continue
        merged["horizon"] = horizon
        merged["export_growth_pct"] = (merged["future_exports"] - merged["total_exports"]) / merged["total_exports"]
        merged["export_growth_log"] = np.log(merged["future_exports"]) - np.log(merged["total_exports"])
        merged["annualized_export_growth_log"] = merged["export_growth_log"] / horizon
        ex_oil_valid = (merged["total_exports_ex_oil"] > 0) & (merged["future_exports_ex_oil"] > 0)
        merged["export_growth_log_ex_oil"] = np.where(
            ex_oil_valid,
            np.log(merged["future_exports_ex_oil"]) - np.log(merged["total_exports_ex_oil"]),
            np.nan,
        )
        merged["annualized_export_growth_log_ex_oil"] = merged["export_growth_log_ex_oil"] / horizon
        merged["log_initial_exports"] = np.log(merged["total_exports"])
        rows.append(merged)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def add_exercise_02_us_deflated_growth(growth: pd.DataFrame) -> pd.DataFrame:
    if growth.empty:
        return growth
    out = growth.copy()
    out = out.drop(
        columns=[
            "base_us_gdp_deflator",
            "future_us_gdp_deflator",
            "export_growth_log_us_deflated",
            "annualized_export_growth_log_us_deflated",
        ],
        errors="ignore",
    )
    end_year = int(pd.to_numeric(out["future_year"], errors="coerce").max())
    deflator = fetch_world_bank_indicator(["USA"], "NY.GDP.DEFL.ZS", "us_gdp_deflator", int(out["year"].min()), end_year)
    if deflator.empty:
        out["annualized_export_growth_log_us_deflated"] = np.nan
        return out
    deflator = deflator[["year", "us_gdp_deflator"]].copy()
    deflator["us_gdp_deflator"] = pd.to_numeric(deflator["us_gdp_deflator"], errors="coerce")
    out = out.merge(deflator.rename(columns={"year": "year", "us_gdp_deflator": "base_us_gdp_deflator"}), on="year", how="left")
    out = out.merge(
        deflator.rename(columns={"year": "future_year", "us_gdp_deflator": "future_us_gdp_deflator"}),
        on="future_year",
        how="left",
    )
    valid = (
        (out["base_us_gdp_deflator"] > 0)
        & (out["future_us_gdp_deflator"] > 0)
        & (out["total_exports"] > 0)
        & (out["future_exports"] > 0)
    )
    base_real = out["total_exports"] / (out["base_us_gdp_deflator"] / 100.0)
    future_real = out["future_exports"] / (out["future_us_gdp_deflator"] / 100.0)
    out["export_growth_log_us_deflated"] = np.where(valid, np.log(future_real) - np.log(base_real), np.nan)
    out["annualized_export_growth_log_us_deflated"] = out["export_growth_log_us_deflated"] / out["horizon"]
    return out


def add_exercise_02_controls(growth: pd.DataFrame) -> pd.DataFrame:
    if growth.empty:
        return growth
    growth = add_exercise_02_us_deflated_growth(growth)
    control_cols = [
        "gdp_current_usd",
        "population",
        "gni_per_capita_current_usd",
        "region",
        "income_group",
        "metadata_source",
        "log_gdp_current_usd",
        "log_population",
        "log_gni_per_capita_current_usd",
    ]
    growth = growth.drop(columns=control_cols, errors="ignore")
    controls = fetch_world_bank_controls(
        sorted(growth["iso3"].dropna().unique()),
        int(growth["year"].min()),
        int(growth["year"].max()),
    )
    if not controls.empty:
        controls = controls.drop_duplicates(["iso3", "year"], keep="last")
        controls.to_csv(sample_processed_path("exercise_02_world_bank_controls.csv"), index=False)
    out = growth.merge(controls, on=["iso3", "year"], how="left") if not controls.empty else growth.copy()
    for source, target in [
        ("gdp_current_usd", "log_gdp_current_usd"),
        ("population", "log_population"),
        ("gni_per_capita_current_usd", "log_gni_per_capita_current_usd"),
    ]:
        if source in out.columns:
            out[target] = np.log(pd.to_numeric(out[source], errors="coerce"))
    return out


def exercise_02_model_specs() -> list[dict]:
    return [
        {
            "model_id": "E2-1",
            "model_label": "bucket_year_fe",
            "outcome": "annualized_export_growth_log",
            "predictor": "bucket",
            "controls": [],
            "fixed_effects": ["year"],
            "robustness": "main",
        },
        {
            "model_id": "E2-2",
            "model_label": "bucket_country_year_fe_core",
            "outcome": "annualized_export_growth_log",
            "predictor": "bucket",
            "controls": ["log_initial_exports", "oil_export_share"],
            "fixed_effects": ["reporter_code", "year"],
            "robustness": "main",
        },
        {
            "model_id": "E2-3",
            "model_label": "bucket_country_year_fe_controls",
            "outcome": "annualized_export_growth_log",
            "predictor": "bucket",
            "controls": [
                "log_initial_exports",
                "oil_export_share",
                "log_gdp_current_usd",
                "log_population",
                "log_gni_per_capita_current_usd",
            ],
            "fixed_effects": ["reporter_code", "year"],
            "robustness": "main",
        },
        {
            "model_id": "E2-R1",
            "model_label": "continuous_gini_country_year_fe",
            "outcome": "annualized_export_growth_log",
            "predictor": "continuous_gini",
            "controls": ["log_initial_exports", "oil_export_share"],
            "fixed_effects": ["reporter_code", "year"],
            "robustness": "continuous_gini",
        },
        {
            "model_id": "E2-R2",
            "model_label": "top_share_bucket_country_year_fe",
            "outcome": "annualized_export_growth_log",
            "predictor": "top_share_bucket",
            "controls": ["log_initial_exports", "oil_export_share"],
            "fixed_effects": ["reporter_code", "year"],
            "robustness": "top_share_bucket",
        },
        {
            "model_id": "E2-R3",
            "model_label": "oil_excluded_growth_country_year_fe",
            "outcome": "annualized_export_growth_log_ex_oil",
            "predictor": "bucket",
            "controls": ["log_initial_exports", "oil_export_share"],
            "fixed_effects": ["reporter_code", "year"],
            "robustness": "oil_excluded_growth",
        },
        {
            "model_id": "E2-R4",
            "model_label": "us_deflated_growth_country_year_fe",
            "outcome": "annualized_export_growth_log_us_deflated",
            "predictor": "bucket",
            "controls": ["log_initial_exports", "oil_export_share"],
            "fixed_effects": ["reporter_code", "year"],
            "robustness": "us_gdp_deflator_growth",
        },
    ]


def exercise_02_predictor_columns(df: pd.DataFrame, predictor: str) -> tuple[pd.DataFrame, list[str]]:
    if predictor == "bucket":
        bucket_col = "concentration_bucket"
        prefix = "bucket"
    elif predictor == "top_share_bucket":
        bucket_col = "concentration_bucket_top_share"
        prefix = "top_share_bucket"
    else:
        bucket_col = ""
        prefix = ""

    if predictor in {"bucket", "top_share_bucket"}:
        bucket_order = ["high_product_high_partner", "high_product_low_partner", "low_product_high_partner"]
        cols = {
            f"{prefix}_{bucket}": (df[bucket_col] == bucket).astype(float)
            for bucket in bucket_order
        }
        return pd.DataFrame(cols, index=df.index), list(cols)

    if predictor == "continuous_gini":
        out = pd.DataFrame(index=df.index)
        out["product_gini"] = pd.to_numeric(df["product_gini"], errors="coerce")
        out["partner_gini"] = pd.to_numeric(df["partner_gini"], errors="coerce")
        out["product_gini_x_partner_gini"] = out["product_gini"] * out["partner_gini"]
        return out, list(out.columns)

    raise ValueError(f"Unknown Exercise 2 predictor: {predictor}")


def full_rank_columns(x: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    kept = []
    dropped = []
    current = None
    current_rank = 0
    for col in x.columns:
        candidate = x[[col]] if current is None else pd.concat([current, x[[col]]], axis=1)
        rank = np.linalg.matrix_rank(candidate.to_numpy(dtype=float))
        if rank > current_rank:
            kept.append(col)
            current = candidate
            current_rank = rank
        else:
            dropped.append(col)
    return x[kept], dropped


def exercise_02_design_matrix(work: pd.DataFrame, spec: dict) -> tuple[pd.DataFrame, list[str], list[str]]:
    parts = [pd.Series(1.0, index=work.index, name="intercept")]
    predictor_frame, variables_of_interest = exercise_02_predictor_columns(work, spec["predictor"])
    parts.append(predictor_frame)

    for col in spec.get("controls", []):
        parts.append(pd.to_numeric(work[col], errors="coerce").rename(col))

    for fe_col in spec.get("fixed_effects", []):
        dummies = pd.get_dummies(work[fe_col].astype(str), prefix=fe_col, drop_first=True, dtype=float)
        if not dummies.empty:
            parts.append(dummies)

    x = pd.concat(parts, axis=1).astype(float)
    x, dropped = full_rank_columns(x)
    return x, variables_of_interest, dropped


def cluster_robust_covariance(x: np.ndarray, resid: np.ndarray, clusters: pd.Series) -> np.ndarray:
    xtx_inv = np.linalg.pinv(x.T @ x)
    meat = np.zeros((x.shape[1], x.shape[1]))
    cluster_values = pd.Series(clusters).to_numpy()
    unique_clusters = pd.unique(cluster_values)
    for cluster in unique_clusters:
        mask = cluster_values == cluster
        xu = x[mask].T @ resid[mask]
        meat += np.outer(xu, xu)
    nobs, k = x.shape
    groups = len(unique_clusters)
    correction = 1.0
    if groups > 1 and nobs > k:
        correction = (groups / (groups - 1)) * ((nobs - 1) / (nobs - k))
    return correction * xtx_inv @ meat @ xtx_inv


def run_exercise_02_model(df: pd.DataFrame, spec: dict, horizon: int) -> tuple[pd.DataFrame, dict]:
    base = df[df["horizon"] == horizon].copy()
    required = [spec["outcome"], "reporter_code", "year"]
    if spec["predictor"] == "bucket":
        required.append("concentration_bucket")
    elif spec["predictor"] == "top_share_bucket":
        required.append("concentration_bucket_top_share")
    elif spec["predictor"] == "continuous_gini":
        required.extend(["product_gini", "partner_gini"])
    required.extend(spec.get("controls", []))
    required.extend(spec.get("fixed_effects", []))
    required = list(dict.fromkeys(required))

    missing_required = [col for col in required if col not in base.columns]
    diagnostics = {
        "model_id": spec["model_id"],
        "model_label": spec["model_label"],
        "horizon": int(horizon),
        "outcome": spec["outcome"],
        "predictor": spec["predictor"],
        "robustness": spec["robustness"],
        "fixed_effects": ",".join(spec.get("fixed_effects", [])) or "none",
        "controls": ",".join(spec.get("controls", [])) or "none",
        "standard_error_type": "country_clustered",
        "cluster_col": "reporter_code",
        "candidate_rows": int(len(base)),
        "nobs": 0,
        "dropped_rows": int(len(base)) if missing_required else 0,
        "countries": 0,
        "dropped_regressors": "",
        "missing_required_columns": ",".join(missing_required),
        "status": "not_run",
    }
    if missing_required:
        diagnostics["status"] = "missing_required_columns"
        return pd.DataFrame(), diagnostics

    work = base.replace([np.inf, -np.inf], np.nan).dropna(subset=required).copy()
    diagnostics["nobs"] = int(len(work))
    diagnostics["dropped_rows"] = int(len(base) - len(work))
    diagnostics["countries"] = int(work["reporter_code"].nunique()) if not work.empty else 0
    if len(work) < 4 or work["reporter_code"].nunique() < 2:
        diagnostics["status"] = "insufficient_sample"
        return pd.DataFrame(), diagnostics

    y = pd.to_numeric(work[spec["outcome"]], errors="coerce").to_numpy(dtype=float)
    x_df, variables_of_interest, dropped_regressors = exercise_02_design_matrix(work, spec)
    diagnostics["dropped_regressors"] = ",".join(dropped_regressors)
    if x_df.shape[0] <= x_df.shape[1]:
        diagnostics["status"] = "too_many_regressors"
        return pd.DataFrame(), diagnostics

    x = x_df.to_numpy(dtype=float)
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    fitted = x @ beta
    resid = y - fitted
    cov = cluster_robust_covariance(x, resid, work["reporter_code"])
    se = np.sqrt(np.clip(np.diag(cov), 0, np.inf))
    total_var = np.sum((y - y.mean()) ** 2)
    diagnostics["r_squared"] = float(1 - np.sum(resid**2) / total_var) if total_var > 0 else np.nan
    diagnostics["status"] = "ok"

    rows = []
    for name, coefficient, stderr in zip(x_df.columns, beta, se):
        rows.append(
            {
                **{key: diagnostics[key] for key in [
                    "model_id",
                    "model_label",
                    "horizon",
                    "outcome",
                    "predictor",
                    "robustness",
                    "fixed_effects",
                    "controls",
                    "standard_error_type",
                    "cluster_col",
                    "nobs",
                    "countries",
                ]},
                "variable": name,
                "variable_role": "main" if name in variables_of_interest else "control_or_fixed_effect",
                "coefficient": float(coefficient),
                "std_error": float(stderr),
                "t_stat": float(coefficient / stderr) if stderr > 0 else np.nan,
                "r_squared": diagnostics["r_squared"],
                "dropped_rows": diagnostics["dropped_rows"],
            }
        )
    return pd.DataFrame(rows), diagnostics


def run_exercise_02_models(growth: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    model_rows = []
    diagnostic_rows = []
    for spec in exercise_02_model_specs():
        if spec["outcome"] not in growth.columns:
            continue
        if spec["predictor"] == "top_share_bucket" and "concentration_bucket_top_share" not in growth.columns:
            continue
        for horizon in sorted(pd.to_numeric(growth["horizon"], errors="coerce").dropna().astype(int).unique()):
            model, diagnostics = run_exercise_02_model(growth, spec, int(horizon))
            diagnostic_rows.append(diagnostics)
            if not model.empty:
                model_rows.append(model)
    models = pd.concat(model_rows, ignore_index=True) if model_rows else pd.DataFrame()
    diagnostics = pd.DataFrame(diagnostic_rows)
    return models, diagnostics


def run_exercise_02_from_panel(panel: pd.DataFrame, source_details: dict | None = None) -> pd.DataFrame:
    if panel.empty:
        raise RuntimeError("No Exercise 2 export panel rows were produced.")
    panel = panel.sort_values(["reporter_code", "year"]).copy()
    panel.to_parquet(sample_processed_path("exercise_02_export_concentration_panel.parquet"), index=False)
    panel.to_csv(EX02_TABLES / "export_concentration_panel.csv", index=False)

    growth = build_exercise_02_growth_rows(panel)
    if growth.empty:
        raise RuntimeError("No Exercise 2 growth rows were produced. Need at least one country with t+h export data.")
    growth = add_exercise_02_controls(growth)
    growth.to_parquet(sample_processed_path("exercise_02_bucket_growth_panel.parquet"), index=False)
    growth.to_csv(EX02_TABLES / "bucket_growth_panel.csv", index=False)

    summary = growth.groupby(["horizon", "concentration_bucket"], as_index=False).agg(
        observations=("annualized_export_growth_log", "size"),
        mean_annualized_log_growth=("annualized_export_growth_log", "mean"),
        median_annualized_log_growth=("annualized_export_growth_log", "median"),
        mean_export_growth_pct=("export_growth_pct", "mean"),
        median_initial_exports=("total_exports", "median"),
    )
    summary.to_csv(EX02_TABLES / "bucket_growth_summary.csv", index=False)

    models, diagnostics = run_exercise_02_models(growth)
    models.to_csv(EX02_TABLES / "bucket_growth_models.csv", index=False)
    diagnostics.to_csv(EX02_TABLES / "bucket_growth_diagnostics.csv", index=False)
    models.to_csv(EX02_TABLES / "bucket_growth_ols.csv", index=False)

    make_exercise_02_figures(growth, summary)
    write_exercise_02_memo(growth, summary, models, diagnostics, source_details or {})
    return growth


def run_exercise_02(leaf: pd.DataFrame) -> pd.DataFrame:
    panel = exercise_02_panel_rows_for_leaf(leaf)
    return run_exercise_02_from_panel(panel, source_details={"mode": "in_memory_leaf"})


def exercise_02_partial_dir() -> Path:
    return sample_processed_dir() / "checkpoints" / "exercise_02_file_panels"


def exercise_02_partial_path(raw_path: Path) -> Path:
    return exercise_02_partial_dir() / checkpoint_name_for_raw(raw_path)


def empty_exercise_02_panel() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "country",
            "iso3",
            "reporter_code",
            "year",
            "flow",
            "variant",
            "total_exports",
            "product_gini",
            "product_top_1pct_share",
            "product_top_2pct_share",
            "product_top_5pct_share",
            "product_top_10pct_share",
            "product_top_200_share",
            "product_active_count",
            "partner_total_trade_value",
            "partner_gini",
            "partner_top_1pct_share",
            "partner_top_2pct_share",
            "partner_top_5pct_share",
            "partner_top_10pct_share",
            "partner_top_200_share",
            "partner_active_count",
            "top_5_partner_share",
            "product_partner_cell_gini",
            "product_partner_cell_top_1pct_share",
            "product_partner_cell_top_2pct_share",
            "product_partner_cell_top_5pct_share",
            "product_partner_cell_top_10pct_share",
            "product_partner_cell_top_200_share",
            "product_partner_cell_active_count",
            "oil_exports",
            "oil_export_share",
        ]
    )


def exercise_02_panel_from_aggregate_values(
    product_values: pd.DataFrame,
    partner_values: pd.DataFrame,
    cell_values: pd.DataFrame,
    oil_values: pd.DataFrame,
) -> pd.DataFrame:
    product_cols = ["reporter_code", "year", "flow", "cmd_code", "trade_value"]
    partner_cols = ["reporter_code", "year", "flow", "partner_code", "trade_value"]
    cell_cols = ["reporter_code", "year", "flow", "cmd_code", "partner_code", "trade_value"]
    oil_cols = ["reporter_code", "year", "flow", "trade_value"]
    product_values = finish_group_sum_frame(product_values, product_cols[:-1])
    partner_values = finish_group_sum_frame(partner_values, partner_cols[:-1], exclude_hs6=False)
    cell_values = finish_group_sum_frame(cell_values, cell_cols[:-1])
    oil_values = finish_group_sum_frame(oil_values, oil_cols[:-1], exclude_hs6=False)
    if product_values.empty:
        return empty_exercise_02_panel()

    panel = save_country_panel()
    country_meta = panel.set_index("reporter_code")[["country", "iso3"]].to_dict("index")
    group_cols = ["reporter_code", "year", "flow"]
    product_rows = []
    partner_rows = []
    cell_rows = []
    for key, group in product_values.groupby(group_cols, sort=True):
        reporter_code, year, flow = key
        meta = country_meta.get(int(reporter_code), {"country": str(reporter_code), "iso3": ""})
        base = {
            "country": meta["country"],
            "iso3": meta["iso3"],
            "reporter_code": int(reporter_code),
            "year": int(year),
            "flow": flow,
            "variant": "baseline",
            "total_trade_value": float(group["trade_value"].sum()),
        }
        product_rows.append({**base, **metric_row(group["trade_value"], "product")})

    for key, group in partner_values.groupby(group_cols, sort=True):
        reporter_code, year, flow = key
        meta = country_meta.get(int(reporter_code), {"country": str(reporter_code), "iso3": ""})
        base = {
            "country": meta["country"],
            "iso3": meta["iso3"],
            "reporter_code": int(reporter_code),
            "year": int(year),
            "flow": flow,
            "variant": "baseline",
            "total_trade_value": float(group["trade_value"].sum()),
        }
        partner_rows.append({**base, **metric_row(group["trade_value"], "partner"), "top_5_partner_share": top_share(group["trade_value"], n=5)})

    for key, group in cell_values.groupby(group_cols, sort=True):
        reporter_code, year, flow = key
        meta = country_meta.get(int(reporter_code), {"country": str(reporter_code), "iso3": ""})
        base = {
            "country": meta["country"],
            "iso3": meta["iso3"],
            "reporter_code": int(reporter_code),
            "year": int(year),
            "flow": flow,
            "variant": "baseline",
            "total_trade_value": float(group["trade_value"].sum()),
        }
        cell_rows.append({**base, **metric_row(group["trade_value"], "product_partner_cell")})

    panel = merge_metric_tables(pd.DataFrame(product_rows), pd.DataFrame(partner_rows), pd.DataFrame(cell_rows))
    if panel.empty:
        return empty_exercise_02_panel()
    oil = oil_values.rename(columns={"trade_value": "oil_exports"})
    panel = panel.merge(oil, on=["reporter_code", "year", "flow"], how="left")
    panel["oil_exports"] = pd.to_numeric(panel["oil_exports"], errors="coerce").fillna(0.0)
    panel["oil_export_share"] = panel["oil_exports"] / panel["total_trade_value"].replace(0, np.nan)
    panel = panel.rename(columns={"total_trade_value": "total_exports"})
    return panel[panel["flow"] == "Exports"].copy()


def exercise_02_panel_rows_for_raw(raw_path: Path, chunk_rows: int = DEFAULT_CHUNK_ROWS) -> pd.DataFrame:
    product_values: pd.DataFrame | None = None
    partner_values: pd.DataFrame | None = None
    cell_values: pd.DataFrame | None = None
    oil_values: pd.DataFrame | None = None
    group_cols = ["reporter_code", "year", "flow"]
    for leaf in iter_leaf_trade_chunks(raw_path, chunk_rows=chunk_rows):
        exports = leaf[leaf["flow"] == "Exports"].copy()
        if exports.empty:
            del leaf, exports
            continue
        product_exports = drop_excluded_hs6(exports)
        if not product_exports.empty:
            chunk_products = product_exports.groupby([*group_cols, "cmd_code"], as_index=False)["trade_value"].sum()
            chunk_cells = product_exports.groupby([*group_cols, "cmd_code", "partner_code"], as_index=False)["trade_value"].sum()
            chunk_oil = product_exports[product_exports["hs2"] == "27"].groupby(group_cols, as_index=False)["trade_value"].sum()
            product_values = add_group_sum_frame(product_values, chunk_products, [*group_cols, "cmd_code"], compact_rows=250_000)
            cell_values = add_group_sum_frame(cell_values, chunk_cells, [*group_cols, "cmd_code", "partner_code"], compact_rows=250_000)
            oil_values = add_group_sum_frame(oil_values, chunk_oil, group_cols, compact_rows=250_000, exclude_hs6=False)
        chunk_partners = exports.groupby([*group_cols, "partner_code"], as_index=False)["trade_value"].sum()
        partner_values = add_group_sum_frame(partner_values, chunk_partners, [*group_cols, "partner_code"], compact_rows=250_000, exclude_hs6=False)
        del leaf, exports, product_exports, chunk_partners
        if "chunk_products" in locals():
            del chunk_products, chunk_cells, chunk_oil
        gc.collect()

    panel = exercise_02_panel_from_aggregate_values(
        finish_group_sum_frame(product_values, [*group_cols, "cmd_code"]),
        finish_group_sum_frame(partner_values, [*group_cols, "partner_code"], exclude_hs6=False),
        finish_group_sum_frame(cell_values, [*group_cols, "cmd_code", "partner_code"]),
        finish_group_sum_frame(oil_values, group_cols, exclude_hs6=False),
    )
    gc.collect()
    return panel


def write_exercise_02_partial_for_raw(raw_path: Path, chunk_rows: int = DEFAULT_CHUNK_ROWS) -> tuple[Path, int]:
    partial = exercise_02_partial_path(raw_path)
    panel = exercise_02_panel_rows_for_raw(raw_path, chunk_rows=chunk_rows)
    panel.to_parquet(partial, index=False)
    return partial, int(len(panel))


def write_exercise_02_partials(max_files: int | None = None, fresh: bool = False, chunk_rows: int = DEFAULT_CHUNK_ROWS) -> list[Path]:
    partial_dir = exercise_02_partial_dir()
    if fresh and partial_dir.exists():
        shutil.rmtree(partial_dir)
    partial_dir.mkdir(parents=True, exist_ok=True)
    files = hs_bulk_files(max_files=max_files)
    if not files:
        raise FileNotFoundError(f"No HS Comtrade bulk files found in {COMTRADE_BULK}")

    partials = []
    manifest_rows = []
    for idx, path in enumerate(files, start=1):
        partial = exercise_02_partial_path(path)
        partials.append(partial)
        if partial.exists():
            print(f"[{idx}/{len(files)}] skip existing Exercise 2 checkpoint {partial.name}", flush=True)
            manifest_rows.append({"raw_file": path.name, "partial_file": partial.name, "status": "already_exists"})
            continue
        print(f"[{idx}/{len(files)}] Exercise 2 export panel from {path.name}", flush=True)
        _, rows = write_exercise_02_partial_for_raw(path, chunk_rows=chunk_rows)
        manifest_rows.append({"raw_file": path.name, "partial_file": partial.name, "status": "written", "rows": rows})
        write_json(
            RESULTS / "run_manifest_exercise_02_checkpoints.json",
            {
                "created_at_utc": now_utc(),
                "mode": "exercise_02_checkpoint_partials",
                "raw_files_seen": len(files),
                "raw_files_attempted": idx,
                "partial_files_present": len(list(partial_dir.glob("*.parquet"))),
                "latest_raw_file": path.name,
                "manifest_tail": manifest_rows[-25:],
                "chunk_rows": int(chunk_rows),
                "exercises_md_updated": False,
            },
        )
    return partials


def finalize_exercise_02_from_partials(partials: list[Path], source_details: dict | None = None) -> pd.DataFrame:
    frames = []
    missing = [path for path in partials if not path.exists()]
    if missing:
        raise RuntimeError(f"Exercise 2 checkpoint set is incomplete; missing {len(missing)} files.")
    for partial in partials:
        frame = pd.read_parquet(partial)
        if not frame.empty:
            frames.append(frame)
    if not frames:
        raise RuntimeError("No Exercise 2 export panel rows were produced from checkpoint files.")
    panel = pd.concat(frames, ignore_index=True)
    duplicate_keys = panel.duplicated(["reporter_code", "year", "flow"], keep=False)
    if duplicate_keys.any():
        examples = panel.loc[duplicate_keys, ["reporter_code", "year", "flow"]].drop_duplicates().head(10).to_dict("records")
        raise RuntimeError(f"Exercise 2 checkpoint panel has duplicate reporter-year-flow keys: {examples}")
    return run_exercise_02_from_panel(panel, source_details=source_details or {})


def run_exercise_02_streaming(
    max_files: int | None = None,
    fresh_checkpoints: bool = False,
    finalize_only: bool = False,
    chunk_rows: int = DEFAULT_CHUNK_ROWS,
) -> pd.DataFrame:
    files = hs_bulk_files(max_files=max_files)
    if not files:
        raise FileNotFoundError(f"No HS Comtrade bulk files found in {COMTRADE_BULK}")
    if finalize_only:
        partials = [exercise_02_partial_path(path) for path in files]
        if not partials or any(not partial.exists() for partial in partials):
            raise RuntimeError(f"No complete Exercise 2 checkpoint set found in {exercise_02_partial_dir()}.")
    else:
        partials = write_exercise_02_partials(max_files=max_files, fresh=fresh_checkpoints, chunk_rows=chunk_rows)
    growth = finalize_exercise_02_from_partials(
        partials,
        source_details={
            "mode": "checkpointed_streaming",
            "hs_bulk_files_processed": len(files),
            "partial_files": len(partials),
            "partial_dir": str(exercise_02_partial_dir().relative_to(ROOT)),
            "finalize_only": finalize_only,
            "chunk_rows": int(chunk_rows),
        },
    )
    write_json(
        RESULTS / "run_manifest.json",
        {
            "created_at_utc": now_utc(),
            "mode": "exercise_02_checkpointed",
            "exercise": "2",
            "hs_bulk_files_seen": len(files),
            "partial_files": len(partials),
            "rows_growth": int(len(growth)),
            "exercises_md_updated": False,
        },
    )
    return growth


def make_exercise_02_figures(growth: pd.DataFrame, summary: pd.DataFrame) -> None:
    import matplotlib.pyplot as plt
    import seaborn as sns

    sns.set_theme(style="whitegrid")
    plt.figure(figsize=(12, 7))
    sns.barplot(data=summary, x="horizon", y="mean_annualized_log_growth", hue="concentration_bucket")
    plt.title("Exercise 2: Mean Annualized Export Growth By Concentration Bucket")
    plt.tight_layout()
    plt.savefig(EX02_FIGURES / "bucket_mean_annualized_growth.png", dpi=200)
    plt.close()

    plt.figure(figsize=(10, 7))
    sns.scatterplot(
        data=growth,
        x="product_gini",
        y="partner_gini",
        hue="annualized_export_growth_log",
        style="horizon",
        palette="vlag",
    )
    plt.title("Exercise 2: Initial Concentration And Future Export Growth")
    plt.tight_layout()
    plt.savefig(EX02_FIGURES / "initial_concentration_vs_growth.png", dpi=200)
    plt.close()


def write_exercise_02_memo(
    growth: pd.DataFrame,
    summary: pd.DataFrame,
    models: pd.DataFrame,
    diagnostics: pd.DataFrame,
    source_details: dict,
) -> None:
    controls = [col for col in ["gdp_current_usd", "population", "gni_per_capita_current_usd", "region", "income_group"] if col in growth.columns]
    main_coefficients = (
        models[(models["variable_role"] == "main") & (models["robustness"] == "main")]
        .round(4)
        .to_markdown(index=False)
        if not models.empty
        else "No model table was produced because the sample is too small or collinear."
    )
    robustness_coefficients = (
        models[(models["variable_role"] == "main") & (models["robustness"] != "main")]
        .round(4)
        .to_markdown(index=False)
        if not models.empty and (models["robustness"] != "main").any()
        else "No robustness model table was produced."
    )
    diagnostic_table = (
        diagnostics[
            [
                "model_id",
                "model_label",
                "horizon",
                "status",
                "candidate_rows",
                "nobs",
                "dropped_rows",
                "countries",
                "standard_error_type",
            ]
        ]
        .to_markdown(index=False)
        if not diagnostics.empty
        else "No diagnostics table was produced."
    )
    memo = f"""# Exercise 2: Four-Bucket Growth Exercise

Generated: {now_utc()}

This memo is intentionally descriptive. The model is a predictive reduced-form panel exercise, not a causal estimate of what concentration does to growth.

## Coverage

- Country-year-horizon rows: {len(growth)}
- Countries: {growth["country"].nunique()}
- Base years: {int(growth["year"].min())}-{int(growth["year"].max())}
- Horizons: {", ".join(str(int(h)) for h in sorted(growth["horizon"].unique()))}
- Controls available: {", ".join(controls) if controls else "none"}
- Source details: `{json.dumps(source_details, sort_keys=True)}`

## Bucket Summary

{summary.round(4).to_markdown(index=False)}

## Main Panel Model Coefficients

{main_coefficients}

## Robustness Coefficients

{robustness_coefficients}

## Model Diagnostics

{diagnostic_table}

## Econometric Interpretation

The bucket coefficients compare each concentration bucket with low-product/low-partner concentration. Country fixed effects absorb time-invariant country differences, year fixed effects absorb common shocks, and standard errors are clustered by country. Rows with missing required controls are dropped rather than converted to zero.

The estimates support or weaken a predictive relationship. They should not be read as proof that concentration causes export growth.

## Files

- Tables: `results/exercise_02_tables/`
- Figures: `results/exercise_02_figures/`
- Processed data: `data/processed/exercise_02_bucket_growth_panel.parquet`
- Main model table: `results/exercise_02_tables/bucket_growth_models.csv`
- Diagnostics: `results/exercise_02_tables/bucket_growth_diagnostics.csv`

## Discussion Prompt

Do high-product/high-partner concentration countries grow differently after accounting for initial exports, oil share, and available World Bank controls?
"""
    write_text(sample_results_dir() / "exercise_02_bucket_growth.md", memo)


def partner_reference_table() -> pd.DataFrame:
    cache_path = COMTRADE_RAW / "partner_reference.csv"
    if cache_path.exists():
        return pd.read_csv(cache_path)
    try:
        resp = requests.get("https://comtradeapi.un.org/files/v1/app/reference/partnerAreas.json", timeout=5)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}")
        payload = resp.json()
        ref = pd.DataFrame(payload.get("results", payload) if isinstance(payload, dict) else payload)
    except Exception:
        return pd.DataFrame(columns=["partner_code", "partner_iso3", "partner_name"])
    if ref is None or ref.empty:
        return pd.DataFrame(columns=["partner_code", "partner_iso3", "partner_name"])
    out = normalize_columns(ref).rename(
        columns={"PartnerCode": "partner_code", "PartnerCodeIsoAlpha3": "partner_iso3", "PartnerDesc": "partner_name"}
    )
    out = out.rename(columns={"partnercode": "partner_code", "partnercodeisoalpha3": "partner_iso3", "partnerdesc": "partner_name"})
    missing = {"partner_code", "partner_iso3", "partner_name"} - set(out.columns)
    if missing:
        return pd.DataFrame(columns=["partner_code", "partner_iso3", "partner_name"])
    out = out[["partner_code", "partner_iso3", "partner_name"]].copy()
    out["partner_code"] = pd.to_numeric(out["partner_code"], errors="coerce")
    out = out.dropna(subset=["partner_code"])
    out["partner_code"] = out["partner_code"].astype(int)
    out.to_csv(cache_path, index=False)
    return out


def partner_region_table(partner_codes: Iterable[int]) -> pd.DataFrame:
    requested = pd.DataFrame({"partner_code": sorted(set(int(code) for code in partner_codes if pd.notna(code)))})
    if requested.empty:
        return pd.DataFrame(columns=["partner_code", "partner_iso3", "partner_name", "partner_region", "partner_region_source", "partner_region_reliability"])
    ref = partner_reference_table()
    if ref.empty:
        out = requested.copy()
        out["partner_iso3"] = ""
        out["partner_name"] = ""
        out["partner_region"] = "Unknown"
        out["partner_region_source"] = "unknown_no_comtrade_partner_reference"
        out["partner_region_reliability"] = "unknown"
        return out
    ref = requested.merge(ref, on="partner_code", how="left")
    ref["partner_iso3"] = ref["partner_iso3"].fillna("").astype(str).str.strip().str.upper()
    iso3s = sorted(iso3 for iso3 in ref["partner_iso3"].replace("", np.nan).dropna().unique() if valid_world_bank_iso3(iso3))
    metadata = fetch_world_bank_country_metadata(iso3s) if iso3s else pd.DataFrame()
    if not metadata.empty:
        ref = ref.merge(metadata[["iso3", "region", "metadata_source"]], left_on="partner_iso3", right_on="iso3", how="left")
    else:
        ref["region"] = np.nan
        ref["metadata_source"] = np.nan
    ref["partner_region"] = ref["region"].fillna("Unknown")
    ref["partner_region_source"] = np.where(ref["region"].notna(), "world_bank", "unknown_no_world_bank_match")
    ref["partner_region_reliability"] = np.where(ref["partner_region_source"] == "world_bank", "world_bank_country_region", "unknown")
    ref["partner_name"] = ref["partner_name"].fillna("")
    return ref[["partner_code", "partner_iso3", "partner_name", "partner_region", "partner_region_source", "partner_region_reliability"]].copy()


def exercise_12_export_aggregates_for_leaf(leaf: pd.DataFrame) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    exports = leaf[leaf["flow"] == "Exports"].copy()
    if exports.empty:
        return {}, pd.DataFrame()
    if "classification_code" not in exports.columns:
        exports["classification_code"] = ""
    exports["classification_code"] = exports["classification_code"].map(normalize_hs_classification_code)

    frames = {}
    product_exports = drop_excluded_hs6(exports)
    if not product_exports.empty:
        product = product_exports.groupby(
            ["reporter_code", "year", "classification_code", "cmd_code"],
            as_index=False,
        )["trade_value"].sum()
        product["dimension"] = "product"
        frames["product"] = product

        cell = product_exports.groupby(
            ["reporter_code", "year", "classification_code", "cmd_code", "partner_code"],
            as_index=False,
        )["trade_value"].sum()
        cell["dimension"] = "product_partner_cell"
        frames["product_partner_cell"] = cell

    partner = exports.groupby(["reporter_code", "year", "partner_code"], as_index=False)["trade_value"].sum()
    partner["dimension"] = "partner"
    frames["partner"] = partner

    if product_exports.empty:
        product_partner = pd.DataFrame(
            columns=["reporter_code", "year", "classification_code", "cmd_code", "partner_code", "trade_value"]
        )
    else:
        product_partner = product_exports.groupby(
            ["reporter_code", "year", "classification_code", "cmd_code", "partner_code"],
            as_index=False,
        )["trade_value"].sum()
    return frames, product_partner


def add_country_metadata(df: pd.DataFrame) -> pd.DataFrame:
    panel = save_country_panel()
    return df.merge(panel, on="reporter_code", how="left")


def item_columns_for_dimension(dimension: str) -> list[str]:
    return {
        "product": ["cmd_code"],
        "partner": ["partner_code"],
        "product_partner_cell": ["cmd_code", "partner_code"],
    }[dimension]


def hs_revision_node_id(classification_code: object, cmd_code: object) -> str:
    revision = normalize_hs_classification_code(classification_code).replace("", "UNKNOWN")
    code = normalize_digit_code(cmd_code, digits=6)
    return f"{revision}:{code}" if code else f"{revision}:"


def split_hs_revision_node_id(node_id: str) -> tuple[str, str]:
    revision, _, code = str(node_id).partition(":")
    return revision, code


def load_hs6_leaf_codes_by_revision() -> dict[str, set[str]]:
    by_revision: dict[str, set[str]] = {}
    for revision in HS_REVISION_SEQUENCE:
        path = CLASSIFICATION_RAW / f"{revision}.json"
        codes: set[str] = set()
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            for row in payload.get("results", []):
                code = normalize_digit_code(row.get("id"), digits=6)
                if code and str(row.get("isLeaf")) == "1" and code not in EXCLUDED_HS6_CODES:
                    codes.add(code)
        by_revision[revision] = codes
    return by_revision


def lt_hgl_weight_url(file_id: int) -> str:
    return f"https://dataverse.harvard.edu/api/access/datafile/{int(file_id)}"


def lt_hgl_weight_file_path(spec: dict[str, object]) -> Path:
    return LT_HGL_WEIGHT_RAW / str(spec["filename"])


def file_md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_lt_hgl_weight_files() -> list[Path]:
    paths: list[Path] = []
    LT_HGL_WEIGHT_RAW.mkdir(parents=True, exist_ok=True)
    for spec in LT_HGL_HS_BACKWARD_SPECS:
        path = lt_hgl_weight_file_path(spec)
        download_reference_file(lt_hgl_weight_url(int(spec["dataverse_file_id"])), path)
        observed_md5 = file_md5(path)
        expected_md5 = str(spec["md5"])
        if observed_md5.lower() != expected_md5.lower():
            raise RuntimeError(
                f"LT/HGL conversion file checksum mismatch for {path.name}: "
                f"expected {expected_md5}, observed {observed_md5}."
            )
        paths.append(path)
    return paths


def lt_hgl_source_column(source_label: str) -> str:
    return f"source_hs{source_label.replace('HS', '')[-2:].lower()}"


def lt_hgl_target_column(target_label: str) -> str:
    return f"target_hs{target_label.replace('HS', '')[-2:].lower()}"


def load_lt_hgl_adjacent_weights(spec: dict[str, object], codes_by_revision: dict[str, set[str]] | None = None) -> pd.DataFrame:
    path = lt_hgl_weight_file_path(spec)
    if not path.exists():
        ensure_lt_hgl_weight_files()
    source_revision = str(spec["source_revision"])
    target_revision = str(spec["target_revision"])
    source_label = str(spec["source_label"])
    target_label = str(spec["target_label"])
    source_col = lt_hgl_source_column(source_label)
    target_col = lt_hgl_target_column(target_label)
    raw = pd.read_csv(path, dtype=str)
    missing_cols = {source_col, target_col, "weight"} - set(raw.columns)
    if missing_cols:
        raise RuntimeError(f"LT/HGL file {path.name} is missing columns: {sorted(missing_cols)}")
    weights = pd.DataFrame(
        {
            "source_classification_code": source_revision,
            "source_cmd_code": raw[source_col].map(lambda value: normalize_digit_code(value, digits=6)),
            "target_classification_code": target_revision,
            "target_cmd_code": raw[target_col].map(lambda value: normalize_digit_code(value, digits=6)),
            "weight": pd.to_numeric(raw["weight"], errors="coerce"),
            "source_file": path.name,
            "source_dataset_doi": LT_HGL_DATASET_DOI,
            "source_dataset_version": LT_HGL_DATASET_VERSION,
            "source_dataverse_file_id": int(spec["dataverse_file_id"]),
            "source_file_md5": str(spec["md5"]),
        }
    )
    weights = weights.replace({"": np.nan}).dropna(subset=["source_cmd_code", "target_cmd_code", "weight"]).copy()
    weights = weights[~weights["source_cmd_code"].isin(EXCLUDED_HS6_CODES)].copy()
    weights = weights[~weights["target_cmd_code"].isin(EXCLUDED_HS6_CODES)].copy()
    if weights.empty:
        raise RuntimeError(f"LT/HGL file {path.name} produced no usable HS6 weights.")

    grouped_sums = weights.groupby("source_cmd_code", observed=True)["weight"].sum()
    bad = grouped_sums[(grouped_sums - 1.0).abs() > LT_HGL_RAW_WEIGHT_TOLERANCE]
    if not bad.empty:
        examples = bad.head(10).to_dict()
        raise RuntimeError(f"LT/HGL file {path.name} has source-code weights far from 1 before normalization: {examples}")

    raw_sum = weights.groupby("source_cmd_code", observed=True)["weight"].transform("sum")
    weights["weight"] = weights["weight"] / raw_sum
    weights = weights[weights["weight"] > 0].copy()
    if codes_by_revision is None:
        codes_by_revision = load_hs6_leaf_codes_by_revision()
    source_codes = set(codes_by_revision.get(source_revision, set()))
    target_codes = set(codes_by_revision.get(target_revision, set()))
    mapped_sources = set(weights["source_cmd_code"].dropna().astype(str))
    identity_codes = sorted((source_codes & target_codes) - mapped_sources - EXCLUDED_HS6_CODES)
    if identity_codes:
        identity = pd.DataFrame(
            {
                "source_classification_code": source_revision,
                "source_cmd_code": identity_codes,
                "target_classification_code": target_revision,
                "target_cmd_code": identity_codes,
                "weight": 1.0,
                "source_file": path.name,
                "source_dataset_doi": LT_HGL_DATASET_DOI,
                "source_dataset_version": LT_HGL_DATASET_VERSION,
                "source_dataverse_file_id": int(spec["dataverse_file_id"]),
                "source_file_md5": str(spec["md5"]),
            }
        )
        weights = pd.concat([weights, identity], ignore_index=True)

    return (
        weights.groupby(
            [
                "source_classification_code",
                "source_cmd_code",
                "target_classification_code",
                "target_cmd_code",
                "source_file",
                "source_dataset_doi",
                "source_dataset_version",
                "source_dataverse_file_id",
                "source_file_md5",
            ],
            as_index=False,
            observed=True,
        )["weight"]
        .sum()
        .sort_values(["source_classification_code", "source_cmd_code", "target_cmd_code"])
        .reset_index(drop=True)
    )


def validate_lt_hgl_conversion_weights(weights: pd.DataFrame, label: str) -> dict[str, object]:
    if weights.empty:
        raise RuntimeError(f"{label} is empty.")
    sums = weights.groupby(["source_classification_code", "source_cmd_code"], observed=True)["weight"].sum()
    bad = sums[(sums - 1.0).abs() > LT_HGL_WEIGHT_TOLERANCE]
    if not bad.empty:
        examples = {f"{idx[0]}:{idx[1]}": float(value) for idx, value in bad.head(10).items()}
        raise RuntimeError(f"{label} has source-code weights that do not sum to 1: {examples}")
    dupes = weights.duplicated(["source_classification_code", "source_cmd_code", "target_classification_code", "target_cmd_code"])
    if dupes.any():
        examples = weights.loc[
            dupes,
            ["source_classification_code", "source_cmd_code", "target_classification_code", "target_cmd_code"],
        ].head(10)
        raise RuntimeError(f"{label} has duplicate source-target weights: {examples.to_dict(orient='records')}")
    return {
        "weight_rows": int(len(weights)),
        "source_pairs": int(sums.shape[0]),
        "target_codes": int(weights["target_cmd_code"].nunique()),
        "max_targets_per_source": int(
            weights.groupby(["source_classification_code", "source_cmd_code"], observed=True)["target_cmd_code"].nunique().max()
        ),
        "max_abs_weight_sum_error": float((sums - 1.0).abs().max()),
    }


def validate_lt_hgl_cached_weight_provenance(weights: pd.DataFrame) -> None:
    """Ensure cached LT/HGL weights are the official HS1992/H0 conversion artifact."""
    expected_values = {
        "conversion_method": "lt_hgl_weighted_hs1992",
        "source_dataset_doi": LT_HGL_DATASET_DOI,
        "source_dataset_version": LT_HGL_DATASET_VERSION,
        "target_classification_code": LT_HGL_TARGET_REVISION,
    }
    for column, expected in expected_values.items():
        observed = set(weights[column].dropna().astype(str).unique().tolist())
        if observed != {str(expected)}:
            raise RuntimeError(
                f"Cached LT/HGL HS1992 weights have unexpected {column}: "
                f"expected {expected!r}, observed {sorted(observed)!r}."
            )
    bad_target_ids = ~weights["target_product_id"].astype(str).str.startswith(f"{LT_HGL_TARGET_LABEL}:")
    if bad_target_ids.any():
        examples = weights.loc[bad_target_ids, "target_product_id"].astype(str).head(10).tolist()
        raise RuntimeError(f"Cached LT/HGL HS1992 weights have unexpected target product ids: {examples}")
    if not LT_HGL_NORMALIZED_WEIGHTS_MANIFEST.exists():
        raise RuntimeError(f"Cached LT/HGL weights are missing manifest: {LT_HGL_NORMALIZED_WEIGHTS_MANIFEST}")
    manifest = json.loads(LT_HGL_NORMALIZED_WEIGHTS_MANIFEST.read_text(encoding="utf-8"))
    manifest_expected = {
        "conversion_method": "lt_hgl_weighted_hs1992",
        "source_dataset_doi": LT_HGL_DATASET_DOI,
        "source_dataset_version": LT_HGL_DATASET_VERSION,
        "target_classification_code": LT_HGL_TARGET_REVISION,
        "target_classification_label": LT_HGL_TARGET_LABEL,
    }
    for key, expected in manifest_expected.items():
        observed = manifest.get(key)
        if str(observed) != str(expected):
            raise RuntimeError(
                f"Cached LT/HGL manifest has unexpected {key}: expected {expected!r}, observed {observed!r}."
            )
    summary = manifest.get("summary") or {}
    if int(summary.get("weight_rows") or -1) != int(len(weights)):
        raise RuntimeError(
            "Cached LT/HGL manifest row count does not match parquet: "
            f"manifest={summary.get('weight_rows')!r}, parquet={len(weights)!r}."
        )
    ensure_lt_hgl_weight_files()
    for spec in LT_HGL_HS_BACKWARD_SPECS:
        path = lt_hgl_weight_file_path(spec)
        observed_md5 = file_md5(path)
        expected_md5 = str(spec["md5"])
        if observed_md5.lower() != expected_md5.lower():
            raise RuntimeError(
                f"Cached LT/HGL raw file checksum mismatch for {path.name}: "
                f"expected {expected_md5}, observed {observed_md5}."
            )


@lru_cache(maxsize=1)
def load_lt_hgl_hs1992_conversion_weights() -> pd.DataFrame:
    required = {
        "source_classification_code",
        "source_cmd_code",
        "target_classification_code",
        "target_cmd_code",
        "target_product_id",
        "weight",
        "conversion_method",
        "source_dataset_doi",
        "source_dataset_version",
    }
    if LT_HGL_NORMALIZED_WEIGHTS_PATH.exists():
        cached = pd.read_parquet(LT_HGL_NORMALIZED_WEIGHTS_PATH)
        if required.issubset(cached.columns):
            validate_lt_hgl_conversion_weights(cached, "cached LT/HGL HS1992 conversion weights")
            validate_lt_hgl_cached_weight_provenance(cached)
            return cached

    ensure_lt_hgl_weight_files()
    codes_by_revision = load_hs6_leaf_codes_by_revision()
    conversions: dict[str, pd.DataFrame] = {}
    h0_codes = sorted(codes_by_revision.get(LT_HGL_TARGET_REVISION, set()) - EXCLUDED_HS6_CODES)
    conversions[LT_HGL_TARGET_REVISION] = pd.DataFrame(
        {
            "source_classification_code": LT_HGL_TARGET_REVISION,
            "source_cmd_code": h0_codes,
            "target_classification_code": LT_HGL_TARGET_REVISION,
            "target_cmd_code": h0_codes,
            "weight": 1.0,
            "source_file": "identity_hs1992",
            "source_dataset_doi": LT_HGL_DATASET_DOI,
            "source_dataset_version": LT_HGL_DATASET_VERSION,
            "source_dataverse_file_id": pd.NA,
            "source_file_md5": "",
        }
    )
    validate_lt_hgl_conversion_weights(conversions[LT_HGL_TARGET_REVISION], "LT/HGL H0 identity weights")

    for spec in LT_HGL_HS_BACKWARD_SPECS:
        source_revision = str(spec["source_revision"])
        target_revision = str(spec["target_revision"])
        adjacent = load_lt_hgl_adjacent_weights(spec, codes_by_revision=codes_by_revision)
        validate_lt_hgl_conversion_weights(adjacent, f"LT/HGL adjacent {source_revision}->{target_revision} weights")
        previous = conversions[target_revision]
        composed = adjacent.merge(
            previous[
                [
                    "source_cmd_code",
                    "target_cmd_code",
                    "weight",
                    "source_file",
                    "source_dataverse_file_id",
                    "source_file_md5",
                ]
            ].rename(
                columns={
                    "source_cmd_code": "intermediate_cmd_code",
                    "target_cmd_code": "final_target_cmd_code",
                    "weight": "next_weight",
                    "source_file": "next_source_file",
                    "source_dataverse_file_id": "next_source_dataverse_file_id",
                    "source_file_md5": "next_source_file_md5",
                }
            ),
            left_on="target_cmd_code",
            right_on="intermediate_cmd_code",
            how="left",
            validate="many_to_many",
        )
        missing = composed["final_target_cmd_code"].isna()
        if missing.any():
            examples = composed.loc[missing, ["source_classification_code", "source_cmd_code", "target_cmd_code"]].head(10)
            raise RuntimeError(f"Could not compose LT/HGL {source_revision}->HS1992 weights: {examples.to_dict(orient='records')}")
        composed["weight"] = composed["weight"] * composed["next_weight"]
        composed["target_classification_code"] = LT_HGL_TARGET_REVISION
        composed["target_cmd_code"] = composed["final_target_cmd_code"]
        composed["source_file"] = composed["source_file"].astype(str) + "|" + composed["next_source_file"].astype(str)
        composed["source_dataverse_file_id"] = (
            composed["source_dataverse_file_id"].astype(str) + "|" + composed["next_source_dataverse_file_id"].astype(str)
        )
        composed["source_file_md5"] = composed["source_file_md5"].astype(str) + "|" + composed["next_source_file_md5"].astype(str)
        keep = [
            "source_classification_code",
            "source_cmd_code",
            "target_classification_code",
            "target_cmd_code",
            "source_file",
            "source_dataset_doi",
            "source_dataset_version",
            "source_dataverse_file_id",
            "source_file_md5",
        ]
        conversion = (
            composed.groupby(keep, as_index=False, observed=True)["weight"]
            .sum()
            .query("weight > 0")
            .sort_values(["source_classification_code", "source_cmd_code", "target_cmd_code"])
            .reset_index(drop=True)
        )
        conversions[source_revision] = conversion
        validate_lt_hgl_conversion_weights(conversion, f"LT/HGL composed {source_revision}->HS1992 weights")

    all_weights = pd.concat([conversions[revision] for revision in HS_REVISION_SEQUENCE], ignore_index=True)
    all_weights["conversion_method"] = "lt_hgl_weighted_hs1992"
    all_weights["target_product_id"] = "HS1992:" + all_weights["target_cmd_code"].astype(str)
    all_weights = all_weights[
        [
            "source_classification_code",
            "source_cmd_code",
            "target_classification_code",
            "target_cmd_code",
            "target_product_id",
            "weight",
            "conversion_method",
            "source_file",
            "source_dataset_doi",
            "source_dataset_version",
            "source_dataverse_file_id",
            "source_file_md5",
        ]
    ].reset_index(drop=True)
    summary = validate_lt_hgl_conversion_weights(all_weights, "LT/HGL HS1992 all-revision weights")
    LT_HGL_NORMALIZED_WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    all_weights.to_parquet(LT_HGL_NORMALIZED_WEIGHTS_PATH, index=False)
    all_weights.to_csv(LT_HGL_NORMALIZED_WEIGHTS_CSV, index=False)
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_dataset_doi": LT_HGL_DATASET_DOI,
        "source_dataset_url": LT_HGL_DATASET_URL,
        "source_dataset_version": LT_HGL_DATASET_VERSION,
        "target_classification_code": LT_HGL_TARGET_REVISION,
        "target_classification_label": LT_HGL_TARGET_LABEL,
        "conversion_method": "lt_hgl_weighted_hs1992",
        "official_weight_specs": LT_HGL_HS_BACKWARD_SPECS,
        "summary": summary,
        "outputs": {
            "parquet": str(LT_HGL_NORMALIZED_WEIGHTS_PATH.relative_to(ROOT)),
            "csv": str(LT_HGL_NORMALIZED_WEIGHTS_CSV.relative_to(ROOT)),
        },
    }
    LT_HGL_NORMALIZED_WEIGHTS_MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return all_weights


def lt_hgl_hs1992_coverage(values: pd.DataFrame, weights: pd.DataFrame | None = None) -> dict[str, object]:
    if values.empty:
        return {
            "lt_hgl_distinct_source_pairs": 0,
            "lt_hgl_missing_distinct_source_pairs": 0,
            "lt_hgl_missing_rows": 0,
            "lt_hgl_missing_trade_value": 0.0,
            "lt_hgl_weighted_target_pairs": 0,
        }
    weights = load_lt_hgl_hs1992_conversion_weights() if weights is None else weights
    keys = weights[["source_classification_code", "source_cmd_code"]].drop_duplicates()
    work = values[["classification_code", "cmd_code", "trade_value"]].copy()
    work["classification_code"] = work["classification_code"].map(normalize_hs_classification_code).replace("", "UNKNOWN")
    work["cmd_code"] = work["cmd_code"].map(lambda value: normalize_digit_code(value, digits=6))
    work["trade_value"] = pd.to_numeric(work["trade_value"], errors="coerce").fillna(0.0)
    work = drop_excluded_hs6(work)
    joined = work.merge(
        keys.assign(_lt_hgl_match=True),
        left_on=["classification_code", "cmd_code"],
        right_on=["source_classification_code", "source_cmd_code"],
        how="left",
        validate="many_to_one",
    )
    missing = joined["_lt_hgl_match"].isna()
    return {
        "lt_hgl_distinct_source_pairs": int(work[["classification_code", "cmd_code"]].drop_duplicates().shape[0]),
        "lt_hgl_missing_distinct_source_pairs": int(joined.loc[missing, ["classification_code", "cmd_code"]].drop_duplicates().shape[0]),
        "lt_hgl_missing_rows": int(missing.sum()),
        "lt_hgl_missing_trade_value": float(joined.loc[missing, "trade_value"].sum()),
        "lt_hgl_weighted_target_pairs": int(weights[["target_classification_code", "target_cmd_code"]].drop_duplicates().shape[0]),
    }


def apply_lt_hgl_hs1992_conversion(
    values: pd.DataFrame,
    weights: pd.DataFrame | None = None,
    value_col: str = "trade_value",
) -> pd.DataFrame:
    if values.empty:
        out = values.copy()
        out["classification_code"] = LT_HGL_TARGET_REVISION
        out["cmd_code"] = pd.Series(dtype="string")
        out["product_id"] = pd.Series(dtype="string")
        return out
    weights = load_lt_hgl_hs1992_conversion_weights() if weights is None else weights
    work = values.copy()
    work["classification_code"] = work["classification_code"].map(normalize_hs_classification_code).replace("", "UNKNOWN")
    work["cmd_code"] = work["cmd_code"].map(lambda value: normalize_digit_code(value, digits=6))
    work = work.dropna(subset=["cmd_code"]).copy()
    work = drop_excluded_hs6(work)
    work[value_col] = pd.to_numeric(work[value_col], errors="coerce")
    work = work.dropna(subset=[value_col]).copy()
    if work.empty:
        return pd.DataFrame(columns=list(values.columns) + ["product_id", "conversion_weight"])
    converted = work.merge(
        weights[
            [
                "source_classification_code",
                "source_cmd_code",
                "target_classification_code",
                "target_cmd_code",
                "target_product_id",
                "weight",
                "conversion_method",
            ]
        ],
        left_on=["classification_code", "cmd_code"],
        right_on=["source_classification_code", "source_cmd_code"],
        how="left",
        validate="many_to_many",
    )
    missing = converted["target_cmd_code"].isna()
    if missing.any():
        examples = converted.loc[missing, ["classification_code", "cmd_code"]].drop_duplicates().head(10).to_dict(orient="records")
        missing_value = float(converted.loc[missing, value_col].sum())
        raise RuntimeError(
            f"LT/HGL HS1992 conversion is missing source codes with {missing_value:,.2f} trade value: {examples}"
        )
    converted["conversion_weight"] = pd.to_numeric(converted["weight"], errors="coerce")
    converted[value_col] = converted[value_col] * converted["conversion_weight"]
    converted["source_classification_code_original"] = converted["classification_code"]
    converted["source_cmd_code_original"] = converted["cmd_code"]
    converted["classification_code"] = converted["target_classification_code"]
    converted["cmd_code"] = converted["target_cmd_code"]
    converted["product_id"] = converted["target_product_id"]
    converted = converted[converted[value_col] > 0].copy()
    drop_cols = [
        "source_classification_code",
        "source_cmd_code",
        "target_classification_code",
        "target_cmd_code",
        "target_product_id",
        "weight",
    ]
    return converted.drop(columns=[col for col in drop_cols if col in converted.columns])


def _combine_wco_code_words(words: list[dict]) -> list[tuple[float, str]]:
    tokens: list[tuple[float, str]] = []
    idx = 0
    while idx < len(words):
        word = words[idx]
        text = str(word.get("text", "")).strip()
        next_text = str(words[idx + 1].get("text", "")).strip() if idx + 1 < len(words) else ""
        if text.lower() == "ex" and idx + 1 < len(words):
            tokens.append((float(word.get("x0", 0.0)), "ex" + next_text))
            idx += 2
            continue
        if re.fullmatch(r"(?i)ex\d{3}", text.replace(" ", "")) and idx + 1 < len(words):
            tokens.append((float(word.get("x0", 0.0)), text + next_text))
            idx += 2
            continue
        if re.fullmatch(r"\d{4}", text) and idx + 1 < len(words) and re.fullmatch(r"\.\d{2}", next_text):
            tokens.append((float(word.get("x0", 0.0)), text + next_text))
            idx += 2
            continue
        tokens.append((float(word.get("x0", 0.0)), text))
        idx += 1

    codes: list[tuple[float, str]] = []
    for x0, token in tokens:
        code = re.sub(r"(?i)^ex", "", token)
        code = re.sub(r"\D", "", code)
        if len(code) == 6 and code not in EXCLUDED_HS6_CODES:
            codes.append((x0, code))
    return codes


def parse_wco_correlation_pdf(path: Path) -> list[tuple[str, str]]:
    try:
        import pdfplumber
    except ImportError:
        print("WARNING: pdfplumber is unavailable; WCO HS correlation PDFs cannot be parsed.", flush=True)
        return []

    edges: list[tuple[str, str]] = []
    current_source_code: str | None = None
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            lines: dict[int, list[dict]] = {}
            for word in page.extract_words(x_tolerance=1, y_tolerance=3, keep_blank_chars=False):
                text = str(word.get("text", ""))
                if not any(char.isdigit() for char in text) and text.lower() != "ex":
                    continue
                line_key = int(round(float(word.get("top", 0.0)) / 2) * 2)
                lines.setdefault(line_key, []).append(word)
            midpoint = float(page.width) / 2.0
            for _line_key, words in sorted(lines.items()):
                codes = _combine_wco_code_words(sorted(words, key=lambda item: float(item.get("x0", 0.0))))
                left_codes = [code for x0, code in codes if x0 < midpoint]
                right_codes = [code for x0, code in codes if x0 >= midpoint]
                if left_codes:
                    current_source_code = left_codes[-1]
                    edges.extend((current_source_code, target_code) for target_code in right_codes)
                elif right_codes and current_source_code is not None:
                    edges.extend((current_source_code, target_code) for target_code in right_codes)
    return sorted(set(edges))


def load_wco_hs_revision_edges() -> list[dict[str, str]]:
    edges: list[dict[str, str]] = []
    for spec in HS_WCO_CORRELATION_SPECS:
        source_revision = spec["source_revision"]
        target_revision = spec["target_revision"]
        destination = HS_HARMONIZATION_RAW / f"{source_revision}_{target_revision}_wco_table_ii.pdf"
        try:
            path = download_reference_file(spec["url"], destination)
            for source_code, target_code in parse_wco_correlation_pdf(path):
                edges.append(
                    {
                        "source_revision": source_revision,
                        "source_code": source_code,
                        "target_revision": target_revision,
                        "target_code": target_code,
                        "edge_source": spec["source_label"],
                    }
                )
        except Exception as exc:
            print(f"WARNING: Could not load {spec['source_label']}: {exc}", flush=True)
    return edges


def normalize_hs_edge(edge: object) -> dict[str, str]:
    if isinstance(edge, dict):
        source_revision = normalize_hs_classification_code(edge.get("source_revision"))
        target_revision = normalize_hs_classification_code(edge.get("target_revision"))
        source_code = normalize_digit_code(edge.get("source_code"), digits=6)
        target_code = normalize_digit_code(edge.get("target_code"), digits=6)
        edge_source = str(edge.get("edge_source") or "manual_test_edge")
    else:
        values = tuple(edge)  # type: ignore[arg-type]
        if len(values) == 4:
            source_revision, source_code, target_revision, target_code = values
            edge_source = "manual_test_edge"
        elif len(values) >= 5:
            source_revision, source_code, target_revision, target_code, edge_source = values[:5]
        else:
            raise ValueError(f"Invalid HS harmonization edge: {edge}")
        source_revision = normalize_hs_classification_code(source_revision)
        target_revision = normalize_hs_classification_code(target_revision)
        source_code = normalize_digit_code(source_code, digits=6)
        target_code = normalize_digit_code(target_code, digits=6)
        edge_source = str(edge_source)
    if not source_revision or not target_revision or not source_code or not target_code:
        raise ValueError(f"Invalid HS harmonization edge: {edge}")
    return {
        "source_revision": source_revision,
        "source_code": source_code,
        "target_revision": target_revision,
        "target_code": target_code,
        "edge_source": edge_source,
    }


def build_hs_harmonized_family_mapping_from_edges(
    edges: Iterable[object],
    codes_by_revision: dict[str, set[str]] | None = None,
    max_family_nodes: int = HS_HARMONIZATION_MAX_FAMILY_NODES,
) -> pd.DataFrame:
    codes_by_revision = codes_by_revision or load_hs6_leaf_codes_by_revision()
    parent: dict[str, str] = {}

    def find(node: str) -> str:
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    edge_records: list[tuple[str, str, str]] = []
    for revision, codes in codes_by_revision.items():
        revision = normalize_hs_classification_code(revision)
        for code in codes:
            code = normalize_digit_code(code, digits=6)
            if code and code not in EXCLUDED_HS6_CODES:
                parent.setdefault(f"{revision}:{code}", f"{revision}:{code}")

    for revision_idx in range(len(HS_REVISION_SEQUENCE) - 1):
        source_revision = HS_REVISION_SEQUENCE[revision_idx]
        target_revision = HS_REVISION_SEQUENCE[revision_idx + 1]
        for code in codes_by_revision.get(source_revision, set()) & codes_by_revision.get(target_revision, set()):
            left = f"{source_revision}:{code}"
            right = f"{target_revision}:{code}"
            union(left, right)
            edge_records.append((left, right, "unchanged_hs6_code"))

    for raw_edge in edges:
        edge = normalize_hs_edge(raw_edge)
        if edge["source_code"] in EXCLUDED_HS6_CODES or edge["target_code"] in EXCLUDED_HS6_CODES:
            continue
        left = f"{edge['source_revision']}:{edge['source_code']}"
        right = f"{edge['target_revision']}:{edge['target_code']}"
        union(left, right)
        edge_records.append((left, right, edge["edge_source"]))

    components: dict[str, list[str]] = {}
    for node in list(parent):
        components.setdefault(find(node), []).append(node)

    component_sources: dict[str, set[str]] = {root: set() for root in components}
    for left, right, source in edge_records:
        component_sources.setdefault(find(left), set()).add(source)
        component_sources.setdefault(find(right), set()).add(source)

    rows = []
    for root, nodes in components.items():
        nodes = sorted(nodes)
        revisions = sorted({split_hs_revision_node_id(node)[0] for node in nodes})
        sources = sorted(component_sources.get(root, set()))
        source_node_count = len(nodes)
        oversized = source_node_count > max_family_nodes
        contains_wco = any(source.startswith("WCO ") for source in sources)
        if oversized:
            status = "ambiguous_oversized_component"
        elif contains_wco:
            status = "matched_wco_correlation"
        elif len(revisions) > 1:
            status = "matched_unchanged_hs6_code"
        else:
            status = "single_revision_reference"

        family_id = f"HSF:{nodes[0].replace(':', '_')}"
        for node in nodes:
            revision, code = split_hs_revision_node_id(node)
            analysis_family_id = f"HSF_UNMATCHED:{revision}_{code}" if oversized else family_id
            rows.append(
                {
                    "classification_code": revision,
                    "classification_label": HS_REVISION_LABELS.get(revision, revision),
                    "cmd_code": code,
                    "harmonized_product_id": analysis_family_id,
                    "harmonization_status": status,
                    "harmonization_source": "|".join(sources) if sources else "classification_reference_singleton",
                    "source_component_id": family_id,
                    "source_component_node_count": int(source_node_count),
                    "analysis_family_node_count": 1 if oversized else int(source_node_count),
                    "source_revision_count": int(len(revisions)),
                    "max_family_nodes": int(max_family_nodes),
                    "harmonization_version": f"{HS_HARMONIZATION_VERSION}_{max_family_nodes}",
                }
            )
    return pd.DataFrame(rows).sort_values(["classification_code", "cmd_code"]).reset_index(drop=True)


@lru_cache(maxsize=1)
def load_hs_harmonized_family_mapping() -> pd.DataFrame:
    required = {
        "classification_code",
        "cmd_code",
        "harmonized_product_id",
        "harmonization_status",
        "harmonization_source",
        "source_component_node_count",
        "analysis_family_node_count",
        "harmonization_version",
    }
    expected_version = f"{HS_HARMONIZATION_VERSION}_{HS_HARMONIZATION_MAX_FAMILY_NODES}"
    if HS_HARMONIZATION_MAPPING_PATH.exists():
        cached = pd.read_csv(HS_HARMONIZATION_MAPPING_PATH, dtype=str)
        if required.issubset(cached.columns) and set(cached["harmonization_version"].dropna().unique()) == {expected_version}:
            for col in ["source_component_node_count", "analysis_family_node_count", "source_revision_count", "max_family_nodes"]:
                if col in cached.columns:
                    cached[col] = pd.to_numeric(cached[col], errors="coerce")
            return cached
    mapping = build_hs_harmonized_family_mapping_from_edges(load_wco_hs_revision_edges())
    HS_HARMONIZATION_MAPPING_PATH.parent.mkdir(parents=True, exist_ok=True)
    mapping.to_csv(HS_HARMONIZATION_MAPPING_PATH, index=False)
    return mapping


def hs_harmonization_lookup(mapping: pd.DataFrame | None = None) -> pd.DataFrame:
    mapping = load_hs_harmonized_family_mapping() if mapping is None else mapping.copy()
    if mapping.empty:
        return pd.DataFrame(
            columns=[
                "classification_code",
                "cmd_code",
                "harmonized_product_id",
                "harmonization_status",
                "harmonization_source",
                "source_component_node_count",
                "analysis_family_node_count",
            ]
        )
    lookup = mapping.copy()
    lookup["classification_code"] = lookup["classification_code"].map(normalize_hs_classification_code).replace("", "UNKNOWN")
    lookup["cmd_code"] = lookup["cmd_code"].map(lambda value: normalize_digit_code(value, digits=6))
    return lookup.dropna(subset=["classification_code", "cmd_code"]).drop_duplicates(subset=["classification_code", "cmd_code"], keep="last")


def attach_hs_harmonized_product_id(values: pd.DataFrame, mapping: pd.DataFrame | None = None) -> pd.DataFrame:
    if values.empty:
        return values.copy()
    out = values.copy()
    lookup = hs_harmonization_lookup(mapping)
    if lookup.empty:
        out["harmonized_product_id"] = "HSF_UNMATCHED:" + out["classification_code"].astype(str) + "_" + out["cmd_code"].astype(str)
        out["harmonization_status"] = "unmatched_no_mapping_available"
        out["harmonization_source"] = "unmatched_no_mapping_available"
        out["source_component_node_count"] = np.nan
        out["analysis_family_node_count"] = 1
        return out
    out = out.merge(
        lookup[
            [
                "classification_code",
                "cmd_code",
                "harmonized_product_id",
                "harmonization_status",
                "harmonization_source",
                "source_component_node_count",
                "analysis_family_node_count",
            ]
        ],
        on=["classification_code", "cmd_code"],
        how="left",
    )
    missing = out["harmonized_product_id"].isna()
    out.loc[missing, "harmonized_product_id"] = (
        "HSF_UNMATCHED:" + out.loc[missing, "classification_code"].astype(str) + "_" + out.loc[missing, "cmd_code"].astype(str)
    )
    out.loc[missing, "harmonization_status"] = "unmatched_not_in_reference"
    out.loc[missing, "harmonization_source"] = "unmatched_not_in_reference"
    out.loc[missing, "analysis_family_node_count"] = 1
    return out


EX12_TOP_DEFINITIONS = ("top_10", "top_1pct", "top_5pct")
EX12_PRODUCT_ITEM_ID_MODES = ("hs6_harmonized_family", "hs6_revision", "hs4", "hs2", "cpa")
EX12_HEADLINE_PRODUCT_ITEM_ID_MODE = "hs6_harmonized_family"
EX12_WIDE_PAIR_MERGE_MAX_STATE_ROWS = int(os.getenv("EX12_WIDE_PAIR_MERGE_MAX_STATE_ROWS", "3000000"))
EX12_LOW_BASE_VALUE_USD = float(os.getenv("EX12_LOW_BASE_VALUE_USD", "10000"))
EX12_LEAST_TRADED_BASE_SHARE = float(os.getenv("EX12_LEAST_TRADED_BASE_SHARE", "0.10"))


def exercise_12_headline_mask(df: pd.DataFrame) -> pd.Series:
    if df.empty or not {"dimension", "item_id_mode", "top_definition"}.issubset(df.columns):
        return pd.Series(False, index=df.index)
    return (
        (df["top_definition"] == "top_10")
        & (
            ((df["dimension"] == "partner") & (df["item_id_mode"] == "partner"))
            | (
                df["dimension"].isin(["product", "product_partner_cell"])
                & (df["item_id_mode"] == EX12_HEADLINE_PRODUCT_ITEM_ID_MODE)
            )
        )
    )


def exercise_12_headline_decomposition(df: pd.DataFrame) -> pd.DataFrame:
    return df.loc[exercise_12_headline_mask(df)].copy() if not df.empty else df


def top_cutoff_count(active_items: int, top_definition: str) -> int:
    if active_items <= 0:
        return 0
    if top_definition == "top_10":
        return min(10, active_items)
    if top_definition == "top_1pct":
        return max(1, int(math.ceil(active_items * 0.01)))
    if top_definition == "top_5pct":
        return max(1, int(math.ceil(active_items * 0.05)))
    raise ValueError(f"Unknown top definition: {top_definition}")


def load_btige_cpa_mapping() -> pd.DataFrame:
    path = OECD_ICIO_RAW / "OECD-Bilateral-Trade-in-Goods-End-use-Conversion-Key.xlsx"
    if not path.exists():
        return pd.DataFrame(columns=["classification_code", "cmd_code", "cpa_code"])
    raw = pd.read_excel(path, sheet_name=0, dtype=str)
    raw = normalize_columns(raw)
    hs_version_col = pick_col(raw, ["HS-version", "hs_version"])
    hs_code_col = pick_col(raw, ["HS-code", "hs_code", "cmd_code"])
    cpa_col = pick_col(raw, ["CPA", "cpa_code"])
    mapping = pd.DataFrame(
        {
            "classification_code": "H" + pd.to_numeric(raw[hs_version_col], errors="coerce").astype("Int64").astype(str),
            "cmd_code": raw[hs_code_col].map(lambda value: normalize_digit_code(value, digits=6)),
            "cpa_code": raw[cpa_col].astype(str).str.strip(),
        }
    )
    mapping = mapping.replace({"": np.nan, "H<NA>": np.nan}).dropna(subset=["classification_code", "cmd_code", "cpa_code"])
    counts = mapping.groupby(["classification_code", "cmd_code"])["cpa_code"].nunique().reset_index(name="cpa_count")
    mapping = mapping.merge(counts, on=["classification_code", "cmd_code"], how="left")
    mapping = mapping[mapping["cpa_count"] == 1].drop(columns=["cpa_count"]).drop_duplicates()
    return mapping


def exercise_12_item_modes_for_dimension(dimension: str) -> tuple[str, ...]:
    return ("partner",) if dimension == "partner" else EX12_PRODUCT_ITEM_ID_MODES


def prepare_exercise_12_item_values(
    values: pd.DataFrame,
    dimension: str,
    item_id_mode: str,
    cpa_mapping: pd.DataFrame | None = None,
    hs_family_mapping: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if values.empty:
        return pd.DataFrame(columns=["reporter_code", "year", "item_id", "trade_value"])
    out = values.copy()
    out["reporter_code"] = pd.to_numeric(out["reporter_code"], errors="coerce")
    out["year"] = pd.to_numeric(out["year"], errors="coerce")
    out["trade_value"] = pd.to_numeric(out["trade_value"], errors="coerce")
    out = out.dropna(subset=["reporter_code", "year", "trade_value"])
    if out.empty:
        return pd.DataFrame(columns=["reporter_code", "year", "item_id", "trade_value"])
    out["reporter_code"] = out["reporter_code"].astype(int)
    out["year"] = out["year"].astype(int)

    if dimension == "partner":
        out["partner_code"] = pd.to_numeric(out["partner_code"], errors="coerce")
        out = out.dropna(subset=["partner_code"])
        out["item_id"] = "partner:" + out["partner_code"].astype(int).astype(str)
    else:
        if "classification_code" not in out.columns:
            out["classification_code"] = ""
        out["classification_code"] = out["classification_code"].map(normalize_hs_classification_code).replace("", "UNKNOWN")
        out["cmd_code"] = out["cmd_code"].astype(str).str.extract(r"(\d{6})", expand=False)
        out = out.dropna(subset=["cmd_code"])
        out = drop_excluded_hs6(out)
        if out.empty:
            return pd.DataFrame(columns=["reporter_code", "year", "item_id", "trade_value"])
        if item_id_mode == "hs6_harmonized_family":
            if hs_family_mapping is not None and "harmonized_product_id" in hs_family_mapping.columns:
                out = attach_hs_harmonized_product_id(out, hs_family_mapping)
                out["product_item_id"] = out["harmonized_product_id"]
            else:
                out = apply_lt_hgl_hs1992_conversion(out, weights=hs_family_mapping)
                out["product_item_id"] = out["product_id"]
        elif item_id_mode == "hs6_revision":
            out["product_item_id"] = out["classification_code"] + ":" + out["cmd_code"]
        elif item_id_mode == "hs4":
            out["product_item_id"] = "HS4:" + out["cmd_code"].str[:4]
        elif item_id_mode == "hs2":
            out["product_item_id"] = "HS2:" + out["cmd_code"].str[:2]
        elif item_id_mode == "cpa":
            mapping = load_btige_cpa_mapping() if cpa_mapping is None else cpa_mapping
            if mapping.empty:
                return pd.DataFrame(columns=["reporter_code", "year", "item_id", "trade_value"])
            out = out.merge(mapping, on=["classification_code", "cmd_code"], how="inner")
            out["product_item_id"] = "CPA:" + out["cpa_code"].astype(str)
        else:
            raise ValueError(f"Unknown Exercise 12 item id mode: {item_id_mode}")
        if dimension == "product":
            out["item_id"] = out["product_item_id"]
        elif dimension == "product_partner_cell":
            out["partner_code"] = pd.to_numeric(out["partner_code"], errors="coerce")
            out = out.dropna(subset=["partner_code"])
            out["item_id"] = out["product_item_id"] + "|partner:" + out["partner_code"].astype(int).astype(str)
        else:
            raise ValueError(f"Unknown Exercise 12 dimension: {dimension}")

    out = out.groupby(["reporter_code", "year", "item_id"], as_index=False)["trade_value"].sum()
    return out[out["trade_value"] > 0].copy()


def exercise_12_year_classifications(values: pd.DataFrame) -> pd.DataFrame:
    if values.empty or "classification_code" not in values.columns:
        return pd.DataFrame(columns=["reporter_code", "year", "classification_code"])
    work = values[["reporter_code", "year", "classification_code"]].copy()
    work["reporter_code"] = pd.to_numeric(work["reporter_code"], errors="coerce")
    work["year"] = pd.to_numeric(work["year"], errors="coerce")
    work["classification_code"] = work["classification_code"].map(normalize_hs_classification_code).replace("", "UNKNOWN")
    work = work.dropna(subset=["reporter_code", "year"]).drop_duplicates()
    out = (
        work.groupby(["reporter_code", "year"])["classification_code"]
        .agg(lambda codes: "|".join(sorted(set(str(code) for code in codes if str(code)))))
        .reset_index()
    )
    out["reporter_code"] = out["reporter_code"].astype(int)
    out["year"] = out["year"].astype(int)
    return out


def exercise_12_allowed_base_years(
    states: pd.DataFrame,
    raw_values: pd.DataFrame,
    dimension: str,
    item_id_mode: str,
    horizon: int,
) -> pd.DataFrame:
    observed_years = states[["reporter_code", "year"]].drop_duplicates()
    future_years = observed_years.copy()
    future_years["year"] = future_years["year"] - horizon
    valid = observed_years.merge(future_years, on=["reporter_code", "year"], how="inner")
    if valid.empty or item_id_mode != "hs6_revision" or dimension == "partner":
        return valid
    classifications = exercise_12_year_classifications(raw_values)
    if classifications.empty:
        return valid
    paired = valid.merge(classifications.rename(columns={"classification_code": "base_classification_code"}), on=["reporter_code", "year"], how="left")
    future_class = classifications.rename(columns={"year": "future_year", "classification_code": "future_classification_code"})
    paired["future_year"] = paired["year"] + horizon
    paired = paired.merge(future_class, on=["reporter_code", "future_year"], how="left")
    paired = paired[paired["base_classification_code"] == paired["future_classification_code"]].copy()
    return paired[["reporter_code", "year"]].drop_duplicates()


def exercise_12_hs_revision_diagnostics(values: pd.DataFrame, dimension: str, horizons: Iterable[int]) -> pd.DataFrame:
    if dimension == "partner" or values.empty:
        return pd.DataFrame()
    classifications = exercise_12_year_classifications(values)
    item_cols = ["cmd_code"] if dimension == "product" else ["cmd_code", "partner_code"]
    work = values.copy()
    for col in item_cols:
        if col not in work.columns:
            return pd.DataFrame()
    work["trade_value"] = pd.to_numeric(work["trade_value"], errors="coerce")
    work = work.dropna(subset=["trade_value"])
    rows = []
    observed = work[["reporter_code", "year"]].drop_duplicates()
    for horizon in horizons:
        valid = observed.copy()
        valid["future_year"] = valid["year"] + horizon
        future = observed.rename(columns={"year": "future_year"})
        valid = valid.merge(future, on=["reporter_code", "future_year"], how="inner")
        if valid.empty:
            continue
        base_class = classifications.rename(columns={"classification_code": "base_classification_code"})
        future_class = classifications.rename(columns={"year": "future_year", "classification_code": "future_classification_code"})
        valid = valid.merge(base_class, on=["reporter_code", "year"], how="left").merge(future_class, on=["reporter_code", "future_year"], how="left")
        invalid = valid[valid["base_classification_code"] != valid["future_classification_code"]].copy()
        for row in invalid.itertuples(index=False):
            base = work[(work["reporter_code"] == row.reporter_code) & (work["year"] == row.year)]
            future_values = work[(work["reporter_code"] == row.reporter_code) & (work["year"] == row.future_year)]
            rows.append(
                {
                    "reporter_code": int(row.reporter_code),
                    "base_year": int(row.year),
                    "future_year": int(row.future_year),
                    "horizon": int(horizon),
                    "dimension": dimension,
                    "item_id_mode": "hs6_revision",
                    "base_classification_code": row.base_classification_code,
                    "future_classification_code": row.future_classification_code,
                    "excluded_base_items": int(base[item_cols].drop_duplicates().shape[0]),
                    "excluded_future_items": int(future_values[item_cols].drop_duplicates().shape[0]),
                    "excluded_base_value": float(base["trade_value"].sum()),
                    "excluded_future_value": float(future_values["trade_value"].sum()),
                }
            )
    return pd.DataFrame(rows)


def exercise_12_hs_harmonization_diagnostics(
    values: pd.DataFrame,
    dimension: str,
    hs_family_mapping: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if dimension == "partner" or values.empty:
        return pd.DataFrame()
    work = values.copy()
    if "classification_code" not in work.columns:
        work["classification_code"] = ""
    if "cmd_code" not in work.columns:
        return pd.DataFrame()
    work["reporter_code"] = pd.to_numeric(work["reporter_code"], errors="coerce")
    work["year"] = pd.to_numeric(work["year"], errors="coerce")
    work["trade_value"] = pd.to_numeric(work["trade_value"], errors="coerce")
    work["classification_code"] = work["classification_code"].map(normalize_hs_classification_code).replace("", "UNKNOWN")
    work["cmd_code"] = work["cmd_code"].astype(str).str.extract(r"(\d{6})", expand=False)
    work = work.dropna(subset=["reporter_code", "year", "trade_value", "cmd_code"])
    work = drop_excluded_hs6(work)
    if work.empty:
        return pd.DataFrame()
    work["reporter_code"] = work["reporter_code"].astype(int)
    if hs_family_mapping is None or "harmonized_product_id" not in hs_family_mapping.columns:
        weights = load_lt_hgl_hs1992_conversion_weights() if hs_family_mapping is None else hs_family_mapping
        key_lookup = weights[["source_classification_code", "source_cmd_code"]].drop_duplicates()
        target_lookup = weights[
            ["source_classification_code", "source_cmd_code", "target_product_id"]
        ].drop_duplicates()
        matched = work.merge(
            key_lookup.assign(_lt_hgl_match=True),
            left_on=["classification_code", "cmd_code"],
            right_on=["source_classification_code", "source_cmd_code"],
            how="left",
            validate="many_to_one",
        )
        matched["node_id"] = matched["classification_code"] + ":" + matched["cmd_code"]
        matched["is_unmatched"] = matched["_lt_hgl_match"].isna()
        rows = []
        targets = work[["reporter_code", "classification_code", "cmd_code"]].drop_duplicates().merge(
            target_lookup,
            left_on=["classification_code", "cmd_code"],
            right_on=["source_classification_code", "source_cmd_code"],
            how="left",
        )
        target_counts = (
            weights.groupby(["source_classification_code", "source_cmd_code"], observed=True)["target_product_id"]
            .nunique()
            .reset_index(name="lt_hgl_target_count")
        )
        target_distribution = (
            work[["reporter_code", "classification_code", "cmd_code"]]
            .drop_duplicates()
            .merge(
                target_counts,
                left_on=["classification_code", "cmd_code"],
                right_on=["source_classification_code", "source_cmd_code"],
                how="left",
            )
        )
        for reporter_code, group in matched.groupby("reporter_code", sort=True):
            total_value = float(group["trade_value"].sum())
            observed_codes = int(group["node_id"].nunique())
            unmatched_value = float(group.loc[group["is_unmatched"], "trade_value"].sum())
            unmatched_codes = int(group.loc[group["is_unmatched"], "node_id"].nunique())
            reporter_targets = targets[targets["reporter_code"].eq(reporter_code)]
            rows.append(
                {
                    "diagnostic_type": "coverage",
                    "reporter_code": int(reporter_code),
                    "dimension": dimension,
                    "harmonization_status": "lt_hgl_weighted_hs1992",
                    "source_component_node_count": np.nan,
                    "observed_rows": int(len(group)),
                    "observed_revision_codes": observed_codes,
                    "analysis_families": int(reporter_targets["target_product_id"].dropna().nunique()),
                    "observed_trade_value": total_value,
                    "matched_trade_value": float(total_value - unmatched_value),
                    "unmatched_trade_value": unmatched_value,
                    "ambiguous_trade_value": 0.0,
                    "unmatched_code_share": unmatched_codes / observed_codes if observed_codes else np.nan,
                    "unmatched_value_share": unmatched_value / total_value if total_value else np.nan,
                    "ambiguous_code_share": 0.0,
                    "ambiguous_value_share": 0.0,
                    "collapsed_family_code_share": np.nan,
                    "max_source_component_node_count": np.nan,
                    "old_same_revision_exclusion_comparison": (
                        "LT/HGL weighted conversion to HS1992/H0; official weights from "
                        f"Harvard Dataverse DOI {LT_HGL_DATASET_DOI} v{LT_HGL_DATASET_VERSION}."
                    ),
                }
            )
        family_reporter_code = int(work["reporter_code"].iloc[0]) if work["reporter_code"].nunique() == 1 else np.nan
        for row in (
            target_distribution.groupby("lt_hgl_target_count", dropna=False, as_index=False)
            .agg(observed_revision_codes=("cmd_code", "nunique"))
            .itertuples(index=False)
        ):
            target_count = row.lt_hgl_target_count
            status = "lt_hgl_missing_weight" if pd.isna(target_count) else "lt_hgl_weighted_hs1992"
            rows.append(
                {
                    "diagnostic_type": "family_size_distribution",
                    "reporter_code": family_reporter_code,
                    "dimension": dimension,
                    "harmonization_status": status,
                    "source_component_node_count": target_count,
                    "observed_rows": np.nan,
                    "observed_revision_codes": int(row.observed_revision_codes),
                    "analysis_families": np.nan,
                    "observed_trade_value": np.nan,
                    "matched_trade_value": np.nan,
                    "unmatched_trade_value": np.nan,
                    "ambiguous_trade_value": 0.0,
                    "unmatched_code_share": np.nan,
                    "unmatched_value_share": np.nan,
                    "ambiguous_code_share": 0.0,
                    "ambiguous_value_share": 0.0,
                    "collapsed_family_code_share": np.nan,
                    "max_source_component_node_count": target_count,
                    "old_same_revision_exclusion_comparison": (
                        "LT/HGL weighted conversion to HS1992/H0; source_component_node_count is the "
                        "number of weighted HS1992 targets for an observed source HS6 code."
                    ),
                }
            )
        return pd.DataFrame(rows)

    work = attach_hs_harmonized_product_id(work, hs_family_mapping)
    work["node_id"] = work["classification_code"] + ":" + work["cmd_code"]
    work["is_unmatched"] = work["harmonization_status"].astype(str).str.startswith("unmatched")
    work["is_ambiguous"] = work["harmonization_status"].eq("ambiguous_oversized_component")
    work["is_collapsed_family"] = (
        pd.to_numeric(work["analysis_family_node_count"], errors="coerce").fillna(1) > 1
    )

    rows = []
    for reporter_code, group in work.groupby("reporter_code", sort=True):
        total_value = float(group["trade_value"].sum())
        observed_codes = int(group["node_id"].nunique())
        unmatched_codes = int(group.loc[group["is_unmatched"], "node_id"].nunique())
        ambiguous_codes = int(group.loc[group["is_ambiguous"], "node_id"].nunique())
        rows.append(
            {
                "diagnostic_type": "coverage",
                "reporter_code": int(reporter_code),
                "dimension": dimension,
                "harmonization_status": "all_observed",
                "source_component_node_count": np.nan,
                "observed_rows": int(len(group)),
                "observed_revision_codes": observed_codes,
                "analysis_families": int(group["harmonized_product_id"].nunique()),
                "observed_trade_value": total_value,
                "matched_trade_value": float(group.loc[~group["is_unmatched"] & ~group["is_ambiguous"], "trade_value"].sum()),
                "unmatched_trade_value": float(group.loc[group["is_unmatched"], "trade_value"].sum()),
                "ambiguous_trade_value": float(group.loc[group["is_ambiguous"], "trade_value"].sum()),
                "unmatched_code_share": unmatched_codes / observed_codes if observed_codes else np.nan,
                "unmatched_value_share": float(group.loc[group["is_unmatched"], "trade_value"].sum()) / total_value if total_value else np.nan,
                "ambiguous_code_share": ambiguous_codes / observed_codes if observed_codes else np.nan,
                "ambiguous_value_share": float(group.loc[group["is_ambiguous"], "trade_value"].sum()) / total_value if total_value else np.nan,
                "collapsed_family_code_share": int(group.loc[group["is_collapsed_family"], "node_id"].nunique()) / observed_codes if observed_codes else np.nan,
                "max_source_component_node_count": float(pd.to_numeric(group["source_component_node_count"], errors="coerce").max()),
                "old_same_revision_exclusion_comparison": "See hs_revision_pair_diagnostics.csv; harmonized mode does not drop pairs solely because HS revision changes.",
            }
        )

    family_reporter_code = int(work["reporter_code"].iloc[0]) if work["reporter_code"].nunique() == 1 else np.nan
    family_sizes = (
        work.drop_duplicates(["node_id", "harmonized_product_id", "harmonization_status", "source_component_node_count"])
        .groupby(["harmonization_status", "source_component_node_count"], dropna=False, as_index=False)
        .agg(observed_revision_codes=("node_id", "nunique"), analysis_families=("harmonized_product_id", "nunique"))
    )
    for row in family_sizes.itertuples(index=False):
        rows.append(
            {
                "diagnostic_type": "family_size_distribution",
                "reporter_code": family_reporter_code,
                "dimension": dimension,
                "harmonization_status": row.harmonization_status,
                "source_component_node_count": row.source_component_node_count,
                "observed_rows": np.nan,
                "observed_revision_codes": int(row.observed_revision_codes),
                "analysis_families": int(row.analysis_families),
                "observed_trade_value": np.nan,
                "matched_trade_value": np.nan,
                "unmatched_trade_value": np.nan,
                "ambiguous_trade_value": np.nan,
                "unmatched_code_share": np.nan,
                "unmatched_value_share": np.nan,
                "ambiguous_code_share": np.nan,
                "ambiguous_value_share": np.nan,
                "collapsed_family_code_share": np.nan,
                "max_source_component_node_count": row.source_component_node_count,
                "old_same_revision_exclusion_comparison": "See hs_revision_pair_diagnostics.csv.",
            }
        )
    return pd.DataFrame(rows)


def assign_size_states_for_items(values: pd.DataFrame, top_definition: str) -> pd.DataFrame:
    if values.empty:
        return pd.DataFrame(columns=["reporter_code", "year", "item_id", "trade_value", "rank", "size_state"])
    out = assign_size_state_columns(values)
    out["size_state"] = out[f"size_state_{top_definition}"]
    return out[["reporter_code", "year", "item_id", "trade_value", "rank", "size_state"]].copy()


def assign_size_state_columns(values: pd.DataFrame) -> pd.DataFrame:
    if values.empty:
        return pd.DataFrame()
    out = values.copy()
    out["rank"] = out.groupby(["reporter_code", "year"])["trade_value"].rank(method="first", ascending=False)
    counts = out.groupby(["reporter_code", "year"])["item_id"].transform("count")
    out["active_item_count"] = counts
    for top_definition in EX12_TOP_DEFINITIONS:
        cutoffs = counts.map(lambda count: top_cutoff_count(int(count), top_definition))
        out[f"size_state_{top_definition}"] = np.where(
            out["rank"] <= cutoffs,
            f"large_{top_definition}",
            f"small_active_non_{top_definition}",
        )
    return out


def mark_exercise_12_low_base_items(
    df: pd.DataFrame,
    threshold_share: float = EX12_LEAST_TRADED_BASE_SHARE,
) -> pd.DataFrame:
    """Flag active base-year items in the least-traded base basket.

    The binary approximation includes the threshold-crossing item so every
    country-year with positive base exports has a nonempty least-traded basket.
    """
    if df.empty:
        out = df.copy()
        out["base_least_traded_10pct"] = False
        return out

    out = df.copy()
    out["base_least_traded_10pct"] = False
    positive = out[pd.to_numeric(out["base_value"], errors="coerce").fillna(0.0) > 0].copy()
    if positive.empty:
        return out

    positive["base_value_numeric"] = pd.to_numeric(positive["base_value"], errors="coerce").fillna(0.0)
    positive = positive.sort_values(["reporter_code", "year", "base_value_numeric", "item_id"], kind="mergesort")
    group_cols = ["reporter_code", "year"]
    positive["base_total_for_low_base"] = positive.groupby(group_cols)["base_value_numeric"].transform("sum")
    positive["base_cumulative_before"] = (
        positive.groupby(group_cols)["base_value_numeric"].cumsum() - positive["base_value_numeric"]
    )
    selected = (positive["base_total_for_low_base"] > 0) & (
        positive["base_cumulative_before"] < threshold_share * positive["base_total_for_low_base"]
    )
    out.loc[positive.index[selected], "base_least_traded_10pct"] = True
    return out


def exercise_12_growth_driver_categories(
    df: pd.DataFrame,
    base_state_col: str,
    top_definition: str,
) -> pd.Series:
    base_value = pd.to_numeric(df["base_value"], errors="coerce").fillna(0.0)
    future_value = pd.to_numeric(df["future_value"], errors="coerce").fillna(0.0)
    grew = future_value > base_value
    was_large = (base_value > 0) & df[base_state_col].eq(f"large_{top_definition}")
    least_traded = (
        df["base_least_traded_10pct"].fillna(False).astype(bool)
        if "base_least_traded_10pct" in df.columns
        else pd.Series(False, index=df.index)
    )
    return pd.Series(
        np.select(
            [
                was_large,
                (base_value == 0) & (future_value > 0),
                (base_value > 0) & (base_value < EX12_LOW_BASE_VALUE_USD) & grew,
                (base_value > 0) & least_traded & grew,
                base_value > 0,
            ],
            [
                f"existing_{top_definition}",
                "strict_new_item",
                "low_base_under_10k_grower",
                "least_traded_10pct_grower",
                f"existing_non_{top_definition}",
            ],
            default="no_base_no_future",
        ),
        index=df.index,
    )


def exercise_12_pair_merge_wide(
    states: pd.DataFrame,
    raw_values: pd.DataFrame,
    dimension: str,
    item_id_mode: str,
    horizon: int,
) -> pd.DataFrame:
    valid_base_years = exercise_12_allowed_base_years(states, raw_values, dimension, item_id_mode, horizon)
    if valid_base_years.empty:
        return pd.DataFrame()
    state_cols = [f"size_state_{top_definition}" for top_definition in EX12_TOP_DEFINITIONS]
    base_cols = ["reporter_code", "year", "item_id", "trade_value", "rank", "active_item_count", *state_cols]
    base_rename = {
        "trade_value": "base_value",
        "rank": "base_rank",
        "active_item_count": "base_active_item_count",
        **{col: f"base_{col}" for col in state_cols},
    }
    future_rename = {
        "trade_value": "future_value",
        "rank": "future_rank",
        "active_item_count": "future_active_item_count",
        **{col: f"future_{col}" for col in state_cols},
    }
    base = states.merge(valid_base_years, on=["reporter_code", "year"], how="inner")[base_cols].rename(columns=base_rename)
    future = states[base_cols].copy()
    future["year"] = future["year"] - horizon
    future = future.merge(valid_base_years, on=["reporter_code", "year"], how="inner").rename(columns=future_rename)
    merged = base.merge(future, on=["reporter_code", "year", "item_id"], how="outer")
    merged["base_value"] = merged["base_value"].fillna(0.0)
    merged["future_value"] = merged["future_value"].fillna(0.0)
    merged["future_year"] = merged["year"] + horizon
    return merged


def exercise_12_pair_merge_wide_for_base_year(
    states: pd.DataFrame,
    reporter_code: int,
    base_year: int,
    horizon: int,
) -> pd.DataFrame:
    state_cols = [f"size_state_{top_definition}" for top_definition in EX12_TOP_DEFINITIONS]
    base_cols = ["reporter_code", "year", "item_id", "trade_value", "rank", "active_item_count", *state_cols]
    base_rename = {
        "trade_value": "base_value",
        "rank": "base_rank",
        "active_item_count": "base_active_item_count",
        **{col: f"base_{col}" for col in state_cols},
    }
    future_rename = {
        "trade_value": "future_value",
        "rank": "future_rank",
        "active_item_count": "future_active_item_count",
        **{col: f"future_{col}" for col in state_cols},
    }
    future_year = int(base_year) + int(horizon)
    base = states[(states["reporter_code"] == int(reporter_code)) & (states["year"] == int(base_year))][base_cols].rename(columns=base_rename)
    future = states[(states["reporter_code"] == int(reporter_code)) & (states["year"] == future_year)][base_cols].rename(columns=future_rename)
    if base.empty and future.empty:
        return pd.DataFrame()
    merged = base.merge(future, on=["reporter_code", "item_id"], how="outer")
    merged = merged.drop(columns=[col for col in ["year_x", "year_y"] if col in merged.columns])
    merged["year"] = int(base_year)
    merged["future_year"] = future_year
    merged["base_value"] = merged["base_value"].fillna(0.0)
    merged["future_value"] = merged["future_value"].fillna(0.0)
    return merged


def exercise_12_accounting_from_pair(
    merged: pd.DataFrame,
    dimension: str,
    horizon: int,
    item_id_mode: str,
    top_definition: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if merged.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    work = merged
    base_state_col = f"base_size_state_{top_definition}"
    future_state_col = f"future_size_state_{top_definition}"
    work["net_contribution"] = work["future_value"] - work["base_value"]
    work = mark_exercise_12_low_base_items(work)
    work["driver_category"] = exercise_12_growth_driver_categories(work, base_state_col, top_definition)
    net = work.groupby(["reporter_code", "year", "future_year", "driver_category"], as_index=False).agg(
        contribution=("net_contribution", "sum"),
        base_value=("base_value", "sum"),
        future_value=("future_value", "sum"),
        item_count=("item_id", "nunique"),
    )
    total = net.groupby(["reporter_code", "year", "future_year"], as_index=False)["contribution"].sum().rename(
        columns={"contribution": "total_growth"}
    )
    net = net.merge(total, on=["reporter_code", "year", "future_year"], how="left")
    net["contribution_share"] = net["contribution"] / net["total_growth"].replace(0, np.nan)
    net["dimension"] = dimension
    net["horizon"] = int(horizon)
    net["item_id_mode"] = item_id_mode
    net["top_definition"] = top_definition
    net["accounting_type"] = "net"

    gross_parts = []
    gross_cols = ["reporter_code", "year", "future_year", "item_id", "base_value", "future_value", "net_contribution", base_state_col]
    if "base_least_traded_10pct" in work.columns:
        gross_cols.append("base_least_traded_10pct")
    positive = work.loc[work["net_contribution"] > 0, gross_cols].copy()
    if not positive.empty:
        positive["driver_category"] = exercise_12_growth_driver_categories(positive, base_state_col, top_definition)
        positive["contribution"] = positive["net_contribution"]
        positive["accounting_type"] = "gross_positive"
        gross_parts.append(positive)
    negative = work.loc[work["net_contribution"] < 0, gross_cols].copy()
    if not negative.empty:
        negative["driver_category"] = np.select(
            [
                (negative["future_value"] == 0) & (negative[base_state_col] == f"large_{top_definition}"),
                negative["future_value"] == 0,
                negative[base_state_col] == f"large_{top_definition}",
            ],
            [f"exited_{top_definition}", f"exited_non_{top_definition}", f"shrinking_{top_definition}"],
            default=f"shrinking_non_{top_definition}",
        )
        negative["contribution"] = -negative["net_contribution"]
        negative["accounting_type"] = "gross_contraction"
        gross_parts.append(negative)
    if gross_parts:
        gross = pd.concat(gross_parts, ignore_index=True)
        gross_out = gross.groupby(
            ["reporter_code", "year", "future_year", "driver_category", "accounting_type"],
            as_index=False,
        ).agg(
            contribution=("contribution", "sum"),
            base_value=("base_value", "sum"),
            future_value=("future_value", "sum"),
            item_count=("item_id", "nunique"),
        )
        gross_total = gross_out.groupby(["reporter_code", "year", "future_year", "accounting_type"], as_index=False)[
            "contribution"
        ].sum().rename(columns={"contribution": "total_growth"})
        gross_out = gross_out.merge(gross_total, on=["reporter_code", "year", "future_year", "accounting_type"], how="left")
        gross_out["contribution_share"] = gross_out["contribution"] / gross_out["total_growth"].replace(0, np.nan)
        gross_out["dimension"] = dimension
        gross_out["horizon"] = int(horizon)
        gross_out["item_id_mode"] = item_id_mode
        gross_out["top_definition"] = top_definition
    else:
        gross_out = pd.DataFrame()

    transitions = work[["reporter_code", "year", "future_year", "item_id", "base_value", "future_value", base_state_col, future_state_col]].copy()
    transitions["base_state"] = transitions[base_state_col].fillna("absent")
    transitions["future_state"] = transitions[future_state_col].fillna("absent")
    transition_out = transitions.groupby(
        ["reporter_code", "year", "future_year", "base_state", "future_state"],
        as_index=False,
    ).agg(
        item_count=("item_id", "nunique"),
        base_value_sum=("base_value", "sum"),
        future_value_sum=("future_value", "sum"),
    )
    transition_out["horizon"] = int(horizon)
    transition_out["dimension"] = dimension
    transition_out["item_id_mode"] = item_id_mode
    transition_out["top_definition"] = top_definition
    transition_out["transition_type"] = "size_state"
    return net, gross_out, transition_out


def exercise_12_pair_merge(states: pd.DataFrame, raw_values: pd.DataFrame, dimension: str, item_id_mode: str, horizon: int) -> pd.DataFrame:
    valid_base_years = exercise_12_allowed_base_years(states, raw_values, dimension, item_id_mode, horizon)
    if valid_base_years.empty:
        return pd.DataFrame()
    base = states.merge(valid_base_years, on=["reporter_code", "year"], how="inner").rename(
        columns={"trade_value": "base_value", "rank": "base_rank", "size_state": "base_size_state"}
    )
    future = states[["reporter_code", "year", "item_id", "trade_value", "rank", "size_state"]].copy()
    future["year"] = future["year"] - horizon
    future = future.merge(valid_base_years, on=["reporter_code", "year"], how="inner")
    future = future.rename(
        columns={"trade_value": "future_value", "rank": "future_rank", "size_state": "future_size_state"}
    )
    merged = base.merge(future, on=["reporter_code", "year", "item_id"], how="outer")
    merged["base_value"] = merged["base_value"].fillna(0.0)
    merged["future_value"] = merged["future_value"].fillna(0.0)
    merged["future_year"] = merged["year"] + horizon
    return merged


def growth_decomposition_accounting(
    raw_values: pd.DataFrame,
    dimension: str,
    horizons: Iterable[int],
    item_id_mode: str,
    top_definition: str,
    cpa_mapping: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    item_values = prepare_exercise_12_item_values(raw_values, dimension, item_id_mode, cpa_mapping=cpa_mapping)
    if item_values.empty:
        return pd.DataFrame(), pd.DataFrame()
    states = assign_size_states_for_items(item_values, top_definition)
    net_rows = []
    gross_rows = []
    for horizon in horizons:
        merged = exercise_12_pair_merge(states, raw_values, dimension, item_id_mode, int(horizon))
        if merged.empty:
            continue
        merged["net_contribution"] = merged["future_value"] - merged["base_value"]
        merged = mark_exercise_12_low_base_items(merged)
        merged["driver_category"] = exercise_12_growth_driver_categories(merged, "base_size_state", top_definition)
        net = merged.groupby(["reporter_code", "year", "future_year", "driver_category"], as_index=False).agg(
            contribution=("net_contribution", "sum"),
            base_value=("base_value", "sum"),
            future_value=("future_value", "sum"),
            item_count=("item_id", "nunique"),
        )
        total = net.groupby(["reporter_code", "year", "future_year"], as_index=False)["contribution"].sum().rename(columns={"contribution": "total_growth"})
        net = net.merge(total, on=["reporter_code", "year", "future_year"], how="left")
        net["contribution_share"] = net["contribution"] / net["total_growth"].replace(0, np.nan)
        net["dimension"] = dimension
        net["horizon"] = int(horizon)
        net["item_id_mode"] = item_id_mode
        net["top_definition"] = top_definition
        net["accounting_type"] = "net"
        net_rows.append(net)

        positive = merged[merged["net_contribution"] > 0].copy()
        if not positive.empty:
            positive["driver_category"] = exercise_12_growth_driver_categories(positive, "base_size_state", top_definition)
            positive["contribution"] = positive["net_contribution"]
            positive["accounting_type"] = "gross_positive"
            gross_rows.append(positive)
        negative = merged[merged["net_contribution"] < 0].copy()
        if not negative.empty:
            negative["driver_category"] = np.select(
                [
                    (negative["future_value"] == 0) & (negative["base_size_state"] == f"large_{top_definition}"),
                    negative["future_value"] == 0,
                    negative["base_size_state"] == f"large_{top_definition}",
                ],
                [f"exited_{top_definition}", f"exited_non_{top_definition}", f"shrinking_{top_definition}"],
                default=f"shrinking_non_{top_definition}",
            )
            negative["contribution"] = -negative["net_contribution"]
            negative["accounting_type"] = "gross_contraction"
            gross_rows.append(negative)

    net_out = pd.concat(net_rows, ignore_index=True) if net_rows else pd.DataFrame()
    if gross_rows:
        gross = pd.concat(gross_rows, ignore_index=True)
        gross_out = gross.groupby(
            ["reporter_code", "year", "future_year", "driver_category", "accounting_type"],
            as_index=False,
        ).agg(
            contribution=("contribution", "sum"),
            base_value=("base_value", "sum"),
            future_value=("future_value", "sum"),
            item_count=("item_id", "nunique"),
        )
        gross_total = gross_out.groupby(["reporter_code", "year", "future_year", "accounting_type"], as_index=False)["contribution"].sum().rename(
            columns={"contribution": "total_growth"}
        )
        gross_out = gross_out.merge(gross_total, on=["reporter_code", "year", "future_year", "accounting_type"], how="left")
        gross_out["contribution_share"] = gross_out["contribution"] / gross_out["total_growth"].replace(0, np.nan)
        gross_out["dimension"] = dimension
        gross_out["horizon"] = gross_out["future_year"] - gross_out["year"]
        gross_out["item_id_mode"] = item_id_mode
        gross_out["top_definition"] = top_definition
    else:
        gross_out = pd.DataFrame()
    return net_out, gross_out


def transition_matrix_detailed(
    raw_values: pd.DataFrame,
    dimension: str,
    horizons: Iterable[int],
    item_id_mode: str,
    top_definition: str,
    transition_type: str = "size_state",
    cpa_mapping: pd.DataFrame | None = None,
) -> pd.DataFrame:
    item_values = prepare_exercise_12_item_values(raw_values, dimension, item_id_mode, cpa_mapping=cpa_mapping)
    if item_values.empty:
        return pd.DataFrame()
    states = assign_size_states_for_items(item_values, top_definition)
    rows = []
    for horizon in horizons:
        merged = exercise_12_pair_merge(states, raw_values, dimension, item_id_mode, int(horizon))
        if merged.empty:
            continue
        merged["base_state"] = merged["base_size_state"].fillna("absent")
        merged["future_state"] = merged["future_size_state"].fillna("absent")
        tab = merged.groupby(["reporter_code", "year", "future_year", "base_state", "future_state"], as_index=False).agg(
            item_count=("item_id", "nunique"),
            base_value_sum=("base_value", "sum"),
            future_value_sum=("future_value", "sum"),
        )
        tab["horizon"] = int(horizon)
        tab["dimension"] = dimension
        tab["item_id_mode"] = item_id_mode
        tab["top_definition"] = top_definition
        tab["transition_type"] = transition_type
        rows.append(tab)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def exercise_12_accounting_outputs_for_values(
    raw_values: pd.DataFrame,
    dimension: str,
    horizons: Iterable[int],
    cpa_mapping: pd.DataFrame | None = None,
    hs_family_mapping: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    net_rows = []
    gross_rows = []
    transition_rows = []
    diagnostic_rows = []
    harmonization_diagnostic_rows = []
    for kind, chunk in iter_exercise_12_accounting_output_chunks(
        raw_values,
        dimension,
        horizons,
        cpa_mapping=cpa_mapping,
        hs_family_mapping=hs_family_mapping,
    ):
        if chunk.empty:
            continue
        if kind == "net":
            net_rows.append(chunk)
        elif kind == "gross":
            gross_rows.append(chunk)
        elif kind == "size_transition":
            transition_rows.append(chunk)
        elif kind == "hs_revision_diagnostics":
            diagnostic_rows.append(chunk)
        elif kind == "hs_harmonization_diagnostics":
            harmonization_diagnostic_rows.append(chunk)
    return (
        pd.concat(net_rows, ignore_index=True) if net_rows else pd.DataFrame(),
        pd.concat(gross_rows, ignore_index=True) if gross_rows else pd.DataFrame(),
        pd.concat(transition_rows, ignore_index=True) if transition_rows else pd.DataFrame(),
        pd.concat(diagnostic_rows, ignore_index=True) if diagnostic_rows else pd.DataFrame(),
        pd.concat(harmonization_diagnostic_rows, ignore_index=True) if harmonization_diagnostic_rows else pd.DataFrame(),
    )


def iter_exercise_12_accounting_output_chunks(
    raw_values: pd.DataFrame,
    dimension: str,
    horizons: Iterable[int],
    cpa_mapping: pd.DataFrame | None = None,
    hs_family_mapping: pd.DataFrame | None = None,
) -> Iterable[tuple[str, pd.DataFrame]]:
    horizons = tuple(int(horizon) for horizon in horizons)
    for item_id_mode in exercise_12_item_modes_for_dimension(dimension):
        diagnostics = exercise_12_hs_revision_diagnostics(raw_values, dimension, horizons) if item_id_mode == "hs6_revision" else pd.DataFrame()
        if not diagnostics.empty:
            yield "hs_revision_diagnostics", diagnostics
        harmonization_diagnostics = (
            exercise_12_hs_harmonization_diagnostics(raw_values, dimension, hs_family_mapping=hs_family_mapping)
            if item_id_mode == "hs6_harmonized_family"
            else pd.DataFrame()
        )
        if not harmonization_diagnostics.empty:
            yield "hs_harmonization_diagnostics", harmonization_diagnostics
        item_values = prepare_exercise_12_item_values(
            raw_values,
            dimension,
            item_id_mode,
            cpa_mapping=cpa_mapping,
            hs_family_mapping=hs_family_mapping,
        )
        if item_values.empty:
            continue
        states = assign_size_state_columns(item_values)
        del item_values
        for horizon in horizons:
            if len(states) <= EX12_WIDE_PAIR_MERGE_MAX_STATE_ROWS:
                paired = exercise_12_pair_merge_wide(states, raw_values, dimension, item_id_mode, horizon)
                if paired.empty:
                    continue
                for top_definition in EX12_TOP_DEFINITIONS:
                    net, gross, transitions = exercise_12_accounting_from_pair(
                        paired,
                        dimension,
                        horizon,
                        item_id_mode,
                        top_definition,
                    )
                    if not net.empty:
                        yield "net", net
                    if not gross.empty:
                        yield "gross", gross
                    if not transitions.empty:
                        yield "size_transition", transitions
                    del net, gross, transitions
                del paired
                gc.collect()
                continue
            valid_base_years = exercise_12_allowed_base_years(states, raw_values, dimension, item_id_mode, horizon)
            if valid_base_years.empty:
                continue
            for valid_row in valid_base_years.itertuples(index=False):
                paired = exercise_12_pair_merge_wide_for_base_year(
                    states,
                    int(valid_row.reporter_code),
                    int(valid_row.year),
                    int(horizon),
                )
                if paired.empty:
                    continue
                for top_definition in EX12_TOP_DEFINITIONS:
                    net, gross, transitions = exercise_12_accounting_from_pair(
                        paired,
                        dimension,
                        horizon,
                        item_id_mode,
                        top_definition,
                    )
                    if not net.empty:
                        yield "net", net
                    if not gross.empty:
                        yield "gross", gross
                    if not transitions.empty:
                        yield "size_transition", transitions
                    del net, gross, transitions
                del paired
                gc.collect()
        del states
        gc.collect()


def assign_size_states(values: pd.DataFrame, dimension: str) -> pd.DataFrame:
    item_cols = item_columns_for_dimension(dimension)
    out = values.copy()
    out["rank"] = out.groupby(["reporter_code", "year"])["trade_value"].rank(method="first", ascending=False)
    out["size_state"] = np.where(out["rank"] <= 10, "large_top_10", "small_active_non_top_10")
    return out[["reporter_code", "year", *item_cols, "trade_value", "rank", "size_state"]].copy()


def transition_matrix(states: pd.DataFrame, item_cols: list[str], state_col: str, horizons: Iterable[int]) -> pd.DataFrame:
    rows = []
    base_cols = ["reporter_code", "year", *item_cols]
    for horizon in horizons:
        observed_years = states[["reporter_code", "year"]].drop_duplicates()
        future_years = observed_years.copy()
        future_years["year"] = future_years["year"] - horizon
        valid_base_years = observed_years.merge(future_years, on=["reporter_code", "year"], how="inner")
        if valid_base_years.empty:
            continue

        base = states.merge(valid_base_years, on=["reporter_code", "year"], how="inner")
        base = base[base_cols + [state_col]].rename(columns={state_col: "base_state"})
        future = states[base_cols + [state_col]].copy()
        future["year"] = future["year"] - horizon
        future = future.merge(valid_base_years, on=["reporter_code", "year"], how="inner")
        future = future.rename(columns={state_col: "future_state"})
        merged = base.merge(future, on=base_cols, how="outer")
        merged["base_state"] = merged["base_state"].fillna("absent")
        merged["future_state"] = merged["future_state"].fillna("absent")
        tab = merged.groupby(["base_state", "future_state"], as_index=False).size()
        tab["horizon"] = horizon
        tab["transition_type"] = state_col
        rows.append(tab)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=["base_state", "future_state", "size", "horizon", "transition_type"]
    )


def growth_decomposition(values: pd.DataFrame, dimension: str, horizons: Iterable[int]) -> pd.DataFrame:
    item_cols = item_columns_for_dimension(dimension)
    states = assign_size_states(values, dimension)
    rows = []
    for horizon in horizons:
        observed_years = states[["reporter_code", "year"]].drop_duplicates()
        future_years = observed_years.copy()
        future_years["year"] = future_years["year"] - horizon
        valid_base_years = observed_years.merge(future_years, on=["reporter_code", "year"], how="inner")
        if valid_base_years.empty:
            continue

        base = states.merge(valid_base_years, on=["reporter_code", "year"], how="inner").rename(
            columns={"trade_value": "base_value", "rank": "base_rank", "size_state": "base_size_state"}
        )
        future = states[["reporter_code", "year", *item_cols, "trade_value"]].copy()
        future["year"] = future["year"] - horizon
        future = future.merge(valid_base_years, on=["reporter_code", "year"], how="inner")
        future = future.rename(columns={"trade_value": "future_value"})
        merged = base.merge(future, on=["reporter_code", "year", *item_cols], how="outer")
        merged["base_value"] = merged["base_value"].fillna(0.0)
        merged["future_value"] = merged["future_value"].fillna(0.0)
        merged["growth_contribution"] = merged["future_value"] - merged["base_value"]
        merged["item_id"] = merged[item_cols].astype(str).agg("|".join, axis=1)
        merged = mark_exercise_12_low_base_items(merged)
        merged["driver_category"] = exercise_12_growth_driver_categories(merged, "base_size_state", "top_10")
        summary = merged.groupby(["reporter_code", "year", "driver_category"], as_index=False).agg(
            contribution=("growth_contribution", "sum"),
            base_value=("base_value", "sum"),
            future_value=("future_value", "sum"),
            item_count=("growth_contribution", "size"),
        )
        totals = summary.groupby(["reporter_code", "year"], as_index=False)["contribution"].sum().rename(
            columns={"contribution": "total_growth"}
        )
        summary = summary.merge(totals, on=["reporter_code", "year"], how="left")
        summary["contribution_share"] = summary["contribution"] / summary["total_growth"].replace(0, np.nan)
        summary["dimension"] = dimension
        summary["horizon"] = horizon
        rows.append(summary)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=[
            "reporter_code",
            "year",
            "driver_category",
            "contribution",
            "base_value",
            "future_value",
            "item_count",
            "total_growth",
            "contribution_share",
            "dimension",
            "horizon",
        ]
    )


def product_scope_states(product_partner: pd.DataFrame) -> pd.DataFrame:
    if product_partner.empty:
        return pd.DataFrame()
    product_partner = product_partner.copy()
    if "classification_code" not in product_partner.columns:
        product_partner["classification_code"] = ""
    product_partner["classification_code"] = product_partner["classification_code"].map(normalize_hs_classification_code).replace("", "UNKNOWN")
    product_partner["cmd_code"] = product_partner["cmd_code"].astype(str).str.extract(r"(\d{6})", expand=False)
    product_partner = product_partner.dropna(subset=["cmd_code"])
    product_partner = drop_excluded_hs6(product_partner)
    if product_partner.empty:
        return pd.DataFrame()
    regions = partner_region_table(product_partner["partner_code"].unique())
    region_lookup = regions.set_index("partner_code")["partner_region"].to_dict() if not regions.empty else {}
    source_lookup = regions.set_index("partner_code")["partner_region_source"].to_dict() if not regions.empty else {}
    product_partner["partner_region"] = product_partner["partner_code"].map(region_lookup).fillna("Unknown")
    product_partner["partner_region_source"] = product_partner["partner_code"].map(source_lookup).fillna("unknown_no_world_bank_match")
    product_partner["unknown_partner_region_value"] = np.where(product_partner["partner_region"] == "Unknown", product_partner["trade_value"], 0.0)
    product_partner["world_bank_partner_region_value"] = np.where(product_partner["partner_region_source"] == "world_bank", product_partner["trade_value"], 0.0)
    scope = product_partner.groupby(["reporter_code", "year", "classification_code", "cmd_code"], as_index=False).agg(
        destination_count=("partner_code", "nunique"),
        partner_region_count=("partner_region", "nunique"),
        partner_region_source_count=("partner_region_source", "nunique"),
        product_export_value=("trade_value", "sum"),
        unknown_partner_region_value=("unknown_partner_region_value", "sum"),
        world_bank_partner_region_value=("world_bank_partner_region_value", "sum"),
    )
    scope["product_identity"] = scope["classification_code"] + ":" + scope["cmd_code"].astype(str)
    scope["unknown_partner_region_share"] = scope["unknown_partner_region_value"] / scope["product_export_value"].replace(0, np.nan)
    scope["world_bank_partner_region_share"] = scope["world_bank_partner_region_value"] / scope["product_export_value"].replace(0, np.nan)
    scope["region_transition_reliability"] = np.where(
        scope["unknown_partner_region_share"] > 0.20,
        "low_unknown_region_gt_20pct",
        "usable_world_bank_region",
    )
    scope["destination_state"] = np.where(scope["destination_count"] <= 1, "single_destination", "multi_destination")
    scope["region_state"] = np.where(scope["partner_region_count"] <= 1, "single_partner_region", "multi_region_global")
    return scope


def run_exercise_12_from_aggregates(
    values_by_dimension: dict[str, pd.DataFrame],
    product_partner: pd.DataFrame,
    source_details: dict | None = None,
) -> pd.DataFrame:
    if not values_by_dimension:
        raise RuntimeError("No Exercise 12 export aggregates were produced.")

    horizons = (5, 10)
    net_rows = []
    gross_rows = []
    transition_rows = []
    diagnostic_rows = []
    harmonization_diagnostic_rows = []
    values_out = []
    cpa_mapping = load_btige_cpa_mapping()
    for dimension, values in values_by_dimension.items():
        values = values.copy()
        values["dimension"] = dimension
        values_out.append(values)
        net, gross, transitions, diagnostics, harmonization_diagnostics = exercise_12_accounting_outputs_for_values(
            values,
            dimension,
            horizons,
            cpa_mapping=cpa_mapping,
        )
        if not net.empty:
            net_rows.append(net)
        if not gross.empty:
            gross_rows.append(gross)
        if not transitions.empty:
            transition_rows.append(transitions)
        if not diagnostics.empty:
            diagnostic_rows.append(diagnostics)
        if not harmonization_diagnostics.empty:
            harmonization_diagnostic_rows.append(harmonization_diagnostics)

    all_values = pd.concat(values_out, ignore_index=True)
    all_values = add_country_metadata(all_values)
    all_values.to_parquet(sample_processed_path("exercise_12_export_aggregates.parquet"), index=False)

    decomposition = pd.concat(net_rows, ignore_index=True) if net_rows else pd.DataFrame()
    gross_decomposition = pd.concat(gross_rows, ignore_index=True) if gross_rows else pd.DataFrame()
    size_transitions = pd.concat(transition_rows, ignore_index=True) if transition_rows else pd.DataFrame()
    hs_diagnostics = pd.concat(diagnostic_rows, ignore_index=True) if diagnostic_rows else pd.DataFrame()
    hs_harmonization_diagnostics = (
        pd.concat(harmonization_diagnostic_rows, ignore_index=True) if harmonization_diagnostic_rows else pd.DataFrame()
    )

    if not decomposition.empty:
        decomposition = add_country_metadata(decomposition)
    if not gross_decomposition.empty:
        gross_decomposition = add_country_metadata(gross_decomposition)
    if not size_transitions.empty:
        size_transitions = add_country_metadata(size_transitions)
    if not hs_diagnostics.empty:
        hs_diagnostics = add_country_metadata(hs_diagnostics)

    main_decomposition = exercise_12_headline_decomposition(decomposition) if not decomposition.empty else decomposition
    decomposition.to_csv(EX12_TABLES / "growth_decomposition_net.csv", index=False)
    gross_decomposition.to_csv(EX12_TABLES / "growth_decomposition_gross.csv", index=False)
    size_transitions.to_csv(EX12_TABLES / "transition_matrices_detailed.csv", index=False)
    hs_diagnostics.to_csv(EX12_TABLES / "hs_revision_pair_diagnostics.csv", index=False)
    hs_harmonization_diagnostics.to_csv(EX12_TABLES / "hs_harmonization_diagnostics.csv", index=False)
    main_decomposition.to_parquet(sample_processed_path("exercise_12_growth_decomposition.parquet"), index=False)
    main_decomposition.to_csv(EX12_TABLES / "growth_decomposition.csv", index=False)
    size_transitions.to_csv(EX12_TABLES / "size_transition_matrices.csv", index=False)

    scope = product_scope_states(product_partner)
    scope_transition_tables = []
    if not scope.empty:
        scope.to_csv(EX12_TABLES / "product_destination_region_states.csv", index=False)
        scope_item_cols = ["product_identity"] if "product_identity" in scope.columns else ["cmd_code"]
        scope_transition_tables.append(transition_matrix(scope, scope_item_cols, "destination_state", horizons))
        scope_transition_tables.append(transition_matrix(scope, scope_item_cols, "region_state", horizons))
    scope_transitions = pd.concat([df for df in scope_transition_tables if not df.empty], ignore_index=True) if any(
        not df.empty for df in scope_transition_tables
    ) else pd.DataFrame(columns=["base_state", "future_state", "size", "horizon", "transition_type"])
    scope_transitions.to_csv(EX12_TABLES / "product_scope_transition_matrices.csv", index=False)

    make_exercise_12_figures(main_decomposition, size_transitions, scope_transitions)
    write_exercise_12_memo(
        main_decomposition,
        size_transitions,
        scope_transitions,
        source_details or {},
        gross_decomposition=gross_decomposition,
        hs_diagnostics=hs_diagnostics,
        hs_harmonization_diagnostics=hs_harmonization_diagnostics,
    )
    return main_decomposition


def run_exercise_12(leaf: pd.DataFrame) -> pd.DataFrame:
    frames, product_partner = exercise_12_export_aggregates_for_leaf(leaf)
    return run_exercise_12_from_aggregates(frames, product_partner, source_details={"mode": "in_memory_leaf"})


def run_exercise_12_streaming(max_files: int | None = None) -> pd.DataFrame:
    files = hs_bulk_files(max_files=max_files)
    if not files:
        raise FileNotFoundError(f"No HS Comtrade bulk files found in {COMTRADE_BULK}")
    values_by_dimension = {"product": [], "partner": [], "product_partner_cell": []}
    product_partner_frames = []
    files_with_rows = 0
    for idx, path in enumerate(files, start=1):
        print(f"[{idx}/{len(files)}] Exercise 12 export transitions from {path.name}", flush=True)
        leaf = extract_leaf_trade(read_comtrade_file(path))
        frames, product_partner = exercise_12_export_aggregates_for_leaf(leaf)
        if frames:
            files_with_rows += 1
            for dimension, frame in frames.items():
                values_by_dimension[dimension].append(frame)
            product_partner_frames.append(product_partner)
    combined = {
        dimension: pd.concat(frames, ignore_index=True)
        for dimension, frames in values_by_dimension.items()
        if frames
    }
    product_partner = pd.concat(product_partner_frames, ignore_index=True) if product_partner_frames else pd.DataFrame()
    decomposition = run_exercise_12_from_aggregates(
        combined,
        product_partner,
        source_details={"mode": "streaming", "hs_bulk_files_processed": len(files), "hs_bulk_files_with_rows": files_with_rows},
    )
    write_json(
        RESULTS / "run_manifest.json",
        {
            "created_at_utc": now_utc(),
            "mode": "exercise_12_streaming",
            "exercise": "12",
            "hs_bulk_files_seen": len(files),
            "hs_bulk_files_with_rows": files_with_rows,
            "rows_decomposition": int(len(decomposition)),
            "exercises_md_updated": False,
        },
    )
    return decomposition


def make_exercise_12_figures(decomposition: pd.DataFrame, size_transitions: pd.DataFrame, scope_transitions: pd.DataFrame) -> None:
    import matplotlib.pyplot as plt
    import seaborn as sns

    sns.set_theme(style="whitegrid")
    if not decomposition.empty:
        summary = decomposition.groupby(["dimension", "horizon", "driver_category"], as_index=False)["contribution_share"].median()
        plt.figure(figsize=(12, 7))
        sns.barplot(data=summary, x="horizon", y="contribution_share", hue="driver_category")
        plt.title("Exercise 12: Median Growth Contribution Share")
        plt.tight_layout()
        plt.savefig(EX12_FIGURES / "median_growth_contribution_share.png", dpi=200)
        plt.close()

    if not size_transitions.empty:
        latest = size_transitions[size_transitions["horizon"] == size_transitions["horizon"].min()]
        value_col = "item_count" if "item_count" in latest.columns else "size"
        pivot = latest.pivot_table(index="base_state", columns="future_state", values=value_col, aggfunc="sum", fill_value=0)
        plt.figure(figsize=(8, 6))
        sns.heatmap(pivot, annot=True, fmt=".0f", cmap="Blues")
        plt.title("Exercise 12: Size Transition Counts")
        plt.tight_layout()
        plt.savefig(EX12_FIGURES / "size_transition_counts.png", dpi=200)
        plt.close()

    if not scope_transitions.empty:
        scope_transitions.groupby(["transition_type", "horizon", "base_state", "future_state"], as_index=False)["size"].sum().to_csv(
            EX12_TABLES / "product_scope_transition_summary.csv", index=False
        )


def write_exercise_12_memo(
    decomposition: pd.DataFrame,
    size_transitions: pd.DataFrame,
    scope_transitions: pd.DataFrame,
    source_details: dict,
    gross_decomposition: pd.DataFrame | None = None,
    hs_diagnostics: pd.DataFrame | None = None,
    hs_harmonization_diagnostics: pd.DataFrame | None = None,
) -> None:
    summary = (
        decomposition.groupby(["dimension", "horizon", "item_id_mode", "top_definition", "driver_category"], as_index=False)["contribution_share"]
        .median()
        .round(4)
        if not decomposition.empty
        else pd.DataFrame()
    )
    gross_headline = (
        exercise_12_headline_decomposition(gross_decomposition)
        if gross_decomposition is not None and not gross_decomposition.empty
        else pd.DataFrame()
    )
    gross_summary = (
        gross_headline.groupby(["dimension", "horizon", "item_id_mode", "top_definition", "accounting_type", "driver_category"], as_index=False)[
            "contribution_share"
        ]
        .median()
        .round(4)
        if not gross_headline.empty
        else pd.DataFrame()
    )
    hs_rows = len(hs_diagnostics) if hs_diagnostics is not None else 0
    hs_harmonization_rows = len(hs_harmonization_diagnostics) if hs_harmonization_diagnostics is not None else 0
    hs_value = (
        float(hs_diagnostics["excluded_base_value"].sum())
        if hs_diagnostics is not None and not hs_diagnostics.empty and "excluded_base_value" in hs_diagnostics.columns
        else 0.0
    )
    gross_all_rows = len(gross_decomposition) if gross_decomposition is not None else 0
    memo = f"""# Exercise 12: Export Transition Exercise

Generated: {now_utc()}

This memo is an accounting exercise, not a regression. It separates where export growth came from: existing top items, strict zero entrants, low-base growers, other existing non-top items, and contractions.

The headline product and product-partner-cell rows use `hs6_harmonized_family + top_10`; partner rows use `partner + top_10`. Other item modes and top definitions remain in the full CSV outputs as diagnostics and robustness checks.

Low-base growth categories are ordered to avoid double counting. `strict_new_item` means base-year value is zero and future value is positive. `low_base_under_10k_grower` means the item was not a base-year top item, had positive base exports below ${EX12_LOW_BASE_VALUE_USD:,.0f}, and grew by the future year. `least_traded_10pct_grower` means the item was not already classified above, was not a base-year top item, belonged to the least-traded base-year basket accounting for the bottom {EX12_LEAST_TRADED_BASE_SHARE:.0%} of base exports, and grew by the future year.

## Coverage

- Growth decomposition rows: {len(decomposition)}
- Size transition rows: {len(size_transitions)}
- Product destination/region transition rows: {len(scope_transitions)}
- HS cross-revision diagnostic rows: {hs_rows}
- HS harmonization diagnostic rows: {hs_harmonization_rows}
- Excluded base value in old same-revision HS diagnostics: {hs_value:,.0f}
- Gross decomposition rows in full CSV: {gross_all_rows}
- Gross decomposition rows in headline memo sample: {len(gross_headline)}
- Source details: `{json.dumps(source_details, sort_keys=True)}`

## Median Net Contribution Shares

{summary.to_markdown(index=False) if not summary.empty else "No contribution summary was produced."}

## Median Gross Contribution Shares

{gross_summary.to_markdown(index=False) if not gross_summary.empty else "No gross contribution summary was produced."}

## Interpretation Limits

The main HS6 product transition now uses the official Harvard Growth Lab / Dataverse weighted conversion tables motivated by Lukaszuk and Torun (2022), "Harmonizing the Harmonized System." Source HS6 revision-code values are multiplied by their LT/HGL conversion weights and aggregated to HS1992/H0 before product-dependent decomposition. HS6 `999999` is excluded before conversion. The old same-revision HS6 diagnostic is retained in `hs_revision_pair_diagnostics.csv` for comparison; harmonization coverage is reported in `hs_harmonization_diagnostics.csv`. HS4, HS2, and CPA-sector outputs are robustness views for product-code instability, not replacements for LT/HGL HS1992 product detail.

Net growth can hide churn, so the gross table should be read alongside the net table. Gross positive growth shows expanding, strict-new, and low-base growing items; gross contraction shows shrinking or exiting items. The median gross table above is filtered to the same headline sample as the net table and keeps `item_id_mode` and `top_definition` visible.

Destination and region transitions remain descriptive. The state table reports `unknown_partner_region_share` and `region_transition_reliability`; region-transition claims should be discounted when the unknown-region share is high.

## Files

- Tables: `{EX12_TABLES.relative_to(ROOT)}/`
- Figures: `{EX12_FIGURES.relative_to(ROOT)}/`
- Processed data: `{sample_processed_path("exercise_12_growth_decomposition.parquet").relative_to(ROOT)}`
- Net decomposition: `{(EX12_TABLES / "growth_decomposition_net.csv").relative_to(ROOT)}`
- Gross decomposition: `{(EX12_TABLES / "growth_decomposition_gross.csv").relative_to(ROOT)}`
- Detailed transitions: `{(EX12_TABLES / "transition_matrices_detailed.csv").relative_to(ROOT)}`
- HS revision diagnostics: `{(EX12_TABLES / "hs_revision_pair_diagnostics.csv").relative_to(ROOT)}`
- HS harmonization diagnostics: `{(EX12_TABLES / "hs_harmonization_diagnostics.csv").relative_to(ROOT)}`

## Discussion Prompt

Does future export growth mostly come from already-top items, strict zero entrants, low-base growers, or other incumbents?
"""
    write_text(sample_results_dir() / "exercise_12_export_transitions.md", memo)


def run_exercise_06(leaf: pd.DataFrame) -> pd.DataFrame:
    panel = save_country_panel()
    outputs, removal_rows = compute_exercise_06_outputs_for_leaf(leaf, panel)
    if not outputs:
        raise RuntimeError("No Exercise 6 rows were produced from the HS6 leaf trade data.")

    out = pd.concat(outputs, ignore_index=True)
    out.to_parquet(sample_processed_path("concentration_exclusions_all_years.parquet"), index=False)
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
    memo = f"""# Exercise 6: Oil / High-Unit-Value Exclusion Tests

Generated: {now_utc()}

This memo is intentionally descriptive. `exercises.md` should only be updated after discussion.

## Exclusion Definitions

- `baseline`: no HS2 product categories are removed.
- `oil_only`: excludes HS27, mineral fuels, oils, petroleum, and related products.
- `oil_aircraft`: excludes HS27 mineral fuels/oil/petroleum and HS88 aircraft/spacecraft.
- `oil_aircraft_precious`: excludes HS27 mineral fuels/oil/petroleum, HS71 precious stones/metals, and HS88 aircraft/spacecraft.
- `full_exclusion`: excludes HS27 mineral fuels/oil/petroleum; HS71 precious stones/metals; HS88 aircraft/spacecraft; HS89 ships/boats/floating structures; and HS93 arms/ammunition.

HS87 vehicles and parts are intentionally not excluded here because the chapter mixes finished autos with parts and is not cleanly a high-unit-value category.

## Median Product Gini And Trade Share Removed

{med.to_markdown()}

## Files

- Tables: `results/exercise_06_tables/`
- Figures: `results/exercise_06_figures/`
- Processed data: `data/processed/concentration_exclusions_all_years.parquet`

## Discussion Prompt

Are oil and high-unit-value/lumpy categories only partial explanations, or do they explain most of the modern concentration pattern?
"""
    write_text(RESULTS / "exercise_06_exclusion_tests.md", memo)


@lru_cache(maxsize=None)
def harmonic_number(n: int) -> float:
    if n <= 0:
        return 0.0
    if n > 10_000:
        return float(math.log(n) + 0.5772156649015329 + (1 / (2 * n)) - (1 / (12 * n * n)))
    return float(np.sum(1.0 / np.arange(1, n + 1, dtype=float)))


def expected_dirichlet_gini(active_items: int) -> float:
    if active_items <= 1:
        return 0.0
    return float((active_items - 1) / (2 * active_items))


def expected_dirichlet_top_share(active_items: int, top_n: int) -> float:
    if active_items <= 0:
        return np.nan
    m = min(top_n, active_items)
    if m == active_items:
        return 1.0
    return float((m / active_items) * (1 + harmonic_number(active_items) - harmonic_number(m)))


def dimension_values_for_benchmark(leaf: pd.DataFrame, dimension: str) -> pd.DataFrame:
    if dimension in {"product", "product_partner_cell"}:
        leaf = drop_excluded_hs6(leaf)
    item_cols = EX10_DIMENSIONS[dimension]
    group_cols = ["reporter_code", "year", "flow", *item_cols]
    return leaf.groupby(group_cols, as_index=False)["trade_value"].sum()


def exercise_10_actual_rows_for_leaf(leaf: pd.DataFrame) -> pd.DataFrame:
    panel = save_country_panel()
    country_meta = panel.set_index("reporter_code")[["country", "iso3"]].to_dict("index")
    group_cols = ["reporter_code", "year", "flow"]
    rows = []

    for dimension in EX10_DIMENSIONS:
        values = dimension_values_for_benchmark(leaf, dimension)
        for key, group in values.groupby(group_cols, sort=True):
            reporter_code, year, flow = key
            actual_values = group["trade_value"].to_numpy(dtype=float)
            meta = country_meta.get(int(reporter_code), {"country": str(reporter_code), "iso3": ""})
            row = {
                "country": meta["country"],
                "iso3": meta["iso3"],
                "reporter_code": int(reporter_code),
                "year": int(year),
                "flow": flow,
                "dimension": dimension,
                "active_items": int(len(actual_values)),
                "total_trade_value": float(np.sum(actual_values)),
                "actual_gini": gini(actual_values),
            }
            for metric, top_n in EX10_TOP_METRICS.items():
                row[f"actual_{metric}"] = top_share(actual_values, n=top_n)
            rows.append(row)

    return pd.DataFrame(rows)


def choose_simulation_counts(
    active_counts: Iterable[int],
    exact_max_items: int,
    grid_size: int,
    max_simulated_items: int,
) -> dict[int, int]:
    unique_counts = sorted({int(count) for count in active_counts if int(count) > 0})
    if not unique_counts:
        return {}

    exact_counts = {count for count in unique_counts if count <= exact_max_items}
    approximate_counts = [count for count in unique_counts if count > exact_max_items]
    simulation_counts = set(exact_counts)

    if approximate_counts:
        capped = np.asarray([min(count, max_simulated_items) for count in approximate_counts], dtype=float)
        if len(set(capped.astype(int))) <= grid_size:
            simulation_counts.update(int(count) for count in capped)
        else:
            quantiles = np.quantile(capped, np.linspace(0, 1, grid_size))
            simulation_counts.update(max(1, int(round(count))) for count in quantiles)
        simulation_counts.add(min(min(approximate_counts), max_simulated_items))
        simulation_counts.add(min(max(approximate_counts), max_simulated_items))

    simulation_counts = sorted(count for count in simulation_counts if count > 0)
    count_map = {}
    for count in unique_counts:
        if count <= exact_max_items:
            count_map[count] = count
            continue
        target = min(count, max_simulated_items)
        count_map[count] = min(simulation_counts, key=lambda candidate: abs(candidate - target))
    return count_map


def simulate_random_allocation_metrics(
    active_items: int,
    simulations: int,
    rng: np.random.Generator,
    max_values_per_batch: int = 5_000_000,
) -> dict[str, np.ndarray]:
    if active_items <= 0:
        empty = np.full(simulations, np.nan)
        return {"gini": empty, **{metric: empty.copy() for metric in EX10_TOP_METRICS}}
    if active_items == 1:
        return {
            "gini": np.zeros(simulations),
            **{metric: np.ones(simulations) for metric in EX10_TOP_METRICS},
        }

    out = {"gini": np.empty(simulations)}
    out.update({metric: np.empty(simulations) for metric in EX10_TOP_METRICS})
    rank_index = np.arange(1, active_items + 1, dtype=float)
    batch_size = max(1, min(simulations, max_values_per_batch // active_items))

    for start in range(0, simulations, batch_size):
        end = min(start + batch_size, simulations)
        batch_n = end - start
        draws = rng.exponential(scale=1.0, size=(batch_n, active_items))
        shares = draws / draws.sum(axis=1, keepdims=True)
        shares.sort(axis=1)
        out["gini"][start:end] = ((2.0 * shares.dot(rank_index)) / active_items) - ((active_items + 1) / active_items)
        for metric, top_n in EX10_TOP_METRICS.items():
            k = min(top_n, active_items)
            out[metric][start:end] = shares[:, -k:].sum(axis=1)

    return out


def adjusted_simulation_metrics(base: dict[str, np.ndarray], active_items: int, simulated_items: int) -> dict[str, np.ndarray]:
    if active_items == simulated_items:
        return {key: value.copy() for key, value in base.items()}

    adjusted = {}
    gini_shift = expected_dirichlet_gini(active_items) - expected_dirichlet_gini(simulated_items)
    adjusted["gini"] = np.clip(base["gini"] + gini_shift, 0, 1)
    for metric, top_n in EX10_TOP_METRICS.items():
        actual_expected = expected_dirichlet_top_share(active_items, top_n)
        simulated_expected = expected_dirichlet_top_share(simulated_items, top_n)
        ratio = actual_expected / simulated_expected if simulated_expected and np.isfinite(simulated_expected) else 1.0
        adjusted[metric] = np.clip(base[metric] * ratio, 0, 1)
    return adjusted


def summarize_random_benchmark(actual: pd.Series, sim: dict[str, np.ndarray]) -> dict:
    row = actual.to_dict()
    for metric in ["gini", *EX10_TOP_METRICS.keys()]:
        actual_value = float(row[f"actual_{metric}"])
        simulated = sim[metric]
        row[f"sim_{metric}_median"] = float(np.nanmedian(simulated))
        row[f"sim_{metric}_p05"] = float(np.nanpercentile(simulated, 5))
        row[f"sim_{metric}_p95"] = float(np.nanpercentile(simulated, 95))
        row[f"actual_{metric}_percentile"] = float(np.nanmean(simulated <= actual_value))
        row[f"actual_minus_sim_median_{metric}"] = float(actual_value - row[f"sim_{metric}_median"])
    return row


def run_exercise_10(
    leaf: pd.DataFrame,
    simulations: int,
    seed: int,
    exact_max_items: int,
    grid_size: int,
    max_simulated_items: int,
) -> pd.DataFrame:
    actual_rows = exercise_10_actual_rows_for_leaf(leaf)
    return run_exercise_10_from_actual_rows(
        actual_rows,
        simulations=simulations,
        seed=seed,
        exact_max_items=exact_max_items,
        grid_size=grid_size,
        max_simulated_items=max_simulated_items,
        source_details={"mode": "in_memory_leaf"},
    )


def run_exercise_10_streaming(
    simulations: int,
    seed: int,
    exact_max_items: int,
    grid_size: int,
    max_simulated_items: int,
    max_files: int | None = None,
) -> pd.DataFrame:
    files = hs_bulk_files()
    if max_files is not None:
        files = files[:max_files]
    if not files:
        raise FileNotFoundError(f"No HS Comtrade bulk files found in {COMTRADE_BULK}")

    part_files = sorted(COMTRADE_BULK.glob("*.part"))
    actual_frames = []
    files_with_rows = 0
    for idx, path in enumerate(files, start=1):
        print(f"[{idx}/{len(files)}] Exercise 10 actual metrics from {path.name}", flush=True)
        raw = read_comtrade_file(path)
        leaf = extract_leaf_trade(raw)
        if not leaf.empty:
            files_with_rows += 1
            actual_frames.append(exercise_10_actual_rows_for_leaf(leaf))

    if not actual_frames:
        raise RuntimeError("No exercise 10 actual concentration rows were produced from HS bulk files.")

    actual_rows = pd.concat(actual_frames, ignore_index=True)
    out = run_exercise_10_from_actual_rows(
        actual_rows,
        simulations=simulations,
        seed=seed,
        exact_max_items=exact_max_items,
        grid_size=grid_size,
        max_simulated_items=max_simulated_items,
        source_details={
            "mode": "streaming",
            "hs_bulk_files_processed": len(files),
            "partial_download_files_present": len(part_files),
            "partial_download_files": [path.name for path in part_files[:20]],
        },
    )
    write_json(
        sample_results_dir() / "run_manifest_exercise_10.json",
        {
            "created_at_utc": now_utc(),
            "mode": "exercise_10_streaming",
            "exercise": "10",
            "country_sample": active_sample_name(),
            "hs_bulk_files_seen": len(files),
            "hs_bulk_files_with_rows": files_with_rows,
            "partial_download_files_present": len(part_files),
            "rows_ex10_actual": int(len(actual_rows)),
            "rows_random_benchmark": int(len(out)),
            "simulations": simulations,
            "seed": seed,
            "benchmark_exact_max_items": exact_max_items,
            "benchmark_grid_size": grid_size,
            "benchmark_max_simulated_items": max_simulated_items,
            "exercises_md_updated": False,
        },
    )
    return out


def run_exercise_10_from_actual_rows(
    actual_rows: pd.DataFrame,
    simulations: int,
    seed: int,
    exact_max_items: int,
    grid_size: int,
    max_simulated_items: int,
    source_details: dict | None = None,
) -> pd.DataFrame:
    if actual_rows.empty:
        raise RuntimeError("No exercise 10 actual rows to benchmark.")

    actual_rows = actual_rows.copy()
    actual_rows.to_csv(EX10_TABLES / "actual_concentration_inputs.csv", index=False)
    count_map = choose_simulation_counts(actual_rows["active_items"], exact_max_items, grid_size, max_simulated_items)
    simulation_counts = sorted(set(count_map.values()))
    rng = np.random.default_rng(seed)
    simulation_cache = {}
    for idx, count in enumerate(simulation_counts, start=1):
        print(f"[{idx}/{len(simulation_counts)}] Simulating random allocation benchmark for active_items={count}", flush=True)
        simulation_cache[count] = simulate_random_allocation_metrics(count, simulations, rng)

    rows = []
    for _, actual in actual_rows.iterrows():
        active_items = int(actual["active_items"])
        simulated_items = int(count_map[active_items])
        sim = adjusted_simulation_metrics(simulation_cache[simulated_items], active_items, simulated_items)
        row = summarize_random_benchmark(actual, sim)
        row["simulations"] = simulations
        row["benchmark_null"] = "symmetric_dirichlet_random_allocation"
        row["simulated_active_items"] = simulated_items
        row["benchmark_approximation"] = active_items != simulated_items
        rows.append(row)

    out = pd.DataFrame(rows)
    out.to_parquet(sample_processed_path("random_benchmark_all_years.parquet"), index=False)
    out.to_csv(EX10_TABLES / "random_benchmark_all_years.csv", index=False)
    make_exercise_10_figures(out)
    write_exercise_10_memo(out)
    validate_benchmark(
        out,
        actual_rows,
        seed=seed,
        simulations=simulations,
        exact_max_items=exact_max_items,
        grid_size=grid_size,
        max_simulated_items=max_simulated_items,
        source_details=source_details or {},
    )
    return out


def make_exercise_10_figures(df: pd.DataFrame) -> None:
    import matplotlib.pyplot as plt
    import seaborn as sns

    sns.set_theme(style="whitegrid")

    for dimension in sorted(df["dimension"].dropna().unique()):
        sub = df[df["dimension"] == dimension]
        safe_dimension = str(dimension).replace(" ", "_")

        med = sub.groupby(["year", "flow"], as_index=False)[["actual_gini", "sim_gini_median"]].median()
        long = med.melt(id_vars=["year", "flow"], var_name="series", value_name="gini")
        plt.figure(figsize=(11, 6))
        sns.lineplot(data=long, x="year", y="gini", hue="series", style="flow", errorbar=None)
        plt.title(f"Actual vs Simulated Median Gini: {dimension}")
        plt.tight_layout()
        plt.savefig(EX10_FIGURES / f"actual_vs_simulated_gini_{safe_dimension}.png", dpi=200)
        plt.close()

        pct = sub.groupby(["year", "flow"], as_index=False)["actual_gini_percentile"].median()
        plt.figure(figsize=(11, 6))
        sns.lineplot(data=pct, x="year", y="actual_gini_percentile", hue="flow", errorbar=None)
        plt.axhline(0.95, color="black", linestyle="--", linewidth=1)
        plt.title(f"Actual Gini Percentile In Benchmark: {dimension}")
        plt.tight_layout()
        plt.savefig(EX10_FIGURES / f"actual_gini_percentile_{safe_dimension}.png", dpi=200)
        plt.close()

    share95 = df.assign(above_95=df["actual_gini_percentile"] >= 0.95).groupby(
        ["year", "flow", "dimension"], as_index=False
    )["above_95"].mean()
    plt.figure(figsize=(12, 7))
    sns.lineplot(data=share95, x="year", y="above_95", hue="dimension", style="flow", errorbar=None)
    plt.title("Share Of Country-Years Above 95th Benchmark Percentile")
    plt.tight_layout()
    plt.savefig(EX10_FIGURES / "share_above_95th_percentile_by_dimension.png", dpi=200)
    plt.close()

    latest_year = int(df["year"].max())
    latest = df[df["year"] == latest_year].copy()
    plt.figure(figsize=(11, 7))
    sns.boxplot(data=latest, x="dimension", y="actual_minus_sim_median_gini", hue="flow")
    plt.axhline(0, color="black", linewidth=0.8)
    plt.title(f"Actual Minus Benchmark Gini In Latest Year ({latest_year})")
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()
    plt.savefig(EX10_FIGURES / "latest_year_actual_minus_benchmark_gini.png", dpi=200)
    plt.close()


def write_exercise_10_memo(df: pd.DataFrame) -> None:
    results_root = sample_results_dir()
    processed_path = sample_processed_path("random_benchmark_all_years.parquet")
    med = df.groupby(["dimension", "flow"])[
        ["actual_gini", "sim_gini_median", "actual_minus_sim_median_gini", "actual_gini_percentile"]
    ].median().round(3)
    share95 = (
        df.assign(above_95=df["actual_gini_percentile"] >= 0.95)
        .groupby(["dimension", "flow"])["above_95"]
        .mean()
        .round(3)
    )
    approximation_share = df.groupby("dimension")["benchmark_approximation"].mean().round(3)
    memo = f"""# Exercise 10: Random Benchmark / Null Model

Generated: {now_utc()}

This memo is intentionally descriptive. `exercises.md` should only be updated after discussion.

## Median Actual Versus Benchmark Measures

```text
{med.to_string()}
```

## Share Of Country-Year-Flow Observations Above 95th Benchmark Percentile

```text
{share95.to_string()}
```

## Share Using Approximate Active-Count Simulation

```text
{approximation_share.to_string()}
```

## Benchmark Design

- Runs separately for products, partners, and product-partner cells.
- Preserves each country-year-flow total trade value.
- Preserves each country-year-flow active item count within the benchmarked dimension.
- Uses a symmetric Dirichlet random-allocation null, implemented as exponential random weights normalized to the observed total.
- Does not use naive relabeling, because relabeling preserves the same Gini by construction.
- Large active-count groups can reuse a nearby/capped simulation count with analytic centering for Gini and top-share expectations; see `{(EX10_TABLES / "benchmark_validation.json").relative_to(ROOT)}`.

## Files

- Tables: `{EX10_TABLES.relative_to(ROOT)}/`
- Figures: `{EX10_FIGURES.relative_to(ROOT)}/`
- Processed data: `{processed_path.relative_to(ROOT)}`

## Discussion Prompt

Is actual concentration still unusually high after preserving scale and sparsity, or is much of it explained by random allocation over a sparse set of active products, partners, and cells?
"""
    write_text(results_root / "exercise_10_random_benchmark.md", memo)


def validate_benchmark(
    out: pd.DataFrame,
    actual_rows: pd.DataFrame,
    seed: int,
    simulations: int,
    exact_max_items: int,
    grid_size: int,
    max_simulated_items: int,
    source_details: dict,
) -> None:
    dimension_summary = (
        out.groupby("dimension")
        .agg(
            rows=("dimension", "size"),
            min_active_items=("active_items", "min"),
            max_active_items=("active_items", "max"),
            approximation_share=("benchmark_approximation", "mean"),
            median_actual_gini_percentile=("actual_gini_percentile", "median"),
        )
        .reset_index()
    )
    check = {
        "created_at_utc": now_utc(),
        "country_sample": active_sample_name(),
        "seed": seed,
        "simulations": simulations,
        "rows": int(len(out)),
        "actual_input_rows": int(len(actual_rows)),
        "actual_gini_percentile_min": float(out["actual_gini_percentile"].min()),
        "actual_gini_percentile_max": float(out["actual_gini_percentile"].max()),
        "exact_max_items": exact_max_items,
        "grid_size": grid_size,
        "max_simulated_items": max_simulated_items,
        "benchmark_null": "symmetric_dirichlet_random_allocation",
        "policy": "Benchmark preserves country-year-flow total trade and active item count by dimension.",
        "source_details": source_details,
        "dimension_summary": dimension_summary.to_dict("records"),
    }
    write_json(EX10_TABLES / "benchmark_validation.json", check)


def load_or_collect_leaf(args: argparse.Namespace) -> pd.DataFrame:
    leaf_path = sample_processed_path("hs6_partner_leaf_trade_all_years.parquet")
    if leaf_path.exists() and not args.reprocess_raw:
        return pd.read_parquet(leaf_path)
    return collect_leaf_data()


def run_selected_exercise_from_leaf(args: argparse.Namespace, leaf: pd.DataFrame) -> None:
    manifest = {
        "created_at_utc": now_utc(),
        "stage": args.stage,
        "mode": "in_memory_leaf",
        "exercise": args.exercise,
        "rows_leaf_trade": int(len(leaf)),
        "simulations": args.simulations,
        "seed": args.seed,
        "benchmark_exact_max_items": args.benchmark_exact_max_items,
        "benchmark_grid_size": args.benchmark_grid_size,
        "benchmark_max_simulated_items": args.benchmark_max_simulated_items,
        "exercises_md_updated": False,
    }

    if args.exercise == "1":
        concentration = run_exercise_01(leaf)
        manifest["rows_concentration"] = int(len(concentration))
    elif args.exercise == "2":
        growth = run_exercise_02(leaf)
        manifest["rows_ex02_growth"] = int(len(growth))
    elif args.exercise == "3":
        concentration = run_exercise_03(leaf)
        manifest["rows_ex03_concentration"] = int(len(concentration))
    elif args.exercise == "4":
        product = run_exercise_04(leaf)
        manifest["rows_ex04_product_supplier"] = int(len(product))
    elif args.exercise == "6":
        exclusions = run_exercise_06(leaf)
        manifest["rows_exclusions"] = int(len(exclusions))
    elif args.exercise == "10":
        benchmark = run_exercise_10(
            leaf,
            simulations=args.simulations,
            seed=args.seed,
            exact_max_items=args.benchmark_exact_max_items,
            grid_size=args.benchmark_grid_size,
            max_simulated_items=args.benchmark_max_simulated_items,
        )
        manifest["rows_random_benchmark"] = int(len(benchmark))
    elif args.exercise == "11":
        exposure = run_exercise_11(leaf)
        manifest["rows_ex11_top_export_input_exposure"] = int(len(exposure))
    elif args.exercise == "12":
        decomposition = run_exercise_12(leaf)
        manifest["rows_ex12_decomposition"] = int(len(decomposition))
    else:
        raise ValueError(f"Unsupported selected exercise: {args.exercise}")

    write_json(RESULTS / "run_manifest.json", manifest)
    mark_exercise_outputs_complete(args.exercise, details=manifest)


def run_all(args: argparse.Namespace) -> None:
    configure_country_sample_from_args(args)
    apply_memory_limit(args.memory_limit_gb)
    ensure_dirs()
    if args.prepare_bec5_mapping_review:
        prepare_bec5_mapping_review()
        return
    if args.approve_bec5_mapping:
        approve_bec5_mapping()
        return
    if args.finalize_only and args.exercise not in {"2", "3", "4", "11"}:
        raise RuntimeError("--finalize-only is only supported with --exercise 2, --exercise 3, --exercise 4, or --exercise 11.")

    save_country_panel()
    if args.stage in {"process", "all"} and can_reuse_exercise_outputs(args) and exercise_outputs_available(args.exercise):
        manifest = {
            "created_at_utc": now_utc(),
            "mode": "skipped_existing_outputs",
            "country_sample": active_sample_name(),
            "exercise": args.exercise,
            "outputs": [str(path.relative_to(ROOT)) for path in exercise_output_paths(args.exercise)],
            "policy": "Existing complete outputs were reused. Use --reprocess-raw, --fresh-checkpoints, or --max-files to force work.",
            "exercises_md_updated": False,
        }
        write_json(RESULTS / "run_manifest.json", manifest)
        print(f"Skipping exercise {args.exercise}: existing outputs are available for sample {active_sample_name()}.", flush=True)
        return

    subscription_key = get_key(args)
    if args.stage in {"download", "all"}:
        local_files = hs_bulk_files(max_files=args.max_files)
        missing_keys = missing_bulk_keys_for_active_sample(local_files)
        if args.stage == "all" and local_files and not missing_keys and not args.refresh_availability:
            print(f"Skipping download: {len(local_files)} matching local Comtrade bulk files are already available.", flush=True)
        else:
            if missing_keys:
                print(f"Need {len(missing_keys)} additional Comtrade bulk files for sample {active_sample_name()}.", flush=True)
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
        if args.stage == "process" and args.max_files is None:
            missing_keys = missing_bulk_keys_for_active_sample()
            if missing_keys:
                examples = [
                    {"reporter_code": reporter_code, "year": year, "classification_code": classification_code}
                    for reporter_code, year, classification_code in sorted(missing_keys)[:25]
                ]
                write_blocker(
                    f"Missing {len(missing_keys)} required Comtrade bulk reporter-year-classification files for "
                    f"country sample {active_sample_name()}; refusing to process a partial sample.",
                    {
                        "country_sample": active_sample_name(),
                        "missing_bulk_file_count": int(len(missing_keys)),
                        "example_missing_keys": examples,
                        "next_step": "Set COMTRADE_SUBSCRIPTION_KEY and run --stage all or --stage download before full processing.",
                    },
                )
                return
        if args.exercise == "all":
            if args.keep_leaf:
                leaf = load_or_collect_leaf(args)
                concentration = run_exercise_01(leaf)
                growth = run_exercise_02(leaf)
                ex03_concentration = run_exercise_03(leaf)
                ex04_product = run_exercise_04(leaf)
                run_exercise_06(leaf)
                benchmark = run_exercise_10(
                    leaf,
                    simulations=args.simulations,
                    seed=args.seed,
                    exact_max_items=args.benchmark_exact_max_items,
                    grid_size=args.benchmark_grid_size,
                    max_simulated_items=args.benchmark_max_simulated_items,
                )
                ex11_exposure = run_exercise_11(leaf)
                decomposition = run_exercise_12(leaf)
                write_json(
                    RESULTS / "run_manifest.json",
                    {
                        "created_at_utc": now_utc(),
                        "stage": args.stage,
                        "mode": "in_memory_leaf",
                        "rows_leaf_trade": int(len(leaf)),
                        "rows_concentration": int(len(concentration)),
                        "rows_ex02_growth": int(len(growth)),
                        "rows_ex03_concentration": int(len(ex03_concentration)),
                        "rows_ex04_product_supplier": int(len(ex04_product)),
                        "rows_random_benchmark": int(len(benchmark)),
                        "rows_ex11_top_export_input_exposure": int(len(ex11_exposure)),
                        "rows_ex12_decomposition": int(len(decomposition)),
                        "simulations": args.simulations,
                        "seed": args.seed,
                        "benchmark_exact_max_items": args.benchmark_exact_max_items,
                        "benchmark_grid_size": args.benchmark_grid_size,
                        "benchmark_max_simulated_items": args.benchmark_max_simulated_items,
                        "exercises_md_updated": False,
                    },
                )
                mark_many_exercises_complete(PIPELINE_EXERCISES, details={"mode": "in_memory_leaf"})
            else:
                run_exercises_streaming(
                    simulations=args.simulations,
                    seed=args.seed,
                    exact_max_items=args.benchmark_exact_max_items,
                    grid_size=args.benchmark_grid_size,
                    max_simulated_items=args.benchmark_max_simulated_items,
                    max_files=args.max_files,
                )
                mark_many_exercises_complete(PIPELINE_EXERCISES, details={"mode": "streaming"})
        elif args.keep_leaf:
            leaf = load_or_collect_leaf(args)
            run_selected_exercise_from_leaf(args, leaf)
        elif args.exercise == "1":
            run_exercise_01_streaming()
            mark_exercise_outputs_complete("1", details={"mode": "exercise_01_streaming"})
        elif args.exercise == "2":
            run_exercise_02_streaming(
                max_files=args.max_files,
                fresh_checkpoints=args.fresh_checkpoints,
                finalize_only=args.finalize_only,
                chunk_rows=args.chunk_rows,
            )
            mark_exercise_outputs_complete("2", details={"mode": "exercise_02_checkpointed"})
        elif args.exercise == "3":
            run_exercise_03_streaming(
                max_files=args.max_files,
                fresh_checkpoints=args.fresh_checkpoints,
                finalize_only=args.finalize_only,
                chunk_rows=args.chunk_rows,
            )
            mark_exercise_outputs_complete("3", details={"mode": "exercise_03_streaming"})
        elif args.exercise == "4":
            run_exercise_04_streaming(
                max_files=args.max_files,
                fresh_checkpoints=args.fresh_checkpoints,
                finalize_only=args.finalize_only,
                chunk_rows=args.chunk_rows,
            )
            mark_exercise_outputs_complete("4", details={"mode": "exercise_04_streaming"})
        elif args.exercise == "6":
            run_exercise_06_streaming()
            mark_exercise_outputs_complete("6", details={"mode": "exercise_06_streaming"})
        elif args.exercise == "10":
            run_exercise_10_streaming(
                simulations=args.simulations,
                seed=args.seed,
                exact_max_items=args.benchmark_exact_max_items,
                grid_size=args.benchmark_grid_size,
                max_simulated_items=args.benchmark_max_simulated_items,
                max_files=args.max_files,
            )
            mark_exercise_outputs_complete("10", details={"mode": "exercise_10_streaming"})
        elif args.exercise == "11":
            run_exercise_11_streaming(
                max_files=args.max_files,
                fresh_checkpoints=args.fresh_checkpoints,
                finalize_only=args.finalize_only,
                chunk_rows=args.chunk_rows,
            )
            mark_exercise_outputs_complete("11", details={"mode": "exercise_11_streaming"})
        elif args.exercise == "12":
            run_exercise_12_streaming(max_files=args.max_files)
            mark_exercise_outputs_complete("12", details={"mode": "exercise_12_streaming"})
        else:
            raise ValueError(f"Unsupported exercise: {args.exercise}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run real-data trade concentration Exercises 1, 2, 3, 4, 6, 10, 11, and 12.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--stage", choices=["download", "process", "all"], default="all")
    parser.add_argument("--exercise", choices=["all", "1", "2", "3", "4", "6", "10", "11", "12"], default="all", help="Exercise to run during the process stage.")
    parser.add_argument(
        "--prepare-bec5-mapping-review",
        action="store_true",
        help="Download official HS/BEC references and write Exercise 3 BEC mapping review/candidate files, without running trade analysis.",
    )
    parser.add_argument(
        "--approve-bec5-mapping",
        action="store_true",
        help="Promote the reviewed Exercise 3 BEC mapping candidate to the approved mapping required by Exercise 3.",
    )
    parser.add_argument("--subscription-key", default=None, help="UN Comtrade subscription key. Defaults to COMTRADE_SUBSCRIPTION_KEY.")
    parser.add_argument("--country-sample", choices=COUNTRY_SAMPLE_CHOICES, default="rd2_countries", help="Reporter sample to use for downloads, raw-file filtering, and country metadata.")
    parser.add_argument(
        "--min-available-years",
        type=int,
        default=10,
        help="Minimum annual HS years required for broad samples. cadot_broad_156 fixes this at 19.",
    )
    parser.add_argument("--start-year", type=int, default=1988, help="Earliest annual HS year included in sample eligibility and raw-file processing.")
    parser.add_argument("--end-year", type=int, default=None, help="Latest annual HS year included in sample eligibility and raw-file processing.")
    parser.add_argument("--refresh-availability", action="store_true", help="Refresh Comtrade reporter and availability metadata instead of using local caches.")
    parser.add_argument("--simulations", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260518)
    parser.add_argument("--max-years-per-country", type=int, default=None, help="Debug option; leave unset for all available years.")
    parser.add_argument("--download-workers", type=int, default=4, help="Parallel Comtrade bulk downloads.")
    parser.add_argument("--max-file-mb", type=float, default=None, help="Download only files at or below this advertised size.")
    parser.add_argument("--min-file-mb", type=float, default=None, help="Download only files at or above this advertised size.")
    parser.add_argument("--reprocess-raw", action="store_true", help="Re-read raw Comtrade files even if processed parquet exists.")
    parser.add_argument("--keep-leaf", action="store_true", help="Store all HS6 partner records in one parquet; off by default to avoid high memory use.")
    parser.add_argument("--max-files", type=int, default=None, help="Debug option for processing; process only the first N HS bulk files.")
    parser.add_argument("--fresh-checkpoints", action="store_true", help="Rebuild Exercise 2/3/4/11 per-file checkpoint parquet files before finalizing.")
    parser.add_argument("--finalize-only", action="store_true", help="Finalize Exercise 2/3/4/11 from existing checkpoint parquet files without reading raw Comtrade files.")
    parser.add_argument("--chunk-rows", type=int, default=DEFAULT_CHUNK_ROWS, help="Raw Comtrade rows per chunk for Exercise 2/3/4/11 checkpoint creation.")
    parser.add_argument("--memory-limit-gb", type=float, default=None, help="Optional process address-space cap to prevent laptop-wide memory exhaustion.")
    parser.add_argument(
        "--benchmark-exact-max-items",
        type=int,
        default=500,
        help="Exercise 10 simulates exact active item counts up to this threshold.",
    )
    parser.add_argument(
        "--benchmark-grid-size",
        type=int,
        default=30,
        help="Exercise 10 approximate grid size for larger active item counts.",
    )
    parser.add_argument(
        "--benchmark-max-simulated-items",
        type=int,
        default=50_000,
        help="Exercise 10 cap for simulated item count before analytic active-count adjustment.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        run_all(args)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
