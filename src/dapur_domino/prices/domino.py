"""Lead-lag cross-correlation, Granger causality, BH-FDR, directed graphs, and VP5 control."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import networkx as nx
import numpy as np
import pandas as pd
from scipy import stats


@dataclass(frozen=True)
class DominoDiscoveryResult:
    """Output of directed lead-lag and Granger discovery over a return panel."""

    edges_df: pd.DataFrame
    nodes_df: pd.DataFrame
    graph: nx.DiGraph[str]
    total_pairs_tested: int
    significant_edges: int


def benjamini_hochberg_fdr(p_values: np.ndarray) -> np.ndarray:
    """Compute Benjamini-Hochberg FDR-adjusted q-values (step-up)."""
    p = np.asarray(p_values, dtype=float)
    m = len(p)
    if m == 0:
        return p.copy()
    order = np.argsort(p)
    sorted_p = p[order]
    ranks = np.arange(1, m + 1, dtype=float)
    raw_q = sorted_p * m / ranks
    # Enforce monotonicity from largest to smallest rank.
    monotone_q = np.minimum.accumulate(raw_q[::-1])[::-1]
    clipped = np.clip(monotone_q, 0.0, 1.0)
    q_values = np.empty_like(clipped)
    q_values[order] = clipped
    return q_values


def compute_lagged_cross_correlation(
    x: np.ndarray,
    y: np.ndarray,
    *,
    max_lag: int = 10,
) -> tuple[int, float, dict[int, float]]:
    """Compute Pearson correlation corr(x_{t-lag}, y_t) for lag = 1..max_lag."""
    corrs: dict[int, float] = {}
    best_lag = 1
    best_corr = 0.0
    best_abs = -1.0

    for lag in range(1, max_lag + 1):
        if len(x) <= lag + 2:
            corrs[lag] = 0.0
            continue
        x_lag = x[:-lag]
        y_cur = y[lag:]
        valid = np.isfinite(x_lag) & np.isfinite(y_cur)
        if int(valid.sum()) < 10:
            r = 0.0
        else:
            xv = x_lag[valid]
            yv = y_cur[valid]
            if float(np.std(xv)) <= 1e-12 or float(np.std(yv)) <= 1e-12:
                r = 0.0
            else:
                r = float(np.corrcoef(xv, yv)[0, 1])
        corrs[lag] = r
        if abs(r) > best_abs:
            best_abs = abs(r)
            best_lag = lag
            best_corr = r

    return best_lag, best_corr, corrs


def granger_ftest(x: np.ndarray, y: np.ndarray, *, lag: int) -> tuple[float, float, int]:
    """Test if lags 1..lag of x Granger-cause y via OLS SSR F-test.

    Matches `statsmodels.tsa.stattools.grangercausalitytests` (`ssr_ftest`)
    while remaining fast enough for thousands of spatial city/province pairs.
    """
    if lag < 1:
        raise ValueError(f"lag must be >= 1, got {lag}")
    n = len(y)
    if n <= 2 * lag + 2:
        return 0.0, 1.0, 0

    y_target = y[lag:]
    cols_y = [y[lag - k : n - k] for k in range(1, lag + 1)]
    cols_x = [x[lag - k : n - k] for k in range(1, lag + 1)]

    y_mat = np.column_stack(cols_y)
    x_mat = np.column_stack(cols_x)
    valid = np.isfinite(y_target) & np.all(np.isfinite(y_mat), axis=1) & np.all(
        np.isfinite(x_mat), axis=1
    )
    n_obs = int(valid.sum())
    df_den = n_obs - (2 * lag + 1)
    if df_den <= 2:
        return 0.0, 1.0, n_obs

    yv = y_target[valid]
    ones = np.ones((n_obs, 1), dtype=float)
    z_restricted = np.hstack([ones, y_mat[valid]])
    z_unrestricted = np.hstack([z_restricted, x_mat[valid]])

    # Guard against rank deficiency (e.g. near-constant subseries).
    if np.linalg.matrix_rank(z_unrestricted) < z_unrestricted.shape[1]:
        return 0.0, 1.0, n_obs

    beta_r, *_ = np.linalg.lstsq(z_restricted, yv, rcond=None)
    beta_u, *_ = np.linalg.lstsq(z_unrestricted, yv, rcond=None)

    rss_r = float(np.sum((yv - z_restricted @ beta_r) ** 2))
    rss_u = float(np.sum((yv - z_unrestricted @ beta_u) ** 2))

    if rss_u <= 1e-18 or rss_r <= rss_u:
        return 0.0, 1.0, n_obs

    f_stat = ((rss_r - rss_u) / lag) / (rss_u / df_den)
    p_value = float(stats.f.sf(f_stat, lag, df_den))
    return float(f_stat), p_value, n_obs


def discover_domino_network(
    returns_df: pd.DataFrame,
    *,
    granger_lag: int = 5,
    xcorr_max_lag: int = 10,
    fdr_alpha: float = 0.05,
    min_obs: int = 60,
) -> DominoDiscoveryResult:
    """Run pairwise lead-lag + Granger + BH-FDR over all ordered pairs in returns_df."""
    active_cols: list[str] = []
    arrays: dict[str, np.ndarray] = {}
    for col in returns_df.columns:
        arr = pd.to_numeric(returns_df[col], errors="coerce").to_numpy(dtype=float)
        finite = arr[np.isfinite(arr)]
        if len(finite) >= min_obs and float(np.std(finite)) > 1e-12:
            col_name = str(col)
            active_cols.append(col_name)
            arrays[col_name] = arr

    pair_rows: list[dict[str, Any]] = []
    for src in active_cols:
        x = arrays[src]
        for dst in active_cols:
            if src == dst:
                continue
            y = arrays[dst]
            f_stat, p_val, n_obs = granger_ftest(x, y, lag=granger_lag)
            best_lag, best_corr, _ = compute_lagged_cross_correlation(
                x, y, max_lag=xcorr_max_lag
            )
            pair_rows.append(
                {
                    "source": src,
                    "target": dst,
                    "granger_lag": granger_lag,
                    "n_obs": n_obs,
                    "f_stat": round(f_stat, 6),
                    "p_value": p_val,
                    "best_xcorr_lag": best_lag,
                    "best_xcorr": round(best_corr, 6),
                }
            )

    edges_df = pd.DataFrame(
        pair_rows,
        columns=[
            "source",
            "target",
            "granger_lag",
            "n_obs",
            "f_stat",
            "p_value",
            "best_xcorr_lag",
            "best_xcorr",
        ],
    )
    if edges_df.empty:
        edges_df["q_value"] = pd.Series(dtype=float)
        edges_df["significant"] = pd.Series(dtype=bool)
        edges_df["weight"] = pd.Series(dtype=float)
        empty_nodes = pd.DataFrame(
            columns=[
                "node",
                "out_degree",
                "in_degree",
                "weighted_out",
                "weighted_in",
                "net_trigger_score",
                "pagerank",
            ]
        )
        return DominoDiscoveryResult(
            edges_df=edges_df,
            nodes_df=empty_nodes,
            graph=nx.DiGraph(),
            total_pairs_tested=0,
            significant_edges=0,
        )

    edges_df["q_value"] = benjamini_hochberg_fdr(edges_df["p_value"].to_numpy(dtype=float))
    edges_df["significant"] = edges_df["q_value"] < fdr_alpha
    # Weight based on -log10(q_value) capped for numerical stability.
    q_clipped = np.clip(edges_df["q_value"].to_numpy(dtype=float), 1e-16, 1.0)
    edges_df["weight"] = np.where(edges_df["significant"], -np.log10(q_clipped), 0.0)
    edges_df = edges_df.sort_values(["q_value", "f_stat"], ascending=[True, False]).reset_index(
        drop=True
    )

    graph: nx.DiGraph[str] = nx.DiGraph()
    for node in active_cols:
        graph.add_node(node)

    sig_df = edges_df.loc[edges_df["significant"]]
    for _, row in sig_df.iterrows():
        graph.add_edge(
            str(row["source"]),
            str(row["target"]),
            q_value=float(row["q_value"]),
            p_value=float(row["p_value"]),
            f_stat=float(row["f_stat"]),
            best_lag=int(row["best_xcorr_lag"]),
            best_corr=float(row["best_xcorr"]),
            weight=float(row["weight"]),
        )

    pr = nx.pagerank(graph, weight="weight") if graph.number_of_edges() > 0 else {
        n: 0.0 for n in active_cols
    }
    node_rows: list[dict[str, Any]] = []
    for node in active_cols:
        out_deg = int(graph.out_degree(node))
        in_deg = int(graph.in_degree(node))
        w_out = float(graph.out_degree(node, weight="weight"))
        w_in = float(graph.in_degree(node, weight="weight"))
        node_rows.append(
            {
                "node": node,
                "out_degree": out_deg,
                "in_degree": in_deg,
                "weighted_out": round(w_out, 4),
                "weighted_in": round(w_in, 4),
                "net_trigger_score": round(w_out - w_in, 4),
                "pagerank": round(float(pr.get(node, 0.0)), 6),
            }
        )

    nodes_df = (
        pd.DataFrame(node_rows)
        .sort_values(["net_trigger_score", "weighted_out"], ascending=[False, False])
        .reset_index(drop=True)
    )
    return DominoDiscoveryResult(
        edges_df=edges_df,
        nodes_df=nodes_df,
        graph=graph,
        total_pairs_tested=len(edges_df),
        significant_edges=len(sig_df),
    )


def run_circular_shift_permutation_control(
    returns_df: pd.DataFrame,
    *,
    seed: int,
    n_permutations: int = 20,
    granger_lag: int = 5,
    fdr_alpha: float = 0.05,
    min_shift: int = 20,
) -> dict[str, Any]:
    """VP5 false-discovery control: circularly shift each series independently.

    Preserves univariate autocorrelation while breaking cross-series temporal alignment.
    """
    rng = np.random.default_rng(seed)
    n_rows = len(returns_df)
    if n_rows <= 2 * min_shift + 5:
        raise ValueError(f"Series length {n_rows} too short for min_shift={min_shift}")

    false_rates: list[float] = []
    false_counts: list[int] = []
    total_pairs = 0

    for _ in range(n_permutations):
        shifted_data: dict[str, np.ndarray] = {}
        for col in returns_df.columns:
            arr = returns_df[col].to_numpy(dtype=float)
            shift = int(rng.integers(min_shift, n_rows - min_shift))
            shifted_data[str(col)] = np.roll(arr, shift)
        shifted_df = pd.DataFrame(shifted_data, index=returns_df.index)
        res = discover_domino_network(
            shifted_df,
            granger_lag=granger_lag,
            xcorr_max_lag=granger_lag,
            fdr_alpha=fdr_alpha,
        )
        total_pairs = res.total_pairs_tested
        false_counts.append(res.significant_edges)
        rate = (res.significant_edges / total_pairs) if total_pairs > 0 else 0.0
        false_rates.append(rate)

    return {
        "n_permutations": n_permutations,
        "total_pairs_per_run": total_pairs,
        "fdr_alpha": fdr_alpha,
        "mean_false_edges": round(float(np.mean(false_counts)), 4),
        "max_false_edges": int(np.max(false_counts)),
        "mean_false_edge_rate": round(float(np.mean(false_rates)), 6),
        "max_false_edge_rate": round(float(np.max(false_rates)), 6),
    }


def compare_seasonal_robustness(
    base_edges_df: pd.DataFrame,
    adjusted_edges_df: pd.DataFrame,
) -> dict[str, Any]:
    """VP7 comparison: fraction of significant directed edges surviving seasonal/holiday control."""
    base_sig = (
        {
            (str(r["source"]), str(r["target"]))
            for _, r in base_edges_df.loc[base_edges_df["significant"]].iterrows()
        }
        if not base_edges_df.empty and "significant" in base_edges_df.columns
        else set()
    )
    adj_sig = (
        {
            (str(r["source"]), str(r["target"]))
            for _, r in adjusted_edges_df.loc[adjusted_edges_df["significant"]].iterrows()
        }
        if not adjusted_edges_df.empty and "significant" in adjusted_edges_df.columns
        else set()
    )
    survived = base_sig & adj_sig
    retention_pct = round(100.0 * len(survived) / len(base_sig), 2) if base_sig else 0.0
    return {
        "base_significant_edges": len(base_sig),
        "adjusted_significant_edges": len(adj_sig),
        "survived_edges": len(survived),
        "retention_pct_of_base": retention_pct,
        "new_only_after_adjustment": len(adj_sig - base_sig),
        "dropped_after_adjustment": len(base_sig - adj_sig),
    }
