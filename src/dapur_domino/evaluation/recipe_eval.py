"""Evaluation protocols for Module A: VP2 (hide-one-ingredient) and VP3 (substitution recall)."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np
from gensim.models import Word2Vec

from dapur_domino.recipes.embedding import rank_substitution_candidates
from dapur_domino.recipes.network import (
    recommend_complementary_ingredients,
    recommend_complements_conditional,
)


def wilson_confidence_interval(
    successes: int, total: int, z: float = 1.959963984540054
) -> tuple[float, float]:
    """Compute 95% Wilson score confidence interval for a binomial proportion."""
    if total <= 0:
        return 0.0, 0.0
    p = successes / total
    denom = 1.0 + (z * z) / total
    center = (p + (z * z) / (2.0 * total)) / denom
    half = (z * np.sqrt((p * (1.0 - p) + (z * z) / (4.0 * total)) / total)) / denom
    return max(0.0, float(center - half)), min(1.0, float(center + half))


def evaluate_hide_one_ingredient(
    train_recipes: list[list[str]],
    eval_recipes: list[list[str]],
    graph: nx.Graph[str],
    w2v_model: Word2Vec,
    *,
    seed: int = 42,
    ks: tuple[int, ...] = (5, 10),
) -> dict[str, Any]:
    """VP2: Hide one known ingredient per held-out recipe and score Top-K prediction.

    Compares three methods on the exact same test cases:
      1. Popularity baseline (most frequent training ingredients not already in recipe)
      2. NPMI graph complementarity score
      3. Word2Vec mean-context cosine similarity
    """
    vocab = set(graph.nodes())
    freq_counter: Counter[str] = Counter()
    for ings in train_recipes:
        for item in set(ings):
            if item in vocab:
                freq_counter[item] += 1
    ranked_popular = [item for item, _ in freq_counter.most_common()]

    rng = np.random.default_rng(seed)
    max_k = max(ks)
    test_cases: list[tuple[list[str], str]] = []
    for ings in eval_recipes:
        known = sorted({item for item in ings if item in vocab})
        if len(known) < 3:
            continue
        hidden_idx = int(rng.integers(0, len(known)))
        target = known[hidden_idx]
        observed = [item for idx, item in enumerate(known) if idx != hidden_idx]
        test_cases.append((observed, target))

    n_cases = len(test_cases)
    n_train = max(len(train_recipes), 1)
    hits: dict[str, dict[int, int]] = {
        "popularity": {k: 0 for k in ks},
        "npmi_graph": {k: 0 for k in ks},
        "cooccur_conditional": {k: 0 for k in ks},
        "word2vec_context": {k: 0 for k in ks},
    }

    # Pre-extract Skip-gram input and output (syn1neg) matrices for context prediction.
    wv_vocab = set(w2v_model.wv.key_to_index.keys())
    wv_keys = list(w2v_model.wv.key_to_index.keys())
    wv_in = w2v_model.wv.vectors
    wv_out = getattr(w2v_model, "syn1neg", None)
    key_to_idx = w2v_model.wv.key_to_index

    for observed, target in test_cases:
        obs_set = set(observed)

        # 1. Popularity baseline
        pop_preds = [item for item in ranked_popular if item not in obs_set][:max_k]

        # 2. Pure NPMI Graph complement
        npmi_recs = recommend_complementary_ingredients(observed, graph, top_k=max_k)
        npmi_preds = [str(r["ingredient"]) for r in npmi_recs]
        if len(npmi_preds) < max_k:
            seen_npmi = set(npmi_preds) | obs_set
            for p_item in ranked_popular:
                if p_item not in seen_npmi:
                    npmi_preds.append(p_item)
                    seen_npmi.add(p_item)
                    if len(npmi_preds) >= max_k:
                        break

        # 3. Conditional Co-occurrence (log P(cand) + mean PMI(cand, obs))
        cond_recs = recommend_complements_conditional(
            observed, graph, n_train, top_k=max_k
        )
        cond_preds = [str(r["ingredient"]) for r in cond_recs]
        if len(cond_preds) < max_k:
            seen_cond = set(cond_preds) | obs_set
            for p_item in ranked_popular:
                if p_item not in seen_cond:
                    cond_preds.append(p_item)
                    seen_cond.add(p_item)
                    if len(cond_preds) >= max_k:
                        break

        # 4. Word2Vec Skip-gram context prediction via syn1neg dot product
        obs_indices = [key_to_idx[item] for item in observed if item in wv_vocab]
        if obs_indices and wv_out is not None and len(wv_keys) > 0:
            ctx_vec = np.mean(wv_in[obs_indices], axis=0)
            scores = (wv_out @ ctx_vec).copy()
            for item in obs_set:
                if item in key_to_idx:
                    scores[key_to_idx[item]] = -np.inf
            k_eff = min(max_k, len(scores))
            top_indices = np.argpartition(scores, -k_eff)[-k_eff:]
            top_indices = top_indices[np.argsort(scores[top_indices])[::-1]]
            w2v_preds = [wv_keys[int(i)] for i in top_indices if np.isfinite(scores[int(i)])]
        else:
            w2v_preds = pop_preds

        for k in ks:
            if target in pop_preds[:k]:
                hits["popularity"][k] += 1
            if target in npmi_preds[:k]:
                hits["npmi_graph"][k] += 1
            if target in cond_preds[:k]:
                hits["cooccur_conditional"][k] += 1
            if target in w2v_preds[:k]:
                hits["word2vec_context"][k] += 1

    summary: dict[str, Any] = {"n_eval_recipes": n_cases, "methods": {}}
    for method, k_hits in hits.items():
        method_res: dict[str, Any] = {}
        for k in ks:
            h = k_hits[k]
            acc = round(100.0 * h / n_cases, 2) if n_cases else 0.0
            ci_lo, ci_hi = wilson_confidence_interval(h, n_cases)
            method_res[f"top_{k}"] = {
                "hits": h,
                "accuracy_pct": acc,
                "ci95_pct": [round(100.0 * ci_lo, 2), round(100.0 * ci_hi, 2)],
            }
        summary["methods"][method] = method_res
    return summary


def evaluate_substitution_recall(
    ref_csv_path: Path,
    w2v_model: Word2Vec,
    graph: nx.Graph[str],
    *,
    ks: tuple[int, ...] = (5, 10),
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """VP3: Evaluate Recall@K against an external curated culinary substitution list."""
    if not ref_csv_path.is_file():
        raise FileNotFoundError(f"Substitution reference file not found: {ref_csv_path}")

    max_k = max(ks)
    details: list[dict[str, Any]] = []
    hits_at_k: dict[int, int] = {k: 0 for k in ks}
    evaluated = 0
    skipped = 0

    with ref_csv_path.open("r", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            ing = row["ingredient"].strip().lower()
            expected = {
                s.strip().lower() for s in row["expected_substitutes"].split("|") if s.strip()
            }
            if ing not in w2v_model.wv:
                skipped += 1
                details.append(
                    {
                        "ingredient": ing,
                        "in_vocab": False,
                        "expected": sorted(expected),
                        "predicted_top10": [],
                        "hit_at_5": False,
                        "hit_at_10": False,
                    }
                )
                continue

            evaluated += 1
            cands = rank_substitution_candidates(ing, w2v_model, graph, top_k=max_k)
            pred_names = [str(c["candidate"]) for c in cands]

            row_detail: dict[str, Any] = {
                "ingredient": ing,
                "in_vocab": True,
                "expected": sorted(expected),
                "predicted_top10": pred_names,
            }
            for k in ks:
                hit = bool(set(pred_names[:k]) & expected)
                if hit:
                    hits_at_k[k] += 1
                row_detail[f"hit_at_{k}"] = hit
            details.append(row_detail)

    summary = {
        "total_reference_items": evaluated + skipped,
        "evaluated_in_vocab": evaluated,
        "skipped_oov": skipped,
        "recall": {
            f"recall_at_{k}": round(100.0 * hits_at_k[k] / evaluated, 2) if evaluated else 0.0
            for k in ks
        },
        "hits": {f"hits_at_{k}": hits_at_k[k] for k in ks},
    }
    return summary, details
