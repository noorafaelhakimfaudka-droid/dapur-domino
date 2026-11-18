"""CLI entry point for Milestone M1 price cleaning and VP4 stationarity audit."""

from __future__ import annotations

import argparse
from pathlib import Path

from dapur_domino.prices.pipeline import run_m1_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Run M1 price cleaning and VP4 stationarity.")
    parser.add_argument("--config", type=Path, default=Path("configs/default.yaml"))
    parser.add_argument("--run-id", type=str, default=None)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    cfg_path = args.config if args.config.is_absolute() else repo_root / args.config
    manifest_path = run_m1_pipeline(repo_root, cfg_path, run_id=args.run_id)
    print(f"M1 completed cleanly. Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
