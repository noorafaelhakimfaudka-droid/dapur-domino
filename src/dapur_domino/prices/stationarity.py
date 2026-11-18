"""Log-return transformation and ADF/KPSS stationarity testing (FR-B2, VP4)."""

from __future__ import annotations

import warnings
from typing import Any

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller, kpss


def compute_log_returns(wide_prices: pd.DataFrame) -> pd.DataFrame:
    """Compute daily business-day log-returns ln(P_t / P_{t-1}) without cross-filling gaps."""
    if wide_prices.empty:
        return wide_prices.copy()
    positive = wide_prices.where(wide_prices > 0)
    log_p = pd.DataFrame(
        np.log(positive.to_numpy(dtype=float)),
        index=positive.index,
        columns=positive.columns,
    )
    return log_p.diff()


def test_series_stationarity(
    series: pd.Series,
    *,
    alpha: float = 0.05,
    min_obs: int = 30,
) -> dict[str, Any]:
    """Run ADF and KPSS stationarity tests on a single numeric series.

    ADF null hypothesis: series has a unit root (non-stationary). Pass when p < alpha.
    KPSS null hypothesis: series is level-stationary. Pass when p >= alpha.
    """
    clean = pd.to_numeric(series, errors="coerce").dropna()
    n_obs = len(clean)
    if n_obs < min_obs:
        return {
            "n_obs": n_obs,
            "adf_stat": None,
            "adf_pvalue": None,
            "kpss_stat": None,
            "kpss_pvalue": None,
            "kpss_boundary_note": None,
            "adf_pass": False,
            "kpss_pass": False,
            "status": "insufficient_data",
        }

    if float(clean.std(ddof=0)) == 0.0:
        return {
            "n_obs": n_obs,
            "adf_stat": None,
            "adf_pvalue": None,
            "kpss_stat": None,
            "kpss_pvalue": None,
            "kpss_boundary_note": None,
            "adf_pass": False,
            "kpss_pass": False,
            "status": "constant_series",
        }

    adf_stat, adf_p, *_ = adfuller(
        clean.to_numpy(dtype=float), autolag="AIC", result_object=False
    )
    adf_pass = bool(float(adf_p) < alpha)

    kpss_note: str | None = None
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        kpss_stat, kpss_p, *_ = kpss(clean.to_numpy(dtype=float), regression="c", nlags="auto")
        if caught:
            kpss_note = "; ".join(str(w.message) for w in caught)
    kpss_pass = bool(float(kpss_p) >= alpha)

    if adf_pass and kpss_pass:
        status = "stationary_both"
    elif adf_pass:
        status = "adf_only"
    elif kpss_pass:
        status = "kpss_only"
    else:
        status = "non_stationary"

    return {
        "n_obs": n_obs,
        "adf_stat": round(float(adf_stat), 6),
        "adf_pvalue": round(float(adf_p), 6),
        "kpss_stat": round(float(kpss_stat), 6),
        "kpss_pvalue": round(float(kpss_p), 6),
        "kpss_boundary_note": kpss_note,
        "adf_pass": adf_pass,
        "kpss_pass": kpss_pass,
        "status": status,
    }


def evaluate_panel_stationarity(
    wide_prices: pd.DataFrame,
    wide_returns: pd.DataFrame,
    *,
    alpha: float = 0.05,
    min_obs: int = 30,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Evaluate ADF + KPSS on both price levels and log-returns across all columns (VP4)."""
    rows: list[dict[str, Any]] = []
    for col in wide_prices.columns:
        comcat_id, entity_name = col if isinstance(col, tuple) else ("unknown", str(col))
        lvl_res = test_series_stationarity(wide_prices[col], alpha=alpha, min_obs=min_obs)
        ret_res = test_series_stationarity(wide_returns[col], alpha=alpha, min_obs=min_obs)
        rows.append(
            {
                "comcat_id": comcat_id,
                "entity_name": entity_name,
                "level_n_obs": lvl_res["n_obs"],
                "level_adf_pvalue": lvl_res["adf_pvalue"],
                "level_kpss_pvalue": lvl_res["kpss_pvalue"],
                "level_status": lvl_res["status"],
                "return_n_obs": ret_res["n_obs"],
                "return_adf_stat": ret_res["adf_stat"],
                "return_adf_pvalue": ret_res["adf_pvalue"],
                "return_kpss_stat": ret_res["kpss_stat"],
                "return_kpss_pvalue": ret_res["kpss_pvalue"],
                "return_kpss_boundary_note": ret_res["kpss_boundary_note"],
                "return_adf_pass": ret_res["adf_pass"],
                "return_kpss_pass": ret_res["kpss_pass"],
                "return_status": ret_res["status"],
            }
        )

    report_df = pd.DataFrame(rows)
    total = len(report_df)
    if total == 0:
        summary: dict[str, Any] = {
            "total_series": 0,
            "return_stationary_both": 0,
            "return_stationary_both_pct": 0.0,
            "return_adf_pass_pct": 0.0,
            "level_stationary_both": 0,
        }
        return report_df, summary

    both_pass = int((report_df["return_status"] == "stationary_both").sum())
    adf_pass_n = int(report_df["return_adf_pass"].sum())
    lvl_both = int((report_df["level_status"] == "stationary_both").sum())
    summary = {
        "total_series": total,
        "return_stationary_both": both_pass,
        "return_stationary_both_pct": round(100.0 * both_pass / total, 2),
        "return_adf_pass": adf_pass_n,
        "return_adf_pass_pct": round(100.0 * adf_pass_n / total, 2),
        "level_stationary_both": lvl_both,
        "return_status_counts": report_df["return_status"].value_counts().to_dict(),
    }
    return report_df, summary
