from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_historical_partner_concentration import _append_role_record, build_flow_panel, build_wide_panel
from historical_partner_common import EXPECTED_ENTITY_SPANS, mpd_code_for_entity


def test_direction_and_partner_filters_are_assigned_correctly() -> None:
    records: list[dict[str, object]] = []
    valid_codes = {"FRA", "GBR", "USA"}
    entity_meta = {code: {"continent": "EUROP", "region": "WEST"} for code in valid_codes}
    _append_role_record(
        records,
        reporter="FRA",
        partner="GBR",
        flow="Exports",
        year=1900,
        flow_value=10.0,
        flow0_value=None,
        source_tf="TEST",
        bitariff=None,
        source_file="part.xlsx",
        part_label="part_1",
        valid_entity_codes=valid_codes,
        entity_metadata=entity_meta,
    )
    _append_role_record(
        records,
        reporter="GBR",
        partner="GBR",
        flow="Imports",
        year=1900,
        flow_value=5.0,
        flow0_value=None,
        source_tf="TEST",
        bitariff=None,
        source_file="part.xlsx",
        part_label="part_1",
        valid_entity_codes=valid_codes,
        entity_metadata=entity_meta,
    )
    _append_role_record(
        records,
        reporter="USA",
        partner="UNK",
        flow="Imports",
        year=1900,
        flow_value=7.0,
        flow0_value=None,
        source_tf="TEST",
        bitariff=None,
        source_file="part.xlsx",
        part_label="part_1",
        valid_entity_codes=valid_codes,
        entity_metadata=entity_meta,
    )
    frame = pd.DataFrame(records)
    assert frame.loc[0, "flow"] == "Exports"
    assert bool(frame.loc[0, "partner_included_main_panel"]) is True
    assert bool(frame.loc[1, "is_self_trade"]) is True
    assert bool(frame.loc[1, "partner_included_main_panel"]) is False
    assert bool(frame.loc[2, "partner_in_master_codebook"]) is False
    assert bool(frame.loc[2, "partner_included_main_panel"]) is False


def test_flow_panel_counts_positive_zero_and_missing_dyads() -> None:
    flows = pd.DataFrame(
        {
            "entity_id": ["FRA", "FRA", "FRA", "FRA", "FRA"],
            "entity_label": ["France"] * 5,
            "entity_boundary_note": ["note"] * 5,
            "flow": ["Exports"] * 5,
            "partner_id": ["GBR", "USA", "ESP", "PRT", "ITA"],
            "year": [1900] * 5,
            "FLOW": [10.0, 5.0, 0.0, np.nan, np.nan],
            "FLOW_0": [np.nan, np.nan, np.nan, 0.0, np.nan],
            "SOURCE_TF": ["TEST"] * 5,
            "source_family": ["Primary"] * 5,
            "BITARIFF": [np.nan] * 5,
            "source_file": ["part.xlsx"] * 5,
            "source_part": ["part_1"] * 5,
            "is_self_trade": [False] * 5,
            "partner_in_master_codebook": [True] * 5,
            "partner_included_main_panel": [True] * 5,
            "observed_positive": [True, True, False, False, False],
            "observed_zero": [False, False, True, False, False],
            "likely_zero": [False, False, False, True, False],
            "coded_zero": [False, False, True, True, False],
            "value_current_gbp": [10.0, 5.0, 0.0, np.nan, np.nan],
            "partner_continent": ["EUROP"] * 5,
            "partner_region": ["WEST"] * 5,
            "boundary_flag": ["standard"] * 5,
            "reporter_role": ["origin"] * 5,
        }
    )
    year_universe = {1900: {"FRA", "GBR", "USA", "ESP", "PRT", "ITA", "DEU"}}
    panel, _ = build_flow_panel(flows, year_universe)
    row = panel.iloc[0]
    assert row["active_partner_count"] == 2
    assert row["explicit_observed_zero_count"] == 1
    assert row["likely_zero_count"] == 1
    assert row["coded_zero_count"] == 2
    assert row["missing_unobserved_count"] == 2
    assert row["bilateral_sum_current_gbp"] == 15.0


def test_wide_panel_preserves_export_import_totals() -> None:
    long_panel = pd.DataFrame(
        {
            "entity_id": ["FRA", "FRA"],
            "entity_label": ["France", "France"],
            "entity_boundary_note": ["note", "note"],
            "flow": ["Exports", "Imports"],
            "year": [1900, 1900],
            "mpd_countrycode": ["FRA", "FRA"],
            "mpd_country": ["France", "France"],
            "mpd_region": ["Western Europe", "Western Europe"],
            "mpd_gdppc_2011_usd": [5000.0, 5000.0],
            "mpd_population_thousands": [1000.0, 1000.0],
            "gdppc_10k": [0.5, 0.5],
            "gdppc_10k_sq": [0.25, 0.25],
            "log_gdppc": [np.log(5000.0), np.log(5000.0)],
            "log_gdppc_sq": [np.log(5000.0) ** 2, np.log(5000.0) ** 2],
            "log_population": [np.log(1000.0), np.log(1000.0)],
            "bilateral_sum_current_gbp": [12.0, 7.0],
            "active_partner_count": [5, 6],
            "explicit_observed_zero_count": [0, 0],
            "likely_zero_count": [0, 0],
            "coded_zero_count": [0, 0],
            "missing_unobserved_count": [0, 0],
            "explicit_missing_observed_rows": [0, 0],
            "universe_partner_count": [5, 6],
            "quality_band": ["20+", "20+"],
            "headline_eligible": [True, True],
            "appendix_eligible": [True, True],
            "diagnostic_only": [False, False],
            "metrics_suppressed": [False, False],
            "dominant_source_tf": ["TEST", "TEST"],
            "dominant_source_family": ["DOTS", "DOTS"],
            "dominant_source_value_share": [1.0, 1.0],
            "dominant_source_partner_share": [1.0, 1.0],
            "partner_gini": [0.1, 0.2],
            "partner_gini_normalized": [0.12, 0.24],
            "partner_theil": [0.3, 0.4],
            "partner_theil_normalized": [0.35, 0.45],
            "partner_hhi": [0.22, 0.18],
            "partner_hhi_normalized": [0.28, 0.22],
            "effective_partner_count": [4.5, 5.5],
            "top1_partner_share": [0.4, 0.3],
            "top3_partner_share": [0.8, 0.7],
            "top5_partner_share": [1.0, 0.9],
            "top10_partner_share": [1.0, 1.0],
            "coded_zero_inclusive_partner_gini": [0.1, 0.2],
            "boundary_flag": ["standard", "standard"],
            "year_is_wwi": [False, False],
            "year_is_wwii": [False, False],
            "year_post_1948": [False, False],
            "year_post_1991": [False, False],
            "source_regime_flag": ["pre1948", "pre1948"],
        }
    )
    wide = build_wide_panel(long_panel)
    assert len(wide) == 1
    assert wide.loc[0, "bilateral_sum_exports_current_gbp"] == 12.0
    assert wide.loc[0, "bilateral_sum_imports_current_gbp"] == 7.0


def test_russia_ussr_mapping_and_span_constants_stay_separate() -> None:
    assert mpd_code_for_entity("USSR", 1991) == "SUN"
    assert mpd_code_for_entity("USSR", 1992) is None
    assert mpd_code_for_entity("RUS", 1991) is None
    assert mpd_code_for_entity("RUS", 1992) == "RUS"
    assert EXPECTED_ENTITY_SPANS["USSR"] == (1827, 1991)
    assert EXPECTED_ENTITY_SPANS["RUS"] == (1992, 2014)
