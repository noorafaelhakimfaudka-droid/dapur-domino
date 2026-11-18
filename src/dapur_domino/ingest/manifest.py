"""Immutable raw artifact storage, SHA-256 hashing, and manifest verification."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def resolve_within(base_dir: Path, relative_path: Path | str) -> Path:
    """Resolve a relative path safely within base_dir, rejecting path traversal.

    Args:
        base_dir: Trusted root directory.
        relative_path: Untrusted relative path inside base_dir.

    Returns:
        Resolved path guaranteed to reside inside base_dir.

    Raises:
        ValueError: If the path is absolute or escapes base_dir.
    """
    rel = Path(relative_path)
    if rel.is_absolute():
        raise ValueError(f"Absolute path not permitted: {relative_path}")

    base_resolved = base_dir.resolve()
    target = (base_resolved / rel).resolve()
    try:
        target.relative_to(base_resolved)
    except ValueError as exc:
        raise ValueError(f"Path traversal detected: {relative_path}") from exc
    return target


def compute_sha256_bytes(data: bytes) -> str:
    """Return hex-encoded SHA-256 digest of bytes."""
    return hashlib.sha256(data).hexdigest()


def compute_sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of an existing file without loading all into RAM."""
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def write_bytes_immutable(
    base_dir: Path,
    relative_path: Path | str,
    data: bytes,
    *,
    allow_refresh: bool = False,
) -> tuple[Path, str]:
    """Write raw bytes without ever overwriting differing existing data unless allow_refresh=True.

    If the destination already exists with identical SHA-256 content, it is kept as-is.
    If it exists with different content and allow_refresh is False, FileExistsError is raised.
    """
    target = resolve_within(base_dir, relative_path)
    new_hash = compute_sha256_bytes(data)

    if target.exists():
        existing_hash = compute_sha256_file(target)
        if existing_hash == new_hash:
            return target, new_hash
        if not allow_refresh:
            raise FileExistsError(
                f"Refusing to overwrite existing raw file with different content: {target}"
            )

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target.with_name(f".{target.name}.tmp")
    tmp_path.write_bytes(data)
    tmp_path.replace(target)
    return target, new_hash


def load_manifest(manifest_path: Path) -> dict[str, Any]:
    """Load an existing manifest JSON file or initialize an empty ledger."""
    if not manifest_path.exists():
        return {"schema_version": 1, "artifacts": {}}
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "artifacts" not in raw:
        raise ValueError(f"Invalid manifest format at {manifest_path}")
    return raw


def record_raw_artifact(
    manifest_path: Path,
    base_dir: Path,
    relative_path: Path | str,
    *,
    source_id: str,
    source_url: str,
    license_note: str,
    sha256: str,
    size_bytes: int,
    metadata: dict[str, Any] | None = None,
    allow_refresh: bool = False,
) -> dict[str, Any]:
    """Record or verify a raw artifact entry in the raw manifest atomically."""
    resolved = resolve_within(base_dir, relative_path)
    key = resolved.relative_to(base_dir.resolve()).as_posix()

    manifest = load_manifest(manifest_path)
    artifacts: dict[str, Any] = manifest["artifacts"]

    existing = artifacts.get(key)
    refresh_history: list[dict[str, Any]] = []
    if existing is not None:
        refresh_history = list(existing.get("refresh_history", []))
        if existing.get("sha256") != sha256:
            if not allow_refresh:
                raise FileExistsError(
                    f"Manifest already records a different SHA-256 for {key}: "
                    f"{existing.get('sha256')} != {sha256}"
                )
            refresh_history.append(
                {
                    "previous_sha256": existing.get("sha256"),
                    "previous_size_bytes": existing.get("size_bytes"),
                    "previous_recorded_at_utc": existing.get("recorded_at_utc"),
                }
            )

    now_iso = datetime.now(UTC).isoformat()
    entry: dict[str, Any] = {
        "source_id": source_id,
        "source_url": source_url,
        "license_note": license_note,
        "sha256": sha256,
        "size_bytes": size_bytes,
        "recorded_at_utc": (
            existing["recorded_at_utc"]
            if existing is not None
            and "recorded_at_utc" in existing
            and existing.get("sha256") == sha256
            else now_iso
        ),
        "metadata": metadata or {},
    }
    if refresh_history:
        entry["refresh_history"] = refresh_history
    artifacts[key] = entry

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = manifest_path.with_name(f".{manifest_path.name}.tmp")
    tmp_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp_path.replace(manifest_path)
    return entry


def verify_raw_manifest(manifest_path: Path, base_dir: Path) -> list[str]:
    """Verify every recorded artifact exists on disk and matches its SHA-256 and size.

    Returns:
        List of discrepancy descriptions. Empty list means integrity check passed.
    """
    manifest = load_manifest(manifest_path)
    artifacts: dict[str, Any] = manifest.get("artifacts", {})
    errors: list[str] = []

    for rel_key, entry in sorted(artifacts.items()):
        try:
            file_path = resolve_within(base_dir, rel_key)
        except ValueError as exc:
            errors.append(f"{rel_key}: invalid path ({exc})")
            continue

        if not file_path.is_file():
            errors.append(f"{rel_key}: missing file")
            continue

        actual_size = file_path.stat().st_size
        expected_size = entry.get("size_bytes")
        if actual_size != expected_size:
            errors.append(f"{rel_key}: size mismatch ({actual_size} != {expected_size})")

        actual_hash = compute_sha256_file(file_path)
        expected_hash = entry.get("sha256")
        if actual_hash != expected_hash:
            errors.append(f"{rel_key}: sha256 mismatch ({actual_hash} != {expected_hash})")

    return errors
