"""Tests for PIHPS grid payload parsing using synthetic fixtures."""

from __future__ import annotations

from datetime import date

import pytest

from dapur_domino.ingest.pihps import (
    parse_pihps_date,
    parse_pihps_grid_records,
    parse_pihps_price,
)


def test_parse_pihps_price_variants() -> None:
    assert parse_pihps_price("58,450") == 58450.0
    assert parse_pihps_price("-") is None
    assert parse_pihps_price("") is None
    assert parse_pihps_price(None) is None
    with pytest.raises(ValueError, match="Negative price"):
        parse_pihps_price("-100")


def test_parse_pihps_date() -> None:
    assert parse_pihps_date("01/10/2026") == date(2026, 10, 1)


def test_parse_pihps_grid_records_daerah_and_komoditas() -> None:
    payload = {
        "data": [
            {
                "no": "I",
                "name": "Cabai Merah",
                "level": 1,
                "01/10/2026": "58,450",
                "02/10/2026": "-",
            },
            {
                "no": 1,
                "name": "Cabai Merah Keriting ",
                "level": 2,
                "01/10/2026": "61,700",
                "02/10/2026": "62,000",
            },
        ]
    }
    records = parse_pihps_grid_records(
        payload, mode="daerah", comcat_id="cat_7", province_id="13"
    )
    assert len(records) == 4
    assert records[0]["entity_name"] == "Cabai Merah"
    assert records[0]["price_idr"] == 58450.0
    assert records[1]["price_idr"] is None
    assert records[2]["entity_name"] == "Cabai Merah Keriting"
    assert records[2]["level"] == 2
    assert records[2]["date"] == "2026-10-01"

    with pytest.raises(ValueError, match="mode must be"):
        parse_pihps_grid_records(payload, mode="invalid")
