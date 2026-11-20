# EVALUATION REPORT — Dapur Domino

Seluruh metrik di bawah berasal langsung dari artefak eksekusi terukur terbaru (`artifacts/runs/` dan `artifacts/analysis/` per `2026-11-18`). Hasil negatif dan keterbatasan dilaporkan apa adanya (`NFR-7`).

---

## 1. Ringkasan Kriteria Validitas (VP1–VP10)

| ID | Kriteria | Hasil terukur | Ambang PRD | Status | Bukti |
|---|---|---|---|---|---|
| **VP1** | Kualitas normalisasi bahan (sampel ≥ 300 baris) | **271 / 300 = 90,33%** (audit ketat; 29 baris menyisakan kata persiapan/merek/typo sumber) | ≥ 90% | **VERIFIED** | `artifacts/vp1_eval_sample_300.csv` |
| **VP2** | Prediksi bahan tersembunyi (`3.459` resep uji) | Top-5 **45,50%** (`CI95%: 43,85%–47,17%`) vs Popularity **40,88%** (`CI95%: 39,25%–42,53%`) | > baseline dengan CI terpisah | **VERIFIED** | `artifacts/runs/m3_20261118T070540Z/m3_summary.json` |
| **VP3** | Kualitas substitusi (25 acuan kuliner) | Recall@5: **24,0% (6/25)** · Recall@10: **24,0% (6/25)** · MRR@10: **0,2100** · NDCG@5: **9,37%** | Dilaporkan + taksonomi error | **VERIFIED (hasil rendah — dibedah di taksonomi error)** | `vp3_substitution_details.json`, `vp3_error_taxonomy.csv` |
| **VP4** | Stasioneritas harga pasca log-return (`796` hari kerja) | Lulus ADF+KPSS: **90,0% (9/10)** nas · **98,24% (334/340)** prov · **98,00% (1.028/1.049)** kota (100% / 100% / 99,81% ADF) | Mayoritas lulus; sisanya dicatat | **VERIFIED** | `artifacts/runs/m1_20261118T080609Z/m1_summary.json` |
| **VP5** | Pengendalian temuan palsu Granger (20× permutasi circular-shift) | Rata-rata sisi palsu **3,1 / 90 = 3,44%** (`α FDR = 5%`), maks 9/90 | ≈ tingkat FDR | **VERIFIED** | `artifacts/runs/m2_20261118T080707Z/m2_summary.json` |
| **VP6** | Nilai prediktif out-of-sample (`296` hari uji) vs Naive & AR(5) | Return mentah: **2/10** lulus (*Daging Sapi*, *Minyak Goreng*). Pasca-musiman: **2/10** lulus penuh (*Beras*, *Daging Sapi*; *Minyak Goreng* +14,79% vs AR(5), `-0,01%` vs Naive) | Klaim "pemicu" sah hanya jika mengalahkan baseline | **VERIFIED (selektif — matriks keputusan di `model_review_decisions.csv`)** | `walk_forward_raw.csv`, `walk_forward_seasonal_adj.csv`, `model_review_decisions.csv` |
| **VP7** | Ketahanan terhadap kontrol musiman/hari raya | **100% (50/50)** sisi mentah bertahan + 6 sisi baru (`56` total) | Dilaporkan | **VERIFIED** | `artifacts/runs/m2_20261118T080707Z/m2_summary.json` |
| **VP8** | Reprodusibilitas pipeline | Identik penuh antara Run 1 & Run 2 untuk M1–M4 pada workspace uji sintetis | Identik / dalam toleransi | **TESTED (pada fixture sintetis)** | `tests/test_reproducibility.py` |
| **VP9** | Integritas manifest & deteksi manipulasi | 100% perubahan/penghapusan raw (`379` file: `370` histori PIHPS + `9` referensi/sampel/resep) maupun artefak run terdeteksi | 100% kasus uji terdeteksi | **VERIFIED** | `tests/test_manifest.py`, `tests/test_tracking.py` |
| **VP10** | Sumber daya aktual (≤ 8 GB = 8.192 MiB) | M1: 50,80 dtk / **796,10 MiB** · M2: 54,17 dtk / **202,11 MiB** · M3: 52,23 dtk / **313,57 MiB** · M4: 0,13 dtk / **92,90 MiB** | ≤ 8 GB RAM | **VERIFIED** | `manifest.json` di tiap folder run |

---

## 2. Rincian Temuan Kunci per Modul

### Modul B (Harga & Efek Domino, `2023-11-01` s.d. `2026-11-18`, `796` hari kerja)
- **Spasial Provinsi (`34` provinsi, `1.122` pasangan/komoditas):** provinsi sentra produksi di Jawa mendominasi posisi pemimpin *out-degree*: Jawa Barat memimpin *Beras* (15), *Telur Ayam* (21), *Bawang Merah* (29); Jawa Tengah memimpin *Daging Ayam* (14), *Bawang Putih* (7), *Cabai Merah* (24); Jawa Timur memimpin *Cabai Rawit* (24), *Gula Pasir* (24). Pada tingkat `105` kota, **Kota Surakarta (Solo)** memimpin *Cabai Merah* (`77` sisi keluar) dan *Cabai Rawit* (`75` sisi keluar).
- **Eksperimen Skenario Validasi (`Hari [400:500]`):** Dari 8 skenario kombinasi `lag` dan `ridge_alpha`, skenario **`S08` (`lag=5`, `ridge_alpha=1,0`, *Seasonally Adjusted*)** mencatat rata-rata peningkatan *skill* terbaik terhadap `AR(5)` (`+4,164%`, menang di `7/10` komoditas) dan `Naive` (`+1,586%`).
- **Walk-forward out-of-sample (`296` hari kerja uji, `Hari [500:796]`, VP6):**
  - *Daging Sapi*: lulus di kedua rezim — Raw RMSE Domino `0,002469` vs AR(5) `0,002816` (**+12,32%**, DM `p=0,0330`) & Musiman RMSE Domino `0,002388` vs AR(5) `0,002654` (**+10,00%**).
  - *Minyak Goreng*: lulus di rezim Raw — RMSE Domino `0,001551` vs AR(5) `0,001792` (**+13,47%**, DM `p=0,0022`) & Naive `0,001581` (**+1,91%**); pada rezim musiman unggul **+14,79%** vs AR(5) (`DM p=0,00019`).
  - *Beras*: lulus di rezim pasca-musiman — RMSE Domino `0,001376` vs AR(5) `0,001473` (**+6,62%**, DM `p=0,0173`) & Naive `0,001378`.
  - *Cabai Merah*, *Cabai Rawit*, *Bawang Merah*: mengalahkan Naive (`+3,77%` s.d. `+6,08%`), tetapi **kalah dari AR(5)** (`-2,82%` s.d. `-12,69%`), sehingga direkomendasikan memakai `AR(5)` univariat (`model_review_decisions.csv`).

### Modul A (Graph Bahan, `66.419` latih / `3.459` uji VP2)
- Graph terdiri atas **1.334 simpul bahan**, **11.938 sisi NPMI**, dan **82 komunitas Louvain**.
- Pada VP2 (*hide-one-ingredient*):
  - `cooccur_conditional`: Top-5 **45,50%** (`[43,85%, 47,17%]`), Top-10 **56,29%** (`[54,63%, 57,93%]`)
  - `popularity` (baseline): Top-5 **40,88%** (`[39,25%, 42,53%]`), Top-10 **54,58%** (`[52,92%, 56,24%]`)
  - `npmi_graph` murni: Top-5 **23,82%**, Top-10 **32,32%**
  - `word2vec_context` (`syn1neg`): Top-5 **7,63%**, Top-10 **11,01%**

### Modul C (Jembatan Sadar-Harga per `2026-11-18`)
- Cakupan pemetaan ke 10 komoditas PIHPS: **1,05%** kosakata (`14/1.334`) dan **27,74%** kemunculan bahan (`217.380/783.564`).
- Pada 10 kasus uji tetap (`bridge_eval_summary.csv` per `2026-11-18`): `C01 cabai merah keriting` (`cabai merah`, skor gabungan `0,8284`) dan `C02 cabai rawit` (`cabai rawit merah`, skor gabungan `0,8707`) terpetakan ke harga PIHPS; kasus `C09 kemiri` & `C10 santan` ditandai `unmapped` secara jujur tanpa estimasi harga.
