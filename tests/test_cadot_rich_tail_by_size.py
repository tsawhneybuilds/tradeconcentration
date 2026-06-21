from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_cadot_rich_tail_by_size as rich_tail


def test_country_means_recalculate_income_square_after_collapsing() -> None:
    panel = pd.DataFrame(
        {
            "country": ["A", "A", "B", "B"],
            "iso3": ["AAA", "AAA", "BBB", "BBB"],
            "reporter_code": [1, 1, 2, 2],
            "year": [2000, 2001, 2000, 2001],
            rich_tail.INCOME: [10_000.0, 30_000.0, 20_000.0, 40_000.0],
            "gdp_pc_ppp_constant_2021_intl_usd_10k_sq": [1.0, 9.0, 4.0, 16.0],
            "log_population": [10.0, 10.0, 12.0, 12.0],
            "oil_export_share": [0.0, 0.0, 0.0, 0.0],
            "export_product_gini": [0.8, 0.7, 0.6, 0.5],
            "export_product_theil": [4.0, 3.0, 2.0, 1.0],
        }
    )
    # qcut needs at least three distinct country values.
    third = panel.loc[panel["reporter_code"].eq(2)].copy()
    third["country"] = "C"
    third["iso3"] = "CCC"
    third["reporter_code"] = 3
    third["log_population"] = 14.0
    panel = pd.concat([panel, third], ignore_index=True)

    means = rich_tail.build_country_means(panel)
    row = means.loc[means["iso3"].eq("AAA")].iloc[0]

    assert math.isclose(row[rich_tail.INCOME_10K], 2.0)
    assert math.isclose(row[rich_tail.INCOME_10K_SQ], 4.0)


def test_linear_combination_uses_model_covariance() -> None:
    frame = pd.DataFrame(
        {
            "y": [1.0, 2.0, 4.0, 7.0, 11.0, 16.0],
            rich_tail.INCOME_10K: [0.0, 1.0, 2.0, 3.0, 4.0, 5.0],
        }
    )
    frame[rich_tail.INCOME_10K_SQ] = frame[rich_tail.INCOME_10K] ** 2
    model = rich_tail.sm.OLS(
        frame["y"],
        rich_tail.sm.add_constant(
            frame[[rich_tail.INCOME_10K, rich_tail.INCOME_10K_SQ]]
        ),
    ).fit(cov_type="HC3")
    estimate, std_error, _ = rich_tail.linear_combination(
        model,
        {
            rich_tail.INCOME_10K: 1.0,
            rich_tail.INCOME_10K_SQ: 4.0,
        },
    )

    expected = (
        model.params[rich_tail.INCOME_10K]
        + 4.0 * model.params[rich_tail.INCOME_10K_SQ]
    )
    assert math.isclose(estimate, expected)
    assert std_error >= 0.0
