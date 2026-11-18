"""Run manifest tracking and measured resource usage (NFR-2, NFR-3, VP9, VP10)."""

from __future__ import annotations

import ctypes
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from dapur_domino.ingest.manifest import compute_sha256_file, resolve_within


def get_peak_rss_mb() -> float:
    """Measure process peak resident set size (RSS) in MiB on Windows or POSIX."""
    if sys.platform == "win32":
        from ctypes import wintypes

        class _ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = _ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(_ProcessMemoryCounters)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        k32_get_mem = getattr(kernel32, "K32GetProcessMemoryInfo", None)
        if k32_get_mem is None:
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            k32_get_mem = psapi.GetProcessMemoryInfo
        k32_get_mem.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_ProcessMemoryCounters),
            wintypes.DWORD,
        ]
        k32_get_mem.restype = wintypes.BOOL

        handle = kernel32.GetCurrentProcess()
        if k32_get_mem(handle, ctypes.byref(counters), counters.cb):
            peak_bytes = int(counters.PeakWorkingSetSize)
            return round(peak_bytes / (1024 * 1024), 3)
        return 0.0

    import resource

    usage = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    # Linux reports KiB, macOS reports bytes.
    if sys.platform == "darwin":
        return round(usage / (1024 * 1024), 3)
    return round(usage / 1024, 3)


def get_git_commit(repo_root: Path) -> str | None:
    """Return current HEAD commit hash if inside a git repository, else None."""
    if not (repo_root / ".git").exists():
        return None
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
        return out.strip()
    except (subprocess.SubprocessError, OSError):
        return None


@dataclass
class RunTracker:
    """Tracks a single pipeline execution and writes an auditable run manifest."""

    runs_dir: Path
    run_id: str
    stage: str
    seed: int
    config_path: Path
    raw_manifest_path: Path | None = None
    repo_root: Path | None = None
    _started_perf: float = field(default_factory=time.perf_counter, init=False)
    _manifest: dict[str, Any] = field(default_factory=dict, init=False)
    _run_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        self._run_dir = resolve_within(self.runs_dir, self.run_id)
        if self._run_dir.exists():
            raise FileExistsError(f"Run directory already exists: {self._run_dir}")
        self._run_dir.mkdir(parents=True, exist_ok=False)

        raw_sha = (
            compute_sha256_file(self.raw_manifest_path)
            if self.raw_manifest_path and self.raw_manifest_path.is_file()
            else None
        )
        self._manifest = {
            "schema_version": 1,
            "run_id": self.run_id,
            "stage": self.stage,
            "status": "running",
            "started_at_utc": datetime.now(UTC).isoformat(),
            "finished_at_utc": None,
            "seed": self.seed,
            "git_commit": get_git_commit(self.repo_root) if self.repo_root else None,
            "config": {
                "path": str(self.config_path),
                "sha256": compute_sha256_file(self.config_path),
            },
            "raw_manifest_sha256": raw_sha,
            "metrics": {},
            "resources": {},
            "artifacts": {},
            "error": None,
        }
        self._flush()

    @property
    def run_dir(self) -> Path:
        return self._run_dir

    @property
    def manifest_path(self) -> Path:
        return self._run_dir / "manifest.json"

    def record_artifact(self, name: str, path: Path, *, kind: str = "output") -> None:
        """Register an output artifact with its SHA-256 and byte size."""
        resolved = path.resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"Artifact does not exist: {path}")
        self._manifest["artifacts"][name] = {
            "path": str(path),
            "kind": kind,
            "size_bytes": resolved.stat().st_size,
            "sha256": compute_sha256_file(resolved),
        }
        self._flush()

    def finish(self, metrics: dict[str, Any] | None = None) -> Path:
        """Mark the run completed and record measured wall time and peak RSS."""
        elapsed = round(time.perf_counter() - self._started_perf, 4)
        self._manifest["status"] = "completed"
        self._manifest["finished_at_utc"] = datetime.now(UTC).isoformat()
        if metrics:
            self._manifest["metrics"].update(metrics)
        self._manifest["resources"] = {
            "duration_sec": elapsed,
            "peak_rss_mb": get_peak_rss_mb(),
        }
        self._flush()
        return self.manifest_path

    def fail(self, error_message: str) -> Path:
        """Mark the run failed without erasing partial diagnostics."""
        elapsed = round(time.perf_counter() - self._started_perf, 4)
        self._manifest["status"] = "failed"
        self._manifest["finished_at_utc"] = datetime.now(UTC).isoformat()
        self._manifest["error"] = error_message
        self._manifest["resources"] = {
            "duration_sec": elapsed,
            "peak_rss_mb": get_peak_rss_mb(),
        }
        self._flush()
        return self.manifest_path

    def _flush(self) -> None:
        tmp = self.manifest_path.with_name(".manifest.json.tmp")
        tmp.write_text(
            json.dumps(self._manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        tmp.replace(self.manifest_path)


def _resolve_manifest_artifact_path(
    raw_path: str,
    manifest_path: Path,
    repo_root: Path | None,
) -> Path:
    """Resolve an artifact path directly, or remap cross-platform repo paths cleanly."""
    p = Path(raw_path)
    if p.is_file() or repo_root is None:
        return p

    norm = raw_path.replace("\\", "/")
    for marker in ("data/processed/", "artifacts/runs/", "data/external/"):
        if marker in norm:
            rel_suffix = marker + norm.split(marker, 1)[1]
            try:
                candidate = resolve_within(repo_root, rel_suffix)
                if candidate.is_file():
                    return candidate
            except ValueError:
                pass

    sibling = manifest_path.parent / PurePosixPath(norm).name
    if sibling.is_file():
        return sibling
    return p


def verify_run_manifest(manifest_path: Path, *, repo_root: Path | None = None) -> list[str]:
    """Verify every recorded output artifact in a run manifest matches size and SHA-256."""
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    artifacts: dict[str, Any] = data.get("artifacts", {})
    for name, info in sorted(artifacts.items()):
        p = _resolve_manifest_artifact_path(str(info["path"]), manifest_path, repo_root)
        if not p.is_file():
            errors.append(f"{name}: missing artifact ({p})")
            continue
        actual_size = p.stat().st_size
        if actual_size != info.get("size_bytes"):
            errors.append(f"{name}: size mismatch ({actual_size} != {info.get('size_bytes')})")
        actual_sha = compute_sha256_file(p)
        if actual_sha != info.get("sha256"):
            errors.append(f"{name}: sha256 mismatch ({actual_sha} != {info.get('sha256')})")
    return errors
