"""Unit tests for M3 ingredient normalization, NPMI graph, Word2Vec, and VP2 evaluation."""

from __future__ import annotations

from pathlib import Path

from dapur_domino.cleaning.ingredients import load_synonym_map, normalize_ingredient_line
from dapur_domino.evaluation.recipe_eval import evaluate_hide_one_ingredient
from dapur_domino.recipes.embedding import (
    rank_substitution_candidates,
    suggest_recipes_from_fridge,
    train_ingredient_embeddings,
)
from dapur_domino.recipes.network import (
    build_ingredient_cooccurrence_graph,
    recommend_complementary_ingredients,
)


def test_normalize_ingredient_line_handles_units_compounds_and_synonyms() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    syn = load_synonym_map(repo_root / "data" / "external" / "ingredient_synonyms.csv")

    assert normalize_ingredient_line("5 buah cabe merah keriting (haluskan)", syn) == [
        "cabai merah keriting"
    ]
    assert normalize_ingredient_line("Secukupnya garam, gula, penyedap rasa", syn) == [
        "garam",
        "gula pasir",
        "kaldu bubuk",
    ]
    assert normalize_ingredient_line("1 , 5 L air untuk merebus", syn) == ["air"]
    assert normalize_ingredient_line("2 jempol jahe, memarkan", syn) == ["jahe"]
    assert normalize_ingredient_line("10-15 cabe rawit. merah (sesuaikan)", syn) == [
        "cabai rawit merah"
    ]


def test_cooccurrence_graph_word2vec_and_vp2_on_synthetic_recipes() -> None:
    # Two distinct culinary clusters sharing garlic/salt, plus two interchangeable chilies.
    recipes: list[list[str]] = []
    for _ in range(25):
        recipes.append(["bawang merah", "bawang putih", "cabai merah besar", "garam", "kemiri"])
        recipes.append(["bawang merah", "bawang putih", "cabai merah keriting", "garam", "kemiri"])
        recipes.append(["tepung terigu", "gula pasir", "santan", "daun pandan", "garam"])

    graph, nodes_df, edges_df = build_ingredient_cooccurrence_graph(
        recipes, min_ingredient_freq=5, min_pair_count=5, min_npmi=0.01, seed=42
    )
    assert graph.number_of_nodes() >= 7
    assert not nodes_df.empty
    assert not edges_df.empty

    # Sweet cluster items should have higher NPMI with each other than with kemiri.
    assert graph.has_edge("tepung terigu", "daun pandan")
    assert not graph.has_edge("kemiri", "daun pandan")

    w2v = train_ingredient_embeddings(
        recipes, vector_size=16, window=5, min_count=5, seed=42, epochs=20
    )
    subs = rank_substitution_candidates("cabai merah besar", w2v, graph, top_k=5)
    assert any(s["candidate"] == "cabai merah keriting" for s in subs)

    comps = recommend_complementary_ingredients(["tepung terigu", "santan"], graph, top_k=3)
    assert any(c["ingredient"] in {"daun pandan", "gula pasir"} for c in comps)

    matches = suggest_recipes_from_fridge(
        ["bawang merah", "bawang putih", "cabai merah besar"],
        ["Sambal", "Kue"],
        [recipes[0], recipes[2]],
        top_k=2,
        min_overlap=2,
    )
    assert matches[0]["title"] == "Sambal"

    vp2 = evaluate_hide_one_ingredient(recipes, recipes[:10], graph, w2v, seed=42, ks=(3, 5))
    assert vp2["n_eval_recipes"] == 10
