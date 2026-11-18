"""Tests for Module C bridge scoring, unmapped honesty, and coverage reporting."""

from __future__ import annotations

import numpy as np
import pandas as pd

from dapur_domino.bridge.scoring import (
    LIMITATION_DISCLAIMER,
    compute_commodity_price_metrics,
    compute_mapping_coverage,
    score_price_aware_substitutions,
)


def test_bridge_scoring_and_unmapped_honesty() -> None:
    dates = pd.bdate_range("2026-08-01", periods=40)
    prices = pd.DataFrame(
        {
            "cat_7__Semua Provinsi": np.linspace(50000.0, 80000.0, 40),
            "cat_8__Semua Provinsi": np.full(40, 60000.0),
        },
        index=dates,
    )
    returns = pd.DataFrame(
        np.log(prices.to_numpy()).astype(float), index=dates, columns=prices.columns
    ).diff()

    metrics_df = compute_commodity_price_metrics(prices, returns, lookback_days=30)
    assert len(metrics_df) == 2

    subs_df = pd.DataFrame(
        [
            {
                "ingredient": "cabai merah besar",
                "rank": 1,
                "candidate": "cabai rawit",
                "cosine_sim": 0.80,
                "direct_npmi": 0.10,
                "sub_score": 0.72,
            },
            {
                "ingredient": "cabai merah besar",
                "rank": 2,
                "candidate": "paprika merah",
                "cosine_sim": 0.85,
                "direct_npmi": 0.0,
                "sub_score": 0.85,
            },
        ]
    )
    mapping = {
        "cabai merah besar": {
            "comcat_id": "cat_7",
            "commodity_name": "Cabai Merah",
            "mapping_note": "",
        },
        "cabai rawit": {
            "comcat_id": "cat_8",
            "commodity_name": "Cabai Rawit",
            "mapping_note": "",
        },
    }

    ranked = score_price_aware_substitutions(
        "cabai merah besar", subs_df, mapping, metrics_df, w_similarity=0.6, w_price=0.4
    )
    assert len(ranked) == 2
    mapped = ranked[0]
    unmapped = ranked[1]

    assert mapped["candidate"] == "cabai rawit"
    assert mapped["price_status"] == "mapped"
    assert mapped["combined_score"] == round(0.6 * 0.72 + 0.4 * 1.0, 4)
    assert mapped["disclaimer"] == LIMITATION_DISCLAIMER

    assert unmapped["candidate"] == "paprika merah"
    assert unmapped["price_status"] == "unmapped"
    assert unmapped["combined_score"] is None
    assert unmapped["latest_price_idr"] is None

    nodes = pd.DataFrame(
        [
            {"ingredient": "cabai merah besar", "recipe_count": 100},
            {"ingredient": "paprika merah", "recipe_count": 50},
            {"ingredient": "garam", "recipe_count": 850},
        ]
    )
    cov = compute_mapping_coverage(nodes, mapping)
    assert cov.mapped_vocab_ingredients == 1
    assert cov.total_vocab_ingredients == 3
    assert cov.mention_coverage_pct == 10.0
