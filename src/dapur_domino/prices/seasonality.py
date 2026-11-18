"""Calendar, seasonal, and holiday regression control fitted strictly on train split (FR-B7)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd


def load_holiday_calendar(path: Path) -> pd.DataFrame:
    """Load external Indonesian holiday calendar with pre/post window definitions."""
    if not path.is_file():
        raise FileNotFoundError(f"Holiday calendar not found: {path}")
    df = pd.read_csv(path)
    required = {"date", "event", "window_pre_days", "window_post_days"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Holiday calendar missing columns: {sorted(missing)}")
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d", errors="raise")
    df["window_pre_days"] = df["window_pre_days"].astype(int)
    df["window_post_days"] = df["window_post_days"].astype(int)
    return df


def build_calendar_design_matrix(
    dates: pd.DatetimeIndex,
    holiday_df: pd.DataFrame | None = None,
) -> np.ndarray:
    """Build deterministic calendar/holiday design matrix with zero future data leakage.

    Features:
      - intercept (1)
      - day-of-week dummies (Mon..Thu vs Fri)
      - annual Fourier harmonics k=1,2 (sin/cos of day-of-year)
      - pre-holiday and post-holiday window indicators if holiday_df is provided
    """
    n = len(dates)
    cols: list[np.ndarray] = [np.ones(n, dtype=float)]

    dow = dates.dayofweek.to_numpy()
    for d in range(4):  # 0..3; Friday (4) is reference
        cols.append((dow == d).astype(float))

    doy = dates.dayofyear.to_numpy(dtype=float)
    for k in (1, 2):
        angle = 2.0 * np.pi * k * doy / 365.25
        cols.append(np.sin(angle))
        cols.append(np.cos(angle))

    if holiday_df is not None and not holiday_df.empty:
        pre_flag = np.zeros(n, dtype=float)
        post_flag = np.zeros(n, dtype=float)
        date_arr = dates.normalize()
        for _, row in holiday_df.iterrows():
            ev_date = pd.Timestamp(row["date"]).normalize()
            pre_start = ev_date - timedelta(days=int(row["window_pre_days"]))
            post_end = ev_date + timedelta(days=int(row["window_post_days"]))
            pre_flag = np.maximum(
                pre_flag, ((date_arr >= pre_start) & (date_arr < ev_date)).astype(float)
            )
            post_flag = np.maximum(
                post_flag, ((date_arr >= ev_date) & (date_arr <= post_end)).astype(float)
            )
        cols.append(pre_flag)
        cols.append(post_flag)

    return np.column_stack(cols)


def residualize_calendar_seasonality(
    full_returns: pd.DataFrame,
    train_end_idx: int,
    holiday_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Remove calendar/seasonal/holiday effects fitted ONLY on `full_returns.iloc[:train_end_idx]`.

    Returns residuals across the full index without leaking test-period coefficients.
    """
    if not isinstance(full_returns.index, pd.DatetimeIndex):
        raise TypeError("full_returns index must be a DatetimeIndex")
    if train_end_idx < 30 or train_end_idx > len(full_returns):
        raise ValueError(f"Invalid train_end_idx={train_end_idx} for length={len(full_returns)}")

    x_all = build_calendar_design_matrix(full_returns.index, holiday_df=holiday_df)
    x_train = x_all[:train_end_idx]

    out = full_returns.copy()
    for col in full_returns.columns:
        y_all = full_returns[col].to_numpy(dtype=float)
        y_train = y_all[:train_end_idx]
        valid = np.isfinite(y_train)
        if int(valid.sum()) <= x_train.shape[1] + 5:
            continue
        beta, *_ = np.linalg.lstsq(x_train[valid], y_train[valid], rcond=None)
        predicted = x_all @ beta
        out[col] = y_all - predicted
    return out
