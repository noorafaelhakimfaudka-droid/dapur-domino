# PRD — Dapur Domino
**Efek Domino Harga Pangan × Jaringan Asosiasi Bahan Masakan Nusantara**

| Item | Nilai |
|---|---|
| Versi | 0.1 (draft) |
| Tanggal | 2026-11-18 |
| Status dokumen | DRAFT — belum ada implementasi |
| Perkiraan durasi | 6–8 minggu (estimasi, belum terbukti) |

> **Konvensi status** yang dipakai di seluruh repo: `IMPLEMENTED` (kode ada) · `TESTED` (tes sudah dijalankan) · `VERIFIED` (kriteria terpenuhi dengan bukti) · `FAILED` · `BLOCKED`. Semua requirement di dokumen ini berstatus **belum dimulai** sampai tercatat di `docs/TRACEABILITY.md`.

---

## 1. Latar Belakang & Masalah

Harga pangan (cabai, bawang, telur, minyak goreng) sering bergejolak, dan dampaknya merambat antar komoditas dan antar daerah. Di sisi lain, rumah tangga dan pelaku kuliner kecil harus memutuskan bahan pengganti secara intuitif ketika satu bahan mahal atau habis.

Dua pertanyaan ini jarang dijawab bersama:
1. **Sisi harga:** komoditas dan daerah mana yang bergerak lebih dulu, dan berapa lama jedanya?
2. **Sisi kuliner:** bahan apa yang secara pola resep bisa menggantikan bahan lain?

**Proyek ini menggabungkan keduanya** menjadi rekomendasi substitusi bahan yang mempertimbangkan kemiripan peran dalam resep *dan* stabilitas/kenaikan harga.

## 2. Tujuan & Non-Tujuan

### Tujuan
- G1. Membangun **graph asosiasi bahan** dari korpus resep Indonesia.
- G2. Membangun **graph lead-lag harga** antar komoditas dan antar kota dari data harga harian.
- G3. Menggabungkan keduanya menjadi **rekomendasi substitusi sadar-harga**.
- G4. Menyajikan hasil dalam **app interaktif** (Streamlit) dengan jejak data dan metrik evaluasi yang bisa diaudit.
- G5. Setiap klaim analitis disertai evaluasi terhadap baseline.

### Non-Tujuan
- Bukan sistem prediksi harga komersial atau saran investasi/perdagangan.
- Bukan klaim kausalitas. Istilah yang dipakai: "mendahului secara prediktif".
- Bukan penilai rasa atau nutrisi. Kemiripan substitusi bersifat statistik, bukan jaminan kecocokan rasa.
- Tidak ada layanan cloud LLM; seluruh pemrosesan berjalan lokal.

## 3. Pengguna Sasaran

| Persona | Kebutuhan | Fitur utama |
|---|---|---|
| Ibu rumah tangga / anak kos | "Cabai mahal, ganti apa?" | Rekomendasi substitusi + isi kulkas |
| Pelaku UMKM kuliner | Antisipasi kenaikan bahan | Peringatan komoditas pemicu |
| Reviewer portofolio / analis | Melihat metode dan bukti | Halaman metodologi, metrik, reproduksi |

## 4. Sumber Data

> Ketersediaan, format, lisensi, dan ketentuan akses **harus diverifikasi** sebelum Milestone M1. Hasil verifikasi dicatat di `docs/DATA_SOURCES.md`.

| ID | Sumber | Kegunaan | Status verifikasi |
|---|---|---|---|
| D1 | PIHPS Nasional (Bank Indonesia) — harga hari kerja per komoditas/kota | Graph harga | Diverifikasi parsial: **10 komoditas, hari kerja saja** (lihat DEV-1, DEV-2) |
| D2 | Open Data Bapanas | Pembanding bulanan untuk D1 | Diverifikasi parsial: bulanan; sebagian "Terbatas" |
| D3 | Dataset resep publik (Hugging Face; Kaggle belum dicek) | Graph bahan | **BLOCKED**: dataset besar gated, butuh persetujuan pengguna |
| D4 | Resep web (mis. Cookpad ID) | — | **Dikeluarkan** (DEV-3): robots.txt memblokir crawler AI/dataset |

> Rincian bukti: [DATA_SOURCES.md](DATA_SOURCES.md). Deviasi dari asumsi awal PRD dicatat di [TRACEABILITY.md](TRACEABILITY.md). Teks PRD di bagian lain (mis. "harian", "10–20 komoditas") belum direvisi dan harus dibaca bersama deviasi tersebut.
| D5 | Kalender hari raya | Kontrol musiman | Belum diverifikasi |
| D6 | Curah hujan BMKG | Kovariat opsional | Opsional |

**Aturan data:** data mentah tidak pernah ditimpa; setiap dataset mentah dicatat hash dan tanggal unduhnya di manifest.

## 5. Ruang Lingkup Fungsional

### 5.1 Modul A — Graph Bahan (Kuliner)
- **FR-A1** Normalisasi teks bahan: hapus kuantitas/satuan, tangani sinonim (cabe/cabai/lombok), huruf besar-kecil, dan salah ketik. Kamus sinonim disimpan terpisah dan berversi.
- **FR-A2** Hitung co-occurrence bahan dengan PMI/lift (ternormalisasi) dengan ambang frekuensi minimum.
- **FR-A3** Bangun graph tak berarah; deteksi komunitas (Louvain/Leiden) sebagai "keluarga rasa".
- **FR-A4** Latih embedding bahan (Word2Vec atau node2vec) dan hasilkan daftar kandidat substitusi (kemiripan konteks tinggi, ko-okurensi langsung rendah).
- **FR-A5** Fungsi rekomendasi: (a) bahan tersedia → bahan/resep pelengkap; (b) bahan hilang → substitusi berperingkat.

### 5.2 Modul B — Efek Domino Harga
- **FR-B1** Pembersihan data harga: data hilang, outlier, hari tanpa data, penyelarasan kode kota/komoditas.
- **FR-B2** Transformasi ke log-return dan uji stasioneritas (ADF/KPSS); dokumentasikan transformasi per seri.
- **FR-B3** Analisis lead-lag: cross-correlation berjeda dan uji Granger untuk pasangan komoditas.
- **FR-B4** Koreksi multiple testing (Benjamini–Hochberg FDR) pada seluruh pasangan yang diuji.
- **FR-B5** Graph berarah antar komoditas (sisi = hubungan signifikan, atribut = jeda dan kekuatan); hitung skor "pemicu" (out-degree/centrality) dan "penerima".
- **FR-B6** Graph spasial antar kota: kota yang bergerak lebih dahulu.
- **FR-B7** Kontrol musiman/hari raya: analisis dijalankan dengan dan tanpa dekomposisi musiman, perbedaannya dilaporkan.
- **FR-B8** Model prakiraan (opsional) dengan fitur lag komoditas lain, dibandingkan dengan baseline.

### 5.3 Modul C — Jembatan (Substitusi Sadar-Harga)
- **FR-C1** Pemetaan bahan resep (Modul A) ke komoditas harga (Modul B) melalui tabel pemetaan manual berversi; bahan tanpa pemetaan ditandai, bukan ditebak.
- **FR-C2** Skor substitusi gabungan: `skor = w_s · kemiripan_resep + w_p · skor_harga`, dengan skor harga berbasis perubahan harga terkini dan volatilitas. Bobot `w_s`, `w_p` diatur di config dan dilaporkan, bukan disetel pada data uji.
- **FR-C3** Setiap rekomendasi menampilkan penjelasan: nilai kemiripan, perubahan harga, tanggal data, dan peringatan keterbatasan.
- **FR-C4** Cakupan pemetaan dilaporkan (persentase bahan yang punya data harga).

### 5.4 Modul D — Aplikasi (Streamlit)
- **FR-D1** Halaman *Substitusi*: pilih bahan → daftar pengganti + harga.
- **FR-D2** Halaman *Isi Kulkasku*: input beberapa bahan → saran resep/pelengkap.
- **FR-D3** Halaman *Efek Domino*: graph komoditas dan peta/graph kota, studi kasus (mis. cabai menjelang Ramadan).
- **FR-D4** Halaman *Metodologi & Bukti*: metrik evaluasi, cakupan data, keterbatasan, versi dan hash data.
- **FR-D5** Semua angka di UI berasal dari artefak hasil komputasi yang tercatat, bukan nilai statis.

## 6. Requirement Non-Fungsional

- **NFR-1 Reprodusibilitas:** satu perintah (`make reproduce`) menjalankan pipeline dari data mentah ke artefak; seed tetap; versi dependensi dikunci.
- **NFR-2 Auditabilitas:** setiap run menyimpan `manifest.json` (hash data, config, versi kode, seed, metrik, lokasi artefak). Run gagal/terhenti tetap tercatat dan dapat dibedakan.
- **NFR-3 Sumber daya:** berjalan di laptop 8 GB RAM; penggunaan memori dan waktu **diukur** dan dilaporkan, bukan diestimasi.
- **NFR-4 Privasi/lokal:** tidak ada pengiriman data ke layanan eksternal; tidak ada API LLM cloud.
- **NFR-5 Keamanan input:** validasi tipe file, skema, ukuran, dan path pada setiap unggahan/input pengguna di app.
- **NFR-6 Kualitas kode:** lint (ruff), tipe (mypy, bertahap), tes otomatis, CI.
- **NFR-7 Kejujuran hasil:** hasil negatif (tidak ada pemicu signifikan, substitusi tidak mengalahkan baseline) dilaporkan apa adanya.

## 7. Desain Evaluasi (Kriteria Validitas)

Validasi proyek ini diberi ID **VP1–VP10** (baru untuk proyek ini).

| ID | Kriteria | Metode | Ambang lulus (usulan, ditetapkan sebelum eksperimen) |
|---|---|---|---|
| VP1 | Kualitas normalisasi bahan | Sampel manual ≥300 baris bahan berlabel; hitung akurasi | ≥ 90% |
| VP2 | Prediksi bahan tersembunyi | Hide-one-ingredient, top-k accuracy vs baseline frekuensi populer | Lebih baik dari baseline dengan selang kepercayaan terpisah |
| VP3 | Kualitas substitusi | Daftar substitusi acuan (sumber kuliner, ± survei kecil) — recall@k | Dilaporkan; ambang ditetapkan setelah melihat ukuran daftar acuan |
| VP4 | Stasioneritas data harga | ADF/KPSS pasca transformasi | Mayoritas seri lulus; sisanya didokumentasikan |
| VP5 | Pengendalian temuan palsu | FDR pada seluruh uji Granger; uji kontrol dengan data diacak (permutasi) | Pada data acak, proporsi sisi signifikan ≈ tingkat FDR |
| VP6 | Nilai prediktif "pemicu" | Walk-forward; model dengan fitur komoditas lain vs naive & ARIMA | Klaim "pemicu" hanya sah jika mengalahkan baseline pada data uji |
| VP7 | Ketahanan terhadap musiman | Bandingkan graph dengan/tanpa dekomposisi musiman | Persentase sisi yang bertahan dilaporkan |
| VP8 | Reprodusibilitas | Jalankan ulang pipeline, bandingkan artefak | Identik, atau dalam toleransi numerik yang ditetapkan |
| VP9 | Integritas manifest | Tes yang mengubah/menghapus artefak harus terdeteksi | 100% kasus uji terdeteksi |
| VP10 | Sumber daya | Ukur puncak RAM dan waktu tiap tahap | ≤ 8 GB RAM; hasil aktual dilaporkan |

**Aturan evaluasi**
- Pembagian data uji ditetapkan **sebelum** tuning; data uji tidak dipakai untuk memilih model/bobot.
- Preprocessing (skala, stasioneritas, ambang frekuensi) dipasang hanya pada data latih.
- Untuk deret waktu: walk-forward, **bukan** random split.
- Granger dan lead-lag dilaporkan sebagai asosiasi prediktif, bukan sebab-akibat.
- Evaluasi Modul C (gabungan) hanya menggunakan kasus yang ditetapkan sebelumnya; kasus pengembangan dan kasus evaluasi dipisah.
- Ambang di tabel di atas bersifat usulan; mengubahnya setelah melihat hasil harus dicatat sebagai deviasi, bukan dilakukan diam-diam.

## 8. Risiko & Mitigasi

| Risiko | Dampak | Mitigasi |
|---|---|---|
| Format/akses data PIHPS berubah atau dibatasi | Modul B tertunda | Verifikasi di M0; siapkan D2 sebagai cadangan; cache lokal |
| Teks bahan sangat kotor | Graph bahan bias | Kamus sinonim berversi, VP1 sebagai gerbang |
| Bias popularitas resep | Substitusi cenderung ke bahan umum | Gunakan PMI/lift, laporkan analisis per frekuensi |
| Granger disalahartikan sebagai sebab | Klaim menyesatkan | Terminologi baku, VP6 sebagai gerbang |
| Temuan palsu akibat banyak uji | Sisi graph semu | FDR + uji permutasi (VP5) |
| Musiman/hari raya menciptakan asosiasi semu | Interpretasi salah | FR-B7, VP7 |
| Substitusi statistik tidak cocok secara rasa | Rekomendasi buruk | Disclaimer, evaluasi VP3, tanpa klaim rasa |
| Pemetaan bahan↔komoditas tidak lengkap | Skor harga bolong | Tandai bahan tak terpetakan, laporkan cakupan (FR-C4) |
| Scraping melanggar ToS | Risiko hukum/etika | Hanya sumber yang mengizinkan; prioritaskan dataset publik |

## 9. Milestone & Gerbang Penerimaan

| M | Nama | Durasi (estimasi) | Gerbang penerimaan |
|---|---|---|---|
| M0 | Fondasi & verifikasi data | Minggu 1 | `DATA_SOURCES.md` terisi; sampel data tiap sumber terunduh; skema dan lisensi terdokumentasi; repo, lint, tes kosong, CI berjalan |
| M1 | Pipeline data harga | Minggu 2 | FR-B1, B2; VP4 diukur; manifest data berfungsi |
| M2 | Analisis domino | Minggu 3–4 | FR-B3–B7; VP5, VP6, VP7 diukur dan dilaporkan (apa pun hasilnya) |
| M3 | Graph bahan | Minggu 4–5 | FR-A1–A5; VP1, VP2, VP3 diukur |
| M4 | Jembatan | Minggu 6 | FR-C1–C4; cakupan pemetaan dilaporkan; evaluasi kasus tetap |
| M5 | Aplikasi & audit | Minggu 7 | FR-D1–D5; tes alur pengguna; VP8, VP9, VP10 diukur |
| M6 | Dokumentasi & rilis | Minggu 8 | Semua dokumen konsisten dengan implementasi; laporan akhir |

**Prinsip urutan:** Modul B (M1–M2) dikerjakan lebih dulu karena data lebih terstruktur. Jika berhenti di M2, proyek tetap utuh sebagai "Efek Domino Harga Pangan". M3 dapat berjalan paralel dengan M2 bila ada kapasitas.

**Aturan gerbang:** milestone berikutnya tidak dimulai bila gerbang milestone sebelumnya `FAILED` atau `BLOCKED` tanpa dokumentasi keputusan.

## 10. Tumpukan Teknologi (usulan)

- Python 3.11+, `pandas`/`polars`, `numpy`, `scipy`, `statsmodels` (ADF, Granger, ARIMA)
- Graph: `networkx`, `python-louvain` atau `leidenalg`; embedding: `gensim` (Word2Vec)
- Teks: normalisasi berbasis aturan + kamus; opsional `rapidfuzz` untuk koreksi salah ketik
- App: Streamlit + `pyvis`/`plotly`
- Mutu: `pytest`, `ruff`, `mypy`, `pre-commit`, GitHub Actions
- Manajemen lingkungan: `uv` atau `venv` + `requirements.lock`/`uv.lock`

## 11. Keluaran (Deliverables)

1. Repo dengan pipeline reproducible dan tes.
2. Artefak: graph bahan, graph harga, tabel substitusi, manifest run.
3. App Streamlit.
4. Dokumen: README, ARCHITECTURE, DATA_SOURCES, METHODOLOGY, EVALUATION_REPORT, LIMITATIONS, TRACEABILITY.
5. Laporan akhir yang memuat hasil VP1–VP10 apa adanya, termasuk hasil negatif dan keterbatasan.

## 12. Pertanyaan Terbuka (perlu diputuskan)

1. Rentang waktu dan komoditas yang dicakup (usulan awal: 10–20 komoditas pangan utama, ≥ 3 tahun data harian).
2. Apakah survei kecil untuk VP3 akan dilakukan, atau cukup daftar acuan tertulis?
3. Apakah D4 (scraping resep) dipakai, atau cukup dataset publik?
4. Bahasa UI: Indonesia saja, atau dwibahasa?
5. Apakah ada komponen LLM lokal (mis. normalisasi bahan sulit)? Default: **tidak**, kecuali terbukti menambah nilai terhadap baseline aturan+kamus.
