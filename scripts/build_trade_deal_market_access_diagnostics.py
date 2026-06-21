#!/usr/bin/env python3
"""Diagnostics-only setup for trade-deal market-access work.

This script prepares auditable inputs for a future trade-deal/export-
concentration pipeline. It deliberately stops before tariff-product merges,
market-access panels, or regressions. Its job is to make source coverage,
country-code mapping, WITS metadata availability, and HS-revision blockers
visible before any coefficient table can be produced.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from trade_concentration_pipeline import (  # noqa: E402
    HS_REVISION_LABELS,
    LT_HGL_DATASET_DOI,
    LT_HGL_DATASET_VERSION,
    LT_HGL_NORMALIZED_WEIGHTS_PATH,
    load_lt_hgl_hs1992_conversion_weights,
    RD2_COUNTRIES,
)

COUNTRY_SAMPLE = "rd2_countries"
PROCESSED_DIR = ROOT / "data" / "processed" / "samples" / COUNTRY_SAMPLE
RESULTS_DIR = ROOT / "results" / "samples" / COUNTRY_SAMPLE / "trade_deal_market_access"
RAW_AGREEMENTS_DIR = ROOT / "data" / "raw" / "trade_agreements"
RAW_TARIFFS_DIR = ROOT / "data" / "raw" / "tariffs"
WITS_RAW_DIR = RAW_TARIFFS_DIR / "wits_trains"
WITS_METADATA_DIR = WITS_RAW_DIR / "metadata"
WITS_AVAILABILITY_DIR = WITS_RAW_DIR / "availability"
COMTRADE_AGG_DIR = PROCESSED_DIR / "exercise_02_12_file_aggregates"
CONCENTRATION_PATH = PROCESSED_DIR / "concentration_all_years.parquet"
PLAN_PATH = ROOT / "trade_deals_export_concentration_plan.md"
DEFENSIBLE_SAMPLE_PLAN_PATH = ROOT / "trade_deal_defensible_samples_plan.md"
HS_FAMILY_MAPPING_PATH = ROOT / "data" / "processed" / "hs6_harmonized_families.csv"
LT_HGL_WEIGHT_MAPPING_PATH = LT_HGL_NORMALIZED_WEIGHTS_PATH
HS_WCO_CORRELATION_DIR = ROOT / "data" / "raw" / "classifications" / "hs_revision_correlations"
PRIMARY_WITS_TARIFF_SAMPLE_PATH = PROCESSED_DIR / "primary_wits_tariff_sample.parquet"
PRIMARY_WITS_2001_2021_SAMPLE_PATH = PROCESSED_DIR / "primary_wits_2001_2021_sample.parquet"
PRIMARY_WITS_HS4_2001_2021_SAMPLE_PATH = PROCESSED_DIR / "primary_wits_hs4_2001_2021_sample.parquet"
PRIMARY_WITS_HS4_LONG_SAMPLE_PATH = PROCESSED_DIR / "primary_wits_hs4_long_sample.parquet"
AGREEMENT_ONLY_FULL_SAMPLE_PATH = PROCESSED_DIR / "agreement_only_full_sample.parquet"
SUPPLEMENT_CANDIDATE_GAP_YEARS_PATH = PROCESSED_DIR / "supplement_candidate_gap_years.csv"
HS4_BASELINE_HARMONIZATION_COVERAGE_PATH = PROCESSED_DIR / "trade_deal_hs4_baseline_harmonization_coverage.csv"
TARIFF_SAMPLE_ATTRITION_PATH = RESULTS_DIR / "tariff_sample_attrition.md"

WITS_COUNTRY_METADATA_URL = "https://wits.worldbank.org/API/V1/wits/datasource/trn/country/ALL"
WITS_DATAAVAILABILITY_URL = (
    "https://wits.worldbank.org/API/V1/wits/datasource/trn/dataavailability/country/{country}/year/all"
)
WITS_SAMPLE_TARIFF_URL = (
    "https://wits.worldbank.org/API/V1/SDMX/V21/datasource/TRN/reporter/840/"
    "partner/000/product/020110/year/2000/datatype/reported?format=JSON"
)

WITS_DOC_SUPPORTED_HS = {"H0", "H1", "H2", "H3", "H4", "H5"}
EXCLUDED_HS6_CODES = {"999999"}
HS4_HARMONIZATION_COVERAGE_MIN = 0.90
PRIMARY_TARIFF_WEIGHT_COVERAGE_MIN = 0.80
EU_CUSTOMS_TERRITORY_CODE = "918"
EU_CUSTOMS_TERRITORY_ISO3 = "EUN"
EU_CUSTOMS_TERRITORY_NAME = "European Union"
# Values are customs-territory membership years for tariff-schedule purposes.
# The UK uses EUN through the 2020 transition year, then direct GBR from 2021.
EU_MEMBERSHIP_YEARS = {
    "AUT": (1995, None),
    "BEL": (1958, None),
    "BGR": (2007, None),
    "CYP": (2004, None),
    "CZE": (2004, None),
    "DEU": (1958, None),
    "DNK": (1973, None),
    "ESP": (1986, None),
    "EST": (2004, None),
    "FIN": (1995, None),
    "FRA": (1958, None),
    "GBR": (1973, 2020),
    "GRC": (1981, None),
    "HRV": (2013, None),
    "HUN": (2004, None),
    "IRL": (1973, None),
    "ITA": (1958, None),
    "LTU": (2004, None),
    "LUX": (1958, None),
    "LVA": (2004, None),
    "MLT": (2004, None),
    "NLD": (1958, None),
    "POL": (2004, None),
    "PRT": (1986, None),
    "ROU": (2007, None),
    "SVK": (2004, None),
    "SVN": (2004, None),
    "SWE": (1995, None),
}


@dataclass(frozen=True)
class DownloadSpec:
    source: str
    url: str
    output: Path
    required_for_primary: bool = False


SOURCE_DOWNLOADS = [
    DownloadSpec(
        "larch_rta_csv_zip",
        "https://www.ewf.uni-bayreuth.de/pool/dokumente/rta_20260111_csv.zip",
        RAW_AGREEMENTS_DIR / "larch_rta" / "rta_20260111_csv.zip",
        required_for_primary=True,
    ),
    DownloadSpec(
        "desta_indices_v02_03",
        "https://www.designoftradeagreements.org/media/filer_public/0c/64/"
        "0c64ec71-5728-409f-91d8-64c324bf4400/desta_indices_version_02_03.csv",
        RAW_AGREEMENTS_DIR / "desta" / "desta_indices_version_02_03.csv",
        required_for_primary=True,
    ),
    DownloadSpec(
        "desta_treaty_dyads_v02_03",
        "https://www.designoftradeagreements.org/media/filer_public/6a/45/"
        "6a454835-eef1-44c4-8af2-5557a9552167/desta_list_of_treaties_02_03_dyads.csv",
        RAW_AGREEMENTS_DIR / "desta" / "desta_list_of_treaties_02_03_dyads.csv",
        required_for_primary=True,
    ),
    DownloadSpec(
        "desta_content_v02_03",
        "https://www.designoftradeagreements.org/media/filer_public/53/af/"
        "53af422c-29b0-48f9-bf1c-3537f5c028d4/desta_version_02_03.csv",
        RAW_AGREEMENTS_DIR / "desta" / "desta_version_02_03.csv",
        required_for_primary=False,
    ),
    DownloadSpec(
        "world_bank_dta_vertical_v2",
        "https://datacatalogfiles.worldbank.org/ddh-published/0065624/2/DR0093616/"
        "DTA%202.0%20-%20Vertical%20Content%20%28v2%29.xlsx",
        RAW_AGREEMENTS_DIR / "world_bank_dta" / "DTA_2_0_Vertical_Content_v2.xlsx",
        required_for_primary=False,
    ),
]

SOURCE_PAGES = {
    "wits_api_docs": "https://wits.worldbank.org/witsapiintro.aspx?lang=en",
    "wto_tariff_trade_data": "https://ttd.wto.org/en/download",
    "wto_rta_database": "https://data.wto.org/dataset/ext_rta",
    "cepii_macmap_hs6": "https://www.cepii.fr/CEPII/en/bdd_modele/bdd_modele_item.asp?id=12",
    "trade_deal_plan": str(PLAN_PATH),
    "trade_deal_defensible_samples_plan": str(DEFENSIBLE_SAMPLE_PLAN_PATH),
}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_dirs() -> None:
    for path in [
        PROCESSED_DIR,
        RESULTS_DIR,
        WITS_METADATA_DIR,
        WITS_AVAILABILITY_DIR,
        RAW_AGREEMENTS_DIR / "larch_rta",
        RAW_AGREEMENTS_DIR / "desta",
        RAW_AGREEMENTS_DIR / "world_bank_dta",
        RAW_TARIFFS_DIR / "wto_ttd",
        RAW_TARIFFS_DIR / "macmap_hs6",
    ]:
        path.mkdir(parents=True, exist_ok=True)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def source_file_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path.relative_to(ROOT)), "exists": False}
    return {
        "path": str(path.relative_to(ROOT)),
        "exists": True,
        "size_bytes": path.stat().st_size,
        "sha256": file_sha256(path),
        "mtime_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
    }


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def normalize_digit_code(value: Any, digits: int) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "<na>"}:
        return ""
    text = re.sub(r"\.0$", "", text)
    if not text.isdigit():
        text = re.sub(r"\D", "", text)
    if not text:
        return ""
    return text.zfill(digits)


def normalize_wits_country_code(value: Any) -> str:
    return normalize_digit_code(value, digits=3)


def normalize_hs6_code(value: Any) -> str:
    return normalize_digit_code(value, digits=6)


def harmonized_hs4_from_hs6(value: Any) -> str:
    code = normalize_hs6_code(value)
    if len(code) != 6 or code in EXCLUDED_HS6_CODES:
        return ""
    return "HS4:" + code[:4]


def split_semicolon_codes(value: Any) -> set[str]:
    if value is None or pd.isna(value):
        return set()
    return {part.strip().upper() for part in str(value).split(";") if part.strip()}


def request_bytes(url: str, timeout: int) -> tuple[bytes | None, dict[str, Any]]:
    started = time.time()
    try:
        response = requests.get(url, timeout=timeout)
        elapsed = round(time.time() - started, 3)
        info = {
            "url": url,
            "status_code": response.status_code,
            "elapsed_seconds": elapsed,
            "content_type": response.headers.get("content-type", ""),
        }
        if response.ok:
            return response.content, info
        info["error"] = response.text[:500]
        return None, info
    except requests.RequestException as exc:
        return None, {"url": url, "error": repr(exc)}


def download_snapshot(spec: DownloadSpec, refresh: bool, timeout: int) -> dict[str, Any]:
    if spec.output.exists() and not refresh:
        out = {
            "source": spec.source,
            "url": spec.url,
            "downloaded": False,
            "used_existing": True,
            "required_for_primary": spec.required_for_primary,
        }
        out.update(source_file_manifest(spec.output))
        return out

    content, info = request_bytes(spec.url, timeout)
    out = {
        "source": spec.source,
        "url": spec.url,
        "downloaded": False,
        "used_existing": False,
        "required_for_primary": spec.required_for_primary,
        "request": info,
    }
    if content is not None:
        spec.output.parent.mkdir(parents=True, exist_ok=True)
        spec.output.write_bytes(content)
        out["downloaded"] = True
        out.update(source_file_manifest(spec.output))
    return out


def check_url_status(name: str, url: str, timeout: int) -> dict[str, Any]:
    if url.startswith("/"):
        path = Path(url)
        return {"source": name, "url": url, "local_file": True, **source_file_manifest(path)}
    started = time.time()
    try:
        response = requests.get(url, timeout=timeout, stream=True)
        response.close()
        return {
            "source": name,
            "url": url,
            "status_code": response.status_code,
            "elapsed_seconds": round(time.time() - started, 3),
            "content_type": response.headers.get("content-type", ""),
        }
    except requests.RequestException as exc:
        return {"source": name, "url": url, "error": repr(exc)}


def rd2_country_frame() -> pd.DataFrame:
    df = pd.DataFrame([country.__dict__ for country in RD2_COUNTRIES])
    df["reporter_code"] = df["reporter_code"].astype(int)
    df["iso3"] = df["iso3"].astype(str).str.upper()
    df["wits_country_code_candidate"] = df["reporter_code"].map(normalize_wits_country_code)
    df["desta_iso_numeric_candidate"] = df["reporter_code"]
    df["larch_iso3_candidate"] = df["iso3"]
    df["wto_economy_label_candidate"] = df["country"]
    df["cepii_iso3_candidate"] = df["iso3"]
    return df.sort_values("iso3").reset_index(drop=True)


def strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1].lower()


def parse_wits_countries_xml(text: str) -> pd.DataFrame:
    root = ET.fromstring(text.lstrip("\ufeff"))
    rows: list[dict[str, Any]] = []
    for elem in root.iter():
        if strip_ns(elem.tag) != "country":
            continue
        row = {
            "wits_country_code": elem.attrib.get("countrycode", ""),
            "wits_is_reporter": elem.attrib.get("isreporter", ""),
            "wits_is_partner": elem.attrib.get("ispartner", ""),
            "wits_is_group": elem.attrib.get("isgroup", ""),
            "wits_group_type": elem.attrib.get("grouptype", ""),
            "wits_iso3": "",
            "wits_name": "",
            "wits_notes": "",
        }
        for child in elem:
            key = strip_ns(child.tag)
            text_value = (child.text or "").strip()
            if key == "iso3code":
                row["wits_iso3"] = text_value.upper()
            elif key == "name":
                row["wits_name"] = text_value
            elif key == "notes":
                row["wits_notes"] = text_value
        rows.append(row)
    return pd.DataFrame(rows)


def parse_wits_dataavailability_xml(text: str) -> pd.DataFrame:
    root = ET.fromstring(text.lstrip("\ufeff"))
    rows: list[dict[str, Any]] = []
    for elem in root.iter():
        if strip_ns(elem.tag) != "reporter":
            continue
        row = {
            "wits_country_code": elem.attrib.get("countrycode", ""),
            "wits_iso3": elem.attrib.get("iso3Code", "").upper(),
            "wits_is_group": elem.attrib.get("isgroup", ""),
            "wits_group_type": elem.attrib.get("grouptype", ""),
            "wits_name": "",
            "year": None,
            "nomenclature_code": "",
            "nomenclature_name": "",
            "number_of_preferential_agreements": None,
            "partner_list": "",
            "specific_duty_ave_available": "",
            "notes": "",
            "last_updated_date": "",
        }
        for child in elem:
            key = strip_ns(child.tag)
            text_value = (child.text or "").strip()
            if key == "name":
                row["wits_name"] = text_value
            elif key == "year":
                row["year"] = int(text_value) if text_value.isdigit() else None
            elif key == "reporternernomenclature":
                row["nomenclature_code"] = child.attrib.get("reporternernomenclaturecode", "")
                row["nomenclature_name"] = text_value
            elif key == "numberofpreferentialagreement":
                row["number_of_preferential_agreements"] = int(text_value) if text_value.isdigit() else None
            elif key == "partnerlist":
                row["partner_list"] = text_value
            elif key == "isspecificdutyexpressionestimatedavailable":
                row["specific_duty_ave_available"] = text_value
            elif key == "notes":
                row["notes"] = text_value
            elif key == "lastupdateddate":
                row["last_updated_date"] = text_value
        rows.append(row)
    return pd.DataFrame(rows)


def fetch_wits_country_metadata(refresh: bool, timeout: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    path = WITS_METADATA_DIR / "country_all.xml"
    manifest = {"source": "wits_trains_country_metadata", "url": WITS_COUNTRY_METADATA_URL}
    if path.exists() and not refresh:
        text = path.read_text(encoding="utf-8-sig")
        manifest.update({"used_existing": True, **source_file_manifest(path)})
    else:
        content, request_info = request_bytes(WITS_COUNTRY_METADATA_URL, timeout)
        manifest["request"] = request_info
        if content is None:
            return pd.DataFrame(), manifest
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        text = content.decode("utf-8-sig")
        manifest.update({"used_existing": False, "downloaded": True, **source_file_manifest(path)})
    try:
        countries = parse_wits_countries_xml(text)
        manifest["rows"] = int(len(countries))
        return countries, manifest
    except ET.ParseError as exc:
        manifest["parse_error"] = repr(exc)
        return pd.DataFrame(), manifest


def fetch_wits_availability_for_country(country_code: str, refresh: bool, timeout: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    url = WITS_DATAAVAILABILITY_URL.format(country=country_code)
    path = WITS_AVAILABILITY_DIR / f"{country_code}.xml"
    manifest = {"country_code": country_code, "url": url}
    if path.exists() and not refresh:
        text = path.read_text(encoding="utf-8-sig")
        manifest.update({"used_existing": True, **source_file_manifest(path)})
    else:
        content, request_info = request_bytes(url, timeout)
        manifest["request"] = request_info
        if content is None:
            return pd.DataFrame(), manifest
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        text = content.decode("utf-8-sig")
        manifest.update({"used_existing": False, "downloaded": True, **source_file_manifest(path)})
    try:
        availability = parse_wits_dataavailability_xml(text)
        manifest["rows"] = int(len(availability))
        return availability, manifest
    except ET.ParseError as exc:
        manifest["parse_error"] = repr(exc)
        return pd.DataFrame(), manifest


def fetch_wits_availability_by_codes(
    country_codes: list[str], refresh: bool, timeout: int, max_reporters: int | None = None
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    frames: list[pd.DataFrame] = []
    manifests: list[dict[str, Any]] = []
    countries = sorted({normalize_wits_country_code(code) for code in country_codes if normalize_wits_country_code(code)})
    if max_reporters is not None:
        countries = countries[:max_reporters]
    for country_code in countries:
        availability, manifest = fetch_wits_availability_for_country(country_code, refresh=refresh, timeout=timeout)
        manifests.append(manifest)
        if not availability.empty:
            frames.append(availability)
    if not frames:
        return pd.DataFrame(), manifests
    return pd.concat(frames, ignore_index=True), manifests


def fetch_wits_availability(
    crosswalk: pd.DataFrame, refresh: bool, timeout: int, max_reporters: int | None = None
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    if "tariff_reporter_code_default" in crosswalk:
        countries = (
            crosswalk["tariff_reporter_code_default"]
            .dropna()
            .map(normalize_wits_country_code)
            .loc[lambda s: s.ne("")]
            .tolist()
        )
    elif "wits_country_code" in crosswalk:
        countries = crosswalk["wits_country_code"].dropna().map(normalize_wits_country_code).loc[lambda s: s.ne("")].tolist()
    else:
        countries = crosswalk["wits_country_code_candidate"].dropna().map(normalize_wits_country_code).loc[lambda s: s.ne("")].tolist()
    return fetch_wits_availability_by_codes(countries, refresh=refresh, timeout=timeout, max_reporters=max_reporters)


def load_export_baseline_sample() -> pd.DataFrame:
    if not CONCENTRATION_PATH.exists():
        return pd.DataFrame()
    df = pd.read_parquet(CONCENTRATION_PATH)
    required = {"country", "iso3", "reporter_code", "year", "flow", "variant"}
    if not required.issubset(df.columns):
        return pd.DataFrame()
    export = df[df["flow"].eq("Exports") & df["variant"].eq("baseline")].copy()
    export["iso3"] = export["iso3"].astype(str).str.upper()
    export["reporter_code"] = pd.to_numeric(export["reporter_code"], errors="coerce").astype("Int64")
    export["year"] = pd.to_numeric(export["year"], errors="coerce").astype("Int64")
    return export


def sample_diagnostics(sample: pd.DataFrame | None = None) -> dict[str, Any]:
    if not CONCENTRATION_PATH.exists():
        return {
            "path": str(CONCENTRATION_PATH.relative_to(ROOT)),
            "exists": False,
            "status": "blocker_missing_concentration_panel",
        }
    df = pd.read_parquet(CONCENTRATION_PATH)
    required = {"country", "iso3", "reporter_code", "year", "flow", "variant", "product_gini"}
    missing_cols = sorted(required - set(df.columns))
    if missing_cols:
        return {
            "path": str(CONCENTRATION_PATH.relative_to(ROOT)),
            "exists": True,
            "status": "blocker_missing_required_columns",
            "missing_columns": missing_cols,
        }
    export = sample.copy() if sample is not None and not sample.empty else df[df["flow"].eq("Exports") & df["variant"].eq("baseline")].copy()
    duplicate_key_count = int(export.duplicated(["iso3", "reporter_code", "year"]).sum())
    missing = export[export["product_gini"].isna()][
        ["country", "iso3", "reporter_code", "year", "flow", "product_gini"]
    ].copy()
    return {
        "path": str(CONCENTRATION_PATH.relative_to(ROOT)),
        "exists": True,
        "all_rows": int(len(df)),
        "export_baseline_rows": int(len(export)),
        "reporters": int(export["reporter_code"].nunique()),
        "countries": int(export["iso3"].nunique()),
        "year_min": int(export["year"].min()) if not export.empty else None,
        "year_max": int(export["year"].max()) if not export.empty else None,
        "duplicate_iso3_reporter_year_rows": duplicate_key_count,
        "missing_product_gini_rows": int(len(missing)),
        "missing_product_gini_examples": missing.to_dict("records"),
        "status": "ok" if duplicate_key_count == 0 and len(export) == 1920 and export["iso3"].nunique() == 60 else "check",
    }


def build_country_crosswalk(rd2: pd.DataFrame, wits_countries: pd.DataFrame) -> pd.DataFrame:
    crosswalk = rd2.copy()
    if wits_countries.empty:
        crosswalk["wits_country_code"] = ""
        crosswalk["wits_iso3"] = ""
        crosswalk["wits_name"] = ""
        crosswalk["wits_is_reporter"] = ""
        crosswalk["wits_is_partner"] = ""
        crosswalk["wits_match_status"] = "missing_wits_metadata"
        return add_tariff_reporter_mapping(crosswalk)

    wits = wits_countries.copy()
    wits["wits_country_code"] = wits["wits_country_code"].astype(str).str.zfill(3)
    merged = crosswalk.merge(
        wits,
        left_on="wits_country_code_candidate",
        right_on="wits_country_code",
        how="left",
        validate="one_to_one",
    )
    merged["wits_match_status"] = "missing_wits_code"
    has_code = merged["wits_country_code"].notna()
    same_iso = has_code & merged["wits_iso3"].astype(str).str.upper().eq(merged["iso3"].astype(str).str.upper())
    iso_mismatch = has_code & ~same_iso
    merged.loc[same_iso, "wits_match_status"] = "exact_code_iso3_match"
    merged.loc[iso_mismatch, "wits_match_status"] = "exact_code_iso3_mismatch"

    missing_code = merged["wits_country_code"].isna()
    if missing_code.any():
        fallback_cols = [
            "wits_country_code",
            "wits_iso3",
            "wits_name",
            "wits_is_reporter",
            "wits_is_partner",
            "wits_is_group",
            "wits_group_type",
            "wits_notes",
        ]
        wits_by_iso = (
            wits[wits["wits_iso3"].astype(str).str.len().eq(3)]
            .sort_values(["wits_iso3", "wits_is_group", "wits_country_code"])
            .drop_duplicates(["wits_iso3"], keep="first")
            .set_index("wits_iso3", drop=False)
        )
        for idx in merged.index[missing_code]:
            iso3 = str(merged.loc[idx, "iso3"]).upper()
            if iso3 not in wits_by_iso.index:
                continue
            for col in fallback_cols:
                merged.loc[idx, col] = wits_by_iso.loc[iso3, col]
            merged.loc[idx, "wits_match_status"] = "iso3_match_different_numeric_code"
    merged = add_tariff_reporter_mapping(merged)
    return merged.sort_values("iso3").reset_index(drop=True)


def add_tariff_reporter_mapping(crosswalk: pd.DataFrame) -> pd.DataFrame:
    out = crosswalk.copy()
    out["eu_member"] = out["iso3"].isin(EU_MEMBERSHIP_YEARS)
    out["eu_accession_year"] = out["iso3"].map(lambda iso: EU_MEMBERSHIP_YEARS.get(str(iso).upper(), (None, None))[0])
    out["eu_exit_year"] = out["iso3"].map(lambda iso: EU_MEMBERSHIP_YEARS.get(str(iso).upper(), (None, None))[1])
    out["tariff_reporter_code_default"] = out["wits_country_code"].map(normalize_wits_country_code)
    out["tariff_reporter_iso3_default"] = out["wits_iso3"].fillna("").astype(str)
    out["tariff_reporter_name_default"] = out["wits_name"].fillna("").astype(str)
    out["tariff_reporter_mapping_status"] = "direct_wits_country"

    direct_missing = out["wits_match_status"].isin(["missing_wits_metadata", "missing_wits_code"])
    out.loc[direct_missing, "tariff_reporter_mapping_status"] = "missing_tariff_reporter"

    eu_mask = out["eu_member"]
    out.loc[eu_mask, "tariff_reporter_code_default"] = EU_CUSTOMS_TERRITORY_CODE
    out.loc[eu_mask, "tariff_reporter_iso3_default"] = EU_CUSTOMS_TERRITORY_ISO3
    out.loc[eu_mask, "tariff_reporter_name_default"] = EU_CUSTOMS_TERRITORY_NAME
    out.loc[eu_mask, "tariff_reporter_mapping_status"] = "needs_year_specific_eu_customs_mapping"
    return out


def eu_customs_active_for_year(iso3: str, year: int) -> bool:
    membership = EU_MEMBERSHIP_YEARS.get(str(iso3).upper())
    if membership is None:
        return False
    accession_year, customs_end_year = membership
    if accession_year is None or year < int(accession_year):
        return False
    if customs_end_year is not None and year > int(customs_end_year):
        return False
    return True


def availability_by_reporter_year(availability: pd.DataFrame) -> pd.DataFrame:
    if availability.empty:
        return pd.DataFrame(columns=["tariff_reporter_code", "year", "availability_nomenclature_codes"])
    work = availability.copy()
    work["tariff_reporter_code"] = work["wits_country_code"].map(normalize_wits_country_code)
    work["year"] = pd.to_numeric(work["year"], errors="coerce").astype("Int64")
    work = work[work["tariff_reporter_code"].ne("") & work["year"].notna()].copy()
    return (
        work.groupby(["tariff_reporter_code", "year"], as_index=False)
        .agg(
            availability_nomenclature_codes=("nomenclature_code", lambda values: ";".join(sorted(set(map(str, values))))),
            availability_last_updated_dates=("last_updated_date", lambda values: ";".join(sorted(set(map(str, values))))),
        )
        .sort_values(["tariff_reporter_code", "year"])
    )


def build_tariff_reporter_year_mapping(
    export_sample: pd.DataFrame, crosswalk: pd.DataFrame, availability: pd.DataFrame
) -> pd.DataFrame:
    sample_cols = ["country", "iso3", "reporter_code", "year"]
    if export_sample.empty or not set(sample_cols).issubset(export_sample.columns):
        return pd.DataFrame()
    sample = (
        export_sample[sample_cols]
        .drop_duplicates(["iso3", "reporter_code", "year"])
        .sort_values(["iso3", "year"])
        .copy()
    )
    sample["iso3"] = sample["iso3"].astype(str).str.upper()
    sample["reporter_code"] = pd.to_numeric(sample["reporter_code"], errors="coerce").astype("Int64")
    sample["year"] = pd.to_numeric(sample["year"], errors="coerce").astype("Int64")

    cw_cols = [
        "iso3",
        "reporter_code",
        "wits_country_code",
        "wits_iso3",
        "wits_name",
        "wits_is_reporter",
        "wits_match_status",
        "eu_member",
        "eu_accession_year",
        "eu_exit_year",
    ]
    cw = crosswalk[cw_cols].copy()
    cw["iso3"] = cw["iso3"].astype(str).str.upper()
    cw["reporter_code"] = pd.to_numeric(cw["reporter_code"], errors="coerce").astype("Int64")
    cw["direct_wits_country_code"] = cw["wits_country_code"].map(normalize_wits_country_code)
    cw = cw.rename(
        columns={
            "wits_iso3": "direct_wits_iso3",
            "wits_name": "direct_wits_name",
            "wits_is_reporter": "direct_wits_is_reporter",
            "wits_match_status": "direct_wits_match_status",
            "eu_exit_year": "eu_customs_end_year",
        }
    )
    cw = cw.drop(columns=["wits_country_code"])
    merged = sample.merge(cw, on=["iso3", "reporter_code"], how="left", validate="many_to_one")
    merged["eu_member"] = merged["eu_member"].fillna(False).astype(bool)
    merged["eu_customs_active"] = merged.apply(
        lambda row: eu_customs_active_for_year(str(row["iso3"]), int(row["year"]))
        if not pd.isna(row["year"])
        else False,
        axis=1,
    )
    merged["tariff_reporter_code"] = merged["direct_wits_country_code"].fillna("").astype(str)
    merged["tariff_reporter_iso3"] = merged["direct_wits_iso3"].fillna("").astype(str)
    merged["tariff_reporter_name"] = merged["direct_wits_name"].fillna("").astype(str)
    merged["customs_mapping_rule"] = "direct_wits_country_not_eu_member"
    merged.loc[merged["eu_member"] & ~merged["eu_customs_active"], "customs_mapping_rule"] = "direct_wits_country_pre_accession"
    post_exit = (
        merged["eu_member"]
        & ~merged["eu_customs_active"]
        & merged["eu_customs_end_year"].notna()
        & (merged["year"].astype("Int64") > merged["eu_customs_end_year"].astype("Int64"))
    ).fillna(False)
    merged.loc[post_exit, "customs_mapping_rule"] = "direct_wits_country_post_eu_customs_exit"

    eu_active = merged["eu_customs_active"]
    merged.loc[eu_active, "tariff_reporter_code"] = EU_CUSTOMS_TERRITORY_CODE
    merged.loc[eu_active, "tariff_reporter_iso3"] = EU_CUSTOMS_TERRITORY_ISO3
    merged.loc[eu_active, "tariff_reporter_name"] = EU_CUSTOMS_TERRITORY_NAME
    merged.loc[eu_active, "customs_mapping_rule"] = "eu_customs_territory_active"
    missing_direct = ~eu_active & merged["tariff_reporter_code"].fillna("").astype(str).eq("")
    merged.loc[missing_direct, "customs_mapping_rule"] = "missing_direct_wits_country_for_non_eu_year"

    availability_year = availability_by_reporter_year(availability)
    if availability_year.empty:
        merged["has_wits_availability_for_year"] = pd.NA
        merged["availability_nomenclature_codes"] = ""
        merged["availability_last_updated_dates"] = ""
        merged["tariff_mapping_status"] = "availability_not_checked"
    else:
        merged = merged.merge(
            availability_year,
            on=["tariff_reporter_code", "year"],
            how="left",
            validate="many_to_one",
        )
        merged["has_wits_availability_for_year"] = merged["availability_nomenclature_codes"].notna()
        merged["availability_nomenclature_codes"] = merged["availability_nomenclature_codes"].fillna("")
        merged["availability_last_updated_dates"] = merged["availability_last_updated_dates"].fillna("")
        merged["tariff_mapping_status"] = "ok"
        merged.loc[~merged["has_wits_availability_for_year"], "tariff_mapping_status"] = "missing_wits_availability_for_year"

    missing_reporter = merged["tariff_reporter_code"].fillna("").astype(str).eq("")
    merged.loc[missing_reporter, "tariff_mapping_status"] = "missing_tariff_reporter_for_year"
    ordered_cols = [
        "country",
        "iso3",
        "reporter_code",
        "year",
        "eu_member",
        "eu_accession_year",
        "eu_customs_end_year",
        "eu_customs_active",
        "direct_wits_country_code",
        "direct_wits_iso3",
        "direct_wits_name",
        "direct_wits_is_reporter",
        "direct_wits_match_status",
        "tariff_reporter_code",
        "tariff_reporter_iso3",
        "tariff_reporter_name",
        "customs_mapping_rule",
        "has_wits_availability_for_year",
        "availability_nomenclature_codes",
        "availability_last_updated_dates",
        "tariff_mapping_status",
    ]
    return merged[ordered_cols].sort_values(["iso3", "year"]).reset_index(drop=True)


def summarize_tariff_reporter_year_mapping(mapping: pd.DataFrame, availability_checked: bool) -> dict[str, Any]:
    path = PROCESSED_DIR / "trade_deal_tariff_reporter_year_mapping.csv"
    if mapping.empty:
        return {
            "path": str(path.relative_to(ROOT)),
            "rows": 0,
            "status": "blocked_missing_export_sample_or_crosswalk",
        }
    duplicate_keys = int(mapping.duplicated(["iso3", "reporter_code", "year"]).sum())
    missing_reporter = mapping[mapping["tariff_reporter_code"].fillna("").astype(str).eq("")]
    if availability_checked:
        missing_availability = mapping[mapping["has_wits_availability_for_year"].fillna(False).eq(False)]
    else:
        missing_availability = pd.DataFrame()
    if duplicate_keys or not missing_reporter.empty:
        status = "blocked_missing_year_tariff_reporter"
    elif availability_checked and not missing_availability.empty:
        status = "mapping_complete_with_wits_year_availability_gaps"
    else:
        status = "ok"
    return {
        "path": str(path.relative_to(ROOT)),
        "rows": int(len(mapping)),
        "expected_export_baseline_rows": 1920,
        "countries": int(mapping["iso3"].nunique()),
        "year_min": int(mapping["year"].min()),
        "year_max": int(mapping["year"].max()),
        "duplicate_iso3_reporter_year_rows": duplicate_keys,
        "missing_tariff_reporter_rows": int(len(missing_reporter)),
        "missing_wits_availability_year_rows": int(len(missing_availability)) if availability_checked else None,
        "eu_customs_territory_active_rows": int(mapping["customs_mapping_rule"].eq("eu_customs_territory_active").sum()),
        "pre_accession_direct_rows": int(mapping["customs_mapping_rule"].eq("direct_wits_country_pre_accession").sum()),
        "post_eu_customs_exit_direct_rows": int(
            mapping["customs_mapping_rule"].eq("direct_wits_country_post_eu_customs_exit").sum()
        ),
        "tariff_reporter_codes": sorted(mapping["tariff_reporter_code"].dropna().astype(str).loc[lambda s: s.ne("")].unique().tolist()),
        "customs_mapping_rule_counts": mapping["customs_mapping_rule"].value_counts().to_dict(),
        "tariff_mapping_status_counts": mapping["tariff_mapping_status"].value_counts(dropna=False).to_dict(),
        "missing_wits_availability_examples": missing_availability[
            ["country", "iso3", "reporter_code", "year", "tariff_reporter_code", "customs_mapping_rule"]
        ]
        .head(20)
        .to_dict("records")
        if availability_checked
        else [],
        "status": status,
    }


def build_wits_availability_gap_tables(mapping: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    gap_path = PROCESSED_DIR / "trade_deal_wits_tariff_reporter_year_availability_gaps.csv"
    summary_path = PROCESSED_DIR / "trade_deal_wits_tariff_reporter_year_availability_gap_summary.csv"
    if mapping.empty or "tariff_mapping_status" not in mapping:
        return (
            pd.DataFrame(),
            pd.DataFrame(),
            {
                "gap_path": str(gap_path.relative_to(ROOT)),
                "summary_path": str(summary_path.relative_to(ROOT)),
                "status": "not_available",
                "rows": 0,
            },
        )
    gaps = mapping[mapping["tariff_mapping_status"].eq("missing_wits_availability_for_year")].copy()
    gap_cols = [
        "country",
        "iso3",
        "reporter_code",
        "year",
        "tariff_reporter_code",
        "tariff_reporter_iso3",
        "tariff_reporter_name",
        "customs_mapping_rule",
        "direct_wits_country_code",
        "direct_wits_iso3",
        "direct_wits_is_reporter",
    ]
    gaps = gaps[[col for col in gap_cols if col in gaps.columns]].sort_values(["year", "iso3"]).reset_index(drop=True)
    if gaps.empty:
        summary = pd.DataFrame(columns=["year", "missing_reporter_years", "countries"])
    else:
        summary = (
            gaps.groupby("year", as_index=False)
            .agg(
                missing_reporter_years=("iso3", "size"),
                countries=("iso3", lambda values: ";".join(sorted(set(map(str, values))))),
                tariff_reporter_codes=("tariff_reporter_code", lambda values: ";".join(sorted(set(map(str, values))))),
            )
            .sort_values("year")
            .reset_index(drop=True)
        )
    return (
        gaps,
        summary,
        {
            "gap_path": str(gap_path.relative_to(ROOT)),
            "summary_path": str(summary_path.relative_to(ROOT)),
            "rows": int(len(gaps)),
            "years": int(gaps["year"].nunique()) if not gaps.empty else 0,
            "countries": int(gaps["iso3"].nunique()) if not gaps.empty else 0,
            "year_min": int(gaps["year"].min()) if not gaps.empty else None,
            "year_max": int(gaps["year"].max()) if not gaps.empty else None,
            "status": "ok" if gaps.empty else "gaps_present",
            "policy": (
                "No tariff exposure should use reporter-years in this table unless the researcher selects "
                "an explicit supplement, sample restriction, or imputation/carry-forward rule."
            ),
        },
    )


def parse_comtrade_aggregate_filename(path: Path) -> dict[str, Any] | None:
    match = re.search(r"COMTRADE-FINAL-CA(?P<reporter>\d{3})(?P<year>\d{4})(?P<revision>H\d)", path.name)
    if not match:
        return None
    return {
        "file": display_path(path),
        "reporter_code": int(match.group("reporter")),
        "year": int(match.group("year")),
        "comtrade_hs_revision": match.group("revision"),
    }


def scan_comtrade_hs_revisions() -> tuple[pd.DataFrame, dict[str, Any]]:
    rows = []
    for path in sorted(COMTRADE_AGG_DIR.glob("*.parquet")):
        parsed = parse_comtrade_aggregate_filename(path)
        if parsed is not None:
            rows.append(parsed)
    df = pd.DataFrame(rows)
    if df.empty:
        return df, {
            "aggregate_dir": str(COMTRADE_AGG_DIR.relative_to(ROOT)),
            "files": 0,
            "status": "blocker_missing_comtrade_aggregate_files",
        }
    summary = {
        "aggregate_dir": str(COMTRADE_AGG_DIR.relative_to(ROOT)),
        "files": int(len(df)),
        "reporters": int(df["reporter_code"].nunique()),
        "year_min": int(df["year"].min()),
        "year_max": int(df["year"].max()),
        "revisions": sorted(df["comtrade_hs_revision"].dropna().unique().tolist()),
        "revision_counts": df["comtrade_hs_revision"].value_counts().sort_index().to_dict(),
        "duplicate_reporter_year_files": int(df.duplicated(["reporter_code", "year"]).sum()),
        "status": "ok",
    }
    return df, summary


def summarize_wits_availability(
    availability: pd.DataFrame, crosswalk: pd.DataFrame, tariff_year_mapping: pd.DataFrame | None = None
) -> dict[str, Any]:
    eu_customs_active_rows = None
    if tariff_year_mapping is not None and not tariff_year_mapping.empty:
        expected = tariff_year_mapping[["iso3", "tariff_reporter_code"]].drop_duplicates().copy()
        expected["tariff_reporter_code_default"] = expected["tariff_reporter_code"].map(normalize_wits_country_code)
        expected["tariff_reporter_mapping_status"] = "year_specific_mapping"
        eu_customs_active_rows = int(
            tariff_year_mapping["customs_mapping_rule"].eq("eu_customs_territory_active").sum()
        )
    else:
        expected = crosswalk[["iso3", "tariff_reporter_code_default", "tariff_reporter_mapping_status"]].copy()
        expected["tariff_reporter_code_default"] = expected["tariff_reporter_code_default"].map(normalize_wits_country_code)
        eu_customs_active_rows = int(
            expected["tariff_reporter_mapping_status"].eq("needs_year_specific_eu_customs_mapping").sum()
        )
    expected.loc[expected["tariff_reporter_code_default"].eq("000"), "tariff_reporter_code_default"] = ""
    if availability.empty:
        return {
            "status": "not_available",
            "rows": 0,
            "reporters_with_availability": 0,
            "reporters_without_availability": sorted(expected["iso3"].tolist()),
            "nomenclature_codes": [],
        }
    availability = availability.copy()
    availability["year"] = pd.to_numeric(availability["year"], errors="coerce")
    availability["wits_country_code"] = availability["wits_country_code"].astype(str).str.zfill(3)
    by_reporter = availability.dropna(subset=["year"]).groupby("wits_iso3").agg(
        years_available=("year", "nunique"),
        year_min=("year", "min"),
        year_max=("year", "max"),
        nomenclature_codes=("nomenclature_code", lambda x: ";".join(sorted(set(map(str, x))))),
        ave_years=("specific_duty_ave_available", lambda x: int(pd.Series(x).astype(str).str.lower().eq("yes").sum())),
    )
    available_codes = set(availability["wits_country_code"].dropna().astype(str).str.zfill(3))
    expected["has_tariff_reporter_availability"] = expected["tariff_reporter_code_default"].isin(available_codes)
    country_any_availability = expected.groupby("iso3")["has_tariff_reporter_availability"].any()
    reporters_without = country_any_availability.loc[lambda s: ~s].index.to_series().astype(str).str.upper()
    return {
        "status": "ok",
        "rows": int(len(availability)),
        "reporters_with_availability": int(country_any_availability.sum()),
        "reporters_without_availability": sorted(reporters_without.tolist()),
        "expected_tariff_reporter_code_mappings": int(len(expected)),
        "tariff_reporter_code_mappings_with_availability": int(expected["has_tariff_reporter_availability"].sum()),
        "year_min": int(availability["year"].min()) if availability["year"].notna().any() else None,
        "year_max": int(availability["year"].max()) if availability["year"].notna().any() else None,
        "nomenclature_codes": sorted(availability["nomenclature_code"].dropna().astype(str).unique().tolist()),
        "expected_tariff_reporter_codes": sorted(
            expected["tariff_reporter_code_default"].loc[lambda s: s.ne("")].drop_duplicates().tolist()
        ),
        "eu_customs_active_reporter_year_rows": eu_customs_active_rows,
        "reporter_summary": by_reporter.reset_index().to_dict("records"),
    }


def load_hs_family_crosswalk() -> tuple[pd.DataFrame, dict[str, Any]]:
    if not LT_HGL_WEIGHT_MAPPING_PATH.exists():
        load_lt_hgl_hs1992_conversion_weights()
    manifest = {
        "path": str(LT_HGL_WEIGHT_MAPPING_PATH.relative_to(ROOT)),
        **source_file_manifest(LT_HGL_WEIGHT_MAPPING_PATH),
        "source_doi": LT_HGL_DATASET_DOI,
        "source_version": LT_HGL_DATASET_VERSION,
        "harmonization_method": "official LT/HGL weighted conversion to HS1992/H0",
    }
    if not LT_HGL_WEIGHT_MAPPING_PATH.exists():
        manifest["status"] = "blocked_missing_lt_hgl_weight_mapping"
        return pd.DataFrame(), manifest
    weights = load_lt_hgl_hs1992_conversion_weights()
    required = {
        "source_classification_code",
        "source_cmd_code",
        "target_product_id",
        "conversion_method",
        "weight",
    }
    missing_cols = sorted(required - set(weights.columns))
    if missing_cols:
        manifest.update({"status": "blocked_missing_required_columns", "missing_columns": missing_cols})
        return pd.DataFrame(), manifest
    family = weights[
        [
            "source_classification_code",
            "source_cmd_code",
            "target_product_id",
            "conversion_method",
            "weight",
        ]
    ].rename(
        columns={
            "source_classification_code": "classification_code",
            "source_cmd_code": "cmd_code",
            "target_product_id": "harmonized_product_id",
            "conversion_method": "harmonization_status",
        }
    )
    family["classification_code"] = family["classification_code"].astype(str).str.upper()
    family["cmd_code"] = family["cmd_code"].map(normalize_hs6_code)
    excluded = family["cmd_code"].isin(EXCLUDED_HS6_CODES)
    family = family[~excluded & family["cmd_code"].ne("")].copy()
    family["classification_label"] = family["classification_code"].map(HS_REVISION_LABELS).fillna(family["classification_code"])
    family["harmonization_source"] = f"Harvard Dataverse DOI {LT_HGL_DATASET_DOI} v{LT_HGL_DATASET_VERSION}"
    family["source_component_id"] = family["classification_code"] + ":" + family["cmd_code"]
    target_counts = (
        family.groupby(["classification_code", "cmd_code"], observed=True)["harmonized_product_id"]
        .nunique()
        .reset_index(name="source_component_node_count")
    )
    family = family.merge(target_counts, on=["classification_code", "cmd_code"], how="left", validate="many_to_one")
    family["analysis_family_node_count"] = 1
    revision_counts = (
        family.groupby("harmonized_product_id", observed=True)["classification_code"]
        .nunique()
        .reset_index(name="source_revision_count")
    )
    family = family.merge(revision_counts, on="harmonized_product_id", how="left", validate="many_to_one")
    family["max_family_nodes"] = family["source_component_node_count"]
    family["harmonization_version"] = "lt_hgl_weighted_hs1992"
    for col in ["source_component_node_count", "analysis_family_node_count", "source_revision_count", "max_family_nodes"]:
        family[col] = pd.to_numeric(family[col], errors="coerce").astype("Int64")
    family = family[
        [
            "classification_code",
            "classification_label",
            "cmd_code",
            "harmonized_product_id",
            "harmonization_status",
            "harmonization_source",
            "source_component_id",
            "source_component_node_count",
            "analysis_family_node_count",
            "source_revision_count",
            "max_family_nodes",
            "harmonization_version",
            "weight",
        ]
    ].copy()
    manifest.update(
        {
            "status": "ok",
            "rows_after_excluding_999999": int(len(family)),
            "excluded_999999_rows": int(excluded.sum()),
            "revision_counts": family["classification_code"].value_counts().sort_index().to_dict(),
            "harmonization_versions": sorted(family["harmonization_version"].dropna().astype(str).unique().tolist()),
            "policy": "HS6 code 999999 is excluded before building product-level concordance artifacts; source keys use LT/HGL weighted HS1992 conversion coverage.",
        }
    )
    return family.sort_values(["classification_code", "cmd_code"]).reset_index(drop=True), manifest


def baseline_export_weight_file_plan(comtrade_revisions: pd.DataFrame, years_per_exporter: int = 5) -> pd.DataFrame:
    if comtrade_revisions.empty:
        return pd.DataFrame()
    required = {"reporter_code", "year", "comtrade_hs_revision", "file"}
    if not required.issubset(comtrade_revisions.columns):
        return pd.DataFrame()
    base = comtrade_revisions[list(required)].copy()
    base["reporter_code"] = pd.to_numeric(base["reporter_code"], errors="coerce").astype("Int64")
    base["year"] = pd.to_numeric(base["year"], errors="coerce").astype("Int64")
    base["comtrade_hs_revision"] = base["comtrade_hs_revision"].fillna("").astype(str).str.upper()
    base = base.dropna(subset=["reporter_code", "year"])
    base = base[base["comtrade_hs_revision"].ne("H6")].copy()
    return base.sort_values(["reporter_code", "year"]).groupby("reporter_code", as_index=False).head(years_per_exporter)


def summarize_hs4_baseline_harmonization_coverage(
    comtrade_revisions: pd.DataFrame, hs_family: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, Any]]:
    path = HS4_BASELINE_HARMONIZATION_COVERAGE_PATH
    if comtrade_revisions.empty or hs_family.empty:
        return pd.DataFrame(), {
            "path": str(path.relative_to(ROOT)),
            "status": "blocked_missing_comtrade_or_hs_family_data",
            "hs4_bridge_trade_value_coverage_min_required": HS4_HARMONIZATION_COVERAGE_MIN,
        }

    baseline_files = baseline_export_weight_file_plan(comtrade_revisions, years_per_exporter=10_000)
    if baseline_files.empty:
        return pd.DataFrame(), {
            "path": str(path.relative_to(ROOT)),
            "status": "blocked_missing_baseline_export_files",
            "hs4_bridge_trade_value_coverage_min_required": HS4_HARMONIZATION_COVERAGE_MIN,
        }

    family_keys = set(
        zip(
            hs_family["classification_code"].fillna("").astype(str).str.upper(),
            hs_family["cmd_code"].map(normalize_hs6_code),
        )
    )
    expected_reporters = sorted(
        pd.to_numeric(comtrade_revisions["reporter_code"], errors="coerce").dropna().astype(int).unique().tolist()
    )
    reporter_totals: dict[int, dict[str, Any]] = {}
    read_errors: list[dict[str, str]] = []
    for row in baseline_files.itertuples(index=False):
        rel = str(row.file)
        revision = str(row.comtrade_hs_revision).upper()
        reporter_code = int(row.reporter_code)
        if reporter_totals.get(reporter_code, {}).get("files_scanned", 0) >= 5:
            continue
        path_in = ROOT / rel
        try:
            frame = pd.read_parquet(
                path_in,
                columns=["flow", "dimension", "cmd_code", "partner_code", "trade_value"],
            )
        except Exception as exc:
            read_errors.append({"file": rel, "error": repr(exc)})
            continue
        frame = frame[
            frame["flow"].astype(str).eq("Exports")
            & frame["dimension"].astype(str).eq("product_partner_cell")
            & pd.to_numeric(frame["partner_code"], errors="coerce").fillna(-1).ne(0)
        ].copy()
        if frame.empty:
            continue
        frame["trade_value"] = pd.to_numeric(frame["trade_value"], errors="coerce").fillna(0.0)
        frame = frame[frame["trade_value"].gt(0)].copy()
        if frame.empty:
            continue
        frame["cmd_code"] = frame["cmd_code"].map(normalize_hs6_code)
        valid_hs6 = frame["cmd_code"].str.match(r"^\d{6}$", na=False)
        unspecified = frame["cmd_code"].isin(EXCLUDED_HS6_CODES)
        denominator_mask = valid_hs6 & ~unspecified
        covered_mask = denominator_mask & frame["cmd_code"].map(lambda code: (revision, code) in family_keys)
        current = reporter_totals.setdefault(
            reporter_code,
            {
                "reporter_code": reporter_code,
                "baseline_years": set(),
                "baseline_revisions": set(),
                "files_scanned": 0,
                "positive_product_partner_rows": 0,
                "positive_product_partner_value": 0.0,
                "excluded_999999_rows": 0,
                "excluded_999999_trade_value": 0.0,
                "hs4_denominator_trade_value": 0.0,
                "hs4_covered_trade_value": 0.0,
                "uncovered_rows": 0,
            },
        )
        current["baseline_years"].add(int(row.year))
        current["baseline_revisions"].add(revision)
        current["files_scanned"] += 1
        current["positive_product_partner_rows"] += int(len(frame))
        current["positive_product_partner_value"] += float(frame["trade_value"].sum())
        current["excluded_999999_rows"] += int(unspecified.sum())
        current["excluded_999999_trade_value"] += float(frame.loc[unspecified, "trade_value"].sum())
        current["hs4_denominator_trade_value"] += float(frame.loc[denominator_mask, "trade_value"].sum())
        current["hs4_covered_trade_value"] += float(frame.loc[covered_mask, "trade_value"].sum())
        current["uncovered_rows"] += int((denominator_mask & ~covered_mask).sum())

    rows = []
    for values in reporter_totals.values():
        denominator = float(values["hs4_denominator_trade_value"])
        covered = float(values["hs4_covered_trade_value"])
        rows.append(
            {
                "reporter_code": values["reporter_code"],
                "baseline_years": ";".join(map(str, sorted(values["baseline_years"]))),
                "baseline_year_count": len(values["baseline_years"]),
                "baseline_revisions": ";".join(sorted(values["baseline_revisions"])),
                "files_scanned": values["files_scanned"],
                "positive_product_partner_rows": values["positive_product_partner_rows"],
                "positive_product_partner_value": values["positive_product_partner_value"],
                "excluded_999999_rows": values["excluded_999999_rows"],
                "excluded_999999_trade_value": values["excluded_999999_trade_value"],
                "hs4_denominator_trade_value": denominator,
                "hs4_covered_trade_value": covered,
                "hs4_bridge_trade_value_coverage": round(covered / denominator, 6) if denominator else None,
                "uncovered_rows": values["uncovered_rows"],
            }
        )
    coverage = pd.DataFrame(rows).sort_values("reporter_code").reset_index(drop=True) if rows else pd.DataFrame()
    if coverage.empty:
        return coverage, {
            "path": str(path.relative_to(ROOT)),
            "status": "blocked_no_positive_baseline_product_partner_exports",
            "read_error_count": int(len(read_errors)),
            "read_errors": read_errors[:20],
            "hs4_bridge_trade_value_coverage_min_required": HS4_HARMONIZATION_COVERAGE_MIN,
        }

    denominator_total = float(coverage["hs4_denominator_trade_value"].sum())
    covered_total = float(coverage["hs4_covered_trade_value"].sum())
    coverage_share = round(covered_total / denominator_total, 6) if denominator_total else None
    short_baseline = coverage[coverage["baseline_year_count"].lt(3)]
    missing_baseline_reporters = sorted(set(expected_reporters) - set(coverage["reporter_code"].astype(int).tolist()))
    failed_gate = (
        coverage_share is None
        or coverage_share < HS4_HARMONIZATION_COVERAGE_MIN
        or not short_baseline.empty
        or bool(missing_baseline_reporters)
    )
    summary = {
        "path": str(path.relative_to(ROOT)),
        "status": "blocked_hs4_baseline_coverage_gate_failed" if failed_gate else "passed",
        "unit": "exporter fixed-pre-period product-partner export value",
        "baseline_rule": "earliest five available non-H6 export years per exporter; require at least three valid years",
        "reporters": int(coverage["reporter_code"].nunique()),
        "expected_reporters": int(len(expected_reporters)),
        "files_scanned": int(coverage["files_scanned"].sum()),
        "read_error_count": int(len(read_errors)),
        "read_errors": read_errors[:20],
        "hs4_denominator_trade_value": denominator_total,
        "hs4_covered_trade_value": covered_total,
        "hs4_bridge_trade_value_coverage": coverage_share,
        "hs4_bridge_trade_value_coverage_min_required": HS4_HARMONIZATION_COVERAGE_MIN,
        "reporters_with_less_than_three_valid_baseline_years": sorted(
            set(short_baseline["reporter_code"].astype(int).tolist()) | set(missing_baseline_reporters)
        ),
        "excluded_999999_rows": int(coverage["excluded_999999_rows"].sum()),
        "excluded_999999_trade_value": float(coverage["excluded_999999_trade_value"].sum()),
        "policy": (
            "HS4 harmonization coverage is baseline-export-value weighted. HS6 999999 is excluded before "
            "HS4 aggregation, H6 revision years are not used, and tariff exposures must be keyed by harmonized_hs4."
        ),
    }
    return coverage, summary


def build_h6_to_wits_revision_bridge(hs_family: pd.DataFrame, wits_revisions: list[str]) -> pd.DataFrame:
    if hs_family.empty:
        return pd.DataFrame()
    target_revisions = sorted({rev for rev in wits_revisions if rev != "H6"})
    if not target_revisions:
        target_revisions = ["H0", "H1", "H2", "H3", "H4", "H5"]
    h6 = (
        hs_family[hs_family["classification_code"].eq("H6")]
        .rename(
            columns={
                "cmd_code": "h6_cmd_code",
                "classification_label": "h6_classification_label",
                "harmonization_status": "h6_harmonization_status",
                "harmonization_source": "h6_harmonization_source",
                "source_component_node_count": "h6_source_component_node_count",
                "analysis_family_node_count": "h6_analysis_family_node_count",
                "source_revision_count": "h6_source_revision_count",
            }
        )
        [
            [
                "h6_cmd_code",
                "h6_classification_label",
                "harmonized_product_id",
                "h6_harmonization_status",
                "h6_harmonization_source",
                "h6_source_component_node_count",
                "h6_analysis_family_node_count",
                "h6_source_revision_count",
                "harmonization_version",
            ]
        ]
        .drop_duplicates(["h6_cmd_code", "harmonized_product_id"])
    )
    frames = []
    for revision in target_revisions:
        left = h6.assign(target_revision=revision)
        target = (
            hs_family[hs_family["classification_code"].eq(revision)]
            .rename(
                columns={
                    "classification_code": "target_revision",
                    "classification_label": "target_classification_label",
                    "cmd_code": "target_cmd_code",
                    "harmonization_status": "target_harmonization_status",
                    "harmonization_source": "target_harmonization_source",
                }
            )
            [
                [
                    "target_revision",
                    "target_classification_label",
                    "target_cmd_code",
                    "harmonized_product_id",
                    "target_harmonization_status",
                    "target_harmonization_source",
                ]
            ]
            .drop_duplicates(["target_revision", "target_cmd_code", "harmonized_product_id"])
        )
        frames.append(left.merge(target, on=["harmonized_product_id", "target_revision"], how="left"))
    bridge = pd.concat(frames, ignore_index=True)
    candidate_counts = (
        bridge.dropna(subset=["target_cmd_code"])
        .groupby(["h6_cmd_code", "target_revision"])["target_cmd_code"]
        .nunique()
        .rename("target_candidate_count")
        .reset_index()
    )
    bridge = bridge.merge(candidate_counts, on=["h6_cmd_code", "target_revision"], how="left")
    bridge["target_candidate_count"] = bridge["target_candidate_count"].fillna(0).astype(int)
    bridge["bridge_status"] = "unique_family_bridge"
    bridge.loc[bridge["target_candidate_count"].eq(0), "bridge_status"] = "no_target_revision_family_match"
    bridge.loc[bridge["target_candidate_count"].gt(1), "bridge_status"] = "ambiguous_multi_target_family_bridge"
    oversized_no_target = bridge["h6_harmonization_status"].eq("ambiguous_oversized_component") & bridge[
        "target_candidate_count"
    ].eq(0)
    bridge.loc[oversized_no_target, "bridge_status"] = "no_target_revision_family_match_ambiguous_oversized_component"
    bridge["bridge_unit"] = "H6 HS6 code x WITS target HS revision"
    ordered_cols = [
        "bridge_unit",
        "h6_cmd_code",
        "target_revision",
        "target_cmd_code",
        "target_candidate_count",
        "bridge_status",
        "harmonized_product_id",
        "h6_classification_label",
        "target_classification_label",
        "h6_harmonization_status",
        "target_harmonization_status",
        "h6_harmonization_source",
        "target_harmonization_source",
        "h6_source_component_node_count",
        "h6_analysis_family_node_count",
        "h6_source_revision_count",
        "harmonization_version",
    ]
    return bridge[ordered_cols].sort_values(["target_revision", "h6_cmd_code", "target_cmd_code"]).reset_index(drop=True)


def summarize_h6_bridge(bridge: pd.DataFrame) -> dict[str, Any]:
    path = PROCESSED_DIR / "trade_deal_h6_to_wits_revision_bridge.csv"
    if bridge.empty:
        return {"path": str(path.relative_to(ROOT)), "rows": 0, "status": "blocked_missing_hs_bridge"}
    per_code = bridge.drop_duplicates(["h6_cmd_code", "target_revision"]).copy()
    by_revision = []
    for revision, group in per_code.groupby("target_revision"):
        total = int(group["h6_cmd_code"].nunique())
        status_counts = group["bridge_status"].value_counts().to_dict()
        unique = int(group["bridge_status"].eq("unique_family_bridge").sum())
        ambiguous = int(group["bridge_status"].eq("ambiguous_multi_target_family_bridge").sum())
        no_target = int(group["bridge_status"].str.startswith("no_target_revision_family_match").sum())
        by_revision.append(
            {
                "target_revision": revision,
                "h6_codes_total": total,
                "h6_codes_unique_family_bridge": unique,
                "h6_codes_ambiguous_multi_target_family_bridge": ambiguous,
                "h6_codes_without_target_revision_family_match": no_target,
                "unique_bridge_share": round(unique / total, 6) if total else None,
                "status_counts": status_counts,
            }
        )
    h5 = next((row for row in by_revision if row["target_revision"] == "H5"), {})
    return {
        "path": str(path.relative_to(ROOT)),
        "rows": int(len(bridge)),
        "h6_codes": int(bridge["h6_cmd_code"].nunique()),
        "target_revisions": sorted(bridge["target_revision"].dropna().astype(str).unique().tolist()),
        "by_target_revision": by_revision,
        "h6_to_h5_unique_bridge_share": h5.get("unique_bridge_share"),
        "status": "ok",
        "policy": (
            "The bridge is a family-level concordance, not a value-splitting algorithm. "
            "Rows with ambiguous or missing target candidates must not be silently used in primary tariff analysis."
        ),
    }


def summarize_observed_h6_h5_coverage(
    comtrade_revisions: pd.DataFrame, bridge: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, Any]]:
    path = PROCESSED_DIR / "trade_deal_observed_h6_h5_bridge_coverage.csv"
    if comtrade_revisions.empty or bridge.empty:
        return pd.DataFrame(), {"path": str(path.relative_to(ROOT)), "status": "not_available", "rows": 0}
    h6_files = comtrade_revisions[comtrade_revisions["comtrade_hs_revision"].eq("H6")]["file"].dropna().astype(str)
    if h6_files.empty:
        return pd.DataFrame(), {"path": str(path.relative_to(ROOT)), "status": "no_h6_comtrade_files", "rows": 0}
    h5_bridge = bridge[bridge["target_revision"].eq("H5")].drop_duplicates(["h6_cmd_code"])[
        ["h6_cmd_code", "bridge_status", "target_candidate_count", "h6_harmonization_status"]
    ]
    totals: dict[str, dict[str, Any]] = {}
    read_errors: list[dict[str, str]] = []
    rows_scanned = 0
    excluded_999999_rows = 0
    excluded_999999_value = 0.0
    for rel in h6_files:
        path_in = ROOT / rel
        try:
            frame = pd.read_parquet(
                path_in,
                columns=["flow", "dimension", "cmd_code", "partner_code", "trade_value"],
            )
        except Exception as exc:
            read_errors.append({"file": rel, "error": repr(exc)})
            continue
        frame = frame[
            frame["flow"].astype(str).eq("Exports") & frame["dimension"].astype(str).eq("product_partner_cell")
        ].copy()
        rows_scanned += int(len(frame))
        if frame.empty:
            continue
        frame["cmd_code"] = frame["cmd_code"].map(normalize_hs6_code)
        unspecified = frame["cmd_code"].isin(EXCLUDED_HS6_CODES)
        excluded_999999_rows += int(unspecified.sum())
        excluded_999999_value += float(frame.loc[unspecified, "trade_value"].sum())
        frame = frame[~unspecified & frame["cmd_code"].ne("")].copy()
        grouped = frame.groupby("cmd_code", as_index=False).agg(
            observed_rows=("trade_value", "size"),
            observed_trade_value=("trade_value", "sum"),
        )
        for row in grouped.itertuples(index=False):
            current = totals.setdefault(row.cmd_code, {"observed_rows": 0, "observed_trade_value": 0.0})
            current["observed_rows"] += int(row.observed_rows)
            current["observed_trade_value"] += float(row.observed_trade_value)
    if not totals:
        return pd.DataFrame(), {
            "path": str(path.relative_to(ROOT)),
            "status": "no_observed_h6_product_partner_exports",
            "files_scanned": int(len(h6_files)),
            "read_errors": read_errors[:20],
        }
    observed = pd.DataFrame(
        [
            {"h6_cmd_code": code, **values}
            for code, values in sorted(totals.items(), key=lambda item: item[0])
        ]
    )
    observed = observed.merge(h5_bridge, on="h6_cmd_code", how="left")
    observed["bridge_status"] = observed["bridge_status"].fillna("not_in_hs_family_mapping")
    observed["target_candidate_count"] = observed["target_candidate_count"].fillna(0).astype(int)
    observed["observed_trade_value_share"] = observed["observed_trade_value"] / observed["observed_trade_value"].sum()
    status_summary = (
        observed.groupby("bridge_status", as_index=False)
        .agg(
            h6_codes=("h6_cmd_code", "nunique"),
            observed_rows=("observed_rows", "sum"),
            observed_trade_value=("observed_trade_value", "sum"),
        )
        .sort_values("bridge_status")
    )
    total_value = float(observed["observed_trade_value"].sum())
    status_summary["observed_trade_value_share"] = status_summary["observed_trade_value"] / total_value
    unique_value = float(
        status_summary.loc[status_summary["bridge_status"].eq("unique_family_bridge"), "observed_trade_value"].sum()
    )
    summary = {
        "path": str(path.relative_to(ROOT)),
        "status": "ok",
        "files_scanned": int(len(h6_files)),
        "read_error_count": int(len(read_errors)),
        "read_errors": read_errors[:20],
        "product_partner_export_rows_scanned": rows_scanned,
        "observed_h6_codes": int(observed["h6_cmd_code"].nunique()),
        "observed_trade_value": total_value,
        "excluded_999999_rows": excluded_999999_rows,
        "excluded_999999_trade_value": excluded_999999_value,
        "unique_h5_bridge_trade_value_share": round(unique_value / total_value, 6) if total_value else None,
        "status_summary": status_summary.to_dict("records"),
        "policy": (
            "Coverage uses H6 product-partner export rows, excludes HS6 999999 before aggregation, "
            "and treats ambiguous family bridges as non-primary until a documented allocation or aggregation rule exists."
        ),
    }
    return observed, summary


def hs_source_file_manifests() -> list[dict[str, Any]]:
    if not HS_WCO_CORRELATION_DIR.exists():
        return []
    return [
        {
            "source": "wco_hs_revision_correlation_pdf",
            **source_file_manifest(path),
        }
        for path in sorted(HS_WCO_CORRELATION_DIR.glob("*.pdf"))
    ]


def hs_concordance_gate(
    comtrade_summary: dict[str, Any],
    wits_summary: dict[str, Any],
    h6_bridge_summary: dict[str, Any] | None = None,
    observed_h6_h5_coverage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    comtrade_revisions = set(comtrade_summary.get("revisions", []))
    wits_revisions = set(wits_summary.get("nomenclature_codes", []))
    if not comtrade_revisions:
        return {
            "status": "blocked",
            "reason": "No local Comtrade HS revision evidence was found.",
        }
    if not wits_revisions:
        return {
            "status": "blocked",
            "reason": "WITS availability was not fetched or contained no nomenclature codes.",
            "comtrade_revisions": sorted(comtrade_revisions),
            "wits_doc_supported_hs": sorted(WITS_DOC_SUPPORTED_HS),
        }
    direct_overlap = sorted(comtrade_revisions & wits_revisions)
    missing_in_wits = sorted(comtrade_revisions - wits_revisions)
    unsupported_by_docs = sorted(comtrade_revisions - WITS_DOC_SUPPORTED_HS)
    bridge_available = (
        h6_bridge_summary is not None
        and h6_bridge_summary.get("status") == "ok"
        and "H6" in missing_in_wits
        and "H5" in h6_bridge_summary.get("target_revisions", [])
    )
    if not missing_in_wits:
        status = "ok_exact_revision_overlap"
    elif bridge_available:
        status = "bridge_available_pending_weighted_coverage_review"
    else:
        status = "blocked_pending_concordance"
    return {
        "status": status,
        "comtrade_revisions": sorted(comtrade_revisions),
        "wits_availability_revisions": sorted(wits_revisions),
        "direct_overlap": direct_overlap,
        "comtrade_revisions_missing_in_wits_availability": missing_in_wits,
        "comtrade_revisions_beyond_wits_supported_hs": unsupported_by_docs,
        "h6_to_h5_unique_bridge_share": (h6_bridge_summary or {}).get("h6_to_h5_unique_bridge_share"),
        "observed_h6_to_h5_unique_trade_value_share": (observed_h6_h5_coverage or {}).get(
            "unique_h5_bridge_trade_value_share"
        ),
        "policy": (
            "Primary product-level tariff analysis remains blocked for non-exact HS revision years until "
            "the bridge is reviewed with observed trade-weight coverage and an explicit ambiguous-family policy."
        ),
    }


def hs4_concordance_gate(
    comtrade_summary: dict[str, Any], wits_summary: dict[str, Any], hs4_coverage_summary: dict[str, Any]
) -> dict[str, Any]:
    comtrade_revisions = set(comtrade_summary.get("revisions", []))
    wits_revisions = set(wits_summary.get("nomenclature_codes", []))
    if not comtrade_revisions:
        return {"status": "blocked", "reason": "No local Comtrade HS revision evidence was found."}
    if not wits_revisions:
        return {
            "status": "blocked",
            "reason": "WITS availability was not fetched or contained no nomenclature codes.",
            "comtrade_revisions": sorted(comtrade_revisions),
            "wits_doc_supported_hs": sorted(WITS_DOC_SUPPORTED_HS),
        }
    coverage = hs4_coverage_summary.get("hs4_bridge_trade_value_coverage")
    gate = hs4_coverage_summary.get("hs4_bridge_trade_value_coverage_min_required", HS4_HARMONIZATION_COVERAGE_MIN)
    coverage_passed = hs4_coverage_summary.get("status") == "passed" and coverage is not None and coverage >= gate
    return {
        "status": "ok_hs4_only_h6_excluded" if coverage_passed else "blocked_hs4_coverage_gate_failed",
        "comtrade_revisions": sorted(comtrade_revisions),
        "wits_availability_revisions": sorted(wits_revisions),
        "direct_overlap": sorted(comtrade_revisions & wits_revisions),
        "comtrade_revisions_missing_in_wits_availability": sorted(comtrade_revisions - wits_revisions),
        "hs4_bridge_trade_value_coverage": coverage,
        "hs4_bridge_trade_value_coverage_min_required": gate,
        "h6_policy": "H6 years are excluded from tariff analysis unless a separate HS4 harmonization diagnostic clears them.",
        "policy": (
            "Primary tariff analysis uses harmonized HS4 only. Exact HS revision overlap is not required at HS6, "
            "but the HS4 baseline export-value coverage gate must pass before tariff exposure construction."
        ),
    }


def attach_tariff_mapping_and_revision(
    export_sample: pd.DataFrame, tariff_year_mapping: pd.DataFrame, comtrade_revisions: pd.DataFrame
) -> pd.DataFrame:
    if export_sample.empty:
        return pd.DataFrame()
    base = export_sample.copy()
    base["iso3"] = base["iso3"].astype(str).str.upper()
    base["reporter_code"] = pd.to_numeric(base["reporter_code"], errors="coerce").astype("Int64")
    base["year"] = pd.to_numeric(base["year"], errors="coerce").astype("Int64")

    mapping_cols = [
        "iso3",
        "reporter_code",
        "year",
        "tariff_reporter_code",
        "tariff_reporter_iso3",
        "tariff_reporter_name",
        "customs_mapping_rule",
        "tariff_mapping_status",
        "has_wits_availability_for_year",
        "availability_nomenclature_codes",
        "availability_last_updated_dates",
        "direct_wits_country_code",
        "direct_wits_iso3",
        "direct_wits_is_reporter",
    ]
    mapping = tariff_year_mapping[[col for col in mapping_cols if col in tariff_year_mapping.columns]].copy()
    if not mapping.empty:
        mapping["iso3"] = mapping["iso3"].astype(str).str.upper()
        mapping["reporter_code"] = pd.to_numeric(mapping["reporter_code"], errors="coerce").astype("Int64")
        mapping["year"] = pd.to_numeric(mapping["year"], errors="coerce").astype("Int64")
        base = base.merge(mapping, on=["iso3", "reporter_code", "year"], how="left", validate="one_to_one")
    else:
        base["tariff_mapping_status"] = "missing_tariff_reporter_year_mapping"

    revision_cols = ["reporter_code", "year", "comtrade_hs_revision", "file"]
    revisions = comtrade_revisions[[col for col in revision_cols if col in comtrade_revisions.columns]].copy()
    if not revisions.empty:
        revisions["reporter_code"] = pd.to_numeric(revisions["reporter_code"], errors="coerce").astype("Int64")
        revisions["year"] = pd.to_numeric(revisions["year"], errors="coerce").astype("Int64")
        revisions = revisions.rename(columns={"file": "comtrade_aggregate_file"})
        base = base.merge(revisions, on=["reporter_code", "year"], how="left", validate="many_to_one")
    else:
        base["comtrade_hs_revision"] = ""
        base["comtrade_aggregate_file"] = ""

    if "availability_nomenclature_codes" not in base.columns:
        base["availability_nomenclature_codes"] = ""
    base["availability_nomenclature_codes"] = base["availability_nomenclature_codes"].fillna("").astype(str)
    base["comtrade_hs_revision"] = base["comtrade_hs_revision"].fillna("").astype(str).str.upper()
    base["exact_wits_hs_revision_match"] = base.apply(
        lambda row: row["comtrade_hs_revision"] in split_semicolon_codes(row["availability_nomenclature_codes"]),
        axis=1,
    )
    base["primary_wits_no_h6_bridge"] = ~base["comtrade_hs_revision"].eq("H6")
    base["has_product_gini"] = base["product_gini"].notna() if "product_gini" in base else False
    if "tariff_reporter_code" not in base.columns:
        base["tariff_reporter_code"] = ""
    base["tariff_reporter_code"] = base["tariff_reporter_code"].fillna("").astype(str).map(normalize_wits_country_code)
    return base.sort_values(["iso3", "year"]).reset_index(drop=True)


def primary_wits_exclusion_reason(row: pd.Series) -> str:
    if not bool(row.get("has_product_gini", False)):
        return "missing_product_gini"
    if str(row.get("tariff_mapping_status", "")) != "ok":
        return "missing_wits_reporter_year_availability"
    if not str(row.get("comtrade_hs_revision", "")):
        return "missing_comtrade_revision_file"
    if str(row.get("comtrade_hs_revision", "")) == "H6":
        return "h6_revision_not_allowed_primary"
    if not bool(row.get("exact_wits_hs_revision_match", False)):
        return "comtrade_revision_not_in_wits_availability"
    return "included_primary_wits"


def primary_wits_hs4_exclusion_reason(row: pd.Series) -> str:
    if not bool(row.get("has_product_gini", False)):
        return "missing_product_gini"
    if str(row.get("tariff_mapping_status", "")) != "ok":
        return "missing_wits_reporter_year_availability"
    if not str(row.get("comtrade_hs_revision", "")):
        return "missing_comtrade_revision_file"
    if str(row.get("comtrade_hs_revision", "")) == "H6":
        return "h6_revision_not_allowed_hs4_primary"
    return "included_primary_wits_hs4"


def validate_hs4_harmonization_gate(hs4_coverage_summary: dict[str, Any] | None) -> bool:
    if not hs4_coverage_summary:
        raise ValueError("HS4 harmonization coverage summary is required for HS4 primary samples.")
    coverage = hs4_coverage_summary.get("hs4_bridge_trade_value_coverage")
    gate = hs4_coverage_summary.get("hs4_bridge_trade_value_coverage_min_required", HS4_HARMONIZATION_COVERAGE_MIN)
    if hs4_coverage_summary.get("status") != "passed" or coverage is None or coverage < gate:
        raise ValueError(
            f"HS4 harmonization coverage gate failed: coverage={coverage}, required={gate}."
        )
    return True


def build_referee_calibrated_samples(
    export_sample: pd.DataFrame,
    tariff_year_mapping: pd.DataFrame,
    comtrade_revisions: pd.DataFrame,
    hs4_coverage_summary: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any], str]:
    panel = attach_tariff_mapping_and_revision(export_sample, tariff_year_mapping, comtrade_revisions)
    if panel.empty:
        empty_summary = {
            "status": "blocked_missing_export_sample",
            "primary_wits_hs4_2001_2021": {"rows": 0},
            "primary_wits_hs4_long": {"rows": 0},
            "primary_wits_2001_2021": {"rows": 0},
            "primary_wits": {"rows": 0},
            "agreement_only_full": {"rows": 0},
            "supplement_candidate_gap_years": {"rows": 0},
        }
        return (
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame(),
            empty_summary,
            build_tariff_sample_attrition_markdown(empty_summary),
        )

    panel["primary_wits_exclusion_reason"] = panel.apply(primary_wits_exclusion_reason, axis=1)
    panel["primary_wits_hs4_exclusion_reason"] = panel.apply(primary_wits_hs4_exclusion_reason, axis=1)
    panel["sample_policy"] = "referee_calibrated_two_tier_design"

    agreement = panel.copy()
    agreement["analysis_sample"] = "agreement_only_full"
    agreement["requires_tariff_data"] = False
    agreement["allowed_for_headline_tariff_result"] = False
    agreement["sample_description"] = "Full export-baseline country-year sample for agreement timing/depth measures."

    validate_hs4_harmonization_gate(hs4_coverage_summary)
    primary_hs4_long = panel[panel["primary_wits_hs4_exclusion_reason"].eq("included_primary_wits_hs4")].copy()
    primary_hs4_long["analysis_sample"] = "primary_wits_hs4_long"
    primary_hs4_long["requires_tariff_data"] = True
    primary_hs4_long["tariff_product_level"] = "HS4"
    primary_hs4_long["tariff_product_key"] = "harmonized_hs4"
    primary_hs4_long["allowed_tariff_source"] = "WITS_TRAINS"
    primary_hs4_long["allowed_for_headline_tariff_result"] = False
    primary_hs4_long["preferred_headline_tariff_sample"] = False
    primary_hs4_long["tariff_imputation_allowed"] = False
    primary_hs4_long["carry_forward_allowed"] = False
    primary_hs4_long["hs6_tariff_exposure_allowed"] = False
    primary_hs4_long["h6_bridge_policy"] = "not_used_hs4_only"
    primary_hs4_long["hs4_bridge_trade_value_coverage_min_required"] = HS4_HARMONIZATION_COVERAGE_MIN
    primary_hs4_long["hs4_bridge_trade_value_coverage"] = hs4_coverage_summary.get("hs4_bridge_trade_value_coverage")
    primary_hs4_long["hs4_bridge_trade_value_coverage_status"] = hs4_coverage_summary.get("status")
    primary_hs4_long["tariff_weight_coverage_min_required"] = PRIMARY_TARIFF_WEIGHT_COVERAGE_MIN
    primary_hs4_long["tariff_weight_coverage_status"] = "pending_tariff_pull"
    primary_hs4_long["sample_description"] = (
        "WITS-only HS4 long-window tariff robustness sample; nonmissing outcome, WITS reporter-year availability, "
        "non-H6 local revision, and passing baseline HS4 harmonization coverage."
    )
    validate_primary_wits_hs4_sample(primary_hs4_long)

    primary_hs4_headline = primary_hs4_long[primary_hs4_long["year"].between(2001, 2021)].copy()
    primary_hs4_headline["analysis_sample"] = "primary_wits_hs4_2001_2021"
    primary_hs4_headline["preferred_headline_tariff_sample"] = True
    primary_hs4_headline["allowed_for_headline_tariff_result"] = True
    primary_hs4_headline["source_sample"] = "primary_wits_hs4_long"
    primary_hs4_headline["sample_description"] = (
        "Preferred headline WITS-only HS4 tariff sample: years 2001-2021, nonmissing outcome, WITS "
        "reporter-year availability, no HS6 tariff exposure, and passing baseline HS4 harmonization coverage."
    )
    validate_primary_wits_hs4_sample(primary_hs4_headline)

    primary = panel[panel["primary_wits_exclusion_reason"].eq("included_primary_wits")].copy()
    primary["analysis_sample"] = "primary_wits"
    primary["requires_tariff_data"] = True
    primary["allowed_tariff_source"] = "WITS_TRAINS"
    primary["allowed_for_headline_tariff_result"] = False
    primary["preferred_headline_tariff_sample"] = False
    primary["tariff_imputation_allowed"] = False
    primary["carry_forward_allowed"] = False
    primary["h6_bridge_policy"] = "not_used_in_primary"
    primary["tariff_weight_coverage_min_required"] = PRIMARY_TARIFF_WEIGHT_COVERAGE_MIN
    primary["tariff_weight_coverage_status"] = "pending_tariff_pull"
    primary["sample_description"] = (
        "WITS-only long-window tariff robustness sample with nonmissing outcome and exact HS revision support."
    )
    validate_primary_wits_sample(primary)

    headline_primary = primary[primary["year"].between(2001, 2021)].copy()
    headline_primary["analysis_sample"] = "primary_wits_2001_2021"
    headline_primary["preferred_headline_tariff_sample"] = True
    headline_primary["allowed_for_headline_tariff_result"] = True
    headline_primary["source_sample"] = "primary_wits"
    headline_primary["sample_description"] = (
        "Preferred headline WITS-only tariff sample: strict WITS support, nonmissing outcome, exact HS revision, "
        "and 2001-2021 coverage window."
    )
    validate_primary_wits_sample(headline_primary)

    supplement = panel[panel["tariff_mapping_status"].eq("missing_wits_availability_for_year")].copy()
    supplement["analysis_sample"] = "supplemented_tariff_candidate"
    supplement["supplement_source_candidates"] = "WTO_TTD_ADB"
    supplement["supplement_status"] = "candidate_requires_overlap_validation"
    supplement["tariff_imputation_allowed"] = False
    supplement["carry_forward_allowed"] = False
    supplement["robustness_only"] = True
    supplement["allowed_for_headline_tariff_result"] = False
    supplement["sample_description"] = (
        "WITS gap reporter-years that may enter only after official supplement retrieval and overlap validation."
    )

    summary = summarize_referee_calibrated_samples(
        panel,
        primary_hs4_headline,
        primary_hs4_long,
        headline_primary,
        primary,
        agreement,
        supplement,
        hs4_coverage_summary,
    )
    return (
        primary_hs4_headline,
        primary_hs4_long,
        headline_primary,
        primary,
        agreement,
        supplement,
        summary,
        build_tariff_sample_attrition_markdown(summary),
    )


def summarize_referee_calibrated_samples(
    panel: pd.DataFrame,
    primary_hs4_headline: pd.DataFrame,
    primary_hs4_long: pd.DataFrame,
    headline_primary: pd.DataFrame,
    primary: pd.DataFrame,
    agreement: pd.DataFrame,
    supplement: pd.DataFrame,
    hs4_coverage_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sequential = []
    hs4_sequential = []
    current = panel.copy()

    def add_step(step: str, before: int, after: int) -> None:
        sequential.append({"step": step, "rows_before": int(before), "rows_after": int(after), "rows_dropped": int(before - after)})

    def add_hs4_step(step: str, before: int, after: int) -> None:
        hs4_sequential.append(
            {"step": step, "rows_before": int(before), "rows_after": int(after), "rows_dropped": int(before - after)}
        )

    def share(numerator: int, denominator: int) -> float | None:
        return round(numerator / denominator, 4) if denominator else None

    hs4_current = panel.copy()
    before = len(hs4_current)
    hs4_current = hs4_current[hs4_current["has_product_gini"]].copy()
    add_hs4_step("drop missing product_gini", before, len(hs4_current))
    before = len(hs4_current)
    hs4_current = hs4_current[hs4_current["tariff_mapping_status"].eq("ok")].copy()
    add_hs4_step("keep WITS-available tariff reporter-years", before, len(hs4_current))
    before = len(hs4_current)
    hs4_current = hs4_current[hs4_current["comtrade_hs_revision"].astype(str).ne("")].copy()
    add_hs4_step("keep rows with local Comtrade HS revision evidence", before, len(hs4_current))
    before = len(hs4_current)
    hs4_current = hs4_current[hs4_current["comtrade_hs_revision"].astype(str).ne("H6")].copy()
    add_hs4_step("exclude H6 years from HS4 primary sample", before, len(hs4_current))
    before = len(hs4_current)
    hs4_headline_current = hs4_current[hs4_current["year"].between(2001, 2021)].copy()
    add_hs4_step("keep 2001-2021 headline HS4 window", before, len(hs4_headline_current))

    before = len(current)
    current = current[current["has_product_gini"]].copy()
    add_step("drop missing product_gini", before, len(current))
    before = len(current)
    current = current[current["tariff_mapping_status"].eq("ok")].copy()
    add_step("keep WITS-available tariff reporter-years", before, len(current))
    before = len(current)
    current = current[current["comtrade_hs_revision"].astype(str).ne("")].copy()
    add_step("keep rows with local Comtrade HS revision evidence", before, len(current))
    before = len(current)
    current = current[current["exact_wits_hs_revision_match"]].copy()
    add_step("keep exact WITS-supported HS revision rows", before, len(current))
    before = len(current)
    current = current[current["comtrade_hs_revision"].astype(str).ne("H6")].copy()
    add_step("exclude H6 bridge rows from primary WITS sample", before, len(current))

    reason_counts = panel["primary_wits_exclusion_reason"].value_counts().to_dict()
    hs4_reason_counts = panel["primary_wits_hs4_exclusion_reason"].value_counts().to_dict()
    nonmissing_outcome = panel[panel["has_product_gini"]].copy()
    headline_denominator = nonmissing_outcome[nonmissing_outcome["year"].between(2001, 2021)]
    long_window_denominator = nonmissing_outcome[nonmissing_outcome["year"].between(1988, 2021)]
    full_nonmissing_denominator = nonmissing_outcome
    supplement_year_summary = (
        supplement.groupby("year", as_index=False)
        .agg(missing_reporter_years=("iso3", "size"), countries=("iso3", lambda values: ";".join(sorted(set(map(str, values))))))
        .sort_values("year")
        .to_dict("records")
        if not supplement.empty
        else []
    )
    return {
        "status": "ok",
        "design": "referee_calibrated_two_tier_design",
        "sample_decision_plan": str(DEFENSIBLE_SAMPLE_PLAN_PATH.relative_to(ROOT)),
        "hs4_harmonization": hs4_coverage_summary or {},
        "primary_wits_hs4_2001_2021": {
            "path": str(PRIMARY_WITS_HS4_2001_2021_SAMPLE_PATH.relative_to(ROOT)),
            "rows": int(len(primary_hs4_headline)),
            "countries": int(primary_hs4_headline["iso3"].nunique()) if not primary_hs4_headline.empty else 0,
            "year_min": int(primary_hs4_headline["year"].min()) if not primary_hs4_headline.empty else None,
            "year_max": int(primary_hs4_headline["year"].max()) if not primary_hs4_headline.empty else None,
            "duplicate_iso3_reporter_year_rows": int(
                primary_hs4_headline.duplicated(["iso3", "reporter_code", "year"]).sum()
            ),
            "h6_rows": int(primary_hs4_headline["comtrade_hs_revision"].eq("H6").sum())
            if not primary_hs4_headline.empty
            else 0,
            "denominator_nonmissing_product_gini_rows_2001_2021": int(len(headline_denominator)),
            "share_of_nonmissing_product_gini_rows_2001_2021": share(
                int(len(primary_hs4_headline)), int(len(headline_denominator))
            ),
            "share_of_full_nonmissing_product_gini_rows_1988_2025": share(
                int(len(primary_hs4_headline)), int(len(full_nonmissing_denominator))
            ),
            "tariff_product_level": "HS4",
            "tariff_product_key": "harmonized_hs4",
            "hs6_tariff_exposure_allowed": False,
            "hs4_bridge_trade_value_coverage_min_required": HS4_HARMONIZATION_COVERAGE_MIN,
            "hs4_bridge_trade_value_coverage": (hs4_coverage_summary or {}).get("hs4_bridge_trade_value_coverage"),
            "tariff_weight_coverage_min_required": PRIMARY_TARIFF_WEIGHT_COVERAGE_MIN,
            "tariff_weight_coverage_status": "pending_tariff_pull",
            "headline_sample": True,
            "policy": (
                "Preferred headline tariff sample: WITS only; HS4 only; years 2001-2021; nonmissing product_gini; "
                "WITS reporter-year availability; no tariff imputation; no HS6 tariff exposure."
            ),
        },
        "primary_wits_hs4_long": {
            "path": str(PRIMARY_WITS_HS4_LONG_SAMPLE_PATH.relative_to(ROOT)),
            "rows": int(len(primary_hs4_long)),
            "countries": int(primary_hs4_long["iso3"].nunique()) if not primary_hs4_long.empty else 0,
            "year_min": int(primary_hs4_long["year"].min()) if not primary_hs4_long.empty else None,
            "year_max": int(primary_hs4_long["year"].max()) if not primary_hs4_long.empty else None,
            "duplicate_iso3_reporter_year_rows": int(primary_hs4_long.duplicated(["iso3", "reporter_code", "year"]).sum()),
            "h6_rows": int(primary_hs4_long["comtrade_hs_revision"].eq("H6").sum()) if not primary_hs4_long.empty else 0,
            "denominator_nonmissing_product_gini_rows_1988_2021": int(len(long_window_denominator)),
            "share_of_nonmissing_product_gini_rows_1988_2021": share(
                int(len(primary_hs4_long)), int(len(long_window_denominator))
            ),
            "tariff_product_level": "HS4",
            "tariff_product_key": "harmonized_hs4",
            "hs6_tariff_exposure_allowed": False,
            "hs4_bridge_trade_value_coverage_min_required": HS4_HARMONIZATION_COVERAGE_MIN,
            "hs4_bridge_trade_value_coverage": (hs4_coverage_summary or {}).get("hs4_bridge_trade_value_coverage"),
            "tariff_weight_coverage_min_required": PRIMARY_TARIFF_WEIGHT_COVERAGE_MIN,
            "tariff_weight_coverage_status": "pending_tariff_pull",
            "headline_sample": False,
            "policy": (
                "Long-window WITS-only HS4 tariff robustness sample; nonmissing product_gini; WITS reporter-year "
                "availability; no tariff imputation; no HS6 tariff exposure."
            ),
        },
        "primary_wits_2001_2021": {
            "path": str(PRIMARY_WITS_2001_2021_SAMPLE_PATH.relative_to(ROOT)),
            "rows": int(len(headline_primary)),
            "countries": int(headline_primary["iso3"].nunique()) if not headline_primary.empty else 0,
            "year_min": int(headline_primary["year"].min()) if not headline_primary.empty else None,
            "year_max": int(headline_primary["year"].max()) if not headline_primary.empty else None,
            "duplicate_iso3_reporter_year_rows": int(
                headline_primary.duplicated(["iso3", "reporter_code", "year"]).sum()
            ),
            "h6_rows": int(headline_primary["comtrade_hs_revision"].eq("H6").sum()) if not headline_primary.empty else 0,
            "denominator_nonmissing_product_gini_rows_2001_2021": int(len(headline_denominator)),
            "share_of_nonmissing_product_gini_rows_2001_2021": share(int(len(headline_primary)), int(len(headline_denominator))),
            "tariff_weight_coverage_min_required": PRIMARY_TARIFF_WEIGHT_COVERAGE_MIN,
            "tariff_weight_coverage_status": "pending_tariff_pull",
            "headline_sample": True,
            "policy": (
                "Preferred headline tariff sample: WITS only; years 2001-2021; nonmissing product_gini; "
                "exact WITS HS revision; no tariff imputation; no H6 bridge."
            ),
        },
        "primary_wits": {
            "path": str(PRIMARY_WITS_TARIFF_SAMPLE_PATH.relative_to(ROOT)),
            "rows": int(len(primary)),
            "countries": int(primary["iso3"].nunique()) if not primary.empty else 0,
            "year_min": int(primary["year"].min()) if not primary.empty else None,
            "year_max": int(primary["year"].max()) if not primary.empty else None,
            "duplicate_iso3_reporter_year_rows": int(primary.duplicated(["iso3", "reporter_code", "year"]).sum()),
            "h6_rows": int(primary["comtrade_hs_revision"].eq("H6").sum()) if not primary.empty else 0,
            "denominator_nonmissing_product_gini_rows_1988_2021": int(len(long_window_denominator)),
            "share_of_nonmissing_product_gini_rows_1988_2021": share(int(len(primary)), int(len(long_window_denominator))),
            "tariff_weight_coverage_min_required": PRIMARY_TARIFF_WEIGHT_COVERAGE_MIN,
            "tariff_weight_coverage_status": "pending_tariff_pull",
            "headline_sample": False,
            "policy": (
                "Long-window WITS-only tariff robustness sample; nonmissing product_gini; exact WITS HS revision; "
                "no tariff imputation; no H6 bridge."
            ),
        },
        "agreement_only_full": {
            "path": str(AGREEMENT_ONLY_FULL_SAMPLE_PATH.relative_to(ROOT)),
            "rows": int(len(agreement)),
            "countries": int(agreement["iso3"].nunique()) if not agreement.empty else 0,
            "missing_product_gini_rows": int((~agreement["has_product_gini"]).sum()) if not agreement.empty else 0,
            "policy": "Full export-baseline country-year sample for non-tariff agreement timing/depth diagnostics.",
        },
        "supplement_candidate_gap_years": {
            "path": str(SUPPLEMENT_CANDIDATE_GAP_YEARS_PATH.relative_to(ROOT)),
            "rows": int(len(supplement)),
            "countries": int(supplement["iso3"].nunique()) if not supplement.empty else 0,
            "year_min": int(supplement["year"].min()) if not supplement.empty else None,
            "year_max": int(supplement["year"].max()) if not supplement.empty else None,
            "source_candidates": ["WTO_TTD_ADB"],
            "robustness_only": True,
            "carry_forward_allowed": False,
            "requires_overlap_validation": True,
            "year_summary": supplement_year_summary,
        },
        "attrition": {
            "path": str(TARIFF_SAMPLE_ATTRITION_PATH.relative_to(ROOT)),
            "starting_export_baseline_rows": int(len(panel)),
            "preferred_headline_primary_wits_hs4_2001_2021_rows": int(len(primary_hs4_headline)),
            "primary_wits_hs4_long_rows": int(len(primary_hs4_long)),
            "preferred_headline_primary_wits_2001_2021_rows": int(len(headline_primary)),
            "primary_wits_rows": int(len(primary)),
            "primary_wits_hs4_exclusion_reason_counts": hs4_reason_counts,
            "primary_wits_exclusion_reason_counts": reason_counts,
            "hs4_sequential_steps": hs4_sequential,
            "sequential_steps": sequential,
        },
        "hard_gates": [
            "preferred headline primary_wits_hs4_2001_2021 is restricted to 2001-2021",
            f"HS4 baseline export-value coverage must be >= {HS4_HARMONIZATION_COVERAGE_MIN:.2f}",
            "tariff exposure outputs must be keyed by harmonized_hs4, not HS6",
            "primary_wits rejects tariff_mapping_status != ok",
            "primary_wits rejects H6 bridge rows",
            "product-level tariff inputs reject HS6 999999",
            "tariff joins must include tariff_reporter_code",
        ],
    }


def build_tariff_sample_attrition_markdown(summary: dict[str, Any]) -> str:
    if summary.get("status") != "ok":
        return "# Tariff Sample Attrition\n\nSample construction did not run because the export sample was unavailable.\n"
    attrition = summary["attrition"]
    hs4_headline = summary["primary_wits_hs4_2001_2021"]
    hs4_long = summary["primary_wits_hs4_long"]
    headline = summary["primary_wits_2001_2021"]
    primary = summary["primary_wits"]
    agreement = summary["agreement_only_full"]
    supplement = summary["supplement_candidate_gap_years"]
    hs4_gate = summary.get("hs4_harmonization", {})
    lines = [
        "# Tariff Sample Attrition",
        "",
        "This diagnostics-only artifact implements the referee-calibrated HS4-only sample split. It does not pull tariffs or run regressions.",
        "",
        "## Output Samples",
        "",
        f"- `primary_wits_hs4_2001_2021`: {hs4_headline['rows']} rows, {hs4_headline['countries']} countries, years {hs4_headline['year_min']}--{hs4_headline['year_max']}; preferred headline HS4 tariff sample.",
        f"- `primary_wits_hs4_long`: {hs4_long['rows']} rows, {hs4_long['countries']} countries, years {hs4_long['year_min']}--{hs4_long['year_max']}; long-window HS4 tariff robustness sample.",
        f"- `primary_wits_2001_2021`: {headline['rows']} rows, {headline['countries']} countries, years {headline['year_min']}--{headline['year_max']}; strict exact-revision reference sample.",
        f"- `primary_wits`: {primary['rows']} rows, {primary['countries']} countries, years {primary['year_min']}--{primary['year_max']}; strict exact-revision long-window reference sample.",
        f"- `agreement_only_full`: {agreement['rows']} rows, {agreement['countries']} countries, including {agreement['missing_product_gini_rows']} missing `product_gini` rows.",
        f"- `supplement_candidate_gap_years`: {supplement['rows']} WITS-gap reporter-years, {supplement['countries']} countries, years {supplement['year_min']}--{supplement['year_max']}.",
        "",
        "## Preferred Headline Sample Rule",
        "",
        f"- Use `primary_wits_hs4_2001_2021` for the headline tariff table: {hs4_headline['rows']} of {hs4_headline['denominator_nonmissing_product_gini_rows_2001_2021']} nonmissing export-baseline rows in 2001-2021.",
        f"- Current strict exact-revision reference coverage is `primary_wits_2001_2021`: {headline['rows']} of {headline['denominator_nonmissing_product_gini_rows_2001_2021']} nonmissing export-baseline rows in 2001-2021.",
        f"- Use `primary_wits_hs4_long` as long-window robustness: {hs4_long['rows']} of {hs4_long['denominator_nonmissing_product_gini_rows_1988_2021']} nonmissing export-baseline rows in 1988-2021.",
        "",
        "## HS4 Harmonization Gate",
        "",
        f"- Baseline export-value HS4 coverage: {hs4_gate.get('hs4_bridge_trade_value_coverage')}.",
        f"- Required minimum: {hs4_gate.get('hs4_bridge_trade_value_coverage_min_required')}.",
        f"- Status: {hs4_gate.get('status')}.",
        "- Tariff exposure outputs must be keyed by `harmonized_hs4`, not HS6.",
        "",
        "## Primary WITS HS4 Sequential Attrition",
        "",
        "| Step | Rows Before | Rows After | Rows Dropped |",
        "| --- | ---: | ---: | ---: |",
    ]
    for step in attrition["hs4_sequential_steps"]:
        lines.append(f"| {step['step']} | {step['rows_before']} | {step['rows_after']} | {step['rows_dropped']} |")
    lines.extend(
        [
            "",
            "## Primary WITS HS4 Exclusion Reasons",
            "",
            "| Reason | Rows |",
            "| --- | ---: |",
        ]
    )
    for reason, rows in sorted(attrition["primary_wits_hs4_exclusion_reason_counts"].items()):
        lines.append(f"| `{reason}` | {rows} |")
    lines.extend(
        [
            "",
            "## Strict Exact-Revision Reference Attrition",
            "",
            "| Step | Rows Before | Rows After | Rows Dropped |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for step in attrition["sequential_steps"]:
        lines.append(f"| {step['step']} | {step['rows_before']} | {step['rows_after']} | {step['rows_dropped']} |")
    lines.extend(
        [
            "",
            "## Primary WITS Exclusion Reasons",
            "",
            "| Reason | Rows |",
            "| --- | ---: |",
        ]
    )
    for reason, rows in sorted(attrition["primary_wits_exclusion_reason_counts"].items()):
        lines.append(f"| `{reason}` | {rows} |")
    lines.extend(
        [
            "",
            "## Gates",
            "",
            f"- HS4 baseline export-value coverage must be `>= {HS4_HARMONIZATION_COVERAGE_MIN:.2f}` before tariff pulls.",
            f"- Primary tariff exposure must require `tariff_weight_coverage_i,t >= {PRIMARY_TARIFF_WEIGHT_COVERAGE_MIN:.2f}` after tariff pulls.",
            "- Tariff exposure outputs must be keyed by `harmonized_hs4`; HS6-keyed tariff outputs are not allowed.",
            "- Carry-forward tariffs are not allowed in the primary specification.",
            "- WTO/ADB supplement rows are robustness-only until overlap validation succeeds.",
            "- H6-to-H5 one-code assignment and HS6-level tariff exposure are not allowed.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_primary_wits_sample(sample: pd.DataFrame) -> bool:
    required = {
        "iso3",
        "reporter_code",
        "year",
        "product_gini",
        "tariff_mapping_status",
        "tariff_reporter_code",
        "comtrade_hs_revision",
        "exact_wits_hs_revision_match",
    }
    missing = sorted(required - set(sample.columns))
    if missing:
        raise ValueError(f"Primary WITS sample is missing required columns: {missing}")
    if sample.duplicated(["iso3", "reporter_code", "year"]).any():
        raise ValueError("Primary WITS sample has duplicate iso3-reporter_code-year keys.")
    bad_status = sample[~sample["tariff_mapping_status"].eq("ok")]
    if not bad_status.empty:
        raise ValueError("Primary WITS sample contains tariff reporter-years without WITS availability.")
    missing_outcome = sample[sample["product_gini"].isna()]
    if not missing_outcome.empty:
        raise ValueError("Primary WITS sample contains missing product_gini rows.")
    h6_rows = sample[sample["comtrade_hs_revision"].astype(str).eq("H6")]
    if not h6_rows.empty:
        raise ValueError("Primary WITS sample cannot contain H6 rows or use the H6 bridge.")
    bad_revision = sample[~sample["exact_wits_hs_revision_match"].fillna(False)]
    if not bad_revision.empty:
        raise ValueError("Primary WITS sample contains rows without exact WITS HS revision support.")
    missing_tariff_code = sample[sample["tariff_reporter_code"].fillna("").astype(str).eq("")]
    if not missing_tariff_code.empty:
        raise ValueError("Primary WITS sample contains missing WITS tariff_reporter_code values.")
    return True


def validate_primary_wits_hs4_sample(sample: pd.DataFrame) -> bool:
    required = {
        "iso3",
        "reporter_code",
        "year",
        "product_gini",
        "tariff_mapping_status",
        "tariff_reporter_code",
        "comtrade_hs_revision",
        "tariff_product_level",
        "tariff_product_key",
        "hs6_tariff_exposure_allowed",
    }
    missing = sorted(required - set(sample.columns))
    if missing:
        raise ValueError(f"Primary WITS HS4 sample is missing required columns: {missing}")
    if sample.duplicated(["iso3", "reporter_code", "year"]).any():
        raise ValueError("Primary WITS HS4 sample has duplicate iso3-reporter_code-year keys.")
    bad_status = sample[~sample["tariff_mapping_status"].eq("ok")]
    if not bad_status.empty:
        raise ValueError("Primary WITS HS4 sample contains tariff reporter-years without WITS availability.")
    missing_outcome = sample[sample["product_gini"].isna()]
    if not missing_outcome.empty:
        raise ValueError("Primary WITS HS4 sample contains missing product_gini rows.")
    h6_rows = sample[sample["comtrade_hs_revision"].astype(str).eq("H6")]
    if not h6_rows.empty:
        raise ValueError("Primary WITS HS4 sample cannot contain H6 rows.")
    if not sample["tariff_product_level"].eq("HS4").all():
        raise ValueError("Primary WITS HS4 sample must use tariff_product_level == HS4.")
    if not sample["tariff_product_key"].eq("harmonized_hs4").all():
        raise ValueError("Primary WITS HS4 sample must use harmonized_hs4 as the tariff product key.")
    if sample["hs6_tariff_exposure_allowed"].astype(bool).any():
        raise ValueError("Primary WITS HS4 sample cannot allow HS6 tariff exposure.")
    missing_tariff_code = sample[sample["tariff_reporter_code"].fillna("").astype(str).eq("")]
    if not missing_tariff_code.empty:
        raise ValueError("Primary WITS HS4 sample contains missing WITS tariff_reporter_code values.")
    return True


def assert_no_product_level_999999(frame: pd.DataFrame, code_col: str = "cmd_code") -> bool:
    if code_col not in frame.columns:
        raise ValueError(f"Product-level input is missing `{code_col}`.")
    codes = frame[code_col].map(normalize_hs6_code)
    if codes.isin(EXCLUDED_HS6_CODES).any():
        raise ValueError("Product-level tariff/market-access input contains HS6 999999.")
    return True


def validate_hs4_tariff_output_keys(keys: list[str] | tuple[str, ...] | set[str]) -> bool:
    key_set = set(keys)
    hs6_like = {"cmd_code", "hs6", "h6_cmd_code", "product_hs6"}
    disallowed = sorted(key_set & hs6_like)
    if disallowed:
        raise ValueError(f"HS4 tariff exposure output cannot be keyed by HS6 columns: {disallowed}")
    if "harmonized_hs4" not in key_set:
        raise ValueError("HS4 tariff exposure output must include harmonized_hs4.")
    if "tariff_reporter_code" not in key_set:
        raise ValueError("HS4 tariff joins must use WITS tariff_reporter_code.")
    if "year" not in key_set:
        raise ValueError("HS4 tariff joins must include year.")
    return True


def validate_h6_bridge_policy(bridge: pd.DataFrame, policy: str = "primary_wits") -> bool:
    if policy == "harmonized_family_extension":
        if "harmonized_product_id" not in bridge.columns:
            raise ValueError("Harmonized-family extension requires harmonized_product_id.")
        return True
    if "bridge_status" not in bridge.columns:
        raise ValueError("H6 bridge input is missing bridge_status.")
    bad = bridge[~bridge["bridge_status"].eq("unique_family_bridge")]
    if not bad.empty:
        raise ValueError("H6 bridge contains ambiguous or missing target rows; use harmonized_family_extension explicitly.")
    return True


def validate_tariff_join_keys(join_keys: list[str] | tuple[str, ...] | set[str]) -> bool:
    keys = set(join_keys)
    if "tariff_reporter_code" not in keys:
        raise ValueError("Tariff joins must use WITS tariff_reporter_code.")
    if "reporter_code" in keys and "tariff_reporter_code" not in keys:
        raise ValueError("Tariff joins cannot use Comtrade reporter_code without WITS tariff_reporter_code.")
    if "year" not in keys:
        raise ValueError("Tariff joins must include year.")
    return True


def sample_wits_tariff_api(timeout: int) -> dict[str, Any]:
    content, info = request_bytes(WITS_SAMPLE_TARIFF_URL, timeout)
    result = {"source": "wits_sample_tariff_api", "url": WITS_SAMPLE_TARIFF_URL, "request": info}
    if content is None:
        result["status"] = "failed"
        return result
    try:
        payload = json.loads(content.decode("utf-8-sig"))
        result["status"] = "ok"
        result["header_id"] = payload.get("header", {}).get("id", "")
        result["prepared"] = payload.get("header", {}).get("prepared", "")
        result["structure_name"] = payload.get("structure", {}).get("name", "")
    except json.JSONDecodeError as exc:
        result["status"] = "parse_failed"
        result["error"] = repr(exc)
    return result


def build_diagnostics_markdown(diagnostics: dict[str, Any]) -> str:
    sample = diagnostics["sample"]
    crosswalk = diagnostics["crosswalk"]
    tariff_year = diagnostics.get("tariff_reporter_year_mapping", {})
    wits = diagnostics["wits_availability"]
    hs_gate = diagnostics["hs_concordance_gate"]
    gap_summary = diagnostics.get("wits_tariff_reporter_year_availability_gaps", {})
    referee_samples = diagnostics.get("referee_calibrated_samples", {})
    hs4_gate = referee_samples.get("hs4_harmonization", {})
    primary_hs4 = referee_samples.get("primary_wits_hs4_2001_2021", {})
    primary_hs4_long = referee_samples.get("primary_wits_hs4_long", {})
    headline_primary = referee_samples.get("primary_wits_2001_2021", {})
    primary_wits = referee_samples.get("primary_wits", {})
    agreement_full = referee_samples.get("agreement_only_full", {})
    supplement_candidates = referee_samples.get("supplement_candidate_gap_years", {})
    lines = [
        "# Trade Deal Market Access Diagnostics",
        "",
        "This diagnostics-only run prepares source and merge checks. It does not build tariff exposures or regressions.",
        "",
        "## Sample",
        "",
        f"- Source: `{sample.get('path')}`",
        f"- Export-baseline rows: {sample.get('export_baseline_rows')}",
        f"- Reporters: {sample.get('reporters')}",
        f"- Years: {sample.get('year_min')}--{sample.get('year_max')}",
        f"- Duplicate `iso3-reporter_code-year` rows: {sample.get('duplicate_iso3_reporter_year_rows')}",
        f"- Missing `product_gini` rows: {sample.get('missing_product_gini_rows')}",
        "",
        "## Country Crosswalk",
        "",
        f"- Rows: {crosswalk.get('rows')}",
        f"- Missing WITS metadata rows: {crosswalk.get('missing_wits_metadata_rows')}",
        f"- Missing WITS country-code rows: {crosswalk.get('missing_wits_code_rows')}",
        f"- ISO3 fallback rows: {crosswalk.get('iso3_fallback_rows')}",
        f"- EU customs-territory mapping rows: {crosswalk.get('eu_customs_mapping_rows')}",
        f"- Missing tariff-reporter rows after mapping: {crosswalk.get('missing_tariff_reporter_rows')}",
        f"- Non-exact WITS matches including acceptable ISO3 fallbacks: {crosswalk.get('non_exact_wits_matches')}",
        "",
        "## Year-Specific Tariff Reporter Mapping",
        "",
        f"- Status: {tariff_year.get('status')}",
        f"- Output: `{tariff_year.get('path')}`",
        f"- Rows: {tariff_year.get('rows')}",
        f"- Duplicate `iso3-reporter_code-year` rows: {tariff_year.get('duplicate_iso3_reporter_year_rows')}",
        f"- Missing tariff reporter rows: {tariff_year.get('missing_tariff_reporter_rows')}",
        f"- Missing WITS availability reporter-year rows: {tariff_year.get('missing_wits_availability_year_rows')}",
        f"- Availability gaps table: `{gap_summary.get('gap_path')}`",
        f"- Availability gap summary: `{gap_summary.get('summary_path')}`",
        f"- EU customs-territory active rows: {tariff_year.get('eu_customs_territory_active_rows')}",
        f"- Pre-accession direct rows: {tariff_year.get('pre_accession_direct_rows')}",
        f"- Post-EU-customs-exit direct rows: {tariff_year.get('post_eu_customs_exit_direct_rows')}",
        "",
        "## WITS Preflight",
        "",
        f"- Status: {wits.get('status')}",
        f"- Availability rows: {wits.get('rows')}",
        f"- Reporters with availability: {wits.get('reporters_with_availability')}",
        f"- Reporters without availability: {', '.join(wits.get('reporters_without_availability', [])) or 'none'}",
        f"- Tariff reporter-code mappings with availability: {wits.get('tariff_reporter_code_mappings_with_availability')}",
        f"- Nomenclature codes: {', '.join(wits.get('nomenclature_codes', [])) or 'none'}",
        "",
        "## Referee-Calibrated Samples",
        "",
        f"- Sample decision plan: `{referee_samples.get('sample_decision_plan')}`",
        f"- Preferred headline WITS HS4 tariff sample: {primary_hs4.get('rows')} rows, output `{primary_hs4.get('path')}`",
        f"- Long-window WITS HS4 robustness sample: {primary_hs4_long.get('rows')} rows, output `{primary_hs4_long.get('path')}`",
        f"- Strict exact-revision reference sample: {headline_primary.get('rows')} rows, output `{headline_primary.get('path')}`",
        f"- Strict exact-revision long-window reference: {primary_wits.get('rows')} rows, output `{primary_wits.get('path')}`",
        f"- Agreement-only full sample: {agreement_full.get('rows')} rows, output `{agreement_full.get('path')}`",
        f"- Supplement candidate gap years: {supplement_candidates.get('rows')} rows, output `{supplement_candidates.get('path')}`",
        f"- Attrition report: `{referee_samples.get('attrition', {}).get('path')}`",
        f"- HS4 baseline export-value coverage: {hs4_gate.get('hs4_bridge_trade_value_coverage')}",
        f"- HS4 coverage gate: {hs4_gate.get('hs4_bridge_trade_value_coverage_min_required')}",
        f"- Primary tariff-weight coverage gate: {primary_hs4.get('tariff_weight_coverage_min_required')}",
        "",
        "## HS4 Harmonization",
        "",
        f"- Family crosswalk: `{diagnostics.get('hs_family_crosswalk', {}).get('path')}`",
        f"- Baseline HS4 coverage table: `{hs4_gate.get('path')}`",
        f"- HS4 coverage status: {hs4_gate.get('status')}",
        f"- Product key for tariff exposures: `harmonized_hs4`",
        f"- HS6 tariff exposure allowed: {primary_hs4.get('hs6_tariff_exposure_allowed')}",
        "",
        "## HS Concordance Gate",
        "",
        f"- Status: {hs_gate.get('status')}",
        f"- Comtrade revisions: {', '.join(hs_gate.get('comtrade_revisions', [])) or 'none'}",
        f"- WITS revisions: {', '.join(hs_gate.get('wits_availability_revisions', [])) or 'none'}",
        f"- Policy: {hs_gate.get('policy', hs_gate.get('reason', ''))}",
        "",
        "## Next Safe Step",
        "",
        "- Use the year-specific tariff reporter mapping for future tariff pulls; do not revert to country defaults.",
        "- Build tariff exposure at harmonized HS4 only; do not create HS6-keyed tariff exposure outputs.",
        "- Resolve WITS year gaps through validated WTO/ADB supplement only for robustness.",
        "- Keep outputs diagnostics-only until an adversarial econometrics review clears the data path.",
        "",
    ]
    return "\n".join(lines)


def run(args: argparse.Namespace) -> dict[str, Any]:
    ensure_dirs()
    rd2 = rd2_country_frame()
    export_sample = load_export_baseline_sample()

    source_downloads: list[dict[str, Any]] = []
    if args.download_source_snapshots:
        for spec in SOURCE_DOWNLOADS:
            source_downloads.append(download_snapshot(spec, refresh=args.refresh_network, timeout=args.timeout))
    else:
        for spec in SOURCE_DOWNLOADS:
            source_downloads.append(
                {
                    "source": spec.source,
                    "url": spec.url,
                    "downloaded": False,
                    "download_skipped": True,
                    "required_for_primary": spec.required_for_primary,
                    **source_file_manifest(spec.output),
                }
            )

    source_pages = []
    if args.refresh_network:
        for name, url in SOURCE_PAGES.items():
            source_pages.append(check_url_status(name, url, timeout=args.timeout))
    else:
        source_pages = [{"source": name, "url": url, "status": "not_checked"} for name, url in SOURCE_PAGES.items()]

    sample = sample_diagnostics(export_sample)
    wits_countries, wits_country_manifest = fetch_wits_country_metadata(refresh=args.refresh_network, timeout=args.timeout)
    crosswalk = build_country_crosswalk(rd2, wits_countries)
    crosswalk_path = PROCESSED_DIR / "trade_deal_country_code_crosswalk.csv"
    crosswalk.to_csv(crosswalk_path, index=False)

    preliminary_tariff_year_mapping = build_tariff_reporter_year_mapping(export_sample, crosswalk, pd.DataFrame())
    tariff_reporter_codes = (
        preliminary_tariff_year_mapping["tariff_reporter_code"]
        .dropna()
        .map(normalize_wits_country_code)
        .loc[lambda s: s.ne("")]
        .drop_duplicates()
        .tolist()
        if not preliminary_tariff_year_mapping.empty
        else []
    )
    if args.wits_preflight:
        availability, availability_manifests = fetch_wits_availability_by_codes(
            tariff_reporter_codes,
            refresh=args.refresh_network,
            timeout=args.timeout,
            max_reporters=args.max_wits_reporters,
        )
    else:
        availability = pd.DataFrame()
        availability_manifests = [{"status": "not_run", "reason": "Run with --wits-preflight to fetch availability."}]
    availability_path = PROCESSED_DIR / "trade_deal_wits_trains_availability_rd2.csv"
    availability.to_csv(availability_path, index=False)
    tariff_year_mapping = build_tariff_reporter_year_mapping(export_sample, crosswalk, availability)
    tariff_year_mapping_path = PROCESSED_DIR / "trade_deal_tariff_reporter_year_mapping.csv"
    tariff_year_mapping.to_csv(tariff_year_mapping_path, index=False)
    availability_gaps, availability_gap_summary, availability_gap_manifest = build_wits_availability_gap_tables(
        tariff_year_mapping
    )
    availability_gaps.to_csv(PROCESSED_DIR / "trade_deal_wits_tariff_reporter_year_availability_gaps.csv", index=False)
    availability_gap_summary.to_csv(
        PROCESSED_DIR / "trade_deal_wits_tariff_reporter_year_availability_gap_summary.csv", index=False
    )

    comtrade_revisions, comtrade_summary = scan_comtrade_hs_revisions()
    hs_revision_path = PROCESSED_DIR / "trade_deal_hs_revision_diagnostics.csv"
    comtrade_revisions.to_csv(hs_revision_path, index=False)

    wits_summary = summarize_wits_availability(availability, crosswalk, tariff_year_mapping)
    tariff_year_summary = summarize_tariff_reporter_year_mapping(
        tariff_year_mapping, availability_checked=args.wits_preflight
    )
    hs_family, hs_family_manifest = load_hs_family_crosswalk()
    hs_family_path = PROCESSED_DIR / "trade_deal_hs6_revision_family_crosswalk.csv"
    hs_family.to_csv(hs_family_path, index=False)
    hs_family_summary = {
        **hs_family_manifest,
        "path": str(hs_family_path.relative_to(ROOT)),
        "source_path": str(LT_HGL_WEIGHT_MAPPING_PATH.relative_to(ROOT)),
    }
    hs4_coverage, hs4_coverage_summary = summarize_hs4_baseline_harmonization_coverage(comtrade_revisions, hs_family)
    hs4_coverage.to_csv(HS4_BASELINE_HARMONIZATION_COVERAGE_PATH, index=False)

    (
        primary_wits_hs4_headline_sample,
        primary_wits_hs4_long_sample,
        headline_primary_wits_sample,
        primary_wits_sample,
        agreement_only_full_sample,
        supplement_candidate_gap_years,
        tariff_sample_summary,
        attrition_md,
    ) = build_referee_calibrated_samples(
        export_sample, tariff_year_mapping, comtrade_revisions, hs4_coverage_summary
    )
    primary_wits_hs4_headline_sample.to_parquet(PRIMARY_WITS_HS4_2001_2021_SAMPLE_PATH, index=False)
    primary_wits_hs4_long_sample.to_parquet(PRIMARY_WITS_HS4_LONG_SAMPLE_PATH, index=False)
    headline_primary_wits_sample.to_parquet(PRIMARY_WITS_2001_2021_SAMPLE_PATH, index=False)
    primary_wits_sample.to_parquet(PRIMARY_WITS_TARIFF_SAMPLE_PATH, index=False)
    agreement_only_full_sample.to_parquet(AGREEMENT_ONLY_FULL_SAMPLE_PATH, index=False)
    supplement_candidate_gap_years.to_csv(SUPPLEMENT_CANDIDATE_GAP_YEARS_PATH, index=False)
    TARIFF_SAMPLE_ATTRITION_PATH.write_text(attrition_md, encoding="utf-8")

    hs_gate = hs4_concordance_gate(comtrade_summary, wits_summary, hs4_coverage_summary)
    wits_sample = sample_wits_tariff_api(args.timeout) if args.refresh_network else {"status": "not_checked"}

    crosswalk_summary = {
        "path": str(crosswalk_path.relative_to(ROOT)),
        "rows": int(len(crosswalk)),
        "missing_wits_metadata_rows": int(crosswalk["wits_match_status"].eq("missing_wits_metadata").sum())
        if "wits_match_status" in crosswalk
        else None,
        "missing_wits_code_rows": int(crosswalk["wits_match_status"].eq("missing_wits_code").sum()),
        "iso3_fallback_rows": int(crosswalk["wits_match_status"].eq("iso3_match_different_numeric_code").sum()),
        "eu_customs_mapping_rows": int(
            crosswalk["tariff_reporter_mapping_status"].eq("needs_year_specific_eu_customs_mapping").sum()
        ),
        "missing_tariff_reporter_rows": int(crosswalk["tariff_reporter_mapping_status"].eq("missing_tariff_reporter").sum()),
        "non_exact_wits_matches": int((crosswalk["wits_match_status"] != "exact_code_iso3_match").sum()),
        "match_status_counts": crosswalk["wits_match_status"].value_counts().to_dict(),
        "tariff_reporter_mapping_status_counts": crosswalk["tariff_reporter_mapping_status"].value_counts().to_dict(),
    }

    diagnostics = {
        "created_at_utc": now_utc(),
        "country_sample": COUNTRY_SAMPLE,
        "script": str(Path(__file__).resolve().relative_to(ROOT)),
        "sample_decision_plan": str(DEFENSIBLE_SAMPLE_PLAN_PATH.relative_to(ROOT)),
        "diagnostics_only": True,
        "sample": sample,
        "crosswalk": crosswalk_summary,
        "tariff_reporter_year_mapping": tariff_year_summary,
        "wits_tariff_reporter_year_availability_gaps": availability_gap_manifest,
        "wits_country_metadata": wits_country_manifest,
        "wits_availability": wits_summary,
        "wits_availability_manifests": availability_manifests,
        "wits_sample_tariff_api": wits_sample,
        "comtrade_hs_revisions": comtrade_summary,
        "referee_calibrated_samples": tariff_sample_summary,
        "hs_family_crosswalk": hs_family_summary,
        "h6_to_wits_revision_bridge": {
            "status": "not_run_hs4_only_policy",
            "policy": "No HS6 tariff exposure or H6-to-H5 one-code bridge is built for the HS4-only tariff plan.",
        },
        "observed_h6_h5_bridge_coverage": {
            "status": "not_run_hs4_only_policy",
            "policy": "H6 years are excluded unless a separate HS4 harmonization diagnostic clears them.",
        },
        "hs_concordance_gate": hs_gate,
        "hs_source_files": hs_source_file_manifests(),
        "source_downloads": source_downloads,
        "source_pages": source_pages,
        "blockers": [
            item
            for item in [
                "missing_concentration_panel" if sample.get("status", "").startswith("blocker") else "",
                "missing_or_incomplete_wits_country_metadata"
                if (crosswalk_summary["missing_wits_metadata_rows"] or 0) != 0
                or crosswalk_summary["missing_tariff_reporter_rows"] != 0
                else "",
                "year_specific_tariff_reporter_mapping_failed"
                if tariff_year_summary.get("status") == "blocked_missing_year_tariff_reporter"
                else "",
                "wits_tariff_reporter_year_availability_gaps"
                if tariff_year_summary.get("status") == "mapping_complete_with_wits_year_availability_gaps"
                else "",
                "wits_nomenclature_availability_missing"
                if hs_gate.get("reason") == "WITS availability was not fetched or contained no nomenclature codes."
                else "",
                "hs4_harmonization_coverage_gate_failed"
                if hs_gate.get("status") == "blocked_hs4_coverage_gate_failed"
                else "",
                "hs4_harmonization_not_passed"
                if tariff_sample_summary.get("hs4_harmonization", {}).get("status") != "passed"
                else "",
                "wits_availability_not_complete"
                if wits_summary.get("reporters_without_availability")
                else "",
            ]
            if item
        ],
        "planned_outputs_not_created_yet": [
            "data/processed/samples/rd2_countries/trade_deal_market_access_panel.parquet",
            "regression tables",
        ],
    }
    write_json(PROCESSED_DIR / "trade_deal_market_access_diagnostics.json", diagnostics)
    write_json(RESULTS_DIR / "source_manifest.json", diagnostics)
    (RESULTS_DIR / "diagnostics.md").write_text(build_diagnostics_markdown(diagnostics), encoding="utf-8")

    if args.fail_on_blocker and diagnostics["blockers"]:
        raise SystemExit(f"Diagnostics completed with blockers: {diagnostics['blockers']}")
    return diagnostics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-network", action="store_true", help="Refresh small remote metadata/status checks.")
    parser.add_argument("--wits-preflight", action="store_true", help="Fetch WITS TRAINS availability for rd2 reporters.")
    parser.add_argument(
        "--download-source-snapshots",
        action="store_true",
        help="Download known public source files for Larch/DESTA/DTA into data/raw.",
    )
    parser.add_argument("--timeout", type=int, default=60, help="HTTP timeout in seconds.")
    parser.add_argument("--max-wits-reporters", type=int, default=None, help="Limit WITS availability reporters for debugging.")
    parser.add_argument(
        "--skip-observed-h6-coverage",
        action="store_true",
        help="Skip scanning H6 aggregate parquet files for observed H6-to-H5 bridge coverage.",
    )
    parser.add_argument("--fail-on-blocker", action="store_true", help="Exit nonzero if blocker diagnostics remain.")
    return parser.parse_args()


def main() -> None:
    diagnostics = run(parse_args())
    print(json.dumps({"created_at_utc": diagnostics["created_at_utc"], "blockers": diagnostics["blockers"]}, indent=2))


if __name__ == "__main__":
    main()
