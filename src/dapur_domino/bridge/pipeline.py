"""End-to-end Milestone M4 Bridge pipeline (FR-C1..FR-C4)."""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from dapur_domino.bridge.scoring import (
    compute_commodity_price_metrics,
    compute_mapping_coverage,
    load_commodity_mapping,
    score_price_aware_substitutions,
)
from dapur_domino.config import load_config
from dapur_domino.tracking import RunTracker, verify_run_manifest


def run_m4_pipeline(
    repo_root: Path,
    config_path: Path,
    *,
    run_id: str | None = None,
) -> Path:
    """Execute Milestone M4 price-aware substitution scoring and fixed-case evaluation."""
    cfg = load_config(config_path)
    px_dir = repo_root / "data" / "processed" / "prices"
    rec_dir = repo_root / "data" / "processed" / "recipes"

    px_nat_pq = px_dir / "prices_national_wide.parquet"
    ret_nat_pq = px_dir / "returns_national_wide.parquet"
    nodes_csv = rec_dir / "ingredient_nodes.csv"
    subs_pq = rec_dir / "ingredient_substitutions.parquet"

    map_rel = Path(str(cfg.bridge["mapping_file"]))
    map_path = map_rel if map_rel.is_absolute() else repo_root / map_rel
    eval_cases_path = repo_root / "data" / "external" / "bridge_eval_cases.csv"

    for p in (px_nat_pq, ret_nat_pq, nodes_csv, subs_pq, map_path, eval_cases_path):
        if not p.is_file():
            raise FileNotFoundError(f"Missing required M4 input: {p}")

    actual_run_id = run_id or f"m4_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    tracker = RunTracker(
        runs_dir=repo_root / "artifacts" / "runs",
        run_id=actual_run_id,
        stage="m4_bridge",
        seed=cfg.seed,
        config_path=config_path,
        raw_manifest_path=repo_root / "data" / "raw" / "manifest.json",
        repo_root=repo_root,
    )

    try:
        px_nat = pd.read_parquet(px_nat_pq)
        ret_nat = pd.read_parquet(ret_nat_pq)
        nodes_df = pd.read_csv(nodes_csv)
        subs_df = pd.read_parquet(subs_pq)
        mapping = load_commodity_mapping(map_path)

        weights = cfg.bridge["weights"]
        w_s = float(weights["similarity"])
        w_p = float(weights["price"])

        commodity_metrics = compute_commodity_price_metrics(px_nat, ret_nat, lookback_days=30)
        coverage = compute_mapping_coverage(nodes_df, mapping)

        # Evaluate fixed benchmark cases.
        case_rows: list[dict[str, Any]] = []
        case_summaries: list[dict[str, Any]] = []
        with eval_cases_path.open("r", encoding="utf-8") as fh:
            for case in csv.DictReader(fh):
                cid = case["case_id"].strip()
                target = case["target_ingredient"].strip().lower()
                scenario = case["scenario"].strip()
                ranked = score_price_aware_substitutions(
                    target,
                    subs_df,
                    mapping,
                    commodity_metrics,
                    w_similarity=w_s,
                    w_price=w_p,
                )
                mapped_count = sum(1 for r in ranked if r["price_status"] == "mapped")
                top_rec = ranked[0] if ranked else None
                case_summaries.append(
                    {
                        "case_id": cid,
                        "target_ingredient": target,
                        "scenario": scenario,
                        "n_candidates": len(ranked),
                        "n_price_mapped_candidates": mapped_count,
                        "top_candidate": top_rec["candidate"] if top_rec else None,
                        "top_price_status": top_rec["price_status"] if top_rec else None,
                        "top_combined_score": top_rec["combined_score"] if top_rec else None,
                        "top_recipe_sub_score": top_rec["recipe_sub_score"] if top_rec else None,
                    }
                )
                for rank_idx, rec in enumerate(ranked, start=1):
                    case_rows.append({"case_id": cid, "rank": rank_idx, **rec})

        processed_bridge_dir = repo_root / "data" / "processed" / "bridge"
        processed_bridge_dir.mkdir(parents=True, exist_ok=True)
        metrics_csv = processed_bridge_dir / "commodity_price_metrics.csv"
        commodity_metrics.to_csv(metrics_csv, index=False)
        tracker.record_artifact("commodity_price_metrics", metrics_csv, kind="processed_data")

        cases_detail_csv = tracker.run_dir / "bridge_eval_details.csv"
        pd.DataFrame(case_rows).to_csv(cases_detail_csv, index=False)
        tracker.record_artifact("bridge_eval_details", cases_detail_csv)

        cases_sum_csv = tracker.run_dir / "bridge_eval_summary.csv"
        pd.DataFrame(case_summaries).to_csv(cases_sum_csv, index=False)
        tracker.record_artifact("bridge_eval_summary", cases_sum_csv)

        m4_summary = {
            "weights": {"similarity": w_s, "price": w_p},
            "mapping_coverage_fr_c4": {
                "total_vocab_ingredients": coverage.total_vocab_ingredients,
                "mapped_vocab_ingredients": coverage.mapped_vocab_ingredients,
                "vocab_coverage_pct": coverage.vocab_coverage_pct,
                "total_recipe_mentions": coverage.total_recipe_mentions,
                "mapped_recipe_mentions": coverage.mapped_recipe_mentions,
                "mention_coverage_pct": coverage.mention_coverage_pct,
            },
            "n_eval_cases": len(case_summaries),
            "cases_with_candidates": sum(1 for c in case_summaries if c["n_candidates"] > 0),
        }
        sum_json = tracker.run_dir / "m4_summary.json"
        sum_json.write_text(
            json.dumps(m4_summary, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        tracker.record_artifact("m4_summary", sum_json)

        manifest_path = tracker.finish(metrics=m4_summary)
        run_errors = verify_run_manifest(manifest_path)
        if run_errors:
            raise RuntimeError(f"M4 manifest verification failed: {run_errors}")
        return manifest_path
    except Exception as exc:
        tracker.fail(str(exc))
        raise
