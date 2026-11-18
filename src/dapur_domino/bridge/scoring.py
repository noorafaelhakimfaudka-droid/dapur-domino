"""Module C: Price-aware culinary substitution bridge (FR-C1..FR-C4)."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

LIMITATION_DISCLAIMER = (
    "Kemiripan dihitung dari pola kemunculan bersama pada korpus resep, bukan jaminan "
    "kecocokan rasa, tekstur, atau nilai gizi. Data harga PIHPS hanya mencakup 10 komoditas "
    "strategis (hari kerja); bahan di luar 10 komoditas ditandai tanpa estimasi harga."
)


@dataclass(frozen=True)
class MappingCoverageReport:
    """Mapping coverage statistics (FR-C4)."""

    total_vocab_ingredients: int
    mapped_vocab_ingredients: int
    vocab_coverage_pct: float
    total_recipe_mentions: int
    mapped_recipe_mentions: int
    mention_coverage_pct: float


def load_commodity_mapping(path: Path) -> dict[str, dict[str, str]]:
    """Load manual versioned ingredient -> PIHPS commodity mapping (FR-C1)."""
    if not path.is_file():
        raise FileNotFoundError(f"Mapping file not found: {path}")
    mapping: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            ing = row["canonical_ingredient"].strip().lower()
            comcat = row["comcat_id"].strip()
            cname = row["commodity_name"].strip()
            if ing and comcat:
                mapping[ing] = {
                    "comcat_id": comcat,
                    "commodity_name": cname,
                    "mapping_note": row.get("mapping_note", "").strip(),
                }
    return mapping


def compute_commodity_price_metrics(
    prices_wide: pd.DataFrame,
    returns_wide: pd.DataFrame,
    *,
    lookback_days: int = 30,
) -> pd.DataFrame:
    """Compute latest price, recent % change, volatility, and price stability score per commodity.

    `prices_wide` should be national or single-region columns formatted `cat_X__Entity`.
    """
    if prices_wide.empty or len(prices_wide) <= lookback_days:
        raise ValueError(
            f"Need > {lookback_days} price rows, got {len(prices_wide)}"
        )

    latest_date = pd.Timestamp(prices_wide.index[-1]).strftime("%Y-%m-%d")
    rows: list[dict[str, Any]] = []

    for col in prices_wide.columns:
        comcat_id = str(col).split("__", maxsplit=1)[0]
        entity_name = str(col).split("__", maxsplit=1)[1] if "__" in str(col) else str(col)
        s_px = pd.to_numeric(prices_wide[col], errors="coerce").dropna()
        s_ret = (
            pd.to_numeric(returns_wide[col], errors="coerce").dropna()
            if col in returns_wide.columns
            else pd.Series(dtype=float)
        )
        if len(s_px) <= lookback_days:
            continue

        latest_px = float(s_px.iloc[-1])
        prev_px = float(s_px.iloc[-1 - lookback_days])
        pct_change = ((latest_px - prev_px) / prev_px) if prev_px > 0 else 0.0
        vol = float(s_ret.iloc[-lookback_days:].std(ddof=1)) if len(s_ret) >= 5 else 0.0

        # Bounded stability/affordability score in (0, 1]: penalizes spikes & volatility.
        price_score = float(np.exp(-max(0.0, pct_change)) * np.exp(-5.0 * max(0.0, vol)))
        rows.append(
            {
                "comcat_id": comcat_id,
                "region_name": entity_name,
                "latest_date": latest_date,
                "latest_price_idr": round(latest_px, 2),
                "pct_change_30d": round(100.0 * pct_change, 2),
                "volatility_30d": round(vol, 6),
                "price_stability_score": round(price_score, 4),
            }
        )

    return pd.DataFrame(rows)


def compute_mapping_coverage(
    nodes_df: pd.DataFrame,
    mapping: dict[str, dict[str, str]],
) -> MappingCoverageReport:
    """Compute both vocabulary-level and mention-weighted mapping coverage (FR-C4)."""
    if nodes_df.empty:
        return MappingCoverageReport(0, 0, 0.0, 0, 0, 0.0)

    ing_col = nodes_df["ingredient"].astype(str).str.lower()
    mapped_mask = ing_col.isin(mapping.keys())
    total_vocab = len(nodes_df)
    mapped_vocab = int(mapped_mask.sum())
    total_mentions = int(nodes_df["recipe_count"].sum())
    mapped_mentions = int(nodes_df.loc[mapped_mask, "recipe_count"].sum())

    return MappingCoverageReport(
        total_vocab_ingredients=total_vocab,
        mapped_vocab_ingredients=mapped_vocab,
        vocab_coverage_pct=round(100.0 * mapped_vocab / total_vocab, 2) if total_vocab else 0.0,
        total_recipe_mentions=total_mentions,
        mapped_recipe_mentions=mapped_mentions,
        mention_coverage_pct=(
            round(100.0 * mapped_mentions / total_mentions, 2) if total_mentions else 0.0
        ),
    )


def score_price_aware_substitutions(
    target_ingredient: str,
    substitutions_df: pd.DataFrame,
    mapping: dict[str, dict[str, str]],
    commodity_metrics_df: pd.DataFrame,
    *,
    w_similarity: float = 0.6,
    w_price: float = 0.4,
) -> list[dict[str, Any]]:
    """Combine recipe similarity with PIHPS price stability score (FR-C2, FR-C3).

    Unmapped candidates are NEVER assigned fabricated price scores; they are marked
    `price_status = "unmapped"` and retain `combined_score = None`.
    """
    target = target_ingredient.strip().lower()
    sub_rows = substitutions_df.loc[substitutions_df["ingredient"] == target].copy()
    if sub_rows.empty:
        return []

    metrics_by_cat = {
        str(r["comcat_id"]): r for _, r in commodity_metrics_df.iterrows()
    }
    target_map = mapping.get(target)
    target_price_info = (
        metrics_by_cat.get(target_map["comcat_id"]) if target_map is not None else None
    )

    results: list[dict[str, Any]] = []
    for _, row in sub_rows.iterrows():
        cand = str(row["candidate"]).strip().lower()
        sim_score = float(np.clip(float(row["sub_score"]), 0.0, 1.0))
        cand_map = mapping.get(cand)
        p_info = metrics_by_cat.get(cand_map["comcat_id"]) if cand_map is not None else None

        if cand_map is not None and p_info is not None:
            p_score = float(p_info["price_stability_score"])
            combined = round(w_similarity * sim_score + w_price * p_score, 4)
            results.append(
                {
                    "target_ingredient": target,
                    "target_price_idr": (
                        float(target_price_info["latest_price_idr"])
                        if target_price_info is not None
                        else None
                    ),
                    "target_pct_change_30d": (
                        float(target_price_info["pct_change_30d"])
                        if target_price_info is not None
                        else None
                    ),
                    "candidate": cand,
                    "recipe_sub_score": round(sim_score, 4),
                    "cosine_sim": round(float(row["cosine_sim"]), 4),
                    "direct_npmi": round(float(row["direct_npmi"]), 4),
                    "price_status": "mapped",
                    "comcat_id": cand_map["comcat_id"],
                    "commodity_name": cand_map["commodity_name"],
                    "latest_date": str(p_info["latest_date"]),
                    "latest_price_idr": float(p_info["latest_price_idr"]),
                    "pct_change_30d": float(p_info["pct_change_30d"]),
                    "volatility_30d": float(p_info["volatility_30d"]),
                    "price_stability_score": p_score,
                    "combined_score": combined,
                    "disclaimer": LIMITATION_DISCLAIMER,
                }
            )
        else:
            results.append(
                {
                    "target_ingredient": target,
                    "target_price_idr": (
                        float(target_price_info["latest_price_idr"])
                        if target_price_info is not None
                        else None
                    ),
                    "target_pct_change_30d": (
                        float(target_price_info["pct_change_30d"])
                        if target_price_info is not None
                        else None
                    ),
                    "candidate": cand,
                    "recipe_sub_score": round(sim_score, 4),
                    "cosine_sim": round(float(row["cosine_sim"]), 4),
                    "direct_npmi": round(float(row["direct_npmi"]), 4),
                    "price_status": "unmapped",
                    "comcat_id": None,
                    "commodity_name": None,
                    "latest_date": None,
                    "latest_price_idr": None,
                    "pct_change_30d": None,
                    "volatility_30d": None,
                    "price_stability_score": None,
                    "combined_score": None,
                    "disclaimer": LIMITATION_DISCLAIMER,
                }
            )

    # Sort mapped candidates first by combined_score, then unmapped by recipe_sub_score.
    results.sort(
        key=lambda r: (
            0 if r["combined_score"] is not None else 1,
            -(
                float(r["combined_score"])
                if r["combined_score"] is not None
                else float(r["recipe_sub_score"])
            ),
        )
    )
    return results
