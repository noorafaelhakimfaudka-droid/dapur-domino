"""CLI entry point for Milestone M2 domino effect analysis."""

from __future__ import annotations

import argparse
from pathlib import Path

from dapur_domino.prices.domino_pipeline import run_m2_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Run M2 domino analysis (FR-B3..B8, VP5..VP7).")
    parser.add_argument("--config", type=Path, default=Path("configs/default.yaml"))
    parser.add_argument("--run-id", type=str, default=None)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    cfg_path = args.config if args.config.is_absolute() else repo_root / args.config
    manifest_path = run_m2_pipeline(repo_root, cfg_path, run_id=args.run_id)
    print(f"M2 completed cleanly. Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
