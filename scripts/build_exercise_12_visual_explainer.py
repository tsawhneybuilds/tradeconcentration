#!/usr/bin/env python3
"""Build an interactive HTML explainer for Exercise 12 results."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "results" / "exercise_12_tables"
OUTPUT = ROOT / "results" / "exercise_12_visual_explainer.html"

NET_PATH = TABLES / "growth_decomposition_net.csv"
GROSS_PATH = TABLES / "growth_decomposition_gross.csv"
TRANSITIONS_PATH = TABLES / "transition_matrices_detailed.csv"
HS_DIAG_PATH = TABLES / "hs_revision_pair_diagnostics.csv"
SCOPE_PATH = TABLES / "product_destination_region_states.csv"

COLORS = {
    "existing_top_10": "#2f6f73",
    "existing_non_top_10": "#8f5f2a",
    "new_item": "#c84b31",
    "gross_positive": "#2f6f73",
    "gross_contraction": "#b23a48",
    "product": "#2f6f73",
    "partner": "#8f5f2a",
    "product_partner_cell": "#c84b31",
}

DIMENSION_LABELS = {
    "partner": "Partner",
    "product": "Product",
    "product_partner_cell": "Product x destination cell",
}

MODE_LABELS = {
    "hs6_revision": "HS6 same revision",
    "hs4": "HS4",
    "hs2": "HS2",
    "cpa": "CPA sector",
    "partner": "Partner",
}

DRIVER_LABELS = {
    "existing_top_10": "Existing top 10",
    "existing_non_top_10": "Existing non-top",
    "new_item": "New item",
    "exited_top_10": "Exited top 10",
    "exited_non_top_10": "Exited non-top",
    "shrinking_top_10": "Shrinking top 10",
    "shrinking_non_top_10": "Shrinking non-top",
}


def require_inputs() -> None:
    missing = [path for path in [NET_PATH, GROSS_PATH, TRANSITIONS_PATH, HS_DIAG_PATH, SCOPE_PATH] if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing Exercise 12 result files: " + ", ".join(str(path) for path in missing))


def clean_records(df: pd.DataFrame) -> list[dict]:
    return json.loads(df.to_json(orient="records"))


def main_identity_filter(df: pd.DataFrame) -> pd.Series:
    return (
        (df["top_definition"] == "top_10")
        & (
            ((df["dimension"] == "partner") & (df["item_id_mode"] == "partner"))
            | ((df["dimension"].isin(["product", "product_partner_cell"])) & (df["item_id_mode"] == "hs6_revision"))
        )
    )


def add_labels(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "dimension" in out.columns:
        out["dimension_label"] = out["dimension"].map(DIMENSION_LABELS).fillna(out["dimension"])
    if "item_id_mode" in out.columns:
        out["item_mode_label"] = out["item_id_mode"].map(MODE_LABELS).fillna(out["item_id_mode"])
    if "driver_category" in out.columns:
        out["driver_label"] = out["driver_category"].map(DRIVER_LABELS).fillna(out["driver_category"])
    return out


def read_scope_summary() -> tuple[pd.DataFrame, pd.DataFrame]:
    usecols = ["unknown_partner_region_share", "region_transition_reliability"]
    scope = pd.read_csv(SCOPE_PATH, usecols=usecols)
    scope["unknown_partner_region_share"] = pd.to_numeric(scope["unknown_partner_region_share"], errors="coerce")
    reliability = scope["region_transition_reliability"].fillna("missing").value_counts().rename_axis("reliability").reset_index(name="rows")
    reliability["share"] = reliability["rows"] / reliability["rows"].sum()

    bins = [-0.001, 0.2, 0.5, 0.8, 0.95, 1.000001]
    labels = ["0-20%", "20-50%", "50-80%", "80-95%", "95-100%"]
    binned = pd.cut(scope["unknown_partner_region_share"], bins=bins, labels=labels, include_lowest=True)
    hist = binned.value_counts(sort=False).rename_axis("unknown_region_share").reset_index(name="rows")
    hist["share"] = hist["rows"] / hist["rows"].sum()
    return reliability, hist


def make_net_source(net: pd.DataFrame) -> pd.DataFrame:
    main = net[main_identity_filter(net)].copy()
    summary = (
        main.groupby(["dimension", "horizon", "driver_category"], as_index=False)["contribution_share"]
        .median()
        .sort_values(["dimension", "horizon", "driver_category"])
    )
    return add_labels(summary)


def make_margin_source(net: pd.DataFrame) -> pd.DataFrame:
    main = net[main_identity_filter(net) & (net["horizon"] == 5)].copy()
    keep = ["existing_top_10", "existing_non_top_10", "new_item"]
    summary = (
        main[main["driver_category"].isin(keep)]
        .groupby(["dimension", "driver_category"], as_index=False)["contribution_share"]
        .median()
        .sort_values(["dimension", "driver_category"])
    )
    return add_labels(summary)


def make_gross_source(gross: pd.DataFrame) -> pd.DataFrame:
    main = gross[main_identity_filter(gross) & (gross["horizon"] == 5)].copy()
    main["signed_contribution"] = main["contribution"].where(main["accounting_type"] == "gross_positive", -main["contribution"])
    summary = (
        main.groupby(["dimension", "accounting_type", "driver_category"], as_index=False)["signed_contribution"]
        .sum()
        .sort_values(["dimension", "accounting_type", "driver_category"])
    )
    summary["signed_contribution_trillions"] = summary["signed_contribution"] / 1_000_000_000_000
    return add_labels(summary)


def make_robustness_source(net: pd.DataFrame) -> pd.DataFrame:
    keep_modes = ["hs6_revision", "hs4", "hs2", "cpa"]
    keep_drivers = ["existing_non_top_10", "new_item"]
    work = net[
        (net["dimension"].isin(["product", "product_partner_cell"]))
        & (net["top_definition"] == "top_10")
        & (net["horizon"] == 5)
        & (net["item_id_mode"].isin(keep_modes))
        & (net["driver_category"].isin(keep_drivers))
    ].copy()
    summary = (
        work.groupby(["dimension", "item_id_mode", "driver_category"], as_index=False)["contribution_share"]
        .median()
        .sort_values(["dimension", "item_id_mode", "driver_category"])
    )
    return add_labels(summary)


def make_hs_source(hs_diag: pd.DataFrame) -> pd.DataFrame:
    work = hs_diag.copy()
    work["revision_pair"] = work["base_classification_code"].astype(str) + " -> " + work["future_classification_code"].astype(str)
    summary = (
        work.groupby(["dimension", "horizon", "revision_pair"], as_index=False)["excluded_base_value"]
        .sum()
        .sort_values("excluded_base_value", ascending=False)
    )
    summary["excluded_base_value_trillions"] = summary["excluded_base_value"] / 1_000_000_000_000
    return add_labels(summary.head(18))


def make_country_source(net: pd.DataFrame) -> pd.DataFrame:
    partner = net[
        (net["dimension"] == "partner")
        & (net["item_id_mode"] == "partner")
        & (net["top_definition"] == "top_10")
        & (net["horizon"] == 5)
        & (net["driver_category"] == "existing_top_10")
    ].copy()
    partner = partner.groupby(["country", "iso3"], as_index=False)["contribution_share"].median()
    partner = partner.rename(columns={"contribution_share": "existing_top_partner_share"})

    cells = net[
        (net["dimension"] == "product_partner_cell")
        & (net["item_id_mode"] == "hs6_revision")
        & (net["top_definition"] == "top_10")
        & (net["horizon"] == 5)
        & (net["driver_category"] == "new_item")
    ].copy()
    cells = cells.groupby(["country", "iso3"], as_index=False)["contribution_share"].median()
    cells = cells.rename(columns={"contribution_share": "new_cell_share"})
    return partner.merge(cells, on=["country", "iso3"], how="inner").sort_values("new_cell_share", ascending=False)


def make_transition_note_source(transitions: pd.DataFrame) -> dict:
    work = transitions[
        (transitions["dimension"] == "product_partner_cell")
        & (transitions["item_id_mode"] == "hs6_revision")
        & (transitions["top_definition"] == "top_10")
        & (transitions["horizon"] == 5)
    ].copy()
    if work.empty:
        return {"new_cell_item_share": None, "transition_rows": 0}
    work["is_new_cell"] = (work["base_state"] == "absent") & (work["future_state"] != "absent")
    total_items = float(work["item_count"].sum())
    new_items = float(work.loc[work["is_new_cell"], "item_count"].sum())
    return {
        "new_cell_item_share": new_items / total_items if total_items else None,
        "transition_rows": int(len(work)),
    }


def bar_trace(df: pd.DataFrame, name: str, x_col: str, y_col: str, color_key: str | None = None, **extra: object) -> dict:
    trace = {
        "type": "bar",
        "name": name,
        "x": df[x_col].tolist(),
        "y": df[y_col].tolist(),
        "marker": {"color": COLORS.get(color_key or name, "#4f6d7a")},
        "hovertemplate": "%{x}<br>%{y:.1%}<extra>" + name + "</extra>",
    }
    trace.update(extra)
    return trace


def build_figures(sources: dict[str, object]) -> dict[str, dict]:
    net_summary = sources["net_summary"]
    margin = sources["margin"]
    gross = sources["gross"]
    robustness = sources["robustness"]
    hs = sources["hs"]
    reliability = sources["reliability"]
    scope_hist = sources["scope_hist"]
    countries = sources["countries"]

    figures: dict[str, dict] = {}

    net_traces = []
    for driver in ["existing_top_10", "existing_non_top_10", "new_item"]:
        sub = net_summary[net_summary["driver_category"] == driver].copy()
        sub["view"] = sub["dimension_label"] + " (" + sub["horizon"].astype(str) + "y)"
        net_traces.append(bar_trace(sub, DRIVER_LABELS[driver], "view", "contribution_share", driver))
    figures["fig-net"] = {
        "data": net_traces,
        "layout": {
            "barmode": "stack",
            "margin": {"t": 20, "r": 20, "b": 90, "l": 60},
            "yaxis": {"title": "Median share of net growth", "tickformat": ".0%"},
            "xaxis": {"tickangle": -25},
            "legend": {"orientation": "h", "y": 1.15},
        },
    }

    margin_traces = []
    for driver in ["existing_top_10", "existing_non_top_10", "new_item"]:
        sub = margin[margin["driver_category"] == driver]
        margin_traces.append(bar_trace(sub, DRIVER_LABELS[driver], "dimension_label", "contribution_share", driver))
    figures["fig-margin"] = {
        "data": margin_traces,
        "layout": {
            "barmode": "group",
            "margin": {"t": 20, "r": 20, "b": 70, "l": 60},
            "yaxis": {"title": "Median 5-year net-growth share", "tickformat": ".0%"},
            "legend": {"orientation": "h", "y": 1.15},
        },
    }

    gross_traces = []
    gross_categories = [
        "existing_top_10",
        "existing_non_top_10",
        "new_item",
        "shrinking_top_10",
        "shrinking_non_top_10",
        "exited_top_10",
        "exited_non_top_10",
    ]
    gross_colors = {
        "existing_top_10": "#2f6f73",
        "existing_non_top_10": "#76a08a",
        "new_item": "#c84b31",
        "shrinking_top_10": "#b23a48",
        "shrinking_non_top_10": "#d9785f",
        "exited_top_10": "#7d1d2f",
        "exited_non_top_10": "#a54d60",
    }
    for driver in gross_categories:
        sub = gross[gross["driver_category"] == driver]
        if sub.empty:
            continue
        gross_traces.append(
            {
                "type": "bar",
                "name": DRIVER_LABELS.get(driver, driver),
                "x": sub["dimension_label"].tolist(),
                "y": sub["signed_contribution_trillions"].tolist(),
                "marker": {"color": gross_colors.get(driver, "#4f6d7a")},
                "hovertemplate": "%{x}<br>$%{y:.1f}T<extra>%{fullData.name}</extra>",
            }
        )
    figures["fig-churn"] = {
        "data": gross_traces,
        "layout": {
            "barmode": "relative",
            "margin": {"t": 20, "r": 20, "b": 70, "l": 70},
            "yaxis": {"title": "5-year gross contribution, USD trillions"},
            "legend": {"orientation": "h", "y": 1.28},
            "shapes": [{"type": "line", "x0": -0.5, "x1": 2.5, "y0": 0, "y1": 0, "line": {"color": "#333", "width": 1}}],
        },
    }

    robust_traces = []
    for dimension in ["product", "product_partner_cell"]:
        for driver in ["existing_non_top_10", "new_item"]:
            sub = robustness[(robustness["dimension"] == dimension) & (robustness["driver_category"] == driver)].copy()
            sub["series"] = DIMENSION_LABELS[dimension] + ": " + DRIVER_LABELS[driver]
            robust_traces.append(
                {
                    "type": "bar",
                    "name": sub["series"].iloc[0] if not sub.empty else "",
                    "x": sub["item_mode_label"].tolist(),
                    "y": sub["contribution_share"].tolist(),
                    "hovertemplate": "%{x}<br>%{y:.1%}<extra>%{fullData.name}</extra>",
                }
            )
    figures["fig-robust"] = {
        "data": robust_traces,
        "layout": {
            "barmode": "group",
            "margin": {"t": 20, "r": 20, "b": 70, "l": 60},
            "yaxis": {"title": "Median 5-year net-growth share", "tickformat": ".0%"},
            "legend": {"orientation": "h", "y": 1.25},
        },
    }

    hs["label"] = hs["dimension_label"] + ", " + hs["horizon"].astype(str) + "y, " + hs["revision_pair"]
    figures["fig-hs"] = {
        "data": [
            {
                "type": "bar",
                "orientation": "h",
                "x": hs["excluded_base_value_trillions"].tolist(),
                "y": hs["label"].tolist(),
                "marker": {"color": "#8f5f2a"},
                "hovertemplate": "%{y}<br>$%{x:.1f}T excluded base value<extra></extra>",
            }
        ],
        "layout": {
            "margin": {"t": 20, "r": 20, "b": 60, "l": 190},
            "xaxis": {"title": "Excluded base value, USD trillions"},
            "yaxis": {"automargin": True},
        },
    }

    figures["fig-region"] = {
        "data": [
            {
                "type": "bar",
                "name": "Unknown-region share bucket",
                "x": scope_hist["unknown_region_share"].astype(str).tolist(),
                "y": scope_hist["share"].tolist(),
                "marker": {"color": "#b23a48"},
                "hovertemplate": "%{x}<br>%{y:.1%} of product-year identities<extra></extra>",
            },
            {
                "type": "bar",
                "name": "Low-reliability rows",
                "x": reliability["reliability"].tolist(),
                "y": reliability["share"].tolist(),
                "marker": {"color": "#2f6f73"},
                "visible": "legendonly",
                "hovertemplate": "%{x}<br>%{y:.1%}<extra></extra>",
            },
        ],
        "layout": {
            "barmode": "group",
            "margin": {"t": 20, "r": 20, "b": 80, "l": 60},
            "yaxis": {"title": "Share", "tickformat": ".0%"},
            "legend": {"orientation": "h", "y": 1.15},
        },
    }

    figures["fig-country"] = {
        "data": [
            {
                "type": "scatter",
                "mode": "markers+text",
                "x": countries["existing_top_partner_share"].tolist(),
                "y": countries["new_cell_share"].tolist(),
                "text": countries["iso3"].tolist(),
                "textposition": "top center",
                "marker": {"size": 11, "color": "#2f6f73", "line": {"color": "#0f2027", "width": 1}},
                "customdata": countries[["country", "iso3"]].values.tolist(),
                "hovertemplate": "%{customdata[0]} (%{customdata[1]})<br>Top-partner share: %{x:.1%}<br>New-cell share: %{y:.1%}<extra></extra>",
            }
        ],
        "layout": {
            "margin": {"t": 20, "r": 20, "b": 70, "l": 70},
            "xaxis": {"title": "Median share from existing top partners", "tickformat": ".0%"},
            "yaxis": {"title": "Median share from new product-destination cells", "tickformat": ".0%"},
        },
    }

    return figures


def card_html(card_id: str, eyebrow: str, question: str, answer: str, caveat: str | None = None) -> str:
    caveat_html = f'<p class="caveat">{caveat}</p>' if caveat else ""
    return f"""
      <section class="card">
        <div class="card-copy">
          <span class="eyebrow">{eyebrow}</span>
          <h2>{question}</h2>
          <p>{answer}</p>
          {caveat_html}
        </div>
        <div id="{card_id}" class="chart" role="img" aria-label="{question}"></div>
      </section>
    """


def build_html(figures: dict[str, dict], coverage: dict, transition_note: dict) -> str:
    figures_json = json.dumps(figures, separators=(",", ":"))
    coverage_json = json.dumps(coverage, separators=(",", ":"))
    new_cell_share = transition_note.get("new_cell_item_share")
    new_cell_text = "The transition matrix also shows a large absent-to-active margin." if new_cell_share is None else (
        f"The transition matrix says about {new_cell_share:.1%} of 5-year HS6 product-destination cell transitions are absent-to-active."
    )
    cards = [
        card_html(
            "fig-net",
            "Question 1",
            "Where did net export growth come from?",
            "The main accounting split says partner growth is mostly incumbent top partners, product growth is mostly smaller incumbent products, and product-destination cell growth is heavily about new cells.",
            "HS6 product and product-destination views use only same-revision comparisons, so only the conservative 5-year HS6 horizon appears for those dimensions.",
        ),
        card_html(
            "fig-margin",
            "Question 2",
            "Is this really new products, or new markets for existing products?",
            "The 5-year comparison separates products, partners, and product-destination cells. New products are small, but new product-destination cells are large, which points to market expansion along the extensive margin. " + new_cell_text,
        ),
        card_html(
            "fig-churn",
            "Question 3",
            "How much churn does net growth hide?",
            "Gross accounting shows the flows behind the net number. Expansions and contractions both concentrate in incumbent categories, so a calm net figure can hide a lot of turnover underneath.",
            "Bars above zero are gross positive growth; bars below zero are gross contraction, both summed over the 5-year accounting sample.",
        ),
        card_html(
            "fig-robust",
            "Question 4",
            "Do conclusions change when product identity is coarser?",
            "HS4, HS2, and CPA mappings compress products into broader groups. If the story survives across coarser identities, it is less likely to be an artifact of fragile HS6 codes.",
            "HS6 same-revision is still the conservative main view; coarser mappings are robustness checks.",
        ),
        card_html(
            "fig-hs",
            "Question 5",
            "How much product comparison is excluded when HS revisions changed?",
            "A large amount of base export value is excluded from conservative HS6 transition accounting when the base and future years use different HS revisions. That is the measurement reason bare cmd_code transitions were unsafe.",
        ),
        card_html(
            "fig-region",
            "Question 6",
            "Can we trust regional-to-global destination labels?",
            "The region metadata is weak in this run: product-year identities mostly have high unknown-region shares. Destination counts are safer than region labels for this exercise.",
            "The page keeps destination and region transitions descriptive and discounts any region-transition claim when unknown-region shares are high.",
        ),
        card_html(
            "fig-country",
            "Question 7",
            "Which countries look most different?",
            "The country scatter shows two different margins: dependence on existing top partners and growth from new product-destination cells. Countries can look similar in one margin and very different in the other.",
            "This is heterogeneity in accounting outcomes, not evidence about mechanisms.",
        ),
    ]
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Exercise 12 Visual Explainer</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    :root {{
      --ink: #172124;
      --muted: #5b686d;
      --line: #d9e1df;
      --paper: #f6f4ef;
      --panel: #ffffff;
      --accent: #2f6f73;
      --warn: #b23a48;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--paper);
      line-height: 1.45;
    }}
    header {{
      padding: 48px clamp(20px, 5vw, 72px) 28px;
      background: #ffffff;
      border-bottom: 1px solid var(--line);
    }}
    main {{ padding: 26px clamp(16px, 4vw, 56px) 56px; }}
    h1 {{ margin: 0 0 10px; font-size: clamp(32px, 5vw, 56px); line-height: 1.02; letter-spacing: 0; }}
    h2 {{ margin: 6px 0 10px; font-size: clamp(20px, 2.4vw, 30px); line-height: 1.15; letter-spacing: 0; }}
    p {{ margin: 0; color: var(--muted); max-width: 78ch; }}
    .subtitle {{ font-size: 18px; max-width: 880px; }}
    .badges {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 24px;
    }}
    .badge {{
      border: 1px solid var(--line);
      background: #f9faf8;
      border-radius: 6px;
      padding: 8px 10px;
      font-size: 13px;
      color: var(--ink);
    }}
    .note {{
      margin-top: 20px;
      border-left: 4px solid var(--accent);
      padding: 12px 14px;
      background: #eef5f3;
      color: var(--ink);
      max-width: 980px;
    }}
    .card {{
      display: grid;
      grid-template-columns: minmax(260px, 0.9fr) minmax(360px, 1.4fr);
      gap: 26px;
      align-items: stretch;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: clamp(18px, 3vw, 28px);
      margin: 18px auto;
      max-width: 1280px;
      box-shadow: 0 8px 24px rgba(23, 33, 36, 0.05);
    }}
    .card-copy {{ align-self: center; }}
    .eyebrow {{
      display: inline-block;
      font-size: 12px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--accent);
      font-weight: 700;
    }}
    .caveat {{
      margin-top: 14px;
      color: #6f4b17;
      background: #fbf1df;
      border: 1px solid #ecd4a8;
      padding: 10px 12px;
      border-radius: 6px;
    }}
    .chart {{ min-height: 430px; width: 100%; }}
    footer {{
      color: var(--muted);
      padding: 10px clamp(20px, 5vw, 72px) 40px;
      font-size: 13px;
    }}
    @media (max-width: 860px) {{
      .card {{ grid-template-columns: 1fr; }}
      .chart {{ min-height: 360px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Exercise 12: Where Export Growth Came From</h1>
    <p class="subtitle">A visual accounting explainer for product, partner, and product-destination transitions. The charts use real Exercise 12 output tables and are descriptive accounting evidence.</p>
    <div class="badges" id="coverage-badges"></div>
    <p class="note">Read this like an economist doing measurement: the question is "which accounting margins mechanically add up to growth?" HS6 product comparisons are conservative and exclude cross-revision comparisons.</p>
  </header>
  <main>
    {''.join(cards)}
  </main>
  <footer>
    Generated {coverage["generated_at"]}. Data source: Exercise 12 CSV outputs in results/exercise_12_tables. No fake or proxy trade data is embedded.
  </footer>
  <script>
    const FIGURES = {figures_json};
    const COVERAGE = {coverage_json};
    const config = {{responsive: true, displaylogo: false}};

    const badges = [
      ["Countries", COVERAGE.countries],
      ["Net rows", COVERAGE.net_rows.toLocaleString()],
      ["Gross rows", COVERAGE.gross_rows.toLocaleString()],
      ["Transition rows", COVERAGE.transition_rows.toLocaleString()],
      ["HS diagnostic rows", COVERAGE.hs_diag_rows.toLocaleString()],
      ["Years", COVERAGE.year_min + "-" + COVERAGE.year_max]
    ];
    document.getElementById("coverage-badges").innerHTML = badges
      .map(([k, v]) => `<span class="badge"><strong>${{k}}:</strong> ${{v}}</span>`)
      .join("");

    for (const [id, fig] of Object.entries(FIGURES)) {{
      Plotly.newPlot(id, fig.data, fig.layout, config);
    }}
  </script>
</body>
</html>
"""


def main() -> None:
    require_inputs()
    net = pd.read_csv(NET_PATH)
    gross = pd.read_csv(GROSS_PATH)
    transitions = pd.read_csv(TRANSITIONS_PATH)
    hs_diag = pd.read_csv(HS_DIAG_PATH)
    reliability, scope_hist = read_scope_summary()

    sources = {
        "net_summary": make_net_source(net),
        "margin": make_margin_source(net),
        "gross": make_gross_source(gross),
        "robustness": make_robustness_source(net),
        "hs": make_hs_source(hs_diag),
        "reliability": reliability,
        "scope_hist": scope_hist,
        "countries": make_country_source(net),
    }
    transition_note = make_transition_note_source(transitions)
    figures = build_figures(sources)
    coverage = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "countries": int(net["reporter_code"].nunique()),
        "year_min": int(net["year"].min()),
        "year_max": int(net["future_year"].max()),
        "net_rows": int(len(net)),
        "gross_rows": int(len(gross)),
        "transition_rows": int(len(transitions)),
        "hs_diag_rows": int(len(hs_diag)),
        "scope_rows": int(reliability["rows"].sum()),
    }
    OUTPUT.write_text(build_html(figures, coverage, transition_note), encoding="utf-8")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
