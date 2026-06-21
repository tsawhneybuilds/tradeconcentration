from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_import_demand_decomposition as demand
import run_production_core_old_cone as core


def test_import_demand_theil_identity_and_nonnegative_kl() -> None:
    result = demand.reference_metrics(
        np.array([60.0, 30.0, 10.0]),
        np.array([50.0, 30.0, 20.0]),
        reference_total_raw=100.0,
        world_min_positive=20.0,
        universe_count=3,
    )
    assert abs(result["theil_identity_residual"]) < 1e-12
    assert result["specialization_kl"] >= 0


def test_import_policies_remove_importer_and_origin_once() -> None:
    group = pd.DataFrame(
        {
            "world_imports": [100.0, 80.0],
            "focal_importer_imports": [10.0, 5.0],
            "focal_origin_imports": [20.0, 7.0],
            "focal_self_imports": [2.0, 1.0],
        }
    )
    assert np.allclose(demand.policy_reference(group, "inclusive_imports"), [100, 80])
    assert np.allclose(demand.policy_reference(group, "exclude_importer"), [90, 75])
    assert np.allclose(demand.policy_reference(group, "double_leave_out"), [72, 69])


def test_screen_sets_are_nested() -> None:
    frame = pd.DataFrame(
        {
            "reporter_code": [1, 2, 3, 4],
            "is_focal_cadot156": [True, True, True, False],
            "keep_baseline": [True] * 4,
            "keep_screen_a": [True, True, False, True],
            "keep_screen_b": [True, False, False, True],
            "keep_screen_c": [True, False, False, False],
        }
    )
    sets = core.screened_sets(frame)
    assert sets["screen_a"]["benchmark"] <= sets["baseline"]["benchmark"]
    assert sets["screen_b"]["benchmark"] <= sets["screen_a"]["benchmark"]
    assert sets["screen_c"]["benchmark"] <= sets["screen_b"]["benchmark"]
    assert sets["screen_c"]["focal"] <= sets["screen_b"]["focal"]


def test_fixed_rich_cutoff_matches_existing_threshold() -> None:
    assert math.isclose(core.RICH_CUTOFF, 39_308.45150637668)
    assert core.SCREEN_B == {"HKG", "SGP", "NLD", "BEL"}
