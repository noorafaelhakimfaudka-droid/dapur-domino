"""End-to-end offline integration test for the M1 price pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from dapur_domino.ingest.manifest import record_raw_artifact, write_bytes_immutable
from dapur_domino.prices.pipeline import run_m1_pipeline
from dapur_domino.tracking import verify_run_manifest


def test_m1_pipeline_end_to_end_on_synthetic_history(tmp_path: Path) -> None:
    repo = tmp_path
    cfg_dir = repo / "configs"
    cfg_dir.mkdir(parents=True)
    cfg_path = cfg_dir / "default.yaml"
    cfg_path.write_text(
        "\n".join(
            [
                "seed: 42",
                "prices:",
                "  commodities: [cat_7]",
                "  cleaning:",
                "    national_holiday_missing_threshold: 0.90",
                "    max_series_missing_pct: 0.20",
                "    max_ffill_gap: 3",
                "    outlier_abs_log_return: 0.65",
                "  stationarity_alpha: 0.05",
                "  min_stationarity_obs: 30",
                "recipes: {}",
                "bridge: {}",
                "evaluation: {}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    raw_dir = repo / "data" / "raw"
    manifest_path = raw_dir / "manifest.json"

    rng = np.random.default_rng(7)
    dates = pd.bdate_range("2026-01-01", periods=60)
    prices_a = 40000.0 * np.exp(np.cumsum(rng.normal(0.0, 0.02, size=60)))
    prices_b = 50000.0 * np.exp(np.cumsum(rng.normal(0.0, 0.02, size=60)))

    row_a: dict[str, object] = {"no": "I", "name": "Semua Provinsi", "level": 0}
    row_b: dict[str, object] = {"no": 1, "name": "Kota Bandung", "level": 2}
    for dt, pa, pb in zip(dates, prices_a, prices_b, strict=True):
        key = dt.strftime("%d/%m/%Y")
        row_a[key] = f"{int(round(pa)):,}"
        row_b[key] = f"{int(round(pb)):,}"

    payload_bytes = json.dumps({"data": [row_a, row_b]}).encode("utf-8")
    _, sha = write_bytes_immutable(raw_dir, "prices/history/cat_7/2026-01.json", payload_bytes)
    record_raw_artifact(
        manifest_path,
        raw_dir,
        "prices/history/cat_7/2026-01.json",
        source_id="TEST",
        source_url="https://example.invalid",
        license_note="synthetic",
        sha256=sha,
        size_bytes=len(payload_bytes),
    )

    run_manifest = run_m1_pipeline(repo, cfg_path, run_id="m1_synth_001", levels=(0, 2))
    assert verify_run_manifest(run_manifest) == []

    summary = json.loads((run_manifest.parent / "m1_summary.json").read_text(encoding="utf-8"))
    assert summary["national"]["cleaning"]["retained_series"] == 1
    assert summary["city"]["cleaning"]["retained_series"] == 1
    assert summary["city"]["stationarity_vp4"]["return_stationary_both"] == 1
