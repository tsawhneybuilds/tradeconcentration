#!/usr/bin/env python3
"""Build the Cadot-156 Gini/Theil/HHI static site bundle."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import shutil
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESULT_DIR = ROOT / "results" / "samples" / "cadot_broad_156" / "three_metric_tables"
DEFAULT_OUTPUT = Path("/tmp/trade-concentration-sites")
DEFAULT_PUBLISH = Path("/Users/tanushsawhney/Desktop/trade-gini-map")
MAX_RAW_DOWNLOAD_BYTES = 95 * 1024 * 1024
METRICS = {
    "gini": {
        "label": "Gini",
        "title": "Gini Trade Concentration",
        "value_col": "gini",
        "format": "{:.3f}",
        "summary": "Active-positive Gini over observed positive trade values.",
    },
    "theil": {
        "label": "Theil",
        "title": "Theil Trade Concentration",
        "value_col": "theil",
        "format": "{:.3f}",
        "summary": "Fixed-universe product Theil: sum_p s_cpft * log(s_cpft * K_f).",
    },
    "hhi": {
        "label": "HHI",
        "title": "HHI Trade Concentration",
        "value_col": "hhi",
        "format": "{:.3f}",
        "summary": "Raw Herfindahl-Hirschman index, sum_i s_i^2, on [0,1].",
    },
}
EXERCISES = [
    {
        "num": "01",
        "short": "1",
        "title": "Exercise 1: Headline Product Concentration",
        "summary": "Common product headline panel for Gini, fixed-universe Theil, and raw HHI.",
        "source": "metric_headline_product_panel.csv",
    },
    {
        "num": "02",
        "short": "2",
        "title": "Exercise 2: Concentration Buckets And Growth",
        "summary": "Trade and active-product growth by metric-specific concentration buckets.",
        "source": "exercise_02_bucket_growth_summary.csv",
    },
    {
        "num": "03",
        "short": "3",
        "title": "Exercise 3: Import BEC-Bin Concentration",
        "summary": "Import concentration within BEC-style goods bins for all three metrics.",
        "source": "exercise_03_import_bin_metrics.csv",
    },
    {
        "num": "04",
        "short": "4",
        "title": "Exercise 4: Dominant Suppliers",
        "summary": "Dominant supplier and source-HHI summaries for importer-product sourcing.",
        "source": "exercise_04_dominant_supplier_summary.csv",
    },
    {
        "num": "06",
        "short": "6",
        "title": "Exercise 6: HS2 Exclusion Sensitivity",
        "summary": "Metric sensitivity after excluding each HS2 sector.",
        "source": "exercise_06_exclusion_metrics.csv",
    },
    {
        "num": "10",
        "short": "10",
        "title": "Exercise 10: Random Benchmarks",
        "summary": "Metric-specific random benchmark simulations for Gini, Theil, and HHI.",
        "source": "exercise_10_random_benchmarks.csv",
    },
    {
        "num": "11",
        "short": "11",
        "title": "Exercise 11: Leave-One-Out Product Contributions",
        "summary": "Top absolute product leave-one-out contributions by metric.",
        "source": "exercise_11_top_product_loo_contributions.csv",
    },
    {
        "num": "12",
        "short": "12",
        "title": "Exercise 12: Growth Decomposition",
        "summary": "Growth decomposition by base-year concentration buckets.",
        "source": "exercise_12_growth_decomposition_summary.csv",
    },
]
EXERCISE_BY_SHORT = {item["short"]: item for item in EXERCISES}
PAGES = [
    "index.html",
    "gini/index.html",
    "theil/index.html",
    "theil/appendix.html",
    "hhi/index.html",
    "downloads/index.html",
    "exercises/index.html",
    *[f"exercises/exercise-{item['num']}.html" for item in EXERCISES],
]
DOWNLOADS = [
    "cadot_three_metric_manifest.json",
    "cadot_three_metric_methods.md",
    "validation_checks.csv",
    "concentration_metric_all_years.csv",
    "metric_headline_product_panel.csv",
    "metric_latest_rankings.csv",
    "metric_yearly_summary.csv",
    "sample_attrition_by_reporter_flow.csv",
    "product_universe.csv",
    "exercise_02_bucket_growth_summary.csv",
    "exercise_03_import_bin_metrics.csv",
    "exercise_04_dominant_supplier_summary.csv",
    "exercise_06_exclusion_metrics.csv",
    "exercise_10_random_benchmarks.csv",
    "exercise_11_top_product_loo_contributions.csv",
    "exercise_12_growth_decomposition_summary.csv",
    "adversarial_review.md",
]


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def gzip_copy(source: Path, dest: Path) -> None:
    with source.open("rb") as src, dest.open("wb") as raw_out:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw_out, mtime=0) as gz_out:
            shutil.copyfileobj(src, gz_out, length=1024 * 1024)


def read_csv(name: str) -> pd.DataFrame:
    path = RESULT_DIR / name
    if not path.exists():
        raise RuntimeError(f"Missing required site input: {path}")
    return pd.read_csv(path)


def load_inputs() -> dict[str, Any]:
    manifest_path = RESULT_DIR / "cadot_three_metric_manifest.json"
    if not manifest_path.exists():
        raise RuntimeError(f"Missing manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validation = read_csv("validation_checks.csv")
    failed = validation[~validation["passed"].astype(bool)]
    if manifest.get("country_sample") != "cadot_broad_156":
        raise RuntimeError("Three-site builder requires cadot_broad_156 results.")
    if int(manifest.get("selected_reporters", 0)) != 156:
        raise RuntimeError("Three-site builder requires exactly 156 selected reporters.")
    if not failed.empty:
        raise RuntimeError(f"Validation checks failed: {failed.to_dict(orient='records')}")
    headline = read_csv("metric_headline_product_panel.csv")
    yearly = read_csv("metric_yearly_summary.csv")
    rankings = read_csv("metric_latest_rankings.csv")
    attrition = read_csv("sample_attrition_by_reporter_flow.csv")
    ex02 = read_csv("exercise_02_bucket_growth_summary.csv")
    ex03 = read_csv("exercise_03_import_bin_metrics.csv")
    ex04 = read_csv("exercise_04_dominant_supplier_summary.csv")
    ex06 = read_csv("exercise_06_exclusion_metrics.csv")
    ex10 = read_csv("exercise_10_random_benchmarks.csv")
    ex11 = read_csv("exercise_11_top_product_loo_contributions.csv")
    ex12 = read_csv("exercise_12_growth_decomposition_summary.csv")
    return {
        "manifest": manifest,
        "validation": validation,
        "headline": headline,
        "yearly": yearly,
        "rankings": rankings,
        "attrition": attrition,
        "exercises": {
            "2": ex02,
            "3": ex03,
            "4": ex04,
            "6": ex06,
            "10": ex10,
            "11": ex11,
            "12": ex12,
        },
    }


def clean_output(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for child in output.iterdir():
        if child.name == ".git":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    for subdir in ["assets", "downloads", "gini", "theil", "hhi", "exercises"]:
        (output / subdir).mkdir(parents=True, exist_ok=True)


def fmt(value: Any, pattern: str = "{:.3f}") -> str:
    try:
        val = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if not math.isfinite(val):
        return "n/a"
    return pattern.format(val)


def table_html(frame: pd.DataFrame, columns: list[tuple[str, str]], max_rows: int = 20) -> str:
    if frame.empty:
        return '<p class="empty">No rows available.</p>'
    head = "".join(f"<th>{escape(label)}</th>" for _col, label in columns)
    rows = []
    for _, row in frame.head(max_rows).iterrows():
        cells = []
        for col, _label in columns:
            value = row.get(col, "")
            if isinstance(value, float):
                text = fmt(value, "{:.4f}") if abs(value) < 10 else fmt(value, "{:,.0f}")
            else:
                text = str(value)
            cells.append(f"<td>{escape(text)}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def link_table_html(frame: pd.DataFrame, columns: list[tuple[str, str]], max_rows: int = 20) -> str:
    if frame.empty:
        return '<p class="empty">No rows available.</p>'
    head = "".join(f"<th>{escape(label)}</th>" for _col, label in columns)
    rows = []
    for _, row in frame.head(max_rows).iterrows():
        cells = []
        for col, _label in columns:
            value = row.get(col, "")
            if isinstance(value, str) and value.startswith("<a "):
                text = value
            elif isinstance(value, float):
                text = escape(fmt(value, "{:.4f}") if abs(value) < 10 else fmt(value, "{:,.0f}"))
            else:
                text = escape(str(value))
            cells.append(f"<td>{text}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def download_href(copied: dict[str, dict[str, Any]], source_name: str) -> str:
    meta = copied[source_name]
    return f'../downloads/{escape(meta["published_name"])}'


def download_button(copied: dict[str, dict[str, Any]], source_name: str, label: str = "Download data") -> str:
    meta = copied[source_name]
    suffix = " .gz" if meta["format"] == "gzip" else ""
    return f'<a class="button" href="{download_href(copied, source_name)}">{escape(label)}{suffix}</a>'


def sample_note() -> str:
    return (
        "Cadot-style 156 reporters, 2000-2024. Tables use available observations unless a complete-case flag is named. "
        "Product-dependent outputs exclude HS6 999999 before aggregation; partner-only outputs exclude partnerCode 0."
    )


def exercise_url(short: str, prefix: str = "../") -> str:
    return f"{prefix}exercises/exercise-{EXERCISE_BY_SHORT[short]['num']}.html"


def exercise_nav(active: str = "") -> str:
    links = []
    for item in EXERCISES:
        cls = "active" if item["short"] == active else ""
        links.append(f'<a class="{cls}" href="exercise-{item["num"]}.html">Ex {item["short"]}</a>')
    return f'<nav class="top-nav"><a href="./">All exercises</a>{"".join(links)}</nav>'


def line_chart_svg(frame: pd.DataFrame, metric: str, dimension: str = "product") -> str:
    if frame.empty:
        return '<div class="chart empty">No chart data.</div>'
    width, height = 760, 260
    margin = {"left": 54, "right": 20, "top": 20, "bottom": 36}
    data = frame[frame["dimension"].eq(dimension) & frame["variant"].eq("baseline")][
        ["year", "flow", f"median_{metric}"]
    ].dropna()
    if data.empty:
        return '<div class="chart empty">No chart data.</div>'
    years = sorted(data["year"].unique())
    values = data[f"median_{metric}"].astype(float)
    y_min = min(0.0, float(values.min()))
    y_max = max(float(values.max()), y_min + 1e-9)

    def x_scale(year: int) -> float:
        if len(years) == 1:
            return margin["left"] + (width - margin["left"] - margin["right"]) / 2
        return margin["left"] + (year - min(years)) * (width - margin["left"] - margin["right"]) / (max(years) - min(years))

    def y_scale(value: float) -> float:
        return height - margin["bottom"] - (value - y_min) * (height - margin["top"] - margin["bottom"]) / (y_max - y_min)

    colors = {"Exports": "#0f766e", "Imports": "#b45309"}
    paths = []
    labels = []
    for flow, group in data.groupby("flow", sort=True):
        group = group.sort_values("year")
        points = [(x_scale(int(row.year)), y_scale(float(getattr(row, f"median_{metric}")))) for row in group.itertuples()]
        if not points:
            continue
        d = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in points)
        color = colors.get(str(flow), "#334155")
        paths.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="3" stroke-linecap="round"/>')
        labels.append(f'<span><i style="background:{color}"></i>{escape(str(flow))}</span>')
    x_ticks = "".join(
        f'<text x="{x_scale(int(year)):.1f}" y="{height - 10}" text-anchor="middle">{int(year)}</text>'
        for year in years
        if int(year) in {min(years), max(years), 2005, 2010, 2015, 2020}
    )
    y_ticks = "".join(
        f'<text x="{margin["left"] - 8}" y="{y_scale(y):.1f}" text-anchor="end">{fmt(y)}</text>'
        for y in np.linspace(y_min, y_max, 4)
    )
    return f"""
    <div class="chart">
      <svg viewBox="0 0 {width} {height}" role="img" aria-label="Median {escape(metric)} by year">
        <line x1="{margin['left']}" y1="{height - margin['bottom']}" x2="{width - margin['right']}" y2="{height - margin['bottom']}" class="axis"/>
        <line x1="{margin['left']}" y1="{margin['top']}" x2="{margin['left']}" y2="{height - margin['bottom']}" class="axis"/>
        {x_ticks}
        {y_ticks}
        {''.join(paths)}
      </svg>
      <div class="legend">{''.join(labels)}</div>
    </div>
    """


def footer(active: str) -> str:
    links = []
    for slug, meta in METRICS.items():
        cls = "active" if slug == active else ""
        links.append(f'<a class="{cls}" href="../{slug}/">{escape(meta["label"])}</a>')
    return f"""
    <footer>
      <div>Cadot-style 156-country concentration sites</div>
      <nav>{''.join(links)}<a href="../exercises/">Exercises</a><a href="../downloads/">Downloads</a><a href="../">Hub</a></nav>
    </footer>
    """


def page_shell(title: str, body: str, current: str = "") -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <link rel="stylesheet" href="../assets/site.css">
</head>
<body>
  {body}
</body>
</html>
"""


def root_shell(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <link rel="stylesheet" href="assets/site.css">
</head>
<body>
  {body}
</body>
</html>
"""


def metric_page(metric: str, inputs: dict[str, Any], copied: dict[str, dict[str, Any]]) -> str:
    meta = METRICS[metric]
    headline = inputs["headline"].copy()
    yearly = inputs["yearly"].copy()
    rankings = inputs["rankings"]
    manifest = inputs["manifest"]
    latest = rankings[rankings["metric"].eq(metric)].copy()
    latest_years = latest.groupby("flow")["year"].max().to_dict() if not latest.empty else {}
    latest_metric = headline[headline["year"].eq(headline["year"].max())][metric].median()
    balanced = int(inputs["attrition"]["balanced_2000_2024_country"].sum())
    exercise_counts = [
        ("1", len(headline), "Common product headline panel"),
        ("2", len(inputs["exercises"]["2"]), "Bucket growth summaries"),
        ("3", len(inputs["exercises"]["3"]), "Import BEC-bin metrics"),
        ("4", len(inputs["exercises"]["4"]), "Dominant supplier summaries"),
        ("6", len(inputs["exercises"]["6"]), "Product-exclusion sensitivity"),
        ("10", len(inputs["exercises"]["10"]), "Metric-specific random benchmarks"),
        ("11", len(inputs["exercises"]["11"]), "Top leave-one-out product contributions"),
        ("12", len(inputs["exercises"]["12"]), "Growth decomposition by concentration bucket"),
    ]
    exercise_frame = pd.DataFrame(
        {
            "exercise": [
                f'<a href="{exercise_url(num)}">Exercise {num}</a>'
                for num, _count, _label in exercise_counts
            ],
            "rows": [count for _num, count, _label in exercise_counts],
            "artifact": [label for _num, _count, label in exercise_counts],
            "download": [
                f'<a href="{download_href(copied, EXERCISE_BY_SHORT[num]["source"])}">Download</a>'
                for num, _count, _label in exercise_counts
            ],
        }
    )
    ranking_tables = []
    for flow in ["Exports", "Imports"]:
        table = latest[latest["flow"].eq(flow)].sort_values("rank")
        ranking_tables.append(
            f"<section><h2>{escape(flow)} Latest Rankings</h2>"
            + table_html(table, [("rank", "Rank"), ("country", "Country"), ("year", "Year"), ("metric_value", meta["label"]), ("active_count", "Active HS6"), ("total_trade_value", "Trade value")], max_rows=20)
            + "</section>"
        )
    body = f"""
<header class="site-head">
  <a class="home-link" href="../">Trade Concentration Hub</a>
  <h1>{escape(meta["title"])}</h1>
  <p>{escape(meta["summary"])}</p>
  <nav class="top-nav">
    <a href="../gini/">Gini</a>
    <a href="../theil/">Theil</a>
    <a href="../hhi/">HHI</a>
    <a href="../exercises/">Exercises</a>
  </nav>
</header>
<main>
  <section class="stats">
    <div><strong>156</strong><span>selected reporters</span></div>
    <div><strong>{manifest.get("raw_files_processed", 0):,}</strong><span>raw files processed</span></div>
    <div><strong>{balanced:,}</strong><span>balanced reporter-flow cells</span></div>
    <div><strong>{fmt(latest_metric, meta["format"])}</strong><span>latest median {escape(meta["label"])}</span></div>
  </section>
  <section>
    <h2>Median Product {escape(meta["label"])} Over Time</h2>
    {line_chart_svg(yearly, metric)}
  </section>
  {''.join(ranking_tables)}
  <section>
    <h2>Exercise Coverage</h2>
    {link_table_html(exercise_frame, [("exercise", "Exercise"), ("rows", "Rows"), ("artifact", "Website artifact"), ("download", "Download")], max_rows=20)}
  </section>
  <section>
    <h2>Downloads</h2>
    <p><a class="button" href="../downloads/">Open downloads</a></p>
  </section>
</main>
{footer(metric)}
"""
    return page_shell(str(meta["title"]), body, metric)


def theil_appendix(inputs: dict[str, Any]) -> str:
    yearly = inputs["yearly"]
    cell = yearly[yearly["dimension"].eq("product_partner_cell") & yearly["variant"].eq("baseline")].copy()
    body = f"""
<header class="site-head">
  <a class="home-link" href="./">Theil</a>
  <h1>Theil Appendix</h1>
  <p>HS6 product-destination Theil-family analogue, clearly separated from the fixed-universe product headline.</p>
  <nav class="top-nav"><a href="../gini/">Gini</a><a href="./">Theil</a><a href="../hhi/">HHI</a><a href="../exercises/">Exercises</a></nav>
</header>
<main>
  <section>
    <h2>Product-Destination Cell Theil</h2>
    {line_chart_svg(cell, "theil", dimension="product_partner_cell")}
    {table_html(cell.sort_values(["flow", "year"], ascending=[True, False]), [("flow", "Flow"), ("year", "Year"), ("countries", "Countries"), ("median_theil", "Median Theil"), ("median_hhi", "Median HHI")], max_rows=30)}
  </section>
</main>
{footer("theil")}
"""
    return page_shell("Theil Appendix", body, "theil")


def hub_page(inputs: dict[str, Any]) -> str:
    manifest = inputs["manifest"]
    validation = inputs["validation"]
    universe = manifest.get("product_universe_counts", {})
    metric_links = "".join(
        f'<a class="hub-link" href="{slug}/"><strong>{escape(meta["label"])}</strong><span>{escape(meta["summary"])}</span></a>'
        for slug, meta in METRICS.items()
    )
    body = f"""
<header class="site-head root">
  <h1>Trade Concentration: Gini, Theil, HHI</h1>
  <p>Cadot-style 156-reporter run over UN Comtrade annual HS final data, {manifest.get("sample_window", {}).get("start_year")}-{manifest.get("sample_window", {}).get("end_year")}.</p>
  <nav class="top-nav"><a href="gini/">Gini</a><a href="theil/">Theil</a><a href="hhi/">HHI</a><a href="exercises/">Exercises</a><a href="downloads/">Downloads</a></nav>
</header>
<main>
  <section class="hub-grid">{metric_links}</section>
  <section class="stats">
    <div><strong>156</strong><span>selected reporters</span></div>
    <div><strong>{manifest.get("raw_files_processed", 0):,}</strong><span>raw files</span></div>
    <div><strong>{escape(str(universe.get("Exports", "n/a")))}</strong><span>export product universe</span></div>
    <div><strong>{escape(str(universe.get("Imports", "n/a")))}</strong><span>import product universe</span></div>
  </section>
  <section>
    <h2>Validation</h2>
    {table_html(validation, [("check", "Check"), ("passed", "Passed"), ("details", "Details")], max_rows=40)}
  </section>
  <section>
    <h2>Exercises</h2>
    <p><a class="button" href="exercises/">Open exercise pages</a></p>
  </section>
  <section>
    <h2>Downloads</h2>
    <p><a class="button" href="downloads/">Open generated files</a></p>
  </section>
</main>
<footer>
  <div>Cadot-style 156-country concentration sites</div>
  <nav><a href="gini/">Gini</a><a href="theil/">Theil</a><a href="hhi/">HHI</a><a href="exercises/">Exercises</a><a href="downloads/">Downloads</a></nav>
</footer>
"""
    return root_shell("Trade Concentration Hub", body)


def downloads_page(copied: dict[str, dict[str, Any]]) -> str:
    rows = "".join(
        f'<tr><td><a href="{escape(meta["published_name"])}">{escape(meta["published_name"])}</a></td>'
        f'<td>{meta["published_bytes"]:,}</td><td>{meta["source_bytes"]:,}</td>'
        f'<td>{escape(meta["format"])}</td><td><code>{escape(meta["sha256"][:16])}</code></td></tr>'
        for name, meta in sorted(copied.items())
    )
    body = f"""
<header class="site-head">
  <a class="home-link" href="../">Hub</a>
  <h1>Downloads</h1>
  <p>Generated Cadot-156 Gini/Theil/HHI artifacts.</p>
  <nav class="top-nav"><a href="../gini/">Gini</a><a href="../theil/">Theil</a><a href="../hhi/">HHI</a><a href="../exercises/">Exercises</a></nav>
</header>
<main>
  <div class="table-wrap"><table><thead><tr><th>File</th><th>Published bytes</th><th>Source bytes</th><th>Format</th><th>SHA-256 prefix</th></tr></thead><tbody>{rows}</tbody></table></div>
</main>
{footer("")}
"""
    return page_shell("Downloads", body)


def exercise_index_page(inputs: dict[str, Any], copied: dict[str, dict[str, Any]]) -> str:
    counts = {
        "1": len(inputs["headline"]),
        **{num: len(frame) for num, frame in inputs["exercises"].items()},
    }
    rows = []
    for item in EXERCISES:
        rows.append(
            {
                "exercise": f'<a href="exercise-{item["num"]}.html">Exercise {item["short"]}</a>',
                "title": item["title"],
                "rows": counts[item["short"]],
                "download": f'<a href="{download_href(copied, item["source"])}">Download</a>',
            }
        )
    body = f"""
<header class="site-head">
  <a class="home-link" href="../">Hub</a>
  <h1>Exercises</h1>
  <p>{escape(sample_note())}</p>
  <nav class="top-nav"><a href="../gini/">Gini</a><a href="../theil/">Theil</a><a href="../hhi/">HHI</a><a href="../downloads/">Downloads</a></nav>
</header>
<main>
  <section>
    <h2>Generated Exercise Pages</h2>
    {link_table_html(pd.DataFrame(rows), [("exercise", "Exercise"), ("title", "Page"), ("rows", "Rows"), ("download", "Download")], max_rows=20)}
  </section>
</main>
{footer("")}
"""
    return page_shell("Exercises", body)


def exercise_header(item: dict[str, str]) -> str:
    return f"""
<header class="site-head">
  <a class="home-link" href="./">Exercises</a>
  <h1>{escape(item["title"])}</h1>
  <p>{escape(item["summary"])} {escape(sample_note())}</p>
  {exercise_nav(item["short"])}
</header>
"""


def exercise_01_page(inputs: dict[str, Any], copied: dict[str, dict[str, Any]]) -> str:
    item = EXERCISE_BY_SHORT["1"]
    headline = inputs["headline"]
    rankings = inputs["rankings"].sort_values(["metric", "flow", "rank"])
    coverage = (
        headline.groupby(["flow"], as_index=False)
        .agg(
            countries=("country", "nunique"),
            reporter_year_rows=("country", "size"),
            min_year=("year", "min"),
            max_year=("year", "max"),
            median_gini=("gini", "median"),
            median_theil=("theil", "median"),
            median_hhi=("hhi", "median"),
        )
        .sort_values("flow")
    )
    body = f"""
{exercise_header(item)}
<main>
  <section class="stats">
    <div><strong>{headline["country"].nunique():,}</strong><span>countries</span></div>
    <div><strong>{headline["year"].min()}-{headline["year"].max()}</strong><span>years</span></div>
    <div><strong>{len(headline):,}</strong><span>reporter-year-flow rows</span></div>
    <div><strong>{int(headline["common_gini_theil_hhi_row"].sum()):,}</strong><span>common metric rows</span></div>
  </section>
  <section><h2>Coverage</h2>{table_html(coverage, [("flow", "Flow"), ("countries", "Countries"), ("reporter_year_rows", "Rows"), ("min_year", "First year"), ("max_year", "Last year"), ("median_gini", "Median Gini"), ("median_theil", "Median Theil"), ("median_hhi", "Median HHI")], max_rows=10)}</section>
  <section><h2>Latest Rankings Across Metrics</h2>{table_html(rankings, [("metric", "Metric"), ("flow", "Flow"), ("rank", "Rank"), ("country", "Country"), ("year", "Year"), ("metric_value", "Value"), ("active_count", "Active HS6")], max_rows=36)}</section>
  <section><h2>Data</h2><p>{download_button(copied, item["source"], "Download headline panel")}</p></section>
</main>
{footer("")}
"""
    return page_shell(item["title"], body)


def exercise_02_page(inputs: dict[str, Any], copied: dict[str, dict[str, Any]]) -> str:
    item = EXERCISE_BY_SHORT["2"]
    frame = inputs["exercises"]["2"].sort_values(["metric", "flow", "horizon", "concentration_bucket"])
    body = f"""
{exercise_header(item)}
<main>
  <section class="stats">
    <div><strong>{len(frame):,}</strong><span>summary rows</span></div>
    <div><strong>{frame["metric"].nunique()}</strong><span>metrics</span></div>
    <div><strong>{frame["horizon"].nunique()}</strong><span>horizons</span></div>
    <div><strong>{frame["concentration_bucket"].nunique()}</strong><span>buckets</span></div>
  </section>
  <section><h2>Bucket Growth Summary</h2>{table_html(frame, [("metric", "Metric"), ("flow", "Flow"), ("horizon", "Horizon"), ("concentration_bucket", "Bucket"), ("observations", "Obs."), ("countries", "Countries"), ("mean_annualized_trade_growth_log", "Mean trade growth"), ("mean_annualized_product_active_count_growth_log", "Mean active-product growth")], max_rows=72)}</section>
  <section><h2>Data</h2><p>{download_button(copied, item["source"], "Download Exercise 2")}</p></section>
</main>
{footer("")}
"""
    return page_shell(item["title"], body)


def exercise_03_page(inputs: dict[str, Any], copied: dict[str, dict[str, Any]]) -> str:
    item = EXERCISE_BY_SHORT["3"]
    frame = inputs["exercises"]["3"]
    summary = (
        frame.groupby("import_bin", as_index=False)
        .agg(
            countries=("country", "nunique"),
            rows=("country", "size"),
            median_import_share=("import_value_share", "median"),
            median_gini=("gini", "median"),
            median_theil=("theil_active", "median"),
            median_hhi=("hhi", "median"),
        )
        .sort_values("import_bin")
    )
    latest = frame[frame["year"].eq(frame["year"].max())].sort_values("import_value_share", ascending=False)
    body = f"""
{exercise_header(item)}
<main>
  <section class="stats">
    <div><strong>{frame["country"].nunique():,}</strong><span>countries</span></div>
    <div><strong>{frame["import_bin"].nunique()}</strong><span>import bins</span></div>
    <div><strong>{len(frame):,}</strong><span>rows</span></div>
    <div><strong>{frame["year"].min()}-{frame["year"].max()}</strong><span>years</span></div>
  </section>
  <section><h2>BEC-Bin Concentration Summary</h2>{table_html(summary, [("import_bin", "Import bin"), ("countries", "Countries"), ("rows", "Rows"), ("median_import_share", "Median import share"), ("median_gini", "Median Gini"), ("median_theil", "Median Theil active"), ("median_hhi", "Median HHI")], max_rows=20)}</section>
  <section><h2>Latest High-Share Bin Rows</h2>{table_html(latest, [("country", "Country"), ("year", "Year"), ("import_bin", "Import bin"), ("import_value_share", "Import share"), ("gini", "Gini"), ("theil_active", "Theil active"), ("hhi", "HHI")], max_rows=30)}</section>
  <section><h2>Data</h2><p>{download_button(copied, item["source"], "Download Exercise 3")}</p></section>
</main>
{footer("")}
"""
    return page_shell(item["title"], body)


def exercise_04_page(inputs: dict[str, Any], copied: dict[str, dict[str, Any]]) -> str:
    item = EXERCISE_BY_SHORT["4"]
    frame = inputs["exercises"]["4"]
    yearly = (
        frame.groupby("year", as_index=False)
        .agg(
            countries=("country", "nunique"),
            median_weighted_top_supplier_share=("weighted_mean_top_supplier_share", "median"),
            median_source_hhi=("weighted_mean_source_hhi", "median"),
            median_share_products_ge_75=("share_products_top_supplier_ge_75", "median"),
        )
        .sort_values("year", ascending=False)
    )
    latest = frame[frame["year"].eq(frame["year"].max())].sort_values("weighted_mean_top_supplier_share", ascending=False)
    body = f"""
{exercise_header(item)}
<main>
  <section class="stats">
    <div><strong>{frame["country"].nunique():,}</strong><span>countries</span></div>
    <div><strong>{len(frame):,}</strong><span>country-year rows</span></div>
    <div><strong>{frame["year"].min()}-{frame["year"].max()}</strong><span>years</span></div>
    <div><strong>{fmt(frame["weighted_mean_top_supplier_share"].median())}</strong><span>median top supplier share</span></div>
  </section>
  <section><h2>Yearly Supplier Concentration</h2>{table_html(yearly, [("year", "Year"), ("countries", "Countries"), ("median_weighted_top_supplier_share", "Median weighted top share"), ("median_source_hhi", "Median source HHI"), ("median_share_products_ge_75", "Median product share >= 75%")], max_rows=25)}</section>
  <section><h2>Latest Highest Dominant-Supplier Exposure</h2>{table_html(latest, [("country", "Country"), ("year", "Year"), ("weighted_mean_top_supplier_share", "Weighted top supplier share"), ("weighted_mean_source_hhi", "Weighted source HHI"), ("share_products_top_supplier_ge_75", "Products top supplier >= 75%"), ("import_value_share_products_top_supplier_ge_75", "Import value share >= 75%")], max_rows=30)}</section>
  <section><h2>Data</h2><p>{download_button(copied, item["source"], "Download Exercise 4")}</p></section>
</main>
{footer("")}
"""
    return page_shell(item["title"], body)


def exercise_06_page(inputs: dict[str, Any], copied: dict[str, dict[str, Any]]) -> str:
    item = EXERCISE_BY_SHORT["6"]
    frame = inputs["exercises"]["6"]
    keys = ["country", "iso3", "reporter_code", "year", "flow", "dimension"]
    baseline = frame[frame["excluded_hs2"].isna()][keys + ["gini", "theil", "hhi"]].rename(
        columns={"gini": "baseline_gini", "theil": "baseline_theil", "hhi": "baseline_hhi"}
    )
    excluded = frame[frame["excluded_hs2"].notna()].merge(baseline, on=keys, how="left")
    for metric in ["gini", "theil", "hhi"]:
        excluded[f"abs_delta_{metric}"] = (excluded[metric] - excluded[f"baseline_{metric}"]).abs()
    summary = (
        excluded.groupby(["dimension", "flow"], as_index=False)
        .agg(
            rows=("country", "size"),
            median_trade_share_removed=("trade_share_removed", "median"),
            median_abs_delta_gini=("abs_delta_gini", "median"),
            median_abs_delta_theil=("abs_delta_theil", "median"),
            median_abs_delta_hhi=("abs_delta_hhi", "median"),
        )
        .sort_values(["dimension", "flow"])
    )
    top = excluded.sort_values("abs_delta_theil", ascending=False)
    body = f"""
{exercise_header(item)}
<main>
  <section class="stats">
    <div><strong>{len(frame):,}</strong><span>rows including baselines</span></div>
    <div><strong>{excluded["excluded_hs2"].nunique():,}</strong><span>HS2 exclusions</span></div>
    <div><strong>{excluded["country"].nunique():,}</strong><span>countries</span></div>
    <div><strong>{fmt(excluded["trade_share_removed"].median())}</strong><span>median trade share removed</span></div>
  </section>
  <section><h2>Median Absolute Metric Changes</h2>{table_html(summary, [("dimension", "Dimension"), ("flow", "Flow"), ("rows", "Rows"), ("median_trade_share_removed", "Median removed share"), ("median_abs_delta_gini", "Median |delta Gini|"), ("median_abs_delta_theil", "Median |delta Theil|"), ("median_abs_delta_hhi", "Median |delta HHI|")], max_rows=20)}</section>
  <section><h2>Largest Theil Sensitivities</h2>{table_html(top, [("country", "Country"), ("year", "Year"), ("flow", "Flow"), ("dimension", "Dimension"), ("excluded_hs2", "Excluded HS2"), ("trade_share_removed", "Trade share removed"), ("abs_delta_gini", "|delta Gini|"), ("abs_delta_theil", "|delta Theil|"), ("abs_delta_hhi", "|delta HHI|")], max_rows=30)}</section>
  <section><h2>Data</h2><p>{download_button(copied, item["source"], "Download Exercise 6")}</p></section>
</main>
{footer("")}
"""
    return page_shell(item["title"], body)


def exercise_10_page(inputs: dict[str, Any], copied: dict[str, dict[str, Any]]) -> str:
    item = EXERCISE_BY_SHORT["10"]
    frame = inputs["exercises"]["10"]
    summary = (
        frame.groupby(["flow", "benchmark_null"], as_index=False)
        .agg(
            rows=("country", "size"),
            simulations=("simulations", "median"),
            median_gini_gap=("actual_minus_sim_median_gini", "median"),
            median_theil_gap=("actual_minus_sim_median_theil", "median"),
            median_hhi_gap=("actual_minus_sim_median_hhi", "median"),
        )
        .sort_values(["flow", "benchmark_null"])
    )
    top = frame.sort_values("actual_minus_sim_median_theil", ascending=False)
    body = f"""
{exercise_header(item)}
<main>
  <section class="stats">
    <div><strong>{len(frame):,}</strong><span>benchmark rows</span></div>
    <div><strong>{int(frame["simulations"].median()):,}</strong><span>simulations per row</span></div>
    <div><strong>{frame["benchmark_null"].nunique()}</strong><span>null models</span></div>
    <div><strong>{frame["country"].nunique():,}</strong><span>countries</span></div>
  </section>
  <section><h2>Actual Minus Simulation Median</h2>{table_html(summary, [("flow", "Flow"), ("benchmark_null", "Benchmark null"), ("rows", "Rows"), ("simulations", "Simulations"), ("median_gini_gap", "Median Gini gap"), ("median_theil_gap", "Median Theil gap"), ("median_hhi_gap", "Median HHI gap")], max_rows=20)}</section>
  <section><h2>Largest Theil Gaps</h2>{table_html(top, [("country", "Country"), ("year", "Year"), ("flow", "Flow"), ("benchmark_null", "Benchmark"), ("actual_theil", "Actual Theil"), ("sim_theil_median", "Sim median Theil"), ("sim_theil_p05", "Sim p05"), ("sim_theil_p95", "Sim p95"), ("actual_minus_sim_median_theil", "Gap")], max_rows=30)}</section>
  <section><h2>Data</h2><p>{download_button(copied, item["source"], "Download Exercise 10")}</p></section>
</main>
{footer("")}
"""
    return page_shell(item["title"], body)


def exercise_11_page(inputs: dict[str, Any], copied: dict[str, dict[str, Any]]) -> str:
    item = EXERCISE_BY_SHORT["11"]
    frame = inputs["exercises"]["11"]
    summary = (
        frame.groupby(["metric", "flow"], as_index=False)
        .agg(
            rows=("country", "size"),
            countries=("country", "nunique"),
            median_abs_contribution=("abs_loo_contribution", "median"),
            max_abs_contribution=("abs_loo_contribution", "max"),
        )
        .sort_values(["metric", "flow"])
    )
    top = frame.sort_values("abs_loo_contribution", ascending=False)
    body = f"""
{exercise_header(item)}
<main>
  <section class="stats">
    <div><strong>{len(frame):,}</strong><span>retained top-product rows</span></div>
    <div><strong>{frame["metric"].nunique()}</strong><span>metrics</span></div>
    <div><strong>{frame["cmd_code"].nunique():,}</strong><span>HS6 products in top lists</span></div>
    <div><strong>{fmt(frame["abs_loo_contribution"].max())}</strong><span>largest absolute contribution</span></div>
  </section>
  <section><h2>Contribution Summary</h2>{table_html(summary, [("metric", "Metric"), ("flow", "Flow"), ("rows", "Rows"), ("countries", "Countries"), ("median_abs_contribution", "Median absolute contribution"), ("max_abs_contribution", "Max absolute contribution")], max_rows=20)}</section>
  <section><h2>Largest Product Contributions</h2>{table_html(top, [("metric", "Metric"), ("flow", "Flow"), ("country", "Country"), ("year", "Year"), ("rank_abs_contribution", "Rank"), ("cmd_code", "HS6"), ("product_label", "Product"), ("trade_value", "Trade value"), ("loo_contribution", "Contribution"), ("abs_loo_contribution", "Absolute contribution")], max_rows=30)}</section>
  <section><h2>Data</h2><p>{download_button(copied, item["source"], "Download Exercise 11")}</p></section>
</main>
{footer("")}
"""
    return page_shell(item["title"], body)


def exercise_12_page(inputs: dict[str, Any], copied: dict[str, dict[str, Any]]) -> str:
    item = EXERCISE_BY_SHORT["12"]
    frame = inputs["exercises"]["12"].sort_values(["metric", "flow", "horizon", "base_concentration_bucket"])
    body = f"""
{exercise_header(item)}
<main>
  <section class="stats">
    <div><strong>{len(frame):,}</strong><span>summary rows</span></div>
    <div><strong>{frame["metric"].nunique()}</strong><span>metrics</span></div>
    <div><strong>{frame["base_concentration_bucket"].nunique()}</strong><span>base buckets</span></div>
    <div><strong>{frame["horizon"].nunique()}</strong><span>horizons</span></div>
  </section>
  <section><h2>Growth Decomposition Summary</h2>{table_html(frame, [("metric", "Metric"), ("flow", "Flow"), ("horizon", "Horizon"), ("base_concentration_bucket", "Base concentration bucket"), ("observations", "Obs."), ("countries", "Countries"), ("mean_annualized_trade_growth_log", "Mean trade growth"), ("mean_annualized_product_active_count_growth_log", "Product active growth"), ("mean_annualized_partner_active_count_growth_log", "Partner active growth"), ("mean_annualized_cell_active_count_growth_log", "Cell active growth")], max_rows=60)}</section>
  <section><h2>Data</h2><p>{download_button(copied, item["source"], "Download Exercise 12")}</p></section>
</main>
{footer("")}
"""
    return page_shell(item["title"], body)


def exercise_page(short: str, inputs: dict[str, Any], copied: dict[str, dict[str, Any]]) -> str:
    builders = {
        "1": exercise_01_page,
        "2": exercise_02_page,
        "3": exercise_03_page,
        "4": exercise_04_page,
        "6": exercise_06_page,
        "10": exercise_10_page,
        "11": exercise_11_page,
        "12": exercise_12_page,
    }
    return builders[short](inputs, copied)


def write_assets(output: Path) -> None:
    css = """
:root {
  color-scheme: light;
  --ink: #172026;
  --muted: #5b6770;
  --line: #d8dee3;
  --paper: #fbfcfd;
  --accent: #0f766e;
  --warm: #b45309;
  --blue: #1d4ed8;
}
* { box-sizing: border-box; }
body { margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: var(--ink); background: var(--paper); line-height: 1.5; }
a { color: var(--blue); text-decoration: none; }
a:hover { text-decoration: underline; }
.site-head { padding: 32px clamp(18px, 5vw, 64px) 22px; border-bottom: 1px solid var(--line); background: #fff; }
.site-head.root { padding-top: 44px; }
.home-link { display: inline-block; margin-bottom: 12px; color: var(--muted); font-size: 14px; }
h1 { margin: 0 0 8px; font-size: clamp(30px, 4vw, 52px); line-height: 1.05; letter-spacing: 0; }
h2 { margin: 0 0 14px; font-size: 21px; letter-spacing: 0; }
p { margin: 0; max-width: 860px; color: var(--muted); }
main { width: min(1180px, calc(100% - 36px)); margin: 0 auto; padding: 26px 0 44px; }
section { margin: 0 0 28px; }
.top-nav { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 18px; }
.top-nav a, .button { display: inline-flex; align-items: center; min-height: 36px; padding: 7px 12px; border: 1px solid var(--line); background: #fff; border-radius: 6px; color: var(--ink); }
.stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.stats div { border: 1px solid var(--line); background: #fff; border-radius: 6px; padding: 14px; }
.stats strong { display: block; font-size: 26px; line-height: 1.1; }
.stats span { color: var(--muted); font-size: 13px; }
.hub-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.hub-link { display: block; border: 1px solid var(--line); background: #fff; border-radius: 6px; padding: 18px; color: var(--ink); }
.hub-link strong { display: block; font-size: 24px; margin-bottom: 8px; }
.hub-link span { display: block; color: var(--muted); }
.chart { border: 1px solid var(--line); background: #fff; border-radius: 6px; padding: 14px; overflow-x: auto; }
.chart svg { width: 100%; min-width: 620px; display: block; }
.axis { stroke: #9aa4ad; stroke-width: 1; }
.chart text { fill: var(--muted); font-size: 12px; }
.legend { display: flex; gap: 14px; margin-top: 8px; color: var(--muted); font-size: 13px; }
.legend i { display: inline-block; width: 12px; height: 12px; margin-right: 6px; vertical-align: -1px; border-radius: 2px; }
.table-wrap { overflow-x: auto; border: 1px solid var(--line); border-radius: 6px; background: #fff; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th, td { padding: 9px 10px; border-bottom: 1px solid var(--line); text-align: left; white-space: nowrap; }
th { color: var(--muted); font-weight: 650; background: #f5f7f8; }
tr:last-child td { border-bottom: 0; }
footer { border-top: 1px solid var(--line); padding: 18px clamp(18px, 5vw, 64px); display: flex; gap: 16px; justify-content: space-between; flex-wrap: wrap; color: var(--muted); background: #fff; }
footer nav { display: flex; gap: 12px; flex-wrap: wrap; }
footer a.active { color: var(--ink); font-weight: 700; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }
.empty { color: var(--muted); padding: 12px; }
@media (max-width: 760px) {
  .stats, .hub-grid { grid-template-columns: 1fr; }
  h1 { font-size: 34px; }
  main { width: min(100% - 24px, 1180px); }
}
"""
    (output / "assets" / "site.css").write_text(css.strip() + "\n", encoding="utf-8")


def copy_downloads(output: Path) -> dict[str, dict[str, Any]]:
    copied: dict[str, dict[str, Any]] = {}
    for name in DOWNLOADS:
        source = RESULT_DIR / name
        if not source.exists():
            raise RuntimeError(f"Missing download source: {source}")
        source_bytes = source.stat().st_size
        if source_bytes > MAX_RAW_DOWNLOAD_BYTES:
            published_name = f"{name}.gz"
            dest = output / "downloads" / published_name
            gzip_copy(source, dest)
            file_format = "gzip"
        else:
            published_name = name
            dest = output / "downloads" / published_name
            shutil.copy2(source, dest)
            file_format = "raw"
        copied[name] = {
            "published_name": published_name,
            "source_name": name,
            "source_bytes": source_bytes,
            "published_bytes": dest.stat().st_size,
            "format": file_format,
            "sha256": sha256(dest),
        }
    return copied


def write_site(output: Path, inputs: dict[str, Any]) -> dict[str, Any]:
    clean_output(output)
    write_assets(output)
    copied = copy_downloads(output)
    (output / "index.html").write_text(hub_page(inputs), encoding="utf-8")
    for metric in METRICS:
        (output / metric / "index.html").write_text(metric_page(metric, inputs, copied), encoding="utf-8")
    (output / "theil" / "appendix.html").write_text(theil_appendix(inputs), encoding="utf-8")
    (output / "downloads" / "index.html").write_text(downloads_page(copied), encoding="utf-8")
    (output / "exercises" / "index.html").write_text(exercise_index_page(inputs, copied), encoding="utf-8")
    for item in EXERCISES:
        (output / "exercises" / f"exercise-{item['num']}.html").write_text(
            exercise_page(item["short"], inputs, copied),
            encoding="utf-8",
        )
    manifest = {
        "built_at_utc": now_utc(),
        "output": str(output),
        "source_result_dir": str(RESULT_DIR),
        "pages": PAGES,
        "downloads": copied,
    }
    (output / "site_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    validate_site(output)
    return manifest


def validate_site(output: Path) -> None:
    required = [output / page for page in PAGES]
    missing = [str(path) for path in required if not path.exists() or path.stat().st_size == 0]
    if missing:
        raise RuntimeError(f"Missing built site files: {missing}")
    for slug in METRICS:
        text = (output / slug / "index.html").read_text(encoding="utf-8")
        for other in METRICS:
            if f'../{other}/' not in text:
                raise RuntimeError(f"{slug} page is missing footer/nav link to {other}.")
        if "../exercises/" not in text:
            raise RuntimeError(f"{slug} page is missing exercise navigation.")
    exercise_required = ["../gini/", "../theil/", "../hhi/", "../downloads/", "exercise-"]
    for page in ["exercises/index.html", *[f"exercises/exercise-{item['num']}.html" for item in EXERCISES]]:
        text = (output / page).read_text(encoding="utf-8")
        for target in exercise_required:
            if target not in text:
                raise RuntimeError(f"{page} is missing link/content target {target}.")


def publish_site(output: Path, destination: Path) -> None:
    if not destination.exists():
        raise RuntimeError(f"Publish destination does not exist: {destination}")
    clean_output(destination)
    for child in output.iterdir():
        target = destination / child.name
        if child.is_dir():
            shutil.copytree(child, target, dirs_exist_ok=True)
        else:
            shutil.copy2(child, target)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--publish", type=Path, default=None, help="Optional Pages repo destination.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    inputs = load_inputs()
    manifest = write_site(args.output, inputs)
    if args.publish is not None:
        publish_site(args.output, args.publish)
        manifest["published_to"] = str(args.publish)
        (args.publish / "site_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
