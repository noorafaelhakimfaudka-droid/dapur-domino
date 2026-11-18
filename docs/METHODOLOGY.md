# METHODOLOGY — Dapur Domino

Dokumen ini menjelaskan metodologi ilmiah dan desain eksperimen end-to-end (lihat ringkasan hasil & tabel audit di [MODEL_REVIEW.md](MODEL_REVIEW.md)).

## 1. Modul B — Data Harga & Efek Domino

1. **Kalender & pembersihan (`FR-B1`):** data PIHPS dikumpulkan setiap hari kerja (Senin–Jumat, `796` hari pasar buka dari `2023-11-01` s.d. `2026-11-18`, `1.141.526` catatan harga, `Pasar Tradisional`). Akhir pekan tidak pernah diimputasi (`DEV-2`). Seri dengan missingness mentah > 20% dikeluarkan (`50/1.099` seri kota dikeluarkan). Lonjakan return harian ekstrem (`|ln(P_t/P_{t-1})| > 0,65`) dicatat di `outlier_audit_*.csv` tanpa diubah diam-diam.
2. **Stasioneritas (`FR-B2`, `VP4`):** harga dikonversi menjadi *log-return* `ln(P_t / P_{t-1})`, lalu diuji ganda dengan **ADF** (`p < 0,05`) dan **KPSS** (`p >= 0,05`).
3. **Kontrol musiman & hari raya (`FR-B7`, `VP7`):** model regresi kalender (hari dalam minggu, harmonik tahunan Fourier `k=1,2`, serta jendela pra/pasca hari raya dari `hari_raya_id.csv`) **dipasang hanya pada data latih** (`[:500]`) dan diselisihkan ke seluruh rentang tanpa kebocoran data uji.
4. **Lead-lag & Granger (`FR-B3`–`FR-B6`):** untuk seluruh `N*(N-1)` pasangan terarah, dihitung *cross-correlation* berjeda (`lag 1..10`) dan uji F Granger (`lag=5` hari kerja), diikuti koreksi **Benjamini–Hochberg FDR** (`α = 0,05`).
5. **Kontrol temuan palsu (`VP5`):** 20 permutasi *circular-shift* independen per seri (offset acak `>= 20` hari) menjaga autokorelasi univariat sembari menghancurkan keterkaitan silang.
6. **Eksperimen skenario & evaluasi *walk-forward* (`FR-B8`, `VP6`):** pemilihan skenario hyperparameter (`lag in {1,3,5}`, `ridge_alpha in {0.001, 0.1, 1.0, 10.0}`) diuji pada jendela validasi `[400:500]`. Evaluasi akhir dijalankan pada `296` hari kerja uji tersegel (`[500:796]`) dengan *expanding-window* 1-langkah ke depan membandingkan **Naive Last (`r=0`)**, **AR(5)** univariat, dan **Domino ARX(5)** (Ridge `α=1,0`), disertai uji **Diebold–Mariano**.

## 2. Modul A — Graph Bahan & Substitusi

1. **Normalisasi (`FR-A1`):** pembersihan berbasis aturan (penghapusan angka, satuan seperti `sdm`, `gr`, `65ml`, `ruas jari`, catatan kurung, kata kerja persiapan, pemisahan multi-bahan) + kamus sinonim berversi ([ingredient_synonyms.csv](../data/external/ingredient_synonyms.csv)).
2. **Graph ko-okurensi (`FR-A2`, `FR-A3`):** simpul adalah bahan dengan frekuensi `>= 20` resep di `train.parquet` (`66.419` resep). Sisi dibobot dengan **NPMI** (`>= 0,05`, `co_count >= 10`), dan komunitas "keluarga rasa" dideteksi dengan **Louvain** (`seed=42`).
3. **Embedding & substitusi (`FR-A4`, `FR-A5`):** `Word2Vec` Skip-gram (`dim=64`, `window=10`, `min_count=20`, `workers=1`, `seed=42`). Skor substitusi mendiskon komplemen langsung: `sub_score = cosine_sim * (1 - max(0, npmi))`.
4. **Evaluasi (`VP1`, `VP2`, `VP3`):**
   - `VP1`: audit manual 300 baris bahan acak dari `eval.parquet`.
   - `VP2`: *hide-one-ingredient* pada resep `eval.parquet` (`3.459` resep uji), membandingkan Popularity, NPMI Graph, Conditional Co-occurrence (`log P(c) + mean PMI(c, obs)`), dan Word2Vec (`syn1neg`) dengan selang kepercayaan Wilson 95%.
   - `VP3`: Recall@5, Recall@10, MRR@10, dan NDCG@5 terhadap 25 bahan acuan di [culinary_substitutions_ref.csv](../data/external/culinary_substitutions_ref.csv) disertai taksonomi error (`artifacts/analysis/vp3_error_taxonomy.csv`).

## 3. Modul C — Jembatan Sadar-Harga

- Pemetaan manual berversi ([ingredient_commodity_map.csv](../data/external/ingredient_commodity_map.csv)) ke 10 komoditas PIHPS.
- Bahan tanpa pemetaan diberi `price_status = "unmapped"` dan `combined_score = None`.
- Untuk bahan terpetakan: `price_stability_score = exp(-max(0, pct_change_30d)) * exp(-5 * vol_30d)` dan `combined_score = 0,6 * sub_score + 0,4 * price_stability_score` (dianalisis sensitivitasnya pada `artifacts/analysis/scenarios_bridge_sensitivity.csv`).
