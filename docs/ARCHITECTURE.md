# ARCHITECTURE — Dapur Domino

## 1. Gambaran Sistem

Dapur Domino menggabungkan dua jalur analisis terpisah lalu menyatukannya melalui tabel pemetaan manual berversi dan antarmuka Streamlit lokal:

```
data/raw/prices/ (PIHPS 360 json) ──▶ M1 Cleaning & Stationarity ──▶ M2 Domino & Walk-Forward
                                                                             │
data/raw/recipes/ (66.419 + 3.496) ─▶ M3 Normalizer, NPMI, W2V  ────────────┼──▶ M4 Bridge ──▶ M5 Streamlit
                                                                             │
data/external/ (sinonim, hari raya, pemetaan komoditas) ─────────────────────┘
```

## 2. Pemisahan Tanggung Jawab Modul (`src/dapur_domino/`)

| Paket | Tanggung jawab | Status |
|---|---|---|
| `ingest/` | Pengambilan data PIHPS (TLS 1.2 adapter), Bapanas terbuka, resep publik, penyimpanan imutabel, SHA-256 raw manifest (`manifest.py`) | VERIFIED |
| `cleaning/` | Pembersihan harga hari kerja & audit outlier (`prices.py`); normalisasi teks bahan berbasis aturan + kamus (`ingredients.py`) | VERIFIED |
| `prices/` | Transformasi log-return & ADF/KPSS (`stationarity.py`), kontrol musiman/hari raya (`seasonality.py`), Granger + BH-FDR + graph (`domino.py`), orkestrasi M1 & M2 | VERIFIED |
| `recipes/` | Co-occurrence NPMI/PMI/Lift & komunitas Louvain (`network.py`), Word2Vec deterministik (`workers=1`) & skor substitusi (`embedding.py`), orkestrasi M3 | VERIFIED |
| `bridge/` | Pemetaan manual berversi ke 10 komoditas PIHPS, skor substitusi sadar-harga, deteksi `unmapped`, cakupan (`scoring.py`, `pipeline.py`) | VERIFIED |
| `evaluation/` | Walk-forward out-of-sample + Diebold–Mariano (`walk_forward.py`), hide-one-ingredient + Wilson CI + recall substitusi (`recipe_eval.py`) | VERIFIED |
| `app/` | Loader artefak + sanitasi input (`artifacts_loader.py`), Streamlit 4 halaman (`streamlit_app.py`) | TESTED |
| `tracking.py` | Pencatatan `manifest.json` per run (`running`/`completed`/`failed`), SHA-256 artefak, pengukuran durasi & puncak RAM aktual | VERIFIED |

## 3. Integritas Data & Auditabilitas

- Data mentah di `data/raw/` tidak pernah ditimpa (`write_bytes_immutable`).
- Setiap eksekusi pipeline menghasilkan folder terpisah di `artifacts/runs/<run_id>/manifest.json` yang mencatat SHA-256 config, SHA-256 `data/raw/manifest.json`, seed, metrik, puncak RSS RAM, durasi, dan SHA-256 setiap keluaran.
- Pemrosesan berjalan 100% lokal tanpa layanan LLM cloud atau transmisi data keluar.
