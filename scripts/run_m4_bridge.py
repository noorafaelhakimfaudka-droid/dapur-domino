"""CLI entry point for Milestone M4 bridge scoring and fixed-case evaluation."""

from __future__ import annotations

import argparse
from pathlib import Path

from dapur_domino.bridge.pipeline import run_m4_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Run M4 price-aware substitution bridge.")
    parser.add_argument("--config", type=Path, default=Path("configs/default.yaml"))
    parser.add_argument("--run-id", type=str, default=None)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    cfg_path = args.config if args.config.is_absolute() else repo_root / args.config
    manifest_path = run_m4_pipeline(repo_root, cfg_path, run_id=args.run_id)
    print(f"M4 completed cleanly. Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
