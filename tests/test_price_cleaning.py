"""Tests for price cleaning, business-day calendar alignment, and outlier flagging (FR-B1)."""

from __future__ import annotations

import numpy as np

from dapur_domino.cleaning.prices import build_price_panel, clean_price_wide_panel


def test_build_price_panel_drops_weekends_and_normalizes_names() -> None:
    records = [
        {
            "date": "2026-10-02",  # Friday
            "comcat_id": "cat_7",
            "entity_name": "Kota Bandung ",
            "level": 2,
            "price_idr": 50000.0,
        },
        {
            "date": "2026-10-03",  # Saturday -> dropped
            "comcat_id": "cat_7",
            "entity_name": "Kota Bandung",
            "level": 2,
            "price_idr": 50000.0,
        },
        {
            "date": "2026-10-05",  # Monday
            "comcat_id": "cat_7",
            "entity_name": "Kota Bandung",
            "level": 2,
            "price_idr": 52000.0,
        },
    ]
    df = build_price_panel(records)
    assert len(df) == 2
    assert list(df["entity_name"]) == ["Kota Bandung", "Kota Bandung"]
    assert all(df["date"].dt.dayofweek < 5)


def test_clean_price_wide_panel_filters_holidays_missing_series_and_flags_outliers() -> None:
    # 5 business days (Mon Oct 5 to Fri Oct 9), 3 series at level 2.
    # Oct 7 is a national holiday (all 3 missing).
    # Series C is missing on >20% of open days -> excluded.
    # Series B has an extreme spike on Oct 8 -> flagged as outlier, NOT altered.
    days = ["2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09"]
    records = []
    series_prices = {
        "Kota A": [40000.0, 41000.0, None, 41500.0, 42000.0],
        "Kota B": [40000.0, 40500.0, None, 120000.0, 41000.0],
        "Kota C": [40000.0, None, None, None, 41000.0],
    }
    for city, vals in series_prices.items():
        for d, v in zip(days, vals, strict=True):
            records.append(
                {
                    "date": d,
                    "comcat_id": "cat_7",
                    "entity_name": city,
                    "level": 2,
                    "price_idr": v,
                }
            )

    long_df = build_price_panel(records)
    wide, series_audit, outlier_audit, report = clean_price_wide_panel(
        long_df,
        level_filter=2,
        national_holiday_missing_threshold=0.90,
        max_series_missing_pct=0.20,
        max_ffill_gap=2,
        outlier_abs_log_return=0.65,
    )

    assert report.holiday_dates_dropped == 1
    assert report.retained_series == 2
    assert report.excluded_series == 1
    assert ("cat_7", "Kota C") not in wide.columns
    assert np.isclose(float(wide.loc["2026-10-08", ("cat_7", "Kota B")]), 120000.0)  # type: ignore[arg-type]
    assert len(outlier_audit) >= 1
    assert "Kota B" in set(outlier_audit["entity_name"])
    assert len(series_audit) == 3
