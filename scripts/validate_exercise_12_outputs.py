#!/usr/bin/env python3
"""Compact validation audit for regenerated Exercise 12 outputs."""

from __future__ import annotations

import json
import sys
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

sys.path.insert(0, str(Path(__file__).resolve().parent))
from trade_concentration_pipeline import (  # noqa: E402
    COUNTRY_SAMPLE_CHOICES,
    configure_country_sample,
    now_utc,
    sample_processed_path,
    sample_results_dir,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "results" / "run_manifest_exercises_02_12.json"
ACCOUNTING_ABS_TOLERANCE = 1e-2
TOP_DEFINITIONS = ("top_10", "top_1pct", "top_5pct")
STRICT_ENTRY_CATEGORIES = {
    "strict_new_item",
    "low_base_under_10k_grower",
    "least_traded_10pct_grower",
}
MAIN_ALLOWED_DRIVER_CATEGORIES = {
    "existing_top_10",
    "existing_non_top_10",
    *STRICT_ENTRY_CATEGORIES,
}
NET_ALLOWED_DRIVER_CATEGORIES = {
    *STRICT_ENTRY_CATEGORIES,
    *(f"existing_top_{suffix}" for suffix in ("10", "1pct", "5pct")),
    *(f"existing_non_top_{suffix}" for suffix in ("10", "1pct", "5pct")),
}
GROSS_ALLOWED_DRIVER_CATEGORIES = {
    *NET_ALLOWED_DRIVER_CATEGORIES,
    *(f"exited_top_{suffix}" for suffix in ("10", "1pct", "5pct")),
    *(f"exited_non_top_{suffix}" for suffix in ("10", "1pct", "5pct")),
    *(f"shrinking_top_{suffix}" for suffix in ("10", "1pct", "5pct")),
    *(f"shrinking_non_top_{suffix}" for suffix in ("10", "1pct", "5pct")),
}


def max_accounting_residual(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    keys = [
        "reporter_code",
        "year",
        "future_year",
        "dimension",
        "horizon",
        "item_id_mode",
        "top_definition",
        "accounting_type",
    ]
    grouped = df.groupby(keys, dropna=False).agg(
        contribution_sum=("contribution", "sum"),
        total_growth=("total_growth", "first"),
    )
    return float((grouped["contribution_sum"] - grouped["total_growth"]).abs().max())


def main_matches_headline_net(main: pd.DataFrame, net: pd.DataFrame) -> bool:
    mask = (
        ((net["dimension"].isin(["product", "product_partner_cell"])) & (net["item_id_mode"] == "hs6_harmonized_family"))
        | ((net["dimension"] == "partner") & (net["item_id_mode"] == "partner"))
    ) & (net["top_definition"] == "top_10")
    headline = net.loc[mask, main.columns].copy()
    sort_cols = list(main.columns)
    left = main.sort_values(sort_cols).reset_index(drop=True)
    right = headline.sort_values(sort_cols).reset_index(drop=True)
    return left.equals(right)


def reporter_set(df: pd.DataFrame) -> set[int]:
    if "reporter_code" not in df.columns:
        return set()
    reporters = pd.to_numeric(df["reporter_code"], errors="coerce").dropna()
    return set(reporters.astype(int).unique().tolist())


def reporter_alignment_audit(
    main: pd.DataFrame,
    net: pd.DataFrame,
    gross: pd.DataFrame,
    scope: pd.DataFrame,
    hs_coverage: pd.DataFrame,
) -> dict[str, object]:
    sets = {
        "main": reporter_set(main),
        "net": reporter_set(net),
        "gross": reporter_set(gross),
        "scope": reporter_set(scope),
        "hs_harmonization_coverage": reporter_set(hs_coverage),
    }
    main_set = sets["main"]
    details: dict[str, object] = {
        f"{name}_reporters": len(value)
        for name, value in sets.items()
    }
    details.update(
        {
            f"{name}_missing_from_main_reporters": sorted(main_set - value)
            for name, value in sets.items()
            if name != "main"
        }
    )
    details.update(
        {
            f"{name}_extra_vs_main_reporters": sorted(value - main_set)
            for name, value in sets.items()
            if name != "main"
        }
    )
    details["reporter_sets_match_main"] = all(value == main_set for value in sets.values())
    return details


def unexpected_driver_categories(df: pd.DataFrame, allowed: set[str]) -> list[str]:
    if "driver_category" not in df.columns:
        return ["<missing driver_category column>"]
    observed = set(df["driver_category"].dropna().astype(str).unique().tolist())
    return sorted(observed - allowed)


def driver_category_schema_audit(
    main: pd.DataFrame,
    net: pd.DataFrame,
    gross: pd.DataFrame,
) -> dict[str, object]:
    stale_counts = {
        "main_stale_new_item_rows": int(main["driver_category"].eq("new_item").sum()),
        "net_stale_new_item_rows": int(net["driver_category"].eq("new_item").sum()),
        "gross_stale_new_item_rows": int(gross["driver_category"].eq("new_item").sum()),
    }
    unexpected = {
        "main_unexpected_driver_categories": unexpected_driver_categories(main, MAIN_ALLOWED_DRIVER_CATEGORIES),
        "net_unexpected_driver_categories": unexpected_driver_categories(net, NET_ALLOWED_DRIVER_CATEGORIES),
        "gross_unexpected_driver_categories": unexpected_driver_categories(gross, GROSS_ALLOWED_DRIVER_CATEGORIES),
    }
    stale_rows = int(sum(stale_counts.values()))
    return {
        **stale_counts,
        "stale_new_item_rows": stale_rows,
        **unexpected,
        "driver_category_schema_valid": stale_rows == 0 and all(not values for values in unexpected.values()),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country-sample", choices=COUNTRY_SAMPLE_CHOICES, default="rd2_countries")
    parser.add_argument("--min-available-years", type=int, default=10)
    parser.add_argument("--start-year", type=int, default=1988)
    parser.add_argument("--end-year", type=int)
    parser.add_argument("--refresh-availability", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_country_sample(
        country_sample=args.country_sample,
        min_available_years=args.min_available_years,
        start_year=args.start_year,
        end_year=args.end_year,
        refresh_availability=args.refresh_availability,
    )
    tables = sample_results_dir(args.country_sample) / "exercise_12_tables"
    audit_path = tables / "exercise_12_validation_audit.json"
    aggregate_path = sample_processed_path("exercise_12_export_aggregates.parquet", args.country_sample)
    manifest = json.loads(MANIFEST.read_text())
    aggregate = ds.dataset(aggregate_path)
    main_df = pd.read_csv(tables / "growth_decomposition.csv")
    net_df = pd.read_csv(tables / "growth_decomposition_net.csv")
    gross_df = pd.read_csv(tables / "growth_decomposition_gross.csv")
    hs_diag = pd.read_csv(tables / "hs_harmonization_diagnostics.csv")
    scope_cols = [
        "reporter_code",
        "product_export_value",
        "unknown_partner_region_value",
        "world_bank_partner_region_value",
        "unknown_partner_region_share",
        "world_bank_partner_region_share",
        "region_transition_reliability",
    ]
    scope = pd.read_csv(tables / "product_destination_region_states.csv", usecols=scope_cols)

    main_key = [
        "reporter_code",
        "year",
        "future_year",
        "dimension",
        "horizon",
        "item_id_mode",
        "top_definition",
        "driver_category",
        "accounting_type",
    ]
    coverage = hs_diag[hs_diag["diagnostic_type"] == "coverage"].copy()
    reporter_audit = reporter_alignment_audit(main_df, net_df, gross_df, scope, coverage)
    category_audit = driver_category_schema_audit(main_df, net_df, gross_df)
    total_scope_value = float(scope["product_export_value"].sum())
    audit = {
        "created_at_utc": now_utc(),
        "manifest_created_at_utc": manifest.get("created_at_utc"),
        "country_sample": args.country_sample,
        "manifest_country_sample": manifest.get("country_sample"),
        "runner_mode": manifest.get("mode"),
        "finalize_only": manifest.get("finalize_only"),
        "reuse_exercise_12_aggregate": manifest.get("reuse_exercise_12_aggregate"),
        "resume_exercise_12_spill": manifest.get("resume_exercise_12_spill"),
        "aggregate_rows": int(aggregate.count_rows()),
        "aggregate_partner_code_0_rows": int(aggregate.count_rows(filter=ds.field("partner_code") == 0)),
        "aggregate_hs6_999999_rows": int(aggregate.count_rows(filter=ds.field("cmd_code") == "999999")),
        "main_rows": int(len(main_df)),
        "net_rows": int(len(net_df)),
        "gross_rows": int(len(gross_df)),
        "main_duplicate_keys": int(main_df.duplicated(main_key).sum()),
        "main_top_definitions": sorted(main_df["top_definition"].dropna().unique().tolist()),
        "main_modes_by_dimension": {
            "|".join(map(str, key)): int(value)
            for key, value in main_df.groupby(["dimension", "item_id_mode"]).size().to_dict().items()
        },
        "main_matches_headline_net": bool(main_matches_headline_net(main_df, net_df)),
        "net_max_accounting_residual": max_accounting_residual(net_df),
        "gross_max_accounting_residual": max_accounting_residual(gross_df),
        "gross_has_item_mode_and_top_definition": bool({"item_id_mode", "top_definition"}.issubset(gross_df.columns)),
        "hs_harmonization_coverage_rows": int(len(coverage)),
        "hs_unmatched_value_share_max": float(pd.to_numeric(coverage["unmatched_value_share"], errors="coerce").max()),
        "hs_ambiguous_value_share_max": float(pd.to_numeric(coverage["ambiguous_value_share"], errors="coerce").max()),
        "scope_rows": int(len(scope)),
        "scope_reporters": int(scope["reporter_code"].nunique()),
        "unknown_region_value_share_total": (
            float(scope["unknown_partner_region_value"].sum() / total_scope_value) if total_scope_value else np.nan
        ),
        "world_bank_region_value_share_total": (
            float(scope["world_bank_partner_region_value"].sum() / total_scope_value) if total_scope_value else np.nan
        ),
        "region_reliability_counts": {
            str(key): int(value)
            for key, value in scope["region_transition_reliability"].value_counts(dropna=False).to_dict().items()
        },
        "debug_scope_artifact_exists": bool((tables / "debug_product_destination_region_states.csv").exists()),
        **reporter_audit,
        **category_audit,
    }
    audit["passed"] = bool(
        audit["manifest_country_sample"] == args.country_sample
        and audit["aggregate_partner_code_0_rows"] == 0
        and audit["aggregate_hs6_999999_rows"] == 0
        and audit["main_duplicate_keys"] == 0
        and audit["main_top_definitions"] == ["top_10"]
        and audit["main_matches_headline_net"]
        and audit["net_max_accounting_residual"] <= ACCOUNTING_ABS_TOLERANCE
        and audit["gross_max_accounting_residual"] <= ACCOUNTING_ABS_TOLERANCE
        and audit["gross_has_item_mode_and_top_definition"]
        and audit["reporter_sets_match_main"]
        and audit["driver_category_schema_valid"]
        and not audit["debug_scope_artifact_exists"]
    )
    audit_path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    print(json.dumps(audit, indent=2, sort_keys=True))
    return 0 if audit["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
