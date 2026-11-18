"""Artifact loader, run discovery, and input sanitization for Streamlit Arena (FR-D5, NFR-5)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import networkx as nx
import pandas as pd

_SAFE_TOKEN_RE = re.compile(r"^[a-z0-9\s\-_]{1,60}$")
_ALAY_REPEAT_RE = re.compile(r"([a-zA-Z])\1{2,}")
_CLEAN_TITLE_RE = re.compile(r"[^a-zA-Z0-9\s(),/\-&']")

_BULAN_INDO = {
    1: "Jan",
    2: "Feb",
    3: "Mar",
    4: "Apr",
    5: "Mei",
    6: "Jun",
    7: "Jul",
    8: "Agu",
    9: "Sep",
    10: "Okt",
    11: "Nov",
    12: "Des",
}


def clean_display_title(raw_title: str) -> str:
    """Strip emojis, decorative symbols, and excessive letter repetition from recipe titles."""
    text = _CLEAN_TITLE_RE.sub(" ", str(raw_title))
    text = _ALAY_REPEAT_RE.sub(r"\1", text)
    text = re.sub(r"\s+", " ", text).strip(" -/,.")
    return text or "Resep Masakan"


def format_tanggal_indo(iso_date: str) -> str:
    """Format YYYY-MM-DD into human-friendly Indonesian date (e.g. '30 Okt 2026')."""
    try:
        ts = pd.Timestamp(str(iso_date))
        bulan = _BULAN_INDO.get(int(ts.month), str(ts.month))
        return f"{int(ts.day)} {bulan} {int(ts.year)}"
    except Exception:
        return str(iso_date)


def sanitize_ingredient_inputs(raw_items: list[str], *, max_items: int = 25) -> list[str]:
    """Validate and sanitize user-supplied ingredient strings (NFR-5)."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in raw_items[:max_items]:
        norm = re.sub(r"\s+", " ", str(item).strip().lower())
        if not norm:
            continue
        if not _SAFE_TOKEN_RE.match(norm):
            raise ValueError(
                f"Input bahan tidak valid (maks 60 karakter alfanumerik/spasi): {item!r}"
            )
        if norm not in seen:
            seen.add(norm)
            cleaned.append(norm)
    return cleaned


def find_latest_completed_run(runs_dir: Path, stage: str) -> Path | None:
    """Return the path to the newest completed run directory for a given stage."""
    if not runs_dir.is_dir():
        return None
    candidates: list[tuple[str, Path]] = []
    for run_dir in runs_dir.iterdir():
        if not run_dir.is_dir():
            continue
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("stage") == stage and data.get("status") == "completed":
            candidates.append((str(data.get("finished_at_utc", "")), run_dir))
    if not candidates:
        return None
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    return candidates[0][1]


def load_json_dict(path: Path) -> dict[str, Any]:
    """Load a JSON object file safely."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Expected JSON dict at {path}")
    return raw


def build_recipe_graph_from_csv(nodes_csv: Path, edges_csv: Path) -> tuple[nx.Graph[str], int]:
    """Reconstruct lightweight NetworkX graph from M3 processed CSV artifacts."""
    nodes_df = pd.read_csv(nodes_csv)
    edges_df = pd.read_csv(edges_csv)
    graph: nx.Graph[str] = nx.Graph()
    for _, row in nodes_df.iterrows():
        graph.add_node(
            str(row["ingredient"]),
            recipe_count=int(row["recipe_count"]),
            community_id=int(row["community_id"]),
        )
    for _, row in edges_df.iterrows():
        graph.add_edge(
            str(row["source"]),
            str(row["target"]),
            weight=float(row["npmi"]),
            npmi=float(row["npmi"]),
            pmi=float(row["pmi"]),
            lift=float(row["lift"]),
            count=int(row["co_count"]),
        )
    return graph, len(nodes_df)


def extract_region_wide_slice(
    wide_df: pd.DataFrame,
    region_name: str,
) -> pd.DataFrame:
    """Filter a `cat_X__Entity` wide panel to a single region across commodities."""
    suffix = f"__{region_name}"
    cols = [col for col in wide_df.columns if str(col).endswith(suffix)]
    return wide_df[cols].copy()
