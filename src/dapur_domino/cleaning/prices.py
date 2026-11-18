"""Price series cleaning, calendar alignment, missingness, and outlier audit (FR-B1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PriceCleaningReport:
    """Summary statistics produced while cleaning PIHPS price data."""

    raw_rows: int
    business_day_rows: int
    weekend_rows_dropped: int
    holiday_dates_dropped: int
    total_series: int
    retained_series: int
    excluded_series: int
    outlier_count: int


def build_price_panel(records: list[dict[str, Any]]) -> pd.DataFrame:
    """Convert raw parsed PIHPS records into a clean, deduplicated long DataFrame.

    Enforces business-day calendar (Mon-Fri, DEV-2) and normalizes names.
    """
    if not records:
        raise ValueError("Cannot build price panel from empty records")

    df = pd.DataFrame.from_records(records)
    required = {"date", "comcat_id", "entity_name", "level", "price_idr"}
    missing_cols = required - set(df.columns)
    if missing_cols:
        raise ValueError(f"Missing required record columns: {sorted(missing_cols)}")

    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d", errors="raise")
    df["entity_name"] = df["entity_name"].astype(str).str.strip()
    df["comcat_id"] = df["comcat_id"].astype(str).str.strip()
    df["level"] = df["level"].astype(int)
    df["price_idr"] = pd.to_numeric(df["price_idr"], errors="coerce")
    df.loc[df["price_idr"] <= 0, "price_idr"] = np.nan

    # Drop any accidental weekend entries (DEV-2: PIHPS is business-day only).
    is_weekday = df["date"].dt.dayofweek < 5
    df = df.loc[is_weekday].copy()

    # Deduplicate overlapping fetch windows deterministically.
    cleaned = (
        df.sort_values(["comcat_id", "level", "entity_name", "date"])
        .drop_duplicates(subset=["comcat_id", "level", "entity_name", "date"], keep="last")
        .reset_index(drop=True)
    )
    assert isinstance(cleaned, pd.DataFrame)
    return cleaned


def clean_price_wide_panel(
    long_df: pd.DataFrame,
    *,
    level_filter: int | None = None,
    national_holiday_missing_threshold: float = 0.90,
    max_series_missing_pct: float = 0.20,
    max_ffill_gap: int = 3,
    outlier_abs_log_return: float = 0.65,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, PriceCleaningReport]:
    """Pivot, align, filter missingness, and flag outliers in a wide price panel.

    Args:
        long_df: Long DataFrame from `build_price_panel`.
        level_filter: Optional PIHPS hierarchy level (0=national, 1=province, 2=city).
        national_holiday_missing_threshold: Drop dates where >= this fraction of series are NaN.
        max_series_missing_pct: Exclude series whose missingness exceeds this fraction.
        max_ffill_gap: Maximum consecutive missing market-open days to forward-fill (0 disables).
        outlier_abs_log_return: Threshold on |ln(P_t / P_{t-1})| for flagging jump outliers.

    Returns:
        Tuple of:
          - cleaned_prices: Wide DataFrame (index=date, columns=MultiIndex(comcat_id, entity_name))
          - series_audit: Per-series missingness and inclusion status
          - outlier_audit: Flagged single-day log-return spikes (not silently modified)
          - report: Summary counts
    """
    raw_rows = len(long_df)
    subset = (
        long_df.loc[long_df["level"] == level_filter].copy()
        if level_filter is not None
        else long_df.copy()
    )
    if subset.empty:
        raise ValueError(f"No records left after level_filter={level_filter}")

    # Reindex to strict Mon-Fri business-day grid without inventing weekend rows.
    min_date = subset["date"].min()
    max_date = subset["date"].max()
    b_days = pd.bdate_range(start=min_date, end=max_date, freq="B")

    wide = subset.pivot(
        index="date",
        columns=["comcat_id", "entity_name"],
        values="price_idr",
    ).reindex(b_days)
    wide.index.name = "date"
    business_day_rows = len(wide)

    # Identify market-closed national holidays where nearly all series are missing.
    date_missing_frac = wide.isna().mean(axis=1)
    holiday_mask = date_missing_frac >= national_holiday_missing_threshold
    holiday_dates_dropped = int(holiday_mask.sum())
    wide_open = wide.loc[~holiday_mask].copy()

    # Per-series missingness audit on market-open days BEFORE bounded ffill.
    raw_missing_pct = wide_open.isna().mean(axis=0)
    keep_mask = raw_missing_pct <= max_series_missing_pct

    series_audit = pd.DataFrame(
        {
            "comcat_id": [col[0] for col in wide_open.columns],
            "entity_name": [col[1] for col in wide_open.columns],
            "n_open_days": len(wide_open),
            "n_missing_raw": wide_open.isna().sum(axis=0).to_numpy(),
            "missing_pct_raw": raw_missing_pct.to_numpy(),
            "retained": keep_mask.to_numpy(),
        }
    )

    retained_wide = wide_open.loc[:, keep_mask].copy()
    if max_ffill_gap > 0 and not retained_wide.empty:
        retained_wide = retained_wide.ffill(limit=max_ffill_gap)

    # Outlier audit on raw log-returns (flag only; never silently alter raw prices).
    outlier_rows: list[dict[str, Any]] = []
    if not retained_wide.empty:
        log_ret = pd.DataFrame(
            np.log(retained_wide.where(retained_wide > 0).to_numpy(dtype=float)),
            index=retained_wide.index,
            columns=retained_wide.columns,
        ).diff()
        flagged = log_ret.abs() > outlier_abs_log_return
        for col in flagged.columns:
            bad_dates = flagged.index[flagged[col].fillna(False)]
            for dt in bad_dates:
                pos = retained_wide.index.get_loc(dt)
                prev_price = (
                    float(retained_wide.iloc[pos - 1][col])
                    if isinstance(pos, int) and pos > 0
                    else np.nan
                )
                curr_price = float(retained_wide.loc[dt, col])
                outlier_rows.append(
                    {
                        "date": dt.strftime("%Y-%m-%d"),
                        "comcat_id": col[0],
                        "entity_name": col[1],
                        "prev_price_idr": prev_price,
                        "price_idr": curr_price,
                        "log_return": float(log_ret.loc[dt, col]),
                    }
                )

    outlier_audit = pd.DataFrame(
        outlier_rows,
        columns=[
            "date",
            "comcat_id",
            "entity_name",
            "prev_price_idr",
            "price_idr",
            "log_return",
        ],
    )

    report = PriceCleaningReport(
        raw_rows=raw_rows,
        business_day_rows=business_day_rows,
        weekend_rows_dropped=0,
        holiday_dates_dropped=holiday_dates_dropped,
        total_series=len(wide_open.columns),
        retained_series=int(keep_mask.sum()),
        excluded_series=int((~keep_mask).sum()),
        outlier_count=len(outlier_audit),
    )
    return retained_wide, series_audit, outlier_audit, report
