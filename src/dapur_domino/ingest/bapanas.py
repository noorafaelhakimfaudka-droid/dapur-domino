"""Open Data Bapanas sample downloader (open datasets only)."""

from __future__ import annotations

from pathlib import Path

import requests

from dapur_domino.ingest.manifest import record_raw_artifact, write_bytes_immutable

USER_AGENT = "dapur-domino-research/0.1 (non-commercial academic portfolio)"
MAX_RESPONSE_BYTES = 50 * 1024 * 1024
BAPANAS_OPEN_ANOMALY_CSV_URL = (
    "https://data.badanpangan.go.id/download/document/dataset/505/1794466431.csv/csv"
)
LICENSE_NOTE = (
    "Open Data Badan Pangan Nasional (dataset berlabel 'Terbuka'; "
    "ketentuan penggunaan rinci belum dibaca karena tautan /privacy mengembalikan HTTP 500)."
)


def fetch_and_save_bapanas_open_sample(raw_dir: Path, manifest_path: Path) -> Path:
    """Download the public Bapanas food price anomaly CSV sample immutably."""
    resp = requests.get(
        BAPANAS_OPEN_ANOMALY_CSV_URL,
        headers={"User-Agent": USER_AGENT},
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.content
    if len(data) > MAX_RESPONSE_BYTES:
        raise ValueError(f"Bapanas response exceeded {MAX_RESPONSE_BYTES} bytes")

    rel_path = Path("prices") / "bapanas_anomaly_sample_2026_10.csv"
    target, sha256 = write_bytes_immutable(raw_dir, rel_path, data)
    record_raw_artifact(
        manifest_path,
        raw_dir,
        rel_path,
        source_id="D2_BAPANAS_OPEN",
        source_url=BAPANAS_OPEN_ANOMALY_CSV_URL,
        license_note=LICENSE_NOTE,
        sha256=sha256,
        size_bytes=len(data),
        metadata={"granularity": "monthly_index", "access_label": "Terbuka"},
    )
    return target
