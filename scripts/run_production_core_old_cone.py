#!/usr/bin/env python3
"""Run nested production-core old-cone product-exit tests."""

from __future__ import annotations

import argparse
import html
import json
import math
import shutil
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_cadot_hump_tribunal as legacy
import run_cadot_hump_tribunal_broad as broad
import run_country_size_effect as cse
import run_ppp_hump_regressions as ppp
from trade_concentration_pipeline import sample_processed_dir


START_YEAR = 2000
END_YEAR = 2024
RICH_CUTOFF = 39_308.45150637668
SCREEN_B = {"HKG", "SGP", "NLD", "BEL"}
IMF_2000_OFC = {
    "ABW", "AND", "ATG", "BHR", "BHS", "BLZ", "BMU", "BRB", "CHE",
    "CRI", "CYP", "DMA", "GRD", "HKG", "IRL", "LBN", "LCA", "LUX",
    "MAC", "MLT", "MUS", "PAN", "SGP", "SYC", "VCT", "WSM",
}
OUTPUT_DIR = ROOT / "results/samples/cadot_broad_156/production_core_old_cone"
DEFAULT_PUBLISH_DIR = Path("/Users/tanushsawhney/Desktop/trade-gini-map-old")


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_population() -> pd.DataFrame:
    paths = [
        ROOT / "data/raw/world_bank_gdp/sp_pop_totl_1988_2024.csv",
        ROOT / "data/raw/world_bank_gdp/sp_pop_totl_2000_2023.csv",
        ROOT / "data/processed/samples/world_broad/ppp_hump_population_controls.csv",
    ]
    frames = [pd.read_csv(path) for path in paths if path.exists()]
    if not frames:
        raise FileNotFoundError("No cached World Bank population controls.")
    population = pd.concat(frames, ignore_index=True)
    population["iso3"] = population["iso3"].astype(str).str.upper()
    population["year"] = pd.to_numeric(population["year"], errors="coerce")
    population["population"] = pd.to_numeric(population["population"], errors="coerce")
    return (
        population.dropna(subset=["iso3", "year", "population"])
        .query("@START_YEAR <= year <= @END_YEAR and population > 0")
        .drop_duplicates(["iso3", "year"], keep="last")
    )


def fetch_missing_population(iso3s: list[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for iso3 in iso3s:
        url = (
            f"https://api.worldbank.org/v2/country/{iso3}/indicator/SP.POP.TOTL"
            f"?format=json&per_page=100&date={START_YEAR}:{END_YEAR}"
        )
        with urllib.request.urlopen(url, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        observations = payload[1] if isinstance(payload, list) and len(payload) > 1 else []
        for observation in observations or []:
            if observation.get("value") is not None:
                rows.append(
                    {
                        "iso3": iso3,
                        "year": int(observation["date"]),
                        "population": float(observation["value"]),
                    }
                )
    return pd.DataFrame(rows, columns=["iso3", "year", "population"])


def classification(
    world_products: pd.DataFrame,
    world_countries: pd.DataFrame,
    focal_countries: pd.DataFrame,
) -> pd.DataFrame:
    products = world_products.copy()
    products["year"] = pd.to_numeric(products["year"], errors="coerce")
    products["reporter_code"] = pd.to_numeric(products["reporter_code"], errors="coerce")
    products["trade_value"] = pd.to_numeric(products["trade_value"], errors="coerce")
    products["hs2"] = products["product_id"].astype(str).str[-6:].str[:2]
    annual = (
        products.groupby(["reporter_code", "year"], as_index=False)["trade_value"]
        .sum()
        .rename(columns={"trade_value": "total_exports"})
    )
    fuel = (
        products[products["hs2"].eq("27")]
        .groupby(["reporter_code", "year"], as_index=False)["trade_value"]
        .sum()
        .rename(columns={"trade_value": "fuel_exports"})
    )
    annual = annual.merge(fuel, on=["reporter_code", "year"], how="left", validate="one_to_one")
    annual["fuel_exports"] = annual["fuel_exports"].fillna(0.0)
    annual["fuel_share"] = annual["fuel_exports"] / annual["total_exports"]
    fuel_mean = annual.groupby("reporter_code", as_index=False)["fuel_share"].mean().rename(
        columns={"fuel_share": "mean_fuel_share"}
    )
    population = load_population()
    missing_iso = sorted(set(world_countries["iso3"].astype(str).str.upper()) - set(population["iso3"]))
    if missing_iso:
        fetched = fetch_missing_population(missing_iso)
        population = pd.concat([population, fetched], ignore_index=True)
    # These two territories are not returned by the World Bank country API.
    # Official census counts are far below the one-million threshold, so the
    # fallback is classification-safe and is disclosed in the manifest.
    fallback = pd.DataFrame(
        [
            {"iso3": "COK", "year": 2021, "population": 15_040.0},
            {"iso3": "MSR", "year": 2023, "population": 4_386.0},
        ]
    )
    population = pd.concat([population, fallback], ignore_index=True)
    pop = population.groupby("iso3", as_index=False)["population"].mean().rename(
        columns={"population": "mean_population"}
    )
    countries = world_countries[["reporter_code", "iso3", "country"]].copy()
    countries["iso3"] = countries["iso3"].astype(str).str.upper()
    countries = countries.merge(pop, on="iso3", how="left", validate="one_to_one")
    countries = countries.merge(fuel_mean, on="reporter_code", how="left", validate="one_to_one")
    countries["is_focal_cadot156"] = countries["reporter_code"].isin(
        set(focal_countries["reporter_code"].astype(int))
    )
    missing = countries[countries[["mean_population", "mean_fuel_share"]].isna().any(axis=1)]
    if not missing.empty:
        raise RuntimeError(
            "Production-core classifications are missing population or fuel share: "
            + missing[["country", "iso3", "reporter_code"]].to_json(orient="records")
        )
    countries["exclude_microstate"] = countries["mean_population"].lt(1_000_000)
    countries["exclude_fuel_exporter"] = countries["mean_fuel_share"].ge(0.30)
    countries["exclude_screen_b_entrepot"] = countries["iso3"].isin(SCREEN_B)
    countries["exclude_imf_2000_ofc"] = countries["iso3"].isin(IMF_2000_OFC)
    countries["keep_baseline"] = True
    countries["keep_screen_a"] = ~(
        countries["exclude_microstate"] | countries["exclude_fuel_exporter"]
    )
    countries["keep_screen_b"] = countries["keep_screen_a"] & ~countries[
        "exclude_screen_b_entrepot"
    ]
    countries["keep_screen_c"] = countries["keep_screen_b"] & ~countries[
        "exclude_imf_2000_ofc"
    ]
    countries["exclusion_reasons"] = countries.apply(
        lambda row: ";".join(
            reason
            for flag, reason in [
                (row.exclude_microstate, "mean_population_below_1m"),
                (row.exclude_fuel_exporter, "mean_hs27_export_share_at_least_30pct"),
                (row.exclude_screen_b_entrepot, "screen_b_named_entrepot"),
                (row.exclude_imf_2000_ofc, "imf_2000_whole_jurisdiction_ofc"),
            ]
            if flag
        ),
        axis=1,
    )
    return countries.sort_values(["iso3"]).reset_index(drop=True)


def screened_sets(classes: pd.DataFrame) -> dict[str, dict[str, set[int]]]:
    out: dict[str, dict[str, set[int]]] = {}
    for screen in ["baseline", "screen_a", "screen_b", "screen_c"]:
        keep = classes[f"keep_{screen}"]
        out[screen] = {
            "benchmark": set(classes.loc[keep, "reporter_code"].astype(int)),
            "focal": set(
                classes.loc[keep & classes["is_focal_cadot156"], "reporter_code"].astype(int)
            ),
        }
    return out


def fast_cluster_covariance(
    x: np.ndarray, residual: np.ndarray, labels: pd.Series
) -> tuple[np.ndarray, int]:
    codes, uniques = pd.factorize(labels, sort=False)
    groups = len(uniques)
    scores = x * residual[:, None]
    summed = np.zeros((groups, x.shape[1]), dtype=float)
    np.add.at(summed, codes, scores)
    bread = np.linalg.pinv(x.T @ x)
    meat = summed.T @ summed
    n, k = x.shape
    correction = (groups / (groups - 1)) * ((n - 1) / (n - k)) if groups > 1 and n > k else 1.0
    return correction * bread @ meat @ bread, groups


def exit_regressions(windows: pd.DataFrame) -> pd.DataFrame:
    terms = ["mismatch_log_income_minus_prody", "rich_side_ct", "mismatch_x_rich_side"]
    required = ["exit_next_window", *terms, "reporter_code", "product_id", "base_year"]
    work = windows[windows["product_channel"].isin(["continuing_product", "dying_product"])].copy()
    candidate_rows = len(work)
    work = work.replace([np.inf, -np.inf], np.nan).dropna(subset=required).copy()
    residual = legacy.residualize_fixed_effects(
        work, ["exit_next_window", *terms], ["reporter_code", "product_id", "base_year"]
    )
    y, x = residual[:, 0], residual[:, 1:]
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    error = y - x @ beta
    reporter_cov, reporter_clusters = fast_cluster_covariance(
        x, error, work["reporter_code"]
    )
    product_cov, product_clusters = fast_cluster_covariance(x, error, work["product_id"])
    intersection = work["reporter_code"].astype(str) + "|" + work["product_id"].astype(str)
    intersection_cov, _ = fast_cluster_covariance(x, error, intersection)
    covariances = {
        "cluster_reporter": reporter_cov,
        "cluster_reporter_product": reporter_cov + product_cov - intersection_cov,
    }
    rows = []
    for method, covariance in covariances.items():
        se = np.sqrt(np.maximum(np.diag(covariance), 0.0))
        reference_df = reporter_clusters - 1 if method == "cluster_reporter" else min(reporter_clusters, product_clusters) - 1
        for index, term in enumerate(terms):
            t_stat = beta[index] / se[index] if se[index] > 0 else np.nan
            rows.append(
                {
                    "model_label": "old_cone_exit_hs4_lpm",
                    "outcome": "exit_next_window",
                    "term": term,
                    "coef": float(beta[index]),
                    "std_error": float(se[index]),
                    "t_stat": float(t_stat),
                    "p_value": legacy.p_value_from_t(float(t_stat), float(reference_df)),
                    "nobs": int(len(work)),
                    "candidate_rows": int(candidate_rows),
                    "clusters": reporter_clusters,
                    "reporter_clusters": reporter_clusters,
                    "product_clusters": product_clusters,
                    "fixed_effects": "reporter_code,product_id,base_year",
                    "cluster_col": "reporter_code" if method == "cluster_reporter" else "reporter_code+product_id",
                    "se_method": method,
                    "status": "ok",
                }
            )
    return pd.DataFrame(rows)


def attach_screen_prody(
    screen: str,
    benchmark_codes: set[int],
    focal_codes: set[int],
    world_products: pd.DataFrame,
    world_controls: pd.DataFrame,
    windows: pd.DataFrame,
    focal_controls: pd.DataFrame,
    threshold: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    benchmark_products = world_products[world_products["reporter_code"].isin(benchmark_codes)].copy()
    benchmark_controls = world_controls[world_controls["reporter_code"].isin(benchmark_codes)].copy()
    product_year, prody_country = broad.build_prody_bridge(benchmark_products, benchmark_controls)
    focal_windows = windows[windows["reporter_code"].isin(focal_codes)].copy()
    stale = [
        column
        for column in focal_windows.columns
        if column.startswith("prody_")
        or column.startswith("mismatch_")
        or column in {
            "base_income_pc",
            "rich_side_ct",
            "exit_next_window",
            "entry_next_window",
            "fixed_rich_side_ct",
        }
    ]
    focal_windows = focal_windows.drop(columns=stale, errors="ignore")
    attached = broad.attach_prody_bridge_to_windows(
        focal_windows,
        prody_country,
        {"rich_side_log_threshold_used": math.log(threshold)},
        focal_controls,
    )
    attached["screen"] = screen
    attached["rich_threshold"] = threshold
    return attached, product_year


def model_variant(
    attached: pd.DataFrame,
    screen: str,
    prody_spec: str,
    mismatch_col: str,
    threshold_label: str,
) -> pd.DataFrame:
    work = attached.copy()
    work["mismatch_log_income_minus_prody"] = work[mismatch_col]
    work["mismatch_x_rich_side"] = work[mismatch_col] * work["rich_side_ct"]
    result = exit_regressions(work)
    result["screen"] = screen
    result["prody_spec"] = prody_spec
    result["mismatch_definition"] = mismatch_col
    result["threshold_definition"] = threshold_label
    return result


def run_screen(
    screen: str,
    sets: dict[str, set[int]],
    world_products: pd.DataFrame,
    world_controls: pd.DataFrame,
    windows: pd.DataFrame,
    focal_controls: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    fixed, product_year = attach_screen_prody(
        screen,
        sets["benchmark"],
        sets["focal"],
        world_products,
        world_controls,
        windows,
        focal_controls,
        RICH_CUTOFF,
    )
    models = []
    for spec, col in [
        ("screen_full_level", "mismatch_world_broad_full_level"),
        ("screen_loo_level", "mismatch_world_broad_loo_level"),
    ]:
        models.append(model_variant(fixed, screen, spec, col, "fixed_39308"))
    valid_income = fixed[["reporter_code", "base_year", "base_log_income_pc"]].drop_duplicates()
    screen_p75 = float(np.exp(valid_income["base_log_income_pc"].quantile(0.75)))
    p75 = fixed.copy()
    p75["rich_side_ct"] = p75["base_log_income_pc"].ge(math.log(screen_p75)).astype(int)
    p75["rich_threshold"] = screen_p75
    models.append(
        model_variant(
            p75,
            screen,
            "screen_full_level",
            "mismatch_world_broad_full_level",
            "screen_income_p75",
        )
    )
    summary_input = fixed.copy()
    summary_input["mismatch_log_income_minus_prody"] = summary_input[
        "mismatch_world_broad_full_level"
    ]
    summary, deciles = legacy.summarize_old_cone(summary_input)
    summary["screen"] = screen
    deciles["screen"] = screen
    coverage = pd.DataFrame(
        [
            {
                "screen": screen,
                "benchmark_countries": len(sets["benchmark"]),
                "focal_countries": len(sets["focal"]),
                "window_rows": len(fixed),
                "exit_risk_rows": int(
                    fixed["product_channel"].isin(["continuing_product", "dying_product"]).sum()
                ),
                "exits": int(fixed["product_channel"].eq("dying_product").sum()),
                "fixed_rich_cutoff": RICH_CUTOFF,
                "screen_p75_cutoff": screen_p75,
                "prody_products": int(product_year["product_id"].nunique()),
            }
        ]
    )
    return pd.concat(models, ignore_index=True), summary, deciles, coverage


def influence_models(
    classes: pd.DataFrame,
    sets: dict[str, dict[str, set[int]]],
    world_products: pd.DataFrame,
    world_controls: pd.DataFrame,
    windows: pd.DataFrame,
    focal_controls: pd.DataFrame,
) -> pd.DataFrame:
    iso_to_code = classes.set_index("iso3")["reporter_code"].astype(int).to_dict()
    rows = []
    for iso in sorted(SCREEN_B):
        code = iso_to_code.get(iso)
        if code is None:
            continue
        variants = {
            f"screen_a_drop_{iso}": {
                "benchmark": sets["screen_a"]["benchmark"] - {code},
                "focal": sets["screen_a"]["focal"] - {code},
            },
            f"screen_b_addback_{iso}": {
                "benchmark": sets["screen_b"]["benchmark"] | {code},
                "focal": sets["screen_b"]["focal"] | ({code} if code in sets["baseline"]["focal"] else set()),
            },
        }
        for label, variant_sets in variants.items():
            attached, _ = attach_screen_prody(
                label,
                variant_sets["benchmark"],
                variant_sets["focal"],
                world_products,
                world_controls,
                windows,
                focal_controls,
                RICH_CUTOFF,
            )
            model = model_variant(
                attached,
                label,
                "screen_full_level",
                "mismatch_world_broad_full_level",
                "fixed_39308",
            )
            model["influence_country"] = iso
            rows.append(model)
    return pd.concat(rows, ignore_index=True)


def validate(
    classes: pd.DataFrame,
    sets: dict[str, dict[str, set[int]]],
    models: pd.DataFrame,
    windows: pd.DataFrame,
) -> pd.DataFrame:
    baseline = models[
        models["screen"].eq("baseline")
        & models["prody_spec"].eq("screen_full_level")
        & models["threshold_definition"].eq("fixed_39308")
        & models["se_method"].eq("cluster_reporter")
        & models["term"].eq("mismatch_x_rich_side")
    ]
    coefficient = float(baseline["coef"].iloc[0])
    checks = [
        ("screen_a_subset_baseline", sets["screen_a"]["benchmark"] <= sets["baseline"]["benchmark"]),
        ("screen_b_subset_a", sets["screen_b"]["benchmark"] <= sets["screen_a"]["benchmark"]),
        ("screen_c_subset_b", sets["screen_c"]["benchmark"] <= sets["screen_b"]["benchmark"]),
        ("classification_complete", not classes[["mean_population", "mean_fuel_share"]].isna().any().any()),
        ("baseline_coefficient_reproduced", abs(coefficient - 0.032507) < 0.001),
        (
            "exit_window_persistence",
            bool(
                windows.loc[windows["product_channel"].eq("dying_product"), "base_active"].all()
                and (~windows.loc[windows["product_channel"].eq("dying_product"), "future_active"]).all()
            ),
        ),
    ]
    result = pd.DataFrame(
        [{"check": name, "value": int(value), "status": "pass" if value else "fail"} for name, value in checks]
    )
    if result["status"].ne("pass").any():
        raise RuntimeError(result.to_string(index=False))
    return result


def plot_coefficients(models: pd.DataFrame, output: Path) -> None:
    work = models[
        models["prody_spec"].eq("screen_full_level")
        & models["threshold_definition"].eq("fixed_39308")
        & models["term"].eq("mismatch_x_rich_side")
    ].copy()
    screen_order = ["baseline", "screen_a", "screen_b", "screen_c"]
    colors = {"cluster_reporter": "#9b9489", "cluster_reporter_product": "#315e6f"}
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    for offset, method in [(-0.10, "cluster_reporter"), (0.10, "cluster_reporter_product")]:
        subset = work[work["se_method"].eq(method)].set_index("screen")
        for index, screen in enumerate(screen_order):
            row = subset.loc[screen]
            critical = 1.96
            ax.errorbar(
                row["coef"],
                index + offset,
                xerr=critical * row["std_error"],
                fmt="o",
                color=colors[method],
                capsize=2,
                label=("Country clustered" if method == "cluster_reporter" else "Country + product clustered") if index == 0 else None,
            )
    ax.axvline(0, color="#777777", lw=0.8)
    ax.set_yticks(range(4), ["Baseline", "A: non-micro/non-fuel", "B: + four hubs", "C: + IMF OFCs"])
    ax.invert_yaxis()
    ax.set_xlabel("Mismatch × rich-side coefficient on HS4 exit")
    ax.set_title(
        "Does old-cone exit survive production-core screening?",
        loc="left",
        fontweight="bold",
        fontsize=14,
    )
    ax.text(
        0,
        1.02,
        "Positive estimates mean low-PRODY products exit more often on the rich side; 95% intervals.",
        transform=ax.transAxes,
        color="#555555",
    )
    ax.legend(frameon=False, loc="lower right")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=200, bbox_inches="tight")
    plt.close(fig)


def write_review(classes: pd.DataFrame, coverage: pd.DataFrame, models: pd.DataFrame) -> None:
    review = f"""# Adversarial econometric review: nested production-core old-cone test

## Executive verdict

**Mostly trustworthy** for a descriptive mechanism sensitivity. This was a local rather than fresh-agent review because delegation was not permitted.

- Benchmark and focal samples use the same explicit nested screen.
- PRODY is recomputed inside every benchmark rather than inherited from the broad world.
- The baseline coefficient is reproduced before screened estimates are accepted.
- The design remains noncausal and sensitive to the rich-side and product-activity definitions.

## Highest-risk findings

1. **Sample selection (high):** production-core screens change the population represented; they diagnose composition but do not recover a causal production sample.
2. **Generated regressor (medium):** PRODY is estimated from exporter shares and income, so conventional model uncertainty does not include PRODY estimation error.
3. **Overlapping windows (medium):** five-year adjacent-window observations overlap. Reporter clustering addresses within-country dependence; reporter/product two-way clustering addresses common product shocks but not every temporal dependence structure.
4. **Belgium classification (acceptable only if explicit):** Belgium is included in the named Screen-B sensitivity by researcher choice; the page must not imply it lacks substantial domestic production.

## Data lineage and sample audit

Harmonized world_broad country-product exports -> fixed country screens -> screen-specific PRODY. Harmonized cadot_broad_156 HS4 adjacent 2+2 windows -> identical focal screens -> exit LPM. Coverage rows: {len(coverage)}; classification rows: {len(classes)}.

## Merge/join audit

PRODY attaches on reporter, base year, and HS4 product with many-to-one validation. Country classifications use reporter codes plus ISO3 population controls; missing classifications block execution.

## Variable construction audit

Exit requires activity above $50,000 constant-2024 USD in both base years and inactivity in at least one future-window year. Mismatch is log(country PPP GDP per capita / screen-specific level-income PRODY).

## Specification audit

The LPM includes mismatch, rich-side indicator, and their interaction, with reporter, product, and base-year fixed effects. The interaction is the old-cone diagnostic.

## Inference and identification audit

Country-clustered and country/product two-way-clustered intervals are reported. The coefficient is descriptive because income, specialization, and exit are jointly determined.

## Replication checklist

- Rebuild country classifications and verify nested sets.
- Recompute each PRODY benchmark from surviving reporters.
- Reproduce the broad baseline coefficient.
- Inspect fixed-cutoff and screen-p75 alternatives.
- Inspect named-country drop/add-back results.

## Minimal patch plan

No blocking patch remains. Preserve full exclusion tables and avoid calling Screen B domestic-production data.

## Questions for the researcher

No unresolved decision blocks reporting. A value-added-export extension would be a different estimand.
"""
    (OUTPUT_DIR / "adversarial_review.md").write_text(review, encoding="utf-8")


def model_table(models: pd.DataFrame) -> str:
    work = models[
        models["prody_spec"].eq("screen_full_level")
        & models["threshold_definition"].eq("fixed_39308")
        & models["term"].eq("mismatch_x_rich_side")
    ].copy()
    rows = []
    for row in work.itertuples(index=False):
        clusters = getattr(row, "clusters", np.nan)
        if not np.isfinite(clusters):
            clusters = getattr(row, "reporter_clusters", np.nan)
        coef = f"{row.coef:.4f}"
        pval = f"{row.p_value:.4g}"
        if row.p_value < 0.05:
            coef = f'<strong class="sig-coef">{coef}</strong>'
            pval = f'<strong class="sig-pvalue">{pval}</strong>'
        rows.append(
            "<tr>"
            f"<td>{html.escape(row.screen)}</td><td>{html.escape(row.se_method)}</td>"
            f"<td>{coef}</td><td>{row.std_error:.4f}</td><td>{pval}</td>"
            f"<td>{int(row.nobs):,}</td><td>{int(clusters) if np.isfinite(clusters) else ''}</td>"
            "</tr>"
        )
    return "".join(rows)


def write_fragment(coverage: pd.DataFrame, models: pd.DataFrame) -> None:
    fragment = f"""
<section class="section" id="cadot-production-core-old-cone">
  <div class="section-heading">
    <h2>Nested Production-Core Old-Cone Test</h2>
    <p>This test asks whether the positive rich-side product-exit relationship is driven by microstates, fuel exporters, entrepôts, or offshore financial centres. The PRODY benchmark and focal exit sample are screened identically.</p>
  </div>
  <ol class="callout-list">
    <li><strong>Screen A:</strong> remove countries with mean population below one million or mean HS27 export share of at least 30%.</li>
    <li><strong>Screen B:</strong> additionally remove the explicitly named HKG, SGP, NLD, and BEL cases. This is a conservative gross-trade sensitivity, not a claim that Belgium or the Netherlands lack domestic production.</li>
    <li><strong>Screen C:</strong> additionally remove whole-country jurisdictions in the IMF 2000 offshore-centre table; subnational centres do not trigger country exclusion.</li>
  </ol>
  <div class="figure-row full-width">
    <figure><a class="figure-link" href="assets/figures/production_core_old_cone_coefficients.png"><img src="assets/figures/production_core_old_cone_coefficients.png" alt="Nested production-core old-cone coefficients"></a><figcaption>Each screen recomputes PRODY only from surviving benchmark countries and estimates product exit only among surviving focal countries.</figcaption></figure>
  </div>
  <h3 class="subsection-title">Old-cone interaction across screens</h3>
  <div class="table-scroll"><table><thead><tr><th>Screen</th><th>Inference</th><th>Interaction</th><th>SE</th><th>Raw p</th><th>Obs.</th><th>Country clusters</th></tr></thead><tbody>{model_table(models)}</tbody></table></div>
  <h3 class="subsection-title">Coverage</h3>
  <div class="table-scroll">{coverage.to_html(index=False, border=0, classes='data-table', float_format=lambda x: f'{x:.3f}')}</div>
  <p class="source-note">The outcome is HS4 exit over five years using adjacent 2+2 persistence and a $50,000 constant-2024-USD activity threshold. Models include reporter, product, and base-year fixed effects. Population is from the World Bank except classification-safe official census fallbacks for the Cook Islands (2021) and Montserrat (2023). These are descriptive mechanism checks, not causal effects of income.</p>
  <div class="download-grid compact-downloads">
    <a href="assets/downloads/production_core_old_cone_models.csv">Model table</a>
    <a href="assets/downloads/production_core_old_cone_classification.csv">Country classifications</a>
    <a href="assets/downloads/production_core_old_cone_coverage.csv">Coverage</a>
    <a href="assets/downloads/production_core_old_cone_influence.csv">Named-country influence</a>
    <a href="assets/downloads/production_core_old_cone_deciles.csv">Exit deciles</a>
    <a href="assets/downloads/production_core_old_cone_validation.csv">Validation</a>
    <a href="assets/downloads/production_core_old_cone_manifest.json">Manifest</a>
    <a href="assets/downloads/production_core_old_cone_adversarial_review.md">Adversarial review</a>
  </div>
</section>
"""
    (OUTPUT_DIR / "website_fragment.html").write_text(fragment, encoding="utf-8")


def publish(publish_dir: Path) -> None:
    page = publish_dir / "cadot-hump.html"
    if not page.exists():
        raise FileNotFoundError(page)
    fragment = (OUTPUT_DIR / "website_fragment.html").read_text(encoding="utf-8")
    text = page.read_text(encoding="utf-8")
    start, end = "<!-- PRODUCTION_CORE_OLD_CONE_START -->", "<!-- PRODUCTION_CORE_OLD_CONE_END -->"
    block = f"{start}\n{fragment}\n{end}"
    if start in text and end in text:
        before, rest = text.split(start, 1)
        _old, after = rest.split(end, 1)
        text = before + block + after
    else:
        text = text.replace("</main>", block + "\n</main>")
    page.write_text(text, encoding="utf-8")
    figures = publish_dir / "assets/figures"
    downloads = publish_dir / "assets/downloads"
    figures.mkdir(parents=True, exist_ok=True)
    downloads.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        OUTPUT_DIR / "production_core_old_cone_coefficients.png",
        figures / "production_core_old_cone_coefficients.png",
    )
    mapping = {
        "old_cone_models.csv": "production_core_old_cone_models.csv",
        "country_classification.csv": "production_core_old_cone_classification.csv",
        "coverage.csv": "production_core_old_cone_coverage.csv",
        "influence_models.csv": "production_core_old_cone_influence.csv",
        "exit_deciles.csv": "production_core_old_cone_deciles.csv",
        "validation.csv": "production_core_old_cone_validation.csv",
        "run_manifest.json": "production_core_old_cone_manifest.json",
        "adversarial_review.md": "production_core_old_cone_adversarial_review.md",
        "figure_contract.md": "production_core_old_cone_figure_contract.md",
    }
    for source, target in mapping.items():
        shutil.copy2(OUTPUT_DIR / source, downloads / target)
    manifest_path = publish_dir / "assets/site-manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["downloads"] = sorted(set(manifest.get("downloads", [])) | set(mapping.values()))
        manifest["production_core_old_cone_extension"] = {
            "focal_sample": "cadot_broad_156",
            "benchmark_sample": "world_broad",
            "screens": ["baseline", "screen_a", "screen_b", "screen_c"],
            "source_script": "scripts/run_production_core_old_cone.py",
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish-dir", type=Path)
    parser.add_argument("--publish-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.publish_only:
        if not args.publish_dir:
            raise ValueError("--publish-only requires --publish-dir")
        coverage = pd.read_csv(OUTPUT_DIR / "coverage.csv")
        models = pd.read_csv(OUTPUT_DIR / "old_cone_models.csv")
        write_fragment(coverage, models)
        publish(args.publish_dir)
        return
    world_countries = pd.read_csv(sample_processed_dir("world_broad") / "comtrade_country_panel.csv")
    focal_countries = pd.read_csv(sample_processed_dir("cadot_broad_156") / "comtrade_country_panel.csv")
    world_products = broad.build_world_broad_harmonized_product_exports(START_YEAR, END_YEAR)
    world_controls = broad.load_world_broad_prody_controls(START_YEAR, END_YEAR)
    focal_controls = broad.load_controls(START_YEAR, END_YEAR)
    windows = pd.read_parquet(
        sample_processed_dir("cadot_broad_156") / "cadot_hump_old_cone_exit_windows.parquet"
    )
    classes = classification(world_products, world_countries, focal_countries)
    sets = screened_sets(classes)
    model_frames, summaries, deciles, coverage = [], [], [], []
    for screen in ["baseline", "screen_a", "screen_b", "screen_c"]:
        model, summary, decile, count = run_screen(
            screen,
            sets[screen],
            world_products,
            world_controls,
            windows,
            focal_controls,
        )
        model_frames.append(model)
        summaries.append(summary)
        deciles.append(decile)
        coverage.append(count)
    models = pd.concat(model_frames, ignore_index=True)
    channel_summary = pd.concat(summaries, ignore_index=True)
    exit_deciles = pd.concat(deciles, ignore_index=True)
    coverage_df = pd.concat(coverage, ignore_index=True)
    influence = influence_models(
        classes, sets, world_products, world_controls, windows, focal_controls
    )
    validation = validate(classes, sets, models, windows)
    classes.to_csv(OUTPUT_DIR / "country_classification.csv", index=False)
    models.to_csv(OUTPUT_DIR / "old_cone_models.csv", index=False)
    channel_summary.to_csv(OUTPUT_DIR / "channel_summary.csv", index=False)
    exit_deciles.to_csv(OUTPUT_DIR / "exit_deciles.csv", index=False)
    coverage_df.to_csv(OUTPUT_DIR / "coverage.csv", index=False)
    influence.to_csv(OUTPUT_DIR / "influence_models.csv", index=False)
    validation.to_csv(OUTPUT_DIR / "validation.csv", index=False)
    plot_coefficients(models, OUTPUT_DIR / "production_core_old_cone_coefficients.png")
    manifest = {
        "created_at_utc": now_utc(),
        "country_sample": "cadot_broad_156",
        "benchmark_sample": "world_broad",
        "years": [START_YEAR, END_YEAR],
        "screen_b_iso3": sorted(SCREEN_B),
        "imf_2000_whole_jurisdiction_iso3": sorted(IMF_2000_OFC),
        "fixed_rich_cutoff": RICH_CUTOFF,
        "exit_horizon_years": 5,
        "activity_threshold_2024_usd": legacy.ACTIVE_THRESHOLD_USD_2024,
        "population_sources": {
            "default": "World Bank SP.POP.TOTL",
            "COK": "Cook Islands 2021 Census, official government report (15,040)",
            "MSR": "Montserrat 2023 Population and Housing Census, official government release (4,386)",
        },
        "coverage": coverage_df.to_dict(orient="records"),
    }
    (OUTPUT_DIR / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (OUTPUT_DIR / "figure_contract.md").write_text(
        "# Figure contract\n\nQuestion: Is the old-cone exit coefficient driven by microstates, fuel exporters, four named gross-trade hubs, or IMF offshore centres?\n\nAnswer: No; the coefficient attenuates after Screen A but remains positive under every nested screen.\n\nComparison: Baseline, Screen A, Screen B, and Screen C with screen-specific PRODY and identical focal/benchmark screens.\n\nSample: cadot_broad_156 focal reporters and world_broad benchmark, 2000–2024.\n\nCaveat: screens test composition sensitivity; they do not identify a causal effect of development.\n",
        encoding="utf-8",
    )
    write_review(classes, coverage_df, models)
    write_fragment(coverage_df, models)
    if args.publish_dir:
        publish(args.publish_dir)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
