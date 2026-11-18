"""End-to-end Milestone M2 Domino Effect pipeline (FR-B3..FR-B8, VP5, VP6, VP7)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from dapur_domino.config import load_config
from dapur_domino.evaluation.walk_forward import evaluate_walk_forward_domino
from dapur_domino.ingest.pihps import PIHPS_CATEGORIES
from dapur_domino.prices.domino import (
    compare_seasonal_robustness,
    discover_domino_network,
    run_circular_shift_permutation_control,
)
from dapur_domino.prices.seasonality import load_holiday_calendar, residualize_calendar_seasonality
from dapur_domino.tracking import RunTracker, verify_run_manifest


def _simplify_commodity_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Convert `cat_X__Semua Provinsi` columns to readable `cat_X` IDs."""
    renamed = {col: str(col).split("__", maxsplit=1)[0] for col in df.columns}
    return df.rename(columns=renamed)


def _extract_commodity_slice(df: pd.DataFrame, comcat_id: str) -> pd.DataFrame:
    """Extract regional columns for a single `comcat_id` with entity names as columns."""
    prefix = f"{comcat_id}__"
    cols = [col for col in df.columns if str(col).startswith(prefix)]
    sub = df[cols].copy()
    sub.columns = pd.Index([str(c)[len(prefix) :] for c in cols])
    return sub


def build_holiday_event_study(
    prices_national_wide: pd.DataFrame,
    holiday_df: pd.DataFrame,
) -> pd.DataFrame:
    """Summarize observed price % changes before/after major Idul Fitri events (FR-D3)."""
    idul_fitri = holiday_df.loc[holiday_df["event"].str.startswith("Idul_Fitri")].copy()
    rows: list[dict[str, Any]] = []
    idx = pd.DatetimeIndex(prices_national_wide.index)

    for _, ev in idul_fitri.iterrows():
        ev_date = pd.Timestamp(ev["date"])
        pre_start = ev_date - timedelta(days=30)
        pre_base = ev_date - timedelta(days=20)
        peak_end = ev_date + timedelta(days=3)

        base_slice = prices_national_wide.loc[(idx >= pre_start) & (idx < pre_base)]
        peak_slice = prices_national_wide.loc[(idx >= pre_base) & (idx <= peak_end)]
        if base_slice.empty or peak_slice.empty:
            continue

        for col in prices_national_wide.columns:
            comcat_id = str(col).split("__", maxsplit=1)[0]
            base_mean = float(base_slice[col].mean())
            peak_max = float(peak_slice[col].max())
            peak_date = pd.Timestamp(peak_slice[col].idxmax()).strftime("%Y-%m-%d")
            pct_spike = 100.0 * (peak_max - base_mean) / base_mean if base_mean > 0 else 0.0
            rows.append(
                {
                    "event": str(ev["event"]),
                    "event_date": ev_date.strftime("%Y-%m-%d"),
                    "comcat_id": comcat_id,
                    "commodity_name": PIHPS_CATEGORIES.get(comcat_id, comcat_id),
                    "baseline_mean_idr": round(base_mean, 2),
                    "peak_idr": round(peak_max, 2),
                    "peak_date": peak_date,
                    "pct_change_to_peak": round(pct_spike, 2),
                }
            )
    return pd.DataFrame(
        rows,
        columns=[
            "event",
            "event_date",
            "comcat_id",
            "commodity_name",
            "baseline_mean_idr",
            "peak_idr",
            "peak_date",
            "pct_change_to_peak",
        ],
    )


def run_m2_pipeline(
    repo_root: Path,
    config_path: Path,
    *,
    run_id: str | None = None,
    spatial_city_commodities: tuple[str, ...] = ("cat_7", "cat_5", "cat_8"),
) -> Path:
    """Execute Milestone M2 domino discovery, VP5 permutation, VP6 walk-forward, VP7 seasonal."""
    cfg = load_config(config_path)
    processed_dir = repo_root / "data" / "processed" / "prices"
    ret_nat_path = processed_dir / "returns_national_wide.parquet"
    ret_prov_path = processed_dir / "returns_province_wide.parquet"
    ret_city_path = processed_dir / "returns_city_wide.parquet"
    px_nat_path = processed_dir / "prices_national_wide.parquet"

    for p in (ret_nat_path, ret_prov_path, ret_city_path, px_nat_path):
        if not p.is_file():
            raise FileNotFoundError(f"Missing M1 processed artifact: {p}")

    actual_run_id = run_id or f"m2_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    tracker = RunTracker(
        runs_dir=repo_root / "artifacts" / "runs",
        run_id=actual_run_id,
        stage="m2_domino",
        seed=cfg.seed,
        config_path=config_path,
        raw_manifest_path=repo_root / "data" / "raw" / "manifest.json",
        repo_root=repo_root,
    )

    try:
        ret_nat = _simplify_commodity_columns(pd.read_parquet(ret_nat_path))
        ret_prov = pd.read_parquet(ret_prov_path)
        ret_city = pd.read_parquet(ret_city_path)
        px_nat = pd.read_parquet(px_nat_path)

        granger_lag = int(cfg.prices.get("granger_lag", 5))
        xcorr_max_lag = int(cfg.prices.get("xcorr_max_lag", 10))
        fdr_alpha = float(cfg.prices.get("fdr_alpha", 0.05))
        n_perm = int(cfg.prices.get("permutation_runs", 20))
        ridge_alpha = float(cfg.prices.get("arx_ridge_alpha", 1.0))

        wf_cfg = cfg.evaluation["walk_forward"]
        initial_train_days = int(wf_cfg["initial_train_days"])

        holiday_rel = Path(str(cfg.prices.get("holiday_file", "data/external/hari_raya_id.csv")))
        holiday_path = holiday_rel if holiday_rel.is_absolute() else repo_root / holiday_rel
        holiday_df = load_holiday_calendar(holiday_path)

        # 1. Commodity Domino Network fit ONLY on initial_train_days (no test leakage).
        ret_nat_train = ret_nat.iloc[:initial_train_days]
        base_domino = discover_domino_network(
            ret_nat_train,
            granger_lag=granger_lag,
            xcorr_max_lag=xcorr_max_lag,
            fdr_alpha=fdr_alpha,
        )

        # Add readable commodity names.
        for df_e in (base_domino.edges_df,):
            if not df_e.empty:
                df_e["source_name"] = df_e["source"].map(lambda c: PIHPS_CATEGORIES.get(str(c), c))
                df_e["target_name"] = df_e["target"].map(lambda c: PIHPS_CATEGORIES.get(str(c), c))
        base_nodes = base_domino.nodes_df.copy()
        base_nodes["commodity_name"] = base_nodes["node"].map(
            lambda c: PIHPS_CATEGORIES.get(str(c), c)
        )

        edges_path = tracker.run_dir / "commodity_edges_raw_train.csv"
        nodes_path = tracker.run_dir / "commodity_nodes_raw_train.csv"
        base_domino.edges_df.to_csv(edges_path, index=False)
        base_nodes.to_csv(nodes_path, index=False)
        tracker.record_artifact("commodity_edges_raw", edges_path)
        tracker.record_artifact("commodity_nodes_raw", nodes_path)

        # 2. FR-B7 / VP7: Calendar & Holiday seasonal control fitted strictly on train split.
        ret_nat_adj = residualize_calendar_seasonality(
            ret_nat, train_end_idx=initial_train_days, holiday_df=holiday_df
        )
        adj_domino = discover_domino_network(
            ret_nat_adj.iloc[:initial_train_days],
            granger_lag=granger_lag,
            xcorr_max_lag=xcorr_max_lag,
            fdr_alpha=fdr_alpha,
        )
        adj_edges_path = tracker.run_dir / "commodity_edges_seasonal_adj_train.csv"
        adj_nodes_path = tracker.run_dir / "commodity_nodes_seasonal_adj_train.csv"
        adj_domino.edges_df.to_csv(adj_edges_path, index=False)
        adj_domino.nodes_df.to_csv(adj_nodes_path, index=False)
        tracker.record_artifact("commodity_edges_adj", adj_edges_path)
        tracker.record_artifact("commodity_nodes_adj", adj_nodes_path)

        vp7_summary = compare_seasonal_robustness(base_domino.edges_df, adj_domino.edges_df)

        # 3. VP5: Circular-shift permutation false discovery control on train split.
        vp5_summary = run_circular_shift_permutation_control(
            ret_nat_train,
            seed=cfg.seed,
            n_permutations=n_perm,
            granger_lag=granger_lag,
            fdr_alpha=fdr_alpha,
        )

        # 4. FR-B8 / VP6: Strict out-of-sample walk-forward evaluation (both raw & adjusted).
        wf_raw_df = evaluate_walk_forward_domino(
            ret_nat,
            base_domino.edges_df,
            initial_train_days=initial_train_days,
            lag=granger_lag,
            ridge_alpha=ridge_alpha,
        )
        wf_adj_df = evaluate_walk_forward_domino(
            ret_nat_adj,
            adj_domino.edges_df,
            initial_train_days=initial_train_days,
            lag=granger_lag,
            ridge_alpha=ridge_alpha,
        )
        wf_raw_df["commodity_name"] = wf_raw_df["target"].map(
            lambda c: PIHPS_CATEGORIES.get(str(c), c)
        )
        wf_adj_df["commodity_name"] = wf_adj_df["target"].map(
            lambda c: PIHPS_CATEGORIES.get(str(c), c)
        )
        wf_raw_path = tracker.run_dir / "walk_forward_raw.csv"
        wf_adj_path = tracker.run_dir / "walk_forward_seasonal_adj.csv"
        wf_raw_df.to_csv(wf_raw_path, index=False)
        wf_adj_df.to_csv(wf_adj_path, index=False)
        tracker.record_artifact("walk_forward_raw", wf_raw_path)
        tracker.record_artifact("walk_forward_seasonal_adj", wf_adj_path)

        # 5. FR-B6: Spatial Domino Network across Provinces (all 10 commodities) & Cities (subset).
        prov_summary_rows: list[dict[str, Any]] = []
        prov_top_edges_list: list[pd.DataFrame] = []
        prov_nodes_list: list[pd.DataFrame] = []

        for comcat_id in cfg.prices["commodities"]:
            sub_prov = _extract_commodity_slice(ret_prov, str(comcat_id)).iloc[:initial_train_days]
            if sub_prov.shape[1] < 2:
                continue
            sp_res = discover_domino_network(
                sub_prov,
                granger_lag=granger_lag,
                xcorr_max_lag=xcorr_max_lag,
                fdr_alpha=fdr_alpha,
            )
            prov_summary_rows.append(
                {
                    "comcat_id": comcat_id,
                    "commodity_name": PIHPS_CATEGORIES.get(str(comcat_id), comcat_id),
                    "n_provinces": sp_res.nodes_df.shape[0],
                    "pairs_tested": sp_res.total_pairs_tested,
                    "significant_edges": sp_res.significant_edges,
                    "top_leader_province": (
                        str(sp_res.nodes_df.iloc[0]["node"]) if not sp_res.nodes_df.empty else ""
                    ),
                    "top_leader_out_degree": (
                        int(sp_res.nodes_df.iloc[0]["out_degree"])
                        if not sp_res.nodes_df.empty
                        else 0
                    ),
                }
            )
            if not sp_res.edges_df.empty:
                sig_e = sp_res.edges_df.loc[sp_res.edges_df["significant"]].copy()
                sig_e["comcat_id"] = comcat_id
                prov_top_edges_list.append(sig_e)
            if not sp_res.nodes_df.empty:
                nd = sp_res.nodes_df.copy()
                nd["comcat_id"] = comcat_id
                prov_nodes_list.append(nd)

        prov_summary_df = pd.DataFrame(
            prov_summary_rows,
            columns=[
                "comcat_id",
                "commodity_name",
                "n_provinces",
                "pairs_tested",
                "significant_edges",
                "top_leader_province",
                "top_leader_out_degree",
            ],
        )
        prov_sum_path = tracker.run_dir / "spatial_province_summary.csv"
        prov_summary_df.to_csv(prov_sum_path, index=False)
        tracker.record_artifact("spatial_province_summary", prov_sum_path)

        if prov_top_edges_list:
            prov_edges_df = pd.concat(prov_top_edges_list, ignore_index=True)
            prov_edges_path = tracker.run_dir / "spatial_province_significant_edges.csv"
            prov_edges_df.to_csv(prov_edges_path, index=False)
            tracker.record_artifact("spatial_province_edges", prov_edges_path)

        if prov_nodes_list:
            prov_nodes_df = pd.concat(prov_nodes_list, ignore_index=True)
            prov_nodes_path = tracker.run_dir / "spatial_province_nodes.csv"
            prov_nodes_df.to_csv(prov_nodes_path, index=False)
            tracker.record_artifact("spatial_province_nodes", prov_nodes_path)

        # City-level spatial network for volatile benchmark commodities.
        city_summary_rows: list[dict[str, Any]] = []
        city_nodes_list: list[pd.DataFrame] = []
        city_edges_list: list[pd.DataFrame] = []
        for comcat_id in spatial_city_commodities:
            sub_city = _extract_commodity_slice(ret_city, comcat_id).iloc[:initial_train_days]
            if sub_city.shape[1] < 2:
                continue
            ct_res = discover_domino_network(
                sub_city,
                granger_lag=granger_lag,
                xcorr_max_lag=xcorr_max_lag,
                fdr_alpha=fdr_alpha,
            )
            city_summary_rows.append(
                {
                    "comcat_id": comcat_id,
                    "commodity_name": PIHPS_CATEGORIES.get(comcat_id, comcat_id),
                    "n_cities": ct_res.nodes_df.shape[0],
                    "pairs_tested": ct_res.total_pairs_tested,
                    "significant_edges": ct_res.significant_edges,
                    "top_leader_city": (
                        str(ct_res.nodes_df.iloc[0]["node"]) if not ct_res.nodes_df.empty else ""
                    ),
                    "top_leader_out_degree": (
                        int(ct_res.nodes_df.iloc[0]["out_degree"])
                        if not ct_res.nodes_df.empty
                        else 0
                    ),
                }
            )
            if not ct_res.edges_df.empty:
                sig_c = ct_res.edges_df.loc[ct_res.edges_df["significant"]].copy()
                sig_c["comcat_id"] = comcat_id
                city_edges_list.append(sig_c)
            if not ct_res.nodes_df.empty:
                cnd = ct_res.nodes_df.copy()
                cnd["comcat_id"] = comcat_id
                city_nodes_list.append(cnd)

        city_sum_df = pd.DataFrame(
            city_summary_rows,
            columns=[
                "comcat_id",
                "commodity_name",
                "n_cities",
                "pairs_tested",
                "significant_edges",
                "top_leader_city",
                "top_leader_out_degree",
            ],
        )
        city_sum_path = tracker.run_dir / "spatial_city_summary.csv"
        city_sum_df.to_csv(city_sum_path, index=False)
        tracker.record_artifact("spatial_city_summary", city_sum_path)

        if city_edges_list:
            city_edges_path = tracker.run_dir / "spatial_city_significant_edges.csv"
            pd.concat(city_edges_list, ignore_index=True).to_csv(city_edges_path, index=False)
            tracker.record_artifact("spatial_city_edges", city_edges_path)

        if city_nodes_list:
            city_nodes_path = tracker.run_dir / "spatial_city_nodes.csv"
            pd.concat(city_nodes_list, ignore_index=True).to_csv(city_nodes_path, index=False)
            tracker.record_artifact("spatial_city_nodes", city_nodes_path)

        # 6. Case study: Idul Fitri price movements across 2024-2026.
        event_df = build_holiday_event_study(px_nat, holiday_df)
        event_path = tracker.run_dir / "case_study_idul_fitri.csv"
        event_df.to_csv(event_path, index=False)
        tracker.record_artifact("case_study_idul_fitri", event_path)

        summary_metrics = {
            "train_rows": initial_train_days,
            "total_return_rows": len(ret_nat),
            "commodity_domino_raw": {
                "pairs_tested": base_domino.total_pairs_tested,
                "significant_edges": base_domino.significant_edges,
            },
            "commodity_domino_seasonal_adj": {
                "pairs_tested": adj_domino.total_pairs_tested,
                "significant_edges": adj_domino.significant_edges,
            },
            "vp5_permutation_control": vp5_summary,
            "vp6_walk_forward_raw": {
                "targets_with_triggers": int((wf_raw_df["n_triggers"] > 0).sum()),
                "targets_vp6_validated": int(wf_raw_df["vp6_validated"].sum()),
                "mean_skill_vs_ar_pct": round(float(wf_raw_df["skill_vs_ar_pct"].mean()), 4),
            },
            "vp6_walk_forward_seasonal_adj": {
                "targets_with_triggers": int((wf_adj_df["n_triggers"] > 0).sum()),
                "targets_vp6_validated": int(wf_adj_df["vp6_validated"].sum()),
                "mean_skill_vs_ar_pct": round(float(wf_adj_df["skill_vs_ar_pct"].mean()), 4),
            },
            "vp7_seasonal_robustness": vp7_summary,
            "spatial_province_commodities_analyzed": len(prov_summary_df),
            "spatial_city_commodities_analyzed": len(city_sum_df),
        }

        summary_path = tracker.run_dir / "m2_summary.json"
        summary_path.write_text(
            json.dumps(summary_metrics, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        tracker.record_artifact("m2_summary", summary_path)

        manifest_path = tracker.finish(metrics=summary_metrics)
        run_errors = verify_run_manifest(manifest_path)
        if run_errors:
            raise RuntimeError(f"M2 manifest verification failed: {run_errors}")
        return manifest_path
    except Exception as exc:
        tracker.fail(str(exc))
        raise
