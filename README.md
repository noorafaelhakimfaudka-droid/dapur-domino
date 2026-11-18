# Dapur Domino

Efek domino harga pangan × jaringan asosiasi bahan masakan Nusantara → rekomendasi substitusi bahan yang sadar harga.

> **Status:** Pipeline lengkap M0–M6 terverifikasi secara lokal (`1.141.526` baris PIHPS s.d. `18 Nov 2026` across `796` hari kerja + `69.915` resep Nusantara, Streamlit 4 halaman, tes `33/33` lulus). Lihat ringkasan siklus & keputusan pemodelan di [docs/MODEL_REVIEW.md](docs/MODEL_REVIEW.md), hasil empiris di [docs/EVALUATION_REPORT.md](docs/EVALUATION_REPORT.md), dan keterbatasan jujur di [docs/LIMITATIONS.md](docs/LIMITATIONS.md).

## Struktur repo

```
dapur-domino/
├── README.md
├── pyproject.toml            # dependensi & konfigurasi ruff/mypy/pytest
├── uv.lock                   # versi dependensi terkunci
├── Makefile                  # lint, typecheck, test, check, samples
├── configs/                  # config berversi (seed, ambang, bobot, pemetaan)
│   └── default.yaml
├── data/
│   ├── raw/{prices,recipes}/ # TIDAK PERNAH ditimpa; hash dicatat di manifest
│   ├── processed/            # dataset siap analisis
│   └── external/             # kalender hari raya, kamus sinonim, pemetaan
├── src/dapur_domino/
│   ├── ingest/               # pengunduhan/pemuatan data + hashing
│   ├── cleaning/             # FR-A1, FR-B1
│   ├── recipes/              # Modul A: co-occurrence, graph, embedding
│   ├── prices/               # Modul B: stasioneritas, lead-lag, FDR, graph
│   ├── bridge/               # Modul C: pemetaan & skor substitusi
│   ├── evaluation/           # VP1–VP10, baseline, walk-forward, lifecycle audit
│   └── app/                  # Modul D: Streamlit 4 halaman
├── notebooks/                # 01_eda_dan_pemodelan_dapur_domino.ipynb
├── scripts/                  # entry point CLI pipeline & update_data.py
├── tests/                    # 33 unit, integrasi, regresi, & lifecycle tests
├── artifacts/
│   ├── runs/                 # satu folder per run + manifest.json
│   └── analysis/             # tabel EDA, validasi, skenario model, & review
└── docs/                     # PRD, metodologi, evaluasi, review model, keterbatasan
```

## Dokumen Utama

| Dokumen | Status |
|---|---|
| [docs/MODEL_REVIEW.md](docs/MODEL_REVIEW.md) | **VERIFIED** (Ringkasan EDA, skenario model, evaluasi, & keputusan review) |
| [docs/PRD.md](docs/PRD.md) | Spesifikasi kebutuhan produk & kriteria validitas |
| [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) | Verifikasi sumber data & SHA-256 manifest |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Arsitektur sistem & pemisahan modul |
| [docs/METHODOLOGY.md](docs/METHODOLOGY.md) | Protokol statistik, ML, & evaluasi |
| [docs/EVALUATION_REPORT.md](docs/EVALUATION_REPORT.md) | Hasil terukur VP1–VP10 per `18 Nov 2026` |
| [docs/LIMITATIONS.md](docs/LIMITATIONS.md) | Keterbatasan data, metode, & lisensi |
| [docs/TRACEABILITY.md](docs/TRACEABILITY.md) | Pemetaan requirement → kode → tes → bukti |

## Menjalankan verifikasi, pembaruan data, & aplikasi lokal

```bash
uv sync --extra dev
uv run ruff check src tests scripts
uv run mypy src tests scripts
uv run pytest -v
uv run python scripts/run_ds_lifecycle_audit.py
uv run python scripts/update_data.py
uv run streamlit run src/dapur_domino/app/streamlit_app.py
```
