"""Tests for out-of-sample walk-forward evaluation and VP6 gating."""

from __future__ import annotations

import numpy as np
import pandas as pd

from dapur_domino.evaluation.walk_forward import evaluate_walk_forward_domino
from dapur_domino.prices.domino import discover_domino_network


def test_walk_forward_validates_true_trigger_and_rejects_noise() -> None:
    rng = np.random.default_rng(99)
    n = 260
    dates = pd.bdate_range("2024-01-01", periods=n)
    x = rng.normal(0.0, 0.02, size=n)
    y = np.zeros(n, dtype=float)
    z = rng.normal(0.0, 0.02, size=n)
    for t in range(2, n):
        y[t] = 0.25 * y[t - 1] + 0.75 * x[t - 2] + rng.normal(0.0, 0.008)

    df = pd.DataFrame({"X": x, "Y": y, "Z": z}, index=dates)
    train_edges = discover_domino_network(df.iloc[:160], granger_lag=3, fdr_alpha=0.05).edges_df

    wf = evaluate_walk_forward_domino(
        df, train_edges, initial_train_days=160, lag=3, ridge_alpha=0.01
    )
    y_row = wf.loc[wf["target"] == "Y"].iloc[0]
    z_row = wf.loc[wf["target"] == "Z"].iloc[0]

    assert "X" in str(y_row["triggers"])
    assert bool(y_row["vp6_validated"]) is True
    assert float(y_row["skill_vs_ar_pct"]) > 10.0
    assert bool(z_row["vp6_validated"]) is False
