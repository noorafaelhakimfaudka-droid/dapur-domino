# Dapur Domino

**Efek domino harga pangan nasional (PIHPS Bank Indonesia) × jaringan asosiasi bahan masakan Nusantara → rekomendasi substitusi dan pelengkap kuliner yang sadar-harga.**

- **Aplikasi Web Live:** [dapurdomino.streamlit.app](https://dapurdomino.streamlit.app)
- **Status Pipeline (`M0–M6`):** Terverifikasi lokal (`1.141.526` baris PIHPS s.d. `18 Nov 2026` across `796` hari pasar aktif di Nasional, `34` Provinsi, & `105` Kota + `69.915` resep Nusantara, Streamlit `4` halaman, `34/34` tes `pytest` lulus, puncak RAM `796,10 MB`).

---

## Ringkasan Metodologi & Hasil Terukur

1. **Validasi & Pembersihan Data:** Verifikasi SHA-256 pada `370` berkas mentah (`0` rusak), penyaringan `8` hari libur nasional dan `50` seri kota bolong `> 20%`, normalisasi `852.568` baris resep dengan `236` sinonim (`90,33%` atau `271/300` bersih pada audit manual), serta uji stasioneritas ganda (`ADF + KPSS`) yang melonjak dari `0%` (harga Rupiah mentah) menjadi **`90,0%` Nasional**, **`98,24%` Provinsi**, dan **`98,00%` Kota** setelah diubah menjadi *log-return*.
2. **Efek Domino Harga (`[0:500]` Latih vs `[500:796]` Ujian):** Uji Granger + koreksi `BH-FDR (5%)` mendeteksi `50` rantai mentah dan `56` rantai pasca-kontrol kalender/Lebaran (`100%` rantai awal bertahan), dengan tingkat temuan palsu hanya **`3,44%` (`3,1/90`)** pada `20×` permutasi melingkar. Di tingkat kota, **Kota Surakarta (Solo)** mendahului `77/104` kota untuk *Cabai Merah* dan `75/104` kota untuk *Cabai Rawit*.
3. **Evaluasi *Walk-Forward Out-of-Sample* (`296` Hari Uji):** Model `Domino ARX(5) Ridge` unggul sah (`Diebold-Mariano p < 0,05`) pada **Minyak Goreng (`+14,79%`)**, **Daging Sapi (`+10,00%` musiman / `+12,32%` raw)**, dan **Beras (`+6,62%`)**, sementara komoditas hortikultura (*Cabai Merah*, *Cabai Rawit*, *Bawang*) lebih akurat memakai fallback `AR(5)` univariat (`model_review_decisions.csv`).
4. **Jaringan Resep & Jembatan Sadar-Harga:** Graf `1.334` bahan dan `11.938` sisi `NPMI` membentuk `82` komunitas rasa Louvain. Untuk *Isi Kulkasku* (`3.459` resep uji), `Conditional PMI` meraih Top-5 **`45,50%`** (`CI 95%: 43,85%–47,17%`) mengalahkan baseline popularitas **`40,88%`** (`39,25%–42,53%`). Jembatan `60%` kecocokan resep + `40%` stabilitas harga 30 hari mencakup **`27,74%`** kemunculan bahan dapur dengan **0 harga buatan** di luar 10 komoditas resmi BI.

---

## Struktur Repositori

```
dapur-domino/
├── README.md
├── streamlit_app.py          # entrypoint root untuk Streamlit Community Cloud
├── requirements.txt          # dependensi runtime ringan untuk cloud deploy
├── pyproject.toml            # konfigurasi paket, ruff, mypy, & pytest
├── uv.lock                   # versi dependensi terkunci
├── Makefile                  # lint, typecheck, test, reproduce, app
├── .streamlit/config.toml    # tema antarmuka Streamlit
├── configs/default.yaml      # konfigurasi seed, ambang batas, & bobot
├── data/
│   ├── raw/manifest.json     # ledger hash SHA-256 berkas mentah (data mentah tetap lokal)
│   ├── external/             # kalender hari raya, kamus sinonim, pemetaan komoditas
│   └── processed/            # data olahan siap pakai aplikasi Streamlit
├── src/dapur_domino/
│   ├── ingest/               # pengunduhan/pemuatan data PIHPS/Bapanas + manifest SHA-256
│   ├── cleaning/             # pembersihan panel harga & normalisasi teks resep
│   ├── recipes/              # Modul A: graf NPMI, Louvain, Word2Vec, isi kulkas
│   ├── prices/               # Modul B: stasioneritas ADF/KPSS, musiman, Granger/FDR
│   ├── bridge/               # Modul C: pemetaan BI & skoring substitusi sadar-harga
│   ├── evaluation/           # walk-forward Ridge, DM test, evaluasi resep, & audit siklus
│   └── app/                  # Modul D: aplikasi Streamlit 4 halaman + CSS
├── notebooks/                # 01_eda_dan_pemodelan_dapur_domino.ipynb
├── scripts/                  # entry point CLI pipeline M1–M4, audit, & update_data.py
├── tests/                    # 34 unit, integrasi, regresi, UI, & reprodusibilitas tests
├── artifacts/
│   ├── runs/                 # 4 folder run final terverifikasi + manifest.json
│   └── analysis/             # tabel EDA, validasi, skenario model, & keputusan review
└── docs/                     # PRD, metodologi, evaluasi, review model, keterbatasan
```

---

## Dokumen Teknis Utama

| Dokumen | Ringkasan |
|---|---|
| [docs/MODEL_REVIEW.md](docs/MODEL_REVIEW.md) | Ringkasan siklus DS, EDA, adu 8 skenario, & matriks keputusan produksi |
| [docs/EVALUATION_REPORT.md](docs/EVALUATION_REPORT.md) | Hasil empiris terukur `VP1–VP10` per `18 Nov 2026` |
| [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) | Verifikasi sumber data PIHPS, Bapanas, & korpus resep |
| [docs/METHODOLOGY.md](docs/METHODOLOGY.md) | Protokol statistik, anti-kebocoran, & metode evaluasi |
| [docs/LIMITATIONS.md](docs/LIMITATIONS.md) | Keterbatasan data, model, & aturan lisensi |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Arsitektur sistem & pemisahan modul |
| [docs/PRD.md](docs/PRD.md) | Spesifikasi kebutuhan produk & kriteria validitas |
| [docs/TRACEABILITY.md](docs/TRACEABILITY.md) | Pemetaan requirement → kode → tes → bukti |

---

## Menjalankan Verifikasi & Aplikasi Secara Lokal

```bash
uv sync --extra dev
uv run ruff check src tests scripts streamlit_app.py
uv run mypy src tests scripts
uv run pytest -v
uv run streamlit run streamlit_app.py
```
