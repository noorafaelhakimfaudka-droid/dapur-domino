# DATA_SOURCES — Hasil Verifikasi M0

Tanggal verifikasi: 2026-11-18 · Sampel mentah tersimpan di `data/raw/` dan diverifikasi dengan SHA-256 di [data/raw/manifest.json](../data/raw/manifest.json).

Status: `VERIFIED` = terbukti dari sumber primer · `UNVERIFIED` = belum terbukti · `BLOCKED` = butuh tindakan pengguna.

---

## D1 — PIHPS Nasional (Bank Indonesia)

| Aspek | Temuan terverifikasi | Status |
|---|---|---|
| Situs & `robots.txt` | `https://www.bi.go.id/hargapangan` HTTP 200; `bi.go.id/robots.txt` `Allow: /` (path `/hargapangan` tidak dilarang) | VERIFIED |
| Jumlah komoditas | **10 kategori** (`cat_1`..`cat_10`): Beras, Daging Ayam, Daging Sapi, Telur Ayam, Bawang Merah, Bawang Putih, Cabai Merah, Cabai Rawit, Minyak Goreng, Gula Pasir (21 sub-komoditas/kualitas) | VERIFIED |
| Cakupan wilayah | 34 provinsi (`ref_provinces.json`); sampel `GetGridDataKomoditas` (`showKota=true`) mengembalikan **145 baris** (1 nasional `level=0`, provinsi `level=1`, dan kota/kabupaten `level=2`) | VERIFIED |
| Frekuensi & kalender | **Hari kerja saja (Senin–Jumat)**; hari libur (mis. `01/01/2018`) ditandai `"-"` | VERIFIED |
| Kedalaman historis | Terbukti merespons untuk rentang `2018-01`, `2021-01`, hingga `2026-10` | VERIFIED (titik sampel) |
| Jenis pasar | 4 tipe (`ref_price_types.json`): `1` Pasar Tradisional, `2` Pasar Modern, `3` Pedagang Besar, `4` Produsen | VERIFIED |
| Skema payload grid | JSON `{"data": [{"no", "name", "level", "DD/MM/YYYY": "58,450" | "-", ...}]}`; sebagian nama memiliki spasi akhir (mis. `"Cabai Merah Keriting "`) | VERIFIED |
| Catatan TLS & akses | Server BI menolak handshake TLS 1.3 dari OpenSSL Python dengan reset koneksi; adapter TLS 1.2 (dengan verifikasi sertifikat penuh) merespons HTTP 200 | VERIFIED |
| Ketentuan penggunaan rinci | Footer situs: "Hak Cipta © PIHPS Nasional - Semua Hak Dilindungi". Halaman `Disclaimer.aspx` BI mengembalikan 404 pada path yang dicoba; syarat rinci redistribusi belum terverifikasi | UNVERIFIED |

**Sampel tersimpan (`data/raw/prices/`):**
- `references/ref_provinces.json` (1.097 B, SHA-256 `5aea0bf16fb7b99651744b248f0bc2fbe452180f789fc58c6327c9448ec65e51`)
- `references/ref_commodities.json` (2.785 B, SHA-256 `af6439603c170991917a665cf89e75ee072330f62f11336ea527d6088c59005d`)
- `references/ref_price_types.json` (137 B, SHA-256 `1df9fe93768955a2a1a21684ea3286907b41f77ec2938babee0bc207c328c43d`)
- `pihps_sample_daerah_cat7_prov13_2026_10.json` (1.600 B, 66 record long, SHA-256 `d25b0e9259fb39704cfa00f35b7bc70609f8f23064db42831885a359fcc992ab`)
- `pihps_sample_komoditas_cat7_2026_10_w1.json` (28.725 B, 1.015 record long, SHA-256 `0914765786f7ea0b0594ab54647dfcd295dca3e2eb1b57e7219e3307db4066c9`)

---

## D2 — Open Data Badan Pangan Nasional (Bapanas)

| Aspek | Temuan terverifikasi | Status |
|---|---|---|
| Portal & dataset terbuka | `https://data.badanpangan.go.id` HTTP 200; dataset `Indikator Anomali Harga Pangan Strategis` berlabel **Terbuka** dengan unduhan CSV langsung | VERIFIED |
| Dataset harga bulanan | `Rata-rata Harga Pangan Bulanan Tingkat Konsumen/Produsen` berlabel **Dataset Terbatas** (diarahkan ke aplikasi `sapa.badanpangan.go.id`) | VERIFIED |
| Skema sampel terbuka | `bapanas_anomaly_sample_2026_10.csv` (10.560 B, 130 baris data + header): kolom `Tahun,Bulan,Komoditas,QIPA,AIPA,IFPA,Status` (indeks bulanan 13 komoditas) | VERIFIED |
| Ketentuan penggunaan | Tautan `/privacy` mengembalikan HTTP 500; halaman `/guidelines` berisi panduan navigasi, bukan teks lisensi formal | UNVERIFIED |

**Sampel tersimpan (`data/raw/prices/`):**
- `bapanas_anomaly_sample_2026_10.csv` (10.560 B, SHA-256 `c7f9a00e716b02c786d16c821591bba1183342e50638fd9726ec43e2137f3c93`)

**Peran di proyek:** D2 terbuka hanya menyediakan indeks anomali bulanan; data harga harian tetap sepenuhnya bertumpu pada D1 (PIHPS).

---

## D3 — Dataset Resep Publik

| Kandidat | Ukuran & skema | Lisensi | Status |
|---|---|---|---|
| `junwatu/indonesian-recipes` (HF) | **69.915 baris** (`train.parquet`: 66.419 baris, `eval.parquet`: 3.496 baris; kolom: `title, ingredients[], steps[], num_ingredients, num_steps, char_count`) | `other` (`research-use-as-is`) | **VERIFIED** (diunduh oleh pengguna via sesi HF; hash dicatat di manifest) |
| `LorthGyu/indonesian-recipes` (HF) | **160 baris** pada `data/train.jsonl` (skema: `id, name, category, ingredients[], steps[], difficulty, time_minutes, region`) | MIT | VERIFIED (sampel terunduh) — hanya untuk fixture/prototipe, terlalu kecil untuk kesimpulan empiris |

**Sampel & korpus tersimpan (`data/raw/recipes/`):**
- `train.parquet` (19.500.000+ B; 66.419 baris, SHA-256 tercatat di `data/raw/manifest.json`)
- `eval.parquet` (1.030.000+ B; 3.496 baris, SHA-256 tercatat di `data/raw/manifest.json`)
- `lorthgyu_train.jsonl` (168.233 B, 160 baris, SHA-256 `e4b8df04194ae16bc66fe29f6ac5775ffcc15f2811f25b1bcb28b8413f0dc460`)

---

## D4 — Cookpad Indonesia (scraping)
**Dikeluarkan dari rencana (DEV-3).** `cookpad.com/robots.txt` memblokir crawler AI/dataset (`GPTBot`, `CCBot`, `ClaudeBot`, `anthropic-ai`, `Diffbot`, dll.).

## D5, D6 — Kalender hari raya & BMKG
Belum disusun (ditargetkan pada M2 sebagai kontrol musiman/hari raya FR-B7).

---

## Keputusan Jalur Kerja (pasca-M0)
1. **Modul B (Efek Domino Harga, M1 → M2) berjalan tanpa hambatan** menggunakan D1 (PIHPS).
2. **Modul A (Graph Bahan, M3) kini UNBLOCKED**: `junwatu/indonesian-recipes` (66.419 train + 3.496 eval) sudah tersedia lokal dan terverifikasi di manifest, dengan pemisahan ketat `train` vs `eval`.
