"""End-to-end Milestone M3 recipe normalization, graph, embedding, and evaluation (FR-A1..A5)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

from dapur_domino.cleaning.ingredients import load_synonym_map, normalize_ingredient_line
from dapur_domino.config import load_config
from dapur_domino.evaluation.recipe_eval import (
    evaluate_hide_one_ingredient,
    evaluate_substitution_recall,
)
from dapur_domino.ingest.manifest import verify_raw_manifest
from dapur_domino.recipes.embedding import rank_substitution_candidates, train_ingredient_embeddings
from dapur_domino.recipes.network import build_ingredient_cooccurrence_graph
from dapur_domino.tracking import RunTracker, verify_run_manifest


def normalize_recipe_corpus(
    parquet_path: Path,
    synonyms: dict[str, str],
) -> tuple[list[str], list[list[str]], int]:
    """Read a Parquet recipe split and normalize all ingredient lists."""
    table = pq.read_table(parquet_path, columns=["title", "ingredients"])
    titles_raw = table["title"].to_pylist()
    ings_raw = table["ingredients"].to_pylist()

    titles: list[str] = []
    norm_lists: list[list[str]] = []
    total_lines = 0
    for title, raw_ings in zip(titles_raw, ings_raw, strict=True):
        titles.append(str(title))
        items: list[str] = []
        seen: set[str] = set()
        for line in raw_ings or []:
            total_lines += 1
            for tok in normalize_ingredient_line(str(line), synonyms):
                if tok not in seen:
                    seen.add(tok)
                    items.append(tok)
        norm_lists.append(items)
    return titles, norm_lists, total_lines


def run_m3_pipeline(
    repo_root: Path,
    config_path: Path,
    *,
    run_id: str | None = None,
) -> Path:
    """Execute Milestone M3 ingredient graph, Word2Vec embeddings, and VP2/VP3 evaluation."""
    cfg = load_config(config_path)
    raw_dir = repo_root / "data" / "raw"
    raw_manifest = raw_dir / "manifest.json"
    raw_errors = verify_raw_manifest(raw_manifest, raw_dir)
    if raw_errors:
        raise RuntimeError(f"Raw manifest verification failed: {raw_errors}")

    train_pq = raw_dir / "recipes" / "train.parquet"
    eval_pq = raw_dir / "recipes" / "eval.parquet"
    syn_path = repo_root / "data" / "external" / "ingredient_synonyms.csv"
    sub_ref_path = repo_root / "data" / "external" / "culinary_substitutions_ref.csv"

    for req_file in (train_pq, eval_pq, syn_path):
        if not req_file.is_file():
            raise FileNotFoundError(f"Required M3 input not found: {req_file}")

    actual_run_id = run_id or f"m3_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    tracker = RunTracker(
        runs_dir=repo_root / "artifacts" / "runs",
        run_id=actual_run_id,
        stage="m3_recipes",
        seed=cfg.seed,
        config_path=config_path,
        raw_manifest_path=raw_manifest,
        repo_root=repo_root,
    )

    try:
        synonyms = load_synonym_map(syn_path)
        train_titles, train_ings, train_raw_lines = normalize_recipe_corpus(train_pq, synonyms)
        eval_titles, eval_ings, eval_raw_lines = normalize_recipe_corpus(eval_pq, synonyms)

        processed_dir = repo_root / "data" / "processed" / "recipes"
        processed_dir.mkdir(parents=True, exist_ok=True)

        train_norm_df = pd.DataFrame(
            {"title": train_titles, "normalized_ingredients": train_ings}
        )
        eval_norm_df = pd.DataFrame(
            {"title": eval_titles, "normalized_ingredients": eval_ings}
        )
        train_out_pq = processed_dir / "train_normalized.parquet"
        eval_out_pq = processed_dir / "eval_normalized.parquet"
        train_norm_df.to_parquet(train_out_pq, index=False)
        eval_norm_df.to_parquet(eval_out_pq, index=False)
        tracker.record_artifact("train_normalized_parquet", train_out_pq, kind="processed_data")
        tracker.record_artifact("eval_normalized_parquet", eval_out_pq, kind="processed_data")

        rec_cfg = cfg.recipes
        emb_cfg = rec_cfg.get("embedding", {})
        min_freq = int(rec_cfg.get("min_ingredient_freq", 20))
        min_pair = int(rec_cfg.get("min_pair_count", 10))
        min_npmi = float(rec_cfg.get("min_npmi", 0.05))

        graph, nodes_df, edges_df = build_ingredient_cooccurrence_graph(
            train_ings,
            min_ingredient_freq=min_freq,
            min_pair_count=min_pair,
            min_npmi=min_npmi,
            seed=cfg.seed,
        )

        nodes_csv = processed_dir / "ingredient_nodes.csv"
        edges_csv = processed_dir / "ingredient_edges.csv"
        nodes_df.to_csv(nodes_csv, index=False)
        edges_df.to_csv(edges_csv, index=False)
        tracker.record_artifact("ingredient_nodes", nodes_csv, kind="processed_data")
        tracker.record_artifact("ingredient_edges", edges_csv, kind="processed_data")

        w2v = train_ingredient_embeddings(
            train_ings,
            vector_size=int(emb_cfg.get("dim", 64)),
            window=int(emb_cfg.get("window", 10)),
            min_count=int(emb_cfg.get("min_count", min_freq)),
            seed=cfg.seed,
        )
        w2v_path = processed_dir / "ingredient_word2vec.model"
        w2v.save(str(w2v_path))
        tracker.record_artifact("ingredient_word2vec_model", w2v_path, kind="model")

        # Precompute top-10 substitution candidates for every node in W2V vocab.
        sub_rows: list[dict[str, Any]] = []
        for ing in sorted(w2v.wv.key_to_index.keys()):
            cands = rank_substitution_candidates(ing, w2v, graph, top_k=10)
            for rank_idx, cand in enumerate(cands, start=1):
                sub_rows.append(
                    {
                        "ingredient": ing,
                        "rank": rank_idx,
                        "candidate": cand["candidate"],
                        "cosine_sim": cand["cosine_sim"],
                        "direct_npmi": cand["direct_npmi"],
                        "sub_score": cand["sub_score"],
                    }
                )
        sub_df = pd.DataFrame(sub_rows)
        sub_pq = processed_dir / "ingredient_substitutions.parquet"
        sub_df.to_parquet(sub_pq, index=False)
        tracker.record_artifact("ingredient_substitutions", sub_pq, kind="processed_data")

        # VP2: Hide-one-ingredient on held-out eval.parquet (never seen during training).
        vp2_summary = evaluate_hide_one_ingredient(
            train_ings, eval_ings, graph, w2v, seed=cfg.seed, ks=(5, 10)
        )

        # VP3: Curated culinary substitution recall.
        vp3_summary: dict[str, Any] = {}
        if sub_ref_path.is_file():
            vp3_summary, vp3_details = evaluate_substitution_recall(
                sub_ref_path, w2v, graph, ks=(5, 10)
            )
            vp3_path = tracker.run_dir / "vp3_substitution_details.json"
            vp3_path.write_text(
                json.dumps(vp3_details, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            tracker.record_artifact("vp3_substitution_details", vp3_path)

        # Community summary ("keluarga rasa").
        comm_summary = (
            nodes_df.groupby("community_id")
            .agg(
                n_ingredients=("ingredient", "count"),
                top_ingredients=("ingredient", lambda s: ", ".join(s.head(8).tolist())),
            )
            .reset_index()
        )
        comm_path = tracker.run_dir / "flavor_communities.csv"
        comm_summary.to_csv(comm_path, index=False)
        tracker.record_artifact("flavor_communities", comm_path)

        m3_summary: dict[str, Any] = {
            "corpus": {
                "train_recipes": len(train_ings),
                "train_raw_lines": train_raw_lines,
                "eval_recipes": len(eval_ings),
                "eval_raw_lines": eval_raw_lines,
            },
            "graph": {
                "nodes": graph.number_of_nodes(),
                "edges": graph.number_of_edges(),
                "communities": int(nodes_df["community_id"].nunique()) if not nodes_df.empty else 0,
            },
            "word2vec_vocab": len(w2v.wv),
            "vp2_hide_one_ingredient": vp2_summary,
            "vp3_substitution_recall": vp3_summary,
        }

        summary_path = tracker.run_dir / "m3_summary.json"
        summary_path.write_text(
            json.dumps(m3_summary, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        tracker.record_artifact("m3_summary", summary_path)

        manifest_path = tracker.finish(metrics=m3_summary)
        run_errors = verify_run_manifest(manifest_path)
        if run_errors:
            raise RuntimeError(f"M3 manifest verification failed: {run_errors}")
        return manifest_path
    except Exception as exc:
        tracker.fail(str(exc))
        raise
