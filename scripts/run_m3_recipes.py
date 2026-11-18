"""CLI entry point for Milestone M3 ingredient graph, embeddings, and VP2/VP3 eval."""

from __future__ import annotations

import argparse
from pathlib import Path

from dapur_domino.recipes.pipeline import run_m3_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Run M3 recipe graph & embedding pipeline.")
    parser.add_argument("--config", type=Path, default=Path("configs/default.yaml"))
    parser.add_argument("--run-id", type=str, default=None)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    cfg_path = args.config if args.config.is_absolute() else repo_root / args.config
    manifest_path = run_m3_pipeline(repo_root, cfg_path, run_id=args.run_id)
    print(f"M3 completed cleanly. Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
