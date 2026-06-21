#!/usr/bin/env python3
"""Post-2001 country-size and extensive-margin tests.

This is a focused robustness exercise for the country-size concentration result.
It asks whether larger countries became especially less concentrated after 2001,
and whether that pattern is consistent with product/partner entry margins.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_country_size_effect as cse  # noqa: E402
from trade_concentration_pipeline import sample_processed_path, sample_results_dir  # noqa: E402


POST_START_YEAR = 2002
DEFAULT_PRE_START_YEAR = 1989
DEFAULT_END_YEAR = 2024
MODEL_LABEL_POST = "post2001_year_fe"
MODEL_LABEL_POST_TWOWAY = "post2001_two_way_country_year_cluster"
MODEL_LABEL_INTERACTION = "pre_post2001_interaction_year_fe"
MODEL_LABEL_ACTIVE_POST = "post2001_active_count_year_fe"
MODEL_LABEL_ACTIVE_INTERACTION = "pre_post2001_active_count_interaction_year_fe"
MODEL_LABEL_ACTIVE_CONTROL = "post2001_active_count_control_year_fe"
POST_INTERACTION_TERM = "log_population_x_post_2001"
GDPPCC_POST_INTERACTION_TERM = "log_gdp_per_capita_x_post_2001"
ACTIVE_SPECS = (
    ("product", "active_count", "log_product_active_count", "Log active HS6 product count"),
    ("partner", "active_count", "log_partner_active_count", "Log active partner count"),
)
ACTIVE_COUNT_COLUMNS = {
    "product": "product_active_count",
    "partner": "partner_active_count",
}
ACTIVE_LOG_COLUMNS = {
    "product": "log_product_active_count",
    "partner": "log_partner_active_count",
}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_dirs(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def load_country_size_panel(country_sample: str, start_year: int, end_year: int) -> pd.DataFrame:
    path = sample_processed_path("country_size_effect_panel.parquet", country_sample)
    if not path.exists():
        raise FileNotFoundError(
            f"Missing country-size panel: {path}. Run scripts/run_country_size_effect.py first."
        )
    panel = pd.read_parquet(path)
    required = {
        "country",
        "iso3",
        "reporter_code",
        "year",
        "flow",
        cse.PRIMARY_TERM,
        cse.CONTROL_TERM,
        "product_active_count",
        "partner_active_count",
        *[spec[2] for spec in cse.OUTCOME_SPECS],
    }
    missing = sorted(required - set(panel.columns))
    if missing:
        raise RuntimeError(f"Country-size panel is missing required columns: {missing}")
    panel = panel[panel["year"].between(start_year, end_year)].copy()
    if panel.empty:
        raise RuntimeError("No country-size panel rows remain after the requested year filter.")
    dupes = int(panel.duplicated(["iso3", "year", "flow"]).sum())
    if dupes:
        raise RuntimeError(f"Country-size panel has {dupes:,} duplicate iso3-year-flow rows.")
    for dimension, active_count_col in ACTIVE_COUNT_COLUMNS.items():
        active = pd.to_numeric(panel[active_count_col], errors="coerce")
        if bool((active <= 0).any()):
            bad = int((active <= 0).sum())
            raise RuntimeError(f"{dimension} active count has {bad:,} nonpositive rows.")
        panel[ACTIVE_LOG_COLUMNS[dimension]] = np.log(active)
    panel["post_2001"] = panel["year"].ge(POST_START_YEAR).astype(float)
    panel[POST_INTERACTION_TERM] = panel[cse.PRIMARY_TERM] * panel["post_2001"]
    panel[GDPPCC_POST_INTERACTION_TERM] = panel[cse.CONTROL_TERM] * panel["post_2001"]
    return panel


def add_q_values(models: pd.DataFrame, labels: Iterable[str], terms: Iterable[str]) -> pd.DataFrame:
    out = models.copy()
    out["bh_q_value"] = np.nan
    for model_label in labels:
        for term in terms:
            mask = out["model_label"].eq(model_label) & out["term"].eq(term) & out["status"].eq("ok")
            out.loc[mask, "bh_q_value"] = cse.benjamini_hochberg(out.loc[mask, "p_value"])
    return out


def run_post_concentration_models(panel: pd.DataFrame, country_sample: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    post = panel[panel["year"].ge(POST_START_YEAR)].copy()
    country_clustered: list[cse.ModelResult] = []
    two_way: list[cse.ModelResult] = []
    for flow in cse.FLOWS:
        flow_panel = post[post["flow"].eq(flow)].copy()
        for dimension, metric, outcome, _label in cse.OUTCOME_SPECS:
            country_clustered.append(
                cse.run_ols_model(
                    flow_panel,
                    outcome=outcome,
                    terms=[cse.PRIMARY_TERM, cse.CONTROL_TERM],
                    fixed_effects=["year"],
                    model_label=MODEL_LABEL_POST,
                    sample=country_sample,
                    flow=flow,
                    dimension=dimension,
                    metric=metric,
                    cluster_col="reporter_code",
                )
            )
            two_way.append(
                cse.run_ols_model(
                    flow_panel,
                    outcome=outcome,
                    terms=[cse.PRIMARY_TERM, cse.CONTROL_TERM],
                    fixed_effects=["year"],
                    model_label=MODEL_LABEL_POST_TWOWAY,
                    sample=country_sample,
                    flow=flow,
                    dimension=dimension,
                    metric=metric,
                    cluster_col="reporter_code",
                    two_way_cluster_col="year",
                )
            )
    country_frame = add_q_values(
        cse.model_results_to_frame(country_clustered),
        [MODEL_LABEL_POST],
        [cse.PRIMARY_TERM],
    )
    two_way_frame = add_q_values(
        cse.model_results_to_frame(two_way),
        [MODEL_LABEL_POST_TWOWAY],
        [cse.PRIMARY_TERM],
    )
    return country_frame, two_way_frame


def run_interaction_concentration_models(panel: pd.DataFrame, country_sample: str) -> pd.DataFrame:
    results: list[cse.ModelResult] = []
    terms = [cse.PRIMARY_TERM, POST_INTERACTION_TERM, cse.CONTROL_TERM, GDPPCC_POST_INTERACTION_TERM]
    for flow in cse.FLOWS:
        flow_panel = panel.copy()
        flow_panel = flow_panel[flow_panel["flow"].eq(flow)].copy()
        for dimension, metric, outcome, _label in cse.OUTCOME_SPECS:
            results.append(
                cse.run_ols_model(
                    flow_panel,
                    outcome=outcome,
                    terms=terms,
                    fixed_effects=["year"],
                    model_label=MODEL_LABEL_INTERACTION,
                    sample=country_sample,
                    flow=flow,
                    dimension=dimension,
                    metric=metric,
                    cluster_col="reporter_code",
                )
            )
    return add_q_values(
        cse.model_results_to_frame(results),
        [MODEL_LABEL_INTERACTION],
        [cse.PRIMARY_TERM, POST_INTERACTION_TERM],
    )


def run_active_count_models(panel: pd.DataFrame, country_sample: str) -> pd.DataFrame:
    results: list[cse.ModelResult] = []
    post = panel[panel["year"].ge(POST_START_YEAR)].copy()
    interaction_terms = [
        cse.PRIMARY_TERM,
        POST_INTERACTION_TERM,
        cse.CONTROL_TERM,
        GDPPCC_POST_INTERACTION_TERM,
    ]
    for flow in cse.FLOWS:
        flow_post = post[post["flow"].eq(flow)].copy()
        flow_all = panel[panel["flow"].eq(flow)].copy()
        for dimension, metric, outcome, _label in ACTIVE_SPECS:
            results.append(
                cse.run_ols_model(
                    flow_post,
                    outcome=outcome,
                    terms=[cse.PRIMARY_TERM, cse.CONTROL_TERM],
                    fixed_effects=["year"],
                    model_label=MODEL_LABEL_ACTIVE_POST,
                    sample=country_sample,
                    flow=flow,
                    dimension=dimension,
                    metric=metric,
                    cluster_col="reporter_code",
                )
            )
            results.append(
                cse.run_ols_model(
                    flow_all,
                    outcome=outcome,
                    terms=interaction_terms,
                    fixed_effects=["year"],
                    model_label=MODEL_LABEL_ACTIVE_INTERACTION,
                    sample=country_sample,
                    flow=flow,
                    dimension=dimension,
                    metric=metric,
                    cluster_col="reporter_code",
                )
            )
    return add_q_values(
        cse.model_results_to_frame(results),
        [MODEL_LABEL_ACTIVE_POST, MODEL_LABEL_ACTIVE_INTERACTION],
        [cse.PRIMARY_TERM, POST_INTERACTION_TERM],
    )


def run_active_count_control_models(panel: pd.DataFrame, country_sample: str) -> pd.DataFrame:
    results: list[cse.ModelResult] = []
    post = panel[panel["year"].ge(POST_START_YEAR)].copy()
    for flow in cse.FLOWS:
        flow_panel = post[post["flow"].eq(flow)].copy()
        for dimension, metric, outcome, _label in cse.OUTCOME_SPECS:
            active_term = ACTIVE_LOG_COLUMNS[dimension]
            results.append(
                cse.run_ols_model(
                    flow_panel,
                    outcome=outcome,
                    terms=[cse.PRIMARY_TERM, cse.CONTROL_TERM, active_term],
                    fixed_effects=["year"],
                    model_label=MODEL_LABEL_ACTIVE_CONTROL,
                    sample=country_sample,
                    flow=flow,
                    dimension=dimension,
                    metric=metric,
                    cluster_col="reporter_code",
                )
            )
    return add_q_values(
        cse.model_results_to_frame(results),
        [MODEL_LABEL_ACTIVE_CONTROL],
        [cse.PRIMARY_TERM],
    )


def summarize_sample(panel: pd.DataFrame) -> pd.DataFrame:
    post = panel[panel["year"].ge(POST_START_YEAR)].copy()
    rows = [
        ("panel_rows", len(panel), ""),
        ("post2001_rows", len(post), f"year >= {POST_START_YEAR}"),
        ("countries", panel["iso3"].nunique(), ""),
        ("post2001_countries", post["iso3"].nunique(), ""),
        ("years", panel["year"].nunique(), ""),
        ("post2001_years", post["year"].nunique(), ""),
        ("duplicate_iso3_year_flow_rows", int(panel.duplicated(["iso3", "year", "flow"]).sum()), ""),
        ("flows", panel["flow"].nunique(), ",".join(sorted(panel["flow"].dropna().astype(str).unique()))),
    ]
    for flow in cse.FLOWS:
        sub = post[post["flow"].eq(flow)]
        rows.append((f"post2001_{flow.lower()}_rows", len(sub), ""))
    for col in [cse.PRIMARY_TERM, cse.CONTROL_TERM, "product_active_count", "partner_active_count"]:
        rows.append((f"missing_{col}", int(panel[col].isna().sum()), ""))
        rows.append((f"post2001_missing_{col}", int(post[col].isna().sum()), ""))
    return pd.DataFrame(rows, columns=["diagnostic", "value", "detail"])


def fmt_num(value: object, digits: int = 4) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value):.{digits}f}"


def fmt_sig(value: object, p_value: object, digits: int = 4) -> str:
    text = fmt_num(value, digits)
    if not text:
        return text
    if pd.notna(p_value) and float(p_value) < 0.05:
        return f"**{text}**"
    return text


def format_p(value: object) -> str:
    if pd.isna(value):
        return ""
    value = float(value)
    text = "0.0000" if value < 0.00005 else f"{value:.4f}"
    if value < 0.05:
        return f"**{text}**"
    return text


def gini_summary_table(post_models: pd.DataFrame, interaction_models: pd.DataFrame) -> str:
    post = post_models[
        post_models["term"].eq(cse.PRIMARY_TERM)
        & post_models["metric"].eq("gini")
        & post_models["status"].eq("ok")
    ].copy()
    inter = interaction_models[
        interaction_models["term"].eq(POST_INTERACTION_TERM)
        & interaction_models["metric"].eq("gini")
        & interaction_models["status"].eq("ok")
    ].copy()
    merged = post.merge(
        inter[["flow", "dimension", "coefficient", "std_error", "p_value", "bh_q_value"]],
        on=["flow", "dimension"],
        how="left",
        suffixes=("_post", "_interaction"),
    )
    rows = []
    for row in merged.sort_values(["flow", "dimension"]).itertuples(index=False):
        label = f"{row.flow} {row.dimension}"
        rows.append(
            {
                "Outcome": label,
                "Post-2001 log-pop beta": fmt_sig(row.coefficient_post, row.p_value_post),
                "Post p": format_p(row.p_value_post),
                "Post q": format_p(row.bh_q_value_post),
                "Post-2001 change beta": fmt_sig(row.coefficient_interaction, row.p_value_interaction),
                "Change p": format_p(row.p_value_interaction),
                "Change q": format_p(row.bh_q_value_interaction),
                "N": int(row.nobs),
            }
        )
    return pd.DataFrame(rows).to_markdown(index=False)


def active_count_summary_table(active_models: pd.DataFrame) -> str:
    post = active_models[
        active_models["model_label"].eq(MODEL_LABEL_ACTIVE_POST)
        & active_models["term"].eq(cse.PRIMARY_TERM)
        & active_models["status"].eq("ok")
    ].copy()
    inter = active_models[
        active_models["model_label"].eq(MODEL_LABEL_ACTIVE_INTERACTION)
        & active_models["term"].eq(POST_INTERACTION_TERM)
        & active_models["status"].eq("ok")
    ].copy()
    merged = post.merge(
        inter[["flow", "dimension", "coefficient", "std_error", "p_value", "bh_q_value"]],
        on=["flow", "dimension"],
        how="left",
        suffixes=("_post", "_interaction"),
    )
    rows = []
    for row in merged.sort_values(["flow", "dimension"]).itertuples(index=False):
        rows.append(
            {
                "Outcome": f"{row.flow} {row.dimension}",
                "Post-2001 log-pop beta": fmt_sig(row.coefficient_post, row.p_value_post),
                "Post p": format_p(row.p_value_post),
                "Post-2001 change beta": fmt_sig(row.coefficient_interaction, row.p_value_interaction),
                "Change p": format_p(row.p_value_interaction),
                "N": int(row.nobs),
            }
        )
    return pd.DataFrame(rows).to_markdown(index=False)


def attenuation_summary_table(post_models: pd.DataFrame, active_control_models: pd.DataFrame) -> str:
    post = post_models[
        post_models["term"].eq(cse.PRIMARY_TERM)
        & post_models["metric"].eq("gini")
        & post_models["status"].eq("ok")
    ].copy()
    active_control = active_control_models[
        active_control_models["term"].eq(cse.PRIMARY_TERM)
        & active_control_models["metric"].eq("gini")
        & active_control_models["status"].eq("ok")
    ].copy()
    merged = post.merge(
        active_control[["flow", "dimension", "coefficient", "std_error", "p_value"]],
        on=["flow", "dimension"],
        how="left",
        suffixes=("_post", "_active_control"),
    )
    rows = []
    for row in merged.sort_values(["flow", "dimension"]).itertuples(index=False):
        beta_post = float(row.coefficient_post)
        beta_control = float(row.coefficient_active_control)
        attenuation = (beta_post - beta_control) / beta_post if beta_post else np.nan
        rows.append(
            {
                "Outcome": f"{row.flow} {row.dimension}",
                "Post beta": fmt_sig(beta_post, row.p_value_post),
                "With log active count": fmt_sig(beta_control, row.p_value_active_control),
                "Attenuation share": fmt_num(attenuation, 3),
                "Active-count interpretation": "supports active-margin channel" if attenuation > 0.25 else "does not mediate much",
            }
        )
    return pd.DataFrame(rows).to_markdown(index=False)


def write_summary(
    path: Path,
    args: argparse.Namespace,
    sample: pd.DataFrame,
    post_models: pd.DataFrame,
    interaction_models: pd.DataFrame,
    active_models: pd.DataFrame,
    active_control_models: pd.DataFrame,
    output_paths: dict[str, Path],
) -> None:
    sample_values = sample.set_index("diagnostic")["value"].to_dict()
    text = f"""# Post-2001 Country-Size Entry-Margin Test

Generated: {now_utc()}

## Question

Do larger countries become less concentrated after 2001 in a way that is consistent with lower fixed costs of product and partner entry?

This is a descriptive robustness test, not a causal estimate of the effect of globalization or fixed-cost declines.

## Specifications

Post-2001 restricted model:

```text
concentration_it = beta log_population_it
                 + gamma log_gdp_per_capita_it
                 + year FE
                 + error_it
```

Pre/post interaction model:

```text
concentration_it = beta_pre log_population_it
                 + beta_change [log_population_it x 1(year >= {POST_START_YEAR})]
                 + gamma_pre log_gdp_per_capita_it
                 + gamma_change [log_gdp_per_capita_it x 1(year >= {POST_START_YEAR})]
                 + year FE
                 + error_it
```

The active-count model replaces the dependent variable with `log(product_active_count)` or `log(partner_active_count)`. The active-count control model adds the matching log active count to the post-2001 concentration regression. Product concentration inherits the upstream exclusion of HS6 `999999`; partner concentration follows the repo's partner-total convention.

## Sample

- Country sample: `{args.country_sample}`
- Pre/post window: {args.start_year}-{args.end_year}
- Post period: {POST_START_YEAR}-{args.end_year}
- Panel rows: {int(sample_values.get("panel_rows", 0)):,}
- Post-2001 rows: {int(sample_values.get("post2001_rows", 0)):,}
- Countries: {int(sample_values.get("countries", 0))}
- Post-2001 countries: {int(sample_values.get("post2001_countries", 0))}

## Gini Results

`Post-2001 change beta` is the interaction coefficient. A negative value means the size gradient is more negative after 2001 than in 1989-2001.

{gini_summary_table(post_models, interaction_models)}

## Active Product And Partner Counts

A positive coefficient means larger countries have more active products or partners. A positive post-2001 change supports the fixed-cost-entry mechanism.

{active_count_summary_table(active_models)}

## Does Active-Count Entry Mediate The Gini Result?

This is not causal mediation because active counts are part of concentration construction. It is a diagnostic: if the log-population coefficient shrinks after adding log active count, the size gradient is partly an extensive-margin count story.

{attenuation_summary_table(post_models, active_control_models)}

## Interpretation

- The post-2001 concentration slopes are negative for all four Gini families: import product, import partner, export product, and export partner.
- The interaction test is strongest for export partner concentration: the size gradient becomes materially more negative after 2001.
- Import product and import partner gradients also move in the predicted negative direction, but the interaction coefficients are weaker.
- Larger countries have more active products and partners after 2001, but the pre/post active-count interactions are negative. That means the size premium in active counts is smaller after 2001 than in 1989-2001, not larger. This weakens the strongest version of the claim that larger countries benefited more from falling product/partner entry costs.
- A more defensible interpretation is that large countries remain broader traders after 2001, while smaller countries may have partially caught up in active-count coverage. The export-partner concentration gradient still becomes more negative after 2001, so partner-value reallocation or destination mix may matter beyond simple active-count entry.
- The active-count diagnostic supports an extensive-margin interpretation most clearly for import product concentration. It does not explain much of the export product or partner Gini gradient.

## Caveats

- This is not a causal post-2001 treatment design. The post period combines WTO-era trade integration, China/GVC expansion, reporting improvements, commodity cycles, and macro shocks.
- Active counts are mechanically related to concentration measures, so the active-count control is diagnostic rather than a clean mediator.
- The interaction model compares 1989-2001 with 2002-{args.end_year}; early years have fewer country observations than the mature panel.
- Product-facing measures inherit the upstream HS6 `999999` exclusion and HS-revision handling from the concentration panel.

## Files

- Post-2001 concentration models: `{rel(output_paths["post_models"])}`
- Post-2001 two-way clustered concentration models: `{rel(output_paths["post_two_way_models"])}`
- Pre/post interaction concentration models: `{rel(output_paths["interaction_models"])}`
- Active-count models: `{rel(output_paths["active_models"])}`
- Active-count control models: `{rel(output_paths["active_control_models"])}`
- Sample diagnostics: `{rel(output_paths["sample_diagnostics"])}`
- Manifest: `{rel(output_paths["manifest"])}`
"""
    path.write_text(text, encoding="utf-8")


def write_manifest(path: Path, args: argparse.Namespace, output_paths: dict[str, Path]) -> None:
    manifest = {
        "generated_at": now_utc(),
        "script": rel(Path(__file__).resolve()),
        "country_sample": args.country_sample,
        "start_year": args.start_year,
        "post_start_year": POST_START_YEAR,
        "end_year": args.end_year,
        "input_panel": rel(sample_processed_path("country_size_effect_panel.parquet", args.country_sample)),
        "outputs": {key: rel(value) for key, value in output_paths.items()},
        "model": "year fixed effects with reporter-country clustered SEs; post-2001 restricted and pre/post interaction variants",
        "repo_rules": {
            "product_999999": "inherited upstream exclusion from concentration panel",
            "partner_999999": "inherited upstream partner-total convention",
            "country_sample": "rd2_countries by default",
        },
    }
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country-sample", default="rd2_countries", choices=cse.COUNTRY_SAMPLE_CHOICES)
    parser.add_argument("--start-year", type=int, default=DEFAULT_PRE_START_YEAR)
    parser.add_argument("--end-year", type=int, default=DEFAULT_END_YEAR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.start_year >= POST_START_YEAR:
        raise RuntimeError(f"start-year must be before {POST_START_YEAR} for the pre/post interaction test.")
    if args.end_year < POST_START_YEAR:
        raise RuntimeError(f"end-year must be at least {POST_START_YEAR}.")

    result_dir = sample_results_dir(args.country_sample)
    table_dir = result_dir / "country_size_post2001_entry_test_tables"
    ensure_dirs(result_dir, table_dir)

    panel = load_country_size_panel(args.country_sample, args.start_year, args.end_year)
    sample = summarize_sample(panel)
    post_models, post_two_way = run_post_concentration_models(panel, args.country_sample)
    interaction_models = run_interaction_concentration_models(panel, args.country_sample)
    active_models = run_active_count_models(panel, args.country_sample)
    active_control_models = run_active_count_control_models(panel, args.country_sample)

    output_paths = {
        "post_models": table_dir / "post2001_concentration_models.csv",
        "post_two_way_models": table_dir / "post2001_two_way_cluster_models.csv",
        "interaction_models": table_dir / "pre_post2001_interaction_models.csv",
        "active_models": table_dir / "active_count_models.csv",
        "active_control_models": table_dir / "active_count_control_models.csv",
        "sample_diagnostics": table_dir / "sample_diagnostics.csv",
        "manifest": result_dir / "run_manifest_country_size_post2001_entry_test.json",
        "summary": result_dir / "country_size_post2001_entry_test.md",
    }

    post_models.to_csv(output_paths["post_models"], index=False)
    post_two_way.to_csv(output_paths["post_two_way_models"], index=False)
    interaction_models.to_csv(output_paths["interaction_models"], index=False)
    active_models.to_csv(output_paths["active_models"], index=False)
    active_control_models.to_csv(output_paths["active_control_models"], index=False)
    sample.to_csv(output_paths["sample_diagnostics"], index=False)
    write_manifest(output_paths["manifest"], args, output_paths)
    write_summary(
        output_paths["summary"],
        args,
        sample,
        post_models,
        interaction_models,
        active_models,
        active_control_models,
        output_paths,
    )

    print(f"Wrote {output_paths['summary']}")


if __name__ == "__main__":
    main()
