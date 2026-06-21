import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts/run_world_market_concentration_decomposition.py"
)
SPEC = importlib.util.spec_from_file_location("world_market_decomposition", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_theil_decomposition_identity_with_inclusive_benchmark():
    group = pd.DataFrame(
        {
            "trade_value": [60.0, 30.0, 10.0],
            "world_product_exports": [500.0, 300.0, 200.0],
        }
    )
    result = MODULE.benchmark_metrics(
        group,
        universe_count=4,
        world_total=1000.0,
        world_positive_count=3,
        world_min_positive=200.0,
        policy="inclusive",
    )
    assert abs(result["theil_identity_residual"]) < 1e-12
    assert result["specialization_kl"] >= 0


def test_leave_one_out_smoothing_is_bounded_and_audited():
    group = pd.DataFrame(
        {
            "trade_value": [10.0, 50.0],
            "world_product_exports": [10.0, 150.0],
        }
    )
    result = MODULE.benchmark_metrics(
        group,
        universe_count=3,
        world_total=200.0,
        world_positive_count=2,
        world_min_positive=10.0,
        policy="loo_smoothed",
    )
    assert result["exclusive_product_rows"] == 1
    assert np.isclose(result["exclusive_product_trade_share"], 1 / 6)
    assert result["smoothing_floor_trade_value"] > 0
    assert abs(result["theil_identity_residual"]) < 1e-12
