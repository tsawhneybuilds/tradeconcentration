#!/usr/bin/env python3
"""
Finalize the Exercise 3 HS/BEC research-bin mapping.

This script starts from the official-BEC/audited candidate mapping produced by
`trade_concentration_pipeline.py`, adds official Comtrade HS descriptions, and
applies conservative economic rules for the remaining ambiguous rows.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests


ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data" / "raw"
CLASSIFICATION_RAW = DATA_RAW / "classifications"
DATA_PROCESSED = ROOT / "data" / "processed"
RESULTS = ROOT / "results"
EX03_TABLES = RESULTS / "exercise_03_tables"

DEFAULT_CANDIDATE = DATA_PROCESSED / "exercise_03_bec5_mapping_candidate.csv"
INPUT_BACKUP = DATA_PROCESSED / "exercise_03_bec5_mapping_pre_description_rules_candidate.csv"
OUTPUT_CANDIDATE = DATA_PROCESSED / "exercise_03_bec5_mapping_desc_resolved_candidate.csv"
DECISION_MEMO = RESULTS / "exercise_03_bec5_mapping_decisions.md"

HS_CLASSES = ["H0", "H1", "H2", "H3", "H4", "H5", "H6"]
HS_REFERENCE_URL = "https://comtradeapi.un.org/files/v1/app/reference/{code}.json"


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_code(value: object, digits: int = 6) -> str:
    text = "" if value is None else str(value).strip()
    text = re.sub(r"\.0$", "", text)
    match = re.search(r"\d+", text)
    if not match:
        return ""
    return match.group(0).zfill(digits)


def clean_desc(text: object) -> str:
    out = "" if text is None else str(text).strip()
    out = re.sub(r"^\s*\d+\s*-\s*", "", out)
    out = re.sub(r"^\s*-+\s*", "", out)
    out = re.sub(r"\s+", " ", out)
    return out.strip()


def ensure_hs_references() -> None:
    CLASSIFICATION_RAW.mkdir(parents=True, exist_ok=True)
    for code in HS_CLASSES:
        path = CLASSIFICATION_RAW / f"{code}.json"
        if path.exists() and path.stat().st_size > 0:
            continue
        url = HS_REFERENCE_URL.format(code=code)
        response = requests.get(url, timeout=(20, 120))
        response.raise_for_status()
        path.write_bytes(response.content)


def load_hs_descriptions() -> pd.DataFrame:
    ensure_hs_references()
    rows = []
    for code in HS_CLASSES:
        payload = json.loads((CLASSIFICATION_RAW / f"{code}.json").read_text(encoding="utf-8"))
        ref_rows = payload.get("results", payload) if isinstance(payload, dict) else payload
        for row in ref_rows:
            cmd_code = str(row.get("id", "")).strip()
            if not re.fullmatch(r"\d{6}", cmd_code):
                continue
            rows.append(
                {
                    "classification_code": code,
                    "cmd_code": cmd_code,
                    "hs_desc_official": clean_desc(row.get("text")),
                }
            )
    return pd.DataFrame(rows).drop_duplicates(subset=["classification_code", "cmd_code"])


def alternative_bins(mapping_issue: str) -> set[str]:
    text = str(mapping_issue)
    bins = set()
    if "Intermediate Consumption" in text:
        bins.add("intermediates")
    if "Gross Fixed Capital Formation" in text:
        bins.add("capital_goods")
    if "Final Consumption" in text:
        bins.add("final_consumption")
    return bins


def choose_description_bin(row: pd.Series) -> tuple[str, str]:
    """Return (bin, rule). Empty bin means no main-spec recode."""
    current = str(row.get("exercise_03_bin", ""))
    if current != "unmapped_or_ambiguous":
        return "", ""

    cmd_code = normalize_code(row.get("cmd_code"))
    desc = str(row.get("hs_desc_official", "")).lower()
    issue = str(row.get("audit_issue_type", ""))
    allowed = alternative_bins(row.get("mapping_issue", ""))

    if cmd_code == "999999" or "not specified according to kind" in desc:
        return "", "keep_unknown_999999_excluded"

    if issue == "energy_treatment_unclear":
        if "fuel" in desc or cmd_code.startswith("2710") or cmd_code in {"360610", "382600"}:
            return "energy", "narrow_energy_fuel_or_power_product"
        return "", "keep_energy_derivative_or_feedstock_excluded"

    if issue == "cross_version_inconsistency":
        return "", "keep_cross_version_inconsistency_excluded"

    if issue != "ambiguous_official_mapping":
        return "", "keep_manual_review_excluded"

    final_patterns = [
        r"telephones? for cellular",
        r"telephone sets",
        r"videophones?",
        r"video games?",
        r"video game consoles?",
        r"television receivers?",
        r"television cameras?",
        r"colour television",
        r"headphones?",
        r"earphones?",
        r"loudspeakers?",
        r"sound reproducing",
        r"refrigerators?",
        r"freezers?",
        r"washing machines?",
        r"orthopaedic|fracture appliances?",
        r"garments?|clothing|babies",
        r"footwear",
        r"toys?|games?",
    ]
    if "final_consumption" in allowed and any(re.search(pattern, desc) for pattern in final_patterns):
        return "final_consumption", "official_hs_description_clear_final_consumption"

    intermediate_patterns = [
        r"\bparts?\b",
        r"\baccessories\b",
        r"\bcomponents?\b",
        r"\bmodules?\b",
        r"for use with",
        r"of the machines?",
        r"of machinery",
        r"of heading",
        r"inductors?",
        r"indicator panels?",
    ]
    if "intermediates" in allowed and any(re.search(pattern, desc) for pattern in intermediate_patterns):
        return "intermediates", "official_hs_description_clear_part_component_or_accessory"

    capital_patterns = [
        r"machines? for the reception, conversion and transmission",
        r"switching and routing apparatus",
        r"base stations?",
        r"packing or wrapping machinery",
        r"machinery for filling|machinery for capsuling|machinery for aerating",
        r"measuring or checking",
        r"instruments?, appliances? and machines?",
        r"printing, copying or facsimile",
        r"telephonic or telegraphic switching apparatus",
        r"static converters?",
        r"automatic data processing machines? and units?",
        r"input or output units?",
        r"other units of automatic data processing",
    ]
    if "capital_goods" in allowed and any(re.search(pattern, desc) for pattern in capital_patterns):
        return "capital_goods", "official_hs_description_clear_capital_equipment"

    return "", "keep_cross_bin_ambiguous_excluded"


def apply_main_rules(candidate: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    out = candidate.drop(
        columns=[
            "original_exercise_03_bin_before_description_rules",
            "description_rule_bin",
            "description_rule",
            "research_bin_changed_by_description_rule",
        ],
        errors="ignore",
    ).copy()
    out["original_exercise_03_bin_before_description_rules"] = out["exercise_03_bin"]
    decisions = out.apply(choose_description_bin, axis=1, result_type="expand")
    decisions.columns = ["description_rule_bin", "description_rule"]
    out = pd.concat([out, decisions], axis=1)

    changed = out["description_rule_bin"].ne("")
    out.loc[changed, "exercise_03_bin"] = out.loc[changed, "description_rule_bin"]
    out.loc[changed, "research_mapping_status"] = "resolved_to_research_bin_by_description_rule"
    out.loc[changed, "research_bin_changed_by_description_rule"] = 1
    out.loc[~changed, "research_bin_changed_by_description_rule"] = 0
    out.loc[changed, "research_bin_rule"] = out.loc[changed, "description_rule"]

    changes = out[out["research_bin_changed_by_description_rule"].eq(1)].copy()
    return out, changes


def apply_sensitivity_rules(main: pd.DataFrame) -> dict[str, pd.DataFrame]:
    sensitivities = {}

    capital = main.copy()
    mask = (
        capital["exercise_03_bin"].eq("unmapped_or_ambiguous")
        & capital["mapping_issue"].map(lambda text: "Gross Fixed Capital Formation" in str(text))
        & capital["audit_issue_type"].eq("ambiguous_official_mapping")
    )
    capital.loc[mask, "exercise_03_bin"] = "capital_goods"
    capital.loc[mask, "research_mapping_status"] = "sensitivity_assigned_to_capital_goods"
    capital.loc[mask, "research_bin_rule"] = "sensitivity_A_all_remaining_plausible_capital"
    sensitivities["capital_bound"] = capital

    intermediate = main.copy()
    mask = (
        intermediate["exercise_03_bin"].eq("unmapped_or_ambiguous")
        & intermediate["mapping_issue"].map(lambda text: "Intermediate Consumption" in str(text))
        & intermediate["audit_issue_type"].eq("ambiguous_official_mapping")
    )
    intermediate.loc[mask, "exercise_03_bin"] = "intermediates"
    intermediate.loc[mask, "research_mapping_status"] = "sensitivity_assigned_to_intermediates"
    intermediate.loc[mask, "research_bin_rule"] = "sensitivity_B_all_remaining_plausible_intermediates"
    sensitivities["intermediate_bound"] = intermediate

    energy = main.copy()
    mask = (
        energy["exercise_03_bin"].eq("unmapped_or_ambiguous")
        & (
            energy["audit_issue_type"].eq("energy_treatment_unclear")
            | energy["cmd_code"].astype(str).str.zfill(6).str.startswith("27")
        )
    )
    energy.loc[mask, "exercise_03_bin"] = "energy"
    energy.loc[mask, "research_mapping_status"] = "sensitivity_assigned_to_energy"
    energy.loc[mask, "research_bin_rule"] = "sensitivity_C_broad_energy_hs27_like_residuals"
    sensitivities["broad_energy_bound"] = energy

    return sensitivities


def write_decision_memo(main: pd.DataFrame, changes: pd.DataFrame, sensitivities: dict[str, pd.DataFrame]) -> None:
    value_share_path = EX03_TABLES / "remaining_bec5_ambiguity_value_share_by_bin.csv"
    value_impact_path = EX03_TABLES / "bec5_mapping_description_resolved_value_impact_summary.csv"
    final_value_share_path = EX03_TABLES / "bec5_mapping_description_resolved_final_value_share_estimate.csv"
    value_share = pd.read_csv(value_share_path) if value_share_path.exists() else pd.DataFrame()
    value_impact = pd.read_csv(value_impact_path) if value_impact_path.exists() else pd.DataFrame()
    final_value_share = pd.read_csv(final_value_share_path) if final_value_share_path.exists() else pd.DataFrame()
    bin_counts = main["exercise_03_bin"].value_counts().rename_axis("bin").reset_index(name="mapping_rows")
    change_counts = (
        changes.groupby(["description_rule", "exercise_03_bin"], as_index=False).size().rename(columns={"size": "rows"})
        if not changes.empty
        else pd.DataFrame(columns=["description_rule", "exercise_03_bin", "rows"])
    )
    sensitivity_counts = []
    for name, frame in sensitivities.items():
        counts = frame["exercise_03_bin"].value_counts().to_dict()
        counts["sensitivity"] = name
        sensitivity_counts.append(counts)
    sensitivity_counts = pd.DataFrame(sensitivity_counts).fillna(0)

    memo = f"""# Exercise 3 BEC5 Research-Bin Mapping Decisions

Generated: {now_utc()}

This memo documents the mapping decisions used to turn official HS-to-BEC and BEC5 end-use information into the Exercise 3 research bins. It is descriptive and does not update `exercises.md`.

## Principle

The mapping is official where the official BEC5 end-use is decisive. When the official BEC alternatives disagree, the main specification only recodes a row if the official HS description gives a clear economic use. Remaining ambiguous rows stay excluded and are reported.

## Main-Spec Rules

- Keep HS `999999` excluded. The official description is “Commodities not specified according to kind,” so assigning it to energy, capital goods, intermediates, or final consumption would create false precision.
- Resolve same-bin official ambiguity. If all official BEC alternatives imply the same research bin, use that bin.
- Use official HS descriptions to resolve clear remaining cross-bin cases:
  - parts, accessories, components, modules, and “for use with” goods -> `intermediates`
  - production/office/network machinery, measuring/checking instruments, switching/routing equipment, static converters, and similar durable equipment -> `capital_goods`
  - mobile phones, video games/consoles, televisions, headphones/loudspeakers, household refrigerators/washing machines, apparel/footwear, toys, and clear patient/consumer appliances -> `final_consumption`
- Energy is narrow in the main specification:
  - fuel/power products and clear petroleum-oil/fuel rows -> `energy`
  - petrochemical feedstocks, coal-tar/bituminous derivatives, waxes, petroleum coke, and ethanol remain excluded unless a broader energy sensitivity is used.
- Cross-version inconsistencies and generic “Other” rows stay excluded unless the official description is specific enough for one of the rules above.

## Current Value Coverage Before These Description Rules

{value_share.to_markdown(index=False) if not value_share.empty else "Value-share table not available."}

## Final Main Mapping Row Counts

{bin_counts.to_markdown(index=False)}

## Rows Reclassified By Description Rule

{change_counts.to_markdown(index=False) if not change_counts.empty else "No rows were reclassified by description rules."}

## Import-Value Impact Of Description Rules

{value_impact.to_markdown(index=False) if not value_impact.empty else "Value-impact table not available. Re-run the value-share scan to populate import-value impact."}

## Estimated Value Coverage After Description Rules

{final_value_share.to_markdown(index=False) if not final_value_share.empty else "Final value-share estimate not available."}

## Sensitivity Mappings

Three robustness mappings were written:

- `capital_bound`: assign remaining official cross-bin rows with a possible capital-goods alternative to `capital_goods`.
- `intermediate_bound`: assign remaining official cross-bin rows with a possible intermediate alternative to `intermediates`.
- `broad_energy_bound`: assign remaining HS27-like/energy-treatment residuals to `energy`.

{sensitivity_counts.to_markdown(index=False)}

## Files

- Main candidate: `data/processed/exercise_03_bec5_mapping_candidate.csv`
- Main candidate copy: `data/processed/exercise_03_bec5_mapping_desc_resolved_candidate.csv`
- Change log: `results/exercise_03_tables/bec5_mapping_description_resolved_changes.csv`
- Sensitivities: `data/processed/exercise_03_bec5_mapping_sensitivity_*.csv`

## Suggested Write-Up

The main specification uses official HS-to-BEC correspondences and official BEC5 end-use labels. Ambiguous official mappings are resolved only when either all alternatives imply the same research bin or the official HS description clearly identifies the product as a component/intermediate, durable capital equipment, final consumption good, or narrow energy product. Remaining ambiguous products are excluded from the main bin comparison and reported separately; robustness checks reassign them under capital-goods, intermediate-input, and broad-energy bounds.
"""
    DECISION_MEMO.write_text(memo, encoding="utf-8")


def main() -> int:
    source_candidate = INPUT_BACKUP if INPUT_BACKUP.exists() else DEFAULT_CANDIDATE
    if not source_candidate.exists():
        raise FileNotFoundError(source_candidate)
    candidate = pd.read_csv(source_candidate, dtype=str).fillna("")
    candidate["classification_code"] = candidate["classification_code"].astype(str).str.strip().str.upper()
    candidate["cmd_code"] = candidate["cmd_code"].map(normalize_code)

    if not INPUT_BACKUP.exists() and source_candidate == DEFAULT_CANDIDATE:
        candidate.to_csv(INPUT_BACKUP, index=False)

    desc = load_hs_descriptions()
    candidate = candidate.drop(columns=["hs_desc_official"], errors="ignore").merge(
        desc, on=["classification_code", "cmd_code"], how="left"
    )
    candidate["hs_desc_official"] = candidate["hs_desc_official"].fillna("")

    main_candidate, changes = apply_main_rules(candidate)
    sensitivities = apply_sensitivity_rules(main_candidate)

    OUTPUT_CANDIDATE.parent.mkdir(parents=True, exist_ok=True)
    EX03_TABLES.mkdir(parents=True, exist_ok=True)
    main_candidate.to_csv(OUTPUT_CANDIDATE, index=False)
    main_candidate.to_csv(DEFAULT_CANDIDATE, index=False)
    changes.to_csv(EX03_TABLES / "bec5_mapping_description_resolved_changes.csv", index=False)
    summary = main_candidate.groupby(
        [
            "original_exercise_03_bin_before_description_rules",
            "exercise_03_bin",
            "description_rule",
        ],
        as_index=False,
    ).size()
    summary.to_csv(EX03_TABLES / "bec5_mapping_description_resolved_summary.csv", index=False)

    for name, frame in sensitivities.items():
        frame.to_csv(DATA_PROCESSED / f"exercise_03_bec5_mapping_sensitivity_{name}.csv", index=False)

    write_decision_memo(main_candidate, changes, sensitivities)
    print(f"Wrote main candidate: {DEFAULT_CANDIDATE}")
    print(f"Wrote decision memo: {DECISION_MEMO}")
    print(f"Rows reclassified by description rules: {len(changes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
