"""Satu perintah untuk memperbarui data harga PIHPS Bank Indonesia & menjalankan ulang analisis."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import pandas as pd


def _update_config_end_month(config_path: Path, end_ym: str) -> bool:
    """Update history_end_month in configs/default.yaml if end_ym is newer."""
    text = config_path.read_text(encoding="utf-8")
    match = re.search(r'(history_end_month:\s*")(\d{4}-\d{2})(")', text)
    if not match:
        return False
    current_ym = match.group(2)
    if end_ym <= current_ym:
        return False
    updated = re.sub(
        r'(history_end_month:\s*")(\d{4}-\d{2})(")',
        rf"\g<1>{end_ym}\g<3>",
        text,
        count=1,
    )
    config_path.write_text(updated, encoding="utf-8")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tarik data harga terbaru dari PIHPS Bank Indonesia dan perbarui aplikasi."
    )
    parser.add_argument(
        "--end-month",
        type=str,
        default=None,
        help="Batas bulan akhir format YYYY-MM (otomatis bulan berjalan jika dikosongkan).",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    config_path = repo_root / "configs" / "default.yaml"
    today_ym = args.end_month or date.today().strftime("%Y-%m")

    if _update_config_end_month(config_path, today_ym):
        print(f"[1/4] Memperbarui history_end_month di configs/default.yaml -> {today_ym}")
    else:
        print(f"[1/4] Menggunakan bulan akhir: {today_ym}")

    steps = [
        (
            "[2/4] Menarik data harga terbaru dari server PIHPS Bank Indonesia...",
            [
                sys.executable,
                str(repo_root / "scripts" / "fetch_pihps_history.py"),
                "--end-month",
                today_ym,
                "--refresh-latest",
            ],
        ),
        (
            "[3/4] Memproses pembersihan harga & jaringan efek domino (M1 + M2)...",
            [sys.executable, str(repo_root / "scripts" / "run_m1_prices.py")],
        ),
        (
            "[3b/4] Memperbarui jaringan efek domino (M2)...",
            [sys.executable, str(repo_root / "scripts" / "run_m2_domino.py")],
        ),
        (
            "[4/4] Memperbarui skor jembatan harga & resep (M4)...",
            [sys.executable, str(repo_root / "scripts" / "run_m4_bridge.py")],
        ),
    ]

    for label, cmd in steps:
        print(label, flush=True)
        subprocess.run(cmd, cwd=repo_root, check=True)

    metrics_csv = repo_root / "data" / "processed" / "bridge" / "commodity_price_metrics.csv"
    if metrics_csv.is_file():
        df = pd.read_csv(metrics_csv)
        latest_dt = str(df["latest_date"].max())
        print("\n=== PEMBARUAN SELESAI ===")
        print(f"Tanggal harga terbaru: {latest_dt}")
        cols = ["comcat_id", "latest_date", "latest_price_idr", "pct_change_30d"]
        print(df[cols].to_string(index=False))


if __name__ == "__main__":
    main()
