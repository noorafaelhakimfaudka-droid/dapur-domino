# MODEL REVIEW & LIFECYCLE SUMMARY — Dapur Domino

**Efek Domino Harga Pangan Nasional × Jaringan Asosiasi Bahan Kuliner Nusantara Sadar-Harga**

Dokumen ini merangkum keseluruhan siklus eksperimen *Data Science* end-to-end (data per `2026-11-18`) beserta artefak audit terukur di `artifacts/analysis/` dan notebook [01_eda_dan_pemodelan_dapur_domino.ipynb](../notebooks/01_eda_dan_pemodelan_dapur_domino.ipynb).

---

## 1. Perumusan Objektif Bisnis & Tujuan Teknis

| Tahap | Implementasi & Modul | Artefak Bukti Terukur | Ringkasan Temuan |
| :--- | :--- | :--- | :--- |
| Objektif Bisnis | `lifecycle.py` (`build_business_objectives_matrix`), `docs/PRD.md` | `artifacts/analysis/business_objectives.csv` | `4` objektif (`BO-1`..`BO-4`) mencakup efisiensi belanja rumah tangga, sinyal dini UMKM, optimasi bahan kulkas, dan tata kelola riset lokal (`<= 8 GB RAM`). |
| Tujuan Teknis DS | `lifecycle.py` (`build_technical_ds_objectives_matrix`) | `artifacts/analysis/technical_objectives.csv` | `7` tujuan teknis (`TDO-1`..`TDO-7` / `VP1`–`VP10`) dengan baseline pembanding dan ambang batas kelulusan yang dikunci sebelum melihat data uji. |

---

## 2. Eksplorasi Data (EDA), Validasi Kualitas, & Seleksi Data

- **Statistik Deskriptif Harga (`796` hari kerja, `2023-11-01` s.d. `2026-11-18`, `eda_prices_stats.csv`):**
  - Komoditas paling bergejolak: **Cabai Rawit** (`mean = Rp 61.035`, `std = Rp 12.693`, `CV = 20,80%`, rentang `Rp 38.800`–`Rp 95.700`, std return harian `2,19%`) dan **Cabai Merah** (`mean = Rp 54.101`, `std = Rp 10.794`, `CV = 19,95%`, std return harian `2,56%`).
  - Komoditas paling stabil: **Beras** (`CV = 2,96%`), **Gula Pasir** (`CV = 3,37%`), dan **Daging Sapi** (`CV = 3,45%`).
- **Statistik Deskriptif Resep (`66.419` train & `3.496` eval, `eda_recipes_stats.csv`):**
  - Jumlah bahan unik per resep identik antara Train (`mean = 13,02`, `median = 13`, `IQR = 7`) dan Eval (`mean = 13,06`, `median = 13`, `IQR = 6`), membuktikan ketiadaan *covariate shift*.
  - Frekuensi bahan mengikuti distribusi *power-law* (Zipf): **Top-10 bahan menyumbang `40,64%`** dan **Top-50 bahan menyumbang `80,40%`** seluruh kemunculan bahan.
- **Validasi Kualitas & Stasioneritas (`data_validation_report.csv`, `data_selection_matrix.csv`):**
  - `379` berkas mentah (`370` arsip PIHPS + `9` referensi/sampel/resep) terverifikasi SHA-256 (`0` ketidakcocokan); `8` hari libur nasional (`>= 90%` kosong) disaring dari `804` hari kerja.
  - Dari `1.099` seri kota, `50` seri dengan *missingness* `> 20%` dieksklusi sehingga menyisakan `1.049` seri kota aktif.
  - Uji stasioneritas ganda (`ADF p < 0,05` & `KPSS p >= 0,05`) melonjak dari `0/10` (harga mentah) menjadi **`90,0% (9/10)`** Nasional, **`98,24% (334/340)`** Provinsi, dan **`98,00% (1.028/1.049)`** Kota setelah transformasi *log-return*.
  - Partisi waktu kronologis 3-tahap: **Sub-Train `[0:400]`**, **Validasi `[400:500]`**, dan **Sealed Test `[500:796]`**.

---

## 3. Pembersihan, Konstruksi Fitur, & Skenario Model

- **Pembersihan & Konstruksi Fitur (`data_cleaning_audit.csv`, `feature_engineering_audit.csv`):**
  - `5` tahap pembersihan deterministik + kamus `236` sinonim (`VP1 = 90,33%` pada `n=300` sampel evaluasi).
  - `6` kelompok rekayasa fitur bebas *data leakage*: *log-return* $r_t$, `11` fitur OLS kalender/Fourier/Lebaran, lag `ARX(p)`, bobot graf `NPMI/Lift`, vektor `Word2Vec` 64-dim dengan penalti komplemen, dan skor stabilitas harga eksponensial 30 hari.
- **Eksperimen 8 Skenario Deret Waktu pada Jendela Validasi `Hari [400:500]` (`scenarios_timeseries_val.csv`):**
  - `S01` (`lag=1`, Raw) kalah (`skill vs AR = -1,264%`) karena horizon terlalu pendek.
  - `S03` (`lag=5`, `alpha=0,001` nyaris OLS) mengalami *overfitting* berat terhadap Naive (`-6,642%`).
  - **`S08` (`lag=5`, `ridge_alpha=1,0`, *Seasonally Adjusted*)** mencatat hasil paling seimbang (`skill vs AR = +4,164%`, menang di `7/10` komoditas, `skill vs Naive = +1,586%`, lulus di `4/10` komoditas validasi).
- **Registri 8 Model (`model_registry.csv`):** Seluruh komponen (`MDL-B1`..`B4`, `MDL-A1`..`A3`, `MDL-C1`, `seed=42`) berjalan lokal dengan puncak memori maksimum **`796,10 MB`** dan waktu total `< 160 detik`.

---

## 4. Evaluasi *Out-of-Sample*, Taksonomi Error, & Keputusan Model Produksi

- **Taksonomi Error Substitusi (`vp3_error_taxonomy.csv`):** `Recall@5 = 24,0% (6/25)`, `MRR@10 = 0,2100`, `NDCG@5 = 9,37%`. Dari `19` kasus meleset, **`10` kasus** adalah varian bentuk/olahan bahan yang sama (`santan -> santan dari kelapa`, `gula merah -> blok gula merah`) dan **`9` kasus** merupakan tetangga konteks serumpun atau token korpus pendek (`miri`, `di`).
- **Matriks Keputusan Model Produksi per Komoditas (`model_review_decisions.csv`):**
  1. **Gunakan `Domino ARX(5) Ridge` (`3` komoditas):** **Daging Sapi** (lulus di raw `+12,32%` & musiman `+10,00%`), **Beras** (lulus pasca-musiman `+6,62%`, DM `p=0,0173`), dan **Minyak Goreng** (lulus di raw `+13,47%`, DM `p=0,0022`).
  2. **Gunakan *Fallback* `Univariate AR(5)` (`5` komoditas):** **Cabai Merah, Cabai Rawit, Bawang Merah, Bawang Putih, Gula Pasir**.
  3. **Gunakan *Fallback* `Naive Last Price` (`2` komoditas):** **Daging Ayam, Telur Ayam**.
- **Peta Jalan Iterasi Berikutnya:** (1) Menambahkan *lemma deduplication* di atas kandidat `Word2Vec`; (2) Menambahkan kovariat cuaca/curah hujan BMKG pada komoditas hortikultura.
