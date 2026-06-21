#!/usr/bin/env python3
"""Update only the Cadot page in the legacy trade-gini-map-old site."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

import build_trade_gini_site as site


DEFAULT_OUTPUT = Path("/Users/tanushsawhney/Desktop/trade-gini-map-old")


def copy_file(source: Path, destination: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(f"Required Cadot page artifact is missing: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_preserved_sections(html: str) -> list[str]:
    sections: list[str] = []
    for start_marker, end_marker in [
        (
            "<!-- PRODUCTION_CORE_OLD_CONE_START -->",
            "<!-- PRODUCTION_CORE_OLD_CONE_END -->",
        ),
    ]:
        pattern = re.compile(
            rf"{re.escape(start_marker)}.*?{re.escape(end_marker)}",
            flags=re.DOTALL,
        )
        match = pattern.search(html)
        if match:
            sections.append(match.group(0))
    return sections


def update_page(output: Path) -> None:
    site.configure_site_sample("cadot_broad_156")
    data = site.load_cadot_hump_data()
    body = site.build_cadot_integrated_body(data)

    page_path = output / "cadot-hump.html"
    if not page_path.exists():
        raise FileNotFoundError(f"Legacy Cadot page is missing: {page_path}")
    html = page_path.read_text(encoding="utf-8")
    preserved_sections = extract_preserved_sections(html)
    main_pattern = re.compile(r"<main>.*?</main>", flags=re.DOTALL)
    if len(main_pattern.findall(html)) != 1:
        raise RuntimeError("Expected exactly one <main> block in the legacy Cadot page.")
    preserved_html = "\n\n".join(preserved_sections)
    if preserved_html:
        preserved_html = f"\n\n  {preserved_html}\n"
    html = main_pattern.sub(f"<main>\n{body}{preserved_html}  </main>", html)
    html = re.sub(
        r"<title>.*?</title>",
        "<title>Cadot Replication Results</title>",
        html,
        count=1,
        flags=re.DOTALL,
    )
    html = html.replace(
        'href="cadot-hump.html">Behind hump</a>',
        'href="cadot-hump.html">Cadot results</a>',
    )
    html = re.sub(
        r"<footer class=\"site-footer\">\s*<p>Generated from local research outputs on .*?</p>\s*</footer>",
        (
            '<footer class="site-footer">\n'
            f"    <p>Cadot page updated from broad-156 and historical research outputs on {site.now_utc()}.</p>\n"
            "  </footer>"
        ),
        html,
        count=1,
        flags=re.DOTALL,
    )
    html = "\n".join(line.rstrip() for line in html.splitlines()) + "\n"
    page_path.write_text(html, encoding="utf-8")

    figure_sources = {
        **site.CADOT_BROAD_PPP_FIGURE_FILES,
        **site.CADOT_INTEGRATED_FIGURE_FILES,
    }
    for key, source in figure_sources.items():
        copy_file(source, output / "assets" / "figures" / f"{key}.png")

    # Replace legacy Cadot filenames as well. Older cached page HTML referenced
    # these generic paths, which previously exposed rd2 figures.
    legacy_figure_aliases = {
        "cadot_hump_curve.png": site.CADOT_INTEGRATED_FIGURE_FILES[
            "cadot_export_gini_theil_fits"
        ],
        "cadot_mechanism_scorecard.png": site.CADOT_INTEGRATED_FIGURE_FILES[
            "cadot_broad_mechanism_scorecard"
        ],
        "cadot_old_cone_exit_plot.png": site.CADOT_INTEGRATED_FIGURE_FILES[
            "cadot_broad_old_cone_exit"
        ],
        "cadot_mechanical_robustness_ladder.png": (
            site.CADOT_BROAD_TRIBUNAL_FIGURE_DIR / "mechanical_robustness_ladder.png"
        ),
        "cadot_ppp_hump_level.png": site.CADOT_BROAD_PPP_FIGURE_FILES[
            "cadot_broad_ppp_hump_level"
        ],
        "cadot_ppp_hump_log.png": site.CADOT_BROAD_PPP_FIGURE_FILES[
            "cadot_broad_ppp_hump_log"
        ],
    }
    for filename, source in legacy_figure_aliases.items():
        copy_file(source, output / "assets" / "figures" / filename)

    download_sources = {
        **{
            filename: site.CADOT_BROAD_PPP_TABLE_FILES[source_key]
            for filename, source_key in site.CADOT_BROAD_PPP_DOWNLOAD_FILENAMES.items()
        },
        **site.CADOT_BROAD_PPP_EXTRA_DOWNLOADS,
        **{
            filename: site.CADOT_INTEGRATED_TABLE_FILES[source_key]
            for filename, source_key in site.CADOT_INTEGRATED_DOWNLOAD_FILENAMES.items()
        },
        **site.CADOT_INTEGRATED_EXTRA_DOWNLOADS,
    }
    for filename, source in download_sources.items():
        copy_file(source, output / "assets" / "downloads" / filename)

    manifest_path = output / "assets" / "site-manifest.json"
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.exists()
        else {}
    )
    manifest["cadot_integrated_update"] = {
        "created_at_utc": site.now_utc(),
        "country_sample": "cadot_broad_156",
        "page": "cadot-hump.html",
        "historical_partner_window": "1827-2014",
        "figures": sorted(f"assets/figures/{key}.png" for key in figure_sources),
        "legacy_figure_aliases_replaced_with_broad_156": sorted(
            f"assets/figures/{name}" for name in legacy_figure_aliases
        ),
        "downloads": sorted(f"assets/downloads/{name}" for name in download_sources),
        "generator": "scripts/update_legacy_cadot_page.py",
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=True, allow_nan=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def validate_page(output: Path) -> None:
    page_path = output / "cadot-hump.html"
    html = page_path.read_text(encoding="utf-8")
    required = [
        'id="cadot-interpretation-results"',
        'id="cadot-modern-156-results"',
        'id="cadot-production-core"',
        'id="cadot-historical-partners"',
        'id="cadot-latest-mechanisms"',
        "14.5%",
        "14.9%",
        "72.2%",
        "1827-2014",
        "Broad 156 sample",
        "How to interpret the exit-cone image",
    ]
    missing_text = [token for token in required if token not in html]
    if missing_text:
        raise RuntimeError(f"Cadot page is missing required content: {missing_text}")
    forbidden = [
        "__PLACEHOLDER__",
        ">None<",
        ">nan<",
        "rd2 Balanced",
        "rd2 countries",
        "55-country",
    ]
    found_forbidden = [token for token in forbidden if token in html]
    if found_forbidden:
        raise RuntimeError(f"Cadot page contains forbidden output: {found_forbidden}")

    missing_assets: list[str] = []
    for reference in re.findall(r'(?:href|src)="([^"]+)"', html):
        if reference.startswith(("http://", "https://", "#", "mailto:")):
            continue
        local_reference = reference.split("#", 1)[0].split("?", 1)[0]
        local = output / local_reference
        if not local.exists():
            missing_assets.append(reference)
    if missing_assets:
        raise RuntimeError(
            f"Cadot page has missing local references: {sorted(set(missing_assets))}"
        )

    modern_sources = {
        **site.CADOT_BROAD_PPP_FIGURE_FILES,
        "cadot_export_gini_theil_fits": site.CADOT_INTEGRATED_FIGURE_FILES[
            "cadot_export_gini_theil_fits"
        ],
        "cadot_broad_mechanism_scorecard": site.CADOT_INTEGRATED_FIGURE_FILES[
            "cadot_broad_mechanism_scorecard"
        ],
        "cadot_broad_old_cone_exit": site.CADOT_INTEGRATED_FIGURE_FILES[
            "cadot_broad_old_cone_exit"
        ],
    }
    wrong_lineage = {
        key: str(source)
        for key, source in modern_sources.items()
        if "cadot_broad_156" not in source.parts
    }
    if wrong_lineage:
        raise RuntimeError(f"Modern Cadot figures are not broad-156: {wrong_lineage}")
    for key, source in modern_sources.items():
        copied = output / "assets" / "figures" / f"{key}.png"
        if sha256(source) != sha256(copied):
            raise RuntimeError(f"Copied Cadot figure differs from source: {key}")

    rd2_figure_dir = (
        site.ROOT / "results" / "samples" / "rd2_countries" / "cadot_hump_tribunal_figures"
    )
    comparisons = {
        "cadot_broad_mechanism_scorecard": rd2_figure_dir / "mechanism_scorecard.png",
        "cadot_broad_old_cone_exit": rd2_figure_dir / "old_cone_exit_plot.png",
    }
    duplicate_rd2 = [
        key
        for key, rd2_source in comparisons.items()
        if rd2_source.exists()
        and sha256(output / "assets" / "figures" / f"{key}.png")
        == sha256(rd2_source)
    ]
    if duplicate_rd2:
        raise RuntimeError(f"Broad Cadot figures duplicate rd2 assets: {duplicate_rd2}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    update_page(args.output)
    validate_page(args.output)
    print(f"Updated and validated {args.output / 'cadot-hump.html'}")


if __name__ == "__main__":
    main()
