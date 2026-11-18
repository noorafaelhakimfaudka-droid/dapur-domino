"""Walk-forward out-of-sample forecast comparison vs Naive and AR baselines (FR-B8, VP6)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats


def _fit_ridge(x: np.ndarray, y: np.ndarray, alpha: float) -> np.ndarray:
    """Fit linear regression with L2 penalty on non-intercept columns."""
    p = x.shape[1]
    reg = np.eye(p, dtype=float) * alpha
    reg[0, 0] = 0.0  # never penalize intercept
    lhs = x.T @ x + reg
    rhs = x.T @ y
    return np.linalg.solve(lhs, rhs)


def diebold_mariano_test(
    errors_model: np.ndarray,
    errors_baseline: np.ndarray,
) -> tuple[float, float]:
    """Two-sided Diebold-Mariano test on squared forecast errors (h=1, Newey-West lag=0).

    Negative DM stat means `errors_model` has lower squared error than `errors_baseline`.
    """
    d = (errors_model**2) - (errors_baseline**2)
    n = len(d)
    if n < 10:
        return 0.0, 1.0
    mean_d = float(np.mean(d))
    var_d = float(np.var(d, ddof=1))
    if var_d <= 1e-24:
        return 0.0, 1.0
    dm_stat = mean_d / np.sqrt(var_d / n)
    p_val = float(2.0 * stats.t.sf(abs(dm_stat), df=n - 1))
    return float(dm_stat), p_val


def evaluate_walk_forward_domino(
    returns_df: pd.DataFrame,
    edges_train_df: pd.DataFrame,
    *,
    initial_train_days: int = 500,
    lag: int = 5,
    ridge_alpha: float = 1.0,
) -> pd.DataFrame:
    """Evaluate expanding-window 1-step-ahead forecasts strictly out-of-sample (VP6).

    Triggers for each target are taken ONLY from `edges_train_df` (which must be
    computed on `returns_df.iloc[:initial_train_days]`).
    """
    n_rows = len(returns_df)
    if initial_train_days < 4 * lag + 20 or initial_train_days >= n_rows - 10:
        raise ValueError(
            f"Invalid initial_train_days={initial_train_days} for n_rows={n_rows}, lag={lag}"
        )

    sig_edges = (
        edges_train_df.loc[edges_train_df["significant"]]
        if not edges_train_df.empty and "significant" in edges_train_df.columns
        else edges_train_df.iloc[0:0]
    )
    results: list[dict[str, Any]] = []

    for target_col in returns_df.columns:
        target = str(target_col)
        triggers = [
            str(s)
            for s in sig_edges.loc[sig_edges["target"] == target, "source"].tolist()
            if s != target and s in returns_df.columns
        ]

        y_series = pd.to_numeric(returns_df[target], errors="coerce").to_numpy(dtype=float)
        x_arrays = [
            pd.to_numeric(returns_df[src], errors="coerce").to_numpy(dtype=float)
            for src in triggers
        ]

        # Build lag matrix for all t in [lag, n_rows - 1].
        y_all = y_series[lag:]
        ar_cols = [y_series[lag - k : n_rows - k] for k in range(1, lag + 1)]
        x_ar_base = np.column_stack([np.ones(len(y_all), dtype=float), *ar_cols])

        if x_arrays:
            trig_cols = [
                arr[lag - k : n_rows - k] for arr in x_arrays for k in range(1, lag + 1)
            ]
            x_arx_base = np.hstack([x_ar_base, np.column_stack(trig_cols)])
        else:
            x_arx_base = x_ar_base

        # Map original time index `t` -> row index `idx = t - lag` in design matrices.
        y_true_list: list[float] = []
        pred_naive: list[float] = []
        pred_ar: list[float] = []
        pred_domino: list[float] = []

        for t in range(initial_train_days, n_rows):
            cur_idx = t - lag
            y_t = y_all[cur_idx]
            if not np.isfinite(y_t):
                continue
            if not np.all(np.isfinite(x_arx_base[cur_idx])):
                continue

            train_y = y_all[:cur_idx]
            train_ar = x_ar_base[:cur_idx]
            train_arx = x_arx_base[:cur_idx]

            valid_mask = (
                np.isfinite(train_y)
                & np.all(np.isfinite(train_ar), axis=1)
                & np.all(np.isfinite(train_arx), axis=1)
            )
            if int(valid_mask.sum()) < x_arx_base.shape[1] + 5:
                continue

            beta_ar = _fit_ridge(train_ar[valid_mask], train_y[valid_mask], alpha=1e-6)
            hat_ar = float(x_ar_base[cur_idx] @ beta_ar)

            if triggers:
                beta_arx = _fit_ridge(
                    train_arx[valid_mask], train_y[valid_mask], alpha=ridge_alpha
                )
                hat_arx = float(x_arx_base[cur_idx] @ beta_arx)
            else:
                hat_arx = hat_ar

            y_true_list.append(float(y_t))
            pred_naive.append(0.0)
            pred_ar.append(hat_ar)
            pred_domino.append(hat_arx)

        y_true = np.asarray(y_true_list, dtype=float)
        e_naive = y_true - np.asarray(pred_naive, dtype=float)
        e_ar = y_true - np.asarray(pred_ar, dtype=float)
        e_domino = y_true - np.asarray(pred_domino, dtype=float)

        rmse_naive = float(np.sqrt(np.mean(e_naive**2))) if len(y_true) else np.nan
        rmse_ar = float(np.sqrt(np.mean(e_ar**2))) if len(y_true) else np.nan
        rmse_domino = float(np.sqrt(np.mean(e_domino**2))) if len(y_true) else np.nan

        mae_naive = float(np.mean(np.abs(e_naive))) if len(y_true) else np.nan
        mae_ar = float(np.mean(np.abs(e_ar))) if len(y_true) else np.nan
        mae_domino = float(np.mean(np.abs(e_domino))) if len(y_true) else np.nan

        skill_vs_naive = (
            100.0 * (rmse_naive - rmse_domino) / rmse_naive
            if np.isfinite(rmse_naive) and rmse_naive > 0
            else 0.0
        )
        skill_vs_ar = (
            100.0 * (rmse_ar - rmse_domino) / rmse_ar
            if np.isfinite(rmse_ar) and rmse_ar > 0
            else 0.0
        )

        dm_vs_naive, dm_p_naive = diebold_mariano_test(e_domino, e_naive)
        dm_vs_ar, dm_p_ar = diebold_mariano_test(e_domino, e_ar)

        vp6_ok = bool(
            len(triggers) > 0
            and np.isfinite(rmse_domino)
            and rmse_domino < rmse_naive
            and rmse_domino < rmse_ar
        )

        results.append(
            {
                "target": target,
                "n_test": len(y_true),
                "n_triggers": len(triggers),
                "triggers": "|".join(triggers),
                "rmse_naive": round(rmse_naive, 6),
                "rmse_ar": round(rmse_ar, 6),
                "rmse_domino": round(rmse_domino, 6),
                "mae_naive": round(mae_naive, 6),
                "mae_ar": round(mae_ar, 6),
                "mae_domino": round(mae_domino, 6),
                "skill_vs_naive_pct": round(skill_vs_naive, 4),
                "skill_vs_ar_pct": round(skill_vs_ar, 4),
                "dm_stat_vs_naive": round(dm_vs_naive, 4),
                "dm_pvalue_vs_naive": round(dm_p_naive, 6),
                "dm_stat_vs_ar": round(dm_vs_ar, 4),
                "dm_pvalue_vs_ar": round(dm_p_ar, 6),
                "vp6_validated": vp6_ok,
            }
        )

    return pd.DataFrame(results)
