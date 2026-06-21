#!/usr/bin/env python3
"""Write current status artifacts for literal Cadot original replication tracks."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import trade_concentration_pipeline as tcp  # noqa: E402


CADOT_WIKI = ROOT / "literature" / "export_margins" / "wiki" / "papers" / "06_cadot_carrere_strauss_kahn_2011_export_diversification_hump.md"
AUDIT_DIR = ROOT / "results" / "cadot_replication_audit"


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def source_evidence() -> dict[str, Any]:
    evidence = {
        "local_wiki_exists": CADOT_WIKI.exists(),
        "local_wiki_path": rel(CADOT_WIKI),
        "paper_country_count": 156,
        "paper_period": "1988-2006",
        "paper_product_universe": 4991,
        "paper_baseline_regression_countries_after_microstate_exclusion": 141,
        "exact_country_list_recovered": False,
        "exact_country_list_count": 0,
        "right_of_turning_point_names_extracted": [],
    }
    if not CADOT_WIKI.exists():
        return evidence
    text = CADOT_WIKI.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"Countries on the right of the turning point in 2006\|(?P<body>.+?)Absolute value", text, flags=re.S)
    if match:
        names = sorted(set(re.findall(r"\b[A-Z][A-Za-z. ]{2,30}\b", match.group("body"))))
        filtered = [
            name.strip()
            for name in names
            if name.strip()
            and not any(token in name for token in ["Col", "Countries", "Dependent", "GDPpc", "Nber", "R2", "Turning"])
        ]
        evidence["right_of_turning_point_names_extracted"] = filtered[:80]
    return evidence


def status_rows(evidence: dict[str, Any]) -> pd.DataFrame:
    rows = [
        {
            "source": "local Cadot wiki/PDF extraction",
            "path_or_url": evidence["local_wiki_path"],
            "paper_pdf_or_text": "yes" if evidence["local_wiki_exists"] else "missing",
            "country_list_status": "not recovered",
            "recovered_country_count": evidence["exact_country_list_count"],
            "data_status": "no raw/processed Cadot package",
            "code_status": "no Cadot replication package",
            "notes": "Local extraction contains paper tables and annex facts, but not an isolated full 156-country list.",
        },
        {
            "source": "public source audit",
            "path_or_url": "EconPapers, World Bank OKR, SSRN, HAL/IDEAS, MIT Press targeted search",
            "paper_pdf_or_text": "yes",
            "country_list_status": "not found",
            "recovered_country_count": 0,
            "data_status": "not found",
            "code_status": "not found",
            "notes": "No public replication package located in targeted search as of 2026-06-16.",
        },
    ]
    return pd.DataFrame(rows)


def write_track_blocker(sample_name: str, evidence: dict[str, Any], extended: bool) -> None:
    processed = tcp.sample_processed_dir(sample_name)
    results = tcp.sample_results_dir(sample_name)
    processed.mkdir(parents=True, exist_ok=True)
    results.mkdir(parents=True, exist_ok=True)
    period = "1988-latest available" if extended else "1988-2006"
    manifest = {
        "created_at_utc": now_utc(),
        "country_sample": sample_name,
        "status": "blocked_not_exact_replication",
        "period_target": period,
        "research_only": True,
        "website_default": False,
        "exact_country_list_recovered": bool(evidence["exact_country_list_recovered"]),
        "recovered_country_count": int(evidence["exact_country_list_count"]),
        "cadot_target_country_count": int(evidence["paper_country_count"]),
        "cadot_target_product_universe": int(evidence["paper_product_universe"]),
        "blocked_reasons": [
            "Exact Cadot 156-country list is not recovered from current local/public sources.",
            "Mirror-import raw-to-exporter construction is not implemented for the original period.",
            "HS0 4,991-line harmonized universe is not reproduced from available concordances.",
        ],
        "next_required_action": "Recover exact country list or build an explicitly reconstructed 1988-2006 mirror-data country list with mismatch reporting.",
        "source_evidence": evidence,
    }
    write_json(processed / "cadot_original_status.json", manifest)
    write_json(results / "cadot_original_status.json", manifest)
    blocker = f"""# Cadot Original Track Status

Generated: {manifest['created_at_utc']}

Sample: `{sample_name}`

Status: **blocked, not an exact Cadot replication yet**.

Target period: {period}

Why blocked:

- Exact Cadot 156-country list is not recovered from current local/public sources.
- Mirror-import raw-to-exporter construction is not implemented for the original period.
- HS0 4,991-line harmonized universe is not reproduced from available concordances.

Do not label this track as a completed Cadot replication. Use `cadot_broad_156` only as a modern 2000-2024 sensitivity.
"""
    (results / "cadot_original_rebuild_blocker.md").write_text(blocker, encoding="utf-8")


def main() -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    evidence = source_evidence()
    status = status_rows(evidence)
    status.to_csv(AUDIT_DIR / "cadot_country_list_status.csv", index=False)
    write_json(AUDIT_DIR / "cadot_country_list_status.json", evidence)
    write_track_blocker(tcp.CADOT_ORIGINAL_SAMPLE, evidence, extended=False)
    write_track_blocker(tcp.CADOT_ORIGINAL_EXTENDED_SAMPLE, evidence, extended=True)
    print(f"Wrote {rel(AUDIT_DIR / 'cadot_country_list_status.csv')}")
    print(f"Wrote {rel(tcp.sample_results_dir(tcp.CADOT_ORIGINAL_SAMPLE) / 'cadot_original_rebuild_blocker.md')}")
    print(f"Wrote {rel(tcp.sample_results_dir(tcp.CADOT_ORIGINAL_EXTENDED_SAMPLE) / 'cadot_original_rebuild_blocker.md')}")


if __name__ == "__main__":
    main()
