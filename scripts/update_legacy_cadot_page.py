#!/usr/bin/env python3
"""Update only the Cadot page in the legacy trade-gini-map-old site."""

from __future__ import annotations

import argparse
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


def update_page(output: Path) -> None:
    site.configure_site_sample("cadot_broad_156")
    data = site.load_cadot_hump_data()
    body = site.build_cadot_integrated_body(data)

    page_path = output / "cadot-hump.html"
    if not page_path.exists():
        raise FileNotFoundError(f"Legacy Cadot page is missing: {page_path}")
    html = page_path.read_text(encoding="utf-8")
    main_pattern = re.compile(r"<main>.*?</main>", flags=re.DOTALL)
    if len(main_pattern.findall(html)) != 1:
        raise RuntimeError("Expected exactly one <main> block in the legacy Cadot page.")
    html = main_pattern.sub(f"<main>\n{body}\n  </main>", html)
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
    ]
    missing_text = [token for token in required if token not in html]
    if missing_text:
        raise RuntimeError(f"Cadot page is missing required content: {missing_text}")
    forbidden = ["__PLACEHOLDER__", ">None<", ">nan<"]
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
