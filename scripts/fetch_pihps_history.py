"""Resumable monthly PIHPS historical data downloader (10 commodities x N months)."""

from __future__ import annotations

import argparse
import calendar
import time
from datetime import date
from pathlib import Path

import requests

from dapur_domino.config import load_config
from dapur_domino.ingest.manifest import load_manifest, verify_raw_manifest
from dapur_domino.ingest.pihps import fetch_and_save_pihps_grid


def iter_months(start_ym: str, end_ym: str) -> list[tuple[str, str, str]]:
    """Return list of (YYYY-MM, start_date, end_date) inclusive."""
    s_year, s_month = map(int, start_ym.split("-"))
    e_year, e_month = map(int, end_ym.split("-"))
    cur = date(s_year, s_month, 1)
    end = date(e_year, e_month, 1)
    if cur > end:
        raise ValueError(f"start_month {start_ym} > end_month {end_ym}")

    months: list[tuple[str, str, str]] = []
    while cur <= end:
        last_day = calendar.monthrange(cur.year, cur.month)[1]
        ym = f"{cur.year:04d}-{cur.month:02d}"
        months.append((ym, f"{ym}-01", f"{ym}-{last_day:02d}"))
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)
    return months


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch monthly PIHPS history immutably.")
    parser.add_argument("--config", type=Path, default=Path("configs/default.yaml"))
    parser.add_argument("--start-month", type=str, default=None)
    parser.add_argument("--end-month", type=str, default=None)
    parser.add_argument("--sleep-sec", type=float, default=0.35)
    parser.add_argument(
        "--refresh-latest",
        action="store_true",
        help="Re-download the final month (end_month) to capture newly published daily prices.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    cfg = load_config(repo_root / args.config if not args.config.is_absolute() else args.config)
    raw_dir = repo_root / "data" / "raw"
    manifest_path = raw_dir / "manifest.json"

    start_ym = args.start_month or str(cfg.prices["history_start_month"])
    end_ym = args.end_month or str(cfg.prices["history_end_month"])
    commodities: list[str] = list(cfg.prices["commodities"])
    price_type_id = int(cfg.prices.get("price_type_id", 1))
    months = iter_months(start_ym, end_ym)

    manifest = load_manifest(manifest_path)
    recorded_keys = set(manifest.get("artifacts", {}).keys())

    total = len(commodities) * len(months)
    done = 0
    downloaded = 0
    skipped = 0

    for comcat_id in commodities:
        for ym, s_date, e_date in months:
            done += 1
            rel_file = f"history/{comcat_id}/{ym}.json"
            manifest_key = f"prices/{rel_file}"
            target_path = raw_dir / manifest_key
            is_latest_refresh = bool(args.refresh_latest and ym == end_ym)
            if target_path.is_file() and manifest_key in recorded_keys and not is_latest_refresh:
                skipped += 1
                continue

            for attempt in range(1, 4):
                try:
                    fetch_and_save_pihps_grid(
                        raw_dir,
                        manifest_path,
                        mode="komoditas",
                        start_date=s_date,
                        end_date=e_date,
                        comcat_id=comcat_id,
                        province_id="",
                        price_type_id=price_type_id,
                        show_kota=True,
                        rel_filename=rel_file,
                        allow_refresh=is_latest_refresh,
                    )
                    break
                except requests.RequestException as exc:
                    if attempt == 3:
                        raise RuntimeError(
                            f"Failed fetching {comcat_id} {ym} after 3 attempts: {exc}"
                        ) from exc
                    time.sleep(2.0 * attempt)
            downloaded += 1
            if downloaded % 10 == 0 or done == total:
                print(
                    f"[{done}/{total}] downloaded={downloaded} skipped={skipped} "
                    f"(latest: {comcat_id} {ym})",
                    flush=True,
                )
            time.sleep(args.sleep_sec)

    errors = verify_raw_manifest(manifest_path, raw_dir)
    if errors:
        raise RuntimeError(f"Raw manifest integrity errors: {errors}")
    print(f"Completed: downloaded={downloaded}, skipped={skipped}, total={total}. Manifest OK.")


if __name__ == "__main__":
    main()
