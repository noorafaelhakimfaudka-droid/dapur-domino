"""End-to-end Milestone M1 price pipeline orchestration (FR-B1, FR-B2, VP4)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from dapur_domino.cleaning.prices import build_price_panel, clean_price_wide_panel
from dapur_domino.config import load_config
from dapur_domino.ingest.manifest import verify_raw_manifest
from dapur_domino.ingest.pihps import parse_pihps_grid_records
from dapur_domino.prices.stationarity import compute_log_returns, evaluate_panel_stationarity
from dapur_domino.tracking import RunTracker, verify_run_manifest


def load_raw_history_records(history_dir: Path) -> list[dict[str, Any]]:
    """Load and parse all raw PIHPS history JSON slices under history_dir."""
    if not history_dir.is_dir():
        raise FileNotFoundError(f"History directory not found: {history_dir}")

    files = sorted(history_dir.glob("cat_*/*.json"))
    if not files:
        raise FileNotFoundError(f"No raw PIHPS history slices found in {history_dir}")

    all_records: list[dict[str, Any]] = []
    for path in files:
        comcat_id = path.parent.name
        payload = json.loads(path.read_text(encoding="utf-8"))
        all_records.extend(
            parse_pihps_grid_records(payload, mode="komoditas", comcat_id=comcat_id)
        )
    return all_records


def run_m1_pipeline(
    repo_root: Path,
    config_path: Path,
    *,
    run_id: str | None = None,
    levels: tuple[int, ...] = (0, 1, 2),
) -> Path:
    """Execute M1 cleaning + stationarity pipeline and return run manifest path."""
    cfg = load_config(config_path)
    raw_dir = repo_root / "data" / "raw"
    raw_manifest = raw_dir / "manifest.json"
    raw_errors = verify_raw_manifest(raw_manifest, raw_dir)
    if raw_errors:
        raise RuntimeError(f"Raw manifest verification failed: {raw_errors}")

    actual_run_id = run_id or f"m1_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    tracker = RunTracker(
        runs_dir=repo_root / "artifacts" / "runs",
        run_id=actual_run_id,
        stage="m1_prices",
        seed=cfg.seed,
        config_path=config_path,
        raw_manifest_path=raw_manifest,
        repo_root=repo_root,
    )

    try:
        records = load_raw_history_records(raw_dir / "prices" / "history")
        long_df = build_price_panel(records)

        processed_dir = repo_root / "data" / "processed" / "prices"
        processed_dir.mkdir(parents=True, exist_ok=True)
        long_parquet = processed_dir / "pihps_long_panel.parquet"
        long_df.to_parquet(long_parquet, index=False)
        tracker.record_artifact("long_panel_parquet", long_parquet, kind="processed_data")

        cleaning_cfg = cfg.prices["cleaning"]
        alpha = float(cfg.prices.get("stationarity_alpha", 0.05))
        min_obs = int(cfg.prices.get("min_stationarity_obs", 30))

        level_names = {0: "national", 1: "province", 2: "city"}
        level_summaries: dict[str, Any] = {}

        for lvl in levels:
            lvl_name = level_names.get(lvl, f"level_{lvl}")
            wide, series_audit, outlier_audit, clean_report = clean_price_wide_panel(
                long_df,
                level_filter=lvl,
                national_holiday_missing_threshold=float(
                    cleaning_cfg["national_holiday_missing_threshold"]
                ),
                max_series_missing_pct=float(cleaning_cfg["max_series_missing_pct"]),
                max_ffill_gap=int(cleaning_cfg["max_ffill_gap"]),
                outlier_abs_log_return=float(cleaning_cfg["outlier_abs_log_return"]),
            )
            returns = compute_log_returns(wide)
            stat_df, stat_summary = evaluate_panel_stationarity(
                wide, returns, alpha=alpha, min_obs=min_obs
            )

            flat_cols = [f"{c[0]}__{c[1]}" for c in wide.columns]
            wide_out = wide.copy()
            wide_out.columns = pd.Index(flat_cols)
            wide_path = processed_dir / f"prices_{lvl_name}_wide.parquet"
            wide_out.to_parquet(wide_path)
            tracker.record_artifact(f"wide_prices_{lvl_name}", wide_path, kind="processed_data")

            ret_out = returns.copy()
            ret_out.columns = pd.Index(flat_cols)
            ret_path = processed_dir / f"returns_{lvl_name}_wide.parquet"
            ret_out.to_parquet(ret_path)
            tracker.record_artifact(f"wide_returns_{lvl_name}", ret_path, kind="processed_data")

            series_path = tracker.run_dir / f"series_audit_{lvl_name}.csv"
            series_audit.to_csv(series_path, index=False)
            tracker.record_artifact(f"series_audit_{lvl_name}", series_path)

            outlier_path = tracker.run_dir / f"outlier_audit_{lvl_name}.csv"
            outlier_audit.to_csv(outlier_path, index=False)
            tracker.record_artifact(f"outlier_audit_{lvl_name}", outlier_path)

            stat_path = tracker.run_dir / f"stationarity_{lvl_name}.csv"
            stat_df.to_csv(stat_path, index=False)
            tracker.record_artifact(f"stationarity_{lvl_name}", stat_path)

            level_summaries[lvl_name] = {
                "cleaning": {
                    "raw_rows": clean_report.raw_rows,
                    "business_day_rows": clean_report.business_day_rows,
                    "holiday_dates_dropped": clean_report.holiday_dates_dropped,
                    "total_series": clean_report.total_series,
                    "retained_series": clean_report.retained_series,
                    "excluded_series": clean_report.excluded_series,
                    "outlier_count": clean_report.outlier_count,
                },
                "stationarity_vp4": stat_summary,
            }

        summary_path = tracker.run_dir / "m1_summary.json"
        summary_path.write_text(
            json.dumps(level_summaries, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        tracker.record_artifact("m1_summary", summary_path)

        manifest_path = tracker.finish(metrics={"levels": level_summaries})
        run_errors = verify_run_manifest(manifest_path)
        if run_errors:
            raise RuntimeError(f"Run manifest verification failed: {run_errors}")
        return manifest_path
    except Exception as exc:
        tracker.fail(str(exc))
        raise
