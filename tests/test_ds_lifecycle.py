"""Tests for Data Science lifecycle audit tables, EDA helpers, scenario tests, & model review."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from dapur_domino.evaluation.lifecycle import (
    analyze_price_distributions,
    build_business_objectives_matrix,
    build_feature_engineering_audit,
    build_model_review_decision_matrix,
    evaluate_timeseries_modeling_scenarios,
    evaluate_vp3_ranking_and_error_taxonomy,
)


def test_business_objectives_and_feature_engineering_tables() -> None:
    bo = build_business_objectives_matrix()
    fea = build_feature_engineering_audit()
    assert len(bo) == 4
    assert "objective_id" in bo.columns
    assert len(fea) == 6
    assert "feature_group" in fea.columns


def test_eda_and_timeseries_validation_scenarios(tmp_path: Path) -> None:
    rng = np.random.default_rng(42)
    dates = pd.bdate_range("2024-01-01", periods=140, freq="B")
    r1 = rng.normal(0.0, 0.01, size=140)
    r2 = np.zeros(140)
    for t in range(1, 140):
        r2[t] = 0.65 * r1[t - 1] + rng.normal(0.0, 0.005)

    returns_df = pd.DataFrame(
        {"cat_1__Semua Provinsi": r1, "cat_2__Semua Provinsi": r2}, index=dates
    )
    prices_df = pd.DataFrame(
        10000.0 * np.exp(returns_df.cumsum().to_numpy(dtype=float)),
        index=dates,
        columns=returns_df.columns,
    )

    stats_df, corr_df = analyze_price_distributions(prices_df, returns_df)
    assert len(stats_df) == 2
    assert "cv_pct" in stats_df.columns
    assert corr_df.shape == (2, 3)

    holiday_csv = tmp_path / "holidays.csv"
    holiday_csv.write_text(
        "event,date,window_pre_days,window_post_days\nIdul_Fitri_2024,2024-04-10,14,7\n",
        encoding="utf-8",
    )
    scen_df = evaluate_timeseries_modeling_scenarios(
        returns_df, holiday_csv, subtrain_end=90, val_end=130
    )
    assert len(scen_df) == 8
    assert "scenario_id" in scen_df.columns


def test_error_taxonomy_and_model_review_matrix(tmp_path: Path) -> None:
    vp3_path = tmp_path / "vp3.json"
    vp3_path.write_text(
        json.dumps(
            [
                {
                    "ingredient": "cabai merah",
                    "in_vocab": True,
                    "expected": ["cabai merah keriting", "cabai rawit"],
                    "predicted_top10": ["cabai merah keriting", "bawang merah", "garam"],
                    "hit_at_5": True,
                    "hit_at_10": True,
                },
                {
                    "ingredient": "bawang putih",
                    "in_vocab": True,
                    "expected": ["bawang bombay"],
                    "predicted_top10": ["di", "sy", "garam"],
                    "hit_at_5": False,
                    "hit_at_10": False,
                },
            ]
        ),
        encoding="utf-8",
    )
    metrics, err_df = evaluate_vp3_ranking_and_error_taxonomy(vp3_path)
    assert metrics["mrr_at_10"] == 0.5
    assert len(err_df) == 2

    wf_raw = pd.DataFrame(
        [
            {
                "target": "cat_3",
                "commodity_name": "Daging Sapi",
                "rmse_naive": 0.0025,
                "rmse_ar": 0.0028,
                "rmse_domino": 0.0024,
                "skill_vs_naive_pct": 4.0,
                "skill_vs_ar_pct": 14.2,
                "dm_pvalue_vs_ar": 0.01,
                "vp6_validated": True,
            },
            {
                "target": "cat_7",
                "commodity_name": "Cabai Merah",
                "rmse_naive": 0.022,
                "rmse_ar": 0.020,
                "rmse_domino": 0.021,
                "skill_vs_naive_pct": 4.5,
                "skill_vs_ar_pct": -5.0,
                "dm_pvalue_vs_ar": 0.02,
                "vp6_validated": False,
            },
        ]
    )
    rev = build_model_review_decision_matrix(wf_raw, wf_raw)
    assert len(rev) == 2
    cat3_dec = str(rev.loc[rev["comcat_id"] == "cat_3", "review_decision"].iloc[0])
    cat7_dec = str(rev.loc[rev["comcat_id"] == "cat_7", "review_decision"].iloc[0])
    assert "DEPLOY_DOMINO" in cat3_dec
    assert "FALLBACK_KE_AR5" in cat7_dec
