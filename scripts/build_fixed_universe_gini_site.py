#!/usr/bin/env python3
"""Build a standalone GitHub Pages site for fixed-universe Product Gini results."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd
from plotly.offline import get_plotlyjs

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import trade_concentration_pipeline as tcp  # noqa: E402


COUNTRY_SAMPLE = "rd2_countries"
BENCHMARK_SAMPLE = "world_broad"
PRODUCT_ID_MODE = "harmonized_hs6_family"
DEFAULT_OUTPUT = Path("/tmp/fixed-universe-gini-site")
RESULT_DIR = ROOT / "results/samples/rd2_countries/fixed_universe_product_gini_tables"
PROCESSED_PANEL = ROOT / "data/processed/samples/rd2_countries/fixed_universe_product_gini_panel.parquet"
DOWNLOAD_FILENAMES = [
    "fixed_universe_product_gini_all_years.csv",
    "fixed_universe_product_gini_latest_rankings.csv",
    "fixed_universe_product_gini_yearly_summary.csv",
    "fixed_universe_product_gini_diagnostics.csv",
    "fixed_universe_product_gini_manifest.json",
    "fixed_universe_product_gini_rich_proxy_summary.csv",
    "fixed_universe_product_gini_world_product_support_by_year.csv",
    "fixed_universe_product_gini.md",
    "fixed_universe_product_gini_adversarial_review.md",
]
DOWNLOAD_SOURCES = {name: RESULT_DIR / name for name in DOWNLOAD_FILENAMES}
DOWNLOAD_SOURCES["fixed_universe_product_gini_adversarial_review.md"] = (
    ROOT / "results/samples/rd2_countries/fixed_universe_product_gini_adversarial_review.md"
)


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and math.isnan(value):
        return None
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def read_csv(name: str) -> pd.DataFrame:
    path = RESULT_DIR / name
    if not path.exists():
        raise RuntimeError(f"Missing required site input: {path}")
    return pd.read_csv(path)


def clean_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return json.loads(frame.to_json(orient="records"))


def validate_site_inputs(panel: pd.DataFrame, manifest: dict[str, Any]) -> None:
    required = {
        "country",
        "iso3",
        "reporter_code",
        "year",
        "flow",
        "fixed_universe_product_gini",
        "active_product_gini",
        "gini_extensive_gap",
        "active_product_count",
        "universe_product_count",
        "zero_product_count",
        "active_product_share",
        "total_trade_value",
        "balanced_panel_flag",
        "product_id_mode",
    }
    missing = required - set(panel.columns)
    if missing:
        raise RuntimeError(f"Fixed-universe panel is missing columns: {sorted(missing)}")
    if manifest.get("country_sample") != COUNTRY_SAMPLE:
        raise RuntimeError("Fixed-universe site requires rd2_countries results.")
    if manifest.get("benchmark_sample") != BENCHMARK_SAMPLE:
        raise RuntimeError("Fixed-universe site requires world_broad only as the universe source.")
    if manifest.get("product_id_mode") != PRODUCT_ID_MODE:
        raise RuntimeError("Fixed-universe site requires harmonized_hs6_family results.")
    if set(panel["flow"].dropna().unique()) != {"Exports", "Imports"}:
        raise RuntimeError("Fixed-universe site requires both Exports and Imports.")
    if not panel["product_id_mode"].eq(PRODUCT_ID_MODE).all():
        raise RuntimeError("Panel contains a non-harmonized product mode.")
    if panel[["reporter_code", "year", "flow"]].duplicated().any():
        raise RuntimeError("Panel contains duplicate reporter-year-flow keys.")
    if panel["fixed_universe_product_gini"].isna().any():
        raise RuntimeError("Panel contains missing fixed-universe Gini values.")
    for flow, group in panel.groupby("flow"):
        if group["universe_product_count"].nunique() != 1:
            raise RuntimeError(f"{flow} does not have a fixed product-universe count.")
    text_cols = [col for col in panel.columns if "product" in col.lower() and panel[col].dtype == object]
    for col in text_cols:
        if panel[col].astype(str).str.contains("999999", na=False).any():
            raise RuntimeError(f"Column {col} contains excluded 999999 product text.")


def load_site_data() -> dict[str, Any]:
    all_years = read_csv("fixed_universe_product_gini_all_years.csv")
    latest = read_csv("fixed_universe_product_gini_latest_rankings.csv")
    yearly = read_csv("fixed_universe_product_gini_yearly_summary.csv")
    diagnostics = read_csv("fixed_universe_product_gini_diagnostics.csv")
    rich_proxy = read_csv("fixed_universe_product_gini_rich_proxy_summary.csv")
    world_support = read_csv("fixed_universe_product_gini_world_product_support_by_year.csv")
    manifest_path = RESULT_DIR / "fixed_universe_product_gini_manifest.json"
    if not manifest_path.exists():
        raise RuntimeError(f"Missing required site input: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_site_inputs(all_years, manifest)

    keep_cols = [
        "country",
        "iso3",
        "reporter_code",
        "year",
        "flow",
        "fixed_universe_product_gini",
        "active_product_gini",
        "gini_extensive_gap",
        "active_product_count",
        "universe_product_count",
        "zero_product_count",
        "active_product_share",
        "total_trade_value",
        "balanced_panel_flag",
        "region",
        "income_group",
    ]
    panel = all_years[keep_cols].copy()
    panel["balanced_panel_flag"] = panel["balanced_panel_flag"].astype(bool)
    years = {
        flow: sorted(int(year) for year in group["year"].drop_duplicates())
        for flow, group in panel.groupby("flow", sort=True)
    }
    latest_year = {flow: max(flow_years) for flow, flow_years in years.items()}
    universe_counts = {
        flow: int(group["universe_product_count"].iloc[0])
        for flow, group in panel.groupby("flow", sort=True)
    }
    balance = manifest.get("balanced_window", {}).get("flows", {})
    return {
        "generated_at_utc": now_utc(),
        "source_manifest_generated_at_utc": manifest.get("generated_at_utc"),
        "country_sample": COUNTRY_SAMPLE,
        "benchmark_sample": BENCHMARK_SAMPLE,
        "benchmark_role": "global product-universe source only",
        "product_id_mode": PRODUCT_ID_MODE,
        "harmonization": manifest.get("harmonization", {}),
        "years": years,
        "latest_year": latest_year,
        "universe_counts": universe_counts,
        "balanced_window": balance,
        "panel": clean_records(panel),
        "latest_rankings": clean_records(latest),
        "yearly_summary": clean_records(yearly),
        "diagnostics": clean_records(diagnostics),
        "rich_proxy_summary": clean_records(rich_proxy),
        "world_product_support_by_year": clean_records(world_support),
        "downloads": [{"filename": name, "path": f"downloads/{name}"} for name in DOWNLOAD_FILENAMES],
    }


def prepare_output(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for child in output.iterdir():
        if child.name == ".git":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    (output / "assets").mkdir(parents=True, exist_ok=True)
    (output / "downloads").mkdir(parents=True, exist_ok=True)


def copy_downloads(output: Path) -> dict[str, dict[str, Any]]:
    copied: dict[str, dict[str, Any]] = {}
    for name in DOWNLOAD_FILENAMES:
        source = DOWNLOAD_SOURCES[name]
        if not source.exists():
            raise RuntimeError(f"Missing download source: {source}")
        dest = output / "downloads" / name
        shutil.copy2(source, dest)
        copied[name] = {"path": f"downloads/{name}", "bytes": dest.stat().st_size, "sha256": sha256(dest)}
    return copied


def nav(active: str) -> str:
    links = [
        ("index", "Dashboard", "index.html"),
        ("methods", "Methods", "methods.html"),
        ("downloads", "Downloads", "downloads.html"),
    ]
    return "\n".join(
        f'<a class="nav-link{" active" if key == active else ""}" href="{href}">{label}</a>' for key, label, href in links
    )


def page_shell(title: str, active: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <link rel="stylesheet" href="assets/styles.css">
</head>
<body>
  <header class="topbar">
    <a class="brand" href="index.html">
      <span class="brand-mark" aria-hidden="true"></span>
      <span>Fixed-Universe Product Gini</span>
    </a>
    <nav class="site-nav" aria-label="Primary navigation">
      {nav(active)}
    </nav>
  </header>
  {body}
</body>
</html>
"""


def render_index() -> str:
    body = """<main>
  <section class="dashboard">
    <div class="dashboard-heading">
      <div>
        <p class="eyebrow">rd2 countries · LT/HGL HS1992 product families · 2000-2024</p>
        <h1>Fixed-universe product <br class="mobile-break">concentration</h1>
      </div>
      <div class="controls" aria-label="Dashboard controls">
        <div class="segmented" role="tablist" aria-label="Flow">
          <button type="button" class="active" data-flow="Exports">Exports</button>
          <button type="button" data-flow="Imports">Imports</button>
        </div>
        <label class="year-control">
          <span>Year <strong id="yearLabel"></strong></span>
          <input id="yearRange" type="range" min="2000" max="2024" value="2024" step="1">
        </label>
      </div>
    </div>

    <section class="metric-strip" aria-label="Selected year summary">
      <article class="metric-tile">
        <span>Median fixed Gini</span>
        <strong id="metricMedianFixed">--</strong>
      </article>
      <article class="metric-tile">
        <span>Median active Gini</span>
        <strong id="metricMedianActive">--</strong>
      </article>
      <article class="metric-tile">
        <span>Median active products</span>
        <strong id="metricActiveProducts">--</strong>
      </article>
      <article class="metric-tile">
        <span>Product universe</span>
        <strong id="metricUniverse">--</strong>
      </article>
    </section>

    <section class="viz-grid">
      <div class="panel panel-large">
        <div class="panel-heading">
          <h2>Country map</h2>
          <span id="mapSubtitle"></span>
        </div>
        <div id="mapChart" class="chart map-chart"></div>
      </div>
      <div class="panel">
        <div class="panel-heading">
          <h2>Active vs fixed</h2>
          <span>Same harmonized products</span>
        </div>
        <div id="scatterChart" class="chart"></div>
      </div>
    </section>

    <section class="content-grid">
      <div class="panel">
        <div class="panel-heading">
          <h2>Highest fixed-universe Gini</h2>
          <span id="rankingSubtitle"></span>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr><th>Rank</th><th>Country</th><th>Fixed</th><th>Active share</th></tr>
            </thead>
            <tbody id="rankingBody"></tbody>
          </table>
        </div>
      </div>
      <div class="panel">
        <div class="panel-heading">
          <h2>Japan and Korea</h2>
          <span>Taiwan is absent from rd2</span>
        </div>
        <div id="japanKoreaBlock" class="comparison-block"></div>
      </div>
      <div class="panel panel-wide">
        <div class="panel-heading">
          <h2>Balanced trend</h2>
          <span id="trendSubtitle"></span>
        </div>
        <div id="trendChart" class="chart trend-chart"></div>
      </div>
    </section>
  </section>
</main>
<script src="assets/plotly.min.js"></script>
<script src="assets/site-data.js"></script>
<script src="assets/app.js"></script>
"""
    return page_shell("Fixed-Universe Product Gini", "index", body)


def render_methods() -> str:
    body = f"""<main>
  <section class="page-band">
    <p class="eyebrow">Methods</p>
    <h1>What the fixed-universe Gini measures</h1>
    <div class="method-grid">
      <section class="method-section">
        <h2>Definition</h2>
        <p>The unit is a reporter-year-flow product basket for the rd2 country sample. Products are LT/HGL-weighted HS1992 product families built from the existing harmonized HS6 artifacts.</p>
        <p>For each flow, the product universe is fixed as the 2000-2024 union of positive <code>world_broad</code> product-family trade. <code>world_broad</code> defines the global product support only; it is not the reporter sample.</p>
      </section>
      <section class="method-section">
        <h2>Formula</h2>
        <p><code>x_cfpt</code> is reporter <code>c</code>'s trade value in flow <code>f</code>, year <code>t</code>, and product family <code>p</code>. If the reporter has no value for an eligible product, that value is zero.</p>
        <pre><code>G_fixed_cft = (2 * sum_i i * x_(i)) / (K_f * sum_i x_i) - (K_f + 1) / K_f</code></pre>
        <p>Higher values mean trade is concentrated in fewer eligible products or in a small number of high-value products.</p>
      </section>
      <section class="method-section">
        <h2>Exclusions and harmonization</h2>
        <p>HS6 <code>999999</code>, commodities not specified, is excluded before product aggregation. The harmonization source is LT/HGL, Harvard Dataverse DOI <code>{tcp.LT_HGL_DATASET_DOI}</code>, version <code>{tcp.LT_HGL_DATASET_VERSION}</code>, targeting {tcp.LT_HGL_TARGET_LABEL}/{tcp.LT_HGL_TARGET_REVISION}.</p>
      </section>
      <section class="method-section">
        <h2>How this differs from UNCTAD Theil</h2>
        <p>This site is product-only. UNCTAD's merchandise Theil index also incorporates market or destination concentration. That is why this fixed-universe Product Gini should be read as an extensive-margin product-basket measure, not as a direct replica of UNCTAD's product-plus-market Theil.</p>
      </section>
    </div>
  </section>
</main>
"""
    return page_shell("Methods · Fixed-Universe Product Gini", "methods", body)


def render_downloads(download_manifest: dict[str, dict[str, Any]]) -> str:
    rows = "\n".join(
        f"""<tr>
          <td><a href="downloads/{escape(name)}">{escape(name)}</a></td>
          <td>{info['bytes']:,}</td>
          <td><code>{escape(info['sha256'][:16])}</code></td>
        </tr>"""
        for name, info in download_manifest.items()
    )
    body = f"""<main>
  <section class="page-band">
    <p class="eyebrow">Downloads</p>
    <h1>Result artifacts</h1>
    <p class="lede">The downloadable files are generated from the rd2 harmonized product artifacts and are copied directly from the research repository output directory.</p>
    <div class="table-wrap downloads-table">
      <table>
        <thead><tr><th>File</th><th>Bytes</th><th>SHA-256 prefix</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
  </section>
</main>
"""
    return page_shell("Downloads · Fixed-Universe Product Gini", "downloads", body)


CSS = r"""
:root {
  --ink: #17202a;
  --muted: #667085;
  --line: #d9e0e7;
  --paper: #f7f8fa;
  --panel: #ffffff;
  --teal: #0b7c78;
  --blue: #315f9c;
  --gold: #ad7c18;
  --red: #b44335;
  --shadow: 0 14px 32px rgba(25, 38, 52, 0.10);
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  overflow-x: hidden;
}

.topbar {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 64px;
  padding: 0 28px;
  border-bottom: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.96);
}

.brand {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  color: var(--ink);
  text-decoration: none;
  font-weight: 700;
}

.brand-mark {
  width: 18px;
  height: 18px;
  border-radius: 4px;
  background: linear-gradient(135deg, var(--teal), var(--gold));
}

.mobile-break {
  display: none;
}

.site-nav {
  display: flex;
  gap: 6px;
}

.nav-link {
  display: inline-flex;
  align-items: center;
  min-height: 36px;
  padding: 0 12px;
  border-radius: 6px;
  color: var(--muted);
  text-decoration: none;
  font-size: 14px;
  font-weight: 650;
}

.nav-link.active,
.nav-link:hover {
  color: var(--ink);
  background: #edf2f5;
}

.dashboard,
.page-band {
  width: calc(100% - 40px);
  max-width: 1480px;
  margin: 0 auto;
  padding: 28px 0 44px;
}

.dashboard-heading {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 20px;
  align-items: end;
  margin-bottom: 18px;
}

.eyebrow {
  margin: 0 0 8px;
  color: var(--teal);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0;
  text-transform: uppercase;
}

h1 {
  margin: 0;
  font-size: 34px;
  line-height: 1.12;
  letter-spacing: 0;
  overflow-wrap: break-word;
}

h2 {
  margin: 0;
  font-size: 17px;
  line-height: 1.2;
  letter-spacing: 0;
}

.controls {
  display: flex;
  align-items: center;
  gap: 18px;
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
}

.segmented {
  display: inline-grid;
  grid-template-columns: 1fr 1fr;
  width: 188px;
  padding: 3px;
  border: 1px solid var(--line);
  border-radius: 7px;
  background: #f1f4f6;
}

.segmented button {
  min-height: 34px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--muted);
  font: inherit;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
}

.segmented button.active {
  color: #ffffff;
  background: var(--teal);
}

.year-control {
  display: grid;
  gap: 6px;
  min-width: 220px;
  color: var(--muted);
  font-size: 13px;
  font-weight: 650;
}

.year-control input {
  width: 100%;
  accent-color: var(--blue);
}

.metric-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin: 16px 0;
}

.metric-tile,
.panel,
.method-section {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
  box-shadow: var(--shadow);
}

.metric-tile {
  min-height: 92px;
  padding: 16px;
}

.metric-tile span {
  display: block;
  margin-bottom: 10px;
  color: var(--muted);
  font-size: 13px;
  font-weight: 700;
}

.metric-tile strong {
  font-size: 30px;
  letter-spacing: 0;
}

.viz-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(420px, 0.65fr);
  gap: 16px;
}

.content-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(360px, 0.7fr);
  gap: 16px;
  margin-top: 16px;
}

.panel-wide {
  grid-column: 1 / -1;
}

.panel {
  min-width: 0;
  padding: 16px;
}

.panel-heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 12px;
}

.panel-heading span {
  color: var(--muted);
  font-size: 13px;
  font-weight: 650;
}

.chart {
  width: 100%;
  max-width: 100%;
  min-height: 420px;
}

.map-chart {
  min-height: 520px;
}

.trend-chart {
  min-height: 320px;
}

.table-wrap {
  width: 100%;
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

th,
td {
  padding: 10px 8px;
  border-bottom: 1px solid var(--line);
  text-align: left;
  vertical-align: middle;
}

th {
  color: var(--muted);
  font-size: 12px;
  font-weight: 800;
  text-transform: uppercase;
}

.comparison-block {
  display: grid;
  gap: 14px;
}

.comparison-stat {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px solid var(--line);
}

.comparison-stat span {
  color: var(--muted);
  font-weight: 650;
}

.comparison-note,
.lede {
  color: var(--muted);
  line-height: 1.55;
}

.method-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-top: 22px;
}

.method-section {
  padding: 20px;
}

.method-section p {
  color: var(--muted);
  line-height: 1.6;
}

pre {
  overflow-x: auto;
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #f1f4f6;
}

code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
}

a {
  color: var(--blue);
}

@media (max-width: 980px) {
  .dashboard-heading,
  .viz-grid,
  .content-grid,
  .method-grid {
    grid-template-columns: 1fr;
  }

  .controls {
    align-items: stretch;
    flex-direction: column;
    width: 100%;
  }

  .metric-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .topbar {
    align-items: flex-start;
    flex-direction: column;
    gap: 10px;
    padding: 12px 20px;
  }

  .site-nav {
    flex-wrap: wrap;
  }
}

@media (max-width: 640px) {
  .dashboard,
  .page-band {
    width: calc(100% - 24px);
    max-width: 1480px;
  }

  h1 {
    font-size: 24px;
    line-height: 1.18;
  }

  .segmented,
  .year-control {
    min-width: 0;
    width: 100%;
  }

  .mobile-break {
    display: block;
  }

  .panel-heading {
    align-items: flex-start;
    flex-direction: column;
  }

  .metric-strip {
    grid-template-columns: 1fr;
  }

  .chart,
  .map-chart {
    min-height: 360px;
  }

  th,
  td {
    padding: 9px 6px;
    font-size: 13px;
  }
}
"""


APP_JS = r"""
(function () {
  const DATA = window.FIXED_UNIVERSE_GINI_DATA;
  const state = { flow: "Exports", year: DATA.latest_year.Exports };
  const nf0 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
  const nf1 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });
  const nf3 = new Intl.NumberFormat("en-US", { minimumFractionDigits: 3, maximumFractionDigits: 3 });
  const pct = new Intl.NumberFormat("en-US", { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 });

  function rowsForSelection() {
    return DATA.panel.filter((row) => row.flow === state.flow && row.year === state.year);
  }

  function balancedSummary() {
    return DATA.yearly_summary.find(
      (row) => row.sample_window === "balanced_2000_2024" && row.flow === state.flow && row.year === state.year
    ) || DATA.yearly_summary.find(
      (row) => row.sample_window === "all_available" && row.flow === state.flow && row.year === state.year
    );
  }

  function richProxySummary() {
    return DATA.rich_proxy_summary.find((row) => row.flow === state.flow && row.year === state.year);
  }

  function setText(id, value) {
    const node = document.getElementById(id);
    if (node) node.textContent = value;
  }

  function updateControls() {
    const years = DATA.years[state.flow];
    const range = document.getElementById("yearRange");
    range.min = Math.min(...years);
    range.max = Math.max(...years);
    range.value = state.year;
    setText("yearLabel", state.year);
    document.querySelectorAll("[data-flow]").forEach((button) => {
      button.classList.toggle("active", button.dataset.flow === state.flow);
    });
  }

  function updateMetrics() {
    const rows = rowsForSelection();
    const summary = balancedSummary();
    const universe = DATA.universe_counts[state.flow];
    setText("metricMedianFixed", summary ? nf3.format(summary.median_fixed_universe_product_gini) : "--");
    setText("metricMedianActive", summary ? nf3.format(summary.median_active_product_gini) : "--");
    setText("metricActiveProducts", summary ? nf0.format(summary.median_active_product_count) : "--");
    setText("metricUniverse", nf0.format(universe));
    setText("mapSubtitle", `${state.flow}, ${state.year}; ${rows.length} countries`);
    setText("rankingSubtitle", `${state.flow}, ${state.year}`);
    setText("trendSubtitle", `${state.flow}; balanced 2000-2024 panel`);
  }

  function renderMap() {
    const rows = rowsForSelection();
    const trace = {
      type: "choropleth",
      locationmode: "ISO-3",
      locations: rows.map((row) => row.iso3),
      z: rows.map((row) => row.fixed_universe_product_gini),
      text: rows.map((row) => `${row.country}<br>Fixed Gini: ${nf3.format(row.fixed_universe_product_gini)}<br>Active share: ${pct.format(row.active_product_share)}`),
      hoverinfo: "text",
      colorscale: [
        [0, "#e8f3f1"],
        [0.35, "#9bcac3"],
        [0.7, "#2f7f7a"],
        [1, "#7d3f35"]
      ],
      zmin: 0.75,
      zmax: 1.0,
      marker: { line: { color: "#ffffff", width: 0.4 } },
      colorbar: { title: "Fixed Gini", thickness: 12 }
    };
    const layout = {
      margin: { l: 0, r: 0, t: 0, b: 0 },
      paper_bgcolor: "#ffffff",
      plot_bgcolor: "#ffffff",
      geo: {
        projection: { type: "natural earth" },
        showframe: false,
        showcoastlines: false,
        showcountries: true,
        countrycolor: "#c8d1dc",
        bgcolor: "#ffffff",
        landcolor: "#eef1f4"
      }
    };
    Plotly.react("mapChart", [trace], layout, { responsive: true, displayModeBar: false });
  }

  function renderScatter() {
    const rows = rowsForSelection();
    const trace = {
      type: "scatter",
      mode: "markers",
      x: rows.map((row) => row.active_product_gini),
      y: rows.map((row) => row.fixed_universe_product_gini),
      text: rows.map((row) => `${row.country}<br>Active: ${nf3.format(row.active_product_gini)}<br>Fixed: ${nf3.format(row.fixed_universe_product_gini)}<br>Active products: ${nf0.format(row.active_product_count)}`),
      hoverinfo: "text",
      marker: {
        size: rows.map((row) => 8 + 18 * row.active_product_share),
        color: rows.map((row) => row.active_product_share),
        colorscale: [
          [0, "#b44335"],
          [0.5, "#ad7c18"],
          [1, "#0b7c78"]
        ],
        line: { color: "#ffffff", width: 0.8 },
        colorbar: { title: "Active share", thickness: 12 }
      }
    };
    const layout = {
      margin: { l: 52, r: 12, t: 6, b: 46 },
      paper_bgcolor: "#ffffff",
      plot_bgcolor: "#ffffff",
      xaxis: { title: "Active Product Gini", range: [0.75, 1.0], gridcolor: "#e6ebf0" },
      yaxis: { title: "Fixed-Universe Product Gini", range: [0.75, 1.0], gridcolor: "#e6ebf0" },
      shapes: [{
        type: "line",
        x0: 0.75, x1: 1.0, y0: 0.75, y1: 1.0,
        line: { color: "#9aa7b2", width: 1, dash: "dot" }
      }]
    };
    Plotly.react("scatterChart", [trace], layout, { responsive: true, displayModeBar: false });
  }

  function renderRanking() {
    const rows = rowsForSelection()
      .slice()
      .sort((a, b) => b.fixed_universe_product_gini - a.fixed_universe_product_gini)
      .slice(0, 12);
    const body = document.getElementById("rankingBody");
    body.innerHTML = rows.map((row, index) => `
      <tr>
        <td>${index + 1}</td>
        <td>${row.country} <span class="comparison-note">(${row.iso3})</span></td>
        <td>${nf3.format(row.fixed_universe_product_gini)}</td>
        <td>${pct.format(row.active_product_share)}</td>
      </tr>
    `).join("");
  }

  function renderJapanKorea() {
    const rows = rowsForSelection().filter((row) => row.iso3 === "JPN" || row.iso3 === "KOR")
      .sort((a, b) => a.country.localeCompare(b.country));
    const rich = richProxySummary();
    const countryRows = rows.map((row) => `
      <div class="comparison-stat">
        <span>${row.country} fixed Gini</span>
        <strong>${nf3.format(row.fixed_universe_product_gini)}</strong>
      </div>
      <div class="comparison-stat">
        <span>${row.country} active product share</span>
        <strong>${pct.format(row.active_product_share)}</strong>
      </div>
    `).join("");
    const richRows = rich ? `
      <div class="comparison-stat">
        <span>Japan/Korea mean fixed Gini</span>
        <strong>${nf3.format(rich.japan_korea_mean_fixed_universe_product_gini)}</strong>
      </div>
      <div class="comparison-stat">
        <span>rd2 high-income proxy mean</span>
        <strong>${nf3.format(rich.rich_proxy_mean_fixed_universe_product_gini)}</strong>
      </div>
      <div class="comparison-stat">
        <span>Japan/Korea gap vs proxy</span>
        <strong>${pct.format(rich.japan_korea_vs_rich_proxy_pct_gap)}</strong>
      </div>
    ` : "";
    document.getElementById("japanKoreaBlock").innerHTML = `
      ${countryRows}
      ${richRows}
      <p class="comparison-note">The comparator is rd2 high-income countries excluding Japan and Korea. Taiwan is not in rd2, so this is not the Economist/UNCTAD Japan-Korea-Taiwan region.</p>
    `;
  }

  function renderTrend() {
    const rows = DATA.yearly_summary
      .filter((row) => row.sample_window === "balanced_2000_2024" && row.flow === state.flow)
      .sort((a, b) => a.year - b.year);
    const traceFixed = {
      type: "scatter",
      mode: "lines+markers",
      name: "Fixed universe",
      x: rows.map((row) => row.year),
      y: rows.map((row) => row.median_fixed_universe_product_gini),
      line: { color: "#0b7c78", width: 3 },
      marker: { size: 5 }
    };
    const traceActive = {
      type: "scatter",
      mode: "lines+markers",
      name: "Active only",
      x: rows.map((row) => row.year),
      y: rows.map((row) => row.median_active_product_gini),
      line: { color: "#315f9c", width: 2 },
      marker: { size: 5 }
    };
    const layout = {
      margin: { l: 52, r: 12, t: 8, b: 42 },
      paper_bgcolor: "#ffffff",
      plot_bgcolor: "#ffffff",
      xaxis: { title: "Year", dtick: 4, gridcolor: "#e6ebf0" },
      yaxis: { title: "Median Gini", range: [0.75, 1.0], gridcolor: "#e6ebf0" },
      legend: { orientation: "h", x: 0, y: 1.12 }
    };
    Plotly.react("trendChart", [traceFixed, traceActive], layout, { responsive: true, displayModeBar: false });
  }

  function render() {
    updateControls();
    updateMetrics();
    renderMap();
    renderScatter();
    renderRanking();
    renderJapanKorea();
    renderTrend();
  }

  document.querySelectorAll("[data-flow]").forEach((button) => {
    button.addEventListener("click", () => {
      state.flow = button.dataset.flow;
      state.year = DATA.latest_year[state.flow];
      render();
    });
  });

  document.getElementById("yearRange").addEventListener("input", (event) => {
    state.year = Number(event.target.value);
    render();
  });

  render();
})();
"""


def write_static_assets(output: Path, site_data: dict[str, Any]) -> None:
    assets = output / "assets"
    (assets / "styles.css").write_text(CSS, encoding="utf-8")
    (assets / "app.js").write_text(APP_JS, encoding="utf-8")
    site_json = json.dumps(site_data, indent=2, default=json_default)
    (assets / "site-data.json").write_text(site_json + "\n", encoding="utf-8")
    (assets / "site-data.js").write_text(f"window.FIXED_UNIVERSE_GINI_DATA = {site_json};\n", encoding="utf-8")
    (assets / "plotly.min.js").write_text(get_plotlyjs(), encoding="utf-8")


def write_readme(output: Path, site_manifest: dict[str, Any]) -> None:
    lines = [
        "# Fixed-Universe Product Gini",
        "",
        "Static GitHub Pages site generated from the `rd2_countries` fixed-universe harmonized-HS6 Product Gini artifacts.",
        "",
        "Source research repository: `tsawhneybuilds/tradeconcentration`.",
        "",
        "Key rules:",
        "",
        "- Reporter sample: `rd2_countries`.",
        "- Product universe source: `world_broad`, used only as global product support.",
        "- Product ID mode: `harmonized_hs6_family`.",
        "- HS6 `999999` is excluded before harmonization and aggregation.",
        "",
        f"Generated: {site_manifest['generated_at_utc']}",
    ]
    (output / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_site(output: Path) -> dict[str, Any]:
    site_data = load_site_data()
    prepare_output(output)
    downloads = copy_downloads(output)
    site_data["downloads"] = [
        {"filename": name, "path": info["path"], "bytes": info["bytes"], "sha256": info["sha256"]}
        for name, info in downloads.items()
    ]
    write_static_assets(output, site_data)
    (output / "index.html").write_text(render_index(), encoding="utf-8")
    (output / "methods.html").write_text(render_methods(), encoding="utf-8")
    (output / "downloads.html").write_text(render_downloads(downloads), encoding="utf-8")
    site_manifest = {
        "status": "complete",
        "generated_at_utc": site_data["generated_at_utc"],
        "country_sample": COUNTRY_SAMPLE,
        "benchmark_sample": BENCHMARK_SAMPLE,
        "benchmark_role": "global product-universe source only",
        "product_id_mode": PRODUCT_ID_MODE,
        "source_result_dir": rel(RESULT_DIR),
        "source_processed_panel": rel(PROCESSED_PANEL),
        "pages": ["index.html", "methods.html", "downloads.html"],
        "assets": {
            "site_data_json": {"path": "assets/site-data.json", "bytes": (output / "assets/site-data.json").stat().st_size},
            "site_data_js": {"path": "assets/site-data.js", "bytes": (output / "assets/site-data.js").stat().st_size},
            "app_js": {"path": "assets/app.js", "bytes": (output / "assets/app.js").stat().st_size},
            "styles_css": {"path": "assets/styles.css", "bytes": (output / "assets/styles.css").stat().st_size},
        },
        "downloads": downloads,
    }
    (output / "assets/site-manifest.json").write_text(
        json.dumps(site_manifest, indent=2, default=json_default) + "\n", encoding="utf-8"
    )
    write_readme(output, site_manifest)
    validate_site_output(output)
    return site_manifest


def validate_site_output(output: Path) -> None:
    required = [
        "index.html",
        "methods.html",
        "downloads.html",
        "README.md",
        "assets/styles.css",
        "assets/app.js",
        "assets/site-data.json",
        "assets/site-data.js",
        "assets/site-manifest.json",
        "assets/plotly.min.js",
    ]
    for rel_path in required:
        path = output / rel_path
        if not path.exists():
            raise RuntimeError(f"Missing generated site file: {path}")
    for name in DOWNLOAD_FILENAMES:
        if not (output / "downloads" / name).exists():
            raise RuntimeError(f"Missing generated download: {name}")
    data = json.loads((output / "assets/site-data.json").read_text(encoding="utf-8"))
    if data.get("country_sample") != COUNTRY_SAMPLE:
        raise RuntimeError("site-data.json does not report rd2_countries.")
    if data.get("product_id_mode") != PRODUCT_ID_MODE:
        raise RuntimeError("site-data.json does not report harmonized_hs6_family.")
    if not data.get("panel"):
        raise RuntimeError("site-data.json has no panel rows.")
    checked_text = "\n".join(
        (output / rel_path).read_text(encoding="utf-8") for rel_path in ["index.html", "methods.html", "downloads.html", "assets/site-data.js"]
    )
    if "NaN" in checked_text:
        raise RuntimeError("Generated site text contains NaN.")
    if "undefined" in checked_text:
        raise RuntimeError("Generated site text contains undefined.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = write_site(args.output)
    print(f"Fixed-universe Gini site written to {args.output}")
    print(f"Generated {len(manifest['pages'])} pages and {len(manifest['downloads'])} downloads.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
