# Pra-registrasi KONFIRMATORI — ditulis SEBELUM tugas baru dijalankan

Enam kali analisisku berubah di satu dataset (255 → 760 → 1.608 token/giliran → −22,4% dicabut
→ pencabutannya salah → status turun jadi eksploratori). Panel adv-max menyatakan status
konfirmatori endpoint itu **hangus**. Berkas ini mengunci satu analisis SEBELUM data ada.

## Endpoint UTAMA — satu, tidak boleh diganti
**Total `output_tokens` tertagih per run yang selesai**, berpasangan per (tugas, ulangan),
kontras **`mode` vs `oneline`**. Itu kontras yang menentukan keputusan: apakah banner 4.664 B
mengalahkan SATU KALIMAT dengan niat yang sama. Bukan `mode` vs `plain`.

## Uji
**Permutasi berpasangan eksak, dua-sisi** (2^n tanda, n = pasangan tak-seri). Uji tanda
dilaporkan sebagai sekunder. α = 0,05.

## Sekunder (dilaporkan, tidak menentukan)
`mode` vs `plain` dengan uji yang sama.

## EKSPLORATORI — dinyatakan sekarang, nol inferensi
Sel per-horizon, profil per-indeks-giliran, dekomposisi cache. Boleh dilaporkan, **dilarang**
dipakai untuk mengklaim mekanisme, dan **dilarang** menggantikan endpoint utama.

## Yang DILARANG, karena tiap larangan lahir dari satu kesalahan nyata
- Jumlah KATA sebagai pengganti token (kesalahan #1).
- Skalar per-giliran apa pun sebagai endpoint (kesalahan #2, #3, #4).
- Mengondisikan pada jumlah giliran — itu variabel PASCA-perlakuan (kesalahan #5).
- Mengganti estimand di tengah analisis (kesalahan #6).

## Data & eksklusi (ditetapkan di depan)
4 tugas BARU (belum pernah dipakai), 3 lengan, 4 ulangan = 48 run. Dikeluarkan HANYA bila:
`rc != 0`, ATAU verifikasi treatment gagal (banner absen di lengan `mode`, atau hadir di lengan
lain). Tidak ada eksklusi lain, tidak ada penambahan ulangan sesudah melihat hasil.

## Gerbang substansi
Daftar regex fakta wajib per tugas. Jawaban ringkas yang kehilangan fakta dihitung **gagal**,
bukan hemat. Dilaporkan berdampingan, tidak menggantikan endpoint.

## Artefak yang diterbitkan
Ledger per-request: `run_id, arm, task, rep, turn, input_tokens, cache_creation, cache_read,
output_tokens`. Diminta panel; tanpa ini hasilnya tak bisa diaudit siapa pun.

## Prediksi yang bisa gagal
`mode` < `oneline` pada endpoint utama dengan p < 0,05. **Bila p >= 0,05, manfaat banner
dinyatakan TIDAK terreplikasi**, dan temuan eksploratori sebelumnya tetap eksploratori
selamanya — tidak ada ronde penyelamat.
