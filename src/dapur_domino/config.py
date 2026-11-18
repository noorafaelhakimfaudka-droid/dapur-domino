"""Configuration loading and validation for Dapur Domino."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REQUIRED_TOP_LEVEL_KEYS = ("seed", "prices", "recipes", "bridge", "evaluation")


@dataclass(frozen=True)
class AppConfig:
    """Validated top-level configuration loaded from YAML."""

    seed: int
    prices: dict[str, Any]
    recipes: dict[str, Any]
    bridge: dict[str, Any]
    evaluation: dict[str, Any]


def load_config(path: Path) -> AppConfig:
    """Load and validate a YAML configuration file.

    Args:
        path: Path to the YAML configuration file.

    Returns:
        Validated AppConfig instance.

    Raises:
        FileNotFoundError: If the configuration file does not exist.
        ValueError: If required keys or types are invalid.
    """
    if not path.is_file():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    if not isinstance(raw, dict):
        raise ValueError(f"Config root must be a mapping, got {type(raw).__name__}")

    missing = [key for key in REQUIRED_TOP_LEVEL_KEYS if key not in raw]
    if missing:
        raise ValueError(f"Missing required config keys: {missing}")

    seed = raw["seed"]
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError(f"'seed' must be an int, got {type(seed).__name__}")

    for section in ("prices", "recipes", "bridge", "evaluation"):
        if not isinstance(raw[section], dict):
            raise ValueError(f"'{section}' must be a mapping, got {type(raw[section]).__name__}")

    return AppConfig(
        seed=seed,
        prices=raw["prices"],
        recipes=raw["recipes"],
        bridge=raw["bridge"],
        evaluation=raw["evaluation"],
    )
