"""Single-command end-to-end pipeline reproduction script (NFR-1)."""

from __future__ import annotations

import argparse
from pathlib import Path

from dapur_domino.bridge.pipeline import run_m4_pipeline
from dapur_domino.prices.domino_pipeline import run_m2_pipeline
from dapur_domino.prices.pipeline import run_m1_pipeline
from dapur_domino.recipes.pipeline import run_m3_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Reproduce Dapur Domino M1-M4 pipeline.")
    parser.add_argument("--config", type=Path, default=Path("configs/default.yaml"))
    parser.add_argument("--tag", type=str, default=None)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    cfg_path = args.config if args.config.is_absolute() else repo_root / args.config
    suffix = f"_{args.tag}" if args.tag else ""

    m1 = run_m1_pipeline(repo_root, cfg_path, run_id=f"repro_m1{suffix}" if suffix else None)
    print(f"[1/4] M1 manifest: {m1}")
    m2 = run_m2_pipeline(repo_root, cfg_path, run_id=f"repro_m2{suffix}" if suffix else None)
    print(f"[2/4] M2 manifest: {m2}")
    m3 = run_m3_pipeline(repo_root, cfg_path, run_id=f"repro_m3{suffix}" if suffix else None)
    print(f"[3/4] M3 manifest: {m3}")
    m4 = run_m4_pipeline(repo_root, cfg_path, run_id=f"repro_m4{suffix}" if suffix else None)
    print(f"[4/4] M4 manifest: {m4}")
    print("Reproduce completed cleanly.")


if __name__ == "__main__":
    main()
