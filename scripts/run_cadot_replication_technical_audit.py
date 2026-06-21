#!/usr/bin/env python3
"""Build a technical audit report for the Cadot replication track.

The report is intentionally conservative: it inventories the current checkout
and labels absent generated artifacts as absent, even when old review notes
describe prior successful runs.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "results" / "cadot_replication_audit"
CADOT_WIKI = ROOT / "literature" / "export_margins" / "wiki" / "papers" / "06_cadot_carrere_strauss_kahn_2011_export_diversification_hump.md"
DATA_ACCESS_BLOCKER = ROOT / "results" / "data_access_blocker.md"
AVAILABILITY = ROOT / "data" / "raw" / "comtrade" / "availability" / "cadot_broad_156_public_availability.csv"


@dataclass(frozen=True)
class Artifact:
    track: str
    role: str
    path: str
    exists: bool
    kind: str
    rows: int | None = None
    columns: int | None = None
    note: str = ""


@dataclass(frozen=True)
class SourceRecord:
    source: str
    url: str
    paper_pdf: str
    country_list: str
    data: str
    code: str
    appendix_tables: str
    replication_package: str
    evidence: str


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def file_kind(path: Path) -> str:
    if path.is_dir():
        return "directory"
    if path.suffix:
        return path.suffix.lstrip(".")
    return "file"


def quick_shape(path: Path) -> tuple[int | None, int | None, str]:
    if not path.exists() or path.is_dir():
        return None, None, ""
    try:
        if path.suffix.lower() == ".csv":
            with path.open(newline="") as fh:
                reader = csv.reader(fh)
                header = next(reader, [])
                rows = sum(1 for _ in reader)
            return rows, len(header), ""
        if path.suffix.lower() == ".parquet":
            df = pd.read_parquet(path, engine="pyarrow")
            return int(len(df)), int(len(df.columns)), "parquet shape read"
        if path.suffix.lower() in {".md", ".html", ".json"}:
            return None, None, f"{path.stat().st_size} bytes"
    except Exception as exc:  # pragma: no cover - diagnostic path
        return None, None, f"shape read failed: {exc}"
    return None, None, f"{path.stat().st_size} bytes"


def artifact(track: str, role: str, path: Path, note: str = "") -> Artifact:
    rows, cols, shape_note = quick_shape(path)
    combined_note = "; ".join(part for part in [note, shape_note] if part)
    return Artifact(
        track=track,
        role=role,
        path=rel(path),
        exists=path.exists(),
        kind=file_kind(path),
        rows=rows,
        columns=cols,
        note=combined_note,
    )


def expected_artifacts() -> list[Artifact]:
    processed = ROOT / "data" / "processed" / "samples"
    results = ROOT / "results" / "samples"
    items: list[Artifact] = []
    for track in ["cadot_original_1988_2006", "cadot_original_countries_extended", "cadot_broad_156", "rd2_countries"]:
        items.extend(
            [
                artifact(track, "processed sample directory", processed / track),
                artifact(track, "results sample directory", results / track),
                artifact(track, "country panel", processed / track / "comtrade_country_panel.csv"),
                artifact(track, "country-year HS coverage", processed / track / "country_year_hs_coverage.csv"),
                artifact(track, "all-year concentration panel", processed / track / "concentration_all_years.parquet"),
                artifact(track, "PPP regression summary", results / track / "ppp_hump_regressions_summary.csv"),
                artifact(track, "PPP analytic panel", results / track / "ppp_hump_regression_panel.csv"),
            ]
        )
    items.extend(
        [
            artifact(
                "cadot_broad_156",
                "modern three-metric concentration panel",
                results / "cadot_broad_156" / "three_metric_tables" / "concentration_metric_all_years.parquet",
            ),
            artifact(
                "cadot_broad_156",
                "modern three-metric validation checks",
                results / "cadot_broad_156" / "three_metric_tables" / "validation_checks.csv",
            ),
            artifact(
                "cadot_broad_156",
                "modern three-metric adversarial review",
                results / "cadot_broad_156" / "three_metric_tables" / "adversarial_review.md",
            ),
            artifact(
                "cadot_broad_156",
                "broad PPP regression summary",
                results / "cadot_broad_156" / "cadot_broad_ppp_hump_regression_tables" / "ppp_hump_regression_summary.csv",
            ),
            artifact(
                "cadot_broad_156",
                "broad PPP analytic panel",
                results / "cadot_broad_156" / "cadot_broad_ppp_hump_regression_tables" / "ppp_hump_analysis_panel.csv",
            ),
        ]
    )
    items.extend(
        [
            artifact("repository", "Comtrade availability cache", AVAILABILITY),
            artifact("repository", "data access blocker", DATA_ACCESS_BLOCKER),
            artifact("repository", "Cadot local wiki extraction", CADOT_WIKI),
            artifact("repository", "website work-in-progress page", ROOT / "workinprogress.html"),
            artifact("repository", "website work-in-progress page", ROOT / "results" / "workinprogress.html"),
            artifact("repository", "website generator", ROOT / "scripts" / "build_trade_gini_site.py"),
            artifact("repository", "Cadot modern PPP runner", ROOT / "scripts" / "run_ppp_hump_regressions.py"),
            artifact("repository", "Cadot tribunal runner", ROOT / "scripts" / "run_cadot_hump_tribunal.py"),
            artifact("repository", "Cadot broad runner wrapper", ROOT / "scripts" / "run_cadot_broad_ppp_hump_regressions.py"),
            artifact("repository", "Cadot broad sample tests", ROOT / "tests" / "test_cadot_broad_sample.py"),
            artifact("repository", "Cadot tribunal tests", ROOT / "tests" / "test_cadot_hump_tribunal.py"),
            artifact("prior review", "round 1 rd2 review", ROOT / "correspondence" / "referee2" / "2026-05-30_round1_cadot_results_report.md"),
            artifact("prior review", "broad 156 rebuild review", ROOT / "correspondence" / "referee2" / "2026-06-02_cadot_broad_156_rebuild_review.md"),
            artifact("prior review", "constant PPP rerun review", ROOT / "correspondence" / "referee2" / "2026-06-02_cadot_constant_ppp_rerun_review.md"),
        ]
    )
    return items


def source_records() -> list[SourceRecord]:
    return [
        SourceRecord(
            "EconPapers/RePEc article page",
            "https://econpapers.repec.org/article/tprrestat/v_3a93_3ay_3a2011_3ai_3a2_3ap_3a590-605.htm",
            "restricted publisher PDF link",
            "not found",
            "not found",
            "not found",
            "abstract and bibliographic metadata only",
            "not found",
            "Verifies REST 2011 article, 156 countries, 19 years, HS6, 4,991 product lines, hump and extensive-margin reconcentration.",
        ),
        SourceRecord(
            "World Bank Open Knowledge Repository",
            "https://openknowledge.worldbank.org/entities/publication/b2af31a8-410a-53c8-b364-17661bb4cd24",
            "article file listed",
            "not found",
            "field present but blank",
            "not found",
            "metadata and article file",
            "not found",
            "The page has a Link to Data Set heading, but no visible dataset link in the metadata inspected.",
        ),
        SourceRecord(
            "MIT Press Direct article page",
            "https://direct.mit.edu/rest/article/93/2/590/58595/Export-Diversification-What-s-behind-the-Hump",
            "publisher article/PDF",
            "not found in public metadata",
            "not found in public metadata",
            "not found in public metadata",
            "publisher article page",
            "not found",
            "Targeted search did not reveal a supplementary-material or replication-package link.",
        ),
        SourceRecord(
            "SSRN page",
            "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2557500",
            "paper versions listed",
            "not found",
            "not found",
            "not found",
            "abstract and versions",
            "not found",
            "Lists REST and CEPR versions; abstract repeats the main sample and mechanism facts.",
        ),
        SourceRecord(
            "IDEAS/RePEc page",
            "https://ideas.repec.org/a/tpr/restat/v93y2011i2p590-605.html",
            "restricted publisher PDF link plus working-paper versions",
            "not found",
            "not found",
            "not found",
            "metadata and links to CEPR/CERDI/HAL/CEPREMAP versions",
            "not found",
            "Useful for enumerating public working-paper versions; no data/code package is listed.",
        ),
        SourceRecord(
            "Local PDF/wiki extraction",
            rel(CADOT_WIKI),
            "local PDF extracted to markdown",
            "partial: right-of-turning-point country names in tables, no full 156 list isolated",
            "no raw data",
            "no code",
            "tables and annex extracted",
            "not found",
            "Local extraction records constant-2005 PPP WDI income, 1988-2006, 4,991-line HS0 harmonization, mirrored data, and 141 nonmicrostate baseline regressions.",
        ),
    ]


def availability_diagnostics() -> dict[str, Any]:
    out: dict[str, Any] = {
        "availability_cache_exists": AVAILABILITY.exists(),
        "path": rel(AVAILABILITY),
    }
    if not AVAILABILITY.exists():
        return out
    df = pd.read_csv(AVAILABILITY)
    out["rows"] = int(len(df))
    out["columns"] = list(df.columns)
    if {"reporterCode", "reporterISO", "period"}.issubset(df.columns):
        hs = df[df.get("classificationSearchCode", "HS").astype(str).eq("HS")].copy()
        hs["period"] = pd.to_numeric(hs["period"], errors="coerce")
        hs = hs[(hs["period"] >= 2000) & (hs["period"] <= 2024)]
        by_reporter = (
            hs.dropna(subset=["period"])
            .groupby(["reporterCode", "reporterISO", "reporterDesc"], dropna=False)["period"]
            .nunique()
            .reset_index(name="available_hs_years_2000_2024")
        )
        out["reporters_in_cache_2000_2024"] = int(by_reporter["reporterCode"].nunique())
        out["reporters_with_19plus_hs_years_2000_2024"] = int((by_reporter["available_hs_years_2000_2024"] >= 19).sum())
        out["min_years_among_19plus"] = int(by_reporter.loc[by_reporter["available_hs_years_2000_2024"] >= 19, "available_hs_years_2000_2024"].min())
        out["max_years"] = int(by_reporter["available_hs_years_2000_2024"].max())
    return out


def write_records(path: Path, records: list[Any]) -> None:
    rows = [asdict(record) for record in records]
    pd.DataFrame(rows).to_csv(path, index=False)


def report_markdown(artifacts: list[Artifact], availability: dict[str, Any]) -> str:
    missing_original_artifacts = [
        a
        for a in artifacts
        if a.track in {"cadot_original_1988_2006", "cadot_original_countries_extended"} and not a.exists
    ]
    prior_reviews_present = [a for a in artifacts if a.track == "prior review" and a.exists]
    blocker = DATA_ACCESS_BLOCKER.exists()
    workinprogress_present = any(
        a.exists for a in artifacts if a.role == "website work-in-progress page"
    )
    broad_three_metric_present = any(a.track == "cadot_broad_156" and a.role == "modern three-metric concentration panel" and a.exists for a in artifacts)
    broad_ppp_present = any(a.track == "cadot_broad_156" and a.role == "broad PPP regression summary" and a.exists for a in artifacts)

    lines: list[str] = [
        "# Cadot Replication Technical Audit",
        "",
        f"Generated: {now_utc()}",
        "",
        "## 1. Executive Verdict",
        "",
        "**Verdict: do not claim a best-possible Cadot replication from this checkout yet.**",
        "",
        "We agree with Cadot only at the level of the research target: the relevant test is a development-stage export-diversification hump using HS6 product concentration, active lines, oil controls, microstate checks, and constant-PPP income. The current checkout now contains a modern broad-156 concentration bundle, but it still does not contain a literal 1988-2006 Cadot-original replication track.",
        "",
        f"Modern broad-156 three-metric bundle present: {'yes' if broad_three_metric_present else 'no'}. Broad-156 PPP hump regressions present: {'yes' if broad_ppp_present else 'no'}. The original Cadot-period replication is not implemented as a completed sample track in this checkout.",
        "",
        f"`workinprogress.html` status: {'present' if workinprogress_present else 'not present in the checked locations'}. Therefore \"Behind the Hump\" cannot be treated as accurate and updated from this checkout alone; it needs regeneration from saved panels plus a fresh validation pass.",
        "",
        "## 2. What Cadot Did",
        "",
        "- Published article: Cadot, Carrere, and Strauss-Kahn, *Review of Economics and Statistics*, 2011, 93(2), 590-605.",
        "- Public metadata and the local paper extraction report 156 countries, 19 years, HS6 exports, and 4,991 harmonized product lines.",
        "- The paper studies country-year export concentration over development using Gini, Herfindahl-Hirschman, Theil, and the number of active HS6 export lines.",
        "- Headline income is GDP per capita PPP in constant 2005 international dollars from WDI; current-dollar income is not Cadot-comparable.",
        "- The local extraction says the baseline regressions exclude microstates and use 2,497 observations for 141 countries over 1988-2006, with an average of 18 observations per country.",
        "- The annex says Cadot harmonized HS1 and HS2 back to HS0, added missing inactive lines as zeros over a 4,991-product universe, and used mirrored trade data to reduce exporter-reporting error.",
        "- The headline result is a diversification hump: concentration falls and active product counts rise with income, then concentration rises again mostly through the extensive margin.",
        "- Cadot reports pooled, within, and between estimates. Local notes put pooled/within/between turning points mostly around PPP $21,000-$29,000, with a common shorthand benchmark around PPP $25,000.",
        "- Cadot treats HS Section 16 as a measurement concern and reports robustness after coarser aggregation or exclusion; we need the same sensitivity before making a paper-level claim.",
        "",
        "Measure definitions for our replication report:",
        "",
        "- Product Gini: inequality of export values across HS6 products within a reporter-year after excluding HS6 `999999`; higher values mean exports are more concentrated in fewer products.",
        "- Herfindahl-Hirschman index: `HHI_{ct} = sum_p s_{cpt}^2`, where `s_{cpt}` is product `p`'s share of reporter `c` exports in year `t`; higher values mean more concentration.",
        "- Theil: `T_{ct} = (1/N) sum_p (x_{cpt}/mu_{ct}) log(x_{cpt}/mu_{ct})` on the fixed product universe with inactive products coded zero where required by the Cadot design; higher values mean more concentration.",
        "- Active line count: count of HS6 products with positive exports in reporter-year `ct`; higher values mean a broader extensive margin.",
        "",
        "## 3. Replication Package Status",
        "",
        "No public replication package was located in the targeted search as of June 16, 2026. This is a source-audit finding, not proof that no private package exists.",
        "",
        "Searched sources included EconPapers/RePEc, IDEAS/RePEc, World Bank OKR, MIT Press Direct, SSRN, HAL/CERDI/CEPR/CEPREMAP working-paper trails, and targeted web queries for `REST_a_00078`, `Cadot Carrere Strauss-Kahn replication package`, `data`, `Stata`, `supplementary`, and `Dataverse`.",
        "",
        "The World Bank OKR metadata has a `Link to Data Set` heading, but the inspected page has no visible dataset URL. MIT Press/RePEc/SSRN/IDEAS expose article or working-paper metadata, not code/data files.",
        "",
        "See `cadot_replication_source_audit.csv` for the source-by-source trail.",
        "",
        "## 4. Our Current State",
        "",
        f"Original Cadot-track artifacts missing in this checkout: {len(missing_original_artifacts)} expected original/extended files/directories are absent.",
        f"Prior local review docs present: {len(prior_reviews_present)}.",
        f"Data access blocker present: {'yes' if blocker else 'no'}.",
        "",
        "The codebase already contains important pieces:",
        "",
        "- `scripts/trade_concentration_pipeline.py` defines `cadot_broad_156` as a research-only broad sample with 2000-2024, at least 19 HS final-data years, and an expected reporter count of 156.",
        "- `results/samples/cadot_broad_156/three_metric_tables/` now contains a modern broad-156 Gini/Theil/HHI concentration bundle and validation checks.",
        "- `scripts/run_ppp_hump_regressions.py` uses World Bank `NY.GDP.PCAP.PP.KD`, labeled GDP per capita PPP in constant 2021 international dollars. This is directionally correct for constant PPP, but its WDI vintage/base differs from Cadot's constant 2005 PPP.",
        "- `tests/test_cadot_broad_sample.py` checks the broad sample defaults and exact-156 failure behavior under mocked availability.",
        "- Prior referee notes report successful earlier broad and constant-PPP runs; current broad three-metric artifacts are present, while literal original-period outputs remain absent.",
        "",
        "Blocking issues in this checkout:",
        "",
        "- The exact Cadot 156-country list is not isolated in current public metadata or local extraction; the paper's regression sample uses 141 nonmicrostate countries after exclusions.",
        "- Original-period mirror-import reconstruction is not implemented as a completed runnable track.",
        f"- Broad-156 PPP hump regressions are {'present' if broad_ppp_present else 'not yet present'} under `results/samples/cadot_broad_156/cadot_broad_ppp_hump_regression_tables/`.",
        "",
        "## 5. Result Comparison",
        "",
        "| Outcome | Cadot benchmark | Current checkout status | Agree/disagree label |",
        "|---|---|---|---|",
        "| Export product concentration | Hump in concentration with income; reconcentration after turning point | Modern broad concentration panel exists; original-period regression panel absent | Modern extension testable, literal replication not yet |",
        "| Active HS6 line count | Inverted concentration pattern: active lines rise, then flatten/fall | Modern active-count outcome exists; original-period active-line panel absent | Modern extension testable, literal replication not yet |",
        "| Theil decomposition | Extensive margin is the main channel | Modern fixed-universe product Theil exists; original Cadot HS0/4,991 universe absent | Partial modern mechanism evidence only |",
        "| Import concentration | Not Cadot's headline; useful modern extension | Existing repo has import runners, but no current Cadot result artifact | Extension only |",
        "| Partner concentration | Not Cadot's product-diversification object | Existing partner rules are separate and may include `999999` when only summing to partner totals | Not a Cadot replication |",
        f"| Modern broad 156 | Not Cadot period; 2000-2024 modern credibility sample | Three-metric bundle {'present' if broad_three_metric_present else 'absent'}; PPP regressions {'present' if broad_ppp_present else 'absent'} | Modern diagnostic, not literal replication |",
        "",
        "The most defensible current statement is: the modern broad-156 concentration bundle is now present and validated, but literal Cadot-original replication remains undone until the country list, mirror data, and HS0 fixed universe are recovered/reconstructed.",
        "",
        "## 6. Country Coverage",
        "",
        "Required tracks:",
        "",
        "- `cadot_original_1988_2006`: closest original-period track. Not currently present as generated data or a completed pipeline choice. Needs exact Cadot country list or a transparent reconstructed list from 1988-2006 HS/mirror coverage.",
        "- `cadot_original_countries_extended`: same country universe extended to latest final-data availability. Not currently present. Feasible after the original list is recovered/reconstructed and HS revision breaks are documented.",
        "- `cadot_broad_156_modern`: present in code under the current sample name `cadot_broad_156` as a modern 2000-2024 design. The modern concentration bundle is present; PPP regression outputs depend on the broad PPP runner.",
        "",
        "Cadot-period all-country feasibility: yes in principle, but not proved here. The public paper does not expose a ready 156-country list in inspected metadata. The local extraction gives the nonmicrostate regression sample count of 141 countries, not the full pre-exclusion 156 list.",
        "",
        "Extended-period feasibility: yes after original-country recovery, but it will necessarily be an unbalanced panel because Comtrade final-data availability, country codes, state succession, and WDI coverage differ over 1988-2024/2025.",
        "",
        "Current availability-cache diagnostic:",
        "",
        "```json",
        json.dumps(availability, indent=2, sort_keys=True),
        "```",
        "",
        "Interpretation: the cached public availability file alone yields 158 reporters with at least 19 HS years in 2000-2024. The implemented `cadot_broad_156` selector is stricter because it also applies reporter-reference filters for active non-group reporters, valid ISO3, and non-expired metadata; prior tests require that final selector to fail unless it returns exactly 156.",
        "",
        "## 7. Rebuild Implementation Plan",
        "",
        "Use bounded stages; do not run all heavy work at once.",
        "",
        "1. Recover or reconstruct the Cadot country list.",
        "   - Search the paper appendix, working papers, author pages, and any table footnotes for the full 156.",
        "   - If unavailable, reconstruct from Comtrade mirrored-import HS6 coverage in 1988-2006 and write a discrepancy table against the paper's counts.",
        "2. Implement `cadot_original_1988_2006` only after the country-list rule is explicit.",
        "   - Period exactly 1988-2006.",
        "   - Harmonize HS1/HS2 to HS0 or document why current HS final-data extraction cannot reproduce that vintage.",
        "   - Exclude `999999` from product-dependent measures before aggregation and add a labeled sensitivity if Cadot's residual-code handling remains unknown.",
        "3. Implement `cadot_original_countries_extended` using the same country universe.",
        "   - Do not impute absent years.",
        "   - Report HS revision breaks and country-year coverage.",
        "4. Keep `cadot_broad_156_modern` as a 2000-2024 sensitivity.",
        "   - Fail loudly unless the official cached availability snapshot selects exactly 156 reporters.",
        "5. Build saved analytic panels before regressions.",
        "   - Enforce unique reporter-year keys.",
        "   - Save row-count attrition at each filter, merge, and complete-case step.",
        "6. Estimate pooled, country-FE/within, between, and sensitivity models.",
        "   - Headline income: constant PPP GDP per capita, not current USD.",
        "   - Report turning points in the WDI base/vintage used and support checks against min/max and p05-p95.",
        "7. Rerun the website explainer only from current saved panels.",
        "   - Label it as research/audit output unless it uses website-default `rd2_countries`.",
        "",
        "CPU/memory-safe command pattern:",
        "",
        "```bash",
        "export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1",
        "/usr/bin/nice -n 10 python3 scripts/trade_concentration_pipeline.py --country-sample cadot_broad_156 --stage process --exercise 1 --chunk-rows 250000 --memory-limit-gb 12",
        "/usr/bin/nice -n 10 python3 scripts/trade_concentration_pipeline.py --country-sample cadot_broad_156 --stage process --exercise 2 --chunk-rows 250000 --memory-limit-gb 12",
        "/usr/bin/nice -n 10 python3 scripts/run_ppp_hump_regressions.py --country-sample cadot_broad_156",
        "```",
        "",
        "For original Cadot tracks, do not start the expensive process stage until the country-list and mirror-data rules are explicit.",
        "",
        "## 8. Bottom-Line Assessment",
        "",
        "We have not yet replicated Cadot in the best possible way in this checkout. We have current modern broad-156 concentration results, but not the original 1988-2006 mirror-data reconstruction, not the exact Cadot 156-country list, and not the exact Cadot HS0 4,991-line universe.",
        "",
        "\"Behind the Hump\" should be treated as not currently certified. It can become accurate after regenerating from current constant-PPP panels, labeling modern versus original-period tracks, and passing an adversarial review.",
        "",
        "Before making a paper-level claim, the project needs: exact or transparently reconstructed Cadot country coverage, 1988-2006 mirror/Harmonized-System handling, saved concentration and active-line panels, complete attrition diagnostics, constant-PPP regressions, Section 16 robustness, and independent re-estimation from saved panels.",
    ]
    return "\n".join(lines) + "\n"


def adversarial_review_markdown(availability: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Adversarial Econometrics Review: Cadot Technical Audit",
            "",
            f"Generated: {now_utc()}",
            "",
            "This was a local adversarial review, not an independent fresh-agent pass. Subagent delegation was not explicitly requested in the current user instruction.",
            "",
            "## 1. Executive verdict",
            "",
            "**Do not trust yet.**",
            "",
            "- The audit report is trustworthy as a file-state and source-search inventory, and the modern broad-156 outputs can be checked from current artifacts.",
            "- Modern broad-156 concentration and PPP regression artifacts are present when generated, but they are not a literal Cadot 1988-2006 replication.",
            "- Prior review notes are secondary; current manifests and validation tables should be the source of truth.",
            "- The original Cadot country list and mirror-data construction are unresolved.",
            "- Constant PPP is correctly identified as required, but the available runner uses current WDI constant-2021 PPP, not Cadot's constant-2005 PPP vintage.",
            "",
            "## 2. Highest-risk findings",
            "",
            "Severity: High. Literal original-period generated panels are missing.",
            "Why it matters: modern broad coefficients, turning points, attrition, and country coverage can be checked, but they do not answer whether the 1988-2006 Cadot paper is replicated.",
            "Fix: implement or recover `cadot_original_1988_2006` panels, then rerun duplicate-key, attrition, and independent regression checks.",
            "",
            "Severity: High. Original Cadot sample is not recovered.",
            "Why it matters: a broad modern 156-country sample is not the same as Cadot's 1988-2006 mirror-data country universe.",
            "Fix: recover the 156 list from appendix/author materials or reconstruct it from transparent Comtrade coverage rules and publish a mismatch table.",
            "",
            "Severity: Medium. PPP base-year drift is unavoidable with current WDI.",
            "Why it matters: turning-point dollar values are not directly comparable across constant-2005 and constant-2021 international dollars.",
            "Fix: label the WDI vintage/base and, if possible, convert benchmark discussion using a documented PPP deflator bridge.",
            "",
            "Severity: Medium. Product-code harmonization is not Cadot-equivalent yet.",
            "Why it matters: Cadot harmonized HS1/HS2 to HS0 and worked on 4,991 fixed lines. Current final-data HS6 extraction can change active-line counts and Theil decomposition.",
            "Fix: implement HS0 fixed-universe reconstruction or state that the analysis is a modern extension, not a literal replication.",
            "",
            "## 3. Data lineage and sample audit",
            "",
            "Current lineage has complete modern broad-156 concentration outputs when `results/samples/cadot_broad_156/three_metric_tables/` is present, plus blocked original-track status artifacts. The current `cadot_broad_156_public_availability.csv` diagnostic is:",
            "",
            "```json",
            json.dumps(availability, indent=2, sort_keys=True),
            "```",
            "",
            "Expected final units are reporter-year for regression panels and reporter-year-product for measure construction. Modern broad reporter-year panels can be audited from current outputs; literal original-period reporter-year-product panels are not present.",
            "",
            "## 4. Merge/join audit",
            "",
            "Expected joins are reporter metadata to Comtrade availability, reporter/ISO3 to WDI controls, and country-year outcomes to controls. Current broad runner code contains uniqueness checks and attrition tables; original-period match rates and unmatched examples are not available because that track is blocked.",
            "",
            "## 5. Variable construction audit",
            "",
            "Headline income should be `NY.GDP.PCAP.PP.KD`, constant PPP GDP per capita. Product-dependent measures must exclude HS6 `999999` before aggregation. Cadot-equivalent Theil requires a fixed product universe with inactive lines represented as zeros.",
            "",
            "## 6. Specification audit",
            "",
            "Required Cadot-comparable model form:",
            "",
            "`Y_ct = alpha + beta_1 GDPpcPPP_ct + beta_2 GDPpcPPP_ct^2 + gamma oilshare_ct + delta_t + epsilon_ct`",
            "",
            "with pooled, country fixed-effect/within, and between variants. Clustered or robust inference should be explicit, and turning points should be reported as `-beta_1 / (2 beta_2)` with support checks.",
            "",
            "## 7. Inference and identification audit",
            "",
            "The exercise is descriptive, not causal. Country fixed effects identify within-country income changes and can differ materially from pooled development-stage differences. Cluster counts, cluster-size distribution, serial correlation, and high-income leverage must be reported from the saved analytic panel.",
            "",
            "## 8. Replication checklist",
            "",
            "- Keep current broad artifacts regenerated from scripts; implement or reconstruct the original-period sample artifacts before making a literal Cadot claim.",
            "- Verify no duplicate reporter-year keys and no duplicate ISO3 mappings.",
            "- Verify no HS6 `999999` in product-dependent panels.",
            "- Re-estimate one pooled and one within model directly from the saved panel.",
            "- Report complete attrition from selected countries to analytic rows/clusters.",
            "- Run Section 16 and microstate robustness.",
            "",
            "## 9. Minimal patch plan",
            "",
            "- Add original Cadot country-list recovery/reconstruction code before exposing new pipeline choices.",
            "- Add a sample manifest that stores country-list provenance, HS harmonization, PPP indicator/base, residual-code rule, and mirror/direct data rule.",
            "- Add regression-panel validation outputs and independent re-estimation scripts.",
            "",
            "## 10. Questions for the researcher",
            "",
            "- Is a current Comtrade subscription key available for original-period HS6 mirror-data reconstruction?",
            "- Should the paper-level replication prioritize literal Cadot HS0 harmonization, or is a modern HS final-data extension acceptable if clearly labeled?",
        ]
    ) + "\n"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    artifacts = expected_artifacts()
    sources = source_records()
    availability = availability_diagnostics()

    write_records(OUT_DIR / "cadot_replication_artifact_inventory.csv", artifacts)
    write_records(OUT_DIR / "cadot_replication_source_audit.csv", sources)

    manifest = {
        "created_at_utc": now_utc(),
        "report": rel(OUT_DIR / "cadot_replication_technical_audit.md"),
        "adversarial_review": rel(OUT_DIR / "cadot_replication_audit_adversarial_review.md"),
        "artifact_inventory": rel(OUT_DIR / "cadot_replication_artifact_inventory.csv"),
        "source_audit": rel(OUT_DIR / "cadot_replication_source_audit.csv"),
        "availability_diagnostics": availability,
        "heavy_rebuild_run": False,
        "reason_heavy_rebuild_not_run": "Generated Cadot original tracks require explicit country-list/mirror-data rules and Comtrade HS6 bulk/final data access.",
    }
    (OUT_DIR / "cadot_replication_rebuild_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    (OUT_DIR / "cadot_replication_technical_audit.md").write_text(report_markdown(artifacts, availability))
    (OUT_DIR / "cadot_replication_audit_adversarial_review.md").write_text(adversarial_review_markdown(availability))

    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
