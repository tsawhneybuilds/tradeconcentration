"""Shared constants and helpers for long-run partner concentration work."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data/raw/historical_trade"
PROCESSED_DIR = ROOT / "data/processed/historical_partner_concentration"
RESULTS_DIR = ROOT / "results/historical_partner_concentration"
FIGURES_DIR = RESULTS_DIR / "figures"

TRADHIST_EXPECTED_ROWS = 2_495_357
TRADHIST_START_YEAR = 1827
TRADHIST_END_YEAR = 2014
WCB_DRAWS = 9_999
TP_BOOTSTRAP_DRAWS = 2_000
BOOTSTRAP_SEED = 20260618
PRIMARY_PARTNER_THRESHOLD = 20
SUPPORTED_MIN_OBSERVATIONS = 60
SUPPORTED_MIN_SIDE_OBSERVATIONS = 10
SUPPORTED_MIN_SIDE_SHARE = 0.10
SUPPORTED_MIN_SIDE_ENTITIES = 3
ENTITY_CLUSTER_COL = "entity_id"
YEAR_COL = "year"
FLOW_EXPORTS = "Exports"
FLOW_IMPORTS = "Imports"
MODEL_INCOME_LEVEL = "gdppc_10k"
MODEL_INCOME_LOG = "log_gdppc"

TRADHIST_DOC_URL = "https://www.cepii.fr/pdf_pub/wp/2016/wp2016-14.pdf"
MPD_DATA_URL = "https://dataverse.nl/api/access/datafile/421302"
MPD_DATASET_URL = "https://dataverse.nl/dataset.xhtml?persistentId=doi:10.34894/INZBF2"

TRADHIST_SOURCE_URLS = {
    "TRADHIST_BITRADE_BITARIFF_1.xlsx": "https://www.cepii.fr/DATA_DOWNLOAD/TRADHIST/TRADHIST_BITRADE_BITARIFF_1.xlsx",
    "TRADHIST_BITRADE_BITARIFF_2.xlsx": "https://www.cepii.fr/DATA_DOWNLOAD/TRADHIST/TRADHIST_BITRADE_BITARIFF_2.xlsx",
    "TRADHIST_BITRADE_BITARIFF_3.xlsx": "https://www.cepii.fr/DATA_DOWNLOAD/TRADHIST/TRADHIST_BITRADE_BITARIFF_3.xlsx",
    "TRADHIST_GRAVITY_COUNTRY_YEAR_SPECIFIC.xlsx": "https://www.cepii.fr/DATA_DOWNLOAD/TRADHIST/TRADHIST_GRAVITY_COUNTRY_YEAR_SPECIFIC.xlsx",
    "TRADHIST_GRAVITY_COUNTRY_SPECIFIC.xlsx": "https://www.cepii.fr/DATA_DOWNLOAD/TRADHIST/TRADHIST_GRAVITY_COUNTRY_SPECIFIC.xlsx",
    "TRADHIST_documentation_wp2016_14.pdf": TRADHIST_DOC_URL,
}

MPD_SOURCE_URLS = {
    "mpd2023_web.xlsx": MPD_DATA_URL,
}

SELECTED_ENTITY_ORDER = [
    "FRA",
    "DNK",
    "SWE",
    "NOR",
    "NLD",
    "ESP",
    "PRT",
    "GBR",
    "USA",
    "ARG",
    "URY",
    "USSR",
    "RUS",
]

EXPECTED_ENTITY_SPANS = {
    "FRA": (1827, 2014),
    "DNK": (1827, 2014),
    "SWE": (1828, 2014),
    "NOR": (1830, 2014),
    "NLD": (1831, 2014),
    "ESP": (1827, 2014),
    "PRT": (1827, 2014),
    "GBR": (1827, 2014),
    "USA": (1827, 2014),
    "ARG": (1827, 2014),
    "URY": (1832, 2014),
    "USSR": (1827, 1991),
    "RUS": (1992, 2014),
}

EXPECTED_ENTITY_INTERIOR_GAPS = {
    "SWE": {1829},
    "URY": {1833, 1834, 1835, 1836},
}

INVALID_PARTNER_CODES = {
    "",
    "0",
    "ALL",
    "ROW",
    "UNK",
    "UNKN",
    "WORLD",
    "WLD",
}


@dataclass(frozen=True)
class EntitySpec:
    entity_id: str
    entity_label: str
    boundary_note: str
    mpd_code_preferred: str


ENTITY_SPECS = {
    "FRA": EntitySpec("FRA", "France", "Stable reporter unit in TRADHIST for the study window.", "FRA"),
    "DNK": EntitySpec("DNK", "Denmark", "Stable reporter unit in TRADHIST for the study window.", "DNK"),
    "SWE": EntitySpec("SWE", "Sweden", "Stable reporter unit in TRADHIST for the study window.", "SWE"),
    "NOR": EntitySpec("NOR", "Norway", "Stable reporter unit in TRADHIST for the study window.", "NOR"),
    "NLD": EntitySpec("NLD", "Netherlands", "Stable reporter unit in TRADHIST for the study window.", "NLD"),
    "ESP": EntitySpec("ESP", "Spain", "Stable reporter unit in TRADHIST for the study window.", "ESP"),
    "PRT": EntitySpec("PRT", "Portugal", "Stable reporter unit in TRADHIST for the study window.", "PRT"),
    "GBR": EntitySpec("GBR", "United Kingdom", "Stable reporter unit in TRADHIST for the study window.", "GBR"),
    "USA": EntitySpec("USA", "United States", "Stable reporter unit in TRADHIST for the study window.", "USA"),
    "ARG": EntitySpec("ARG", "Argentina", "Stable reporter unit in TRADHIST for the study window.", "ARG"),
    "URY": EntitySpec("URY", "Uruguay", "Stable reporter unit in TRADHIST for the study window.", "URY"),
    "USSR": EntitySpec(
        "USSR",
        "Russian Empire/USSR",
        "TRADHIST documents USSR as 'Russian Empire/USSR'; pre-1922 rows refer to predecessor Russian territory and must not be concatenated with RUS.",
        "SUN",
    ),
    "RUS": EntitySpec(
        "RUS",
        "Russian Federation",
        "Russian Federation reporter in TRADHIST from 1992 onward; do not concatenate with USSR in regressions or trends.",
        "RUS",
    ),
}

SOURCE_FAMILY_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^DOTS", re.I), "DOTS"),
    (re.compile(r"^COW$", re.I), "COW"),
    (re.compile(r"^RIC_", re.I), "RICARDO"),
    (re.compile(r"^MITC_", re.I), "MITCHELL"),
    (re.compile(r"COLO", re.I), "Colonial compilation"),
    (re.compile(r"STAT", re.I), "National statistical publication"),
    (re.compile(r"ANNU", re.I), "National statistical publication"),
    (re.compile(r"YEARBOOK|YRBK|BLUEBOOK", re.I), "Yearbook"),
    (re.compile(r"TABLEAU|RAPPORT|RETURNS|REPORT|GAZETEER", re.I), "Official report"),
)


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def relpath(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def ensure_dirs() -> None:
    for path in (RAW_DIR, PROCESSED_DIR, RESULTS_DIR, FIGURES_DIR):
        path.mkdir(parents=True, exist_ok=True)


def json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        if not math.isfinite(float(value)):
            return None
        return float(value)
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if pd_is_na(value):
        return None
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def pd_is_na(value: Any) -> bool:
    try:
        import pandas as pd

        return bool(pd.isna(value))
    except Exception:
        return value is None


def write_json(path: Path, payload: dict[str, Any] | list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=json_default) + "\n", encoding="utf-8")


def sha256sum(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def source_file_manifest(path: Path, url: str) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": relpath(path),
        "url": url,
        "retrieved_at_utc": now_utc(),
        "bytes": int(stat.st_size),
        "sha256": sha256sum(path),
    }


def entity_metadata_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for entity_id in SELECTED_ENTITY_ORDER:
        spec = ENTITY_SPECS[entity_id]
        rows.append(
            {
                "entity_id": spec.entity_id,
                "entity_label": spec.entity_label,
                "boundary_note": spec.boundary_note,
                "mpd_code_preferred": spec.mpd_code_preferred,
            }
        )
    return rows


def mpd_code_for_entity(entity_id: str, year: int) -> str | None:
    if entity_id == "USSR":
        return "SUN" if year <= 1991 else None
    if entity_id == "RUS":
        return "RUS" if year >= 1992 else None
    return entity_id


def boundary_flag(entity_id: str, year: int) -> str:
    if entity_id == "USSR" and year < 1922:
        return "russian_empire_pre_1922"
    if entity_id == "USSR":
        return "ussr_1922_1991"
    if entity_id == "RUS":
        return "russian_federation_1992_2014"
    return "standard"


def source_family(source_tf: str | None) -> str:
    code = (source_tf or "").strip()
    if not code:
        return "Unknown"
    for pattern, label in SOURCE_FAMILY_RULES:
        if pattern.search(code):
            return label
    return "Primary source compilation"


def quality_band(active_partner_count: int) -> str:
    if active_partner_count < 5:
        return "<5"
    if active_partner_count < 10:
        return "5-9"
    if active_partner_count < 20:
        return "10-19"
    return "20+"


def supports_headline(active_partner_count: int) -> bool:
    return active_partner_count >= PRIMARY_PARTNER_THRESHOLD


def finite_nonnegative(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    if numeric < 0:
        raise ValueError(f"Negative value encountered: {numeric}")
    return numeric


def bh_adjust(p_values: Iterable[float | None]) -> list[float | None]:
    pvals = list(p_values)
    out: list[float | None] = [None] * len(pvals)
    indexed = [(idx, float(value)) for idx, value in enumerate(pvals) if value is not None and math.isfinite(float(value))]
    if not indexed:
        return out
    ranked = sorted(indexed, key=lambda item: item[1])
    m = len(ranked)
    adjusted = [0.0] * m
    running = 1.0
    for pos in range(m - 1, -1, -1):
        idx, p = ranked[pos]
        rank = pos + 1
        running = min(running, p * m / rank)
        adjusted[pos] = running
    for (idx, _), q in zip(ranked, adjusted, strict=True):
        out[idx] = min(q, 1.0)
    return out


def two_sided_star(p_value: float | None) -> str:
    if p_value is None or not math.isfinite(float(p_value)):
        return ""
    if p_value < 0.01:
        return "***"
    if p_value < 0.05:
        return "**"
    if p_value < 0.10:
        return "*"
    return ""


def primary_source_paths() -> dict[str, Path]:
    return {name: RAW_DIR / "tradhist" / name for name in TRADHIST_SOURCE_URLS}


def mpd_source_paths() -> dict[str, Path]:
    return {name: RAW_DIR / "maddison" / name for name in MPD_SOURCE_URLS}
