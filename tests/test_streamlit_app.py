"""Headless Streamlit UI smoke test verifying all 4 pages render without exceptions."""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from dapur_domino.bridge.pipeline import run_m4_pipeline
from dapur_domino.ingest.manifest import (
    compute_sha256_bytes,
    record_raw_artifact,
    write_bytes_immutable,
)
from dapur_domino.prices.domino_pipeline import run_m2_pipeline
from dapur_domino.prices.pipeline import run_m1_pipeline
from dapur_domino.recipes.pipeline import run_m3_pipeline


def _setup_ui_workspace(root: Path) -> Path:
    (root / "configs").mkdir(parents=True)
    (root / "data" / "external").mkdir(parents=True)
    (root / "data" / "raw" / "recipes").mkdir(parents=True)
    cfg_path = root / "configs" / "default.yaml"
    cfg_path.write_text(
        "\n".join(
            [
                "seed: 42",
                "prices:",
                "  commodities: [cat_5, cat_7, cat_8]",
                "  cleaning:",
                "    national_holiday_missing_threshold: 0.90",
                "    max_series_missing_pct: 0.20",
                "    max_ffill_gap: 3",
                "    outlier_abs_log_return: 0.65",
                "  stationarity_alpha: 0.05",
                "  min_stationarity_obs: 30",
                "  granger_lag: 2",
                "  xcorr_max_lag: 4",
                "  fdr_alpha: 0.05",
                "  permutation_runs: 3",
                "  arx_ridge_alpha: 1.0",
                "  holiday_file: data/external/hari_raya_id.csv",
                "recipes:",
                "  min_ingredient_freq: 5",
                "  min_pair_count: 5",
                "  min_npmi: 0.01",
                "  embedding:",
                "    dim: 16",
                "    window: 5",
                "    min_count: 5",
                "bridge:",
                "  weights:",
                "    similarity: 0.6",
                "    price: 0.4",
                "  mapping_file: data/external/ingredient_commodity_map.csv",
                "evaluation:",
                "  walk_forward:",
                "    initial_train_days: 70",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    repo_root = Path(__file__).resolve().parents[1]
    for ext_file in (
        "hari_raya_id.csv",
        "ingredient_synonyms.csv",
        "ingredient_commodity_map.csv",
        "bridge_eval_cases.csv",
        "culinary_substitutions_ref.csv",
    ):
        (root / "data" / "external" / ext_file).write_text(
            (repo_root / "data" / "external" / ext_file).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    raw_dir = root / "data" / "raw"
    manifest_path = raw_dir / "manifest.json"
    rng = np.random.default_rng(42)
    dates = pd.bdate_range("2025-01-01", periods=105)
    for comcat in ("cat_5", "cat_7", "cat_8"):
        rows = [
            {"no": "I", "name": "Semua Provinsi", "level": 0},
            {"no": "II", "name": "Jawa Tengah", "level": 1},
            {"no": 1, "name": "Kota Surakarta (Solo)", "level": 2},
        ]
        for lvl_i, v in enumerate(
            [
                40000.0 * np.exp(np.cumsum(rng.normal(0.0, 0.02, size=105)))
                for _ in range(3)
            ]
        ):
            for dt, val in zip(dates, v, strict=True):
                rows[lvl_i][dt.strftime("%d/%m/%Y")] = f"{int(round(val)):,}"
        b = json.dumps({"data": rows}).encode("utf-8")
        _, sha = write_bytes_immutable(raw_dir, f"prices/history/{comcat}/2025-01.json", b)
        record_raw_artifact(
            manifest_path,
            raw_dir,
            f"prices/history/{comcat}/2025-01.json",
            source_id="SYNTH",
            source_url="https://example.invalid",
            license_note="synthetic",
            sha256=sha,
            size_bytes=len(b),
        )
    train_rows = [
        {
            "title": f"Sambal {i}",
            "ingredients": [
                "5 buah cabe merah keriting",
                "3 buah cabe rawit",
                "4 siung bawang merah",
                "2 siung bawang putih",
                "1 sdt garam",
            ],
        }
        for i in range(30)
    ] + [
        {
            "title": f"Tumis {i}",
            "ingredients": [
                "5 buah cabe merah besar",
                "3 siung bawang merah",
                "2 siung bawang putih",
                "1 sdm minyak goreng",
                "1 sdt garam",
            ],
        }
        for i in range(30)
    ]
    for split_name in ("train.parquet", "eval.parquet"):
        pq_path = raw_dir / "recipes" / split_name
        pd.DataFrame(train_rows).to_parquet(pq_path, index=False)
        raw_bytes = pq_path.read_bytes()
        record_raw_artifact(
            manifest_path,
            raw_dir,
            f"recipes/{split_name}",
            source_id="SYNTH",
            source_url="https://example.invalid",
            license_note="synthetic",
            sha256=compute_sha256_bytes(raw_bytes),
            size_bytes=len(raw_bytes),
        )
    return cfg_path


def test_streamlit_app_renders_all_four_pages(tmp_path: Path) -> None:
    cfg_path = _setup_ui_workspace(tmp_path)
    run_m1_pipeline(tmp_path, cfg_path, run_id="ui_m1")
    run_m2_pipeline(tmp_path, cfg_path, run_id="ui_m2", spatial_city_commodities=("cat_7",))
    run_m3_pipeline(tmp_path, cfg_path, run_id="ui_m3")
    run_m4_pipeline(tmp_path, cfg_path, run_id="ui_m4")

    app_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "dapur_domino"
        / "app"
        / "streamlit_app.py"
    )
    prev_env = os.environ.get("DAPUR_DOMINO_ROOT")
    os.environ["DAPUR_DOMINO_ROOT"] = str(tmp_path)
    try:
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        assert not at.exception

        for page_label in (
            "Ganti bahan",
            "Isi kulkasku",
            "Efek domino",
            "Metodologi",
        ):
            at.radio[0].set_value(page_label).run()
            assert not at.exception
    finally:
        if prev_env is None:
            os.environ.pop("DAPUR_DOMINO_ROOT", None)
        else:
            os.environ["DAPUR_DOMINO_ROOT"] = prev_env
