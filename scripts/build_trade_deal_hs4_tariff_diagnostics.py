#!/usr/bin/env python3
"""Build HS4-only WITS tariff diagnostics for trade-deal market access.

This runner creates diagnostics-ready HS4 tariff inputs for the
primary_wits_hs4_2001_2021 sample. It does not run regressions. WITS serves
tariff observations at native source product codes, so raw API snapshots may
contain six-digit product codes for provenance, but all processed analytical
outputs are keyed only by harmonized_hs4.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
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

import build_trade_deal_market_access_diagnostics as base  # noqa: E402

COUNTRY_SAMPLE = "rd2_countries"
PROCESSED_DIR = ROOT / "data" / "processed" / "samples" / COUNTRY_SAMPLE
RESULTS_DIR = ROOT / "results" / "samples" / COUNTRY_SAMPLE / "trade_deal_market_access"
COMTRADE_AGG_DIR = PROCESSED_DIR / "exercise_02_12_file_aggregates"
PARTNER_REFERENCE_PATH = ROOT / "data" / "raw" / "comtrade" / "partner_reference.csv"

PRIMARY_SAMPLE_PATH = PROCESSED_DIR / "primary_wits_hs4_2001_2021_sample.parquet"
HS4_BASELINE_COVERAGE_PATH = PROCESSED_DIR / "trade_deal_hs4_baseline_harmonization_coverage.csv"

BASELINE_WEIGHTS_PATH = PROCESSED_DIR / "trade_deal_hs4_baseline_weights.parquet"
DESTINATION_MAPPING_PATH = PROCESSED_DIR / "trade_deal_hs4_destination_tariff_mapping.csv"
PULL_SKELETON_PATH = PROCESSED_DIR / "trade_deal_hs4_wits_pull_skeleton.parquet"
REQUEST_HS4_PATH = PROCESSED_DIR / "trade_deal_hs4_wits_request_products.parquet"
HS4_TARIFFS_PATH = PROCESSED_DIR / "trade_deal_wits_hs4_tariffs_aveestimated.parquet"
COVERAGE_PATH = PROCESSED_DIR / "trade_deal_hs4_tariff_coverage_by_exporter_year.csv"
DIAGNOSTICS_PANEL_PATH = PROCESSED_DIR / "trade_deal_hs4_market_access_diagnostics_panel.parquet"
COVERAGE_PASS_SAMPLE_PATH = PROCESSED_DIR / "primary_wits_hs4_2001_2021_tariff_coverage_pass_sample.parquet"
UNCOVERED_DECOMPOSITION_PATH = PROCESSED_DIR / "trade_deal_hs4_uncovered_weight_decomposition.csv"
DESTINATION_UNCOVERED_AUDIT_PATH = PROCESSED_DIR / "trade_deal_hs4_uncovered_destination_audit.csv"
MANIFEST_PATH = PROCESSED_DIR / "trade_deal_hs4_tariff_diagnostics_manifest.json"
MARKDOWN_PATH = RESULTS_DIR / "hs4_tariff_diagnostics.md"

RAW_CACHE_DIR = base.WITS_RAW_DIR / "hs4_diagnostics" / "aveestimated"
RAW_MANIFEST_PATH = RAW_CACHE_DIR / "manifest.csv"

WITS_TARIFF_URL = (
    "https://wits.worldbank.org/API/V1/SDMX/V21/datasource/TRN/reporter/{reporter}/"
    "partner/000/product/all/year/{year}/datatype/{datatype}?format=JSON"
)
WITS_DATAAVAILABILITY_URL = (
    "https://wits.worldbank.org/API/V1/wits/datasource/trn/dataavailability/country/{country}/year/all"
)

DEFAULT_DATATYPE = "AVEEstimated"
DATATYPE = DEFAULT_DATATYPE
PARTNER_WORLD = "000"
HS4_HARMONIZATION_COVERAGE_MIN = 0.90
TARIFF_WEIGHT_COVERAGE_MIN = 0.80


def datatype_slug(datatype: str) -> str:
    slug = "".join(char.lower() if char.isalnum() else "_" for char in str(datatype)).strip("_")
    return slug or "unknown"


def datatype_suffix(datatype: str) -> str:
    slug = datatype_slug(datatype)
    return "" if slug == datatype_slug(DEFAULT_DATATYPE) else f"_{slug}"


def tariff_rate_column(datatype: str | None = None) -> str:
    return f"tariff_{datatype_slug(datatype or DATATYPE)}"


def datatype_unavailable_reason(datatype: str | None = None) -> str:
    return f"{datatype_slug(datatype or DATATYPE)}_unavailable_or_no_wits_year"


def configure_runtime_datatype(datatype: str) -> None:
    """Configure datatype-specific outputs while preserving legacy AVE names."""
    global DATATYPE
    global PULL_SKELETON_PATH
    global REQUEST_HS4_PATH
    global HS4_TARIFFS_PATH
    global COVERAGE_PATH
    global DIAGNOSTICS_PANEL_PATH
    global COVERAGE_PASS_SAMPLE_PATH
    global UNCOVERED_DECOMPOSITION_PATH
    global DESTINATION_UNCOVERED_AUDIT_PATH
    global MANIFEST_PATH
    global MARKDOWN_PATH
    global RAW_CACHE_DIR
    global RAW_MANIFEST_PATH

    DATATYPE = str(datatype)
    suffix = datatype_suffix(DATATYPE)
    slug = datatype_slug(DATATYPE)

    PULL_SKELETON_PATH = PROCESSED_DIR / f"trade_deal_hs4_wits_pull_skeleton{suffix}.parquet"
    REQUEST_HS4_PATH = PROCESSED_DIR / f"trade_deal_hs4_wits_request_products{suffix}.parquet"
    HS4_TARIFFS_PATH = PROCESSED_DIR / f"trade_deal_wits_hs4_tariffs_{slug}.parquet"
    COVERAGE_PATH = PROCESSED_DIR / f"trade_deal_hs4_tariff_coverage_by_exporter_year{suffix}.csv"
    DIAGNOSTICS_PANEL_PATH = PROCESSED_DIR / f"trade_deal_hs4_market_access_diagnostics_panel{suffix}.parquet"
    COVERAGE_PASS_SAMPLE_PATH = (
        PROCESSED_DIR / f"primary_wits_hs4_2001_2021_tariff_coverage_pass_sample{suffix}.parquet"
    )
    UNCOVERED_DECOMPOSITION_PATH = PROCESSED_DIR / f"trade_deal_hs4_uncovered_weight_decomposition{suffix}.csv"
    DESTINATION_UNCOVERED_AUDIT_PATH = PROCESSED_DIR / f"trade_deal_hs4_uncovered_destination_audit{suffix}.csv"
    MANIFEST_PATH = PROCESSED_DIR / f"trade_deal_hs4_tariff_diagnostics_manifest{suffix}.json"
    MARKDOWN_PATH = RESULTS_DIR / f"hs4_tariff_diagnostics{suffix}.md"
    RAW_CACHE_DIR = base.WITS_RAW_DIR / "hs4_diagnostics" / slug
    RAW_MANIFEST_PATH = RAW_CACHE_DIR / "manifest.csv"


@dataclass(frozen=True)
class TariffRequest:
    tariff_reporter_code: str
    tariff_reporter_iso3: str
    tariff_reporter_name: str
    year: int
    url: str
    raw_path: Path


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def ensure_dirs() -> None:
    for path in [PROCESSED_DIR, RESULTS_DIR, RAW_CACHE_DIR, base.WITS_AVAILABILITY_DIR]:
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


def normalize_3digit(value: Any) -> str:
    return base.normalize_digit_code(value, digits=3)


def normalize_hs6(value: Any) -> str:
    return base.normalize_hs6_code(value)


def harmonized_hs4(value: Any) -> str:
    return base.harmonized_hs4_from_hs6(value)


def parse_baseline_years(value: Any) -> list[int]:
    if value is None or pd.isna(value):
        return []
    years: list[int] = []
    for part in str(value).split(";"):
        part = part.strip()
        if part.isdigit():
            years.append(int(part))
    return sorted(set(years))


def read_primary_sample() -> pd.DataFrame:
    sample = pd.read_parquet(PRIMARY_SAMPLE_PATH)
    expected = {"reporter_code", "iso3", "country", "year", "product_gini"}
    missing = expected - set(sample.columns)
    if missing:
        raise ValueError(f"Primary sample is missing columns: {sorted(missing)}")
    duplicate_keys = sample.duplicated(["iso3", "reporter_code", "year"]).sum()
    if duplicate_keys:
        raise ValueError(f"Primary sample has duplicate iso3-reporter_code-year rows: {duplicate_keys}")
    sample = sample.copy()
    sample["reporter_code"] = pd.to_numeric(sample["reporter_code"], errors="coerce").astype("Int64")
    sample["year"] = pd.to_numeric(sample["year"], errors="coerce").astype("Int64")
    return sample.sort_values(["iso3", "year"]).reset_index(drop=True)


def load_partner_reference() -> pd.DataFrame:
    partners = pd.read_csv(PARTNER_REFERENCE_PATH)
    partners["destination_partner_code"] = partners["partner_code"].map(normalize_3digit)
    partners["destination_iso3"] = partners["partner_iso3"].fillna("").astype(str).str.upper()
    partners["destination_name"] = partners["partner_name"].fillna("").astype(str)
    return partners[["destination_partner_code", "destination_iso3", "destination_name"]].drop_duplicates()


def load_wits_countries() -> pd.DataFrame:
    path = base.WITS_METADATA_DIR / "country_all.xml"
    if not path.exists():
        raise FileNotFoundError(
            f"Missing WITS country metadata at {relative_path(path)}. Run the market-access diagnostics preflight first."
        )
    countries = base.parse_wits_countries_xml(path.read_text(encoding="utf-8-sig"))
    countries = countries.copy()
    countries["wits_country_code"] = countries["wits_country_code"].map(normalize_3digit)
    countries["wits_iso3"] = countries["wits_iso3"].fillna("").astype(str).str.upper()
    countries["wits_is_reporter"] = countries["wits_is_reporter"].fillna("").astype(str)
    countries["wits_name"] = countries["wits_name"].fillna("").astype(str)
    return countries


def index_comtrade_files() -> dict[tuple[int, int], Path]:
    indexed: dict[tuple[int, int], Path] = {}
    for path in sorted(COMTRADE_AGG_DIR.glob("*.parquet")):
        parsed = base.parse_comtrade_aggregate_filename(path)
        if parsed is None:
            continue
        key = (int(parsed["reporter_code"]), int(parsed["year"]))
        indexed[key] = path
    return indexed


def build_hs4_baseline_weights(
    sample: pd.DataFrame, coverage: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, Any]]:
    file_index = index_comtrade_files()
    reporters = set(pd.to_numeric(sample["reporter_code"], errors="coerce").dropna().astype(int).tolist())
    cov = coverage[pd.to_numeric(coverage["reporter_code"], errors="coerce").isin(reporters)].copy()
    rows: list[pd.DataFrame] = []
    summary_rows: list[dict[str, Any]] = []
    missing_files: list[dict[str, Any]] = []

    for cov_row in cov.itertuples(index=False):
        reporter_code = int(getattr(cov_row, "reporter_code"))
        baseline_years = parse_baseline_years(getattr(cov_row, "baseline_years"))
        reporter_positive_rows = 0
        reporter_positive_value = 0.0
        reporter_excluded_999999_rows = 0
        reporter_excluded_999999_value = 0.0
        reporter_excluded_world_rows = 0
        reporter_excluded_world_value = 0.0
        reporter_files = 0

        for year in baseline_years:
            path = file_index.get((reporter_code, year))
            if path is None:
                missing_files.append({"reporter_code": reporter_code, "year": year})
                continue
            reporter_files += 1
            df = pd.read_parquet(
                path,
                columns=[
                    "reporter_code",
                    "year",
                    "flow",
                    "dimension",
                    "cmd_code",
                    "partner_code",
                    "trade_value",
                ],
            )
            cells = df[
                df["dimension"].eq("product_partner_cell")
                & df["flow"].eq("Exports")
                & (pd.to_numeric(df["trade_value"], errors="coerce") > 0)
            ].copy()
            reporter_positive_rows += int(len(cells))
            reporter_positive_value += float(pd.to_numeric(cells["trade_value"], errors="coerce").fillna(0).sum())
            cells["source_product_code"] = cells["cmd_code"].map(normalize_hs6)
            cells["destination_partner_code"] = cells["partner_code"].map(normalize_3digit)

            excluded_999999 = cells["source_product_code"].isin(base.EXCLUDED_HS6_CODES)
            reporter_excluded_999999_rows += int(excluded_999999.sum())
            reporter_excluded_999999_value += float(cells.loc[excluded_999999, "trade_value"].sum())
            cells = cells[~excluded_999999].copy()

            excluded_world = cells["destination_partner_code"].eq(PARTNER_WORLD)
            reporter_excluded_world_rows += int(excluded_world.sum())
            reporter_excluded_world_value += float(cells.loc[excluded_world, "trade_value"].sum())
            cells = cells[~excluded_world].copy()

            cells["harmonized_hs4"] = cells["source_product_code"].map(harmonized_hs4)
            cells = cells[cells["harmonized_hs4"].ne("")].copy()
            if cells.empty:
                continue
            grouped = (
                cells.groupby(["reporter_code", "destination_partner_code", "harmonized_hs4"], as_index=False)
                .agg(
                    baseline_trade_value=("trade_value", "sum"),
                    source_cell_count=("trade_value", "size"),
                )
                .rename(columns={"reporter_code": "exporter_reporter_code"})
            )
            grouped["baseline_year"] = year
            rows.append(grouped)

        summary_rows.append(
            {
                "exporter_reporter_code": reporter_code,
                "baseline_years": ";".join(map(str, baseline_years)),
                "files_scanned": reporter_files,
                "positive_product_partner_rows": reporter_positive_rows,
                "positive_product_partner_value": reporter_positive_value,
                "excluded_999999_rows": reporter_excluded_999999_rows,
                "excluded_999999_trade_value": reporter_excluded_999999_value,
                "excluded_world_rows": reporter_excluded_world_rows,
                "excluded_world_trade_value": reporter_excluded_world_value,
            }
        )

    if not rows:
        raise ValueError("No baseline product-partner rows were available to build HS4 weights.")

    weights = pd.concat(rows, ignore_index=True)
    weights = (
        weights.groupby(["exporter_reporter_code", "destination_partner_code", "harmonized_hs4"], as_index=False)
        .agg(
            baseline_trade_value=("baseline_trade_value", "sum"),
            source_cell_count=("source_cell_count", "sum"),
            baseline_year_count=("baseline_year", "nunique"),
        )
        .sort_values(["exporter_reporter_code", "destination_partner_code", "harmonized_hs4"])
    )
    denominators = (
        weights.groupby("exporter_reporter_code", as_index=False)["baseline_trade_value"]
        .sum()
        .rename(columns={"baseline_trade_value": "exporter_baseline_trade_value_denominator"})
    )
    weights = weights.merge(denominators, on="exporter_reporter_code", how="left", validate="many_to_one")
    weights["baseline_weight"] = (
        weights["baseline_trade_value"] / weights["exporter_baseline_trade_value_denominator"]
    )
    weight_sums = weights.groupby("exporter_reporter_code")["baseline_weight"].sum()
    bad_sums = weight_sums[(weight_sums - 1).abs() > 1e-8]
    if not bad_sums.empty:
        raise ValueError(f"Baseline weights do not sum to one for reporters: {bad_sums.head().to_dict()}")

    summary = {
        "path": relative_path(BASELINE_WEIGHTS_PATH),
        "rows": int(len(weights)),
        "exporters": int(weights["exporter_reporter_code"].nunique()),
        "destinations": int(weights["destination_partner_code"].nunique()),
        "harmonized_hs4": int(weights["harmonized_hs4"].nunique()),
        "source_positive_product_partner_rows": int(sum(item["positive_product_partner_rows"] for item in summary_rows)),
        "excluded_999999_rows": int(sum(item["excluded_999999_rows"] for item in summary_rows)),
        "excluded_999999_trade_value": float(sum(item["excluded_999999_trade_value"] for item in summary_rows)),
        "excluded_world_rows": int(sum(item["excluded_world_rows"] for item in summary_rows)),
        "excluded_world_trade_value": float(sum(item["excluded_world_trade_value"] for item in summary_rows)),
        "missing_baseline_files": missing_files[:20],
        "missing_baseline_file_count": int(len(missing_files)),
        "reporter_summaries": summary_rows,
    }
    return weights.reset_index(drop=True), summary


def wits_lookup_tables(wits: pd.DataFrame) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_code: dict[str, dict[str, Any]] = {}
    by_iso: dict[str, dict[str, Any]] = {}

    def priority(row: dict[str, Any]) -> tuple[int, int]:
        is_reporter = 1 if str(row.get("wits_is_reporter", "")) == "1" else 0
        iso3 = str(row.get("wits_iso3", "")).upper()
        country_like_iso3 = 1 if len(iso3) == 3 and iso3.isalpha() else 0
        return is_reporter, country_like_iso3

    for row in wits.to_dict("records"):
        code = normalize_3digit(row.get("wits_country_code"))
        iso3 = str(row.get("wits_iso3", "")).upper()
        if code:
            current = by_code.get(code)
            if current is None or priority(row) > priority(current):
                by_code[code] = row
        if iso3:
            by_iso[iso3] = row
    return by_code, by_iso


def destination_mapping_row(
    destination_partner_code: str,
    year: int,
    partner_ref: dict[str, dict[str, Any]],
    wits_by_code: dict[str, dict[str, Any]],
    wits_by_iso: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    ref = partner_ref.get(destination_partner_code, {})
    destination_iso3 = str(ref.get("destination_iso3", "")).upper()
    destination_name = str(ref.get("destination_name", ""))
    direct = wits_by_code.get(destination_partner_code)
    match_status = "exact_numeric_code_match" if direct else "missing_numeric_code"
    if direct is None and destination_iso3:
        direct = wits_by_iso.get(destination_iso3)
        if direct is not None:
            match_status = "iso3_match_different_numeric_code"

    eu_active = base.eu_customs_active_for_year(destination_iso3, int(year))
    if eu_active:
        eun = wits_by_code.get(base.EU_CUSTOMS_TERRITORY_CODE, {})
        return {
            "destination_partner_code": destination_partner_code,
            "destination_iso3": destination_iso3,
            "destination_name": destination_name,
            "year": int(year),
            "destination_tariff_reporter_code": base.EU_CUSTOMS_TERRITORY_CODE,
            "destination_tariff_reporter_iso3": base.EU_CUSTOMS_TERRITORY_ISO3,
            "destination_tariff_reporter_name": eun.get("wits_name", base.EU_CUSTOMS_TERRITORY_NAME),
            "destination_customs_mapping_rule": "eu_customs_territory_active",
            "destination_wits_match_status": "eu_customs_territory",
            "destination_tariff_mapping_status": "ok",
            "direct_wits_country_code": normalize_3digit(direct.get("wits_country_code")) if direct else "",
            "direct_wits_iso3": direct.get("wits_iso3", "") if direct else "",
            "direct_wits_is_reporter": direct.get("wits_is_reporter", "") if direct else "",
        }

    if direct is None:
        return {
            "destination_partner_code": destination_partner_code,
            "destination_iso3": destination_iso3,
            "destination_name": destination_name,
            "year": int(year),
            "destination_tariff_reporter_code": "",
            "destination_tariff_reporter_iso3": "",
            "destination_tariff_reporter_name": "",
            "destination_customs_mapping_rule": "missing_direct_wits_country_for_destination",
            "destination_wits_match_status": match_status,
            "destination_tariff_mapping_status": "missing_wits_destination",
            "direct_wits_country_code": "",
            "direct_wits_iso3": "",
            "direct_wits_is_reporter": "",
        }

    direct_code = normalize_3digit(direct.get("wits_country_code"))
    direct_is_reporter = str(direct.get("wits_is_reporter", ""))
    status = "ok" if direct_code and direct_is_reporter == "1" else "wits_destination_not_reporter"
    membership = base.EU_MEMBERSHIP_YEARS.get(destination_iso3)
    if membership is not None:
        accession_year, exit_year = membership
        if accession_year is not None and int(year) < int(accession_year):
            rule = "direct_wits_country_pre_accession"
        elif exit_year is not None and int(year) > int(exit_year):
            rule = "direct_wits_country_post_eu_customs_exit"
        else:
            rule = "direct_wits_country_eu_inactive"
    else:
        rule = "direct_wits_country_not_eu_member"

    return {
        "destination_partner_code": destination_partner_code,
        "destination_iso3": destination_iso3,
        "destination_name": destination_name,
        "year": int(year),
        "destination_tariff_reporter_code": direct_code,
        "destination_tariff_reporter_iso3": str(direct.get("wits_iso3", "")),
        "destination_tariff_reporter_name": str(direct.get("wits_name", "")),
        "destination_customs_mapping_rule": rule,
        "destination_wits_match_status": match_status,
        "destination_tariff_mapping_status": status,
        "direct_wits_country_code": direct_code,
        "direct_wits_iso3": str(direct.get("wits_iso3", "")),
        "direct_wits_is_reporter": direct_is_reporter,
    }


def build_destination_tariff_mapping(weights: pd.DataFrame, sample: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    partners = load_partner_reference()
    partner_ref = {
        str(row["destination_partner_code"]): row
        for row in partners.to_dict("records")
        if str(row.get("destination_partner_code", ""))
    }
    wits = load_wits_countries()
    wits_by_code, wits_by_iso = wits_lookup_tables(wits)

    destination_codes = sorted(weights["destination_partner_code"].dropna().astype(str).unique().tolist())
    years = sorted(pd.to_numeric(sample["year"], errors="coerce").dropna().astype(int).unique().tolist())
    rows = [
        destination_mapping_row(code, year, partner_ref, wits_by_code, wits_by_iso)
        for code in destination_codes
        for year in years
    ]
    mapping = pd.DataFrame(rows)
    duplicate_keys = int(mapping.duplicated(["destination_partner_code", "year"]).sum())
    if duplicate_keys:
        raise ValueError(f"Destination mapping has duplicate destination-year rows: {duplicate_keys}")

    summary = {
        "path": relative_path(DESTINATION_MAPPING_PATH),
        "rows": int(len(mapping)),
        "destination_partner_codes": int(mapping["destination_partner_code"].nunique()),
        "years": int(mapping["year"].nunique()),
        "tariff_reporter_codes": int(mapping["destination_tariff_reporter_code"].replace("", pd.NA).nunique()),
        "status_counts": mapping["destination_tariff_mapping_status"].value_counts(dropna=False).to_dict(),
        "customs_mapping_rule_counts": mapping["destination_customs_mapping_rule"].value_counts(dropna=False).to_dict(),
        "wits_match_status_counts": mapping["destination_wits_match_status"].value_counts(dropna=False).to_dict(),
        "unmatched_examples": mapping[
            ~mapping["destination_tariff_mapping_status"].eq("ok")
        ][
            [
                "destination_partner_code",
                "destination_iso3",
                "destination_name",
                "year",
                "destination_tariff_mapping_status",
            ]
        ]
        .head(20)
        .to_dict("records"),
    }
    return mapping.sort_values(["destination_partner_code", "year"]).reset_index(drop=True), summary


def fetch_wits_availability(
    reporter_codes: list[str], refresh: bool, timeout: int, max_reporters: int | None = None
) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows: list[pd.DataFrame] = []
    manifests: list[dict[str, Any]] = []
    selected_codes = reporter_codes[: max_reporters or len(reporter_codes)]
    for index, code in enumerate(selected_codes, start=1):
        path = base.WITS_AVAILABILITY_DIR / f"{code}.xml"
        url = WITS_DATAAVAILABILITY_URL.format(country=code)
        manifest: dict[str, Any] = {"wits_country_code": code, "url": url, "path": relative_path(path)}
        if path.exists() and not refresh:
            text = path.read_text(encoding="utf-8-sig")
            manifest.update({"status": "cached", "size_bytes": path.stat().st_size, "sha256": file_sha256(path)})
        else:
            started = time.time()
            try:
                response = requests.get(url, timeout=timeout)
                manifest.update(
                    {
                        "status_code": response.status_code,
                        "elapsed_seconds": round(time.time() - started, 3),
                        "content_type": response.headers.get("content-type", ""),
                    }
                )
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(response.content)
                text = response.content.decode("utf-8-sig", errors="replace")
                manifest.update({"status": "downloaded", "size_bytes": path.stat().st_size, "sha256": file_sha256(path)})
            except requests.RequestException as exc:
                manifest.update({"status": "request_failed", "error": repr(exc)})
                manifests.append(manifest)
                continue
        try:
            parsed = base.parse_wits_dataavailability_xml(text)
            manifest["rows"] = int(len(parsed))
            if not parsed.empty:
                parsed["wits_country_code"] = parsed["wits_country_code"].map(normalize_3digit)
                rows.append(parsed)
        except ET.ParseError as exc:
            manifest.update({"status": "parse_failed", "error": repr(exc)})
        manifests.append(manifest)
        if index % 50 == 0:
            print(f"availability checked {index}/{len(selected_codes)} reporters", flush=True)

    availability = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    summary = {
        "reporters_requested": int(len(selected_codes)),
        "rows": int(len(availability)),
        "reporters_with_rows": int(availability["wits_country_code"].nunique()) if not availability.empty else 0,
        "manifest_examples": manifests[:10],
        "request_status_counts": pd.Series([item.get("status", "") for item in manifests]).value_counts().to_dict()
        if manifests
        else {},
    }
    return availability, summary


def availability_by_reporter_year(availability: pd.DataFrame) -> pd.DataFrame:
    if availability.empty:
        return pd.DataFrame(
            columns=[
                "destination_tariff_reporter_code",
                "year",
                "destination_availability_nomenclature_codes",
                "destination_availability_last_updated_dates",
                "destination_specific_duty_ave_available_values",
                "destination_has_aveestimated_available",
            ]
        )
    work = availability.copy()
    work["destination_tariff_reporter_code"] = work["wits_country_code"].map(normalize_3digit)
    work["year"] = pd.to_numeric(work["year"], errors="coerce").astype("Int64")
    work = work[work["destination_tariff_reporter_code"].ne("") & work["year"].notna()].copy()
    out = (
        work.groupby(["destination_tariff_reporter_code", "year"], as_index=False)
        .agg(
            destination_availability_nomenclature_codes=(
                "nomenclature_code",
                lambda values: ";".join(sorted(set(map(str, values)))),
            ),
            destination_availability_last_updated_dates=(
                "last_updated_date",
                lambda values: ";".join(sorted(set(map(str, values)))),
            ),
            destination_specific_duty_ave_available_values=(
                "specific_duty_ave_available",
                lambda values: ";".join(sorted(set(map(str, values)))),
            ),
        )
        .sort_values(["destination_tariff_reporter_code", "year"])
    )
    out["destination_has_aveestimated_available"] = out[
        "destination_specific_duty_ave_available_values"
    ].str.contains("Yes", case=False, na=False)
    return out


def build_pull_skeleton(
    sample: pd.DataFrame,
    weights: pd.DataFrame,
    destination_mapping: pd.DataFrame,
    availability: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    exporter_years = (
        sample[["reporter_code", "iso3", "country", "year"]]
        .drop_duplicates()
        .rename(columns={"reporter_code": "exporter_reporter_code", "iso3": "exporter_iso3", "country": "exporter_country"})
    )
    exporter_destinations = weights[["exporter_reporter_code", "destination_partner_code"]].drop_duplicates()
    exporter_dest_years = exporter_years.merge(exporter_destinations, on="exporter_reporter_code", how="inner")
    mapped = exporter_dest_years.merge(
        destination_mapping,
        on=["destination_partner_code", "year"],
        how="left",
        validate="many_to_one",
    )
    availability_year = availability_by_reporter_year(availability)
    if availability_year.empty:
        mapped["has_destination_wits_availability_for_year"] = False
        mapped["destination_has_aveestimated_available"] = False
        mapped["destination_availability_nomenclature_codes"] = ""
        mapped["destination_availability_last_updated_dates"] = ""
        mapped["destination_specific_duty_ave_available_values"] = ""
    else:
        mapped = mapped.merge(
            availability_year,
            on=["destination_tariff_reporter_code", "year"],
            how="left",
            validate="many_to_one",
        )
        mapped["has_destination_wits_availability_for_year"] = mapped[
            "destination_availability_nomenclature_codes"
        ].notna()
        mapped["destination_availability_nomenclature_codes"] = mapped[
            "destination_availability_nomenclature_codes"
        ].fillna("")
        mapped["destination_availability_last_updated_dates"] = mapped[
            "destination_availability_last_updated_dates"
        ].fillna("")
        mapped["destination_specific_duty_ave_available_values"] = mapped[
            "destination_specific_duty_ave_available_values"
        ].fillna("")
        mapped["destination_has_aveestimated_available"] = mapped[
            "destination_has_aveestimated_available"
        ].map(lambda value: bool(value) if not pd.isna(value) else False)

    if datatype_slug(DATATYPE) == datatype_slug(DEFAULT_DATATYPE):
        mapped["destination_datatype_available"] = mapped["destination_has_aveestimated_available"].fillna(False).astype(
            bool
        )
        mapped["destination_datatype_availability_rule"] = "specific_duty_ave_available_yes"
    else:
        mapped["destination_datatype_available"] = mapped["has_destination_wits_availability_for_year"].fillna(
            False
        ).astype(bool)
        mapped["destination_datatype_availability_rule"] = "wits_reporter_year_available"

    mapped["pull_eligible"] = (
        mapped["destination_tariff_mapping_status"].eq("ok")
        & mapped["has_destination_wits_availability_for_year"].fillna(False).astype(bool)
        & mapped["destination_datatype_available"].fillna(False).astype(bool)
        & mapped["destination_tariff_reporter_code"].fillna("").astype(str).ne("")
    )
    skeleton = (
        mapped[mapped["pull_eligible"]]
        [
            [
                "destination_tariff_reporter_code",
                "destination_tariff_reporter_iso3",
                "destination_tariff_reporter_name",
                "year",
                "destination_availability_nomenclature_codes",
                "destination_availability_last_updated_dates",
                "destination_specific_duty_ave_available_values",
                "destination_datatype_available",
                "destination_datatype_availability_rule",
            ]
        ]
        .drop_duplicates(["destination_tariff_reporter_code", "year"])
        .sort_values(["destination_tariff_reporter_code", "year"])
        .reset_index(drop=True)
    )
    skeleton["datasource"] = "TRN"
    skeleton["datatype"] = DATATYPE
    skeleton["partner"] = PARTNER_WORLD
    skeleton["product_request"] = "all"
    skeleton["url"] = skeleton.apply(
        lambda row: WITS_TARIFF_URL.format(
            reporter=row["destination_tariff_reporter_code"], year=int(row["year"]), datatype=DATATYPE
        ),
        axis=1,
    )
    skeleton["raw_cache_path"] = skeleton.apply(
        lambda row: relative_path(raw_tariff_path(row["destination_tariff_reporter_code"], int(row["year"]))),
        axis=1,
    )
    skeleton["raw_cache_exists"] = skeleton["raw_cache_path"].map(lambda p: (ROOT / p).exists())

    request_products = build_request_hs4_index(sample, weights, destination_mapping)
    request_products = request_products.merge(
        skeleton[["destination_tariff_reporter_code", "year"]],
        on=["destination_tariff_reporter_code", "year"],
        how="inner",
        validate="many_to_one",
    )

    summary = {
        "path": relative_path(PULL_SKELETON_PATH),
        "datatype": DATATYPE,
        "rows": int(len(skeleton)),
        "destination_year_rows_before_unique_requests": int(len(mapped)),
        "eligible_destination_year_rows_before_unique_requests": int(mapped["pull_eligible"].sum()),
        "unique_destination_tariff_reporters": int(skeleton["destination_tariff_reporter_code"].nunique())
        if not skeleton.empty
        else 0,
        "year_min": int(skeleton["year"].min()) if not skeleton.empty else None,
        "year_max": int(skeleton["year"].max()) if not skeleton.empty else None,
        "raw_cache_existing_rows": int(skeleton["raw_cache_exists"].sum()) if not skeleton.empty else 0,
        "destination_mapping_status_counts": mapped["destination_tariff_mapping_status"]
        .value_counts(dropna=False)
        .to_dict(),
        "destination_availability_rows_missing": int((~mapped["has_destination_wits_availability_for_year"]).sum()),
        "destination_aveestimated_rows_missing": int((~mapped["destination_has_aveestimated_available"]).sum()),
        "destination_datatype_rows_missing": int((~mapped["destination_datatype_available"]).sum()),
        "destination_datatype_availability_rule_counts": mapped["destination_datatype_availability_rule"]
        .value_counts(dropna=False)
        .to_dict(),
        "request_hs4_rows": int(len(request_products)),
        "request_hs4_unique": int(request_products["harmonized_hs4"].nunique()) if not request_products.empty else 0,
    }
    return skeleton, request_products, summary


def build_request_hs4_index(
    sample: pd.DataFrame, weights: pd.DataFrame, destination_mapping: pd.DataFrame
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    year_lookup = {
        int(exporter): group[["year"]].drop_duplicates().copy()
        for exporter, group in sample.groupby("reporter_code", observed=True)
    }
    for exporter, w_i in weights.groupby("exporter_reporter_code", observed=True):
        years_i = year_lookup.get(int(exporter))
        if years_i is None or years_i.empty:
            continue
        dest_hs4 = w_i[["destination_partner_code", "harmonized_hs4"]].drop_duplicates()
        expanded = dest_hs4.merge(years_i, how="cross")
        expanded = expanded.merge(
            destination_mapping[
                [
                    "destination_partner_code",
                    "year",
                    "destination_tariff_reporter_code",
                    "destination_tariff_mapping_status",
                ]
            ],
            on=["destination_partner_code", "year"],
            how="left",
            validate="many_to_one",
        )
        expanded = expanded[
            expanded["destination_tariff_mapping_status"].eq("ok")
            & expanded["destination_tariff_reporter_code"].fillna("").astype(str).ne("")
        ].copy()
        rows.append(expanded[["destination_tariff_reporter_code", "year", "harmonized_hs4"]])
    if not rows:
        return pd.DataFrame(columns=["destination_tariff_reporter_code", "year", "harmonized_hs4"])
    return (
        pd.concat(rows, ignore_index=True)
        .drop_duplicates(["destination_tariff_reporter_code", "year", "harmonized_hs4"])
        .sort_values(["destination_tariff_reporter_code", "year", "harmonized_hs4"])
        .reset_index(drop=True)
    )


def raw_tariff_path(tariff_reporter_code: str, year: int) -> Path:
    return RAW_CACHE_DIR / str(tariff_reporter_code).zfill(3) / f"{int(year)}.json.gz"


def pull_wits_tariffs(
    skeleton: pd.DataFrame,
    pull_wits: bool,
    force_refresh: bool,
    max_requests: int | None,
    timeout: int,
    sleep_seconds: float,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    manifests: list[dict[str, Any]] = []
    requests_run = 0
    for row in skeleton.itertuples(index=False):
        code = str(getattr(row, "destination_tariff_reporter_code")).zfill(3)
        year = int(getattr(row, "year"))
        url = getattr(row, "url")
        path = raw_tariff_path(code, year)
        manifest: dict[str, Any] = {
            "destination_tariff_reporter_code": code,
            "year": year,
            "url": url,
            "raw_path": relative_path(path),
            "datatype": DATATYPE,
            "partner": PARTNER_WORLD,
            "product_request": "all",
            "retrieved_at_utc": "",
        }
        if path.exists() and not force_refresh:
            manifest.update(
                {
                    "pull_status": "cached",
                    "status_code": 200,
                    "size_bytes": path.stat().st_size,
                    "sha256": file_sha256(path),
                }
            )
            manifests.append(manifest)
            continue
        if not pull_wits:
            manifest["pull_status"] = "skipped_not_requested"
            manifests.append(manifest)
            continue
        if max_requests is not None and requests_run >= max_requests:
            manifest["pull_status"] = "skipped_max_requests"
            manifests.append(manifest)
            continue

        path.parent.mkdir(parents=True, exist_ok=True)
        started = time.time()
        try:
            response = requests.get(url, timeout=timeout)
            manifest.update(
                {
                    "retrieved_at_utc": now_utc(),
                    "status_code": response.status_code,
                    "elapsed_seconds": round(time.time() - started, 3),
                    "content_type": response.headers.get("content-type", ""),
                }
            )
            if response.status_code == 200 and "json" in response.headers.get("content-type", "").lower():
                with gzip.open(path, "wb") as handle:
                    handle.write(response.content)
                manifest.update(
                    {
                        "pull_status": "downloaded",
                        "size_bytes": path.stat().st_size,
                        "sha256": file_sha256(path),
                    }
                )
            elif response.status_code == 404 and "NoRecordsFound" in response.text:
                manifest.update(
                    {
                        "pull_status": "no_records_found",
                        "error_excerpt": response.text[:500],
                    }
                )
            else:
                manifest.update(
                    {
                        "pull_status": "http_or_content_error",
                        "error_excerpt": response.text[:500],
                    }
                )
            requests_run += 1
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
        except requests.RequestException as exc:
            manifest.update(
                {
                    "retrieved_at_utc": now_utc(),
                    "pull_status": "request_failed",
                    "error": repr(exc),
                    "elapsed_seconds": round(time.time() - started, 3),
                }
            )
            requests_run += 1
        manifests.append(manifest)
        if requests_run and requests_run % 25 == 0:
            print(f"WITS tariff requests attempted this run: {requests_run}", flush=True)

    manifest_df = pd.DataFrame(manifests)
    manifest_df.to_csv(RAW_MANIFEST_PATH, index=False)
    summary = {
        "path": relative_path(RAW_MANIFEST_PATH),
        "rows": int(len(manifest_df)),
        "requests_attempted_this_run": int(requests_run),
        "status_counts": manifest_df["pull_status"].value_counts(dropna=False).to_dict()
        if "pull_status" in manifest_df
        else {},
    }
    return manifest_df, summary


def attr_value(obs_attrs: list[dict[str, Any]], values: list[Any], attr_id: str) -> Any:
    for pos, attr in enumerate(obs_attrs):
        if attr.get("id") != attr_id:
            continue
        value_index = values[pos] if pos < len(values) else None
        if value_index is None:
            return ""
        attr_values = attr.get("values", [])
        try:
            return attr_values[int(value_index)].get("id", "")
        except (IndexError, TypeError, ValueError):
            return ""
    return ""


def infer_series_dimension_positions(series_dims: list[dict[str, Any]], series_keys: list[str]) -> dict[str, int | None]:
    """Infer SDMX series-key positions.

    WITS' JSON metadata can list PRODUCTCODE after PARTNER even when the
    product index varies in the third key slot for product/all requests.
    Singleton dimensions are position-insensitive, but varying dimensions must
    be inferred from observed key ranges.
    """
    if not series_dims:
        return {}
    key_parts = [[int(part) for part in key.split(":")] for key in series_keys]
    key_len = max((len(parts) for parts in key_parts), default=0)
    max_by_position = []
    for pos in range(key_len):
        max_by_position.append(max((parts[pos] for parts in key_parts if pos < len(parts)), default=0))

    positions: dict[str, int | None] = {}
    claimed: set[int] = set()
    for listed_pos, dim in enumerate(series_dims):
        dim_id = dim.get("id", "")
        values = dim.get("values", [])
        if len(values) <= 1:
            positions[dim_id] = None
            continue
        candidates = [
            pos
            for pos, max_index in enumerate(max_by_position)
            if pos not in claimed and max_index > 0 and max_index < len(values)
        ]
        if candidates:
            chosen = max(candidates, key=lambda pos: max_by_position[pos])
        elif listed_pos < key_len:
            chosen = listed_pos
        else:
            chosen = None
        positions[dim_id] = chosen
        if chosen is not None:
            claimed.add(chosen)
    return positions


def parse_wits_sdmx_tariff_json(obj: dict[str, Any]) -> pd.DataFrame:
    structure = obj.get("structure", {})
    series_dims = structure.get("dimensions", {}).get("series", [])
    obs_dims = structure.get("dimensions", {}).get("observation", [])
    obs_attrs = structure.get("attributes", {}).get("observation", [])
    series_values = [
        [item.get("id", "") for item in dim.get("values", [])]
        for dim in series_dims
    ]
    obs_years = []
    if obs_dims:
        obs_years = [item.get("id", "") for item in obs_dims[0].get("values", [])]

    rows: list[dict[str, Any]] = []
    all_series_keys = [
        series_key
        for dataset in obj.get("dataSets", [])
        for series_key in dataset.get("series", {}).keys()
    ]
    dimension_positions = infer_series_dimension_positions(series_dims, all_series_keys)

    for dataset in obj.get("dataSets", []):
        for series_key, series_payload in dataset.get("series", {}).items():
            key_parts = [int(part) for part in series_key.split(":")]
            dims: dict[str, str] = {}
            for listed_pos, dim in enumerate(series_dims):
                dim_id = dim.get("id", "")
                values = series_values[listed_pos]
                if not values:
                    dims[dim_id] = ""
                    continue
                actual_pos = dimension_positions.get(dim_id)
                if actual_pos is None:
                    dims[dim_id] = values[0]
                    continue
                try:
                    dims[dim_id] = values[key_parts[actual_pos]]
                except (IndexError, TypeError):
                    dims[dim_id] = ""
            product_code = normalize_hs6(dims.get("PRODUCTCODE", ""))
            hs4 = harmonized_hs4(product_code)
            if not hs4:
                continue
            for obs_key, obs_values in series_payload.get("observations", {}).items():
                year = obs_years[int(obs_key)] if obs_years and str(obs_key).isdigit() else ""
                rate = obs_values[0] if obs_values else None
                attrs = obs_values[1:] if len(obs_values) > 1 else []
                rows.append(
                    {
                        "tariff_reporter_code": normalize_3digit(dims.get("REPORTER", "")),
                        "year": int(year) if str(year).isdigit() else pd.NA,
                        "partner": normalize_3digit(dims.get("PARTNER", "")),
                        "datatype": dims.get("DATATYPE", ""),
                        "source_product_code": product_code,
                        "harmonized_hs4": hs4,
                        "tariff_rate": pd.to_numeric(rate, errors="coerce"),
                        "nomenclature_code": attr_value(obs_attrs, attrs, "NOMENCODE"),
                        "tariff_type": attr_value(obs_attrs, attrs, "TARIFFTYPE"),
                        "total_lines": pd.to_numeric(attr_value(obs_attrs, attrs, "TOTALNOOFLINES"), errors="coerce"),
                        "nbr_mfn_lines": pd.to_numeric(attr_value(obs_attrs, attrs, "NBR_MFN_LINES"), errors="coerce"),
                        "nbr_pref_lines": pd.to_numeric(attr_value(obs_attrs, attrs, "NBR_PREF_LINES"), errors="coerce"),
                        "obs_value_measure": attr_value(obs_attrs, attrs, "OBS_VALUE_MEASURE"),
                    }
                )
    if not rows:
        return pd.DataFrame(
            columns=[
                "tariff_reporter_code",
                "year",
                "partner",
                "datatype",
                "source_product_code",
                "harmonized_hs4",
                "tariff_rate",
                "nomenclature_code",
                "tariff_type",
                "total_lines",
                "nbr_mfn_lines",
                "nbr_pref_lines",
                "obs_value_measure",
            ]
        )
    return pd.DataFrame(rows)


def aggregate_tariffs_to_hs4(source: pd.DataFrame, request_products: pd.DataFrame | None = None) -> pd.DataFrame:
    rate_col = tariff_rate_column()
    if source.empty:
        return pd.DataFrame(
            columns=[
                "tariff_reporter_code",
                "year",
                "harmonized_hs4",
                "tariff_rate_hs4",
                rate_col,
                "source_product_count",
                "source_tariff_line_count",
                "nomenclature_codes",
                "tariff_types",
                "hs4_aggregation_method",
            ]
        )
    data = source.copy()
    data["tariff_reporter_code"] = data["tariff_reporter_code"].map(normalize_3digit)
    data["year"] = pd.to_numeric(data["year"], errors="coerce").astype("Int64")
    data = data[
        data["tariff_reporter_code"].ne("")
        & data["year"].notna()
        & data["harmonized_hs4"].astype(str).str.startswith("HS4:")
        & data["tariff_rate"].notna()
    ].copy()
    if request_products is not None and not request_products.empty:
        keep = request_products[["destination_tariff_reporter_code", "year", "harmonized_hs4"]].rename(
            columns={"destination_tariff_reporter_code": "tariff_reporter_code"}
        )
        keep["tariff_reporter_code"] = keep["tariff_reporter_code"].map(normalize_3digit)
        keep["year"] = pd.to_numeric(keep["year"], errors="coerce").astype("Int64")
        data = data.merge(keep.drop_duplicates(), on=["tariff_reporter_code", "year", "harmonized_hs4"], how="inner")
    if data.empty:
        return aggregate_tariffs_to_hs4(pd.DataFrame())

    data["line_weight"] = pd.to_numeric(data["total_lines"], errors="coerce").fillna(0)
    data.loc[data["line_weight"] <= 0, "line_weight"] = 1
    data["weighted_rate"] = data["tariff_rate"] * data["line_weight"]
    grouped = (
        data.groupby(["tariff_reporter_code", "year", "harmonized_hs4"], as_index=False)
        .agg(
            weighted_rate_sum=("weighted_rate", "sum"),
            source_tariff_line_count=("line_weight", "sum"),
            source_product_count=("source_product_code", "nunique"),
            nomenclature_codes=("nomenclature_code", lambda values: ";".join(sorted(set(map(str, values))))),
            tariff_types=("tariff_type", lambda values: ";".join(sorted(set(map(str, values))))),
        )
        .sort_values(["tariff_reporter_code", "year", "harmonized_hs4"])
    )
    grouped[rate_col] = grouped["weighted_rate_sum"] / grouped["source_tariff_line_count"]
    grouped["tariff_rate_hs4"] = grouped[rate_col]
    grouped["hs4_aggregation_method"] = "line_count_weighted_average_of_wits_source_products"
    return grouped[
        [
            "tariff_reporter_code",
            "year",
            "harmonized_hs4",
            "tariff_rate_hs4",
            rate_col,
            "source_product_count",
            "source_tariff_line_count",
            "nomenclature_codes",
            "tariff_types",
            "hs4_aggregation_method",
        ]
    ].reset_index(drop=True)


def load_and_aggregate_cached_tariffs(
    manifest_df: pd.DataFrame, request_products: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, Any]]:
    parsed_chunks: list[pd.DataFrame] = []
    parse_manifests: list[dict[str, Any]] = []
    ok_manifest = manifest_df[manifest_df["pull_status"].isin(["cached", "downloaded"])].copy()
    request_products = request_products.copy()
    request_products["destination_tariff_reporter_code"] = request_products["destination_tariff_reporter_code"].map(
        normalize_3digit
    )
    request_products["year"] = pd.to_numeric(request_products["year"], errors="coerce").astype("Int64")
    request_groups = {
        (str(code), int(year)): group[["destination_tariff_reporter_code", "year", "harmonized_hs4"]].drop_duplicates()
        for (code, year), group in request_products.groupby(["destination_tariff_reporter_code", "year"], observed=True)
    }
    for idx, row in enumerate(ok_manifest.itertuples(index=False), start=1):
        code = normalize_3digit(getattr(row, "destination_tariff_reporter_code"))
        year = int(getattr(row, "year"))
        path = ROOT / getattr(row, "raw_path")
        info: dict[str, Any] = {"tariff_reporter_code": code, "year": year, "raw_path": relative_path(path)}
        if not path.exists():
            info["parse_status"] = "missing_raw_cache"
            parse_manifests.append(info)
            continue
        try:
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                obj = json.load(handle)
            parsed = parse_wits_sdmx_tariff_json(obj)
            keep = request_groups.get((code, year), pd.DataFrame())
            hs4 = aggregate_tariffs_to_hs4(parsed, keep)
            parsed_chunks.append(hs4)
            info.update(
                {
                    "parse_status": "ok",
                    "source_rows": int(len(parsed)),
                    "hs4_rows": int(len(hs4)),
                }
            )
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            info.update({"parse_status": "parse_failed", "error": repr(exc)})
        parse_manifests.append(info)
        if idx % 50 == 0:
            print(f"parsed cached WITS tariff files: {idx}/{len(ok_manifest)}", flush=True)

    tariffs = pd.concat(parsed_chunks, ignore_index=True) if parsed_chunks else aggregate_tariffs_to_hs4(pd.DataFrame())
    if not tariffs.empty:
        duplicate_keys = int(tariffs.duplicated(["tariff_reporter_code", "year", "harmonized_hs4"]).sum())
        if duplicate_keys:
            raise ValueError(f"HS4 tariff table has duplicate reporter-year-HS4 rows: {duplicate_keys}")

    parse_df = pd.DataFrame(parse_manifests)
    summary = {
        "path": relative_path(HS4_TARIFFS_PATH),
        "rows": int(len(tariffs)),
        "tariff_reporter_years": int(tariffs[["tariff_reporter_code", "year"]].drop_duplicates().shape[0])
        if not tariffs.empty
        else 0,
        "tariff_reporters": int(tariffs["tariff_reporter_code"].nunique()) if not tariffs.empty else 0,
        "harmonized_hs4": int(tariffs["harmonized_hs4"].nunique()) if not tariffs.empty else 0,
        "parse_status_counts": parse_df["parse_status"].value_counts(dropna=False).to_dict()
        if not parse_df.empty
        else {},
        "parse_examples": parse_manifests[:10],
        "processed_output_policy": "No processed tariff output is keyed by HS6; WITS source product codes are collapsed to harmonized_hs4.",
    }
    return tariffs, summary


def compute_market_access_panel(
    sample: pd.DataFrame,
    weights: pd.DataFrame,
    destination_mapping: pd.DataFrame,
    tariffs: pd.DataFrame,
    skeleton: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    if tariffs.empty:
        panel = sample.copy()
        panel["tariff_weight_coverage_i_t"] = pd.NA
        panel["market_access_tariff_avg_i_t"] = pd.NA
        panel["tariff_coverage_gate_080"] = False
        coverage = panel[
            ["country", "iso3", "reporter_code", "year", "tariff_weight_coverage_i_t", "tariff_coverage_gate_080"]
        ].copy()
        decomposition = pd.DataFrame()
        destination_audit = pd.DataFrame()
        return panel, coverage, decomposition, destination_audit, {
            "status": "pending_tariff_pulls",
            "panel_path": relative_path(DIAGNOSTICS_PANEL_PATH),
            "coverage_path": relative_path(COVERAGE_PATH),
            "uncovered_decomposition_path": relative_path(UNCOVERED_DECOMPOSITION_PATH),
            "destination_uncovered_audit_path": relative_path(DESTINATION_UNCOVERED_AUDIT_PATH),
        }

    tariff_keyed = tariffs.rename(columns={"tariff_reporter_code": "destination_tariff_reporter_code"}).copy()
    rate_col = tariff_rate_column()
    if rate_col not in tariff_keyed.columns:
        if "tariff_rate_hs4" in tariff_keyed.columns:
            rate_col = "tariff_rate_hs4"
        elif "tariff_aveestimated" in tariff_keyed.columns:
            rate_col = "tariff_aveestimated"
        else:
            raise ValueError("Tariff table is missing a usable HS4 tariff rate column.")
    tariff_keyed = tariff_keyed.rename(columns={rate_col: "_tariff_rate_hs4"})
    if skeleton is not None and not skeleton.empty:
        eligible_requests = skeleton[["destination_tariff_reporter_code", "year"]].drop_duplicates().copy()
    else:
        eligible_requests = tariff_keyed[["destination_tariff_reporter_code", "year"]].drop_duplicates().copy()
    eligible_requests["destination_tariff_reporter_code"] = eligible_requests["destination_tariff_reporter_code"].map(
        normalize_3digit
    )
    eligible_requests["year"] = pd.to_numeric(eligible_requests["year"], errors="coerce").astype("Int64")
    eligible_requests["tariff_request_eligible"] = True
    coverage_chunks: list[pd.DataFrame] = []
    decomposition_chunks: list[pd.DataFrame] = []
    destination_audit_chunks: list[pd.DataFrame] = []
    for exporter, w_i in weights.groupby("exporter_reporter_code", observed=True):
        sample_i = sample[sample["reporter_code"].astype("Int64").eq(int(exporter))].copy()
        if sample_i.empty:
            continue
        years_i = sample_i[["year"]].drop_duplicates()
        expanded = w_i.merge(years_i, how="cross")
        mapping_for_merge = destination_mapping.copy()
        for optional_col in ["destination_iso3", "destination_name"]:
            if optional_col not in mapping_for_merge.columns:
                mapping_for_merge[optional_col] = ""
        expanded = expanded.merge(
            mapping_for_merge[
                [
                    "destination_partner_code",
                    "destination_iso3",
                    "destination_name",
                    "year",
                    "destination_tariff_reporter_code",
                    "destination_tariff_mapping_status",
                    "destination_customs_mapping_rule",
                ]
            ],
            on=["destination_partner_code", "year"],
            how="left",
            validate="many_to_one",
        )
        expanded = expanded.merge(
            eligible_requests,
            on=["destination_tariff_reporter_code", "year"],
            how="left",
            validate="many_to_one",
        )
        expanded["tariff_request_eligible"] = expanded["tariff_request_eligible"].map(
            lambda value: bool(value) if not pd.isna(value) else False
        )
        expanded = expanded.merge(
            tariff_keyed[
                [
                    "destination_tariff_reporter_code",
                    "year",
                    "harmonized_hs4",
                    "_tariff_rate_hs4",
                ]
            ],
            on=["destination_tariff_reporter_code", "year", "harmonized_hs4"],
            how="left",
            validate="many_to_one",
        )
        expanded["mapped_weight"] = expanded["baseline_weight"].where(
            expanded["destination_tariff_mapping_status"].eq("ok"), 0.0
        )
        expanded["covered_weight"] = expanded["baseline_weight"].where(
            expanded["destination_tariff_mapping_status"].eq("ok") & expanded["_tariff_rate_hs4"].notna(), 0.0
        )
        expanded["weighted_tariff"] = expanded["baseline_weight"] * expanded["_tariff_rate_hs4"].fillna(0.0)
        covered = expanded["destination_tariff_mapping_status"].eq("ok") & expanded["_tariff_rate_hs4"].notna()
        expanded["coverage_reason"] = "covered"
        mapping_bad = ~covered & ~expanded["destination_tariff_mapping_status"].eq("ok")
        expanded.loc[mapping_bad, "coverage_reason"] = (
            "destination_" + expanded.loc[mapping_bad, "destination_tariff_mapping_status"].fillna("mapping_missing")
        )
        no_request = ~covered & expanded["destination_tariff_mapping_status"].eq("ok") & ~expanded["tariff_request_eligible"]
        expanded.loc[no_request, "coverage_reason"] = datatype_unavailable_reason()
        tariff_missing = (
            ~covered
            & expanded["destination_tariff_mapping_status"].eq("ok")
            & expanded["tariff_request_eligible"]
        )
        expanded.loc[tariff_missing, "coverage_reason"] = "hs4_tariff_missing_after_pull"
        grouped = (
            expanded.groupby(["exporter_reporter_code", "year"], as_index=False)
            .agg(
                baseline_weight_total=("baseline_weight", "sum"),
                destination_mapped_weight=("mapped_weight", "sum"),
                tariff_weight_coverage_i_t=("covered_weight", "sum"),
                weighted_tariff_sum=("weighted_tariff", "sum"),
                weight_rows=("baseline_weight", "size"),
                mapped_weight_rows=("mapped_weight", lambda values: int((values > 0).sum())),
                covered_weight_rows=("covered_weight", lambda values: int((values > 0).sum())),
            )
        )
        grouped["market_access_tariff_avg_i_t"] = grouped["weighted_tariff_sum"] / grouped[
            "tariff_weight_coverage_i_t"
        ].where(grouped["tariff_weight_coverage_i_t"] > 0)
        coverage_chunks.append(grouped)
        decomposition_chunks.append(
            expanded.groupby(["exporter_reporter_code", "year", "coverage_reason"], as_index=False).agg(
                baseline_weight=("baseline_weight", "sum"),
                cell_count=("baseline_weight", "size"),
            )
        )
        destination_audit_chunks.append(
            expanded.groupby(
                [
                    "exporter_reporter_code",
                    "year",
                    "destination_partner_code",
                    "destination_iso3",
                    "destination_name",
                    "destination_tariff_reporter_code",
                    "destination_tariff_mapping_status",
                    "destination_customs_mapping_rule",
                    "coverage_reason",
                ],
                as_index=False,
                dropna=False,
            ).agg(
                baseline_weight=("baseline_weight", "sum"),
                cell_count=("baseline_weight", "size"),
            )
        )

    coverage = pd.concat(coverage_chunks, ignore_index=True) if coverage_chunks else pd.DataFrame()
    coverage = coverage.rename(columns={"exporter_reporter_code": "reporter_code"})
    coverage["tariff_coverage_gate_080"] = coverage["tariff_weight_coverage_i_t"] >= TARIFF_WEIGHT_COVERAGE_MIN
    coverage["tariff_coverage_gate_090"] = coverage["tariff_weight_coverage_i_t"] >= 0.90
    coverage["tariff_coverage_gate_095"] = coverage["tariff_weight_coverage_i_t"] >= 0.95
    panel = sample.merge(coverage, on=["reporter_code", "year"], how="left", validate="one_to_one")
    panel["analysis_sample_after_tariff_coverage"] = panel["tariff_coverage_gate_080"].map(
        {True: "primary_wits_hs4_2001_2021_tariff_coverage_pass", False: "tariff_coverage_below_080_or_missing"}
    )
    coverage_labeled = panel[
        [
            "country",
            "iso3",
            "reporter_code",
            "year",
            "baseline_weight_total",
            "destination_mapped_weight",
            "tariff_weight_coverage_i_t",
            "weighted_tariff_sum",
            "market_access_tariff_avg_i_t",
            "weight_rows",
            "mapped_weight_rows",
            "covered_weight_rows",
            "tariff_coverage_gate_080",
            "tariff_coverage_gate_090",
            "tariff_coverage_gate_095",
        ]
    ].copy()
    decomposition = pd.concat(decomposition_chunks, ignore_index=True) if decomposition_chunks else pd.DataFrame()
    if not decomposition.empty:
        decomposition = decomposition.rename(columns={"exporter_reporter_code": "reporter_code"})
        decomposition = sample[["country", "iso3", "reporter_code", "year"]].merge(
            decomposition,
            on=["reporter_code", "year"],
            how="right",
            validate="one_to_many",
        )
        decomposition = decomposition.sort_values(["iso3", "year", "coverage_reason"]).reset_index(drop=True)
    destination_audit = (
        pd.concat(destination_audit_chunks, ignore_index=True) if destination_audit_chunks else pd.DataFrame()
    )
    if not destination_audit.empty:
        destination_audit = destination_audit.rename(columns={"exporter_reporter_code": "reporter_code"})
        destination_audit = sample[["country", "iso3", "reporter_code", "year"]].merge(
            destination_audit,
            on=["reporter_code", "year"],
            how="right",
            validate="one_to_many",
        )
        destination_audit = destination_audit.sort_values(
            ["coverage_reason", "baseline_weight", "iso3", "year"],
            ascending=[True, False, True, True],
        ).reset_index(drop=True)

    summary = {
        "panel_path": relative_path(DIAGNOSTICS_PANEL_PATH),
        "coverage_path": relative_path(COVERAGE_PATH),
        "coverage_pass_sample_path": relative_path(COVERAGE_PASS_SAMPLE_PATH),
        "uncovered_decomposition_path": relative_path(UNCOVERED_DECOMPOSITION_PATH),
        "destination_uncovered_audit_path": relative_path(DESTINATION_UNCOVERED_AUDIT_PATH),
        "candidate_rows": int(len(sample)),
        "coverage_rows": int(len(coverage_labeled)),
        "uncovered_decomposition_rows": int(len(decomposition)),
        "destination_uncovered_audit_rows": int(len(destination_audit)),
        "rows_with_tariff_coverage": int(panel["tariff_weight_coverage_i_t"].notna().sum()),
        "rows_passing_080": int(panel["tariff_coverage_gate_080"].fillna(False).sum()),
        "rows_passing_090": int(panel["tariff_coverage_gate_090"].fillna(False).sum()),
        "rows_passing_095": int(panel["tariff_coverage_gate_095"].fillna(False).sum()),
        "coverage_min": float(panel["tariff_weight_coverage_i_t"].min())
        if panel["tariff_weight_coverage_i_t"].notna().any()
        else None,
        "coverage_mean": float(panel["tariff_weight_coverage_i_t"].mean())
        if panel["tariff_weight_coverage_i_t"].notna().any()
        else None,
        "coverage_median": float(panel["tariff_weight_coverage_i_t"].median())
        if panel["tariff_weight_coverage_i_t"].notna().any()
        else None,
        "failed_080_examples": panel[
            ~panel["tariff_coverage_gate_080"].fillna(False)
        ][["country", "iso3", "reporter_code", "year", "tariff_weight_coverage_i_t"]]
        .head(20)
        .to_dict("records"),
        "exposure_formula": (
            "market_access_tariff_avg_i_t = sum_j,h w_i,j,h,0 * tariff_j,h,t / "
            "sum_j,h w_i,j,h,0 over covered tariff cells; report tariff_weight_coverage_i_t separately."
        ),
    }
    return panel, coverage_labeled, decomposition, destination_audit, summary


def summarize_hs4_gate(coverage: pd.DataFrame) -> dict[str, Any]:
    if coverage.empty:
        return {"status": "missing_hs4_baseline_harmonization_coverage"}
    value = pd.to_numeric(coverage["hs4_bridge_trade_value_coverage"], errors="coerce").min()
    return {
        "path": relative_path(HS4_BASELINE_COVERAGE_PATH),
        "rows": int(len(coverage)),
        "min_hs4_bridge_trade_value_coverage": float(value),
        "threshold": HS4_HARMONIZATION_COVERAGE_MIN,
        "status": "passed" if value >= HS4_HARMONIZATION_COVERAGE_MIN else "blocked_hs4_gate_failed",
    }


def build_markdown(diagnostics: dict[str, Any]) -> str:
    sample = diagnostics["sample"]
    weights = diagnostics["baseline_weights"]
    destination = diagnostics["destination_mapping"]
    skeleton = diagnostics["pull_skeleton"]
    pulls = diagnostics["wits_pulls"]
    tariffs = diagnostics["hs4_tariffs"]
    panel = diagnostics["market_access_panel"]
    blockers = diagnostics["blockers"]
    lines = [
        "# HS4 WITS Tariff Diagnostics",
        "",
        f"Created UTC: `{diagnostics['created_at_utc']}`",
        "",
        "## Verdict",
        "",
        "- This is diagnostics-only output. No regression table should be treated as usable from this run.",
        f"- Blockers: `{', '.join(blockers) if blockers else 'none'}`.",
        f"- WITS datatype: `{diagnostics['datatype']}`.",
        "- Tariffs are destination/importer-side WITS TRAINS MFN/world rates, not exporter-side schedules.",
        "- Raw WITS source product codes are collapsed immediately to `harmonized_hs4`; processed outputs are not keyed by HS6.",
        "",
        "## Sample",
        "",
        f"- Candidate sample rows: `{sample['rows']}`.",
        f"- Countries: `{sample['countries']}`.",
        f"- Years: `{sample['year_min']}`-`{sample['year_max']}`.",
        f"- Duplicate `iso3-reporter_code-year` rows: `{sample['duplicate_keys']}`.",
        "",
        "## Baseline Weights",
        "",
        f"- Output: `{weights['path']}`.",
        f"- Rows: `{weights['rows']}`.",
        f"- Unique destinations: `{weights['destinations']}`.",
        f"- Unique HS4 products: `{weights['harmonized_hs4']}`.",
        f"- Excluded HS6 `999999` rows before HS4 aggregation: `{weights['excluded_999999_rows']}`.",
        f"- Excluded `partnerCode == 0` rows before aggregation: `{weights['excluded_world_rows']}`.",
        "",
        "## Destination Mapping",
        "",
        f"- Output: `{destination['path']}`.",
        f"- Destination-year rows: `{destination['rows']}`.",
        f"- Tariff reporter codes: `{destination['tariff_reporter_codes']}`.",
        f"- Mapping status counts: `{destination['status_counts']}`.",
        "",
        "## WITS Pull Skeleton",
        "",
        f"- Output: `{skeleton['path']}`.",
        f"- Unique MFN/world all-product destination-year requests: `{skeleton['rows']}`.",
        f"- Existing raw cache rows before pull: `{skeleton['raw_cache_existing_rows']}`.",
        f"- Request HS4 rows: `{skeleton['request_hs4_rows']}`.",
        "",
        "## WITS Pulls And HS4 Tariffs",
        "",
        f"- Raw manifest: `{pulls['path']}`.",
        f"- Pull status counts: `{pulls['status_counts']}`.",
        f"- HS4 tariff output: `{tariffs['path']}`.",
        f"- HS4 tariff rows: `{tariffs['rows']}`.",
        f"- Tariff reporter-years parsed: `{tariffs['tariff_reporter_years']}`.",
        f"- Unique HS4 tariff products: `{tariffs['harmonized_hs4']}`.",
        "",
        "## Coverage Gate",
        "",
        f"- Diagnostics panel: `{panel['panel_path']}`.",
        f"- Coverage table: `{panel['coverage_path']}`.",
        f"- Coverage-pass sample: `{panel['coverage_pass_sample_path']}`.",
        f"- Uncovered-weight decomposition: `{panel['uncovered_decomposition_path']}`.",
        f"- Destination coverage audit: `{panel['destination_uncovered_audit_path']}`.",
        f"- Rows passing `tariff_weight_coverage_i,t >= 0.80`: `{panel.get('rows_passing_080')}`.",
        f"- Rows passing `tariff_weight_coverage_i,t >= 0.90`: `{panel.get('rows_passing_090')}`.",
        f"- Rows passing `tariff_weight_coverage_i,t >= 0.95`: `{panel.get('rows_passing_095')}`.",
        f"- Mean tariff-weight coverage: `{panel.get('coverage_mean')}`.",
        f"- Minimum tariff-weight coverage: `{panel.get('coverage_min')}`.",
        "",
        "## Next Gate",
        "",
        "- Run adversarial econometrics review before using these outputs for any regression table.",
        "- Preferential partner-specific tariff pulls are not included here; this is MFN/world only.",
    ]
    return "\n".join(lines) + "\n"


def run(args: argparse.Namespace) -> dict[str, Any]:
    configure_runtime_datatype(args.datatype)
    ensure_dirs()
    sample = read_primary_sample()
    hs4_coverage = pd.read_csv(HS4_BASELINE_COVERAGE_PATH)
    hs4_gate = summarize_hs4_gate(hs4_coverage)
    if hs4_gate["status"] != "passed" and args.fail_on_gate:
        raise SystemExit("HS4 harmonization coverage gate failed.")

    print("building fixed HS4 baseline weights", flush=True)
    weights, weights_summary = build_hs4_baseline_weights(sample, hs4_coverage)
    weights.to_parquet(BASELINE_WEIGHTS_PATH, index=False)

    print("building destination-side tariff reporter mapping", flush=True)
    destination_mapping, destination_summary = build_destination_tariff_mapping(weights, sample)
    destination_mapping.to_csv(DESTINATION_MAPPING_PATH, index=False)

    destination_codes = sorted(
        destination_mapping["destination_tariff_reporter_code"]
        .replace("", pd.NA)
        .dropna()
        .astype(str)
        .map(normalize_3digit)
        .unique()
        .tolist()
    )
    print(f"checking WITS availability for {len(destination_codes)} destination tariff reporters", flush=True)
    availability, availability_summary = fetch_wits_availability(
        destination_codes,
        refresh=args.refresh_availability,
        timeout=args.timeout,
        max_reporters=args.max_availability_reporters,
    )

    print("building WITS pull skeleton", flush=True)
    skeleton, request_products, skeleton_summary = build_pull_skeleton(sample, weights, destination_mapping, availability)
    skeleton.to_parquet(PULL_SKELETON_PATH, index=False)
    request_products.to_parquet(REQUEST_HS4_PATH, index=False)

    print("checking or pulling WITS tariff caches", flush=True)
    manifest_df, pull_summary = pull_wits_tariffs(
        skeleton,
        pull_wits=args.pull_wits,
        force_refresh=args.force_refresh_pulls,
        max_requests=args.max_requests,
        timeout=args.timeout,
        sleep_seconds=args.sleep_seconds,
    )

    print("parsing cached WITS tariff files and aggregating to HS4", flush=True)
    tariffs, tariff_summary = load_and_aggregate_cached_tariffs(manifest_df, request_products)
    tariffs.to_parquet(HS4_TARIFFS_PATH, index=False)

    print("computing exporter-year tariff coverage diagnostics", flush=True)
    panel, coverage, uncovered_decomposition, destination_audit, panel_summary = compute_market_access_panel(
        sample, weights, destination_mapping, tariffs, skeleton
    )
    coverage.to_csv(COVERAGE_PATH, index=False)
    uncovered_decomposition.to_csv(UNCOVERED_DECOMPOSITION_PATH, index=False)
    destination_audit.to_csv(DESTINATION_UNCOVERED_AUDIT_PATH, index=False)
    panel.to_parquet(DIAGNOSTICS_PANEL_PATH, index=False)
    coverage_pass_sample = panel[panel["tariff_coverage_gate_080"].fillna(False)].copy()
    coverage_pass_sample.to_parquet(COVERAGE_PASS_SAMPLE_PATH, index=False)

    sample_summary = {
        "path": relative_path(PRIMARY_SAMPLE_PATH),
        "rows": int(len(sample)),
        "countries": int(sample["iso3"].nunique()),
        "year_min": int(sample["year"].min()),
        "year_max": int(sample["year"].max()),
        "duplicate_keys": int(sample.duplicated(["iso3", "reporter_code", "year"]).sum()),
    }

    blockers = []
    pull_status_counts = pull_summary.get("status_counts", {})
    incomplete_pull_statuses = {
        "skipped_not_requested",
        "skipped_max_requests",
        "http_or_content_error",
        "request_failed",
    }
    if hs4_gate["status"] != "passed":
        blockers.append("hs4_harmonization_coverage_gate_failed")
    if tariff_summary["rows"] == 0 or any(
        int(pull_status_counts.get(status, 0)) > 0 for status in incomplete_pull_statuses
    ):
        blockers.append("wits_tariff_pulls_not_complete")
    if panel_summary.get("rows_passing_080", 0) != len(sample):
        blockers.append("tariff_weight_coverage_below_080_for_some_rows")

    diagnostics = {
        "created_at_utc": now_utc(),
        "script": relative_path(Path(__file__)),
        "diagnostics_only": True,
        "country_sample": COUNTRY_SAMPLE,
        "tariff_source": "WITS_TRAINS",
        "datatype": DATATYPE,
        "tariff_partner": PARTNER_WORLD,
        "sample": sample_summary,
        "hs4_harmonization_gate": hs4_gate,
        "baseline_weights": weights_summary,
        "destination_mapping": destination_summary,
        "wits_availability": availability_summary,
        "pull_skeleton": skeleton_summary,
        "wits_pulls": pull_summary,
        "hs4_tariffs": tariff_summary,
        "market_access_panel": panel_summary,
        "blockers": blockers,
        "regression_policy": "No regression table is trusted until diagnostics and adversarial econometrics review clear.",
    }
    write_json(MANIFEST_PATH, diagnostics)
    MARKDOWN_PATH.write_text(build_markdown(diagnostics), encoding="utf-8")

    if args.fail_on_gate and blockers:
        raise SystemExit(f"Diagnostics completed with blockers: {blockers}")
    return diagnostics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--datatype",
        default=DEFAULT_DATATYPE,
        help="WITS TRAINS datatype to pull. Default keeps existing AVEEstimated outputs; e.g. use 'reported' for WITS reported tariffs.",
    )
    parser.add_argument("--pull-wits", action="store_true", help="Download missing WITS tariff JSON snapshots.")
    parser.add_argument("--force-refresh-pulls", action="store_true", help="Re-pull WITS tariff JSON even when cached.")
    parser.add_argument("--refresh-availability", action="store_true", help="Refresh WITS availability XML snapshots.")
    parser.add_argument("--max-requests", type=int, default=None, help="Maximum WITS tariff requests to attempt this run.")
    parser.add_argument(
        "--max-availability-reporters",
        type=int,
        default=None,
        help="Limit availability reporter checks for debugging.",
    )
    parser.add_argument("--timeout", type=int, default=60, help="HTTP timeout in seconds.")
    parser.add_argument("--sleep-seconds", type=float, default=0.05, help="Delay between WITS tariff requests.")
    parser.add_argument("--fail-on-gate", action="store_true", help="Exit nonzero when a diagnostics gate fails.")
    return parser.parse_args()


def main() -> None:
    diagnostics = run(parse_args())
    print(
        json.dumps(
            {
                "created_at_utc": diagnostics["created_at_utc"],
                "blockers": diagnostics["blockers"],
                "outputs": {
                    "baseline_weights": relative_path(BASELINE_WEIGHTS_PATH),
                    "pull_skeleton": relative_path(PULL_SKELETON_PATH),
                    "hs4_tariffs": relative_path(HS4_TARIFFS_PATH),
                    "coverage": relative_path(COVERAGE_PATH),
                    "coverage_pass_sample": relative_path(COVERAGE_PASS_SAMPLE_PATH),
                    "uncovered_decomposition": relative_path(UNCOVERED_DECOMPOSITION_PATH),
                    "destination_uncovered_audit": relative_path(DESTINATION_UNCOVERED_AUDIT_PATH),
                    "panel": relative_path(DIAGNOSTICS_PANEL_PATH),
                    "markdown": relative_path(MARKDOWN_PATH),
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
