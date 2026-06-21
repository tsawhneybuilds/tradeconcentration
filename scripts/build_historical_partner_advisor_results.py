#!/usr/bin/env python3
"""Build question-led figures and a short advisor memo from Cadot outputs."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "results" / "historical_partner_concentration"
FIGURES_DIR = RESULTS_DIR / "figures" / "advisor"
SUMMARY_PATH = RESULTS_DIR / "cadot_model_summary.csv"
MEMO_PATH = RESULTS_DIR / "historical_partner_concentration_advisor_memo.md"
EVIDENCE_PATH = RESULTS_DIR / "historical_partner_concentration_advisor_evidence.md"
TABLE_PATH = RESULTS_DIR / "advisor_preferred_within_results.csv"

PRIMARY_VARIANT = "baseline_threshold20"
PRIMARY_MODEL = "entity_year_fe_logpop"
PRIMARY_COMPONENT = "within"
PRIMARY_INCOME = "gdppc_10k"
PRIMARY_SAMPLE_POLICY = "fixed"
METRIC_ORDER = ["Gini", "Theil", "HHI"]
FLOW_ORDER = ["Exports", "Imports"]
OUTCOME_ORDER = [(flow, metric) for flow in FLOW_ORDER for metric in METRIC_ORDER]

NAVY = "#17324D"
BLUE = "#2B6F9E"
LIGHT_BLUE = "#A7C4D8"
MID_GREY = "#777777"
LIGHT_GREY = "#D7DADD"
VERY_LIGHT_GREY = "#EEF0F2"
RED = "#9C2F2F"


def configure_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.titlesize": 11,
            "axes.labelsize": 10,
            "axes.edgecolor": MID_GREY,
            "axes.linewidth": 0.7,
            "xtick.color": "#333333",
            "ytick.color": "#333333",
            "text.color": "#222222",
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
        }
    )


def read_summary() -> pd.DataFrame:
    summary = pd.read_csv(SUMMARY_PATH)
    required = {
        "variant",
        "flow",
        "metric_name",
        "income_form",
        "sample_policy",
        "model_name",
        "curve_component",
        "observations",
        "entity_count",
        "support_p05",
        "support_p95",
        "turning_point_ppp_2011_usd",
        "turning_point_inside_p05_p95",
        "slope_p05",
        "slope_p95",
        "u_test_p_value",
        "u_test_q_value",
        "classification",
    }
    missing = sorted(required.difference(summary.columns))
    if missing:
        raise ValueError(f"Missing required model-summary columns: {missing}")
    return summary


def preferred_within(summary: pd.DataFrame) -> pd.DataFrame:
    preferred = summary[
        summary["variant"].eq(PRIMARY_VARIANT)
        & summary["income_form"].eq(PRIMARY_INCOME)
        & summary["sample_policy"].eq(PRIMARY_SAMPLE_POLICY)
        & summary["model_name"].eq(PRIMARY_MODEL)
        & summary["curve_component"].eq(PRIMARY_COMPONENT)
    ].copy()
    preferred["outcome_order"] = preferred.apply(
        lambda row: OUTCOME_ORDER.index((str(row["flow"]), str(row["metric_name"]))), axis=1
    )
    preferred = preferred.sort_values("outcome_order").reset_index(drop=True)
    if len(preferred) != 6 or preferred[["flow", "metric_name"]].duplicated().any():
        raise ValueError("Expected exactly one preferred within-country row for each of six flow-metric outcomes.")
    return preferred


def all_within_sensitivities(summary: pd.DataFrame) -> pd.DataFrame:
    sensitivity = summary[
        summary["income_form"].eq(PRIMARY_INCOME)
        & summary["sample_policy"].eq(PRIMARY_SAMPLE_POLICY)
        & summary["model_name"].eq(PRIMARY_MODEL)
        & summary["curve_component"].eq(PRIMARY_COMPONENT)
    ].copy()
    sensitivity["outcome"] = sensitivity["flow"] + " — " + sensitivity["metric_name"]
    expected = sensitivity.groupby(["flow", "metric_name"]).size()
    if len(expected) != 6 or expected.nunique() != 1:
        raise ValueError(f"Sensitivity grid is not rectangular: {expected.to_dict()}")
    return sensitivity


def tidy_axes(ax: plt.Axes) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color=VERY_LIGHT_GREY, linewidth=0.8)
    ax.set_axisbelow(True)


def save_figure(fig: plt.Figure, stem: str) -> tuple[Path, Path]:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    png_path = FIGURES_DIR / f"{stem}.png"
    pdf_path = FIGURES_DIR / f"{stem}.pdf"
    fig.savefig(png_path, dpi=240, bbox_inches="tight")
    fig.savefig(pdf_path, bbox_inches="tight")
    plt.close(fig)
    return png_path, pdf_path


def plot_baseline_u_tests(preferred: pd.DataFrame) -> tuple[Path, Path]:
    """Question: Do any preferred within-country models pass the formal U-test?"""
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.8), sharex=True, sharey=True)
    for ax, flow in zip(axes, FLOW_ORDER, strict=True):
        subset = preferred[preferred["flow"].eq(flow)].set_index("metric_name").loc[METRIC_ORDER].reset_index()
        ypos = np.arange(len(subset))[::-1]
        ax.axvspan(0, 0.05, color=VERY_LIGHT_GREY, zorder=0)
        ax.axvline(0.05, color=RED, linewidth=1.0, linestyle=(0, (3, 3)), zorder=1)
        ax.scatter(subset["u_test_p_value"], ypos, s=48, color=NAVY, zorder=3)
        for y, (_, row) in zip(ypos, subset.iterrows(), strict=True):
            label = f"p = {row['u_test_p_value']:.3f}   q = {row['u_test_q_value']:.3f}"
            ax.annotate(label, (float(row["u_test_p_value"]), y), xytext=(7, 0), textcoords="offset points", va="center", fontsize=9)
        ax.set_yticks(ypos, subset["metric_name"])
        ax.set_xlim(0, 1.0)
        ax.set_xticks([0, 0.05, 0.25, 0.50, 0.75, 1.00])
        ax.set_xticklabels(["0", ".05", ".25", ".50", ".75", "1"])
        ax.set_title(flow, loc="left", fontweight="bold")
        tidy_axes(ax)
    axes[0].set_xlabel("Wild-cluster bootstrap U-test p-value")
    axes[1].set_xlabel("Wild-cluster bootstrap U-test p-value")
    fig.suptitle(
        "No baseline partner-concentration measure passes the U-shape test",
        x=0.08,
        ha="left",
        fontsize=15,
        fontweight="bold",
    )
    fig.text(
        0.08,
        0.91,
        "Preferred within-country models; the shaded region marks p < 0.05.",
        ha="left",
        fontsize=10,
        color="#444444",
    )
    fig.text(
        0.08,
        0.015,
        "Notes: Entity and year fixed effects plus log population; 13 reporter entities; 1,670 export and 1,634 import observations. "
        "Rademacher wild-cluster bootstrap, 9,999 draws; q is Benjamini–Hochberg adjusted across the six primary tests.",
        ha="left",
        va="bottom",
        fontsize=8.3,
        color="#555555",
        wrap=True,
    )
    fig.subplots_adjust(left=0.08, right=0.98, top=0.82, bottom=0.20, wspace=0.18)
    return save_figure(fig, "baseline_u_shape_tests")


def plot_sensitivity_u_tests(sensitivity: pd.DataFrame, preferred: pd.DataFrame) -> tuple[Path, Path]:
    """Question: Does any reasonable within-country sensitivity support a U-shape?"""
    rng = np.random.default_rng(20260618)
    labels = [f"{flow} — {metric}" for flow, metric in OUTCOME_ORDER]
    ymap = {label: len(labels) - 1 - idx for idx, label in enumerate(labels)}

    fig, ax = plt.subplots(figsize=(10.5, 5.7))
    ax.axvspan(0, 0.05, color=VERY_LIGHT_GREY, zorder=0)
    ax.axvline(0.05, color=RED, linewidth=1.0, linestyle=(0, (3, 3)), zorder=1)

    for flow, metric in OUTCOME_ORDER:
        label = f"{flow} — {metric}"
        group = sensitivity[sensitivity["outcome"].eq(label)].copy()
        y = ymap[label]
        jitter = rng.uniform(-0.12, 0.12, size=len(group))
        ax.hlines(y, group["u_test_p_value"].min(), group["u_test_p_value"].max(), color=LIGHT_GREY, linewidth=1.0, zorder=1)
        ax.scatter(group["u_test_p_value"], y + jitter, s=19, color=LIGHT_BLUE, alpha=0.85, edgecolors="none", zorder=2)

        base = preferred[(preferred["flow"].eq(flow)) & (preferred["metric_name"].eq(metric))].iloc[0]
        ax.scatter(float(base["u_test_p_value"]), y, s=55, marker="D", color=NAVY, edgecolor="white", linewidth=0.6, zorder=4)
        ax.text(1.015, y, f"min p = {group['u_test_p_value'].min():.3f}", va="center", fontsize=8.7, color="#444444", clip_on=False)

    ax.set_yticks([ymap[label] for label in labels], labels)
    ax.set_xlim(0, 1.0)
    ax.set_xticks([0, 0.05, 0.25, 0.50, 0.75, 1.00])
    ax.set_xticklabels(["0", ".05", ".25", ".50", ".75", "1"])
    ax.set_xlabel("Wild-cluster bootstrap U-test p-value")
    tidy_axes(ax)
    fig.suptitle(
        "None of 168 within-country sensitivity tests reaches p < 0.05",
        x=0.12,
        ha="left",
        fontsize=15,
        fontweight="bold",
    )
    fig.text(
        0.12,
        0.91,
        "Each row contains 28 sample, coverage, source-regime, and leave-one-entity-out variants; diamonds mark the baseline.",
        ha="left",
        fontsize=10,
        color="#444444",
    )
    fig.text(
        0.12,
        0.015,
        "Notes: A supported U-shape also requires a negative low-income slope, a positive high-income slope, an in-support turning point, "
        "and adequate observations and entities on both sides. No variant satisfies the full classification rule.",
        ha="left",
        va="bottom",
        fontsize=8.3,
        color="#555555",
        wrap=True,
    )
    fig.subplots_adjust(left=0.22, right=0.88, top=0.82, bottom=0.17)
    return save_figure(fig, "within_u_shape_sensitivity")


def sign_pattern(row: pd.Series) -> str:
    low = float(row["slope_p05"])
    high = float(row["slope_p95"])
    low_sign = "negative" if low < 0 else "positive"
    high_sign = "negative" if high < 0 else "positive"
    if low < 0 < high:
        return "U-shaped signs"
    if low > 0 > high:
        return "inverted-U signs"
    return f"{low_sign} to {high_sign}"


def support_label(row: pd.Series) -> str:
    if bool(row["turning_point_inside_p05_p95"]):
        return f"${float(row['turning_point_ppp_2011_usd']):,.0f}"
    return "outside support"


def classification_label(value: str) -> str:
    return {
        "supported_u_shape": "supported U-shape",
        "suggestive_only": "sign pattern only",
        "outside_support": "outside support",
        "no_u_shape": "no U-shape",
        "insufficient_support": "insufficient support",
    }.get(value, value.replace("_", " "))


def write_preferred_table(preferred: pd.DataFrame) -> None:
    output = preferred[
        [
            "flow",
            "metric_name",
            "observations",
            "entity_count",
            "support_p05",
            "support_p95",
            "slope_p05",
            "slope_p95",
            "turning_point_ppp_2011_usd",
            "turning_point_inside_p05_p95",
            "u_test_p_value",
            "u_test_q_value",
            "classification",
        ]
    ].copy()
    output["support_p05_ppp_2011_usd"] = output.pop("support_p05") * 10_000
    output["support_p95_ppp_2011_usd"] = output.pop("support_p95") * 10_000
    output["slope_sign_pattern"] = preferred.apply(sign_pattern, axis=1)
    output.to_csv(TABLE_PATH, index=False)


def build_memo(preferred: pd.DataFrame, sensitivity: pd.DataFrame) -> str:
    export_n = int(preferred.loc[preferred["flow"].eq("Exports"), "observations"].iloc[0])
    import_n = int(preferred.loc[preferred["flow"].eq("Imports"), "observations"].iloc[0])
    min_sensitivity_p = float(sensitivity["u_test_p_value"].min())
    supported_count = int(sensitivity["classification"].eq("supported_u_shape").sum())
    rows = []
    for _, row in preferred.iterrows():
        rows.append(
            "| {flow} | {metric} | {signs} | {turning} | {p:.3f} | {q:.3f} | {classification} |".format(
                flow=row["flow"],
                metric=row["metric_name"],
                signs=sign_pattern(row),
                turning=support_label(row),
                p=float(row["u_test_p_value"]),
                q=float(row["u_test_q_value"]),
                classification=classification_label(str(row["classification"])),
            )
        )

    return "\n".join(
        [
            "# Advisor results memo: long-run trade-partner concentration",
            "",
            "## Bottom line",
            "",
            "The 1827–2014 data do **not** support a Cadot-style diversification-then-reconcentration pattern across trading partners. "
            "None of the six preferred within-country tests passes the formal U-shape test, and none survives the full sensitivity grid. "
            "The defensible interpretation is a null result for partner concentration—not evidence against Cadot's product-diversification result.",
            "",
            "![Baseline U-shape tests](figures/advisor/baseline_u_shape_tests.png)",
            "",
            "## What the estimates show",
            "",
            "Only export Gini and export Theil have the required negative-to-positive endpoint slopes. Their joint U-test p-values are "
            f"{float(preferred[(preferred.flow == 'Exports') & (preferred.metric_name == 'Gini')].u_test_p_value.iloc[0]):.3f} and "
            f"{float(preferred[(preferred.flow == 'Exports') & (preferred.metric_name == 'Theil')].u_test_p_value.iloc[0]):.3f}; "
            "both have BH-adjusted q = 0.841. Export Gini also lacks enough support above its estimated trough. "
            "The import measures either continue declining or have inverted-U signs.",
            "",
            "| Flow | Measure | Endpoint slopes | Stationary point, if in support | Raw U-test p | BH q | Classification |",
            "| --- | --- | --- | ---: | ---: | ---: | --- |",
            *rows,
            "",
            f"Across 168 preferred within-country sensitivity tests—28 variants for each flow-measure pair—there are {supported_count} supported U-shapes. "
            f"The smallest raw U-test p-value is {min_sensitivity_p:.3f}, still well above 0.05.",
            "",
            "![Sensitivity U-shape tests](figures/advisor/within_u_shape_sensitivity.png)",
            "",
            "## Interpretation and recommendation",
            "",
            "Partner concentration does not reproduce the product-space hump in this long historical sample. A plausible substantive interpretation is that "
            "development broadens the product margin differently from the geographic partner margin; however, this exercise is descriptive and cannot identify "
            "income as the cause of either process.",
            "",
            "I recommend presenting this as a disciplined negative result: keep the partner analysis as a boundary test of the Cadot mechanism, and make the next "
            "decision explicit—either compare product and partner concentration in the same countries and years, or move the partner result to an appendix and "
            "focus the main paper on product diversification.",
            "",
            "## Data and inference note",
            "",
            f"The preferred models use {export_n:,} export and {import_n:,} import entity-years from 13 historical reporter entities, with entity and year fixed effects "
            "and log population. Income is Maddison real GDP per capita in 2011 PPP dollars. Inference uses 9,999 entity-level Rademacher wild-cluster bootstrap draws; "
            "the six primary tests use Benjamini–Hochberg adjustment.",
            "",
            r"For strictly positive observed partner flows \(x_j\), shares are \(s_j=x_j/\sum_jx_j\). The measures are "
            r"\(G=2\sum_j jx_{(j)}/(n\sum_jx_j)-(n+1)/n\), \(T=\sum_js_j\log(ns_j)\), and \(HHI=\sum_js_j^2\). "
            "Higher values mean trade is more concentrated among active partners. Baseline estimates require at least 20 active partners; missing dyads are not coded as zero.",
            "",
            "The remaining limitations are 13 clusters, uneven historical coverage, Maddison income/population attrition, changing source regimes, and the absence of a fresh "
            "independent-agent trust review. The completed local adversarial review rates the pipeline **mostly trustworthy** and finds no unresolved high-risk coding defect.",
            "",
            "**Question for discussion:** Should the null partner result become an appendix boundary test, or should we build a matched product-versus-partner comparison as the next main exhibit?",
            "",
        ]
    )


def build_evidence_ledger(preferred: pd.DataFrame, sensitivity: pd.DataFrame) -> str:
    return "\n".join(
        [
            "# Internal evidence ledger for the advisor memo",
            "",
            "## Figure contracts",
            "",
            "### Figure 1 — baseline inference",
            "",
            "- Question: Do any preferred within-country partner-concentration models pass the formal U-shape test?",
            "- Answer: No; all six wild-cluster bootstrap p-values exceed 0.45 and all BH q-values equal 0.841.",
            "- Comparison: Six raw U-test p-values against the 0.05 threshold, split by exports and imports.",
            "- Unit: Flow-measure model result.",
            "- Sample: Baseline minimum 20 active partners; entity and year fixed effects plus log population.",
            "- Integrity caveat: A p-value plot communicates inference, not effect size; the table retains signs and turning-point support.",
            "",
            "### Figure 2 — robustness",
            "",
            "- Question: Does any reasonable within-country sensitivity support a U-shape?",
            f"- Answer: No; {len(sensitivity)} tests yield zero supported U-shapes and the minimum raw p-value is {sensitivity['u_test_p_value'].min():.3f}.",
            "- Comparison: Full p-value distributions across 28 variants for each of six flow-measure outcomes.",
            "- Unit: Flow-measure-variant model result.",
            "- Integrity caveat: The variants change samples and measurement conventions, so the graph shows robustness of the conclusion rather than a pooled sampling distribution.",
            "",
            "## Sources inspected",
            "",
            "- `results/historical_partner_concentration/cadot_model_summary.csv`",
            "- `results/historical_partner_concentration/sample_attrition.csv`",
            "- `results/historical_partner_concentration/historical_partner_mpd_merge_attrition.csv`",
            "- `results/historical_partner_concentration/historical_partner_build_manifest.json`",
            "- `results/historical_partner_concentration/run_manifest.json`",
            "- `results/historical_partner_concentration/adversarial_review.md`",
            "",
            "## Unresolved fact",
            "",
            "- The post-fix adversarial review was local rather than a fresh independent-agent pass.",
            "",
        ]
    )


def main() -> None:
    configure_style()
    summary = read_summary()
    preferred = preferred_within(summary)
    sensitivity = all_within_sensitivities(summary)

    if sensitivity["classification"].eq("supported_u_shape").any():
        raise ValueError("Memo language assumes no supported within-country sensitivity; source outputs now disagree.")

    plot_baseline_u_tests(preferred)
    plot_sensitivity_u_tests(sensitivity, preferred)
    write_preferred_table(preferred)
    MEMO_PATH.write_text(build_memo(preferred, sensitivity), encoding="utf-8")
    EVIDENCE_PATH.write_text(build_evidence_ledger(preferred, sensitivity), encoding="utf-8")
    print(f"Wrote {MEMO_PATH.relative_to(ROOT)}")
    print(f"Wrote advisor figures under {FIGURES_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
