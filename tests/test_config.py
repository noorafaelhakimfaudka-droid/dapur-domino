"""Tests for configuration loading and schema validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from dapur_domino.config import load_config


def test_default_config_loads_and_has_ten_pihps_commodities() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    cfg = load_config(repo_root / "configs" / "default.yaml")
    assert cfg.seed == 42
    assert cfg.prices["commodities"] == [f"cat_{i}" for i in range(1, 11)]
    assert cfg.prices["calendar"] == "business_days"


def test_load_config_rejects_missing_keys(tmp_path: Path) -> None:
    bad_cfg = tmp_path / "bad.yaml"
    bad_cfg.write_text("seed: 42\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Missing required config keys"):
        load_config(bad_cfg)


def test_load_config_rejects_bool_seed(tmp_path: Path) -> None:
    bad_cfg = tmp_path / "bad_seed.yaml"
    bad_cfg.write_text(
        "seed: true\nprices: {}\nrecipes: {}\nbridge: {}\nevaluation: {}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="'seed' must be an int"):
        load_config(bad_cfg)
