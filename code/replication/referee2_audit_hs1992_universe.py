#!/usr/bin/env python3
"""Independent audit of the fixed HS1992 universe and H6 weighted mappings."""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
WEIGHTS_PATH = ROOT / "data/processed/lt_hgl_hs6_to_hs1992_weights.parquet"
H0_PATH = ROOT / "data/raw/classifications/H0.json"
UNIVERSE_PATH = ROOT / "results/samples/cadot_broad_156/three_metric_tables/product_universe.csv"
PANEL_PATH = ROOT / "results/samples/cadot_broad_156/three_metric_tables/metric_headline_product_panel.parquet"
RAW_DIR = ROOT / "data/raw/comtrade/bulk"
COMTRADE_ROOT = ROOT / "data/raw/comtrade"
OUTPUT_DIR = ROOT / "code/replication"
FIXED_K = 5037
SAMPLE_ISO3 = ("USA", "CHN", "AUS", "ALB", "BFA")


def active_gini(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    values = np.sort(values[np.isfinite(values) & (values > 0)])
    n = len(values)
    if n == 0:
        return np.nan
    ranks = np.arange(1, n + 1, dtype=float)
    return float(2 * np.sum(ranks * values) / (n * values.sum()) - (n + 1) / n)


def fixed_theil(values: np.ndarray, k: int = FIXED_K) -> float:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values) & (values > 0)]
    shares = values / values.sum()
    return float(np.sum(shares * np.log(shares * k)))


def hhi(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values) & (values > 0)]
    shares = values / values.sum()
    return float(np.sum(shares**2))


def classification_audit(weights: pd.DataFrame, universe: pd.DataFrame) -> pd.DataFrame:
    records = json.loads(H0_PATH.read_text(encoding="utf-8"))["results"]
    h0 = pd.DataFrame(records)
    h0["id"] = h0["id"].astype(str)
    official = h0[
        h0["isLeaf"].astype(str).eq("1")
        & pd.to_numeric(h0["aggrlevel"], errors="coerce").eq(6)
        & h0["id"].str.fullmatch(r"\d{6}")
        & h0["id"].ne("999999")
    ].copy()
    target_codes = set(weights["target_cmd_code"].astype(str).str.zfill(6))
    observed_codes = set(universe["product_id"].str.split(":").str[-1])
    official_codes = set(official["id"])
    rows = [
        {"item": "official_numeric_hs1992_leaf_codes_excluding_999999", "value": len(official_codes)},
        {"item": "weighted_crosswalk_target_codes", "value": len(target_codes)},
        {"item": "observed_world_broad_fixed_universe_codes", "value": len(observed_codes)},
        {"item": "crosswalk_targets_not_official_numeric_leaves", "value": len(target_codes - official_codes)},
        {"item": "official_numeric_leaves_not_observed", "value": len(official_codes - observed_codes)},
        {"item": "observed_codes_not_official_numeric_leaves", "value": len(observed_codes - official_codes)},
    ]
    return pd.DataFrame(rows)


def read_source_products(path: Path) -> pd.DataFrame:
    usecols = ["flowCode", "partnerCode", "cmdCode", "primaryValue", "isAggregate"]
    chunks: list[pd.DataFrame] = []
    for chunk in pd.read_csv(
        path,
        sep="\t",
        compression="gzip",
        usecols=usecols,
        dtype={"flowCode": "string", "cmdCode": "string"},
        chunksize=500_000,
        low_memory=False,
    ):
        chunk["partnerCode"] = pd.to_numeric(chunk["partnerCode"], errors="coerce")
        chunk["isAggregate"] = pd.to_numeric(chunk["isAggregate"], errors="coerce").fillna(0)
        chunk["trade_value"] = pd.to_numeric(chunk["primaryValue"], errors="coerce")
        chunk["cmd_code"] = chunk["cmdCode"].astype("string").str.extract(r"(\d{1,6})", expand=False).str.zfill(6)
        chunk["flow"] = chunk["flowCode"].map({"X": "Exports", "M": "Imports"})
        chunk = chunk[
            chunk["flow"].notna()
            & chunk["partnerCode"].ne(0)
            & chunk["isAggregate"].eq(0)
            & chunk["cmd_code"].str.fullmatch(r"\d{6}", na=False)
            & chunk["cmd_code"].ne("999999")
            & chunk["trade_value"].gt(0)
        ]
        if not chunk.empty:
            chunks.append(chunk.groupby(["flow", "cmd_code"], as_index=False)["trade_value"].sum())
    if not chunks:
        return pd.DataFrame(columns=["flow", "cmd_code", "trade_value"])
    return pd.concat(chunks, ignore_index=True).groupby(["flow", "cmd_code"], as_index=False)["trade_value"].sum()


def metric_record(values: pd.Series | np.ndarray) -> dict[str, float | int]:
    array = np.asarray(values, dtype=float)
    array = array[np.isfinite(array) & (array > 0)]
    return {
        "active_count": int(len(array)),
        "gini": active_gini(array),
        "theil_fixed_k5037": fixed_theil(array),
        "hhi": hhi(array),
    }


def file_audit(meta: pd.Series, h6_weights: pd.DataFrame, fanout: pd.Series) -> list[dict[str, object]]:
    raw_path = RAW_DIR / str(meta["source_raw_file"])
    if not raw_path.exists():
        matches = list(COMTRADE_ROOT.rglob(glob.escape(str(meta["source_raw_file"]))))
        if len(matches) != 1:
            raise FileNotFoundError(
                f"Expected one raw file named {meta['source_raw_file']}, found {len(matches)}."
            )
        raw_path = matches[0]
    source = read_source_products(raw_path)
    rows: list[dict[str, object]] = []
    max_target = (
        h6_weights.sort_values(["source_cmd_code", "weight", "target_cmd_code"], ascending=[True, False, True])
        .drop_duplicates("source_cmd_code")
        [["source_cmd_code", "target_cmd_code"]]
    )
    for flow, group in source.groupby("flow", sort=True):
        group = group.copy()
        group["fanout"] = group["cmd_code"].map(fanout).fillna(0).astype(int)
        total = group["trade_value"].sum()
        weighted = group.merge(
            h6_weights[["source_cmd_code", "target_cmd_code", "weight"]],
            left_on="cmd_code",
            right_on="source_cmd_code",
            how="left",
            validate="one_to_many",
        )
        if weighted["target_cmd_code"].isna().any():
            missing = weighted.loc[weighted["target_cmd_code"].isna(), "cmd_code"].drop_duplicates().tolist()
            raise RuntimeError(f"Missing H6 weights for {raw_path.name}: {missing[:10]}")
        weighted["converted_value"] = weighted["trade_value"] * weighted["weight"]
        target = weighted.groupby("target_cmd_code", as_index=False)["converted_value"].sum()

        deterministic = group.merge(
            max_target,
            left_on="cmd_code",
            right_on="source_cmd_code",
            how="left",
            validate="one_to_one",
        )
        deterministic_target = deterministic.groupby("target_cmd_code", as_index=False)["trade_value"].sum()

        base = {
            "iso3": str(meta["iso3"]),
            "country": str(meta["country"]),
            "reporter_code": int(meta["reporter_code"]),
            "year": int(meta["year"]),
            "flow": str(flow),
            "source_file": raw_path.name,
            "source_trade_value": float(total),
            "fanout_ge20_value_share": float(group.loc[group["fanout"].ge(20), "trade_value"].sum() / total),
            "fanout_ge100_value_share": float(group.loc[group["fanout"].ge(100), "trade_value"].sum() / total),
            "weighted_target_value_lt_1_count": int((target["converted_value"] < 1).sum()),
            "weighted_target_value_lt_100_count": int((target["converted_value"] < 100).sum()),
            "weighted_target_value_lt_1000_count": int((target["converted_value"] < 1000).sum()),
        }
        for method, values in [
            ("native_h6", group["trade_value"]),
            ("weighted_hs1992", target["converted_value"]),
            ("max_weight_hs1992", deterministic_target["trade_value"]),
        ]:
            rows.append({**base, "method": method, **metric_record(values)})
    return rows


def transition_audit(panel: pd.DataFrame) -> pd.DataFrame:
    product = panel[
        panel["dimension"].eq("product") & panel["variant"].eq("baseline")
    ].sort_values(["reporter_code", "flow", "year"]).copy()
    product["prev_classification"] = product.groupby(["reporter_code", "flow"])["source_classification_code"].shift()
    product["prev_active_count"] = product.groupby(["reporter_code", "flow"])["active_count"].shift()
    product["active_count_change"] = product["active_count"] - product["prev_active_count"]
    product["switch_to_h6"] = product["source_classification_code"].eq("H6") & product["prev_classification"].ne("H6")
    recent = product[product["year"].ge(2022) & product["prev_classification"].notna()].copy()
    return (
        recent.groupby(["flow", "switch_to_h6"], as_index=False)
        .agg(
            observations=("active_count_change", "size"),
            mean_active_count_change=("active_count_change", "mean"),
            median_active_count_change=("active_count_change", "median"),
        )
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-raw-sample", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    weights = pd.read_parquet(WEIGHTS_PATH)
    weights["source_cmd_code"] = weights["source_cmd_code"].astype(str).str.zfill(6)
    weights["target_cmd_code"] = weights["target_cmd_code"].astype(str).str.zfill(6)
    universe = pd.read_csv(UNIVERSE_PATH, dtype=str)
    panel = pd.read_parquet(PANEL_PATH)

    classification = classification_audit(weights, universe)
    transitions = transition_audit(panel)
    classification.to_csv(OUTPUT_DIR / "referee2_hs1992_universe_counts.csv", index=False)
    transitions.to_csv(OUTPUT_DIR / "referee2_h6_transition_diagnostics.csv", index=False)
    print(classification.to_string(index=False))
    print(transitions.to_string(index=False))

    if not args.skip_raw_sample:
        h6_weights = weights[weights["source_classification_code"].eq("H6")].copy()
        fanout = h6_weights.groupby("source_cmd_code")["target_cmd_code"].nunique()
        sample = (
            panel[
                panel["iso3"].isin(SAMPLE_ISO3)
                & panel["year"].eq(2022)
                & panel["source_classification_code"].eq("H6")
                & panel["dimension"].eq("product")
                & panel["variant"].eq("baseline")
            ]
            .drop_duplicates(["reporter_code", "year", "source_raw_file"])
            .sort_values("iso3")
        )
        rows: list[dict[str, object]] = []
        for _, meta in sample.iterrows():
            print(f"Auditing {meta['iso3']} {meta['source_raw_file']}", flush=True)
            rows.extend(file_audit(meta, h6_weights, fanout))
        raw_results = pd.DataFrame(rows)
        raw_results.to_csv(OUTPUT_DIR / "referee2_h6_mapping_sample.csv", index=False)
        print(raw_results.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
