from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_cadot_hump_tribunal as cadot


def test_normalize_hs6_and_exclude_999999_before_product_aggregation() -> None:
    exports = pd.DataFrame(
        {
            "reporter_code": [1, 1, 1],
            "year": [2000, 2000, 2000],
            "cmd_code": ["999999", "840100", "270900"],
            "trade_value": [10_000.0, 20_000.0, 30_000.0],
        }
    )
    exports["cmd_code"] = cadot.normalize_hs6(exports["cmd_code"])
    exports = exports[~exports["cmd_code"].isin(cadot.EXCLUDED_HS6_CODES)].copy()
    exports["hs2"] = exports["cmd_code"].str[:2]
    exports["hs4_id"] = "HS4:" + exports["cmd_code"].str[:4]
    exports["section16"] = exports["hs2"].isin(cadot.SECTION_16_HS2)

    assert "999999" not in set(exports["cmd_code"])
    assert set(exports["cmd_code"]) == {"840100", "270900"}
    assert bool(exports.loc[exports["cmd_code"].eq("840100"), "section16"].iloc[0]) is True
    assert exports.loc[exports["cmd_code"].eq("270900"), "hs4_id"].iloc[0] == "HS4:2709"


def test_prody_leave_one_out_subtracts_focal_country() -> None:
    hs4 = pd.DataFrame(
        {
            "reporter_code": [1, 1, 2, 2, 3, 3],
            "year": [2000] * 6,
            "product_id": ["HS4:A", "HS4:B", "HS4:A", "HS4:B", "HS4:A", "HS4:B"],
            "trade_value_2024_usd": [80.0, 20.0, 10.0, 90.0, 40.0, 60.0],
        }
    )
    controls = pd.DataFrame(
        {
            "reporter_code": [1, 2, 3],
            "year": [2000, 2000, 2000],
            cadot.INCOME_LOG_COL: [1.0, 2.0, 4.0],
        }
    )
    prody = cadot.build_prody(hs4, controls)
    row = prody[(prody["reporter_code"].eq(1)) & (prody["product_id"].eq("HS4:A"))].iloc[0]

    assert math.isclose(row["prody_log_income_pc_loo"], 3.6)
    assert math.isclose(row["prody_log_gni_pc_loo"], 3.6)
    assert row["prody_exporter_count"] == 3


def test_positive_mismatch_means_country_is_above_product_prody() -> None:
    windows = pd.DataFrame(
        {
            "reporter_code": [1],
            "base_year": [2000],
            "product_id": ["HS4:A"],
            "base_log_income_pc": [10.0],
            "product_channel": ["dying_product"],
            "horizon": [5],
        }
    )
    prody = pd.DataFrame(
        {
            "reporter_code": [1],
            "year": [2000],
            "product_id": ["HS4:A"],
            "prody_log_income_pc_loo": [8.0],
            "prody_exporter_count": [3],
        }
    )
    out = cadot.attach_prody_to_windows(
        windows,
        prody,
        {"rich_side_log_threshold_used": 9.0},
    )

    assert out["mismatch_log_income_minus_prody"].iloc[0] == 2.0
    assert out["mismatch_log_gni_minus_prody"].iloc[0] == 2.0
    assert out["rich_side_ct"].iloc[0] == 1
    assert out["exit_next_window"].iloc[0] == 1
