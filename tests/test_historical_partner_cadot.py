from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from run_historical_partner_cadot import (
    MODEL_INCOME_LEVEL,
    RegressionComponent,
    classify_country_episode,
    classify_u_shape,
    prepare_model_dataset,
    preferred_pooled_turning_points,
    robust_result,
    turning_point_value,
    wild_cluster_bootstrap_pvalue,
)


def synthetic_panel(turning_point: float, quadratic: float, *, n_entities: int = 13, years: int = 80) -> pd.DataFrame:
    rows = []
    for entity in range(n_entities):
        entity_id = f"E{entity:02d}"
        for year in range(1900, 1900 + years):
            income = 0.4 + (year - 1900) / 25.0 + entity * 0.03
            outcome = 1.0 + 0.2 * entity + quadratic * ((income - turning_point) ** 2)
            rows.append(
                {
                    "entity_id": entity_id,
                    "year": year,
                    "flow": "Exports",
                    "partner_gini": outcome,
                    "gdppc_10k": income,
                    "gdppc_10k_sq": income**2,
                    "log_population": np.log(1000 + entity * 10 + year - 1900),
                    "metric_valid": True,
                }
            )
    return pd.DataFrame(rows)


def test_turning_point_formula_level_income() -> None:
    params = pd.Series({"gdppc_10k": -0.6, "gdppc_10k_sq": 0.1})
    tp_var, tp_ppp = turning_point_value(params, "gdppc_10k", "gdppc_10k_sq", MODEL_INCOME_LEVEL)
    assert np.isclose(tp_var, 3.0)
    assert np.isclose(tp_ppp, 30_000.0)


def test_wild_cluster_bootstrap_is_deterministic() -> None:
    panel = synthetic_panel(2.5, 0.08, years=50)
    result = smf.ols("partner_gini ~ gdppc_10k + gdppc_10k_sq + C(entity_id) + C(year)", data=panel).fit()
    robust = robust_result(result, panel["entity_id"])
    names = robust.model.exog_names
    contrast = np.zeros(len(names))
    contrast[names.index("gdppc_10k_sq")] = 1.0
    p1 = wild_cluster_bootstrap_pvalue(robust, panel["entity_id"].to_numpy(), contrast, alternative="greater", draws=399)
    p2 = wild_cluster_bootstrap_pvalue(robust, panel["entity_id"].to_numpy(), contrast, alternative="greater", draws=399)
    assert p1 == p2


def test_classify_u_shape_supported_outside_and_no_u_shape() -> None:
    supported = synthetic_panel(2.5, 0.08)
    result = smf.ols("partner_gini ~ gdppc_10k + gdppc_10k_sq + C(entity_id) + C(year)", data=supported).fit()
    robust = robust_result(result, supported["entity_id"])
    params = pd.Series(np.asarray(robust.params), index=robust.model.exog_names)
    verdict = classify_u_shape(
        params,
        robust,
        supported,
        RegressionComponent("entity_year_fe", "within", "gdppc_10k", "gdppc_10k_sq"),
        MODEL_INCOME_LEVEL,
        use_wcb=False,
    )
    assert verdict["classification"] == "supported_u_shape"

    outside = synthetic_panel(12.0, 0.03)
    result = smf.ols("partner_gini ~ gdppc_10k + gdppc_10k_sq + C(entity_id) + C(year)", data=outside).fit()
    robust = robust_result(result, outside["entity_id"])
    params = pd.Series(np.asarray(robust.params), index=robust.model.exog_names)
    verdict = classify_u_shape(
        params,
        robust,
        outside,
        RegressionComponent("entity_year_fe", "within", "gdppc_10k", "gdppc_10k_sq"),
        MODEL_INCOME_LEVEL,
        use_wcb=False,
    )
    assert verdict["classification"] == "outside_support"

    monotone = synthetic_panel(2.5, -0.05)
    result = smf.ols("partner_gini ~ gdppc_10k + gdppc_10k_sq + C(entity_id) + C(year)", data=monotone).fit()
    robust = robust_result(result, monotone["entity_id"])
    params = pd.Series(np.asarray(robust.params), index=robust.model.exog_names)
    verdict = classify_u_shape(
        params,
        robust,
        monotone,
        RegressionComponent("entity_year_fe", "within", "gdppc_10k", "gdppc_10k_sq"),
        MODEL_INCOME_LEVEL,
        use_wcb=False,
    )
    assert verdict["classification"] == "no_u_shape"


def test_country_episode_classifier() -> None:
    assert classify_country_episode(-0.4, 0.03, 0.5, 0.02, True, 80, 30, 30) == "diversification_then_reconcentration"
    assert classify_country_episode(-0.4, 0.03, 0.1, 0.50, True, 80, 30, 30) == "diversification_only"
    assert classify_country_episode(-0.1, 0.50, 0.5, 0.02, True, 80, 30, 30) == "reconcentration_only"
    assert classify_country_episode(-0.1, 0.50, 0.1, 0.50, True, 80, 30, 30) == "flat/unclear"
    assert classify_country_episode(-0.4, 0.03, 0.5, 0.02, False, 80, 5, 5) == "insufficient_support"


def test_preferred_pooled_turning_point_lookup() -> None:
    summary = pd.DataFrame(
        {
            "variant": ["baseline_threshold20", "baseline_threshold20"],
            "income_form": ["gdppc_10k", "gdppc_10k"],
            "sample_policy": ["fixed", "fixed"],
            "model_name": ["pooled_year_fe", "pooled_year_fe"],
            "curve_component": ["overall", "overall"],
            "flow": ["Exports", "Imports"],
            "metric_name": ["Gini", "HHI"],
            "turning_point_ppp_2011_usd": [25_000.0, 40_000.0],
            "classification": ["supported_u_shape", "outside_support"],
            "u_test_p_value": [0.01, 0.40],
        }
    )
    lookup = preferred_pooled_turning_points(summary)
    assert lookup[("Exports", "Gini")]["turning_point_ppp_2011_usd"] == 25_000.0
    assert np.isnan(lookup[("Imports", "HHI")]["turning_point_ppp_2011_usd"])


def test_fixed_sample_does_not_require_log_population_for_models_without_pop_control() -> None:
    panel = pd.DataFrame(
        {
            "entity_id": ["A", "A", "B", "B"],
            "year": [1900, 1901, 1900, 1901],
            "partner_gini": [0.2, 0.3, 0.4, 0.5],
            "gdppc_10k": [1.0, 1.1, 1.2, 1.3],
            "gdppc_10k_sq": [1.0, 1.21, 1.44, 1.69],
            "log_population": [np.nan, 2.0, np.nan, 2.3],
        }
    )
    analytic, required = prepare_model_dataset(panel, "partner_gini", "gdppc_10k", "pooled_year_fe", "fixed")
    assert "log_population" not in required
    assert len(analytic) == 4

    analytic_pop, required_pop = prepare_model_dataset(panel, "partner_gini", "gdppc_10k", "entity_year_fe_logpop", "fixed")
    assert "log_population" in required_pop
    assert len(analytic_pop) == 2
