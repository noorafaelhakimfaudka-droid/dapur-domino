"""Tests for Granger causality, BH-FDR, seasonal control, and VP5 permutation check."""

from __future__ import annotations

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import grangercausalitytests

from dapur_domino.prices.domino import (
    benjamini_hochberg_fdr,
    compare_seasonal_robustness,
    discover_domino_network,
    granger_ftest,
    run_circular_shift_permutation_control,
)
from dapur_domino.prices.seasonality import residualize_calendar_seasonality


def test_granger_ftest_matches_statsmodels_ssr_ftest() -> None:
    rng = np.random.default_rng(123)
    n = 200
    x = rng.normal(0.0, 1.0, size=n)
    y = np.zeros(n, dtype=float)
    for t in range(2, n):
        y[t] = 0.3 * y[t - 1] + 0.6 * x[t - 2] + rng.normal(0.0, 0.5)

    f_ours, p_ours, _ = granger_ftest(x, y, lag=3)
    sm_res = grangercausalitytests(np.column_stack([y, x]), maxlag=3)
    f_sm, p_sm, _, _ = sm_res[3][0]["ssr_ftest"]

    assert np.isclose(f_ours, f_sm, rtol=1e-9, atol=1e-9)
    assert np.isclose(p_ours, p_sm, rtol=1e-9, atol=1e-9)


def test_benjamini_hochberg_fdr_monotonicity() -> None:
    p = np.array([0.001, 0.01, 0.04, 0.5, 0.9])
    q = benjamini_hochberg_fdr(p)
    assert np.all((q >= 0.0) & (q <= 1.0))
    assert q[0] < q[1] < q[2] < q[3] <= q[4]


def test_discover_domino_and_vp5_permutation_on_synthetic_system() -> None:
    rng = np.random.default_rng(42)
    n = 300
    dates = pd.bdate_range("2024-01-01", periods=n)
    x = rng.normal(0.0, 0.02, size=n)
    y = np.zeros(n, dtype=float)
    z = rng.normal(0.0, 0.02, size=n)
    for t in range(2, n):
        y[t] = 0.2 * y[t - 1] + 0.7 * x[t - 2] + rng.normal(0.0, 0.01)

    df = pd.DataFrame({"X": x, "Y": y, "Z": z}, index=dates)
    res = discover_domino_network(df, granger_lag=3, xcorr_max_lag=5, fdr_alpha=0.05)
    sig_pairs = {
        (str(r["source"]), str(r["target"]))
        for _, r in res.edges_df.loc[res.edges_df["significant"]].iterrows()
    }
    assert ("X", "Y") in sig_pairs
    assert ("Z", "Y") not in sig_pairs

    perm = run_circular_shift_permutation_control(
        df, seed=42, n_permutations=10, granger_lag=3, fdr_alpha=0.05
    )
    assert perm["mean_false_edge_rate"] <= 0.15

    rob = compare_seasonal_robustness(res.edges_df, res.edges_df)
    assert rob["retention_pct_of_base"] == 100.0


def test_seasonal_residualization_has_zero_test_leakage() -> None:
    rng = np.random.default_rng(9)
    dates = pd.bdate_range("2024-01-01", periods=120)
    df1 = pd.DataFrame({"A": rng.normal(0.0, 0.02, size=120)}, index=dates)
    df2 = df1.copy()
    # Mutate test split rows dramatically; train residuals MUST remain bitwise identical.
    df2.iloc[80:, 0] = 5.0

    r1 = residualize_calendar_seasonality(df1, train_end_idx=80)
    r2 = residualize_calendar_seasonality(df2, train_end_idx=80)
    np.testing.assert_allclose(r1.iloc[:80, 0].to_numpy(), r2.iloc[:80, 0].to_numpy(), atol=1e-15)
