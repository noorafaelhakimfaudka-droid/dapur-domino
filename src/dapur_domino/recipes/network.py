"""Ingredient co-occurrence, NPMI/Lift, graph construction, and Louvain (FR-A2, FR-A3)."""

from __future__ import annotations

from collections import Counter
from itertools import combinations
from typing import Any

import community as community_louvain
import networkx as nx
import numpy as np
import pandas as pd


def build_ingredient_cooccurrence_graph(
    recipe_ingredients: list[list[str]],
    *,
    min_ingredient_freq: int = 20,
    min_pair_count: int = 10,
    min_npmi: float = 0.05,
    seed: int = 42,
) -> tuple[nx.Graph[str], pd.DataFrame, pd.DataFrame]:
    """Build an undirected NPMI-weighted ingredient graph and detect flavor communities.

    Args:
        recipe_ingredients: List of normalized ingredient lists (one list per recipe).
        min_ingredient_freq: Minimum recipe count to keep an ingredient node.
        min_pair_count: Minimum co-occurrence recipe count for an edge.
        min_npmi: Minimum normalized PMI (>0 indicates positive association beyond chance).
        seed: Random seed for Louvain community detection.

    Returns:
        Tuple of (graph, nodes_df, edges_df).
    """
    unique_per_recipe: list[list[str]] = []
    item_counts: Counter[str] = Counter()
    for ings in recipe_ingredients:
        uniq = sorted(set(ings))
        if uniq:
            unique_per_recipe.append(uniq)
            item_counts.update(uniq)

    vocab = {item for item, cnt in item_counts.items() if cnt >= min_ingredient_freq}
    n_recipes = len(unique_per_recipe)
    if n_recipes == 0 or not vocab:
        return nx.Graph(), pd.DataFrame(), pd.DataFrame()

    pair_counts: Counter[tuple[str, str]] = Counter()
    for uniq in unique_per_recipe:
        filtered = [item for item in uniq if item in vocab]
        for a, b in combinations(filtered, 2):
            pair_counts[(a, b)] += 1

    edge_rows: list[dict[str, Any]] = []
    graph: nx.Graph[str] = nx.Graph()
    for item in sorted(vocab):
        graph.add_node(item, recipe_count=int(item_counts[item]))

    for (a, b), c_ab in pair_counts.items():
        if c_ab < min_pair_count:
            continue
        p_a = item_counts[a] / n_recipes
        p_b = item_counts[b] / n_recipes
        p_ab = c_ab / n_recipes
        lift = p_ab / (p_a * p_b)
        pmi = float(np.log2(lift))
        denom = float(-np.log2(p_ab))
        npmi = pmi / denom if denom > 0 else 0.0
        if npmi < min_npmi:
            continue

        graph.add_edge(
            a,
            b,
            weight=float(npmi),
            npmi=float(npmi),
            pmi=float(pmi),
            lift=float(lift),
            count=int(c_ab),
        )
        edge_rows.append(
            {
                "source": a,
                "target": b,
                "co_count": int(c_ab),
                "pmi": round(pmi, 6),
                "npmi": round(float(npmi), 6),
                "lift": round(float(lift), 6),
            }
        )

    partition: dict[str, int] = (
        community_louvain.best_partition(graph, weight="weight", random_state=seed)
        if graph.number_of_edges() > 0
        else {node: 0 for node in graph.nodes()}
    )

    node_rows: list[dict[str, Any]] = []
    for node in sorted(graph.nodes()):
        deg = int(graph.degree(node))
        w_deg = float(graph.degree(node, weight="weight"))
        cnt = int(item_counts[node])
        node_rows.append(
            {
                "ingredient": node,
                "recipe_count": cnt,
                "recipe_share_pct": round(100.0 * cnt / n_recipes, 4),
                "community_id": int(partition.get(node, -1)),
                "degree": deg,
                "weighted_degree": round(w_deg, 4),
            }
        )

    nodes_df = pd.DataFrame(
        node_rows,
        columns=[
            "ingredient",
            "recipe_count",
            "recipe_share_pct",
            "community_id",
            "degree",
            "weighted_degree",
        ],
    )
    if not nodes_df.empty:
        nodes_df = nodes_df.sort_values("recipe_count", ascending=False).reset_index(drop=True)

    edges_df = pd.DataFrame(
        edge_rows,
        columns=["source", "target", "co_count", "pmi", "npmi", "lift"],
    )
    if not edges_df.empty:
        edges_df = edges_df.sort_values("npmi", ascending=False).reset_index(drop=True)
    return graph, nodes_df, edges_df


def recommend_complementary_ingredients(
    available: list[str],
    graph: nx.Graph[str],
    *,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """Recommend complementary ingredients given currently available items (FR-A5a)."""
    avail_set = {item.strip().lower() for item in available if item.strip()}
    scores: dict[str, float] = {}
    matched_with: dict[str, list[str]] = {}

    for item in avail_set:
        if item not in graph:
            continue
        for nbr, attrs in graph[item].items():
            if nbr in avail_set:
                continue
            w = float(attrs.get("npmi", attrs.get("weight", 0.0)))
            scores[nbr] = scores.get(nbr, 0.0) + w
            matched_with.setdefault(nbr, []).append(item)

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
    return [
        {
            "ingredient": nbr,
            "complement_score": round(score, 4),
            "paired_with": sorted(matched_with[nbr]),
        }
        for nbr, score in ranked
    ]


def recommend_complements_conditional(
    available: list[str],
    graph: nx.Graph[str],
    total_recipes: int,
    *,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """Rank complementary ingredients using log P(cand) + mean log2 Lift(cand, obs)."""
    avail_set = {item.strip().lower() for item in available if item.strip()}
    if not avail_set or total_recipes <= 0:
        return []

    active_obs = [item for item in avail_set if item in graph]
    scores: dict[str, float] = {}
    matched_with: dict[str, list[str]] = {}

    for node, ndata in graph.nodes(data=True):
        if node in avail_set:
            continue
        cnt = int(ndata.get("recipe_count", 1))
        log_prior = float(np.log2(max(cnt, 1) / total_recipes))
        pmi_sum = 0.0
        matches: list[str] = []
        for obs in active_obs:
            if graph.has_edge(obs, node):
                pmi_sum += float(graph[obs][node].get("pmi", 0.0))
                matches.append(obs)
        if not matches:
            continue
        mean_pmi = pmi_sum / max(len(active_obs), 1)
        scores[str(node)] = log_prior + mean_pmi
        matched_with[str(node)] = sorted(matches)

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
    return [
        {
            "ingredient": cand,
            "conditional_log_score": round(score, 4),
            "paired_with": matched_with[cand],
        }
        for cand, score in ranked
    ]
