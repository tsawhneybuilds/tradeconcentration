#!/usr/bin/env python3
"""Build a standalone Cadot hump explainer HTML from local outputs.

The page is a reader-facing synthesis, not a new empirical pipeline. It pulls
tables from the existing rd2 Cadot tribunal and PPP hump regression artifacts.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from html import escape
import os
from pathlib import Path
import re
from typing import Iterable

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "results" / "samples" / "rd2_countries"
OUT = BASE / "workinprogress.html"
LEGACY_OUT = BASE / "cadot_hump_from_scratch_explainer.html"

CADOT_FIG = BASE / "cadot_hump_tribunal_figures" / "cadot_hump_curve.png"
MECHANISM_FIG = BASE / "cadot_hump_tribunal_figures" / "mechanism_scorecard.png"
OLD_CONE_FIG = BASE / "cadot_hump_tribunal_figures" / "old_cone_exit_plot.png"
PPP_LEVEL_FIG = (
    BASE
    / "ppp_hump_regression_figures"
    / "ppp_hump_diagnostics_level_ppp_five_outcomes.png"
)
PPP_LOG_FIG = (
    BASE
    / "ppp_hump_regression_figures"
    / "ppp_hump_diagnostics_log_ppp_five_outcomes.png"
)
PPP_BROWSER_DIR = BASE / "ppp_hump_regression_figures" / "product_browser"
PPP_BROWSER_FIGS = {
    "export_world_relative_product_gini": {
        "label": "Export World-Relative Product Gini",
        "level_ppp": PPP_BROWSER_DIR / "export_world_relative_product_gini_level_ppp.png",
        "log_ppp": PPP_BROWSER_DIR / "export_world_relative_product_gini_log_ppp.png",
    },
    "export_product_gini": {
        "label": "Export Product Gini",
        "level_ppp": PPP_BROWSER_DIR / "export_product_gini_level_ppp.png",
        "log_ppp": PPP_BROWSER_DIR / "export_product_gini_log_ppp.png",
    },
    "import_product_gini": {
        "label": "Import Product Gini",
        "level_ppp": PPP_BROWSER_DIR / "import_product_gini_level_ppp.png",
        "log_ppp": PPP_BROWSER_DIR / "import_product_gini_log_ppp.png",
    },
}

TRIBUNAL_MODELS = BASE / "cadot_hump_tribunal_tables" / "cadot_hump_models.csv"
PPP_SUMMARY = BASE / "ppp_hump_regression_tables" / "ppp_hump_regression_summary.csv"
PPP_FE = BASE / "ppp_hump_regression_tables" / "ppp_hump_country_fe_robustness.csv"
PPP_MICROSTATE = (
    BASE
    / "ppp_hump_regression_tables"
    / "ppp_hump_regression_summary_no_isl_lux_guy.csv"
)
MECHANISM = BASE / "cadot_hump_tribunal_tables" / "mechanism_scorecard_summary.csv"
OLD_CONE = BASE / "cadot_hump_tribunal_tables" / "old_cone_exit_models.csv"
BROAD_BASE = ROOT / "results" / "samples" / "cadot_broad_156"
BROAD_TABLE_DIR = BROAD_BASE / "cadot_broad_ppp_hump_regression_tables"
BROAD_FIGURE_DIR = BROAD_BASE / "cadot_broad_ppp_hump_regression_figures"
BROAD_SUMMARY = BROAD_TABLE_DIR / "ppp_hump_regression_summary.csv"
BROAD_ATTRITION = BROAD_TABLE_DIR / "ppp_hump_sample_attrition.csv"
BROAD_INDEPENDENT_CHECKS = BROAD_TABLE_DIR / "ppp_hump_independent_reestimate_checks.csv"
BROAD_DIAGNOSTICS = BROAD_TABLE_DIR / "ppp_hump_diagnostics.json"
BROAD_LEVEL_FIG = BROAD_FIGURE_DIR / "ppp_hump_diagnostics_level_ppp_five_outcomes.png"
BROAD_LOG_FIG = BROAD_FIGURE_DIR / "ppp_hump_diagnostics_log_ppp_five_outcomes.png"
BROAD_MEMO = BROAD_BASE / "cadot_broad_ppp_hump_regressions.md"
BROAD_REVIEW = BROAD_TABLE_DIR / "adversarial_review.md"
CONSTANT_RERUN_REVIEW = ROOT / "correspondence" / "referee2" / "2026-06-02_cadot_constant_ppp_rerun_review.md"
EXPLANATORY_DIR = BASE / "import_concentration_explanatory_regressions"
EXPLANATORY_SUMMARY = EXPLANATORY_DIR / "regression_model_summary.csv"
EXPLANATORY_TERMS = EXPLANATORY_DIR / "regression_terms.csv"
EXPLANATORY_DIAGNOSTICS = EXPLANATORY_DIR / "sample_diagnostics.csv"
EXPLANATORY_SAMPLE_MANIFEST = EXPLANATORY_DIR / "model_sample_manifest.csv"
EXPLANATORY_INFLUENCE = EXPLANATORY_DIR / "leave_one_country_influence.csv"
EXPLANATORY_TARIFF_ENDPOINTS = EXPLANATORY_DIR / "tariff_endpoint_diagnostics.csv"
EXPLANATORY_MEMO = EXPLANATORY_DIR / "import_concentration_explanatory_regressions.md"
EXPLANATORY_FIG = EXPLANATORY_DIR / "figures" / "selected_explanatory_coefficients.png"
EXPLANATORY_ADVERSARIAL = EXPLANATORY_DIR / "adversarial_review.md"
COUNTRY_WIKI_DIR = BASE / "import_energy_gini_diagnostics" / "country_wiki"
COUNTRY_WIKI_README = COUNTRY_WIKI_DIR / "README.md"
COUNTRY_WIKI_SYNTHESIS = COUNTRY_WIKI_DIR / "synthesis.md"
COUNTRY_WIKI_GROUP_MEMOS = COUNTRY_WIKI_DIR / "group_memos.md"
COUNTRY_WIKI_METHOD = COUNTRY_WIKI_DIR / "method_note.md"
COUNTRY_WIKI_SOURCES = COUNTRY_WIKI_DIR / "sources.md"
COUNTRY_WIKI_ADVERSARIAL = COUNTRY_WIKI_DIR / "adversarial_review.md"
COUNTRY_WIKI_INDEX = COUNTRY_WIKI_DIR / "country_index.csv"
COUNTRY_WIKI_COUNTRIES = COUNTRY_WIKI_DIR / "countries"
TOP5_WIKI_DIR = BASE / "import_energy_gini_diagnostics" / "top5_country_wiki"
TOP5_WIKI_README = TOP5_WIKI_DIR / "README.md"
TOP5_WIKI_SYNTHESIS = TOP5_WIKI_DIR / "synthesis.md"
TOP5_WIKI_GROUP_MEMOS = TOP5_WIKI_DIR / "group_memos.md"
TOP5_WIKI_METHOD = TOP5_WIKI_DIR / "method_note.md"
TOP5_WIKI_SOURCES = TOP5_WIKI_DIR / "sources.md"
TOP5_WIKI_ADVERSARIAL = TOP5_WIKI_DIR / "adversarial_review.md"
TOP5_WIKI_INDEX = TOP5_WIKI_DIR / "country_index.csv"
TOP5_WIKI_COUNTRIES = TOP5_WIKI_DIR / "countries"
MECHANISM_REGRESSION_DIR = BASE / "import_gini_mechanism_regressions"
MECHANISM_REGRESSION_SECTION = (
    MECHANISM_REGRESSION_DIR / "import_gini_mechanism_regressions_section.html"
)
MECHANISM_REGRESSION_MEMO = (
    MECHANISM_REGRESSION_DIR / "import_gini_mechanism_regressions.md"
)
MECHANISM_REGRESSION_ADVERSARIAL = MECHANISM_REGRESSION_DIR / "adversarial_review.md"
INDUSTRIAL_POLICY_DIR = BASE / "industrial_policy_import_gini"
INDUSTRIAL_POLICY_MEMO = INDUSTRIAL_POLICY_DIR / "industrial_policy_import_gini.md"
INDUSTRIAL_POLICY_ADVERSARIAL = INDUSTRIAL_POLICY_DIR / "adversarial_review.md"
INDUSTRIAL_POLICY_MODEL_SUMMARY = INDUSTRIAL_POLICY_DIR / "model_summary.csv"
INDUSTRIAL_POLICY_TERMS = INDUSTRIAL_POLICY_DIR / "regression_terms.csv"
INDUSTRIAL_POLICY_EXPOSURE_SUMMARY = INDUSTRIAL_POLICY_DIR / "policy_exposure_summary.csv"
INDUSTRIAL_POLICY_FIG = INDUSTRIAL_POLICY_DIR / "figures" / "industrial_policy_import_gini_coefficients.png"


@dataclass(frozen=True)
class Source:
    label: str
    path: Path
    note: str


SOURCES = [
    Source(
        "Cadot, Carrere, and Strauss-Kahn paper notes",
        ROOT
        / "literature"
        / "export_margins"
        / "wiki"
        / "papers"
        / "06_cadot_carrere_strauss_kahn_2011_export_diversification_hump.md",
        "Local extracted paper notes used for Cadot's sample, estimator, robustness, decomposition, and old-cone interpretation.",
    ),
    Source(
        "Export margins study guide",
        ROOT / "literature" / "export_margins" / "project_study_guide.md",
        "Local cross-paper map used for other mechanisms in the export-margin literature.",
    ),
    Source(
        "Detailed export-margins notes",
        ROOT / "literature" / "export_margins" / "detailed_project_notes.md",
        "Local detailed synthesis for Cadot, BRS, Freund-Pierola, and related mechanisms.",
    ),
    Source(
        "Constant-PPP Cadot mechanism tribunal memo",
        BASE / "cadot_hump_tribunal.md",
        "rd2 mechanism tribunal rerun with World Bank constant-PPP GDP per capita as the headline income axis.",
    ),
    Source(
        "PPP hump regression memo",
        BASE / "ppp_hump_regressions.md",
        "Our World Bank constant-PPP GDP per capita rerun.",
    ),
    Source(
        "PPP microstate-exclusion robustness table",
        PPP_MICROSTATE,
        "Same PPP hump specification after excluding Iceland, Luxembourg, and Guyana.",
    ),
    Source(
        "PPP adversarial review",
        BASE / "ppp_hump_regression_adversarial_review.md",
        "Local trust review for the PPP regression implementation.",
    ),
    Source(
        "Referee 2 Cadot audit",
        ROOT
        / "correspondence"
        / "referee2"
        / "2026-05-30_round1_cadot_results_report.md",
        "Independent replication/audit notes on the Cadot PPP results and interpretation risk.",
    ),
    Source(
        "Cadot broad 156-country PPP memo",
        BROAD_MEMO,
        "Modern Cadot-comparable broad sample using 156 selected reporters and constant-PPP GDP per capita.",
    ),
    Source(
        "Cadot broad 156-country PPP regression summary",
        BROAD_SUMMARY,
        "Sixty-row modern broad PPP regression summary covering outcomes, estimators, income forms, turning points, support flags, and verdicts.",
    ),
    Source(
        "Cadot broad 156-country PPP attrition table",
        BROAD_ATTRITION,
        "Selected-reporter to complete-case regression attrition for each broad-sample outcome.",
    ),
    Source(
        "Cadot broad 156-country independent re-estimation checks",
        BROAD_INDEPENDENT_CHECKS,
        "Saved-panel re-estimation checks for one pooled model and one country-FE model.",
    ),
    Source(
        "Cadot broad 156-country diagnostics JSON",
        BROAD_DIAGNOSTICS,
        "Machine-readable broad PPP diagnostics, including sample support and validation metadata.",
    ),
    Source(
        "Cadot broad 156-country adversarial review",
        BROAD_REVIEW,
        "Trust review for the broad-sample PPP regressions, regression inputs, attrition, and interpretation caveats.",
    ),
    Source(
        "Cadot constant-PPP rerun adversarial review",
        CONSTANT_RERUN_REVIEW,
        "Local non-independent trust review for the constant-PPP rerun and remaining caveats.",
    ),
    Source(
        "Import concentration explanatory regressions",
        EXPLANATORY_MEMO,
        "Descriptive regressions for export scale/growth, PPP income, openness, and tariff/barrier proxies.",
    ),
    Source(
        "Import explanatory-regression adversarial review",
        EXPLANATORY_ADVERSARIAL,
        "Local trust review for the explanatory-regression implementation.",
    ),
    Source(
        "Ex-energy import concentration country wiki",
        COUNTRY_WIKI_README,
        "Index and summary table for the 56-country ex-energy import concentration wiki.",
    ),
    Source(
        "Country wiki synthesis",
        COUNTRY_WIKI_SYNTHESIS,
        "Holistic economist-council synthesis for the country driver groups.",
    ),
    Source(
        "Country wiki adversarial review",
        COUNTRY_WIKI_ADVERSARIAL,
        "Trust review and remaining caveats for the country wiki build.",
    ),
    Source(
        "Top-5 import concentration country wiki",
        TOP5_WIKI_README,
        "Index and summary table for the 56-country top-five import concentration wiki.",
    ),
    Source(
        "Top-5 country wiki synthesis",
        TOP5_WIKI_SYNTHESIS,
        "Economist-council synthesis of top-five import concentration mechanisms.",
    ),
    Source(
        "Top-5 country wiki adversarial review",
        TOP5_WIKI_ADVERSARIAL,
        "Trust review and remaining caveats for the top-five country wiki build.",
    ),
    Source(
        "Industrial policy and import Gini memo",
        INDUSTRIAL_POLICY_MEMO,
        "JLOP industrial-policy exposure test against rd2 ex-energy import Product Gini.",
    ),
    Source(
        "Industrial policy adversarial review",
        INDUSTRIAL_POLICY_ADVERSARIAL,
        "Trust review for the industrial-policy/import-Gini descriptive regressions.",
    ),
]


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing required artifact: {path}")
    return pd.read_csv(path)


def rel(path: Path) -> str:
    return path.relative_to(OUT.parent).as_posix()


def image_src(path: Path) -> str:
    """Embed figures so the standalone HTML survives being copied elsewhere."""
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def fmt_p(value: float | int | str | None) -> str:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return ""
    if pd.isna(x):
        return ""
    if x < 0.001:
        return "<0.001"
    return f"{x:.3f}"


def sig_class(value: float | int | str | None) -> str:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return ""
    if pd.isna(x):
        return ""
    return "sig" if x < 0.05 else ""


def fmt_money(value: float | int | str | None) -> str:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return ""
    if pd.isna(x):
        return ""
    sign = "-" if x < 0 else ""
    x = abs(x)
    if x >= 1e12:
        return f"{sign}${x:.2e}".replace("+", "")
    if x >= 1e6:
        return f"{sign}${x / 1e6:.1f}m"
    if x >= 1e3:
        return f"{sign}${x / 1e3:.1f}k"
    if x >= 1:
        return f"{sign}${x:,.0f}"
    return f"{sign}< $1"


def fmt_num(value: float | int | str | None, digits: int = 3) -> str:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return ""
    if pd.isna(x):
        return ""
    return f"{x:.{digits}f}"


def clean_cell(value: object, fallback: str = "none") -> str:
    if value is None:
        return fallback
    if isinstance(value, float) and pd.isna(value):
        return fallback
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return fallback
    return text


def pct(value: float | int | str | None) -> str:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return ""
    if pd.isna(x):
        return ""
    return f"{100 * x:.1f}%"


def tag(text: str, kind: str = "") -> str:
    cls = f' class="tag {kind}"' if kind else ' class="tag"'
    return f"<span{cls}>{escape(text)}</span>"


def table(headers: list[str], rows: Iterable[Iterable[str]], cls: str = "") -> str:
    class_attr = f' class="{cls}"' if cls else ""
    head = "".join(f"<th>{escape(h)}</th>" for h in headers)
    body = []
    for row in rows:
        cells = []
        for item in row:
            cells.append(f"<td>{item}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return (
        f'<div class="table-wrap"><table{class_attr}><thead><tr>{head}</tr></thead>'
        f"<tbody>{''.join(body)}</tbody></table></div>"
    )


def markdown_inline(text: str) -> str:
    out = escape(text)
    out = re.sub(
        r"`([^`]+)`",
        lambda m: f"<code>{m.group(1)}</code>",
        out,
    )
    out = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: f'<a href="{escape(m.group(2), quote=True)}">{m.group(1)}</a>',
        out,
    )
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    return out


def markdown_table(lines: list[str]) -> str:
    rows = []
    for line in lines:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        rows.append(cells)
    headers = rows[0]
    body_rows = rows[2:]
    head = "".join(f"<th>{markdown_inline(cell)}</th>" for cell in headers)
    body = []
    for row in body_rows:
        body.append(
            "<tr>"
            + "".join(f"<td>{markdown_inline(cell)}</td>" for cell in row)
            + "</tr>"
        )
    return (
        '<div class="table-wrap wiki-table"><table><thead><tr>'
        + head
        + "</tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table></div>"
    )


def markdown_to_html(markdown: str) -> str:
    lines = markdown.splitlines()
    html: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-{3,}", lines[i + 1]):
            table_lines = [stripped]
            i += 1
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i].strip())
                i += 1
            html.append(markdown_table(table_lines))
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            level = min(len(heading.group(1)) + 2, 6)
            html.append(f"<h{level}>{markdown_inline(heading.group(2))}</h{level}>")
            i += 1
            continue
        if stripped.startswith(">"):
            quote_lines = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote_lines.append(lines[i].strip().lstrip(">").strip())
                i += 1
            html.append(
                "<blockquote>"
                + "".join(f"<p>{markdown_inline(q)}</p>" for q in quote_lines if q)
                + "</blockquote>"
            )
            continue
        if stripped.startswith("- "):
            items = []
            while i < len(lines) and lines[i].strip().startswith("- "):
                items.append(lines[i].strip()[2:].strip())
                i += 1
            html.append("<ul>" + "".join(f"<li>{markdown_inline(item)}</li>" for item in items) + "</ul>")
            continue
        if re.match(r"^\d+\.\s+", stripped):
            items = []
            while i < len(lines) and re.match(r"^\d+\.\s+", lines[i].strip()):
                items.append(re.sub(r"^\d+\.\s+", "", lines[i].strip()))
                i += 1
            html.append("<ol>" + "".join(f"<li>{markdown_inline(item)}</li>" for item in items) + "</ol>")
            continue
        paragraph = [stripped]
        i += 1
        while i < len(lines):
            nxt = lines[i].strip()
            if not nxt or nxt.startswith("#") or nxt.startswith("|") or nxt.startswith("- ") or nxt.startswith(">") or re.match(r"^\d+\.\s+", nxt):
                break
            paragraph.append(nxt)
            i += 1
        html.append(f"<p>{markdown_inline(' '.join(paragraph))}</p>")
    return "\n".join(html)


def wiki_doc(path: Path, label: str, open_doc: bool = False) -> str:
    attr = " open" if open_doc else ""
    return (
        f'<details class="wiki-doc"{attr}>'
        f"<summary>{escape(label)}</summary>"
        f'<div class="wiki-md">{markdown_to_html(path.read_text(encoding="utf-8"))}</div>'
        "</details>"
    )


def cadot_tribunal_constant_ppp_table() -> str:
    df = read_csv(TRIBUNAL_MODELS)
    term_col = "log_income_pc_sq" if "log_income_pc_sq" in set(df["term"].astype(str)) else "log_gni_pc_sq"
    tp_col = (
        "turning_point_ppp_constant_2021_intl_usd"
        if "turning_point_ppp_constant_2021_intl_usd" in df.columns
        else "turning_point_gni_pc_current_usd"
    )
    labels = {
        "standard_product_gini": "Export Product Gini",
        "world_relative_product_gini": "Export World-Relative Product Gini",
        "log_active_product_count": "Log active export products",
        "top_product_1pct_share": "Top 1% product share",
        "top_product_partner_cell_1pct_share": "Top 1% product-partner cell share",
    }
    df = df[
        df["model_label"].eq("quadratic_controls_year_fe_country_cluster")
        & df["term"].astype(str).eq(term_col)
    ].copy()
    rows = []
    for _, r in df.iterrows():
        p = r["p_value"]
        sign = "+" if r["coefficient"] > 0 else "-"
        verdict = "Clear U-shape" if (
            r["coefficient"] > 0
            and p < 0.05
            and pd.notna(r.get(tp_col))
        ) else "No clean U-shape"
        rows.append(
            [
                escape(labels.get(r["metric"], r["metric"])),
                escape(str(r["flow"])),
                f'<span class="{sig_class(p)}">{sign}, p={fmt_p(p)}</span>',
                escape(fmt_money(r.get(tp_col))),
                escape(str(int(r["nobs"])) if pd.notna(r.get("nobs")) else ""),
                escape(str(int(r["clusters"])) if pd.notna(r.get("clusters")) else ""),
                escape(verdict),
            ]
        )
    return table(
        [
            "Outcome",
            "Flow",
            "Quadratic sign and p",
            "Turning point, constant PPP",
            "Rows",
            "Clusters",
            "Read",
        ],
        rows,
    )


def broad_sort_key(df: pd.DataFrame) -> pd.DataFrame:
    outcome_order = {
        "export_product_gini": 0,
        "export_product_theil": 1,
        "export_product_hhi": 2,
        "export_active_product_count": 3,
        "import_product_gini": 4,
        "import_product_theil": 5,
        "import_product_hhi": 6,
        "import_active_product_count": 7,
        "export_partner_gini": 8,
        "import_partner_gini": 9,
    }
    income_order = {"level_ppp": 0, "log_ppp": 1}
    estimator_order = {
        "pooled_year_fe": 0,
        "country_year_fe": 1,
        "between_country": 2,
    }
    out = df.copy()
    out["_outcome_order"] = out["outcome_slug"].map(outcome_order).fillna(99)
    out["_income_order"] = out["income_form"].map(income_order).fillna(99)
    out["_estimator_order"] = out["estimator"].map(estimator_order).fillna(99)
    return out.sort_values(["_outcome_order", "_income_order", "_estimator_order"])


def broad_regression_rows(df: pd.DataFrame) -> list[list[str]]:
    rows = []
    for _, r in df.iterrows():
        p = r["quadratic_p_value"]
        sign = "+" if r["quadratic_coefficient"] > 0 else "-"
        rows.append(
            [
                escape(str(r["outcome_label"])),
                escape(str(r["flow"])),
                escape(
                    {
                        "pooled_year_fe": "pooled/year FE",
                        "country_year_fe": "country + year FE",
                        "between_country": "between countries",
                    }.get(str(r["estimator"]), str(r["estimator"]))
                ),
                escape("level PPP" if r["income_form"] == "level_ppp" else "log PPP"),
                f'<span class="{sig_class(p)}">{sign}, p={fmt_p(p)}</span>',
                escape(fmt_money(r["turning_point_ppp_constant_2021_intl_usd"])),
                escape("yes" if r["turning_point_inside_p05_p95"] else "no"),
                escape(str(int(r["nobs"]))),
                escape(str(int(r["clusters"]))),
                escape(str(r["verdict"])),
            ]
        )
    return rows


def broad_pooled_headline_table() -> str:
    df = read_csv(BROAD_SUMMARY)
    df = df[df["estimator"].astype(str).eq("pooled_year_fe")].copy()
    df = broad_sort_key(df)
    return table(
        [
            "Outcome",
            "Flow",
            "Estimator",
            "Income form",
            "Quadratic sign and p",
            "Turning point",
            "Inside p05-p95 support",
            "Rows",
            "Clusters",
            "Verdict",
        ],
        broad_regression_rows(df),
    )


def broad_estimator_stress_table() -> str:
    df = read_csv(BROAD_SUMMARY)
    keep = {
        "export_product_gini",
        "export_product_theil",
        "import_product_gini",
        "import_product_theil",
        "export_partner_gini",
        "import_partner_gini",
    }
    df = df[
        df["income_form"].astype(str).eq("level_ppp")
        & df["outcome_slug"].astype(str).isin(keep)
    ].copy()
    df = broad_sort_key(df)
    return table(
        [
            "Outcome",
            "Flow",
            "Estimator",
            "Income form",
            "Quadratic sign and p",
            "Turning point",
            "Inside p05-p95 support",
            "Rows",
            "Clusters",
            "Verdict",
        ],
        broad_regression_rows(df),
    )


def broad_attrition_table() -> str:
    df = read_csv(BROAD_ATTRITION)
    rows = []
    for _, r in df.iterrows():
        rows.append(
            [
                escape(str(r["outcome_slug"]).replace("_", " ")),
                escape(str(int(r["selected_reporters"]))),
                escape(str(int(r["source_countries"]))),
                escape(str(int(r["analytic_rows_after_balance"]))),
                escape(str(int(r["analytic_countries_after_balance"]))),
                escape(str(int(r["analytic_clusters_after_balance"]))),
                escape(str(int(r["missing_population_rows"]))),
                escape(str(int(r["missing_ppp_rows"]))),
            ]
        )
    return table(
        [
            "Outcome",
            "Selected reporters",
            "Source countries",
            "Analytic rows",
            "Analytic countries",
            "Clusters",
            "Missing population rows",
            "Missing PPP rows",
        ],
        rows,
    )


def broad_reestimate_table() -> str:
    df = read_csv(BROAD_INDEPENDENT_CHECKS)
    df["_passed_bool"] = df["passed"].astype(str).str.lower().isin(["true", "1", "yes"])
    grouped = (
        df.groupby("check", as_index=False)
        .agg(
            terms=("term", "size"),
            max_coefficient_diff=("abs_coefficient_diff", "max"),
            max_std_error_diff=("abs_std_error_diff", "max"),
            nobs=("nobs", "max"),
            clusters=("clusters", "max"),
            passed=("_passed_bool", "all"),
        )
        .sort_values("check")
    )
    rows = []
    for _, r in grouped.iterrows():
        rows.append(
            [
                escape(str(r["check"]).replace("_", " ")),
                escape(str(int(r["terms"]))),
                escape(f"{float(r['max_coefficient_diff']):.2e}"),
                escape(f"{float(r['max_std_error_diff']):.2e}"),
                escape(str(int(r["nobs"]))),
                escape(str(int(r["clusters"]))),
                escape("passed" if bool(r["passed"]) else "failed"),
            ]
        )
    return table(
        [
            "Saved-panel check",
            "Terms",
            "Max coefficient difference",
            "Max SE difference",
            "Rows",
            "Clusters",
            "Status",
        ],
        rows,
    )


def ppp_main_table() -> str:
    df = read_csv(PPP_SUMMARY)
    rows = []
    for _, r in df.iterrows():
        p = r["quadratic_p_value"]
        sign = "+" if r["quadratic_coefficient"] > 0 else "-"
        rows.append(
            [
                escape(str(r["outcome_label"])),
                escape(str(r["flow"])),
                escape("level PPP" if r["income_form"] == "level_ppp" else "log PPP"),
                f'<span class="{sig_class(p)}">{sign}, p={fmt_p(p)}</span>',
                escape(fmt_money(r["turning_point_ppp_constant_2021_intl_usd"])),
                escape("yes" if r["turning_point_inside_p05_p95"] else "no"),
                escape(str(r["verdict"])),
            ]
        )
    return table(
        [
            "Outcome",
            "Flow",
            "Income form",
            "Quadratic sign and p",
            "Turning point",
            "Inside p05-p95 support",
            "Verdict",
        ],
        rows,
    )


def ppp_fe_table() -> str:
    df = read_csv(PPP_FE)
    df = df[df["specification"].isin(["pooled_year_fe", "country_year_fe"])].copy()
    rows = []
    for _, r in df.iterrows():
        p = r["quadratic_p_value"]
        sign = "+" if r["quadratic_coefficient"] > 0 else "-"
        rows.append(
            [
                escape(str(r["outcome_label"])),
                escape("level PPP" if r["income_form"] == "level_ppp" else "log PPP"),
                escape(
                    "pooled/year FE"
                    if r["specification"] == "pooled_year_fe"
                    else "country + year FE"
                ),
                f'<span class="{sig_class(p)}">{sign}, p={fmt_p(p)}</span>',
                escape(fmt_money(r["turning_point_ppp_constant_2021_intl_usd"])),
                escape("yes" if r["turning_point_inside_p05_p95"] else "no"),
            ]
        )
    return table(
        [
            "Outcome",
            "Income form",
            "Specification",
            "Quadratic sign and p",
            "Turning point",
            "Inside p05-p95 support",
        ],
        rows,
    )


def ppp_microstate_table() -> str:
    if not PPP_MICROSTATE.exists():
        return (
            '<div class="callout warning">'
            "<p><strong>Microstate robustness artifact missing:</strong> "
            f"{escape(PPP_MICROSTATE.relative_to(ROOT).as_posix())} is not present in this checkout, "
            "so the table is omitted rather than rebuilt implicitly.</p>"
            "</div>"
        )
    base = read_csv(PPP_SUMMARY)
    no3 = read_csv(PPP_MICROSTATE)
    merged = base.merge(
        no3,
        on=["outcome_slug", "income_form"],
        suffixes=("_base", "_no3"),
        validate="one_to_one",
    )
    rows = []
    for _, r in merged.iterrows():
        base_p = r["quadratic_p_value_base"]
        no3_p = r["quadratic_p_value_no3"]
        base_sign = "+" if r["quadratic_coefficient_base"] > 0 else "-"
        no3_sign = "+" if r["quadratic_coefficient_no3"] > 0 else "-"
        changed = str(r["verdict_base"]) != str(r["verdict_no3"])
        rows.append(
            [
                escape(str(r["outcome_label_base"])),
                escape("level PPP" if r["income_form"] == "level_ppp" else "log PPP"),
                f"{escape(base_sign)}, p={escape(fmt_p(base_p))}; TP {escape(fmt_money(r['turning_point_ppp_constant_2021_intl_usd_base']))}; {escape(str(r['verdict_base']))}",
                f"{escape(no3_sign)}, p={escape(fmt_p(no3_p))}; TP {escape(fmt_money(r['turning_point_ppp_constant_2021_intl_usd_no3']))}; {escape(str(r['verdict_no3']))}",
                escape("yes" if changed else "no"),
            ]
        )
    return table(
        [
            "Outcome",
            "Income form",
            "Original 55 countries",
            "Excluding Iceland, Luxembourg, Guyana",
            "Verdict changed?",
        ],
        rows,
    )


def mechanism_method_table() -> str:
    return table(
        ["Flag", "Rule used in the scorecard", "Plain-English read"],
        [
            [
                "Reconcentration episode",
                "World-relative product Gini rises over a 5-year country window.",
                "The country becomes more concentrated relative to the world product distribution.",
            ],
            [
                "Commodity spike",
                "Commodity share removed >= 20%, or oil export share >= 25%, or commodity exclusion lowers product Gini by >= 0.05.",
                "The concentration rise may be commodity-price or commodity-basket driven.",
            ],
            [
                "Section 16 sensitivity",
                "Dropping HS2 84/85 changes product Gini by >= 0.03, or Section 16 is >= 30% of exports.",
                "Machinery/electrical classification may mechanically affect measured product concentration.",
            ],
            [
                "Old-cone pruning",
                "Rich-side country, dying products are more mismatched than continuing products, and dying products explain > 5% of contraction.",
                "This is the closest proxy for Cadot's rich countries dropping old comparative-advantage products.",
            ],
            [
                "Continuing-product scaling",
                "Continuing products explain >= 75% of positive expansion and top-product share rises.",
                "Existing products scale unevenly; this is a product-level proxy, not direct firm-level evidence.",
            ],
            [
                "Broad unexplained",
                "Reconcentration episode with none of the named flags.",
                "The episode needs a different mechanism or finer data.",
            ],
        ],
    )


def import_u_shape_table() -> str:
    return table(
        ["Development stage", "Import concentration interpretation", "Council caution"],
        [
            [
                "Low income",
                "Imports can be concentrated in essentials: fuels, food, medicines, basic manufactures, and a few capital goods.",
                "Narrow imports may reflect limited demand and limited production capacity.",
            ],
            [
                "Middle income",
                "Imports diversify as countries build factories, infrastructure, retail systems, and broader consumer markets.",
                "This is not Cadot's export old-cone mechanism; it is import-basket broadening.",
            ],
            [
                "High income",
                "Imports may reconcentrate around specialized supply-chain inputs, energy, electronics, machinery, pharma, autos, or a few large sectors.",
                "Could be productive specialization, commodity exposure, or top-firm/top-sector scaling.",
            ],
        ],
    )


def explanatory_hypothesis_table() -> str:
    return table(
        ["Hypothesis", "Data used", "Regression structure", "Interpretation standard"],
        [
            [
                "Export level",
                "Main: nominal Comtrade merchandise exports, logged. Robustness: WDI real goods-and-services exports.",
                "Country-change OLS and annual panel FE.",
                "Does larger export scale predict higher ex-energy import concentration?",
            ],
            [
                "Export growth",
                "Main: 2000-2024 log change in nominal Comtrade merchandise exports. Robustness: WDI real export growth.",
                "Country-change OLS and first-difference panel.",
                "Does export expansion bring imported-input specialization or broader baskets?",
            ],
            [
                "Per-capita income level",
                "World Bank constant PPP GDP per capita.",
                "Country-change OLS and annual panel FE.",
                "Does development stage explain concentration after export scale and openness?",
            ],
            [
                "Per-capita income growth",
                "2000-2024 log change in PPP GDP per capita; annual log changes in panel checks.",
                "Country-change OLS and first-difference panel.",
                "Does getting richer over the sample correspond to concentration change?",
            ],
            [
                "Trade openness",
                "Main: merchandise openness = 100 * (Comtrade imports + exports) / WDI current GDP. Robustness: WDI goods-and-services openness.",
                "Country-change OLS, country/year FE panel, first differences.",
                "Does integration with trade flows correspond to concentration?",
            ],
            [
                "Trade barriers",
                "World Bank weighted mean applied tariff. WITS HS4 market-access tariffs were not used as main domestic import barriers.",
                "Reduced-sample tariff robustness.",
                "Do broad tariff barriers add explanatory power beyond openness and macro controls?",
            ],
        ],
    )


def explanatory_model_table() -> str:
    df = read_csv(EXPLANATORY_SUMMARY)
    keep_order = [
        "xs_exports",
        "xs_real_exports",
        "xs_income",
        "xs_openness",
        "xs_full",
        "xs_full_real_exports",
        "xs_full_no_microstates",
        "xs_full_no_logistics_hubs",
        "xs_full_wdi_openness",
        "xs_per_capita_export_robust",
        "xs_tariff_robust",
        "xs_increase_lpm",
        "panel_pooled_year_fe",
        "panel_country_year_fe",
        "panel_country_year_fe_real_exports",
        "panel_country_year_fe_no_logistics_hubs",
        "panel_country_year_fe_wdi_openness",
        "panel_annual_changes",
        "panel_annual_changes_real_exports",
        "panel_lagged_annual_changes",
        "panel_lagged_annual_changes_real_exports",
        "panel_tariff_country_year_fe",
    ]
    df["order"] = df["model_id"].map({model: i for i, model in enumerate(keep_order)})
    df = df.sort_values("order")
    terms = read_csv(EXPLANATORY_TERMS)
    rows = []
    for _, r in df.iterrows():
        sig_terms = terms[
            terms["model_id"].eq(r["model_id"]) & terms["p_value"].lt(0.05)
        ]["term"].tolist()
        rows.append(
            [
                escape(str(r["model_id"])),
                escape(str(r["family"])),
                escape(f"{int(r['nobs']):,}"),
                escape(f"{int(r['entities']):,}"),
                escape(fmt_num(r["rsquared"], 3)),
                escape(", ".join(sig_terms) if sig_terms else "none"),
            ]
        )
    return table(["Model", "Family", "N", "Countries", "R2", "p < 0.05 terms"], rows)


def explanatory_selected_terms_table() -> str:
    terms = read_csv(EXPLANATORY_TERMS)
    model_order = {
        "xs_full": 0,
        "xs_full_real_exports": 1,
        "xs_full_no_logistics_hubs": 2,
        "xs_full_wdi_openness": 3,
        "panel_country_year_fe": 4,
        "panel_country_year_fe_real_exports": 5,
        "panel_country_year_fe_no_logistics_hubs": 6,
        "panel_country_year_fe_wdi_openness": 7,
        "panel_annual_changes": 8,
        "panel_annual_changes_real_exports": 9,
        "panel_lagged_annual_changes": 10,
        "panel_lagged_annual_changes_real_exports": 11,
        "panel_tariff_country_year_fe": 12,
    }
    term_labels = {
        "log_goods_exports_2000": "Initial export level",
        "goods_export_growth_2000_2024": "Export growth",
        "log_real_exports_2000": "Initial real exports",
        "real_export_growth_2000_2024": "Real export growth",
        "log_gdp_pc_ppp_2000": "Initial PPP GDPpc",
        "gdp_pc_ppp_growth_2000_2024": "PPP GDPpc growth",
        "trade_openness_pct_gdp_2000": "Initial merchandise openness",
        "trade_openness_change_2000_2024": "Merchandise openness change",
        "wdi_goods_services_trade_openness_pct_gdp_2000": "Initial WDI openness",
        "wdi_goods_services_trade_openness_change_2000_2024": "WDI openness change",
        "log_goods_exports_current_usd": "Export level",
        "log_real_exports_goods_services_constant_2015_usd": "Real exports",
        "log_gdp_pc_ppp_constant_2021_intl_usd": "PPP GDPpc",
        "trade_openness_pct_gdp": "Merchandise openness",
        "wdi_goods_services_trade_openness_pct_gdp": "WDI openness",
        "d_log_goods_exports_current_usd": "Annual export growth",
        "d_log_real_exports_goods_services_constant_2015_usd": "Annual real export growth",
        "d_log_gdp_pc_ppp_constant_2021_intl_usd": "Annual PPP GDPpc growth",
        "d_trade_openness_pct_gdp": "Annual openness change",
        "l1_d_log_goods_exports_current_usd": "Lagged annual export growth",
        "l1_d_log_real_exports_goods_services_constant_2015_usd": "Lagged annual real export growth",
        "l1_d_log_gdp_pc_ppp_constant_2021_intl_usd": "Lagged annual PPP GDPpc growth",
        "l1_d_trade_openness_pct_gdp": "Lagged annual openness change",
        "tariff_applied_weighted_mean_pct": "Applied tariff",
    }
    terms = terms[terms["model_id"].isin(model_order) & terms["term"].isin(term_labels)].copy()
    terms["model_order"] = terms["model_id"].map(model_order)
    terms["term_label"] = terms["term"].map(term_labels)
    terms = terms.sort_values(["model_order", "term_label"])
    rows = []
    for _, r in terms.iterrows():
        p = r["p_value"]
        coef = fmt_num(r["coef"], 4)
        rows.append(
            [
                escape(str(r["model_id"])),
                escape(str(r["term_label"])),
                f'<span class="{sig_class(p)}">{escape(coef)}</span>',
                escape(fmt_num(r["std_error"], 4)),
                f'<span class="{sig_class(p)}">{escape(fmt_p(p))}</span>',
            ]
        )
    return table(["Model", "Term", "Coef", "SE", "p"], rows)


def explanatory_diagnostics_table() -> str:
    df = read_csv(EXPLANATORY_DIAGNOSTICS)
    labels = {
        "classification_countries": "Balanced classification countries",
        "panel_rows": "Annual panel rows",
        "panel_countries": "Annual panel countries",
        "panel_year_min": "Panel first year",
        "panel_year_max": "Panel last year",
        "country_change_rows": "Country-change rows",
        "panel_nonmissing_ex_energy_import_product_gini": "Nonmissing annual outcome rows",
        "panel_nonmissing_goods_exports_current_usd": "Nonmissing merchandise export rows",
        "panel_nonmissing_gdp_pc_ppp_constant_2021_intl_usd": "Nonmissing PPP GDPpc rows",
        "panel_nonmissing_trade_openness_pct_gdp": "Nonmissing merchandise openness rows",
        "panel_nonmissing_tariff_applied_weighted_mean_pct": "Nonmissing tariff rows",
        "tariff_country_change_complete_rows": "Country-change rows with tariff endpoints",
    }
    df = df[df["diagnostic"].isin(labels)].copy()
    rows = [
        [escape(labels.get(str(r["diagnostic"]), str(r["diagnostic"]))), escape(str(int(r["value"])))]
        for _, r in df.iterrows()
    ]
    return table(["Diagnostic", "Value"], rows)


def explanatory_influence_table() -> str:
    df = read_csv(EXPLANATORY_INFLUENCE)
    df = df[df["omitted_iso3"].ne("FULL") & df["status"].eq("ok")].copy()
    if "significant_05" in df.columns:
        sig = df["significant_05"].astype(str).str.lower().isin(["true", "1"])
        df = df[~sig].copy()
    df = df.sort_values(["model_id", "p_value"])
    rows = []
    for _, r in df.iterrows():
        rows.append(
            [
                escape(str(r["model_id"])),
                escape(f"{r['omitted_country']} ({r['omitted_iso3']})"),
                escape(fmt_num(r["coef"], 4)),
                escape(fmt_num(r["std_error"], 4)),
                escape(fmt_p(r["p_value"])),
            ]
        )
    if not rows:
        rows = [["none", "none", "", "", ""]]
    return table(["Model", "Omitted Country", "Coef", "SE", "p"], rows)


def explanatory_sample_manifest_table() -> str:
    df = read_csv(EXPLANATORY_SAMPLE_MANIFEST)
    df = df[pd.to_numeric(df["dropped_rows"], errors="coerce").fillna(0).gt(0)].copy()
    df = df.sort_values(["model_id"])
    rows = []
    for _, r in df.iterrows():
        rows.append(
            [
                escape(str(r["model_id"])),
                escape(f"{int(r['complete_rows']):,} / {int(r['input_rows']):,}"),
                escape(f"{int(r['complete_countries']):,}"),
                escape(f"{int(r['dropped_rows']):,}"),
                escape(clean_cell(r.get("excluded_countries"))),
                escape(clean_cell(r.get("missing_columns_summary"))),
            ]
        )
    if not rows:
        rows = [["none", "", "", "", "", ""]]
    return table(["Model", "Complete Rows", "Countries", "Dropped Rows", "Excluded Countries", "Missing Columns"], rows)


def explanatory_tariff_endpoint_table() -> str:
    df = read_csv(EXPLANATORY_TARIFF_ENDPOINTS)
    complete = df.dropna(subset=["tariff_end_year"]).copy()
    rows = []
    if not complete.empty:
        for year, count in complete["tariff_end_year"].astype(int).value_counts().sort_index().items():
            rows.append([escape(str(year)), escape(f"{int(count):,}")])
    missing = int(df["tariff_end_year"].isna().sum())
    if missing:
        rows.append(["missing endpoint", escape(f"{missing:,}")])
    return table(["Tariff End Year Used", "Countries"], rows)


def mechanism_table() -> str:
    df = read_csv(MECHANISM)
    priority = [
        "continuing_product_superstar_scaling",
        "commodity_spike",
        "section16_hs_design_sensitive",
        "old_cone_pruning",
        "broad_unexplained_reconcentration",
        "new_product_net_growth_share",
        "continuing_product_net_growth_share",
        "dying_product_net_growth_share",
    ]
    df = df[df["mechanism"].isin(priority)].copy()
    df["order"] = df["mechanism"].map({m: i for i, m in enumerate(priority)})
    df = df.sort_values("order")
    labels = {
        "continuing_product_superstar_scaling": "Continuing-product scaling",
        "commodity_spike": "Commodity spike",
        "section16_hs_design_sensitive": "HS Section 16 sensitivity",
        "old_cone_pruning": "Old-cone pruning",
        "broad_unexplained_reconcentration": "Broad unexplained reconcentration",
        "new_product_net_growth_share": "New products: share of net growth",
        "continuing_product_net_growth_share": "Continuing products: share of net growth",
        "dying_product_net_growth_share": "Dying products: share of net growth",
    }
    explanations = {
        "continuing_product_superstar_scaling": "Existing products grow unevenly; concentration rises because incumbents scale.",
        "commodity_spike": "A commodity-heavy episode may be driven by price/value shocks.",
        "section16_hs_design_sensitive": "Machinery/electrical HS design may affect line counts and measured concentration.",
        "old_cone_pruning": "Exited products look far from the country's income/endowment position.",
        "broad_unexplained_reconcentration": "Rising concentration not captured by the named flags.",
        "new_product_net_growth_share": "New products explain little net growth in reconcentration episodes.",
        "continuing_product_net_growth_share": "Continuing products explain nearly all net growth.",
        "dying_product_net_growth_share": "Exited products are a small negative net-growth component.",
    }
    rows = []
    for _, r in df.iterrows():
        mech = str(r["mechanism"])
        flagged = r["flagged_episodes"]
        rows.append(
            [
                escape(labels.get(mech, mech)),
                escape(explanations.get(mech, "")),
                escape(
                    ""
                    if pd.isna(flagged)
                    else f"{int(flagged):,} / {int(r['reconcentration_episodes']):,}"
                ),
                escape(pct(r["flagged_share"])),
            ]
        )
    return table(["Mechanism", "Plain-English meaning", "Flagged episodes", "Share"], rows)


def old_cone_table() -> str:
    df = read_csv(OLD_CONE)
    rows = []
    labels = {
        "mismatch_log_gni_minus_prody": "Mismatch: country income minus product PRODY",
        "rich_side_ct": "Rich-side episode indicator",
        "mismatch_x_rich_side": "Mismatch x rich-side interaction",
    }
    for _, r in df.iterrows():
        p = r["p_value"]
        rows.append(
            [
                escape(labels.get(str(r["term"]), str(r["term"]))),
                f'<span class="{sig_class(p)}">{fmt_num(r["coef"], 4)}</span>',
                escape(fmt_num(r["std_error"], 4)),
                f'<span class="{sig_class(p)}">{fmt_p(p)}</span>',
                escape(f"{int(r['nobs']):,}"),
        ]
    )
    return table(["Term", "Coefficient", "SE", "p-value", "N"], rows)


def country_wiki_index_table() -> str:
    df = read_csv(COUNTRY_WIKI_INDEX)
    rows = []
    for (direction, group), sub in df.groupby(["gini_change_direction", "main_driver_group"], sort=True):
        countries = ", ".join(sorted(sub["country"].astype(str)))
        rows.append(
            [
                escape(str(direction)),
                escape(str(group)),
                escape(f"{len(sub):,}"),
                escape(fmt_num(sub["delta_panel_ex_energy_gini"].median(), 4)),
                escape(countries),
            ]
        )
    return table(["Direction", "Driver Group", "Countries", "Median Delta Gini", "Country List"], rows)


def country_wiki_browser() -> str:
    df = read_csv(COUNTRY_WIKI_INDEX).sort_values(["main_driver_group", "country"]).copy()
    if df.empty:
        raise RuntimeError("Country wiki index is empty")
    df["country_id"] = df["wiki_file"].map(lambda x: Path(str(x)).stem)
    default_id = "germany" if "germany" in set(df["country_id"]) else str(df.iloc[0]["country_id"])
    options = []
    articles = []
    for _, r in df.iterrows():
        country_id = str(r["country_id"])
        path = COUNTRY_WIKI_DIR / str(r["wiki_file"])
        if not path.exists():
            raise FileNotFoundError(path)
        label = f"{r['country']} ({r['iso3']}) - {r['main_driver_group']}"
        selected = " selected" if country_id == default_id else ""
        options.append(f'<option value="{escape(country_id)}"{selected}>{escape(label)}</option>')
        active = " active" if country_id == default_id else ""
        articles.append(
            f'<article class="country-article{active}" '
            f'data-country-id="{escape(country_id)}" '
            f'data-country="{escape(str(r["country"]))}" '
            f'data-iso3="{escape(str(r["iso3"]))}" '
            f'data-group="{escape(str(r["main_driver_group"]))}" '
            f'data-direction="{escape(str(r["gini_change_direction"]))}" '
            f'data-delta="{escape(fmt_num(r["delta_panel_ex_energy_gini"], 4))}">'
            f'{markdown_to_html(path.read_text(encoding="utf-8"))}'
            "</article>"
        )
    return f"""
    <div class="country-picker">
      <label for="countryWikiSelect">Country file</label>
      <select id="countryWikiSelect">
        {''.join(options)}
      </select>
      <p id="countryWikiMeta" class="muted"></p>
    </div>
    <div id="countryWikiArticles" class="country-articles">
      {''.join(articles)}
    </div>
    <script>
      (function() {{
        const select = document.getElementById("countryWikiSelect");
        const meta = document.getElementById("countryWikiMeta");
        const root = document.getElementById("countryWikiArticles");
        const articles = Array.from(root.querySelectorAll(".country-article"));
        function updateCountryArticle() {{
          const active = articles.find((article) => article.dataset.countryId === select.value);
          articles.forEach((article) => article.classList.toggle("active", article === active));
          if (active) {{
            meta.textContent = active.dataset.country + " (" + active.dataset.iso3 + ") | "
              + active.dataset.direction + " | " + active.dataset.group
              + " | delta Gini " + active.dataset.delta;
          }}
        }}
        select.addEventListener("change", updateCountryArticle);
        updateCountryArticle();
      }})();
    </script>
    """


def country_wiki_section() -> str:
    required = [
        COUNTRY_WIKI_README,
        COUNTRY_WIKI_SYNTHESIS,
        COUNTRY_WIKI_GROUP_MEMOS,
        COUNTRY_WIKI_METHOD,
        COUNTRY_WIKI_SOURCES,
        COUNTRY_WIKI_ADVERSARIAL,
        COUNTRY_WIKI_INDEX,
    ]
    missing = missing_section("country-wiki", "Country Wiki: Ex-Energy Import Concentration", required)
    if missing:
        return missing
    return f"""
<section id="country-wiki">
  <div class="wrap">
    <h2>Country Wiki: Ex-Energy Import Concentration</h2>
    <p>This pulls the country wiki into the explainer so you can read the mechanism taxonomy without leaving the page. The wiki explains why each balanced 2000-2024 rd2 country was assigned to its energy-excluded import Product Gini driver group.</p>
    <div class="callout warning">
      <p><strong>Read this as mechanism diagnosis, not causal proof.</strong> The country files combine local product-rank evidence with plausible economic history. Historical and policy hooks still need country-specific source verification before they become paper claims.</p>
    </div>
    <h3>Driver-Group Index</h3>
    {country_wiki_index_table()}
    <h3>Core Wiki Notes</h3>
    <div class="wiki-docs">
      {wiki_doc(COUNTRY_WIKI_SYNTHESIS, "Synthesis", open_doc=True)}
      {wiki_doc(COUNTRY_WIKI_GROUP_MEMOS, "Group Memos")}
      {wiki_doc(COUNTRY_WIKI_METHOD, "Method Note")}
      {wiki_doc(COUNTRY_WIKI_SOURCES, "Sources To Check")}
      {wiki_doc(COUNTRY_WIKI_ADVERSARIAL, "Adversarial Review")}
    </div>
    <h3>Country Files</h3>
    {country_wiki_browser()}
  </div>
</section>
"""


def top5_wiki_index_table() -> str:
    df = read_csv(TOP5_WIKI_INDEX)
    rows = []
    for (role, family), sub in df.groupby(["top5_role", "mechanism_family"], sort=True):
        countries = ", ".join(sorted(sub["country"].astype(str)))
        rows.append(
            [
                escape(str(role)),
                escape(str(family)),
                escape(f"{len(sub):,}"),
                escape(pct(sub["delta_top5_share"].median())),
                escape(pct(sub["delta_panel_ex_energy_gini"].median())),
                escape(countries),
            ]
        )
    return table(
        [
            "Top-5 Role",
            "Mechanism Family",
            "Countries",
            "Median Delta Top-5 Share",
            "Median Delta Gini",
            "Country List",
        ],
        rows,
    )


def top5_country_wiki_browser() -> str:
    df = read_csv(TOP5_WIKI_INDEX).sort_values(["top5_role", "mechanism_family", "country"]).copy()
    if df.empty:
        raise RuntimeError("Top-5 country wiki index is empty")
    df["country_id"] = df["wiki_file"].map(lambda x: Path(str(x)).stem)
    default_id = "slovenia" if "slovenia" in set(df["country_id"]) else str(df.iloc[0]["country_id"])
    options = []
    articles = []
    for _, r in df.iterrows():
        country_id = str(r["country_id"])
        path = TOP5_WIKI_DIR / str(r["wiki_file"])
        if not path.exists():
            raise FileNotFoundError(path)
        label = f"{r['country']} ({r['iso3']}) - {r['top5_role']} - {r['mechanism_family']}"
        selected = " selected" if country_id == default_id else ""
        options.append(f'<option value="{escape(country_id)}"{selected}>{escape(label)}</option>')
        active = " active" if country_id == default_id else ""
        articles.append(
            f'<article class="top5-country-article{active}" '
            f'data-country-id="{escape(country_id)}" '
            f'data-country="{escape(str(r["country"]))}" '
            f'data-iso3="{escape(str(r["iso3"]))}" '
            f'data-role="{escape(str(r["top5_role"]))}" '
            f'data-family="{escape(str(r["mechanism_family"]))}" '
            f'data-direction="{escape(str(r["top5_direction"]))}" '
            f'data-delta-top5="{escape(pct(r["delta_top5_share"]))}" '
            f'data-delta-gini="{escape(fmt_num(r["delta_panel_ex_energy_gini"], 4))}">'
            f'{markdown_to_html(path.read_text(encoding="utf-8"))}'
            "</article>"
        )
    return f"""
    <div class="country-picker">
      <label for="top5CountryWikiSelect">Country file</label>
      <select id="top5CountryWikiSelect">
        {''.join(options)}
      </select>
      <p id="top5CountryWikiMeta" class="muted"></p>
    </div>
    <div id="top5CountryWikiArticles" class="country-articles">
      {''.join(articles)}
    </div>
    <script>
      (function() {{
        const select = document.getElementById("top5CountryWikiSelect");
        const meta = document.getElementById("top5CountryWikiMeta");
        const root = document.getElementById("top5CountryWikiArticles");
        const articles = Array.from(root.querySelectorAll(".top5-country-article"));
        function updateTop5CountryArticle() {{
          const active = articles.find((article) => article.dataset.countryId === select.value);
          articles.forEach((article) => article.classList.toggle("active", article === active));
          if (active) {{
            meta.textContent = active.dataset.country + " (" + active.dataset.iso3 + ") | "
              + active.dataset.role + " | " + active.dataset.family
              + " | delta top-5 share " + active.dataset.deltaTop5
              + " | delta Gini " + active.dataset.deltaGini;
          }}
        }}
        select.addEventListener("change", updateTop5CountryArticle);
        updateTop5CountryArticle();
      }})();
    </script>
    """


def top5_country_wiki_section() -> str:
    required = [
        TOP5_WIKI_README,
        TOP5_WIKI_SYNTHESIS,
        TOP5_WIKI_GROUP_MEMOS,
        TOP5_WIKI_METHOD,
        TOP5_WIKI_SOURCES,
        TOP5_WIKI_ADVERSARIAL,
        TOP5_WIKI_INDEX,
    ]
    missing = missing_section("top5-country-wiki", "Top-5 Import Concentration Country Wiki", required)
    if missing:
        return missing
    return f"""
<section id="top5-country-wiki">
  <div class="wrap">
    <h2>Top-5 Country Wiki: Import Concentration</h2>
    <p>This is the same country-by-country mechanism exercise as the broader ex-energy import wiki, but it focuses only on the five largest non-energy HS6 import products in each country. The point is to separate true superstar-product concentration from cases where the top five fall while ranks 6-50, ranks 51-200, or the long tail drive the Gini.</p>
    <div class="callout warning">
      <p><strong>Read this as structured diagnosis.</strong> The country files use start/mid/end product-rank evidence plus Economist Council reasoning. They identify plausible mechanisms and decisive follow-up tests; they do not by themselves prove that a trade agreement, crisis, or industrial-policy event caused the shift.</p>
    </div>
    <h3>Top-5 Role Index</h3>
    {top5_wiki_index_table()}
    <h3>Core Top-5 Wiki Notes</h3>
    <div class="wiki-docs">
      {wiki_doc(TOP5_WIKI_SYNTHESIS, "Top-5 Synthesis", open_doc=True)}
      {wiki_doc(TOP5_WIKI_GROUP_MEMOS, "Top-5 Group Memos")}
      {wiki_doc(TOP5_WIKI_METHOD, "Top-5 Method Note")}
      {wiki_doc(TOP5_WIKI_SOURCES, "Top-5 Sources To Check")}
      {wiki_doc(TOP5_WIKI_ADVERSARIAL, "Top-5 Adversarial Review")}
    </div>
    <h3>Top-5 Country Files</h3>
    {top5_country_wiki_browser()}
  </div>
</section>
"""


def source_list() -> str:
    items = []
    for source in SOURCES:
        exists = "available" if source.path.exists() else "missing"
        href = escape(os.path.relpath(source.path, OUT.parent).replace(os.sep, "/"))
        items.append(
            "<li>"
            f'<a href="{href}">{escape(source.label)}</a> '
            f'<span class="muted">({escape(exists)})</span>: {escape(source.note)}'
            "</li>"
        )
    return "<ul>" + "".join(items) + "</ul>"


def figure(path: Path, caption: str) -> str:
    if not path.exists():
        return (
            '<div class="missing-figure">'
            f"Missing figure: {escape(path.relative_to(ROOT).as_posix())}"
            "</div>"
        )
    return (
        "<figure>"
        f'<img src="{escape(image_src(path))}" alt="{escape(caption)}">'
        f"<figcaption>{escape(caption)}</figcaption>"
        "</figure>"
    )


def missing_artifacts(paths: Iterable[Path]) -> list[Path]:
    return [path for path in paths if not path.exists()]


def missing_section(section_id: str, title: str, paths: Iterable[Path]) -> str:
    missing = missing_artifacts(paths)
    if not missing:
        return ""
    rows = "".join(
        f"<li>{escape(path.relative_to(ROOT).as_posix())}</li>"
        for path in missing
    )
    return f"""
<section id="{escape(section_id)}">
  <div class="wrap">
    <h2>{escape(title)}</h2>
    <div class="callout warning">
      <p><strong>Section unavailable in this checkout.</strong> The page was rebuilt without this ancillary section because the required generated artifacts are missing.</p>
      <ul>{rows}</ul>
    </div>
  </div>
</section>
"""


def product_graph_browser() -> str:
    missing = [
        path
        for spec in PPP_BROWSER_FIGS.values()
        for key, path in spec.items()
        if key in {"level_ppp", "log_ppp"} and not path.exists()
    ]
    if missing:
        return (
            '<div class="missing-figure">'
            "Missing product-browser figures: "
            + escape(", ".join(path.relative_to(ROOT).as_posix() for path in missing))
            + "</div>"
        )
    outcome_options = "".join(
        f'<option value="{escape(slug)}">{escape(spec["label"])}</option>'
        for slug, spec in PPP_BROWSER_FIGS.items()
    )
    image_map_entries = []
    label_entries = []
    for slug, spec in PPP_BROWSER_FIGS.items():
        label_entries.append(f'"{slug}": "{escape(str(spec["label"]))}"')
        image_map_entries.append(
            '"{slug}": {{ "level_ppp": "{level}", "log_ppp": "{log}" }}'.format(
                slug=slug,
                level=escape(image_src(spec["level_ppp"])),
                log=escape(image_src(spec["log_ppp"])),
            )
        )
    image_map = "{ " + ", ".join(image_map_entries) + " }"
    label_map = "{ " + ", ".join(label_entries) + " }"
    default_src = escape(image_src(PPP_BROWSER_FIGS["export_world_relative_product_gini"]["level_ppp"]))
    return f"""
    <div class="figure-browser">
      <div class="figure-controls" aria-label="PPP product hump figure controls">
        <label for="pppOutcomeSelect">Outcome</label>
        <select id="pppOutcomeSelect">
          {outcome_options}
        </select>
        <label for="pppIncomeSelect">Income form</label>
        <select id="pppIncomeSelect">
          <option value="level_ppp">Level PPP: income and income squared</option>
          <option value="log_ppp">Log PPP: log income and log-income squared</option>
        </select>
      </div>
      <figure>
        <img id="pppProductBrowserImg" src="{default_src}" alt="PPP product hump diagnostic">
        <figcaption id="pppProductBrowserCaption">Export World-Relative Product Gini, level PPP income form.</figcaption>
      </figure>
    </div>
    <script>
      (function() {{
        const imageMap = {image_map};
        const labelMap = {label_map};
        const outcome = document.getElementById("pppOutcomeSelect");
        const income = document.getElementById("pppIncomeSelect");
        const img = document.getElementById("pppProductBrowserImg");
        const caption = document.getElementById("pppProductBrowserCaption");
        function updateFigure() {{
          const outcomeKey = outcome.value;
          const incomeKey = income.value;
          img.src = imageMap[outcomeKey][incomeKey];
          const incomeLabel = incomeKey === "level_ppp" ? "level PPP income form" : "log PPP income form";
          const axisLabel = incomeKey === "level_ppp" ? "x-axis is PPP dollars" : "x-axis is log PPP GDP per capita";
          img.alt = labelMap[outcomeKey] + ", " + incomeLabel;
          caption.textContent = labelMap[outcomeKey] + ", " + incomeLabel + "; " + axisLabel + ".";
        }}
        outcome.addEventListener("change", updateFigure);
        income.addEventListener("change", updateFigure);
      }})();
    </script>
    """


def mechanism_regression_section() -> str:
    required = [
        EXPLANATORY_SUMMARY,
        EXPLANATORY_TERMS,
        EXPLANATORY_DIAGNOSTICS,
        EXPLANATORY_SAMPLE_MANIFEST,
        EXPLANATORY_INFLUENCE,
        EXPLANATORY_TARIFF_ENDPOINTS,
        EXPLANATORY_MEMO,
        EXPLANATORY_ADVERSARIAL,
    ]
    missing = missing_section(
        "import-concentration-explanatory-regressions",
        "Can Exports, Income, Or Trade Openness Explain Import Concentration?",
        required,
    )
    if missing:
        return missing
    return f"""
<section>
  <div class="wrap">
    <h2>Can Exports, Income, Or Trade Openness Explain Import Concentration?</h2>
    <p>This is a descriptive explanation test for the 2000-2024 rise in energy-excluded import product concentration. The dependent variable is the change in import Product Gini after removing the Exercise 3 energy bin; product code 999999 remains excluded from product-dependent calculations.</p>
    <div class="callout">
      <p><strong>Bottom line:</strong> export growth and PPP income growth do not explain the concentration changes. Export and income levels correlate in simple cross-country models, but mostly disappear once openness and macro controls are included. The strongest recurring signal is trade openness, especially in within-country panel specifications. That is a trade-integration/import-basket result, not proof that free-trade policy or tariffs caused concentration.</p>
    </div>
    <h3>Hypotheses Tested</h3>
    {explanatory_hypothesis_table()}
    <h3>Data and Econometric Structure</h3>
    <p>The main panel uses rd2 countries for 2000-2024. Import concentration comes from the same Exercise 3 import-bin file used elsewhere on this page. Export scale is measured from Comtrade merchandise exports, with WDI real exports used as a robustness check. Income is World Bank constant-PPP GDP per capita. Openness is mainly merchandise imports plus exports over current GDP; WDI goods-and-services openness is a robustness check. Tariffs are World Bank weighted mean applied tariffs and are treated only as a reduced-sample barrier proxy.</p>
    <p>The main country-level specification explains each country's 2000-2024 concentration change with initial levels and 2000-2024 changes, using HC3 robust standard errors because the country sample is small. The panel specification adds country and year fixed effects, which asks whether the same country becomes more concentrated in years when exports, income, or openness move. Alternatives were pooled-only regressions, pure bivariate correlations, nonlinear hump equations, and detailed tariff/trade-agreement models. The chosen structure is best for this diagnostic because it keeps the unit of comparison transparent and separates cross-country development-stage differences from within-country co-movement.</p>
    <h3>Model Inventory</h3>
    {explanatory_model_table()}
    <h3>Selected Coefficients</h3>
    {explanatory_selected_terms_table()}
    {figure(EXPLANATORY_FIG, "Selected coefficient estimates from the explanatory regressions.")}
    <h3>Leave-One-Country Influence</h3>
    <p>The cross-country merchandise-openness result is high-leverage sensitive. It is significant in the preferred full sample, but the leave-one-country check below shows the coefficient loses p&lt;0.05 when Hong Kong, Singapore, Slovakia, or Slovenia is omitted. The within-country country/year-FE openness result is more stable, including with WDI openness and after excluding logistics hubs.</p>
    {explanatory_influence_table()}
    <h3>Model Sample Manifest</h3>
    <p>These are the models with complete-case row loss. The real-export robustness drops countries with incomplete WDI real-export coverage; tariff models are reduced-sample checks.</p>
    {explanatory_sample_manifest_table()}
    <h3>Tariff Endpoint Timing</h3>
    <p>Tariff country-change models use nearest available WDI tariff values in 2000-2005 and 2019-2024 windows. Most end-year tariff endpoints are 2022, so tariff results should not be described as a literal 2000-to-2024 policy-barrier test.</p>
    {explanatory_tariff_endpoint_table()}
    <h3>Sample Checks</h3>
    {explanatory_diagnostics_table()}
    <div class="grid">
      <div class="panel">
        <h3>What this supports</h3>
        <p>The evidence supports a descriptive link between trade integration and energy-excluded import concentration. The strongest version is within-country co-movement: countries tend to look more concentrated in years when merchandise openness is higher.</p>
      </div>
      <div class="panel">
        <h3>What it does not support</h3>
        <p>It does not support a strong export-growth story, a PPP-income-growth story, or a clean tariff-barrier story. Lagged annual changes are not significant, so the evidence is weaker for a simple timing story where export, income, or openness changes clearly precede next-year concentration changes.</p>
      </div>
      <div class="panel">
        <h3>Confidence</h3>
        <p>Moderate for the negative finding on export and income growth. Lower for any positive openness interpretation because openness partly reflects trade composition itself and weakens under some robustness choices, especially when logistics hubs are removed or WDI goods-and-services openness replaces the merchandise measure.</p>
      </div>
    </div>
  </div>
</section>
"""


def industrial_policy_section() -> str:
    required = [
        INDUSTRIAL_POLICY_MEMO,
        INDUSTRIAL_POLICY_ADVERSARIAL,
        INDUSTRIAL_POLICY_MODEL_SUMMARY,
        INDUSTRIAL_POLICY_TERMS,
    ]
    missing = missing_section("industrial-policy", "Industrial Policy, Globalization, And Import Gini", required)
    if missing:
        return missing
    return f"""
<section id="industrial-policy">
  <div class="wrap">
    <h2>Industrial Policy, Globalization, And Import Gini</h2>
    <p>This section tests whether the energy-excluded import Product Gini is linked to import-substitution-style industrial policy, using the Juhasz-Lane-Oehlsen-Perez text-based industrial-policy dataset for 2010-2022.</p>
    <div class="callout warning">
      <p><strong>Bottom line:</strong> this does not give a clean “import substitution explains import concentration” result. Lagged import-substitution/protective IP counts are not significant in the country/year fixed-effect model, the first-difference model, or the 2010-2022 country-change model. The only positive signal is narrower: the lagged share of a country's IP measures that are import-substitution-like is positive in one country/year-FE specification.</p>
    </div>
    <div class="callout">
      <p><strong>Coefficient size:</strong> the significant share coefficient is 0.00395. A 10 percentage-point increase in the import-substitution share of industrial-policy measures predicts only about +0.00040 in import Product Gini; a 25 percentage-point increase predicts about +0.00099. That is small relative to the median annual movement of roughly 0.0031 and the median 2010-2022 country change of roughly 0.0115.</p>
    </div>
    {figure(INDUSTRIAL_POLICY_FIG, "Industrial-policy exposure coefficients for ex-energy import Product Gini regressions.")}
    <div class="wiki-docs">
      {wiki_doc(INDUSTRIAL_POLICY_MEMO, "Industrial Policy Memo", open_doc=True)}
      {wiki_doc(INDUSTRIAL_POLICY_ADVERSARIAL, "Industrial Policy Adversarial Review")}
    </div>
  </div>
</section>
"""


def render() -> str:
    for artifact in [
        TRIBUNAL_MODELS,
        PPP_SUMMARY,
        PPP_FE,
        MECHANISM,
        OLD_CONE,
        BROAD_SUMMARY,
        BROAD_ATTRITION,
        BROAD_INDEPENDENT_CHECKS,
        BROAD_DIAGNOSTICS,
        BROAD_MEMO,
        BROAD_REVIEW,
    ]:
        if not artifact.exists():
            raise FileNotFoundError(artifact)

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Cadot Hump Work In Progress</title>
  <style>
    :root {{
      --ink: #17212b;
      --muted: #647184;
      --line: #d8dee8;
      --paper: #fbfcfe;
      --panel: #ffffff;
      --blue: #275f91;
      --green: #26745d;
      --red: #a33d3d;
      --amber: #9a641e;
      --soft-blue: #eaf2f8;
      --soft-green: #e9f5ef;
      --soft-red: #f8eded;
      --soft-amber: #fbf1e3;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background: var(--paper);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.52;
      overflow-wrap: anywhere;
    }}
    header {{
      border-bottom: 1px solid var(--line);
      background: #f3f6fa;
    }}
    .wrap {{
      max-width: 1160px;
      margin: 0 auto;
      padding: 28px 20px;
      min-width: 0;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: clamp(2rem, 4vw, 4.2rem);
      line-height: 1.02;
      letter-spacing: 0;
    }}
    h2 {{
      margin: 0 0 14px;
      font-size: 1.45rem;
      letter-spacing: 0;
    }}
    h3 {{
      margin: 18px 0 8px;
      font-size: 1rem;
      letter-spacing: 0;
    }}
    h4 {{
      margin: 16px 0 7px;
      font-size: 0.96rem;
      letter-spacing: 0;
    }}
    h5 {{
      margin: 14px 0 6px;
      font-size: 0.9rem;
      letter-spacing: 0;
      color: #304355;
    }}
    p {{ margin: 0 0 12px; }}
    section {{
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }}
    section:nth-of-type(even) {{ background: #f8fafc; }}
    .lead {{
      max-width: 860px;
      font-size: 1.08rem;
      color: #283848;
    }}
    .mini-nav {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 14px;
    }}
    .mini-nav a {{
      border: 1px solid var(--line);
      border-radius: 999px;
      background: #fff;
      padding: 5px 10px;
      text-decoration: none;
      font-size: 0.86rem;
      font-weight: 650;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 14px;
      margin-top: 16px;
    }}
    .figure-controls {{
      display: grid;
      grid-template-columns: auto minmax(220px, 1fr) auto minmax(220px, 1fr);
      gap: 10px;
      align-items: center;
      margin: 14px 0 10px;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
    }}
    .figure-controls label {{
      color: var(--muted);
      font-size: 0.9rem;
      font-weight: 650;
    }}
    .figure-controls select {{
      width: 100%;
      min-height: 38px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
      font: inherit;
      padding: 6px 9px;
    }}
    .country-picker {{
      display: grid;
      grid-template-columns: auto minmax(260px, 1fr);
      gap: 10px;
      align-items: center;
      margin: 14px 0 8px;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
    }}
    .country-picker label {{
      color: var(--muted);
      font-size: 0.9rem;
      font-weight: 650;
    }}
    .country-picker select {{
      width: 100%;
      min-height: 38px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
      font: inherit;
      padding: 6px 9px;
    }}
    .country-picker .muted {{
      grid-column: 1 / -1;
      margin: 0;
    }}
    @media (max-width: 760px) {{
      .figure-controls, .country-picker {{
        grid-template-columns: 1fr;
      }}
    }}
    .panel {{
      border: 1px solid var(--line);
      background: #fff;
      border-radius: 8px;
      padding: 16px;
    }}
    .panel h3 {{ margin-top: 0; }}
    .callout {{
      border-left: 5px solid var(--blue);
      background: var(--soft-blue);
      padding: 14px 16px;
      margin: 16px 0;
      overflow-wrap: anywhere;
    }}
    .warning {{
      border-left-color: var(--amber);
      background: var(--soft-amber);
    }}
    .danger {{
      border-left-color: var(--red);
      background: var(--soft-red);
    }}
    .good {{
      border-left-color: var(--green);
      background: var(--soft-green);
    }}
    .tag {{
      display: inline-block;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 0.78rem;
      background: #fff;
      margin: 2px 4px 2px 0;
      white-space: nowrap;
    }}
    .tag.good {{ border-color: #a8d6c5; background: var(--soft-green); }}
    .tag.warn {{ border-color: #e4c991; background: var(--soft-amber); }}
    .tag.bad {{ border-color: #e0aaaa; background: var(--soft-red); }}
    .muted {{ color: var(--muted); }}
    .formula {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      background: #f5f7fa;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px 12px;
      overflow-wrap: anywhere;
      white-space: normal;
    }}
    .table-wrap {{
      overflow-x: auto;
      margin: 12px 0 18px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
    }}
    table {{
      border-collapse: collapse;
      min-width: 780px;
      width: 100%;
      font-size: 0.92rem;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 9px 10px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      background: #eef3f8;
      font-weight: 650;
      color: #233140;
    }}
    tr:last-child td {{ border-bottom: 0; }}
    .sig {{
      font-weight: 800;
      color: #0d5a43;
      background: #e3f4ed;
      padding: 1px 4px;
      border-radius: 4px;
    }}
    figure {{
      margin: 16px 0;
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      background: #fff;
    }}
    img {{
      display: block;
      width: 100%;
      height: auto;
    }}
    figcaption {{
      padding: 10px 12px;
      color: var(--muted);
      font-size: 0.9rem;
      border-top: 1px solid var(--line);
    }}
    .timeline {{
      counter-reset: step;
      list-style: none;
      padding-left: 0;
    }}
    .timeline li {{
      position: relative;
      padding: 0 0 14px 36px;
      margin: 0;
    }}
    .timeline li::before {{
      counter-increment: step;
      content: counter(step);
      position: absolute;
      left: 0;
      top: 0;
      width: 24px;
      height: 24px;
      border-radius: 50%;
      background: var(--blue);
      color: #fff;
      text-align: center;
      line-height: 24px;
      font-size: 0.78rem;
      font-weight: 700;
    }}
    ul {{ padding-left: 20px; }}
    a {{ color: var(--blue); }}
    code {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      background: #eef3f8;
      border: 1px solid #dce5ef;
      border-radius: 4px;
      padding: 1px 4px;
    }}
    blockquote {{
      margin: 12px 0;
      border-left: 4px solid var(--line);
      padding: 8px 12px;
      background: #f7f9fc;
      color: #304355;
    }}
    .wiki-docs {{
      display: grid;
      gap: 10px;
      margin: 12px 0 18px;
    }}
    .wiki-doc {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      overflow: hidden;
    }}
    .wiki-doc summary {{
      cursor: pointer;
      padding: 12px 14px;
      font-weight: 750;
      background: #eef3f8;
      border-bottom: 1px solid var(--line);
    }}
    .wiki-md {{
      padding: 14px;
    }}
    .wiki-md h3:first-child,
    .country-article h3:first-child,
    .top5-country-article h3:first-child {{
      margin-top: 0;
    }}
    .wiki-md .table-wrap,
    .country-article .table-wrap,
    .top5-country-article .table-wrap {{
      margin-top: 8px;
    }}
    .country-articles {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      overflow: hidden;
    }}
    .country-article,
    .top5-country-article {{
      display: none;
      padding: 16px;
    }}
    .country-article.active,
    .top5-country-article.active {{
      display: block;
    }}
    .missing-figure {{
      border: 1px dashed var(--red);
      color: var(--red);
      padding: 16px;
      border-radius: 8px;
      background: var(--soft-red);
      overflow-wrap: anywhere;
    }}
  </style>
</head>
<body>
<header>
  <div class="wrap">
    <h1>Cadot Hump Work In Progress</h1>
    <p class="lead">A refreshed, from-scratch guide to the export diversification U-shape question: what Cadot et al. argued, what other trade-margin papers suggest, what we estimated in the rd2 data, what changed after the PPP and microstate robustness checks, and how strong the evidence is.</p>
    <p>
      {tag("updated June 16, 2026", "good")}
      {tag("rd2 countries, 2000-2024", "good")}
      {tag("HS6 999999 excluded for product outcomes", "good")}
      {tag("partner outcomes use default partner convention", "good")}
      {tag("PPP axes corrected", "good")}
      {tag("modern broad 156-country extension added", "good")}
      {tag("country wiki embedded", "good")}
      {tag("top-5 wiki embedded", "good")}
      {tag("industrial policy test added", "good")}
      {tag("descriptive, not causal", "warn")}
    </p>
    <nav class="mini-nav" aria-label="Page sections">
      <a href="#industrial-policy">Industrial Policy</a>
      <a href="#top5-country-wiki">Top-5 Wiki</a>
      <a href="#country-wiki">Country Wiki</a>
      <a href="#cadot-broad-results">Broad 156 Results</a>
      <a href="#source-files">Source Files</a>
    </nav>
  </div>
</header>

<section>
  <div class="wrap">
    <h2>One-Minute Answer</h2>
    <div class="callout good">
      <p><strong>Cadot's idea:</strong> export concentration is U-shaped over development. Poor countries start concentrated, middle-income countries diversify by adding product lines, and rich countries can reconcentrate because they close old export lines that no longer fit their comparative advantage.</p>
    </div>
    <div class="callout warning">
      <p><strong>Our answer:</strong> Constant PPP GDP restores some Cadot-looking product humps in pooled/year-FE regressions, especially with level PPP GDP per capita. The modern broad 156-country extension makes the import-product U-shape much stronger, while export-product evidence is edge-sensitive in pooled results and stronger between countries than within countries. This is still descriptive, not causal.</p>
    </div>
    <div class="callout danger">
      <p><strong>Main issue is still pooled vs country FE.</strong> Pooled/year-FE compares countries at different development stages. Country FE asks whether the same country reconcentrates as it gets richer. The PPP hump weakens there, so do not overclaim.</p>
    </div>
    <div class="callout">
      <p><strong>Since the first version:</strong> we verified that Cadot used constant PPP dollars, made constant PPP the headline income axis, reran the rd2 mechanism tribunal on constant PPP, and added a separate 156-country modern extension. The old current-GNI diagnostics are now legacy sensitivity context, not the headline result.</p>
    </div>
  </div>
</section>

<section>
  <div class="wrap">
    <h2>First Principles</h2>
    <div class="grid">
      <div class="panel">
        <h3>What is the hump?</h3>
        <p>A concentration U-shape means concentration is high at low income, falls at middle income, then rises at high income. If the y-axis is diversification rather than concentration, the same fact is an inverted U.</p>
      </div>
      <div class="panel">
        <h3>Why quadratic?</h3>
        <p>The regression includes income and income squared. A positive squared term in a concentration regression creates a U-shape: first falling concentration, then rising concentration after the turning point.</p>
      </div>
      <div class="panel">
        <h3>What is a turning point?</h3>
        <p>It is the income level where the fitted curve changes direction. A turning point outside the observed sample is not meaningful evidence of a real hump.</p>
      </div>
      <div class="panel">
        <h3>Exports vs imports</h3>
        <p>Cadot's paper is about exports. Our import-product U-shape is a related descriptive fact, but it needs a different mechanism: import baskets broaden during industrialization and may reconcentrate around specialized high-income supply-chain inputs.</p>
      </div>
    </div>
    <div class="formula">concentration_ct = beta1 * income_ct + beta2 * income_ct^2 + controls_ct + year FE + error_ct</div>
    <p class="muted">For concentration outcomes, the Cadot-style sign is beta2 &gt; 0. The estimated turning point is -beta1 / (2 * beta2), translated back into dollars when the income variable is logged.</p>
  </div>
</section>

<section>
  <div class="wrap">
    <h2>What Cadot Did</h2>
    <div class="grid">
      <div class="panel">
        <h3>Data</h3>
        <p>UN Comtrade exports, HS6 product lines, 156 countries, 1988-2006. The usable sample in the local notes is 2,797 country-years. Cadot used GDP per capita in constant PPP dollars as the main development measure.</p>
      </div>
      <div class="panel">
        <h3>Outcomes</h3>
        <p>Theil, Gini, Herfindahl, and active export-line counts. Theil mattered because it decomposes concentration into extensive-margin and intensive-margin pieces.</p>
      </div>
      <div class="panel">
        <h3>Estimators</h3>
        <p>Quadratic concentration-income regressions, including pooled OLS, within, between, and robustness checks. Their local notes report turning points around $22k-$30k in constant PPP dollars.</p>
      </div>
      <div class="panel">
        <h3>Population</h3>
        <p>Cadot excluded microstates with population below one million. Our original rd2 regressions did not impose that exact exclusion; they controlled for log population instead. We later reran the PPP table excluding Iceland, Luxembourg, and Guyana, the three rd2 countries ever below one million people, and the level-PPP product humps survived.</p>
      </div>
    </div>
    <h3>Cadot's Mechanism</h3>
    <ol class="timeline">
      <li><strong>Low income:</strong> countries export few products, so product concentration is high.</li>
      <li><strong>Middle income:</strong> countries add products at the extensive margin. Active lines rise and concentration falls.</li>
      <li><strong>High income:</strong> countries stop exporting old, peripheral, lower-factor-intensity products. Active lines can fall and concentration rises again.</li>
      <li><strong>Interpretation:</strong> rich-country reconcentration is not just a loss of variety; it can be pruning of old-cone products that no longer match current comparative advantage.</li>
    </ol>
  </div>
</section>

<section>
  <div class="wrap">
    <h2>Cadot's Alternative Explanations</h2>
    <p>Cadot did not just fit a curve. The paper explicitly worried that the hump might be fake, then checked several possible culprits.</p>
    {table(
        ["Hypothesis", "Why it could create a fake hump", "Cadot's answer"],
        [
            [
                "Oil and commodities",
                "Rich commodity exporters can be both high-income and concentrated.",
                "They add robustness checks and argue the turning point survives.",
            ],
            [
                "Microstates",
                "Tiny island economies may have extreme income and extreme concentration.",
                "They exclude countries below one million population in the main analysis.",
            ],
            [
                "HS classification design",
                "Some HS sections, especially machinery/electrical, have many lines and high values per line.",
                "They run section aggregation/exclusion checks and argue the hump survives.",
            ],
            [
                "Unobserved country heterogeneity",
                "A pooled curve may compare different countries rather than trace the same country over time.",
                "They report within and between estimates with similar turning points.",
            ],
            [
                "GDP endogeneity",
                "Export concentration and income may jointly move with omitted factors.",
                "They run system-GMM-style robustness, but the result remains descriptive rather than causal.",
            ],
        ],
    )}
  </div>
</section>

<section>
  <div class="wrap">
    <h2>Other Ideas In The Literature</h2>
    <p>These papers do not all predict the same hump, but they explain mechanisms that can look like diversification or reconcentration in aggregate trade data.</p>
    {table(
        ["Paper or idea", "Mechanism", "What it means for our hump question"],
        [
            [
                "Imbs-Wacziarg; Klinger-Lederman",
                "Development can involve stages of diversification and later reconcentration.",
                "Cadot's export hump is the trade-data cousin of a broader development-stage idea.",
            ],
            [
                "Hummels-Klenow",
                "Larger/richer economies export more varieties, but also differ in quality, quantity, and unit values.",
                "A product count is not enough. Value concentration can hide quality upgrading inside existing HS6 codes.",
            ],
            [
                "Kehoe-Ruhl",
                "Least-traded or barely traded goods can become important after liberalization or structural change.",
                "New-product evidence should distinguish true discovery from low-base products becoming meaningful.",
            ],
            [
                "Evenett-Venables",
                "Developing-country export growth often comes from selling existing products to new markets.",
                "Partner diversification is a separate margin from product diversification.",
            ],
            [
                "Brenton-Newfarmer",
                "Export growth often comes more from scaling existing flows and entering markets than from discovering new products.",
                "A lack of product diversification need not mean export failure if existing products scale and markets broaden.",
            ],
            [
                "Besedes-Prusa",
                "Many new export relationships die quickly; survival and deepening matter.",
                "Entry is not success. A country can add products without durable diversification.",
            ],
            [
                "Bernard-Redding-Schott",
                "Multi-product firms drop weak products and focus on stronger core products.",
                "Reconcentration can be efficient core-competence reallocation, not only loss.",
            ],
            [
                "Freund-Pierola",
                "Top exporters or superstar firms can dominate sector export patterns.",
                "Aggregate product concentration may reflect a few large firms or cells scaling up.",
            ],
            [
                "Fieler-Eaton",
                "Product margins, quantity, unit values, quality, and welfare need to be separated.",
                "Value-only concentration cannot tell us whether welfare rises or falls.",
            ],
        ],
    )}
  </div>
</section>

<section>
  <div class="wrap">
    <h2>What We Did</h2>
    <ol class="timeline">
      <li><strong>Built the rd2 panel.</strong> The main empirical sample is 55 countries over 25 years, 2000-2024, for 1,375 country-years.</li>
      <li><strong>Applied product rules.</strong> Product outcomes exclude HS6 999999 before aggregation. Partner concentration uses the default partner-total convention.</li>
      <li><strong>Reran the mechanism tribunal with constant PPP income.</strong> The headline income axis is World Bank NY.GDP.PCAP.PP.KD, GDP per capita at PPP in constant 2021 international dollars.</li>
      <li><strong>Ran PPP GDP checks.</strong> We used World Bank NY.GDP.PCAP.PP.KD, constant 2021 PPP GDP per capita, then estimated both level PPP and log PPP forms.</li>
      <li><strong>Added a broad Cadot-comparable modern extension.</strong> The separate cadot_broad_156 track selects 156 reporters and uses complete-case regressions for observed country-years; it is not a literal Cadot 1988-2006 mirror-data replication.</li>
      <li><strong>Audited the PPP functional form.</strong> We verified that log PPP uses log income and log-income squared, and corrected the figures so the level graph uses a linear dollar x-axis while the log graph uses a log-income x-axis.</li>
      <li><strong>Ran country-FE robustness.</strong> This asks whether the same country reconcentrates as it gets richer, not just whether richer countries look more concentrated than middle-income countries.</li>
      <li><strong>Ran microstate exclusion.</strong> We dropped Iceland, Luxembourg, and Guyana to mimic Cadot's sub-1m population concern. The level-PPP product humps remained clear.</li>
      <li><strong>Ran mechanism diagnostics.</strong> We classified reconcentration episodes by commodity exposure, Section 16 sensitivity, old-cone pruning, continuing-product scaling, and unexplained residual cases.</li>
      <li><strong>Separated import interpretation.</strong> The import-product U-shape is not Cadot's export old-cone story. The council interpretation is broader import-basket development followed by high-income supply-chain specialization.</li>
      <li><strong>Audited the results.</strong> The local Referee 2 audit replicated selected coefficients and flagged the main interpretation risk: do not sell pooled patterns as within-country reconcentration.</li>
    </ol>
  </div>
</section>

<section>
  <div class="wrap">
    <h2>Constant-PPP Mechanism Tribunal</h2>
    <p>This rd2 mechanism tribunal now uses constant PPP GDP per capita as the headline income axis. Current-GNI diagnostics are legacy sensitivity context, not the main Cadot comparison.</p>
    {cadot_tribunal_constant_ppp_table()}
    {figure(CADOT_FIG, "Constant-PPP Cadot mechanism diagnostic for the world-relative export product concentration outcome.")}
  </div>
</section>

<section>
  <div class="wrap">
    <h2>PPP GDP Results</h2>
    <p>This rerun is closer to Cadot's income setup because it uses constant PPP GDP per capita. Level PPP and log PPP do not give the same answer. The figures below now match the regression variable: level PPP uses a linear dollar x-axis, while log PPP uses a log-income x-axis.</p>
    {ppp_main_table()}
    <div class="grid">
      {figure(PPP_LEVEL_FIG, "Level PPP diagnostics: x-axis is PPP GDP per capita in dollars; the blue fit uses income and income squared.")}
      {figure(PPP_LOG_FIG, "Log PPP diagnostics: x-axis is log PPP GDP per capita; the blue fit uses log income and log-income squared.")}
    </div>
  </div>
</section>

<section>
  <div class="wrap">
    <h2>PPP Product Figure Browser</h2>
    <p>Use the dropdowns to inspect the product-concentration graphs one at a time. The outcome dropdown covers world-relative product Gini, export product Gini, and import product Gini; the income-form dropdown switches between the level-PPP and log-PPP specifications.</p>
    {product_graph_browser()}
  </div>
</section>

<section id="cadot-broad-results">
  <div class="wrap">
    <h2>Cadot Broad 156 Modern Extension, 2000-2024</h2>
    <p>This is the separate modern extension track, not the website/default rd2 workflow and not a literal Cadot replication. It selects 156 active non-group reporters with valid ISO3 metadata and at least 19 annual HS final-data years in 2000-2024, then estimates complete-case country-year regressions with constant PPP GDP per capita, population, oil-share controls, and year fixed effects.</p>
    <div class="callout good">
      <p><strong>Main result:</strong> import Product Gini and import Product Theil give the cleanest broad-sample humps. In pooled regressions, both level-PPP and log-PPP specifications have positive, statistically significant quadratic terms with turning points inside the central income support.</p>
    </div>
    <div class="callout warning">
      <p><strong>Concern:</strong> export-product evidence is edge-sensitive in pooled results and mostly stronger between countries than within countries. Partner concentration does not give robust Cadot-style evidence. The literal Cadot 1988-2006 mirror-data, HS0, 4,991-line replication is still not complete.</p>
    </div>
    <h3>Pooled Headline Rows</h3>
    {broad_pooled_headline_table()}
    <h3>Estimator Stress Test, Level PPP</h3>
    <p>The key check is whether the broad-sample pattern is pooled/between-country or within-country. The export rows are much weaker with country fixed effects; the import Product Gini row is the more durable modern-extension result.</p>
    {broad_estimator_stress_table()}
    <h3>Broad-Sample Attrition</h3>
    <p>The sample definition selects 156 reporters, but the analytic regressions use 135 countries/clusters after complete-case requirements for outcomes, constant PPP, population, and oil-share controls.</p>
    {broad_attrition_table()}
    <h3>Independent Saved-Panel Re-Estimation</h3>
    <p>The broad PPP runner was checked by re-estimating one pooled/year-FE model and one country+year-FE model from the saved analytic panel. All eight checked terms matched the saved coefficients and standard errors within tolerance.</p>
    {broad_reestimate_table()}
    <div class="grid">
      {figure(BROAD_LEVEL_FIG, "Cadot broad 156 modern extension: level-PPP diagnostics.")}
      {figure(BROAD_LOG_FIG, "Cadot broad 156 modern extension: log-PPP diagnostics.")}
    </div>
  </div>
</section>

<section>
  <div class="wrap">
    <h2>Microstate Exclusion</h2>
    <p>Cadot excluded countries below one million population. Our rd2 sample includes three countries that are below one million in at least some years: Iceland, Luxembourg, and Guyana. Dropping them leaves 52 countries and 1,300 country-years. The product humps in level PPP remain clear; the only changed verdict labels are partner-level cases that remain non-evidence.</p>
    {ppp_microstate_table()}
    <div class="callout good">
      <p><strong>Read:</strong> the level-PPP product humps are not an artifact of those three small-population countries. Export product Gini shifts from a $75.8k turning point to $63.6k; import product Gini shifts from $64.5k to $55.7k, and both remain clear humps.</p>
    </div>
  </div>
</section>

<section>
  <div class="wrap">
    <h2>Pooled Versus Within-Country</h2>
    <p>Pooled/year-FE regressions compare countries at different development stages in the same world year. Country + year FE regressions ask a harder question: when a given country becomes richer over 2000-2024, does its concentration first fall and then rise?</p>
    {ppp_fe_table()}
    <div class="callout warning">
      <p>The pooled PPP level product humps are the strongest evidence for a Cadot-like pattern in our data. The country-FE rows are weaker and sometimes flip or move outside central support. That is why the empirical claim should be framed as a development-stage pattern, not as proof that each country inevitably reconcentrates over time.</p>
    </div>
  </div>
</section>

<section>
  <div class="wrap">
    <h2>Mechanism Evidence</h2>
    <p>The mechanism tribunal asks what is inside reconcentration episodes. It is a descriptive scorecard built on 5-year country windows, not a causal model. The strongest mass in our scorecard is continuing-product scaling, not clean old-cone exit.</p>
    <h3>How the scorecard was built</h3>
    <p>A reconcentration episode is a country-window where world-relative product Gini rises. The 5-year product transition decomposition uses adjacent two-year base and future windows to reduce one-year noise. Flags can overlap, so the shares below do not sum to 100%.</p>
    {mechanism_method_table()}
    <h3>What the scorecard found</h3>
    {mechanism_table()}
    {figure(MECHANISM_FIG, "Mechanism scorecard for reconcentration episodes in the rd2 panel.")}
    <h3>Old-Cone Exit Test</h3>
    <p>The old-cone interaction is statistically visible: products with larger mismatch are more likely to exit on the rich side. But the scorecard says this is not the dominant mass of reconcentration episodes.</p>
    {old_cone_table()}
    {figure(OLD_CONE_FIG, "Old-cone exit diagnostic by mismatch bins.")}
  </div>
</section>

<section>
  <div class="wrap">
    <h2>Import Concentration U-Shape</h2>
    <p>The import-product U-shape is real in the level-PPP pooled/year-FE specification, but it should not be sold as Cadot's export old-cone mechanism. The most plausible council interpretation is that poor countries import a narrow basket of essentials, middle-income countries broaden imports as production and consumption diversify, and rich countries may reconcentrate around large specialized input, capital-goods, energy, pharma, electronics, auto, or supply-chain categories.</p>
    {import_u_shape_table()}
    <div class="callout warning">
      <p><strong>Read:</strong> the import result is useful but still descriptive. The best next tests are sector decomposition, fuels/commodities exclusion, top-product contribution, input-versus-consumer-goods splits, and country-FE robustness.</p>
    </div>
  </div>
</section>

{mechanism_regression_section()}

{industrial_policy_section()}

{top5_country_wiki_section()}

{country_wiki_section()}

<section>
  <div class="wrap">
    <h2>How It Stands Up</h2>
    <div class="grid">
      <div class="panel">
        <h3>What is solid</h3>
        <p>Cadot's conceptual distinction is useful: product concentration can fall through product entry and rise later through product exit or selective scaling. Our PPP level regressions do find product concentration U-shapes in the pooled/year-FE sample, and those product humps survive dropping Iceland, Luxembourg, and Guyana.</p>
      </div>
      <div class="panel">
        <h3>What is fragile</h3>
        <p>The shape depends on income definition and functional form. Log PPP weakens several product outcomes, and country FE weakens the within-country interpretation. This remains the main limitation.</p>
      </div>
      <div class="panel">
        <h3>What mechanism looks most likely here</h3>
        <p>Continuing-product scaling explains more reconcentration-episode mass than old-cone pruning. Commodity exposure and Section 16 sensitivity are also nontrivial, so the mechanism story is mixed.</p>
      </div>
      <div class="panel">
        <h3>What remains missing</h3>
        <p>We do not yet have the literal Cadot 1988-2006 mirror-data, HS0, 4,991-line replication, a full Cadot Theil decomposition, firm IDs, product quality/unit-value decomposition, microstate-excluded country-FE table, or a publication-grade causal identification design.</p>
      </div>
    </div>
    <div class="callout">
      <p><strong>Best current wording:</strong> In the rd2 2000-2024 panel, PPP level specifications recover Cadot-like product concentration U-shapes in pooled/year-FE regressions, and those product humps survive excluding the three sub-1m population rd2 countries. But the within-country evidence is weaker and the mechanism evidence points more toward continuing-product scaling than pure old-cone exit. The result is evidence for a development-stage concentration pattern, not proof of a universal mechanical reconcentration law.</p>
    </div>
  </div>
</section>

<section id="source-files">
  <div class="wrap">
    <h2>Source Files</h2>
    {source_list()}
    <p class="muted">Generated from local artifacts in {escape(str(BASE))}. This HTML builder renders existing outputs; it does not run the regressions itself.</p>
  </div>
</section>
</body>
</html>
"""
    return html


def main() -> None:
    OUT.write_text(render(), encoding="utf-8")
    LEGACY_OUT.write_text(
        """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="0; url=workinprogress.html">
  <title>Redirecting to Work In Progress</title>
</head>
<body>
  <p>This Cadot explainer has moved to <a href="workinprogress.html">workinprogress.html</a>.</p>
</body>
</html>
""",
        encoding="utf-8",
    )
    print(OUT)


if __name__ == "__main__":
    main()
