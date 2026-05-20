#!/usr/bin/env python3
"""
Build OECD reference inputs for Exercise 11.

Inputs are the official OECD BTiGE HS-to-CPA/end-use conversion key and the
OECD 2025 regular ICIO CSV bundles. Outputs match the local schema expected by
scripts/trade_concentration_pipeline.py.
"""

from __future__ import annotations

import argparse
import gc
import json
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import requests


ROOT = Path(__file__).resolve().parents[1]
OECD_RAW = ROOT / "data" / "raw" / "oecd_icio"
BTIGE_XLSX = OECD_RAW / "OECD-Bilateral-Trade-in-Goods-End-use-Conversion-Key.xlsx"
ICIO_README_XLSX = OECD_RAW / "OECD-ICIO-2025-ReadMe-regular.xlsx"
ICIO_README_ALT = OECD_RAW / "OECD-ICIO-2025-ReadMe-regular.csv"
BRIDGE_OUT = OECD_RAW / "oecd_btige_hs_to_sector_bridge.csv"
REQUIREMENTS_OUT = OECD_RAW / "oecd_icio_imported_input_requirements.parquet"
MANIFEST_OUT = OECD_RAW / "exercise_11_oecd_sources_manifest.json"

BTIGE_URL = "https://webfs-sti.oecd.org/files/STI-PIE/BTIGE/OECD-Bilateral-Trade-in-Goods-End-use-Conversion-Key.xlsx"
ICIO_README_URL = "https://stats.oecd.org/wbos/fileview2.aspx?IDFile=71a2673b-862a-4a1c-b1d7-6b6255973c90"
ICIO_BUNDLES = [
    {
        "name": "1995-2000_SML.zip",
        "url": "https://stats.oecd.org/wbos/fileview2.aspx?IDFile=f337e03f-697a-4495-a772-78e8963da2d0",
        "years": list(range(1995, 2001)),
    },
    {
        "name": "2001-2005_SML.zip",
        "url": "https://stats.oecd.org/wbos/fileview2.aspx?IDFile=873eb327-a175-449e-9608-677d1b9ebf83",
        "years": list(range(2001, 2006)),
    },
    {
        "name": "2006-2010_SML.zip",
        "url": "https://stats.oecd.org/wbos/fileview2.aspx?IDFile=dac9b40c-a3ab-4689-83c7-a9015b289dc1",
        "years": list(range(2006, 2011)),
    },
    {
        "name": "2011-2015_SML.zip",
        "url": "https://stats.oecd.org/wbos/fileview2.aspx?IDFile=5cb62314-8367-4a1f-a1bf-ae7a8064fd41",
        "years": list(range(2011, 2016)),
    },
    {
        "name": "2016-2022_SML.zip",
        "url": "https://stats.oecd.org/wbos/fileview2.aspx?IDFile=7af46a6a-c5a6-4ba1-91d8-5c09ea436cd9",
        "years": list(range(2016, 2023)),
    },
]

HS_VERSION_MAP = {str(i): f"H{i}" for i in range(7)}

CPA_TO_ICIO = {
    "A01": "A01",
    "A02": "A02",
    "A03": "A03",
    "B05": "B05",
    "B06": "B06",
    "B071": "B07",
    "B072": "B07",
    "B08": "B08",
    "B09": "B09",
    "C10": "C10T12",
    "C11": "C10T12",
    "C12": "C10T12",
    "C13": "C13T15",
    "C14": "C13T15",
    "C15": "C13T15",
    "C16": "C16",
    "C17": "C17_18",
    "C18": "C17_18",
    "C19": "C19",
    "C20": "C20",
    "C21": "C21",
    "C22": "C22",
    "C23": "C23",
    "C24A": "C24A",
    "C24B": "C24B",
    "C254": "C25",
    "C25X254": "C25",
    "C261": "C26",
    "C262": "C26",
    "C263": "C26",
    "C264": "C26",
    "C265": "C26",
    "C266": "C26",
    "C267": "C26",
    "C268": "C26",
    "C27": "C27",
    "C28": "C28",
    "C29": "C29",
    "C301": "C301",
    "C302_309": "C302T309",
    "C303": "C302T309",
    "C304": "C302T309",
    "C31": "C31T33",
    "C325": "C31T33",
    "C32X325": "C31T33",
    "D35": "D",
    "E38": "E",
    "H53": "H53",
    "J58": "J58T60",
    "J59_60": "J58T60",
    "M71": "M",
    "M74": "M",
    "R90": "R",
    "R91": "R",
}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def download(url: str, path: Path) -> None:
    if path.exists() and path.stat().st_size > 0:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with requests.get(url, stream=True, timeout=60) as response:
        response.raise_for_status()
        with tmp.open("wb") as fh:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fh.write(chunk)
    tmp.replace(path)


def ensure_sources(download_missing: bool) -> None:
    if download_missing:
        download(BTIGE_URL, BTIGE_XLSX)
        download(ICIO_README_URL, ICIO_README_XLSX)
        for bundle in ICIO_BUNDLES:
            download(bundle["url"], OECD_RAW / bundle["name"])

    missing = [str(BTIGE_XLSX)]
    readme = readme_path()
    if BTIGE_XLSX.exists():
        missing = []
    if readme is None:
        missing.append(str(ICIO_README_XLSX))
    for bundle in ICIO_BUNDLES:
        path = OECD_RAW / bundle["name"]
        if not path.exists():
            missing.append(str(path))
    if missing:
        raise FileNotFoundError("Missing OECD source files:\n" + "\n".join(missing))


def readme_path() -> Path | None:
    if ICIO_README_XLSX.exists():
        return ICIO_README_XLSX
    if ICIO_README_ALT.exists():
        return ICIO_README_ALT
    return None


def normalized_hs_version(value: object) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if re.fullmatch(r"\d+(\.0+)?", text):
        text = str(int(float(text)))
    text = text.upper().replace("HS", "H")
    return HS_VERSION_MAP.get(text, text if text.startswith("H") else "")


def normalized_hs6_code(value: object) -> str | None:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    text = str(value).strip()
    if re.fullmatch(r"\d+(\.0+)?", text):
        text = str(int(float(text)))
    if not re.fullmatch(r"\d{5,6}", text):
        return None
    return text.zfill(6)


def cpa_to_icio_sector(cpa: object) -> str | None:
    text = str(cpa).strip().upper()
    if not text or text in {"NAN", "NONE", "_X"}:
        return None
    return CPA_TO_ICIO.get(text)


def load_sector_labels() -> dict[str, str]:
    path = readme_path()
    if path is None:
        raise FileNotFoundError(f"Missing {ICIO_README_XLSX}")
    raw = pd.read_excel(path, sheet_name="Area_Activities", header=None)
    sector_table = raw.iloc[:, [9, 10]].rename(columns={9: "code", 10: "label"})
    sector_table = sector_table.dropna(subset=["code", "label"])
    sector_table["code"] = sector_table["code"].astype(str).str.strip()
    sector_table["label"] = sector_table["label"].astype(str).str.strip()
    sector_table = sector_table[sector_table["code"].str.match(r"^[A-Z][A-Z0-9_T]*$")]
    labels = dict(zip(sector_table["code"], sector_table["label"], strict=False))
    missing = sorted(set(CPA_TO_ICIO.values()) - set(labels))
    if missing:
        raise RuntimeError(f"ICIO readme is missing sector labels for: {missing}")
    return labels


def build_sector_bridge(sector_labels: dict[str, str]) -> pd.DataFrame:
    raw = pd.read_excel(BTIGE_XLSX, sheet_name="BTiGE FromHS-ToCPA-ToENDUSE", dtype={"HS-code": str})
    bridge = pd.DataFrame(
        {
            "classification_code": raw["HS-version"].map(normalized_hs_version),
            "cmd_code": raw["HS-code"].map(normalized_hs6_code),
            "io_sector_code": raw["CPA"].map(cpa_to_icio_sector),
        }
    )
    bridge = bridge.dropna(subset=["classification_code", "cmd_code", "io_sector_code"])
    bridge["io_sector_label"] = bridge["io_sector_code"].map(sector_labels).fillna(bridge["io_sector_code"])
    bridge = bridge.drop_duplicates().sort_values(["classification_code", "cmd_code"])

    duplicate = bridge.duplicated(["classification_code", "cmd_code"], keep=False)
    if duplicate.any():
        examples = bridge.loc[duplicate, ["classification_code", "cmd_code", "io_sector_code"]].head(20)
        raise RuntimeError("BTiGE bridge is not one-to-one after CPA-to-ICIO mapping:\n" + examples.to_string(index=False))

    BRIDGE_OUT.parent.mkdir(parents=True, exist_ok=True)
    bridge.to_csv(BRIDGE_OUT, index=False)
    return bridge


def load_item_sheet(sheet_name: str, valid_industries: set[str]) -> pd.DataFrame:
    path = readme_path()
    if path is None:
        raise FileNotFoundError(f"Missing {ICIO_README_XLSX}")
    raw = pd.read_excel(path, sheet_name=sheet_name, header=2, dtype=str)
    raw = raw.rename(columns=lambda col: str(col).strip())
    out = raw[["Sector code", "Country", "Industry/Final demand"]].copy()
    out = out.rename(
        columns={
            "Sector code": "sector_code",
            "Country": "country",
            "Industry/Final demand": "industry",
        }
    )
    out = out.dropna(subset=["sector_code", "country", "industry"])
    out["sector_code"] = out["sector_code"].astype(str).str.strip()
    out["country"] = out["country"].astype(str).str.strip()
    out["industry"] = out["industry"].astype(str).str.strip()
    out = out[out["industry"].isin(valid_industries)]
    return out.reset_index(drop=True)


def find_year_member(zf: zipfile.ZipFile, year: int) -> str:
    candidates = [f"{year}_SML.csv", f"{year}_SML.CSV", f"{year}.csv", f"{year}.CSV"]
    names = {Path(name).name: name for name in zf.namelist()}
    for candidate in candidates:
        if candidate in names:
            return names[candidate]
    raise FileNotFoundError(f"Could not find a CSV for {year} in {zf.filename}")


def stack_nonmissing(frame: pd.DataFrame) -> pd.Series:
    try:
        stacked = frame.stack(future_stack=True)
    except TypeError:
        stacked = frame.stack(dropna=True)
    return stacked.dropna()


def compute_year_requirements(
    zip_path: Path,
    year: int,
    row_items: pd.DataFrame,
    col_items: pd.DataFrame,
    sector_labels: dict[str, str],
) -> pd.DataFrame:
    row_ids = row_items["sector_code"].tolist()
    col_ids = col_items["sector_code"].tolist()
    row_meta = row_items.set_index("sector_code")
    col_meta = col_items.set_index("sector_code")

    with zipfile.ZipFile(zip_path) as zf:
        member = find_year_member(zf, year)
        with zf.open(member) as fh:
            raw = pd.read_csv(fh, na_values=["na", "NA", "NaN", ""], low_memory=False)

    row_col = raw.columns[0]
    raw[row_col] = raw[row_col].astype(str).str.strip()
    raw = raw.set_index(row_col)
    missing_rows = sorted(set(row_ids) - set(raw.index))
    missing_cols = sorted(set(col_ids) - set(raw.columns))
    if missing_rows or missing_cols or "OUT" not in raw.columns:
        raise RuntimeError(
            f"ICIO {year} has unexpected row/column structure: "
            f"missing_rows={missing_rows[:5]}, missing_cols={missing_cols[:5]}, has_OUT={'OUT' in raw.columns}"
        )

    z_matrix = raw.loc[row_ids, col_ids].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    output = pd.to_numeric(raw.loc[col_ids, "OUT"], errors="coerce")
    del raw

    frames: list[pd.DataFrame] = []
    for country, country_cols in col_items.groupby("country", sort=True):
        cols = country_cols["sector_code"].tolist()
        foreign_rows = row_meta.index[row_meta["country"] != country].tolist()
        imported = z_matrix.loc[foreign_rows, cols].groupby(row_meta.loc[foreign_rows, "industry"]).sum()
        if imported.empty:
            continue

        shares = imported.div(output.loc[cols].replace(0, np.nan), axis=1)
        long = stack_nonmissing(shares).rename("imported_input_requirement_share").reset_index()
        long = long[long["imported_input_requirement_share"] > 0].copy()
        if long.empty:
            continue

        long = long.rename(columns={"industry": "input_sector_code", "level_1": "output_sector_id"})
        long["iso3"] = country
        long["year"] = int(year)
        long["output_sector_code"] = long["output_sector_id"].map(col_meta["industry"])
        long["input_sector_label"] = long["input_sector_code"].map(sector_labels)
        long["output_sector_label"] = long["output_sector_code"].map(sector_labels)
        frames.append(
            long[
                [
                    "iso3",
                    "year",
                    "output_sector_code",
                    "input_sector_code",
                    "imported_input_requirement_share",
                    "output_sector_label",
                    "input_sector_label",
                ]
            ]
        )

    del z_matrix
    gc.collect()
    if not frames:
        return pd.DataFrame(
            columns=[
                "iso3",
                "year",
                "output_sector_code",
                "input_sector_code",
                "imported_input_requirement_share",
                "output_sector_label",
                "input_sector_label",
            ]
        )
    return pd.concat(frames, ignore_index=True)


def build_input_requirements(sector_labels: dict[str, str]) -> dict[str, object]:
    row_items = load_item_sheet("RowItems", set(sector_labels))
    col_items = load_item_sheet("ColItems", set(sector_labels))
    if len(row_items) != len(col_items):
        raise RuntimeError(f"Row/column ICIO industry counts differ: {len(row_items)} vs {len(col_items)}")

    if REQUIREMENTS_OUT.exists():
        REQUIREMENTS_OUT.unlink()

    writer: pq.ParquetWriter | None = None
    total_rows = 0
    years_written: list[int] = []
    try:
        for bundle in ICIO_BUNDLES:
            zip_path = OECD_RAW / bundle["name"]
            for year in bundle["years"]:
                print(f"Building Exercise 11 ICIO imported input requirements for {year}", flush=True)
                year_frame = compute_year_requirements(zip_path, year, row_items, col_items, sector_labels)
                table = pa.Table.from_pandas(year_frame, preserve_index=False)
                if writer is None:
                    writer = pq.ParquetWriter(REQUIREMENTS_OUT, table.schema, compression="zstd")
                writer.write_table(table)
                total_rows += int(len(year_frame))
                years_written.append(int(year))
                del year_frame, table
                gc.collect()
    finally:
        if writer is not None:
            writer.close()

    return {
        "rows": total_rows,
        "years": years_written,
        "row_items": int(len(row_items)),
        "column_items": int(len(col_items)),
        "countries": int(row_items["country"].nunique()),
        "industries": int(row_items["industry"].nunique()),
    }


def write_manifest(bridge: pd.DataFrame, requirements_details: dict[str, object]) -> None:
    manifest = {
        "created_at_utc": now_utc(),
        "btige": {
            "source_url": BTIGE_URL,
            "raw_file": str(BTIGE_XLSX.relative_to(ROOT)),
            "bridge_file": str(BRIDGE_OUT.relative_to(ROOT)),
            "bridge_rows": int(len(bridge)),
            "classification_codes": sorted(bridge["classification_code"].unique().tolist()),
        },
        "icio": {
            "readme_url": ICIO_README_URL,
            "readme_file": str(readme_path().relative_to(ROOT)) if readme_path() else None,
            "requirement_file": str(REQUIREMENTS_OUT.relative_to(ROOT)),
            "bundles": [
                {
                    "source_url": bundle["url"],
                    "raw_file": str((OECD_RAW / bundle["name"]).relative_to(ROOT)),
                    "years": bundle["years"],
                }
                for bundle in ICIO_BUNDLES
            ],
            **requirements_details,
        },
    }
    MANIFEST_OUT.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build OECD BTiGE/ICIO inputs for Exercise 11.")
    parser.add_argument("--download", action="store_true", help="Download missing OECD source files before building.")
    parser.add_argument("--bridge-only", action="store_true", help="Only build the BTiGE HS-to-ICIO bridge.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    ensure_sources(download_missing=args.download)
    sector_labels = load_sector_labels()
    bridge = build_sector_bridge(sector_labels)
    if args.bridge_only:
        requirements_details: dict[str, object] = {"skipped": True}
    else:
        requirements_details = build_input_requirements(sector_labels)
    write_manifest(bridge, requirements_details)
    print(f"Wrote {BRIDGE_OUT.relative_to(ROOT)} with {len(bridge):,} rows", flush=True)
    if not args.bridge_only:
        print(
            f"Wrote {REQUIREMENTS_OUT.relative_to(ROOT)} with {requirements_details['rows']:,} rows",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
