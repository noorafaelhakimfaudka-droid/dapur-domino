"""Tests for run manifest tracking, tamper detection (VP9), and resource measurement (VP10)."""

from __future__ import annotations

import json
from pathlib import Path

from dapur_domino.tracking import RunTracker, verify_run_manifest


def test_run_tracker_records_resources_and_detects_artifact_tampering(tmp_path: Path) -> None:
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("seed: 42\n", encoding="utf-8")
    runs_dir = tmp_path / "runs"

    tracker = RunTracker(
        runs_dir=runs_dir,
        run_id="run_test_001",
        stage="m1_test",
        seed=42,
        config_path=cfg,
    )
    out_file = tracker.run_dir / "stationarity.csv"
    out_file.write_text("col,val\na,1\n", encoding="utf-8")
    tracker.record_artifact("stationarity", out_file)
    manifest_path = tracker.finish({"retained_series": 10})

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["status"] == "completed"
    assert data["resources"]["duration_sec"] >= 0.0
    assert data["resources"]["peak_rss_mb"] > 0.0
    assert verify_run_manifest(manifest_path) == []

    # Tamper with artifact -> VP9 check must catch it.
    out_file.write_text("col,val\na,999\n", encoding="utf-8")
    errors = verify_run_manifest(manifest_path)
    assert len(errors) == 2
    assert any("sha256 mismatch" in err for err in errors)


def test_run_tracker_records_failed_runs(tmp_path: Path) -> None:
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("seed: 42\n", encoding="utf-8")
    tracker = RunTracker(
        runs_dir=tmp_path / "runs",
        run_id="run_fail_001",
        stage="m1_test",
        seed=42,
        config_path=cfg,
    )
    manifest_path = tracker.fail("simulated error")
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["status"] == "failed"
    assert data["error"] == "simulated error"
