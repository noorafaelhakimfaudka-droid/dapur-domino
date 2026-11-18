"""Tests for log-return transform and ADF/KPSS stationarity evaluation (FR-B2, VP4)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from dapur_domino.prices.stationarity import compute_log_returns, evaluate_panel_stationarity


def test_stationarity_distinguishes_random_walk_from_log_returns() -> None:
    rng = np.random.default_rng(42)
    n = 250
    dates = pd.bdate_range("2025-01-01", periods=n)
    # Random walk in log-price -> levels are non-stationary, log-returns are stationary.
    shocks = rng.normal(0.0, 0.02, size=n)
    rw_prices = 40000.0 * np.exp(np.cumsum(shocks))
    const_prices = np.full(n, 15000.0)

    cols = pd.MultiIndex.from_tuples([("cat_7", "Kota Uji"), ("cat_1", "Kota Konstan")])
    wide = pd.DataFrame(np.column_stack([rw_prices, const_prices]), index=dates, columns=cols)

    returns = compute_log_returns(wide)
    report_df, summary = evaluate_panel_stationarity(wide, returns, min_obs=30)

    rw_row = report_df.loc[report_df["entity_name"] == "Kota Uji"].iloc[0]
    const_row = report_df.loc[report_df["entity_name"] == "Kota Konstan"].iloc[0]

    assert rw_row["return_status"] == "stationary_both"
    assert bool(rw_row["return_adf_pass"]) is True
    assert bool(rw_row["return_kpss_pass"]) is True
    assert const_row["return_status"] == "constant_series"
    assert summary["total_series"] == 2
