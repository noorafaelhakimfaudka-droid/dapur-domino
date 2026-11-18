"""End-to-end reproducibility test (VP8): running M1->M4 twice yields identical outputs."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from dapur_domino.bridge.pipeline import run_m4_pipeline
from dapur_domino.ingest.manifest import record_raw_artifact, write_bytes_immutable
from dapur_domino.prices.domino_pipeline import run_m2_pipeline
from dapur_domino.prices.pipeline import run_m1_pipeline
from dapur_domino.recipes.pipeline import run_m3_pipeline


def _build_synthetic_repo(root: Path) -> Path:
    """Populate a self-contained temporary workspace for full M1-M4 reproducibility."""
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
                "  permutation_runs: 5",
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

    # Copy small reference files from repo external.
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
        p_nat = 40000.0 * np.exp(np.cumsum(rng.normal(0.0, 0.02, size=105)))
        p_prov = 41000.0 * np.exp(np.cumsum(rng.normal(0.0, 0.02, size=105)))
        p_city = 42000.0 * np.exp(np.cumsum(rng.normal(0.0, 0.02, size=105)))
        rows = [
            {"no": "I", "name": "Semua Provinsi", "level": 0},
            {"no": "II", "name": "Jawa Tengah", "level": 1},
            {"no": 1, "name": "Kota Surakarta (Solo)", "level": 2},
        ]
        for dt, v0, v1, v2 in zip(dates, p_nat, p_prov, p_city, strict=True):
            k = dt.strftime("%d/%m/%Y")
            rows[0][k] = f"{int(round(v0)):,}"
            rows[1][k] = f"{int(round(v1)):,}"
            rows[2][k] = f"{int(round(v2)):,}"
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

    # Create synthetic train & eval recipe parquet files.
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
    eval_rows = train_rows[:12]

    for split_name, data_rows in [("train.parquet", train_rows), ("eval.parquet", eval_rows)]:
        pq_path = raw_dir / "recipes" / split_name
        pd.DataFrame(data_rows).to_parquet(pq_path, index=False)
        raw_bytes = pq_path.read_bytes()
        from dapur_domino.ingest.manifest import compute_sha256_bytes

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


def test_full_pipeline_reproducibility_vp8(tmp_path: Path) -> None:
    cfg_path = _build_synthetic_repo(tmp_path)

    # Run 1
    m1_a = run_m1_pipeline(tmp_path, cfg_path, run_id="r1_m1")
    m2_a = run_m2_pipeline(
        tmp_path, cfg_path, run_id="r1_m2", spatial_city_commodities=("cat_7",)
    )
    m3_a = run_m3_pipeline(tmp_path, cfg_path, run_id="r1_m3")
    m4_a = run_m4_pipeline(tmp_path, cfg_path, run_id="r1_m4")

    # Run 2
    m1_b = run_m1_pipeline(tmp_path, cfg_path, run_id="r2_m1")
    m2_b = run_m2_pipeline(
        tmp_path, cfg_path, run_id="r2_m2", spatial_city_commodities=("cat_7",)
    )
    m3_b = run_m3_pipeline(tmp_path, cfg_path, run_id="r2_m3")
    m4_b = run_m4_pipeline(tmp_path, cfg_path, run_id="r2_m4")

    for p_a, p_b in [(m1_a, m1_b), (m2_a, m2_b), (m3_a, m3_b), (m4_a, m4_b)]:
        d_a = json.loads(p_a.read_text(encoding="utf-8"))
        d_b = json.loads(p_b.read_text(encoding="utf-8"))
        assert d_a["metrics"] == d_b["metrics"]
