"""CLI entrypoint to generate end-to-end Data Science lifecycle analysis tables."""

from __future__ import annotations

import json
from pathlib import Path

from dapur_domino.evaluation.lifecycle import run_ds_lifecycle_audit


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    summary = run_ds_lifecycle_audit(repo_root)
    print("Data Science lifecycle audit completed:")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
