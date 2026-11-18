"""Download and verify M0 raw data samples without overwriting existing raw files."""

from __future__ import annotations

import json
import time
from pathlib import Path

from dapur_domino.ingest.bapanas import fetch_and_save_bapanas_open_sample
from dapur_domino.ingest.manifest import verify_raw_manifest
from dapur_domino.ingest.pihps import (
    fetch_and_save_pihps_grid,
    fetch_and_save_pihps_references,
    parse_pihps_grid_records,
)
from dapur_domino.ingest.recipes_hf import fetch_and_save_lorthgyu_sample


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    raw_dir = repo_root / "data" / "raw"
    manifest_path = raw_dir / "manifest.json"

    print("1. Fetching PIHPS reference tables...")
    fetch_and_save_pihps_references(raw_dir, manifest_path, sleep_sec=0.5)

    print("2. Fetching PIHPS 1-month daerah sample (DKI Jakarta, Cabai Merah, 2026-10)...")
    daerah_path = fetch_and_save_pihps_grid(
        raw_dir,
        manifest_path,
        mode="daerah",
        start_date="2026-10-01",
        end_date="2026-10-31",
        comcat_id="cat_7",
        province_id="13",
        price_type_id=1,
        rel_filename="pihps_sample_daerah_cat7_prov13_2026_10.json",
    )
    time.sleep(0.5)

    print("3. Fetching PIHPS 1-week komoditas spatial sample (All cities, Cabai Merah)...")
    kom_path = fetch_and_save_pihps_grid(
        raw_dir,
        manifest_path,
        mode="komoditas",
        start_date="2026-10-01",
        end_date="2026-10-09",
        comcat_id="cat_7",
        province_id="",
        price_type_id=1,
        show_kota=True,
        rel_filename="pihps_sample_komoditas_cat7_2026_10_w1.json",
    )

    daerah_payload = json.loads(daerah_path.read_text(encoding="utf-8"))
    kom_payload = json.loads(kom_path.read_text(encoding="utf-8"))
    daerah_records = parse_pihps_grid_records(
        daerah_payload, mode="daerah", comcat_id="cat_7", province_id="13"
    )
    kom_records = parse_pihps_grid_records(kom_payload, mode="komoditas", comcat_id="cat_7")
    print(f"   Parsed PIHPS daerah sample records: {len(daerah_records)}")
    print(f"   Parsed PIHPS komoditas sample records: {len(kom_records)}")

    print("4. Fetching Bapanas open anomaly indicator CSV sample...")
    fetch_and_save_bapanas_open_sample(raw_dir, manifest_path)

    print("5. Fetching LorthGyu/indonesian-recipes (MIT) sample...")
    fetch_and_save_lorthgyu_sample(raw_dir, manifest_path)

    print("6. Verifying raw manifest integrity...")
    errors = verify_raw_manifest(manifest_path, raw_dir)
    if errors:
        raise RuntimeError(f"Manifest verification failed: {errors}")
    print("OK: all M0 samples verified cleanly.")


if __name__ == "__main__":
    main()
