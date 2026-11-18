"""Sample 300 raw ingredient lines from eval.parquet for VP1 normalization audit."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from dapur_domino.cleaning.ingredients import load_synonym_map, normalize_ingredient_line


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    eval_pq = repo_root / "data" / "raw" / "recipes" / "eval.parquet"
    syn = load_synonym_map(repo_root / "data" / "external" / "ingredient_synonyms.csv")

    ings_col = pq.read_table(eval_pq, columns=["ingredients"])["ingredients"].to_pylist()
    all_lines: list[str] = [str(line) for recipe in ings_col for line in (recipe or [])]

    rng = np.random.default_rng(42)
    indices = rng.choice(len(all_lines), size=300, replace=False)

    rows = []
    for idx in sorted(int(i) for i in indices):
        raw = all_lines[idx]
        pred = normalize_ingredient_line(raw, syn)
        rows.append(
            {
                "eval_line_idx": idx,
                "raw_line": raw,
                "predicted_canonical": "|".join(pred),
            }
        )

    out_path = repo_root / "artifacts" / "vp1_eval_sample_300.csv"
    pd.DataFrame(rows).to_csv(out_path, index=False)
    print(f"Wrote 300-row VP1 sample to {out_path}")


if __name__ == "__main__":
    main()
