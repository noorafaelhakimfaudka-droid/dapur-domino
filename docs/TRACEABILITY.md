# TRACEABILITY

Pemetaan requirement PRD → kode → tes → bukti. Diperbarui setiap perubahan material.
Status: `NOT_STARTED` · `IMPLEMENTED` · `TESTED` · `VERIFIED` · `FAILED` · `BLOCKED`.

## Ringkasan Status Milestone (M0–M6)

| Milestone | Status | Catatan |
|---|---|---|
| M0 — Fondasi & verifikasi data | **VERIFIED** | `379` berkas mentah (`370` histori PIHPS `2023-11` s.d. `2026-11` + `9` ref/sampel/resep) di-hash di `data/raw/manifest.json` |
| M1 — Pipeline data harga | **VERIFIED** | Run `m1_20261118T080609Z` (`1.141.526` baris, `796` hari kerja pasar buka) |
| M2 — Analisis domino | **VERIFIED** | Run `m2_20261118T080707Z` (VP5=3,44%, VP6 296 hari uji, VP7=100% bertahan) |
| M3 — Graph bahan | **VERIFIED** | Run `m3_20261118T070540Z` (VP1=90,33%, VP2=45,50% vs 40,88%, VP3=24,0%) |
| M4 — Jembatan sadar-harga | **VERIFIED** | Run `m4_20261118T080802Z` (cakupan 27,74% mention, per `2026-11-18`) |
| M5 — Aplikasi & audit | **VERIFIED** | Streamlit 4 halaman navigasi atas lolos `AppTest` pada data sintetis & nyata |
| M6 — Dokumentasi, EDA, & Review Model | **VERIFIED** | Audit siklus lengkap Data Science (`artifacts/analysis/`), `MODEL_REVIEW.md`, & Notebook |

## Pemetaan Requirement Fungsional & Non-Fungsional

| ID | Deskripsi singkat | Implementasi | Tes | Status | Bukti |
|---|---|---|---|---|---|
| FR-B1 | Pembersihan harga, kalender hari kerja, outlier | `cleaning/prices.py`, `prices/pipeline.py` | `test_price_cleaning.py`, `test_m1_pipeline.py` | **VERIFIED** | `m1_20261118T080609Z` |
| FR-B2 / VP4 | Log-return & ADF/KPSS | `prices/stationarity.py` | `test_stationarity.py` | **VERIFIED** | 90,0% nas / 98,24% prov / 98,00% kota lulus keduanya |
| FR-B3..FR-B5 | Xcorr, Granger, BH-FDR, graph komoditas | `prices/domino.py`, `prices/domino_pipeline.py` | `test_domino.py` | **VERIFIED** | `m2_20261118T080707Z` (50/90 mentah, 56/90 musiman) |
| FR-B6 | Graph spasial provinsi & kota | `prices/domino_pipeline.py` | `test_domino.py` | **VERIFIED** | 34 prov × 10 komoditas; 105 kota × 3 komoditas |
| FR-B7 / VP7 | Kontrol musiman/hari raya bebas kebocoran | `prices/seasonality.py`, `hari_raya_id.csv` | `test_domino.py` | **VERIFIED** | 100% (50/50) sisi bertahan |
| VP5 | Kontrol permutasi circular-shift (20×) | `prices/domino.py` | `test_domino.py` | **VERIFIED** | 3,44% rata-rata sisi palsu (≤ 5%) |
| FR-B8 / VP6 | Walk-forward (`296` hari uji) vs Naive & AR(5) | `evaluation/walk_forward.py` | `test_walk_forward.py` | **VERIFIED** | Selektif per komoditas (`model_review_decisions.csv`) |
| FR-A1 / VP1 | Normalisasi teks bahan + sinonim | `cleaning/ingredients.py`, `ingredient_synonyms.csv` | `test_recipes.py` | **VERIFIED** | 271/300 (90,33%) pada `artifacts/vp1_eval_sample_300.csv` |
| FR-A2..A5 / VP2, VP3 | Graph NPMI, Louvain, Word2Vec, substitusi, kulkas | `recipes/network.py`, `recipes/embedding.py`, `recipes/pipeline.py` | `test_recipes.py` | **VERIFIED** | `m3_20261118T070540Z` (VP2: 45,50% vs 40,88%; VP3: 24,0%) |
| FR-C1..C4 | Pemetaan manual, skor gabungan, cakupan, unmapped | `bridge/scoring.py`, `bridge/pipeline.py` | `test_bridge.py` | **VERIFIED** | `m4_20261118T080802Z` (1,05% vocab / 27,74% mention) |
| FR-D1..D5 | Streamlit 4 halaman berbasis artefak | `app/streamlit_app.py`, `app/artifacts_loader.py` | `test_app_loader.py`, `test_streamlit_app.py` | **VERIFIED** | `AppTest` lulus pada data sintetis & nyata (`2026-11-18`) |
| DS Lifecycle Audit | EDA, validasi, seleksi, skenario val, review keputusan | `evaluation/lifecycle.py`, `scripts/run_ds_lifecycle_audit.py` | `test_ds_lifecycle.py` | **VERIFIED** | `artifacts/analysis/*.csv`, `MODEL_REVIEW.md`, Notebook |
| NFR-1 / VP8 | Reprodusibilitas (`make reproduce` & `update_data.py`) | `scripts/reproduce.py`, `scripts/update_data.py` | `test_reproducibility.py` | **TESTED** | Identik di workspace sintetis |
| NFR-2 / VP9 | Raw & run manifest SHA-256 + deteksi manipulasi | `ingest/manifest.py`, `tracking.py` | `test_manifest.py`, `test_tracking.py` | **VERIFIED** | 100% kasus manipulasi terdeteksi |
| NFR-3 / VP10 | Pengukuran aktual waktu & RAM (≤ 8 GB) | `tracking.py` | `test_tracking.py` | **VERIFIED** | Puncak maks 796,10 MiB (M1) |

## Deviasi PRD

| ID | Deviasi | Tanggal | Alasan |
|---|---|---|---|
| DEV-1 | Cakupan komoditas harga 10–20 → 10 kategori PIHPS | 2026-11-18 | Fakta sumber data (`ref_commodities.json`) |
| DEV-2 | "Harian" → hari kerja Senin–Jumat | 2026-11-18 | Fakta sumber data PIHPS |
| DEV-3 | D4 (scraping Cookpad) dikeluarkan | 2026-11-18 | `robots.txt` memblokir crawler AI/dataset |
| DEV-4 | Python `<3.14` (memakai 3.12) | 2026-11-18 | Kompatibilitas wheel pustaka ilmiah |
| DEV-5 | Walk-forward `initial_train_days` 730→500, `horizon` 7→1, `granger_lag` 5 | 2026-11-18 | Ditetapkan sebelum M2 agar tersisa 296 hari uji out-of-sample |
