"""Ingredient Word2Vec embedding, substitution ranking, and recipe matcher (FR-A4, FR-A5)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import networkx as nx

if TYPE_CHECKING:
    from gensim.models import Word2Vec


def train_ingredient_embeddings(
    recipe_ingredients: list[list[str]],
    *,
    vector_size: int = 64,
    window: int = 10,
    min_count: int = 20,
    seed: int = 42,
    epochs: int = 10,
) -> Word2Vec:
    """Train a deterministic Skip-gram Word2Vec model on ingredient sets (`workers=1`)."""
    from gensim.models import Word2Vec

    sentences = [sorted(set(ings)) for ings in recipe_ingredients if len(set(ings)) >= 2]
    if not sentences:
        raise ValueError("Cannot train Word2Vec on empty recipe corpus")

    return Word2Vec(
        sentences=sentences,
        vector_size=vector_size,
        window=window,
        min_count=min_count,
        sg=1,
        workers=1,
        seed=seed,
        epochs=epochs,
    )


def rank_substitution_candidates(
    ingredient: str,
    model: Word2Vec,
    graph: nx.Graph[str],
    *,
    top_k: int = 10,
    search_pool: int = 50,
) -> list[dict[str, Any]]:
    """Rank statistical substitution candidates (high context similarity, low direct co-occurrence).

    Args:
        ingredient: Target canonical ingredient.
        model: Trained gensim Word2Vec model.
        graph: NPMI co-occurrence graph (used to discount direct complements).
        top_k: Number of top candidates to return.
        search_pool: Number of nearest neighbors from Word2Vec to rerank.
    """
    key = ingredient.strip().lower()
    if key not in model.wv:
        return []

    neighbors = model.wv.most_similar(key, topn=search_pool)
    candidates: list[dict[str, Any]] = []
    for cand, cos_sim in neighbors:
        npmi = 0.0
        if graph.has_edge(key, cand):
            npmi = float(graph[key][cand].get("npmi", 0.0))
        # Discount direct complements (items that strongly co-occur in the same dish).
        sub_score = float(cos_sim) * (1.0 - max(0.0, npmi))
        candidates.append(
            {
                "candidate": cand,
                "cosine_sim": round(float(cos_sim), 4),
                "direct_npmi": round(npmi, 4),
                "sub_score": round(sub_score, 4),
            }
        )

    candidates.sort(key=lambda row: float(row["sub_score"]), reverse=True)
    return candidates[:top_k]


def suggest_recipes_from_fridge(
    available: list[str],
    recipe_titles: list[str],
    recipe_ingredients: list[list[str]],
    *,
    top_k: int = 10,
    min_overlap: int = 2,
) -> list[dict[str, Any]]:
    """Suggest recipes matching available ingredients (`Isi Kulkasku`, FR-A5a)."""
    avail_set = {item.strip().lower() for item in available if item.strip()}
    if not avail_set:
        return []

    matches: list[dict[str, Any]] = []
    for title, ings in zip(recipe_titles, recipe_ingredients, strict=True):
        req = set(ings)
        if not req:
            continue
        have = req & avail_set
        if len(have) < min_overlap:
            continue
        missing = sorted(req - avail_set)
        coverage = len(have) / len(req)
        matches.append(
            {
                "title": title,
                "coverage_pct": round(100.0 * coverage, 1),
                "matched_count": len(have),
                "missing_count": len(missing),
                "matched": sorted(have),
                "missing": missing,
            }
        )

    matches.sort(
        key=lambda r: (-float(r["coverage_pct"]), int(r["missing_count"]), -int(r["matched_count"]))
    )
    return matches[:top_k]
