"""Public recipe dataset sample downloader (MIT-licensed prototype corpus)."""

from __future__ import annotations

import json
from pathlib import Path

import requests

from dapur_domino.ingest.manifest import record_raw_artifact, write_bytes_immutable

USER_AGENT = "dapur-domino-research/0.1 (non-commercial academic portfolio)"
MAX_RESPONSE_BYTES = 20 * 1024 * 1024
LORTHGYU_TRAIN_URL = (
    "https://huggingface.co/datasets/LorthGyu/indonesian-recipes/raw/main/data/train.jsonl"
)


def fetch_and_save_lorthgyu_sample(raw_dir: Path, manifest_path: Path) -> Path:
    """Download the open MIT-licensed LorthGyu/indonesian-recipes train.jsonl sample."""
    resp = requests.get(LORTHGYU_TRAIN_URL, headers={"User-Agent": USER_AGENT}, timeout=30.0)
    resp.raise_for_status()
    data = resp.content
    if len(data) > MAX_RESPONSE_BYTES:
        raise ValueError(f"Recipe response exceeded {MAX_RESPONSE_BYTES} bytes")

    # Validate JSONL lines before persisting.
    lines = [line for line in data.decode("utf-8").splitlines() if line.strip()]
    if not lines:
        raise ValueError("Downloaded recipe JSONL is empty")
    first = json.loads(lines[0])
    if not isinstance(first, dict) or "ingredients" not in first:
        raise ValueError("Unexpected recipe schema: missing 'ingredients'")

    rel_path = Path("recipes") / "lorthgyu_train.jsonl"
    target, sha256 = write_bytes_immutable(raw_dir, rel_path, data)
    record_raw_artifact(
        manifest_path,
        raw_dir,
        rel_path,
        source_id="D3_LORTHGYU_HF",
        source_url=LORTHGYU_TRAIN_URL,
        license_note="MIT (prototype/test corpus only; <1K rows; provenance unverified)",
        sha256=sha256,
        size_bytes=len(data),
        metadata={"row_count": len(lines)},
    )
    return target
