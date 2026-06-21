#!/usr/bin/env python3
"""Finalize H2.4 world supplier-specialization outputs from processed panels.

The source processed panels are global H24 world-product-market benchmarks, not
rd2-country-sample outputs. This script validates that HS6 999999 is absent
before writing tables, figures, the memo, and manifests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


ROOT = Path(__file__).resolve().parents[1]
DATA_PROCESSED = ROOT / "data" / "processed"
RESULTS = ROOT / "results"

PROCESSED_DIR = DATA_PROCESSED / "h24_supplier_specialization"
TABLE_DIR = RESULTS / "h24_supplier_specialization_tables"
FIGURE_DIR = RESULTS / "h24_supplier_specialization_figures"
MEMO_PATH = RESULTS / "h24_supplier_specialization.md"
RESULTS_MANIFEST = RESULTS / "run_manifest_h24_supplier_specialization.json"
PROCESSED_MANIFEST = PROCESSED_DIR / "run_manifest_h24_supplier_specialization.json"

PRODUCT_SUPPLIER_PATH = PROCESSED_DIR / "product_supplier_concentration.parquet"
DOMINANT_PATH = PROCESSED_DIR / "dominant_specialized_suppliers.parquet"
RCA_PATH = PROCESSED_DIR / "exporter_product_rca.parquet"
COMPARISON_PATH = TABLE_DIR / "importer_vs_world_supplier_dominance_comparison.csv"

EXCLUDED_HS6_CODES = {"999999"}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_file_manifest(path: Path) -> dict[str, object]:
    return {
        "path": rel(path),
        "exists": path.exists(),
        "size_bytes": int(path.stat().st_size) if path.exists() else None,
        "mtime_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
        if path.exists()
        else None,
        "sha256": file_sha256(path) if path.exists() else None,
    }


def ensure_dirs() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)


def normalize_cmd(series: pd.Series) -> pd.Series:
    return series.astype(str).str.extract(r"(\d{1,6})", expand=False).str.zfill(6)


def excluded_hs6_count(frame: pd.DataFrame, code_col: str = "cmd_code") -> int:
    if frame.empty or code_col not in frame.columns:
        return 0
    return int(normalize_cmd(frame[code_col]).isin(EXCLUDED_HS6_CODES).sum())


def assert_no_excluded_hs6(frame: pd.DataFrame, label: str, code_col: str = "cmd_code") -> None:
    count = excluded_hs6_count(frame, code_col=code_col)
    if count:
        raise RuntimeError(f"{label} contains {count:,} excluded HS6 999999 rows in {code_col}.")


def require_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Required H2.4 source artifact is missing: {path}")


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    for path in [PRODUCT_SUPPLIER_PATH, DOMINANT_PATH, RCA_PATH]:
        require_file(path)
    product = pd.read_parquet(PRODUCT_SUPPLIER_PATH)
    dominant = pd.read_parquet(DOMINANT_PATH)
    rca = pd.read_parquet(RCA_PATH)
    for label, frame in {
        "product_supplier_concentration": product,
        "dominant_specialized_suppliers": dominant,
        "exporter_product_rca": rca,
    }.items():
        frame["cmd_code"] = normalize_cmd(frame["cmd_code"])
        assert_no_excluded_hs6(frame, label)
    if "strict_dominant_specialized" not in dominant.columns:
        dominant["strict_dominant_specialized"] = (
            dominant["dominant_specialized"].fillna(False).astype(bool)
            & pd.to_numeric(dominant["top_supplier_share"], errors="coerce").ge(0.75)
        )
    return product, dominant, rca


def weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    mask = values.notna() & weights.notna() & weights.gt(0)
    if not mask.any():
        return np.nan
    return float(np.average(values[mask], weights=weights[mask]))


def import_value_share(frame: pd.DataFrame, mask: pd.Series) -> float:
    total = float(pd.to_numeric(frame["total_product_imports"], errors="coerce").sum())
    if total <= 0:
        return np.nan
    return float(pd.to_numeric(frame.loc[mask, "total_product_imports"], errors="coerce").sum() / total)


def build_yearly_summary(dominant: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, float | int]] = []
    for year, group in dominant.groupby("year", sort=True):
        top_share = pd.to_numeric(group["top_supplier_share"], errors="coerce")
        hhi = pd.to_numeric(group["supplier_hhi"], errors="coerce")
        imports = pd.to_numeric(group["total_product_imports"], errors="coerce")
        effective = pd.to_numeric(group["effective_supplier_count"], errors="coerce")
        has_rca = group["has_top_supplier_rca"].fillna(False).astype(bool)
        dominant_flag = group["dominant_specialized"].fillna(False).astype(bool)
        strict_flag = group["strict_dominant_specialized"].fillna(False).astype(bool)
        rows.append(
            {
                "year": int(year),
                "product_years": int(len(group)),
                "total_product_imports": float(imports.sum()),
                "mean_top_supplier_share": float(top_share.mean()),
                "median_top_supplier_share": float(top_share.median()),
                "weighted_mean_top_supplier_share": weighted_mean(top_share, imports),
                "mean_supplier_hhi": float(hhi.mean()),
                "weighted_mean_supplier_hhi": weighted_mean(hhi, imports),
                "median_effective_supplier_count": float(effective.median()),
                "share_products_top_supplier_ge_50": float(top_share.ge(0.50).mean()),
                "share_products_top_supplier_ge_75": float(top_share.ge(0.75).mean()),
                "import_value_share_top_supplier_ge_50": import_value_share(group, top_share.ge(0.50)),
                "import_value_share_top_supplier_ge_75": import_value_share(group, top_share.ge(0.75)),
                "rca_coverage_share_products": float(has_rca.mean()),
                "rca_coverage_share_import_value": import_value_share(group, has_rca),
                "share_products_dominant_specialized": float(dominant_flag.mean()),
                "import_value_share_dominant_specialized": import_value_share(group, dominant_flag),
                "share_products_strict_dominant_specialized": float(strict_flag.mean()),
                "import_value_share_strict_dominant_specialized": import_value_share(group, strict_flag),
            }
        )
    return pd.DataFrame(rows)


def latest_strict_tables(dominant: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    latest_year = int(dominant["year"].max())
    latest = dominant[dominant["year"].eq(latest_year)].copy()
    strict = latest[latest["strict_dominant_specialized"].fillna(False).astype(bool)].copy()
    keep = [
        "year",
        "cmd_code",
        "product_description",
        "total_product_imports",
        "top_supplier_code",
        "top_supplier_iso3",
        "top_supplier_name",
        "top_supplier_share",
        "supplier_hhi",
        "effective_supplier_count",
        "supplier_count",
        "importer_count",
        "top_supplier_rca",
        "dominant_specialized",
        "strict_dominant_specialized",
    ]
    strict = strict[[col for col in keep if col in strict.columns]]
    dominated_products = strict.sort_values("total_product_imports", ascending=False).head(100).reset_index(drop=True)
    dominant_suppliers = (
        strict.sort_values(["top_supplier_name", "total_product_imports"], ascending=[True, False])
        .groupby("top_supplier_code", as_index=False)
        .head(5)
        .sort_values("total_product_imports", ascending=False)
        .head(100)
        .reset_index(drop=True)
    )
    return dominated_products, dominant_suppliers


def read_or_create_comparison() -> pd.DataFrame:
    if COMPARISON_PATH.exists():
        comparison = pd.read_csv(COMPARISON_PATH)
    else:
        comparison = pd.DataFrame(
            columns=[
                "year",
                "importer_country_median_top_supplier_share",
                "importer_country_share_products_top_supplier_ge_75",
                "importer_country_import_value_share_top_supplier_ge_75",
                "importer_country_count",
                "world_product_market_median_top_supplier_share",
                "world_product_market_share_products_top_supplier_ge_75",
                "world_product_market_import_value_share_top_supplier_ge_75",
                "world_product_market_product_years",
            ]
        )
    comparison.to_csv(COMPARISON_PATH, index=False)
    return comparison


def savefig(path: Path) -> None:
    plt.tight_layout()
    plt.savefig(path, dpi=220, bbox_inches="tight")
    plt.close()


def write_figures(yearly: pd.DataFrame, dominant: pd.DataFrame, comparison: pd.DataFrame) -> None:
    sns.set_theme(style="whitegrid", context="paper", font_scale=1.05)
    plt.figure(figsize=(9, 5))
    sns.lineplot(data=yearly, x="year", y="median_top_supplier_share", marker="o", label="Median top-supplier share")
    sns.lineplot(data=yearly, x="year", y="weighted_mean_supplier_hhi", marker="o", label="Import-weighted supplier HHI")
    plt.ylabel("Share / HHI")
    plt.xlabel("Year")
    plt.title("Global H24 Supplier Concentration")
    plt.legend(frameon=False)
    savefig(FIGURE_DIR / "supplier_concentration_trend.png")

    plt.figure(figsize=(9, 5))
    sns.lineplot(data=yearly, x="year", y="share_products_dominant_specialized", marker="o", label="RCA-specialized top supplier")
    sns.lineplot(
        data=yearly,
        x="year",
        y="share_products_strict_dominant_specialized",
        marker="o",
        label="RCA-specialized and >=75% share",
    )
    plt.ylabel("Share of HS6 product markets")
    plt.xlabel("Year")
    plt.title("Dominant Specialized Supplier Definitions")
    plt.legend(frameon=False)
    savefig(FIGURE_DIR / "dominant_specialized_import_value_share_trend.png")

    latest = dominant[dominant["year"].eq(dominant["year"].max())].copy()
    plt.figure(figsize=(9, 5))
    sns.histplot(latest["top_supplier_share"], bins=30, color="#2f5d62")
    plt.axvline(0.75, color="#8c4f2b", linewidth=1.5)
    plt.xlabel("Top-supplier share of global HS6 imports")
    plt.ylabel("HS6 product markets")
    plt.title(f"Latest-Year Global Top-Supplier Shares ({int(latest['year'].max())})")
    savefig(FIGURE_DIR / "latest_year_top_supplier_share_distribution.png")

    scatter = latest.dropna(subset=["top_supplier_share", "top_supplier_rca"]).copy()
    plt.figure(figsize=(9, 6))
    sns.scatterplot(
        data=scatter,
        x="top_supplier_share",
        y="top_supplier_rca",
        hue="strict_dominant_specialized",
        alpha=0.55,
        edgecolor="none",
    )
    plt.axvline(0.75, color="#8c4f2b", linewidth=1.2)
    plt.axhline(1.0, color="#6b7280", linewidth=1.2)
    plt.yscale("log")
    plt.xlabel("Top-supplier share of global HS6 imports")
    plt.ylabel("Top supplier RCA, log scale")
    plt.title("Top-Supplier Share Versus Export Specialization")
    plt.legend(frameon=False, title="Strict dominant")
    savefig(FIGURE_DIR / "latest_year_top_supplier_share_vs_rca.png")

    comp = comparison.copy()
    for col in comparison.columns:
        comp[col] = pd.to_numeric(comp[col], errors="coerce")
    plt.figure(figsize=(9, 5))
    if not comp.empty and "world_product_market_median_top_supplier_share" in comp.columns:
        sns.lineplot(
            data=comp,
            x="year",
            y="importer_country_median_top_supplier_share",
            marker="o",
            label="Importer-country median",
        )
        sns.lineplot(
            data=comp,
            x="year",
            y="world_product_market_median_top_supplier_share",
            marker="o",
            label="World product-market median",
        )
    plt.ylabel("Median top-supplier share")
    plt.xlabel("Year")
    plt.title("Importer-Country Versus Global Supplier Dominance")
    plt.legend(frameon=False)
    savefig(FIGURE_DIR / "importer_country_vs_world_supplier_dominance.png")


def write_memo(yearly: pd.DataFrame, dominated_products: pd.DataFrame, dominant_suppliers: pd.DataFrame) -> None:
    latest_year = int(yearly["year"].max())
    latest = yearly[yearly["year"].eq(latest_year)].iloc[0]
    lines = [
        "# H2.4 Supplier Specialization Benchmark",
        "",
        f"Generated: {now_utc()}",
        "",
        "Scope: this is a global H24 world-product-market benchmark. It is not limited to the rd2_countries website sample.",
        "",
        "HS6 `999999` is excluded before tables, figures, and manifests are written.",
        "",
        "## Measures",
        "",
        "`top_supplier_share` is the largest country-coded supplier's share of global imports for an HS6 product-year.",
        "",
        "`dominant_specialized` means the top supplier has revealed comparative advantage above 1 for that HS6 product. This is an RCA-specialization flag and does not require a 75% top-supplier share.",
        "",
        "`strict_dominant_specialized` means `dominant_specialized` is true and the top supplier share is at least 75%. Higher values indicate a product market where one specialized source country dominates global observed imports.",
        "",
        "## Latest-Year Summary",
        "",
        f"- Latest year: {latest_year}",
        f"- Product markets: {int(latest['product_years']):,}",
        f"- Median top-supplier share: {latest['median_top_supplier_share']:.3f}",
        f"- Share of products with top supplier >= 75%: {latest['share_products_top_supplier_ge_75']:.3f}",
        f"- Import-value share with top supplier >= 75%: {latest['import_value_share_top_supplier_ge_75']:.3f}",
        f"- Share strict dominant specialized: {latest['share_products_strict_dominant_specialized']:.3f}",
        f"- Import-value share strict dominant specialized: {latest['import_value_share_strict_dominant_specialized']:.3f}",
        "",
        "## Output Files",
        "",
        f"- `{rel(TABLE_DIR / 'yearly_concentration_summary.csv')}`",
        f"- `{rel(TABLE_DIR / 'latest_year_top_dominated_products.csv')}`",
        f"- `{rel(TABLE_DIR / 'latest_year_top_dominant_specialized_suppliers.csv')}`",
        f"- `{rel(TABLE_DIR / 'importer_vs_world_supplier_dominance_comparison.csv')}`",
        f"- `{rel(FIGURE_DIR)}/`",
        "",
        "The two latest-year top tables are restricted to `strict_dominant_specialized == True`; the broader RCA-only flag remains in the processed parquet and yearly summary.",
        "",
        f"Rows in latest strict product table: {len(dominated_products):,}",
        f"Rows in latest strict supplier table: {len(dominant_suppliers):,}",
    ]
    MEMO_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_manifest(
    product: pd.DataFrame,
    dominant: pd.DataFrame,
    rca: pd.DataFrame,
    yearly: pd.DataFrame,
    dominated_products: pd.DataFrame,
    dominant_suppliers: pd.DataFrame,
    comparison: pd.DataFrame,
) -> None:
    manifest = {
        "created_at_utc": now_utc(),
        "command": " ".join([Path(sys.executable).name, *sys.argv]),
        "mode": "h24_supplier_specialization_finalize_only",
        "scope": "global H24 world-product-market benchmark, not rd2-country-sample limited",
        "excluded_hs6_codes": sorted(EXCLUDED_HS6_CODES),
        "hs6_999999_rows": {
            "product_supplier_concentration": excluded_hs6_count(product),
            "dominant_specialized_suppliers": excluded_hs6_count(dominant),
            "exporter_product_rca": excluded_hs6_count(rca),
            "latest_year_top_dominated_products": excluded_hs6_count(dominated_products),
            "latest_year_top_dominant_specialized_suppliers": excluded_hs6_count(dominant_suppliers),
        },
        "row_counts": {
            "product_supplier_concentration": int(len(product)),
            "dominant_specialized_suppliers": int(len(dominant)),
            "exporter_product_rca": int(len(rca)),
            "yearly_summary": int(len(yearly)),
            "latest_year_top_dominated_products": int(len(dominated_products)),
            "latest_year_top_dominant_specialized_suppliers": int(len(dominant_suppliers)),
            "comparison": int(len(comparison)),
        },
        "source_artifacts": {
            "product_supplier_concentration": source_file_manifest(PRODUCT_SUPPLIER_PATH),
            "dominant_specialized_suppliers": source_file_manifest(DOMINANT_PATH),
            "exporter_product_rca": source_file_manifest(RCA_PATH),
        },
        "outputs": {
            "yearly_summary": rel(TABLE_DIR / "yearly_concentration_summary.csv"),
            "latest_year_top_dominated_products": rel(TABLE_DIR / "latest_year_top_dominated_products.csv"),
            "latest_year_top_dominant_specialized_suppliers": rel(
                TABLE_DIR / "latest_year_top_dominant_specialized_suppliers.csv"
            ),
            "comparison": rel(COMPARISON_PATH),
            "figures": rel(FIGURE_DIR),
            "memo": rel(MEMO_PATH),
        },
        "exercises_md_updated": False,
    }
    if any(int(value) != 0 for value in manifest["hs6_999999_rows"].values()):
        raise RuntimeError(f"H2.4 manifest found excluded HS6 rows: {manifest['hs6_999999_rows']}")
    text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    RESULTS_MANIFEST.write_text(text, encoding="utf-8")
    PROCESSED_MANIFEST.write_text(text, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--finalize-only",
        action="store_true",
        help="Validate existing processed H2.4 panels and regenerate derived tables, figures, memo, and manifests.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.finalize_only:
        raise SystemExit("This runner currently supports --finalize-only from existing processed H2.4 panels.")
    ensure_dirs()
    product, dominant, rca = load_inputs()
    yearly = build_yearly_summary(dominant)
    dominated_products, dominant_suppliers = latest_strict_tables(dominant)
    comparison = read_or_create_comparison()
    yearly.to_csv(TABLE_DIR / "yearly_concentration_summary.csv", index=False)
    dominated_products.to_csv(TABLE_DIR / "latest_year_top_dominated_products.csv", index=False)
    dominant_suppliers.to_csv(TABLE_DIR / "latest_year_top_dominant_specialized_suppliers.csv", index=False)
    write_figures(yearly, dominant, comparison)
    write_memo(yearly, dominated_products, dominant_suppliers)
    write_manifest(product, dominant, rca, yearly, dominated_products, dominant_suppliers, comparison)
    print(f"wrote {rel(TABLE_DIR)}")
    print(f"wrote {rel(FIGURE_DIR)}")
    print(f"wrote {rel(MEMO_PATH)}")
    print(f"wrote {rel(RESULTS_MANIFEST)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
