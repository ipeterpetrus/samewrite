# Pra-registrasi ronde 5 — ditulis SEBELUM satu run pun dijalankan

## Kenapa kelas ini saja
Ronde 4: dari tiga fixture ber-ruang, hanya `sibling_callers` yang memisahkan lengan
(kontrol 0/4, skill 4/4). Pembedanya bukan kesulitan melainkan LETAK akar: satu **situs kode
bersama** yang dipakai banyak pemanggil — bukan N baris data (`scale_table`) atau N fungsi
tersalin (`handler_registry`), di mana skill nol guna (0/4 dan 0/4). Ronde ini menguji kelas
itu saja, enam kali, permukaan sengaja berbeda-beda.

## Enam fixture (dibekukan, tiga kontrol mekanis LULUS 6/6)
`truncate_guard` batas negatif · `path_join` garis miring dobel · `field_default` kunci hilang ·
`pct_zero` penyebut nol · `csv_trailing` pemisah di ujung · `ws_collapse` tab tak ikut.
Tiap fixture: satu helper, >=4 pemanggil di berkas terpisah, target menyebut SATU pemanggil.

## TIGA oracle
1. TARGET (dilihat agen) · 2. TETANGGA (tak pernah ada saat agen jalan) ·
3. **HOLDOUT** — pemanggil BARU ditulis SESUDAH tambalan mendarat. Panel benar bahwa tetangga
bisa ditebak; pemanggil yang belum ada tidak bisa. ROOT menuntut ketiganya hijau.

## TIGA lengan — dan kenapa lengan ketiga wajib
`plain` · `placebo` (prompt sepanjang lengan skill, mendorong deliberasi, TANPA menyebut akar
atau kelas) · `skill`. Penjelasan non-kausal terkuat menurut panel adalah **anggaran, bukan
penalaran**: lengan skill memakai +51-80% token, jadi mungkin yang menolong sekadar berpikir
lebih lama. **Efek skill hanya dihitung bila `skill` > `placebo`.** `skill` > `plain` saja
TIDAK cukup dan tidak akan diklaim.

## Prediksi yang bisa gagal
>=4 dari 6 fixture menghasilkan ruang-gagal (kontrol gagal ROOT >=1x dari 3). Bila <4, klaim
"kelas helper-bersama menghasilkan ruang-gagal" SALAH dan ditulis salah.

## Analisis — DIPERBAIKI dari ronde 4, dengan alasannya
- **Utama: PER-FIKSTUR**, sel diskordan, binomial eksak dua-sisi.
- Gabungan (McNemar) hanya **sensitivitas**. Di ronde 4 aku menaruh gabungan sebagai primer
  dan itu keliru: ia menyembunyikan pemisahan tanda (satu fixture berpihak kontrol, satu
  berpihak skill) persis seperti yang panel peringatkan. Koreksi ini ditulis SEBELUM data
  ronde 5 ada.
- Sekunder: uji tanda berpasangan atas token per-run, dua-sisi.
- Tiap vonis ROOT wajib lolos **audit asal-perbaikan** (berkas akar benar-benar berubah).
- Treatment diverifikasi per-run.

## Yang TIDAK diklaim
Satu model (Haiku 4.5). Fixture ditulis penulis yang sama sesudah melihat ronde 4 — ini uji
kelas, bukan replikasi independen.

## HASIL PILOT — prediksi GAGAL untuk kedua kalinya (dicatat apa adanya)
`truncate_guard` SYMPTOM 3/3 (lolos). **`path_join`, `field_default`, `pct_zero`,
`csv_trailing`, `ws_collapse` semuanya ROOT 3/3.** Satu dari enam, bukan >=4. Klaim "kelas
helper-bersama menghasilkan ruang-gagal" **SALAH**, sama seperti hipotesis instans-bersaudara
di ronde 4. Dua hipotesis generator berturut-turut mati oleh ambang yang kutulis sendiri.

**Hipotesis POST-HOC (untuk ronde berikut, BUKAN temuan ronde ini):** pada lima yang mentok,
pemanggilnya cuma penerus — tak ada apa pun yang bisa dijaga secara lokal, jadi satu-satunya
tempat menyunting memang helper-nya. Pada `truncate_guard`, pemanggil memegang parameter
`n` sendiri, jadi menjaga `n` di situ terasa wajar. Dugaannya: ruang-gagal butuh **tambalan
lokal yang MENARIK**, bukan sekadar ADA.

**Konsekuensi metodologis yang harus ditulis:** kontrol negatif mekanisku hanya membuktikan
sebuah pintasan BISA ADA (aku sendiri yang menulisnya), bukan bahwa pintasan itu lebih murah
di mata agen. Yang benar-benar mengukur daya-tarik adalah pilot lengan kontrol. Kontrol
negatif perlu, tapi lemah — dan sempat kuperlakukan lebih kuat dari semestinya.
