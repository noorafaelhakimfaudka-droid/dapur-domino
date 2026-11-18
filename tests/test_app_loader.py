"""Tests for Streamlit app artifact loader and input validation (NFR-5)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from dapur_domino.app.artifacts_loader import (
    clean_display_title,
    extract_region_wide_slice,
    find_latest_completed_run,
    format_tanggal_indo,
    sanitize_ingredient_inputs,
)


def test_sanitize_ingredient_inputs_validates_and_bounds() -> None:
    cleaned = sanitize_ingredient_inputs([" Bawang Merah ", "cabai rawit", "bawang merah"])
    assert cleaned == ["bawang merah", "cabai rawit"]

    with pytest.raises(ValueError, match="Input bahan tidak valid"):
        sanitize_ingredient_inputs(["<script>alert(1)</script>"])

    # Enforces max_items cap.
    many = [f"bahan {i}" for i in range(40)]
    assert len(sanitize_ingredient_inputs(many, max_items=25)) == 25


def test_find_latest_completed_run_ignores_failed_runs(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    for rid, status, ts in [
        ("m2_old", "completed", "2026-11-18T01:00:00+00:00"),
        ("m2_new", "completed", "2026-11-18T02:00:00+00:00"),
        ("m2_fail", "failed", "2026-11-18T03:00:00+00:00"),
    ]:
        d = runs / rid
        d.mkdir(parents=True)
        (d / "manifest.json").write_text(
            json.dumps({"stage": "m2_domino", "status": status, "finished_at_utc": ts}),
            encoding="utf-8",
        )

    latest = find_latest_completed_run(runs, "m2_domino")
    assert latest is not None
    assert latest.name == "m2_new"


def test_extract_region_wide_slice() -> None:
    df = pd.DataFrame(
        {
            "cat_1__Jawa Barat": [15000.0],
            "cat_7__Jawa Barat": [60000.0],
            "cat_1__Aceh": [14500.0],
        }
    )
    sub = extract_region_wide_slice(df, "Jawa Barat")
    assert list(sub.columns) == ["cat_1__Jawa Barat", "cat_7__Jawa Barat"]


def test_clean_display_title_and_format_tanggal() -> None:
    assert clean_display_title("Tahu Bakso Goreng Endesss ❤️✨") == "Tahu Bakso Goreng Endes"
    assert format_tanggal_indo("2026-10-30") == "30 Okt 2026"
