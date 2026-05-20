#!/usr/bin/env python3
"""Create a standalone interactive world map for trade concentration Ginis."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from plotly.offline import get_plotlyjs


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "results" / "exercise_01_tables" / "concentration_all_years.csv"
DEFAULT_EXERCISE_2_INPUT = ROOT / "results" / "exercise_02_tables" / "export_concentration_panel.csv"
DEFAULT_OUTPUT = ROOT / "results" / "maps" / "trade_gini_world_map.html"

METRICS = {
    "product_gini": "Product Gini",
    "partner_gini": "Partner Gini",
    "product_partner_cell_gini": "Product-Partner Cell Gini",
}

REQUIRED_COLUMNS = {
    "iso3",
    "country",
    "year",
    "flow",
    "variant",
    "total_trade_value",
    "product_gini",
    "partner_gini",
    "product_partner_cell_gini",
    "product_active_count",
    "partner_active_count",
    "product_partner_cell_active_count",
}

EXERCISE_2_REQUIRED_COLUMNS = {
    "iso3",
    "country",
    "year",
    "flow",
    "variant",
    "total_exports",
    "product_gini",
    "partner_gini",
}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_and_validate(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Input panel not found: {path}")

    df = pd.read_csv(path)
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise RuntimeError(f"Input panel is missing required columns: {sorted(missing)}")

    df = df[df["variant"].astype(str).str.lower().eq("baseline")].copy()
    if df.empty:
        raise RuntimeError("No baseline rows found in Exercise 1 panel.")

    for col in [
        "year",
        "total_trade_value",
        "product_gini",
        "partner_gini",
        "product_partner_cell_gini",
        "product_active_count",
        "partner_active_count",
        "product_partner_cell_active_count",
    ]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["iso3"] = df["iso3"].astype(str).str.upper().str.strip()
    df["country"] = df["country"].astype(str).str.strip()
    df["flow"] = df["flow"].astype(str).str.strip()
    df = df.dropna(subset=["iso3", "country", "year", "flow"])
    df["year"] = df["year"].astype(int)

    allowed_flows = {"Exports", "Imports"}
    bad_flows = sorted(set(df["flow"]) - allowed_flows)
    if bad_flows:
        raise RuntimeError(f"Unexpected flow labels in panel: {bad_flows}")

    duplicate_keys = df.duplicated(subset=["iso3", "year", "flow"], keep=False)
    if duplicate_keys.any():
        examples = df.loc[duplicate_keys, ["iso3", "year", "flow"]].head(10).to_dict("records")
        raise RuntimeError(f"Duplicate country-year-flow rows found. Examples: {examples}")

    return df.sort_values(["country", "year", "flow"]).reset_index(drop=True)


def read_exercise_2_panel(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Exercise 2 export panel not found: {path}")

    df = pd.read_csv(path)
    missing = EXERCISE_2_REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise RuntimeError(f"Exercise 2 panel is missing required columns: {sorted(missing)}")

    df = df[df["variant"].astype(str).str.lower().eq("baseline")].copy()
    if df.empty:
        raise RuntimeError("No baseline rows found in Exercise 2 export panel.")

    for col in ["year", "total_exports", "product_gini", "partner_gini"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["iso3"] = df["iso3"].astype(str).str.upper().str.strip()
    df["country"] = df["country"].astype(str).str.strip()
    df["flow"] = df["flow"].astype(str).str.strip()
    df = df[df["flow"].eq("Exports")].copy()
    df = df.dropna(subset=["iso3", "country", "year", "flow"])
    df["year"] = df["year"].astype(int)

    duplicate_keys = df.duplicated(subset=["iso3", "year", "flow"], keep=False)
    if duplicate_keys.any():
        examples = df.loc[duplicate_keys, ["iso3", "year", "flow"]].head(10).to_dict("records")
        raise RuntimeError(f"Duplicate Exercise 2 country-year-flow rows found. Examples: {examples}")

    return df.sort_values(["country", "year"]).reset_index(drop=True)


def json_ready(value: object) -> object:
    if pd.isna(value):
        return None
    if isinstance(value, float):
        return round(value, 12)
    if hasattr(value, "item"):
        return value.item()
    return value


def panel_rows(df: pd.DataFrame) -> list[dict[str, object]]:
    columns = [
        "iso3",
        "country",
        "year",
        "flow",
        "total_trade_value",
        "product_gini",
        "partner_gini",
        "product_partner_cell_gini",
        "product_active_count",
        "partner_active_count",
        "product_partner_cell_active_count",
    ]
    return [
        {column: json_ready(row[column]) for column in columns}
        for row in df[columns].to_dict(orient="records")
    ]


def country_rows(df: pd.DataFrame) -> list[dict[str, str]]:
    countries = df[["iso3", "country"]].drop_duplicates().sort_values("country")
    return countries.to_dict(orient="records")


def line_panel_rows(ex1: pd.DataFrame, ex2: pd.DataFrame) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []

    for row in ex1.to_dict(orient="records"):
        rows.append(
            {
                "exercise": "exercise_01",
                "iso3": json_ready(row["iso3"]),
                "country": json_ready(row["country"]),
                "year": json_ready(row["year"]),
                "flow": json_ready(row["flow"]),
                "product_gini": json_ready(row["product_gini"]),
                "partner_gini": json_ready(row["partner_gini"]),
                "total_trade_value": json_ready(row["total_trade_value"]),
            }
        )

    for row in ex2.to_dict(orient="records"):
        rows.append(
            {
                "exercise": "exercise_02",
                "iso3": json_ready(row["iso3"]),
                "country": json_ready(row["country"]),
                "year": json_ready(row["year"]),
                "flow": "Exports",
                "product_gini": json_ready(row["product_gini"]),
                "partner_gini": json_ready(row["partner_gini"]),
                "total_trade_value": json_ready(row["total_exports"]),
            }
        )

    return rows


def render_html(df: pd.DataFrame, exercise_2_df: pd.DataFrame, source_path: Path, exercise_2_source_path: Path) -> str:
    rows_json = json.dumps(panel_rows(df), separators=(",", ":"), allow_nan=False).replace("</", "<\\/")
    countries_json = json.dumps(country_rows(df), separators=(",", ":"), allow_nan=False).replace("</", "<\\/")
    line_rows_json = json.dumps(line_panel_rows(df, exercise_2_df), separators=(",", ":"), allow_nan=False).replace("</", "<\\/")
    metrics_json = json.dumps(METRICS, separators=(",", ":"), allow_nan=False)
    plotly_js = get_plotlyjs()
    years = sorted(int(year) for year in df["year"].unique())
    flows = sorted(df["flow"].unique())

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Trade Concentration Gini Map</title>
  <style>
    :root {{
      --bg: #f8fafc;
      --panel: #ffffff;
      --text: #111827;
      --muted: #4b5563;
      --line: #d1d5db;
      --accent: #1d4ed8;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
    }}
    main {{
      max-width: 1280px;
      margin: 0 auto;
      padding: 22px 24px 18px;
    }}
    header {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 16px;
      align-items: end;
      margin-bottom: 12px;
    }}
    h1 {{
      margin: 0 0 4px;
      font-size: 26px;
      font-weight: 700;
      letter-spacing: 0;
    }}
    .subtitle {{
      margin: 0;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.4;
    }}
    .controls {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: flex-end;
      align-items: center;
    }}
    label {{
      display: grid;
      gap: 4px;
      font-size: 12px;
      color: var(--muted);
      font-weight: 600;
    }}
    select {{
      min-width: 150px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      color: var(--text);
      padding: 8px 10px;
      font-size: 14px;
    }}
    .map-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }}
    .section-heading {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: end;
      margin: 28px 0 10px;
    }}
    h2 {{
      margin: 0;
      font-size: 20px;
      font-weight: 700;
      letter-spacing: 0;
    }}
    .line-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }}
    .line-toolbar {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: end;
      justify-content: space-between;
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      background: #ffffff;
    }}
    .line-toolbar-group {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: end;
    }}
    input[type="search"] {{
      min-width: 220px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      color: var(--text);
      padding: 8px 10px;
      font-size: 14px;
    }}
    button {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
      color: var(--text);
      padding: 8px 10px;
      font-size: 14px;
      cursor: pointer;
    }}
    button:hover {{
      border-color: var(--accent);
      color: var(--accent);
    }}
    .line-layout {{
      display: grid;
      grid-template-columns: 250px minmax(0, 1fr);
      min-height: 620px;
    }}
    .country-panel {{
      border-right: 1px solid var(--line);
      background: #f9fafb;
      padding: 12px;
    }}
    .country-count {{
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      margin-bottom: 8px;
    }}
    .country-list {{
      display: grid;
      gap: 3px;
      max-height: 548px;
      overflow: auto;
      padding-right: 4px;
    }}
    .country-item {{
      display: flex;
      align-items: center;
      gap: 7px;
      min-height: 28px;
      color: var(--text);
      font-size: 13px;
      font-weight: 500;
    }}
    .country-item input {{
      accent-color: var(--accent);
      width: 15px;
      height: 15px;
      flex: 0 0 auto;
    }}
    .line-main {{
      min-width: 0;
      display: grid;
      grid-template-rows: minmax(520px, 1fr) auto;
    }}
    #lineChart {{
      width: 100%;
      height: 580px;
    }}
    .line-info {{
      min-height: 60px;
      border-top: 1px solid var(--line);
      padding: 10px 14px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
      background: #ffffff;
    }}
    .line-info strong {{
      color: var(--text);
    }}
    #map {{
      width: 100%;
      height: min(72vh, 760px);
      min-height: 520px;
    }}
    .slider-panel {{
      display: grid;
      grid-template-columns: auto 1fr auto;
      gap: 14px;
      align-items: center;
      padding: 12px 16px 16px;
      border-top: 1px solid var(--line);
      background: #ffffff;
    }}
    .year-label {{
      font-size: 13px;
      color: var(--muted);
      font-weight: 700;
      min-width: 72px;
    }}
    #yearValue {{
      color: var(--accent);
      font-variant-numeric: tabular-nums;
    }}
    input[type="range"] {{
      width: 100%;
      accent-color: var(--accent);
    }}
    .status {{
      font-size: 13px;
      color: var(--muted);
      min-width: 190px;
      text-align: right;
    }}
    .note {{
      margin: 10px 2px 0;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }}
    @media (max-width: 760px) {{
      main {{ padding: 14px; }}
      header {{ grid-template-columns: 1fr; }}
      .controls {{ justify-content: stretch; }}
      label, select, input[type="search"] {{ width: 100%; }}
      #map {{ min-height: 440px; height: 64vh; }}
      .slider-panel {{ grid-template-columns: 1fr; gap: 8px; }}
      .status {{ text-align: left; }}
      .section-heading {{ display: block; }}
      .line-layout {{ grid-template-columns: 1fr; }}
      .country-panel {{ border-right: 0; border-bottom: 1px solid var(--line); }}
      .country-list {{ max-height: 210px; }}
      #lineChart {{ height: 520px; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Trade Concentration Gini Map</h1>
        <p class="subtitle">Thirty-three-country annual HS6 merchandise trade concentration panel.</p>
      </div>
      <div class="controls" aria-label="Map controls">
        <label>
          Flow
          <select id="flowSelect">
            {"".join(f'<option value="{flow}"{" selected" if flow == "Exports" else ""}>{flow}</option>' for flow in flows)}
          </select>
        </label>
        <label>
          Metric
          <select id="metricSelect">
            <option value="product_gini" selected>Product Gini</option>
            <option value="partner_gini">Partner Gini</option>
            <option value="product_partner_cell_gini">Product-Partner Cell Gini</option>
          </select>
        </label>
      </div>
    </header>

    <section class="map-card">
      <div id="map" role="img" aria-label="Interactive world map of trade concentration Gini by country"></div>
      <div class="slider-panel">
        <div class="year-label">Year: <span id="yearValue">{years[-1]}</span></div>
        <input id="yearSlider" type="range" min="0" max="{len(years) - 1}" value="{len(years) - 1}" step="1" aria-label="Year slider">
        <div id="status" class="status"></div>
      </div>
    </section>

    <section aria-labelledby="lineTitle">
      <div class="section-heading">
        <div>
          <h2 id="lineTitle">Country Gini Lines</h2>
          <p class="subtitle">Exercise 1 and Exercise 2 country-year Gini paths.</p>
        </div>
      </div>
      <div class="line-card">
        <div class="line-toolbar">
          <div class="line-toolbar-group">
            <label>
              Graph
              <select id="lineChartSelect">
                <option value="ex1_exports_product" selected>Exercise 1: Export Product Gini</option>
                <option value="ex1_imports_product">Exercise 1: Import Product Gini</option>
                <option value="ex2_exports_product">Exercise 2: Export Product Gini</option>
                <option value="ex2_exports_partner">Exercise 2: Export Partner Gini</option>
              </select>
            </label>
            <label>
              Country Search
              <input id="countrySearch" type="search" autocomplete="off" placeholder="Type country name">
            </label>
          </div>
          <div class="line-toolbar-group" aria-label="Country selection controls">
            <button id="selectAllCountries" type="button">All Countries</button>
            <button id="clearCountries" type="button">Clear</button>
            <button id="selectIndiaPeers" type="button">India + Peers</button>
          </div>
        </div>
        <div class="line-layout">
          <aside class="country-panel" aria-label="Country filter">
            <div id="countryCount" class="country-count"></div>
            <div id="countryList" class="country-list"></div>
          </aside>
          <div class="line-main">
            <div id="lineChart" role="img" aria-label="Interactive line chart of Gini over time by country"></div>
            <div id="lineInfo" class="line-info"></div>
          </div>
        </div>
      </div>
    </section>

    <p class="note">
      Source: UN Comtrade HS6 annual reporter-product-partner data; concentration measures from Exercise 1 baseline panel.
      Analytical framing follows Panagariya and Bagaria (2013), "Some Surprising Facts About the Concentration of Trade Across Commodities and Trading Partners," <em>The World Economy</em>.
      Generated {now_utc()} from <code>{source_path.relative_to(ROOT)}</code> and <code>{exercise_2_source_path.relative_to(ROOT)}</code>. Missing country-year-flow observations are shown in gray; no values are interpolated.
    </p>
  </main>

  <script>
{plotly_js}
  </script>
  <script>
    const PANEL_ROWS = {rows_json};
    const LINE_ROWS = {line_rows_json};
    const COUNTRIES = {countries_json};
    const METRICS = {metrics_json};
    const YEARS = {json.dumps(years)};
    const Z_MIN = 0.75;
    const Z_MAX = 1.00;
    const LINE_CHARTS = {{
      ex1_exports_product: {{
        label: "Exercise 1: Export Product Gini",
        exercise: "exercise_01",
        flow: "Exports",
        metric: "product_gini",
        yTitle: "Product Gini"
      }},
      ex1_imports_product: {{
        label: "Exercise 1: Import Product Gini",
        exercise: "exercise_01",
        flow: "Imports",
        metric: "product_gini",
        yTitle: "Product Gini"
      }},
      ex2_exports_product: {{
        label: "Exercise 2: Export Product Gini",
        exercise: "exercise_02",
        flow: "Exports",
        metric: "product_gini",
        yTitle: "Product Gini"
      }},
      ex2_exports_partner: {{
        label: "Exercise 2: Export Partner Gini",
        exercise: "exercise_02",
        flow: "Exports",
        metric: "partner_gini",
        yTitle: "Partner Gini"
      }}
    }};
    const LINE_COLORS = [
      "#2563eb", "#dc2626", "#059669", "#9333ea", "#ea580c", "#0891b2",
      "#be123c", "#4f46e5", "#16a34a", "#c2410c", "#0f766e", "#7c3aed",
      "#b45309", "#0284c7", "#a21caf", "#65a30d", "#e11d48", "#1d4ed8",
      "#047857", "#b91c1c", "#6d28d9", "#0369a1", "#ca8a04", "#15803d",
      "#db2777", "#4338ca", "#0e7490", "#a16207", "#166534", "#9f1239",
      "#7e22ce", "#1e40af", "#991b1b"
    ];
    const INDIA_PEERS = new Set(["India", "China", "Korea", "Japan", "Germany", "United States", "Vietnam"]);

    const mapDiv = document.getElementById("map");
    const lineChartDiv = document.getElementById("lineChart");
    const flowSelect = document.getElementById("flowSelect");
    const metricSelect = document.getElementById("metricSelect");
    const yearSlider = document.getElementById("yearSlider");
    const yearValue = document.getElementById("yearValue");
    const status = document.getElementById("status");
    const lineChartSelect = document.getElementById("lineChartSelect");
    const countrySearch = document.getElementById("countrySearch");
    const countryList = document.getElementById("countryList");
    const countryCount = document.getElementById("countryCount");
    const lineInfo = document.getElementById("lineInfo");
    const selectAllCountries = document.getElementById("selectAllCountries");
    const clearCountries = document.getElementById("clearCountries");
    const selectIndiaPeers = document.getElementById("selectIndiaPeers");
    const selectedCountries = new Set(COUNTRIES.map(row => row.country));

    function formatMoney(value) {{
      if (value === null || value === undefined || Number.isNaN(Number(value))) return "n/a";
      return new Intl.NumberFormat("en-US", {{
        style: "currency",
        currency: "USD",
        notation: "compact",
        maximumFractionDigits: 2
      }}).format(value);
    }}

    function formatInt(value) {{
      if (value === null || value === undefined || Number.isNaN(Number(value))) return "n/a";
      return new Intl.NumberFormat("en-US", {{ maximumFractionDigits: 0 }}).format(value);
    }}

    function formatGini(value) {{
      if (value === null || value === undefined || Number.isNaN(Number(value))) return "n/a";
      return Number(value).toFixed(3);
    }}

    function selectedYear() {{
      return YEARS[Number(yearSlider.value)];
    }}

    function selectedRows() {{
      const year = selectedYear();
      const flow = flowSelect.value;
      return PANEL_ROWS.filter(row => row.year === year && row.flow === flow);
    }}

    function hoverText(row, metric) {{
      return [
        `<b>${{row.country}}</b> (${{row.iso3}})`,
        `Year: ${{row.year}}`,
        `Flow: ${{row.flow}}`,
        `${{METRICS[metric]}}: ${{formatGini(row[metric])}}`,
        `Total trade value: ${{formatMoney(row.total_trade_value)}}`,
        `Active products: ${{formatInt(row.product_active_count)}}`,
        `Active partners: ${{formatInt(row.partner_active_count)}}`,
        `Active product-partner cells: ${{formatInt(row.product_partner_cell_active_count)}}`
      ].join("<br>");
    }}

    function buildColoredTrace(rows, metric) {{
      return {{
        type: "choropleth",
        locationmode: "ISO-3",
        locations: rows.map(row => row.iso3),
        z: rows.map(row => row[metric]),
        text: rows.map(row => hoverText(row, metric)),
        hovertemplate: "%{{text}}<extra></extra>",
        colorscale: [
          [0.00, "#eff6ff"],
          [0.20, "#bfdbfe"],
          [0.40, "#60a5fa"],
          [0.60, "#2563eb"],
          [0.80, "#1e40af"],
          [1.00, "#172554"]
        ],
        zmin: Z_MIN,
        zmax: Z_MAX,
        colorbar: {{
          title: METRICS[metric],
          tickformat: ".2f",
          len: 0.72
        }},
        marker: {{
          line: {{ color: "#ffffff", width: 0.7 }}
        }},
        name: "Available data"
      }};
    }}

    function buildMissingTrace() {{
      return {{
        type: "choropleth",
        locationmode: "ISO-3",
        locations: COUNTRIES.map(row => row.iso3),
        z: COUNTRIES.map(() => 0),
        text: COUNTRIES.map(row => `<b>${{row.country}}</b> (${{row.iso3}})<br>No available data for the selected year and flow.`),
        hovertemplate: "%{{text}}<extra></extra>",
        colorscale: [[0, "#d1d5db"], [1, "#d1d5db"]],
        showscale: false,
        marker: {{
          line: {{ color: "#ffffff", width: 0.7 }}
        }},
        name: "Missing data"
      }};
    }}

    function layoutTitle(year, flow, metric) {{
      return `${{METRICS[metric]}} by Country, ${{flow}}, ${{year}}`;
    }}

    function updateMap(firstDraw = false) {{
      const year = selectedYear();
      const flow = flowSelect.value;
      const metric = metricSelect.value;
      const rows = selectedRows();
      yearValue.textContent = year;
      status.textContent = `${{rows.length}} of ${{COUNTRIES.length}} countries available`;

      const traces = [buildMissingTrace(), buildColoredTrace(rows, metric)];
      const layout = {{
        title: {{
          text: layoutTitle(year, flow, metric),
          x: 0.02,
          xanchor: "left",
          font: {{ size: 18 }}
        }},
        margin: {{ l: 8, r: 8, t: 48, b: 8 }},
        paper_bgcolor: "#ffffff",
        plot_bgcolor: "#ffffff",
        geo: {{
          projection: {{ type: "natural earth" }},
          showframe: false,
          showcountries: true,
          countrycolor: "#ffffff",
          showland: true,
          landcolor: "#f3f4f6",
          showocean: true,
          oceancolor: "#eef2ff",
          bgcolor: "#ffffff"
        }},
        annotations: [{{
          text: "Fixed color scale: 0.75 to 1.00",
          x: 0,
          y: 0,
          xref: "paper",
          yref: "paper",
          xanchor: "left",
          yanchor: "bottom",
          showarrow: false,
          font: {{ size: 12, color: "#4b5563" }},
          bgcolor: "rgba(255,255,255,0.78)",
          borderpad: 4
        }}]
      }};
      const config = {{
        responsive: true,
        displaylogo: false,
        modeBarButtonsToRemove: ["lasso2d", "select2d"]
      }};

      if (firstDraw) {{
        Plotly.newPlot(mapDiv, traces, layout, config);
      }} else {{
        Plotly.react(mapDiv, traces, layout, config);
      }}
    }}

    function escapeHtml(value) {{
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }}

    function currentLineSpec() {{
      return LINE_CHARTS[lineChartSelect.value];
    }}

    function rowsForLineChart() {{
      const spec = currentLineSpec();
      return LINE_ROWS.filter(row =>
        row.exercise === spec.exercise &&
        row.flow === spec.flow &&
        selectedCountries.has(row.country) &&
        row[spec.metric] !== null &&
        row[spec.metric] !== undefined
      );
    }}

    function renderCountryList() {{
      const query = countrySearch.value.trim().toLowerCase();
      const visibleCountries = COUNTRIES
        .map(row => row.country)
        .filter(country => country.toLowerCase().includes(query));
      countryList.innerHTML = "";

      for (const country of visibleCountries) {{
        const id = `country-${{country.replace(/[^a-z0-9]/gi, "-")}}`;
        const label = document.createElement("label");
        label.className = "country-item";
        label.setAttribute("for", id);

        const input = document.createElement("input");
        input.type = "checkbox";
        input.id = id;
        input.value = country;
        input.checked = selectedCountries.has(country);
        input.addEventListener("change", () => {{
          if (input.checked) {{
            selectedCountries.add(country);
          }} else {{
            selectedCountries.delete(country);
          }}
          updateLineChart(false);
        }});

        const span = document.createElement("span");
        span.textContent = country;
        label.append(input, span);
        countryList.appendChild(label);
      }}

      countryCount.textContent = `${{selectedCountries.size}} of ${{COUNTRIES.length}} countries selected`;
    }}

    function groupedLineRows(rows) {{
      const groups = new Map();
      for (const row of rows) {{
        if (!groups.has(row.country)) groups.set(row.country, []);
        groups.get(row.country).push(row);
      }}
      return [...groups.entries()]
        .sort((a, b) => a[0].localeCompare(b[0]))
        .map(([country, values]) => [country, values.sort((a, b) => a.year - b.year)]);
    }}

    function lineHoverText(row, spec) {{
      return [
        `<b>${{escapeHtml(row.country)}}</b> (${{escapeHtml(row.iso3)}})`,
        `Year: ${{row.year}}`,
        `Series: ${{escapeHtml(spec.label)}}`,
        `${{escapeHtml(spec.yTitle)}}: ${{formatGini(row[spec.metric])}}`,
        `Trade value: ${{formatMoney(row.total_trade_value)}}`
      ].join("<br>");
    }}

    function lineTrace(country, values, color, spec) {{
      return {{
        type: "scatter",
        mode: "lines+markers",
        name: country,
        x: values.map(row => row.year),
        y: values.map(row => row[spec.metric]),
        customdata: values.map(row => [row.country, row.iso3, row.year, row[spec.metric], row.total_trade_value, spec.label, spec.yTitle]),
        hovertext: values.map(row => lineHoverText(row, spec)),
        hovertemplate: "%{{hovertext}}<extra></extra>",
        line: {{ color, width: 2 }},
        marker: {{ color, size: 5 }},
        connectgaps: false
      }};
    }}

    function updateLineInfoFromPoint(point) {{
      if (!point || !point.customdata) return;
      const [country, iso3, year, gini, tradeValue, label, yTitle] = point.customdata;
      lineInfo.innerHTML = [
        `<strong>${{escapeHtml(country)}} (${{escapeHtml(iso3)}})</strong>`,
        `${{escapeHtml(label)}}`,
        `Year ${{year}}: ${{escapeHtml(yTitle)}} = <strong>${{formatGini(gini)}}</strong>`,
        `Trade value: ${{formatMoney(tradeValue)}}`
      ].join(" &nbsp; | &nbsp; ");
    }}

    function updateLineChart(firstDraw = false) {{
      renderCountryList();
      const spec = currentLineSpec();
      const rows = rowsForLineChart();
      const groups = groupedLineRows(rows);
      const traces = groups.map(([country, values], idx) =>
        lineTrace(country, values, LINE_COLORS[idx % LINE_COLORS.length], spec)
      );

      const layout = {{
        title: {{
          text: spec.label,
          x: 0.02,
          xanchor: "left",
          font: {{ size: 18 }}
        }},
        xaxis: {{
          title: "Year",
          range: [Math.min(...YEARS), Math.max(...YEARS)],
          tickformat: "d",
          gridcolor: "#e5e7eb",
          zeroline: false
        }},
        yaxis: {{
          title: spec.yTitle,
          range: [0.74, 1.0],
          tickformat: ".2f",
          gridcolor: "#e5e7eb",
          zeroline: false
        }},
        margin: {{ l: 64, r: 20, t: 56, b: 54 }},
        paper_bgcolor: "#ffffff",
        plot_bgcolor: "#ffffff",
        hovermode: "closest",
        legend: {{
          orientation: "v",
          x: 1.02,
          xanchor: "left",
          y: 1,
          font: {{ size: 10 }}
        }},
        annotations: groups.length ? [] : [{{
          text: "No countries selected",
          x: 0.5,
          y: 0.5,
          xref: "paper",
          yref: "paper",
          showarrow: false,
          font: {{ size: 16, color: "#4b5563" }}
        }}]
      }};

      const config = {{
        responsive: true,
        displaylogo: false,
        modeBarButtonsToRemove: ["lasso2d", "select2d"]
      }};

      if (firstDraw) {{
        Plotly.newPlot(lineChartDiv, traces, layout, config).then(() => {{
          lineChartDiv.on("plotly_click", event => updateLineInfoFromPoint(event.points?.[0]));
        }});
      }} else {{
        Plotly.react(lineChartDiv, traces, layout, config);
      }}

      lineInfo.innerHTML = groups.length
        ? `<strong>${{groups.length}}</strong> selected country lines shown for ${{escapeHtml(spec.label)}}.`
        : "No selected country lines.";
    }}

    flowSelect.addEventListener("change", () => updateMap(false));
    metricSelect.addEventListener("change", () => updateMap(false));
    yearSlider.addEventListener("input", () => updateMap(false));
    lineChartSelect.addEventListener("change", () => updateLineChart(false));
    countrySearch.addEventListener("input", renderCountryList);
    selectAllCountries.addEventListener("click", () => {{
      selectedCountries.clear();
      for (const row of COUNTRIES) selectedCountries.add(row.country);
      updateLineChart(false);
    }});
    clearCountries.addEventListener("click", () => {{
      selectedCountries.clear();
      updateLineChart(false);
    }});
    selectIndiaPeers.addEventListener("click", () => {{
      selectedCountries.clear();
      for (const row of COUNTRIES) {{
        if (INDIA_PEERS.has(row.country)) selectedCountries.add(row.country);
      }}
      updateLineChart(false);
    }});
    updateMap(true);
    updateLineChart(true);
  </script>
</body>
</html>
"""


def write_map(input_path: Path, exercise_2_input_path: Path, output_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = read_and_validate(input_path)
    exercise_2_df = read_exercise_2_panel(exercise_2_input_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_html(df, exercise_2_df, input_path, exercise_2_input_path), encoding="utf-8")
    return df, exercise_2_df


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a standalone HTML map of trade concentration Ginis.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Exercise 1 concentration panel CSV.")
    parser.add_argument("--exercise-2-input", type=Path, default=DEFAULT_EXERCISE_2_INPUT, help="Exercise 2 export concentration panel CSV.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Standalone HTML output path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    df, exercise_2_df = write_map(args.input, args.exercise_2_input, args.output)
    print(f"Wrote {args.output}")
    print(f"Exercise 1 rows: {len(df)}")
    print(f"Exercise 2 rows: {len(exercise_2_df)}")
    print(f"Countries: {df['iso3'].nunique()}")
    print(f"Years: {int(df['year'].min())}-{int(df['year'].max())} ({df['year'].nunique()})")
    print(f"Flows: {', '.join(sorted(df['flow'].unique()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
