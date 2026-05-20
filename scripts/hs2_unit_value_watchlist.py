#!/usr/bin/env python3
"""Build an HS2 unit-value watchlist from Comtrade raw files.

This is a screening tool, not a price index. It uses reported trade value per
reported net weight, so it is useful for flagging high-value-per-kg chapters
that may deserve exclusion/sensitivity checks.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from trade_concentration_pipeline import FLOW_LABELS, RESULTS, hs_bulk_files, normalize_columns, pick_col


HS2_LABELS = {
    "27": "Mineral fuels, oils, petroleum",
    "29": "Organic chemicals",
    "30": "Pharmaceutical products",
    "33": "Essential oils, perfumes, cosmetics",
    "37": "Photographic/cinematographic goods",
    "38": "Miscellaneous chemical products",
    "71": "Precious stones/metals",
    "84": "Machinery/mechanical appliances",
    "85": "Electrical machinery/equipment",
    "87": "Vehicles and parts",
    "88": "Aircraft/spacecraft",
    "89": "Ships/boats/floating structures",
    "90": "Optical/medical/precision instruments",
    "91": "Clocks/watches",
    "92": "Musical instruments",
    "93": "Arms/ammunition",
    "97": "Art/antiques",
}


def header_columns(path: Path) -> tuple[list[str], str | None]:
    compression = "gzip" if path.suffix == ".gz" else None
    try:
        header = pd.read_csv(path, compression=compression, nrows=0)
        if len(header.columns) == 1:
            raise ValueError("single column after comma parse")
        return header.columns.tolist(), None
    except Exception:
        header = pd.read_csv(path, sep="\t", compression=compression, nrows=0)
        return header.columns.tolist(), "\t"


def selected_raw_columns(path: Path) -> tuple[list[str], str | None]:
    columns, sep = header_columns(path)
    normalized = normalize_columns(pd.DataFrame(columns=columns))
    needed = []
    for candidates in [
        ["cmdCode", "commodityCode", "Commodity Code"],
        ["primaryValue", "Trade Value (US$)", "Trade Value", "tradeValue", "fobvalue", "cifvalue"],
        ["netWgt", "netweight", "Netweight (kg)"],
        ["reporterCode", "Reporter Code"],
        ["period", "refYear", "year"],
        ["partnerCode", "Partner Code"],
        ["flowCode", "Trade Flow Code"],
        ["flowDesc", "Trade Flow"],
        ["isAggregate", "isaggregate"],
    ]:
        try:
            normalized_name = pick_col(normalized, candidates)
        except KeyError:
            continue
        original = next(col for col in columns if "".join(ch for ch in col.lower() if ch.isalnum()) == normalized_name)
        if original not in needed:
            needed.append(original)
    return needed, sep


def chunk_to_hs2_summary(chunk: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    chunk = normalize_columns(chunk)
    cmd_col = pick_col(chunk, ["cmdCode", "commodityCode", "Commodity Code"])
    value_col = pick_col(chunk, ["primaryValue", "Trade Value (US$)", "Trade Value", "tradeValue", "fobvalue", "cifvalue"])
    weight_col = pick_col(chunk, ["netWgt", "netweight", "Netweight (kg)"])
    partner_col = pick_col(chunk, ["partnerCode", "Partner Code"])

    flow_col = None
    for candidates in (["flowCode", "Trade Flow Code"], ["flowDesc", "Trade Flow"]):
        try:
            flow_col = pick_col(chunk, candidates)
            break
        except KeyError:
            continue
    if flow_col is None:
        raise KeyError("No flow column found.")

    out = pd.DataFrame(
        {
            "cmd_code": chunk[cmd_col].astype(str).str.replace(r"\.0$", "", regex=True),
            "flow_raw": chunk[flow_col],
            "partner_code": pd.to_numeric(chunk[partner_col], errors="coerce"),
            "trade_value": pd.to_numeric(chunk[value_col], errors="coerce"),
            "netwgt_kg": pd.to_numeric(chunk[weight_col], errors="coerce"),
        }
    )
    out["flow"] = out["flow_raw"].map(FLOW_LABELS)
    missing_flow = out["flow"].isna()
    if missing_flow.any():
        raw_lower = out.loc[missing_flow, "flow_raw"].astype(str).str.lower()
        out.loc[missing_flow & raw_lower.str.contains("export"), "flow"] = "Exports"
        out.loc[missing_flow & raw_lower.str.contains("import"), "flow"] = "Imports"

    if "isaggregate" in chunk.columns:
        out["is_aggregate"] = pd.to_numeric(chunk["isaggregate"], errors="coerce").fillna(0).astype(int)
        out = out[out["is_aggregate"] == 0]

    out = out.dropna(subset=["partner_code", "trade_value", "flow"])
    out = out[(out["partner_code"] != 0) & (out["trade_value"] > 0)]
    out = out[out["cmd_code"].str.match(r"^\d{6}$", na=False)]
    out = out[out["flow"].isin(["Exports", "Imports"])]
    if out.empty:
        return pd.DataFrame(), pd.DataFrame()

    out["hs2"] = out["cmd_code"].str[:2]
    totals = out.groupby(["hs2", "flow"], as_index=False)["trade_value"].sum()
    with_weight = out[(out["netwgt_kg"] > 0) & np.isfinite(out["netwgt_kg"])].copy()
    weighted = with_weight.groupby(["hs2", "flow"], as_index=False).agg(
        value_with_netwgt=("trade_value", "sum"),
        netwgt_kg=("netwgt_kg", "sum"),
        rows_with_netwgt=("trade_value", "size"),
    )
    return totals, weighted


def build_watchlist(max_files: int | None, chunksize: int) -> pd.DataFrame:
    total_frames = []
    weighted_frames = []
    files = hs_bulk_files(max_files=max_files)
    for idx, path in enumerate(files, start=1):
        print(f"[{idx}/{len(files)}] Unit-value scan from {path.name}", flush=True)
        usecols, sep = selected_raw_columns(path)
        compression = "gzip" if path.suffix == ".gz" else None
        reader = pd.read_csv(path, sep=sep, compression=compression, usecols=usecols, chunksize=chunksize, low_memory=False)
        for chunk in reader:
            totals, weighted = chunk_to_hs2_summary(chunk)
            if not totals.empty:
                total_frames.append(totals)
            if not weighted.empty:
                weighted_frames.append(weighted)

    totals = pd.concat(total_frames, ignore_index=True).groupby(["hs2", "flow"], as_index=False)["trade_value"].sum()
    weighted = pd.concat(weighted_frames, ignore_index=True).groupby(["hs2", "flow"], as_index=False).agg(
        value_with_netwgt=("value_with_netwgt", "sum"),
        netwgt_kg=("netwgt_kg", "sum"),
        rows_with_netwgt=("rows_with_netwgt", "sum"),
    )
    out = totals.merge(weighted, on=["hs2", "flow"], how="left")
    out["value_with_netwgt"] = out["value_with_netwgt"].fillna(0.0)
    out["netwgt_kg"] = out["netwgt_kg"].fillna(0.0)
    out["rows_with_netwgt"] = out["rows_with_netwgt"].fillna(0).astype(int)
    out["netwgt_value_coverage"] = out["value_with_netwgt"] / out["trade_value"].replace(0, np.nan)
    out["usd_per_kg"] = out["value_with_netwgt"] / out["netwgt_kg"].replace(0, np.nan)
    out["hs2_label"] = out["hs2"].map(HS2_LABELS).fillna("")
    return out.sort_values(["usd_per_kg", "trade_value"], ascending=[False, False])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-files", type=int, default=None)
    parser.add_argument("--chunksize", type=int, default=250_000)
    args = parser.parse_args()

    out = build_watchlist(max_files=args.max_files, chunksize=args.chunksize)
    path = RESULTS / "exercise_10_tables" / "hs2_unit_value_watchlist.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False)
    print(f"Wrote {path}", flush=True)


if __name__ == "__main__":
    main()
