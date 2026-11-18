"""Tests for immutable raw storage, path safety, and manifest tamper detection."""

from __future__ import annotations

from pathlib import Path

import pytest

from dapur_domino.ingest.manifest import (
    record_raw_artifact,
    resolve_within,
    verify_raw_manifest,
    write_bytes_immutable,
)


def test_resolve_within_rejects_traversal_and_absolute(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Path traversal"):
        resolve_within(tmp_path, "../outside.txt")
    with pytest.raises(ValueError, match="Absolute path"):
        resolve_within(tmp_path, tmp_path / "inside.txt")


def test_write_bytes_immutable_refuses_different_overwrite(tmp_path: Path) -> None:
    target, sha1 = write_bytes_immutable(tmp_path, "prices/sample.json", b'{"a":1}')
    assert target.is_file()

    # Identical bytes succeed idempotently.
    _, sha2 = write_bytes_immutable(tmp_path, "prices/sample.json", b'{"a":1}')
    assert sha1 == sha2

    # Different bytes must raise FileExistsError.
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        write_bytes_immutable(tmp_path, "prices/sample.json", b'{"a":2}')


def test_verify_raw_manifest_detects_tampering_and_deletion(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    manifest_path = raw_dir / "manifest.json"
    payload = b"hello,pihps"
    target, sha = write_bytes_immutable(raw_dir, "prices/test.csv", payload)
    record_raw_artifact(
        manifest_path,
        raw_dir,
        "prices/test.csv",
        source_id="TEST",
        source_url="https://example.invalid",
        license_note="test",
        sha256=sha,
        size_bytes=len(payload),
    )

    assert verify_raw_manifest(manifest_path, raw_dir) == []

    # Alter file content -> must detect size/hash mismatch.
    target.write_bytes(b"hello,tampered")
    errors = verify_raw_manifest(manifest_path, raw_dir)
    assert len(errors) == 2
    assert any("size mismatch" in e for e in errors)
    assert any("sha256 mismatch" in e for e in errors)

    # Delete file -> must detect missing file.
    target.unlink()
    errors_missing = verify_raw_manifest(manifest_path, raw_dir)
    assert errors_missing == ["prices/test.csv: missing file"]


def test_allow_refresh_preserves_refresh_history(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    manifest_path = raw_dir / "manifest.json"

    _, sha1 = write_bytes_immutable(raw_dir, "prices/history/cat_1/2026-11.json", b'{"d":1}')
    record_raw_artifact(
        manifest_path,
        raw_dir,
        "prices/history/cat_1/2026-11.json",
        source_id="D1_PIHPS",
        source_url="https://example.invalid",
        license_note="test",
        sha256=sha1,
        size_bytes=7,
    )

    _, sha2 = write_bytes_immutable(
        raw_dir, "prices/history/cat_1/2026-11.json", b'{"d":1,"d2":2}', allow_refresh=True
    )
    assert sha1 != sha2
    entry = record_raw_artifact(
        manifest_path,
        raw_dir,
        "prices/history/cat_1/2026-11.json",
        source_id="D1_PIHPS",
        source_url="https://example.invalid",
        license_note="test",
        sha256=sha2,
        size_bytes=14,
        allow_refresh=True,
    )
    assert entry["sha256"] == sha2
    assert len(entry["refresh_history"]) == 1
    assert entry["refresh_history"][0]["previous_sha256"] == sha1
    assert verify_raw_manifest(manifest_path, raw_dir) == []
